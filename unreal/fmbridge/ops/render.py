"""Renders with Movie Render Queue, in the editor (PIE executor): image sequences plus the mixed audio, deferred
(Lumen) or path-traced, with temporal/spatial samples and console variables for quality."""
from __future__ import annotations

import os

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
        warmup: int = 32, name: str = "shot", start: int | None = None, end: int | None = None) -> dict:
    """Start a Movie Render Queue job (returns at once; poll render.progress). Frames go to `out_dir` as
    {frame}.png|exr|jpg, the audio as a wav; `start`/`end` (end exclusive) render part of the sequence."""
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
    mq.render_queue_with_executor(unreal.MoviePipelinePIEExecutor)
    return {"out_dir": out_dir, "started": True}


@op("render.progress")
def progress(out_dir: str, expected: int = 0) -> dict:
    """Frames written so far (and whether Movie Render Queue is still running)."""
    files = [f for f in os.listdir(out_dir) if f.lower().endswith((".png", ".exr", ".jpg", ".jpeg"))] if os.path.isdir(out_dir) else []
    rendering = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem).is_rendering()
    return {"frames": len(files), "expected": expected, "rendering": rendering, "done": not rendering and len(files) > 0}
