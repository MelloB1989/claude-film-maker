"""Round 5b (agent-02): is the neck backstop's shrink live on the face he renders with? Compares the Face component's
mesh (after mh.build with the hidden face map) with a reference face mesh of the same topology from before the
assembly (REF: e.g. the unpacked SKM_..._FaceMesh), rest pose, vertex by vertex. Live: ~1000 verts moved inward,
up to SHRINK_CM (1.5), all of them low on the neck; dead: 0 moved (the build did not bake it, or the Face component
still points at an older mesh).

    film-ue exec -c "REF='/Game/.../SKM_Host_Op_FaceMesh'; exec(open('<tree>/films/host-studio/reel/r5/shrink_live.py').read())"
"""
import unreal

LABEL = globals().get("LABEL", "Host")
REF = globals().get("REF", "")
AU, MQ, LU = unreal.GeometryScript_AssetUtils, unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List
EAL = unreal.EditorAssetLibrary


def pick(res, cls):
    items = res if isinstance(res, tuple) else (res,)
    return next((x for x in items if type(x).__name__ == cls), items[0])


def dm_of(skm):
    dm = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_index", 0)
    AU.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
    return dm


def verts(dm):
    return list(LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList")))


def summary(d, P):
    """d: [(distance cm, vertex index)] sorted; P: the built face's positions."""
    moved = [(x, i) for x, i in d if x > 0.05]
    o = {"moved_gt_0.05cm": len(moved), "moved_gt_0.5cm": sum(1 for x, _ in d if x > 0.5), "max_cm": round(d[-1][0], 3)}
    if moved:
        zs = sorted(P[i].z for _, i in moved)
        o["moved_z_range_cm"] = [round(zs[0], 1), round(zs[-1], 1)]
        o["median_moved_cm"] = round(moved[len(moved) // 2][0], 3)
    return o


host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == LABEL)
comps = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
face = comps["Face"].get_skeletal_mesh_asset()
out = {"face_component_mesh": face.get_path_name(), "ref": REF}
if REF:
    fd, rd = dm_of(face), dm_of(EAL.load_asset(REF))
    A, B = verts(fd), verts(rd)
    out["verts"] = [len(A), len(B)]
    if len(A) == len(B):
        d = sorted(((a - b).length(), i) for i, (a, b) in enumerate(zip(A, B)))
        out["by_index"] = summary(d, A)
    # by SURFACE (vertex order free: the assembly may reorder the face's vertices; round 5b read 33762 "moved" by index):
    # each built vertex's distance to the nearest point of REF's surface. Live: ~1000 low on the neck up to SHRINK_CM;
    # the rest ~0. Everything moved by a similar amount: REF is in another place or pose
    SP = unreal.GeometryScript_MeshSpatial
    bvh = pick(SP.build_bvh_for_mesh(rd), "GeometryScriptDynamicMeshBVH")
    q = unreal.GeometryScriptSpatialQueryOptions()
    d = []
    for i, p in enumerate(A):
        r = pick(SP.find_nearest_point_on_mesh(rd, bvh, p, q), "GeometryScriptTrianglePoint")
        d.append(((p - r.get_editor_property("position")).length(), i))
    out["by_surface"] = summary(sorted(d), A)
result = out
