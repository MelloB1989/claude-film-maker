"""The pose library, pure: named poses as end-effector goals relative to the body, the body's frame from its bones,
control names resolved by pattern, and the errors that say whether a pose took. No `unreal`: the pose ops solve
it closed-loop on the real rig (key, evaluate, measure, correct) and the tests check it with plain numbers.

A pose is {effector: goal}. Effectors: hand_l, hand_r, foot_l, foot_r, pelvis, chest, head. A goal is
{"anchor": landmark, "offset": [forward, right, up] cm in the body's frame} (anchors: pelvis, chest, head, neck,
shoulder_l, shoulder_r, foot_l, foot_r, hand_l, hand_r, ground), or "keep" (stay where it is: planted feet), or a
world point [x, y, z]. The body's frame: origin the pelvis, forward the way it faces (from the clavicles or the
eyes), right 90 degrees clockwise from it seen from above (Unreal: Y is right of X), up +Z.
"""
from __future__ import annotations

import math
import re

EFFECTOR_BONES = {
    "hand_l": ("hand_l", "LeftHand"), "hand_r": ("hand_r", "RightHand"),
    "foot_l": ("foot_l", "LeftFoot"), "foot_r": ("foot_r", "RightFoot"),
    "pelvis": ("pelvis", "Hips"), "chest": ("spine_05", "spine_04", "Spine2"), "head": ("head", "Head"),
}
ANCHOR_BONES = {**EFFECTOR_BONES, "neck": ("neck_01", "neck_02", "Neck"),
                "shoulder_l": ("upperarm_l", "clavicle_l", "LeftArm"),
                "shoulder_r": ("upperarm_r", "clavicle_r", "RightArm")}
# control name patterns per effector, most specific first (the MetaHuman / UE5 mannequin body rig's usual names are
# hand_l_ik_ctrl, foot_l_ik_ctrl, body_ctrl, spine_*_fk_ctrl, head_fk_ctrl: unverified, so matched, never assumed)
CONTROL_PATTERNS = {
    "hand_l": [r"^hand_l_ik_ctrl$", r"hand.*_l_.*ik|ik.*hand.*_l|l_hand.*ik", r"^hand_l.*ctrl$", r"hand_l"],
    "hand_r": [r"^hand_r_ik_ctrl$", r"hand.*_r_.*ik|ik.*hand.*_r|r_hand.*ik", r"^hand_r.*ctrl$", r"hand_r"],
    "foot_l": [r"^foot_l_ik_ctrl$", r"foot.*_l_.*ik|ik.*foot.*_l|l_foot.*ik", r"^foot_l.*ctrl$", r"foot_l"],
    "foot_r": [r"^foot_r_ik_ctrl$", r"foot.*_r_.*ik|ik.*foot.*_r|r_foot.*ik", r"^foot_r.*ctrl$", r"foot_r"],
    "pelvis": [r"^body_ctrl$", r"^pelvis_ctrl$", r"^hips?_ctrl$", r"body|pelvis|hips"],
    "chest": [r"^chest_ctrl$", r"^spine_05.*ctrl$", r"^spine_04.*ctrl$", r"chest|spine_0?5|spine_0?4"],
    "head": [r"^head_ik_ctrl$", r"^head.*ctrl$", r"head"],
}

POSES = {
    "neutral": {"desc": "standing, arms relaxed at the sides", "goals": {
        "hand_l": {"anchor": "shoulder_l", "offset": [2, -8, -58]},
        "hand_r": {"anchor": "shoulder_r", "offset": [2, 8, -58]},
        "foot_l": "keep", "foot_r": "keep"}},
    "hands_on_hips": {"desc": "both hands on the hips, elbows out", "goals": {
        "hand_l": {"anchor": "pelvis", "offset": [2, -24, 6]},
        "hand_r": {"anchor": "pelvis", "offset": [2, 24, 6]},
        "foot_l": "keep", "foot_r": "keep"}},
    "arms_crossed": {"desc": "forearms folded across the chest", "goals": {
        "hand_l": {"anchor": "chest", "offset": [22, 9, -8]},
        "hand_r": {"anchor": "chest", "offset": [20, -9, -6]},
        "foot_l": "keep", "foot_r": "keep"}},
    "hands_clasped": {"desc": "hands together in front of the belly", "goals": {
        "hand_l": {"anchor": "pelvis", "offset": [24, -2, 14]},
        "hand_r": {"anchor": "pelvis", "offset": [24, 2, 14]},
        "foot_l": "keep", "foot_r": "keep"}},
    "thinking": {"desc": "right hand at the chin, left arm across under the elbow", "goals": {
        "hand_r": {"anchor": "head", "offset": [14, 2, -14]},
        "hand_l": {"anchor": "chest", "offset": [18, 4, -16]},
        "foot_l": "keep", "foot_r": "keep"}},
    "wave": {"desc": "right hand raised beside the head", "goals": {
        "hand_r": {"anchor": "shoulder_r", "offset": [10, 25, 45]},
        "foot_l": "keep", "foot_r": "keep"}},
    "point": {"desc": "right arm pointing forward at shoulder height", "goals": {
        "hand_r": {"anchor": "shoulder_r", "offset": [60, 6, 0]},
        "foot_l": "keep", "foot_r": "keep"}},
    "presenting": {"desc": "both palms open toward the camera, forearms forward", "goals": {
        "hand_l": {"anchor": "pelvis", "offset": [32, -28, 22]},
        "hand_r": {"anchor": "pelvis", "offset": [32, 28, 22]},
        "foot_l": "keep", "foot_r": "keep"}},
    "crouch": {"desc": "knees bent, hips lowered, feet planted", "goals": {
        "pelvis": {"anchor": "pelvis", "offset": [6, 0, -35]},
        "foot_l": "keep", "foot_r": "keep"}},
    "sit": {"desc": "seated on a chair: hips down `drop_cm` (45) and back 5, feet planted", "goals": {
        "pelvis": {"anchor": "pelvis", "offset": [-5, 0, -45]},
        "foot_l": "keep", "foot_r": "keep"}},
    "lean_forward": {"desc": "the chest forward over the hips", "goals": {
        "chest": {"anchor": "chest", "offset": [15, 0, -3]},
        "pelvis": "keep", "foot_l": "keep", "foot_r": "keep"}},
    "lean_back": {"desc": "the chest back behind the hips", "goals": {
        "chest": {"anchor": "chest", "offset": [-12, 0, -2]},
        "pelvis": "keep", "foot_l": "keep", "foot_r": "keep"}},
}
PARAMS = {"drop_cm": ("sit", "pelvis", 2)}  # a named parameter: (pose, effector, offset axis) it sets (negated)


def _first(bones: dict, names) -> tuple | None:
    for n in names:
        if n in bones and bones[n] is not None:
            return tuple(float(v) for v in bones[n])
    return None


def _norm(v):
    n = math.sqrt(sum(x * x for x in v))
    if n < 1e-9:
        raise ValueError("cannot normalise a zero vector")
    return tuple(x / n for x in v)


def body_frame(bones: dict) -> dict:
    """{"origin", "forward", "right", "up"} from bone world positions: the pelvis, and the facing from the
    clavicles/upper arms (else the eyes, else the feet's toes)."""
    pelvis = _first(bones, EFFECTOR_BONES["pelvis"])
    if pelvis is None:
        raise ValueError(f"no pelvis bone among {sorted(bones)[:10]}...: is this a UE5 / MetaHuman skeleton?")
    for l_names, r_names in ((("clavicle_l", "upperarm_l"), ("clavicle_r", "upperarm_r")),
                             (("FACIAL_L_Eye",), ("FACIAL_R_Eye",)), (("ball_l",), ("ball_r",))):
        lp, rp = _first(bones, l_names), _first(bones, r_names)
        if lp and rp:
            rx, ry = rp[0] - lp[0], rp[1] - lp[1]
            if math.hypot(rx, ry) > 1e-3:
                right = _norm((rx, ry, 0.0))
                fwd = (right[1], -right[0], 0.0)  # right is forward turned +90 yaw (Y right of X)
                return {"origin": pelvis, "forward": fwd, "right": right, "up": (0.0, 0.0, 1.0)}
    raise ValueError("cannot tell which way the body faces (no clavicle, eye or toe bones)")


def to_world(frame: dict, anchor_point, offset) -> tuple:
    f, r, u = frame["forward"], frame["right"], frame["up"]
    a = anchor_point
    return tuple(a[i] + offset[0] * f[i] + offset[1] * r[i] + offset[2] * u[i] for i in range(3))


def anchor(bones: dict, name: str):
    if name == "ground":
        feet = [_first(bones, ("foot_l",)), _first(bones, ("foot_r",))]
        feet = [p for p in feet if p]
        p = _first(bones, EFFECTOR_BONES["pelvis"])
        return (p[0], p[1], min(f[2] for f in feet) - 8.0) if feet else None
    if name not in ANCHOR_BONES:
        raise ValueError(f"unknown anchor {name!r}; one of {', '.join(sorted(ANCHOR_BONES))}, ground")
    return _first(bones, ANCHOR_BONES[name])


def pose_goals(pose, params: dict | None = None) -> dict:
    """A pose's goal table: a library name (with `params`), or a dict {effector: goal}."""
    if isinstance(pose, dict):
        goals = pose
    else:
        if pose not in POSES:
            raise ValueError(f"unknown pose {pose!r}; one of {', '.join(sorted(POSES))} (or give goals)")
        goals = {k: (dict(v, offset=list(v["offset"])) if isinstance(v, dict) else v)
                 for k, v in POSES[pose]["goals"].items()}
    for k, v in (params or {}).items():
        if k not in PARAMS:
            raise ValueError(f"unknown pose parameter {k!r}; one of {', '.join(PARAMS)}")
        name, eff, axis = PARAMS[k]
        if pose == name:
            goals[eff]["offset"][axis] = -abs(float(v))
    for eff in goals:
        if eff not in EFFECTOR_BONES:
            raise ValueError(f"unknown effector {eff!r}; one of {', '.join(EFFECTOR_BONES)}")
    return goals


def goals_world(pose, bones: dict, params: dict | None = None) -> dict:
    """{effector: [x, y, z]} where each effector should be, from the bones now (the rest pose or the shot's)."""
    frame = body_frame(bones)
    out = {}
    for eff, g in pose_goals(pose, params).items():
        if g == "keep":
            p = _first(bones, EFFECTOR_BONES[eff])
            if p is None:
                raise ValueError(f"{eff}: no bone {EFFECTOR_BONES[eff]} to keep")
            out[eff] = list(p)
        elif isinstance(g, (list, tuple)):
            out[eff] = [float(x) for x in g]
        else:
            a = anchor(bones, g["anchor"])
            if a is None:
                raise ValueError(f"{eff}: no bone for anchor {g['anchor']!r}")
            out[eff] = list(to_world(frame, a, g.get("offset", (0, 0, 0))))
    return out


def errors(goals: dict, bones: dict) -> dict:
    """{effector: (distance cm, [dx, dy, dz] goal minus bone)}."""
    out = {}
    for eff, g in goals.items():
        p = _first(bones, EFFECTOR_BONES[eff])
        if p is None:
            out[eff] = (float("inf"), [0.0, 0.0, 0.0])
            continue
        d = [g[i] - p[i] for i in range(3)]
        out[eff] = (math.sqrt(sum(x * x for x in d)), d)
    return out


def resolve_controls(controls: list, effectors, overrides: dict | None = None) -> tuple:
    """({effector: control name}, {effector: nearest candidates}) from the rig's real control names: an override
    wins, else the first pattern that matches exactly one name (several matches: the shortest name)."""
    names = list(controls)
    low = {n.lower(): n for n in names}
    found, missing = {}, {}
    for eff in effectors:
        if overrides and eff in overrides:
            if overrides[eff] not in names:
                missing[eff] = _near(overrides[eff], names)
            else:
                found[eff] = overrides[eff]
            continue
        hit = None
        for pat in CONTROL_PATTERNS[eff]:
            m = [low[n] for n in low if re.search(pat, n)]
            if m:
                hit = min(m, key=len)
                break
        if hit:
            found[eff] = hit
        else:
            missing[eff] = _near(eff, names)
    return found, missing


def _near(name: str, names: list) -> list:
    import difflib
    return difflib.get_close_matches(name.lower(), [n.lower() for n in names], n=3, cutoff=0.3)


def describe() -> dict:
    return {k: {"desc": v["desc"], "effectors": sorted(v["goals"])} for k, v in POSES.items()}
