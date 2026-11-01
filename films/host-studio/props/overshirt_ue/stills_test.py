"""Viewport stills of her in the overshirt (no Movie Render Queue): her idle on a scratch sequence, two cameras of
our own, everything put back as it was. Run from tools/ on the operator's Mac through the bridge's run.sh:
    uv run python ../films/host-studio/props/overshirt_ue/stills_test.py [frames...]
"""
import json
import sys

from filmtools.unreal import client

PROJECT = r"C:\UEProjects\HostStudio"
OUT = PROJECT + r"\Saved\Export\overshirt_stills"
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
SEQ = "/Game/Host/Presenter_Overshirt/SEQ_OvershirtTest"
CAMS = {  # her at the origin facing +X; +Y is her right
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
        out[lab] = L.actor(lab).is_temporarily_hidden_in_editor()
    except ValueError:
        pass
result = out
'''
SET = '''
from fmbridge.ops import level as L
for lab, hide in %r.items():
    try:
        a = L.actor(lab)
    except ValueError:
        continue
    a.set_is_temporarily_hidden_in_editor(hide)
result = True
'''


def ok(r):
    if not r.get("ok"):
        raise SystemExit(r.get("stdout", "") + r.get("error", ""))
    return r.get("result")


def main():
    frames = [int(x) for x in sys.argv[1:]] or [48]
    before = ok(client.exec_code(STATE % (LABELS,)))
    shots = []
    try:
        for name, (loc, at, focal) in CAMS.items():
            ok(client.op("look.camera", label=name, loc=loc, look_at=at, focal=focal, aperture=4.0,
                         filmback=[24.0, 30.0], pilot=False))
        ok(client.exec_code(SET % ({"Host": True, "Stool": True, "Presenter": False, "HerEarL": False,
                                    "HerEarR": False, "HerWatch": False},)))
        ok(client.op("seq.close"))
        ok(client.op("seq.shot", path=SEQ, actor_label="Presenter", anims={"Body": IDLE}, camera="OvershirtCamF",
                     seconds=max(frames) / 24 + 1))
        for f in frames:
            for cam in CAMS:
                p = rf"{OUT}\{cam}_{f}.png"
                ok(client.op("seq.still", path=SEQ, frame=f, camera=cam, out=p, width=1600, height=2000))
                shots.append(p)
    finally:
        client.op("seq.close")
        ok(client.exec_code(SET % (before,)))
        client.op("level.delete", labels=list(CAMS))
    print(json.dumps({"stills": shots, "restored": before}))


if __name__ == "__main__":
    main()
