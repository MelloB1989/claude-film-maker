"""Round 6, K1 (agent-02): what the face CULL removed, proven on the built face. Every vertex of REF (his unpacked,
uncut face mesh, same rest pose) is looked up on the face his Face component renders now (by surface): gone =
nearer than 0.05 cm to nothing within GONE_CM. Expected after the chest-flange cull: a few hundred to ~2000 gone, ALL
low (z under the collar line, ~140-150 cm in rest), none on the lips/eyes/teeth/ears; and the remaining verts unmoved
(kept_moved_gt_0.05cm 0: no shrink). Anything gone high up = the mask hit another section sharing UV 0: STOP.

    film-ue exec -c "REF='/Game/Host/Snap/SKM_Host_Op_FaceMesh_r5'; exec(open('<tree>/films/host-studio/reel/r6/cull_live.py').read())"
"""
import unreal

LABEL = globals().get("LABEL", "Host")
REF = globals().get("REF", "/Game/Host/Snap/SKM_Host_Op_FaceMesh_r5")
GONE_CM = float(globals().get("GONE_CM", 0.5))
AU, MQ, LU, SP = (unreal.GeometryScript_AssetUtils, unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List,
                  unreal.GeometryScript_MeshSpatial)


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
    return list(LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(dm, True), "GeometryScriptVectorList")))


def near(dm, pts):
    bvh = pick(SP.build_bvh_for_mesh(dm), "GeometryScriptDynamicMeshBVH")
    q = unreal.GeometryScriptSpatialQueryOptions()
    return [(p - pick(SP.find_nearest_point_on_mesh(dm, bvh, p, q), "GeometryScriptTrianglePoint")
             .get_editor_property("position")).length() for p in pts]


host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == LABEL)
comps = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
built, ref = dm_of(comps["Face"].get_skeletal_mesh_asset()), dm_of(unreal.EditorAssetLibrary.load_asset(REF))
B, R = verts(built), verts(ref)
gone = [p for p, d in zip(R, near(built, R)) if d > GONE_CM]
kept_moved = sum(1 for d in near(ref, B) if d > 0.05)
zs = sorted(p.z for p in gone)
result = {"built_verts": len(B), "ref_verts": len(R), "gone": len(gone),
          "gone_z_cm": [round(zs[0], 1), round(zs[len(zs) // 2], 1), round(zs[-1], 1)] if zs else None,
          "kept_moved_gt_0.05cm": kept_moved}
