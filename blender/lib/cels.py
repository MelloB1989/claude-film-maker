"""Drawn characters: 2D drawings of ink lines, flat colour fills and cel shadows, built from code as Grease Pencil, the
way a TV anime draws its cast over its backgrounds.

A `Drawing` is one frame of a character: named layers bottom to top, each a list of `Fill`s and `Line`s in the
drawing's own units (x right, y up). A layer can be clipped to others (`mask`): a cel shadow drawn inside the skin, an
iris inside the eye's white, a sheen inside the hair. `build(name, {frame: Drawing})` turns drawings keyed by frame into
one Grease Pencil object; a drawing holds until the next, so one every other frame animates "on twos" (`twos`).

The pieces, all numpy:
- `spline(points, closed=, corners=)`: a smooth curve through points (centripetal Catmull-Rom), sharp at `corners`;
  `between` (a run of a closed outline: a contour's visible part), `resample`, `lengths`, `normals`, `offset`.
- `ellipse`, `arc`, `ribbon(centre, widths)`: a closed oval, an open arc, a band of varying width round a centre line.
- `line(...)`, `fill(...)`: a tapered ink `Line` (thin at the ends, `taper`) and a flat `Fill`, from control points.
- `lock(root_a, root_b, tip)`: a drawn lock of hair, two roots drawn to a point (`Lock.inner`: its shaded half).
- `zig`, `teeth`: jagged edges (a shadow's, a ring of light's); `drop`: a bead of water on a surface.
- `Eye`: an anime eye drawn round its centre: white, iris, pupil, highlights, the lash line and its flick, the lower
  lid, the crease; opens and closes (`open`) and looks about (`look`).
- `bend`, `wave`, `blend`: motion: points swung about a root (more toward the tip), a travelling wave along a line,
  two drawings of the same points in between; `Drawing.shift` (a breath), `Drawing.recolor` (a grade).
- `move`, `mirror`: placing pieces; `rgb`, `linear`, `mix`: colours as sRGB hex or tuples (Grease Pencil wants them
  linear); `flash`: a colour in a lightning flash.

`build` runs in Blender. Grease Pencil only hides behind the scene's meshes with the view layer's Z pass on, which
`build` turns on. Drawings are unlit (`use_lights` off): every shade in them is drawn.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

Color = "str | tuple[float, float, float]"
INK = "#14121a"


def rgb(c) -> tuple[float, float, float]:
    """An sRGB colour, '#rrggbb' or (r, g, b) in 0..1, as a tuple in 0..1 (still sRGB)."""
    if isinstance(c, str):
        h = c.lstrip("#")
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return tuple(float(v) for v in c[:3])


def linear(c) -> tuple[float, float, float]:
    """An sRGB colour in linear light, for Grease Pencil."""
    out = []
    for v in rgb(c):
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def mix(a, b, t: float) -> tuple[float, float, float]:
    """Colours mixed in sRGB (the way a painter's palette mixes)."""
    a, b = rgb(a), rgb(b)
    return tuple(x + (y - x) * t for x, y in zip(a, b))


FLASH_LIT = "#eef2ff"     # what a lightning flash bleaches lit colours toward
FLASH_DARK = "#232b4a"    # ... and sinks shades toward


def flash(color, amount: float, kind: str = "lit") -> tuple[float, float, float]:
    """A colour in a lightning flash, `amount` 0..1: a lit colour ("lit") bleached toward a cold white, a shade
    ("shade") sunk toward a cold dark, the hard contrast an anime lightning frame draws; ink ("ink") stays."""
    if amount <= 0 or kind == "ink":
        return rgb(color)
    a = min(1.0, float(amount))
    return mix(color, FLASH_LIT, a * 0.85) if kind == "lit" else mix(color, FLASH_DARK, a * 0.65)


# ---------------------------------------------------------------------------------------------------- curves

def _arr(points) -> np.ndarray:
    p = np.asarray(points, dtype=float)
    if p.ndim != 2 or p.shape[1] != 2:
        raise ValueError(f"points must be (n, 2), got {p.shape}")
    return p


def _catmull(P: np.ndarray, step: float, alpha: float = 0.5) -> np.ndarray:
    """A centripetal Catmull-Rom curve through the open chain P (ends extended by reflection), sampled about every
    `step`, every control point on it."""
    if len(P) < 2:
        return P.copy()
    ext = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = [P[:1]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        chord = float(np.linalg.norm(p2 - p1))
        n = max(1, int(math.ceil(chord / step)))
        d01 = max(np.linalg.norm(p1 - p0) ** alpha, 1e-9)
        d12 = max(chord ** alpha, 1e-9)
        d23 = max(np.linalg.norm(p3 - p2) ** alpha, 1e-9)
        t0, t1 = 0.0, d01
        t2, t3 = t1 + d12, t1 + d12 + d23
        t = np.linspace(t1, t2, n + 1)[1:, None]
        a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
        a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
        a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
        b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
        b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
        out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    return np.vstack(out)


def spline(points, *, closed: bool = False, corners=(), step: float = 0.004) -> np.ndarray:
    """A smooth curve through `points`, sampled about every `step`; at the indices in `corners` it turns sharply
    (a chin, a lash's flick, a lock's tip). Closed curves don't repeat their first point at the end."""
    P = _arr(points)
    n = len(P)
    if n < 3:
        return P.copy() if not closed else P.copy()
    cs = sorted({c % n for c in corners})
    if closed and not cs:
        # wrap: two points of context each side, keep the middle
        ext = np.vstack([P[-2:], P, P[:3]])
        cur = _catmull(ext, step)
        # the samples from ext[2] (P[0]) to ext[n+2] (P[0] again)
        idx = _sample_index(ext, step)
        return cur[idx[2]:idx[n + 2]]
    if closed:
        P = np.roll(P, -cs[0], axis=0)
        cs = [c - cs[0] for c in cs] + [n]
        P = np.vstack([P, P[:1]])
    else:
        cs = [0] + [c for c in cs if 0 < c < n - 1] + [n - 1]
    parts = []
    for a, b in zip(cs[:-1], cs[1:]):
        seg = _catmull(P[a:b + 1], step)
        parts.append(seg if not parts else seg[1:])
    out = np.vstack(parts)
    if not closed:
        return out
    out = out[:-1]
    # start where the points did (the curve passes through every control point)
    first = _arr(points)[0]
    return np.roll(out, -int(np.argmin(np.linalg.norm(out - first, axis=1))), axis=0)


def _sample_index(P: np.ndarray, step: float) -> list[int]:
    """Where each control point of P lands in `_catmull(P, step)`'s samples."""
    idx = [0]
    for i in range(len(P) - 1):
        n = max(1, int(math.ceil(float(np.linalg.norm(P[i + 1] - P[i])) / step)))
        idx.append(idx[-1] + n)
    return idx


def between(P, start, end) -> np.ndarray:
    """The run of the closed outline P from its point nearest `start` forward to its point nearest `end` (wrapping
    round): an ink line along part of a fill's edge (the cheek and jaw of a face whose top is under the hair)."""
    P = _arr(P)
    i = int(np.argmin(np.linalg.norm(P - np.asarray(start, float), axis=1)))
    j = int(np.argmin(np.linalg.norm(P - np.asarray(end, float), axis=1)))
    return np.vstack([P[i:j + 1]]) if j >= i else np.vstack([P[i:], P[:j + 1]])


def resample(P, n: int) -> np.ndarray:
    """The polyline P as n points evenly spaced along it."""
    P = _arr(P)
    s = lengths(P)
    u = np.linspace(0.0, s[-1], n)
    return np.c_[np.interp(u, s, P[:, 0]), np.interp(u, s, P[:, 1])]


def ellipse(center, rx: float, ry: float, *, rotate: float = 0.0, n: int = 72, start: float = 0.0) -> np.ndarray:
    """A closed oval round `center`, `rotate` degrees, starting `start` degrees round."""
    a = np.radians(start) + np.linspace(0, 2 * math.pi, n, endpoint=False)
    return _rot(np.c_[rx * np.cos(a), ry * np.sin(a)], rotate) + np.asarray(center, float)


def arc(center, rx: float, ry: float, a0: float, a1: float, *, rotate: float = 0.0, n: int = 48) -> np.ndarray:
    """Part of an oval, from `a0` to `a1` degrees (counterclockwise from +x)."""
    a = np.radians(np.linspace(a0, a1, n))
    return _rot(np.c_[rx * np.cos(a), ry * np.sin(a)], rotate) + np.asarray(center, float)


def _rot(P: np.ndarray, deg: float) -> np.ndarray:
    if not deg:
        return P
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.c_[c * P[:, 0] - s * P[:, 1], s * P[:, 0] + c * P[:, 1]]


def lengths(P) -> np.ndarray:
    """Distance along the polyline P at each point (0 at the first)."""
    P = _arr(P)
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]


def normals(P) -> np.ndarray:
    """Unit normals along the polyline P (its direction turned a quarter counterclockwise: the left side)."""
    P = _arr(P)
    d = np.gradient(P, axis=0)
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    return np.c_[-d[:, 1], d[:, 0]]


def ribbon(center, widths) -> np.ndarray:
    """A closed band round the centre line `center`, `widths` across (one number or one per point; 0 comes to a
    point): a tail of cloth, a lash line, a sword."""
    C = _arr(center)
    w = np.broadcast_to(np.asarray(widths, float), (len(C),))
    N = normals(C)
    left = C + N * (w[:, None] / 2)
    right = C - N * (w[:, None] / 2)
    return np.vstack([left, right[::-1]])


def taper(P, start: float = 0.2, end: float = 0.2, tip: float = 0.1) -> np.ndarray:
    """A line's width along P, 0..1: from `tip` at the ends up to full over the first `start` and last `end`
    fractions of its length (a brush pressed in and lifted)."""
    s = lengths(P)
    s = s / s[-1] if s[-1] > 0 else np.zeros_like(s)
    w = np.ones_like(s)
    for frac, x in ((start, s), (end, 1 - s)):
        if frac > 0:
            e = np.sin(np.clip(x / frac, 0, 1) * math.pi / 2)
            w = np.minimum(w, tip + (1 - tip) * e)
    return w


# ---------------------------------------------------------------------------------------------------- pieces

@dataclass
class Line:
    """An ink line: dense points (n, 2), its width in drawing units, a colour."""
    points: np.ndarray
    width: float = 0.01
    color: object = INK
    widths: np.ndarray | None = None   # 0..1 along the line (taper), times `width`
    closed: bool = False
    opacity: float = 1.0


@dataclass
class Fill:
    """A flat fill: a closed outline (n, 2) without holes or crossings, a colour."""
    points: np.ndarray
    color: object = "#ffffff"
    opacity: float = 1.0


def line(points, width: float = 0.01, color=INK, *, taper_=(0.2, 0.2), tip: float = 0.1, corners=(),
         closed: bool = False, smooth: bool = True, step: float = 0.004, opacity: float = 1.0) -> Line:
    """An ink line through control points: smooth (sharp at `corners`), tapering in over the first `taper_[0]` and
    out over the last `taper_[1]` of its length."""
    P = spline(points, closed=closed, corners=corners, step=step) if smooth else _arr(points)
    w = taper(P, *taper_, tip=tip) if not closed else np.ones(len(P))
    return Line(P, width, color, w, closed, opacity)


def fill(points, color="#ffffff", *, corners=(), smooth: bool = True, step: float = 0.004, opacity: float = 1.0) -> Fill:
    """A flat fill inside a closed curve through control points (sharp at `corners`)."""
    P = spline(points, closed=True, corners=corners, step=step) if smooth else _arr(points)
    return Fill(P, color, opacity)


def outline(f: Fill, width: float = 0.01, color=INK, **kw) -> Line:
    """An ink line round a fill."""
    return Line(f.points.copy(), width, color, np.ones(len(f.points)), True, kw.get("opacity", 1.0))


@dataclass
class Lock:
    """A drawn lock of hair (or any shape coming to a point): side `a` from its first root to the tip, side `b` from
    the tip back to its second root."""
    a: np.ndarray
    b: np.ndarray

    @property
    def outline(self) -> np.ndarray:
        """The closed outline: side a, then side b (the tip once)."""
        return np.vstack([self.a, self.b[1:]])

    @property
    def tip(self) -> np.ndarray:
        return self.a[-1]

    def inner(self, k: float, side: str = "a") -> np.ndarray:
        """A narrower shape inside the lock sharing its tip: side `side` drawn `k` of the way toward the other, the
        other kept (the lock's shaded half, or its sheen)."""
        n = max(len(self.a), len(self.b), 16)
        A = resample(self.a, n)                  # root a -> tip
        B = resample(self.b[::-1], n)            # root b -> tip
        if side == "a":
            m = A + (B - A) * k
            return np.vstack([m, B[::-1][1:-1]])
        m = B + (A - B) * k
        return np.vstack([A, m[::-1][1:-1]])

    def edge(self, side: str = "a") -> np.ndarray:
        """One side as an open line, root to tip."""
        return self.a.copy() if side == "a" else self.b[::-1].copy()


def lock(root_a, root_b, tip, *, bow: float = 0.12, bow_b: float | None = None, curl: float = 0.0,
         step: float = 0.004) -> Lock:
    """A drawn lock of hair from two roots to a point: each side bows out from the lock's middle by `bow` of its
    length (`bow_b` for the second side; negative: in), `curl` (signed, in lengths) swings both sides' middles the
    same way, a lock sweeping round."""
    a, b, t = (np.asarray(v, float) for v in (root_a, root_b, tip))
    mid = (a + b) / 2

    def bulge(p, q, amount):
        d = q - p
        L = float(np.linalg.norm(d)) or 1.0
        n = np.array([-d[1], d[0]]) / L
        c = p + d * 0.5
        # outward: away from the root pair's middle line toward the root this side starts from
        out = n if np.dot(n, p - mid) >= 0 else -n
        swing = np.array([-(t - mid)[1], (t - mid)[0]])
        swing = swing / (np.linalg.norm(swing) or 1.0)
        return c + out * amount * L + swing * curl * L

    sa = bulge(a, t, bow)
    sb = bulge(b, t, bow if bow_b is None else bow_b)
    A = spline([a, sa, t], step=step)
    B = spline([t, sb, b], step=step)
    return Lock(A, B)


def offset(P, depth) -> np.ndarray:
    """The open line P pushed `depth` to its left (one number or one per point; negative: right)."""
    P = _arr(P)
    dep = np.broadcast_to(np.asarray(depth, float), (len(P),))
    return P + normals(P) * dep[:, None]


def zig(P, depth: float, count: int, *, jitter: float = 0.0, seed: int = 0, sharp: float = 0.5,
        base: float = 0.25) -> np.ndarray:
    """The open line P made a row of `count` teeth reaching `depth` to its right (negative: left), from `base` of
    that between them: a jagged edge. `sharp` 0..1: rounded to pointed; `jitter` varies their reach."""
    P = resample(P, max(count * 10, 16))
    rng = np.random.default_rng(seed)
    u = np.linspace(0, 1, len(P))
    k = (u * count) % 1.0
    tooth = (1.0 - np.abs(2 * k - 1)) ** (1.0 + 2.0 * sharp)   # 0 between, 1 at the points
    var = 1.0 + jitter * rng.uniform(-1, 1, count + 1)[np.minimum((u * count).astype(int), count)]
    return P - normals(P) * (depth * (base + (1 - base) * tooth) * var)[:, None]


def teeth(P, depth: float, count: int, **kw) -> np.ndarray:
    """A band hanging off the open line P (to its right) whose far edge is a row of `count` teeth (`zig`): anime
    hair's ring of light, a shadow's jagged edge, a straw fringe. Returns the closed outline (P, then the teeth)."""
    Q = resample(P, max(count * 10, 16))
    return np.vstack([Q, zig(P, depth, count, **kw)[::-1]])


def drop(center, r: float, *, body="#9fb0d0", light="#ffffff", ink=INK, stretch: float = 1.25,
         opacity: float = 0.8) -> list:
    """A bead of water on a surface, drawn the anime way: a body a little darker than what it sits on (`body`), a
    bright point of light up and to the left, an ink arc under its lower right; `stretch` draws it taller than wide
    (a drop starting to run)."""
    c = np.asarray(center, float)
    rim = arc(c, r, r * stretch, -105, 15, n=16)
    return [Fill(ellipse(c, r, r * stretch, n=24), body, opacity=opacity),
            Fill(ellipse(c + [-0.35 * r, 0.42 * r * stretch], 0.27 * r, 0.32 * r, n=12), light),
            Line(rim, r * 0.28, ink, taper(rim, 0.45, 0.45, tip=0.0))]


def _closed_normals(P: np.ndarray) -> np.ndarray:
    d = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    return np.c_[-d[:, 1], d[:, 0]]


def soft(points, color="#000000", *, spread: float = 0.05, opacity: float = 1.0, steps: int | None = None, corners=(),
         smooth: bool = True, step: float = 0.004) -> list:
    """An airbrushed shape: the closed curve through `points` with its edge softened over `spread` (half inside the
    curve, half outside), as `steps` stacked fills, each a little bigger, that build to `opacity` in its middle: a
    blush, the soft shadow under a jaw, a gradient of light, the glow round a lantern. `steps` defaults to one per
    0.006 of spread (fewer band visibly). Keep `spread` small beside the shape's narrow parts (a concave outline pushed
    far out crosses itself); clip it with a mask."""
    P = spline(points, closed=True, corners=corners, step=step) if smooth else _arr(points)
    area = 0.5 * float(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))
    out = -1.0 if area > 0 else 1.0       # the normals are the left side: inward round a counterclockwise outline
    N = _closed_normals(P) * out
    steps = max(2, int(steps if steps is not None else round(spread / 0.006)))
    a = 1.0 - (1.0 - min(max(opacity, 0.0), 0.999)) ** (1.0 / steps)
    return [Fill(P + N * (spread * (k / (steps - 1) - 0.5)), color, a) for k in range(steps)]


def hatch(box, *, angle: float = 45.0, spacing: float = 0.02, width: float = 0.004, color=INK, jitter: float = 0.25,
          seed: int = 0, opacity: float = 1.0, taper_=(0.35, 0.35)) -> list:
    """Parallel ink strokes `spacing` apart across the box (x0, y0, x1, y1) at `angle` degrees from +x, each a little
    uneven in place and reach (`jitter`, of the spacing), tapered at both ends: the hatching a manga inks its deep
    shadows and rough cloth with. Clip it to the shadow it darkens with a mask."""
    x0, y0, x1, y1 = (float(v) for v in box)
    c = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
    half = math.hypot(x1 - x0, y1 - y0) / 2
    rng = np.random.default_rng(seed)
    t = math.radians(angle)
    along, across = np.array([math.cos(t), math.sin(t)]), np.array([-math.sin(t), math.cos(t)])
    out = []
    for k in range(int(2 * half / spacing) + 1):
        o = -half + k * spacing + jitter * spacing * rng.uniform(-0.5, 0.5)
        p0, d = c + across * o - along * half, along * 2 * half
        # the stroke's run inside the box (Liang-Barsky), then a little short of it at either end
        t0, t1 = 0.0, 1.0
        for dv, lo, hi, pv in ((d[0], x0, x1, p0[0]), (d[1], y0, y1, p0[1])):
            if abs(dv) < 1e-12:
                if not lo <= pv <= hi:
                    t0, t1 = 1.0, 0.0
                continue
            a, b = (lo - pv) / dv, (hi - pv) / dv
            t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
        if t1 - t0 < 1e-6:
            continue
        span = t1 - t0
        t0 += span * jitter * rng.uniform(0, 0.2)
        t1 -= span * jitter * rng.uniform(0, 0.2)
        P = resample(np.array([p0 + d * t0, p0 + d * t1]), 12)
        out.append(Line(P, width, color, taper(P, *taper_, tip=0.0), False, opacity))
    return out


def zig_down(P, depth: float, count: int, **kw) -> np.ndarray:
    """`zig` with its teeth hanging down (-y) whichever way the line runs, in the line's own order."""
    P = _arr(P)
    if P[-1, 0] >= P[0, 0]:
        return zig(P, depth, count, **kw)
    return zig(P[::-1], depth, count, **kw)[::-1]


def fringe(top, hang, count: int, *, splay=(0.0, 0.0), tooth: float = 0.07, seed: int = 0, jitter: float = 0.3,
           sharp: float = 0.85) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Something hanging from the line through `top` in `count` uneven points: a row of a straw cape, thatch at an
    eave, a grass skirt, a fur trim. It hangs `hang` down (one number or one per point), its far end splayed by
    `splay` (x, y), the points reaching `tooth` past that. Returns the closed outline, the top line and the line the
    points hang from (the last two the same length, in `top`'s order)."""
    T = resample(spline(top), max(count * 6, 24))
    u = np.linspace(0, 1, len(T))[:, None]
    h = np.broadcast_to(np.asarray(hang, float), (len(T),))
    B = T + np.c_[np.zeros(len(T)), -h] + np.asarray(splay, float) * u
    Bz = zig_down(B, tooth, count, seed=seed, jitter=jitter, sharp=sharp, base=0.0)
    return np.vstack([T, Bz[::-1]]), T, B


# ---------------------------------------------------------------------------------------------------- motion

def bend(points, root, angle: float, *, reach: float | None = None, power: float = 1.6) -> np.ndarray:
    """`points` swung `angle` degrees about `root`, the swing growing from nothing at the root to all of it `reach`
    away (default: the farthest point): hair, a sleeve, a tail of cloth in the wind."""
    P = _arr(points)
    r = np.asarray(root, float)
    v = P - r
    d = np.linalg.norm(v, axis=1)
    L = reach or float(d.max()) or 1.0
    a = np.radians(angle) * np.clip(d / L, 0, 1) ** power
    c, s = np.cos(a), np.sin(a)
    return r + np.c_[c * v[:, 0] - s * v[:, 1], s * v[:, 0] + c * v[:, 1]]


def wave(points, amp: float, wavelength: float, phase: float, *, power: float = 1.0) -> np.ndarray:
    """A travelling wave along the polyline `points`: each point pushed sideways by `amp`, growing from its first
    point (pinned) as (s/L)**power; advance `phase` (radians) over time to make it travel."""
    P = _arr(points)
    s = lengths(P)
    L = s[-1] or 1.0
    off = amp * (s / L) ** power * np.sin(2 * math.pi * s / wavelength - phase)
    return P + normals(P) * off[:, None]


def blend(a, b, t: float) -> np.ndarray:
    """Two drawings of the same points, `t` of the way from a to b."""
    return _arr(a) + (_arr(b) - _arr(a)) * t


def move(points, offset=(0.0, 0.0), *, scale=1.0, rotate: float = 0.0, about=(0.0, 0.0)) -> np.ndarray:
    """Points scaled and turned about `about`, then moved by `offset`."""
    P = _arr(points)
    o = np.asarray(about, float)
    return _rot((P - o) * np.asarray(scale, float), rotate) + o + np.asarray(offset, float)


def mirror(points, x: float = 0.0) -> np.ndarray:
    """Points mirrored across the vertical line at `x` (the order reversed, so outlines keep their winding)."""
    P = _arr(points)
    return np.c_[2 * x - P[:, 0], P[:, 1]][::-1]


def twos(f0: int, f1: int, step: int = 2) -> list[int]:
    """Drawing frames from f0 up to (not including) f1, one every `step`: animation on twos (or threes...)."""
    return list(range(int(f0), int(f1), int(step)))


# ---------------------------------------------------------------------------------------------------- an eye

@dataclass
class Eye:
    """An anime eye in drawing units round `center`: `side` +1 has its outer corner toward +x, -1 toward -x. Its
    shape is drawn in eye widths: the inner corner at (0, 0), the outer at (1, tilt); the upper lid peaks `peak` along
    at `height`, the lower lid sags `lower` of it."""
    center: tuple = (0.0, 0.0)
    width: float = 0.3
    side: int = 1
    height: float = 0.36               # the opening, over the width
    tilt: float = 0.06                 # the outer corner's rise, over the width
    peak: float = 0.42                 # where the upper lid is highest (0 inner .. 1 outer)
    flat: float = 0.0                  # 0..1: the upper lid pulled straight (a hard, narrowed look)
    lower: float = 0.55                # the lower lid's sag, over the height
    open: float = 1.0                  # 1 open .. 0 shut (the upper lid comes down)
    look: tuple = (0.0, 0.0)           # the iris's shift, in eye widths (x toward the outer corner)
    iris: float = 0.44                 # its radius across, over the width
    iris_tall: float = 1.15            # its height over its width
    pupil: float = 0.4                 # over the iris
    lights: tuple = ((-0.35, 0.38, 0.24), (0.38, -0.42, 0.1))   # highlights: (x, y in iris radii, r in iris radii)
    white: object = "#e9e6ee"
    white_shade: object = "#a9a9c2"    # the lid's shadow over the white
    shade: float = 0.38                # that shadow's depth below the lid, over the height
    iris_dark: object = "#2a1b17"
    iris_light: object = "#7a4a2c"
    pupil_color: object = "#0d0a0c"
    light: object = "#ffffff"
    lash: float = 0.075                # the lash line's thickness at its thickest, over the width
    lash_inner: float = 0.35           # ... at the inner corner, over that
    flick: tuple = (0.16, 18.0)        # the outer flick's length (widths) and angle down from the lid's end (deg)
    lower_lash: tuple | None = (0.45, 1.0, 0.018)   # from, to along the lower lid, thickness over the width
    crease: float = 0.0                # the lid crease's height above the lid, over the height (0: none)
    ink: object = INK

    def _to(self, P) -> np.ndarray:
        P = _arr(P) * self.width
        P[:, 0] -= 0.5 * self.width
        if self.side < 0:
            P[:, 0] = -P[:, 0]
        return P + np.asarray(self.center, float)

    def lids(self, n: int = 40) -> tuple[np.ndarray, np.ndarray]:
        """The upper and lower lid lines, inner corner to outer, in eye widths."""
        h, k = self.height, self.tilt
        x = np.linspace(0.0, 1.0, n)
        base = k * x
        # upper: a skewed arch peaking at `peak`, pulled flatter by `flat`
        u = np.where(x < self.peak, x / self.peak, (1 - x) / (1 - self.peak))
        arch = np.sin(np.clip(u, 0, 1) * math.pi / 2) ** (1.0 + 1.5 * self.flat)
        up = base + h * arch
        lo = base - h * self.lower * np.sin(x * math.pi) ** 0.8
        # closing: the upper lid comes down toward the lower
        up = lo + (up - lo) * np.clip(self.open, 0.0, 1.0)
        return np.c_[x, up], np.c_[x, lo]

    def pieces(self) -> dict[str, list]:
        """The eye's pieces by layer: "eye_white" (the opening), "eye_iris" (iris, pupil, the lid's shadow: clip it to
        "eye_white"), "eye_light" (highlights, also clipped) and "eye_lines" (the lash line, its flick, the lower lid,
        the crease)."""
        up, lo = self.lids()
        out = {"eye_white": [], "eye_iris": [], "eye_light": [], "eye_lines": []}
        opening = np.vstack([up, lo[::-1][1:-1]])
        if self.open > 0.04:
            out["eye_white"].append(Fill(self._to(opening), self.white))
            # the lid's shadow along the top of the white
            sh = np.vstack([up, (up - np.c_[np.zeros(len(up)), np.full(len(up), self.height * self.shade)])[::-1]])
            out["eye_iris"].append(Fill(self._to(sh), self.white_shade))
            r = self.iris
            cx = 0.5 + self.look[0]
            cy = self.tilt * 0.5 + self.height * 0.18 + self.look[1]
            iris = np.c_[cx + r * np.cos(np.linspace(0, 2 * math.pi, 64, endpoint=False)),
                         cy + r * self.iris_tall * np.sin(np.linspace(0, 2 * math.pi, 64, endpoint=False))]
            out["eye_iris"].append(Fill(self._to(iris), self.iris_light))
            dark = np.c_[cx + r * 0.98 * np.cos(np.linspace(0, 2 * math.pi, 64, endpoint=False)),
                         cy + r * 0.25 + r * self.iris_tall * 0.78 * np.sin(np.linspace(0, 2 * math.pi, 64, endpoint=False))]
            out["eye_iris"].append(Fill(self._to(dark), self.iris_dark))
            pr = r * self.pupil
            pupil = np.c_[cx + pr * np.cos(np.linspace(0, 2 * math.pi, 48, endpoint=False)),
                          cy + pr * self.iris_tall * np.sin(np.linspace(0, 2 * math.pi, 48, endpoint=False))]
            out["eye_iris"].append(Fill(self._to(pupil), self.pupil_color))
            # the lid's shadow again over the iris, darker
            out["eye_iris"].append(Fill(self._to(sh), self.iris_dark, opacity=0.45))
            for lx, ly, lr in self.lights:
                c = (cx + lx * r, cy + ly * r * self.iris_tall)
                out["eye_light"].append(Fill(self._to(ellipse(c, lr * r, lr * r * 1.1, n=32)), self.light))
        # the lash line: thick along the upper lid, thin at the inner corner, flicking out at the outer
        x = up[:, 0]
        thick = self.lash * (self.lash_inner + (1 - self.lash_inner) * np.clip(x / 0.75, 0, 1) ** 0.8)
        thick[-1] *= 0.7
        top = up + np.c_[np.zeros(len(up)), thick]
        fl_len, fl_ang = self.flick
        end = up[-1]
        d = up[-1] - up[-4]
        d = d / (np.linalg.norm(d) or 1.0)
        a = math.radians(-fl_ang)
        dirn = np.array([d[0] * math.cos(a) - d[1] * math.sin(a), d[0] * math.sin(a) + d[1] * math.cos(a)])
        tip = end + dirn * fl_len
        lash = np.vstack([up[:1] + [-0.01, 0.0], up[1:], [tip], top[::-1]])
        out["eye_lines"].append(Fill(self._to(lash), self.ink))
        if self.lower_lash and self.open > 0.04:
            a0, a1, t = self.lower_lash
            sel = lo[(lo[:, 0] >= a0) & (lo[:, 0] <= a1)]
            if len(sel) > 2:
                w = taper(sel, 0.5, 0.15, tip=0.05)
                out["eye_lines"].append(Line(self._to(sel), t * self.width, self.ink, w))
        if self.crease > 0 and self.open > 0.3:
            cr = up[int(len(up) * 0.25):int(len(up) * 0.9)] + [0.0, self.height * self.crease]
            out["eye_lines"].append(Line(self._to(cr), 0.012 * self.width, self.ink, taper(cr, 0.4, 0.4, tip=0.0)))
        return out


# ---------------------------------------------------------------------------------------------------- a drawing

@dataclass
class Layer:
    name: str
    pieces: list = field(default_factory=list)
    mask: tuple = ()                   # layer names to clip to ("!name": outside it)


class Drawing:
    """One frame of a drawn character: layers bottom to top. `add(layer, *pieces, mask=)` appends pieces to a layer
    (made on first use, on top); `eye(e)` adds an `Eye`'s pieces to its layers, the iris and lights clipped to the
    white; `bounds()` is the drawing's extent."""

    def __init__(self):
        self.layers: dict[str, Layer] = {}

    def layer(self, name: str, mask=()) -> Layer:
        if name not in self.layers:
            self.layers[name] = Layer(name, [], tuple(mask))
        elif mask:
            self.layers[name].mask = tuple(mask)
        return self.layers[name]

    def add(self, name: str, *pieces, mask=()) -> "Drawing":
        L = self.layer(name, mask)
        for p in pieces:
            if isinstance(p, (list, tuple)):
                L.pieces.extend(p)
            else:
                L.pieces.append(p)
        return self

    def eye(self, e: Eye, prefix: str = "") -> "Drawing":
        parts = e.pieces()
        self.add(prefix + "eye_white", parts["eye_white"])
        self.add(prefix + "eye_iris", parts["eye_iris"], mask=(prefix + "eye_white",))
        self.add(prefix + "eye_light", parts["eye_light"], mask=(prefix + "eye_white",))
        self.add(prefix + "eye_lines", parts["eye_lines"])
        return self

    def bounds(self) -> tuple[float, float, float, float]:
        pts = [p.points for L in self.layers.values() for p in L.pieces if len(p.points)]
        if not pts:
            return (0.0, 0.0, 0.0, 0.0)
        P = np.vstack(pts)
        return float(P[:, 0].min()), float(P[:, 1].min()), float(P[:, 0].max()), float(P[:, 1].max())

    def counts(self) -> dict[str, int]:
        return {n: len(L.pieces) for n, L in self.layers.items()}

    def shift(self, dx: float = 0.0, dy: float = 0.0, layers=None) -> "Drawing":
        """Every piece (or those on `layers`) moved by (dx, dy): a breath, a settle, a shake."""
        for n, L in self.layers.items():
            if layers is None or n in layers:
                for p in L.pieces:
                    p.points = _arr(p.points) + (dx, dy)
        return self

    def recolor(self, fn) -> "Drawing":
        """Every piece's colour passed through `fn(color) -> color` (a lightning flash, a night grade)."""
        for L in self.layers.values():
            for p in L.pieces:
                p.color = fn(p.color)
        return self


def order(drawings) -> list[str]:
    """Every layer name across drawings, bottom to top: each drawing's order kept, new names placed after the layer
    they follow in the drawing that has them."""
    names: list[str] = []
    for d in drawings:
        prev = None
        for n in d.layers:
            if n not in names:
                names.insert(names.index(prev) + 1 if prev in names else len(names), n)
            prev = n
    return names


# ---------------------------------------------------------------------------------------------------- Blender

def _attr(D, name: str, kind: str, domain: str):
    a = D.attributes.get(name)
    if a is None:
        a = D.attributes.new(name, kind, domain)
    return a


def _strokes(pieces, scale: float, tint=None):
    """Flatten pieces into stroke arrays: points (N, 3), radius (N), point rgba (N, 4), and per stroke: sizes,
    cyclic, fill flag, fill rgba, fill opacity."""
    pos, rad, pcol, popa = [], [], [], []
    sizes, cyc, isfill, fcol, fopa = [], [], [], [], []
    for p in pieces:
        P = _arr(p.points)
        if len(P) < 2:
            continue
        n = len(P)
        col = p.color if tint is None else tint(p.color)
        lin = (*linear(col), 1.0)
        pos.append(np.c_[P[:, 0] * scale, np.zeros(n), P[:, 1] * scale])
        sizes.append(n)
        if isinstance(p, Fill):
            rad.append(np.full(n, 0.0005 * scale))
            pcol.append(np.tile(lin, (n, 1)))
            popa.append(np.full(n, p.opacity))
            cyc.append(True)
            isfill.append(True)
            fcol.append(lin)
            fopa.append(p.opacity)
        else:
            w = p.widths if p.widths is not None else np.ones(n)
            rad.append(np.asarray(w, float) * p.width * 0.5 * scale)
            pcol.append(np.tile(lin, (n, 1)))
            popa.append(np.full(n, p.opacity))
            cyc.append(bool(p.closed))
            isfill.append(False)
            fcol.append((0.0, 0.0, 0.0, 0.0))
            fopa.append(1.0)
    if not sizes:
        return None
    return dict(pos=np.vstack(pos), rad=np.concatenate(rad), pcol=np.vstack(pcol), popa=np.concatenate(popa),
                sizes=sizes, cyc=np.array(cyc), fill=np.array(isfill), fcol=np.array(fcol, float),
                fopa=np.array(fopa, float))


def _write(D, s) -> None:
    D.add_strokes(s["sizes"])
    D.attributes["position"].data.foreach_set("vector", s["pos"].astype(np.float32).ravel())
    _attr(D, "radius", "FLOAT", "POINT").data.foreach_set("value", s["rad"].astype(np.float32))
    _attr(D, "opacity", "FLOAT", "POINT").data.foreach_set("value", s["popa"].astype(np.float32))
    _attr(D, "vertex_color", "FLOAT_COLOR", "POINT").data.foreach_set("color", s["pcol"].astype(np.float32).ravel())
    _attr(D, "cyclic", "BOOLEAN", "CURVE").data.foreach_set("value", s["cyc"])
    ids = np.where(s["fill"], np.cumsum(s["fill"]), 0).astype(np.int32)
    _attr(D, "fill_id", "INT", "CURVE").data.foreach_set("value", ids)
    _attr(D, "hide_stroke", "BOOLEAN", "CURVE").data.foreach_set("value", s["fill"])
    _attr(D, "fill_color", "FLOAT_COLOR", "CURVE").data.foreach_set("color", s["fcol"].astype(np.float32).ravel())
    _attr(D, "fill_opacity", "FLOAT", "CURVE").data.foreach_set("value", s["fopa"].astype(np.float32))
    _attr(D, "material_index", "INT", "CURVE").data.foreach_set("value", np.zeros(len(s["sizes"]), np.int32))
    D.tag_positions_changed()


def build(name: str, drawings, *, collection=None, scale: float = 1.0, tint=None, scene=None):
    """One Grease Pencil object drawing `drawings` ({frame: Drawing}, or one Drawing for frame 1) in its local x-z
    plane (drawing x to +x, y to +z, seen from -y), `scale` metres per drawing unit. `tint(color) -> color`, if
    given, recolours every piece (a night grade, a flash). Layers keep their order; masks clip as declared."""
    import bpy

    if isinstance(drawings, Drawing):
        drawings = {1: drawings}
    frames = sorted(drawings)
    scene = scene or bpy.context.scene
    for vl in scene.view_layers:
        vl.use_pass_z = True  # Grease Pencil is depth tested against the scene only with the Z pass

    gp = bpy.data.grease_pencils.new(name)
    gp.stroke_depth_order = "2D"
    ob = bpy.data.objects.new(name, gp)
    (collection or scene.collection).objects.link(ob)
    ob.use_grease_pencil_lights = False
    mat = bpy.data.materials.get("cel") or bpy.data.materials.new("cel")
    if mat.grease_pencil is None:
        bpy.data.materials.create_gpencil_data(mat)
        mat.grease_pencil.color = (1, 1, 1, 1)
        mat.grease_pencil.fill_color = (1, 1, 1, 1)
    gp.materials.append(mat)

    names = order([drawings[f] for f in frames])
    layers = {}
    for n in names:
        L = gp.layers.new(n)
        L.use_lights = False
        layers[n] = L
    masks = {}
    for f in frames:
        for n, spec in drawings[f].layers.items():
            if spec.mask:
                masks[n] = spec.mask
    for n, ms in masks.items():
        L = layers[n]
        L.use_masks = True
        for m in ms:
            inv = m.startswith("!")
            target = layers.get(m.lstrip("!"))
            if target is None:
                continue
            slot = L.mask_layers.add(target)
            if inv:
                slot.invert = True
    for f in frames:
        d = drawings[f]
        for n in names:
            D = layers[n].frames.new(int(f)).drawing
            spec = d.layers.get(n)
            if spec is None or not spec.pieces:
                continue
            s = _strokes(spec.pieces, scale, tint)
            if s is not None:
                _write(D, s)
    return ob


def add_layer(ob, name: str, drawings, *, scale: float = 1.0, mask=(), tint=None):
    """A layer on top of the Grease Pencil object `ob` (made by `build`) with drawings of its own ({frame: [pieces]}):
    a layer timed apart from the rest, say rain on ones over a character drawn on twos. `mask`: layer names to clip
    it to (their union; "!name": outside it). Returns the layer."""
    gp = ob.data
    L = gp.layers.new(name)
    L.use_lights = False
    if mask:
        L.use_masks = True
        for m in mask:
            target = gp.layers.get(m.lstrip("!"))
            if target is None or target == L:
                continue
            slot = L.mask_layers.add(target)
            if m.startswith("!"):
                slot.invert = True
    for f in sorted(drawings):
        D = L.frames.new(int(f)).drawing
        s = _strokes(list(drawings[f]), scale, tint)
        if s is not None:
            _write(D, s)
    return L


def bolt(start, end, *, width: float = 0.03, glow: float = 4.0, branches: int = 3, seed: int = 1, depth: int = 6,
         rough: float = 0.22, core="#ffffff", halo="#c9d6ff", halo_opacity: float = 0.35) -> Drawing:
    """A fork of lightning drawn from `start` (the sky) down to `end`, in drawing units: a jagged white core `width`
    across, tapering to its foot, over a pale halo `glow` times as wide; `branches` shorter forks off its upper half.
    Crisp, as anime draws it however far away it strikes. Layers "bolt_halo" and "bolt"."""
    rng = np.random.default_rng(seed)

    def jag(a, b, depth_, rough_, seed_):
        r = np.random.default_rng(seed_)
        pts = np.array([a, b], float)
        for _ in range(depth_):
            out = [pts[0]]
            for p, q in zip(pts[:-1], pts[1:]):
                dv = q - p
                side = np.array([-dv[1], dv[0]])
                n = np.linalg.norm(side)
                side = side / n if n > 1e-12 else side
                out.append((p + q) / 2 + side * np.linalg.norm(dv) * rough_ * r.uniform(-1, 1))
                out.append(q)
            pts = np.array(out)
        return pts

    a, b = np.asarray(start, float), np.asarray(end, float)
    main = jag(a, b, depth, rough, seed)
    forks = [(main, width)]
    for k in range(branches):
        i = int(rng.uniform(0.12, 0.55) * len(main))
        reach = np.linalg.norm(b - a) * rng.uniform(0.18, 0.35)
        ang = rng.uniform(0.35, 0.9) * (1 if rng.uniform() < 0.5 else -1)
        down = (b - a) / (np.linalg.norm(b - a) or 1.0)
        c, s = math.cos(ang), math.sin(ang)
        tip = main[i] + reach * np.array([c * down[0] - s * down[1], s * down[0] + c * down[1]])
        forks.append((jag(main[i], tip, max(3, depth - 2), rough * 1.3, seed + 17 * (k + 1)), width * 0.5))
    d = Drawing()
    for pts, w in forks:
        u = np.linspace(0.0, 1.0, len(pts))
        d.add("bolt_halo", Line(pts, w * glow, halo, 1.0 - 0.7 * u, False, halo_opacity))
        d.add("bolt", Line(pts, w, core, 1.0 - 0.8 * u))
    return d


# ---------------------------------------------------------------------------------------------------- texture

def pressure(P, *, amount: float = 0.3, waves: float = 3.0, seed: int = 0) -> np.ndarray:
    """A hand's pressure along the line P, about 1: a smooth wander of `amount` either way, `waves` swells along its
    length. Multiply a taper by it for an inked line that thickens and thins as a brush does."""
    s = lengths(P)
    u = s / s[-1] if s[-1] > 0 else np.zeros(len(s))
    rng = np.random.default_rng(seed)
    w = np.zeros_like(u)
    for k in range(1, 4):
        w += rng.uniform(-1, 1) / k * np.sin(2 * math.pi * (waves * k * u + rng.uniform()))
    return 1.0 + amount * w / 1.84


def strands(a, b, count: int, *, width: float = 0.003, color=INK, seed: int = 0, reach=(0.0, 1.0),
            jitter: float = 0.5, bow: float = 0.0, opacity=1.0, colors=None, tip: float = 0.0) -> list:
    """`count` fine strands running from the line `a` toward the line `b` (both open, drawn the same way round),
    each at its own place along them and starting and stopping at its own fraction of the way across (within
    `reach`), bowed `bow` of its length to its left: the hairs of a combed lock, the straws of a thatch, the fibres of
    rough cloth. `colors` (a list) gives each its colour from them in turn at random; `opacity` a number or a
    (low, high) range."""
    A, B = resample(a, 64), resample(b, 64)
    rng = np.random.default_rng(seed)
    out = []
    lo, hi = reach
    for k in range(count):
        u = (k + 0.5 + rng.uniform(-0.5, 0.5) * jitter) / count
        i = min(62, max(0, int(u * 63)))
        f = u * 63 - i
        p = A[i] + (A[i + 1] - A[i]) * f
        q = B[i] + (B[i + 1] - B[i]) * f
        s0 = lo + (hi - lo) * rng.uniform(0, 0.35) * jitter
        s1 = hi - (hi - lo) * rng.uniform(0, 0.35) * jitter
        p0, p1 = p + (q - p) * s0, p + (q - p) * s1
        d = p1 - p0
        n = np.array([-d[1], d[0]])
        mid = (p0 + p1) / 2 + n * bow * rng.uniform(0.5, 1.5)
        P = spline([p0, mid, p1], step=max(float(np.linalg.norm(d)) / 12, 1e-4))
        col = colors[int(rng.integers(len(colors)))] if colors else color
        op = rng.uniform(*opacity) if isinstance(opacity, tuple) else opacity
        out.append(Line(P, width * rng.uniform(0.6, 1.2), col, taper(P, 0.3, 0.4, tip=tip), False, float(op)))
    return out


def ragged(P, depth: float, count: int, *, seed: int = 0, vary: float = 0.6, sharp: float = 0.8,
           base: float = 0.15) -> np.ndarray:
    """The open line P made a ragged edge reaching `depth` to its right: `count` points of uneven width, reach (down
    to `1 - vary` of `depth`) and spacing, overlapping where they crowd, `base` of the depth between them: the ends of
    wet straw, a torn hem, a fringe of hair. Unlike `zig` no two teeth are alike."""
    Q = resample(P, max(count * 14, 32))
    u = lengths(Q)
    u = u / u[-1] if u[-1] > 0 else np.zeros(len(Q))
    rng = np.random.default_rng(seed)
    centres = np.sort((np.arange(count) + 0.5 + rng.uniform(-0.45, 0.45, count)) / count)
    reach = depth * (1 - vary * rng.uniform(0, 1, count) ** 1.5)
    half = rng.uniform(0.55, 1.25, count) / count
    dep = np.full(len(Q), depth * base)
    for c, r, h in zip(centres, reach, half):
        x = np.clip(1 - np.abs(u - c) / h, 0, 1) ** (1 + 2.5 * sharp)
        dep = np.maximum(dep, r * x)
    dep[0], dep[-1] = 0.0, 0.0
    return Q - normals(Q) * dep[:, None]


def drip(point, t: float, *, period: float = 1.6, r: float = 0.012, fall: float = 0.25, phase: float = 0.0,
         body="#a9b4c6", light="#ffffff", ink=INK, opacity: float = 0.85) -> list:
    """Water dripping off a point (a straw's end, a chin, an eave) at time `t` seconds: a bead swelling there over
    each `period`, then letting go and falling `fall` below as a short streak; `phase` (0..1) staggers drips."""
    p = np.asarray(point, float)
    k = (t / period + phase) % 1.0
    out = []
    if k < 0.8:                                     # swelling, sagging as it grows
        g = (k / 0.8) ** 0.7
        rr = r * (0.35 + 0.65 * g)
        st = 1.15 + 0.35 * g
        out += drop(p + [0.0, -rr * st], rr, body=body, light=light, ink=ink, stretch=st, opacity=opacity)
    else:                                           # falling: a streak below the point, and a small bead left
        g = (k - 0.8) / 0.2
        y = fall * g ** 1.6
        streak = np.array([p + [0.0, -y - r * 0.4], p + [0.0, -y - r * 0.4 - r * (2 + 4 * g)]])
        out.append(Line(streak, r * 0.9, body, np.array([1.0, 0.2]), False, opacity))
        out += drop(p + [0.0, -r * 0.4], r * 0.35, body=body, light=light, ink=ink, opacity=opacity)
    return out


def lit_widths(P, light=(0.0, 1.0), *, closed: bool = True, outward: int = 1, lit: float = 0.35,
               dark: float = 1.3) -> np.ndarray:
    """A contour's weight along P, as a light falls on it: `lit` where the contour faces the direction `light`, `dark`
    where it faces away, smoothly between. Closed: P's outward side is found; open: `outward` says which side is out
    (1 its left, -1 its right). The way an inker lifts the brush on a lit edge and presses into a shadowed one."""
    P = _arr(P)
    if closed:
        area = 0.5 * float(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))
        N = _closed_normals(P) * (-1.0 if area > 0 else 1.0)
    else:
        N = normals(P) * float(outward)
    L = np.asarray(light, float)
    L = L / (np.linalg.norm(L) or 1.0)
    k = np.clip((N @ L + 1.0) / 2.0, 0.0, 1.0) ** 1.4    # 1 facing the light .. 0 facing away
    w = dark + (lit - dark) * k
    n = min(7, len(w))                                       # eased: no step where the outline turns a corner
    ker = np.ones(n) / n
    if closed:
        w = np.convolve(np.r_[w[-n:], w, w[:n]], ker, "same")[n:-n]
    else:
        w = np.convolve(np.r_[np.full(n, w[0]), w, np.full(n, w[-1])], ker, "same")[n:-n]
    return w


def contour(points, width: float = 0.01, color=INK, *, light=(0.0, 1.0), lit: float = 0.35, dark: float = 1.3,
            opacity: float = 1.0) -> Line:
    """A closed ink line round the outline `points` (a fill's), its weight following the light (`lit_widths`):
    thin on the edges facing `light`, heavy on those turned from it."""
    P = _arr(points)
    return Line(P, width, color, lit_widths(P, light, lit=lit, dark=dark), True, opacity)


def brush(points, width: float = 0.01, color=INK, *, gaps=(), amount: float = 0.25, waves: float = 2.5, seed: int = 0,
          taper_=(0.2, 0.2), tip: float = 0.1, lift: float = 0.18, corners=(), smooth: bool = True,
          step: float = 0.004, opacity: float = 1.0) -> list:
    """An inked line drawn by hand: `line`'s taper times a brush's `pressure` (`amount`, `waves`, `seed`), lifted off
    the page over each of `gaps` ((start, end) fractions of its length: where light catches the edge it draws), each
    run tapering over `lift` of its length where the brush lifts and comes down again. Returns its Lines."""
    P = spline(points, corners=corners, step=step) if smooth else _arr(points)
    s = lengths(P)
    u = s / s[-1] if s[-1] > 0 else np.zeros(len(P))
    w = taper(P, *taper_, tip=tip) * pressure(P, amount=amount, waves=waves, seed=seed)
    keep = np.ones(len(P), bool)
    for a, b in gaps:
        keep &= ~((u > a) & (u < b))
    idx = np.flatnonzero(keep)
    out = []
    for run in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []:
        if len(run) < 2:
            continue
        Q = P[run]
        ww = w[run] * taper(Q, lift if run[0] > 0 else 0.0, lift if run[-1] < len(P) - 1 else 0.0, tip=0.0)
        out.append(Line(Q, width, color, ww, False, opacity))
    return out


def strips(a, b, count: int, *, seed: int = 0, vary: float = 0.4, sway: float = 0.0, n: int = 64) -> list:
    """The band between two open lines `a` and `b` (drawn the same way round) cut lengthwise into `count` strips
    of uneven width (`vary`), their dividing lines wandering across by up to `sway` of a strip's width: the clumps
    of hair combed back between a hairline and a crown, the pleats of a skirt, a thatch's bundles. Returns each
    strip's closed outline, from the `a` side to the `b` side."""
    A, B = resample(a, n), resample(b, n)
    rng = np.random.default_rng(seed)
    w = 1.0 + vary * rng.uniform(-1, 1, count)
    cuts = np.r_[0.0, np.cumsum(w) / w.sum()]
    u = np.linspace(0.0, 1.0, n)
    lines = []
    for k, c in enumerate(cuts):
        if 0 < k < count:
            c = c + sway / count * np.sin(2 * math.pi * (u * rng.uniform(0.6, 1.4) + rng.uniform()))
        lines.append(A + (B - A) * np.clip(c, 0.0, 1.0)[..., None] if np.ndim(c) else A + (B - A) * c)
    return [np.vstack([lines[k], lines[k + 1][::-1]]) for k in range(count)]


def lumpy(P, amp: float, bumps: float = 4.0, *, seed: int = 0, ends: float = 0.08) -> np.ndarray:
    """The open line P pushed to its left by smooth uneven bumps (`bumps` along it, up to `amp`, negative: right),
    held at its ends over the first and last `ends` of its length: a bundle's outline, a heap, a sagging hem."""
    P = _arr(P)
    s = lengths(P)
    u = s / s[-1] if s[-1] > 0 else np.zeros(len(P))
    rng = np.random.default_rng(seed)
    w = np.zeros(len(P))
    for k in range(1, 4):
        w += rng.uniform(0.3, 1.0) / k * np.sin(2 * math.pi * (bumps * k * 0.5 * u + rng.uniform()))
    w = np.abs(w) / 1.4
    hold = np.clip(np.minimum(u, 1 - u) / max(ends, 1e-9), 0, 1) if ends > 0 else 1.0
    return P + normals(P) * (amp * np.clip(w, 0, 1) * hold)[:, None]


def clumps(P, depth: float, count: int, *, fine: float = 0.35, fine_count: int | None = None, seed: int = 0,
           vary: float = 0.7, sharp: float = 0.9) -> np.ndarray:
    """The open line P made a hanging edge of clumps, `depth` to its right: `count` clumps of uneven width and reach,
    each split into finer points (`fine` of the depth, `fine_count` of them in all), the way wet straw, matted fur or
    a frayed hem hangs. Like `ragged` at two scales."""
    Q = resample(P, max(count, fine_count or count * 4) * 12 + 16)
    s = lengths(Q)
    u = s / s[-1] if s[-1] > 0 else np.zeros(len(Q))
    rng = np.random.default_rng(seed)
    dep = np.zeros(len(Q))
    for n, d, sh in ((count, depth * (1 - fine), 0.4), (fine_count or count * 4, depth * fine, sharp)):
        centres = np.sort((np.arange(n) + 0.5 + rng.uniform(-0.45, 0.45, n)) / n)
        reach = d * (1 - vary * rng.uniform(0, 1, n) ** 1.5)
        half = rng.uniform(0.55, 1.3, n) / n
        layer = np.zeros(len(Q))
        for c, r, h in zip(centres, reach, half):
            layer = np.maximum(layer, r * np.clip(1 - np.abs(u - c) / h, 0, 1) ** (1 + 2.5 * sh))
        dep += layer
    dep[0], dep[-1] = 0.0, 0.0
    return Q - normals(Q) * dep[:, None]


def tufts(P, count: int, *, length=(0.03, 0.08), width=(0.02, 0.05), droop: float = 0.5, seed: int = 0,
          side: int = 1, reach=(0.05, 0.95)) -> list:
    """`count` tufts sticking out of the open line P to its left (`side` -1: right), each a narrow wedge `width`
    across its root on the line and `length` long (ranges), bent down toward -y by `droop` (0 straight out, 1 hanging
    down), at random places within `reach` of its length: straw sticking out of a thatch, fur off a pelt. Returns
    their closed outlines (root, tip, root)."""
    P = _arr(P)
    s = lengths(P)
    u = s / s[-1] if s[-1] > 0 else np.zeros(len(P))
    N = normals(P) * side
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(count):
        at = rng.uniform(*reach)
        i = int(np.searchsorted(u, at).clip(1, len(P) - 2))
        w, ln = rng.uniform(*width), rng.uniform(*length)
        t = P[i + 1] - P[i - 1]
        t = t / (np.linalg.norm(t) or 1.0)
        dirn = N[i] * (1 - droop) + np.array([0.0, -1.0]) * droop + rng.uniform(-0.25, 0.25, 2)
        dirn = dirn / (np.linalg.norm(dirn) or 1.0)
        a, b = P[i] - t * w / 2, P[i] + t * w / 2
        tip = P[i] + dirn * ln
        mid_a = (a + tip) / 2 + N[i] * w * 0.15
        mid_b = (b + tip) / 2 + N[i] * w * 0.15
        out.append(np.array([a, mid_a, tip, mid_b, b]))
    return out
