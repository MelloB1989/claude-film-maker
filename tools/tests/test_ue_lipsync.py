"""R5 lip-sync: perfkit.lipsync (the curve-level gate and the per-line mouth compose). The cases are the round-4
failure (his mouth ~0.7 s early on L1, moving in the silence before it) and its neighbours: in sync, one frame off,
a constant offset, a 30-vs-24 fps drift, a mouth that does not follow the words."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "unreal" / "fmbridge"))

from perfkit import audio as AU  # noqa: E402
from perfkit import lipsync as LS  # noqa: E402

FPS = 24.0
JAW = "CTRL_expressions_jawOpen"


def syllables(t0: float, t1: float, seed: int = 1, rate_hz: float = 4.5) -> list:
    """Syllable nuclei [(t, strength)] between t0 and t1, irregularly spaced like speech."""
    rnd = random.Random(seed)
    out, t = [], t0 + 0.05
    while t < t1 - 0.08:
        out.append((t, 0.55 + 0.45 * rnd.random()))
        t += (1.0 / rate_hz) * (0.6 + 0.8 * rnd.random())
    return out


def voice(lines: list, length_s: float, rate: float = 100.0, offset_s: float = 0.0, seed: int = 1) -> AU.Envelope:
    """A 0..1 loudness envelope with a bump per syllable inside each (t0, t1), silence elsewhere."""
    nuclei = [s for i, (a, b) in enumerate(lines) for s in syllables(a, b, seed + i)]
    vals = []
    for i in range(int(length_s * rate)):
        t = offset_s + i / rate
        v = sum(k * math.exp(-0.5 * ((t - c) / 0.045) ** 2) for c, k in nuclei)
        vals.append(min(1.0, v))
    return AU.Envelope(vals, rate, offset_s)


def mouth_from(env: AU.Envelope, shift_s: float = 0.0, scale: float = 1.0, gain: float = 0.6, t_end=None,
               rate: float = 30.0) -> dict:
    """A jaw curve that follows the voice, `shift_s` later (negative = early), its time scaled by `scale` (a
    rate mismatch: the jaw at t plays the voice at t / scale)."""
    t_end = t_end or env.offset_s + env.duration_s
    times = [env.offset_s + i / rate for i in range(int((t_end - env.offset_s) * rate))]
    vals = [gain * env.at((t - shift_s) / scale if scale != 1 else t - shift_s) for t in times]
    return {JAW: (times, vals)}


LINES = [(2.5, 3.6), (6.0, 7.4), (11.0, 12.6)]


def cue_lines():
    return [{"id": f"L{i}", "t0": a, "t1": b} for i, (a, b) in enumerate(LINES, 1)]


def run(shift=0.0, scale=1.0, **kw):
    env = voice(LINES, 15.0)
    return LS.check(env, mouth_from(env, shift, scale), cue_lines(), fps=FPS, **kw)


# --- the gate ----------------------------------------------------------------------------------------------------

def test_in_sync_passes():
    r = run()
    assert r["pass"], r["issues"]
    for x in r["lines"].values():
        assert abs(x["lag_frames"]) < 0.3 and x["corr"] > 0.9
    assert r["diagnosis"] == "in sync"


def test_one_frame_is_the_limit():
    assert run(shift=0.5 / FPS)["pass"]
    r = run(shift=2.0 / FPS)
    assert not r["pass"]
    assert {i["code"] for i in r["issues"]} == {"lag"}
    assert all(1.6 < x["lag_frames"] < 2.4 for x in r["lines"].values())  # positive: LATE


def test_round4_his_mouth_early_fails_lag_onset_and_silence():
    """Round 4: the mouth opened wide ~0.7 s (17 frames) before L1 and talked in the silence before it."""
    r = run(shift=-0.7)
    codes = {i["code"] for i in r["issues"]}
    assert {"lag", "onset", "silence"} <= codes
    l1 = r["lines"]["L1"]
    assert -18.5 < l1["lag_frames"] < -15.5
    assert l1["onset_lead_s"] > 0.5
    assert "EARLY" in next(i["message"] for i in r["issues"] if i["code"] == "lag")
    assert r["diagnosis"].startswith("offset")
    assert "later" in next(i["fix"] for i in r["issues"] if i["code"] == "lag")


def test_a_rate_mismatch_is_diagnosed_as_drift():
    """30 fps keys read at 24 (time x 0.8): the lag grows through the performance."""
    env = voice(LINES, 15.0)
    r = LS.check(env, mouth_from(env, scale=0.95), cue_lines(), fps=FPS, max_lag_s=1.0)
    assert not r["pass"]
    assert r["diagnosis"].startswith("drift"), r["diagnosis"]


def test_a_mouth_that_does_not_follow_the_words_fails_corr():
    env = voice(LINES, 15.0)
    other = voice(LINES, 15.0, seed=99)  # the same lines' spans, other syllables: talking, but not these words
    r = LS.check(env, mouth_from(other), cue_lines(), fps=FPS)
    assert "corr" in {i["code"] for i in r["issues"]}


def test_breath_and_smile_in_silence_are_allowed_talking_is_not():
    env = voice(LINES, 15.0)
    m = mouth_from(env)
    t, v = m[JAW]
    breath = [y + (0.04 * max(0.0, math.sin(2 * math.pi * 0.25 * x)) if 4.0 < x < 5.5 else 0.0) for x, y in zip(t, v)]
    assert LS.check(env, {JAW: (t, breath)}, cue_lines(), fps=FPS)["pass"]
    chat = [y + (0.3 * abs(math.sin(2 * math.pi * 2.5 * x)) if 8.5 < x < 10.0 else 0.0) for x, y in zip(t, v)]
    r = LS.check(env, {JAW: (t, chat)}, cue_lines(), fps=FPS)
    sil = [i for i in r["issues"] if i["code"] == "silence"]
    assert sil and "f" in sil[0]["message"]


def test_expected_lag_removes_the_solvers_own_bias():
    r = run(shift=-0.1, expected_lag_s=-0.1)
    assert r["pass"], r["issues"]


def test_no_mouth_is_a_clear_failure():
    env = voice(LINES, 15.0)
    r = LS.check(env, {"CTRL_expressions_browRaiseInL": ([0, 1], [0, 0])}, cue_lines())
    assert not r["pass"] and r["issues"][0]["code"] == "no_mouth"


def test_the_envelope_on_the_master_timeline():
    """The audio placed at 40 s (a stem cut from START): the check works on master time."""
    lines = [(42.5, 43.6), (45.6, 46.9)]
    env = voice([(a, b) for a, b in lines], 10.0, offset_s=40.0)
    m = mouth_from(env)
    r = LS.check(env, m, [{"id": "a", "t0": 42.5, "t1": 43.6}, {"id": "b", "t0": 45.6, "t1": 46.9}])
    assert r["pass"], r["issues"]


# --- vad ----------------------------------------------------------------------------------------------------------

def test_vad_finds_each_line_and_its_first_sound():
    env = voice(LINES, 15.0)
    spans = LS.vad(env.values, env.rate)
    assert len(spans) == 3
    for (a, b), (s0, s1) in zip(LINES, spans):
        assert a - 0.1 < s0 < a + 0.12 and b - 0.25 < s1 < b + 0.15
    assert LS.speech_in(spans, 5.0, 9.0)[0] == spans[1][0]
    assert LS.speech_in(spans, 4.0, 5.5) is None


# --- placement ----------------------------------------------------------------------------------------------------

def test_place_shifts_offsets_and_rates():
    cur = {JAW: ([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])}
    assert LS.place(cur, 40.0)[JAW] == ([40.0, 41.0, 42.0], [0.0, 1.0, 0.0])
    assert LS.place(cur, 40.0, offset_s=1.0)[JAW] == ([40.0, 41.0], [1.0, 0.0])
    assert LS.place(cur, 0.0, rate=2.0)[JAW][0] == [0.0, 0.5, 1.0]


def test_merge_sections_later_section_wins():
    a = (0.0, 5.0, {JAW: ([0.0, 2.0, 4.0], [0.1, 0.1, 0.1])})
    b = (3.0, 6.0, {JAW: ([3.0, 5.0], [0.9, 0.9])})
    t, v = LS.merge_sections([b, a])[JAW]
    assert t == [0.0, 2.0, 3.0, 5.0] and v == [0.1, 0.1, 0.9, 0.9]


# --- compose ------------------------------------------------------------------------------------------------------

def test_compose_rests_the_mouth_between_lines_and_keeps_each_line():
    line = {JAW: ([0.0, 0.2, 0.4, 0.6, 0.8], [0.0, 0.5, 0.1, 0.6, 0.0]),
            "CTRL_expressions_mouthCornerPullL": ([0.0, 0.8], [0.3, 0.3]),  # the smile layer: not speech
            "CTRL_expressions_eyeBlinkL": ([0.0, 0.8], [1.0, 1.0])}
    out = LS.compose([(2.0, line), (5.0, line)], 8.0, fade_s=0.05)
    assert set(out) == {JAW}
    t, v = out[JAW]
    from perfkit import curves as C
    assert max(abs(C.at(t, v, x)) for x in (1.0, 4.0, 7.0)) < 1e-9
    assert abs(C.at(t, v, 2.2) - 0.5) < 0.01 and abs(C.at(t, v, 5.6) - 0.6) < 0.01


def test_composed_lines_pass_the_gate_and_the_old_whole_stem_misplacement_fails():
    env = voice(LINES, 15.0)
    parts = []
    for a, b in LINES:  # each line solved alone: its WAV starts 50 ms before its first sound
        w0 = a - 0.05
        seg = AU.Envelope([env.at(w0 + i / 100) for i in range(int((b - a + 0.3) * 100))], 100.0)
        parts.append((w0, mouth_from(seg)))
    good = LS.compose(parts, 15.0)
    assert LS.check(env, good, cue_lines(), fps=FPS)["pass"]
    bad = LS.compose([(t0 - 0.7, c) for t0, c in parts], 15.0)
    assert not LS.check(env, bad, cue_lines(), fps=FPS)["pass"]


def test_speech_curves():
    assert LS.is_speech_curve("CTRL_expressions_jawOpen")
    assert LS.is_speech_curve("CTRL_expressions_mouthLipsPurseUL")
    assert LS.is_speech_curve("CTRL_expressions_tongueUp")
    assert not LS.is_speech_curve("CTRL_expressions_mouthCornerPullL")
    assert not LS.is_speech_curve("CTRL_expressions_browRaiseInL")
