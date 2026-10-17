"""Composite the Blender elements (blender/amv2/elements.py) over real footage frames and write check images.

    python tools/filmtools/amv2/test_elements.py --element rift --frames 244,248,252,256 --src out/q1/frames --out out/q1/comp
        [--mode normal|add] [--alpha premul|straight] [--bg checker]

Needs ffmpeg, numpy and cv2 (the render VM's python has them). Elements are premultiplied PNGs by default.
Backdrops (the real clips, mapped like edl.py's shots): rift = S08 T08_eye_dive push into the left iris (f < 252) then S09
A01_lens_pullout; shockwave = S18 M01_lens_portal; timeless3d = the three triptych panels side by side.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

CLIPS = Path("/home/nikhil/code/film-making/handover/amv_handover/footage_clips")


def grab(clip, t, cache):
    p = cache / f"{clip}_{t:.3f}.png"
    if not p.exists():
        cache.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(CLIPS / f"clip_{clip}.mp4"),
                        "-frames:v", "1", str(p)], check=True)
    im = cv2.imread(str(p))
    if im.shape[:2] != (1080, 1920):
        im = cv2.resize(im, (1920, 1080), interpolation=cv2.INTER_AREA)
    return im


def scale_about(im, pct, focus):
    s = pct / 100.0
    m = np.float32([[s, 0, focus[0] * (1 - s)], [0, s, focus[1] * (1 - s)]])
    return cv2.warpAffine(im, m, (1920, 1080), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def backdrop(element, f, cache):
    if element == "rift":
        if f < 252:   # S08: src 0.05 -> 0.75 over 235-252, drift 100 -> 160 % about the iris
            u = (f - 235) / 17.0
            return scale_about(grab("T08_eye_dive", 0.05 + 0.70 * u, cache), 100 + 60 * u, (901, 390))
        u = min(1.0, (f - 252) / 48.0)    # S09: A01 played backwards from 4.45 s, landing
        return grab("A01_lens_pullout", 4.45 - 4.05 * (1 - (1 - u) ** 2) - 0.0, cache)
    if element == "shockwave":
        u = (f - 480) / 39.0
        return grab("M01_lens_portal", 0.02 + 1.10 * (1 - (1 - u) ** 2), cache)
    # timeless3d: three panels side by side, each a 640x1080 crop (the real layout is the triptych's job)
    panels = [("T01_mask_night", 0.7), ("A03_sunset_mask", 0.35), ("M16_sunset_hero", 0.5)]
    out = np.zeros((1080, 1920, 3), np.uint8)
    for i, (c, t) in enumerate(panels):
        im = grab(c, t, cache)
        out[:, i * 640:(i + 1) * 640] = im[:, 640:1280]
    for i in (1, 2):
        out[:, i * 640 - 3:i * 640 + 3] = 255
    return out


def checker():
    y, x = np.mgrid[0:1080, 0:1920]
    c = (((x // 40) + (y // 40)) % 2) * 40 + 60
    return np.dstack([c, c, c]).astype(np.uint8)


def composite(fg, bg, mode, alpha):
    f = fg.astype(np.float32) / 255.0
    b = bg.astype(np.float32) / 255.0
    rgb, a = f[..., 2::-1], f[..., 3:4]        # cv2 loads BGRA; make rgb order irrelevant by keeping BGR order
    rgb = f[..., :3]
    if mode == "add":
        premul = rgb if alpha == "premul" else rgb * a
        out = b + premul
    else:
        premul = rgb if alpha == "premul" else rgb * a
        out = premul + b * (1 - a)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--element", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="normal")
    ap.add_argument("--alpha", default="premul")
    ap.add_argument("--bg", default="footage")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "_bg"
    for f in [int(x) for x in a.frames.split(",")]:
        fg = cv2.imread(str(Path(a.src) / a.element / f"{f:04d}.png"), cv2.IMREAD_UNCHANGED)
        if fg.shape[:2] != (1080, 1920):
            fg = cv2.resize(fg, (1920, 1080), interpolation=cv2.INTER_CUBIC)
        if fg.shape[2] == 3:
            fg = np.dstack([fg, np.full(fg.shape[:2], 255, fg.dtype)])
        bg = checker() if a.bg == "checker" else backdrop(a.element, f, cache)
        mode = a.mode
        cv2.imwrite(str(out / f"{a.element}_{f:04d}_comp.png"), composite(fg, bg, mode, a.alpha))
        print("wrote", out / f"{a.element}_{f:04d}_comp.png")


if __name__ == "__main__":
    sys.exit(main())
