import math

import numpy as np
import pytest

from lib import cinema, weather


def test_values_are_numbers_or_eased_keys_held_outside():
    assert weather.value_at(0.7, 3.0) == 0.7
    keys = [(0, 1.0), (2.0, 0.0)]
    assert weather.value_at(keys, -1) == 1.0 and weather.value_at(keys, 5) == 0.0
    assert weather.value_at(keys, 1.0) == pytest.approx(0.5)
    assert weather.value_at([[0, 0.6], [2.6, 0.3], [4.4, 0.0]], 2.6) == pytest.approx(0.3)


def test_travel_integrates_speed_and_stops_where_it_is():
    dt = 1 / 24
    assert weather.travel([9.5] * 25, dt)[-1] == pytest.approx(9.5)
    # slowing to a stop: it keeps the distance it had and never jumps back
    v = np.r_[np.linspace(9.5, 0, 12), np.zeros(12)]
    d = weather.travel(v, dt)
    assert np.all(np.diff(d) >= 0) and d[-1] == pytest.approx(d[12])
    assert np.max(np.diff(d)) <= 9.5 * dt + 1e-9
    assert len(weather.travel([], dt)) == 0


def test_streaks_shorten_to_beads_as_rain_slows():
    assert weather.stretch(9.5) == pytest.approx(1.0) and weather.stretch(20) == pytest.approx(1.0)
    assert weather.stretch(0) == pytest.approx(weather.BEAD)
    assert weather.BEAD < weather.stretch(4) < 1


def test_a_drip_swells_falls_and_is_gone():
    dz, s = weather.drip(0.0, 1.0, 0.6, 1.5)
    assert dz == 0 and s == pytest.approx(0.4)
    dz, s = weather.drip(0.59, 1.0, 0.6, 1.5)
    assert dz == 0 and s > 0.95
    dz, s = weather.drip(0.8, 1.0, 0.6, 1.5)
    assert dz == pytest.approx(0.5 * 9.81 * 0.04) and s == 1.0
    dz, s = weather.drip(0.99, 1.0, 0.3, 0.5)
    assert s == 0.0
    assert weather.drip(1.2, 1.0, 0.6, 1.5) == pytest.approx(weather.drip(0.2, 1.0, 0.6, 1.5))


def _pose(cam, aim, lens=40.0):
    return cinema.Shot([cinema.Setup("a", 0.0, cinema.hold(cam, aim), lens=lens)], 1.0).pose(0.0)


def test_frustum_box_holds_what_the_lens_sees():
    p = _pose((0, -10, 1.5), (0, 0, 1.5), 40.0)
    lo, hi = weather.frustum_box([p], 2.0, 20.0, margin=0.0)
    hh = 20 * cinema.GATE_H / 40 / 2
    assert lo[1] == pytest.approx(-8.0) and hi[1] == pytest.approx(10.0)
    assert hi[2] == pytest.approx(1.5 + hh) and lo[2] == pytest.approx(1.5 - hh)
    assert hi[0] == pytest.approx(hh * 16 / 9)
    # every point the camera sees between the distances is inside it
    for u, v, d in ((0.5, 0.5, 5.0), (0.0, 1.0, 19.0), (1.0, 0.0, 2.5)):
        h = d * cinema.GATE_H / 40
        q = p.position + p.forward * d + p.rotation[:, 0] * (u - 0.5) * h * 16 / 9 + p.rotation[:, 1] * (v - 0.5) * h
        assert np.all(q >= lo - 1e-9) and np.all(q <= hi + 1e-9)
    lo2, _ = weather.frustum_box([p], 2.0, 20.0, floor=0.0)
    assert lo2[2] == 0.0


def test_frustum_box_spans_a_moving_camera():
    a, b = _pose((0, -10, 1), (0, 0, 1)), _pose((8, -10, 1), (8, 0, 1))
    lo, hi = weather.frustum_box([a, b], 1.0, 5.0, margin=0.0)
    assert lo[0] < 0 and hi[0] > 8


def test_edges_and_rings_of_drip_points():
    e = weather.edge((0, 0, 2), (4, 0, 2), 5)
    assert e.shape == (5, 3) and e[2] == pytest.approx((2, 0, 2))
    r = weather.ring((1, 1, 1.7), 0.3, 12, z=-0.05)
    assert r.shape == (12, 3) and np.allclose(np.hypot(r[:, 0] - 1, r[:, 1] - 1), 0.3) and np.allclose(r[:, 2], 1.65)


def test_layers_run_near_to_far_without_gaps():
    ls = list(weather.LAYERS.values())
    assert all(a.far == b.near for a, b in zip(ls, ls[1:]))
    assert ls[0].length >= ls[1].length and ls[-1].alpha < ls[1].alpha
