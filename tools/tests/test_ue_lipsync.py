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


# --- film-ue lips: measured cues, the offline curve gate, the render gate ----------------------------------------

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")


def _speech(sr: int, dur: float, seed: int) -> "np.ndarray":
    """A voiced-sounding burst: a 140 Hz buzz under a syllable-rate (4-5 Hz) envelope."""
    rnd = np.random.default_rng(seed)
    t = np.arange(int(sr * dur)) / sr
    syl = 0.5 + 0.5 * np.sin(2 * np.pi * (4.2 + rnd.random()) * t - np.pi / 2)
    return (0.3 * syl * np.sign(np.sin(2 * np.pi * 140 * t)) * (0.7 + 0.3 * rnd.random(len(t)))).astype(np.float32)


def _stem(path, sr, length_s, lines):
    x = np.zeros(int(sr * length_s), np.float32)
    for t0, dur, seed in lines:
        y = _speech(sr, dur, seed)
        i0 = int(t0 * sr)
        x[i0:i0 + len(y)] += y
    x += np.random.default_rng(0).normal(0, 1e-4, len(x)).astype(np.float32)
    sf.write(path, x, sr, subtype="PCM_24")
    return path


@pytest.fixture
def lips(tmp_path):
    from filmtools.unreal import cli_lipsync as CL
    sr, fps = 48000, 24.0
    stem = _stem(tmp_path / "vo_him.wav", sr, 50.0, [(42.55, 1.0, 1), (45.7, 1.1, 2)])
    lines = {"fps": fps, "lines": {
        "L1": {"who": "him", "text": "Took you long enough.", "wav": "L1.wav", "file_frame": 1018.8, "voice_frame": 1020,
               "end_frame": None, "slot_end": 1065},
        "L2": {"who": "him", "text": "Ask her what's next.", "wav": "L2.wav", "file_frame": 1093.8, "voice_frame": 1095,
               "end_frame": None, "slot_end": 1133}}}
    return CL, stem, lines, fps, tmp_path


def test_cues_are_measured_from_the_stem_and_record_its_hash(lips):
    CL, stem, lines, fps, tmp = lips
    doc = CL.build_cues(lines, {"him": stem}, fps, words="estimate")
    assert doc["measured"] and doc["stems"]["him"]["sha256"] == CL.sha256(stem)
    l1, l2 = doc["lines"]["L1"], doc["lines"]["L2"]
    assert abs(l1["voice_frame"] - 42.55 * fps) < 1.5 and abs(l1["end_frame"] - 43.55 * fps) < 3
    assert abs(l2["voice_frame"] - 45.7 * fps) < 1.5
    assert l1["words"][0]["start"] == l1["voice_frame"] and l1["words"][-1]["end"] == l1["end_frame"]
    assert [w["w"] for w in l1["words"]] == ["Took", "you", "long", "enough."]
    assert l1["words_source"] == "estimate"
    assert CL.stale(doc, {"him": stem}) == []
    _stem(stem, 48000, 50.0, [(42.0, 1.0, 1)])  # the stem changed: the cues are stale
    assert CL.stale(doc, {"him": stem}) == ["him"]


def test_offline_curve_gate_catches_an_early_face(lips):
    CL, stem, lines, fps, tmp = lips
    doc = CL.build_cues(lines, {"him": stem}, fps, words="none")
    x, sr = sf.read(stem, dtype="float32")
    env = CL.envelope(x, sr)
    ts = [i / 30 for i in range(30 * 50)]
    good = {JAW: (ts, [0.6 * env.at(t) for t in ts])}
    # as anim.read_curves returns them: on the animation's own time; it starts on master frame 960
    shifted = {JAW: ([t - 40.0 for t in ts if t >= 40.0], [0.6 * env.at(t) for t in ts if t >= 40.0])}
    assert CL.curve_check(shifted, 960, stem, doc, "him", fps)["pass"]
    early = {JAW: ([t - 40.0 - 0.7 for t in ts if t >= 40.7], [0.6 * env.at(t) for t in ts if t >= 40.7])}
    r = CL.curve_check(early, 960, stem, doc, "him", fps)
    assert not r["pass"] and r["lines"]["L1"]["lag_frames"] < -15
    assert good


def _frames_for(env, f0, n, fps, shift_frames=0.0, h=90, w=160):
    """A grey face with a mouth whose dark cavity opens with the voice (shifted by `shift_frames`)."""
    out = np.full((n, h, w), 0.7, np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    for i in range(n):
        a = env.at((f0 + i - shift_frames) / fps)
        ry = 1 + 14 * a
        m = ((xx - 80) / 20.0) ** 2 + ((yy - 45) / ry) ** 2 <= 1.0
        out[i][m] = 0.1
    return out


def test_render_gate_passes_in_sync_and_fails_an_early_mouth(lips):
    CL, stem, lines, fps, tmp = lips
    doc = CL.build_cues(lines, {"him": stem}, fps, words="none")
    x, sr = sf.read(stem, dtype="float32")
    env = CL.envelope(x, sr)
    box = [0.3, 0.2, 0.7, 0.8]

    def frames(shift):
        out = {}
        for k, c in doc["lines"].items():
            f0 = int(math.floor(c["voice_frame"] - fps))
            f1 = int(math.ceil(c["end_frame"] + fps))
            out[k] = _frames_for(env, f0, f1 - f0, fps, shift)
        return out
    ok = CL.render_check(stem, stem, doc, "him", box=box, frames_override=frames(0))
    assert ok["verdict"] == "pass", ok
    assert all(abs(v["lag_frames"]) <= 1 and v["sensitive"] for v in ok["lines"].values())
    bad = CL.render_check(stem, stem, doc, "him", box=box, frames_override=frames(-17))
    assert bad["verdict"] == "fail" and bad["issues"][0]["code"] == "render_lag"
    assert "EARLY" in bad["issues"][0]["message"]


def test_render_gate_is_inconclusive_on_a_static_mouth(lips):
    CL, stem, lines, fps, tmp = lips
    doc = CL.build_cues(lines, {"him": stem}, fps, words="none")
    still = {k: np.full((int(c["end_frame"] - c["voice_frame"] + 2 * fps) + 2, 90, 160), 0.5, np.float32)
             for k, c in doc["lines"].items()}
    r = CL.render_check(stem, stem, doc, "him", box=[0.3, 0.2, 0.7, 0.8], frames_override=still)
    assert r["verdict"] == "inconclusive" and not r["pass"]


def test_words_the_mouth_holds_through_fail():
    env = voice(LINES, 15.0)
    m = mouth_from(env)
    t, v = m[JAW]
    held = [0.3 if 6.0 <= x <= 7.4 else y for x, y in zip(t, v)]  # L2: the jaw parked open over every word
    words = [[6.0 + 0.35 * i, 6.0 + 0.35 * i + 0.3] for i in range(4)]
    lines = cue_lines()
    lines[1]["words"] = words
    r = LS.check(env, {JAW: (t, held)}, lines, fps=FPS)
    assert r["lines"]["L2"]["words_moving"] < 0.8 and "words" in {i["code"] for i in r["issues"]}
    lines_ok = cue_lines()
    lines_ok[1]["words"] = words
    assert LS.check(env, m, lines_ok, fps=FPS)["lines"]["L2"]["words_moving"] >= 0.8


def test_gate_numbers_round4_fails_every_line_it_should(lips):
    CL, stem, lines, fps, tmp = lips
    cues = CL.build_cues(lines, {"him": stem}, fps, words="none")
    x, sr = sf.read(stem, dtype="float32")
    env = CL.envelope(x, sr)
    ts = [40.0 + i / 30 for i in range(30 * 10)]
    early = {JAW: ([t - 40.0 - 0.7 for t in ts if t >= 40.7], [0.6 * env.at(t) for t in ts if t >= 40.7])}
    rep = CL.curve_check(early, 960, stem, cues, "him", fps)
    g = CL.gate_numbers({"him": rep}, {}, cues, {"him": stem})["gate"]
    assert g["lips.lag_frames"]["value"] > 15 and g["lips.onset_lead_ms"]["value"] > 500
    assert g["lips.silence_open"]["value"] > 0.10 or g["lips.silence_busy"]["value"] > 0.25
    assert g["lips.cues_fresh"]["value"] == 1 and "error" in g["lips.render_lag_frames"]
    cues["lines"]["L1"]["words_lost"] = True
    assert CL.gate_numbers({"him": rep}, {}, cues, {"him": stem})["gate"]["lips.cues_fresh"]["value"] == 0


def _place(sr, length_s, items, noise=1e-4, music=0.0):
    x = np.zeros(int(sr * length_s), np.float32)
    for t0, y in items:
        i0 = int(round(t0 * sr))
        x[i0:i0 + len(y)] += y
    rnd = np.random.default_rng(3)
    x += rnd.normal(0, noise, len(x)).astype(np.float32)
    if music:
        t = np.arange(len(x)) / sr
        x += (music * (np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 330 * t + 1))).astype(np.float32)
    return x


def test_cues_locate_each_line_and_catch_a_mix_that_plays_it_elsewhere(tmp_path):
    """Round 4: the face was solved from stems whose L1 sat ~14 frames before the mix's L1."""
    from filmtools.unreal import cli_lipsync as CL
    sr, fps = 48000, 24.0
    l1, l2 = _speech(sr, 1.0, 1), _speech(sr, 1.1, 2)
    (tmp_path / "vo").mkdir()
    sf.write(tmp_path / "vo" / "L1.wav", l1, sr, subtype="PCM_24")
    sf.write(tmp_path / "vo" / "L2.wav", l2, sr, subtype="PCM_24")
    stem = tmp_path / "vo_him.wav"
    sf.write(stem, _place(sr, 50.0, [(1007.0 / fps, l1), (1093.8 / fps, l2)]), sr, subtype="PCM_24")
    lines = {"lines": {
        "L1": {"who": "him", "text": "Took you long enough.", "wav": "L1.wav", "file_frame": 1018.8, "voice_frame": 1020,
               "slot_end": 1065},
        "L2": {"who": "him", "text": "Ask her what's next.", "wav": "L2.wav", "file_frame": 1093.8, "voice_frame": 1095,
               "slot_end": 1133}}}
    good_mix = tmp_path / "mix_good.wav"
    sf.write(good_mix, _place(sr, 50.0, [(1007.0 / fps, 0.8 * l1), (1093.8 / fps, 0.8 * l2)], music=0.05), sr)
    doc = CL.build_cues(lines, {"him": stem}, fps, words="none", line_dir=tmp_path / "vo", mix=good_mix)
    assert not [i for i in doc["issues"] if i["severity"] == "fail"], doc["issues"]
    assert abs(doc["lines"]["L1"]["file_frame"] - 1007.0) < 0.05  # measured, not the listed 1018.8
    assert doc["lines"]["L1"]["file_frame_listed"] == 1018.8
    assert abs(doc["lines"]["L1"]["voice_frame"] - 1007.0) < 2.5 and doc["lines"]["L1"]["mix_score"] > 0.5
    bad_mix = tmp_path / "mix_bad.wav"
    sf.write(bad_mix, _place(sr, 50.0, [(1021.0 / fps, 0.8 * l1), (1093.8 / fps, 0.8 * l2)], music=0.05), sr)
    doc = CL.build_cues(lines, {"him": stem}, fps, words="none", line_dir=tmp_path / "vo", mix=bad_mix)
    bad = [i for i in doc["issues"] if i["severity"] == "fail"]
    assert [i["code"] for i in bad] == ["mix_mismatch"] and bad[0]["line"] == "L1"
    assert "14.0 frames EARLY" in bad[0]["message"]
    other = (0.3 * np.random.default_rng(7).normal(0, 1, sr)).astype(np.float32)  # another take: other samples
    sf.write(tmp_path / "vo" / "L2.wav", other, sr, subtype="PCM_24")
    doc = CL.build_cues(lines, {"him": stem}, fps, words="none", line_dir=tmp_path / "vo")
    assert "not_in_stem" in {i["code"] for i in doc["issues"]}


def test_cues_from_the_mix_rebuild_the_stems_and_fail_round4s(tmp_path):
    from filmtools.unreal import cli_lipsync as CL
    sr, fps = 48000, 24.0
    l1, l2 = _speech(sr, 1.0, 1), _speech(sr, 1.1, 2)
    (tmp_path / "vo").mkdir()
    sf.write(tmp_path / "vo" / "L1.wav", l1, sr, subtype="PCM_24")
    sf.write(tmp_path / "vo" / "L2.wav", l2, sr, subtype="PCM_24")
    old = tmp_path / "vo_him.wav"  # round 4's stems: L1 14 frames before the mix's
    sf.write(old, _place(sr, 50.0, [(1007.0 / fps, l1), (1093.8 / fps, l2)]), sr, subtype="PCM_24")
    mix = tmp_path / "mix.wav"
    sf.write(mix, _place(sr, 50.0, [(1021.0 / fps, 0.8 * l1), (1096.0 / fps, 0.8 * l2)], music=0.05), sr)
    lines = {"lines": {
        "L1": {"who": "him", "text": "Took you long enough.", "wav": "L1.wav", "file_frame": 1018.8, "voice_frame": 1020,
               "slot_end": 1065},
        "L2": {"who": "him", "text": "Ask her what's next.", "wav": "L2.wav", "file_frame": 1093.8, "voice_frame": 1095,
               "slot_end": 1133}}}
    doc = CL.cues_from_mix(lines, tmp_path / "vo", mix, tmp_path / "stems", {"him": old}, fps, "none")
    assert not [i for i in doc["issues"] if i["severity"] == "fail"], doc["issues"]
    assert abs(doc["lines"]["L1"]["file_frame"] - 1021.0) < 0.05 and abs(doc["lines"]["L2"]["file_frame"] - 1096.0) < 0.05
    assert abs(doc["lines"]["L1"]["voice_frame"] - 1021.0) < 2.5
    assert doc["stems"]["him"]["path"].endswith("stems/vo_him.wav") and doc["canonical"] == "mix"
    o = doc["old_stems"]
    assert not o["pass"] and o["issues"][0]["code"] == "mix_mismatch" and "14.0 frames EARLY" in o["issues"][0]["message"]


def test_one_wav_split_into_two_lines_at_its_pause(tmp_path):
    """Only L3.wav exists (L3a 'Nice try.' + L3b): located once, captioned and checked as two lines."""
    from filmtools.unreal import cli_lipsync as CL
    sr, fps = 48000, 24.0
    gap = np.zeros(int(0.9 * sr), np.float32)
    l3 = np.concatenate([_speech(sr, 0.5, 4), gap, _speech(sr, 2.0, 5)])
    (tmp_path / "vo").mkdir()
    sf.write(tmp_path / "vo" / "L3.wav", l3, sr, subtype="PCM_24")
    mix = tmp_path / "mix.wav"
    sf.write(mix, _place(sr, 60.0, [(1157.0 / fps, 0.8 * l3)], music=0.05), sr)
    lines = {"lines": {"L3": {"who": "her", "text": "Nice try. Some things you have to see for yourself.", "wav": "L3.wav",
                              "file_frame": 1156.8, "split": [
                                  {"id": "L3a", "text": "Nice try.", "voice_frame": 1158, "mood": "HAPPINESS"},
                                  {"id": "L3b", "text": "Some things you have to see for yourself.", "voice_frame": 1215}]}}}
    doc = CL.cues_from_mix(lines, tmp_path / "vo", mix, tmp_path / "stems", None, fps, "estimate")
    assert not [i for i in doc["issues"] if i["severity"] == "fail"], doc["issues"]
    a, b = doc["lines"]["L3a"], doc["lines"]["L3b"]
    assert "L3" not in doc["lines"] and a["split_of"] == b["split_of"] == "L3"
    assert a["wav"] == b["wav"] == "L3.wav" and a["file_frame"] == b["file_frame"]
    assert abs(a["voice_frame"] - 1157.0) < 2.5 and a["end_frame"] < b["voice_frame"]
    assert abs(b["voice_frame"] - (1157.0 + 1.4 * fps)) < 3
    assert [w["w"] for w in a["words"]] == ["Nice", "try."] and a["mood"] == "HAPPINESS"


def test_a_regular_syllable_rate_does_not_alias_the_lag():
    """Evenly spaced syllables (a 4 Hz chant): the syllable band alone peaks at every 0.25 s; the words' envelope
    pins the right one."""
    lines = [(2.5, 4.0), (6.0, 6.8)]
    rate = 100.0
    vals = []
    for i in range(int(10 * rate)):
        t = i / rate
        on = any(a <= t <= b for a, b in lines)
        vals.append(max(0.0, math.sin(2 * math.pi * 4.0 * t)) if on else 0.0)
    env = AU.Envelope(vals, rate)
    for shift in (-0.25, -0.5, 0.25):
        m = mouth_from(env, shift)
        r = LS.check(env, m, [{"id": "a", "t0": 2.5, "t1": 4.0}, {"id": "b", "t0": 6.0, "t1": 6.8}], fps=FPS)
        for v in r["lines"].values():
            assert abs(v["lag_frames"] - shift * FPS) < 1.0, (shift, v)


def test_the_take_the_mix_holds_wins_over_a_stale_line_wav(tmp_path):
    """Round 5: the line WAVs on hand were not the ones mixed; the mix's line is one of the raw takes, trimmed and
    levelled by vo.py build. cues finds it, places it where the mix has it, and hands it on as the WAV to solve."""
    from filmtools.unreal import cli_lipsync as CL
    sr, fps = 48000, 24.0
    rnd = np.random.default_rng(11)
    (tmp_path / "vo").mkdir()
    sf.write(tmp_path / "vo" / "L1.wav", (0.3 * rnd.normal(0, 1, sr)).astype(np.float32), sr, subtype="PCM_24")
    (tmp_path / "takes" / "L1").mkdir(parents=True)
    takes = {}
    for i in range(3):
        raw = np.concatenate([np.zeros(int(0.4 * sr), np.float32), _speech(sr, 1.0, 20 + i),
                              np.zeros(int(0.5 * sr), np.float32)]) + rnd.normal(0, 1e-4, int(1.9 * sr)).astype(np.float32)
        takes[i] = raw
        sf.write(tmp_path / "takes" / "L1" / f"tarun-{i + 1}.wav", raw, sr, subtype="PCM_24")
    y, a = CL.prepare_take(takes[1], sr)
    assert 0.3 < a < 0.4
    mix = tmp_path / "mix.wav"
    sf.write(mix, _place(sr, 50.0, [(1021.0 / fps, 0.7 * y)], music=0.05), sr)
    lines = {"lines": {"L1": {"who": "him", "text": "Took you long enough.", "wav": "L1.wav", "file_frame": 1018.8,
                              "voice_frame": 1020, "slot_end": 1065, "take": "tarun-4"}}}
    doc = CL.cues_from_mix(lines, tmp_path / "vo", mix, tmp_path / "stems", None, fps, "none", tmp_path / "takes")
    assert not [i for i in doc["issues"] if i["severity"] == "fail"], doc["issues"]
    l1 = doc["lines"]["L1"]
    assert l1["take"] == "tarun-2" and abs(l1["file_frame"] - 1021.0) < 0.05 and l1["mix_score"] > 0.5
    assert l1["candidates"]["line"] < 0.2
    assert doc["line_dir"].endswith("stems/lines") and (tmp_path / "stems" / "lines" / "L1.wav").exists()
    none = CL.cues_from_mix(lines, tmp_path / "vo", mix, tmp_path / "s2", None, fps, "none")  # no takes: fails
    assert [i["code"] for i in none["issues"] if i["severity"] == "fail"] == ["not_in_mix"]


def test_a_line_wav_that_is_missing_is_a_failure_not_a_silent_none(lips):
    CL, stem, lines, fps, tmp = lips
    doc = CL.build_cues(lines, {"him": stem}, fps, words="none", line_dir=tmp)  # no L1.wav / L2.wav in tmp
    assert {i["code"] for i in doc["issues"] if i["severity"] == "fail"} == {"no_wav"}


def test_the_mixed_voice_must_be_the_solved_voice(tmp_path):
    """Round 4 in one test: the faces' stems were not the stems the mix was built from. mix.json's hashes prove it."""
    from filmtools.unreal import cli_lipsync as CL
    sr, fps = 48000, 24.0
    l1 = _speech(sr, 1.0, 1)
    (tmp_path / "vo").mkdir()
    sf.write(tmp_path / "vo" / "L1.wav", l1, sr, subtype="PCM_24")
    lines = {"lines": {"L1": {"who": "him", "text": "Took you long enough.", "wav": "L1.wav", "voice_frame": 1020,
                              "file_frame": 1018.8, "slot_end": 1065}}}
    paths, placed, issues = CL.stems_from_lines(lines, tmp_path / "vo", tmp_path / "stems", 1560, fps)
    assert not issues and abs(placed["L1"] - 1020.0) < 2.5  # its first sound on the planned frame
    voice = tmp_path / "stem-voice.wav"
    x, _ = sf.read(paths["him"], dtype="float32")
    sf.write(voice, 0.5 * x, sr)
    mix = tmp_path / "mix.wav"
    sf.write(mix, 0.5 * x + _place(sr, len(x) / sr, [], music=0.05), sr)
    meta = {"voice_sha256": {"him": CL.sha256(paths["him"])}, "stem_voice_sha256": CL.sha256(voice),
            "mix_sha256": CL.sha256(mix)}
    doc = CL.build_cues(lines, paths, fps, "none", line_dir=tmp_path / "vo", mix=mix, mix_voice=voice, mix_meta=meta)
    assert not [i for i in doc["issues"] if i["severity"] == "fail"], doc["issues"]
    assert doc["lines"]["L1"]["mix_score"] > 0.99  # on the mix's own voice stem
    other = tmp_path / "other.wav"  # the faces solved on other stems (round 4)
    sf.write(other, np.roll(x, sr), sr, subtype="PCM_24")
    bad = CL.build_cues(lines, {"him": other}, fps, "none", mix=mix, mix_voice=voice, mix_meta=meta)
    assert "vo_not_mixed" in {i["code"] for i in bad["issues"]}
    unproven = CL.build_cues(lines, paths, fps, "none", mix=mix, mix_meta={})
    assert "vo_unproven" in {i["code"] for i in unproven["issues"]}


def _voice_at(sr, dur, f0, seed):
    rnd = np.random.default_rng(seed)
    t = np.arange(int(sr * dur)) / sr
    syl = 0.5 + 0.5 * np.sin(2 * np.pi * (4.2 + rnd.random()) * t - np.pi / 2)
    return (0.3 * syl * np.sign(np.sin(2 * np.pi * f0 * t))).astype(np.float32)


def test_line_wavs_cut_from_the_mixs_separated_voice(tmp_path):
    """Option D: the voice separated from the delivered mix, cut per line at the plan's windows, speaker checked by
    pitch, and proven to come from that mix."""
    from filmtools.unreal import cli_lipsync as CL
    sr, fps = 48000, 24.0
    him, her = _voice_at(sr, 1.3, 120, 1), _voice_at(sr, 0.8, 230, 2)
    vocals = _place(sr, 60.0, [(1021.0 / fps, him), (1160.0 / fps, her)], noise=3e-4)
    sf.write(tmp_path / "vocals.wav", vocals, sr, subtype="PCM_24")
    mix = tmp_path / "mix.wav"
    sf.write(mix, vocals + _place(sr, 60.0, [], music=0.05), sr)
    plan = {"lines": {"L1": {"who": "him", "text": "Took you long enough.", "voice_frame": 1020, "slot_end": 1065},
                      "L3a": {"who": "her", "text": "Nice try.", "voice_frame": 1158, "slot_end": 1185}}}
    lines, issues, man = CL.lines_from_voice(tmp_path / "vocals.wav", plan, tmp_path / "sep", mix, fps, "htdemucs")
    assert not [i for i in issues if i["severity"] == "fail"], issues
    assert abs(lines["L1"]["voice_frame"] - 1021.0) < 1.5 and abs(lines["L3a"]["voice_frame"] - 1160.0) < 1.5
    assert abs(lines["L1"]["file_frame"] - (1021.0 - 0.05 * fps)) < 1.5
    assert lines["L1"]["f0_hz"] < 165 < lines["L3a"]["f0_hz"] and man["leak_db"] < -25
    # the cues on them: stems placed at the cut, proven against the mix
    doc_lines = {"lines": {k: {**c, "place": "file_frame"} for k, c in lines.items()}}
    stems, placed, _ = CL.stems_from_lines(doc_lines, tmp_path / "sep", tmp_path / "stems", 1560, fps)
    assert abs(placed["L1"] - lines["L1"]["file_frame"]) < 1e-6
    doc = CL.build_cues(doc_lines, stems, fps, "none", line_dir=tmp_path / "sep", mix=mix,
                        mix_voice=tmp_path / "vocals.wav", mix_meta=man)
    assert not [i for i in doc["issues"] if i["severity"] == "fail"], doc["issues"]
    assert all(c["mix_score"] > 0.8 for c in doc["lines"].values())
    sf.write(mix, vocals + _place(sr, 60.0, [], music=0.06), sr)  # another mix: not the one the voice came from
    doc = CL.build_cues(doc_lines, stems, fps, "none", line_dir=tmp_path / "sep", mix=mix,
                        mix_voice=tmp_path / "vocals.wav", mix_meta=man)
    assert "vo_not_mixed" in {i["code"] for i in doc["issues"]}
    wrong = {"lines": {"L1": {**plan["lines"]["L1"], "who": "her"}}}  # the plan says her: the pitch says him
    _, issues, _ = CL.lines_from_voice(tmp_path / "vocals.wav", wrong, tmp_path / "sep2", mix, fps)
    assert [i["code"] for i in issues if i["severity"] == "fail"] == ["speaker"]
