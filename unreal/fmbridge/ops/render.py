"""Rendering with Movie Render Queue, driven by a RENDER SPEC (fmbridge/render_spec.py; docs/unreal/render.md):
presets (preview, draft, final, final_exr, 4k, pathtrace), image sequences (PNG, JPG, 16-bit EXR) plus the WAV, AOVs
(depth, motion vectors, lighting passes, object IDs), anti-aliasing samples and warm-up, console variables, chunks
per camera cut that resume where a render stopped and are pre-rolled from the shot start (cloth), three executors
(in this editor, a separate process the editor watches, or a manifest + command line for a process with no editor),
a JSON report per job (time per frame, VRAM, errors), H.264/ProRes encodes with ffmpeg, and per-frame QA.

The one entry point for a whole job is `render.job` (multi-tick: poll the job id, or `render.status`). `render.mrq`
and `render.progress` are the older start-and-poll pair (kept: films call them); `render.frames` renders a few frames
for stills."""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import time

import unreal

from . import op
from .. import render_spec as rs
from ..errors import OpError

QUALITY_CVARS = rs.QUALITY_CVARS  # older callers import it from here

_RUN: dict = {"status": "idle"}  # the job in progress (or the last one): render.status reads it
_GPU_CACHE: dict = {"t": 0.0, "v": None}


# ---------------------------------------------------------------------------------------------------------------------
# small engine helpers

def _mq():
    return unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)


def _pkg(path: str) -> str:
    """Package path of an asset path (/Game/A/B.B -> /Game/A/B)."""
    return str(path).split(".", 1)[0] if "." in str(path).rsplit("/", 1)[-1] else str(path)


def _obj(path: str) -> str:
    """Object path of an asset path (/Game/A/B -> /Game/A/B.B)."""
    p = _pkg(path)
    return f"{p}.{p.rsplit('/', 1)[-1]}"


def _load_sequence(path: str):
    seq = unreal.load_asset(_pkg(path))
    if seq is None:
        raise OpError(f"no level sequence {path!r}", code="not_found",
                      hint="list them with assets.list path=/Game cls=LevelSequence")
    return seq


def _fps(seq) -> float:
    r = seq.get_display_rate()
    return float(r.numerator) / float(r.denominator or 1)


def _cuts(path: str, seq) -> list:
    """[[camera label, start, end], ...] in order; [] when the sequence has no camera cut track."""
    try:
        from . import seq as seqops
        return [list(c) for c in seqops.cuts(path)]
    except OpError:
        raise
    except Exception:
        out = []
        for t in seq.find_tracks_by_type(unreal.MovieSceneCameraCutTrack):
            for i, s in enumerate(t.get_sections()):
                out.append([f"cut{i}", int(s.get_start_frame()), int(s.get_end_frame())])
        return sorted(out, key=lambda c: c[1])


def _editor_level() -> str:
    try:
        w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        return _pkg(w.get_path_name()) if w else ""
    except Exception:
        return ""


def _dirty_packages() -> list:
    lib = unreal.EditorLoadingAndSavingUtils
    return [p.get_name() for p in list(lib.get_dirty_map_packages()) + list(lib.get_dirty_content_packages())]


def _walk(root: str) -> list:
    out = []
    for d, _, files in os.walk(root):
        rel = os.path.relpath(d, root)
        if rel.split(os.sep)[0] == "_render":
            continue
        out.extend(f if rel == "." else os.path.join(rel, f).replace("\\", "/") for f in files)
    return out


def _valid(path: str) -> bool:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(8)
            f.seek(max(0, size - 16))
            tail = f.read(16)
        return rs.image_ok(head, tail, size)
    except OSError:
        return False


def _done_frames(r: dict, check: bool = True) -> set:
    """Beauty frames on disk that are complete (a frame cut off by a crash is dropped, so it renders again)."""
    if not os.path.isdir(r["out_dir"]):
        return set()
    have = rs.frames_on_disk(r, _walk(r["out_dir"]))
    return {f for f in have if not check or _valid(rs.frame_path(r, f))}


def _seq_state(r: dict, with_done: bool = True) -> dict:
    seq = _load_sequence(r["sequence"])
    st = {"playback": [int(seq.get_playback_start()), int(seq.get_playback_end())], "fps": _fps(seq),
          "cuts": _cuts(r["sequence"], seq)}
    if with_done:
        st["done"] = sorted(_done_frames(r))
    cal = _calibration(r)
    if cal:
        st["calibration"] = cal
    return st


def _report_path(r: dict) -> str:
    return os.path.join(r["out_dir"], "_render", f"{r['name']}.report.json")


def _calibration(r: dict) -> dict:
    """Measured seconds per sample from this job's last report, if it ran with the same renderer."""
    try:
        with open(_report_path(r)) as f:
            rep = json.load(f)
        m = rep.get("measured") or {}
        key = "pt_sample_s_1080p" if r["path_tracer"] else "sample_s_1080p"
        return {key: m["sample_s_1080p"]} if m.get("sample_s_1080p") and rep.get("path_tracer") == r["path_tracer"] else {}
    except (OSError, ValueError, KeyError):
        return {}


def _resolve(spec: dict) -> dict:
    try:
        return rs.resolve(spec)
    except rs.SpecError as e:
        raise OpError("render spec: " + "; ".join(e.errors), code="bad_args", details={"errors": e.errors},
                      hint="film-ue render presets and film-ue render schema show the fields (docs/unreal/render.md)") from None


# ---------------------------------------------------------------------------------------------------------------------
# GPU

def gpu_info(max_age_s: float = 2.0) -> dict | None:
    """The first NVIDIA GPU's memory (nvidia-smi), cached for max_age_s; None where there is no nvidia-smi."""
    now = time.time()
    if now - _GPU_CACHE["t"] < max_age_s:
        return _GPU_CACHE["v"]
    v = None
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # CREATE_NO_WINDOW
            out = subprocess.run([exe] + rs.NVIDIA_SMI_ARGS[1:], capture_output=True, text=True, timeout=3, **kw).stdout
            v = rs.parse_nvidia_smi(out)
        except (OSError, subprocess.SubprocessError):
            v = None
    _GPU_CACHE.update(t=now, v=v)
    return v


def _rss_gb() -> float | None:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) * 1024 / 1e9, 2)
    except OSError:
        pass
    return None


@op("render.gpu", mutates=False, idempotent=True, tags=["gpu"])
def gpu() -> dict:
    """The render box's GPU and memory now: name, VRAM total/used/free in GB, utilisation, and the editor's RSS.

    Returns: {"gpu": {"name", "total_gb", "used_gb", "free_gb", "util_pct"} | None, "rss_gb", "rendering": bool}.
    Example: film-ue op render.gpu
    """
    return {"gpu": gpu_info(0), "rss_gb": _rss_gb(), "rendering": bool(_mq().is_rendering())}


# ---------------------------------------------------------------------------------------------------------------------
# configuring an MRQ job from a resolved spec

def _setting(cfg, cls_name: str, exact: bool = True):
    cls = getattr(unreal, cls_name)
    return cfg.find_or_add_setting_by_class(cls, False, exact)


_AA = {"none": "AAM_NONE", "fxaa": "AAM_FXAA", "taa": "AAM_TEMPORAL_AA", "msaa": "AAM_MSAA", "tsr": "AAM_TSR",
       "smaa": "AAM_SMAA"}


_GAME_OVERRIDES = {"cinematic_quality": "cinematic_quality_settings", "texture_streaming": "texture_streaming",
                   "lod_zero": "use_lod_zero", "disable_hlods": "disable_hlods",
                   "high_quality_shadows": "use_high_quality_shadows", "shadow_distance_scale": "shadow_distance_scale",
                   "view_distance_scale": "view_distance_scale", "flush_streaming": "flush_streaming_managers"}


def _configure(job, r: dict, chunk: dict) -> None:
    """Fill a queue job's legacy (preset) configuration from a resolved spec and one chunk."""
    try:
        job.set_config_mode(unreal.MoviePipelineConfigMode.PRESET)
    except Exception:
        pass  # older engines have only the preset mode
    cfg = job.get_configuration()
    o = _setting(cfg, "MoviePipelineOutputSetting")
    o.set_editor_property("output_directory", unreal.DirectoryPath(r["out_dir"]))
    o.set_editor_property("output_resolution", unreal.IntPoint(r["width"], r["height"]))
    o.set_editor_property("file_name_format", r["file_name"])
    o.set_editor_property("zero_pad_frame_numbers", r["zero_pad"])
    o.set_editor_property("override_existing_output", True)
    o.set_editor_property("handle_frame_count", 0)
    o.set_editor_property("use_custom_playback_range", True)
    o.set_editor_property("custom_start_frame", int(chunk["start"]))
    o.set_editor_property("custom_end_frame", int(chunk["end"]))

    main = _setting(cfg, "MoviePipelineDeferredPass_PathTracer" if r["path_tracer"] else "MoviePipelineDeferredPassBase")
    ppm = [rs.PASSES[p][1] for p in r["passes"] if rs.PASSES[p][0] == "ppm"]
    if ppm:
        passes = list(main.get_editor_property("additional_post_process_materials") or [])
        for want in ppm:
            hit = [p for p in passes if want.split(".")[0] in str(p.get_editor_property("material"))]
            if not hit:
                p = unreal.MoviePipelinePostProcessPass()
                p.set_editor_property("material", unreal.load_asset(want.split(".")[0]))
                passes.append(p)
                hit = [p]
            for p in hit:
                p.set_editor_property("enabled", True)
                if "WorldDepth" in want:
                    p.set_editor_property("high_precision_output", True)
                    p.set_editor_property("use_lossless_compression", True)
        main.set_editor_property("additional_post_process_materials", passes)
    for p in r["passes"]:
        if rs.PASSES[p][0] == "class":
            _setting(cfg, rs.PASSES[p][1])

    for out in r["outputs"]:
        k = out["kind"]
        if k == "png":
            s = _setting(cfg, "MoviePipelineImageSequenceOutput_PNG")
            s.set_editor_property("write_alpha", bool(out.get("alpha", False)))
        elif k == "jpg":
            _setting(cfg, "MoviePipelineImageSequenceOutput_JPG")
        elif k == "bmp":
            _setting(cfg, "MoviePipelineImageSequenceOutput_BMP")
        elif k == "exr":
            s = _setting(cfg, "MoviePipelineImageSequenceOutput_EXR")
            s.set_editor_property("compression", getattr(unreal.EXRCompressionFormat, out.get("compression", "piz").upper()))
            s.set_editor_property("multilayer", bool(out.get("multilayer", False)))
        elif k == "wav":
            s = _setting(cfg, "MoviePipelineWaveOutput")
            s.set_editor_property("file_name_format_override", f"_render/audio/{chunk['start']}-{chunk['end']}")

    aa = _setting(cfg, "MoviePipelineAntiAliasingSetting")
    aa.set_editor_property("spatial_sample_count", r["spatial"])
    aa.set_editor_property("temporal_sample_count", r["temporal"])
    aa.set_editor_property("render_warm_up_count", r["warmup_render"])
    aa.set_editor_property("engine_warm_up_count", r["warmup_engine"])
    # Pre-roll: the camera cut's frames before the chunk are evaluated one by one, nothing rendered (cloth settles
    # as in a full-shot render). With no excess cut MRQ warns and uses engine_warm_up_count.
    aa.set_editor_property("use_camera_cut_for_warm_up", bool(chunk.get("preroll")))
    if r["aa_method"]:
        aa.set_editor_property("override_anti_aliasing", True)
        aa.set_editor_property("anti_aliasing_method", getattr(unreal.AntiAliasingMethod, _AA[r["aa_method"]]))

    go = r.get("game_overrides")
    if go:  # absent: MRQ's transient Game Overrides apply with their defaults, as in every earlier render
        g = _setting(cfg, "MoviePipelineGameOverrideSetting")
        for key, prop in _GAME_OVERRIDES.items():
            if key in go:
                v = go[key]
                if key == "texture_streaming":
                    v = getattr(unreal.MoviePipelineTextureStreamingMethod, v.upper())
                g.set_editor_property(prop, v)
        if "view_distance_scale" in go:
            g.set_editor_property("override_view_distance_scale", True)

    cvs = _setting(cfg, "MoviePipelineConsoleVariableSetting")
    for name, value in r["cvars"].items():
        cvs.add_or_update_console_variable(name, float(value))


def _new_job(r: dict, chunk: dict, level: str):
    q = _mq().get_queue()
    q.delete_all_jobs()
    job = q.allocate_new_job(unreal.MoviePipelineExecutorJob)
    # Full object paths (/Game/A/B.B): MRQ's {sequence_name}/{level_name} tokens and its current-map check read the
    # asset name. set_editor_property runs PostEditChangeProperty, which calls the SetSequence setter (Python cannot
    # call a BlueprintSetter directly: PyGenUtil.cpp:1620; MoviePipelineQueue.cpp:185-193).
    job.set_editor_property("sequence", unreal.SoftObjectPath(_obj(r["sequence"])))
    job.set_editor_property("map", unreal.SoftObjectPath(_obj(level)))
    job.set_editor_property("job_name", chunk.get("id") or r["name"])
    _configure(job, r, chunk)
    return q, job


def _check_level(r: dict) -> str:
    """The map to render: the spec's, else the open one; it must exist on disk (MRQ refuses an unsaved map, and
    offscreen it says nothing)."""
    level = _pkg(r["level"]) if r["level"] else _editor_level()
    if not level or not unreal.EditorAssetLibrary.does_asset_exist(level):
        raise OpError(f"level {level or '(none open)'!r} is not saved on disk: MRQ renders only a saved map",
                      code="conflict", hint="save it first with level.save, or pass level=/Game/... of a saved map")
    return level


def _save_first(save: bool) -> list:
    """The new-process executor loads from disk and asks to save dirty packages first: unattended, nobody answers and
    the job never starts (docs/linux/engine.md P3). So save them here, or refuse."""
    dirty = _dirty_packages()
    if dirty and not save:
        raise OpError(f"unsaved packages {dirty}: a separate process renders what is on disk and would wait on a save "
                      "prompt", code="conflict", hint="pass save_dirty=true, save with level.save, or use executor pie")
    if dirty:
        if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
            raise OpError(f"saving {dirty} failed", code="engine", hint="see film-ue log")
    return dirty


def _offscreen_child():
    """The new-process executor starts the game with the project's 'Additional Command Line Arguments' (Project
    Settings > Movie Render Pipeline): with no desktop it must render offscreen too."""
    if sys.platform == "win32":
        return
    st = unreal.get_default_object(unreal.MoviePipelineInProcessExecutorSettings)
    args = st.get_editor_property("additional_command_line_arguments") or ""
    if "-RenderOffscreen" not in args:
        st.set_editor_property("additional_command_line_arguments", (args + " -RenderOffscreen").strip())


# ---------------------------------------------------------------------------------------------------------------------
# running chunks

def _editor_binary() -> str:
    eng = unreal.Paths.convert_relative_path_to_full(unreal.Paths.engine_dir())
    if sys.platform == "win32":
        return os.path.join(eng, "Binaries", "Win64", "UnrealEditor-Cmd.exe")
    return os.path.join(eng, "Binaries", "Linux", "UnrealEditor")


def _write_manifest(q, path: str) -> str:
    res = unreal.MoviePipelineEditorBlueprintLibrary.save_queue_to_manifest_file(q)
    src = res[1] if isinstance(res, tuple) else res
    if not src or not os.path.isfile(str(src)):
        raise OpError("MRQ wrote no queue manifest", code="engine", hint="see film-ue log (LogMovieRenderPipeline)")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.copyfile(str(src), path)
    return path


def _sample(rec: dict, r: dict, chunk: dict, seen: dict) -> None:
    """Note new frames (with their file times), VRAM and RSS."""
    now = time.time()
    for f in rs.frames_on_disk(r, _walk(r["out_dir"])) if os.path.isdir(r["out_dir"]) else ():
        if chunk["start"] <= f < chunk["end"] and f not in seen:
            try:
                seen[f] = os.path.getmtime(rs.frame_path(r, f))
            except OSError:
                pass
    g = gpu_info()
    if g:
        rec["vram"].append([round(now - rec["t0"], 1), g["used_gb"]])
        rec["vram_peak_gb"] = max(rec.get("vram_peak_gb") or 0, g["used_gb"])
    rss = _rss_gb()
    if rss is not None:
        rec["rss_peak_gb"] = max(rec.get("rss_peak_gb") or 0, rss)


def _run_chunk(r: dict, chunk: dict, level: str, stall_s: float):
    """Render one chunk (multi-tick); returns its record. Never raises for a failed render: the record says why."""
    mq = _mq()
    if mq.is_rendering():
        raise OpError("a render is already running", code="conflict", hint="wait (render.status) or render.cancel")
    rec = {"id": chunk["id"], "camera": chunk["camera"], "start": chunk["start"], "end": chunk["end"],
           "preroll": chunk["preroll"], "status": "running", "errors": [], "vram": [], "t0": time.time()}
    _RUN.update(chunk=chunk["id"], chunk_rec=rec)
    q, job = _new_job(r, chunk, level)
    errors = rec["errors"]
    proc = None
    if r["executor"] == "cmdline":
        manifest = _write_manifest(q, os.path.join(r["out_dir"], "_render", f"{chunk['id']}.utxt"))
        log = os.path.join(r["out_dir"], "_render", f"{chunk['id']}.log")
        argv = rs.cmdline(_editor_binary(), unreal.Paths.get_project_file_path(), manifest, log=log)
        rec.update(manifest=manifest, argv=argv, log=log)
        q.delete_all_jobs()
        kw = {"creationflags": 0x00000200} if sys.platform == "win32" else {"start_new_session": True}
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        except OSError as e:
            rec.update(status="failed", errors=[f"could not start {argv[0]}: {e}"])
            return rec
        _RUN["proc"] = proc
        rec["pid"] = proc.pid
    else:
        cls = unreal.MoviePipelineNewProcessExecutor if r["executor"] == "process" else unreal.MoviePipelinePIEExecutor
        exe = mq.render_queue_with_executor(cls)
        if exe is None:
            rec.update(status="failed", errors=["MRQ refused to start the queue"])
            return rec
        _RUN["executor"] = exe
        try:
            exe.on_executor_errored_delegate.add_callable(
                lambda exe_, pipeline, fatal, text: errors.append(("fatal: " if fatal else "") + (str(text) or "MRQ error")))
        except Exception:
            pass
    seen: dict = {}
    last_new, started = time.time(), False
    while True:
        done = _RUN.get("frames_done", 0) + len(seen)
        total = max(1, _RUN.get("frames_total") or (chunk["end"] - chunk["start"]))
        yield {"progress": round(min(1.0, done / total), 3), "wait": 0.5,
               "message": f"{chunk['id']} ({chunk['camera']}): frame {chunk['start'] + len(seen)} of "
                          f"[{chunk['start']}, {chunk['end']}); {done}/{total} frames"}
        _sample(rec, r, chunk, seen)
        if len(seen) > rec.get("_n", 0):
            rec["_n"], last_new = len(seen), time.time()
        busy = proc.poll() is None if proc else bool(mq.is_rendering())
        started = started or busy or bool(seen)
        if _RUN.get("cancel"):
            _cancel_now()
            rec["status"] = "cancelled"
            break
        abort = r["vram"]["abort_pct"]
        g = gpu_info()
        if busy and abort and g and g["total_gb"] and 100 * g["used_gb"] / g["total_gb"] >= abort:
            _cancel_now()
            errors.append(f"VRAM {g['used_gb']:.1f} of {g['total_gb']:.1f} GB (>= {abort:g}%): cancelled before the "
                          "driver runs out and the editor dies; lower the resolution/samples or use a bigger GPU")
            rec["status"] = "vram_abort"
            break
        if busy and time.time() - last_new > stall_s:
            _cancel_now()
            errors.append(f"no new frame for {stall_s:.0f} s: cancelled (a dialog nobody answers? see film-ue log)")
            rec["status"] = "stalled"
            break
        if not busy:
            break
    _sample(rec, r, chunk, seen)
    rec["seconds"] = round(time.time() - rec.pop("t0"), 2)
    rec.pop("_n", None)
    if proc is not None:
        rec["exit_code"] = proc.returncode
        if proc.returncode:
            errors.append(f"exit code {proc.returncode}: {rs.EXIT_CODES.get(proc.returncode, 'see the log')} "
                          f"({rec['log']})")
    want = chunk["end"] - chunk["start"]
    got = {f for f in range(chunk["start"], chunk["end"]) if _valid(rs.frame_path(r, f))}
    rec["frames"] = len(got)
    rec["missing"] = rs.missing_frames(got, chunk["start"], chunk["end"])
    if rec["status"] == "running":
        rec["status"] = "ok" if len(got) == want else ("failed" if not got else "incomplete")
        if not started and not got:
            errors.append("the render never started (unsaved map? a modal? see film-ue log)")
    ft = rs.frame_times(seen)
    rec["frame_s"] = {str(k): v for k, v in ft.pop("per_frame").items()}
    rec.update(ft)
    if r["executor"] != "cmdline":
        _RUN.pop("executor", None)
    _RUN.pop("proc", None)
    return rec


def _cancel_now() -> None:
    exe = _RUN.get("executor")
    try:
        if exe is not None:
            exe.cancel_all_jobs()
    except Exception:
        pass
    proc = _RUN.get("proc")
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            pass


def _close_sequencer() -> None:
    """Close a sequence open in Sequencer before a render (the reel's render.py did, through seq.close): an open
    sequence keeps evaluating on the editor world and its edit state is not what MRQ renders."""
    try:
        lse = unreal.LevelSequenceEditorBlueprintLibrary
        if lse.get_current_level_sequence():
            lse.close_level_sequence()
    except Exception:
        pass


def _guards(r: dict) -> dict:
    g = gpu_info(0)
    v = rs.vram_check(r, g)
    if not v["ok"]:
        raise OpError(v["why"], code="unsupported" if r["path_tracer"] else "conflict", details={"vram": v},
                      hint="vram.force=true renders anyway")
    return {"gpu": g, "vram": v}


def _write_report(r: dict, rep: dict) -> str:
    p = _report_path(r)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rep, f, indent=1, default=str)
    os.replace(tmp, p)
    return p


def _measure(r: dict, chunks: list) -> dict:
    meds = [c["median_s"] for c in chunks if c.get("median_s")]
    if not meds:
        return {}
    med = sorted(meds)[len(meds) // 2]
    per_sample = med / (r["spatial"] * r["temporal"]) / (r["width"] * r["height"] / (1920 * 1080))
    return {"s_per_frame": med, "sample_s_1080p": round(per_sample, 4)}


def _run_job(r: dict, plan: dict, level: str, stall_s: float):
    rep = {"name": r["name"], "spec": r, "level": level, "executor": r["executor"], "path_tracer": r["path_tracer"],
           "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "plan_seconds": plan["seconds"],
           "skipped": plan["skipped"], "chunks": [], "status": "running"}
    rep.update(_guards(r))
    if r["executor"] in ("process", "cmdline"):
        rep["saved"] = _save_first(r["save_dirty"])
        if r["executor"] == "process":
            _offscreen_child()
    os.makedirs(r["out_dir"], exist_ok=True)
    _close_sequencer()
    if r["overwrite"]:
        for f in rs.frames_on_disk(r, _walk(r["out_dir"])):
            if plan["range"][0] <= f < plan["range"][1]:
                try:
                    os.remove(rs.frame_path(r, f))
                except OSError:
                    pass
    _RUN.update(status="running", name=r["name"], report=_report_path(r), cancel=False, started=time.time(),
                chunks_total=len(plan["chunks"]), chunks_done=0, frames_done=0,
                frames_total=sum(c["frames"] for c in plan["chunks"]), finished=None)
    t0 = time.time()
    try:
        for c in plan["chunks"]:
            rec = yield from _run_chunk(r, c, level, stall_s)
            rep["chunks"].append(rec)
            _RUN["chunks_done"] += 1
            _RUN["frames_done"] += rec.get("frames", 0)
            _write_report(r, rep)
            if rec["status"] in ("cancelled", "vram_abort"):
                break
    except GeneratorExit:  # the bridge cancelled the job (jobs.cancel): stop MRQ too, keep the report honest
        _cancel_now()
        rep.update(status="cancelled", seconds=round(time.time() - t0, 1))
        _write_report(r, rep)
        _RUN.update(status="cancelled", finished=time.time())
        raise
    rep["seconds"] = round(time.time() - t0, 1)
    rep["frames"] = sum(c.get("frames", 0) for c in rep["chunks"])
    rep["measured"] = _measure(r, rep["chunks"])
    rep["vram_peak_gb"] = max([c.get("vram_peak_gb") or 0 for c in rep["chunks"]] or [0]) or None
    sts = {c["status"] for c in rep["chunks"]}
    rep["status"] = "ok" if sts <= {"ok"} else next(s for s in ("cancelled", "vram_abort", "stalled", "failed",
                                                                "incomplete") if s in sts)
    rep["errors"] = [f"{c['id']}: {e}" for c in rep["chunks"] for e in c["errors"]]
    rep["report"] = _write_report(r, rep)
    _RUN.update(status=rep["status"], finished=time.time())
    return rep


# ---------------------------------------------------------------------------------------------------------------------
# ops

@op("render.presets", mutates=False, idempotent=True)
def presets() -> dict:
    """The render presets (preview, draft, final, final_exr, 4k, pathtrace): what each is for and its settings.

    Returns: {preset: {"about", "width", "height", "spatial", "temporal", "warmup_render", "warmup_engine",
    "quality", "outputs", ...}}.
    Example: film-ue op render.presets
    """
    return rs.preset_table()


@op("render.plan", mutates=False, idempotent=True)
def plan(*, spec: dict) -> dict:
    """What a render spec would do, without rendering: the resolved settings, one chunk per camera cut (or per
    `chunking` frames) with its pre-roll, frames already on disk that a resume skips, an estimate in seconds, the
    split over `boxes`, and whether the GPU passes the VRAM guard.

    Args: spec: a RENDER SPEC (docs/unreal/render.md; schema tools/filmtools/unreal/schemas/render.schema.json).
    Returns: {"name", "spec", "range", "chunks": [{"id", "camera", "start", "end", "frames", "preroll", "seconds"}],
    "skipped", "frames", "seconds", "boxes", "vram"}.
    Example: film-ue op render.plan 'spec={"sequence": "/Game/Reel/SEQ_Reel", "out_dir": "/srv/r/reel", "preset": "draft"}'
    """
    r = _resolve(spec)
    try:
        p = rs.plan(r, _seq_state(r))
    except rs.SpecError as e:
        raise OpError("; ".join(e.errors), code="bad_args", hint="seq.cuts lists the camera cuts") from None
    p["vram"] = rs.vram_check(r, gpu_info())
    return p


@op("render.job", mutates=True, idempotent=True, tags=["slow", "gpu"])
def job(*, spec: dict, stall_s: float = 900.0):
    """Render a RENDER SPEC to the end (multi-tick: with --async the bridge returns a job id at once; follow it with
    film-ue job ID, or render.status): plan the chunks, check the level and the GPU, render each chunk with MRQ (pre-rolled from its
    shot start), watch frames, VRAM and stalls, then write <out_dir>/_render/<name>.report.json. Re-running resumes:
    frames on disk (and complete) are skipped, so a finished job re-runs as a no-op.

    Args: spec: the RENDER SPEC. stall_s: cancel a chunk after this many seconds with no new frame.
    Returns: the report: {"status": ok|incomplete|failed|stalled|vram_abort|cancelled, "changed", "frames",
    "seconds", "chunks": [{"id", "status", "frames", "missing", "median_s", "vram_peak_gb", "errors", ...}],
    "measured": {"s_per_frame", "sample_s_1080p"}, "report": path, "errors"}.
    Example: film-ue op render.job 'spec={"sequence": "/Game/Reel/SEQ_Reel", "out_dir": "/srv/r/reel", "preset": "final", "shots": ["Reel_S16"]}' (or film-ue render job ... --async; film-ue render run SPEC)
    """
    r = _resolve(spec)
    if _mq().is_rendering() or _RUN.get("status") == "running":
        raise OpError("a render is already running", code="conflict", hint="render.status; render.cancel to stop it")
    level = _check_level(r)
    p = rs.plan(r, _seq_state(r))
    if not p["chunks"]:
        rep = {"name": r["name"], "status": "ok", "changed": False, "frames": 0, "chunks": [], "skipped": p["skipped"],
               "report": _report_path(r), "why": "every frame is already on disk"}
        return rep
    rep = yield from _run_job(r, p, level, stall_s)
    rep["changed"] = rep["frames"] > 0
    rs_videos = [o for o in r["outputs"] if o["kind"] in rs.VIDEO_KINDS]
    if rs_videos and rep["status"] == "ok":
        enc = yield from _encode(r, None, None, rs_videos)
        rep["videos"] = enc["videos"]
        _write_report(r, rep)
    return rep


@op("render.frames", mutates=True, idempotent=True, tags=["gpu"])
def frames(*, sequence: str, frames: list, out_dir: str, level: str = "", preset: str = "preview",
           width: int | None = None, height: int | None = None, cvars: dict | None = None, overwrite: bool = False):
    """Render a few frames of a sequence through its camera cuts with MRQ, viewport-free (works offscreen on Linux):
    for stills, contact sheets and checks (WP10's qa.still mode=mrq builds on it). Consecutive frames in one cut are
    one MRQ job, pre-rolled from the cut start. Frames already on disk are reused.

    Args: sequence: /Game/... level sequence. frames: sequence frame numbers. out_dir: directory on the box.
    level: map (default the open one). preset: preview|draft|final|... width/height: pixels (default the preset's).
    cvars: extra console variables. overwrite: render again even when the frame is on disk (out_dir shared with
    other stills, or the scene changed since).
    Returns: {"frames": {frame: png/jpg path}, "cameras": {frame: camera label}, "width", "height", "seconds",
    "changed", "report"}.
    Example: film-ue op render.frames sequence=/Game/Reel/SEQ_Reel 'frames=[1200,1260]' out_dir=/srv/r/stills
    """
    if not frames:
        raise OpError("no frames asked for", code="bad_args", hint="frames=[1200, 1260]")
    spec = {"sequence": sequence, "out_dir": out_dir, "preset": preset, "name": "frames", "chunking": "shot",
            "cvars": cvars or {}}
    if level:
        spec["level"] = level
    if width:
        spec["width"] = int(width)
    if height:
        spec["height"] = int(height)
    r = _resolve(spec)
    r["outputs"] = [o for o in r["outputs"] if o["kind"] in rs.IMAGE_KINDS][:1]  # stills: one image, no wav/video
    st = _seq_state(r)
    want = sorted({int(f) for f in frames})
    cams = {}
    for f in want:
        cam = next((c for c in st["cuts"] if c[1] <= f < c[2]), None)
        if cam is None and st["cuts"]:
            raise OpError(f"frame {f} is outside every camera cut of {sequence}", code="bad_args",
                          hint=f"cuts: {[c[1:] for c in st['cuts']]}; seq.cuts lists them")
        cams[f] = cam[0] if cam else ""
    done = set() if overwrite else set(st["done"])
    todo = [f for f in want if f not in done]
    t0 = time.time()
    rep = None
    if todo:
        level = _check_level(r)
        chunks = []
        for a, b in rs.runs(todo):
            for cam, cs, ce in st["cuts"] or [["", st["playback"][0], st["playback"][1]]]:
                s, e = max(a, cs), min(b, ce)
                if s < e:
                    chunks.append({"id": f"frames_{s}", "cut": 0, "camera": cam, "cut_start": cs, "start": s, "end": e,
                                   "frames": e - s, "preroll": s - cs, "seconds": 0})
        if _mq().is_rendering() or _RUN.get("status") == "running":
            raise OpError("a render is already running", code="conflict", hint="render.status; render.cancel")
        rep = yield from _run_job(r, {"chunks": chunks, "seconds": 0, "skipped": [], "range": [want[0], want[-1] + 1]},
                                  level, 600.0)
    got = {f: rs.frame_path(r, f) for f in want if _valid(rs.frame_path(r, f))}
    missing = [f for f in want if f not in got]
    if missing:
        raise OpError(f"frames {missing} were not rendered", code="failed", details={"report": rep},
                      hint=f"see {_report_path(r)} and film-ue log")
    return {"frames": got, "cameras": {f: cams[f] for f in want}, "width": r["width"], "height": r["height"],
            "seconds": round(time.time() - t0, 1), "changed": bool(todo), "report": _report_path(r) if rep else None}


@op("render.status", mutates=False, idempotent=True)
def status() -> dict:
    """The render in progress (or the last one): status, job name, chunk, chunks done/total, frames written, GPU
    memory now, and the report path.

    Returns: {"status": idle|running|ok|..., "name", "chunk", "chunks_done", "chunks_total", "chunk_frames",
    "elapsed_s", "gpu", "report", "rendering"}.
    Example: film-ue op render.status
    """
    out = {k: v for k, v in _RUN.items() if k in ("status", "name", "chunk", "chunks_done", "chunks_total", "report")}
    rec = _RUN.get("chunk_rec") or {}
    out["chunk_frames"] = rec.get("_n", rec.get("frames", 0))
    if _RUN.get("started"):
        out["elapsed_s"] = round((_RUN.get("finished") or time.time()) - _RUN["started"], 1)
    out["gpu"] = gpu_info()
    out["rendering"] = bool(_mq().is_rendering())
    return out


@op("render.cancel", mutates=True, idempotent=True)
def cancel() -> dict:
    """Stop the render in progress (the chunk's frames so far stay; a re-run resumes).

    Returns: {"changed": bool, "was": status}.
    Example: film-ue op render.cancel
    """
    was = _RUN.get("status", "idle")
    busy = bool(_mq().is_rendering()) or was == "running"
    _RUN["cancel"] = True
    _cancel_now()
    if busy and not _RUN.get("chunk_rec"):
        try:
            exe = _mq().get_active_executor()
            if exe:
                exe.cancel_all_jobs()
        except Exception:
            pass
    return {"changed": busy, "was": was}


@op("render.describe", mutates=False, idempotent=True)
def describe(*, out_dir: str = "", name: str = "") -> dict:
    """The render state for planning and for Claude: whether MRQ is rendering, the job in progress, and, given
    out_dir (and name), the last report's summary and the frames on disk.

    Returns: {"rendering", "status", "report": {...} | None, "frames_on_disk": int | None}.
    Example: film-ue op render.describe out_dir=/srv/r/reel name=SEQ_Reel
    """
    out = {"rendering": bool(_mq().is_rendering()), "status": _RUN.get("status", "idle"), "report": None,
           "frames_on_disk": None}
    if out_dir:
        reps = sorted(glob.glob(os.path.join(out_dir, "_render", f"{name or '*'}.report.json")), key=os.path.getmtime)
        if reps:
            with open(reps[-1]) as f:
                rep = json.load(f)
            out["report"] = {k: rep.get(k) for k in ("name", "status", "frames", "seconds", "measured", "errors",
                                                     "vram_peak_gb", "started")}
            out["report"]["path"] = reps[-1]
            r = rep.get("spec")
            if r:
                out["frames_on_disk"] = len(_done_frames(r, check=False))
    return out


@op("render.manifest", mutates=True, idempotent=True)
def manifest(*, spec: dict) -> dict:
    """Write, per chunk of a spec, an MRQ queue manifest and the command line that renders it in a process with no
    editor (one process per job: survives editor restarts; run it on this box or another with the same project).

    Returns: {"changed": True, "chunks": [{"id", "start", "end", "manifest", "argv"}], "exit_codes"}.
    Example: film-ue op render.manifest 'spec={"sequence": "/Game/Reel/SEQ_Reel", "out_dir": "/srv/r/reel", "executor": "cmdline"}'
    """
    r = _resolve(spec)
    level = _check_level(r)
    p = rs.plan(r, _seq_state(r))
    out = []
    for c in p["chunks"]:
        q, _ = _new_job(r, c, level)
        m = _write_manifest(q, os.path.join(r["out_dir"], "_render", f"{c['id']}.utxt"))
        q.delete_all_jobs()
        out.append({"id": c["id"], "start": c["start"], "end": c["end"], "manifest": m,
                    "argv": rs.cmdline(_editor_binary(), unreal.Paths.get_project_file_path(), m,
                                       log=os.path.join(r["out_dir"], "_render", f"{c['id']}.log"))})
    return {"changed": bool(out), "chunks": out, "exit_codes": rs.EXIT_CODES}


# ---------------------------------------------------------------------------------------------------------------------
# encode

def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise OpError("ffmpeg is not installed on the render box", code="unsupported",
                      hint="install it (Ubuntu: apt-get install -y ffmpeg), or pull the frames and run "
                           "film-ue render video SPEC --local DIR")
    return exe


def _run_proc(argv: list, timeout_s: float = 3600.0):
    """Run a process to the end without blocking the game thread (multi-tick); returns (code, stderr tail)."""
    kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
    p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kw)
    t0 = time.time()
    while p.poll() is None:
        if time.time() - t0 > timeout_s:
            p.kill()
            return -9, "timed out"
        yield 0.25
    return p.returncode, (p.stderr.read() or b"").decode(errors="replace")[-2000:]


def _audio_for(r: dict, start: int, end: int, fps: float) -> str:
    parts = []
    for path in glob.glob(os.path.join(r["out_dir"], "_render", "audio", "*.wav")):
        stem = os.path.basename(path)[:-4]
        try:
            a, b = (int(x) for x in stem.split("-"))
        except ValueError:
            continue
        if a < end and b > start:
            parts.append((path, a))
    if not parts:
        return ""
    out = os.path.join(r["out_dir"], "_render", "audio", f"_{r['name']}_{start}-{end}.wav")
    rs.assemble_wav(parts, start, end, fps, out)
    return out


def _encode(r: dict, start, end, outs: list):
    seq = _load_sequence(r["sequence"])
    fps = _fps(seq)
    lo = int(seq.get_playback_start()) if start is None else int(start)
    hi = int(seq.get_playback_end()) if end is None else int(end)
    if start is None and r["frames"]:
        lo, hi = r["frames"]
    have = _done_frames(r)
    present = sorted(f for f in have if lo <= f < hi)
    if start is None and r.get("shots") and present:
        lo, hi = present[0], present[-1] + 1  # a shots-only render: encode what it covers
    gaps = rs.missing_frames(have, lo, hi)
    if gaps:
        raise OpError(f"frames missing in [{lo}, {hi}): {gaps[:10]}", code="conflict", details={"missing": gaps},
                      hint="render them first (render.job resumes), or pass start/end around them")
    ff = _ffmpeg()
    videos = []
    for o in outs:
        audio, a0 = "", 0.0
        if o.get("audio", True) is True:
            audio = _audio_for(r, lo, hi, fps)
        elif isinstance(o.get("audio"), str):
            audio, a0 = o["audio"], float(o.get("audio_offset", lo / fps))
        argv = rs.encode_args(r, o, lo, hi, fps, audio_file=audio, audio_start_s=a0, ffmpeg=ff)
        code, err = yield from _run_proc(argv)
        if code:
            raise OpError(f"ffmpeg failed ({code}) encoding {o['kind']}: {err.strip()[-400:]}", code="failed",
                          details={"argv": argv})
        videos.append({"kind": o["kind"], "path": argv[-1], "frames": hi - lo, "start": lo, "end": hi,
                       "audio": audio or None, "bytes": os.path.getsize(argv[-1])})
    return {"videos": videos, "changed": bool(videos), "fps": fps}


@op("render.encode", mutates=True, idempotent=True, tags=["slow"])
def encode(*, spec: dict, start: int | None = None, end: int | None = None, outputs: list | None = None):
    """Encode a render's frames into video with ffmpeg on the box: H.264 (yuv420p, CRF), H.265 or ProRes (prores_ks,
    10-bit), with the render's WAV chunks laid on the timeline (or an audio file of yours). Frames must be complete
    in the range; EXR frames are converted from linear with the sRGB curve.

    Args: spec: the RENDER SPEC that rendered them. start/end: frames, end exclusive (default the spec's range).
    outputs: video outputs (default the spec's h264/h265/prores outputs, else one h264).
    Returns: {"videos": [{"kind", "path", "frames", "start", "end", "audio", "bytes"}], "changed", "fps"}.
    Example: film-ue op render.encode 'spec={"sequence": "/Game/Reel/SEQ_Reel", "out_dir": "/srv/r/reel"}' 'outputs=[{"kind": "prores", "profile": 3}]'
    """
    r = _resolve(spec)
    outs = outputs or [o for o in r["outputs"] if o["kind"] in rs.VIDEO_KINDS] or [{"kind": "h264"}]
    bad = [o for o in outs if o.get("kind") not in rs.VIDEO_KINDS]
    if bad:
        raise OpError(f"not video outputs: {bad}", code="bad_args", hint=f"kinds: {', '.join(rs.VIDEO_KINDS)}")
    return (yield from _encode(r, start, end, outs))


@op("render.concat", mutates=True, idempotent=True, tags=["slow"])
def concat(*, parts: list, out_file: str, audio: str = "", audio_offset_s: float = 0.0):
    """Join video files of the same codec and size (chunks from several boxes, shots) into one without re-encoding,
    and optionally lay an audio file under the result.

    Args: parts: video paths in order. out_file: the result. audio: a WAV/AAC to put under it. audio_offset_s: seconds
    of that audio to skip.
    Returns: {"path", "parts", "bytes", "changed"}.
    Example: film-ue op render.concat 'parts=["/srv/r/a.mp4","/srv/r/b.mp4"]' out_file=/srv/r/all.mp4
    """
    missing = [p for p in parts if not os.path.isfile(p)]
    if not parts or missing:
        raise OpError(f"missing parts: {missing or 'none given'}", code="not_found", hint="render.encode makes them")
    ff = _ffmpeg()
    lst = out_file + ".parts.txt"
    target = out_file + ".noaudio" + os.path.splitext(out_file)[1] if audio else out_file
    argv, text = rs.concat_args(parts, target, lst, ff)
    with open(lst, "w") as f:
        f.write(text)
    code, err = yield from _run_proc(argv)
    if code:
        raise OpError(f"ffmpeg concat failed ({code}): {err.strip()[-400:]}", code="failed", details={"argv": argv})
    if audio:
        argv = rs.mux_audio_args(target, audio, out_file, audio_start_s=audio_offset_s,
                                 prores=out_file.lower().endswith(".mov"), ffmpeg=ff)
        code, err = yield from _run_proc(argv)
        if code:
            raise OpError(f"ffmpeg mux failed ({code}): {err.strip()[-400:]}", code="failed", details={"argv": argv})
        os.remove(target)
    os.remove(lst)
    return {"path": out_file, "parts": len(parts), "bytes": os.path.getsize(out_file), "changed": True}


# ---------------------------------------------------------------------------------------------------------------------
# A/B

def _frames_in(d: str, ext: str, pad: int) -> set:
    import re
    rx = re.compile(r"^(-?\d{%d,})\.%s$" % (pad, re.escape(ext)))
    return {int(m.group(1)) for f in (os.listdir(d) if os.path.isdir(d) else []) for m in [rx.match(f)] if m}


@op("render.compare", mutates=False, idempotent=True, tags=["slow"])
def compare(*, a: str, b: str, frames: list | None = None, ext: str = "png", zero_pad: int = 4, min_ssim: float = 0.98,
            worst: int = 5, every: int = 1, sheet: str = "", method: str = "auto"):
    """Compare two renders frame by frame (two outputs of the same frames: a pre-rolled chunk against the full-shot
    render, Linux against Windows, today against yesterday, a render against reference frames): per-frame SSIM and
    PSNR, the worst frames, a pass/fail check at min_ssim, and optionally a sheet of the worst frames side by side.

    Args: a, b: folders of frames named <frame>.<ext> (the beauty pass: <out_dir> or <out_dir>/FinalImage). frames:
    [start, end) (default every frame in both). ext: png|jpg|exr. min_ssim: the pass threshold. worst: how many worst
    frames to list (and sheet). every: compare every n-th frame. sheet: a PNG path for the worst frames side by side
    (PNG frames). method: auto (ffmpeg ssim/psnr when the box has ffmpeg, else qa.compare at 480 px), ffmpeg or qa.
    Returns: {"pass", "metric" (min SSIM), "threshold", "why", "mean_ssim", "min_psnr", "mean_psnr", "worst":
    [[frame, ssim, psnr]], "below", "frames", "per_frame": {frame: [ssim, psnr]}, "method", "sheet"}.
    Example: film-ue op render.compare a=/srv/r/full b=/srv/r/chunk 'frames=[1136,1160]' sheet=/srv/r/ab.png
    """
    if method not in ("auto", "ffmpeg", "qa"):
        raise OpError(f"method {method!r}: auto, ffmpeg or qa", code="bad_args", candidates=["auto", "ffmpeg", "qa"])
    for d in (a, b):
        if not os.path.isdir(d):
            raise OpError(f"no folder {d!r}", code="not_found", hint="give the folders the frames are in")
    both = _frames_in(a, ext, zero_pad) & _frames_in(b, ext, zero_pad)
    if frames:
        lo, hi = int(frames[0]), int(frames[1])
        want = [f for f in range(lo, hi)]
        missing = [f for f in want if f not in both]
        if missing:
            raise OpError(f"{len(missing)} frames of [{lo}, {hi}) are not in both folders: {rs.runs(missing)[:5]}",
                          code="not_found", hint=f"frames in both: {rs.runs(both)[:5]}")
    else:
        want = sorted(both)
    want = want[::max(1, int(every))]
    if not want:
        raise OpError(f"no frame named <frame>.{ext} is in both {a} and {b}", code="not_found",
                      hint="ext=exr? zero_pad? a pass folder (FinalImage)?")
    ff = shutil.which("ffmpeg")
    use = "ffmpeg" if method == "ffmpeg" or (method == "auto" and ff and every == 1 and
                                            rs.runs(want) == [[want[0], want[-1] + 1]]) else "qa"
    ssim, psnr = {}, {}
    if use == "ffmpeg":
        if not ff:
            raise OpError("ffmpeg is not installed on the box", code="unsupported", hint="method=qa, or install ffmpeg")
        import tempfile
        tmp = tempfile.mkdtemp(prefix="render_ab_")
        sl, pl = os.path.join(tmp, "ssim.log"), os.path.join(tmp, "psnr.log")
        pat = lambda d: os.path.join(d, f"%0{zero_pad}d.{ext}")  # noqa: E731
        argv = rs.compare_args(pat(a), pat(b), want[0], len(want), sl, pl, ff, exr=ext == "exr")
        code, err = yield from _run_proc(argv)
        if code:
            raise OpError(f"ffmpeg compare failed ({code}): {err.strip()[-400:]}", code="failed", details={"argv": argv})
        with open(sl) as f:
            ssim = rs.parse_ffmpeg_stats(f.read(), "All", want[0])
        with open(pl) as f:
            psnr = rs.parse_ffmpeg_stats(f.read(), "psnr_avg", want[0])
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        if ext != "png":
            raise OpError(f"qa.compare reads PNG only, these are .{ext}", code="unsupported",
                          hint="install ffmpeg on the box (method=ffmpeg), or render PNG")
        from ..qa import compare as qcmp, image as qim
        for i, f in enumerate(want):
            r = qcmp.compare(qim.read(os.path.join(a, f"{f:0{zero_pad}d}.{ext}")),
                             qim.read(os.path.join(b, f"{f:0{zero_pad}d}.{ext}")), width=480)
            ssim[f], psnr[f] = float(r["ssim"]), float(r["psnr"])
            yield {"progress": round((i + 1) / len(want), 3), "message": f"frame {f}: SSIM {ssim[f]:.4f}"}
    out = rs.ab_summary(ssim, psnr, min_ssim=min_ssim, worst=worst)
    out.update(frames=len(ssim), per_frame={f: [round(ssim[f], 5), psnr.get(f)] for f in sorted(ssim)}, method=use,
               a=a, b=b, sheet=None)
    if sheet and out["worst"] and ext == "png":
        from ..qa import image as qim, sheet as qsheet
        cells = []
        for f, sv, pv in out["worst"]:
            pair = qsheet.side_by_side(qim.read(os.path.join(a, f"{f:0{zero_pad}d}.png")),
                                       qim.read(os.path.join(b, f"{f:0{zero_pad}d}.png")), labels=("A", "B"))
            cells.append({"image": pair, "label": f"{f}  SSIM {sv:.4f}  PSNR {pv}",
                          "status": "fail" if sv < min_ssim else "ok"})
            yield
        qim.write(qsheet.contact_sheet(cells, cols=1, cell_width=960, title=f"A {a}  |  B {b}"), sheet)
        out["sheet"] = sheet
    return out


# ---------------------------------------------------------------------------------------------------------------------
# the older start-and-poll pair (films/host-studio/reel/render.py and poc.py call these)

@op("render.mrq", mutates=True, idempotent=False, tags=["gpu"])
def mrq(sequence: str, level: str, out_dir: str, width: int = 1920, height: int = 1080, temporal: int = 8,
        spatial: int = 1, path_tracer: bool = False, quality: bool = True, cvars: dict | None = None, fmt: str = "png",
        warmup: int = 32, name: str = "shot", start: int | None = None, end: int | None = None,
        executor: str = "pie", save_dirty: bool = False, preroll_from: int | None = None) -> dict:
    """Start one Movie Render Queue job and return at once (poll render.progress); render.job does a whole spec.
    Frames go to `out_dir` as {frame}.png|exr|jpg, the audio as a wav; `start`/`end` (end exclusive) render part of
    the sequence. `preroll_from`: the shot's first frame when `start` is mid-shot: the frames between are evaluated
    without rendering so cloth arrives as in a full-shot render (needs the camera cut to begin there). `executor`:
    "pie" (in this editor) or "process" (a separate -game process; offscreen where the editor has no desktop). The
    process loads the level from disk, and with unsaved changes the executor asks to save first: unattended, that
    question goes unanswered and the job never starts, so unsaved packages are an error unless `save_dirty`.

    Example: film-ue op render.mrq sequence=/Game/Reel/SEQ_Reel level=/Game/Studio/Studio out_dir=/srv/r/s16 start=1196 end=1220
    """
    mq = _mq()
    if mq.is_rendering():
        raise OpError("a render is already running", code="conflict", hint="render.progress / render.cancel")
    if executor not in ("pie", "process"):
        raise OpError(f"executor {executor!r}: pie or process", code="bad_args", candidates=["pie", "process"])
    spec = {"sequence": sequence, "level": level, "out_dir": out_dir, "preset": "final", "width": width,
            "height": height, "temporal": temporal, "spatial": spatial, "path_tracer": path_tracer, "quality": quality,
            "cvars": dict(cvars or {}), "warmup_render": warmup, "warmup_engine": warmup, "executor": executor,
            "outputs": [{"kind": fmt}, {"kind": "wav"}], "save_dirty": save_dirty}
    r = _resolve(spec)
    seq = _load_sequence(sequence)
    s = int(seq.get_playback_start()) if start is None else int(start)
    e = int(seq.get_playback_end()) if end is None else int(end)
    chunk = {"id": name, "start": s, "end": e, "preroll": (s - preroll_from) if preroll_from is not None else 0}
    q, job_ = _new_job(r, chunk, _pkg(level))
    os.makedirs(out_dir, exist_ok=True)
    if executor == "process":
        _save_first(save_dirty)
        _offscreen_child()
        mq.render_queue_with_executor(unreal.MoviePipelineNewProcessExecutor)
    else:
        mq.render_queue_with_executor(unreal.MoviePipelinePIEExecutor)
    return {"out_dir": out_dir, "started": True, "executor": executor, "changed": True}


@op("render.progress", mutates=False, idempotent=True)
def progress(out_dir: str, expected: int = 0) -> dict:
    """Frames written so far in out_dir (and whether Movie Render Queue is still running).

    Example: film-ue op render.progress out_dir=/srv/r/s16 expected=24
    """
    files = [f for f in os.listdir(out_dir) if f.lower().endswith((".png", ".exr", ".jpg", ".jpeg"))] if os.path.isdir(out_dir) else []
    rendering = bool(_mq().is_rendering())
    return {"frames": len(files), "expected": expected, "rendering": rendering, "done": not rendering and len(files) > 0}
