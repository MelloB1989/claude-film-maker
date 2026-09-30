import json

import pytest

from lib import timing

# Expected values are read off data/vo.json and data/audio.json by hand (scene windows x 30, beats x 30), never
# computed with timing.py.


def test_frame_is_seconds_times_30():
    assert timing.frame(1.0) == 30
    assert timing.frame(0.0) == 0
    assert timing.frame(18.16) == 545  # 544.8


def test_frame_rounds_half_frames_up_like_the_engine():
    # the engine's frameIdx is Math.round(t * 30): halves go up, also for even frames, where Python's round() goes
    # down (round(2.5) == 2). 2.5 / 30 * 30 is exactly 2.5 in floating point.
    assert timing.frame(2.5 / 30) == 3
    assert timing.frame(0.5 / 30) == 1
    assert timing.frame(3.5 / 30) == 4
    assert timing.frame(2.49 / 30) == 2
    assert timing.frame(-2.5 / 30) == -2  # Math.round(-2.5) is -2


def test_scene_frames_are_the_vo_scene_windows_times_30_rounded():
    assert timing.scene_frames("thread") == (0, 180)  # 0.0 .. 6.008 s
    assert timing.scene_frames("ex") == (180, 468)  # 6.008 .. 15.608 s
    assert timing.scene_frames("her") == (468, 684)  # 15.608 .. 22.808 s
    assert timing.scene_frames("honest") == (1836, 1980)  # 61.208 .. 66.008 s (1980.2399999999998)
    assert timing.scene_frames("weave") == (2592, 2808)  # 86.408 .. 93.6 s


def test_scene_windows_tile_the_film_without_gaps_or_overlaps():
    ids = ["thread", "ex", "her", "repo", "loom", "diff", "cite", "braid", "merkle", "graph", "honest", "proof",
           "connect", "anywhere", "weave"]
    windows = [timing.scene_frames(i) for i in ids]
    assert windows[0][0] == 0 and windows[-1][1] == 2808
    for (_, end), (start, _) in zip(windows, windows[1:]):
        assert end == start


def test_scene_frames_rejects_an_unknown_scene():
    with pytest.raises(KeyError, match="nope"):
        timing.scene_frames("nope")


def test_word_gives_the_measured_onset():
    w = timing.word("L07", 1)  # "Every memory... a commit."
    assert w.w == "memory..."
    assert w.start == 18.16
    assert w.frame == 545
    assert timing.word("L07", 3).start == 19.348  # "commit."
    with pytest.raises(IndexError):
        timing.word("L07", 4)
    with pytest.raises(KeyError, match="L99"):
        timing.word("L99", 0)


def test_downbeats_in_is_half_open_in_film_frames():
    # downbeats at 0.008, 2.408, 4.808, 7.208 s: frames 0, 72, 144, 216
    assert timing.downbeats_in(0, 180) == [0, 72, 144]
    assert timing.downbeats_in(72, 144) == [72]
    assert timing.downbeats_in(73, 144) == []
    assert timing.downbeats_in(180, 468) == [216, 288, 360, 432]  # the `ex` scene: 7.208 .. 14.408 s


def test_beats_in_gives_every_beat_frame():
    # beats every 0.6 s from 0.008: frames 0, 18, 36, 54, 72 ...
    assert timing.beats_in(0, 72) == [0, 18, 36, 54]
    assert timing.beats_in(1, 37) == [18, 36]


def _fixture(tmp_path, beats):
    (tmp_path / "data").mkdir()
    vo = {"duration": 1, "lines": [], "scenes": [{"id": "s", "act": "I", "start": 0.0, "end": 1.0}], "acts": []}
    audio = {"beats": beats, "downbeats": beats[:1]}
    (tmp_path / "data" / "vo.json").write_text(json.dumps(vo))
    (tmp_path / "data" / "audio.json").write_text(json.dumps(audio))


def test_load_reads_another_root_and_beats_round_like_frame(tmp_path):
    _fixture(tmp_path, [2.5 / 30, 4.5 / 30])
    t = timing.load(tmp_path)
    assert t.scene_frames("s") == (0, 30)
    assert t.beats_in(0, 30) == [3, 5]  # Python's round() would say 2 and 4
    assert t.downbeats_in(0, 30) == [3]
    assert timing.scene_frames("thread") == (0, 180)  # the module's own functions keep the film's data


def test_parse_frames_takes_inclusive_ranges_and_lists():
    assert timing.parse_frames("40-44") == [40, 41, 42, 43, 44]
    assert timing.parse_frames("47") == [47]
    assert timing.parse_frames("40,47,50-52") == [40, 47, 50, 51, 52]
    assert timing.parse_frames("50-52,40,51") == [40, 50, 51, 52]  # sorted, each frame once


@pytest.mark.parametrize("bad", ["", "a-b", "52-50", "4.5", "-3", "1--2"])
def test_parse_frames_rejects_nonsense(bad):
    with pytest.raises(ValueError):
        timing.parse_frames(bad)
