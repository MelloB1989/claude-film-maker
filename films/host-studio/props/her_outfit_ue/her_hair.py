"""Her hair's look, re-applied: studio.py's MI_K_HerHair{,_Cards,_Helmet} (children of the preset's
MI_WI_Hair_L_Straight_Hair*, hairMelanin 1.0, hairRedness 0.05: sleek black, even root to tip) on her Hair groom's
three slots. The preset's own hair reads with green/teal lengths in warm light (v2's reel hair tests a-h), and a
change to any of her instance components re-creates them (restore_leader.py, perf.py drive_faces/place): the override
is lost and the teal is back (round 3 preview, S16 f1217/f1277). Run with film-ue exec as the LAST step of any
re-place, before a presenter render. Fails loudly (no silent skip) if a parent or the groom is missing. Saves the
instances it makes or changes; the level is saved by the render (save_dirty).

    film-ue exec films/host-studio/props/her_outfit_ue/her_hair.py
"""
import unreal

GROOMS = "/Game/Host/Unpacked/Presenter/Grooms"
FOLDER = "/Game/Studio/Materials"  # studio.py's M
SCALARS = {"hairMelanin": 1.0, "hairRedness": 0.05}
EAL, MEL = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary

hair = next((c for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
             if a.get_actor_label() == "Presenter" for c in a.get_components_by_class(unreal.GroomComponent)
             if c.get_name() == "Hair"), None)
if hair is None:
    raise RuntimeError("her_hair: no Hair groom on the Presenter")
out, missing = {}, []
for i, suffix in enumerate(("", "_Cards", "_Helmet")):
    ppath = f"{GROOMS}/MI_WI_Hair_L_Straight_Hair{suffix}"
    parent = unreal.load_asset(ppath) if EAL.does_asset_exist(ppath) else None
    if parent is None:
        missing.append(ppath)
        continue
    name = f"MI_K_HerHair{suffix}"
    path = f"{FOLDER}/{name}"
    mi = unreal.load_asset(path) if EAL.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, FOLDER, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if mi.get_editor_property("parent") != parent:
        mi.set_editor_property("parent", parent)
    for k, v in SCALARS.items():
        MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
    EAL.save_asset(path)
    hair.set_material(i, mi)
    got = hair.get_material(i)
    out[i] = {"set": path, "now": got.get_path_name() if got else None,
              "melanin": MEL.get_material_instance_scalar_parameter_value(mi, "hairMelanin")}
if missing:
    raise RuntimeError(f"her_hair: preset parents missing on this project: {missing}; slots done: {out}")
bad = {i: r for i, r in out.items() if not (r["now"] or "").startswith(r["set"])}
if bad:
    raise RuntimeError(f"her_hair: the groom did not keep the instances: {bad}")
result = out
