"""Round 5b (agent-02): why Fit7's previews showed two dark ovals on his chest. Epic's default tee is a CLOSED shell
(outer and inner wall ~0.34 cm apart, joined at the rims) and garment-fit moves every vertex along the body normal
to its region's ease, both walls to the same target: where they cross, the inner wall (normals in) or the hollow
inside (his worn body is cut there: nothing behind) is what the camera sees. qa.clip's Body>tee cannot see it (no
body pixels in front of the tee). This compares the fitted tee with the exported original, same topology:

  per vertex, the normal's turn vs the original (> 90 deg: the face turned inside out), and the walls crossing
  (non-adjacent triangles of the shirt slot that intersect, BVH self-overlap), each located by height and side.

    blender -b --factory-startup -P tee_layers.py -- <garment_tee.fbx (the export)> <garment_fit_tee.fbx> [slot substr]
"""
import sys

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

a = sys.argv[sys.argv.index("--") + 1:]
SLOT = a[2] if len(a) > 2 else "shirt"


def load(p):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.import_scene.fbx(filepath=p)
    ob = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
    for m in list(ob.modifiers):
        ob.modifiers.remove(m)
    me = ob.data
    M = np.array(ob.matrix_world)
    X = np.array([v.co[:] for v in me.vertices])
    X = (M @ np.c_[X, np.ones(len(X))].T).T[:, :3] * 100.0
    R = M[:3, :3] / np.cbrt(abs(np.linalg.det(M[:3, :3])) or 1.0)
    N = np.array([v.normal[:] for v in me.vertices]) @ R.T
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    names = [(s.name if s else "").lower() for s in me.materials]
    tris = [(tuple(p.vertices), p.material_index) for p in me.polygons]
    return X, N, tris, names


X0, N0, tris, names = load(a[0])
X1, N1, _, _ = load(a[1])
if len(X0) != len(X1):
    sys.exit("different vertex counts: not the same garment")
keep = {i for i, n in enumerate(names) if SLOT in n and "short" not in n}
F = [t for t, m in tris if m in keep]
V = sorted({i for f in F for i in f})
z = X1[V, 2]
zlo, zhi = np.percentile(z, 2), np.percentile(z, 98)
cx, cy = X1[V, 0].mean(), X1[V, 1].mean()


def where(p):
    h = (p[2] - zlo) / max(zhi - zlo, 1e-6)
    band = "hem" if h < 0.25 else "waist" if h < 0.5 else "chest" if h < 0.8 else "shoulders/collar"
    return band


turn = np.degrees(np.arccos(np.clip((N0[V] * N1[V]).sum(1), -1, 1)))
flip = [V[i] for i in np.where(turn > 90)[0]]
print(f"slot verts {len(V)}; normals turned > 90 deg: {len(flip)}; > 45: {int((turn > 45).sum())}")


def crossings(X):
    polys = [list(f) for f in F]
    bvh = BVHTree.FromPolygons(X.tolist(), polys)
    pairs = bvh.overlap(bvh)
    out = [(i, j) for i, j in pairs if i < j and not (set(polys[i]) & set(polys[j]))]
    return out, polys


c0, _ = crossings(X0)
c1, polys = crossings(X1)
print(f"wall crossings (intersecting non-adjacent triangles): original {len(c0)}, fitted {len(c1)}")
for name, idx in (("flipped verts", flip), ("crossings", [polys[i][0] for i, _ in c1])):
    if not idx:
        continue
    P = X1[idx]
    front = P[:, 1] < cy  # MetaHuman faces -Y in Unreal's export: front = smaller y
    bands = {}
    for p, fr in zip(P, front):
        k = f"{where(p)} {'front' if fr else 'back'} {'L' if p[0] > cx else 'R'}"
        bands[k] = bands.get(k, 0) + 1
    print(name, "by place:", dict(sorted(bands.items(), key=lambda kv: -kv[1])[:8]))
