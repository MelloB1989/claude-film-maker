import math

import numpy as np
import pytest

from lib import boat, landscape, water, wayside


def test_puddle_outline_is_a_closed_irregular_rim_round_its_center():
    rim = water.puddle_outline((2.0, -1.0), 0.5, seed=3, n=32)
    assert rim.shape == (32, 2)
    r = np.hypot(rim[:, 0] - 2.0, rim[:, 1] + 1.0)
    assert r.min() >= 0.5 * 0.45 - 1e-9 and r.max() < 0.5 * 1.6
    assert r.std() > 0.01                       # not a circle
    # deterministic, and a new seed is a new puddle
    assert np.allclose(rim, water.puddle_outline((2.0, -1.0), 0.5, seed=3, n=32))
    assert not np.allclose(rim, water.puddle_outline((2.0, -1.0), 0.5, seed=4, n=32))


def test_puddle_outline_stretches_along_its_angle():
    rim = water.puddle_outline((0, 0), 1.0, wobble=0.0, stretch=2.0, angle=math.pi / 2)
    assert np.ptp(rim[:, 1]) == pytest.approx(4.0, abs=1e-6) and np.ptp(rim[:, 0]) == pytest.approx(2.0, abs=0.02)


def test_hull_is_symmetric_flat_bottomed_and_within_its_beam():
    v, f = boat.hull(5.0, 1.2, 0.45, n=20)
    assert len(v) == 20 * 8 and all(max(face) < len(v) for face in f)
    assert np.abs(v[:, 1]).max() <= 0.6 + 1e-9
    # mirror image across y
    m = v * (1, -1, 1)
    assert all(np.min(np.linalg.norm(v - p, axis=1)) < 1e-9 for p in m)
    # amidships the floor is flat: both bottom corners at one height, below the waterline; the sheer above it
    b, w, zb, zs = boat.hull_section(0.4, 1.2, 0.45)
    assert b > 0.25 and w > b and zb < 0 < zs
    # the bow rises and narrows to its stem
    b1, w1, zb1, zs1 = boat.hull_section(1.0, 1.2, 0.45)
    assert w1 < 0.1 and zb1 > zb and zs1 > zs


def test_float_pose_is_small_smooth_and_still_when_calm():
    ts = np.linspace(0, 20, 481)
    poses = np.array([boat.float_pose(t) for t in ts])
    assert np.abs(poses[:, 0]).max() <= 0.018 + 1e-9
    assert np.abs(poses[:, 1]).max() <= math.radians(1.6) + 1e-9
    assert np.abs(np.diff(poses[:, 0])).max() < 0.003          # no jumps frame to frame
    assert boat.float_pose(3.3, calm=0.0) == (0.0, 0.0, 0.0)


def test_drift_pose_holds_then_follows_its_path_bow_first():
    path = [(0, 0), (10, 0), (20, 10)]
    assert boat.drift_pose(-1.0, path, 0.0, 5.0)[:2] == pytest.approx((0, 0))
    assert boat.drift_pose(9.0, path, 0.0, 5.0)[:2] == pytest.approx((20, 10))
    x, y, h = boat.drift_pose(0.5, path, 0.0, 5.0)
    assert 0 < x < 10 and abs(y) < 0.6 and abs(h) < 0.2
    # pushed off: further along in the first half of the time than the second
    a = boat.drift_pose(2.5, path, 0.0, 5.0)
    assert a[0] > 10
    assert boat.path_point(path, 0.5) == pytest.approx((10, 0))


def test_stave_layout_rings_the_post_with_a_ragged_crown():
    st = wayside.stave_layout(0.14, 9, 0.6, seed=2)
    assert len(st) == 9
    share = 2 * math.pi * 0.14 / 9
    assert all(w < share for _, w, _ in st)
    tops = [t for *_, t in st]
    assert max(tops) <= 0.6 and min(tops) >= 0.55 and len(set(tops)) == 9


def test_grid_faces_cover_the_grid():
    f = landscape.grid_faces(4, 3)
    assert len(f) == 3 * 2 and f[0] == (0, 1, 5, 4) and max(max(q) for q in f) == 11


def test_fbm_is_deterministic_and_bounded():
    X, Y = np.meshgrid(np.linspace(-100, 100, 40), np.linspace(-100, 100, 40))
    a = landscape.fbm(X, Y, seed=2)
    assert a.shape == X.shape and np.abs(a).max() <= 1.0 and a.std() > 0.1
    assert np.allclose(a, landscape.fbm(X, Y, seed=2)) and not np.allclose(a, landscape.fbm(X, Y, seed=3))


def test_conifer_stands_on_its_base_to_its_height():
    v, f = landscape.conifer_mesh((3.0, 4.0, 1.0), 10.0, tiers=5, sides=7)
    assert v[:, 2].max() == pytest.approx(11.0) and v[:, 2].min() == pytest.approx(0.7)
    assert all(max(face) < len(v) for face in f)
    assert np.abs(v[:, 0] - 3.0).max() < 10 * 0.28 * 1.3


def test_scatter_keeps_its_gap_and_its_mask():
    pts = landscape.scatter(200, (0, 50), (0, 50), seed=1, min_gap=2.0, keep=lambda x, y: x > 10)
    assert 50 < len(pts) <= 200 and (pts[:, 0] > 10).all()
    d = np.hypot(*(pts[:, None, :] - pts[None, :, :]).transpose(2, 0, 1))
    np.fill_diagonal(d, 99)
    assert d.min() >= 2.0
