"""Read-only: how her MetaHuman is built and assembled (character, palette, the assembled folder, the BP's meshes)."""
import unreal

EAL = unreal.EditorAssetLibrary
info = {}
for root in ("/Game/Host",):
    seen = {}
    for p in EAL.list_assets(root, recursive=True, include_folder=False):
        d = EAL.find_asset_data(p)
        k = str(d.asset_class_path.asset_name)
        if k in ("MetaHumanCharacter", "Blueprint", "SkeletalMesh", "Skeleton", "MetaHumanCollection"):
            seen[p.split(".")[0]] = k
    info["assets"] = seen
s = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
c = unreal.load_asset("/Game/Host/Presenter_F")
coll = c.get_editor_property("internal_collection")
info["slots"] = [str(x) for x in coll.get_slot_names()]
try:
    info["items"] = [str(k) for k in coll.get_all_item_keys()]
except Exception as e:
    info["items_err"] = str(e)
inst = coll.get_editor_property("default_instance")
try:
    info["selections"] = [str(x) for x in inst.get_editor_property("slot_selections")]
except Exception as e:
    info["sel_err"] = str(e)
try:
    info["pipeline"] = str(coll.get_editor_property("pipeline"))
except Exception as e:
    info["pipe_err"] = str(e)
try:
    info["body_constraints"] = {str(x.name): round(x.target_measurement, 1) for x in s.get_body_constraints(c, True)
                                if x.is_active}
except Exception as e:
    info["bc_err"] = str(e)
info["mh_sub_methods"] = [m for m in dir(s) if not m.startswith("_") and any(w in m for w in ("body", "mesh", "export", "build", "preview"))]
result = info
