"""v2 source prep: RIFE 240 fps copies of the handover clips and BiRefNet subject mattes.

    python -m filmtools.amv2.prep rife240 [--clips A03_sunset_mask,...] --out DIR [--device cuda|cpu] [--scale S] [--limit N]
    python -m filmtools.amv2.prep mattes --clips A03_sunset_mask,... --out DIR [--src240 DIR] [--device ...] [--scale S] [--limit N]

rife240: `DIR/clip_<ID>.mp4` + `DIR/clip_<ID>.json`. Same timeline as the 60 fps clip: output frame 4k is source frame k
(exactly, bit for bit before encoding) and the clip keeps its duration (4n frames for n source frames; the last source
frame is held for its 3 trailing frames). Frames 4k+1..4k+3 are RIFE at t = .25/.5/.75. Across a hard cut (retime.detect_cuts)
nothing is interpolated: the three frames repeat the frame before the cut, so the cut stays exactly on frame 4c.
Sources that run at half rate (frames duplicated, M01: >25% repeats) are interpolated between their distinct frames
instead (the 4k == k rule then holds only at the distinct frames); disable with --no-dedup.

mattes: `DIR/<ID>/NNNNN.png`, 8-bit grey, white subject on black, one per 240 fps frame (aligned to `src240/clip_<ID>.mp4`;
when that is missing the 60 fps clip is matted and the matte is blended up to 240). BiRefNet at 1024 px, light temporal
smoothing (triangle, radius 2, never across a cut).

Needs numpy, opencv, torch (+ transformers, timm, einops, kornia for mattes) and ffmpeg with libx264.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from filmtools.amv import retime

HANDOVER = Path(os.environ.get("AMV_HANDOVER", "/home/nikhil/code/film-making/handover/amv_handover"))
CLIPS = HANDOVER / "footage_clips"
MATTE_CLIPS = ["A03_sunset_mask", "M08_shuriken", "T03_glove_city", "M14_head_raise", "M16_sunset_hero", "T01_mask_night"]
FACTOR = 4
LEVEL_LO, LEVEL_HI = 12.0, 235.0   # matte levels: below LO is black, above HI is white
DUP_STEP = 0.3          # mean abs step (0..255 on a 1/8 frame) under which two frames are the same picture
DUP_RATIO = 0.25        # share of repeated steps over which a clip counts as half-rate


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def clip_ids(arg=None):
    if arg:
        return [c.strip().removeprefix("clip_") for c in arg.split(",") if c.strip()]
    return sorted(p.name[5:-4] for p in CLIPS.glob("clip_*.mp4"))


def clip_path(cid):
    p = CLIPS / f"clip_{cid}.mp4"
    if not p.is_file():
        raise SystemExit(f"no such clip: {p}")
    return p


def pick_device(name):
    import torch
    if name == "cuda" and not torch.cuda.is_available():
        raise SystemExit("--device cuda, but torch.cuda is not available")
    return name


def even(v):
    return max(2, int(round(v / 2)) * 2)


# ---------------------------------------------------------------- analysis

def analyse(path):
    """(small frames, cut frames, step sizes d[j] = frame j -> j+1) of a clip, decoded at 1/8 size."""
    small = retime.decode_clip(path, 0.125)
    g = small[:, ::2, ::2].astype(np.float32).mean(axis=3)
    d = np.abs(g[1:] - g[:-1]).mean(axis=(1, 2)) if len(g) > 1 else np.zeros(0)
    return retime.detect_cuts(small), d


def plan_frames(n, cuts, d, dedup):
    """For every output frame the source mix: (a, b, t), image a when t == 0, else RIFE(a, b, t).

    Runs of identical source frames (when dedup) are crossed as one interval; cuts and the clip end hold."""
    cutset = set(cuts)
    dup = [bool(d[j] < DUP_STEP) and (j + 1) not in cutset for j in range(n - 1)]     # frame j+1 repeats frame j
    run_start, run_len = list(range(n)), [1] * n
    if dedup:
        s = 0
        while s < n:
            e = s
            while e < n - 1 and dup[e]:
                e += 1
            for j in range(s, e + 1):
                run_start[j] = s
            for j in range(s, e + 1):
                run_len[j] = e - s + 1
            s = e + 1
    out = []
    for k in range(n):
        s, L = run_start[k], run_len[k]
        nxt = s + L
        for i in range(FACTOR):
            if i == 0 and L == 1:
                out.append((k, k, 0.0))
            elif nxt >= n or nxt in cutset:                      # clip end or cut ahead: hold the real frame
                out.append((s if dedup else k, s if dedup else k, 0.0))
            elif L == 1:
                out.append((k, k + 1, i / FACTOR))
            else:
                out.append((s, nxt, ((k - s) + i / FACTOR) / L))
    return out


# ---------------------------------------------------------------- RIFE

class Rife:
    """Practical-RIFE (the repo's IFNet) with several (pair, t) items per network call."""

    def __init__(self, device, batch):
        import torch
        from filmtools.amv.interp.rife import RifeInterpolator
        self.torch = torch
        self.r = RifeInterpolator(device=device)
        self.batch = batch

    def run(self, a_list, b_list, ts):
        torch, r = self.torch, self.r
        h, w = a_list[0].shape[:2]
        ph, pw = (-h) % 64, (-w) % 64

        def prep(imgs):
            x = torch.from_numpy(np.stack(imgs)).to(r.device).permute(0, 3, 1, 2).float() / 255.0
            x = torch.nn.functional.pad(x, (0, pw, 0, ph), mode="replicate")
            return x.half() if r.half else x
        a, b = prep(a_list), prep(b_list)
        t = torch.tensor(ts, dtype=a.dtype, device=r.device).view(-1, 1, 1, 1)
        with torch.no_grad():
            y = r.net(a, b, t, (16, 8, 4, 2, 1))
        y = (y[:, :, :h, :w].float().clamp(0, 1) * 255.0 + 0.5).permute(0, 2, 3, 1).byte().cpu().numpy()
        return list(y)


def encoder(out, w, h, pix_fmt, crf, gop):
    vf = f"scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format={pix_fmt}"
    cmd = [retime.ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", "240",
           "-i", "-", "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-g", str(gop),
           "-keyint_min", str(gop), "-bf", "0", "-sc_threshold", "0", "-colorspace", "bt709", "-color_primaries", "bt709",
           "-color_trc", "bt709", "-color_range", "tv", "-movflags", "+faststart", "-an", str(out)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def rife_clip(cid, out_dir, rife, scale, limit, dedup, pix_fmt, crf, gop):
    t0 = time.time()
    path = clip_path(cid)
    cuts, d = analyse(path)
    frames = retime.decode_clip(path, scale)
    n_all = len(frames)
    n = min(n_all, limit) if limit else n_all
    dedup = dedup and n > 1 and float((d < DUP_STEP).mean()) > DUP_RATIO
    mix = plan_frames(n, [c for c in cuts if c < n], d[:max(0, n - 1)], dedup)
    h, w = frames.shape[1:3]
    out = out_dir / f"clip_{cid}.mp4"
    enc = encoder(out, w, h, pix_fmt, crf, gop)
    pend = []

    def flush():
        if not pend:
            return
        ys = rife.run([frames[a] for _, a, _, _ in pend], [frames[b] for _, _, b, _ in pend], [t for _, _, _, t in pend])
        for y in ys:
            enc.stdin.write(y.tobytes())
        pend.clear()
    # real frames go straight to the encoder, interpolated ones through the batch (order is kept: flush first)
    for i, (a, b, t) in enumerate(mix):
        if t == 0.0:
            flush()
            enc.stdin.write(frames[a].tobytes())
        else:
            pend.append((i, a, b, t))
            if len(pend) >= rife.batch:
                flush()
    flush()
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {cid}")
    side = {"clip": cid, "source": str(path), "src_fps": 60, "fps": 240, "factor": FACTOR, "scale": scale,
            "src_frames": n, "frames": len(mix), "cuts_src": [c for c in cuts if c < n],
            "cuts": [FACTOR * c for c in cuts if c < n], "dedup": dedup, "width": w, "height": h,
            "pix_fmt": pix_fmt, "crf": crf, "gop": gop, "rife": "Practical-RIFE v4.25",
            "seconds": round(time.time() - t0, 1)}
    (out_dir / f"clip_{cid}.json").write_text(json.dumps(side, indent=1))
    log(f"{cid}: {n} -> {len(mix)} frames, cuts {side['cuts']}, dedup {dedup}, {side['seconds']} s")
    return side


def cmd_rife(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rife = Rife(pick_device(a.device), a.batch)
    for cid in clip_ids(a.clips):
        rife_clip(cid, out, rife, a.scale, a.limit, not a.no_dedup, a.pix_fmt, a.crf, a.gop)


# ---------------------------------------------------------------- mattes

def stream_rgb(path, w, h, limit=None):
    """Frames of a video as (h, w, 3) uint8 RGB (full range), scaled by ffmpeg."""
    vf = f"scale={w}:{h}:in_range=tv:in_color_matrix=bt709:out_range=pc:flags=bicubic+accurate_rnd+full_chroma_int,format=rgb24"
    cmd = [retime.ffmpeg_bin(), "-v", "error", "-i", str(path), "-fps_mode", "passthrough", "-vf", vf]
    if limit:
        cmd += ["-frames:v", str(limit)]
    p = subprocess.Popen(cmd + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = w * h * 3
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    p.stdout.close()
    p.wait()


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
        """uint8 probability maps (len, s, s) for a list of (s, s, 3) uint8 RGB frames."""
        torch = self.torch
        x = torch.from_numpy(np.stack(imgs)).to(self.device).permute(0, 3, 1, 2).float() / 255.0
        x = (x - self.mean) / self.std
        if self.half:
            x = x.half()
        with torch.no_grad():
            p = self.m(x)[-1].sigmoid().float()
        return (p[:, 0].clamp(0, 1) * 255.0 + 0.5).byte().cpu().numpy()


def smooth_time(p, cuts, radius):
    """Triangle filter along time on (n, s, s) uint8 probabilities, clamped at the clip ends and at every cut."""
    n = len(p)
    if radius <= 0 or n < 2:
        return p
    seg = np.zeros(n, np.int32)
    for c in cuts:
        seg[c:] += 1
    acc = np.zeros(p.shape, np.float32)
    wsum = np.zeros(n, np.float32)
    for o in range(-radius, radius + 1):
        w = radius + 1 - abs(o)
        idx = np.clip(np.arange(n) + o, 0, n - 1)
        ok = (seg[idx] == seg).astype(np.float32) * w
        acc += p[idx].astype(np.float32) * ok[:, None, None]
        wsum += ok
    return (acc / wsum[:, None, None] + 0.5).astype(np.uint8)


def matte_clip(cid, out_root, net, src240, scale, limit, radius):
    import cv2
    t0 = time.time()
    path60 = clip_path(cid)
    cuts60, _ = analyse(path60)
    w0, h0, _, n60 = retime.probe(path60)
    w, h = even(w0 * scale), even(h0 * scale)
    s = max(64, int(round(1024 * scale / 32)) * 32)
    f240 = Path(src240) / f"clip_{cid}.mp4" if src240 else None
    native = bool(f240 and f240.is_file())
    if native:
        src, cuts = f240, [FACTOR * c for c in cuts60]
        n = FACTOR * n60
    else:
        log(f"{cid}: no 240 fps source in {src240}; matting the 60 fps clip and blending the matte up")
        src, cuts, n = path60, cuts60, n60
    if limit:
        n = min(n, limit if native else -(-limit // FACTOR) + 1)
    cuts = [c for c in cuts if c < n]
    probs, buf = [], []
    for fr in stream_rgb(src, s, s, n):
        buf.append(fr)
        if len(buf) == net.batch:
            probs.extend(net.probs(buf))
            buf = []
    if buf:
        probs.extend(net.probs(buf))
    p = np.stack(probs)
    if not native:                               # blend up to 240 fps; the cut frames repeat the matte before the cut
        cutset, up = set(cuts), []
        for k in range(len(p)):
            for i in range(FACTOR):
                nxt = k + 1
                if i == 0 or nxt >= len(p) or nxt in cutset:
                    up.append(p[k])
                else:
                    up.append(((p[k].astype(np.float32) * (FACTOR - i) + p[nxt] * i) / FACTOR + 0.5).astype(np.uint8))
        p = np.stack(up)[:limit] if limit else np.stack(up)
        cuts = [FACTOR * c for c in cuts60 if FACTOR * c < len(p)]
    p = smooth_time(p, cuts, radius)
    out = Path(out_root) / cid
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    for i, m in enumerate(p):
        up = cv2.resize(m, (w, h), interpolation=cv2.INTER_CUBIC)
        up = np.clip((up.astype(np.float32) - LEVEL_LO) * (255.0 / (LEVEL_HI - LEVEL_LO)), 0, 255).astype(np.uint8)   # solid core, clean edge foot
        cv2.imwrite(str(out / f"{i:05d}.png"), up)
    (out / "matte.json").write_text(json.dumps({"clip": cid, "frames": len(p), "fps": 240, "width": w, "height": h,
                                                "cuts": cuts, "model": net.REPO, "model_px": s, "smooth_radius": radius,
                                                "native_240": native, "scale": scale}, indent=1))
    log(f"{cid}: {len(p)} mattes {w}x{h} in {time.time() - t0:.0f} s")


def cmd_mattes(a):
    net = BiRefNet(pick_device(a.device), a.batch)
    src240 = a.src240 or os.environ.get("AMV2_SRC240") or (Path(os.environ["AMV2_DATA"]) / "src240" if os.environ.get("AMV2_DATA") else None)
    for cid in clip_ids(a.clips or ",".join(MATTE_CLIPS)):
        matte_clip(cid, a.out, net, src240, a.scale, a.limit, a.smooth)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("rife240", cmd_rife), ("mattes", cmd_mattes)):
        p = sub.add_parser(name)
        p.add_argument("--clips", help="comma separated clip ids (default: all clips / the six matte clips)")
        p.add_argument("--out", required=True)
        p.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
        p.add_argument("--scale", type=float, default=1.0, help="resolution scale (smoke tests: 0.25)")
        p.add_argument("--limit", type=int, default=0, help="first N source frames (rife240) / output frames (mattes)")
        p.add_argument("--batch", type=int, default=6 if name == "rife240" else 8)
        p.set_defaults(fn=fn)
        if name == "rife240":
            p.add_argument("--no-dedup", action="store_true")
            p.add_argument("--pix-fmt", default="yuv420p")
            p.add_argument("--crf", type=int, default=12)
            p.add_argument("--gop", type=int, default=8)
        else:
            p.add_argument("--src240", help="dir with clip_<ID>.mp4 at 240 fps (default $AMV2_DATA/src240)")
            p.add_argument("--smooth", type=int, default=2, help="temporal smoothing radius in frames (0 = off)")
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
