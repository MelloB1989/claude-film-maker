"""Round 6 (agent-02): are her Top's neckline EDGE-WALL UVs collapsed? READ-ONLY (the asset, no actor, no change).

Her Top's material tiles a rib knit 50x over the mesh UVs. If the triangles of the shell's fold rim (the thickness
wall between the outer and inner face, span of face normals >= SPAN_DEG) have (near) zero UV area, they sample one
line of the rib, a dark groove or a light rib, as a FLAT band with hard edges: the orchestrator's look at test30 f29.

Per triangle: texel density = UV area / 3D area (UV0). Reported: the median over the flat fabric, and over the rim
wall in the top ZONE_CM of the mesh (the neckline at rest; arms/hem are lower), as percentiles and the share of wall
triangles below 10 % of the fabric's density.

    film-ue exec -c "TREE='<tree>'; exec(open('<tree>/films/host-studio/reel/r6/uv_probe.py').read())"
"""
import importlib.util
import math
import os

import unreal

MESH = globals().get("MESH", "/Game/Host/Presenter_Outfit/SKM_Presenter_Top")
SPAN_DEG = float(globals().get("SPAN_DEG", 70.0))
ZONE_CM = float(globals().get("ZONE_CM", 30.0))
here = globals()["TREE"]  # the checkout on the box (its helpers come from scoop_fit.py there)
spec = importlib.util.spec_from_file_location("scoop_fit", os.path.join(here, "films/host-studio/reel/r6/scoop_fit.py"))
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)

AU, MQ, LU = unreal.GeometryScript_AssetUtils, unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List


def pick(res, cls):
    items = res if isinstance(res, tuple) else (res,)
    return next((x for x in items if type(x).__name__ == cls), items[0])


skm = unreal.load_asset(MESH)
dm = unreal.DynamicMesh()
lod = unreal.GeometryScriptMeshReadLOD()
lod.set_editor_property("lod_index", 0)
AU.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
V = [(p.x, p.y, p.z) for p in LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(dm, False),
                                                                    "GeometryScriptVectorList"))]
nt = MQ.get_num_triangle_ids(dm)
T, tids = [], []
for t in range(nt):
    iv = MQ.get_triangle_indices(dm, t)
    iv = pick(iv, "IntVector")
    if iv.x < 0:
        continue
    T.append((int(iv.x), int(iv.y), int(iv.z)))
    tids.append(t)
K = sf.weld_keys(V)
_, span = sf.normals_and_span(T, V, K)
zmax = max(p[2] for p in V)
uvfn = getattr(MQ, "get_triangle_u_vs", None) or getattr(MQ, "get_triangle_uvs")


def area3(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return 0.5 * math.sqrt(sum(x * x for x in n))


fab, wall = [], []
for t, tri in zip(tids, T):
    pa, pb, pc = (V[i] for i in tri)
    a3 = area3(pa, pb, pc)
    if a3 < 1e-8:
        continue
    res = uvfn(dm, 0, t)
    uvs = [x for x in (res if isinstance(res, tuple) else (res,)) if type(x).__name__ == "Vector2D"]
    if len(uvs) < 3:
        continue
    (u1, v1), (u2, v2), (u3, v3) = ((q.x, q.y) for q in uvs[:3])
    auv = 0.5 * abs((u2 - u1) * (v3 - v1) - (u3 - u1) * (v2 - v1))
    dens = auv / a3
    is_wall = all(span.get(K[i], 0.0) >= SPAN_DEG for i in tri)
    if is_wall and min(p[2] for p in (pa, pb, pc)) >= zmax - ZONE_CM:
        wall.append(dens)
    elif not is_wall:
        fab.append(dens)
fab.sort()
wall.sort()


def pct(x, q):
    return x[int(q * (len(x) - 1))] if x else None


f50 = pct(fab, 0.5)
result = {"mesh": MESH, "tris": len(T), "fabric_n": len(fab), "fabric_density_p50": f50,
          "wall_n": len(wall), "wall_density": [pct(wall, q) for q in (0.1, 0.5, 0.9)],
          "wall_below_10pct_of_fabric": round(sum(1 for d in wall if f50 and d < 0.1 * f50) / max(1, len(wall)), 3),
          "wall_over_fabric_p50": round(pct(wall, 0.5) / f50, 4) if wall and f50 else None}
