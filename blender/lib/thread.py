"""The film's thread in Blender: plies twisted around a smooth centreline, as bevelled curve objects, with fibre fuzz
as hair curves.

The geometry (`centreline`, `ply_paths`) is numpy only and tested under the tools project; `ply_thread` builds the
objects in Blender. Units are the scene's (a macro shot can work in real millimetres or scale the thread up: the
twist and the fuzz follow the radius).

Plies that just touch inside a thread of radius R: n round plies of radius r = R s / (1 + s) on a ring of radius
R / (1 + s), s = sin(pi / n) (three plies: r = 0.464 R). They wind around the centreline at `twist` turns per unit of
length, carried along it by parallel transport, so a bent thread does not corkscrew its plies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def _catmull_rom(p0, p1, p2, p3, u: np.ndarray) -> np.ndarray:
    """Centripetal Catmull-Rom between p1 and p2 at u in [0, 1] (passes through p1 at 0 and p2 at 1)."""
    def knot(a, b):
        return max(float(np.linalg.norm(b - a)) ** 0.5, 1e-12)

    t0, t1 = 0.0, knot(p0, p1)
    t2 = t1 + knot(p1, p2)
    t3 = t2 + knot(p2, p3)
    t = (t1 + (t2 - t1) * u)[:, None]
    a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
    a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
    a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
    b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
    b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
    return (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2


def centreline(points, step: float) -> np.ndarray:
    """A smooth path through every point (centripetal Catmull-Rom), sampled evenly along each span at most `step` apart."""
    p = np.asarray(points, float)
    keep = np.concatenate([[True], np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-12])
    p = p[keep]
    if len(p) < 2:
        raise ValueError("a thread needs two distinct points")
    ext = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    dense_u = np.linspace(0, 1, 257)
    out = [p[:1]]
    for i in range(len(p) - 1):
        dense = _catmull_rom(ext[i], ext[i + 1], ext[i + 2], ext[i + 3], dense_u)
        dense[0], dense[-1] = p[i], p[i + 1]
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))])
        m = max(1, math.ceil(s[-1] / step))
        at = np.linspace(0, s[-1], m + 1)[1:]
        seg = np.column_stack([np.interp(at, s, dense[:, k]) for k in range(3)])
        seg[-1] = p[i + 1]
        out.append(seg)
    return np.vstack(out)


def transport_frames(c: np.ndarray):
    """Tangents, normals and binormals along a polyline, the normal carried by parallel transport (no twist of its own)."""
    d = np.gradient(c, axis=0)
    T = d / np.linalg.norm(d, axis=1, keepdims=True)
    helper = np.array([0.0, 0.0, 1.0]) if abs(T[0, 2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    N = np.empty_like(T)
    n = np.cross(T[0], helper)
    N[0] = n / np.linalg.norm(n)
    for i in range(1, len(T)):
        axis = np.cross(T[i - 1], T[i])
        s = np.linalg.norm(axis)
        n = N[i - 1]
        if s > 1e-12:  # rotate the previous normal by the turn from T[i-1] to T[i] (Rodrigues)
            k = axis / s
            cos = float(np.clip(np.dot(T[i - 1], T[i]), -1, 1))
            n = n * cos + np.cross(k, n) * s + k * np.dot(k, n) * (1 - cos)
        n = n - T[i] * np.dot(n, T[i])
        N[i] = n / np.linalg.norm(n)
    return T, N, np.cross(T, N)


def ply_geometry(radius: float, plies: int) -> tuple[float, float]:
    """(ply radius, radius of the ring the ply centres sit on) for plies that just touch inside `radius`."""
    if plies < 1:
        raise ValueError("plies must be at least 1")
    if plies == 1:
        return radius, 0.0
    s = math.sin(math.pi / plies)
    return radius * s / (1 + s), radius / (1 + s)


def default_twist(radius: float) -> float:
    """One turn every 8 thread radii (a ply angle of about 23 degrees): turns per unit length."""
    return 1 / (8 * radius)


def ply_paths(points, radius: float, plies: int = 3, twist: float | None = None, samples_per_turn: int = 24):
    """The ply centrelines of a thread through `points`: ([array (m, 3)] per ply, ply radius)."""
    twist = default_twist(radius) if twist is None else twist
    rp, ro = ply_geometry(radius, plies)
    step = min(1 / (abs(twist) * samples_per_turn) if twist else math.inf, radius * 4)
    c = centreline(points, step)
    _, N, B = transport_frames(c)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
    out = []
    for k in range(plies):
        th = (2 * math.pi * k / plies + 2 * math.pi * twist * s)[:, None]
        out.append(c + ro * (np.cos(th) * N + np.sin(th) * B))
    return out, rp


def fuzz_strands(c: np.ndarray, radius: float, count: int, seed: int = 1, length: float = 0.9):
    """Loose fibres standing off the thread: (points (count, 4, 3), radii (count, 4)). Roots sit just under the
    surface at random places along and around it; each fibre leans along the thread and bends a little as it goes.
    `length` is the typical fibre length in thread radii. Seeded: the same arguments give the same fuzz."""
    rng = np.random.default_rng(seed)
    T, N, B = transport_frames(c)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
    at = rng.uniform(0, s[-1], count)
    idx = np.clip(np.searchsorted(s, at), 1, len(c) - 1)
    f = ((at - s[idx - 1]) / np.maximum(s[idx] - s[idx - 1], 1e-12))[:, None]
    pos = c[idx - 1] * (1 - f) + c[idx] * f
    t, n, b = T[idx], N[idx], B[idx]
    th = rng.uniform(0, 2 * math.pi, count)[:, None]
    u = np.cos(th) * n + np.sin(th) * b  # outward
    root = pos + u * radius * 0.9
    lean = rng.uniform(-1, 1, count)[:, None]
    lift = rng.uniform(0.25, 0.9, count)[:, None]
    d = u * lift + t * lean
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    ln = np.clip(radius * length * rng.lognormal(0, 0.45, count), radius * 0.25, radius * 3)[:, None]
    bend_dir = np.cross(d, u)
    bend_dir /= np.maximum(np.linalg.norm(bend_dir, axis=1, keepdims=True), 1e-12)
    bend = rng.normal(0, 0.18, count)[:, None]
    k = np.linspace(0, 1, 4)[None, :, None]
    pts = root[:, None] + d[:, None] * ln[:, None] * k + bend_dir[:, None] * (bend * ln)[:, None] * k**2
    radii = radius * 0.02 * np.linspace(1.0, 0.4, 4)[None, :].repeat(count, 0)
    return pts, radii


@dataclass
class Thread:
    root: object  # the empty everything hangs from
    plies: list = field(default_factory=list)  # curve objects
    fuzz: object | None = None  # hair curves object
    radius: float = 0.0
    ply_radius: float = 0.0
    path: np.ndarray | None = None  # the centreline


def ply_thread(points, radius: float, plies: int = 3, twist: float | None = None, fuzz: bool = True, *,
               material=None, fuzz_material=None, name: str = "thread", seed: int = 1, fuzz_per_radius: float = 4.0,
               fuzz_length: float = 0.9, bevel_resolution: int = 4, collection=None) -> Thread:
    """Build a thread through `points` (scene units): `plies` twisted curve objects with a round bevel, and, with
    `fuzz`, loose fibres as a hair-curves object (about `fuzz_per_radius` fibres per radius of length). Everything is
    parented to an empty named `name`; returns a Thread."""
    import bpy

    coll = collection or bpy.context.scene.collection
    root = bpy.data.objects.new(name, None)
    root.empty_display_size = radius * 4
    coll.objects.link(root)
    paths, rp = ply_paths(points, radius, plies, twist)
    th = Thread(root=root, radius=radius, ply_radius=rp)
    for k, p in enumerate(paths):
        cu = bpy.data.curves.new(f"{name}.ply{k}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_mode = "ROUND"
        cu.bevel_depth = rp
        cu.bevel_resolution = bevel_resolution
        cu.use_fill_caps = True
        sp = cu.splines.new("POLY")
        sp.points.add(len(p) - 1)
        sp.points.foreach_set("co", np.column_stack([p, np.ones(len(p))]).ravel().tolist())
        ob = bpy.data.objects.new(f"{name}.ply{k}", cu)
        if material is not None:
            cu.materials.append(material)
        ob.parent = root
        coll.objects.link(ob)
        th.plies.append(ob)
    th.path = centreline(points, min(radius * 2, 1 / (abs(twist or default_twist(radius)) * 24)))
    if fuzz:
        s = np.linalg.norm(np.diff(th.path, axis=0), axis=1).sum()
        count = max(1, int(fuzz_per_radius * s / radius))
        pts, radii = fuzz_strands(th.path, radius, count, seed, fuzz_length)
        hc = bpy.data.hair_curves.new(f"{name}.fuzz")
        hc.add_curves([pts.shape[1]] * count)
        hc.attributes["position"].data.foreach_set("vector", pts.reshape(-1).tolist())
        ra = hc.attributes.get("radius") or hc.attributes.new("radius", "FLOAT", "POINT")
        ra.data.foreach_set("value", radii.reshape(-1).tolist())
        mat = fuzz_material or material
        if mat is not None:
            hc.materials.append(mat)
        ob = bpy.data.objects.new(f"{name}.fuzz", hc)
        ob.parent = root
        coll.objects.link(ob)
        th.fuzz = ob
    return th
