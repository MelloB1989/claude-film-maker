"""face_acting (round 7): the sheet's smiles calibrated, the lips left to the solve, the rows met offline."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import face_acting as FA  # noqa: E402


def test_full_duchenne_only_on_payoffs():
    p = FA.plan("her")
    full = [e for e in p["expressions"] if e["name"] == "smile"]
    assert len(full) == 5
    assert all(e["intensity"] >= 0.8 * 0.93 for e in full)
    soft = [e for e in p["expressions"] if e["name"] == "soft"]
    assert soft and all(0.4 * 0.95 * 0.93 <= e["intensity"] <= 0.6 * 1.05 * 1.07 for e in soft)
    assert not [n for n in p["notes"] if "off the payoff" in n]


def test_no_jaw_or_lip_shapes_over_speech():
    cu = FA.cue("her")
    for e in FA.plan("her")["expressions"]:
        moving = {n.rstrip("*LR") for n in e["preset"]} & {"jawOpen", "mouthUpperLipRaise", "mouthStretch"}
        if not moving:
            continue
        end = e["until"] + e["release_s"]
        assert not [w for w in cu["words"] if w["t0"] - FA.LIP_CLEAR_S < end and w["t1"] > e["t"]], e


def test_rows_pass_offline_on_the_test_span_and_the_take():
    assert FA.check("her", {"N01", "N02", "N03", "N13"})["pass"]
    assert FA.check("her")["pass"]


def test_tilts_keep_blinks_off_their_eases():
    p = FA.plan("her")
    assert p["tilts"]
    for t in p["tilts"]:
        assert any(a <= t["t"] and t["t"] + t["ease_s"] <= b for a, b in p["avoid_blinks"])
        assert any(a <= t["until"] and t["until"] + t["ease_s"] <= b for a, b in p["avoid_blinks"])


def test_mouth_shut_in_the_end_silence():
    cu = FA.cue("her")
    last = cu["words"][-1]["t1"]
    for e in FA.plan("her")["expressions"]:
        if e["until"] + e["release_s"] > last:
            assert not {n.rstrip("*LR") for n in e["preset"]} & {"jawOpen", "mouthUpperLipRaise"}, e


def test_his_smile_mouth_share_divided_by_his_speech_gain():
    him = [e for e in FA.plan("him")["expressions"] if e["name"] == "smile"][0]["preset"]
    assert abs(him["mouthCornerPull*"][0] * FA.MOUTH_GAIN["him"] - FA.RECIPES["duchenne"]["mouthCornerPull*"][0]) < 1e-9
    assert him["eyeCheekRaise*"] == FA.RECIPES["duchenne"]["eyeCheekRaise*"]


def test_his_head_is_calmer_hers_unchanged():
    import head as HP
    his, hers = FA.plan("him")["nods"], FA.plan("her")["nods"]
    full = [n for n in his if n["depth_deg"] >= 2.5]
    assert len(full) == 4 and all(n["depth_deg"] <= 0.61 for n in his if n not in full)
    assert max(n["depth_deg"] for n in hers) == 3.0 and min(n["depth_deg"] for n in hers) == 2.5
    assert HP.BEAT_EVERY.get("him") == 0 and HP.BEAT_EVERY.get("her", 2) == 2
