"""Timeless v3 prep on the plates: BiRefNet subject mattes and Video Depth Anything depth (pod_prep3.sh runs it on a
RunPod 4090; it also runs on CPU for tests). Python 3.10, numpy + opencv (+ torch/transformers/VDA for the models).

    python prep3.py mattes --data DIR [--only S08,P1] [--device cuda|cpu] [--px 1024] [--limit N] [--batch 8]
    python prep3.py depth  --data DIR [--only ...] [--device ...] [--vda-repo DIR] [--model large|small] [--input-size 518]
                           [--limit N] [--fallback]
    python prep3.py verify --data DIR [--only ...] [--sheets-copy DIR]

DIR holds `plates/<id>/f_NNNNN.jpg` + `plate.json` (plates.py). Writes
  mattes/<id>/f_NNNNN.png   8-bit grey, white subject. BiRefNet (ZhengPeng7/BiRefNet, as v2) at px x px, triangle temporal
                            smoothing (radius 2, edge-preserving: no ghosts on fast motion) that never crosses a scene change of the plate, v2's levels (12..235).
  depth/<id>/f_NNNNN.png    16-bit grey, near = white. Video Depth Anything (temporally consistent, relative disparity),
                            run per scene segment of the plate, then ONE linear range per segment (0.5 / 99.5 percentiles
                            over all its frames) -> 0..65535: stable, not per frame. --fallback: Depth Anything V2 Large
                            per frame, each frame least-squares aligned (scale + shift) to the running reference, then
                            triangle-smoothed (radius 2), then the same range normalisation.
  <kind>/<id>/<kind>.json   done marker: plate frame list + settings. A shot whose marker matches is skipped (resumable).
Scene segments of a plate: split where plate.json `source_cut` lands and where consecutive src240 indices jump by more
than 4 x 60 fps frames (a clip's own cut inside the handles never happens: plates.py clamps them).
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np

LEVEL_LO, LEVEL_HI = 12.0, 235.0
W, H = 1920, 1080


def log(*a):
    print("[prep3]", *a, flush=True)


def plate_ids(data, only):
    ids = sorted(p.name for p in (data / "plates").iterdir() if (p / "plate.json").exists())
    if only:
        keep = set(only.split(","))
        ids = [i for i in ids if i in keep]
    return ids


def plate(data, sid, limit=None):
    meta = json.loads((data / "plates" / sid / "plate.json").read_text())
    fs = sorted(int(f) for f in meta["frames"])
    if limit:
        fs = fs[:limit]
    return meta, fs


def segments(meta, fs):
    """Lists of consecutive frames that belong to one scene."""
    cut = meta.get("source_cut")
    segs, cur = [], []
    for f in fs:
        if cur:
            jump = abs(meta["frames"][str(f)]["src240"] - meta["frames"][str(cur[-1])]["src240"]) > 16
            if (cut and f == cut["f"]) or jump:
                segs.append(cur)
                cur = []
        cur.append(f)
    if cur:
        segs.append(cur)
    return segs


def read_rgb(data, sid, f):
    return cv2.cvtColor(cv2.imread(str(data / "plates" / sid / f"f_{f:05d}.jpg")), cv2.COLOR_BGR2RGB)


def done(path, fs, settings):
    if not path.exists():
        return False
    try:
        m = json.loads(path.read_text())
    except ValueError:
        return False
    return m.get("frames") == fs and m.get("settings") == settings


def mark(path, fs, settings, extra=None):
    path.write_text(json.dumps(dict(frames=fs, settings=settings, **(extra or {})), indent=0))


def smooth_time(p, seg_id, radius):
    """Triangle filter along time on (n, ...) arrays, never across a segment change."""
    n = len(p)
    if radius <= 0 or n < 2:
        return p
    seg_id = np.asarray(seg_id)
    acc = np.zeros(p.shape, np.float32)
    wsum = np.zeros(n, np.float32)
    for o in range(-radius, radius + 1):
        w = radius + 1 - abs(o)
        idx = np.clip(np.arange(n) + o, 0, n - 1)
        ok = (seg_id[idx] == seg_id).astype(np.float32) * w
        acc += p[idx].astype(np.float32) * ok.reshape((-1,) + (1,) * (p.ndim - 1))
        wsum += ok
    return acc / wsum.reshape((-1,) + (1,) * (p.ndim - 1))


def smooth_matte(p, seg_id, radius=2, sigma=24.0):
    """Edge-preserving temporal filter for mattes at comp rate: triangle weights times exp(-(dp/sigma)^2) per pixel, so
    static edges lose their flicker and moving edges (dp large: plate frames are up to 16 source frames apart) do not
    ghost. Never across a segment change."""
    n = len(p)
    if radius <= 0 or n < 2:
        return p.astype(np.float32)
    seg_id = np.asarray(seg_id)
    pf = p.astype(np.float32)
    out = np.empty_like(pf)
    for i in range(n):
        acc = pf[i].copy()
        ws = np.ones_like(acc)
        for o in range(-radius, radius + 1):
            j = i + o
            if o == 0 or j < 0 or j >= n or seg_id[j] != seg_id[i]:
                continue
            w = (radius + 1 - abs(o)) / (radius + 1) * np.exp(-((pf[j] - pf[i]) / sigma) ** 2)
            acc += w * pf[j]
            ws += w
        out[i] = acc / ws
    return out


# ---------------------------------------------------------------- mattes
class BiRefNet:
    REPO = "ZhengPeng7/BiRefNet"

    def __init__(self, device, batch):
        import torch
        from transformers import AutoModelForImageSegmentation
        self.torch, self.device, self.batch = torch, torch.device(device), batch
        m = AutoModelForImageSegmentation.from_pretrained(self.REPO, trust_remote_code=True)
        self.half = self.device.type == "cuda"
        self.m = m.eval().to(self.device, dtype=torch.float16 if self.half else torch.float32)
        self.mean = torch.tensor([0.485, 0.456, 0.406], device=self.device).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], device=self.device).view(1, 3, 1, 1)

    def probs(self, imgs):
        torch = self.torch
        x = torch.from_numpy(np.stack(imgs)).to(self.device).permute(0, 3, 1, 2).float() / 255.0
        x = (x - self.mean) / self.std
        if self.half:
            x = x.half()
        with torch.no_grad():
            p = self.m(x)[-1].sigmoid().float()
        return (p[:, 0].clamp(0, 1) * 255.0 + 0.5).byte().cpu().numpy()


def cmd_mattes(a, data):
    settings = dict(model=BiRefNet.REPO, px=a.px, smooth="adaptive2/24", levels=[LEVEL_LO, LEVEL_HI])
    net = None
    for sid in plate_ids(data, a.only):
        meta, fs = plate(data, sid, a.limit)
        out = data / "mattes" / sid
        if done(out / "matte.json", fs, settings):
            log(f"mattes {sid}: done, skipped")
            continue
        net = net or BiRefNet(a.device, a.batch)
        t0 = time.time()
        segs = segments(meta, fs)
        seg_id = [i for i, s in enumerate(segs) for _ in s]
        # holds repeat a src240 frame: matte each distinct source frame once
        uniq, probs, buf = {}, {}, []
        for f in fs:
            uniq.setdefault(meta["frames"][str(f)]["src240"], f)
        todo = list(uniq.items())

        def flush(batch):
            ps = net.probs([b[1] for b in batch])
            for (j, _), p in zip(batch, ps):
                probs[j] = p

        for j, f in todo:
            buf.append((j, cv2.resize(read_rgb(data, sid, f), (a.px, a.px), interpolation=cv2.INTER_AREA)))
            if len(buf) == net.batch:
                flush(buf)
                buf = []
        if buf:
            flush(buf)
        p = np.stack([probs[meta["frames"][str(f)]["src240"]] for f in fs])
        p = smooth_matte(p, seg_id)
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        for f, m in zip(fs, p):
            up = cv2.resize(m, (W, H), interpolation=cv2.INTER_CUBIC)
            up = np.clip((up - LEVEL_LO) * (255.0 / (LEVEL_HI - LEVEL_LO)), 0, 255).astype(np.uint8)
            cv2.imwrite(str(out / f"f_{f:05d}.png"), up)
        mark(out / "matte.json", fs, settings, dict(segments=[[s[0], s[-1]] for s in segs]))
        log(f"mattes {sid}: {len(fs)} frames ({len(todo)} distinct) in {time.time() - t0:.1f} s")


# ---------------------------------------------------------------- depth
VDA_CFG = {"small": ("vits", 64, [48, 96, 192, 384], "depth-anything/Video-Depth-Anything-Small", "video_depth_anything_vits.pth"),
           "large": ("vitl", 256, [256, 512, 1024, 1024], "depth-anything/Video-Depth-Anything-Large", "video_depth_anything_vitl.pth")}


class VDA:
    def __init__(self, repo, model, device, input_size):
        import torch
        from huggingface_hub import hf_hub_download
        sys.path.insert(0, str(repo))
        from video_depth_anything.video_depth import VideoDepthAnything
        enc, feat, oc, hf, fn = VDA_CFG[model]
        ckpt = hf_hub_download(hf, fn)
        self.m = VideoDepthAnything(encoder=enc, features=feat, out_channels=oc)
        self.m.load_state_dict(torch.load(ckpt, map_location="cpu"), strict=True)
        self.m = self.m.to(device).eval()
        self.device, self.input_size = device, input_size
        self.params = inspect.signature(self.m.infer_video_depth).parameters

    def __call__(self, frames):
        kw = dict(input_size=self.input_size, device=self.device)
        if "fp32" in self.params:
            kw["fp32"] = self.device == "cpu"
        r = self.m.infer_video_depth(np.stack(frames), 30, **kw)
        d = r[0] if isinstance(r, tuple) else r
        return np.asarray(d, np.float32)[:len(frames)]


class DAV2:
    """Fallback: Depth Anything V2 Large per frame + temporal alignment and smoothing."""

    def __init__(self, device, input_size):
        import torch
        from transformers import AutoModelForDepthEstimation
        self.torch, self.device = torch, device
        self.m = AutoModelForDepthEstimation.from_pretrained("depth-anything/Depth-Anything-V2-Large-hf").to(device).eval()
        self.input_size = input_size

    def one(self, img):
        torch = self.torch
        h, w = img.shape[:2]
        s = self.input_size / min(h, w)
        nh, nw = int(round(h * s / 14)) * 14, int(round(w * s / 14)) * 14
        x = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
        x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        x = torch.from_numpy(x.transpose(2, 0, 1)[None].astype(np.float32)).to(self.device)
        with torch.no_grad():
            d = self.m(pixel_values=x).predicted_depth
        return cv2.resize(d[0].float().cpu().numpy(), (w, h), interpolation=cv2.INTER_CUBIC)

    def __call__(self, frames):
        ds = [self.one(f) for f in frames]
        ref = ds[0]
        out = [ref]
        for d in ds[1:]:                           # scale + shift to the running reference (least squares, 1/8 grid)
            a, b = d[::8, ::8].ravel(), ref[::8, ::8].ravel()
            A = np.stack([a, np.ones_like(a)], 1)
            k, c = np.linalg.lstsq(A, b, rcond=None)[0]
            al = d * k + c
            out.append(al)
            ref = 0.7 * ref + 0.3 * al
        return smooth_time(np.stack(out), [0] * len(out), 2)


def cmd_depth(a, data):
    name = "dav2" if a.fallback else f"vda-{a.model}"
    settings = dict(model=name, input_size=a.input_size, range=[0.5, 99.5])
    net = None
    for sid in plate_ids(data, a.only):
        meta, fs = plate(data, sid, a.limit)
        out = data / "depth" / sid
        if done(out / "depth.json", fs, settings):
            log(f"depth {sid}: done, skipped")
            continue
        if net is None:
            net = DAV2(a.device, a.input_size) if a.fallback else VDA(a.vda_repo, a.model, a.device, a.input_size)
        t0 = time.time()
        segs = segments(meta, fs)
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        ranges = []
        for seg in segs:
            d = net([read_rgb(data, sid, f) for f in seg])
            if d.shape[1:] != (H, W):
                d = np.stack([cv2.resize(x, (W, H), interpolation=cv2.INTER_CUBIC) for x in d])
            sample = d[:, ::4, ::4]
            lo, hi = np.percentile(sample, 0.5), np.percentile(sample, 99.5)
            ranges.append([float(lo), float(hi)])
            for f, x in zip(seg, d):
                v = np.clip((x - lo) / max(hi - lo, 1e-6), 0, 1)
                cv2.imwrite(str(out / f"f_{f:05d}.png"), (v * 65535 + 0.5).astype(np.uint16))
        mark(out / "depth.json", fs, settings, dict(segments=[[s[0], s[-1]] for s in segs], ranges=ranges))
        log(f"depth {sid}: {len(fs)} frames, {len(segs)} segment(s) in {time.time() - t0:.1f} s")


# ---------------------------------------------------------------- verify
def cmd_verify(a, data):
    bad = []
    sd = data / "prep_sheets"
    sd.mkdir(exist_ok=True)
    for sid in plate_ids(data, a.only):
        meta, fs = plate(data, sid)
        md, dd = data / "mattes" / sid, data / "depth" / sid
        nm = len(list(md.glob("f_*.png"))) if md.exists() else 0
        nd = len(list(dd.glob("f_*.png"))) if dd.exists() else 0
        ok = nm == len(fs) and nd == len(fs)
        if not ok:
            bad.append(sid)
        log(f"verify {sid}: plates {len(fs)} mattes {nm} depth {nd}" + ("" if ok else "  INCOMPLETE"))
        have = [f for f in fs if (md / f"f_{f:05d}.png").exists() or (dd / f"f_{f:05d}.png").exists()]
        if not have:
            continue
        pick = [have[round(i * (len(have) - 1) / 5)] for i in range(6)] if len(have) >= 6 else have
        rows = []
        for f in pick:
            tw, th = 384, 216
            pl = cv2.resize(cv2.imread(str(data / "plates" / sid / f"f_{f:05d}.jpg")), (tw, th), interpolation=cv2.INTER_AREA)
            m = cv2.imread(str(md / f"f_{f:05d}.png"), cv2.IMREAD_GRAYSCALE)
            m = np.zeros((th, tw), np.uint8) if m is None else cv2.resize(m, (tw, th), interpolation=cv2.INTER_AREA)
            d = cv2.imread(str(dd / f"f_{f:05d}.png"), cv2.IMREAD_UNCHANGED)
            d = np.zeros((th, tw), np.uint8) if d is None else cv2.resize((d >> 8).astype(np.uint8), (tw, th), interpolation=cv2.INTER_AREA)
            comp = (pl * 0.5 + np.dstack([np.zeros_like(m), m, np.zeros_like(m)]) * 0.5).astype(np.uint8)
            row = np.hstack([pl, cv2.cvtColor(m, cv2.COLOR_GRAY2BGR), comp, cv2.applyColorMap(d, cv2.COLORMAP_INFERNO)])
            cv2.putText(row, f"{sid} f{f}", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
            rows.append(row)
        cv2.imwrite(str(sd / f"{sid}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
        if a.sheets_copy:
            Path(a.sheets_copy).mkdir(parents=True, exist_ok=True)
            shutil.copy(sd / f"{sid}.jpg", Path(a.sheets_copy) / f"{sid}.jpg")
    log(f"verify: {len(bad)} incomplete: {bad}")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("mattes", "depth", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--data", default=os.environ.get("AMV3_DATA", "/home/nikhil/code/film-making/work/timeless_v3"))
        p.add_argument("--only", default="")
        p.add_argument("--limit", type=int, default=None, help="first N plate frames per shot (tests)")
        p.add_argument("--device", default="cuda")
        p.add_argument("--sheets-copy", default="")
    sub.choices["mattes"].add_argument("--px", type=int, default=1024)
    sub.choices["mattes"].add_argument("--batch", type=int, default=8)
    d = sub.choices["depth"]
    d.add_argument("--vda-repo", default=os.environ.get("VDA_REPO", "/workspace/Video-Depth-Anything"))
    d.add_argument("--model", choices=("large", "small"), default="large")
    d.add_argument("--input-size", type=int, default=518)
    d.add_argument("--fallback", action="store_true", help="Depth Anything V2 Large + temporal smoothing instead of VDA")
    a = ap.parse_args(argv)
    data = Path(a.data)
    rc = dict(mattes=cmd_mattes, depth=cmd_depth, verify=cmd_verify)[a.cmd](a, data)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
