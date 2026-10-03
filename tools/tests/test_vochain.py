import numpy as np

from gitloom_film.vochain import CHAIN, chain, compress, deess, loudness, onset_shift, plate, report, saturate

SR = 48000


def sine(f, dur=2.0, amp=0.3):
    t = np.arange(int(dur * SR)) / SR
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def tone_bursts(starts, dur=3.0, length=0.4, f=220.0, amp=0.3):
    """220 Hz bursts that start on a step (cosine phase), so the first sample of each burst is already loud."""
    y = np.zeros(int(dur * SR), dtype=np.float32)
    for s in starts:
        i = round(s * SR)
        t = np.arange(int(length * SR)) / SR
        y[i:i + len(t)] = amp * np.cos(2 * np.pi * f * t)
    return y


def first_above(x, s, rel=0.25, win=0.2):
    """The first sample at or after `s - 10 ms` whose magnitude passes `rel` of the window's peak."""
    i0, i1 = round((s - 0.01) * SR), round((s + win) * SR)
    seg = np.abs(x[i0:i1])
    return i0 + int(np.argmax(seg > rel * seg.max()))


def band_db(x, lo=20.0, hi=60.0):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return 10 * np.log10(spec[(f >= lo) & (f <= hi)].sum() + 1e-30)


def sib_ratio(x):
    return band_db(x, 5000, 9000) - band_db(x, 1000, 4000)


def noise_band(lo, hi, dur=2.0, seed=3):
    n = np.random.default_rng(seed).standard_normal(int(dur * SR))
    spec = np.fft.rfft(n)
    f = np.fft.rfftfreq(len(n), 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, len(n))
    return (x / np.abs(x).max()).astype(np.float32)


def bursts(x, amp, on=0.12, period=0.4):
    t = np.arange(len(x)) / SR
    return (amp * x * ((t % period) < on)).astype(np.float32)


def test_the_chain_keeps_every_onset_on_its_sample():
    y = tone_bursts(starts=[0.5, 1.25, 2.0])
    out = chain(y, SR)
    for s in [0.5, 1.25, 2.0]:
        assert abs(first_above(out, s) - first_above(y, s)) <= 1


def test_hpf_removes_rumble_and_keeps_the_voice():
    # rumble under a voice: the makeup restores the whole signal's loudness, so a lone 40 Hz tone would come back
    # up to where it was; under a 1 kHz "voice" the rumble has to stay down
    y = sine(40) + sine(1000)
    out = chain(y, SR)
    assert band_db(out) - band_db(y) <= -12
    assert abs(band_db(out, 900, 1100) - band_db(y, 900, 1100)) <= 3


def test_the_de_esser_tames_sibilance_only():
    # voiced tone + /s/ bursts, with a faint 1–4 kHz bed so the ratio has a denominator
    y = (sine(250, amp=0.3) + bursts(noise_band(5000, 9000), 0.4) + 1e-3 * noise_band(1000, 4000, seed=9))
    out = deess(y, SR, **CHAIN["deess"])
    assert sib_ratio(out) <= sib_ratio(y) - 4
    assert abs(band_db(out, 200, 300) - band_db(y, 200, 300)) <= 0.5


def test_the_onset_check_sees_a_two_sample_slip():
    rng = np.random.default_rng(7)
    y = np.zeros(SR, dtype=np.float32)
    y[SR // 2:] = 0.3 * rng.standard_normal(SR // 2)
    assert onset_shift(y, y, SR, 0.5) == 0
    assert onset_shift(y, np.concatenate([np.zeros(2), y[:-2]]), SR, 0.5) == 2


def test_2_to_1_compression_halves_level_above_threshold():
    c = CHAIN["comp"]
    amp = 10 ** ((c["thresh_db"] + 10) / 20)  # peak 10 dB over the threshold
    out = compress(sine(1000, dur=2.0, amp=amp), SR, **c)
    over = 20 * np.log10(np.abs(out[SR:]).max()) - c["thresh_db"]
    assert abs(over - 5.0) <= 1.0


def test_compression_leaves_quiet_signal_alone():
    c = CHAIN["comp"]
    y = sine(1000, amp=10 ** ((c["thresh_db"] - 12) / 20))
    assert np.allclose(compress(y, SR, **c), y, atol=1e-6)


def test_the_plate_adds_a_short_tail_and_stays_low():
    y = np.zeros(SR, dtype=np.float32)
    y[0] = 1.0
    out = plate(y, SR, **CHAIN["plate"])
    assert out[0] == y[0]  # the dry path is untouched and the send starts at sample 0 at the earliest
    tail = 10 * np.log10(np.sum(out[int(0.05 * SR):int(0.4 * SR)] ** 2))
    assert -60 < tail <= -18
    late = 10 * np.log10(np.sum(out[int(0.8 * SR):] ** 2) + 1e-30)
    assert late < -60  # a very short plate


def test_saturation_never_clips_and_is_light():
    s = CHAIN["sat"]
    assert np.abs(saturate(sine(100, amp=1.0), **s)).max() <= 1.0
    x = sine(1000, dur=1.0, amp=0.5)
    out = saturate(x, **s)
    spec = np.abs(np.fft.rfft(out * np.hanning(len(out))))
    f = np.fft.rfftfreq(len(out), 1 / SR)
    fund = spec[np.abs(f - 1000) < 5].max()
    harm = np.sqrt(sum(spec[np.abs(f - k * 1000) < 5].max() ** 2 for k in range(2, 10)))
    assert harm / fund < 0.03


def test_chain_is_deterministic_and_keeps_loudness():
    y = sine(220, dur=3.0, amp=0.2) + bursts(noise_band(5000, 9000, dur=3.0), 0.05)
    a, b = chain(y, SR), chain(y, SR)
    assert np.array_equal(a, b)
    assert len(a) == len(y)
    assert abs(loudness(a, SR) - loudness(y, SR)) <= 1.0


def test_loudness_matches_bs1770_for_a_1k_sine():
    # a 0 dBFS-peak 997 Hz sine in one channel reads −3.01 LUFS (BS.1770-4)
    assert abs(loudness(sine(997, dur=5.0, amp=1.0), SR) - (-3.01)) <= 0.1


def test_report_checks_onsets_sibilance_and_the_gap_floor():
    rng = np.random.default_rng(4)
    y = (1e-3 * rng.standard_normal(4 * SR)).astype(np.float32)
    voice = tone_bursts([0.5, 2.5], dur=4.0, length=0.8) + bursts(noise_band(5000, 9000, dur=4.0), 0.2)
    voice *= (np.abs(tone_bursts([0.5, 2.5], dur=4.0, length=0.8)) > 0)
    y = y + voice
    vo = {"lines": [{"id": "L01", "start": 0.5, "end": 1.3, "words": [{"w": "a", "start": 0.5, "end": 1.3}]},
                    {"id": "L02", "start": 2.5, "end": 3.3, "words": [{"w": "b", "start": 2.5, "end": 3.3}]}]}
    r = report(y, chain(y, SR), SR, vo)
    assert [ln["id"] for ln in r["lines"]] == ["L01", "L02"]
    for ln in r["lines"]:
        assert ln["onset_shift"] is not None and abs(ln["onset_shift"]) <= 1
        assert ln["clipped"] == 0
        assert set(ln) >= {"lufs_in", "lufs_out", "true_peak", "sib_in", "sib_out", "crest_in", "crest_out"}
    assert "gap_floor_in" in r and "gap_floor_out" in r
    assert r["ok"]["onsets"]
