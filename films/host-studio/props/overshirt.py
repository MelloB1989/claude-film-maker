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
HEM_Z = 95.0                   # hem height at the centre front/back: cropped, at the high hip
HEM_RISE = 1.5                 # the shirttail: the hem is this much higher at the side seams
TAPER = {"front": 0.10, "side": 0.30, "back": 0.16}   # how much a slice may narrow per cm going down
EASE_TOP, EASE_CHEST, EASE_LOW = 0.6, 1.1, 1.4        # ease on the shoulders, the chest, the waist/hips
EASE_BACK = 0.3                                         # extra at the back (room to reach forward)
ARM_EASE_UP, ARM_EASE_ELBOW, ARM_EASE_END = 1.0, 1.3, 0.6
SMOOTH_K = 3.0                 # the underarm's smooth union
SLEEVE_END = 5.0               # the sleeve's (rolled) end: this far down the forearm from the elbow
NECK_R = {"back": 6.0, "side": 6.9, "front": 8.0}   # neckline: horizontal radius round the neck's axis
FRONT_GAP = ((141.0, 5.0), (125.0, 6.5), (110.0, 7.5), (94.0, 8.5))  # (z, half-gap between the open fronts)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog=NAME)
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--src", default=os.path.join(here, "out", "overshirt_ue"))
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument("--stage", default="all", help="envelope | sim | detail | all")
    ap.add_argument("--body", default="SKM_Presenter_F_BodyMesh.fbx")
    ap.add_argument("--under", default="Presenter_F_Outfits.fbx", help="comma-separated FBXs worn under it")
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
    """Her reference A-pose: the armature, her body, what she wears under the overshirt, the neck.

    `under` lists the FBXs of the layer under the overshirt (each on her skeleton): by default MetaHuman's tee and
    shorts; with her own fitted top and trousers, those. Their faces' material index tells the torso (0) from the
    hips (1): a single-material file takes its position in the list."""

    def __init__(self, src, body="SKM_Presenter_F_BodyMesh.fbx", under=("Presenter_F_Outfits.fbx",)):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        body_objs = import_fbx(os.path.join(src, body))
        self.arm = next(o for o in body_objs if o.type == "ARMATURE")
        self.body_ob = next(o for o in body_objs if o.type == "MESH")
        self.under_obs = []
        xs, ts, tms, ws, off = [], [], [], {}, 0
        for k, f in enumerate(under):
            objs = import_fbx(f if os.path.isabs(f) else os.path.join(src, f))
            for ob in (o for o in objs if o.type == "MESH"):
                self.under_obs.append(ob)
                X, T, TM, W = mesh_arrays(ob)
                if len(ob.data.materials) <= 1:
                    TM = np.full(len(T), min(k, 1))
                xs.append(X)
                ts.append(T + off)
                tms.append(TM)
                for g, a in W.items():
                    ws.setdefault(g, [])
                    ws[g].append((off, a))
                off += len(X)
        self.ox, self.ot, self.otm = np.concatenate(xs), np.concatenate(ts), np.concatenate(tms)
        self.ow = {}
        for g, parts in ws.items():
            full = np.zeros(off)
            for o, a in parts:
                full[o:o + len(a)] = a
            self.ow[g] = full
        self.outfit_ob = self.under_obs[0]
        self.face_ob = None
        fp = os.path.join(src, "face.fbx")
        if os.path.exists(fp):
            fo = import_fbx(fp)
            self.face_ob = next((o for o in fo if o.type == "MESH"), None)
        self.bone = {b.name: np.array((self.arm.matrix_world @ b.head_local)[:]) * 100.0 for b in self.arm.data.bones}
        self.bx, self.bt, self.btm, self.bw = mesh_arrays(self.body_ob)
        if self.face_ob is not None:
            fx, ft, _, _ = mesh_arrays(self.face_ob)
            self.fx, self.ft = fx, ft
        log("body verts", len(self.bx), "under verts", len(self.ox), "face", self.face_ob is not None)

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
        return [o for o in (*self.under_obs, self.body_ob, self.face_ob) if o is not None]

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
        nb = len(her.bx)
        barm = np.maximum(her.arm_weight(her.bw, nb, 1), her.arm_weight(her.bw, nb, -1))
        P = np.concatenate([P, her.bx[(barm < 0.35) & (her.bx[:, 2] > 68.0)]])  # an uncut body adds its torso
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
    try:
        _snap_views(path, views, centre, dist, sc, cam, out)
    finally:
        for ob in objs_colors:
            for sl in ob.material_slots:
                if sl.link == "OBJECT":
                    sl.material = None
                    sl.link = "DATA"
    return out


def _snap_views(path, views, centre, dist, sc, cam, out):
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


# ================================================================ skinning, pose tests, export

def weight_source(her, sel_out, sel_body):
    """Points, triangles and per-vertex weights (n x G) of the chosen tee/body vertices, as one mesh."""
    parts = []
    for X, T, W, sel in ((her.ox, her.ot, her.ow, sel_out), (her.bx, her.bt, her.bw, sel_body)):
        keep = sel[T].all(1)
        parts.append((X, T[keep], W))
    groups = sorted({g for _, _, W in parts for g in W})
    gi = {g: i for i, g in enumerate(groups)}
    V, T, WW = [], [], []
    off = 0
    for X, Tk, W in parts:
        A = np.zeros((len(X), len(groups)), np.float32)
        for g, a in W.items():
            A[:, gi[g]] = a
        V.append(X)
        T.append(Tk + off)
        WW.append(A)
        off += len(X)
    V, T, WW = np.concatenate(V), np.concatenate(T), np.concatenate(WW)
    bvh = BVHTree.FromPolygons([Vector(p) for p in V], [tuple(map(int, t)) for t in T])
    return dict(V=V, T=T, W=WW, groups=groups, bvh=bvh)


def bary_weights(src, P, gmap, G):
    """Weights at points P (cm) from the nearest point of a weight source, interpolated over its triangle."""
    out = np.zeros((len(P), G), np.float32)
    tri = src["T"]
    cols = np.array([gmap[g] for g in src["groups"]])
    for i, p in enumerate(P):
        loc, nor, fi, dist = src["bvh"].find_nearest(Vector(p))
        if loc is None:
            continue
        t = tri[fi]
        w = RestMap._bary(np.array(loc[:]), src["V"][t])
        w = np.clip(w, 0, 1)
        w /= max(w.sum(), 1e-9)
        out[i, cols] = (src["W"][t] * w[:, None]).sum(0)
    return out


def mesh_adjacency(me, lo, hi):
    """Edge neighbour lists for vertices lo..hi of a mesh (indices relative to lo)."""
    E = np.zeros(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", E)
    E = E.reshape(-1, 2)
    E = E[(E >= lo).all(1) & (E < hi).all(1)] - lo
    n = hi - lo
    nb = [[] for _ in range(n)]
    for a, b in E:
        nb[a].append(b)
        nb[b].append(a)
    return [np.array(x, int) for x in nb]


def skin(her, ob, pat):
    """Vertex groups for the overshirt on her skeleton."""
    me = ob.data
    X = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", X)
    X = X.reshape(-1, 3) * 100.0
    ranges = json.loads(ob["pieces"])
    n_out, n_body = len(her.ox), len(her.bx)
    armw_out = [her.arm_weight(her.ow, n_out, s) for s in (1, -1)]
    body_arm = [(np.sign(her.bx[:, 0]) == s) & (np.abs(her.bx[:, 0]) > 11.0) & (her.bx[:, 2] > 90.0) for s in (1, -1)]
    full = weight_source(her, np.ones(n_out, bool), her.bx[:, 2] > 60.0)
    arm_src = [weight_source(her, armw_out[k] > 0.5, body_arm[k]) for k in range(2)]
    groups = sorted(set(full["groups"]) | set(arm_src[0]["groups"]) | set(arm_src[1]["groups"]))
    gmap = {g: i for i, g in enumerate(groups)}
    G = len(groups)
    W = np.zeros((len(X), G), np.float32)
    # the shirt's panels: from her (the sleeves from her arm only), smoothed over the cloth
    _, b0, b1 = next(r for r in ranges if r[0] == "body")
    Pb = X[b0:b1]
    ah, side = pat.armhole(Pb)
    sleeve = ah > -1.5
    blend = smoothstep(-1.5, 2.5, ah)
    Wt = bary_weights(full, Pb, gmap, G)
    Wa = np.zeros_like(Wt)
    for k, s in enumerate((1, -1)):
        m = sleeve & (side == s)
        Wa[m] = bary_weights(arm_src[k], Pb[m], gmap, G)
    Wb = Wt * (1 - blend)[:, None] + Wa * blend[:, None]
    nb = mesh_adjacency(me, b0, b1)
    for _ in range(25):
        avg = np.array([Wb[x].mean(0) if len(x) else Wb[i] for i, x in enumerate(nb)])
        Wb = 0.5 * Wb + 0.5 * avg
    W[b0:b1] = Wb
    # everything sewn on (collar, cuffs, pocket, buttons) moves with the cloth under it
    tri = []
    for poly in me.polygons:
        if b0 <= poly.vertices[0] < b1:
            v = list(poly.vertices)
            for k in range(1, len(v) - 1):
                tri.append((v[0] - b0, v[k] - b0, v[k + 1] - b0))
    shirt = dict(V=Pb, T=np.array(tri), W=Wb, groups=groups,
                 bvh=BVHTree.FromPolygons([Vector(p) for p in Pb], tri))
    for name, a0, a1 in ranges:
        if name == "body":
            continue
        W[a0:a1] = bary_weights(shirt, X[a0:a1], gmap, G)
    # at most 8 bones a vertex, normalised
    W[W < 0.005] = 0
    if G > 8:
        idx = np.argsort(-W, axis=1)[:, 8:]
        np.put_along_axis(W, idx, 0, axis=1)
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    for g in list(ob.vertex_groups):
        ob.vertex_groups.remove(g)
    used = [i for i in range(G) if W[:, i].max() > 0]
    for i in used:
        vg = ob.vertex_groups.new(name=groups[i])
        nz = np.nonzero(W[:, i])[0]
        # group equal weights to cut down the calls
        ww = np.round(W[nz, i], 4)
        for w in np.unique(ww):
            vg.add(nz[ww == w].tolist(), float(w), "REPLACE")
    log(f"skin: {len(used)} bones, max influences {(W > 0).sum(1).max()}")
    return [groups[i] for i in used]


def bind(her, ob):
    arm = her.arm
    ob.parent = arm
    ob.matrix_parent_inverse = arm.matrix_world.inverted()
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return mod


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


def clip_check(her, ob, step=4, tol=0.0):
    """Garment vertices inside her (tee, limbs) in the current pose: count and deepest (cm)."""
    V, T = [], []
    for o in (*her.under_obs, her.body_ob):
        X, Tr = eval_points(o)
        T.append(Tr + sum(len(v) for v in V))
        V.append(X)
    V, T = np.concatenate(V), np.concatenate(T)
    bvh = BVHTree.FromPolygons([Vector(p) for p in V], [tuple(map(int, t)) for t in T])
    G, _ = eval_points(ob)
    G = G[::step]
    bad, deep, where = 0, 0.0, []
    for p in G:
        loc, nor, fi, dist = bvh.find_nearest(Vector(p), 6.0)
        if loc is None:
            continue
        if (Vector(p) - loc).dot(nor) < -tol:
            bad += 1
            deep = max(deep, dist)
            where.append((p, dist))
    if where:  # where it happens, coarsely: 10 cm cells, the worst first
        cells = {}
        for p, d in where:
            k = tuple((np.floor(p / 10) * 10).astype(int))
            c = cells.setdefault(k, [0, 0.0])
            c[0] += 1
            c[1] = max(c[1], d)
        top = sorted(cells.items(), key=lambda kv: -kv[1][0])[:6]
        log("   clip cells (x,y,z cm: count, deepest): " + "; ".join(f"{k}: {v[0] * step}, {v[1]:.1f}" for k, v in top))
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
    "raise60": [("upperarm_l", (0, 1, 0), -60), ("upperarm_r", (0, 1, 0), 60)],
    "down40": [("upperarm_l", (0, 1, 0), 40), ("upperarm_r", (0, 1, 0), -40)],
    "fwd60": [("upperarm_l", (1, 0, 0), 60), ("upperarm_r", (1, 0, 0), 60)],
    "back60": [("upperarm_l", (1, 0, 0), -45), ("upperarm_r", (1, 0, 0), -45)],
    "elbow60": [("lowerarm_l", (1, 0, 0), 60), ("lowerarm_r", (1, 0, 0), 60)],
}


def pose_tests(her, ob, args, colours):
    arm = her.arm
    for o in (*her.under_obs, her.body_ob):  # what she wears and her limbs follow the same armature
        for m in o.modifiers:
            if m.type == "ARMATURE":
                m.object = arm
    res = {}
    for name, moves in POSES.items():
        reset_pose(arm)
        for bone, ax, deg in moves:
            pose_bone_world(arm, bone, ax, deg)
        res[name] = clip_check(her, ob)
        log(f"pose {name}: {res[name][0]} verts inside her, deepest {res[name][1]:.2f} cm")
        snapshot(os.path.join(args.out, f"overshirt_pose_{name}"), {ob: (0.33, 0.38, 0.22), **colours},
                 views=(("front", (0, 1, 0)), ("q", (0.6, 1, -0.25))), centre=(0, 0, 1.15), ortho=1.25,
                 res=(800, 900))
    reset_pose(arm)
    return res


def retarget(src, dst):
    """Her pose from another armature of the same skeleton, as Unreal plays an animation on her: each bone takes
    the source's local rotation on her own bone offsets (her proportions)."""
    for pb in dst.pose.bones:
        sb = src.pose.bones.get(pb.name)
        if sb is None or pb.parent is None:
            continue
        sl = (sb.parent.matrix.inverted() @ sb.matrix) if sb.parent else sb.matrix
        rl = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
        want = Matrix.Translation(rl.translation) @ sl.to_quaternion().to_matrix().to_4x4()
        pb.matrix_basis = rl.inverted() @ want


def idle_test(her, ob, args, colours, samples=10):
    """Play her idle (the stills' animation) retargeted onto her: clipping per sampled frame."""
    p = os.path.join(args.src, "idle.fbx")
    if not os.path.exists(p):
        return {}
    before = set(bpy.data.actions)
    objs = import_fbx(p)
    acts = [a for a in bpy.data.actions if a not in before]
    src = next((o for o in objs if o.type == "ARMATURE"), None)
    if not acts or src is None:
        return {}
    for o in objs:
        o.hide_render = True
    f0, f1 = (int(x) for x in acts[0].frame_range)
    targets = [her.arm]
    if her.face_ob is not None and her.face_ob.parent is not None and her.face_ob.parent.type == "ARMATURE":
        targets.append(her.face_ob.parent)
    res = {}
    shots = {f0 + (f1 - f0) // 3, f0 + 2 * (f1 - f0) // 3}
    frames = sorted({int(f0 + (f1 - f0) * k / (samples - 1)) for k in range(samples)} | shots)
    for f in frames:
        bpy.context.scene.frame_set(f)
        for t in targets:
            retarget(src, t)
        bpy.context.view_layer.update()
        res[f] = clip_check(her, ob)
        log(f"idle frame {f}: {res[f][0]} verts inside her, deepest {res[f][1]:.2f} cm")
        if f in shots:
            snapshot(os.path.join(args.out, f"overshirt_idle_{f}"), {ob: (0.33, 0.38, 0.22), **colours},
                     views=(("front", (0, 1, 0)), ("q", (0.6, 1, -0.25)), ("side", (-1, 0, 0))),
                     centre=(0, 0, 1.15), ortho=1.25, res=(800, 900))
            snapshot(os.path.join(args.out, f"overshirt_idleclose_{f}"), {ob: (0.33, 0.38, 0.22), **colours},
                     views=(("front", (0, 1, -0.1)), ("qr", (-0.6, 1, -0.2)), ("ql", (0.6, 1, -0.2))),
                     centre=(0, -0.05, 1.3), ortho=0.45, res=(900, 900))
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    for t in targets:
        reset_pose(t)
    return res


def export_skeletal(her, ob, path):
    """The overshirt on her skeleton, as Unreal expects it: the armature object is the skeleton's root bone."""
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
    for o in bpy.context.scene.objects:
        o.select_set(o in (arm, ob))
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"},
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", global_scale=1.0,
        axis_forward="-Y", axis_up="Z", add_leaf_bones=False, use_armature_deform_only=False,
        bake_anim=False, mesh_smooth_type="FACE", use_mesh_modifiers=False, use_tspace=False,
        primary_bone_axis="Y", secondary_bone_axis="X", path_mode="STRIP")
    log(f"exported {path}")


# ================================================================ detail: the pattern (rest) space

YOKE_Z = 131.0                 # the back yoke seam
ARMHOLE = (19.5, 139.0, 16.0, 119.0)   # the armhole seam: (x, z) at the shoulder top and at the underarm
SEAM_Y = 1.0                   # side seams this far behind her centre line
PLACKET_W = 2.8
HEM_W = 2.0
BUTTONS_Z = (121.0, 113.0, 105.0)
REVERS = dict(break_z=125.0, top_z=139.5, top_w=3.8, roll=0.36)  # the fronts' tops fold back from the break point
POCKET = dict(inset=0.6, top=127.0, w=10.5, h=12.2, chamfer=1.3, hem=2.2)  # inset: from the placket
THICK = 0.11                   # cotton twill
BAND = 0.13                    # extra at the folded hem and the plackets


class Pattern:
    """Seam lines and regions, as functions of a point's rest (envelope) position."""

    def __init__(self, her):
        self.her = her
        self.torso = Torso(her)
        self.arms = [ArmTube(her, 1), ArmTube(her, -1)]
        x0, z0, x1, z1 = ARMHOLE
        d = np.array((x0 - x1, 0.0, z0 - z1))
        n = np.array((d[2], 0.0, -d[0]))
        self.ah_n = n / np.linalg.norm(n)          # for her left arm; mirrored for the right
        self.ah_p = np.array((x0, 0.0, z0))

    def armhole(self, R):
        """Signed distance past the armhole seam (> 0 on the sleeve), and which side."""
        side = np.where(R[:, 0] >= 0, 1.0, -1.0)
        Q = R.copy()
        Q[:, 0] *= side
        phi = (Q - self.ah_p) @ self.ah_n
        near = np.zeros(len(R), bool)
        for a in self.arms:
            s, d = a.project(R)
            near |= (np.sign(R[:, 0]) == a.side) & (d < a.r.max() + 4.0) & (R[:, 2] > 100)
        phi = np.where(near, phi, -10.0)
        return phi, side

    def sleeve(self, R):
        phi, _ = self.armhole(R)
        return phi > 0

    def seam_y(self, z):
        return self.torso.c[1] + SEAM_Y - 2.5 * smoothstep(124, 134, z)

    def fields(self, R):
        """{name: (phi, active, kind)} for every seam line (phi ~ cm across the line)."""
        t = self.torso
        ah, side = self.armhole(R)
        sl = ah > 0
        out = {}
        # the side seams over the shoulder (the shoulder seam) and the sleeves' underarm seams
        phi_y = R[:, 1] - self.seam_y(R[:, 2])
        under = np.zeros(len(R), bool)
        for a in self.arms:
            s, d = a.project(R)
            q = R - (a.sh + np.outer(np.clip(s, 0, a.L1) / a.L1, a.el - a.sh))
            w = np.cross(a.udir, np.array((0.0, 1.0, 0.0)))
            w = w if w[2] < 0 else -w
            under |= (np.sign(R[:, 0]) == a.side) & ((q @ w) > 0)
        side_ok = (~sl & (np.abs(R[:, 0]) > 7.0)) | (sl & under)
        out["side"] = (phi_y, side_ok & (R[:, 2] > hem_z(R, t) - 1), "seam")
        out["armhole"] = (ah, (ah > -5) & (ah < 5), "seam")
        back = R[:, 1] > t.c[1] + 3.0
        out["yoke"] = (R[:, 2] - YOKE_Z, back & ~sl & (np.abs(R[:, 0]) < 22), "seam")
        # topstitching: the hem and the plackets
        e_hem = R[:, 2] - hem_z(R, t)
        out["hem"] = (e_hem - (HEM_W - 0.35), ~sl & (R[:, 2] < 100), "stitch")
        front = (R[:, 1] < t.c[1]) & ~sl
        e_pl = np.abs(R[:, 0]) - front_gap(R[:, 2])
        out["placket_in"] = (e_pl - (PLACKET_W - 0.3), front & (R[:, 2] < 142), "stitch")
        out["placket_edge"] = (e_pl - 0.45, front & (R[:, 2] < 142), "stitch")
        rd = revers_dist(R, t.c[1])
        out["revers"] = (rd - REVERS["roll"] * 1.5, rd > -2, "fold")
        band = np.zeros(len(R))
        band = np.maximum(band, np.where(~sl & (R[:, 2] < 100), 1 - smoothstep(HEM_W - 0.3, HEM_W + 0.1, e_hem), 0))
        band = np.maximum(band, np.where(front, 1 - smoothstep(PLACKET_W - 0.2, PLACKET_W + 0.2, e_pl), 0))
        return out, band

    def uv(self, R, n):
        """World-scale UV (m) at rest points R with rest normals n: grain down the body and along the sleeves."""
        uv = np.zeros((len(R), 2))
        sl = self.sleeve(R)
        ax = np.abs(n[:, 0]) > np.abs(n[:, 1])
        top = np.abs(n[:, 2]) > 0.8
        uv[:, 0] = np.where(ax, R[:, 1] * np.sign(n[:, 0]), -R[:, 0] * np.sign(n[:, 1] + 1e-9))
        uv[:, 1] = np.where(top, R[:, 1], R[:, 2])
        uv[top, 0] = R[top, 0]
        for a in self.arms:
            m = sl & (np.sign(R[:, 0]) == a.side)
            if not m.any():
                continue
            s, _ = a.project(R[m])
            b1 = np.cross(a.udir, (0, 1.0, 0))
            b1 /= np.linalg.norm(b1)
            b2 = np.cross(a.udir, b1)
            q = R[m] - a.sh
            nb1, nb2 = n[m] @ b1, n[m] @ b2
            uv[m, 0] = np.where(np.abs(nb1) > np.abs(nb2), (q @ b2) * np.sign(nb1), (q @ b1) * -np.sign(nb2))
            uv[m, 1] = -s
        return uv * 0.01


# ================================================================ detail: the cloth surface

def nbr_lists(n, F):
    nb = [set() for _ in range(n)]
    for f in F:
        k = len(f)
        for i in range(k):
            nb[f[i]].add(f[(i + 1) % k])
            nb[f[(i + 1) % k]].add(f[i])
    return [np.array(sorted(s), int) for s in nb]


def boundary_mask(n, F):
    cnt = {}
    for f in F:
        k = len(f)
        for i in range(k):
            e = (min(f[i], f[(i + 1) % k]), max(f[i], f[(i + 1) % k]))
            cnt[e] = cnt.get(e, 0) + 1
    m = np.zeros(n, bool)
    for (a, b), c in cnt.items():
        if c == 1:
            m[a] = m[b] = True
    return m


def taubin_np(X, nb, iters, fixed, lam=0.5, mu=-0.53):
    X = X.copy()
    for _ in range(iters):
        for w in (lam, mu):
            avg = np.array([X[s].mean(0) if len(s) else X[i] for i, s in enumerate(nb)])
            d = (avg - X) * w
            d[fixed] = 0
            X += d
    return X


def smooth_edges(X, X0, Q, nb, sigma=2.5, iters=3):
    """Even out the free edges (hem, fronts, neckline, sleeve ends): the drape leaves a fine ripple on them.
    The edge curves are smoothed along their length (corners kept), then the strip inside follows."""
    X = X.copy()
    for loop in boundary_loops_of(Q):
        L = np.array(loop)
        n = len(L)
        if n < 8:
            continue
        P0 = X0[L]
        a, b = np.roll(P0, 1, 0) - P0, np.roll(P0, -1, 0) - P0
        cosang = (a * b).sum(1) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-9)
        corner = cosang > -0.6          # turning more than ~50 degrees in the pattern
        # smooth each run between corners
        P = X[L]
        Ps = smooth1d(P, sigma, axis=0, wrap=True)
        if corner.any():
            w = np.ones(n)
            for c in np.where(corner)[0]:
                for k in range(-4, 5):
                    w[(c + k) % n] = min(w[(c + k) % n], abs(k) / 4.0)
            Ps = P + (Ps - P) * w[:, None]
        X[L] = Ps
    fixed = np.zeros(len(X), bool)
    for loop in boundary_loops_of(Q):
        fixed[loop] = True
    return taubin_np(X, nb, iters, fixed)


def subdivide_pair(Xr, Xs, Q):
    """One Catmull-Clark step of the rest and the draped mesh alike (same topology -> same vertex order)."""
    res = []
    for X in (Xr, Xs):
        ob = arrays_object("_sub", X, Q)
        mod = ob.modifiers.new("Sub", "SUBSURF")
        mod.levels = mod.render_levels = 1
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        V = np.array([v.co[:] for v in me.vertices]) * 100.0
        F = [list(p.vertices) for p in me.polygons]
        res.append((V, F))
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(me)
    assert len(res[0][0]) == len(res[1][0])
    return res[0][0], res[1][0], res[1][1]


def tri_split(F):
    T = []
    for f in F:
        for k in range(1, len(f) - 1):
            T.append((f[0], f[k], f[k + 1]))
    return np.array(T, int)


class RestMap:
    """Maps pattern-space (rest) points on the garment to the draped surface: a ray along +Y (front) or -Y (back)
    finds the rest face, its barycentric coordinates carry the point to the draped face."""

    def __init__(self, Rr, Rs, F):
        self.T = tri_split(F)
        self.Rr, self.Rs = Rr, Rs
        self.bvh = BVHTree.FromPolygons([Vector(p) for p in Rr], [tuple(t) for t in self.T])
        a, b, c = Rs[self.T[:, 0]], Rs[self.T[:, 1]], Rs[self.T[:, 2]]
        fn = np.cross(b - a, c - a)
        self.vn = np.zeros_like(Rs)
        for k in range(3):
            np.add.at(self.vn, self.T[:, k], fn)
        self.vn /= np.maximum(np.linalg.norm(self.vn, axis=1)[:, None], 1e-12)

    def at(self, x, z, front=True):
        o = Vector((x, -60.0 if front else 60.0, z))
        d = Vector((0, 1.0 if front else -1.0, 0))
        loc, nor, fi, dist = self.bvh.ray_cast(o, d)
        if loc is None:
            return None
        t = self.T[fi]
        A, B, C = (Vector(self.Rr[i]) for i in t)
        from mathutils.geometry import barycentric_transform
        p = barycentric_transform(loc, A, B, C, *(Vector(self.Rs[i]) for i in t))
        w = self._bary(np.array(loc[:]), self.Rr[t])
        n = (self.vn[t] * w[:, None]).sum(0)
        return np.array(p[:]), n / np.linalg.norm(n)

    @staticmethod
    def _bary(p, tri):
        a, b, c = tri
        v0, v1, v2 = b - a, c - a, p - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        v = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
        return np.array((1 - v - w, v, w))

    def frame(self, x, z, front=True, h=0.5):
        """Point, normal and the draped direction of rest +Z (up the garment) at (x, z)."""
        p = self.at(x, z, front)
        q = self.at(x, z + h, front)
        if p is None or q is None:
            return None
        up = q[0] - p[0]
        n = p[1]
        up -= n * (up @ n)
        return p[0], n, up / np.linalg.norm(up)


def refine_near(bm, rest, fields, width, passes=1):
    """Split the edges near the seam lines so the grooves have vertices to sit on."""
    for _ in range(passes):
        bm.verts.ensure_lookup_table()
        R = np.array([v[rest][:] for v in bm.verts])
        near = np.zeros(len(R), bool)
        for phi, act, kind in fields(R)[0].values():
            near |= act & (np.abs(phi) < width)
        edges = [e for e in bm.edges if near[e.verts[0].index] and near[e.verts[1].index]]
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True, smooth=0.0)
        width *= 0.6
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])


def groove(phi, kind):
    if kind == "fold":
        return 0.0 * phi
    if kind == "seam":   # the joining seam: a valley, the pressed allowance puffs on one side
        return -0.075 * np.exp(-(phi / 0.17) ** 2) + 0.035 * np.exp(-((phi - 0.55) / 0.35) ** 2)
    return -0.032 * np.exp(-(phi / 0.1) ** 2)  # topstitching


def vertex_normals_any(X, F):
    vn = np.zeros_like(X)
    for f in F:
        f = list(f)
        for k in range(1, len(f) - 1):
            a, b, c = X[f[0]], X[f[k]], X[f[k + 1]]
            n = np.cross(b - a, c - a)
            for i in (f[0], f[k], f[k + 1]):
                vn[i] += n
    return vn / np.maximum(np.linalg.norm(vn, axis=1)[:, None], 1e-12)


def solidify(X, F, thick, uvs_of, rim_round=0.9):
    """Thicken a surface (cm): the outer layer is X, the inner X - n*thick (per vertex); rounded rims on open edges.
    Returns verts, faces, per-face-corner uvs."""
    vn = vertex_normals_any(X, F)
    n = len(X)
    inner = X - vn * thick[:, None]
    verts = list(X) + list(inner)
    faces, uvs = [], []
    for f in F:
        faces.append(list(f))
        uvs.append([uvs_of(i) for i in f])
        faces.append([n + i for i in reversed(f)])
        uvs.append([uvs_of(i) for i in reversed(f)])
    edges = {}
    for fi, f in enumerate(F):
        k = len(f)
        for i in range(k):
            a, b = f[i], f[(i + 1) % k]
            key = (min(a, b), max(a, b))
            edges.setdefault(key, []).append((a, b, fi))
    bedges = [v[0] for v in edges.values() if len(v) == 1]
    bdir = np.zeros_like(X)
    for a, b, fi in bedges:
        e = X[b] - X[a]
        out = np.cross(e, vn[a] + vn[b])
        cen = X[F[fi]].mean(0)
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
            verts.append(mid + vn[v] * h * math.cos(r) + d * h * math.sin(r) * rim_round * 1.6)
        ids.append(n + v)
        rows[v] = ids
    for a, b, fi in bedges:
        ra, rb = rows[a], rows[b]
        ua, ub = uvs_of(a), uvs_of(b)
        for k in range(4):
            faces.append([rb[k], ra[k], ra[k + 1], rb[k + 1]])
            dv = thick[a] * 0.01 / 4
            uvs.append([(ub[0], ub[1] + dv * k), (ua[0], ua[1] + dv * k), (ua[0], ua[1] + dv * (k + 1)),
                        (ub[0], ub[1] + dv * (k + 1))])
    return np.array(verts), faces, uvs


class Piece:
    """A part of the garment (cm): verts, faces, per-corner uvs, material slot."""

    def __init__(self, name, V, F, UV, mat):
        self.name, self.V, self.F, self.UV, self.mat = name, np.asarray(V, float), [list(f) for f in F], UV, mat


def grid_faces(nu, nv, wrap_u=False):
    F = []
    for i in range(nu - (0 if wrap_u else 1)):
        for j in range(nv - 1):
            i2 = (i + 1) % nu
            F.append([i * nv + j, i2 * nv + j, i2 * nv + j + 1, i * nv + j + 1])
    return F


def grid_piece(name, P, mat, thick, wrap_u=False, uv=None, rim=True):
    """A (nu, nv, 3) grid surface (cm), thickened; uv (nu, nv, 2) in m (default: arc lengths)."""
    nu, nv = P.shape[:2]
    if uv is None:
        du = np.concatenate([np.zeros((1, nv)), np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=2), 0)], 0)
        dv = np.concatenate([np.zeros((nu, 1)), np.cumsum(np.linalg.norm(np.diff(P, axis=1), axis=2), 1)], 1)
        uv = np.stack([du, dv], -1) * 0.01
    X = P.reshape(-1, 3)
    UVf = uv.reshape(-1, 2)
    F = grid_faces(nu, nv, wrap_u)
    if thick is None:
        return Piece(name, X, F, [[tuple(UVf[i]) for i in f] for f in F], mat)
    t = np.full(len(X), thick) if np.isscalar(thick) else np.asarray(thick).reshape(-1)
    V, FF, UV = solidify(X, F, t, lambda i: tuple(UVf[i]))
    return Piece(name, V, FF, UV, mat)


# ================================================================ detail: collar, cuffs, pocket, buttons

def boundary_loops_of(F):
    """Ordered boundary loops (vertex lists) of a polygon mesh."""
    cnt = {}
    for f in F:
        k = len(f)
        for i in range(k):
            a, b = f[i], f[(i + 1) % k]
            cnt.setdefault((min(a, b), max(a, b)), []).append((a, b))
    nxt = {}
    for v in cnt.values():
        if len(v) == 1:
            a, b = v[0]
            nxt[a] = b
    loops, seen = [], set()
    for s0 in nxt:
        if s0 in seen:
            continue
        loop, v = [], s0
        while v not in seen and v in nxt:
            seen.add(v)
            loop.append(v)
            v = nxt[v]
        loops.append(loop)
    return loops


def neckline_chain(X, F, R, pattern):
    """The neckline's boundary, ordered from her right front edge round the back to her left front edge."""
    loop = max(boundary_loops_of(F), key=len)
    L = np.array(loop)
    rn, rmax = neck_radius(pattern.her, R[L])
    neck = (R[L, 2] > 128) & (rn < rmax + 2.0)
    # the longest cyclic run of neck vertices
    n = len(L)
    best, cur, best_end = 0, 0, -1
    for i in range(2 * n):
        if neck[i % n]:
            cur += 1
            if cur > best:
                best, best_end = cur, i
        else:
            cur = 0
    best = min(best, n)
    idx = [(best_end - best + 1 + k) % n for k in range(best)]
    chain = L[idx]
    if R[chain[0], 0] > R[chain[-1], 0]:
        chain = chain[::-1]
    return chain


def resample_curve(P, n):
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    s = np.linspace(0, cum[-1], n)
    return np.stack([np.interp(s, cum, P[:, k]) for k in range(3)], 1), cum[-1]


def collar(X, F, R, pattern, surf_bvh, neck_bvh):
    chain = neckline_chain(X, F, R, pattern)
    P = X[chain]
    log(f"collar: neckline chain {len(chain)} verts, from {P[0].round(1)} to {P[-1].round(1)}, "
        f"length {np.linalg.norm(np.diff(P, axis=0), axis=1).sum():.1f} cm")
    P = np.array(S.catmull_rom([tuple(p) for p in P[::2]] + [tuple(P[-1])], per_seg=4))
    P, length = resample_curve(P, 160)
    a, b = neck_axis(pattern.her)
    up = (b - a) / np.linalg.norm(b - a)
    nu = len(P)
    u = np.linspace(0, 1, nu)
    back = np.exp(-((u - 0.5) / 0.28) ** 2)
    end = np.minimum(u, 1 - u) * length                      # cm from the nearer collar end
    flap_len = REVERS["top_w"] + 0.5                          # the neckline's turned-back part at each end
    hs = (2.5 + 0.7 * back) * (0.6 + 0.4 * smoothstep(flap_len - 1.0, flap_len + 2.5, end))  # stand height
    point = (1 - smoothstep(0.0, 9.0, end)) ** 1.5           # 1 at the collar points
    wf = 4.1 + 3.3 * point                                   # the fall, measured from the fold
    th = 0.16
    rows = []
    NS, NF = 7, 16
    for i in range(nu):
        p = P[i]
        o = p - a - up * ((p - a) @ up)
        o /= np.linalg.norm(o)
        upi = up - 0.22 * o
        upi /= np.linalg.norm(upi)
        col = []
        base = p - upi * 0.35 - o * 0.1
        for j in range(NS):
            q = base + upi * (hs[i] + 0.35) * j / (NS - 1)
            col.append(q)
        top = col[-1]
        # keep clear of the neck
        loc, nor, _, dist = neck_bvh.find_nearest(Vector(top))
        if loc is not None:
            gap = (top - np.array(loc[:])) @ o
            if gap < 0.45:
                shift = o * (0.45 - gap)
                col = [c + shift * (k / (NS - 1)) ** 0.5 for k, c in enumerate(col)]
                top = col[-1]
        # the fold: half a turn outward
        for k in range(1, 4):
            ang = math.pi * k / 4
            col.append(top + upi * (th * 1.2) * math.sin(ang) + o * (th * 1.2) * (1 - math.cos(ang)))
        f0 = top + o * th * 2.4
        # the fall: down the stand's outside, then on over the shirt
        rest = wf[i]
        cur = f0.copy()
        d = -upi + o * 0.7 * point[i]
        d /= np.linalg.norm(d)
        step = rest / NF
        for k in range(NF):
            nxt = cur + d * step
            loc, nor, _, dist = surf_bvh.find_nearest(Vector(nxt))
            if loc is not None:
                sp = np.array(loc[:])
                sn = np.array(nor[:])
                if sn @ o < 0 and sn @ upi < 0.3:
                    sn = -sn
                lift = th * 2.4 + 0.12
                if (nxt - sp) @ sn < lift:
                    nxt = sp + sn * lift
            d = nxt - cur
            d /= np.linalg.norm(d)
            cur = nxt
            col.append(cur)
        rows.append(col)
    G = np.array(rows)
    G = relax_collar(G, NS, surf_bvh, neck_bvh, a, up, th)
    return grid_piece("collar", G, 0, th), (P, up, hs, a)


def relax_collar(G, NS, surf_bvh, neck_bvh, a, up, th, iters=40):
    """Smooth the collar as one surface (the per-column march jitters), keeping it on top of the shirt and clear of
    her neck; the stand's sewn edge stays where it is."""
    G = G.copy()
    nu, nv = G.shape[:2]
    lift = th * 2.4 + 0.12
    fall0 = NS + 3
    for it in range(iters):
        L = G.copy()
        L[1:-1] = 0.5 * G[1:-1] + 0.25 * (G[:-2] + G[2:])
        L[0] = 0.5 * G[0] + 0.5 * (2 * G[1] - G[2])         # ends: keep straight
        L[-1] = 0.5 * G[-1] + 0.5 * (2 * G[-2] - G[-3])
        M = L.copy()
        M[:, 1:-1] = 0.5 * L[:, 1:-1] + 0.25 * (L[:, :-2] + L[:, 2:])
        M[:, -1] = 0.5 * L[:, -1] + 0.5 * (2 * L[:, -2] - L[:, -3])
        M[:, 0] = G[:, 0]                                    # sewn to the neckline
        G = M
        for i in range(nu):
            for j in range(fall0, nv):
                loc, nor, _, dist = surf_bvh.find_nearest(Vector(G[i, j]))
                if loc is None:
                    continue
                sp, sn = np.array(loc[:]), np.array(nor[:])
                h = (G[i, j] - sp) @ sn
                if h < lift:
                    G[i, j] = G[i, j] + sn * (lift - h)
            for j in range(1, fall0):
                loc, nor, _, dist = neck_bvh.find_nearest(Vector(G[i, j]))
                if loc is None:
                    continue
                sp, sn = np.array(loc[:]), np.array(nor[:])
                h = (G[i, j] - sp) @ sn
                if h < 0.45:
                    G[i, j] = G[i, j] + sn * (0.45 - h)
    return G


def cuff(arm, X, sleeve_mask):
    """A rolled cuff round the sleeve's end: a fold at the end and a band up the sleeve, gripping the forearm."""
    a = arm.fdir
    c0 = arm.el + a * SLEEVE_END
    b1 = np.cross(a, (0, 1.0, 0))
    b1 /= np.linalg.norm(b1)
    b2 = np.cross(a, b1)
    NT = 64
    th = np.linspace(0, 2 * math.pi, NT, endpoint=False)
    Q = X[sleeve_mask] - c0
    t = -(Q @ a)                                              # up the sleeve from its end
    ang = np.arctan2(Q @ b2, Q @ b1)
    rad = np.hypot(Q @ b1, Q @ b2)
    W = 4.8
    rmax = np.zeros(NT)
    rend = np.zeros(NT)
    for k in range(NT):
        dth = np.angle(np.exp(1j * (ang - th[k])))
        m = np.abs(dth) < 0.2
        mb = m & (t > -0.5) & (t < W + 0.5)
        rmax[k] = rad[mb].max() if mb.any() else 0
        me = m & (t > -0.6) & (t < 0.8)
        rend[k] = np.median(rad[me]) if me.any() else 0
    rmax[rmax == 0] = rmax[rmax > 0].mean()
    rend[rend == 0] = rend[rend > 0].mean()
    rmax = smooth1d(rmax, 2.0, wrap=True)
    rend = smooth1d(rend, 2.0, wrap=True)
    rng = np.random.default_rng(7 if arm.side > 0 else 11)
    ph = rng.uniform(0, 2 * math.pi, 3)
    wob = 0.12 * np.sin(2 * th + ph[0]) + 0.07 * np.sin(3 * th + ph[1])
    rb = np.maximum(rmax, rend) + 0.3 + wob
    Wk = W + 0.35 * np.sin(th + ph[2]) + 0.15 * np.sin(2 * th + ph[0])
    T = 0.28                                                  # the band's thickness (three layers)
    prof = []                                                  # (t, r) per angle
    for k in range(NT):
        r0, r1, w = rend[k] - 0.05, rb[k], Wk[k]
        pts = [(0.9, r0 + 0.02), (0.3, r0)]
        rm, hr = (r0 + r1) / 2, (r1 - r0) / 2
        for j in range(1, 8):  # the bottom fold, round
            g = math.pi * j / 8
            pts.append((-hr * math.sin(g) * 0.9, rm - hr * math.cos(g)))
        n_band = 14
        for j in range(n_band + 1):
            tt = w * j / n_band
            bulge = 0.08 * math.sin(math.pi * tt / w) - 0.05 * math.exp(-((tt - w * 0.48) / 0.18) ** 2)
            pts.append((tt, r1 + bulge))
        for j in range(1, 6):  # the top edge, round
            g = math.pi * j / 6
            pts.append((w + (T / 2) * math.sin(g), r1 - T / 2 + (T / 2) * math.cos(g)))
        pts.append((w - 0.8, r1 - T))
        pts.append((w - 1.6, r1 - T - 0.02))
        prof.append(pts)
    G = np.zeros((NT, len(prof[0]), 3))
    for k in range(NT):
        d = math.cos(th[k]) * b1 + math.sin(th[k]) * b2
        for j, (tt, r) in enumerate(prof[k]):
            G[k, j] = c0 - a * tt + d * r
    arc = th * rb.mean()
    uv = np.zeros(G.shape[:2] + (2,))
    dv = np.concatenate([np.zeros((NT, 1)), np.cumsum(np.linalg.norm(np.diff(G, axis=1), axis=2), 1)], 1)
    uv[..., 0] = arc[:, None] * 0.01
    uv[..., 1] = dv * 0.01
    return grid_piece(f"cuff{arm.side:+d}", G, 0, None, wrap_u=True, uv=uv)


def arc_table(rmap, z, x0, x1, front=True, step=0.2):
    """Rest x against surface arc length along the rest surface at height z, from x0 towards x1."""
    xs = np.arange(x0, x1, step if x1 > x0 else -step)
    P = []
    for x in xs:
        r = rmap.bvh.ray_cast(Vector((x, -60.0 if front else 60.0, z)), Vector((0, 1.0 if front else -1.0, 0)))
        if r[0] is None:
            break
        P.append(np.array(r[0][:]))
    P = np.array(P)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    return xs[:len(P)], s


def pocket(rmap):
    """The chest patch pocket on her left front, laid out by arc length on the fabric."""
    p = POCKET
    nu, nv = 24, 28
    G = np.zeros((nu, nv, 3))
    N = np.zeros((nu, nv, 3))
    uv = np.zeros((nu, nv, 2))
    z0 = p["top"] - p["h"]
    for j in range(nv):
        z = z0 + p["h"] * j / (nv - 1)
        xa = front_gap(z) + PLACKET_W + p["inset"]
        xs, sarc = arc_table(rmap, z, xa, 40.0)
        for i in range(nu):
            u = p["w"] * i / (nu - 1)
            zz = z
            # chamfer the bottom corners
            dx = min(u, p["w"] - u)
            dz = zz - z0
            if dx + dz < p["chamfer"]:
                k = (p["chamfer"] - dx - dz) / 2
                zz += k
                u += k if u < p["w"] / 2 else -k
            x = float(np.interp(u, sarc, xs))
            G[i, j], N[i, j] = rmap.at(x, zz, True)
            uv[i, j] = (u * 0.01, zz * 0.01)
    zz = uv[..., 1] * 100
    thick = np.where(zz > p["top"] - p["hem"], 0.24, 0.12)
    G = G + N * (thick + 0.06)[..., None]
    return grid_piece("pocket", G, 0, thick, uv=uv)


def button_mesh(p, n, up, scale=1.0):
    """A four-hole shirt button (dark horn) on the surface at p, facing n, with its tonal thread cross."""
    n = n / np.linalg.norm(n)
    upv = up - n * (up @ n)
    upv /= np.linalg.norm(upv)
    rt = np.cross(upv, n)
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = rt, upv, n, p
    R = 0.575 * scale
    prof = [(0, 0.11), (0.18, 0.11), (0.30, 0.125), (0.40, 0.165), (0.50, 0.215), (0.555, 0.205), (0.575, 0.16),
            (0.565, 0.05), (0.53, 0.0), (0, 0.0)]
    prof = [(r * scale, z * scale) for r, z in prof]
    segs = 28
    V, F = [], []
    rings = []
    for r, z in prof:
        if r < 1e-9:
            rings.append([len(V)])
            V.append((0, 0, z))
        else:
            ring = []
            for k in range(segs):
                g = 2 * math.pi * k / segs
                ring.append(len(V))
                V.append((r * math.cos(g), r * math.sin(g), z))
            rings.append(ring)
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(A) == 1:
                F.append([A[0], B[k2], B[k]])
            elif len(B) == 1:
                F.append([A[k], A[k2], B[0]])
            else:
                F.append([A[k], A[k2], B[k2], B[k]])
    V = np.array(V)
    Vw = (M[:3, :3] @ V.T).T + p
    # the faces were built for a +Z normal outward on the top; flip if needed later by tidy
    btn = Piece("button", Vw, [f[::-1] for f in F], None, 1)
    btn.UV = [[(Vw[i] @ rt * 0.01, Vw[i] @ upv * 0.01) for i in f] for f in btn.F]
    # thread: two short bars crossing over the holes
    th = []
    hole = 0.11 * scale
    for sgn in (1, -1):
        a = p + n * 0.125 * scale + (rt * hole + upv * hole * sgn)
        b = p + n * 0.125 * scale - (rt * hole + upv * hole * sgn)
        th.append(tube_piece("thread", [a - n * 0.02, (a + b) / 2 + n * 0.025, b - n * 0.02], 0.028 * scale, 0, segs=6))
    return [btn] + th


def tube_piece(name, pts, r, mat, segs=8):
    pts = [np.asarray(q, float) for q in pts]
    pts = [np.array(q) for q in S.catmull_rom([tuple(q) for q in pts], per_seg=4)]
    G = []
    nrm = None
    for i, q in enumerate(pts):
        t = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
        t /= np.linalg.norm(t)
        if nrm is None:
            nrm = np.cross(t, (0.3, 0.5, 0.8))
        nrm = nrm - t * (nrm @ t)
        nrm /= np.linalg.norm(nrm)
        b = np.cross(t, nrm)
        G.append([q + r * (math.cos(2 * math.pi * k / segs) * nrm + math.sin(2 * math.pi * k / segs) * b)
                  for k in range(segs)])
    G = np.array(G)
    pc = grid_piece(name, G, mat, None, wrap_u=False)
    # close the tube round its circumference
    nu, nv = G.shape[:2]
    F = list(pc.F)
    UV = list(pc.UV)
    for i in range(nu - 1):
        F.append([i * nv + nv - 1, (i + 1) * nv + nv - 1, (i + 1) * nv, i * nv])
        UV.append([(0, 0)] * 4)
    pc.F, pc.UV = F, UV
    return pc


def buttonhole(p, n, up, length=1.6, width=0.36, vertical=True):
    """A stitched buttonhole: a raised bead round a slit, on the surface at p."""
    n = n / np.linalg.norm(n)
    upv = up - n * (up @ n)
    upv /= np.linalg.norm(upv)
    rt = np.cross(upv, n)
    if not vertical:
        upv, rt = rt, -upv
    def ring(L, W, h, segs=40):
        out = []
        r = W / 2
        for k in range(segs):
            g = 2 * math.pi * k / segs
            x, y = r * math.cos(g), (L / 2 - r) * np.sign(math.sin(g)) + r * math.sin(g)
            out.append(p + rt * x + upv * y + n * h)
        return out
    rows = [ring(length + 0.06, width + 0.06, -0.02), ring(length, width, 0.035), ring(length - 0.12, width - 0.12, 0.05),
            ring(length - 0.24, 0.07, 0.02), ring(length - 0.26, 0.04, -0.06)]
    G = np.array(rows).transpose(1, 0, 2)
    return grid_piece("buttonhole", G, 0, None, wrap_u=True)


def revers_lines():
    """Per side: the break point, the unit direction of the break line and its normal towards the front edge
    (rest x, z)."""
    out = {}
    for s in (1.0, -1.0):
        B = np.array((s * front_gap(REVERS["break_z"]), REVERS["break_z"]))
        T = np.array((s * (front_gap(REVERS["top_z"]) + REVERS["top_w"]), REVERS["top_z"]))
        L = (T - B) / np.linalg.norm(T - B)
        m = np.array((-L[1], L[0]))
        if m[0] * s > 0:
            m = -m
        out[s] = (B, L, m)
    return out


def revers_dist(R, c):
    """Distance into the folding flap (> 0) from the break line, and the flap mask, per vertex."""
    d = np.full(len(R), -99.0)
    q = np.stack([R[:, 0], R[:, 2]], 1)
    for s, (B, L, m) in revers_lines().items():
        ds = (q - B) @ m
        along = (q - B) @ L
        ok = (R[:, 1] < c) & (np.sign(R[:, 0]) == s) & (along > -1.0) & (R[:, 2] > B[1] - 1.5)
        d = np.where(ok, ds, d)
    return d


def fold_revers(X, R, rmap, pattern):
    """Fold each front's top back along the break line (from the break point on the front edge up to the
    neckline) round a soft roll, so the open neck makes a V and the collar can lie on the turned-back fronts."""
    c = pattern.torso.c[1]
    X = X.copy()
    r = REVERS["roll"]
    d = revers_dist(R, c)
    lines = revers_lines()
    moved = 0
    for i in np.where(d > 0)[0]:
        s = 1.0 if R[i, 0] > 0 else -1.0
        B, L, m = lines[s]
        q = np.array((R[i, 0], R[i, 2]))
        foot = q - d[i] * m
        f = rmap.at(foot[0], foot[1], True)
        g = rmap.at(foot[0] + 0.4 * m[0], foot[1] + 0.4 * m[1], True)
        if f is None or g is None:
            continue
        p0, n0 = f
        t = g[0] - p0
        t -= n0 * (t @ n0)
        t /= np.linalg.norm(t)
        if d[i] < math.pi * r:
            ph = d[i] / r
            ctr = p0 + n0 * r
            X[i] = ctr + r * (math.sin(ph) * t - math.cos(ph) * n0)
        else:
            mq = foot - (d[i] - math.pi * r) * m
            h = rmap.at(mq[0], mq[1], True)
            if h is None:
                continue
            X[i] = h[0] + h[1] * 2 * r
        moved += 1
    log(f"revers: folded {moved} verts")
    return X


# ================================================================ detail: assemble

def detail(her, m, args):
    pat = Pattern(her)
    Xs, X0, Q = m["X"], m["X0"], m["Q"]
    nb = nbr_lists(len(Xs), Q)
    bnd = boundary_mask(len(Xs), Q)
    Xs = taubin_np(Xs, nb, 4, bnd)
    Xs = smooth_edges(Xs, X0, Q, nb)
    surf = Surf(her)
    d, nrm = surf.signed(Xs)
    lo = d < 0.35
    Xs[lo] += nrm[lo] * (0.35 - d[lo])[:, None]
    log(f"detail: pushed {lo.sum()} verts out of her (min {d.min():.2f} cm)")
    Rr, Rs, F = subdivide_pair(X0, Xs, Q)
    rmap = RestMap(Rr, Rs, F)
    # the cloth surface with its rest position as a vertex layer, refined along the seams
    bm = bmesh.new()
    rest = bm.verts.layers.float_vector.new("rest")
    vs = []
    for p, r in zip(Rs, Rr):
        v = bm.verts.new(p)
        v[rest] = r
        vs.append(v)
    for f in F:
        bm.faces.new([vs[i] for i in f])
    refine_near(bm, rest, pat.fields, 0.9, passes=2)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    X = np.array([v.co[:] for v in bm.verts])
    R = np.array([v[rest][:] for v in bm.verts])
    FF = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    X = fold_revers(X, R, rmap, pat)
    vn = vertex_normals_any(X, FF)
    fields, band = pat.fields(R)
    disp = BAND * band
    for name, (phi, act, kind) in fields.items():
        disp += np.where(act, groove(phi, kind), 0.0)
    Xo = X + vn * disp[:, None]
    # uvs from the rest shape (so the weave follows the folds)
    rn = vertex_normals_any(R, FF)
    UVv = pat.uv(R, rn)
    thick = THICK + BAND * band + np.maximum(disp - BAND * band, 0) * 0
    V, Fs, UVs = solidify(Xo, FF, thick + 0.0, lambda i: tuple(UVv[i]))
    pieces = [Piece("body", V, Fs, UVs, 0)]
    log(f"detail: body verts {len(V)} faces {len(Fs)}")
    # collar, on the shirt and clear of her neck
    sbvh = BVHTree.FromPolygons([Vector(p) for p in Xo], [tuple(f) for f in FF])
    nbvh = BVHTree.FromPolygons([Vector(p) for p in her.fx], [tuple(map(int, t)) for t in her.ft]) \
        if her.face_ob is not None else sbvh
    col, cinfo = collar(Xo, FF, R, pat, sbvh, nbvh)
    pieces.append(col)
    # cuffs
    sl = pat.sleeve(R)
    for a in pat.arms:
        pieces.append(cuff(a, Xo, sl & (np.sign(R[:, 0]) == a.side)))
    # the chest pocket (her left)
    pieces.append(pocket(rmap))
    # buttons on her left placket, buttonholes on her right
    for z in BUTTONS_Z:
        for side in (1, -1):
            x = side * (front_gap(z) + PLACKET_W / 2)
            fr = rmap.frame(x, z, True)
            if fr is None:
                continue
            p, n, up = fr
            lift = THICK * 0 + BAND + 0.02
            if side > 0:
                pieces += button_mesh(p + n * lift, n, up)
            else:
                pieces.append(buttonhole(p + n * lift, n, up))
    return pieces


def pieces_object(name, pieces, mats):
    V, F, UV, M = [], [], [], []
    off = 0
    for pc in pieces:
        V.append(pc.V)
        for f, uv in zip(pc.F, pc.UV):
            F.append([i + off for i in f])
            UV.append(uv)
            M.append(pc.mat)
        off += len(pc.V)
    V = np.concatenate(V) * 0.01
    me = bpy.data.meshes.new(name)
    me.from_pydata(V.tolist(), [], F)
    me.update()
    for mt in mats:
        me.materials.append(mt)
    me.polygons.foreach_set("material_index", np.array(M, np.int32))
    uvl = me.uv_layers.new(name="UVMap")
    flat = [c for uv in UV for c in uv]
    uvl.data.foreach_set("uv", np.array(flat, float).reshape(-1))
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ranges, off = [], 0
    for pc in pieces:
        ranges.append((pc.name, off, off + len(pc.V)))
        off += len(pc.V)
    ob["pieces"] = json.dumps(ranges)
    return ob


def garment_materials():
    olive = S.material("M_Overshirt", (0.085, 0.095, 0.05), 0.85)
    buttons = S.material("M_Buttons", (0.07, 0.05, 0.032), 0.35)
    return [olive, buttons]


def main():
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)
    her = Her(args.src, args.body, [u for u in args.under.split(",") if u])
    stages = {"envelope", "sim", "detail"} if args.stage == "all" else set(args.stage.split(","))
    env_path = os.path.join(args.out, "overshirt_env.npz")
    sim_path = os.path.join(args.out, "overshirt_sim.npz")
    colours = {o: (0.85, 0.85, 0.82) for o in her.under_obs}
    colours[her.body_ob] = (0.55, 0.42, 0.35)
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
    if "detail" in stages:
        m = load_mesh(sim_path)
        t0 = time.time()
        pieces = detail(her, m, args)
        ob = pieces_object(NAME, pieces, garment_materials())
        tidy_normals(ob)
        log(f"detail: {time.time() - t0:.0f}s  triangles {S.tri_count(ob)}")
        snapshot(os.path.join(args.out, "overshirt_det"), {ob: (0.33, 0.38, 0.22), **colours})
        snapshot(os.path.join(args.out, "overshirt_detneck"), {ob: (0.33, 0.38, 0.22), **colours},
                 views=(("front", (0, 1, 0)), ("side", (-1, 0, -0.3)), ("back", (0, -1, -0.5)), ("q", (0.6, 1, -0.6))),
                 centre=(0, 0, 1.3), ortho=0.6, res=(900, 900))
        snapshot(os.path.join(args.out, "overshirt_detclose"), {ob: (0.33, 0.38, 0.22), **colours},
                 views=(("front", (0, 1, -0.15)), ("q", (0.5, 1, -0.3))), centre=(0, -0.08, 1.33), ortho=0.36,
                 res=(1100, 1100))
        if "skin" in stages:
            pat = Pattern(her)
            skin(her, ob, pat)
            bind(her, ob)
            res = {"poses": pose_tests(her, ob, args, colours), "idle": idle_test(her, ob, args, colours)}
            json.dump(res, open(os.path.join(args.out, "overshirt_clip.json"), "w"), indent=1)
            export_skeletal(her, ob, os.path.join(args.out, NAME + ".fbx"))
        if args.tag == "dbg":
            snapshot(os.path.join(args.out, "overshirt_dbg"), {ob: (0.33, 0.38, 0.22), **colours},
                     views=(("a", (0.2, 1, 0)), ("b", (-0.3, 1, 0.1))), centre=(-0.065, -0.13, 1.19), ortho=0.07,
                     res=(900, 900))


def tidy_normals(ob):
    """Outward normals per piece (vertex order is kept: the skinning relies on it)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.shade_smooth()


if __name__ == "__main__":
    main()
