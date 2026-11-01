"""Put her hoops and watch back on her bones (HerEarL/R through the lobes on FACIAL_*_Ear4, HerWatch on the left wrist on
lowerarm_twist_02_l), placed exactly as studio.py places them but from where her sockets are now, then attached so they
ride the bones. Run with film-ue exec on the open level (no studio rebuild); reports each one's distance from its
bone afterwards."""
import unreal

from fmbridge.ops import level as L

her = L.actor("Presenter")
comps = {c.get_name(): c for c in her.get_components_by_class(unreal.SkeletalMeshComponent)}
face, body_ = comps["Face"], comps["Body"]
rule = unreal.AttachmentRule.KEEP_WORLD
keep = unreal.DetachmentRule.KEEP_WORLD
out = {"mobility": {}}
for lab in ("HerEarL", "HerEarR", "HerWatch"):  # a Static root cannot ride a moving bone
    rc = L.actor(lab).root_component
    out["mobility"][lab] = str(rc.mobility)
    rc.set_mobility(unreal.ComponentMobility.MOVABLE)
for side, bone in (("L", "FACIAL_L_Ear4"), ("R", "FACIAL_R_Ear4")):
    lab = f"HerEar{side}"
    a = L.actor(lab)
    a.detach_from_actor(keep, keep, keep)
    p = face.get_socket_location(bone)
    inward = 0.25 if side == "L" else -0.25  # through the lobe, not on its surface (as studio.py)
    a.set_actor_location(unreal.Vector(p.x - 0.1, p.y + inward, p.z + 0.15), False, False)
    out[lab + "_ok"] = a.attach_to_component(face, bone, rule, rule, rule, False)
w = L.actor("HerWatch")
w.detach_from_actor(keep, keep, keep)
a_, b_ = body_.get_socket_location("lowerarm_twist_02_l"), body_.get_socket_location("hand_l")
fwd = (b_ - a_).normal()
o = body_.get_socket_location("wrist_outer_l") - body_.get_socket_location("wrist_inner_l")
up = (o - fwd * o.dot(fwd)).normal()
at = b_ - fwd * 3.6
w.set_actor_location(at, False, False)
w.set_actor_rotation(unreal.MathLibrary.make_rot_from_yz(fwd, up), False)
out["HerWatch_ok"] = w.attach_to_component(body_, "lowerarm_twist_02_l", rule, rule, rule, False)
for lab, comp, bone in (("HerEarL", face, "FACIAL_L_Ear4"), ("HerEarR", face, "FACIAL_R_Ear4"),
                        ("HerWatch", body_, "lowerarm_twist_02_l")):
    a = L.actor(lab)
    rc = a.root_component
    out[lab] = {"dist": round((a.get_actor_location() - comp.get_socket_location(bone)).length(), 2),
                "parent": rc.get_attach_parent().get_name() if rc.get_attach_parent() else None,
                "socket": str(rc.get_attach_socket_name())}
result = out
