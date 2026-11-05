# The bpy-free half of anime faces (lib/animeface.py): the lids' curves, the strokes' splines and the drawing itself.
# Expected values are worked from the definitions, not with the code under test.
import math

import numpy as np
import pytest

from lib import animeface as af


def test_the_lids_meet_at_the_corners_and_the_upper_one_peaks_where_asked():
    e = af.Eye(width=0.6, height=0.3, peak=0.4, round=1.0, lower=0.5)
    t = np.array([0.0, 0.4, 1.0])
    top, bottom = af.lids(e, t)
    assert top[0] == pytest.approx(0.0, abs=1e-12) and top[2] == pytest.approx(0.0, abs=1e-12)
    assert bottom[0] == pytest.approx(0.0, abs=1e-12) and bottom[2] == pytest.approx(0.0, abs=1e-12)
    assert top[1] == pytest.approx(0.3)                    # sin(pi * 0.4**q) = 1 when 0.4**q = 0.5
    ts = np.linspace(0, 1, 201)
    tops, bottoms = af.lids(e, ts)
    assert ts[np.argmax(tops)] == pytest.approx(0.4, abs=0.01)
    assert (bottoms[1:-1] < 0).all() and bottoms.min() == pytest.approx(-0.15, rel=0.01)


def test_a_scowl_flattens_the_inner_lid_and_a_droop_lowers_the_outer():
    plain = af.Eye()
    ts = np.array([0.2, 0.9])
    top, _ = af.lids(plain, ts)
    scowl, _ = af.lids(af.Eye(slant=0.7), ts)
    droop, _ = af.lids(af.Eye(droop=0.5), ts)
    # a scowl scales the lid by 1 - slant (1 - t)^1.5: much at the inner end, hardly at the outer
    assert scowl == pytest.approx(top * (1 - 0.7 * (1 - ts) ** 1.5))
    assert scowl[0] / top[0] < 0.6 and scowl[1] / top[1] > 0.97
    # a droop leaves the inner part (before t 0.3) alone and lowers the outer
    assert droop[1] < top[1] and droop[0] == pytest.approx(top[0])


def test_a_spline_runs_through_its_points():
    pts = [(0.0, 0.0), (0.5, 0.3), (1.0, 0.0)]
    curve, at = af.spline(pts, k=10)
    for i, p in enumerate(pts):
        j = int(np.argmin(np.abs(at - i)))
        assert curve[j] == pytest.approx(p)
    assert curve[:, 1].max() >= 0.3 - 1e-9                 # bowed through the middle point, not cut under it
    two, _ = af.spline([(0, 0), (1, 1)], k=4)
    assert np.allclose(two[:, 0], two[:, 1])              # two points: a straight line


def test_a_drawing_is_transparent_but_for_its_features_and_eye_matches_eye():
    face = af.Face(eye=af.Eye(), strokes=[af.Stroke(((0.1, 0.35), (0.8, 0.4)), width=0.05, mirror=True)])
    img = af.drawing(face, extent=(-1.0, 1.0, -0.6, 0.6), res=200)
    assert img.shape == (240, 400, 4)
    a = img[..., 3]
    assert a.min() == 0.0 and a.max() == pytest.approx(1.0)
    assert a[5, 200] == 0.0                                # between the eyes, low: bare skin
    # the iris's middle (the pupil there) at an eye's centre, drawn opaque and dark
    e = face.eye
    for side in (1, -1):
        x = side * 0.5 + side * e.iris_at[0]
        col = int((x + 1.0) * 200)
        row = int((0.6 + e.iris_at[1]) * 200)
        assert a[row, col] == pytest.approx(1.0)
        assert img[row, col, :3].max() < 0.05
    # the two eyes and the mirrored strokes make a symmetric drawing
    assert np.allclose(a, a[:, ::-1], atol=0.02)


def test_a_strokes_width_is_drawn_to_scale():
    s = af.Stroke(((-0.5, 0.0), (0.5, 0.0)), width=0.1, taper=(1.0, 1.0))
    img = af.drawing(af.Face(eye=af.Eye(width=0.01, height=0.001, flick=(0.0, 0.0, 0.0), lower_lash=None), strokes=[s]),
                     extent=(-1.0, 1.0, -0.2, 0.2), res=400)
    col = img[:, 400, 3]                                   # a column through the stroke's middle
    covered = col.sum() / 400                              # in eye units
    assert covered == pytest.approx(0.1, abs=0.01)
