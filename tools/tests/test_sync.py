from gitloom_film.sync import check

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
