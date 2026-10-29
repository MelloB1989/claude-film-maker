import math

import numpy as np
import pytest

from lib import fx_impact as fx


def test_focus_lines_run_from_beyond_the_frame_to_short_of_the_subject():
    t = fx.focus_lines(80, center=(0.1, -0.05), inner=0.25, ellipse=(1.0, 1.0), jitter=0.4, seed=3)
    assert t.shape == (80, 3, 2)
    base = (t[:, 0] + t[:, 1]) / 2
    corner = math.hypot(16 / 9 / 2, 0.5)
    assert (np.hypot(*base.T) > corner).all()                       # every base off the frame
    r_tip = np.hypot(*(t[:, 2] - (0.1, -0.05)).T)
    assert r_tip.min() >= 0.25 - 1e-9 and r_tip.max() <= 0.25 * 1.4 + 1e-9
    # spread all round: no gap wider than a few lines' worth
    a = np.sort(np.arctan2(*(t[:, 2] - (0.1, -0.05))[:, ::-1].T))
    assert np.diff(np.r_[a, a[0] + 2 * math.pi]).max() < 3 * 2 * math.pi / 80


def test_focus_lines_are_the_same_for_a_seed():
    assert np.array_equal(fx.focus_lines(20, seed=5), fx.focus_lines(20, seed=5))
    assert not np.array_equal(fx.focus_lines(20, seed=5), fx.focus_lines(20, seed=6))


def test_streaks_run_along_their_direction_and_leave_the_subject_clear():
    clear = ((0.0, 0.0), (0.4, 0.3))
    t = fx.streaks(200, direction=(1.0, 0.2), clear=clear, seed=2)
    assert t.shape[1:] == (3, 2) and len(t) % 2 == 0 and len(t) > 100
    d = np.array([1.0, 0.2]) / np.hypot(1.0, 0.2)
    pairs = t.reshape(-1, 2, 3, 2)
    tips = pairs[:, :, 0]                                            # the two ends of each line
    along = tips[:, 1] - tips[:, 0]
    cross = np.abs(along[:, 0] * d[1] - along[:, 1] * d[0])
    assert (cross < 1e-9).all()
    for p in t.reshape(-1, 2):
        assert (p[0] / 0.4) ** 2 + (p[1] / 0.3) ** 2 >= 0.85


def test_glint_tapers_to_points_and_draws_across():
    g = fx.glint((-0.8, -0.2), (0.8, 0.2), 0.01, n=20)
    assert g.shape == (38, 3, 2)
    pts = g.reshape(-1, 2)
    assert np.allclose(pts[np.argmin(pts[:, 0])], (-0.8, -0.2))      # both ends a point on the line
    assert np.allclose(pts[np.argmax(pts[:, 0])], (0.8, 0.2))
    half = fx.glint((-0.8, -0.2), (0.8, 0.2), 0.01, draw=0.5)
    assert half.reshape(-1, 2)[:, 0].max() == pytest.approx(0.0)
    assert fx.glint((0, 0), (1, 0), 0.01, draw=0.0).shape == (0, 3, 2)
    # never wider than asked
    d = np.array([1.6, 0.4]) / np.hypot(1.6, 0.4)
    off = np.abs((pts - (-0.8, -0.2)) @ np.array([-d[1], d[0]]))
    assert off.max() <= 0.005 + 1e-12


def test_star_has_its_rays():
    s = fx.star((0.2, 0.1), 0.1, rays=6)
    assert s.shape == (12, 3, 2)
    far = np.hypot(*(s.reshape(-1, 2) - (0.2, 0.1)).T).max()
    assert far == pytest.approx(0.1)


def test_shards_burst_out_slow_and_fall():
    assert fx.shards(10, -0.1).shape == (0, 3, 2)
    a, b, c = (fx.shards(30, t, center=(0.0, 0.0), gravity=0.0, seed=4) for t in (0.0, 0.2, 0.6))
    ca, cb, cc = (np.hypot(*x.reshape(-1, 3, 2).mean(axis=1).T).mean() for x in (a, b, c))
    assert ca < 0.05 < cb < cc
    assert (cc - cb) / 0.4 < (cb - ca) / 0.2                          # drag: slower later
    fall = fx.shards(30, 0.6, center=(0.0, 0.0), gravity=1.0, seed=4)
    assert fall.reshape(-1, 2)[:, 1].mean() < c.reshape(-1, 2)[:, 1].mean()


def test_beats_lay_a_pattern_out_and_hold_its_last():
    b = fx.beats([("white", 2), ("neg", 3), ("pos", 1)], frames=8)
    assert b == ["white", "white", "neg", "neg", "neg", "pos", "pos", "pos"]
    with pytest.raises(ValueError):
        fx.beats([("pink", 2)])
    with pytest.raises(ValueError):
        fx.beats([("neg", 5)], frames=3)


def test_beat_values():
    assert fx.beat_values("color") == {"amount": 0.0, "invert": 0.0, "white": 0.0, "black": 0.0}
    assert fx.beat_values("neg")["invert"] == 1.0 and fx.beat_values("neg")["amount"] == 1.0
    assert fx.beat_values("pos")["invert"] == 0.0
    assert fx.beat_values("white")["white"] == 1.0
    with pytest.raises(ValueError):
        fx.beat_values("x")


def test_jolt_starts_on_its_frame_and_dies_away():
    e = fx.jolt(24, 6, 0.02, decay=8.0)
    assert (e[:6] == 0).all() and e[6] == pytest.approx(0.02)
    assert (np.diff(e[6:]) < 0).all() and e[-1] < 0.002


def test_shake_follows_its_envelope():
    env = np.r_[np.zeros(10), np.full(30, 0.01)]
    s = fx.shake(env, roll=2.0, seed=3)
    assert s.shape == (40, 3)
    assert (s[:10] == 0).all()
    assert np.abs(s[10:, :2]).max() <= 0.01 + 1e-12 and np.abs(s[10:, :2]).max() > 0.004
    assert np.array_equal(s, fx.shake(env, roll=2.0, seed=3))


def test_burst_throws_drops_up_and_out_and_drops_the_fallen():
    p, v = fx.burst(50, -0.1)
    assert p.shape == (0, 3)
    p, v = fx.burst(200, 0.15, origin=(1.0, 2.0, 0.0), toward=(1.0, 0.0), spread=0.3, seed=2)
    assert len(p) > 150 and (p[:, 2] > 0).all()
    assert (p[:, 0] > 1.0).all() and np.abs(p[:, 1] - 2.0).max() < 0.3 * 2.4 * 0.15 + 1e-9
    late, _ = fx.burst(200, 1.0, seed=2)
    assert len(late) < len(p)                                     # most have come down by then
