"""A retargeted clip on a neutral mannequin (capsules on the MetaHuman skeleton's joints; no mesh of hers), for the
library's previews (agent-08, R7). Headless on box B:

    blender -b --factory-startup -t 4 -P preview_blender.py -- clip_rtg.json skeleton_read.json out.mp4 [title]

Front three-quarter camera at chest height, a grey mic post on the body's LEFT front (where her desk mic is), the
torso drawn as an ellipsoid of a slim adult's chest so arm-to-torso clearance reads by eye. 640x360, 30 fps, H.264.
"""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retarget as R  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
clip_path, skel_path, out = argv[0], argv[1], argv[2]
title = argv[3] if len(argv) > 3 else Path(clip_path).stem
clip = json.load(open(clip_path))
tg = R.Target(json.load(open(skel_path)))
fps = int(round(clip["fps"]))

SEGS = [("pelvis", "spine_03", 7.0), ("spine_03", "spine_05", 8.0), ("spine_05", "neck_01", 5.0),
        ("neck_01", "head", 4.0)]
for s in ("l", "r"):
    SEGS += [(f"clavicle_{s}", f"upperarm_{s}", 3.5), (f"upperarm_{s}", f"lowerarm_{s}", 4.2),
             (f"lowerarm_{s}", f"hand_{s}", 3.4), (f"hand_{s}", f"middle_01_{s}", 2.6)]
    for f in ("thumb", "index", "middle", "ring", "pinky"):
        SEGS += [(f"{f}_01_{s}", f"{f}_02_{s}", 0.9), (f"{f}_02_{s}", f"{f}_03_{s}", 0.8)]
    SEGS += [(f"thigh_{s}", f"calf_{s}", 6.5), (f"calf_{s}", f"foot_{s}", 5.0)]
SEGS = [g for g in SEGS if g[0] in tg.t and g[1] in tg.t]


def world_positions(frame_locals):
    """FK of every bone: the clip's locals where it has them, the rest elsewhere."""
    q = dict(zip(clip["bones"], frame_locals))
    W, P = {}, {}
    for b in tg.order:
        p = tg.parent.get(b)
        loc = q.get(b, tg.local[b]["q"])
        if not p or p not in W:
            W[b], P[b] = tg.q[b], list(tg.t[b])
        else:
            W[b] = R.qnorm(R.qmul(W[p], loc))
            P[b] = R.add(P[p], R.qrot(W[p], tg.local[b]["t"]))
    return P


def bl(p):
    """UE cm -> Blender m (Y negated)."""
    return Vector((p[0] / 100.0, -p[1] / 100.0, p[2] / 100.0))


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "OBJECT"
scene.display.shading.show_shadows = True
scene.render.resolution_x, scene.render.resolution_y = 640, 360
scene.render.fps = fps
scene.frame_start, scene.frame_end = 0, len(clip["frames"]) - 1
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
scene.render.filepath = out
world = bpy.data.worlds.new("w")
world.color = (0.82, 0.83, 0.85)
scene.world = world
scene.render.use_stamp = True
scene.render.use_stamp_frame = True
scene.render.use_stamp_note = True
scene.render.stamp_note_text = title
for k in ("use_stamp_date", "use_stamp_time", "use_stamp_render_time", "use_stamp_camera", "use_stamp_lens",
          "use_stamp_scene", "use_stamp_filename", "use_stamp_memory", "use_stamp_hostname"):
    setattr(scene.render, k, False)


def capsule(name, r, color):
    bpy.ops.mesh.primitive_cylinder_add(radius=1.0, depth=1.0, vertices=16)
    o = bpy.context.object
    o.name = name
    o.color = color
    o.dimensions = (2 * r / 100.0, 2 * r / 100.0, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    return o


skin = (0.70, 0.66, 0.62, 1.0)
objs = [(a, b, capsule(f"{a}-{b}", r, skin)) for a, b, r in SEGS]
joints = {}
for a, b, r in SEGS:
    for j in (a, b):
        if j not in joints:
            bpy.ops.mesh.primitive_uv_sphere_add(radius=r / 100.0 * 1.05, segments=12, ring_count=8)
            joints[j] = bpy.context.object
            joints[j].color = skin
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, segments=24, ring_count=16)
head = bpy.context.object
head.color = skin
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=24, ring_count=16)
chest = bpy.context.object
chest.color = (0.62, 0.66, 0.72, 1.0)

P0 = world_positions(clip["frames"][0])
up = R.unit(R.sub(tg.t["neck_01"], tg.t["pelvis"]))
left = R.ortho(R.sub(tg.t["upperarm_l"], tg.t["upperarm_r"]), up)
hands0 = R.mul(R.add(P0["hand_l"], P0["hand_r"]), 0.5)
fwd = R.ortho(R.sub(hands0, tg.t["spine_05"]), up)
fwd = R.ortho(fwd, left)
# the mic post: the body's left front at chest height
mic_at = R.add(R.add(tg.t["spine_03"], R.mul(left, 24.0)), R.mul(fwd, 32.0))
bpy.ops.mesh.primitive_cylinder_add(radius=0.025, depth=0.30, location=bl(mic_at))
bpy.context.object.color = (0.25, 0.25, 0.27, 1.0)

for f, loc in enumerate(clip["frames"]):
    P = world_positions(loc)
    for a, b, o in objs:
        pa, pb = bl(P[a]), bl(P[b])
        d = pb - pa
        o.matrix_world = Matrix.Translation((pa + pb) / 2) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4() @ \
            Matrix.Diagonal((1.0, 1.0, max(d.length, 1e-4), 1.0))
        o.keyframe_insert("location", frame=f)
        o.keyframe_insert("rotation_euler", frame=f)
        o.keyframe_insert("scale", frame=f)
    for j, o in joints.items():
        o.location = bl(P[j])
        o.keyframe_insert("location", frame=f)
    head.location = bl(R.add(P["head"], R.mul(up, 9.0)))
    head.keyframe_insert("location", frame=f)
    # chest: an ellipsoid 30 x 20 x 26 cm about spine_04 (the MH body faces +Y, its width along X)
    c = bl(R.add(P["spine_04"], R.mul(fwd, 3.0)))
    chest.matrix_world = Matrix.Translation(c) @ Matrix.Diagonal((0.15, 0.10, 0.13, 1.0))
    chest.keyframe_insert("location", frame=f)
    chest.keyframe_insert("scale", frame=f)

cam_at = R.add(R.add(tg.t["spine_05"], R.mul(fwd, 190.0)), R.mul(left, -70.0))
bpy.ops.object.camera_add(location=bl(cam_at))
cam = bpy.context.object
cam.data.lens = 50
look = bl(R.sub(tg.t["spine_05"], R.mul(up, 8.0)))
cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam
bpy.ops.render.render(animation=True)
print(json.dumps({"out": out, "frames": len(clip["frames"]), "fps": fps}))
