import numpy as np
import pytest

from lib import minka


def _normal(verts, face):
    p = np.asarray([verts[i] for i in face], float)
    n = np.zeros(3)
    for a, b in zip(p, np.roll(p, -1, axis=0)):      # Newell's method: right for any planar polygon
        n += np.cross(a, b)
    return n / np.linalg.norm(n)


def test_hip_gable_roof_faces_are_flat_and_face_out():
    verts, faces, pts = minka.hip_gable_roof(2.2, 1.9, 2.1, 3.5)
    assert len(faces) == 6
    middle = np.array([0.0, 0.0, 2.1])
    for face in faces:
        p = np.asarray([verts[i] for i in face], float)
        n = _normal(verts, face)
        assert np.abs((p - p[0]) @ n).max() < 1e-9               # planar
        assert (p.mean(axis=0) - middle) @ n > 0                 # outward
    assert pts["zg"] == pytest.approx(3.5 - 1.4 * 0.45)
    assert 0 < pts["xr"] < 2.2


def test_hip_gable_roof_hips_are_as_steep_as_its_slopes():
    X, Y, ze, zt = 2.2, 1.9, 2.1, 3.5
    _, _, pts = minka.hip_gable_roof(X, Y, ze, zt)
    side = (zt - ze) / Y
    hip = (pts["zg"] - ze) / (X - pts["xr"])
    assert hip == pytest.approx(side)


def test_gables_stand_upright():
    verts, faces, _ = minka.hip_gable_roof(2.2, 1.9, 2.1, 3.5)
    for face in faces[4:]:
        assert abs(_normal(verts, face)[2]) < 1e-9


def test_chochin_profile_is_round_pinched_at_its_hoops_and_open_at_its_caps():
    prof = minka.chochin_profile(0.16, 0.44, 13)
    r = np.array([p[0] for p in prof])
    z = np.array([p[1] for p in prof])
    assert z[0] == pytest.approx(-0.22) and z[-1] == pytest.approx(0.22)
    assert np.all(np.diff(z) > 0)
    assert r.max() <= 0.16 + 1e-9 and r.max() > 0.15
    assert r[0] > 0.03                                           # an opening for the cap, not a point
    hoops, between = r[0::2], r[1::2]                            # even points on a hoop, odd between
    assert np.all(between[: len(between) // 2] > hoops[: len(between) // 2])   # the paper bulges out between them


def test_material_falls_back():
    m = {"wall": "W", "thatch": "T", "door": "D"}
    assert minka.material(m, "plaster") == "W"
    assert minka.material(m, "ridge") == "T"
    assert minka.material(m, "lattice") == "W"                   # lattice -> post -> wall
    assert minka.material({**m, "post": "P"}, "lattice") == "P"


def test_parts_gather_boxes_beams_and_cylinders_per_material():
    P = minka.Parts()
    P.box("wall", (0, 0, 0), (2, 1, 0.5))
    P.box("wall", (5, 0, 0), (1, 1, 1), rot_z=0.3)
    P.cyl("rope", (0, 0, 0), (0, 0, 1), 0.1, n=6)
    P.beam("post", (0, 0, 0), (3, 4, 0), 0.2, 0.1)
    assert len(P.v["wall"]) == 16 and len(P.f["wall"]) == 12
    assert max(max(f) for f in P.f["wall"]) == 15                # the second box's faces index its own points
    assert len(P.v["rope"]) == 12 and len(P.f["rope"]) == 6 + 2
    beam = np.asarray(P.v["post"])
    assert np.ptp(beam @ np.array([0.6, 0.8, 0.0])) == pytest.approx(5.0)   # 5 long along a-b
    assert np.ptp(beam[:, 2]) == pytest.approx(0.1)                       # `h` deep, upright


def test_hip_gable_roof_eaves_stay_where_asked():
    verts, _, _ = minka.hip_gable_roof(2.2, 1.9, 2.1, 3.5)
    v = np.asarray(verts)
    assert v[:, 0].max() == pytest.approx(2.2) and v[:, 1].max() == pytest.approx(1.9)
    assert v[:, 2].min() == pytest.approx(2.1) and v[:, 2].max() == pytest.approx(3.5)
