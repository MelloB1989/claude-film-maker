"""Pixel diff of two stage render folders (renderopt before/after): per frame mean / p99 / max abs difference in 8-bit
levels over premultiplied RGB (straight-alpha RGB under a near-zero alpha is noise), % of pixels off by > 2 and > 8
levels, the alpha's max difference, and the low-pass (16 x 16 box) max difference: noise averages out there, a
systematic change (a shifted edge, a different blur) does not. Optional amplified diff images.

  python blender/amv3/tests/ro_diff.py <dirA>/plate <dirB>/plate [--out diffdir] [--gain 8]
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--out")
    ap.add_argument("--gain", type=float, default=8.0)
    a = ap.parse_args()
    names = sorted(n for n in os.listdir(a.a) if n.endswith(".png") and os.path.exists(os.path.join(a.b, n)))
    if not names:
        sys.exit("no common frames")
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    print(f"{'frame':<14}{'mean':>7}{'p99':>6}{'max':>6}{'>2 %':>8}{'>8 %':>8}{'a max':>7}{'lp max':>8}")
    for n in names:
        x = np.asarray(Image.open(os.path.join(a.a, n)).convert("RGBA"), dtype=np.float32)
        y = np.asarray(Image.open(os.path.join(a.b, n)).convert("RGBA"), dtype=np.float32)
        xp = x[..., :3] * x[..., 3:] / 255.0
        yp = y[..., :3] * y[..., 3:] / 255.0
        d = np.abs(xp - yp).max(axis=2)
        da = np.abs(x[..., 3] - y[..., 3]).max()
        h, w = (d.shape[0] // 16) * 16, (d.shape[1] // 16) * 16
        lp = np.abs((xp - yp)[:h, :w].reshape(h // 16, 16, w // 16, 16, 3).mean(axis=(1, 3))).max()
        print(f"{n:<14}{d.mean():7.3f}{np.percentile(d, 99):6.0f}{d.max():6.0f}{(d > 2).mean() * 100:8.3f}"
              f"{(d > 8).mean() * 100:8.3f}{da:7.0f}{lp:8.2f}")
        if a.out:
            Image.fromarray(np.clip(d * a.gain, 0, 255).astype(np.uint8)).save(os.path.join(a.out, n))


if __name__ == "__main__":
    main()
