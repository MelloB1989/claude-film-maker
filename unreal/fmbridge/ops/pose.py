"""Poses by name, on the real rig: "hands on hips", "sit", "arms crossed", "lean forward"... keyed on a character's
Control Rig at a frame of a sequence and solved closed-loop (key the effector's control in world space, let the
engine evaluate, measure the bone, correct), then checked numerically: every effector within a tolerance of its goal.

The library and the maths are ops/_pose.py (pure). Controls are never assumed: they are read from the rig on the
sequence (anim.rig_controls) and matched by pattern (hand_l_ik_ctrl, foot_l_ik_ctrl, body_ctrl, spine_05...); the
result names what it used. A rig track is made with `rig_class` when the actor has none (anim.rig_keys, WP4).
"""
from __future__ import annotations

import json

import unreal

from . import call, op
from . import _pose as P
from ._util import find_actor, actors
from ..errors import OpError, not_found

LSE = unreal.LevelSequenceEditorBlueprintLibrary
EAL = unreal.EditorAssetLibrary
ALL_BONES = tuple(dict.fromkeys(b for names in P.ANCHOR_BONES.values() for b in names)) + (
    "clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r", "FACIAL_L_Eye", "FACIAL_R_Eye", "ball_l", "ball_r")


def _skeletal(label: str, component: str = ""):
    a = find_actor(label)
    if a is None:
        raise not_found("actor", label, [x.get_actor_label() for x in actors()], hint="level.find lists them")
    comps = list(a.get_components_by_class(unreal.SkeletalMeshComponent))
    if component:
        comps = [c for c in comps if c.get_name() == component] or comps
    for c in comps:  # the one with a pelvis (a MetaHuman's Body, not its Face)
        try:
            if c.does_socket_exist("pelvis"):
                return c
        except Exception:
            continue
    if not comps:
        raise OpError(f"{label!r} has no skeletal mesh", code="bad_args", hint="poses need a UE5/MetaHuman body")
    return comps[0]


def bones_of(label: str, component: str = "") -> dict:
    """World positions of the pose library's bones on the actor's body (fetched afresh: Blueprint components go
    stale)."""
    c = _skeletal(label, component)
    out = {}
    for b in ALL_BONES:
        try:
            if c.does_socket_exist(b):
                p = c.get_socket_location(b)
                out[b] = [float(p.x), float(p.y), float(p.z)]
        except Exception:
            continue
    return out


def _scrub(frame: int, ticks: int = 3):
    LSE.set_current_time(int(frame) + 1)
    yield
    LSE.set_current_time(int(frame))
    for _ in range(ticks):
        yield


def _rig(sequence: str, label: str, component: str, rig_class: str):
    """(sequence asset, control rig, control names): the rig track on the actor's binding, made from `rig_class`
    when missing."""
    from .anim import _rig_on
    seq = EAL.load_asset(sequence)
    if seq is None:
        raise not_found("level sequence", sequence, [], hint="seq.new makes one")
    if LSE.get_current_level_sequence() != seq:
        LSE.open_level_sequence(seq)  # world-space control writes need the sequence open in the level editor
    p = _rig_on(seq, label, component)
    if p is None:
        if not rig_class:
            raise OpError(f"{label} has no Control Rig track in {sequence}", code="not_found",
                          hint="pass rig_class (the body's Control Rig Blueprint, e.g. a MetaHuman's body rig) "
                               "to make one")
        call("anim.rig_keys", sequence=sequence, label=label, keys={}, component=component, rig_class=rig_class)
        p = _rig_on(seq, label, component)
        if p is None:
            raise OpError("the engine made no control rig track", code="engine")
    rig = p.get_editor_property("control_rig")
    names = [str(k.get_editor_property("name")) for k in rig.get_hierarchy().get_controls()]  # ScriptName of GetControlKeys (RigHierarchy.h:1181)
    return seq, rig, names


def _rest(seq, label: str, bones: dict, reset: bool = False) -> dict:
    """The character's rest bones for this sequence: captured the first time a pose is applied (asset metadata
    `fm_pose_rest:<label>` on the sequence), so poses are relative to the rest pose and re-applying converges."""
    tag = f"fm_pose_rest:{label}"
    have = EAL.get_metadata_tag(seq, tag) if not reset else ""
    if have:
        return json.loads(have)
    EAL.set_metadata_tag(seq, tag, json.dumps({k: [round(x, 3) for x in v] for k, v in bones.items()}))
    return bones


def _xf(t, delta):
    """A world transform moved by `delta` cm, its rotation kept."""
    loc = t.translation
    r = t.rotation
    rot = r.rotator() if hasattr(r, "rotator") else r
    return unreal.Transform(location=unreal.Vector(loc.x + delta[0], loc.y + delta[1], loc.z + delta[2]),
                            rotation=rot, scale=unreal.Vector(1.0, 1.0, 1.0))


def _report(goals: dict, bones: dict, tol: float, frame: int, label: str, used: dict) -> tuple:
    errs = P.errors(goals, bones)
    issues = []
    for eff, (d, delta) in errs.items():
        if d > tol:
            issues.append({"code": "pose.effector_off", "severity": "fail" if d > 3 * tol else "warn",
                           "message": f"{label} {eff} is {d:.1f} cm from its goal (tolerance {tol:g})",
                           "fix": f"pose.apply again with more iterations, or check the control "
                                  f"{used.get(eff, '?')} drives {eff}", "frame": frame, "subject": label,
                           "value": round(d, 2), "expected": tol})
    return {eff: round(d, 2) for eff, (d, _) in errs.items()}, issues


@op("pose.library", mutates=False, idempotent=True, tags=["animation"])
def library(*, pose: str = "") -> dict:
    """The named poses: what each looks like and which effectors it sets (hand_l/r, foot_l/r, pelvis, chest, head),
    with the goal table (anchor + [forward, right, up] cm in the body's frame) for one `pose`.

    Example: film-ue op pose.library pose=hands_on_hips
    """
    if pose:
        if pose not in P.POSES:
            raise not_found("pose", pose, list(P.POSES))
        return {"pose": pose, **P.POSES[pose], "params": {k: v[0] for k, v in P.PARAMS.items() if v[0] == pose}}
    return {"poses": P.describe(), "effectors": list(P.EFFECTOR_BONES), "anchors": sorted(P.ANCHOR_BONES) + ["ground"]}


@op("pose.apply", mutates=True, idempotent=True, tags=["animation", "sequencer"])
def apply(*, label: str, sequence: str, frame: int, pose: str | dict, params: dict | None = None,
          component: str = "", rig_class: str = "", controls: dict | None = None, tolerance_cm: float = 1.0,
          iterations: int = 8, reset_rest: bool = False):
    """Pose a character at a frame of a sequence: key its Control Rig so each effector reaches the pose's goal, solved
    closed-loop on what the engine evaluates, then report the remaining error per effector.

    Args: label: the character (its body's skeletal mesh; `component` names it, else the one with a pelvis).
    pose: a library name (pose.library) or {effector: {"anchor", "offset": [fwd, right, up]} | "keep" | [x,y,z]}.
    params: {"drop_cm": 45} for sit. rig_class: the body's Control Rig Blueprint, to make the rig track if missing.
    controls: {effector: control name} overrides for the pattern match. tolerance_cm, iterations: the solve.
    Goals are relative to the character's REST pose, captured the first time a pose is applied in this sequence
    (stored on it); `reset_rest` captures it again (after the character moved).
    A multi-tick job. Re-running converges (the controls are re-solved to the same goals).
    Returns: {"pass", "errors_cm": {effector: cm}, "controls": {effector: control}, "iterations", "goals",
    "issues", "changed"}.
    Example: film-ue op pose.apply label=Host sequence=/Game/Seq/S010 frame=48 pose=hands_on_hips
    """
    try:
        P.pose_goals(pose, params)
    except ValueError as e:
        raise OpError(str(e), code="bad_args", hint="pose.library lists the poses") from None
    seq, rig, names = _rig(sequence, label, component, rig_class)
    yield from _scrub(frame)
    bones = bones_of(label, component)
    rest = _rest(seq, label, bones, reset_rest)
    try:
        goals = P.goals_world(pose, rest, params)
    except ValueError as e:
        raise OpError(f"{label}: {e}", code="bad_args") from None
    used, missing = P.resolve_controls(names, goals, controls)
    if missing:
        eff = next(iter(missing))
        raise OpError(f"{label}'s rig has no control for {sorted(missing)}", code="not_found",
                      candidates=missing[eff], details={"controls": names},
                      hint="pass controls={effector: name} (anim.rig_controls lists the rig's controls)")
    CR = unreal.ControlRigSequencerLibrary
    fn = unreal.FrameNumber(int(frame))
    unit = unreal.MovieSceneTimeUnit.DISPLAY_RATE
    done = 0
    for it in range(int(iterations)):
        errs = P.errors(goals, bones)
        todo = {e: d for e, (dist, d) in errs.items() if dist > tolerance_cm}
        if not todo:
            break
        for eff, delta in todo.items():
            ctrl = used[eff]
            t = CR.get_control_rig_world_transform(seq, rig, ctrl, fn, unit)
            CR.set_control_rig_world_transform(seq, rig, ctrl, fn, _xf(t, delta), unit, True)
        done = it + 1
        LSE.refresh_current_level_sequence()
        yield from _scrub(frame)
        bones = bones_of(label, component)
    errors, issues = _report(goals, bones, tolerance_cm, frame, label, used)
    EAL.save_asset(sequence)
    return {"pass": not any(i["severity"] == "fail" for i in issues), "errors_cm": errors, "controls": used,
            "iterations": done, "goals": {k: [round(x, 2) for x in v] for k, v in goals.items()}, "issues": issues,
            "pose": pose if isinstance(pose, str) else "custom", "frame": int(frame), "changed": done > 0}


@op("pose.check", mutates=False, idempotent=True, tags=["animation", "qa"])
def check(*, label: str, sequence: str, frame: int, pose: str | dict, params: dict | None = None,
          component: str = "", tolerance_cm: float = 2.0, rest: dict | None = None):
    """Is the character in the pose at that frame? Scrub there and measure each effector against the pose's goals.
    Goals are anchored on the rest pose pose.apply stored on the sequence, else on the bones now (a held pose then
    checks against itself); `rest` ({bone: [x, y, z]}) overrides both. A multi-tick job.

    Returns: {"pass", "issues", "metrics": {"errors_cm"}}.
    Example: film-ue op pose.check label=Host sequence=/Game/Seq/S010 frame=60 pose=hands_on_hips
    """
    seq = EAL.load_asset(sequence)
    if seq is None:
        raise not_found("level sequence", sequence, [])
    if LSE.get_current_level_sequence() != seq:
        LSE.open_level_sequence(seq)
    yield from _scrub(frame)
    bones = bones_of(label, component)
    stored = EAL.get_metadata_tag(seq, f"fm_pose_rest:{label}")
    try:
        goals = P.goals_world(pose, rest or (json.loads(stored) if stored else bones), params)
    except ValueError as e:
        raise OpError(f"{label}: {e}", code="bad_args", hint="pose.library lists the poses") from None
    errors, issues = _report(goals, bones, tolerance_cm, frame, label, {})
    return {"pass": not any(i["severity"] == "fail" for i in issues), "issues": issues,
            "metrics": {"errors_cm": errors}}
