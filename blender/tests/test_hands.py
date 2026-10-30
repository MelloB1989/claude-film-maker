"""The hands core without Blender: hand shapes (lib/vrm.py), grips that wrap and pinch (lib/vrm_rig.py), and the arm's
motion helpers (lib/vrm_anim.py: arcs, follow-through, finger stagger, forearm twist), on a VRoid-like hand."""
import math

import numpy as np
import pytest

from lib import vrm, vrm_rig
from lib import vrm_anim as va

# a VRoid left hand at rest (T-pose, palm down, fingers along +x), metres in the character's frame
_HAND = {
    "leftHand": ((0.501, 0.024, 1.174), (0.548, 0.024, 1.174)),
    "leftThumbMetacarpal": ((0.504, 0.009, 1.165), (0.536, -0.018, 1.163)),
    "leftThumbProximal": ((0.536, -0.019, 1.163), (0.556, -0.035, 1.162)),
    "leftThumbDistal": ((0.556, -0.035, 1.162), (0.566, -0.043, 1.162)),
}
for _f, _y, _l in (("Index", 0.006, (0.030, 0.019, 0.012)), ("Middle", 0.022, (0.033, 0.021, 0.013)),
                   ("Ring", 0.036, (0.031, 0.020, 0.012)), ("Little", 0.050, (0.028, 0.017, 0.010))):
    _x = 0.56
    for _j, _len in zip(("Proximal", "Intermediate", "Distal"), _l):
        _HAND[f"left{_f}{_j}"] = ((_x, _y, 1.181), (_x + _len, _y, 1.181))
        _x += _len
_PARENT = {"leftHand": None, "leftThumbMetacarpal": "leftHand", "leftThumbProximal": "leftThumbMetacarpal",
           "leftThumbDistal": "leftThumbProximal"}
for _f in ("Index", "Middle", "Ring", "Little"):
    _PARENT.update({f"left{_f}Proximal": "leftHand", f"left{_f}Intermediate": f"left{_f}Proximal",
                    f"left{_f}Distal": f"left{_f}Intermediate"})


class FakeHand:
    def has(self, n):
        return n in _HAND

    def rest(self, n, tail=False):
        return np.array(_HAND[n][1 if tail else 0], float)


def posed(turns):
    order = list(_HAND)
    heads = {b: np.array(_HAND[b][0]) for b in order}
    t = {b: (np.asarray(v) if np.shape(v) == (3, 3) else vrm.euler(v)) for b, v in turns.items()}
    tot, hd = va.fk(order, _PARENT, heads, t)
    tails = {b: hd[b] + tot[b] @ (np.array(_HAND[b][1]) - heads[b]) for b in order}
    return hd, tails


def curl_deg(pose, finger):
    return sum(pose[f"left{finger}{j}"][1] for j in ("Proximal", "Intermediate", "Distal"))


def test_relaxed_cascade_index_least_little_most():
    p = vrm.hand_pose("left")
    curls = [curl_deg(p, f) for f in ("Index", "Middle", "Ring", "Little")]
    assert curls == sorted(curls) and curls[0] > 20 and curls[-1] < 120


def test_right_hand_mirrors_left():
    l, r = vrm.hand_pose("left", "fist"), vrm.hand_pose("right", "fist")
    for k, v in l.items():
        w = r["right" + k[4:]]
        assert w == pytest.approx((v[0], -v[1], -v[2]))


def test_every_shape_keeps_fingers_apart():
    # no finger crosses its neighbour: the tips stay in order across the hand (index front, little back)
    for shape in vrm.HAND_SHAPES:
        _, tails = posed(vrm.hand_pose("left", shape))
        ys = [tails[f"left{f}Distal"][1] for f in ("Index", "Middle", "Ring", "Little")]
        assert ys == sorted(ys), shape


def test_pose_fills_relaxed_fingers_only_for_unnamed_hands():
    got = vrm.relaxed_fingers({"leftIndexProximal": (0, 30, 0)})
    assert all(k.startswith("right") for k in got) and "rightLittleProximal" in got


@pytest.mark.parametrize("radius", [0.013, 0.022])
def test_wrap_closes_on_the_grip(radius):
    ch = FakeHand()
    f = vrm_rig.wrap(ch, "left", radius)
    _, tails = posed(f)
    hd, _ = posed(f)
    k0, p0, r0 = vrm.hand_rest(ch, "left")
    hole = ch.rest("leftHand") + r0 * 0.85 + p0 * 0.028
    for finger in ("Index", "Middle", "Ring", "Little"):
        for j in ("Intermediate", "Distal"):
            q = hd[f"left{finger}{j}"] - hole
            d = np.linalg.norm(q - k0 * np.dot(q, k0))         # distance from the grip's axis
            assert d >= radius - 0.001, (finger, j)              # never through it
            assert d - radius < 0.006 + 0.004, (finger, j)       # on it: a finger's half thickness, within 4 mm


def test_grip_eases_to_relaxed():
    ch = FakeHand()
    full = vrm_rig.grip(ch, "left", 0.02)
    half = vrm_rig.grip(ch, "left", 0.02, amount=0.0)
    rel = vrm.hand_pose("left")
    assert va.angle_between(vrm.euler(rel["leftIndexProximal"]), va.turn_matrix(half["leftIndexProximal"])) < 1e-4
    assert va.angle_between(np.eye(3), va.turn_matrix(full["leftIndexProximal"])) > 30


def test_pinch_brings_thumb_to_index():
    _, tails = posed(vrm_rig.pinch("left"))
    gap = np.linalg.norm(tails["leftThumbDistal"] - tails["leftIndexIntermediate"])
    _, t0 = posed({})
    assert gap < np.linalg.norm(t0["leftThumbDistal"] - t0["leftIndexIntermediate"])


def test_arc_swings_round_center():
    c = np.zeros(3)
    a, b = np.array([0.5, 0, 0]), np.array([0, 0.5, 0])
    m = va.arc(a, b, 0.5, center=c)
    assert np.linalg.norm(m) == pytest.approx(0.5)              # stays the arm's length out
    assert np.allclose(va.arc(a, b, 0.0, center=c), a) and np.allclose(va.arc(a, b, 1.0, center=c), b)
    lifted = va.arc(a, b, 0.5, lift=0.1)
    assert lifted[2] == pytest.approx(0.1)


def test_follow_lags_then_settles():
    fps = 24
    rots = [vrm.euler((0, 0, min(90.0, 9.0 * i))) for i in range(40)]
    d = va.follow(rots, fps, lag=0.08, bounce=0.35)
    lag = [va.angle_between(np.eye(3), x) for x in d]
    assert lag[0] < 1e-6
    assert max(lag[:11]) > 5.0                                  # trails while the swing goes
    assert lag[-1] < 2.0                                        # settles once it stops
    # trails behind (against the swing) while moving
    assert (d[6] @ rots[6])[1, 0] < rots[6][1, 0]


def test_follow_still_is_still():
    d = va.follow([vrm.euler((10, 20, 30))] * 10)
    assert all(va.angle_between(np.eye(3), x) < 1e-6 for x in d)


def test_stagger_orders_and_spreads():
    s = va.stagger(4, 3.0, seed=2)
    assert list(s) == sorted(s) and s[-1] - s[0] > 1.5


def test_twist_split_composes():
    t = vrm.euler((70.0, 10.0, 5.0))
    fore, hand = va.twist_split(t, (1.0, 0.0, 0.0), 0.5)
    assert np.allclose(fore @ hand, t)
    assert va.angle_between(np.eye(3), fore) == pytest.approx(35.0, abs=4.0)
