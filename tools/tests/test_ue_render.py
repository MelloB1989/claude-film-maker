"""WP9's render ops against the fake engine (fakeunreal/ext_render.py): MRQ configuration from a spec, chunked and
resumable jobs with pre-roll, reports, guards (unsaved map, VRAM, stalls, a render already running), render.frames,
manifests for one-process renders, and the older render.mrq/render.progress pair."""
from __future__ import annotations

import json
import os

import pytest

from fakeunreal import drive, run_op

SEQ = "/Game/Reel/SEQ_T"
LEVEL = "/Game/Maps/Stage"
CUTS = [["CamA", 0, 10], ["CamB", 10, 16], ["CamC", 16, 30]]


@pytest.fixture
def stage(ue, fmb, monkeypatch, tmp_path):
    ue.add_sequence(SEQ, start=0, end=30, fps=24, cuts=CUTS)
    ue.add_asset(LEVEL, "World")
    monkeypatch.setattr(fmb.seq, "cuts", lambda path: [list(c) for c in ue.load_asset(path).cuts])
    render = fmb.render
    monkeypatch.setattr(render, "gpu_info", lambda max_age_s=2.0: {"name": "Fake L4", "total_gb": 24.0,
                                                                   "used_gb": 4.0, "free_gb": 20.0, "util_pct": 50})
    out = str(tmp_path / "out")
    return {"ue": ue, "render": render, "out": out, "spec": {"sequence": SEQ, "level": LEVEL, "out_dir": out,
                                                              "preset": "draft"}}


def pngs(d):
    return sorted(f for f in os.listdir(d) if f.endswith(".png")) if os.path.isdir(d) else []


def test_job_renders_every_cut_and_writes_a_report(stage):
    ue = stage["ue"]
    rep = run_op("render.job", spec=stage["spec"])
    assert rep["status"] == "ok" and rep["changed"] and rep["frames"] == 30
    assert len(pngs(stage["out"])) == 30 and pngs(stage["out"])[0] == "0000.png"
    assert [(j["name"], j["executor"]) for j in ue.mrq.jobs] == [
        ("SEQ_T_c000_0", "MoviePipelinePIEExecutor"), ("SEQ_T_c001_10", "MoviePipelinePIEExecutor"),
        ("SEQ_T_c002_16", "MoviePipelinePIEExecutor")]
    with open(rep["report"]) as f:
        disk = json.load(f)
    assert disk["status"] == "ok" and len(disk["chunks"]) == 3 and disk["chunks"][0]["vram_peak_gb"] == 4.0
    assert disk["chunks"][1]["missing"] == [] and disk["gpu"]["name"] == "Fake L4"
    assert ue.dialogs == []


def test_job_configures_mrq_from_the_spec(stage):
    ue = stage["ue"]
    spec = {**stage["spec"], "preset": "final", "frames": [12, 20], "aa_method": "tsr",
            "cvars": {"r.Foo": 2}, "outputs": [{"kind": "exr", "compression": "zip"}, {"kind": "wav"}]}
    rep = run_op("render.job", spec=spec)
    assert rep["status"] == "ok"
    first = ue.mrq.jobs[0]
    s = first["settings"]
    o = s["MoviePipelineOutputSetting"]
    assert (o.get_editor_property("custom_start_frame"), o.get_editor_property("custom_end_frame")) == (12, 16)
    assert o.get_editor_property("output_resolution") == ue.IntPoint(1920, 1080)
    aa = s["MoviePipelineAntiAliasingSetting"]
    assert aa.get_editor_property("temporal_sample_count") == 8 and aa.get_editor_property("render_warm_up_count") == 32
    assert aa.get_editor_property("use_camera_cut_for_warm_up") is True  # 12 is mid-cut: pre-roll from 10
    assert ue.mrq.jobs[1]["settings"]["MoviePipelineAntiAliasingSetting"].get_editor_property(
        "use_camera_cut_for_warm_up") is False  # starts on its cut
    assert aa.get_editor_property("anti_aliasing_method") == "AAM_TSR"
    cv = s["MoviePipelineConsoleVariableSetting"].cvars
    assert cv["r.Foo"] == 2 and cv["r.HairStrands.SkyLighting"] == 0 and cv["r.DepthOfFieldQuality"] == 4
    assert s["MoviePipelineImageSequenceOutput_EXR"].get_editor_property("compression") == "ZIP"
    assert first["map"] == LEVEL and first["sequence"] == SEQ
    wavs = sorted(os.listdir(os.path.join(stage["out"], "_render", "audio")))
    assert wavs == ["12-16.wav", "16-20.wav"]


def test_rerun_is_a_no_op_and_resume_after_a_crash(stage):
    ue = stage["ue"]
    ue.mrq.fail_at = 13
    rep = run_op("render.job", spec=stage["spec"])
    assert rep["status"] == "failed" or rep["status"] == "incomplete"
    crashed = rep["chunks"][1]
    assert crashed["status"] == "incomplete" and crashed["missing"] == [[13, 16]] and "fake crash" in crashed["errors"][0]
    # a frame cut off mid-write is not counted as done
    with open(os.path.join(stage["out"], "0012.png"), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\nhalf")
    ue.mrq.fail_at = None
    n = len(ue.mrq.jobs)
    rep = run_op("render.job", spec=stage["spec"])
    assert rep["status"] == "ok"
    resumed = ue.mrq.jobs[n:]
    assert [(j["settings"]["MoviePipelineOutputSetting"].get_editor_property("custom_start_frame"),
             j["settings"]["MoviePipelineAntiAliasingSetting"].get_editor_property("use_camera_cut_for_warm_up"))
            for j in resumed] == [(12, True)]
    again = run_op("render.job", spec=stage["spec"])
    assert again["changed"] is False and again["chunks"] == [] and len(ue.mrq.jobs) == n + 1


def test_plan_reads_the_sequence_and_the_disk(stage):
    p = run_op("render.plan", spec={**stage["spec"], "boxes": 2})
    assert [c["camera"] for c in p["chunks"]] == ["CamA", "CamB", "CamC"] and p["vram"]["ok"]
    assert len(p["boxes"]) == 2 and p["frames"] == 30


def test_unsaved_level_is_refused_before_anything_starts(stage):
    from fmbridge.errors import OpError
    with pytest.raises(OpError, match="not saved on disk") as e:
        run_op("render.job", spec={**stage["spec"], "level": "/Game/Maps/Nope"})
    assert e.value.code == "conflict" and "level.save" in e.value.hint and stage["ue"].mrq.jobs == []


def test_bad_spec_is_bad_args_with_every_error(stage):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("render.job", spec={**stage["spec"], "preset": "fnal", "widht": 3})
    assert e.value.code == "bad_args" and len(e.value.details["errors"]) == 2


def test_path_tracer_refused_on_a_small_gpu(stage):
    from fmbridge.errors import OpError
    with pytest.raises(OpError, match="path tracer needs") as e:
        run_op("render.job", spec={**stage["spec"], "preset": "pathtrace"})
    assert e.value.code == "unsupported" and stage["ue"].mrq.jobs == []


def test_vram_abort_cancels_the_render(stage, monkeypatch):
    monkeypatch.setattr(stage["render"], "gpu_info", lambda max_age_s=2.0: {"name": "L4", "total_gb": 24.0,
                                                                            "used_gb": 23.5, "free_gb": 0.5})
    rep = run_op("render.job", spec={**stage["spec"], "vram": {"force": True}})
    assert rep["status"] == "vram_abort" and len(rep["chunks"]) == 1 and "VRAM 23.5" in rep["errors"][0]


def test_a_render_that_never_starts_stalls_out(stage):
    stage["ue"].mrq.hang = True  # the executor claims to run but writes nothing
    rep = run_op("render.job", spec={**stage["spec"], "shots": ["CamB"]}, stall_s=0.0)
    assert rep["status"] == "stalled" and "no new frame" in rep["errors"][0]


def test_process_executor_saves_or_refuses_dirty_packages(stage, monkeypatch):
    from fmbridge.errors import OpError
    ue = stage["ue"]
    ue.dirty["maps"].append(LEVEL)
    ue.stub("EditorLoadingAndSavingUtils.save_dirty_packages", True)
    with pytest.raises(OpError, match="unsaved packages"):
        run_op("render.job", spec={**stage["spec"], "executor": "process", "save_dirty": False})
    rep = run_op("render.job", spec={**stage["spec"], "executor": "process", "shots": ["CamA"]})
    assert rep["saved"] == [LEVEL] and ue.called("EditorLoadingAndSavingUtils.save_dirty_packages")
    assert ue.mrq.jobs[-1]["executor"] == "MoviePipelineNewProcessExecutor"


def test_frames_renders_only_what_is_asked_and_reuses(stage):
    ue = stage["ue"]
    res = run_op("render.frames", sequence=SEQ, level=LEVEL, frames=[3, 4, 12, 20], out_dir=stage["out"])
    assert sorted(res["frames"]) == [3, 4, 12, 20] and res["cameras"] == {3: "CamA", 4: "CamA", 12: "CamB", 20: "CamC"}
    assert all(p.endswith(".jpg") for p in res["frames"].values()) and (res["width"], res["height"]) == (960, 540)
    starts = [(j["settings"]["MoviePipelineOutputSetting"].get_editor_property("custom_start_frame"),
               j["settings"]["MoviePipelineOutputSetting"].get_editor_property("custom_end_frame")) for j in ue.mrq.jobs]
    assert starts == [(3, 5), (12, 13), (20, 21)]
    assert ue.mrq.jobs[1]["settings"]["MoviePipelineAntiAliasingSetting"].get_editor_property("use_camera_cut_for_warm_up")
    again = run_op("render.frames", sequence=SEQ, level=LEVEL, frames=[3, 12], out_dir=stage["out"])
    assert again["changed"] is False and len(ue.mrq.jobs) == 3


def test_frames_outside_the_cuts(stage):
    from fmbridge.errors import OpError
    with pytest.raises(OpError, match="outside every camera cut"):
        run_op("render.frames", sequence=SEQ, level=LEVEL, frames=[99], out_dir=stage["out"])


def test_passes_turn_on_aovs_and_lighting_passes(stage):
    ue = stage["ue"]
    rep = run_op("render.job", spec={**stage["spec"], "shots": ["CamB"], "passes": ["depth", "lighting_only"]})
    assert rep["status"] == "ok"
    s = ue.mrq.jobs[0]["settings"]
    ppm = s["MoviePipelineDeferredPassBase"].get_editor_property("additional_post_process_materials")
    on = {str(p.get_editor_property("material")).rsplit(".", 1)[-1]: p.get_editor_property("enabled") for p in ppm}
    assert on == {"MovieRenderQueue_WorldDepth": True, "MovieRenderQueue_MotionVectors": False}
    assert "MoviePipelineDeferredPass_LightingOnly" in s
    assert sorted(os.listdir(stage["out"])) == ["FinalImage", "LightingOnly", "MovieRenderQueue_WorldDepth", "_render"]


def test_manifest_writes_one_per_chunk(stage, monkeypatch):
    ue = stage["ue"]
    src = os.path.join(stage["out"], "QueueManifest.utxt")
    os.makedirs(stage["out"], exist_ok=True)
    with open(src, "w") as f:
        f.write("manifest")
    ue.stub("MoviePipelineEditorBlueprintLibrary.save_queue_to_manifest_file", lambda q: (q, src))
    res = run_op("render.manifest", spec={**stage["spec"], "executor": "cmdline"})
    assert [c["id"] for c in res["chunks"]] == ["SEQ_T_c000_0", "SEQ_T_c001_10", "SEQ_T_c002_16"]
    first = res["chunks"][0]
    assert os.path.isfile(first["manifest"]) and f"-MoviePipelineConfig={first['manifest']}" in first["argv"]
    assert "-game" in first["argv"] and res["exit_codes"][3]


def test_status_cancel_describe(stage):
    st = run_op("render.status")
    assert st["status"] == "idle" and st["rendering"] is False
    assert run_op("render.cancel")["changed"] is False
    run_op("render.job", spec={**stage["spec"], "shots": ["CamB"]})
    d = run_op("render.describe", out_dir=stage["out"])
    assert d["report"]["status"] == "ok" and d["frames_on_disk"] == 6
    assert run_op("render.status")["status"] == "ok"


def test_cancel_mid_job(stage, fmb):
    gen = fmb.call("render.job", spec=stage["spec"])
    for _ in range(4):
        next(gen)
        stage["ue"].tick()
    assert run_op("render.status")["status"] == "running"
    run_op("render.cancel")
    rep, _ = drive(gen)
    assert rep["status"] == "cancelled" and len(rep["chunks"]) == 1


def test_two_jobs_conflict(stage, fmb):
    from fmbridge.errors import OpError
    gen = fmb.call("render.job", spec=stage["spec"])
    next(gen)
    with pytest.raises(OpError, match="already running"):
        run_op("render.job", spec=stage["spec"])
    run_op("render.cancel")
    drive(gen)


def test_old_mrq_and_progress_still_work(stage):
    ue = stage["ue"]
    res = run_op("render.mrq", sequence=SEQ, level=LEVEL, out_dir=stage["out"], start=12, end=16, preroll_from=10)
    assert res["started"] and res["changed"]
    aa = ue.mrq.jobs[0]["settings"]["MoviePipelineAntiAliasingSetting"]
    assert aa.get_editor_property("engine_warm_up_count") == 32 and aa.get_editor_property("use_camera_cut_for_warm_up")
    assert run_op("render.progress", out_dir=stage["out"])["rendering"] is True
    ue.tick(10)
    p = run_op("render.progress", out_dir=stage["out"], expected=4)
    assert p == {"frames": 4, "expected": 4, "rendering": False, "done": True}


def test_encode_needs_complete_frames_and_ffmpeg(stage, monkeypatch):
    from fmbridge.errors import OpError
    run_op("render.job", spec={**stage["spec"], "shots": ["CamB"]})
    with pytest.raises(OpError, match="frames missing") as e:
        run_op("render.encode", spec=stage["spec"], start=8, end=16)
    assert e.value.details["missing"] == [[8, 10]]
    monkeypatch.setattr(stage["render"].shutil, "which", lambda name: None)
    with pytest.raises(OpError, match="ffmpeg is not installed") as e:
        run_op("render.encode", spec=stage["spec"], start=10, end=16)
    assert e.value.code == "unsupported"


def test_encode_runs_ffmpeg_with_the_assembled_audio(stage, monkeypatch):
    render = stage["render"]
    spec = {**stage["spec"], "preset": "final", "shots": ["CamB"]}
    run_op("render.job", spec=spec)
    calls = []

    def fake_run(argv, timeout_s=3600.0):
        calls.append(argv)
        with open(argv[-1], "wb") as f:
            f.write(b"video")
        return 0, ""
        yield  # a generator, like the real one

    monkeypatch.setattr(render, "_run_proc", fake_run)
    monkeypatch.setattr(render, "_ffmpeg", lambda: "ffmpeg")
    res = run_op("render.encode", spec=spec)
    v = res["videos"][0]
    assert (v["kind"], v["start"], v["end"], v["frames"]) == ("h264", 10, 16, 6) and v["audio"].endswith("_SEQ_T_10-16.wav")
    assert "-start_number" in calls[0] and calls[0][calls[0].index("-start_number") + 1] == "10"


def test_bridge_cancel_closes_the_job_and_stops_mrq(stage, fmb):
    gen = fmb.call("render.job", spec=stage["spec"])
    got = [next(gen) for _ in range(3)]
    assert got[-1]["message"].startswith("SEQ_T_c000_0 (CamA)") and 0 <= got[-1]["progress"] <= 1
    gen.close()  # what the server's jobs.cancel does
    assert run_op("render.status")["status"] == "cancelled" and stage["ue"].mrq.active is None
    with open(os.path.join(stage["out"], "_render", "SEQ_T.report.json")) as f:
        assert json.load(f)["status"] == "cancelled"


def test_frames_overwrite_renders_again(stage):
    ue = stage["ue"]
    run_op("render.frames", sequence=SEQ, level=LEVEL, frames=[3], out_dir=stage["out"])
    res = run_op("render.frames", sequence=SEQ, level=LEVEL, frames=[3], out_dir=stage["out"], overwrite=True)
    assert res["changed"] and len(ue.mrq.jobs) == 2
