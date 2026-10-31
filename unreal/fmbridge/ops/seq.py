"""Level sequences: a shot from an actor, animations per component, audio and a camera; open and scrub."""
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
def set_anim(path: str, component: str, anim: str) -> str:
    """Swap the animation on a component's track in a sequence (every section of it)."""
    seq = load(path)
    tracks = _binding(seq, component).find_tracks_by_type(unreal.MovieSceneSkeletalAnimationTrack)
    for s in tracks[0].get_sections():
        p = s.get_editor_property("params")
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


@op("seq.sample")
def sample(path: str, actor_label: str, component: str, bones: list, frames: list | None = None, every: int = 1,
           ticks: int = 2, camera: str = ""):
    """Play a sequence frame by frame across editor ticks (so animation and rigs settle) and record bones' world
    transforms, each [x, y, z, axis_x(3), axis_y(3), axis_z(3)], and `camera`'s location. A multi-tick job."""
    LSE.open_level_sequence(load(path))
    seq = LSE.get_current_level_sequence()
    if frames is None:
        frames = list(range(seq.get_playback_start(), seq.get_playback_end(), every))
    comp = component_of(actor_label, component)
    out = {"frames": frames, "bones": {b: [] for b in bones}, "camera": []}
    LSE.set_current_time(int(frames[0]) + 1)  # move off the first frame, so evaluating it is never skipped
    yield
    for f in frames:
        LSE.set_current_time(int(f))
        for _ in range(ticks):
            yield
        for b in bones:
            out["bones"][b].append(_xform(comp, b))
        if camera:
            p = component_of(camera, "CameraComponent").get_world_location()
            out["camera"].append([p.x, p.y, p.z])
    return out


@op("seq.still")
def seq_still(path: str, frame: int, camera: str, out: str, width: int = 1920, height: int = 1080, settle: int = 30):
    """A still of a sequence at a frame through `camera`: scrub there, let it settle `settle` ticks (temporal
    anti-aliasing, Lumen), capture. A multi-tick job."""
    from .look import still
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
def key_transform(path: str, label: str, keys: list) -> int:
    """Animate an actor in a sequence: keys are [frame, [x, y, z], {"pitch", "yaw", "roll"} | [x, y, z] to look at],
    smooth (auto tangents). Replaces the actor's transform track."""
    seq = load(path)
    b = _bound(seq, label)
    for t in b.find_tracks_by_type(unreal.MovieScene3DTransformTrack):
        b.remove_track(t)
    sec = b.add_track(unreal.MovieScene3DTransformTrack).add_section()
    sec.set_range(seq.get_playback_start(), seq.get_playback_end())
    ch = list(sec.get_all_channels())[:9]  # location x y z, rotation x (roll) y (pitch) z (yaw), scale x y z
    for frame, loc, aim in keys:
        r = look_rot(loc, aim) if isinstance(aim, (list, tuple)) else unreal.Rotator(
            roll=aim.get("roll", 0.0), pitch=aim.get("pitch", 0.0), yaw=aim.get("yaw", 0.0))
        for c, v in zip(ch, list(loc) + [r.roll, r.pitch, r.yaw] + [1.0, 1.0, 1.0]):
            c.add_key(unreal.FrameNumber(int(frame)), float(v), interpolation=unreal.MovieSceneKeyInterpolation.AUTO)
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
def seq_stills(path: str, frames: list, camera: str, out_dir: str, width: int = 960, height: int = 540, settle: int = 20):
    """Stills of a sequence at many frames through one camera ({out_dir}/{frame:04d}.png): a contact sheet's
    worth in one call. A multi-tick job."""
    import os
    out = []
    for f in frames:
        p = os.path.join(out_dir, f"{int(f):04d}.png")
        yield from seq_still(path, f, camera, p, width, height, settle)
        out.append(p)
    return out
