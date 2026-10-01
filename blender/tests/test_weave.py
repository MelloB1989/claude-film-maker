# The loom's weave (blender/lib/weave.py): the lanes, plain weave's over/under, the shed, and the clock that puts a pick
# on every beat.
import math

import numpy as np
import pytest

from lib import weave


def test_lanes_sit_side_by_side_centred_with_a_gap_between():
    lanes = weave.layout(("a", "b", "c"), (3, 2, 4), 2.0, 5.0)
    assert [l.count for l in lanes] == [3, 2, 4]
    assert [l.first for l in lanes] == [0, 3, 5]
    assert lanes[0].x0 == pytest.approx(-lanes[-1].x1)  # centred
    assert np.allclose(np.diff(lanes[0].xs), 2.0)
    assert lanes[1].x0 - lanes[0].x1 == pytest.approx(2.0 + 5.0)  # a pitch and the gap
    assert list(lanes[2].warps()) == [5, 6, 7, 8]
    with pytest.raises(ValueError):
        weave.layout(("a",), (1, 2), 1.0, 1.0)


def test_plain_weave_puts_the_warp_over_where_j_plus_r_is_even_and_the_weft_under_it_there():
    a_w, a_f = 0.9, 0.7
    for r in range(4):
        for j in range(4):
            zw = float(weave.warp_crimp(r, j, a_w))
            zf = float(weave.weft_crimp(j, r, a_f))
            assert np.sign(zw) == (1 if (j + r) % 2 == 0 else -1)
            assert np.sign(zf) == -np.sign(zw)  # they cross: always on opposite sides
            assert zw - zf == pytest.approx(np.sign(zw) * (a_w + a_f))  # touching at the crossing: centres a_w + a_f apart
    # half way between rows the warp crosses the cloth's plane
    assert float(weave.warp_crimp(0.5, 0, a_w)) == pytest.approx(0.0, abs=1e-12)


def test_the_shed_opens_from_the_fell_to_the_heddles_and_closes_to_the_back_beam():
    y = np.array([-5.0, 0.0, 20.0, 60.0, 100.0, 140.0])
    s = weave.shed_profile(y, 20.0, 100.0)
    assert s.tolist() == pytest.approx([0.0, 0.0, 1.0, 0.5, 0.0, 0.0])
    fine = np.linspace(0.0, 100.0, 2001)
    slope = np.diff(weave.shed_profile(fine, 20.0, 100.0))
    assert np.max(np.abs(np.diff(slope))) < 1e-3  # no kink at the heddles: it rises to them and eases away


BEATS = [1.0 + 0.6 * k for k in range(6)]
CLOCK = weave.WeaveClock(BEATS, 0.4)


def test_a_pass_lands_on_every_beat_and_the_passes_alternate():
    ps = CLOCK.passes
    assert [p.land for p in ps] == BEATS
    assert [p.start for p in ps] == [-1, 1, -1, 1, -1, 1]
    assert [p.row for p in ps] == [1, 2, 3, 4, 5, 6]
    for p, before in zip(ps, [0.4] + BEATS):
        assert p.depart == pytest.approx(before + CLOCK.open)
        assert CLOCK.flight(p.depart, p) == 0 and CLOCK.flight(p.land, p) == 1
    with pytest.raises(ValueError):
        weave.WeaveClock([1.0, 0.9], 0.4)  # not in order


def test_the_cloth_is_taken_up_one_pick_per_beat_continuously():
    assert CLOCK.taken(0.5) == 0
    for k, b in enumerate(BEATS):
        assert CLOCK.taken(b - CLOCK.lead - 1e-6) == pytest.approx(k, abs=1e-6)  # still k just before the stroke
        assert CLOCK.taken(b + CLOCK.settle + 1e-6) == pytest.approx(k + 1)  # one more once it is in
    ts = np.linspace(0.4, BEATS[-1] + 0.3, 2000)
    n = np.array([CLOCK.taken(t) for t in ts])
    assert np.all(np.diff(n) >= -1e-12) and np.max(np.diff(n)) < 0.05  # monotonic, no jumps


def test_the_shed_is_open_for_the_row_in_flight_and_changes_over_round_each_beat():
    for p in CLOCK.passes:
        mid = 0.5 * (p.depart + p.land)
        for j in range(5):
            up = 1.0 if (j + p.row) % 2 == 0 else -1.0  # the warps that go over this row once it is beaten in
            assert CLOCK.shed(mid, j) == pytest.approx(up)
            assert CLOCK.shed(p.depart, j) == pytest.approx(up)  # fully open when it departs
            # it closes (the warps cross) `cross` after its landing, and the next row's shed opens the other way
            assert CLOCK.shed(p.land + CLOCK.cross, j) == pytest.approx(0.0, abs=1e-9)
            assert CLOCK.shed(p.land + CLOCK.cross + 0.5 * CLOCK.shed_dur + 1e-6, j) == pytest.approx(-up)
    ts = np.linspace(0.0, BEATS[-1] + 0.4, 3000)
    s = np.array([CLOCK.shed(t, 3) for t in ts])
    assert np.max(np.abs(np.diff(s))) < 0.1  # never jumps


def test_the_weft_in_flight_passes_under_the_warps_that_are_up():
    # warp j is up in the shed while row r flies; beaten in, it crosses over row r (warp_crimp > 0)
    for p in CLOCK.passes:
        t = 0.5 * (p.depart + p.land)
        for j in range(6):
            assert np.sign(CLOCK.shed(t, j)) == np.sign(float(weave.warp_crimp(p.row, j, 1.0)))


def test_three_plies_wind_round_a_centreline_in_its_plane_at_the_lay():
    y = np.linspace(0, 20, 401)
    c = np.column_stack([np.zeros_like(y), y, 0.3 * np.sin(y)])  # a warp: in the y-z plane
    plies = weave.ply_offsets(c, (1.0, 0.0, 0.0), 0.5, 0.1)
    assert len(plies) == 3
    for p in plies:
        assert np.allclose(np.linalg.norm(p - c, axis=1), 0.5)
    # a third of a turn apart
    d0, d1 = plies[0][0] - c[0], plies[1][0] - c[0]
    assert math.degrees(math.acos(np.dot(d0, d1) / 0.25)) == pytest.approx(120, abs=1e-6)
    # straight: one turn every 10 units of length
    s = np.linspace(0, 20, 201)
    straight = np.column_stack([np.zeros_like(s), s, np.zeros_like(s)])
    off = weave.ply_offsets(straight, (1.0, 0.0, 0.0), 0.5, 0.1)[0] - straight
    assert np.allclose(off[0], off[100]) and np.allclose(off[0], -off[50])  # a turn in 10, half a turn in 5
    assert weave.lay_turns(14, 0.5) == pytest.approx(math.tan(math.radians(14)) / math.pi)
