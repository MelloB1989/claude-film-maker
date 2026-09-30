import librosa
import numpy as np
import pytest

from gitloom_film.beats import analyze, fit_grid, grid_fit

SR = 22050
META = {"bpm": 100.0, "sections": [{"name": "a", "start": 0.0, "end": 14.4}, {"name": "b", "start": 14.4, "end": 30.0}]}


def clicks(bpm=100.0, dur=30.0, offset=0.25, silent=None, bpm2=None, switch=15.0):
    y = np.zeros(int(dur * SR), np.float32)
    L = int(0.05 * SR)
    k = np.arange(L) / SR
    t, i = offset, 0
    while t < dur - 0.1:
        if not (silent and silent[0] <= t < silent[1]):
            if i % 4 == 0:
                burst = np.exp(-k / 0.03) * np.sin(2 * np.pi * 60 * k)  # a kick on the one
            else:
                burst = 0.3 * np.exp(-k / 0.005) * np.sin(2 * np.pi * 3000 * k)  # a tick
            n = int(round(t * SR))
            y[n:n + L] += burst.astype(np.float32)
        t += 60.0 / (bpm2 if bpm2 and t >= switch else bpm)
        i += 1
    return y


def test_grid_tempo_phase_and_downbeats():
    a = analyze(clicks(), SR, META)
    b, d = np.array(a["beats"]), np.array(a["downbeats"])
    assert a["bpm"] == pytest.approx(100.0, abs=0.3) and a["grid_error_ms"] < 20
    assert np.min(np.abs(b - 0.25)) < 0.02
    assert np.min(np.abs(d - 0.25)) < 0.02 and np.min(np.abs(d - 2.65)) < 0.02
    assert len(a["rms"]) == 3000 and min(a["low"]) >= 0.0 and max(a["low"]) <= 1.0
    assert a["sections"][1]["start"] == pytest.approx(14.65, abs=0.03)  # 14.4 snapped to the downbeat
    assert a["sections"][-1]["end"] == pytest.approx(a["duration"])
    assert len(a["onsets"]["kick"]) >= 8


def test_grid_runs_through_silence():
    a = analyze(clicks(silent=(10.0, 18.0)), SR, META)
    inside = np.array([t for t in a["beats"] if 10.5 < t < 17.5])
    assert len(inside) >= 10
    expected = 0.25 + np.round((inside - 0.25) / 0.6) * 0.6
    assert np.max(np.abs(inside - expected)) < 0.02


def test_steady_score_fits_and_drift_is_reported():
    assert analyze(clicks(), SR, META)["grid_fit"] >= 0.9
    assert analyze(clicks(bpm2=110.0), SR, META)["grid_fit"] < 0.8  # the tempo changes mid-track


def test_vocal_onsets_and_envelope_come_from_the_voice():
    vo = {"lines": [{"words": [{"w": "a", "start": 1.0, "end": 1.2}, {"w": "b", "start": 2.0, "end": 2.2}]}]}
    vo_y = np.zeros(30 * SR, np.float32)
    vo_y[SR:int(1.2 * SR)] = 0.5
    a = analyze(clicks(), SR, META, vo=vo, vo_y=vo_y)
    assert a["onsets"]["vocal"] == [[1.0, 1.0], [2.0, 1.0]]
    assert a["vocal"][110] > 0.5 and a["vocal"][150] < 0.1


def test_grid_fit_counts_misses_and_skips_beats_outside_audible_stretches():
    grid, onsets = np.array([1.0, 2.0, 3.0, 4.0]), np.array([1.02, 2.5, 3.0])
    assert grid_fit(grid, onsets, np.array([True, True, True, False])) == pytest.approx(2 / 3)
    assert grid_fit(grid, onsets, np.array([True, False, True, False])) == 1.0
    assert grid_fit(grid, onsets, np.zeros(4, bool)) == 0.0 and grid_fit(grid, np.array([]), np.ones(4, bool)) == 0.0
    assert grid_fit(np.array([1.0]), np.array([1.029]), np.array([True])) == 1.0  # the window is 30 ms
    assert grid_fit(np.array([1.0]), np.array([1.031]), np.array([True])) == 0.0


def test_fit_grid_is_not_tilted_by_the_trackers_stray_end_beats():
    good = 0.25 + 0.6 * np.arange(48)
    astray = good[-1] + np.array([0.6 - 0.079, 1.2 - 0.162])  # a fade-out leaves the tracker's last beats off the line
    grid, period, _ = fit_grid(np.concatenate([good, astray]), 30.0)
    assert period == pytest.approx(0.6, abs=0.0001) and grid[0] == pytest.approx(0.25, abs=0.001)


def test_grid_holds_at_the_pipelines_sample_rate():
    y = librosa.resample(clicks(), orig_sr=SR, target_sr=48000)  # the score is 48 kHz, so is the voiceover
    a = analyze(y, 48000, META)
    assert a["bpm"] == pytest.approx(100.0, abs=0.05) and abs(a["beats"][0] - 0.25) < 0.005 and a["grid_fit"] >= 0.9
