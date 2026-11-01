"""Run studio.py's overshirt block (between its '# >>> overshirt' and '# <<< overshirt' markers) on the open level's
Presenter, without rebuilding the studio, then check that it follows her body. Run with film-ue exec."""
import os
import textwrap

import unreal
from fmbridge.ops import level as L, look as K

M = "/Game/Studio/Materials"


def tex(folder, name):
    p = f"{folder}/{name}"
    return p if unreal.EditorAssetLibrary.does_asset_exist(p) else ""


def plain(name, color, roughness=0.6, metallic=0.0, specular=None):
    return K.material(f"MI_K_{name}", color, roughness=roughness, metallic=metallic, specular=specular, folder=M)


here = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Import", "overshirt")
src = open(os.path.join(here, "studio.py"), encoding="utf-8").read()
block = src[src.index("    # >>> overshirt"):src.index("    # <<< overshirt")]
exec(textwrap.dedent(block), globals())

comps = {c.get_name(): c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent)}
c = comps.get("Overshirt")
lead = c.get_editor_property("leader_pose_component") if c else None
result = {"components": sorted(comps), "leader": lead.get_name() if lead else None,
          "parent": c.get_attach_parent().get_name() if c and c.get_attach_parent() else None,
          "mesh": c.get_skeletal_mesh_asset().get_path_name() if c else None,
          "materials": [m.get_name() if m else None for m in c.get_materials()] if c else None,
          "same_as_body": [round((c.get_socket_location(b) - comps["Body"].get_socket_location(b)).length(), 3)
                           for b in ("hand_l", "head", "lowerarm_r")] if c else None}
