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


def verts(skm):
    dm = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_index", 0)
    AU.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
    return list(LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList")))


host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == LABEL)
comps = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
face = comps["Face"].get_skeletal_mesh_asset()
out = {"face_component_mesh": face.get_path_name(), "ref": REF}
if REF:
    A, B = verts(face), verts(EAL.load_asset(REF))
    out["verts"] = [len(A), len(B)]
    if len(A) == len(B):
        d = sorted(((a - b).length(), i) for i, (a, b) in enumerate(zip(A, B)))
        moved = [(x, i) for x, i in d if x > 0.05]
        out["moved_gt_0.05cm"] = len(moved)
        out["max_cm"] = round(d[-1][0], 3)
        if moved:
            zs = sorted(A[i].z for _, i in moved)
            out["moved_z_range_cm"] = [round(zs[0], 1), round(zs[-1], 1)]
            out["median_moved_cm"] = round(moved[len(moved) // 2][0], 3)
    else:
        out["note"] = "different vertex counts: REF is not this face's topology (pick the unpacked FaceMesh)"
result = out
