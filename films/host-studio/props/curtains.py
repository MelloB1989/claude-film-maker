"""curtains — two sheer linen panels on a slim black rod in front of the window.

Rod (M_Rod): studio z = 292, 12 cm in front of the back wall (x = -248), spanning studio
y = +115..+300 (Blender y = -1.15..-3.00), with two wall brackets, end caps, and a clip ring at
every other fold.

Panels (M_Sheer): mostly drawn, covering ~85% of the glass, with a ~22 cm gap left of centre of the
window that narrows towards the hem. Soft vertical folds: regular at the heading (7 cm deep), they
widen and deepen towards the hem (8-13 cm, each fold its own), with small slow wobbles; an A-line
flare; the hem breaks ~1.2 cm above the floor. The cloth is a single sheet with its normals towards
the room (use a two-sided material), but every edge is turned like a real hem: an 8 cm header
folded back at the top, a 5 cm weighted hem at the bottom and 2 cm side hems, each a second layer
1-2.5 mm behind the face, so the edges have thickness and read denser against the light.
UVs: world scale along the cloth, U across (1 UV = 1 m of cloth), V down the drop.
Origin: the world origin.

    blender -b --factory-startup -P curtains.py -- --out out
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import _studio as S  # noqa: E402
import _room_common as R  # noqa: E402

NAME = "curtains"
args = S.parse_args(__file__)
S.reset_scene()
rng = random.Random(11)

SHEER = R.slot("M_Sheer")
ROD = R.slot("M_Rod")

ROD_X = R.X_BACK + 0.12        # 12 cm in front of the back wall
ROD_Z = 2.92
ROD_R = 0.010
ROD_Y0, ROD_Y1 = -3.00, -1.15  # with the end caps
BRACKETS = (-2.955, -1.195)

RING_R, RING_W = 0.0165, 0.0028          # ring centre-line radius, wire radius
RING_Z = ROD_Z + ROD_R - (RING_R - RING_W)   # rings hang on the rod
Z_TOP = 2.884                            # top edge of the cloth (in the clips)
Z_HEM = 0.0125                           # bottom of the hem: 1.2 cm above the floor
DROP = Z_TOP - Z_HEM

HEADER = 0.08        # header folded back at the top
HEM = 0.05           # weighted hem at the bottom
SIDE = 0.02          # side hems
OFF_HEADER, OFF_HEM, OFF_SIDE = 0.0025, 0.0022, 0.0012
PER_HALF = 12        # vertices across each half fold


# ------------------------------------------------------------------ fold field

class Panel:
    """Folds of one panel: zero crossings c_j(t) and depths D_j(t) down the drop (t = 0 top, 1 hem)."""

    def __init__(self, name, y_out, y_in, halves, flare_out, flare_in, d_top, d_hem, seed):
        r = random.Random(seed)
        self.name = name
        self.n = halves
        self.dir = 1.0 if y_in > y_out else -1.0      # from the outer edge to the leading edge
        hw = abs(y_in - y_out) / halves
        # at the top the clips (even crossings) are evenly spaced; the cloth between two clips
        # need not split evenly into its forward and back fold
        top = [y_out + (y_in - y_out) * j / halves for j in range(halves + 1)]
        top = [y + self.dir * (r.uniform(-0.18, 0.18) * hw if j % 2 else r.uniform(-0.002, 0.002))
               if 0 < j < halves else y for j, y in enumerate(top)]
        ho, hi = y_out - self.dir * flare_out, y_in + self.dir * flare_in
        hem = [ho + (hi - ho) * j / halves for j in range(halves + 1)]
        hw2 = abs(hi - ho) / halves
        hem = [y + self.dir * r.uniform(-0.32, 0.32) * hw2 if 0 < j < halves else y for j, y in enumerate(hem)]
        self.top, self.hem = top, hem
        # each crossing drifts on its own way down: a slow wobble that grows with the drop, and a bow
        self.wob = [(r.uniform(0.35, 1.1), r.uniform(0, 2 * math.pi), r.uniform(0.004, 0.011),
                     r.uniform(-0.25, 0.25) * hw) for _ in range(halves + 1)]
        self.d_top = d_top
        self.d_hem = [d_hem * r.uniform(0.68, 1.32) for _ in range(halves)]
        # the outermost and leading half folds relax a little
        self.d_hem[0] *= 0.85
        self.d_hem[-1] *= 0.8
        self.dwob = [(r.uniform(0.5, 1.6), r.uniform(0, 2 * math.pi), r.uniform(0.06, 0.16))
                     for _ in range(halves)]
        self.skew = [r.uniform(-0.32, 0.32) for _ in range(halves)]
        # a third harmonic per fold: some crests round and full, some narrower, changing down the drop
        self.harm = [(r.uniform(-0.10, 0.16), r.uniform(-0.12, 0.12), r.uniform(0.6, 1.5), r.uniform(0, 6.3))
                     for _ in range(halves)]
        # the whole panel undulates gently over a long wavelength, more towards the hem
        self.pan = (r.uniform(0.55, 0.9), r.uniform(0, 2 * math.pi), r.uniform(0.010, 0.016))
        self.lean = r.uniform(-0.006, 0.006)          # the hem a few mm towards or away from the room
        self.first = 1.0 if r.random() < 0.5 else -1.0

    def crossings(self, t):
        e = t ** 1.5
        out = []
        for j in range(self.n + 1):
            f, ph, a, bow = self.wob[j]
            w = a * math.sin(2 * math.pi * f * t + ph) * math.sin(math.pi * 0.5 * min(1.0, t * 1.6))
            w += bow * math.sin(math.pi * t) * self.dir
            if j in (0, self.n):
                w *= 0.6
            out.append(self.top[j] + (self.hem[j] - self.top[j]) * e + w)
        # keep every half fold at least 3 cm wide
        for j in range(1, self.n + 1):
            if (out[j] - out[j - 1]) * self.dir < 0.03:
                out[j] = out[j - 1] + 0.03 * self.dir
        return out

    def depth(self, j, t):
        d = self.d_top + (self.d_hem[j] - self.d_top) * t ** 1.25
        f, ph, a = self.dwob[j]
        d *= 1.0 + a * math.sin(2 * math.pi * f * t + ph) * min(1.0, t * 3)
        return d

    def section(self, t):
        """Cross-section at drop fraction t: list of (y, x) and the unit tangent, PER_HALF per half fold."""
        cs = self.crossings(t)
        xc = ROD_X + self.lean * t ** 2
        pl, pph, pa = self.pan
        y0 = cs[0]
        pts = []
        for j in range(self.n):
            a, b = cs[j], cs[j + 1]
            amp = 0.5 * self.depth(j, t) * self.first * (1 if j % 2 == 0 else -1)
            k = self.skew[j] * (1.0 - 0.4 * t)      # the hem's weight evens the folds out a little
            h0, h1, hf, hph = self.harm[j]
            beta = h0 * min(1.0, t * 4) + h1 * math.sin(2 * math.pi * hf * t + hph) * t
            dense = []
            for i in range(97):
                u = i / 96
                g = u + k * u * (1 - u)
                y = a + (b - a) * u
                x = xc + amp * (math.sin(math.pi * g) + beta * math.sin(3 * math.pi * g)) / (1 + max(0.0, -beta))
                x += pa * t ** 1.3 * math.sin(2 * math.pi * abs(y - y0) / pl + pph)
                dense.append(Vector((y, x)))
            # resample the half fold evenly along its length
            acc = [0.0]
            for i in range(1, len(dense)):
                acc.append(acc[-1] + (dense[i] - dense[i - 1]).length)
            L = acc[-1]
            idx = 0
            for m in range(PER_HALF if j < self.n - 1 else PER_HALF + 1):
                s = L * m / PER_HALF
                while idx < len(acc) - 2 and acc[idx + 1] < s:
                    idx += 1
                f = (s - acc[idx]) / max(1e-12, acc[idx + 1] - acc[idx])
                pts.append(dense[idx].lerp(dense[idx + 1], min(1.0, max(0.0, f))))
        tans = []
        for i in range(len(pts)):
            p0, p1 = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
            tans.append((p1 - p0).normalized())
        return pts, tans


def hem_z(panel, i, ncols):
    """The hem is not perfectly level: a few mm of slow wave along the panel."""
    u = i / (ncols - 1)
    return Z_HEM + 0.0028 * (1 + math.sin(2 * math.pi * (1.3 * u) + (0.7 if panel.dir > 0 else 2.1))) * 0.5


def rows_spec():
    """(kind, distance): 'top' rows at a distance below the top edge, 'hem' rows above the hem."""
    tops = [0.0, 0.012, 0.03, 0.055, HEADER]
    hems = [HEM, 0.035, 0.02, 0.008, 0.0]
    mid_n = 52
    mids = [HEADER + (DROP - HEM - HEADER) * k / (mid_n + 1) for k in range(1, mid_n + 1)]
    return [("top", d) for d in tops] + [("mid", d) for d in mids] + [("hem", e) for e in hems]


def build_panel(panel):
    spec = rows_spec()
    sections = []
    for kind, d in spec:
        t = d / DROP if kind != "hem" else (DROP - d) / DROP
        sections.append(panel.section(t))
    ncols = len(sections[0][0])
    # world-scale U: the arc length at half drop, shared by every row (the cloth does not stretch)
    mid_pts = panel.section(0.5)[0]
    w_ref = sum((mid_pts[i + 1] - mid_pts[i]).length for i in range(ncols - 1))

    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    vuv = {}

    def vert(co, uv):
        v = bm.verts.new(co)
        vuv[v] = uv
        return v

    def quad(a, b, c, d):
        f = bm.faces.new((a, b, c, d))
        for lp in f.loops:
            lp[uvl].uv = vuv[lp.vert]
        return f

    # per row: positions, room-side normals (in xy), U values
    grid, normals, us, zs = [], [], [], []
    for r, ((kind, d), (pts, tans)) in enumerate(zip(spec, sections)):
        arc = [0.0]
        for i in range(1, ncols):
            arc.append(arc[-1] + (pts[i] - pts[i - 1]).length)
        u_row = [a / arc[-1] * w_ref for a in arc]
        # tangents are (ty, tx) in the (y, x) plane; turned 90 degrees they give a normal (ny, nx)
        nrm = [Vector((-tg.y, tg.x)) for tg in tans]
        row, zrow = [], []
        for i in range(ncols):
            if kind == "top":
                z = Z_TOP - d
            elif kind == "hem":
                z = hem_z(panel, i, ncols) + d
            else:
                zt = Z_TOP - d
                # blend towards the uneven hem over the lowest metre
                zt += (hem_z(panel, i, ncols) - Z_HEM) * max(0.0, 1 - (zt - Z_HEM) / 1.0)
                z = zt
            zrow.append(z)
            row.append(vert((pts[i].y, pts[i].x, z), (u_row[i], Z_TOP - z)))
        grid.append(row)
        normals.append(nrm)
        us.append(u_row)
        zs.append(zrow)

    nr = len(grid)
    for r in range(nr - 1):
        for i in range(ncols - 1):
            quad(grid[r][i], grid[r][i + 1], grid[r + 1][i + 1], grid[r + 1][i])

    def room_normal(r, i):
        """Unit normal of the cloth in world (x, y), on one fixed side of the tangent."""
        n = normals[r][i]
        return Vector((n.y, n.x, 0.0))

    # which side is the room's: the one the normals point to (+x) on average
    sgn = 1.0 if sum(room_normal(nr // 2, i).x for i in range(ncols)) >= 0 else -1.0

    def behind(r, i, off):
        v = grid[r][i].co
        n = room_normal(r, i) * sgn
        return Vector((v.x - n.x * off, v.y - n.y * off, v.z))

    # --- header folded back at the top: turn above the top edge, then down behind the face
    top_rows = [r for r, (k, _) in enumerate(spec) if k == "top"]
    turn = [vert(behind(0, i, OFF_HEADER * 0.5) + Vector((0, 0, OFF_HEADER * 0.5)),
                 (us[0][i], -OFF_HEADER * 0.8)) for i in range(ncols)]
    back = [[vert(behind(r, i, OFF_HEADER), (us[r][i], -OFF_HEADER * 1.6 - (Z_TOP - zs[r][i])))
             for i in range(ncols)] for r in top_rows]
    chain = [grid[0], turn] + back
    for a, b in zip(chain[:-1], chain[1:]):
        for i in range(ncols - 1):
            quad(b[i], b[i + 1], a[i + 1], a[i])

    # --- weighted hem folded back at the bottom
    hem_rows = [r for r, (k, _) in enumerate(spec) if k == "hem"]   # top to bottom, last is the hem edge
    last = nr - 1
    turn = [vert(behind(last, i, OFF_HEM * 0.5) - Vector((0, 0, OFF_HEM * 0.5)),
                 (us[last][i], DROP + OFF_HEM * 0.8)) for i in range(ncols)]
    back = [[vert(behind(r, i, OFF_HEM), (us[r][i], DROP + OFF_HEM * 1.6 + (zs[r][i] - Z_HEM)))
             for i in range(ncols)] for r in reversed(hem_rows)]
    chain = [grid[last], turn] + back
    for a, b in zip(chain[:-1], chain[1:]):
        for i in range(ncols - 1):
            quad(a[i], a[i + 1], b[i + 1], b[i])

    # --- side hems: turn round each vertical edge, 2 cm back behind the face
    def side(edge_i, inward):
        cols = [edge_i + inward * k for k in range(3)]   # 0, ~1, ~2 cm in from the edge
        turn_col, back_cols = [], [[] for _ in cols]
        for r in range(nr):
            v = grid[r][edge_i].co
            tg = Vector((sections[r][1][edge_i].y, sections[r][1][edge_i].x, 0.0))   # world (x, y)
            out = -tg * inward
            n = room_normal(r, edge_i) * sgn
            turn_col.append(vert(v + out * OFF_SIDE * 0.5 - n * OFF_SIDE * 0.5,
                                 (us[r][edge_i] - inward * OFF_SIDE * 0.8, Z_TOP - zs[r][edge_i])))
            for k, c in enumerate(cols):
                back_cols[k].append(vert(behind(r, c, OFF_SIDE),
                                         (us[r][edge_i] - inward * (OFF_SIDE * 1.6 + abs(us[r][c] - us[r][edge_i])),
                                          Z_TOP - zs[r][c])))
        chain = [[grid[r][edge_i] for r in range(nr)], turn_col] + back_cols
        for a, b in zip(chain[:-1], chain[1:]):
            for r in range(nr - 1):
                if inward > 0:
                    quad(a[r], b[r], b[r + 1], a[r + 1])
                else:
                    quad(b[r], a[r], a[r + 1], b[r + 1])

    side(0, 1)
    side(ncols - 1, -1)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = S.obj_from_bm(bm, "sheer_" + panel.name, SHEER)
    return ob, panel.crossings(0.0), sections[0]


# ------------------------------------------------------------------ hardware

def torus(name, centre, axis, R_, r_, mat, segs=16, ring=6):
    bm = bmesh.new()
    rot = Vector((0, 0, 1)).rotation_difference(Vector(axis).normalized()).to_matrix().to_4x4()
    m = Matrix.Translation(centre) @ rot
    rings = []
    for a in range(segs):
        th = 2 * math.pi * a / segs
        c = Vector((R_ * math.cos(th), R_ * math.sin(th), 0))
        d = Vector((math.cos(th), math.sin(th), 0))
        rings.append([bm.verts.new(m @ (c + d * r_ * math.cos(2 * math.pi * b / ring)
                                        + Vector((0, 0, r_ * math.sin(2 * math.pi * b / ring)))))
                      for b in range(ring)])
    for a in range(segs):
        a2 = (a + 1) % segs
        for b in range(ring):
            b2 = (b + 1) % ring
            bm.faces.new((rings[a][b], rings[a2][b], rings[a2][b2], rings[a][b2]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return S.obj_from_bm(bm, name, mat)


def hardware():
    parts = []
    cap = 0.012
    parts.append(S.cylinder("rod", (ROD_X, ROD_Y0 + cap, ROD_Z), (ROD_X, ROD_Y1 - cap, ROD_Z), ROD_R, ROD, segs=24))
    for y0, y1 in ((ROD_Y0, ROD_Y0 + cap), (ROD_Y1 - cap, ROD_Y1)):
        c = S.cylinder("cap", (ROD_X, y0, ROD_Z), (ROD_X, y1, ROD_Z), ROD_R + 0.0025, ROD, segs=24)
        parts.append(S.bevel(c, 0.0015, 2, angle=30))
    for y in BRACKETS:
        zb = ROD_Z - 0.022
        rose = S.cylinder("rosette", (R.X_BACK - 0.0005, y, zb), (R.X_BACK + 0.010, y, zb), 0.022, ROD, segs=28)
        parts.append(S.bevel(rose, 0.002, 2, angle=30))
        parts.append(S.cylinder("arm", (R.X_BACK + 0.009, y, zb), (ROD_X + 0.004, y, zb), 0.0055, ROD, segs=14))
        parts.append(S.cylinder("post", (ROD_X, y, zb - 0.006), (ROD_X, y, ROD_Z - 0.006), 0.006, ROD, segs=14))
        cup = S.cylinder("saddle", (ROD_X, y - 0.009, ROD_Z - 0.012), (ROD_X, y + 0.009, ROD_Z - 0.012),
                         0.0065, ROD, segs=14)
        parts.append(cup)
    return parts


def clip_ring(y, x, tangent_yx, k):
    """A ring on the rod, a small eye under it and a sprung clip holding the cloth."""
    parts = [torus(f"ring{k}", (ROD_X, y, RING_Z), (0, 1, 0), RING_R, RING_W, ROD, 16, 6)]
    z_eye = RING_Z - RING_R - RING_W - 0.0030
    parts.append(torus(f"eye{k}", (ROD_X, y, z_eye), (1, 0, 0), 0.0042, 0.0011, ROD, 10, 4))
    # clip: jaws along the cloth at the top edge (the cloth runs through it)
    ang = math.atan2(tangent_yx.y, tangent_yx.x)   # angle of the cloth in plan, from +Y towards +X
    zc0, zc1 = Z_TOP - 0.014, z_eye - 0.0035
    w, d = 0.013, 0.0075
    clip = S.box(f"clip{k}", (-w / 2, -d / 2, zc0), (w / 2, d / 2, zc1), ROD)
    # box local x along the cloth: rotate it from +X to the cloth direction (y along, x across)
    clip.data.transform(Matrix.Rotation(math.pi / 2 - ang, 4, "Z"))
    clip.data.transform(Matrix.Translation((x, y, 0)))
    S.bevel(clip, 0.0012, 2, angle=30)
    parts.append(clip)
    return parts


# ------------------------------------------------------------------ build

LEFT = Panel("left", -2.93, -2.10, 12, flare_out=0.025, flare_in=0.045, d_top=0.072, d_hem=0.108, seed=3)
RIGHT = Panel("right", -1.235, -1.88, 10, flare_out=0.018, flare_in=0.055, d_top=0.070, d_hem=0.112, seed=8)

parts = hardware()
k = 0
for p in (LEFT, RIGHT):
    sheet, cross, (pts, tans) = build_panel(p)
    parts.append(sheet)
    for j in range(0, p.n + 1, 2):
        i = min(j * PER_HALF, len(pts) - 1)
        parts += clip_ring(pts[i].x, pts[i].y, Vector((tans[i].x, tans[i].y)), k)
        k += 1

ob = S.join(NAME, parts)
S.set_origin(ob, (0, 0, 0))
S.tidy(ob, sharp_angle=50)
R.box_uv(ob, only_mats={"M_Rod"})

# the cloth faces the room: flip any sheet island whose area-weighted normal points to the window
bm = bmesh.new()
bm.from_mesh(ob.data)
sheer_i = [m.name for m in ob.data.materials].index("M_Sheer")
seen = set()
for f in bm.faces:
    if f.index in seen or f.material_index != sheer_i:
        continue
    island, stack = [], [f]
    seen.add(f.index)
    while stack:
        g = stack.pop()
        island.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen and h.material_index == sheer_i:
                    seen.add(h.index)
                    stack.append(h)
    if sum(g.normal.x * g.calc_area() for g in island) < 0:
        bmesh.ops.reverse_faces(bm, faces=island)
bm.to_mesh(ob.data)
bm.free()
ob.data.update()

os.makedirs(args.out, exist_ok=True)
fbx = os.path.join(args.out, NAME + ".fbx")
S.export_fbx(ob, fbx)
lo, hi = S.bbox(ob)
print("=" * 60)
print(f"{NAME}: materials {[m.name for m in ob.data.materials]}")
print(f"{NAME}: triangles {S.tri_count(ob)}")
print(f"{NAME}: bbox cm  X {lo.x*100:.2f}..{hi.x*100:.2f}  Y {lo.y*100:.2f}..{hi.y*100:.2f}"
      f"  Z {lo.z*100:.2f}..{hi.z*100:.2f}")
for p in (LEFT, RIGHT):
    c0, c1 = p.crossings(0.0), p.crossings(1.0)
    print(f"{NAME}: {p.name} panel y top {c0[0]*100:.1f}..{c0[-1]*100:.1f}  hem {c1[0]*100:.1f}..{c1[-1]*100:.1f} cm")
print("=" * 60)
if not args.no_render:
    for m in ob.data.materials:
        R.dress(m.name, m)
    R.prop_previews(ob, args.out, NAME, (1.0, 0.75, 0.55), (1.0, 0.0, 0.0), args.samples, lens=50)
    R.closeup(ob, os.path.join(args.out, NAME + "_close.png"), (-1.75, -1.55, 2.62), (ROD_X, -2.0, 2.80),
              45, args.samples)
