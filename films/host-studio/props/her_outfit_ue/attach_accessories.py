"""Put her hoops and watch back on her bones on the open level (no studio rebuild), as studio.py's
seat_her_accessories() does at the end of a build: HerEarL/R through the lobes on FACIAL_*_Ear4, HerWatch flat on the
back of her left wrist (band round the forearm, dial out) on lowerarm_twist_01_l. Run it LAST, after anything that
changes her components (import_overshirt.py, restore_leader.py, mh.cloth_inflate): those re-create her components and
leave what rode them at its bone with no offset. Run with film-ue exec; reports how the watch sits, then saves nothing
(L.save_level() when it reads ok)."""
import unreal

from fmbridge.ops import level as L

WATCH_BONE = "lowerarm_twist_01_l"
WATCH_UP_ARM = 3.6

her = L.actor("Presenter")
comps = {c.get_name(): c for c in her.get_components_by_class(unreal.SkeletalMeshComponent)}
face, body_ = comps["Face"], comps["Body"]
rule, keep = unreal.AttachmentRule.KEEP_WORLD, unreal.DetachmentRule.KEEP_WORLD
out = {}


def ride(lab):  # a Static root cannot ride a moving bone
    a = L.actor(lab)
    a.root_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    a.detach_from_actor(keep, keep, keep)
    return a


for side, bone in (("L", "FACIAL_L_Ear4"), ("R", "FACIAL_R_Ear4")):
    a = ride(f"HerEar{side}")
    p = face.get_socket_location(bone)
    inward = 0.25 if side == "L" else -0.25  # through the lobe, not on its surface (as studio.py)
    a.set_actor_location(unreal.Vector(p.x - 0.1, p.y + inward, p.z + 0.15), False, False)
    a.attach_to_component(face, bone, rule, rule, rule, False)
    out[f"HerEar{side}"] = round((a.get_actor_location() - p).length(), 2)

w = ride("HerWatch")
P = body_.get_socket_location
hand = P("hand_l")
fwd = (hand - P("lowerarm_l")).normal()
across = P("index_metacarpal_l") - P("pinky_metacarpal_l")
across = (across - fwd * across.dot(fwd)).normal()
back = fwd.cross(across).normal()  # the back of the wrist (left arm, UE axes)
at = hand - fwd * WATCH_UP_ARM
rot = unreal.MathLibrary.make_rot_from_yz(fwd, back)
w.set_actor_location_and_rotation(at, rot, False, False)
w.attach_to_component(body_, WATCH_BONE, rule, rule, rule, False)
w.set_actor_location_and_rotation(at, rot, False, False)
sm = w.static_mesh_component.static_mesh if hasattr(w, "static_mesh_component") else None
bb = sm.get_bounding_box() if sm else None
out["HerWatch"] = {"from_hand_cm": round((w.get_actor_location() - hand).length(), 2),
                   "band_along_forearm": round(w.get_actor_right_vector().dot(fwd), 3),
                   "dial_to_back_of_wrist": round(w.get_actor_up_vector().dot(back), 3),
                   "socket": str(w.root_component.get_attach_socket_name()),
                   "rel_loc": [round(v, 2) for v in (w.root_component.relative_location.x,
                                                     w.root_component.relative_location.y,
                                                     w.root_component.relative_location.z)],
                   # the mesh's own extents (cm): the loop is widest along X, the band narrowest along Y (the forearm)
                   "mesh_extent": [round(bb.max.x - bb.min.x, 2), round(bb.max.y - bb.min.y, 2),
                                   round(bb.max.z - bb.min.z, 2)] if bb else None}
h = out["HerWatch"]
h["ok"] = abs(h["from_hand_cm"] - WATCH_UP_ARM) < 0.5 and h["band_along_forearm"] > 0.98 and \
    h["dial_to_back_of_wrist"] > 0.98
result = out
