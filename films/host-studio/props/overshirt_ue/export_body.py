"""Export her reference body (and the worn tee, for fitting) to FBX in Saved/Export/overshirt (run with film-ue exec)."""
import os
import unreal

EAL = unreal.EditorAssetLibrary
OUT = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Export", "overshirt")
os.makedirs(OUT, exist_ok=True)
found = {}
for root in ("/Game/Host/Unpacked/Presenter", "/Game/Host/Presenter_F"):
    if EAL.does_directory_exist(root):
        for p in EAL.list_assets(root, recursive=True):
            d = unreal.EditorAssetLibrary.find_asset_data(p)
            if str(d.asset_class_path.asset_name) in ("SkeletalMesh", "Skeleton"):
                found[p.split(".")[0]] = str(d.asset_class_path.asset_name)

info = {"found": found, "exported": {}, "components": {}}
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    if a.get_actor_label() == "Presenter":
        for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
            m = c.get_skeletal_mesh_asset()
            t = c.get_relative_transform()
            info["components"][c.get_name()] = {
                "mesh": m.get_path_name() if m else None,
                "parent": c.get_attach_parent().get_name() if c.get_attach_parent() else None,
                "rel_loc": [t.translation.x, t.translation.y, t.translation.z],
                "rel_rot": [t.rotation.rotator().roll, t.rotation.rotator().pitch, t.rotation.rotator().yaw],
                "skeleton": m.skeleton.get_path_name() if m and m.skeleton else None,
                "leader": (c.get_editor_property("leader_pose_component").get_name()
                           if c.get_editor_property("leader_pose_component") else None),
                "anim_mode": str(c.get_editor_property("animation_mode")),
                "anim_class": str(c.get_editor_property("anim_class")),
                "materials": [str(n) for n in c.get_material_slot_names()],
            }
        info["actor_loc"] = [a.get_actor_location().x, a.get_actor_location().y, a.get_actor_location().z]
        info["actor_yaw"] = a.get_actor_rotation().yaw

want = [p for p, k in found.items() if k == "SkeletalMesh"
        and any(s in p.rsplit("/", 1)[1].lower() for s in ("body", "shirt", "top", "tee"))]
for comp in info["components"].values():
    if comp["mesh"]:
        p = comp["mesh"].split(".")[0]
        if p not in want and "face" not in p.rsplit("/", 1)[1].lower():
            want.append(p)
for p in want:
    asset = unreal.load_asset(p)
    t = unreal.AssetExportTask()
    t.object = asset
    t.filename = os.path.join(OUT, p.rsplit("/", 1)[1] + ".fbx")
    t.automated, t.prompt, t.replace_identical = True, False, True
    o = unreal.FbxExportOption()
    o.ascii = False
    o.level_of_detail = False
    o.collision = False
    o.export_morph_targets = False
    o.vertex_color = True
    o.map_skeletal_motion_to_root = False
    t.options = o
    ok = unreal.Exporter.run_asset_export_task(t)
    info["exported"][p] = [ok, t.filename, os.path.getsize(t.filename) if os.path.exists(t.filename) else 0]
info["out"] = OUT
info["anims"] = [p.split(".")[0] for p in EAL.list_assets("/Game/Host", recursive=True)
                 if str(EAL.find_asset_data(p).asset_class_path.asset_name) == "AnimSequence"][:80]
result = info
