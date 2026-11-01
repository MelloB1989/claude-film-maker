"""Import the overshirt (props/out/overshirt.fbx) onto her skeleton, and its twill maps, from Saved/Import/overshirt
(pushed there by workstation.push_dir). Run with film-ue exec; re-running replaces them."""
import os

import unreal
from fmbridge.ops import assets as A

EAL = unreal.EditorAssetLibrary
SRC = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Import", "overshirt")
DEST = "/Game/Host/Presenter_Overshirt"
NAME = "SKM_Presenter_Overshirt"
SKEL = "/MetaHumanCharacter/Female/Medium/NormalWeight/Body/metahuman_base_skel"

t = unreal.AssetImportTask()
t.filename = os.path.join(SRC, "overshirt.fbx")
t.destination_path, t.destination_name = DEST, NAME
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
texs = [os.path.join(SRC, f"T_OvershirtTwill_{k}.png") for k in ("A", "N", "M")]
tex_paths = A.import_files([p for p in texs if os.path.exists(p)], DEST)

m = unreal.load_asset(f"{DEST}/{NAME}")
out = {"imported": list(t.imported_object_paths), "textures": tex_paths}
if m:
    b = m.get_bounds()
    out["skeleton"] = m.skeleton.get_path_name() if m.skeleton else None
    out["bounds"] = [[b.origin.x, b.origin.y, b.origin.z], [b.box_extent.x, b.box_extent.y, b.box_extent.z]]
    out["slots"] = [str(s.material_slot_name) for s in m.materials]
    tee = unreal.load_asset("/Game/Host/Unpacked/Presenter/Clothing/Presenter_F_Outfits")
    if tee:
        tb = tee.get_bounds()
        out["tee_bounds"] = [[tb.origin.x, tb.origin.y, tb.origin.z], [tb.box_extent.x, tb.box_extent.y, tb.box_extent.z]]
result = out
