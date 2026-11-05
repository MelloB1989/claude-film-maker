"""mic_boom — a broadcast dynamic microphone on a desk boom arm, posed as used on camera.

Original design. The mic: a ~19 cm, 6 cm diameter matte-black body with a foam windscreen over the
front third, in a U yoke with two side knobs. The boom: a vertical mast on a desk clamp, then two
articulated sections (~40 cm each) of two parallel tubes with a spring along each side.

Origin: the desk clamp, at the underside of its top jaw, i.e. on the desk surface below the mast.
The clamp's lower jaw and screw hang below z = 0 (under the desk top). The arm reaches +X and up;
the mic hangs ~45 cm forward and ~35 cm up, pointing back toward -X and ~15 degrees down.

    blender -b --factory-startup -P films/host-studio/props/mic_boom.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

args = S.parse_args(__file__)
S.reset_scene()

BLACK = S.material("M_MatteBlack", (0.012, 0.012, 0.013), 0.6)
FOAM = S.material("M_Foam", (0.024, 0.024, 0.026), 1.0, specular=0.15)
METAL = S.material("M_Metal", (0.17, 0.175, 0.185), 0.38, metallic=1.0)    # dark gunmetal
SPRING = S.material("M_Spring", (0.62, 0.62, 0.63), 0.3, metallic=1.0)

parts = []
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))

# ---------------------------------------------------------------- pose
MIC_C = Vector((0.45, 0.0, 0.35))       # centre of the mic body (its pivot in the yoke)
MIC_TILT = math.radians(15)             # nose down
MIC_DIR = Vector((-math.cos(MIC_TILT), 0.0, -math.sin(MIC_TILT)))   # where the mic points
YOKE_TOP = 0.060                        # yoke crown above the pivot
J0 = Vector((0.0, 0.0, 0.165))          # top of the mast
J2 = MIC_C + Vector((0, 0, YOKE_TOP + 0.048))   # boom tip, above the yoke
L1 = L2 = 0.40

# elbow J1: the two sections meet, elbow up
d = J2 - J0
dist = d.length
a = (L1 * L1 - L2 * L2 + dist * dist) / (2 * dist)
h = math.sqrt(L1 * L1 - a * a)
u = d.normalized()
perp = Vector((-u.z, 0.0, u.x))          # in the XZ plane, pointing up-back
J1 = J0 + u * a + perp * h

# ---------------------------------------------------------------- desk clamp (top jaw underside at z = 0)
cl = [
    S.box("clamp_top", (-0.036, -0.025, 0.0), (0.046, 0.025, 0.012), METAL),
    S.box("clamp_spine", (-0.036, -0.022, -0.064), (-0.024, 0.022, 0.010), METAL),
    S.box("clamp_low", (-0.030, -0.0215, -0.0635), (0.036, 0.0215, -0.053), METAL),
]
for b in cl:
    S.bevel(b, 0.0025, segments=2)
parts += cl
parts.append(S.box("clamp_pad_top", (-0.022, -0.023, -0.003), (0.044, 0.023, 0.0), BLACK))
parts.append(S.cylinder("clamp_screw", (0.020, 0, -0.092), (0.020, 0, -0.042), 0.0045, METAL, segs=16))
parts.append(S.cylinder("clamp_pad", (0.020, 0, -0.045), (0.020, 0, -0.040), 0.013, BLACK, segs=24))
parts.append(S.prism("clamp_handle", S.knurl_outline(0.017, teeth=14, depth=0.12),
                     (0.020, 0, -0.100), (0.020, 0, -0.088), BLACK))

# ---------------------------------------------------------------- mast
parts.append(S.cylinder("mast_collar", (0, 0, 0.012), (0, 0, 0.034), 0.016, BLACK, segs=32))
parts.append(S.cylinder("mast", (0, 0, 0.030), J0, 0.0105, METAL, segs=24))
parts.append(S.cylinder("mast_head", J0 - Z * 0.03, J0, 0.0135, BLACK, segs=24))

# ---------------------------------------------------------------- joints
HUB_R, HUB_W = 0.017, 0.017


def joint(name, p):
    out = [S.cylinder(name + "_hub", p - Y * HUB_W, p + Y * HUB_W, HUB_R, BLACK, segs=32)]
    out.append(S.cylinder(name + "_stem", p + Y * HUB_W, p + Y * (HUB_W + 0.006), 0.005, METAL, segs=12))
    out.append(S.prism(name + "_knob", S.knurl_outline(0.0155, teeth=18, depth=0.07),
                       p + Y * (HUB_W + 0.005), p + Y * (HUB_W + 0.018), BLACK))
    out.append(S.cylinder(name + "_nut", p - Y * HUB_W, p - Y * (HUB_W + 0.005), 0.010, METAL, segs=6))
    return out


for name, p in (("j0", J0), ("j1", J1), ("j2", J2)):
    parts += joint(name, p)

# ---------------------------------------------------------------- sections: two parallel tubes + a spring each side
TUBE_R, TUBE_OFF = 0.0055, 0.011
SPRING_Y, COIL_R, WIRE_R, PITCH = 0.027, 0.0058, 0.0011, 0.0042


def section(name, pa, pb):
    out = []
    dd = (pb - pa).normalized()
    n = Vector((-dd.z, 0.0, dd.x))
    for s in (-1, 1):
        out.append(S.cylinder(f"{name}_tube{s}", pa + n * TUBE_OFF * s, pb + n * TUBE_OFF * s,
                              TUBE_R, METAL, segs=16))
    length = (pb - pa).length
    pin_a, pin_b = pa + dd * 0.035, pb - dd * 0.035
    for pin in (pin_a, pin_b):
        out.append(S.cylinder(f"{name}_pin", pin - Y * (SPRING_Y + 0.006), pin + Y * (SPRING_Y + 0.006),
                              0.0024, METAL, segs=10))
    sa, sb = pa + dd * 0.12 * length, pb - dd * 0.12 * length
    turns = (sb - sa).length / PITCH
    steps = int(turns * 10)
    e2 = dd.cross(Y)
    for side in (-1, 1):
        off = Y * SPRING_Y * side
        coil = []
        for i in range(steps + 1):
            t = i / steps
            ang = 2 * math.pi * turns * t
            coil.append(sa + (sb - sa) * t + off + (Y * math.cos(ang) + e2 * math.sin(ang)) * COIL_R)
        # straight hooks from the coil ends along the axis to the pins
        path = [pin_a + off, sa + off - dd * 0.004, coil[0]] + coil[1:-1] + [coil[-1], sb + off + dd * 0.004, pin_b + off]
        out.append(S.sweep(f"{name}_spring{side}", path, S.circle_outline(WIRE_R, 6), SPRING, hint=Y))
    return out


parts += section("arm1", J0, J1)
parts += section("arm2", J1, J2)

# ---------------------------------------------------------------- drop rod and yoke
yoke_top = MIC_C + Z * YOKE_TOP
parts.append(S.cylinder("drop_rod", J2, yoke_top + Z * 0.008, 0.0048, METAL, segs=16))
parts.append(S.cylinder("swivel", J2 - Z * 0.034, J2 - Z * 0.022, 0.0095, BLACK, segs=24))
parts.append(S.cylinder("yoke_mount", yoke_top - Z * 0.002, yoke_top + Z * 0.010, 0.0085, BLACK, segs=24))

ARM_Y, CR = 0.041, 0.018
yoke_pts = []
for k in range(5):                                    # left arm, going up
    yoke_pts.append((-ARM_Y, -0.006 + (YOKE_TOP - CR + 0.006) * k / 4))
for k in range(1, 9):                                 # left corner
    a_ = math.pi - (math.pi / 2) * k / 8
    yoke_pts.append((-ARM_Y + CR + CR * math.cos(a_), YOKE_TOP - CR + CR * math.sin(a_)))
yoke_pts += [(y, z) for (y, z) in [(-ARM_Y + CR + 0.01, YOKE_TOP), (ARM_Y - CR - 0.01, YOKE_TOP)]]
for k in range(0, 8):                                 # right corner
    a_ = (math.pi / 2) - (math.pi / 2) * k / 8
    yoke_pts.append((ARM_Y - CR + CR * math.cos(a_), YOKE_TOP - CR + CR * math.sin(a_)))
for k in range(5):                                    # right arm, going down
    yoke_pts.append((ARM_Y, YOKE_TOP - CR - (YOKE_TOP - CR + 0.006) * k / 4))
yoke_path = [MIC_C + Vector((0, y, z)) for (y, z) in yoke_pts]
strap = []
for k in range(16):                                   # rounded flat strap, 14 x 4.4 mm
    t = 2 * math.pi * k / 16
    c, s_ = math.cos(t), math.sin(t)
    strap.append((0.007 * math.copysign(abs(c) ** 0.5, c), 0.0022 * math.copysign(abs(s_) ** 0.5, s_)))
parts.append(S.sweep("yoke", yoke_path, strap, METAL, hint=X))

for side in (-1, 1):
    parts.append(S.cylinder(f"yoke_spacer{side}", MIC_C + Y * 0.027 * side, MIC_C + Y * (ARM_Y + 0.001) * side,
                            0.0065, METAL, segs=16))
    parts.append(S.prism(f"yoke_knob{side}", S.knurl_outline(0.0125, teeth=10, depth=0.15),
                         MIC_C + Y * (ARM_Y + 0.002) * side, MIC_C + Y * (ARM_Y + 0.015) * side, BLACK))

# ---------------------------------------------------------------- microphone (built along +Z, then aimed)
mic_m = Matrix.Translation(MIC_C) @ MIC_DIR.to_track_quat("Z", "Y").to_matrix().to_4x4()
body_profile = [
    (0.0, -0.090), (0.0265, -0.090), (0.0292, -0.087), (0.0300, -0.082),
    (0.0300, 0.028), (0.0285, 0.040), (0.0, 0.040)]
parts.append(S.lathe("mic_body", body_profile, [BLACK], segs=48, matrix=mic_m))
rear_profile = [
    (0.0, -0.0965), (0.0110, -0.0965), (0.0112, -0.0950),   # XLR recess rim
    (0.0, -0.0950)]
parts.append(S.lathe("mic_xlr", rear_profile, [BLACK], segs=32, matrix=mic_m @ Matrix.Translation((0, 0, -0.0005))))
cap_profile = [
    (0.0, -0.0955), (0.0255, -0.0955), (0.0292, -0.0935), (0.0303, -0.0905),
    (0.0303, -0.0840), (0.0296, -0.0835), (0.0, -0.0835)]
parts.append(S.lathe("mic_endcap", cap_profile, [METAL], segs=48, matrix=mic_m))
trim_profile = [(0.0, 0.024), (0.0306, 0.024), (0.0308, 0.026), (0.0308, 0.031), (0.0, 0.031)]
parts.append(S.lathe("mic_trim", trim_profile, [METAL], segs=48, matrix=mic_m))
foam_profile = [
    (0.0, 0.030), (0.0320, 0.030), (0.0338, 0.034), (0.0344, 0.042), (0.0344, 0.078),
    (0.0338, 0.088), (0.0318, 0.097), (0.0280, 0.104), (0.0215, 0.1095), (0.0130, 0.1125), (0.0, 0.1135)]
parts.append(S.lathe("mic_foam", foam_profile, [FOAM], segs=48, matrix=mic_m))

S.finish("mic_boom", parts, origin=(0, 0, 0), view_dir=(-0.45, -1.0, 0.32), args=args,
         sharp_angle=40, lens=55, floor=False)  # the clamp hangs below the desk
print(f"mic_boom: J0 {tuple(round(c * 100, 1) for c in J0)} J1 {tuple(round(c * 100, 1) for c in J1)} "
      f"J2 {tuple(round(c * 100, 1) for c in J2)} cm; mic centre {tuple(round(c * 100, 1) for c in MIC_C)} cm, "
      f"nose {tuple(round(c * 100, 1) for c in MIC_C + MIC_DIR * 0.1135)} cm")
