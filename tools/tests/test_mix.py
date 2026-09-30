import numpy as np
import pytest

from gitloom_film.mix import mix
from gitloom_film.wav import read_wav, write_wav

SR = 48000


def synth(tmp):
    t = np.arange(10 * SR) / SR
    vo = np.zeros_like(t, dtype=np.float32)
    for k in range(0, 10, 2):  # a 1 kHz "voice", on for 1 s every 2 s
        on = (t >= k) & (t < k + 1)
        vo[on] = 0.3 * np.sin(2 * np.pi * 1000 * t[on])
    music = (0.2 * np.random.default_rng(1).standard_normal(len(t))).astype(np.float32)
    write_wav(tmp / "vo.wav", vo)
    write_wav(tmp / "music.wav", np.stack([music, music], axis=1))
    return tmp / "vo.wav", tmp / "music.wav"


def hi_band_db(x):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    return 10 * np.log10(spec[np.fft.rfftfreq(len(x), 1 / SR) > 4000].mean())


def test_mix_hits_loudness_targets(tmp_path):
    vo, mu = synth(tmp_path)
    m = mix(vo, mu, tmp_path / "mix.wav")
    assert m["I"] == pytest.approx(-14.0, abs=0.5) and m["TP"] <= -1.0
    y, sr = read_wav(tmp_path / "mix.wav", mono=False)
    assert sr == 48000 and y.shape[1] == 2


def test_music_ducks_under_the_voice(tmp_path):
    vo, mu = synth(tmp_path)
    mix(vo, mu, tmp_path / "mix.wav")
    y, _ = read_wav(tmp_path / "mix.wav")
    on = np.mean([hi_band_db(y[int((k + 0.3) * SR):int((k + 0.8) * SR)]) for k in range(2, 10, 2)])
    off = np.mean([hi_band_db(y[int((k + 1.3) * SR):int((k + 1.8) * SR)]) for k in range(2, 8, 2)])
    assert off - on >= 4.0  # energy above 4 kHz is music only


def test_mix_applies_automation_when_given_sections(tmp_path):
    vo, mu = synth(tmp_path)
    sections = [{"name": "the tour", "start": 0.0, "end": 4.0}, {"name": "honest", "start": 4.0, "end": 6.0},
                {"name": "proof and everywhere", "start": 6.0, "end": 10.0}]
    mix(vo, mu, tmp_path / "mix.wav", sections=sections)
    y, _ = read_wav(tmp_path / "mix.wav")
    silent = hi_band_db(y[int(4.3 * SR):int(5.8 * SR)])  # music muted (the voice is a 1 kHz tone)
    open_ = hi_band_db(y[int(1.2 * SR):int(1.8 * SR)])  # music playing, voice off
    assert open_ - silent >= 40
