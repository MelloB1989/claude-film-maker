"""candle — a cream wax candle in a clear glass tumbler, 8 cm across, 10 cm tall, lit.

Glass: 3 mm wall, rounded rim, a thick base (about 1 cm) with a filleted inner corner and a
shallow recess under it so it stands on a ring. Wax: fills the glass to 2 cm below the rim, a
little meniscus at the glass and a shallow melt pool around the wick. A black wick with a curled,
charred tip, and a separate teardrop flame shell above it (its own slot, for an emissive /
flickering material). The wax stops 0.2 mm short of the glass, so nothing is coplanar.
Origin: bottom centre. Slots: M_Glass, M_Wax, M_Wick, M_Flame.

    blender -b --factory-startup -P films/host-studio/props/candle.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402

NAME = "candle"
CM = M.CM


def cm(pts):
    return [(r * CM, z * CM) for r, z in pts]


GLASS = cm([
    (0.0, 0.12), (3.15, 0.10), (3.45, 0.04), (3.58, 0.0), (3.78, 0.02), (3.90, 0.10), (3.955, 0.28),
    (3.97, 1.0), (4.0, 9.80), (3.995, 9.90), (3.975, 9.96), (3.94, 9.993), (3.89, 10.0),
    (3.79, 10.0), (3.745, 9.99), (3.712, 9.955), (3.70, 9.90), (3.70, 9.80),
    (3.675, 1.62), (3.655, 1.38), (3.60, 1.20), (3.50, 1.09), (3.35, 1.03),
    (3.10, 1.0), (0.0, 0.98),
])
WAX_TOP = 8.0
WAX = cm([
    (0.0, 1.0), (3.08, 1.02), (3.33, 1.05), (3.48, 1.11), (3.58, 1.22), (3.633, 1.39), (3.653, 1.62),
    (3.680, 7.90), (3.672, 7.99), (3.645, 8.035), (3.58, 8.04), (3.40, 8.02),
    (3.0, 7.985), (2.65, 7.95), (2.45, 7.90), (2.2, 7.83), (1.7, 7.76), (1.1, 7.715), (0.5, 7.70), (0.0, 7.70),
])
FLAME = cm([
    (0.0, 0.0), (0.10, 0.012), (0.20, 0.05), (0.30, 0.13), (0.37, 0.26), (0.41, 0.42), (0.42, 0.58),
    (0.40, 0.78), (0.35, 1.02), (0.28, 1.30), (0.20, 1.60), (0.12, 1.88), (0.055, 2.12), (0.018, 2.30), (0.0, 2.40),
])
FLAME_BASE = 8.42


def build():
    glass = M.glassy(S.material("M_Glass", (0.96, 0.97, 0.97), 0.0, specular=0.5), roughness=0.0, ior=1.5,
                     tint=(0.96, 0.98, 0.97))
    wax = S.material("M_Wax", (0.84, 0.75, 0.58), 0.5)
    b = M.principled(wax)
    M.set_input(b, ["Subsurface Weight", "Subsurface"], 0.6)
    M.set_input(b, "Subsurface Radius", (0.012, 0.007, 0.004))
    M.set_input(b, "Subsurface Scale", 0.6)
    wick = S.material("M_Wick", (0.018, 0.016, 0.015), 0.85)
    flame = flame_material()

    parts = [
        M.lathe_uv("glass", GLASS, [glass], segs=72),
        M.lathe_uv("wax", WAX, [wax], segs=72),
        M.lathe_uv("flame", [(r, z + FLAME_BASE * CM) for r, z in FLAME], [flame], segs=20),
    ]

    # wick: rises from inside the wax, bends over sideways (+Y, seen from the front) and curls;
    # the charred tip ends in a small bead, all inside the lower flame.
    ctrl = [(0, 0, 7.30), (0, 0, 7.75), (0, 0.004, 8.15), (0, 0.022, 8.45), (0, 0.07, 8.66),
            (0, 0.14, 8.77), (0, 0.205, 8.76), (0, 0.235, 8.68)]
    path = [(x * CM, y * CM, z * CM) for x, y, z in S.catmull_rom(ctrl, per_seg=4)]
    ring = []
    for i, p in enumerate(path):
        t = i / (len(path) - 1)
        r = (0.050 + 0.012 * t * t) * CM          # the charred end is a bit fatter
        ring.append(r)
    rings = _tube_rings(path, ring, sides=8)
    tip = path[-1]
    d = [a - b for a, b in zip(path[-1], path[-2])]
    n = math.sqrt(sum(c * c for c in d))
    cap = tuple(p + c / n * ring[-1] * 0.8 for p, c in zip(tip, d))
    parts.append(M.loft("wick", rings, [wick], cap0="ngon", cap1=cap))
    return parts


def flame_material():
    """Preview flame: emission graded up the flame (blue root, white-yellow core, orange tip)."""
    m = S.material("M_Flame", (1.0, 0.62, 0.25), 0.5)
    nt = m.node_tree
    b = M.principled(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = FLAME_BASE * CM
    mr.inputs["From Max"].default_value = FLAME_BASE * CM + 0.024
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.15, 0.25, 0.9, 1)
    els[1].position, els[1].color = 0.16, (1.0, 0.55, 0.18, 1)
    e = els.new(0.38)
    e.color = (1.0, 0.85, 0.55, 1)
    e = els.new(0.80)
    e.color = (1.0, 0.55, 0.15, 1)
    e = els.new(1.0)
    e.color = (0.9, 0.30, 0.06, 1)
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    M.set_input(b, "Base Color", (0, 0, 0, 1))
    nt.links.new(ramp.outputs["Color"], b.inputs[next(k for k in ("Emission Color", "Emission") if k in b.inputs)])
    M.set_input(b, "Emission Strength", 3.5)
    return m


def flame_light(ob):
    """Preview only: the flame lights the wax and the board."""
    M.point_light("_flame", (0, 0, (FLAME_BASE + 0.7) * CM), 0.35)


def _tube_rings(path, radii, sides=8):
    from mathutils import Vector
    pts = [Vector(p) for p in path]
    rings = []
    nrm = Vector((1, 0, 0))
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        nrm = (nrm - nrm.dot(t) * t).normalized()
        b = t.cross(nrm)
        rings.append([p + radii[i] * (math.cos(a) * nrm + math.sin(a) * b)
                      for a in (2 * math.pi * k / sides for k in range(sides))])
    return rings


if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, sharp_angle=50, extras=flame_light)
