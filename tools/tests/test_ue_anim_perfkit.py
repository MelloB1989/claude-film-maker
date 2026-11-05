"""WP4: perfkit, the pure performance synthesis (no engine): easing, eye-head coordination, nods, blinks, expressions,
audio emphasis, naturalness metrics, the animation library, body plans and the PERFORMANCE spec compiler."""
from __future__ import annotations

import json
import math
import struct
import sys
import wave
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "unreal" / "fmbridge"))

from perfkit import audio as AU  # noqa: E402
from perfkit import blinks as B  # noqa: E402
from perfkit import body as BD  # noqa: E402
from perfkit import curves as C  # noqa: E402
from perfkit import expressions as X  # noqa: E402
from perfkit import eyes as E  # noqa: E402
from perfkit import face as F  # noqa: E402
from perfkit import gaze as G  # noqa: E402
from perfkit import head as H  # noqa: E402
from perfkit import library as L  # noqa: E402
from perfkit import metrics as M  # noqa: E402
from perfkit import rig as R  # noqa: E402
from perfkit import spec as S  # noqa: E402


def vel(f, t, h=1e-4):
    return (f(t + h) - f(t - h)) / (2 * h)


# --- rig vocabulary ---------------------------------------------------------------------------------------------

def test_rig_has_the_verified_curves():
    assert len(R.CURVES) == 251
    assert "CTRL_expressions_eyeBlinkL" in R.CURVES and "CTRL_expressions_mouthCornerPullR" in R.CURVES
    bad = R.unknown(["eyeBlinkL", "mouthSmileL"])
    assert [b["name"] for b in bad] == ["mouthSmileL"] and bad[0]["did_you_mean"]


def test_every_preset_curve_is_a_real_metahuman_curve():
    for name in X.PRESETS:
        for c in X.expand(name):
            assert c in R.CURVES, (name, c)
    for mood, layers in X.MOODS.items():
        assert mood in X.SOLVER_MOOD
        for preset, _ in layers:
            assert preset in X.PRESETS


# --- curves -----------------------------------------------------------------------------------------------------

def test_min_jerk_and_skew():
    assert C.min_jerk(0) == 0 and C.min_jerk(1) == 1 and abs(C.min_jerk(0.5) - 0.5) < 1e-9
    # the peak speed of a skewed move comes early
    us = [i / 400 for i in range(1, 400)]
    peak = max(us, key=lambda u: vel(lambda x: C.skewed(x, 0.4), u))
    assert 0.33 < peak < 0.47


def test_move_overshoots_then_settles_continuously():
    f = lambda t: C.move(t, 0.0, 0.3, 0.0, 10.0, 0.42, 0.08, 0.4)  # noqa: E731
    assert abs(f(0.3) - 10.8) < 1e-6  # the peak carries 8% past
    assert abs(f(3.0) - 10.0) < 0.01  # and settles home
    assert min(f(0.3 + i / 100) for i in range(150)) < 10.0  # with a small undershoot
    # continuous in value and velocity where the move hands over to the settle
    assert abs(f(0.3 - 1e-6) - f(0.3 + 1e-6)) < 1e-4
    assert abs(vel(f, 0.3 - 1e-3)) < 2.0 and abs(vel(f, 0.3 + 1e-3)) < 2.0


def test_settle_starts_flat():
    assert C.settle(0, 0.4) == 1.0
    assert abs((C.settle(1e-4, 0.4) - 1.0) / 1e-4) < 0.05
    assert C.settle(5.0, 0.4) == 0.0


def test_noise_is_deterministic_smooth_and_bounded():
    a, b = C.Noise(5), C.Noise(5)
    vals = [a.at(i / 30) for i in range(300)]
    assert vals == [b.at(i / 30) for i in range(300)]
    assert max(abs(v) for v in vals) < 1.2
    assert max(abs(x - y) for x, y in zip(vals, vals[1:])) < 0.1  # no jumps at 30 Hz


def test_reduce_stays_within_tolerance():
    t = C.grid(0, 4, 60)
    v = [math.sin(x * 2) * 10 for x in t]
    rt, rv = C.reduce(t, v, 0.05)
    assert len(rt) < len(t) / 3 and rt[0] == t[0] and rt[-1] == t[-1]
    assert max(abs(C.at(rt, rv, x) - y) for x, y in zip(t, v)) <= 0.05 + 1e-9


def test_lowpass_is_zero_phase():
    t = C.grid(0, 4, 60)
    v = [math.exp(-((x - 2) ** 2) / 0.05) for x in t]
    lp = C.lowpass(v, 60, 3.0)
    assert abs(t[lp.index(max(lp))] - 2.0) < 0.02  # the peak does not move


# --- gaze and head ----------------------------------------------------------------------------------------------

def test_head_share_grows_with_amplitude():
    assert G.head_share(4) < 0.2
    assert G.head_share(20) > G.head_share(10)
    assert 0.8 < G.head_share(60) <= 0.97
    assert G.head_share(30, "pitch") < G.head_share(30, "yaw")


def test_saccade_main_sequence():
    assert abs(G.saccade_s(10) - 0.043) < 1e-6
    assert G.saccade_s(100) == 0.15


def test_eyes_lead_the_head_and_the_vor_holds_the_gaze():
    plan = G.GazePlan([G.Shift(1.0, 30.0)], seed=1)
    ev = plan.events[0]
    assert ev["t_head"] > ev["t_eye"]  # eyes first
    assert plan.gaze(1.06)[0] > 25 and plan.head_base(1.06)[0] < 5  # eyes are there, the head is not yet
    head = H.compose(0, 3, plan, style=H.Style(micro_deg=0, breath_deg=0), rate=120)
    eyes = E.solve(plan, head, micro_deg=0.0, vergence=False)
    i = head["times"].index(min(head["times"], key=lambda t: abs(t - 2.5)))
    # once settled, eye-in-head + head = the target
    assert abs(eyes["L"][i][0] + head["yaw"][i] - 30.0) < 0.3
    assert 15 < head["yaw"][i] < 29


def test_head_lead_mode_turns_the_head_first():
    plan = G.GazePlan([G.Shift(1.0, 30.0)], lead="head", seed=1)
    assert plan.events[0]["t_head"] < plan.events[0]["t_eye"]
    with pytest.raises(ValueError):
        G.GazePlan([], lead="sideways")


def test_big_turn_dips_the_chin():
    plan = G.GazePlan([G.Shift(1.0, 40.0)], seed=2)
    p = [plan.head_base(1.0 + i / 50)[1] for i in range(40)]
    assert min(p) < -0.5 and abs(plan.head_base(4.0)[1]) < 0.01


def test_yes_nod_drops_rebounds_and_settles():
    n = H.Nod(1.0, "nod", 5.0)
    vals = [n.at(1.0 + i / 200) for i in range(400)]
    assert min(vals) == pytest.approx(-5.0, abs=0.2)
    assert max(vals) > 0.5  # the rebound past level
    assert abs(n.at(4.0)) < 0.05
    assert all(abs(a - b) < 0.6 for a, b in zip(vals, vals[1:]))  # no jumps at 200 Hz
    with pytest.raises(ValueError):
        H.Nod(0, "maybe")


def test_repeated_nods_shrink_and_no_shakes_yaw():
    n = H.Nod(0.0, "nod", 6.0, count=3)
    lows = []
    for k in range(3):
        a = k * (0.16 + 0.24 * 0.8)
        lows.append(min(n.at(a + i / 200) for i in range(60)))
    assert lows[0] < lows[1] < lows[2] < 0
    assert H.Nod(0, "shake").axis() == "yaw" and H.Nod(0, "no").kind == "shake"


def test_compose_is_alive_and_deterministic():
    plan = G.GazePlan([G.Shift(0.5, 20.0)], seed=3)
    a = H.compose(0, 4, plan, style=H.Style(seed=3))
    b = H.compose(0, 4, plan, style=H.Style(seed=3))
    assert a == b
    rig = H.to_rig(a)
    assert M.frozen_head(rig)["pass"] and M.head_linear(rig)["pass"]


def test_to_rig_applies_signs():
    h = {"times": [0, 1], "yaw": [0, 10], "pitch": [0, 5], "roll": [0, 2]}
    out = H.to_rig(h, R.HeadSigns(yaw=-1, pitch=1, roll=-1), tol_deg=0)
    assert out["HeadYaw"][1][-1] == -10 and out["HeadPitch"][1][-1] == 5 and out["HeadRoll"][1][-1] == -2
    assert out["HeadControlSwitch"][1] == [1.0, 1.0]
    back = H.from_rig(out, R.HeadSigns(yaw=-1, pitch=1, roll=-1))
    assert back["yaw"][1][-1] == 10


def test_naturalize_softens_jitter():
    t = C.grid(0, 4, 30)
    raw = [5 * math.sin(x) + (0.8 if i % 2 else -0.8) for i, x in enumerate(t)]
    jitter = M.head_jitter({"HeadYaw": (t, raw)})
    nt, nv = H.naturalize(t, raw)
    assert M.head_jitter({"HeadYaw": (nt, nv)})["metric"] < jitter["metric"] / 3


# --- eyes -------------------------------------------------------------------------------------------------------

def test_vergence_turns_the_eyes_in():
    plan = G.GazePlan([G.Shift(0.0, 0.0, dist_cm=40.0, scan="still")], seed=0)
    head = H.compose(0, 1, plan, style=H.Style(micro_deg=0, breath_deg=0))
    eyes = E.solve(plan, head, micro_deg=0.0)
    yl, yr = eyes["L"][-1][0], eyes["R"][-1][0]
    assert yl < 0 < yr and abs(yr - yl - 2 * math.degrees(math.atan(3.1 / 40))) < 0.2


def test_eye_curves_are_clamped_and_round_trip():
    plan = G.GazePlan([G.Shift(0.5, 15.0, -8.0, scan="still")], seed=0)
    head = H.compose(0, 2, plan, style=H.Style(micro_deg=0, breath_deg=0))
    eyes = E.solve(plan, head, micro_deg=0.0, vergence=False)
    cur = E.to_rig(eyes, tol=0.0)
    assert all(0.0 <= v <= 1.0 for _, vs in cur.values() for v in vs)
    back = E.angles_from_rig(cur)
    t = back["times"][-1]
    i = eyes["times"].index(min(eyes["times"], key=lambda x: abs(x - t)))
    assert abs(back["L"][-1][0] - eyes["L"][i][0]) < 0.2 and abs(back["L"][-1][1] - eyes["L"][i][1]) < 0.2


def test_face_scanning_moves_between_eyes_and_mouth():
    plan = G.GazePlan([G.Shift(0.0, 0.0, dist_cm=100.0, scan="face")], seed=4)
    times = C.grid(0, 8, 30)
    offs = E.fixation_offsets(plan, times, seed=4)
    ys = {round(y, 0) for y, _ in offs[30:]}
    assert len(ys) >= 2 and min(p for _, p in offs) < -2.0  # visits the mouth (below)


# --- blinks -----------------------------------------------------------------------------------------------------

def test_spontaneous_blinks_are_irregular_at_a_human_rate():
    bl = B.plan(0, 120, "talk", seed=1)
    rate = len(bl) / 2.0
    assert 15 < rate < 32
    gaps = [b.t - a.t for a, b in zip(bl, bl[1:])]
    m = sum(gaps) / len(gaps)
    cv = math.sqrt(sum((g - m) ** 2 for g in gaps) / len(gaps)) / m
    assert cv > 0.3
    assert min(gaps) >= 0.2  # double blinks come close, others not


def test_blink_shape_closes_faster_than_it_opens():
    b = B.Blink(0.0)
    assert b.close_s < b.open_s
    assert b.at(b.close_s + b.hold_s / 2) == pytest.approx(1.0)
    assert b.at(-0.01) == 0 and b.at(b.end() + 0.01) == 0


def test_big_gaze_shift_brings_a_blink():
    plan = G.GazePlan([G.Shift(1.0, 45.0)], seed=0)
    hits = 0
    for seed in range(20):
        bl = B.plan(0, 3, "focus", gaze_events=plan.events, seed=seed, rate_per_min=0.001)
        hits += any(b.cause == "gaze" and abs(b.t - 1.0) < 0.05 for b in bl)
    assert hits >= 17


def test_blink_curves_and_detection():
    bl = [B.Blink(1.0), B.Blink(3.0, peak=0.7)]
    cur = B.to_curves(bl, 0, 5)
    t, v = cur[R.blink("L")]
    found = B.detect(t, v, 0.5)
    assert len(found) == 2 and abs(found[0][0] - 1.05) < 0.06
    assert len(t) < 80  # sparse: dense only around blinks


# --- expressions ------------------------------------------------------------------------------------------------

def test_duchenne_smile_cheeks_follow_the_mouth():
    ev = X.Event("smile", 1.0, 3.0, intensity=1.0, asym=0.0, lead_s=0.0)
    cur = X.render([ev], 0, 4, rate=200)
    corner, cheek = cur["CTRL_expressions_mouthCornerPullL"], cur["CTRL_expressions_eyeCheekRaiseL"]

    def onset(c):
        return next(t for t, v in zip(*c) if v > 0.05)
    assert onset(cheek) > onset(corner) + 0.04
    assert max(corner[1]) > 0.5


def test_asymmetry_left_stronger():
    cur = X.render([X.Event("brow_raise", 0.5, 2.0, intensity=0.8, asym=0.5)], 0, 3)
    assert max(cur["CTRL_expressions_browRaiseInL"][1]) > max(cur["CTRL_expressions_browRaiseInR"][1]) * 1.2


def test_mouth_mix_quiets_a_smile_on_a_talking_mouth():
    ev = [X.Event("smile", 0.0, 4.0, intensity=1.0, lead_s=0)]
    loud = X.render(ev, 0, 4, speech=lambda t: 1.0, mouth_mix=0.4)
    quiet = X.render(ev, 0, 4)
    assert max(loud["CTRL_expressions_mouthCornerPullL"][1]) < 0.5 * max(quiet["CTRL_expressions_mouthCornerPullL"][1])
    assert max(loud["CTRL_expressions_eyeCheekRaiseL"][1]) == pytest.approx(max(quiet["CTRL_expressions_eyeCheekRaiseL"][1]))


def test_unknown_preset_and_mood_suggest():
    with pytest.raises(ValueError, match="did you mean smile"):
        X.expand("smiel")
    with pytest.raises(ValueError, match="moods"):
        X.mood_events([{"t0": 0, "t1": 1, "mood": "grumpy"}])


def test_moods_cross_fade():
    ev = X.mood_events([{"t0": 0, "t1": 5, "mood": "happy"}, {"t0": 5, "t1": 10, "mood": "sad"}], blend_s=1.0)
    cur = X.render(ev, 0, 10)
    smile = cur["CTRL_expressions_mouthCornerPullL"]
    sad = cur["CTRL_expressions_mouthCornerDepressL"]
    assert C.at(*smile, 2.5) > 0.1 and C.at(*smile, 8) < 0.01
    assert C.at(*sad, 8) > 0.05 and C.at(*sad, 2.5) < 0.01
    assert 0.01 < C.at(*smile, 4.9) < C.at(*smile, 3.5)  # fading through the boundary


def test_swallow_runs_its_phases_in_order():
    s = X.swallow(1.0)
    peaks = [max(zip(*s[f"CTRL_expressions_neckSwallowPh{i}"]), key=lambda p: p[1])[0] for i in range(1, 5)]
    assert peaks == sorted(peaks)


# --- audio ------------------------------------------------------------------------------------------------------

def _wav(path, segments, sr=16000):
    """segments: [(seconds, amplitude 0..1)] of a 200 Hz tone (0 = silence)."""
    frames = bytearray()
    for sec, amp in segments:
        for i in range(int(sec * sr)):
            frames += struct.pack("<h", int(amp * 20000 * math.sin(2 * math.pi * 200 * i / sr)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(frames))
    return str(path)


def test_audio_pauses_and_emphasis(tmp_path):
    p = _wav(tmp_path / "l.wav", [(0.3, 0), (0.5, 0.3), (0.15, 1.0), (0.5, 0.3), (0.6, 0), (0.8, 0.3), (0.4, 0)])
    env = AU.Envelope.from_wav(p)
    assert abs(env.duration_s - 3.25) < 0.05
    ps = env.pauses()
    assert any(abs(a - 1.45) < 0.08 and b - a > 0.45 for a, b in ps)
    assert env.phrase_ends() and abs(env.phrase_ends()[0] - 1.45) < 0.08
    emph = env.emphasis()
    assert any(abs(t - 0.875) < 0.12 for t, _ in emph)
    assert env.at(0.1) < 0.2 and env.at(0.875) > 0.8


# --- metrics ----------------------------------------------------------------------------------------------------

def test_metrics_catch_a_robotic_face():
    robotic = {"HeadYaw": ([0, 1, 2, 3, 4, 5, 6, 7, 8], [0, 10, 10, -10, -10, 0, 0, 12, 0]),
               "HeadPitch": ([0, 8], [0, 0]), "HeadRoll": ([0, 8], [0, 0]),
               # metronome blinks, linear triangles: as fast to open as to close
               R.blink("L"): ([0] + [x for t in (1, 3, 5, 7) for x in (t - 0.1, t, t + 0.1)] + [8],
                              [0] + [0, 1, 0] * 4 + [0]),
               "CTRL_expressions_browRaiseInL": ([0, 4, 8], [0, 0.5, 0]),
               "CTRL_expressions_browRaiseInR": ([0, 4, 8], [0, 0.5, 0])}
    rep = M.report(robotic)
    assert not rep["pass"]
    assert {"head_linear", "frozen_head", "blink_regularity", "blink_shape", "asymmetry"} <= set(rep["failed"])


def test_metrics_pass_a_perfkit_face():
    r = F.build(0, 12, shifts=[{"t": 1, "yaw": 25}, {"t": 4, "yaw": 0, "scan": "lens"}, {"t": 7, "yaw": -30, "scan": "face"}],
                emphasis=[(2, 1), (3.1, .6), (5.5, .8), (8.2, 1), (10, .5)], phrase_ends=[3.6, 9.0],
                moods=[{"t0": 0, "t1": 12, "mood": "warm"}], seed=2)
    assert r["report"]["pass"], r["report"]["failed"]


def test_no_blinks_in_a_long_shot_fails():
    rep = M.blink_checks({"HeadYaw": ([0, 10], [0, 0])})
    assert not rep[0]["pass"] and "never blinks" in rep[0]["why"]


# --- face composition -------------------------------------------------------------------------------------------

def test_face_keeps_lip_sync_and_softens_the_solver_head():
    t = C.grid(0, 4, 30)
    base = {"CTRL_expressions_jawOpen": (t, [abs(math.sin(x * 9)) * 0.6 for x in t]),
            "HeadYaw": (t, [8 * math.sin(x * 3) + (0.7 if i % 2 else -0.7) for i, x in enumerate(t)])}
    r = F.build(0, 4, base=base, moods=[{"t0": 0, "t1": 4, "mood": "happy"}], speech=lambda x: 0.8)
    assert "CTRL_expressions_jawOpen" not in r["curves"]  # untouched: the lip-sync stays as solved
    assert M.head_jitter(r["curves"])["metric"] < M.head_jitter(base)["metric"]
    with pytest.raises(ValueError, match="layers"):
        F.build(0, 1, layers=["head", "ears"])


def test_face_blink_modes():
    base = {R.blink("L"): ([0, 1, 1.1, 1.3, 4], [0, 0, 1, 0, 0]), R.blink("R"): ([0, 4], [0, 0])}
    keep = F.build(0, 4, base=base, layers=["blinks"], blink_mode="keep")
    assert keep["curves"][R.blink("L")] == base[R.blink("L")]
    rep = F.build(0, 4, base=base, layers=["blinks"], blink_mode="replace", seed=3)
    assert rep["curves"][R.blink("L")] != base[R.blink("L")]


# --- library ----------------------------------------------------------------------------------------------------

def test_known_matches_the_workstation_inventory():
    inv = REPO / "films" / "host-studio" / "reel" / "previs" / "metahuman_animations.json"
    if not inv.exists():
        pytest.skip("no inventory in this checkout")
    assert {p for _, p in json.loads(inv.read_text())} == set(L.KNOWN)


def test_library_infer_and_search():
    i = L.infer(L.MH + "/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Walk_Loop_F")
    assert (i["kind"], i["category"], i["gait"], i["phase"], i["direction"]) == ("body", "locomotion", "walk", "loop", "forward")
    f = L.infer(L.MH + "/TemplateAnimations/Expression_Loops/HappyA/mhc_mh002_fmn_f_facialloop_happy_f_s001")
    assert (f["kind"], f["category"], f["emotion"]) == ("face", "expression_loop", "happy")
    top = L.search(L.KNOWN, "walk forward loop")[0]["path"]
    assert top.endswith("AS_MH_Neutral_Walk_Loop_F")
    assert L.search(L.KNOWN, "smiling face", kind="face")[0]["emotion"] == "happy"
    assert all(r["kind"] in ("face", "?") for r in L.search(L.KNOWN, "loop", kind="face"))


# --- body -------------------------------------------------------------------------------------------------------

def test_idles_cover_vary_and_split_around_gaps():
    clips = [{"anim": "/A/idle1", "length_s": 8}, {"anim": "/A/idle2", "length_s": 6}]
    secs = BD.idles(0, 30, clips, 24, gaps=[(10, 12)], seed=1)
    assert secs[0]["start"] == 0 and secs[-1]["end"] >= 30 * 24 - 1
    assert all(0.92 <= s["rate"] <= 1.08 for s in secs)
    assert len({s["offset"] for s in secs}) == len(secs)
    assert not any(s["start"] < 11 * 24 < s["end"] for s in secs)  # nothing under the gesture's middle


def test_gesture_stroke_lands_before_the_beat():
    lib = {"palms": {"anim": "/A/palms", "length_s": 2.0, "stroke_s": 0.8}}
    secs, notes = BD.place_gestures([{"name": "palms", "at_s": 3.0}, {"name": "palms", "at_s": 3.5},
                                     {"name": "nope", "at_s": 5}], lib, 24)
    assert secs[0]["stroke_frame"] == round((3.0 - 0.08) * 24)
    assert any("dropped" in n for n in notes)  # the overlapping one and the unknown one


def test_walk_reaches_the_point_with_eased_speed():
    w = BD.walk(1.0, [0, 0, 0], [[300, 400, 0]], 24, speed_cm_s=150, yaw0=0.0)
    assert w["keys"][-1][1] == [300.0, 400.0, 0.0]
    assert w["distance_cm"] == 500.0
    # it turned toward the goal first (53 deg off its facing)
    assert w["keys"][0][1] == [0.0, 0.0, 0.0] and abs(w["yaw_end"] - math.degrees(math.atan2(400, 300))) < 1
    pos = [(k[0], k[1]) for k in w["keys"]]
    speeds = [math.dist(a[1], b[1]) / ((b[0] - a[0]) / 24) for a, b in zip(pos, pos[1:]) if b[0] > a[0]]
    assert max(speeds) == pytest.approx(150, rel=0.08) and speeds[-1] < 60


def test_turn_unwraps_the_short_way():
    keys, _ = BD.turn(0, 170, -170, 24)
    assert keys[-1][1] == pytest.approx(190)
    assert BD.unwrap(10, 350) == -10


# --- the PERFORMANCE spec ---------------------------------------------------------------------------------------

SPEC = {"kind": "performance", "version": 1, "name": "demo", "sequence": "/Game/S/Seq", "actor": "Host", "camera": "Cam",
        "targets": {"guest": "Guest:Face:head", "desk": [300, 100, 80]},
        "library": {"idle": ["/Game/A/idle"], "walk": {"anim": "/Game/A/walk", "speed_cm_s": 150},
                    "gestures": {"palms": {"anim": "/Game/A/palms", "stroke_s": 0.7}}},
        "lines": [{"id": "l1", "audio": "/w/l1.wav", "mood": "warm",
                   "gaze": [{"at_s": 0, "target": "camera"}, {"at_s": 2.4, "target": "guest", "scan": "face"}],
                   "gestures": [{"name": "palms", "at_s": 1.1}],
                   "expressions": [{"preset": "smile", "at_s": 2.6, "duration_s": 1.4, "intensity": 0.6}],
                   "nods": [{"at_s": 3.0, "kind": "nod"}]},
                  {"id": "beat", "duration_s": 1.5, "listen": True, "gaze": [{"at_s": 0, "target": "guest", "scan": "face"}]}],
        "actions": [{"at_s": 6.0, "walk_to": "desk", "speed_cm_s": 120, "end_facing": "camera"}]}
STATE = {"fps": 24, "actor": {"loc": [0, 0, 0], "yaw": 0, "head_z_cm": 165, "face_mesh": "/Game/MH/Face"},
         "targets": {"camera": [300, 0, 165], "guest": [100, 200, 165], "desk": [300, 100, 80]},
         "clips": {"/Game/A/idle": {"length_s": 8}, "/Game/A/palms": {"length_s": 2.2},
                   "/Game/A/walk": {"length_s": 1.1}},
         "audio": {"l1": {"duration_s": 4.0, "emphasis": [[1.2, 1], [2.9, 0.7]], "phrase_ends": [2.0]}}}


def test_spec_validation_names_the_problem():
    bad = json.loads(json.dumps(SPEC))
    bad["lines"][0]["mood"] = "grumpy"
    bad["lines"][0]["gestrues"] = []
    bad["lines"][1].pop("duration_s")
    bad["actions"][0]["walk_to"] = None
    errs = S.validate(bad)
    assert any("grumpy" in e for e in errs) and any("gestrues" in e for e in errs)
    assert any("needs audio, face_anim or duration_s" in e for e in errs)
    assert S.validate(SPEC) == []


def test_timeline_follows_audio_and_gaps():
    tl = S.timeline(SPEC, STATE)
    assert tl[0]["end_s"] == 4.0 and tl[1]["start_s"] == pytest.approx(4.35) and tl[1]["listen"]


def test_targets_in_the_characters_frame():
    # a target on the actor's right (Unreal +Y) is negative yaw (the character's right)
    y, p, d = S.target_angles([0, 100, 165], {}, [0, 0, 0], 0.0, 165)
    assert y == pytest.approx(-90) and p == pytest.approx(0) and d == pytest.approx(100)
    y, p, _ = S.target_angles([100, -100, 65], {}, [0, 0, 0], 0.0, 165)
    assert y == pytest.approx(45) and p < -30


def test_compile_places_everything():
    c = S.compile(SPEC, STATE)
    f = c["face"]
    assert [round(s["t"], 2) for s in f["shifts"]] == [0.0, 2.4, 4.35]
    assert f["shifts"][1]["yaw"] < -40  # the guest is on the right
    assert any(abs(t - 1.2) < 1e-6 for t, _ in f["emphasis"])
    assert {"t0": 0.0, "t1": 4.0, "mood": "warm", "intensity": 1.0} in f["moods"]
    kinds = {s["kind"] for s in c["body"]}
    assert kinds == {"idle", "gesture", "walk"}
    g = next(s for s in c["body"] if s["kind"] == "gesture")
    assert g["stroke_frame"] == round((1.1 - 0.08) * 24)
    assert c["transform"][-1][1][:2] == [300.0, 100.0] and c["duration_s"] > 6.0
    built = F.build(**{k: v for k, v in f.items() if k != "talk_spans"})
    assert built["report"]["pass"], built["report"]["failed"]


def test_plan_solves_then_composes_then_converges():
    steps = S.plan(SPEC, STATE)
    assert [s["op"] for s in steps] == ["perf.solve", "perf.compose"]
    assert steps[0]["args"]["mood"] == "HAPPINESS" and steps[0]["args"]["face_mesh"] == "/Game/MH/Face"
    st = dict(STATE, solves={"l1": {"anim": "/x", "key": steps[0]["args"]["key"]}})
    st["face"] = {"fingerprint": S.fingerprint(SPEC, st)}
    assert S.plan(SPEC, st) == []
    changed = json.loads(json.dumps(SPEC))
    changed["lines"][0]["mood"] = "sad"
    assert [s["op"] for s in S.plan(changed, st)] == ["perf.solve", "perf.compose"]


def test_plot_draws_a_strip_per_part(tmp_path):
    from perfkit import plot as PL
    from camkit import png
    r = F.build(0, 6, shifts=[{"t": 1, "yaw": 25}], emphasis=[(2, 1)], moods=[{"t0": 0, "t1": 6, "mood": "happy"}], seed=1)
    img = PL.performance(r["curves"], marks={"shifts": [1.0], "emphasis": [2.0]}, title="test")
    png.write(str(tmp_path / "p.png"), img)
    back = png.read(str(tmp_path / "p.png"))
    assert (back.w, back.h) == (img.w, img.h) and img.h > 4 * 120  # head, eyes, blinks, upper face, mouth
    assert len(set(bytes(img.px))) > 10  # something was drawn


def test_listeners_backchannel_and_talkers_look_away_to_think():
    long_listen = json.loads(json.dumps(SPEC))
    long_listen["lines"][1]["duration_s"] = 8.0
    c = S.compile(long_listen, STATE)
    nods = [n for n in c["face"]["nods"] if 4.35 <= n["t"] <= 12.35]
    assert len(nods) >= 2  # the listen line had no nods: it gets small ones
    st = json.loads(json.dumps(STATE))
    st["audio"]["l1"]["phrase_ends"] = [0.8]  # a pause while the line still looks at the guest? (it looks at camera)
    c2 = S.compile(SPEC, st)
    assert not [s for s in c2["face"]["shifts"] if s.get("label") == "aversion"]  # never away from the lens
    sp = json.loads(json.dumps(SPEC))
    sp["lines"][0]["gaze"] = [{"at_s": 0, "target": "guest", "scan": "face"}]
    found = 0
    for seed in range(6):
        sp["seed"] = seed
        found += bool([s for s in S.compile(sp, st)["face"]["shifts"] if s.get("label") == "aversion"])
    assert found >= 2
    sp["face"] = {"aversion": False, "backchannel": False}
    c3 = S.compile(sp, st)
    assert not [s for s in c3["face"]["shifts"] if s.get("label") == "aversion"]
    sp["lines"][1]["duration_s"] = 8.0
    c3 = S.compile(sp, st)
    assert not [n for n in c3["face"]["nods"] if 4.35 <= n["t"] <= 12.35]
    assert S.backchannel(0, 10, seed=1) == S.backchannel(0, 10, seed=1)


def test_perfkit_is_engine_free():
    """perfkit must import without `unreal` (the client plans with it) and with no third-party package."""
    import ast
    for p in (REPO / "unreal" / "fmbridge" / "perfkit").glob("*.py"):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for n in names:
                    assert n.split(".")[0] not in ("unreal", "numpy", "scipy"), (p.name, n)


def test_on_emphasis_places_things_on_the_stressed_words():
    sp = json.loads(json.dumps(SPEC))
    sp["lines"][0]["gestures"] = [{"name": "palms", "on_emphasis": "strongest"}]
    sp["lines"][0]["nods"] = [{"on_emphasis": 2, "kind": "beat"}, {"on_emphasis": 9}]
    sp["lines"][0]["expressions"] = [{"preset": "brow_raise", "on_emphasis": "first"}]
    assert S.validate(sp) == []
    c = S.compile(sp, STATE)  # l1's emphasis: 1.2 (1.0), 2.9 (0.7)
    g = next(s for s in c["body"] if s["kind"] == "gesture")
    assert g["stroke_frame"] == round((1.2 - 0.08) * 24)
    assert any(n["t"] == pytest.approx(2.9) and n["kind"] == "beat" for n in c["face"]["nods"])
    assert any("on_emphasis 9" in n.get("why", "") for n in c["notes"])
    ev = next(e for e in c["face"]["expressions"] if e["preset"] == "brow_raise")
    assert ev["t"] == pytest.approx(1.2 - 0.15)
    with pytest.raises(ValueError):
        S.at_s({"on_emphasis": 1}, [])


def test_long_audio_is_cut_in_pauses(tmp_path):
    segs = []
    for _ in range(9):  # 9 phrases of 4 s with 0.5 s pauses: 40.5 s
        segs += [(4.0, 0.4), (0.5, 0.0)]
    p = _wav(tmp_path / "long.wav", segs)
    env = AU.Envelope.from_wav(p)
    cuts = AU.split_points(env, max_s=10.0, min_s=3.0)
    assert cuts and all(b - a <= 10.0 + 1e-6 for a, b in zip([0.0] + cuts, cuts + [env.duration_s]))
    for c in cuts:  # each cut in a pause (4.0-4.5, 8.5-9.0, ... every 4.5 s)
        assert 4.0 - 0.1 <= c % 4.5 <= 4.5 + 0.1 or c % 4.5 < 0.1
    out = AU.write_chunk(p, str(tmp_path / "c.wav"), 4.5, 9.0)
    assert abs(AU.Envelope.from_wav(out).duration_s - 4.5) < 0.02
    assert AU.split_points(env, max_s=60) == []
    flap = AU.lip_flap(AU.Envelope.from_wav(out))
    jaw = flap["CTRL_expressions_jawOpen"]
    assert max(jaw[1]) > 0.2 and C.at(*jaw, 4.3) < 0.05  # open while talking, shut in the pause


def test_body_life_breathes_shifts_and_follows_the_head():
    from perfkit import bodylife as BLF
    life = BLF.plan(0, 40, state="talk", head_yaw=lambda t: 40.0 if t > 20 else 0.0, seed=3)
    assert 13 < life["breaths_per_min"] < 17
    t = life["times"]
    flex = life["bones"]["spine_05"]["flex"]
    # breathing: periodic extension, inhale shorter than exhale
    assert min(flex) < -0.15 and max(flex) <= 1e-9
    assert len(life["shifts"]) >= 3 and max(abs(c) for c in life["pelvis_shift_cm"]) <= 1.5 * 1.3
    twist = sum(life["bones"][b]["twist"][-1] for b in BLF.SPINE)
    assert twist == pytest.approx(40 * 0.15, rel=0.01) and life["bones"]["spine_03"]["twist"][t.index(min(t, key=lambda x: abs(x - 19.5)))] == 0
    assert BLF.plan(0, 5, seed=1) == BLF.plan(0, 5, seed=1)


def test_body_life_to_local_axes_and_quaternions():
    from perfkit import bodylife as BLF
    life = BLF.plan(0, 2, seed=0)
    axes = {"spine_05": {"flex": ["z", -1.0], "side": ["x", 1.0], "twist": ["y", 1.0]}}
    loc = BLF.to_local(life, axes)
    assert set(loc) == {"spine_05"} and loc["spine_05"]["z"][5] == pytest.approx(-life["bones"]["spine_05"]["flex"][5])
    q = BLF.quat_from_euler_xyz(0, 0, 90)
    assert q == pytest.approx([0, 0, math.sqrt(0.5), math.sqrt(0.5)])
    assert BLF.qmul([0, 0, 0, 1], q) == pytest.approx(q)


def test_blinks_never_tick_like_a_metronome():
    """Day-1 (box): a 10.6 s face with phrase ends every second planned blinks whose intervals varied by 0.24
    (std/mean), under metrics' 0.25. The planner now nudges spontaneous blinks until they vary by 0.3."""
    ends = [0.7, 1.7, 2.7, 3.7]
    for seed in range(40):
        bl = B.plan(0.0, 10.5667, "talk", phrase_ends=ends, seed=seed)
        ts = [b.t for b in bl]
        if len(ts) >= 4:
            assert B._cv(ts) >= 0.25, (seed, ts)
        assert all(b - a >= 0.0 for a, b in zip(ts, ts[1:]))
