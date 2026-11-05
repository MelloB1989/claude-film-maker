"""The engine side of the Sequencer core: read a level sequence into the canonical document (_model) and write
canonical tracks back, plus the resolver that answers what a spec needs from the level. Every engine API used here
is listed, with its source file:line on UE 5.8.4, in docs/unreal/sequencer.md (API_NOTES).

Units at this boundary: the scripting channels' add_key / get_time take DISPLAY frames (time_unit DISPLAY_RATE);
section pre/post roll, easing, audio and animation start offsets, sub-section offsets and material / collection
parameter keys are TICKS; tangents are stored per tick and given here per display frame.

Writes are batched: one op call writes every key of a track in-process, with the sequence closed in Sequencer (each
add_key broadcasts OnChannelChanged, which an open Sequencer answers), yielding every KEYS_PER_TICK keys so a big
bake never holds the game thread, and refreshes and saves once at the end.
"""
from __future__ import annotations

import math

import unreal

from ...errors import OpError, closest, not_found
from ..assets import EAL, load
from .._util import actor as _actor, find_actor
from ._curves import KEY_INTERPOLATION, interp_from_engine
from ._model import KINDS, PARTIAL, TRANSFORM_CHANNELS, channel, new_section, new_track, track_id, track_label
from ._time import Rate, snap

LSE = unreal.LevelSequenceEditorBlueprintLibrary
KEYS_PER_TICK = 2000
DISPLAY = None  # set lazily: unreal.MovieSceneTimeUnit.DISPLAY_RATE

TRACK_CLASS = {
    "transform": "MovieScene3DTransformTrack", "float": "MovieSceneFloatTrack", "bool": "MovieSceneBoolTrack",
    "byte": "MovieSceneByteTrack", "integer": "MovieSceneIntegerTrack", "string": "MovieSceneStringTrack",
    "visibility": "MovieSceneVisibilityTrack", "spawn": "MovieSceneSpawnTrack", "color": "MovieSceneColorTrack",
    "vector": "MovieSceneDoubleVectorTrack", "anim": "MovieSceneSkeletalAnimationTrack", "audio": "MovieSceneAudioTrack",
    "camera_cut": "MovieSceneCameraCutTrack", "fade": "MovieSceneFadeTrack",
    "level_visibility": "MovieSceneLevelVisibilityTrack", "material": "MovieSceneComponentMaterialTrack",
    "mpc": "MovieSceneMaterialParameterCollectionTrack", "event": "MovieSceneEventTrack",
    "shot": "MovieSceneCinematicShotTrack", "sub": "MovieSceneSubTrack",
}
KIND_OF = {v: k for k, v in TRACK_CLASS.items()}
KIND_OF.update({"MovieSceneDoubleTrack": "float", "MovieSceneEnumTrack": "byte", "MovieSceneFloatVectorTrack": "vector"})
PROPERTY_KINDS = {"float", "bool", "byte", "integer", "string", "color", "vector", "visibility"}
_ENGINE_CH = dict(zip(["Location.X", "Location.Y", "Location.Z", "Rotation.X", "Rotation.Y", "Rotation.Z", "Scale.X",
                       "Scale.Y", "Scale.Z"], TRANSFORM_CHANNELS))
_CANON_CH = {v: k for k, v in _ENGINE_CH.items()}


def _unit():
    return unreal.MovieSceneTimeUnit.DISPLAY_RATE


def _ename(e) -> str:
    return str(getattr(e, "name", e))


# --- the sequence -----------------------------------------------------------------------------------------------------

def find(path: str):
    """The LevelSequence at `path`, or None."""
    path = path.split(".")[0]
    if not EAL.does_asset_exist(path):
        return None
    return EAL.load_asset(path)


def get(path: str):
    s = find(path)
    if s is None:
        folder = path.rsplit("/", 1)[0]
        names = [p.split(".")[0] for p in (EAL.list_assets(folder, recursive=False) or [])] if folder else []
        raise not_found("sequence", path, names, hint="make it with seq.add or seq.apply")
    return s


def rate(seq) -> Rate:
    return Rate.parse(seq.get_display_rate())


def ticks(seq) -> Rate:
    return Rate.parse(seq.get_tick_resolution())


def tpf(seq) -> float:
    """Ticks per display frame."""
    return ticks(seq).fps / rate(seq).fps


def world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


class Writing:
    """`with Writing(seq):` close the sequence in Sequencer while writing (each key write broadcasts a channel change
    that an open Sequencer answers), reopen it after if it was open, save once."""

    def __init__(self, seq, save: bool = True):
        self.seq, self.save, self.was_open = seq, save, False

    def __enter__(self):
        cur = LSE.get_current_level_sequence()
        self.was_open = cur is not None and cur == self.seq
        if self.was_open:
            LSE.close_level_sequence()
        return self

    def __exit__(self, *exc):
        if self.was_open:
            LSE.open_level_sequence(self.seq)
        if self.save and not exc[0]:
            EAL.save_loaded_asset(self.seq, False)
        return False


# --- bindings ---------------------------------------------------------------------------------------------------------

def _parent(b):
    try:
        p = b.get_parent()
    except Exception:
        return None
    if p is None:
        return None
    try:
        if not p.is_valid():
            return None
    except Exception:
        pass
    return p if str(p.get_display_name()) else None


def bindings(seq) -> dict:
    """{(actor label, component name or ""): binding proxy} for every binding."""
    out = {}
    for b in seq.get_bindings():
        p = _parent(b)
        name = str(b.get_display_name())
        out[(str(p.get_display_name()), name) if p is not None else (name, "")] = b
    return out


def binding(seq, label: str, component: str = "", *, create: bool = False):
    """The binding of an actor (component "") or of one of its components, made (possessable) when `create`."""
    have = bindings(seq)
    if (label, component) in have:
        return have[(label, component)]
    if not create:
        raise not_found("binding", f"{label}.{component}" if component else label,
                        [f"{a}.{c}" if c else a for a, c in have], hint=f"seq.describe path={seq.get_path_name()}")
    if not component:
        return seq.add_possessable(actor(label))
    parent = binding(seq, label, "", create=True)
    comp = _component(_bound_actor(seq, parent, label), component)
    b = seq.add_possessable(comp)
    try:
        if _parent(b) is None:
            b.set_parent(parent)
    except Exception:
        pass
    return b


def actor(label: str):
    return _actor(label)  # a not_found OpError naming the nearest labels


def _bound_actor(seq, b, label: str):
    """The actor a binding drives: the level actor of that label, else (a spawnable) the spawned object while the
    sequence is open."""
    a = find_actor(label)
    if a is not None:
        return a
    if LSE.get_current_level_sequence() != seq:
        LSE.open_level_sequence(seq)
    objs = LSE.get_bound_objects(seq.get_binding_id(b))
    if not objs:
        raise OpError(f"binding {label!r} resolves to no object (a spawnable not spawned at the current time?)",
                      code="engine", hint="scrub into its spawn range (seq.scrub) and retry")
    return objs[0]


def _component(a, name: str):
    comps = a.get_components_by_class(unreal.ActorComponent)
    for c in comps:
        if c.get_name() == name:
            return c
    for c in comps:
        if c.get_class().get_name() == name:
            return c
    raise not_found("component", f"{a.get_actor_label()}.{name}", [c.get_name() for c in comps],
                    hint="level.describe lists an actor's components")


def is_bound(seq, b, label: str = "") -> bool | None:
    """Whether the binding finds its object (None: it could not be asked). With `label`, only when it finds exactly the
    level's actor of that label: a possessable keeps its actor by object name (PersistentLevel.CineCameraActor_3), not
    by label, so after its actor is deleted a new actor that takes the freed name (another script's camera) is found
    instead, and its tracks drive that one (day-1 r3: Reel_V02 drove perf.py's Test_agent-10_S13)."""
    try:
        objs = list(seq.locate_bound_objects(b, world()))
    except Exception:
        return None
    if not label:
        return bool(objs)
    a = find_actor(label)
    if a is None:  # no actor of that label (a binding named apart from its actor): only whether it finds anything
        return bool(objs)
    return len(objs) == 1 and objs[0] == a


def is_spawnable(b) -> bool:
    try:
        return bool(b.find_tracks_by_exact_type(unreal.MovieSceneSpawnTrack))
    except Exception:
        return False


def bind(seq, label: str, spawn: dict | None = None, replace: bool = False) -> tuple:
    """Converge a binding: (binding, changed). A possessable binds the level actor `label`; a spawnable is made from
    {"class": "CineCameraActor" | "/Script/CinematicCamera.CineCameraActor"} or {"template": <level actor label>}."""
    have = bindings(seq).get((label, ""))
    if have is not None and not replace and bool(spawn) == is_spawnable(have):
        if spawn or is_bound(seq, have, label) is not False:
            return have, False
        a = actor(label)  # bound to an actor that is gone, or to another one: point it at the level's actor of this
        # label (replace, not add: it drops whatever else the binding found), keeping its tracks
        if LSE.get_current_level_sequence() != seq:
            LSE.open_level_sequence(seq)
        unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem).replace_binding_with_actors([a], have)
        return have, True
    if have is not None:
        have.remove()
    if not spawn:
        return seq.add_possessable(actor(label)), True
    if "template" in spawn:
        b = seq.add_spawnable_from_instance(actor(spawn["template"]))
    else:
        b = seq.add_spawnable_from_class(_class(spawn["class"]))
    b.set_display_name(label)
    return b, True


def _class(name: str):
    if name.startswith("/Script/"):
        c = unreal.load_class(None, name)
    else:
        c = getattr(unreal, name, None)
    if c is None:
        raise OpError(f"no class {name!r}", code="not_found", hint="a class name like CineCameraActor, or "
                      "/Script/Module.Class")
    return c


# --- reading ----------------------------------------------------------------------------------------------------------

def _chname(ch) -> str:
    for get in (lambda: ch.channel_name, lambda: ch.get_editor_property("channel_name"), lambda: ch.get_name()):
        try:
            v = get()
            if v is not None and str(v):
                return str(v)
        except Exception:
            continue
    return ""


def _frame(ft) -> float:
    fn = ft.frame_number
    return snap((fn.value if hasattr(fn, "value") else int(fn)) + float(getattr(ft, "sub_frame", 0.0)))


def read_keys(ch, per_tick: float) -> list:
    out = []
    for k in ch.get_keys():
        f = _frame(k.get_time(_unit()))
        v = k.get_value()
        if hasattr(k, "get_interpolation_mode") and isinstance(v, (int, float)) and not isinstance(v, bool):
            how = interp_from_engine(_ename(k.get_interpolation_mode()), _ename(k.get_tangent_mode()))
            key = [f, float(v), how]
            if how in ("user", "break"):
                key.append({"arrive": float(k.get_arrive_tangent()) * per_tick,
                            "leave": float(k.get_leave_tangent()) * per_tick})
        else:
            if hasattr(v, "get_path_name"):
                v = v.get_path_name()
            key = [f, v, "constant"]
        out.append(key)
    return out


def _default(ch):
    try:
        if ch.has_default():
            v = ch.get_default()
            return v if isinstance(v, (bool, int, float, str)) else None
    except Exception:
        pass
    return None


def _range(s) -> list:
    a = s.get_start_frame() if s.has_start_frame() else None
    b = s.get_end_frame() if s.has_end_frame() else None
    return [a, b]


def _channels(kind: str, s, per_tick: float) -> dict:
    chans = list(s.get_all_channels())
    names = KINDS[kind][0]
    out = {}
    if kind == "transform":
        for ch in chans:
            n = _ENGINE_CH.get(_chname(ch))
            if n:
                out[n] = channel(read_keys(ch, per_tick), _default(ch))
        return out
    if kind in ("material", "mpc"):
        groups: dict = {}
        for ch in chans:
            n = _chname(ch)
            base, comp = (n[:-1], n[-1]) if n[-1:] in "RGBA" and any(_chname(c) == n[:-1] + "G" for c in chans) \
                else (n, "")
            groups.setdefault(base, {})[comp] = read_keys(ch, per_tick)
        for base, parts in groups.items():
            if "" in parts:
                out[base] = channel(parts[""])
            else:  # a colour parameter: four channels keyed together
                frames = sorted({k[0] for p in parts.values() for k in p})
                from ._curves import evaluate
                keys = [[f, [float(evaluate(parts.get(c, []), f, 1.0 if c == "A" else 0.0)) for c in "RGBA"],
                         next((k[2] for k in parts.get("R", []) if k[0] == f), "auto")] for f in frames]
                out[base] = channel(keys)
        return out
    if kind in ("anim", "audio"):
        for ch in chans:
            n = _chname(ch).lower()
            if n in names:
                out[n] = channel(read_keys(ch, per_tick), _default(ch))
        return out
    if kind in ("color", "vector"):
        for n, ch in zip(names, chans):
            out[n] = channel(read_keys(ch, per_tick), _default(ch))
        return out
    if names and chans:
        out[names[0]] = channel(read_keys(chans[0], per_tick), _default(chans[0]))
    return out


def _seconds(ticks_value, seq) -> float:
    return round(float(getattr(ticks_value, "value", ticks_value) or 0) / ticks(seq).fps, 6)


def _rate_of(tw) -> float:
    if isinstance(tw, (int, float)):
        return float(tw)
    for f in ("to_fixed_play_rate", "get_fixed_play_rate"):
        try:
            return float(getattr(tw, f)())
        except Exception:
            continue
    try:
        return float(unreal.MovieSceneTimeWarpExtensions.to_fixed_play_rate(tw))
    except Exception:
        return 1.0


def _params(kind: str, s, seq, names: dict) -> dict:
    pt = tpf(seq)
    if kind == "anim":
        p = s.get_editor_property("params")
        a = p.get_editor_property("animation")
        return {"anim": a.get_path_name().split(".")[0] if a else None,
                "offset": _seconds(p.get_editor_property("start_frame_offset"), seq),
                "rate": _rate_of(p.get_editor_property("play_rate")),
                "slot": str(p.get_editor_property("slot_name")), "reverse": bool(p.get_editor_property("reverse")),
                "blend_in": snap(s.get_ease_in_duration() / pt), "blend_out": snap(s.get_ease_out_duration() / pt)}
    if kind == "audio":
        snd = s.get_sound()
        return {"sound": snd.get_path_name().split(".")[0] if snd else None,
                "offset": _seconds(s.get_start_offset(), seq)}
    if kind == "camera_cut":
        g = s.get_camera_binding_id().get_editor_property("guid").export_text()
        return {"camera": names.get(g, f"?{g}")}
    if kind == "fade":
        c = s.get_editor_property("fade_color")
        return {"color": [c.r, c.g, c.b, c.a], "fade_audio": bool(s.get_editor_property("fade_audio"))}
    if kind == "level_visibility":
        return {"visible": "HIDDEN" not in _ename(s.get_visibility()).upper(),
                "levels": [str(n) for n in s.get_level_names()]}
    if kind in ("shot", "sub"):
        inner = s.get_sequence()
        p = s.get_editor_property("parameters")
        inner_tpf = tpf(inner) if inner else pt
        d = {"sequence": inner.get_path_name().split(".")[0] if inner else None,
             "offset": snap(getattr(p.get_editor_property("start_frame_offset"), "value", 0) / inner_tpf),
             "timescale": _rate_of(p.get_editor_property("time_scale")),
             "preroll": snap(s.get_pre_roll_frames() / pt), "postroll": snap(s.get_post_roll_frames() / pt)}
        if kind == "shot":
            d["name"] = str(s.get_shot_display_name())
        return d
    return {}


def _track_name(kind: str, t) -> tuple:
    """(name, params) identifying a track of `kind`."""
    if kind in PROPERTY_KINDS and kind != "visibility":
        return str(t.get_property_path()), ({"double": True} if t.get_class().get_name() == "MovieSceneDoubleTrack"
                                             else {})
    if kind in ("audio", "sub", "event"):
        return str(t.get_display_name()), {}
    if kind == "material":
        info = t.get_material_info()
        idx = int(info.get_editor_property("material_slot_index"))
        return f"slot:{idx}", {"slot": idx, "slot_name": str(info.get_editor_property("material_slot_name"))}
    if kind == "mpc":
        m = t.get_editor_property("mpc")
        return (m.get_path_name().split(".")[0] if m else ""), {}
    return "", {}


def read_track(seq, t, label: str, component: str, names: dict):
    """A track as a canonical track dict, or None for a class this core does not model (reported by describe)."""
    kind = KIND_OF.get(t.get_class().get_name())
    if kind is None:
        return None
    name, params = _track_name(kind, t)
    per_tick = tpf(seq)
    secs = []
    for s in t.get_sections():
        sec = new_section(_range(s), s.get_row_index(), _params(kind, s, seq, names),
                          {} if kind in ("camera_cut", "level_visibility", "shot", "sub", "event")
                          else _channels(kind, s, per_tick))
        if kind == "event":
            sec["params"]["keys"] = sum(len(c.get_keys()) for c in s.get_all_channels())
        secs.append(sec)
    return new_track(kind, label, component, name, params, secs)


def describe(path: str, keys: bool = True) -> dict:
    """The sequence at `path` as a canonical document (+ "unsupported": tracks of classes not modelled, which apply
    never touches). {"exists": False, "sequence": path} when there is none."""
    seq = find(path)
    if seq is None:
        return {"exists": False, "sequence": path}
    r, tk = rate(seq), ticks(seq)
    doc = {"exists": True, "sequence": path.split(".")[0], "fps": str(r), "tick_resolution": tk.numerator if
           tk.denominator == 1 else str(tk), "range": [seq.get_playback_start(), seq.get_playback_end()],
           "markers": [], "bindings": [], "tracks": [], "unsupported": []}
    try:
        for m in seq.get_marked_frames_from_sequence(_unit()):
            fn = m.get_editor_property("frame_number")
            doc["markers"].append({"frame": getattr(fn, "value", fn), "label": str(m.get_editor_property("label"))})
    except Exception as e:  # older engines: no display-rate variant
        doc["notes"] = [f"markers not read: {e}"]
    names = {}
    blist = bindings(seq)
    for (label, comp), b in blist.items():
        names[b.get_id().export_text()] = label if not comp else f"{label}.{comp}"
    for (label, comp), b in blist.items():
        if not comp:
            cls = b.get_possessed_object_class()
            spawn = is_spawnable(b)
            doc["bindings"].append({"name": label, "kind": "spawnable" if spawn else "possessable",
                                    "class": cls.get_name() if cls else None,
                                    "bound": None if spawn else is_bound(seq, b, label)})
        for t in b.get_tracks():
            tr = read_track(seq, t, label, comp, names)
            if tr is None:
                doc["unsupported"].append({"binding": label, "component": comp, "class": t.get_class().get_name()})
            elif not (tr["kind"] == "spawn" and not keys):
                doc["tracks"].append(tr)
    for t in seq.get_tracks():
        tr = read_track(seq, t, "", "", names)
        if tr is None:
            doc["unsupported"].append({"binding": "", "class": t.get_class().get_name()})
        else:
            doc["tracks"].append(tr)
    for t in doc["tracks"]:
        if t["kind"] == "spawn":
            t["sections"] = [dict(s, range=[None, None]) for s in t["sections"]]  # its extent follows the binding
    if not keys:
        for t in doc["tracks"]:
            for s in t["sections"]:
                s["channels"] = {n: {"keys": len(c["keys"]), "default": c["default"]} for n, c in s["channels"].items()}
    return doc


# --- writing ----------------------------------------------------------------------------------------------------------

def _add_keys(ch, keys: list, per_tick: float, kind: str):
    """Write canonical keys into a scripting channel (display frames), sorted. A generator: it yields every
    KEYS_PER_TICK keys."""
    numeric = kind not in ("bool", "visibility", "spawn", "byte", "integer", "string")
    unit = _unit()
    for i, k in enumerate(sorted(keys, key=lambda k: k[0])):
        f = float(k[0])
        whole = math.floor(f + 1e-9)
        sub = max(0.0, f - whole)
        at = unreal.FrameNumber(int(whole))
        if numeric:
            mode = getattr(unreal.MovieSceneKeyInterpolation, KEY_INTERPOLATION[k[2] if len(k) > 2 else "auto"])
            key = ch.add_key(at, float(k[1]), sub, unit, mode)
            if len(k) > 3 and k[3] and key is not None:
                t = k[3]
                if "arrive" in t:
                    key.set_arrive_tangent(float(t["arrive"]) / per_tick)
                if "leave" in t:
                    key.set_leave_tangent(float(t["leave"]) / per_tick)
                if "arrive_weight" in t or "leave_weight" in t:
                    key.set_tangent_weight_mode(unreal.RichCurveTangentWeightMode.RCTWM_WEIGHTED_BOTH)
                    if "arrive_weight" in t:
                        key.set_arrive_tangent_weight(float(t["arrive_weight"]))
                    if "leave_weight" in t:
                        key.set_leave_tangent_weight(float(t["leave_weight"]))
        else:
            v = bool(k[1]) if kind in ("bool", "visibility", "spawn") else (str(k[1]) if kind == "string" else int(k[1]))
            ch.add_key(at, v, sub, unit)
        if (i + 1) % KEYS_PER_TICK == 0:
            yield


def _fill(kind: str, sec, chans: dict, per_tick: float):
    """Write a section's canonical channels; a generator (see _add_keys)."""
    engine = list(sec.get_all_channels())
    if kind == "transform":
        for n, c in chans.items():
            ch = sec.get_channel(_CANON_CH[n])
            yield from _write_channel(ch, c, per_tick, kind)
        return
    if kind in ("anim", "audio"):
        by = {_chname(ch).lower(): ch for ch in engine}
        for n, c in chans.items():
            if n not in by:
                raise OpError(f"{kind} section has no channel {n!r}", code="engine", candidates=closest(n, by))
            yield from _write_channel(by[n], c, per_tick, kind)
        return
    names = KINDS[kind][0]
    for n, c in chans.items():
        if n not in names:
            raise OpError(f"a {kind} track has no channel {n!r}", code="bad_args", candidates=closest(n, names),
                          hint=f"its channels: {', '.join(names)}")
        idx = names.index(n)
        if idx >= len(engine):
            raise OpError(f"the {kind} section has {len(engine)} channel(s); {n!r} is not among them", code="engine")
        yield from _write_channel(engine[idx], c, per_tick, kind)


def _write_channel(ch, c: dict, per_tick: float, kind: str):
    if c.get("default") is not None:
        d = c["default"]
        ch.set_default(bool(d) if kind in ("bool", "visibility", "spawn") else d)
    yield from _add_keys(ch, c.get("keys") or [], per_tick, kind)


def _set_range(sec, rng):
    """Bound first, then set: SetStart/EndFrameBounded(true) RESETS that bound to the playback range
    (MovieSceneSectionExtensions.cpp:359-385), so called after set_range it collapsed every section and camera cut to
    the whole sequence (day 1 on the box). Unbounded ends are opened; given ends are set (which bounds them)."""
    a, b = rng
    if a is None:
        sec.set_start_frame_bounded(False)
    if b is None:
        sec.set_end_frame_bounded(False)
    if a is not None and b is not None:
        sec.set_range(int(a), int(b))
    else:
        if a is not None:
            sec.set_start_frame(int(a))
        if b is not None:
            sec.set_end_frame(int(b))


def _time_warp(rate_: float):
    try:
        return unreal.MovieSceneTimeWarpExtensions.make_time_warp(float(rate_))
    except Exception:
        if not hasattr(unreal, "MovieSceneTimeWarpVariant"):
            return float(rate_)
        v = unreal.MovieSceneTimeWarpVariant()
        v.set_fixed_play_rate(float(rate_))
        return v


def _section_params(kind: str, sec, p: dict, seq, label_binding):
    pt = tpf(seq)
    if kind == "anim":
        prm = sec.get_editor_property("params")
        prm.set_editor_property("animation", load(p["anim"]))
        prm.set_editor_property("start_frame_offset", unreal.FrameNumber(int(round(float(p.get("offset", 0.0))
                                                                                   * ticks(seq).fps))))
        prm.set_editor_property("play_rate", _time_warp(p.get("rate", 1.0)))
        prm.set_editor_property("slot_name", p.get("slot", "DefaultSlot"))
        prm.set_editor_property("reverse", bool(p.get("reverse", False)))
        sec.set_editor_property("params", prm)
        sec.set_ease_in_duration(int(round(float(p.get("blend_in", 0)) * pt)))
        sec.set_ease_out_duration(int(round(float(p.get("blend_out", 0)) * pt)))
    elif kind == "audio":
        sec.set_sound(load(p["sound"]))
        sec.set_start_offset(unreal.FrameNumber(int(round(float(p.get("offset", 0.0)) * ticks(seq).fps))))
    elif kind == "camera_cut":
        cam = p["camera"]
        sec.set_camera_binding_id(seq.get_binding_id(label_binding(cam)))
    elif kind == "fade":
        if "color" in p:
            c = list(p["color"]) + [1.0] * (4 - len(p["color"]))
            sec.set_editor_property("fade_color", unreal.LinearColor(r=c[0], g=c[1], b=c[2], a=c[3]))
        if "fade_audio" in p:
            sec.set_editor_property("fade_audio", bool(p["fade_audio"]))
    elif kind == "level_visibility":
        sec.set_visibility(unreal.LevelVisibility.VISIBLE if p.get("visible", True) else unreal.LevelVisibility.HIDDEN)
        sec.set_level_names([str(n) for n in p.get("levels") or []])
    elif kind in ("shot", "sub"):
        inner = load(p["sequence"])
        sec.set_sequence(inner)
        if kind == "shot" and p.get("name"):
            sec.set_shot_display_name(str(p["name"]))
        prm = sec.get_editor_property("parameters")
        prm.set_editor_property("start_frame_offset", unreal.FrameNumber(int(round(float(p.get("offset", 0))
                                                                                   * tpf(inner)))))
        prm.set_editor_property("time_scale", _time_warp(p.get("timescale", 1.0)))
        sec.set_editor_property("parameters", prm)
        sec.set_pre_roll_frames(int(round(float(p.get("preroll", 0)) * pt)))
        sec.set_post_roll_frames(int(round(float(p.get("postroll", 0)) * pt)))


def _find_tracks(owner, kind: str, name: str) -> list:
    cls = getattr(unreal, TRACK_CLASS[kind])
    classes = [cls] + ([unreal.MovieSceneDoubleTrack] if kind == "float" else []) + (
        [unreal.MovieSceneFloatVectorTrack] if kind == "vector" else [])
    out = []
    for c in classes:
        for t in owner.find_tracks_by_exact_type(c):
            if _track_name(kind, t)[0] == name or kind in ("transform", "visibility", "spawn", "anim", "camera_cut",
                                                            "fade", "level_visibility", "shot"):
                out.append(t)
    return out


def write_track(seq, t: dict):
    """Make the engine's track what canonical `t` says: the old track of that identity is removed and a new one
    written (PARTIAL kinds keep their other parameters). A generator (multi-tick for big writes); returns a summary."""
    kind = t["kind"]
    if kind not in TRACK_CLASS:
        raise OpError(f"unknown track kind {kind!r}", code="bad_args", candidates=closest(kind, TRACK_CLASS))
    if kind == "event":
        raise OpError("writing event tracks is not supported yet (their keys need a director blueprint endpoint)",
                      code="unsupported", hint="key events in the editor, or use SequencerTools.create_quick_binding "
                                               "+ create_event from exec'd code; describe reads them")
    label, comp, name = t.get("binding") or "", t.get("component") or "", t.get("name") or ""
    per_tick = tpf(seq)
    owner = seq if not label else binding(seq, label, comp, create=True)
    cache: dict = {}

    def label_binding(cam):  # a camera cut's camera: bound when it is not yet
        if cam not in cache:
            cache[cam] = binding(seq, cam, "", create=True)
        return cache[cam]

    keys = 0
    if kind == "spawn":
        tracks = owner.find_tracks_by_exact_type(unreal.MovieSceneSpawnTrack)
        if not tracks:
            raise OpError(f"{label!r} is not a spawnable (no spawn track)", code="bad_args",
                          hint="declare it with spawn: {class: ...} in the spec, or seq.bind spawn=...")
        sec = tracks[0].get_sections()[0]
        for c in (t["sections"][0]["channels"].values() if t["sections"] else []):
            ch = sec.get_all_channels()[0]
            for k in list(ch.get_keys()):
                ch.remove_key(k)
            keys += len(c.get("keys") or [])
            yield from _write_channel(ch, c, per_tick, kind)
        return {"track": track_label(t), "keys": keys, "sections": 1}
    if kind in PARTIAL:
        yield from _write_partial(seq, owner, t, per_tick)
        return {"track": track_label(t), "keys": sum(len(c.get("keys") or []) for s in t["sections"]
                                                     for c in s["channels"].values()), "sections": 1}
    for old in _find_tracks(owner, kind, name):
        owner.remove_track(old)
    cls = TRACK_CLASS[kind]
    if kind == "float" and t.get("params", {}).get("double"):
        cls = "MovieSceneDoubleTrack"
    track = owner.add_track(getattr(unreal, cls))
    if kind in PROPERTY_KINDS:
        if kind == "visibility":
            track.set_property_name_and_path("bHiddenInGame", "bHiddenInGame")
        else:
            track.set_property_name_and_path(name.split(".")[-1], name)
    if kind in ("audio", "sub") and name:
        track.set_display_name(name)
    if kind == "vector":
        n = max((len(s["channels"]) for s in t["sections"]), default=3)
        track.set_num_channels_used(max(2, min(4, n)))
    for s in t["sections"]:
        sec = track.add_section()
        _set_range(sec, s["range"])
        sec.set_row_index(int(s.get("row", 0)))
        _section_params(kind, sec, s.get("params") or {}, seq, label_binding)
        keys += sum(len(c.get("keys") or []) for c in s["channels"].values())
        yield from _fill(kind, sec, s["channels"], per_tick)
    return {"track": track_label(t), "keys": keys, "sections": len(t["sections"])}


def _param_info(name: str):
    info = unreal.MaterialParameterInfo()
    info.set_editor_property("name", name)
    info.set_editor_property("association", unreal.MaterialParameterAssociation.GLOBAL_PARAMETER)
    info.set_editor_property("index", -1)
    return info


def _write_partial(seq, owner, t: dict, per_tick: float):
    """Material slot or parameter collection: one track per slot/collection, one section, a channel per parameter;
    only the parameters `t` names are replaced. Their key API takes ticks (MovieSceneComponentMaterialParameter-
    Section / MovieSceneParameterSection)."""
    kind = t["kind"]
    if kind == "material":
        slot = int((t.get("params") or {}).get("slot", int(t["name"].split(":")[1]) if ":" in t["name"] else 0))
        track = next((x for x in owner.find_tracks_by_exact_type(unreal.MovieSceneComponentMaterialTrack)
                      if int(x.get_material_info().get_editor_property("material_slot_index")) == slot), None)
        if track is None:
            track = owner.add_track(unreal.MovieSceneComponentMaterialTrack)
        info = track.get_material_info()
        info.set_editor_property("material_type", unreal.ComponentMaterialType.INDEXED_MATERIAL)  # EMPTY plays nothing
        info.set_editor_property("material_slot_index", slot)
        if (t.get("params") or {}).get("slot_name"):
            info.set_editor_property("material_slot_name", t["params"]["slot_name"])
        track.set_material_info(info)
    else:
        mpc = load(t["name"])
        track = next((x for x in seq.find_tracks_by_exact_type(unreal.MovieSceneMaterialParameterCollectionTrack)
                      if x.get_editor_property("mpc") == mpc), None)
        if track is None:
            track = seq.add_track(unreal.MovieSceneMaterialParameterCollectionTrack)
            track.set_editor_property("mpc", mpc)
    secs = track.get_sections()
    sec = secs[0] if secs else track.add_section()
    sec.set_start_frame_bounded(False)
    sec.set_end_frame_bounded(False)
    n = 0
    for s in t["sections"]:
        for param, c in s["channels"].items():
            ks = sorted(c.get("keys") or [], key=lambda k: k[0])
            vector = bool(ks) and isinstance(ks[0][1], (list, tuple))
            key = _param_info(param) if kind == "material" else param
            for remove in ("remove_scalar_parameter", "remove_color_parameter"):
                try:
                    getattr(sec, remove)(key)
                except Exception:
                    pass
            for k in ks:
                at = unreal.FrameNumber(int(round(float(k[0]) * per_tick)))
                mode = getattr(unreal.MovieSceneKeyInterpolation, KEY_INTERPOLATION[k[2] if len(k) > 2 else "auto"])
                if kind == "material" and vector:
                    rgba = list(k[1]) + [1.0] * (4 - len(k[1]))
                    sec.add_color_parameter_key(key, at, unreal.LinearColor(r=rgba[0], g=rgba[1], b=rgba[2],
                                                                            a=rgba[3]), "", "",
                                                default_interpolation=mode)
                elif kind == "material":
                    sec.add_scalar_parameter_key(key, at, float(k[1]), "", "", default_interpolation=mode)
                elif vector:
                    rgba = list(k[1]) + [1.0] * (4 - len(k[1]))
                    sec.add_color_parameter_key(key, at, unreal.LinearColor(r=rgba[0], g=rgba[1], b=rgba[2],
                                                                            a=rgba[3]), default_interpolation=mode)
                else:
                    sec.add_scalar_parameter_key(key, at, float(k[1]), default_interpolation=mode)
                n += 1
                if n % KEYS_PER_TICK == 0:
                    yield


def remove_track(seq, kind: str, label: str = "", component: str = "", name: str = "") -> int:
    if kind not in TRACK_CLASS:
        raise OpError(f"unknown track kind {kind!r}", code="bad_args", candidates=closest(kind, TRACK_CLASS))
    if label:
        have = bindings(seq)
        if (label, component) not in have:
            return 0
        owner = have[(label, component)]
    else:
        owner = seq
    n = 0
    for t in _find_tracks(owner, kind, name):
        owner.remove_track(t)
        n += 1
    return n


def set_markers(seq, markers: list) -> None:
    seq.delete_marked_frames()
    for m in sorted(markers, key=lambda m: m["frame"]):
        mf = unreal.MovieSceneMarkedFrame()
        mf.set_editor_property("frame_number", unreal.FrameNumber(int(round(m["frame"]))))
        mf.set_editor_property("label", str(m.get("label", "")))
        seq.add_marked_frame_to_sequence(mf, _unit())


# --- the resolver: what a spec needs from the level -------------------------------------------------------------------

def anim_length(a):
    """An anim asset's play length in seconds, or None. get_play_length() first: the 'sequence_length' property is
    deprecated since 5.0 (AnimSequenceBase.h:47), kept only as the fallback."""
    for get in (lambda: a.get_play_length(), lambda: a.get_editor_property("sequence_length")):
        try:
            v = float(get())
            if v > 0:
                return v
        except Exception:
            continue
    return None


class EngineResolver:
    """compile_spec's questions answered from the open level. Spawnable labels (not in the level) get guesses."""

    def __init__(self, spawnables=()):
        self.spawnables = set(spawnables)
        self.notes: list = []

    def _actor(self, label):
        if label in self.spawnables:
            return None
        return actor(label)

    def actor_location(self, label):
        a = self._actor(label)
        if a is None:
            self.notes.append(f"look_at {label!r}: a spawnable has no level location")
            return None
        p = a.get_actor_location()
        return [p.x, p.y, p.z]

    def actor_transform(self, label):
        a = self._actor(label)
        if a is None:
            return None
        p, r, s = a.get_actor_location(), a.get_actor_rotation(), a.get_actor_scale3d()
        return {"location": [p.x, p.y, p.z], "rotation": {"roll": r.roll, "pitch": r.pitch, "yaw": r.yaw},
                "scale": [s.x, s.y, s.z]}

    def anim_length(self, path):
        return anim_length(load(path))

    def sound_duration(self, path):
        return float(load(path).get_editor_property("duration"))

    def prop_info(self, label, component, prop, sample=None):
        a = self._actor(label)
        if a is None:
            from ._spec import _guess_kind
            return {"component": component, "kind": _guess_kind(prop, sample), "srgb": None}
        owner, comp = (_component(a, component), None) if component else (a, "")
        if component:
            comp = owner.get_name()
        try:
            v = _value(owner, prop)
        except Exception:
            if component:
                raise OpError(f"{label}.{component} has no property {prop!r}", code="not_found",
                              hint="property names are the C++ ones, e.g. Intensity, FocusSettings.ManualFocusDistance")
            root = a.get_editor_property("root_component")
            try:
                v = _value(root, prop)
            except Exception:
                raise OpError(f"{label!r} and its root component have no property {prop!r}", code="not_found",
                              hint="name the component: 'LightComponent0/Intensity' (level.describe lists them)") from None
            comp = root.get_name()
        return {"component": comp, "kind": _kind_of_value(v, sample), "srgb": isinstance(v, unreal.Color)}

    def material_slot(self, label, component, slot):
        a = self._actor(label)
        if a is None:
            return component, (slot if isinstance(slot, int) else 0), (slot if isinstance(slot, str) else "")
        if component:
            mesh = _component(a, component)
        else:
            meshes = a.get_components_by_class(unreal.MeshComponent)
            if not meshes:
                raise OpError(f"{label!r} has no mesh component", code="not_found", hint="name the component")
            mesh = meshes[0]
        names = [str(n) for n in mesh.get_material_slot_names()]
        if isinstance(slot, str):
            if slot not in names:
                raise not_found("material slot", slot, names, hint=f"slots of {label}.{mesh.get_name()}")
            idx = names.index(slot)
        else:
            idx = int(slot)
        return mesh.get_name(), idx, names[idx] if idx < len(names) else ""

    def skeletal_component(self, label, component):
        a = self._actor(label)
        if a is None:
            return component or "SkeletalMeshComponent0"
        comps = a.get_components_by_class(unreal.SkeletalMeshComponent)
        if component:
            if not any(c.get_name() == component for c in comps):
                raise not_found("skeletal mesh component", f"{label}.{component}", [c.get_name() for c in comps])
            return component
        if not comps:
            raise OpError(f"{label!r} has no skeletal mesh component", code="not_found")
        return comps[0].get_name()


def _snake(name: str) -> str:
    import re
    if name[:1] == "b" and name[1:2].isupper():
        name = name[1:]
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def _value(obj, prop: str):
    v = obj
    for part in prop.split("."):
        v = v.get_editor_property(_snake(part))
    return v


def _kind_of_value(v, sample) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (unreal.Color, unreal.LinearColor)):
        return "color"
    if isinstance(v, unreal.Vector):
        return "vector"
    if isinstance(v, float):
        return "float"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, str):
        return "string"
    if hasattr(unreal, "EnumBase") and isinstance(v, unreal.EnumBase):
        return "byte"
    from ._spec import _guess_kind
    return _guess_kind("", sample)


# --- evaluation (numbers for checks, no ticking) ----------------------------------------------------------------------

def eval_channels(seq, t: dict, frames: list) -> dict:
    """What the engine's curves give at `frames` for a canonical track's channels: {channel: [value, ...]}, through
    the scripting channel's evaluate_keys over the span (exact engine evaluation, no tick, sequence closed is fine)."""
    label, comp = t.get("binding") or "", t.get("component") or ""
    owner = seq if not label else binding(seq, label, comp)
    tracks = _find_tracks(owner, t["kind"], t.get("name") or "")
    if not tracks:
        raise not_found("track", track_label(t), [], hint="seq.describe lists them")
    secs = tracks[0].get_sections()
    lo, hi = int(math.floor(min(frames))), int(math.ceil(max(frames))) + 1
    disp = seq.get_display_rate()
    out = {}
    for s in secs:
        engine = list(s.get_all_channels())
        names = ([_ENGINE_CH.get(_chname(c), _chname(c)) for c in engine] if t["kind"] == "transform"
                 else KINDS[t["kind"]][0][:len(engine)] or [_chname(c) for c in engine])
        for n, ch in zip(names, engine):
            if not hasattr(ch, "evaluate_keys"):
                continue
            rng = seq.make_range(lo, hi - lo)
            vals = list(ch.evaluate_keys(rng, disp))
            out[n] = [vals[int(round(f)) - lo] if 0 <= int(round(f)) - lo < len(vals) else None for f in frames]
        break  # the first section: property tracks have one
    return out


def world_transforms(seq, label: str, frames: list) -> list:
    """An actor's world transform at each frame as Sequencer evaluates it, without ticking: [[x, y, z, pitch, yaw,
    roll], ...]. ControlRigSequencerLibrary (Python's name for UControlRigSequencerEditorLibrary: its ScriptName)
    evaluates the OPEN sequence (it ignores its sequence argument),
    so the sequence is opened first."""
    if LSE.get_current_level_sequence() != seq:
        LSE.open_level_sequence(seq)
    b = binding(seq, label)
    a = _bound_actor(seq, b, label)
    xs = unreal.ControlRigSequencerLibrary.get_actor_world_transforms(
        seq, a, [unreal.FrameNumber(int(f)) for f in frames], _unit())
    out = []
    for x in xs:
        p, r = x.translation, x.rotation.rotator()
        out.append([p.x, p.y, p.z, r.pitch, r.yaw, r.roll])
    return out


def track_by_id(doc: dict, ident: tuple):
    for t in doc.get("tracks") or []:
        if track_id(t) == ident:
            return t
    return None
