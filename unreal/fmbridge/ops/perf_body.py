"""Body life (perfkit.bodylife) on a real skeleton: measure which local axis of each spine, clavicle and pelvis bone
bends the body forward, sideways or turns it (perf.calibrate_body, once per body skeleton), then bake breathing,
weight shifts and the torso following the head into an ADDITIVE animation (anim.body_life) that rides on any idle in
Sequencer. The additive's base is its own first frame (the rest pose), so the body mesh's proportions never leak into
the offsets."""
from __future__ import annotations

import json
import math
import os

import unreal

from . import call, op
from .assets import EAL, load
from ..errors import OpError, not_found
from ..perfkit import bodylife as BL

AL = unreal.AnimationLibrary
LSE = unreal.LevelSequenceEditorBlueprintLibrary
BONES = list(BL.SPINE) + ["clavicle_l", "clavicle_r", "pelvis"]
PROBES = ["head", "clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r", "foot_l", "foot_r", "ball_l", "ball_r"]


def _saved(name: str) -> str:
    d = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "fmbridge", "perf")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _calib_file(skeleton: str) -> str:
    return _saved(f"body_{skeleton.rsplit('/', 1)[-1]}.json")


def _v(a, b):
    return [x - y for x, y in zip(a, b)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _unit(v):
    n = math.sqrt(_dot(v, v)) or 1.0
    return [x / n for x in v]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _mid(a, b):
    return [(x + y) / 2 for x, y in zip(a, b)]


def _local_pose(label: str, component: str, bones: list) -> dict:
    """{bone: {"t": [x, y, z], "q": [x, y, z, w], "s": [x, y, z]}} in parent-bone space, as the component shows now."""
    from .seq import component_of
    comp = component_of(label, component)
    out = {}
    for b in bones:
        t = comp.get_socket_transform(b, unreal.RelativeTransformSpace.RTS_PARENT_BONE_SPACE)
        p, q, s = t.translation, t.rotation, t.scale3d
        out[b] = {"t": [p.x, p.y, p.z], "q": [q.x, q.y, q.z, q.w], "s": [s.x, s.y, s.z]}
    return out


def _write_tracks(anim, tracks: dict, n_keys: int) -> None:
    """Bone tracks {bone: [(t, q, s)] * n_keys} in one bracket (each key list as long as the animation's keys)."""
    ctrl = anim.get_editor_property("controller")
    have = {str(n) for n in AL.get_animation_track_names(anim)}
    ctrl.open_bracket("fmbridge body life", False)
    try:
        for b, keys in tracks.items():
            if b not in have:
                ctrl.add_bone_curve(b, False)
            ctrl.set_bone_track_keys(b, [unreal.Vector(*k[0]) for k in keys], [unreal.Quat(*k[1]) for k in keys],
                                     [unreal.Vector(*k[2]) for k in keys], False)
    finally:
        ctrl.close_bracket(False)


@op("perf.calibrate_body", mutates=True, idempotent=True, tags=["slow"])
def calibrate_body(*, label: str, component: str = "Body", scratch: str = "/Game/_Perf/CalibrateBody",
                   degrees: float = 10.0, bones: list | None = None):
    """Measure, on the real body skeleton, which local axis (and sign) of each spine, clavicle and pelvis bone bends the
    body forward (flex), to the character's left (side; for a clavicle: lifts it) and turns it left (twist), and which
    of the pelvis's parent axes shifts it to the left; with the bones' rest pose. Saved per skeleton
    (Saved/fmbridge/perf/body_<skeleton>.json) for anim.body_life. Plays scratch animations on the actor's body in a
    scratch sequence and samples the head, clavicles, upper arms and feet ("forward" is where the feet point).
    A multi-tick job, ~1 min.

    Returns: {"skeleton", "axes": {bone: {"flex": [axis, sign], "side": [...], "twist": [...]}}, "shift_axis",
    "file", "raw"}.
    Example: film-ue op perf.calibrate_body label=Presenter
    """
    from .anim import _await_change, _skeleton_path, new as anim_new
    from .seq import component_of, sample
    bones = list(bones or BONES)
    comp = component_of(label, component)
    mesh = comp.get_skeletal_mesh_asset()
    if mesh is None:
        raise OpError(f"{label}.{component} has no skeletal mesh", code="bad_args")
    have = {str(comp.get_bone_name(i)) for i in range(comp.get_num_bones())}
    missing = [b for b in bones + PROBES if b not in have]
    if missing:
        raise OpError(f"{label}.{component} has no bones {missing}", code="unsupported",
                      hint="body life expects the UE5 / MetaHuman body skeleton (spine_01..05, clavicle_l/r, pelvis, "
                           "head, upperarm_l/r, foot_l/r, ball_l/r); pass `bones` to calibrate a subset")
    mesh_path = mesh.get_path_name().split(".")[0]
    skel = _skeleton_path(mesh)
    anim_path, seq_path = f"{scratch}/AS_body_probe", f"{scratch}/LS_body_probe"
    anim_new(path=anim_path, skeleton=mesh_path, length_s=2.0, fps=30, replace=True)
    call("seq.new", path=seq_path, start=0, end=48, fps=24, replace=True)
    call("seq.anim", path=seq_path, label=label, component=component,
         sections=[{"anim": anim_path, "start": 0, "end": 48, "loop": True}])
    frame = 12

    def measure():
        m = yield from sample(seq_path, label, component, PROBES, frames=[frame], ticks=3)
        return m

    rest = yield from measure()
    ref = _local_pose(label, component, bones)
    P = {b: rest["bones"][b][0][:3] for b in PROBES}
    up = [0.0, 0.0, 1.0]
    fwd = _v(_mid(P["ball_l"], P["ball_r"]), _mid(P["foot_l"], P["foot_r"]))
    fwd = _unit([fwd[0], fwd[1], 0.0])
    left = _unit(_cross(fwd, up))  # Unreal is left-handed: up x fwd is the character's right
    a = load(anim_path)
    n_keys = AL.get_num_keys(a)
    last = rest

    def pose_with(bone, axis=None, shift=None):
        r = ref[bone]
        q = r["q"]
        t = list(r["t"])
        if axis:
            e = {"x": (degrees, 0, 0), "y": (0, degrees, 0), "z": (0, 0, degrees)}[axis]
            q = BL.qmul(r["q"], BL.quat_from_euler_xyz(*e))
        if shift:
            k = "xyz".index(shift)
            t[k] += 2.0
        return {bone: [(t, q, r["s"])] * n_keys}

    raw, axes = {}, {}
    for b in bones:
        scores = {}
        for ax in "xyz":
            _write_tracks(a, pose_with(b, ax), n_keys)
            EAL.save_asset(anim_path)
            probe = "upperarm_" + b[-1] if b.startswith("clavicle") else "clavicle_l"  # off the spine's axis:
            m = yield from _await_change(lambda fs: measure(), frame, probe, last["bones"][probe][0])  # moves for all
            last = m
            d = {p: _v(m["bones"][p][0][:3], P[p]) for p in PROBES}
            if b.startswith("clavicle"):
                arm = d["upperarm_" + b[-1]]
                scores[ax] = {"flex": _dot(arm, fwd), "side": _dot(arm, up), "twist": _dot(arm, left) * (1 if b[-1] == "l" else -1)}
            else:
                scores[ax] = {"flex": _dot(d["head"], fwd), "side": _dot(d["head"], left),
                              "twist": (_dot(d["clavicle_r"], fwd) - _dot(d["clavicle_l"], fwd)) / 2.0}
            # restore this bone before the next axis
            _write_tracks(a, pose_with(b), n_keys)
        raw[b] = {ax: {k: round(v, 3) for k, v in s.items()} for ax, s in scores.items()}
        left_axes = set("xyz")
        pick = {}
        for comp_name in ("flex", "side", "twist"):
            ax = max(left_axes, key=lambda x: abs(scores[x][comp_name]))
            v = scores[ax][comp_name]
            if abs(v) < 0.05:
                raise OpError(f"{b}: no local axis moves the body ({comp_name}): {raw[b]}", code="failed",
                              hint="is the body driven by Sequencer (its own anim instance)? see perf.calibrate_body")
            pick[comp_name] = [ax, 1.0 if v > 0 else -1.0]
            left_axes.discard(ax)
        axes[b] = pick
    shift_axis = None
    if "pelvis" in bones:
        best = None
        for ax in "xyz":
            _write_tracks(a, pose_with("pelvis", shift=ax), n_keys)
            EAL.save_asset(anim_path)
            m = yield from _await_change(lambda fs: measure(), frame, "head", last["bones"]["head"][0])
            last = m
            s = _dot(_v(m["bones"]["head"][0][:3], P["head"]), left)
            raw.setdefault("pelvis_shift", {})[ax] = round(s, 3)
            if best is None or abs(s) > abs(best[1]):
                best = (ax, s)
            _write_tracks(a, pose_with("pelvis"), n_keys)
        shift_axis = [best[0], 1.0 if best[1] > 0 else -1.0]
    out = {"skeleton": skel, "axes": axes, "shift_axis": shift_axis, "ref": ref, "measured": True}
    path = _calib_file(skel)
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    if LSE.get_current_level_sequence():
        LSE.close_level_sequence()
    return {"skeleton": skel, "axes": axes, "shift_axis": shift_axis, "file": path, "raw": raw, "changed": True}


@op("anim.body_life", mutates=True, idempotent=True)
def body_life(*, out: str, body_mesh: str, length_s: float, state: str = "rest", face_anim: str = "",
              follow: float = 0.15, breath_deg: float = 0.6, clavicle_deg: float = 1.0, shift_cm: float = 1.5,
              seed: int = 0) -> dict:
    """An additive animation of body life for a body skeleton: breathing (spine extension and clavicle lift on each
    inhale, at a rate by `state`: calm, rest, listen, talk, focus, nervous), slow weight shifts (`shift_cm` of pelvis,
    the spine bending back over the feet) and, with `face_anim`, the torso following the head's turns (`follow` of
    its yaw, a beat later). Layer it over any idle: seq.anim with replace=false, or a spec's character.body_life.
    Needs perf.calibrate_body for this skeleton.

    Args: out: the additive animation's path (re-made). body_mesh: the body SkeletalMesh. length_s: seconds.
    face_anim: a face animation whose HeadYaw the torso follows. Others: amplitudes in degrees / cm.
    Returns: {"out", "changed", "breaths_per_min", "shifts", "bones"}.
    Example: film-ue op anim.body_life out=/Game/Perf/AS_life body_mesh=/Game/MetaHumans/Ada/Body/m_med_nrw_body length_s=12 state=talk
    """
    from .anim import _anim, _keys, _skeleton_path, new as anim_new
    from .perf import signs_for
    from ..perfkit import curves as C
    if not EAL.does_asset_exist(body_mesh.split(".")[0]):
        raise not_found("body mesh", body_mesh, hint="the MetaHuman's body SkeletalMesh (mh.body_mesh)")
    skel = _skeleton_path(load(body_mesh.split(".")[0]))
    path = _calib_file(skel)
    if not os.path.exists(path):
        raise OpError(f"no body calibration for {skel}", code="conflict",
                      hint="run perf.calibrate_body label=<an actor with this body> once (it measures the bone axes)")
    with open(path) as f:
        cal = json.load(f)
    head_yaw = None
    if face_anim:
        fa = _anim(face_anim)
        if AL.does_curve_exist(fa, "HeadYaw", unreal.RawCurveTrackTypes.RCT_FLOAT):
            ht, hv = _keys(fa, "HeadYaw")
            sg = signs_for(_skeleton_path(fa)).yaw
            head_yaw = (lambda t: sg * C.at(ht, hv, t))
    anim_new(path=out, skeleton=body_mesh, length_s=length_s, fps=30, replace=True)
    a = load(out)
    n_keys = AL.get_num_keys(a)
    life = BL.plan(0.0, length_s, state=state, breath_deg=breath_deg, clavicle_deg=clavicle_deg, shift_cm=shift_cm,
                   follow=follow, head_yaw=head_yaw, seed=seed)
    # the first frame is the rest pose (the additive's base): every offset relative to its value there
    for comps in life["bones"].values():
        for k, vals in comps.items():
            comps[k] = [v - vals[0] for v in vals]
    shift = [v - life["pelvis_shift_cm"][0] for v in life["pelvis_shift_cm"]]
    local = BL.to_local(life, cal["axes"])
    times = life["times"]
    key_t = [k * length_s / max(1, n_keys - 1) for k in range(n_keys)]
    tracks = {}
    for b, rot in local.items():
        r = cal["ref"][b]
        keys = []
        for t in key_t:
            x, y, z = (C.at(times, rot[a_], t) for a_ in "xyz")
            q = BL.qmul(r["q"], BL.quat_from_euler_xyz(x, y, z))
            pos = list(r["t"])
            if b == "pelvis" and cal.get("shift_axis"):
                ax, sign = cal["shift_axis"]
                pos["xyz".index(ax)] += sign * C.at(times, shift, t)
            keys.append((pos, q, r["s"]))
        tracks[b] = keys
    _write_tracks(a, tracks, n_keys)
    AL.set_additive_animation_type(a, unreal.AdditiveAnimationType.AAT_LOCAL_SPACE_BASE)
    AL.set_additive_base_pose_type(a, unreal.AdditiveBasePoseType.ABPT_LOCAL_ANIM_FRAME)
    a.set_editor_property("ref_frame_index", 0)
    EAL.save_asset(out)
    return {"out": out, "changed": True, "breaths_per_min": life["breaths_per_min"], "shifts": life["shifts"],
            "bones": sorted(tracks)}
