"""window — the floor-to-ceiling window unit filling the room's back-wall opening.

Opening (studio): x = -275..-260 (the 15 cm back wall), y = +130..+280, z = 0..285; in Blender
y = -2.80..-1.30 (the FBX import mirrors Y). Origin: the world origin, like room_shell, so both
import aligned.

- plastered reveal lining (M_Wall, so it takes the room's wall material) and a painted sill/threshold
  1.5 cm proud of the wall with a rounded nose (M_WinFrame);
- slim warm-white painted frame: 5 cm members, 7 cm deep, two mullions, a transom at 210 cm,
  glazing beads stepped 5 mm back from the frame face (M_WinFrame);
- one 24 mm double-glazing slab per light (M_Glass).

    blender -b --factory-startup -P window.py -- --out out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402

import _studio as S  # noqa: E402
import _room_common as R  # noqa: E402

NAME = "window"
args = S.parse_args(__file__)
S.reset_scene()

WALLM = R.slot("M_Wall")
FRAME = R.slot("M_WinFrame")
GLASS = R.slot("M_Glass")

XO = R.X_BACK - R.WALL      # outside face of the wall, -2.75
XI = R.X_BACK               # inside face, -2.60
Y0, Y1 = R.WIN_Y0, R.WIN_Y1
ZT = R.WIN_Z1
G = 0.0001                  # hairline between butting members (no welded bevels)
E = 0.0005                  # tucked into the shell by 0.5 mm: no slit, no coplanar faces

LINING = 0.015              # plaster lining of the reveal
SILL_H = 0.025              # sill / threshold height
SILL_PROUD = 0.015          # proud of the inside wall face
FW = 0.05                   # frame member face width
FX0, FX1 = -2.715, -2.645   # frame depth: 7 cm, set towards the outside of the reveal
TRANSOM_Z = 2.10
GL_X0, GL_X1 = -2.692, -2.668   # 24 mm glazing unit
BEAD_W = 0.015
BEAD_RECESS = 0.005


def rect_ring(name, y0, y1, z0, z1, w, x0, x1, mat, bev=0.002, segs=2):
    """A rectangular frame (outer y0..y1, z0..z1, member width w) running x0..x1 in depth."""
    bm = bmesh.new()
    loops = []
    for x in (x0, x1):
        outer = [bm.verts.new((x, y, z)) for y, z in ((y0, z0), (y1, z0), (y1, z1), (y0, z1))]
        inner = [bm.verts.new((x, y, z)) for y, z in ((y0 + w, z0 + w), (y1 - w, z0 + w),
                                                      (y1 - w, z1 - w), (y0 + w, z1 - w))]
        loops.append((outer, inner))
    (o0, i0), (o1, i1) = loops
    for k in range(4):
        j = (k + 1) % 4
        bm.faces.new((o0[k], o0[j], i0[j], i0[k]))      # face at x0
        bm.faces.new((o1[k], i1[k], i1[j], o1[j]))      # face at x1
        bm.faces.new((o0[k], o1[k], o1[j], o0[j]))      # outside
        bm.faces.new((i0[k], i0[j], i1[j], i1[k]))      # inside of the opening
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = S.obj_from_bm(bm, name, mat)
    return S.bevel(ob, bev, segs, angle=30)


def bbox_part(name, lo, hi, mat, bev=0.002, segs=2):
    return S.bevel(S.box(name, lo, hi, mat), bev, segs, angle=30)


parts = []

# --- reveal lining and sill
zs = SILL_H
parts.append(bbox_part("lining_l", (XO - E, Y0 - E, zs), (XI - E, Y0 + LINING, ZT + E), WALLM, 0.0015))
parts.append(bbox_part("lining_r", (XO - E, Y1 - LINING, zs), (XI - E, Y1 + E, ZT + E), WALLM, 0.0015))
parts.append(bbox_part("lining_head", (XO - E, Y0 + LINING + G, ZT - LINING), (XI - E, Y1 - LINING - G, ZT + E),
                       WALLM, 0.0015))
# sill: full depth of the reveal, 1.5 cm proud with a softly rounded nose; tucked 0.5 mm into the floor
sill = S.box("sill", (XO - E, Y0 - E, -E), (XI + SILL_PROUD, Y1 + E, SILL_H), FRAME)
S.bevel(sill, 0.006, 4, angle=30)
parts.append(sill)

# --- frame
fy0, fy1 = Y0 + LINING, Y1 - LINING
fz0, fz1 = SILL_H, ZT - LINING
parts.append(rect_ring("frame", fy0, fy1, fz0, fz1, FW, FX0, FX1, FRAME))

iy0, iy1 = fy0 + FW, fy1 - FW            # inside of the frame
iz0, iz1 = fz0 + FW, fz1 - FW
pane = (iy1 - iy0 - 2 * FW) / 3.0
cols = [(iy0 + k * (pane + FW), iy0 + k * (pane + FW) + pane) for k in range(3)]
for k in (1, 2):
    y = cols[k][0]
    # 0.1 mm short of the frame so the bevels meet without welding into non-manifold edges
    parts.append(bbox_part(f"mullion{k}", (FX0, y - FW, iz0 + G), (FX1, y, iz1 - G), FRAME))
rows = [(iz0, TRANSOM_Z - FW / 2), (TRANSOM_Z + FW / 2, iz1)]
for k, (a, b) in enumerate(cols):
    parts.append(bbox_part(f"transom{k}", (FX0, a + G, rows[0][1]), (FX1, b - G, rows[1][0]), FRAME))

# --- glazing: a bead ring each side of every light, the glass slab between
for k, (a, b) in enumerate(cols):
    for j, (c, d) in enumerate(rows):
        parts.append(rect_ring(f"bead_in{k}{j}", a, b, c, d, BEAD_W, GL_X1 + 0.0005, FX1 - BEAD_RECESS,
                               FRAME, bev=0.001))
        parts.append(rect_ring(f"bead_out{k}{j}", a, b, c, d, BEAD_W, FX0 + BEAD_RECESS, GL_X0 - 0.0005,
                               FRAME, bev=0.001))
        g = 0.004   # the glass runs 11 mm under the beads, 4 mm short of the frame
        parts.append(bbox_part(f"glass{k}{j}", (GL_X0, a + g, c + g), (GL_X1, b - g, d - g), GLASS, 0.001, 1))

ob = S.join(NAME, parts)
S.set_origin(ob, (0, 0, 0))
S.tidy(ob, sharp_angle=40)
R.box_uv(ob)
os.makedirs(args.out, exist_ok=True)
fbx = os.path.join(args.out, NAME + ".fbx")
S.export_fbx(ob, fbx)
lo, hi = S.bbox(ob)
print("=" * 60)
print(f"{NAME}: materials {[m.name for m in ob.data.materials]}")
print(f"{NAME}: triangles {S.tri_count(ob)}")
print(f"{NAME}: bbox cm  X {lo.x*100:.2f}..{hi.x*100:.2f}  Y {lo.y*100:.2f}..{hi.y*100:.2f}"
      f"  Z {lo.z*100:.2f}..{hi.z*100:.2f}")
print(f"{NAME}: lights {pane*100:.1f} cm wide; lower {(rows[0][1]-rows[0][0])*100:.1f} cm,"
      f" upper {(rows[1][1]-rows[1][0])*100:.1f} cm tall")
print("=" * 60)
if not args.no_render:
    for m in ob.data.materials:
        R.dress(m.name, m)
    R.prop_previews(ob, args.out, NAME, (1.0, 0.75, 0.55), (1.0, 0.0, 0.0), args.samples, lens=50)
