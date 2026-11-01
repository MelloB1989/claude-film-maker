"""her_outfit: the female presenter's fitted outfit, a cream ribbed knit top tucked into high-rise charcoal tailored
trousers, as skinned garments on her own skeleton (metahuman_base_skel). The olive overshirt (overshirt.py, agent-05)
goes over the top.

Fitted to her uncut A-pose body as exported from Unreal after the rebuild without MetaHuman's default garment
(her_outfit_ue/export_body.py -> body.fbx, face.fbx, idle.fbx).

Run headless (on the Mac, through the fleet wrapper; scipy from --pylib):
    blender -b --factory-startup -P her_outfit.py -- --src <dir with the UE FBXs> --out <out dir> [--stage all]

Frame (cm): her left +X, her front -Y, up +Z (her skeleton's frame, as exported).

How it is made
  Her body is voxelised (0.4 cm) into a signed distance field.
  Top     a stack of horizontal slices of her torso, each slice's convex hull (the knit bridges the cleavage and the
          spine), closed vertically with a parabola so it bridges under the bust but keeps the waist; short sleeves as
          tubes round the upper arms; joined with a smooth union, meshed (surface nets), cut (square neckline, sleeve
          ends, the tucked hem inside the trousers), relaxed, a few millimetres off her skin. Then the rib bindings at
          the neckline and the sleeve ends, shoulder/side/armhole seams, a soft blouse over the waistband, a few drag
          lines from the bust, thickness. The rib itself is a normal map (her_outfit_maps.py), wales along V.
  Trousers  her lower body's distance field, closed (2.5 cm) so the cloth bridges the seat and the crotch, eased,
          with straight legs from the knee down and the top's tuck inside the waist. Built as four panels (left/right
          front and back) of a pattern grid: each row is a horizontal section of that field, the columns are placed
          by arc length between the side seam, the pressed crease and the inseam / centre seam, so the seams and the
          creases are exact edge lines. Waistband with a gold button, fly topstitching, slanted front pockets, back
          welts and darts, a clean hem at the ankle bone, a sharp pressed crease front and back.
  Skinning  weights from her body (nearest face, interpolated; sleeves from the arms only, legs per side, no foot
          bones), smoothed over each garment, max 8 influences; checked by posing and by her idle.

Material slots: M_Top (cream rib knit), M_Trousers (charcoal wool), M_Hardware (the gold button).
UVs: world scale (1 UV = 1 m); the top's wales (V) run up the body and along each sleeve, the trousers' grain (V) down
each panel.
"""

import argparse
import json
import math
import os
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

NAME = "her_outfit"

# ---------------------------------------------------------------- fit (cm)
VOX = 0.4                       # body voxels
TOP = dict(
    clear=0.32,                 # her skin to the top's inner face
    thick=0.16,                 # the knit
    rho_front=3.0, rho_back=3.0, rho_side=1.5,   # vertical bridging (parabola radius) by side
    neck_hw=8.6,                # the square neckline: half width
    neck_drop=3.2,              # its front edge below the sternal notch
    neck_r=1.8,                 # its corner radius
    back_drop=3.4,              # the back neckline below the base of her neck at the centre
    sleeve=11.5,                # sleeve length from the shoulder joint, along the upper arm
    tuck=6.5,                   # the tucked hem: this far below the trousers' waist edge
    bind=1.0,                   # rib binding width (neckline, sleeve ends)
    grid=0.5,                   # surface-net voxel
    bridge=0.82,                # how much of a hollow across a slice the knit bridges (1: straight across)
)
TROUSERS = dict(
    close=2.5,                  # the bridging (closing radius) of her lower body
    ease_waist=0.55, ease_hip=0.75, ease_thigh=1.25, ease_knee=1.6,
    band=4.0,                   # waistband height
    rise=0.0,                   # waist edge above her natural waist
    hem_above_ankle=0.0,        # the hem: at the ankle bone (foot_l joint) + this
    leg_hem_r=7.1, leg_knee_r=6.9,   # straight leg: least half-girth (cm) at the knee and the hem
    crease_h=0.2, crease_w=1.1,
    thick=0.08, band_thick=0.22,
)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog=NAME)
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--src", default=os.path.join(here, "out", "her_outfit_ue"))
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument("--pylib", default="")
    ap.add_argument("--stage", default="all", help="measure | top | trousers | all")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-tests", action="store_true")
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--tag", default="")
    return ap.parse_args(argv)


ARGS = parse_args()
if ARGS.pylib:
    sys.path.append(ARGS.pylib)          # after Blender's own numpy
from scipy import ndimage  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402


def log(*a):
    print(f"[{NAME}]", *a, flush=True)


# ================================================================ her, from the FBX exports

def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def mesh_arrays(ob):
    """World-space verts (cm), triangles and per-vertex bone weights {group: array}."""
    me = ob.data
    X = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", X)
    M = np.array(ob.matrix_world)
    X = (M @ np.c_[X.reshape(-1, 3), np.ones(len(me.vertices))].T).T[:, :3] * 100.0
    me.calc_loop_triangles()
    T = np.zeros(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", T)
    W = {}
    names = {g.index: g.name for g in ob.vertex_groups}
    for v in me.vertices:
        for g in v.groups:
            if g.weight > 1e-4:
                W.setdefault(names[g.group], np.zeros(len(me.vertices)))[v.index] = g.weight
    return X, T.reshape(-1, 3), W


def chain_weight(W, n, keys, side=None):
    w = np.zeros(n)
    for g, a in W.items():
        if side and not g.endswith(side):
            continue
        if any(k in g for k in keys):
            w += a
    return np.clip(w, 0, 1)


ARM_KEYS = ("upperarm", "lowerarm", "hand", "index", "middle", "ring", "pinky", "thumb", "wrist")
LEG_KEYS = ("thigh", "calf", "foot", "ball", "toe", "knee", "ankle")
FOOT_KEYS = ("foot", "ball", "toe", "ankle")


class Her:
    """Her reference A-pose: the armature, the body, the face (neck), landmarks."""

    def __init__(self, src):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        objs = import_fbx(os.path.join(src, "body.fbx"))
        self.arm = next(o for o in objs if o.type == "ARMATURE")
        self.body_ob = next(o for o in objs if o.type == "MESH")
        self.face_ob = None
        fp = os.path.join(src, "face.fbx")
        if os.path.exists(fp):
            fo = import_fbx(fp)
            self.face_ob = next((o for o in fo if o.type == "MESH"), None)
        self.bone = {b.name: np.array((self.arm.matrix_world @ b.head_local)[:]) * 100.0 for b in self.arm.data.bones}
        self.bx, self.bt, self.bw = mesh_arrays(self.body_ob)
        n = len(self.bx)
        self.armw = chain_weight(self.bw, n, ARM_KEYS)
        self.legw = chain_weight(self.bw, n, LEG_KEYS)
        self.footw = chain_weight(self.bw, n, FOOT_KEYS)
        if self.face_ob is not None:
            self.fx, self.ft, _ = mesh_arrays(self.face_ob)
        self.bvh = BVHTree.FromPolygons(self.bx.tolist(), self.bt.tolist())
        log(f"body verts {n} tris {len(self.bt)}  bbox {self.bx.min(0).round(1)} {self.bx.max(0).round(1)}")

    def colliders(self):
        parts = [(self.bx, self.bt)]
        if self.face_ob is not None:
            parts.append((self.fx, self.ft))
        return parts


# ================================================================ her body as a distance field

class Field:
    """A regular grid of values (cm frame) with trilinear lookups."""

    def __init__(self, lo, h, A):
        self.lo, self.h, self.A = np.asarray(lo, float), float(h), A

    def __call__(self, P):
        c = ((np.asarray(P) - self.lo) / self.h).T
        return ndimage.map_coordinates(self.A, c, order=1, mode="nearest")

    def coords(self):
        return [self.lo[i] + np.arange(self.A.shape[i]) * self.h for i in range(3)]


def voxelise(her, lo, hi, h):
    """Inside/outside of her body on a grid, by ray parity along +X, one ray per (y, z) row."""
    n = np.ceil((np.asarray(hi) - lo) / h).astype(int) + 1
    xs = lo[0] + np.arange(n[0]) * h
    inside = np.zeros(n, bool)
    x_start = float(her.bx[:, 0].min() - 5.0)
    t0 = time.time()
    for j in range(n[1]):
        y = lo[1] + j * h
        for k in range(n[2]):
            z = lo[2] + k * h
            o = Vector((x_start, y + 1e-4, z + 1.3e-4))
            hits = []
            d = Vector((1, 0, 0))
            for _ in range(40):
                loc, nor, fi, dist = her.bvh.ray_cast(o, d)
                if loc is None:
                    break
                hits.append(loc.x)
                o = loc + d * 1e-3
            if len(hits) < 2:
                continue
            if len(hits) % 2:  # a grazing hit: drop the closest pair duplicate
                hits = hits[:-1]
            for a, b in zip(hits[0::2], hits[1::2]):
                inside[(xs >= a) & (xs <= b), j, k] = True
    log(f"voxelise: grid {tuple(n)} {time.time() - t0:.0f}s, inside {inside.mean() * 100:.1f}%")
    return inside


def sdf_of(inside, h):
    """Signed distance (cm, outside > 0) of a voxel set."""
    if not inside.any():
        return np.full(inside.shape, 99.0)
    dout = ndimage.distance_transform_edt(~inside, sampling=h)
    din = ndimage.distance_transform_edt(inside, sampling=h)
    return dout - din + np.where(inside, h * 0.5, -h * 0.5)


def closing(inside, r, h):
    """Morphological closing by a ball of radius r (cm): concavities narrower than 2r are bridged."""
    dout = ndimage.distance_transform_edt(~inside, sampling=h)
    dil = dout <= r
    d2 = ndimage.distance_transform_edt(dil, sampling=h)
    return d2 > r


class Body:
    def __init__(self, her):
        self.lo = np.array((-34.0, -24.0, 0.0))
        self.hi = np.array((34.0, 20.0, 150.0))
        self.inside = voxelise(her, self.lo, self.hi, VOX)
        self.sd = Field(self.lo, VOX, sdf_of(self.inside, VOX).astype(np.float32))


# ================================================================ landmarks and measurements

def slice_points(X, T, z, keep=None):
    """Points where triangles cross the plane at height z (x, y), optionally only triangles whose verts all keep."""
    Tz = X[T, 2]
    m = (Tz.min(1) <= z) & (Tz.max(1) > z)
    if keep is not None:
        m &= keep[T].all(1)
    tri = T[m]
    out = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        pa, pb = X[tri[:, a]], X[tri[:, b]]
        za, zb = pa[:, 2], pb[:, 2]
        c = (za - z) * (zb - z) < 0
        t = (z - za[c]) / (zb[c] - za[c])
        out.append(pa[c, :2] + (pb[c, :2] - pa[c, :2]) * t[:, None])
    return np.concatenate(out) if out else np.zeros((0, 2))


def convex_hull_2d(P):
    P = np.unique(np.round(P, 3), axis=0)
    if len(P) < 3:
        return P
    P = P[np.lexsort((P[:, 1], P[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, hi = [], []
    for p in P:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(tuple(p))
    for p in P[::-1]:
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(tuple(p))
    return np.array(lo[:-1] + hi[:-1])


def hull_perimeter(H):
    return float(np.linalg.norm(np.roll(H, -1, 0) - H, axis=1).sum()) if len(H) > 2 else 0.0


def loop_perimeter(P, c):
    """Perimeter of a slice's outline measured round its centre (a tape over the hollows' rims: the hull)."""
    return hull_perimeter(convex_hull_2d(P))


def polar_radius(hull, c, angles):
    """Radius of a convex polygon (containing c) along each angle."""
    A = hull - c
    B = np.roll(A, -1, axis=0)
    e = B - A
    d = np.stack([np.cos(angles), np.sin(angles)], 1)                      # (na, 2)
    den = d[:, None, 0] * e[None, :, 1] - d[:, None, 1] * e[None, :, 0]    # (na, ne)
    ok = np.abs(den) > 1e-9
    dd = np.where(ok, den, 1)
    s = np.where(ok, (A[None, :, 0] * e[None, :, 1] - A[None, :, 1] * e[None, :, 0]) / dd, -1)
    u = np.where(ok, (A[None, :, 0] * d[:, None, 1] - A[None, :, 1] * d[:, None, 0]) / dd, -1)
    hit = ok & (s > 0) & (u >= -1e-6) & (u <= 1 + 1e-6)
    return np.where(hit, s, 0).max(1)


def polar_outer(P, c, angles):
    """Outermost radius of a slice's points per angle (each angle bin's farthest point, gaps interpolated)."""
    d = P - c
    r = np.hypot(d[:, 0], d[:, 1])
    th = np.arctan2(d[:, 1], d[:, 0])
    na = len(angles)
    b = np.floor((th - angles[0]) / (2 * math.pi) * na).astype(int) % na
    R = np.zeros(na)
    np.maximum.at(R, b, r)
    ok = R > 0
    if ok.sum() >= 3:
        R = np.interp(angles, angles[ok], R[ok], period=2 * math.pi)
    return smooth1d(R, 1.0, wrap=True)


def smooth1d(a, sigma, axis=0, wrap=False):
    if sigma <= 0:
        return a
    return ndimage.gaussian_filter1d(a, sigma, axis=axis, mode="wrap" if wrap else "nearest")


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def smin(a, b, k):
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


class Marks:
    """Her landmarks (cm) and the tape measurements, from the body."""

    def __init__(self, her):
        self.her = her
        X, T = her.bx, her.bt
        torso = (her.armw < 0.5) & (her.legw < 0.5)
        B = her.bone
        self.cy = 0.5 * (B["spine_03"][1] + B["pelvis"][1])
        zs = np.arange(60.0, 140.0, 0.5)
        girth = []
        for z in zs:
            P = slice_points(X, T, z, her.armw < 0.5)
            girth.append(loop_perimeter(P, None) if len(P) > 5 else 0.0)
        g = np.array(girth)
        self.zs, self.girth = zs, g
        m = (zs > 98) & (zs < 118)
        self.z_waist = float(zs[m][np.argmin(g[m])])
        m = (zs > 112) & (zs < 132)
        self.z_bust = float(zs[m][np.argmax(g[m])])
        m = (zs > 75) & (zs < 96)
        self.z_hip = float(zs[m][np.argmax(g[m])])
        # under the bust: the tape at the fold, through the hollows (not the hull)
        self.z_underbust = self._underbust()
        # the crotch: lowest point between the legs, from below
        o = Vector((0.0, self.cy, 30.0))
        loc, *_ = her.bvh.ray_cast(o, Vector((0, 0, 1)))
        self.z_crotch = float(loc.z) if loc else 75.0
        # the base of the neck, the sternal notch (front, at x=0)
        self.z_notch = self._notch()
        self.z_neck_back = float(B["neck_01"][2]) - 1.0
        self.ankle = 0.5 * (B["foot_l"] + B["foot_r"] * np.array((-1, 1, 1)))
        self.knee = 0.5 * (B["calf_l"] + B["calf_r"] * np.array((-1, 1, 1)))
        self.hipj = 0.5 * (B["thigh_l"] + B["thigh_r"] * np.array((-1, 1, 1)))
        self.shoulder = 0.5 * (B["upperarm_l"] + B["upperarm_r"] * np.array((-1, 1, 1)))
        self.elbow = 0.5 * (B["lowerarm_l"] + B["lowerarm_r"] * np.array((-1, 1, 1)))

    def _underbust(self):
        her = self.her
        best = None
        for z in np.arange(self.z_bust - 14, self.z_bust - 4, 0.5):
            P = slice_points(her.bx, her.bt, z, her.armw < 0.5)
            g = loop_perimeter(P, None)
            if best is None or g < best[1]:
                best = (z, g)
        return float(best[0])

    def _notch(self):
        her = self.her
        best = None
        for z in np.arange(128.0, 146.0, 0.25):
            loc, *_ = her.bvh.ray_cast(Vector((0.0, -40.0, z)), Vector((0, 1, 0)))
            if loc is None:
                continue
            # the notch: the deepest point (largest y) of the front profile between the chest and the neck
            if best is None or loc.y > best[1] + 1e-6:
                best = (z, loc.y)
        return float(best[0]) if best else 136.0

    def girth_at(self, z, arm_free=True):
        P = slice_points(self.her.bx, self.her.bt, z, (self.her.armw < 0.5) if arm_free else None)
        return loop_perimeter(P, None)

    def report(self):
        g = lambda z: round(self.girth_at(z), 1)
        r = {
            "bust": [self.z_bust, g(self.z_bust)], "underbust": [self.z_underbust, g(self.z_underbust)],
            "waist": [self.z_waist, g(self.z_waist)], "hip": [self.z_hip, g(self.z_hip)],
            "crotch_z": round(self.z_crotch, 1), "notch_z": self.z_notch, "neck_back_z": round(self.z_neck_back, 1),
            "ankle": self.ankle.round(1).tolist(), "knee": self.knee.round(1).tolist(),
            "shoulder": self.shoulder.round(1).tolist(), "elbow": self.elbow.round(1).tolist(), "cy": round(self.cy, 1),
        }
        log("marks " + json.dumps(r))
        return r


# ================================================================ meshing helpers

def surface_nets(F, origin, h):
    """Quad mesh of the zero level of a sampled field F (inside < 0); normals point to +F (outside)."""
    nx, ny, nz = F.shape
    cell_sum = np.zeros((nx - 1, ny - 1, nz - 1, 3))
    cell_cnt = np.zeros((nx - 1, ny - 1, nz - 1))
    edges = []
    for ax in range(3):
        sl0 = [slice(None)] * 3
        sl1 = [slice(None)] * 3
        sl0[ax] = slice(0, -1)
        sl1[ax] = slice(1, None)
        f0, f1 = F[tuple(sl0)], F[tuple(sl1)]
        x = (f0 < 0) != (f1 < 0)
        idx = np.argwhere(x)
        t = f0[x] / (f0[x] - f1[x])
        p = idx.astype(float)
        p[:, ax] += t
        o = [a for a in range(3) if a != ax]
        for da in (0, 1):
            for db in (0, 1):
                c = idx.copy()
                c[:, o[0]] -= da
                c[:, o[1]] -= db
                ok = (c >= 0).all(1) & (c[:, 0] < nx - 1) & (c[:, 1] < ny - 1) & (c[:, 2] < nz - 1)
                np.add.at(cell_sum, tuple(c[ok].T), p[ok])
                np.add.at(cell_cnt, tuple(c[ok].T), 1)
        edges.append((ax, idx, f0[x] < 0))
    act = cell_cnt > 0
    vid = -np.ones(cell_cnt.shape, int)
    vid[act] = np.arange(act.sum())
    V = origin + cell_sum[act] / cell_cnt[act][:, None] * h
    quads = []
    for ax, idx, inner_low in edges:
        o = [a for a in range(3) if a != ax]
        cs = []
        for da, db in ((1, 1), (0, 1), (0, 0), (1, 0)):
            c = idx.copy()
            c[:, o[0]] -= da
            c[:, o[1]] -= db
            cs.append(c)
        ok = np.ones(len(idx), bool)
        for c in cs:
            ok &= (c >= 0).all(1) & (c[:, 0] < nx - 1) & (c[:, 1] < ny - 1) & (c[:, 2] < nz - 1)
        q = np.stack([vid[tuple(c[ok].T)] for c in cs], 1)
        flip = ~inner_low[ok]
        if (o[0] - ax) % 3 != 1:
            flip = ~flip
        q[flip] = q[flip][:, ::-1]
        quads.append(q)
    Q = np.concatenate(quads)
    Q = Q[(Q >= 0).all(1)]
    return V, Q


def edges_of(F):
    E = set()
    for f in F:
        k = len(f)
        for i in range(k):
            a, b = int(f[i]), int(f[(i + 1) % k])
            E.add((min(a, b), max(a, b)))
    return np.array(sorted(E), int)


def nbr_lists(n, F):
    E = edges_of(F)
    nb = [[] for _ in range(n)]
    for a, b in E:
        nb[a].append(b)
        nb[b].append(a)
    return [np.array(x, int) for x in nb]


def boundary_edges(F):
    cnt = {}
    for f in F:
        k = len(f)
        for i in range(k):
            a, b = int(f[i]), int(f[(i + 1) % k])
            key = (min(a, b), max(a, b))
            cnt[key] = cnt.get(key, 0) + 1
    return [e for e, c in cnt.items() if c == 1]


def boundary_loops(F):
    """Ordered boundary loops (vertex lists)."""
    nxt = {}
    for f in F:
        k = len(f)
        for i in range(k):
            a, b = int(f[i]), int(f[(i + 1) % k])
            nxt[(a, b)] = True
    succ = {}
    for (a, b) in nxt:
        if (b, a) not in nxt:
            succ[a] = b
    loops, seen = [], set()
    for s in list(succ):
        if s in seen:
            continue
        loop, v = [], s
        while v not in seen and v in succ:
            seen.add(v)
            loop.append(v)
            v = succ[v]
        if len(loop) > 2:
            loops.append(loop)
    return loops


class Lap:
    """Uniform Laplacian over a mesh's edges (sparse-free: neighbour index arrays padded)."""

    def __init__(self, n, F):
        nb = nbr_lists(n, F)
        k = max(len(x) for x in nb)
        self.idx = np.zeros((n, k), int)
        self.w = np.zeros((n, k))
        for i, x in enumerate(nb):
            if len(x):
                self.idx[i, :len(x)] = x
                self.w[i, :len(x)] = 1.0 / len(x)
        self.deg = np.array([len(x) for x in nb])

    def avg(self, X):
        return (X[self.idx] * self.w[..., None]).sum(1) if X.ndim == 2 else (X[self.idx] * self.w).sum(1)


def vertex_normals(X, F):
    T = tri_split(F)
    fn = np.cross(X[T[:, 1]] - X[T[:, 0]], X[T[:, 2]] - X[T[:, 0]])
    vn = np.zeros_like(X)
    for k in range(3):
        np.add.at(vn, T[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1)[:, None], 1e-12)


def tri_split(F):
    T = []
    for f in F:
        for k in range(1, len(f) - 1):
            T.append((f[0], f[k], f[k + 1]))
    return np.array(T, int)


def taubin(X, lap, iters, fixed=None, lam=0.5, mu=-0.53):
    X = X.copy()
    for _ in range(iters):
        for w in (lam, mu):
            d = (lap.avg(X) - X) * w
            if fixed is not None:
                d[fixed] = 0
            X += d
    return X


def tangential_relax(X, F, lap, iters, fixed=None, lam=0.5):
    X = X.copy()
    for _ in range(iters):
        n = vertex_normals(X, F)
        d = lap.avg(X) - X
        d -= n * (d * n).sum(1)[:, None]
        if fixed is not None:
            d[fixed] = 0
        X += lam * d
    return X


class Surf:
    """Closest-point queries on her (cm): body and neck."""

    def __init__(self, her):
        V, T = [], []
        for X, F in her.colliders():
            T.append(F + sum(len(v) for v in V))
            V.append(X)
        self.V, self.T = np.concatenate(V), np.concatenate(T)
        self.bvh = BVHTree.FromPolygons(self.V.tolist(), self.T.tolist())

    def signed(self, P, maxd=10.0):
        d = np.full(len(P), 99.0)
        n = np.zeros((len(P), 3))
        for i, p in enumerate(P):
            loc, nor, _, dist = self.bvh.find_nearest(Vector(p), maxd)
            if loc is None:
                continue
            v = Vector(p) - loc
            s = 1.0 if v.dot(nor) >= 0 else -1.0
            d[i] = s * dist
            n[i] = (v.normalized() * s)[:] if dist > 1e-6 else nor[:]
        return d, n


def push_out(X, surf, clear, iters=3, lap=None, F=None, mask=None):
    """Move verts closer than `clear` to her out to it (then a touch of tangential relaxing)."""
    for it in range(iters):
        d, n = surf.signed(X)
        bad = d < clear
        if mask is not None:
            bad &= mask
        X[bad] += n[bad] * (clear - d[bad])[:, None]
        log(f"push_out {it}: {bad.sum()} verts closer than {clear} cm (min {d.min():.2f})")
        if lap is not None and F is not None and it < iters - 1:
            X = tangential_relax(X, F, lap, 2)
    return X


# ================================================================ objects, materials, previews

def arrays_object(name, X_cm, faces, mats=(), mat_idx=None, uvs=None, sharp=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata((np.asarray(X_cm) * 0.01).tolist(), [], [list(map(int, f)) for f in faces])
    me.update()
    for m in mats:
        me.materials.append(m)
    if mat_idx is not None:
        me.polygons.foreach_set("material_index", np.asarray(mat_idx, np.int32))
    if uvs is not None:
        uvl = me.uv_layers.new(name="UVMap")
        flat = [c for f in uvs for c in f]
        uvl.data.foreach_set("uv", np.asarray(flat, np.float32).reshape(-1))
    me.shade_smooth()
    if sharp:
        E = {tuple(sorted(e.vertices)): e.index for e in me.edges}
        attr = me.attributes.get("sharp_edge") or me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
        vals = np.zeros(len(me.edges), bool)
        for a, b in sharp:
            i = E.get((min(a, b), max(a, b)))
            if i is not None:
                vals[i] = True
        attr.data.foreach_set("value", vals)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def snapshot(path, objs_colors, views, centre=(0, 0, 1.12), dist=3.2, ortho=1.15, res=(900, 1100)):
    """Quick workbench renders of the listed objects (object colour), for checking the fit."""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "OBJECT"
    sh.show_cavity = True
    sh.cavity_type = "WORLD"
    sh.show_specular_highlight = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    for ob in sc.objects:
        ob.hide_render = ob not in objs_colors
    for ob, col in objs_colors.items():
        ob.color = (*col, 1.0)
    cd = bpy.data.cameras.get("_snap") or bpy.data.cameras.new("_snap")
    cd.type = "ORTHO"
    cd.ortho_scale = ortho
    cam = bpy.data.objects.get("_snap") or bpy.data.objects.new("_snap", cd)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    out = []
    for name, d in views:
        d = Vector(d).normalized()
        c = Vector(centre)
        cam.location = c - d * dist
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = f"{path}_{name}.png"
        bpy.ops.render.render(write_still=True)
        out.append(sc.render.filepath)
    return out


VIEWS = (("front", (0, 1, 0)), ("q", (0.62, 1, -0.12)), ("side", (-1, 0, 0)), ("back", (0, -1, 0)))
SKIN = (0.72, 0.5, 0.4)


# ================================================================ the top

class TopShape:
    """The top's volume: torso slices (hull, bridged vertically) and sleeve tubes, smooth-unioned."""

    NANG = 240

    def __init__(self, her, marks, z_lo):
        self.her, self.mk = her, marks
        self.c = np.array((0.0, marks.cy))
        self.z_lo = z_lo
        X, T = her.bx, her.bt
        keep = her.armw < 0.5
        top = float(X[keep, 2].max())
        self.zs = np.arange(z_lo - 2.0, top + 0.01, 0.5)
        self.ang = np.linspace(-math.pi, math.pi, self.NANG, endpoint=False)
        R = np.zeros((len(self.zs), self.NANG))
        for i, z in enumerate(self.zs):
            P = slice_points(X, T, z, keep)
            if len(P) < 8:
                R[i] = R[i - 1] if i else 0
                continue
            # the neck above the shoulders is its own slice: keep only what is near the centre there
            hull = polar_radius(convex_hull_2d(P), self.c, self.ang)
            raw = polar_outer(P, self.c, self.ang)
            # the knit bridges the hollows (cleavage, spine) only partly: tension pulls it a little into them
            R[i] = raw + TOP["bridge"] * (hull - raw)
        self.raw = R.copy()
        # vertical bridging: a closing of each angle's radius profile with a parabola (radius by side)
        dy = np.sin(self.ang)
        rho = TOP["rho_side"] + (TOP["rho_front"] - TOP["rho_side"]) * smoothstep(0.3, 0.85, -dy) \
            + (TOP["rho_back"] - TOP["rho_side"]) * smoothstep(0.3, 0.85, dy)
        Rc = R.copy()
        zz = self.zs
        # only below the armpits: above, the slices follow her (shoulders, neck)
        z_arm = marks.shoulder[2] - 10.0
        for a in range(self.NANG):
            f = R[:, a]
            D = (f[None, :] - (zz[:, None] - zz[None, :]) ** 2 / (2 * rho[a])).max(1)
            C = (D[None, :] + (zz[:, None] - zz[None, :]) ** 2 / (2 * rho[a])).min(1)
            w = 1 - smoothstep(z_arm - 3, z_arm + 2, zz)
            Rc[:, a] = f + (np.maximum(C, f) - f) * w
        Rc = smooth1d(Rc, 1.5, axis=1, wrap=True)
        Rc = smooth1d(Rc, 0.8, axis=0)
        self.R = np.maximum(Rc, R) + TOP["clear"]
        self.ztop = top
        # sleeves
        self.arms = [Sleeve(her, marks, s) for s in (1, -1)]
        marks.top_shape = self
        log(f"top: slices {len(self.zs)} z {self.zs[0]:.1f}..{top:.1f}")

    def radius(self, z, th):
        zi = np.clip((z - self.zs[0]) / 0.5, 0, len(self.zs) - 1.0001)
        i0 = np.floor(zi).astype(int)
        fz = zi - i0
        ai = ((th + math.pi) / (2 * math.pi) * self.NANG) % self.NANG
        a0 = np.floor(ai).astype(int)
        fa = ai - a0
        a1 = (a0 + 1) % self.NANG
        r0 = self.R[i0, a0] * (1 - fa) + self.R[i0, a1] * fa
        r1 = self.R[i0 + 1, a0] * (1 - fa) + self.R[i0 + 1, a1] * fa
        return r0 * (1 - fz) + r1 * fz

    def torso_sdf(self, P):
        dx, dy = P[:, 0] - self.c[0], P[:, 1] - self.c[1]
        r = np.hypot(dx, dy)
        d = r - self.radius(P[:, 2], np.arctan2(dy, dx))
        d = np.maximum(d, P[:, 2] - self.ztop - TOP["clear"])
        return np.maximum(d, self.zs[0] - P[:, 2])

    def sdf(self, P):
        f = self.torso_sdf(P)
        fa = np.minimum(self.arms[0].sdf(P), self.arms[1].sdf(P))
        return smin(f, fa, 2.2)


class Sleeve:
    """A short fitted sleeve: a tube round the upper arm, per angle round the bone, her arm + clearance."""

    NPHI = 24

    def __init__(self, her, marks, side):
        s = "_l" if side > 0 else "_r"
        self.side = side
        self.sh, self.el = her.bone["upperarm" + s], her.bone["lowerarm" + s]
        self.L = float(np.linalg.norm(self.el - self.sh))
        self.u = (self.el - self.sh) / self.L
        b1 = np.cross(self.u, (0.0, 1.0, 0.0))
        self.b1 = b1 / np.linalg.norm(b1)
        self.b2 = np.cross(self.u, self.b1)
        armw = chain_weight(her.bw, len(her.bx), ("upperarm", "lowerarm"), s)
        sel = (armw > 0.5) | ((np.sign(her.bx[:, 0]) == side) & (np.abs(her.bx[:, 0]) > abs(self.sh[0]) + 2))
        P = her.bx[sel]
        t, d, phi = self.coords(P)
        self.ts = np.arange(-1.5, TOP["sleeve"] + 6.01, 0.5)
        self.phis = np.linspace(-math.pi, math.pi, self.NPHI, endpoint=False)
        R = np.zeros((len(self.ts), self.NPHI))
        near = d < 8.5
        for i, x in enumerate(self.ts):
            m = near & (np.abs(t - x) < 0.8)
            if m.sum() < 6:
                continue
            for j, p in enumerate(self.phis):
                dp = np.angle(np.exp(1j * (phi[m] - p)))
                k = np.abs(dp) < math.pi / self.NPHI * 1.6
                if k.sum() >= 2:
                    R[i, j] = d[m][k].max()
        # fill gaps (the shoulder joint end) from the neighbours
        for j in range(self.NPHI):
            col = R[:, j]
            ok = col > 0
            if ok.sum() >= 2:
                R[:, j] = np.interp(self.ts, self.ts[ok], col[ok])
            else:
                R[:, j] = 4.5
        R = smooth1d(R, 1.2, axis=1, wrap=True)
        R = smooth1d(R, 1.5, axis=0)
        self.R = R + TOP["clear"]
        log(f"sleeve {side:+d}: L {self.L:.1f}  r {self.R.min():.1f}..{self.R.max():.1f}")

    def coords(self, P):
        q = P - self.sh
        t = q @ self.u
        r = q - np.outer(t, self.u)
        d = np.linalg.norm(r, axis=1)
        phi = np.arctan2(r @ self.b2, r @ self.b1)
        return t, d, phi

    def radius(self, t, phi):
        ti = np.clip((t - self.ts[0]) / 0.5, 0, len(self.ts) - 1.0001)
        i0 = np.floor(ti).astype(int)
        ft = ti - i0
        ai = ((phi + math.pi) / (2 * math.pi) * self.NPHI) % self.NPHI
        a0 = np.floor(ai).astype(int)
        fa = ai - a0
        a1 = (a0 + 1) % self.NPHI
        r0 = self.R[i0, a0] * (1 - fa) + self.R[i0, a1] * fa
        r1 = self.R[i0 + 1, a0] * (1 - fa) + self.R[i0 + 1, a1] * fa
        return r0 * (1 - ft) + r1 * ft

    def sdf(self, P):
        t, d, phi = self.coords(P)
        f = d - self.radius(t, phi)
        f = np.maximum(f, self.ts[0] - t)
        return np.maximum(f, t - self.ts[-1])


class TopCuts:
    """The top's openings as signed distances (> 0 where the cloth stays): the square neckline, the sleeve ends,
    the tucked hem."""

    def __init__(self, marks, shape, z_hem):
        self.mk, self.shape = marks, shape
        self.z_hem = z_hem
        self.z_front = marks.z_notch - TOP["neck_drop"]
        self.z_back = marks.z_neck_back - TOP["back_drop"]
        self.hw = TOP["neck_hw"]

    def z_open(self, P):
        """The neckline's lower edge: square in front, a shallow scoop at the back, sloping between over the
        shoulders."""
        zb = self.z_back + 1.2 * (np.abs(P[:, 0]) / self.hw) ** 2
        w = smoothstep(self.mk.cy - 4.0, self.mk.cy + 4.0, P[:, 1])
        return self.z_front + (zb - self.z_front) * w

    def neck_C(self, P):
        r = TOP["neck_r"]
        qx = np.abs(P[:, 0]) - self.hw
        qz = self.z_open(P) - P[:, 2]
        ax, az = qx + r, qz + r
        return np.hypot(np.maximum(ax, 0), np.maximum(az, 0)) + np.minimum(np.maximum(ax, az), 0) - r

    def sleeve_C(self, P, k):
        a = self.shape.arms[k]
        t, d, _ = a.coords(P)
        on = (np.sign(P[:, 0]) == a.side) & (armhole_phi(P, self.mk) > 0.5) & (d < a.R.max() + 2.5) \
            & (self.shape.torso_sdf(P) > 1.0)
        return np.where(on, TOP["sleeve"] - t, 99.0)

    def hem_C(self, P):
        return P[:, 2] - self.z_hem

    def all_C(self, P):
        return np.stack([self.hem_C(P), self.sleeve_C(P, 0), self.sleeve_C(P, 1), self.neck_C(P)], 1)

    def C(self, P):
        return self.all_C(P).min(1)


def grad(fn, P, h=0.05):
    g = np.zeros_like(P)
    for k in range(3):
        e = np.zeros(3)
        e[k] = h
        g[:, k] = (fn(P + e) - fn(P - e)) / (2 * h)
    return g


def project_to(fn, P, iters=4):
    """Newton steps onto fn = 0."""
    P = P.copy()
    for _ in range(iters):
        f = fn(P)
        g = grad(fn, P)
        P -= (f / np.maximum((g * g).sum(1), 1e-9))[:, None] * g
    return P


def keep_largest(V, Q):
    """Faces of the largest edge-connected piece."""
    n = len(V)
    parent = np.arange(n)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for q in Q:
        r0 = find(q[0])
        for v in q[1:]:
            r = find(v)
            if r != r0:
                parent[r] = r0
    roots = np.array([find(q[0]) for q in Q])
    u, c = np.unique(roots, return_counts=True)
    return Q[roots == u[np.argmax(c)]]


def compact(V, Q):
    used = np.unique(np.concatenate([np.asarray(q) for q in Q]))
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    return V[used], [remap[np.asarray(q)] for q in Q]


def clean_mesh(V, Q, hole_sides=12):
    """Split non-manifold corners, fill pinholes, drop loose bits, triangulate nothing: quads stay quads."""
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in V]
    for q in Q:
        try:
            bm.faces.new([vs[i] for i in q])
        except ValueError:
            pass
    bad = [v for v in bm.verts if not v.is_manifold and v.link_faces]
    if bad:
        bmesh.ops.split_edges(bm, edges=list({e for v in bad for e in v.link_edges if not e.is_manifold}))
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=hole_sides)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.verts.index_update()
    bm.verts.ensure_lookup_table()
    V2 = np.array([v.co[:] for v in bm.verts])
    Q2 = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return V2, Q2


def build_top(her, marks, surf, z_hem, z_band):
    shape = TopShape(her, marks, z_hem)
    cuts = TopCuts(marks, shape, z_hem)
    h = TOP["grid"]
    lo = np.array((-30.0, marks.cy - 20.0, z_hem - 3.0))
    hi = np.array((30.0, marks.cy + 18.0, shape.ztop + 3.0))
    n = np.ceil((hi - lo) / h).astype(int) + 1
    g = np.stack(np.meshgrid(*[lo[i] + np.arange(n[i]) * h for i in range(3)], indexing="ij"), -1).reshape(-1, 3)
    t0 = time.time()
    fs = shape.sdf(g)
    F = np.maximum(fs, -cuts.C(g)).reshape(tuple(n))
    V, Q = surface_nets(F, lo, h)
    log(f"top envelope: grid {tuple(n)} {time.time() - t0:.1f}s verts {len(V)} quads {len(Q)}")
    # the caps the cuts leave are inside the cloth's volume: drop them, keep the main piece
    cen = V[Q].mean(1)
    cap = np.abs(shape.sdf(cen)) > np.abs(cuts.C(cen))
    Q = Q[~cap]
    Q = keep_largest(V, Q)
    V, Q = compact(V, Q)
    V, Q = clean_mesh(V, Q)
    lap = Lap(len(V), Q)
    loops = boundary_loops(Q)
    bnd = np.zeros(len(V), bool)
    names = ["hem", "sleeve L", "sleeve R", "neck"]
    loop_kind = []
    for loop in loops:
        L = np.array(loop)
        bnd[L] = True
        w = int(np.bincount(np.abs(cuts.all_C(V[L])).argmin(1), minlength=4).argmax())
        loop_kind.append(w)
        log(f"opening {names[w]}: {len(L)} verts")
    on_cut = lambda k: (lambda P: cuts.all_C(P)[:, k])
    for it in range(12):
        for L, w in zip(loops, loop_kind):
            L = np.array(L)
            P = V[L]
            if it:
                P = P + 0.5 * (0.5 * (np.roll(P, 1, 0) + np.roll(P, -1, 0)) - P)
            P = project_to(on_cut(w), P, 2)
            P = project_to(shape.sdf, P, 2)
            V[L] = project_to(on_cut(w), P, 2)
        V = tangential_relax(V, Q, lap, 2, fixed=bnd)
    V = tangential_relax(V, Q, lap, 12, fixed=bnd)
    V = taubin(V, lap, 8, fixed=bnd)
    V = push_out(V, surf, TOP["clear"] * 0.85, iters=3, lap=lap, F=Q)
    V = smooth_openings(V, Q, lap, loops, loop_kind, cuts, shape, surf, bnd)
    return dict(V=V, Q=Q, shape=shape, cuts=cuts, lap=lap, bnd=bnd, loops=loops, loop_kind=loop_kind)


def smooth_openings(V, Q, lap, loops, loop_kind, cuts, shape, surf, bnd, clear=None):
    """Even the open edges along their length (on their cut curves), then let the strip inside follow; never into her."""
    clear = TOP["clear"] * 0.85 if clear is None else clear
    for it in range(10):
        for L, w in zip(loops, loop_kind):
            L = np.array(L)
            P = V[L]
            P = P + 0.5 * (0.5 * (np.roll(P, 1, 0) + np.roll(P, -1, 0)) - P)
            P = project_to(lambda X, w=w: cuts.all_C(X)[:, w], P, 2)
            d, nrm = surf.signed(P)
            bad = d < clear
            P[bad] += nrm[bad] * (clear - d[bad])[:, None]
            V[L] = P
        V = tangential_relax(V, Q, lap, 1, fixed=bnd)
    # the rows next to the edge: a few Laplacian passes with the edge held
    ring = np.zeros(len(V), bool)
    for i in np.where(bnd)[0]:
        ring[lap.idx[i, :lap.deg[i]]] = True
    ring &= ~bnd
    for _ in range(4):
        A = lap.avg(V)
        V[ring] += 0.5 * (A[ring] - V[ring])
    return V


# ---------------------------------------------------------------- top: detail

def armhole_phi(P, marks, side_of=None):
    """Signed distance-like value past the armhole seam (> 0 on the sleeve): where the sleeve's tube is nearer than
    the torso's volume, i.e. the junction of the two (a set-in sleeve's seam)."""
    sh = marks.top_shape
    ft = sh.torso_sdf(P)
    fa = np.minimum(sh.arms[0].sdf(P), sh.arms[1].sdf(P))
    phi = 0.5 * (ft - fa)
    # under the arm the junction is the underarm; below it everything is body
    z1 = marks.shoulder[2] - 13.0
    return np.where(P[:, 2] < z1, np.minimum(phi, (P[:, 2] - z1) * 2.0), phi)


def top_detail(top, her, marks, surf):
    """Bindings, seams, the blouse over the waistband, drag lines; then thickness and UVs."""
    V, Q, cuts, shape = top["V"].copy(), top["Q"], top["cuts"], top["shape"]
    n = len(V)
    N = vertex_normals(V, Q)
    lap = top["lap"]
    # distance (along the surface, approximated by graph distance) from each opening
    dist_open = np.full(n, 99.0)
    open_kind = np.full(n, -1)
    for L, w in zip(top["loops"], top["loop_kind"]):
        d, _ = cKDTree(V[np.array(L)]).query(V)
        m = d < dist_open
        dist_open[m] = d[m]
        open_kind[m] = w
    disp = np.zeros(n)
    # rib bindings (neck, sleeve ends): a band standing 0.07 cm proud, with a soft step and a stitch line inside
    bind = (open_kind == 3) | (open_kind == 1) | (open_kind == 2)
    bw = TOP["bind"]
    band = bind * (1 - smoothstep(bw - 0.12, bw + 0.12, dist_open))
    disp += 0.07 * band
    disp += bind * (-0.035 * np.exp(-((dist_open - (bw + 0.2)) / 0.09) ** 2))   # the coverstitch beside it
    # seams: shoulder (over the top of the shoulder strap), sides, armholes: shallow valleys
    ah = armhole_phi(V, marks)
    under_arm = V[:, 2] < marks.shoulder[2] - 8
    seam = np.zeros(n)
    seam += np.where(np.abs(V[:, 0]) > 5, np.exp(-(ah / 0.13) ** 2), 0)
    side_y = marks.cy + 1.0
    on_torso = ah < -0.5
    seam += np.where(on_torso & (V[:, 2] < marks.shoulder[2] - 9), np.exp(-((V[:, 1] - side_y) / 0.13) ** 2)
                     * (np.abs(V[:, 0]) > 8), 0)
    # the shoulder seam: along the top of the strap (where the front meets the back)
    sh_line = shape.c[1] + 0.5
    seam += np.where(on_torso & (V[:, 2] > marks.shoulder[2] - 2) & (np.abs(V[:, 0]) > TOP["neck_hw"] - 0.3),
                     np.exp(-((V[:, 1] - sh_line) / 0.13) ** 2), 0)
    # sleeve underarm seam
    for a in shape.arms:
        t, d, phi = a.coords(V)
        on = (np.sign(V[:, 0]) == a.side) & (ah > 0.5)
        under = phi - (-math.pi / 2)   # b2 x u: phi = -pi/2 is the arm's underside? measured below
        seam += np.where(on, np.exp(-((d * np.angle(np.exp(1j * (phi + math.pi / 2)))) / 0.13) ** 2), 0)
    disp += -0.05 * np.clip(seam, 0, 1)
    # the blouse: just above the waistband the knit eases out a little, in soft folds
    zb = top["z_band"]
    rng = np.random.default_rng(7)
    th = np.arctan2(V[:, 1] - shape.c[1], V[:, 0])
    s_arc = th * 12.0
    folds = np.zeros(n)
    for k in range(5):
        lam = rng.uniform(2.6, 5.0)
        ph = rng.uniform(0, 2 * math.pi)
        folds += np.cos(s_arc / lam * 2 * math.pi + ph) * rng.uniform(0.5, 1.0)
    folds /= 3.0
    env = smoothstep(zb - 0.5, zb + 0.6, V[:, 2]) * (1 - smoothstep(zb + 1.0, zb + 3.8, V[:, 2]))
    disp += env * (0.12 + 0.06 * folds)
    # drag lines: from the bust towards the underarm, a few soft ripples, fading towards the bust
    ap = np.array((10.0, marks.z_bust))                          # |x|, z at the bust's apex region
    ua = np.array((abs(marks.shoulder[0]) - 1.5, marks.shoulder[2] - 12.0))
    dvec = (ua - ap) / np.linalg.norm(ua - ap)
    perp = np.array((-dvec[1], dvec[0]))
    q = np.stack([np.abs(V[:, 0]), V[:, 2]], 1) - ap
    along = q @ dvec
    across = q @ perp
    L = float(np.linalg.norm(ua - ap))
    front = V[:, 1] < shape.c[1] - 2
    env = front * smoothstep(0.25 * L, 0.65 * L, along) * (1 - smoothstep(0.85 * L, 1.05 * L, along)) \
        * np.exp(-(across / 2.6) ** 2) * (ah < -0.5)
    disp += env * 0.07 * np.sin(across / 1.15 * math.pi)
    # small of the back: two faint horizontal ripples above the blouse
    back = V[:, 1] > shape.c[1] + 4
    env = back * smoothstep(zb + 2.5, zb + 4.0, V[:, 2]) * (1 - smoothstep(zb + 7.0, zb + 9.0, V[:, 2])) \
        * np.exp(-(V[:, 0] / 7.0) ** 2)
    disp += env * 0.05 * np.sin((V[:, 2] - zb) / 2.1 * math.pi)
    # apply along the normals, then make sure the cloth still clears her
    Vd = V + N * disp[:, None]
    Vd = push_out(Vd, surf, TOP["clear"] * 0.7, iters=2)
    Vd = smooth_openings(Vd, Q, lap, top["loops"], top["loop_kind"], cuts, shape, surf, top["bnd"],
                         clear=TOP["clear"] * 0.7)
    top["Vd"] = Vd
    top["open_kind"], top["dist_open"] = open_kind, dist_open
    return top


def top_uv(top, marks):
    """Per-corner UVs (m): the torso round her (seam at the centre back), each sleeve round its arm (seam under it),
    V up the body / along the arm, so the rib's wales run vertically and along the sleeves."""
    V, Q, shape = top["V"], top["Q"], top["shape"]
    ah = armhole_phi(V, marks)
    cen = np.array([V[q].mean(0) for q in Q])
    face_sleeve = armhole_phi(cen, marks) > 0
    R_U = 12.0
    uvs = []
    for f, q in enumerate(Q):
        P = V[np.asarray(q)]
        if face_sleeve[f]:
            a = shape.arms[0] if cen[f, 0] > 0 else shape.arms[1]
            t, d, phi = a.coords(P)
            tc, dc, phc = a.coords(cen[f][None])
            # seam under the arm (phi = +-pi/2 side picked so the seam faces her body)
            ref = phc[0]
            phi = ref + np.angle(np.exp(1j * (phi - ref)))
            uvs.append([((ph * 5.0) * 0.01, (-tt) * 0.01) for ph, tt in zip(phi, t)])
        else:
            a = np.arctan2(P[:, 0], -(P[:, 1] - shape.c[1]))   # 0 at the centre front, +-pi at the back
            ac = math.atan2(cen[f, 0], -(cen[f, 1] - shape.c[1]))
            a = ac + np.angle(np.exp(1j * (a - ac)))
            uvs.append([(aa * R_U * 0.01, zz * 0.01) for aa, zz in zip(a, P[:, 2])])
    return uvs


def solidify(X, F, thick, uvs, rim_round=1.0):
    """Thicken a surface (cm): outer = X, inner = X - n*thick; rounded rims on open edges. uvs: per face corner."""
    vn = vertex_normals(X, F)
    n = len(X)
    inner = X - vn * thick[:, None]
    verts = list(X) + list(inner)
    src = list(range(n)) + list(range(n))
    faces, fuv = [], []
    for f, uv in zip(F, uvs):
        faces.append(list(f))
        fuv.append(list(uv))
        faces.append([n + i for i in reversed(list(f))])
        fuv.append(list(reversed(list(uv))))
    corner_uv = {}
    for f, uv in zip(F, uvs):
        for v, u in zip(f, uv):
            corner_uv.setdefault(int(v), u)
    edges = {}
    for fi, f in enumerate(F):
        k = len(f)
        for i in range(k):
            a, b = int(f[i]), int(f[(i + 1) % k])
            edges.setdefault((min(a, b), max(a, b)), []).append((a, b, fi))
    bedges = [v[0] for v in edges.values() if len(v) == 1]
    bdir = np.zeros_like(X)
    for a, b, fi in bedges:
        e = X[b] - X[a]
        out = np.cross(e, vn[a] + vn[b])
        cen = X[list(F[fi])].mean(0)
        if out @ (0.5 * (X[a] + X[b]) - cen) < 0:
            out = -out
        out /= max(np.linalg.norm(out), 1e-12)
        bdir[a] += out
        bdir[b] += out
    rows = {}
    for v in {x for e in bedges for x in e[:2]}:
        d = bdir[v] / max(np.linalg.norm(bdir[v]), 1e-12)
        h = thick[v] / 2
        mid = X[v] - vn[v] * h
        ids = [v]
        for ang in (45, 90, 135):
            r = math.radians(ang)
            ids.append(len(verts))
            verts.append(mid + vn[v] * h * math.cos(r) + d * h * math.sin(r) * rim_round)
            src.append(v)
        ids.append(n + v)
        rows[v] = ids
    for a, b, fi in bedges:
        ra, rb = rows[a], rows[b]
        ua, ub = corner_uv[a], corner_uv[b]
        for k in range(4):
            faces.append([rb[k], ra[k], ra[k + 1], rb[k + 1]])
            dv = thick[a] * 0.01 / 4
            fuv.append([(ub[0], ub[1] + dv * k), (ua[0], ua[1] + dv * k), (ua[0], ua[1] + dv * (k + 1)),
                        (ub[0], ub[1] + dv * (k + 1))])
    return np.array(verts), faces, fuv, np.array(src)


def finish_top(top, marks):
    V = top["Vd"]
    Q = top["Q"]
    # one Catmull-Clark step for smooth silhouettes (the knit is soft): done on the surface, uvs re-derived
    uvs = top_uv(dict(V=top["V"], Q=Q, shape=top["shape"]), marks)
    thick = np.full(len(V), TOP["thick"])
    bind = (top["open_kind"] >= 1) & (top["dist_open"] < TOP["bind"])
    thick[bind] = TOP["thick"] * 1.5          # the binding is a folded double layer
    X, F, UV, src = solidify(V, Q, thick, uvs)
    return X, F, UV, src


# ================================================================ the trousers

class LowerShape:
    """The trousers' volume: her lower body closed and eased, straight legs below the knee, the top's tuck inside."""

    def __init__(self, her, marks, body, top_shape, z_w):
        self.mk = marks
        self.z_w = z_w
        h = VOX
        ins = body.inside.copy()
        xs, ys, zs = body.sd.coords()
        # her arms and hands are not in the trousers: drop the voxels nearest an arm-weighted vertex
        arm_pts = her.bx[her.armw > 0.3]
        tree = cKDTree(arm_pts)
        idx = np.argwhere(ins)
        P = body.lo + idx * h
        d, _ = tree.query(P, distance_upper_bound=1.2)
        far_side = np.abs(P[:, 0]) > 15
        drop = (d < 1.2) & far_side
        ins[tuple(idx[drop].T)] = False
        closed = closing(ins, TROUSERS["close"], h)
        self.sd = Field(body.lo, h, sdf_of(closed, h).astype(np.float32))
        self.top_shape = top_shape
        # the legs' straight lower part: per leg, a centre line from the knee to the ankle, and the least radius
        self.legs = []
        for s in (1, -1):
            k = her.bone["calf_l" if s > 0 else "calf_r"]
            a = her.bone["foot_l" if s > 0 else "foot_r"]
            self.legs.append((s, k, a))
        log(f"lower: closed body ({TROUSERS['close']} cm), waist edge z {z_w:.1f}")

    def ease(self, z):
        mk = self.mk
        e = np.interp(z, [mk.z_crotch - 20, mk.z_crotch, mk.z_hip, mk.z_waist, self.z_w + 2],
                      [TROUSERS["ease_knee"], TROUSERS["ease_thigh"], TROUSERS["ease_hip"],
                       TROUSERS["ease_waist"], TROUSERS["ease_waist"]])
        return e

    def leg_centre(self, s, z):
        _, k, a = self.legs[0 if s > 0 else 1]
        t = (z - a[2]) / (k[2] - a[2])
        return a + (k - a) * t if np.isscalar(z) else a[None] + np.outer(t, k - a)

    def straight_sdf(self, P):
        """Straight leg tubes: from the hem up past the knee, round each leg's knee-ankle line; the radius is the
        largest of her calf (+ ease) at that angle over the whole lower leg, so the leg falls straight."""
        out = np.full(len(P), 99.0)
        for s, k, a in self.legs:
            c = self.leg_centre(s, P[:, 2])
            dx, dy = P[:, 0] - c[:, 0], P[:, 1] - c[:, 1]
            r = np.hypot(dx, dy)
            th = np.arctan2(dy, dx)
            R = self.leg_R[s](th, P[:, 2])
            f = r - R
            f = np.maximum(f, P[:, 2] - (k[2] + 14.0))
            out = np.minimum(out, f)
        return out

    def fit_legs(self, her):
        """The least radius per angle (round the knee-ankle line) that clears her lower leg everywhere below the knee,
        and the straight leg's profile."""
        self.leg_R = {}
        for s, k, a in self.legs:
            sel = (np.sign(her.bx[:, 0]) == s) & (her.bx[:, 2] > a[2] - 3) & (her.bx[:, 2] < k[2] + 2) \
                & (her.footw < 0.5)
            P = her.bx[sel]
            c = self.leg_centre(s, P[:, 2])
            dx, dy = P[:, 0] - c[:, 0], P[:, 1] - c[:, 1]
            r, th = np.hypot(dx, dy), np.arctan2(dy, dx)
            angs = np.linspace(-math.pi, math.pi, 72, endpoint=False)
            Rm = np.zeros(len(angs))
            for i, t in enumerate(angs):
                m = np.abs(np.angle(np.exp(1j * (th - t)))) < 0.12
                Rm[i] = r[m].max() if m.any() else 0
            Rm = np.maximum(Rm, 1e-3)
            Rm = smooth1d(Rm, 2.0, wrap=True) + TROUSERS["ease_knee"]
            # a clean oval: the least ellipse-ish shape over Rm, no less than the straight leg's half girth
            kr, hr = TROUSERS["leg_knee_r"], TROUSERS["leg_hem_r"]
            z_k, z_h = k[2], a[2]

            def R(th, z, Rm=Rm, angs=angs, kr=kr, hr=hr, z_k=z_k, z_h=z_h):
                base = np.interp(th, angs, Rm, period=2 * math.pi)
                floor = np.interp(z, [z_h, z_k], [hr, kr])
                # front and back slightly deeper than the sides: trousers hang as an oval
                oval = 1.0 + 0.05 * np.sin(th) ** 2
                return np.maximum(base, floor * oval)

            self.leg_R[s] = R
        log("legs fitted")

    def sdf(self, P):
        z = P[:, 2]
        f = self.sd(P) - self.ease(z)
        f = np.minimum(f, self.straight_sdf(P) + 0.0)
        # the top's tuck lies inside the waist: the trousers clear its outer face
        tz = (z > self.z_w - TROUSERS["band"] - TOP["tuck"] - 3) & (z < self.z_w + 1)
        ft = self.top_shape.torso_sdf(P) - (TOP["thick"] + 0.25)
        f = np.where(tz, np.minimum(f, ft), f)
        # the waistband zone follows the hull (a smooth band, no dents)
        bz = (z > self.z_w - TROUSERS["band"] - 1.5)
        fb = self.top_shape.torso_sdf(P) - (TOP["thick"] + 0.3)
        f = np.where(bz, np.minimum(f, fb), f)
        return f


def ray_section(F, centre, z, angles, rmax=30.0, step=0.12):
    """Outermost crossing of F (inside < 0) along rays from centre (x, y) at height z: points (na, 3)."""
    rs = np.arange(0.0, rmax, step)
    d = np.stack([np.cos(angles), np.sin(angles)], 1)
    P = np.zeros((len(angles), len(rs), 3))
    P[..., 0] = centre[0] + d[:, None, 0] * rs[None]
    P[..., 1] = centre[1] + d[:, None, 1] * rs[None]
    P[..., 2] = z
    f = F(P.reshape(-1, 3)).reshape(len(angles), len(rs))
    out = np.zeros((len(angles), 3))
    for i in range(len(angles)):
        ins = np.where(f[i] < 0)[0]
        if len(ins) == 0:
            out[i] = (*centre, z)
            continue
        j = ins[-1]
        if j + 1 < len(rs):
            t = f[i, j] / (f[i, j] - f[i, j + 1])
            r = rs[j] + t * step
        else:
            r = rs[j]
        out[i] = (centre[0] + d[i, 0] * r, centre[1] + d[i, 1] * r, z)
    return out


def arc_param(P, closed=True):
    seg = np.linalg.norm(np.diff(np.vstack([P, P[:1]]) if closed else P, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    return s


def resample_between(curve, s, i0, i1, fr):
    """Points at arc-length fractions fr of the (closed) curve from index i0 forward to i1."""
    n = len(curve)
    idx = [(i0 + k) % n for k in range(((i1 - i0) % n) + 1)]
    P = curve[idx]
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    ss = np.concatenate([[0], np.cumsum(seg)])
    t = np.asarray(fr) * ss[-1]
    return np.stack([np.interp(t, ss, P[:, k]) for k in range(3)], 1)


def column_fracs(n_half, dense=0.18):
    """Column positions over a panel half (0 at a seam, 1 at the crease), denser near the crease."""
    u = np.linspace(0, 1, n_half + 1)
    return u - dense * np.sin(u * math.pi) * u  # pulls toward 1 slightly


def build_trousers(her, marks, body, top_shape, z_w):
    lower = LowerShape(her, marks, body, top_shape, z_w)
    lower.fit_legs(her)
    F = lower.sdf
    z_hem = float(marks.ankle[2]) + TROUSERS["hem_above_ankle"]
    z_crotch_tr = None
    # the crotch of the trousers' volume: the lowest inside point at x = 0, from below
    ys = np.arange(marks.cy - 14, marks.cy + 14, 0.25)
    zs = np.arange(marks.z_crotch - 12, marks.z_crotch + 6, 0.1)
    Y, Z = np.meshgrid(ys, zs, indexing="ij")
    P = np.stack([np.zeros(Y.size), Y.ravel(), Z.ravel()], 1)
    f = F(P).reshape(Y.shape)
    lowest = np.array([zs[np.argmax(f[i] < 0)] if (f[i] < 0).any() else 1e9 for i in range(len(ys))])
    ia = int(np.argmin(lowest))
    z_apex, y_apex = float(lowest[ia]), float(ys[ia])
    log(f"trousers: hem z {z_hem:.1f}, crotch apex z {z_apex:.1f} y {y_apex:.1f}, waist edge z {z_w:.1f}")
    # rows: legs from the hem to just under the apex, the apex row, then the hips to the waist edge
    leg_rows = np.linspace(z_hem, z_apex - 0.35, max(8, int((z_apex - z_hem) / 1.1)))
    hip_rows = np.linspace(z_apex + 0.25, z_w, max(8, int((z_w - z_apex) / 0.6)))
    rows = list(leg_rows) + [z_apex] + list(hip_rows)
    jc = len(leg_rows)
    NA = 900
    angles = np.linspace(-math.pi, math.pi, NA, endpoint=False)
    nh = 14   # columns per half panel (seam -> crease, crease -> seam)
    fr = column_fracs(nh)
    panels = {k: [] for k in ("LF", "LB", "RF", "RB")}
    for j, z in enumerate(rows):
        for s, (kf, kb) in ((1, ("LF", "LB")), (-1, ("RF", "RB"))):
            if j <= jc:
                c = lower.leg_centre(s, z)[:2]
                cur = ray_section(F, c, z, angles)
                # keep only her own leg's lobe (the other leg is not on these rays: rays start inside this one)
                xl = c[0]
            else:
                c = np.array((0.0, marks.cy))
                cur = ray_section(F, c, z, angles)
                xl = float(lower.leg_centre(s, min(z, marks.knee[2] + 30))[0]) * 0.92
            ang = np.arctan2(cur[:, 1] - c[1], cur[:, 0] - c[0])
            # landmarks (indices on the curve)
            i_side = int(np.argmin(np.abs(np.angle(np.exp(1j * (ang - (0.0 if s > 0 else math.pi)))))))
            front = cur[:, 1] < c[1]
            back = ~front
            if j < jc:
                i_in = int(np.argmin(np.abs(np.angle(np.exp(1j * (ang - (math.pi if s > 0 else 0.0)))))))
            else:
                # the centre front / back: the curve's points at x = 0
                pass
            dxl = np.abs(cur[:, 0] - xl)
            i_cf_crease = int(np.argmin(np.where(front, dxl, 1e9)))
            i_cb_crease = int(np.argmin(np.where(back, dxl, 1e9)))
            if j <= jc:
                if j == jc:
                    # the apex row: the inner point is the apex itself
                    i_in = int(np.argmin(np.linalg.norm(cur[:, :2] - (0.0, y_apex), axis=1)))
                i_cf, i_cb = i_in, i_in
            else:
                ax = np.abs(cur[:, 0])
                i_cf = int(np.argmin(np.where(front, ax, 1e9)))
                i_cb = int(np.argmin(np.where(back, ax, 1e9)))
            # walk directions on the curve: angles increase counter-clockwise (seen from above, +X -> +Y)
            # left leg: side (0) -> front (-pi/2) is clockwise, i.e. decreasing index
            if s > 0:
                rev = cur[::-1]
                m = lambda i: len(cur) - 1 - i
                curF, a0, a1, a2 = rev, m(i_side), m(i_cf_crease), m(i_cf)
                fpts = np.vstack([resample_between(curF, None, a0, a1, fr[:-1]),
                                  resample_between(curF, None, a1, a2, fr)])
                # back: from the inner/centre-back through the crease to the side, also clockwise (+Y -> +X)
                b0, b1, b2 = m(i_cb), m(i_cb_crease), m(i_side)
                bpts = np.vstack([resample_between(curF, None, b0, b1, fr[:-1]),
                                  resample_between(curF, None, b1, b2, fr)])
            else:
                curF = cur
                a0, a1, a2 = i_side, i_cf_crease, i_cf
                fpts = np.vstack([resample_between(curF, None, a0, a1, fr[:-1]),
                                  resample_between(curF, None, a1, a2, fr)])
                b0, b1, b2 = i_cb, i_cb_crease, i_side
                bpts = np.vstack([resample_between(curF, None, b0, b1, fr[:-1]),
                                  resample_between(curF, None, b1, b2, fr)])
            if j == jc:
                fpts[-1] = (0.0, y_apex, z_apex)
                bpts[0] = (0.0, y_apex, z_apex)
            if j > jc:
                fpts[-1, 0] = 0.0
                bpts[0, 0] = 0.0
            panels[kf].append(fpts)
            panels[kb].append(bpts)
    G = {k: np.array(v) for k, v in panels.items()}   # (rows, cols, 3)
    return dict(G=G, rows=np.array(rows), jc=jc, z_hem=z_hem, z_apex=z_apex, y_apex=y_apex, lower=lower,
                nh=nh, fr=fr, z_w=z_w)


# ================================================================ skinning, pose tests, export

class WeightSource:
    """Her body's triangles (a chosen part) with per-vertex bone weights, for nearest-point lookups."""

    def __init__(self, her, tri_keep, groups):
        T = her.bt[tri_keep]
        self.T = T
        self.groups = groups
        gi = {g: i for i, g in enumerate(groups)}
        self.W = np.zeros((len(her.bx), len(groups)), np.float32)
        for g, a in her.bw.items():
            if g in gi:
                self.W[:, gi[g]] = a
        self.X = her.bx
        self.bvh = BVHTree.FromPolygons(her.bx.tolist(), T.tolist())

    def at(self, P):
        out = np.zeros((len(P), len(self.groups)), np.float32)
        for i, p in enumerate(P):
            loc, nor, fi, dist = self.bvh.find_nearest(Vector(p))
            if loc is None:
                continue
            t = self.T[fi]
            w = bary(np.array(loc[:]), self.X[t])
            out[i] = (self.W[t] * w[:, None]).sum(0)
        return out


def bary(p, tri):
    a, b, c = tri
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-12:
        return np.array((1.0, 0.0, 0.0))
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    r = np.clip(np.array((1 - v - w, v, w)), 0, 1)
    return r / max(r.sum(), 1e-9)


def finalise_weights(W, lap, smooth_iters=20, max_inf=8):
    for _ in range(smooth_iters):
        W = 0.5 * W + 0.5 * lap.avg(W)
    W[W < 0.01] = 0
    if W.shape[1] > max_inf:
        idx = np.argsort(-W, axis=1)[:, max_inf:]
        np.put_along_axis(W, idx, 0, axis=1)
    return W / np.maximum(W.sum(1, keepdims=True), 1e-9)


def weight_groups(her):
    return sorted(her.bw)


def skin_top(her, marks, V, Q, lap):
    """Weights at the top's surface verts: the torso from her torso, the sleeves from her arm (per side)."""
    groups = weight_groups(her)
    # the torso from her torso, the chest included (its skin carries the arm's corrective weights too): only
    # what is geometrically the arm is left out
    tc = her.bx[her.bt].mean(1)
    on_arm = (her.armw[her.bt].max(1) > 0.6) & (armhole_phi(tc, marks) > 1.0)
    torso_src = WeightSource(her, ~on_arm & (her.legw[her.bt].max(1) < 0.3), groups)
    W = torso_src.at(V)
    ah = armhole_phi(V, marks)
    blend = smoothstep(-2.0, 2.5, ah)
    for s in (1, -1):
        sfx = "_l" if s > 0 else "_r"
        aw = chain_weight(her.bw, len(her.bx), ("upperarm", "lowerarm"), sfx)
        src = WeightSource(her, aw[her.bt].min(1) > 0.35, groups)
        m = (np.sign(V[:, 0]) == s) & (blend > 0)
        Wa = src.at(V[m])
        W[m] = W[m] * (1 - blend[m])[:, None] + Wa * blend[m][:, None]
    return finalise_weights(W, lap), groups


def skin_trousers(her, V, lap, panel_side):
    """Weights at the trousers' surface verts: from her pelvis and legs, each panel from its own side, no foot
    bones (the hem must not ride the foot)."""
    groups = weight_groups(her)
    no_arm = her.armw[her.bt].max(1) < 0.2
    no_foot = her.footw[her.bt].max(1) < 0.25
    low = her.bx[her.bt][:, :, 2].max(1) < 118
    W = np.zeros((len(V), len(groups)), np.float32)
    for s in (1, -1):
        side = (np.sign(her.bx[her.bt][:, :, 0].mean(1)) == s) | (np.abs(her.bx[her.bt][:, :, 0].mean(1)) < 2.0)
        src = WeightSource(her, no_arm & no_foot & low & side, groups)
        m = panel_side == s
        W[m] = src.at(V[m])
    return finalise_weights(W, lap, smooth_iters=30), groups


def make_skinned(her, name, X, F, UV, mats, mat_idx, Wsurf, src, groups, sharp=None):
    ob = arrays_object(name, X, F, mats=mats, mat_idx=mat_idx, uvs=UV, sharp=sharp)
    W = Wsurf[src]
    used = [i for i in range(len(groups)) if W[:, i].max() > 0]
    for i in used:
        vg = ob.vertex_groups.new(name=groups[i])
        nz = np.nonzero(W[:, i])[0]
        ww = np.round(W[nz, i], 4)
        for w in np.unique(ww):
            vg.add(nz[ww == w].tolist(), float(w), "REPLACE")
    ob.parent = her.arm
    ob.matrix_parent_inverse = her.arm.matrix_world.inverted()
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = her.arm
    log(f"{name}: {len(X)} verts, {len(used)} bones, max influences {(W > 0).sum(1).max()}")
    return ob


def bind_body(her):
    for o in (her.body_ob, her.face_ob):
        if o is None:
            continue
        for m in o.modifiers:
            if m.type == "ARMATURE":
                m.object = her.arm


def eval_points(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    X = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", X)
    X = (np.array(ob.matrix_world) @ np.c_[X.reshape(-1, 3), np.ones(len(me.vertices))].T).T[:, :3] * 100.0
    me.calc_loop_triangles()
    T = np.zeros(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", T)
    ev.to_mesh_clear()
    return X, T.reshape(-1, 3)


def clip_check(her, ob, step=3, under=None):
    """Garment verts inside her body (or inside the layer under it) in the current pose: count, deepest (cm)."""
    V, T = eval_points(her.body_ob)
    layers = [(V, T)]
    if under is not None:
        layers.append(eval_points(under))
    G, _ = eval_points(ob)
    G = G[::step]
    bad, deep = 0, 0.0
    for V, T in layers:
        bvh = BVHTree.FromPolygons(V.tolist(), T.tolist())
        for p in G:
            loc, nor, fi, dist = bvh.find_nearest(Vector(p), 1.2)
            if loc is None:
                continue
            if (Vector(p) - loc).dot(nor) < 0:
                bad += 1
                deep = max(deep, dist)
    return bad * step, deep


def pose_bone_world(arm, bone, axis, deg):
    pb = arm.pose.bones[bone]
    M = pb.matrix.copy()
    h = M.translation.copy()
    R = Matrix.Rotation(math.radians(deg), 4, Vector(axis))
    pb.matrix = Matrix.Translation(h) @ R @ Matrix.Translation(-h) @ M
    bpy.context.view_layer.update()


def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


POSES = {  # name: [(bone, world axis, degrees)]; her left is +X, her front -Y
    "arms_down": [("upperarm_l", (0, 1, 0), 30), ("upperarm_r", (0, 1, 0), -30)],
    "arms_raise": [("upperarm_l", (0, 1, 0), -50), ("upperarm_r", (0, 1, 0), 50)],
    "arms_fwd": [("upperarm_l", (1, 0, 0), 55), ("upperarm_r", (1, 0, 0), 55)],
    "elbows": [("lowerarm_l", (1, 0, 0), 80), ("lowerarm_r", (1, 0, 0), 80)],
    "step": [("thigh_l", (1, 0, 0), 30), ("thigh_r", (1, 0, 0), -15), ("calf_l", (1, 0, 0), -35)],
    "sit": [("thigh_l", (1, 0, 0), 80), ("thigh_r", (1, 0, 0), 80), ("calf_l", (1, 0, 0), -80),
            ("calf_r", (1, 0, 0), -80)],
    "lean": [("spine_03", (0, 1, 0), 12), ("spine_01", (1, 0, 0), 10)],
}


def pose_tests(her, garments, args, colours):
    bind_body(her)
    arm = her.arm
    res = {"import": {g.name: clip_check(her, g) for g in garments}}
    moved = [pb.name for pb in arm.pose.bones if (pb.matrix_basis - Matrix.Identity(4)).to_3x3().to_scale().length > 0
             or pb.matrix_basis != Matrix.Identity(4)]
    log(f"pose at import: {res['import']}, bones off rest: {len(moved)} {moved[:12]}")
    reset_pose(arm)
    res["rest"] = {g.name: clip_check(her, g) for g in garments}
    log(f"pose at rest: {res['rest']}")
    for g in [her.body_ob] + list(garments):
        Xe, _ = eval_points(g)
        X0 = np.array([(g.matrix_world @ v.co)[:] for v in g.data.vertices]) * 100.0
        dd = np.linalg.norm(Xe - X0, axis=1)
        log(f"rest vs mesh {g.name}: mean {dd.mean():.3f} max {dd.max():.3f} cm, argmax at {X0[dd.argmax()].round(1)}")
    for name, moves in POSES.items():
        reset_pose(arm)
        for bone, ax, deg in moves:
            pose_bone_world(arm, bone, ax, deg)
        res[name] = {g.name: clip_check(her, g) for g in garments}
        log(f"pose {name}: " + ", ".join(f"{k} {v[0]} inside (deepest {v[1]:.2f} cm)" for k, v in res[name].items()))
        snapshot(os.path.join(args.out, f"{NAME}_pose_{name}"), colours, (("front", (0, 1, 0)), ("q", (0.62, 1, -0.12))),
                 centre=(0, 0, 0.95), ortho=1.9, res=(700, 900))
    reset_pose(arm)
    return res


def retarget(src, dst):
    """Her pose from another armature of the same skeleton, as Unreal plays an animation on her: each bone takes
    the source's local rotation on her own bone offsets (her proportions). (After agent-05's overshirt.py.)"""
    for pb in dst.pose.bones:
        sb = src.pose.bones.get(pb.name)
        if sb is None or pb.parent is None:
            continue
        sl = (sb.parent.matrix.inverted() @ sb.matrix) if sb.parent else sb.matrix
        rl = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
        want = Matrix.Translation(rl.translation) @ sl.to_quaternion().to_matrix().to_4x4()
        pb.matrix_basis = rl.inverted() @ want


def idle_test(her, garments, args, colours, samples=8):
    p = os.path.join(args.src, "idle.fbx")
    if not os.path.exists(p):
        return {}
    bind_body(her)
    before = set(bpy.data.actions)
    objs = import_fbx(p)
    acts = [a for a in bpy.data.actions if a not in before]
    src = next((o for o in objs if o.type == "ARMATURE"), None)
    if not acts or src is None:
        return {}
    for o in objs:
        o.hide_render = True
    f0, f1 = (int(x) for x in acts[0].frame_range)
    res = {}
    frames = sorted({int(f0 + (f1 - f0) * k / (samples - 1)) for k in range(samples)})
    for f in frames:
        bpy.context.scene.frame_set(f)
        retarget(src, her.arm)
        bpy.context.view_layer.update()
        res[f] = {g.name: clip_check(her, g) for g in garments}
        log(f"idle {f}: " + ", ".join(f"{k} {v[0]} inside (deepest {v[1]:.2f} cm)" for k, v in res[f].items()))
        if f == frames[len(frames) // 2]:
            snapshot(os.path.join(args.out, f"{NAME}_idle"), colours, VIEWS[:3], centre=(0, 0, 0.95), ortho=1.9,
                     res=(700, 900))
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    reset_pose(her.arm)
    return res


def prepare_export_armature(her):
    """The armature object as Unreal's skeleton root: unparented, scale applied, named 'root'."""
    arm = her.arm
    mw = arm.matrix_world.copy()
    arm.parent = None
    arm.matrix_world = mw
    for o in bpy.context.scene.objects:
        o.select_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    arm.name = "root"


def export_skeletal(her, ob, path):
    arm = her.arm
    for o in bpy.context.scene.objects:
        o.select_set(o in (arm, ob))
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"},
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", global_scale=1.0,
        axis_forward="-Y", axis_up="Z", add_leaf_bones=False, use_armature_deform_only=False,
        bake_anim=False, mesh_smooth_type="OFF", use_mesh_modifiers=False, use_tspace=True,
        primary_bone_axis="Y", secondary_bone_axis="X", path_mode="STRIP")
    log(f"exported {path}")


# ================================================================ driver

def body_object(her):
    return her.body_ob


def materials():
    return {
        "M_Top": S.material("M_Top", (0.86, 0.82, 0.74), 0.85),
        "M_Trousers": S.material("M_Trousers", (0.028, 0.028, 0.031), 0.72),
        "M_Hardware": S.material("M_Hardware", (0.83, 0.62, 0.3), 0.25, metallic=1.0),
    }


def main():
    a = ARGS
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    her = Her(a.src)
    marks = Marks(her)
    rep = marks.report()
    if a.stage == "measure":
        snapshot(os.path.join(a.out, f"{NAME}_body"), {her.body_ob: SKIN}, VIEWS, ortho=1.9, centre=(0, 0, 0.85))
        return
    M = materials()
    surf = Surf(her)
    z_w = marks.z_waist + TROUSERS["rise"]
    top = build_top(her, marks, surf, z_w - TOP["tuck"], z_w)
    top["z_band"] = z_w
    top = top_detail(top, her, marks, surf)
    X, F, UV, src = finish_top(top, marks)
    Wt, groups = skin_top(her, marks, top["Vd"], top["Q"], top["lap"])
    ob_top = make_skinned(her, "her_top", X, F, UV, [M["M_Top"]], None, Wt, src, groups)
    log(f"top: {len(X)} verts {time.time() - t0:.0f}s")
    snapshot(os.path.join(a.out, f"{NAME}_top{a.tag}"), {ob_top: (0.92, 0.9, 0.85), her.body_ob: SKIN}, VIEWS,
             centre=(0, 0, 1.15), ortho=0.9)
    snapshot(os.path.join(a.out, f"{NAME}_topc{a.tag}"), {ob_top: (0.92, 0.9, 0.85), her.body_ob: SKIN},
             (("front", (0, 1, 0)), ("back", (0, -1, 0)), ("q", (0.62, 1, -0.3)), ("top", (0.0, 0.3, -1))),
             centre=(0, -0.02, 1.32), ortho=0.42, res=(1000, 1000))
    garments = [ob_top]
    cols = {ob_top: (0.92, 0.9, 0.85), her.body_ob: SKIN}
    if a.stage != "top":
        body = Body(her)
        tr = build_trousers(her, marks, body, top["shape"], z_w)
        obs = {}
        for k, G in tr["G"].items():
            nr, nc = G.shape[:2]
            FF = [[r * nc + c, r * nc + c + 1, (r + 1) * nc + c + 1, (r + 1) * nc + c] for r in range(nr - 1)
                  for c in range(nc - 1)]
            obs[k] = arrays_object(f"tr_{k}", G.reshape(-1, 3), FF)
        cols.update({obs["LF"]: (0.15, 0.15, 0.17), obs["LB"]: (0.25, 0.2, 0.2), obs["RF"]: (0.15, 0.17, 0.25),
                     obs["RB"]: (0.2, 0.25, 0.2)})
        snapshot(os.path.join(a.out, f"{NAME}_tr{a.tag}"), cols, VIEWS, centre=(0, 0, 0.8), ortho=1.75)
    if not a.no_tests:
        res = {"poses": pose_tests(her, garments, a, cols), "idle": idle_test(her, garments, a, cols)}
        with open(os.path.join(a.out, f"{NAME}_tests.json"), "w") as f:
            json.dump(res, f, indent=1, default=str)
    prepare_export_armature(her)
    for g in garments:
        export_skeletal(her, g, os.path.join(a.out, f"{g.name}.fbx"))
    rep["top"] = {"verts": len(X), "tris": int(sum(len(f) - 2 for f in F))}
    with open(os.path.join(a.out, f"{NAME}_marks.json"), "w") as f:
        json.dump(rep, f, indent=1)
    log(f"done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
