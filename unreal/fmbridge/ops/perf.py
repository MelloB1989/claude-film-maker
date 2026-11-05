"""Performance: make a MetaHuman act by code. A face that is alive (organic head turns that the eyes lead, nods that
overshoot and settle, irregular blinks that go with gaze shifts, asymmetric expressions with living envelopes,
moods that blend line to line, micro-motion in every hold) over the speech solver's lip-sync, and a body that idles
without visibly looping, gestures on the stressed word, walks and turns. All the synthesis is fmbridge.perfkit (pure
Python, unit-tested); these ops read the editor, run it, and write the curves and Sequencer tracks.

Start here:
    perf.face      naturalize one face animation (a speech solve): head, eyes, blinks, brows, moods
    perf.apply     a whole PERFORMANCE spec (kind: performance) -> a keyed sequence; perf.plan shows the steps
    perf.check     -> anim.check: will it read as alive (numbers)
    perf.calibrate measure the rig's head/eye signs once per face skeleton (makes perf.face exact)
"""
from __future__ import annotations

import json
import os

import unreal

from . import call, op
from .assets import EAL, free, load
from ..errors import OpError, not_found
from ..perfkit import audio as AU
from ..perfkit import blinks as BL
from ..perfkit import body as BD
from ..perfkit import expressions as X
from ..perfkit import face as FACE
from ..perfkit import head as HD
from ..perfkit import spec as SP
from ..perfkit.rig import HEAD, LIVE_CM, HeadSigns, head_axes

LSE = unreal.LevelSequenceEditorBlueprintLibrary


def _saved(*parts) -> str:
    d = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "fmbridge", "perf")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, *parts)


def _signs_file(skeleton: str) -> str:
    return _saved(f"signs_{skeleton.rsplit('/', 1)[-1]}.json")


def signs_for(skeleton: str, given: dict | None = None) -> HeadSigns:
    """The rig signs to use: `given`, else perf.calibrate's saved measurement for this skeleton, else defaults."""
    if given:
        return HeadSigns.from_json(given)
    p = _signs_file(skeleton) if skeleton else ""
    if p and os.path.exists(p):
        with open(p) as f:
            return HeadSigns.from_json(json.load(f))
    return HeadSigns()


def _meta(obj, key: str, value=None):
    if value is None:
        try:
            return EAL.get_metadata_tag(obj, key) or ""
        except Exception:
            return ""
    EAL.set_metadata_tag(obj, key, str(value))
    return value


# --- vocabulary and analysis -------------------------------------------------------------------------------------

@op("perf.vocab", mutates=False, idempotent=True)
def vocab() -> dict:
    """The words a performance understands: expression presets (with their curves), moods (and the speech solver
    mood each maps to), nod kinds, face layers, blink states, gaze scan modes.
    Example: film-ue op perf.vocab
    """
    return {"expressions": {k: sorted(X.expand(k)) for k in sorted(X.PRESETS)},
            "moods": {k: {"layers": v, "solver_mood": X.SOLVER_MOOD.get(k)} for k, v in sorted(X.MOODS.items())},
            "nods": list(HD.Nod.KINDS), "layers": list(FACE.LAYERS), "blink_states": BL.RATE_PER_MIN,
            "scan": ["face", "lens", "still", None], "lead": ["eyes", "head"],
            "solver_head": ["soften", "keep", "replace"], "blink_mode": ["replace", "keep", "max"]}


@op("perf.analyze_audio", mutates=False, idempotent=True)
def analyze_audio(*, wav: str, top: int = 0) -> dict:
    """A voice file's timing for a performance, with no engine work: duration, stressed syllables (emphasis: beat
    nods and brow flashes land there), pauses and phrase ends (blinks), and a 25 Hz loudness envelope.

    Args: wav: a PCM WAV path on the editor's machine. top: keep only the strongest n emphases (0 = all).
    Returns: {"duration_s", "emphasis": [[t, strength]], "pauses": [[t0, t1]], "phrase_ends": [t], "talking":
    [[t0, t1]], "envelope": {"rate": 25, "values": [...]}}.
    Example: film-ue op perf.analyze_audio wav=/home/ue/Audio/line1.wav
    """
    if not os.path.exists(wav):
        raise not_found("WAV file", wav, hint="push it to the box first (client.push)")
    env = AU.Envelope.from_wav(wav)
    small = AU.Envelope(env.values, env.rate)
    step = max(1, int(env.rate / 25))
    return {"duration_s": round(env.duration_s, 3), "emphasis": [list(e) for e in env.emphasis(top=top or None)],
            "pauses": [list(p) for p in env.pauses()], "phrase_ends": env.phrase_ends(),
            "talking": [list(p) for p in small.talking()],
            "envelope": {"rate": env.rate / step, "values": [round(v, 3) for v in env.values[::step]]}}


# --- one face animation ------------------------------------------------------------------------------------------

@op("perf.face", mutates=True, idempotent=True)
def face(*, anim: str, out: str = "", wav: str = "", gaze: list | None = None, start_gaze: list | None = None,
         lead: str = "eyes", head: dict | None = None, nods: list | None = None, tilts: list | None = None,
         mood: str = "", moods: list | None = None, expressions: list | None = None, emphasis=None,
         layers: list | None = None, solver_head: str = "soften", blink_mode: str = "replace", blink_state: str = "talk",
         energy: float = 1.0, mouth_mix: float = 0.5, brow_chance: float = 0.55, signs: dict | None = None,
         seed: int = 0, plot: str = "") -> dict:
    """Make a face animation (a speech solve, or any MetaHuman face animation) read as alive: write a copy whose head
    turns follow the gaze (eyes lead, the head eases with overshoot and settles), with nods and brow flashes on the
    stressed words, irregular asymmetric blinks (with big gaze shifts and at phrase ends), fixational eye darts, a
    mood's baseline expression, and micro-motion in every hold; the solver's own head motion is softened under it
    and the lip-sync is kept.

    Args (times in seconds from the animation's start, angles in degrees in the CHARACTER's frame: yaw + = their
    left, pitch + = up):
      anim: the source animation. out: where to write (default <anim>_perf); re-written on each call.
      wav: the line's audio, for automatic emphasis and phrase ends (perf.analyze_audio).
      gaze: shifts [{"t", "yaw", "pitch", "scan": face|lens|still, "dist_cm", "head": share 0..1}]; default: hold
      straight ahead on a lens. start_gaze: [yaw, pitch] at t=0. lead: eyes|head.
      head: style {"gain", "rest_roll_deg", "rest_pitch_deg", "micro_deg", "breath_deg", "lean", "speech_gain"}.
      nods: [{"t", "kind": yes|beat|up|no, "depth_deg", "count"}]. tilts: [{"t", "until", "roll_deg"}].
      mood: one mood over the whole clip, or moods: [{"t0", "t1", "mood", "intensity"}] (perf.vocab lists them).
      expressions: [{"preset", "t", "until", "intensity", "asym"}]. emphasis: [[t, strength]] or "auto" (from wav).
      layers: subset of head, eyes, blinks, expressions, brows, nods. solver_head: soften|keep|replace.
      blink_mode: replace|keep|max. blink_state: talk|listen|rest|focus|nervous|calm. energy: >1 brisker head.
      mouth_mix: smile strength on a talking mouth (0..1). signs: rig signs (default perf.calibrate's, else guesses).
      plot: a PNG path on the box: the result's curves drawn as strips (perf.plot) to look at.
    Returns: {"out", "changed", "plan": {shifts, nods, blinks, expressions, ...}, "report": naturalness checks,
    "curves": n, "plot"?: {"path", "width", "height"}}.
    Example: film-ue op perf.face anim=/Game/Speech/Anim/AS_line1 wav=/home/ue/Audio/line1.wav mood=warm 'gaze=[{"t":0,"yaw":0,"scan":"lens"},{"t":2.5,"yaw":25,"pitch":-5}]'
    """
    from .anim import _anim, _skeleton_path, _write, read_all
    a = _anim(anim)
    out = out or f"{anim.split('.')[0]}_perf"
    length = float(unreal.AnimationLibrary.get_sequence_length(a))
    base = read_all(a)
    emph, ends, speech = [], [], None
    if wav:
        env = AU.Envelope.from_wav(wav)
        speech = env.at
        ends = env.phrase_ends()
        if emphasis in (None, "auto"):
            emph = env.emphasis()
    if isinstance(emphasis, list):
        emph = [tuple(e) if isinstance(e, (list, tuple)) else (float(e), 1.0) for e in emphasis]
    mood_spans = moods or ([{"t0": 0.0, "t1": length, "mood": mood}] if mood else [])
    try:
        r = FACE.build(0.0, length, base=base, shifts=gaze if gaze is not None else [{"t": 0.0, "yaw": 0.0, "scan": "lens"}],
                       start_gaze=tuple(start_gaze or (0.0, 0.0)), lead=lead, head_style=head, nods=nods or [],
                       tilts=tilts or [], moods=mood_spans, expressions=expressions or [], emphasis=emph,
                       phrase_ends=ends, speech=speech, layers=layers or FACE.LAYERS, solver_head=solver_head,
                       blink_mode=blink_mode, blink_state=blink_state,
                       signs=signs_for(_skeleton_path(a), signs), energy=energy, mouth_mix=mouth_mix,
                       brow_chance=brow_chance, seed=seed)
    except ValueError as e:
        raise OpError(str(e), code="bad_args", hint="perf.vocab lists presets, moods, nods and layers") from None
    if out != anim.split(".")[0]:
        free(out)
        if not EAL.duplicate_asset(anim.split(".")[0], out):
            raise OpError(f"could not copy {anim} to {out}", code="engine")
    o = load(out)
    _write(o, r["curves"])
    _meta(o, "fm.perf.made_by", "perf.face")
    EAL.save_asset(out)
    res = {"out": out, "changed": True, "plan": r["plan"], "report": r["report"], "curves": len(r["curves"])}
    if plot:
        res["plot"] = _plot({**base, **r["curves"]}, plot, r["plan"], signs_for(_skeleton_path(a), signs), out)
    return res


def _plot(curves: dict, path: str, plan_: dict | None, signs: HeadSigns, title: str, t0=None, t1=None) -> dict:
    from ..camkit import png
    from ..perfkit import plot as PL
    marks = {"shifts": [s["t"] for s in (plan_ or {}).get("shifts", [])],
             "emphasis": [n["t"] for n in (plan_ or {}).get("nods", []) if n.get("kind") == "beat"]}
    img = PL.performance(curves, t0, t1, marks=marks, signs=signs, title=title.rsplit("/", 1)[-1])
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    png.write(path, img)
    return {"path": path, "width": img.w, "height": img.h}


@op("perf.plot", mutates=True, idempotent=True, tags=["feedback"])
def plot(*, anim: str, out: str, signs: dict | None = None, t0_s: float | None = None, t1_s: float | None = None) -> dict:
    """Draw a face animation's performance as a PNG (head yaw/pitch/roll, the left eye in the head, blinks, upper
    face, mouth, on one time axis): look at it to judge motion without rendering. Straight ramps and flat holds in the
    head strip are robotic; eased S-curves with a small overshoot and a slight wobble are alive.

    Args: anim: a face AnimSequence. out: PNG path on the box. signs: rig signs (default the calibration).
    t0_s/t1_s: the time window (default the whole animation).
    Returns: {"path", "width", "height", "changed": true}.
    Example: film-ue op perf.plot anim=/Game/Speech/Anim/AS_l1_perf out=/tmp/l1_perf.png
    """
    from .anim import _anim, _skeleton_path, read_all
    a = _anim(anim)
    cur = read_all(a)
    r = _plot(cur, out, None, signs_for(_skeleton_path(a), signs), anim, t0_s, t1_s)
    return {**r, "changed": True}


@op("perf.check", mutates=False, idempotent=True)
def check(*, anim: str, signs: dict | None = None) -> dict:
    """Will this face read as alive? Same as anim.check (naturalness numbers with pass/fail and why).
    Example: film-ue op perf.check anim=/Game/Speech/Anim/AS_line1_perf
    """
    return call("anim.check", anim=anim, signs=signs)


# --- calibration: which way the rig's head curves and eye curves really turn -------------------------------------

def _mid(a, b):
    return [(x + y) / 2 for x, y in zip(a, b)]


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _unit(v):
    import math
    n = math.sqrt(_dot(v, v)) or 1.0
    return [x / n for x in v]


@op("perf.calibrate", mutates=True, idempotent=True, tags=["slow"])
def calibrate(*, label: str, face_component: str = "Face", scratch: str = "/Game/_Perf/Calibrate",
              degrees: float = 10.0):
    """Measure, on the real rig, which of HeadYaw/HeadPitch/HeadRoll turns, nods and tilts the head (the names need not
    say: on the reel's MetaHumans HeadYaw nods), which way, and how far eyeLook* turns the
    eyes, and save it for this face skeleton (Saved/fmbridge/perf/signs_<skeleton>.json): perf.face and perf.apply
    then use it. Plays a scratch animation on the actor's face in a scratch sequence and samples the eye bones.
    Run once per face skeleton (the face must be driven by Sequencer: mh.drive_face). A multi-tick job, ~20 s.

    Returns: {"signs": {"yaw", "pitch", "roll", "eye_deg", "eye_flip", "measured", "curves": {axis: curve}}, "file",
    "raw": {...}}.
    Example: film-ue op perf.calibrate label=Presenter
    """
    import math
    from .anim import _skeleton_path, _write, new as anim_new
    from .anim import _await_change
    from .seq import component_of, sample
    comp = component_of(label, face_component)
    mesh = comp.get_skeletal_mesh_asset()
    if mesh is None:
        raise OpError(f"{label}.{face_component} has no skeletal mesh", code="bad_args")
    mesh_path = mesh.get_path_name().split(".")[0]
    skel = _skeleton_path(mesh)
    anim_path, seq_path = f"{scratch}/AS_calibrate", f"{scratch}/LS_calibrate"
    anim_new(path=anim_path, skeleton=mesh_path, length_s=2.0, fps=30, replace=True)
    a = load(anim_path)
    zero = ([0.0, 2.0], [0.0, 0.0])
    heads = {"HeadYaw": zero, "HeadPitch": zero, "HeadRoll": zero, "HeadControlSwitch": ([0.0, 2.0], [1.0, 1.0])}
    _write(a, heads)
    EAL.save_asset(anim_path)
    call("seq.new", path=seq_path, start=0, end=48, fps=24, replace=True)
    call("seq.anim", path=seq_path, label=label, component=face_component,
         sections=[{"anim": anim_path, "start": 0, "end": 48, "loop": True}])
    bones = ["FACIAL_L_Eye", "FACIAL_R_Eye", "head"]
    frame = 12

    def measure(fs):
        m = yield from sample(seq_path, label, face_component, bones, frames=fs, ticks=3)
        return m

    rest = yield from measure([frame])
    eL, eR = rest["bones"]["FACIAL_L_Eye"][0], rest["bones"]["FACIAL_R_Eye"][0]
    mid0 = _mid(eL[:3], eR[:3])
    head0 = rest["bones"]["head"][0][:3]
    up = [0.0, 0.0, 1.0]
    fwd = _unit([mid0[0] - head0[0], mid0[1] - head0[1], 0.0])  # the face looks past its eyes
    left = _unit(_cross(fwd, up))  # Unreal is left-handed: up x fwd is the character's right
    raw = {}
    last = rest

    def apply(curves):
        _write(a, {**heads, **curves})
        EAL.save_asset(anim_path)

    resp = {}  # curve -> {"yaw": sideways cm, "pitch": up cm, "roll": eye height difference cm}
    for name in ("HeadYaw", "HeadPitch", "HeadRoll"):
        apply({name: ([0.0, 2.0], [degrees, degrees])})
        m = yield from _await_change(measure, frame, "FACIAL_L_Eye", last["bones"]["FACIAL_L_Eye"][0])
        last = m
        l1, r1 = m["bones"]["FACIAL_L_Eye"][0], m["bones"]["FACIAL_R_Eye"][0]
        d = _sub(_mid(l1[:3], r1[:3]), mid0)
        # the top of the head to the character's left raises the right eye against the left
        resp[name] = {"yaw": _dot(d, left), "pitch": _dot(d, up), "roll": (r1[2] - l1[2]) - (eR[2] - eL[2])}
        raw[name] = {k: round(v, 4) for k, v in resp[name].items()}
    try:
        curves = head_axes(resp)
    except ValueError as e:
        apply({})
        raise OpError(f"{label}'s head curves: {e} (cm at the eyes for {degrees} each: {raw})", code="failed",
                      details={"raw": raw},
                      hint="drive the face from Sequencer with mh.drive_face, and check its Anim Blueprint reads "
                           "HeadYaw/HeadPitch/HeadRoll with HeadControlSwitch=1") from None
    dead = [c for c in resp if max(abs(v) for v in resp[c].values()) < LIVE_CM]
    signs = {k: (1.0 if resp[c][k] > 0 else -1.0) if c not in dead else 1.0 for k, c in curves.items()}
    apply({})
    yield from _await_change(measure, frame, "FACIAL_L_Eye", last["bones"]["FACIAL_L_Eye"][0])
    rest2 = yield from measure([frame])
    eye_deg, flip_votes = {}, []
    base_axes = rest2["bones"]["FACIAL_L_Eye"][0]
    axes0 = [base_axes[3:6], base_axes[6:9], base_axes[9:12]]
    g = max(range(3), key=lambda i: abs(_dot(axes0[i], fwd)))  # the eye's gaze axis: the one along the face
    gs = 1.0 if _dot(axes0[g], fwd) > 0 else -1.0
    last = rest2
    for d in ("Left", "Right", "Up", "Down"):
        apply({f"CTRL_expressions_eyeLook{d}L": ([0.0, 2.0], [1.0, 1.0])})
        m = yield from _await_change(measure, frame, "FACIAL_L_Eye", last["bones"]["FACIAL_L_Eye"][0])
        last = m
        x = m["bones"]["FACIAL_L_Eye"][0]
        gaze_new = [gs * c for c in [x[3:6], x[6:9], x[9:12]][g]]
        gaze_old = [gs * c for c in axes0[g]]
        ang = math.degrees(math.acos(max(-1.0, min(1.0, _dot(_unit(gaze_new), _unit(gaze_old))))))
        eye_deg[d] = round(ang, 2)
        if d == "Left":
            flip_votes.append(_dot(_sub(gaze_new, gaze_old), left) < 0)
        raw[f"eyeLook{d}L"] = round(ang, 3)
    apply({})
    result = HeadSigns(signs["yaw"], signs["pitch"], signs["roll"], eye_deg, True, bool(flip_votes and flip_votes[0]),
                       curves)
    path = _signs_file(skel)
    with open(path, "w") as f:
        json.dump(result.to_json(), f, indent=1)
    if LSE.get_current_level_sequence():
        LSE.close_level_sequence()
    return {"signs": result.to_json(), "file": path, "skeleton": skel, "raw": raw, "dead_curves": dead, "changed": True}


# --- the PERFORMANCE spec ----------------------------------------------------------------------------------------

def _spec(spec) -> dict:
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except ValueError:
            if os.path.exists(spec):
                with open(spec) as f:
                    txt = f.read()
                try:
                    spec = json.loads(txt)
                except ValueError:
                    import yaml  # noqa: the client sends JSON; YAML only for a file on the box
                    spec = yaml.safe_load(txt)
            else:
                raise OpError("spec must be an object, JSON text or a file on the box", code="bad_args") from None
    errs = SP.validate(spec)
    if errs:
        raise OpError("bad performance spec: " + "; ".join(errs[:6]), code="bad_args",
                      details={"errors": errs}, hint="the schema: tools/filmtools/unreal/schemas/performance.schema.json")
    return spec


def _solve_path(spec: dict, line: dict, i: int) -> str:
    folder = (spec.get("face") or {}).get("solve_folder", f"/Game/Perf/{spec['name']}/Speech")
    return f"{folder}/Anim/AS_{SP.solve_name(spec, line, i)}"


@op("perf.state", mutates=False, idempotent=True)
def state(*, spec: dict) -> dict:
    """What a performance spec depends on, read from the editor (the planner's input): the sequence's rate, the
    actor's position/facing/head height and face mesh, every target's position, clip lengths, each line's audio
    analysis and speech-solve key, and the composed face animation's fingerprint.
    Example: film-ue op perf.state spec=@performance.yaml
    """
    from .seq import aim_point, component_of
    from ._util import actor
    spec = _spec(spec)
    fc = spec.get("face_component", "Face")
    seq_exists = EAL.does_asset_exist(spec["sequence"])
    fps = float(spec.get("fps", 24))
    if seq_exists:
        r = load(spec["sequence"]).get_display_rate()
        fps = r.numerator / r.denominator
    a = actor(spec["actor"])
    loc, yaw = a.get_actor_location(), a.get_actor_rotation().yaw
    try:
        comp = component_of(spec["actor"], fc)
    except StopIteration:
        raise not_found("component", fc, [c.get_name() for c in a.get_components_by_class(unreal.SkeletalMeshComponent)],
                        hint="set face_component in the spec") from None
    hp = comp.get_socket_location("head")
    mesh = comp.get_skeletal_mesh_asset()
    try:
        bmesh = component_of(spec["actor"], spec.get("body_component", "Body")).get_skeletal_mesh_asset()
    except StopIteration:
        bmesh = None
    targets = {}
    if spec.get("camera"):
        targets["camera"] = aim_point(spec["camera"])
    for k, v in (spec.get("targets") or {}).items():
        if isinstance(v, dict):
            targets[k] = aim_point(v.get("actor") or v.get("target"), v.get("offset"))
        else:
            targets[k] = aim_point(v)
    clips = {}
    lib = spec.get("library") or {}
    paths = list(lib.get("idle") or []) + [g["anim"] for g in (lib.get("gestures") or {}).values()]
    if lib.get("walk"):
        paths.append(lib["walk"]["anim"] if isinstance(lib["walk"], dict) else lib["walk"])
    paths += [ln["face_anim"] for ln in spec["lines"] if ln.get("face_anim")]
    for p in paths:
        p = p if isinstance(p, str) else p.get("anim")
        if EAL.does_asset_exist(p):
            clips[p] = {"length_s": float(unreal.AnimationLibrary.get_sequence_length(load(p)))}
        else:
            clips[p] = {"missing": True}
    audio, solves = {}, {}
    for i, ln in enumerate(spec["lines"]):
        lid = ln.get("id", f"line{i}")
        if ln.get("audio"):
            if os.path.exists(ln["audio"]):
                env = AU.Envelope.from_wav(ln["audio"])
                step = max(1, int(env.rate / 25))
                audio[lid] = {"duration_s": round(env.duration_s, 3), "emphasis": env.emphasis(),
                              "phrase_ends": env.phrase_ends(),
                              "envelope": {"rate": env.rate / step, "values": [round(v, 3) for v in env.values[::step]]}}
            else:
                audio[lid] = {"missing": ln["audio"]}
            sp = _solve_path(spec, ln, i)
            if EAL.does_asset_exist(sp):
                solves[lid] = {"anim": sp, "key": _meta(load(sp), "fm.perf.solve_key")}
    out = SP.out_anim(spec)
    fp = _meta(load(out), "fm.perf.fingerprint") if EAL.does_asset_exist(out) else ""
    return {"fps": fps, "sequence": {"exists": seq_exists},
            "actor": {"loc": [loc.x, loc.y, loc.z], "yaw": yaw, "head_z_cm": round(hp.z - loc.z, 2),
                      "face_mesh": mesh.get_path_name().split(".")[0] if mesh else "",
                      "body_mesh": bmesh.get_path_name().split(".")[0] if bmesh else ""},
            "targets": targets, "clips": clips, "audio": audio, "solves": solves,
            "face": {"anim": out if fp or EAL.does_asset_exist(out) else "", "fingerprint": fp}}


@op("perf.plan", mutates=False, idempotent=True)
def plan(*, spec: dict) -> dict:
    """What perf.apply would do for a performance spec, without doing it: {"steps": [{"op", "args", "why"}],
    "compiled": timeline, body sections and notes}. Empty steps = converged.
    Example: film-ue op perf.plan spec=@performance.yaml
    """
    spec = _spec(spec)
    st = state(spec=spec)
    missing = [k for k, v in st["clips"].items() if v.get("missing")] + [v["missing"] for v in st["audio"].values() if "missing" in v]
    steps = SP.plan(spec, st)
    try:
        c = SP.compile(spec, st)
        compiled = {"timeline": c["timeline"], "duration_s": c["duration_s"], "body": c["body"], "notes": c["notes"],
                    "transform_keys": len(c["transform"])}
    except ValueError as e:
        compiled = {"error": str(e)}
    return {"steps": steps, "compiled": compiled, "missing": missing}


@op("perf.solve", mutates=True, idempotent=True, tags=["slow"])
def solve(*, wav: str, name: str, face_mesh: str, mood: str = "NEUTRAL", intensity: float = 1.0,
          folder: str = "/Game/Speech", key: str = ""):
    """A line's speech solve (speech.to_face) tagged with the key of what it was made from, so perf.plan knows when
    it is up to date. A multi-tick job.
    Example: film-ue op perf.solve wav=/home/ue/Audio/l1.wav name=intro_l1 face_mesh=/Game/MetaHumans/Ada/Face/Ada_FaceMesh mood=HAPPINESS
    """
    from .speech import to_face
    r = yield from to_face(wav=wav, name=name, face_mesh=face_mesh, mood=mood, intensity=intensity, folder=folder)
    if not r.get("anim"):
        raise OpError(f"the speech solve of {wav} exported nothing", code="engine", details=r)
    a = load(r["anim"])
    _meta(a, "fm.perf.solve_key", key)
    _meta(a, "fm.perf.made_by", "perf.solve")
    EAL.save_asset(r["anim"])
    return {**r, "key": key, "changed": True}


def _place(curves: dict, t0: float, dur: float, into: dict) -> None:
    """Add an animation's curves into `into` shifted to start at t0 and cut at dur, each bracketed by its rest value
    (0) just outside the line, so a mouth closes between lines instead of holding."""
    eps = 1.0 / 120.0
    for n, (t, v) in curves.items():
        pts = [(t0 + x, y) for x, y in zip(t, v) if x <= dur + 1e-6]
        if not pts:
            continue
        rest = 1.0 if n == "HeadControlSwitch" else 0.0
        seq = [(max(0.0, t0 - eps), rest)] + pts + [(t0 + dur + eps, rest)]
        tt, vv = into.setdefault(n, ([], []))
        for x, y in seq:
            if tt and x <= tt[-1]:
                continue
            tt.append(x)
            vv.append(y)


def _speech_fn(tl: list, st: dict):
    envs = []
    for x in tl:
        e = (st.get("audio") or {}).get(x["id"], {}).get("envelope")
        envs.append((x["start_s"], x["end_s"], e, x["listen"]))

    def f(t):
        for a, b, e, listen in envs:
            if a <= t <= b and not listen:
                if not e:
                    return 0.7
                i = (t - a) * e["rate"]
                vals = e["values"]
                if i < 0 or i >= len(vals) - 1:
                    return 0.0
                k = int(i)
                return vals[k] + (vals[k + 1] - vals[k]) * (i - k)
        return 0.0
    return f


@op("perf.compose", mutates=True, idempotent=True)
def compose(*, spec: dict) -> dict:
    """Compose a performance spec into the sequence: one continuous face animation (every line's lip-sync placed at
    its time, with the head, eyes, blinks, moods and expressions of perfkit over the whole timeline, so nothing
    jumps between lines) on the face track, the body's idle/gesture/walk sections, and the actor's transform keys.
    perf.apply calls it after the speech solves; call it yourself to re-key without re-solving.
    Returns: {"face_anim", "fingerprint", "frames", "report", "timeline", "body_sections", "notes", "changed"}.
    Example: film-ue op perf.compose spec=@examples/unreal/performance/listener.yaml
    """
    from .anim import _write, new as anim_new, read_all
    spec = _spec(spec)
    st = state(spec=spec)
    try:
        c = SP.compile(spec, st)
    except ValueError as e:
        raise OpError(str(e), code="bad_args") from None
    fps = c["fps"]
    base: dict = {}
    for x in c["timeline"]:
        ln = spec["lines"][x["index"]]
        src = (st["solves"].get(x["id"]) or {}).get("anim") if ln.get("audio") else ln.get("face_anim")
        if src:
            _place(read_all(load(src)), x["start_s"], x["duration_s"], base)
        elif ln.get("audio"):
            raise OpError(f"line {x['id']} has no speech solve yet", code="conflict", hint="run perf.apply (it solves first)")
    fa = dict(c["face"])
    fa.pop("talk_spans", None)
    face_mesh = st["actor"]["face_mesh"]
    signs = signs_for(_skel_of(face_mesh), fa.pop("signs", None))
    r = FACE.build(**fa, base=base, speech=_speech_fn(c["timeline"], st), signs=signs)
    out = c["face_out"]
    try:  # converge on the existing animation (the sequence plays it), else start afresh
        anim_new(path=out, skeleton=face_mesh, length_s=c["duration_s"], fps=30)
    except OpError:
        anim_new(path=out, skeleton=face_mesh, length_s=c["duration_s"], fps=30, replace=True)
    o = load(out)
    ctrl = o.get_editor_property("controller")
    ctrl.open_bracket("fmbridge perf.compose", False)
    try:  # last composition's curves go: a line taken out must not leave its mouth behind
        ctrl.remove_all_curves_of_type(unreal.RawCurveTrackTypes.RCT_FLOAT, False)
    finally:
        ctrl.close_bracket(False)
    _write(o, {**base, **r["curves"]})
    fp = SP.fingerprint(spec, st)
    _meta(o, "fm.perf.fingerprint", fp)
    _meta(o, "fm.perf.spec", spec["name"])
    _meta(o, "fm.perf.made_by", "perf.compose")
    EAL.save_asset(out)
    frames = int(round(c["duration_s"] * fps))
    if not EAL.does_asset_exist(spec["sequence"]):
        call("seq.new", path=spec["sequence"], start=0, end=frames, fps=int(round(fps)))
    else:
        s = load(spec["sequence"])
        if s.get_playback_end() < frames:
            s.set_playback_end(frames)
    label = spec["actor"]
    call("seq.anim", path=spec["sequence"], label=label, component=spec.get("face_component", "Face"),
         sections=[{"anim": out, "start": 0, "end": frames, "loop": False}], replace=True)
    body = list(c["body"])
    life = (spec.get("character") or {}).get("body_life")
    if life and st["actor"].get("body_mesh"):
        opts = life if isinstance(life, dict) else {}
        talk = any(not x["listen"] for x in c["timeline"])
        try:
            r_life = call("anim.body_life", out=f"{out}_life", body_mesh=st["actor"]["body_mesh"],
                          length_s=c["duration_s"], state=opts.get("state", "talk" if talk else "listen"), face_anim=out,
                          **{k: v for k, v in opts.items() if k in ("follow", "breath_deg", "clavicle_deg", "shift_cm")},
                          seed=int(spec.get("seed", 0)))
            body.append({"anim": r_life["out"], "start": 0, "end": frames, "loop": False, "kind": "life"})
        except OpError as e:  # not calibrated yet: the performance still applies, without body life
            c["notes"].append({"skipped": "body_life", "why": e.message, "hint": e.hint})
    if body:
        call("seq.anim", path=spec["sequence"], label=label, component=spec.get("body_component", "Body"),
             sections=[{k: v for k, v in s.items() if k not in ("kind", "additive", "stroke_frame")} for s in body],
             replace=True)
    if c["transform"]:
        call("seq.key_transform", path=spec["sequence"], label=label, keys=c["transform"])
    return {"face_anim": out, "fingerprint": fp, "frames": frames, "fps": fps, "report": r["report"],
            "plan": r["plan"], "timeline": c["timeline"], "body_sections": len(body), "notes": c["notes"],
            "changed": True}


def _skel_of(mesh_path: str) -> str:
    from .anim import _skeleton_path
    return _skeleton_path(load(mesh_path)) if mesh_path and EAL.does_asset_exist(mesh_path) else ""


@op("perf.lock_eyes", mutates=True, idempotent=True, tags=["slow"])
def lock_eyes(*, spec: dict):
    """Measured eye contact with the spec's camera over the composed face (anim.gaze_lock: the eye curves solved
    from the eye bones' real pose on the lines that look at the camera). A multi-tick job.
    Example: film-ue op perf.lock_eyes spec=@examples/unreal/performance/presenter_intro.yaml
    """
    spec = _spec(spec)
    out = SP.out_anim(spec)
    return (yield from call("anim.gaze_lock", sequence=spec["sequence"], actor_label=spec["actor"], anim=out,
                            out=out + "_eyes", camera=spec["camera"], component=spec.get("face_component", "Face")))


@op("perf.apply", mutates=True, idempotent=True, tags=["slow"])
def apply(*, spec: dict, dry_run: bool = False, max_rounds: int = 2):
    """Converge the editor on a PERFORMANCE spec (kind: performance): speech-solve the lines whose audio or mood
    changed, compose the face, key the body and the actor's moves in the sequence; re-run safely (a converged spec
    does nothing). `dry_run` returns the plan only. A multi-tick job (speech solves take seconds per line).

    Returns: {"converged", "rounds", "ran": [{"op", "why", "result"}], "report": the face's naturalness checks}.
    Example: film-ue op perf.apply spec=@films/demo/perf/intro.yaml
    """
    import inspect
    spec = _spec(spec)
    ran, report = [], None
    for rnd in range(max_rounds + 1):
        st = state(spec=spec)
        steps = SP.plan(spec, st)
        if dry_run:
            return {"steps": steps, "converged": not steps}
        if not steps:
            return {"converged": True, "rounds": rnd, "ran": ran, "report": report, "changed": bool(ran)}
        if rnd == max_rounds:
            break
        for s in steps:
            res = call(s["op"], **s["args"])
            if inspect.isgenerator(res):
                res = yield from res
            if s["op"] == "perf.compose":
                report = res.get("report")
            ran.append({"op": s["op"], "why": s["why"], "result": {k: v for k, v in (res or {}).items()
                                                                    if k in ("anim", "face_anim", "fingerprint", "frames",
                                                                             "notes", "seconds")}})
    raise OpError(f"the performance did not converge in {max_rounds} rounds", code="failed",
                  details={"ran": ran, "left": steps}, hint="perf.plan shows what keeps changing")


@op("perf.describe", mutates=False, idempotent=True)
def describe(*, sequence: str, label: str, face_component: str = "Face", body_component: str = "Body") -> dict:
    """An actor's performance in a sequence: the animation sections on its face and body tracks, the face
    animation's perf metadata (which spec, its fingerprint), and its transform keys.
    Example: film-ue op perf.describe sequence=/Game/Shots/S010 label=Presenter
    """
    from .seq import _comp_binding
    seq = load(sequence)
    out = {"sequence": sequence, "label": label}
    for key, comp in (("face", face_component), ("body", body_component)):
        try:
            b = _comp_binding(seq, label, comp, create=False)
        except Exception:
            out[key] = None
            continue
        secs = []
        for t in b.find_tracks_by_type(unreal.MovieSceneSkeletalAnimationTrack):
            for s in t.get_sections():
                anim = s.get_editor_property("params").get_editor_property("animation")
                p = anim.get_path_name().split(".")[0] if anim else None
                secs.append({"anim": p, "start": s.get_start_frame() if s.has_start_frame() else None,
                             "end": s.get_end_frame() if s.has_end_frame() else None, "row": s.get_row_index(),
                             "perf": {k: _meta(anim, f"fm.perf.{k}") for k in ("spec", "fingerprint", "made_by")}
                             if anim else {}})
        out[key] = sorted(secs, key=lambda s: (s["start"] or 0, s["row"]))
    try:
        ab = _comp_binding(seq, label, "", create=False)
        tr = ab.find_tracks_by_type(unreal.MovieScene3DTransformTrack)
        out["transform_keys"] = sum(len(ch.get_keys()) for t in tr for s in t.get_sections()
                                    for ch in list(s.get_all_channels())[:1])
    except Exception:
        out["transform_keys"] = 0
    return out


# --- body moves without a spec -----------------------------------------------------------------------------------

def _clip(path: str, speed: float = 0.0) -> dict:
    from .anim import _anim
    a = _anim(path)
    return {"anim": path, "length_s": float(unreal.AnimationLibrary.get_sequence_length(a)), "speed_cm_s": speed}


@op("perf.walk_to", mutates=True, idempotent=True)
def walk_to(*, sequence: str, label: str, to: list | str, walk_anim: str, at_frame: int = 0, speed_cm_s: float = 140.0,
            clip_speed_cm_s: float = 0.0, path: list | None = None, end_facing=None, facing_offset_deg: float = 0.0,
            component: str = "Body") -> dict:
    """Walk an actor to a point in a sequence: turn in place if needed, accelerate, follow `path` waypoints, brake,
    optionally turn to face `end_facing`; the actor's transform is keyed (replacing its transform track) and the walk
    loop is added on the body track at the play rate that matches its own speed (`clip_speed_cm_s`, default
    speed_cm_s: rate 1).

    Args: to: [x, y, z] cm, or a target (actor label, "Label:Component:bone"). at_frame: when it sets off.
    speed_cm_s: cruise speed (people: 110-150). facing_offset_deg: the actor's forward vs its mesh's (MetaHumans: 0).
    Returns: {"changed", "keys", "frames": [start, stop], "distance_cm", "walk": the walk section, "slide": check}.
    Example: film-ue op perf.walk_to sequence=/Game/Shots/S020 label=Presenter 'to=[300,120,0]' walk_anim=/MetaHumanCharacter/Optional/Animation/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Walk_Loop_F at_frame=24
    """
    from .seq import aim_point, _fps
    from ._util import actor
    seq = load(sequence)
    fps = _fps(seq)
    a = actor(label)
    loc = a.get_actor_location()
    start = [loc.x, loc.y, loc.z]
    pts = [aim_point(p) for p in (path or [])] + [aim_point(to)]
    pts = [[p[0], p[1], loc.z] for p in pts]
    end_yaw = None
    if end_facing is not None:
        end_yaw = BD.heading_deg(pts[-1], aim_point(end_facing), -facing_offset_deg)
    wp = BD.walk(at_frame / fps, start, pts, fps, speed_cm_s=speed_cm_s, yaw0=a.get_actor_rotation().yaw,
                 facing_offset_deg=-facing_offset_deg, end_yaw=end_yaw)
    keys = wp["keys"]
    if keys and keys[0][0] > 0:
        keys.insert(0, [0, [round(v, 2) for v in start], {"yaw": round(a.get_actor_rotation().yaw, 2)}])
    call("seq.key_transform", path=sequence, label=label, keys=keys)
    clip = _clip(walk_anim, clip_speed_cm_s or speed_cm_s)
    secs, chk = BD.walk_sections(wp, clip, None, fps, speed_cm_s)
    if secs:
        call("seq.anim", path=sequence, label=label, component=component,
             sections=[{k: v for k, v in s.items() if k != "kind"} for s in secs], replace=False)
    return {"changed": True, "keys": len(keys), "frames": [int(wp["walk"][0] * fps), int(wp["walk"][1] * fps)] if wp["walk"] else None,
            "distance_cm": wp["distance_cm"], "walk": secs[0] if secs else None, "slide": chk}


@op("perf.turn_to", mutates=True, idempotent=True)
def turn_to(*, sequence: str, label: str, target: list | str | float, at_frame: int = 0, facing_offset_deg: float = 0.0,
            speed: float = 1.0) -> dict:
    """Turn an actor in place to face a target (a point, an actor, "Label:Component:bone") or a yaw (degrees),
    eased with a skewed min-jerk over 0.45 s + 0.5 s per 90 deg (/ speed); keys its transform (replacing the
    transform track, so give a whole route to perf.walk_to or a spec instead when there are several moves).
    Example: film-ue op perf.turn_to sequence=/Game/Shots/S020 label=Presenter target=Guest at_frame=48
    """
    from .seq import aim_point, _fps
    from ._util import actor
    seq = load(sequence)
    fps = _fps(seq)
    a = actor(label)
    loc = a.get_actor_location()
    here = [loc.x, loc.y, loc.z]
    y0 = a.get_actor_rotation().yaw
    y1 = float(target) if isinstance(target, (int, float)) else BD.heading_deg(here, aim_point(target), -facing_offset_deg)
    tk, t_end = BD.turn(at_frame / fps, y0, y1, fps, speed)
    keys = ([[0, here, {"yaw": y0}]] if at_frame > 0 else []) + [[f, here, {"yaw": round(y, 2)}] for f, y in tk]
    call("seq.key_transform", path=sequence, label=label, keys=keys)
    return {"changed": True, "keys": len(keys), "yaw": [round(y0, 2), round(BD.unwrap(y0, y1), 2)],
            "end_frame": int(round(t_end * fps))}


@op("perf.idle", mutates=True, idempotent=True)
def idle(*, sequence: str, label: str, clips: list, start: int = 0, end: int = 0, component: str = "Body",
         seed: int = 0, gaps: list | None = None, replace: bool = True) -> dict:
    """An idle that never loops visibly on an actor's body track: segments of 4-9 s from the given idle clips at
    random offsets and play rates 0.92-1.08, cross-fading into each other; split around `gaps` [[start, end]]
    frames (where gestures play). end 0 = the sequence's end.
    Example: film-ue op perf.idle sequence=/Game/Shots/S010 label=Presenter 'clips=["/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"]'
    """
    from .seq import _fps
    seq = load(sequence)
    fps = _fps(seq)
    end = end or seq.get_playback_end()
    cl = [_clip(p) for p in clips]
    secs = BD.idles(start / fps, end / fps, cl, fps, gaps=[(a / fps, b / fps) for a, b in (gaps or [])], seed=seed)
    call("seq.anim", path=sequence, label=label, component=component,
         sections=[{k: v for k, v in s.items() if k != "kind"} for s in secs], replace=replace)
    return {"changed": True, "sections": secs}


@op("perf.gestures", mutates=True, idempotent=True)
def gestures(*, sequence: str, label: str, gestures: list, library: dict | None = None, component: str = "Body",
             lead_s: float = 0.08) -> dict:
    """Gestures timed to their beats: each {"anim" | "name", "at_s" (the beat: the stressed word), "stroke_s" (where
    the stroke falls in the clip; default 40% in), "hold_s", "intensity"}; the clip starts so its stroke lands
    `lead_s` before the beat. Overlaps are moved or dropped (see notes). Adds the sections to the body track.
    Example: film-ue op perf.gestures sequence=/Game/Shots/S010 label=Presenter 'gestures=[{"anim":"/Game/Anim/AS_OpenPalms","at_s":2.1,"stroke_s":0.7}]'
    """
    from .seq import _fps
    seq = load(sequence)
    fps = _fps(seq)
    lib = {k: {**v, "length_s": v.get("length_s") or _clip(v["anim"])["length_s"]} for k, v in (library or {}).items()}
    gs = []
    for g in gestures:
        g = dict(g)
        if g.get("anim") and "length_s" not in g:
            g["length_s"] = _clip(g["anim"])["length_s"]
        gs.append(g)
    secs, notes = BD.place_gestures(gs, lib, fps, lead_s=lead_s)
    if secs:
        call("seq.anim", path=sequence, label=label, component=component,
             sections=[{k: v for k, v in s.items() if k not in ("kind", "additive", "stroke_frame")} for s in secs],
             replace=False)
    return {"changed": bool(secs), "sections": secs, "notes": notes}


@op("perf.head_curves", mutates=False, idempotent=True)
def head_curves(*, duration_s: float, gaze: list | None = None, nods: list | None = None, tilts: list | None = None,
                head: dict | None = None, lead: str = "eyes", seed: int = 0, rate: float = 30.0) -> dict:
    """Preview organic head motion with no engine and no animation: the HeadYaw/Pitch/Roll curves (character frame,
    degrees) perfkit makes for these gaze shifts, nods and tilts, with the plan and the head checks. For trying
    styles before writing them (perf.face).
    Example: film-ue op perf.head_curves duration_s=6 'gaze=[{"t":1,"yaw":30},{"t":3.5,"yaw":-10,"pitch":-5}]' 'nods=[{"t":4.5,"kind":"nod"}]'
    """
    from ..perfkit import gaze as GZ
    from ..perfkit import metrics as M
    style = HD.Style.from_json({"seed": seed, **(head or {})})
    plan_ = GZ.GazePlan([FACE._shift(s) for s in (gaze or [])], lead=lead, head_gain=style.gain, seed=seed)
    h = HD.compose(0.0, float(duration_s), plan_, [FACE._nod(n) for n in nods or []],
                   [FACE._tilt(t) for t in tilts or []], style, None, rate)
    rig = HD.to_rig(h, HeadSigns(), tol_deg=0.02, switch=False)
    checks = [M.frozen_head(rig), M.head_linear(rig), M.head_jitter(rig)]
    return {"times": [round(t, 4) for t in h["times"]], "yaw": [round(v, 3) for v in h["yaw"]],
            "pitch": [round(v, 3) for v in h["pitch"]], "roll": [round(v, 3) for v in h["roll"]],
            "shifts": plan_.events, "checks": checks}


__all__ = ["HEAD"]
