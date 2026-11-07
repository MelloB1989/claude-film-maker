"""Round 6 (agent-02, the orchestrator's (B)(2) for HER neckline band): fix the Top's neckline EDGE WALL on a NEW
asset. No vertex moves. Which knob follows from mid_diag.py's frames (white base colour clears it = texture/UV;
flat normal or no AO clears it = shading) and uv_probe.py (wall texel density vs the fabric).

The wall = the shell's fold rim in the top ZONE_CM of the Top at rest (every corner's span of face normals >=
SPAN_DEG: the thickness between the outer and the inner face; uv_probe.py reads the same set).

  MODE uv:      each wall triangle gets UVs EXTENDED from the fabric next to it: corner i takes the UV of its nearest
                fabric vertex j plus J_j (p_i - p_j), J_j = the dUV/dpos of a fabric triangle at j. The rib then runs
                over the wall at the fabric's own density instead of one stretched groove.
  MODE normals: each wall corner's normal = the area-weighted normal of the fabric around its nearest fabric vertex:
                the wall shades like the outer face it belongs to (tangents recomputed from them).
  MODE both.

    film-ue exec -c "TREE='<tree>'; MODE='uv'; DEST='/Game/Host/Presenter_Outfit/SKM_Presenter_Top_Edge1'; exec(open('<tree>/films/host-studio/reel/r6/edge_fix.py').read())"

Then swap DEST onto Presenter's Top component (as the Overshirt RW2; materials as worn) and render MCU f29 + CU.
Read-back: positions identical (max diff 0), vertex count kept, wall triangles changed / total."""
import importlib.util
import math
import os

import unreal

SRC = globals().get("SRC", "/Game/Host/Presenter_Outfit/SKM_Presenter_Top")
DEST = globals()["DEST"]
MODE = globals().get("MODE", "uv")
SPAN_DEG = float(globals().get("SPAN_DEG", 70.0))
ZONE_CM = float(globals().get("ZONE_CM", 30.0))
spec = importlib.util.spec_from_file_location("scoop_fit", os.path.join(globals()["TREE"],
                                                                        "films/host-studio/reel/r6/scoop_fit.py"))
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)
AU, MQ, LU, EAL = (unreal.GeometryScript_AssetUtils, unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List,
                   unreal.EditorAssetLibrary)


def pick(res, cls):
    items = res if isinstance(res, tuple) else (res,)
    return next((x for x in items if type(x).__name__ == cls), items[0])


def asset_dm(skm):
    dm = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_index", 0)
    AU.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
    return dm


def positions(dm):
    return [(p.x, p.y, p.z) for p in LU.convert_vector_list_to_array(
        pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList"))]


def tri_uvs(dm, t):
    res = getattr(MQ, "get_triangle_u_vs", None) or getattr(MQ, "get_triangle_uvs")
    r = res(dm, 0, t)
    return [(q.x, q.y) for q in (r if isinstance(r, tuple) else (r,)) if type(q).__name__ == "Vector2D"][:3]


if EAL.does_asset_exist(DEST):
    raise RuntimeError(f"{DEST} exists: pass a new DEST (never overwrite a rendered asset)")
src = unreal.load_asset(SRC)
dup = EAL.duplicate_asset(SRC, DEST)
dm = asset_dm(dup)
V = positions(dm)
T, tids = [], []
for t in range(MQ.get_num_triangle_ids(dm)):
    iv = pick(MQ.get_triangle_indices(dm, t), "IntVector")
    if iv.x >= 0:
        T.append((int(iv.x), int(iv.y), int(iv.z)))
        tids.append(t)
K = sf.weld_keys(V)
fnrm, span = sf.normals_and_span(T, V, K)
zmax = max(p[2] for p in V)
wall = [k for k, tri in enumerate(T) if all(span.get(K[i], 0.0) >= SPAN_DEG for i in tri)
        and min(V[i][2] for i in tri) >= zmax - ZONE_CM]
wallset = set(wall)
wallv = {i for k in wall for i in T[k]}
# fabric vertices near the zone, each with one fabric triangle (for J) and the fabric normal around it
fab_tri_of, fab_n = {}, {}
for k, tri in enumerate(T):
    if k in wallset or min(V[i][2] for i in tri) < zmax - ZONE_CM - 5.0:
        continue
    for i in tri:
        if span.get(K[i], 0.0) < SPAN_DEG:
            fab_tri_of.setdefault(i, k)
fab = list(fab_tri_of)
if not wall or not fab:
    raise RuntimeError(f"wall {len(wall)} tris, fabric {len(fab)} verts: nothing to do (SPAN_DEG/ZONE_CM?)")


def nearest_fab(p):
    return min(fab, key=lambda j: (V[j][0] - p[0]) ** 2 + (V[j][1] - p[1]) ** 2 + (V[j][2] - p[2]) ** 2)


def jac(k):
    """dUV/dpos of triangle k as two 3-vectors (gu, gv), from its corners (least squares in its plane)."""
    a, b, c = (V[i] for i in T[k])
    uv = tri_uvs(dm, tids[k])
    e1 = [b[i] - a[i] for i in range(3)]
    e2 = [c[i] - a[i] for i in range(3)]
    d1 = (uv[1][0] - uv[0][0], uv[1][1] - uv[0][1])
    d2 = (uv[2][0] - uv[0][0], uv[2][1] - uv[0][1])
    g11 = sum(x * x for x in e1)
    g12 = sum(x * y for x, y in zip(e1, e2))
    g22 = sum(x * x for x in e2)
    det = g11 * g22 - g12 * g12
    if abs(det) < 1e-12:
        return None
    out = []
    for d in range(2):
        # grad = alpha e1 + beta e2 with grad.e1 = d1[d], grad.e2 = d2[d]
        al = (d1[d] * g22 - d2[d] * g12) / det
        be = (d2[d] * g11 - d1[d] * g12) / det
        out.append([al * e1[i] + be * e2[i] for i in range(3)])
    return out


def uv_at(j):
    k = fab_tri_of[j]
    uv = tri_uvs(dm, tids[k])
    return uv[T[k].index(j)]


changed = {"uv": 0, "normals": 0}
near = {i: nearest_fab(V[i]) for i in wallv}
if MODE in ("uv", "both"):
    UVL = unreal.GeometryScript_UVs
    J = {}
    for k in wall:
        corners = []
        for i in T[k]:
            j = near[i]
            if j not in J:
                J[j] = jac(fab_tri_of[j])
            u0 = uv_at(j)
            g = J[j]
            dp = [V[i][d] - V[j][d] for d in range(3)]
            corners.append(unreal.Vector2D(u0[0] + (sum(a * b for a, b in zip(g[0], dp)) if g else 0.0),
                                           u0[1] + (sum(a * b for a, b in zip(g[1], dp)) if g else 0.0)))
        tri = unreal.GeometryScriptUVTriangle()
        tri.set_editor_property("uv0", corners[0])
        tri.set_editor_property("uv1", corners[1])
        tri.set_editor_property("uv2", corners[2])
        UVL.set_mesh_triangle_uvs(dm, 0, tids[k], tri)
        changed["uv"] += 1
if MODE in ("normals", "both"):
    NL = unreal.GeometryScript_Normals
    for k in wall:
        vs = []
        for i in T[k]:
            n = fnrm.get(K[near[i]], (0.0, 0.0, 1.0))
            vs.append(unreal.Vector(*n))
        tri = unreal.GeometryScriptTriangle()
        for name, v in zip(("vector0", "vector1", "vector2"), vs):
            tri.set_editor_property(name, v)
        NL.set_mesh_triangle_normals(dm, tids[k], tri)
        changed["normals"] += 1
opts = unreal.GeometryScriptCopyMeshToAssetOptions()
for key, val in (("enable_recompute_normals", False), ("enable_recompute_tangents", MODE in ("normals", "both")),
                 ("enable_remove_degenerates", False), ("use_original_vertex_order", True),
                 ("replace_materials", False)):
    try:
        opts.set_editor_property(key, val)
    except Exception:  # noqa: BLE001
        pass
lod = unreal.GeometryScriptMeshWriteLOD()
lod.set_editor_property("lod_index", 0)
AU.copy_mesh_to_skeletal_mesh(dm, dup, opts, lod)
EAL.save_asset(DEST)
back, orig = positions(asset_dm(dup)), positions(asset_dm(src))
dpos = max((math.dist(a, b) for a, b in zip(back, orig)), default=0.0) if len(back) == len(orig) else None
result = {"dest": DEST, "src": SRC, "mode": MODE, "wall_tris": len(wall), "tris": len(T), "changed": changed,
          "verts": [len(back), len(orig)], "positions_max_diff_cm": round(dpos, 6) if dpos is not None else "count changed",
          "wall_z": [round(min(V[i][2] for i in wallv), 1), round(max(V[i][2] for i in wallv), 1)], "zmax": round(zmax, 1)}
