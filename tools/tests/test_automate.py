import numpy as np
import pytest

from filmtools.automate import OPEN, apply, lanes, rules_from

SR = 8000
MUSIC = {"sections": [  # pipeline.music.sections: a muffled intro, a build that opens up, a drop and a lift
    {"name": "intro", "gain_db": -10, "cutoff_hz": 300},
    {"name": "build", "gain_db": [-10, -3], "cutoff_hz": [300, 4000]},
    {"name": "chorus", "glide": 0.005},
    {"name": "tour"},
    {"name": "drop", "gain_db": -12, "glide": 0.12},
    {"name": "lift", "glide": 0.005},
    {"name": "outro"},
]}
RULES = rules_from(MUSIC)
SECTIONS = [{"name": "intro", "start": 0.0, "end": 1.0}, {"name": "build", "start": 1.0, "end": 2.0},
            {"name": "chorus", "start": 2.0, "end": 3.0}, {"name": "tour", "start": 3.0, "end": 4.0},
            {"name": "drop", "start": 4.0, "end": 5.0}, {"name": "lift", "start": 5.0, "end": 6.0},
            {"name": "outro", "start": 6.0, "end": 9.0}]
N = 9 * SR


def test_rules_come_from_the_sections_settings():
    assert RULES["intro"] == (-10.0, -10.0, 300.0, 300.0, 0.0)
    assert RULES["build"] == (-10.0, -3.0, 300.0, 4000.0, 0.0)
    assert RULES["tour"] == (0.0, 0.0, OPEN, OPEN, 0.0)
    assert rules_from({"sections": []}) is None and rules_from({}) is None


def db(x):
    return 20 * np.log10(x)


def at(t):
    return int(t * SR)


def test_gain_lane_draws_the_arc():
    g, _ = lanes(SECTIONS, SR, N, RULES)
    assert db(g[at(0.5)]) == pytest.approx(-10, abs=0.01)
    assert db(g[at(1.5)]) == pytest.approx(-6.5, abs=0.05)  # halfway from −10 to −3
    assert db(g[at(2.5)]) == pytest.approx(0, abs=0.01)
    assert -12 < db(g[at(4.05)]) < 0  # inside the drop's 120 ms dip
    assert db(g[at(4.2)]) == pytest.approx(-12, abs=0.01)
    assert db(g[at(5.01)]) == pytest.approx(0, abs=0.01)  # slammed back within 5 ms
    assert db(g[at(6.5)]) == pytest.approx(0, abs=0.01)  # the fade is only the last 2 s
    assert g[-1] < 1e-3


def test_cutoff_lane_sweeps_open():
    _, c = lanes(SECTIONS, SR, N, RULES)
    assert c[at(0.5)] == pytest.approx(300)
    assert c[at(1.5)] == pytest.approx((300 * 4000) ** 0.5, rel=0.01)  # geometric midpoint ≈ 1095 Hz
    assert c[at(2.5)] == pytest.approx(20000)


def hi_db(seg):
    spec = np.abs(np.fft.rfft(seg)) ** 2
    return 10 * np.log10(spec[np.fft.rfftfreq(len(seg), 1 / SR) > 2000].mean() + 1e-20)


def test_filter_muffles_the_intro_and_the_drop_dips():
    y = (0.3 * np.random.default_rng(3).standard_normal(N)).astype(np.float32)
    out = apply(y, SR, *lanes(SECTIONS, SR, N, RULES))
    intro, tour = out[at(0.2):at(0.8)], out[at(3.2):at(3.8)]
    assert hi_db(intro) < hi_db(tour) - 30
    drop = out[at(4.2):at(4.9)]
    assert -13 < db(np.sqrt(np.mean(drop ** 2)) / np.sqrt(np.mean(tour ** 2))) < -11


def test_stereo_channels_stay_independent_and_dc_passes():
    y = np.stack([np.ones(N, np.float32), -np.ones(N, np.float32)], axis=1)
    out = apply(y, SR, *lanes(SECTIONS, SR, N, RULES))
    assert out.shape == (N, 2)
    assert out[at(3.5), 0] == pytest.approx(1.0, abs=1e-3) and out[at(3.5), 1] == pytest.approx(-1.0, abs=1e-3)


def test_a_section_without_a_rule_is_an_error():
    with pytest.raises(ValueError, match="'the drop'"):
        lanes([*SECTIONS[:3], {"name": "the drop", "start": 3.0, "end": 4.0}], SR, N, RULES)  # a typo plays open


def test_without_rules_only_the_fade_out_is_drawn():
    g, c = lanes([{"name": "anything", "start": 0.0, "end": 9.0}], SR, N, None, fade_out=1.0)
    assert np.all(g[:at(7.9)] == 1.0) and np.all(c == OPEN)
    assert g[at(8.5)] < 1.0 and g[-1] < 1e-3
    g, _ = lanes(SECTIONS, SR, N, RULES, fade_out=0.0)
    assert db(g[-1]) == pytest.approx(0, abs=0.01)  # no fade


def test_duck_lanes_hold_full_depth_with_fades_either_side():
    from filmtools.automate import duck_lanes
    ducks = [{"t": 1.0, "dur": 0.5, "depth": -30, "fade": 0.1, "bus": "music"},
             {"t": 3.0, "dur": 0.5, "depth": -12, "fade": 0.0, "bus": "all"}]
    g = duck_lanes(ducks, SR, N, "music")
    assert db(g[at(1.0)]) == pytest.approx(-30, abs=0.01) and db(g[at(1.499)]) == pytest.approx(-30, abs=0.01)
    assert -30 < db(g[at(0.95)]) < 0 and -30 < db(g[at(1.55)]) < 0  # inside the fades
    assert g[at(0.89)] == pytest.approx(1.0) and g[at(1.61)] == pytest.approx(1.0)
    assert g[at(3.2)] == pytest.approx(1.0)  # an 'all' duck is not on the music lane by itself
    a = duck_lanes(ducks, SR, N, "all")
    assert db(a[at(3.2)]) == pytest.approx(-12, abs=0.01) and a[at(1.2)] == pytest.approx(1.0)
    assert np.all(np.diff(g[at(0.85):at(1.0)]) <= 1e-9)  # the fade-in only goes down
    with pytest.raises(ValueError, match="'voice'"):
        duck_lanes(ducks, SR, N, "voice")
