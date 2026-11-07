"""The gesture library's retarget and annotation on synthetic skeletons: a MetaHuman-shaped target in an A-pose with
random rest rotations (facing +Y), and a Mixamo-named source in a T-pose facing elsewhere."""
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import annotate as A  # noqa: E402
import retarget as R  # noqa: E402
from seatkit import axis_angle, dot, norm, qinv, qmul, qnorm, qrot, sub, unit  # noqa: E402

# target: bone -> (parent, rest position); the body's left at +X, facing +Y (the MH body's component space)
T = {
    "root": (None, [0, 0, 0]), "pelvis": ("root", [0, 0, 98]),
    "spine_01": ("pelvis", [0, 0, 103]), "spine_02": ("spine_01", [0, 0, 110]), "spine_03": ("spine_02", [0, 0, 118]),
    "spine_04": ("spine_03", [0, 0, 126]), "spine_05": ("spine_04", [0, 0, 136]),
    "neck_01": ("spine_05", [0, 1, 146]), "neck_02": ("neck_01", [0, 1, 152]), "head": ("neck_02", [0, 1, 158]),
}
for s, x in (("l", 1), ("r", -1)):
    T.update({
        f"thigh_{s}": ("pelvis", [9 * x, 0, 93]), f"calf_{s}": (f"thigh_{s}", [10 * x, 1, 50]),
        f"clavicle_{s}": ("spine_05", [3 * x, 2, 142]), f"upperarm_{s}": (f"clavicle_{s}", [18 * x, -2, 142]),
        f"upperarm_twist_01_{s}": (f"upperarm_{s}", [24 * x, -3, 128]),
        f"lowerarm_{s}": (f"upperarm_{s}", [30 * x, -4, 115]), f"hand_{s}": (f"lowerarm_{s}", [38 * x, 0, 92]),
        f"middle_metacarpal_{s}": (f"hand_{s}", [39 * x, 1, 88]),
        f"middle_01_{s}": (f"middle_metacarpal_{s}", [40 * x, 1, 83]),
        f"middle_02_{s}": (f"middle_01_{s}", [40.5 * x, 1, 80]), f"middle_03_{s}": (f"middle_02_{s}", [41 * x, 1, 77]),
    })


def read_of(P, seed):
    rnd = random.Random(seed)
    q = {b: qnorm([rnd.uniform(-1, 1) for _ in range(4)]) for b in P}
    local = {}
    for b, (p, t) in P.items():
        if p is None:
            local[b] = {"t": t, "q": q[b]}
        else:
            local[b] = {"t": qrot(qinv(q[p]), sub(t, P[p][1])), "q": qnorm(qmul(qinv(q[p]), q[b]))}
    return {"parent": {b: p for b, (p, _) in P.items()}, "local": local}, q


# source: Mixamo names, a T-pose, the body's left at +X, facing -Y (a mirror-free turn of 180 deg about Z from +Y),
# then turned 90 deg about Z so nothing lines up with the target by accident
S = {"Hips": (None, [0, 0, 100]), "Spine": ("Hips", [0, 0, 110]), "Spine1": ("Spine", [0, 0, 122]),
     "Spine2": ("Spine1", [0, 0, 134]), "Neck": ("Spine2", [0, 0, 148]), "Head": ("Neck", [0, 0, 156])}
for side, x in (("Left", 1), ("Right", -1)):
    S.update({f"{side}Shoulder": ("Spine2", [4 * x, 0, 144]), f"{side}Arm": (f"{side}Shoulder", [16 * x, 0, 144]),
              f"{side}ForeArm": (f"{side}Arm", [44 * x, 0, 144]), f"{side}Hand": (f"{side}ForeArm", [70 * x, 0, 144]),
              f"{side}HandMiddle1": (f"{side}Hand", [79 * x, 0, 144]),
              f"{side}HandMiddle2": (f"{side}HandMiddle1", [83 * x, 0, 144]),
              f"{side}HandMiddle3": (f"{side}HandMiddle2", [86 * x, 0, 144])})
TURN = axis_angle([0, 0, 1], 90.0)


def src_rest(seed=5):
    rnd = random.Random(seed)
    rest = {}
    for b, (p, t) in S.items():
        rest["mixamorig:" + b] = {"t": qrot(TURN, t), "q": qnorm(qmul(TURN, qnorm([rnd.uniform(-1, 1) for _ in range(4)])))}
    return rest


def pose(rest, rots):
    """A source frame: world rotation deltas per bone (bone -> quaternion, applied to it and its subtree, in order
    from the root), positions by FK."""
    world = {b: dict(t=list(v["t"]), q=list(v["q"])) for b, v in rest.items()}
    order = list(S)
    for b, r in rots.items():
        sub_tree = [b]
        for c in order:
            if S[c][0] in sub_tree:
                sub_tree.append(c)
        piv = world["mixamorig:" + b]["t"]
        for c in sub_tree:
            w = world["mixamorig:" + c]
            w["q"] = qnorm(qmul(r, w["q"]))
            w["t"] = [a + b_ for a, b_ in zip(piv, qrot(r, sub(w["t"], piv)))]
    return world


def dump_of(frames_rots, fps=30):
    rest = src_rest()
    return {"fps": fps, "rest": rest, "frames": [pose(rest, r) for r in frames_rots]}


def target():
    read, _ = read_of(T, 3)
    return R.Target(read)


def ang(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


def test_rest_frame_puts_target_in_source_pose():
    """The source at rest (a T-pose): the target's arms point where the source's do (after the body turn)."""
    tg = target()
    rt = R.Retarget(tg, dump_of([{}]))
    P = rt.positions(rt.world(0))
    for s, x in (("l", 1), ("r", -1)):
        assert ang(sub(P[f"lowerarm_{s}"], P[f"upperarm_{s}"]), [x, 0, 0]) < 0.5
        assert ang(sub(P[f"hand_{s}"], P[f"lowerarm_{s}"]), [x, 0, 0]) < 0.5


def test_motion_follows_source_directions():
    """Every frame, the target's arm segments point where the source's do, turned by G."""
    frames = []
    for i in range(12):
        a = 8.0 * i
        frames.append({"RightArm": axis_angle(qrot(TURN, [0, 1, 0]), -a),
                       "RightForeArm": axis_angle(qrot(TURN, [0, 0, 1]), 3 * i),
                       "Spine1": axis_angle(qrot(TURN, [1, 0, 0]), i)})
    d = dump_of(frames)
    rt = R.Retarget(target(), d)
    for f in range(len(frames)):
        W = rt.world(f)
        P = rt.positions(W)
        src = d["frames"][f]
        for (tb, tc), (sb, sc) in ((("upperarm_r", "lowerarm_r"), ("RightArm", "RightForeArm")),
                                   (("lowerarm_r", "hand_r"), ("RightForeArm", "RightHand"))):
            want = qrot(rt.G, sub(src["mixamorig:" + sc]["t"], src["mixamorig:" + sb]["t"]))
            assert ang(sub(P[tc], P[tb]), want) < 0.5, (f, tb)


def test_unmapped_bones_ride_their_parent():
    tg = target()
    rt = R.Retarget(tg, dump_of([{"RightArm": axis_angle([0, 0, 1], 30)}]))
    W = rt.world(0)
    loc = rt.local(W, ["upperarm_twist_01_r", "middle_metacarpal_r", "thigh_l"])
    for b, q in loc.items():
        d = abs(sum(x * y for x, y in zip(q, tg.local[b]["q"])))
        assert d > 0.9999, b


def test_mirror_moves_the_other_arm():
    """A right-arm raise mirrored is a left-arm raise of the same size."""
    up_r = {"RightArm": axis_angle(qrot(TURN, [0, 1, 0]), -50)}
    d = dump_of([{}, up_r])
    m = R.mirror_dump(d)
    assert m["mirrored"]
    rt0, rtm = R.Retarget(target(), d), R.Retarget(target(), m)
    P0r = [rt0.positions(rt0.world(f)) for f in (0, 1)]
    Pmr = [rtm.positions(rtm.world(f)) for f in (0, 1)]
    moved_r = norm(sub(P0r[1]["hand_r"], P0r[0]["hand_r"]))
    moved_l_m = norm(sub(Pmr[1]["hand_l"], Pmr[0]["hand_l"]))
    still_r_m = norm(sub(Pmr[1]["hand_r"], Pmr[0]["hand_r"]))
    assert moved_r > 20 and abs(moved_l_m - moved_r) < 0.5 and still_r_m < 0.5


def test_elbows_cleared_off_the_torso():
    """Arms hanging straight down (the elbow under the shoulder) are abducted until the elbow is >= elbow_out
    outside the shoulder; the forearm keeps its world rotation."""
    down = 90.0
    fr = {"RightArm": axis_angle(qrot(TURN, [0, 1, 0]), -down), "LeftArm": axis_angle(qrot(TURN, [0, 1, 0]), down)}
    rt = R.Retarget(target(), dump_of([fr]), elbow_out_cm=4.0)
    W0 = rt.world(0)
    W1 = rt.clear_elbows(W0, 0)
    P = rt.positions(W1)
    for s in ("l", "r"):
        side = rt.left if s == "l" else [-x for x in rt.left]
        assert dot(sub(P[f"lowerarm_{s}"], P[f"upperarm_{s}"]), side) >= 3.9
        d = abs(sum(x * y for x, y in zip(W0[f"lowerarm_{s}"], W1[f"lowerarm_{s}"])))
        assert d > 0.9999
    assert len(rt.clear_log) == 2 and all(0 < c["deg"] < 20 for c in rt.clear_log)


def test_run_outputs_upper_body_locals_and_tracks():
    d = dump_of([{}, {"RightArm": axis_angle([0, 0, 1], 10)}])
    res = R.Retarget(target(), d).run()
    assert "thigh_l" not in res["bones"] and "upperarm_r" in res["bones"] and "middle_02_r" in res["bones"]
    assert len(res["frames"]) == 2 and len(res["frames"][0]) == len(res["bones"])
    assert set(res["joints"]["joints"]) >= {"hand_l", "hand_r", "upperarm_l", "spine_05", "head"}
    w = res["wrists_chest"]["hand_r"]
    assert len(w) == 2 and abs(norm(w[0]["t"]) - norm(sub(res["joints"]["joints"]["hand_r"][0],
                                                          res["joints"]["joints"]["spine_05"][0]))) < 0.01


# --- annotation ------------------------------------------------------------------------------------------------------

def synth_joints(fps=30, n=150):
    """A seated body facing +Y (left +X): the right hand rests, rises 20 cm forward-and-out at 1.0-1.4 s, holds,
    returns by 2.2 s; both hands beat together at 3.5 s."""
    def bump(t, t0, t1):
        if t <= t0 or t >= t1:
            return 0.0
        return 0.5 - 0.5 * math.cos(2 * math.pi * (t - t0) / (t1 - t0))

    def ramp(t, t0, t1, t2, t3):
        if t <= t0 or t >= t3:
            return 0.0
        if t < t1:
            return 0.5 - 0.5 * math.cos(math.pi * (t - t0) / (t1 - t0))
        if t <= t2:
            return 1.0
        return 0.5 + 0.5 * math.cos(math.pi * (t - t2) / (t3 - t2))

    j = {k: [] for k in ("upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "spine_05", "head")}
    for f in range(n):
        t = f / fps
        r = ramp(t, 1.0, 1.4, 1.8, 2.2)
        b = bump(t, 3.3, 3.8)
        j["spine_05"].append([0, 0, 130])
        j["head"].append([0, 2, 160])
        j["upperarm_l"].append([17, 0, 140])
        j["upperarm_r"].append([-17, 0, 140])
        j["lowerarm_l"].append([22, 5, 115])
        j["lowerarm_r"].append([-22, 5, 115])
        j["hand_l"].append([12, 30, 100 + 8 * b])
        j["hand_r"].append([-12 - 8 * r, 30 + 18 * r, 100 + 4 * r + 8 * b])
    return {"fps": fps, "joints": j}


def test_annotate_finds_strokes_holds_and_rests():
    ann = A.annotate(synth_joints())
    ev = ann["events"]
    assert len(ev) == 2, ev
    one, two = ev
    assert one["hand"] == "R" and 30 <= one["prep_f"] <= 36 and 34 <= one["stroke_f"] <= 40
    assert 52 <= one["hold_end_f"] <= 58 and 62 <= one["retract_f"] <= 68
    assert one["target"] == "front" and one["size"] == "medium"
    assert two["hand"] == "both" and 99 <= two["stroke_f"] <= 109
    assert ann["rest"] and ann["rest"][0][0] == 0 and ann["rest"][0][1] < 33
    assert not ann["left_dominant"]


def test_entry_has_agent10_fields():
    cat = {"id": "mx_x", "file": "mx_x.fbx", "source": "mixamo", "source_id": "id", "licence": "L",
           "licence_url": "u", "seated": True, "types": ["open_palm"]}
    e = A.entry(cat, A.annotate(synth_joints()))
    for k in ("id", "file", "source", "licence", "licence_url", "fps", "seated", "frames", "events", "rest", "hand",
              "energy", "length_s"):
        assert k in e, k
    for ev in e["events"]:
        for k in ("type", "hand", "prep_f", "stroke_f", "hold_end_f", "retract_f", "energy", "size", "target"):
            assert k in ev, k
    assert e["hand"] == "both" and 0 < e["energy"] <= 1


def test_batch_one_clip_without_blender(tmp_path=None):
    """batch.one on a dump already made: retarget, annotate and the library entry (a left-hand clip is mirrored)."""
    import json
    import tempfile
    import batch as B
    work = Path(tmp_path or tempfile.mkdtemp())
    frames = []
    for i in range(90):
        a = 50.0 * math.sin(math.pi * min(1.0, max(0.0, (i - 20) / 40.0)))
        frames.append({"LeftArm": axis_angle(qrot(TURN, [0, 1, 0]), 80 - a), "RightArm": axis_angle(qrot(TURN, [0, 1, 0]), -80)})
    (work / "mx_t").mkdir(parents=True, exist_ok=True)
    json.dump(dump_of(frames), open(work / "mx_t" / "dump.json", "w"))
    read, _ = read_of(T, 3)
    clip = {"id": "mx_t", "file": "mx_t.fbx", "source": "mixamo", "source_id": "x", "licence": "L", "licence_url": "u",
            "seated": True, "types": ["open_palm"]}
    e = B.one(clip, work, read, work, "blender-not-needed", preview=False)
    assert e["mirrored"] and e["events"] and all(ev["hand"] in ("R", "both") for ev in e["events"])
    assert (work / "mx_t" / "rtg.json").exists() and (work / "mx_t" / "entry.json").exists()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
