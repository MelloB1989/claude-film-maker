"""Read-only: his body mesh and the animations in /Game/Host/Anim (and what the level sequences play on Host)."""
import unreal

EAL = unreal.EditorAssetLibrary
host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == "Host")
comps = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
out = {"body": comps["Body"].get_skeletal_mesh_asset().get_path_name(),
       "body_anim_mode": str(comps["Body"].get_editor_property("animation_mode"))}
try:
    out["body_anim"] = str(comps["Body"].get_editor_property("animation_data").get_editor_property("anim_to_play"))
except Exception as e:
    out["body_anim_err"] = str(e)
anims = {}
for p in EAL.list_assets("/Game/Host/Anim", recursive=True, include_folder=False):
    d = EAL.find_asset_data(p)
    anims[p.split(".")[0]] = str(d.asset_class_path.asset_name)
out["anims"] = anims
seqs = {}
for p in EAL.list_assets("/Game", recursive=True, include_folder=False):
    if "/SEQ_" in p or "/Seq" in p:
        d = EAL.find_asset_data(p)
        if str(d.asset_class_path.asset_name) == "LevelSequence":
            seqs[p.split(".")[0]] = 1
out["seqs"] = sorted(seqs)[:60]
result = out
