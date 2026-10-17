"""Audio-sync audit: the transient and word-onset helpers on synthetic sound with known times."""
import numpy as np
import pytest

from filmtools.amv import audit_audio as A

SR = 48000
FPS = 30


def bed(seconds, level=3e-4, seed=0):
    return np.random.default_rng(seed).normal(0, level, int(seconds * SR))


def tone(t, f0=140.0, harmonics=5):
    return sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, harmonics + 1))


def add_burst(x, t0, length=0.2, attack=0.004, amp=0.2, seed=1):
    """Noise burst with a linear attack starting exactly at t0 s."""
    i0, n = int(round(t0 * SR)), int(length * SR)
    tt = np.arange(n) / SR
    x[i0:i0 + n] += np.random.default_rng(seed).normal(0, amp, n) * np.minimum(1.0, tt / attack) * np.exp(-tt / 0.08)


def add_word(x, t0, length=0.25, attack=0.01, amp=0.1, f0=140.0):
    i0, n = int(round(t0 * SR)), int(length * SR)
    tt = np.arange(n) / SR
    x[i0:i0 + n] += tone(tt, f0) * amp * np.minimum(1.0, tt / attack)


def test_transients_find_hits_within_a_few_ms():
    x = bed(2.0) + 0.05 * np.sin(2 * np.pi * 60 * np.arange(int(2.0 * SR)) / SR)  # a steady bass bed
    for t in (0.5, 1.0, 1.4):
        add_burst(x, t)
    found = A.transients(x, SR, 10.0)
    assert len(found) == 3
    for (got, _), want in zip(found, (0.5, 1.0, 1.4)):
        assert abs(got - want) < 0.008


def test_steady_sound_has_no_transients_and_the_start_of_the_file_is_not_one():
    t = np.arange(int(1.5 * SR)) / SR
    x = 0.1 * tone(t, 110.0) + bed(1.5)  # loud from sample 0
    assert A.transients(x, SR, 8.0) == []  # a score of ~3 is what a noise-only band does by itself


def test_a_hit_inside_loud_music_is_a_smaller_rise():
    t = np.arange(int(2.0 * SR)) / SR
    quiet, loud = bed(2.0), 0.2 * tone(t, 90.0) + bed(2.0, 3e-2)
    add_burst(quiet, 1.0)
    add_burst(loud, 1.0)
    (_, s_quiet), (_, s_loud) = A.transients(quiet, SR, 10.0)[0], max(A.transients(loud, SR, 1.0), key=lambda h: h[1])
    assert s_quiet > s_loud > 1.0


def test_min_gap_keeps_one_peak_per_hit():
    x = bed(1.0)
    add_burst(x, 0.5, length=0.3)
    assert len(A.transients(x, SR, 10.0, min_gap=0.1)) == 1


def test_rise_curve_ignores_digital_silence_floor():
    x = np.zeros(SR)  # nothing at all
    t, db = A.band_db(x, SR)
    assert np.allclose(A.rise_curve(db), 0.0)


def test_word_onsets_after_a_pause_and_inside_speech():
    x = bed(1.5)
    add_word(x, 0.30)
    add_word(x, 0.90, f0=180.0)
    on = A.word_onsets(x, SR, [0.34, 0.86])  # aligned times off by +-40 ms
    assert abs(on[0]["t"] - 0.30) < 0.01 and on[0]["edge"] and on[0]["conf"] > 4
    assert abs(on[1]["t"] - 0.90) < 0.01


def test_word_onsets_skip_the_fade_in_of_the_stem():
    x = bed(1.0)
    x[:int(0.01 * SR)] += np.linspace(0, 1, int(0.01 * SR)) * 0.02  # a bed that fades in over the first 10 ms
    add_word(x, 0.20)
    assert abs(A.word_onsets(x, SR, [0.18])[0]["t"] - 0.20) < 0.01


def test_word_onsets_do_not_take_the_previous_words_tail():
    x = bed(1.0)
    add_word(x, 0.10, length=0.20)
    add_word(x, 0.40, length=0.20)
    first, second = A.word_onsets(x, SR, [0.10, 0.24])  # the second ref is early: 'am' after 'Who'
    assert abs(first["t"] - 0.10) < 0.01
    assert second["t"] >= first["t"] + 0.07


def test_locate_finds_a_stem_in_a_mix_to_the_sample():
    rng = np.random.default_rng(3)
    stem = rng.normal(0, 0.1, SR // 2)
    mix = rng.normal(0, 0.05, SR * 2)
    k0 = int(0.7333 * SR)
    mix[k0:k0 + len(stem)] += 0.5 * stem
    k, r = A.locate(mix, stem)
    assert k == k0 and r > 0.7


def test_frame_of():
    assert A.frame_of(8 / 30, 30) == 8
    assert A.frame_of(8 / 30 - 1e-4, 30) == 7
    assert A.frame_of(0.0, 30) == 0


@pytest.mark.parametrize("delta, weak, want", [
    (0, False, "ok"), (2, False, "ok"), (3, False, "FAIL"), (-1, False, "FAIL"),
    (3, True, "ok~"), (-1, True, "ok~"), (4, True, "FAIL"), (-2, True, "FAIL"), (1, True, "ok"),
])
def test_judge(delta, weak, want):
    assert A.judge(delta, weak) == want


def test_group_words_merges_hyphenated_name():
    line = ["Who", "am", "I?", "I'm", "Spider-", "Man."]
    assert A.group_words(["WHO", "AM", "I?", "I'M", "SPIDER-MAN."], line) == [[0], [1], [2], [3], [4, 5]]
    with pytest.raises(ValueError):
        A.group_words(["WHO", "ARE"], line)


def test_even_runs_finds_the_click_train_and_not_the_rest():
    train = [100 + 3.57 * i for i in range(8)]
    other = [103.1, 107.7, 119.0, 125.2, 131.9, 140.3]
    runs = A.even_runs(sorted(train + other))
    assert len(runs) == 1 and len(runs[0]) == 8
    assert np.allclose(runs[0], train)
    assert A.even_runs([10, 17, 29, 41, 58, 60]) == []


def test_hard_cuts_tell_a_stop_from_a_decay():
    t = np.arange(SR) / SR
    stop = 0.05 * tone(t, 200.0)
    stop[int(0.6 * SR):] = 0.0
    decay = 0.05 * tone(t, 200.0) * np.exp(-np.maximum(0, t - 0.6) / 0.03)
    cuts = A.hard_cuts(stop, SR, FPS)
    assert len(cuts) == 1 and abs(cuts[0]["t"] - 0.6) < 0.003 and abs(cuts[0]["frame"] - 18.0) < 0.1
    assert A.hard_cuts(decay, SR, FPS) == []
    assert A.hard_cuts(0.0005 * tone(t, 200.0) * (t < 0.6), SR, FPS) == []  # below -60 dBFS: not a cut


def test_check_outro_reports_the_silent_tail():
    raw = {"fps": 30, "dur": 90, "sfx": [{"name": "shutter_flash", "f": 70, "db": -14}]}
    x = 0.05 * tone(np.arange(3 * SR) / SR, 150.0)
    x[int(2.9 * SR):] = 0.0  # 3 frames of silence, hard stop
    o = A.check_outro(raw, x, SR)
    assert o["last_audible_f"] == pytest.approx(87.0, abs=0.01) and o["silent_tail_frames"] == pytest.approx(3.0, abs=0.01)
    assert o["first_audible_f"] == pytest.approx(0.0, abs=0.01)
    assert len(o["hard_cuts"]) == 1 and o["sfx_flash"] == [70]
    assert o["tail_rms_db_last6"][-1] < -100


def test_visual_events_and_shift():
    raw = {"shots": [{"name": "A", "a": 0}, {"name": "B", "a": 36}], "black": [647], "invert": [605], "halftone": [483],
           "flash_ev": [[135, 0.0], [136, 1.2], [137, 0.66], [138, 0.363], [140, 0.0],
                        [477, 0.0], [478, -0.15], [485, -1.3], [486, 1.2], [487, 0.6], [489, 0.0]],
           "titles": [{"style": "sub", "f_in": 8, "spec": {}}, {"style": "gold", "f_in": 624, "spec": {"text": "T"}}],
           "outro": {"f": 812, "n": 88}}
    ev = {(e["kind"], e["f"]) for e in A.visual_events(raw)}
    assert ev == {("cut", 36), ("flash", 136), ("flash", 486), ("black", 647), ("invert", 605), ("halftone", 483),
                  ("title", 624), ("outro", 812)}  # the dim ramp before 486 is not a flash, a sub is not a pop
    assert A.shift_for(1.65) == -2 and A.shift_for(-2.14) == 2 and A.shift_for(0.4) == 0


def test_pick_hit_takes_the_nearest_of_the_strong_ones():
    assert A.pick_hit([(571.95, 3.8), (573.24, 3.2), (575.0, 1.0)], 573) == (573.24, 3.2)
    assert A.pick_hit([(571.0, 8.0), (573.2, 3.0)], 573) == (571.0, 8.0)  # the weak one is under 60 %
    assert A.pick_hit([], 5) is None
