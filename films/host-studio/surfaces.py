"""Seamless PBR surface textures for the host studio: albedo, normal and roughness for the set's main materials.

    uv run --with numpy --with pillow --with scipy python films/host-studio/surfaces.py [--only Oak Walnut]

writes films/host-studio/surfaces/T_<Name>_{A,N,R}.png (and T_Linen_O.png) plus contact.png, each texture tiled 2x2:
  A  albedo, sRGB
  N  tangent-space normal, DirectX convention (green = down), as Unreal expects
  R  roughness, linear grayscale
  O  opacity (Linen only): the gaps between the threads are open

Every texture covers a stated real size (SPECS, in metres) and tiles: all its noise is built periodically (white noise
filtered in the Fourier domain, wrap-around sampling and splatting, Voronoi on a torus), and every repeating structure
(planks, threads, loops, stitches) fits a whole number of times into the tile. In Unreal the meshes' UVs are in world
scale (1 UV unit = 1 m), so a material samples a texture at UV / size. Heights are built in metres, so the normals have
the true slope of the relief at that scale.

The same file renders the Blender previews on a 1 m plane and a rounded box with a grazing key light (it runs inside
Blender when bpy is importable):

    Blender -b --factory-startup -P surfaces.py -- --preview --tex <dir with the PNGs> --out <dir> [--only ...]
    python surfaces.py --sheet <dir with the renders>     # composes surfaces/preview_<Name>.png from them
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

try:  # not in Blender's Python, which only runs the preview half of this file
    import scipy.fft as sfft
    from PIL import Image, ImageDraw, ImageFont
    from scipy import ndimage as ndi
    from scipy.spatial import cKDTree
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
OUT = HERE / "surfaces"
F32 = np.float32

# name: (pixels, metres covered)
SPECS = {
    "Limewash": (2048, 2.0),
    "OakFloor": (2048, 2.0),
    "Oak": (2048, 1.0),
    "OakEnd": (2048, 0.2),
    "Walnut": (2048, 1.0),
    "Linen": (1024, 0.08),
    "Wool": (2048, 0.6),
    "Felt": (1024, 0.4),
    "Stoneware": (1024, 0.3),
    "BookCloth": (1024, 0.1),
    "Fleece": (1024, 0.1),
    "Leather": (1024, 0.1),
    "Brushed": (1024, 0.2),
}
METALLIC = {"Brushed"}


# --------------------------------------------------------------------------- colour and maths

def srgb2lin(c):
    c = np.asarray(c, F32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(F32)


def lin2srgb(x):
    x = np.clip(np.asarray(x, F32), 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055).astype(F32)


def col(rgb):
    """An sRGB 0-255 triple as a linear colour."""
    return srgb2lin(np.array(rgb, F32) / 255)


def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    if np.ndim(t) == 2 and (np.ndim(a) == 3 or np.ndim(b) == 3 or np.size(a) == 3):
        t = t[..., None]
    return a + (b - a) * t


def match_mean(lin, target_srgb, mask=None):
    """Scale a linear RGB image per channel so its mean in sRGB is target_srgb (0-255)."""
    t = np.array(target_srgb, F32) / 255
    for _ in range(6):
        s = lin2srgb(lin)
        m = s[mask].mean(0) if mask is not None else s.reshape(-1, 3).mean(0)
        lin = lin * (srgb2lin(t) / np.maximum(srgb2lin(m), 1e-6))
    return lin


# --------------------------------------------------------------------------- periodic noise

def gnoise(rng, shape, su, sv=None, angle=0.0):
    """Unit-variance periodic noise: white noise blurred by a Gaussian of std su px along x (u) and sv px along y
    (v), the axes turned by angle (radians). It wraps exactly at the tile's edges."""
    sv = su if sv is None else sv
    fy = sfft.fftfreq(shape[0]).astype(F32)[:, None]
    fx = sfft.rfftfreq(shape[1]).astype(F32)[None, :]
    if angle:
        c, s = math.cos(angle), math.sin(angle)
        fx, fy = c * fx + s * fy, -s * fx + c * fy
    filt = np.exp(-2 * np.pi ** 2 * ((su * fx) ** 2 + (sv * fy) ** 2)).astype(F32)
    w = rng.standard_normal(shape, dtype=F32)
    n = sfft.irfft2(sfft.rfft2(w, workers=-1) * filt, s=shape, workers=-1).astype(F32)
    n -= n.mean()
    return n / (n.std() + 1e-12)


def noise1(rng, n, s):
    """Unit-variance periodic 1-D noise of n samples, Gaussian-blurred by s samples."""
    f = sfft.rfftfreq(n)
    w = rng.standard_normal(n)
    x = sfft.irfft(sfft.rfft(w) * np.exp(-2 * np.pi ** 2 * (s * f) ** 2), n)
    x -= x.mean()
    return (x / (x.std() + 1e-12)).astype(F32)


def wrap_sample(img, y, x, order=1):
    return ndi.map_coordinates(img, [y, x], order=order, mode="grid-wrap").astype(F32)


def splat(canvas, cy, cx, stamp, mode="add"):
    """Add (or max) a stamp centred at (cy, cx) into a canvas, wrapping around its edges."""
    h, w = stamp.shape
    H, W = canvas.shape
    ys = (np.arange(h) + int(round(cy)) - h // 2) % H
    xs = (np.arange(w) + int(round(cx)) - w // 2) % W
    ix = np.ix_(ys, xs)
    if mode == "max":
        canvas[ix] = np.maximum(canvas[ix], stamp)
    else:
        canvas[ix] += stamp


def normal_dx(h, px):
    """Tangent-space normal (0..1 RGB) of a height field in metres on pixels of px metres, DirectX (green down)."""
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * px)
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / (2 * px)  # dh / d(row): rows run down the image
    n = np.stack([-gx, -gy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


# --------------------------------------------------------------------------- wood

def ring_phase(rng, r, sp, cv):
    """Growth-ring index at radius r (m): rings sp apart on average, each year's width varying by cv, with slow
    good and bad decades."""
    n = 1600
    trend = np.convolve(rng.standard_normal(n + 40), np.ones(25) / 5, "same")[20:20 + n]
    steps = sp * np.exp(rng.normal(0, cv, n) + 0.22 * trend)
    lo = float(r.min()) - sp * rng.uniform(0.1, 1.0)
    edges = lo + np.concatenate([[0.0], np.cumsum(steps)])
    return np.interp(r, edges, np.arange(n + 1)).astype(F32)


def wood_board(rng, rows, cols, px, P, wrap_u=False, knots=0):
    """One board (or veneer leaf) of wood with the grain along u (columns): rows x cols pixels of px metres.

    The board is a plane cut through a log whose pith runs along u at depth s(u) below the face and at vc(u) across
    it; a ring's radius at a point is then sqrt((v - vc)^2 + s^2). Where the face passes close over the pith (flat
    sawn) the rings cross it in cathedral arches; towards the edges, or when vc is off the board (rift and quarter
    sawn), they run straight along it. Oak's earlywood pores, its medullary rays (fine dark ticks on flat-sawn faces,
    pale flakes on quartered ones), the fibres and the board's tone come on top.

    Returns linear albedo (rows, cols, 3), height (m) and roughness."""
    Wd = cols if wrap_u else int(cols * 1.3) + 48  # not periodic along a plank: its ends must not match
    Hd = rows + 48
    shp = (Hd, Wd)
    mm = 0.001 / px  # pixels per mm
    v = (np.arange(Hd, dtype=F32) * px)[:, None]
    s = P["d"] + P["d_amp"] * noise1(rng, Wd, P["d_len"] / px) + 0.25 * P["d_amp"] * noise1(rng, Wd, P["d_len"] / px / 4)
    s = np.maximum(s, 0.008)[None, :]
    vc = (P["vc"] + P["vc_amp"] * noise1(rng, Wd, 0.25 / px))[None, :]
    dv = (v - vc) * P["ecc"]
    r0 = np.sqrt(dv ** 2 + s ** 2)
    r = r0 + P["warp"] * (gnoise(rng, shp, 60 * mm, 7 * mm) + 0.35 * gnoise(rng, shp, 15 * mm, 1.5 * mm))

    kn = []
    for _ in range(knots):
        ky, kx = rng.uniform(0.25, 0.75) * rows, rng.uniform(0.1, 0.9) * cols
        rad = rng.uniform(1.2, 2.6) * mm
        yy = np.arange(Hd, dtype=F32)[:, None] - ky
        xx = (np.arange(Wd, dtype=F32)[None, :] - kx) / 1.35
        d = np.sqrt(yy ** 2 + xx ** 2)
        r = r + rng.uniform(2.5, 4.5) * 0.001 * np.exp(-(d / (rad * 3.2)) ** 2)
        kn.append((d, rad))

    phase = ring_phase(rng, r, P["sp"], P["sp_cv"])
    # the trunk tapers, so along the board the face cuts ever later rings: arches nest one way, as in flat-sawn
    # boards; a whole number of rings per tile keeps a periodic veneer seamless
    taper = P.get("taper", 0.0) * (Wd * px)
    if wrap_u:
        taper = round(taper)
    phase = phase + taper * (np.arange(Wd, dtype=F32) / Wd)[None, :]
    gy, gx = np.gradient(phase)
    g = np.hypot(gx, gy)
    f = phase % 1.0
    ew = P["ew"]
    f2 = np.where(f > 0.5 + ew / 2, f - 1.0, f)
    dl = np.clip(g * 0.9, 0.025, 0.5)
    early = sstep(-dl, dl, f2) * (1 - sstep(ew - dl - P["ew_soft"], ew + dl, f2))
    early = lerp(early, ew, sstep(0.18, 0.45, g))  # rings finer than a pixel blend to their average
    late = np.clip((f - ew) / (1 - ew), 0, 1)
    late = lerp(late, 0.5, sstep(0.18, 0.45, g))

    pn = gnoise(rng, shp, P["pore_len"] * mm, P["pore_w"] * mm)
    pores = sstep(P["pe0"], P["pe0"] + 0.7, pn) * early
    pores = np.clip(pores + P["pore_scatter"] * sstep(1.9, 2.5, gnoise(rng, shp, P["pore_len"] * mm, P["pore_w"] * mm)), 0, 1)
    fiber = gnoise(rng, shp, 7 * mm, 0.35 * mm)
    q = np.clip(np.abs(dv) / r0, 0, 1)  # 0 where the face is tangential to the rings, 1 where it is radial
    rays_n = sstep(2.1, 2.7, gnoise(rng, shp, P["ray_len"] * mm, 0.22 * mm)) * (1 - q) ** 1.5
    rays_w = sstep(1.9, 2.6, gnoise(rng, shp, 5 * mm, 0.9 * mm, angle=rng.uniform(-0.15, 0.15))) * sstep(0.6, 0.95, q)
    lf = gnoise(rng, shp, 180 * mm, 35 * mm)
    mf = gnoise(rng, shp, 40 * mm, 6 * mm)
    streak = sstep(P["streak0"], P["streak0"] + 2.2,
                   gnoise(rng, shp, 220 * mm, 18 * mm) + 0.35 * gnoise(rng, shp, 60 * mm, 4 * mm)
                   + 0.2 * gnoise(rng, shp, 20 * mm, 1.2 * mm))

    c = lerp(col(P["late"]), col(P["late2"]), late ** 1.6)
    c = lerp(c, col(P["early"]), early * P["ew_contrast"])
    c = lerp(c, col(P["honey"]), streak * P["streak_amt"])
    c = c * (1 + P["fib"] * fiber + P["lf"] * lf + 0.5 * P["lf"] * mf)[..., None]
    c = lerp(c, col(P["pore"]), pores * P["pore_amt"])
    c = lerp(c, col(P["ray_dark"]), rays_n * P["ray_dark_amt"])
    c = lerp(c, col(P["ray_light"]), rays_w * P["ray_light_amt"])

    h = (-P["h_early"] * early - P["h_pore"] * pores - 5e-6 * rays_n + 3e-6 * rays_w + 1.5e-6 * fiber
         + 20e-6 * gnoise(rng, shp, 25 * mm))
    rough = (P["rough"] + 0.05 * early + 0.10 * pores - 0.06 * rays_w + 0.015 * fiber + 0.02 * lf)

    for d, rad in kn:
        core = 1 - sstep(rad * 0.7, rad * 1.15, d + 0.3 * mm * gnoise(rng, shp, 0.4 * mm))
        halo = np.exp(-((d - rad * 1.2) / (rad * 0.35)) ** 2)
        c = lerp(c, col(P["knot"]), np.clip(core * 0.9 + halo * 0.35, 0, 1))
        h = h - 15e-6 * core
        rough = rough + 0.05 * core

    return c[:rows, :cols], h[:rows, :cols], rough[:rows, :cols]


OAK = dict(
    late=(219, 188, 146), late2=(203, 167, 124), early=(176, 135, 92), pore=(118, 86, 56), honey=(214, 170, 118),
    ray_dark=(146, 106, 68), ray_light=(232, 210, 176), knot=(92, 62, 36),
    ew=0.30, ew_soft=0.10, ew_contrast=0.75, sp=0.0028, sp_cv=0.32, ecc=1.0, warp=0.0012,
    pore_len=1.4, pore_w=0.28, pe0=0.9, pore_scatter=0.05, pore_amt=0.55, ray_len=4.5,
    ray_dark_amt=0.45, ray_light_amt=0.3, streak0=1.6, streak_amt=0.0, fib=0.035, lf=0.045,
    h_early=10e-6, h_pore=30e-6, rough=0.47,
)

WALNUT = dict(
    late=(112, 74, 49), late2=(86, 56, 37), early=(74, 47, 31), pore=(34, 21, 14), honey=(168, 118, 74),
    ray_dark=(70, 45, 30), ray_light=(130, 90, 60), knot=(40, 26, 18),
    ew=0.35, ew_soft=0.25, ew_contrast=0.5, sp=0.0045, sp_cv=0.35, ecc=1.0, warp=0.0016,
    pore_len=1.6, pore_w=0.3, pe0=1.2, pore_scatter=0.6, pore_amt=0.65, ray_len=3.0,
    ray_dark_amt=0.0, ray_light_amt=0.0, streak0=0.4, streak_amt=0.32, fib=0.05, lf=0.07,
    h_early=6e-6, h_pore=35e-6, rough=0.43,
)


def leaf_params(rng, base, width, flat_p=0.55, sp=None):
    P = dict(base)
    if rng.random() < flat_p:  # flat sawn: the face passes close over the pith, cathedral arches
        P.update(d=rng.uniform(0.03, 0.075), d_amp=rng.uniform(0.0015, 0.004), d_len=rng.uniform(0.08, 0.16),
                 vc=width * rng.uniform(0.3, 0.7), vc_amp=rng.uniform(0.004, 0.012),
                 taper=rng.choice([-1, 1]) * rng.uniform(4, 9))  # rings per metre
    else:  # rift / quarter sawn: the pith is off the board's edge, rings run straight along it
        P.update(d=rng.uniform(0.02, 0.07), d_amp=rng.uniform(0.002, 0.006), d_len=rng.uniform(0.1, 0.2),
                 vc=-rng.uniform(0.06, 0.25) if rng.random() < 0.5 else width + rng.uniform(0.06, 0.25),
                 vc_amp=rng.uniform(0.002, 0.008), taper=rng.uniform(-2, 2))
    lo, hi = sp or (0.8, 1.25)
    P["sp"] = base["sp"] * rng.uniform(lo, hi)
    return P


def veneer(N, px, rng, base, target, leaf_w, flat_p, sp=None):
    """A panel of veneer leaves laid side by side across v, each its own cut of the log, the whole tile periodic."""
    L = N * px
    k = max(2, round(L / np.mean(leaf_w)))
    w = rng.uniform(leaf_w[0], leaf_w[1], k)
    edges = np.round(np.concatenate([[0], np.cumsum(w / w.sum())]) * N).astype(int)
    A = np.zeros((N, N, 3), F32)
    H = np.zeros((N, N), F32)
    R = np.zeros((N, N), F32)
    for i in range(k):
        y0, y1 = edges[i], edges[i + 1]
        P = leaf_params(rng, base, (y1 - y0) * px, flat_p, sp)
        a, h, r = wood_board(rng, y1 - y0, N, px, P, wrap_u=True)
        tone = 1 + rng.normal(0, 0.035)
        warm = rng.normal(0, 0.02)
        A[y0:y1] = a * tone * np.array([1 + warm, 1, 1 - 1.5 * warm], F32)
        H[y0:y1] = h
        R[y0:y1] = r + rng.normal(0, 0.012)
    return match_mean(A, target), H, R


def tex_oak(N, px, rng):
    A, H, R = veneer(N, px, rng, OAK, (205, 170, 128), (0.13, 0.21), 0.5)
    return dict(A=A, H=H, R=np.clip(R, 0.4, 0.62))


def tex_walnut(N, px, rng):
    A, H, R = veneer(N, px, rng, WALNUT, (105, 70, 46), (0.16, 0.28), 0.55)
    return dict(A=A, H=H, R=np.clip(R, 0.36, 0.6))


def tex_oakfloor(N, px, rng):
    """11 rows of planks along u (200 cm / 11 = 18.2 cm wide, so the rows tile); each row holds one 200 cm plank or two
    of 90-110 cm, the joints staggered at least 30 cm from the neighbouring rows'. Micro-bevelled edges."""
    L = N * px
    nrow = 11
    bounds = np.round(np.arange(nrow + 1) * N / nrow).astype(int)
    A = np.zeros((N, N, 3), F32)
    H = np.zeros((N, N), F32)
    R = np.zeros((N, N), F32)
    joints = []
    min_gap = 0.3 / L
    for i in range(nrow):
        for _ in range(500):
            x0 = rng.random()
            js = [x0] if rng.random() < 0.4 else [x0, (x0 + rng.uniform(0.45, 0.55)) % 1.0]
            near = [joints[i - 1]] if i else []
            if i == nrow - 1:
                near.append(joints[0])
            ok = all(min(abs(a - b), 1 - abs(a - b)) >= min_gap for prev in near for a in js for b in prev)
            if ok:
                break
        joints.append(js)
    base = dict(OAK, late=(222, 190, 148), late2=(207, 170, 126), rough=0.45, h_early=8e-6, h_pore=25e-6)
    for i in range(nrow):
        y0, y1 = bounds[i], bounds[i + 1]
        js = sorted(round(j * N) for j in joints[i])
        spans = [(js[k], (js[(k + 1) % len(js)] - js[k]) % N or N) for k in range(len(js))]
        for x0, n in spans:
            P = leaf_params(rng, base, (y1 - y0) * px, 0.6, (0.75, 1.3))
            P["lf"] = 0.06
            a, h, r = wood_board(rng, y1 - y0, n, px, P, knots=rng.choice([0, 0, 0, 1, 1, 2]))
            tone = math.exp(rng.normal(0, 0.065))
            warm = rng.normal(0, 0.03)
            a = a * tone * np.array([1 + warm, 1, 1 - 1.6 * warm], F32)
            # micro-bevel: within ~1.5 mm of every edge the face rolls down 0.8 mm; the gap itself reads dark
            ey = np.minimum(np.arange(y1 - y0) + 0.5, (y1 - y0) - np.arange(y1 - y0) - 0.5)[:, None] * px
            ex = np.minimum(np.arange(n) + 0.5, n - np.arange(n) - 0.5)[None, :] * px
            e = np.minimum(ey, ex)
            bev = np.clip(1 - e / 0.0016, 0, 1)
            h = h - 0.0008 * bev ** 1.5
            a = a * (1 - 0.45 * sstep(0.35, 0.9, bev))[..., None]
            r = r + 0.2 * sstep(0.35, 0.9, bev)
            xs = (np.arange(n) + x0) % N
            A[y0:y1, xs] = a
            H[y0:y1, xs] = h
            R[y0:y1, xs] = r + rng.normal(0, 0.01)
    A = match_mean(A, (198, 161, 119))
    return dict(A=A, H=H, R=np.clip(R, 0.38, 0.62))


def tex_oakend(N, px, rng):
    """Oak end grain over 20 cm: gently arched growth rings (~2.9 mm), a row of big open earlywood pores at the start
    of each ring, small latewood pores in radial flames, and the rays crossing the rings as fine pale lines."""
    shp = (N, N)
    mm = 0.001 / px
    nr = 68  # rings per tile, whole so it wraps
    y, x = np.mgrid[0:N, 0:N].astype(F32)
    bend = 0.9 * gnoise(rng, shp, 60 * mm, 40 * mm) + 0.2 * gnoise(rng, shp, 14 * mm, 8 * mm) + 0.04 * gnoise(rng, shp, 2 * mm, 1 * mm)
    arch = 1.6 * np.cos(2 * np.pi * x / N + rng.uniform(0, 6.3)) + 0.5 * np.cos(4 * np.pi * x / N + rng.uniform(0, 6.3))
    p = nr * (y / N) + bend + arch
    # uneven ring widths: remap ring index by a periodic sequence of widths
    w = np.exp(rng.normal(0, 0.28, nr) + 0.25 * np.convolve(rng.standard_normal(nr + 8), np.ones(5) / 2.2, "same")[4:4 + nr])
    cum = np.concatenate([[0], np.cumsum(w / w.sum() * nr)])
    base = np.floor(p / nr) * nr
    phase = base + np.interp(p - base, cum, np.arange(nr + 1)).astype(F32)
    f = phase % 1.0
    ew = 0.2
    early = sstep(0.0, 0.03, f) * (1 - sstep(ew - 0.04, ew + 0.03, f))
    late = np.clip((f - ew) / (1 - ew), 0, 1)
    rad = phase * (N / nr)  # ~radial coordinate in px (wraps with the rings), so radial features follow them

    # pores as round dots: seeds on a jittered grid, kept where they fall in the earlywood (big) or in a latewood
    # flame (small), drawn by distance to the nearest seed on the torus
    flames = sstep(0.5, 1.5, wrap_sample(gnoise(rng, shp, 0.45 * mm, 1.8 * mm), rad % N, x))
    g = 0.34 * mm
    gy, gx = np.mgrid[0:N / g, 0:N / g].reshape(2, -1) * g
    pts = (np.stack([gx, gy], 1) + rng.uniform(-0.45, 0.45, (gx.size, 2)) * g) % N
    iy, ix = pts[:, 1].astype(int) % N, pts[:, 0].astype(int) % N
    e, fl, lt = early[iy, ix], flames[iy, ix], late[iy, ix]
    big = (e > 0.5) & (rng.random(gx.size) < 0.85)
    small = (~big) & (lt > 0.15) & (rng.random(gx.size) < 0.55 * fl)
    keep = big | small
    pts = pts[keep]
    rads = np.where(big[keep], rng.uniform(0.11, 0.2, keep.sum()) * mm, rng.uniform(0.04, 0.07, keep.sum()) * mm)
    d, i = cKDTree(pts, boxsize=N).query(np.stack([(x + 0.5).ravel() % N, (y + 0.5).ravel() % N], 1), workers=-1)
    d, i = d.reshape(shp), i.reshape(shp)
    pr = rads[i]
    pore = 1 - sstep(pr * 0.75, pr * 1.2 + 0.4, d)
    isbig = big[keep][i]
    big_pores, small_pores = pore * isbig, pore * ~isbig

    rays = np.maximum(sstep(2.0, 2.6, wrap_sample(gnoise(rng, shp, 0.8, 4 * mm), rad % N, x)) * 0.7,
                      sstep(2.2, 2.7, wrap_sample(gnoise(rng, shp, 2.2, 9 * mm), rad % N, x)))
    lf = gnoise(rng, shp, 25 * mm)
    saw = gnoise(rng, shp, 30 * mm, 0.15 * mm, angle=0.5)  # sanding scratches

    c = lerp(col((182, 142, 98)), col((150, 108, 70)), late ** 2)
    c = lerp(c, col((140, 100, 64)), early * 0.5)
    c = c * (1 + 0.02 * lf + 0.02 * saw)[..., None]
    c = lerp(c, col((48, 31, 20)), big_pores * 0.9)
    c = lerp(c, col((96, 64, 42)), small_pores * 0.7)
    c = lerp(c, col((194, 158, 116)), rays * 0.45)
    c = match_mean(c, (160, 120, 82))
    h = -60e-6 * big_pores - 25e-6 * small_pores - 6e-6 * early + 4e-6 * rays + 2e-6 * saw + 15e-6 * gnoise(rng, shp, 15 * mm)
    rough = 0.66 + 0.1 * big_pores + 0.04 * early - 0.04 * rays + 0.02 * lf
    return dict(A=c, H=h, R=np.clip(rough, 0.55, 0.85))


# --------------------------------------------------------------------------- plaster

def tex_limewash(N, px, rng):
    """Limewash: cloudy mottling in 20-60 cm patches (+-5 % value), crossed brush strokes with bristle lines, fine
    sand, a gently wavy plaster under it."""
    shp = (N, N)
    cm = 0.01 / px
    y, x = np.mgrid[0:N, 0:N].astype(F32)
    cloud = 0.75 * gnoise(rng, shp, 13 * cm) + 0.45 * gnoise(rng, shp, 5.5 * cm) + 0.2 * gnoise(rng, shp, 2.2 * cm)
    cloud = wrap_sample(cloud, y + 9 * cm * gnoise(rng, shp, 18 * cm), x + 9 * cm * gnoise(rng, shp, 18 * cm))
    cloud = np.tanh(cloud / cloud.std() * 0.8)
    cloud = (cloud - cloud.mean()) / cloud.std()

    fine = gnoise(rng, shp, 0.5 * cm)
    tone = np.zeros(shp, F32)
    bh = np.zeros(shp, F32)
    for _ in range(320):
        R = rng.uniform(0.3, 1.1) / px
        l = rng.uniform(0.22, 0.55) / px
        w = rng.uniform(0.06, 0.13) / px
        a = rng.choice([-1, 1]) * math.pi / 4 + rng.normal(0, 0.3) + rng.choice([0, math.pi])
        sg = rng.choice([-1, 1])
        p0 = rng.random(2) * N
        nrm = np.array([-math.sin(a), math.cos(a)])
        cen = p0 + nrm * R * sg
        b = int(l + w) + 4
        ys = np.arange(b, dtype=F32)[:, None] + int(p0[1]) - b // 2
        xs = np.arange(b, dtype=F32)[None, :] + int(p0[0]) - b // 2
        dx, dy = xs - cen[0], ys - cen[1]
        across = (np.hypot(dx, dy) - R) * sg
        th0 = math.atan2(p0[1] - cen[1], p0[0] - cen[0])
        along = ((np.arctan2(dy, dx) - th0 + np.pi) % (2 * np.pi) - np.pi) * R
        e = fine[np.ix_(ys[:, 0].astype(int) % N, xs[0].astype(int) % N)] * 0.6 * cm
        m = 1 - sstep(0.3 * w, 0.5 * w, np.abs(across) + e)
        m = m * sstep(-l / 2, -l / 2 + 6 * cm, along) * (1 - sstep(l / 2 - 16 * cm, l / 2, along + 2.5 * e))
        nb = int(w) + 8
        prof = noise1(rng, nb, 1.3) * 0.7 + noise1(rng, nb, 4) * 0.3
        br = np.interp(across + nb / 2, np.arange(nb), prof)
        press = np.interp(along, np.linspace(-l / 2, l / 2, 5), rng.uniform(0.4, 1.0, 5))
        m = m * press
        splat(tone, p0[1], p0[0], (m * (rng.normal(0, 1) + 0.35 * br)).astype(F32))
        splat(bh, p0[1], p0[0], (m * br).astype(F32))
    tone /= tone.std()
    bh /= bh.std()

    sand = gnoise(rng, shp, 0.6)
    grains = sstep(2.3, 2.9, gnoise(rng, shp, 1.0))
    v = 1 + 0.024 * cloud + 0.007 * tone + 0.01 * sand + 0.02 * grains * np.sign(gnoise(rng, shp, 3))
    base = np.array([226, 216, 200], F32) / 255
    srgb = base[None, None] * v[..., None]
    srgb[..., 0] *= 1 - 0.004 * cloud  # the darker, denser lime is a little warmer
    srgb[..., 2] *= 1 + 0.012 * cloud
    A = match_mean(srgb2lin(np.clip(srgb, 0, 1)), (226, 216, 200))
    H = (0.0003 * gnoise(rng, shp, 4 * cm) + 0.00006 * gnoise(rng, shp, 1.2 * cm) + 25e-6 * bh
         + 12e-6 * sand + 35e-6 * grains)
    Rf = 0.9 - 0.02 * cloud - 0.012 * bh + 0.01 * sand
    return dict(A=A, H=H, R=np.clip(Rf, 0.85, 0.95))


# --------------------------------------------------------------------------- textiles

def thread_layer(rng, N, n, cov, slub, wander, s_slub, s_wander, s_fuzz=0.0):
    """Threads spaced along columns (x) and running along rows (y): n threads in N px, each covering cov of the
    pitch, thickening in slubs and wandering sideways. Returns per-pixel coverage, cross-section profile (0..1),
    thread index (unwrapped) and the thread's relative thickness there."""
    p = N / n
    W = np.stack([noise1(rng, N, s_wander) for _ in range(n)]) * wander * p
    S = np.stack([slub * sstep(0.9, 2.1, noise1(rng, N, s_slub)) + 0.12 * noise1(rng, N, s_slub / 3) for _ in range(n)])
    S = np.clip(S, -0.3, None)
    width = cov * p * (1 + S)
    a = np.arange(N, dtype=F32)[None, :] + 0.5
    b = np.arange(N)[:, None]
    i0 = np.floor(a / p).astype(int)
    best = dict(alpha=np.zeros((N, N), F32), prof=np.zeros((N, N), F32), idx=i0.repeat(N, 0), thick=np.ones((N, N), F32))
    for di in (-1, 0, 1):
        ic = i0 + di
        k = ic % n
        cen = (ic + 0.5) * p + W[k, b]
        hw = width[k, b] / 2
        d = np.abs(a - cen)
        alpha = np.clip(hw - d + 0.5, 0, 1)
        prof = np.sqrt(np.clip(1 - (d / hw) ** 2, 0, 1))
        take = alpha > best["alpha"]
        best["alpha"] = np.where(take, alpha, best["alpha"])
        best["prof"] = np.where(take, prof, best["prof"])
        best["idx"] = np.where(take, ic, best["idx"])
        best["thick"] = np.where(take, 1 + S[k, b], best["thick"])
    return best


def plain_weave(rng, N, nx, ny, cov, slub, wander, s_slub, s_wander, crimp=0.35):
    """A plain weave: nx warp threads (running along v) and ny weft threads (along u), over-under alternating.
    Returns height (in thread radii), coverage, which layer is on top, per-pixel thread tone index and thickness."""
    warp = thread_layer(rng, N, nx, cov[0], slub[0], wander[0], s_slub, s_wander)
    weft = thread_layer(rng, N, ny, cov[1], slub[1], wander[1], s_slub, s_wander)
    weft = {k: v.T for k, v in weft.items()}
    y, x = np.mgrid[0:N, 0:N].astype(F32) + 0.5
    zw = crimp * np.cos(np.pi * (y / (N / ny) - 0.5) + np.pi * warp["idx"])
    zf = -crimp * np.cos(np.pi * (x / (N / nx) - 0.5) + np.pi * weft["idx"])
    hw = np.where(warp["alpha"] > 0.02, zw + warp["prof"] * warp["thick"] * 0.5, -9)
    hf = np.where(weft["alpha"] > 0.02, zf + weft["prof"] * weft["thick"] * 0.5, -9)
    top_warp = hw >= hf
    h = np.maximum(hw, hf)
    cover = 1 - (1 - warp["alpha"]) * (1 - weft["alpha"])
    h = np.where(cover > 0.02, h, -crimp - 0.2)
    return dict(h=h, cover=cover, top_warp=top_warp, warp=warp, weft=weft)


def tex_linen(N, px, rng):
    """Sheer linen, ~16 x 15 threads/cm: irregular slubby yarns with gaps between them (the opacity map)."""
    mm = 0.001 / px
    nx, ny = 128, 120
    state = rng.bit_generator.state
    cov = 0.42
    for _ in range(4):  # set the thread cover so that ~35 % of the cloth is open
        rng.bit_generator.state = state
        wv = plain_weave(rng, N, nx, ny, (cov, cov * 1.05), (0.9, 1.2), (0.1, 0.16), 6 * mm, 4 * mm)
        open_ = 1 - wv["cover"].mean()
        cov += (open_ - 0.35) * 0.6
    shp = (N, N)
    tw = rng.normal(0, 1, nx)
    tf = rng.normal(0, 1, ny)
    t = np.where(wv["top_warp"], tw[wv["warp"]["idx"] % nx], tf[wv["weft"]["idx"] % ny])
    fib = np.where(wv["top_warp"], gnoise(rng, shp, 0.25, 4), gnoise(rng, shp, 4, 0.25))
    thick = np.where(wv["top_warp"], wv["warp"]["thick"], wv["weft"]["thick"])
    v = 1 + 0.035 * t + 0.035 * fib + 0.03 * (thick - 1) + 0.04 * np.clip(wv["h"], -0.5, 1)
    c = col((234, 228, 215))[None, None] * v[..., None]
    c[..., 2] *= 1 - 0.01 * t
    # the open gaps take the mean thread colour so a cut-out edge never shows a dark fringe
    m = wv["cover"] > 0.5
    mean = c[m].mean(0)
    c = lerp(mean, c, sstep(0.0, 0.5, wv["cover"]))
    A = match_mean(c, (232, 226, 212), m)
    fuzz = sstep(1.6, 2.4, gnoise(rng, shp, 0.9)) * 0.35
    O = np.clip(wv["cover"] + fuzz * (1 - wv["cover"]) * sstep(0.0, 0.3, ndi.uniform_filter(wv["cover"], 5, mode="wrap")), 0, 1)
    H = (wv["h"] * 0.11e-3 + 4e-6 * fib).astype(F32)
    R = 0.82 + 0.04 * fib - 0.03 * wv["h"]
    print(f"  Linen: open area {100 * (1 - O.mean()):.1f} %  (thread cover {cov:.2f})")
    return dict(A=A, H=H, R=np.clip(R, 0.75, 0.92), O=O)


def tex_bookcloth(N, px, rng):
    """Dark green book cloth: a fine (~24/cm) plain weave filled and coated, the thread crowns a touch lighter."""
    shp = (N, N)
    mm = 0.001 / px
    wv = plain_weave(rng, N, 240, 216, (0.92, 0.98), (0.35, 0.5), (0.06, 0.1), 3 * mm, 3 * mm, crimp=0.3)
    t = np.where(wv["top_warp"], rng.normal(0, 1, 240)[wv["warp"]["idx"] % 240], rng.normal(0, 1, 216)[wv["weft"]["idx"] % 216])
    fib = np.where(wv["top_warp"], gnoise(rng, shp, 0.3, 3), gnoise(rng, shp, 3, 0.3))
    hn = np.clip((wv["h"] + 0.4) / 1.2, 0, 1)
    mott = gnoise(rng, shp, 4 * mm)
    v = 1 + 0.05 * t + 0.04 * fib + 0.14 * (hn - 0.5) + 0.04 * mott
    c = col((33, 60, 46))[None, None] * v[..., None]
    A = match_mean(c, (33, 60, 46))
    H = wv["h"] * 0.05e-3 + 2e-6 * fib + 8e-6 * mott
    R = 0.7 - 0.08 * (hn - 0.5) + 0.03 * fib
    return dict(A=A, H=H, R=np.clip(R, 0.58, 0.8))


def tex_wool(N, px, rng):
    """A cream chunky wool loop-pile (berber) rug: rows of plump loops of two-ply yarn along u, packed tight, their
    twist and stray fibres visible, a heather of darker fibres here and there, the crevices shadowed."""
    shp = (N, N)
    mm = 0.001 / px
    nrow, nloop = 96, 110  # 6.25 mm rows, 5.45 mm loops
    pv, pu = N / nrow, N / nloop
    y, x = np.mgrid[0:N, 0:N].astype(F32) + 0.5
    yr = y - 0.18 * pv * gnoise(rng, shp, 40 * mm, 60 * mm)  # rows wander
    xr = x + 0.12 * pu * gnoise(rng, shp, 30 * mm, 20 * mm)
    edge = gnoise(rng, shp, 1.4)  # stray fibres break up each loop's outline
    off = rng.uniform(0, pu, nrow)
    jx, jy = rng.normal(0, 0.1 * pu, (nrow, nloop)), rng.normal(0, 0.1 * pv, (nrow, nloop))
    half = rng.uniform(0.3, 0.42, (nrow, nloop)) * pu  # half length of the loop's crown
    rad = rng.uniform(0.36, 0.46, (nrow, nloop)) * pv  # yarn radius (~2.5 mm)
    ht = rng.uniform(0.8, 1.15, (nrow, nloop))
    rot = rng.normal(0, 0.22, (nrow, nloop))
    ply = rng.uniform(0, 6.3, (nrow, nloop))
    tone = rng.normal(0, 1, (nrow, nloop))
    best = np.full(shp, -1.0, F32)
    bid = np.zeros(shp, np.int64)
    btw = np.zeros(shp, F32)
    r0 = np.floor(yr / pv).astype(int)
    for dr in (-1, 0, 1):
        ri = r0 + dr
        rk = ri % nrow
        c0 = np.floor((xr - off[rk]) / pu).astype(int)
        for dc in (-1, 0, 1):
            ci = c0 + dc
            ck = ci % nloop
            k = (rk, ck)
            cx = off[rk] + (ci + 0.5) * pu + jx[k]
            cy = (ri + 0.5) * pv + jy[k]
            dx, dy = xr - cx, yr - cy
            cr, sr = np.cos(rot[k]), np.sin(rot[k])
            al, ac = dx * cr + dy * sr, -dx * sr + dy * cr
            hl = half[k]
            sa = np.clip(al, -hl, hl)  # capsule: distance to the crown's centre line
            dist = np.hypot(al - sa, ac) / rad[k] * (1 + 0.16 * edge)
            fall = 1 - 0.35 * (np.abs(al) / (hl + rad[k])) ** 2  # the yarn dips into the backing at both ends
            h = ht[k] * fall * np.sqrt(np.clip(1 - dist ** 2, 0, 1))
            tw = np.sin(2 * np.pi * (al + 0.9 * ac) / (2.4 * mm) + ply[k] + 0.6 * edge)  # two plies twisted
            h = h * (1 + 0.05 * tw)
            take = h > best
            best = np.where(take, h, best)
            bid = np.where(take, rk * nloop + ck, bid)
            btw = np.where(take, tw, btw)
    fuzz = gnoise(rng, shp, 0.5)
    hair = np.maximum(sstep(1.8, 2.6, gnoise(rng, shp, 4.5, 0.6, angle=rng.uniform(0, 3))),
                      sstep(1.8, 2.6, gnoise(rng, shp, 4.5, 0.6, angle=rng.uniform(0, 3))))
    hn = np.maximum(np.clip(best, 0, None), 0.12 + 0.05 * fuzz)  # dense pile: no backing shows between loops
    ao = 0.7 + 0.3 * sstep(0.1, 0.7, hn)
    v = (1 + 0.03 * tone.ravel()[bid] + 0.03 * btw + 0.06 * fuzz + 0.1 * hair) * ao
    c = col((228, 218, 198))[None, None] * v[..., None]
    heather = np.zeros(shp, F32)
    for _ in range(4):  # short darker fibres spun into the yarn, in all directions
        heather = np.maximum(heather, sstep(2.5, 3.1, gnoise(rng, shp, 5, 0.7, angle=rng.uniform(0, 3.2))))
    heather *= sstep(-0.5, 1.0, gnoise(rng, shp, 30 * mm))
    c = lerp(c, col((150, 132, 110)) * ao[..., None], heather * 0.5)
    A = match_mean(c, (214, 202, 180))
    H = hn * 4.0e-3 + 0.12e-3 * fuzz + 0.2e-3 * hair
    R = 0.95 - 0.03 * sstep(0.3, 1.0, hn) + 0.02 * fuzz
    return dict(A=A, H=H, R=np.clip(R, 0.88, 1.0), nscale=0.3)


def tex_felt(N, px, rng):
    """Black needle-punched acoustic felt: a dense mat of fine fibres, faint mottling, fully matte."""
    shp = (N, N)
    mm = 0.001 / px
    fib = np.zeros(shp, F32)
    light = np.zeros(shp, F32)
    for k in range(10):
        f = sstep(1.7, 2.5, gnoise(rng, shp, 3.5 * mm, 0.22 * mm, angle=rng.uniform(0, math.pi)))
        fib = np.maximum(fib, f)
        if k < 3:
            light = np.maximum(light, f)
    mott = gnoise(rng, shp, 12 * mm) + 0.5 * gnoise(rng, shp, 3 * mm)
    grain = gnoise(rng, shp, 0.6)
    pits = sstep(2.0, 2.6, gnoise(rng, shp, 0.5 * mm))  # needle-punch holes
    v = 1 + 0.035 * mott + 0.06 * grain + 0.1 * fib + 0.12 * light - 0.12 * pits
    c = col((31, 31, 33))[None, None] * v[..., None]
    A = match_mean(c, (31, 31, 33))
    H = 12e-6 * fib + 8e-6 * grain + 8e-6 * gnoise(rng, shp, 2 * mm) + 15e-6 * mott - 15e-6 * pits
    R = 0.94 - 0.03 * fib + 0.02 * grain
    return dict(A=A, H=H, R=np.clip(R, 0.88, 1.0))


def tex_fleece(N, px, rng):
    """Black cotton jersey knit: columns (wales, along v) of V-shaped stitches, ~14 wales and 18 courses per cm,
    with a brushed cotton fuzz over it."""
    shp = (N, N)
    nw, nc = 140, 180
    pw, pc = N / nw, N / nc
    y, x = np.mgrid[0:N, 0:N].astype(F32) + 0.5
    jx, jy = rng.normal(0, 0.05 * pw, (nc, nw)), rng.normal(0, 0.05 * pc, (nc, nw))
    tone = rng.normal(0, 1, (nc, nw))
    best = np.full(shp, -1.0, F32)
    btone = np.zeros(shp, F32)
    blong = np.zeros(shp, F32)
    w0, c0 = np.floor(x / pw).astype(int), np.floor(y / pc).astype(int)
    ang = 0.42
    for dc in (-1, 0, 1):
        ci = c0 + dc
        for dw in (-1, 0, 1):
            wi = w0 + dw
            ck, wk = ci % nc, wi % nw
            for leg in (-1, 1):
                cx = (wi + 0.5) * pw + leg * 0.24 * pw + jx[ck, wk]
                cy = (ci + 0.5) * pc + jy[ck, wk]
                tx, ty = -leg * math.sin(ang), math.cos(ang)
                dx, dy = x - cx, y - cy
                al, ac = dx * tx + dy * ty, -dx * ty + dy * tx
                rho2 = (al / (0.72 * pc)) ** 2 + (ac / (0.27 * pw)) ** 2
                h = np.clip(1 - rho2, 0, 1) ** 0.5 * (1 + 0.04 * leg)
                take = h > best
                best = np.where(take, h, best)
                btone = np.where(take, tone[ck, wk], btone)
                blong = np.where(take, al / pc, blong)
    hn = np.clip(best, 0, None)
    fuzz = gnoise(rng, shp, 0.7)
    hair = np.maximum(sstep(1.9, 2.6, gnoise(rng, shp, 6, 0.5, angle=rng.uniform(0, 3))),
                      sstep(1.9, 2.6, gnoise(rng, shp, 6, 0.5, angle=rng.uniform(0, 3))))
    v = (0.75 + 0.35 * hn) * (1 + 0.05 * btone + 0.08 * fuzz) + 0.5 * hair
    c = col((22, 22, 24))[None, None] * v[..., None]
    A = match_mean(c, (22, 22, 24))
    H = hn * 0.12e-3 + 6e-6 * fuzz + 8e-6 * hair + 20e-6 * gnoise(rng, shp, 30)
    R = 0.86 - 0.05 * hn + 0.03 * fuzz
    return dict(A=A, H=H, R=np.clip(R, 0.75, 0.95))


# --------------------------------------------------------------------------- hard surfaces

def voronoi_edges(rng, N, n, jitter=2.0):
    """F2 - F1 (px) of a periodic Voronoi diagram of n random seeds, sampled at slightly warped pixel centres."""
    pts = rng.random((n, 2)) * N
    tree = cKDTree(pts, boxsize=N)
    y, x = np.mgrid[0:N, 0:N].astype(F32) + 0.5
    shp = (N, N)
    y = (y + jitter * gnoise(rng, shp, 6)) % N
    x = (x + jitter * gnoise(rng, shp, 6)) % N
    d, i = tree.query(np.stack([x.ravel(), y.ravel()], 1), k=2, workers=-1)
    return (d[:, 1] - d[:, 0]).reshape(shp).astype(F32), d[:, 0].reshape(shp).astype(F32), i[:, 0].reshape(shp)


def tex_leather(N, px, rng):
    """Black protein (PU) leather for headphone pads: a fine pebble grain of ~0.9 mm rounded cells with soft valleys
    between them, a smaller grain inside, a satin sheen on the crowns."""
    shp = (N, N)
    mm = 0.001 / px
    eb, f1b, _ = voronoi_edges(rng, N, int((N / (0.9 * mm)) ** 2), 1.6)
    es, _, _ = voronoi_edges(rng, N, int((N / (0.35 * mm)) ** 2), 0.8)
    hb = sstep(0, 4.5, eb) ** 0.7  # rounded crowns, soft valleys
    hs = sstep(0, 2.0, es)
    micro = gnoise(rng, shp, 0.8)
    H = 12e-6 * hb + 2.5e-6 * hs + 1.5e-6 * micro + 20e-6 * gnoise(rng, shp, 30 * mm)
    v = 1 + 0.05 * (hb - 0.7) + 0.03 * micro
    c = col((19, 19, 20))[None, None] * v[..., None]
    A = match_mean(c, (19, 19, 20))
    R = 0.44 - 0.06 * (hb - 0.7) - 0.02 * hs + 0.012 * micro + 0.02 * gnoise(rng, shp, 15 * mm)
    return dict(A=A, H=H, R=np.clip(R, 0.32, 0.58))


def tex_stoneware(N, px, rng):
    """Cream stoneware glaze: iron speckles 0.5-2 mm with a faint bleed, glaze pooling (thick = creamier and
    glossier, thin = the warmer clay showing), a soft orange-peel surface."""
    shp = (N, N)
    mm = 0.001 / px
    thick = 0.8 * gnoise(rng, shp, 22 * mm) + 0.4 * gnoise(rng, shp, 8 * mm)
    thick = thick / thick.std()
    core = np.zeros(shp, F32)
    halo = np.zeros(shp, F32)
    n = int(2.2 * (N * px * 100) ** 2)  # ~2 per cm2
    for _ in range(n):
        d = 0.5 * mm * (4.0 ** rng.random() ** 1.8)  # 0.5-2 mm, most small
        r = d / 2
        s = int(r * 4) + 5
        yy, xx = np.mgrid[0:s, 0:s].astype(F32) - s // 2 + rng.uniform(-0.5, 0.5, 2)[:, None, None]
        th = np.arctan2(yy, xx)
        rr = np.hypot(yy, xx) / (r * (1 + 0.1 * np.sin(2 * th + rng.uniform(0, 6)) + 0.07 * np.sin(3 * th + rng.uniform(0, 6)) + 0.05 * np.sin(5 * th + rng.uniform(0, 6))))
        cy, cx = rng.random(2) * N
        splat(core, cy, cx, (1 - sstep(0.75, 1.15, rr)).astype(F32), "max")
        splat(halo, cy, cx, (np.exp(-((rr / 1.9) ** 2)) * rng.uniform(0.4, 1)).astype(F32), "max")
    peel = gnoise(rng, shp, 1.2 * mm)
    c = lerp(col((236, 226, 204)), col((214, 196, 166)), sstep(-0.5, -2.2, thick) * 0.45)
    c = c * (1 + 0.012 * thick + 0.01 * gnoise(rng, shp, 0.8 * mm))[..., None]
    c = lerp(c, col((180, 146, 108)), halo * 0.22)
    c = lerp(c, col((58, 40, 28)), core)
    A = match_mean(c, (228, 216, 194))
    H = 12e-6 * peel + 60e-6 * gnoise(rng, shp, 8 * mm) + 25e-6 * thick / 3 + 10e-6 * core
    R = 0.36 - 0.05 * np.clip(thick, -2, 2) + 0.12 * core + 0.015 * peel
    return dict(A=A, H=H, R=np.clip(R, 0.22, 0.55))


def tex_brushed(N, px, rng):
    """Brushed metal: neutral base colour of 0.6 linear (sRGB ~203), roughness and fine relief streaked along u, a
    few longer scratches."""
    shp = (N, N)
    mm = 0.001 / px
    st = (0.6 * gnoise(rng, shp, 60 * mm, 0.05 * mm) + 0.5 * gnoise(rng, shp, 20 * mm, 0.1 * mm)
          + 0.35 * gnoise(rng, shp, 8 * mm, 0.3 * mm) + 0.25 * gnoise(rng, shp, 80 * mm, 2 * mm))
    st /= st.std()
    scratch = sstep(2.4, 3.2, gnoise(rng, shp, 60 * mm, 0.06 * mm, angle=rng.normal(0, 0.02)))
    lf = gnoise(rng, shp, 30 * mm, 10 * mm)
    fine = gnoise(rng, shp, 40 * mm, 0.05 * mm)
    a = 0.6 * (1 + 0.015 * st + 0.01 * lf + 0.03 * scratch)
    A = np.repeat(a[..., None], 3, -1).astype(F32)
    H = 0.5e-6 * fine + 0.25e-6 * st + 1.2e-6 * scratch
    R = 0.3 + 0.02 * fine + 0.012 * st + 0.015 * lf + 0.05 * scratch
    return dict(A=A, H=H, R=np.clip(R, 0.18, 0.48))


GEN = {
    "Limewash": tex_limewash, "OakFloor": tex_oakfloor, "Oak": tex_oak, "OakEnd": tex_oakend, "Walnut": tex_walnut,
    "Linen": tex_linen, "Wool": tex_wool, "Felt": tex_felt, "Stoneware": tex_stoneware, "BookCloth": tex_bookcloth,
    "Fleece": tex_fleece, "Leather": tex_leather, "Brushed": tex_brushed,
}


# --------------------------------------------------------------------------- output

def to8(x, rng):
    """0..1 floats to 8 bits with a triangular dither, so the soft gradients do not band."""
    d = rng.random(x.shape, dtype=F32) - rng.random(x.shape, dtype=F32)
    return np.clip(np.round(x * 255 + d), 0, 255).astype(np.uint8)


def save(name, t, px, rng):
    OUT.mkdir(parents=True, exist_ok=True)
    A = lin2srgb(t["A"])
    N = normal_dx(t["H"].astype(F32) * t.get("nscale", 1.0), px)
    Image.fromarray(to8(A, rng), "RGB").save(OUT / f"T_{name}_A.png", optimize=True)
    Image.fromarray(np.clip(np.round(N * 255), 0, 255).astype(np.uint8), "RGB").save(OUT / f"T_{name}_N.png", optimize=True)
    Image.fromarray(to8(np.asarray(t["R"], F32), rng), "L").save(OUT / f"T_{name}_R.png", optimize=True)
    if "O" in t:
        Image.fromarray(to8(np.asarray(t["O"], F32), rng), "L").save(OUT / f"T_{name}_O.png", optimize=True)
    m = A.reshape(-1, 3).mean(0) * 255
    r = np.asarray(t["R"])
    tilt = np.degrees(np.arccos(np.clip(N[..., 2] * 2 - 1, -1, 1)))
    print(f"  {name}: mean sRGB {m.round().astype(int).tolist()}  roughness {r.min():.2f}..{r.max():.2f} "
          f"(mean {r.mean():.2f})  normal tilt median {np.median(tilt):.1f}, p99 {np.percentile(tilt, 99):.1f} deg")


def shaded(name, size):
    """The albedo lit by its normal map from the upper left at a low angle, for the contact sheet."""
    A = srgb2lin(np.asarray(Image.open(OUT / f"T_{name}_A.png"), F32) / 255)
    n = np.asarray(Image.open(OUT / f"T_{name}_N.png"), F32) / 255 * 2 - 1  # DirectX: +y is down the image
    L = np.array([-0.55, -0.55, 0.45], F32)
    L /= np.linalg.norm(L)
    s = np.clip((n @ L) / L[2], 0, 3) * 0.75 + 0.25
    img = lin2srgb(A * s[..., None])
    if (OUT / f"T_{name}_O.png").exists():
        o = np.asarray(Image.open(OUT / f"T_{name}_O.png"), F32)[..., None] / 255
        img = img * o + 0.18 * (1 - o)
    im = Image.fromarray((img * 255).astype(np.uint8))
    im = im.resize((size // 2, size // 2), Image.LANCZOS)
    tile = Image.new("RGB", (size, size))
    for i in range(2):
        for j in range(2):
            tile.paste(im, (i * size // 2, j * size // 2))
    return tile


def font(sz):
    for f in ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              str(HERE.parents[1] / "fonts" / "src" / "Geist[wght].ttf")):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def contact_sheet():
    names = [n for n in SPECS if (OUT / f"T_{n}_A.png").exists()]
    cell, lab, cols = 600, 46, 5
    rows = math.ceil(len(names) / cols)
    sheet = Image.new("RGB", (cols * cell, rows * (cell + lab)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    f = font(26)
    for k, n in enumerate(names):
        x, y = (k % cols) * cell, (k // cols) * (cell + lab)
        sheet.paste(shaded(n, cell - 8), (x + 4, y + 4))
        px, m = SPECS[n]
        d.text((x + 10, y + cell + 4), f"{n}   2x2 of {m * 100:g} cm ({px}px)", fill=(230, 230, 230), font=f)
    sheet.save(OUT / "contact.png", optimize=True)
    print(OUT / "contact.png")


def preview_sheet(src):
    """preview_<Name>.png: the 1 m plane and rounded box beside a close-up, from the Blender renders in src."""
    src = Path(src)
    f = font(30)
    for n in SPECS:
        wide, close = src / f"{n}_wide.png", src / f"{n}_close.png"
        if not (wide.exists() and close.exists()):
            continue
        a, b = Image.open(wide).convert("RGB"), Image.open(close).convert("RGB")
        im = Image.new("RGB", (a.width + b.width, a.height + 50), (24, 24, 24))
        im.paste(a, (0, 50))
        im.paste(b, (a.width, 50))
        px, m = SPECS[n]
        ImageDraw.Draw(im).text((14, 8), f"{n}: covers {m * 100:g} cm.  Left: 1 x 1 m plane, rounded box 40 x 25 x 12 cm."
                                f"  Right: close-up ~{close_width(m) * 100:.0f} cm wide", fill=(230, 230, 230), font=f)
        im.save(OUT / f"preview_{n}.png", optimize=True)
        print(OUT / f"preview_{n}.png")


def close_width(cover):
    return float(np.clip(1.6 * cover, 0.07, 0.45))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--sheet", default=None, help="compose preview_<Name>.png from Blender renders in this directory")
    ap.add_argument("--no-contact", action="store_true")
    a = ap.parse_args(argv)
    if a.sheet:
        preview_sheet(a.sheet)
        return
    for k, name in enumerate(SPECS):
        if a.only and name not in a.only:
            continue
        N, L = SPECS[name]
        rng = np.random.default_rng(1000 + k)
        print(f"{name}: {N}px over {L * 100:g} cm ({L / N * 1000:.3f} mm/px)", flush=True)
        save(name, GEN[name](N, L / N, rng), L / N, rng)
    if not a.no_contact:
        contact_sheet()


# --------------------------------------------------------------------------- Blender previews

def blender_preview(argv):
    import bpy
    import bmesh
    from mathutils import Vector

    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--tex", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--samples", type=int, default=128)
    ap.add_argument("--res", type=int, default=900)
    a = ap.parse_args(argv)
    tex = Path(a.tex)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    sc = bpy.context.scene

    def mesh_obj(bm, name):
        # world-scale UVs: each face projected on the axis plane it faces most, in metres
        uv = bm.loops.layers.uv.verify()
        for face in bm.faces:
            nx, ny, nz = (abs(c) for c in face.normal)
            for lp in face.loops:
                co = lp.vert.co
                if nz >= nx and nz >= ny:
                    lp[uv].uv = (co.x, co.y)
                elif nx >= ny:
                    lp[uv].uv = (co.y if face.normal.x > 0 else -co.y, co.z)
                else:
                    lp[uv].uv = (-co.x if face.normal.y > 0 else co.x, co.z)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        sc.collection.objects.link(ob)
        for p in me.polygons:
            p.use_smooth = True
        return ob

    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    plane = mesh_obj(bm, "plane")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= 0.40
        v.co.y *= 0.25
        v.co.z *= 0.12
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.018, segments=6, profile=0.5, affect="EDGES")
    for v in bm.verts:
        v.co += Vector((-0.17, -0.2, 0.06 + 0.0005))
    box = mesh_obj(bm, "box")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=20)
    for v in bm.verts:
        v.co.z = -0.04
    ground = mesh_obj(bm, "ground")
    gm = bpy.data.materials.new("ground")
    gm.use_nodes = True
    gb = gm.node_tree.nodes["Principled BSDF"]
    gb.inputs["Base Color"].default_value = (0.05, 0.05, 0.05, 1)
    gb.inputs["Roughness"].default_value = 0.8
    ground.data.materials.append(gm)

    world = bpy.data.worlds.new("w")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.20, 0.19, 0.18, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    key = bpy.data.lights.new("key", "AREA")
    key.shape = "DISK"
    key.size = 0.9
    key.energy = 700
    key.color = (1.0, 0.93, 0.85)  # a little warm, as the studio's lamps
    kd = Vector((0.45, 1.0, 0.26)).normalized()  # from the right, ~13 degrees above the plane: grazing
    ko = bpy.data.objects.new("key", key)
    sc.collection.objects.link(ko)
    ko.location = kd * 3.2
    ko.rotation_euler = (-kd).to_track_quat("-Z", "Y").to_euler()

    cam_d = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam_d.clip_start = 0.005

    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = a.samples
    for attr in ("use_shadows", "use_raytracing"):
        if hasattr(sc.eevee, attr):
            setattr(sc.eevee, attr, True)
    for attr, val in (("shadow_ray_count", 4), ("shadow_step_count", 16)):
        if hasattr(sc.eevee, attr):
            setattr(sc.eevee, attr, val)
    if hasattr(key, "use_shadow_jitter"):
        key.use_shadow_jitter = True
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    sc.render.resolution_x = sc.render.resolution_y = a.res
    sc.render.image_settings.file_format = "PNG"

    def look(target, direction, width, lens=50.0):
        cam_d.lens = lens
        d = width * lens / 36.0
        dv = Vector(direction).normalized()
        cam.location = Vector(target) + dv * d
        cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()

    for name, (px, cover) in SPECS.items():
        if a.only and name not in a.only:
            continue
        m = bpy.data.materials.new("M_" + name)
        m.use_nodes = True
        nt = m.node_tree
        bsdf = nt.nodes["Principled BSDF"]
        uvn = nt.nodes.new("ShaderNodeUVMap")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1 / cover, 1 / cover, 1)
        nt.links.new(uvn.outputs["UV"], mp.inputs["Vector"])

        def img(suffix, noncolor):
            n = nt.nodes.new("ShaderNodeTexImage")
            n.image = bpy.data.images.load(str(tex / f"T_{name}_{suffix}.png"))
            if noncolor:
                n.image.colorspace_settings.name = "Non-Color"
            nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
            return n

        nt.links.new(img("A", False).outputs["Color"], bsdf.inputs["Base Color"])
        nt.links.new(img("R", True).outputs["Color"], bsdf.inputs["Roughness"])
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        comb = nt.nodes.new("ShaderNodeCombineColor")
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(img("N", True).outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs[0], comb.inputs[0])
        nt.links.new(sep.outputs[1], inv.inputs[1])  # DirectX green down -> Blender's OpenGL green up
        nt.links.new(inv.outputs[0], comb.inputs[1])
        nt.links.new(sep.outputs[2], comb.inputs[2])
        nt.links.new(comb.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        bsdf.inputs["Metallic"].default_value = 1.0 if name in METALLIC else 0.0
        if (tex / f"T_{name}_O.png").exists():
            nt.links.new(img("O", True).outputs["Color"], bsdf.inputs["Alpha"])
            if hasattr(m, "use_transparent_shadow"):
                m.use_transparent_shadow = True
        for ob in (plane, box):
            ob.data.materials.clear()
            ob.data.materials.append(m)

        look((0.0, 0.0, 0.03), (1.0, 0.75, 0.85), 1.35)
        sc.render.filepath = str(out / f"{name}_wide.png")
        bpy.ops.render.render(write_still=True)
        w = close_width(cover)
        # close-up on the box's front-right top corner, the lit side and the plane beside it
        look((0.03 - w * 0.05, -0.075 + w * 0.12, 0.12 - w * 0.18), (1.0, 0.8, 0.65), w)
        sc.render.filepath = str(out / f"{name}_close.png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
    except ImportError:
        main()
    else:
        blender_preview(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
