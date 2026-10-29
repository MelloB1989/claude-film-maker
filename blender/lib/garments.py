"""Clothes for the people of lib/human.py, cut from the shells MakeHuman fits to every body, in the rest pose, and
skinned to the rig so they follow any pose:

- `cut(person, name, part, keep=..., push=..., swell=...)`: a garment from a fitted part (`tights`, a bodysuit; `skirt`,
  waist to ankles): the faces whose vertices pass `keep`, pushed off the body by `push` plus `swell` (a function of
  where a vertex is: a sleeve bunched, a skirt flaring into a hakama with `flare`).
- `belt(...)`: a band round whatever is at a height (an obi round a kimono, a headband round the hair), following its
  real cross-section, with an optional knot and tails.
- `lapels(...)`: a kimono's crossed collar, left over right, lying on the garment.
- `legs(...)`: wide divided trouser legs from the waist (a hakama, monpe), pleated, flaring to a hem, skinned down
  each leg.
- `v_neck(...)` and `above(...)`: the usual `keep` tests.

Positions are in the person's frame (rest pose: facing -y, left at +x, feet at z 0). `flare` and the outline math are
numpy only and tested without Blender.
"""
from __future__ import annotations

import math

import numpy as np

from . import human


def flare(waist_z: float, hem_z: float, *, amount: float = 0.1, pleats: int = 0, depth: float = 0.0, front_only: bool = False,
          power: float = 1.6):
    """A `swell` for a skirt: from nothing at `waist_z` out to `amount` metres at `hem_z` (eased by `power`), and
    `pleats` folds round the body `depth` deep (only across the front with `front_only`)."""
    def swell(co, weights) -> float:
        x, y, z = co
        u = float(np.clip((waist_z - z) / max(waist_z - hem_z, 1e-6), 0.0, 1.0))
        s = amount * u ** power
        if pleats and depth:
            a = math.atan2(x, -y)          # 0 at the front
            if not front_only or abs(a) < math.pi / 2:
                s += depth * (0.3 + u) * abs(math.sin(pleats * a / 2))
        return s
    return swell


def above(z: float):
    """keep: everything above height `z`."""
    return lambda co, w: co[2] > z


def v_neck(bottom_z: float, top_z: float, *, half_width: float = 0.075, cross_x: float = -0.012, front_y: float = 0.0):
    """keep: everything but a V opening at the front of the neck, from `bottom_z` (where the lapels cross, at
    `cross_x`: a little to the wearer's right, the left side over the right) widening to `half_width` at `top_z`."""
    def keep(co, w) -> bool:
        x, y, z = co
        if y > front_y or z < bottom_z:
            return True
        k = (z - bottom_z) / max(top_z - bottom_z, 1e-6)
        return abs(x - cross_x) > half_width * k

    def edge(co):
        """A vertex of the cut's open edge near the V moved onto its line (a straight neckline, not a staircase)."""
        x, y, z = co
        if y > front_y or z < bottom_z - 0.03:
            return None
        k = max((z - bottom_z) / max(top_z - bottom_z, 1e-6), 0.0)
        line = cross_x + math.copysign(half_width * k, x - cross_x)
        return (line, y, z) if abs(x - line) < 0.035 else None
    keep.edge = edge
    return keep


def outline(points: np.ndarray, n: int = 48) -> np.ndarray:
    """The outline of a slice of points (k, 2) round their middle: for each of `n` directions, the furthest point
    that way (a band laid round them never cuts into them). Numpy only."""
    p = np.asarray(points, float)
    c = p.mean(axis=0)
    d = p - c
    ang = np.arctan2(d[:, 1], d[:, 0])
    r = np.hypot(d[:, 0], d[:, 1])
    out = np.zeros((n, 2))
    edges = np.linspace(-math.pi, math.pi, n + 1)
    for i in range(n):
        sel = (ang >= edges[i]) & (ang < edges[i + 1])
        a = (edges[i] + edges[i + 1]) / 2
        rr = r[sel].max() if sel.any() else np.nan
        out[i] = (a, rr)
    # fill empty sectors from their neighbours
    rs = out[:, 1]
    if np.isnan(rs).any():
        idx = np.arange(n)
        good = ~np.isnan(rs)
        rs = np.interp(idx, idx[good], rs[good], period=n)
    return c + np.column_stack([np.cos(out[:, 0]) * rs, np.sin(out[:, 0]) * rs])


def _weights(ob, v) -> dict:
    return {ob.vertex_groups[g.group].name: g.weight for g in v.groups}


def cut(person, name: str, part: str, *, keep=None, push: float = 0.01, swell=None, material=None, subsurf: int = 1,
        hem: tuple | None = None, seed: int = 1, edge=None, feather: float = 0.0):
    """A garment from `person.parts[part]` (or `part` itself, an object: the body, for a cap off its scalp): the faces
    whose vertices all pass `keep(co, weights)`, each vertex pushed
    out along its normal by `push` plus `swell(co, weights)`. `hem` (amp, count) zigzags the lowest edge up and down
    (a tattered hem). `feather` (metres): the push fades to nothing at the cut's open edge over that distance (a cap
    that meets the skin at the hairline, no step). `edge(co)` moves a vertex of the cut's open edge (returning its new
    place, or None to leave it):
    by default `keep.edge` where the test has one (v_neck's straight neckline). Skinned like the part."""
    import bmesh
    import bpy

    src = person.parts[part] if isinstance(part, str) else part
    me = src.data
    ok = np.ones(len(me.vertices), bool)
    if keep is not None:
        for v in me.vertices:
            ok[v.index] = bool(keep(tuple(v.co), _weights(src, v)))
    faces = {p.index for p in me.polygons if all(ok[i] for i in p.vertices)}
    ob = human._subset(src, faces, name, person.coll, person.rig)
    me2 = ob.data
    me2.update()
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    bm.from_mesh(me2)
    bm.verts.ensure_lookup_table()
    edge = edge or getattr(keep, "edge", None)
    if edge is not None:
        for v in bm.verts:
            if v.is_boundary:
                to = edge(tuple(v.co))
                if to is not None:
                    v.co = to
    bm.normal_update()
    deform = bm.verts.layers.deform.active
    names = [g.name for g in ob.vertex_groups]
    fade = None
    if feather > 0:
        from mathutils import kdtree

        rim = [v.co.copy() for v in bm.verts if v.is_boundary]
        if rim:
            kd = kdtree.KDTree(len(rim))
            for i, c in enumerate(rim):
                kd.insert(c, i)
            kd.balance()
            fade = kd
    moves = []
    for v in bm.verts:
        w = {names[g]: x for g, x in v[deform].items()} if deform else {}
        k = 1.0
        if fade is not None:
            dist = fade.find(v.co)[2]
            x = min(1.0, dist / feather)
            k = x * x * (3 - 2 * x)
        d = push * k + (swell(tuple(v.co), w) if swell else 0.0)
        moves.append(v.normal * d)
    for v, mv in zip(bm.verts, moves):
        v.co += mv
    if hem:
        amp, count = hem
        zs = np.array([v.co.z for v in bm.verts])
        low = zs.min()
        for v in bm.verts:
            if v.co.z < low + 0.02:
                a = math.atan2(v.co.x, -v.co.y)
                v.co.z += amp * (0.5 + 0.5 * math.cos(count * a)) * rng.uniform(0.3, 1.2)
    bm.to_mesh(me2)
    bm.free()
    if material is not None:
        me2.materials.append(material)
    if subsurf:
        s = ob.modifiers.new("smooth", "SUBSURF")
        s.levels = s.render_levels = subsurf
    person.parts[name] = ob
    return ob


def _slice(ob, z: float, dz: float, tilt: float = 0.0) -> np.ndarray:
    """The (x, y) of `ob`'s vertices within `dz` of the plane through height `z` tilted `tilt` radians about x
    (rising toward +y, the back)."""
    co = np.array([v.co[:] for v in ob.data.vertices])
    plane = z + co[:, 1] * math.tan(tilt)
    sel = np.abs(co[:, 2] - plane) < dz
    return co[sel][:, :2]


def belt(person, name: str, around, z: float, height: float, *, push: float = 0.006, thickness: float = 0.006, tilt: float = 0.0,
         material=None, bone: str = "spine04", n: int = 48, knot=None, tails=None, smooth: bool = False, curl: float = 0.0,
         subsurf: int | None = None):
    """A band `height` tall round `around` (an object in the person's rest frame, or several: round them all, a
    headband over the forehead and the hair) at height `z`, tilted `tilt` radians about x (rising toward the back),
    following the outline of its slice there `push` out from it, bound to `bone`; `smooth` rounds it (cloth, not a
    hoop; `subsurf` 0 keeps it crisp but smooth-shaded). `knot` (angle, size): a knot at that angle round the band (0 the front, pi the back). `tails` [(length,
    width, droop)]: ribbons hanging from the knot, `curl` (radians) twisting along them; the tails' object has its
    local x along them (toon.flutter's default axis waves them from the knot out). Returns the band (and the tails as
    a second object, or None)."""
    import bpy

    from . import shapes

    objs = around if isinstance(around, (list, tuple)) else [around]
    dz = max(height * 0.6, 0.01)
    xy = np.concatenate([_slice(o, z, dz, tilt) for o in objs])
    while len(xy) < 8 and dz < 0.08:
        # a coarse mesh (rings a hand apart): widen the slice until it holds a ring
        dz *= 2
        xy = np.concatenate([_slice(o, z, dz, tilt) for o in objs])
    if len(xy) < 8:
        raise ValueError(f"belt {name}: nothing of {', '.join(o.name for o in objs)} at z {z:.3f}")
    ring = outline(xy, n)
    c = xy.mean(axis=0)
    d = ring - c
    ring = c + d * (1 + push / np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-6))[:, None]
    zs = z + ring[:, 1] * math.tan(tilt)
    verts, faces = [], []
    out_r = ring + d / np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-6)[:, None] * thickness
    for (x, y), (xo, yo), zz in zip(ring, out_r, zs):
        verts += [(x, y, zz - height / 2), (x, y, zz + height / 2), (xo, yo, zz + height / 2), (xo, yo, zz - height / 2)]
    for i in range(n):
        a, b = 4 * i, 4 * ((i + 1) % n)
        for k in range(4):
            faces.append((a + k, a + (k + 1) % 4, b + (k + 1) % 4, b + k))
    ob = shapes.mesh_object(name, verts, faces, material, person.coll, smooth=smooth,
                            subsurf=(1 if smooth else 0) if subsurf is None else subsurf)
    human.bind(ob, person.rig, bone)
    tail_ob = None
    if knot is not None or tails:
        ang, size = knot if knot is not None else (math.pi, 0.03)
        # the point of the band at that angle round it (0 the front: -y)
        a = np.arctan2(d[:, 0], -d[:, 1])
        i = int(np.argmin(np.abs((a - ang + math.pi) % (2 * math.pi) - math.pi)))
        kx, ky = out_r[i]
        kz = zs[i]
        outward = np.array([d[i, 0], d[i, 1], 0.0])
        outward /= np.linalg.norm(outward)
        kp = np.array([kx, ky, kz]) + outward * size * 0.5
        parts = [shapes.ellipsoid(f"{name}-knot", tuple(kp), (size, size * 0.8, size * 0.8), material=material, coll=person.coll, n=10)]
        for p in parts:
            human.bind(p, person.rig, bone)
        if tails:
            tail_ob = _tails(person, f"{name}-tails", kp, outward, tails, material=material, curl=curl, thickness=thickness * 0.5)
            human.bind(tail_ob, person.rig, bone)
    return ob, tail_ob


def _tails(person, name: str, root, outward, tails, *, material=None, curl: float = 0.0, thickness: float = 0.002, k: int = 12):
    """Ribbons from `root` streaming out along `outward` and drooping, as one object whose local x runs along them."""
    import bpy
    from mathutils import Matrix, Vector

    from . import hair as hair_mod
    from . import shapes

    root = np.asarray(root, float)
    out = np.asarray(outward, float)
    out = out / np.linalg.norm(out)
    side = np.cross(out, (0.0, 0.0, 1.0))
    side /= np.linalg.norm(side)
    verts, faces = [], []
    for j, (length, width, droop) in enumerate(tails):
        spread = (j - (len(tails) - 1) / 2)
        u = np.linspace(0, 1, k)
        pts = (root[None] + out[None] * (length * u * 0.92)[:, None] + side[None] * (spread * 0.035 * u)[:, None]
               + np.array([0, 0, 1.0])[None] * (-droop * length * u ** 1.6)[:, None])
        # the ribbon's flat faces sideways, twisting by `curl` toward its end
        nrm = np.array([side * math.cos(curl * x) + np.array([0, 0, 1.0]) * math.sin(curl * x) for x in u])
        widths = width * (1.0 - 0.45 * u ** 2)
        widths[-1] = width * 0.15
        v, f = hair_mod.ribbon(pts, nrm, widths, thickness)
        base = len(verts)
        verts.extend(v.tolist())
        faces.extend(tuple(base + i for i in face) for face in f)
    # local x along the tails, from the knot
    ang = math.atan2(out[1], out[0])
    to_local = Matrix.Rotation(-ang, 4, "Z") @ Matrix.Translation(Vector(-root))
    local = [tuple(to_local @ Vector(v)) for v in verts]
    ob = shapes.mesh_object(name, local, faces, material, person.coll, smooth=True, subsurf=1)
    ob.location = tuple(root)
    ob.rotation_euler = (0.0, 0.0, ang)
    return ob


def lapels(person, name: str, garment, *, neck_z: float, cross_z: float, waist_z: float, half_width: float = 0.07,
           cross_x: float = -0.012, width: float = 0.045, lift: float = 0.004, material=None, n: int = 14, push: float = 0.012,
           collar: float = 0.018, under_to: float = 0.05) -> list:
    """A kimono's collar (eri) as one band: up the edge of the left panel from the waist on the wearer's right (where
    the left side has crossed over the right), along the V that `v_neck` cut (`cross_z`, `half_width`, `cross_x`) to
    the side of the neck, round the back of the neck standing `collar` off it, and down the right panel's edge to
    `under_to` below the crossing. It lies on the person's closed bodysuit `push` + `lift` out (the garment's own
    push), its flat to the body, so it is never lost in the V's hole. Skinned like `garment`."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    from . import hair as hair_mod
    from . import shapes

    shell = person.parts.get("tights") or garment
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(shell, dg, deform=False)
    co = np.array([v.co[:] for v in shell.data.vertices])
    ring = co[np.abs(co[:, 2] - neck_z) < 0.012]
    ncx, ncy = ring[:, 0].mean(), ring[:, 1].mean()
    nr = np.median(np.hypot(ring[:, 0] - ncx, ring[:, 1] - ncy))
    top_z = neck_z

    def v_line(z, sgn):
        k = (z - cross_z) / max(top_z - cross_z, 1e-6)
        return cross_x + sgn * half_width * k

    def on_front(x, z):
        hit = bvh.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)), 2.0)
        if hit[0] is None:
            return None
        return np.array(hit[0][:]) + np.array(hit[1][:]) * (push + lift), np.array(hit[1][:])

    pts, nrms = [], []
    # the left panel's edge: from the waist on the wearer's right up to the left side of the neck
    for z in np.linspace(waist_z, top_z - 0.012, n):
        h = on_front(v_line(z, +1), z)
        if h is not None:
            pts.append(h[0])
            nrms.append(h[1])
    # round the back of the neck, from the left (+x) to the right
    for a in np.linspace(0.35, 2 * math.pi - 0.35, 13):
        # a = 0 at the front (-y), pi at the back; +x is the left
        d = np.array([math.sin(a), -math.cos(a), 0.0])
        if abs(math.sin(a)) > 0.93 or abs(a - math.pi) < 2.3:
            p = np.array([ncx, ncy, top_z + 0.004]) + d * (nr + collar)
            pts.append(p)
            nrms.append(d)
    # the right panel's edge, down to just below the crossing (the left panel lies over the rest)
    for z in np.linspace(top_z - 0.012, cross_z - under_to, max(4, n // 2)):
        h = on_front(v_line(z, -1), z)
        if h is not None:
            pts.append(h[0] - h[1] * lift * 0.5)
            nrms.append(h[1])
    pts, nrms = np.array(pts), np.array(nrms)
    v, f = hair_mod.ribbon(pts, nrms, np.full(len(pts), width), 0.003)
    ob = shapes.mesh_object(name, v.tolist(), f, material, person.coll, smooth=True, subsurf=1)
    human.skin_like(ob, garment, person.rig)
    person.parts[name] = ob
    return [ob]


def legs(person, name: str, *, waist_z: float, hem_z: float, hips: tuple = (0.13, 0.14), hem: tuple = (0.22, 0.24),
         knee: tuple | None = None, pleats: int = 5, depth: float = 0.018, ragged: tuple | None = None, material=None, rings: int = 16,
         around: int = 28, seed: int = 1, waist: tuple | None = None):
    """Wide divided trouser legs (a hakama): for each leg a tube from `waist_z` to `hem_z` round the rest pose's leg,
    its half-widths across and front to back `waist` at the top (default `hips`: cinch it with less), `hips` at the
    hip joint, swelling through `knee` (default between) to `hem`,
    folded into `pleats` down its front `depth` deep, the hem `ragged` (amp, count) when given; the two tubes overlap
    at the middle and read as one garment. Skinned by height down each leg (human.skin_by_height). Returns the object."""
    import bpy

    from . import shapes

    rng = np.random.default_rng(seed)
    verts, faces = [], []
    obs = []
    for side in ("L", "R"):
        sgn = 1 if side == "L" else -1
        hip = person.rest(f"upperleg01.{side}")
        kn = person.rest(f"lowerleg01.{side}")
        ank = person.rest(f"foot.{side}")
        hip_z, knee_z = hip.z, kn.z

        def centre(z):
            # follow the leg: the hip joint at the top (nudged in to the middle), the ankle at the bottom
            xs = [ank.x, kn.x, hip.x * 0.8, hip.x * 0.8]
            ys = [ank.y, kn.y, hip.y, hip.y]
            zz = [ank.z, kn.z, hip.z, waist_z + 0.01]
            return float(np.interp(z, zz, xs)), float(np.interp(z, zz, ys))

        kx, ky = knee if knee is not None else ((hips[0] + hem[0]) / 2, (hips[1] + hem[1]) / 2)
        base = len(verts)
        for i in range(rings):
            u = i / (rings - 1)
            z = waist_z + (hem_z - waist_z) * u
            wx, wy = waist if waist is not None else hips
            rx = float(np.interp(z, [hem_z, knee_z, hip_z, waist_z], [hem[0], kx, hips[0], wx]))
            ry = float(np.interp(z, [hem_z, knee_z, hip_z, waist_z], [hem[1], ky, hips[1], wy]))
            cx, cy = centre(z)
            for j in range(around):
                a = 2 * math.pi * j / around       # 0 at the front (-y)
                r = 1.0
                if abs(math.sin(a / 2)) < 0.72:    # the front half: the pleats
                    r += depth / max(rx, 1e-6) * (0.4 + u) * abs(math.sin(pleats * a))
                x = cx + sgn * rx * r * math.sin(a) * (1.0 if math.sin(a) * sgn > 0 else 0.85)
                y = cy - ry * r * math.cos(a)
                zz = z
                if ragged and i == rings - 1:
                    amp, count = ragged
                    zz += amp * (0.5 + 0.5 * math.cos(count * a + sgn)) * rng.uniform(0.3, 1.2)
                verts.append((x, y, zz))
        for i in range(rings - 1):
            for j in range(around):
                a0 = base + i * around + j
                a1 = base + i * around + (j + 1) % around
                faces.append((a0, a0 + around, a1 + around, a1) if sgn > 0 else (a0, a1, a1 + around, a0 + around))
        leg = shapes.mesh_object(f"{name}.{side}", verts[base:], [tuple(k - base for k in f) for f in faces[-(rings - 1) * around:]],
                                 material, person.coll, smooth=True, subsurf=1)
        human.skin_by_height(leg, person.rig, [(waist_z + 0.05, f"pelvis.{side}"), (hip_z - 0.02, f"pelvis.{side}"),
                                                (hip_z - 0.13, f"upperleg02.{side}"), (knee_z + 0.07, f"upperleg02.{side}"),
                                                (knee_z - 0.05, f"lowerleg01.{side}"), (knee_z - 0.22, f"lowerleg02.{side}")])
        obs.append(leg)
    person.parts[name] = obs
    return obs

