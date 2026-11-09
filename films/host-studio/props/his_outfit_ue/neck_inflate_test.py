"""Compile test of neck_inflate.py's graph on SCRATCH copies (never on anything drawn): Host's tee master is
duplicated to /Game/FM/ClothOpTest, given the neckline term, recompiled, its stats read, then the folder is deleted.
    film-ue exec -c "CHECKOUT='<tree>'; exec(open(CHECKOUT + '/films/host-studio/props/his_outfit_ue/neck_inflate_test.py').read())"
Pass: ok True (vertex shader instructions > 0, the six FM_ parameters present)."""
import importlib.util
import os

import unreal

EAL, MEL = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
CHECKOUT = globals().get("CHECKOUT", os.getcwd())
spec = importlib.util.spec_from_file_location(
    "neck_inflate", os.path.join(CHECKOUT, "films/host-studio/props/his_outfit_ue/neck_inflate.py"))
ni = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ni)
h = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
         if a.get_actor_label() == "Host")
c = {x.get_name(): x for x in h.get_components_by_class(unreal.SkeletalMeshComponent)}
g = c.get("SkeletalMesh") or next(x for n, x in c.items() if n not in ("Body", "Face", "Trousers"))
mi = next(m for n, m in zip(g.get_material_slot_names(), g.get_materials()) if "shirt" in str(n).lower())
x = mi
while isinstance(x, unreal.MaterialInstance):
    x = x.get_editor_property("parent")
src = x.get_path_name().split(".")[0]
TEST = "/Game/FM/ClothOpTest"
dst = f"{TEST}/{src.rsplit('/', 1)[1]}_T"
out = {"worn": mi.get_name(), "master": src}
try:
    EAL.duplicate_asset(src, dst)
    m = unreal.load_asset(dst)
    had = "FM_Inflate" in [str(n) for n in MEL.get_scalar_parameter_names(m)]
    out["master_already_inflated"] = had
    if True:
        ni.add_neck_inflate(m)
        unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
        st = MEL.get_statistics(m)
        out["vs_instructions"] = int(st.num_vertex_shader_instructions)
        out["ps_instructions"] = int(st.num_pixel_shader_instructions)
        out["params"] = sorted(str(n) for n in MEL.get_scalar_parameter_names(m) if str(n).startswith("FM_"))
        out["ok"] = out["vs_instructions"] > 0 and len(out["params"]) == len(ni.PARAMS)
finally:
    EAL.delete_directory(TEST)
    out["cleaned"] = not EAL.does_directory_exist(TEST) or not EAL.list_assets(TEST)
result = out
