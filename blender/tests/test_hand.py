import math
from collections import Counter

import pytest

from lib import hand as H


def close(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_rotate_is_right_handed():
    assert close(H.rotate((1, 0, 0), (0, 0, 1), 90), (0, 1, 0))
    assert close(H.toward((0, 0, -1), (1, 0, 0), 90), (1, 0, 0))


@pytest.mark.parametrize("name", sorted(H.POSES))
def test_every_named_pose_resolves(name):
    p = H.resolve(name)
    assert len(p["fingers"]) == 4 and all(len(f) == 4 for f in p["fingers"])
    assert len(p["thumb"]) == 4


def test_a_pose_can_start_from_another():
    p = H.resolve({"base": "fist", "thumb": (30, 20, 0, 0)})
    assert p["fingers"] == H.resolve("fist")["fingers"]


def test_bad_poses_are_refused():
    with pytest.raises(KeyError):
        H.resolve("wave hello")
    with pytest.raises(ValueError):
        H.resolve({"fingers": [(0, 0, 0, 0)] * 3})


def test_a_straight_finger_runs_down_its_length_and_a_bent_knuckle_curls_to_the_palm():
    base, lengths = H.FINGERS[1][1], H.FINGERS[1][2]
    pts, _, _ = H.finger(1, (0, 0, 0, 0))
    assert close(pts[-1], H.add(base, (0, 0, -sum(lengths))), 1e-9)
    pts, _, frames = H.finger(1, (0, 90, 0, 0))
    assert close(frames[0][0], (0, -1, 0), 1e-9)            # past the knuckle it points out of the palm (-Y)


@pytest.mark.parametrize("name", sorted(H.POSES))
def test_the_thumb_stays_clear_of_the_fingers(name):
    assert H.thumb_gap(name) >= H.GAP - 1e-6


def test_a_pinch_brings_the_thumb_tip_to_the_index_tip():
    p = H.resolve("pinch")
    ipts, irs, _ = H.finger(0, p["fingers"][0])
    tpts, trs, _ = H.thumb(p["thumb"])
    gap = H.length(H.sub(ipts[-1], tpts[-1])) - irs[-1] - trs[-1]
    assert H.GAP - 0.005 <= gap <= H.GAP + 0.03


def _closed(verts, faces):
    edges = Counter()
    for f in faces:
        assert len(set(f)) == len(f) >= 3
        for i in range(len(f)):
            edges[frozenset((f[i], f[(i + 1) % len(f)]))] += 1
    return all(n == 2 for n in edges.values()) and all(0 <= i < len(verts) for f in faces for i in f)


@pytest.mark.parametrize("detail", ["full", "mitten"])
@pytest.mark.parametrize("name", sorted(H.POSES))
def test_every_cage_is_one_closed_mesh(name, detail):
    parts = H.cage(name, detail)
    assert list(parts) == ["hand"]
    assert _closed(*parts["hand"])


def test_a_mitten_keeps_a_pointing_index_apart():
    fist, point = H.cage("fist", "mitten")["hand"], H.cage("point", "mitten")["hand"]
    assert len(point[0]) > len(fist[0])
    assert len(H.cage("fist", "full")["hand"][0]) > len(fist[0])


def test_grips_close_round_a_channel_in_front_of_the_palm():
    clear = {}
    for name in ("fist", "grip", "wrap"):
        (x, y, z), clear[name] = H.anchor(name)
        assert y < -H.PALM["half_thick"] * 0.85
        assert -0.8 < z < -0.2
    assert 0 < clear["fist"] < clear["grip"] < clear["wrap"]


def test_anchors_default_to_the_poses_own():
    assert H.anchor("point")[0] == H.anchor("point", "tip")[0]
    assert H.anchor("pinch")[0] == H.anchor("pinch", "pinch")[0]
    assert H.anchor("rest")[0] == H.anchor("rest", "palm")[0]
    with pytest.raises(KeyError):
        H.anchor("grip", "elbow")
    with pytest.raises(ValueError):
        H.anchor("flat", "grip")
