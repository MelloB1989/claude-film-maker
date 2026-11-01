"""Debug: how far a garment's outer face is off her skin (cm), as percentiles, and where it is farthest.
    blender -b --factory-startup -P her_outfit_measure.py -- <garment.fbx> <body.fbx> [face.fbx]"""
import sys
import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
a = sys.argv[sys.argv.index("--") + 1:]
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)


def load(p):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=p)
    o = [x for x in bpy.data.objects if x not in before and x.type == "MESH"][0]
    X = np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) * 100
    o.data.calc_loop_triangles()
    T = np.array([t.vertices[:] for t in o.data.loop_triangles])
    return o, X, T


g, G, GT = load(a[0])
parts = [load(x)[1:] for x in a[1:]]
B = np.concatenate([p[0] for p in parts])
BT = np.concatenate([p[1] + sum(len(q[0]) for q in parts[:k]) for k, p in enumerate(parts)])
bvh = BVHTree.FromPolygons(B.tolist(), BT.tolist())
n = len(G)
# the outer layer: the first third-ish of verts (solidify puts the outer surface first); test all, report by height
d = np.array([bvh.find_nearest(Vector(p))[3] for p in G])
for lo, hi in ((100, 112), (112, 122), (122, 132), (132, 142)):
    m = (G[:, 2] >= lo) & (G[:, 2] < hi)
    if m.any():
        q = np.percentile(d[m], [50, 90, 99]).round(2)
        print(f"MEASURE z {lo}-{hi}: n {m.sum()} p50/p90/p99 {q.tolist()} max {d[m].max():.2f} at {G[m][d[m].argmax()].round(1).tolist()}")
