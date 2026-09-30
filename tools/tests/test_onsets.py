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


def test_a_voiced_tone_gives_its_onset_within_5_ms():
    x = np.concatenate([quiet(0.5023), tone(0.6)])  # the tone starts off the 5 ms frame grid
    [on] = voice_onsets(x, SR, [{"w": "I", "start": 0.62, "end": 0.9}])  # aligned 118 ms late, as "I" is
    assert on == pytest.approx(0.5023, abs=0.005)


def test_a_voice_that_swells_in_is_timed_where_it_reaches_minus_30_db():
    swell = tone(0.2) * (10 ** (np.linspace(-40, 0, int(0.2 * SR)) / 20)).astype(np.float32)  # -40 to 0 dB in 200 ms
    x = np.concatenate([quiet(0.5), swell, tone(0.5)])  # reaches -35 dB at 0.525 and -30 dB at 0.55
    [on] = voice_onsets(x, SR, [{"w": "Or", "start": 0.60, "end": 0.9}])
    assert on == pytest.approx(0.55, abs=0.005)


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


def test_a_breath_running_straight_into_the_voice_is_ignored_too():
    x = np.concatenate([quiet(0.45), breath(0.15), tone(0.5)])  # breath 0.45-0.60 with no gap before the voice
    [on] = voice_onsets(x, SR, [{"w": "One", "start": 0.64, "end": 0.9}])  # the window opens at 0.44
    # a 30 ms run may start with up to 10 ms of noise (a plosive burst counts), never with the breath itself
    assert 0.59 - 1e-9 <= on <= 0.605


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
