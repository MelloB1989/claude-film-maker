# lib/braid.py: the three-strand plait (B08) and threads that move along their own length.
import math

import numpy as np
import pytest

from lib import braid, thread

R = 0.004


def test_the_plaits_strands_just_touch():
    pl = braid.Plait(R)
    gap = braid.min_gap(pl)
    assert 1.97 * R <= gap <= 2.06 * R  # neighbours touch at their closest, with no overlap to speak of
    # and it is a plait: wherever two strands cross (their x the same), one is over the other, the same one every time,
    # round the cycle: 0 over 1, 1 over 2, 2 over 0 (left over middle, right over middle). Each strand goes over one
    # neighbour and under the other.
    b = np.linspace(0, 2 * pl.period * R, 2000)
    over = {}
    for i, j in ((0, 1), (1, 2), (2, 0)):
        xi, xj = pl.offset(i, b)[:, 0], pl.offset(j, b)[:, 0]
        cross = np.where(np.diff(np.sign(xi - xj)) != 0)[0]
        assert len(cross) >= 2
        signs = {float(np.sign(pl.offset(i, b[c])[1] - pl.offset(j, b[c])[1])) for c in cross}
        assert len(signs) == 1  # the same strand over at every crossing of this pair
        over[(i, j)] = signs.pop()
    assert len(set(over.values())) == 1  # the cycle: each strand over the next, under the one before


def test_the_pattern_belongs_to_the_material_a_third_of_a_period_apart():
    pl = braid.Plait(R, phase0=0.13)
    P = pl.period * R
    b = np.linspace(0, 3 * P, 97)
    assert np.allclose(pl.offset(1, b), pl.offset(0, b + P / 3))
    assert np.allclose(pl.offset(2, b), pl.offset(0, b + 2 * P / 3))
    assert np.allclose(pl.offset(0, b + P), pl.offset(0, b))  # periodic in the material
    # the frame's axial coordinate is free: the pattern rides the material wherever the plait has been pulled
    assert np.allclose(pl.frame_points(0, b, 0.2)[:, :2], pl.frame_points(0, b, -b)[:, :2])


def test_a_strand_is_longer_than_its_plait_and_arc_inverts():
    pl = braid.Plait(R)
    P = pl.period * R
    for k in range(3):
        b = np.linspace(0, 2.5 * P, 300)
        s = pl.arc(k, b)
        assert s[0] == pytest.approx(0) and np.all(np.diff(s) > 0)
        assert pl.arc(k, P) == pytest.approx(pl.stretch * P, rel=1e-3)
        pts = pl.frame_points(k, b, -b)  # straight plait: integrate the strand numerically
        assert pl.arc(k, b[-1]) == pytest.approx(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum(), rel=2e-3)
        assert pl.b_of_arc(k, s, b[-1]) == pytest.approx(b, abs=R * 0.05)
    assert 1.35 < pl.stretch < 1.5


def test_tubes_along_lay_the_diff_thread_as_diff_thread_paths_does():
    pts = np.array([[0, 0, 0], [0.3, 0.05, 0.02], [0.6, 0.0, 0.1]])
    ref = thread.diff_thread_paths(pts, R)
    X = ref[0][1]  # any tube's path is the centreline offset; rebuild the centreline as the engine does
    c = thread.centreline(pts, min(1 / (abs(thread.diff_twist(R)) * 24), R * 2))
    u = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
    got = braid.tubes_along(c, u, R, (0.0, 0.0, 1.0))
    assert len(got) == len(ref) == 5
    for (ta, Pa, ra), (tb, Pb, rb) in zip(got, ref):
        assert ta == tb and ra == pytest.approx(rb)
        assert np.allclose(Pa, Pb, atol=1e-12)
    assert X.shape == got[0][1].shape


def test_a_thread_pulled_along_carries_its_lay_with_its_material():
    c = np.column_stack([np.linspace(0, 0.2, 201), np.zeros(201), np.zeros(201)])
    u = c[:, 0].copy()
    d = 0.013
    a = braid.tubes_along(c, u, R, (0, 0, 1))
    # the same material, pulled d along the path: every tube point moves exactly d along x
    b = braid.tubes_along(c + [d, 0, 0], u, R, (0, 0, 1))
    for (_, Pa, _), (_, Pb, _) in zip(a, b):
        assert np.allclose(Pb - Pa, [d, 0, 0])
    # whereas the material shifted under a fixed path turns every tube by the lay over d
    s = braid.tubes_along(c, u + d, R, (0, 0, 1))
    turn = 2 * math.pi * thread.diff_twist(R) * d
    ang = lambda P: np.arctan2(P[:, 2], P[:, 1])  # noqa: E731
    for (_, Pa, _), (_, Ps, _) in zip(a[:3], s[:3]):
        dang = np.angle(np.exp(1j * (ang(Ps) - ang(Pa))))
        assert np.allclose(dang, turn, atol=1e-9)


def test_fuzz_rides_the_material():
    c = np.column_stack([np.linspace(0, 0.3, 301), np.zeros(301), np.zeros(301)])
    u = np.linspace(0.0, 0.3, 301)
    table = braid.FuzzTable(0.3, R, per_R=1.0, seed=3)
    T, N, B = braid.frames_along(c, (0, 0, 1))
    p0, r0 = braid.fuzz_along(table, c, u, T, N, B)
    p1, r1 = braid.fuzz_along(table, c + [0.02, 0, 0], u, T, N, B)
    assert np.allclose(p1 - p0, [0.02, 0, 0])
    assert np.allclose(r0, r1) and (r0 > 0).all()
    assert p0.shape == (table.n, table.pts, 3)
    # a fibre whose material is off the thread lies flat at its end with no radius
    p2, r2 = braid.fuzz_along(table, c[:150], u[:150], T[:150], N[:150], B[:150])
    off = table.u > u[149]
    assert (r2[off] == 0).all() and (r2[~off] > 0).all()


def test_paths_extend_straight_past_their_ends_and_corners_round():
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0]], float)
    s = braid.polyline_arc(P)
    assert s[-1] == pytest.approx(2)
    assert braid.at_arc(P, s, np.array([-0.5]))[0] == pytest.approx([-0.5, 0, 0])
    assert braid.at_arc(P, s, np.array([2.25]))[0] == pytest.approx([1, 1.25, 0])
    m = np.linspace(0, 2, 401)
    X = braid.at_arc(P, s, m)
    Y = braid.round_corner(X, m, 1.0, 0.2)
    far = np.abs(m - 1.0) >= 0.2
    assert np.allclose(Y[far], X[far])
    steps = np.linalg.norm(np.diff(Y, axis=0), axis=1)
    assert steps.max() < 0.01  # continuous through the corner
    # the corner is cut, not passed through: a quadratic with its control on the corner and its ends r along each leg
    # passes r / (2 sqrt 2) from it
    assert np.linalg.norm(Y[200] - [1, 0, 0]) == pytest.approx(0.2 / (2 * math.sqrt(2)), abs=1e-3)
