"""Timeless v3.1 stage: region masks for the nested zooms (the feathered shape the next clip shows through).

Sources (white = region):
  eye / lens  $AMV3_DATA/regions/<shot>/<kind>/f_NNNNN.png (SAM2, agent-08); until those exist, an ellipse around the
              shot's track (or p.at / the EDL focus) with half-axes `size` (plate px) stands in, same interface.
  bg          1 - $AMV3_DATA/mattes/<shot>/f_NNNNN.png (the subject stays, the background goes).
Every mask is box-blurred (3 passes, sigma ~16 plate px) at half resolution and written as a 16-bit grey PNG under
<out>/_regions/<shot>_<kind>/; the card shader thresholds it at 0.5 with smoothstep(0.5 -+ w), so the feather width is
animatable (w = feather_px / FEATHER_DIV) while the shape stays the mask's 0.5 contour. Also per frame: centroid, bbox,
area and the "inner" point (deepest inside the region, biased towards the track / frame centre): where the camera
crosses the front plane.
Runs inside Blender (numpy + bpy for reading images); no PIL / scipy needed.
"""
import json
import math
import os
import struct
import zlib

import numpy as np

HW, HH = 960, 540  # bg processing resolution (half of the 1920 x 1080 plate); eye / lens masks run at full res
BLUR_R = 8  # bg box radius (half-res px); 3 passes -> sigma ~ 8.2 half px ~ 16 plate px


def sigma_plate(r, scale):
    """sigma (plate px) of 3 box passes of radius r at `scale` plate px per processing px."""
    return scale * math.sqrt(3 * ((2 * r + 1) ** 2 - 1) / 12.0)


def feather_div(sig):
    return 2.0 * sig * math.sqrt(2 * math.pi)  # feather (plate px, full width) -> smoothstep half width w


FEATHER_DIV = feather_div(sigma_plate(BLUR_R, 2.0))
SIZES = {"eye": (70.0, 34.0), "lens": (95.0, 95.0)}


def write_png16(path, a):
    """a: float array (h, w) in 0..1, top row first -> 16-bit greyscale PNG."""
    h, w = a.shape
    v = (np.clip(a, 0.0, 1.0) * 65535.0 + 0.5).astype(">u2")
    raw = b"".join(b"\x00" + v[j].tobytes() for j in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, 0, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def read_grey(path):
    """Image -> float array (h, w) 0..1, top row first (channel 0; through bpy so any format Blender reads works)."""
    import bpy
    img = bpy.data.images.load(path, check_existing=False)
    try:
        img.colorspace_settings.name = "Non-Color"
    except TypeError:
        pass
    w, h = img.size
    buf = np.empty(w * h * img.channels, np.float32)
    img.pixels.foreach_get(buf)
    bpy.data.images.remove(img)
    a = buf.reshape(h, w, -1)[::-1, :, 0]
    return np.ascontiguousarray(a)


def resize(a, w, h):
    """Area-ish resize by integer block mean when possible, else nearest."""
    H, W = a.shape
    if W % w == 0 and H % h == 0:
        return a.reshape(h, H // h, w, W // w).mean(axis=(1, 3))
    ys = (np.arange(h) * H / h).astype(int)
    xs = (np.arange(w) * W / w).astype(int)
    return a[ys][:, xs]


def _box(a, r, axis):
    pad = [(r + 1, r) if ax == axis else (0, 0) for ax in range(a.ndim)]
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(p, axis=axis, dtype=np.float64)
    n = 2 * r + 1
    if axis == 0:
        return ((c[n:] - c[:-n]) / n).astype(np.float32)
    return ((c[:, n:] - c[:, :-n]) / n).astype(np.float32)


def blur(a, r, passes=3):
    for _ in range(passes):
        a = _box(_box(a, r, 0), r, 1)
    return a


def ellipse(cx, cy, rx, ry, w=HW, h=HH):
    """Soft-edged ellipse mask (plate px centre / half-axes) at w x h."""
    sx, sy = w / 1920.0, h / 1080.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx + 0.5) / sx - cx) ** 2 / rx ** 2 + ((yy + 0.5) / sy - cy) ** 2 / ry ** 2)
    return np.clip((1.0 - d) * min(rx, ry) / 1.5 + 0.5, 0.0, 1.0)


def analyse(m, bias_pt=None, bias=0.35):
    """Centroid / bbox / area / inner point (plate px) of a half-res mask m (region = m > 0.5)."""
    on = m > 0.5
    area = float(on.mean())
    if not on.any():
        c = bias_pt or [960.0, 540.0]
        return dict(area=0.0, centroid=list(c), bbox=[c[0], c[1], c[0], c[1]], inner=list(c), depth=0.0)
    ys, xs = np.nonzero(on)
    sx, sy = 1920.0 / m.shape[1], 1080.0 / m.shape[0]
    cen = [float(xs.mean() + 0.5) * sx, float(ys.mean() + 0.5) * sy]
    bbox = [float(xs.min()) * sx, float(ys.min()) * sy, float(xs.max() + 1) * sx, float(ys.max() + 1) * sy]
    # inner point: a heavy blur of the region at 1/8 res (how deep inside it a point sits), biased towards bias_pt
    small = resize(on.astype(np.float32), 120, 68) if m.shape == (HH, HW) else on.astype(np.float32)
    deep = blur(small, 4)
    deep = np.where(small > 0.5, deep, 0.0)
    yy, xx = np.mgrid[0:small.shape[0], 0:small.shape[1]].astype(np.float32)
    bx, by = (bias_pt or [960.0, 540.0])
    ex = (xx + 0.5) * 1920.0 / small.shape[1] - bx
    ey = (yy + 0.5) * 1080.0 / small.shape[0] - by
    score = deep - bias * (ex ** 2 + ey ** 2) / (960.0 ** 2)
    score = np.where(small > 0.5, score, -1e9)
    j = int(np.argmax(score))
    iy, ix = divmod(j, small.shape[1])
    inner = [float(ix + 0.5) * 1920.0 / small.shape[1], float(iy + 0.5) * 1080.0 / small.shape[0]]
    return dict(area=area, centroid=cen, bbox=bbox, inner=inner, depth=float(deep[iy, ix]))


def prepare(ctx, sid, kind, frames, size=None, at=None):
    """Build the blurred mask sequence of `kind` on shot `sid` for comp frames `frames` (iterable of ints).
    -> (bpy image sequence for the card shader, {frame: analyse() dict}). Cached per run in <out>/_regions."""
    import cards
    tag = f"{sid}_{kind}"
    odir = os.path.join(ctx.out, "_regions", tag)
    os.makedirs(odir, exist_ok=True)
    meta_path = os.path.join(odir, "meta.json")
    meta = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path) as fh:
                meta = {(int(k) if k.isdigit() else k): v for k, v in json.load(fh).items()}
        except Exception:  # noqa: BLE001
            meta = {}
    src_dir = os.path.join(ctx.data, "regions", sid, kind) if kind in ("eye", "lens") else \
        os.path.join(ctx.data, "mattes", sid)
    have_src = os.path.isdir(src_dir) and any(n.startswith("f_") for n in os.listdir(src_dir))
    if not have_src:
        ctx.log(f"regions {tag}: no {src_dir}, " + ("ellipse stand-in" if kind != "bg" else "WARN no mattes: whole card"))
    src_frames = sorted(int(n[2:7]) for n in os.listdir(src_dir) if n.startswith("f_") and n[2:7].isdigit()) \
        if have_src else []
    rx, ry = size or SIZES.get(kind, (80.0, 80.0))
    small = kind in ("eye", "lens")
    W, H = (1920, 1080) if small else (HW, HH)
    blur_r = meta.get("_blur_r")
    n_new = 0
    for f in sorted(set(int(x) for x in frames)):
        out_png = os.path.join(odir, f"f_{f:05d}.png")
        if f in meta and os.path.exists(out_png) and "_blur_r" in meta:
            continue
        track = at or ctx.track(sid, f) or ctx.shot(sid).get("focus") or [960.0, 540.0]
        if have_src:
            g = min(src_frames, key=lambda k: abs(k - f))
            ext = os.path.splitext([n for n in os.listdir(src_dir) if n.startswith(f"f_{g:05d}")][0])[1]
            a = resize(read_grey(os.path.join(src_dir, f"f_{g:05d}{ext}")), W, H)
            m = 1.0 - a if kind == "bg" else a
        elif kind == "bg":
            m = np.ones((H, W), np.float32)
        else:
            m = ellipse(track[0], track[1], rx, ry, W, H)
        m = np.clip(m, 0.0, 1.0).astype(np.float32)
        info = analyse(resize(m, HW, HH) if small else m,
                       bias_pt=track if kind != "bg" else [0.5 * (960.0 + track[0]), 0.5 * (540.0 + track[1])])
        if small:
            info["inner"] = list(info["centroid"])  # an opening is convex: the camera aims at its centre
        if blur_r is None:
            # small openings get a small blur, so the mask's 0.5 contour still hugs the lids (an eye can be 30 px tall)
            if small:
                x0, y0, x1, y1 = info["bbox"]
                blur_r = int(max(1, min(8, round(min(x1 - x0, y1 - y0) / 14.0))))
            else:
                blur_r = BLUR_R
            meta["_blur_r"] = blur_r
            meta["_scale"] = 1.0 if small else 2.0
        write_png16(out_png, blur(m, blur_r))
        meta[f] = info
        n_new += 1
    with open(meta_path, "w") as fh:
        json.dump({str(k): v for k, v in sorted(meta.items(), key=lambda kv: str(kv[0]))}, fh)
    first = cards.link_sequence(odir, os.path.join(ctx.out, "_seq", "regions", tag), "png")
    img = cards.load_sequence(first, "Non-Color")
    ctx.log(f"regions {tag}: {n_new} new / {len(meta) - 2} frames, blur r {blur_r} ({'source' if have_src else 'stand-in'})")
    return img, meta


def info_at(meta, f):
    k = min((x for x in meta if isinstance(x, int)), key=lambda x: abs(x - f))
    return meta[k]


def feather_w(feather_plate_px, meta=None):
    """Smoothstep half width (mask units) for a full feather width in plate px (meta: the sequence's blur)."""
    div = FEATHER_DIV
    if meta and "_blur_r" in meta:
        div = feather_div(sigma_plate(meta["_blur_r"], meta.get("_scale", 2.0)))
    return max(0.004, min(0.45, feather_plate_px / div))
