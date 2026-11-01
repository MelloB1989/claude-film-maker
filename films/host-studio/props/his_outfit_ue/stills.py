"""Viewport stills of him in his trousers (no Movie Render Queue): his reel body animation on a scratch sequence,
cameras of our own (front and 3/4 full length, a side, a waist close-up where the tee lies over the waistband), her
hidden and him keyed visible in that sequence only; everything put back as it was (the open sequence, its lock and
time; the cameras deleted). Run from tools/ on the operator's Mac through the bridge's run.sh:
    uv run python ../films/host-studio/props/his_outfit_ue/stills.py [--frames 300,700] [--only F,Q]
(After agent-02's her_outfit_ue/stills.py.)
"""
import argparse
import json

from filmtools.unreal import client

PROJECT = r"C:\UEProjects\HostStudio"
OUT = PROJECT + r"\Saved\Export\his_outfit_stills"
ANIM = "/Game/Reel/Perf/AS_reel_him_body"
SEQ = "/Game/Host/Host_Outfit/SEQ_HisOutfitTest"
CAMS = {  # him on his mark facing +X; +Y is his right. (loc, look_at, focal) relative to his actor's location
    "HisFitF": ([300, 0, 100], [0, 0, 98], 35.0),
    "HisFitQ": ([215, -210, 104], [0, 0, 98], 35.0),
    "HisFitS": ([0, 300, 100], [0, 0, 98], 35.0),
    "HisFitC": ([120, -45, 112], [0, 0, 100], 50.0),
}
STATE = '''
import unreal
from fmbridge.ops import level as L
p = L.actor("Host").get_actor_location()
cur = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
LSE = unreal.LevelSequenceEditorBlueprintLibrary
labels = [a.get_actor_label() for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()]
result = {"him": [p.x, p.y, p.z], "seq": cur.get_path_name().split(".")[0] if cur else "",
          "t": LSE.get_current_time() if cur else 0, "lock": LSE.is_camera_cut_locked_to_viewport() if cur else False,
          "labels": [x for x in ("Presenter", "HerEarL", "HerEarR", "HerWatch", "Stool") if x in labels]}
'''
BODY = '''
import unreal
from fmbridge.ops import level as L
c = next(c for c in L.actor("Host").get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == "Body")
c.set_visibility(%r, False)  # just the body's skin: the garments follow its pose all the same
result = True
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
    ap.add_argument("--frames", default="300,700")
    ap.add_argument("--only", default="")
    ap.add_argument("--body", default="on", help="on, or off to see the garments alone")
    ap.add_argument("--rest", action="store_true", help="his rest pose, no animation")
    a = ap.parse_args()
    frames = [int(x) for x in a.frames.split(",")]
    st = ok(client.exec_code(STATE))
    him = st["him"]
    tag = ("_rest" if a.rest else "") + ("_nobody" if a.body == "off" else "")
    cams = {k: v for k, v in CAMS.items() if not a.only or k[-1] in a.only.split(",")}
    shots, made = [], []
    try:
        if a.body == "off":
            ok(client.exec_code(BODY % (False,)))
        for name, (loc, at, focal) in cams.items():
            ok(client.op("look.camera", label=name, loc=add(him, loc), look_at=add(him, at), focal=focal,
                         aperture=5.6, filmback=[24.0, 30.0], pilot=False))
            made.append(name)
        ok(client.op("seq.close"))
        secs = max(frames) / 24 + 1
        for cam in cams:
            ok(client.op("seq.shot", path=SEQ, actor_label="Host", anims={} if a.rest else {"Body": ANIM},
                         camera=cam, seconds=secs))
            ok(client.op("seq.key_visible", path=SEQ, label="Host", keys=[[0, True]], attached=True))
            for lab in st["labels"]:
                ok(client.op("seq.key_visible", path=SEQ, label=lab, keys=[[0, False]]))
            for f in frames:
                p = rf"{OUT}\{cam}_{f}{tag}.png"
                ok(client.op("seq.still", path=SEQ, frame=f, camera=cam, out=p, width=1600, height=2000))
                shots.append(p)
    finally:
        client.op("seq.close")
        client.exec_code(BODY % (True,))
        if st.get("seq"):  # put back the sequence that was open (the reel), locked to its cut as before
            client.exec_code(REOPEN % (st["seq"], st["lock"], st["t"]))
        if made:
            client.op("level.delete", labels=sorted(set(made)))
    print(json.dumps({"stills": shots, "reopened": st.get("seq")}))


if __name__ == "__main__":
    main()
