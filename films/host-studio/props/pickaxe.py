"""pickaxe — a palm-sized brass pickaxe: 14 cm dark-wood handle, 11 cm curved double-pointed head.

Built standing (handle up +Z, head across Y, thickness along X), then laid on its side as it
rests on a shelf: the handle runs along +Y with the head at the +Y end, the head's span along X
and its points curving back towards the handle. It is tipped a fraction of a degree about X so
that both the head's eye and the handle's butt knob touch z = 0 (it rests stably, nothing
floats). Head: a tapered crescent swept along an arc, unioned with a rounded eye block; the
handle passes through the eye and shows 4 mm above it. Handle: an oval loft (long axis in the
swing plane, so lying flat it rests on its narrow side) with a butt knob, a slim waist and a
swell at the eye. Origin: bottom centre of the footprint. Slots: M_Brass, M_HandleWood.

    blender -b --factory-startup -P films/host-studio/props/pickaxe.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402

NAME = "pickaxe"
CM = M.CM

# handle stations (z, a = half-width in the swing plane (Y), b = half-thickness (X)), cm
HANDLE = [
    (0.05, 0.36, 0.29), (0.14, 0.56, 0.45), (0.30, 0.68, 0.55), (0.58, 0.73, 0.59), (0.95, 0.72, 0.58),
    (1.45, 0.65, 0.52), (2.2, 0.595, 0.475), (3.8, 0.575, 0.46), (6.5, 0.575, 0.46), (9.0, 0.605, 0.48),
    (11.0, 0.655, 0.515), (13.55, 0.675, 0.53), (13.82, 0.63, 0.495), (13.95, 0.48, 0.38),
]
HANDLE_TOP = 14.0

# head: crescent centre line is an arc through the centre (0, ZC) and the tips (+-5.5, ZC - SAG)
SPAN = 11.0
SAG = 1.8
ZC = 12.75
# eye collar stations (z, half-thickness X, half-width Y), cm
EYE = [
    (11.22, 0.56, 0.71), (11.28, 0.64, 0.80), (11.40, 0.69, 0.86), (11.9, 0.72, 0.90), (12.5, 0.76, 0.95),
    (13.3, 0.78, 0.975), (13.52, 0.755, 0.95), (13.62, 0.70, 0.88), (13.67, 0.62, 0.79),
]


def oval(a, b, sides=16, n=2.0):
    pts = []
    for k in range(sides):
        t = 2 * math.pi * k / sides
        c, s = math.cos(t), math.sin(t)
        pts.append((math.copysign(abs(c) ** (2 / n), c), math.copysign(abs(s) ** (2 / n), s)))
    return [(b * px, a * py) for px, py in pts]


def handle(mat):
    rings = []
    for z, a, b in HANDLE:
        rings.append([Vector((x * CM, y * CM, z * CM)) for x, y in oval(a, b, 24)])
    return M.loft("handle", rings, [mat], cap0=(0, 0, 0), cap1=(0, 0, HANDLE_TOP * CM))


def crescent(mat):
    half = SPAN / 2
    R = (half * half + SAG * SAG) / (2 * SAG)
    phmax = math.asin(half / R)
    centre = Vector((0, 0, ZC - R))

    def at(t):
        ph = t * phmax
        n = Vector((0, math.sin(ph), math.cos(ph)))     # in-plane normal, outward from the arc centre
        return centre + n * R, n

    us = [0.0, 0.05, 0.10, 0.16, 0.22, 0.29, 0.36, 0.43, 0.50, 0.57, 0.64, 0.70, 0.76, 0.81, 0.855, 0.895,
          0.928, 0.955, 0.975, 0.99]
    ts = [-u for u in reversed(us[1:])] + us
    prof = oval(1.0, 1.0, 28, n=2.6)
    rings = []
    for t in ts:
        u = abs(t)
        h = 1.15 * (1 - u ** 2.2) ** 0.6 + 0.035          # height of the blade (in the swing plane)
        w = 0.95 * (1 - u ** 2.5) ** 0.55 + 0.035         # thickness (X)
        c, n = at(t)
        x = Vector((1, 0, 0))
        rings.append([(c + n * (h / 2 * py) + x * (w / 2 * px)) * CM for px, py in prof])
    tip0, _ = at(-1.0)
    tip1, _ = at(1.0)
    ob = M.loft("crescent", rings, [mat], cap0=tuple(tip0 * CM), cap1=tuple(tip1 * CM))
    recalc_normals(ob)
    return ob


def recalc_normals(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()


def head(mat):
    """The eye: a forged collar round the handle (rounded-square section, swelling towards the
    blade, chamfered ends), unioned with the crescent."""
    rings = []
    for z, b, a in EYE:
        rings.append([Vector((x * CM, y * CM, z * CM)) for x, y in oval(a, b, 24, n=4.0)])
    eye = M.loft("eye", rings, [mat], cap0="ngon", cap1="ngon")
    recalc_normals(eye)
    cres = crescent(mat)
    boo = eye.modifiers.new("Union", "BOOLEAN")
    boo.operation = "UNION"
    boo.solver = "EXACT"
    boo.object = cres
    eye = M.bake(eye)
    bpy.data.objects.remove(cres, do_unlink=True)
    return eye


def materials():
    brass = S.material("M_Brass", (0.87, 0.67, 0.33), 0.18, metallic=1.0)
    M.roughness_noise(brass, 0.12, 0.28, scale=900.0)
    wood = S.material("M_HandleWood", (0.085, 0.040, 0.022), 0.42)
    nt = wood.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (6.0, 260.0, 1.0)    # UV: U along the handle -> long streaks
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Detail"].default_value = 6.0
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = 0.35, (0.030, 0.013, 0.007, 1)
    e[1].position, e[1].color = 0.68, (0.095, 0.045, 0.024, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], M.principled(wood).inputs["Base Color"])
    return brass, wood


def lay_down(ob):
    """Standing -> lying on its side, then tip about X so the eye and the butt knob both rest on z = 0."""
    # standing (x, y, z) -> lying (y, z, x): handle along +Y, head span along X, thickness along Z
    rot = Matrix(((0, 1, 0, 0), (0, 0, 1, 0), (1, 0, 0, 0), (0, 0, 0, 1)))
    ob.data.transform(rot)
    vs = [v.co.copy() for v in ob.data.vertices]
    for _ in range(3):
        head_low = min((v for v in vs if v.y > 9 * CM), key=lambda v: v.z)
        butt_low = min((v for v in vs if v.y < 4 * CM), key=lambda v: v.z)
        ang = math.atan2(butt_low.z - head_low.z, head_low.y - butt_low.y)
        if abs(ang) < 1e-6:
            break
        r = Matrix.Rotation(ang, 4, "X")
        ob.data.transform(r)
        vs = [v.co.copy() for v in ob.data.vertices]
    ob.data.update()
    return ob


def build():
    brass, wood = materials()
    parts = [handle(wood), head(brass)]
    ob = S.join(NAME, parts)
    lay_down(ob)
    return [ob]


if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, sharp_angle=45)
