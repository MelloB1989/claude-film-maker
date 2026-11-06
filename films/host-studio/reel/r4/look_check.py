"""Read-only: is Host_Op's round-4 look on the restored box (numbers only)? In the editor, with Studio open:

    film-ue exec films/host-studio/reel/r4/look_check.py

Checks the placed Host (grooms worn, no beard, hair colour, TRASH_) and the character asset (skin, iris, the S3
sculpt by its face fingerprint and the nose tip's place among the landmarks). `ok` is True when all hold; `fix` lists
what to re-run for each that does not. Expected values: operator_mh.py's ROUND 4 header.
"""
import importlib

import unreal

K = importlib.import_module("fmbridge.ops.mh._core")
G_ = importlib.import_module("fmbridge.ops.groom")
CHAR = "/Game/Host/Host_Op"
WANT_GROOMS = {"Hair": "Hair_S_SideSweptFringe", "Eyebrows": "Eyebrows_M_SlightArch", "Mustache": "Mustache_S_Full",
               "Beard": None}
FACE_S3 = "136163de2077"  # Host_Op's Face tag after the S3 sculpt (r4 05:26 UTC)
R = {"checks": {}, "fix": []}


def check(name, ok, got, fix):
    R["checks"][name] = {"ok": bool(ok), "got": got}
    if not ok:
        R["fix"].append(fix)


host = [x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
        if x.get_actor_label() == "Host"]
check("host_is_op", host and "BP_Host_Op" in host[0].get_class().get_name(),
      host[0].get_class().get_name() if host else None, "host_swap.py HOST='op' (+ --swap-set NECK_CM=2.5)")
if host:
    h = host[0]
    worn = {}
    for c in h.get_components_by_class(unreal.GroomComponent):
        a = c.get_editor_property("groom_asset")
        worn[c.get_name()] = a.get_name() if a else None
    for slot, want in WANT_GROOMS.items():
        got = next((v for k, v in worn.items() if k.lower().startswith(slot.lower())), None)
        check("groom_" + slot, got == want, got, "look_apply.py with the round-4 picks (operator_mh.py header)")
    trash = [c.get_name() for c in h.get_components_by_class(unreal.ActorComponent) if c.get_name().startswith("TRASH_")]
    check("no_trash", not trash, trash, "respawn: host_swap.py HOST='op'")
    hair = [c for c in h.get_components_by_class(unreal.GroomComponent) if c.get_name().lower().startswith("hair")]
    mel = None
    if hair:
        for m in hair[0].get_materials():
            v = G_._get_scalar(m, "hairMelanin") if m is not None else None
            if v is not None:
                mel = round(v, 3)
                break
    check("hair_melanin", mel is not None and abs(mel - 1.0) < 0.02, mel,
          "film-ue op groom.set label=Host melanin=1.0 redness=0.08 (per instance: lost unless the level was saved)")
c = K.char(CHAR)
sk = K.plain(c.get_editor_property("skin_settings")).get("skin", {})
check("skin_uv", abs(sk.get("u", 0) - 0.30) < 0.01 and abs(sk.get("v", 0) - 0.45) < 0.01,
      [sk.get("u"), sk.get("v")], "look_apply.py --skin 0.30:0.45 (textures + build)")
eye = K.plain(c.get_editor_property("eyes_settings")).get("eye_left", {}).get("iris", {})
check("iris_uv", abs(eye.get("primary_color_u", 0) - 0.92) < 0.01 and abs(eye.get("primary_color_v", 0) - 0.12) < 0.01,
      [eye.get("primary_color_u"), eye.get("primary_color_v")], "look_apply.py --iris 0.92:0.12")
face = (K.get_tag(c, "Face") or "")[:12]
check("sculpt_S3_tag", face == FACE_S3, face, "look_apply.py --sculpt S3 (r4/look/sculpt.json)")
p = [(q.x, q.y, q.z) for q in (K.sub().get_face_landmarks(c) or [])]
if len(p) > 76:  # the nose tip (13) ~4.65 cm before the cheekbones (72/76) after S3; ~4.0 before it
    back = round(((p[72][1] + p[76][1]) / 2) - p[13][1], 2)
    check("sculpt_S3_tip", back > 4.4, back, "look_apply.py --sculpt S3")
R["ok"] = not R["fix"]
result = R
