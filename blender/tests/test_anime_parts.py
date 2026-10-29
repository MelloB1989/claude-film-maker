# The bpy-free halves of the anime parts: lofted rings (lib/shapes.py), the drawn face's outlines (lib/anime.py), the
# ridges and banks of a landscape (lib/landscape.py), and a lightning strike's flash and fork (lib/toon.py).
import math

import numpy as np
import pytest

from lib import anime, landscape, shapes, toon


# ---- shapes ----

def test_frames_are_orthonormal_and_follow_the_path():
    path = np.array([(0, 0, 0), (1, 0, 0.2), (2, 0.5, 0.6), (3, 1.5, 0.7)], float)
    t, u, v = shapes.frames(path)
    for i in range(len(path)):
        assert np.linalg.norm(t[i]) == pytest.approx(1)
        assert np.linalg.norm(u[i]) == pytest.approx(1)
        assert np.linalg.norm(v[i]) == pytest.approx(1)
        assert np.dot(t[i], u[i]) == pytest.approx(0, abs=1e-9)
        assert np.dot(t[i], v[i]) == pytest.approx(0, abs=1e-9)
    # a straight path along x with z up: u across (y), v up (z)
    t, u, v = shapes.frames(np.array([(0, 0, 0), (1, 0, 0), (2, 0, 0)], float))
    assert np.allclose(np.abs(u), [(0, 1, 0)] * 3)
    assert np.allclose(np.abs(v), [(0, 0, 1)] * 3)


def test_an_elliptic_loft_has_rings_of_its_radii_round_each_point():
    path = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    rings = shapes.loft_points(path, [0.3, 0.2, 0.1], [0.15, 0.1, 0.05], n=8)
    assert rings.shape == (3, 8, 3)
    for i, (ru, rv) in enumerate([(0.3, 0.15), (0.2, 0.1), (0.1, 0.05)]):
        ring = rings[i]
        assert np.allclose(ring.mean(axis=0), path[i], atol=1e-9)        # centred on the path
        assert np.allclose(ring[:, 0], path[i][0])                       # square to it
        assert np.abs(ring[:, 1]).max() == pytest.approx(ru)             # across
        assert np.abs(ring[:, 2]).max() == pytest.approx(rv)             # up


def test_a_loft_offset_shifts_its_rings():
    path = [(0, 0, 0), (1, 0, 0)]
    plain = shapes.loft_points(path, 0.1, n=6)
    moved = shapes.loft_points(path, 0.1, n=6, offset=[(0.0, 0.05), (0.0, 0.05)])
    assert np.allclose(np.abs((moved - plain)[..., 2]), 0.05)


# ---- the face's outlines ----

def test_an_eye_runs_corner_to_corner_its_lid_above_and_the_lower_lid_below():
    w, h = 0.04, 0.016
    eye = anime.eye_outline(w, h, n=10)
    assert len(eye) == 10 + 8
    assert eye[0] == pytest.approx((-w / 2, 0.0))          # the inner corner
    assert eye[9][0] == pytest.approx(w / 2)               # the outer corner, raised
    assert eye[9][1] == pytest.approx(0.15 * h)
    upper, lower = eye[:10], eye[10:]
    assert upper[1:-1, 1].min() > 0
    assert upper[:, 1].max() <= h * 1.01
    # every point of the lower lid lies below the straight line between the corners
    chord = 0.15 * h * (lower[:, 0] + w / 2) / w
    assert (lower[:, 1] < chord).all()


def test_a_band_is_as_wide_as_asked_along_its_line():
    pts = np.array([(0, 0), (1, 0), (2, 0)], float)
    band = anime.band_along(pts, [0.2, 0.1, 0.0])
    assert band.shape == (6, 2)
    assert np.allclose(band[:3, 1], [0.1, 0.05, 0.0])      # one side
    assert np.allclose(band[3:, 1], [-0.0, -0.05, -0.1])   # the other, back again
    assert np.allclose(band[:3, 0], pts[:, 0])


# ---- landscape ----

def test_a_ridge_is_the_same_for_its_seed_and_trees_only_add_height():
    xs = np.linspace(-200, 200, 400)
    a = landscape.ridge_profile(xs, 120.0, 40.0, seed=3)
    assert np.allclose(a, landscape.ridge_profile(xs, 120.0, 40.0, seed=3))
    assert not np.allclose(a, landscape.ridge_profile(xs, 120.0, 40.0, seed=4))
    # rolling summits about the height: 0.1 to 1.25 of it with the one high peak
    assert a.min() >= 0.1 * 40.0 - 1e-9
    assert a.max() <= 1.25 * 40.0 + 1e-9
    t = landscape.ridge_profile(xs, 120.0, 40.0, seed=3, trees=2.0)
    assert (t >= a - 1e-9).all() and (t - a).max() <= 2.0 + 1e-9


def test_the_bank_meets_the_water_at_its_edge_and_rises_inland():
    edge, water = -5.6, -0.45
    for y in (-3.0, 0.0, 4.0):
        e = landscape.bank_edge(y, edge)
        assert landscape.bank_height(e + 1.0, y, edge, water) == pytest.approx(water - 0.05)   # in the water: flat
        assert landscape.bank_height(e, y, edge, water) == pytest.approx(water - 0.05)
        inland = landscape.bank_height(e - 2.6, y, edge, water)                                # a full slope in
        assert water - 0.05 + 0.85 - 0.25 <= inland <= water - 0.05 + 0.85 + 0.25


# ---- lightning ----

def test_a_strike_whites_out_for_one_frame_then_flickers_and_dies():
    fps = 24.0
    assert toon.strike(-0.01, fps) == 0.0
    assert toon.strike(0.0, fps) == 1.0
    assert toon.strike(0.5 / fps, fps) == 1.0
    after = [toon.strike(k / fps, fps) for k in range(1, 3)]
    assert 0 < after[1] < after[0] < 1                     # falling after the white-out
    dip = toon.strike(0.12, fps)
    flicker = toon.strike(0.15, fps)
    assert flicker > dip                                   # the second flicker
    assert flicker == pytest.approx(0.8 * math.exp(-(0.15 - 1 / fps) * 18) + 0.8 * math.exp(-0.025 * 10))
    assert toon.strike(0.8, fps) < 0.01                    # gone


def test_a_bolt_runs_end_to_end_in_its_plane_and_is_the_same_for_its_seed():
    start, end = (6.0, 60.0, 24.0), (8.6, 60.0, 3.0)
    p = toon.bolt_path(start, end, seed=11, depth=5)
    assert p.shape == (2 ** 5 + 1, 3)
    assert np.allclose(p[0], start) and np.allclose(p[-1], end)
    assert np.allclose(p[:, 1], 60.0)                      # flat in x-z, facing the camera
    assert np.allclose(p, toon.bolt_path(start, end, seed=11, depth=5))
    assert not np.allclose(p, toon.bolt_path(start, end, seed=12, depth=5))
    # jagged, but no point strays further from the straight line than the displacements could carry it
    d = np.array(end) - np.array(start)
    side = np.array([-d[2], 0, d[0]]) / np.linalg.norm(d)
    off = np.abs((p - np.array(start)) @ side)
    assert off.max() > 0.05
    assert off.max() < 0.22 * np.linalg.norm(d) * 2
