"""Run studio.py's his outfit block (between '# >>> his outfit' and '# <<< his outfit') on the open level's Host without
rebuilding the studio, then check that the trousers follow his body and the shorts are cut out. Run from tools/ on the
operator's Mac through the bridge's run.sh:
    uv run python ../films/host-studio/props/his_outfit_ue/attach_outfit.py
(After agent-02's her_outfit_ue/attach_outfit.py.)
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
'''
CHECK = '''
comps = {c.get_name(): c for c in L.actor("Host").get_components_by_class(unreal.SkeletalMeshComponent)}
out = {"components": sorted(comps)}
c = comps.get("Trousers")
if c is not None:
    lead = c.get_editor_property("leader_pose_component")
    out["Trousers"] = {"leader": lead.get_name() if lead else None,
                       "parent": c.get_attach_parent().get_name() if c.get_attach_parent() else None,
                       "mesh": c.get_skeletal_mesh_asset().get_path_name() if c.get_skeletal_mesh_asset() else None,
                       "materials": [m.get_name() if m else None for m in c.get_materials()],
                       "same_as_body": [round((c.get_socket_location(b) - comps["Body"].get_socket_location(b)).length(), 3)
                                        for b in ("pelvis", "calf_r", "foot_l", "spine_02")]}
def ref(c, bone):  # a garment whose root carries a scale (bones in metres under a x100 root) collapses when posed
    t = c.get_ref_pose_transform(c.get_bone_index(bone))
    return [round(t.translation.x, 3), round(t.translation.y, 3), round(t.translation.z, 3),
            round(t.scale3d.x, 3)]


for n in ("Body", "Trousers", "SkeletalMesh"):
    if n in comps:
        out[n + "_ref"] = {b: ref(comps[n], b) for b in ("root", "pelvis", "calf_l")}
g = comps.get("SkeletalMesh")
out["garment"] = [f"{s}: {m.get_name() if m else None}" for s, m in zip(g.get_material_slot_names(), g.get_materials())]
result = out
'''


def main():
    src = open(STUDIO, encoding="utf-8").read()
    block = src[src.index("# >>> his outfit"):src.index("# <<< his outfit")]
    r = client.exec_code(PRELUDE + textwrap.dedent(block) + CHECK)
    if not r.get("ok"):
        raise SystemExit(r.get("stdout", "") + r.get("error", ""))
    print(json.dumps(r.get("result"), indent=1))


if __name__ == "__main__":
    main()
