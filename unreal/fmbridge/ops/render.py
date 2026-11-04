"""Renders with Movie Render Queue: image sequences plus the mixed audio, deferred (Lumen) or path-traced, with
temporal/spatial samples and console variables for quality. In the editor (PIE executor), or in a separate game
process the editor starts (`executor="process"`): a crash there does not take the editor down, and the editor is free
for the next shot while it renders."""
from __future__ import annotations

import os
import sys

import unreal

from . import op

QUALITY_CVARS = {  # Lumen and shadows at film quality for a final
    "r.Lumen.ScreenProbeGather.DownsampleFactor": 8, "r.Lumen.ScreenProbeGather.TracingOctahedronResolution": 16,
    "r.Lumen.Reflections.DownsampleFactor": 1, "r.Lumen.TranslucencyReflections.FrontLayer.Enable": 1,
    "r.Shadow.Virtual.SMRT.RayCountDirectional": 16, "r.Shadow.Virtual.SMRT.SamplesPerRayDirectional": 16,
    "r.Shadow.Virtual.SMRT.RayCountLocal": 16, "r.Shadow.Virtual.SMRT.SamplesPerRayLocal": 16,
    "r.HairStrands.Visibility.MSAA.SamplePerPixel": 8, "r.DepthOfFieldQuality": 4, "r.MotionBlurQuality": 4,
    "r.Tonemapper.Sharpen": 0.5, "r.ScreenPercentage": 100,
}


@op("render.mrq")
def mrq(sequence: str, level: str, out_dir: str, width: int = 1920, height: int = 1080, temporal: int = 8,
        spatial: int = 1, path_tracer: bool = False, quality: bool = True, cvars: dict | None = None, fmt: str = "png",
        warmup: int = 32, name: str = "shot", start: int | None = None, end: int | None = None,
        executor: str = "pie") -> dict:
    """Start a Movie Render Queue job (returns at once; poll render.progress). Frames go to `out_dir` as
    {frame}.png|exr|jpg, the audio as a wav; `start`/`end` (end exclusive) render part of the sequence. `executor`:
    "pie" (in this editor) or "process" (a separate -game process; offscreen where the editor has no desktop)."""
    mq = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    if mq.is_rendering():
        raise RuntimeError("a render is already running")
    q = mq.get_queue()
    q.delete_all_jobs()
    job = q.allocate_new_job(unreal.MoviePipelineExecutorJob)
    job.sequence = unreal.SoftObjectPath(sequence)
    job.map = unreal.SoftObjectPath(level)
    job.job_name = name
    cfg = job.get_configuration()
    o = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
    o.output_directory = unreal.DirectoryPath(out_dir)
    o.output_resolution = unreal.IntPoint(width, height)
    o.file_name_format = "{frame_number}"
    o.zero_pad_frame_numbers = 4
    if start is not None or end is not None:
        seq = unreal.load_asset(sequence)
        o.use_custom_playback_range = True
        o.custom_start_frame = seq.get_playback_start() if start is None else int(start)
        o.custom_end_frame = seq.get_playback_end() if end is None else int(end)
    cfg.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPass_PathTracer if path_tracer else unreal.MoviePipelineDeferredPassBase)
    cfg.find_or_add_setting_by_class({"png": unreal.MoviePipelineImageSequenceOutput_PNG, "exr": unreal.MoviePipelineImageSequenceOutput_EXR,
                                      "jpg": unreal.MoviePipelineImageSequenceOutput_JPG}[fmt])
    cfg.find_or_add_setting_by_class(unreal.MoviePipelineWaveOutput)
    aa = cfg.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
    aa.spatial_sample_count, aa.temporal_sample_count = spatial, temporal
    aa.engine_warm_up_count = aa.render_warm_up_count = warmup
    cv = dict(QUALITY_CVARS if quality else {})
    cv.update(cvars or {})
    if cv:
        cvs = cfg.find_or_add_setting_by_class(unreal.MoviePipelineConsoleVariableSetting)
        for k, v in cv.items():
            cvs.add_or_update_console_variable(k, float(v))
    os.makedirs(out_dir, exist_ok=True)
    if executor == "process":
        _offscreen_child()
        mq.render_queue_with_executor(unreal.MoviePipelineNewProcessExecutor)
    elif executor == "pie":
        mq.render_queue_with_executor(unreal.MoviePipelinePIEExecutor)
    else:
        raise ValueError(f"executor {executor!r}: pie or process")
    return {"out_dir": out_dir, "started": True, "executor": executor}


def _offscreen_child():
    """The new-process executor starts the game with the project's 'Additional Command Line Arguments' (Project
    Settings > Movie Render Pipeline): with no desktop it must render offscreen too."""
    if sys.platform == "win32":
        return
    st = unreal.get_default_object(unreal.MoviePipelineInProcessExecutorSettings)
    args = st.get_editor_property("additional_command_line_arguments") or ""
    if "-RenderOffscreen" not in args:
        st.set_editor_property("additional_command_line_arguments", (args + " -RenderOffscreen").strip())


@op("render.progress")
def progress(out_dir: str, expected: int = 0) -> dict:
    """Frames written so far (and whether Movie Render Queue is still running)."""
    files = [f for f in os.listdir(out_dir) if f.lower().endswith((".png", ".exr", ".jpg", ".jpeg"))] if os.path.isdir(out_dir) else []
    rendering = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem).is_rendering()
    return {"frames": len(files), "expected": expected, "rendering": rendering, "done": not rendering and len(files) > 0}
