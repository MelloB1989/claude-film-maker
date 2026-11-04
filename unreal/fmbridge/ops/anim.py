"""Animation curves: read and write a sequence's float curves, and lock a talking face's gaze on the camera.

A MetaHuman facial animation drives the face rig through curves: CTRL_expressions_* (eyeLookLeftL, jawOpen, ...) and,
with head movement on, HeadYaw/HeadPitch/HeadRoll (degrees). The audio solver lets the eyes wander with the head; a
presenter keeps them on the lens. gaze_lock rewrites the eye-look curves so the eyes counter the head's turn (plus the
camera's offset), with small natural saccades, and copies the result to a new sequence."""
from __future__ import annotations

import math
import random

import unreal

from . import op
from .assets import EAL, free, load

AL = unreal.AnimationLibrary
FLOAT = unreal.RawCurveTrackTypes.RCT_FLOAT


def _keys(anim, name):
    t, v = AL.get_float_keys(anim, name)
    return list(t), list(v)


def _curve_id(anim, name):
    """An FAnimationCurveIdentifier for a float curve: SetCurveIdentifier on a fresh struct (a ref-self script method:
    CurveIdentifier.h:150); the skeleton route is deprecated in 5.8 and logs a warning per call, so it is only the
    fallback."""
    try:
        cid = unreal.AnimationCurveIdentifier()
        cid.set_curve_identifier(name, FLOAT)
        return cid
    except Exception:
        return unreal.AnimationCurveIdentifierExtensions.get_curve_identifier(anim.get_skeleton(), name, FLOAT)


def _write(anim, curves: dict) -> None:
    """Replace float curves {name: (times, values)} in one controller bracket: each curve's keys in one call, and one
    recompression for the lot. AnimationLibrary.add_float_curve_keys recompresses the animation after every key
    (a few ms on a short clip, tens on a long face: a long curve held the game thread for many minutes)."""
    ctrl = anim.get_editor_property("controller")
    lin = unreal.RichCurveInterpMode.RCIM_LINEAR
    ctrl.open_bracket("fmbridge curves", False)
    try:
        for name, (times, values) in curves.items():
            cid = _curve_id(anim, name)
            if not AL.does_curve_exist(anim, name, FLOAT):
                ctrl.add_curve(cid, 4, False)  # AACF_Editable
            ctrl.set_curve_keys(cid, [unreal.RichCurveKey(time=float(t), value=float(v), interp_mode=lin)
                                      for t, v in zip(times, values)], False)
    finally:
        ctrl.close_bracket(False)


def _set(anim, name, times, values):
    _write(anim, {name: (times, values)})


@op("anim.curves", mutates=False, idempotent=True)
def curves(anim: str, contains: str = "") -> list:
    """A sequence's float curve names (containing `contains`).
    Example: film-ue op anim.curves anim=/Game/Speech/Anim/AS_line1 contains=eyeLook
    """
    return [str(n) for n in AL.get_animation_curve_names(load(anim), FLOAT) if contains.lower() in str(n).lower()]


@op("anim.curve", mutates=False, idempotent=True)
def curve(anim: str, name: str, every: int = 1) -> dict:
    """One curve's keys (every n-th): times and values, with its range.
    Example: film-ue op anim.curve anim=/Game/Speech/Anim/AS_line1 name=HeadYaw
    """
    t, v = _keys(load(anim), name)
    return {"times": t[::every], "values": v[::every], "min": min(v) if v else None, "max": max(v) if v else None}


@op("anim.set_curve", mutates=True, idempotent=True)
def set_curve(anim: str, name: str, times: list, values: list) -> int:
    """Replace a curve with these keys (times in seconds). anim.write_curves writes many in one batch.
    Example: film-ue op anim.set_curve anim=/Game/Perf/AS_face name=CTRL_expressions_browRaiseInL 'times=[0,1,2]' 'values=[0,0.5,0]'
    """
    a = load(anim)
    _set(a, name, times, values)
    EAL.save_asset(anim)
    return len(times)


@op("anim.scale_curves", mutates=True, idempotent=False)
def scale_curves(anim: str, scale: dict, offset: dict | None = None) -> dict:
    """Multiply (then offset) curves by name: {"HeadYaw": 0.6, "CTRL_expressions_browRaiseInL": 1.3}. Not idempotent:
    each call scales again.
    Example: film-ue op anim.scale_curves anim=/Game/Speech/Anim/AS_line1 'scale={"HeadYaw": 0.6}'
    """
    a, out = load(anim), {}
    for name, k in scale.items():
        if not AL.does_curve_exist(a, name, FLOAT):
            continue
        t, v = _keys(a, name)
        b = (offset or {}).get(name, 0.0)
        _set(a, name, t, [x * k + b for x in v])
        out[name] = len(t)
    EAL.save_asset(anim)
    return out


EYES = {"L": "FACIAL_L_Eye", "R": "FACIAL_R_Eye"}
LOOK = ("Left", "Right", "Up", "Down")


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return [a[0] / n, a[1] / n, a[2] / n]


def _axes(x):
    return [x[3:6], x[6:9], x[9:12]]


def _local(v, x):
    """A world direction in a sampled bone's own axes."""
    return [_dot(v, ax) for ax in _axes(x)]


def _angles(lv, g, u):
    """Yaw and pitch (degrees) of a local direction against the gaze axis g and up axis u (signed local axes)."""
    s = 6 - abs(g) - abs(u)  # the remaining axis, 1-based
    fwd, up, side = lv[abs(g) - 1] * (1 if g > 0 else -1), lv[abs(u) - 1] * (1 if u > 0 else -1), lv[s - 1]
    return math.degrees(math.atan2(side, fwd)), math.degrees(math.atan2(up, math.hypot(fwd, side)))


def _write_eyes(a, times, curves):
    _write(a, {f"CTRL_expressions_eyeLook{d}{side}": (v if isinstance(v, tuple) else (times, v))
               for (side, d), v in curves.items()})


def _merged(times, curves, orig, gap):
    """Solved eye curves on `times`, and the animation's own keys (`orig`) wherever no solved time is near (more than
    1.5 `gap` seconds away): the eyes wander as recorded outside the aimed range. Each curve as (times, values)."""
    if len(times) < 2:
        return curves
    out = {}
    for k, v in curves.items():
        ot, ov = orig.get(k, ([], []))
        keep = [(t, x) for t, x in zip(ot, ov) if min(abs(t - s) for s in times) > 1.5 * gap]
        pts = sorted(list(zip(times, v)) + keep)
        out[k] = ([t for t, _ in pts], [x for _, x in pts])
    return out


def _await_change(measure, frame: int, bone: str, before: list, timeout: float = 30.0):
    """After editing an animation: the editor swaps in the recompressed data a moment later (longer with many bone
    tracks), so measure `bone` at `frame` until it has moved from `before`, or `timeout` s. Returns the measurement."""
    import time
    t0 = time.time()
    while True:
        m = yield from measure([frame])
        x = m["bones"][bone][0]
        if max(abs(a - b) for a, b in zip(x[3:], before[3:])) > 1e-5 or time.time() - t0 > timeout:
            return m
        yield 0.5


@op("anim.gaze_lock", mutates=True, idempotent=True, tags=["slow"])
def gaze_lock(sequence: str, actor_label: str, anim: str, out: str, camera: str = "", component: str = "Face",
              saccades: float = 0.5, seed: int = 3, every: int = 2, iterations: int = 2, target=None,
              target_offset=None, frames=None):
    """Keep a talking face's eyes on the lens, measured rather than guessed: `out` (a copy of `anim`) goes on
    `component`'s track in `sequence` (on the sections that play `anim`, wherever they start); the eye-look curves are
    calibrated on the rig, then solved per frame from the eye bones' real pose (head and body motion included)
    toward `camera`, with small saccades, and refined `iterations` times against a fresh measurement.
    `target` aims the eyes elsewhere: a point [x, y, z], an actor (+ `target_offset` in its frame) or
    "Label:Component:bone" (her eyes: "Presenter:Face:FACIAL_L_Eye"); with `frames` [first, last] only in that range
    (the camera, if given, elsewhere). Frames with neither keep the animation's own eye curves. Returns the angle error
    per pass. A multi-tick job.
    Example: film-ue op anim.gaze_lock sequence=/Game/Shots/S010 actor_label=Presenter anim=/Game/Speech/Anim/AS_line1 out=/Game/Speech/Anim/AS_line1_eyes camera=CAM_A
    """
    from .seq import _comp_binding, sample, set_anim
    if not camera and target is None:
        raise ValueError("gaze_lock needs a camera or a target")
    if out != anim:
        free(out)
    EAL.duplicate_asset(anim, out)
    a = load(out)
    length = a.get_editor_property("sequence_length")
    orig = {(s, d): _keys(a, f"CTRL_expressions_eyeLook{d}{s}") for s in EYES for d in LOOK}
    zero2 = {(s, d): [0.0, 0.0] for s in EYES for d in LOOK}
    _write_eyes(a, [0.0, length], zero2)
    EAL.save_asset(out)
    set_anim(sequence, component, out, label=actor_label, only=anim)
    yield 1.0
    seq = load(sequence)
    fps = seq.get_display_rate().numerator / seq.get_display_rate().denominator
    tick = seq.get_tick_resolution().numerator / seq.get_tick_resolution().denominator
    # where the animation plays: the section on this actor's track that carries it (frame -> seconds into the anim)
    secs = [x for t in _comp_binding(seq, actor_label, component, create=False).find_tracks_by_type(
        unreal.MovieSceneSkeletalAnimationTrack) for x in t.get_sections()
        if (x.get_editor_property("params").get_editor_property("animation") or a).get_path_name().split(".")[0] == out]
    sec = min(secs, key=lambda x: x.get_start_frame()) if secs else None
    s0 = sec.get_start_frame() if sec and sec.has_start_frame() else 0
    s1 = sec.get_end_frame() if sec and sec.has_end_frame() else seq.get_playback_end()
    prm = sec.get_editor_property("params") if sec else None
    rate = prm.get_editor_property("play_rate") if prm else 1.0
    rate = rate.to_fixed_play_rate() if hasattr(rate, "to_fixed_play_rate") else rate  # a time-warp variant since 5.5
    off = 0.0
    for k in ("first_loop_start_frame_offset", "start_frame_offset"):
        try:
            off = prm.get_editor_property(k).value / tick
            break
        except Exception:
            pass

    def at(f):  # seconds into the animation at sequence frame f
        return off + (f - s0) / fps * rate

    span = frames  # `frames` is reused for the solved frames below: aimed() keeps the range it was given

    def aimed(f):  # what the eyes look at on frame f: "target", "camera" or None
        if target is not None and (span is None or span[0] <= f <= span[1]):
            return "target"
        return "camera" if camera else None
    solve = [f for f in range(max(s0, seq.get_playback_start()), min(s1, seq.get_playback_end()), every)
             if at(f) <= length and aimed(f)]
    if not solve:
        raise ValueError(f"no frame of {sequence} plays {anim} with something to look at")
    f0 = solve[0]
    bones = list(EYES.values())
    probe = EYES["L"]

    def measure(fs):
        m = yield from sample(sequence, actor_label, component, bones, frames=fs, ticks=3, camera=camera,
                              target=target, target_offset=target_offset)
        m["aim"] = [m["target"][i] if aimed(f) == "target" else m["camera"][i] for i, f in enumerate(fs)]
        return m

    # calibrate on the first frame: each look direction at full against none
    base = yield from measure([f0])
    g, u = {}, {}
    for side, bone in EYES.items():
        x = base["bones"][bone][0]
        to_cam = _norm([base["aim"][0][k] - x[k] for k in range(3)])
        lc = _local(to_cam, x)
        k = max(range(3), key=lambda i: abs(lc[i]))
        g[side] = (k + 1) * (1 if lc[k] > 0 else -1)
        lu = _local([0.0, 0.0, 1.0], x)
        k2 = max((i for i in range(3) if i != k), key=lambda i: abs(lu[i]))
        u[side] = (k2 + 1) * (1 if lu[k2] > 0 else -1)
    cal, last = {}, base
    for d in LOOK:
        c = dict(zero2)
        c.update({(s, d): [1.0, 1.0] for s in EYES})
        _write_eyes(a, [0.0, length], c)
        m = yield from _await_change(measure, f0, probe, last["bones"][probe][0])
        last = m
        for side, bone in EYES.items():
            gw = _axes(m["bones"][bone][0])[abs(g[side]) - 1]
            gw = [v * (1 if g[side] > 0 else -1) for v in gw]
            cal[(side, d)] = _angles(_local(gw, base["bones"][bone][0]), g[side], u[side])

    # the eyes' rest pose through the whole shot, then the solve
    _write_eyes(a, [0.0, length], zero2)
    yield from _await_change(measure, f0, probe, last["bones"][probe][0])
    frames = solve
    rest = yield from measure(frames)
    times = [at(f) for f in frames]
    rnd = random.Random(seed)
    off, hold = [], 0.0
    sh = sv = 0.0
    for i, t in enumerate(times):  # fixations: mostly dead on the lens, now and then a tiny flick
        hold -= (times[i] - times[i - 1]) if i else 0.0
        if hold <= 0:
            hold = rnd.uniform(0.5, 1.8)
            sh, sv = (rnd.gauss(0, saccades), rnd.gauss(0, saccades * 0.6)) if rnd.random() < 0.65 else (0.0, 0.0)
        off.append((sh, sv))

    def need(sample_, i, side):
        x = sample_["bones"][EYES[side]][i]
        to_cam = _norm([sample_["aim"][i][k] - x[k] for k in range(3)])
        return _angles(_local(to_cam, x), g[side], u[side])

    need_rest = {side: [need(rest, i, side) for i in range(len(frames))] for side in EYES}
    want = {side: [(y + off[i][0], p + off[i][1]) for i, (y, p) in enumerate(need_rest[side])] for side in EYES}
    yaw_gain = {s: (cal[(s, "Left")][0], cal[(s, "Right")][0]) for s in EYES}
    pitch_gain = {s: (cal[(s, "Up")][1], cal[(s, "Down")][1]) for s in EYES}

    def curves_for(angles):
        c = {(s, d): [] for s in EYES for d in LOOK}
        for s in EYES:
            for y, p in angles[s]:
                gl, gr = yaw_gain[s]
                c[(s, "Left")].append(max(0.0, min(1.0, y / gl)) if y * gl > 0 else 0.0)
                c[(s, "Right")].append(max(0.0, min(1.0, y / gr)) if y * gr > 0 else 0.0)
                gu, gd = pitch_gain[s]
                c[(s, "Up")].append(max(0.0, min(1.0, p / gu)) if p * gu > 0 else 0.0)
                c[(s, "Down")].append(max(0.0, min(1.0, p / gd)) if p * gd > 0 else 0.0)
        return c

    report = {"calibration": {f"{s}.{d}": [round(v, 2) for v in cal[(s, d)]] for s, d in cal},
              "head_to_lens_deg": {s: [round(min(abs(y) for y, _ in need_rest[s]), 2), round(max(abs(y) for y, _ in need_rest[s]), 2)]
                                   for s in EYES}, "passes": []}
    cmd = {s: list(want[s]) for s in EYES}  # what the curves ask for, corrected each pass by what the eyes did
    prev, seen = rest, None
    for it in range(iterations + 1):
        curves = curves_for(cmd)
        _write_eyes(a, times, _merged(times, curves, orig, every * rate / fps))
        EAL.save_asset(out)
        # wait on the frame whose eyes this write moves most, then measure the shot
        i_probe = max(range(len(frames)), key=lambda i: abs(curves[("L", "Left")][i] - curves[("L", "Right")][i]) +
                      abs(curves[("L", "Up")][i] - curves[("L", "Down")][i]) if seen is None else
                      sum(abs(curves[k][i] - seen[k][i]) for k in curves))
        yield from _await_change(measure, frames[i_probe], probe, prev["bones"][probe][i_probe])
        seen = curves
        got = yield from measure(frames)
        prev = got
        errs, lens = [], []
        for s in EYES:
            for i in range(len(frames)):
                y, p = need(got, i, s)  # what is still left between this eye and the lens
                ey, ep = y + off[i][0], p + off[i][1]  # ...and the saccade it should be holding
                errs.append(math.hypot(ey, ep))
                lens.append(math.hypot(y, p))
                cmd[s][i] = (cmd[s][i][0] + ey, cmd[s][i][1] + ep)
        errs.sort()
        report["passes"].append({"err_mean_deg": round(sum(errs) / len(errs), 2), "err_p95_deg": round(errs[int(len(errs) * 0.95)], 2),
                                 "err_max_deg": round(errs[-1], 2), "off_lens_mean_deg": round(sum(lens) / len(lens), 2)})
        if it == iterations:
            break
    return {"anim": out, "frames": len(frames), "range": [frames[0], frames[-1]], **report}


def _q(t):
    q = t.rotation
    return [q.x, q.y, q.z, q.w]


def _nlerp(a, b, u):
    s = 1.0 if sum(x * y for x, y in zip(a, b)) >= 0 else -1.0  # the short way round
    q = [x + (s * y - x) * u for x, y in zip(a, b)]
    n = math.sqrt(sum(x * x for x in q)) or 1.0
    return [x / n for x in q]


@op("anim.bake_pose", mutates=True, idempotent=True, tags=["slow"])
def bake_pose(sequence: str, actor_label: str, source: str, target: str, anim: str, out: str, bones: list, ticks: int = 2):
    """Sample `source` (a skeletal mesh component of the actor) as it really plays in `sequence` (animation, rig and
    post-process correctives included) and write those bones, local to their parents, as bone tracks into `out` (a
    copy of `anim`), which then goes on `target`'s track. Keys past the sequence keep the animation's own pose; curves
    are untouched. A multi-tick job.
    Example: film-ue op anim.bake_pose sequence=/Game/Shots/S010 actor_label=Presenter source=Body target=Face anim=/Game/Speech/Anim/AS_line1 out=/Game/Speech/Anim/AS_line1_baked 'bones=["neck_01","head"]'
    """
    from .seq import component_of, set_anim
    LSE = unreal.LevelSequenceEditorBlueprintLibrary
    src = component_of(actor_label, source)
    free(out)
    EAL.duplicate_asset(anim, out)
    a = load(out)
    seq = load(sequence)
    fps = seq.get_display_rate().numerator / seq.get_display_rate().denominator
    LSE.open_level_sequence(seq)
    frames = list(range(seq.get_playback_start(), seq.get_playback_end()))
    space = unreal.RelativeTransformSpace.RTS_PARENT_BONE_SPACE
    pos, rot, scl = ({b: [] for b in bones} for _ in range(3))
    LSE.set_current_time(frames[0] + 1)
    yield
    for f in frames:
        LSE.set_current_time(f)
        for _ in range(ticks):
            yield
        for b in bones:
            t = src.get_socket_transform(b, space)
            p, sc = t.translation, t.scale3d
            pos[b].append([p.x, p.y, p.z])
            rot[b].append(_q(t))
            scl[b].append([sc.x, sc.y, sc.z])
    n_keys = AL.get_num_keys(a)
    length = a.get_editor_property("sequence_length")
    span = (len(frames) - 1) / fps  # the seconds the samples cover
    tracks = {str(n) for n in AL.get_animation_track_names(a)}
    ctrl = a.get_editor_property("controller")
    ctrl.open_bracket("fmbridge bake_pose", True)
    for b in bones:
        P, R, S = [], [], []
        for k in range(n_keys):
            t = k * length / max(1, n_keys - 1)
            if t > span:  # past the shot: the animation's own pose
                own = AL.get_bone_pose_for_frame(a, b, k, False) if b in tracks else unreal.Transform()
                P.append(own.translation)
                R.append(own.rotation)
                S.append(own.scale3d)
                continue
            x = min(t * fps, len(frames) - 1.0001)
            i, u = int(x), x - int(x)
            P.append(unreal.Vector(*[p0 + (p1 - p0) * u for p0, p1 in zip(pos[b][i], pos[b][i + 1])]))
            q = _nlerp(rot[b][i], rot[b][i + 1], u)
            R.append(unreal.Quat(q[0], q[1], q[2], q[3]))
            S.append(unreal.Vector(*[s0 + (s1 - s0) * u for s0, s1 in zip(scl[b][i], scl[b][i + 1])]))
        if b not in tracks:
            ctrl.add_bone_curve(b)
        ctrl.set_bone_track_keys(b, P, R, S)
    ctrl.close_bracket(True)
    EAL.save_asset(out)
    set_anim(sequence, target, out, label=actor_label)
    return {"anim": out, "bones": len(bones), "keys": n_keys, "frames": len(frames)}


@op("anim.bake_follow", mutates=True, idempotent=True, tags=["slow"])
def bake_follow(sequence: str, actor_label: str, anim: str, out: str, leader: str = "Body", follower: str = "Face",
                bones: list | None = None, head_control: bool = False, ticks: int = 2):
    """Make a follower animation (a MetaHuman face's) carry its leader's pose: bake_pose from the leader (the body)
    into `out` for every non-facial bone the two skeletons share, and switch the face rig's own head control off
    (headcontrolswitch 0) unless `head_control`, so the head turns only as the body's does. A face playing alone
    otherwise keeps its neck and chest apart from the body, and its chest pokes through the clothes. Multi-tick.
    Example: film-ue op anim.bake_follow sequence=/Game/Shots/S010 actor_label=Presenter anim=/Game/Speech/Anim/AS_line1 out=/Game/Speech/Anim/AS_line1_follow
    """
    from .seq import component_of
    if bones is None:
        lead, foll = component_of(actor_label, leader), component_of(actor_label, follower)
        lb = {str(lead.get_bone_name(i)) for i in range(lead.get_num_bones())}
        bones = [n for n in (str(foll.get_bone_name(i)) for i in range(foll.get_num_bones()))
                 if n in lb and not n.startswith("FACIAL")]
    res = yield from bake_pose(sequence, actor_label, leader, follower, anim, out, bones, ticks)
    if not head_control:
        a = load(out)
        _set(a, "headcontrolswitch", [0.0, a.get_editor_property("sequence_length")], [0.0, 0.0])
        EAL.save_asset(out)
    return res


@op("anim.head_to_body", mutates=True, idempotent=True, tags=["slow"])
def head_to_body(sequence: str, actor_label: str, body_anim: str, out: str, face: str = "Face", body: str = "Body",
                 bones: list = ("spine_04", "spine_05", "neck_01", "neck_02", "head")):
    """Give the body the head motion a face rig makes from speech (HeadYaw/Pitch/Roll spread down the neck): bake the
    face's spine, neck and head as they play into `out` (a copy of the body's animation), which goes on the body's
    track. Then bake_follow puts the whole shared skeleton back on the face, so both move as one. Multi-tick.
    Example: film-ue op anim.head_to_body sequence=/Game/Shots/S010 actor_label=Presenter body_anim=/Game/Anim/AS_idle out=/Game/Anim/AS_idle_head
    """
    return (yield from bake_pose(sequence, actor_label, face, body, body_anim, out, list(bones)))


# --- the animation library: find, describe, make, read and write curves, check --------------------------------------

def _pkg(path: str) -> str:
    return str(path).split(".")[0]


def _err():
    from ..errors import OpError, not_found
    return OpError, not_found


def _anim(path: str):
    """An AnimSequence by package path, with an actionable error when it is not one."""
    OpError, not_found = _err()
    if not EAL.does_asset_exist(_pkg(path)):
        folder = _pkg(path).rsplit("/", 1)[0]
        near = [_pkg(p).rsplit("/", 1)[-1] for p in (EAL.list_assets(folder, False, False) if EAL.does_directory_exist(folder) else [])]
        raise not_found("animation", _pkg(path), near, hint="search with anim.find query='...'")
    a = EAL.load_asset(_pkg(path))
    if not isinstance(a, unreal.AnimSequence):
        raise OpError(f"{_pkg(path)} is a {a.get_class().get_name()}, not an AnimSequence", code="bad_args",
                      hint="anim.find lists animations")
    return a


def _tag(ad, name: str):
    try:
        v = ad.get_tag_value(name)
    except Exception:
        return None
    if isinstance(v, tuple):
        v = v[-1] if (len(v) > 1 and v[0]) else None
    return v if v not in ("", None) else None


def _object_path(tag: str) -> str:
    """A registry tag's object reference as a package path: "/Script/Engine.Skeleton'/Game/A/S.S'" -> "/Game/A/S"
    (the quoted export-text form, or a bare object path)."""
    tag = str(tag or "")
    if "'" in tag:
        tag = tag.split("'")[1]
    return _pkg(tag)


def _skeleton_path(obj) -> str:
    """The skeleton of an animation, skeletal mesh or skeleton, as a package path ("" when none)."""
    if obj is None:
        return ""
    if isinstance(obj, unreal.Skeleton):
        return _pkg(obj.get_path_name())
    sk = None
    for getter in ("get_skeleton",):
        try:
            sk = getattr(obj, getter)()
        except Exception:
            sk = None
    if sk is None:
        try:
            sk = obj.get_editor_property("skeleton")
        except Exception:
            sk = None
    return _pkg(sk.get_path_name()) if sk else ""


@op("anim.find", mutates=False, idempotent=True)
def find(*, query: str = "", path: str = "/", skeleton: str = "", kind: str = "", min_s: float = 0.0,
         max_s: float = 0.0, limit: int = 25) -> dict:
    """Search the project's animations (AnimSequence) by plain words, ranked: "happy face loop", "walk forward loop",
    "idle body". MetaHuman template names are understood (face/body, emotion, gait, start/loop/stop, direction).

    Args: query: words (empty = everything under `path`). path: folder to search ("/" = all mounted content,
    "/MetaHumanCharacter/Optional/Animation" = the MetaHuman templates). skeleton: only animations on this skeleton
    (a Skeleton, SkeletalMesh or AnimSequence path: "the face's skeleton" = the face mesh). kind: face|body.
    min_s/max_s: length bounds in seconds (0 = none). limit: how many.
    Returns: {"found": [{"path", "score", "kind", "category", "emotion", "gait", "phase", "direction", "tags",
    "length_s", "skeleton"}], "total": n}.
    Example: film-ue op anim.find query='walk forward loop' path=/MetaHumanCharacter
    """
    from ..perfkit import library as LIB
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    root = path.rstrip("/")
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "AnimSequence")],
                          package_paths=[root] if root else [], recursive_paths=True)  # "/" = every mount
    ads = list(reg.get_assets(flt) or [])
    want_sk = ""
    if skeleton:
        want_sk = _skeleton_path(EAL.load_asset(_pkg(skeleton))) or _pkg(skeleton)
    by = {}
    for ad in ads:
        p = str(ad.package_name)
        by[p] = ad
    ranked = LIB.search(list(by), query, kind=kind, limit=max(limit * 4, 100))
    out = []
    for r in ranked:
        ad = by[r["path"]]
        sk = _object_path(_tag(ad, "Skeleton") or "")
        if want_sk and sk and _pkg(sk) != want_sk:
            continue
        ln = _tag(ad, "SequenceLength")
        try:
            ln = float(ln) if ln is not None else None
        except ValueError:
            ln = None
        if ln is not None and ((min_s and ln < min_s) or (max_s and ln > max_s)):
            continue
        out.append({**r, "length_s": ln, "skeleton": _pkg(sk) if sk else None})
        if len(out) >= limit:
            break
    return {"found": out, "total": len(ads)}


@op("anim.describe", mutates=False, idempotent=True)
def describe(*, anim: str, curves: bool = False) -> dict:
    """What an animation is: length, frames, rate, skeleton, its float curves (count, and which face groups),
    bone tracks, additive settings, root motion, and the perf metadata (fingerprint) when perf made it.

    Args: anim: AnimSequence path. curves: also list every curve name.
    Returns: {"path", "length_s", "frames" (key intervals: keys - 1), "fps", "skeleton", "curve_count", "head_curves": [...],
    "face_curves": n, "bone_tracks": n, "additive": {"type", "base"}, "root_motion": bool, "perf": {...}, "curves"?}.
    Example: film-ue op anim.describe anim=/Game/Speech/Anim/AS_line1
    """
    from ..perfkit import rig as R
    a = _anim(anim)
    names = [str(n) for n in AL.get_animation_curve_names(a, FLOAT)]
    length = float(AL.get_sequence_length(a))
    frames = int(AL.get_num_frames(a))
    meta = {}
    for k in ("fm.perf.fingerprint", "fm.perf.spec", "fm.perf.solve_key", "fm.perf.made_by"):
        try:
            v = EAL.get_metadata_tag(a, k)
        except Exception:
            v = ""
        if v:
            meta[k.split(".")[-1]] = v
    out = {"path": _pkg(anim), "length_s": round(length, 4), "frames": frames,
           "fps": round(frames / length, 3) if length > 0 and frames > 0 else None,
           "skeleton": _skeleton_path(a), "curve_count": len(names),
           "head_curves": [n for n in names if n in R.HEAD], "face_curves": sum(1 for n in names if n in R.CURVES),
           "bone_tracks": len(list(AL.get_animation_track_names(a))),
           "additive": {"type": str(a.get_editor_property("additive_anim_type")),
                        "base": str(a.get_editor_property("ref_pose_type"))},
           "root_motion": bool(AL.is_root_motion_enabled(a)), "perf": meta}
    if curves:
        out["curves"] = sorted(names)
    return out


@op("anim.new", mutates=True, idempotent=True)
def new(*, path: str, skeleton: str, length_s: float, fps: int = 30, replace: bool = False) -> dict:
    """An empty animation (no keys: the skeleton's reference pose) on a skeleton, `length_s` long at `fps`: a canvas
    for perf.face, anim.write_curves or a procedural additive. Converges: an existing one of the same skeleton is
    resized in place (its curves kept) unless `replace`.

    Args: path: /Game/... package path. skeleton: a Skeleton, SkeletalMesh or AnimSequence whose skeleton to use.
    length_s: seconds. fps: frame rate of the keys.
    Returns: {"path", "changed", "created", "frames", "length_s"}.
    Example: film-ue op anim.new path=/Game/Perf/AS_blank skeleton=/Game/MetaHumans/Ada/Face/Ada_FaceMesh length_s=5
    """
    OpError, not_found = _err()
    if length_s <= 0:
        raise OpError("length_s must be > 0", code="bad_args")
    src = EAL.load_asset(_pkg(skeleton)) if EAL.does_asset_exist(_pkg(skeleton)) else None
    if src is None:
        raise not_found("skeleton source", _pkg(skeleton), hint="give a Skeleton, SkeletalMesh or AnimSequence path")
    sk = src if isinstance(src, unreal.Skeleton) else None
    if sk is None:
        skp = _skeleton_path(src)
        sk = EAL.load_asset(skp) if skp else None
    if sk is None:
        raise OpError(f"{_pkg(skeleton)} has no skeleton", code="bad_args")
    n = max(1, int(round(length_s * fps)))
    created = False
    if EAL.does_asset_exist(path) and not replace:
        a = EAL.load_asset(path)
        if not isinstance(a, unreal.AnimSequence) or _skeleton_path(a) != _pkg(sk.get_path_name()):
            raise OpError(f"{path} exists and is not an animation on {_pkg(sk.get_path_name())}", code="conflict",
                          hint="pass replace=true to start it afresh, or another path")
    else:
        free(path)
        folder, name = path.rsplit("/", 1)
        f = unreal.AnimSequenceFactory()
        f.set_editor_property("target_skeleton", sk)
        if isinstance(src, unreal.SkeletalMesh):
            f.set_editor_property("preview_skeletal_mesh", src)
        a = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.AnimSequence, f)
        if a is None:
            raise OpError(f"could not create {path}", code="engine")
        created = True
    before = int(AL.get_num_frames(a))
    ctrl = a.get_editor_property("controller")
    ctrl.open_bracket("fmbridge anim.new", False)
    try:
        ctrl.set_frame_rate(unreal.FrameRate(int(fps), 1), False)
        ctrl.set_number_of_frames(unreal.FrameNumber(n), False)
    finally:
        ctrl.close_bracket(False)
    EAL.save_asset(path)
    return {"path": path, "changed": created or before != int(AL.get_num_frames(a)), "created": created,
            "frames": int(AL.get_num_frames(a)), "length_s": float(AL.get_sequence_length(a))}


def read_all(a, names=None) -> dict:
    """{name: (times, values)} of an animation's float curves (all, or `names`)."""
    have = [str(n) for n in AL.get_animation_curve_names(a, FLOAT)]
    out = {}
    for n in (have if names is None else [x for x in names if x in have]):
        out[n] = _keys(a, n)
    return out


@op("anim.read_curves", mutates=False, idempotent=True)
def read_curves(*, anim: str, names: list | None = None, contains: str = "", every: int = 1) -> dict:
    """Float curves of an animation as {name: [times_s, values]}: all, the `names` given, or those whose name
    contains `contains`; every n-th key. For client-side analysis (perfkit.metrics, plots).
    Example: film-ue op anim.read_curves anim=/Game/Speech/Anim/AS_line1 contains=Head
    """
    a = _anim(anim)
    cur = read_all(a, names)
    return {n: [t[::every], v[::every]] for n, (t, v) in cur.items() if contains.lower() in n.lower()}


@op("anim.write_curves", mutates=True, idempotent=True)
def write_curves(*, anim: str, curves: dict, mode: str = "replace", save: bool = True) -> dict:
    """Write many float curves in one batch (one controller bracket, one recompression): {name: [times_s, values]}.
    mode: "replace" (these keys only), "add" (added to the curve's current values), "max", "mul".

    Returns: {"anim", "changed", "curves": n, "keys": total}.
    Example: film-ue op anim.write_curves anim=/Game/Perf/AS_face 'curves={"CTRL_expressions_browRaiseInL": [[0,1,2],[0,0.4,0]]}'
    """
    from ..perfkit import curves as C
    OpError, _ = _err()
    if mode not in ("replace", "add", "max", "mul"):
        raise OpError(f"mode {mode!r}", code="bad_args", hint="replace, add, max or mul")
    a = _anim(anim)
    todo = {}
    for name, tv in curves.items():
        t, v = list(map(float, tv[0])), list(map(float, tv[1]))
        if len(t) != len(v):
            raise OpError(f"curve {name}: {len(t)} times but {len(v)} values", code="bad_args")
        if mode != "replace" and AL.does_curve_exist(a, name, FLOAT):
            old = _keys(a, name)
            tt = sorted(set(t) | set(old[0]))
            v = C.combine([old, (t, v)], tt, mode)
            t = tt
        todo[name] = (t, v)
    before = {n: _keys(a, n) for n in todo if AL.does_curve_exist(a, n, FLOAT)}
    changed = any(before.get(n) != (list(t), list(v)) for n, (t, v) in todo.items())
    if changed:
        _write(a, todo)
        if save:
            EAL.save_asset(_pkg(anim))
    return {"anim": _pkg(anim), "changed": changed, "curves": len(todo), "keys": sum(len(t) for t, _ in todo.values())}


@op("anim.check", mutates=False, idempotent=True)
def check(*, anim: str, signs: dict | None = None) -> dict:
    """Will this face read as alive? Numeric naturalness checks on an animation's curves (perfkit.metrics): frozen
    head, linear (robotic) head moves, head jitter, blink rate/regularity/shape, left-right asymmetry, upper-face
    range, gaze activity. Each check {"name", "pass", "metric", "threshold", "why"}.

    Args: anim: a face animation (MetaHuman face curves). signs: perf.calibrate's result (rig signs/eye gains).
    Returns: {"pass", "failed": [names], "checks": [...], "blinks": {...}}.
    Example: film-ue op anim.check anim=/Game/Speech/Anim/AS_line1
    """
    from ..perfkit import metrics as M
    from ..perfkit.rig import HeadSigns
    return M.report(read_all(_anim(anim)), HeadSigns.from_json(signs))


# --- additive layering -----------------------------------------------------------------------------------------------

@op("anim.additive", mutates=True, idempotent=True)
def additive(*, anim: str, out: str, base: str = "first_frame", space: str = "local", frame: int = 0) -> dict:
    """An additive copy of an animation (it then layers on top of whatever plays under it in Sequencer: a gesture or
    a breath over an idle or a walk, without replacing the legs).

    Args: anim: the source. out: the additive copy's path (re-made on each call). base: what is subtracted:
    "first_frame" (the clip's own frame `frame`: the usual for a gesture authored from a rest pose), "ref_pose"
    (the skeleton's reference pose), or an AnimSequence path (its frame `frame`). space: "local" or "mesh"
    (rotation offset in mesh space: aiming layers).
    Returns: {"out", "changed": true, "type", "base"}.
    Example: film-ue op anim.additive anim=/Game/Anim/AS_Shrug out=/Game/Anim/AS_Shrug_Add
    """
    OpError, _ = _err()
    _anim(anim)
    if space not in ("local", "mesh"):
        raise OpError(f"space {space!r}", code="bad_args", hint="local or mesh")
    free(out)
    if not EAL.duplicate_asset(_pkg(anim), out):
        raise OpError(f"could not duplicate {anim} to {out}", code="engine")
    a = load(out)
    AL.set_additive_animation_type(a, unreal.AdditiveAnimationType.AAT_LOCAL_SPACE_BASE if space == "local"
                                   else unreal.AdditiveAnimationType.AAT_ROTATION_OFFSET_MESH_SPACE)
    if base == "first_frame":
        AL.set_additive_base_pose_type(a, unreal.AdditiveBasePoseType.ABPT_LOCAL_ANIM_FRAME)
        a.set_editor_property("ref_frame_index", int(frame))
    elif base == "ref_pose":
        AL.set_additive_base_pose_type(a, unreal.AdditiveBasePoseType.ABPT_REF_POSE)
    else:
        b = _anim(base)
        AL.set_additive_base_pose_type(a, unreal.AdditiveBasePoseType.ABPT_ANIM_FRAME)
        a.set_editor_property("ref_pose_seq", b)
        a.set_editor_property("ref_frame_index", int(frame))
    EAL.save_asset(out)
    return {"out": out, "changed": True, "type": str(a.get_editor_property("additive_anim_type")),
            "base": str(a.get_editor_property("ref_pose_type"))}


# --- retargeting: IK Rigs and an IK Retargeter made by code, then a batch retarget -----------------------------------

def _ik_rig(path: str, mesh) -> tuple:
    """An IK Rig for `mesh` at `path`: made with the auto-generated retarget chains (and full-body IK) when missing.
    Returns (rig, created)."""
    OpError, _ = _err()
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path), False
    folder, name = path.rsplit("/", 1)
    rig = unreal.IKRigDefinitionFactory.create_new_ik_rig_asset(folder, name)
    if rig is None:
        raise OpError(f"could not create the IK Rig {path}", code="engine")
    c = unreal.IKRigController.get_controller(rig)
    c.set_skeletal_mesh(mesh)
    if not c.apply_auto_generated_retarget_definition():
        raise OpError(f"the engine could not auto-generate retarget chains for {_pkg(mesh.get_path_name())}",
                      code="engine", hint="give your own source_rig/target_rig (IK Rig assets) instead")
    c.apply_auto_fbik()
    EAL.save_asset(path)
    return rig, True


@op("anim.retarget", mutates=True, idempotent=True, tags=["slow"])
def retarget(*, anims: list, source_mesh: str, target_mesh: str, out_folder: str, source_rig: str = "",
             target_rig: str = "", retargeter: str = "", suffix: str = "_RTG", align: bool = True,
             include_referenced: bool = False) -> dict:
    """Retarget animations from one skeleton to another (a Mixamo or UE5 mannequin clip onto a MetaHuman body) by
    code: IK Rigs for both meshes (auto-generated chains + full-body IK, made once under out_folder/Rigs unless
    given), an IK Retargeter (default op stack, chains auto-mapped by name, the target's retarget pose auto-aligned
    to the source), then the engine's batch retarget into `out_folder`, overwriting earlier results of the same name.

    Args: anims: AnimSequence paths on the source skeleton. source_mesh/target_mesh: SkeletalMesh paths.
    out_folder: /Game/... folder for the results and the rigs. source_rig/target_rig/retargeter: existing assets to
    use instead of making them. suffix: added to each result's name. align: auto-align the target's retarget pose
    (fixes T-pose vs A-pose). include_referenced: also retarget assets the inputs reference.
    Returns: {"changed", "results": [paths], "retargeter", "rigs": {"source", "target"}, "made": [paths]}.
    Example: film-ue op anim.retarget 'anims=["/Game/Mixamo/Wave"]' source_mesh=/Game/Mixamo/Y_Bot target_mesh=/Game/MetaHumans/Ada/Body/m_med_nrw_body out_folder=/Game/Anim/Retargeted
    """
    OpError, not_found = _err()
    smesh, tmesh = load(_pkg(source_mesh)), load(_pkg(target_mesh))
    for p, m in ((source_mesh, smesh), (target_mesh, tmesh)):
        if not isinstance(m, unreal.SkeletalMesh):
            raise OpError(f"{p} is not a SkeletalMesh", code="bad_args")
    srcs = [_anim(a) for a in anims]
    made = []
    sname, tname = _pkg(source_mesh).rsplit("/", 1)[-1], _pkg(target_mesh).rsplit("/", 1)[-1]
    srig, c1 = (load(source_rig), False) if source_rig else _ik_rig(f"{out_folder}/Rigs/IK_{sname}", smesh)
    trig, c2 = (load(target_rig), False) if target_rig else _ik_rig(f"{out_folder}/Rigs/IK_{tname}", tmesh)
    made += [p for p, c in ((f"{out_folder}/Rigs/IK_{sname}", c1), (f"{out_folder}/Rigs/IK_{tname}", c2)) if c]
    rpath = retargeter or f"{out_folder}/Rigs/RTG_{sname}_to_{tname}"
    if EAL.does_asset_exist(rpath):
        rtg = load(rpath)
    else:
        folder, name = rpath.rsplit("/", 1)
        rtg = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.IKRetargeter,
                                                                     unreal.IKRetargetFactory())
        if rtg is None:
            raise OpError(f"could not create the IK Retargeter {rpath}", code="engine")
        made.append(rpath)
        rc = unreal.IKRetargeterController.get_controller(rtg)
        S, T = unreal.RetargetSourceOrTarget.SOURCE, unreal.RetargetSourceOrTarget.TARGET
        rc.set_ik_rig(S, srig)
        rc.set_ik_rig(T, trig)
        rc.set_preview_mesh(S, smesh)
        rc.set_preview_mesh(T, tmesh)
        if rc.get_num_retarget_ops() == 0:
            rc.add_default_ops()
        rc.assign_ik_rig_to_all_ops(S, srig)
        rc.assign_ik_rig_to_all_ops(T, trig)
        rc.auto_map_chains(unreal.AutoMapChainType.FUZZY, True)
        if align:
            rc.auto_align_all_bones(T)
        EAL.save_asset(rpath)
    inputs = unreal.IKRetargetBatchOperationInputs()
    ads = [EAL.find_asset_data(_pkg(a.get_path_name())) for a in srcs]
    for k, v in (("assets_to_retarget", ads), ("source_mesh", smesh), ("target_mesh", tmesh),
                 ("ik_retarget_asset", rtg), ("suffix", suffix), ("target_path", out_folder),
                 ("use_source_path", False), ("include_referenced_assets", include_referenced),
                 ("overwrite_existing_files", True), ("retain_additive_flags", True)):
        inputs.set_editor_property(k, v)
    res = unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
    paths = [str(ad.package_name) for ad in (res or [])]
    if not paths:
        raise OpError("the batch retarget produced nothing", code="engine",
                      hint="check the source animations are on source_mesh's skeleton (anim.describe) and the editor log")
    for p in paths:
        EAL.save_asset(p)
    return {"changed": True, "results": paths, "retargeter": rpath,
            "rigs": {"source": _pkg(srig.get_path_name()), "target": _pkg(trig.get_path_name())}, "made": made}


# --- Control Rig keys in Sequencer ------------------------------------------------------------------------------------

def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _rig_on(seq, label: str, component: str = ""):
    """The (proxy, control rig, track) on `label`'s binding (or its component's) in `seq`, or None."""
    names = {label, component} - {""}
    for p in unreal.ControlRigSequencerLibrary.get_control_rigs(seq) or []:
        try:
            b = p.get_editor_property("proxy")
            nm = str(b.get_display_name())
        except Exception:
            nm = ""
        if nm in names:
            return p
    return None


@op("anim.rig_controls", mutates=False, idempotent=True)
def rig_controls(*, sequence: str, label: str, component: str = "") -> dict:
    """The controls of the Control Rig on an actor (or its component) in a sequence, for anim.rig_keys.
    Returns: {"rig": class name, "controls": [names]}.
    Example: film-ue op anim.rig_controls sequence=/Game/Shots/S010 label=Presenter component=Face
    """
    _, not_found = _err()
    seq = load(sequence)
    p = _rig_on(seq, label, component)
    if p is None:
        raise not_found("control rig track", f"{label}.{component}" if component else label,
                        hint="anim.rig_keys with rig_class=... makes one")
    rig = p.get_editor_property("control_rig")
    keys = rig.get_hierarchy().get_controls()  # ScriptName of GetControlKeys (RigHierarchy.h:1181)
    return {"rig": rig.get_class().get_name(), "controls": [str(k.get_editor_property("name")) for k in keys]}


@op("anim.rig_keys", mutates=True, idempotent=True)
def rig_keys(*, sequence: str, label: str, keys: dict, component: str = "", rig_class: str = "",
             layered: bool = False) -> dict:
    """Key Control Rig controls in a sequence, batched per control (one engine call each, not one per key).
    keys: {control: [[frame, value], ...]} where value is a number (a float control), {"pitch", "yaw", "roll"} (a
    rotator control) or {"loc": [x, y, z], "rot": {...}} (a transform control, local space). The rig track is found
    on the actor (or `component`'s) binding, or made from `rig_class` (a Blueprint-based Control Rig asset path, or
    a class path; 5.8's independent Control Rig assets cannot be made into a track from Python; `layered` for an
    additive layer over the animation).
    Returns: {"changed", "controls": n, "keys": n, "rig"}.
    Example: film-ue op anim.rig_keys sequence=/Game/Shots/S010 label=Presenter component=Face 'keys={"CTRL_L_brow_raiseIn": [[0,0],[12,0.6],[30,0]]}'
    """
    from .seq import _comp_binding
    OpError, not_found = _err()
    seq = load(sequence)
    CR = unreal.ControlRigSequencerLibrary
    p = _rig_on(seq, label, component)
    if p is None:
        if not rig_class:
            raise not_found("control rig track", label, hint="pass rig_class (a Control Rig Blueprint) to make one")
        b = _comp_binding(seq, label, component)
        cls = unreal.load_class(None, rig_class) if "." in rig_class else None
        if cls is None:
            cls = EAL.load_blueprint_class(_pkg(rig_class))
        if cls is None:
            raise not_found("control rig class", rig_class,
                            hint="a Blueprint-based Control Rig asset path (a legacy ControlRigBlueprint, like the "
                                 "MetaHuman control boards); 5.8's independent Control Rig assets have no Python route "
                                 "to their class: add the rig track in the editor once, then key it here")
        CR.find_or_create_control_rig_track(_world(), seq, cls, b, layered)
        p = _rig_on(seq, label, component)
        if p is None:
            raise OpError("the engine made no control rig track", code="engine")
    rig = p.get_editor_property("control_rig")
    have = {str(k.get_editor_property("name")) for k in rig.get_hierarchy().get_controls()}
    missing = [c for c in keys if c not in have]
    if missing:
        from ..errors import closest
        raise OpError(f"no controls {missing[:5]} on {rig.get_class().get_name()}", code="not_found",
                      candidates=closest(missing[0], have), hint="anim.rig_controls lists them")
    n = 0
    for control, ks in keys.items():
        frames = [unreal.FrameNumber(int(k[0])) for k in ks]
        vals = [k[1] for k in ks]
        if all(isinstance(v, (int, float)) for v in vals):
            CR.set_local_control_rig_floats(seq, rig, control, frames, [float(v) for v in vals])
        elif all(isinstance(v, dict) and set(v) <= {"pitch", "yaw", "roll"} for v in vals):
            CR.set_local_control_rig_rotators(seq, rig, control, frames,
                                              [unreal.Rotator(roll=v.get("roll", 0.0), pitch=v.get("pitch", 0.0),
                                                              yaw=v.get("yaw", 0.0)) for v in vals])
        elif all(isinstance(v, dict) for v in vals):
            ets = []
            for v in vals:
                r = v.get("rot", {})
                ets.append(unreal.EulerTransform(location=unreal.Vector(*[float(x) for x in v.get("loc", (0, 0, 0))]),
                                                 rotation=unreal.Rotator(roll=r.get("roll", 0.0), pitch=r.get("pitch", 0.0),
                                                                         yaw=r.get("yaw", 0.0)),
                                                 scale=unreal.Vector(1.0, 1.0, 1.0)))
            CR.set_local_control_rig_euler_transforms(seq, rig, control, frames, ets)
        else:
            raise OpError(f"control {control}: values must all be numbers, rotators or transforms", code="bad_args")
        n += len(ks)
    EAL.save_asset(sequence)
    return {"changed": True, "controls": len(keys), "keys": n, "rig": rig.get_class().get_name()}
