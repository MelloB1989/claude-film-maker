import json

import numpy as np
import pytest

from filmtools import temptrack as tt
from filmtools.vochain import loudness
from filmtools.wav import read_wav

SR = 48000
BEATS_KEYS = {"duration", "bpm", "beat_period", "time_signature", "beats", "downbeats", "sections", "fps", "rms", "low",
              "mid", "high", "vocal", "drums", "bass", "other", "onsets", "grid_error_ms", "grid_fit"}


@pytest.fixture(scope="module")
def pulse():
    return tt.render(tt.make_grid(120, 4, bars=8), "pulse", seed=5, phrase=2)


@pytest.fixture(scope="module")
def cinematic():
    return tt.render(tt.make_grid(90, 3, duration=17.3, offset=0.25), "cinematic", seed=5, phrase=2)


def peak_db(x):
    return 20 * np.log10(np.abs(x).max())


def test_the_grid_is_exact():
    g = tt.make_grid(97, 3, bars=5, offset=0.1)
    assert g.duration == pytest.approx(0.1 + 5 * 3 * 60 / 97)
    assert np.allclose(g.beats, 0.1 + np.arange(15) * 60 / 97, atol=1e-12)
    assert np.allclose(g.downbeats, g.beats[::3])
    g = tt.make_grid(120, 4, duration=10.3)  # a film's length is kept, the last bar left short
    assert (g.bars, g.duration, len(g.beats), g.beats[-1]) == (6, 10.3, 21, 10.0)
    with pytest.raises(ValueError):
        tt.make_grid(0, 4, bars=4)


@pytest.mark.parametrize("style", tt.STYLES)
def test_one_seed_one_score(style):
    g = tt.make_grid(128, 4, bars=4)
    a, b = tt.render(g, style, seed=9, phrase=2), tt.render(g, style, seed=9, phrase=2)
    assert np.array_equal(a.audio, b.audio) and a.onsets == b.onsets
    assert not np.array_equal(a.audio, tt.render(g, style, seed=10, phrase=2).audio)


@pytest.mark.parametrize("name", ["pulse", "cinematic"])
def test_peak_safe_stereo_at_the_films_length_and_about_the_target(name, request):
    s = request.getfixturevalue(name)
    assert s.audio.dtype == np.float32 and s.audio.shape == (int(round(s.grid.duration * SR)), 2)
    assert peak_db(s.audio) <= -1.0
    assert -15.5 <= s.lufs <= -13.5 and loudness(s.audio, SR) == pytest.approx(s.lufs, abs=0.01)
    assert np.abs(s.audio[:5]).max() < 0.01 and np.abs(s.audio[-5:]).max() < 0.01  # faded in and out
    assert np.abs(np.diff(s.audio, axis=0)).max() < 0.5  # no clicks: no sample jumps


def test_the_analysis_has_film_beats_schema_and_the_exact_grid(pulse):
    a = tt.analysis(pulse)
    assert set(a) == BEATS_KEYS and set(a["onsets"]) == {"kick", "snare", "hat", "vocal"}
    assert (a["bpm"], a["beat_period"], a["time_signature"], a["fps"], a["duration"]) == (120, 0.5, 4, 100, 16.0)
    assert a["beats"] == [round(0.5 * k, 6) for k in range(32)] and a["downbeats"] == a["beats"][::4]
    n = 1600
    for k in ("rms", "low", "mid", "high", "vocal", "drums", "bass", "other"):
        assert len(a[k]) == n and min(a[k]) >= 0 and max(a[k]) <= 1
    assert not any(a["vocal"]) and a["onsets"]["vocal"] == []
    assert max(a["drums"]) == 1.0 and max(a["rms"]) == 1.0
    kicks = [t for t, _ in a["onsets"]["kick"]]
    assert kicks and set(kicks) <= set(a["beats"])  # four on the floor: every kick on a beat
    assert all(0 < v <= 1 for _, v in a["onsets"]["kick"] + a["onsets"]["hat"])
    assert [s["start"] for s in a["sections"]] == [0.0, 4.0, 8.0, 12.0] and a["sections"][-1]["end"] == 16.0
    assert [s["name"] for s in a["sections"]] == ["intro", "groove", "break", "groove 2"]
    assert (a["grid_fit"], a["grid_error_ms"]) == (1.0, 0.0)


def test_film_beats_hears_the_grid_it_was_given(pulse):
    from filmtools.beats import analyze
    meta = {"bpm": 120.0, "sections": [{"name": s["name"], "start": s["start"], "end": s["end"]}
                                       for s in pulse.sections]}
    heard = analyze(pulse.audio.mean(axis=1), SR, meta, automate=False)
    assert set(heard) == BEATS_KEYS
    assert heard["bpm"] == pytest.approx(120.0, abs=0.5)
    exact = np.asarray(tt.analysis(pulse)["beats"])
    near = [float(np.min(np.abs(exact - b))) for b in heard["beats"] if b < 15.5]
    assert np.median(near) < 0.02


def test_cinematic_hits_land_on_downbeats_and_risers_end_on_them(cinematic):
    a = tt.analysis(cinematic)
    assert a["time_signature"] == 3 and a["beats"][0] == 0.25 and a["duration"] == 17.3
    assert set(t for t, _ in a["onsets"]["kick"]) <= set(a["beats"]) and a["onsets"]["snare"] == []
    riser = np.abs(cinematic.stems["riser"]).max(axis=1)
    assert riser.any()
    for s in cinematic.sections[1:]:
        i = int(round(s["start"] * SR))
        before = riser[i - SR // 10:i].max()
        if before > 0:  # a riser into this section: loud just before the downbeat, gone after (40 dB down at least;
            assert riser[i + 10:i + SR // 10].max() < 0.01 * before  # the next one may be fading in from silence)


def test_sections_follow_the_style():
    assert tt.arrangement(1, "pulse") == ["groove"]
    assert tt.arrangement(4, "pulse") == ["intro", "groove", "break", "groove"]
    assert tt.arrangement(7, "pulse") == ["intro", "groove", "groove", "groove", "break", "groove", "outro"]
    assert tt.arrangement(5, "cinematic") == ["intro", "build", "build", "peak", "outro"]
    with pytest.raises(ValueError, match="style"):
        tt.render(tt.make_grid(120, 4, bars=1), "polka")


def test_film_temptrack_writes_the_score_its_grid_and_its_pick(film):
    (film.data / "timeline.json").write_text(json.dumps({"fps": 30, "duration": 9.0, "scenes": [
        {"id": "a", "start": 0, "end": 4}, {"id": "b", "start": 4, "end": 9}]}))
    film.config.write_text(json.dumps({"id": "demo", "audio": {"bpm": 100, "beatsPerBar": 4}}))
    tt.main(["--seed", "3", "--mix"])
    wav = film.audio / "music" / "temp.wav"
    y, sr = read_wav(wav, mono=False)
    assert sr == SR and y.shape == (9 * SR, 2) and peak_db(y) <= -1.0  # the film's length, from its timeline
    a = json.loads((film.data / "audio.json").read_text())
    assert a["bpm"] == 100 and a["duration"] == 9.0 and a["beats"][:3] == [0.0, 0.6, 1.2]
    mp = json.loads((film.data / "music_plan.json").read_text())
    assert mp["chosen"] == "audio/music/temp.wav"
    side = json.loads(wav.with_suffix(".plan.json").read_text())
    assert side["meta"]["bpm"] == 100 and side["temptrack"]["seed"] == 3
    assert (film.audio / "mix" / "mix.wav").read_bytes() == wav.read_bytes()

    from filmtools.music import pick_meta
    assert pick_meta(mp) == side["meta"]  # film-beats and film-splice read its timing like any score's


def test_another_pick_stands_unless_chosen(film):
    (film.data / "music_plan.json").write_text(json.dumps({"chosen": "audio/music/score-seed1.wav"}))
    tt.main(["--bars", "2", "--bpm", "140", "--out", str(film.audio / "music" / "t2.wav")])
    assert json.loads((film.data / "music_plan.json").read_text())["chosen"] == "audio/music/score-seed1.wav"
    y, _ = read_wav(film.audio / "music" / "t2.wav", mono=False)
    assert len(y) == int(round(2 * 4 * 60 / 140 * SR))
    tt.main(["--bars", "2", "--style", "cinematic", "--choose"])
    assert json.loads((film.data / "music_plan.json").read_text())["chosen"] == "audio/music/temp.wav"


def test_without_a_timeline_it_runs_sixteen_bars(film):
    tt.main(["--beats-per-bar", "3"])
    a = json.loads((film.data / "audio.json").read_text())
    assert a["time_signature"] == 3 and len(a["beats"]) == 48 and a["duration"] == pytest.approx(24.0)


def test_film_beats_keeps_a_temp_tracks_grid_through_a_splice(film):
    from filmtools import beats, splice
    tt.main(["--bars", "8", "--bpm", "110", "--offset", "0.2", "--style", "cinematic", "--phrase", "4"])
    exact = json.loads((film.data / "audio.json").read_text())
    beats.main([])  # the chain runs film-beats after the score: the grid stays the one the score was made on
    heard = json.loads((film.data / "audio.json").read_text())
    assert heard["beats"] == exact["beats"] and heard["downbeats"] == exact["downbeats"]
    assert heard["grid_error_ms"] == 0.0 and heard["bpm"] == 110.0
    splice.main(["--map", "4-7,0-3"])
    beats.main([])
    cut = json.loads((film.data / "audio.json").read_text())
    assert cut["beats"] == exact["beats"]  # whole bars moved on the grid: the edit keeps it
