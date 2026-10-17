"""Stand-in layer frames for testing the AMV scene before the bake stage exists (needs numpy + opencv, not Blender).

Per shot it writes what `tools/filmtools/amv/bake.py` will: `<out>/<shot>/<f:04d>.png` (RGBA, the canvas of `Shot.canvas`
scaled by --scale) and `<out>/<shot>/canvas.json` ({w, h, ox, oy} at 1080p). The picture is the nearest 60p clip frame
of `Shot.remap(f) * 60`, mirror-padded to the canvas (cv2 BORDER_REFLECT = AE's Motion Tile mirror), and the eye-dive
`hole` is cut as a feathered ellipse of alpha. No retime, balance, titles, rim, blur or lens effects: geometry only.

    python3 blender/tests/amv_scene_standin.py --film films/timeless --out /tmp/amv/layers --shots T01_mask_night,...
    python3 blender/tests/amv_scene_standin.py --film films/timeless --out /tmp/amv/layers --frames 240-260,480-500
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from filmtools.amv import plan as amv_plan  # noqa: E402


def parse_frames(spec):
    out = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return sorted(out)


def hole_alpha(shot, f, w, h, ox, oy, scale):
    """Alpha (h*scale, w*scale) of the canvas with the eye-dive hole cut out, or None when the shot has none."""
    hole = shot.hole(f)
    if hole is None:
        return None
    cx, cy, rx, ry, feather, exp = hole
    ys, xs = np.mgrid[0:int(round(h * scale)), 0:int(round(w * scale))].astype(np.float32)
    x = (xs + 0.5) / scale - ox - cx
    y = (ys + 0.5) / scale - oy - cy
    rr = np.sqrt((x / max(rx + exp, 1e-3)) ** 2 + (y / max(ry + exp, 1e-3)) ** 2)
    d = (rr - 1.0) * max(rx + exp, 1e-3)  # px outside the ellipse edge (roughly)
    return np.clip(0.5 + d / max(feather, 1.0), 0.0, 1.0)


def make(plan, shot, frames, out, scale, clip_dir):
    w, h, ox, oy = shot.canvas
    folder = out / shot.name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "canvas.json").write_text(json.dumps({"w": w, "h": h, "ox": ox, "oy": oy}))
    cap = cv2.VideoCapture(str(clip_dir / (shot.src + ".mp4")))
    if not cap.isOpened():
        raise SystemExit(f"cannot open the clip of {shot.name}: {clip_dir / (shot.src + '.mp4')}")
    cw, ch = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for f in frames:
        i = min(max(int(round(shot.remap(f) * 60.0)), 0), n - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, img = cap.read()
        if not ok:
            raise SystemExit(f"{shot.name}: cannot read clip frame {i}")
        img = cv2.resize(img, (amv_plan.W, amv_plan.H), interpolation=cv2.INTER_AREA) if (cw, ch) != (amv_plan.W, amv_plan.H) else img
        if shot.raw.get("flipx"):
            img = img[:, ::-1]
        img = cv2.copyMakeBorder(img, oy, h - amv_plan.H - oy, ox, w - amv_plan.W - ox, cv2.BORDER_REFLECT)
        size = (int(round(w * scale)), int(round(h * scale)))
        img = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
        a = hole_alpha(shot, f, w, h, ox, oy, scale)
        alpha = np.full(img.shape[:2], 255, np.uint8) if a is None else (a * 255).astype(np.uint8)
        cv2.imwrite(str(folder / f"{f:04d}.png"), np.dstack([img, alpha]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--film", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shots", help="comma-separated shot names (default: those visible in --frames)")
    ap.add_argument("--frames", help="comma list of a-b comp frames: write each listed shot's frames within them")
    ap.add_argument("--scale", type=float, default=0.25)
    ap.add_argument("--clips", help="clip folder (default <film>/assets/clips)")
    a = ap.parse_args(argv)
    film = Path(a.film)
    plan = amv_plan.load(film)
    clip_dir = Path(a.clips) if a.clips else film / "assets" / "clips"
    want = parse_frames(a.frames) if a.frames else None
    names = a.shots.split(",") if a.shots else None
    # a plane is keyed one frame either side of its range (motion blur): write those too
    for shot in plan.shots:
        frames = [f for f in range(shot.a - 1, shot.end + 1) if 0 <= f < plan.dur]
        if want is not None:
            wanted = set(want)
            frames = [f for f in frames if f in wanted or f + 1 in wanted or f - 1 in wanted]
            if names is None and not frames:
                continue
        if names is not None and shot.name not in names:
            continue
        if want is not None and not frames:
            continue
        make(plan, shot, [f for f in frames if shot.a <= f < shot.end], Path(a.out), a.scale, clip_dir)
        print(f"{shot.name}: {len(frames)} frames", flush=True)


if __name__ == "__main__":
    main()
