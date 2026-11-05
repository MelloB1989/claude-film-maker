"""Anime characters from code: the parts every design is made of, so a film's cast file only says what its
characters look like (their proportions, costume, colours) and where their joints are.

- `palette(colors, look, ...)`: a toon material per named colour (lit, shade) of a design, with optional mid bands.
- `rig(name, coll, ...)`: a character's root empty (placed and turned by the shot) and its `upper` empty, which the
  breathing and the small shifts of weight move (the head, the arms and what they hold ride on it; the legs stay
  planted); `attach(objects, parent)` parents parts keeping where they are.
- `head_shape(jaw, chin)`: an anime head from a unit sphere (a narrowing jaw, the chin brought forward).
- `face(...)`: a drawn face (almond eyes with irises, glints and heavy lids, brows, a mouth, age lines) as decals
  shrinkwrapped onto the head, by mood (`fierce`: wide, brows and lids slanted down to the middle; `calm`: half-lidded).
- `hair_locks(...)`: anime hair, flat tapering locks curving off the crown and the back of the head, and bangs.
- `spiky_hair(...)`: rougher hair, a clump of thin spikes.
- `headband(...)`: a band round the head and two tails off its knot (flutter them with toon.flutter).
- `breathe(upper, ...)`: keys a breath (and an optional lean) on an `upper` empty across a shot's frames.

Characters are built facing +x with their feet at the origin. Colours are linear RGB.
"""
from __future__ import annotations

import math

import numpy as np

from . import shapes

FIERCE, CALM = "fierce", "calm"


def palette(colors: dict, look, *, mids: dict | None = None, prefix: str = "cast", cuts: dict | None = None,
            flashes: dict | None = None) -> dict:
    """{name: toon.cel material} for {name: (lit, shade)}; `mids` adds a mid band to some, `cuts` moves their cut,
    `flashes` how far some whiten in a lightning flash (toon.cel's `flash`; the look's otherwise)."""
    from . import toon

    mids, cuts, flashes = mids or {}, cuts or {}, flashes or {}
    return {k: toon.cel(f"{prefix}-{k}", lit, shade, look=look, mid=mids.get(k), cut=cuts.get(k, 0.4),
                        flash=flashes.get(k)) for k, (lit, shade) in colors.items()}


def empty(name: str, coll, parent=None, location=(0, 0, 0)):
    import bpy

    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.2
    coll.objects.link(e)
    e.location = location
    if parent is not None:
        e.parent = parent
    return e


def rig(name: str, coll, upper_height: float) -> tuple:
    """(root, upper): the character's root at its feet and the empty its upper body rides on, at `upper_height`."""
    root = empty(f"{name}-root", coll)
    upper = empty(f"{name}-upper", coll, root, (0.0, 0.0, upper_height))
    return root, upper


def attach(obs, parent) -> None:
    """Parent `obs` to `parent`, each staying where it is."""
    import bpy

    bpy.context.view_layer.update()  # the parent's world matrix, not the identity a new object starts with
    inv = parent.matrix_world.inverted()
    for ob in obs:
        ob.parent = parent
        ob.matrix_parent_inverse = inv


def head_shape(jaw: float = 0.32, chin: float = 0.18):
    """An anime head from a unit sphere: the lower half narrowing to a jaw (`jaw` of its width gone at the chin) and the
    chin brought forward (+x) by `chin`."""
    def f(v):
        v = v.copy()
        low = np.clip(-v[:, 2], 0, 1)
        v[:, 1] *= 1 - jaw * low ** 1.4
        v[:, 0] *= 1 - 0.18 * low
        v[:, 0] += chin * low ** 2 * 0.5
        return v
    return f


def eye_outline(w: float, h: float, n: int = 10) -> np.ndarray:
    """An almond, `w` wide and `h` tall over its corners: the upper lid's arc peaking a little inside its middle, the
    outer corner a little higher than the inner, the lower lid a shallower arc. (u, v): u from the inner corner (-w/2)
    to the outer (+w/2)."""
    t = np.linspace(0, 1, n)
    u_up = -w / 2 + w * t
    v_up = h * np.sin(np.pi * t) ** 0.8 * (1 - 0.15 * t) + 0.15 * h * t
    t2 = np.linspace(1, 0, n)[1:-1]
    u_lo = -w / 2 + w * t2
    v_lo = -0.32 * h * np.sin(np.pi * t2) + 0.15 * h * t2
    return np.column_stack([np.concatenate([u_up, u_lo]), np.concatenate([v_up, v_lo])])


def band_along(points: np.ndarray, widths) -> np.ndarray:
    """A band (a stroke) along a polyline `points` (k, 2), `widths` (k,) wide, as a closed outline."""
    p = np.asarray(points, float)
    d = np.gradient(p, axis=0)
    nrm = np.column_stack([-d[:, 1], d[:, 0]])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    w = np.asarray(widths, float)[:, None] / 2
    return np.concatenate([p + nrm * w, (p - nrm * w)[::-1]])


def face(prefix: str, head, H, R, m: dict, coll, *, mood: str = CALM, tilt: float = 0.0, skin: str = "skin", scale: float = 1.0,
         age: float = 0.0, ink: str = "ink", white: str = "eye_white", iris: str = "iris", glint: str = "eye_white") -> list:
    """A drawn face on the head object `head` (centre H, radii R, tilted `tilt` about y), facing +x: almond eyes (their
    whites, a dark iris with a glint, a heavy upper lid with a flick past the outer corner, a short lower lid), brows,
    a small nose and a mouth, as flat decals shrinkwrapped onto the head so they follow its curve. `mood`: FIERCE
    (wide eyes, small irises, brows and lids slanted down to the middle, a hard mouth) or CALM (half-lidded, the brows
    level, a slight smile). `age` (0..1) adds lines: crow's feet, the folds from nose to mouth."""
    fierce = mood == FIERCE
    rot = shapes.rot_y(tilt)
    out = []

    def xf(p):
        return np.asarray(H) + rot @ p

    def decal(name, outline, mat, layer):
        ob = shapes.patch(f"{prefix}-{name}", outline, depth_axis=0, depth=R[0] * 1.25, material=m[mat], coll=coll, xform=xf)
        sw = ob.modifiers.new("onto", "SHRINKWRAP")
        sw.target = head
        sw.wrap_method = "PROJECT"
        sw.use_project_x = True
        sw.use_negative_direction = True
        sw.use_positive_direction = True
        sw.offset = 0.0008 + 0.0005 * layer
        ob.visible_shadow = False
        out.append(ob)
        return ob

    w = 0.05 * scale
    h = (0.02 if fierce else 0.009) * scale
    for side in (-1, 1):
        cy, cz = side * R[1] * 0.43, R[2] * 0.02
        slant = (0.28 if fierce else 0.06) * side      # the inner corner (toward the middle) lower when fierce

        def place(uv, cy=cy, cz=cz, side=side, slant=slant):
            uv = np.asarray(uv, float)
            u, v = uv[:, 0] * side, uv[:, 1]           # u runs outward on each side
            c, s_ = math.cos(slant), math.sin(slant)
            return np.column_stack([cy + u * c - v * s_, cz + u * s_ + v * c])

        alm = eye_outline(w, h)
        decal(f"white{side}", place(alm), white, 0)
        ir_w, ir_h = (0.19 if fierce else 0.24) * w, (0.75 if fierce else 1.1) * h
        ang = np.linspace(0, 2 * np.pi, 14, endpoint=False)
        ir = np.column_stack([0.02 * w + ir_w * np.cos(ang), 0.4 * h + ir_h * np.sin(ang) * 0.6])
        decal(f"iris{side}", place(ir), iris, 1)
        gl = np.column_stack([-0.04 * w + 0.045 * w * np.cos(ang), 0.62 * h + 0.045 * w * np.sin(ang)])
        decal(f"glint{side}", place(gl), glint, 2)
        top = alm[: len(alm) // 2 + 1]
        lid = np.vstack([top + [0, 0.05 * h], [[w / 2 + 0.16 * w, 0.55 * h]]])
        lw = np.linspace(0.07, 0.16, len(lid)) * w * (1.25 if fierce else 1.0)
        decal(f"lid{side}", place(band_along(lid, lw)), ink, 3)
        lo = np.array([[0.1 * w, -0.25 * h], [0.32 * w, -0.2 * h], [0.48 * w, 0.0]])
        decal(f"lower{side}", place(band_along(lo, [0.02 * w, 0.035 * w, 0.02 * w])), ink, 3)
        # the brow: heavy at its inner end when fierce
        bz = 0.95 * h + (0.012 if fierce else 0.02) * scale
        brow = np.array([[-0.55 * w, bz - (0.01 * scale if fierce else 0.0)], [0.0, bz + 0.004 * scale], [0.55 * w, bz]])
        decal(f"brow{side}", place(band_along(brow, np.array([0.3, 0.22, 0.08]) * w * (1.2 if fierce else 0.7))), ink, 3)
        if age > 0:
            for k, a_ in enumerate((0.25, -0.05, -0.35)):
                st = np.array([[0.62 * w, 0.2 * h], [0.62 * w + 0.28 * w * math.cos(a_), 0.2 * h + 0.28 * w * math.sin(a_)]])
                decal(f"crow{side}{k}", place(band_along(st, [0.025 * w * age, 0.012 * w * age])), ink, 3)
            fold = np.array([[side * 0.33 * R[1], -0.24 * R[2]], [side * 0.36 * R[1], -0.36 * R[2]], [side * 0.3 * R[1], -0.47 * R[2]]])
            decal(f"fold{side}", band_along(fold, np.array([0.006, 0.008, 0.004]) * age), ink, 3)
    out.append(shapes.ellipsoid(f"{prefix}-nose", tuple(xf(np.array([R[0] * 0.96, 0.0, -R[2] * 0.22]))), (0.009, 0.006, 0.013), material=m[skin],
                                coll=coll, n=10))
    mw = 0.034 * scale
    t = np.linspace(-1, 1, 7)
    mouth = np.column_stack([t * mw / 2, -R[2] * 0.5 + (0.0 if fierce else -0.004 * scale) + (0.0 if fierce else 0.006 * scale) * t ** 2])
    decal("mouth", band_along(mouth, np.full(7, 0.0045 * scale) * (1 - 0.5 * np.abs(t))), ink, 3)
    return out


def hair_locks(prefix: str, H, R, material, coll, *, count: int = 32, length=(0.14, 0.26), width=(0.04, 0.065), thickness: float = 0.012,
               sweep=(-0.6, 0.0, -0.3), gravity: float = 0.3, bangs: int = 5, bang_length: float = 0.1, bang_floor: float = 0.45,
               tilt: float = 0.0, seed: int = 3) -> list:
    """Anime hair: a cap over the skull and flat, tapering locks off the crown and the back of the head, curving out
    and down (`sweep`, `gravity`), keeping off the face; `bangs` locks fall from the hairline over the brow, their tips
    no lower than `bang_floor` of the head's half-height above its centre."""
    rng = np.random.default_rng(seed)
    specs = []
    for _ in range(count * 3):
        if len(specs) >= count:
            break
        th = rng.uniform(0.05, 1.45)
        ph = rng.uniform(-math.pi, math.pi)
        d = np.array([math.sin(th) * math.cos(ph) - 0.25, math.sin(th) * math.sin(ph), math.cos(th) + 0.1])
        if d[0] > 0.15 and th > 0.45:
            continue
        d /= np.linalg.norm(d)
        r0 = np.array(H) + np.array(R) * 0.84 * d
        L = rng.uniform(*length)
        go = d + np.array(sweep) + rng.normal(0, 0.15, 3)
        go /= np.linalg.norm(go)
        s = np.linspace(0, 1, 5)
        path = [r0 + go * L * si + np.array([0, 0, -gravity * L * si * si]) for si in s]
        wd = rng.uniform(*width)
        specs.append((path, wd * (1 - s) ** 0.8 + 0.002, thickness * (1 - 0.85 * s)))
    for i in range(bangs):
        y = R[1] * (-0.7 + 1.4 * i / max(1, bangs - 1)) + rng.normal(0, 0.004)
        r0 = np.array(H) + np.array([R[0] * 0.55, y, R[2] * 0.8])
        tip_z = H[2] + R[2] * bang_floor
        tip = np.array([H[0] + R[0] * 1.08, y * 1.08, tip_z + rng.uniform(0, 0.015)])
        mid = (r0 + tip) / 2 + np.array([0.03, 0, 0.01])
        path = [r0, mid, tip]
        specs.append((path, np.array([0.045, 0.03, 0.002]) * rng.uniform(0.85, 1.15), np.array([0.012, 0.009, 0.002])))
    cap = shapes.ellipsoid(f"{prefix}-skull", (H[0] - 0.016, 0, H[2] + 0.018), (R[0] * 0.97, R[1] * 1.06, R[2] * 0.95),
                           material=material, coll=coll, n=20, rot=shapes.rot_y(tilt),
                           squash=lambda v: np.where(np.stack([v[:, 0] > 0.55] * 3, 1) & np.stack([v[:, 2] < 0.55] * 3, 1), v * [0.7, 1, 1], v))
    return [cap, shapes.lofts(f"{prefix}-locks", specs, material=material, coll=coll, n=8)]


def ears(prefix: str, H, R, material, coll) -> list:
    return [shapes.ellipsoid(f"{prefix}-ear{side}", (H[0] - 0.012, side * R[1] * 0.98, H[2] - 0.008), (0.021, 0.0125, 0.033),
                             material=material, coll=coll, n=10) for side in (-1, 1)]


def spiky_hair(prefix: str, H, R, material, coll, *, count: int = 60, length=(0.1, 0.2), width=(0.032, 0.05), sweep=(-0.5, 0.0, -0.2),
               bangs: int = 8, tilt: float = 0.0, seed: int = 3) -> list:
    """A cap over the skull and `count` spikes off the crown and the back of the head, swept by `sweep` (a direction
    added to each spike's), keeping clear of the face; `bangs` spikes fall over the brow."""
    rng = np.random.default_rng(seed)
    roots, tips, widths = [], [], []
    for _ in range(count):
        th = rng.uniform(0.0, 1.35)
        ph = rng.uniform(-math.pi, math.pi)
        d = np.array([math.sin(th) * math.cos(ph) - 0.3, math.sin(th) * math.sin(ph), math.cos(th) + 0.1])
        if d[0] > 0.3 and th > 0.55:
            continue
        d /= np.linalg.norm(d)
        r0 = np.array(H) + np.array(R) * 0.82 * d
        tipd = d + np.array(sweep) + rng.normal(0, 0.2, 3)
        tipd /= np.linalg.norm(tipd)
        roots.append(r0)
        tips.append(r0 + tipd * rng.uniform(*length))
        widths.append(rng.uniform(*width))
    for i in range(bangs):
        y = R[1] * (-0.75 + 1.5 * i / max(1, bangs - 1)) + rng.normal(0, 0.004)
        r0 = np.array(H) + np.array([R[0] * 0.58, y, R[2] * 0.72])
        roots.append(r0)
        tips.append(r0 + np.array([0.075 + rng.uniform(0, 0.03), y * 0.35, -0.12 - rng.uniform(0, 0.05)]))
        widths.append(0.026)
    cap = shapes.ellipsoid(f"{prefix}-skull", (H[0] - 0.014, 0, H[2] + 0.016), (R[0] * 0.98, R[1] * 1.06, R[2] * 0.95),
                           material=material, coll=coll, n=20, rot=shapes.rot_y(tilt))
    return [cap, shapes.spikes(f"{prefix}-hair", roots, tips, widths, material=material, coll=coll)]


def headband(prefix: str, H, R, material, coll, *, height: float = 0.022, tails=((0.42, 0.05), (0.34, 0.044))) -> tuple:
    """(band, tails): a band round the brow of the head at H (radii R), and ribbon tails off its knot at the back,
    each (length, width), streaming back and down."""
    ang = np.linspace(0, 2 * math.pi, 29)
    ring = [(H[0] - 0.01 + (R[0] * 1.02) * math.cos(a), (R[1] * 1.1) * math.sin(a), H[2] + R[2] * 0.62 + 0.012 * math.cos(a) ** 2) for a in ang]
    band = shapes.loft(f"{prefix}-band", ring, [height] * len(ring), [0.007] * len(ring), material=material, coll=coll, n=6,
                       cap=False, subsurf=0)
    knot = np.array([H[0] - R[0] * 1.03, 0.0, H[2] + R[2] * 0.62 + 0.012])
    dirs = [(-1, -0.25, -0.3), (-1, 0.3, -0.45)][: len(tails)]
    tail = shapes.strips(f"{prefix}-tails", [knot + [0, -0.018, 0], knot + [0, 0.018, 0]][: len(tails)], dirs,
                         [L for L, _ in tails], [w for _, w in tails], material=material, coll=coll, segs=8,
                         droop=[(0, 0, -0.06), (0, 0, -0.09)][: len(tails)])
    return band, tail


def breathe(upper, frames: range, fps: float, *, rate: float = 0.3, depth: float = 0.005, base_z: float | None = None,
            sway: float = 0.0, lean=None, phase: float = 0.0) -> None:
    """Key a breath on `upper` for every frame in `frames`: it rises and falls `depth` metres `rate` times a second
    (and rocks `sway` radians with it); `lean(t)` (radians about y, t in s from the first frame) adds a shift of
    weight on top."""
    z0 = upper.location.z if base_z is None else base_z
    f0 = frames.start
    for f in frames:
        t = (f - f0) / fps
        b = math.sin(2 * math.pi * rate * t + phase)
        upper.location.z = z0 + depth * b
        upper.rotation_euler = (0.0, (lean(t) if lean else 0.0) + sway * math.sin(2 * math.pi * rate * t + phase + 1.0), 0.0)
        upper.keyframe_insert("location", frame=f)
        upper.keyframe_insert("rotation_euler", frame=f)
