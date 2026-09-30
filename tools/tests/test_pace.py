import json
import shutil

import numpy as np
import pytest

from gitloom_film.pace import MAX_FACTOR, MIN_FACTOR, factor_for, pace_take, speech_rate, stretch, trim
from gitloom_film.wav import SR, read_wav, write_wav

needs_rb = pytest.mark.skipif(not shutil.which("rubberband"), reason="brew install rubberband")


def tone(sec, f=220.0, sr=SR):
    t = np.arange(int(sec * sr)) / sr
    return (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32)


def test_trim_cuts_silence_and_shifts_words():
    x = np.concatenate([np.zeros(SR // 2, np.float32), tone(1.0), np.zeros(SR // 2, np.float32)])
    words = [{"w": "a", "start": 0.5, "end": 0.9}, {"w": "b.", "start": 1.0, "end": 1.5}]
    y, w = trim(x, SR, words)
    assert len(y) / SR == pytest.approx(0.04 + 1.0 + 0.08, abs=1e-3)
    assert w[0]["start"] == pytest.approx(0.04) and w[1]["end"] == pytest.approx(1.04)
    assert abs(y[0]) < 1e-6  # faded in, never clicks


def test_rate_and_clamped_factor():
    words = [{"w": str(i), "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(5)]  # 5 words over 2.4 s
    assert speech_rate(words) == pytest.approx(5 / 2.4)
    assert factor_for(words, target_wps=5 / 2.4 / 0.9) == pytest.approx(0.9)
    assert factor_for(words, target_wps=100) == MIN_FACTOR
    assert factor_for(words, target_wps=0.5) == MAX_FACTOR


@needs_rb
def test_stretch_keeps_pitch_and_scales_length():
    y = stretch(tone(1.0, 440.0), SR, 0.9)
    assert len(y) / SR == pytest.approx(0.9, rel=0.01)
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    assert np.fft.rfftfreq(len(y), 1 / SR)[np.argmax(spec)] == pytest.approx(440.0, abs=3.0)


def test_stretch_factor_one_is_a_copy():
    x = tone(0.2)
    assert np.array_equal(stretch(x, SR, 1.0), x)


@needs_rb
def test_pace_take_writes_scaled_words(tmp_path):
    x = np.concatenate([np.zeros(SR // 4, np.float32), tone(1.0)])
    write_wav(tmp_path / "1.wav", x)
    (tmp_path / "1.json").write_text(json.dumps({"line": "L01", "take": 1, "duration": 1.25,
                                                 "words": [{"w": "hey.", "start": 0.25, "end": 1.25}]}))
    out = pace_take(tmp_path / "1.wav", tmp_path / "1.json", tmp_path / "paced", 0.9)
    y, _ = read_wav(tmp_path / "paced" / "1.wav")
    assert out["factor"] == 0.9
    assert out["words"][0]["start"] == pytest.approx(0.04 * 0.9, abs=1e-3)
    assert out["duration"] == pytest.approx(len(y) / SR, abs=1e-3)
    assert json.loads((tmp_path / "paced" / "1.json").read_text())["factor"] == 0.9
