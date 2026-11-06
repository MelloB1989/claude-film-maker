"""Per-vertex cloth maps from a garment's rest pose (cm, the reference pose of the MetaHuman body skeleton).

Chaos cloth reads per-particle weight maps: MaxDistance (how far a particle may leave its skinned position, cm),
BackstopDistance / BackstopRadius (a sphere behind the skin it may not enter), and the anim-drive / stiffness maps.
A painted max distance is what makes a garment cloth and not armour: 0 where it is sewn to the body's motion (collar,
shoulder seam, waistband), a few cm where it hangs (hem, sleeve ends). This module computes them from geometry, so a
garment is "painted" by rule, reproducibly, without the Paint tool:

    segs  = bone_segments(heads, parents)            # bones of the reference pose
    zones = assign(verts, segs, preset)              # each vertex's zone and bone
    maps  = paint(verts, zones, segs, preset, colours=None)   # {"max_distance": [...], "backstop_*": [...], ...}

`colours` are the fit's vertex colours (agent-02's garment.fit: R = ease to the body / 5 cm, G = pinned, 0..1):
pinned vertices get 0, and the max distance never exceeds the ease plus the collision thickness, so the cloth cannot
fall through where the physics asset's capsules are coarser than the body.
"""
from __future__ import annotations

import math

EASE_FULL_CM = 5.0          # R = 1.0 in the fit's colours (garment.fit encodes ease cm / 5, clamped)
PIN_LEVEL = 0.5             # G above this is pinned
USE_EASE = False            # R (ease) arrives sRGB-decoded through UE's FBX colours (byte 77 -> 0.37 cm): G only (round 5)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return math.sqrt(_dot(a, a))


def bone_segments(heads: dict, parents: dict) -> dict:
    """{bone: (head, tail)} from bone head positions and parent names: a bone runs from its head to the mean of its
    children's heads (a leaf continues its parent's direction for half its parent's length)."""
    kids: dict = {}
    for b, p in parents.items():
        if p:
            kids.setdefault(p, []).append(b)
    segs = {}
    for b, h in heads.items():
        ch = [heads[c] for c in kids.get(b, []) if c in heads]
        if ch:
            tail = tuple(sum(c[i] for c in ch) / len(ch) for i in range(3))
        elif parents.get(b) in heads:
            d = _sub(h, heads[parents[b]])
            tail = (h[0] + d[0] * 0.5, h[1] + d[1] * 0.5, h[2] + d[2] * 0.5)
        else:
            tail = tuple(h)
        segs[b] = (tuple(h), tail)
    return segs


def _seg_dist(p, seg):
    a, b = seg
    ab = _sub(b, a)
    L2 = _dot(ab, ab)
    t = 0.0 if L2 <= 1e-9 else max(0.0, min(1.0, _dot(_sub(p, a), ab) / L2))
    q = (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)
    return _len(_sub(p, q)), t


def assign(verts: list, segs: dict, preset: dict) -> list:
    """Each vertex's (zone name, nearest bone): the nearest bone segment among the bones the preset's zones name
    (bones the skeleton lacks are skipped). Raises ValueError when no zone bone is in the skeleton."""
    owner = {}
    for z in preset["zones"]:
        for b in z["bones"]:
            if b in segs and b not in owner:
                owner[b] = z["name"]
    if not owner:
        raise ValueError("none of the preset's zone bones are in the skeleton: is it the MetaHuman body skeleton?")
    out = []
    bones = list(owner)
    for v in verts:
        best, bb = None, None
        for b in bones:
            d, _ = _seg_dist(v, segs[b])
            if best is None or d < best:
                best, bb = d, b
        out.append((owner[bb], bb))
    return out


def _chain_root(bone: str, zone_bones: set, parents: dict) -> str:
    b = bone
    while parents.get(b) in zone_bones:
        b = parents[b]
    return b


def ramp_t(verts: list, zones: list, segs: dict, preset: dict, parents: dict) -> list:
    """0..1 per vertex: 0 at its zone's anchor end, 1 at its free end. `height` ramps down from the zone's highest
    vertex to its lowest (a torso toward the hem); `along` out along the limb from the zone's root bone's head (a
    sleeve from the shoulder); `fixed` is 0."""
    t = [0.0] * len(verts)
    by_zone = {z["name"]: z for z in preset["zones"]}
    groups: dict = {}
    for i, (zn, b) in enumerate(zones):
        z = by_zone[zn]
        if z["ramp"] == "height":
            groups.setdefault((zn, None), []).append(i)
        elif z["ramp"] == "along":
            root = _chain_root(b, set(z["bones"]), parents)
            groups.setdefault((zn, root), []).append(i)
    for (zn, root), idx in groups.items():
        z = by_zone[zn]
        if z["ramp"] == "height":
            zs = [verts[i][2] for i in idx]
            top, bot = max(zs), min(zs)
            span = max(top - bot, 1e-6)
            for i in idx:
                t[i] = (top - verts[i][2]) / span
        else:
            a, b = segs[root]
            d = _sub(b, a)
            n = _len(d) or 1.0
            u = (d[0] / n, d[1] / n, d[2] / n)
            proj = {i: max(0.0, _dot(_sub(verts[i], a), u)) for i in idx}
            far = max(proj.values()) or 1.0
            for i in idx:
                t[i] = proj[i] / far
    return t


def paint(verts: list, zones: list, segs: dict, preset: dict, parents: dict, colours: list | None = None) -> dict:
    """The cloth's maps per vertex (cm): {"max_distance", "backstop_distance", "backstop_radius", "zone", "pinned",
    "stats": {zone: {"n", "min_cm", "max_cm", "mean_cm"}}}. `colours`: [(r, g, b, a), ...] 0..1 (the fit's), or None.

    Backstop: only where the fit's ease is known; the particle may sink toward the body by at most the ease minus the
    collision thickness (a sphere of radius = the max distance, behind the skin)."""
    by_zone = {z["name"]: z for z in preset["zones"]}
    thick = float(preset["config"].get("collision_thickness", 0.5))
    t = ramp_t(verts, zones, segs, preset, parents)
    md, bd, br, pinned = [], [], [], []
    for i, (zn, _b) in enumerate(zones):
        z = by_zone[zn]
        g = max(0.0, min(1.0, t[i])) ** float(z.get("gamma", 1.0))
        d = z["from_cm"] + (z["to_cm"] - z["from_cm"]) * g
        pin = False
        back_d, back_r = 0.0, 0.0
        if colours is not None and i < len(colours) and colours[i] is not None:
            r, gch = float(colours[i][0]), float(colours[i][1])
            if gch > PIN_LEVEL:
                d, pin = 0.0, True
            elif USE_EASE and r < 0.98:                      # a body is under it (the ease is measured, not "far")
                ease = r * EASE_FULL_CM
                d = min(d, ease + thick)
                back_d = max(0.0, ease - thick)
                back_r = d
        md.append(round(max(0.0, d), 3))
        bd.append(round(back_d, 3))
        br.append(round(back_r, 3))
        pinned.append(pin or d <= 0.0)
    stats = {}
    for zn in by_zone:
        vals = [md[i] for i, (z, _b) in enumerate(zones) if z == zn]
        if vals:
            stats[zn] = {"n": len(vals), "min_cm": min(vals), "max_cm": max(vals),
                         "mean_cm": round(sum(vals) / len(vals), 3)}
    return {"max_distance": md, "backstop_distance": bd, "backstop_radius": br, "zone": [z for z, _ in zones],
            "pinned": pinned, "stats": stats}


def check_maps(maps: dict, preset: dict) -> list:
    """Problems with painted maps, as strings (empty when fine): the whole garment pinned (armour: nothing can move),
    nothing pinned (it slides off), a free zone with no slack, or a max distance beyond the preset's."""
    from .presets import max_cm
    md = maps["max_distance"]
    out = []
    if not md:
        return ["no vertices"]
    if max(md) <= 0.0:
        out.append("every vertex has max distance 0: the garment is skinned, not cloth (armour)")
    if min(md) > 0.0:
        out.append("no vertex is pinned: the garment would slide off the body (pin the collar/waist)")
    for zn in preset.get("free", []):
        s = maps["stats"].get(zn)
        if s and s["max_cm"] < 0.5:
            out.append(f"free zone {zn} has at most {s['max_cm']} cm of slack: it cannot move")
    if max(md) > max_cm(preset) + 1e-6:
        out.append(f"max distance {max(md)} cm is beyond the preset's {max_cm(preset)} cm")
    return out
