"""Run studio.py's outfit block (between '# >>> outfit' and '# <<< outfit') on the open level's Presenter without
rebuilding the studio, then check that the top and trousers follow her body. Run from tools/ on the operator's Mac
through the bridge's run.sh:
    uv run python ../films/host-studio/props/her_outfit_ue/attach_outfit.py
"""
import json
import os
import textwrap

from filmtools.unreal import client

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.join(HERE, "..", "..", "unreal", "studio.py")
PRELUDE = '''
import unreal
from fmbridge.ops import level as L, look as K
M = "/Game/Studio/Materials"


def tex(folder, name):
    p = f"{folder}/{name}"
    return p if unreal.EditorAssetLibrary.does_asset_exist(p) else ""


def plain(name, color, roughness=0.6, metallic=0.0, specular=None):
    return K.material(f"MI_K_{name}", color, roughness=roughness, metallic=metallic, specular=specular, folder=M)
'''
CHECK = '''
comps = {c.get_name(): c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent)}
out = {"components": sorted(comps)}
for n in ("Top", "Trousers"):
    c = comps.get(n)
    if c is None:
        continue
    lead = c.get_editor_property("leader_pose_component")
    ac = c.get_editor_property("anim_class")
    out[n] = {"leader": lead.get_name() if lead else None, "anim_class": ac.get_name() if ac else None,
              "mode": str(c.get_editor_property("animation_mode")),
              "parent": c.get_attach_parent().get_name() if c.get_attach_parent() else None,
              "mesh": c.get_skeletal_mesh_asset().get_path_name() if c.get_skeletal_mesh_asset() else None,
              "materials": [m.get_name() if m else None for m in c.get_materials()],
              "same_as_body": [round((c.get_socket_location(b) - comps["Body"].get_socket_location(b)).length(), 3)
                               for b in ("hand_l", "head", "calf_r", "pelvis")]}
for lab in ("HerEarL", "HerEarR", "HerWatch"):
    try:
        rc = L.actor(lab).root_component
        out[lab] = rc.get_attach_parent().get_name() if rc.get_attach_parent() else None
    except ValueError:
        out[lab] = "missing"
result = out
'''


def main():
    src = open(STUDIO, encoding="utf-8").read()
    block = src[src.index("    # >>> outfit"):src.index("    # <<< outfit")]
    r = client.exec_code(PRELUDE + textwrap.dedent(block) + CHECK)
    if not r.get("ok"):
        raise SystemExit(r.get("stdout", "") + r.get("error", ""))
    print(json.dumps(r.get("result"), indent=1))


if __name__ == "__main__":
    main()
