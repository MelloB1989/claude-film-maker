"""The RENDER SPEC and everything about a render that needs no engine: presets, validation against the JSON schema,
resolving a spec into concrete settings, planning chunks from the sequence's camera cuts (resumable, each chunk
pre-rolled from its shot start for cloth), splitting chunks across boxes, cost estimates, the command line of a
one-process render, and the ffmpeg command lines that turn frames into H.264 / ProRes and join chunks with audio.

Pure Python 3.11, no `unreal`: the bridge (`ops/render.py`) and the operator's side (`filmtools.unreal.render`) both
import it, and the unit tests run it as is. docs/unreal/render.md is the guide; this file is the reference.

A spec, smallest form (everything else has a default from the preset):

    {"sequence": "/Game/Reel/SEQ_Reel", "level": "/Game/Studio/Studio", "out_dir": "/srv/renders/reel", "preset": "final"}

Units: frames are the sequence's display-rate frame numbers (end exclusive), sizes are pixels, times are seconds,
memory is GB (10^9 bytes).
"""
from __future__ import annotations

import copy
import os
import re

SPEC_VERSION = 1

# ---------------------------------------------------------------------------------------------------------------------
# presets

QUALITY_CVARS = {  # Lumen and shadows at film quality (the reel's finals; docs/linux/engine.md P4 measured the cost)
    "r.Lumen.ScreenProbeGather.DownsampleFactor": 8, "r.Lumen.ScreenProbeGather.TracingOctahedronResolution": 16,
    "r.Lumen.Reflections.DownsampleFactor": 1, "r.Lumen.TranslucencyReflections.FrontLayer.Enable": 1,
    "r.Shadow.Virtual.SMRT.RayCountDirectional": 16, "r.Shadow.Virtual.SMRT.SamplesPerRayDirectional": 16,
    "r.Shadow.Virtual.SMRT.RayCountLocal": 16, "r.Shadow.Virtual.SMRT.SamplesPerRayLocal": 16,
    "r.HairStrands.Visibility.MSAA.SamplePerPixel": 8, "r.DepthOfFieldQuality": 4, "r.MotionBlurQuality": 4,
    "r.Tonemapper.Sharpen": 0.5, "r.ScreenPercentage": 100,
}
# Always set while rendering: no frame cap (the bridge caps an idle offscreen editor), and strand hair without the
# unoccluded sky light (indoors in daylight it goes white: unreal/README.md).
BASE_CVARS = {"t.MaxFPS": 0, "r.HairStrands.SkyLighting": 0}

PRESETS: dict = {
    "preview": {
        "about": "fast look: half HD, one sample, JPG, no film-quality cvars; seconds per shot",
        "width": 960, "height": 540, "spatial": 1, "temporal": 1, "warmup_render": 8, "warmup_engine": 0,
        "quality": False, "outputs": [{"kind": "jpg"}],
    },
    "draft": {
        "about": "full HD, 4 temporal samples, PNG, no film-quality cvars; checks motion and timing",
        "width": 1920, "height": 1080, "spatial": 1, "temporal": 4, "warmup_render": 16, "warmup_engine": 0,
        "quality": False, "outputs": [{"kind": "png"}],
    },
    "final": {
        "about": "the reel's finals: full HD, 8 temporal samples (motion blur), 32 warm-up, film-quality cvars, PNG + WAV",
        "width": 1920, "height": 1080, "spatial": 1, "temporal": 8, "warmup_render": 32, "warmup_engine": 0,
        "quality": True, "outputs": [{"kind": "png"}, {"kind": "wav"}],
    },
    "final_exr": {
        "about": "final, as 16-bit half EXR (PIZ) with depth and motion vectors, for grading and compositing",
        "width": 1920, "height": 1080, "spatial": 1, "temporal": 8, "warmup_render": 32, "warmup_engine": 0,
        "quality": True, "outputs": [{"kind": "exr"}, {"kind": "wav"}], "passes": ["beauty", "depth", "motion_vectors"],
    },
    "4k": {
        "about": "UHD 3840x2160, otherwise final; ~4x the time and ~2x the VRAM of final",
        "width": 3840, "height": 2160, "spatial": 1, "temporal": 8, "warmup_render": 32, "warmup_engine": 0,
        "quality": True, "outputs": [{"kind": "png"}, {"kind": "wav"}],
    },
    "pathtrace": {
        "about": "path tracer, 16 spp, denoised; guarded: needs >= 40 GB VRAM with strand hair (an L4 24 GB runs out)",
        "width": 1920, "height": 1080, "spatial": 16, "temporal": 1, "warmup_render": 0, "warmup_engine": 8,
        "quality": False, "path_tracer": True, "outputs": [{"kind": "exr"}],
    },
}

OUTPUT_KINDS = {  # kind: (made by, file extension)
    "png": ("mrq", "png"), "jpg": ("mrq", "jpg"), "exr": ("mrq", "exr"), "bmp": ("mrq", "bmp"), "wav": ("mrq", "wav"),
    "h264": ("ffmpeg", "mp4"), "h265": ("ffmpeg", "mp4"), "prores": ("ffmpeg", "mov"),
}
IMAGE_KINDS = ("png", "jpg", "exr", "bmp")
VIDEO_KINDS = ("h264", "h265", "prores")
# Render passes: "beauty" is the main deferred image; the post-process AOVs ride on the deferred pass (MRQ's own
# materials); the lighting passes are separate deferred passes; object_id needs the MoviePipelineMaskRenderPass plugin.
PASSES = {
    "beauty": ("deferred", "FinalImage"),
    "depth": ("ppm", "/MovieRenderPipeline/Materials/MovieRenderQueue_WorldDepth.MovieRenderQueue_WorldDepth"),
    "motion_vectors": ("ppm", "/MovieRenderPipeline/Materials/MovieRenderQueue_MotionVectors.MovieRenderQueue_MotionVectors"),
    "unlit": ("class", "MoviePipelineDeferredPass_Unlit"),
    "lighting_only": ("class", "MoviePipelineDeferredPass_LightingOnly"),
    "detail_lighting": ("class", "MoviePipelineDeferredPass_DetailLighting"),
    "reflections_only": ("class", "MoviePipelineDeferredPass_ReflectionsOnly"),
    "object_id": ("class", "MoviePipelineObjectIdRenderPass"),  # cryptomatte-style IDs, best in a multilayer EXR
}
EXECUTORS = ("pie", "process", "cmdline")
AA_METHODS = ("none", "fxaa", "taa", "msaa", "tsr", "smaa")
EXR_COMPRESSION = ("none", "rle", "zips", "zip", "piz", "pxr24", "b44", "b44a", "dwaa", "dwab")

# Cost model (docs/linux/engine.md P3/P4/P5, UE 5.8.4, L4, Vulkan SM6): ~0.09 s per deferred sample at 1920x1080,
# ~12 s to start a PIE job, warm-ups cost a sample each; the path tracer ~0.3 s per sample plus a CPU denoise of
# ~2.4 s per rendered frame on Linux (no GPU NNE runtime there). A report's measured s_per_sample replaces the guess.
COST = {"sample_s_1080p": 0.09, "pt_sample_s_1080p": 0.3, "pt_denoise_s": 2.4, "engine_frame_s": 0.03,
        "job_overhead_s": 12.0}
PT_MIN_VRAM_GB = 40.0  # P5: 1080p + strand hair OOMed a 24 GB L4 (22.5 of 23 GB in ~25 s); 48 GB untested


class SpecError(ValueError):
    """A spec that cannot render: `errors` lists every problem as 'path: what is wrong (what to do)'."""

    def __init__(self, errors: list):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


# ---------------------------------------------------------------------------------------------------------------------
# the schema (also written to tools/filmtools/unreal/schemas/render.schema.json; a test keeps the two equal)

def _int(desc: str, minimum: int | None = None, **kw) -> dict:
    d = {"type": "integer", "description": desc, **kw}
    if minimum is not None:
        d["minimum"] = minimum
    return d


_OUTPUT = {
    "type": "object", "additionalProperties": False, "required": ["kind"],
    "description": "One output. png/jpg/exr/bmp/wav are written by Movie Render Queue; h264/h265/prores are encoded "
                   "with ffmpeg from the image frames (plus the WAV when there is one) after each render.",
    "properties": {
        "kind": {"enum": list(OUTPUT_KINDS), "description": "the output kind"},
        "compression": {"enum": list(EXR_COMPRESSION), "description": "exr: compression (default piz, lossless)"},
        "multilayer": {"type": "boolean", "description": "exr: every pass in one multilayer file (default false)"},
        "alpha": {"type": "boolean", "description": "png: write the alpha channel (default false)"},
        "crf": _int("h264/h265: constant rate factor, 0 = lossless, 18 = visually lossless (default 18)", 0, maximum=51),
        "profile": _int("prores: 0 proxy, 1 LT, 2 standard, 3 HQ, 4 4444, 5 4444 XQ (default 3)", 0, maximum=5),
        "audio": {"type": ["string", "boolean"],
                  "description": "video: true (default) muxes the render's WAV, a path muxes that file, false = silent"},
        "audio_offset": {"type": "number", "description": "video: seconds of audio to skip so it lines up with the "
                                                          "first frame (default: the first frame's time in the sequence)"},
        "file": {"type": "string", "description": "video: output file name in out_dir (default <name>.<ext>)"},
    },
}

SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://claude-film-maker/schemas/render.schema.json",
    "title": "render",
    "description": "A render job for Unreal's Movie Render Queue, driven by film-ue render / the render.job op. "
                   "Frames are the sequence's display-rate frame numbers, end exclusive; sizes in pixels; times in "
                   "seconds; memory in GB.",
    "type": "object", "additionalProperties": False,
    "required": ["sequence", "out_dir"],
    "properties": {
        "kind": {"const": "render", "description": "spec kind (for film-ue apply)"},
        "version": {"const": SPEC_VERSION, "description": "spec version"},
        "name": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+$",
                 "description": "job name: the report, the manifest and videos are named after it (default: the "
                                "sequence's asset name)"},
        "sequence": {"type": "string", "pattern": "^/", "description": "LevelSequence package path, /Game/..."},
        "level": {"type": "string", "pattern": "^/",
                  "description": "map package path, /Game/... (default: the level open in the editor)"},
        "out_dir": {"type": "string", "description": "directory on the render box for frames, report and videos"},
        "preset": {"enum": list(PRESETS), "description": "starting point for every setting below (default final)"},
        "width": _int("output width in pixels", 16, maximum=16384),
        "height": _int("output height in pixels", 16, maximum=16384),
        "frames": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2,
                   "description": "[start, end) in sequence frames (default: the playback range)"},
        "shots": {"type": "array", "items": {"type": ["string", "integer"]},
                  "description": "only these camera cuts: camera labels, or 0-based cut indices (default all)"},
        "spatial": _int("spatial samples per temporal sample (anti-aliasing; path tracer: samples per pixel)", 1, maximum=1024),
        "temporal": _int("temporal samples per frame (motion blur sub-steps)", 1, maximum=256),
        "warmup_render": _int("frames rendered and discarded at each shot start (temporal history)", 0, maximum=512),
        "warmup_engine": _int("frames the engine ticks without rendering at a chunk start when it has no pre-roll", 0, maximum=1024),
        "preroll": {"enum": ["cut", "none"],
                    "description": "cut (default): a chunk that starts after its camera cut's first frame is "
                                   "pre-rolled from that first frame (the sequence evaluated frame by frame, nothing "
                                   "rendered) so cloth and physics arrive in the state a full-shot render would have"},
        "aa_method": {"enum": list(AA_METHODS), "description": "override the project's anti-aliasing (default: the project's)"},
        "path_tracer": {"type": "boolean", "description": "render with the path tracer instead of deferred (Lumen)"},
        "quality": {"type": "boolean", "description": "apply the film-quality cvars (Lumen, VSM SMRT, hair MSAA, DOF, blur)"},
        "cvars": {"type": "object", "additionalProperties": {"type": "number"},
                  "description": "console variables while rendering (on top of the preset's), name: number"},
        "passes": {"type": "array", "items": {"enum": list(PASSES)}, "uniqueItems": True,
                   "description": "render passes / AOVs (default [beauty]); more than one writes <out_dir>/<pass>/"},
        "outputs": {"type": "array", "items": _OUTPUT, "minItems": 1, "description": "what to write"},
        "executor": {"enum": list(EXECUTORS),
                     "description": "pie (default): inside the editor; process: a separate -game process the editor "
                                    "starts and watches; cmdline: a manifest and command line for a process with "
                                    "no editor at all"},
        "save_dirty": {"type": "boolean", "description": "process/cmdline: save unsaved packages first (default true; "
                                                         "false makes unsaved packages an error)"},
        "chunking": {"type": ["string", "integer"],
                     "description": "shot (default): one MRQ job per camera cut; none: one job for the range; an "
                                    "integer: per cut, at most that many frames per job"},
        "resume": {"type": "boolean", "description": "skip frames already on disk (default true)"},
        "overwrite": {"type": "boolean", "description": "delete the frames in range first (default false)"},
        "file_name": {"type": "string",
                      "description": "MRQ file name format (default {frame_number}; {render_pass}/{frame_number} "
                                     "with several passes)"},
        "zero_pad": _int("digits in frame numbers", 1, maximum=8),
        "boxes": _int("render boxes to plan for (default 1): chunks are balanced by estimated time", 1, maximum=64),
        "game_overrides": {
            "type": "object", "additionalProperties": False,
            "description": "MRQ Game Overrides to set explicitly (absent = MRQ's own defaults, which every render "
                           "already gets as a transient setting: cinematic scalability, LOD 0, no HLODs, cloth "
                           "time-step smoothing off); give only what you want to change",
            "properties": {
                "cinematic_quality": {"type": "boolean", "description": "Cinematic scalability while rendering"},
                "texture_streaming": {"enum": ["none", "disabled", "fully_load"],
                                      "description": "none: leave the project's; disabled: no streaming (most VRAM); "
                                                     "fully_load: load used textures fully (less VRAM)"},
                "lod_zero": {"type": "boolean", "description": "force LOD 0 on every mesh"},
                "disable_hlods": {"type": "boolean", "description": "no HLOD proxies"},
                "high_quality_shadows": {"type": "boolean", "description": "raise shadow distance/resolution"},
                "shadow_distance_scale": _int("with high_quality_shadows: shadow distance multiplier", 1, maximum=10),
                "view_distance_scale": _int("view distance multiplier (r.ViewDistanceScale), unset = project's", 1,
                                            maximum=100),
                "flush_streaming": {"type": "boolean", "description": "flush streaming managers every frame"},
            }},
        "vram": {"type": "object", "additionalProperties": False, "description": "GPU memory guards",
                 "properties": {
                     "path_tracer_min_gb": {"type": "number", "description": f"refuse the path tracer below this total "
                                                                            f"VRAM in GB (default {PT_MIN_VRAM_GB:g})"},
                     "abort_pct": {"type": "number", "description": "cancel the render when VRAM use passes this "
                                                                    "percentage, before the driver kills the editor "
                                                                    "(default 97; 0 = off)"},
                     "force": {"type": "boolean", "description": "render even when a guard says no"}}},
    },
}


def validate(spec) -> list:
    """Errors in a spec against SCHEMA (the subset of JSON Schema it uses), each 'path: problem'; [] when valid."""
    errs: list = []
    _check(spec, SCHEMA, "spec", errs)
    if not errs:
        if "frames" in spec and spec["frames"][1] <= spec["frames"][0]:
            errs.append(f"spec.frames: end {spec['frames'][1]} must be after start {spec['frames'][0]} (end is exclusive)")
        ch = spec.get("chunking")
        if isinstance(ch, str) and ch not in ("shot", "none"):
            errs.append(f"spec.chunking: {ch!r} is not shot, none or a frame count")
        if isinstance(ch, int) and ch < 1:
            errs.append("spec.chunking: a frame count must be >= 1")
    return errs


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "number": (int, float), "integer": int}


def _is(v, t: str) -> bool:
    if t in ("integer", "number") and isinstance(v, bool):
        return False
    return isinstance(v, _TYPES[t])


def _near(name, names) -> list:
    """The nearest of `names` to `name`, ignoring case (for "did you mean")."""
    from difflib import get_close_matches
    low = {str(x).lower(): str(x) for x in names}
    return [low[m] for m in get_close_matches(str(name).lower(), list(low), n=1, cutoff=0.5)]


def _check(v, s: dict, path: str, errs: list) -> None:
    if "const" in s and v != s["const"]:
        errs.append(f"{path}: must be {s['const']!r}, got {v!r}")
        return
    if "enum" in s and v not in s["enum"]:
        near = _near(v, s["enum"])
        errs.append(f"{path}: {v!r} is not one of {s['enum']}" + (f" (did you mean {near[0]!r}?)" if near else ""))
        return
    if "type" in s:
        ts = s["type"] if isinstance(s["type"], list) else [s["type"]]
        if not any(_is(v, t) for t in ts):
            errs.append(f"{path}: expected {' or '.join(ts)}, got {type(v).__name__} {v!r}")
            return
    if isinstance(v, dict):
        props = s.get("properties", {})
        for k in s.get("required", []):
            if k not in v:
                errs.append(f"{path}.{k}: required ({props.get(k, {}).get('description', '')})")
        for k, x in v.items():
            if k in props:
                _check(x, props[k], f"{path}.{k}", errs)
            elif s.get("additionalProperties") is False:
                near = _near(k, props)
                errs.append(f"{path}.{k}: unknown key" + (f" (did you mean {near[0]!r}?)" if near else
                                                          f" (keys: {', '.join(props)})"))
            elif isinstance(s.get("additionalProperties"), dict):
                _check(x, s["additionalProperties"], f"{path}.{k}", errs)
    if isinstance(v, list):
        if "minItems" in s and len(v) < s["minItems"] or "maxItems" in s and len(v) > s["maxItems"]:
            errs.append(f"{path}: needs {s.get('minItems', 0)}..{s.get('maxItems', 'any')} items, got {len(v)}")
        if s.get("uniqueItems") and len(set(map(repr, v))) != len(v):
            errs.append(f"{path}: items must be unique")
        for i, x in enumerate(v):
            if "items" in s:
                _check(x, s["items"], f"{path}[{i}]", errs)
    if _is(v, "number") and not isinstance(v, bool):
        if "minimum" in s and v < s["minimum"]:
            errs.append(f"{path}: {v} is below the minimum {s['minimum']}")
        if "maximum" in s and v > s["maximum"]:
            errs.append(f"{path}: {v} is above the maximum {s['maximum']}")
    if isinstance(v, str) and "pattern" in s and not re.search(s["pattern"], v):
        errs.append(f"{path}: {v!r} does not match {s['pattern']}")


# ---------------------------------------------------------------------------------------------------------------------
# resolving a spec

def resolve(spec: dict) -> dict:
    """The spec with every setting filled in from its preset and the defaults, validated. Raises SpecError."""
    errs = validate(spec)
    if errs:
        raise SpecError(errs)
    preset = spec.get("preset", "final")
    r = copy.deepcopy({k: v for k, v in PRESETS[preset].items() if k != "about"})
    r.update({"preset": preset, "path_tracer": r.get("path_tracer", False), "passes": r.get("passes", ["beauty"]),
              "preroll": "cut", "aa_method": None, "executor": "pie", "save_dirty": True, "chunking": "shot",
              "resume": True, "overwrite": False, "zero_pad": 4, "boxes": 1, "cvars": {}, "level": "",
              "frames": None, "shots": None, "game_overrides": None})
    r.update(copy.deepcopy({k: v for k, v in spec.items() if k not in ("kind", "version")}))
    r["name"] = r.get("name") or spec["sequence"].rstrip("/").rsplit("/", 1)[-1].split(".")[0]
    r["passes"] = ["beauty"] + [p for p in r["passes"] if p != "beauty"]  # MRQ always writes the main image
    r["vram"] = {"path_tracer_min_gb": PT_MIN_VRAM_GB, "abort_pct": 97.0, "force": False, **spec.get("vram", {})}
    cv = dict(BASE_CVARS)
    if r["quality"]:
        cv.update(QUALITY_CVARS)
    cv.update(r["cvars"])
    r["cvars"] = cv
    if "file_name" not in spec:
        r["file_name"] = "{render_pass}/{frame_number}" if len(r["passes"]) > 1 else "{frame_number}"
    errs = []
    kinds = [o["kind"] for o in r["outputs"]]
    if not any(k in IMAGE_KINDS for k in kinds):
        errs.append("spec.outputs: needs an image output (png, jpg, exr or bmp); videos are encoded from the frames")
    if len(r["passes"]) > 1 and "{render_pass}" not in r["file_name"]:
        errs.append("spec.file_name: several passes need {render_pass} in the file name, or they overwrite each other")
    if r["path_tracer"] and any(p in ("unlit", "lighting_only", "detail_lighting", "reflections_only") for p in r["passes"]):
        errs.append("spec.passes: the lighting passes are deferred-renderer passes; drop them or path_tracer")
    if errs:
        raise SpecError(errs)
    return r


# the file extension MRQ writes for an output kind: its JPEG writer names files .jpeg (day 1 on the box: 168 frames
# rendered, the job counted 0 because it looked for .jpg)
FILE_EXT = {"jpg": "jpeg"}


def _ext(r: dict) -> str:
    return FILE_EXT.get(next(o["kind"] for o in r["outputs"] if o["kind"] in IMAGE_KINDS),
                        next(o["kind"] for o in r["outputs"] if o["kind"] in IMAGE_KINDS))


def frame_path(r: dict, frame: int, pass_name: str = "beauty", ext: str | None = None) -> str:
    """Where MRQ writes `frame` of a pass (the beauty pass is FinalImage in {render_pass})."""
    ext = FILE_EXT.get(ext, ext) if ext else _ext(r)
    rp = PASSES[pass_name][1] if pass_name == "beauty" else (
        PASSES[pass_name][1].rsplit(".", 1)[-1] if PASSES[pass_name][0] == "ppm" else pass_name)
    name = r["file_name"].replace("{render_pass}", rp).replace("{frame_number}", f"{int(frame):0{r['zero_pad']}d}")
    return os.path.join(r["out_dir"], *name.split("/")) + "." + ext


def frames_on_disk(r: dict, names: list) -> set:
    """Frame numbers present in `names` (paths relative to out_dir, as os.walk would list them) for the beauty pass."""
    fmt = r["file_name"].replace("{render_pass}", PASSES["beauty"][1])
    kind = next(o["kind"] for o in r["outputs"] if o["kind"] in IMAGE_KINDS)
    exts = sorted({kind, FILE_EXT.get(kind, kind)})  # .jpg and .jpeg both count
    rx = re.compile("^" + re.escape(fmt).replace(re.escape("{frame_number}"), r"(-?\d+)") +
                    r"\.(?:" + "|".join(map(re.escape, exts)) + ")$")
    out = set()
    for n in names:
        m = rx.match(n.replace("\\", "/"))
        if m:
            out.add(int(m.group(1)))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# planning

def _pick_cuts(r: dict, cuts: list) -> list:
    if not r.get("shots"):
        return list(enumerate(cuts))
    picked, errs = [], []
    for s in r["shots"]:
        if isinstance(s, int):
            if not 0 <= s < len(cuts):
                errs.append(f"spec.shots: cut index {s} out of range (the sequence has {len(cuts)} cuts)")
            else:
                picked.append((s, cuts[s]))
        else:
            hit = [(i, c) for i, c in enumerate(cuts) if c[0] == s]
            if not hit:
                near = _near(s, [c[0] for c in cuts])
                errs.append(f"spec.shots: no camera cut on {s!r}" + (f" (did you mean {near[0]!r}?)" if near else ""))
            picked.extend(hit)
    if errs:
        raise SpecError(errs)
    return sorted({i: (i, c) for i, c in picked}.values(), key=lambda x: x[0])


def runs(frames) -> list:
    """[start, end) runs of consecutive frames: [3, 4, 5, 9] -> [[3, 6], [9, 10]]."""
    out = []
    for f in sorted(frames):
        if out and f == out[-1][1]:
            out[-1][1] = f + 1
        else:
            out.append([f, f + 1])
    return out


def plan(spec: dict, state: dict) -> dict:
    """The chunks a spec renders, given the sequence as it is (`state`):

        state = {"playback": [start, end], "fps": 24.0, "cuts": [[camera label, start, end], ...],
                 "done": [frame, ...]  (beauty frames already on disk), "calibration": {"sample_s_1080p": ...}}

    Each chunk is one MRQ job: {"id", "cut", "camera", "cut_start", "start", "end", "frames", "preroll", "seconds"}.
    `preroll` is how many frames the engine evaluates before `start` (from the cut's first frame, nothing rendered)
    so that cloth arrives as in a full-shot render. With resume, a chunk covers its cut's missing frames only (from the
    first missing to the last missing; frames between that are on disk are rendered again). Raises SpecError."""
    r = resolve(spec) if "cvars" not in spec or "vram" not in spec else spec
    pb = state.get("playback") or [0, 0]
    lo, hi = (r["frames"] or pb)
    cuts = state.get("cuts") or [["", pb[0], pb[1]]]
    done = set(state.get("done") or []) if r["resume"] and not r["overwrite"] else set()
    chunks, skipped = [], []
    for i, (cam, cs, ce) in _pick_cuts(r, cuts):
        s, e = max(cs, lo), min(ce, hi)
        if s >= e:
            continue
        todo = [f for f in range(s, e) if f not in done]
        if not todo:
            skipped.append({"cut": i, "camera": cam, "start": s, "end": e, "why": "all frames on disk"})
            continue
        s, e = todo[0], todo[-1] + 1
        step = r["chunking"] if isinstance(r["chunking"], int) else e - s
        for a in range(s, e, step):
            b = min(a + step, e)
            chunks.append({"cut": i, "camera": cam, "cut_start": cs, "start": a, "end": b, "frames": b - a,
                           "preroll": (a - cs) if r["preroll"] == "cut" else 0})
    if r["chunking"] == "none" and chunks:
        # one job: from the first chunk's start to the last chunk's end (the cuts inside are rendered as MRQ shots)
        first, last = chunks[0], chunks[-1]
        chunks = [{**first, "end": last["end"], "frames": last["end"] - first["start"],
                   "camera": "+".join(dict.fromkeys(c["camera"] for c in chunks)), "cuts": [c["cut"] for c in chunks]}]
    cal = {**COST, **(state.get("calibration") or {})}
    for n, c in enumerate(chunks):
        c["id"] = f"{r['name']}_c{n:03d}_{c['start']}"
        c["seconds"] = round(chunk_seconds(r, c, cal), 1)
    total = sum(c["seconds"] for c in chunks)
    return {"name": r["name"], "spec": r, "fps": state.get("fps"), "range": [lo, hi], "chunks": chunks,
            "skipped": skipped, "frames": sum(c["frames"] for c in chunks), "seconds": round(total, 1),
            "boxes": split_boxes(chunks, r["boxes"]) if r["boxes"] > 1 else None}


def sample_seconds(r: dict, cal: dict | None = None) -> float:
    """Estimated GPU seconds per sample at the spec's resolution."""
    cal = {**COST, **(cal or {})}
    mp = r["width"] * r["height"] / (1920 * 1080)
    per = cal["pt_sample_s_1080p"] if r["path_tracer"] else cal["sample_s_1080p"]
    return per * mp * (1 + 0.6 * (len(r["passes"]) - 1))


def chunk_seconds(r: dict, c: dict, cal: dict | None = None) -> float:
    cal = {**COST, **(cal or {})}
    ss = sample_seconds(r, cal)
    rendered = c["frames"] * r["spatial"] * r["temporal"] + r["warmup_render"]
    t = cal["job_overhead_s"] + rendered * ss + (c["preroll"] or r["warmup_engine"]) * cal["engine_frame_s"]
    if r["path_tracer"]:
        t += (c["frames"] + r["warmup_render"]) * cal["pt_denoise_s"]
    return t


def split_boxes(chunks: list, n: int) -> list:
    """Chunks shared out over n boxes, longest first onto the least-loaded box (each chunk stays whole, so every
    box pre-rolls its own chunks); each box's chunks back in sequence order."""
    boxes = [{"box": i, "chunks": [], "seconds": 0.0, "frames": 0} for i in range(max(1, n))]
    for c in sorted(chunks, key=lambda c: -c["seconds"]):
        b = min(boxes, key=lambda b: (b["seconds"], b["box"]))
        b["chunks"].append(c["id"])
        b["seconds"] = round(b["seconds"] + c["seconds"], 1)
        b["frames"] += c["frames"]
    order = {c["id"]: i for i, c in enumerate(chunks)}
    for b in boxes:
        b["chunks"].sort(key=order.get)
    return boxes


# ---------------------------------------------------------------------------------------------------------------------
# guards

def vram_check(r: dict, gpu: dict | None) -> dict:
    """Whether the GPU can take this render: {"ok", "why", "need_gb", "total_gb", "free_gb"}. The path tracer with
    strand hair needs a big GPU (PT_MIN_VRAM_GB); deferred needs ~4 GB free plus ~2 GB per extra 1080p of pixels."""
    mp = r["width"] * r["height"] / (1920 * 1080)
    need = (r["vram"]["path_tracer_min_gb"] if r["path_tracer"] else 4.0 + 2.0 * max(0.0, mp - 1) + 1.0 * (len(r["passes"]) - 1))
    if not gpu or gpu.get("total_gb") is None:
        return {"ok": True, "why": "GPU memory unknown (no nvidia-smi): not checked", "need_gb": need,
                "total_gb": None, "free_gb": None}
    total, free = gpu["total_gb"], gpu.get("free_gb")
    if r["path_tracer"] and total < need:
        why = (f"the path tracer needs >= {need:g} GB of VRAM with strand hair, this GPU has {total:.1f} GB "
               "(an L4 ran out at 1080p: docs/linux/engine.md P5); use preset final (Lumen), hair cards, a 48 GB "
               "GPU, or vram.force")
        return {"ok": bool(r["vram"]["force"]), "why": why, "need_gb": need, "total_gb": total, "free_gb": free}
    if free is not None and not r["path_tracer"] and free < need:
        why = f"{free:.1f} GB of VRAM free, this render wants ~{need:.1f} GB: close other GPU work or restart the editor"
        return {"ok": bool(r["vram"]["force"]), "why": why, "need_gb": need, "total_gb": total, "free_gb": free}
    return {"ok": True, "why": "", "need_gb": need, "total_gb": total, "free_gb": free}


def parse_nvidia_smi(text: str) -> dict | None:
    """`nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits`
    (first GPU) -> {"name", "total_gb", "used_gb", "free_gb", "util_pct"} (MiB converted to GB)."""
    for line in (text or "").strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            tot, used, free = (float(p) * 1048576 / 1e9 for p in parts[1:4])
        except ValueError:
            continue
        util = None
        if len(parts) > 4:
            try:
                util = float(parts[4])
            except ValueError:
                pass
        return {"name": parts[0], "total_gb": round(tot, 2), "used_gb": round(used, 2), "free_gb": round(free, 2),
                "util_pct": util}
    return None


NVIDIA_SMI_ARGS = ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
                   "--format=csv,noheader,nounits"]


# ---------------------------------------------------------------------------------------------------------------------
# reports

def frame_times(mtimes: dict) -> dict:
    """Per-frame wall time from the frames' file times {frame: mtime}: {frame: seconds since the previous frame was
    written}, plus a summary. The first frame of a chunk carries the job start and warm-up; it is left out of the
    steady-state figures."""
    fs = sorted(mtimes)
    per = {f: round(mtimes[f] - mtimes[p], 3) for p, f in zip(fs, fs[1:])}
    vals = sorted(v for v in per.values() if v >= 0)
    if not vals:
        return {"per_frame": per, "median_s": None, "p90_s": None, "max_s": None}
    return {"per_frame": per, "median_s": vals[len(vals) // 2], "p90_s": vals[min(len(vals) - 1, int(len(vals) * 0.9))],
            "max_s": vals[-1]}


# ---------------------------------------------------------------------------------------------------------------------
# one-process rendering (no editor): the command line

def cmdline(editor: str, uproject: str, manifest: str, *, offscreen: bool = True, vulkan: bool | None = None,
            log: str = "", extra: list | None = None) -> list:
    """argv of a command-line MRQ render of a saved queue manifest (MovieRenderPipelineCommandLine.cpp, option 1 with
    a queue): `editor` is UnrealEditor-Cmd(.exe), the manifest a .utxt written by render.manifest. The process loads
    everything from disk, renders, and exits with 0 on success (1 critical, 2 no asset, 3 no config)."""
    argv = [editor, uproject, "MoviePipelineEntryMap", "-game", f"-MoviePipelineConfig={manifest}", "-windowed",
            "-ResX=1280", "-ResY=720", "-Unattended", "-NoSplash", "-NoLoadingScreen", "-NoTextureStreaming",
            "-deterministicaudio", "-audiomixer", "-stdout", "-FullStdOutLogOutput", "-log"]
    if offscreen:
        argv.append("-RenderOffscreen")
    if vulkan or (vulkan is None and not editor.lower().endswith(".exe")):
        argv.append("-vulkan")
    if log:
        argv.append(f"-abslog={log}")
    return argv + list(extra or [])


EXIT_CODES = {0: "success", 1: "critical failure (see the log)", 2: "the sequence asset was not found",
              3: "the config/manifest was not found"}


# ---------------------------------------------------------------------------------------------------------------------
# ffmpeg

def _pattern(r: dict, pass_name: str = "beauty") -> tuple:
    """(ffmpeg %0Nd pattern, extension) of an image pass."""
    ext = _ext(r)
    p = frame_path(r, 0, pass_name, ext)
    pad = r["zero_pad"]
    p = p[: -len(ext) - 1 - pad] + f"%0{pad}d." + ext
    return p, ext


def encode_args(r: dict, out: dict, start: int, end: int, fps: float, *, audio_file: str = "",
                audio_start_s: float = 0.0, ffmpeg: str = "ffmpeg") -> list:
    """argv that encodes frames [start, end) of the beauty pass into one video output `out` ({"kind": h264|h265|prores,
    ...}). Frames must be contiguous (check with missing_frames first). EXR input is linear: it is converted with the
    sRGB transfer so the video looks like the PNG would."""
    if out["kind"] not in VIDEO_KINDS:
        raise SpecError([f"outputs: {out['kind']!r} is not a video kind ({', '.join(VIDEO_KINDS)})"])
    pat, ext = _pattern(r)
    argv = [ffmpeg, "-hide_banner", "-y", "-loglevel", "error", "-framerate", _rate(fps), "-start_number", str(start)]
    if ext == "exr":
        argv += ["-apply_trc", "iec61966_2_1"]
    argv += ["-i", pat]
    if audio_file:
        argv += ["-ss", f"{max(0.0, audio_start_s):.6f}", "-i", audio_file]
    argv += ["-frames:v", str(end - start)]
    kind = out["kind"]
    if kind == "h264":
        argv += ["-c:v", "libx264", "-preset", "slow", "-crf", str(out.get("crf", 18)), "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart"]
    elif kind == "h265":
        argv += ["-c:v", "libx265", "-preset", "slow", "-crf", str(out.get("crf", 18)), "-pix_fmt", "yuv420p10le",
                 "-tag:v", "hvc1", "-movflags", "+faststart"]
    else:
        prof = int(out.get("profile", 3))
        argv += ["-c:v", "prores_ks", "-profile:v", str(prof), "-vendor", "apl0",
                 "-pix_fmt", "yuva444p10le" if prof >= 4 else "yuv422p10le"]
    if audio_file:
        argv += ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "pcm_s24le" if kind == "prores" else "aac"]
        if kind != "prores":
            argv += ["-b:a", "256k"]
        argv += ["-t", f"{(end - start) / fps:.6f}"]
    else:
        argv += ["-an"]
    argv += ["-r", _rate(fps), video_path(r, out)]
    return argv


def video_path(r: dict, out: dict, suffix: str = "") -> str:
    ext = OUTPUT_KINDS[out["kind"]][1]
    name = out.get("file") or f"{r['name']}{suffix}.{ext}"
    if suffix and out.get("file"):
        base, e = os.path.splitext(out["file"])
        name = f"{base}{suffix}{e}"
    return os.path.join(r["out_dir"], name)


def concat_args(parts: list, out_file: str, list_file: str, ffmpeg: str = "ffmpeg") -> tuple:
    """(argv, list file text) joining same-codec video files without re-encoding (ffmpeg's concat demuxer)."""
    text = "".join("file '" + p.replace("'", "'\\''") + "'\n" for p in parts)
    return [ffmpeg, "-hide_banner", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list_file,
            "-c", "copy", "-movflags", "+faststart", out_file], text


def mux_audio_args(video: str, audio: str, out_file: str, *, audio_start_s: float = 0.0, prores: bool = False,
                   ffmpeg: str = "ffmpeg") -> list:
    """argv putting an audio file under a finished video (video copied, audio cut to the video's length)."""
    return [ffmpeg, "-hide_banner", "-y", "-loglevel", "error", "-i", video, "-ss", f"{max(0.0, audio_start_s):.6f}",
            "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            "-c:a", "pcm_s24le" if prores else "aac", *([] if prores else ["-b:a", "256k"]), "-shortest", out_file]


def missing_frames(have, start: int, end: int) -> list:
    """[start, end) runs of frames in [start, end) not in `have`."""
    have = set(have)
    return runs([f for f in range(start, end) if f not in have])


def image_ok(head: bytes, tail: bytes, size: int) -> bool:
    """Whether an image file looks complete from its first and last bytes (a frame cut off by a crash is not): PNG
    ends with its IEND chunk, JPEG with FFD9, EXR starts with its magic and is not tiny, BMP's size matches its
    header."""
    if size <= 0:
        return False
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return tail.endswith(b"IEND\xaeB`\x82")
    if head.startswith(b"\xff\xd8"):
        return tail.rstrip(b"\x00").endswith(b"\xff\xd9")
    if head.startswith(b"\x76\x2f\x31\x01"):
        return size > 256
    if head.startswith(b"BM") and len(head) >= 6:
        return int.from_bytes(head[2:6], "little") == size
    return False


def assemble_wav(parts: list, start: int, end: int, fps: float, out_path: str) -> dict:
    """One WAV for frames [start, end) from chunk WAVs [(path, first frame), ...] placed on the timeline at
    (first frame - start) / fps; gaps are silence, overlaps keep the later chunk. All parts must share a format.
    Returns {"path", "seconds", "parts", "rate", "channels"}."""
    import wave
    parts = sorted(parts, key=lambda p: p[1])
    fmt, data = None, None
    for path, first in parts:
        with wave.open(path, "rb") as w:
            f = (w.getnchannels(), w.getsampwidth(), w.getframerate())
            if fmt is None:
                fmt = f
                frame_bytes = f[0] * f[1]
                data = bytearray(int(round((end - start) / fps * f[2])) * frame_bytes)
            elif f != fmt:
                raise ValueError(f"{path}: {f} differs from the first part's format {fmt} (channels, width, rate)")
            pcm = w.readframes(w.getnframes())
        at = int(round((first - start) / fps * fmt[2])) * frame_bytes
        if at < 0:
            pcm, at = pcm[-at:], 0
        pcm = pcm[: max(0, len(data) - at)]
        data[at: at + len(pcm)] = pcm
    if fmt is None:
        raise ValueError("no audio parts")
    with wave.open(out_path, "wb") as w:
        w.setnchannels(fmt[0])
        w.setsampwidth(fmt[1])
        w.setframerate(fmt[2])
        w.writeframes(bytes(data))
    return {"path": out_path, "seconds": round(len(data) / (fmt[0] * fmt[1] * fmt[2]), 4), "parts": len(parts),
            "rate": fmt[2], "channels": fmt[0]}


def parse_signalstats(text: str, start: int) -> dict:
    """{frame: mean luma 0..255} from ffmpeg `signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-` output
    (frames in input order from `start`)."""
    out, i = {}, start
    for line in (text or "").splitlines():
        if "lavfi.signalstats.YAVG=" in line:
            try:
                out[i] = float(line.split("=", 1)[1])
            except ValueError:
                pass
            i += 1
    return out


def compare_args(a_pattern: str, b_pattern: str, start: int, frames: int, ssim_log: str, psnr_log: str,
                 ffmpeg: str = "ffmpeg", exr: bool = False) -> list:
    """argv comparing two image sequences frame by frame with ffmpeg's ssim and psnr filters (stats files, one line
    per frame); EXR inputs go through the sRGB curve first, like encode_args."""
    def inp(pat):
        return (["-apply_trc", "iec61966_2_1"] if exr else []) + ["-start_number", str(start), "-i", pat]
    esc = [x.replace("\\", "/").replace(":", "\\:").replace("'", "\\'") for x in (ssim_log, psnr_log)]
    return [ffmpeg, "-hide_banner", "-loglevel", "error", *inp(a_pattern), *inp(b_pattern), "-frames:v", str(frames),
            "-lavfi", f"[0:v][1:v]ssim=stats_file='{esc[0]}';[0:v][1:v]psnr=stats_file='{esc[1]}'", "-f", "null", "-"]


def parse_ffmpeg_stats(text: str, key: str, start: int) -> dict:
    """{frame: value} from an ffmpeg ssim (key "All") or psnr (key "psnr_avg") stats file; n is 1-based. 'inf' (two
    identical frames' PSNR) becomes 100.0."""
    out = {}
    for line in (text or "").splitlines():
        parts = dict(p.split(":", 1) for p in line.split() if ":" in p)
        if "n" not in parts or key not in parts:
            continue
        try:
            v = parts[key]
            out[start + int(parts["n"]) - 1] = 100.0 if v.startswith("inf") else float(v)
        except ValueError:
            continue
    return out


def ab_summary(ssim: dict, psnr: dict, min_ssim: float = 0.98, worst: int = 5) -> dict:
    """A check over per-frame SSIM/PSNR of two renders: {"pass", "metric" (min SSIM), "threshold", "why",
    "mean_ssim", "min_psnr", "mean_psnr", "worst": [[frame, ssim, psnr]], "below": [frames]}."""
    fs = sorted(ssim)
    if not fs:
        return {"pass": False, "metric": None, "threshold": min_ssim, "why": "no frames compared", "worst": [],
                "below": []}
    lo = min(ssim[f] for f in fs)
    below = [f for f in fs if ssim[f] < min_ssim]
    ps = [psnr[f] for f in fs if f in psnr]
    order = sorted(fs, key=lambda f: ssim[f])[:worst]
    return {"pass": not below, "metric": round(lo, 5), "threshold": min_ssim,
            "why": (f"{len(below)} of {len(fs)} frames under SSIM {min_ssim} (worst {order[0]}: {ssim[order[0]]:.4f})"
                    if below else f"all {len(fs)} frames at SSIM >= {min_ssim}"),
            "mean_ssim": round(sum(ssim[f] for f in fs) / len(fs), 5), "min_psnr": round(min(ps), 2) if ps else None,
            "mean_psnr": round(sum(ps) / len(ps), 2) if ps else None,
            "worst": [[f, round(ssim[f], 5), psnr.get(f)] for f in order], "below": below}


def frame_qa(luma: dict, *, black_luma: float = 4.0, flicker_ratio: float = 4.0, flicker_min: float = 2.0) -> dict:
    """Black frames (mean luma below black_luma) and flicker (a change from the previous frame over flicker_ratio x
    the median change and over flicker_min, that the next frame does not continue: a one-frame spike, not a cut or
    a fade) from {frame: mean luma}. Returns {"black", "flicker", "median_delta"}."""
    fs = sorted(luma)
    black = [f for f in fs if luma[f] < black_luma]
    d = {f: luma[f] - luma[p] for p, f in zip(fs, fs[1:]) if f == p + 1}
    mags = sorted(abs(x) for x in d.values())
    med = mags[len(mags) // 2] if mags else 0.0
    lim = max(flicker_min, flicker_ratio * med)
    flicker = [f for f, x in d.items() if abs(x) > lim and f + 1 in d and abs(d[f + 1]) > lim and
               (x > 0) != (d[f + 1] > 0)]
    return {"black": black, "flicker": sorted(flicker), "median_delta": round(med, 3)}


def _rate(fps: float) -> str:
    """ffmpeg rate string: 23.976 -> 24000/1001, 29.97 -> 30000/1001, else the number."""
    for n in (24, 30, 60, 120):
        if abs(fps - n * 1000 / 1001) < 0.005:
            return f"{n * 1000}/1001"
    return str(int(fps)) if float(fps).is_integer() else f"{fps:.6f}"


def preset_table() -> dict:
    """Every preset with what it is for and its settings."""
    return {k: dict(v) for k, v in PRESETS.items()}


def estimate(spec: dict, frames: int, state: dict | None = None) -> float:
    """Rough seconds to render `frames` frames as one chunk (for a quick answer before a plan)."""
    r = resolve(spec)
    return round(chunk_seconds(r, {"frames": frames, "preroll": 0}, (state or {}).get("calibration")), 1)


__all__ = ["SPEC_VERSION", "PRESETS", "QUALITY_CVARS", "BASE_CVARS", "PASSES", "OUTPUT_KINDS", "SCHEMA", "SpecError",
           "validate", "resolve", "plan", "runs", "split_boxes", "vram_check", "parse_nvidia_smi", "frame_times", "cmdline",
           "encode_args", "concat_args", "mux_audio_args", "missing_frames", "frame_path", "frames_on_disk",
           "chunk_seconds", "sample_seconds", "estimate", "preset_table", "image_ok", "assemble_wav", "parse_signalstats", "frame_qa", "compare_args", "parse_ffmpeg_stats", "ab_summary"]
