"""Speech to face: a voice file on the workstation becomes a MetaHuman facial animation (lip-sync, blinks, brows, head
movement), through MetaHuman Animator's audio solver with a chosen mood. Long recordings are solved in chunks cut in
pauses and stitched into one animation; a solve that fails is reported with what to do, and (unless told not to)
replaced by a loudness-driven lip flap so the shot still talks, flagged as a fallback."""
from __future__ import annotations

import os
import time

import unreal

from . import op
from .assets import EAL, free, import_files, load
from ..errors import OpError, closest, not_found
from ..perfkit import audio as AU

MOODS = [m for m in dir(unreal.AudioDrivenAnimationMood) if m.isupper()]


@op("speech.moods", mutates=False, idempotent=True)
def moods() -> list:
    """The audio solver's moods (AUTO_DETECT, CONFIDENCE, EXCITEMENT, HAPPINESS, ...).
    Example: film-ue op speech.moods
    """
    return MOODS


class SolveFailed(Exception):
    """The audio solver did not produce an animation (the reason in the message)."""


# MetaHuman Performance (UE 5.6+) audio options by their Python names (Epic's audio-driven animation docs; the plugin
# is not in the engine source, so each is set only if the asset has it, and what was missing is reported):
#   audio_driven_animation_output_controls  FULL_FACE | MOUTH_ONLY  ("Process Mask": mouth-only when perfkit owns the
#                                            eyes, brows and blinks)
#   head_movement_mode                       the solver's head motion; DISABLED when perfkit/the body owns the head
#   downmix_channels, audio_channel_index    a stereo file: mix down, or which channel
MASKS = {"full": "FULL_FACE", "mouth": "MOUTH_ONLY"}


def _set_enum(obj, prop: str, member: str) -> str | None:
    """Set an enum property by member name, the enum class taken from the property's current value (the plugin's enum
    names are not guessed). Returns the value set, or None when the object has no such property/member."""
    try:
        cur = obj.get_editor_property(prop)
    except Exception:
        return None
    val = getattr(type(cur), member, None)
    if val is None:
        return None
    obj.set_editor_property(prop, val)
    return member


def _enum_members(obj, prop: str) -> list:
    try:
        return [m for m in dir(type(obj.get_editor_property(prop))) if m.isupper()]
    except Exception:
        return []


def _solve(wav: str, name: str, face_mesh: str, mood: str, intensity: float, head: bool, blinks: bool,
           folder: str, timeout_s: float, process_mask: str = "full"):
    """One audio solve, multi-tick: import `wav`, run the performance's pipeline (non-blocking), export
    {folder}/Anim/AS_{name}. Raises SolveFailed with the reason; returns the result dict."""
    wave = import_files([wav], f"{folder}/Audio")[0].split(".")[0]
    perf_path = f"{folder}/Perf_{name}"
    free(perf_path)
    perf = unreal.AssetToolsHelpers.get_asset_tools().create_asset(f"Perf_{name}", folder, unreal.MetaHumanPerformance,
                                                                   unreal.MetaHumanPerformanceFactoryNew())
    if perf is None:
        raise SolveFailed(f"could not create the performance asset {perf_path}")
    perf.set_editor_property("input_type", unreal.DataInputType.AUDIO)
    perf.set_editor_property("audio", load(wave))
    so = perf.get_editor_property("audio_driven_animation_solve_overrides")
    so.set_editor_property("mood", getattr(unreal.AudioDrivenAnimationMood, mood))
    so.set_editor_property("mood_intensity", float(intensity))
    perf.set_editor_property("audio_driven_animation_solve_overrides", so)
    perf.set_editor_property("generate_blinks", bool(blinks))  # bGenerateBlinks
    options, missing = {"generate_blinks": bool(blinks)}, []
    got = _set_enum(perf, "audio_driven_animation_output_controls", MASKS[process_mask])
    if got:
        options["process_mask"] = got
    elif process_mask != "full":
        have = _enum_members(perf, "audio_driven_animation_output_controls")
        raise OpError("this MetaHuman plugin has no Process Mask (audio_driven_animation_output_controls: "
                      f"{have or 'no such property'}): a mouth-only solve needs UE 5.6+", code="unsupported",
                      hint="solve the full face (process_mask=full) and let lipsync.compose keep only the mouth")
    else:
        missing.append("audio_driven_animation_output_controls")
    if not head:
        got = _set_enum(perf, "head_movement_mode", "DISABLED")
        options["head_movement_mode"] = got or "export only"
        if not got:
            missing.append("head_movement_mode")
    perf.set_blocking_processing(False)  # across editor ticks: a blocking solve holds the game thread for minutes
    err = perf.start_pipeline(True)  # EStartPipelineErrorType: NONE, NO_FRAMES, DISABLED (MetaHumanPerformance.h:65)
    started = err == getattr(unreal.StartPipelineErrorType, "NONE", None) or str(err).upper().rstrip(">: 0").endswith("NONE")
    if not started:
        raise SolveFailed(f"the audio solve did not start ({err}): NO_FRAMES = the audio is empty or unreadable, "
                          "DISABLED = MetaHuman Animator's processing is unavailable (plugin, GPU or sign-in)")
    t0 = time.time()
    yield 0.5
    while perf.is_processing():
        if time.time() - t0 > timeout_s:
            perf.cancel_pipeline()
            raise SolveFailed(f"the audio solve of {os.path.basename(wav)} took over {timeout_s:.0f} s and was "
                              "cancelled")
        yield 0.5
    frames = perf.get_number_of_processed_frames()
    if not frames:
        raise SolveFailed("the audio solve processed no frames (see the editor log: film-ue log)")
    # the export asks "Overwrite Existing Object?" in a modal dialog (the game thread waits for a click) when the
    # animation exists: free the name first, deleting it, or moving it aside if something still holds it
    out = f"{folder}/Anim/AS_{name}"
    free(out)
    U = unreal.MetaHumanPerformanceExportUtils
    st = U.get_export_animation_sequence_settings(perf)  # the class default object: shared for the session
    dialog = st.get_editor_property("show_export_dialog")
    for k, v in (("package_path", f"{folder}/Anim"), ("asset_name", f"AS_{name}"), ("show_export_dialog", False),
                 ("enable_head_movement", head), ("export_range", unreal.PerformanceExportRange.WHOLE_SEQUENCE),
                 ("target_skeleton_or_skeletal_mesh", load(face_mesh))):
        st.set_editor_property(k, v)
    try:
        anim = U.export_animation_sequence(perf, st)
    finally:
        st.set_editor_property("show_export_dialog", dialog)  # leave the editor's own export as it was
    if anim is None:
        raise SolveFailed("the export produced no animation")
    EAL.save_asset(perf_path)
    seconds = float(unreal.AnimationLibrary.get_sequence_length(anim))
    return {"sound": wave, "performance": perf_path, "anim": anim.get_path_name().split(".")[0], "pipeline": str(err),
            "frames": frames, "seconds": seconds, "options": options, "missing_options": missing,
            "timing": timing(AU.Envelope.from_wav(wav).duration_s, seconds, frames)}


def timing(wav_s: float, anim_s: float, frames: int) -> dict:
    """The solve's timebase against its WAV: the animation must be as long as the audio (its t=0 is the WAV's first
    sample), at a whole frame rate. A different length means a trimmed/padded wave or a rate mismatch: every lip-sync
    placed from it would be off. {"wav_s", "anim_s", "fps", "ok", "why"?}"""
    fps = round(frames / anim_s, 3) if anim_s > 0 and frames else None
    out = {"wav_s": round(wav_s, 3), "anim_s": round(anim_s, 3), "fps": fps,
           "ok": abs(anim_s - wav_s) <= max(0.1, 2.0 / (fps or 30.0))}
    if not out["ok"]:
        out["why"] = (f"the animation is {anim_s:.2f} s for a {wav_s:.2f} s WAV: its t=0 may not be the WAV's first "
                      "sample (a processing range, a trimmed wave or a frame-rate mismatch); lipsync.check anim=... "
                      "wav=... measures the lag")
    return out


def _stitch(out: str, face_mesh: str, length_s: float, parts: list) -> None:
    """One animation at `out` from parts [(offset_s, curves {name: (times, values)})]: each part's keys shifted to its
    offset (the cuts are in pauses, so the mouth is closed at every seam)."""
    from .anim import _write, new as anim_new
    anim_new(path=out, skeleton=face_mesh, length_s=length_s, fps=30, replace=True)
    merged: dict = {}
    for off, cur in sorted(parts, key=lambda p: p[0]):
        for n, (t, v) in cur.items():
            tt, vv = merged.setdefault(n, ([], []))
            for x, y in zip(t, v):
                x = off + x
                if tt and x <= tt[-1]:
                    continue
                tt.append(x)
                vv.append(y)
    _write(load(out), merged)
    EAL.save_asset(out)


def _flap(env, length_s: float) -> dict:
    cur = AU.lip_flap(env)
    cur["HeadControlSwitch"] = ([0.0, length_s], [1.0, 1.0])
    return cur


@op("speech.to_face", mutates=True, idempotent=True, tags=["slow"])
def to_face(wav: str, name: str, face_mesh: str, mood: str = "CONFIDENCE", intensity: float = 1.0,
            head: bool = True, blinks: bool = True, folder: str = "/Game/Speech", max_chunk_s: float = 40.0,
            fallback: bool = True, timeout_s: float = 0.0, process_mask: str = "full"):
    """Import `wav` (a path on the workstation), solve it with MetaHuman Animator's audio solver in `mood` at
    `intensity`, and export an animation on `face_mesh`'s skeleton at {folder}/Anim/AS_{name}. A multi-tick job.
    Then make it alive with perf.face (head, eyes, blinks, brows over the lip-sync).

    Longer than `max_chunk_s` seconds: cut in pauses into chunks, each solved on its own (under {folder}/Chunks), and
    stitched into the one animation. `timeout_s` per solve (0 = 60 s + 20 x the audio's length). A solve that fails
    raises an OpError (code engine/timeout, with the reason) unless `fallback`: then that part becomes a lip flap
    driven by the voice's loudness and the result says {"fallback": true, "errors": [...]}: re-solve when the solver
    works.
    For a line whose face perfkit makes (head, eyes, blinks, brows): process_mask="mouth" head=false blinks=false,
    one solve per line WAV, then lipsync.compose places each at its cue and lipsync.check proves the timing.
    `timing` in the result: the animation's length against the WAV's (t=0 is the WAV's first sample; a mismatch is
    flagged). `options`: what was set on the performance; `missing_options`: what this plugin version lacks.
    Returns: {"sound", "performance", "anim", "pipeline", "frames", "seconds", "chunks", "fallback", "errors",
    "options", "timing"}.
    Example: film-ue op speech.to_face wav=/home/ue/Audio/line1.wav name=line1 face_mesh=/Game/MetaHumans/Ada/Face/Ada_FaceMesh mood=CONFIDENCE
    """
    if not os.path.exists(wav):
        raise not_found("WAV file", wav, hint="push it to the box first (client.push); the path is on the box")
    if not EAL.does_asset_exist(face_mesh.split(".")[0]):
        raise not_found("face mesh", face_mesh, hint="the MetaHuman's face SkeletalMesh (mh.components or assets.list)")
    if process_mask not in MASKS:
        raise OpError(f"process_mask {process_mask!r}", code="bad_args", hint="full or mouth")
    if MOODS and mood not in MOODS:
        raise OpError(f"unknown mood {mood!r}", code="bad_args", candidates=closest(mood, MOODS),
                      hint="speech.moods lists them")
    env = AU.Envelope.from_wav(wav)
    length = env.duration_s
    if length <= 0.05:
        raise OpError(f"{wav} holds no audio", code="bad_args")
    budget = timeout_s or (60.0 + 20.0 * min(length, max_chunk_s))
    cuts = AU.split_points(env, max_s=max_chunk_s)
    out = f"{folder}/Anim/AS_{name}"
    errors = []
    if not cuts:
        try:
            r = yield from _solve(wav, name, face_mesh, mood, intensity, head, blinks, folder, budget, process_mask)
            return {**r, "chunks": 1, "fallback": False, "errors": [], "changed": True}
        except SolveFailed as e:
            if not fallback:
                raise OpError(f"speech.to_face {name}: {e}", code="timeout" if "cancelled" in str(e) else "engine",
                              hint="retry, or pass fallback=true for a loudness lip flap; check the editor log") from None
            errors.append(str(e))
            _stitch(out, face_mesh, length, [(0.0, _flap(env, length))])
            return {"sound": None, "performance": None, "anim": out, "pipeline": None, "frames": 0, "seconds": length,
                    "chunks": 1, "fallback": True, "errors": errors, "changed": True}
    # long audio: chunks cut in pauses, each solved, stitched
    saved = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                         "fmbridge", "speech", name)
    os.makedirs(saved, exist_ok=True)
    bounds = [0.0] + cuts + [length]
    parts, frames, flapped = [], 0, 0
    from .anim import read_all
    for k, (a, b) in enumerate(zip(bounds, bounds[1:])):
        cw = AU.write_chunk(wav, os.path.join(saved, f"c{k:02d}.wav"), a, b)
        try:
            r = yield from _solve(cw, f"{name}_c{k:02d}", face_mesh, mood, intensity, head, blinks,
                                  f"{folder}/Chunks", budget, process_mask)
            parts.append((a, read_all(load(r["anim"]))))
            frames += r["frames"]
        except SolveFailed as e:
            if not fallback:
                raise OpError(f"speech.to_face {name}: chunk {k} ({a:.1f}-{b:.1f} s): {e}", code="engine",
                              hint="retry, or pass fallback=true; a smaller max_chunk_s may help") from None
            errors.append(f"chunk {k} ({a:.1f}-{b:.1f} s): {e}")
            parts.append((a, _flap(AU.Envelope.from_wav(cw), b - a)))
            flapped += 1
    _stitch(out, face_mesh, length, parts)
    wave = import_files([wav], f"{folder}/Audio")[0].split(".")[0]
    return {"sound": wave, "performance": None, "anim": out, "pipeline": "chunked", "frames": frames, "seconds": length,
            "chunks": len(bounds) - 1, "fallback": bool(flapped), "errors": errors, "changed": True}
