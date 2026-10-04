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
    dipped = hi_band_db(y[int(4.3 * SR):int(5.8 * SR)])  # music dipped 12 dB (the voice is a 1 kHz tone)
    open_ = hi_band_db(y[int(1.2 * SR):int(1.8 * SR)])  # music playing, voice off
    assert open_ - dipped >= 10


def test_mastering_keeps_the_drawn_arc(tmp_path):
    t = np.arange(12 * SR) / SR
    music = (0.2 * np.random.default_rng(2).standard_normal(len(t))).astype(np.float32)
    write_wav(tmp_path / "m.wav", np.stack([music, music], axis=1))
    write_wav(tmp_path / "v.wav", np.zeros(len(t), np.float32))
    sections = [{"name": "the tour", "start": 0.0, "end": 6.0}, {"name": "honest", "start": 6.0, "end": 12.0}]
    mix(tmp_path / "v.wav", tmp_path / "m.wav", tmp_path / "mix.wav", sections=sections)
    y, _ = read_wav(tmp_path / "mix.wav")
    rms = lambda a, b: 20 * np.log10(np.sqrt(np.mean(y[int(a * SR):int(b * SR)] ** 2)))  # noqa: E731
    assert rms(7.0, 9.5) - rms(1.0, 5.0) == pytest.approx(-12.0, abs=1.0)  # honest sits 12 dB under the tour


def test_mastering_keeps_the_voice_on_its_sample(tmp_path):
    n = 4 * SR
    t = np.arange(n) / SR
    vo = np.zeros(n, np.float32)
    vo[t >= 1.0] = 0.3 * np.sin(2 * np.pi * 1000 * (t[t >= 1.0] - 1.0))  # a tone that starts at exactly 1.000 s
    write_wav(tmp_path / "vo.wav", vo)
    write_wav(tmp_path / "music.wav", np.zeros((n, 2), np.float32))
    mix(tmp_path / "vo.wav", tmp_path / "music.wav", tmp_path / "mix.wav")
    y, _ = read_wav(tmp_path / "mix.wav")
    onset = lambda a: int(np.argmax(np.abs(a) > 0.05 * np.abs(a).max()))  # noqa: E731
    assert abs(onset(y) - onset(vo)) <= 1  # a look-ahead limiter must not delay the mix against the picture


# ---------------------------------------------------------------- the final mix with stems (Plan 3, Task 9)

from gitloom_film.mix import duck_depth, mix_stems  # noqa: E402


def clicks_every(period, peak, seconds):
    n = int(seconds * SR)
    y = np.zeros(n, np.float32)
    k = np.arange(int(0.02 * SR))
    click = peak * np.exp(-k / (0.002 * SR)) * np.sign(np.sin(2 * np.pi * 2500 * k / SR) + 1e-9)
    for s in np.arange(0.25, seconds - 0.05, period):
        i = int(s * SR)
        y[i:i + len(k)] += click
    return np.stack([y, y], axis=1)


def synth3(tmp, seconds=10):
    """A voice at a spoken level (−17 dBFS RMS while on, where her processed voice's envelope sits mid-phrase), on
    1 s in every 2,
    a noise score at about the score's level, and light effects clicks."""
    t = np.arange(seconds * SR) / SR
    vo = np.zeros_like(t, dtype=np.float32)
    for k in range(0, seconds, 2):
        on = (t >= k) & (t < k + 1)
        vo[on] = 0.2 * np.sin(2 * np.pi * 1000 * t[on])
    music = (0.1 * np.random.default_rng(1).standard_normal(len(t))).astype(np.float32)
    write_wav(tmp / "vo.wav", vo)
    write_wav(tmp / "music.wav", np.stack([music, music], axis=1))
    write_wav(tmp / "sfx.wav", clicks_every(0.7, 0.1, seconds))
    return tmp / "vo.wav", tmp / "music.wav", tmp / "sfx.wav"


def test_hot_sfx_transients_keep_the_master_in_spec(tmp_path):
    vo, mu = synth(tmp_path)
    sfx = tmp_path / "sfx.wav"
    write_wav(sfx, clicks_every(0.5, peak=1.0, seconds=10))
    m = mix_stems(vo, mu, sfx, tmp_path / "mix")
    assert m["I"] == pytest.approx(-14.0, abs=0.5) and m["TP"] <= -1.0
    for stem in ("mix", "vo", "music", "sfx"):
        y, sr = read_wav(tmp_path / "mix" / f"{stem}.wav", mono=False)
        assert sr == 48000 and y.shape == (10 * SR, 2)


def test_stems_sum_to_the_premaster_mix(tmp_path):
    m = mix_stems(*synth3(tmp_path), tmp_path / "mix")
    assert m["stem_residual_db"] <= -30  # (vo + music + sfx) − mix, where the limiter is idle


def test_music_ducks_six_to_nine_db_under_the_voice(tmp_path):
    assert 6.0 <= mix_stems(*synth3(tmp_path), tmp_path / "mix")["duck_db"] <= 9.0


def test_the_effects_duck_lightly_under_the_voice(tmp_path):
    vo, mu, sfx = synth3(tmp_path)
    m = mix_stems(vo, mu, sfx, tmp_path / "mix")
    raw, _ = read_wav(sfx)
    out, _ = read_wav(tmp_path / "mix" / "sfx.wav")
    v, _ = read_wav(vo)
    assert 2.0 <= duck_depth(raw * 10 ** (m["gain_db"] / 20), out, v, SR) <= 4.0  # ratio 2: about 3 dB, light


def test_the_arc_survives_with_sfx(tmp_path):
    t = np.arange(12 * SR) / SR
    music = (0.2 * np.random.default_rng(2).standard_normal(len(t))).astype(np.float32)
    write_wav(tmp_path / "m.wav", np.stack([music, music], axis=1))
    write_wav(tmp_path / "v.wav", np.zeros(len(t), np.float32))
    write_wav(tmp_path / "s.wav", clicks_every(1.0, 0.02, 12))
    sections = [{"name": "the tour", "start": 0.0, "end": 6.0}, {"name": "honest", "start": 6.0, "end": 12.0}]
    mix_stems(tmp_path / "v.wav", tmp_path / "m.wav", tmp_path / "s.wav", tmp_path / "mix", sections=sections)
    y, _ = read_wav(tmp_path / "mix" / "mix.wav")
    rms = lambda a, b: 20 * np.log10(np.sqrt(np.mean(y[int(a * SR):int(b * SR)] ** 2)))  # noqa: E731
    assert rms(7.0, 9.5) - rms(1.0, 5.0) == pytest.approx(-12.0, abs=1.0)  # honest sits 12 dB under the tour


def test_a_music_duck_silences_only_the_music(tmp_path):
    vo, mu, sfx = synth3(tmp_path)
    ducks = [{"t": 3.0, "dur": 2 / 30, "depth": -30, "fade": 0.005, "bus": "music"}]
    g = {"a": mix_stems(vo, mu, sfx, tmp_path / "a", ducks=[])["gain_db"],
         "b": mix_stems(vo, mu, sfx, tmp_path / "b", ducks=ducks)["gain_db"]}  # the master gain is not the duck
    rd = lambda d, s, a, b: read_wav(tmp_path / d / f"{s}.wav")[0][int(a * SR):int(b * SR)] \
        / 10 ** (g[d] / 20)  # noqa: E731
    rms = lambda x: np.sqrt(np.mean(x ** 2))  # noqa: E731
    w = (3.006, 3.06)
    assert 20 * np.log10(rms(rd("b", "music", *w)) / rms(rd("a", "music", *w))) <= -28
    for s in ("vo", "sfx"):
        assert np.allclose(rd("a", s, 0, 10), rd("b", s, 0, 10), atol=1e-6)  # the voice and effects untouched
    assert rms(rd("b", "music", 4.0, 4.9)) == pytest.approx(rms(rd("a", "music", 4.0, 4.9)), rel=1e-3)


def test_an_all_duck_never_touches_the_voice(tmp_path):
    vo, mu, sfx = synth3(tmp_path)
    ducks = [{"t": 2.0, "dur": 0.5, "depth": -20, "fade": 0.01, "bus": "all"}]
    g = {"a": mix_stems(vo, mu, sfx, tmp_path / "a", ducks=[])["gain_db"],
         "b": mix_stems(vo, mu, sfx, tmp_path / "b", ducks=ducks)["gain_db"]}
    rd = lambda d, s: read_wav(tmp_path / d / f"{s}.wav")[0][int(2.05 * SR):int(2.45 * SR)] \
        / 10 ** (g[d] / 20)  # noqa: E731
    rms = lambda x: np.sqrt(np.mean(x ** 2))  # noqa: E731
    assert np.allclose(rd("a", "vo"), rd("b", "vo"), atol=1e-6)
    for s in ("music", "sfx"):
        assert 20 * np.log10(rms(rd("b", s)) / rms(rd("a", s))) == pytest.approx(-20, abs=0.5)


def test_the_voice_stays_on_its_sample(tmp_path):
    n = 4 * SR
    t = np.arange(n) / SR
    vo = np.zeros(n, np.float32)
    vo[t >= 1.0] = 0.3 * np.sin(2 * np.pi * 1000 * (t[t >= 1.0] - 1.0))
    write_wav(tmp_path / "vo.wav", vo)
    write_wav(tmp_path / "music.wav", np.zeros((n, 2), np.float32))
    write_wav(tmp_path / "sfx.wav", np.zeros((n, 2), np.float32))
    mix_stems(tmp_path / "vo.wav", tmp_path / "music.wav", tmp_path / "sfx.wav", tmp_path / "mix")
    onset = lambda a: int(np.argmax(np.abs(a) > 0.05 * np.abs(a).max()))  # noqa: E731
    for stem in ("mix", "vo"):
        y, _ = read_wav(tmp_path / "mix" / f"{stem}.wav")
        assert abs(onset(y) - onset(vo)) <= 1


def test_a_missing_sfx_mixes_without_effects(tmp_path):
    vo, mu, _ = synth3(tmp_path)
    m = mix_stems(vo, mu, None, tmp_path / "mix")
    assert m["I"] == pytest.approx(-14.0, abs=0.5)
    y, _ = read_wav(tmp_path / "mix" / "sfx.wav")
    assert not y.any()


def test_stems_keep_their_overs(tmp_path):
    """The stems are pre-limiter: a voice whose peaks the master gain lifts over 0 dBFS must not clip in its stem."""
    n = 6 * SR
    t = np.arange(n) / SR
    vo = (0.05 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    vo[::SR // 4] = 0.9  # sparse spikes: little loudness, a high crest
    write_wav(tmp_path / "vo.wav", vo)
    write_wav(tmp_path / "music.wav", np.zeros((n, 2), np.float32))
    m = mix_stems(tmp_path / "vo.wav", tmp_path / "music.wav", None, tmp_path / "mix")
    y, _ = read_wav(tmp_path / "mix" / "vo.wav", mono=False)
    assert m["stem_peak_db"]["vo"] > 0 and np.abs(y).max() == pytest.approx(10 ** (m["stem_peak_db"]["vo"] / 20),
                                                                              rel=1e-4)


def test_film_mix_needs_the_processed_voice(tmp_path, monkeypatch):
    import gitloom_film.mix as mixmod
    monkeypatch.setattr(mixmod, "AUDIO", tmp_path)
    with pytest.raises(SystemExit, match="film-vo-chain"):
        mixmod.main([])


def test_review_flags_effects_that_crowd_a_word(tmp_path):
    from gitloom_film.mix import review
    vo, mu, _ = synth3(tmp_path)
    sfx = tmp_path / "loud.wav"
    y = np.zeros((10 * SR, 2), np.float32)
    y[int(4.2 * SR):int(4.2 * SR) + int(0.4 * SR)] = 0.2 * np.random.default_rng(5).standard_normal((int(0.4 * SR), 2))
    write_wav(sfx, y)  # a hiss as loud as the voice, inside the second "word"
    mix_stems(vo, mu, sfx, tmp_path / "mix")
    data = {"scenes": [{"id": "a", "start": 0.0, "end": 5.0}, {"id": "b", "start": 5.0, "end": 10.0}],
            "lines": [{"id": "L1", "scene": "a", "words": [{"w": "one", "start": 0.1, "end": 0.9},
                                                           {"w": "two", "start": 4.1, "end": 4.9}]},
                      {"id": "L2", "scene": "b", "words": [{"w": "three", "start": 6.1, "end": 6.9}]}]}
    r = review(tmp_path / "mix", data, {"cues": [{"sound": "hiss", "t": 4.2}]}, png=tmp_path / "mix.png")
    a, b = r["scenes"]
    assert [w["w"] for w in a["sfx_near_voice"]] == ["two"] and b["sfx_near_voice"] == []
    assert r["flagged_words"] == 1 and r["sfx_peaks"][0]["scene"] == "a" and r["sfx_peaks"][0]["cues"] == ["hiss@4.200"]
    assert a["music_to_vo_median_lu"] < 0 and a["bed_I"] < a["I"]  # the voice over the ducked score
    assert -30 < a["I"] < 0 and (tmp_path / "mix.png").stat().st_size > 10_000


def test_the_music_duck_holds_through_a_breath(tmp_path):
    """Between two words a 0.3 s breath must not let the score swell back (pumping); after the line it comes back."""
    from gitloom_film.mix import MUSIC_DUCK, sidechain_gain
    n = 5 * SR
    t = np.arange(n) / SR
    vo = np.where(((t >= 1.0) & (t < 2.0)) | ((t >= 2.3) & (t < 3.0)), 0.2 * np.sin(2 * np.pi * 1000 * t), 0.0)
    g = 20 * np.log10(sidechain_gain(vo, n, SR, **MUSIC_DUCK))
    assert g[int(1.5 * SR)] <= -6.0
    assert g[int(2.0 * SR):int(2.3 * SR)].max() <= -5.0  # held through the breath
    assert g[int(4.5 * SR)] >= -1.0  # back up after the line
