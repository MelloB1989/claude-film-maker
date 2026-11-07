"""Dump a Mixamo FBX's motion for retarget.py (agent-08, R7 gesture library). Runs headless in Blender on box B:

    blender -b --factory-startup -t 4 -P mixamo_dump_blender.py -- clip.fbx clip_dump.json

Out: {fps, frames: [{bone: {t, q}}], rest: {bone: {t, q}}}: every bone's world position (cm) and rotation (x y z w)
in UE component space. Blender is right-handed and UE left-handed: UE imports an FBX with Y negated, so here
t -> (x, -y, z) and q -> (-x, y, -z, w) (the rotation conjugated by that reflection).
"""
import json
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=src, automatic_bone_orientation=False, ignore_leaf_bones=False)
arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
act = arm.animation_data.action if arm.animation_data else None
if act is None:
    raise SystemExit(f"{src}: no animation")
scene = bpy.context.scene
f0, f1 = (int(round(x)) for x in act.frame_range)
fps = scene.render.fps / scene.render.fps_base


def ue(m):
    """Position (cm) and rotation of a Blender world matrix (metres; the FBX importer's 0.01 sits on the object)."""
    t = m.to_translation() * 100.0
    q = m.to_3x3().normalized().to_quaternion().normalized()
    return {"t": [round(t.x, 4), round(-t.y, 4), round(t.z, 4)],
            "q": [round(-q.x, 7), round(q.y, 7), round(-q.z, 7), round(q.w, 7)]}


mw = arm.matrix_world
# matrix_world carries the 0.01 import scale: normalise rotations, keep it for the translations
rest = {b.name: ue(mw @ b.matrix_local) for b in arm.data.bones}
frames = []
for f in range(f0, f1 + 1):
    scene.frame_set(f)
    frames.append({pb.name: ue(mw @ pb.matrix) for pb in arm.pose.bones})

json.dump({"source": src.rsplit("/", 1)[-1], "fps": fps, "frame_range": [f0, f1], "rest": rest, "frames": frames},
          open(out, "w"))
print(json.dumps({"out": out, "fps": fps, "frames": len(frames), "bones": len(rest)}))
