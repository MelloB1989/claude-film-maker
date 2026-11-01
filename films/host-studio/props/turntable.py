"""turntable — a belt-drive turntable on a solid walnut plinth, 45 x 35 x 9 cm (wider along Y), front toward +X.

Walnut plinth on four black/brass isolation feet, a heavy black platter driven by a rim belt from a motor pod
in the back-left corner, a black record with its centre label (own slot, UV 0..1 over the label disc), a
straight tonearm with offset headshell on a pivot base at the back right, resting on the record's outer
grooves, an arm rest and cue lever, a knurled speed knob front left and a two-button 33/45 selector front
right. No text or logos.
Origin: bottom centre of the footprint (the feet stand on z = 0).

    blender -b --factory-startup -P films/host-studio/props/turntable.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

args = S.parse_args(__file__)
S.reset_scene()

cm = 0.01


# --------------------------------------------------------------------------- local helpers

def bake(ob):
    """Apply an object's modifiers in place."""
    if ob.modifiers:
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        old = ob.data
        ob.modifiers.clear()
        ob.data = me
        bpy.data.meshes.remove(old)
    return ob


def uv_layer(me):
    return me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")


def uv_box(ob, grain=None):
    """World-scale box projection, 1 UV unit = 1 m. U runs along axis `grain` (0, 1, 2) wherever the face
    plane contains it (default: the part's longest dimension), so wood grain follows the board."""
    bake(ob)
    me = ob.data
    uvl = uv_layer(me)
    mw = ob.matrix_world
    cos = [mw @ v.co for v in me.vertices]
    ext = [max(c[i] for c in cos) - min(c[i] for c in cos) for i in range(3)]
    if grain is None:
        grain = max(range(3), key=lambda i: ext[i])
    rot = mw.to_3x3()
    for p in me.polygons:
        n = rot @ p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        plane = [i for i in range(3) if i != ax]
        u = grain if grain in plane else max(plane, key=lambda i: ext[i])
        v = plane[0] if plane[1] == u else plane[1]
        for li in p.loop_indices:
            c = cos[me.loops[li].vertex_index]
            uvl.data[li].uv = (c[u], c[v])
    return ob


def uv_planar(ob, origin, uax, vax, size_u, size_v, slot=None):
    """Planar projection: `origin` maps to UV (0.5, 0.5), size_u x size_v metres span 0..1.
    With `slot`, only faces of that material index are mapped."""
    bake(ob)
    me = ob.data
    uvl = uv_layer(me)
    mw = ob.matrix_world
    o, ua, va = Vector(origin), Vector(uax).normalized(), Vector(vax).normalized()
    for p in me.polygons:
        if slot is not None and p.material_index != slot:
            continue
        for li in p.loop_indices:
            c = mw @ me.vertices[me.loops[li].vertex_index].co - o
            uvl.data[li].uv = (c.dot(ua) / size_u + 0.5, c.dot(va) / size_v + 0.5)
    return ob


def weighted_normals(ob):
    """Face-area weighted custom normals: big flat faces stay flat next to their bevels."""
    m = ob.modifiers.new("WN", "WEIGHTED_NORMAL")
    m.mode = "FACE_AREA"
    m.weight = 50
    m.keep_sharp = True
    bake(ob)


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def wood_preview(mat, dark, light, rings=110.0):
    """Preview-only walnut grain driven by the UVs (streaks run along U), so the grain direction is checkable."""
    nt = mat.node_tree
    bsdf = principled(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (4.0, rings, 1.0)
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.3
    nz.inputs["Detail"].default_value = 9.0
    nz.inputs["Roughness"].default_value = 0.62
    nz.inputs["Distortion"].default_value = 0.35
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.36
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].position = 0.66
    ramp.color_ramp.elements[1].color = (*light, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.02
    bump.inputs["Distance"].default_value = 0.0005
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


GLYPHS = {
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
}


def uv_test_image(name="_uv_test", n=512):
    """Preview-only UV test card: grid, red border, blue arrow and the word UP, green bottom-left corner."""
    import numpy as np
    a = np.ones((n, n, 4), dtype=np.float32) * np.array([0.86, 0.84, 0.78, 1.0], dtype=np.float32)
    a[::32, :, :3] = 0.6
    a[:, ::32, :3] = 0.6
    b = n // 40
    a[:b, :, :3] = a[-b:, :, :3] = a[:, :b, :3] = a[:, -b:, :3] = (0.75, 0.05, 0.05)
    a[b:b + n // 8, b:b + n // 8, :3] = (0.1, 0.6, 0.15)          # bottom-left (UV 0, 0)
    blue = (0.08, 0.2, 0.75)
    cx = n // 2
    a[int(n * 0.18):int(n * 0.55), cx - n // 28:cx + n // 28, :3] = blue      # shaft
    for y in range(int(n * 0.55), int(n * 0.78)):                            # head
        half = int((n * 0.78 - y) * 0.55)
        a[y, cx - half:cx + half, :3] = blue
    px = n // 40
    x0 = cx - 11 * px // 2 * 1
    for gi, ch in enumerate("UP"):
        for r, row in enumerate(GLYPHS[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    y = int(n * 0.92) - r * px
                    x = x0 + gi * 6 * px + c * px
                    a[y - px:y, x:x + px, :3] = (0.05, 0.05, 0.05)
    img = bpy.data.images.new(name, n, n, alpha=False)
    img.pixels.foreach_set(a.ravel())
    img.pack()
    return img


def label_preview(mat):
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.get("_uv_test") or uv_test_image()
    nt.links.new(tex.outputs["Color"], principled(mat).inputs["Base Color"])


def clear_preview():
    for o in list(bpy.data.objects):
        if o.name.startswith("_"):
            bpy.data.objects.remove(o, do_unlink=True)


def lathe_at(name, profile, mats, centre, segs=64, mat_split=None, axis=None):
    """S.lathe with the axis through `centre` (local Z = world Z unless `axis` = (p0, p1))."""
    if axis is None:
        m = Matrix.Translation(Vector(centre))
    else:
        m, _ = S.frame_to(*axis)
    return S.lathe(name, [(r * cm, z * cm) for r, z in profile], mats, segs=segs, matrix=m, mat_split=mat_split)


def add_slot(ob, mat):
    ob.data.materials.append(mat)
    return len(ob.data.materials) - 1


# --------------------------------------------------------------------------- materials

WALNUT = S.material("M_Walnut", (0.15, 0.065, 0.032), 0.5)
FOOT = S.material("M_FootMetal", (0.72, 0.52, 0.26), 0.32, metallic=1.0)        # brass
BLACK = S.material("M_BlackMetal", (0.018, 0.018, 0.019), 0.38, metallic=0.6)   # black anodised parts
PLATTER = S.material("M_Platter", (0.012, 0.012, 0.013), 0.30)                  # black lacquered platter
VINYL = S.material("M_Vinyl", (0.008, 0.008, 0.009), 0.28)
LABEL = S.material("M_Label_Record", (0.80, 0.78, 0.72), 0.5)
ARM = S.material("M_ArmMetal", (0.78, 0.78, 0.77), 0.24, metallic=1.0)          # brushed aluminium
wood_preview(WALNUT, (0.045, 0.018, 0.009), (0.20, 0.085, 0.040))
label_preview(LABEL)


def vinyl_preview(mat):
    """Preview-only groove sheen: fine radial rings from the record's planar UV (0..1 over the disc)."""
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sub = nt.nodes.new("ShaderNodeVectorMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = (0.5, 0.5, 0.0)
    nt.links.new(tc.outputs["UV"], sub.inputs[0])
    ln = nt.nodes.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    nt.links.new(sub.outputs["Vector"], ln.inputs[0])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 900.0
    nt.links.new(ln.outputs["Value"], mul.inputs[0])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.noise_dimensions = "1D"
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 2.0
    nt.links.new(mul.outputs["Value"], nz.inputs["W"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.0002
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], principled(mat).inputs["Normal"])


vinyl_preview(VINYL)

# --------------------------------------------------------------------------- dimensions (cm)

PX, PY, PH = 35.0, 45.0, 9.0            # plinth depth (X), width (Y), height
FOOT_H = 2.2
Z0, ZT = FOOT_H, FOOT_H + PH            # plinth bottom / top
PC = Vector((0.0, -5.0))                # platter centre (left of middle, room for the arm on the right)
PLAT_R, PLAT_T, PLAT_GAP = 15.0, 2.8, 0.5
Z_PB = ZT + PLAT_GAP                    # platter bottom
Z_PT = Z_PB + PLAT_T                    # platter top
REC_R = 15.05
Z_RB = Z_PT + 0.03                      # record bottom (0.3 mm above the platter: no coplanar faces)
REC_T = 0.17                            # vinyl thickness in the grooved area
Z_RT = Z_RB + REC_T                     # record playing surface
LABEL_R = 5.0
BELT_Z = Z_PB + 1.25

parts = []

# --------------------------------------------------------------------------- plinth
plinth = S.prism("plinth", S.rounded_rect(PX * cm, PY * cm, 1.2 * cm, segs=6),
                 (0, 0, Z0 * cm), (0, 0, ZT * cm), WALNUT, up=(1, 0, 0))
S.bevel(plinth, 0.32 * cm, segments=3, angle=30)
uv_box(plinth, grain=1)
parts.append(plinth)

# --------------------------------------------------------------------------- feet: black body, brass collar and base ring
foot_profile = [
    (0.0, 0.0), (1.70, 0.0), (1.82, 0.04), (1.86, 0.14),        # brass base ring
    (1.86, 0.30), (1.80, 0.36),
    (1.74, 0.42),                                                  # black body
    (1.66, 1.08), (1.60, 1.14), (1.60, 1.24), (1.66, 1.30),       # small groove
    (1.74, 1.56),
    (1.92, 1.62), (2.02, 1.70), (2.06, 1.82),                      # brass collar
    (2.06, 2.06), (2.00, 2.16), (1.90, 2.20 + 0.06),
    (0.0, 2.20 + 0.06),                                            # 0.6 mm into the plinth
]


def foot_slot(i):
    return 0 if i <= 4 or i >= 11 else 1


for sx in (-1, 1):
    for sy in (-1, 1):
        parts.append(uv_box(lathe_at(f"foot_{sx}_{sy}", foot_profile, [FOOT, BLACK],
                                     ((PX / 2 - 3.6) * sx * cm, (PY / 2 - 4.0) * sy * cm, 0),
                                     segs=40, mat_split=foot_slot)))

# --------------------------------------------------------------------------- hub under the platter, platter, belt, motor pod
parts.append(uv_box(lathe_at("hub", [(0, -0.05), (6.8, -0.05), (6.8, PLAT_GAP - 0.05), (6.5, PLAT_GAP + 0.03),
                                     (0, PLAT_GAP + 0.03)], [BLACK], (PC.x * cm, PC.y * cm, ZT * cm), segs=64)))

R = PLAT_R
platter_profile = [
    (0.0, 0.0), (R - 0.9, 0.0), (R - 0.35, 0.18), (R - 0.05, 0.55), (R, 0.62),
    (R, 1.02), (R - 0.12, 1.06), (R - 0.15, 1.10), (R - 0.15, 1.40), (R - 0.12, 1.44), (R, 1.48),   # belt groove
    (R, 2.18), (R - 0.03, 2.22), (R - 0.03, 2.30), (R, 2.34),                                        # machined line
    (R, 2.66), (R - 0.04, 2.75), (R - 0.14, PLAT_T), (0.0, PLAT_T),
]
platter = lathe_at("platter", platter_profile, [PLATTER], (PC.x * cm, PC.y * cm, Z_PB * cm), segs=128)
parts.append(uv_box(platter))

MOTOR = Vector((-13.8, -19.0))
PUL_R = 0.72                       # belt radius at the pulley groove
belt_r_in = R - 0.15


def belt_path(segs_big=160, segs_small=24):
    c1, r1 = PC, belt_r_in + 0.03
    c2, r2 = MOTOR, PUL_R + 0.03
    d = c2 - c1
    L = d.length
    th = math.atan2(d.y, d.x)
    al = math.acos((r1 - r2) / L)
    pts = []
    for k in range(segs_big + 1):                       # long way round the platter
        a = th + al + (2 * math.pi - 2 * al) * k / segs_big
        pts.append(c1 + r1 * Vector((math.cos(a), math.sin(a))))
    for k in range(1, segs_small):                       # short way round the pulley
        a = th - al + 2 * al * k / segs_small
        pts.append(c2 + r2 * Vector((math.cos(a), math.sin(a))))
    return [(p.x * cm, p.y * cm, BELT_Z * cm) for p in pts]


belt = S.sweep("belt", belt_path(), [(-0.16 * cm, -0.03 * cm), (0.16 * cm, -0.03 * cm),
                                     (0.16 * cm, 0.03 * cm), (-0.16 * cm, 0.03 * cm)],
               BLACK, hint=(0, 0, 1), closed=True)
parts.append(uv_box(belt))

pod_profile = [(0, -0.05), (2.0, -0.05), (2.0, 1.05), (1.94, 1.16), (1.84, 1.2), (0.95, 1.2), (0.95, 1.24),
               (0, 1.24)]
parts.append(uv_box(lathe_at("motor_pod", pod_profile, [BLACK], (MOTOR.x * cm, MOTOR.y * cm, ZT * cm), segs=48)))
gz = BELT_Z - ZT
pulley_profile = [(0, 1.2), (0.85, 1.2), (0.85, gz - 0.25), (0.80, gz - 0.2), (PUL_R, gz - 0.18),
                  (PUL_R, gz + 0.18), (0.80, gz + 0.2), (0.85, gz + 0.25), (0.85, gz + 0.62), (0.8, gz + 0.68),
                  (0.25, gz + 0.68), (0.25, gz + 0.62), (0, gz + 0.62)]
parts.append(uv_box(lathe_at("pulley", pulley_profile, [ARM], (MOTOR.x * cm, MOTOR.y * cm, ZT * cm), segs=40)))

# --------------------------------------------------------------------------- record (one lathe: vinyl + label slot) and spindle
HOLE = 0.37
T = REC_T
top = [(HOLE, T + 0.02), (LABEL_R - 0.05, T + 0.02), (LABEL_R, T + 0.012), (LABEL_R + 0.06, T)]
LABEL_BANDS = 2                          # bands 0..1 are the label face (top), from the hole to r = 5
grooves = [(6.30, T), (6.36, T - 0.004), (6.44, T - 0.004), (6.50, T)]          # lead-out ring
for gap in (8.05, 9.40, 10.85, 12.10, 13.25):                                    # gaps between tracks
    grooves += [(gap - 0.05, T), (gap, T + 0.0025), (gap + 0.05, T)]
edge = [(14.45, T), (14.62, T + 0.012), (14.78, T + 0.035), (14.92, T + 0.035), (15.0, T + 0.02),
        (REC_R, T - 0.03), (REC_R, 0.05), (15.0, 0.005), (14.9, 0.0)]
bottom = [(LABEL_R, 0.0), (HOLE, 0.0), (HOLE, T + 0.02)]
record_profile = top + grooves + edge + bottom
record = lathe_at("record", record_profile, [VINYL, LABEL], (PC.x * cm, PC.y * cm, Z_RB * cm), segs=128,
                  mat_split=lambda i: 1 if i < LABEL_BANDS else 0)
rc = Vector((PC.x * cm, PC.y * cm, Z_RT * cm))
uv_planar(record, rc, (0, 1, 0), (-1, 0, 0), 2 * REC_R * cm, 2 * REC_R * cm, slot=0)
uv_planar(record, rc, (0, 1, 0), (-1, 0, 0), 2 * LABEL_R * cm, 2 * LABEL_R * cm, slot=1)
parts.append(record)

spindle_profile = [(0, Z_PT - 0.05 - Z_PT), (0.36, -0.05), (0.36, 1.25), (0.33, 1.38), (0.25, 1.46),
                   (0.12, 1.50), (0, 1.51)]
parts.append(uv_box(lathe_at("spindle", spindle_profile, [ARM], (PC.x * cm, PC.y * cm, Z_RT * cm), segs=24)))

# --------------------------------------------------------------------------- tonearm geometry
PIV = Vector((-8.6, 15.4))
L_TUBE = 19.2                  # pivot to headshell collar centre
HS_LEN = 4.2                   # collar centre to stylus, along the headshell
OFFSET = math.radians(22)
R_STYLUS = 14.15               # outer grooves
Z_ARM = Z_RT + 1.98            # tube axis height (arm parallel to the record)


def rot2(v, a):
    return Vector((v.x * math.cos(a) - v.y * math.sin(a), v.x * math.sin(a) + v.y * math.cos(a)))


def arm_pose(phi, sgn):
    d = Vector((math.cos(phi), math.sin(phi)))
    dh = rot2(d, sgn * OFFSET)
    return PIV + d * L_TUBE + dh * HS_LEN, d, dh


best = None
for sgn in (1, -1):
    prev = None
    for k in range(36000):
        phi = 2 * math.pi * k / 36000
        s, d, dh = arm_pose(phi, sgn)
        f = (s - PC).length - R_STYLUS
        if prev is not None and (f > 0) != (prev > 0) and s.x > PIV.x:
            radial = (s - PC).normalized()
            score = abs(dh.dot(radial))         # 0 = cartridge tangent to the groove
            if best is None or score < best[0]:
                best = (score, phi, sgn)
        prev = f
_, PHI, SGN = best
STYLUS, D, DH = arm_pose(PHI, SGN)
N = Vector((-D.y, D.x))                     # horizontal, perpendicular to the tube
HC = PIV + D * L_TUBE                       # headshell collar centre
print(f"tonearm: phi {math.degrees(PHI):.1f} deg, offset sign {SGN}, effective length "
      f"{(STYLUS - PIV).length:.2f} cm, stylus at r {(STYLUS - PC).length:.2f} cm, "
      f"tangent error {math.degrees(math.asin(min(1, best[0]))):.1f} deg")


def v3(p2, z):
    return (p2.x * cm, p2.y * cm, z * cm)


# pivot base: plate, height collar, pillar, bearing housing with cap, axle stubs
parts.append(uv_box(lathe_at("arm_base", [(0, -0.05), (2.75, -0.05), (2.75, 0.32), (2.68, 0.42), (2.55, 0.46),
                                         (0, 0.46)], [BLACK], v3(PIV, ZT), segs=56)))
parts.append(uv_box(lathe_at("arm_collar", [(0, 0.4), (1.25, 0.4), (1.25, 0.95), (1.18, 1.02), (0, 1.02)],
                             [ARM], v3(PIV, ZT), segs=40)))
pillar_top = Z_ARM - 1.0 - ZT
parts.append(uv_box(lathe_at("arm_pillar", [(0, 0.98), (0.8, 0.98), (0.8, pillar_top + 0.05), (0, pillar_top + 0.05)],
                             [ARM], v3(PIV, ZT), segs=32)))
hz = Z_ARM - ZT
housing_profile = [(0, hz - 1.0), (1.25, hz - 1.0), (1.32, hz - 0.92), (1.32, hz + 0.55), (1.25, hz + 0.65),
                   (1.0, hz + 0.68), (0.95, hz + 0.95), (0.7, hz + 1.12), (0.35, hz + 1.2), (0, hz + 1.22)]
parts.append(uv_box(lathe_at("arm_housing", housing_profile, [BLACK, ARM], v3(PIV, ZT), segs=48,
                             mat_split=lambda i: 1 if i >= 5 else 0)))
for s_ in (-1, 1):
    a0 = PIV + N * (1.2 * s_)
    a1 = PIV + N * (1.75 * s_)
    parts.append(uv_box(lathe_at(f"axle_{s_}", [(0, -0.5), (0.3, -0.5), (0.3, 0.42), (0.25, 0.5), (0, 0.5)], [ARM],
                                 None, segs=20, axis=(v3(a0, Z_ARM), v3(a1, Z_ARM)))))

# arm tube, rear stub, counterweight
tube = S.cylinder("arm_tube", v3(PIV - D * 0.5, Z_ARM), v3(HC - D * 0.55, Z_ARM), 0.33 * cm, ARM, segs=24)
parts.append(uv_box(tube))
stub = S.cylinder("arm_stub", v3(PIV - D * 0.4, Z_ARM), v3(PIV - D * 8.2, Z_ARM), 0.26 * cm, ARM, segs=20)
parts.append(uv_box(stub))
cw_profile = [(0, -1.45), (0.5, -1.45), (1.38, -1.42), (1.52, -1.30), (1.55, -1.1), (1.55, -0.35), (1.50, -0.30),
              (1.50, -0.18), (1.55, -0.13), (1.55, 1.15), (1.50, 1.32), (1.35, 1.42), (0.42, 1.45), (0, 1.45)]
parts.append(uv_box(lathe_at("counterweight", cw_profile, [BLACK, ARM], None, segs=48,
                             mat_split=lambda i: 1 if 5 <= i <= 7 else 0,
                             axis=(v3(PIV - D * 6.6, Z_ARM), v3(PIV - D * 3.5, Z_ARM)))))

# headshell: collar, plate, finger lift, cartridge, cantilever
parts.append(uv_box(lathe_at("hs_collar", [(0, -0.62), (0.45, -0.62), (0.52, -0.55), (0.52, 0.55), (0.45, 0.62),
                                          (0, 0.62)], [ARM], None, segs=28,
                             axis=(v3(HC - D * 0.6, Z_ARM), v3(HC + D * 0.6, Z_ARM)))))
PLATE_Z0, PLATE_Z1 = Z_ARM - 0.40, Z_ARM - 0.12
hs_start = HC + D * 0.45
hs_end = STYLUS + DH * 1.05
hs_len = (hs_end - hs_start).dot(DH)
hs_mid = hs_start + DH * (hs_len / 2)
plate = S.prism("hs_plate", S.rounded_rect(hs_len * cm, 1.85 * cm, 0.25 * cm, segs=4),
                v3(hs_mid, PLATE_Z0), v3(hs_mid, PLATE_Z1), BLACK, up=(DH.x, DH.y, 0))
S.bevel(plate, 0.05 * cm, segments=2, angle=30)
parts.append(uv_box(plate))
# finger lift on the outer side (away from the spindle)
side = Vector((-DH.y, DH.x))
if side.dot(STYLUS - PC) < 0:
    side = -side
fl0 = STYLUS + DH * 0.2 + side * 0.85
lift_pts = [v3(fl0, PLATE_Z0 + 0.14), v3(fl0 + side * 0.6, PLATE_Z0 + 0.2), v3(fl0 + side * 1.25, PLATE_Z0 + 0.45),
            v3(fl0 + side * 1.65, PLATE_Z0 + 0.9), v3(fl0 + side * 1.8 + DH * 0.05, PLATE_Z0 + 1.15)]
lift = S.sweep("finger_lift", S.catmull_rom(lift_pts, per_seg=5), S.circle_outline(0.075 * cm, 10), ARM,
               hint=(0, 0, 1))
parts.append(uv_box(lift))
CART_Z0 = Z_RT + 0.42
cart_mid = STYLUS - DH * 0.95
cart = S.prism("cartridge", S.rounded_rect(2.5 * cm, 1.65 * cm, 0.18 * cm, segs=3),
               v3(cart_mid, CART_Z0), v3(cart_mid, PLATE_Z0 + 0.03), BLACK, up=(DH.x, DH.y, 0))
S.bevel(cart, 0.06 * cm, segments=2, angle=30)
parts.append(uv_box(cart))
cant = S.cylinder("cantilever", v3(STYLUS - DH * 0.55, CART_Z0 + 0.12), v3(STYLUS, Z_RT + 0.015),
                  0.035 * cm, ARM, segs=8, r2=0.02 * cm)
parts.append(uv_box(cant))

# arm rest (where the arm parks, along +X from the pivot) and cue lever
REST = PIV + Vector((7.4, 1.0))
parts.append(uv_box(lathe_at("rest_base", [(0, -0.05), (0.75, -0.05), (0.75, 0.2), (0.68, 0.27), (0, 0.27)],
                             [BLACK], v3(REST, ZT), segs=32)))
rest_top = Z_ARM - 0.45
parts.append(uv_box(S.cylinder("rest_post", v3(REST, ZT + 0.2), v3(REST, rest_top), 0.28 * cm, ARM, segs=20)))
cradle_parts = [((-0.45, -0.75, -0.25), (0.45, 0.75, 0.05)), ((-0.45, -0.75, 0.05), (0.45, -0.42, 0.55)),
                ((-0.45, 0.42, 0.05), (0.45, 0.75, 0.55))]
for i, (lo, hi) in enumerate(cradle_parts):
    c = S.box(f"cradle_{i}", ((REST.x + lo[0]) * cm, (REST.y + lo[1]) * cm, (rest_top + lo[2]) * cm),
              ((REST.x + hi[0]) * cm, (REST.y + hi[1]) * cm, (rest_top + hi[2]) * cm), BLACK)
    S.bevel(c, 0.06 * cm, segments=2, angle=30)
    parts.append(uv_box(c))
CUE = REST + Vector((-2.4, 1.7))
parts.append(uv_box(lathe_at("cue_body", [(0, -0.05), (0.55, -0.05), (0.55, 1.9), (0.5, 2.0), (0.42, 2.05),
                                         (0, 2.05)], [ARM], v3(CUE, ZT), segs=28)))
lever_end = CUE + Vector((2.0, 0.6))
parts.append(uv_box(S.cylinder("cue_lever", v3(CUE, ZT + 1.75), v3(lever_end, ZT + 1.95), 0.12 * cm, BLACK,
                               segs=12)))
parts.append(uv_box(lathe_at("cue_knob", [(0, -0.3), (0.22, -0.3), (0.3, -0.2), (0.3, 0.2), (0.22, 0.3), (0, 0.3)],
                             [BLACK], None, segs=16,
                             axis=(v3(lever_end - Vector((2.0, 0.6)).normalized() * 0.15, ZT + 1.94),
                                   v3(lever_end + Vector((2.0, 0.6)).normalized() * 0.45, ZT + 1.99)))))

# --------------------------------------------------------------------------- speed knob (front left) and 33/45 selector (front right)
KNOB = Vector((PX / 2 - 4.2, -PY / 2 + 3.6))
parts.append(uv_box(lathe_at("knob_ring", [(0, -0.05), (1.95, -0.05), (1.95, 0.08), (1.9, 0.14), (0, 0.14)],
                             [BLACK], v3(KNOB, ZT), segs=56)))
knurl = S.prism("knob_knurl", S.knurl_outline(1.45 * cm, teeth=36, depth=0.035),
                v3(KNOB, ZT + 0.22), v3(KNOB, ZT + 1.45), ARM)
S.bevel(knurl, 0.03 * cm, segments=1, angle=50)
parts.append(uv_box(knurl))
parts.append(uv_box(lathe_at("knob_skirt", [(0, 0.12), (1.38, 0.12), (1.5, 0.18), (1.5, 0.30), (0, 0.30)],
                             [ARM], v3(KNOB, ZT), segs=56)))
parts.append(uv_box(lathe_at("knob_cap", [(0, 1.40), (1.42, 1.40), (1.42, 1.52), (1.34, 1.62), (1.15, 1.64),
                                         (1.05, 1.60), (0, 1.57)], [ARM], v3(KNOB, ZT), segs=56)))
ind = S.box("knob_mark", ((KNOB.x + 0.55) * cm, (KNOB.y - 0.07) * cm, (ZT + 1.60) * cm),
            ((KNOB.x + 1.18) * cm, (KNOB.y + 0.07) * cm, (ZT + 1.66) * cm), BLACK)
S.bevel(ind, 0.015 * cm, segments=1, angle=30)
parts.append(uv_box(ind))

SEL = Vector((PX / 2 - 3.4, PY / 2 - 4.6))
sel_plate = S.prism("sel_plate", S.rounded_rect(1.9 * cm, 4.2 * cm, 0.6 * cm, segs=4),
                    v3(SEL, ZT - 0.05), v3(SEL, ZT + 0.22), BLACK, up=(1, 0, 0))
S.bevel(sel_plate, 0.06 * cm, segments=2, angle=30)
parts.append(uv_box(sel_plate))
for i, (dy, h) in enumerate(((-1.0, 0.55), (1.0, 0.32))):          # 33 up, 45 pressed in
    parts.append(uv_box(lathe_at(f"sel_btn{i}", [(0, 0.1), (0.58, 0.1), (0.58, h - 0.06), (0.53, h), (0, h - 0.02)],
                                 [ARM], v3(SEL + Vector((0, dy)), ZT + 0.12), segs=32)))

# --------------------------------------------------------------------------- finish: join, origin, normals, export, previews


def finish(name, parts, sharp_angle=40):
    ob = S.join(name, parts)
    S.set_origin(ob, (0, 0, 0))
    S.tidy(ob, sharp_angle)
    weighted_normals(ob)
    os.makedirs(args.out, exist_ok=True)
    fbx = os.path.join(args.out, name + ".fbx")
    S.export_fbx(ob, fbx)
    lo, hi = S.bbox(ob)
    print("=" * 60)
    print(f"{name}: exported {fbx}")
    print(f"{name}: materials {[m.name for m in ob.data.materials]}")
    print(f"{name}: triangles {S.tri_count(ob)}")
    print(f"{name}: bbox cm  X {lo.x*100:.1f}..{hi.x*100:.1f}  Y {lo.y*100:.1f}..{hi.y*100:.1f}"
          f"  Z {lo.z*100:.1f}..{hi.z*100:.1f}")
    print("=" * 60)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(args.out, name + ".blend"), compress=True)
    return ob


ob = finish("turntable", parts)

if not args.no_render:
    S.render_preview(ob, os.path.join(args.out, "turntable.png"), (1.0, 0.85, 0.85), args.samples, lens=60)
    clear_preview()
    S.render_preview(ob, os.path.join(args.out, "turntable_front.png"), (1.0, 0.0, 0.12), args.samples, lens=70)
    clear_preview()
    # close-up of the tonearm and the record: frame a proxy around headshell, arm and pivot
    pts = [v3(STYLUS, Z_RT), v3(PIV, ZT), v3(PIV - D * 6.6, Z_ARM + 1.6), v3(STYLUS + side * 2.5, Z_RT),
           v3(PC + (STYLUS - PC) * 0.7, Z_RT)]
    bm = bmesh.new()
    for p in pts:
        bm.verts.new(p)
    proxy = S.obj_from_bm(bm, "_proxy", BLACK)
    proxy.hide_render = True
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=2.0, matrix=Matrix.Translation((0, 0, -0.0005)))
    S.obj_from_bm(bm, "_table", S.material("_PreviewFloor", (0.18, 0.18, 0.18), 0.8))
    S.render_preview(proxy, os.path.join(args.out, "turntable_close.png"), (0.75, -0.55, 0.55), args.samples,
                     lens=85, margin=1.05, floor=False)
