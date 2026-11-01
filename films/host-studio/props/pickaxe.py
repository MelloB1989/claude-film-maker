"""pickaxe — a brass display pickaxe on a walnut plinth: 20 cm dark-wood handle, 15.6 cm head.

The pick: a tapered, curved, double-pointed brass head (a crescent swept along an arc, unioned
with a forged eye collar) on an oval dark-wood handle with a butt knob, a slim waist and a
swell at the eye; the handle shows 6 mm above the eye. It is the palm-sized design scaled 1.42x.

The display: the pick is mounted diagonally, its handle 35 degrees from vertical with the head
up and to the right (+Y), the head's span in the YZ plane (parallel to the wall, facing +X), on
a vertical brass pin (4.8 mm) rising from a turned brass collar on a walnut plinth 12 x 6 x
2.5 cm (Y x X x Z, edges rounded 2 mm). The pin enters the handle from below and ends at its
axis; the pin sits under the pick's centre of width, the butt end clears the plinth by 2 cm.

Origin: bottom centre of the plinth. Slots: M_Brass, M_HandleWood, M_Walnut. UVs: handle along
its length; brass parts lofted/lathed; walnut box-projected (1 UV = 1 m), grain along Y.

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
import _furniture as F  # noqa: E402

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
        rings.append([Vector((x * CM, y * CM, z * CM)) for x, y in oval(a, b, 40)])
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
    prof = oval(1.0, 1.0, 40, n=2.6)
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
        rings.append([Vector((x * CM, y * CM, z * CM)) for x, y in oval(a, b, 40, n=4.0)])
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


SCALE = 1.42                    # palm-sized design -> display size
TILT = 35.0                     # handle from vertical, head up and to +Y
PLINTH = (6.0, 12.0, 2.5)       # X (depth) x Y (width) x Z, cm
PLINTH_R = 0.2
CLEAR = 2.0                     # butt end above the plinth, cm
PIN_R = 0.24
COLLAR = [(0.0, -0.05), (0.62, -0.05), (0.62, 0.10), (0.60, 0.17), (0.55, 0.21), (0.42, 0.25),
          (0.30, 0.30), (0.26, 0.36), (0.0, 0.36)]      # turned collar (r, z) cm over the plinth top


def walnut():
    return F.wood("M_Walnut", (0.36, 0.225, 0.14), (0.16, 0.085, 0.045), roughness=0.5, ring=12.0, seed=0.3)


def plinth(mat):
    x, y, z = (v * CM for v in PLINTH)
    ob = S.box("plinth", (-x / 2, -y / 2, 0), (x / 2, y / 2, z), mat)
    bev = ob.modifiers.new("Bevel", "BEVEL")
    bev.width = PLINTH_R * CM
    bev.segments = 4
    bev.limit_method = "ANGLE"
    ob = M.bake(ob)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    M.box_uv(bm, grain=1)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def mount(pick, brass):
    """Tilt the standing pick, put it over the plinth and add the pin and its collar."""
    me = pick.data
    me.transform(Matrix.Scale(SCALE, 4))
    me.transform(Matrix.Rotation(math.radians(-TILT), 4, "X"))
    vs = [v.co for v in me.vertices]
    y_mid = (min(v.y for v in vs) + max(v.y for v in vs)) / 2
    z_low = min(v.z for v in vs)
    top = PLINTH[2] * CM
    # the handle axis runs from the origin along (0, sin, cos): the pin meets it at y = y_mid
    t = y_mid / math.sin(math.radians(TILT))
    axis_pt = Vector((0.0, y_mid, t * math.cos(math.radians(TILT))))
    shift = Vector((0.0, -y_mid, top + CLEAR * CM - z_low))
    me.transform(Matrix.Translation(shift))
    me.update()
    pin_top = axis_pt + shift
    pin = M.lathe_uv("pin", [(0.0, top), (PIN_R * CM, top), (PIN_R * CM, pin_top.z), (0.0, pin_top.z)],
                     [brass], segs=24)
    collar = M.lathe_uv("collar", [(r * CM, top + z * CM) for r, z in COLLAR], [brass], segs=48)
    print(f"pickaxe: pin {(pin_top.z - top) / CM:.1f} cm from the plinth to the handle axis")
    return [pin, collar]


def build():
    brass, wood = materials()
    pick = S.join("pick", [handle(wood), head(brass)])
    parts = [pick] + mount(pick, brass) + [plinth(walnut())]
    return parts


if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, origin=(0, 0, 0), sharp_angle=45, glossy=True, views=[
        ("", (1.0, 0.75, 0.85), 70, 1.12),
        ("_front", (1.0, 0.0, 0.10), 70, 1.12),
    ])
