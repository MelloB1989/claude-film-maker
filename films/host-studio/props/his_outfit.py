"""his_outfit: the male presenter's slim dark trousers (charcoal tailored, tapered to the ankle, a clean waistband), as a skinned
garment on his own skeleton (metahuman_base_skel), worn with MetaHuman's default fitted tee (kept) while the default
garment's shorts are hidden in Unreal (their material slots get an invisible material: studio.py's his outfit block).

Fitted to his A-pose body and default garment as exported from Unreal (his_outfit_ue/export_body.py -> body.fbx,
garment.fbx, face.fbx, anim_*.fbx). MetaHuman removed the body's faces under the garment, so his volume is his body
with the garment (shorts and tee) round it, filled from outside (a flood fill of the voxels), and the trousers clear
the shorts. The tee hangs over the trousers' waistband: in the waist zone the trousers stay inside the tee.
Built with agent-02's trousers (his_outfit.py): the pattern-grid panels, tailoring and skinning, re-proportioned.

Run headless (on the Mac, through the fleet wrapper; scipy from --pylib):
    blender -b --factory-startup -P his_outfit.py -- --src <dir with the UE FBXs> --out <out dir> [--stage all]

Frame (cm): his left +X, his front -Y, up +Z (his skeleton's frame, as exported).

Material slot: M_Trousers (charcoal wool twill). No belt or button: the tee hangs over the waistband.
UVs: world scale (1 UV = 1 m), the trousers' grain (V) down each panel.
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

NAME = "his_outfit"

# ---------------------------------------------------------------- fit (cm)
VOX = 0.4                       # body voxels
TROUSERS = dict(
    close=2.5,                  # the bridging (closing radius) of his lower body
    soften=1.2,                 # his body's field blurred by this much (cm): cloth lies over the muscles, not into them
    ease_waist=0.45, ease_hip=1.5, ease_thigh=1.8, ease_knee=1.6, ease_ankle=0.9,
    band=3.8,                   # waistband height
    waist_above_pelvis=8.2,     # the waist edge: this far above his pelvis joint (a mid rise, under the tee's hem)
    hem_above_ankle=1.6,        # the hem: at the ankle bone (foot joint) + this
    leg_hem_r=5.75, leg_knee_r=7.0,  # the taper's floor: half-girth at the hem (a 36 cm opening) and at the knee
    crease_h=0.12, crease_w=1.0,    # a soft pressed crease
    crotch_drop=3.2,            # the trousers' crotch below his
    rise_front=4.0, rise_back=9.0,   # the centre seams' curve under to the crotch point: its height in front, behind
    notch_slope=1.35, notch_round=1.6,   # the opening between the legs under that curve: how fast it widens, its round
    bridge_ramp=3.0,            # the front bridge between the thighs: none at the crotch, full this far above it
    row_smooth=3.0,             # the hip rows evened up the body (gaussian, in rows)
    thick=0.08, band_thick=0.2,
    tee_gap=0.14,               # the trousers' outside under the tee's inside
)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog=NAME)
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--src", default=os.path.join(here, "out", "his_outfit_ue"))
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument("--pylib", default="")
    ap.add_argument("--stage", default="all", help="measure | top | trousers | all")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-tests", action="store_true")
    ap.add_argument("--no-bake", action="store_true")
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


# ================================================================ him, from the FBX exports

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


class Him:
    """His reference A-pose: the armature, the body, the face (neck), his default garment (the tee and the shorts,
    told apart by their material slots), landmarks. MetaHuman cut the body's faces under the garment, so the solid
    he is (for the trousers to clear) is the body with the garment round it: `dressed`."""

    def __init__(self, src):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        objs = import_fbx(os.path.join(src, "body.fbx"))
        self.arm = next(o for o in objs if o.type == "ARMATURE")
        self.body_ob = next(o for o in objs if o.type == "MESH")
        self.body_vis = self.body_ob
        alt = os.path.join(src, "body_alt.fbx")
        if os.path.exists(alt):
            self.body_ob = self.uncut_body(alt)
        self.face_ob = None
        fp = os.path.join(src, "face.fbx")
        if os.path.exists(fp):
            fo = import_fbx(fp)
            self.face_ob = next((o for o in fo if o.type == "MESH"), None)
            for o in fo:
                if o.type == "ARMATURE":
                    bpy.data.objects.remove(o, do_unlink=True)
        self.bone = {b.name: np.array((self.arm.matrix_world @ b.head_local)[:]) * 100.0 for b in self.arm.data.bones}
        self.bx, self.bt, self.bw = mesh_arrays(self.body_ob)
        n = len(self.bx)
        self.armw = chain_weight(self.bw, n, ARM_KEYS)
        self.legw = chain_weight(self.bw, n, LEG_KEYS)
        self.footw = chain_weight(self.bw, n, FOOT_KEYS)
        if self.face_ob is not None:
            self.fx, self.ft, _ = mesh_arrays(self.face_ob)
        # the default garment on the same skeleton: its own armature dropped, bound to his
        go = import_fbx(os.path.join(src, "garment.fbx"))
        self.garment_ob = next(o for o in go if o.type == "MESH")
        for o in go:
            if o.type == "ARMATURE":
                mw = self.garment_ob.matrix_world.copy()
                self.garment_ob.parent = None
                self.garment_ob.matrix_world = mw
                bpy.data.objects.remove(o, do_unlink=True)
        for m in self.garment_ob.modifiers:
            if m.type == "ARMATURE":
                m.object = self.arm
        self.gx, self.gt, self.gw = mesh_arrays(self.garment_ob)
        me = self.garment_ob.data
        names = [m.name if m else "" for m in me.materials]
        me.calc_loop_triangles()
        mi = np.zeros(len(me.loop_triangles), np.int64)
        me.loop_triangles.foreach_get("material_index", mi)
        short_slot = np.array(["short" in names[i].lower() for i in range(len(names))] or [False])
        self.g_short_tri = short_slot[mi]                         # per garment triangle: the shorts (else the tee)
        self.short_v = np.zeros(len(self.gx), bool)
        self.short_v[self.gt[self.g_short_tri].ravel()] = True
        self.tee_v = np.zeros(len(self.gx), bool)
        self.tee_v[self.gt[~self.g_short_tri].ravel()] = True
        log(f"garment: slots {names}, {int(self.g_short_tri.sum())} shorts tris, {int((~self.g_short_tri).sum())} tee tris")
        # the tee alone (the shorts' faces deleted), on his armature: for the previews and the through-the-tee checks
        self.tee_ob = self.garment_ob.copy()
        self.tee_ob.data = self.garment_ob.data.copy()
        self.tee_ob.name = "tee"
        bpy.context.scene.collection.objects.link(self.tee_ob)
        bm = bmesh.new()
        bm.from_mesh(self.tee_ob.data)
        short_idx = {i for i, nm in enumerate(names) if "short" in nm.lower()}
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in short_idx], context="FACES")
        bm.to_mesh(self.tee_ob.data)
        bm.free()
        # dressed: body + garment (all of it) as one triangle soup, for slices and rays
        self.dx = np.concatenate([self.bx, self.gx])
        self.dt = np.concatenate([self.bt, self.gt + n])
        self.dvh = BVHTree.FromPolygons(self.dx.tolist(), self.dt.tolist())
        self.bvh = BVHTree.FromPolygons(self.bx.tolist(), self.bt.tolist())
        log(f"body verts {n} tris {len(self.bt)}  bbox {self.bx.min(0).round(1)} {self.bx.max(0).round(1)}")
        log(f"garment bbox {self.gx.min(0).round(1)} {self.gx.max(0).round(1)}; shorts z "
            f"{self.gx[self.short_v, 2].min():.1f}..{self.gx[self.short_v, 2].max():.1f}, tee z "
            f"{self.gx[self.tee_v, 2].min():.1f}..{self.gx[self.tee_v, 2].max():.1f}")

    def uncut_body(self, alt_path):
        """His whole body. MetaHuman cut his body's faces under the default garment; an earlier build's body in his
        folder (SKM_Host_BodyMesh, another character's proportions, built without the garment) has the same template
        topology, every one of his vertices matching one of its by UV. Its mesh takes his vertices where he has
        them, and in the cut region its own shape plus his difference from it carried in smoothly (a harmonic fill
        of the displacement over its welded surface). Weights: his where he has them, the template's elsewhere.
        Returns the new body object, on his armature; his cut body is removed."""
        cut = self.body_ob
        ao = import_fbx(alt_path)
        ob = next(o for o in ao if o.type == "MESH")
        mw = ob.matrix_world.copy()
        ob.parent = None
        ob.matrix_world = mw
        for o in ao:
            if o.type == "ARMATURE":
                bpy.data.objects.remove(o, do_unlink=True)
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

        def verts_uv(o):
            me = o.data
            X = np.zeros(len(me.vertices) * 3)
            me.vertices.foreach_get("co", X)
            X = (np.array(o.matrix_world) @ np.c_[X.reshape(-1, 3), np.ones(len(me.vertices))].T).T[:, :3]
            li = np.zeros(len(me.loops), np.int64)
            me.loops.foreach_get("vertex_index", li)
            uvl = np.zeros(len(me.loops) * 2)
            me.uv_layers[0].data.foreach_get("uv", uvl)
            uv = np.zeros((len(me.vertices), 2))
            uv[li] = uvl.reshape(-1, 2)
            return X, uv

        Xc, uvc = verts_uv(cut)
        Xa, uva = verts_uv(ob)
        d, j = cKDTree(uva).query(uvc)
        ok = d < 2e-5
        log(f"uncut body: {int(ok.sum())} of his {len(Xc)} verts matched by UV in the template body ({len(Xa)} verts)")
        disp = np.zeros_like(Xa)
        known = np.zeros(len(Xa), bool)
        disp[j[ok]] = Xc[ok] - Xa[j[ok]]
        known[j[ok]] = True
        # weld the template's seam-split verts for the fill
        _, grp = np.unique(np.round(Xa * 1e5).astype(np.int64), axis=0, return_inverse=True)
        grp = grp.ravel()
        ng = grp.max() + 1
        me = ob.data
        me.calc_loop_triangles()
        T = np.zeros(len(me.loop_triangles) * 3, np.int64)
        me.loop_triangles.foreach_get("vertices", T)
        Tg = grp[T.reshape(-1, 3)]
        gk = np.zeros(ng, bool)
        gk[grp[known]] = True
        gd = np.zeros((ng, 3))
        cnt = np.zeros(ng)
        np.add.at(gd, grp[known], disp[known])
        np.add.at(cnt, grp[known], 1)
        gd[gk] /= cnt[gk][:, None]
        lap = Lap(ng, [list(t) for t in Tg])
        for _ in range(3000):
            nd = lap.avg(gd)
            gd[~gk] = nd[~gk]
        Xn = Xa + gd[grp]
        Xn[known] = Xa[known] + disp[known]
        log(f"uncut body: filled {int((~known).sum())} verts, displacement there mean "
            f"{np.linalg.norm(gd[grp][~known], axis=1).mean() * 100:.2f} cm")
        me.vertices.foreach_set("co", Xn.ravel())  # transforms applied: world = local
        me.update()
        # his own weights on his verts
        cut_names = {g.index: g.name for g in cut.vertex_groups}
        for i in np.nonzero(ok)[0]:
            v = cut.data.vertices[int(i)]
            k = int(j[i])
            for g in list(ob.data.vertices[k].groups):
                ob.vertex_groups[g.group].remove([k])
            for g in v.groups:
                nm = cut_names[g.group]
                vg = ob.vertex_groups.get(nm) or ob.vertex_groups.new(name=nm)
                vg.add([k], g.weight, "REPLACE")
        for m in list(ob.modifiers):
            ob.modifiers.remove(m)
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = self.arm
        ob.parent = self.arm
        ob.matrix_parent_inverse = self.arm.matrix_world.inverted()
        ob.name = "body_uncut"
        self.body_vis = cut          # what Unreal shows (cut under the garment): the previews
        cut.name = "body_cut"
        return ob

    def colliders(self):
        """What the trousers keep clear of: his skin (the shorts are hidden in Unreal, the tee is over them)."""
        parts = [(self.bx, self.bt)]
        if self.face_ob is not None:
            parts.append((self.fx, self.ft))
        return parts


# ================================================================ his body as a distance field

class Field:
    """A regular grid of values (cm frame) with trilinear lookups."""

    def __init__(self, lo, h, A):
        self.lo, self.h, self.A = np.asarray(lo, float), float(h), A

    def __call__(self, P):
        c = ((np.asarray(P) - self.lo) / self.h).T
        return ndimage.map_coordinates(self.A, c, order=1, mode="nearest")

    def coords(self):
        return [self.lo[i] + np.arange(self.A.shape[i]) * self.h for i in range(3)]


def voxelise(parts, lo, hi, h):
    """Inside/outside of a set of surfaces [(verts cm, tris)] on a grid. His body is cut under the garment (no ray
    parity): the surfaces are rasterised into a shell (dense samples on every triangle), the shell closed by a voxel,
    and each horizontal slice's enclosed area filled (a slice's rings close where a ray along the slice would not: the
    soles are open). Less the closing: the shell's own thickness."""
    n = np.ceil((np.asarray(hi) - lo) / h).astype(int) + 1
    t0 = time.time()
    shell = np.zeros(n, bool)
    for X, T in parts:
        A, B, C = X[T[:, 0]], X[T[:, 1]], X[T[:, 2]]
        L = np.maximum(np.maximum(np.linalg.norm(B - A, axis=1), np.linalg.norm(C - B, axis=1)),
                       np.linalg.norm(A - C, axis=1))
        K = np.clip(np.ceil(L / (0.45 * h)).astype(int), 1, 64)
        for k in np.unique(K):
            sel = K == k
            i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
            m = (i + j) <= k
            u, v = (i[m] / k)[None, :, None], (j[m] / k)[None, :, None]
            P = A[sel][:, None] + u * (B[sel] - A[sel])[:, None] + v * (C[sel] - A[sel])[:, None]
            q = np.round((P.reshape(-1, 3) - lo) / h).astype(int)
            q = q[np.all((q >= 0) & (q < n), axis=1)]
            shell[q[:, 0], q[:, 1], q[:, 2]] = True
    shell = ndimage.binary_dilation(shell, iterations=1)
    inside = np.zeros(n, bool)
    for k in range(n[2]):
        inside[:, :, k] = ndimage.binary_fill_holes(shell[:, :, k])
    inside = ndimage.binary_erosion(inside, iterations=1, border_value=0)
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
    """His lower body as the trousers see it: skin and the (hidden) shorts, filled; and the tee's inside, which the
    waistband stays in."""

    def __init__(self, him):
        D = him.dx[him.dx[:, 2] < him.bone["pelvis"][2] + 45]
        self.lo = np.array((-36.0, D[:, 1].min() - 3.0, -1.0))
        self.hi = np.array((36.0, D[:, 1].max() + 3.0, him.bone["pelvis"][2] + 25.0))
        self.inside = voxelise([(him.bx, him.bt)], self.lo, self.hi, VOX)
        self.sd = Field(self.lo, VOX, sdf_of(self.inside, VOX).astype(np.float32))
        # the tee: its rings close only above its hem (the hem's own height varies round him): the first closed
        # slice carried down below the hem, as the jersey falls about straight there
        tee = voxelise([(him.gx, him.gt[~him.g_short_tri])], self.lo, self.hi, VOX)
        area = tee.sum((0, 1)) * VOX * VOX
        zz = self.lo[2] + np.arange(tee.shape[2]) * VOX
        z_hem_top = max(v for v in Marks.tee_hem_profile(him) if v is not None)
        k0 = int(np.argmax((zz > z_hem_top + 0.4) & (area > 300)))
        for k in range(max(0, k0 - int(8.0 / VOX)), k0):
            tee[:, :, k] = tee[:, :, k0]
        self.tee_z_full = float(zz[k0])
        # smoothed (the voxel steps would ripple the waistband that follows it)
        self.tee = Field(self.lo, VOX, ndimage.gaussian_filter(sdf_of(tee, VOX), 1.2).astype(np.float32))
        self.tee_surf = TeeSurf(him)
        log(f"tee inside: closed from z {self.tee_z_full:.1f} (area {area[k0]:.0f} cm2), carried down 8 cm")


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
    """His landmarks (cm) and the tape measurements, from him dressed (the body is cut under the garment), ranges
    relative to his bones (he is not her height)."""

    def __init__(self, him):
        self.him = him
        X, T = him.dx, him.dt
        B = him.bone
        self.cy = 0.5 * (B["spine_03"][1] + B["pelvis"][1])
        self.armw_d = np.concatenate([him.armw, chain_weight(him.gw, len(him.gx), ARM_KEYS)])
        zp = float(B["pelvis"][2])
        zs = np.arange(zp - 25.0, zp + 40.0, 0.5)
        g = np.array([self.girth_at(z) for z in zs])
        self.zs, self.girth = zs, g
        m = (zs > zp + 5) & (zs < zp + 30)
        self.z_waist = float(zs[m][np.argmin(g[m])])
        m = (zs > zp - 15) & (zs < zp + 5)
        self.z_hip = float(zs[m][np.argmax(g[m])])
        # the crotch: lowest point between the legs, from below
        o = Vector((0.0, self.cy, 30.0))
        loc, *_ = him.bvh.ray_cast(o, Vector((0, 0, 1)))
        self.z_crotch = float(loc.z) if loc else zp - 10.0
        self.ankle = 0.5 * (B["foot_l"] + B["foot_r"] * np.array((-1, 1, 1)))
        self.knee = 0.5 * (B["calf_l"] + B["calf_r"] * np.array((-1, 1, 1)))
        self.hipj = 0.5 * (B["thigh_l"] + B["thigh_r"] * np.array((-1, 1, 1)))
        self.shoulder = 0.5 * (B["upperarm_l"] + B["upperarm_r"] * np.array((-1, 1, 1)))
        self.elbow = 0.5 * (B["lowerarm_l"] + B["lowerarm_r"] * np.array((-1, 1, 1)))
        S = him.gx[him.short_v]
        self.z_shorts_top = float(S[:, 2].max())
        self.z_shorts_low = float(S[:, 2].min())
        self.z_tee_hem = float(him.gx[him.tee_v, 2].min())
        self.tee_hem_by_angle = Marks.tee_hem_profile(him)

    def hem_at(self, P):
        """The tee's hem height above each point's angle round him."""
        prof = np.array([np.nan if v is None else v for v in self.tee_hem_by_angle])
        prof = np.where(np.isnan(prof), np.nanmax(prof), prof)
        ang = np.arctan2(P[:, 1] - self.cy, P[:, 0])
        return np.interp(ang, -math.pi + (np.arange(len(prof)) + 0.5) * 2 * math.pi / len(prof), prof,
                         period=2 * math.pi)

    @staticmethod
    def tee_hem_profile(him, nb=24):
        """The tee's hem height round him: its lowest verts per angle bin (from -pi, round the body's axis)."""
        cy = 0.5 * (him.bone["spine_03"][1] + him.bone["pelvis"][1])
        Tv = him.gx[him.tee_v & (him.gx[:, 2] < him.bone["pelvis"][2] + 40)]
        ang = np.arctan2(Tv[:, 1] - cy, Tv[:, 0])
        bins = np.floor((ang + math.pi) / (2 * math.pi) * nb).astype(int) % nb
        return [float(Tv[bins == k, 2].min()) if (bins == k).any() else None for k in range(nb)]

    def girth_at(self, z, arm_free=True):
        him = self.him
        P = slice_points(him.dx, him.dt, z, (self.armw_d < 0.5) if arm_free else None)
        return loop_perimeter(P, None) if len(P) > 5 else 0.0

    def report(self):
        g = lambda z: round(self.girth_at(z), 1)
        r = {
            "waist": [self.z_waist, g(self.z_waist)], "hip": [self.z_hip, g(self.z_hip)],
            "crotch_z": round(self.z_crotch, 1), "pelvis": self.him.bone["pelvis"].round(1).tolist(),
            "ankle": self.ankle.round(1).tolist(), "knee": self.knee.round(1).tolist(), "hipj": self.hipj.round(1).tolist(),
            "shoulder": self.shoulder.round(1).tolist(), "elbow": self.elbow.round(1).tolist(), "cy": round(self.cy, 1),
            "shorts_z": [round(self.z_shorts_low, 1), round(self.z_shorts_top, 1)], "tee_hem_z": round(self.z_tee_hem, 1),
            "tee_hem_by_angle": [None if v is None else round(v, 1) for v in self.tee_hem_by_angle],
            "girth_profile": {round(float(z), 1): round(float(v), 1) for z, v in zip(self.zs[::4], self.girth[::4])},
        }
        log("marks " + json.dumps(r))
        return r


def tee_clearance(him, mk):
    """How far the tee's lower part stands off his skin / the shorts (cm), by height band and side: the room the
    trousers' waistband has under it."""
    zp = float(him.bone["pelvis"][2])
    under = MeshSurf(np.concatenate([him.bx, him.gx]), np.concatenate([him.bt, him.gt[him.g_short_tri] + len(him.bx)]))
    sel = np.where(him.tee_v & (him.gx[:, 2] < mk.z_tee_hem + 16))[0]
    P = him.gx[sel]
    d, _ = under.signed(P, maxd=8.0)
    ang = np.degrees(np.arctan2(P[:, 1] - mk.cy, P[:, 0]))
    out = {}
    for z0 in np.arange(mk.z_tee_hem, mk.z_tee_hem + 16, 2.0):
        m = (P[:, 2] >= z0) & (P[:, 2] < z0 + 2)
        row = {}
        for nm, lo_, hi_ in (("front", -135, -45), ("left", -45, 45), ("back", 45, 135)):
            mm = m & (ang >= lo_) & (ang < hi_)
            if mm.any():
                row[nm] = [round(float(np.percentile(d[mm], 5)), 2), round(float(np.median(d[mm])), 2)]
        mm = m & ((ang >= 135) | (ang < -135))
        if mm.any():
            row["right"] = [round(float(np.percentile(d[mm], 5)), 2), round(float(np.median(d[mm])), 2)]
        out[round(float(z0), 1)] = row
    log("tee clearance (5th pct, median) by z: " + json.dumps(out))
    loops = boundary_loops([list(t) for t in him.bt])
    holes = [(len(l), round(float(him.bx[l, 2].min()), 1), round(float(him.bx[l, 2].max()), 1)) for l in loops]
    log(f"body boundary loops (n verts, z min, z max): {sorted(holes, key=lambda h: -h[0])[:12]}")
    return out


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
    """Closest-point queries on him (cm): body and neck."""

    def __init__(self, him):
        V, T = [], []
        for X, F in him.colliders():
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


class MeshSurf(Surf):
    """Closest-point queries on any mesh (cm)."""

    def __init__(self, V, F):
        self.V = np.asarray(V)
        self.T = tri_split(F)
        self.bvh = BVHTree.FromPolygons(self.V.tolist(), self.T.tolist())


def push_out(X, surf, clear, iters=3, lap=None, F=None, mask=None):
    """Move verts closer than `clear` to him out to it (then a touch of tangential relaxing)."""
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



# ================================================================ cloth helpers

def solidify(X, F, thick, uvs, rim_round=1.0):
    """Thicken a surface (cm): outer = X, inner = X - n*thick; rounded rims on open edges. uvs: per face corner.
    The normals are evened over their neighbours first: at an opening a vertex's few faces can tilt its normal one way
    and its neighbour's the other, and the inner layer and the rim would zig-zag along the hem."""
    vn = vertex_normals(X, F)
    lp = Lap(len(X), F)
    for _ in range(4):
        vn = 0.5 * vn + 0.5 * lp.avg(vn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1)[:, None], 1e-12)
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



# ================================================================ the trousers

class LowerShape:
    """The trousers' volume: his lower body (skin and the hidden shorts) closed and eased, tapered legs below the
    knee, and the waist inside the tee (the jersey hangs over the waistband)."""

    def __init__(self, him, marks, body, z_w):
        self.mk = marks
        self.z_w = z_w
        self.body = body
        h = VOX
        ins = body.inside.copy()
        # his arms and hands are not in the trousers: drop the voxels whose nearest skin is the arm's
        idx = np.argwhere(ins)
        P = body.lo + idx * h
        _, nearest = cKDTree(him.bx).query(P)
        drop = him.armw[nearest] > 0.3
        ins[tuple(idx[drop].T)] = False
        self.sd_raw = Field(body.lo, h, sdf_of(ins, h).astype(np.float32))   # him (no arms), not closed
        closed = closing(ins, TROUSERS["close"], h)
        self.sd = Field(body.lo, h, ndimage.gaussian_filter(sdf_of(closed, h), TROUSERS["soften"] / h).astype(np.float32))
        # the legs' lower part: per leg, a centre line from the knee to the ankle
        self.legs = []
        for s in (1, -1):
            k = him.bone["calf_l" if s > 0 else "calf_r"]
            a = him.bone["foot_l" if s > 0 else "foot_r"]
            self.legs.append((s, k, a))
        log(f"lower: closed body ({TROUSERS['close']} cm), waist edge z {z_w:.1f}")

    def ease(self, z):
        """The ease over his skin by height: the seat and thighs easy, closing in to the waist's from a few cm under
        the tee's hem (the fitted jersey lies over the waistband: the trousers fit inside it there)."""
        mk = self.mk
        zc, zw, zh = mk.z_crotch, self.z_w, mk.z_tee_hem
        return np.interp(z, [zc - 24, zc - 8, zc + 6, zh - 7, zh - 1, zw + 2],
                         [TROUSERS["ease_knee"], TROUSERS["ease_thigh"], TROUSERS["ease_hip"], TROUSERS["ease_hip"],
                          TROUSERS["ease_waist"], TROUSERS["ease_waist"]])

    def leg_centre(self, s, z):
        _, k, a = self.legs[0 if s > 0 else 1]
        t = (z - a[2]) / (k[2] - a[2])
        return a + (k - a) * t if np.isscalar(z) else a[None] + np.outer(t, k - a)

    def straight_sdf(self, P):
        """The lower legs: a tapered tube round each leg's knee-ankle line (fit_legs), narrowing away above the knee so
        his thigh (eased) takes over smoothly."""
        out = np.full(len(P), 99.0)
        for s, k, a in self.legs:
            c = self.leg_centre(s, P[:, 2])
            dx, dy = P[:, 0] - c[:, 0], P[:, 1] - c[:, 1]
            r = np.hypot(dx, dy)
            th = np.arctan2(dy, dx)
            R = self.leg_R[s](th, P[:, 2]) * (1 - 0.45 * smoothstep(k[2] + 1, k[2] + 18, P[:, 2]))
            out = np.minimum(out, r - R)
        return out

    def fit_legs(self, him):
        """Per leg and angle round the knee-ankle line, the radius the cloth needs at each height (his calf and
        ankle, eased; the taper's floor from the knee to the hem), and over it the taut envelope down the leg (the
        upper concave hull in height): the cloth lies over the calf and runs straight to the knee and the hem."""
        self.leg_R = {}
        angs = np.linspace(-math.pi, math.pi, 72, endpoint=False)
        for s, k, a in self.legs:
            z_k, z_h = float(k[2]), float(a[2]) + TROUSERS["hem_above_ankle"]
            zb = np.arange(z_h - 1.0, z_k + 6.01, 1.0)
            sel = (np.sign(him.bx[:, 0]) == s) & (him.bx[:, 2] > z_h - 3) & (him.bx[:, 2] < z_k + 8) \
                & (him.footw < 0.5)
            P = him.bx[sel]
            c = self.leg_centre(s, P[:, 2])
            dx, dy = P[:, 0] - c[:, 0], P[:, 1] - c[:, 1]
            r, th = np.hypot(dx, dy), np.arctan2(dy, dx)
            ai = np.round((th + math.pi) / (2 * math.pi) * len(angs)).astype(int) % len(angs)
            zi = np.clip(np.round(P[:, 2] - zb[0]).astype(int), 0, len(zb) - 1)
            need = np.zeros((len(zb), len(angs)))
            np.maximum.at(need, (zi, ai), r)
            for _ in range(4):  # fill the empty bins from their neighbours
                fill = ndimage.maximum_filter(need, size=(3, 3), mode=("nearest", "wrap"))
                need = np.where(need > 0, need, fill)
            need = ndimage.maximum_filter(need, size=(3, 3), mode=("nearest", "wrap"))   # +-1 cm, +-5 degrees
            need = ndimage.gaussian_filter(need, (0.7, 1.0), mode=("nearest", "wrap"))
            ease = np.interp(zb, [z_h, z_k], [TROUSERS["ease_ankle"], TROUSERS["ease_knee"]])
            need = need + ease[:, None]
            # the taper's floor: an oval from the knee's to the hem's half-girth
            oval = 1.0 + 0.06 * np.sin(angs) ** 2
            floor = np.interp(zb, [z_h, z_k], [TROUSERS["leg_hem_r"], TROUSERS["leg_knee_r"]])[:, None] * oval[None]
            need = np.maximum(need, floor)
            env = np.zeros_like(need)
            for j in range(len(angs)):
                env[:, j] = upper_hull_1d(zb, need[:, j])
            env = ndimage.gaussian_filter1d(env, 1.0, axis=1, mode="wrap")

            def R(th, z, env=env, zb=zb):
                t = np.clip(z - zb[0], 0, len(zb) - 1.0001)
                u = (np.asarray(th) + math.pi) / (2 * math.pi) * len(angs)
                return ndimage.map_coordinates(env, np.stack([t, u]), order=1, mode="grid-wrap")

            self.leg_R[s] = R
            log(f"leg {'L' if s > 0 else 'R'}: hem half-girth {env[1].mean():.2f} (circ {2 * math.pi * env[1].mean():.1f}),"
                f" calf max {env.mean(1).max():.2f}, knee {env[-7].mean():.2f} cm")
        log("legs fitted")

    def sdf(self, P):
        z = P[:, 2]
        f = self.sd(P) - self.ease(z)
        f = smin(f, self.straight_sdf(P), 2.5)
        # the legs part below the crotch (his thighs touch higher up; the cloth goes up between them)
        zc = self.mk.z_crotch - TROUSERS["crotch_drop"]
        f = np.where(z < zc, np.maximum(f, 0.12 - np.abs(P[:, 0])), f)
        # under the tee: the trousers stay inside it (below its hem too, as it falls about straight), and the
        # waistband follows its inside (a smooth band, no dents)
        ft = self.body.tee(P) + TROUSERS["tee_gap"]
        hem = self.mk.hem_at(P)
        w = smoothstep(hem - 0.3, hem + 0.5, z)       # inside it from its hem up (below, his hips widen)
        f = np.where(w > 0, (1 - w) * f + w * np.maximum(f, ft), f)
        bz = z > np.maximum(self.z_w - TROUSERS["band"] - 1.0, hem + 0.5)
        f = np.where(bz, ft, f)
        return f


def upper_hull_1d(x, y):
    """The least concave function over the points (x, y) (x increasing): a taut line over the bumps."""
    H = []
    for p in zip(x, y):
        while len(H) >= 2 and (H[-1][0] - H[-2][0]) * (p[1] - H[-2][1]) - (H[-1][1] - H[-2][1]) * (p[0] - H[-2][0]) >= 0:
            H.pop()
        H.append(p)
    H = np.array(H)
    return np.interp(x, H[:, 0], H[:, 1])


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
        ins = f[i] < 0
        if not ins.any():
            out[i] = (*centre, z)
            continue
        j0 = int(np.argmax(ins))                       # the first inside sample (the centre may be just outside)
        outs = np.where(~ins[j0:])[0]
        j = j0 + (outs[0] - 1 if len(outs) else len(rs) - 1 - j0)   # the last inside sample before the first exit
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
    return 0.55 * u + 0.45 * 0.5 * (1 - np.cos(u * math.pi))    # denser at both ends: the seam and the crease


def build_trousers(him, marks, body, z_w):
    lower = LowerShape(him, marks, body, z_w)
    lower.fit_legs(him)
    F = lower.sdf
    z_hem = float(marks.ankle[2]) + TROUSERS["hem_above_ankle"]
    # the crotch: where the legs part (the floor between them); its point at the floor's middle
    z_apex = marks.z_crotch - TROUSERS["crotch_drop"]
    ys = np.arange(marks.cy - 16, marks.cy + 16, 0.1)
    fin = F(np.stack([np.zeros(len(ys)), ys, np.full(len(ys), z_apex + 0.3)], 1)) < 0
    y_apex = float(ys[fin].mean()) if fin.any() else float(marks.cy)
    log(f"trousers: hem z {z_hem:.1f}, crotch z {z_apex:.1f} (floor y {ys[fin].min() if fin.any() else 0:.1f}.."
        f"{ys[fin].max() if fin.any() else 0:.1f}), waist edge z {z_w:.1f}")
    # rows: legs from the hem to just under the apex, the apex row, then the hips to the waist edge
    zk = float(marks.knee[2])
    leg_rows = graded_rows(z_hem, z_apex - 0.35, 0.8, [(z_hem, 0.25, 2.0), (z_hem + 4, 0.4, 5.5), (zk + 1.5, 0.45, 7.5)])
    zb = z_w - TROUSERS["band"]
    hip_rows = graded_rows(z_apex + 0.25, z_w, 0.32, [(zb, 0.12, 0.8), (zb - WELT["drop"], 0.12, 1.2),
                                                       (z_w, 0.15, 0.8)])
    rows = list(leg_rows) + [z_apex] + list(hip_rows)
    jc = len(leg_rows)
    NA = 900
    angles = np.linspace(-math.pi, math.pi, NA, endpoint=False)
    nh = 32   # columns per half panel (seam -> crease, crease -> seam)
    fr = column_fracs(nh)
    panels = {k: [] for k in ("LF", "LB", "RF", "RB")}
    for j, z in enumerate(rows):
        for s, (kf, kb) in ((1, ("LF", "LB")), (-1, ("RF", "RB"))):
            if j <= jc:
                c = lower.leg_centre(s, z)[:2]
                cur = ray_section(leg_field(lower, F, z_apex, y_apex), c, min(z, z_apex - 0.05), angles)
                cur[:, 2] = z
                # keep only his own leg's lobe (the other leg is not on these rays: rays start inside this one)
                xl = c[0]
            else:
                c = np.array((0.0, marks.cy))
                cur = ray_section(F, c, z, angles)
                xl = float(lower.leg_centre(s, min(z, marks.knee[2] + 30))[0]) * 0.92
            # cloth over hollows: each section towards its convex hull (the seat's cleft, the front between the
            # legs fully; the sides partly, so the waist-hip line still reads)
            hr = polar_radius(convex_hull_2d(cur[:, :2]), c, angles)
            rr = np.hypot(cur[:, 0] - c[0], cur[:, 1] - c[1])
            sy = np.sin(angles)
            if j <= jc:
                w = np.ones(len(angles))
            else:
                w = 0.65 + 0.35 * smoothstep(0.2, 0.7, np.abs(sy))
                # in front the bridge between the thighs fades out down to the crotch, so the hips meet the legs'
                # own round sections there (the seat stays bridged behind: it hangs from the buttocks)
                w = w * np.where(sy < 0, smoothstep(z_apex, z_apex + TROUSERS["bridge_ramp"], z), 1.0)
            rn = rr + w * np.maximum(hr - rr, 0)
            cs = crotch_section(lower, c, z, angles, rn, z_apex, y_apex) if j > jc else None
            if cs is not None:
                cur = cs
            else:
                cur[:, 0] = c[0] + np.cos(angles) * rn
                cur[:, 1] = c[1] + np.sin(angles) * rn
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
    # even the sections out up the body (the voxel field and the per-row hulls leave a fine ripple between rows):
    # the hips' rows and the legs' rows each smoothed along the columns' height, the crotch row and the edges kept
    # all rows together first (across the crotch row too, so the hips run into the legs without a ledge), then the
    # hips a little more; the crotch point and the centre seams (x = 0) pinned again after
    for k in G:
        g = G[k]
        for lo_, hi_, sig in ((1, len(rows) - 2, 2.0), (jc + 4, len(rows) - 2, TROUSERS["row_smooth"])):
            seg = g[lo_:hi_, :, :2]
            g[lo_:hi_, :, :2] = ndimage.gaussian_filter1d(seg, sig, axis=0, mode="nearest")
        ci = -1 if k[1] == "F" else 0
        g[jc, ci, :2] = (0.0, y_apex)
        g[jc + 1:, ci, 0] = 0.0
        G[k] = g
    return dict(G=G, rows=np.array(rows), jc=jc, z_hem=z_hem, z_apex=z_apex, y_apex=y_apex, lower=lower,
                nh=nh, fr=fr, z_w=z_w)


def crotch_curve(z, z_apex, y_apex, y0, H):
    """The centre seam's y at height z (front or back): straight up above z_apex + H (at y0), then a quarter ellipse
    curving under to the crotch point (level there, upright at the top), as a trouser rise is cut."""
    t = float(np.clip((z - z_apex) / H, 0.0, 1.0))
    return y0 + (y_apex - y0) * (1.0 - math.sqrt(max(0.0, 1.0 - (1.0 - t) ** 2)))


def leg_field(lower, F, z_apex, y_apex):
    """The legs' field just under the crotch: the closing's fill between his thighs cut away in front of and behind
    the crotch point (the rounded V of crotch_section, at the crotch point's own y), the cut drawing off forward and
    back down the thigh so it is gone a few cm lower; his own body (eased) always kept."""
    sl, r0 = TROUSERS["notch_slope"], TROUSERS["notch_round"]

    def fn(P):
        f = F(P)
        dz = np.maximum(z_apex - P[:, 2], 0.0)
        near = dz < 10.0
        if not near.any():
            return f
        Q = P[near]
        g = np.sqrt((Q[:, 0] * sl) ** 2 + r0 ** 2) - r0 + 1.6 * dz[near]
        cut = np.maximum((y_apex - g) - Q[:, 1], Q[:, 1] - (y_apex + g))
        body = lower.sd_raw(Q) - lower.ease(Q[:, 2])
        f[near] = np.minimum(np.maximum(f[near], cut), body)
        return f

    return fn


def crotch_section(lower, c, z, angles, rn, z_apex, y_apex, rmax=30.0, step=0.1):
    """A hip row near the crotch: the bridged section (radius rn round c), cut under the centre seams' curves by a
    rounded V opening between the legs (front and back), but never into him (his own body, eased, stays inside).
    The outermost crossing per ray from the seams' midpoint, so the two leg lobes and the bridge between them are all
    kept. None above the curves (the plain bridged section applies)."""
    if z - z_apex >= max(TROUSERS["rise_front"], TROUSERS["rise_back"]):
        return None
    y0f = c[1] - float(np.interp(-math.pi / 2, angles, rn, period=2 * math.pi))
    y0b = c[1] + float(np.interp(math.pi / 2, angles, rn, period=2 * math.pi))
    ycf = crotch_curve(z, z_apex, y_apex, y0f, TROUSERS["rise_front"])
    ycb = crotch_curve(z, z_apex, y_apex, y0b, TROUSERS["rise_back"])
    c2 = np.array((0.0, 0.5 * (ycf + ycb)))
    rs = np.arange(0.0, rmax, step)
    d = np.stack([np.cos(angles), np.sin(angles)], 1)
    X = c2[0] + d[:, 0, None] * rs[None]
    Y = c2[1] + d[:, 1, None] * rs[None]
    th = np.arctan2(Y - c[1], X - c[0])
    rad = np.hypot(X - c[0], Y - c[1]) - np.interp(th, angles, rn, period=2 * math.pi)
    sl, r0 = TROUSERS["notch_slope"], TROUSERS["notch_round"]
    g = np.sqrt((X * sl) ** 2 + r0 ** 2) - r0
    cloth = np.maximum(rad, np.maximum((ycf - g) - Y, Y - (ycb + g)))
    P = np.stack([X, Y, np.full_like(X, z)], -1).reshape(-1, 3)
    body = (lower.sd_raw(P) - lower.ease(z)).reshape(X.shape)
    f = np.minimum(cloth, body)
    out = np.zeros((len(angles), 3))
    for i in range(len(angles)):
        w = np.nonzero(f[i] < 0)[0]
        if not len(w):
            out[i] = (*c2, z)
            continue
        j = int(w[-1])
        r = rs[j] + (f[i, j] / (f[i, j] - f[i, j + 1]) * step if j + 1 < len(rs) else 0.0)
        out[i] = (c2[0] + d[i, 0] * r, c2[1] + d[i, 1] * r, z)
    return out


def graded_rows(z0, z1, step, dense):
    """Row heights from z0 to z1 about `step` apart, finer (step2) within `width` of each dense z."""
    zs = [z0]
    z = z0
    while z < z1 - 1e-6:
        h = step
        for zc, h2, wd in dense:
            if abs(z - zc) < wd:
                h = min(h, h2)
        z = min(z + h, z1)
        zs.append(z)
    return np.array(zs)


WELT = dict(drop=6.0, from_cb=4.0, width=11.0, lip=0.55)   # back welt pockets: below the band, from the centre back
POCKET = dict(top_from_side=8.5, depth=15.5)                 # slanted front pockets: opening at the band, to the side
FLY = dict(width=3.3, bottom=7.0)                            # fly topstitch: from the centre front; its bottom above the crotch
DART = dict(from_cb=8.8, length=8.0)


def trousers_detail(T, tr, marks):
    """Per-vertex displacement (cm, along the normal) for the tailoring, plus the crease edges and the button's place.
    Every feature is placed in each panel's own (arc across the row, height) coordinates."""
    V, idx, nh = T["V"], T["idx"], tr["nh"]
    n = len(V)
    N = vertex_normals(V, T["F"])
    disp = np.zeros(n)
    z_w, zc = tr["z_w"], tr["z_apex"]
    zb = z_w - TROUSERS["band"]
    sharp = []
    rows = tr["rows"]
    gauss = lambda x, w: np.exp(-(x / w) ** 2)
    for k, I in idx.items():
        front = k[1] == "F"
        nr, nc = I.shape
        P = V[I]                                                    # (rows, cols, 3)
        seg = np.linalg.norm(np.diff(P, axis=1), axis=2)
        S = np.concatenate([np.zeros((nr, 1)), np.cumsum(seg, 1)], 1)   # arc from column 0
        L = S[:, -1:]
        # from the side seam / from the centre (front: col 0 is the side; back: col 0 is the centre/inseam)
        s_side = S if front else L - S
        s_mid = L - S if front else S
        s_crease = S - S[:, nh:nh + 1]
        Z = P[..., 2]
        d = np.zeros((nr, nc))
        below_band = Z < zb - 0.05
        # the pressed crease: a sharp ridge, front to the band, back to below the seat
        if front:
            # pressed sharp down the leg, softening over the thigh to a faint line at the band
            fade = 1 - smoothstep(zc - 2, zc + 9, Z)
        else:
            fade = 1 - smoothstep(zc - 12, zc - 3, Z)
        tent = np.clip(1 - np.abs(s_crease) / TROUSERS["crease_w"], 0, 1) ** 1.7
        d += TROUSERS["crease_h"] * tent * fade
        # natural folds (outward only, so none dips into him): behind the knee a few shallow horizontal ripples
        # (the cloth gathers as he stands), at the front of the knee a softer pair; above the hem a small break,
        # the ripples running into a shallow V at the crease; on the front of the thigh, faint diagonal whiskers
        # from the crotch
        zk, zh = float(marks.knee[2]), tr["z_hem"]
        ripple = lambda u: 0.5 + 0.5 * np.cos(u)
        if front:
            kz = Z - (zk + 1.0) - 0.12 * np.abs(s_crease)
            d += 0.07 * ripple(kz / 3.2 * 2 * math.pi) * gauss(kz, 4.0) * gauss(s_crease, 7.0)
            az = Z - (zh + 3.6) + 0.22 * np.abs(s_crease)          # the V points down at the crease
            d += 0.24 * ripple(az / 2.6 * 2 * math.pi) * gauss(az, 2.6) * gauss(s_crease, 6.5) \
                * smoothstep(zh + 0.6, zh + 1.8, Z)
            wz = Z - (zc + 2.0) - 0.55 * np.maximum(s_mid, 0)       # rising from the crotch towards the hip
            d += 0.05 * ripple(wz / 2.4 * 2 * math.pi) * gauss(wz, 3.0) * gauss(s_mid - 6.0, 5.0) * below_band
        else:
            kz = Z - (zk + 2.0) + 0.1 * s_crease
            d += 0.15 * ripple(kz / 2.3 * 2 * math.pi) * gauss(kz, 3.6) * gauss(s_crease, 5.5)
            az = Z - (zh + 3.2)
            d += 0.08 * ripple(az / 2.8 * 2 * math.pi) * gauss(az, 2.2) * gauss(s_crease, 6.0) \
                * smoothstep(zh + 0.6, zh + 1.8, Z)
        # seams: shallow valleys with the pressed allowance either side
        seam = lambda x: -0.045 * gauss(x, 0.16) + 0.018 * gauss(np.abs(x) - 0.45, 0.3)
        d += seam(s_side) * below_band                                # side seams
        inner = np.where(Z < zc, s_mid, 99.0)                          # inseams
        d += seam(inner)
        if not front:
            d += np.where(Z >= zc, seam(s_mid), 0) * below_band        # centre back
        # the waistband: stands proud of the trousers, its seam a crisp valley
        band = smoothstep(zb - 0.08, zb + 0.18, Z)
        d += 0.13 * band - 0.06 * gauss(Z - zb, 0.12)
        d += -0.025 * gauss(Z - (zb + 0.35), 0.06) - 0.025 * gauss(Z - (z_w - 0.35), 0.06)   # band topstitch
        if front:
            # fly: the left front laps over; its edge at the centre and a J of topstitching
            if k[0] == "L":
                zbot = zc + FLY["bottom"]
                y = Z - zbot
                # the J: straight down at FLY width, then a quarter circle into the centre
                rr = FLY["width"]
                dj = np.where(y >= 0, np.abs(s_mid - rr), np.abs(np.hypot(s_mid, y) - rr))
                on = (Z < zb) & (Z > zbot - rr)
                d += np.where(on, -0.03 * gauss(dj, 0.07), 0)
                # the fly's folded edge at the centre: a soft roll, the lap a hair proud of the panel beside it
                edge = (Z < zb) & (Z > zbot - rr * 0.8)
                d += np.where(edge, 0.05 * gauss(s_mid - 0.18, 0.2) + 0.015 * (1 - smoothstep(rr - 0.3, rr + 0.2, s_mid)), 0)
            # slanted pocket: from the band (POCKET top_from_side from the side seam) down to the side seam
            a = np.array((POCKET["top_from_side"], zb))
            b = np.array((0.0, zb - POCKET["depth"]))
            q = np.stack([s_side, Z], -1) - a
            t = np.clip((q @ (b - a)) / ((b - a) @ (b - a)), 0, 1)
            dist = np.linalg.norm(q - t[..., None] * (b - a), axis=-1)
            sgn = np.sign(np.cross(np.broadcast_to(b - a, q.shape), q))
            on = (t > 0.0) & (t < 1.0) & below_band
            d += np.where(on, -0.05 * gauss(dist, 0.1) + 0.045 * smoothstep(0.0, 0.3, dist) * (sgn > 0)
                          * (1 - smoothstep(0.5, 1.5, dist)), 0)
        else:
            # welt pocket: two lips between grooves, ends bar-tacked
            zt = zb - WELT["drop"]
            sw0, sw1 = WELT["from_cb"], WELT["from_cb"] + WELT["width"]
            inw = smoothstep(sw0 - 0.1, sw0 + 0.1, s_mid) * (1 - smoothstep(sw1 - 0.1, sw1 + 0.1, s_mid))
            lp = WELT["lip"]
            prof = -0.05 * gauss(Z - (zt + lp), 0.06) - 0.06 * gauss(Z - zt, 0.05) - 0.05 * gauss(Z - (zt - lp), 0.06) \
                + 0.03 * (gauss(Z - (zt + lp / 2), 0.18) + gauss(Z - (zt - lp / 2), 0.18))
            d += prof * inw
            # dart: a tapering valley down from the band
            dz = (zb - Z) / DART["length"]
            on = (dz > 0) & (dz < 1)
            d += np.where(on, -0.05 * (1 - dz) * gauss(s_mid - DART["from_cb"], 0.12 + 0.1 * (1 - dz)), 0)
        disp[I.ravel()] = np.where(np.abs(d.ravel()) > np.abs(disp[I.ravel()]), d.ravel(), disp[I.ravel()])
    Vd = V + N * disp[:, None]
    # the button: on the band at the centre front, on the left (under-lap) side of the fly's edge
    I = idx["LF"]
    P = V[I]
    zb_mid = zb + TROUSERS["band"] * 0.5
    r = int(np.argmin(np.abs(P[:, -1, 2] - zb_mid)))
    S = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P[r], axis=0), axis=1))])
    c = int(np.argmin(np.abs((S[-1] - S) - 1.5)))
    btn = (Vd[I[r, c]], N[I[r, c]])
    return Vd, sharp, btn


def button_part(at, normal, mat_i):
    """A small domed gold button (1.5 cm), a raised rim, a shank, facing along the normal (cm)."""
    prof = [(0.0, 0.26), (0.32, 0.25), (0.58, 0.21), (0.70, 0.17), (0.75, 0.12), (0.76, 0.05), (0.72, 0.0),
            (0.22, 0.0), (0.2, -0.12), (0.0, -0.12)]
    seg = 40
    n = Vector(normal).normalized()
    up = Vector((0, 0, 1))
    u = (up - n * up.dot(n)).normalized()
    v = n.cross(u)
    verts, faces = [], []
    for r, h in prof:
        for k in range(seg):
            a = 2 * math.pi * k / seg
            p = Vector(at) + n * (h + 0.12) + (u * math.cos(a) + v * math.sin(a)) * r
            verts.append(p[:])
    for i in range(len(prof) - 1):
        for k in range(seg):
            k2 = (k + 1) % seg
            faces.append([i * seg + k, i * seg + k2, (i + 1) * seg + k2, (i + 1) * seg + k])
    X = np.array(verts)
    uv = [[((X[q][j][0] - at[0]) * 0.01, (X[q][j][2] - at[2]) * 0.01) for j in range(4)] for q in faces]
    return X, faces, uv


def finish_trousers(T, Vd, tr, btn):
    """Thickness (the band thicker), per-panel UVs (U across the panel from its first seam, V up; metres), the button
    joined in. Returns verts, faces, uvs, the source surface vertex of each vert, material indices, sharp edges."""
    idx, F, fpanel = T["idx"], T["F"], T["fpanel"]
    keys = list(idx)
    sval = []
    for k in keys:
        I = idx[k]
        P = Vd[I]
        S = np.concatenate([np.zeros((I.shape[0], 1)), np.cumsum(np.linalg.norm(np.diff(P, axis=1), axis=2), 1)], 1)
        sval.append({int(v): float(x) for v, x in zip(I.ravel(), S.ravel())})
    uvs = [[(sval[pi][v] * 0.01, Vd[v, 2] * 0.01) for v in f] for f, pi in zip(F, fpanel)]
    zb = tr["z_w"] - TROUSERS["band"]
    thick = np.where(Vd[:, 2] > zb, TROUSERS["band_thick"], TROUSERS["thick"])
    # the hem is turned up: a touch thicker at the bottom edge
    thick = np.where(Vd[:, 2] < tr["z_hem"] + 1.0, TROUSERS["thick"] * 1.8, thick)
    X, FF, UV, src = solidify(Vd, F, thick, uvs, rim_round=1.0)
    mat = [0] * len(FF)
    # no button: the waistband is under the tee, and a button would stand through the jersey
    return X, FF, UV, src, mat


def field_grad(fn, P, h=0.05):
    g = np.zeros_like(P)
    for k in range(3):
        d = np.zeros(3)
        d[k] = h
        g[:, k] = (fn(P + d) - fn(P - d)) / (2 * h)
    return g / np.maximum(np.linalg.norm(g, axis=1)[:, None], 1e-9)


def pull_inside(V, field, gap, mask, iters=3):
    """Verts (mask) less than `gap` inside a field (inside < 0) moved in along its gradient."""
    for _ in range(iters):
        d = np.full(len(V), -99.0)
        d[mask] = field(V[mask])
        bad = mask & (d > -gap)
        if not bad.any():
            break
        V[bad] -= field_grad(field, V[bad]) * (d[bad] + gap)[:, None]
    log(f"pull_inside: {int(bad.sum())} verts moved (gap {gap} cm)")
    return V


class TeeSurf(MeshSurf):
    """The tee's mesh (rest pose), signed distance positive outside it, whichever way its faces wind."""

    def __init__(self, him):
        super().__init__(him.gx, [list(t) for t in him.gt[~him.g_short_tri]])
        c = him.bone["spine_04"]           # well inside the jersey (not near its hem)
        d, _ = MeshSurf.signed(self, np.array([[0.0, float(c[1]), float(c[2])]]), maxd=60.0)
        log(f"tee mesh: faces wind {'inwards' if d[0] > 0 else 'outwards'} (spine_04 at {d[0]:.1f} cm)")
        self.flip = -1.0 if d[0] > 0 else 1.0

    def signed(self, P, maxd=10.0):
        d, n = MeshSurf.signed(self, P, maxd)
        return d * self.flip, n * self.flip


def pull_in_tee(V, tee, gap, mask, iters=3):
    """Verts (mask) outside the tee or less than `gap` inside it moved in, on the tee's exact mesh."""
    for it in range(iters):
        idx = np.nonzero(mask)[0]
        d, n = tee.signed(V[idx], maxd=4.0)
        bad = (d > -gap + 0.01) & (d < 90)
        V[idx[bad]] -= n[bad] * (d[bad] + gap)[:, None]
        log(f"pull_in_tee {it}: {int(bad.sum())} verts (max out {d[bad].max() if bad.any() else 0:.2f} cm)")
        if not bad.any():
            break
    return V


def assemble_trousers(tr, him, marks, surf, body):
    """The four panel grids welded into one mesh (side seams, inseams, centre front and back shared), smoothed,
    kept off him and off the top; then the details. Returns verts, quads and per-vertex data."""
    G, jc, nh = tr["G"], tr["jc"], tr["nh"]
    nr, nc = G["LF"].shape[:2]
    ids = {}
    V = []

    def vid(key, p):
        if key not in ids:
            ids[key] = len(V)
            V.append(np.array(p, float))
        else:
            V[ids[key]] = 0.5 * (V[ids[key]] + p)
        return ids[key]

    def key(k, r, c):
        side = "L" if k[0] == "L" else "R"
        front = k[1] == "F"
        last = nc - 1
        if (front and c == 0) or (not front and c == last):
            return ("side", side, r)
        inner = (front and c == last) or (not front and c == 0)
        if inner:
            if r == jc:
                return ("apex",)
            if r < jc:
                return ("inseam", side, r)
            return ("cf" if front else "cb", r)
        return (k, r, c)

    idx = {}
    for k, g in G.items():
        I = np.zeros((nr, nc), int)
        for r in range(nr):
            for c in range(nc):
                I[r, c] = vid(key(k, r, c), g[r, c])
        idx[k] = I
    V = np.array(V)
    F, fpanel = [], []
    for pi, (k, I) in enumerate(idx.items()):
        for r in range(nr - 1):
            for c in range(nc - 1):
                q = [I[r, c], I[r, c + 1], I[r + 1, c + 1], I[r + 1, c]]
                if len(set(q)) < 3:
                    continue
                if len(set(q)) == 3:   # a quad collapsed at the crotch point: a triangle
                    q = list(dict.fromkeys(q))
                F.append(q)
                fpanel.append(pi)
    # outward faces: each panel's winding by its mean normal against the way out from the body's axis
    fpanel = np.array(fpanel)
    for pi in range(4):
        sel = np.where(fpanel == pi)[0]
        dots = 0.0
        for f in sel[::7]:
            q = F[f]
            p = V[q].mean(0)
            n = np.cross(V[q[1]] - V[q[0]], V[q[-1]] - V[q[0]])
            k = list(idx)[pi]
            s = 1 if k[0] == "L" else -1
            if p[2] < tr["z_apex"]:
                c = tr["lower"].leg_centre(s, p[2])
                o = p - np.array((c[0], c[1], p[2]))
            else:
                o = p - np.array((0.0, marks.cy, p[2]))
            dots += float(n @ o)
        if dots < 0:
            for f in sel:
                F[f] = F[f][::-1]
    lap = Lap(len(V), F)
    bnd = np.zeros(len(V), bool)
    for a, b in boundary_edges(F):
        bnd[a] = bnd[b] = True
    V = taubin(V, lap, 6, fixed=bnd)
    under_tee = V[:, 2] > marks.hem_at(V) + 0.2
    V = push_out(V, surf, 0.3, iters=2, mask=~under_tee)
    V = pull_inside(V, body.tee, TROUSERS["tee_gap"], under_tee)
    V = pull_in_tee(V, body.tee_surf, TROUSERS["tee_gap"], V[:, 2] > marks.hem_at(V) + 0.2)
    return dict(V=V, F=F, idx=idx, fpanel=fpanel, lap=lap, bnd=bnd, nr=nr, nc=nc)


# ================================================================ skinning, pose tests, export

class WeightSource:
    """Triangles of a mesh (a chosen part) with per-vertex bone weights, for nearest-point lookups."""

    def __init__(self, X, T, Wd, groups):
        self.X, self.T, self.groups = X, T, groups
        gi = {g: i for i, g in enumerate(groups)}
        self.W = np.zeros((len(X), len(groups)), np.float32)
        for g, a in Wd.items():
            if g in gi:
                self.W[:, gi[g]] = a
        self.bvh = BVHTree.FromPolygons(X.tolist(), T.tolist())

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


def weight_groups(him):
    return sorted(set(him.bw) | set(him.gw))


def skin_trousers(him, marks, V, lap, panel_side):
    """Weights at the trousers' surface verts: from his body (uncut) below the waist, each
    panel from its own side, no foot bones (the hem must not ride the foot); under the tee, the tee's own weights
    (so the waistband moves as the jersey over it does and cannot come through it), blended down to the body's over
    the 4 cm below the tee's hem."""
    groups = weight_groups(him)
    nb = len(him.bx)
    X = np.concatenate([him.bx, him.gx])
    Wd = {g: np.concatenate([him.bw.get(g, np.zeros(nb)), him.gw.get(g, np.zeros(len(him.gx)))]) for g in groups}
    armw = np.concatenate([him.armw, chain_weight(him.gw, len(him.gx), ARM_KEYS)])
    footw = np.concatenate([him.footw, np.zeros(len(him.gx))])
    T = him.bt
    no_arm = armw[T].max(1) < 0.2
    no_foot = footw[T].max(1) < 0.25
    low = X[T][:, :, 2].max(1) < marks.z_shorts_top + 4
    cx = X[T][:, :, 0].mean(1)
    W = np.zeros((len(V), len(groups)), np.float32)
    for s in (1, -1):
        side = (np.sign(cx) == s) | (np.abs(cx) < 2.0)
        src = WeightSource(X, T[no_arm & no_foot & low & side], Wd, groups)
        m = panel_side == s
        W[m] = src.at(V[m])
    tee_T = him.gt[~him.g_short_tri]
    tee_T = tee_T[(him.gx[tee_T][:, :, 2].max(1) < marks.z_tee_hem + 20) & (armw[tee_T + nb].max(1) < 0.2)]
    prof = np.array([np.nan if v is None else v for v in marks.tee_hem_by_angle])
    prof = np.where(np.isnan(prof), np.nanmax(prof), prof)
    ang = np.arctan2(V[:, 1] - marks.cy, V[:, 0])
    hem = marks.hem_at(V)
    t = smoothstep(hem - 4.0, hem - 0.5, V[:, 2])
    m = t > 0
    if m.any():
        Wt = WeightSource(him.gx, tee_T, him.gw, groups).at(V[m])
        W[m] = W[m] * (1 - t[m])[:, None] + Wt * t[m][:, None]
    log(f"trousers skin: {int(m.sum())} verts take the tee's weights (fully {int((t >= 1).sum())})")
    return finalise_weights(W, lap, smooth_iters=30), groups


def make_skinned(him, name, X, F, UV, mats, mat_idx, Wsurf, src, groups, sharp=None):
    ob = arrays_object(name, X, F, mats=mats, mat_idx=mat_idx, uvs=UV, sharp=sharp)
    W = Wsurf[src]
    used = [i for i in range(len(groups)) if W[:, i].max() > 0]
    for i in used:
        vg = ob.vertex_groups.new(name=groups[i])
        nz = np.nonzero(W[:, i])[0]
        ww = np.round(W[nz, i], 4)
        for w in np.unique(ww):
            vg.add(nz[ww == w].tolist(), float(w), "REPLACE")
    ob.parent = him.arm
    ob.matrix_parent_inverse = him.arm.matrix_world.inverted()
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = him.arm
    log(f"{name}: {len(X)} verts, {len(used)} bones, max influences {(W > 0).sum(1).max()}")
    return ob


def bind_body(him):
    for o in (him.body_ob, him.body_vis, him.face_ob, him.garment_ob, him.tee_ob):
        if o is None:
            continue
        for m in o.modifiers:
            if m.type == "ARMATURE":
                m.object = him.arm


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


def clip_check(him, ob, step=3, under=None):
    """Garment verts inside his skin as Unreal shows it (his cut body: where MetaHuman removed the skin under the
    default garment there is none to poke through) in the current pose: count, deepest (cm)."""
    V, T = eval_points(him.body_vis)
    layers = [(V, T)]
    if under is not None:
        layers.append(eval_points(under))
    G, _ = eval_points(ob)
    G = G[::step]
    bad, deep, where = 0, 0.0, []
    for V, T in layers:
        bvh = BVHTree.FromPolygons(V.tolist(), T.tolist())
        for p in G:
            loc, nor, fi, dist = bvh.find_nearest(Vector(p), 1.2)
            if loc is None:
                continue
            if (Vector(p) - loc).dot(nor) < 0:
                bad += 1
                deep = max(deep, dist)
                where.append(p)
    # where they are: clusters of 4 cm cells, the biggest few (cell centre, count)
    cells = {}
    for p in where:
        k = tuple((np.asarray(p) // 4 * 4 + 2).astype(int).tolist())
        cells[k] = cells.get(k, 0) + 1
    top = sorted(cells.items(), key=lambda kv: -kv[1])[:6]
    return bad * step, deep, top


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


POSES = {  # name: [(bone, world axis, degrees)]; his left is +X, his front -Y
    "arms_down": [("upperarm_l", (0, 1, 0), 30), ("upperarm_r", (0, 1, 0), -30)],
    "arms_raise": [("upperarm_l", (0, 1, 0), -50), ("upperarm_r", (0, 1, 0), 50)],
    "arms_fwd": [("upperarm_l", (1, 0, 0), 55), ("upperarm_r", (1, 0, 0), 55)],
    "elbows": [("lowerarm_l", (1, 0, 0), 80), ("lowerarm_r", (1, 0, 0), 80)],
    "step": [("thigh_l", (1, 0, 0), 30), ("thigh_r", (1, 0, 0), -15), ("calf_l", (1, 0, 0), -35)],
    "sit": [("thigh_l", (1, 0, 0), 80), ("thigh_r", (1, 0, 0), 80), ("calf_l", (1, 0, 0), -80),
            ("calf_r", (1, 0, 0), -80)],
    "lean": [("spine_03", (0, 1, 0), 12), ("spine_01", (1, 0, 0), 10)],
}


def pose_tests(him, garments, args, colours, under_tee):
    bind_body(him)
    arm = him.arm
    res = {"import": {g.name: clip_check(him, g) for g in garments}}
    moved = [pb.name for pb in arm.pose.bones if (pb.matrix_basis - Matrix.Identity(4)).to_3x3().to_scale().length > 0
             or pb.matrix_basis != Matrix.Identity(4)]
    log(f"pose at import: {res['import']}, bones off rest: {len(moved)} {moved[:12]}")
    reset_pose(arm)
    res["rest"] = {g.name: clip_check(him, g) for g in garments}
    log(f"pose at rest: {res['rest']}")
    for g, v in res["rest"].items():
        log(f"rest clip cells {g}: {v[2]}")
    for g in [him.body_ob] + list(garments):
        Xe, _ = eval_points(g)
        X0 = np.array([(g.matrix_world @ v.co)[:] for v in g.data.vertices]) * 100.0
        dd = np.linalg.norm(Xe - X0, axis=1)
        log(f"rest vs mesh {g.name}: mean {dd.mean():.3f} max {dd.max():.3f} cm, argmax at {X0[dd.argmax()].round(1)}")
    for name, moves in POSES.items():
        reset_pose(arm)
        for bone, ax, deg in moves:
            pose_bone_world(arm, bone, ax, deg)
        res[name] = {g.name: clip_check(him, g) for g in garments}
        res[name]["tee"] = {g.name: tee_check(him, g, under_tee) for g in garments}
        log(f"pose {name}: " + ", ".join(f"{k} {v[0]} inside (deepest {v[1]:.2f} cm)" for k, v in res[name].items() if k != "tee") + f"; through the tee {res[name]['tee']}")
        snapshot(os.path.join(args.out, f"{NAME}_pose_{name}"), colours, (("front", (0, 1, 0)), ("q", (0.62, 1, -0.12))),
                 centre=(0, 0, 0.95), ortho=1.9, res=(700, 900))
    reset_pose(arm)
    return res


def retarget(src, dst):
    """Him pose from another armature of the same skeleton, as Unreal plays an animation on him: each bone takes
    the source's local rotation on him own bone offsets (his proportions). (After agent-05's overshirt.py.)"""
    for pb in dst.pose.bones:
        sb = src.pose.bones.get(pb.name)
        if sb is None or pb.parent is None:
            continue
        sl = (sb.parent.matrix.inverted() @ sb.matrix) if sb.parent else sb.matrix
        rl = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
        want = Matrix.Translation(rl.translation) @ sl.to_quaternion().to_matrix().to_4x4()
        pb.matrix_basis = rl.inverted() @ want


ANIMS = ("anim_AS_reel_him_body", "anim_mhc_mh001_fmn_b_idle", "anim_AS_line1_bodyidle")   # what he plays


def load_anims(args):
    """His body animations (the reel's and the line's), each on its own armature, hidden: [(name, armature, its
    objects, (f0, f1))]."""
    out = []
    for name in ANIMS:
        p = os.path.join(args.src, name + ".fbx")
        if not os.path.exists(p):
            continue
        before = set(bpy.data.actions)
        objs = import_fbx(p)
        acts = [a for a in bpy.data.actions if a not in before]
        src = next((o for o in objs if o.type == "ARMATURE"), None)
        if not acts or src is None:
            continue
        for o in objs:
            o.hide_render = True
            if o.type == "MESH":
                o.hide_viewport = True
        f0, f1 = (int(x) for x in acts[0].frame_range)
        out.append((name, src, objs, (f0, f1)))
        log(f"anim {name}: frames {f0}..{f1}")
    return out


def anim_frames(anim, samples):
    f0, f1 = anim[3]
    return sorted({int(f0 + (f1 - f0) * k / max(samples - 1, 1)) for k in range(samples)})


def set_anim_pose(him, anim, f):
    reset_pose(him.arm)
    bpy.context.scene.frame_set(f)
    retarget(anim[1], him.arm)
    bpy.context.view_layer.update()


def tee_check(him, ob, idx):
    """Trouser verts (idx: the ones under the tee at rest) that are outside the tee in the current pose: count,
    farthest out (cm)."""
    G, _ = eval_points(ob)
    X, T = eval_points(him.tee_ob)
    bvh = BVHTree.FromPolygons(X.tolist(), T.tolist())
    bad, far = 0, 0.0
    for p in G[idx]:
        loc, nor, fi, dist = bvh.find_nearest(Vector(p), 2.0)
        if loc is not None and (Vector(p) - loc).dot(nor) > 0:
            bad += 1
            far = max(far, dist)
    return bad, far


def idle_test(him, garments, args, colours, anims, under_tee, samples=8):
    bind_body(him)
    res = {}
    for an in anims:
        frames = anim_frames(an, samples)
        for f in frames:
            set_anim_pose(him, an, f)
            r = {g.name: clip_check(him, g) for g in garments}
            r["tee"] = {g.name: tee_check(him, g, under_tee) for g in garments}
            res[f"{an[0]}:{f}"] = r
            log(f"{an[0]} {f}: " + ", ".join(f"{k} {v[0]} inside (deepest {v[1]:.2f} cm) at {v[2][:3]}"
                                               for k, v in r.items() if k != "tee") + f"; through the tee {r['tee']}")
            if f == frames[len(frames) // 2]:
                snapshot(os.path.join(args.out, f"{NAME}_{an[0].replace('anim_', '')}"), colours, VIEWS[:3],
                         centre=(0, 0, 0.95), ortho=1.9, res=(700, 900))
    reset_pose(him.arm)
    return res


def bake_clearance(him, ob, n, Q, lap, src, args, surf, anims, gap=0.3, iters=2, samples=10, arms=True, skip=None):
    """Keep his skin from poking through as he moves: pose him through his animations (and the arms down), find where
    the garment's inner layer comes within `gap` of his skin (not where the skin faces the cloth from outside: an arm
    closing onto the torso, a sandwich no offset can fix), and push the cloth out by that much in the rest pose, away
    from him there, spread and smoothed over the surface; twice, as the push changes the posed cloth a little. Last,
    nothing left closer than gap/2 to him at rest. `skip`: surface verts left alone (the waist under the tee, which
    rides the tee's weights instead)."""
    bind_body(him)
    me = ob.data
    poses = [("anim", an, f) for an in anims for f in anim_frames(an, samples)]
    poses.append(("pose", "arms_down", None))
    for it in range(iters):
        X = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", X)
        X = X.reshape(-1, 3) * 100.0
        need = np.zeros(n)
        for kind, what, f in poses:
            if kind == "anim":
                set_anim_pose(him, what, f)
            else:
                reset_pose(him.arm)
                for bone, ax, deg in POSES[what]:
                    pose_bone_world(him.arm, bone, ax, deg)
            G, _ = eval_points(ob)
            Np = vertex_normals(G[:n], Q)
            # the trousers clear his torso and legs, not his arms and hands: a hand resting on the hip is not cloth's
            # to clear
            bv, bt = eval_points(him.body_ob)
            bvh = BVHTree.FromPolygons(bv.tolist(), (bt if arms else bt[him.armw[bt].max(1) < 0.5]).tolist())
            for i in range(n):
                if skip is not None and skip[i]:
                    continue
                p = Vector(G[n + i])
                loc, nor, fi, dist = bvh.find_nearest(p, gap + 2.5)
                if loc is None or Vector(Np[i]).dot(nor) < -0.3:
                    continue
                sd = dist if (p - loc).dot(nor) >= 0 else -dist
                if sd < gap:
                    need[i] = max(need[i], gap - sd)
        reset_pose(him.arm)
        hit = int((need > 0).sum())
        # spread a plateau round each spot, then soften its edge
        sp = need.copy()
        for _ in range(6):
            sp = np.maximum(need, lap.avg(sp) * 0.97)
        for _ in range(4):
            sp = 0.5 * sp + 0.5 * lap.avg(sp)
        sp = np.maximum(sp, need)
        if skip is not None:
            sp[skip] = 0.0
        _, Nb = surf.signed(X[n:2 * n], maxd=6.0)        # away from him, at rest
        Nb = np.where((np.abs(Nb).sum(1) > 0)[:, None], Nb, vertex_normals(X[:n], Q))
        Nb = lap.avg(Nb)
        Nb /= np.maximum(np.linalg.norm(Nb, axis=1)[:, None], 1e-9)
        X += (sp[:, None] * Nb)[src]
        me.vertices.foreach_set("co", (X * 0.01).ravel())
        me.update()
        log(f"clearance {ob.name} pass {it}: {hit} verts under {gap} cm, pushed up to {need.max():.2f} cm")
    X = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", X)
    X = X.reshape(-1, 3) * 100.0
    d, nb = surf.signed(X[n:2 * n], maxd=6.0)
    short = np.where(d < gap * 0.5, gap * 0.5 - d, 0.0)
    if skip is not None:
        short[skip] = 0.0
    X += (short[:, None] * nb)[src]
    me.vertices.foreach_set("co", (X * 0.01).ravel())
    me.update()
    log(f"clearance {ob.name} at rest: {int((short > 0).sum())} verts set off to {gap * 0.5} cm")
    reset_pose(him.arm)


def prepare_export_armature(him, garments):
    """(agent-02's recipe.) The armature object as Unreal's skeleton root: unparented, scale applied, named 'root';
    then the armature and the garments in centimetres (scene unit 0.01, everything x100 and applied), as his body's FBX is. Exported in
    metres, the root carried x100 over bones in metres: the garment matched her at rest and shrank to nothing as soon
    as leader pose moved it."""
    arm = him.arm
    mw = arm.matrix_world.copy()
    arm.parent = None
    arm.matrix_world = mw
    for o in bpy.context.scene.objects:
        o.select_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    arm.name = "root"
    parented = [g for g in garments if g.parent == arm]
    for g in garments:
        gw = g.matrix_world.copy()
        g.parent = None
        g.matrix_world = gw
    for o in [arm] + list(garments):
        o.matrix_world = Matrix.Scale(100.0, 4) @ o.matrix_world
        o.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
    for g in parented:
        g.parent = arm
        g.matrix_parent_inverse = arm.matrix_world.inverted()
    us = bpy.context.scene.unit_settings
    us.system, us.scale_length = "METRIC", 0.01


def export_skeletal(him, ob, path):
    arm = him.arm
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

def body_object(him):
    return him.body_ob


def materials():
    return {
        "M_Trousers": S.material("M_Trousers", (0.034, 0.035, 0.039), 0.8),
    }


TEE, TR = (0.06, 0.065, 0.075), (0.16, 0.165, 0.18)   # preview colours: the dark tee, the charcoal trousers (lifted)


def main():
    a = ARGS
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    him = Him(a.src)
    marks = Marks(him)
    rep = marks.report()
    if a.stage == "measure":
        rep["tee_clearance"] = tee_clearance(him, marks)
        snapshot(os.path.join(a.out, f"{NAME}_body"), {him.body_ob: SKIN, him.garment_ob: (0.85, 0.85, 0.85)}, VIEWS,
                 ortho=2.0, centre=(0, 0, 0.92))
        with open(os.path.join(a.out, f"{NAME}_measure.json"), "w") as f:
            json.dump(rep, f, indent=1)
        return
    M = materials()
    surf = Surf(him)
    body = Body(him)
    z_w = float(him.bone["pelvis"][2]) + TROUSERS["waist_above_pelvis"]
    tr = build_trousers(him, marks, body, z_w)
    T = assemble_trousers(tr, him, marks, surf, body)
    Vd, sharp, btn = trousers_detail(T, tr, marks)
    Vd = pull_in_tee(Vd, body.tee_surf, TROUSERS["tee_gap"], Vd[:, 2] > marks.hem_at(Vd) + 0.2)   # after the detail
    Xt, Ft, UVt, srct, matt = finish_trousers(T, Vd, tr, btn)
    side = np.zeros(len(Vd))
    for k, I in T["idx"].items():
        side[I.ravel()] = 1 if k[0] == "L" else -1
    Wtr, groups = skin_trousers(him, marks, Vd, T["lap"], side)
    ob_tr = make_skinned(him, "his_trousers", Xt, Ft, UVt, [M["M_Trousers"]], matt, Wtr, srct,
                         groups, sharp=sharp if TROUSERS["crease_h"] > 0.15 else None)
    n = len(Vd)
    under_tee = np.where(Vd[:, 2] > marks.hem_at(Vd) + 0.5)[0]
    skip = Vd[:, 2] > marks.hem_at(Vd) - 1.0
    garments = [ob_tr]
    cols = {ob_tr: TR, him.tee_ob: TEE, him.body_vis: SKIN}
    if a.tag == "rays":   # debug: what the front and back rays hit first round the waist
        for o in bpy.context.scene.objects:
            o.hide_viewport = o not in cols
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        for z in np.arange(95.0, 108.0, 0.5):
            row = []
            for y0, dy in ((-60.0, 1.0), (60.0, -1.0)):
                hit, loc, nor, idx, ob, _ = bpy.context.scene.ray_cast(dg, Vector((0.05, y0 * 0.01, z * 0.01)),
                                                                        Vector((0, dy, 0)))
                row.append(f"{ob.name if hit else '-'}@{loc.y * 100:.2f}" if hit else "-")
            log(f"ray z {z:.1f}: front {row[0]}  back {row[1]}")
        return
    rep["trousers"] = {"verts": len(Xt), "tris": int(sum(len(f) - 2 for f in Ft)), "z_waist_edge": round(z_w, 1),
                       "z_hem": round(tr["z_hem"], 1), "z_crotch": round(tr["z_apex"], 1)}
    snapshot(os.path.join(a.out, f"{NAME}_tr{a.tag}"), cols, VIEWS, centre=(0, 0, 0.8), ortho=1.75)
    snapshot(os.path.join(a.out, f"{NAME}_trc{a.tag}"), cols, (("front", (0, 1, 0)), ("q", (0.62, 1, -0.2)),
             ("low", (0.3, 1, 0.6)), ("back", (0, -1, 0))), centre=(0, 0, 0.98), ortho=0.5, res=(1000, 1000))
    snapshot(os.path.join(a.out, f"{NAME}_legs{a.tag}"), cols, (("front", (0, 1, 0)), ("q", (0.62, 1, -0.1)),
             ("side", (-1, 0, 0)), ("back", (0, -1, 0))), centre=(0, 0, 0.3), ortho=0.7, res=(1000, 1000))
    anims = load_anims(a) if not (a.no_bake and a.no_tests) else []
    if not a.no_bake:
        bake_clearance(him, ob_tr, n, T["F"], T["lap"], srct, a, surf, anims, gap=0.3, arms=False, skip=skip)
    if not a.no_tests:
        res = {"poses": pose_tests(him, garments, a, cols, under_tee),
               "anims": idle_test(him, garments, a, cols, anims, under_tee)}
        with open(os.path.join(a.out, f"{NAME}_tests.json"), "w") as f:
            json.dump(res, f, indent=1, default=str)
    prepare_export_armature(him, [ob_tr])
    export_skeletal(him, ob_tr, os.path.join(a.out, "his_trousers.fbx"))
    with open(os.path.join(a.out, f"{NAME}_marks.json"), "w") as f:
        json.dump(rep, f, indent=1)
    log(f"done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
