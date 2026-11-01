"""Level sequences: a shot from an actor, animations per component, audio and a camera; open and scrub. Keys on any
property of an actor or component (floats, colours, visibility, material parameters), animation sections at offsets
with blends, audio clips, and stills through the edit.

Sequencer traps these ops handle: frames are display-rate frames (the sequence's fps); section easing and start
offsets are in tick resolution, converted here. Components are bound under their actor's binding and found by the
pair (actor, component), never by the component's name alone (both presenters have a "Body"). Each key op replaces
only its own track (that property, that parameter) on that binding, so re-running it is safe and tracks coexist."""
from __future__ import annotations

import math

import unreal

from . import op
from .assets import EAL, load
from .level import actor, look_rot

LSE = unreal.LevelSequenceEditorBlueprintLibrary


@op("seq.shot")
def shot(path: str, actor_label: str, anims: dict, camera: str, audio: str = "", seconds: float = 0.0, fps: int = 24,
         audio_start: int = 0, tail: int = 6) -> dict:
    """A shot: `anims` maps component names to animations ({"Body": idle, "Face": talk}); `audio` a SoundWave; the
    camera cut on `camera`. Length: `seconds`, else the audio's, else the longest animation's."""
    if EAL.does_asset_exist(path):
        if LSE.get_current_level_sequence():
            LSE.close_level_sequence()
        EAL.delete_asset(path)
    folder, name = path.rsplit("/", 1)
    seq = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    wave = load(audio) if audio else None
    secs = seconds or (wave.get_editor_property("duration") if wave else 0) or max(
        load(a).get_editor_property("sequence_length") for a in anims.values())
    end = int(math.ceil(secs * fps)) + tail
    seq.set_display_rate(unreal.FrameRate(fps, 1))
    seq.set_playback_start(0)
    seq.set_playback_end(end)
    a = actor(actor_label)
    seq.add_possessable(a)
    comps = {c.get_name(): c for c in a.get_components_by_class(unreal.SkeletalMeshComponent)}
    for comp, anim in anims.items():
        b = seq.add_possessable(comps[comp])
        tr = b.add_track(unreal.MovieSceneSkeletalAnimationTrack)
        sec = tr.add_section()
        sec.set_range(0, end)
        p = sec.get_editor_property("params")
        p.set_editor_property("animation", load(anim))
        sec.set_editor_property("params", p)
    if wave:
        tr = seq.add_track(unreal.MovieSceneAudioTrack)
        s = tr.add_section()
        s.set_range(audio_start, end)
        s.set_sound(wave)
    cb = seq.add_possessable(actor(camera))
    cut = seq.add_track(unreal.MovieSceneCameraCutTrack)
    cs = cut.add_section()
    cs.set_range(0, end)
    cs.set_camera_binding_id(seq.get_binding_id(cb))
    EAL.save_asset(path)
    return {"sequence": path, "frames": end, "fps": fps}


@op("seq.scrub")
def scrub(path: str, frame: int) -> int:
    """Open a sequence in Sequencer, locked to its camera, at a frame (for checking a pose in the viewport)."""
    LSE.open_level_sequence(load(path))
    LSE.set_lock_camera_cut_to_viewport(True)
    LSE.set_current_time(int(frame))
    return frame


@op("seq.close")
def close() -> bool:
    """Close the open sequence."""
    LSE.close_level_sequence()
    return True


def _binding(seq, name: str):
    for b in seq.get_bindings():
        if str(b.get_display_name()) == name or str(b.get_name()) == name:
            return b
    raise ValueError(f"no binding {name!r} in {seq.get_path_name()}")


def component_of(actor_label: str, component: str):
    return next(c for c in actor(actor_label).get_components_by_class(unreal.SceneComponent) if c.get_name() == component)


@op("seq.set_anim")
def set_anim(path: str, component: str, anim: str, label: str = "", only: str = "") -> str:
    """Swap the animation on a component's track in a sequence: every section of it, or only those playing `only`.
    `label` picks the actor when several have a component of that name (both presenters have "Body")."""
    seq = load(path)
    b = _comp_binding(seq, label, component, create=False) if label else _binding(seq, component)
    tracks = b.find_tracks_by_type(unreal.MovieSceneSkeletalAnimationTrack)
    for s in tracks[0].get_sections():
        p = s.get_editor_property("params")
        cur = p.get_editor_property("animation")
        if only and not (cur and cur.get_path_name().split(".")[0] in (only, anim)):
            continue
        p.set_editor_property("animation", load(anim))
        s.set_editor_property("params", p)
    EAL.save_asset(path)
    if LSE.get_current_level_sequence():
        LSE.refresh_current_level_sequence()
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


@op("seq.sample")
def sample(path: str, actor_label: str, component: str, bones: list, frames: list | None = None, every: int = 1,
           ticks: int = 2, camera: str = "", target=None, target_offset=None):
    """Play a sequence frame by frame across editor ticks (so animation and rigs settle) and record bones' world
    transforms, each [x, y, z, axis_x(3), axis_y(3), axis_z(3)], `camera`'s location, and `target`'s (see
    seq.aim_point: a point, an actor, "Label:Component:bone"). A multi-tick job."""
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


@op("seq.still")
def seq_still(path: str, frame: int, camera: str, out: str, width: int = 1920, height: int = 1080, settle: int = 30):
    """A still of a sequence at a frame through `camera`, or, with camera "", through the camera the edit (the camera
    cut track) shows at that frame: scrub there, let it settle `settle` ticks (temporal anti-aliasing, Lumen),
    capture. A multi-tick job."""
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


def _bound(seq, label: str):
    """The sequence's binding for an actor, made when missing."""
    for b in seq.get_bindings():
        if str(b.get_display_name()) == label:
            return b
    return seq.add_possessable(actor(label))


@op("seq.key_transform")
def key_transform(path: str, label: str, keys: list, interp: str = "auto") -> int:
    """Animate an actor in a sequence: keys are [frame, [x, y, z], {"pitch", "yaw", "roll"} | [x, y, z] to look at]
    with an optional 4th element, the interpolation leaving that key: "auto" (smooth, eases at held ends), "linear"
    or "constant" (hold until the next key, a jump cut). `interp` is the default. Replaces the actor's transform
    track (and only that), keeping the actor's scale; yaw is keyed as given, so unwrap it yourself across +-180."""
    seq = load(path)
    b = _bound(seq, label)
    for t in b.find_tracks_by_type(unreal.MovieScene3DTransformTrack):
        b.remove_track(t)
    sec = b.add_track(unreal.MovieScene3DTransformTrack).add_section()
    sec.set_range(seq.get_playback_start(), seq.get_playback_end())
    ch = list(sec.get_all_channels())[:9]  # location x y z, rotation x (roll) y (pitch) z (yaw), scale x y z
    sc = actor(label).get_actor_scale3d()  # kept as the actor has it
    for frame, loc, aim, *how in keys:
        mode = _interp(how[0] if how else interp)
        r = look_rot(loc, aim) if isinstance(aim, (list, tuple)) else unreal.Rotator(
            roll=aim.get("roll", 0.0), pitch=aim.get("pitch", 0.0), yaw=aim.get("yaw", 0.0))
        for c, v in zip(ch, list(loc) + [r.roll, r.pitch, r.yaw] + [sc.x, sc.y, sc.z]):
            c.add_key(unreal.FrameNumber(int(frame)), float(v), interpolation=mode)
    EAL.save_asset(path)
    return len(keys)


@op("seq.camera_cuts")
def camera_cuts(path: str, cuts: list) -> list:
    """The edit: cuts are [camera label, first frame] in order; each runs to the next (the last to the end)."""
    seq = load(path)
    for t in seq.find_tracks_by_type(unreal.MovieSceneCameraCutTrack):
        seq.remove_track(t)
    track = seq.add_track(unreal.MovieSceneCameraCutTrack)
    end = seq.get_playback_end()
    out = []
    for k, (cam, start) in enumerate(cuts):
        stop = cuts[k + 1][1] if k + 1 < len(cuts) else end
        s = track.add_section()
        s.set_range(int(start), int(stop))
        s.set_camera_binding_id(seq.get_binding_id(_bound(seq, cam)))
        out.append([cam, int(start), int(stop)])
    EAL.save_asset(path)
    return out


@op("seq.stills")
def seq_stills(path: str, frames: list, camera: str = "", out_dir: str = "", width: int = 960, height: int = 540,
               settle: int = 20):
    """Stills of a sequence at many frames ({out_dir}/{frame:04d}.png): a contact sheet's worth in one call. Through
    one `camera`, or with camera "" each frame through its own shot's camera (the camera cut track): a previs of the
    whole cut. A multi-tick job; returns [[frame, camera, path]]."""
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


def _interp(name: str):
    return getattr(unreal.MovieSceneKeyInterpolation, INTERP[str(name).lower()])


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
    ab = _bound(seq, label) if create else next(b for b in seq.get_bindings() if str(b.get_display_name()) == label)
    if not component:
        return ab
    name = _component(label, component).get_name() if create else component
    for b in seq.get_bindings():
        try:
            parent = b.get_parent()
        except Exception:
            parent = None
        if str(b.get_display_name()) == name and parent is not None and parent == ab:
            return b
    for b in ab.get_child_possessables():
        if str(b.get_display_name()) == name:
            return b
    if not create:
        raise ValueError(f"no binding for {label}.{component} in {seq.get_path_name()}")
    return seq.add_possessable(_component(label, component))


def _property_track(b, cls, prop: str):
    """A fresh track of `cls` for `prop` on a binding (the old one for that property removed, others kept), with one
    section open at both ends so the first and last keys hold before and after."""
    path, leaf = _path(prop)
    for t in b.find_tracks_by_type(cls):
        if str(t.get_property_path()) == path:
            b.remove_track(t)
    t = b.add_track(cls)
    t.set_property_name_and_path(leaf, path)
    sec = t.add_section()
    sec.set_start_frame_bounded(False)
    sec.set_end_frame_bounded(False)
    return t, sec


def _ticks(seq, frames: float) -> int:
    """Display frames to tick resolution (section easing and offsets are in ticks)."""
    d, t = seq.get_display_rate(), seq.get_tick_resolution()
    return int(round(frames * (t.numerator / t.denominator) / (d.numerator / d.denominator)))


def _fps(seq) -> float:
    r = seq.get_display_rate()
    return r.numerator / r.denominator


def _done(path: str):
    EAL.save_asset(path)
    if LSE.get_current_level_sequence():
        LSE.refresh_current_level_sequence()


@op("seq.new")
def new(path: str, start: int = 0, end: int = 120, fps: int = 24, replace: bool = False) -> dict:
    """An empty level sequence for building into (no actor, no camera): playback [start, end) at `fps`. If it exists it
    is kept as it is (only its range set), so several scripts can each add their tracks; `replace` starts it afresh."""
    if EAL.does_asset_exist(path) and replace:
        if LSE.get_current_level_sequence():
            LSE.close_level_sequence()
        EAL.delete_asset(path)
    if EAL.does_asset_exist(path):
        seq, made = load(path), False
    else:
        folder, name = path.rsplit("/", 1)
        seq = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.LevelSequence,
                                                                     unreal.LevelSequenceFactoryNew())
        seq.set_display_rate(unreal.FrameRate(fps, 1))
        made = True
    seq.set_playback_start(int(start))
    seq.set_playback_end(int(end))
    EAL.save_asset(path)
    return {"sequence": path, "created": made, "start": seq.get_playback_start(), "end": seq.get_playback_end(),
            "fps": _fps(seq)}


@op("seq.key_float")
def key_float(path: str, label: str, prop: str, keys: list, component: str = "", interp: str = "auto",
              double: bool = False) -> dict:
    """Key a float property of an actor or component: keys [[frame, value(, interp)], ...], interp "auto" (smooth,
    eased at held ends), "linear" or "constant" (stepped). `prop` is the C++ name or a path into structs, either
    spelling: "Intensity", "Temperature", "FocusSettings.ManualFocusDistance" (CameraComponent), "CurrentAperture",
    "Settings.AutoExposureBias" (a PostProcessVolume actor: set its override flag once with look.post), "FogDensity".
    `component` by name or class ("CameraComponent", "LightComponent0"); "" = the actor if it has the property, else
    its root component (a light's). `double` for a double property (a UE5 large-world value). Replaces only this
    property's track on that binding; the keys hold before the first and after the last."""
    seq = load(path)
    comp = _owner(label, component, prop)
    b = _comp_binding(seq, label, comp)
    _, sec = _property_track(b, unreal.MovieSceneDoubleTrack if double else unreal.MovieSceneFloatTrack, prop)
    ch = sec.get_all_channels()[0]
    for frame, v, *how in keys:
        ch.add_key(unreal.FrameNumber(int(frame)), float(v), interpolation=_interp(how[0] if how else interp))
    _done(path)
    return {"binding": f"{label}.{comp}" if comp else label, "prop": _path(prop)[0], "keys": len(keys)}


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


@op("seq.key_color")
def key_color(path: str, label: str, prop: str, keys: list, component: str = "", interp: str = "auto",
              srgb: bool = None) -> dict:
    """Key a colour property: keys [[frame, [r, g, b(, a)](, interp)], ...]. An FColor property (a light's
    "LightColor") takes sRGB 0-1, as look.light does; an FLinearColor one (fog "FogInscatteringLuminance", a post
    "Settings.ColorGain") takes linear values. `srgb` overrides that guess. Component and replacement as key_float."""
    seq = load(path)
    comp = _owner(label, component, prop)
    owner = _component(label, comp) if comp else actor(label)
    if srgb is None:
        srgb = isinstance(_value(owner, prop), unreal.Color)
    b = _comp_binding(seq, label, comp)
    _, sec = _property_track(b, unreal.MovieSceneColorTrack, prop)
    ch = sec.get_all_channels()[:4]  # r g b a
    for frame, rgb, *how in keys:
        rgba = list(rgb) + [1.0] * (4 - len(rgb))
        if srgb:  # the channels are linear; the engine writes an FColor property back as sRGB
            rgba = [_to_linear(x) for x in rgba[:3]] + rgba[3:]
        for c, v in zip(ch, rgba):
            c.add_key(unreal.FrameNumber(int(frame)), float(v), interpolation=_interp(how[0] if how else interp))
    _done(path)
    return {"binding": f"{label}.{comp}" if comp else label, "prop": _path(prop)[0], "keys": len(keys), "srgb": srgb}


@op("seq.key_visible")
def key_visible(path: str, label: str, keys: list, component: str = "", attached: bool = False) -> dict:
    """Show and hide an actor (or one of its components) over a sequence: keys [[frame, visible], ...], stepped; the
    first key holds before it. Overrides the level's hidden state while the sequence is open or playing (a
    presenter hidden in the level can appear in the reel). `attached` keys the actors attached to it too (her
    earrings and watch). Replaces only the visibility track."""
    seq = load(path)
    labels = [label] + ([a.get_actor_label() for a in actor(label).get_attached_actors()] if attached and not component else [])
    for lab in labels:
        b = _comp_binding(seq, lab, component)
        for t in b.find_tracks_by_type(unreal.MovieSceneVisibilityTrack):
            b.remove_track(t)
        t = b.add_track(unreal.MovieSceneVisibilityTrack)
        t.set_property_name_and_path("bHiddenInGame", "bHiddenInGame")
        sec = t.add_section()
        sec.set_start_frame_bounded(False)
        sec.set_end_frame_bounded(False)
        ch = sec.get_all_channels()[0]
        for frame, vis in keys:
            ch.add_key(unreal.FrameNumber(int(frame)), bool(vis))
    _done(path)
    return {"bindings": labels, "keys": len(keys)}


def _mesh(label: str, component: str):
    if component:
        return _component(label, component)
    c = actor(label).get_components_by_class(unreal.MeshComponent)
    if not c:
        raise ValueError(f"{label!r} has no mesh component")
    return c[0]


@op("seq.key_material")
def key_material(path: str, label: str, param: str, keys: list, slot=0, component: str = "",
                 interp: str = "auto") -> dict:
    """Key a material parameter on a mesh component's material slot (the material there must be an instance or
    material with that parameter): keys [[frame, value(, interp)], ...], a float for a scalar parameter or
    [r, g, b(, a)] (linear) for a vector one. `slot` is its index or name ("M_Sheer"); `component` "" = the actor's
    first mesh component. Replaces only that parameter's keys in the slot's track; other parameters keep theirs."""
    seq = load(path)
    mesh = _mesh(label, component)
    names = [str(n) for n in mesh.get_material_slot_names()]
    index = names.index(slot) if isinstance(slot, str) else int(slot)
    b = _comp_binding(seq, label, mesh.get_name())
    track = None
    for t in b.find_tracks_by_type(unreal.MovieSceneComponentMaterialTrack):
        if _material_index(t) == index:
            track = t
    if track is None:
        track = b.add_track(unreal.MovieSceneComponentMaterialTrack)
    _set_material_index(track, index, names[index] if index < len(names) else "")  # also mends an older track
    secs = track.get_sections()
    sec = secs[0] if secs else track.add_section()
    sec.set_start_frame_bounded(False)
    sec.set_end_frame_bounded(False)
    vector = bool(keys) and isinstance(keys[0][1], (list, tuple))
    # Sequencer writes into the MID by the whole parameter info (name, association, index), so a plain material
    # parameter needs GLOBAL_PARAMETER and index -1 said outright: a bare MaterialParameterInfo from Python names the
    # parameter but matches none, and the MID keeps the instance's values. The bare one is removed too (older keys).
    bare = unreal.MaterialParameterInfo()
    bare.set_editor_property("name", param)
    info = unreal.MaterialParameterInfo()
    info.set_editor_property("name", param)
    info.set_editor_property("association", unreal.MaterialParameterAssociation.GLOBAL_PARAMETER)
    info.set_editor_property("index", -1)
    for old in (bare, info):
        for remove in ("remove_scalar_parameter", "remove_color_parameter"):
            try:
                getattr(sec, remove)(old)
            except Exception:
                pass
    for frame, v, *how in keys:
        mode = _interp(how[0] if how else interp)
        if vector:
            rgba = list(v) + [1.0] * (4 - len(v))
            sec.add_color_parameter_key(info, unreal.FrameNumber(int(frame)), unreal.LinearColor(*rgba), "", "",
                                        default_interpolation=mode)
        else:
            sec.add_scalar_parameter_key(info, unreal.FrameNumber(int(frame)), float(v), "", "",
                                         default_interpolation=mode)
    _done(path)
    return {"binding": f"{label}.{mesh.get_name()}", "slot": index, "param": param, "keys": len(keys)}


def _material_index(t) -> int:
    return int(t.get_material_info().get_editor_property("material_slot_index"))


def _set_material_index(t, index: int, name: str):
    """Point a material track at a mesh's slot. Since UE 5.4 the track's info also has a material type, and a track
    made from Python starts at EMPTY (the editor's UI sets it): an EMPTY track resolves to no material, so Sequencer
    makes no MID and none of its keys reach the mesh."""
    info = t.get_material_info()
    if hasattr(unreal, "ComponentMaterialType"):
        info.set_editor_property("material_type", unreal.ComponentMaterialType.INDEXED_MATERIAL)
    info.set_editor_property("material_slot_index", index)
    if name:
        info.set_editor_property("material_slot_name", name)
    t.set_material_info(info)


def _play_rate(rate: float):
    """A section's play rate: a float before UE 5.5, a time-warp variant set to a fixed rate since."""
    if not hasattr(unreal, "MovieSceneTimeWarpVariant"):
        return float(rate)
    v = unreal.MovieSceneTimeWarpVariant()
    v.set_fixed_play_rate(float(rate))
    return v


@op("seq.anim")
def anim_track(path: str, label: str, component: str, sections: list, replace: bool = True) -> list:
    """Animation sections on an actor's skeletal mesh component (a MetaHuman's "Body" or "Face"), each
    {"anim", "start", "end", "offset", "blend_in", "blend_out", "rate", "weight", "loop", "row"}: `start`/`end`
    frames (end default: start + the animation's length / rate; past that it loops, `loop` False holds the last
    pose), `offset` seconds into the animation where it starts, `blend_in`/`blend_out` frames of ease (weights
    cross-fade where sections overlap: idle -> line -> idle), `weight` (1), `row` (default: the first free one; overlaps
    go on separate rows). `replace` clears the track's sections first, else these are added. Returns [[anim, start,
    end, row]]."""
    seq = load(path)
    b = _comp_binding(seq, label, component)
    tracks = b.find_tracks_by_type(unreal.MovieSceneSkeletalAnimationTrack)
    track = tracks[0] if tracks else b.add_track(unreal.MovieSceneSkeletalAnimationTrack)
    if replace:
        for s in track.get_sections():
            track.remove_section(s)
    fps = _fps(seq)
    taken = [] if replace else [(s.get_start_frame(), s.get_end_frame(), s.get_row_index()) for s in track.get_sections()]
    out = []
    for d in sections:
        a = load(d["anim"])
        rate = float(d.get("rate", 1.0))
        offset = float(d.get("offset", 0.0))
        start = int(d["start"])
        length = a.get_editor_property("sequence_length")
        end = int(d.get("end", start + int(math.ceil((length - offset) * fps / rate))))
        row = d.get("row")
        if row is None:
            row = 0
            while any(r == row and s < end and start < e for s, e, r in taken):
                row += 1
        sec = track.add_section()
        sec.set_range(start, end)
        sec.set_row_index(int(row))
        p = sec.get_editor_property("params")
        p.set_editor_property("animation", a)
        if rate != 1.0:
            p.set_editor_property("play_rate", _play_rate(rate))
        if offset:
            for k in ("first_loop_start_frame_offset", "start_frame_offset"):
                try:
                    p.set_editor_property(k, unreal.FrameNumber(_ticks(seq, offset * fps)))
                    break
                except Exception:
                    pass
        if d.get("loop") is False:
            p.set_editor_property("force_custom_mode", False)
            for k in ("hold_last_frame", "b_hold_last_frame"):  # hold rather than loop past the end of the clip
                try:
                    p.set_editor_property(k, True)
                    break
                except Exception:
                    pass
        sec.set_editor_property("params", p)
        if "weight" in d:
            for ch in sec.get_all_channels():
                if "weight" in str(ch.get_name()).lower():
                    ch.set_default(float(d["weight"]))
        ease = [f"bManualEase{side}=True,ManualEase{side}Duration={_ticks(seq, d[f'blend_{side.lower()}'])}"
                for side in ("In", "Out") if d.get(f"blend_{side.lower()}")]
        if ease:  # the manual-ease flags are not editor properties: set them as text
            e = sec.get_editor_property("easing")
            e.import_text("(" + ",".join(ease) + ")")
            sec.set_editor_property("easing", e)
        taken.append((start, end, row))
        out.append([d["anim"], start, end, int(row)])
    _done(path)
    return out


@op("seq.audio")
def audio(path: str, clips: list, track: str = "Audio", replace: bool = True) -> list:
    """Sounds in a sequence on a named audio track ("VO", "Score", "SFX"): clips [{"sound", "start", "end", "offset",
    "volume"}] or [sound, start]: a SoundWave asset (assets.import a WAV first) from frame `start`, `offset` seconds
    into it, to `end` (default: its length), at `volume` (1). For timing in the editor; the mix is made in post.
    `replace` empties the named track first, else adds to it. Returns [[sound, start, end, row]]."""
    seq = load(path)
    t = next((x for x in seq.find_tracks_by_type(unreal.MovieSceneAudioTrack) if str(x.get_display_name()) == track), None)
    if t is not None and replace:
        seq.remove_track(t)
        t = None
    if t is None:
        t = seq.add_track(unreal.MovieSceneAudioTrack)
        t.set_display_name(track)
    fps = _fps(seq)
    taken = [(s.get_start_frame(), s.get_end_frame(), s.get_row_index()) for s in t.get_sections()]
    out = []
    for c in clips:
        c = c if isinstance(c, dict) else {"sound": c[0], "start": c[1]}
        wave = load(c["sound"])
        offset = float(c.get("offset", 0.0))
        start = int(c["start"])
        end = int(c.get("end", start + int(math.ceil((wave.get_editor_property("duration") - offset) * fps))))
        row = 0
        while any(r == row and s < end and start < e for s, e, r in taken):
            row += 1
        s = t.add_section()
        s.set_range(start, end)
        s.set_row_index(row)
        s.set_sound(wave)
        if offset:
            s.set_editor_property("start_frame_offset", unreal.FrameNumber(_ticks(seq, offset * fps)))
        if "volume" in c:
            for ch in s.get_all_channels():
                if "volume" in str(ch.get_name()).lower():
                    ch.set_default(float(c["volume"]))
        taken.append((start, end, row))
        out.append([c["sound"], start, end, row])
    _done(path)
    return out


@op("seq.cuts")
def cuts(path: str) -> list:
    """The edit as it stands: [camera label, first frame, end frame] for each camera cut, in order."""
    seq = load(path)
    by_id = {b.get_id().export_text(): str(b.get_display_name()) for b in seq.get_bindings()}  # a Guid's str() is its repr
    out = []
    for t in seq.find_tracks_by_type(unreal.MovieSceneCameraCutTrack):
        for s in t.get_sections():
            g = s.get_camera_binding_id().get_editor_property("guid").export_text()
            if g not in by_id:
                raise ValueError(f"camera cut at {s.get_start_frame()} is bound to no binding of {path} ({g})")
            out.append([by_id[g], s.get_start_frame(), s.get_end_frame()])
    return sorted(out, key=lambda c: c[1])


def cut_camera(path: str, frame: int) -> str:
    """The camera the edit shows at `frame`."""
    for cam, start, end in cuts(path):
        if start <= int(frame) < end:
            return cam
    raise ValueError(f"no camera cut at frame {frame} in {path}")


@op("seq.rebind")
def rebind(path: str, labels: list | None = None) -> dict:
    """Point a sequence's actor bindings at the level's actors of the same label again, after the level was rebuilt
    and the old actors are gone (their tracks are kept; a binding removed and remade would lose them). `labels` None
    = every actor binding whose name is an actor in the level. Returns {label: "ok" | "missing"}."""
    seq = load(path)
    LSE.open_level_sequence(seq)
    lss = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
    out = {}
    for b in seq.get_bindings():
        name = str(b.get_display_name())
        try:
            if b.get_parent() is not None and str(b.get_parent().get_display_name()):
                continue  # a component binding follows its actor's
        except Exception:
            pass
        if labels is not None and name not in labels:
            continue
        try:
            a = actor(name)
        except ValueError:
            if labels is not None:
                out[name] = "missing"
            continue
        lss.replace_binding_with_actors([a], b)
        out[name] = "ok"
    EAL.save_asset(path)
    LSE.refresh_current_level_sequence()
    return out


@op("seq.tracks")
def tracks(path: str) -> dict:
    """What a sequence holds: for each binding (an actor, or actor.component) its tracks as [class, property or
    name, sections, keys]; master tracks under "". For checking what a build script made."""
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
