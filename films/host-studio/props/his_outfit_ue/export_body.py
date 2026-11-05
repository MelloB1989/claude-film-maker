"""Export his body, his default garment (tee + shorts), his face and the animations he plays in the reel to
Saved/Export/his_outfit, for fitting his trousers in Blender (props/his_outfit.py). Read-only on the project.
Run with film-ue exec."""
import os

import unreal

EAL = unreal.EditorAssetLibrary
OUT = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Export", "his_outfit")
os.makedirs(OUT, exist_ok=True)
host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == "Host")
comps = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
info = {"exported": {}, "out": OUT}

# the body animations the reel and the line sequences play on him (sections on any skeletal track)
played = {}
for sp in ("/Game/Reel/SEQ_Reel", "/Game/Studio/SEQ_Line1", "/Game/Studio/SEQ_Line2"):
    seq = unreal.load_asset(sp)
    if not seq:
        continue
    for b in seq.get_bindings():
        for t in b.get_tracks():
            if isinstance(t, unreal.MovieSceneSkeletalAnimationTrack):
                for s in t.get_sections():
                    a = s.get_editor_property("params").get_editor_property("animation")
                    if a:
                        played.setdefault(a.get_path_name().split(".")[0], []).append(f"{sp.split('/')[-1]}:{b.get_display_name()}")
info["played"] = played
idles = [p.split(".")[0] for p in EAL.list_assets("/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle",
                                                  recursive=True, include_folder=False)]
info["idles"] = idles

todo = [("body", comps["Body"].get_skeletal_mesh_asset()), ("face", comps["Face"].get_skeletal_mesh_asset()),
        ("garment", comps["SkeletalMesh"].get_skeletal_mesh_asset())]
male_idle = next((p for p in idles if "_m_" in p.lower() or "_mn" in p.lower() or "male" in p.lower().replace("female", "")), None)
if male_idle:
    todo.append(("idle", unreal.load_asset(male_idle)))
for p in played:
    a = unreal.load_asset(p)
    if a and a.get_class().get_name() == "AnimSequence":
        todo.append(("anim_" + p.split("/")[-1], a))
for name, asset in todo:
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
    info["exported"][name] = [asset.get_path_name(), ok,
                              os.path.getsize(t.filename) if os.path.exists(t.filename) else 0]
result = info
