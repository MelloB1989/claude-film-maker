"""Anime faces for the people of lib/human.py: the realistic face MakeHuman makes, turned into one a TV anime would draw.

- `head(...)`: MakeHuman's own targets that move a head toward an anime one (a small nose and mouth, thin lips, flat
  cheeks, a cleaner jaw and chin), for `human.make(targets=...)`.
- `smooth(person)`: the features smoothed into one clean surface as seen from the front: the eye sockets filled to the
  lids, the lips and the nostrils flattened, a small nose kept, so what is drawn on it lies flat.
- `shade(person)`: the face shaded like a drawing: its normals taken from a smooth proxy of the head (an ellipsoid
  riding on the head bone), so light and shadow fall across it in one simple shape.
- `draw(person, Face(...))`: the features drawn back on, in one texture (`drawing`) on a decal laid over the face: big graphic
  eyes (`Eye`: the white under the lid's shadow, an iris darkening upward with a dark rim, the pupil, two highlights, a
  thick upper lash line flicking out at the corner, a hint of the lower lash, a lid crease), and `Stroke`s for the
  brows, the nose, the mouth and lines of age; cel shaded with the face, whitening with a lightning flash.
- `apply(person, Face(...), look=...)`: all of it, MakeHuman's eyeballs hidden (kept as landmarks) and its lashes gone.

Drawings are in eye units round the eyes' midpoint: the distance between the eyes' centres is 1, x runs toward the
person's left, z up; the eyes' centres are at (+-0.5, 0). So one Face fits any head. `Eye`, `Stroke`, `Face`, `lids`,
`spline` and `drawing` are numpy only and tested without Blender. Positions in the person's own frame (rest pose: facing -y,
left +x).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import human

RGB = tuple[float, float, float]
INK = (0.012, 0.012, 0.016)


# ---------------------------------------------------------------------------------------------------- the drawing

def _smoothstep(e0: float, e1: float, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _cover(sd, px: float):
    """How much of a pixel `px` across lies inside an edge its centre is `sd` from (signed: inside negative)."""
    return np.clip(0.5 - sd / px, 0.0, 1.0)


@dataclass
class Eye:
    """One eye, drawn round its centre in eye units: x out from the nose along the eye, z up (the right eye is the
    left one mirrored)."""
    width: float = 0.6                  # corner to corner
    height: float = 0.3                 # the opening at its tallest
    tilt: float = 4.0                   # degrees the outer corner sits above the inner
    peak: float = 0.45                  # where along the eye (0 inner corner .. 1 outer) the upper lid is highest
    round: float = 0.7                  # the upper lid's arc: lower, a flatter top; higher, a rounder one
    lower: float = 0.45                 # the lower lid's depth, in heights
    slant: float = 0.0                  # 0..1: the upper lid flattened toward the nose (a scowl's hard line)
    droop: float = 0.0                  # 0..1: its outer half lowered (half-lidded: calm, kind, tired)
    iris: tuple = (0.15, 0.2)           # half-width, half-height
    iris_at: tuple = (0.01, -0.01)      # its centre from the eye's
    iris_top: RGB = (0.03, 0.02, 0.015)
    iris_bottom: RGB = (0.25, 0.14, 0.07)
    rim: RGB = (0.015, 0.01, 0.01)
    pupil: float = 0.42                 # its size over the iris's
    pupil_color: RGB = (0.006, 0.005, 0.005)
    highlights: tuple = ((-0.38, 0.42, 0.26), (0.42, -0.5, 0.11))   # (x, z in iris radii, radius in iris half-widths)
    white: RGB = (0.9, 0.9, 0.92)
    shadow: float = 0.32                # the lid's shadow over the white and the iris, in heights below the lid
    shadow_color: RGB = (0.55, 0.58, 0.68)
    lash: float = 0.055                 # the upper lash line's thickness at its outer end
    lash_inner: float = 0.3             # ... at the inner corner, over that
    flick: tuple = (0.1, 12.0, 0.9)     # length, angle up from the eye's axis (degrees), thickness over `lash`
    lower_lash: tuple | None = (0.55, 0.98, 0.014)   # from, to (along the eye 0..1), thickness
    crease: float = 0.0                 # the lid crease's height above the lid, in heights (0: none)
    crease_width: float = 0.01
    lash_color: RGB = INK


@dataclass
class Stroke:
    """An ink stroke in eye units round the eyes' midpoint: a brow, the nose, the mouth, a line of age."""
    points: tuple                       # [(x, z), ...]
    width: float | tuple = 0.03         # one width, or one for each point
    color: RGB = INK
    taper: tuple = (0.25, 0.25)         # its width at the start and the end, over its full width
    mirror: bool = False                # drawn mirrored across the face's middle as well
    far: float = 1.0                    # in the far drawing (Face.bolder): its width over the near one's share; 0 left out


@dataclass
class Face:
    """A face's drawing: its eyes and its strokes (drawn over the eyes, in order)."""
    eye: Eye = field(default_factory=Eye)
    strokes: list = field(default_factory=list)

    def bolder(self, k: float = 2.0) -> "Face":
        """The drawing for a face small on screen: every line `k` times as heavy (the lash line, the lower lash, the
        strokes, each by its own `far` share too), the lid crease and the strokes with `far` 0 left out, the highlights
        a little larger, so it still reads at a few pixels an eye."""
        from dataclasses import replace

        e = self.eye
        lower = None if e.lower_lash is None else (e.lower_lash[0], e.lower_lash[1], e.lower_lash[2] * k)
        eye = replace(e, lash=e.lash * k, lower_lash=lower, crease=0.0,
                      highlights=tuple((hx, hz, hr * 1.25) for hx, hz, hr in e.highlights[:1]))
        strokes = []
        for s in self.strokes:
            if s.far <= 0:
                continue
            w = np.asarray(s.width, float) * k * s.far
            strokes.append(replace(s, width=tuple(w.tolist()) if w.ndim else float(w)))
        return Face(eye, strokes)


def lids(e: Eye, t):
    """The upper and lower lids' heights above the eye's axis at `t` (0 the inner corner .. 1 the outer), eye units."""
    tc = np.clip(t, 0.0, 1.0)
    q = math.log(0.5) / math.log(min(max(e.peak, 0.05), 0.95))
    top = e.height * np.sin(np.pi * tc ** q) ** e.round
    top = top * (1 - e.slant * (1 - tc) ** 1.5) * (1 - e.droop * _smoothstep(0.3, 1.0, tc))
    bottom = -e.lower * e.height * np.sin(np.pi * tc) ** 0.9
    return top, bottom


def _over(rgb, a, color, cov):
    """Lay `color` (a colour or an (h, w, 3) array) over the straight-alpha canvas where it covers `cov`."""
    cov = cov[..., None]
    col = np.asarray(color, float)
    pre = rgb * a[..., None]
    pre = col * cov + pre * (1 - cov)
    a[...] = cov[..., 0] + a * (1 - cov[..., 0])
    rgb[...] = np.where(a[..., None] > 1e-6, pre / np.maximum(a[..., None], 1e-6), 0.0)


def _eye(rgb, a, X, Z, e: Eye, side: int, px: float):
    """Draw one eye (side +1 the person's left, at x +0.5; -1 the right) on the canvas crop with face coordinates X, Z."""
    th = math.radians(e.tilt)
    xo = side * X - 0.5
    ex = xo * math.cos(th) + Z * math.sin(th)
    ez = -xo * math.sin(th) + Z * math.cos(th)
    half = e.width / 2
    t = (ex + half) / e.width
    top, bottom = lids(e, t)
    sd_t = np.maximum(-t, t - 1) * e.width
    white_cov = _cover(np.maximum(np.maximum(ez - top, bottom - ez), sd_t), px)
    below_lid = np.clip(top - ez, 0, None)
    shade = 1 - _smoothstep(0.0, e.shadow * e.height, below_lid)        # 1 at the lid, 0 a shadow's depth below
    white = np.asarray(e.white) + (np.asarray(e.shadow_color) - np.asarray(e.white)) * shade[..., None] * 0.9
    _over(rgb, a, white, white_cov)
    # the iris, darkening upward to a dark rim, the pupil, the lid's shadow across them
    ix, iz = e.iris_at
    rx, rz = e.iris
    dx, dz = ex - ix, ez - iz
    r = np.sqrt((dx / rx) ** 2 + (dz / rz) ** 2)
    g = np.clip((dz + rz) / (2 * rz), 0, 1)
    col = np.asarray(e.iris_bottom) + (np.asarray(e.iris_top) - np.asarray(e.iris_bottom)) * _smoothstep(0.1, 0.95, g)[..., None]
    col = col + (np.asarray(e.rim) - col) * _smoothstep(0.72, 0.97, r)[..., None]
    col = col * (1 - 0.45 * shade)[..., None]
    _over(rgb, a, col, _cover((r - 1) * min(rx, rz), px) * white_cov)
    _over(rgb, a, e.pupil_color, _cover((r / e.pupil - 1) * min(rx, rz) * e.pupil, px) * white_cov)
    for hx, hz, hr in e.highlights:
        d = np.hypot(ex - (ix + hx * rx), ez - (iz + hz * rz))
        _over(rgb, a, (1.0, 1.0, 1.0), _cover(d - hr * rx, px) * white_cov)
    # the upper lash line, thick at the outer end, and its flick past the corner
    thick = e.lash * (e.lash_inner + (1 - e.lash_inner) * _smoothstep(0.0, 0.8, t))
    sd = np.maximum(np.maximum(ez - (top + 0.7 * thick), (top - 0.3 * thick) - ez), np.maximum(-(t + 0.03), t - 1) * e.width)
    _over(rgb, a, e.lash_color, _cover(sd, px))
    length, angle, fthick = e.flick
    if length > 0:
        ph = math.radians(angle)
        s = (ex - half) * math.cos(ph) + ez * math.sin(ph)
        n = -(ex - half) * math.sin(ph) + ez * math.cos(ph)
        w = e.lash * fthick * np.clip(1 - s / length, 0, 1) ** 1.2
        sd = np.maximum(np.maximum(-s, s - length), np.maximum(n - 0.7 * w, -0.3 * w - n))
        _over(rgb, a, e.lash_color, _cover(sd, px))
    if e.lower_lash is not None:
        t0, t1, lw = e.lower_lash
        k = np.clip((t - t0) / max(t1 - t0, 1e-6), 0, 1)
        w = lw * np.sin(np.pi * k)
        sd = np.maximum(np.abs(ez - bottom) - w / 2, np.maximum(t0 - t, t - t1) * e.width)
        _over(rgb, a, e.lash_color, _cover(sd, px))
    if e.crease > 0:
        k = np.clip((t - 0.25) / 0.7, 0, 1)
        w = e.crease_width * np.sin(np.pi * k)
        sd = np.maximum(np.abs(ez - (top + e.crease * e.height)) - w / 2, np.maximum(0.25 - t, t - 0.95) * e.width)
        _over(rgb, a, e.lash_color, _cover(sd, px))


def spline(points, k: int = 24) -> tuple[np.ndarray, np.ndarray]:
    """A smooth curve through `points` (a Catmull-Rom spline, the ends held): `k` samples a span, and for each sample
    the position along the points it falls at (0 .. len-1), to carry a value given at each point along it."""
    p = np.asarray(points, float)
    if len(p) < 3:
        f = np.linspace(0, len(p) - 1, k * (len(p) - 1) + 1)
        return np.column_stack([np.interp(f, np.arange(len(p)), p[:, i]) for i in range(p.shape[1])]), f
    q = np.concatenate([[2 * p[0] - p[1]], p, [2 * p[-1] - p[-2]]])
    out, where = [], []
    for i in range(len(p) - 1):
        p0, p1, p2, p3 = q[i], q[i + 1], q[i + 2], q[i + 3]
        t = np.linspace(0, 1, k, endpoint=False)[:, None]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
        where.append(i + t[:, 0])
    out.append(p[-1:])
    where.append(np.array([len(p) - 1.0]))
    return np.concatenate(out), np.concatenate(where)


def _stroke(rgb, a, X, Z, s: Stroke, px: float):
    pts, at = spline(s.points)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    total = max(arc[-1], 1e-9)
    n = max(8, int(total / (px * 0.5)) + 2)
    u = np.linspace(0, total, n)
    sx, sz = np.interp(u, arc, pts[:, 0]), np.interp(u, arc, pts[:, 1])
    widths = np.broadcast_to(np.asarray(s.width, float), (len(s.points),))
    w = np.interp(np.interp(u, arc, at), np.arange(len(widths)), widths)
    f = u / total
    w = w * (s.taper[0] + (1 - s.taper[0]) * _smoothstep(0.0, 0.3, f)) * (s.taper[1] + (1 - s.taper[1]) * _smoothstep(1.0, 0.7, f))
    # nearest sample of the stroke to each pixel
    xs, zs = X.ravel(), Z.ravel()
    best = np.full(xs.shape, np.inf)
    bw = np.zeros(xs.shape)
    for i0 in range(0, n, 256):
        cx, cz, cw = sx[i0:i0 + 256], sz[i0:i0 + 256], w[i0:i0 + 256]
        d = np.hypot(xs[:, None] - cx[None, :], zs[:, None] - cz[None, :])
        j = np.argmin(d, axis=1)
        dj = d[np.arange(len(xs)), j]
        better = dj < best
        best[better] = dj[better]
        bw[better] = cw[j[better]]
    cov = _cover((best - bw / 2).reshape(X.shape), px)
    _over(rgb, a, s.color, cov)


def drawing(face: Face, *, extent=(-1.3, 1.3, -2.4, 1.4), res: int = 640) -> np.ndarray:
    """The face's drawing as straight-alpha linear RGBA, (rows, cols, 4), row 0 at the bottom (as Blender stores an
    image), over `extent` (x0, x1, z0, z1 in eye units) at `res` pixels an eye unit."""
    x0, x1, z0, z1 = extent
    W, H = int(round((x1 - x0) * res)), int(round((z1 - z0) * res))
    px = 1.0 / res
    rgb = np.zeros((H, W, 3))
    a = np.zeros((H, W))

    def crop(bx0, bx1, bz0, bz1):
        c0, c1 = max(0, int((bx0 - x0) * res)), min(W, int(math.ceil((bx1 - x0) * res)))
        r0, r1 = max(0, int((bz0 - z0) * res)), min(H, int(math.ceil((bz1 - z0) * res)))
        if c1 <= c0 or r1 <= r0:
            return None
        xs = x0 + (np.arange(c0, c1) + 0.5) * px
        zs = z0 + (np.arange(r0, r1) + 0.5) * px
        X, Z = np.meshgrid(xs, zs)
        return (slice(r0, r1), slice(c0, c1)), X, Z

    e = face.eye
    reach = e.width / 2 + e.flick[0] + 0.1
    for side in (1, -1):
        c = crop(side * 0.5 - reach, side * 0.5 + reach, -0.6, 0.7)
        if c is None:
            continue
        sl, X, Z = c
        sub_rgb, sub_a = rgb[sl].copy(), a[sl].copy()
        _eye(sub_rgb, sub_a, X, Z, e, side, px)
        rgb[sl], a[sl] = sub_rgb, sub_a
    for s in face.strokes:
        for mirror in ((False, True) if s.mirror else (False,)):
            pts = np.asarray(s.points, float) * ([-1.0, 1.0] if mirror else [1.0, 1.0])
            stroke = Stroke(tuple(map(tuple, pts)), s.width, s.color, s.taper, False, s.far)
            ww = float(np.max(np.asarray(s.width, float)))
            c = crop(pts[:, 0].min() - ww, pts[:, 0].max() + ww, pts[:, 1].min() - ww, pts[:, 1].max() + ww)
            if c is None:
                continue
            sl, X, Z = c
            sub_rgb, sub_a = rgb[sl].copy(), a[sl].copy()
            _stroke(sub_rgb, sub_a, X, Z, stroke, px)
            rgb[sl], a[sl] = sub_rgb, sub_a
    return np.concatenate([rgb, a[..., None]], axis=2)


# ---------------------------------------------------------------------------------------------------- the head

# MakeHuman targets (data/targets/<group>/<name>) that move a head toward an anime one
HEAD = {
    "nose/nose-volume-decr": 0.7, "nose/nose-scale-horiz-decr": 0.5, "nose/nose-scale-vert-decr": 0.3,
    "nose/nose-scale-depth-decr": 0.3, "nose/nose-flaring-decr": 0.9, "nose/nose-nostrils-width-decr": 0.8,
    "nose/nose-point-width-decr": 0.6,
    "mouth/mouth-scale-horiz-decr": 0.3, "mouth/mouth-upperlip-volume-decr": 0.9, "mouth/mouth-lowerlip-volume-decr": 0.9,
    "mouth/mouth-cupidsbow-decr": 0.7, "mouth/mouth-philtrum-volume-decr": 0.7,
    "chin/chin-width-decr": 0.35, "chin/chin-prominent-incr": 0.2,
    "cheek/l-cheek-bones-decr": 0.5, "cheek/r-cheek-bones-decr": 0.5, "cheek/l-cheek-volume-decr": 0.3,
    "cheek/r-cheek-volume-decr": 0.3,
    "eyes/l-eye-bag-decr": 0.8, "eyes/r-eye-bag-decr": 0.8,
    "head/head-invertedtriangular": 0.25,
}


def head(strength: float = 1.0, extra: dict | None = None) -> dict:
    """`HEAD` times `strength`, with `extra` {"group/target": weight} added (or overriding), for human.make(targets=)."""
    out = {k: v * strength for k, v in HEAD.items()}
    out.update(extra or {})
    return out


def landmarks(person) -> dict:
    """The eyes' centres (left at +x), their midpoint, the distance between them (the eye unit) and their radius."""
    eyes = person.parts["eyes"]
    obs = eyes if isinstance(eyes, (list, tuple)) else [eyes]
    co = np.concatenate([np.array([v.co[:] for v in ob.data.vertices]) for ob in obs])
    left, lr = human.fit_sphere(co[co[:, 0] > 0])
    right, _ = human.fit_sphere(co[co[:, 0] <= 0])
    mid, unit = (left + right) / 2, float(np.linalg.norm(left - right))
    mouth = mid + np.array([0.0, -0.2 * unit, -1.25 * unit])
    g = person.body.vertex_groups.get("lips")
    if g is not None:
        lips = [v.co[:] for v in person.body.data.vertices if any(x.group == g.index and x.weight > 0.5 for x in v.groups)]
        if lips:
            mouth = np.mean(lips, axis=0)
    return {"left": left, "right": right, "mid": mid, "unit": unit, "radius": lr, "mouth": mouth}


def _blur(h, sigma: float):
    """A Gaussian blur of a grid (sigma in cells), NaNs (no surface) ignored and kept."""
    if sigma <= 0:
        return h
    m = ~np.isnan(h)
    v = np.where(m, h, 0.0)
    r = int(3 * sigma) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)

    def conv(x):
        x = np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), 0, x)
        return np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), 1, x)
    num, den = conv(v), conv(m.astype(float))
    out = num / np.maximum(den, 1e-9)
    out[~m] = np.nan
    return out


def _filter(h, size: int, op):
    """A square min or max filter of a grid (NaNs ignored)."""
    pad = np.pad(h, size, mode="edge")
    stack = [pad[size + dy:size + dy + h.shape[0], size + dx:size + dx + h.shape[1]]
             for dy in range(-size, size + 1) for dx in range(-size, size + 1)]
    return op(np.stack(stack), axis=0)


@dataclass
class _Field:
    x0: float
    z0: float
    step: float
    depth: np.ndarray       # the surface's y seen from the front (NaN: none)
    target: np.ndarray      # its smoothed y

    def sample(self, grid, x, z):
        fx, fz = (x - self.x0) / self.step, (z - self.z0) / self.step
        i, j = int(np.floor(fz)), int(np.floor(fx))
        if i < 0 or j < 0 or i + 1 >= grid.shape[0] or j + 1 >= grid.shape[1]:
            return np.nan
        a, b = fz - i, fx - j
        q = grid[i:i + 2, j:j + 2]
        return (q[0, 0] * (1 - a) * (1 - b) + q[0, 1] * (1 - a) * b + q[1, 0] * a * (1 - b) + q[1, 1] * a * b)


def _ellipse(X, Z, cx, cz, rx, rz, feather: float = 0.35):
    r = np.sqrt(((X - cx) / rx) ** 2 + ((Z - cz) / rz) ** 2)
    return 1 - _smoothstep(1 - feather, 1.0, r)


def smooth(person, *, eyes: float = 1.0, mouth: float = 1.0, nose: float = 0.6, rest: float = 0.5, nostrils: bool = True,
           step: float = 0.0012, depth: float = 0.065) -> _Field:
    """Smooth the face into one clean surface as seen from the front (the rest pose, in place): the eye sockets filled
    to the lids (`eyes`), the lips flattened (`mouth`), the nose softened (`nose`), the rest of the face eased
    (`rest`), each 0..1; `nostrils`: the base of the nose (the nostrils, the folds of its wings) laid smooth too, so
    the nose is one small anime bump. Only what the front sees moves, and only toward or away from it, so the face's
    outline stays. Returns the smoothed surface (a front-view depth field) for decals to lie on."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    lm = landmarks(person)
    mid, u = lm["mid"], lm["unit"]
    me = person.body.data
    bvh = BVHTree.FromPolygons([v.co[:] for v in me.vertices], [p.vertices[:] for p in me.polygons])
    x0, x1 = mid[0] - 1.45 * u, mid[0] + 1.45 * u
    z0, z1 = mid[2] - 2.5 * u, mid[2] + 1.45 * u
    xs = np.arange(x0, x1, step)
    zs = np.arange(z0, z1, step)
    D = np.full((len(zs), len(xs)), np.nan)
    front = mid[1] - 0.3
    for i, z in enumerate(zs):
        for j, x in enumerate(xs):
            hit = bvh.ray_cast(Vector((x, front, z)), Vector((0.0, 1.0, 0.0)), 0.6)
            if hit[0] is not None and hit[0].y < mid[1] + depth:
                D[i, j] = hit[0].y
    h = -D                                   # height toward the front
    cell = lambda m: max(1, int(round(m / step)))   # noqa: E731
    closed = _filter(_filter(np.nan_to_num(h, nan=-1.0), cell(0.006), np.max), cell(0.006), np.min)   # pits filled
    flat = _filter(_filter(closed, cell(0.004), np.min), cell(0.004), np.max)                        # bumps taken off
    eye_h = _blur(np.where(np.isnan(h), np.nan, closed), 0.004 / step)
    mouth_h = _blur(np.where(np.isnan(h), np.nan, flat), 0.004 / step)
    nose_h = _blur(h, 0.003 / step)
    rest_h = _blur(h, 0.002 / step)
    X, Z = np.meshgrid(xs, zs)
    L, R = lm["left"], lm["right"]
    w_eye = np.maximum(_ellipse(X, Z, L[0], L[2] + 0.04 * u, 0.42 * u, 0.32 * u), _ellipse(X, Z, R[0], R[2] + 0.04 * u, 0.42 * u, 0.32 * u))
    w_mouth = _ellipse(X, Z, mid[0], mid[2] - 1.3 * u, 0.55 * u, 0.3 * u)
    w_nose = _ellipse(X, Z, mid[0], mid[2] - 0.75 * u, 0.3 * u, 0.5 * u)
    w_face = _ellipse(X, Z, mid[0], mid[2] - 0.6 * u, 1.05 * u, 1.75 * u, feather=0.3)
    target = h.copy()
    for zone, w, k in ((rest_h, w_face, rest), (nose_h, w_nose * w_face, nose), (mouth_h, w_mouth, mouth), (eye_h, w_eye, eyes)):
        ok = ~np.isnan(zone) & ~np.isnan(target)
        target[ok] = target[ok] + (zone[ok] - target[ok]) * (w[ok] * k)
    fld = _Field(float(xs[0]), float(zs[0]), step, D, -target)
    # move what the front sees onto the smoothed surface
    for v in me.vertices:
        x, y, z = v.co
        if not (x0 < x < x1 and z0 < z < z1):
            continue
        d = fld.sample(D, x, z)
        tgt = fld.sample(fld.target, x, z)
        if np.isnan(d) or np.isnan(tgt) or abs(y - d) > 0.0025:
            continue
        v.co.y = float(tgt)
    # the sockets and the seam of the lips still fold behind the surface: cut them out and lay fresh patches over them
    mo = lm["mouth"]
    zones = [(L[0], L[2] + 0.03 * u, 0.36 * u, 0.27 * u), (R[0], R[2] + 0.03 * u, 0.36 * u, 0.27 * u)] if eyes > 0 else []
    if mouth > 0:
        zones.append((float(mo[0]), float(mo[2]), 0.4 * u, 0.17 * u))
    if nostrils:
        zones.append((mid[0], mid[2] - 0.74 * u, 0.3 * u, 0.13 * u))
    if zones:
        _patch(me, fld, zones, mid[1] + 0.05)
    me.update()
    return fld


def _patch(me, fld: _Field, zones, front_y: float, relax: int = 24, cuts: int = 4):
    """Replace the faces of `me` in each zone ((x, z) ellipses: cx, cz, rx, rz) in front of `front_y` with fresh
    patches lying on the smoothed surface, so nothing folds there (a socket, the lips' seam) to draw a line."""
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(me)

    def inside(p, k: float = 1.0):
        return any(((p.x - cx) / (rx * k)) ** 2 + ((p.z - cz) / (rz * k)) ** 2 < 1.0 for cx, cz, rx, rz in zones)

    def hidden(p):
        """Just behind the smoothed surface: what is left of a pocket (a nostril, the mouth), which would cut through
        a patch and draw a line (not the back of the head: that is far behind)."""
        t = fld.sample(fld.target, p.x, p.z)
        return not np.isnan(t) and t + 0.0015 < p.y < t + 0.045

    kill = [f for f in bm.faces if (f.calc_center_median().y < front_y and inside(f.calc_center_median()))
            or (inside(f.calc_center_median(), 1.5) and hidden(f.calc_center_median()))]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # the holes left, each a loop of boundary edges
    edges = {e for e in bm.edges if e.is_boundary}
    loops = []
    while edges:
        e0 = edges.pop()
        loop, todo = {e0}, [e0]
        while todo:
            e = todo.pop()
            for v in e.verts:
                for e2 in v.link_edges:
                    if e2 in edges:
                        edges.discard(e2)
                        loop.add(e2)
                        todo.append(e2)
        loops.append(loop)
    for loop in loops:
        rim = {v for e in loop for v in e.verts}
        dev = [abs(v.co.y - fld.sample(fld.target, v.co.x, v.co.z)) for v in rim]
        dev = [d for d in dev if not np.isnan(d)]
        if not dev or float(np.median(dev)) > 0.004:
            continue            # the back of a pocket left inside the head: unseen
        for v in bm.verts:          # mark what is there (element references do not survive the ops below)
            v.tag = True
        rim_co = [v.co.copy() for v in rim]
        res = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=list(loop))
        new_faces = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]
        if not new_faces:
            continue
        nf = set(new_faces)
        inner = [e for e in {e for f in new_faces for e in f.edges} if len(e.link_faces) == 2 and all(f in nf for f in e.link_faces)]
        if inner:
            bmesh.ops.subdivide_edges(bm, edges=inner, cuts=cuts, use_grid_fill=True)
        fresh = [v for v in bm.verts if not v.tag]
        rim_set = {tuple(round(c, 7) for c in co) for co in rim_co}
        # spread them evenly over the hole, then lay them on the surface
        for _ in range(relax):
            for v in fresh:
                ns = [e.other_vert(v) for e in v.link_edges]
                if ns:
                    v.co.x = sum(n.co.x for n in ns) / len(ns)
                    v.co.z = sum(n.co.z for n in ns) / len(ns)
        for v in fresh:
            t = fld.sample(fld.target, v.co.x, v.co.z)
            if not np.isnan(t):
                v.co.y = float(t)
        fresh_set = set(fresh)
        for f in bm.faces:
            if any(v in fresh_set or tuple(round(c, 7) for c in v.co) in rim_set for v in f.verts):
                f.smooth = True
        for v in bm.verts:
            v.tag = False
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()


# ---------------------------------------------------------------------------------------------------- shading

def _proxy(person, name: str, center, radii):
    import bmesh
    import bpy

    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=32, radius=1.0)
    for v in bm.verts:
        v.co.x, v.co.y, v.co.z = center[0] + v.co.x * radii[0], center[1] + v.co.y * radii[1], center[2] + v.co.z * radii[2]
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    person.coll.objects.link(ob)
    ob.hide_render = True
    ob.display_type = "WIRE"
    _no_lines(ob)
    human.bind(ob, person.rig, "head")
    return ob


def _no_lines(ob):
    """Leave `ob` out of the line art (drawn decals, proxies)."""
    try:
        ob.lineart.usage = "EXCLUDE"
    except (AttributeError, TypeError):
        pass


def _transfer_normals(ob, proxy, group: str | None = None):
    """`ob`'s normals taken from `proxy` (a modifier after its skinning, before any subdivision)."""
    import bpy

    mod = ob.modifiers.new("face-normals", "DATA_TRANSFER")
    mod.object = proxy
    mod.use_loop_data = True
    mod.data_types_loops = {"CUSTOM_NORMAL"}
    mod.loop_mapping = "POLYINTERP_NEAREST"
    if group:
        mod.vertex_group = group
    # after the armature, before the subdivision
    arm = next((i for i, m in enumerate(ob.modifiers) if m.type == "ARMATURE"), -1)
    with human._ctx(ob):
        while ob.modifiers.find(mod.name) > arm + 1:
            bpy.ops.object.modifier_move_up(modifier=mod.name)
    for m in ob.modifiers:
        if m.type == "SUBSURF":
            m.use_custom_normals = True
    return mod


def shade(person, *, back: float = 0.55, size=(1.45, 1.9, 2.35), bias: float = 0.3, marks: bool = True):
    """Shade the face like a drawing: its normals taken from an ellipsoid riding on the head bone (centred `back` eye
    units behind the eyes, `size` eye units across, deep and tall), over the face and fading out toward the ears, the
    hairline and the neck; `bias` added to the light the face reads (toon.BIAS), so it stays lit with a small shadow on
    its far side rather than split in half; with `marks` its faces marked `freestyle_face`, so the line art draws none
    of the nose's or the lips' geometry (the drawing does, and the outline hull its silhouette). Returns the proxy
    (other drawn parts of the face take their normals from it too)."""
    lm = landmarks(person)
    mid, u = lm["mid"], lm["unit"]
    center = (mid[0], mid[1] + back * u, mid[2] - 0.35 * u)
    radii = (size[0] * u, size[1] * u, size[2] * u)
    proxy = _proxy(person, f"{person.name}-face-proxy", center, radii)
    body = person.body
    g = body.vertex_groups.get("face-normals") or body.vertex_groups.new(name="face-normals")
    co = np.array([v.co[:] for v in body.data.vertices])
    X, Y, Z = co[:, 0], co[:, 1], co[:, 2]
    w = _ellipse(X, Z, mid[0], mid[2] - 0.55 * u, 1.25 * u, 1.85 * u, feather=0.4) * (1 - _smoothstep(mid[1] + 0.25 * u, mid[1] + 0.9 * u, Y))
    for i in np.nonzero(w > 0.001)[0]:
        g.add([int(i)], float(w[i]), "REPLACE")
    _transfer_normals(body, proxy, "face-normals")
    me = body.data
    if bias:
        from . import toon

        att = me.attributes.get(toon.BIAS) or me.attributes.new(toon.BIAS, "FLOAT", "POINT")
        att.data.foreach_set("value", (w * bias).astype(np.float32))
    if marks:
        fm = me.attributes.get("freestyle_face") or me.attributes.new("freestyle_face", "BOOLEAN", "FACE")
        front = mid[1] + 0.2 * u
        fm.data.foreach_set("value", [bool(np.mean(w[list(p.vertices)]) > 0.45 and p.center.y < front) for p in me.polygons])
        # the outline hull (lib/outline.py) thinned over the wings of the nose and the folds beside them, where it
        # peeked out of their hollows as dots; the drawing draws the nose. The middle (the nose's and the lips' profile)
        # keeps its line
        nb = np.maximum(_ellipse(X, Z, mid[0] + 0.42 * u, mid[2] - 0.9 * u, 0.4 * u, 0.36 * u, feather=0.5),
                        _ellipse(X, Z, mid[0] - 0.42 * u, mid[2] - 0.9 * u, 0.4 * u, 0.36 * u, feather=0.5))
        nb = nb * (1 - _ellipse(X, Z, mid[0], mid[2] - 0.86 * u, 0.07 * u, 0.6 * u, feather=0.6)) * (Y < mid[1] + 0.1 * u)
        sg = body.vertex_groups.get("outline-scale") or body.vertex_groups.new(name="outline-scale")
        for i in np.nonzero(nb > 0.001)[0]:
            sg.add([int(i)], float(1.0 - 0.9 * nb[i]), "REPLACE")
    person.parts["face-proxy"] = proxy
    return proxy


# ---------------------------------------------------------------------------------------------------- the decal

def _image(name: str, rgba: np.ndarray):
    import bpy

    h, w = rgba.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Linear Rec.709"
    # premultiplied: a straight-alpha float image sparkles along its edges under linear filtering (the colour divided
    # by an alpha near nothing)
    img.alpha_mode = "PREMUL"
    pre = rgba.astype(np.float32).copy()
    pre[..., :3] *= pre[..., 3:4]
    img.pixels.foreach_set(pre.ravel())
    img.pack()
    return img


def _decal_material(name: str, img, look, *, cut: float = 0.4, shade: float = 0.72, bias: float = 0.0, far_img=None,
                    lod=(3.8, 5.8)):
    """The decal's toon material: the drawing, cel shaded (its shade `shade` times its colour; `bias` added to the
    light it reads, as the face's skin has), faded to the fog, whitening with a lightning flash where it is light (the
    ink stays ink), transparent where nothing is drawn. With `far_img` (the bolder drawing) it turns from the drawing
    to that one as the camera goes from `lod[0]` to `lod[1]` metres away."""
    import bpy

    from . import toon

    look = look or toon.Look()
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    uv = nt.nodes.new("ShaderNodeUVMap")

    def texture(image):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = image
        t.interpolation = "Linear"
        t.extension = "CLIP"
        nt.links.new(uv.outputs[0], t.inputs["Vector"])
        return t

    near = texture(img)
    color, alpha = near.outputs["Color"], near.outputs["Alpha"]
    if far_img is not None:
        far = texture(far_img)
        cam = nt.nodes.new("ShaderNodeCameraData")
        k = nt.nodes.new("ShaderNodeMapRange")
        k.interpolation_type = "SMOOTHSTEP"
        k.inputs["From Min"].default_value = lod[0]
        k.inputs["From Max"].default_value = lod[1]
        nt.links.new(cam.outputs["View Distance"], k.inputs["Value"])
        mc = nt.nodes.new("ShaderNodeMix")
        mc.data_type = "RGBA"
        nt.links.new(k.outputs["Result"], mc.inputs["Factor"])
        nt.links.new(color, mc.inputs["A"])
        nt.links.new(far.outputs["Color"], mc.inputs["B"])
        ma = nt.nodes.new("ShaderNodeMix")
        ma.data_type = "FLOAT"
        nt.links.new(k.outputs["Result"], ma.inputs["Factor"])
        nt.links.new(alpha, ma.inputs["A"])
        nt.links.new(far.outputs["Alpha"], ma.inputs["B"])
        color, alpha = mc.outputs["Result"], ma.outputs["Result"]
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(diff.outputs[0], s2r.inputs[0])
    lum = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(s2r.outputs["Color"], lum.inputs[0])
    lb = nt.nodes.new("ShaderNodeMath")
    lb.operation = "ADD"
    lb.inputs[1].default_value = bias
    nt.links.new(lum.outputs[0], lb.inputs[0])
    band = nt.nodes.new("ShaderNodeMapRange")
    band.interpolation_type = "SMOOTHSTEP"
    band.inputs["From Min"].default_value = cut - 0.02
    band.inputs["From Max"].default_value = cut + 0.02
    band.inputs["To Min"].default_value = shade
    nt.links.new(lb.outputs[0], band.inputs["Value"])
    lit = nt.nodes.new("ShaderNodeVectorMath")
    lit.operation = "SCALE"
    nt.links.new(color, lit.inputs[0])
    nt.links.new(band.outputs["Result"], lit.inputs["Scale"])
    # a flash whitens the light of the drawing, not its ink
    bright = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(color, bright.inputs[0])
    keep = nt.nodes.new("ShaderNodeMapRange")
    keep.inputs["From Min"].default_value = 0.05
    keep.inputs["From Max"].default_value = 0.3
    nt.links.new(bright.outputs[0], keep.inputs["Value"])
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = look.flash_amount
    nt.links.new(toon.scene_value(nt), k.inputs[0])
    k2 = nt.nodes.new("ShaderNodeMath")
    k2.operation = "MULTIPLY"
    nt.links.new(k.outputs[0], k2.inputs[0])
    nt.links.new(keep.outputs["Result"], k2.inputs[1])
    fl = nt.nodes.new("ShaderNodeMix")
    fl.data_type = "RGBA"
    nt.links.new(k2.outputs[0], fl.inputs["Factor"])
    nt.links.new(lit.outputs[0], fl.inputs["A"])
    fl.inputs["B"].default_value = (*look.flash_lit, 1.0)
    col = toon._fog_mix(nt, fl.outputs["Result"], look)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(alpha, mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "DITHERED"
    return mat


def draw(person, face: Face, *, look=None, name: str | None = None, extent=(-1.3, 1.3, -2.4, 1.4), res: int = 640,
         lift: float = 0.00035, facing: float = 0.3, cells: float = 0.0016, proxy=None, far=True, far_k: float = 2.2,
         far_res: int = 256, lod=(3.8, 5.8), bias: float = 0.3):
    """Draw `face` on the person: its drawing (`drawing`'s texture over `extent`, eye units round the eyes' midpoint)
    on a decal lying `lift` off the smoothed face (smooth's field, else the face as it is), only where the face looks
    within acos(`facing`) of the front, bound to the head, its normals from the face's proxy (shade) so it shades with
    the face (`bias` as its skin's); no line art of its own. `far`: a second drawing for the face small on screen
    (True: `face.bolder(far_k)`; or a Face), turned to as the camera goes from `lod[0]` to `lod[1]` metres away."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    from . import shapes

    name = name or f"{person.name}-face"
    lm = landmarks(person)
    mid, u = lm["mid"], lm["unit"]
    x0, x1, z0, z1 = extent
    nx = max(8, int((x1 - x0) * u / cells))
    nz = max(8, int((z1 - z0) * u / cells))
    me = person.body.data
    bvh = BVHTree.FromPolygons([v.co[:] for v in me.vertices], [p.vertices[:] for p in me.polygons])
    verts, uvs, ok = [], [], []
    front = mid[1] - 0.3
    for i in range(nz + 1):
        for j in range(nx + 1):
            fu, fv = j / nx, i / nz
            x = mid[0] + (x0 + (x1 - x0) * fu) * u
            z = mid[2] + (z0 + (z1 - z0) * fv) * u
            hit = bvh.ray_cast(Vector((x, front, z)), Vector((0.0, 1.0, 0.0)), 0.6)
            good = hit[0] is not None and hit[0].y < mid[1] + 0.06 and -hit[1].y > facing
            if good:
                p, n = hit[0], hit[1]
                verts.append(tuple(p + n * lift))
            else:
                verts.append((x, mid[1], z))
            uvs.append((fu, fv))
            ok.append(good)
    faces = []
    row = nx + 1
    for i in range(nz):
        for j in range(nx):
            q = (i * row + j, i * row + j + 1, (i + 1) * row + j + 1, (i + 1) * row + j)
            if all(ok[k] for k in q):
                faces.append(q)
    img = _image(f"{name}-drawing", drawing(face, extent=extent, res=res))
    far_img = None
    if far:
        far_face = face.bolder(far_k) if far is True else far
        far_img = _image(f"{name}-drawing-far", drawing(far_face, extent=extent, res=far_res))
    mat = _decal_material(f"{name}-drawing", img, look, bias=bias, far_img=far_img, lod=lod)
    ob = shapes.mesh_object(name, verts, faces, mat, person.coll, smooth=True)
    uvl = ob.data.uv_layers.new(name="UVMap")
    for loop in ob.data.loops:
        uvl.data[loop.index].uv = uvs[loop.vertex_index]
    # drop the vertices no face uses
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    ob.visible_shadow = False
    _no_lines(ob)
    human.bind(ob, person.rig, "head")
    proxy = proxy or person.parts.get("face-proxy")
    if proxy is not None:
        _transfer_normals(ob, proxy)
    ob["decal"] = True
    person.parts[name] = ob
    return ob


def apply(person, face: Face, *, look=None, smooth_args: dict | None = None, shade_args: dict | None = None,
          draw_args: dict | None = None, eye_material=None, bias: float = 0.3) -> list:
    """The whole anime face: MakeHuman's eyeballs (fitted, then hidden: they stay as the eyes' landmarks) and lashes
    (gone), the face smoothed, shaded from its proxy (kept lit by `bias`) and drawn, near and far. Returns the eyeball
    objects (person.parts["eyes"])."""
    import bpy

    eyes = person.parts.get("eyes")
    if not isinstance(eyes, (list, tuple)):
        mat = eye_material or bpy.data.materials.new(f"{person.name}-eyeball")
        eyes = human.eyes(person, mat)
    for e in eyes:
        e.hide_render = True
        e.visible_shadow = False
        _no_lines(e)
    person.discard("lashes")
    smooth(person, **(smooth_args or {}))
    shade(person, **{"bias": bias, **(shade_args or {})})
    draw(person, face, look=look, **{"bias": bias, **(draw_args or {})})
    return eyes
