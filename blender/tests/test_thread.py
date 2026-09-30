import math

import numpy as np
import pytest

from lib import thread

# Plies that just touch inside a thread of radius R: n circles of radius r on a ring of radius R - r, neighbours
# touching when (R - r) sin(pi / n) = r, so r = R s / (1 + s) and the ring is R / (1 + s), s = sin(pi / n).
R = 0.01
S3 = math.sin(math.pi / 3)
RP3 = R * S3 / (1 + S3)  # 0.004641016
RO3 = R / (1 + S3)  # 0.005358984


def _dist_to_x_axis(p):
    return np.hypot(p[:, 1], p[:, 2])


def test_three_plies_touch_inside_the_thread_radius():
    plies, rp = thread.ply_paths([(0, 0, 0), (1, 0, 0)], R, plies=3, twist=10)
    assert len(plies) == 3
    assert rp == pytest.approx(0.004641016, abs=1e-9)
    for p in plies:
        np.testing.assert_allclose(_dist_to_x_axis(p), 0.005358984, atol=1e-8)
        assert p[0, 0] == pytest.approx(0) and p[-1, 0] == pytest.approx(1)


def test_plies_sit_a_third_of_a_turn_apart_and_twist_along_the_thread():
    twist = 10  # turns per unit length: half a turn by x = 0.05
    plies, _ = thread.ply_paths([(0, 0, 0), (1, 0, 0)], R, plies=3, twist=twist)
    ang = [np.arctan2(p[:, 2], p[:, 1]) for p in plies]
    x = plies[0][:, 0]
    for k in (1, 2):  # ply k leads ply 0 by k/3 of a turn everywhere
        d = np.angle(np.exp(1j * (ang[k] - ang[0])))
        np.testing.assert_allclose(np.mod(d, 2 * np.pi), 2 * np.pi * k / 3, atol=1e-6)
    # ply 0 turns 2 pi * twist * x
    turned = np.unwrap(ang[0]) - ang[0][0]
    np.testing.assert_allclose(np.abs(turned), 2 * np.pi * twist * x, atol=1e-6)


def test_the_centreline_passes_through_every_point():
    pts = [(0, 0, 0), (1, 1, 0), (2, 0, 0)]
    c = thread.centreline(pts, 0.02)
    for q in pts:
        assert np.min(np.linalg.norm(c - np.array(q, float), axis=1)) < 1e-9
    steps = np.linalg.norm(np.diff(c, axis=0), axis=1)
    assert steps.max() <= 0.02 * 1.05  # sampled at most ~0.02 apart


def test_one_ply_is_the_thread_itself():
    plies, rp = thread.ply_paths([(0, 0, 0), (1, 0, 0)], R, plies=1, twist=10)
    assert rp == pytest.approx(R)
    np.testing.assert_allclose(_dist_to_x_axis(plies[0]), 0, atol=1e-12)
