"""Export her rebuilt, uncut body (with its skeleton) and her face (LOD0) to Saved/Export/her_outfit, for fitting her
outfit in Blender (props/her_outfit.py). Run with film-ue exec after the rebuild without the default garment."""
import os

import unreal

EAL = unreal.EditorAssetLibrary
OUT = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Export", "her_outfit")
os.makedirs(OUT, exist_ok=True)
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
her = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
           if a.get_actor_label() == "Presenter")
comps = {c.get_name(): c for c in her.get_components_by_class(unreal.SkeletalMeshComponent)}
info = {"components": {n: (c.get_skeletal_mesh_asset().get_path_name() if c.get_skeletal_mesh_asset() else None)
                       for n, c in comps.items()}, "exported": {}}
for name, asset in (("body", comps["Body"].get_skeletal_mesh_asset()), ("face", comps["Face"].get_skeletal_mesh_asset()),
                    ("idle", unreal.load_asset(IDLE))):
    t = unreal.AssetExportTask()
    t.object = asset
    t.filename = os.path.join(OUT, name + ".fbx")
    t.automated, t.prompt, t.replace_identical = True, False, True
    o = unreal.FbxExportOption()
    o.ascii, o.level_of_detail, o.collision, o.export_morph_targets = False, False, False, False
    o.vertex_color = True
    o.map_skeletal_motion_to_root = False
    t.options = o
    ok = unreal.Exporter.run_asset_export_task(t)
    info["exported"][name] = [asset.get_path_name(), ok, os.path.getsize(t.filename) if os.path.exists(t.filename) else 0]
info["out"] = OUT
result = info
