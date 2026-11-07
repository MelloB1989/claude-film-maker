"""seatkit on a synthetic MetaHuman-shaped skeleton (rest rotations random, facing +Y like the MH body's component
space), so nothing depends on identity frames."""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seatkit as S  # noqa: E402

# bone: (parent, rest component position [x right?, y forward, z up]) -- facing +Y, the body's right at -X
P = {
    "root": (None, [0, 0, 0]), "pelvis": ("root", [0, 0, 98]),
    "spine_01": ("pelvis", [0, 0, 103]), "spine_02": ("spine_01", [0, 0, 110]), "spine_03": ("spine_02", [0, 0, 118]),
    "spine_04": ("spine_03", [0, 0, 126]), "spine_05": ("spine_04", [0, 0, 136]),
    "neck_01": ("spine_05", [0, 1, 146]), "neck_02": ("neck_01", [0, 1, 152]), "head": ("neck_02", [0, 1, 158]),
}
for s, x in (("l", 1), ("r", -1)):
    P.update({
        f"thigh_{s}": ("pelvis", [9 * x, 0, 93]), f"calf_{s}": (f"thigh_{s}", [10 * x, 1, 50]),
        f"foot_{s}": (f"calf_{s}", [11 * x, -2, 9]), f"ball_{s}": (f"foot_{s}", [12 * x, 13, 2]),
        f"clavicle_{s}": ("spine_05", [3 * x, 2, 142]), f"upperarm_{s}": (f"clavicle_{s}", [18 * x, -2, 142]),
        f"lowerarm_{s}": (f"upperarm_{s}", [30 * x, -4, 115]), f"hand_{s}": (f"lowerarm_{s}", [38 * x, 0, 92]),
        f"middle_01_{s}": (f"hand_{s}", [40 * x, 1, 83]), f"index_01_{s}": (f"hand_{s}", [39 * x, 3, 84]),
        f"pinky_01_{s}": (f"hand_{s}", [40 * x, -2, 85]), f"middle_03_{s}": (f"middle_01_{s}", [41 * x, 1, 77]),
    })


def skeleton(seed=3):
    rnd = random.Random(seed)
    world, local, parent = {}, {}, {}
    for b, (p, pos) in P.items():
        q = S.qnorm([rnd.uniform(-1, 1) for _ in range(4)])
        world[b] = {"t": [float(v) for v in pos], "q": q}
        parent[b] = p
    for b, (p, pos) in P.items():
        if p is None:
            local[b] = {"t": list(world[b]["t"]), "q": list(world[b]["q"]), "s": [1, 1, 1]}
            continue
        pq = world[p]["q"]
        local[b] = {"t": S.qrot(S.qinv(pq), S.sub(world[b]["t"], world[p]["t"])),
                    "q": S.qmul(S.qinv(pq), world[b]["q"]), "s": [1, 1, 1]}
    return S.Skeleton.from_read({"parent": parent, "local": local, "world": world})


def test_frame():
    F = skeleton().frame()
    assert F["fwd"][1] > 0.99 and F["right"][0] < -0.99


def test_fk_roundtrip_rest():
    sk = skeleton()
    se = S.Seater(sk)
    posed = se.fk({})
    for b in P:
        assert S.norm(S.sub(posed[b][0], sk.p(b))) < 1e-6, b


def test_seated_pose():
    sk = skeleton()
    st = S.Set(mic=[24, -14, 99], desk_near=12.0)
    se = S.Seater(sk, st)
    loc = se.pose()
    posed = se.fk(loc)
    chk = S.check(se, posed)
    assert chk["pass"], chk["issues"]
    A = {b: se.actor(v[0]) for b, v in posed.items()}
    hips = [(A["thigh_l"][i] + A["thigh_r"][i]) / 2 for i in range(3)]
    assert abs(hips[0]) < 0.5 and abs(hips[1]) < 0.5 and abs(hips[2] - 55.5) < 0.5
    for s in "lr":
        assert A[f"calf_{s}"][0] > 30  # knees forward
        assert abs(A[f"foot_{s}"][2] - sk.p(f"foot_{s}")[2]) < 0.5  # feet on the floor
        assert A[f"hand_{s}"][2] > 74 and A[f"hand_{s}"][0] > 30  # wrists on the desk
        # bone lengths kept and IK reached: the FK'd wrist is where the IK put it
    assert A["head"][2] > A["spine_05"][2]
    # the head kept its rest rotation (level on the lens)
    assert S.qangle(posed["head"][1], sk.q("head")) < 0.5
    # feet flat: the foot's rotation is the rest one turned about up only
    for s in "lr":
        d = S.qmul(posed[f"foot_{s}"][1], S.qinv(sk.q(f"foot_{s}")))
        ax = S.unit(d[:3]) if S.norm(d[:3]) > 1e-6 else [0, 0, 1]
        assert abs(ax[2]) > 0.99


def test_knee_bends_forward_and_elbow_back():
    sk = skeleton(7)
    se = S.Seater(sk)
    posed = se.fk(se.pose())
    A = {b: se.actor(v[0]) for b, v in posed.items()}
    for s in "lr":
        hip, knee, ank = A[f"thigh_{s}"], A[f"calf_{s}"], A[f"foot_{s}"]
        assert knee[2] > ank[2] + 30 and knee[0] > hip[0] + 30
        sh, el, wr = A[f"upperarm_{s}"], A[f"lowerarm_{s}"], A[f"hand_{s}"]
        assert el[0] < wr[0] and el[2] < sh[2]
        # the elbow sits outside the shoulder-wrist line
        assert abs(el[1]) > min(abs(sh[1]), abs(wr[1])) - 1


def test_gesture_lifts_and_returns():
    sk = skeleton()
    se = S.Seater(sk)
    g = [S.Gesture(1.0, 1.4, 1.9, 2.5, "r", "lift")]
    a0 = se.actor(se.fk(se.pose(0.5, g))["hand_r"][0])
    a1 = se.actor(se.fk(se.pose(1.6, g))["hand_r"][0])
    a2 = se.actor(se.fk(se.pose(3.0, g))["hand_r"][0])
    al = se.actor(se.fk(se.pose(1.6, g))["hand_l"][0])
    assert a1[2] - a0[2] > 8 and S.norm(S.sub(a2, a0)) < 1e-6
    assert S.norm(S.sub(al, se.actor(se.fk(se.pose(0.5, g))["hand_l"][0]))) < 1e-6


def test_gestures_from_cues_merge():
    gs = S.gestures_from_cues([{"t": 1.0, "hand": "r"}, {"t": 1.5, "hand": "r"}, {"t": 4.0}])
    assert len(gs) == 2 and gs[0].t3 >= 1.5 + 0.45 and gs[1].hand in "lr"


def test_frame_to_frame():
    q = S.frame_to_frame([1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0])
    assert S.norm(S.sub(S.qrot(q, [1, 0, 0]), [0, 0, 1])) < 1e-6
    assert S.norm(S.sub(S.qrot(q, [0, 1, 0]), [1, 0, 0])) < 1e-6


def test_signs_lean_twist_tilt():
    sk = skeleton()
    se0 = S.Seater(sk, sy=S.Style(lean=0.0, pelvis_tilt=0.0, twist=0.0))
    se1 = S.Seater(sk, sy=S.Style(lean=20.0, pelvis_tilt=0.0, twist=12.0))
    A0 = {b: se0.actor(v[0]) for b, v in se0.fk(se0.pose()).items()}
    A1 = {b: se1.actor(v[0]) for b, v in se1.fk(se1.pose()).items()}
    assert A1["head"][0] > A0["head"][0] + 10  # leans forward
    # turned toward the right: the left shoulder comes forward, the right goes back
    assert A1["upperarm_l"][0] - A1["upperarm_r"][0] > A0["upperarm_l"][0] - A0["upperarm_r"][0] + 3
    se2 = S.Seater(sk, sy=S.Style(lean=0.0, pelvis_tilt=10.0))
    A2 = {b: se2.actor(v[0]) for b, v in se2.fk(se2.pose()).items()}
    assert A2["spine_02"][0] < A0["spine_02"][0] - 0.5  # pelvis tilts back


def test_boom_clearance_flags():
    sk = skeleton()
    se = S.Seater(sk, S.Set(boom=[[40, 30, 70], [40, 30, 90]]))
    posed = se.fk(se.pose())
    A = se.actor(posed["hand_r"][0])
    se2 = S.Seater(sk, S.Set(boom=[[A[0], A[1], 60], [A[0], A[1], 100]]))
    assert not S.check(se2, se2.fk(se2.pose()))["pass"]


def test_forearms_rest_on_the_desk_and_gestures_pivot_on_the_elbow():
    sk = skeleton()
    se = S.Seater(sk, S.Set(desk_near=12.0))
    g = [S.Gesture(1.0, 1.4, 1.9, 2.5, "r", "lift")]
    A0 = {b: se.actor(v[0]) for b, v in se.fk(se.pose(0.5, g)).items()}
    A1 = {b: se.actor(v[0]) for b, v in se.fk(se.pose(1.6, g)).items()}
    for s in "lr":
        assert abs(A0[f"lowerarm_{s}"][2] - (74 + se.sy.elbow_r)) < 0.5  # the elbow on the desk
        assert abs(A0[f"hand_{s}"][2] - (74 + se.sy.wrist_r)) < 0.5     # the forearm lying on it
    assert S.norm(S.sub(A1["lowerarm_r"], A0["lowerarm_r"])) < 0.5  # the elbow stays planted
    assert A1["hand_r"][2] - A0["hand_r"][2] > 6


def test_wrists_mode_still_works():
    sk = skeleton()
    se = S.Seater(sk, S.Set(), S.Style(rest="wrists"))
    assert S.check(se, se.fk(se.pose()))["pass"]
