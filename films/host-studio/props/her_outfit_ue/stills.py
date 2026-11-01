"""Viewport stills of her in her fitted outfit (no Movie Render Queue): her idle on a scratch sequence, cameras of our
own (front, 3/4, side full length, a waist-up close, close-ups of the watch and the left hoop aimed at where they
are in that frame), with and without agent-05's overshirt; everything put back as it was. Also measures how far
each accessory is from the bone it should ride. Run from tools/ on the operator's Mac through the bridge's run.sh:
    uv run python ../films/host-studio/props/her_outfit_ue/stills.py [--frames 48] [--shirt on,off] [--only F,Q]
"""
import argparse
import json

from filmtools.unreal import client

PROJECT = r"C:\UEProjects\HostStudio"
OUT = PROJECT + r"\Saved\Export\her_outfit_stills"
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
SEQ = "/Game/Host/Presenter_Outfit/SEQ_OutfitTest"
CAMS = {  # her on her mark facing +X; +Y is her right. (loc, look_at, focal) relative to her actor's location
    "HerFitF": ([265, 0, 96], [0, 0, 94], 35.0),
    "HerFitQ": ([190, -185, 100], [0, 0, 94], 35.0),
    "HerFitS": ([0, 265, 96], [0, 0, 94], 35.0),
    "HerFitC": ([105, -30, 124], [0, 0, 116], 50.0),
}
LABELS = ["Host", "Presenter", "HerEarL", "HerEarR", "HerWatch", "Stool"]
STATE = '''
import unreal
from fmbridge.ops import level as L
out = {}
for lab in %r:
    try:
        a = L.actor(lab)
        out[lab] = [a.is_temporarily_hidden_in_editor(), a.get_editor_property("hidden")]
    except ValueError:
        pass
p = L.actor("Presenter").get_actor_location()
cur = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
LSE = unreal.LevelSequenceEditorBlueprintLibrary
result = {"hidden": out, "her": [p.x, p.y, p.z], "seq": cur.get_path_name().split(".")[0] if cur else "",
          "t": LSE.get_current_time() if cur else 0, "lock": LSE.is_camera_cut_locked_to_viewport() if cur else False}
'''
SET = '''
from fmbridge.ops import level as L
for lab, hide in %r.items():
    try:
        a = L.actor(lab)
    except ValueError:
        continue
    ed, game = hide if isinstance(hide, list) else (hide, hide)
    a.set_is_temporarily_hidden_in_editor(ed)
    a.set_actor_hidden_in_game(game)  # a high-res screenshot draws as the game would
result = True
'''
SHIRT = '''
import unreal
from fmbridge.ops import level as L
c = next((c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent)
          if c.get_name() == "Overshirt"), None)
if c is not None:
    c.set_visibility(%r)
result = c is not None
'''
WHERE = '''
import unreal
from fmbridge.ops import level as L
comps = {c.get_name(): c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent)}
def v(p):
    return [round(p.x, 2), round(p.y, 2), round(p.z, 2)]
out = {}
for lab, comp, bone in (("HerWatch", "Body", "lowerarm_twist_02_l"), ("HerEarL", "Face", "FACIAL_L_Ear4"),
                        ("HerEarR", "Face", "FACIAL_R_Ear4")):
    try:
        a = L.actor(lab)
    except ValueError:
        continue
    p = a.get_actor_location()
    b = comps[comp].get_socket_location(bone)
    out[lab] = {"at": v(p), "bone": v(b), "dist": round((p - b).length(), 2)}
out["hand_l"] = v(comps["Body"].get_socket_location("hand_l"))
result = out
'''
REOPEN = '''
import unreal
LSE = unreal.LevelSequenceEditorBlueprintLibrary
LSE.open_level_sequence(unreal.load_asset(%r))
LSE.set_lock_camera_cut_to_viewport(%r)
LSE.set_current_time(%r)
result = True
'''


def ok(r):
    if not r.get("ok"):
        raise SystemExit(r.get("stdout", "") + r.get("error", ""))
    return r.get("result")


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", default="48")
    ap.add_argument("--shirt", default="off,on")
    ap.add_argument("--only", default="")
    ap.add_argument("--close", default="watch,ear")
    a = ap.parse_args()
    frames = [int(x) for x in a.frames.split(",")]
    st = ok(client.exec_code(STATE % (LABELS,)))
    before, her = st["hidden"], st["her"]
    cams = {k: v for k, v in CAMS.items() if not a.only or k[-1] in a.only.split(",")}
    shots, where, made = [], {}, []
    try:
        for name, (loc, at, focal) in cams.items():
            ok(client.op("look.camera", label=name, loc=add(her, loc), look_at=add(her, at), focal=focal,
                         aperture=4.0, filmback=[24.0, 30.0], pilot=False))
            made.append(name)
        ok(client.exec_code(SET % ({"Host": True, "Stool": True, "Presenter": False, "HerEarL": False,
                                    "HerEarR": False, "HerWatch": False},)))
        ok(client.op("seq.close"))
        secs = max(frames) / 24 + 1
        for f in frames:
            # the still goes through the sequence's camera cut: one shot per camera
            ok(client.op("seq.shot", path=SEQ, actor_label="Presenter", anims={"Body": IDLE},
                         camera=next(iter(cams), "HerFitF"), seconds=secs))
            ok(client.op("seq.scrub", path=SEQ, frame=f))
            w = ok(client.exec_code(WHERE))
            where[f] = w
            close = {}
            if "watch" in a.close and "HerWatch" in w:
                p = w["HerWatch"]["at"]
                close["HerWatchC"] = (add(p, [26, -16, 8]), p, 85.0)
            if "ear" in a.close and "HerEarL" in w:
                p = w["HerEarL"]["at"]
                close["HerEarLC"] = (add(p, [14, -24, 2]), p, 85.0)
            for name, (loc, at, focal) in close.items():
                ok(client.op("look.camera", label=name, loc=loc, look_at=at, focal=focal, aperture=5.6,
                             filmback=[24.0, 24.0], pilot=False))
                made.append(name)
            for cam in list(cams) + list(close):
                ok(client.op("seq.shot", path=SEQ, actor_label="Presenter", anims={"Body": IDLE}, camera=cam,
                             seconds=secs))
                for shirt in a.shirt.split(","):
                    if cam in close and shirt == "on":
                        continue
                    ok(client.exec_code(SHIRT % (shirt == "on",)))
                    p = rf"{OUT}\{cam}_{f}_shirt{shirt}.png"
                    wh = (1600, 1600) if cam in close else (1600, 2000)
                    ok(client.op("seq.still", path=SEQ, frame=f, camera=cam, out=p, width=wh[0], height=wh[1]))
                    shots.append(p)
    finally:
        client.op("seq.close")
        if st.get("seq"):  # put back the sequence that was open (the reel), locked to its cut as before
            client.exec_code(REOPEN % (st["seq"], st["lock"], st["t"]))
        client.exec_code(SHIRT % (True,))
        ok(client.exec_code(SET % (before,)))
        if made:
            client.op("level.delete", labels=sorted(set(made)))
    print(json.dumps({"stills": shots, "where": where, "restored": before, "reopened": st.get("seq")}))


if __name__ == "__main__":
    main()
