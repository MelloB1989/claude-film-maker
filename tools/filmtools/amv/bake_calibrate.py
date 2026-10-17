"""Calibrate / audit the baked layers against the After Effects reference render.

The reference (`rendered_f0-599_full_quality.mp4`) has the grade, the shutter blur and the stacking on top, so it cannot
be compared pixel for pixel. What survives all that is *geometry*: where edges and streaks lie. So:

  - `screen_view` puts a baked canvas on the screen with `Shot.matrix(f)` (averaged over the plan's shutter, like AE's
    motion blur) over black: what the Blender scene would show for that shot alone;
  - `edge_score` is the normalised correlation of the two pictures' gradient magnitudes (luma, lightly blurred), blind
    to colour grade and exposure;
  - `sheet` writes a side-by-side JPG, ours | reference | abs difference of the normalised luma.

    python -m filmtools.amv.bake_calibrate --film films/timeless --cases T01_mask_night:31-35 --layers /tmp/layers --ref /tmp/ref
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from . import bake, plan as planmod


def screen_view(plan, shot, f, canvas, scale, mb=8):
    """The baked `canvas` (float RGBA, from `bake_frame(.., scale)`) on a W*scale x H*scale screen, as RGB over black."""
    cw, ch, ox, oy = bake.scaled_canvas(shot, scale)
    lw, lh = bake.layer_size(scale)
    pm = np.ascontiguousarray(canvas.copy())
    pm[..., :3] *= pm[..., 3:4]
    acc = np.zeros((lh, lw, 4), np.float32)
    times = planmod.shutter_times(f, mb) if mb > 1 else [float(f)]
    for t in times:
        A = np.array(planmod.affine(*(_transform(shot, t))), np.float64)
        lin, off = A[:, :2], A[:, 2]
        # canvas px c -> layer (c - o) / s -> screen A . layer + off -> screen px at `scale`: A (c - o) + s off
        b = -lin @ np.array([ox, oy]) + scale * off
        # continuous -> cv2 integer-centre convention
        b_cv = b + lin @ np.array([0.5, 0.5]) - 0.5
        m = np.hstack([lin, b_cv[:, None]])
        acc += cv2.warpAffine(pm, m, (lw, lh), flags=cv2.INTER_LINEAR, borderValue=0)
    return np.clip(acc[..., :3] / len(times), 0, 1)


def _transform(shot, t):
    j = t - shot.a
    return (planmod.per_frame(shot.raw["px"], j), planmod.per_frame(shot.raw["py"], j),
            planmod.per_frame(shot.raw["s"], j), planmod.per_frame(shot.raw["rz"], j))


def ref_frame(ref_dir, f, scale):
    """The AE reference frame `f` as float RGB at W*scale x H*scale."""
    im = cv2.imread(str(Path(ref_dir) / f"{f:04d}.jpg"))
    im = im[..., ::-1].astype(np.float32) / 255.0
    lw, lh = bake.layer_size(scale)
    return cv2.resize(im, (lw, lh), interpolation=cv2.INTER_AREA) if scale != 1 else im


def _grad(rgb, blur=1.5):
    g = cv2.GaussianBlur(rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32), (0, 0), blur)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    return np.sqrt(gx * gx + gy * gy)


def edge_score(a, b):
    """Normalised correlation of gradient magnitudes, 1 = same edges (grade and exposure do not matter)."""
    ga, gb = _grad(a), _grad(b)
    ga, gb = ga - ga.mean(), gb - gb.mean()
    return float((ga * gb).sum() / (np.sqrt((ga * ga).sum() * (gb * gb).sum()) + 1e-9))


def luma_ncc(a, b):
    """Normalised correlation of the luma images (brightness/contrast invariant)."""
    la, lb = (x @ np.array([0.2126, 0.7152, 0.0722], np.float32) for x in (a, b))
    la, lb = la - la.mean(), lb - lb.mean()
    return float((la * lb).sum() / (np.sqrt((la * la).sum() * (lb * lb).sum()) + 1e-9))


def sheet(ours, ref, path, label=""):
    """ours | reference | |difference| of the mean/std-normalised luma, as one JPG."""
    def norm(x):
        l = x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        return (l - l.mean()) / (l.std() + 1e-6)
    d = np.abs(norm(ours) - norm(ref))
    d = np.repeat(np.clip(d / 3.0, 0, 1)[..., None], 3, axis=2)
    row = np.concatenate([ours, ref, d], axis=1)
    img = (np.clip(row, 0, 1) * 255).astype(np.uint8)[..., ::-1].copy()
    cv2.putText(img, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", required=True)
    ap.add_argument("--cases", required=True, help="shot:a-b[,shot:a-b...]  comp frames to bake and compare")
    ap.add_argument("--ref", required=True, help="dir of reference frames NNNN.jpg (ffmpeg -q:v 1 -start_number 0)")
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--src", default=None)
    ap.add_argument("--out", default="/tmp/amv_calib")
    ap.add_argument("--mb", type=int, default=8)
    args = ap.parse_args(argv)
    plan = planmod.load(args.film)
    rows = []
    for case in args.cases.split(","):
        name, _, rng = case.partition(":")
        shot = bake.select_shots(plan, name)[0]
        a, b = bake.parse_frames(rng)
        for f in range(a, b + 1):
            canvas = bake.bake_frame(plan, shot, f, args.scale, args.src, None, None)
            ours = screen_view(plan, shot, f, canvas, args.scale, args.mb)
            ref = ref_frame(args.ref, f, args.scale)
            e, n = edge_score(ours, ref), luma_ncc(ours, ref)
            sheet(ours, ref, Path(args.out) / f"{shot.name}_{f:04d}.jpg", f"{shot.name} f{f}  edge {e:.3f}  ncc {n:.3f}")
            rows.append({"shot": shot.name, "f": f, "edge": round(e, 4), "ncc": round(n, 4)})
            print(rows[-1], flush=True)
    (Path(args.out) / "scores.json").write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
