"""Stage `retime`: what each shot's layer shows at every comp frame.

After Effects rendered a shot as a time-remapped precomp (frame blending on `slow` shots) sampled by the main comp's
motion blur (301 deg shutter, phase -150 deg), so every output frame integrates the clip over the shutter. This
reproduces that: for comp frame f take `plan.shutter_times(f, K)`, map each time through `Shot.remap` to a clip frame
position p = seconds * clip fps, synthesise the clip image at fractional p, and average the K images in linear light.

Modes (how the image at p is made):
- `nearest`  K = 1, frame floor(p): the draft.
- `mix`      AE Frame Mix: linear cross-blend of frames floor(p) and floor(p) + 1 by frac(p).
- `flow`     optical-flow interpolation (OpenCV DIS, CPU): the open-source stand-in for Twixtor (interp/flow.py).
- `rife`     RIFE v4.x neural interpolation, CUDA when available (interp/rife.py).

K is picked per frame so consecutive sub-samples sit <= ~0.25 source frames apart (fast shots cover ~2 source frames
per comp frame, slow ones ~0.8), clamped to 2..16; `--samples` overrides. Clips are decoded once per shot (ffmpeg
pipe, BT.709 limited range -> full range sRGB RGB) and a clip time past the last frame holds the last frame.

    python -m filmtools.amv.retime --film films/timeless [--shots A,B] [--frames a-b] [--mode mix] [--scale 0.5]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import plan as planmod

MODES = ("nearest", "mix", "flow", "rife")
MAX_STEP = 0.25                 # source frames between consecutive shutter sub-samples
K_MIN, K_MAX = 2, 16
FFMPEG_FALLBACK = "/home/nikhil/code/film-making/bin"


# ---------------------------------------------------------------- time mapping (pure)

def source_positions(shot, f, k, fps=60.0):
    """Clip frame positions p (fractional, unclamped) of the `k` shutter sub-samples of comp frame `f`."""
    return [shot.remap(t) * fps for t in planmod.shutter_times(f, k)]


def auto_samples(shot, f, fps=60.0):
    """K so that the sub-samples are at most MAX_STEP source frames apart over the shutter, clamped to K_MIN..K_MAX."""
    t0 = f + planmod.SHUTTER_PHASE / 360.0
    t1 = t0 + planmod.SHUTTER_ANGLE / 360.0
    pts = [shot.remap(t0 + (t1 - t0) * i / 8) * fps for i in range(9)]
    span = sum(abs(b - a) for a, b in zip(pts, pts[1:]))
    return max(K_MIN, min(K_MAX, math.ceil(span / MAX_STEP - 1e-9)))


def clamp_position(p, n):
    """p held inside the clip: (clamped p, True when it ran past the last frame)."""
    last = n - 1
    return (min(max(p, 0.0), float(last)), p > last + 1e-6)


def split_position(p, n):
    """(i, frac) with frames i, i+1 the neighbours of position p; frac is 0 at the clip's ends."""
    p, _ = clamp_position(p, n)
    i = int(math.floor(p + 1e-6))
    if i >= n - 1:
        return n - 1, 0.0
    frac = p - i
    return i, (0.0 if frac < 1e-6 else frac)


def mix_weights(ps, n):
    """AE Frame Mix of the shutter samples as source-frame weights {frame index: weight}, summing to 1."""
    w: dict[int, float] = {}
    for p in ps:
        i, fr = split_position(p, n)
        w[i] = w.get(i, 0.0) + (1.0 - fr) / len(ps)
        if fr > 0.0:
            w[i + 1] = w.get(i + 1, 0.0) + fr / len(ps)
    return w


# ---------------------------------------------------------------- sRGB <-> linear

_SRGB = np.arange(256, dtype=np.float32) / 255.0
LIN_LUT = np.where(_SRGB <= 0.04045, _SRGB / 12.92, ((_SRGB + 0.055) / 1.055) ** 2.4).astype(np.float32)
_ENC_N = 16384
_x = np.arange(_ENC_N + 1, dtype=np.float32) / _ENC_N
ENC_LUT = np.clip(np.rint(255.0 * np.where(_x <= 0.0031308, 12.92 * _x, 1.055 * _x ** (1 / 2.4) - 0.055)), 0, 255).astype(np.uint8)


def to_linear(u8):
    return LIN_LUT[u8]


def to_srgb8(lin):
    return ENC_LUT[(np.clip(lin, 0.0, 1.0) * _ENC_N + 0.5).astype(np.int32)]


def srgb_f(u8):
    return u8.astype(np.float32) * (1.0 / 255.0)


def linear_f(img):
    """Linear light of a float32 sRGB-encoded 0..1 image (interpolator output)."""
    img = np.clip(img, 0.0, 1.0)
    return np.where(img <= 0.04045, img / 12.92, ((img + 0.055) / 1.055) ** 2.4).astype(np.float32)


# ---------------------------------------------------------------- clips

def ffmpeg_bin(name="ffmpeg"):
    for d in (os.environ.get("FILM_BIN"), FFMPEG_FALLBACK):
        if d and (Path(d) / name).is_file():
            return str(Path(d) / name)
    return shutil.which(name) or name


def probe(path):
    """(width, height, fps, frames) of the first video stream."""
    out = subprocess.run([ffmpeg_bin("ffprobe"), "-v", "error", "-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames", "-of", "json", str(path)],
                         check=True, capture_output=True, text=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den), int(s["nb_read_frames"])


def decode_clip(path, scale=1.0):
    """All frames of the clip as a uint8 array (n, h, w, 3) RGB, scaled by `scale` (area filter)."""
    w, h, _, _ = probe(path)
    ow, oh = max(2, int(round(w * scale / 2)) * 2), max(2, int(round(h * scale / 2)) * 2)
    vf = f"scale={ow}:{oh}:in_range=tv:in_color_matrix=bt709:out_range=pc:flags=area+accurate_rnd+full_chroma_int,format=rgb24"
    p = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(path), "-fps_mode", "passthrough", "-vf", vf,
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True)
    return np.frombuffer(p.stdout, np.uint8).reshape(-1, oh, ow, 3)


# ---------------------------------------------------------------- rendering

@dataclass
class FrameInfo:
    k: int
    times: list           # clip seconds of the sub-samples
    held: bool            # a sample ran past the last frame


def render_frame(frames, shot, f, mode, k, interp=None, fps=60.0):
    """(uint8 RGB image, FrameInfo) of `shot`'s layer at comp frame `f`. `frames` is the decoded clip."""
    n = len(frames)
    k = 1 if mode == "nearest" else k
    ps = source_positions(shot, f, k, fps)
    held = any(clamp_position(p, n)[1] for p in ps)
    info = FrameInfo(k, [round(p / fps, 6) for p in ps], held)
    if mode == "nearest":
        i, _ = split_position(math.floor(ps[0] + 1e-6), n)
        return frames[i].copy(), info
    acc = None
    if mode == "mix":
        for i, w in mix_weights(ps, n).items():
            lin = to_linear(frames[i]) * np.float32(w)
            acc = lin if acc is None else acc + lin
    else:
        groups: dict[int, list] = {}
        for p in ps:                                     # group the samples by source pair, one interpolator call each
            i, fr = split_position(p, n)
            groups.setdefault(i, []).append(fr)
        for i, frs in groups.items():
            exact = [fr for fr in frs if fr == 0.0]
            mids = [fr for fr in frs if fr > 0.0]
            parts = [linear_f(srgb_f(frames[i]))] * len(exact)
            if mids:
                a, b = srgb_f(frames[i]), srgb_f(frames[i + 1])
                parts += [linear_f(x) for x in interp.between(a, b, mids)]
            for lin in parts:
                lin = lin / np.float32(len(ps))
                acc = lin if acc is None else acc + lin
    return to_srgb8(acc), info


def parse_range(s):
    a, _, b = s.partition("-")
    return int(a), int(b or a)


def retime_shot(plan, shot, out_root, mode="mix", samples=None, scale=1.0, frames=None, interp=None, log=print):
    """Render `shot`'s frames (all of `Shot.frames()`, or those inside `frames` = (a, b) inclusive) to
    <out_root>/<shot>/<f:04d>.png and write retime.json. Returns the list of comp frames that held the last frame."""
    import cv2
    clip = plan.clip(shot)
    _, _, fps, _ = probe(clip)
    if abs(fps - 60.0) > 1e-3:
        log(f"warning: {clip.name} is {fps} fps, not 60 (positions use {fps})")
    dec = decode_clip(clip, scale)
    out = Path(out_root) / shot.name
    out.mkdir(parents=True, exist_ok=True)
    meta_path = out / "retime.json"
    prev = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
    per = prev.get("frames", {}) if prev.get("mode") == mode else {}
    held = []
    todo = [f for f in shot.frames() if frames is None or frames[0] <= f <= frames[1]]
    for f in todo:
        k = samples or auto_samples(shot, f, fps)
        img, info = render_frame(dec, shot, f, mode, k, interp, fps)
        cv2.imwrite(str(out / f"{f:04d}.png"), img[..., ::-1], [cv2.IMWRITE_PNG_COMPRESSION, 1])
        per[str(f)] = {"k": info.k, "times": info.times, **({"held": True} if info.held else {})}
        if info.held:
            held.append(f)
    meta_path.write_text(json.dumps({"mode": mode, "samples": samples or "auto", "scale": scale, "clip": clip.name,
                                     "clip_fps": fps, "clip_frames": len(dec), "frames": per}, indent=1))
    if held:
        log(f"warning: {shot.name}: clip time past its last frame ({len(dec)} frames), held: comp frames {held[0]}-{held[-1]}")
    return held


def _job(args):
    film, name, kw = args
    plan = planmod.load(film)
    return name, retime_shot(plan, plan.shot(name), interp=_make_interp(kw["mode"]), **kw)


def _make_interp(mode):
    if mode in ("flow", "rife"):
        from . import interp
        return interp.make(mode)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="filmtools.amv.retime", description=__doc__.split("\n\n")[0])
    ap.add_argument("--film", required=True, help="film folder (films/<id>)")
    ap.add_argument("--shots", help="comma-separated shot names (default: all)")
    ap.add_argument("--frames", help="comp frame range a-b, inclusive (default: every frame of each shot)")
    ap.add_argument("--mode", choices=MODES, default="mix")
    ap.add_argument("--samples", type=int, help="shutter samples K per frame (default: auto, 2..16)")
    ap.add_argument("--scale", type=float, default=1.0, help="output size factor (0.5 = 960x540)")
    ap.add_argument("--out", help="output root (default out/<id>/amv/src under the repo root)")
    ap.add_argument("--jobs", type=int, default=1, help="shots in parallel (CPU modes)")
    a = ap.parse_args(argv)

    film = Path(a.film).resolve()
    plan = planmod.load(film)
    out = Path(a.out) if a.out else film.parents[1] / "out" / film.name / "amv" / "src"
    names = a.shots.split(",") if a.shots else [s.name for s in plan.shots]
    for n in names:
        plan.shot(n)                                     # fail early on a typo
    kw = dict(out_root=out, mode=a.mode, samples=a.samples, scale=a.scale,
              frames=parse_range(a.frames) if a.frames else None)
    held = {}
    if a.jobs > 1 and a.mode != "rife":
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(a.jobs) as ex:
            for name, h in ex.map(_job, [(film, n, kw) for n in names]):
                print(f"{name}: done", flush=True)
                if h:
                    held[name] = h
    else:
        interp = _make_interp(a.mode)
        for n in names:
            h = retime_shot(plan, plan.shot(n), interp=interp, **kw)
            print(f"{n}: done", flush=True)
            if h:
                held[n] = h
    if held:
        print("WARNING clip time past the last frame (last frame held): "
              + ", ".join(f"{n} ({h[0]}-{h[-1]})" for n, h in held.items()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
