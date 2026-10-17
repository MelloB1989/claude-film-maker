"""Stage `retime`: what each shot's layer shows at every comp frame.

After Effects rendered a shot as a time-remapped precomp (frame blending on `slow` shots) sampled by the main comp's
motion blur (301 deg shutter, phase -150 deg), so every output frame integrates the clip over the shutter. This
reproduces that: for comp frame f take `plan.shutter_times(f, K)`, map each time through `Shot.remap` to a clip frame
position p = seconds * clip fps, synthesise the clip image at fractional p, and average the K images in linear light.

Scene cuts inside a clip (hard cuts of the source footage, `detect_cuts`) are never crossed: a comp frame whose shutter
samples straddle one uses only the samples in the scene of the frame's centre time, and no blend or interpolation
spans the cut.

Modes (how the image at p is made):
- `auto`     the default, as AE did: `--slow-mode` (flow) on `slow` shots, `nearest` on all others.
- `nearest`  K = 1, frame floor(p) at the centre of the shutter: one source frame per comp frame.
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

MODES = ("nearest", "mix", "flow", "rife", "auto")
CUT_MIN_DIFF = 20.0             # mean abs luma step (0..255, on a 1/8 sub-sampled frame) a scene cut must exceed
CUT_RATIO = 3.0                 # ... and exceed this multiple of the typical step between distinct frames around it
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


def split_position(p, n, cuts=()):
    """(i, frac) with frames i, i+1 the neighbours of position p; frac is 0 at the clip's ends and in front of a scene
    cut (`cuts` = first frame of every scene after the first): never a blend of two scenes."""
    p, _ = clamp_position(p, n)
    i = int(math.floor(p + 1e-6))
    if i >= n - 1:
        return n - 1, 0.0
    if i + 1 in cuts:
        return i, 0.0
    frac = p - i
    return i, (0.0 if frac < 1e-6 else frac)


def scene_index(p, n, cuts=()):
    """Which scene (0 = before the first cut) of the clip the position p falls in."""
    i, _ = split_position(p, n)
    return sum(1 for c in cuts if c <= i)


def keep_scene(ps, pc, n, cuts=()):
    """The shutter sub-sample positions `ps` that lie in the same scene as the frame's centre position `pc`: samples
    across a source cut belong to another shot of the original footage and are dropped, not blended in."""
    if not cuts:
        return list(ps)
    sc = scene_index(pc, n, cuts)
    return [p for p in ps if scene_index(p, n, cuts) == sc] or [pc]


def mix_weights(ps, n, cuts=()):
    """AE Frame Mix of the shutter samples as source-frame weights {frame index: weight}, summing to 1."""
    w: dict[int, float] = {}
    for p in ps:
        i, fr = split_position(p, n, cuts)
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


_fcache: dict = {}


def float_frame(frames, i):
    """Frame i as float32 sRGB-encoded 0..1, the same array object on repeat calls (interpolators cache by identity)."""
    k = (id(frames), i)
    if k not in _fcache:
        if len(_fcache) >= 8:
            _fcache.pop(next(iter(_fcache)))
        _fcache[k] = srgb_f(frames[i])
    return _fcache[k]


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


def detect_cuts(frames, min_diff=CUT_MIN_DIFF, ratio=CUT_RATIO):
    """First frame index of every scene after the first in a decoded clip (hard cuts of the source footage).

    A cut is a step between consecutive frames that is both large in absolute terms and much larger than the typical
    step between the distinct frames around it, so fast motion (and clips that repeat frames, whose real steps are all
    big) does not count. Steps under 1.5 are repeated frames and are ignored when judging 'typical'."""
    n = len(frames)
    if n < 2:
        return []
    g = np.asarray(frames[:, ::8, ::8], dtype=np.float32).mean(axis=3)
    d = np.abs(g[1:] - g[:-1]).mean(axis=(1, 2))            # d[j]: frame j -> j + 1
    cuts = []
    for j in range(n - 1):
        if d[j] < min_diff:
            continue
        near = [d[m] for m in range(max(0, j - 8), min(n - 1, j + 9)) if m != j and d[m] >= 1.5]
        ref = float(np.median(near)) if near else 0.0
        if d[j] >= ratio * max(ref, 1.0):
            cuts.append(j + 1)
    return cuts


# ---------------------------------------------------------------- rendering

@dataclass
class FrameInfo:
    k: int
    times: list           # clip seconds of the sub-samples
    held: bool            # a sample ran past the last frame
    cut: bool = False     # samples on the other side of a source scene cut were dropped


def centre_position(shot, f, fps=60.0):
    """Clip frame position at the centre of comp frame `f`'s shutter."""
    return shot.remap(f + (planmod.SHUTTER_PHASE + planmod.SHUTTER_ANGLE / 2) / 360.0) * fps


def render_frame(frames, shot, f, mode, k, interp=None, fps=60.0, cuts=()):
    """(uint8 RGB image, FrameInfo) of `shot`'s layer at comp frame `f`. `frames` is the decoded clip, `cuts` its scene
    cuts (`detect_cuts`): sub-samples on the far side of a cut from the frame's centre are dropped, never blended."""
    n = len(frames)
    k = 1 if mode == "nearest" else k
    ps = source_positions(shot, f, k, fps)
    held = any(clamp_position(p, n)[1] for p in ps)
    kept = keep_scene(ps, centre_position(shot, f, fps), n, cuts)
    info = FrameInfo(len(kept), [round(p / fps, 6) for p in kept], held, len(kept) != len(ps))
    ps = kept
    if mode == "nearest":
        i, _ = split_position(math.floor(ps[0] + 1e-6), n)
        return frames[i].copy(), info
    acc = None
    if mode == "mix":
        for i, w in mix_weights(ps, n, cuts).items():
            lin = to_linear(frames[i]) * np.float32(w)
            acc = lin if acc is None else acc + lin
    else:
        groups: dict[int, list] = {}
        for p in ps:                                     # group the samples by source pair, one interpolator call each
            i, fr = split_position(p, n, cuts)
            groups.setdefault(i, []).append(fr)
        for i, frs in groups.items():
            exact = [fr for fr in frs if fr == 0.0]
            mids = [fr for fr in frs if fr > 0.0]
            parts = [linear_f(float_frame(frames, i))] * len(exact)
            if mids:
                a, b = float_frame(frames, i), float_frame(frames, i + 1)
                parts += [linear_f(x) for x in interp.between(a, b, mids)]
            for lin in parts:
                lin = lin / np.float32(len(ps))
                acc = lin if acc is None else acc + lin
    return to_srgb8(acc), info


def parse_range(s):
    a, _, b = s.partition("-")
    return int(a), int(b or a)


def resolve_mode(shot, mode, slow_mode="flow"):
    """`auto` is AE's behaviour: frame blending (interpolation) only on `slow` shots; every other shot shows one source
    frame per comp frame (the main comp's motion blur blurs the transform, it does not integrate the footage)."""
    if mode == "auto":
        return slow_mode if shot.slow else "nearest"
    return mode


def retime_shot(plan, shot, out_root, mode="mix", samples=None, scale=1.0, frames=None, interp=None, log=print,
                slow_mode="flow"):
    """Render `shot`'s frames (all of `Shot.frames()`, or those inside `frames` = (a, b) inclusive) to
    <out_root>/<shot>/<f:04d>.png and write retime.json. Returns the list of comp frames that held the last frame."""
    import cv2
    clip = plan.clip(shot)
    _, _, fps, _ = probe(clip)
    if abs(fps - 60.0) > 1e-3:
        log(f"warning: {clip.name} is {fps} fps, not 60 (positions use {fps})")
    mode = resolve_mode(shot, mode, slow_mode)
    interp = interp or _make_interp(mode)
    dec = decode_clip(clip, scale)
    cuts = detect_cuts(dec)
    if cuts:
        log(f"{shot.name}: source scene cut(s) at clip frame {cuts}: samples never mixed across them")
    out = Path(out_root) / shot.name
    out.mkdir(parents=True, exist_ok=True)
    meta_path = out / "retime.json"
    prev = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
    per = prev.get("frames", {}) if prev.get("mode") == mode else {}
    held = []
    todo = [f for f in shot.frames() if frames is None or frames[0] <= f <= frames[1]]
    for f in todo:
        k = samples or auto_samples(shot, f, fps)
        img, info = render_frame(dec, shot, f, mode, k, interp, fps, cuts)
        cv2.imwrite(str(out / f"{f:04d}.png"), img[..., ::-1], [cv2.IMWRITE_PNG_COMPRESSION, 1])
        per[str(f)] = {"k": info.k, "times": info.times, **({"held": True} if info.held else {}),
                        **({"cut": True} if info.cut else {})}
        if info.held:
            held.append(f)
    meta_path.write_text(json.dumps({"mode": mode, "samples": samples or "auto", "scale": scale, "clip": clip.name,
                                     "clip_fps": fps, "clip_frames": len(dec), "cuts": cuts, "frames": per}, indent=1))
    if held:
        log(f"warning: {shot.name}: clip time past its last frame ({len(dec)} frames), held: comp frames {held[0]}-{held[-1]}")
    return held


def _job(args):
    film, name, kw = args
    plan = planmod.load(film)
    return name, retime_shot(plan, plan.shot(name), **kw)


_interps: dict = {}


def _make_interp(mode):
    if mode in ("flow", "rife"):
        if mode not in _interps:
            from . import interp
            _interps[mode] = interp.make(mode)
        return _interps[mode]
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="filmtools.amv.retime", description=__doc__.split("\n\n")[0])
    ap.add_argument("--film", required=True, help="film folder (films/<id>)")
    ap.add_argument("--shots", help="comma-separated shot names (default: all)")
    ap.add_argument("--frames", help="comp frame range a-b, inclusive (default: every frame of each shot)")
    ap.add_argument("--mode", choices=MODES, default="auto",
                    help="auto (default): --slow-mode on `slow` shots, nearest source frame on the others, as AE did")
    ap.add_argument("--slow-mode", choices=("mix", "flow", "rife"), default="flow", help="mode of `slow` shots under auto")
    ap.add_argument("--list-cuts", action="store_true", help="only list the source scene cuts of every clip and exit")
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
    if a.list_cuts:
        for n in names:
            clip = plan.clip(plan.shot(n))
            print(f"{clip.name}: {detect_cuts(decode_clip(clip, 0.25))}", flush=True)
        return 0
    kw = dict(out_root=out, mode=a.mode, slow_mode=a.slow_mode, samples=a.samples, scale=a.scale,
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
        for n in names:
            h = retime_shot(plan, plan.shot(n), **kw)
            print(f"{n}: done", flush=True)
            if h:
                held[n] = h
    if held:
        print("WARNING clip time past the last frame (last frame held): "
              + ", ".join(f"{n} ({h[0]}-{h[-1]})" for n, h in held.items()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
