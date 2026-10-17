"""Bake stage: each shot's layer exactly as After Effects renders it *before* its transform.

For every comp frame of a shot: balance the retimed plate (exposure, saturation), lay the shot titles over it, cut the
subject out of the matte over the titles (with the rim glow), punch the eye-dive hole, then run the layer effects in
build.jsx's order (Motion Tile, CC Radial Fast Blur, Directional Blur, Optics Compensation) on the grown canvas. Output:
`<out>/<shot>/<f:04d>.png` RGBA at `Shot.canvas` (times --scale) and `<out>/<shot>/canvas.json`
`{w, h, ox, oy, scale}`: layer pixel (x, y) is at canvas pixel (x * scale + ox, y * scale + oy), `ox, oy` already in
canvas px. At scale 1.0 that is `Shot.canvas`; at other scales the canvas is sized from the scaled layer, so it can be a
pixel off `scale * Shot.canvas` (odd halves are rounded to even): use canvas.json, not the plan, to place the plane.

Inputs: `src/<shot>/<f:04d>.png` (retime's output). When a frame is missing there, a stand-in decodes the clip itself
(nearest 60p frame of `Shot.remap(f)`, no shutter integration, no frame mix), so the stage runs before retime exists.
Shot titles come from `titles/<shot>.<i>/<k:04d>.png` (1920x1080 RGBA, k = f - f_in) and are skipped when missing.

    python -m filmtools.amv.bake --film films/timeless [--shots T01,A03_sunset_mask] [--frames 30-40] [--scale 0.5]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from . import layerfx as fx
from . import plan as planmod

cv2.setNumThreads(1)          # parallelism is over frames; OpenCV's own threads would only fight for the cores

CLIP_FPS = 60.0


# ---------------------------------------------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------------------------------------------

def scaled_canvas(shot, scale):
    """(w, h, ox, oy) of the shot's canvas when the 1920x1080 layer is rendered at `scale`: the layer is
    round(1920 s) x round(1080 s), the canvas follows Motion Tile on that, so everything stays integral."""
    lw, lh = layer_size(scale)
    tw, th = shot.tile
    return fx.tile_canvas(lw, lh, tw, th)


def layer_size(scale):
    return int(round(planmod.W * scale)), int(round(planmod.H * scale))


# ---------------------------------------------------------------------------------------------------------------
# image io (8-bit PNG <-> float32)
# ---------------------------------------------------------------------------------------------------------------

def read_png(path, scale=1.0, alpha=False):
    """float32 RGB (or RGBA) 0..1 from an 8-bit PNG, resized by `scale` (area filter on premultiplied colour)."""
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im is None:
        raise FileNotFoundError(path)
    if im.ndim == 2:
        im = im[..., None]
    if im.dtype == np.uint16:
        f = im.astype(np.float32) / 65535.0
    else:
        f = im.astype(np.float32) / 255.0
    if f.shape[2] == 1:
        f = np.repeat(f, 3, axis=2)
    if f.shape[2] == 3:
        f = f[..., [2, 1, 0]]
    elif f.shape[2] == 4:
        f = f[..., [2, 1, 0, 3]]
    if f.shape[2] == 3 and alpha:
        f = np.concatenate([f, np.ones(f.shape[:2] + (1,), np.float32)], axis=2)
    if f.shape[2] == 4 and not alpha:
        f = f[..., :3]
    if scale != 1.0:
        lw, lh = layer_size(scale)
        if f.shape[2] == 4:
            f = fx.unpremultiply(cv2.resize(fx.premultiply(f), (lw, lh), interpolation=cv2.INTER_AREA))
        else:
            f = cv2.resize(f, (lw, lh), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(f)


def write_png(path, rgba):
    """RGBA float32 -> 8-bit PNG (fast compression: this is scratch for the renderer)."""
    u8 = np.clip(rgba * 255.0 + 0.5, 0, 255).astype(np.uint8)
    u8 = np.ascontiguousarray(u8[..., [2, 1, 0, 3]])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), u8, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
        raise IOError(f"cannot write {path}")


# ---------------------------------------------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------------------------------------------

_caps = {}


def standin_frame(plan, shot, f):
    """The clip frame nearest to `Shot.remap(f)` (clips are 60 fps, frame 0 at t = 0): float32 RGB 1920x1080.
    Stand-in for retime.py; no shutter blur, no frame mix."""
    path = str(plan.clip(shot))
    cap = _caps.get(path)
    if cap is None:
        cap = _caps[path] = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise FileNotFoundError(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idx = int(np.clip(round(shot.remap(f) * CLIP_FPS), 0, max(n - 1, 0)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, bgr = cap.read()
    if not ok:
        raise IOError(f"cannot decode frame {idx} of {path}")
    if shot.raw.get("flipx"):
        bgr = bgr[:, ::-1]
    return np.ascontiguousarray(bgr[..., ::-1]).astype(np.float32) / 255.0


def numbered(dirpath, k):
    """`<k:04d>.png` in `dirpath`, or the unpadded `<k>.png`; None when neither exists."""
    for name in (f"{k:04d}.png", f"{k}.png"):
        p = Path(dirpath) / name
        if p.exists():
            return p
    return None


def load_plate(plan, shot, f, src_dir, scale):
    p = numbered(Path(src_dir) / shot.name, f) if src_dir else None
    if p is not None:
        return read_png(p, scale)
    img = standin_frame(plan, shot, f)
    lw, lh = layer_size(scale)
    return img if scale == 1.0 else cv2.resize(img, (lw, lh), interpolation=cv2.INTER_AREA)


def title_frames(plan, shot, f, titles_dir, scale):
    """The shot's titles live at comp frame `f`, as RGBA arrays (missing files are skipped silently)."""
    out = []
    if not titles_dir:
        return out
    for i, t in enumerate(shot.titles):
        k = f - t["f_in"]
        if k < 0 or k >= t["spec"]["dur"] or f >= shot.end:
            continue
        p = numbered(Path(titles_dir) / f"{shot.name}.{i}", k)
        if p is None:
            continue
        img = read_png(p, scale, alpha=True)
        if t.get("scale"):
            img = scale_about_centre(img, t["scale"] / 100.0)
        out.append(img)
    return out


def scale_about_centre(img, k):
    h, w = img.shape[:2]
    m = np.array([[k, 0, w / 2.0 * (1 - k)], [0, k, h / 2.0 * (1 - k)]], np.float64)
    pm = fx.premultiply(img)
    return fx.unpremultiply(cv2.warpAffine(pm, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=0))


class Matte:
    """A shot's luma matte sequence: frame i of the sequence is shown at comp frame a + matte_f0 + i."""

    def __init__(self, plan, shot):
        first = plan.path(shot.matte)
        m = re.match(r"^(.*?)(\d+)$", first.stem)
        self.dir, self.prefix, self.digits = first.parent, m.group(1), len(m.group(2))
        self.first = int(m.group(2))
        self.f0 = shot.raw.get("matte_f0") or 0
        self.a = shot.a
        n = 0
        while (self.dir / f"{self.prefix}{self.first + n:0{self.digits}d}.png").exists():
            n += 1
        self.count = n

    def frame(self, f, scale):
        """Matte luma (H x W float32) at comp frame f, or None when the sequence is not running (no matte layer: AE's
        luma matte of nothing hides the cutout)."""
        i = f - self.a - self.f0
        if i < 0 or i >= self.count:
            return None
        img = read_png(self.dir / f"{self.prefix}{self.first + i:0{self.digits}d}.png", scale)
        return fx.luma(img).astype(np.float32)


# ---------------------------------------------------------------------------------------------------------------
# one frame
# ---------------------------------------------------------------------------------------------------------------

def bake_frame(plan, shot, f, scale=1.0, src_dir=None, titles_dir=None, matte=None):
    """The baked canvas of `shot` at comp frame `f`: float32 RGBA, size `scaled_canvas(shot, scale)`."""
    plate = load_plate(plan, shot, f, src_dir, scale)
    plate = fx.exposure(plate, shot.ev(f))
    plate = fx.hue_sat_master(plate, shot.sat)

    base = plate
    for t in title_frames(plan, shot, f, titles_dir, scale):
        base = fx.over(t, base)
    if matte is not None and shot.titles:
        m = matte.frame(f, scale)
        if m is not None:
            cut = fx.glow(plate, 55, 18 * scale, 0.6) if shot.rim else plate
            base = fx.over(np.dstack([cut, m]), base)

    lh, lw = base.shape[:2]
    alpha = np.ones((lh, lw), np.float32)
    hole = shot.hole(f)
    if hole is not None:
        cx, cy, rx, ry, feather, expansion = hole
        alpha = fx.hole_mask(alpha, cx * scale, cy * scale, rx * scale, ry * scale, feather * scale, expansion * scale)
    layer = np.dstack([base, alpha])

    tw, th = shot.tile
    canvas = fx.motion_tile(layer, tw, th)
    cw, ch, ox, oy = scaled_canvas(shot, scale)
    assert canvas.shape[:2] == (ch, cw), (canvas.shape, (ch, cw))

    rfb = shot.rfb(f)
    if rfb:
        amount, cx, cy = rfb
        canvas = fx.radial_fast_blur(canvas, amount, (cx * scale + ox, cy * scale + oy), "brightest",
                                     length=shot.raw.get("rfb_len"), mix=shot.raw.get("rfb_mix"))
    db = shot.dblur(f)
    if db:
        canvas = fx.directional_blur(canvas, db[0], db[1] * scale)
    fov = shot.bulge(f)
    if fov:
        canvas = fx.optics_compensation(canvas, fov, reverse=True, orientation=2,
                                        center=(planmod.ANCHOR[0] * scale + ox, planmod.ANCHOR[1] * scale + oy),
                                        dim_size=(lw, lh))
    if shot.raw.get("defocus"):
        canvas = fx.defocus(canvas, planmod.keys_lin(shot.raw["defocus"], f) * scale)
    return canvas


# ---------------------------------------------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------------------------------------------

_ctx = {}


def _init(film, scale, src_dir, titles_dir, out_dir):
    _ctx.update(plan=planmod.load(film), scale=scale, src=src_dir, titles=titles_dir, out=Path(out_dir), mattes={})


def _work(task):
    name, f = task
    plan = _ctx["plan"]
    shot = plan.shot(name)
    matte = None
    if shot.matte:
        matte = _ctx["mattes"].get(name) or _ctx["mattes"].setdefault(name, Matte(plan, shot))
    t0 = time.time()
    img = bake_frame(plan, shot, f, _ctx["scale"], _ctx["src"], _ctx["titles"], matte)
    write_png(_ctx["out"] / name / f"{f:04d}.png", img)
    return name, f, time.time() - t0


def select_shots(plan, spec):
    if not spec:
        return list(plan.shots)
    out = []
    for token in spec.split(","):
        token = token.strip()
        hits = [s for s in plan.shots if s.name == token] or [s for s in plan.shots if s.name.startswith(token)]
        if not hits:
            raise SystemExit(f"no shot matches {token!r}")
        out += [h for h in hits if h not in out]
    return out


def parse_frames(spec):
    if not spec:
        return None
    a, _, b = spec.partition("-")
    return int(a), int(b or a)


def default_paths(film):
    film = Path(film)
    fid = json.loads((film / "film.json").read_text())["id"]
    return film.parent.parent / "out" / fid / "amv"


def workers_for(shots, scale, requested):
    """Workers that fit in memory: a frame peaks at ~12 canvas-sized float32 RGBA buffers."""
    if requested:
        return requested
    biggest = max(planmod.W * planmod.H * scale * scale * (s.tile[0] / 100) * (s.tile[1] / 100) for s in shots)
    need = biggest * 16 * 12
    try:
        avail = os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        avail = 4 << 30
    return int(max(1, min(os.cpu_count() or 1, avail * 0.8 // need)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--film", required=True, help="film dir (films/<id>)")
    ap.add_argument("--shots", help="comma list of shot names or name prefixes (default: all)")
    ap.add_argument("--frames", help="comp frame range a-b, inclusive (default: each shot's own frames)")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--src")
    ap.add_argument("--titles")
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=0)
    args = ap.parse_args(argv)

    film = Path(args.film)
    plan = planmod.load(film)
    base = default_paths(film)
    src = args.src or str(base / "src")
    titles = args.titles or str(base / "titles")
    out = Path(args.out or base / "layers")
    shots = select_shots(plan, args.shots)
    rng = parse_frames(args.frames)

    tasks = []
    for s in shots:
        fr = [f for f in s.frames() if rng is None or rng[0] <= f <= rng[1]]
        if not fr:
            continue
        cw, ch, ox, oy = scaled_canvas(s, args.scale)
        (out / s.name).mkdir(parents=True, exist_ok=True)
        (out / s.name / "canvas.json").write_text(json.dumps({"w": cw, "h": ch, "ox": ox, "oy": oy, "scale": args.scale}))
        tasks += [(s.name, f) for f in fr]
    n = workers_for(shots, args.scale, args.workers)
    print(f"bake: {len(tasks)} frames of {len(shots)} shots, scale {args.scale}, {n} workers -> {out}", flush=True)
    t0 = time.time()
    tot = 0.0
    with mp.Pool(n, _init, (str(film), args.scale, src, titles, str(out))) as pool:
        for i, (name, f, dt) in enumerate(pool.imap_unordered(_work, tasks, chunksize=1), 1):
            tot += dt
            if i % 25 == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)}  {tot / i:.2f} s/frame/worker, {(time.time() - t0) / i:.2f} s/frame wall", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
