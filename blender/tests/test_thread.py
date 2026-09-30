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


# ------------------------------------------------------------------------------------------ the macro rope (B01)

def test_the_lay_matches_the_engines_thread_look():
    # THREAD_LOOK: plies of 0.5 R on a circle of 0.5 R, a 32 degree lay = 0.199 turns per R (5.03 R per turn)
    assert thread.LOOK["ply_radius"] == 0.5 and thread.LOOK["ply_offset"] == 0.5 and thread.LOOK["lay_deg"] == 32
    assert thread.lay_turns(32, 0.5) == pytest.approx(math.tan(math.radians(32)) / math.pi, rel=1e-12)
    assert 1 / thread.lay_turns(32, 0.5) == pytest.approx(5.03, abs=0.01)


def test_a_fray_untwists_the_middle_and_puts_the_twist_back_on_its_shoulders():
    s = np.linspace(-40, 40, 8001)
    u = thread.untwisted(s, 0.0, 5.0, 1.0, 1.35)
    far = np.abs(s) >= 15  # beyond three spans the rope never turns
    np.testing.assert_allclose(u[far], s[far], atol=1e-9)
    rate = np.gradient(u, s)
    assert rate[4000] == pytest.approx(1 - 1.35 + 1.35 / 3, abs=1e-3)  # 10% of the twist at the middle
    assert np.all(np.diff(u) > 0)  # and it still turns the same way everywhere


def test_the_rotation_minimising_frame_does_not_turn_on_a_straight_line():
    X = np.column_stack([np.linspace(0, 1, 50), np.zeros(50), np.zeros(50)])
    for rev in (False, True):
        T, N, B = thread.rmf(X, [0.0, 0.3, 1.0], reverse=rev)
        n = np.array([0.0, 0.3, 1.0]) / np.hypot(0.3, 1.0)
        np.testing.assert_allclose(N, np.tile(n, (50, 1)), atol=1e-12)
        np.testing.assert_allclose(np.einsum("ij,ij->i", T, N), 0, atol=1e-12)


def test_the_fibre_rope_is_seeded():
    a = thread.fibre_rope(0.01, 0.2, seed=3, fibres=12, fuzz_per_R=4)
    b = thread.fibre_rope(0.01, 0.2, seed=3, fibres=12, fuzz_per_R=4)
    c = thread.fibre_rope(0.01, 0.2, seed=4, fibres=12, fuzz_per_R=4)
    for k in ("fib_phi", "fib_rho", "fib_break", "fz_s", "fz_len", "fib_crimp", "fib_frayloop"):
        np.testing.assert_array_equal(getattr(a, k), getattr(b, k))
    assert not np.array_equal(a.fib_phi, c.fib_phi)


def _whole(rope, side):
    s = thread.half_samples(rope, side)
    X = np.column_stack([s - rope.break_at, np.zeros_like(s), np.zeros_like(s)])
    _, N, _ = thread.rmf(X, [0.0, 0.0, 1.0], reverse=side == "right")
    return thread.still_pose(rope, s, X, N)


def test_the_halves_of_a_whole_rope_meet_fibre_for_fibre():
    R = 0.01
    rope = thread.fibre_rope(R, 40 * R, seed=5, fibres=16, fuzz_per_R=2)
    geo = {}
    for side in ("left", "right"):
        topo = thread.half_topology(rope, side)
        geo[side] = (topo, thread.rope_geometry(rope, _whole(rope, side), topo, fray_centre=rope.break_at, fray_amount=0))
    (tl, gl), (tr, gr) = geo["left"], geo["right"]
    ends = np.cumsum(gl.fibre_counts) - 1  # each left fibre's last point, each right fibre's first
    starts = np.concatenate([[0], np.cumsum(gr.fibre_counts)[:-1]])
    np.testing.assert_allclose(gl.fibre_pts[ends], gr.fibre_pts[starts], atol=1e-9)
    for k in range(3):  # the cores meet ring for ring at each ply's parting
        np.testing.assert_allclose(gl.cores[k][-1], gr.cores[k][0], atol=1e-9)
        # and a ply's centre sits THREAD_LOOK's 0.5 R off the axis (the parting ring, between samples, on a chord of the
        # helix: within 0.3%)
        centre = gl.cores[k].mean(axis=1)
        np.testing.assert_allclose(np.hypot(centre[:, 1], centre[:, 2]), 0.5 * R, rtol=3e-3)
