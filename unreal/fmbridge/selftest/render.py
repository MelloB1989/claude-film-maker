"""WP9's acceptance test: every render op on a scratch scene, on the GPU box, with numbers and frames to look at.

It builds a floor, a light, a cube that falls under physics and two cine cameras, and a 48-frame sequence at 24 fps
cut A [0, 24) / B [24, 48). Then it proves:

- render.presets / render.gpu / render.plan answer (two chunks, one per cut, an estimate, the VRAM guard);
- render.job renders every frame (PNG, 480x270, draft samples) and writes a report with time per frame and VRAM;
  a second run renders nothing (changed false): the job converges;
- resume: six frames deleted mid-shot B are rendered again as one chunk [30, 36) pre-rolled from 24, and match the
  full-shot frames (PSNR); the same chunk with preroll none is measured too: the falling cube is where the full-shot
  render had it only with the pre-roll (the cloth rule of docs/linux/engine.md P6, on physics);
- render.frames gives the frames asked for, with their camera;
- AOVs: depth and motion vectors next to the beauty pass; an EXR (16-bit half) frame;
- the new-process executor renders after saving the level (the old unsaved-level stall); render.manifest writes a
  one-process command line, and the cmdline executor renders two frames with no editor in the loop;
- render.encode makes an H.264 with ffmpeg (skipped without ffmpeg on the box);
- the path tracer is refused on a GPU under 40 GB, or renders two frames on a bigger one;
- render.cancel stops a job, and a re-run resumes it.

Takes ~4-6 min on an L4 (the cmdline step starts a second engine process: ~1-2 min with a warm DDC).
Needs: GPU. No Epic login, no assets (engine basic shapes only). Writes under /Game/_Selftest/render and
Saved/Selftest/render; leaves nothing else.
"""
from __future__ import annotations

import glob
import os
import shutil

import unreal

REQUIRES = ["gpu"]
AREAS = ["render"]
TIMEOUT = 1500

W, H = 480, 270


def _scratch(t) -> str:
    s = getattr(t, "scratch", None)
    s = s() if callable(s) else s
    return str(s or "/Game/_Selftest/render").rstrip("/")


def _out_root() -> str:
    return os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Selftest", "render")


def _psnr(a_path: str, b_path: str):
    from fmbridge.qa import compare, image
    return compare.psnr(image.read(a_path), image.read(b_path))


def _build(t, root: str, prefix: str) -> dict:
    floor, cube, cam_a, cam_b, key = (prefix + n for n in ("Floor", "Cube", "CamA", "CamB", "Key"))
    t.op("level.spawn", label=floor, shape="plane", loc=[0, 0, 0], scale=[20, 20, 1])
    t.op("level.spawn", label=cube, shape="cube", loc=[0, 0, 450])  # in camera B's view while it falls
    from fmbridge.ops.level import actor
    comp = actor(cube).get_component_by_class(unreal.StaticMeshComponent)
    comp.set_mobility(unreal.ComponentMobility.MOVABLE)
    comp.set_simulate_physics(True)  # falls in PIE: state that depends on how long the world has run
    t.op("look.light", label=key, kind="rect", loc=[300, -200, 600], look_at=[0, 0, 100], intensity=40.0)
    t.op("look.camera", label=cam_a, loc=[900, 0, 300], look_at=[0, 0, 300], focal=24.0)
    t.op("look.camera", label=cam_b, loc=[0, 900, 300], look_at=[0, 0, 300], focal=24.0)
    seq = root + "/SEQ_Render"
    t.op("seq.new", path=seq, start=0, end=48, fps=24, replace=True)
    t.op("seq.camera_cuts", path=seq, cuts=[[cam_a, 0], [cam_b, 24]])
    # MRQ renders only a saved map (day 1: render.job refused the scratch level as unsaved)
    t.check("scratch level saved", bool(t.op("level.save")), True)
    level = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name().split(".")[0]
    return {"seq": seq, "level": level, "cams": [cam_a, cam_b]}


def run(t):
    root = _scratch(t)
    prefix = getattr(t, "prefix", "ST_render_")
    out = _out_root()
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)

    pre = t.op("render.presets")
    t.check("presets", sorted(pre), sorted(["preview", "draft", "final", "final_exr", "4k", "pathtrace"]))
    g = t.op("render.gpu")
    t.ok("render.gpu sees the GPU", bool(g.get("gpu")), detail=str(g))
    if g.get("gpu"):
        t.metric("vram_total_gb", g["gpu"]["total_gb"], "GB")
        t.metric("vram_used_idle_gb", g["gpu"]["used_gb"], "GB")
    t.raises("a bad spec is bad_args", "render.plan", code="bad_args", spec={"sequence": "/Game/x", "out_dir": out,
                                                                            "preset": "fnal"})

    scene = _build(t, root, prefix)
    seq, level = scene["seq"], scene["level"]
    t.check("seq.cuts", [c[1:] for c in t.op("seq.cuts", path=seq)], [[0, 24], [24, 48]])
    full = os.path.join(out, "full")
    spec = {"sequence": seq, "level": level, "out_dir": full, "preset": "draft", "width": W, "height": H,
            "temporal": 1, "warmup_render": 0, "name": "full"}

    p = t.op("render.plan", spec=spec)
    t.check("plan: one chunk per cut", [(c["start"], c["end"], c["preroll"]) for c in p["chunks"]],
            [[0, 24, 0], [24, 48, 0]])
    t.ok("plan: VRAM guard passes for deferred", p["vram"]["ok"], detail=str(p["vram"]))
    t.metric("plan_estimate_s", p["seconds"], "s")

    rep = yield from t.op("render.job", spec=spec)
    t.check("job ok", rep["status"], "ok")
    t.check("job frames", rep["frames"], 48)
    t.ok("report on disk", os.path.isfile(rep["report"]), detail=rep["report"])
    m = rep.get("measured") or {}
    t.metric("s_per_frame_480p_draft", m.get("s_per_frame"), "s")
    t.metric("sample_s_1080p_measured", m.get("sample_s_1080p"), "s")
    t.metric("vram_peak_gb", rep.get("vram_peak_gb"), "GB")
    t.metric("job_s", rep["seconds"], "s")
    if hasattr(t, "artifact"):
        t.artifact(rep["report"])
        for f in (5, 30):
            t.artifact(os.path.join(full, f"{f:04d}.png"))

    again = yield from t.op("render.job", spec=spec)
    t.check("re-run converges (nothing rendered)", [again["changed"], again["frames"]], [False, 0])

    # resume mid-shot with pre-roll, and the same chunk cold
    keep = os.path.join(out, "orig")
    os.makedirs(keep, exist_ok=True)
    for f in range(30, 36):
        shutil.copy(os.path.join(full, f"{f:04d}.png"), keep)
        os.remove(os.path.join(full, f"{f:04d}.png"))
    p = t.op("render.plan", spec=spec)
    t.check("resume plans one pre-rolled chunk", [(c["start"], c["end"], c["preroll"]) for c in p["chunks"]],
            [[30, 36, 6]])
    rep = yield from t.op("render.job", spec=spec)
    t.check("resume renders the six frames", [rep["status"], rep["frames"]], ["ok", 6])
    cold = os.path.join(out, "cold")
    yield from t.op("render.job", spec={**spec, "out_dir": cold, "frames": [30, 36], "preroll": "none", "name": "cold"})
    pre_p = [_psnr(os.path.join(keep, f"{f:04d}.png"), os.path.join(full, f"{f:04d}.png")) for f in range(30, 36)]
    cold_p = [_psnr(os.path.join(keep, f"{f:04d}.png"), os.path.join(cold, f"{f:04d}.png")) for f in range(30, 36)]
    t.metric("psnr_preroll_vs_full_min", round(min(pre_p), 2), "dB")
    t.metric("psnr_cold_vs_full_min", round(min(cold_p), 2), "dB")
    t.ok("pre-rolled chunk matches the full-shot render (PSNR >= 35 dB)", min(pre_p) >= 35.0, detail=str(pre_p))
    t.ok("pre-roll is closer to the full shot than a cold start", min(pre_p) >= min(cold_p), detail=f"{pre_p} {cold_p}")
    ab = yield from t.op("render.compare", a=keep, b=full, frames=[30, 36], sheet=os.path.join(out, "ab_worst.png"))
    t.check("render.compare: pre-rolled chunk vs full shot passes", ab["pass"], True)
    t.metric("ab_min_ssim", ab["metric"])
    t.metric("ab_method", ab["method"])

    # frames for stills
    fr = yield from t.op("render.frames", sequence=seq, level=level, frames=[5, 30], out_dir=os.path.join(out, "stills"),
                         preset="draft", width=W, height=H)
    t.check("render.frames cameras", fr["cameras"], {5: scene["cams"][0], 30: scene["cams"][1]})
    t.ok("render.frames files", all(os.path.isfile(v) for v in fr["frames"].values()), detail=str(fr["frames"]))

    # AOVs and EXR
    aov = os.path.join(out, "aov")
    rep = yield from t.op("render.job", spec={**spec, "out_dir": aov, "name": "aov", "frames": [24, 28],
                                              "passes": ["depth", "motion_vectors"],
                                              "outputs": [{"kind": "exr"}]})
    t.check("AOV job ok", rep["status"], "ok")
    dirs = sorted(d for d in os.listdir(aov) if not d.startswith("_"))
    # live 5.8 names a post-process pass "FinalImage" + its material (FinalImageMovieRenderQueue_MotionVectors): accept
    # either spelling, require the three passes
    want = ("MotionVectors", "WorldDepth")
    t.check("AOV folders", [dirs[0] if dirs else None] + [any(d.endswith(w) for d in dirs) for w in want],
            ["FinalImage", True, True])
    t.check("EXR frames per pass", [len(glob.glob(os.path.join(aov, d, "*.exr"))) for d in dirs], [4, 4, 4])

    # executors: a separate process after saving, and a command line with no editor. The command line takes MRQ's
    # queue manifest, or (5.8 on Linux has no manifest writer in Python) the queue saved as an asset. PIE stays the
    # supported route (DECISIONS, day 1): an executor that is unsupported in this editor is a note, not a failure
    from ..errors import OpError
    try:
        proc = os.path.join(out, "process")
        rep = yield from t.op("render.job", spec={**spec, "out_dir": proc, "name": "process", "frames": [0, 2],
                                                  "executor": "process", "save_dirty": True})
        t.check("new-process executor renders (no save prompt stall)", [rep["status"], rep["frames"]], ["ok", 2])
        t.metric("process_job_s", rep["seconds"], "s")
        man = t.op("render.manifest", spec={**spec, "out_dir": os.path.join(out, "cmd"), "name": "cmd", "frames": [0, 2],
                                            "executor": "cmdline"})
        from ..ops.assets import EAL
        m0 = man["chunks"][0]["manifest"] if man["chunks"] else ""
        t.ok("manifest written (a .utxt or a saved queue asset)",
             os.path.isfile(m0) or (m0.startswith("/Game/") and bool(EAL.does_asset_exist(
                 m0.split(".")[0]))), detail=str(man)[:500])
        t.metric("manifest_kind", "asset" if m0.startswith("/Game/") else "file")
        rep = yield from t.op("render.job", spec={**spec, "out_dir": os.path.join(out, "cmd"), "name": "cmd",
                                                  "frames": [0, 2], "executor": "cmdline"}, stall_s=600.0)
        t.check("command-line render (one process, no editor)", [rep["status"], rep["frames"]], ["ok", 2])
        t.metric("cmdline_job_s", rep["seconds"], "s")
        if rep["chunks"] and rep["chunks"][0].get("log") and hasattr(t, "artifact"):
            t.artifact(rep["chunks"][0]["log"])
    except OpError as e:
        if e.code != "unsupported":
            raise
        # DECISIONS (day 1): the in-editor PIE executor is the supported render route; without the MRQ editor library
        # the other two are unsupported by decision, noted here rather than failed
        t.note(f"new-process / command-line executors unsupported in this editor (PIE is the route): {e.message}")

    # encode
    if shutil.which("ffmpeg"):
        enc = yield from t.op("render.encode", spec=spec, outputs=[{"kind": "h264", "audio": False}])
        v = enc["videos"][0]
        t.check("H.264 of 48 frames", [v["frames"], v["bytes"] > 1000], [48, True])
    else:
        t.note("no ffmpeg on the box: render.encode not exercised (apt-get install -y ffmpeg)")

    # path tracer guard
    total = (g.get("gpu") or {}).get("total_gb") or 0
    pt = {**spec, "out_dir": os.path.join(out, "pt"), "name": "pt", "preset": "pathtrace", "width": W, "height": H,
          "frames": [24, 26], "spatial": 4}
    if total and total < 40:
        try:
            yield from t.op("render.job", spec=pt)
            t.ok("path tracer refused under 40 GB", False, detail="it rendered")
        except Exception as e:
            t.check("path tracer refused under 40 GB", getattr(e, "code", type(e).__name__), "unsupported")
    elif total:
        rep = yield from t.op("render.job", spec=pt)
        t.check("path tracer renders on a big GPU", rep["status"], "ok")
        t.metric("pt_vram_peak_gb", rep.get("vram_peak_gb"), "GB")

    # cancel, then resume
    # Day 1 on an L4: the 48 draft frames finished inside the fixed 40 ticks, so the cancel landed after the last frame
    # and the job honestly reported ok. Make the job slow (temporal 16) and cancel once frames are landing.
    can = {**spec, "out_dir": os.path.join(out, "cancel"), "name": "cancel", "temporal": 16}
    job = t.op("render.job", spec=can)
    first = None
    try:
        for _ in range(3000):
            next(job)
            yield 0.05
            if (t.op("render.status").get("chunk_frames") or 0) >= 2:
                break
        t.check("cancel", t.op("render.cancel")["changed"], True)
        while True:
            next(job)
            yield
    except StopIteration as e:
        first = e.value
    t.check("cancelled job reports cancelled", (first or {}).get("status"), "cancelled")
    rep = yield from t.op("render.job", spec=can)
    t.check("re-run after cancel completes", rep["status"], "ok")
    st = t.op("render.status")
    t.check("render.status after", st["status"], "ok")
    d = t.op("render.describe", out_dir=full)  # (no name=: it would collide with t.op(name, ...))
    t.check("render.describe sees the report", d["report"]["status"], "ok")
    return {"out": out}
