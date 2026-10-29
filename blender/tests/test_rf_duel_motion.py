"""The Rain Ferry's duel motion (films/rain-ferry/blender/rf/duel_motion.py): easing, breath, wind, heartbeat, a
line's mouth shapes and the ferry pole's lift, without Blender."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "films" / "rain-ferry" / "blender"))

from rf import duel_motion as dm  # noqa: E402


def test_ease_and_span_are_clamped_and_monotonic():
    assert dm.ease(-1) == 0.0 and dm.ease(2) == 1.0 and dm.ease(0.5) == pytest.approx(0.5)
    xs = [dm.span(t, 1.0, 2.0) for t in np.linspace(0, 3, 31)]
    assert xs[0] == 0.0 and xs[-1] == 1.0 and all(b >= a for a, b in zip(xs, xs[1:]))
    assert dm.span(5.0, 2.0, 2.0) == 1.0 and dm.span(1.0, 2.0, 2.0) == 0.0


def test_envelope_rises_holds_and_falls():
    assert dm.envelope(0.0, 1, 2, 3, 4) == 0.0
    assert dm.envelope(2.5, 1, 2, 3, 4) == 1.0
    assert dm.envelope(4.5, 1, 2, 3, 4) == 0.0


def test_breath_is_periodic_and_inhales_faster_than_it_exhales():
    rate = 0.5
    assert dm.breath(0.3, rate) == pytest.approx(dm.breath(0.3 + 1 / rate, rate))
    ts = np.linspace(0, 1 / rate, 400, endpoint=False)
    b = np.array([dm.breath(t, rate) for t in ts])
    assert b.min() == pytest.approx(0.0, abs=1e-3) and b.max() == pytest.approx(1.0, abs=1e-3)
    peak = ts[b.argmax()] * rate
    assert peak == pytest.approx(0.4, abs=0.01)     # in over 40% of the breath, out over the rest


def test_gusts_rise_fast_and_die_slowly():
    at = [(1.0, 2.0, 1.5)]
    assert dm.gusts(0.9, at) == 0.0 and dm.gusts(3.1, at) == 0.0
    assert dm.gusts(1.5, at) == pytest.approx(1.5)
    assert dm.gusts(1.25, at) > dm.gusts(2.75, at)


def test_wind_differs_by_seed_and_carries_its_gust():
    a = [dm.wind(t, 1) for t in np.linspace(0, 4, 50)]
    b = [dm.wind(t, 2) for t in np.linspace(0, 4, 50)]
    assert not np.allclose(a, b)
    assert all(0.4 < v < 1.6 for v in a)
    assert dm.wind(1.5, 1, at=[(1.0, 2.0, 1.5)]) == pytest.approx(dm.wind(1.5, 1) + 1.5)


def test_sway_tip_lags_root():
    """A travelling wave: the tip reaches the root's swing a little later."""
    ts = np.linspace(0, 3, 600)
    root = np.array([dm.sway(t, 0.0, seed=3) for t in ts])
    tip = np.array([dm.sway(t, 1.0, seed=3) for t in ts])
    lags = range(0, 120)
    best = max(lags, key=lambda k: float(np.dot(root[: len(ts) - k], tip[k:])))
    assert best > 0


def test_heartbeat_has_lub_and_dub():
    h = [dm.heartbeat(t, [0.5]) for t in np.linspace(0, 1.5, 361)]
    assert dm.heartbeat(0.49, [0.5]) == 0.0
    lub, dub = dm.heartbeat(0.53, [0.5]), dm.heartbeat(0.81, [0.5])
    assert lub > 0.7 and dub > 0.3 and lub > dub
    assert max(h) <= 1.0 and h[-1] < 0.05


def test_syllables_fill_the_line_and_hold_the_last():
    s = dm.syllables(1.2, 3.2, ["aa", "aa", "ih", "ee"], hold_last=2.0)
    assert s[0][0] == pytest.approx(1.2) and s[-1][1] == pytest.approx(3.2)
    lengths = [e - b for b, e, _, _ in s]
    assert lengths[-1] == pytest.approx(2 * lengths[0])
    assert all(b2 == pytest.approx(e1) for (_, e1, _, _), (b2, _, _, _) in zip(s, s[1:]))


def test_mouth_opens_on_each_syllable_and_shuts_between_lines():
    s = dm.syllables(1.0, 2.0, ["aa", ("oh", 0.5)])
    assert all(v == 0.0 for v in dm.mouth(0.5, s).values())
    mid = dm.mouth(1.2, s)
    assert mid["aa"] == pytest.approx(0.7) and mid["oh"] == 0.0
    assert dm.mouth(1.85, s)["oh"] == pytest.approx(0.5)
    assert all(v == 0.0 for v in dm.mouth(2.5, s).values())
    with pytest.raises(ValueError):
        dm.mouth(1.0, [(0.0, 1.0, "xx", 1.0)])


def test_slerp_dir_stays_unit_and_ends_on_its_ends():
    a, b = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    assert np.allclose(dm.slerp_dir(a, b, 0.0), a) and np.allclose(dm.slerp_dir(a, b, 1.0), b)
    m = dm.slerp_dir(a, b, 0.5)
    assert np.linalg.norm(m) == pytest.approx(1.0)
    assert np.allclose(m, (math.sqrt(0.5), 0.0, math.sqrt(0.5)))


def test_pole_at_keeps_its_foot_below_the_grip_and_arcs():
    g0, d0 = (0.0, 0.0, 0.3), (-0.8, -0.5, 0.33)
    g1, d1 = (0.2, 0.3, 1.0), (0.0, 0.0, 1.0)
    for k in np.linspace(0, 1, 11):
        g, d, foot = dm.pole_at(k, g0, d0, g1, d1, below=0.98, lift=0.2)
        assert np.linalg.norm(g - foot) == pytest.approx(0.98)
        assert np.linalg.norm(d) == pytest.approx(1.0)
    g, _, foot = dm.pole_at(1.0, g0, d0, g1, d1, below=0.98)
    assert np.allclose(g, g1) and foot[2] == pytest.approx(1.0 - 0.98)
    mid, _, _ = dm.pole_at(0.5, g0, d0, g1, d1, below=0.98, lift=0.2)
    assert mid[2] == pytest.approx((0.3 + 1.0) / 2 + 0.2)


def test_clock_runs_at_full_speed_then_stops():
    c = dm.clock([9.5] * 24 + [4.75] * 24 + [0.0] * 24, 24.0, 9.5)
    assert c[0] == 0.0 and c[24] == pytest.approx(1.0)
    assert c[48] == pytest.approx(1.5)
    assert c[-1] == pytest.approx(1.5)        # stopped: the drops hang
