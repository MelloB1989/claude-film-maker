"""Round 7 (agent-05): import her waist refit (props/her_waist_r7.py --fit Top / --fit Trousers, on the box) as NEW
assets beside the originals, with the originals' materials slot for slot. Read-only on everything else; run with
film-ue exec on box B (the driver):

    film-ue exec -c "SRC='/srv/ue/fit/a05_r7'; exec(open('<tree>/films/host-studio/props/her_outfit_ue/import_r7_waist.py').read())"

Then setplan's GARMENT_SRC (already pointing at these) and `set.py --steps garments,dress,save` put them on her.
"""
import os

import unreal

SRC = globals().get("SRC", "/srv/ue/fit/a05_r7")
DEST = "/Game/Host/Presenter_Outfit"
SKEL = "/MetaHumanCharacter/Female/Medium/NormalWeight/Body/metahuman_base_skel"
MESHES = {  # fbx under SRC -> (new asset, the original whose materials it takes)
    "fit1_top/garment_fit_Top.fbx": ("SKM_Presenter_Top_R7W", "SKM_Presenter_Top"),
    "fit2_tr/garment_fit_Trousers.fbx": ("SKM_Presenter_Trousers_R7W", "SKM_Presenter_Trousers"),
}


def import_skm(fbx, name):
    t = unreal.AssetImportTask()
    t.filename = os.path.join(SRC, fbx)
    t.destination_path, t.destination_name = DEST, name
    t.automated, t.replace_existing, t.save = True, True, True
    ui = unreal.FbxImportUI()
    ui.import_mesh, ui.import_as_skeletal = True, True
    ui.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    ui.skeleton = unreal.load_asset(SKEL)
    ui.import_materials, ui.import_textures, ui.import_animations = False, False, False
    ui.create_physics_asset = False
    sk = ui.skeletal_mesh_import_data
    for k, v in dict(normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
                     update_skeleton_reference_pose=False, use_t0_as_reference_pose=False, convert_scene=True,
                     force_front_x_axis=False, convert_scene_unit=False).items():
        try:
            sk.set_editor_property(k, v)
        except Exception:
            pass
    t.options = ui
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    return unreal.load_asset(f"{DEST}/{name}")


out = {}
for fbx, (name, orig_name) in MESHES.items():
    if not os.path.exists(os.path.join(SRC, fbx)):
        out[name] = {"error": f"missing {os.path.join(SRC, fbx)}"}
        continue
    m = import_skm(fbx, name)
    orig = unreal.load_asset(f"{DEST}/{orig_name}")
    if not m or not orig:
        out[name] = {"error": "not loaded", "orig": bool(orig)}
        continue
    # by slot INDEX: the FBX round trip names every slot WorldGridMaterial*, and the struct copies m.materials hands
    # out ignore assignment, so each slot is a fresh SkeletalMaterial carrying the original's material and slot name
    # (r7: agent-06 found both imports on the grid material)
    if len(m.materials) != len(orig.materials):
        out[name] = {"error": f"{len(m.materials)} slots vs the original's {len(orig.materials)}"}
        continue
    mats, how = [], []
    for i, (s, o) in enumerate(zip(m.materials, orig.materials)):
        sm = unreal.SkeletalMaterial()
        sm.set_editor_property("material_interface", o.material_interface)
        sm.set_editor_property("material_slot_name", o.material_slot_name)
        try:
            sm.set_editor_property("imported_material_slot_name", o.material_slot_name)
        except Exception:
            pass
        mats.append(sm)
        how.append([str(s.material_slot_name), str(o.material_slot_name)])
    m.set_editor_property("materials", mats)
    unreal.EditorAssetLibrary.save_loaded_asset(m)
    b = m.get_bounds()
    out[name] = {"skeleton": m.skeleton.get_path_name() if m.skeleton else None, "slots": how,
                 "materials": [s.material_interface.get_path_name() if s.material_interface else None
                               for s in m.materials],
                 "bounds": [[round(b.origin.x, 1), round(b.origin.y, 1), round(b.origin.z, 1)],
                            [round(b.box_extent.x, 1), round(b.box_extent.y, 1), round(b.box_extent.z, 1)]]}
result = out
