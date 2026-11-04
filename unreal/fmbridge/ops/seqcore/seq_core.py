"""WP8 Sequencer core ops: describe a sequence as JSON, plan and apply a SEQUENCE SPEC (idempotent, batched), write or
remove one canonical track, bindings, markers, engine evaluation for checks, shots and render chunks with cloth
pre-roll, copy / retime / offset, time conversion. The guide is docs/unreal/sequencer.md; the spec's schema is
tools/filmtools/unreal/schemas/sequence.schema.json.

The older ops in ops/seq.py (seq.shot, seq.key_*, seq.anim, seq.audio, seq.camera_cuts, seq.sample, seq.still...)
keep working; a spec through seq.apply does the same work in one converging call.
"""
from __future__ import annotations

import copy
import json

import unreal

from .. import op
from ...errors import OpError
from ..assets import EAL, free
from . import _engine as E
from ._model import index, track_id, track_label, transform_time, clip
from ._plan import chunks as plan_chunks, diff as plan_diff, lint, plan as make_plan, shots_of
from ._spec import SpecError, compile_spec, validate as spec_validate
from ._time import Rate, snap


def _spec(spec) -> dict:
    """A spec given as a dict, JSON text, or a .json path on the box."""
    if isinstance(spec, dict):
        return copy.deepcopy(spec)
    if isinstance(spec, str):
        s = spec.strip()
        if s.startswith("{"):
            return json.loads(s)
        if s.endswith(".json"):
            with open(s) as f:
                return json.load(f)
    raise OpError("spec must be a mapping (or JSON text / a .json file on the box)", code="bad_args",
                  hint="the client loads YAML: film-ue apply spec.yaml, or seq_spec.load(path)")


def _compiled(spec: dict) -> tuple:
    spawn = [label for label, b in (spec.get("bindings") or {}).items() if isinstance(b, dict) and b.get("spawn")] \
        if isinstance(spec.get("bindings"), dict) else []
    try:
        return compile_spec(spec, E.EngineResolver(spawn))
    except SpecError as e:
        raise OpError(str(e), code="bad_args", details={"problems": e.problems},
                      hint="seq.validate lists them; the schema is schemas/sequence.schema.json") from None


@op("seq.describe", mutates=False, idempotent=True, tags=["sequencer", "describe"])
def describe(*, path: str, spec: dict = None, keys: bool = True, check: bool = False) -> dict:
    """A level sequence as JSON: rate, range, markers, bindings (bound or not), every track with sections and keys.

    The same shape seq.apply takes ("tracks"), so a describe fed back is a no-op. With `spec`, also "want": the
    spec compiled against the level (look-at targets, clip lengths, property owners resolved) for planning
    offline. `keys` False gives key counts instead of keys. `check` adds "lint" (seq.check's verdict).
    Args: path: /Game/... sequence. spec: a sequence spec (dict). keys: bool. check: bool.
    Returns: {"exists", "sequence", "fps", "tick_resolution", "range": [start, end), "markers", "bindings",
    "tracks", "unsupported"(, "want", "notes", "lint")}.
    Example: film-ue op seq.describe path=/Game/Film/SEQ_010 keys=false
    """
    doc = E.describe(path, keys=keys)
    if spec is not None:
        want, notes = _compiled(_spec(spec))
        doc["want"], doc["notes"] = want, doc.get("notes", []) + notes
    if check and doc["exists"]:
        doc["lint"] = lint(doc)
    return doc


@op("seq.validate", mutates=False, idempotent=True, tags=["sequencer", "spec"])
def validate(*, spec: dict) -> dict:
    """Check a sequence spec without touching anything: every problem at once, with where and what to write.

    Args: spec: a sequence spec (dict). Returns: {"ok", "problems": [...], "notes": [...], "tracks": [labels]}.
    Example: film-ue op seq.validate 'spec={"sequence": "/Game/S/SEQ_A", "duration": "5s"}'
    """
    return spec_validate(_spec(spec))


@op("seq.plan", mutates=False, idempotent=True, tags=["sequencer", "spec"])
def plan(*, spec: dict, prune: bool = None) -> dict:
    """What seq.apply would do to converge the level's sequence to `spec`: the steps, nothing changed.

    Args: spec: a sequence spec. prune: also remove unlisted tracks of the bindings the spec names (default: the
    spec's `prune`). Returns: {"steps": [{"op", "args", "why"}], "converged": bool, "notes"}.
    Example: film-ue plan examples/unreal/sequence/two_shot.yaml
    """
    spec = _spec(spec)
    want, notes = _compiled(spec)
    have = E.describe(want["sequence"])
    steps = make_plan(want, have if have["exists"] else None, prune=prune)
    return {"steps": [_brief(s) for s in steps], "converged": not steps, "notes": notes}


def _brief(step: dict) -> dict:
    """A step for display: a track argument summarised (keys counted)."""
    s = copy.deepcopy(step)
    t = s["args"].get("track")
    if t:
        s["args"]["track"] = {"id": track_label(t), "sections": len(t["sections"]),
                              "keys": sum(len(c.get("keys") or []) for x in t["sections"] for c in x["channels"].values())}
    return s


@op("seq.apply", mutates=True, idempotent=True, tags=["sequencer", "spec"])
def apply(*, spec: dict, prune: bool = None, dry_run: bool = False, save: bool = True):
    """Converge a level sequence to a SEQUENCE SPEC in one call: create it, bind actors, write only the tracks that
    differ (each track's keys batched), set markers; then describe again and confirm nothing is left to do.

    Re-running with the same spec changes nothing (changed false). Tracks the spec does not name are kept unless
    `prune`. A multi-tick job (big writes yield). See docs/unreal/sequencer.md for the spec.
    Args: spec: the spec (dict). prune: bool. dry_run: plan only. save: save the asset.
    Returns: {"changed", "steps": [{"op", "why", "result"}], "converged", "remaining": [...], "notes", "sequence"}.
    Example: film-ue apply examples/unreal/sequence/two_shot.yaml
    """
    spec = _spec(spec)
    want, notes = _compiled(spec)
    path = want["sequence"]
    have = E.describe(path)
    steps = make_plan(want, have if have["exists"] else None, prune=prune)
    if dry_run:
        return {"changed": False, "steps": [_brief(s) for s in steps], "converged": not steps, "notes": notes,
                "sequence": path, "dry_run": True}
    done = []
    for s in steps:
        res = yield from _run_step(s, save=False)
        done.append({"op": s["op"], "why": s["why"], "result": res})
    if steps and save:
        seq = E.find(path)
        if seq is not None:
            EAL.save_loaded_asset(seq, False)
    again = E.describe(path)
    remaining = make_plan(want, again, prune=prune)
    return {"changed": bool(steps), "steps": done, "converged": not remaining,
            "remaining": [_brief(s) for s in remaining], "notes": notes, "sequence": path}


def _run_step(step: dict, save: bool):
    """Run one planned step (a generator)."""
    a = dict(step["args"])
    name = step["op"]
    if name == "seq.write":
        return (yield from write(path=a["path"], track=a["track"], save=save))
    if name == "seq.add":
        return add(save=save, **a)
    if name == "seq.bind":
        return bind(save=save, **a)
    if name == "seq.markers":
        return markers(save=save, **a)
    if name == "seq.remove_track":
        return remove_track(save=save, **a)
    if name == "seq.rebind":
        from .. import call
        return call("seq.rebind", **a)
    raise OpError(f"unknown step {name}", code="failed")


@op("seq.add", mutates=True, idempotent=True, tags=["sequencer"])
def add(*, path: str, fps=None, start: int = None, end: int = None, tick_resolution: int = None,
        save: bool = True) -> dict:
    """Make a level sequence, or converge an existing one's rate and playback range [start, end) (frames).

    Changing `fps` on an existing sequence keeps every key at its time in seconds (keys live in ticks); its
    frame numbers change. `tick_resolution` migrates existing keys. Never opens a dialog.
    Args: path: /Game/... . fps: 24, 25, 30, 23.976, "30000/1001". start, end: frames. tick_resolution: per second.
    Returns: {"sequence", "created", "changed", "fps", "range", "tick_resolution"}.
    Example: film-ue op seq.add path=/Game/Film/SEQ_010 fps=24 start=0 end=240
    """
    seq = E.find(path)
    created = seq is None
    if created:
        folder, name = path.split(".")[0].rsplit("/", 1)
        seq = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.LevelSequence,
                                                                     unreal.LevelSequenceFactoryNew())
        if seq is None:
            raise OpError(f"could not create {path}", code="engine", hint="is the folder writable? assets.free it")
    changed = created
    if fps is not None:
        r = Rate.parse(fps)
        if E.rate(seq) != r:
            seq.set_display_rate(unreal.FrameRate(r.numerator, r.denominator))
            changed = True
    if tick_resolution is not None:
        t = Rate.parse(tick_resolution)
        if E.ticks(seq) != t:
            seq.set_tick_resolution(unreal.FrameRate(t.numerator, t.denominator))
            changed = True
    if start is not None and seq.get_playback_start() != int(start):
        seq.set_playback_start(int(start))
        changed = True
    if end is not None and seq.get_playback_end() != int(end):
        seq.set_playback_end(int(end))
        changed = True
    if changed and save:
        EAL.save_loaded_asset(seq, False)
    return {"sequence": path, "created": created, "changed": changed, "fps": str(E.rate(seq)),
            "range": [seq.get_playback_start(), seq.get_playback_end()], "tick_resolution": E.ticks(seq).numerator}


@op("seq.bind", mutates=True, idempotent=True, tags=["sequencer"])
def bind(*, path: str, label: str, spawn: dict = None, replace: bool = False, save: bool = True) -> dict:
    """Bind an actor to a sequence by its label (a possessable), or make a spawnable the sequence owns.

    spawn: {"class": "CineCameraActor"} or {"template": "<level actor label>"}; the binding is named `label`.
    `replace` remakes the binding (its tracks go with it). Converges: an existing, bound binding is kept.
    Returns: {"binding", "kind", "changed"}.
    Example: film-ue op seq.bind path=/Game/Film/SEQ_010 label=Hero
    """
    seq = E.get(path)
    with E.Writing(seq, save=False):
        b, changed = E.bind(seq, label, spawn, replace)
    if changed and save:
        EAL.save_loaded_asset(seq, False)
    return {"binding": label, "kind": "spawnable" if spawn else "possessable", "changed": changed}


@op("seq.write", mutates=True, idempotent=True, tags=["sequencer"])
def write(*, path: str, track: dict, save: bool = True):
    """Write one canonical track (seq.describe's shape) into a sequence, replacing the track of the same identity.

    Every key of the track goes in one call (batched, Sequencer closed while writing, a tick yielded every 2000
    keys). Material and collection tracks replace only the parameters given. Bindings are made as needed
    (possessables by label). A multi-tick job. Unchanged tracks are left alone (changed false).
    Args: path: sequence. track: {"kind", "binding", "component", "name", "params", "sections"}. save: bool.
    Returns: {"track", "keys", "sections", "changed"}.
    Example: film-ue op seq.write path=/Game/S/SEQ_A 'track={"kind":"float","binding":"Key","name":"Intensity","sections":[{"range":[null,null],"channels":{"value":{"keys":[[0,5],[24,10]]}}}]}'
    """
    from ._spec import Compiler
    seq = E.get(path)
    want = Compiler({"sequence": path, "fps": str(E.rate(seq)), "tracks": [track]}).raw_track(track, "track")
    have = E.track_by_id(E.describe(path), track_id(want))
    from ._model import track_equal
    if track_equal(want, have):
        return {"track": track_label(want), "keys": 0, "sections": len(want["sections"]), "changed": False}
    with E.Writing(seq, save=save):
        res = yield from E.write_track(seq, want)
    if E.LSE.get_current_level_sequence() == seq:
        E.LSE.refresh_current_level_sequence()
    res["changed"] = True
    return res


@op("seq.remove_track", mutates=True, idempotent=True, tags=["sequencer"])
def remove_track(*, path: str, kind: str, binding: str = "", component: str = "", name: str = "",
                 save: bool = True) -> dict:
    """Remove a track by identity: its kind, binding (actor label, "" = the sequence's own), component, and name
    (property path, track name, "slot:N", collection path). Removing nothing is fine.

    Returns: {"removed": n, "changed"}.
    Example: film-ue op seq.remove_track path=/Game/S/SEQ_A kind=float binding=Key name=Intensity
    """
    seq = E.get(path)
    n = E.remove_track(seq, kind, binding, component, name)
    if n and save:
        EAL.save_loaded_asset(seq, False)
    return {"removed": n, "changed": bool(n)}


@op("seq.remove_binding", mutates=True, idempotent=True, tags=["sequencer"])
def remove_binding(*, path: str, label: str, save: bool = True) -> dict:
    """Remove an actor's binding (with its component bindings and all their tracks). Removing nothing is fine.

    Returns: {"removed": n, "changed"}.
    Example: film-ue op seq.remove_binding path=/Game/S/SEQ_A label=OldCam
    """
    seq = E.get(path)
    gone = [b for (a, c), b in E.bindings(seq).items() if a == label]
    gone.sort(key=lambda b: E._parent(b) is None)  # components first
    for b in gone:
        b.remove()
    if gone and save:
        EAL.save_loaded_asset(seq, False)
    return {"removed": len(gone), "changed": bool(gone)}


@op("seq.markers", mutates=True, idempotent=True, tags=["sequencer"])
def markers(*, path: str, markers: list, save: bool = True) -> dict:
    """Set a sequence's marked frames (replacing them): [{"frame", "label"}] or [[frame, label]], display frames.

    Returns: {"markers": n, "changed"}.
    Example: film-ue op seq.markers path=/Game/S/SEQ_A 'markers=[[48,"beat"],[96,"hit"]]'
    """
    seq = E.get(path)
    ms = [m if isinstance(m, dict) else {"frame": m[0], "label": m[1] if len(m) > 1 else ""} for m in markers]
    have = E.describe(path).get("markers") or []
    if sorted((m["frame"], m.get("label", "")) for m in have) == sorted((m["frame"], m.get("label", "")) for m in ms):
        return {"markers": len(ms), "changed": False}
    E.set_markers(seq, ms)
    if save:
        EAL.save_loaded_asset(seq, False)
    return {"markers": len(ms), "changed": True}


@op("seq.diff", mutates=False, idempotent=True, tags=["sequencer", "describe"])
def diff(*, path: str, other: str = "", spec: dict = None, tol: float = 1e-4) -> dict:
    """What differs between two sequences (`path` vs `other`), or between a sequence and what a spec asks for.

    Each track that differs says where first: a param, the section count, a section's range, a channel's key
    (index, both keys). Args: path, other: sequences. spec: a sequence spec instead of `other`. tol: value tolerance.
    Returns: {"same", "sequence": {fps/range/markers: {a, b}}, "bindings": [...], "tracks": [{"track", "change":
    added|removed|changed, "where", "a", "b"}]}.
    Example: film-ue op seq.diff path=/Game/Film/SEQ_010 other=/Game/Film/SEQ_010_v2
    """
    a = E.describe(path)
    if not a["exists"]:
        raise OpError(f"no sequence {path}", code="not_found")
    if spec is not None:
        b, _ = _compiled(_spec(spec))
        b = dict(b, tracks=[dict(t) for t in b["tracks"]], markers=b["markers"] or a.get("markers"))
        # a spec claims only what it names: compare only its tracks (others are kept by apply)
        names = {track_id(t) for t in b["tracks"]}
        a = dict(a, tracks=[t for t in a["tracks"] if track_id(t) in names])
    elif other:
        b = E.describe(other)
        if not b["exists"]:
            raise OpError(f"no sequence {other}", code="not_found")
    else:
        raise OpError("give `other` (a sequence) or `spec`", code="bad_args")
    return plan_diff(a, b, tol=tol, claims_only=spec is not None)


@op("seq.check", mutates=False, idempotent=True, tags=["sequencer", "qa"])
def check(*, path: str) -> dict:
    """Numeric checks of a sequence: unbound bindings, camera-cut gaps and missing cameras, keys outside the
    range, rotation flips across +-180, overlapping shots, empty tracks.

    Returns: {"pass", "issues": [{"code", "severity", "message", "fix", "frame", "subject"}], "metrics"}.
    Example: film-ue op seq.check path=/Game/Film/SEQ_010
    """
    doc = E.describe(path)
    if not doc["exists"]:
        raise OpError(f"no sequence {path}", code="not_found", hint="seq.add or seq.apply makes it")
    return lint(doc)


@op("seq.eval", mutates=False, idempotent=True, tags=["sequencer", "qa"])
def evaluate(*, path: str, frames: list, labels: list = (), tracks: list = ()) -> dict:
    """What the sequence evaluates to at frames, without playing it: actors' world transforms (opens the sequence in
    Sequencer: ControlRigSequencerEditorLibrary evaluates the open one) and tracks' channel values (curve
    evaluation; works closed). For checking keys landed where meant.

    Args: frames: display frames. labels: actor labels -> [[x, y, z, pitch, yaw, roll], ...] per frame.
    tracks: [{"kind", "binding", "component", "name"}] -> {channel: [values]}.
    Returns: {"frames", "transforms": {label: [...]}, "channels": {track label: {channel: [...]}}}.
    Example: film-ue op seq.eval path=/Game/S/SEQ_A 'frames=[0,24,48]' 'labels=["CamA"]'
    """
    seq = E.get(path)
    out = {"frames": list(frames), "transforms": {}, "channels": {}}
    for lab in labels or []:
        out["transforms"][lab] = E.world_transforms(seq, lab, frames)
    for t in tracks or []:
        t = dict({"binding": "", "component": "", "name": ""}, **t)
        out["channels"][track_label(t)] = E.eval_channels(seq, t, frames)
    return out


@op("seq.shots", mutates=False, idempotent=True, tags=["sequencer"])
def shots(*, path: str) -> list:
    """The shots of a sequence in order: its cinematic shot track's sections, else its camera cuts.

    Returns: [{"name", "start", "end", "sequence" | "camera", "preroll"}] (frames).
    Example: film-ue op seq.shots path=/Game/Film/SEQ_Master
    """
    doc = E.describe(path, keys=False)
    if not doc["exists"]:
        raise OpError(f"no sequence {path}", code="not_found")
    return shots_of(doc)


@op("seq.chunks", mutates=False, idempotent=True, tags=["sequencer", "render"])
def render_chunks(*, path: str, start: int = None, end: int = None, max_frames: int = 0, preroll: int = 0,
                  max_preroll: int = 0) -> dict:
    """Render chunks that never start cloth cold: each lies in one shot and pre-rolls back to its shot's start.

    Cloth (and any simulation) needs its history: a render that starts mid-shot is wrong (the Linux PoC's open
    overshirt). Render [eval_from, end) and keep [start, end). max_frames > 0 splits long shots; max_preroll
    caps the pre-roll (the chunk is then flagged "cold"); preroll adds frames before every shot start.
    Returns: {"chunks": [{"start", "end", "shot", "shot_start", "preroll_frames", "eval_from", "first_after_cut",
    "cold"}], "frames", "preroll_total"}.
    Example: film-ue op seq.chunks path=/Game/Film/SEQ_010 max_frames=48 preroll=8
    """
    doc = E.describe(path, keys=False)
    if not doc["exists"]:
        raise OpError(f"no sequence {path}", code="not_found")
    return plan_chunks(doc, start=start, end=end, max_frames=max_frames, preroll=preroll, max_preroll=max_preroll)


@op("seq.preroll", mutates=True, idempotent=True, tags=["sequencer", "render"])
def preroll(*, path: str, frames: int, postroll: int = 0, save: bool = True) -> dict:
    """Give every shot / subsequence section of a sequence `frames` of pre-roll (and `postroll`): Sequencer then
    evaluates each inner sequence that long before its section starts, so simulations have history at the cut.

    Returns: {"sections": n, "changed"}.
    Example: film-ue op seq.preroll path=/Game/Film/SEQ_Master frames=24
    """
    seq = E.get(path)
    pt = E.tpf(seq)
    n = changed = 0
    for cls in (unreal.MovieSceneCinematicShotTrack, unreal.MovieSceneSubTrack):
        for t in seq.find_tracks_by_exact_type(cls):
            for s in t.get_sections():
                n += 1
                want_pre, want_post = int(round(frames * pt)), int(round(postroll * pt))
                if s.get_pre_roll_frames() != want_pre or s.get_post_roll_frames() != want_post:
                    s.set_pre_roll_frames(want_pre)
                    s.set_post_roll_frames(want_post)
                    changed += 1
    if changed and save:
        EAL.save_loaded_asset(seq, False)
    return {"sections": n, "changed": bool(changed)}


@op("seq.retime", mutates=True, idempotent=False, tags=["sequencer"])
def retime(*, path: str, offset: float = 0, scale: float = 1.0, pivot: float = 0, after: float = None,
           out: str = "", save: bool = True):
    """Move or stretch a sequence's time: f -> pivot + (f - pivot) * scale + offset, keys, sections and range alike.

    `after` makes it a ripple (only what is at or after that frame moves: insert time with offset > 0, close a gap
    with offset < 0). Animation sections play at rate / scale; audio is moved, never stretched. `out`: write to a
    copy (made with the asset duplicated) and leave `path` as it is. Tracks of unsupported classes are not moved
    (listed in "untouched"). Not idempotent: each call moves again. A multi-tick job.
    Returns: {"sequence", "tracks", "notes", "untouched", "changed"}.
    Example: film-ue op seq.retime path=/Game/S/SEQ_A offset=12 after=96
    """
    target = path
    if out:
        yield from _copy_asset(path, out, replace=True)
        target = out
    doc = E.describe(target)
    moved, notes = transform_time(doc, offset=offset, scale=scale, pivot=pivot, after=after)
    seq = E.get(target)
    with E.Writing(seq, save=save):
        n = 0
        for t in moved["tracks"]:
            if t["kind"] in ("event", "spawn"):
                continue
            yield from E.write_track(seq, t)
            n += 1
        a, b = moved["range"]
        seq.set_playback_start(int(round(a)))
        seq.set_playback_end(int(round(b)))
        if moved.get("markers"):
            E.set_markers(seq, moved["markers"])
    untouched = doc["unsupported"] + [{"binding": t["binding"], "kind": t["kind"]} for t in moved["tracks"]
                                      if t["kind"] in ("event",)]
    return {"sequence": target, "tracks": n, "notes": notes, "untouched": untouched, "changed": True}


def _copy_asset(src: str, dst: str, replace: bool):
    if E.find(dst) is not None:
        if not replace:
            raise OpError(f"{dst} exists", code="conflict", hint="pass replace=true, or another dst")
        if E.LSE.get_current_level_sequence() == E.find(dst):
            E.LSE.close_level_sequence()
        free(dst)
        yield
    if EAL.duplicate_asset(src.split(".")[0], dst.split(".")[0]) is None:
        raise OpError(f"could not duplicate {src} to {dst}", code="engine")
    yield


@op("seq.copy", mutates=True, idempotent=True, tags=["sequencer"])
def copy_sequence(*, src: str, dst: str, start: int = None, end: int = None, to: int = 0, replace: bool = False,
                  save: bool = True):
    """Copy a sequence (all of it: the asset duplicated), or a window [start, end) of it moved to begin at `to`:
    sections cut to the window (clips start that much later into themselves), curves holding their values at the
    edges, markers inside kept. For pulling a shot out of a long sequence. A multi-tick job.

    `replace` frees an existing `dst` first (no dialog), else an existing dst is an error.
    Returns: {"sequence", "range", "tracks", "notes", "changed"}.
    Example: film-ue op seq.copy src=/Game/Film/SEQ_All dst=/Game/Film/SEQ_sh020 start=120 end=240
    """
    if E.find(src) is None:
        raise OpError(f"no sequence {src}", code="not_found")
    yield from _copy_asset(src, dst, replace)
    if start is None and end is None:
        d = E.describe(dst, keys=False)
        if save:
            EAL.save_loaded_asset(E.get(dst), False)
        return {"sequence": dst, "range": d["range"], "tracks": len(d["tracks"]), "notes": [], "changed": True}
    doc = E.describe(dst)
    a = doc["range"][0] if start is None else start
    b = doc["range"][1] if end is None else end
    fps = Rate.parse(doc["fps"]).fps
    cut, notes = clip(doc, a, b, to=to, fps=fps)
    seq = E.get(dst)
    keep = index(cut)
    with E.Writing(seq, save=save):
        for t in doc["tracks"]:
            if track_id(t) not in keep and t["kind"] not in ("spawn", "event"):
                E.remove_track(seq, t["kind"], t["binding"], t["component"], t["name"])
        for t in cut["tracks"]:
            if t["kind"] in ("spawn", "event"):
                continue
            yield from E.write_track(seq, t)
        seq.set_playback_start(int(cut["range"][0]))
        seq.set_playback_end(int(cut["range"][1]))
        E.set_markers(seq, cut.get("markers") or [])
    return {"sequence": dst, "range": cut["range"], "tracks": len(cut["tracks"]), "notes": notes, "changed": True}


@op("seq.time", mutates=False, idempotent=True, tags=["sequencer"])
def time(*, value: str, fps=None, path: str = "") -> dict:
    """Convert a time between frames, seconds, timecode and ticks at a sequence's rate (or `fps`).

    Args: value: 48, "2s", "48f", "1m30s", "00:00:02:00". fps: a rate (default: the sequence's, else 24).
    Returns: {"frame", "seconds", "timecode", "ticks", "fps"}.
    Example: film-ue op seq.time value=00:01:00:00 fps=23.976
    """
    tick = 24000
    if fps is None and path:
        seq = E.get(path)
        r, tick = E.rate(seq), E.ticks(seq).numerator
    else:
        r = Rate.parse(fps or 24)
    f = r.parse_time(value)
    return {"frame": snap(f), "seconds": round(r.seconds(f), 6), "timecode": r.timecode(f),
            "ticks": r.to_ticks(f, tick), "fps": str(r)}
