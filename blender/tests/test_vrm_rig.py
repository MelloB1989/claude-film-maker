import math

import numpy as np
import pytest

from lib import vrm_rig

FACE_KEYS = ["Fcl_ALL_Angry", "Fcl_BRW_Angry", "Fcl_BRW_Sorrow", "Fcl_EYE_Angry", "Fcl_EYE_Close", "Fcl_EYE_Close_L",
             "Fcl_EYE_Close_R", "Fcl_MTH_Angry", "Fcl_MTH_Close", "Fcl_MTH_Sorrow"]


def test_resolve_names_and_patterns_any_case_summing_overlaps():
    assert vrm_rig.resolve(FACE_KEYS, {"Fcl_BRW_Angry": 1.0, "fcl_eye_angry": 0.8}) == {"Fcl_BRW_Angry": 1.0,
                                                                                         "Fcl_EYE_Angry": 0.8}
    # a pattern takes every key it matches; one matched twice adds up
    got = vrm_rig.resolve(FACE_KEYS, {"*EYE_Close*": 0.2, "Fcl_EYE_Close": 0.1})
    assert got == pytest.approx({"Fcl_EYE_Close": 0.3, "Fcl_EYE_Close_L": 0.2, "Fcl_EYE_Close_R": 0.2})
    assert set(vrm_rig.resolve(FACE_KEYS, {"*_Angry": 1.0})) == {"Fcl_ALL_Angry", "Fcl_BRW_Angry", "Fcl_EYE_Angry",
                                                                  "Fcl_MTH_Angry"}
    with pytest.raises(KeyError, match="Fcl_MTH"):
        vrm_rig.resolve(FACE_KEYS, {"Fcl_MTH_Grin": 1.0})


def test_rotation_and_swing():
    r = vrm_rig.rotation((0, 0, 1), 90)
    assert r @ np.array([1.0, 0, 0]) == pytest.approx([0, 1, 0])
    assert np.linalg.det(r) == pytest.approx(1.0) and r @ r.T == pytest.approx(np.eye(3))
    # a strand hanging down, swung 30 degrees toward the character's left (+x)
    s = vrm_rig.swing((0, 0, -1), (1, 0, 0), 30)
    assert s @ np.array([0, 0, -1.0]) == pytest.approx([0.5, 0, -math.cos(math.pi / 6)])
    # ... and toward its right, the other way
    assert (vrm_rig.swing((0, 0, -1), (-1, 0, 0), 30) @ np.array([0, 0, -1.0]))[0] == pytest.approx(-0.5)
    # a direction swung toward itself goes nowhere
    assert vrm_rig.swing((0, 0, -1), (0, 0, -2), 40) == pytest.approx(np.eye(3))


def test_shares_put_most_of_a_swing_at_the_root():
    for n in (1, 2, 3, 4, 6):
        s = vrm_rig.shares(n)
        assert s.sum() == pytest.approx(1.0) and len(s) == n
        assert all(a >= b for a, b in zip(s, s[1:]))
    assert vrm_rig.shares(4, root=0.55)[0] == pytest.approx(0.55)
    assert len(vrm_rig.shares(0)) == 0


def test_curl_to_round_lays_each_joint_on_the_grip():
    # a straight finger 2 cm past the grip's middle and 2.4 cm off it, three bones 3.5, 2.2, 1.6 cm long
    joints = [(0.02, -0.024), (0.055, -0.024), (0.077, -0.024), (0.093, -0.024)]
    turns = vrm_rig.curl_to_round(joints, (0.0, 0.0), 0.017, step=0.25)
    assert all(t > 0 for t in turns)                            # each bone folds toward the palm
    at, total = np.array(joints[0]), 0.0
    for (a, b), t in zip(zip(joints, joints[1:]), turns):
        seg = np.subtract(b, a)
        total += t
        ang = math.atan2(seg[1], seg[0]) + math.radians(total)
        at = at + np.linalg.norm(seg) * np.array([math.cos(ang), math.sin(ang)])
        assert np.linalg.norm(at) == pytest.approx(0.017, abs=0.0006)   # on the round, a step's error at most
    # a finger already inside the round does not curl; one too far to reach it folds as far as it can
    assert vrm_rig.curl_to_round([(0.0, 0.005), (0.004, 0.005)], (0.0, 0.0), 0.02) == [0.0]
    far = vrm_rig.curl_to_round([(0.0, -0.2), (0.03, -0.2)], (0.0, 0.0), 0.017, most=60)
    assert far[0] == pytest.approx(60.0, abs=1.0)


def test_stretch_lets_a_hem_down_and_flares_it():
    # a skirt's ring at the knee (0.55) and its hem (0.43), 0.2 from the middle
    ring = [(0.2 * math.cos(a), 0.2 * math.sin(a), z) for z in (0.43, 0.55, 0.8) for a in np.linspace(0, 6, 6)]
    out = vrm_rig.stretch(ring, 0.55, 0.08, flare=0.3)
    z = out[:, 2]
    assert z.min() == pytest.approx(0.08)
    above = np.isclose(np.array(ring)[:, 2], 0.8)
    assert out[above] == pytest.approx(np.array(ring)[above])
    hem = out[np.isclose(z, 0.08)]
    assert np.hypot(hem[:, 0], hem[:, 1]) == pytest.approx(0.2 * 1.3)          # flared by 0.3 at the hem
    knee = out[np.isclose(z, 0.55)]
    assert np.hypot(knee[:, 0], knee[:, 1]) == pytest.approx(0.2)               # and not at all where it starts
    # nothing below `top`: nothing moves
    assert vrm_rig.stretch(ring, 0.2, 0.0, flare=1.0) == pytest.approx(np.array(ring))


def test_box_blur_keeps_the_mean_and_flattens_a_check():
    img = np.indices((40, 40)).sum(0) % 2 * 1.0               # a fine check
    b = vrm_rig.box_blur(img, 3)
    assert b.shape == img.shape
    assert b[5:-5, 5:-5] == pytest.approx(0.5, abs=0.04)
    assert vrm_rig.box_blur(img, 0) == pytest.approx(img)


def test_flatten_turns_a_plaid_one_grey_and_keeps_alpha():
    h, w = 64, 64
    yy, xx = np.indices((h, w))
    plaid = 0.5 + 0.3 * ((xx // 2 + yy // 2) % 2)              # small checks
    px = np.zeros((h, w, 4))
    px[..., :3] = plaid[..., None] * (0.9, 0.8, 0.7)
    px[..., 3] = 1.0
    px[:, :8, 3] = 0.0                                          # a transparent margin
    out = vrm_rig.flatten(px, keep=0.3, blur=0.1)
    grey = out[..., 0]
    assert out[..., 0] == pytest.approx(out[..., 1]) and out[..., 1] == pytest.approx(out[..., 2])
    inner = grey[8:-8, 16:-8]
    assert inner.max() - inner.min() < 0.05                    # the checks gone
    assert grey.min() >= 0.7 - 1e-9 and grey.max() <= 1.0     # within keep of white
    assert out[..., 3] == pytest.approx(px[..., 3])
    # the islands' edges are not darkened by the transparent texels beside them
    assert grey[30, 8] == pytest.approx(grey[30, 30], abs=0.05)
    assert vrm_rig.flatten(px, keep=0.0)[..., :3] == pytest.approx(1.0)


def test_raster_covers_a_triangle_by_its_texel_centres():
    m = vrm_rig.raster([[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]], 10, 10)
    assert m.shape == (10, 10)
    assert m[0, 0] and m[0, 8] and m[8, 0] and not m[9, 9] and not m[5, 5]
    assert m.sum() == 55                                       # the centres on or under the diagonal
    # rows run up v: a triangle at the top of UV space marks the last rows
    top = vrm_rig.raster([[(0.0, 0.8), (1.0, 0.8), (0.5, 1.0)]], 10, 10)
    assert top[9].any() and not top[:7].any()
    grown = vrm_rig.raster([[(0.4, 0.4), (0.6, 0.4), (0.5, 0.6)]], 10, 10, grow=1)
    assert grown.sum() > vrm_rig.raster([[(0.4, 0.4), (0.6, 0.4), (0.5, 0.6)]], 10, 10).sum()
    assert not vrm_rig.raster([[(2.0, 2.0), (3.0, 2.0), (2.0, 3.0)]], 10, 10).any()   # off the texture


def test_resample_and_along():
    path = [(0, 0, 0), (1, 0, 0), (1, 2, 0)]
    r = vrm_rig.resample(path, 4)
    assert r[0] == pytest.approx([0, 0, 0]) and r[-1] == pytest.approx([1, 2, 0])
    assert np.linalg.norm(np.diff(r, axis=0), axis=1) == pytest.approx([1.0, 1.0, 1.0])
    assert vrm_rig.along(path, [0.0, 1.0, 3.0], 4) == pytest.approx([0.0, 1.0, 2.0, 3.0])
    assert vrm_rig.along(path, 0.04, 4) == 0.04


def test_ribbon_lies_flat_on_its_surface():
    pts = [(x, 0.0, 0.0) for x in np.linspace(0, 0.3, 5)]
    nrm = [(0.0, 0.0, 1.0)] * 5
    verts, faces = vrm_rig.ribbon(pts, nrm, 0.04, 0.004)
    assert verts.shape == (20, 3) and len(faces) == 4 * 4 + 2
    assert verts[:, 2].min() == pytest.approx(0.0) and verts[:, 2].max() == pytest.approx(0.004)
    assert np.ptp(verts[:, 1]) == pytest.approx(0.04)          # across the run, on the surface
    assert all(len(set(f)) == 4 and max(f) < 20 for f in faces)
    # one width per point
    v2, _ = vrm_rig.ribbon(pts, nrm, [0.06, 0.05, 0.04, 0.04, 0.04], 0.004)
    assert np.ptp(v2[:4, 1]) == pytest.approx(0.06) and np.ptp(v2[-4:, 1]) == pytest.approx(0.04)


def test_relax_points_irons_a_crumple_and_leaves_the_rest():
    # a ring of 12 points round z, every other one pushed out (a crumpled sleeve); one more point off it, fixed
    ang = np.linspace(0, 2 * np.pi, 12, endpoint=False)
    r = np.where(np.arange(12) % 2 == 0, 1.0, 1.3)
    ring = np.c_[r * np.cos(ang), r * np.sin(ang), np.zeros(12)]
    pts = np.vstack([ring, [[5.0, 5.0, 5.0]]])
    edges = [(i, (i + 1) % 12) for i in range(12)]
    out = vrm_rig.relax_points(pts, edges, np.arange(12), iterations=4)
    radii = np.linalg.norm(out[:12, :2], axis=1)
    assert np.ptp(radii) < 0.3 * np.ptp(r)          # the crumple mostly gone
    assert np.allclose(out[12], pts[12])             # a point not moving stays
    assert np.allclose(vrm_rig.relax_points(pts, edges, [], iterations=3), pts)
