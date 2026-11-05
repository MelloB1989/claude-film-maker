"""rug — a cream wool rug under the presenter: 260 x 180 cm (long side along studio Y), 1.6 cm thick.

Centred at studio (x = -20, y = +10), i.e. Blender (-0.20, -0.10). Softly rounded edges (7 mm round
on top, 4 mm underneath), 2 cm corner radius, a pile that is not quite flat (about +-0.8 mm over
tens of cm) and an edge that wanders by a millimetre or so, as a bound wool rug does. It rests
0.3 mm above the floor (no coplanar faces). Slot M_Rug; world-scale UVs (1 UV = 1 m), the top
projected from above and the edge unfolded outwards from it, so the pile runs on without a seam.
Origin: the world origin.

    blender -b --factory-startup -P rug.py -- --out out
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402

import _studio as S  # noqa: E402
import _room_common as R  # noqa: E402

NAME = "rug"
args = S.parse_args(__file__)
S.reset_scene()
RUG = R.slot("M_Rug")

CX, CY = -0.20, -0.10       # centre (Blender)
HX, HY = 0.90, 1.30         # half sizes: 180 along X, 260 along Y
RC = 0.020                  # corner radius
Z0, TH = 0.0003, 0.016      # underside, thickness
RT, RB = 0.007, 0.004       # edge rounds, top and bottom
STEP = 0.04                 # top grid spacing


def pile(x, y):
    """The pile's height above nominal: a millimetre of slow unevenness."""
    return 0.0008 * (0.55 * math.sin(2.3 * x + 0.4) * math.sin(1.7 * y + 1.1)
                     + 0.30 * math.sin(5.1 * x - 3.3 * y + 2.0)
                     + 0.15 * math.sin(9.7 * x + 7.9 * y))


def edge_wander(s):
    """The bound edge is not ruler-straight: about +-1 mm along the perimeter (s in metres)."""
    return 0.0011 * math.sin(2 * math.pi * s / 0.9 + 0.3) + 0.0005 * math.sin(2 * math.pi * s / 0.33 + 1.9)


# --- the top grid: rows at x, each spanning the rounded outline inset by RT
hx, hy, rc = HX - RT, HY - RT, RC - RT


def half_width(x):
    ax = abs(x)
    if ax <= hx - rc:
        return hy
    d = min(rc, ax - (hx - rc))
    return hy - rc + math.sqrt(max(0.0, rc * rc - d * d))


n_mid = int(round(2 * (hx - rc) / STEP))
xs_mid = [-(hx - rc) + 2 * (hx - rc) * k / n_mid for k in range(n_mid + 1)]
corner = [(hx - rc) + rc * math.sin(0.5 * math.pi * k / 4) for k in range(1, 5)]
xs = [-c for c in reversed(corner)] + xs_mid + corner
ncol = int(round(2 * hy / STEP)) + 1

bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")
uv_of = {}


def vert(co, uv):
    v = bm.verts.new(co)
    uv_of[v] = uv
    return v


def face(vs):
    f = bm.faces.new(vs)
    for lp in f.loops:
        lp[uvl].uv = uv_of[lp.vert]
    return f


grid = []
for x in xs:
    w = half_width(x)
    row = []
    for i in range(ncol):
        y = -w + 2 * w * i / (ncol - 1)
        row.append([x, y])
    grid.append(row)

# boundary loop of the grid (counter-clockwise from above): first row, last column, last row, first column
nr = len(grid)
loop_idx = ([(0, i) for i in range(ncol - 1, -1, -1)] + [(r, 0) for r in range(1, nr)]
            + [(nr - 1, i) for i in range(1, ncol)] + [(r, ncol - 1) for r in range(nr - 2, 0, -1)])
pts = [Vector(grid[r][i]) for r, i in loop_idx]
nb = len(pts)
normals, perim = [], [0.0]
for k in range(nb):
    t = (pts[(k + 1) % nb] - pts[k - 1]).normalized()
    n = Vector((t.y, -t.x))
    if n.dot(pts[k]) < 0:
        n = -n
    normals.append(n)
for k in range(1, nb):
    perim.append(perim[-1] + (pts[k] - pts[k - 1]).length)
wander = [edge_wander(s) for s in perim]
for k, (r, i) in enumerate(loop_idx):
    grid[r][i][0] += normals[k].x * wander[k]
    grid[r][i][1] += normals[k].y * wander[k]

top = [[vert((CX + x, CY + y, Z0 + TH + pile(x, y)), (CX + x, CY + y)) for x, y in row] for row in grid]
for r in range(nr - 1):
    for i in range(ncol - 1):
        face((top[r][i], top[r][i + 1], top[r + 1][i + 1], top[r + 1][i]))

# --- the rounded edge, swept round the boundary: (offset outwards, height) from the top's edge
prof = [(RT * math.sin(math.radians(a)), TH - RT + RT * math.cos(math.radians(a))) for a in (22.5, 45, 67.5, 90)]
prof += [(RT - RB + RB * math.cos(math.radians(a)), RB + RB * math.sin(math.radians(a))) for a in (-30, -60, -90)]
arc = []
prev = (0.0, TH)
acc = 0.0
for o, z in prof:
    acc += math.hypot(o - prev[0], z - prev[1])
    arc.append(acc)
    prev = (o, z)

rings = [[top[r][i] for r, i in loop_idx]]
for (o, z), a in zip(prof, arc):
    ring = []
    for k, (r, i) in enumerate(loop_idx):
        x, y = grid[r][i]
        p = Vector((x, y)) + normals[k] * o
        uvp = Vector((x, y)) + normals[k] * a
        lift = pile(x, y) * (z / TH)
        ring.append(vert((CX + p.x, CY + p.y, Z0 + z + lift), (CX + uvp.x, CY + uvp.y)))
    rings.append(ring)
for a, b in zip(rings[:-1], rings[1:]):
    for k in range(nb):
        k2 = (k + 1) % nb
        face((a[k], a[k2], b[k2], b[k]))

# --- the underside: one flat convex n-gon, triangulated
under = face(list(reversed(rings[-1])))
for lp in under.loops:
    lp[uvl].uv = (lp.vert.co.x, lp.vert.co.y)
bmesh.ops.triangulate(bm, faces=[under], quad_method="BEAUTY", ngon_method="BEAUTY")
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
ob = S.obj_from_bm(bm, NAME, RUG)
S.set_origin(ob, (0, 0, 0))
S.tidy(ob, sharp_angle=60)

os.makedirs(args.out, exist_ok=True)
fbx = os.path.join(args.out, NAME + ".fbx")
S.export_fbx(ob, fbx)
lo, hi = S.bbox(ob)
print("=" * 60)
print(f"{NAME}: materials {[m.name for m in ob.data.materials]}")
print(f"{NAME}: triangles {S.tri_count(ob)}")
print(f"{NAME}: bbox cm  X {lo.x*100:.2f}..{hi.x*100:.2f}  Y {lo.y*100:.2f}..{hi.y*100:.2f}"
      f"  Z {lo.z*100:.2f}..{hi.z*100:.2f}")
print("=" * 60)
if not args.no_render:
    for m in ob.data.materials:
        R.dress(m.name, m)
    R.prop_previews(ob, args.out, NAME, (1.0, 0.75, 0.55), (1.0, 0.0, 0.12), args.samples, lens=50, exposure=-1.3)
    R.closeup(ob, os.path.join(args.out, NAME + "_close.png"), (CX + HX + 0.35, CY + HY + 0.25, 0.30),
              (CX + HX - 0.05, CY + HY - 0.08, 0.0), 40, args.samples, exposure=-1.3)
