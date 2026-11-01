"""Read-only: where her accessories are and what they ride (HerEarL/R, HerWatch), and whether the bones they use
exist on her rebuilt body and face. Run with film-ue exec."""
import unreal

from fmbridge.ops import level as L

her = L.actor("Presenter")
comps = {c.get_name(): c for c in her.get_components_by_class(unreal.SkeletalMeshComponent)}
out = {"components": {n: (c.get_skeletal_mesh_asset().get_path_name() if c.get_skeletal_mesh_asset() else None)
                      for n, c in comps.items()},
       "her": [round(v, 1) for v in (her.get_actor_location().x, her.get_actor_location().y, her.get_actor_location().z)]}
bones = {"Body": ["lowerarm_twist_02_l", "hand_l", "wrist_outer_l", "wrist_inner_l", "lowerarm_l"],
         "Face": ["FACIAL_L_Ear4", "FACIAL_R_Ear4", "head"]}
for cn, names in bones.items():
    c = comps.get(cn)
    if c is None:
        continue
    out[cn] = {}
    for b in names:
        p = c.get_socket_location(b)
        out[cn][b] = {"exists": bool(c.does_socket_exist(b)), "at": [round(p.x, 1), round(p.y, 1), round(p.z, 1)]}
for lab in ("HerEarL", "HerEarR", "HerWatch"):
    try:
        a = L.actor(lab)
    except ValueError:
        out[lab] = None
        continue
    p = a.get_actor_location()
    parent = a.get_attach_parent_actor()
    rc = a.root_component
    out[lab] = {"at": [round(p.x, 1), round(p.y, 1), round(p.z, 1)],
                "parent_actor": parent.get_actor_label() if parent else None,
                "parent_comp": rc.get_attach_parent().get_name() if rc and rc.get_attach_parent() else None,
                "socket": str(rc.get_attach_socket_name()) if rc else None}
result = out
