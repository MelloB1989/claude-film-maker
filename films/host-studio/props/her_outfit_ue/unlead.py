"""Top and Trousers off leader pose (their bind pose, as before the leader fix): while their reference root carries
x100 they vanish when posed. Run with film-ue exec; nothing saved."""
import unreal

from fmbridge.ops import level as L

out = {}
for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent):
    if c.get_name() in ("Top", "Trousers"):
        c.set_leader_pose_component(None)
    lead = c.get_editor_property("leader_pose_component")
    out[c.get_name()] = lead.get_name() if lead else None
result = out
