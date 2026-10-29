"""A river boat from code for anime shots, and the way it floats: a low flat-bottomed wooden ferry (a square stern,
the bow narrowing and rising to a raked stem, planked sides flaring out), thwarts across it, a seat at the stern, a
mooring ring at the bow and, if asked, a light awning of bamboo slats on four poles. Built round an empty at its
waterline (`root`) that everything hangs from, so a shot moves the whole boat by moving the root: `float_pose` bobs
and rocks it in place, `drift_pose` carries it along a path (pushed off from a jetty, out across the river), and
`animate` keys both.

The boat's own axes: its length along +x (stern at x 0, bow at x `length`), its beam across y, z up from the
waterline. `hull` and the motion (`float_pose`, `drift_pose`, `path_point`) are numpy only and tested without Blender.
"""
from __future__ import annotations

import math

import numpy as np

from . import shapes


def hull_section(f: float, beam: float, depth: float, *, bottom: float = 0.62, flare: float = 1.0, rocker: float = 0.22,
                 sheer: float = 0.32, bow: float = 0.3) -> tuple[float, float, float, float]:
    """The hull's cross-section `f` (0 stern to 1 bow) along it: (bottom half-width, top half-width, bottom z, sheer
    z), z from the waterline. Flat-bottomed (`bottom` of the beam at the floor); toward the bow (its last `bow`) both
    widths narrow to the stem while the bottom rises by `rocker` and the sheer by `sheer`."""
    g = max(0.0, (f - (1.0 - bow)) / bow)                 # 0 behind the bow's run, 1 at the stem
    s = max(0.0, (0.06 - f) / 0.06)                       # the stern's slight lift
    narrow = math.sqrt(max(0.0, 1.0 - g ** 1.6))
    top = beam / 2 * (0.93 + 0.07 * math.sin(math.pi * min(1.0, f / (1.0 - bow)))) * max(narrow, 0.04)
    bot = beam / 2 * bottom * max(narrow, 0.0) ** 1.3 * (1.0 - 0.15 * s)
    zb = -0.6 * depth + rocker * g ** 1.8 + 0.04 * s
    zs = 0.4 * depth + sheer * g ** 2.2 + 0.05 * s
    return bot, top * flare, zb, zs


def hull(length: float = 5.4, beam: float = 1.3, depth: float = 0.45, *, n: int = 24, thick: float = 0.035,
         **section) -> tuple[np.ndarray, list]:
    """(verts, faces) of the hull as a shell of planking `thick` thick: each section a U (outer side, bottom, other
    side, then the inner faces back), lofted from stern to bow and closed at both ends."""
    verts, faces = [], []
    fs = np.linspace(0.0, 1.0, n)
    for f in fs:
        b, w, zb, zs = hull_section(float(f), beam, depth, **section)
        x = float(f) * length
        t = thick * (1.0 if f < 0.98 else 0.3)
        bi, wi = max(b - t, 0.0), max(w - t, 0.0)
        verts += [(x, -w, zs), (x, -b, zb), (x, b, zb), (x, w, zs),
                  (x, wi, zs), (x, bi, zb + t), (x, -bi, zb + t), (x, -wi, zs)]
    k = 8
    for i in range(n - 1):
        a, c = i * k, (i + 1) * k
        for j in range(k):
            faces.append((a + j, a + (j + 1) % k, c + (j + 1) % k, c + j))
    faces.append(tuple(range(k - 1, -1, -1)))              # the transom
    faces.append(tuple((n - 1) * k + j for j in range(k)))  # the stem
    return np.array(verts, float), faces


def float_pose(t: float, *, heave: float = 0.018, roll: float = 1.6, pitch: float = 0.7, period: float = 3.4,
               seed: int = 1, calm: float = 1.0) -> tuple[float, float, float]:
    """(dz m, roll rad, pitch rad) of a boat floating at rest at time t s: a slow bob and a rock, each two sines out
    of step so it never repeats a beat; `heave` m and `roll`, `pitch` degrees at most, `calm` scaling them all (0
    still water)."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(0, 2 * math.pi, 6)
    w = 2 * math.pi / period

    def wave(a, b, k):
        return 0.65 * math.sin(w * a * t + p[k]) + 0.35 * math.sin(w * b * t + p[k + 1])

    return (calm * heave * wave(1.0, 2.31, 0), calm * math.radians(roll) * wave(0.83, 1.97, 2),
            calm * math.radians(pitch) * wave(1.13, 2.71, 4))


def path_point(points, u: float) -> tuple[float, float]:
    """The point at `u` (0..1) along a Catmull-Rom curve through `points` [(x, y), ...] (u spread evenly over its
    spans)."""
    P = np.asarray(points, float)
    n = len(P)
    if n == 1:
        return float(P[0, 0]), float(P[0, 1])
    s = min(max(u, 0.0), 1.0) * (n - 1)
    i = min(int(s), n - 2)
    t = s - i
    p1, p2 = P[i], P[i + 1]
    p0 = P[i - 1] if i > 0 else 2 * p1 - p2          # past the ends: the end spans carried straight on
    p3 = P[i + 2] if i + 2 < n else 2 * p2 - p1
    q = 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
    return float(q[0]), float(q[1])


def ease_out(u: float) -> float:
    """A push off: full speed at the start, slowing as it glides (a pole's shove, then the water's drag)."""
    u = min(max(u, 0.0), 1.0)
    return 1.0 - (1.0 - u) ** 2


def drift_pose(t: float, points, t0: float, t1: float, *, ease=None) -> tuple[float, float, float]:
    """(x, y, heading rad) of a boat carried along `points` from time t0 to t1 (held at the ends), `ease` (u -> u;
    default `ease_out`, a push off) timing it; its bow along the path."""
    ease = ease or ease_out
    u = ease((t - t0) / max(t1 - t0, 1e-6))
    x, y = path_point(points, u)
    a, b = path_point(points, max(u - 0.01, 0.0)), path_point(points, min(u + 0.01, 1.0))
    return x, y, math.atan2(b[1] - a[1], b[0] - a[0])


def _empty(name: str, coll, parent, location):
    import bpy

    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.15
    coll.objects.link(e)
    e.parent = parent
    e.location = location
    return e


def river_boat(m: dict, coll, *, length: float = 5.4, beam: float = 1.3, depth: float = 0.45, location=(0.0, 0.0, 0.0),
               heading: float = 0.0, awning: bool = True, prefix: str = "ferry", seed: int = 3) -> dict:
    """The ferry: hull, gunwales, ribs, floorboards, thwarts, the stern seat and a mooring ring at the bow; an
    awning of slats on four bamboo poles over its middle with `awning`. `m`: hull, wood (seat, thwarts, boards),
    rope, bamboo (falling back to hull). Its root at `location` (the waterline under its middle), its bow toward
    `heading` (radians from +x). Returns its root and parts and anchors (empties hanging from
    the root a shot can parent to or read): seat (on the stern seat), stern (where a boatman stands to pole), bow,
    ring (the mooring ring), middle."""
    rng = np.random.default_rng(seed)
    hullm, wood = m["hull"], m.get("wood", m["hull"])
    rope, bamboo = m.get("rope", wood), m.get("bamboo", wood)
    root = _empty(f"{prefix}-root", coll, None, location)
    root.rotation_euler = (0.0, 0.0, heading)
    x0 = -length / 2
    parts = []

    def own(ob, smooth=False):
        ob.parent = root
        if not smooth:
            for p in ob.data.polygons:
                p.use_smooth = False
        parts.append(ob)
        return ob

    v, f = hull(length, beam, depth)
    v[:, 0] += x0
    own(shapes.mesh_object(f"{prefix}-hull", v, f, hullm, coll, smooth=False))
    sec = lambda u: hull_section(u, beam, depth)                       # noqa: E731
    # gunwales: a rail along each side's top edge
    us = np.linspace(0.0, 0.985, 16)
    for s in (-1, 1):
        path = [(x0 + u * length, s * (sec(u)[1] + 0.012), sec(u)[3] + 0.015) for u in us]
        own(shapes.loft(f"{prefix}-gunwale{s}", path, 0.03, 0.022, material=wood, coll=coll, n=6, subsurf=0))
    # ribs inside the hull, and boards laid along the floor
    for k, u in enumerate(np.linspace(0.1, 0.78, 7)):
        b, w, zb, zs = sec(float(u))
        x = x0 + float(u) * length
        path = [(x, -w + 0.04, zs - 0.02), (x, -b + 0.03, zb + 0.05), (x, b - 0.03, zb + 0.05), (x, w - 0.04, zs - 0.02)]
        own(shapes.loft(f"{prefix}-rib{k}", path, 0.022, 0.018, material=wood, coll=coll, n=4, subsurf=0, power=1.0))
    b_mid, _, zb_mid, _ = sec(0.4)
    for k in range(5):
        y = (k - 2) * (b_mid * 2 - 0.12) / 4.6
        own(shapes.box(f"{prefix}-floor{k}", (x0 + 0.45 * length, y, zb_mid + 0.075), (0.72 * length, 0.15, 0.022),
                       material=wood, coll=coll, rot_z=rng.uniform(-0.004, 0.004)))
    # thwarts across, and the stern seat: a broad board with a little step under it
    for k, u in enumerate((0.38, 0.62)):
        b, w, zb, zs = sec(u)
        own(shapes.box(f"{prefix}-thwart{k}", (x0 + u * length, 0.0, zs - 0.07), (0.2, 2 * w - 0.05, 0.04), material=wood,
                       coll=coll))
    us_ = 0.09
    b, w, zb, zs = sec(us_)
    seat_z = zs - 0.05
    own(shapes.box(f"{prefix}-seat", (x0 + us_ * length, 0.0, seat_z), (0.42, 2 * w - 0.05, 0.05), material=wood, coll=coll))
    own(shapes.box(f"{prefix}-seat-post", (x0 + us_ * length, 0.0, (seat_z + zb) / 2), (0.08, 0.08, seat_z - zb), material=wood,
                   coll=coll))
    # a mooring ring of rope on a cleat at the bow
    bx = x0 + 0.95 * length
    bz = sec(0.95)[3]
    own(shapes.box(f"{prefix}-cleat", (bx, 0.0, bz + 0.03), (0.16, 0.06, 0.05), material=wood, coll=coll))
    ang = np.linspace(0, 2 * math.pi, 17)
    ring = [(bx + 0.04 + 0.05 * math.cos(a), 0.0 + 0.05 * math.sin(a) * 0.4, bz + 0.07 + 0.05 * math.sin(a)) for a in ang]
    own(shapes.loft(f"{prefix}-ring", ring, 0.009, material=rope, coll=coll, n=6, subsurf=0, cap=False))
    if awning:
        ax0, ax1 = x0 + 0.3 * length, x0 + 0.72 * length
        top = sec(0.5)[3] + 1.25
        for k, (px, s) in enumerate(((ax0, -1), (ax0, 1), (ax1, -1), (ax1, 1))):
            w = sec((px - x0) / length)[1] - 0.06
            own(shapes.cylinder(f"{prefix}-pole{k}", (px, s * w, sec(0.5)[3] - 0.05), (px, s * w * 0.97, top), 0.022,
                                material=bamboo, coll=coll, n=8))
        w = sec(0.5)[1]
        for s in (-1, 1):
            own(shapes.cylinder(f"{prefix}-beam{s}", (ax0 - 0.12, s * w * 0.97, top), (ax1 + 0.12, s * w * 0.97, top), 0.02,
                                material=bamboo, coll=coll, n=6))
        # slats across, a gentle arch, a few missing and some askew: a worn awning that lets the rain through
        slats = int((ax1 - ax0 + 0.3) / 0.11)
        for k in range(slats):
            if rng.uniform() < 0.12:
                continue
            x = ax0 - 0.15 + k * 0.11 + rng.uniform(-0.015, 0.015)
            arch = [(x, y, top + 0.04 + 0.1 * (1 - (y / (w + 0.12)) ** 2)) for y in np.linspace(-w - 0.12, w + 0.12, 5)]
            own(shapes.loft(f"{prefix}-slat{k}", arch, 0.04, 0.008, material=bamboo, coll=coll, n=4, subsurf=0,
                            up=(1, 0, 0)))
    anchors = {
        "seat": _empty(f"{prefix}-at-seat", coll, root, (x0 + us_ * length, 0.0, seat_z + 0.025)),
        "stern": _empty(f"{prefix}-at-stern", coll, root, (x0 + 0.2 * length, 0.0, zb_mid + 0.09)),
        "middle": _empty(f"{prefix}-at-middle", coll, root, (x0 + 0.5 * length, 0.0, zb_mid + 0.09)),
        "bow": _empty(f"{prefix}-at-bow", coll, root, (x0 + length, 0.0, sec(1.0)[3])),
        "ring": _empty(f"{prefix}-at-ring", coll, root, (bx + 0.04, 0.0, bz + 0.07)),
    }
    return {"root": root, "objects": parts, "anchors": anchors, "length": length, "beam": beam}


def animate(root, frames, fps: float, *, base, f0: int = 0, path=None, push=None, bob: dict | None = None) -> None:
    """Key `root` on every frame of `frames`: floating (`float_pose` with `bob`'s settings) at `base` (x, y, z,
    heading) or, given `path` [(x, y), ...] and `push` (t0, t1 s), carried along it from the first point (`drift_pose`),
    its rock eased in as it gets under way. Time t is (frame - f0) / fps."""
    bx, by, bz, bh = base
    bob = bob or {}
    for f in frames:
        t = (f - f0) / fps
        dz, roll, pitch = float_pose(t, **bob)
        x, y, h = bx, by, bh
        if path is not None and push is not None:
            x, y, h = drift_pose(t, path, *push)
            if t < push[0]:
                h = bh
            elif t < push[0] + 0.6:
                k = (t - push[0]) / 0.6                      # the bow swings round as it gets under way
                h = bh + (((h - bh + math.pi) % (2 * math.pi)) - math.pi) * k * k * (3 - 2 * k)
        root.location = (x, y, bz + dz)
        root.rotation_euler = (roll, pitch, h)
        root.keyframe_insert("location", frame=f)
        root.keyframe_insert("rotation_euler", frame=f)
