# The bpy-free halves of anime hair (lib/animehair.py): a lock's section, its taper, the smooth path it is swept along,
# the sweep itself, rows of locks, and the way a combed lock climbs over the skull. Expected values are worked from the
# definitions, never with the code under test.
import math

import numpy as np
import pytest

from lib import animehair


def test_a_section_runs_edge_to_edge_out_and_back_meeting_in_two_sharp_edges():
    prof = animehair.profile("crescent", 6)
    assert prof.shape == (2 * 6 - 2, 2)
    assert tuple(prof[0]) == (-1.0, 0.0) and tuple(prof[5]) == (1.0, 0.0)    # the two edges
    assert prof[:6, 1].max() == pytest.approx(1.0 - 0.2 ** 2)                 # the outer arc's crown (x +-0.2 sampled)
    inner = prof[6:]
    assert (inner[:, 1] > 0).all() and (inner[:, 1] < prof[1:5, 1][::-1]).all()   # a crescent: inner bowed out, inside the outer
    lens = animehair.profile("lens", 6)
    assert (lens[6:, 1] < 0).all()                                           # a lens bows toward the head


def test_a_lock_widens_from_its_root_to_its_peak_then_narrows_to_a_point():
    u = np.linspace(0, 1, 101)
    w = animehair.taper(u, peak=0.3, point=1.0, root=0.5)
    assert w[0] == pytest.approx(0.5)
    assert w[30] == pytest.approx(1.0)
    assert w[100] == pytest.approx(0.0)
    assert (np.diff(w[:31]) >= -1e-12).all() and (np.diff(w[30:]) <= 1e-12).all()
    assert w[65] == pytest.approx((1 - 0.65) / 0.7)                          # point 1: straight down to the tip


def test_a_path_is_resampled_smooth_and_even_through_its_ends():
    pts = np.array([(0, 0, 0), (0.1, 0, 0), (0.2, 0.05, 0), (0.25, 0.15, 0)], float)
    rp = animehair.resample(pts, 21)
    assert rp.shape == (21, 3)
    assert np.allclose(rp[0], pts[0]) and np.allclose(rp[-1], pts[-1])
    seg = np.linalg.norm(np.diff(rp, axis=0), axis=1)
    assert seg.max() / seg.min() < 1.05                                      # evenly spaced along it


def test_a_sweep_makes_rings_of_the_section_a_tip_and_the_two_sharp_edges():
    k, n = 5, 4
    path = np.column_stack([np.zeros(k), np.zeros(k), -np.linspace(0, 0.1, k)])   # falling straight down
    outs = np.tile((0.0, -1.0, 0.0), (k, 1))                                  # away from the head: -y
    w = np.array([0.04, 0.04, 0.03, 0.02, 0.0])
    d = np.full(k, 0.01)
    prof = animehair.profile("crescent", n)
    verts, faces, along, across, edges = animehair.sweep(path, outs, w, d, prof)
    m = len(prof)
    assert verts.shape == ((k - 1) * m + 1, 3)
    assert np.allclose(verts[-1], path[-1])                                   # one vertex for the point
    ring0 = verts[:m]
    assert np.ptp(ring0[:, 0]) == pytest.approx(0.04)                        # across: x
    assert ring0[:, 1].min() == pytest.approx(-0.01 * (1 - (1 / 3) ** 2))    # out from the head (-y): the arc's crown at x +-1/3
    assert along[0] == 0.0 and along[-1] == 1.0 and across[0] == -1.0
    assert len(faces) == 1 + (k - 2) * m + m                                  # the cap, the quads, the fan to the tip
    assert len(edges) == 2 * (k - 2)


def test_a_fan_places_its_locks_round_the_head_and_varies_them_within_bounds():
    rng = np.random.default_rng(3)
    plain = animehair.fan([0, 90, 180], 40, length=0.2, width=0.05)
    assert [lk.az for lk in plain] == [0.0, 90.0, 180.0] and {lk.el for lk in plain} == {40.0}
    varied = animehair.fan([0, 90, 180], [10, 20, 30], rng=rng, jitter=0.2, length=0.2, width=0.05)
    for lk, el in zip(varied, [10, 20, 30]):
        assert 0.2 * 0.8 <= lk.length <= 0.2 * 1.2 and 0.05 * 0.8 <= lk.width <= 0.05 * 1.2
        assert abs(lk.el - el) <= 3


def test_azimuth_and_elevation_name_the_front_the_left_and_the_top():
    assert np.allclose(animehair.direction(0, 0), (0, -1, 0))                 # the front is -y
    assert np.allclose(animehair.direction(90, 0), (1, 0, 0))                 # the person's left is +x
    assert np.allclose(animehair.direction(180, 0), (0, 1, 0))
    assert np.allclose(animehair.direction(0, 90), (0, 0, 1))


def test_a_lock_combed_from_the_forehead_to_a_low_bun_climbs_over_the_crown():
    d = animehair.direction(0, 20)                                            # the front hairline
    b = animehair.direction(180, -25)                                         # a bun low at the back
    m = animehair.over(d, b)
    assert np.linalg.norm(m) == pytest.approx(1.0)
    assert m[2] > 0.8                                                         # over the top, not under the chin
    near = animehair.direction(150, 0)
    assert animehair.over(near, b)[2] < 0.5                                   # a lock near the bun barely climbs
    r = 0.08
    straight = math.acos(float(d @ b)) * r
    assert animehair.arc(d, b, r) >= straight                                 # the way over is the longer way round
