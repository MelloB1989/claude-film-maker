"""her_waist_r7: her trousers at the waist, seated (round 7, agent-05): probe and refit.

    blender -b --factory-startup -P her_waist_r7.py -- --src <garment.export out_dir> --out <dir> [--frames 0,40,..]
        [--fit] [--anim anim_X.fbx]

In: garment.export's FBXs (cm, her skeleton): ref_body.fbx (uncut), garment_Top.fbx, garment_Trousers.fbx, anim_*.fbx.
Everything stays on the box (her body is presenter data).

PROBE (always): at each sampled frame of the anim, her body, Top and Trousers posed as Unreal leader-poses them (the
anim's local rotations on her own bone offsets), then 24 sectors round the pelvis -> spine_03 axis x 5 heights through
the waistband: a ray from the axis outward, its hits in order. Per sector: the band's gap (the trousers' inner face
off her skin), body or Top poking OUT through the trousers (a hit of either beyond the trousers' outer face), and
the Top's tuck (its hem still inside the band). waist.json + a per-frame table in the log.

FIT (--fit): the trousers' upper part (the band and the 12 cm under it) is re-solved in her SEATED pose, then carried
back to the bind pose by the inverse of each vertex's skinning matrix, so leader pose lands it where it was solved:
  - the band sits ON her waist: inner face BAND_CLEAR off her skin all round, at every sampled frame (the worst
    frame wins: the most compressed front, the most stretched back);
  - its weights are her body's (nearest face, interpolated, NOT smoothed over the garment), ramping back to the
    trousers' own by the hip: so the band moves with her belly and back as her skin does;
  - the Top's tuck is pulled in to TUCK_CLEAR inside the band (a tucked hem never comes out through it).
Writes garment_fit_Trousers.fbx and garment_fit_Top.fbx (same topology, UVs and slots: the materials still fit).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "..", "..", "..", "blender"))
import garment_fit as G  # noqa: E402  (import_fbx, world_cm, set_world_cm, weights_of, bind, retarget, export)
from lib import garmentfit as GF  # noqa: E402

NAME = "her_waist_r7"
SECTORS = 24
BAND_CLEAR = 0.42      # cm: the band's inner face off her skin (over the tuck: TUCK_CLEAR + the knit 0.16 + 0.14)
TUCK_CLEAR = 0.12      # cm: the Top's tucked part, its inner face off her skin (the band presses it flat)
FULL = 5.0             # cm under the band: refit fully with her ...
UPPER = 13.0           # ... ramping back to the trousers' own shape and weights by here
TOP_ABOVE = (0.3, 2.0) # cm above the waist edge: the Top's tuck refit fully below the first, its own above the second


def log(*a):
    print(f"[{NAME}]", *a, flush=True)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog=NAME)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--anim", default="", help="anim_*.fbx (default: every one)")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--frames", default="", help="comma list of frames (overrides --samples)")
    ap.add_argument("--fit", default="", choices=("", "Trousers", "Top"), help="refit this garment and export it")
    ap.add_argument("--top", default="garment_Top.fbx", help="the Top FBX in --src")
    ap.add_argument("--fit-frame", type=int, default=1, help="the seated frame the fit is solved on")
    ap.add_argument("--ue-posed", default="", help="'dir[:frame],...': dirs with Unreal's POSED body.obj / trousers.obj (+ meta.json), "
                    "world cm, UE axes: her skin as Unreal poses it (correctives included) joins the collider, and each "
                    "band vertex is measured where Unreal puts it")
    ap.add_argument("--trousers", default="garment_Trousers.fbx", help="the trousers FBX in --src (the live cut copy, "
                    "or garment_Trousers_orig.fbx: the uncut asset)")
    ap.add_argument("--band", type=float, default=4.0, help="the waistband's height, cm (her_outfit TROUSERS band)")
    return ap.parse_args(argv)


def load(path, arm=None):
    objs = G.import_fbx(path)
    ob = next(o for o in objs if o.type == "MESH")
    a = next((o for o in objs if o.type == "ARMATURE"), None)
    if arm is not None:
        G.bind(ob, arm)
        for o in objs:  # bind() already removed the FBX's own armature when it was the mesh's parent
            try:
                if o.type == "ARMATURE" and o != arm:
                    bpy.data.objects.remove(o, do_unlink=True)
            except ReferenceError:
                pass
        return ob, arm
    return ob, a


def bone_world(arm, name):
    pb = arm.pose.bones[name]
    return np.array(arm.matrix_world @ pb.head) * 100.0


class Rig:
    def __init__(self, a):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        self.body, self.arm = load(os.path.join(a.src, "ref_body.fbx"))
        self.top, _ = load(os.path.join(a.src, a.top), self.arm)
        self.tr, _ = load(os.path.join(a.src, a.trousers), self.arm)
        X, _ = G.world_cm(self.tr)
        self.z_edge = float(np.percentile(X[:, 2], 99.9))      # the waist edge in the bind pose
        self.rest_tr = X
        log(f"body {len(self.body.data.vertices)} v, Top {len(self.top.data.vertices)} v, Trousers {len(X)} v, "
            f"waist edge z {self.z_edge:.1f} cm (bind pose)")
        self.anims = []

    def anim(self, path):
        before = set(bpy.data.actions)
        objs = G.import_fbx(path)
        acts = [x for x in bpy.data.actions if x not in before]
        src = next((o for o in objs if o.type == "ARMATURE"), None)
        for o in objs:
            if o.type == "MESH":
                bpy.data.objects.remove(o, do_unlink=True)
        f0, f1 = (int(x) for x in acts[0].frame_range)
        return src, f0, f1

    def pose(self, src, f):
        bpy.context.scene.frame_set(f)
        if src is None:
            for pb in self.arm.pose.bones:
                pb.matrix_basis = Matrix.Identity(4)
        else:
            G.retarget(src, self.arm)
        bpy.context.view_layer.update()

    def posed(self):
        return {k: G.world_cm(o, evaluated=True) for k, o in (("body", self.body), ("top", self.top), ("tr", self.tr))}


def axis(arm):
    p = bone_world(arm, "pelvis")
    s = bone_world(arm, "spine_03")
    u = (s - p) / np.linalg.norm(s - p)
    # her front: -Y of the pelvis bone's frame, as posed (the bind frame: front -Y)
    M = np.array((arm.matrix_world @ arm.pose.bones["pelvis"].matrix).to_3x3())
    f = M @ np.array((0.0, -1.0, 0.0))
    f = f - (f @ u) * u
    f /= np.linalg.norm(f)
    return p, u, f, np.cross(u, f)


def hits_along(bvh, o, d, far=40.0):
    """Every hit of a ray, nearest first, as distances (both faces of a thick shell)."""
    out, start, left = [], Vector(o), far
    dv = Vector(d)
    while left > 0:
        loc, nor, fi, dist = bvh.ray_cast(start, dv, left)
        if loc is None:
            break
        t = (np.array(loc[:]) - o) @ d
        out.append(float(t))
        start = loc + dv * 0.002
        left = far - float(t) - 0.002
    return out


def probe(rig, a, src, frames, z_band_lo, z_edge_bind):
    """Per frame and sector at 5 heights through the band: gap, pokes, tuck."""
    rows = []
    for f in frames:
        rig.pose(src, f)
        P = rig.posed()
        bv = {k: BVHTree.FromPolygons(X.tolist(), T.tolist()) for k, (X, T) in P.items()}
        p, u, fr, side = axis(rig.arm)
        log(f"f{f} pose: pelvis {np.round(bone_world(rig.arm, 'pelvis'), 1).tolist()}, knee_l "
            f"{np.round(bone_world(rig.arm, 'calf_l'), 1).tolist()}, axis {np.round(u, 2).tolist()}")
        # the band's heights along the axis, from the bind-pose waist edge: the pelvis keeps its offset to the band
        p0 = np.array(rig.arm.matrix_world @ rig.arm.data.bones["pelvis"].head_local) * 100.0
        h_edge = z_edge_bind - p0[2]
        hs = [h_edge - 0.4, h_edge - a.band * 0.35, h_edge - a.band * 0.7, h_edge - a.band - 1.0,
              h_edge - a.band - 3.0]
        fr_rows = []
        for k in range(SECTORS):
            th = 2 * math.pi * k / SECTORS        # 0 = front, +90 deg = her left
            d = math.cos(th) * fr + math.sin(th) * side
            for j, h in enumerate(hs):
                o = p + u * h
                hb = hits_along(bv["body"], o, d)
                ht = hits_along(bv["tr"], o, d)
                hp = hits_along(bv["top"], o, d)
                # first crossings only: the ray starts inside her, so her skin is its first body hit, the
                # trousers' first two hits are its inner and outer face (an arm or a sleeve further out is not a poke)
                rb = hb[0] if hb else None
                tr_in, tr_out = (ht[0], ht[1]) if len(ht) >= 2 else (ht[0], ht[0]) if ht else (None, None)
                top_out = (hp[1] if len(hp) >= 2 else hp[0]) if hp else None
                row = {"f": f, "s": k, "j": j, "body": rb, "tr_in": tr_in, "tr_out": tr_out, "top": top_out}
                if rb is not None and tr_in is not None:
                    row["gap"] = round(tr_in - rb, 2)
                    row["body_poke"] = round(max(0.0, rb - tr_out), 2)
                if top_out is not None and tr_out is not None:
                    row["top_poke"] = round(max(0.0, top_out - tr_out), 2)
                if tr_in is None and j < 3:
                    row["band_missing"] = 1
                fr_rows.append(row)
        rows += fr_rows
        summarise(f, fr_rows)
    return rows


def summarise(f, rows):
    band = [r for r in rows if r["j"] <= 2]
    gaps = [r["gap"] for r in band if "gap" in r]
    bp = [r["body_poke"] for r in rows if r.get("body_poke", 0) > 0.05]
    tp = [r["top_poke"] for r in rows if r.get("top_poke", 0) > 0.05]
    miss = sum(r.get("band_missing", 0) for r in band)
    miss_at = sorted({(r["s"], r["j"]) for r in band if r.get("band_missing")})

    def sect(name, ks):
        g = [r["gap"] for r in band if "gap" in r and r["s"] in ks]
        return f"{name} gap {min(g):+.2f}..{max(g):+.2f}" if g else f"{name} -"
    q = SECTORS // 4
    front = {(SECTORS - 2) % SECTORS, SECTORS - 1, 0, 1, 2}
    back = {2 * q - 2, 2 * q - 1, 2 * q, 2 * q + 1, 2 * q + 2}
    left = {q - 1, q, q + 1}
    right = {3 * q - 1, 3 * q, 3 * q + 1}
    log(f"f{f}: band gap median {np.median(gaps) if gaps else float('nan'):.2f} (min {min(gaps) if gaps else 0:.2f}, "
        f"max {max(gaps) if gaps else 0:.2f}); {sect('front', front)}; {sect('back', back)}; {sect('L', left)}; "
        f"{sect('R', right)}; body pokes {len(bp)} (max {max(bp) if bp else 0:.2f}); Top pokes {len(tp)} "
        f"(max {max(tp) if tp else 0:.2f}); band rays missing {miss} {miss_at}")


# ------------------------------------------------------------------------------------------------------------- fit
def set_weights(ob, W, groups):
    for g in list(ob.vertex_groups):
        ob.vertex_groups.remove(g)
    for gi, name in enumerate(groups):
        nz = np.nonzero(W[:, gi])[0]
        if not len(nz):
            continue
        vg = ob.vertex_groups.new(name=name)
        for i in nz:
            vg.add([int(i)], float(W[i, gi]), "REPLACE")


def body_weights_at(rig, ob):
    """Her body's weights at the garment's verts (Data Transfer, nearest face interpolated, bind pose), unsmoothed."""
    tmp = ob.copy()
    tmp.data = ob.data.copy()
    bpy.context.scene.collection.objects.link(tmp)
    for m in list(tmp.modifiers):
        tmp.modifiers.remove(m)
    for g in list(tmp.vertex_groups):
        tmp.vertex_groups.remove(g)
    for g in rig.body.vertex_groups:
        tmp.vertex_groups.new(name=g.name)
    m = tmp.modifiers.new("W", "DATA_TRANSFER")
    m.object = rig.body
    m.use_vert_data = True
    m.data_types_verts = {"VGROUP_WEIGHTS"}
    m.vert_mapping = "POLYINTERP_NEAREST"
    m.layers_vgroup_select_src = "ALL"
    m.layers_vgroup_select_dst = "NAME"
    bpy.context.view_layer.objects.active = tmp
    for o in bpy.context.scene.objects:
        o.select_set(o == tmp)
    bpy.ops.object.modifier_apply(modifier=m.name)
    W, groups = G.weights_of(tmp)
    bpy.data.objects.remove(tmp, do_unlink=True)
    return W, groups


def skin_mats(arm, groups):
    """Per bone: the 3x3 of its skinning transform (posed world x inverse bind world), for the inverse skin."""
    out = np.zeros((len(groups), 3, 3))
    mw = arm.matrix_world
    for i, g in enumerate(groups):
        pb = arm.pose.bones.get(g)
        if pb is None:
            out[i] = np.eye(3)
            continue
        M = mw @ pb.matrix @ pb.bone.matrix_local.inverted() @ mw.inverted()
        out[i] = np.array(M.to_3x3())
    return out


def read_obj(path):
    """(verts, triangles) of an OBJ (v / f lines; f may carry /vt/vn; polygons fanned)."""
    V, F = [], []
    with open(path) as fh:
        for ln in fh:
            if ln.startswith("v "):
                V.append([float(x) for x in ln.split()[1:4]])
            elif ln.startswith("f "):
                ix = [int(t.split("/")[0]) for t in ln.split()[1:]]
                ix = [i - 1 if i > 0 else len(V) + i for i in ix]
                for k in range(1, len(ix) - 1):
                    F.append((ix[0], ix[k], ix[k + 1]))
    return np.array(V, float), np.array(F, np.int64)


def rigid(A, B, reflect=True):
    """R, t with R @ A_i + t ~ B_i (least squares; a reflection allowed: Unreal's frame is left-handed)."""
    ca, cb = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    R = (U @ Vt).T
    if not reflect and np.linalg.det(R) < 0:
        Vt[-1] *= -1
        R = (U @ Vt).T
    return R, cb - R @ ca


class UEPosed:
    """Unreal's posed meshes brought into the rig's posed frame: first by her bones (meta.json), then ICP of Unreal's
    trousers onto the rig's posed trousers (the same garment, so what is left is the pose's own difference)."""

    def __init__(self, d, rig, P_tr):
        meta = json.load(open(os.path.join(d, "meta.json")))
        bones = meta.get("bones") or meta
        names = [b for b in ("pelvis", "spine_01", "spine_02", "spine_03", "thigh_l", "thigh_r", "calf_l", "calf_r")
                 if b in bones and b in rig.arm.pose.bones]
        A = np.array([bones[b] for b in names], float)
        B = np.array([bone_world(rig.arm, b) for b in names])
        R, t = rigid(A, B)
        log(f"ue-posed: bones {names}: fit residual {np.linalg.norm((A @ R.T + t) - B, axis=1).round(2).tolist()} cm, "
            f"det {np.linalg.det(R):+.0f}")
        self.body = read_obj(os.path.join(d, "body.obj"))
        self.tr = read_obj(os.path.join(d, "trousers.obj"))
        TX = self.tr[0]
        for it in range(6):
            Y = TX @ R.T + t
            kd = KDTree(len(Y))
            for k, y in enumerate(Y):
                kd.insert(Vector(y), k)
            kd.balance()
            sub = P_tr[::7]
            pairs = []
            for p in sub:
                _, k, dist = kd.find(Vector(p))
                if dist < 3.0:
                    pairs.append((k, p))
            if len(pairs) < 100:
                raise SystemExit(f"ue-posed: only {len(pairs)} trousers matches after the bone alignment")
            Ak = TX[[k for k, _ in pairs]]
            Bp = np.array([p for _, p in pairs])
            R, t = rigid(Ak, Bp)
            res = np.linalg.norm(Ak @ R.T + t - Bp, axis=1)
            log(f"ue-posed ICP {it + 1}: {len(pairs)} pairs, residual median {np.median(res):.2f} p95 "
                f"{np.percentile(res, 95):.2f} cm")
        self.R, self.t = R, t
        BX = self.body[0] @ R.T + t
        self.bvh_body = BVHTree.FromPolygons(BX.tolist(), self.body[1].tolist())
        TY = TX @ R.T + t
        self.bvh_tr = BVHTree.FromPolygons(TY.tolist(), self.tr[1].tolist())

    def where(self, P):
        """Each rig-posed garment vertex's place on Unreal's posed trousers (nearest point), and how far it moved."""
        U = np.array(P, float)
        mv = np.zeros(len(P))
        for i, p in enumerate(P):
            loc, nor, fi, dist = self.bvh_tr.find_nearest(Vector(p))
            if loc is not None and dist < 2.0:
                U[i] = loc[:]
                mv[i] = dist
        return U, mv


def posed_list(a):
    """--ue-posed 'dir[:frame],dir[:frame]' -> [(dir, frame)]; none: [(None, --fit-frame)] (Blender's skin only)."""
    if not a.ue_posed:
        return [(None, a.fit_frame)]
    out = []
    for item in a.ue_posed.split(","):
        d, _, f = item.strip().partition(":")
        out.append((d, int(f) if f else a.fit_frame))
    return out


def fit(rig, a, src):
    """Refit a.fit (Trousers or Top) at the waist in her seated pose(s) and carry it back to the bind pose. With several
    posed frames each is solved on its own and every vertex takes the most outward of its moves (the worst frame
    wins: no poke anywhere; a pull-in only as far as every frame allows)."""
    ob = rig.tr if a.fit == "Trousers" else rig.top
    X0, T = G.world_cm(ob)
    z = X0[:, 2]
    ze = rig.z_edge
    if a.fit == "Trousers":
        top_z = ze - a.band - FULL
        alpha = np.clip((z - (ze - a.band - UPPER)) / (top_z - (ze - a.band - UPPER)), 0, 1)
        target_in = BAND_CLEAR
    else:
        alpha = 1 - np.clip((z - (ze + TOP_ABOVE[0])) / (TOP_ABOVE[1] - TOP_ABOVE[0]), 0, 1)
        target_in = TUCK_CLEAR
    alpha = alpha * alpha * (3 - 2 * alpha)
    nbrs = GF.neighbours(len(X0), T)
    zone = alpha > 1e-4
    log(f"fit {a.fit}: {int(zone.sum())} verts in the waist zone ({int((alpha > 0.999).sum())} fully)")
    # 1. weights: her body's through the zone (unsmoothed: the band moves as her skin does), its own outside
    W_own, g_own = G.weights_of(ob)
    W_b, g_b = body_weights_at(rig, ob)
    W_b = GF.limit_normalize(W_b, 8)
    W, groups = GF.blend_weights(W_b, g_b, W_own, g_own, alpha)
    set_weights(ob, W, groups)
    # the panels are separate shells along their seams: coincident verts move together (no seam opens)
    key = np.round(X0 / 0.002).astype(np.int64)
    _, grp = np.unique(key, axis=0, return_inverse=True)
    grp = grp.ravel()

    def weld(v):
        acc = np.zeros((grp.max() + 1,) + v.shape[1:])
        np.add.at(acc, grp, v)
        cnt = np.bincount(grp, minlength=grp.max() + 1).reshape((-1,) + (1,) * (v.ndim - 1))
        return (acc / cnt)[grp]
    log(f"seams: {int(len(grp) - (grp.max() + 1))} coincident verts weld in the move")
    ctx = dict(ob=ob, T=T, z=z, alpha=alpha, zone=zone, nbrs=nbrs, weld=weld, W=W, groups=groups, target_in=target_in)
    sols = [solve(rig, a, src, ctx, udir, f) for udir, f in posed_list(a)]
    # 4. the most outward move per vertex over the frames, carried to the bind pose as that frame solved it
    MV = np.stack([s_["mv"] for s_ in sols])
    pick = MV.argmax(0)
    Dr = np.stack([s_["Dr"] for s_ in sols])[pick, np.arange(len(X0))]
    Dr = weld(Dr)
    if len(sols) > 1:
        log("worst frame per vertex: " + ", ".join(f"f{s_['frame']} {int((pick[zone] == k).sum())}"
                                                   for k, s_ in enumerate(sols)))
    rig.pose(None, 0)
    G.set_world_cm(ob, X0 + Dr)
    for s_ in sols:
        if s_.get("ue") is not None:
            ue_check(rig, a, src, ob, s_)
    mag = np.linalg.norm(Dr, axis=1)
    log(f"bind-pose move median {np.median(mag[mag > 1e-5]):.2f} cm, max {mag.max():.2f}")
    return ob


def solve(rig, a, src, ctx, udir, frame):
    """One posed frame: each zone vertex's distance to her skin (Blender's, and Unreal's when given: the furthest out
    wins), the move to target_in along her skin's normal, smoothed and welded; carried to the bind pose by the inverse
    of that frame's skinning."""
    ob, T, z, alpha, zone, nbrs, weld = (ctx[k] for k in ("ob", "T", "z", "alpha", "zone", "nbrs", "weld"))
    rig.pose(src, frame)
    P, _ = G.world_cm(ob, evaluated=True)
    BX, BT = G.world_cm(rig.body, evaluated=True)
    bvhs = [BVHTree.FromPolygons(BX.tolist(), BT.tolist())]
    sol = {"frame": frame, "ue": None}
    if udir:
        ue = UEPosed(udir, rig, P)
        U, off = ue.where(P)
        log(f"f{frame} ue-posed: zone verts vs Unreal's own: moved median {np.median(off[zone]):.2f} cm, p95 "
            f"{np.percentile(off[zone], 95):.2f}, max {off[zone].max():.2f}")
        sol.update(ue=ue, off=U - P)            # Unreal's place minus the rig's, per vertex (for the after-check)
        P = U                                   # measure each vertex where Unreal puts it
        bvhs.append(ue.bvh_body)
    vn = GF.vertex_normals(P, T)
    d = np.full(len(P), np.nan)
    N = np.zeros((len(P), 3))
    src_ue = np.zeros(len(P), bool)
    for i in np.nonzero(zone)[0]:
        best = None
        for bi, bv in enumerate(bvhs):          # the skin furthest out wins (Unreal's belly over Blender's)
            loc, nor, fi, dist = bv.find_nearest(Vector(P[i]))
            if loc is None or dist > 8.0:
                continue
            n = np.array(nor[:])
            di = (P[i] - np.array(loc[:])) @ n
            if bi == 1 and abs(di) > 4.0:     # a hole of the live cut: a far surface, not her skin under the band
                continue
            if best is None or di < best[0]:
                best = (di, n, bi)
        if best is None:
            continue
        d[i], N[i], src_ue[i] = best[0], best[1], best[2] == 1
    if udir:
        log(f"f{frame} collider: Unreal's skin decides {int(src_ue[zone].sum())} of {int(zone.sum())} zone verts")
    ok = zone & np.isfinite(d)
    inner = ok & (np.einsum("ij,ij->i", vn, N) < 0)      # the shell's inner face looks at her
    outer = ok & ~inner
    mv = np.zeros(len(P))
    mv[inner] = ctx["target_in"] - d[inner]
    # the outer face moves with its nearest inner vertex (the wall keeps its thickness)
    kd = KDTree(int(inner.sum()))
    ii = np.nonzero(inner)[0]
    for k, i in enumerate(ii):
        kd.insert(Vector(P[i]), k)
    kd.balance()
    for i in np.nonzero(outer)[0]:
        _, k, _ = kd.find(Vector(P[i]))
        mv[i] = mv[ii[k]]
        N[i] = N[ii[k]]
    log(f"f{frame}: inner face off her skin median {np.median(d[inner]):.2f} cm (min {d[inner].min():.2f}, max "
        f"{d[inner].max():.2f}); move median {np.median(mv[ok]):+.2f}, {mv[ok].min():+.2f}..{mv[ok].max():+.2f}")
    # a nearest point across a fold (her seated hip crease) reads deep inside: not a clip the band can fix, left as is
    fold = ok & (d < -1.0)
    mv[fold] = 0.0
    if fold.any():
        log(f"f{frame} fold: {int(fold.sum())} zone verts read > 1 cm inside (left alone): z "
            f"{np.percentile(z[fold], 5):.1f}..{np.percentile(z[fold], 95):.1f} cm (bind), alpha median "
            f"{np.median(alpha[fold]):.2f}")
    mv = np.clip(mv, -3.0, 1.0)
    for _ in range(3):
        mv = weld(GF.smooth_field(mv, nbrs, iters=2, pinned=~zone))
        N = weld(GF.smooth_field(N, nbrs, iters=1, pinned=~zone))
    mv = mv * alpha
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    D = mv[:, None] * N
    # back to the bind pose: the inverse of each vertex's blended skinning at this frame (3x3; the move is a vector)
    S = np.einsum("vb,bij->vij", ctx["W"], skin_mats(rig.arm, ctx["groups"]))
    idx = np.nonzero(np.abs(mv) > 1e-5)[0]
    Dr = np.zeros_like(D)
    Dr[idx] = np.linalg.solve(S[idx], D[idx][:, :, None])[:, :, 0]
    sol.update(mv=mv, Dr=Dr, inner=inner)
    return sol


def ue_check(rig, a, src, ob, sol):
    """After the fit: the band where Unreal would put it (the rig's new posed band + Unreal's per-vertex offset),
    against the furthest-out skin: inner face off her skin, front half (|angle| < 90 deg) and all round."""
    rig.pose(src, sol["frame"])
    P2, _ = G.world_cm(ob, evaluated=True)
    U2 = P2 + sol["off"]
    BX, BT = G.world_cm(rig.body, evaluated=True)
    bvhs = [BVHTree.FromPolygons(BX.tolist(), BT.tolist()), sol["ue"].bvh_body]
    p, u, fr, side = axis(rig.arm)
    X0, _ = G.world_cm(ob)
    band = sol["inner"] & (X0[:, 2] > rig.z_edge - a.band - 0.5)
    dd, front = [], []
    for i in np.nonzero(band)[0]:
        best = None
        for bi, bv in enumerate(bvhs):
            loc, nor, fi, dist = bv.find_nearest(Vector(U2[i]))
            if loc is None or dist > 8.0:
                continue
            di = (U2[i] - np.array(loc[:])) @ np.array(nor[:])
            if bi == 1 and abs(di) > 4.0:
                continue
            best = di if best is None else min(best, di)
        if best is None:
            continue
        r = U2[i] - p
        dd.append(best)
        front.append((r @ fr) > 0)
    dd, front = np.array(dd), np.array(front)
    for name, m in (("front half", front), ("all round", np.ones(len(dd), bool))):
        x = dd[m]
        log(f"ue-check f{sol['frame']} {name}: band inner face off her skin median {np.median(x):.2f}, p5 {np.percentile(x, 5):.2f}, "
            f"min {x.min():.2f}, p95 {np.percentile(x, 95):.2f} cm; under 0: {int((x < 0).sum())} of {len(x)}")
    rig.pose(None, 0)


def export_fit(rig, ob, path):
    from types import SimpleNamespace
    for o in (rig.body, rig.top, rig.tr):
        if o is not ob and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)
    G.export(SimpleNamespace(arm=rig.arm, garment=ob), path)


def main():
    a = parse_args()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    rig = Rig(a)
    anims = [os.path.join(a.src, a.anim)] if a.anim else sorted(glob.glob(os.path.join(a.src, "anim_*.fbx")))
    report = {"z_edge_bind": rig.z_edge, "anims": {}}
    log("bind pose:")
    report["bind"] = probe(rig, a, None, [0], rig.z_edge - a.band, rig.z_edge)
    for p in anims:
        src, f0, f1 = rig.anim(p)
        frames = [int(x) for x in a.frames.split(",")] if a.frames else \
            [int(f0 + (f1 - f0) * k / max(1, a.samples - 1)) for k in range(a.samples)]
        log(f"{os.path.basename(p)}: frames {f0}..{f1}, probing {frames}")
        report["anims"][os.path.basename(p)] = probe(rig, a, src, frames, rig.z_edge - a.band, rig.z_edge)
        bpy.data.objects.remove(src, do_unlink=True)
    if a.fit:
        src, f0, f1 = rig.anim(anims[0])
        ob = fit(rig, a, src)
        log("after the fit:")
        report["after"] = probe(rig, a, src, [a.fit_frame], rig.z_edge - a.band, rig.z_edge)
        report["after_bind"] = probe(rig, a, None, [0], rig.z_edge - a.band, rig.z_edge)
        bpy.data.objects.remove(src, do_unlink=True)
        json.dump(report, open(os.path.join(a.out, "waist.json"), "w"))
        export_fit(rig, ob, os.path.join(a.out, f"garment_fit_{a.fit}.fbx"))
        return
    json.dump(report, open(os.path.join(a.out, "waist.json"), "w"))
    log(f"done in {time.time() - t0:.0f}s -> {a.out}/waist.json")


if __name__ == "__main__":
    main()
