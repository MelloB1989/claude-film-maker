"""Stage `polish`: the finishing pass over the rendered frames, after the grade: beat hits and film grain.

Two things the After Effects edit did not have, kept small enough to sit under the grade rather than on top of it:

- Chromatic hits. On every flash beat of the plan (`flash_ev` keys that jump by >= 0.5 EV) the frame splits radially:
  red scaled out and blue scaled in about the centre by `--ca` px at the edge, decaying by e every 1.6 frames. The
  drop and the outro's arrival get it too. Between hits a resting split of `--ca-rest` px keeps the lens feel.
- Grain. Luma noise of `--grain` /255 at mid-grey, falling to 0 at black and white, re-seeded every frame and softened
  by a 0.6 px blur so it reads as film, not as compression noise.

    python -m filmtools.amv.polish --film films/timeless --src out/timeless/amv/frames --out out/timeless/amv/final \
        [--frames a-b] [--ca 7] [--ca-rest 0.8] [--grain 3.2] [--workers 8]

Input and output are `<dir>/<f:04d>.png`; frames missing in --src are skipped with a note.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from . import plan as planmod

cv2.setNumThreads(1)

DECAY = 1.6                 # frames per e-fold of a hit
HIT_JUMP = 0.5              # EV jump in flash_ev that counts as a hit


def hits(plan) -> list[tuple[int, float]]:
    """(frame, strength 0..1) of every beat hit: flash_ev jumps, scaled by their size, plus the drop and the outro."""
    keys = plan.raw.get("flash_ev") or []
    out = []
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f1 == f0 + 1 and v1 - v0 >= HIT_JUMP:
            out.append((int(f1), min(1.0, v1 / 1.8)))
    for p in plan.raw.get("portals") or []:
        out.append((int(p["f0"]), 1.0))
    if plan.raw.get("outro"):
        out.append((int(plan.raw["outro"]["f"]), 0.8))
    best: dict[int, float] = {}
    for f, st in out:                       # one hit per frame (the drop is both a flash and the portal)
        best[f] = max(best.get(f, 0.0), st)
    return sorted(best.items())


def ca_amount(f: int, hit_list, peak: float, rest: float) -> float:
    a = rest
    for fh, s in hit_list:
        if fh <= f < fh + 12:
            a += peak * s * math.exp(-(f - fh) / DECAY)
    return a


def radial_scale(ch: np.ndarray, k: float) -> np.ndarray:
    h, w = ch.shape
    m = np.float32([[k, 0, (1 - k) * w / 2], [0, k, (1 - k) * h / 2]])
    return cv2.warpAffine(ch, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def polish(img: np.ndarray, f: int, ca_px: float, grain: float) -> np.ndarray:
    """img: uint8 RGB (h, w, 3) display values -> the same, polished."""
    x = img.astype(np.float32)
    h, w = x.shape[:2]
    if ca_px > 1e-3:
        k = ca_px * (w / 1920) / (w / 2)          # edge displacement in px -> scale factor
        x[..., 0] = radial_scale(x[..., 0], 1 + k)
        x[..., 2] = radial_scale(x[..., 2], 1 - k)
    if grain > 0:
        rng = np.random.default_rng(1000 + f)
        n = rng.standard_normal((h, w), dtype=np.float32)
        n = cv2.GaussianBlur(n, (0, 0), 0.6) * 2.0   # the blur takes the std from 1 to ~0.5; bring it back
        l = (0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]) / 255
        x += (n * grain * 4 * l * (1 - l))[..., None]
    return np.clip(x + 0.5, 0, 255).astype(np.uint8)


def _job(args):
    src, out, f, ca_px, grain = args
    p = Path(src) / f"{f:04d}.png"
    if not p.is_file():
        return f, False
    img = cv2.imread(str(p), cv2.IMREAD_COLOR)[..., ::-1]
    res = polish(img, f, ca_px, grain)
    cv2.imwrite(str(Path(out) / f"{f:04d}.png"), res[..., ::-1], [cv2.IMWRITE_PNG_COMPRESSION, 1])
    return f, True


def main(argv=None):
    ap = argparse.ArgumentParser(prog="filmtools.amv.polish", description=__doc__.split("\n\n")[0])
    ap.add_argument("--film", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", help="a-b inclusive (default: the whole film)")
    ap.add_argument("--ca", type=float, default=7.0, help="peak red/blue split at the frame edge, px at 1920 wide")
    ap.add_argument("--ca-rest", type=float, default=0.8)
    ap.add_argument("--grain", type=float, default=3.2, help="grain std at mid-grey, /255")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    a = ap.parse_args(argv)
    plan = planmod.load(Path(a.film))
    lo, hi = (map(int, a.frames.split("-")) if a.frames else (0, plan.dur - 1))
    hl = hits(plan)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    jobs = [(a.src, a.out, f, ca_amount(f, hl, a.ca, a.ca_rest), a.grain) for f in range(lo, hi + 1)]
    missing = []
    with ProcessPoolExecutor(a.workers) as ex:
        for f, ok in ex.map(_job, jobs, chunksize=4):
            if not ok:
                missing.append(f)
    done = len(jobs) - len(missing)
    print(f"polished {done} frames -> {a.out}" + (f"; missing in src: {missing[:8]}{'...' if len(missing) > 8 else ''}"
                                                  if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
