"""her_watch_fit: where her smartwatch sits on her left wrist, checked on her own body (Blender, review only).

Her left wrist in her A-pose reference body as exported from Unreal (--src: body.fbx, idle.fbx), measured where the
watch goes (the wrist's cross-section --at cm above the wrist joint, hand_l, along the forearm), and the watch
(--watch: smartwatch.fbx) put there the way unreal/studio.py puts it: its loop's centre on the wrist's centre, its
screen (+Z) on the back of the wrist (wrist_outer_l - wrist_inner_l, square to the forearm: the side the fingers
curl away from), its crown (+Y) toward the hand, riding lowerarm_twist_01_l (the bone the skin there follows: 0.78
of its weight, against 0.2 for lowerarm_twist_02_l, which is near the elbow and takes little of the forearm's roll).

Prints the wrist's size there and the watch's gap to her skin round the loop (case back and band, cm), and renders
close-ups: the back of the wrist, the thumb side, the little-finger side, a 3/4 from the hand, and the same on
frames of idle.fbx (her arms move and the forearm rolls), so the watch can be seen to stay on the back of the wrist.

    blender -b --factory-startup -P her_watch_fit.py -- --src <dir with body.fbx, idle.fbx> --watch smartwatch.fbx \
        --out <dir> [--at 2.6] [--frames 0,60,120]
"""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

BONE = "lowerarm_twist_01_l"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="her_watch_fit")
    ap.add_argument("--src", required=True)
    ap.add_argument("--watch", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--at", type=float, default=2.6, help="cm above the wrist joint (hand_l) to the loop's centre")
    ap.add_argument("--frames", default="", help="idle.fbx frames to check posed, e.g. 0,60,120")
    ap.add_argument("--tag", default="")
    ap.add_argument("--samples", type=int, default=24)
    return ap.parse_args(argv)


def import_fbx(path, **kw):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, **kw)
    return [o for o in bpy.data.objects if o not in before]


def wrist_frame(arm, at):
    """The watch's frame in her rest pose (metres): centre, forearm (to the hand), back of the wrist, thumb side."""
    B = {b.name: (arm.matrix_world @ b.head_local) for b in arm.data.bones}
    h = B["hand_l"]
    fwd = (h - B["lowerarm_twist_02_l"]).normalized()
    o = B["wrist_outer_l"] - B["wrist_inner_l"]
    dors = (o - fwd * o.dot(fwd)).normalized()
    side = fwd.cross(dors)
    return h - fwd * (at / 100.0), fwd, dors, side


def section(body, c, fwd, dors, side):
    """The wrist's cross-section through c, square to the forearm: its centroid offset and half-extents (cm)."""
    me = body.data
    X = np.array([(body.matrix_world @ v.co)[:] for v in me.vertices])
    s = (X - np.array(c[:])) @ np.array(fwd[:])
    E = np.zeros(len(me.edges) * 2, int)
    me.edges.foreach_get("vertices", E)
    E = E.reshape(-1, 2)
    E = E[s[E[:, 0]] * s[E[:, 1]] < 0]
    t = s[E[:, 0]] / (s[E[:, 0]] - s[E[:, 1]])
    P = X[E[:, 0]] + t[:, None] * (X[E[:, 1]] - X[E[:, 0]])
    r = P - np.array(c[:])
    P = P[np.linalg.norm(r, axis=1) < 0.06]
    r = (P - np.array(c[:])) * 100
    d, w = r @ np.array(dors[:]), r @ np.array(side[:])
    ang = np.arctan2(d, w)
    Q = r[np.argsort(ang)]
    per = float(np.linalg.norm(np.diff(np.vstack([Q, Q[:1]]), axis=0), axis=1).sum())
    return dict(centre_dors=(d.max() + d.min()) / 2, centre_side=(w.max() + w.min()) / 2,
                half_dors=(d.max() - d.min()) / 2, half_side=(w.max() - w.min()) / 2, perimeter=per)


def gaps(watch, body):
    """Per watch vertex on the inner side (facing the wrist), the distance to her skin (cm): min and by part."""
    dg = bpy.context.evaluated_depsgraph_get()
    be = body.evaluated_get(dg)
    bm = be.to_mesh()
    bvh = BVHTree.FromPolygons([be.matrix_world @ v.co for v in bm.vertices], [p.vertices[:] for p in bm.polygons])
    we = watch.evaluated_get(dg)
    wm = we.to_mesh()
    inside, mind = [], 9.0
    for v in wm.vertices:
        p = we.matrix_world @ v.co
        loc, nor, _, dist = bvh.find_nearest(p)
        if loc is None:
            continue
        sgn = 1 if (p - loc).dot(nor) > 0 else -1
        if dist < 0.02:
            inside.append(sgn * dist * 100)
    be.to_mesh_clear()
    we.to_mesh_clear()
    a = np.array(inside)
    return dict(min=round(float(a.min()), 2), p05=round(float(np.percentile(a, 5)), 2),
                inside_skin=int((a < 0).sum()), n=len(a))


def light_rig(target):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in {e.identifier for e in
                                                               bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items} else "BLENDER_EEVEE_NEXT"
    w = sc.world or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.25, 0.25, 0.27, 1)
    for k, (d, e) in enumerate((((1, -1, 1.2), 40.0), ((-1, 0.5, 0.6), 15.0), ((0, 1, -0.4), 10.0))):
        ld = bpy.data.lights.new(f"L{k}", "AREA")
        ld.energy = e
        ld.size = 0.4
        lo = bpy.data.objects.new(f"L{k}", ld)
        sc.collection.objects.link(lo)
        lo.location = target + Vector(d).normalized() * 0.6
        lo.rotation_euler = (target - lo.location).to_track_quat("-Z", "Y").to_euler()


def shoot(path, target, view, up, dist=0.16, lens=70, samples=24):
    sc = bpy.context.scene
    cam = sc.camera
    if cam is None:
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        sc.collection.objects.link(cam)
        sc.camera = cam
    cam.data.lens = lens
    cam.data.clip_start = 0.005
    cam.location = target + view.normalized() * dist
    z = (cam.location - target).normalized()
    x = up.cross(z).normalized()
    y = z.cross(x)
    cam.matrix_world = Matrix((x, y, z)).transposed().to_4x4()
    cam.location = target + view.normalized() * dist
    sc.render.resolution_x = sc.render.resolution_y = 900
    try:
        sc.eevee.taa_render_samples = samples
    except AttributeError:
        pass
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    a = parse_args()
    os.makedirs(a.out, exist_ok=True)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    objs = import_fbx(os.path.join(a.src, "body.fbx"))
    arm = next(o for o in objs if o.type == "ARMATURE")
    body = next(o for o in objs if o.type == "MESH")
    skin = bpy.data.materials.new("Skin")
    skin.diffuse_color = (0.55, 0.33, 0.24, 1)
    skin.use_nodes = True
    skin.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.33, 0.24, 1)
    body.data.materials.clear()
    body.data.materials.append(skin)
    for p in body.data.polygons:
        p.use_smooth = True
    c, fwd, dors, side = wrist_frame(arm, a.at)
    sec = section(body, c, fwd, dors, side)
    centre = c + dors * (sec["centre_dors"] / 100) + side * (sec["centre_side"] / 100)
    wobjs = import_fbx(a.watch)
    watch = next(o for o in wobjs if o.type == "MESH")
    # the watch's +Y (crown) to the hand, +Z (screen) to the back of the wrist
    R = Matrix((fwd.cross(dors), fwd, dors)).transposed()
    watch.matrix_world = Matrix.Translation(centre) @ R.to_4x4()
    bpy.context.view_layer.update()
    # ride the bone (as attach_to_component with KEEP_WORLD)
    mw = watch.matrix_world.copy()
    watch.parent = arm
    watch.parent_type = "BONE"
    watch.parent_bone = BONE
    bpy.context.view_layer.update()
    watch.matrix_world = mw
    rep = {"at_cm": a.at, "wrist": {k: round(float(v), 2) for k, v in sec.items()}, "rest_gap": gaps(watch, body)}
    light_rig(centre)
    tag = a.tag
    views = [("back", dors, fwd), ("thumb", side, dors), ("pinky", -side, dors),
             ("q", (dors * 0.8 + side * 0.6 + fwd * 0.6), dors)]
    for name, v, up in views:
        shoot(os.path.join(a.out, f"watch{tag}_rest_{name}.png"), centre, v, up, samples=a.samples)
    if a.frames:
        idle = [o for o in import_fbx(os.path.join(a.src, "idle.fbx")) if o.type == "ARMATURE"]
        act = idle[0].animation_data.action if idle and idle[0].animation_data else None
        for o in bpy.data.objects:
            if o.name.startswith(("idle", "Armature")) and o not in (arm, body, watch) and o.type != "ARMATURE":
                pass
        if act is not None:
            arm.animation_data_create()
            arm.animation_data.action = act
            for o in idle:
                bpy.data.objects.remove(o, do_unlink=True)
            for f in [int(x) for x in a.frames.split(",")]:
                bpy.context.scene.frame_set(f)
                bpy.context.view_layer.update()
                pb = arm.pose.bones
                m = arm.matrix_world @ pb["hand_l"].matrix
                h = m.translation
                mo = arm.matrix_world @ pb["wrist_outer_l"].matrix
                mi = arm.matrix_world @ pb["wrist_inner_l"].matrix
                f2 = (h - (arm.matrix_world @ pb["lowerarm_twist_02_l"].matrix).translation).normalized()
                o = mo.translation - mi.translation
                d2 = (o - f2 * o.dot(f2)).normalized()
                s2 = f2.cross(d2)
                ctr = h - f2 * (a.at / 100)
                # the watch's screen against the back of her wrist, posed: the angle between them (deg)
                zw = (watch.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
                rep[f"frame_{f}"] = {"screen_vs_back_deg": round(math.degrees(zw.angle(d2)), 1), "gap": gaps(watch, body)}
                for name, v, up in (("back", d2, f2), ("q", d2 * 0.8 + s2 * 0.6 + f2 * 0.6, d2)):
                    shoot(os.path.join(a.out, f"watch{tag}_f{f}_{name}.png"), ctr, v, up, samples=a.samples)
    print("WATCHFIT " + json.dumps(rep))
    json.dump(rep, open(os.path.join(a.out, f"watch_fit{tag}.json"), "w"), indent=1)


main()
