import math

import numpy as np
import pytest

from lib import cinema


def test_eases_run_zero_to_one_and_clamp():
    for kind in ("linear", "sine", "cubic", "quint", "in", "out"):
        assert cinema.ease(0, kind) == pytest.approx(0) and cinema.ease(1, kind) == pytest.approx(1)
        assert cinema.ease(-2, kind) == pytest.approx(0) and cinema.ease(3, kind) == pytest.approx(1)
    assert cinema.ease(0.5, "sine") == pytest.approx(0.5)
    assert cinema.ease(0.1, "quint") < cinema.ease(0.1, "sine")    # a slower start
    assert cinema.ease(0.2, "out") > 0.2 > cinema.ease(0.2, "in")
    with pytest.raises(ValueError):
        cinema.ease(0.5, "bounce")


def test_lenses_by_intent():
    assert cinema.lens_of("wide") == 26.0 and cinema.lens_of("close") == 85.0 and cinema.lens_of(35) == 35.0
    with pytest.raises(ValueError):
        cinema.lens_of("fisheye")


def test_push_moves_toward_the_aim_and_pull_away():
    m = cinema.push((0, -10, 1), (0, 0, 1), 2.0)
    c, a = m.at(1.0)
    assert c == pytest.approx((0, -8, 1)) and a == pytest.approx((0, 0, 1))
    c, _ = cinema.push((0, -10, 1), (0, 0, 1), -3.0).at(1.0)
    assert c == pytest.approx((0, -13, 1))


def test_truck_crane_and_path():
    c, a = cinema.truck((0, -5, 1), (0, 0, 1), (2, 0, 0)).at(0.5)
    assert c == pytest.approx((1, -5, 1)) and a == pytest.approx((1, 0, 1))
    c, a = cinema.crane((0, -5, 1), (0, 0, 1), 3.0, aim_rise=1.0, toward=1.0).at(1.0)
    assert c == pytest.approx((0, -4, 4)) and a == pytest.approx((0, 0, 2))
    p = cinema.path([(0, 0, 0), (1, 0, 0), (2, 1, 0)], (5, 5, 5))
    assert p.at(0)[0] == pytest.approx((0, 0, 0)) and p.at(1)[0] == pytest.approx((2, 1, 0))
    assert p.at(0.5)[0] == pytest.approx((1, 0, 0)) and p.at(0.3)[1] == pytest.approx((5, 5, 5))


def test_orbit_keeps_its_radius_and_aims_at_the_center():
    m = cinema.orbit((1, 2, 0), 4.0, 1.5, -30, 30)
    for u in (0, 0.5, 1):
        c, a = m.at(u)
        assert math.hypot(c[0] - 1, c[1] - 2) == pytest.approx(4.0) and c[2] == pytest.approx(1.5)
        assert a == pytest.approx((1, 2, 0))
    assert m.at(0.5)[0] == pytest.approx((1, -2, 1.5))   # bearing 0: straight down -y


def test_drift_wanders_a_little_and_is_seeded():
    base = cinema.hold((0, -5, 1), (0, 0, 1))
    d = cinema.drift(base, 0.05, seed=2)
    pts = np.array([d.at(u)[0] for u in np.linspace(0, 1, 40)])
    assert np.abs(pts - (0, -5, 1)).max() <= 0.05 * 1.0001 and np.ptp(pts, axis=0).max() > 0.01
    assert cinema.drift(base, 0.05, seed=2).at(0.3)[0] == pytest.approx(d.at(0.3)[0])


def test_frame_on_fills_the_share_through_the_lens():
    face = (0, 0, 1.5)
    cam, aim = cinema.frame_on(face, 0.24, share=0.5, lens=85, bearing=0)
    d = np.linalg.norm(cam - face)
    assert d == pytest.approx(0.48 * 85 / cinema.GATE_H)
    assert cam[1] < 0 and aim == pytest.approx(face)
    assert d == pytest.approx(cinema.distance_for(0.24, 0.5, 85))
    # the face in the left third: the aim is right of it
    cam, aim = cinema.frame_on(face, 0.24, share=0.5, lens=85, third=-1)
    pose = cinema.Pose("x", 0, cam, aim, cinema.look_at(cam, aim), 85.0, 2.8, 0.0)
    u, v = pose.screen(face)
    assert u == pytest.approx(1 / 3, abs=1e-6) and v == pytest.approx(0.5)


def test_look_at_points_the_camera_at_the_aim_upright():
    R = cinema.look_at((0, -5, 1), (2, 0, 2))
    assert R.T @ R == pytest.approx(np.eye(3))
    f = -R[:, 2]
    want = np.array([2, 5, 1]) / np.linalg.norm([2, 5, 1])
    assert f == pytest.approx(want)
    assert R[2, 0] == pytest.approx(0.0)        # no roll: the right stays level
    Rr = cinema.look_at((0, -5, 1), (0, 0, 1), 10)
    assert math.degrees(math.asin(Rr[2, 0])) == pytest.approx(10)
    assert -Rr[:, 2] == pytest.approx((0, 1, 0))


def test_shake_breathes_and_hits_hard():
    s = cinema.Shake(breath=0.1, hits=((1.0, 2.0),), decay=5.0)
    calm = max(np.abs(s.at(t)[0]).max() for t in np.linspace(0, 0.95, 50))
    hit = max(np.abs(s.at(t)[0]).max() for t in np.linspace(1.0, 1.2, 20))
    assert calm < 0.2 and hit > 1.0
    assert cinema.shake_amplitude(s, 0.5) == pytest.approx(0.1)
    assert cinema.shake_amplitude(s, 1.0) == pytest.approx(2.1)
    assert cinema.shake_amplitude(s, 3.0) < 0.2
    assert s.at(0.4)[0] == pytest.approx(cinema.Shake(breath=0.1, hits=((1.0, 2.0),)).at(0.4)[0])
    assert np.all(cinema.Shake().at(1.3)[0] == 0)


def shot():
    return cinema.Shot([
        cinema.Setup("wide", 0.0, cinema.push((0, -10, 1), (0, 0, 1), 2.0), lens="wide", fstop=(8, 4), span=(0.5, 1.5)),
        cinema.Setup("mcu", 2.0, cinema.hold((1, -2, 1.5), (1, 0, 1.5)), lens=(85, 100), focus="aim",
                     racks=(cinema.Rack(3.0, "far", 0.5), cinema.Rack(3.8, "back", 0.4))),
    ], 4.5)


def test_setups_hold_before_and_after_their_span_and_cut():
    s = shot()
    assert s.cuts() == [2.0] and s.window(0) == (0.0, 2.0) and s.window(1) == (2.0, 4.5)
    assert s.pose(0.2).position == pytest.approx((0, -10, 1))      # held before the span
    assert s.pose(1.7).position == pytest.approx((0, -8, 1))       # and after it
    assert s.pose(1.0).position == pytest.approx((0, -9, 1))       # the middle of an eased span
    assert s.pose(1.0).fstop == pytest.approx(6)
    p = s.pose(2.0)
    assert p.setup == "mcu" and p.index == 1 and p.position == pytest.approx((1, -2, 1.5))
    assert p.lens == pytest.approx(85) and s.pose(4.5).lens == pytest.approx(100)
    assert s.pose(1.99).setup == "wide"
    assert p.depth((1, 3, 1.5)) == pytest.approx(5)


def test_focus_racks_blend_along_the_chain():
    s = shot()
    chain = s.focus_chain()
    assert [c[1] for c in chain] == ["aim", "aim", "far", "back"]
    assert s.focus_weights(1.0) == [1, 0, 0, 0]
    assert s.focus_weights(2.5) == [0, 1, 0, 0]
    w = s.focus_weights(3.25)
    assert w[1] == 1 and w[2] == pytest.approx(0.5) and w[3] == 0
    assert s.focus_weights(3.6) == [0, 0, 1, 0]
    w = s.focus_weights(4.0)
    assert w[2] == 1 and w[3] == pytest.approx(0.5)
    assert s.focus_weights(4.4) == [0, 0, 0, 1]


def test_a_shot_must_start_at_zero_with_unique_setups():
    m = cinema.hold((0, -1, 0), (0, 0, 0))
    with pytest.raises(ValueError):
        cinema.Shot([cinema.Setup("a", 0.5, m)], 2)
    with pytest.raises(ValueError):
        cinema.Shot([cinema.Setup("a", 0.0, m), cinema.Setup("a", 1.0, m)], 2)
    with pytest.raises(ValueError):
        cinema.Shot([], 2)


def test_shake_turns_the_view_without_losing_its_aim_much():
    s = cinema.Shot([cinema.Setup("h", 0.0, cinema.hold((0, -5, 1), (0, 0, 1)), shake=cinema.Shake(breath=0.3))], 3)
    for t in np.linspace(0, 3, 13):
        p = s.pose(t)
        assert p.rotation.T @ p.rotation == pytest.approx(np.eye(3))
        ang = math.degrees(math.acos(min(1.0, float(p.forward @ (0, 1, 0)))))
        assert ang < 0.6
