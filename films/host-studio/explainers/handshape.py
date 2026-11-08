"""Anatomical hand shapes (R7 hands, agent-08): named whole-hand poses as ABSOLUTE joint targets, not curl offsets.

Why (the operator, 08 Nov, on her verify at 00:08: "the finger -> it looks like zombie"): gesturekit's shapes were
degrees ADDED to the rig's reference curl (ref MCP 20-43, PIP 23-37, DIP 11-25 on her rig), spread 0.8/1/0.8 over
MCP/PIP/DIP, with the PIP/DIP clamped at -5. A "straight" counted index (-22) ended at MCP 12-19, PIP 19, DIP 21: the
knuckle straight, the end joints bent, DIP >= PIP: the intrinsic-minus CLAW. The desk hand's DIPs sat at 7-18: flat.

Here every finger is driven by ONE number, its closure c (0 = a straight finger with its natural slight curve,
1 = a full fist), through one flexion synergy from hand anatomy:
  - MCP leads: MCP = M0 + (Mmax - M0) * (1 - (1 - c)^MCP_LEAD), front-loaded, so a natural curl bends the knuckle
    first and the knuckle is never straight while the end joints are bent (no claw, at any blend);
  - PIP = P0 + (Pmax - P0) * c;
  - DIP = DIP_K * PIP (the coupled flexion: the DIP rides the PIP at ~2/3).
The relaxed cascade (index least flexed, pinky most), the spread narrowing as the fingers close, and the thumb (its
CMC swings it in front of the palm toward the pinky: opposition; its MCP and IP flex together) complete it.

A shape is {finger: closure %, "thumb": thumb flexion %, "_opp": thumb opposition %} (0-100; the style layer's per-
finger drift, settle and seeded offsets still ADD to it, in the same units). Blending two shapes blends closures, so a
transition follows the same synergy and never passes through a claw. The rig's own reference angles are measured once
per skeleton (ref_angles) and each joint turns by target - ref, so it works on both presenters' rigs.
"""
from __future__ import annotations

import math

FINGERS4 = ("index", "middle", "ring", "pinky")

# deg: (MCP at c=0, MCP at c=1, PIP at c=0, PIP at c=1) per finger. c=0 keeps the natural slight curve of a straight
# human finger (never dead straight, never bent back); c=1 is a closed fist (MCP ~85-90, PIP ~100-105).
SYNERGY = {"index": (4.0, 82.0, 6.0, 100.0), "middle": (4.0, 86.0, 6.0, 104.0),
           "ring": (5.0, 88.0, 7.0, 104.0), "pinky": (6.0, 90.0, 8.0, 100.0)}
MCP_LEAD = 1.6  # the MCP's front-loading (1 = linear with the PIP)
PIP_LAG = 1.4   # the PIP's back-loading (PIP = P0 + (Pmax - P0) * c^PIP_LAG)
DIP_K = 0.67    # DIP / PIP
C_MIN, C_MAX = -0.06, 1.08  # closure limits (a little past straight on an open palm; a tight fist)

# the thumb: CMC opposition (deg of swing in front of the palm, and of swing across toward the pinky, at 100 %),
# MCP and IP flexion (deg at 100 %)
THUMB_OPP_FRONT = 40.0
THUMB_OPP_ACROSS = 22.0
THUMB_FRONT_BASE = 12.0  # deg of palmar abduction always: a living thumb never lies in the palm's plane (agent-13's
#   thumb_flat: 6 right-hand frames on dd4cc957, the open palm's thumb at opp ~0 as the fingers curled out of it)
THUMB_MCP = 50.0
THUMB_IP = 62.0

# The named whole-hand poses (closure %; thumb flexion %, opposition %). Authored from anatomy:
# The thumb's (flexion, opposition) per shape are fitted on her rig by its tip, each with an opposition floor (the
# proximal phalanx out of the palm's plane toward the palm: agent-13's thumb_flat, opp < 10 with the fingers curled):
# the pinch's tip to the index tip 0.4-1.8 cm at opp 35-45 deg, the point/raise thumb on the folded middle phalanx
# 1.2-2.6 cm at opp 28-41, the fist's 1.2-1.9 cm at 25-34, the relaxed/rest thumb beside the index at 21-31; the open
# palm's thumb swings out in plane (opp < 0: radial abduction).
#   relaxed  the resting hand in the air: the cascade 22 < 28 < 34 < 40, the thumb loosely opposed beside the index
#   rest     the hand resting PALM DOWN on the desk (the orchestrator's targets: MCP 15-25 / PIP 20-35 / DIP 10-20):
#            fingers together and gently curled, the pads on the desk, the thumb lying along the index. Fitted on her
#            rig so all four fingertips touch (0.9 cm, the pads): MCP 22-29 / PIP 20-27 / DIP 13-18. A supported hand
#            takes the desk's shape, not the air's cascade (the palm's arch puts ring and pinky lower, the middle is
#            longest)
#   open     an open palm: nearly straight, a natural slight curve, a small cascade, spread (gesture_style)
#   list     the listing beat: an open hand, a touch cupped (palm up/in, placing an item on a line)
#   point    the index straight with a slight curve; the others folded into the palm (PIP ~85, off the joint's limit:
#            agent-13's fold_at_limit, PIP >= 95 on a hold), the thumb over the middle
#   raise    the raised index ('wait a second'): the index up with a slight curve, the others folded softly (a
#            looser cascade than the point's, the thumb resting on the middle)
#   count1-3 the counted fingers straight with a slight curve; the rest folded INTO the palm, held by the thumb
#   pinch    a soft precision pinch: index and thumb pads toward each other, the others cascading behind
#   soft_fist  a loose fist, the thumb across the middle phalanges
SHAPES = {
    "relaxed": {"index": 22, "middle": 28, "ring": 34, "pinky": 40, "thumb": 60, "_opp": 10},
    "rest": {"index": 18, "middle": 20, "ring": 17, "pinky": 13, "thumb": 12, "_opp": -10},
    "open": {"index": 3, "middle": 4, "ring": 6, "pinky": 9, "thumb": 5, "_opp": -45},
    "list": {"index": 8, "middle": 10, "ring": 13, "pinky": 17, "thumb": 8, "_opp": -20},
    "point": {"index": 3, "middle": 80, "ring": 84, "pinky": 86, "thumb": 90, "_opp": 0},
    "raise": {"index": 4, "middle": 66, "ring": 76, "pinky": 84, "thumb": 80, "_opp": 10},
    "count1": {"index": 3, "middle": 80, "ring": 84, "pinky": 86, "thumb": 90, "_opp": 0},
    "count2": {"index": 3, "middle": 4, "ring": 84, "pinky": 86, "thumb": 100, "_opp": 10},
    "count3": {"index": 3, "middle": 4, "ring": 8, "pinky": 86, "thumb": 100, "_opp": 20},
    "pinch": {"index": 46, "middle": 40, "ring": 46, "pinky": 52, "thumb": 20, "_opp": 60},
    "soft_fist": {"index": 66, "middle": 72, "ring": 76, "pinky": 80, "thumb": 80, "_opp": 0},
}
KEYS = FINGERS4 + ("thumb", "_opp")


def full(shape) -> dict:
    """A shape name or (partial) dict -> every key, the missing ones from 'relaxed' (an absent finger is relaxed,
    never straight)."""
    base = SHAPES["relaxed"]
    if isinstance(shape, dict):
        return {**{k: float(base[k]) for k in KEYS}, **{k: float(v) for k, v in shape.items()}}
    return {k: float(v) for k, v in SHAPES.get(shape, base).items()}


def opp_floor(shape: dict) -> float:
    """The thumb's opposition % at least, from the fingers' mean closure: as the fingers curl the thumb comes around
    with them (a hand-wide synergy), so no blend or transition ever has a curled hand with a flat thumb (agent-13's
    thumb_flat). 0 up to a mean closure of 18 (open, list, the desk rest), rising 2.5 % per % of closure."""
    mean_c = sum(float(shape.get(f, 0.0)) for f in FINGERS4) / 4.0
    return max(0.0, min(40.0, 2.5 * (mean_c - 18.0)))


def finger_angles(finger: str, closure_pct: float, pip_extra: float = 0.0) -> tuple:
    """(MCP, PIP, DIP) absolute flexion deg for a closure in %, + an independent PIP drift (the DIP follows it)."""
    m0, m1, p0, p1 = SYNERGY[finger]
    c = max(C_MIN, min(C_MAX, closure_pct / 100.0))
    if c >= 0.0:
        lead = 1.0 - (1.0 - min(c, 1.0)) ** MCP_LEAD + max(0.0, c - 1.0) * MCP_LEAD
        mcp = m0 + (m1 - m0) * lead
    else:  # past straight (an open palm's drift): the knuckle gives, the end joints barely
        mcp = m0 + 60.0 * c
    cp = c ** PIP_LAG if c > 0.0 else c  # the middle joint trails at low closure: an open or relaxed hand bends at the
    #   knuckles with the fingers nearly straight (the operator's reference); linear, a list hand's PIP+DIP (8-11 +
    #   6-7 at MCP 13-22) curled like the MCP and, palm to camera with the knuckles foreshortened, read as a claw
    pip = max(0.0, p0 + (p1 - p0) * cp + pip_extra)
    return mcp, pip, DIP_K * pip


def thumb_angles(flex_pct: float, opp_pct: float) -> tuple:
    """(CMC front swing, CMC across swing, MCP flex, IP flex) deg."""
    f = max(-0.1, min(1.1, flex_pct / 100.0))
    o = max(-1.0, min(1.1, opp_pct / 100.0))  # < 0: radial abduction (the open palm's thumb swings out, in plane)
    base = THUMB_FRONT_BASE * max(0.0, min(1.0, 1.0 + o))  # a thumb laid out along the index (o < 0: the
    #   rest's, the open palm's) drops the base, or a palm-down hand's thumb poked under it into the desk
    return base + THUMB_OPP_FRONT * max(0.0, o), THUMB_OPP_ACROSS * o, THUMB_MCP * max(0.0, f), THUMB_IP * max(0.0, f)


# Abduction (R7 hands, the orchestrator's review: 'the fingers SPREAD APART individually, a piano/spider look'; her rig's
# own reference fans the left fingers -11 / +8 / +7 deg off the middle): ABSOLUTE targets too, deg off the middle
# finger's proximal phalanx in the palm's plane, + toward the pinky. A relaxed hand's fingers lie nearly together
# (adjacent <= ~3 deg, converging slightly); a shape's '_spread' (deg) opens the fan from there (x SPREAD_DIR), only an
# open 'present' palm opens it visibly (adjacent ~5).
ABD_TOGETHER = {"index": -2.0, "middle": 0.0, "ring": 2.0, "pinky": 4.5}
SPREAD_DIR = {"index": -1.0, "middle": 0.0, "ring": 0.7, "pinky": 1.4}


def abduction_target(finger: str, spread: float, closure_pct: float) -> float:
    """deg off the middle finger (+ toward the pinky) for a shape's spread; closing fingers converge (spread_k)."""
    return (ABD_TOGETHER[finger] + spread * SPREAD_DIR[finger]) * spread_k(closure_pct)


def abduction(P: dict, Q: dict, s: str) -> dict:
    """{finger: deg off the middle finger's proximal phalanx in the palm's plane, + toward the pinky} (the
    finger_spread row's measure; adjacent abduction = the difference of neighbours)."""
    sign = 1.0 if s == "l" else -1.0
    hd = _unit(_sub(P[f"middle_01_{s}"], P[f"hand_{s}"]))
    kn = _sub(P[f"pinky_01_{s}"], P[f"index_01_{s}"])
    n = _unit(_cross(hd, kn))

    def plane(v):
        return _unit(_sub(v, [n[i] * _dot(v, n) for i in range(3)]))
    m = plane(bone_dir(Q[f"middle_01_{s}"], sign))
    side = plane(_sub(kn, [m[i] * _dot(kn, m) for i in range(3)]))  # in the plane, toward the pinky
    out = {}
    for f in FINGERS4:
        v = plane(bone_dir(Q[f"{f}_01_{s}"], sign))
        out[f] = math.degrees(math.atan2(_dot(v, side), _dot(v, m)))
    return out


def spread_k(closure_pct: float) -> float:
    """The share of a shape's spread a finger keeps: it narrows as the finger closes (closed fingers converge)."""
    return max(0.15, 1.0 - 0.85 * max(0.0, min(1.0, closure_pct / 100.0)))


# --- measuring a hand (the reference pose, or any posed frame) ----------------------------------------------------------

def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a) or 1.0
    return [a[0] / n, a[1] / n, a[2] / n]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _qrot(q, v):
    x, y, z, w = q
    t = [2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])]
    return [v[0] + w * t[0] + y * t[2] - z * t[1], v[1] + w * t[1] + z * t[0] - x * t[2],
            v[2] + w * t[2] + x * t[1] - y * t[0]]


def bone_dir(q, sign: float) -> list:
    """A finger bone's direction from its rotation: UE finger bones run along local +x (left) / -x (right)."""
    return _unit(_qrot(q, [sign, 0.0, 0.0]))


def signed_bend(a, b, n) -> float:
    """deg from bone direction a to b, + when b turns toward n (the palm side)."""
    ang = math.degrees(math.acos(max(-1.0, min(1.0, _dot(_unit(a), _unit(b))))))
    return ang if _dot(_sub(_unit(b), _unit(a)), n) >= 0.0 else -ang


def palm_normal(P: dict, s: str) -> list:
    """The palm's normal toward the palm side (where the fingers curl to), from joint positions {bone: [x, y, z]}."""
    hd = _unit(_sub(P[f"middle_01_{s}"], P[f"hand_{s}"]))
    n = _unit(_cross(hd, _sub(P[f"index_01_{s}"], P[f"pinky_01_{s}"])))
    if _dot(_sub(P[f"middle_03_{s}"], P[f"middle_01_{s}"]), n) < 0.0:
        n = [-n[0], -n[1], -n[2]]
    return n


HAND_SIGN = {"l": -1.0, "r": 1.0}  # handedness: flexion is + about (pinky_01 - index_01) x this (MetaHuman / UE rig)


def flex(a, b, axis, sgn) -> float:
    """Signed deg from bone direction a to b about the hinge axis (each projected off it: lateral deviation and
    abduction drop out), + toward the palm. Fold-proof: no sign taken from a finger's own pose."""
    a = _unit(_sub(a, [axis[i] * _dot(a, axis) for i in range(3)]))
    b = _unit(_sub(b, [axis[i] * _dot(b, axis) for i in range(3)]))
    ang = math.degrees(math.atan2(_dot(_cross(a, b), axis), _dot(a, b)))
    return sgn * ang


def hand_angles(P: dict, Q: dict, s: str) -> dict:
    """{finger: (MCP, PIP, DIP)} flexion deg of one hand from joint positions P and rotations Q (component space):
    each finger's bone directions (UE finger bones run along local +x left / -x right), the angle between successive
    bones about the knuckle line (index_01 -> pinky_01), + toward the palm. The thumb: (MCP, IP) unsigned. The rows
    (agent-13) use the same measure; the rig's reference angles come from it."""
    sign = 1.0 if s == "l" else -1.0
    axis = _unit(_sub(P[f"pinky_01_{s}"], P[f"index_01_{s}"]))
    out = {}
    for f in FINGERS4:
        js = [f"{f}_metacarpal_{s}", f"{f}_01_{s}", f"{f}_02_{s}", f"{f}_03_{s}"]
        if not all(j in Q for j in js):
            continue
        d = [bone_dir(Q[j], sign) for j in js]
        out[f] = tuple(flex(d[i], d[i + 1], axis, HAND_SIGN[s]) for i in range(3))
    js = [f"thumb_01_{s}", f"thumb_02_{s}", f"thumb_03_{s}"]
    if all(j in Q for j in js):
        d = [bone_dir(Q[j], sign) for j in js]
        out["thumb"] = tuple(math.degrees(math.acos(max(-1.0, min(1.0, _dot(d[i], d[i + 1]))))) for i in range(2))
    return out


PALM_SIGN = {"l": -1.0, "r": 1.0}  # (middle_01 - hand) x (index_01 - pinky_01) x this points to the palm side


def thumb_opposition(P: dict, s: str) -> float:
    """deg the thumb's proximal phalanx (thumb_02 -> thumb_03) leaves the palm's plane toward the palm side (agent-13's
    thumb_flat: < 10 with the fingers curled = a thumb lying flat in the palm's plane). Fold-proof: the palm's normal
    from the hand's long axis and the knuckle line, its side by the rig's handedness."""
    hd = _unit(_sub(P[f"middle_01_{s}"], P[f"hand_{s}"]))
    n = _unit(_cross(hd, _sub(P[f"index_01_{s}"], P[f"pinky_01_{s}"])))
    n = [PALM_SIGN[s] * x for x in n]
    v = _unit(_sub(P[f"thumb_03_{s}"], P[f"thumb_02_{s}"]))
    return math.degrees(math.asin(max(-1.0, min(1.0, _dot(v, n)))))


def claw_score(mcp: float, pip: float, dip: float) -> float:
    """> 0 for an intrinsic-minus claw: the knuckle (near) straight while the end joints are flexed. The amount (deg)
    by which PIP + DIP flexion exceeds what the MCP's flexion carries on the synergy, less a tolerance."""
    return (pip + dip) - (1.67 * (mcp + 8.0) + 25.0)
