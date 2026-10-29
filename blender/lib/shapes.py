"""Shapes for building characters, props and sets from code: lofts along paths (limbs, sleeves, trousers, a hull),
ellipsoids (heads, hands), surfaces of revolution (a hat, a lantern, a tree's tier), clumps of spikes (anime hair,
grass), flat strips (straw, ribbons, fringes), boxes and cylinders, each a Blender object in a collection with its
material.

The point math (`loft_points`, `frames`, the rotations) is numpy only and tested without Blender; the builders import
bpy when called."""
from __future__ import annotations

import math

import numpy as np


def frames(path: np.ndarray, up=(0.0, 0.0, 1.0)) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per point of a polyline: its tangent, and two normals square to it (u across, v along `up` as near as can be),
    rotation-minimising from the first so a lofted tube never twists."""
    p = np.asarray(path, float)
    t = np.gradient(p, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    up = np.asarray(up, float)
    u0 = np.cross(up, t[0])
    if np.linalg.norm(u0) < 1e-6:
        u0 = np.cross((1.0, 0.0, 0.0), t[0])
    u = [u0 / np.linalg.norm(u0)]
    for i in range(1, len(p)):
        # carry the previous frame over by the rotation that takes t[i-1] to t[i]
        a = u[-1] - t[i] * np.dot(u[-1], t[i])
        n = np.linalg.norm(a)
        u.append(a / n if n > 1e-9 else u[-1])
    u = np.array(u)
    v = np.cross(t, u)
    return t, u, v


def loft_points(path, ru, rv=None, *, n: int = 16, power: float = 2.0, up=(0, 0, 1), twist=None, offset=None):
    """Rings of `n` points round each point of `path`: a superellipse (`power` 2 an ellipse, higher boxier) of
    half-widths ru (across) and rv (along the up side) per point. `offset` (k, 2) shifts each ring in its own (u, v)."""
    p = np.asarray(path, float)
    k = len(p)
    ru = np.broadcast_to(np.asarray(ru, float), (k,))
    rv = ru if rv is None else np.broadcast_to(np.asarray(rv, float), (k,))
    _, u, v = frames(p, up)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    c, s = np.cos(ang), np.sin(ang)
    sc = np.sign(c) * np.abs(c) ** (2 / power)
    ss = np.sign(s) * np.abs(s) ** (2 / power)
    rings = []
    for i in range(k):
        tw = 0.0 if twist is None else twist[i]
        cu, cv = sc * math.cos(tw) - ss * math.sin(tw), sc * math.sin(tw) + ss * math.cos(tw)
        o = (0.0, 0.0) if offset is None else offset[i]
        rings.append(p[i] + u[i] * (ru[i] * cu + o[0])[:, None] + v[i] * (rv[i] * cv + o[1])[:, None])
    return np.array(rings)  # (k, n, 3)


def tube_faces(k: int, n: int, cap: bool = True) -> list[tuple[int, ...]]:
    faces = []
    for i in range(k - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    if cap:
        faces.append(tuple(range(n - 1, -1, -1)))
        faces.append(tuple((k - 1) * n + j for j in range(n)))
    return faces


def lofts(name: str, specs, *, material=None, coll=None, n: int = 8, power: float = 2.0, subsurf: int = 1, cap: bool = True):
    """Many lofts in one mesh (a head of hair, a fringe): `specs` is [(path, ru, rv), ...] as `loft` takes them."""
    verts, faces = [], []
    for path, ru, rv in specs:
        rings = loft_points(path, ru, rv, n=n, power=power)
        k = len(rings)
        base = len(verts)
        verts.extend(rings.reshape(-1, 3))
        faces.extend(tuple(base + i for i in f) for f in tube_faces(k, n, cap))
    return mesh_object(name, verts, faces, material, coll, subsurf=subsurf)


def patch(name: str, outline, *, depth_axis=0, depth: float = 0.0, material=None, coll=None, xform=None, subdiv: int = 2):
    """A flat polygon (a decal: an eye, a brow, a mouth), `outline` [(u, v), ...] in the plane square to `depth_axis`
    at `depth`, triangulated as a fan round its centre and subdivided flat (`subdiv`) so a shrinkwrap can bend it;
    `xform(p)` maps each point to the world (the head's tilt and place)."""
    pts = np.asarray(outline, float)
    c = pts.mean(0)

    def lift(u, v):
        p = [0.0, 0.0, 0.0]
        axes = [a for a in range(3) if a != depth_axis]
        p[depth_axis] = depth
        p[axes[0]], p[axes[1]] = u, v
        p = np.asarray(p)
        return xform(p) if xform else p
    verts = [lift(*c)] + [lift(u, v) for u, v in pts]
    k = len(pts)
    faces = [(0, i + 1, (i + 1) % k + 1) for i in range(k)]
    ob = mesh_object(name, verts, faces, material, coll, smooth=False)
    if subdiv:
        m = ob.modifiers.new("subdiv", "SUBSURF")
        m.subdivision_type = "SIMPLE"
        m.levels = m.render_levels = subdiv
    return ob


def mesh_object(name: str, verts, faces, material=None, coll=None, smooth: bool = True, subsurf: int = 0):
    import bpy

    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], [tuple(f) for f in faces])
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    if smooth:
        for poly in me.polygons:
            poly.use_smooth = True
    if material is not None:
        me.materials.append(material)
    if subsurf:
        m = ob.modifiers.new("subsurf", "SUBSURF")
        m.levels = m.render_levels = subsurf
    return ob


def loft(name: str, path, ru, rv=None, *, material=None, coll=None, n: int = 16, power: float = 2.0, cap=True,
         subsurf: int = 1, up=(0, 0, 1), offset=None, hem=None):
    """A tube lofted along `path`. `hem` (amp, count) zigzags the last ring (a tattered hem)."""
    rings = loft_points(path, ru, rv, n=n, power=power, up=up, offset=offset)
    if hem:
        amp, count = hem
        last = rings[-1].copy()
        t = np.asarray(path[-1], float) - np.asarray(path[-2], float)
        t /= np.linalg.norm(t)
        rng = np.random.default_rng(len(name) * 7 + n)
        for j in range(len(last)):
            last[j] += t * amp * (0.5 + 0.5 * math.cos(2 * math.pi * count * j / len(last))) * rng.uniform(0.4, 1.3)
        rings[-1] = last
    k, nn = rings.shape[:2]
    return mesh_object(name, rings.reshape(-1, 3), tube_faces(k, nn, cap), material, coll, subsurf=subsurf)


def ellipsoid(name: str, center, radii, *, material=None, coll=None, n: int = 20, rot=None, squash=None):
    """An ellipsoid of `radii` (x, y, z) at `center`, optionally rotated (a 3x3 matrix); `squash(p)` may reshape the
    unit-sphere points first (an egg, a jaw)."""
    rows, cols = n // 2, n
    verts = []
    for i in range(rows + 1):
        th = math.pi * i / rows
        for j in range(cols):
            ph = 2 * math.pi * j / cols
            verts.append((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th)))
    v = np.array(verts)
    if squash is not None:
        v = squash(v)
    v = v * np.asarray(radii, float)
    if rot is not None:
        v = v @ np.asarray(rot, float).T
    v = v + np.asarray(center, float)
    faces = []
    for i in range(rows):
        for j in range(cols):
            a, b = i * cols + j, i * cols + (j + 1) % cols
            faces.append((a, b, b + cols, a + cols))
    ob = mesh_object(name, v, faces, material, coll)
    ob.data.validate()
    return ob


def lathe(name: str, profile, *, material=None, coll=None, n: int = 24, center=(0, 0, 0), rot=None, smooth=True):
    """A surface of revolution about z: `profile` is [(radius, z), ...] from bottom to top."""
    prof = np.asarray(profile, float)
    verts = []
    for r, z in prof:
        for j in range(n):
            a = 2 * math.pi * j / n
            verts.append((r * math.cos(a), r * math.sin(a), z))
    v = np.array(verts)
    if rot is not None:
        v = v @ np.asarray(rot, float).T
    v = v + np.asarray(center, float)
    return mesh_object(name, v, tube_faces(len(prof), n, cap=False), material, coll, smooth=smooth)


def box(name: str, center, size, *, material=None, coll=None, rot_z: float = 0.0, rot=None):
    import bpy

    cx, cy, cz = center
    sx, sy, sz = (s / 2 for s in size)
    v = np.array([(x, y, z) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)])
    R = np.asarray(rot, float) if rot is not None else np.array(
        [[math.cos(rot_z), -math.sin(rot_z), 0], [math.sin(rot_z), math.cos(rot_z), 0], [0, 0, 1]])
    v = v @ R.T + np.array([cx, cy, cz])
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    ob = mesh_object(name, v, faces, material, coll, smooth=False)
    return ob


def cylinder(name: str, a, b, r, *, material=None, coll=None, n: int = 12, r2=None):
    """A capped cylinder from point a to point b (radius r, r2 at b)."""
    return loft(name, np.array([a, b], float), [r, r if r2 is None else r2], material=material, coll=coll, n=n,
                subsurf=0, up=(0, 1, 0) if abs(np.subtract(b, a)[2]) > 0.9 * np.linalg.norm(np.subtract(b, a)) else (0, 0, 1))


def spikes(name: str, roots, tips, widths, *, material=None, coll=None, sides: int = 4):
    """A clump of spikes (anime hair): a cone from each root (radius `widths[i]`) to its tip, joined in one mesh."""
    verts, faces = [], []
    for r0, t0, w in zip(np.asarray(roots, float), np.asarray(tips, float), widths):
        d = t0 - r0
        d /= np.linalg.norm(d)
        a = np.cross(d, (0, 0, 1))
        if np.linalg.norm(a) < 1e-6:
            a = np.cross(d, (1, 0, 0))
        a /= np.linalg.norm(a)
        b = np.cross(d, a)
        base = len(verts)
        for j in range(sides):
            ang = 2 * math.pi * j / sides
            verts.append(r0 + w * (math.cos(ang) * a + 0.6 * math.sin(ang) * b))
        verts.append(t0)
        tip = base + sides
        for j in range(sides):
            faces.append((base + j, base + (j + 1) % sides, tip))
        faces.append(tuple(base + j for j in range(sides - 1, -1, -1)))
    return mesh_object(name, verts, faces, material, coll, smooth=False)


def strips(name: str, roots, dirs, lengths, widths, *, material=None, coll=None, segs: int = 3, droop=None):
    """Flat strips (straw, ribbon ends): from each root along its direction for its length, `widths[i]` wide, in
    `segs` segments; `droop` (k, 3) bends each strip's far end by that vector."""
    verts, faces = [], []
    for i, (r0, d0, L, w) in enumerate(zip(np.asarray(roots, float), np.asarray(dirs, float), lengths, widths)):
        d = d0 / np.linalg.norm(d0)
        side = np.cross(d, (0, 0, 1))
        if np.linalg.norm(side) < 1e-6:
            side = np.array([1.0, 0, 0])
        side /= np.linalg.norm(side)
        base = len(verts)
        for s in range(segs + 1):
            f = s / segs
            c = r0 + d * L * f + (0 if droop is None else np.asarray(droop[i]) * f * f)
            ww = w * (1 - 0.6 * f)
            verts += [c - side * ww / 2, c + side * ww / 2]
        for s in range(segs):
            a = base + 2 * s
            faces.append((a, a + 1, a + 3, a + 2))
    return mesh_object(name, verts, faces, material, coll, smooth=False)


def rot_y(a: float) -> np.ndarray:
    return np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])


def rot_z(a: float) -> np.ndarray:
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])


def rot_x(a: float) -> np.ndarray:
    return np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])


def place(ob, location=(0, 0, 0), rotation_z: float = 0.0):
    """Move an object built about the origin to `location`, turned `rotation_z` about z."""
    ob.location = location
    ob.rotation_euler = (0, 0, rotation_z)
    return ob
