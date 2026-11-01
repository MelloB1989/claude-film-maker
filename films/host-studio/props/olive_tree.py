"""olive_tree: a potted olive tree (Olea europaea) in a pale textured ceramic planter, 195 cm tall.

Run headless:
    blender -b --factory-startup -P films/host-studio/props/olive_tree.py -- --out films/host-studio/props/out

Writes <out>/olive_tree.fbx and the previews olive_tree.png (3/4), olive_tree_front.png,
olive_tree_backlit.png (soft daylight behind the tree, as through the studio's sheer curtains)
and olive_tree_close.png (a ~40 cm patch of leaves and twigs), and prints bbox, triangles and slots.
1 Blender unit = 1 m; origin at the bottom centre of the pot; front = +X. Seeded (--seed, default 7)
and deterministic.

One mesh, five slots:
    M_Pot        the planter (off-white ceramic; cylindrical UVs, 1 UV unit = 1 m)
    M_Pebbles    the grey-brown pebble top dressing (planar world-XY UVs; per-pebble vertex colour)
    M_Bark       trunk, branches and twigs (U around the bark, V along it, both in metres)
    M_LeafTop    upper (adaxial) leaf surface, grey-green  (UV 0..1 per leaf: U across, V base->tip)
    M_LeafUnder  lower (abaxial) leaf surface, silvery     (same UVs)

Each leaf is a closed lens-shaped shell: the upper and lower surfaces share the margin vertices and
are 0.4 mm apart along the midrib, so the leaf is two-sided, manifold and costs 24 triangles.
Leaves and branches are placed by rejection sampling against everything placed before them.
"""

import argparse
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector, noise
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

NAME = "olive_tree"
UP = Vector((0, 0, 1))

# ---------------------------------------------------------------- dimensions (m)
POT_H = 0.48
POT_R_RIM = 0.23           # 46 cm across the rim
POT_R_BASE = 0.152
POT_LIP = 0.010            # radius of the rounded lip (wall 2 cm thick at the top)
POT_WALL = 0.019
PEBBLE_Z = 0.432           # top of the pebble bed, ~4.8 cm below the rim
INNER_FLOOR = 0.395        # hidden false floor under the pebble bed

TOTAL_H = 1.95
TRUNK_TOP = PEBBLE_Z + 0.90
CROWN_C = Vector((0.0, 0.015, 1.425))      # twig-tip envelope (leaves reach a few cm beyond)
CROWN_A = Vector((0.425, 0.425, 0.49))

LEAF_GAP = 0.0008          # minimum clearance between leaf mid-surfaces
LEAF_THICK = 0.0004

M_POT, M_PEB, M_BARK, M_TOP, M_UNDER = range(5)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(prog=NAME)
    p.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--views", default="34,front,backlit,close")
    return p.parse_args(argv)


# ---------------------------------------------------------------- mesh accumulator

class Acc:
    """Vertices, faces, per-face material and per-loop UVs/colours for one big mesh."""

    def __init__(self):
        self.v, self.f, self.m, self.uv, self.col = [], [], [], [], []

    def vert(self, co):
        self.v.append(Vector(co))
        return len(self.v) - 1

    def face(self, idx, mat, uvs, col=(1.0, 1.0, 1.0)):
        self.f.append(tuple(idx))
        self.m.append(mat)
        self.uv.append(uvs)
        self.col.append(col)

    def tris(self):
        return sum(len(f) - 2 for f in self.f)

    def to_object(self, name, mats):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in self.v], [], self.f)
        for m in mats:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", self.m)
        uvl = me.uv_layers.new(name="UVMap")
        flat = [c for uvs in self.uv for uv in uvs for c in uv]
        uvl.data.foreach_set("uv", flat)
        ca = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
        cols = [c for f, col in zip(self.f, self.col) for _ in f for c in (*col, 1.0)]
        ca.data.foreach_set("color", cols)
        me.update()
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


# ---------------------------------------------------------------- helpers

def smoothstep(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def rand_unit(rng):
    while True:
        v = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if 0.01 < v.length <= 1:
            return v.normalized()


def frames(points, hint=None):
    """Parallel-transport (T, N, B) frames along a polyline."""
    n = len(points)
    T = []
    for i in range(n):
        a, b = points[max(i - 1, 0)], points[min(i + 1, n - 1)]
        T.append((b - a).normalized())
    ref = hint if hint is not None else (UP if abs(T[0].z) < 0.9 else Vector((1, 0, 0)))
    N = (ref - ref.dot(T[0]) * T[0]).normalized()
    out = []
    for i in range(n):
        if i:
            axis = T[i - 1].cross(T[i])
            if axis.length > 1e-9:
                N = Matrix.Rotation(T[i - 1].angle(T[i]), 3, axis.normalized()) @ N
            N = (N - N.dot(T[i]) * T[i]).normalized()
        out.append((T[i], N, T[i].cross(N)))
    return out


def arclen(points):
    s = [0.0]
    for a, b in zip(points, points[1:]):
        s.append(s[-1] + (b - a).length)
    return s


def tube(acc, points, radius, sides, mat, cap_end=True, cap_start=True, fr=None):
    """Sweep a ring along `points`; radius(i, theta) or a list. UVs in metres (U around, V along)."""
    fr = fr or frames(points)
    s = arclen(points)
    rad = (lambda i, th: radius[i]) if not callable(radius) else radius
    rmean = sum(rad(i, 0.0) for i in range(len(points))) / len(points)
    rings = []
    for i, p in enumerate(points):
        T, N, B = fr[i]
        ring = []
        for k in range(sides):
            th = 2 * math.pi * k / sides
            ring.append(acc.vert(p + (N * math.cos(th) + B * math.sin(th)) * rad(i, th)))
        rings.append(ring)
    circ = 2 * math.pi * rmean
    for i in range(len(points) - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(sides):
            k2 = (k + 1) % sides
            u0, u1 = circ * k / sides, circ * (k + 1) / sides
            acc.face((a[k], a[k2], b[k2], b[k]), mat,
                     ((u0, s[i]), (u1, s[i]), (u1, s[i + 1]), (u0, s[i + 1])))
    for end, use in ((0, cap_start), (len(points) - 1, cap_end)):
        if not use:
            continue
        T, N, B = fr[end]
        r = rings[end]
        c = acc.vert(points[end] + T * (rad(end, 0.0) * (0.35 if end else -0.35)))
        for k in range(sides):
            k2 = (k + 1) % sides
            th0, th1 = 2 * math.pi * k / sides, 2 * math.pi * k2 / sides
            uv0 = (0.5 * rmean * math.cos(th0), 0.5 * rmean * math.sin(th0))
            uv1 = (0.5 * rmean * math.cos(th1), 0.5 * rmean * math.sin(th1))
            if end == 0:
                acc.face((c, r[k2], r[k]), mat, ((0, 0), uv1, uv0))
            else:
                acc.face((c, r[k], r[k2]), mat, ((0, 0), uv0, uv1))


def lathe(acc, profile, segs, mat, uv_r, jitter=None):
    """Revolve (r, z) around Z (r == 0 -> pole). Cylindrical UVs in metres. jitter(p) -> radial offset."""
    s = arclen([Vector((r, 0, z)) for r, z in profile])
    rings = []
    for r, z in profile:
        if r < 1e-9:
            rings.append([acc.vert((0, 0, z))] * segs)
            continue
        ring = []
        for k in range(segs):
            a = 2 * math.pi * k / segs
            p = Vector((r * math.cos(a), r * math.sin(a), z))
            if jitter:
                p += Vector((math.cos(a), math.sin(a), 0)) * jitter(p)
            ring.append(acc.vert(p))
        rings.append(ring)
    for i in range(len(profile) - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(segs):
            k2 = (k + 1) % segs
            u0, u1 = uv_r * 2 * math.pi * k / segs, uv_r * 2 * math.pi * (k + 1) / segs
            quad = [(a[k], (u0, s[i])), (a[k2], (u1, s[i])), (b[k2], (u1, s[i + 1])), (b[k], (u0, s[i + 1]))]
            seen, idx, uv = set(), [], []
            for vi, t in quad:
                if vi in seen:
                    continue
                seen.add(vi)
                idx.append(vi)
                uv.append(t)
            if len(idx) >= 3:
                acc.face(idx, mat, uv)


def bvh_of(verts, faces):
    return BVHTree.FromPolygons([tuple(v) for v in verts], faces, all_triangles=False, epsilon=0.0)


def tube_bvh(points, radii, sides=6, inflate=1.1):
    fr = frames(points)
    verts, faces = [], []
    for i, p in enumerate(points):
        T, N, B = fr[i]
        for k in range(sides):
            th = 2 * math.pi * k / sides
            verts.append(p + (N * math.cos(th) + B * math.sin(th)) * radii[i] * inflate)
    for i in range(len(points) - 1):
        for k in range(sides):
            k2 = (k + 1) % sides
            faces.append((i * sides + k, i * sides + k2, (i + 1) * sides + k2, (i + 1) * sides + k))
    return bvh_of(verts, faces)


class Grid:
    """Spatial hash of bounding boxes -> item ids."""

    def __init__(self, cell):
        self.cell, self.cells = cell, {}

    def _keys(self, lo, hi):
        c = self.cell
        for i in range(int(math.floor(lo.x / c)), int(math.floor(hi.x / c)) + 1):
            for j in range(int(math.floor(lo.y / c)), int(math.floor(hi.y / c)) + 1):
                for k in range(int(math.floor(lo.z / c)), int(math.floor(hi.z / c)) + 1):
                    yield (i, j, k)

    def add(self, lo, hi, item):
        for key in self._keys(lo, hi):
            self.cells.setdefault(key, []).append(item)

    def query(self, lo, hi):
        out = set()
        for key in self._keys(lo, hi):
            out.update(self.cells.get(key, ()))
        return out


def bounds(points, pad=0.0):
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return lo - Vector((pad, pad, pad)), hi + Vector((pad, pad, pad))


# ---------------------------------------------------------------- the pot and pebbles

def pot_outer_r(z):
    """Outer radius of the wall: a full, gently bellied taper, widest ~8 cm below the rim."""
    u = (z - 0.018) / (POT_H - POT_LIP - 0.018)
    return POT_R_BASE + (0.2315 - POT_R_BASE) * math.sin(min(max(u, 0.0), 1.0) * math.pi / 2 / 0.9)


def build_pot(acc, rng):
    heel = 0.018
    prof = [(0.0, 0.0), (POT_R_BASE - heel - 0.012, 0.0)]
    # slightly recessed foot: the base touches the floor on a ring
    prof[0] = (0.0, 0.003)
    prof.insert(1, (POT_R_BASE - heel - 0.03, 0.0015))
    for k in range(7):
        a = math.pi / 2 * k / 6
        prof.append((POT_R_BASE - heel + heel * math.sin(a), heel - heel * math.cos(a)))
    z_wall_top = POT_H - POT_LIP
    n = 32
    for k in range(1, n + 1):
        z = heel + (z_wall_top - heel) * k / n
        prof.append((pot_outer_r(z), z))
    r_end = pot_outer_r(z_wall_top)
    cx = r_end - POT_LIP
    for k in range(1, 12):
        a = math.pi * k / 11
        prof.append((cx + POT_LIP * math.cos(a), z_wall_top + POT_LIP * math.sin(a)))
    for k in range(1, 7):
        z = z_wall_top - (z_wall_top - INNER_FLOOR) * k / 6
        prof.append((pot_outer_r(z) - POT_WALL - 0.001 * (1 - k / 6), z))
    prof.append((0.0, INNER_FLOOR))

    ph = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))

    def jitter(p):
        if math.hypot(p.x, p.y) < pot_outer_r(min(p.z, POT_H - POT_LIP)) - POT_WALL * 0.5:
            return 0.0  # inner wall stays true
        # hand-thrown irregularity plus a fine pitted texture, faded out at the foot and the lip
        fade = smoothstep(0.004, 0.03, p.z) * (1 - smoothstep(0.452, 0.468, p.z))
        return fade * (0.0010 * noise.noise(p * 6 + ph) + 0.00035 * noise.noise(p * 70 + ph))

    lathe(acc, prof, 96, M_POT, 0.23, jitter)


def build_pebbles(acc, rng, avoid_xy, avoid_r):
    """A dark bumpy bed under ~1600 small rounded pebbles on a jittered hex lattice, partly sunk."""
    r_in = pot_outer_r(PEBBLE_Z) - POT_WALL - 0.0006
    ph = Vector((rng.uniform(0, 50), rng.uniform(0, 50), 3.0))

    def bed_z(x, y):
        rr = math.hypot(x, y) / r_in
        return PEBBLE_Z - 0.004 + 0.0012 * noise.noise(Vector((x * 14, y * 14, 0)) + ph) + 0.002 * rr * rr

    # bed: rings of verts, z from bed_z, closed underneath
    segs, nring = 72, 12
    rings = [[acc.vert((0, 0, bed_z(0, 0)))]]
    for i in range(1, nring + 1):
        r = r_in * i / nring
        rings.append([acc.vert((r * math.cos(2 * math.pi * k / segs), r * math.sin(2 * math.pi * k / segs),
                                bed_z(r * math.cos(2 * math.pi * k / segs), r * math.sin(2 * math.pi * k / segs))))
                      for k in range(segs)])
    skirt = [acc.vert((r_in * math.cos(2 * math.pi * k / segs), r_in * math.sin(2 * math.pi * k / segs),
                       PEBBLE_Z - 0.02)) for k in range(segs)]
    bottom = acc.vert((0, 0, PEBBLE_Z - 0.02))
    col = (0.80, 0.78, 0.76)

    def uv(i):
        return (acc.v[i].x, acc.v[i].y)
    for k in range(segs):
        k2 = (k + 1) % segs
        f = (rings[0][0], rings[1][k], rings[1][k2])
        acc.face(f, M_PEB, [uv(i) for i in f], col)
        for i in range(1, nring):
            f = (rings[i][k], rings[i + 1][k], rings[i + 1][k2], rings[i][k2])
            acc.face(f, M_PEB, [uv(j) for j in f], col)
        f = (rings[nring][k], skirt[k], skirt[k2], rings[nring][k2])
        acc.face(f, M_PEB, [uv(j) for j in f], col)
        f = (skirt[k], bottom, skirt[k2])
        acc.face(f, M_PEB, [uv(j) for j in f], col)

    # Pebbles on a jittered hex lattice, each shrunk to clear the ones already placed (dense cover)
    placed = []
    grid = {}
    cell = 0.015
    sp = 0.0097
    rows = int(r_in / (sp * 0.866)) + 2
    sites = []
    for jr in range(-rows, rows + 1):
        for ir in range(-rows, rows + 1):
            x = (ir + 0.5 * (jr & 1)) * sp + rng.uniform(-0.28, 0.28) * sp
            y = jr * sp * 0.866 + rng.uniform(-0.28, 0.28) * sp
            sites.append((x, y))
    rng.shuffle(sites)
    for x, y in sites:
        want = sp * 0.5 * rng.uniform(0.95, 1.25)
        room = r_in - 0.0008 - math.hypot(x, y)
        room = min(room, math.hypot(x - avoid_xy.x, y - avoid_xy.y) - avoid_r)
        room += 0.0007  # neighbours may just touch
        gx, gy = int(math.floor(x / cell)), int(math.floor(y / cell))
        for i in range(gx - 1, gx + 2):
            for j in range(gy - 1, gy + 2):
                for (px, py, pa) in grid.get((i, j), ()):
                    room = min(room, math.hypot(px - x, py - y) - pa)
        a = min(want, room)
        if a < 0.0026:
            continue
        grid.setdefault((gx, gy), []).append((x, y, a))
        placed.append((x, y, a))

    for x, y, a in placed:
        b = a * rng.uniform(0.70, 0.95)
        c = a * rng.uniform(0.55, 0.80)
        rot = Matrix.Rotation(rng.uniform(0, 2 * math.pi), 3, "Z") @ \
            Matrix.Rotation(rng.uniform(-0.25, 0.25), 3, "X")
        cz = bed_z(x, y) + c * rng.uniform(0.35, 0.60)
        cen = Vector((x, y, cz))
        n = 5
        ring = []
        for k in range(n):
            t = 2 * math.pi * (k + rng.uniform(-0.12, 0.12)) / n
            j = rng.uniform(0.88, 1.06)
            ring.append(acc.vert(cen + rot @ Vector((a * j * math.cos(t), b * j * math.sin(t),
                                                     c * rng.uniform(-0.15, 0.15)))))
        top = acc.vert(cen + rot @ Vector((rng.uniform(-0.2, 0.2) * a, rng.uniform(-0.2, 0.2) * b, c)))
        bot = acc.vert(cen + rot @ Vector((0, 0, -c * 0.8)))
        g = rng.uniform(0.75, 1.25)
        tint = (min(1.0, g * rng.uniform(1.0, 1.07)), g, g * rng.uniform(0.88, 0.97))
        for k in range(n):
            k2 = (k + 1) % n
            f = (top, ring[k], ring[k2])
            acc.face(f, M_PEB, [uv(i) for i in f], tint)
            f = (bot, ring[k2], ring[k])
            acc.face(f, M_PEB, [uv(i) for i in f], tint)
    return len(placed)


# ---------------------------------------------------------------- the crown envelope

class Envelope:
    def __init__(self, rng):
        self.ph = Vector((rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)))
        # see-through gaps in the crown: no twig ends or leaves inside these
        self.voids = []
        while len(self.voids) < 6:
            p = CROWN_C + Vector((rng.uniform(-1, 1) * CROWN_A.x, rng.uniform(-1, 1) * CROWN_A.y,
                                  rng.uniform(-0.8, 0.9) * CROWN_A.z))
            if 0.35 < self.value(p) < 0.85 and (p.xy - CROWN_C.xy).length > 0.10:
                self.voids.append((p, rng.uniform(0.07, 0.12)))

    def in_void(self, p, pad=0.0):
        return any((p - c).length < r + pad for c, r in self.voids)

    def radii(self, d):
        # lumpy, so the outline is irregular rather than a clean ellipsoid
        k = 1.0 + 0.20 * noise.noise(d * 1.3 + self.ph) + 0.07 * noise.noise(d * 3.5 + self.ph)
        return Vector((CROWN_A.x * k, CROWN_A.y * k, CROWN_A.z * k))

    def value(self, p):
        q = p - CROWN_C
        if q.length < 1e-6:
            return 0.0
        A = self.radii(q.normalized())
        return math.sqrt((q.x / A.x) ** 2 + (q.y / A.y) ** 2 + (q.z / A.z) ** 2)

    def dist(self, p, d):
        """Distance from p along unit d to the envelope surface (0 if outside)."""
        q = p - CROWN_C
        far = q + d * 0.3
        A = self.radii(far.normalized() if far.length > 1e-6 else d)
        qs = Vector((q.x / A.x, q.y / A.y, q.z / A.z))
        ds = Vector((d.x / A.x, d.y / A.y, d.z / A.z))
        a, b, c = ds.dot(ds), 2 * qs.dot(ds), qs.dot(qs) - 1
        disc = b * b - 4 * a * c
        if c > 0 or disc < 0:
            return 0.0
        return (-b + math.sqrt(disc)) / (2 * a)


# ---------------------------------------------------------------- branches

class Branch:
    def __init__(self, pts, radii, level, parent=None):
        self.pts, self.radii, self.level, self.parent = pts, radii, level, parent
        self.fr = frames(pts)
        self.s = arclen(pts)
        self.length = self.s[-1]

    def at(self, s):
        """Index of the point at arc length s."""
        for i, v in enumerate(self.s):
            if v >= s:
                return i
        return len(self.s) - 1


GROW = {  # level: step, wobble, tropism (up), sides
    1: (0.020, 0.10, 0.06, 10),
    2: (0.018, 0.16, 0.04, 6),
    3: (0.013, 0.20, 0.03, 4),
}


def grow(env, rng, start, d0, length, level, droop=0.0):
    step, wob, trop, _ = GROW[level]
    n = max(3, int(round(length / step)))
    step = length / n
    pts, d = [start.copy()], d0.normalized()
    for i in range(n):
        d = (d + rand_unit(rng) * wob + UP * (trop - droop * (i / n))).normalized()
        p = pts[-1] + d * step
        e = env.value(p)
        if e > 0.9:
            d = (d + (CROWN_C - p).normalized() * (e - 0.9) * 2.5).normalized()
            p = pts[-1] + d * step
        pts.append(p)
    return pts


def taper(n, r0, r1, power=1.0):
    return [r0 + (r1 - r0) * (i / (n - 1)) ** power for i in range(n)]


def child_dir(rng, parent_T, parent_N, parent_B, az, angle):
    radial = parent_N * math.cos(az) + parent_B * math.sin(az)
    return (parent_T * math.cos(angle) + radial * math.sin(angle)).normalized()


# ---------------------------------------------------------------- leaves

# (t along the leaf, half-width as a fraction of W/2) for the margin; midrib stations
MARGIN = [(0.08, 0.10), (0.27, 0.80), (0.52, 1.00), (0.79, 0.62)]
MIDRIB = [0.0, 0.08, 0.50, 1.0]


def leaf_local(rng, L, W):
    """Lens-shaped two-sided olive leaf in leaf space (x across, y along, z = upper side).

    Returns verts, faces [(idx, mat, uvs)], and the indices of the blade's upper faces for testing."""
    fold = math.tan(math.radians(rng.uniform(8, 16)))       # margins raised: slight fold on the midrib
    curl = rng.uniform(0.02, 0.09)                          # tip bends down
    twist = rng.uniform(-0.25, 0.25)                        # gentle twist along the blade

    def shape(x, y):
        t = y / L
        z = fold * abs(x) - curl * L * t * t
        return Vector((x * math.cos(twist * t), y, z + x * math.sin(twist * t)))

    verts, faces = [], []
    B = 0
    verts.append(shape(0, 0))
    T = 1
    verts.append(shape(0, L))
    mt, mb = {}, {}
    for t in MIDRIB[1:-1]:
        h = 0.0004 if t < 0.2 else LEAF_THICK / 2          # petiole a little thicker
        p = shape(0, t * L)
        mt[t] = len(verts)
        verts.append(p + Vector((0, 0, h)))
        mb[t] = len(verts)
        verts.append(p - Vector((0, 0, h)))
    edge = {}
    for side in (1, -1):
        for t, w in MARGIN:
            edge[(side, t)] = len(verts)
            verts.append(shape(side * w * W / 2, t * L))

    def uv(i):
        p = verts[i]
        return (0.5 + p.x / W, p.y / L)

    m1, m2 = MIDRIB[1], MIDRIB[2]
    e = [MARGIN[k][0] for k in range(4)]
    test = []
    for side in (1, -1):
        E = [edge[(side, t)] for t in e]
        for top in (True, False):
            M1 = mt[m1] if top else mb[m1]
            M2 = mt[m2] if top else mb[m2]
            tris = [(B, E[0], M1), (M1, E[0], E[1]), (M1, E[1], M2),
                    (M2, E[1], E[2]), (M2, E[2], E[3]), (M2, E[3], T)]
            # wound so that the upper surface faces +z; mirrored side and the underside flip
            flip = (side < 0) != (not top)
            for k, tri in enumerate(tris):
                tri = tri if not flip else (tri[0], tri[2], tri[1])
                faces.append((tri, M_TOP if top else M_UNDER, [uv(i) for i in tri]))
                if top and k > 0:
                    test.append(len(faces) - 1)
    return verts, faces, test


def leaf_orient(base, d, n):
    """Matrix taking leaf space (x across, y along, z up-surface) to world."""
    y = d.normalized()
    z = (n - n.dot(y) * y).normalized()
    x = y.cross(z)
    return Matrix((x, y, z)).transposed(), base


# ---------------------------------------------------------------- the tree

def build_tree(acc, rng, env):
    branches = []
    bgrid = Grid(0.06)
    bvhs = []

    def register(br):
        branches.append(br)
        bvhs.append(tube_bvh(br.pts, br.radii, sides=6, inflate=1.12))
        lo, hi = bounds(br.pts, max(br.radii) + 0.002)
        bgrid.add(lo, hi, len(branches) - 1)

    def clashes(pts, rad, skip_len):
        s = arclen(pts)
        k = next((i for i, v in enumerate(s) if v >= skip_len), len(pts) - 1)
        if len(pts) - k < 2:
            return False
        sub_p, sub_r = pts[k:], rad[k:]
        tree = tube_bvh(sub_p, sub_r, sides=6, inflate=1.12)
        lo, hi = bounds(sub_p, max(sub_r) + 0.003)
        for j in bgrid.query(lo, hi):
            if tree.overlap(bvhs[j]):
                return True
        return False

    # ---- trunk: slender, slightly S-curved and twisting, gnarled near the base
    base = Vector((0.006, -0.004, INNER_FLOOR + 0.004))
    lean = Vector((rng.uniform(-0.02, 0.02), rng.uniform(0.0, 0.03), 0))
    trunk_pts = []
    n_tr = 95
    for i in range(n_tr + 1):
        t = i / n_tr
        z = base.z + (TRUNK_TOP - base.z) * t
        off = lean * t + Vector((0.022 * math.sin(t * 5.2 + 0.7), 0.018 * math.sin(t * 3.9 + 2.1), 0)) * \
            smoothstep(0.0, 0.25, t)
        trunk_pts.append(Vector((base.x, base.y, z)) + off)
    soil_t = (PEBBLE_Z - base.z) / (TRUNK_TOP - base.z)
    tph = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))

    def trunk_r(i, th):
        t = i / n_tr
        h = max(0.0, (t - soil_t)) * (TRUNK_TOP - base.z)          # height above the pebbles
        r = 0.0175 + (0.0100 - 0.0175) * smoothstep(soil_t, 1.0, t)
        r += 0.0075 * math.exp(-h / 0.035)                            # root flare
        g = 1.0 * math.exp(-h / 0.22) + 0.12                         # gnarl, strongest low down
        tw = 3.4 * h                                                  # slight twist of the fluting
        lobes = 0.26 * math.cos(3 * th + tw + 0.4) + 0.13 * math.cos(5 * th - 1.3 * tw + 2.0)
        p = trunk_pts[i]
        knob = noise.noise(Vector((math.cos(th) * 0.9, math.sin(th) * 0.9, p.z * 16)) + tph)
        fiss = noise.noise(Vector((math.cos(th + tw) * 3.0, math.sin(th + tw) * 3.0, p.z * 6)) + tph * 2)
        return r * (1 + g * lobes + 0.45 * g * knob + 0.04 * fiss)

    trunk_rad = [trunk_r(i, 0.0) for i in range(n_tr + 1)]
    trunk = Branch(trunk_pts, [0.019 if i / n_tr < soil_t + 0.05 else trunk_rad[i] for i in range(n_tr + 1)], 0)
    trunk.rfun = trunk_r
    register(trunk)

    # pruning stubs on the trunk (old cut side shoots) - small knobs
    stubs = []
    for z0 in (0.70, 0.98):
        i = int((z0 - base.z) / (TRUNK_TOP - base.z) * n_tr)
        T, N, B = trunk.fr[i]
        az = rng.uniform(0, 2 * math.pi)
        d = child_dir(rng, T, N, B, az, math.radians(rng.uniform(50, 70)))
        p0 = trunk_pts[i]
        L = rng.uniform(0.018, 0.028)
        pts = [p0 + d * (L * k / 5) for k in range(6)]
        stubs.append((pts, taper(6, 0.0062, 0.0042)))

    # ---- main scaffold branches from the top of the trunk
    n_main = rng.randint(4, 6)
    mains = []
    leader_br = None
    az0 = rng.uniform(0, 2 * math.pi)
    tops = sorted(rng.uniform(0.80, 0.97) for _ in range(n_main - 1)) + [1.0]
    for k in range(n_main):
        leader = k == n_main - 1
        for attempt in range(12):
            t = tops[k]
            i = min(int(t * n_tr), n_tr - 1) if not leader else n_tr
            T, N, B = trunk.fr[i]
            start = trunk_pts[i]
            if leader:
                d = (trunk.fr[n_tr][0] + rand_unit(rng) * 0.08).normalized()
            else:
                az = az0 + k * 2 * math.pi / (n_main - 1) + rng.uniform(-0.35, 0.35) + attempt * 0.4
                elev = math.radians(rng.uniform(22, 58))
                d = Vector((math.cos(az) * math.cos(elev), math.sin(az) * math.cos(elev), math.sin(elev)))
            L = env.dist(start, d) * rng.uniform(0.75, 0.95)
            L = max(0.25, L)
            pts = grow(env, rng, start, d, L, 1)
            r0 = trunk_rad[i] * (0.97 if leader else 0.70)
            rad = taper(len(pts), r0, 0.0022, 0.8)
            if not clashes(pts, rad, 0.04):
                br = Branch(pts, rad, 1, trunk)
                register(br)
                mains.append(br)
                if leader:
                    leader_br = br
                break

    # ---- secondary branches
    seconds = []

    def add_children(parent, level, s0, s1, spacing, angle, maxlen, minlen, r0f, droop_p):
        out = []
        s = parent.length * s0 + rng.uniform(0, spacing[1] - spacing[0])
        az = rng.uniform(0, 2 * math.pi)
        while s < parent.length * s1:
            i = parent.at(s)
            T, N, B = parent.fr[i]
            az += math.radians(rng.uniform(120, 160))
            for attempt in range(8):
                a2 = az + attempt * 0.7
                d = child_dir(rng, T, N, B, a2, math.radians(rng.uniform(*angle)))
                start = parent.pts[i]
                room = env.dist(start, d)
                L = min(maxlen * rng.uniform(0.7, 1.0), room * rng.uniform(0.75, 1.0))
                if L < minlen:
                    continue
                droop = droop_p * rng.random()
                pts = grow(env, rng, start, d, L, level, droop)
                if env.in_void(pts[-1]):
                    continue
                r0 = min(parent.radii[i] * r0f, {2: 0.0040, 3: 0.0016}[level])
                r1 = {2: 0.0011, 3: 0.0007}[level]
                rad = taper(len(pts), r0, r1, 0.9)
                if not clashes(pts, rad, parent.radii[i] * 2.5 + 0.006):
                    br = Branch(pts, rad, level, parent)
                    register(br)
                    out.append(br)
                    break
            s += rng.uniform(*spacing)
        return out

    for m in mains:
        seconds += add_children(m, 2, 0.20, 0.95, (0.045, 0.075), (40, 75), 0.36, 0.07, 0.75, 0.30)
    # a few low shoots straight off the trunk (the concept shows foliage low on the stem)
    low = []
    for z0 in sorted(rng.uniform(0.95, 1.26) for _ in range(7)):
        i = int((z0 - base.z) / (TRUNK_TOP - base.z) * n_tr)
        T, N, B = trunk.fr[i]
        for attempt in range(8):
            d = child_dir(rng, T, N, B, rng.uniform(0, 2 * math.pi), math.radians(rng.uniform(45, 70)))
            L = min(rng.uniform(0.18, 0.34), env.dist(trunk_pts[i], d) * 0.95)
            if L < 0.08:
                continue
            pts = grow(env, rng, trunk_pts[i], d, L, 2, 0.20)
            rad = taper(len(pts), 0.0030, 0.0010, 0.9)
            if not clashes(pts, rad, 0.03):
                br = Branch(pts, rad, 2, trunk)
                register(br)
                low.append(br)
                break
    seconds += low

    twigs = []
    for sbr in seconds:
        twigs += add_children(sbr, 3, 0.18, 0.92, (0.032, 0.055), (32, 58), 0.15, 0.045, 0.8, 0.20)
    for m in mains:  # twigs straight off the outer scaffold too
        twigs += add_children(m, 3, 0.70, 0.98, (0.04, 0.07), (35, 55), 0.13, 0.045, 0.6, 0.10)

    print(f"[{NAME}] branches: main {len(mains)}  secondary {len(seconds)}  twigs {len(twigs)}")

    # ---- leaves
    leaf_grid = Grid(0.07)
    leaf_bvhs, leaf_pts = [], []
    centres = []
    stats = {"tried": 0, "placed": 0}
    leaf_count = {}

    def try_leaf(br, i, phi, k_from_tip):
        T, N, B = br.fr[i]
        young = k_from_tip < 2
        size = min(1.0, 0.50 + 0.16 * k_from_tip) * rng.uniform(0.85, 1.12)
        L = max(0.022, min(0.072, rng.uniform(0.045, 0.068) * size))
        W = max(0.0075, min(0.014, L * rng.uniform(0.15, 0.20)))
        for attempt in range(6):
            stats["tried"] += 1
            ph = phi + rng.uniform(-0.3, 0.3) * (1 + attempt * 0.4)
            radial = N * math.cos(ph) + B * math.sin(ph)
            ang = math.radians(rng.uniform(16, 30) if young else rng.uniform(30, 58) + attempt * 3)
            d = (T * math.cos(ang) + radial * math.sin(ang))
            d = (d + UP * rng.uniform(0.10, 0.35)).normalized()
            if d.z < -0.55:
                continue
            # upper surface faces the twig tip / the sky
            n0 = T - T.dot(d) * d
            upp = UP - UP.dot(d) * d
            n = (n0.normalized() if n0.length > 1e-6 else upp) + upp * 0.8
            n = Matrix.Rotation(rng.uniform(-0.45, 0.45), 3, d) @ n
            rot, _ = leaf_orient(None, d, n)
            p0 = br.pts[i] + radial * br.radii[i] * 0.4
            lv, lf, test = leaf_local(rng, L, W)
            wv = [p0 + rot @ v for v in lv]
            tfaces = [lf[j][0] for j in test]
            tree = bvh_of(wv, tfaces)
            lo, hi = bounds(wv, LEAF_GAP)
            if wv[1].z < PEBBLE_Z + 0.2 or env.in_void((wv[0] + wv[1]) / 2):
                continue
            bad = False
            for j in bgrid.query(lo, hi):
                if tree.overlap(bvhs[j]):
                    bad = True
                    break
            if not bad:
                for j in leaf_grid.query(lo, hi):
                    if tree.overlap(leaf_bvhs[j]):
                        bad = True
                        break
                    other = leaf_bvhs[j]
                    for v in wv[2:]:
                        if other.find_nearest(v, LEAF_GAP)[0] is not None:
                            bad = True
                            break
                    if bad:
                        break
            if bad:
                continue
            base_i = len(acc.v)
            for v in wv:
                acc.vert(v)
            for tri, mat, uvs in lf:
                acc.face(tuple(base_i + t for t in tri), mat, uvs)
            leaf_bvhs.append(tree)
            leaf_grid.add(lo, hi, len(leaf_bvhs) - 1)
            centres.append((wv[0] + wv[1]) / 2)
            stats["placed"] += 1
            leaf_count[id(br)] = leaf_count.get(id(br), 0) + 1
            return True
        return False

    def leaf_branch(br, s_from):
        s = br.length - rng.uniform(0.003, 0.006)
        phi = rng.uniform(0, 2 * math.pi)
        k = 0
        while s > br.length * s_from:
            i = br.at(s)
            for side in (0, math.pi):
                try_leaf(br, i, phi + side, k)
            phi += math.pi / 2 + rng.uniform(-0.25, 0.25)        # decussate pairs
            s -= rng.uniform(0.010, 0.014) if k < 3 else rng.uniform(0.014, 0.021)
            k += 1

    for br in twigs:
        leaf_branch(br, 0.10)
    for br in seconds:
        leaf_branch(br, 0.35)
    for br in mains:
        leaf_branch(br, 0.78)
    print(f"[{NAME}] leaves placed {stats['placed']} of {stats['tried']} tries")

    # ---- bark geometry (after the leaves, so twigs that ended up leafless can be left out)
    if leader_br is not None:
        # the leader continues the trunk as one tube, so there is no seam where they meet
        lp = trunk_pts + leader_br.pts[1:]
        n_l = len(leader_br.pts)

        def stem_r(i, th):
            if i <= n_tr:
                return trunk_r(i, th)
            j = i - n_tr
            f = trunk_r(n_tr, th) / trunk_r(n_tr, 0.0)
            w = smoothstep(0, 6, j)
            return leader_br.radii[min(j, n_l - 1)] * (f * (1 - w) + w)
        tube(acc, lp, stem_r, 20, M_BARK)
    else:
        tube(acc, trunk_pts, trunk_r, 20, M_BARK, fr=trunk.fr)
    for pts, rad in stubs:
        tube(acc, pts, rad, 8, M_BARK)
    dropped = 0
    for br in branches[1:]:
        if br is leader_br:
            continue
        if br.level == 3 and not leaf_count.get(id(br)):
            dropped += 1
            continue
        tube(acc, br.pts, br.radii, GROW[br.level][3], M_BARK, fr=br.fr)
    print(f"[{NAME}] leafless twigs left out: {dropped}")
    return centres


# ---------------------------------------------------------------- materials

def node_mats():
    pot = S.material("M_Pot", (0.70, 0.67, 0.61), 0.72)
    nt = pot.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 95.0
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 300.0
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "MULTIPLY_ADD"
    add.inputs[1].default_value = 0.25
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.002
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], add.inputs[0])
    nt.links.new(vor.outputs["Distance"], add.inputs[2])
    nt.links.new(add.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    # preview only: a fine-gravel pattern on the planar UVs (1 UV unit = 1 m) so the bed between
    # the modelled pebbles reads as gravel too; in Unreal a gravel texture on this slot does the same
    peb = S.material("M_Pebbles", (0.21, 0.18, 0.15), 0.85)
    nt = peb.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 260.0
    vor.inputs["Randomness"].default_value = 0.9
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.10, 0.085, 0.07, 1)
    ramp.color_ramp.elements[1].color = (0.30, 0.27, 0.23, 1)
    nt.links.new(tc.outputs["UV"], vor.inputs["Vector"])
    nt.links.new(vor.outputs["Color"], ramp.inputs["Fac"])
    edge = nt.nodes.new("ShaderNodeMath")
    edge.operation = "POWER"
    edge.inputs[1].default_value = 0.6
    nt.links.new(vor.outputs["Distance"], edge.inputs[0])
    shade = nt.nodes.new("ShaderNodeMix")
    shade.data_type = "RGBA"
    shade.blend_type = "MULTIPLY"
    shade.inputs["Factor"].default_value = 0.7
    nt.links.new(ramp.outputs["Color"], shade.inputs[6])
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.15
    nt.links.new(edge.outputs[0], inv.inputs[1])
    nt.links.new(inv.outputs[0], shade.inputs[7])
    ca = nt.nodes.new("ShaderNodeVertexColor")
    ca.layer_name = "Col"
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(shade.outputs[2], mul.inputs[6])
    nt.links.new(ca.outputs["Color"], mul.inputs[7])
    nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.002
    nt.links.new(inv.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    bark = S.material("M_Bark", (0.072, 0.066, 0.056), 0.88)
    nt = bark.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 220.0
    nz.inputs["Detail"].default_value = 6.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    bump.inputs["Distance"].default_value = 0.001
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    def leaf(name, color, rough, trans_col, fac):
        m = S.material(name, color, rough, specular=0.30)
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
        tr.inputs["Color"].default_value = (*trans_col, 1)
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs["Fac"].default_value = fac
        nt.links.new(bsdf.outputs[0], mix.inputs[1])
        nt.links.new(tr.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        return m

    top = leaf("M_LeafTop", (0.042, 0.055, 0.030), 0.48, (0.16, 0.22, 0.05), 0.30)
    under = leaf("M_LeafUnder", (0.16, 0.175, 0.145), 0.52, (0.14, 0.19, 0.07), 0.25)
    return [pot, peb, bark, top, under]


# ---------------------------------------------------------------- finishing

def tidy(ob, sharp_angle=60):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    lim = math.radians(sharp_angle)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if all(f.material_index == M_PEB for f in e.link_faces):
            e.smooth = e.is_manifold          # low-poly pebbles read round when fully smoothed
            continue
        e.smooth = e.is_manifold and e.calc_face_angle(0.0) <= lim
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def check_mesh(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return nonman


# ---------------------------------------------------------------- previews

def clear_rig():
    for ob in list(bpy.data.objects):
        if ob.name.startswith("_"):
            bpy.data.objects.remove(ob, do_unlink=True)


def setup_render(samples):
    sc = bpy.context.scene
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = samples
    for attr in ("use_shadows", "use_raytracing"):
        if hasattr(sc.eevee, attr):
            setattr(sc.eevee, attr, True)
    sc.render.resolution_x = sc.render.resolution_y = 1200
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"


def world(color, strength):
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength


def floor(z=0.0, grey=0.18):
    m = S.material("_PreviewFloor", (grey, grey, grey), 0.8)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=20, matrix=Matrix.Translation((0, 0, z - 0.0005)))
    return S.obj_from_bm(bm, "_floor", m)


def area_light(name, loc, target, size, energy, color=(1, 1, 1)):
    light = bpy.data.lights.new(name, "AREA")
    light.shape = "DISK"
    light.size = size
    light.energy = energy
    light.color = color
    ob = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def camera(view_dir, target, lens, fit=None, margin=1.08, dist=None):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("_cam")
    cd.lens = lens
    cam = bpy.data.objects.new("_cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    v = Vector(view_dir).normalized()
    cam.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
    target = Vector(target)
    if fit is not None:
        lo, hi = fit
        corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        cam.location = target + v * 10
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        co, _ = cam.camera_fit_coords(dg, [c for p in corners for c in p])
        co = Vector(co)
        centre = (lo + hi) / 2
        cam.location = centre + (co - centre) * margin
    else:
        cam.location = target + v * dist
    cd.clip_start = 0.02
    cd.clip_end = 100
    return cam


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print(f"[{NAME}] wrote {path}")


def previews(ob, out, samples, views, centres):
    lo, hi = S.bbox(ob)
    centre = (lo + hi) / 2
    size = (hi - lo).length
    setup_render(samples)

    def neutral(view):
        clear_rig()
        world((0.18, 0.18, 0.18), 1.0)
        floor()
        v = Vector(view).normalized()
        side = v.cross(UP).normalized()
        for name, d, e, s in (("_key", v * 0.6 + side * 0.9 + UP * 0.9, 110, 1.4),
                              ("_fill", v * 0.8 - side * 0.8 + UP * 0.3, 35, 2.0),
                              ("_rim", -v + UP * 0.8, 70, 1.0)):
            area_light(name, centre + d.normalized() * size * 2.2, centre, size * s, e * size * size)

    if "34" in views:
        view = (1.0, 0.85, 0.55)
        neutral(view)
        camera(view, centre, 60, fit=(lo, hi), margin=1.06)
        render(os.path.join(out, NAME + ".png"))
    if "front" in views:
        view = (1.0, 0.0, 0.0)
        neutral((1.0, 0.0, 0.08))
        camera(view, centre, 60, fit=(lo, hi), margin=1.06)
        render(os.path.join(out, NAME + "_front.png"))
    if "backlit" in views:
        clear_rig()
        world((0.10, 0.09, 0.08), 0.6)
        floor(grey=0.22)
        # a big soft bright panel behind the tree: daylight through sheer curtains
        em = S.material("_Curtain", (1, 1, 1), 1.0)
        nt = em.node_tree
        out_n = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        es = nt.nodes.new("ShaderNodeEmission")
        es.inputs["Color"].default_value = (1.0, 0.93, 0.82, 1)
        es.inputs["Strength"].default_value = 3.2
        nt.links.new(es.outputs[0], out_n.inputs["Surface"])
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0,
                              matrix=Matrix.Translation((-0.75, 0, 1.6)) @ Matrix.Rotation(math.pi / 2, 4, "Y")
                              @ Matrix.Diagonal((2.0, 3.5, 1, 1)))
        S.obj_from_bm(bm, "_curtain", em)
        area_light("_sun", Vector((-0.70, 0.0, 1.5)), Vector((0.5, 0, 1.2)), 2.5, 250, (1.0, 0.92, 0.80))
        area_light("_room", Vector((3.5, -1.0, 1.6)), centre, 2.5, 90, (1.0, 0.95, 0.9))
        camera((1.0, 0.0, 0.0), centre, 55, fit=(lo, hi), margin=1.06)
        render(os.path.join(out, NAME + "_backlit.png"))
    if "pot" in views:  # internal check of the pebble bed and trunk base
        clear_rig()
        world((0.18, 0.18, 0.18), 1.0)
        tgt = Vector((0, 0, 0.45))
        view = Vector((1.0, 0.3, 0.9))
        area_light("_key", tgt + Vector((0.5, 0.8, 1.2)), tgt, 0.8, 60)
        area_light("_fill", tgt + Vector((1.2, -0.6, 0.5)), tgt, 1.0, 25)
        camera(view, tgt, 60, dist=0.75)
        render(os.path.join(out, NAME + "_dbg_pot.png"))
    if "close" in views:
        # densest patch of leaves on the camera side, mid-crown
        cand = [c for c in centres if c.x > 0.12 and 1.35 < c.z < 1.70]
        best, bn = None, -1
        for c in cand[::3]:
            n = sum(1 for d in cand if (d - c).length < 0.12)
            if n > bn:
                best, bn = c, n
        target = best or Vector((0.25, 0, 1.5))
        view = Vector((1.0, 0.35, 0.18))
        clear_rig()
        world((0.18, 0.18, 0.18), 1.0)
        v = view.normalized()
        side = v.cross(UP).normalized()
        for name, d, e, s in (("_key", v * 0.6 + side * 0.9 + UP * 0.9, 60, 0.8),
                              ("_fill", v * 0.8 - side * 0.8 + UP * 0.3, 20, 1.0),
                              ("_rim", -v + UP * 0.8, 50, 0.8)):
            area_light(name, target + d.normalized() * 1.2, target, s, e)
        camera(view, target, 60, dist=0.40 * 60 / 36)
        render(os.path.join(out, NAME + "_close.png"))


# ---------------------------------------------------------------- main

def main():
    args = parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    S.reset_scene()
    rng = random.Random(args.seed)
    mats = node_mats()
    acc = Acc()
    build_pot(acc, random.Random(rng.random()))
    n_pot = acc.tris()
    env = Envelope(random.Random(rng.random()))
    centres = build_tree(acc, random.Random(rng.random()), env)
    n_tree = acc.tris() - n_pot
    npeb = build_pebbles(acc, random.Random(rng.random()), Vector((0.006, -0.004)), 0.032)
    n_peb = acc.tris() - n_pot - n_tree
    ob = acc.to_object(NAME, mats)
    tidy(ob)
    print(f"[{NAME}] tris pot {n_pot}  tree+leaves {n_tree}  pebbles {n_peb} ({npeb} pebbles)")
    print(f"[{NAME}] non-manifold edges {check_mesh(ob)}")
    h = sum((i % 97 + 1) * (v.co.x + 2 * v.co.y + 3 * v.co.z) for i, v in enumerate(ob.data.vertices))
    print(f"[{NAME}] geometry hash {h:.6f}")
    leaf_tris = sum(1 for m in acc.m if m in (M_TOP, M_UNDER))
    print(f"[{NAME}] leaf tris {leaf_tris}  (= {leaf_tris // 24} leaves)")

    S.export_fbx(ob, os.path.join(out, NAME + ".fbx"))
    lo, hi = S.bbox(ob)
    d = (hi - lo) * 100
    print("=" * 60)
    print(f"{NAME}: materials {[m.name for m in ob.data.materials]}")
    print(f"{NAME}: triangles {S.tri_count(ob)}")
    print(f"{NAME}: bbox cm  X {lo.x*100:.1f}..{hi.x*100:.1f}  Y {lo.y*100:.1f}..{hi.y*100:.1f}"
          f"  Z {lo.z*100:.1f}..{hi.z*100:.1f}")
    print(f"{NAME}: size cm  {d.x:.1f} x {d.y:.1f} x {d.z:.1f}")
    print("=" * 60)
    if not args.no_render:
        previews(ob, out, args.samples, args.views.split(","), centres)


main()
