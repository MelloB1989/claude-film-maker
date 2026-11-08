"""gesture_style (agent-08, R7): the variation, kinematics and finger layer over gesturekit's code-generated gestures,
on synthetic events, plus gesturekit.build on her skeleton read with the hooks on."""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gesture_style as G  # noqa: E402
import gesturekit as GK  # noqa: E402


def ev(hand, prep, stroke, hold=0.25, kind="open", detail="open_palm", line="N01", seed=1, off=(30.0, 16.0, -1.0),
       pron=-40.0, shape="open", energy=0.5):
    p = GK.HandPose(off, pron, 15.0, shape)
    pl = GK.HandPose((off[0], 7.0, -3.5), pron, 34.0, shape) if hand in ("both", "l") else None
    e = GK.Event(hand, prep, stroke, hold, p, pl, kind, "w", False, energy=energy, seed=seed, detail=detail, line=line)
    e.pose_r = G.vary(e.pose_r, e, "r")
    if e.pose_l is not None:
        e.pose_l = G.vary(e.pose_l, e, "l")
    return e


class Perf:
    def __init__(self, events):
        self.plan = GK.Plan(events, [(0.0, 30.0)], [])


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def test_minimum_jerk_and_envelope():
    assert G.mj(0) == 0 and G.mj(1) == 1 and abs(G.mj(0.5) - 0.5) < 1e-9
    e = ev("r", 1.0, 1.4)
    v = G.var_of(e, "r")
    assert G.envelope("prep", 0.0, e) == 0.0
    assert abs(G.envelope("prep", 1.0, e) - (1 + v.overshoot)) < 1e-9 and v.overshoot > 0.01
    assert abs(G.envelope("hold", 0.0, e) - (1 + v.overshoot)) < 1e-9 and G.envelope("hold", 1.0, e) == 1.0
    assert G.envelope("retract", 1.0, e) == 0.0
    # one min-jerk bell (r7F, agent-13: no skew): symmetric about the middle, overshoot aside
    assert abs(G.envelope("prep", 0.5, e) - 0.5 * (1 + v.overshoot)) < 1e-9


def test_seeded_and_unique():
    a, b = ev("r", 1.0, 1.4, line="N01", seed=5), ev("r", 1.0, 1.4, line="N01", seed=5)
    assert a.pose_r == b.pose_r
    c = ev("r", 1.0, 1.4, line="N01", seed=6)
    d = ev("r", 1.0, 1.4, line="W01", seed=5)  # his line: another seed
    assert c.pose_r.off != a.pose_r.off and d.pose_r.off != a.pose_r.off
    va, vl = G.var_of(a, "r"), G.var_of(a, "l")
    assert va.dt != vl.dt and abs(va.dt) <= 0.04


def test_overshoot_then_settle_on_the_track():
    e = ev("r", 1.0, 1.5, hold=0.5)
    tr = G.HandTrack([e], "r")
    v = G.var_of(e, "r")
    goal = e.pose_r.off
    rest = GK.HIGH_REST.off
    apex = 1.5 + v.dt
    span = dist(goal, rest)
    seg = next(s for s in tr.segs if s.kind == "hold")
    at_apex = tr._eval(seg, apex + 1e-4)[0].off
    settled = tr._eval(seg, apex + v.settle + 0.05)[0].off
    assert dist(at_apex, rest) > span * (1 + 0.6 * v.overshoot)  # past the goal
    assert dist(settled, goal) < 1e-6  # settled (micro-motion is added in at(), not here)


def test_coarticulated_gestures_never_go_home():
    a = ev("r", 1.0, 1.4, hold=0.2, seed=1)
    b = ev("r", 1.8, 2.1, hold=0.2, seed=2, kind="beat", detail="beat", off=(27.0, 12.0, -3.0), pron=35.0,
           shape="relaxed")  # gap 1.8 - 1.6 = 0.2 s < COART_S
    tr = G.HandTrack([a, b], "r")
    kinds = [s.kind for s in tr.segs]
    assert "coart" in kinds and kinds.index("coart") > kinds.index("stroke")
    rest = GK.HIGH_REST.off
    near = min(dist(tr.at(1.6 + k * 0.02)[0].off, rest) for k in range(30))
    assert near > 0.5 * min(dist(a.pose_r.off, rest), dist(b.pose_r.off, rest))


def test_partial_retract_on_a_medium_gap():
    a = ev("r", 1.0, 1.4, hold=0.2, seed=1)
    b = ev("r", 2.4, 2.7, hold=0.2, seed=2)  # gap 0.8 s
    tr = G.HandTrack([a, b], "r")
    r = [s for s in tr.segs if s.kind == "retract"]
    assert r[0].w_to == 0.5 and r[-1].w_to == 0.0


def test_wrist_leads_in_and_follows_out_and_fingers_cascade():
    e = ev("r", 1.0, 1.6, hold=0.3, shape="count1", kind="count", detail="count")
    tr = G.HandTrack([e], "r")
    s = next(x for x in tr.segs if x.kind == "stroke")
    t = s.t0 + 0.3 * (s.t1 - s.t0)
    hp = tr._eval(s, t)[0]
    a, b = s.a, s.b
    u_rot = (hp.pron - a.pron) / (b.pron - a.pron)
    u_pos_plain = G.mj(0.3)  # without the late skew
    assert u_rot > u_pos_plain
    sa, sb, sh = G.shape_dict(a.shape), G.shape_dict(b.shape), hp.shape
    prog = {f: (sh[f] - sa[f]) / (sb[f] - sa[f]) for f in ("pinky", "index") if abs(sb[f] - sa[f]) > 5}
    assert prog["pinky"] > prog["index"]  # pinky first, index last
    r = next(x for x in tr.segs if x.kind == "retract")
    t = r.t0 + 0.3 * (r.t1 - r.t0)
    hp = tr._eval(r, t)[0]
    u_rot = (hp.pron - r.a.pron) / (r.b.pron - r.a.pron)
    assert u_rot < G.mj(0.3)


def test_never_frozen():
    e = ev("r", 1.0, 1.4, hold=1.2)
    perf = Perf([e])
    fr = G.frozen_max_s(perf, 0.0, 4.0)
    assert fr["fingers"] == 0.0 and fr["wrist"] < 0.5


def test_left_hand_stays_inside_the_mic_line():
    for k in range(20):
        e = ev("both", 1.0, 1.4, seed=100 + k, energy=0.9)
        perf = Perf([e])
        for i in range(60):
            hp, _ = G.hand(perf, "l", 1.0 + i * 0.02)
            import gesturekit as GK
            r = GK.HIGH_REST.off
            assert hp.off[1] <= max(G.MIC_L[0], r[1]) + 0.6 and hp.off[2] <= max(G.MIC_L[1], r[2]) + 0.6  # the high rest at most, plus micro


def test_similarity_flags_copies_and_passes_variation():
    a = ev("r", 1.0, 1.4, seed=1)
    b = ev("r", 3.0, 3.4, seed=2)
    perf = Perf([a, b])
    cs = G.curves(perf)
    k = list(cs)
    assert abs(G.curve_sim(cs[k[0]], cs[k[0]]) - 1.0) < 1e-9
    rep = G.similarity({"x": cs})
    assert rep["pass"] and rep["max"] < G.SIM_FAIL
    rep2 = G.similarity({"x": {("r", "a"): cs[k[0]], ("r", "b"): cs[k[0]]}})
    assert not rep2["pass"]


def test_build_on_her_skeleton_passes_with_the_hooks():
    """gesturekit.build with the hooks on her skeleton read, the first 6 s of her sheet (the hook N01-N02)."""
    import perform as P
    import seatkit as S
    assert GK.STYLE_HOOK is not None
    bp = P.body_params("her")
    bp["style"].update(P.PERFORM_STYLE)
    pp = P.perform_params("her")
    data = json.load(open(HERE / "skeletons" / "her_body_read.json"))
    doc, summ = GK.build(data, S.Set(**bp["set"]), S.Style(**bp["style"]), pp["sheet"], pp["cues"], pp["tilts"],
                         6.0, 30)
    assert summ["hooks"]["style"] and summ["pass"], summ["issues"][:5]
    assert min(summ["rows"]["upperarm_bust_clear_cm"].values()) >= 3.0  # the bust by 3 (her side: not into it)
    assert min(summ["rows"]["upperarm_side_clear_cm"].values()) >= 0.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
