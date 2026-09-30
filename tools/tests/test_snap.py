import numpy as np
import pytest

from gitloom_film.snap import cut_scenes, snap, snap_lines

BEATS = np.round(np.arange(0.2, 30.0, 0.6), 4)  # 0.2, 0.8, 1.4, …
DOWNS = BEATS[::4]  # 0.2, 2.6, 5.0, 7.4, 9.8, …


def line(lid, scene, start, dur=1.0):
    return {"id": lid, "scene": scene, "start": start, "end": start + dur,
            "words": [{"w": "a", "start": start + 0.04, "end": start + 0.5},
                      {"w": "b.", "start": start + 0.6, "end": start + dur - 0.1}]}


def test_line_within_tolerance_moves_onto_the_beat():
    [l] = snap_lines([line("L1", "s1", 1.30)], BEATS)  # first word 1.34 → beat 1.4
    assert l["words"][0]["start"] == pytest.approx(1.4) and l["start"] == pytest.approx(1.36)
    assert l["words"][1]["start"] == pytest.approx(1.96)


def test_line_beyond_tolerance_stays():
    [l] = snap_lines([line("L1", "s1", 1.66)], BEATS)  # first word 1.70 is 0.3 s from both beats
    assert l["start"] == 1.66


def test_nudge_never_collides_with_the_next_line():
    out = snap_lines([line("L1", "s1", 1.30), line("L2", "s1", 2.38)], BEATS)
    assert out[0]["start"] == 1.30  # +0.06 would leave 0.02 s before L2


def test_cut_is_the_last_beat_before_the_first_word_and_acts_take_downbeats():
    lines = [line("L1", "s1", 1.0), line("L2", "s2", 4.0), line("L3", "s3", 8.9)]
    scenes = [{"id": "s1", "act": "I"}, {"id": "s2", "act": "I"}, {"id": "s3", "act": "II"}]
    out = cut_scenes(scenes, lines, BEATS, DOWNS, act_starts={"s3"}, duration=12.0)
    assert [s["start"] for s in out] == [0.0, 3.8, 7.4]
    assert [s["end"] for s in out] == [3.8, 7.4, 12.0]


def test_cut_never_lands_after_the_word_or_before_the_previous_word():
    lines = [line("L1", "s1", 1.0, dur=1.25), line("L2", "s2", 2.25)]  # words end 2.15; next starts 2.29
    scenes = [{"id": "s1", "act": "I"}, {"id": "s2", "act": "I"}]
    out = cut_scenes(scenes, lines, BEATS, DOWNS, act_starts=set(), duration=5.0)
    assert 2.15 <= out[1]["start"] <= 2.29


def test_snap_updates_lines_scenes_acts_and_duration():
    script = {"acts": [{"id": "I", "name": "A", "scenes": ["s1", "s2"]}, {"id": "II", "name": "B", "scenes": ["s3"]}]}
    vo = {"duration": 11.0, "lines": [line("L1", "s1", 1.30), line("L2", "s2", 4.0), line("L3", "s3", 8.9)],
          "scenes": [{"id": "s1", "act": "I", "start": 0, "end": 3}, {"id": "s2", "act": "I", "start": 3, "end": 8},
                     {"id": "s3", "act": "II", "start": 8, "end": 11}], "acts": []}
    out = snap(vo, {"duration": 12.0, "beats": list(BEATS), "downbeats": list(DOWNS)}, script)
    assert out["duration"] == 12.0 and out["scenes"][-1]["end"] == 12.0
    assert out["lines"][0]["words"][0]["start"] == pytest.approx(1.4)
    assert [a["id"] for a in out["acts"]] == ["I", "II"] and out["acts"][1]["start"] == out["scenes"][2]["start"]
