"""Round 5b (agent-02): two neck masks compared where MetaHuman reads them, per face vertex (bilinear at its UV 0
copies, the darkest copy per position), against the observed build. ComputeShrinkWeight (5.8.4) is proportional:
w = 1 - clamp((p - MaxCull) / (MinKeep - MaxCull)), move = w x MaxShrinkDistance. Per mask: the positions it shrinks
(p < MinKeep), the predicted count moving > 0.5 cm and its median move, the lowest such z, and the open-edge verts it
shrinks. If two masks predict different counts/medians but the box measures the same, the build did not read the
second one (or does not shrink proportionally).

    blender -b --factory-startup -P mask_diff.py -- <face.fbx> <a.png> <b.png> [shrink_cm 3.0] [min_keep 0.9]
"""
import sys

import bpy
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
face_fbx, pa, pb = a[0], a[1], a[2]
SHRINK = float(a[3]) if len(a) > 3 else 3.0
KEEP = float(a[4]) if len(a) > 4 else 0.9
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.fbx(filepath=face_fbx)
face = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
me = face.data
lv = np.zeros(len(me.loops), int)
me.loops.foreach_get("vertex_index", lv)
uv = np.zeros(len(me.loops) * 2)
me.uv_layers[0].data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
co = np.zeros(len(me.vertices) * 3)
me.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)
M = np.array(face.matrix_world)
W = (M @ np.c_[co, np.ones(len(co))].T).T[:, :3] * 100.0  # cm, world (z up)
_, grp = np.unique(np.round(co * 1e4).astype(np.int64), axis=0, return_inverse=True)
grp = grp.ravel()
ng = int(grp.max()) + 1
gz = np.full(ng, 1e9)
np.minimum.at(gz, grp, W[:, 2])
# open edges (positions on an edge of one polygon), welded by position
ec = {}
for p in me.polygons:
    vs = [grp[v] for v in p.vertices]
    for i in range(len(vs)):
        k = tuple(sorted((vs[i], vs[(i + 1) % len(vs)])))
        ec[k] = ec.get(k, 0) + 1
openg = np.zeros(ng, bool)
for k, n in ec.items():
    if n == 1:
        openg[list(k)] = True


def load(p):
    img = bpy.data.images.load(p)
    w, h = img.size
    return np.array(img.pixels[:], np.float32).reshape(h, w, img.channels)[:, :, 0]


def per_pos(P):
    H, Wd = P.shape
    fx, fy = uv[:, 0] * Wd - 0.5, uv[:, 1] * H - 0.5
    ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
    ax, ay = fx - ix, fy - iy
    c = lambda x, y: P[np.clip(y, 0, H - 1), np.clip(x, 0, Wd - 1)]
    s = (1 - ax) * (1 - ay) * c(ix, iy) + ax * (1 - ay) * c(ix + 1, iy) + (1 - ax) * ay * c(ix, iy + 1) + \
        ax * ay * c(ix + 1, iy + 1)
    lo = np.full(ng, 9.0)
    np.minimum.at(lo, grp[lv], s)
    return lo


out = {}
for tag, path in (("A", pa), ("B", pb)):
    p = per_pos(load(path))
    wgt = 1 - np.clip(p / KEEP, 0, 1)
    mv = wgt * SHRINK
    sh = mv > 0.5
    out[tag] = (p, sh)
    print(f"{tag} {path.split('/')[-1]}: shrinks (p<{KEEP}) {int((p < KEEP).sum())} positions; predicted >0.5 cm "
          f"{int(sh.sum())}, median {float(np.median(mv[sh])) if sh.any() else 0:.2f} cm, lowest z "
          f"{float(gz[sh].min()) if sh.any() else 0:.1f}; open-edge positions shrunk > 0.5 cm {int((sh & openg).sum())}")
pA, sA = out["A"]
pB, sB = out["B"]
print(f"differ: shrunk in A only {int((sA & ~sB).sum())}, in B only {int((sB & ~sA).sum())}, |pA-pB| > 0.05 at "
      f"{int((np.abs(pA - pB) > 0.05).sum())} positions")
