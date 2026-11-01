"""Per-FBX stats for her outfit: bbox (cm, her frame), triangles, material slots.
    blender -b --factory-startup -P her_outfit_stats.py -- <fbx> [<fbx> ...]"""
import sys

import bpy
from mathutils import Vector

for path in sys.argv[sys.argv.index("--") + 1:]:
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.import_scene.fbx(filepath=path)
    pts, tris, slots = [], 0, []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        pts += [o.matrix_world @ v.co for v in o.data.vertices]
        tris += sum(len(p.vertices) - 2 for p in o.data.polygons)
        slots += [s.material.name if s.material else "" for s in o.material_slots]
    lo = Vector([min(p[i] for p in pts) for i in range(3)]) * 100
    hi = Vector([max(p[i] for p in pts) for i in range(3)]) * 100
    print("STATS", path.rsplit("/", 1)[-1], "bbox_cm", [round(x, 1) for x in hi - lo],
          "min", [round(x, 1) for x in lo], "max", [round(x, 1) for x in hi], "tris", tris, "slots", slots)
