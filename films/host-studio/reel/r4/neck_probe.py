"""Round 4, read-only: does Host's FACE mesh (its lower neck, down to the clavicles) stand out through his tee? On the
posed meshes in the editor's current pose (Geometry Script, render LOD 0). Before the slim build, on cast_op4's
Host_Op: face verts under the collar line stood 0.4-2.3 cm out of the tee (the orange patch left of his neckline).
    film-ue exec films/host-studio/reel/r4/neck_probe.py           (scrub SEQ_Reel to a frame first to probe a pose)
Returns: under_collar: face verts more than 2 cm below the tee's collar top and within 6 cm of the tee: n, out (> 0.1 cm
outside it), max_out_cm; by_z: the same per cm band relative to neck_01; worst: [dx, dy, dz rel neck_01, out cm]. Pass:
out == 0 (a few verts within 0.2 cm are inflate's to cover).
"""
import unreal
from fmbridge.ops.mh.actor import _pick

SU, SP, MQ, LU = (unreal.GeometryScript_SceneUtils, unreal.GeometryScript_MeshSpatial,
                  unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List)
LABEL = globals().get("LABEL", "Host")
h = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
         if a.get_actor_label() == LABEL)
c = {x.get_name(): x for x in h.get_components_by_class(unreal.SkeletalMeshComponent)}
tee_c = c.get("SkeletalMesh") or next(x for n, x in c.items() if n not in ("Body", "Face", "Trousers"))
opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
lod = unreal.GeometryScriptMeshReadLOD()
lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
opts.set_editor_property("requested_lod", lod)


def copy(comp):
    dm = unreal.DynamicMesh()
    SU.copy_mesh_from_component(comp, dm, opts, True)
    return dm


def verts(dm):
    return LU.convert_vector_list_to_array(_pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList"))


tee, face = copy(tee_c), copy(c["Face"])
bvh = _pick(SP.build_bvh_for_mesh(tee), "GeometryScriptDynamicMeshBVH")
tv, fv = verts(tee), verts(face)
q = unreal.GeometryScriptSpatialQueryOptions()
neck = c["Body"].get_socket_location("neck_01")
collar_top = max(p.z for p in tv)
rows, worst, n, out, mx = {}, [], 0, 0, 0.0
for p in fv:
    if p.z > collar_top + 1.0:
        continue
    tp = _pick(SP.find_nearest_point_on_mesh(tee, bvh, p, q), "GeometryScriptTrianglePoint")
    if not tp.get_editor_property("valid"):
        continue
    d = p - tp.get_editor_property("position")
    if d.length() > 6.0:
        continue
    s = d.dot(_pick(MQ.get_triangle_face_normal(tee, tp.get_editor_property("triangle_id")), "Vector"))
    k = round(p.z - neck.z)
    r = rows.setdefault(k, [0, 0, 0.0])
    r[0] += 1
    if s > 0.1:
        r[1] += 1
        r[2] = max(r[2], round(s, 2))
    if p.z < collar_top - 2.0:
        n += 1
        if s > 0.1:
            out += 1
            mx = max(mx, s)
            worst.append([round(p.x - neck.x, 1), round(p.y - neck.y, 1), round(p.z - neck.z, 1), round(s, 2)])
worst.sort(key=lambda w: -w[3])
result = {"tee": tee_c.get_name(), "face_mesh": c["Face"].get_skeletal_mesh_asset().get_name(),
          "face_min_z_rel_neck": round(min(p.z for p in fv) - neck.z, 1),
          "collar_top_rel_neck": round(collar_top - neck.z, 1),
          "under_collar": {"n": n, "out": out, "max_out_cm": round(mx, 2)}, "pass": out == 0,
          "by_z [n, out, max out cm]": dict(sorted(rows.items())), "worst": worst[:10]}
