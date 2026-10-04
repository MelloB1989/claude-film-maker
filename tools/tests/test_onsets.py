import numpy as np
import pytest

from gitloom_film.onsets import ZCR_MAX, frames, voice_onsets

SR = 48000


def tone(sec, f=150.0, amp=0.3):
    t = np.arange(int(round(sec * SR))) / SR
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def quiet(sec):
    return np.zeros(int(round(sec * SR)), np.float32)


def breath(sec, amp=0.06, seed=0):
    """Breath-like noise: broadband between 1.5 and 5 kHz, well above the voiced zero-crossing rate."""
    n = int(round(sec * SR))
    spec = np.fft.rfft(np.random.default_rng(seed).standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec[(f < 1500) | (f > 5000)] = 0
    x = np.fft.irfft(spec, n)
    return (amp * x / np.sqrt(np.mean(x ** 2))).astype(np.float32)


REF = 0.3 / np.sqrt(2)  # the tone's RMS: the take's loudest 5 ms frame, 0 dB


def noise(sec, db, lo=None, hi=None, seed=0):
    """Gaussian noise at `db` relative to the tone's RMS, band-limited to lo..hi Hz if given."""
    n = int(round(sec * SR))
    x = np.random.default_rng(seed).standard_normal(n)
    if lo or hi:
        spec = np.fft.rfft(x)
        f = np.fft.rfftfreq(n, 1 / SR)
        spec[(f < (lo or 0)) | (f > (hi or SR))] = 0
        x = np.fft.irfft(spec, n)
    return (REF * 10 ** (db / 20) * x / np.sqrt(np.mean(x ** 2))).astype(np.float32)


def test_a_voiced_tone_gives_its_onset_within_5_ms():
    x = np.concatenate([quiet(0.5023), tone(0.6)])  # the tone starts off the 5 ms frame grid
    [on] = voice_onsets(x, SR, [{"w": "I", "start": 0.62, "end": 0.9}])  # aligned 118 ms late, as "I" is
    assert on == pytest.approx(0.5023, abs=0.005)


def test_a_voice_that_swells_in_starts_where_it_reaches_minus_35_db():
    swell = tone(0.2) * (10 ** (np.linspace(-40, 0, int(0.2 * SR)) / 20)).astype(np.float32)  # -40 to 0 dB in 200 ms
    x = np.concatenate([quiet(0.5), swell, tone(0.5)])  # reaches -35 dB at 0.525 and -30 dB at 0.55
    [on] = voice_onsets(x, SR, [{"w": "Or", "start": 0.60, "end": 0.9}])
    assert on == pytest.approx(0.525, abs=0.005)  # the voiced run begins at -30 dB; the word, where it is heard


def test_a_voice_that_never_reaches_minus_30_db_is_no_onset():
    x = np.concatenate([tone(0.2), quiet(0.4), tone(0.3, amp=0.3 * 10 ** (-33 / 20))])  # a hum at -33 dB from 0.60
    words = [{"w": "a", "start": 0.0, "end": 0.2}, {"w": "b", "start": 0.62, "end": 0.9}]
    assert voice_onsets(x, SR, words)[1] is None


def test_a_breath_before_the_tone_is_ignored():
    b = breath(0.12)
    db, zcr, _ = frames(np.concatenate([quiet(0.1), b, quiet(0.1)]), SR)
    assert db.max() > -1 and np.median(zcr[db > -30]) > ZCR_MAX  # loud enough to pass the level test, breath-like
    x = np.concatenate([quiet(0.47), b[:int(0.09 * SR)], quiet(0.04), tone(0.5)])  # breath 0.47-0.56, voice at 0.60
    [on] = voice_onsets(x, SR, [{"w": "One", "start": 0.66, "end": 0.9}])  # the window opens at 0.46
    assert on == pytest.approx(0.60, abs=0.005)


def test_a_click_before_the_voice_is_not_an_onset():
    x = np.concatenate([quiet(0.50), tone(0.01), quiet(0.09), tone(0.5)])  # a 10 ms voiced pop, then the voice at 0.60
    [on] = voice_onsets(x, SR, [{"w": "One", "start": 0.66, "end": 0.9}])
    assert on == pytest.approx(0.60, abs=0.005)


def test_a_plosive_burst_counts_as_the_start():
    burst = breath(0.008, amp=0.25, seed=1)  # 8 ms of broadband release, then voicing
    x = np.concatenate([quiet(0.3), burst, tone(0.5)])
    [on] = voice_onsets(x, SR, [{"w": "GitLoom.", "start": 0.40, "end": 0.9}])
    assert on == pytest.approx(0.30, abs=0.005)


def test_silence_gives_none():
    assert voice_onsets(quiet(1.0), SR, [{"w": "a", "start": 0.3, "end": 0.5}]) == [None]
    rng = np.random.default_rng(2)
    room = (1e-4 * rng.standard_normal(SR)).astype(np.float32)  # room tone alone: it is its own peak, but never voiced
    assert voice_onsets(room, SR, [{"w": "a", "start": 0.3, "end": 0.5}]) == [None]


def test_a_word_inside_connected_speech_gives_none():
    x = np.concatenate([quiet(0.2), tone(0.4), quiet(0.03), tone(0.4)])
    words = [{"w": "a", "start": 0.2, "end": 0.6}, {"w": "b", "start": 0.64, "end": 1.0}]  # 40 ms after "a" ends
    on = voice_onsets(x, SR, words)
    assert on[0] == pytest.approx(0.2, abs=0.005) and on[1] is None


def test_a_word_after_a_pause_is_measured():
    x = np.concatenate([quiet(0.2), tone(0.4), quiet(0.3), tone(0.4)])  # second voice at 0.90
    words = [{"w": "a", "start": 0.2, "end": 0.6}, {"w": "b", "start": 1.0, "end": 1.3}]
    assert voice_onsets(x, SR, words)[1] == pytest.approx(0.90, abs=0.005)


def test_the_previous_words_tail_is_not_an_onset():
    # The aligner ends "Rules" at 0.50 but its voice runs on to 0.55; "I" starts at 0.61 and is aligned at 0.70. The
    # tail sits inside the search window, yet it is sound that began before the window, so it is not "I".
    x = np.concatenate([quiet(0.1), tone(0.45), quiet(0.06), tone(0.4)])
    words = [{"w": "Rules", "start": 0.1, "end": 0.50}, {"w": "I", "start": 0.70, "end": 0.9}]
    assert voice_onsets(x, SR, words)[1] == pytest.approx(0.61, abs=0.005)


def test_the_search_stops_at_the_words_own_end():
    # "why I believe": "I" is spoken inside the voice of "why"; the next sound is "believe", which starts within
    # 80 ms of "I"'s aligned start but after its end. It must not be taken for "I".
    x = np.concatenate([quiet(0.1), tone(0.74), quiet(0.01), tone(0.4)])  # "why I" 0.10-0.84, "believe" 0.85
    words = [{"w": "why", "start": 0.1, "end": 0.68}, {"w": "I", "start": 0.77, "end": 0.83},
             {"w": "believe", "start": 0.86, "end": 1.2}]
    on = voice_onsets(x, SR, words)
    assert on[1] is None


def test_a_fricative_running_into_the_vowel_starts_the_word():
    x = np.concatenate([quiet(0.4), noise(0.12, -12, 4000, 8000), tone(0.5)])  # /s/ 0.40-0.52, voice from 0.52
    [on] = voice_onsets(x, SR, [{"w": "Skills,", "start": 0.55, "end": 0.9}])
    assert on == pytest.approx(0.40, abs=0.005)


def test_a_plosive_burst_and_its_aspiration_start_the_word():
    x = np.concatenate([quiet(0.4), noise(0.005, -10, seed=1), noise(0.02, -20, 1000, 8000, seed=2), tone(0.5)])
    [on] = voice_onsets(x, SR, [{"w": "tells", "start": 0.45, "end": 0.9}])  # click 0.400, aspiration, voice 0.425
    assert on == pytest.approx(0.40, abs=0.005)


def test_a_breath_separated_from_the_voice_is_excluded():
    x = np.concatenate([quiet(0.42), noise(0.15, -24, seed=3), quiet(0.04), tone(0.5)])  # breath 0.42-0.57, voice 0.61
    [on] = voice_onsets(x, SR, [{"w": "One", "start": 0.62, "end": 0.9}])  # the window opens at 0.42
    assert on == pytest.approx(0.61, abs=0.005)  # the voice after the gap starts voiced: no release, so no closure


def test_an_s_before_a_stop_closure_starts_the_word():
    # "Skills": /s/, a -47 dB closure, the /k/ burst and its aspiration, then the vowel
    x = np.concatenate([quiet(0.3), noise(0.1, -15, 4000, 8000, seed=4), noise(0.06, -47, seed=5),
                        noise(0.01, -12, seed=6), noise(0.02, -20, 1000, 8000, seed=7), tone(0.5)])
    [on] = voice_onsets(x, SR, [{"w": "Skills,", "start": 0.42, "end": 0.9}])  # /s/ 0.30-0.40, burst 0.46, voice 0.49
    assert on == pytest.approx(0.30, abs=0.005)


def test_the_previous_words_final_fricative_is_not_bridged():
    # "…Facts, keep": the previous word's /s/ runs on past its aligned end (0.48) into the window, then a closure and
    # a released /k/. That /s/ began before the window, so it is not this word's.
    x = np.concatenate([quiet(0.1), tone(0.3), noise(0.15, -15, 4000, 8000, seed=8), noise(0.05, -47, seed=9),
                        noise(0.01, -12, seed=10), noise(0.02, -20, 1000, 8000, seed=11), tone(0.5)])
    words = [{"w": "Facts,", "start": 0.1, "end": 0.48}, {"w": "keep", "start": 0.66, "end": 0.95}]
    assert voice_onsets(x, SR, words)[1] == pytest.approx(0.60, abs=0.005)  # the burst, not the fricative at 0.48


def test_an_s_that_follows_the_previous_words_voice_starts_the_word():
    # "vector store": no silence between "vector" and the /s/, but the /s/ begins inside the window, where the
    # previous word's voicing stops; then a 20 ms closure, the /t/ burst and the vowel
    x = np.concatenate([quiet(0.1), tone(0.35), noise(0.12, -15, 4000, 8000, seed=12), noise(0.02, -47, seed=13),
                        noise(0.01, -12, seed=14), noise(0.02, -20, 1000, 8000, seed=15), tone(0.5)])
    words = [{"w": "vector", "start": 0.1, "end": 0.43}, {"w": "store.", "start": 0.576, "end": 0.9}]
    assert voice_onsets(x, SR, words)[1] == pytest.approx(0.45, abs=0.005)


def test_the_walk_back_does_not_run_into_the_previous_words_voice():
    # "You already": the voice dips to -32 dB between the words (below -30, above -35) and never stops
    x = np.concatenate([quiet(0.1), tone(0.16), tone(0.04, amp=0.3 * 10 ** (-32 / 20)), tone(0.5)])
    words = [{"w": "You", "start": 0.1, "end": 0.25}, {"w": "already", "start": 0.36, "end": 0.7}]
    assert voice_onsets(x, SR, words)[1] == pytest.approx(0.30, abs=0.005)  # not the window's start, 0.25


def test_a_short_dip_inside_a_consonant_is_crossed():
    x = np.concatenate([quiet(0.4), noise(0.005, -8, seed=16), quiet(0.01), noise(0.02, -20, 1000, 8000, seed=17),
                        tone(0.5)])  # burst 0.400, a 10 ms dip, aspiration 0.415, voice 0.435
    [on] = voice_onsets(x, SR, [{"w": "to", "start": 0.46, "end": 0.9}])
    assert on == pytest.approx(0.40, abs=0.005)


def test_only_a_real_fricative_is_joined_across_a_closure():
    after = [noise(0.05, -47, seed=18), noise(0.01, -12, seed=19), noise(0.02, -20, 1000, 8000, seed=20), tone(0.5)]
    pop = np.concatenate([quiet(0.3), tone(0.025), *after])  # a voiced 25 ms pop: loud but not a fricative
    hiss = np.concatenate([quiet(0.3), noise(0.1, -31, 4000, 8000, seed=21), *after])  # a hiss under -25 dB
    for x, start in ((pop, 0.325), (hiss, 0.4)):  # the burst after the closure is at x's closure end
        [on] = voice_onsets(x, SR, [{"w": "keep", "start": start + 0.1, "end": 0.95}])
        assert on == pytest.approx(start + 0.05, abs=0.005)


def test_only_one_stop_closure_is_crossed():
    s = lambda seed: noise(0.08, -15, 4000, 8000, seed=seed)  # noqa: E731
    gap = lambda seed: noise(0.04, -47, seed=seed)  # noqa: E731
    x = np.concatenate([quiet(0.2), s(22), gap(23), s(24), gap(25), noise(0.01, -12, seed=26), tone(0.5)])
    # /s/ 0.20, closure, /s/ 0.32, closure, burst 0.44, voice 0.45: the walk stops at the first closure it has crossed
    [on] = voice_onsets(x, SR, [{"w": "sts", "start": 0.40, "end": 0.9}])
    assert on == pytest.approx(0.32, abs=0.005)
