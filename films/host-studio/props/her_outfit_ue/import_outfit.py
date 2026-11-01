"""Import her fitted outfit (props/out/her_top.fbx, her_trousers.fbx) onto her skeleton, and its cloth maps
(her_outfit_maps.py), from Saved/Import/her_outfit (pushed there by workstation.push_dir). Run with film-ue exec;
re-running replaces them."""
import os

import unreal
from fmbridge.ops import assets as A

SRC = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Import", "her_outfit")
DEST = "/Game/Host/Presenter_Outfit"
SKEL = "/MetaHumanCharacter/Female/Medium/NormalWeight/Body/metahuman_base_skel"
MESHES = {"her_top": "SKM_Presenter_Top", "her_trousers": "SKM_Presenter_Trousers"}


def import_skm(fbx, name):
    t = unreal.AssetImportTask()
    t.filename = os.path.join(SRC, fbx + ".fbx")
    t.destination_path, t.destination_name = DEST, name
    t.automated, t.replace_existing, t.save = True, True, True
    ui = unreal.FbxImportUI()
    ui.import_mesh, ui.import_as_skeletal = True, True
    ui.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    ui.skeleton = unreal.load_asset(SKEL)
    ui.import_materials, ui.import_textures, ui.import_animations = False, False, False
    ui.create_physics_asset = False
    sk = ui.skeletal_mesh_import_data
    sk.import_morph_targets = False
    sk.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    sk.update_skeleton_reference_pose = False
    sk.use_t0_as_reference_pose = False
    sk.convert_scene, sk.force_front_x_axis, sk.convert_scene_unit = True, False, False
    t.options = ui
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    m = unreal.load_asset(f"{DEST}/{name}")
    if not m:
        return {"imported": list(t.imported_object_paths), "error": "not loaded"}
    b = m.get_bounds()
    return {"imported": list(t.imported_object_paths),
            "skeleton": m.skeleton.get_path_name() if m.skeleton else None,
            "bounds": [[round(b.origin.x, 1), round(b.origin.y, 1), round(b.origin.z, 1)],
                       [round(b.box_extent.x, 1), round(b.box_extent.y, 1), round(b.box_extent.z, 1)]],
            "slots": [str(s.material_slot_name) for s in m.materials]}


out = {k: import_skm(k, v) for k, v in MESHES.items()}
texs = [os.path.join(SRC, f"T_Her{n}_{k}.png") for n in ("Rib", "Wool") for k in ("A", "N", "M")]
out["textures"] = A.import_files([p for p in texs if os.path.exists(p)], DEST)
result = out
