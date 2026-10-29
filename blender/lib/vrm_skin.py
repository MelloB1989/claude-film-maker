"""The skin of a VRM character (blender/lib/vrm.py) changed in code: marks painted into its textures and its face
reshaped by shape keys of its own. VRoid Studio paints every face young and smooth; age (lines, folds, spots), a scar,
a hairline or a sock is drawn into a copy of the material's base-colour texture, placed on the 3D face by its landmarks
(the eyes' corners, the nose, the mouth) and carried to the texture through the mesh's UVs.

Marks. A `Mark` is a stroke along a smooth curve through 3D points (a wrinkle, a fold) or a spot round one point (an
age spot), `width` metres across (a spot's: its diameter), its colour multiplied into the skin ("multiply": lines and
shadows), laid over it ("mix") or lightening it ("screen": a highlight on a fold). Points are in the mesh's own space
at rest: a VRM as imported faces -y with its left at +x, z up, metres before any scale_to. A `Surface` is the
triangles of a material's faces with their UVs; `Surface.project(points)` finds each point's nearest place on it (or,
`along` a direction, where a line through it meets it: a mark drawn on a front view of the face) and gives its UV and
how far a metre goes in UV there, so a mark keeps its width in metres wherever it falls. `paint(pixels,
surface, marks)` draws them; `stroke` and `spot` draw in the texture's own pixels, `fill` paints whole faces (feet
in socks), `lighten` / `replace` grade or flatten what a texture has (a white collar gone), `soften` turns an
alpha-masked edge soft (VRoid's zigzag hairline) and `strands` draws fine hairs across it.

`landmarks(eye_white, brow, mouth, skin)` reads a VRoid face's landmarks from its parts' vertices. `displace(co,
moves)` is a sculpt's offsets ({centre, offset, radius}: vertices near the centre moved, eased to nothing at the
radius), for a shape key that hollows a cheek or sags a jowl.

In Blender: `surface(ob, material)`, `face_landmarks(ob)` (VRoid's face mesh), `retexture(mat, edit, scale=2)` (a copy
of the material's lit and shade textures, upscaled, through `edit(pixels) -> pixels`), `drop_faces(ob, material)`
(VRoid's shoes off), `sculpt(ob, name, moves)` and `derive(ob, name, source, weights)` (new shape keys: one of moves,
one an existing key's offsets scaled per vertex: a lid that droops more at its outer corner), `blend_alpha(mat)`
(MToon's BLEND, for a soft edge). A material is a material or a fragment of its name ("EyeWhite").

Pixels are (rows, columns, RGBA) floats 0..1 as Blender keeps them, row 0 at the bottom (v = 0): the UV (u, v) is the
pixel (u * width, v * height). The numpy halves are tested without Blender in blender/tests/test_vrm_skin.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

BLENDS = ("multiply", "mix", "screen", "max")
LUMA = (0.2126, 0.7152, 0.0722)


# ---------------------------------------------------------------------------------------------------- curves, surfaces

def catmull_rom(points, n: int = 12) -> np.ndarray:
    """A smooth curve through `points` (k, d): `n` samples per span, the ends carried on straight (one point: itself)."""
    p = np.atleast_2d(np.asarray(points, float))
    if len(p) < 2:
        return p.copy()
    q = np.concatenate([2 * p[:1] - p[1:2], p, 2 * p[-1:] - p[-2:-1]])
    t = np.linspace(0.0, 1.0, n, endpoint=False)[:, None]
    out = []
    for i in range(1, len(q) - 2):
        p0, p1, p2, p3 = q[i - 1], q[i], q[i + 1], q[i + 2]
        out.append(0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                          + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3))
    out.append(p[-1:])
    return np.concatenate(out)


def closest_on_triangles(points, tris, *, candidates: int = 24) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each point (P, 3), the nearest place on the triangles (T, 3, 3): (triangle index (P,), its barycentric
    weights there (P, 3), the distance (P,)). Only the `candidates` triangles whose middles are nearest are tried."""
    pts = np.atleast_2d(np.asarray(points, float))
    tris = np.asarray(tris, float)
    mids = tris.mean(axis=1)
    k = min(candidates, len(tris))
    near = np.argsort(((pts[:, None, :] - mids[None, :, :]) ** 2).sum(-1), axis=1)[:, :k]      # (P, k)
    a, b, c = (tris[near, i] for i in range(3))                                               # (P, k, 3)
    p = pts[:, None, :]
    bary = _closest_bary(p, a, b, c)
    q = bary[..., :1] * a + bary[..., 1:2] * b + bary[..., 2:] * c
    d = np.linalg.norm(q - p, axis=-1)
    best = np.argmin(d, axis=1)
    rows = np.arange(len(pts))
    return near[rows, best], bary[rows, best], d[rows, best]


def _closest_bary(p, a, b, c) -> np.ndarray:
    """Barycentric weights of the point of each triangle (a, b, c) nearest p (Ericson, Real-Time Collision
    Detection, 5.1.5), broadcast over the leading axes."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(-1), (ac * ap).sum(-1)
    bp = p - b
    d3, d4 = (ab * bp).sum(-1), (ac * bp).sum(-1)
    cp = p - c
    d5, d6 = (ab * cp).sum(-1), (ac * cp).sum(-1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    shape = d1.shape
    out = np.zeros(shape + (3,))
    done = np.zeros(shape, bool)

    def take(mask, u, v, w):
        m = mask & ~done
        out[m] = np.stack([u, v, w], -1)[m] if np.ndim(u) else np.array([u, v, w])
        done[m] = True

    with np.errstate(divide="ignore", invalid="ignore"):
        take((d1 <= 0) & (d2 <= 0), 1.0, 0.0, 0.0)                                   # vertex a
        take((d3 >= 0) & (d4 <= d3), 0.0, 1.0, 0.0)                                  # vertex b
        take((d6 >= 0) & (d5 <= d6), 0.0, 0.0, 1.0)                                  # vertex c
        t = d1 / (d1 - d3)
        take((vc <= 0) & (d1 >= 0) & (d3 <= 0), 1 - t, t, np.zeros(shape))          # edge ab
        t = d2 / (d2 - d6)
        take((vb <= 0) & (d2 >= 0) & (d6 <= 0), 1 - t, np.zeros(shape), t)          # edge ac
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        take((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), np.zeros(shape), 1 - t, t)   # edge bc
        s = va + vb + vc
        v, w = vb / s, vc / s
        take(np.ones(shape, bool), 1 - v - w, v, w)                                  # inside
    return np.nan_to_num(out)


@dataclass
class Surface:
    """A material's faces as triangles (T, 3, 3) and their UVs (T, 3, 2)."""
    tris: np.ndarray
    uvs: np.ndarray

    def __post_init__(self):
        self.tris = np.asarray(self.tris, float)
        self.uvs = np.asarray(self.uvs, float)
        e1, e2 = self.tris[:, 1] - self.tris[:, 0], self.tris[:, 2] - self.tris[:, 0]
        area = np.linalg.norm(np.cross(e1, e2), axis=1) / 2
        f1, f2 = self.uvs[:, 1] - self.uvs[:, 0], self.uvs[:, 2] - self.uvs[:, 0]
        uv_area = np.abs(f1[:, 0] * f2[:, 1] - f1[:, 1] * f2[:, 0]) / 2
        # how far a metre goes in UV on each triangle (as if its stretch were the same every way)
        self.density = np.sqrt(uv_area / np.maximum(area, 1e-12))

    def project(self, points, along=None) -> tuple[np.ndarray, np.ndarray]:
        """Each point's place on the surface: (its UV (P, 2), UV per metre there (P,)). The nearest place, or with
        `along` (a direction) where a line through the point along it first meets the surface from behind it (a mark
        drawn on a picture of the face seen along `along`), the nearest place for a line that misses."""
        pts = np.atleast_2d(np.asarray(points, float))
        idx, bary, _ = closest_on_triangles(pts, self.tris)
        if along is not None:
            hit, hb, ok = cast(pts, along, self.tris)
            idx, bary = np.where(ok, hit, idx), np.where(ok[:, None], hb, bary)
        uv = (bary[:, :, None] * self.uvs[idx]).sum(axis=1)
        return uv, self.density[idx]


def cast(points, along, tris, *, chunk: int = 64) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Lines through `points` (P, 3) along `along`: where each first meets the triangles (T, 3, 3) coming from far
    back along it (Moller-Trumbore): (triangle index (P,), barycentric weights (P, 3), hit (P,) bool)."""
    pts = np.atleast_2d(np.asarray(points, float))
    d = np.asarray(along, float) / np.linalg.norm(along)
    tris = np.asarray(tris, float)
    v0, e1, e2 = tris[:, 0], tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    pv = np.cross(d, e2)
    det = (e1 * pv).sum(-1)
    good = np.abs(det) > 1e-12
    inv = np.where(good, 1.0 / np.where(good, det, 1.0), 0.0)
    origin = pts - d * 10.0
    idx = np.zeros(len(pts), int)
    bary = np.zeros((len(pts), 3))
    ok = np.zeros(len(pts), bool)
    for s in range(0, len(pts), chunk):
        o = origin[s:s + chunk, None, :] - v0[None]
        u = (o * pv).sum(-1) * inv
        q = np.cross(o, e1)
        v = (q * d).sum(-1) * inv
        t = (q * e2).sum(-1) * inv
        hit = good & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
        t = np.where(hit, t, np.inf)
        best = np.argmin(t, axis=1)
        rows = np.arange(len(best))
        found = np.isfinite(t[rows, best])
        idx[s:s + chunk] = best
        ub, vb = u[rows, best], v[rows, best]
        bary[s:s + chunk] = np.stack([1 - ub - vb, ub, vb], -1)
        ok[s:s + chunk] = found
    return idx, bary, ok


# ---------------------------------------------------------------------------------------------------- drawing

def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / np.where(e1 == e0, 1e-9, e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def composite(pixels, mask, window, color, strength: float = 1.0, blend: str = "multiply", channels=slice(0, 3)):
    """Lay `mask` (coverage 0..1 over `window`: (row0, row1, col0, col1)) onto `pixels` in place, `color` by
    `strength`: "multiply" darkens toward the colour times the skin, "mix" paints the colour over, "screen" lightens,
    "max" raises each channel to the colour (an alpha raised to 1 where the mask is)."""
    if blend not in BLENDS:
        raise ValueError(f"blend {blend!r} is not one of {', '.join(BLENDS)}")
    r0, r1, c0, c1 = window
    region = pixels[r0:r1, c0:c1, channels]
    a = float(strength) * np.asarray(mask, np.float32)[..., None]
    col = np.asarray(color, np.float32)[: region.shape[-1]]
    if blend == "multiply":
        region *= 1.0 - a * (1.0 - col)
    elif blend == "mix":
        region += (col - region) * a
    elif blend == "screen":
        region[:] = 1.0 - (1.0 - region) * (1.0 - a * col)
    else:
        np.maximum(region, a * col, out=region)
    return pixels


def stroke_mask(shape, path, widths, *, soft: float = 0.0) -> tuple[np.ndarray, tuple]:
    """Coverage (0..1) of a stroke along `path` (k, 2: pixel x, y) `widths` pixels across at each point (the width
    goes between them): solid to `soft` of its half width in from its edge, eased to nothing at the edge (half a pixel
    on, so a fine line is drawn antialiased). Returns (mask, window) over the stroke's bounding box."""
    h, w = shape[:2]
    p = np.atleast_2d(np.asarray(path, float))
    wd = np.broadcast_to(np.asarray(widths, float), (len(p),))
    pad = wd.max() / 2 + 2
    c0, c1 = int(max(0, math.floor(p[:, 0].min() - pad))), int(min(w, math.ceil(p[:, 0].max() + pad)))
    r0, r1 = int(max(0, math.floor(p[:, 1].min() - pad))), int(min(h, math.ceil(p[:, 1].max() + pad)))
    if c1 <= c0 or r1 <= r0:
        return np.zeros((0, 0), np.float32), (0, 0, 0, 0)
    mask = np.zeros((r1 - r0, c1 - c0), np.float32)
    segs = [(p[i], p[i + 1], wd[i], wd[i + 1]) for i in range(len(p) - 1)] or [(p[0], p[0], wd[0], wd[0])]
    for a, b, wa, wb in segs:
        hp = max(wa, wb) / 2 + 2
        x0, x1 = int(max(c0, math.floor(min(a[0], b[0]) - hp))), int(min(c1, math.ceil(max(a[0], b[0]) + hp)))
        y0, y1 = int(max(r0, math.floor(min(a[1], b[1]) - hp))), int(min(r1, math.ceil(max(a[1], b[1]) + hp)))
        if x1 <= x0 or y1 <= y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        ab = b - a
        L2 = float(ab @ ab)
        t = np.clip(((xs - a[0]) * ab[0] + (ys - a[1]) * ab[1]) / L2, 0.0, 1.0) if L2 > 1e-12 else np.zeros_like(xs)
        d = np.hypot(xs - (a[0] + t * ab[0]), ys - (a[1] + t * ab[1]))
        half = (wa + (wb - wa) * t) / 2
        cov = 1.0 - smoothstep(half * (1.0 - soft) - 0.5, half + 0.5, d)
        # a line thinner than a pixel covers it only in part
        cov *= np.minimum(1.0, half * 2)
        sub = mask[y0 - r0:y1 - r0, x0 - c0:x1 - c0]
        np.maximum(sub, cov, out=sub)
    return mask, (r0, r1, c0, c1)


def stroke(pixels, path, widths, color, strength: float = 1.0, *, blend: str = "multiply", soft: float = 0.0,
           channels=slice(0, 3)):
    """Draw a stroke (stroke_mask) onto `pixels` in place (composite). Returns the pixels."""
    mask, window = stroke_mask(pixels.shape, path, widths, soft=soft)
    if mask.size:
        composite(pixels, mask, window, color, strength, blend, channels)
    return pixels


def spot(pixels, center, radius: float, color, strength: float = 1.0, *, blend: str = "multiply",
         hardness: float = 0.5, stretch: float = 1.0, angle: float = 0.0, channels=slice(0, 3)):
    """Draw a round spot onto `pixels` in place: `radius` pixels (times `stretch` along `angle`, radians from +x),
    solid out to `hardness` of it and eased to nothing at its edge. Returns the pixels."""
    h, w = pixels.shape[:2]
    cx, cy = (float(v) for v in center)
    big = radius * max(1.0, stretch) + 1
    c0, c1 = int(max(0, math.floor(cx - big))), int(min(w, math.ceil(cx + big)))
    r0, r1 = int(max(0, math.floor(cy - big))), int(min(h, math.ceil(cy + big)))
    if c1 <= c0 or r1 <= r0:
        return pixels
    xs, ys = np.meshgrid(np.arange(c0, c1) + 0.5 - cx, np.arange(r0, r1) + 0.5 - cy)
    ca, sa = math.cos(angle), math.sin(angle)
    along, across = xs * ca + ys * sa, -xs * sa + ys * ca
    d = np.hypot(along / max(stretch, 1e-6), across) / max(radius, 1e-6)
    mask = 1.0 - smoothstep(hardness, 1.0, d)
    composite(pixels, mask, (r0, r1, c0, c1), color, strength, blend, channels)
    return pixels


def profile(t, taper=(1.0, 1.0)) -> np.ndarray:
    """A stroke's width along it (t 0..1): taper[0] at its start, full in the middle, taper[1] at its end."""
    t = np.asarray(t, float)
    a, b = taper
    return np.where(t < 0.5, a + (1 - a) * smoothstep(0.0, 0.5, t), 1 + (b - 1) * smoothstep(0.5, 1.0, t))


@dataclass
class Mark:
    """A stroke along a smooth curve through `path` (3D points, the mesh's own space), or a spot round its one point:
    `width` metres across (a spot's diameter), `color` (linear RGB) by `strength`, blended by `blend` (BLENDS). A
    stroke tapers to `taper` (start, end) of its width; `soft` is how much of its half width eases out (0 a crisp line,
    1 a wash). A spot is `stretch` times as long along `toward` (a 3D direction) as across."""
    path: list
    width: float
    color: tuple = (0.55, 0.38, 0.32)
    strength: float = 0.5
    taper: tuple = (0.3, 0.3)
    soft: float = 0.0
    blend: str = "multiply"
    stretch: float = 1.0
    toward: tuple | None = None


def paint(pixels, surface: Surface, marks, *, along=None, samples: int = 10, seam: float = 0.08):
    """Draw `marks` onto `pixels` (a texture of `surface`'s UVs) in place: each projected onto the surface (along
    `along` when given: Surface.project), its curve sampled `samples` times per span; a stroke is broken where it
    jumps more than `seam` in UV (a seam). Returns the pixels."""
    h, w = pixels.shape[:2]
    size = np.array([w, h], float)
    px_per_uv = math.sqrt(w * h)
    for mk in marks:
        pts = np.atleast_2d(np.asarray(mk.path, float))
        if len(pts) == 1:
            uv, dens = surface.project(pts, along)
            r = mk.width / 2 * dens[0] * px_per_uv
            ang = 0.0
            if mk.toward is not None:
                tip, _ = surface.project(pts + np.asarray(mk.toward, float) * 1e-3, along)
                dv = (tip[0] - uv[0]) * size
                ang = math.atan2(dv[1], dv[0])
            spot(pixels, uv[0] * size, r, mk.color, mk.strength, blend=mk.blend, hardness=1.0 - mk.soft,
                 stretch=mk.stretch, angle=ang)
            continue
        curve = catmull_rom(pts, samples)
        uv, dens = surface.project(curve, along)
        seg = np.linalg.norm(np.diff(uv, axis=0), axis=1)
        t = np.concatenate([[0.0], np.cumsum(seg)])
        t = t / t[-1] if t[-1] > 0 else t
        widths = mk.width * dens * px_per_uv * profile(t, mk.taper)
        cuts = np.flatnonzero(seg > seam) + 1
        for part, wd in zip(np.split(uv * size, cuts), np.split(widths, cuts)):
            if len(part):
                stroke(pixels, part, wd, mk.color, mk.strength, blend=mk.blend, soft=mk.soft)
    return pixels


def fill(pixels, uvs, color, strength: float = 1.0, *, grow: float = 1.5, blend: str = "mix"):
    """Paint every triangle (UVs (T, 3, 2)) of a texture in place, grown by `grow` pixels so no seam shows the old
    colour. Returns the pixels."""
    h, w = pixels.shape[:2]
    mask = np.zeros((h, w), np.float32)
    for tri in np.asarray(uvs, float) * (w, h):
        c0, c1 = int(max(0, math.floor(tri[:, 0].min() - grow))), int(min(w, math.ceil(tri[:, 0].max() + grow)))
        r0, r1 = int(max(0, math.floor(tri[:, 1].min() - grow))), int(min(h, math.ceil(tri[:, 1].max() + grow)))
        if c1 <= c0 or r1 <= r0:
            continue
        xs, ys = np.meshgrid(np.arange(c0, c1) + 0.5, np.arange(r0, r1) + 0.5)
        inside = np.ones(xs.shape, np.float32)
        for i in range(3):
            a, b, o = tri[i], tri[(i + 1) % 3], tri[(i + 2) % 3]
            n = np.array([b[1] - a[1], a[0] - b[0]])
            ln = np.linalg.norm(n)
            if ln < 1e-9:
                inside[:] = 0
                break
            n /= ln
            if (o - a) @ n < 0:
                n = -n
            # signed distance in from this edge, in pixels
            sd = (xs - a[0]) * n[0] + (ys - a[1]) * n[1]
            inside = np.minimum(inside, np.clip(sd + grow, 0.0, 1.0))
        sub = mask[r0:r1, c0:c1]
        np.maximum(sub, inside, out=sub)
    composite(pixels, mask, (0, h, 0, w), color, strength, blend)
    return pixels


def luma(pixels) -> np.ndarray:
    return np.asarray(pixels, np.float32)[..., :3] @ np.asarray(LUMA, np.float32)


def replace(pixels, where, color, *, grow: int = 2):
    """Pixels where `where` (a (rows, cols) bool mask) holds, and `grow` pixels round them, set to `color` (RGB; the
    alpha kept): a white collar in a dark robe's texture gone. Returns the pixels."""
    m = np.asarray(where, bool)
    for _ in range(grow):
        m = m | np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
    pixels[m, :3] = np.asarray(color, np.float32)[:3]
    return pixels


def lighten(pixels, gain=1.0, *, saturation: float = 1.0, lift: float = 0.0, where=None):
    """Grade a texture in place: its colour toward its own grey by `saturation`, then times `gain` (RGB or one value)
    and lifted toward white by `lift`; only where `where` holds when given. Returns the pixels."""
    px = pixels[..., :3]
    y = luma(pixels)[..., None]
    out = y + (px - y) * float(saturation)
    out = out * np.asarray(gain, np.float32)
    out = np.clip(out + (1.0 - out) * float(lift), 0.0, 1.0)
    if where is None:
        px[:] = out
    else:
        px[where] = out[where]
    return pixels


def box_blur(a, radius: int, passes: int = 3) -> np.ndarray:
    """A blur of `a` (rows, cols[, channels]) near a gaussian of sigma ~ radius * sqrt(passes / 3): `passes` box
    blurs of 2 radius + 1, the edges held."""
    out = np.asarray(a, np.float32).copy()
    r = int(radius)
    if r <= 0:
        return out
    for _ in range(passes):
        for axis in (0, 1):
            n = out.shape[axis]
            pad = [(0, 0)] * out.ndim
            pad[axis] = (r + 1, r)
            c = np.cumsum(np.pad(out, pad, mode="edge"), axis=axis, dtype=np.float64)
            hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
            lo = np.take(c, np.arange(0, n), axis=axis)
            out = ((hi - lo) / (2 * r + 1)).astype(np.float32)
    return out


def soften(pixels, *, radius: int = 8, feather: float = 0.35, level: float = 0.5, where=None, bleed: int = 12):
    """An alpha-masked edge (a zigzag) made smooth and soft in place: the alpha blurred by `radius` pixels and cut
    again at `level`, eased over `feather` (0..0.5) either side of it, only where `where` (bool mask) holds when
    given; the colour bled `bleed` pixels out past the old edge so the soft part keeps the inside's colour. Returns
    the pixels."""
    alpha = pixels[..., 3].copy()
    solid = (alpha > 0.5).astype(np.float32)
    if bleed > 0:
        wsum = box_blur(solid, bleed, passes=2)
        rgb = box_blur(pixels[..., :3] * solid[..., None], bleed, passes=2)
        fill_in = (solid < 0.5) & (wsum > 1e-4)
        pixels[fill_in, :3] = rgb[fill_in] / wsum[fill_in][:, None]
    soft = smoothstep(level - feather, level + feather, box_blur(solid, radius))
    if where is not None:
        soft = np.where(where, soft, alpha)
    pixels[..., 3] = soft
    return pixels


def strands(pixels, count: int, length: float, width: float, *, rng=None, where=None, lo: float = 0.15,
            hi: float = 0.85, color=None, strength: float = 1.0, radius: int = 6):
    """Fine hairs drawn across a soft alpha edge (soften) in place: `count` strokes `length` pixels long and `width`
    across, rooted where the alpha is between `lo` and `hi` (and `where` holds), each running into the solid side
    (up the alpha's slope) from a fine tip out on the clear side; their alpha raised to `strength` and their colour
    the edge's own, or `color`. Returns the pixels."""
    rng = rng or np.random.default_rng(0)
    alpha = pixels[..., 3]
    ok = (alpha > lo) & (alpha < hi)
    if where is not None:
        ok &= where
    ys, xs = np.nonzero(ok)
    if not len(xs):
        return pixels
    smooth = box_blur(alpha, radius)
    gy, gx = np.gradient(smooth)
    for i in rng.choice(len(xs), size=min(count, len(xs)), replace=False):
        y, x = ys[i], xs[i]
        g = np.array([gx[y, x], gy[y, x]])
        n = np.linalg.norm(g)
        if n < 1e-6:
            continue
        g /= n
        g = g + rng.normal(0, 0.15, 2)
        g /= np.linalg.norm(g)
        L = length * rng.uniform(0.6, 1.3)
        tip = np.array([x + 0.5, y + 0.5]) - g * L * 0.45
        root = tip + g * L
        path = np.array([tip, (tip + root) / 2 + rng.normal(0, 0.4, 2), root])
        wd = width * rng.uniform(0.7, 1.2) * np.array([0.35, 0.8, 1.0])
        mask, win = stroke_mask(pixels.shape, path, wd)
        if not mask.size:
            continue
        r0, r1, c0, c1 = win
        col = color if color is not None else pixels[min(int(root[1]), pixels.shape[0] - 1),
                                                     min(int(root[0]), pixels.shape[1] - 1), :3]
        composite(pixels, mask, win, col, 1.0, "mix")
        composite(pixels, mask, win, (strength,), 1.0, "max", channels=slice(3, 4))
    return pixels


# ---------------------------------------------------------------------------------------------------- the face

def landmarks(eye_white, brow, mouth, skin) -> dict:
    """A VRoid face's landmarks from its parts' vertices (mesh space: facing -y, its left at +x): per side ("left",
    "right": the character's own) the eye's "outer" and "inner" corners, its "top", "bottom" and "middle", the
    brow's "brow_inner" and "brow_outer" ends; the "nose" (its tip), the mouth's corners ("mouth_left",
    "mouth_right") and "mouth" (its middle), the "chin" (the lowest skin on the middle line, in front)."""
    eye_white, brow, mouth, skin = (np.asarray(a, float) for a in (eye_white, brow, mouth, skin))
    out = {}
    for side, s in (("left", 1.0), ("right", -1.0)):
        e = eye_white[eye_white[:, 0] * s > 0]
        b = brow[brow[:, 0] * s > 0]
        outer, inner = e[np.argmax(np.abs(e[:, 0]))], e[np.argmin(np.abs(e[:, 0]))]
        top, bottom = e[np.argmax(e[:, 2])], e[np.argmin(e[:, 2])]
        middle = np.array([(outer[0] + inner[0]) / 2, e[:, 1].min(), (top[2] + bottom[2]) / 2])
        out[side] = {"outer": outer, "inner": inner, "top": top, "bottom": bottom, "middle": middle,
                     "brow_inner": b[np.argmin(np.abs(b[:, 0]))], "brow_outer": b[np.argmax(np.abs(b[:, 0]))]}
    eye_z = min(out["left"]["bottom"][2], out["right"]["bottom"][2])
    m_lo, m_hi = mouth[:, 2].min(), mouth[:, 2].max()
    width = np.abs(skin[:, 0]).max()
    centre = skin[np.abs(skin[:, 0]) < 0.04 * width]
    mid = centre[(centre[:, 2] < eye_z) & (centre[:, 2] > m_hi)]
    nose = mid[np.argmin(mid[:, 1])]
    mz = (m_lo + m_hi) / 2
    band = mouth[np.abs(mouth[:, 2] - mz) < (m_hi - m_lo)]
    ml, mr = band[np.argmax(band[:, 0])], band[np.argmin(band[:, 0])]
    front = centre[centre[:, 1] < np.median(skin[:, 1])]
    chin = front[np.argmin(front[:, 2])]
    out.update(nose=nose, mouth_left=ml, mouth_right=mr, mouth=(ml + mr) / 2, chin=chin)
    return out


def displace(co, moves) -> np.ndarray:
    """A sculpt's offsets for vertices `co` (N, 3): each move (centre, offset, radius) moves the vertices within its
    radius by its offset, all of it at the centre eased to none at the radius (moves add up)."""
    co = np.asarray(co, float)
    out = np.zeros_like(co)
    for center, offset, radius in moves:
        s = np.linalg.norm(co - np.asarray(center, float), axis=1) / float(radius)
        k = np.where(s < 1.0, (1.0 - s ** 2) ** 2, 0.0)
        out += k[:, None] * np.asarray(offset, float)
    return out


@dataclass
class Drape:
    """What hangs from a body falls straight down from its widest reach: given how far the body reaches from a
    vertical axis at heights `zs` (ascending) in n directions round it (`radii` (len(zs), n), the directions from +x
    toward +y: girth), `drape(z, angle)` is how near the axis a hanging cloth or cape can come at height z, in that
    direction: the furthest the body reaches there or anywhere above it (within zs)."""
    zs: np.ndarray
    radii: np.ndarray

    def __post_init__(self):
        self.zs = np.asarray(self.zs, float)
        r = np.nan_to_num(np.asarray(self.radii, float))
        self.curtain = np.maximum.accumulate(r[::-1], axis=0)[::-1]

    def __call__(self, z: float, angle: float) -> float:
        zs, c = self.zs, self.curtain
        n = c.shape[1]
        i = float(np.interp(z, zs, np.arange(len(zs))))
        i0 = int(math.floor(i))
        i1, fz = min(i0 + 1, len(zs) - 1), i - i0
        j = (angle % (2 * math.pi)) / (2 * math.pi) * n
        j0 = int(math.floor(j)) % n
        j1, fa = (j0 + 1) % n, j - math.floor(j)
        row = lambda k: c[k, j0] * (1 - fa) + c[k, j1] * fa   # noqa: E731
        return float(row(i0) * (1 - fz) + row(i1) * fz)


# ---------------------------------------------------------------------------------------------------- Blender

def girth(ch, center, zs, *, n: int = 48, limit: float | None = None, slab: float | None = None,
          smooth: int = 2, skip=()) -> np.ndarray:
    """How far the posed character `ch` (vrm.Character) reaches from a vertical axis through `center` (x, y in the
    world) at each height of `zs`, in `n` directions from +x toward +y (vrm.outline_ring over its meshes' vertices
    within `slab` of the height, nothing further than `limit` from the axis), leaving out what the humanoid bones
    `skip` and everything below them carry (a hand held out in front): (len(zs), n) radii, 0 where it does not reach
    (for a Drape)."""
    import bpy

    from . import vrm

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    gone = set()
    for h in skip:
        b = ch.armature.data.bones[ch.bones[vrm.canonical(h)]]
        gone |= {b.name, *(c.name for c in b.children_recursive)}
    pts = []
    for ob in ch.meshes:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        m = np.array(ob.matrix_world)
        w = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
        groups = {g.index for g in ob.vertex_groups if g.name in gone}
        if groups and len(ob.data.vertices) == len(w):
            carried = np.array([sum(g.weight for g in v.groups if g.group in groups) for v in ob.data.vertices])
            w = w[carried < 0.5]
        pts.append(w)
    pts = np.concatenate(pts)
    zs = np.asarray(zs, float)
    slab = slab or (float(np.median(np.diff(zs))) if len(zs) > 1 else 0.02)
    c = np.array([center[0], center[1], 0.0])
    out = np.zeros((len(zs), n))
    for i, z in enumerate(zs):
        near = pts[np.abs(pts[:, 2] - z) < slab]
        try:
            out[i] = vrm.outline_ring(near, (c[0], c[1], z), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), n=n, limit=limit,
                                      smooth=smooth)
        except ValueError:
            pass     # nothing of it at this height
    return out


def _slot(ob, material) -> int:
    """The index of `material` (a material, or a fragment of its name) among `ob`'s slots."""
    for i, s in enumerate(ob.material_slots):
        m = s.material
        if m is not None and (m == material or (isinstance(material, str) and material in m.name)):
            return i
    raise KeyError(f"{ob.name} has no material {getattr(material, 'name', material)!r} "
                   f"(it has {', '.join(s.material.name for s in ob.material_slots if s.material)})")


def _rest(ob) -> np.ndarray:
    """`ob`'s vertices at rest (its basis shape when it has shape keys), mesh space."""
    me = ob.data
    co = np.empty(len(me.vertices) * 3, np.float64)
    if me.shape_keys is not None:
        me.shape_keys.reference_key.data.foreach_get("co", co)
    else:
        me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def surface(ob, material) -> Surface:
    """The faces of `ob` that wear `material`, at rest, as a Surface (their first UV map's coordinates)."""
    me = ob.data
    idx = _slot(ob, material)
    co = _rest(ob)
    uv = np.empty(len(me.loops) * 2, np.float64)
    me.uv_layers[0].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    tris, uvs = [], []
    for p in me.polygons:
        if p.material_index != idx:
            continue
        ls = list(p.loop_indices)
        for i in range(1, len(ls) - 1):
            tri = (ls[0], ls[i], ls[i + 1])
            tris.append(co[lv[list(tri)]])
            uvs.append(uv[list(tri)])
    if not tris:
        raise ValueError(f"{ob.name}: no faces wear {getattr(material, 'name', material)!r}")
    return Surface(np.array(tris), np.array(uvs))


def points(ob, material) -> np.ndarray:
    """The rest positions (mesh space) of `ob`'s vertices on faces that wear `material`."""
    me = ob.data
    idx = _slot(ob, material)
    co = _rest(ob)
    keep = sorted({v for p in me.polygons if p.material_index == idx for v in p.vertices})
    return co[keep]


def face_landmarks(ob) -> dict:
    """`landmarks` of a VRoid face mesh (its EyeWhite, FaceBrow, FaceMouth and its skin)."""
    from . import vrm

    skin = next(s.material for s in ob.material_slots if s.material is not None and vrm.kind(s.material.name) == "skin")
    return landmarks(points(ob, "EyeWhite"), points(ob, "FaceBrow"), points(ob, "FaceMouth"), points(ob, skin))


def _textures(mat):
    mt = mat.vrm_addon_extension.mtoon1
    return mt.pbr_metallic_roughness.base_color_texture, mt.extensions.vrmc_materials_mtoon.shade_multiply_texture


def texture_size(mat) -> tuple[int, int]:
    src = _textures(mat)[0].index.source
    return tuple(src.size) if src is not None else (0, 0)


def retexture(mat, edit, *, scale: int = 1, tag: str = "skin"):
    """Give `mat` (an MToon material) a copy of its lit texture, `scale` times the size, through `edit(pixels) ->
    pixels` ((rows, cols, 4) floats), as its lit texture and (when it is the same image, as VRoid makes it) its shade
    texture; a shade texture of its own goes through `edit` too. Returns the new lit image."""
    done = {}
    for info in _textures(mat):
        src = info.index.source
        if src is None or src.size[0] * src.size[1] <= 64:
            continue   # none, or the add-on's 8x8 stand-in
        img = done.get(src.name)
        if img is None:
            img = src.copy()
            img.name = f"{src.name}-{tag}"
            if scale != 1:
                img.scale(src.size[0] * scale, src.size[1] * scale)
            w, h = img.size
            px = np.empty(w * h * 4, np.float32)
            img.pixels.foreach_get(px)
            px = np.asarray(edit(px.reshape(h, w, 4)), np.float32)
            img.pixels.foreach_set(np.clip(px, 0.0, 1.0).ravel())
            img.pack()
            done[src.name] = img
        info.index.source = img
    return next(iter(done.values()), None)


def blend_alpha(mat) -> None:
    """MToon's BLEND alpha on `mat`: its texture's alpha drawn soft (dithered), not cut at the cutoff."""
    mat.vrm_addon_extension.mtoon1.alpha_mode = "BLEND"


def drop_faces(ob, material) -> int:
    """Delete `ob`'s faces that wear `material` (and the vertices left loose); returns how many went."""
    import bmesh

    idx = _slot(ob, material)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    gone = [f for f in bm.faces if f.material_index == idx]
    bmesh.ops.delete(bm, geom=gone, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    return len(gone)


def _key(ob, name: str, co, value: float):
    if ob.data.shape_keys is None:
        ob.shape_key_add(name="Basis", from_mix=False)
    kb = ob.data.shape_keys.key_blocks.get(name) or ob.shape_key_add(name=name, from_mix=False)
    kb.data.foreach_set("co", np.asarray(co, np.float32).ravel())
    kb.value = float(value)
    ob.data.update()
    return kb


def sculpt(ob, name: str, moves, *, value: float = 1.0, only=None):
    """A shape key `name` on `ob` of `moves` (displace, mesh space), set to `value` (1: always on, since no
    expression drives it); only the vertices of faces wearing `only` (a material or a list of them) move."""
    co = _rest(ob)
    off = displace(co, moves)
    if only is not None:
        keep = np.zeros(len(co), bool)
        me = ob.data
        for m in (only if isinstance(only, (list, tuple)) else [only]):
            idx = _slot(ob, m)
            keep[[v for p in me.polygons if p.material_index == idx for v in p.vertices]] = True
        off[~keep] = 0.0
    return _key(ob, name, co + off, value)


def derive(ob, name: str, source: str, weights, *, value: float = 0.0):
    """A shape key `name` on `ob`: the key `source`'s offsets times `weights` (one per vertex, or a function of the
    rest positions (N, 3) giving them)."""
    co = _rest(ob)
    src = np.empty(co.size, np.float64)
    ob.data.shape_keys.key_blocks[source].data.foreach_get("co", src)
    w = weights(co) if callable(weights) else np.asarray(weights, float)
    return _key(ob, name, co + (src.reshape(-1, 3) - co) * np.asarray(w, float)[:, None], value)
