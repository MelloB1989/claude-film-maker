"""Is her body in the level the one the outfit was fitted to (Saved/Export/her_outfit/body.fbx)? Its mesh's bounds,
LOD0 vertex count and the export's file time. Read-only. Run with film-ue exec."""
import os

import unreal

OUT = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Export", "her_outfit")
her = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
           if a.get_actor_label() == "Presenter")
body = next(c for c in her.get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == "Body")
m = body.get_skeletal_mesh_asset()
b = m.get_bounds()
lib = unreal.SkeletalMeshEditorSubsystem if hasattr(unreal, "SkeletalMeshEditorSubsystem") else None
out = {"mesh": m.get_path_name(), "bounds": [[round(b.origin.x, 2), round(b.origin.y, 2), round(b.origin.z, 2)],
                                            [round(b.box_extent.x, 2), round(b.box_extent.y, 2), round(b.box_extent.z, 2)]],
       "export": {f: os.path.getmtime(os.path.join(OUT, f)) for f in ("body.fbx",) if os.path.exists(os.path.join(OUT, f))}}
try:
    out["lod0_verts"] = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem).get_num_verts(m, 0)
except Exception as e:
    out["lod0_verts"] = str(e)
pkg = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir()) + m.get_path_name().split(".")[0][len("/Game/"):] + ".uasset"
out["uasset_mtime"] = os.path.getmtime(pkg) if os.path.exists(pkg) else pkg
for k in ("anim_class", "animation_mode"):
    try:
        v = body.get_editor_property(k)
        out[k] = v.get_name() if hasattr(v, "get_name") else str(v)
    except Exception as e:
        out[k] = str(e)
result = out
# the watch: its mesh's local extents (the band loop is narrow along the forearm, ~6-7 cm across it) and where its
# local axes point against her forearm (lowerarm_twist_02_l -> hand_l)
w = next((a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
          if a.get_actor_label() == "HerWatch"), None)
if w is not None:
    sm = w.get_components_by_class(unreal.StaticMeshComponent)[0]
    bb = sm.static_mesh.get_bounding_box()
    tf = w.get_actor_transform()
    fwd = (body.get_socket_location("hand_l") - body.get_socket_location("lowerarm_twist_02_l")).normal()
    out["watch"] = {"mesh": sm.static_mesh.get_path_name(),
                    "local_min": [round(v, 2) for v in (bb.min.x, bb.min.y, bb.min.z)],
                    "local_max": [round(v, 2) for v in (bb.max.x, bb.max.y, bb.max.z)],
                    "scale": [round(v, 3) for v in (tf.scale3d.x, tf.scale3d.y, tf.scale3d.z)],
                    "axis_dot_forearm": {k: round(v.dot(fwd), 2) for k, v in (("x", w.get_actor_forward_vector()),
                                         ("y", w.get_actor_right_vector()), ("z", w.get_actor_up_vector()))}}
