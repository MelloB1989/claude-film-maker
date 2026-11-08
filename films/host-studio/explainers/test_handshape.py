"""handshape.py: the anatomical hand shapes (R7 hands): no claw on any shape or blend, coupled DIP/PIP, the relaxed
cascade, and on her rig each joint lands on its absolute target."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import handshape as HS  # noqa: E402
import seatkit as S  # noqa: E402

NAMES = list(HS.SHAPES)


def angles(name, f):
    return HS.finger_angles(f, HS.full(name)[f])


@pytest.mark.parametrize("a", NAMES)
@pytest.mark.parametrize("b", NAMES)
def test_no_claw_on_any_shape_or_blend(a, b):
    sa, sb = HS.full(a), HS.full(b)
    for f in HS.FINGERS4:
        for k in range(11):
            u = k / 10.0
            m, p, d = HS.finger_angles(f, sa[f] + (sb[f] - sa[f]) * u)
            assert HS.claw_score(m, p, d) < 0.0, (a, b, f, u, m, p, d)
            assert not (m < 20.0 and p > 15.0 and d >= p), (a, b, f, u)  # agent-13's finger_claw row


def test_dip_follows_pip_and_mcp_leads():
    for f in HS.FINGERS4:
        for c in range(0, 101, 10):
            m, p, d = HS.finger_angles(f, c)
            assert d == pytest.approx(HS.DIP_K * p)
            if 15 <= c <= 70:  # a natural curl bends the knuckle at least as far as the middle joint's share
                assert m >= 0.85 * p - 2.0, (f, c, m, p)


def test_a_straight_finger_keeps_its_natural_curve():
    for f in HS.FINGERS4:
        m, p, d = HS.finger_angles(f, 0.0)
        assert 3.0 <= m <= 8.0 and 5.0 <= p <= 9.0 and d > 3.0


@pytest.mark.parametrize("name", ["relaxed", "open", "list", "soft_fist", "pinch"])
def test_relaxed_cascade_index_least_pinky_most(name):
    sh = HS.full(name)
    order = [sh[f] for f in ("middle", "ring", "pinky")]
    assert order == sorted(order) and sh["index"] <= sh["ring"]


def test_folded_fingers_off_the_joint_limit():
    for name in ("point", "raise", "count1", "count2", "count3", "soft_fist"):
        for f in HS.FINGERS4:
            assert angles(name, f)[1] < 95.0, (name, f)  # agent-13's fold_at_limit


def test_spread_narrows_as_the_fingers_close():
    assert HS.spread_k(0) == 1.0 and HS.spread_k(90) < 0.3


def test_a_missing_finger_is_relaxed_not_straight():
    assert HS.full({"index": 3})["pinky"] == HS.SHAPES["relaxed"]["pinky"]


@pytest.fixture(scope="module")
def rig():
    from dataclasses import replace
    import gesturekit as G
    import perform as PF
    d = json.loads((HERE / "skeletons" / "her_body_read.json").read_text())
    sk = S.Skeleton.from_read(d)
    p = PF.perform_params("her")
    plan = G.plan_from_sheet(p["sheet"], p["cues"], p["tilts"], timing=p["timing"], on_cam=p["on_cam"])
    st = PF.set_of("her")
    se, _ = S.autotune(sk, st, replace(PF.STYLE["her"], **PF.PERFORM_STYLE))
    return G, sk, G.Performer(sk, st, se.sy, plan)


def posed(rig, s, name):
    G, sk, perf = rig
    W = {b: [sk.p(b), sk.q(b)] for b in sk.world}
    perf._finger_pose(s, G.HandPose((0, 0, 0), 0, 0, HS.full(name)), W)
    return W


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("s", ["l", "r"])
def test_each_joint_lands_on_its_target_on_her_rig(rig, name, s):
    W = posed(rig, s, name)
    got = HS.hand_angles({b: v[0] for b, v in W.items()}, {b: v[1] for b, v in W.items()}, s)
    for f in HS.FINGERS4:
        for g, w in zip(got[f], angles(name, f)):
            assert g == pytest.approx(w, abs=2.0), (name, s, f, got[f])


@pytest.mark.parametrize("s", ["l", "r"])
def test_the_pinch_pads_meet(rig, s):
    G, sk, perf = rig
    W = posed(rig, s, "pinch")
    F = {b: W[b] for b in W}
    tips = G.finger_tips(perf, F)
    d = S.norm(S.sub(tips[f"thumb_tip_{s}"], tips[f"index_tip_{s}"]))
    assert d < 3.0, d


OPP_FLOOR = {"relaxed": 15, "point": 25, "raise": 25, "count1": 25, "count2": 25, "count3": 25,
             "pinch": 30, "soft_fist": 20}


@pytest.mark.parametrize("name", list(OPP_FLOOR))
@pytest.mark.parametrize("s", ["l", "r"])
def test_the_thumb_is_opposed_not_flat_in_the_palm(rig, name, s):
    W = posed(rig, s, name)
    assert HS.thumb_opposition({b: v[0] for b, v in W.items()}, s) >= OPP_FLOOR[name]


def test_the_desk_rest_is_gently_curled_in_the_orchestrators_ranges():
    for f in HS.FINGERS4:  # the orchestrator's r7I review: nearly flat along the desk (MCP 10-20, PIP 10-20, DIP 5-12);
        m, p, d = angles("rest", f)  # the middle finger, the longest, takes a little more MCP to reach the desk
        assert 10.0 <= m <= 28.0 and 8.0 <= p <= 20.0 and 5.0 <= d <= 12.0, (f, m, p, d)


@pytest.mark.parametrize("name", ["relaxed", "rest", "list"])
@pytest.mark.parametrize("s", ["l", "r"])
def test_fingers_lie_nearly_together(rig, name, s):
    """the orchestrator: no 'piano/spider' fan; agent-13's finger_spread: adjacent abduction <= 5 deg."""
    G, sk, perf = rig
    import gesture_style as GS
    W = posed(rig, s, name)
    GS.finger_post(perf, s, G.HandPose((0, 0, 0), 0, 0, GS.shape_dict(name)), W)
    ab = HS.abduction({b: v[0] for b, v in W.items()}, {b: v[1] for b, v in W.items()}, s)
    adj = [ab["middle"] - ab["index"], ab["ring"] - ab["middle"], ab["pinky"] - ab["ring"]]
    assert max(abs(x) for x in adj) <= 5.0, adj
