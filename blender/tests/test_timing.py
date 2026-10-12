import json

import pytest

from lib import film, timing

# Expected values are worked by hand (scene windows x fps, beats x fps), never computed with timing.py. Every film here
# is a fixture under tmp_path: nothing reads the repo's films/ or data/.

SCENES = [{"id": "open", "start": 0.0, "end": 6.008}, {"id": "intro", "start": 6.008, "end": 15.608},
          {"id": "hero", "start": 15.608, "end": 22.808}, {"id": "close", "start": 22.808, "end": 30.0}]


def _write(root, rel, doc):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc))


def test_frame_is_seconds_times_fps():
    assert timing.frame(1.0) == 30
    assert timing.frame(0.0) == 0
    assert timing.frame(18.16) == 545  # 544.8
    assert timing.frame(1.0, 24) == 24
    assert timing.frame(18.16, 25) == 454  # 454.0
    assert timing.frame(1.0, 29.97) == 30  # 29.97


def test_frame_rounds_half_frames_up_like_the_engine():
    # the engine's frameIdx is Math.round(t * fps): halves go up, also for even frames, where Python's round() goes
    # down (round(2.5) == 2). 2.5 / 30 * 30 is exactly 2.5 in floating point.
    assert timing.frame(2.5 / 30) == 3
    assert timing.frame(0.5 / 30) == 1
    assert timing.frame(3.5 / 30) == 4
    assert timing.frame(2.49 / 30) == 2
    assert timing.frame(-2.5 / 30) == -2  # Math.round(-2.5) is -2


def test_scene_frames_match_the_engines_owned_frames():
    # the engine shows a scene on frame n when start <= n / fps < end (engine.ts onScreen, ownedFrames), so a scene's
    # frames run from the first frame at or after its start to the last one before its end
    t = timing.Timing(SCENES)
    assert t.scene_frames("open") == (0, 181)  # 0.0 .. 6.008 s: frame 180 (6.000 s) is still open's
    assert t.scene_frames("intro") == (181, 469)  # 6.008 .. 15.608 s
    assert t.scene_frames("hero") == (469, 685)  # 15.608 .. 22.808 s: 468.24 .. 684.24 frames
    assert t.scene_frames("close") == (685, 900)
    t24 = timing.Timing(SCENES, fps=24)
    assert t24.scene_frames("hero") == (375, 548)  # 374.592 .. 547.392 frames


@pytest.mark.parametrize("start, end, frames", [
    (8.3, 16.1, (249, 483)),  # 8.3 * 30 is 249.00000000000003, and frame 249 is at 8.3: it is the window's
    (2.0, 4.0, (60, 120)),  # both ends on frame times: a frame on the end belongs to the next window
    (15.608, 15.62, (469, 469)),  # a window between two frame times owns no frame
])
def test_scene_frames_take_a_boundary_on_a_frame_time_as_the_engine_does(start, end, frames):
    # engine.test.ts's ownedFrames cases, as [first, last + 1)
    assert timing.Timing([{"id": "s", "start": start, "end": end}]).scene_frames("s") == frames


def test_scene_windows_tile_the_film_without_gaps_or_overlaps():
    t = timing.Timing(SCENES)
    windows = [t.scene_frames(i) for i in t.scene_ids]
    assert windows[0][0] == 0 and windows[-1][1] == 900
    for (_, end), (start, _) in zip(windows, windows[1:]):
        assert end == start


def test_an_unknown_scene_names_the_film_scenes_or_how_to_export_them():
    with pytest.raises(KeyError, match="nope.*open, intro, hero, close"):
        timing.Timing(SCENES, source="x/timeline.json").scene_frames("nope")
    with pytest.raises(KeyError, match="timeline.ts"):
        timing.Timing().scene_frames("hero")


def test_scene_windows_come_from_the_timeline_else_the_voiceover(tmp_path):
    root = tmp_path / "films" / "demo"
    _write(root, "data/vo.json", {"duration": 12, "scenes": [{"id": "hero", "start": 1.0, "end": 2.0}],
                                  "lines": [{"id": "L01", "words": [{"w": "Hello", "start": 1.1, "end": 1.4},
                                                                    {"w": "there.", "start": 1.5, "end": 1.9}]}]})
    t = timing.load(root)
    assert t.scene_frames("hero") == (30, 60) and t.source.endswith("vo.json")
    assert t.word("L01", 1).frame == 45 and t.word("L01", 1).w == "there."
    _write(root, "data/timeline.json",
           {"fps": 30, "duration": 10.0, "scenes": [{"id": "hero", "start": 3.0, "end": 4.0}]})
    t = timing.load(root)  # the engine's export wins over the voiceover's scenes; the words are still the voiceover's
    assert t.scene_frames("hero") == (90, 120) and t.source.endswith("timeline.json")
    assert t.duration == 10.0 and t.word("L01", 0).start == 1.1
    with pytest.raises(IndexError):
        t.word("L01", 2)
    with pytest.raises(KeyError, match="L99"):
        t.word("L99", 0)


def test_a_timeline_exported_at_another_fps_is_refused(tmp_path):
    _write(tmp_path, "data/timeline.json", {"fps": 30, "duration": 4, "scenes": []})
    with pytest.raises(ValueError, match="30 fps but the film runs at 24"):
        timing.load(tmp_path, fps=24)
    assert timing.load(tmp_path, fps=30).fps == 30


def test_a_film_with_no_timing_files_still_loads(tmp_path):
    t = timing.load(tmp_path)
    assert t.scene_ids == [] and t.beats == [] and t.duration is None


def test_beats_come_from_the_analysis(tmp_path):
    # beats every 0.6 s from 0.008: frames 0, 18, 36, 54, 72 ...; downbeats every 4th
    beats = [0.008 + 0.6 * k for k in range(16)]
    _write(tmp_path, "data/audio.json", {"beats": beats, "downbeats": beats[::4]})
    t = timing.load(tmp_path)
    assert t.beats_in(0, 72) == [0, 18, 36, 54]
    assert t.beats_in(1, 37) == [18, 36]
    assert t.downbeats_in(0, 180) == [0, 72, 144]  # 0.008, 2.408, 4.808 s
    assert t.downbeats_in(73, 144) == []


def test_beats_round_like_frame(tmp_path):
    _write(tmp_path, "data/audio.json", {"beats": [2.5 / 30, 4.5 / 30], "downbeats": [2.5 / 30]})
    t = timing.load(tmp_path)
    assert t.beats_in(0, 30) == [3, 5]  # Python's round() would say 2 and 4
    assert t.downbeats_in(0, 30) == [3]


def test_without_an_analysis_the_grid_is_synthesised_from_bpm_offset_and_beats_per_bar(tmp_path):
    _write(tmp_path, "data/timeline.json", {"fps": 30, "duration": 4.0, "scenes": []})
    t = timing.load(tmp_path)  # the defaults: 120 bpm from 0, 4 to the bar: a beat every 0.5 s while before 4 s
    assert t.beats == [0.5 * k for k in range(8)] and t.downbeats == [0.0, 2.0]
    t = timing.load(tmp_path, grid={"bpm": 90, "offset": 0.2, "beatsPerBar": 3})
    assert t.beats == pytest.approx([0.2 + k * 2 / 3 for k in range(6)])  # 0.2 .. 3.533
    assert t.downbeats == pytest.approx([0.2, 2.2])
    assert t.beats_in(0, 120) == [6, 26, 46, 66, 86, 106]


def test_the_synthesised_grid_keeps_its_bars_where_a_negative_offset_drops_early_beats():
    beats, downbeats = timing.beat_grid(3.0, bpm=60, offset=-1.0, beats_per_bar=4)
    assert beats == [0.0, 1.0, 2.0]  # beats -1 (a downbeat) is before the film: beat 0 is at 0.0
    assert downbeats == []  # the next downbeat is at 3.0, the film's end
    assert timing.beat_grid(None) == ([], [])
    with pytest.raises(ValueError):
        timing.beat_grid(4.0, bpm=0)


def test_for_film_reads_the_paths_and_grid_in_film_json(make_film):
    repo = make_film("demo", fps=24, vo="script/voice.json", audio={"analysis": "beats.json", "bpm": 60})
    f = film.load("demo", repo)
    _write(f.root, "script/voice.json", {"duration": 3.0, "scenes": [{"id": "hero", "start": 0.5, "end": 2.0}],
                                         "lines": []})
    t = f.timing()
    assert t.fps == 24 and t.scene_frames("hero") == (12, 48)
    assert t.beats == [0.0, 1.0, 2.0]  # no beats.json: 60 bpm over the voiceover's 3 s
    assert f.timing() is t  # loaded once


def test_parse_frames_takes_inclusive_ranges_and_lists():
    assert timing.parse_frames("40-44") == [40, 41, 42, 43, 44]
    assert timing.parse_frames("47") == [47]
    assert timing.parse_frames("40,47,50-52") == [40, 47, 50, 51, 52]
    assert timing.parse_frames("50-52,40,51") == [40, 50, 51, 52]  # sorted, each frame once


@pytest.mark.parametrize("bad", ["", "a-b", "52-50", "4.5", "-3", "1--2"])
def test_parse_frames_rejects_nonsense(bad):
    with pytest.raises(ValueError):
        timing.parse_frames(bad)
