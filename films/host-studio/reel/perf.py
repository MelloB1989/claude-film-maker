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
ME = "agent-10"
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
FACE_MESH = {"him": "/Game/Host/Unpacked/Host/Face/SKM_Host_Trey_FaceMesh",
             "her": "/Game/Host/Unpacked/Presenter/Face/SKM_Presenter_F_FaceMesh"}
LABEL = {"him": "Host", "her": "Presenter"}
MARK = {"him": MARK_HIM, "her": MARK_HER}
EYES = {"him": EYES_HIM, "her": EYES_HER}
# Each presenter's performance runs from the first shot they are in to the end of the reel (master frames).
START = {"him": 960, "her": 1080}  # PLAN v2: S13 is bars 17-18, S14 is gone
END = 1560
# The body idle: both presenters play the engine's idle; her copy starts 17 s in, so the two never sway in step.
IDLE_OFFSET = {"him": 0.0, "her": 17.0}

# The solves: each presenter's whole stem in their base mood, and the lines whose mood differs (PLAN.md §2) alone.
# PLAN v2 moods (vo.py MOODS): L1 CONFIDENCE 0.7, L2 HAPPINESS 0.6, L3a HAPPINESS 0.6, L3b CONFIDENCE 0.8, L4a HAPPINESS
# 0.6, L4b HAPPINESS 0.8. Each stem is solved whole in the speaker's base mood (L1 / L3b) and the other lines spliced.
SOLVES = {
    "him": {"wav": "stem_him", "who": "him", "mood": "CONFIDENCE", "intensity": 0.7},
    "her": {"wav": "stem_her", "who": "her", "mood": "CONFIDENCE", "intensity": 0.8},
    "L2": {"wav": "L2", "who": "him", "mood": "HAPPINESS", "intensity": 0.6},
    "L3a": {"wav": "L3a", "who": "her", "mood": "HAPPINESS", "intensity": 0.6},
    "L4a": {"wav": "L4a", "who": "him", "mood": "HAPPINESS", "intensity": 0.6},
    "L4b": {"wav": "L4b", "who": "her", "mood": "HAPPINESS", "intensity": 0.8},
}


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def cues() -> dict:
    return json.loads((VO / "cues.json").read_text())["lines"]  # vo.py build


def anim_name(key: str) -> str:
    return f"reel_{key}"


# ---------------------------------------------------------------------------------------------------- audio

def stems() -> list[Path]:
    """Each presenter's VO stem cut to their performance window (START .. END), the audio the base solve hears."""
    made = []
    for who in ("him", "her"):
        if (VO / f"vo_{who}.wav").exists():
            x, sr = read_wav(VO / f"vo_{who}.wav")
        else:  # only the line WAVs and cues.json: each line placed on its file frame
            sr, x = SR, np.zeros(int((END + FPS) * SR / FPS), np.float32)
            for k, c in cues().items():
                if c["who"] == who:
                    w, _ = read_wav(VO / c["wav"])
                    i0 = int(round(c["file_frame"] / FPS * sr))
                    x[i0:i0 + len(w)] += w[:len(x) - i0]
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
# (eased between keys, so a beat starts and ends at 0). The head curves are degrees, but on this rig their names do not
# say what they do (`signs` measured it on the head bone, +-20 each): HeadYaw nods (+ tips the head down), HeadRoll
# turns (+ towards world -Y: his own right, screen left from the front) and HeadPitch tilts ear to shoulder.
# The beats use PITCH (+ down) and turn() (+ towards world +Y: own left, screen right from the front).
PITCH = "HeadYaw"
TURN, TURN_SIGN = "HeadRoll", -1.0
SIGN: dict = {}


def turn(keys: list) -> list:
    return [TURN, [[f, v * TURN_SIGN] for f, v in keys]]
SMILE = ("CTRL_expressions_mouthCornerPullL", "CTRL_expressions_mouthCornerPullR")
SQUINT = ("CTRL_expressions_eyeSquintInnerL", "CTRL_expressions_eyeSquintInnerR")
CHEEK = ("CTRL_expressions_eyeCheekRaiseL", "CTRL_expressions_eyeCheekRaiseR")


def smile(f0: int, f1: int, f2: int, f3: int, amount: float, side: str = "LR") -> list:
    """A smile that grows f0->f1, holds, and lets go f2->f3 (cheeks and a hint of squint come with it); one `side`
    ("L" or "R", the face's own) for a smirk or a half-smile."""
    keys = lambda a: [[f0, 0.0], [f1, a], [f2, a], [f3, 0.0]]  # noqa: E731
    pick = lambda pair: [c for c in pair if c[-1] in side]  # noqa: E731
    return ([[c, keys(amount)] for c in pick(SMILE)] + [[c, keys(amount * 0.5)] for c in pick(CHEEK)] +
            [[c, keys(amount * 0.3)] for c in pick(SQUINT)])


def eyes(f0: int, f1: int, f2: int, f3: int, look: dict) -> list:
    """Both eyes held on eye-look curves ({"Left": 0.6, "Down": 0.1}) f1..f2, eased in from f0 and out to f3. On this
    rig eyeLookLeft turns the eyes to the face's own right (world -Y for both presenters), eyeLookRight to its left."""
    return [[f"CTRL_expressions_eyeLook{d}{s}", [[f0, 0.0], [f1, v], [f2, v], [f3, 0.0]]] for s in "LR" for d, v in look.items()]


def word(line: str, w: str, default: float) -> float:
    """The master frame a word of a line starts on (cues.json), else `default`."""
    try:
        return next(x["start"] for x in cues()[line]["words"] if x["w"].strip(".,…!?'").lower() == w)
    except (OSError, KeyError, StopIteration):
        return default


def nod(f: int, deg: float = 4.0) -> list:
    """A small nod: down over 6 frames, back over 9."""
    return [[PITCH, [[f, 0.0], [f + 6, deg], [f + 15, 0.0]]]]


def beats(who: str) -> list:
    """The silent beats of PLAN v2 (S13 f960-1079, S15 f1080-1199, S16 f1200-1319, S17 f1320-1439, S18 to f1560)."""
    if who == "him":
        return [
            # S13: a silhouette, head down; his eyes come up to the lens as the key ramps (bar 17 beat 3, f990-1002)
            [PITCH, [[960, 16.0], [986, 15.0], [1004, 0.0]]],
            *eyes(960, 960, 988, 1000, {"Down": 0.35}),
            # L1 "Took you long enough." (f1020), then a small smirk held to the cut, let go as L2 comes
            *smile(1056, 1066, 1086, 1098, 0.32, side="R"),
            # S15: L2 "Ask her what's next." (f1095), then he turns his head to her and holds through S15; back to the
            # front during S16 (he is off screen). She stands 80 cm behind him and 95 cm to his right (world -Y),
            # ~130 deg from his front: more than a lock converges on, so the look is written, the head over his right
            # shoulder and the eyes the rest of the way
            turn([[1128, 0.0], [1146, -62.0], [1196, -65.0], [1290, -65.0], [1316, 0.0]]),
            [PITCH, [[1128, 0.0], [1146, 5.0], [1290, 5.0], [1316, 0.0]]],
            *eyes(1130, 1142, 1196, 1206, {"Left": 0.6, "Down": 0.1}),
            *smile(1126, 1140, 1180, 1200, 0.22),
            # S17: L4a "What goes around..." (f1350), a glance to her as she says "comes around", back to the lens
            turn([[1378, 0.0], [1388, -32.0], [1400, -34.0], [1412, 0.0]]),
            *eyes(1378, 1386, 1400, 1410, {"Left": 0.7}),
            # ...then a small warm smile to the lens, a settling nod, held through S18
            *smile(1404, 1420, 1530, 1560, 0.32),
            *nod(1424, 3.0),
        ]
    tilt = word("L3b", "yourself", 1282)
    return [
        # S15: she watches him while he speaks L2 (he is 80 cm in front of her and 95 cm to her left, world +Y, his
        # eyes 16 cm higher; written, as a lock does not converge from there), then to the lens for L3a (f1158)
        turn([[1080, 34.0], [1140, 36.0], [1154, 0.0]]),
        [PITCH, [[1080, -4.0], [1140, -4.0], [1154, 0.0]]],
        *eyes(1080, 1080, 1142, 1152, {"Right": 0.35, "Up": 0.12}),
        # "Nice try." with a half-smile: a playful refusal, held a beat, gone by L3b
        *smile(1160, 1172, 1196, 1212, 0.3, side="L"),
        # S16: L3b to the lens, unhurried; a small head tilt on "yourself"
        ["HeadPitch", [[tilt - 6, 0.0], [tilt + 4, 6.0], [tilt + 24, 6.0], [tilt + 40, 0.0]]],
        # S17: L4b "...comes around. That's karma." (f1386): a glance to him on "comes around", then the lens
        turn([[1376, 0.0], [1386, 30.0], [1398, 32.0], [1408, 0.0]]),
        *eyes(1376, 1384, 1398, 1406, {"Right": 0.35, "Up": 0.1}),
        *smile(1424, 1438, 1530, 1560, 0.35),
        *nod(1436, 3.0),
    ]


# The lines whose mood differs from the base solve: spliced over the base with a 4-frame cross-fade at each end.
SPLICES = {"him": ["L2", "L4a"], "her": ["L3a", "L4b"]}

COMPOSE = r"""
import json, bisect, time, unreal
AL, EAL, F = unreal.AnimationLibrary, unreal.EditorAssetLibrary, unreal.RawCurveTrackTypes.RCT_FLOAT
from fmbridge.ops.assets import free  # never a dialog over an existing asset
P = json.loads(PARAMS)
T0 = time.time()
def job():
    free(P["out"])
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
        yield
        report["splices"].append([sp["anim"], round(t0, 3), round(sl, 3), len(sn)])
    for n, ks in P["beats"]:
        v = get(n)
        for (ta, va), (tb, vb) in zip(ks, ks[1:]):
            for i, x in enumerate(grid):
                if ta <= x < tb or (x == tb and (tb, vb) == tuple(ks[-1])):
                    v[i] += va + (vb - va) * ease((x - ta) / ((tb - ta) or 1))
        report["beats"] += 1
    # each curve's keys in one controller call, one bracket, so one recompression for the asset
    # (AnimationLibrary.add_float_curve_keys recompresses after every key: it held the game thread for 40 min)
    X = unreal.AnimationCurveIdentifierExtensions
    def cid(n):
        for args in ((n, F), (a.get_skeleton(), n, F)):
            try:
                return X.get_curve_identifier(*args)
            except Exception:
                pass
        return X.find_curve_identifier(a, n, F)
    t0 = time.time()
    lin = unreal.RichCurveInterpMode.RCIM_LINEAR
    ctrl = a.get_editor_property("controller")
    ctrl.open_bracket("fmbridge reel compose", False)
    try:
        for n, v in cur.items():
            if n.startswith("CTRL_"):
                v = [min(1.0, max(0.0, x)) for x in v]
            c = cid(n)
            if not AL.does_curve_exist(a, n, F):
                ctrl.add_curve(c, 4, False)
            ctrl.set_curve_keys(c, [unreal.RichCurveKey(time=x, value=y, interp_mode=lin) for x, y in zip(grid, v)], False)
    finally:
        ctrl.close_bracket(False)
    report["write_s"] = round(time.time() - t0, 2)
    yield
    EAL.save_asset(P["out"])
    report["curves_written"] = len(cur)
    report["total_s"] = round(time.time() - T0, 2)
    return report


result = job()
"""


def compose(who: str) -> dict:
    """The face of `who`'s whole performance: the base solve, the other-mood lines spliced in at their frames, the
    silent beats added. -> ANIM/AS_reel_<who>_face (curves only; sync bakes the skeleton onto it)."""
    c = cues()
    sec = lambda f: (f - START[who]) / FPS  # noqa: E731  master frame -> seconds into the performance
    splices = [{"anim": f"{SPEECH}/Anim/AS_{anim_name(k)}", "t0": sec(c[k]["file_frame"]), "fade": 4 / FPS}
               for k in SPLICES[who]]
    beats = [[n, [[sec(f), v * SIGN.get(n, 1.0)] for f, v in ks]] for n, ks in globals()["beats"](who)]
    params = {"base": f"{SPEECH}/Anim/AS_{anim_name(who)}", "out": f"{ANIM}/AS_reel_{who}_face",
              "splices": splices, "beats": beats}
    return ok(client.exec_code(f"PARAMS = {json.dumps(json.dumps(params))}\n" + COMPOSE, timeout=1800))



# ---------------------------------------------------------------------------------------------------- the stage

# My own copies of the presenters (same Blueprint class as Host / Presenter) and test cameras, all moved by OFFSET
# out of every reel camera's view (under the floor): the geometry between eyes, lenses and partner is what matters.
OFFSET = (0.0, 0.0, -2500.0)
SHOTS_OF = {"him": ["S13", "S15", "S17", "S18"], "her": ["S15", "S16", "S17", "S18"]}


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
from fmbridge.ops.assets import free  # never a dialog over an existing asset
P = json.loads(PARAMS)
def job():  # across editor ticks (a yield every few bones), one bracket: one recompression
    free(P["out"])
    EAL.duplicate_asset(P["src"], P["out"])
    a = unreal.load_asset(P["out"])
    n = AL.get_num_keys(a)
    L = a.get_editor_property("sequence_length")
    shift = int(round(P["seconds"] / L * (n - 1)))
    ctrl = a.get_editor_property("controller")
    names = [str(b) for b in AL.get_animation_track_names(a)]
    ctrl.open_bracket("roll idle", False)
    try:
        for i, b in enumerate(names):
            poses = [AL.get_bone_pose_for_frame(a, b, k, False) for k in range(n - 1)]
            poses = poses[shift:] + poses[:shift]
            poses.append(poses[0])
            ctrl.set_bone_track_keys(b, [t.translation for t in poses], [t.rotation for t in poses],
                                     [t.scale3d for t in poses], False)
            if i % 8 == 7:
                yield
    finally:
        ctrl.close_bracket(False)
    yield
    EAL.save_asset(P["out"])
    return {"anim": P["out"], "keys": n, "shift": shift, "bones": len(names)}
result = job()
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
    res["face_mode"] = ok(client.op("mh.drive_face", label=test_label(who)))  # Sequencer drives the face (README)
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


def restage(who: str) -> dict:
    """stage again (my copy and cameras are gone after the level is reloaded) and put the synced animations back on
    the test sequence's tracks, so gaze can go on from where it was."""
    res = stage(who)
    have = ok(client.exec_code("import unreal\nresult = [p for p in %r if unreal.EditorAssetLibrary.does_asset_exist(p)]"
                               % [f"{ANIM}/AS_reel_{who}_follow", f"{ANIM}/AS_reel_{who}_body"]))
    for comp, anim in (("Face", f"{ANIM}/AS_reel_{who}_follow"), ("Body", f"{ANIM}/AS_reel_{who}_body")):
        if anim in have:
            ok(client.op("seq.set_anim", path=test_seq(who), component=comp, anim=anim, label=test_label(who)))
    res["tracks"] = have
    return res


def signs(who: str = "him") -> dict:
    """What each head curve does on this rig: the head bone's up axis and the eyes' mid-point with the curve at +-20
    against all at 0, on my copy in its test sequence (frame 2). Read it to set PITCH and TURN."""
    face, probe = f"{ANIM}/AS_reel_{who}_face", f"{ANIM}/AS_reel_signprobe"
    bones = ["head", "FACIAL_L_Eye", "FACIAL_R_Eye"]
    out = {}
    for name, val in ((None, 0), ("HeadPitch", 20), ("HeadPitch", -20), ("HeadYaw", 20), ("HeadYaw", -20),
                      ("HeadRoll", 20), ("HeadRoll", -20)):
        run(r"""
import json, unreal
import fmbridge.ops.anim as A
EAL = unreal.EditorAssetLibrary
from fmbridge.ops.assets import free
P = json.loads(PARAMS)
free(P["probe"])
EAL.duplicate_asset(P["face"], P["probe"])
a = unreal.load_asset(P["probe"])
L = a.get_editor_property("sequence_length")
A._write(a, {n: ([0.0, L], [P["val"]] * 2 if n == P["name"] else [0.0, 0.0]) for n in ("HeadPitch", "HeadYaw", "HeadRoll")})
EAL.save_asset(P["probe"])
result = True
""", {"face": face, "probe": probe, "name": name, "val": float(val)})
        ok(client.op("seq.set_anim", path=test_seq(who), component="Face", anim=probe, label=test_label(who)))
        m = ok(client.op("seq.sample", path=test_seq(who), actor_label=test_label(who), component="Face", bones=bones,
                         frames=[2], ticks=8))
        mid = [(m["bones"][bones[1]][0][k] + m["bones"][bones[2]][0][k]) / 2 for k in range(3)]
        out[f"{name}{val:+d}" if name else "rest"] = {"eyes": mid, "head_up": m["bones"]["head"][0][3:6]}
    ok(client.op("seq.set_anim", path=test_seq(who), component="Face", anim=face, label=test_label(who)))
    ok(client.exec_code(f"import unreal\nunreal.EditorAssetLibrary.delete_asset({probe!r})\nresult = True"))
    r = out["rest"]["eyes"]
    return {k: {"eyes_moved": [round(a - b, 2) for a, b in zip(v["eyes"], r)], "head_up": [round(x, 3) for x in v["head_up"]]}
            for k, v in out.items()}


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
# keep the solve's own eyes and the beats' (his head-down opening, his written look to her, his S16 off screen).
GAZE = {  # each lens range ends before a written look starts and begins after it has let go
    "him": [["S13", 1000, 1079], ["S15", 1080, 1127], ["S17", 1320, 1377], ["S17", 1412, 1439], ["S18", 1440, 1559]],
    "her": [["S15", 1152, 1199], ["S16", 1200, 1319], ["S17", 1320, 1375], ["S17", 1408, 1439], ["S18", 1440, 1559]],
}


def final_face(who: str) -> str:
    return f"{ANIM}/AS_reel_{who}_gaze{len(GAZE[who])}"


def gaze(who: str, start_at: int = 1, stop_at: int = 99) -> list:
    """The eye locks one range at a time (gaze_lock with a target and frames), each pass on the last one's output."""
    path, lab = test_seq(who), test_label(who)
    out = []
    for i, (what, f0, f1) in enumerate(GAZE[who], 1):
        src = f"{ANIM}/AS_reel_{who}_follow" if i == 1 else f"{ANIM}/AS_reel_{who}_gaze{i - 1}"
        if i < start_at or i > stop_at:
            continue
        target = eyes_at(what) if what in ("him", "her") else cam_label(what)
        # the Face track plays this pass's source first: gaze_lock swaps only the sections playing `anim`, so a rerun
        # (the track left on this pass's earlier output) would otherwise write into an animation nobody plays
        ok(client.op("seq.set_anim", path=path, component="Face", anim=src, label=lab))
        r = ok(client.op("anim.gaze_lock", sequence=path, actor_label=lab, anim=src, out=f"{ANIM}/AS_reel_{who}_gaze{i}",
                         target=target, frames=[f0 - START[who], f1 - START[who]], timeout=3600))
        out.append({"range": [f0, f1], "target": what, "passes": r.get("passes"), "head_to_lens": r.get("head_to_lens_deg"),
                    "calibration": r.get("calibration"), "frames": r.get("frames")})
        print(who, i, json.dumps(out[-1]), flush=True)
    return out



# ---------------------------------------------------------------------------------------------------- gestures

# The engine's MetaHuman content has no talk gestures (only the idle, facial loops, ROM clips, locomotion), and the
# brief rules out downloading packs, so a gesture is written by hand: rotations added onto the arm bones of the baked
# body animation, eased in and out, in each bone's own axes. Which local axis does what on this rig is measured first
# (`arm_axes`), not guessed. Subtle on purpose: a stiff gesture reads worse than none.
ARM = {"him": "r", "her": "l"}  # his right hand (towards the shelves, screen right); her left (the watch hand)
GESTURES = {
    # S14, on "Everything on these shelves": the hand comes up open, palm a little up, and settles back
    "him": {"keys": [[962, 0.0], [980, 1.0], [998, 0.85], [1022, 0.0]],
            "rot": {"upperarm": ["fwd", 14.0], "lowerarm": ["flex", 48.0], "hand": ["supinate", 35.0]}},
    # S16, on "calm, honest": the watch hand lifts a little, palm in
    "her": {"keys": [[1236, 0.0], [1252, 1.0], [1270, 0.9], [1292, 0.0]],
            "rot": {"upperarm": ["fwd", 8.0], "lowerarm": ["flex", 38.0], "hand": ["supinate", 15.0]}},
}

AXES_PROBE = r"""
import json, unreal
AL, EAL = unreal.AnimationLibrary, unreal.EditorAssetLibrary
from fmbridge.ops.assets import free  # never a dialog over an existing asset
P = json.loads(PARAMS)
free(P["out"])
EAL.duplicate_asset(P["src"], P["out"])
a = unreal.load_asset(P["out"])
n = AL.get_num_keys(a)
b = P["bone"]
poses = [AL.get_bone_pose_for_frame(a, b, k, False) for k in range(n)]
ax = unreal.Vector(*P["axis"])
dq = unreal.MathLibrary.quat_make_from_euler(unreal.Vector(*[P["deg"] * c for c in P["axis"]]))
ctrl = a.get_editor_property("controller")
ctrl.open_bracket("arm probe", True)
ctrl.set_bone_track_keys(b, [t.translation for t in poses], [unreal.MathLibrary.multiply_quat_quat(t.rotation, dq) for t in poses],
                         [t.scale3d for t in poses])
ctrl.close_bracket(True)
EAL.save_asset(P["out"])
result = n
"""

GESTURE = r"""
import json, math, unreal
AL, EAL = unreal.AnimationLibrary, unreal.EditorAssetLibrary
from fmbridge.ops.assets import free  # never a dialog over an existing asset
P = json.loads(PARAMS)
def job():
    free(P["out"])
    EAL.duplicate_asset(P["src"], P["out"])
    a = unreal.load_asset(P["out"])
    n = AL.get_num_keys(a)
    L = a.get_editor_property("sequence_length")
    rate = (n - 1) / L
    ks = P["keys"]
    def env(t):
        if t <= ks[0][0] or t >= ks[-1][0]:
            return 0.0
        for (ta, va), (tb, vb) in zip(ks, ks[1:]):
            if ta <= t <= tb:
                u = (t - ta) / (tb - ta)
                return va + (vb - va) * u * u * (3 - 2 * u)
        return 0.0
    ctrl = a.get_editor_property("controller")
    ctrl.open_bracket("reel gesture", True)
    for b, (axis, deg) in P["rot"].items():
        poses = [AL.get_bone_pose_for_frame(a, b, k, False) for k in range(n)]
        rots = []
        for k, t in enumerate(poses):
            w = env(k / rate)
            if w <= 0:
                rots.append(t.rotation)
                continue
            dq = unreal.MathLibrary.quat_make_from_euler(unreal.Vector(*[deg * w * c for c in axis]))
            rots.append(unreal.MathLibrary.multiply_quat_quat(t.rotation, dq))
        ctrl.set_bone_track_keys(b, [t.translation for t in poses], rots, [t.scale3d for t in poses])
        yield
    ctrl.close_bracket(True)
    EAL.save_asset(P["out"])
    return {"anim": P["out"], "keys": n, "bones": list(P["rot"])}
result = job()
"""


def arm_axes(who: str) -> dict:
    """For each arm bone and each local axis: where the hand goes (world cm, his/her own frame) and how the palm turns
    when that bone is rotated +25 deg about the axis. Read it to fill AXES below."""
    side = ARM[who]
    body = f"{ANIM}/AS_reel_{who}_body"
    probe = f"{ANIM}/AS_reel_armprobe"
    path, lab = test_seq(who), test_label(who)
    frame = (GESTURES[who]["keys"][1][0] - START[who])
    hand = f"hand_{side}"
    base = None
    out = {}
    for bone in (f"upperarm_{side}", f"lowerarm_{side}", hand):
        for k, axis in enumerate(([1, 0, 0], [0, 1, 0], [0, 0, 1], None)):
            if axis is None and base is not None:
                continue
            if axis is not None:
                run(AXES_PROBE, {"src": body, "out": probe, "bone": bone, "axis": axis, "deg": 25.0})
                ok(client.op("seq.set_anim", path=path, component="Body", anim=probe, label=lab))
            else:
                ok(client.op("seq.set_anim", path=path, component="Body", anim=body, label=lab))
            m = ok(client.op("seq.sample", path=path, actor_label=lab, component="Body", bones=[hand], frames=[frame],
                             ticks=6))
            x = m["bones"][hand][0]
            if axis is None:
                base = x
                continue
            out[f"{bone}.{'XYZ'[k]}"] = {"hand_moves": [round(x[i] - base[i], 1) for i in range(3)],
                                         "hand_axes": [round(v, 2) for v in x[3:]]}
    ok(client.op("seq.set_anim", path=path, component="Body", anim=body, label=lab))
    out["base_axes"] = [round(v, 2) for v in base[3:]]
    return out


# Whether the reviewed gesture goes into the reel (set after looking at the stills; dropped if it reads stiff).
USE_GESTURE = {"him": False, "her": False}
# Filled from arm_axes on this rig: the local rotation axis (and sign) for each named motion.
AXES = {"fwd": [0, 0, 1], "flex": [0, 0, 1], "supinate": [1, 0, 0]}


def gesture(who: str) -> dict:
    """The gesture on `who`'s body animation -> AS_reel_<who>_body_g (the sequence's Body track is switched to it)."""
    g, side = GESTURES[who], ARM[who]
    sec = lambda f: (f - START[who]) / FPS  # noqa: E731
    rot = {f"{bone}_{side}": [AXES[motion], deg] for bone, (motion, deg) in g["rot"].items()}
    r = run(GESTURE, {"src": f"{ANIM}/AS_reel_{who}_body", "out": f"{ANIM}/AS_reel_{who}_body_g",
                      "keys": [[sec(f), v] for f, v in g["keys"]], "rot": rot}, 1800)
    ok(client.op("seq.set_anim", path=test_seq(who), component="Body", anim=f"{ANIM}/AS_reel_{who}_body_g",
                 label=test_label(who)))
    return r


# ---------------------------------------------------------------------------------------------------- looking at it

STILLS = {"him": [975, 1030, 1070, 1110, 1170, 1360, 1394, 1430], "her": [1110, 1165, 1240, 1290, 1394, 1430]}
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


# The body's idle around the performance (seq.anim's idle -> line -> idle): from PRE_ROLL frames before START (both
# are hidden until their first shot; the pre-roll covers the handles and a render's warm-up) to POST_ROLL after END,
# phased so the idle is where the baked body starts and ends, cross-faded over BLEND frames.
PRE_ROLL, POST_ROLL, BLEND = 240, 48, 6


def drive_faces() -> list:
    """Sequencer drives the level's presenters' faces (their Blueprint has no slot for it). It changes the faces
    in any render that does not carry these sections: run it only once the editor's operator says so."""
    return [ok(client.op("mh.drive_face", label=LABEL[w])) for w in ("him", "her")]


def place(path: str) -> list:
    """The performances on a sequence (SEQ_Reel, for R7): per presenter one Face section START..END (the last
    pose held after), and the Body as idle -> performance -> idle. Run drive_faces first."""
    out = []
    lengths = ok(client.exec_code("import unreal\nresult = {p: unreal.load_asset(p).get_editor_property("
                                  "'sequence_length') for p in %r}" % [idle_for(w) for w in ("him", "her")]))
    for who in ("him", "her"):
        s0, s1 = START[who], END
        idle, L = idle_for(who), lengths[idle_for(who)]
        phase = lambda f: ((f - s0) / FPS) % L  # noqa: E731  the idle's time at master frame f (0 at START)
        body = f"{ANIM}/AS_reel_{who}_body" + ("_g" if USE_GESTURE[who] else "")
        out.append(ok(client.op("seq.anim", path=path, label=LABEL[who], component="Face",
                                sections=[{"anim": final_face(who), "start": s0, "end": s1 + POST_ROLL,
                                           "loop": False}])))
        out.append(ok(client.op("seq.anim", path=path, label=LABEL[who], component="Body", sections=[
            {"anim": idle, "start": s0 - PRE_ROLL, "end": s0 + BLEND, "offset": phase(s0 - PRE_ROLL),
             "blend_out": BLEND},
            {"anim": body, "start": s0, "end": s1, "blend_in": BLEND, "blend_out": BLEND, "loop": False},
            {"anim": idle, "start": s1 - BLEND, "end": s1 + POST_ROLL, "offset": phase(s1 - BLEND),
             "blend_in": BLEND}])))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["push", "solve", "compose", "stage", "signs", "sync", "gaze", "stills", "cleanup", "drive_faces", "restage",
                                       "place", "arm_axes", "gesture"])
    ap.add_argument("--who", default="him,her")
    ap.add_argument("--seq", default="/Game/Reel/SEQ_Reel", help="place: the sequence")
    ap.add_argument("--frames", help="stills: master frames, comma-separated")
    ap.add_argument("--from", dest="start_at", type=int, default=1, help="gaze: resume at this range (1-based)")
    ap.add_argument("--to", dest="stop_at", type=int, default=99, help="gaze: stop after this range (short jobs)")
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
    elif a.cmd in ("stage", "restage", "signs", "sync", "gaze", "stills", "arm_axes", "gesture"):
        for w in a.who.split(","):
            if a.cmd == "gaze":
                r = gaze(w, a.start_at, a.stop_at)
            elif a.cmd == "stills":
                r = stills(w, [int(f) for f in a.frames.split(",")] if a.frames else None)
            else:
                r = globals()[a.cmd](w)
            print(w, json.dumps(r, default=str))
    elif a.cmd == "cleanup":
        print(json.dumps(cleanup()))
    elif a.cmd == "drive_faces":
        print(json.dumps(drive_faces()))
    elif a.cmd == "place":
        print(json.dumps(place(a.seq)))


if __name__ == "__main__":
    main()
