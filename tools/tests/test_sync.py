import numpy as np
import pytest

from gitloom_film.sync import any_sound, check, report, section_table, word_sync

BEATS = [round(0.2 + 0.6 * k, 4) for k in range(160)]
AUDIO = {"beats": BEATS, "downbeats": BEATS[::4]}  # downbeats 0.2, 2.6, 5.0, 7.4, 9.8, …
SCRIPT = {"acts": [{"id": "I", "name": "A", "scenes": ["s1", "s2"]}, {"id": "II", "name": "B", "scenes": ["s3"]}]}


def good():
    line = lambda lid, s, t: {"id": lid, "scene": s, "start": t, "end": t + 1.0,  # noqa: E731
                              "words": [{"w": "a", "start": t + 0.04, "end": t + 0.9}]}
    return {"duration": 90.0, "lines": [line("L1", "s1", 1.0), line("L2", "s2", 4.0), line("L3", "s3", 9.0)],
            "scenes": [{"id": "s1", "start": 0.0, "end": 3.8}, {"id": "s2", "start": 3.8, "end": 7.4},
                       {"id": "s3", "start": 7.4, "end": 90.0}]}


def test_clean_edit_passes():
    assert check(good(), AUDIO, SCRIPT) == []


def test_off_beat_cut_and_act_off_downbeat_are_reported():
    vo = good()
    vo["scenes"][0]["end"] = vo["scenes"][1]["start"] = 3.9  # 100 ms after a beat
    vo["scenes"][1]["end"] = vo["scenes"][2]["start"] = 8.0  # a beat, but not a downbeat
    p = check(vo, AUDIO, SCRIPT)
    assert any("cut s2" in x and "off the beat" in x for x in p)
    assert any("cut s3" in x and "off the downbeat" in x for x in p)


def test_overlap_and_duration_are_reported():
    vo = good()
    vo["lines"][1]["start"] = 1.5
    vo["duration"] = 97.0
    p = check(vo, AUDIO, SCRIPT)
    assert any("L2 overlaps" in x for x in p) and any("duration" in x for x in p)


def test_line_outside_its_scene_is_reported():
    vo = good()
    vo["scenes"][1]["start"] = vo["scenes"][0]["end"] = 4.4  # cuts after L2's first word
    assert any("L2 is not inside its scene" in x for x in check(vo, AUDIO, SCRIPT))


def test_word_outside_its_line_is_reported():
    vo = good()
    vo["lines"][0]["words"][0]["end"] = vo["lines"][0]["end"] + 0.5  # past its line, still inside its scene
    assert check(vo, AUDIO, SCRIPT) == ["L1 word 'a' lies outside its line"]


SR = 48000


def voice(duration, onsets, length=0.5):
    """A voiceover track: a 150 Hz voice starting at each onset (seconds, exact), silence elsewhere."""
    y = np.zeros(int(duration * SR), np.float32)
    for t in onsets:
        i = int(round(t * SR))
        n = int(length * SR)
        y[i:i + n] = 0.3 * np.sin(2 * np.pi * 150 * np.arange(n) / SR)
    return y


def spoken(starts):
    """Two lines; each word lasts 0.3 s. `starts` holds the placed (vo.json) start of L1's and L2's first word."""
    return {"lines": [{"id": "L1", "start": 1.0, "end": 2.0, "words": [{"w": "I", "start": starts[0], "end": 1.5}]},
                      {"id": "L2", "start": 3.0, "end": 4.0,
                       "words": [{"w": "commit.", "start": starts[1], "end": 3.6}]}]}


def test_words_that_light_within_a_frame_after_their_onset_pass():
    y = voice(5.0, [1.1, 3.2011])  # 3.2011 is not on a frame: the word lights on the next one, 32 ms later
    problems, rows = word_sync(spoken([1.1, 3.2011]), y, SR)
    assert problems == []
    assert [(r["line"], r["word"]) for r in rows] == [("L1", "I"), ("L2", "commit.")]
    assert rows[0]["error_ms"] == pytest.approx(0, abs=0.2) and 0 <= rows[1]["error_ms"] <= 35


def test_a_word_that_lights_late_is_reported_in_ms():
    y = voice(5.0, [1.1, 3.2])
    problems, _ = word_sync(spoken([1.2, 3.2]), y, SR)  # lit at 1.2, spoken at 1.1
    assert problems == ["L1 word 'I' lights 100 ms after its spoken onset (1.100 s)"]


def test_a_word_that_lights_ahead_of_the_voice_is_reported():
    y = voice(5.0, [1.1, 3.2])
    problems, _ = word_sync(spoken([1.1, 3.15]), y, SR)  # lit at 3.1667, spoken at 3.2
    assert problems == ["L2 word 'commit.' lights 33 ms ahead of its spoken onset (3.200 s)"]


def test_a_line_whose_first_word_has_no_onset_is_reported():
    y = voice(5.0, [1.1])  # L2 is silent in the track: the voiceover is out of step with vo.json
    problems, _ = word_sync(spoken([1.1, 3.2]), y, SR)
    assert problems == ["L2 word 'commit.': no spoken onset near its start"]


WAIVERS = {"cut her": "act cut on a beat: no downbeat fits; ruled at Task 15, C3-approved"}


def test_waived_problems_are_listed_but_do_not_fail():
    problems = ["cut her at 16.208s is 600 ms off the downbeat", "cut hero at 20.000s is 100 ms off the beat",
                "L32 word 'I' lights 108 ms after its spoken onset (90.258 s)"]
    lines, failed = report(problems, WAIVERS)
    assert failed
    assert ("waived: cut her at 16.208s is 600 ms off the downbeat (act cut on a beat: no downbeat fits; ruled at "
            "Task 15, C3-approved)") in lines
    assert "✗ cut hero at 20.000s is 100 ms off the beat" in lines  # a waiver names one scene, whole
    assert lines[-1] == "2 problem(s), 1 waived"


def test_only_waived_problems_pass_the_gate():
    lines, failed = report(["cut her at 16.208s is 600 ms off the downbeat"], WAIVERS)
    assert not failed and lines[-1] == "sync OK (1 waived)"


def test_a_waiver_that_matches_nothing_is_pointed_out_without_failing():
    lines, failed = report([], {**WAIVERS, "cut loom": "ruled"})
    assert not failed and lines[-1] == "sync OK"
    assert "note: waiver 'cut her' matches no problem" in lines and "note: waiver 'cut loom' matches no problem" in lines


def test_section_table_gives_each_section_start_against_the_cut_it_opens():
    vo = {"scenes": [{"id": "thread", "start": 0.0}, {"id": "ex", "start": 6.008}, {"id": "her", "start": 16.208},
                     {"id": "loom", "start": 28.208}, {"id": "honest", "start": 61.208}, {"id": "proof", "start": 66.008},
                     {"id": "weave", "start": 86.408}]}
    audio = {"sections": [{"name": "cold open", "start": 0.0}, {"name": "the ex", "start": 7.208},
                          {"name": "her", "start": 16.808}, {"name": "the tour", "start": 28.808},
                          {"name": "honest", "start": 62.408}, {"name": "proof and everywhere", "start": 67.208},
                          {"name": "weave", "start": 86.408}]}
    rows = section_table(vo, audio)
    assert [(r["section"], r["scene"], r["delta_ms"]) for r in rows] == [
        ("cold open", "thread", 0), ("the ex", "ex", 1200), ("her", "her", 600), ("the tour", "loom", 600),
        ("honest", "honest", 1200), ("proof and everywhere", "proof", 1200), ("weave", "weave", 0)]


def test_an_act_cut_off_the_beat_grid_cannot_be_waived():
    vo = good()
    vo["scenes"][1]["end"] = vo["scenes"][2]["start"] = 8.1  # s3 opens act II, 100 ms after the 8.0 beat
    problems = check(vo, AUDIO, SCRIPT)
    assert problems == ["cut s3 at 8.100s: act cut not on a beat (100 ms off the nearest beat)"]
    lines, failed = report(problems, {"cut s3": "act cut on a beat: no downbeat fits"})
    assert failed and lines[0] == "✗ cut s3 at 8.100s: act cut not on a beat (100 ms off the nearest beat)"


def hissed(duration, lines):
    """A voiceover track: for each (head, voice) an audible /s/ (4-8 kHz noise at -12 dB) from `head` running into a
    150 Hz voice at `voice`."""
    y = np.zeros(int(duration * SR), np.float32)
    rng = np.random.default_rng(0)
    for head, at in lines:
        n, i = int(round((at - head) * SR)), int(round(head * SR))
        if n:
            spec = np.fft.rfft(rng.standard_normal(n))
            f = np.fft.rfftfreq(n, 1 / SR)
            spec[(f < 4000) | (f > 8000)] = 0
            hiss = np.fft.irfft(spec, n)
            y[i:i + n] = 0.3 / np.sqrt(2) * 10 ** (-12 / 20) * hiss / np.sqrt(np.mean(hiss ** 2))
        k = int(0.5 * SR)
        y[i + n:i + n + k] = 0.3 * np.sin(2 * np.pi * 150 * np.arange(k) / SR)
    return y


def test_a_line_that_lights_well_after_its_first_sound_fails_the_any_sound_check():
    y = hissed(5.0, [(1.10, 1.22), (3.2, 3.2)])  # L1 opens with 120 ms of /s/
    assert any_sound(spoken([1.16, 3.2]), y, SR) == [
        "L1 word 'I' lights 67 ms after the first sound in its window (1.100 s)"]  # lit at 1.1667
    assert any_sound(spoken([1.12, 3.2]), y, SR) == []  # lit at 1.1333, 33 ms after it


def test_word_sync_measures_each_word_on_its_takes_own_window():
    # L1's word is placed at its onset, the start of a 150 ms /s/; its voiced run is at 1.25. The take's aligned
    # times (relative to the line) give the window film-pace measured it in; a window around the placed start
    # alone ends at 1.18 and never reaches the voice.
    y = hissed(5.0, [(1.10, 1.25), (3.2, 3.2)])
    vo = spoken([1.1, 3.2])
    takes = {"L1": [{"w": "I", "start": 0.27, "end": 0.5}], "L2": [{"w": "commit.", "start": 0.2, "end": 0.6}]}
    problems, rows = word_sync(vo, y, SR, takes)
    assert problems == [] and rows[0]["onset"] == pytest.approx(1.10, abs=0.005)
    assert word_sync(vo, y, SR)[0] == ["L1 word 'I': no spoken onset near its start"]


def test_a_missing_voiceover_is_a_clear_message(tmp_path, monkeypatch):
    from gitloom_film import sync
    monkeypatch.setattr(sync, "AUDIO", tmp_path)
    with pytest.raises(SystemExit, match="audio/vo/vo.wav is missing: run film-edit"):
        sync.main([])


def test_a_line_with_no_sound_near_its_first_word_fails_the_any_sound_check():
    y = hissed(5.0, [(1.10, 1.22)])  # L2 is silent in the track
    assert any_sound(spoken([1.12, 3.2]), y, SR) == ["L2 word 'commit.': no audible sound in its window"]
