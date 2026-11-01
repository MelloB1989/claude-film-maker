"""The presenters' performances for the reel (PLAN.md §5 "The presenters' animation", task R4), on the Unreal workstation
through the bridge: each presenter's voice solved to a face (the whole of their screen time in one solve, so blinks,
breaths and the listening face between lines are continuous; the lines in another mood solved alone and spliced in),
silent beats written on the face's curves (his head down then up to the lens, the hand-off turn, nods, smiles), face
and body made one skeleton, the eyes locked on each shot's lens or on the partner.

    cd tools && uv run python ../films/host-studio/reel/perf.py push            # the WAVs to the workstation
    cd tools && uv run python ../films/host-studio/reel/perf.py solve --only him # one solve per call (see SOLVES)
    cd tools && uv run python ../films/host-studio/reel/perf.py compose         # splice, beats -> AS_reel_<who>_face
    cd tools && uv run python ../films/host-studio/reel/perf.py stage           # Test_ sequences, cameras, marks
    cd tools && uv run python ../films/host-studio/reel/perf.py sync|gaze|stills [--who him]
    cd tools && uv run python ../films/host-studio/reel/perf.py place --seq /Game/Reel/SEQ_Reel   # for R7

The work happens in one test sequence per presenter (`Test_agent-03_Him`/`_Her`, frame 0 = the master frame its
performance starts on, the one actor in it, test cameras keyed like the reel's), because the bake ops sample a sequence
from its first frame and bind one actor. What comes out is two animations per presenter, `AS_reel_<who>_face` and
`AS_reel_<who>_body`, timed to the master: `place` puts them on SEQ_Reel as single sections at START[who].
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from shots import EYES_HER, EYES_HIM, FPS, FULL_FRAME, MARK_HER, MARK_HIM, SHOTS  # noqa: E402
from vo import OUT as VO, SR  # noqa: E402

from filmtools.unreal import client, workstation as ws  # noqa: E402
from filmtools.wav import read_wav, write_wav  # noqa: E402

ROOT = HERE.parents[2]
OUT = ROOT / "out" / "host-studio" / "reel" / "perf"
PROJECT = r"C:\UEProjects\HostStudio"
IMPORT = rf"{PROJECT}\Saved\Import\reel"
SPEECH = "/Game/Speech"
ANIM = "/Game/Reel/Perf"
ME = "agent-03"
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
FACE_MESH = {"him": "/Game/Host/Unpacked/Host/Face/SKM_Host_Trey_FaceMesh",
             "her": "/Game/Host/Unpacked/Presenter/Face/SKM_Presenter_F_FaceMesh"}
LABEL = {"him": "Host", "her": "Presenter"}
MARK = {"him": MARK_HIM, "her": MARK_HER}
EYES = {"him": EYES_HIM, "her": EYES_HER}
# Each presenter's performance runs from the first shot they are in to the end of the reel (master frames).
START = {"him": 840, "her": 1080}
END = 1560
# The body idle: both presenters play the engine's idle; her copy starts 17 s in, so the two never sway in step.
IDLE_OFFSET = {"him": 0.0, "her": 17.0}

# The solves: each presenter's whole stem in their base mood, and the lines whose mood differs (PLAN.md §2) alone.
SOLVES = {
    "him": {"wav": "stem_him", "who": "him", "mood": "CONFIDENCE", "intensity": 0.8},
    "her": {"wav": "stem_her", "who": "her", "mood": "CONFIDENCE", "intensity": 0.9},
    "L2": {"wav": "L2", "who": "him", "mood": "HAPPINESS", "intensity": 0.6},
    "L4a": {"wav": "L4a", "who": "him", "mood": "HAPPINESS", "intensity": 0.7},
    "L4b": {"wav": "L4b", "who": "her", "mood": "HAPPINESS", "intensity": 0.7},
}


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def cues() -> dict:
    return json.loads((VO / "cues.json").read_text())["lines"]


def anim_name(key: str) -> str:
    return f"reel_{key}"


# ---------------------------------------------------------------------------------------------------- audio

def stems() -> list[Path]:
    """Each presenter's VO stem cut to their performance window (START .. END), the audio the base solve hears."""
    made = []
    for who in ("him", "her"):
        x, sr = read_wav(VO / f"vo_{who}.wav")
        y = x[START[who] * sr // FPS:END * sr // FPS]
        y = y + np.random.default_rng(7).normal(0, 10 ** (-72 / 20), len(y)).astype(np.float32)  # a room-tone floor
        p = OUT / "wav" / f"stem_{who}.wav"
        write_wav(p, y, sr)
        made.append(p)
    return made


def push() -> list:
    out = []
    for p in stems() + [VO / f"{k}.wav" for k in cues()]:
        out.append(client.push(str(p), rf"{IMPORT}\{p.name}"))
    return out


def solve(key: str) -> dict:
    s = SOLVES[key]
    return ok(client.op("speech.to_face", wav=rf"{IMPORT}\{s['wav']}.wav", name=anim_name(key),
                        face_mesh=FACE_MESH[s["who"]], mood=s["mood"], intensity=s["intensity"], timeout=1800))



# ---------------------------------------------------------------------------------------------------- the face

# Silent beats on the face's curves, in master frames: [curve, [[frame, value], ...]] added onto what the solve made
# (eased between keys, so a beat starts and ends at 0). Head* are degrees (HeadPitch > 0 tips the head down, HeadYaw > 0
# turns it to his own left = screen right; `signs` measures them and SIGN flips them if the rig disagrees).
SIGN = {"HeadPitch": 1.0, "HeadYaw": 1.0}
SMILE = ("CTRL_expressions_mouthCornerPullL", "CTRL_expressions_mouthCornerPullR")
SQUINT = ("CTRL_expressions_eyeSquintInnerL", "CTRL_expressions_eyeSquintInnerR")
CHEEK = ("CTRL_expressions_eyeCheekRaiseL", "CTRL_expressions_eyeCheekRaiseR")


def smile(f0: int, f1: int, f2: int, f3: int, amount: float) -> list:
    """A smile that grows f0->f1, holds, and lets go f2->f3 (cheeks and a hint of squint come with it)."""
    keys = lambda a: [[f0, 0.0], [f1, a], [f2, a], [f3, 0.0]]  # noqa: E731
    return ([[c, keys(amount)] for c in SMILE] + [[c, keys(amount * 0.5)] for c in CHEEK] +
            [[c, keys(amount * 0.3)] for c in SQUINT])


def nod(f: int, deg: float = 4.0) -> list:
    """A small nod: down over 6 frames, back over 9."""
    return [["HeadPitch", [[f, 0.0], [f + 6, deg], [f + 15, 0.0]]]]


BEATS = {
    "him": [
        # S13: head down in the dark, then up to the lens with the key light (bar 16 beat 1, f900, 15 frames)
        ["HeadPitch", [[840, 16.0], [896, 15.0], [914, 0.0]]],
        ["CTRL_expressions_eyeLookDownL", [[840, 0.35], [898, 0.35], [910, 0.0]]],
        ["CTRL_expressions_eyeLookDownR", [[840, 0.35], [898, 0.35], [910, 0.0]]],
        # S15: after L2 ("She'll tell you the next one", ends f1141) he turns his head to her and holds while she
        # starts; back to the front during S16 (he is off screen), ready for S17
        ["HeadYaw", [[1136, 0.0], [1152, 42.0], [1196, 45.0], [1290, 45.0], [1316, 0.0]]],
        ["HeadPitch", [[1136, 0.0], [1152, 4.0], [1290, 4.0], [1316, 0.0]]],
        *smile(1138, 1150, 1180, 1200, 0.25),
        # S17-S18: "Welcome..." then a small smile to the lens, a settling nod, held through the title
        *nod(1404, 3.0),
        *smile(1376, 1396, 1530, 1560, 0.35),
    ],
    "her": [
        # S15: she watches him while he speaks (head turned towards him), a smile at "the next one", then she turns
        # to the lens for L3 (f1158)
        ["HeadYaw", [[1080, -22.0], [1140, -24.0], [1156, 0.0]]],
        ["HeadPitch", [[1080, -3.0], [1140, -3.0], [1156, 0.0]]],
        *smile(1124, 1138, 1146, 1160, 0.3),
        # S17-S18: "...to karma." then the smile to the lens and a settling nod with him
        *nod(1408, 3.0),
        *smile(1398, 1416, 1530, 1560, 0.35),
    ],
}
# The lines whose mood differs from the base solve: spliced over the base with a 4-frame cross-fade at each end.
SPLICES = {"him": ["L2", "L4a"], "her": ["L4b"]}

COMPOSE = r"""
import json, bisect, unreal
AL, EAL, F = unreal.AnimationLibrary, unreal.EditorAssetLibrary, unreal.RawCurveTrackTypes.RCT_FLOAT
P = json.loads(PARAMS)
if EAL.does_asset_exist(P["out"]):
    EAL.delete_asset(P["out"])
EAL.duplicate_asset(P["base"], P["out"])
a = unreal.load_asset(P["out"])
L = a.get_editor_property("sequence_length")
dt = 1.0 / 30
grid = [i * dt for i in range(int(L / dt) + 1)]
def keys(anim, n):
    if not AL.does_curve_exist(anim, n, F):
        return [], []
    t, v = AL.get_float_keys(anim, n)
    return list(t), list(v)
def at(t, v, x):
    if not t:
        return 0.0
    i = bisect.bisect_right(t, x)
    if i <= 0:
        return v[0]
    if i >= len(t):
        return v[-1]
    u = (x - t[i - 1]) / ((t[i] - t[i - 1]) or 1)
    return v[i - 1] + (v[i] - v[i - 1]) * u
def ease(u):
    return u * u * (3 - 2 * u)
names = [str(n) for n in AL.get_animation_curve_names(a, F)]
cur = {}
def get(n):
    if n not in cur:
        t, v = keys(a, n)
        cur[n] = [at(t, v, x) for x in grid]
    return cur[n]
report = {"length": L, "splices": [], "beats": 0}
for sp in P["splices"]:
    s = unreal.load_asset(sp["anim"])
    sl = s.get_editor_property("sequence_length")
    t0, fade = sp["t0"], sp["fade"]
    sn = [str(n) for n in AL.get_animation_curve_names(s, F)]
    for n in sn:
        st, sv = keys(s, n)
        base = get(n)
        for i, x in enumerate(grid):
            u = x - t0
            if u < 0 or u > sl:
                continue
            w = ease(min(1.0, u / fade, (sl - u) / fade))
            base[i] = base[i] * (1 - w) + at(st, sv, u) * w
    report["splices"].append([sp["anim"], round(t0, 3), round(sl, 3), len(sn)])
for n, ks in P["beats"]:
    v = get(n)
    for (ta, va), (tb, vb) in zip(ks, ks[1:]):
        for i, x in enumerate(grid):
            if ta <= x < tb or (x == tb and (tb, vb) == tuple(ks[-1])):
                v[i] += va + (vb - va) * ease((x - ta) / ((tb - ta) or 1))
    report["beats"] += 1
for n, v in cur.items():
    if n.startswith("CTRL_"):
        v = [min(1.0, max(0.0, x)) for x in v]
    if AL.does_curve_exist(a, n, F):
        AL.remove_curve(a, n, False)
    AL.add_curve(a, n, F, False)
    AL.add_float_curve_keys(a, n, grid, v)
EAL.save_asset(P["out"])
report["curves_written"] = len(cur)
result = report
"""


def compose(who: str) -> dict:
    """The face of `who`'s whole performance: the base solve, the other-mood lines spliced in at their frames, the
    silent beats added. -> ANIM/AS_reel_<who>_face (curves only; sync bakes the skeleton onto it)."""
    c = cues()
    sec = lambda f: (f - START[who]) / FPS  # noqa: E731  master frame -> seconds into the performance
    splices = [{"anim": f"{SPEECH}/Anim/AS_{anim_name(k)}", "t0": sec(c[k]["file_frame"]), "fade": 4 / FPS}
               for k in SPLICES[who]]
    beats = [[n, [[sec(f), v * SIGN.get(n, 1.0)] for f, v in ks]] for n, ks in BEATS[who]]
    params = {"base": f"{SPEECH}/Anim/AS_{anim_name(who)}", "out": f"{ANIM}/AS_reel_{who}_face",
              "splices": splices, "beats": beats}
    return ok(client.exec_code(f"PARAMS = {json.dumps(json.dumps(params))}\n" + COMPOSE, timeout=600))



# ---------------------------------------------------------------------------------------------------- the stage

# My own copies of the presenters (same Blueprint class as Host / Presenter) and test cameras, all moved by OFFSET
# out of every reel camera's view (under the floor): the geometry between eyes, lenses and partner is what matters.
OFFSET = (0.0, 0.0, -2500.0)
SHOTS_OF = {"him": ["S13", "S14", "S15", "S17", "S18"], "her": ["S15", "S16", "S17", "S18"]}


def test_label(who: str) -> str:
    return f"Test_{ME}_{'Him' if who == 'him' else 'Her'}"


def test_seq(who: str) -> str:
    return f"/Game/Reel/Test_{ME}_{'Him' if who == 'him' else 'Her'}"


def cam_label(sid: str) -> str:
    return f"Test_{ME}_{sid}"


def shifted(p) -> list:
    return [float(a + b) for a, b in zip(p, OFFSET)]


def eyes_at(who: str) -> list:
    """Where a presenter's eyes are on the reel mark (they face +X; the eyes sit 9 cm forward of the feet)."""
    m = MARK[who]
    return shifted([m[0] + 9.0, m[1], EYES[who]])


def idle_for(who: str) -> str:
    return IDLE if not IDLE_OFFSET[who] else f"{ANIM}/AS_reel_{who}_idle"


ROLL = r"""
import json, unreal
AL, EAL = unreal.AnimationLibrary, unreal.EditorAssetLibrary
P = json.loads(PARAMS)
if EAL.does_asset_exist(P["out"]):
    EAL.delete_asset(P["out"])
EAL.duplicate_asset(P["src"], P["out"])
a = unreal.load_asset(P["out"])
n = AL.get_num_keys(a)
L = a.get_editor_property("sequence_length")
shift = int(round(P["seconds"] / L * (n - 1)))
ctrl = a.get_editor_property("controller")
ctrl.open_bracket("roll idle", True)
names = [str(b) for b in AL.get_animation_track_names(a)]
for b in names:
    poses = [AL.get_bone_pose_for_frame(a, b, k, False) for k in range(n - 1)]
    poses = poses[shift:] + poses[:shift]
    poses.append(poses[0])
    ctrl.set_bone_track_keys(b, [t.translation for t in poses], [t.rotation for t in poses], [t.scale3d for t in poses])
ctrl.close_bracket(True)
EAL.save_asset(P["out"])
result = {"anim": P["out"], "keys": n, "shift": shift, "bones": len(names)}
"""

SPAWN = r"""
import json, unreal
P = json.loads(PARAMS)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
src = next(a for a in EAS.get_all_level_actors() if a.get_actor_label() == P["source"])
for a in EAS.get_all_level_actors():
    if a.get_actor_label() == P["label"]:
        EAS.destroy_actor(a)
x = EAS.spawn_actor_from_class(src.get_class(), unreal.Vector(*P["loc"]), src.get_actor_rotation())
x.set_actor_label(P["label"])
x.set_actor_hidden_in_game(False)
x.set_is_temporarily_hidden_in_editor(False)
r = src.get_actor_rotation()
result = {"label": P["label"], "class": src.get_class().get_name(), "yaw": r.yaw}
"""


def run(code: str, params: dict, timeout: float = 900):
    return ok(client.exec_code(f"PARAMS = {json.dumps(json.dumps(params))}\n" + code, timeout=timeout))


def stage(who: str) -> dict:
    """My copy of `who` on its (offset) mark, the body idle, test cameras keyed like the reel's, and the sequence:
    frame 0 = master frame START[who]."""
    res = {"spawn": run(SPAWN, {"source": LABEL[who], "label": test_label(who), "loc": shifted(MARK[who])})}
    if IDLE_OFFSET[who]:
        res["idle"] = run(ROLL, {"src": IDLE, "out": idle_for(who), "seconds": IDLE_OFFSET[who]}, 1800)
    by_id = {s.id: s for s in SHOTS}
    for sid in SHOTS_OF[who]:
        s = by_id[sid]
        loc, at = s.keys[0][1], s.keys[0][2]
        ok(client.op("look.camera", label=cam_label(sid), loc=shifted(loc), look_at=shifted(at), focal=float(s.lens),
                     aperture=float(s.stop), filmback=list(FULL_FRAME), pilot=False))
    path, frames = test_seq(who), END - START[who]
    ok(client.op("seq.shot", path=path, actor_label=test_label(who),
                 anims={"Body": idle_for(who), "Face": f"{ANIM}/AS_reel_{who}_face"},
                 camera=cam_label(SHOTS_OF[who][0]), seconds=frames / FPS))
    cuts = []
    for sid in SHOTS_OF[who]:
        s = by_id[sid]
        ok(client.op("seq.key_transform", path=path, label=cam_label(sid),
                     keys=[[max(0, s.start + f - START[who]), shifted(loc), shifted(at)] for f, loc, at in s.keys]))
        cuts.append([cam_label(sid), max(0, s.start - START[who])])
    res["cuts"] = ok(client.op("seq.camera_cuts", path=path, cuts=cuts))
    res["sequence"] = path
    return res


def signs(who: str = "him") -> dict:
    """Which way HeadPitch and HeadYaw turn this rig: the eyes' mid-point with each curve at +15 against 0, on my
    copy in its test sequence (frame 0)."""
    face = f"{ANIM}/AS_reel_{who}_face"
    probe = f"{ANIM}/AS_reel_signprobe"
    out = {}
    eyes = ["FACIAL_L_Eye", "FACIAL_R_Eye"]
    for name in (None, "HeadPitch", "HeadYaw"):
        ok(client.exec_code(f"""
import unreal
AL, EAL = unreal.AnimationLibrary, unreal.EditorAssetLibrary
if EAL.does_asset_exist({probe!r}):
    EAL.delete_asset({probe!r})
EAL.duplicate_asset({face!r}, {probe!r})
a = unreal.load_asset({probe!r})
L = a.get_editor_property("sequence_length")
for n in ("HeadPitch", "HeadYaw", "HeadRoll"):
    if AL.does_curve_exist(a, n, unreal.RawCurveTrackTypes.RCT_FLOAT):
        AL.remove_curve(a, n, False)
    AL.add_curve(a, n, unreal.RawCurveTrackTypes.RCT_FLOAT, False)
    AL.add_float_curve_keys(a, n, [0.0, L], [15.0, 15.0] if n == {name!r} else [0.0, 0.0])
EAL.save_asset({probe!r})
result = True
"""))
        ok(client.op("seq.set_anim", path=test_seq(who), component="Face", anim=probe, label=test_label(who)))
        m = ok(client.op("seq.sample", path=test_seq(who), actor_label=test_label(who), component="Face", bones=eyes,
                         frames=[2], ticks=6))
        mid = [(m["bones"][eyes[0]][0][k] + m["bones"][eyes[1]][0][k]) / 2 for k in range(3)]
        out[name or "rest"] = [round(v, 2) for v in mid]
    ok(client.op("seq.set_anim", path=test_seq(who), component="Face", anim=face, label=test_label(who)))
    ok(client.exec_code(f"import unreal\nunreal.EditorAssetLibrary.delete_asset({probe!r})\nresult = True"))
    r = out["rest"]
    out["pitch_down_positive"] = out["HeadPitch"][2] < r[2]
    out["yaw_screen_right_positive"] = out["HeadYaw"][1] < r[1]  # screen right is -Y
    return out


# ---------------------------------------------------------------------------------------------------- face and body

def sync(who: str) -> dict:
    """One skeleton for face and body (shot.py's recipe): the face rides the body with its head control on, the body
    takes the head motion that makes, then the shared skeleton is baked back onto the face with head control off."""
    path, lab = test_seq(who), test_label(who)
    face = f"{ANIM}/AS_reel_{who}_face"
    ok(client.op("seq.set_anim", path=path, component="Body", anim=idle_for(who), label=lab))
    ok(client.op("seq.set_anim", path=path, component="Face", anim=face, label=lab))
    a = ok(client.op("anim.bake_follow", sequence=path, actor_label=lab, anim=face, out=f"{ANIM}/AS_reel_{who}_follow",
                     head_control=True, timeout=3600))
    b = ok(client.op("anim.head_to_body", sequence=path, actor_label=lab, body_anim=idle_for(who),
                     out=f"{ANIM}/AS_reel_{who}_body", timeout=3600))
    c = ok(client.op("anim.bake_follow", sequence=path, actor_label=lab, anim=face, out=f"{ANIM}/AS_reel_{who}_follow",
                     timeout=3600))
    return {"follow_head": a, "body": b, "follow": c}


# Where the eyes go, master frames: a test camera (the shot's lens) or the partner's eyes. Frames in none of these
# keep the solve's own eyes (his head-down opening, his S16 off screen).
GAZE = {
    "him": [["S13", 908, 959], ["S14", 960, 1079], ["S15", 1080, 1137], ["her", 1146, 1199], ["S17", 1320, 1439],
            ["S18", 1440, 1559]],
    "her": [["him", 1080, 1149], ["S15", 1156, 1199], ["S16", 1200, 1319], ["S17", 1320, 1439], ["S18", 1440, 1559]],
}


def final_face(who: str) -> str:
    return f"{ANIM}/AS_reel_{who}_gaze{len(GAZE[who])}"


def gaze(who: str, start_at: int = 1) -> list:
    """The eye locks one range at a time (gaze_lock with a target and frames), each pass on the last one's output."""
    path, lab = test_seq(who), test_label(who)
    out = []
    for i, (what, f0, f1) in enumerate(GAZE[who], 1):
        src = f"{ANIM}/AS_reel_{who}_follow" if i == 1 else f"{ANIM}/AS_reel_{who}_gaze{i - 1}"
        if i < start_at:
            continue
        target = eyes_at(what) if what in ("him", "her") else cam_label(what)
        r = ok(client.op("anim.gaze_lock", sequence=path, actor_label=lab, anim=src, out=f"{ANIM}/AS_reel_{who}_gaze{i}",
                         target=target, frames=[f0 - START[who], f1 - START[who]], timeout=3600))
        out.append({"range": [f0, f1], "target": what, "passes": r.get("passes"), "head_to_lens": r.get("head_to_lens_deg")})
        print(who, i, json.dumps(out[-1]), flush=True)
    return out


# ---------------------------------------------------------------------------------------------------- looking at it

STILLS = {"him": [870, 925, 1000, 1060, 1120, 1170, 1380, 1420], "her": [1100, 1150, 1180, 1250, 1300, 1395, 1420]}
REMOTE_STILLS = rf"{PROJECT}\Saved\Reel\perf"


def light(who: str) -> None:
    """A soft key and fill on my copy, so a still reads under the floor."""
    e = eyes_at(who)
    ok(client.op("look.light", label=f"Test_{ME}_Key_{who}", kind="rect", loc=[e[0] + 160, e[1] + 90, e[2] + 60],
                 look_at=e, intensity=6.0, temperature=4200, width=80, height=80))
    ok(client.op("look.light", label=f"Test_{ME}_Fill_{who}", kind="rect", loc=[e[0] + 150, e[1] - 140, e[2]],
                 look_at=e, intensity=1.5, temperature=5000, width=120, height=120, shadows=False))


def stills(who: str, frames: list | None = None) -> list:
    light(who)
    got = []
    for f in frames or STILLS[who]:
        name = f"{who}_f{f}.png"
        ok(client.op("seq.still", path=test_seq(who), frame=f - START[who], camera="", out=rf"{REMOTE_STILLS}\{name}",
                     width=1280, height=720, timeout=600))
        got.append(client.pull(rf"{REMOTE_STILLS}\{name}", str(OUT / "stills" / name)))
    return got


def cleanup() -> dict:
    """Remove everything this script put in the level (my presenter copies, cameras, lights) and the test sequences.
    The animations under ANIM stay: they are the deliverable."""
    labels = [test_label(w) for w in ("him", "her")] + [cam_label(s) for s in {x for v in SHOTS_OF.values() for x in v}]
    labels += [f"Test_{ME}_{k}_{w}" for k in ("Key", "Fill") for w in ("him", "her")]
    ok(client.op("seq.close"))
    n = ok(client.op("level.delete", labels=labels))
    gone = ok(client.exec_code("import unreal\nresult = [p for p in %r if unreal.EditorAssetLibrary.does_asset_exist(p) "
                               "and unreal.EditorAssetLibrary.delete_asset(p)]" % [test_seq("him"), test_seq("her")]))
    return {"actors": n, "sequences": gone}


def place(path: str) -> list:
    """The performances on a sequence (SEQ_Reel, for R7): one Face and one Body section per presenter from START."""
    out = []
    for who in ("him", "her"):
        for comp, anim in (("Face", final_face(who)), ("Body", f"{ANIM}/AS_reel_{who}_body")):
            out.append(ok(client.op("seq.anim", path=path, label=LABEL[who], component=comp,
                                    sections=[{"anim": anim, "start": START[who], "end": END + 12}])))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["push", "solve", "compose", "stage", "signs", "sync", "gaze", "stills", "cleanup", "place"])
    ap.add_argument("--who", default="him,her")
    ap.add_argument("--seq", default="/Game/Reel/SEQ_Reel", help="place: the sequence")
    ap.add_argument("--frames", help="stills: master frames, comma-separated")
    ap.add_argument("--from", dest="start_at", type=int, default=1, help="gaze: resume at this range (1-based)")
    ap.add_argument("--only", help="solve: comma-separated SOLVES keys")
    a = ap.parse_args()
    if a.cmd == "push":
        print(json.dumps(push()))
    elif a.cmd == "solve":
        for k in (a.only.split(",") if a.only else SOLVES):
            print(k, json.dumps(solve(k)))
    elif a.cmd == "compose":
        for w in a.who.split(","):
            print(w, json.dumps(compose(w)))
    elif a.cmd in ("stage", "signs", "sync", "gaze", "stills"):
        for w in a.who.split(","):
            if a.cmd == "gaze":
                r = gaze(w, a.start_at)
            elif a.cmd == "stills":
                r = stills(w, [int(f) for f in a.frames.split(",")] if a.frames else None)
            else:
                r = globals()[a.cmd](w)
            print(w, json.dumps(r, default=str))
    elif a.cmd == "cleanup":
        print(json.dumps(cleanup()))
    elif a.cmd == "place":
        print(json.dumps(place(a.seq)))


if __name__ == "__main__":
    main()
