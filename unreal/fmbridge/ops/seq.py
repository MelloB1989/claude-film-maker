"""The older single-purpose sequence ops (seq.shot, seq.key_*, seq.anim, seq.audio, seq.camera_cuts, seq.new,
seq.cuts, seq.set_anim, seq.rebind, seq.tracks) and the viewport ones (seq.scrub, seq.close, seq.sample, seq.still,
seq.stills). Same signatures and results as before; every write is now a canonical track handed to the Sequencer
core (ops/seqcore: _engine.write_track, batched, Sequencer closed while writing), and seq.cuts / seq.set_anim read
through its describe, so there is one engine path. New work: the declarative seq.apply (docs/unreal/sequencer.md).

Traps handled (by seqcore now): frames are display-rate frames; easing, start offsets and parameter keys are in
ticks. Components are bound under their actor's binding and found by the pair (actor, component), never by the
component's name alone (both presenters have a "Body"). Each key op replaces only its own track (that property,
that parameter) on that binding, so re-running it is safe and tracks coexist."""
from __future__ import annotations

import math

import unreal

from . import op
from ..errors import not_found
from ._util import actor, find_actor
from .assets import EAL, free, load
from .level import look_rot
from .seqcore import _engine as E
from .seqcore._model import TRANSFORM_CHANNELS

LSE = unreal.LevelSequenceEditorBlueprintLibrary


# --- the layer over seqcore: every write goes through seqcore._engine.write_track (one engine path) ---------------

def _section(rng=(None, None), row: int = 0, params: dict | None = None, channels: dict | None = None) -> dict:
    return {"range": [rng[0], rng[1]], "row": int(row), "params": dict(params or {}), "channels": dict(channels or {})}


def _track(kind: str, binding: str = "", component: str = "", name: str = "", params: dict | None = None,
           sections: list | None = None) -> dict:
    return {"kind": kind, "binding": binding, "component": component, "name": name, "params": dict(params or {}),
            "sections": list(sections or [])}


def _write(seq, tracks: list) -> None:
    """Write canonical tracks through seqcore (batched, Sequencer closed while writing), save, refresh. The older
    ops are plain functions, so seqcore's multi-tick writer is run to its end here (each yields per 2000 keys)."""
    with E.Writing(seq, save=True):
        for t in tracks:
            g = E.write_track(seq, t)
            try:
                while True:
                    next(g)
            except StopIteration:
                pass
    if LSE.get_current_level_sequence():
        LSE.refresh_current_level_sequence()


def _interp_name(name: str) -> str:
    """This module's interpolation names ("step" too) as seqcore's."""
    n = str(name).lower()
    if n not in INTERP:
        raise ValueError(f"unknown interpolation {name!r}: one of {', '.join(INTERP)}")
    return "constant" if n == "step" else n


def _label_of(seq, component: str) -> str:
    """The actor whose binding has a child binding `component` (the only one: else name the label)."""
    found = [a for (a, c) in E.bindings(seq) if c == component]
    if len(found) != 1:
        raise not_found("component binding", component, [f"{a}.{c}" for a, c in E.bindings(seq) if c],
                        hint="pass label= to say whose")
    return found[0]


@op("seq.shot", mutates=True, idempotent=False, tags=["sequencer", "legacy"])
def shot(path: str, actor_label: str, anims: dict, camera: str, audio: str = "", seconds: float = 0.0, fps: int = 24,
         audio_start: int = 0, tail: int = 6) -> dict:
    """A shot: `anims` maps component names to animations ({"Body": idle, "Face": talk}); `audio` a SoundWave; the
    camera cut on `camera`. Length: `seconds`, else the audio's, else the longest animation's.
    Example: film-ue op seq.shot path=/Game/S/SEQ_A actor_label=Host 'anims={"Body": "/Game/A/Idle"}' camera=CamA seconds=5
    """
    if EAL.does_asset_exist(path):
        if LSE.get_current_level_sequence():
            LSE.close_level_sequence()
        free(path)  # create_asset over an existing asset asks in a modal dialog
    wave = load(audio) if audio else None
    secs = seconds or (wave.get_editor_property("duration") if wave else 0) or max(
        E.anim_length(load(a)) or 0 for a in anims.values())
    end = int(math.ceil(secs * fps)) + tail
    from .seqcore import seq_core
    seq_core.add(path=path, fps=fps, start=0, end=end, save=False)
    seq = E.get(path)
    E.binding(seq, actor_label, create=True)
    tracks = [_track("anim", actor_label, comp, sections=[_section((0, end), params={"anim": a})])
              for comp, a in anims.items()]
    if wave:
        tracks.append(_track("audio", name="Audio", sections=[_section((audio_start, end), params={"sound": audio})]))
    tracks.append(_track("camera_cut", sections=[_section((0, end), params={"camera": camera})]))
    _write(seq, tracks)
    return {"sequence": path, "frames": end, "fps": fps}


@op("seq.scrub", mutates=False, idempotent=True, tags=["sequencer", "legacy"])
def scrub(path: str, frame: int) -> int:
    """Open a sequence in Sequencer, locked to its camera, at a frame (for checking a pose in the viewport).
    Example: film-ue op seq.scrub path=/Game/S/SEQ_A frame=48
    """
    LSE.open_level_sequence(load(path))
    LSE.set_lock_camera_cut_to_viewport(True)
    LSE.set_current_time(int(frame))
    return frame


@op("seq.close", mutates=False, idempotent=True, tags=["sequencer", "legacy"])
def close() -> bool:
    """Close the open sequence.
    Example: film-ue op seq.close
    """
    LSE.close_level_sequence()
    return True



def component_of(actor_label: str, component: str):
    return next(c for c in actor(actor_label).get_components_by_class(unreal.SceneComponent) if c.get_name() == component)


@op("seq.set_anim", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def set_anim(path: str, component: str, anim: str, label: str = "", only: str = "") -> str:
    """Swap the animation on a component's track in a sequence: every section of it, or only those playing `only`.
    `label` picks the actor when several have a component of that name (both presenters have "Body").
    Example: film-ue op seq.set_anim path=/Game/S/SEQ_A component=Body anim=/Game/A/Walk label=Host
    """
    seq = load(path)
    have = E.describe(path)
    comp_label = label or _label_of(seq, component)
    t = E.track_by_id(have, ("anim", comp_label, component, ""))
    if t is None:
        raise not_found("animation track", f"{comp_label}.{component}",
                        [f"{x['binding']}.{x['component']}" for x in have["tracks"] if x["kind"] == "anim"],
                        hint="seq.tracks lists them")
    for s in t["sections"]:
        cur = s["params"].get("anim")
        if only and not (cur and cur in (only, anim)):
            continue
        s["params"]["anim"] = anim
    _write(seq, [t])
    return anim


def _xform(comp, bone: str) -> list:
    t = comp.get_socket_transform(bone, unreal.RelativeTransformSpace.RTS_WORLD)
    p, q = t.translation, t.rotation
    return [p.x, p.y, p.z] + [c for v in (q.get_axis_x(), q.get_axis_y(), q.get_axis_z()) for c in (v.x, v.y, v.z)]


def aim_point(target, offset=None) -> list:
    """Where a target is now, in world cm: a point [x, y, z]; an actor's label (its location, plus `offset` in the
    actor's own frame); "Label:Component:bone" (a bone or socket, e.g. "Presenter:Face:FACIAL_L_Eye"); or a
    camera's label (its camera component, i.e. the lens)."""
    if isinstance(target, (list, tuple)):
        return [float(v) for v in target]
    parts = str(target).split(":")
    if len(parts) == 3:
        p = component_of(parts[0], parts[1]).get_socket_location(parts[2])
    else:
        a = actor(parts[0])
        cam = a.get_components_by_class(unreal.CameraComponent)
        if cam and not offset:
            p = cam[0].get_world_location()
        else:
            p = a.get_actor_transform().transform_location(unreal.Vector(*[float(v) for v in (offset or (0, 0, 0))]))
    return [p.x, p.y, p.z]


@op("seq.sample", mutates=False, idempotent=True, tags=["sequencer", "legacy"])
def sample(path: str, actor_label: str, component: str, bones: list, frames: list | None = None, every: int = 1,
           ticks: int = 2, camera: str = "", target=None, target_offset=None):
    """Play a sequence frame by frame across editor ticks (so animation and rigs settle) and record bones' world
    transforms, each [x, y, z, axis_x(3), axis_y(3), axis_z(3)], `camera`'s location, and `target`'s (see
    seq.aim_point: a point, an actor, "Label:Component:bone"). A multi-tick job.
    Example: film-ue op seq.sample path=/Game/S/SEQ_A actor_label=Host component=Face 'bones=["FACIAL_L_Eye"]' 'frames=[0,24]'
    """
    LSE.open_level_sequence(load(path))
    seq = LSE.get_current_level_sequence()
    if frames is None:
        frames = list(range(seq.get_playback_start(), seq.get_playback_end(), every))
    comp = component_of(actor_label, component)
    out = {"frames": frames, "bones": {b: [] for b in bones}, "camera": [], "target": []}
    LSE.set_current_time(int(frames[0]) + 1)  # move off the first frame, so evaluating it is never skipped
    yield
    for f in frames:
        LSE.set_current_time(int(f))
        for _ in range(ticks):
            yield
        comp = component_of(actor_label, component)  # afresh: a MetaHuman's components go stale
        for b in bones:
            out["bones"][b].append(_xform(comp, b))
        if camera:
            p = component_of(camera, "CameraComponent").get_world_location()
            out["camera"].append([p.x, p.y, p.z])
        if target is not None:
            out["target"].append(aim_point(target, target_offset))
    return out


@op("seq.still", mutates=False, idempotent=True, tags=["sequencer", "legacy"])
def seq_still(path: str, frame: int, camera: str, out: str, width: int = 1920, height: int = 1080, settle: int = 30):
    """A still of a sequence at a frame through `camera`, or, with camera "", through the camera the edit (the camera
    cut track) shows at that frame: scrub there, let it settle `settle` ticks (temporal anti-aliasing, Lumen),
    capture. A multi-tick job.
    Example: film-ue op seq.still path=/Game/S/SEQ_A frame=48 camera=CamA out=/tmp/f48.png
    """
    from .look import still
    camera = camera or cut_camera(path, frame)
    LSE.open_level_sequence(load(path))
    LSE.set_lock_camera_cut_to_viewport(True)
    LSE.set_current_time(int(frame) + 1)
    yield
    LSE.set_current_time(int(frame))
    for _ in range(settle):
        yield
    return (yield from still(camera, out, width, height))



@op("seq.key_transform", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def key_transform(path: str, label: str, keys: list, interp: str = "auto") -> int:
    """Animate an actor in a sequence: keys are [frame, [x, y, z], {"pitch", "yaw", "roll"} | [x, y, z] to look at]
    with an optional 4th element, the interpolation leaving that key: "auto" (smooth, eases at held ends), "linear"
    or "constant" (hold until the next key, a jump cut). `interp` is the default. Replaces the actor's transform
    track (and only that), keeping the actor's scale; yaw is keyed as given, so unwrap it yourself across +-180.
    Example: film-ue op seq.key_transform path=/Game/S/SEQ_A label=CamA 'keys=[[0,[0,-300,160],{"yaw":90}],[48,[100,-300,160],[0,0,150]]]'
    """
    seq = load(path)
    sc = actor(label).get_actor_scale3d()  # kept as the actor has it
    ch = {n: [] for n in TRANSFORM_CHANNELS}
    for frame, loc, aim, *how in keys:
        mode = _interp_name(how[0] if how else interp)
        r = look_rot(loc, aim) if isinstance(aim, (list, tuple)) else unreal.Rotator(
            roll=aim.get("roll", 0.0), pitch=aim.get("pitch", 0.0), yaw=aim.get("yaw", 0.0))
        for n, v in zip(TRANSFORM_CHANNELS, list(loc) + [r.roll, r.pitch, r.yaw] + [sc.x, sc.y, sc.z]):
            ch[n].append([int(frame), float(v), mode])
    _write(seq, [_track("transform", label, sections=[_section(
        (seq.get_playback_start(), seq.get_playback_end()), channels={n: {"keys": k, "default": None}
                                                                      for n, k in ch.items()})])])
    return len(keys)


@op("seq.camera_cuts", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def camera_cuts(path: str, cuts: list) -> list:
    """The edit: cuts are [camera label, first frame] in order; each runs to the next (the last to the end).
    Example: film-ue op seq.camera_cuts path=/Game/S/SEQ_A 'cuts=[["CamA",0],["CamB",72]]'
    """
    seq = load(path)
    end = seq.get_playback_end()
    out, secs = [], []
    for k, (cam, start) in enumerate(cuts):
        stop = cuts[k + 1][1] if k + 1 < len(cuts) else end
        secs.append(_section((int(start), int(stop)), params={"camera": cam}))
        out.append([cam, int(start), int(stop)])
    _write(seq, [_track("camera_cut", sections=secs)])
    return out


@op("seq.stills", mutates=False, idempotent=True, tags=["sequencer", "legacy"])
def seq_stills(path: str, frames: list, camera: str = "", out_dir: str = "", width: int = 960, height: int = 540,
               settle: int = 20):
    """Stills of a sequence at many frames ({out_dir}/{frame:04d}.png): a contact sheet's worth in one call. Through
    one `camera`, or with camera "" each frame through its own shot's camera (the camera cut track): a previs of the
    whole cut. A multi-tick job; returns [[frame, camera, path]].
    Example: film-ue op seq.stills path=/Game/S/SEQ_A 'frames=[0,48,96]' out_dir=/tmp/sheet
    """
    import os
    out = []
    for f in frames:
        p = os.path.join(out_dir, f"{int(f):04d}.png")
        cam = camera or cut_camera(path, f)
        yield from seq_still(path, f, cam, p, width, height, settle)
        out.append([int(f), cam, p])
    return out


# --- the reel's ops: a sequence of its own, keys on any property, sections, audio, the edit -------------------------

INTERP = {"auto": "AUTO", "linear": "LINEAR", "constant": "CONSTANT", "step": "CONSTANT", "user": "USER", "break": "BREAK"}



def _snake(name: str) -> str:
    """A C++ property name as Python's editor-property name: ManualFocusDistance -> manual_focus_distance."""
    import re
    if name[:1] == "b" and name[1:2].isupper():
        name = name[1:]
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def _camel(name: str) -> str:
    """The C++ name Sequencer binds to, from either spelling: manual_focus_distance -> ManualFocusDistance."""
    return "".join(w[:1].upper() + w[1:] for w in name.split("_")) if ("_" in name or name.islower()) else name


def _path(prop: str) -> tuple:
    """A property path in Sequencer's spelling, and its leaf: ("FocusSettings.ManualFocusDistance", "ManualFocusDistance")."""
    parts = [_camel(p) for p in prop.split(".")]
    return ".".join(parts), parts[-1]


def _value(obj, prop: str):
    """A property's current value by path, through structs; raises if `obj` has no such property."""
    v = obj
    for part in prop.split("."):
        v = v.get_editor_property(_snake(part))
    return v


def _component(label: str, component: str):
    """An actor's component by name or class name, fetched afresh (a MetaHuman's go stale)."""
    for c in actor(label).get_components_by_class(unreal.ActorComponent):
        if c.get_name() == component or c.get_class().get_name() == component:
            return c
    raise ValueError(f"{label!r} has no component {component!r}")


def _owner(label: str, component: str, prop: str):
    """Who carries `prop`: the named component, else the actor if it has the property, else its root component
    (a light actor's Intensity lives on its root LightComponent)."""
    if component:
        return component
    try:
        _value(actor(label), prop)
        return ""
    except Exception:
        return actor(label).get_editor_property("root_component").get_name()


def _comp_binding(seq, label: str, component: str = "", create: bool = True):
    """The binding of an actor (component "") or of one of its components, under the actor's binding; made when
    missing (`create`)."""
    return E.binding(seq, label, component, create=create)



def _ticks(seq, frames: float) -> int:
    """Display frames to tick resolution (section easing and offsets are in ticks)."""
    d, t = seq.get_display_rate(), seq.get_tick_resolution()
    return int(round(frames * (t.numerator / t.denominator) / (d.numerator / d.denominator)))


def _fps(seq) -> float:
    r = seq.get_display_rate()
    return r.numerator / r.denominator



@op("seq.new", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def new(path: str, start: int = 0, end: int = 120, fps: int = 24, replace: bool = False) -> dict:
    """An empty level sequence for building into (no actor, no camera): playback [start, end) at `fps`. If it exists it
    is kept as it is (only its range set), so several scripts can each add their tracks; `replace` starts it afresh.
    Example: film-ue op seq.new path=/Game/S/SEQ_A start=0 end=240 fps=24
    """
    if EAL.does_asset_exist(path) and replace:
        if LSE.get_current_level_sequence():
            LSE.close_level_sequence()
        EAL.delete_asset(path)
    made = not EAL.does_asset_exist(path)
    from .seqcore import seq_core
    # an existing sequence keeps its rate (only its range is set), as this op always did
    r = seq_core.add(path=path, fps=fps if made else None, start=int(start), end=int(end))
    seq = E.get(path)
    return {"sequence": path, "created": made, "start": r["range"][0], "end": r["range"][1], "fps": _fps(seq)}


@op("seq.key_float", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def key_float(path: str, label: str, prop: str, keys: list, component: str = "", interp: str = "auto",
              double: bool = False) -> dict:
    """Key a float property of an actor or component: keys [[frame, value(, interp)], ...], interp "auto" (smooth,
    eased at held ends), "linear" or "constant" (stepped). `prop` is the C++ name or a path into structs, either
    spelling: "Intensity", "Temperature", "FocusSettings.ManualFocusDistance" (CameraComponent), "CurrentAperture",
    "Settings.AutoExposureBias" (a PostProcessVolume actor: set its override flag once with look.post), "FogDensity".
    `component` by name or class ("CameraComponent", "LightComponent0"); "" = the actor if it has the property, else
    its root component (a light's). `double` for a double property (a UE5 large-world value). Replaces only this
    property's track on that binding; the keys hold before the first and after the last.
    Example: film-ue op seq.key_float path=/Game/S/SEQ_A label=Key prop=Intensity 'keys=[[0,5],[24,10]]'
    """
    seq = load(path)
    comp = _owner(label, component, prop)
    keys_ = [[int(frame), float(v), _interp_name(how[0] if how else interp)] for frame, v, *how in keys]
    _write(seq, [_track("float", label, comp, _path(prop)[0], {"double": True} if double else {},
                        [_section(channels={"value": {"keys": keys_, "default": None}})])])
    return {"binding": f"{label}.{comp}" if comp else label, "prop": _path(prop)[0], "keys": len(keys)}


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


@op("seq.key_color", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def key_color(path: str, label: str, prop: str, keys: list, component: str = "", interp: str = "auto",
              srgb: bool = None) -> dict:
    """Key a colour property: keys [[frame, [r, g, b(, a)](, interp)], ...]. An FColor property (a light's
    "LightColor") takes sRGB 0-1, as look.light does; an FLinearColor one (fog "FogInscatteringLuminance", a post
    "Settings.ColorGain") takes linear values. `srgb` overrides that guess. Component and replacement as key_float.
    Example: film-ue op seq.key_color path=/Game/S/SEQ_A label=Key prop=LightColor 'keys=[[0,[1,0.8,0.6]]]'
    """
    seq = load(path)
    comp = _owner(label, component, prop)
    owner = _component(label, comp) if comp else actor(label)
    if srgb is None:
        srgb = isinstance(_value(owner, prop), unreal.Color)
    ch = {n: [] for n in "rgba"}
    for frame, rgb, *how in keys:
        rgba = list(rgb) + [1.0] * (4 - len(rgb))
        if srgb:  # the channels are linear; the engine writes an FColor property back as sRGB
            rgba = [_to_linear(x) for x in rgba[:3]] + rgba[3:]
        for n, v in zip("rgba", rgba):
            ch[n].append([int(frame), float(v), _interp_name(how[0] if how else interp)])
    _write(seq, [_track("color", label, comp, _path(prop)[0], sections=[_section(
        channels={n: {"keys": k, "default": None} for n, k in ch.items()})])])
    return {"binding": f"{label}.{comp}" if comp else label, "prop": _path(prop)[0], "keys": len(keys), "srgb": srgb}


@op("seq.key_visible", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def key_visible(path: str, label: str, keys: list, component: str = "", attached: bool = False) -> dict:
    """Show and hide an actor (or one of its components) over a sequence: keys [[frame, visible], ...], stepped; the
    first key holds before it. Overrides the level's hidden state while the sequence is open or playing (a
    presenter hidden in the level can appear in the reel). `attached` keys the actors attached to it too (her
    earrings and watch). Replaces only the visibility track.
    Example: film-ue op seq.key_visible path=/Game/S/SEQ_A label=Prop 'keys=[[0,true],[100,false]]'
    """
    seq = load(path)
    labels = [label] + ([a.get_actor_label() for a in actor(label).get_attached_actors()] if attached and not component else [])
    ks = [[int(frame), bool(vis), "constant"] for frame, vis in keys]
    _write(seq, [_track("visibility", lab, component, sections=[_section(
        channels={"visible": {"keys": list(ks), "default": None}})]) for lab in labels])
    return {"bindings": labels, "keys": len(keys)}


def _mesh(label: str, component: str):
    if component:
        return _component(label, component)
    c = actor(label).get_components_by_class(unreal.MeshComponent)
    if not c:
        raise ValueError(f"{label!r} has no mesh component")
    return c[0]


@op("seq.key_material", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def key_material(path: str, label: str, param: str, keys: list, slot=0, component: str = "",
                 interp: str = "auto") -> dict:
    """Key a material parameter on a mesh component's material slot (the material there must be an instance or
    material with that parameter): keys [[frame, value(, interp)], ...], a float for a scalar parameter or
    [r, g, b(, a)] (linear) for a vector one. `slot` is its index or name ("M_Sheer"); `component` "" = the actor's
    first mesh component. Replaces only that parameter's keys in the slot's track; other parameters keep theirs.
    Example: film-ue op seq.key_material path=/Game/S/SEQ_A label=Sign param=Glow 'keys=[[0,0],[24,1]]'
    """
    seq = load(path)
    mesh = _mesh(label, component)
    names = [str(n) for n in mesh.get_material_slot_names()]
    index = names.index(slot) if isinstance(slot, str) else int(slot)
    vector = bool(keys) and isinstance(keys[0][1], (list, tuple))
    ks = [[int(frame), [float(x) for x in v] + [1.0] * (4 - len(v)) if vector else float(v),
           _interp_name(how[0] if how else interp)] for frame, v, *how in keys]
    params = {"slot": index}
    if index < len(names):
        params["slot_name"] = names[index]
    _write(seq, [_track("material", label, mesh.get_name(), f"slot:{index}", params,
                        [_section(channels={param: {"keys": ks, "default": None}})])])
    return {"binding": f"{label}.{mesh.get_name()}", "slot": index, "param": param, "keys": len(keys)}


@op("seq.key_collection", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def key_collection(path: str, collection: str, param: str, keys: list, interp: str = "auto") -> dict:
    """Key a scalar parameter of a material parameter collection (look.collection) on the sequence's track for that
    collection: keys [[frame, value(, interp)], ...]. Sequencer writes the world's instance of the collection, so the
    value reaches every material reading it with no mesh binding and no MID in between. Replaces only that
    parameter's keys.
    Example: film-ue op seq.key_collection path=/Game/S/SEQ_A collection=/Game/MPC_FM param=WipeOn 'keys=[[0,0],[24,1]]'
    """
    seq = load(path)
    load(collection)
    ks = [[int(frame), float(v), _interp_name(how[0] if how else interp)] for frame, v, *how in keys]
    _write(seq, [_track("mpc", name=collection, sections=[_section(
        channels={param: {"keys": ks, "default": None}})])])
    mpc = load(collection)
    track = next(t for t in seq.find_tracks_by_type(unreal.MovieSceneMaterialParameterCollectionTrack)
                 if t.get_editor_property("mpc") == mpc)
    sec = track.get_sections()[0]
    # seqcore keys a collection by FName (MovieSceneParameterSection.add_scalar_parameter_key(name, ticks, v, interp))
    return {"collection": collection, "param": param, "keys": len(keys), "section": sec.get_class().get_name(),
            "form": "name+interp"}





@op("seq.anim", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def anim_track(path: str, label: str, component: str, sections: list, replace: bool = True) -> list:
    """Animation sections on an actor's skeletal mesh component (a MetaHuman's "Body" or "Face"), each
    {"anim", "start", "end", "offset", "blend_in", "blend_out", "rate", "weight", "loop", "row"}: `start`/`end`
    frames (end default: start + the animation's length / rate; past that it loops, `loop` False holds the last
    pose), `offset` seconds into the animation where it starts, `blend_in`/`blend_out` frames of ease (weights
    cross-fade where sections overlap: idle -> line -> idle), `weight` (1), `row` (default: the first free one; overlaps
    go on separate rows). `replace` clears the track's sections first, else these are added. Returns [[anim, start,
    end, row]].
    Example: film-ue op seq.anim path=/Game/S/SEQ_A label=Host component=Body 'sections=[{"anim":"/Game/A/Idle","start":0,"blend_in":6}]'
    """
    seq = load(path)
    E.binding(seq, label, component, create=True)
    have = E.track_by_id(E.describe(path), ("anim", label, component, ""))
    old = [] if replace or have is None else have["sections"]
    fps = _fps(seq)
    taken = [(s["range"][0], s["range"][1], s.get("row", 0)) for s in old]
    secs, out = list(old), []
    for d in sections:
        a = load(d["anim"])
        rate = float(d.get("rate", 1.0))
        offset = float(d.get("offset", 0.0))
        start = int(d["start"])
        length = E.anim_length(a) or 0.0
        end = int(d.get("end", start + int(math.ceil((length - offset) * fps / rate))))
        row = d.get("row")
        if row is None:
            row = 0
            while any(r == row and s < end and start < e for s, e, r in taken):
                row += 1
        p = {"anim": d["anim"], "offset": offset, "rate": rate}
        for side in ("in", "out"):  # frames of manual ease (seqcore sets them in ticks)
            if d.get(f"blend_{side}"):
                p[f"blend_{side}"] = d[f"blend_{side}"]
        ch = {"weight": {"keys": [], "default": float(d["weight"])}} if "weight" in d else {}
        secs.append(_section((start, end), int(row), p, ch))
        taken.append((start, end, row))
        out.append([d["anim"], start, end, int(row)])
    _write(seq, [_track("anim", label, component, sections=secs)])
    return out


@op("seq.audio", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def audio(path: str, clips: list, track: str = "Audio", replace: bool = True) -> list:
    """Sounds in a sequence on a named audio track ("VO", "Score", "SFX"): clips [{"sound", "start", "end", "offset",
    "volume"}] or [sound, start]: a SoundWave asset (assets.import a WAV first) from frame `start`, `offset` seconds
    into it, to `end` (default: its length), at `volume` (1). For timing in the editor; the mix is made in post.
    `replace` empties the named track first, else adds to it. Returns [[sound, start, end, row]].
    Example: film-ue op seq.audio path=/Game/S/SEQ_A track=VO 'clips=[["/Game/Audio/L1",12]]'
    """
    seq = load(path)
    have = E.track_by_id(E.describe(path), ("audio", "", "", track))
    old = [] if replace or have is None else have["sections"]
    fps = _fps(seq)
    taken = [(s["range"][0], s["range"][1], s.get("row", 0)) for s in old]
    secs, out = list(old), []
    for c in clips:
        c = c if isinstance(c, dict) else {"sound": c[0], "start": c[1]}
        wave = load(c["sound"])
        offset = float(c.get("offset", 0.0))
        start = int(c["start"])
        end = int(c.get("end", start + int(math.ceil((wave.get_editor_property("duration") - offset) * fps))))
        row = 0
        while any(r == row and s < end and start < e for s, e, r in taken):
            row += 1
        ch = {"volume": {"keys": [], "default": float(c["volume"])}} if "volume" in c else {}
        secs.append(_section((start, end), row, {"sound": c["sound"], "offset": offset}, ch))
        taken.append((start, end, row))
        out.append([c["sound"], start, end, row])
    _write(seq, [_track("audio", name=track, sections=secs)])
    return out


@op("seq.cuts", mutates=False, idempotent=True, tags=["sequencer", "legacy"])
def cuts(path: str) -> list:
    """The edit as it stands: [camera label, first frame, end frame] for each camera cut, in order.
    Example: film-ue op seq.cuts path=/Game/S/SEQ_A
    """
    doc = E.describe(path, keys=False)
    if not doc["exists"]:
        raise not_found("sequence", path, hint="seq.new or seq.add makes it")
    out = []
    for t in doc["tracks"]:
        if t["kind"] != "camera_cut":
            continue
        for s in t["sections"]:
            cam = s["params"]["camera"]
            if cam.startswith("?"):
                raise ValueError(f"camera cut at {s['range'][0]} is bound to no binding of {path} ({cam[1:]})")
            out.append([cam, s["range"][0], s["range"][1]])
    return sorted(out, key=lambda c: c[1])


def cut_camera(path: str, frame: int) -> str:
    """The camera the edit shows at `frame`."""
    for cam, start, end in cuts(path):
        if start <= int(frame) < end:
            return cam
    raise ValueError(f"no camera cut at frame {frame} in {path}")


@op("seq.rebind", mutates=True, idempotent=True, tags=["sequencer", "legacy"])
def rebind(path: str, labels: list | None = None) -> dict:
    """Point a sequence's actor bindings at the level's actors of the same label again, after the level was rebuilt
    and the old actors are gone (their tracks are kept; a binding removed and remade would lose them). `labels` None
    = every actor binding whose name is an actor in the level. Returns {label: "ok" | "missing"}.
    Example: film-ue op seq.rebind path=/Game/S/SEQ_A 'labels=["Host"]'
    """
    seq = load(path)
    out = {}
    for (name, comp), b in E.bindings(seq).items():
        if comp or E.is_spawnable(b):
            continue  # a component binding follows its actor's; a spawnable has no level actor
        if labels is not None and name not in labels:
            continue
        if find_actor(name) is None:
            if labels is not None:
                out[name] = "missing"
            continue
        if E.is_bound(seq, b) is False:  # bound to an actor that is gone: re-point it, its tracks kept
            E.bind(seq, name)
        out[name] = "ok"
    EAL.save_asset(path)
    if LSE.get_current_level_sequence():
        LSE.refresh_current_level_sequence()
    return out


@op("seq.tracks", mutates=False, idempotent=True, tags=["sequencer", "legacy"])
def tracks(path: str) -> dict:
    """What a sequence holds: for each binding (an actor, or actor.component) its tracks as [class, property or
    name, sections, keys]; master tracks under "". For checking what a build script made.
    Example: film-ue op seq.tracks path=/Game/S/SEQ_A
    """
    seq = load(path)

    def describe(t):
        name = ""
        for f in ("get_property_path", "get_display_name"):
            try:
                name = str(getattr(t, f)())
                break
            except Exception:
                pass
        secs = t.get_sections()
        keys = sum(len(ch.get_keys()) for s in secs for ch in s.get_all_channels() if hasattr(ch, "get_keys"))
        return [t.get_class().get_name(), name, len(secs), keys]
    out = {"": [describe(t) for t in seq.get_tracks()]}
    for b in seq.get_bindings():
        name = str(b.get_display_name())
        try:
            parent = b.get_parent()
            if parent is not None and str(parent.get_display_name()):
                name = f"{parent.get_display_name()}.{name}"
        except Exception:
            pass
        out[name] = [describe(t) for t in b.get_tracks()]
    return out
