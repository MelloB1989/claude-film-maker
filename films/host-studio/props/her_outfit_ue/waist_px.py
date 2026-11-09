"""Round 7 (agent-05), read-only: where her waist is, for the 1:1 waist crops. Run with film-ue exec on box B (the
driver) right after the stills, with SEQ_Explain_Her open at the stills' frame (so her Body holds that pose):

    film-ue exec -c "OUT='/srv/ue/explainer/review/r7waist2/waist_px.json'; exec(open('<tree>/films/host-studio/props/her_outfit_ue/waist_px.py').read())"

Writes {camera: camera_info} and her Body's bone points (pelvis, spine_01, spine_02, thighs) in world cm to OUT;
crop_waist.py (on the box) projects them and cuts the crops. Nothing in the level changes.
"""
import json

import unreal
from fmbridge.ops import view as V

OUT = globals().get("OUT", "/srv/ue/explainer/review/r7waist2/waist_px.json")
CAMS = ["CAM_WIDE", "CAM_MCU_L", "CAM_MCU", "CAM_CU"]
BONES = ["pelvis", "spine_01", "spine_02", "spine_03", "thigh_l", "thigh_r"]

her = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
           if a.get_actor_label() == "Presenter")
body = next(c for c in her.get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == "Body")
pts = {}
for b in BONES:
    p = body.get_socket_location(b)
    pts[b] = [round(p.x, 2), round(p.y, 2), round(p.z, 2)]
cams = {}
for c in CAMS:
    try:
        info = V.camera_info(camera=c)
        info.pop("post", None)
        cams[c] = info
    except Exception as e:  # a missing camera is reported, not fatal
        cams[c] = {"error": str(e)}
out = {"bones": pts, "cameras": cams,
       "seated": pts["pelvis"][2] < 80.0}   # standing her pelvis is ~94 cm: then the sequence was not evaluated
json.dump(out, open(OUT, "w"), indent=1)
result = out
