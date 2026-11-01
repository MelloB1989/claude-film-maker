"""pothos_trailing: a golden pothos in a cream ceramic pot on the top shelf, vines trailing down.

    blender -b --factory-startup -P films/host-studio/props/pothos_trailing.py -- --out films/host-studio/props/out

Frame (cm in this file, 1 Blender unit = 1 m in the FBX): origin = top surface of the top shelf at
its left end, back edge (x = 0 wall, y = 0 left end, z = 0 shelf top).  +X towards the camera, +Y
screen-right seen from +X.  The shelves (150 x 26 x 4.5, tops at z = 0, -37, -74, -111) are
colliders only and are not exported.  The pot is centred at (14, 14).

Writes <out>/pothos_trailing.fbx, <out>/T_PothosLeaf.png (1024 px leaf texture), previews
pothos_trailing.png, pothos_trailing_front.png, pothos_on_shelves.png, pothos_trailing_close.png and
pothos_leaf_close.png.  Seeded (--seed): a run is reproducible.
"""
import argparse
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

NAME = "pothos_trailing"
CM = 0.01
UVN = "UVMap"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--texture-only", action="store_true")
    ap.add_argument("--only", default="", help="comma list of previews to render (default all)")
    return ap.parse_args(argv)


# =========================================================================== leaf outline
# Normalised leaf (length 1, base/petiole at the origin, tip at +y): a cordate margin in polar form,
# r(theta) through control points (smoothed with a monotone cubic), theta = 0 at the tip.
W0 = 0.92                      # nominal width factor baked into the outline (and the texture)
TH_MAX = math.radians(166)     # the lobes end here, behind the petiole; the sinus runs back to the origin
_CTRL = [(0, 1.0), (5, 0.945), (12, 0.83), (22, 0.715), (36, 0.635), (55, 0.565), (75, 0.52),
         (95, 0.50), (115, 0.47), (135, 0.43), (152, 0.38), (166, 0.31)]


def _monotone_table(ctrl, n=2000):
    xs = [math.radians(a) for a, _ in ctrl]
    ys = [r for _, r in ctrl]
    h = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(len(h))]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else 2 / (1 / d[i - 1] + 1 / d[i]) for i in range(1, len(d))] + [d[-1]]
    tab_t, tab_r = [], []
    for k in range(n + 1):
        t = TH_MAX * k / n
        i = min(max(sum(1 for x in xs[1:] if x <= t), 0), len(h) - 1)
        u = (t - xs[i]) / h[i]
        h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
        tab_t.append(t)
        tab_r.append(h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1])
    return np.array(tab_t), np.array(tab_r)


_TT, _TR = _monotone_table(_CTRL)


def margin_r(th):
    return float(np.interp(abs(th), _TT, _TR))


def margin_r_np(th):
    return np.interp(np.abs(th), _TT, _TR)


def _bounds():
    xs, ys = [], []
    for k in range(721):
        th = -TH_MAX + 2 * TH_MAX * k / 720
        r = margin_r(abs(th))
        xs.append(W0 * r * math.sin(th))
        ys.append(r * math.cos(th))
    return min(xs), max(xs), min(ys), max(ys)


XMIN, XMAX, YMIN, YMAX = _bounds()


# =========================================================================== leaf texture
def _smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _vnoise(g, x, y):
    n = g.shape[0]
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx = x - x0
    fy = y - y0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    xi = x0.astype(np.int64) % n
    yi = y0.astype(np.int64) % n
    xj = (xi + 1) % n
    yj = (yi + 1) % n
    return (g[yi, xi] * (1 - fx) * (1 - fy) + g[yi, xj] * fx * (1 - fy)
            + g[yj, xi] * (1 - fx) * fy + g[yj, xj] * fx * fy)


def _fbm(grids, x, y, base, octaves, gain=0.5):
    tot = np.zeros_like(x)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        f = base * (2 ** o)
        tot += amp * _vnoise(grids[o], x * f, y * f)
        norm += amp
        amp *= gain
    return tot / norm


def _blur(a, sigma):
    rad = int(sigma * 3) + 1
    k = np.exp(-0.5 * (np.arange(-rad, rad + 1) / sigma) ** 2)
    k /= k.sum()
    out = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, a)
    return np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), 0, out)


def leaf_texture_pixels(size=1024, seed=11):
    """A pothos leaf, top side, in the leaf's UV frame: green with golden-cream variegation and veins.

    Returns float32 (size, size, 3) sRGB 0..1, row 0 = v 0 (bottom of the UV square)."""
    rs = np.random.default_rng(seed)
    N = size
    grids = [rs.random((96, 96)) for _ in range(8)]
    c = (np.arange(N) + 0.5) / N
    U, V = np.meshgrid(c, c)
    xn = XMIN + U * (XMAX - XMIN)
    yn = YMIN + V * (YMAX - YMIN)
    rx = xn / W0
    th = np.arctan2(rx, yn)
    r = np.hypot(rx, yn)
    R = margin_r_np(np.clip(np.abs(th), 0, TH_MAX))
    inside = (np.abs(th) <= TH_MAX) & (r <= R)
    edge = np.clip((R - r) / 0.10, 0, 1)          # 0 at the margin, 1 well inside

    # organic warp
    wx = (_fbm(grids[:3], U, V, 3, 3) - 0.5) * 0.14
    wy = (_fbm(grids[3:6], U + 7.3, V + 3.1, 3, 3) - 0.5) * 0.14
    Uw, Vw = U + wx, V + wy

    # variegation: splashes + streaks that radiate from the base along the veins, more at the margin
    ax_ = np.abs(xn)
    side = (xn < 0) * 3.7
    sa, ca = math.sin(math.radians(56)), math.cos(math.radians(56))
    along = ax_ * sa + yn * ca
    across = ax_ * ca - yn * sa + side
    streak = _fbm(grids, along * 1.0 + 1.0, across * 4.5 + 2.0, 1.0, 3)       # streaks parallel to the veins
    streak2 = _fbm(grids, along * 2.0 + 5.0, across * 9.0 + 7.0, 1.0, 2)
    sp = _fbm(grids, Uw + 1.7, Vw + 4.2, 2.2, 4)
    s = (0.60 * sp + 0.32 * streak + 0.12 * streak2
         + 0.12 * (1 - edge) * (0.4 + 0.6 * _fbm(grids, Uw + 3, Vw + 5, 5.0, 2))
         - 0.25 * np.exp(-(xn / 0.05) ** 2))
    q = np.quantile(s[inside], 1 - 0.25)
    A1 = _smooth(q - 0.030, q - 0.004, s)          # yellow-green
    A2 = _smooth(q - 0.004, q + 0.016, s)          # gold
    Cc = _smooth(q + 0.075, q + 0.14, s)           # pale cream core of a splash
    # fine pale speckles: round dots (not noise blobs), denser near the edge of a splash
    dots = np.zeros((N, N), np.float32)
    nd = 5200
    dx = rs.random(nd)
    dy = rs.random(nd)
    px_, py_ = (dx * N).astype(int), (dy * N).astype(int)
    near = _smooth(q - 0.22, q - 0.02, s[py_, px_])
    keep = (rs.random(nd) < 0.015 + 0.45 * near) & inside[py_, px_]
    np.add.at(dots, (py_[keep], px_[keep]), rs.uniform(0.5, 1.5, keep.sum()))
    dots = _smooth(0.10, 0.16, _blur(dots, 2.4) * 16.0)
    fleck = dots * (1 - A2)

    g_lo = np.array([18, 54, 14]) / 255.0
    g_hi = np.array([44, 92, 26]) / 255.0
    lime = np.array([120, 142, 38]) / 255.0
    gold = np.array([212, 156, 26]) / 255.0
    cream = np.array([224, 186, 76]) / 255.0
    mixg = np.clip(0.30 + 1.5 * (_fbm(grids, Uw + 6, Vw + 8, 6.0, 3) - 0.5) + 0.30 * (1 - edge), 0, 1)
    col = g_lo[None, None, :] * (1 - mixg[..., None]) + g_hi[None, None, :] * mixg[..., None]
    col = col * (1 - A1[..., None]) + lime[None, None, :] * A1[..., None]
    col = col * (1 - A2[..., None]) + gold[None, None, :] * A2[..., None]
    col = col * (1 - 0.4 * Cc[..., None]) + cream[None, None, :] * (0.4 * Cc[..., None])
    col = col * (1 - 0.9 * fleck[..., None]) + gold[None, None, :] * (0.9 * fleck[..., None])

    # veins: a midrib and ~7 lateral veins per side sweeping forward to the margin, then blurred
    mid = np.zeros((N, N), np.float32)
    lat = np.zeros((N, N), np.float32)

    def stamp(acc, pts, w):
        px = ((pts[:, 0] - XMIN) / (XMAX - XMIN) * N).astype(int)
        py = ((pts[:, 1] - YMIN) / (YMAX - YMIN) * N).astype(int)
        ok = (px >= 0) & (px < N) & (py >= 0) & (py < N)
        np.add.at(acc, (py[ok], px[ok]), w[ok])

    t = np.linspace(0, 1, 2400)
    stamp(mid, np.stack([np.zeros_like(t), 0.0 + 0.97 * t], 1), (1 - 0.55 * t))
    y0s = [0.0, 0.10, 0.21, 0.33, 0.46, 0.60, 0.74]
    a0s = [105, 74, 64, 58, 53, 49, 45]
    for y0, a0 in zip(y0s, a0s):
        x, y = 0.0, y0
        path = [(x, y)]
        ds = 0.0015
        for k in range(1200):
            tau = min(k * ds / 0.55, 1.0)
            ang = math.radians(a0 * (1 - 0.62 * tau ** 0.9))
            x += ds * math.sin(ang) * W0
            y += ds * math.cos(ang)
            thp = math.atan2(x / W0, y)
            if math.hypot(x / W0, y) > margin_r(abs(thp)) * 0.965:
                break
            path.append((x, y))
        pa = np.array(path)
        if len(pa) < 3:
            continue
        w = 1 - 0.65 * np.linspace(0, 1, len(pa))
        for sg in (-1, 1):
            stamp(lat, np.stack([sg * pa[:, 0], pa[:, 1]], 1), w)
    mid = _blur(mid, 3.2) * 0.95
    lat = _blur(lat, 1.7) * 2.6
    net = 1 - np.abs(2 * _fbm(grids, U + 2, V + 9, 44.0, 2) - 1)
    net = _smooth(0.85, 0.98, net) * 0.07
    vein = np.clip(mid + lat + net, 0, 1)
    vein_col = (np.array([150, 198, 100]) / 255.0)[None, None, :] * (1 - A2[..., None]) \
        + (np.array([250, 238, 168]) / 255.0)[None, None, :] * A2[..., None]
    col = col * (1 - 0.72 * vein[..., None]) + vein_col * 0.72 * vein[..., None]

    # slightly darker rim and a fine grain
    col = col * (0.84 + 0.16 * _smooth(0.0, 0.4, edge))[..., None]
    grain = 0.965 + 0.07 * _fbm(grids, U * 1.0 + 4, V + 1, 70.0, 2)
    col = np.clip(col * grain[..., None], 0, 1)
    if DEBUG_OUTLINE:
        ring = inside & ~np.roll(inside, 1, 0) | inside & ~np.roll(inside, 1, 1) | inside & ~np.roll(inside, -1, 0) | inside & ~np.roll(inside, -1, 1)
        col[ring] = (1, 0, 0)
    return col.astype(np.float32)


DEBUG_OUTLINE = False


def write_leaf_texture(path, size=1024):
    px = leaf_texture_pixels(size)
    img = bpy.data.images.new("T_PothosLeaf_gen", size, size, alpha=False)
    img.colorspace_settings.name = "Non-Color"           # raw sRGB values, written as they are
    rgba = np.ones((size, size, 4), np.float32)
    rgba[..., :3] = px
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


# =========================================================================== small geometry helpers
def frame(t, hint, roll=0.0):
    """Columns (x, tip, normal) of a leaf frame: tip along t, top face towards `hint`."""
    t = Vector(t).normalized()
    n = Vector(hint) - t * Vector(hint).dot(t)
    if n.length < 1e-6:
        n = t.orthogonal()
    n.normalize()
    if roll:
        n = Matrix.Rotation(roll, 3, t) @ n
    x = t.cross(n)
    return Matrix((x, t, n)).transposed()


def smoothstep1(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def catmull_centripetal(pts, per_cm=5):
    """Centripetal Catmull-Rom through pts (Barry-Goldman), ~per_cm samples per cm."""
    p = [Vector(q) for q in pts]
    p = [p[0] * 2 - p[1]] + p + [p[-1] * 2 - p[-2]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        t0 = 0.0
        t1 = t0 + max((p1 - p0).length, 1e-4) ** 0.5
        t2 = t1 + max((p2 - p1).length, 1e-4) ** 0.5
        t3 = t2 + max((p3 - p2).length, 1e-4) ** 0.5
        n = max(2, int((p2 - p1).length * per_cm))
        for k in range(n):
            t = t1 + (t2 - t1) * k / n
            a1 = p0 * ((t1 - t) / (t1 - t0)) + p1 * ((t - t0) / (t1 - t0))
            a2 = p1 * ((t2 - t) / (t2 - t1)) + p2 * ((t - t1) / (t2 - t1))
            a3 = p2 * ((t3 - t) / (t3 - t2)) + p3 * ((t - t2) / (t3 - t2))
            b1 = a1 * ((t2 - t) / (t2 - t0)) + a2 * ((t - t0) / (t2 - t0))
            b2 = a2 * ((t3 - t) / (t3 - t1)) + a3 * ((t - t1) / (t3 - t1))
            out.append(b1 * ((t2 - t) / (t2 - t1)) + b2 * ((t - t1) / (t2 - t1)))
    out.append(p[-2])
    return out


def resample(pts, step):
    out = [pts[0].copy()]
    acc = 0.0
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        seg = (b - a).length
        if seg < 1e-9:
            continue
        d = step - acc
        while d <= seg:
            out.append(a.lerp(b, d / seg))
            d += step
        acc = seg - (d - step)
    if (out[-1] - pts[-1]).length > step * 0.3:
        out.append(pts[-1].copy())
    return out


def cum_len(pts):
    c = [0.0]
    for i in range(1, len(pts)):
        c.append(c[-1] + (pts[i] - pts[i - 1]).length)
    return c


def at_len(pts, cum, s):
    """(position, unit tangent) at arclength s."""
    s = min(max(s, 0.0), cum[-1])
    lo, hi = 0, len(cum) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if cum[mid] <= s:
            lo = mid
        else:
            hi = mid
    seg = cum[hi] - cum[lo]
    f = 0.0 if seg < 1e-9 else (s - cum[lo]) / seg
    p = pts[lo].lerp(pts[hi], f)
    t = (pts[min(hi + 1, len(pts) - 1)] - pts[max(lo - 1, 0)])
    if t.length < 1e-9:
        t = pts[hi] - pts[lo]
    return p, t.normalized()


def bvh_of(verts, faces):
    return BVHTree.FromPolygons([tuple(v) for v in verts], faces, all_triangles=False, epsilon=0.0)


def too_close(verts, tree, d):
    for v in verts:
        if tree.find_nearest(v, d)[0] is not None:
            return True
    return False


# =========================================================================== bmesh builders (cm)
class Sink:
    """One bmesh per material (cm); scaled to metres when turned into an object."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new(UVN)

    def face(self, verts, uvs):
        try:
            f = self.bm.faces.new(verts)
        except ValueError:
            return None
        for lp, uv in zip(f.loops, uvs):
            lp[self.uv].uv = uv
        return f

    def to_object(self, name, mat):
        self.bm.transform(Matrix.Scale(CM, 4))
        return S.obj_from_bm(self.bm, name, mat)


def add_tube(sink, pts, radii, sides=7, cap_start=True, cone_end=True, vscale=CM, hint=(1, 0.3, 0.2)):
    n = len(pts)
    tans = []
    for i in range(n):
        t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        tans.append(t.normalized())
    nrm = Vector(hint) - Vector(hint).dot(tans[0]) * tans[0]
    if nrm.length < 1e-6:
        nrm = tans[0].orthogonal()
    nrm.normalize()
    cum = cum_len(pts)
    rings = []
    for i in range(n):
        t = tans[i]
        nrm = (nrm - nrm.dot(t) * t).normalized()
        b = t.cross(nrm)
        ring = []
        for k in range(sides):
            a = 2 * math.pi * k / sides
            ring.append(sink.bm.verts.new(pts[i] + (nrm * math.cos(a) + b * math.sin(a)) * radii[i]))
        rings.append(ring)
    for i in range(n - 1):
        v0, v1 = cum[i] * vscale, cum[i + 1] * vscale
        for k in range(sides):
            k2 = (k + 1) % sides
            sink.face([rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]],
                      [(k / sides, v0), ((k + 1) / sides, v0), ((k + 1) / sides, v1), (k / sides, v1)])
    if cap_start:
        ring = rings[0]
        sink.face(list(reversed(ring)), [(0.5 + 0.5 * math.cos(2 * math.pi * k / sides),
                                          0.5 + 0.5 * math.sin(2 * math.pi * k / sides)) for k in reversed(range(sides))])
    if cone_end:
        apex = sink.bm.verts.new(pts[-1] + tans[-1] * radii[-1] * 1.3)
        v1 = cum[-1] * vscale
        for k in range(sides):
            k2 = (k + 1) % sides
            sink.face([rings[-1][k], rings[-1][k2], apex], [(k / sides, v1), ((k + 1) / sides, v1), (0.5, v1 + radii[-1] * vscale)])
    else:
        ring = rings[-1]
        sink.face(ring, [(0.5 + 0.5 * math.cos(2 * math.pi * k / sides),
                          0.5 + 0.5 * math.sin(2 * math.pi * k / sides)) for k in range(sides)])
    return rings


def tube_mesh_data(pts, radii, sides=7):
    """Plain (verts, faces) of a tube for collision tests (no caps)."""
    n = len(pts)
    tans = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    nrm = tans[0].orthogonal().normalized()
    verts, faces = [], []
    for i in range(n):
        t = tans[i]
        nrm = (nrm - nrm.dot(t) * t).normalized()
        b = t.cross(nrm)
        for k in range(sides):
            a = 2 * math.pi * k / sides
            verts.append(pts[i] + (nrm * math.cos(a) + b * math.sin(a)) * radii[i])
    for i in range(n - 1):
        for k in range(sides):
            k2 = (k + 1) % sides
            faces.append((i * sides + k, i * sides + k2, (i + 1) * sides + k2, (i + 1) * sides + k))
    return verts, faces


def lathe_sink(sink, profile, segs, uvscale=CM):
    """Revolve (r, z) around the vertical axis through the origin. Quads with per-loop cylindrical UVs."""
    rings = []
    for r, z in profile:
        if r <= 1e-9:
            rings.append([sink.bm.verts.new((0, 0, z))])
        else:
            rings.append([sink.bm.verts.new((r * math.cos(2 * math.pi * k / segs),
                                             r * math.sin(2 * math.pi * k / segs), z)) for k in range(segs)])
    vs = [0.0]
    for i in range(1, len(profile)):
        vs.append(vs[-1] + math.hypot(profile[i][0] - profile[i - 1][0], profile[i][1] - profile[i - 1][1]))
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(segs):
            k2 = (k + 1) % segs
            u0, u1 = k / segs, (k + 1) / segs
            v0, v1 = vs[i] * uvscale, vs[i + 1] * uvscale
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                sink.face([a[0], b[k2], b[k]], [((u0 + u1) / 2, v0), (u1, v1), (u0, v1)])
            elif len(b) == 1:
                sink.face([a[k], a[k2], b[0]], [(u0, v0), (u1, v0), ((u0 + u1) / 2, v1)])
            else:
                sink.face([a[k], a[k2], b[k2], b[k]], [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
    return rings


# =========================================================================== the scene's world (cm)
POT_C = Vector((14.0, 14.0, 0.0))
POT_H = 16.0
SOIL_Z = 13.3

SHELF_X = (0.0, 26.0)
SHELF_Y = (0.0, 150.0)
SHELF_T = 4.5
SHELF_TOPS = (0.0, -37.0, -74.0, -111.0)
SHELF_BOXES = [((SHELF_X[0], SHELF_Y[0], z - SHELF_T), (SHELF_X[1], SHELF_Y[1], z)) for z in SHELF_TOPS]
WALL_X_LEAF = 0.30      # leaves stay this far in front of the wall plane
WALL_X_VINE = 0.65


def box_tree(lo, hi):
    lo, hi = Vector(lo), Vector(hi)
    vs = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    idx = lambda x, y, z: x * 4 + y * 2 + z   # noqa: E731
    quads = [(idx(0, 0, 0), idx(0, 0, 1), idx(0, 1, 1), idx(0, 1, 0)),
             (idx(1, 0, 0), idx(1, 1, 0), idx(1, 1, 1), idx(1, 0, 1)),
             (idx(0, 0, 0), idx(1, 0, 0), idx(1, 0, 1), idx(0, 0, 1)),
             (idx(0, 1, 0), idx(0, 1, 1), idx(1, 1, 1), idx(1, 1, 0)),
             (idx(0, 0, 0), idx(0, 1, 0), idx(1, 1, 0), idx(1, 0, 0)),
             (idx(0, 0, 1), idx(1, 0, 1), idx(1, 1, 1), idx(0, 1, 1))]
    return vs, quads


def shelves_tree():
    verts, faces = [], []
    for lo, hi in SHELF_BOXES:
        vs, qs = box_tree(lo, hi)
        o = len(verts)
        verts += vs
        faces += [tuple(i + o for i in q) for q in qs]
    return bvh_of(verts, faces)


def box_push(p, rmin):
    """Push p out of every shelf (and the wall) until it is rmin from the surface."""
    p = p.copy()
    for lo, hi in SHELF_BOXES:
        q = Vector((min(max(p.x, lo[0]), hi[0]), min(max(p.y, lo[1]), hi[1]), min(max(p.z, lo[2]), hi[2])))
        d = (p - q).length
        if d >= rmin:
            continue
        if d > 1e-9:
            p = q + (p - q) / d * rmin
        else:   # inside: leave through the nearest face
            gaps = [(p.x - lo[0], Vector((-1, 0, 0)), lo[0]), (hi[0] - p.x, Vector((1, 0, 0)), hi[0]),
                    (p.y - lo[1], Vector((0, -1, 0)), lo[1]), (hi[1] - p.y, Vector((0, 1, 0)), hi[1]),
                    (p.z - lo[2], Vector((0, 0, -1)), lo[2]), (hi[2] - p.z, Vector((0, 0, 1)), hi[2])]
            g = min(gaps, key=lambda e: e[0])
            ax = [i for i in range(3) if abs(g[1][i]) > 0][0]
            p[ax] = g[2] + g[1][ax] * rmin
    if p.x < WALL_X_VINE:
        p.x = WALL_X_VINE
    return p


# =========================================================================== the pot
POT_PROFILE = [
    (0.0, 0.0), (4.90, 0.0), (5.30, 0.14), (5.58, 0.50), (5.92, 1.5), (6.45, 3.9), (7.00, 6.7),
    (7.55, 9.8), (8.00, 12.4), (8.12, 13.3), (8.20, 13.62), (8.12, 13.95), (8.20, 14.4),
    (8.38, 15.0), (8.50, 15.45), (8.47, 15.72), (8.37, 15.90), (8.20, 15.99), (8.02, 16.0),
    (7.86, 15.96), (7.77, 15.86), (7.74, 15.68), (7.72, 14.8), (7.66, 12.4), (7.45, 10.2), (0.0, 10.0),
]


def build_pot():
    sink = Sink()
    lathe_sink(sink, POT_PROFILE, 72)
    verts, faces = [], []
    # collision copy: the outer shell (profile up to the rim top) as a lathe in plain lists
    prof = POT_PROFILE
    segs = 36
    ring_idx = []
    for r, z in prof:
        if r <= 1e-9:
            ring_idx.append([len(verts)])
            verts.append(Vector((POT_C.x, POT_C.y, z)))
        else:
            ring_idx.append([])
            for k in range(segs):
                ring_idx[-1].append(len(verts))
                verts.append(Vector((POT_C.x + r * math.cos(2 * math.pi * k / segs),
                                     POT_C.y + r * math.sin(2 * math.pi * k / segs), z)))
    for i in range(len(prof) - 1):
        a, b = ring_idx[i], ring_idx[i + 1]
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                faces.append((a[0], b[k2], b[k]))
            elif len(b) == 1:
                faces.append((a[k], a[k2], b[0]))
            else:
                faces.append((a[k], a[k2], b[k2], b[k]))
    sink.bm.transform(Matrix.Translation(POT_C))
    return sink, bvh_of(verts, faces)


def build_soil(rr):
    sink = Sink()
    R = 7.78
    prof = [(0.0, SOIL_Z + 0.25)]
    for k in range(1, 9):
        t = k / 8
        prof.append((R * t, SOIL_Z + 0.25 - 0.45 * t * t))
    prof.append((R, SOIL_Z - 0.6))
    prof.append((R - 0.02, 11.4))
    prof.append((0.0, 11.4))
    segs = 44
    lathe_sink(sink, prof, segs)
    for v in sink.bm.verts:
        if v.co.z > SOIL_Z - 0.5:
            v.co.z += rr.uniform(-0.10, 0.12)
    sink.bm.transform(Matrix.Translation(POT_C))
    return sink


# =========================================================================== leaves
SV = {3: [0.0, 0.2, 0.55, 1.0], 4: [0.0, 0.11, 0.36, 0.68, 1.0]}
TOPO = {}


def leaf_topology(nu, ns):
    """Vertex layout and face lists of the shared leaf grid. Rows 0..nu-1 are full rows of 2*ns+1
    columns; row nu is the single tip vertex."""
    key = (nu, ns)
    if key in TOPO:
        return TOPO[key]
    w = 2 * ns + 1
    tip = nu * w
    idx = lambda i, j: tip if i == nu else i * w + (j + ns)   # noqa: E731
    faces = []
    for i in range(nu):
        for j in range(-ns, ns):
            a, b, c, d = idx(i, j), idx(i, j + 1), idx(i + 1, j + 1), idx(i + 1, j)
            faces.append((a, b, c) if c == d else (a, b, c, d))
    edges = {}
    for f in faces:
        for q in range(len(f)):
            a, b = f[q], f[(q + 1) % len(f)]
            edges.setdefault((min(a, b), max(a, b)), []).append((a, b))
    boundary = [v[0] for v in edges.values() if len(v) == 1]
    tris = []
    for f in faces:
        tris.append((f[0], f[1], f[2]))
        if len(f) == 4:
            tris.append((f[0], f[2], f[3]))
    TOPO[key] = (tip + 1, faces, boundary, tris, idx)
    return TOPO[key]


class LeafShape:
    def __init__(self, rr, L):
        self.L = L
        self.cup = rr.uniform(0.10, 0.20)
        self.droop = rr.uniform(0.10, 0.30)
        self.wave = rr.uniform(0.008, 0.022)
        self.ph = rr.uniform(0, 6.28)
        self.twist = rr.uniform(-0.12, 0.12)
        self.wsv = rr.uniform(0.92, 1.08)
        self.flip = rr.random() < 0.5
        self.nu, self.ns = (13, 3) if L >= 8.0 else ((11, 3) if L >= 5.5 else (9, 3))

    def zfield(self, x, y):
        L = self.L
        a = abs(x)
        k = 0.03 * L
        cup = self.cup * (math.sqrt(x * x + k * k) - k) * (1 - 0.30 * min(1.0, a / (0.45 * L)))
        droop = -self.droop * L * (max(y, 0.0) / L) ** 2 - 0.25 * min(y, 0.0) ** 2 / L
        wave = self.wave * L * min(1.0, a / (0.40 * L)) * math.sin(7.5 * y / L + self.ph + (0.0 if x > 0 else 2.1))
        return cup + droop + wave + self.twist * x * y / L

    def local(self):
        """(mid, top, bot, uv) lists of the leaf in its own frame (x lateral, y tip, z normal), cm."""
        L = self.L
        nu, ns = self.nu, self.ns
        nv, faces, boundary, tris, idx = leaf_topology(nu, ns)
        sv = SV[ns]
        mid, top, bot, uv = [None] * nv, [None] * nv, [None] * nv, [None] * nv
        ht = 0.028 + 0.002 * L

        def put(i, j, xn, yn):
            x = xn * self.wsv * L
            y = yn * L
            z = self.zfield(x, y)
            e = 0.012 * L
            dzx = (self.zfield(x + e, y) - self.zfield(x - e, y)) / (2 * e)
            dzy = (self.zfield(x, y + e) - self.zfield(x, y - e)) / (2 * e)
            n = Vector((-dzx, -dzy, 1.0)).normalized()
            m = Vector((x, y, z))
            ridge = 0.05 * (L / 8.0) * math.exp(-(x / (0.05 * L)) ** 2) * max(0.0, 1 - yn / 0.92)
            groove = 0.015 * math.exp(-(x / (0.04 * L)) ** 2)
            k = idx(i, j)
            mid[k] = m
            top[k] = m + n * (ht - groove)
            bot[k] = m - n * (ht + ridge)
            u = (xn - XMIN) / (XMAX - XMIN)
            uv[k] = (1 - u if self.flip else u, (yn - YMIN) / (YMAX - YMIN))

        for i in range(nu):
            t = i / nu
            th = TH_MAX * (1 - t)
            r = margin_r(th)
            xm, ym = W0 * r * math.sin(th), r * math.cos(th)
            ay = t ** 2.2
            for j in range(-ns, ns + 1):
                s = (1 if j > 0 else -1) * sv[abs(j)] if j else 0.0
                put(i, j, s * xm, ay + (ym - ay) * abs(s))
        put(nu, 0, 0.0, 1.0)
        return mid, top, bot, uv


def emit_leaf(sink, shape, M, base):
    """Add the leaf (top + bottom + rim) at world frame (M, base) to the sink."""
    nu, ns = shape.nu, shape.ns
    nv, faces, boundary, tris, idx = leaf_topology(nu, ns)
    mid, top, bot, uv = shape.local()
    tv = [sink.bm.verts.new(base + M @ p) for p in top]
    bv = [sink.bm.verts.new(base + M @ p) for p in bot]
    for f in faces:
        sink.face([tv[i] for i in f], [uv[i] for i in f])
        sink.face([bv[i] for i in reversed(f)], [uv[i] for i in reversed(f)])
    for a, b in boundary:
        sink.face([tv[a], bv[a], bv[b], tv[b]], [uv[a], uv[a], uv[b], uv[b]])


def leaf_world(shape, M, base):
    mid, top, bot, uv = shape.local()
    nv, faces, boundary, tris, idx = leaf_topology(shape.nu, shape.ns)
    wv = [base + M @ p for p in mid]
    return wv, tris


# =========================================================================== the plant
class Plant:
    CLR = 0.18            # min distance between a leaf's mid surface and anything else (cm)

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.leaf = Sink()
        self.stem = Sink()
        self.shelf_tree = shelves_tree()
        self.pot_sink, self.pot_tree = build_pot()
        self.items = []          # leaves, petioles, vines: dicts with c, r, trees, verts
        self.leaf_records = []
        self.vine_info = []
        self.rejected = 0

    # ---------------------------------------------------------------- vines
    def vine_path(self, spec):
        rr = random.Random(self.rng.random())
        phi = math.radians(spec["phi"])
        u = Vector((math.cos(phi), math.sin(phi), 0))
        rs = spec.get("r_soil", 2.5)
        S0 = POT_C + u * rs
        S0.z = 12.6
        M0 = POT_C + u * ((rs + 8.2) / 2 + 0.4)
        M0.z = 15.1
        R0 = POT_C + u * 8.15
        R0.z = 16.40
        wp = [S0, M0, R0]
        i_rim = 2
        if "head" in spec:
            wp += [Vector(p) for p in spec["head"]]
        else:
            E = Vector((R0.x, R0.y, 0))
            Hh = Vector((spec["H"][0], spec["H"][1], 0))
            zr, zh = R0.z, spec["H"][2]
            for k in range(1, 8):
                t = k / 7
                f = 1 - (1 - t) ** 2.3
                xy = E + (Hh - E) * f
                wp.append(Vector((xy.x, xy.y, zr - (zr - zh) * t)))
        last = wp[-1]
        pts = catmull_centripetal(wp, per_cm=4)
        pts = resample(pts, 0.5)
        i_rim_s = min(range(len(pts)), key=lambda i: (pts[i] - R0).length)
        # tail: a gravity hang with gentle S-curves
        ds = 1.0
        L = spec["L"]
        cum = cum_len(pts)
        rem = L - cum[-1] + 6.0
        tail = []
        if rem > 0:
            ax, ay = rr.uniform(1.2, 2.8), rr.uniform(1.2, 2.8)
            lx, ly = rr.uniform(30, 48), rr.uniform(28, 46)
            px, py = rr.uniform(0, 6.28), rr.uniform(0, 6.28)
            dxd, dyd = spec.get("drift", (0.0, 0.0))
            for k in range(1, int(rem / ds) + 1):
                s = k * ds
                ramp = smoothstep1(0, 16, s)
                x = last.x + ax * (math.sin(2 * math.pi * s / lx + px) - math.sin(px)) * ramp + dxd * s
                y = last.y + ay * (math.sin(2 * math.pi * s / ly + py) - math.sin(py)) * ramp + dyd * s
                y = min(y, spec.get("ymax", 1e9))
                x = max(x, spec.get("xmin", -1e9))
                x = min(x, spec.get("xmax", 1e9))
                tail.append(Vector((x, y, last.z - s * 0.995)))
        allp = pts[:-1] + [pts[-1]] + tail
        allp = resample(allp, 0.5)
        # relax: smooth then push out of the colliders
        for it in range(5):
            sm = [allp[0].copy()] + [(allp[i - 1] + allp[i + 1]) * 0.25 + allp[i] * 0.5 for i in range(1, len(allp) - 1)] + [allp[-1].copy()]
            for i in range(len(allp)):
                if i > i_rim_s - 6:
                    allp[i] = sm[i]
            for i in range(len(allp)):
                if i > i_rim_s - 2:
                    allp[i] = self.push_vine(allp[i], 0.30, i > i_rim_s)
        allp = resample(allp, 0.5)
        for i in range(len(allp)):
            if i > i_rim_s - 2:
                allp[i] = self.push_vine(allp[i], 0.30, i > i_rim_s)
        cum = cum_len(allp)
        keep = [i for i in range(len(allp)) if cum[i] <= L]
        allp = allp[:keep[-1] + 1]
        return allp

    def push_vine(self, p, rmin, test_pot):
        p = box_push(p, rmin)
        if test_pot:
            inside_pot = p.z < POT_H + 0.1 and math.hypot(p.x - POT_C.x, p.y - POT_C.y) < 7.9
            if not inside_pot:
                loc, nrm, _, dist = self.pot_tree.find_nearest(p, rmin)
                if loc is not None and dist < rmin:
                    d = p - loc
                    if d.length > 1e-9:
                        p = loc + d.normalized() * rmin
        return p

    def build_vines(self, specs):
        for vi, spec in enumerate(specs):
            pts = self.vine_path(spec)
            cum = cum_len(pts)
            Ltot = cum[-1]
            # nodes every 3.2-4.6 cm, after the rim
            nodes = []
            s = spec.get("first", 17.0)
            rr = random.Random(self.rng.random())
            while s < Ltot - 0.8:
                nodes.append(s)
                s += rr.uniform(2.9, 4.1)
            nodes.append(Ltot - 0.5)
            # radius profile: stout at the pot, thin at the tip, a little swelling at every node
            radii = []
            for i, c in enumerate(cum):
                r = 0.115 + 0.115 * (1 - c / Ltot) ** 0.8
                for sn in nodes:
                    r *= 1 + 0.22 * math.exp(-((c - sn) / 0.55) ** 2)
                radii.append(r)
            # decimate: keep corners and nodes
            keepi = [0]
            acc = 0.0
            for i in range(1, len(pts) - 1):
                t0 = (pts[i] - pts[keepi[-1]]).normalized()
                t1 = (pts[i + 1] - pts[i]).normalized()
                acc = t0.angle(t1, 0.0)
                near_node = any(abs(cum[i] - sn) < 0.55 for sn in nodes)
                if acc > math.radians(7) or cum[i] - cum[keepi[-1]] >= 2.6 or (near_node and cum[i] - cum[keepi[-1]] >= 0.45):
                    keepi.append(i)
            keepi.append(len(pts) - 1)
            dp = [pts[i] for i in keepi]
            dr = [radii[i] for i in keepi]
            verts, faces = tube_mesh_data(dp, dr, sides=6)
            tree = bvh_of(verts, faces)
            c = sum(dp, Vector()) / len(dp)
            self.items.append({"c": c, "r": max((p - c).length for p in dp) + 1.0, "trees": [tree], "verts": None,
                               "vine": vi})
            add_tube(self.stem, dp, dr, sides=6)
            self.vine_info.append({"name": f"V{vi + 1}", "len": Ltot, "z_end": pts[-1].z, "pts": pts, "cum": cum,
                                   "nodes": nodes, "spec": spec, "tree": tree})

    # ---------------------------------------------------------------- leaves
    def try_leaf(self, att, gen, L, own_vine, rr, name):
        """Place one leaf (+ petiole) at node `att`; `gen(attempt)` gives
        (tip dir, normal hint, roll, petiole dir, petiole length). Returns True when placed."""
        for attempt in range(44):
            f = 1.0 if attempt < 14 else (0.88 if attempt < 26 else (0.76 if attempt < 36 else 0.66))
            Ls = L * f
            t, hint, roll, hdir, plen = gen(attempt)
            plen *= (0.6 + Ls / 18.0)
            M = frame(t, hint, roll)
            base = att + hdir * plen
            shape = LeafShape(random.Random(rr.random()), Ls)
            wv, tris = leaf_world(shape, M, base)
            if min(v.x for v in wv) < WALL_X_LEAF:
                continue
            tree = bvh_of(wv, [tuple(t_) for t_ in tris])
            if self.leaf_clear(wv, tree, own_vine):
                # petiole
                p1 = att + hdir * plen * 0.55 + Vector((0, 0, 0.15 * plen))
                p2 = base - Vector(t).normalized() * plen * 0.45
                pet = []
                for k in range(6):
                    q = k / 5
                    pet.append(att * (1 - q) ** 3 + p1 * 3 * (1 - q) ** 2 * q + p2 * 3 * (1 - q) * q * q + base * q ** 3)
                pr = 0.07 + 0.0035 * Ls
                pradii = [pr * (1.25 - 0.3 * k / 5) for k in range(6)]
                pv, pf = tube_mesh_data(pet, pradii, sides=4)
                ptree = bvh_of(pv, pf)
                if self.petiole_clear(pet, ptree, own_vine):
                    emit_leaf(self.leaf, shape, M, base)
                    add_tube(self.stem, pet, pradii, sides=4, cone_end=False, cap_start=True)
                    c = sum(wv, Vector()) / len(wv)
                    self.items.append({"c": c, "r": max((v - c).length for v in wv) + 0.3,
                                       "trees": [tree, ptree], "verts": wv, "vine": None, "owner": own_vine})
                    self.leaf_records.append({"name": name, "L": Ls, "wv": wv, "tris": tris, "vine": own_vine})
                    return True
            self.rejected += 1
        return False

    def leaf_clear(self, wv, tree, own):
        clr = self.CLR
        if tree.overlap(self.shelf_tree) or too_close(wv, self.shelf_tree, clr + 0.05):
            return False
        if tree.overlap(self.pot_tree) or too_close(wv, self.pot_tree, clr + 0.05):
            return False
        c = sum(wv, Vector()) / len(wv)
        rad = max((v - c).length for v in wv)
        for it in self.items:
            if (it["c"] - c).length > rad + it["r"] + 0.8:
                continue
            for tr in it["trees"]:
                if tree.overlap(tr):
                    return False
                if too_close(wv, tr, clr):
                    return False
            if it["verts"] is not None and too_close(it["verts"], tree, clr):
                return False
        return True

    def petiole_clear(self, pet, ptree, own):
        if ptree.overlap(self.shelf_tree) or any(p.x < WALL_X_LEAF for p in pet):
            return False
        if ptree.overlap(self.pot_tree):
            return False
        c = sum(pet, Vector()) / len(pet)
        for it in self.items:
            if it["vine"] is not None and it["vine"] == own:
                continue
            if it.get("owner") is not None and it["owner"] == own and it["verts"] is not None:
                pass
            if (it["c"] - c).length > it["r"] + 3.5:
                continue
            for tr in it["trees"]:
                if ptree.overlap(tr):
                    return False
        return True

    def aerial_root(self, att, hdir, rr):
        d = Vector((-hdir.x, -hdir.y, -0.25)).normalized()
        n = rr.randint(1, 1)
        ln = rr.uniform(0.7, 1.3)
        pts = [att + d * 0.05, att + d * ln * 0.4 + Vector((0, 0, -0.05)), att + d * ln * 0.8 + Vector((0, 0, -0.25)),
               att + d * ln + Vector((0, 0, -0.55))]
        for p in pts:
            if p.x < 0.6 or (box_push(p, 0.1) - p).length_squared > 1e-9:
                return
            if self.pot_tree.find_nearest(p, 0.15)[0] is not None:
                return
        add_tube(self.stem, pts, [0.07, 0.06, 0.05, 0.035], sides=5, cone_end=True)

    def hang_gen(self, rr, sign, az0=0.0, pitch=(40, 82), spread=(20, 75)):
        def g(a):
            if a < 10:
                azd = sign * rr.uniform(*spread)
            elif a < 22:
                azd = -sign * rr.uniform(15, 75)
            else:
                azd = rr.uniform(-130, 130)
            az = az0 + math.radians(azd)
            p = math.radians(rr.uniform(*pitch))
            t = Vector((math.cos(p) * math.cos(az), math.cos(p) * math.sin(az), -math.sin(p)))
            hint = Vector((math.sin(p) * math.cos(az), math.sin(p) * math.sin(az), math.cos(p)))
            hdir = Vector((math.cos(az) * 0.9, math.sin(az) * 0.9, 0.45)).normalized()
            return t, hint, math.radians(rr.uniform(-28, 28)), hdir, rr.uniform(1.5, 3.2)
        return g

    def flat_gen(self, rr, az0, sign, pitch=(-20, 30), spread=(10, 65)):
        def g(a):
            if a < 12:
                azd = sign * rr.uniform(*spread)
            elif a < 24:
                azd = -sign * rr.uniform(*spread)
            else:
                azd = rr.uniform(-150, 150)
            az = az0 + math.radians(azd)
            p = math.radians(rr.uniform(*pitch))
            t = Vector((math.cos(p) * math.cos(az), math.cos(p) * math.sin(az), math.sin(p)))
            hint = Vector((0, 0, 1)) + Vector((math.cos(az), math.sin(az), 0)) * 1.5
            hdir = Vector((math.cos(az) * 0.85, math.sin(az) * 0.85, 0.5)).normalized()
            return t, hint, math.radians(rr.uniform(-22, 22)), hdir, rr.uniform(1.4, 3.0)
        return g

    def dress_vines(self):
        for vi, info in enumerate(self.vine_info):
            rr = random.Random(self.rng.random())
            pts, cum, nodes = info["pts"], info["cum"], info["nodes"]
            Ltot = cum[-1]
            sign = 1 if rr.random() < 0.5 else -1
            placed = 0
            for n, s in enumerate(nodes):
                p, tan = at_len(pts, cum, s)
                frac = s / Ltot
                L = 10.4 * (1 - 0.64 * frac ** 0.85) * rr.uniform(0.9, 1.08)
                if n == len(nodes) - 1:
                    L = 3.4
                L = min(max(L, 3.4), 11.0)
                sign = -sign if rr.random() > 0.12 else sign
                hanging = tan.z < -0.5
                if hanging:
                    gen = self.hang_gen(rr, sign)
                else:
                    out = Vector((tan.y, -tan.x, 0)) * sign
                    if out.length < 1e-3:
                        out = Vector((1, 0, 0))
                    az0 = math.atan2(out.y, out.x)
                    gen = self.flat_gen(rr, az0, 1)
                ok = self.try_leaf(p, gen, L, vi, rr, f"v{vi}_{n}")
                placed += ok
                hd = Vector((-tan.y, tan.x, 0)).normalized() if tan.xy.length > 0.2 else Vector((1, 0, 0))
                if rr.random() < 0.75:
                    self.aerial_root(p, hd, rr)
            info["leaves"] = placed

    # ---------------------------------------------------------------- crown
    def crown(self):
        rr = random.Random(self.rng.random())
        # 1) rim spill: short stems over the pot rim, leaves hanging down the pot sides
        nrim = 14
        for k in range(nrim):
            az = 2 * math.pi * (k + rr.uniform(-0.25, 0.25)) / nrim + 0.2
            u = Vector((math.cos(az), math.sin(az), 0))
            rs = rr.uniform(3.0, 5.2)
            S0 = POT_C + u * rs
            S0.z = 12.6
            pts = [S0, POT_C + u * (rs + 1.0) + Vector((0, 0, 14.4)), POT_C + u * (rs + 3.2) + Vector((0, 0, 16.1)),
                   POT_C + u * 8.4 + Vector((0, 0, 16.55))]
            pts = resample(catmull_centripetal(pts, 5), 0.6)
            self.add_crown_stem(pts, 0.19, 0.15, k + 100)
            tip = pts[-1]
            L = rr.uniform(6.0, 8.6)
            gen = self.hang_gen(rr, 1 if k % 2 else -1, az0=az, pitch=(20, 60), spread=(8, 45))
            self.try_leaf(tip, gen, L, k + 100, rr, f"rim{k}")
            if rr.random() < 0.7:  # a second leaf a bit earlier on the stem
                p2 = pts[len(pts) // 2 + 1]
                self.try_leaf(p2, self.flat_gen(rr, az, 1 if k % 2 == 0 else -1, pitch=(-5, 40)), rr.uniform(5.5, 8.0),
                              k + 100, rr, f"rim{k}b")
        # 2) rising stems with leaves facing up and out
        nst = 24
        for k in range(nst):
            az = 2 * math.pi * (k + rr.uniform(-0.3, 0.3)) / nst
            u = Vector((math.cos(az), math.sin(az), 0))
            rs = rr.uniform(0.3, 4.0)
            S0 = POT_C + u * rs
            S0.z = 12.6
            h = rr.uniform(10, 25)
            reach = rr.uniform(3.5, 12.0)
            if u.x < 0:
                reach = min(reach, 3.5 + 4.0 * (1 + u.x))
            P0 = S0
            P1 = S0 + Vector((0, 0, h * 0.55)) + u * reach * 0.05
            P2 = S0 + Vector((0, 0, h * 0.95)) + u * reach * 0.55
            P3 = S0 + Vector((0, 0, h * 0.85)) + u * reach
            pts = []
            for q in range(21):
                t = q / 20
                pts.append(P0 * (1 - t) ** 3 + P1 * 3 * (1 - t) ** 2 * t + P2 * 3 * (1 - t) * t * t + P3 * t ** 3)
            pts = resample(pts, 0.6)
            self.add_crown_stem(pts, 0.21, 0.13, k + 200)
            cum = cum_len(pts)
            sgn = 1 if k % 2 else -1
            for q, tfrac in enumerate((0.38, 0.55, 0.72, 0.88, 1.0)):
                p, tan = at_len(pts, cum, tfrac * cum[-1])
                L = rr.uniform(8.0, 11.0) * (1 - 0.28 * tfrac)
                if tfrac >= 1.0:
                    L = rr.uniform(5.0, 7.0)
                pitch = (-20, 35) if tfrac < 0.95 else (0, 45)
                self.try_leaf(p, self.flat_gen(rr, az, sgn * (1 if q % 2 == 0 else -1), pitch=pitch),
                              L, k + 200, rr, f"crown{k}_{q}")

    def add_crown_stem(self, pts, r0, r1, sid):
        radii = [r0 + (r1 - r0) * i / (len(pts) - 1) for i in range(len(pts))]
        verts, faces = tube_mesh_data(pts, radii, sides=6)
        tree = bvh_of(verts, faces)
        c = sum(pts, Vector()) / len(pts)
        self.items.append({"c": c, "r": max((p - c).length for p in pts) + 1.0, "trees": [tree], "verts": None, "vine": sid})
        add_tube(self.stem, pts, radii, sides=6)

    # ---------------------------------------------------------------- verification
    def verify(self):
        issues = []
        recs = self.leaf_records
        trees = [bvh_of(r["wv"], [tuple(t) for t in r["tris"]]) for r in recs]
        for i, r in enumerate(recs):
            if trees[i].overlap(self.shelf_tree):
                issues.append(("shelf", r["name"]))
            if min(v.x for v in r["wv"]) < 0.0:
                issues.append(("wall", r["name"]))
            if trees[i].overlap(self.pot_tree):
                issues.append(("pot", r["name"]))
        for i in range(len(recs)):
            ci = sum(recs[i]["wv"], Vector()) / len(recs[i]["wv"])
            for j in range(i + 1, len(recs)):
                cj = sum(recs[j]["wv"], Vector()) / len(recs[j]["wv"])
                if (ci - cj).length > 24:
                    continue
                if trees[i].overlap(trees[j]):
                    issues.append(("leaf-leaf", recs[i]["name"], recs[j]["name"]))
        return issues


# =========================================================================== specs
VINES = [
    # free hangers: over the left rim, arc out, fall past the shelves' left ends
    {"phi": -100, "H": (13.0, -7.0, 1.5), "L": 140, "ymax": -2.2, "xmin": 6.0, "xmax": 24.0, "drift": (0.0, -0.01), "r_soil": 2.6},
    {"phi": -68, "H": (21.5, -4.6, 2.5), "L": 125, "ymax": -2.0, "xmin": 8.0, "xmax": 29.0, "drift": (0.01, -0.01), "r_soil": 3.4},
    {"phi": -128, "H": (6.2, -3.4, 2.0), "L": 100, "ymax": -1.6, "xmin": 4.2, "xmax": 15.0, "r_soil": 3.0},
    {"phi": -40, "H": (27.4, -2.8, 3.0), "L": 90, "ymax": -1.6, "xmin": 14.0, "xmax": 32.0, "drift": (0.01, -0.005), "r_soil": 3.8},
    # lies on the shelf-2 top, loops, drapes over its left end and continues down
    {"phi": -88, "L": 120, "ymax": -0.65, "xmin": 8.0, "xmax": 24.0, "r_soil": 4.2, "first": 20.0, "drift": (0.0, -0.01),
     "head": [(12.7, 3.6, 15.8), (12.5, -1.2, 10.5), (12.3, -3.5, 3.0), (12.0, -3.7, -9.0), (11.8, -3.5, -20.0),
              (12.4, -2.2, -28.5), (13.2, -0.2, -33.2), (14.3, 1.8, -35.9), (15.6, 3.4, -36.71), (17.3, 5.2, -36.71),
              (19.3, 5.9, -36.71), (20.9, 4.7, -36.71), (21.1, 2.8, -36.71), (20.7, 1.1, -36.71), (20.45, 0.35, -36.69),
              (20.25, -0.1, -36.76), (20.1, -0.31, -37.0), (20.0, -0.35, -37.7), (19.9, -0.8, -40.0)]},
    # drapes over the top shelf's left end and hugs the end faces on the way down
    {"phi": -78, "L": 140, "ymax": -0.65, "xmin": 8.0, "xmax": 24.0, "r_soil": 3.6, "first": 18.0, "drift": (0.0, -0.006),
     "head": [(15.9, 5.3, 13.0), (15.9, 4.6, 8.0), (15.7, 3.5, 3.0), (15.6, 2.4, 0.32), (15.7, 1.3, 0.31),
              (15.8, 0.35, 0.31), (15.8, -0.1, 0.27), (15.8, -0.31, 0.0), (15.8, -0.36, -0.8), (15.7, -0.6, -3.0)]},
    # spill over the front edge and fall in front of the shelves
    {"phi": 8, "L": 70, "xmin": 26.5, "xmax": 31.0, "r_soil": 3.2, "first": 17.0, "drift": (0.01, 0.0),
     "head": [(23.4, 15.3, 14.0), (24.5, 15.5, 8.5), (25.0, 15.7, 3.0), (25.2, 15.8, 0.32), (25.8, 15.9, 0.31),
              (26.0, 15.95, 0.31), (26.22, 16.0, 0.22), (26.31, 16.0, 0.0), (26.36, 16.05, -0.8), (26.55, 16.1, -3.0)]},
    {"phi": 38, "L": 38, "xmin": 26.5, "xmax": 30.0, "r_soil": 3.0, "first": 16.0,
     "head": [(22.6, 19.7, 14.0), (24.2, 20.6, 8.5), (24.9, 21.0, 3.0), (25.2, 21.1, 0.32), (25.8, 21.2, 0.31),
              (26.0, 21.25, 0.31), (26.22, 21.3, 0.22), (26.31, 21.3, 0.0), (26.38, 21.3, -0.8), (26.6, 21.4, -3.0)]},
]


# =========================================================================== preview rendering
def make_materials(out_dir):
    M = {}
    M["pot"] = S.material("M_Pot", (0.70, 0.58, 0.42), 0.25, specular=0.6)
    M["soil"] = S.material("M_Soil", (0.030, 0.021, 0.014), 0.95)
    M["leaf"] = S.material("M_Leaf", (0.12, 0.30, 0.05), 0.38)
    M["stem"] = S.material("M_Stem", (0.14, 0.24, 0.05), 0.5)
    tex = bpy.data.images.load(os.path.join(out_dir, "T_PothosLeaf.png"))
    tex.colorspace_settings.name = "sRGB"
    nt = M["leaf"].node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = tex
    node.extension = "EXTEND"
    nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    return M


def setup_render(samples, path):
    sc = bpy.context.scene
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    eevee = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    try:
        sc.render.engine = eevee
        sc.eevee.taa_render_samples = samples
        for attr in ("use_shadows", "use_raytracing"):
            if hasattr(sc.eevee, attr):
                setattr(sc.eevee, attr, True)
    except Exception:
        sc.render.engine = "CYCLES"
        sc.cycles.samples = samples
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.render.resolution_x = sc.render.resolution_y = 1200
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path


def set_world(grey=0.18, strength=1.0, color=None):
    sc = bpy.context.scene
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        c = color or (grey, grey, grey)
        bg.inputs["Color"].default_value = (*c, 1)
        bg.inputs["Strength"].default_value = strength


def add_area(name, loc, target, energy, size, color=(1, 1, 1), shape="DISK"):
    light = bpy.data.lights.new(name, "AREA")
    light.shape = shape
    light.size = size
    light.energy = energy
    light.color = color
    ob = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def add_camera(loc, target, lens):
    cd = bpy.data.cameras.new("_cam")
    cd.lens = lens
    cd.clip_start = 0.01
    cd.clip_end = 50
    cam = bpy.data.objects.new("_cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return cam


def fit_camera(view_dir, corners, lens, margin=1.08, target=None):
    """Camera looking along -view_dir that frames the corners (metres)."""
    v = Vector(view_dir).normalized()
    cd = bpy.data.cameras.new("_cam")
    cd.lens = lens
    cd.clip_start = 0.01
    cd.clip_end = 50
    cam = bpy.data.objects.new("_cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    co, _ = cam.camera_fit_coords(dg, [c for p in corners for c in p])
    cam.location = co
    bpy.context.view_layer.update()
    co, _ = cam.camera_fit_coords(bpy.context.evaluated_depsgraph_get(), [c for p in corners for c in p])
    centre = target if target is not None else sum((Vector(c) for c in corners), Vector()) / len(corners)
    cam.location = centre + (Vector(co) - centre) * margin if target is not None else co
    if target is None:
        cam.location = centre + (Vector(co) - centre) * margin
    return cam


def clear_preview():
    for ob in list(bpy.data.objects):
        if ob.name.startswith(("_", "pv_")) or ob.type in {"LIGHT", "CAMERA"}:
            bpy.data.objects.remove(ob, do_unlink=True)


def render(path):
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def box_obj(name, lo, hi, mat):
    return S.box(name, [c * CM for c in lo], [c * CM for c in hi], mat)


def oak_material():
    return S.material("pv_Oak", (0.36, 0.20, 0.08), 0.55)


def plant_views(plant_ob, out, samples, want):
    lo, hi = S.bbox(plant_ob)
    corners = [(x, y, z) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    centre = (lo + hi) / 2

    def lights(centre, d):
        add_area("_key", centre + Vector((0.6, 0.9, 0.9)).normalized() * d, centre, 38 * d * d, d * 0.8)
        add_area("_fill", centre + Vector((0.8, -0.8, 0.3)).normalized() * d, centre, 12 * d * d, d * 1.1)
        add_area("_rim", centre + Vector((-1.0, 0.2, 0.8)).normalized() * d, centre, 22 * d * d, d * 0.5)

    if "3q" in want:
        clear_preview()
        set_world()
        d = (hi - lo).length * 1.6
        lights(centre, d)
        v = Vector((1.0, 0.8, 0.40)).normalized()
        cam = add_camera(centre + v * 4.0, centre, 60)
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = (hi.z - lo.z) * 1.10
        setup_render(samples, os.path.join(out, NAME + ".png"))
        render("3q")
    if "front" in want:
        clear_preview()
        set_world()
        d = (hi - lo).length * 1.6
        lights(centre, d)
        fit_camera((1.0, 0.0, 0.03), corners, 60, 1.06)
        setup_render(samples, os.path.join(out, NAME + "_front.png"))
        render("front")


def shelf_scene(plant_ob, out, samples):
    clear_preview()
    oak = oak_material()
    wall = S.material("pv_Wall", (0.42, 0.32, 0.22), 0.9)
    walnut = S.material("pv_Walnut", (0.20, 0.10, 0.05), 0.5)
    objs = []
    for i, (lo, hi) in enumerate(SHELF_BOXES):
        hi2 = (hi[0], 70.0, hi[2])        # the first 70 cm of each shelf is enough
        objs.append(box_obj(f"pv_shelf{i}", (lo[0], lo[1], lo[2]), hi2, oak))
    objs.append(S.box("pv_wall", (-0.02, -90 * CM, -150 * CM), (-0.0005, 120 * CM, 60 * CM), wall))
    for k in range(10):   # walnut slat panel to the left of the shelves
        y0 = (-95 + k * 8.4)
        objs.append(S.box(f"pv_slat{k}", (-0.02, y0 * CM, -150 * CM), (0.0, (y0 + 5.2) * CM, 60 * CM), walnut))
    set_world(0.05, 0.25, (0.35, 0.28, 0.22))
    tgt = Vector((10 * CM, 10 * CM, -42 * CM))
    add_area("_key", Vector((190, -140, 90)) * CM, tgt, 120, 1.6, (1.0, 0.93, 0.82))
    add_area("_fill", Vector((160, 120, 20)) * CM, tgt, 25, 1.6, (0.9, 0.95, 1.0))
    for i, z in enumerate(SHELF_TOPS):     # warm LED strips under each shelf's front edge
        add_area(f"_led{i}", Vector((22 * CM, 20 * CM, (z - SHELF_T - 1.0) * CM)), Vector((2 * CM, 20 * CM, (z - SHELF_T - 26) * CM)),
                 25, 0.22, (1.0, 0.62, 0.30), "RECTANGLE")
    add_camera(Vector((190, -80, 25)) * CM, Vector((8, 8, -40)) * CM, 40)
    setup_render(samples, os.path.join(out, "pothos_on_shelves.png"))
    render("shelves")


def close_scene(plant_ob, out, samples):
    clear_preview()
    set_world()
    tgt = Vector((12, -2, 10)) * CM
    add_area("_key", tgt + Vector((0.7, 0.4, 1.0)).normalized() * 0.9, tgt, 45, 0.7)
    add_area("_fill", tgt + Vector((0.8, -0.8, 0.2)).normalized() * 0.9, tgt, 10, 0.9)
    add_area("_rim", tgt + Vector((-0.5, -0.2, 1.0)).normalized() * 0.9, tgt, 18, 0.5)
    add_camera(Vector((82, -52, 36)) * CM, tgt, 50)
    setup_render(samples, os.path.join(out, NAME + "_close.png"))
    render("close")


def leaf_close(out, samples, M):
    """One leaf close-up on its own to show T_PothosLeaf."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    sink = Sink()
    rr = random.Random(2)
    shape = LeafShape(rr, 12.0)
    shape.flip = False
    shape.nu, shape.ns = 16, 5
    SV[5] = [0.0, 0.08, 0.22, 0.45, 0.72, 1.0]
    shape.cup, shape.droop, shape.wave = 0.14, 0.14, 0.012
    Mx = frame((0, 0, 1), (1, 0, 0), 0.0)     # leaf faces +X, tip up
    emit_leaf(sink, shape, Mx, Vector((0, 0, 0)))
    ob = sink.to_object("pv_leaf", M["leaf"])
    S.tidy(ob, 40)
    set_world()
    tgt = Vector((0.0, 0.0, 0.058))
    add_area("_key", tgt + Vector((0.8, 0.5, 0.7)).normalized() * 0.8, tgt, 22, 0.6)
    add_area("_fill", tgt + Vector((0.8, -0.8, 0.1)).normalized() * 0.8, tgt, 9, 0.8)
    add_area("_rim", tgt + Vector((-0.8, 0.3, 0.6)).normalized() * 0.8, tgt, 18, 0.5)
    add_camera(tgt + Vector((0.42, 0.0, 0.0)), tgt, 50)
    setup_render(samples, os.path.join(out, "pothos_leaf_close.png"))
    render("leaf")


# =========================================================================== main
def main():
    args = parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    S.reset_scene()
    write_leaf_texture(os.path.join(out, "T_PothosLeaf.png"))
    if args.texture_only:
        return
    mats = make_materials(out)

    pl = Plant(args.seed)
    soil = build_soil(random.Random(args.seed + 1))
    pl.build_vines(VINES)
    pl.crown()
    pl.dress_vines()
    for info in pl.vine_info:
        print(f"[{NAME}] {info['name']}: length {info['len']:.0f} cm, leaves {info.get('leaves', 0)}/{len(info['nodes'])}, "
              f"end z {info['pts'][-1].z:.0f}")
    issues = pl.verify()
    print(f"[{NAME}] leaves {len(pl.leaf_records)}, rejected candidates {pl.rejected}, issues {issues}")

    parts = [pl.pot_sink.to_object("pot", mats["pot"]), soil.to_object("soil", mats["soil"]),
             pl.leaf.to_object("leaf", mats["leaf"]), pl.stem.to_object("stem", mats["stem"])]
    ob = S.join(NAME, parts)
    S.set_origin(ob, (0, 0, 0))
    S.tidy(ob, 40)
    fbx = os.path.join(out, NAME + ".fbx")
    S.export_fbx(ob, fbx)
    lo, hi = S.bbox(ob)
    print("=" * 60)
    print(f"{NAME}: exported {fbx}")
    print(f"{NAME}: materials {[m.name for m in ob.data.materials]}")
    print(f"{NAME}: triangles {S.tri_count(ob)}")
    print(f"{NAME}: bbox cm  X {lo.x*100:.1f}..{hi.x*100:.1f}  Y {lo.y*100:.1f}..{hi.y*100:.1f}  Z {lo.z*100:.1f}..{hi.z*100:.1f}")
    print("=" * 60)
    if args.no_render:
        return
    want = set(args.only.split(",")) if args.only else {"3q", "front", "shelves", "close", "leaf"}
    plant_views(ob, out, args.samples, want)
    if "shelves" in want:
        shelf_scene(ob, out, args.samples)
    if "close" in want:
        close_scene(ob, out, args.samples)
    if "leaf" in want:
        leaf_close(out, args.samples, mats)


main()
