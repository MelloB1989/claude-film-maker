"""keyboard — a 75% mechanical keyboard, ~32 x 13 cm, slight typing angle, front edge toward +X.

Dark-grey aluminium case, individual keycaps: off-white alphas, muted orange Escape and Enter.
Origin: bottom centre of the case.

    blender -b --factory-startup -P films/host-studio/props/keyboard.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

args = S.parse_args(__file__)
S.reset_scene()

CASE = S.material("M_Case", (0.12, 0.125, 0.13), 0.55, metallic=0.35)      # anodised dark grey
PLATE = S.material("M_Plate", (0.015, 0.015, 0.016), 0.6)                    # plate/switches seen between caps
KEY = S.material("M_Keycap", (0.68, 0.65, 0.58), 0.55)                      # off-white
ACCENT = S.material("M_KeycapAccent", (0.62, 0.19, 0.045), 0.55)             # muted orange

cm = 0.01
# Built with the width along X and the front edge at -Y; turned to face +X at the end.
W, D = 32.0 * cm, 13.2 * cm
H_FRONT, H_BACK = 1.9 * cm, 3.1 * cm
BORDER = 0.7 * cm
WELL = 0.7 * cm
U = 1.9 * cm                    # key pitch
ROW_GAP = 0.15 * U              # gap under the function row
TILT = math.atan2(H_BACK - H_FRONT, D)

# ---------------------------------------------------------------- case: a wedge with a key well
bm = bmesh.new()
v = [bm.verts.new(p) for p in (
    (-W / 2, -D / 2, 0), (W / 2, -D / 2, 0), (W / 2, D / 2, 0), (-W / 2, D / 2, 0),
    (-W / 2, -D / 2, H_FRONT), (W / 2, -D / 2, H_FRONT), (W / 2, D / 2, H_BACK), (-W / 2, D / 2, H_BACK))]
bm.faces.new((v[3], v[2], v[1], v[0]))
bm.faces.new((v[0], v[1], v[5], v[4]))
bm.faces.new((v[1], v[2], v[6], v[5]))
bm.faces.new((v[2], v[3], v[7], v[6]))
bm.faces.new((v[3], v[0], v[4], v[7]))
top = bm.faces.new((v[4], v[5], v[6], v[7]))
bm.normal_update()
normal = top.normal.copy()
res = bmesh.ops.inset_individual(bm, faces=[top], thickness=BORDER, depth=0.0)
bmesh.ops.translate(bm, verts=list(top.verts), vec=-normal * WELL)
top.material_index = 1
plate_centre = top.calc_center_median()
case = S.obj_from_bm(bm, "case", CASE)
case.data.materials.append(PLATE)
S.bevel(case, 0.14 * cm, segments=3, angle=30)

# ---------------------------------------------------------------- keycaps
# 75% layout, back row first; (width in units, accent?)
rows = [
    [(1, True)] + [(1, False)] * 15,                                  # Esc, F1-F12, ...
    [(1, False)] * 13 + [(2, False), (1, False)],                     # number row, Backspace
    [(1.5, False)] + [(1, False)] * 12 + [(1.5, False), (1, False)],   # Tab ... \
    [(1.75, False)] + [(1, False)] * 11 + [(2.25, True), (1, False)],  # Caps ... Enter
    [(2.25, False)] + [(1, False)] * 10 + [(1.75, False), (1, False), (1, False)],
    [(1.25, False)] * 3 + [(6.25, False)] + [(1, False)] * 6,
]
row_heights = [0.82, 0.86, 0.80, 0.76, 0.79, 0.79]   # gentle sculpted profile, cm
GAP = 0.12 * cm        # between caps at the base
TAPER = 0.22 * cm      # each side, base to top
LIFT = 0.42 * cm       # switch height: cap base above the plate

# plate frame: x across, y up the slope, z out of the plate
ax = Vector((1, 0, 0))
ay = Vector((0, math.cos(TILT), math.sin(TILT)))
az = ax.cross(ay)
plate_m = Matrix((
    (ax.x, ay.x, az.x, plate_centre.x),
    (ax.y, ay.y, az.y, plate_centre.y),
    (ax.z, ay.z, az.z, plate_centre.z),
    (0, 0, 0, 1)))

total_depth = 6 * U + ROW_GAP
keys = []
for r, row in enumerate(rows):
    y_top = total_depth / 2 - r * U - (ROW_GAP if r > 0 else 0)
    yc = y_top - U / 2
    x = -8 * U
    h = row_heights[r] * cm
    for i, (w, accent) in enumerate(row):
        xc = x + w * U / 2
        x += w * U
        bw, bd = w * U - GAP, U - GAP
        tw, td = bw - 2 * TAPER, bd - 2 * TAPER
        back = 0.06 * cm   # tops lean back slightly, like real caps
        bmk = bmesh.new()
        base = [bmk.verts.new((xc + sx * bw / 2, yc + sy * bd / 2, LIFT))
                for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        topv = [bmk.verts.new((xc + sx * tw / 2, yc + back + sy * td / 2, LIFT + h))
                for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        bmk.faces.new(list(reversed(base)))
        bmk.faces.new(topv)
        for k in range(4):
            k2 = (k + 1) % 4
            bmk.faces.new((base[k], base[k2], topv[k2], topv[k]))
        bmk.transform(plate_m)
        cap = S.obj_from_bm(bmk, f"key_{r}_{i}", ACCENT if accent else KEY)
        S.bevel(cap, 0.09 * cm, segments=2, angle=30)
        keys.append(cap)

# Front edge to +X.
turn = Matrix.Rotation(math.radians(90), 4, "Z")
parts = [case] + keys
for p in parts:
    p.matrix_world = turn @ p.matrix_world

S.finish("keyboard", parts, origin=(0, 0, 0), view_dir=(1.0, -0.75, 0.85), args=args,
         sharp_angle=30, lens=60)
