"""Mono video -> MetaHuman body + hands AnimSequence (+ FBX), inside the Windows editor (MetaHuman Animator
Markerless Motion Capture, UE 5.8, experimental). Body only: face tracking OFF, head movement OFF (our face pipeline
keeps the face; an Audio-to-Lip Sync anim on the Body track overrides markerless body/hands in 5.8.0, forum 2733267).

Runs once per job and quits the editor:

    UnrealEditor.exe C:/UEProjects/Mocap/Mocap.uproject -ExecutePythonScript="C:/mocap/ue_solve.py C:/mocap/job.json"

job.json (paths with forward slashes):
    {"video": "C:/mocap/in/take01.mp4", "slate": "take01", "take": 1,
     "target": "/Game/MetaHumans/Common/Female/Medium/NormalWeight/Body/metahuman_base_skel",
     "folder": "/Game/Mocap", "fbx_dir": "C:/mocap/out", "timeout_s": 7200, "quit": true}

Writes <fbx_dir>/<slate>.result.json: {"ok", "anim", "fbx", "frames", "seconds", "solve_s", "ingest_s", "error"?}.
Property names follow Epic's Blueprint page (InputType=MonoFootage, FootageCaptureData, bBodyTracking,
bFaceTracking, SetBlockingProcessing, StartPipeline, MetaHumanPerformanceExportUtils) and our audio solve
(unreal/fmbridge/ops/speech.py). The plugin's own sample, Content/Python/process_monocular_performance.py, is the
reference when a name here fails: the error lists what the object does have.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

import unreal

EAL = unreal.EditorAssetLibrary


def _enum(obj, prop: str, member: str) -> bool:
    """Set an enum property by member name, the enum class taken from its current value (names not guessed)."""
    try:
        cur = obj.get_editor_property(prop)
    except Exception:
        return False
    val = getattr(type(cur), member, None)
    if val is None:
        raise RuntimeError(f"{prop} has no {member}: {[m for m in dir(type(cur)) if m.isupper()]}")
    obj.set_editor_property(prop, val)
    return True


def _set(obj, prop: str, val) -> None:
    try:
        obj.set_editor_property(prop, val)
    except Exception as e:
        have = [p for p in dir(obj) if not p.startswith("_")]
        raise RuntimeError(f"{type(obj).__name__}.{prop}: {e}; it has {have[:80]}") from e


def ingest(job: dict):
    """The video -> a Footage Capture Data asset (Capture Manager's Mono Video Ingest, no calibration)."""
    lib = getattr(unreal, "CaptureManagerIngestBlueprintLibrary", None)
    if lib is None:
        raise RuntimeError("no CaptureManagerIngestBlueprintLibrary: enable the Capture Manager Editor plugin")
    params = unreal.CaptureManagerConversionParams()
    out = lib.ingest_mono_video_sync(video_file_path=job["video"], audio_file_path="", slate=job["slate"],
                                     take_number=int(job.get("take", 1)), params=params)
    footage, err = out if isinstance(out, tuple) else (out, None)
    if footage is None:
        raise RuntimeError(f"ingest failed: {err} (forum fixes: unique file name, CFR video, PixelFormat U8_Mono, "
                           "Settings > Use Third Party Encoder)")
    return footage


def solve(job: dict, footage):
    folder = job.get("folder", "/Game/Mocap")
    name = f"MHP_{job['slate']}"
    if EAL.does_asset_exist(f"{folder}/{name}"):
        EAL.delete_asset(f"{folder}/{name}")
    perf = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.MetaHumanPerformance,
                                                                   unreal.MetaHumanPerformanceFactoryNew())
    if perf is None:
        raise RuntimeError(f"could not create {folder}/{name}")
    _enum(perf, "input_type", "MONO_FOOTAGE")
    _set(perf, "footage_capture_data", footage)
    _set(perf, "body_tracking", True)  # no effect unless the Markerless plugin is enabled (Epic's note)
    _set(perf, "face_tracking", False)
    _enum(perf, "head_movement_mode", "DISABLED")
    perf.set_blocking_processing(True)  # a batch job: holding the game thread is fine
    err = perf.start_pipeline(True)
    if not str(err).upper().rstrip(">: 0").endswith("NONE"):
        raise RuntimeError(f"the solve did not start ({err}): NO_FRAMES = unreadable footage, DISABLED = the "
                           "plugin, the GPU (DX12 default RHI) or a missing Body Tracking option")
    t0 = time.time()
    while perf.is_processing():  # blocking returns when done; this covers a build where it does not
        if time.time() - t0 > float(job.get("timeout_s", 7200)):
            perf.cancel_pipeline()
            raise RuntimeError("the solve timed out and was cancelled")
        time.sleep(1.0)
    frames = perf.get_number_of_processed_frames()
    if not frames:
        raise RuntimeError("the solve processed no frames (see Saved/Logs)")
    EAL.save_asset(f"{folder}/{name}")
    return perf, frames, time.time() - t0


def export(job: dict, perf):
    folder = job.get("folder", "/Game/Mocap")
    asset = f"AS_{job['slate']}"
    if EAL.does_asset_exist(f"{folder}/Anim/{asset}"):
        EAL.delete_asset(f"{folder}/Anim/{asset}")  # else a modal 'Overwrite?' dialog waits for a click
    U = unreal.MetaHumanPerformanceExportUtils
    st = U.get_export_animation_sequence_settings(perf)
    for k, v in (("package_path", f"{folder}/Anim"), ("asset_name", asset), ("show_export_dialog", False),
                 ("target_skeleton_or_skeletal_mesh", unreal.load_asset(job["target"]))):
        _set(st, k, v)
    anim = U.export_animation_sequence(perf, st)
    if anim is None:
        raise RuntimeError("the export produced no animation")
    EAL.save_asset(anim.get_path_name())
    fbx = f"{job['fbx_dir'].rstrip('/')}/{job['slate']}.fbx"
    os.makedirs(job["fbx_dir"], exist_ok=True)
    t = unreal.AssetExportTask()
    t.object, t.filename, t.automated, t.prompt, t.replace_identical = anim, fbx, True, False, True
    t.exporter = unreal.AnimSequenceExporterFBX()
    if not unreal.Exporter.run_asset_export_task(t):
        raise RuntimeError(f"the FBX export to {fbx} failed")
    return anim, fbx


def main(path: str) -> dict:
    job = json.load(open(path))
    res = {"ok": False, "job": job}
    try:
        t0 = time.time()
        footage = ingest(job)
        res["ingest_s"] = round(time.time() - t0, 1)
        perf, frames, solve_s = solve(job, footage)
        anim, fbx = export(job, perf)
        secs = float(unreal.AnimationLibrary.get_sequence_length(anim))
        res.update(ok=True, anim=anim.get_path_name().split(".")[0], fbx=fbx, frames=frames, seconds=round(secs, 3),
                   solve_s=round(solve_s, 1), solve_s_per_video_s=round(solve_s / secs, 1) if secs else None)
    except Exception as e:
        res["error"] = f"{e}\n{traceback.format_exc()[-1500:]}"
    out = f"{job['fbx_dir'].rstrip('/')}/{job['slate']}.result.json"
    os.makedirs(job["fbx_dir"], exist_ok=True)
    json.dump(res, open(out, "w"), indent=1)
    unreal.log(f"mocap ue_solve: {out} ok={res['ok']}")
    if job.get("quit", True):
        unreal.SystemLibrary.quit_editor()
    return res


if __name__ == "__main__":
    main(sys.argv[1])
