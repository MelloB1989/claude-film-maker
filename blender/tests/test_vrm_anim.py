import math

import numpy as np
import pytest

from lib import vrm, vrm_anim as va


def test_eases_start_at_0_and_end_at_1():
    for kind in va.EASES:
        assert va.ease(0.0, kind) == pytest.approx(0.0, abs=1e-9)
        assert va.ease(1.0, kind) == pytest.approx(1.0)
    assert va.ease(0.5, "inout") == pytest.approx(0.5)
    assert va.ease(0.5, "in") < 0.5 < va.ease(0.5, "out")
    assert va.ease(0.99, "hold") == 0.0
    with pytest.raises(ValueError, match="overshoot"):
        va.ease(0.5, "bounce")


def test_overshoot_and_settle_go_past_the_key_and_come_back():
    over = [va.ease(u, "overshoot") for u in np.linspace(0, 1, 41)]
    assert 1.05 < max(over) < 1.15
    settle = [va.ease(u, "settle") for u in np.linspace(0, 1, 81)]
    assert 1.0 < max(settle) < 1.1 and min(settle[20:]) > 0.95
    # it ends on the key with no step
    assert abs(settle[-2] - 1.0) < 0.01


def test_quaternions_round_trip_and_slerp_the_short_way():
    for turn in [(0, 0, 0), (30, -20, 75), (170, 10, -5), (-90, 0, 180)]:
        m = vrm.euler(turn)
        q = va.quat(m)
        assert q[0] >= 0 and np.linalg.norm(q) == pytest.approx(1.0)
        assert np.allclose(va.matrix(q), m, atol=1e-9)
    a, b = va.quat(vrm.euler((0, 0, 10))), va.quat(vrm.euler((0, 0, 50)))
    mid = va.matrix(va.slerp(a, b, 0.5))
    assert np.allclose(mid, vrm.euler((0, 0, 30)), atol=1e-9)
    # past the end (an overshoot) carries on round the same axis
    assert np.allclose(va.matrix(va.slerp(a, b, 1.25)), vrm.euler((0, 0, 60)), atol=1e-9)
    assert va.angle_between(vrm.euler((0, 0, 10)), vrm.euler((0, 0, 50))) == pytest.approx(40.0)


def test_swing_to_takes_one_direction_to_another():
    for a, b in [((1, 0, 0), (0, 1, 0)), ((0, 0, 1), (0.3, -0.2, 0.9)), ((1, 0, 0), (-1, 0, 0))]:
        r = va.swing_to(a, b)
        b = np.asarray(b, float) / np.linalg.norm(b)
        assert np.allclose(r @ np.asarray(a, float), b, atol=1e-9)
        assert np.allclose(r @ r.T, np.eye(3), atol=1e-9)


def test_track_holds_outside_its_keys_and_eases_between():
    tr = va.Track("vec")
    tr.key(10, (0.0, 0.0, 0.0))
    tr.key(20, (1.0, 2.0, 0.0), "linear")
    tr.key(30, (1.0, 2.0, 4.0), "hold")
    assert np.allclose(tr.at(0), (0, 0, 0)) and np.allclose(tr.at(99), (1, 2, 4))
    assert np.allclose(tr.at(15), (0.5, 1.0, 0.0))
    assert np.allclose(tr.at(29.5), (1, 2, 0)) and np.allclose(tr.at(30), (1, 2, 4))
    # a key on the same frame replaces the old one
    tr.key(20, (0.0, 0.0, 0.0), "linear")
    assert len(tr.keys) == 3 and np.allclose(tr.at(20), 0)


def test_rotation_track_slerps_turns():
    tr = va.Track("rot")
    tr.key(0, (0, 0, 0))
    tr.key(10, (0, 0, 90), "linear")
    assert np.allclose(tr.at(5), vrm.euler((0, 0, 45)), atol=1e-9)
    assert np.allclose(tr.at(10), vrm.euler((0, 0, 90)), atol=1e-9)
    with pytest.raises(ValueError):
        va.Track("angle")


def test_the_root_frame_faces_x_with_its_left_at_y():
    # the character's front is -y in its own frame; on a root turned by nothing it faces +x
    assert np.allclose(va.to_world((0, -1, 0), (0, 0, 0), 0.0), (1, 0, 0))
    assert np.allclose(va.to_world((1, 0, 0), (0, 0, 0), 0.0), (0, 1, 0))
    # turned 90 degrees it faces +y, its left at -x
    assert np.allclose(va.to_world((0, -1, 0), (2, 3, 0), 90.0), (2, 4, 0))
    p = np.array([0.3, -0.2, 1.1])
    assert np.allclose(va.to_char(va.to_world(p, (1, -2, 0.5), 37.0), (1, -2, 0.5), 37.0), p)
    assert va.heading((0, 1)) == pytest.approx(90.0)
    assert va.unwrap(170.0, -170.0) == pytest.approx(190.0)


def test_path_rounds_corners_and_measures_its_length():
    p = va.Path([(0, 0), (4, 0)])
    assert p.length == pytest.approx(4.0)
    assert np.allclose(p.at(1.0), (1, 0)) and np.allclose(p.at(9), (4, 0))
    assert p.yaw(2.0) == pytest.approx(0.0)
    corner = va.Path([(0, 0), (2, 0), (2, 2)])
    assert corner.length < 4.0                    # the corner rounded off
    assert 0 < corner.yaw(corner.length / 2) < 90
    with pytest.raises(ValueError):
        va.Path([(1, 1), (1, 1)])


def test_pchip_never_overshoots_its_knots():
    x, y = [0, 1, 2, 3], [0, 0.5, 2.5, 3.0]
    xs = np.linspace(-1, 4, 200)
    ys = va.pchip(x, y, xs)
    assert np.all(np.diff(ys) >= -1e-12)
    assert ys[0] == 0 and ys[-1] == 3.0
    assert np.allclose(va.pchip(x, y, x), y)


@pytest.mark.parametrize("gait", list(va.GAITS))
@pytest.mark.parametrize("length", [0.3, 1.0, 3.7, 8.0])
def test_a_walks_plan_alternates_feet_and_ends_with_them_together(gait, length):
    g = va.GAITS[gait]
    steps, kt, kd = va.plan_steps(length, g)
    assert steps[0].side == "right"
    sides = [s.side for s in steps[:-1]]
    assert all(a != b for a, b in zip(sides, sides[1:]))
    # every step forward, none longer than a stride and a bit, the last brings the feet together at the end
    for s in steps:
        assert s.b >= s.a - 1e-9 and s.t1 > s.t0
        assert s.b - s.a <= 2 * g.stride * 1.2 + 1e-9
    last = {}
    for s in steps:
        last[s.side] = s.b
    assert last["left"] == pytest.approx(length) and last["right"] == pytest.approx(length)
    # a walk always has a foot down: the next lifts only after the last has landed
    if g.duty > 0.5:
        for a, b in zip(steps, steps[1:]):
            assert b.t0 >= a.t1 - 1e-9
    # the body starts and ends at rest, moving forward only
    assert kd[0] == 0 and kd[-1] == pytest.approx(length)
    assert np.all(np.diff(kd) >= 0) and np.all(np.diff(kt) > 0)
    assert kt[-1] >= steps[-1].t1


def test_gaits_scale_with_height_and_change_one_field():
    old = va.GAITS["old"]
    tall = old.scaled(old.height * 2)
    assert tall.stride == pytest.approx(old.stride * 2) and tall.speed == pytest.approx(old.speed * 2)
    assert tall.duty == old.duty
    assert va.GAITS["heavy"].but(stride=1.0).stride == 1.0
    assert va.gait_of("run") is va.GAITS["run"]
    with pytest.raises(KeyError):
        va.gait_of("skip")


def test_the_heavy_walk_is_slower_and_longer_than_the_old_womans():
    h, o = va.GAITS["heavy"], va.GAITS["old"]
    assert h.stride > 1.5 * o.stride and h.lift > o.lift and o.duty > h.duty
    r, c = va.GAITS["run"], va.GAITS["charge"]
    assert r.duty < 0.5 and c.duty < 0.5 and c.lean > r.lean > h.lean


def test_foot_phase_follows_its_steps():
    steps, _, _ = va.plan_steps(3.0, va.GAITS["walk"])
    s = steps[1]
    a, b, u, since = va.foot_phase(steps, s.side, (s.t0 + s.t1) / 2)
    assert (a, b) == (s.a, s.b) and u == pytest.approx(0.5)
    assert va.foot_phase(steps, "right", -1.0)[2] == 1.0
    assert va.until_lift(steps, s.side, s.t0 - 0.1) == pytest.approx(0.1)


def test_blinks_are_seeded_spaced_and_include_extra_ones():
    a = va.blink_times(0, 30, seed=4)
    assert a == va.blink_times(0, 30, seed=4) and a != va.blink_times(0, 30, seed=5)
    assert all(b - a_ >= 0.25 for a_, b in zip(a, a[1:]))
    assert 4 <= len(a) <= 20
    assert 12.0 in va.blink_times(0, 30, seed=4, mean=1e6, extra=[12.0])
    assert va.blink_shape(-0.01) == 0 and va.blink_shape(0.07) == 1.0 and va.blink_shape(1.0) == 0
    assert 0 < va.blink_shape(0.15) < 1


def test_morae_read_romaji_and_kana():
    m = va.morae("tsuyoku naritai")
    assert [x.vowel for x in m] == ["ou", "oh", "ou", "aa", "ih", "aa", "ih"]
    m = va.morae("baasan")
    assert [x.vowel for x in m] == ["aa", "aa", None] and m[0].lips and m[0].weight == 2.0
    m = va.morae("ame wa, yanda yo")
    assert m[2].pause > 0 and m[1].lips
    k = va.morae("わかいねぇ")
    assert [x.vowel for x in k] == ["aa", "aa", "ih", "ee"]
    assert [x.vowel for x in va.morae("きった")] == ["ih", None, "aa"]
    # kanji flap at a natural rate
    assert len(va.morae("強")) == 1 and va.morae("強")[0].weight == 1.5
    assert va.morae("……") == []


def test_visemes_open_on_the_line_and_shut_off_it():
    v = va.visemes("tsuyoku naritai", 10.0, 11.6)
    ts = [t for t, _ in v]
    assert ts[0] < 10.0 and ts[-1] > 11.6
    assert v[0][1] == {} and v[-1][1] == {}
    peak = max((max(w.values()) for _, w in v if w), default=0)
    assert 0.4 < peak <= 1.2
    seen = {k for _, w in v for k in w}
    assert seen == {"ou", "oh", "aa", "ih"}
    # the mouth moves: it opens and closes several times over the line
    open_ = [sum(w.values()) > 0.3 for _, w in v]
    rises = sum(1 for a, b in zip(open_, open_[1:]) if b and not a)
    assert rises >= 3
    # the same line, the same seed, the same mouth
    assert v == va.visemes("tsuyoku naritai", 10.0, 11.6)


def test_smooth_damp_arrives_without_overshoot():
    x, v = 0.0, 0.0
    xs = []
    for _ in range(96):
        x, v = va.smooth_damp(x, v, 10.0, 0.3, 1 / 24)
        xs.append(x)
    assert max(xs) <= 10.0 + 1e-9 and xs[-1] == pytest.approx(10.0, abs=0.05)
    assert 2.0 < xs[6] < 9.5       # a quarter second in: on its way


def test_yaw_pitch_by_vrms_turns():
    assert va.yaw_pitch((0, -1, 0)) == pytest.approx((0.0, 0.0))
    assert va.yaw_pitch((1, -1, 0))[0] == pytest.approx(45.0)        # to its left: z+
    assert va.yaw_pitch((0, -1, -1))[1] == pytest.approx(45.0)       # down: x+ (a nod)


def test_fk_carries_children_with_their_parents_turns():
    order = ["hips", "spine", "head"]
    parents = {"spine": "hips", "head": "spine"}
    rest = {"hips": (0, 0, 1.0), "spine": (0, 0, 1.2), "head": (0, 0, 1.6)}
    tot, heads = va.fk(order, parents, rest, {"spine": vrm.euler((90, 0, 0))}, hips_offset=(0, 0, -0.1))
    assert np.allclose(heads["hips"], (0, 0, 0.9))
    assert np.allclose(heads["spine"], (0, 0, 1.1))
    # a 90 degree bend forward at the spine lays the head out in front (-y)
    assert np.allclose(heads["head"], (0, -0.4, 1.1), atol=1e-9)
    assert np.allclose(tot["head"], vrm.euler((90, 0, 0)))


def test_a_chain_hangs_and_lags_but_keeps_its_lengths():
    goal = np.array([[0, 0, 1.0], [0, 0, 0.8], [0, 0, 0.6]])
    lengths = [0.2, 0.2]
    pts, prev = goal.copy(), goal.copy()
    # the root jerks sideways: the chain trails it, then comes back under it
    moved = goal + np.array([0.3, 0, 0])
    trail = None
    for i in range(48):
        new = va.chain_step(pts, prev, moved, lengths, dt=1 / 48, stiffness=8.0, drag=0.1, gravity=(0, 0, 0),
                            wind=(0, 0, 0))
        prev, pts = pts, new
        if i == 1:
            trail = pts[-1, 0]
    assert trail < 0.3 - 0.02
    assert np.allclose(pts[0], moved[0])
    for i in range(2):
        assert np.linalg.norm(pts[i + 1] - pts[i]) == pytest.approx(0.2, abs=1e-6)
    assert abs(pts[-1, 0] - 0.3) < 0.03


def test_wind_gusts_round_one():
    g = [va.gust(t, seed=3) for t in np.linspace(0, 20, 400)]
    assert 0.5 < min(g) < max(g) < 1.5 and abs(np.mean(g) - 1.0) < 0.15
    assert g == [va.gust(t, seed=3) for t in np.linspace(0, 20, 400)]


def test_pivot_raises_the_ankle_off_its_heel_or_ball():
    ankle = np.array([0.0, 0.0, 0.08])
    up = va._pivot(ankle, 0.0, 30.0, 0.13, 0.08)       # heel off, about the ball
    assert up[2] > ankle[2] and up[0] > ankle[0]
    back = va._pivot(ankle, 0.0, -15.0, -0.05, 0.08)   # toes up, about the heel
    assert back[2] > ankle[2] - 1e-9 and back[0] < ankle[0]
    assert np.allclose(va._pivot(ankle, 0.0, 0.0, 0.13, 0.08), ankle)
    # the pivot itself stays on the ground where it was
    ball = ankle + np.array([0.13, 0, -0.08])
    assert np.linalg.norm(up - ball) == pytest.approx(np.linalg.norm(ankle - ball))


def test_ground_from_a_height_or_a_function():
    assert va.ground_of(0.25)(3.0, -1.0) == 0.25
    hill = va.ground_of(lambda x, y: 0.1 * x)
    assert hill(2.0, 0.0) == pytest.approx(0.2)
