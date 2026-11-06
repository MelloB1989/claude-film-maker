"""garment.fit: refit a garment to a MetaHuman's body with REAL ease, headless, on the box (the body never leaves it).

    blender -b --factory-startup -P blender/garment_fit.py -- --src <garment.export out_dir> --garment tee \
        --out <dir> [--ease '{"chest": 1.8}'] [--drape-frames 40] [--weights transfer|keep] [--thickness 0]

(`film-ue garment fit` builds this command, runs it and checks the report: docs/unreal/garment.md.)

In: garment.export's FBXs (cm, the body skeleton): ref_body.fbx (the UNCUT body: the collider, and the weights'
source), face.fbx (a MetaHuman's face mesh runs ~10 cm below neck_01, to the clavicles: its lower neck is in the
collider, or the collar fits the body and the face comes out through it, round 4's 'orange patch'), garment_<g>.fbx,
anim_*.fbx (the pose tests). With --morph-ref, ref_body.fbx may be ANOTHER person's uncut body of the same MetaHuman topology:
it is morphed onto body.fbx (his worn, cut body) where they meet, the cut region filled smoothly (round 5: no uncut
body of Host_Op existed in the project). The garment keeps its topology, UVs and material slots: only its vertices move and its
weights change, so its materials (and their normal maps) still fit it.

Steps (lib/garmentfit.py has the numbers, tested without Blender):
1. collider = ref body + face, BVH; each garment vertex's signed distance to it (+ outside).
2. optional DRAPE (--drape-frames N): Blender cloth on the garment in the rest pose, the collar and shoulder seam
   pinned, the collider with collision distance = min ease: the hem and sleeves fall, folds form (a shell does not).
3. FIT: a target ease per region (collar 0.8, shoulder 0.6, sleeve 1.4, chest 1.6, waist 2.4, hem 2.8 cm; --ease
   overrides) from each vertex's dominant bone; the displacement along the body normal to reach it, SMOOTHED as a
   field (corrective smooth of the move, not of the shape: the garment keeps its seams and folds); 3 passes; then
   a hard pass: nothing closer than --min-ease.
4. WEIGHTS: --weights transfer (default): the Data Transfer modifier from the ref body (nearest face interpolated),
   smoothed, max 8 influences, normalized; keep: the garment's own.
5. THICKNESS: --thickness > 0 adds a Solidify (outward) to an OPEN single-layer garment; a closed shell (a MetaHuman
   default garment) is left as is.
6. Vertex colours for the cloth setup: R = ease / 5 cm, G = 1 on the pinned collar and shoulder (T3b's cloth.setup).
7. Pose tests: every anim_*.fbx at --anim-samples frames: garment verts inside the body or the face (posed).
8. Export garment_fit_<g>.fbx (cm, unscaled root: the recipe proven on his trousers) + fit_report.json.

Exit 1 when the fit gate fails (verts inside, too tight, an even shell) or a pose test clips: the FBX is still
written, `film-ue garment fit` refuses to import it.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import garmentfit as GF  # noqa: E402

NAME = "garment_fit"


def log(*a):
    print(f"[{NAME}]", *a, flush=True)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog=NAME)
    ap.add_argument("--src", required=True, help="garment.export's out_dir")
    ap.add_argument("--garment", default="tee", help="the role exported as garment_<role>.fbx")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ease", default="", help='JSON {region: cm} over lib/garmentfit.EASE_CM')
    ap.add_argument("--min-ease", type=float, default=GF.MIN_EASE_CM)
    ap.add_argument("--slack", type=float, default=3.0, help="cm looser than the target before it is drawn in")
    ap.add_argument("--pull", type=float, default=0.35)
    ap.add_argument("--smooth-iters", type=int, default=12)
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--drape-frames", type=int, default=0)
    ap.add_argument("--weights", choices=("transfer", "keep"), default="transfer")
    ap.add_argument("--thickness", type=float, default=0.0, help="cm, Solidify on an open garment (0: none)")
    ap.add_argument("--only-slots", default="", help="comma list: fit only faces of material slots containing these")
    ap.add_argument("--collider", default="ref_body,face")
    ap.add_argument("--anim-samples", type=int, default=12)
    ap.add_argument("--morph-ref", action="store_true",
                    help="ref_body.fbx is ANOTHER person's uncut body (same MetaHuman topology): morph it onto this "
                         "person's worn (cut) body.fbx, filling the cut region smoothly (no uncut body of his exists)")
    ap.add_argument("--match-cm", type=float, default=1.5)
    return ap.parse_args(argv)


def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def world_cm(ob, evaluated=False) -> tuple:
    """(verts cm world, triangles) of a mesh object, evaluated (posed, modifiers) or rest."""
    if evaluated:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
    else:
        me = ob.data
    X = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", X)
    M = np.array(ob.matrix_world)
    X = (M @ np.c_[X.reshape(-1, 3), np.ones(len(me.vertices))].T).T[:, :3] * 100.0
    me.calc_loop_triangles()
    T = np.zeros(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", T)
    if evaluated:
        ev.to_mesh_clear()
    return X, T.reshape(-1, 3)


def set_world_cm(ob, X):
    Mi = np.array(ob.matrix_world.inverted())
    L = (Mi @ np.c_[X / 100.0, np.ones(len(X))].T).T[:, :3]
    ob.data.vertices.foreach_set("co", L.ravel())
    ob.data.update()


def weights_of(ob) -> tuple:
    """(n x groups weights, group names)."""
    groups = [g.name for g in ob.vertex_groups]
    W = np.zeros((len(ob.data.vertices), len(groups)))
    for v in ob.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    return W, groups


def bind(ob, arm):
    """Drop the object's own armature (an FBX brings one each), bind it to `arm`."""
    own = ob.parent if ob.parent and ob.parent.type == "ARMATURE" else None
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = mw
    if own is not None and own != arm:
        bpy.data.objects.remove(own, do_unlink=True)
    mods = [m for m in ob.modifiers if m.type == "ARMATURE"]
    if not mods:
        mods = [ob.modifiers.new("Armature", "ARMATURE")]
    for m in mods:
        m.object = arm


class Scene:
    def __init__(self, a):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        man = os.path.join(a.src, "manifest.json")
        self.manifest = json.load(open(man)) if os.path.exists(man) else {}
        objs = import_fbx(os.path.join(a.src, "ref_body.fbx"))
        self.arm = next(o for o in objs if o.type == "ARMATURE")
        self.body = next(o for o in objs if o.type == "MESH")
        self.morph = None
        if a.morph_ref:
            self.morph = self._morph(a)
        self.face = None
        if "face" in a.collider and os.path.exists(os.path.join(a.src, "face.fbx")):
            fo = import_fbx(os.path.join(a.src, "face.fbx"))
            self.face = next((o for o in fo if o.type == "MESH"), None)
            for o in fo:  # the face's own skeleton: its rest pose is where it sits; posed tests use the body's neck
                if o.type == "ARMATURE":
                    mw = self.face.matrix_world.copy()
                    self.face.parent = None
                    self.face.matrix_world = mw
                    bpy.data.objects.remove(o, do_unlink=True)
            for m in list(self.face.modifiers):
                self.face.modifiers.remove(m)
            self._face_follow()
        go = import_fbx(os.path.join(a.src, f"garment_{a.garment}.fbx"))
        self.garment = next(o for o in go if o.type == "MESH")
        for o in go:
            if o.type == "ARMATURE":
                mw = self.garment.matrix_world.copy()
                self.garment.parent = None
                self.garment.matrix_world = mw
                bpy.data.objects.remove(o, do_unlink=True)
        bind(self.garment, self.arm)
        log(f"body {len(self.body.data.vertices)} v, face {len(self.face.data.vertices) if self.face else 0} v, "
            f"garment {len(self.garment.data.vertices)} v, slots {[m.name if m else '' for m in self.garment.data.materials]}")

    def _morph(self, a) -> dict:
        """ref_body (another person, uncut) onto body.fbx (him, cut): lib/garmentfit.morph_onto."""
        wo = import_fbx(os.path.join(a.src, "body.fbx"))
        worn = next(o for o in wo if o.type == "MESH")
        WX, WT = world_cm(worn)
        bvh = BVHTree.FromPolygons(WX.tolist(), WT.tolist())
        for o in wo:
            bpy.data.objects.remove(o, do_unlink=True)

        def nearest(p):
            loc, nor, fi, dist = bvh.find_nearest(Vector(p))
            return None if loc is None else loc[:]

        RX, RT = world_cm(self.body)
        M, known, st = GF.morph_onto(RX, RT, nearest, match_cm=a.match_cm, iters=1500)
        set_world_cm(self.body, M)
        log(f"morph: ref onto his worn body: matched {st['matched']:.1%}, the cut region moved median "
            f"{st['fill_median_cm']} cm (max {st['fill_max_cm']})")
        return st

    def _face_follow(self):
        """The face rides the body's head/neck bones (a child of neck_02 kept at its rest offset): close enough for
        the collar in the pose tests (the face's own rig moves the jaw, not the lower neck)."""
        bone = "neck_02" if "neck_02" in self.arm.data.bones else "head"
        mw = self.face.matrix_world.copy()
        self.face.parent = self.arm
        self.face.parent_type = "BONE"
        self.face.parent_bone = bone
        self.face.matrix_world = mw

    def collider(self, evaluated=False):
        parts = [world_cm(self.body, evaluated)]
        if self.face is not None:
            parts.append(world_cm(self.face, evaluated))
        X = np.concatenate([p[0] for p in parts])
        off = np.cumsum([0] + [len(p[0]) for p in parts[:-1]])
        T = np.concatenate([p[1] + o for p, o in zip(parts, off)])
        return X, T, BVHTree.FromPolygons(X.tolist(), T.tolist())


def signed(bvh, P) -> tuple:
    """(signed distance cm, unit normal at the nearest point) per point."""
    d = np.zeros(len(P))
    N = np.zeros((len(P), 3))
    for i, p in enumerate(P):
        loc, nor, fi, dist = bvh.find_nearest(Vector(p))
        if loc is None:
            d[i] = np.inf
            continue
        n = np.array(nor[:])
        d[i] = float((np.array(p) - np.array(loc[:])) @ n)
        N[i] = n
    return d, N


def fit_mask(ob, only_slots: str) -> np.ndarray:
    n = len(ob.data.vertices)
    if not only_slots:
        return np.ones(n, bool)
    keys = [k.strip().lower() for k in only_slots.split(",") if k.strip()]
    names = [m.name.lower() if m else "" for m in ob.data.materials]
    m = np.zeros(n, bool)
    for p in ob.data.polygons:
        if any(k in names[p.material_index] for k in keys):
            m[list(p.vertices)] = True
    return m


def drape(sc, a, pinned, active):
    """Blender cloth on the garment in the rest pose: pinned collar/shoulder, the collider at min ease."""
    ob = sc.garment
    pin = ob.vertex_groups.new(name="fit_pin")
    pin.add([int(i) for i in np.nonzero(pinned | ~active)[0]], 1.0, "REPLACE")
    for c in (sc.body, sc.face):
        if c is None:
            continue
        col = c.modifiers.new("Collision", "COLLISION")
        c.collision.thickness_outer = max(0.001, a.min_ease / 100.0)
        c.collision.cloth_friction = 5.0
    cl = ob.modifiers.new("Cloth", "CLOTH")
    s = cl.settings  # cotton jersey (Blender's 'Cotton' preset, lighter)
    s.quality = 8
    s.mass = 0.15
    s.tension_stiffness = s.compression_stiffness = 15.0
    s.shear_stiffness = 5.0
    s.bending_stiffness = 0.5
    s.air_damping = 1.0
    s.vertex_group_mass = "fit_pin"
    cs = cl.collision_settings
    cs.distance_min = max(0.001, a.min_ease / 100.0)
    cs.use_self_collision = True
    cs.self_distance_min = 0.002
    sc_ = bpy.context.scene
    sc_.frame_start, sc_.frame_end = 1, a.drape_frames + 1
    cl.point_cache.frame_start, cl.point_cache.frame_end = 1, a.drape_frames + 1
    for f in range(1, a.drape_frames + 2):
        sc_.frame_set(f)
    X, _ = world_cm(ob, evaluated=True)
    ob.modifiers.remove(cl)
    for c in (sc.body, sc.face):
        if c is not None:
            for m in [m for m in c.modifiers if m.type == "COLLISION"]:
                c.modifiers.remove(m)
    sc_.frame_set(1)
    ob.vertex_groups.remove(pin)
    return X


def transfer(sc, a):
    """Weights from the ref body (Data Transfer, nearest face interpolated), smoothed, limited to 8, normalized."""
    ob = sc.garment
    for g in list(ob.vertex_groups):
        ob.vertex_groups.remove(g)
    for g in sc.body.vertex_groups:
        ob.vertex_groups.new(name=g.name)
    m = ob.modifiers.new("FitWeights", "DATA_TRANSFER")
    m.object = sc.body
    m.use_vert_data = True
    m.data_types_verts = {"VGROUP_WEIGHTS"}
    m.vert_mapping = "POLYINTERP_NEAREST"
    m.layers_vgroup_select_src = "ALL"
    m.layers_vgroup_select_dst = "NAME"
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    while ob.modifiers[0].name != m.name:  # it must come before the Armature modifier
        bpy.ops.object.modifier_move_up(modifier=m.name)
    bpy.ops.object.modifier_apply(modifier=m.name)
    W, groups = weights_of(ob)
    lap = GF.neighbours(len(W), world_cm(ob)[1])
    W = GF.smooth_field(W, lap, iters=4, lam=0.5)
    W = GF.limit_normalize(W, 8)
    for gi, name in enumerate(groups):
        vg = ob.vertex_groups[name]
        nz = np.nonzero(W[:, gi])[0]
        vg.remove(list(range(len(W))))
        for i in nz:
            vg.add([int(i)], float(W[i, gi]), "REPLACE")
    for g in [g for g in ob.vertex_groups if not np.any(W[:, groups.index(g.name)])]:
        ob.vertex_groups.remove(g)
    log(f"weights: {len(ob.vertex_groups)} bones, max influences {int((W > 0).sum(1).max())}")


def is_open(ob) -> int:
    from collections import Counter
    c = Counter()
    for p in ob.data.polygons:
        vs = list(p.vertices)
        for i in range(len(vs)):
            c[tuple(sorted((vs[i], vs[(i + 1) % len(vs)])))] += 1
    return sum(1 for v in c.values() if v == 1)


def retarget(src, dst):
    """Pose dst from another armature of the same skeleton (local rotations on dst's own bone offsets)."""
    for pb in dst.pose.bones:
        sb = src.pose.bones.get(pb.name)
        if sb is None or pb.parent is None:
            continue
        sl = (sb.parent.matrix.inverted() @ sb.matrix) if sb.parent else sb.matrix
        rl = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
        want = Matrix.Translation(rl.translation) @ sl.to_quaternion().to_matrix().to_4x4()
        pb.matrix_basis = rl.inverted() @ want


def pose_tests(sc, a, active=None) -> dict:
    """Every anim_*.fbx at anim_samples frames: the FITTED garment verts (active: --only-slots; a MetaHuman default
    garment's shorts are hidden and were never refit, so their thighs say nothing about the tee) inside the posed
    body/face: count, deepest cm (distances past 6 cm are left out: a nearest point across a gap, not a clip)."""
    out = {}
    for p in sorted(glob.glob(os.path.join(a.src, "anim_*.fbx"))):
        before = set(bpy.data.actions)
        objs = import_fbx(p)
        acts = [x for x in bpy.data.actions if x not in before]
        src = next((o for o in objs if o.type == "ARMATURE"), None)
        for o in objs:
            if o.type == "MESH":
                bpy.data.objects.remove(o, do_unlink=True)
        if not acts or src is None:
            continue
        f0, f1 = (int(x) for x in acts[0].frame_range)
        worst = {"inside": 0, "deepest_cm": 0.0, "frame": None}
        for k in range(a.anim_samples):
            f = int(f0 + (f1 - f0) * k / max(1, a.anim_samples - 1))
            bpy.context.scene.frame_set(f)
            retarget(src, sc.arm)
            bpy.context.view_layer.update()
            _, _, bvh = sc.collider(evaluated=True)
            G, _ = world_cm(sc.garment, evaluated=True)
            if active is not None and len(active) == len(G):
                G = G[active]
            d, _ = signed(bvh, G[::2])
            d = d[np.isfinite(d) & (np.abs(d) < 6.0)]
            n_in = int((d < -0.1).sum())
            if n_in > worst["inside"]:
                worst = {"inside": n_in, "deepest_cm": round(float(-d.min()), 2), "frame": f}
        out[os.path.basename(p)[:-4]] = {"frames": [f0, f1], **worst}
        for pb in sc.arm.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        bpy.data.objects.remove(src, do_unlink=True)
        log(f"pose test {os.path.basename(p)}: {out[os.path.basename(p)[:-4]]}")
    bpy.context.view_layer.update()
    return out


def export(sc, path):
    """The armature as Unreal's skeleton root (unparented, scale applied, named 'root'), it and the garment in cm
    (scene unit 0.01, x100 applied): agent-02's recipe from his trousers (an x100 root over bones in metres shrinks
    the garment to nothing once leader pose moves it)."""
    arm, ob = sc.arm, sc.garment
    for o in list(bpy.context.scene.objects):
        if o not in (arm, ob):
            bpy.data.objects.remove(o, do_unlink=True)
    mw = arm.matrix_world.copy()
    arm.parent = None
    arm.matrix_world = mw
    for o in bpy.context.scene.objects:
        o.select_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    arm.name = "root"
    gw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = gw
    for o in (arm, ob):
        o.matrix_world = Matrix.Scale(100.0, 4) @ o.matrix_world
        o.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
    ob.parent = arm
    ob.matrix_parent_inverse = arm.matrix_world.inverted()
    for m in ob.modifiers:
        if m.type == "ARMATURE":
            m.object = arm
    us = bpy.context.scene.unit_settings
    us.system, us.scale_length = "METRIC", 0.01
    for o in bpy.context.scene.objects:
        o.select_set(o in (arm, ob))
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"},
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", global_scale=1.0,
        axis_forward="-Y", axis_up="Z", add_leaf_bones=False, use_armature_deform_only=False,
        bake_anim=False, mesh_smooth_type="OFF", use_mesh_modifiers=False, use_tspace=True,
        primary_bone_axis="Y", secondary_bone_axis="X", path_mode="STRIP", colors_type="LINEAR")
    log(f"exported {path}")


def main():
    a = parse_args()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    sc = Scene(a)
    ease_over = json.loads(a.ease) if a.ease else {}
    W0, groups = weights_of(sc.garment)
    region = GF.regions(W0, groups)
    target = GF.targets(region, ease_over)
    pinned = np.isin(region, [GF.REGIONS.index(r) for r in GF.PINNED])
    active = fit_mask(sc.garment, a.only_slots)
    Xc, Tc, bvh = sc.collider()
    G, Tg = world_cm(sc.garment)
    d0, _ = signed(bvh, G)
    rep = {"args": vars(a), "verts": len(G), "regions": {r: int((region == i).sum()) for i, r in enumerate(GF.REGIONS)},
           "before": GF.ease_report(d0[active], region[active]), "morph": sc.morph}
    log(f"before: {rep['before'].get('all')}")
    if a.drape_frames > 0:
        G = drape(sc, a, pinned, active)
        set_world_cm(sc.garment, G)
        rep["after_drape"] = GF.ease_report(signed(bvh, G)[0][active], region[active])
        log(f"after drape: {rep['after_drape'].get('all')}")
    nbrs = GF.neighbours(len(G), Tg)
    fixed = ~active
    for k in range(max(1, a.passes)):
        d, N = signed(bvh, G)
        d = np.where(np.isfinite(d), d, target + a.slack)
        mv = GF.fit_displacement(d, target, min_ease=a.min_ease, slack=a.slack, pull=a.pull)
        mv[fixed] = 0.0
        mv = GF.smooth_field(mv, nbrs, iters=a.smooth_iters, pinned=fixed)
        N = GF.smooth_field(N, nbrs, iters=2, pinned=fixed)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        G = G + mv[:, None] * N
        log(f"fit pass {k + 1}: moved median {np.median(np.abs(mv)):.2f} cm, max {np.abs(mv).max():.2f}")
    d, N = signed(bvh, G)  # the hard pass: nowhere closer than min ease
    low = active & np.isfinite(d) & (d < a.min_ease)
    G[low] += ((a.min_ease - d[low]) + 0.02)[:, None] * N[low]
    set_world_cm(sc.garment, G)
    d, _ = signed(bvh, G)
    rep["after"] = GF.ease_report(d[active], region[active])
    log(f"after: {rep['after'].get('all')}")
    if a.weights == "transfer":
        transfer(sc, a)
    open_edges = is_open(sc.garment)
    rep["open_edges"] = open_edges
    if a.thickness > 0 and open_edges:
        m = sc.garment.modifiers.new("FitThickness", "SOLIDIFY")
        m.thickness = a.thickness / 100.0
        m.offset = 1.0
        m.use_rim = True
        bpy.context.view_layer.objects.active = sc.garment
        while sc.garment.modifiers[0].name != m.name:
            bpy.ops.object.modifier_move_up(modifier=m.name)
        bpy.ops.object.modifier_apply(modifier=m.name)
        rep["thickness_cm"] = a.thickness
    elif a.thickness > 0:
        rep["thickness_note"] = "closed shell: no Solidify"
    me = sc.garment.data
    col = GF.colours(np.clip(signed(bvh, world_cm(sc.garment)[0])[0], 0, None), np.r_[pinned, np.zeros(
        max(0, len(me.vertices) - len(pinned)), bool)][:len(me.vertices)])
    attr = me.color_attributes.new("FitCol", "BYTE_COLOR", "POINT")
    attr.data.foreach_set("color", col.ravel())
    me.color_attributes.active_color = attr
    rep["poses"] = pose_tests(sc, a, active if len(active) == len(sc.garment.data.vertices) else None)
    problems = GF.fit_gate(rep["after"])
    problems += [f"pose test {k}: {v['inside']} garment verts inside the body at frame {v['frame']} "
                 f"(deepest {v['deepest_cm']} cm)" for k, v in rep["poses"].items() if v["inside"] > 0]
    rep["problems"] = problems
    rep["pass"] = not problems
    fbx = os.path.join(a.out, f"garment_fit_{a.garment}.fbx")
    export(sc, fbx)
    rep["fbx"] = fbx
    rep["seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(a.out, "fit_report.json"), "w") as fh:
        json.dump(rep, fh, indent=1, default=float)
    log(("PASS" if rep["pass"] else "FAIL: " + "; ".join(problems)) + f" ({rep['seconds']} s)")
    sys.exit(0 if rep["pass"] else 1)


if __name__ == "__main__":
    main()
