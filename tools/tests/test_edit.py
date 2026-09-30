import numpy as np
import pytest

from gitloom_film.edit import assemble, place
from gitloom_film.wav import SR, write_wav

SCRIPT = {"acts": [{"id": "I", "name": "A", "scenes": ["s1", "s2"]}, {"id": "II", "name": "B", "scenes": ["s3"]}],
          "lines": [{"id": "L1", "scene": "s1", "text": "a b"}, {"id": "L2", "scene": "s1", "text": "c"},
                    {"id": "L3", "scene": "s2", "text": "d"},
                    {"id": "L3b", "scene": "s2", "text": "x", "optional": True},
                    {"id": "L4", "scene": "s3", "text": "e"}]}


def take(dur, words):
    return {"take": 1, "factor": 0.9, "duration": dur, "words": words}


TAKES = {"L1": take(1.0, [{"w": "a", "start": 0.04, "end": 0.4}, {"w": "b", "start": 0.5, "end": 0.9}]),
         "L2": take(0.5, [{"w": "c", "start": 0.04, "end": 0.4}]),
         "L3": take(0.5, [{"w": "d", "start": 0.04, "end": 0.4}]),
         "L3b": take(0.5, [{"w": "x", "start": 0.04, "end": 0.4}]),
         "L4": take(0.5, [{"w": "e", "start": 0.04, "end": 0.4}])}
CFG = {"lead_in": 1.0, "tail": 2.0, "gap": {"line": 0.5, "scene": 1.0, "act": 2.0}, "scene_lead": 0.3,
       "overrides": {"L4": {"gap_before": 3.0}}, "optional": {"L3b": False}}


def test_place_applies_gaps_and_overrides():
    vo = place(SCRIPT, TAKES, CFG)
    assert {l["id"]: l["start"] for l in vo["lines"]} == {"L1": 1.0, "L2": 2.5, "L3": 4.0, "L4": 7.5}
    assert vo["duration"] == 10.0
    l1 = vo["lines"][0]
    assert l1["words"][1] == {"w": "b", "start": 1.5, "end": 1.9}
    assert (l1["act"], l1["take"], l1["factor"]) == ("I", 1, 0.9)


def test_word_lead_moves_starts_earlier_but_keeps_order_and_line_start():
    takes = {**TAKES, "L1": take(1.0, [{"w": "I", "start": 0.04, "end": 0.041}, {"w": "b", "start": 0.08, "end": 0.9}])}
    vo = place(SCRIPT, takes, {**CFG, "word_lead": 0.05})
    w = vo["lines"][0]["words"]
    assert w[0]["start"] == 1.0  # 1.04 − 0.05 would precede the line start
    assert w[1]["start"] == 1.03  # 1.08 − 0.05
    assert w[1]["end"] == 1.9  # ends are untouched
    assert vo["lines"][1]["words"][0]["start"] == 2.5  # 2.54 − 0.05 clamps to L2's start


def test_optional_line_included_when_enabled():
    vo = place(SCRIPT, TAKES, {**CFG, "optional": {"L3b": True}})
    assert [l["id"] for l in vo["lines"]] == ["L1", "L2", "L3", "L3b", "L4"]


def test_scene_and_act_spans_tile_the_film():
    vo = place(SCRIPT, TAKES, CFG)
    sc = vo["scenes"]
    assert [s["id"] for s in sc] == ["s1", "s2", "s3"]
    assert sc[0]["start"] == 0.0 and sc[-1]["end"] == 10.0
    assert all(a["end"] == b["start"] for a, b in zip(sc, sc[1:]))
    assert sc[1]["start"] == pytest.approx(3.74)  # 0.3 s before its first word (4.04), after s1's last word + 0.1
    assert vo["acts"] == [{"id": "I", "name": "A", "start": 0.0, "end": sc[2]["start"]},
                          {"id": "II", "name": "B", "start": sc[2]["start"], "end": 10.0}]


def test_missing_take_names_the_line():
    with pytest.raises(KeyError, match="L2"):
        place(SCRIPT, {k: v for k, v in TAKES.items() if k != "L2"}, CFG)


def test_assemble_places_audio_at_line_starts(tmp_path):
    for lid, t in TAKES.items():
        x = np.zeros(int(t["duration"] * SR), np.float32)
        x[0] = 0.9
        write_wav(tmp_path / lid / "1.wav", x)
    vo = place(SCRIPT, TAKES, CFG)
    y = assemble(vo, tmp_path)
    assert len(y) >= int(10.0 * SR)
    assert list(np.round(np.flatnonzero(y > 0.5) / SR, 3)) == [1.0, 2.5, 4.0, 7.5]
