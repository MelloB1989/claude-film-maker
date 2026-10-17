"""Audit the baked layer effects against the After Effects render by *brightness*, through the grade.

`bake_calibrate.py` compares geometry (edges). The two effects that move luma, CC Radial Fast Blur in Brightest mode
(a max along the ray: highlights spread and dominate) and Directional Blur (a box average), cannot be checked by
edges, so this tool runs the whole path for chosen comp frames: bake the shot (the real `bake_frame`, from retime's
`src/` frames), put the canvas on the screen with the plan's camera (shutter-averaged), apply the flash exposure
(`flash_ev`, linear light) and the fitted grade (`grade_np`), and print the mean luma (0..255) of ours and of the AE
render side by side, with the share of clipped pixels. Constants of `layerfx` can be overridden to sweep them:

    python -m filmtools.amv.bake_luma --ref rendered_f0-599_full_quality.mp4 --src $AMV_OUT/src --titles $AMV_OUT/titles \\
        --frames 589-599,336-346 --set RFB_LENGTH=0.2 --set RFB_GAIN=1.0

Frames are measured on the top shot at 480x270 (--scale 0.25), away from the watermark and from pixels the canvas
does not cover. The mean is over those pixels only, so a frame is comparable between runs, not across shots.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from . import bake, bake_calibrate as cal, grade_np as G, layerfx as fx, plan as planmod


def parse_frames(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def decode_ref(ref, frames, ffmpeg=G.FFMPEG):
    """The AE render's frames at 960x540 as PNGs in a temp dir (named by comp frame)."""
    tmp = Path(tempfile.mkdtemp(prefix="bake_luma_"))
    ok = sorted(f for f in set(frames) if f < 600)
    sel = "+".join(f"eq(n\\,{f})" for f in ok)
    subprocess.run([ffmpeg, "-v", "error", "-i", str(ref), "-vf", f"select={sel},scale=960:540:flags=area",
                    "-fps_mode", "passthrough", "-start_number", "0", str(tmp / "k%04d.png")], check=True)
    for i, f in enumerate(ok):
        (tmp / f"k{i:04d}.png").rename(tmp / f"{f:04d}.png")
    return tmp


def ours_screen(plan, shot, f, scale, src, titles, matte_cache):
    """(RGB, coverage) of the baked shot on a W*scale screen."""
    matte = None
    if shot.matte:
        matte = matte_cache.get(shot.name) or matte_cache.setdefault(shot.name, bake.Matte(plan, shot))
    canvas = bake.bake_frame(plan, shot, f, scale, src, titles, matte)
    rgb = cal.screen_view(plan, shot, f, canvas, scale)
    white = canvas.copy()
    white[..., :3] = 1.0
    cov = cal.screen_view(plan, shot, f, white, scale)[..., 0]
    return rgb, cov


def measure(plan, frames, ref_dir, grade_params, scale, src, titles, verbose=True, dump=None):
    """Rows (frame, shot, ours, ae) of mean luma 0..255."""
    size = (int(planmod.W * scale), int(planmod.H * scale))
    cache = {}
    rows = []
    for f in frames:
        shot = plan.visible(f)[-1]
        rgb, cov = ours_screen(plan, shot, f, scale, src, titles, cache)
        ev = plan.flash_ev(f)
        if abs(ev) > 1e-9:
            rgb = G.linear_to_srgb(G.srgb_to_linear(rgb) * 2.0 ** ev)
        g = G.grade(rgb, grade_params, scale)
        m = G.fit_mask(cov > 0.999, None)
        bar = int(np.ceil(plan.bars(f) * scale)) + 2      # letterbox bars are drawn over the grade: leave them out
        if plan.bars(f) > 0.5:
            m[:bar] = False
            m[-bar:] = False
        ours = float(G.luma(g)[m].mean() * 255)
        if dump:
            Path(dump).mkdir(parents=True, exist_ok=True)
            tiles = [np.clip(rgb, 0, 1), g] + ([G.load_ref(ref_dir, f, size)] if f < 600 else [])
            cv2.imwrite(str(Path(dump) / f"{f:04d}.jpg"), (np.hstack(tiles)[..., ::-1] * 255).astype(np.uint8))
        if f < 600:
            ref = G.load_ref(ref_dir, f, size)
            ae = float(G.luma(ref)[m].mean() * 255)
            clip = lambda x: float((x.max(-1) >= 0.99)[m].mean() * 100)
            rows.append((f, shot.name, ours, ae, clip(g), clip(ref)))
        else:
            rows.append((f, shot.name, ours, None, None, None))
        if verbose:
            r = rows[-1]
            print(f"{r[0]:4d} {r[1]:16s} {r[2]:5.0f} {r[3] if r[3] is None else round(r[3]):>4} "
                  f"{'' if r[3] is None else format(r[2] - r[3], '+4.0f')}", flush=True)
    return rows


def apply_overrides(sets):
    for s in sets or []:
        k, _, v = s.partition("=")
        if not hasattr(fx, k):
            raise SystemExit(f"layerfx has no constant {k}")
        setattr(fx, k, type(getattr(fx, k))(v) if not isinstance(getattr(fx, k), str) else v)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--film", default="films/timeless")
    ap.add_argument("--ref", required=True, help="AE render mp4")
    ap.add_argument("--src", required=True)
    ap.add_argument("--titles", required=True)
    ap.add_argument("--grade", default="films/timeless/amv/grade.json")
    ap.add_argument("--frames", required=True)
    ap.add_argument("--scale", type=float, default=0.25)
    ap.add_argument("--dump", help="write ours-before-grade | ours graded | AE strips here")
    ap.add_argument("--set", action="append", help="NAME=value override of a layerfx constant (repeatable)")
    args = ap.parse_args(argv)
    apply_overrides(args.set)
    plan = planmod.load(args.film)
    doc = json.loads(Path(args.grade).read_text())
    frames = parse_frames(args.frames)
    ref_dir = decode_ref(args.ref, frames)
    rows = measure(plan, frames, ref_dir, doc.get("fitted", doc), args.scale, args.src, args.titles, dump=args.dump)
    gaps = [r[2] - r[3] for r in rows if r[3] is not None]
    if gaps:
        print(f"mean |gap| {np.mean(np.abs(gaps)):.1f}, mean gap {np.mean(gaps):+.1f} over {len(gaps)} frames")


if __name__ == "__main__":
    main()
