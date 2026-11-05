"""Read-only: export the other body mesh in his assembled folder (SKM_Host_BodyMesh, an earlier build) to
Saved/Export/his_outfit_alt, to see whether it is his body uncut."""
import os

import unreal

OUT = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Export", "his_outfit_alt")
os.makedirs(OUT, exist_ok=True)
m = unreal.load_asset("/Game/Host/Unpacked/Host/Body/SKM_Host_BodyMesh")
t = unreal.AssetExportTask()
t.object = m
t.filename = os.path.join(OUT, "body_alt.fbx")
t.automated, t.prompt, t.replace_identical = True, False, True
o = unreal.FbxExportOption()
o.ascii, o.level_of_detail, o.collision, o.export_morph_targets = False, False, False, False
t.options = o
result = {"ok": unreal.Exporter.run_asset_export_task(t), "size": os.path.getsize(t.filename),
          "skeleton": m.skeleton.get_path_name()}
