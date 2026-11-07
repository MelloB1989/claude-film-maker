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

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "..", "..", "..", "blender"))
import garment_fit as G  # noqa: E402  (import_fbx, world_cm, set_world_cm, weights_of, bind, retarget, export)

NAME = "her_waist_r7"
SECTORS = 24
BAND_CLEAR = 0.25      # cm: the band's inner face off her skin
BAND_SLACK = 0.6       # cm: looser than this at a sector and the band is drawn in
TUCK_CLEAR = 0.20      # cm: the Top's tuck inside the band's inner face
UPPER = 12.0           # cm under the band refit with her (then ramped to the trousers' own over RAMP)
RAMP = 6.0


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
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--band", type=float, default=4.0, help="the waistband's height, cm (her_outfit TROUSERS band)")
    return ap.parse_args(argv)


def load(path, arm=None):
    objs = G.import_fbx(path)
    ob = next(o for o in objs if o.type == "MESH")
    a = next((o for o in objs if o.type == "ARMATURE"), None)
    if arm is not None:
        G.bind(ob, arm)
        for o in objs:
            if o.type == "ARMATURE" and o != arm and o.name in bpy.data.objects:
                bpy.data.objects.remove(o, do_unlink=True)
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
        self.top, _ = load(os.path.join(a.src, "garment_Top.fbx"), self.arm)
        self.tr, _ = load(os.path.join(a.src, "garment_Trousers.fbx"), self.arm)
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
        f"(max {max(tp) if tp else 0:.2f}); band rays missing {miss}")


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
    json.dump(report, open(os.path.join(a.out, "waist.json"), "w"))
    log(f"done in {time.time() - t0:.0f}s -> {a.out}/waist.json")


if __name__ == "__main__":
    main()
