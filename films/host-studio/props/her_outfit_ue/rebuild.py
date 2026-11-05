"""Rebuild her MetaHuman without the default garment (tee + shorts), so her body is whole (MetaHuman removes the
faces a garment hides): a backup of the character first (/Game/Host/Presenter_F_v1), then the Outfits slot emptied
and the cinematic build into BP_Presenter. Run once with film-ue exec; her fitted outfit (props/her_outfit.py)
replaces the garment."""
import time

import unreal

EAL = unreal.EditorAssetLibrary
CHAR, BACKUP = "/Game/Host/Presenter_F", "/Game/Host/Presenter_F_v1"
out = {}
if not EAL.does_asset_exist(BACKUP):
    out["backup"] = bool(EAL.duplicate_asset(CHAR, BACKUP))
s = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
c = unreal.load_asset(CHAR)
if not s.is_object_added_for_editing(c):
    s.try_add_object_to_edit(c)
coll = c.get_editor_property("internal_collection")
inst = coll.get_editor_property("default_instance")
for slot in ("Outfits", "Top Garment", "Bottom Garment"):
    try:
        inst.set_single_slot_selection(slot, unreal.MetaHumanPaletteItemKey())
        out[slot] = "cleared"
    except Exception as e:
        out[slot] = str(e)
EAL.save_asset(CHAR)
p = unreal.MetaHumanCharacterEditorBuildParameters()
p.name_override = "Presenter"
t0 = time.time()
s.build_meta_human(c, p)
out["build_s"] = round(time.time() - t0, 1)
seen = {}
for q in EAL.list_assets("/Game/Host/Unpacked/Presenter", recursive=True, include_folder=False):
    d = EAL.find_asset_data(q)
    k = str(d.asset_class_path.asset_name)
    if k in ("Blueprint", "SkeletalMesh"):
        seen[q.split(".")[0]] = k
out["assembled"] = seen
her = [a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
       if a.get_actor_label() == "Presenter"]
if her:
    out["components"] = {x.get_name(): (x.get_skeletal_mesh_asset().get_path_name() if x.get_skeletal_mesh_asset() else None)
                         for x in her[0].get_components_by_class(unreal.SkeletalMeshComponent)}
result = out
