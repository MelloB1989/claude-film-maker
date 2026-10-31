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
from .assets import EAL, load

AL = unreal.AnimationLibrary
FLOAT = unreal.RawCurveTrackTypes.RCT_FLOAT


def _keys(anim, name):
    t, v = AL.get_float_keys(anim, name)
    return list(t), list(v)


def _set(anim, name, times, values):
    if AL.does_curve_exist(anim, name, FLOAT):
        AL.remove_curve(anim, name, False)
    AL.add_curve(anim, name, FLOAT, False)
    AL.add_float_curve_keys(anim, name, times, values)


@op("anim.curves")
def curves(anim: str, contains: str = "") -> list:
    """A sequence's float curve names."""
    return [str(n) for n in AL.get_animation_curve_names(load(anim), FLOAT) if contains.lower() in str(n).lower()]


@op("anim.curve")
def curve(anim: str, name: str, every: int = 1) -> dict:
    """One curve's keys (every n-th): times and values, with its range."""
    t, v = _keys(load(anim), name)
    return {"times": t[::every], "values": v[::every], "min": min(v) if v else None, "max": max(v) if v else None}


@op("anim.set_curve")
def set_curve(anim: str, name: str, times: list, values: list) -> int:
    """Replace a curve with these keys."""
    a = load(anim)
    _set(a, name, times, values)
    EAL.save_asset(anim)
    return len(times)


@op("anim.scale_curves")
def scale_curves(anim: str, scale: dict, offset: dict | None = None) -> dict:
    """Multiply (then offset) curves by name: {"HeadYaw": 0.6, "CTRL_expressions_browRaiseInL": 1.3}."""
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
    for (side, d), v in curves.items():
        _set(a, f"CTRL_expressions_eyeLook{d}{side}", times, v)


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


@op("anim.gaze_lock")
def gaze_lock(sequence: str, actor_label: str, anim: str, out: str, camera: str, component: str = "Face",
              saccades: float = 0.5, seed: int = 3, every: int = 2, iterations: int = 2):
    """Keep a talking face's eyes on the lens, measured rather than guessed: `out` (a copy of `anim`) goes on
    `component`'s track in `sequence`; the eye-look curves are calibrated on the rig, then solved per frame from the
    eye bones' real pose (head and body motion included) toward `camera`, with small saccades, and refined
    `iterations` times against a fresh measurement. Returns the angle error per pass. A multi-tick job."""
    from .seq import sample, set_anim
    if EAL.does_asset_exist(out):
        EAL.delete_asset(out)
    EAL.duplicate_asset(anim, out)
    a = load(out)
    length = a.get_editor_property("sequence_length")
    zero2 = {(s, d): [0.0, 0.0] for s in EYES for d in LOOK}
    _write_eyes(a, [0.0, length], zero2)
    EAL.save_asset(out)
    set_anim(sequence, component, out)
    yield 1.0
    bones = list(EYES.values())
    probe = EYES["L"]

    def measure(frames):
        return (yield from sample(sequence, actor_label, component, bones, frames=frames, ticks=3, camera=camera))

    # calibrate on the first frame: each look direction at full against none
    base = yield from measure([0])
    g, u = {}, {}
    for side, bone in EYES.items():
        x = base["bones"][bone][0]
        to_cam = _norm([base["camera"][0][k] - x[k] for k in range(3)])
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
        m = yield from _await_change(measure, 0, probe, last["bones"][probe][0])
        last = m
        for side, bone in EYES.items():
            gw = _axes(m["bones"][bone][0])[abs(g[side]) - 1]
            gw = [v * (1 if g[side] > 0 else -1) for v in gw]
            cal[(side, d)] = _angles(_local(gw, base["bones"][bone][0]), g[side], u[side])

    # the eyes' rest pose through the whole shot, then the solve
    _write_eyes(a, [0.0, length], zero2)
    yield from _await_change(measure, 0, probe, last["bones"][probe][0])
    seq = load(sequence)
    fps = seq.get_display_rate().numerator / seq.get_display_rate().denominator
    frames = [f for f in range(0, seq.get_playback_end(), every) if f / fps <= length]
    rest = yield from measure(frames)
    times = [f / fps for f in frames]
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
        to_cam = _norm([sample_["camera"][i][k] - x[k] for k in range(3)])
        return _angles(_local(to_cam, x), g[side], u[side])

    target = {side: [need(rest, i, side) for i in range(len(frames))] for side in EYES}
    want = {side: [(y + off[i][0], p + off[i][1]) for i, (y, p) in enumerate(target[side])] for side in EYES}
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
              "head_to_lens_deg": {s: [round(min(abs(y) for y, _ in target[s]), 2), round(max(abs(y) for y, _ in target[s]), 2)]
                                   for s in EYES}, "passes": []}
    cmd = {s: list(want[s]) for s in EYES}  # what the curves ask for, corrected each pass by what the eyes did
    prev, seen = rest, None
    for it in range(iterations + 1):
        curves = curves_for(cmd)
        _write_eyes(a, times, curves)
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
    return {"anim": out, "frames": len(frames), **report}


def _q(t):
    q = t.rotation
    return [q.x, q.y, q.z, q.w]


def _nlerp(a, b, u):
    s = 1.0 if sum(x * y for x, y in zip(a, b)) >= 0 else -1.0  # the short way round
    q = [x + (s * y - x) * u for x, y in zip(a, b)]
    n = math.sqrt(sum(x * x for x in q)) or 1.0
    return [x / n for x in q]


@op("anim.bake_pose")
def bake_pose(sequence: str, actor_label: str, source: str, target: str, anim: str, out: str, bones: list, ticks: int = 2):
    """Sample `source` (a skeletal mesh component of the actor) as it really plays in `sequence` (animation, rig and
    post-process correctives included) and write those bones, local to their parents, as bone tracks into `out` (a
    copy of `anim`), which then goes on `target`'s track. Keys past the sequence keep the animation's own pose; curves
    are untouched. A multi-tick job."""
    from .seq import component_of, set_anim
    LSE = unreal.LevelSequenceEditorBlueprintLibrary
    src = component_of(actor_label, source)
    if EAL.does_asset_exist(out):
        EAL.delete_asset(out)
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
    set_anim(sequence, target, out)
    return {"anim": out, "bones": len(bones), "keys": n_keys, "frames": len(frames)}


@op("anim.bake_follow")
def bake_follow(sequence: str, actor_label: str, anim: str, out: str, leader: str = "Body", follower: str = "Face",
                bones: list | None = None, head_control: bool = False, ticks: int = 2):
    """Make a follower animation (a MetaHuman face's) carry its leader's pose: bake_pose from the leader (the body)
    into `out` for every non-facial bone the two skeletons share, and switch the face rig's own head control off
    (headcontrolswitch 0) unless `head_control`, so the head turns only as the body's does. A face playing alone
    otherwise keeps its neck and chest apart from the body, and its chest pokes through the clothes. Multi-tick."""
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


@op("anim.head_to_body")
def head_to_body(sequence: str, actor_label: str, body_anim: str, out: str, face: str = "Face", body: str = "Body",
                 bones: list = ("spine_04", "spine_05", "neck_01", "neck_02", "head")):
    """Give the body the head motion a face rig makes from speech (HeadYaw/Pitch/Roll spread down the neck): bake the
    face's spine, neck and head as they play into `out` (a copy of the body's animation), which goes on the body's
    track. Then bake_follow puts the whole shared skeleton back on the face, so both move as one. Multi-tick."""
    return (yield from bake_pose(sequence, actor_label, face, body, body_anim, out, list(bones)))
