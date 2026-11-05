"""Export her face mesh (LOD0: the neck the collar sits on) and the idle the stills play, to Saved/Export/overshirt2."""
import os
import unreal

OUT = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Export", "overshirt2")
os.makedirs(OUT, exist_ok=True)
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
info = {}
her = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
           if a.get_actor_label() == "Presenter")
face = next(c for c in her.get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == "Face")
for asset, name in ((face.get_skeletal_mesh_asset(), "face"), (unreal.load_asset(IDLE), "idle")):
    t = unreal.AssetExportTask()
    t.object = asset
    t.filename = os.path.join(OUT, name + ".fbx")
    t.automated, t.prompt, t.replace_identical = True, False, True
    o = unreal.FbxExportOption()
    o.ascii, o.level_of_detail, o.collision, o.export_morph_targets = False, False, False, False
    o.map_skeletal_motion_to_root = False
    t.options = o
    ok = unreal.Exporter.run_asset_export_task(t)
    info[name] = [asset.get_path_name(), ok, os.path.getsize(t.filename) if os.path.exists(t.filename) else 0]
info["idle_skeleton"] = unreal.load_asset(IDLE).get_editor_property("skeleton").get_path_name()
info["idle_len"] = unreal.load_asset(IDLE).get_editor_property("sequence_length")
result = info
