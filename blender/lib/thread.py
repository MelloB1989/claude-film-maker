"""The film's thread in Blender: plies twisted around a smooth centreline, as bevelled curve objects, with fibre fuzz
as hair curves.

The geometry (`centreline`, `ply_paths`) is numpy only and tested under the tools project; `ply_thread` builds the
objects in Blender. Units are the scene's (a macro shot can work in real millimetres or scale the thread up: the
twist and the fuzz follow the radius).

Plies that just touch inside a thread of radius R: n round plies of radius r = R s / (1 + s) on a ring of radius
R / (1 + s), s = sin(pi / n) (three plies: r = 0.464 R). They wind around the centreline at `twist` turns per unit of
length, carried along it by parallel transport, so a bent thread does not corkscrew its plies.

Two more threads, both the engine's look: the macro rope (B01's bone 3-ply, fibre by fibre: `fibre_rope`, `MacroRope`)
and the diff thread every later shot shows (`DIFF_THREAD`, `diff_thread`: the engine's preset, read from
data/look/thread.json, with its strands lit on meaning by `strand_glow`).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

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


# ------------------------------------------------------------------------------------------------ the macro rope
#
# The macro thread (B01, and any shot close enough to see fibres): the bone 3-ply rope of the engine's THREAD_LOOK,
# built fibre by fibre. Each ply is a round core wrapped in a sheath of surface fibres, each fibre a curve that winds
# round its ply against the ply's own lay (the singles twist), dives in and out of the surface (migration) and now and
# then stands off it in a loop; fuzz fibres stand off the plies and catch the rim light. So the striation, the crevice
# shading and the fibre sheen of the engine's shader come from real geometry here.
#
# Everything is measured along the rope's material coordinate s (its rest arc length, world units): twist, fray and the
# break are fixed to the material, so a rope that bends, stretches or recoils carries its plies and fibres with it.
# `FibreRope` holds the seeded, static tables (where every fibre and fuzz fibre is); a `RopePose` (per half: the left
# half runs from s = 0 to the break, the right from the break to the end) says where the centreline is at an instant
# and how frayed, unravelled and splayed each part is; `rope_geometry` turns the two into points. The halves overlap
# round the break (fibres break at staggered places); posed alike, they make one continuous rope.
#
# The geometry is numpy only (tested under the tools project); `MacroRope` builds and updates the Blender objects.

LOOK = {
    # the engine's THREAD_LOOK (app/src/engine/thread3d.ts) for the bone 3-ply; lengths in thread radii R
    "ply_radius": 0.5, "ply_offset": 0.5,  # three plies of 0.5 R on a circle of 0.5 R: pressed 13% into each other
    "lay_deg": 32.0,  # right-hand (Z) lay against the axis: 0.199 turns per R, a lay length of 5.03 R
    "fibre_lay": 0.6,  # crown fibres lean 60% of the way from the ply's lay to the thread axis (about 13 degrees)
    "fibres": 40,  # striations round a ply
    "fray_span": 10.0, "fray_separation": 1.4, "fray_swell": 0.12, "fray_untwist": 1.35,
    "fuzz_density": 2.0, "fuzz_length": (0.15, 0.5), "fray_density": 4.0, "fray_length": (0.4, 1.6),
    # the diff thread (below): its strands in the bone plies' grooves, of radius worm_radius (x DIFF_THREAD's
    # strand_scale), dyed `dye` of the way to their dim shade, with a core glowing (1 - soft)(N.V)^28 + soft (N.V)^3
    "worm_radius": 0.2, "dye": 0.82, "glow_falloff": (28, 3), "glow_soft": 0.2,
    # the plies' fibre surface on a smooth tube: roughness along the fibres, specular (x F0 at the IOR), sheen
    "roughness": 0.42, "specular": 0.8, "ior": 1.5, "sheen": 1.0, "sheen_roughness": 0.35,
}


def lay_turns(lay_deg: float, offset: float) -> float:
    """Turns per unit length of a helix at radius `offset` lying `lay_deg` degrees off its axis."""
    return math.tan(math.radians(lay_deg)) / (2 * math.pi * offset)


def bump(y):
    """The raised cosine on [-1, 1] (1 at 0, 0 outside), the fray's profile as the engine draws it."""
    y = np.asarray(y, float)
    return np.where(np.abs(y) < 1, 0.5 + 0.5 * np.cos(np.pi * np.clip(y, -1, 1)), 0.0)


def bump_int(y):
    """The integral of bump from -1 to y: 0 before, 1 after."""
    y = np.clip(np.asarray(y, float), -1, 1)
    return 0.5 * (y + 1) + np.sin(np.pi * y) / (2 * np.pi)


def untwisted(s, centre: float, span: float, amount, untwist: float):
    """The twist coordinate of a fray (turns = twist x this): the rope's own s, less the twist a fray of `amount`
    takes out round `centre` (the rate there falls to 1 - 2/3 untwist), all of it put back on the shoulders over a bump
    three times as wide, so the rope beyond them never turns (the engine's rule)."""
    y = (np.asarray(s, float) - centre) / span
    return np.asarray(s, float) - np.asarray(amount, float) * untwist * span * (bump_int(y) - bump_int(y / 3))


def rmf(X: np.ndarray, n0, reverse: bool = False):
    """Rotation-minimising frames along a polyline by double reflection (Wang et al. 2008): (T, N, B), B = T x N, the
    normal starting as n0 at the first point (the last with `reverse`) and carried along without twist."""
    X = np.asarray(X, float)
    m = len(X)
    d = np.gradient(X, axis=0)
    T = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    N = np.empty_like(X)
    order = range(m - 1, -1, -1) if reverse else range(m)
    order = list(order)
    i0 = order[0]
    n = np.asarray(n0, float) - T[i0] * np.dot(n0, T[i0])
    N[i0] = n / np.linalg.norm(n)
    for a, b in zip(order[:-1], order[1:]):
        v1 = X[b] - X[a]
        c1 = float(v1 @ v1)
        if c1 < 1e-24:
            N[b] = N[a]
            continue
        rL = N[a] - (2 / c1) * (v1 @ N[a]) * v1
        tL = T[a] - (2 / c1) * (v1 @ T[a]) * v1
        v2 = T[b] - tL
        c2 = float(v2 @ v2)
        nb = rL - (2 / c2) * (v2 @ rL) * v2 if c2 > 1e-24 else rL
        nb = nb - T[b] * (nb @ T[b])
        N[b] = nb / np.linalg.norm(nb)
    return T, N, np.cross(T, N)


def interp_rows(x, xp, fp):
    """Rows of fp (m, k), sampled at xp (increasing), linearly interpolated at x (n,): (n, k). Held at the ends."""
    x = np.asarray(x, float)
    i = np.clip(np.searchsorted(xp, x, side="right"), 1, len(xp) - 1)
    t = np.clip((x - xp[i - 1]) / np.maximum(xp[i] - xp[i - 1], 1e-12), 0, 1)[:, None]
    return fp[i - 1] * (1 - t) + fp[i] * t


@dataclass
class FibreRope:
    """The static tables of a fibre-level 3-ply rope (see `fibre_rope`). Lengths in world units."""
    R: float
    length: float
    twist: float  # ply turns per unit length (material)
    fibre_twist: float  # singles turns per unit length (material), against the lay
    ply_r: float
    ply_d: float
    core_r: float
    grid: np.ndarray  # material samples along the rope
    break_at: float
    ply_break: np.ndarray  # (3,) where each ply's core parts
    reach: float  # how far a fibre's break can lie from break_at
    # fibres: ply, angle at s = 0, radius (fraction of the ply's), migration, loops, break, thickness, tone
    fib_ply: np.ndarray
    fib_phi: np.ndarray
    fib_rho: np.ndarray
    fib_mig: np.ndarray  # (n, 3) amplitude, wavelength, phase
    fib_loops: np.ndarray  # (n, L, 3) centre, half-width, height (fractions of the ply radius); height 0 = none
    fib_break: np.ndarray
    fib_radius: np.ndarray
    fib_tone: np.ndarray
    fib_splay: np.ndarray  # (n,) how far the fibre fans out at a free end, and its direction (turns)
    # fuzz and fray fibres (roots on a ply, a shape in the local frame)
    fz_ply: np.ndarray
    fz_s: np.ndarray
    fz_phi: np.ndarray
    fz_len: np.ndarray
    fz_lift: np.ndarray  # radians at rest
    fz_dir: np.ndarray  # +1 along the ply, -1 against
    fz_curl: np.ndarray  # (n, 2) up and sideways bend
    fz_fray: np.ndarray  # 1 for a fray fibre (lies flat until the fray lifts it), 0 for fuzz
    fz_radius: np.ndarray
    fz_tone: np.ndarray
    fib_crimp: np.ndarray | None = None  # (n, 4) amplitude, wavelength, phase round, phase out
    fz_kink: np.ndarray | None = None  # (n, 4) amplitude (x length), cycles, two phases
    fib_frayloop: np.ndarray | None = None  # (n, 3) centre, half-width, height (x ply radius) of a loop the fray pulls out
    points_per_fuzz: int = 9
    fray_loose: float = 0.12  # how far a fray loosens the sheath's fibres off their ply (x the ply radius)
    fray_separation: float = LOOK["fray_separation"]  # at full fray the plies stand 1 + this x their offset
    fray_swell: float = LOOK["fray_swell"]  # and swell by this
    fray_untwist: float = LOOK["fray_untwist"]  # and the twist rate at the middle falls to 1 - 2/3 of this


def fibre_rope(R: float, length: float, *, break_at: float | None = None, seed: int = 1,
               lay_deg: float = LOOK["lay_deg"], fibres: int = 56, fibre_radius: float = 0.028,
               core: float = 0.8, samples_per_R: float = 8.0, fuzz_per_R: float = 10.0,
               fray_per_R: float = LOOK["fray_density"] * 3, fray_span: float = LOOK["fray_span"],
               loops: float = 0.12, reach: float = 3.0) -> FibreRope:
    """A seeded fibre-level 3-ply rope of radius R and material length `length` (world units), THREAD_LOOK's bone rope:
    plies of 0.5 R on a circle of 0.5 R at a `lay_deg` lay, each a core of `core` x its radius under `fibres` surface
    fibres (radius `fibre_radius` R) whose crown runs `LOOK['fibre_lay']` of the way to the rope's axis. `fuzz_per_R`
    fuzz fibres per R of length stand off the plies, and `fray_per_R` fray fibres lie within `fray_span` R of
    `break_at` (the middle by default), flat until a fray lifts them. Each ply parts near `break_at` and each fibre
    within `reach` R of its ply's parting: a broken end is a brush, not a cut."""
    rng = np.random.default_rng(seed)
    ply_r, ply_d = LOOK["ply_radius"] * R, LOOK["ply_offset"] * R
    twist = lay_turns(lay_deg, ply_d)
    lay = math.radians(lay_deg)
    crown = lay * (1 - LOOK["fibre_lay"])  # crown fibres against the rope's axis
    # the singles twist: at the ply's surface the fibres lie (lay - crown) off the ply's axis, the other hand
    fibre_twist = math.tan(lay - crown) / (2 * math.pi * ply_r) / math.cos(lay)  # per unit of rope length
    break_at = length / 2 if break_at is None else break_at
    step = R / samples_per_R
    grid = np.linspace(0.0, length, int(round(length / step)) + 1)

    ply_break = break_at + rng.uniform(-1.2, 1.2, 3) * R
    n = 3 * fibres
    fib_ply = np.repeat(np.arange(3), fibres)
    fib_phi = (np.tile(np.arange(fibres), 3) + rng.uniform(-0.35, 0.35, n)) * (2 * np.pi / fibres)
    fib_rho = rng.uniform(0.86, 1.0, n)
    fib_mig = np.column_stack([rng.uniform(0.02, 0.07, n), rng.uniform(3.0, 9.0, n) * R, rng.uniform(0, 2 * np.pi, n)])
    n_loops = max(1, int(round(loops * length / R / 10)))
    fib_loops = np.zeros((n, n_loops, 3))
    fib_loops[..., 0] = rng.uniform(0, length, (n, n_loops))
    fib_loops[..., 1] = rng.uniform(0.6, 1.8, (n, n_loops)) * R
    fib_loops[..., 2] = np.where(rng.random((n, n_loops)) < 0.35, rng.uniform(0.15, 0.7, (n, n_loops)), 0.0)
    fib_break = ply_break[fib_ply] + rng.uniform(-1, 1, n) * reach * R * rng.uniform(0.3, 1.0, n)
    fib_radius = fibre_radius * R * rng.uniform(0.75, 1.2, n)
    fib_tone = rng.uniform(0.9, 1.06, n)
    fib_splay = np.column_stack([rng.lognormal(0, 0.5, n), rng.uniform(-0.25, 0.25, n)])
    fib_crimp = np.column_stack([rng.uniform(0.008, 0.022, n) * R, rng.uniform(0.25, 0.7, n) * R,
                                 rng.uniform(0, 2 * np.pi, n), rng.uniform(0, 2 * np.pi, n)])
    # stress loops: under a fray, fibres near the break arch out of their ply (they only show as the fray opens)
    fib_frayloop = np.column_stack([break_at + rng.normal(0, 0.45, n) * fray_span * R, rng.uniform(0.4, 1.2, n) * R,
                                    np.where(rng.random(n) < 0.45, rng.uniform(0.3, 1.2, n), 0.0)])

    n_fuzz = int(round(fuzz_per_R * length / R))
    n_fray = int(round(fray_per_R * 2 * fray_span))
    m = n_fuzz + n_fray
    fz_fray = np.concatenate([np.zeros(n_fuzz), np.ones(n_fray)])
    fz_ply = rng.integers(0, 3, m)
    fz_s = np.concatenate([rng.uniform(0, length, n_fuzz),
                           break_at + fray_span * R * (rng.random(n_fray) - rng.random(n_fray))])  # a tent round the break
    fz_phi = rng.uniform(-1.4, 1.4, m)  # round the crown (the ply's outer side), not in the crevices
    lo, hi = LOOK["fuzz_length"]
    flo, fhi = LOOK["fray_length"]
    fz_len = np.where(fz_fray > 0, np.clip(rng.lognormal(math.log(0.45 * (flo + fhi) / 2), 0.45, m), 0.6 * flo, fhi),
                      np.clip(rng.lognormal(math.log(0.26), 0.65, m), lo * 0.6, hi * 3.2)) * R
    fz_lift = np.where(fz_fray > 0, rng.uniform(0.0, 0.08, m), np.radians(rng.uniform(6, 55, m)))
    fz_dir = np.where(rng.random(m) < 0.5, -1.0, 1.0)
    fz_curl = np.column_stack([rng.normal(0.2, 0.5, m), rng.normal(0, 0.5, m)])
    fz_radius = np.where(fz_fray > 0, 0.013, 0.0085) * R * rng.uniform(0.7, 1.25, m)
    fz_tone = rng.uniform(0.9, 1.06, m)
    fz_kink = np.column_stack([np.where(fz_fray > 0, rng.uniform(0.08, 0.2, m), rng.uniform(0.03, 0.12, m)),
                               rng.uniform(0.6, 2.2, m), rng.uniform(0, 2 * np.pi, m),
                               rng.uniform(0, 2 * np.pi, m)])
    return FibreRope(R, length, twist, fibre_twist, ply_r, ply_d, core * ply_r, grid, break_at, ply_break,
                     reach * R, fib_ply, fib_phi, fib_rho, fib_mig, fib_loops, fib_break, fib_radius, fib_tone,
                     fib_splay, fz_ply, fz_s, fz_phi, fz_len, fz_lift, fz_dir, fz_curl, fz_fray, fz_radius, fz_tone,
                     fib_crimp=fib_crimp, fz_kink=fz_kink, fib_frayloop=fib_frayloop)


@dataclass
class RopePose:
    """One half of a rope at an instant, on material samples `s` (increasing): its centreline X (m, 3) and normal N
    (m, 3) (rmf), and fields over s: `fray` (0..1, the fray's local amount), `unravel` (extra ply turns), per ply (3, m):
    `splay` (extra ply offset, x the rest offset), `neck` (core thinning 0..1), `brush` (fibre fan-out, R) and `taper`
    (the core's radius factor, 0 at a broken tip)."""
    s: np.ndarray
    X: np.ndarray
    N: np.ndarray
    fray: np.ndarray
    unravel: np.ndarray
    splay: np.ndarray
    neck: np.ndarray
    brush: np.ndarray
    taper: np.ndarray
    lift: float = 0.0  # extra fuzz lift (radians), the heartbeat's flutter
    broken: float = 0.0  # 0 whole, 1 parted: broken fibres thin to their ends


def still_pose(rope: FibreRope, s: np.ndarray, X: np.ndarray, N: np.ndarray, fray=None) -> RopePose:
    """A pose with no break: the fields at rest (optionally a fray field)."""
    m = len(s)
    z3 = np.zeros((3, m))
    return RopePose(s, X, N, np.zeros(m) if fray is None else np.asarray(fray, float), np.zeros(m), z3, z3.copy(),
                    z3.copy(), np.ones((3, m)))


def half_samples(rope: FibreRope, side: str) -> np.ndarray:
    """The material samples of a half: the grid up to (left) or from (right) the furthest a fibre of it reaches past
    the break, with that end sample exact."""
    lo, hi = rope.break_at - rope.reach - 1.5 * rope.R, rope.break_at + rope.reach + 1.5 * rope.R
    g = rope.grid
    if side == "left":
        return np.concatenate([g[g < hi], [hi]])
    return np.concatenate([[lo], g[g > lo]])


def _ply_rows(rope: FibreRope, pose: RopePose, fray_centre: float, fray_span: float, fray_amount: float):
    """Per ply, rows over the pose's samples: centre (3), outward (3), round (3), ply radius, core radius, fibre twist
    coordinate, fray field, brush, neck: (3, m, 14)."""
    s, X, N = pose.s, pose.X, pose.N
    T = np.gradient(X, s, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    N = N - T * np.sum(N * T, axis=1, keepdims=True)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    B = np.cross(T, N)
    phase = rope.twist * untwisted(s, fray_centre, fray_span, fray_amount, rope.fray_untwist) + pose.unravel
    fphase = rope.fibre_twist * untwisted(s, fray_centre, fray_span, fray_amount, 0.7 * rope.fray_untwist)
    rows = np.empty((3, len(s), 14))
    for k in range(3):
        th = 2 * np.pi * (k / 3 + phase)
        o = np.cos(th)[:, None] * N + np.sin(th)[:, None] * B
        d = rope.ply_d * (1 + rope.fray_separation * pose.fray + pose.splay[k])
        P = X + d[:, None] * o
        t = np.gradient(P, s, axis=0)
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
        o = o - t * np.sum(o * t, axis=1, keepdims=True)
        o /= np.maximum(np.linalg.norm(o, axis=1, keepdims=True), 1e-12)
        w = np.cross(t, o)
        rp = rope.ply_r * (1 + rope.fray_swell * pose.fray)
        rc = rope.core_r * (1 - 0.55 * pose.neck[k]) * pose.taper[k]
        rows[k, :, 0:3], rows[k, :, 3:6], rows[k, :, 6:9] = P, o, w
        rows[k, :, 9], rows[k, :, 10], rows[k, :, 11], rows[k, :, 12] = rp, rc, fphase, pose.brush[k]
        rows[k, :, 13] = pose.neck[k]
    return rows, T


@dataclass
class RopeGeometry:
    """Points of one half: cores (per ply: rings (r, seg, 3)), fibres (points (P, 3), per-curve counts, radii (P,)),
    fuzz likewise."""
    cores: list
    fibre_pts: np.ndarray
    fibre_counts: np.ndarray
    fibre_radii: np.ndarray
    fuzz_pts: np.ndarray
    fuzz_counts: np.ndarray
    fuzz_radii: np.ndarray


def half_topology(rope: FibreRope, side: str):
    """Which fibres, fuzz and core samples belong to a half, and at which material samples each fibre is evaluated
    (fixed for the rope, so the objects keep their topology frame to frame)."""
    s = half_samples(rope, side)
    left = side == "left"
    fib = []
    for j, b in enumerate(rope.fib_break):
        pts = np.concatenate([s[s < b], [b]]) if left else np.concatenate([[b], s[s > b]])
        fib.append(pts)
    fz = np.flatnonzero((rope.fz_s < rope.ply_break[rope.fz_ply]) == left)
    cores = []
    for k in range(3):
        c = rope.ply_break[k]
        cores.append(np.concatenate([s[s < c], [c]]) if left else np.concatenate([[c], s[s > c]]))
    return {"s": s, "fibres": fib, "fuzz": fz, "cores": cores}


def rope_geometry(rope: FibreRope, pose: RopePose, topo: dict, *, fray_centre: float, fray_amount: float,
                  ring: int = 12, fray_span: float | None = None) -> RopeGeometry:
    """The points of one half of `rope` in `pose` (its topology from half_topology). `fray_amount` and `fray_centre`
    set the untwist (the fray's local field is pose.fray)."""
    span = (fray_span or LOOK["fray_span"]) * rope.R
    rows, _ = _ply_rows(rope, pose, fray_centre, span, fray_amount)
    s = pose.s
    # cores: rings round each ply's centre
    ang = np.linspace(0, 2 * np.pi, ring, endpoint=False)
    cores = []
    for k in range(3):
        r = interp_rows(topo["cores"][k], s, rows[k])
        P, o, w, rc = r[:, 0:3], r[:, 3:6], r[:, 6:9], r[:, 10]
        cores.append(P[:, None] + rc[:, None, None] * (np.cos(ang)[None, :, None] * o[:, None] + np.sin(ang)[None, :, None] * w[:, None]))
    # fibres
    pts, counts, radii = [], [], []
    ones = np.ones
    for j, fs in enumerate(topo["fibres"]):
        k = rope.fib_ply[j]
        r = interp_rows(fs, s, rows[k])
        P, o, w, rp, fph, br = r[:, 0:3], r[:, 3:6], r[:, 6:9], r[:, 9], r[:, 11], r[:, 12]
        fray = np.interp(fs, s, pose.fray)
        amp, lam, ph = rope.fib_mig[j]
        rho = rope.fib_rho[j] + amp * np.sin(2 * np.pi * fs / lam + ph)
        for c, hw, h in rope.fib_loops[j]:
            if h > 0:
                rho = rho + h * bump((fs - c) / hw)
        rho = rho + fray * rope.fray_loose * rope.fib_splay[j, 0] * (0.5 + 0.5 * np.sin(fs / rope.R * 0.45 + 2.4 * j))
        if rope.fib_frayloop is not None and rope.fib_frayloop[j, 2] > 0:
            c, hw, h = rope.fib_frayloop[j]
            rho = rho + fray * h * bump((fs - c) / hw)
        phi = rope.fib_phi[j] - 2 * np.pi * fph + br / rope.R * rope.fib_splay[j, 1] * 2 * np.pi
        rad = rp * rho * (1 - 0.4 * r[:, 13]) + br * rope.fib_splay[j, 0]
        if rope.fib_crimp is not None:
            ca, cl, c1, c2 = rope.fib_crimp[j]
            phi = phi + ca / np.maximum(rad, 1e-9) * np.sin(2 * np.pi * fs / cl + c1)
            rad = rad + 0.6 * ca * np.sin(2 * np.pi * fs / (0.77 * cl) + c2)
        p = P + rad[:, None] * (np.cos(phi)[:, None] * o + np.sin(phi)[:, None] * w)
        pts.append(p)
        counts.append(len(fs))
        tip = np.clip((np.abs(fs - rope.fib_break[j])) / (0.6 * rope.R), 0, 1)  # a broken fibre thins to its end
        radii.append(rope.fib_radius[j] * (1 - 0.65 * pose.broken * (1 - tip)) * ones(len(fs)))
    fibre_pts = np.vstack(pts)
    # fuzz: roots on the ply's surface, a shape in the root's frame
    idx = topo["fuzz"]
    P_ = rope.points_per_fuzz
    fz_pts = np.empty((len(idx), P_, 3))
    fz_r = np.empty((len(idx), P_))
    u = np.linspace(0, 1, P_)
    for k in range(3):
        sel = idx[rope.fz_ply[idx] == k]
        if not len(sel):
            continue
        at = np.flatnonzero(rope.fz_ply[idx] == k)
        r = interp_rows(rope.fz_s[sel], s, rows[k])
        P, o, w, rp, fph = r[:, 0:3], r[:, 3:6], r[:, 6:9], r[:, 9], r[:, 11]
        fray = np.interp(rope.fz_s[sel], s, pose.fray)
        phi = rope.fz_phi[sel] - 2 * np.pi * fph
        n_ = np.cos(phi)[:, None] * o + np.sin(phi)[:, None] * w
        tdir = _tangent_rows(r)
        tdir = tdir - n_ * np.sum(tdir * n_, axis=1, keepdims=True)
        tdir /= np.maximum(np.linalg.norm(tdir, axis=1, keepdims=True), 1e-12)
        side = np.cross(tdir, n_)
        is_fray = rope.fz_fray[sel]
        lift = rope.fz_lift[sel] + (np.radians(62) - rope.fz_lift[sel]) * fray * np.where(is_fray > 0, 1.0, 0.7) + pose.lift
        grow = np.where(is_fray > 0, np.clip(fray * 2.5, 0, 1), 1.0)  # fray fibres come out of the ply as it loosens
        L = rope.fz_len[sel] * (1 + 0.5 * fray * is_fray) * np.maximum(grow, 1e-3)
        root = P + (rp * 0.9)[:, None] * n_
        a = (u[None] * np.cos(lift)[:, None]) * L[:, None] * rope.fz_dir[sel][:, None]
        h = (u[None] * np.sin(lift)[:, None] + rope.fz_curl[sel, 0][:, None] * u[None] ** 2 * 0.35) * L[:, None]
        h = h + (rp * 0.12)[:, None] * u[None]  # clear the surface it grows from
        c = rope.fz_curl[sel, 1][:, None] * u[None] ** 2 * L[:, None] * 0.35
        if rope.fz_kink is not None:  # a fibre is never straight: a kink or two along it, round and out
            kk = rope.fz_kink[sel]
            h = h + (kk[:, 0:1] * L[:, None]) * u[None] * np.sin(2 * np.pi * kk[:, 1:2] * u[None] + kk[:, 2:3])
            c = c + (kk[:, 0:1] * L[:, None]) * u[None] * np.sin(2 * np.pi * kk[:, 1:2] * 1.3 * u[None] + kk[:, 3:4])
        fz_pts[at] = root[:, None] + a[..., None] * tdir[:, None] + h[..., None] * n_[:, None] + c[..., None] * side[:, None]
        fz_r[at] = (rope.fz_radius[sel] * np.sqrt(grow))[:, None] * (1 - 0.7 * u[None])
    return RopeGeometry(cores, fibre_pts, np.array(counts), np.concatenate(radii), fz_pts.reshape(-1, 3),
                        np.full(len(idx), P_), fz_r.reshape(-1))


def _tangent_rows(r: np.ndarray) -> np.ndarray:
    """The ply's direction at interpolated rows: round x outward (the rows' frame is right-handed: w = t x o)."""
    o, w = r[:, 3:6], r[:, 6:9]
    return np.cross(o, w)


# ----------------------------------------------------------------------------------------- the rope in Blender

def fibre_material(name: str = "fibre_bone", *, color=None, sheen: float = 0.35, roughness: float = 0.36,
                   translucency: float = 0.25, tone_attr: str | None = "tone", core: bool = False):
    """The macro thread's fibre: bone (THREAD_LOOK's albedo, the palette's bone in linear light), a soft dielectric
    (roughness along the fibre 0.42-0.46, specular F0 0.032 at IOR 1.5) with a fabric sheen that lifts at grazing angles,
    mixed with a little diffuse translucency so thin fibres glow when the rim light is behind them. `tone_attr` scales
    the colour by a per-curve attribute (fibre-to-fibre variation). `core`: the shadowed inside of a ply, darker, no
    translucency."""
    import bpy

    from . import materials

    base = color or materials.linear("bone")
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    col = (*[c * (0.4 if core else 1.0) for c in base], 1.0)  # a core is inner fibre in the plies' shade
    bsdf.inputs["Base Color"].default_value = col
    bsdf.inputs["Roughness"].default_value = roughness + (0.12 if core else 0.0)
    bsdf.inputs["IOR"].default_value = 1.5
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    bsdf.inputs["Sheen Weight"].default_value = sheen
    bsdf.inputs["Sheen Roughness"].default_value = 0.35
    bsdf.inputs["Sheen Tint"].default_value = (1.0, 1.0, 1.0, 1.0)
    color_out = None
    if tone_attr and not core:
        attr = nt.nodes.new("ShaderNodeAttribute")
        attr.attribute_type = "GEOMETRY"
        attr.attribute_name = tone_attr
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        mul.inputs["A"].default_value = col
        nt.links.new(attr.outputs["Fac"], mul.inputs["B"])
        color_out = mul.outputs["Result"]
        nt.links.new(color_out, bsdf.inputs["Base Color"])
    if translucency > 0 and not core:
        tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
        tr.inputs["Color"].default_value = col
        if color_out is not None:
            nt.links.new(color_out, tr.inputs["Color"])
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs["Fac"].default_value = translucency
        nt.links.new(bsdf.outputs["BSDF"], mix.inputs[1])
        nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    else:
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _pass_through():
    """A Geometry Nodes group that hands its geometry straight back."""
    import bpy

    ng = bpy.data.node_groups.get("motion_pass_through")
    if ng is None:
        ng = bpy.data.node_groups.new("motion_pass_through", "GeometryNodeTree")
        ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        gi, go = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
        go.location = (300, 0)
        ng.links.new(gi.outputs[0], go.inputs[0])
    return ng


def deform_blur(ob) -> None:
    """Let Cycles motion-blur the points a frame handler moves on `ob`.

    Cycles exports an object's points at each motion-blur step only when Blender reports the object as deform-modified;
    for any other object it copies the frame's own positions into every step, so handler-posed geometry renders sharp
    while its camera blurs (blender/check_deform.py finds such objects). A modifier that changes nothing is enough: on
    a mesh, a Displace whose offset is (1 - mid level) x strength = 0 (a Displace of strength 0 counts as disabled, so
    it would not do); on hair curves, which take only Geometry Nodes modifiers, a group that passes its geometry
    straight through."""
    if ob.type == "MESH":
        m = ob.modifiers.new("motion", "DISPLACE")
        m.direction, m.strength, m.mid_level = "X", 1.0, 1.0  # offsets along x by (1 - 1) x 1: no normals needed
    else:
        m = ob.modifiers.new("motion", "NODES")
        m.node_group = _pass_through()


def _new_curves(name: str, counts, radii_per_curve_tone, material, coll, parent):
    """Hair curves whose points a frame handler moves (`_set_curves`), so they carry the `deform_blur` modifier."""
    import bpy

    hc = bpy.data.hair_curves.new(name)
    hc.add_curves([int(c) for c in counts])
    if hc.attributes.get("radius") is None:
        hc.attributes.new("radius", "FLOAT", "POINT")
    tone = hc.attributes.new("tone", "FLOAT", "CURVE")
    tone.data.foreach_set("value", np.asarray(radii_per_curve_tone, np.float32).tolist())
    if material is not None:
        hc.materials.append(material)
    ob = bpy.data.objects.new(name, hc)
    ob.parent = parent
    coll.objects.link(ob)
    deform_blur(ob)
    return ob


def _set_curves(ob, pts: np.ndarray, radii: np.ndarray) -> None:
    hc = ob.data
    hc.attributes["position"].data.foreach_set("vector", np.asarray(pts, np.float32).ravel())
    hc.attributes["radius"].data.foreach_set("value", np.asarray(radii, np.float32).ravel())
    hc.update_tag()


def _tube_faces(rings: int, seg: int) -> list:
    f = []
    for i in range(rings - 1):
        a, b = i * seg, (i + 1) * seg
        for j in range(seg):
            j1 = (j + 1) % seg
            f.append((a + j, a + j1, b + j1, b + j))
    return f


class MacroRope:
    """A FibreRope in Blender: per half (left, right), three core tubes (meshes, smooth-shaded), the surface fibres
    and the fuzz (hair curves), all under one empty. Topology is fixed at construction; `update(poses)` moves every
    point, so a frame handler can pose it at each motion-blur step, and each object carries the no-op `deform_blur`
    modifier, so Cycles exports every step and blurs the motion."""

    def __init__(self, rope: FibreRope, *, name: str = "rope", fibre_mat=None, core_mat=None, fuzz_mat=None,
                 collection=None, ring: int = 12):
        import bpy

        self.rope, self.ring = rope, ring
        coll = collection or bpy.context.scene.collection
        self.root = bpy.data.objects.new(name, None)
        coll.objects.link(self.root)
        self.topo = {side: half_topology(rope, side) for side in ("left", "right")}
        self.cores, self.fibres, self.fuzz = {}, {}, {}
        for side, topo in self.topo.items():
            obs = []
            for k in range(3):
                n = len(topo["cores"][k])
                me = bpy.data.meshes.new(f"{name}.{side}.core{k}")
                me.from_pydata(np.zeros((n * ring, 3)).tolist(), [], _tube_faces(n, ring))
                me.shade_smooth()
                if core_mat is not None:
                    me.materials.append(core_mat)
                ob = bpy.data.objects.new(me.name, me)
                ob.parent = self.root
                coll.objects.link(ob)
                deform_blur(ob)
                obs.append(ob)
            self.cores[side] = obs
            fib = np.array([len(fs) for fs in topo["fibres"]])
            self.fibres[side] = _new_curves(f"{name}.{side}.fibres", fib, rope.fib_tone, fibre_mat, coll, self.root)
            fz = topo["fuzz"]
            self.fuzz[side] = _new_curves(f"{name}.{side}.fuzz", np.full(len(fz), rope.points_per_fuzz),
                                          rope.fz_tone[fz], fuzz_mat or fibre_mat, coll, self.root)

    def objects(self) -> list:
        return [*self.cores["left"], *self.cores["right"], *self.fibres.values(), *self.fuzz.values()]

    def update(self, poses: dict, *, fray_centre: float, fray_amount: float) -> dict:
        """Pose both halves (poses: {'left': RopePose, 'right': RopePose}). Returns their RopeGeometry."""
        out = {}
        for side, pose in poses.items():
            g = rope_geometry(self.rope, pose, self.topo[side], fray_centre=fray_centre, fray_amount=fray_amount,
                              ring=self.ring)
            for k, ob in enumerate(self.cores[side]):
                me = ob.data
                me.vertices.foreach_set("co", g.cores[k].astype(np.float32).ravel())
                me.update()
            _set_curves(self.fibres[side], g.fibre_pts, g.fibre_radii)
            _set_curves(self.fuzz[side], g.fuzz_pts, g.fuzz_radii)
            out[side] = g
        return out


# ------------------------------------------------------------------------------------------------ the diff thread
#
# The engine's DIFF_THREAD (app/src/engine/thread3d.ts), from the file it reads, data/look/thread.json, so the two
# renderers' diff threads match for intercuts (B03 re-form, B05 loom, B08 braid): THREAD_LOOK's bone 3-ply at a 14
# degree lay, with the blood and moss strands laid in its grooves, slimmed, and dyed near ink so their colour is the
# light of their cores. That light rests dim and lights on meaning (the C4a verdict (b)): moss when something is
# committed or added, blood when something is struck or removed. The numbers are the engine's: a glow level is an
# emission strength (Task 6 report §4), with the core's colour at its brightest channel 1.
#
# The geometry and the look's numbers are numpy only (tested under the tools project); `diff_thread` builds the curves
# and materials in Blender.

LOOK_FILE = Path(__file__).resolve().parents[2] / "data" / "look" / "thread.json"


def _diff_thread() -> dict:
    d = json.loads(LOOK_FILE.read_text())["diffThread"]
    return {"lay_deg": d["layDeg"], "strand_dye": d["strandDye"], "strand_scale": d["strandScale"], "glow": d["glow"],
            "rest": d["rest"], "flare_lead": d["flare"]["lead"], "flare_decay": d["flare"]["decay"]}


# lay_deg: the plies' lay against the axis; strand_dye: the strands' albedo as a multiple of the dyed colour
# (strand_albedo); strand_scale: their radius as a multiple of LOOK['worm_radius']; glow and rest: the strands' emission
# strength lit on meaning and at rest; flare_lead and flare_decay: strand_flare's envelope (s)
DIFF_THREAD = _diff_thread()


def diff_twist(radius: float, preset: dict = DIFF_THREAD) -> float:
    """The diff thread's ply turns per unit length: its lay at the bone plies' offset (the engine's layDeg)."""
    return lay_turns(preset["lay_deg"], LOOK["ply_offset"] * radius)


def diff_tubes(strand_scale: float | None = None) -> list[dict]:
    """The diff thread's cross-section in thread radii, as the engine lays it out: the bone 3-ply (radius 0.5 on a circle
    of 0.5, at 0, 1/3 and 2/3 of a turn), then the blood and the moss strand, each in a groove touching the plies either
    side, the blood at half a turn and the moss at a sixth, so along the thread the `-` passes each point a third of a
    turn before the `+`. Each tube: {"color", "r", "d" (offset from the axis), "phase" (turns)}."""
    s = DIFF_THREAD["strand_scale"] if strand_scale is None else strand_scale
    r, d, rw = LOOK["ply_radius"], LOOK["ply_offset"], LOOK["worm_radius"] * s
    D = d * math.cos(math.pi / 3) + math.sqrt((r + rw) ** 2 - (d * math.sin(math.pi / 3)) ** 2)
    bone = [{"color": "bone", "r": r, "d": d, "phase": k / 3} for k in range(3)]
    return bone + [{"color": c, "r": rw, "d": D, "phase": 0.5 - j / 3} for j, c in enumerate(("blood", "moss"))]


def diff_thread_paths(points, radius: float, preset: dict = DIFF_THREAD, *, up=(0.0, 0.0, 1.0),
                      samples_per_turn: int = 24) -> list:
    """Each tube's centreline through `points` (scene units), placed as the engine's shader places it: round the
    centreline (centripetal Catmull-Rom) in a rotation-minimising frame whose normal starts from `up`, at the tube's
    offset and phase plus the lay's turns over the arc length. [(tube (diff_tubes), points (m, 3), tube radius)]."""
    twist = diff_twist(radius, preset)
    c = centreline(points, min(1 / (abs(twist) * samples_per_turn), radius * 2))
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
    t0 = (c[1] - c[0]) / np.linalg.norm(c[1] - c[0])
    n0 = np.asarray(up, float)
    if abs(float(t0 @ n0)) > 0.99:  # a thread that starts along `up`: any other start square to it
        n0 = np.array([0.0, 1.0, 0.0]) if abs(t0[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    _, N, B = rmf(c, n0)
    out = []
    for tube in diff_tubes(preset["strand_scale"]):
        th = (2 * np.pi * (twist * s + tube["phase"]))[:, None]
        out.append((tube, c + tube["d"] * radius * (np.cos(th) * N + np.sin(th) * B), tube["r"] * radius))
    return out


def strand_albedo(color: str, strand_dye: float | None = None) -> tuple[float, float, float]:
    """A strand's fibre colour (linear): the palette colour LOOK['dye'] of the way to its dim shade, as the engine dyes
    it, times `strand_dye` (DIFF_THREAD's 0.03: near ink, so the core's light carries the colour)."""
    from . import materials

    k = DIFF_THREAD["strand_dye"] if strand_dye is None else strand_dye
    a, b = materials.linear(color), materials.linear(color + "Dim")
    return tuple((x + (y - x) * LOOK["dye"]) * k for x, y in zip(a, b))  # type: ignore[return-value]


def glow_color(color: str) -> tuple[float, float, float]:
    """The colour of a strand's core: the palette colour in linear light with its brightest channel at 1 (look.ts
    glow(color, 1)). At an emission strength of the glow level it is the engine's glow(color, level)."""
    from . import materials

    c = materials.linear(color)
    return tuple(x / max(c) for x in c)  # type: ignore[return-value]


def glow_profile(n_dot_v):
    """The core across a strand, 1 where it faces the camera: a sharp filament over a soft scattered base,
    (1 - soft)(N.V)^28 + soft (N.V)^3 (THREAD_LOOK glowFalloff, glowSoft)."""
    a, b = LOOK["glow_falloff"]
    k = LOOK["glow_soft"]
    x = np.clip(np.asarray(n_dot_v, float), 0.0, 1.0)
    return (1 - k) * x ** a + k * x ** b


def strand_flare(t: float, at, lead: float | None = None, decay: float | None = None) -> float:
    """Flare on meaning, 0..1, the engine's strandFlare: rising over `lead` s into the onset `at` (seconds; or a list of
    onsets, the brightest wins), peaking on it, and dying away as (1 - age/decay)^2 to exactly 0 `decay` s after it."""
    lead = DIFF_THREAD["flare_lead"] if lead is None else lead
    decay = DIFF_THREAD["flare_decay"] if decay is None else decay
    k = 0.0
    for a in ([at] if isinstance(at, (int, float)) else at):
        if t < a:
            if lead > 0:
                x = min(max((t - (a - lead)) / lead, 0.0), 1.0)
                k = max(k, x * x * (3 - 2 * x))
        elif t < a + decay:
            k = max(k, (1 - (t - a) / decay) ** 2)
    return k


def strand_glow(t: float, at, rest: float | None = None, lit: float | None = None, lead: float | None = None,
                decay: float | None = None) -> float:
    """A strand's glow level (emission strength) at t, the engine's strandGlow: `rest` (DIFF_THREAD's) lit toward `lit`
    (DIFF_THREAD's glow) by strand_flare on its onsets."""
    rest = DIFF_THREAD["rest"] if rest is None else rest
    lit = DIFF_THREAD["glow"] if lit is None else lit
    k = strand_flare(t, at, lead, decay)
    return rest * (1 - k) + lit * k


def _fibre_surface(bsdf, base) -> None:
    """THREAD_LOOK's fibre surface on a Principled BSDF in colour `base` (linear): Blender's Specular IOR Level 0.5 is
    the IOR's own F0, and the engine's specular scales F0 (0.8: 0.032 at IOR 1.5); the sheen tinted 15% toward white."""
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Roughness"].default_value = LOOK["roughness"]
    bsdf.inputs["IOR"].default_value = LOOK["ior"]
    bsdf.inputs["Specular IOR Level"].default_value = 0.5 * LOOK["specular"]
    bsdf.inputs["Sheen Weight"].default_value = LOOK["sheen"]
    bsdf.inputs["Sheen Roughness"].default_value = LOOK["sheen_roughness"]
    bsdf.inputs["Sheen Tint"].default_value = (*[c + (1 - c) * 0.15 for c in base], 1.0)


def ply_material(name: str = "diff_bone"):
    """The diff thread's bone plies: bone with THREAD_LOOK's fibre surface. No anisotropy (a bevelled curve's tangent
    runs round the tube, not along its fibres); the macro rope has real fibres."""
    from . import materials

    mat, bsdf = materials._principled(name)
    _fibre_surface(bsdf, materials.linear("bone"))
    return mat


def strand_material(color: str, *, preset: dict = DIFF_THREAD, name: str | None = None, heat_attr: str | None = None):
    """A blood or moss strand: its fibre dyed near ink (strand_albedo) with a glowing core, an emission of
    glow_color(color) at strength glow x glow_profile(N.V), where N.V = 1 - Layer Weight's Facing at blend 0.5. The glow
    level is the Value node named 'glow' (glow_socket), starting at preset['rest']: set or key it (DiffThread.set_glow).
    `heat_attr` names a geometry attribute added to that level where the strand has it (StrandTube's `heat`: a tip that
    burns hotter as it lays in); without it the material is exactly as before."""
    from . import materials

    mat, bsdf = materials._principled(name or f"diff_{color}")
    _fibre_surface(bsdf, strand_albedo(color, preset["strand_dye"]))
    bsdf.inputs["Emission Color"].default_value = (*glow_color(color), 1.0)
    nt = mat.node_tree

    def math_node(op, a, b, c=None):
        m = nt.nodes.new("ShaderNodeMath")
        m.operation = op
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = float(v)
            else:
                nt.links.new(v, m.inputs[i])
        return m.outputs[0]

    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    ndv = math_node("SUBTRACT", 1.0, lw.outputs["Facing"])
    hi, lo = LOOK["glow_falloff"]
    soft = LOOK["glow_soft"]
    profile = math_node("MULTIPLY_ADD", math_node("POWER", ndv, hi), 1.0 - soft, math_node("MULTIPLY", math_node("POWER", ndv, lo), soft))
    glow = nt.nodes.new("ShaderNodeValue")
    glow.name = glow.label = "glow"
    glow.outputs[0].default_value = preset["rest"]
    level = glow.outputs[0]
    if heat_attr:
        attr = nt.nodes.new("ShaderNodeAttribute")
        attr.attribute_type = "GEOMETRY"
        attr.attribute_name = heat_attr
        level = math_node("ADD", level, attr.outputs["Fac"])
    nt.links.new(math_node("MULTIPLY", profile, level), bsdf.inputs["Emission Strength"])
    return mat


def glow_socket(material):
    """A strand material's glow level: the output of its 'glow' Value node (set default_value, or keyframe it)."""
    return material.node_tree.nodes["glow"].outputs[0]


@dataclass
class DiffThread:
    """The diff thread in Blender (`diff_thread`): its five tube curves under one empty (the three bone plies, then the
    blood and the moss strand) and the strands' materials."""
    root: object
    radius: float
    preset: dict
    tubes: list = field(default_factory=list)
    strands: dict = field(default_factory=dict)  # "blood", "moss": material

    def set_glow(self, blood: float | None = None, moss: float | None = None, *, frame: int | None = None) -> None:
        """Each strand's glow level (emission strength; strand_glow gives it at a time), the other left as it is; with
        `frame`, keyed there too, so a render plays it back (keys interpolate linearly between frames)."""
        for c, level in (("blood", blood), ("moss", moss)):
            if level is None:
                continue
            sock = glow_socket(self.strands[c])
            sock.default_value = max(0.0, float(level))
            if frame is not None:
                sock.keyframe_insert("default_value", frame=frame)
                for fc in _fcurves(self.strands[c].node_tree.animation_data.action):
                    for k in fc.keyframe_points:  # new keys are Bezier: motion-blur steps between frames go straight
                        k.interpolation = "LINEAR"


def _fcurves(action) -> list:
    """An action's F-curves (Blender 5 keeps them in layers, strips and channel bags)."""
    out = []
    if getattr(action, "layers", None):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    out.extend(bag.fcurves)
    elif hasattr(action, "fcurves"):
        out.extend(action.fcurves)
    return out


def diff_thread(points, radius: float, *, preset: dict = DIFF_THREAD, name: str = "diff_thread", collection=None,
                up=(0.0, 0.0, 1.0), bevel_resolution: int = 4, bone_material=None) -> DiffThread:
    """Build the diff thread through `points` (scene units) of radius `radius` from `preset` (DIFF_THREAD): the bone
    plies and the two strands as round bevelled curves (diff_thread_paths), parented to an empty named `name`, the
    strands resting at the preset's rest level until set_glow lights one. The curves are static: a shot that moves the
    thread rebuilds them, or poses its own geometry with `deform_blur` on what a handler moves."""
    import bpy

    coll = collection or bpy.context.scene.collection
    root = bpy.data.objects.new(name, None)
    root.empty_display_size = radius * 4
    coll.objects.link(root)
    th = DiffThread(root=root, radius=radius, preset=dict(preset))
    th.strands = {c: strand_material(c, preset=preset, name=f"{name}.{c}") for c in ("blood", "moss")}
    bone = bone_material or ply_material(f"{name}.bone")
    for k, (tube, P, r) in enumerate(diff_thread_paths(points, radius, preset, up=up)):
        cu = bpy.data.curves.new(f"{name}.{k}.{tube['color']}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_mode = "ROUND"
        cu.bevel_depth = r
        cu.bevel_resolution = bevel_resolution
        cu.use_fill_caps = True
        sp = cu.splines.new("POLY")
        sp.use_smooth = True
        sp.points.add(len(P) - 1)
        sp.points.foreach_set("co", np.column_stack([P, np.ones(len(P))]).ravel().tolist())
        cu.materials.append(bone if tube["color"] == "bone" else th.strands[tube["color"]])
        ob = bpy.data.objects.new(cu.name, cu)
        ob.parent = root
        coll.objects.link(ob)
        th.tubes.append(ob)
    return th


# ------------------------------------------------------------------------------------------ strands in the macro rope
#
# The diff thread at macro (B03, the re-form): DIFF_THREAD's blood and moss strands laid in the grooves of the fibre
# rope (FibreRope), in any pose. A groove lies between two plies, a sixth of a turn from each; a strand in groove g
# (turns from ply 0: blood 1/2, moss 1/6, as diff_tubes) winds with the plies' phase, the pose's unravel and the fray's
# untwist included, at diff_tubes' strand offset, opened with the plies' fray and splay. The strands are smooth tubes
# (StrandTube): at macro their glowing core (strand_material) is the detail, and the plies round them are fibre.

def groove_path(rope: FibreRope, pose: RopePose, groove: float, *, depth=None, fray_centre: float, fray_amount: float,
                fray_span: float | None = None):
    """The centreline of a strand in groove `groove` (turns from ply 0) of `rope` in `pose`, at the pose's samples:
    (points (m, 3), unit outward directions (m, 3)). `depth` is its offset from the axis in R, a number or one per sample
    (a strand rising out of the axis); by default diff_tubes' strand offset (0.70 R, touching the plies either side).
    The fray's untwist is the one rope_geometry gives the plies (`fray_centre`, `fray_amount`, `fray_span`)."""
    span = (fray_span or LOOK["fray_span"]) * rope.R
    s, X = pose.s, pose.X
    T = np.gradient(X, s, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    N = pose.N - T * np.sum(pose.N * T, axis=1, keepdims=True)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    B = np.cross(T, N)
    phase = rope.twist * untwisted(s, fray_centre, span, fray_amount, rope.fray_untwist) + pose.unravel
    th = 2 * np.pi * (groove + phase)
    out = np.cos(th)[:, None] * N + np.sin(th)[:, None] * B
    D = diff_tubes()[3]["d"] if depth is None else np.asarray(depth, float)
    # the plies either side of the groove stand out with the fray, and with their own splay at a broken end
    k1, k2 = int(round(3 * (groove - 1 / 6))) % 3, int(round(3 * (groove + 1 / 6))) % 3
    d = D * rope.R * (1 + rope.fray_separation * pose.fray + 0.5 * (pose.splay[k1] + pose.splay[k2]))
    return X + np.broadcast_to(d, s.shape)[:, None] * out, out


def tube_rings(P, radius, seg: int = 12, up=None) -> np.ndarray:
    """The vertices of a round tube along a path P (m, 3): (m, seg, 3), ring i of radius radius[i] (a number, or one per
    ring) square to the path, starting from `up` (one direction per ring, or one for all; default +z) made square to the
    path's tangent."""
    P = np.asarray(P, float)
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    ref = np.broadcast_to(np.asarray((0.0, 0.0, 1.0) if up is None else up, float), P.shape)
    U = ref - T * np.sum(ref * T, axis=1, keepdims=True)
    U /= np.maximum(np.linalg.norm(U, axis=1, keepdims=True), 1e-12)
    V = np.cross(T, U)
    a = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    r = np.broadcast_to(np.asarray(radius, float), (len(P),))[:, None, None]
    return P[:, None] + r * (np.cos(a)[None, :, None] * U[:, None] + np.sin(a)[None, :, None] * V[:, None])


class StrandTube:
    """A strand as a smooth mesh tube whose path, radius and heat a frame handler sets every (sub-)frame (`update`):
    `rings` cross-sections of `seg` vertices (tube_rings), a ring at radius 0 gone (so a strand can grow along its
    groove out of nothing), and a per-vertex float attribute `heat` that its material adds to its glow level
    (strand_material(heat_attr="heat")). It carries `deform_blur`, so Cycles motion-blurs what the handler moves."""

    def __init__(self, name: str, rings: int, material=None, *, seg: int = 12, collection=None, parent=None):
        import bpy

        self.rings, self.seg = rings, seg
        coll = collection or bpy.context.scene.collection
        me = bpy.data.meshes.new(name)
        me.from_pydata(np.zeros((rings * seg, 3)).tolist(), [], _tube_faces(rings, seg))
        me.shade_smooth()
        me.attributes.new("heat", "FLOAT", "POINT")
        if material is not None:
            me.materials.append(material)
        self.ob = bpy.data.objects.new(name, me)
        self.ob.parent = parent
        coll.objects.link(self.ob)
        deform_blur(self.ob)

    def update(self, P, radius, heat=None, up=None) -> None:
        me = self.ob.data
        me.vertices.foreach_set("co", tube_rings(P, radius, self.seg, up).astype(np.float32).ravel())
        h = np.zeros(self.rings) if heat is None else np.broadcast_to(np.asarray(heat, float), (self.rings,))
        me.attributes["heat"].data.foreach_set("value", np.repeat(h, self.seg).astype(np.float32))
        me.update()
