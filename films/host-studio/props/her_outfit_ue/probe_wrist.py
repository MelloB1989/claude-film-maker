"""Read-only: her left wrist's frame and where HerWatch faces. The watch's screen (+Z) must point to the back of the
wrist (dorsal); round 2 aimed it along wrist_outer_l - wrist_inner_l, which reads as the side of the forearm. Reports
the dorsal direction two ways (forearm x knuckle line; away from the finger curl), the angle the watch's screen makes
with each, and which forearm bone sits nearest the wrist. Run with film-ue exec."""
import math

import unreal

from fmbridge.ops import level as L

her = L.actor("Presenter")
body_ = next(c for c in her.get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == "Body")
P = lambda b: body_.get_socket_location(b)  # noqa: E731
r = lambda v: [round(v.x, 2), round(v.y, 2), round(v.z, 2)]  # noqa: E731
names = ["lowerarm_l", "lowerarm_twist_01_l", "lowerarm_twist_02_l", "hand_l", "wrist_inner_l", "wrist_outer_l",
         "index_metacarpal_l", "pinky_metacarpal_l", "middle_metacarpal_l", "middle_01_l", "middle_02_l",
         "middle_03_l", "thumb_01_l"]
out = {"bones": {b: (r(P(b)) if body_.does_socket_exist(b) else None) for b in names}}
hand = P("hand_l")
fwd = (hand - P("lowerarm_l")).normal()
across = P("index_metacarpal_l") - P("pinky_metacarpal_l")  # ulnar -> radial
across = (across - fwd * across.dot(fwd)).normal()
dorsal_x = fwd.cross(across).normal()  # left arm, UE axes: forearm x radial = back of the hand
axis = (P("middle_metacarpal_l") - hand).normal()
tip = P("middle_03_l") - P("middle_metacarpal_l")
curl = tip - axis * tip.dot(axis)
curl = (curl - fwd * curl.dot(fwd))
dorsal_c = (curl * -1.0).normal() if curl.length() > 0.05 else None  # fingers curl to the palm
oo = P("wrist_outer_l") - P("wrist_inner_l")
old_up = (oo - fwd * oo.dot(fwd)).normal()
deg = lambda a, b: round(math.degrees(math.acos(max(-1.0, min(1.0, a.dot(b))))), 1)  # noqa: E731
out["fwd"], out["across"], out["dorsal_cross"] = r(fwd), r(across), r(dorsal_x)
out["dorsal_curl"] = r(dorsal_c) if dorsal_c else None
out["curl_cm"] = round(curl.length(), 2)
out["deg_cross_vs_curl"] = deg(dorsal_x, dorsal_c) if dorsal_c else None
out["deg_old_up_vs_dorsal"] = deg(old_up, dorsal_x)
out["wrist_width_cm"] = round((P("wrist_outer_l") - P("wrist_inner_l")).length(), 2)
out["nearest_twist_to_hand"] = {b: round((P(b) - hand).length(), 2) for b in ("lowerarm_twist_01_l",
                                                                              "lowerarm_twist_02_l")
                                if body_.does_socket_exist(b)}
try:
    w = L.actor("HerWatch")
    out["watch"] = {"at": r(w.get_actor_location()), "screen": r(w.get_actor_up_vector()),
                    "band_axis": r(w.get_actor_right_vector()),
                    "deg_screen_vs_dorsal": deg(w.get_actor_up_vector(), dorsal_x),
                    "deg_band_vs_forearm": deg(w.get_actor_right_vector(), fwd),
                    "from_hand_cm": round((w.get_actor_location() - hand).length(), 2),
                    "socket": str(w.root_component.get_attach_socket_name())}
except ValueError:
    out["watch"] = None
result = out
