"""Round 5 (T2): the head never moves with a blink. perfkit.stability (the checks and the fixes), perf.face's
blink_head/solver_head, and the render-level film-qa head (math only: no mediapipe here).

Round 4, the operator on her: "every time she blinks her head nods a little down like a jitter". The face test
below rebuilds that face's recipe (solver_head=soften, gaze blinks on big turns, a solve that nods with its own
blinks) and the checks must fail it; the round-5 defaults must pass."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "unreal" / "fmbridge"))

from perfkit import curves as C  # noqa: E402
from perfkit import face as F  # noqa: E402
from perfkit import metrics as M  # noqa: E402
from perfkit import stability as ST  # noqa: E402
from perfkit.rig import HeadSigns  # noqa: E402

RATE = 30.0
# the reel's rigs (REEL_PERF.md): HeadYaw nods (+ down), HeadRoll turns, HeadPitch tilts
REEL = HeadSigns(yaw=-1.0, pitch=-1.0, curves={"yaw": "HeadRoll", "pitch": "HeadYaw", "roll": "HeadPitch"})


def blink_closure(t, onsets, dur=0.3):
    v = 0.0
    for o in onsets:
        u = t - o
        if 0 < u < dur:
            v = max(v, math.sin(math.pi * u / dur))
    return v


def dip(t, onsets, depth=1.5, dur=0.45):
    return sum(-depth * math.sin(math.pi * (t - o) / dur) ** 2 for o in onsets if 0 < t - o < dur)


ONSETS = [0.8, 2.1, 3.9, 5.2, 6.6, 8.3, 9.4]


def judge(pitch_fn, onsets=ONSETS, length=10.5, yaw_fn=None):
    t = C.grid(0, length, RATE)
    clos = [blink_closure(x, onsets) for x in t]
    spans = ST.blink_windows(t, clos)
    yaw = [yaw_fn(x) for x in t] if yaw_fn else None
    return ST.check(t, [pitch_fn(x) for x in t], spans, yaw=yaw), spans


def by_name(r):
    return {c["name"]: c for c in r["checks"]}


# --- the measurement -----------------------------------------------------------------------------------------------

def test_blink_windows_find_each_blink():
    t = C.grid(0, 10.5, RATE)
    spans = ST.blink_windows(t, [blink_closure(x, ONSETS) for x in t])
    assert len(spans) == len(ONSETS)
    assert all(abs(a - o) < 0.05 for (a, _), o in zip(spans, ONSETS))


def test_a_still_head_with_micro_motion_passes():
    n = C.Noise(4, base_hz=0.25, octaves=3)
    r, _ = judge(lambda x: 0.5 * n.at(x) + 0.25 * math.sin(2 * math.pi * 0.24 * x))
    assert r["pass"], r["failed"]
    assert all(abs(b["nod_deg"]) < 0.2 for b in r["blinks"])


def test_a_nod_with_every_blink_fails_and_says_what_to_do():
    n = C.Noise(4, base_hz=0.25, octaves=3)
    r, _ = judge(lambda x: 0.5 * n.at(x) + dip(x, ONSETS, 1.5))
    c = by_name(r)
    assert not c["blink_nod"]["pass"] and not c["blink_locked"]["pass"]
    assert "blink_head='still'" in c["blink_nod"]["why"]
    assert min(b["nod_deg"] for b in r["blinks"]) < -1.0  # down


def test_a_small_nod_on_every_blink_is_caught_by_the_average():
    """0.4 deg is under the per-blink line, but locked to every blink the triggered average still sees it."""
    n = C.Noise(4, base_hz=0.25, octaves=3)
    r, _ = judge(lambda x: 0.3 * n.at(x) + dip(x, ONSETS, 0.45))
    c = by_name(r)
    assert c["blink_nod"]["pass"]
    assert not c["blink_locked"]["pass"]


def test_a_turn_through_a_blink_is_not_a_nod():
    """A blink with a gaze shift (Evinger 1994: most big shifts carry one): the head turns and pitches smoothly
    through the window; the chord takes it out."""
    turn = lambda x: C.move(x, 2.05, 0.4, 0.0, 30.0)  # noqa: E731
    r, _ = judge(lambda x: C.move(x, 2.05, 0.4, 0.0, -6.0), yaw_fn=turn)
    assert by_name(r)["blink_nod"]["pass"], r["blinks"]
    assert by_name(r)["head_buzz"]["pass"]


def test_buzz_and_spikes_fail_head_buzz_but_fast_smooth_turns_do_not():
    rnd = random.Random(1)
    r, _ = judge(lambda x: 0.3 * rnd.uniform(-1, 1))
    assert not by_name(r)["head_buzz"]["pass"]
    r2, _ = judge(lambda x: 4.0 if abs(x - 4.6) < 0.02 else 0.0)  # one snapped frame
    assert not by_name(r2)["head_buzz"]["pass"]
    r3, _ = judge(lambda x: 0.0, yaw_fn=lambda x: C.move(x, 4.5, 0.4, 0.0, 32.0))  # perfkit: 32 deg in 0.39 s
    assert by_name(r3)["head_buzz"]["pass"], r3["jitter"]


def test_no_blinks_runs_only_the_buzz_check():
    t = C.grid(0, 5, RATE)
    r = ST.check(t, [0.0] * len(t), [])
    assert [c["name"] for c in r["checks"]] == ["head_buzz"]


# --- the fixes -----------------------------------------------------------------------------------------------------

def test_bridge_removes_a_dip_and_keeps_a_drift():
    t = C.grid(0, 3, 60.0)
    v = [0.5 * x + dip(x, [1.2], 2.0) for x in t]
    out, n = ST.still_through_blinks(t, v, [(1.25, 1.55)])
    assert n == 1
    assert max(abs(a - 0.5 * x) for a, x in zip(out, t)) < 0.1
    flat, n2 = ST.still_through_blinks(t, [0.5 * x for x in t], [(1.25, 1.55)])
    assert n2 == 0 and flat == [0.5 * x for x in t]


def test_hampel_removes_a_spike():
    v = [math.sin(i / 10) for i in range(100)]
    v[40] += 5.0
    out, n = ST.hampel(v)
    assert n >= 1 and abs(out[40] - math.sin(4.0)) < 0.1


def test_one_euro_calms_a_hold_and_follows_a_move():
    rnd = random.Random(2)
    hold = [rnd.gauss(0, 0.3) for _ in range(300)]
    out = ST.OneEuro(60.0).run(hold)
    sd = lambda xs: math.sqrt(sum(x * x for x in xs) / len(xs))  # noqa: E731
    assert sd(out[30:]) < 0.5 * sd(hold[30:])
    ramp = [min(30.0, i * 1.0) for i in range(120)]
    lag_fast = abs(ST.OneEuro(60.0, beta=0.05).run(ramp)[30] - ramp[30])
    lag_slow = abs(ST.OneEuro(60.0, beta=0.0).run(ramp)[30] - ramp[30])
    assert lag_fast < lag_slow


# --- perf.face: round 4's recipe fails, round 5's passes -----------------------------------------------------------

def solve_like_hers(length=20.0, seed=5):
    """A speech solve whose head drops 1.5 deg with each of its own (phrase-end) blinks, with a slow drift and a
    head translation that follows the pitch: the shape the 5.6+ audio solve's head can take."""
    rnd = random.Random(seed)
    ends = [1.2 + 2.5 * k + rnd.uniform(-0.4, 0.4) for k in range(int(length / 2.5))]
    g = C.grid(0, length, 60.0)
    nz = C.Noise(9, base_hz=0.3, octaves=3)
    blink = [blink_closure(x, [e + 0.1 for e in ends]) for x in g]
    pitch = [dip(x, ends) + nz.at(x) for x in g]
    base = {"HeadYaw": (g, [-p for p in pitch]), "HeadRoll": (g, [0.0] * len(g)), "HeadPitch": (g, [0.0] * len(g)),
            "CTRL_expressions_eyeBlinkL": (g, blink), "CTRL_expressions_eyeBlinkR": (g, blink),
            "HeadTranslationZ": (g, [0.3 * p for p in pitch]),
            "CTRL_expressions_jawOpen": (g, [abs(math.sin(x * 9)) * 0.6 for x in g])}
    return base, ends


HER = dict(shifts=[{"t": 0.0, "yaw": -50.0, "pitch": 5.0, "scan": "face", "head": 0.1},
                   {"t": 2.75, "yaw": 0.0, "pitch": 0.0, "scan": "lens", "head": 1.0},
                   {"t": 12.5, "yaw": -45.0, "pitch": 3.0, "scan": "face", "head": 0.6},
                   {"t": 13.2, "yaw": 0.0, "pitch": 0.0, "scan": "lens", "head": 1.0}],
           start_gaze=(-36.5, 3.6), blink_state="listen", tilts=[{"t": 7.0, "until": 9.0, "roll_deg": 5.0}],
           nods=[{"t": 15.5, "kind": "nod", "depth_deg": 3.0}], seed=17, signs=REEL)


def build(**kw):
    base, ends = solve_like_hers()
    return F.build(0.0, 20.0, base=base, phrase_ends=ends, emphasis=[(e - 0.3, 0.8) for e in ends], **{**HER, **kw})


def checks(r):
    return {c["name"]: c["pass"] for c in r["report"]["checks"]}


def test_round4_recipe_nods_with_the_blinks():
    r = build(solver_head="soften", blink_head="free")
    c = checks(r)
    assert not c["blink_nod"] and not c["blink_locked"], r["report"]["head_stability"]


@pytest.mark.parametrize("solver_head", ["replace", "clean", "soften"])
def test_round5_keeps_the_head_still_through_blinks(solver_head):
    r = build(solver_head=solver_head)
    c = checks(r)
    assert c["blink_nod"] and c["blink_locked"] and c["blink_speed"] and c["head_buzz"], r["report"]["head_stability"]
    assert c["frozen_head"]  # still through the blinks, alive between them
    assert r["plan"]["blink_head"] == "still"


def test_round5_defaults_drop_the_solver_head_and_keep_the_lip_sync():
    r = build()
    assert r["plan"]["solver_head"] == "replace"
    assert r["curves"]["HeadTranslationZ"][1] == [0.0, 0.0]  # dropped with the rotation
    assert "CTRL_expressions_jawOpen" not in r["curves"]  # the mouth is never touched (agent-01's lip checks)
    clean = build(solver_head="clean")
    assert clean["plan"]["solver"]["bridged"] > 0
    tz = clean["curves"]["HeadTranslationZ"]
    assert max(abs(v) for v in tz[1]) > 0.0  # kept, cleaned


def test_gaze_blinks_no_longer_ride_the_chin_dip():
    """Offline on her round-4 plan: 3 of 9 blinks were gaze blinks dipping 0.8-1.6 deg (gaze.py's chin dip of the
    same turn). Still: none of them moves the head."""
    free = build(solver_head="replace", blink_head="free")
    still = build(solver_head="replace")
    nods = lambda r: [b for b in r["report"]["head_stability"]["blinks"] if abs(b["nod_deg"]) >= 0.5]  # noqa: E731
    assert nods(free)
    assert not nods(still)


def test_blinks_keep_off_nods():
    r = build(solver_head="replace")
    nod_t = 15.5
    assert not any(nod_t - 0.05 < b["t"] + b["dur_s"] and b["t"] < nod_t + 0.55 for b in r["plan"]["blinks"])


def test_bad_modes_are_refused_with_the_choices():
    with pytest.raises(ValueError, match="clean"):
        F.build(0, 2, solver_head="filter")
    with pytest.raises(ValueError, match="still"):
        F.build(0, 2, blink_head="nod")


def test_report_carries_the_stability_numbers():
    rep = M.report(build()["curves"] | solve_like_hers()[0], REEL)
    assert {"blink_nod", "blink_locked", "blink_speed", "head_buzz"} <= {c["name"] for c in rep["checks"]}


# --- bones and the render ----------------------------------------------------------------------------------------

def rot_x(deg):
    a = math.radians(deg)
    return [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]


def test_from_bones_reads_pitch_whatever_the_bone_axes():
    """A head bone whose local Y points forward and Z to the side (MetaHuman bones are not X-forward): pitching it
    by p must read p. Actor forward is +X, up +Z."""
    frames, samples, want = list(range(60)), [], []
    for f in frames:
        p = 5.0 * math.sin(f / 9)
        want.append(p)
        a = math.radians(p)
        fwd = [math.cos(a), 0.0, math.sin(a)]
        side = [0.0, 1.0, 0.0]
        upv = [-math.sin(a), 0.0, math.cos(a)]
        samples.append([0, 0, 160] + upv + fwd + side)  # axis_x = up, axis_y = forward, axis_z = side
    h = ST.from_bones(frames, 24.0, samples, [1.0, 0.0, 0.0])
    assert h["axes"]["forward"] == ["y", 1.0]
    assert max(abs(a - b) for a, b in zip(h["pitch"], want)) < 1e-6


def test_render_pose_from_rigid_landmarks():
    cv2 = pytest.importorskip("cv2")  # noqa: F841
    from filmtools.unreal import qa_head as QH
    rnd = random.Random(3)
    model = [[rnd.uniform(-60, 60), rnd.uniform(-80, 60), rnd.uniform(-30, 30)] for _ in QH.RIGID]
    w, h = 1280, 720
    for pitch in (-4.0, 0.0, 3.0):
        R = rot_x(pitch)
        pts = []
        for x, y, z in model:
            X = [sum(R[i][k] * v for k, v in enumerate((x, y, z))) for i in range(3)]
            Z = X[2] + 900.0
            pts.append([w * X[0] / Z + w / 2, w * X[1] / Z + h / 2])
        base = []
        for x, y, z in model:
            Z = z + 900.0
            base.append([w * x / Z + w / 2, w * y / Z + h / 2])
        got = QH.rel_pose([[x, y, z] for x, y, z in model], pts, (w, h))[0]
        assert abs(got - pitch) < 0.3, (got, pitch)


def test_render_judge_tells_a_nod_from_a_tracker_artifact():
    from filmtools.unreal import qa_head as QH
    t = C.grid(0, 10.5, 24.0)
    blink = [blink_closure(x, ONSETS) * 0.8 for x in t]
    nod = [dip(x, ONSETS, 1.6) for x in t]
    flat = [0.0] * len(t)
    real = QH.judge({"times": t, "pitch": nod, "yaw": flat, "roll": flat, "pitch_matrix": nod, "blink": blink})
    assert not real["pass"] and any(i["code"] == "head.blink_nod" for i in real["issues"])
    art = QH.judge({"times": t, "pitch": flat, "yaw": flat, "roll": flat, "pitch_matrix": nod, "blink": blink})
    assert art["pass"] and any(i["code"] == "head.tracker_artifact" for i in art["issues"])


def test_head_gate_reports_the_worst_blink_and_errors_on_missing_numbers(tmp_path):
    import json
    from filmtools.unreal import qa_head as QH
    a = tmp_path / "her.json"
    a.write_text(json.dumps({"label": "Presenter", "frames": [1056, 1584], "fps": 24.0,
                             "blinks": [{"t": 1.0, "nod_deg": -0.2}, {"t": 2.0, "nod_deg": -1.4}],
                             "bta": {"peak_deg": 0.62}}))
    b = tmp_path / "him.json"
    b.write_text(json.dumps({"label": "Host", "frames": [960, 1584], "fps": 24.0, "blinks": []}))
    g = QH.gate([str(a)])["gate"]["head.blink_nod_deg"]
    assert g["value"] == 1.4 and g["where"].startswith("Presenter f1104-") and g["value"] > QH.GATE_LINE_DEG
    lk = QH.gate([str(a)])["gate"]["head.blink_locked_deg"]
    assert lk["value"] == 0.62 and lk["value"] > QH.GATE_LOCKED_DEG
    both = QH.gate([str(a), str(b)])["gate"]
    assert "error" in both["head.blink_nod_deg"] and "error" in both["head.blink_locked_deg"]


# --- natural-motion presets and body life --------------------------------------------------------------------------

def test_presets_fill_under_what_is_given():
    from perfkit import presets as PR
    a = PR.face_args("listener", {"energy": 1.3, "head": {"micro_deg": 0.4}})
    assert a["energy"] == 1.3 and a["blink_state"] == "listen" and a["beat_every"] == 0
    assert a["head"]["micro_deg"] == 0.4 and a["head"]["speech_gain"] == 0.0
    assert all(p["face"]["blink_head"] == "still" and p["face"]["solver_head"] == "replace"
               for p in PR.PRESETS.values())
    with pytest.raises(ValueError, match="presenter_calm"):
        PR.face_args("robot", {})


def test_no_beat_nods_for_a_listener():
    r = F.build(0, 8, emphasis=[(1, 1), (3, 1), (5, 1)], beat_every=0, seed=1)
    assert not [n for n in r["plan"]["nods"] if n["kind"] == "beat"]


def test_breathing_is_never_a_metronome():
    from perfkit import bodylife as BL
    life = BL.plan(0, 60, state="talk", seed=3)
    assert 0.1 <= life["breath_cv"] <= 0.35
    old = BL.plan(0, 60, state="talk", seed=3, breath_cv=0.0, breath_depth_cv=0.0)
    assert old["breath_cv"] == 0.0
    flex = life["bones"]["spine_05"]["flex"]
    assert min(flex) < -0.1 and max(flex) <= 1e-9  # extension on the inhale, back to rest


def test_blinks_on_another_clock_are_refused_not_dropped():
    """r5 box: qa.head_stability found her blinks on the sequence's clock (45-65 s) and judged them on samples from 0;
    every blink was dropped and the gate read 0.0 for round 4. That must raise."""
    t = C.grid(0, 10.5, RATE)
    with pytest.raises(ValueError, match="same clock"):
        ST.check(t, [0.0] * len(t), [(45.0 + a, 45.3 + a) for a in ONSETS])


def test_bone_samples_from_a_late_frame_find_the_blinks():
    """The op's path end to end on bone samples that start at master frame 1080 (her screen time)."""
    import json
    from filmtools.unreal import qa_head as QH
    fps, f0 = 24.0, 1080
    frames = list(range(f0, f0 + 480))
    samples, closure = [], []
    for f in frames:
        x = (f - f0) / fps
        p = math.radians(dip(x, ONSETS, 1.5))
        samples.append([0, 0, 160] + [-math.sin(p), 0.0, math.cos(p)] + [math.cos(p), 0.0, math.sin(p)] + [0.0, 1.0, 0.0])
        closure.append(blink_closure(x, ONSETS))
    path = Path(__file__).parent / "_tmp_head_samples.json"
    try:
        path.write_text(json.dumps({"samples": {"frames": frames, "fps": fps, "bone": samples, "closure": closure,
                                                "forward": [1.0, 0.0, 0.0]}}))
        r = QH.samples(str(path))
        g = QH.gate([str(path)])["gate"]  # the gate re-judges saved samples (the box's first files had no blinks)
        # agent-09's scope.json keys are who, the file is head_<who>.json: the first blink's frames off screen
        sc = QH.gate([str(path)], seen={"samples": [[1080 + 30, 1560]]})
        none = QH.gate([str(path)], seen={"someone_else": [[0, 10]]})
    finally:
        path.unlink()
    assert len(r["blinks"]) == len(ONSETS)
    assert "blink_nod" in r["failed"]
    assert "error" not in g["head.blink_nod_deg"] and g["head.blink_nod_deg"]["value"] > 1.0
    assert g["head.blink_nod_deg"]["where"].startswith("_tmp_head_samples f1")
    assert len(sc["out_of_scope"]) == 1 and 1095 <= sc["out_of_scope"][0]["frame"] <= 1102
    assert "error" in none["gate"]["head.blink_nod_deg"]


def test_a_blink_cut_by_the_end_of_the_samples_is_not_judged():
    """r5 box: his last blink, cut off by the end of his screen time with the head moving, scored 5.8 deg."""
    t = C.grid(0, 10.5, RATE)
    onsets = ONSETS + [10.35]
    clos = [blink_closure(x, onsets) for x in t]
    r = ST.check(t, [(-8.0 * (x - 10.2) if x > 10.2 else 0.0) for x in t], ST.blink_windows(t, clos))
    assert r["pass"], r["failed"]
    assert len(r["edge"]) == 1 and len(r["blinks"]) == len(ONSETS)


def test_turn_blinks_are_nods_by_default_and_listed_only_when_asked():
    """r5 box: his return turn (-94 -> 0 deg in 16 frames) carried its gaze blink and dipped 2.9 deg in pitch, his face
    flat: judged as the turn's path (head_turn_dip, a warning over 2 deg), not as a blink nod."""
    t = C.grid(0, 10.5, RATE)
    yaw = lambda x: C.move(x, 5.15, 0.6, -90.0, 0.0)  # noqa: E731
    pitch = lambda x: dip(x, [5.15], 4.0, 0.6)  # noqa: E731
    off, _ = judge(pitch, yaw_fn=yaw)  # the default (the orchestrator's r5 ruling): a turn blink is judged as a nod
    assert not off["turns"] and min(b["nod_deg"] for b in off["blinks"]) < -2.0
    t = C.grid(0, 10.5, RATE)
    r = ST.check(t, [pitch(x) for x in t], ST.blink_windows(t, [blink_closure(x, ONSETS) for x in t]),
                 yaw=[yaw(x) for x in t], limits={"turn_deg": 20.0})
    c = by_name(r)
    assert c["blink_nod"]["pass"] and c["blink_locked"]["pass"], r["blinks"]
    assert len(r["turns"]) == 1 and not c["head_turn_dip"]["pass"] and c["head_turn_dip"]["severity"] == "warn"
    assert r["pass"]  # a warning does not fail


def test_off_screen_blinks_are_listed_not_judged():
    t = C.grid(0, 10.5, RATE)
    spans = ST.blink_windows(t, [blink_closure(x, ONSETS) for x in t])
    pitch = [dip(x, ONSETS[3:5], 2.0) for x in t]
    assert not ST.check(t, pitch, spans)["pass"]
    r = ST.check(t, pitch, spans, seen=[(0.0, 4.5), (7.5, 10.5)])
    assert r["pass"] and len(r["unseen"]) == 2 and r["unseen"][0]["nod_deg"] < -1.5
