"""RIFE (Practical-RIFE v4.25, hzwer, MIT) frame interpolation at an arbitrary timestep, in PyTorch.

The network (IFNet: five IFBlocks refining a flow pair + a blend mask, coarse to fine) is re-typed here from the
reference `IFNet_HDv3.py` so the repo carries no vendored model code; only the weights are fetched, once, to
`~/.cache/filmtools/rife/flownet.pkl` (never committed) and checked against a pinned sha256. CUDA (fp16) when
available, CPU otherwise (slow, but the same code path: the tests and the small local runs use it).

Weights: the `flownet.pkl` of Practical-RIFE v4.25 (the 4.2x line has the 5-block head/ResConv architecture below;
4.6+ requirement of the brief is met). The author's own links are Google Drive folders; this HuggingFace mirror is a
plain file URL, and a second repo carries the byte-identical file (same sha256).
"""
from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from . import Interpolator

WEIGHTS_URL = "https://huggingface.co/MonsterMMORPG/Practical-RIFE/resolve/main/train_log/flownet.pkl"
WEIGHTS_MIRROR = "https://huggingface.co/gpanaretou/practical-rife-interpolation/resolve/main/train_log/flownet.pkl"
WEIGHTS_SHA256 = "6615790efd627772917205db291f51cd392528a157ecbb2ecaeec3bff8eb6de2"
WEIGHTS_VERSION = "Practical-RIFE v4.25"


def cache_dir() -> Path:
    return Path(os.environ.get("FILMTOOLS_CACHE", Path.home() / ".cache" / "filmtools")) / "rife"


def fetch_weights(path: Path | None = None) -> Path:
    """The verified `flownet.pkl`, downloaded (main URL, then the mirror) when it is not in the cache."""
    path = path or cache_dir() / "flownet.pkl"
    if path.is_file() and _sha256(path) == WEIGHTS_SHA256:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    for url in (WEIGHTS_URL, WEIGHTS_MIRROR):
        tmp = path.with_suffix(".part")
        try:
            with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            if _sha256(tmp) != WEIGHTS_SHA256:
                raise ValueError("sha256 mismatch")
            tmp.replace(path)
            return path
        except Exception as e:                      # try the next source
            errors.append(f"{url}: {e}")
            tmp.unlink(missing_ok=True)
    raise RuntimeError("could not fetch the RIFE weights:\n  " + "\n  ".join(errors))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


_grids: dict = {}


def warp(x, flow):
    """Backward-warp `x` by `flow` (pixels), border-clamped; grid cached per (device, shape)."""
    k = (str(flow.device), tuple(flow.shape))
    if k not in _grids:
        hor = torch.linspace(-1.0, 1.0, flow.shape[3], device=flow.device).view(1, 1, 1, -1).expand(flow.shape[0], -1, flow.shape[2], -1)
        ver = torch.linspace(-1.0, 1.0, flow.shape[2], device=flow.device).view(1, 1, -1, 1).expand(flow.shape[0], -1, -1, flow.shape[3])
        _grids[k] = torch.cat([hor, ver], 1)
    f = torch.cat([flow[:, 0:1] / ((x.shape[3] - 1.0) / 2.0), flow[:, 1:2] / ((x.shape[2] - 1.0) / 2.0)], 1)
    g = (_grids[k].to(flow.dtype) + f).permute(0, 2, 3, 1)
    return F.grid_sample(x, g, mode="bilinear", padding_mode="border", align_corners=True)


def _conv(i, o, k=3, s=1, p=1):
    return nn.Sequential(nn.Conv2d(i, o, k, s, p), nn.LeakyReLU(0.2, True))


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.cnn0 = nn.Conv2d(3, 16, 3, 2, 1)
        self.cnn1 = nn.Conv2d(16, 16, 3, 1, 1)
        self.cnn2 = nn.Conv2d(16, 16, 3, 1, 1)
        self.cnn3 = nn.ConvTranspose2d(16, 4, 4, 2, 1)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x):
        x = self.relu(self.cnn0(x))
        x = self.relu(self.cnn1(x))
        x = self.relu(self.cnn2(x))
        return self.cnn3(x)


class ResConv(nn.Module):
    def __init__(self, c):
        super().__init__()
        self.conv = nn.Conv2d(c, c, 3, 1, 1)
        self.beta = nn.Parameter(torch.ones((1, c, 1, 1)))
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x):
        return self.relu(self.conv(x) * self.beta + x)


class IFBlock(nn.Module):
    def __init__(self, in_planes, c=64):
        super().__init__()
        self.conv0 = nn.Sequential(_conv(in_planes, c // 2, 3, 2, 1), _conv(c // 2, c, 3, 2, 1))
        self.convblock = nn.Sequential(*[ResConv(c) for _ in range(8)])
        self.lastconv = nn.Sequential(nn.ConvTranspose2d(c, 4 * 13, 4, 2, 1), nn.PixelShuffle(2))

    def forward(self, x, flow=None, scale=1):
        x = F.interpolate(x, scale_factor=1.0 / scale, mode="bilinear", align_corners=False)
        if flow is not None:
            flow = F.interpolate(flow, scale_factor=1.0 / scale, mode="bilinear", align_corners=False) / scale
            x = torch.cat((x, flow), 1)
        tmp = self.lastconv(self.convblock(self.conv0(x)))
        tmp = F.interpolate(tmp, scale_factor=scale, mode="bilinear", align_corners=False)
        return tmp[:, :4] * scale, tmp[:, 4:5], tmp[:, 5:]


class IFNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.block0 = IFBlock(7 + 8, c=192)
        self.block1 = IFBlock(8 + 4 + 8 + 8, c=128)
        self.block2 = IFBlock(8 + 4 + 8 + 8, c=96)
        self.block3 = IFBlock(8 + 4 + 8 + 8, c=64)
        self.block4 = IFBlock(8 + 4 + 8 + 8, c=32)
        self.encode = Head()

    def forward(self, img0, img1, timestep, scale_list=(16, 8, 4, 2, 1)):
        """img0, img1: Bx3xHxW in 0..1 (H, W multiples of 64); timestep: Bx1x1x1 in 0..1. Returns the middle image."""
        timestep = timestep.expand(-1, 1, img0.shape[2], img0.shape[3])
        f0, f1 = self.encode(img0), self.encode(img1)
        blocks = [self.block0, self.block1, self.block2, self.block3, self.block4]
        flow = mask = feat = None
        w0, w1 = img0, img1
        for blk, sc in zip(blocks, scale_list):
            if flow is None:
                flow, mask, feat = blk(torch.cat((img0, img1, f0, f1, timestep), 1), None, scale=sc)
            else:
                fd, mask, feat = blk(torch.cat((w0, w1, warp(f0, flow[:, :2]), warp(f1, flow[:, 2:4]), timestep, mask, feat), 1),
                                     flow, scale=sc)
                flow = flow + fd
            w0, w1 = warp(img0, flow[:, :2]), warp(img1, flow[:, 2:4])
        m = torch.sigmoid(mask)
        return w0 * m + w1 * (1 - m)


class RifeInterpolator(Interpolator):
    name = "rife"

    def __init__(self, device=None, half=None, weights=None, scale=1.0, batch=4):
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.half = (self.device.type == "cuda") if half is None else half
        self.scale = scale
        self.batch = batch
        self.net = IFNet()
        sd = torch.load(fetch_weights(Path(weights) if weights else None), map_location="cpu", weights_only=True)
        sd = {k.replace("module.", ""): v for k, v in sd.items()}
        missing, _ = self.net.load_state_dict(sd, strict=False)
        if missing:
            raise RuntimeError(f"RIFE weights do not match the network: missing {missing[:4]}")
        self.net.eval().to(self.device)
        if self.half:
            self.net.half()

    def _tensor(self, img, ph, pw):
        x = torch.from_numpy(np.ascontiguousarray(img)).permute(2, 0, 1)[None].to(self.device)
        x = F.pad(x, (0, pw, 0, ph), mode="replicate")
        return x.half() if self.half else x

    @torch.no_grad()
    def between(self, img0, img1, ts):
        h, w = img0.shape[:2]
        step = int(64 / min(1.0, self.scale))
        ph, pw = (-h) % step, (-w) % step
        a, b = self._tensor(img0, ph, pw), self._tensor(img1, ph, pw)
        sl = [16 / self.scale, 8 / self.scale, 4 / self.scale, 2 / self.scale, 1 / self.scale]
        out = []
        for i in range(0, len(ts), self.batch):
            chunk = ts[i:i + self.batch]
            t = torch.tensor(chunk, dtype=a.dtype, device=self.device).view(-1, 1, 1, 1)
            y = self.net(a.expand(len(chunk), -1, -1, -1), b.expand(len(chunk), -1, -1, -1), t, sl)
            y = y[:, :, :h, :w].float().clamp(0, 1).permute(0, 2, 3, 1).cpu().numpy()
            out.extend(np.ascontiguousarray(y[j]) for j in range(len(chunk)))
        return out


if __name__ == "__main__":
    import sys
    if "--fetch" in sys.argv:
        print(fetch_weights())
