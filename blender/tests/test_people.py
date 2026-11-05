# The bpy-free halves of realistic people: MakeHuman's age slider and the eyeball fit (lib/human.py), the cut and
# flare of clothes and the outline a belt is laid round (lib/garments.py), and the hem and strands of hair
# (lib/hair.py). Expected values are worked from the definitions, never with the code under test.
import math

import numpy as np
import pytest

from lib import garments, hair, human


# ---- human ----

def test_ages_land_on_makehumans_stops_and_run_straight_between_them():
    assert human.age_value(1) == 0.0
    assert human.age_value(11) == pytest.approx(0.1875)
    assert human.age_value(25) == pytest.approx(0.5)
    assert human.age_value(90) == pytest.approx(1.0)
    assert human.age_value(18) == pytest.approx(0.1875 + (18 - 11) / 14 * 0.3125)
    assert human.age_value(72) == pytest.approx(0.5 + (72 - 25) / 65 * 0.5)
    assert human.age_value(0) == 0.0 and human.age_value(120) == 1.0      # clamped


def test_a_sphere_is_found_from_a_cap_of_it():
    rng = np.random.default_rng(3)
    c, r = np.array([0.03, -0.11, 1.69]), 0.0125
    # only the front cap of an eye, as MakeHuman's helper is
    d = rng.normal(size=(200, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    d = d[d[:, 1] < -0.3]
    fc, fr = human.fit_sphere(c + d * r)
    assert np.allclose(fc, c, atol=1e-9)
    assert fr == pytest.approx(r)


# ---- garments ----

def test_a_skirt_flares_from_nothing_at_the_waist_to_its_amount_at_the_hem():
    sw = garments.flare(1.0, 0.1, amount=0.15, power=1.0)
    assert sw((0.0, -0.2, 1.0), {}) == 0.0
    assert sw((0.0, -0.2, 1.3), {}) == 0.0                 # above the waist: none
    assert sw((0.0, -0.2, 0.55), {}) == pytest.approx(0.075)
    assert sw((0.0, -0.2, 0.1), {}) == pytest.approx(0.15)
    assert sw((0.0, -0.2, -0.3), {}) == pytest.approx(0.15)  # past the hem: held


def test_pleats_fold_round_the_skirt_and_only_across_the_front_when_asked():
    sw = garments.flare(1.0, 0.0, amount=0.0, pleats=4, depth=0.01)
    # at the hem (u 1) a pleat's crest is depth * 1.3, its valley none
    crest_a = math.pi / 4                                   # |sin(4 a / 2)| = 1
    x, y = math.sin(crest_a), -math.cos(crest_a)            # angle a round from the front (-y) toward +x
    assert sw((x, y, 0.0), {}) == pytest.approx(0.013)
    assert sw((0.0, -1.0, 0.0), {}) == pytest.approx(0.0, abs=1e-12)
    front = garments.flare(1.0, 0.0, amount=0.0, pleats=4, depth=0.01, front_only=True)
    back_a = math.pi - math.pi / 4
    assert front((math.sin(back_a), -math.cos(back_a), 0.0), {}) == 0.0


def test_a_v_neck_opens_at_the_front_only_and_widens_upward():
    keep = garments.v_neck(1.3, 1.5, half_width=0.08, cross_x=0.0)
    assert keep((0.0, -0.1, 1.45), {}) is False             # in the V
    assert keep((0.0, -0.1, 1.29), {}) is True              # below it
    assert keep((0.0, 0.1, 1.45), {}) is True               # at the back
    assert keep((0.05, -0.1, 1.4), {}) is True              # half way up, the V is 0.04 wide either side
    assert keep((0.03, -0.1, 1.4), {}) is False
    assert garments.above(1.0)((0, 0, 1.01), {}) and not garments.above(1.0)((0, 0, 0.99), {})


def test_a_belts_outline_goes_round_the_furthest_points_of_its_slice():
    a = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    pts = np.column_stack([0.15 * np.cos(a), 0.1 * np.sin(a)])
    inner = 0.5 * pts                                      # points inside must not pull the band in
    ring = garments.outline(np.concatenate([pts, inner]), n=32)
    assert ring.shape == (32, 2)
    r = np.hypot(ring[:, 0] / 0.15, ring[:, 1] / 0.1)
    assert (r >= 1.0 - 1e-9).all()                          # never inside the slice: a band round it never cuts in
    assert r.max() < 1.05                                   # and hardly out from it


def test_an_outline_fills_a_sector_with_no_points_from_its_neighbours():
    a = np.linspace(0, 2 * np.pi, 200, endpoint=False)
    a = a[(a < 1.0) | (a > 1.6)]                           # a gap
    pts = np.column_stack([np.cos(a), np.sin(a)]) * 0.12
    ring = garments.outline(pts, n=24)
    assert not np.isnan(ring).any()
    assert np.allclose(np.hypot(*(ring - ring.mean(axis=0)).T), 0.12, atol=0.02)


# ---- hair ----

def test_a_hem_is_its_heights_at_the_front_sides_and_back_and_between_them():
    hem = hair.hem_profile(1.72, 1.58, 1.45)
    assert hem(0.0) == pytest.approx(1.72)
    assert hem(math.pi / 2) == pytest.approx(1.58)
    assert hem(-math.pi / 2) == pytest.approx(1.58)
    assert hem(math.pi) == pytest.approx(1.45)
    assert hem(math.pi / 4) == pytest.approx((1.72 + 1.58) / 2)
    assert 1.45 < hem(3 * math.pi / 4) < 1.58


def test_a_strand_is_a_flat_box_lying_on_its_surface():
    pts = np.array([(0, 0, 0), (0, 0, -0.05), (0, 0, -0.1)], float)
    nrm = np.array([(0, -1, 0)] * 3, float)                # the surface faces -y
    verts, faces = hair.ribbon(pts, nrm, [0.02, 0.01, 0.002], thickness=0.002)
    assert verts.shape == (12, 3) and len(faces) == 2 * 4 + 2
    first = verts[:4]
    assert np.ptp(first[:, 0]) == pytest.approx(0.02)       # across the surface
    assert np.ptp(first[:, 1]) == pytest.approx(0.002)      # through it
    assert np.allclose(first[:, 2], 0.0)
    assert np.ptp(verts[8:, 0]) == pytest.approx(0.002)     # tapered at the tip
