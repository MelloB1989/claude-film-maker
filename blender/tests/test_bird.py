import math
from dataclasses import astuple

import numpy as np
import pytest

from lib import bird


def test_lerp_runs_from_one_pose_to_the_other():
    a, b = bird.PERCH, bird.CAW
    assert bird.lerp(a, b, 0.0) == a
    assert astuple(bird.lerp(a, b, 1.0)) == pytest.approx(astuple(b))
    mid = bird.lerp(a, b, 0.5)
    assert mid.jaw == pytest.approx(b.jaw / 2)
    assert mid.body_pitch == pytest.approx((a.body_pitch + b.body_pitch) / 2)


def test_flap_goes_high_low_high_with_the_hands_swept_back_on_the_upstroke():
    top, bottom = bird.flap(0.0), bird.flap(0.55)
    assert top.lift_arm > math.radians(30) and bottom.lift_arm < -math.radians(30)
    assert bird.flap(1.0).lift_arm == pytest.approx(top.lift_arm)
    # the downstroke's hands are spread; the upstroke's swept back and folded in
    assert bird.flap(0.3).sweep_hand == pytest.approx(bird.FLIGHT.sweep_hand)
    assert bird.flap(0.78).sweep_hand > math.radians(40)
    # the body bobs against the wings: up when they are high
    assert top.lift > bottom.lift
    # no beat holds the base
    assert bird.flap(0.4, amp=0.0) == bird.FLIGHT


def test_beat_wraps_at_the_rate():
    assert bird.beat(0.0, 4.0) == 0.0
    assert bird.beat(0.25, 4.0) == pytest.approx(0.0)
    assert bird.beat(0.125, 4.0, phase=0.25) == pytest.approx(0.75)


def test_curve_passes_through_its_points_evenly_spaced():
    pts = [(0, 0, 0), (1, 0, 0), (2, 1, 0), (3, 1, 1)]
    c = bird.curve(pts, 50)
    assert np.allclose(c[0], pts[0]) and np.allclose(c[-1], pts[-1], atol=1e-6)
    gaps = np.linalg.norm(np.diff(c, axis=0), axis=1)
    assert gaps.max() / gaps.min() < 1.05
    with pytest.raises(ValueError):
        bird.curve([(0, 0, 0)], 5)


def test_path_heads_along_the_way_it_goes_and_banks_into_turns():
    straight = bird.path([(0, 0, 0), (0, 5, 0), (0, 10, 0)], 20)
    assert all(p.heading == pytest.approx(0.0, abs=1e-6) for p in straight)
    assert all(abs(p.bank) < 1e-6 for p in straight)
    climb = bird.path([(0, 0, 0), (0, 10, 10)], 10)
    assert climb[5].pitch == pytest.approx(math.pi / 4, abs=1e-3)
    # toward +x is a turn to the right of +y: heading negative; a left curve banks positive
    right = bird.path([(0, 0, 0), (10, 0, 0)], 10)
    assert right[5].heading == pytest.approx(-math.pi / 2, abs=1e-6)
    left = bird.path([(0, 0, 0), (0, 10, 0), (-10, 20, 0)], 40)
    assert max(p.bank for p in left) > 0.05
    assert all(p.bank <= math.radians(50) + 1e-9 for p in left)


def test_path_spaces_its_samples_by_the_speeds():
    pts = [(0, 0, 0), (0, 10, 0)]
    slow_start = bird.path(pts, 11, speeds=np.linspace(0.1, 1.0, 11))
    ys = [p.location[1] for p in slow_start]
    gaps = np.diff(ys)
    assert ys[0] == pytest.approx(0.0) and ys[-1] == pytest.approx(10.0)
    assert gaps[0] < gaps[-1]
    with pytest.raises(ValueError):
        bird.path(pts, 3, speeds=[1, 1])


def test_holds_snap_to_each_value_and_hold_it():
    keys = [(0.0, 0.0), (1.0, 1.0), (2.0, -0.5)]
    assert bird.holds(keys, 0.5) == 0.0
    assert bird.holds(keys, 1.5) == 1.0
    assert bird.holds(keys, 9.0) == -0.5
    # mid-snap it is on its way, and overshoots a little before it settles
    mid = bird.holds(keys, 1.05, snap=0.12)
    assert 0.3 < mid < 1.0
    assert max(bird.holds(keys, 1.0 + s, snap=0.12) for s in np.linspace(0, 0.12, 30)) > 1.0
    with pytest.raises(ValueError):
        bird.holds([], 0.0)


def test_vane_is_pointed_and_widest_near_its_root():
    left, right = bird.vane(0.2, 0.04)
    w = right[:, 0] - left[:, 0]
    assert w[-1] == pytest.approx(0.0) and right[-1, 1] == pytest.approx(0.2)
    assert w.argmax() in (1, 2, 3)
    assert w.max() == pytest.approx(0.04, rel=0.1)


def test_the_wings_mirror_and_span_about_a_metre():
    r = bird.wing_geometry(side=1)
    lft = bird.wing_geometry(side=-1)
    rv = np.array(r["hand"][0])
    lv = np.array(lft["hand"][0])
    assert np.allclose(rv[:, 0], -lv[:, 0]) and np.allclose(rv[:, 1:], lv[:, 1:])
    # span: shoulder to wrist plus the hand's reach outward, both sides and the body between
    reach = bird.ARM + rv[:, 0].max()
    span = 2 * (bird.SHOULDER[0] + reach)
    assert 0.8 < span < 1.2
    # every face indexes a vertex
    for verts, faces in (r["arm"], r["hand"], bird.tail_geometry(), bird.folded_geometry(side=-1)):
        assert max(max(f) for f in faces) < len(verts)
