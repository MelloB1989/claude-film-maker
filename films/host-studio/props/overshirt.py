"""overshirt: her olive cotton-twill overshirt, worn open over the white tee, sleeves rolled below the elbow.

A skinned garment for the female presenter (MetaHuman "Presenter"), on her own skeleton (metahuman_base_skel), fitted
to her A-pose reference body as exported from Unreal (out/overshirt_ue/: SKM_Presenter_F_BodyMesh.fbx, whose torso is
cut away under the outfit, Presenter_F_Outfits.fbx, the tee and shorts she wears, and face.fbx for the neck).

Run headless (on the Mac, through the fleet wrapper):
    blender -b --factory-startup -P overshirt.py -- --src <dir with the UE FBXs> --out <out dir> [--stage all]

How it is made
  1. The envelope (cm, Blender frame: her left +X, her front -Y, up +Z). Her torso is sliced every cm; each slice of
     the tee (and the shorts over the hips) gives a convex hull, so the cloth bridges the bust and the small of the
     back as a shirt does. Going down, a slice may not be narrower than the one above it less a little taper, so the
     shirt falls from the bust and the shoulder blades instead of following the waist. Ease is added (little on the
     shoulders, more at the waist and back). Each arm is a tube round its bone axis, as wide as the arm (or the
     tee's sleeve) plus ease. The torso and arm volumes are joined with a smooth union (the underarm), and the
     surface is meshed (surface nets, quads) from that field.
  2. The openings are cut and their edges snapped to clean curves: a shirttail hem, the sleeve ends below the elbow,
     the neckline, and the open front (the fronts hang apart, as worn open).
  3. Blender's cloth solver drops it onto her (the tee, the arms, the neck as colliders): it settles on the
     shoulders, the sleeves slide and bunch toward the elbows, the fronts hang.
  4. Detail on the settled cloth: subdivision, seams as stitched grooves (shoulder, yoke, armholes, sides, sleeve
     underarms, hem and placket stitching), a collar with a stand, plackets, buttons (her left) and buttonholes (her
     right), a chest patch pocket (her left), rolled cuffs, thickness.
  5. Skinning: weights transferred from the tee and the body (nearest face, interpolated), smoothed, checked by
     posing the arms; exported as a skeletal mesh FBX on her skeleton.

Material slots: M_Overshirt (olive cotton twill), M_Buttons. UVs: world scale (1 UV = 1 m), the grain (V) along the
body panels' length and along each sleeve.
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

NAME = "overshirt"

# ---------------------------------------------------------------- fit (cm)
VOX = 1.0                      # envelope grid
HEM_Z = 74.5                   # hem height at the centre front/back
HEM_RISE = 2.5                 # the shirttail: the hem is this much higher at the side seams
TAPER = {"front": 0.07, "side": 0.11, "back": 0.06}   # how much a slice may narrow per cm going down
EASE_TOP, EASE_CHEST, EASE_LOW = 0.6, 1.3, 2.4        # ease on the shoulders, the chest, the waist/hips
EASE_BACK = 0.6                                         # extra at the back (room to reach forward)
ARM_EASE_UP, ARM_EASE_ELBOW, ARM_EASE_END = 1.4, 2.0, 0.9
SMOOTH_K = 3.0                 # the underarm's smooth union
SLEEVE_END = 5.0               # the sleeve's (rolled) end: this far down the forearm from the elbow
NECK_R = {"back": 6.0, "side": 6.9, "front": 8.0}   # neckline: horizontal radius round the neck's axis
FRONT_GAP = ((141.0, 5.5), (125.0, 7.5), (100.0, 8.5), (74.0, 9.5))  # (z, half-gap between the open fronts)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog=NAME)
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--src", default=os.path.join(here, "out", "overshirt_ue"))
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument("--stage", default="all", help="envelope | sim | detail | all")
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--quality", type=int, default=6)
    ap.add_argument("--mass", type=float, default=0.02)
    ap.add_argument("--tension", type=float, default=60.0)
    ap.add_argument("--bend", type=float, default=2.0)
    ap.add_argument("--selfcol", type=int, default=0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--samples", type=int, default=48)
    return ap.parse_args(argv)


def log(*a):
    print(f"[{NAME}]", *a, flush=True)


# ================================================================ her, from the FBX exports

def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def mesh_arrays(ob):
    """World-space verts (cm), triangles, per-face material, and per-vertex bone weights {group: array}."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.data
    X = np.array([(ob.matrix_world @ v.co)[:] for v in me.vertices]) * 100.0
    me.calc_loop_triangles()
    T = np.array([t.vertices[:] for t in me.loop_triangles])
    TM = np.array([me.polygons[t.polygon_index].material_index for t in me.loop_triangles])
    W = {}
    names = {g.index: g.name for g in ob.vertex_groups}
    for v in me.vertices:
        for g in v.groups:
            if g.weight > 1e-4:
                W.setdefault(names[g.group], np.zeros(len(me.vertices)))[v.index] = g.weight
    return X, T, TM, W


class Her:
    """Her reference A-pose: the armature, the tee + shorts, the limbs, the neck."""

    def __init__(self, src):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        body_objs = import_fbx(os.path.join(src, "SKM_Presenter_F_BodyMesh.fbx"))
        self.arm = next(o for o in body_objs if o.type == "ARMATURE")
        self.body_ob = next(o for o in body_objs if o.type == "MESH")
        out_objs = import_fbx(os.path.join(src, "Presenter_F_Outfits.fbx"))
        self.outfit_ob = next(o for o in out_objs if o.type == "MESH")
        self.face_ob = None
        fp = os.path.join(src, "face.fbx")
        if os.path.exists(fp):
            fo = import_fbx(fp)
            self.face_ob = next((o for o in fo if o.type == "MESH"), None)
        self.bone = {b.name: np.array((self.arm.matrix_world @ b.head_local)[:]) * 100.0 for b in self.arm.data.bones}
        self.bx, self.bt, self.btm, self.bw = mesh_arrays(self.body_ob)
        self.ox, self.ot, self.otm, self.ow = mesh_arrays(self.outfit_ob)
        if self.face_ob is not None:
            fx, ft, _, _ = mesh_arrays(self.face_ob)
            self.fx, self.ft = fx, ft
        log("body verts", len(self.bx), "outfit verts", len(self.ox), "face", self.face_ob is not None)

    def arm_weight(self, W, n, side):
        s = "_l" if side > 0 else "_r"
        w = np.zeros(n)
        for g, a in W.items():
            if g.endswith(s) and any(k in g for k in ("upperarm", "lowerarm", "hand", "index", "middle", "ring",
                                                       "pinky", "thumb", "wrist")):
                w += a
        return w

    def axis(self, side):
        s = "_l" if side > 0 else "_r"
        sh, el, wr = self.bone["upperarm" + s], self.bone["lowerarm" + s], self.bone["hand" + s]
        return sh, el, wr

    def colliders_objects(self):
        return [o for o in (self.outfit_ob, self.body_ob, self.face_ob) if o is not None]

    def colliders(self):
        """Points/triangles (cm) of what the overshirt lies on: the tee, the shorts, the arms, the neck."""
        parts = [(self.ox, self.ot), (self.bx, self.bt)]
        if self.face_ob is not None:
            parts.append((self.fx, self.ft))
        return parts


# ================================================================ the envelope

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


def polar_radius(hull, c, angles):
    """Radius of a convex polygon (containing c) along each angle."""
    R = np.zeros(len(angles))
    A = hull - c
    B = np.roll(A, -1, axis=0)
    for i, t in enumerate(angles):
        d = np.array((math.cos(t), math.sin(t)))
        # ray c + s d against each edge A + u (B - A)
        e = B - A
        den = d[0] * e[:, 1] - d[1] * e[:, 0]
        ok = np.abs(den) > 1e-9
        s = np.where(ok, (A[:, 0] * e[:, 1] - A[:, 1] * e[:, 0]) / np.where(ok, den, 1), -1)
        u = np.where(ok, (A[:, 0] * d[1] - A[:, 1] * d[0]) / np.where(ok, den, 1), -1)
        hit = ok & (s > 0) & (u >= -1e-6) & (u <= 1 + 1e-6)
        R[i] = s[hit].max() if hit.any() else 0.0
    return R


def smooth1d(a, sigma, axis=0, wrap=False):
    if sigma <= 0:
        return a
    r = int(math.ceil(sigma * 3))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    a = np.moveaxis(a, axis, 0)
    if wrap:
        pad = np.concatenate([a[-r:], a, a[:r]], 0)
    else:
        pad = np.concatenate([np.repeat(a[:1], r, 0), a, np.repeat(a[-1:], r, 0)], 0)
    out = np.zeros_like(a)
    for i, w in enumerate(k):
        out += w * pad[i:i + len(a)]
    return np.moveaxis(out, 0, axis)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


NANG = 144


class Torso:
    """Her torso as a stack of convexified, eased horizontal slices, in polar form round a vertical axis."""

    def __init__(self, her):
        n = len(her.ox)
        armw = np.maximum(her.arm_weight(her.ow, n, 1), her.arm_weight(her.ow, n, -1))
        vmat = np.zeros(n, int)
        for t, m in zip(her.ot, her.otm):
            vmat[t] = m
        shirt = (vmat == 0) & (armw < 0.35)
        shorts = (vmat == 1)
        P = her.ox[shirt | (shorts & (her.ox[:, 2] > 68.0))]
        self.c = np.array((0.0, float(np.median(her.ox[shirt, 1]))))
        z0, z1 = 66.0, float(P[:, 2].max())
        self.zs = np.arange(z0, z1 + 1e-6, 1.0)
        self.ang = np.linspace(-math.pi, math.pi, NANG, endpoint=False)
        R = np.zeros((len(self.zs), NANG))
        for i, z in enumerate(self.zs):
            band = P[np.abs(P[:, 2] - z) < 0.8][:, :2]
            if len(band) < 8:
                R[i] = R[i - 1] * 0.98 if i else 0
                continue
            R[i] = polar_radius(convex_hull_2d(band), self.c, self.ang)
        self.raw = R.copy()
        # the hang: going down, a slice may not be narrower than the one above less a little taper
        dirx, diry = np.cos(self.ang), np.sin(self.ang)
        front = smoothstep(0.2, 0.8, -diry)
        back = smoothstep(0.2, 0.8, diry)
        taper = TAPER["side"] * (1 - front - back) + TAPER["front"] * front + TAPER["back"] * back
        top_hang = 136.0  # above this (the shoulders) the slices follow her exactly
        for i in range(len(self.zs) - 2, -1, -1):
            if self.zs[i] < top_hang:
                R[i] = np.maximum(R[i], R[i + 1] - taper)
        R = smooth1d(R, 1.5, axis=1, wrap=True)
        R = smooth1d(R, 1.2, axis=0)
        # ease
        z = self.zs[:, None]
        ease = EASE_TOP + (EASE_CHEST - EASE_TOP) * (1 - smoothstep(128, 140, z))
        ease = ease + (EASE_LOW - EASE_CHEST) * (1 - smoothstep(98, 118, z))
        ease = ease + EASE_BACK * back[None] * (1 - smoothstep(125, 140, z))
        self.R = R + ease
        self.ztop = z1 + EASE_TOP
        log(f"torso: slices {len(self.zs)} z {z0:.0f}..{z1:.1f}  centre y {self.c[1]:.1f}")

    def radius(self, z, th):
        zi = np.clip((z - self.zs[0]) / 1.0, 0, len(self.zs) - 1.0001)
        i0 = np.floor(zi).astype(int)
        fz = zi - i0
        ai = ((th + math.pi) / (2 * math.pi) * NANG) % NANG
        a0 = np.floor(ai).astype(int)
        fa = ai - a0
        a1 = (a0 + 1) % NANG
        r00, r01 = self.R[i0, a0], self.R[i0, a1]
        r10, r11 = self.R[i0 + 1, a0], self.R[i0 + 1, a1]
        return (r00 * (1 - fa) + r01 * fa) * (1 - fz) + (r10 * (1 - fa) + r11 * fa) * fz

    def sdf(self, P):
        """Approximate signed distance (cm): radial outside the slice, vertical above the top."""
        dx, dy = P[:, 0] - self.c[0], P[:, 1] - self.c[1]
        r = np.hypot(dx, dy)
        th = np.arctan2(dy, dx)
        Rz = self.radius(P[:, 2], th)
        d = r - Rz
        # the top: the shoulders' upper surface (the top slices shrink inward; above the last slice it is outside)
        above = P[:, 2] - self.ztop
        d = np.maximum(d, above)
        below = self.zs[0] - P[:, 2]
        return np.maximum(d, below)


class ArmTube:
    """A sleeve's volume: a tube round her arm's axis (shoulder -> elbow -> forearm), arm (or tee sleeve) + ease."""

    def __init__(self, her, side):
        self.side = side
        sh, el, wr = her.axis(side)
        self.sh, self.el = sh, el
        fdir = (wr - el) / np.linalg.norm(wr - el)
        self.end = el + fdir * (SLEEVE_END + 9.0)  # the tube runs past the sleeve end; the end is cut later
        self.cut = el + fdir * SLEEVE_END
        self.fdir = fdir
        self.udir = (el - sh) / np.linalg.norm(el - sh)
        self.L1 = float(np.linalg.norm(el - sh))
        self.L2 = float(np.linalg.norm(self.end - el))
        n = len(her.ox)
        armw = her.arm_weight(her.ow, n, side)
        pts = [her.ox[armw > 0.5]]
        bsel = (np.sign(her.bx[:, 0]) == side) & (np.abs(her.bx[:, 0]) > 11.0) & (her.bx[:, 2] > 90.0)
        pts.append(her.bx[bsel])
        P = np.concatenate(pts)
        s, dist = self.project(P)
        self.ss = np.arange(-2.0, self.L1 + self.L2 + 0.01, 1.0)
        r = np.zeros(len(self.ss))
        for i, x in enumerate(self.ss):
            m = (np.abs(s - x) < 1.0) & (dist < 9.0)
            r[i] = np.percentile(dist[m], 97) if m.sum() > 5 else 0.0
        r[r == 0] = r[r > 0].min() if (r > 0).any() else 4.0
        r = smooth1d(r, 1.5)
        e = (ARM_EASE_UP + (ARM_EASE_ELBOW - ARM_EASE_UP) * smoothstep(self.L1 - 12, self.L1, self.ss)
             + (ARM_EASE_END - ARM_EASE_ELBOW) * smoothstep(self.L1 + 1, self.L1 + SLEEVE_END - 1, self.ss))
        self.r = r + e
        log(f"arm {side:+d}: L1 {self.L1:.1f} L2 {self.L2:.1f}  r {self.r.min():.1f}..{self.r.max():.1f}")

    def project(self, P):
        """Arc length along the axis polyline and distance to it, for each point."""
        best_d = np.full(len(P), 1e9)
        best_s = np.zeros(len(P))
        for a, b, s0 in ((self.sh, self.el, 0.0), (self.el, self.end, self.L1)):
            ab = b - a
            L = np.linalg.norm(ab)
            t = np.clip(((P - a) @ ab) / (L * L), 0, 1)
            # the first segment extends back past the shoulder joint (the deltoid cap is rounded by the distance)
            q = a + t[:, None] * ab
            d = np.linalg.norm(P - q, axis=1)
            m = d < best_d
            best_d[m] = d[m]
            best_s[m] = s0 + t[m] * L
        return best_s, best_d

    def sdf(self, P):
        s, d = self.project(P)
        r = np.interp(s, self.ss, self.r)
        return d - r


def smin(a, b, k):
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def surface_nets(F, origin, h):
    """Quad mesh of the zero level of a sampled field F (inside < 0)."""
    nx, ny, nz = F.shape
    inside = F < 0
    cell_sum = np.zeros((nx - 1, ny - 1, nz - 1, 3))
    cell_cnt = np.zeros((nx - 1, ny - 1, nz - 1))
    gi = np.stack(np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij"), -1).astype(float)
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
        p = gi[tuple(sl0)][x].copy()
        p[:, ax] += t
        # the 4 cells around this edge
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
    V = cell_sum[act] / cell_cnt[act][:, None]
    V = origin + V * h
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
        # (o0-, o1-) -> (o0, o1-) -> (o0, o1) -> (o0-, o1): normal along +ax when o = (ax+1, ax+2) cyclic
        if (o[0] - ax) % 3 != 1:
            flip = ~flip
        q[flip] = q[flip][:, ::-1]
        quads.append(q)
    Q = np.concatenate(quads)
    Q = Q[(Q >= 0).all(1)]
    return V, Q


def envelope(her):
    torso = Torso(her)
    arms = [ArmTube(her, 1), ArmTube(her, -1)]
    lo = np.array((-48.0, -26.0, 64.0))
    hi = np.array((48.0, 26.0, 152.0))
    n = np.ceil((hi - lo) / VOX).astype(int) + 1
    g = np.stack(np.meshgrid(*[lo[i] + np.arange(n[i]) * VOX for i in range(3)], indexing="ij"), -1).reshape(-1, 3)
    t0 = time.time()
    f = torso.sdf(g)
    fa = np.minimum(arms[0].sdf(g), arms[1].sdf(g))
    F = smin(f, fa, SMOOTH_K).reshape(tuple(n))
    V, Q = surface_nets(F, lo, VOX)
    log(f"envelope: grid {tuple(n)} {time.time() - t0:.1f}s  verts {len(V)} quads {len(Q)}")
    return V, Q, torso, arms


# ================================================================ the openings

def hem_z(P, torso):
    """The shirttail: highest at the side seams."""
    th = np.arctan2(P[:, 1] - torso.c[1], P[:, 0] - torso.c[0])
    side = np.abs(np.cos(th)) ** 6
    return HEM_Z + HEM_RISE * side


def front_gap(z):
    zz, gg = zip(*sorted(FRONT_GAP))
    return np.interp(z, zz, gg)


def neck_axis(her):
    a, b = her.bone["neck_01"], her.bone["neck_02"]
    return a, b


def neck_radius(her, P):
    a, _ = neck_axis(her)
    dx, dy = P[:, 0] - a[0], P[:, 1] - a[1]
    th = np.arctan2(dy, dx)
    # back (+y), side, front (-y)
    s = np.sin(th)
    r = np.where(s > 0, NECK_R["side"] + (NECK_R["back"] - NECK_R["side"]) * s ** 2,
                 NECK_R["side"] + (NECK_R["front"] - NECK_R["side"]) * s ** 2)
    return np.hypot(dx, dy), r


def classify(P, her, torso, arms):
    """Which cut removes each point: 0 keep, 1 hem, 2 sleeve end (+x), 3 sleeve end (-x), 4 neck, 5 front gap."""
    lab = np.zeros(len(P), int)
    for k, a in enumerate(arms):
        s, d = a.project(P)
        on_arm = (s > a.L1 - 4) & (d < a.r.max() + 6)
        lab[on_arm & (s > a.L1 + SLEEVE_END)] = 2 + k
    lab[(lab == 0) & (P[:, 2] < hem_z(P, torso))] = 1
    rn, rmax = neck_radius(her, P)
    lab[(lab == 0) & (P[:, 2] > 128) & (rn < rmax)] = 4
    front = P[:, 1] < torso.c[1]
    lab[(lab == 0) & front & (np.abs(P[:, 0]) < front_gap(P[:, 2])) & (P[:, 2] < 150)] = 5
    return lab


def cut(V, Q, her, torso, arms):
    cen = V[Q].mean(1)
    lab = classify(cen, her, torso, arms)
    Q = Q[lab == 0]
    used = np.unique(Q)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    V, Q = V[used], remap[Q]
    # keep the largest connected piece
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in V]
    for q in Q:
        try:
            bm.faces.new([vs[i] for i in q])
        except ValueError:
            pass
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    seen, best = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        comp, st = [], [f]
        while st:
            x = st.pop()
            if x.index in seen:
                continue
            seen.add(x.index)
            comp.append(x)
            for e in x.edges:
                st.extend(g for g in e.link_faces if g.index not in seen)
        if len(comp) > len(best):
            best = comp
    keep = {f.index for f in best}
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
    # non-manifold verts (two sheets touching at a corner of the voxel mesh) would tear the cloth: split them off
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # outward: the normals should point away from her axis on the whole
    bm.normal_update()
    out = sum((f.normal.dot(Vector((f.calc_center_median().x, f.calc_center_median().y + 1.5, 0))) for f in bm.faces))
    if out < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    return bm


def boundary_snap(bm, her, torso, arms):
    """Move the open edges onto their clean curves, then relax the strip inside them."""
    bm.verts.ensure_lookup_table()
    bverts = [v for v in bm.verts if v.is_boundary]
    P = np.array([v.co[:] for v in bverts])
    # which cut each boundary vertex belongs to: the one whose curve it is nearest to
    cands = []
    hz = hem_z(P, torso)
    cands.append(np.abs(P[:, 2] - hz))
    for a in arms:
        s, d = a.project(P)
        dd = np.abs(s - (a.L1 + SLEEVE_END))
        dd[(d > a.r.max() + 6) | (s < a.L1 - 4)] = 1e9
        cands.append(dd)
    rn, rmax = neck_radius(her, P)
    dn = np.abs(rn - rmax)
    dn[P[:, 2] < 125] = 1e9
    cands.append(dn)
    front = P[:, 1] < torso.c[1]
    dg = np.abs(np.abs(P[:, 0]) - front_gap(P[:, 2]))
    dg[~front] = 1e9
    cands.append(dg)
    C = np.stack(cands, 1)
    which = C.argmin(1)
    for i, v in enumerate(bverts):
        p = np.array(v.co[:])
        w = which[i]
        if w == 0:
            p[2] = hz[i]
        elif w in (1, 2):
            a = arms[w - 1]
            s, _ = a.project(p[None])
            p = p + a.fdir * ((a.L1 + SLEEVE_END) - s[0])
        elif w == 3:
            c = neck_axis(her)[0]
            q = p[:2] - c[:2]
            p[:2] = c[:2] + q / max(np.linalg.norm(q), 1e-9) * rmax[i]
        elif w == 4:
            p[0] = math.copysign(front_gap(p[2]), p[0])
        v.co = p
    # corners where the front edge meets the hem / the neckline get both
    for i, v in enumerate(bverts):
        p = np.array(v.co[:])
        if which[i] in (0, 3, 4):
            if abs(p[2] - hem_z(p[None], torso)[0]) < 1.2 and p[1] < torso.c[1] and abs(abs(p[0]) - front_gap(p[2])) < 1.2:
                p[2] = hem_z(p[None], torso)[0]
                p[0] = math.copysign(front_gap(p[2]), p[0])
                v.co = p
    return which


def relax(bm, iters=20, lam=0.5, pin_boundary=True, project=None):
    """Tangential Laplacian smoothing (keeps the shape, evens the quads)."""
    bm.verts.ensure_lookup_table()
    for _ in range(iters):
        bm.normal_update()
        new = {}
        for v in bm.verts:
            if pin_boundary and v.is_boundary:
                continue
            nb = [e.other_vert(v).co for e in v.link_edges]
            if not nb:
                continue
            c = sum(nb, Vector()) / len(nb)
            d = c - v.co
            n = v.normal
            d -= n * d.dot(n)
            new[v] = v.co + d * lam
        for v, p in new.items():
            v.co = p
        if project is not None:
            project(bm)


def taubin_bm(bm, iters=10, lam=0.5, mu=-0.53):
    """Shape smoothing without shrinking (boundary kept)."""
    bm.verts.ensure_lookup_table()
    n = len(bm.verts)
    X = np.array([v.co[:] for v in bm.verts])
    nb = [np.array([e.other_vert(v).index for e in v.link_edges]) for v in bm.verts]
    fixed = np.array([v.is_boundary for v in bm.verts])
    for _ in range(iters):
        for w in (lam, mu):
            avg = np.array([X[s].mean(0) if len(s) else X[i] for i, s in enumerate(nb)])
            d = (avg - X) * w
            d[fixed] = 0
            X += d
    for v, p in zip(bm.verts, X):
        v.co = p


class Surf:
    """Closest-point queries on her (cm): the tee and shorts, the limbs, the neck."""

    def __init__(self, her):
        V, T = [], []
        for X, F in her.colliders():
            T.append(F + sum(len(v) for v in V))
            V.append(X)
        self.V, self.T = np.concatenate(V), np.concatenate(T)
        self.bvh = BVHTree.FromPolygons([Vector(p) for p in self.V], [tuple(map(int, t)) for t in self.T])

    def signed(self, P):
        """Signed distance (outside > 0, by the nearest face's normal) and the outward direction."""
        d = np.zeros(len(P))
        n = np.zeros((len(P), 3))
        for i, p in enumerate(P):
            loc, nor, _, dist = self.bvh.find_nearest(Vector(p))
            if loc is None:
                d[i] = 99
                continue
            v = Vector(p) - loc
            s = 1.0 if v.dot(nor) >= 0 else -1.0
            d[i] = s * dist
            n[i] = nor[:] if s > 0 or dist < 1e-6 else nor[:]
        return d, n


def push_out(bm, her, clear=0.6, iters=3):
    surf = getattr(her, "_surf", None) or Surf(her)
    her._surf = surf
    bm.verts.ensure_lookup_table()
    for _ in range(iters):
        X = np.array([v.co[:] for v in bm.verts])
        d, n = surf.signed(X)
        bad = d < clear
        for i in np.where(bad)[0]:
            bm.verts[i].co = Vector(X[i] + n[i] * (clear - d[i]))
        log(f"push_out: {bad.sum()} verts closer than {clear} cm (min {d.min():.2f})")
        relax(bm, iters=2)


def build_envelope(her):
    V, Q, torso, arms = envelope(her)
    bm = cut(V, Q, her, torso, arms)
    relax(bm, iters=10)
    boundary_snap(bm, her, torso, arms)
    relax(bm, iters=15)
    # boundary rows: even them along the edge
    for _ in range(6):
        for v in bm.verts:
            if not v.is_boundary:
                continue
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(nb) == 2:
                c = (nb[0].co + nb[1].co) / 2
                v.co = v.co.lerp(c, 0.3)
        relax(bm, iters=2)
    taubin_bm(bm, iters=12)
    relax(bm, iters=4)
    push_out(bm, her, clear=0.7)
    bm.normal_update()
    log(f"cut: verts {len(bm.verts)} faces {len(bm.faces)}  boundary {sum(v.is_boundary for v in bm.verts)}")
    return bm, torso, arms


# ================================================================ preview helpers

def bm_object(bm, name, mats=()):
    """An object from a bmesh in cm."""
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    me.transform(Matrix.Scale(0.01, 4))
    me.shade_smooth()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def arrays_object(name, X_cm, faces, mats=(), mat_idx=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata((np.asarray(X_cm) * 0.01).tolist(), [], [list(map(int, f)) for f in faces])
    me.update()
    for m in mats:
        me.materials.append(m)
    if mat_idx is not None:
        me.polygons.foreach_set("material_index", np.asarray(mat_idx, np.int32))
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def snapshot(path, objs_colors, views=(("front", (0, 1, 0)), ("side", (-1, 0, 0)), ("back", (0, -1, 0)),
                                         ("q", (0.6, 1, -0.25))), centre=(0, 0, 1.12), dist=3.2, ortho=1.15,
             res=(900, 1100)):
    """Quick workbench renders of the listed objects (object colour), for checking the fit."""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_cavity = True
    sh.cavity_type = "WORLD"
    sc.render.resolution_x, sc.render.resolution_y = res
    for ob in sc.objects:
        ob.hide_render = ob not in objs_colors
    for ob, col in objs_colors.items():
        m = bpy.data.materials.get(f"_snap_{ob.name}") or bpy.data.materials.new(f"_snap_{ob.name}")
        m.diffuse_color = (*col, 1.0)
        for i in range(max(1, len(ob.material_slots))):
            if i < len(ob.material_slots):
                ob.material_slots[i].link = "OBJECT"
                ob.material_slots[i].material = m
            else:
                ob.data.materials.append(m)
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


# ================================================================ the drape

def bm_arrays(bm):
    bm.verts.ensure_lookup_table()
    X = np.array([v.co[:] for v in bm.verts])
    Q = [[v.index for v in f.verts] for f in bm.faces]
    return X, Q


def make_collider(ob, outer=0.004, friction=8.0):
    mod = ob.modifiers.new("Collision", "COLLISION")
    c = ob.collision
    c.thickness_outer = outer
    c.thickness_inner = 0.004
    c.cloth_friction = friction
    c.damping = 0.6
    c.use_culling = False
    return mod


def simulate(her, X0, Q, args, pins=None):
    sc = bpy.context.scene
    ob = arrays_object("overshirt_sim", X0, Q)
    for c in her.colliders_objects():
        make_collider(c)
    if pins is not None:
        vg = ob.vertex_groups.new(name="pin")
        for i, w in enumerate(pins):
            if w > 1e-3:
                vg.add([i], float(w), "REPLACE")
    mod = ob.modifiers.new("Cloth", "CLOTH")
    st, cs = mod.settings, mod.collision_settings
    if pins is not None:
        st.vertex_group_mass = "pin"
        st.pin_stiffness = 1.0
    st.quality = args.quality
    st.mass = args.mass
    st.air_damping = 1.0
    st.bending_model = "ANGULAR"
    st.tension_stiffness = args.tension
    st.compression_stiffness = args.tension
    st.shear_stiffness = 10.0
    st.bending_stiffness = args.bend
    st.tension_damping = 5.0
    st.compression_damping = 5.0
    st.shear_damping = 5.0
    st.bending_damping = 0.5
    cs.use_collision = True
    cs.collision_quality = 4
    cs.distance_min = 0.004
    cs.use_self_collision = bool(args.selfcol)
    cs.self_distance_min = 0.003
    cs.self_friction = 5.0
    sc.frame_start = 1
    sc.frame_end = args.frames
    mod.point_cache.frame_start = 1
    mod.point_cache.frame_end = args.frames
    t0 = time.time()
    for f in range(1, args.frames + 1):
        sc.frame_set(f)
        if f % 10 == 0:
            log(f"frame {f}/{args.frames}  {time.time() - t0:.0f}s")
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    X = np.array([v.co[:] for v in ev.data.vertices]) * 100.0
    bpy.data.objects.remove(ob, do_unlink=True)
    return X


def save_mesh(path, **kw):
    np.savez(path, **{k: (np.array(v, dtype=object) if k == "Q" else v) for k, v in kw.items()})


def load_mesh(path):
    d = np.load(path, allow_pickle=True)
    return {k: (list(d[k]) if k == "Q" else d[k]) for k in d.files}


def main():
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)
    her = Her(args.src)
    stages = {"envelope", "sim", "detail"} if args.stage == "all" else set(args.stage.split(","))
    env_path = os.path.join(args.out, "overshirt_env.npz")
    sim_path = os.path.join(args.out, "overshirt_sim.npz")
    colours = {her.outfit_ob: (0.85, 0.85, 0.82), her.body_ob: (0.55, 0.42, 0.35)}
    if her.face_ob is not None:
        colours[her.face_ob] = (0.55, 0.42, 0.35)
    if "envelope" in stages:
        bm, torso, arms = build_envelope(her)
        X, Q = bm_arrays(bm)
        save_mesh(env_path, X=X, Q=Q)
        env = bm_object(bm, "envelope")
        bm.free()
        snapshot(os.path.join(args.out, "overshirt_env"), {env: (0.33, 0.38, 0.22), **colours})
        bpy.data.objects.remove(env, do_unlink=True)
    if "sim" in stages:
        m = load_mesh(env_path)
        arms = [ArmTube(her, 1), ArmTube(her, -1)]
        pins = np.zeros(len(m["X"]))
        for a in arms:  # the sleeve ends are held where the rolled cuffs will grip the forearm
            sa, da = a.project(m["X"])
            on = (sa > a.L1) & (da < a.r.max() + 5)
            pins = np.maximum(pins, np.where(on, smoothstep(a.L1 + SLEEVE_END - 4.0, a.L1 + SLEEVE_END - 1.5, sa), 0))
        X = simulate(her, m["X"], m["Q"], args, pins=pins)
        save_mesh(sim_path, X=X, Q=m["Q"], X0=m["X"])
        ob = arrays_object("sim", X, m["Q"])
        snapshot(os.path.join(args.out, "overshirt_sim" + args.tag), {ob: (0.33, 0.38, 0.22), **colours})
        snapshot(os.path.join(args.out, "overshirt_simneck" + args.tag), {ob: (0.33, 0.38, 0.22), **colours},
                 views=(("front", (0, 1, 0)), ("side", (-1, 0, -0.3)), ("back", (0, -1, -0.5)), ("q", (0.6, 1, -0.6))),
                 centre=(0, 0, 1.36), ortho=0.5, res=(900, 900))
        bpy.data.objects.remove(ob, do_unlink=True)


if __name__ == "__main__":
    main()
