"""Round 7 (agent-02, for agent-05's waist refit): write her POSED meshes at the current frame as OBJ, world cm,
UE axes (X fwd, Y right, Z up; no conversion), positions + triangles only. READ-ONLY on the level. The files stay ON
THE BOX (presenter data: private, never off the box).

    (scrub the sequence to F+1 then F, as qa.clip)
    film-ue exec -c "OUT='/srv/ue/fit/her_r7/posed_f1080'; exec(open('<tree>/films/host-studio/reel/r7/export_posed.py').read())"

COMPS: component name -> file stem (default Body, Trousers, Top). Each OBJ is the component's render LOD0 as posed now
(copy_mesh_from_component, the same copy garment_measure reads), including the level's garment cuts.
"""
import json
import os

import unreal

OUT = globals()["OUT"]
LABEL = globals().get("LABEL", "Presenter")
COMPS = globals().get("COMPS", {"Body": "body", "Trousers": "trousers", "Top": "top"})
MQ, LU, SU = unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List, unreal.GeometryScript_SceneUtils


def pick(res, cls):
    items = res if isinstance(res, tuple) else (res,)
    return next((x for x in items if type(x).__name__ == cls), items[0])


host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == LABEL)
cs = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
os.makedirs(OUT, exist_ok=True)
result = {"out": OUT, "files": {}}
for name, stem in COMPS.items():
    c = cs[name]
    opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
    lod.set_editor_property("lod_index", 0)
    opts.set_editor_property("requested_lod", lod)
    dm = unreal.DynamicMesh()
    SU.copy_mesh_from_component(c, dm, opts, True)
    P = LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList"))
    T = [(int(t.x), int(t.y), int(t.z)) for t in LU.convert_triangle_list_to_array(
        pick(MQ.get_all_triangle_indices(dm, False), "GeometryScriptTriangleList")) if t.x >= 0]
    path = os.path.join(OUT, f"{stem}.obj")
    with open(path, "w") as fh:
        fh.write(f"# {LABEL}.{name} {c.get_skeletal_mesh_asset().get_path_name()} posed, world cm, UE axes\n")
        fh.writelines(f"v {p.x:.4f} {p.y:.4f} {p.z:.4f}\n" for p in P)
        fh.writelines(f"f {a + 1} {b + 1} {d + 1}\n" for a, b, d in T)
    result["files"][name] = {"path": path, "verts": len(P), "tris": len(T),
                             "mesh": c.get_skeletal_mesh_asset().get_path_name()}
bones = {b: c.get_socket_location(b) for c in (cs["Body"],) for b in ("pelvis", "spine_03", "thigh_l", "thigh_r")}
result["bones"] = {k: [round(v.x, 3), round(v.y, 3), round(v.z, 3)] for k, v in bones.items()}
with open(os.path.join(OUT, "meta.json"), "w") as fh:
    json.dump(result, fh)
