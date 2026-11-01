"""Viewport stills of her in the overshirt (no Movie Render Queue): her idle on a scratch sequence, two cameras of
our own, everything put back as it was. Run from tools/ on the operator's Mac through the bridge's run.sh:
    uv run python ../films/host-studio/props/overshirt_ue/stills_test.py [frames...]
"""
import json
import math
import sys

from filmtools.unreal import client

PROJECT = r"C:\UEProjects\HostStudio"
OUT = PROJECT + r"\Saved\Export\overshirt_stills"
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
SEQ = "/Game/Host/Presenter_Overshirt/SEQ_OvershirtTest"
CAMS = {  # relative to her: +X ahead of her, +Y her right, Z up (placed on her actual mark by WHERE)
    "OvershirtCamF": ([165, 0, 128], [0, 0, 122], 35.0),
    "OvershirtCamQ": ([118, -118, 132], [0, 0, 124], 35.0),
    "OvershirtCamC": ([62, -18, 140], [0, 0, 136], 50.0),
}
LABELS = ["Host", "Presenter", "HerEarL", "HerEarR", "HerWatch", "Stool"]
STATE = '''
from fmbridge.ops import level as L
out = {}
for lab in %r:
    try:
        a = L.actor(lab)
        out[lab] = [a.is_temporarily_hidden_in_editor(), a.get_editor_property("hidden")]
    except ValueError:
        pass
result = out
'''
LEADER = '''
import unreal
from fmbridge.ops import level as L
cs = {c.get_name(): c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent)}
cs["Overshirt"].set_leader_pose_component(cs["Body"] if %r else None)
result = True
'''
WHERE = '''
from fmbridge.ops import level as L
a = L.actor("Presenter")
p, r = a.get_actor_location(), a.get_actor_rotation()
result = [p.x, p.y, p.z, r.yaw]
'''
OPENSEQ = '''
import unreal
s = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
result = s.get_path_name() if s else ""
'''
REOPEN = '''
import unreal
LSE = unreal.LevelSequenceEditorBlueprintLibrary
LSE.open_level_sequence(unreal.load_asset(%r))
LSE.set_current_time(%d)
LSE.set_lock_camera_cut_to_viewport(%r)
result = True
'''
TIME = '''
import unreal
LSE = unreal.LevelSequenceEditorBlueprintLibrary
result = [LSE.get_current_time(), LSE.is_camera_cut_locked_to_viewport()]
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
    a.set_actor_hidden_in_game(game)
result = True
'''


def ok(r):
    if not r.get("ok"):
        raise SystemExit(r.get("stdout", "") + r.get("error", ""))
    return r.get("result")


def main():
    frames = [int(x) for x in sys.argv[1:] if x.isdigit()] or [48]
    noleader = "--noleader" in sys.argv  # diagnosis: the shirt in its own bind pose, not following her body
    cams = {k: v for k, v in CAMS.items() if not noleader or k == "OvershirtCamF"}
    before = ok(client.exec_code(STATE % (LABELS,)))
    was_open = ok(client.exec_code(OPENSEQ))  # someone else's sequence (the reel) goes back open as we found it
    was_time, was_lock = ok(client.exec_code(TIME)) if was_open else (0, False)
    px, py, pz, yaw = ok(client.exec_code(WHERE))
    c, sn = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))

    def place(v):  # her frame to the world: the MetaHuman faces the actor's +Y, her right is the actor's -X
        lx, ly = -v[1], v[0]
        return [px + c * lx - sn * ly, py + sn * lx + c * ly, pz + v[2]]
    shots = []
    try:
        if noleader:
            ok(client.exec_code(LEADER % (False,)))
        for name, (loc, at, focal) in cams.items():
            ok(client.op("look.camera", label=name, loc=place(loc), look_at=place(at), focal=focal, aperture=4.0,
                         filmback=[24.0, 30.0], pilot=False))
        ok(client.exec_code(SET % ({"Host": True, "Stool": True, "Presenter": False, "HerEarL": False,
                                    "HerEarR": False, "HerWatch": False},)))
        for cam in cams:  # the viewport follows the sequence's camera cut: one sequence per camera
            ok(client.op("seq.close"))
            ok(client.op("seq.shot", path=SEQ, actor_label="Presenter", anims={"Body": IDLE}, camera=cam,
                         seconds=max(frames) / 24 + 1))
            for f in frames:
                p = rf"{OUT}\{cam}_{f}.png"
                ok(client.op("seq.still", path=SEQ, frame=f, camera=cam, out=p, width=1600, height=2000))
                shots.append(p)
    finally:
        client.op("seq.close")
        if noleader:
            ok(client.exec_code(LEADER % (True,)))
        ok(client.exec_code(SET % (before,)))
        client.op("level.delete", labels=list(CAMS))
        if was_open:
            ok(client.exec_code(REOPEN % (was_open, int(was_time), bool(was_lock))))
    print(json.dumps({"stills": shots, "restored": before, "reopened": was_open}))


if __name__ == "__main__":
    main()
