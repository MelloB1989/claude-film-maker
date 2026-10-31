"""Speech to face: a voice file on the workstation becomes a MetaHuman facial animation (lip-sync, blinks, brows, head
movement), through MetaHuman Animator's audio solver with a chosen mood."""
from __future__ import annotations

import unreal

from . import op
from .assets import EAL, import_files, load

MOODS = [m for m in dir(unreal.AudioDrivenAnimationMood) if m.isupper()]


@op("speech.moods")
def moods() -> list:
    """The audio solver's moods (AUTO_DETECT, CONFIDENCE, EXCITEMENT, HAPPINESS, ...)."""
    return MOODS


@op("speech.to_face")
def to_face(wav: str, name: str, face_mesh: str, mood: str = "CONFIDENCE", intensity: float = 1.0,
            head: bool = True, blinks: bool = True, folder: str = "/Game/Speech") -> dict:
    """Import `wav` (a path on the workstation), solve it with MetaHuman Animator's audio solver in `mood` at
    `intensity`, and export an animation on `face_mesh`'s skeleton. Returns the sound, performance and animation."""
    wave = import_files([wav], f"{folder}/Audio")[0].split(".")[0]
    perf_path = f"{folder}/Perf_{name}"
    if EAL.does_asset_exist(perf_path):
        EAL.delete_asset(perf_path)
    perf = unreal.AssetToolsHelpers.get_asset_tools().create_asset(f"Perf_{name}", folder, unreal.MetaHumanPerformance,
                                                                   unreal.MetaHumanPerformanceFactoryNew())
    perf.set_editor_property("input_type", unreal.DataInputType.AUDIO)
    perf.set_editor_property("audio", load(wave))
    so = perf.get_editor_property("audio_driven_animation_solve_overrides")
    so.set_editor_property("mood", getattr(unreal.AudioDrivenAnimationMood, mood))
    so.set_editor_property("mood_intensity", float(intensity))
    perf.set_editor_property("audio_driven_animation_solve_overrides", so)
    for k, v in (("generate_blinks", blinks), ("enable_head_movement", head)):
        try:
            perf.set_editor_property(k, v)
        except Exception:
            pass
    perf.set_blocking_processing(True)
    err = perf.start_pipeline(True)
    U = unreal.MetaHumanPerformanceExportUtils
    st = U.get_export_animation_sequence_settings(perf)
    for k, v in (("package_path", f"{folder}/Anim"), ("asset_name", f"AS_{name}"), ("show_export_dialog", False),
                 ("enable_head_movement", head), ("export_range", unreal.PerformanceExportRange.WHOLE_SEQUENCE),
                 ("target_skeleton_or_skeletal_mesh", load(face_mesh))):
        st.set_editor_property(k, v)
    anim = U.export_animation_sequence(perf, st)
    EAL.save_asset(perf_path)
    return {"sound": wave, "performance": perf_path, "anim": anim.get_path_name().split(".")[0] if anim else None,
            "pipeline": str(err), "frames": perf.get_number_of_processed_frames(),
            "seconds": anim.get_editor_property("sequence_length") if anim else 0}
