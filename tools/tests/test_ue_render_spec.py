"""WP9's pure render logic (unreal/fmbridge/render_spec.py): schema and validation, presets, chunk planning with
resume and pre-roll, box splitting, VRAM guard, reports, the command line and ffmpeg argv. No engine."""
from __future__ import annotations

import importlib.util
import json
import struct
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("render_spec", ROOT / "unreal" / "fmbridge" / "render_spec.py")
rs = importlib.util.module_from_spec(_spec)
sys.modules["render_spec_under_test"] = rs
_spec.loader.exec_module(rs)

BASE = {"sequence": "/Game/Reel/SEQ_Reel", "out_dir": "/srv/r/reel"}
CUTS = [["CamA", 0, 100], ["CamB", 100, 160], ["CamC", 160, 300]]
STATE = {"playback": [0, 300], "fps": 24.0, "cuts": CUTS}


def spec(**kw):
    return {**BASE, **kw}


def test_schema_file_matches_the_module():
    on_disk = json.loads((ROOT / "tools/filmtools/unreal/schemas/render.schema.json").read_text())
    assert on_disk == json.loads(json.dumps(rs.SCHEMA))


def test_every_schema_property_has_a_description():
    def walk(s, path):
        for k, v in s.get("properties", {}).items():
            assert v.get("description"), f"{path}.{k} has no description"
            walk(v, f"{path}.{k}")
        if isinstance(s.get("items"), dict):
            walk(s["items"], path + "[]")
    walk(rs.SCHEMA, "render")


def test_minimal_spec_resolves_to_final():
    r = rs.resolve(spec())
    assert r["preset"] == "final" and (r["width"], r["height"], r["temporal"]) == (1920, 1080, 8)
    assert r["name"] == "SEQ_Reel" and r["passes"] == ["beauty"] and r["file_name"] == "{frame_number}"
    assert r["cvars"]["r.HairStrands.SkyLighting"] == 0 and r["cvars"]["t.MaxFPS"] == 0
    assert r["cvars"]["r.DepthOfFieldQuality"] == 4  # film quality


def test_preset_overrides_and_user_cvars_win():
    r = rs.resolve(spec(preset="preview", width=640, height=360, cvars={"r.HairStrands.SkyLighting": 1}))
    assert (r["width"], r["height"], r["temporal"]) == (640, 360, 1)
    assert "r.DepthOfFieldQuality" not in r["cvars"] and r["cvars"]["r.HairStrands.SkyLighting"] == 1


@pytest.mark.parametrize("bad, needle", [
    ({"preset": "fnal"}, "did you mean 'final'"),
    ({"widht": 100}, "did you mean 'width'"),
    ({"frames": [10, 5]}, "end 5 must be after start 10"),
    ({"temporal": 0}, "below the minimum"),
    ({"outputs": [{"kind": "gif"}]}, "is not one of"),
    ({"sequence": "Game/x"}, "does not match"),
    ({"chunking": "per-shot"}, "is not shot, none"),
    ({"passes": ["beauty", "beauty"]}, "unique"),
])
def test_validation_errors_are_actionable(bad, needle):
    errs = rs.validate(spec(**bad))
    assert any(needle in e for e in errs), errs


def test_required_keys():
    errs = rs.validate({"sequence": "/Game/S"})
    assert any(e.startswith("spec.out_dir: required") for e in errs)


def test_several_passes_use_render_pass_folders():
    r = rs.resolve(spec(passes=["depth", "object_id"]))
    assert r["passes"] == ["beauty", "depth", "object_id"] and r["file_name"] == "{render_pass}/{frame_number}"
    assert rs.frame_path(r, 7).replace("\\", "/") == "/srv/r/reel/FinalImage/0007.png"
    assert rs.frame_path(r, 7, "depth").replace("\\", "/").endswith("MovieRenderQueue_WorldDepth/0007.png")
    with pytest.raises(rs.SpecError, match="render_pass"):
        rs.resolve(spec(passes=["depth"], file_name="{frame_number}"))


def test_needs_an_image_output_and_no_lighting_passes_with_path_tracer():
    with pytest.raises(rs.SpecError, match="image output"):
        rs.resolve(spec(outputs=[{"kind": "h264"}]))
    with pytest.raises(rs.SpecError, match="deferred-renderer"):
        rs.resolve(spec(preset="pathtrace", passes=["unlit"]))


def test_plan_one_chunk_per_cut_with_estimates():
    p = rs.plan(rs.resolve(spec()), STATE)
    assert [(c["camera"], c["start"], c["end"], c["preroll"]) for c in p["chunks"]] == [
        ("CamA", 0, 100, 0), ("CamB", 100, 160, 0), ("CamC", 160, 300, 0)]
    assert p["frames"] == 300 and p["seconds"] > 300 * 0.7
    assert p["chunks"][0]["id"] == "SEQ_Reel_c000_0"


def test_plan_range_mid_shot_prerolls_from_the_cut_start():
    p = rs.plan(rs.resolve(spec(frames=[130, 200])), STATE)
    assert [(c["start"], c["end"], c["preroll"]) for c in p["chunks"]] == [(130, 160, 30), (160, 200, 0)]
    p = rs.plan(rs.resolve(spec(frames=[130, 200], preroll="none")), STATE)
    assert [c["preroll"] for c in p["chunks"]] == [0, 0]


def test_resume_skips_done_frames_and_starts_at_the_first_missing():
    done = list(range(0, 100)) + list(range(100, 140)) + [150, 151]
    p = rs.plan(rs.resolve(spec()), {**STATE, "done": done})
    assert [(c["camera"], c["start"], c["end"], c["preroll"]) for c in p["chunks"]] == [
        ("CamB", 140, 160, 40), ("CamC", 160, 300, 0)]
    assert p["skipped"] == [{"cut": 0, "camera": "CamA", "start": 0, "end": 100, "why": "all frames on disk"}]
    # overwrite ignores what is on disk
    p = rs.plan(rs.resolve(spec(overwrite=True)), {**STATE, "done": done})
    assert len(p["chunks"]) == 3
    # a finished render plans nothing (the job converges)
    p = rs.plan(rs.resolve(spec()), {**STATE, "done": list(range(300))})
    assert p["chunks"] == [] and p["frames"] == 0


def test_chunking_by_frame_count_prerolls_every_later_chunk():
    p = rs.plan(rs.resolve(spec(chunking=50, shots=["CamC"])), STATE)
    assert [(c["start"], c["end"], c["preroll"]) for c in p["chunks"]] == [(160, 210, 0), (210, 260, 50), (260, 300, 100)]


def test_chunking_none_is_one_job():
    p = rs.plan(rs.resolve(spec(chunking="none", frames=[50, 200])), STATE)
    assert len(p["chunks"]) == 1 and (p["chunks"][0]["start"], p["chunks"][0]["end"]) == (50, 200)
    assert p["chunks"][0]["preroll"] == 50 and p["chunks"][0]["camera"] == "CamA+CamB+CamC"


def test_shots_by_label_or_index_and_typos():
    p = rs.plan(rs.resolve(spec(shots=["CamC", 0])), STATE)
    assert [c["camera"] for c in p["chunks"]] == ["CamA", "CamC"]
    with pytest.raises(rs.SpecError, match="did you mean 'CamB'"):
        rs.plan(rs.resolve(spec(shots=["camb"])), STATE)
    with pytest.raises(rs.SpecError, match="out of range"):
        rs.plan(rs.resolve(spec(shots=[7])), STATE)


def test_no_cuts_uses_the_playback_range():
    p = rs.plan(rs.resolve(spec()), {"playback": [10, 40], "fps": 30.0, "cuts": []})
    assert [(c["start"], c["end"]) for c in p["chunks"]] == [(10, 40)]


def test_calibration_replaces_the_cost_guess():
    r = rs.resolve(spec(shots=["CamA"]))
    slow = rs.plan(r, {**STATE, "calibration": {"sample_s_1080p": 0.5}})["seconds"]
    fast = rs.plan(r, STATE)["seconds"]
    assert slow > 4 * fast


def test_split_boxes_balances_and_keeps_order():
    p = rs.plan(rs.resolve(spec(boxes=2, chunking=40)), STATE)
    boxes = p["boxes"]
    assert len(boxes) == 2 and sum(b["frames"] for b in boxes) == 300
    ids = [c["id"] for c in p["chunks"]]
    for b in boxes:
        assert b["chunks"] == sorted(b["chunks"], key=ids.index)
    assert abs(boxes[0]["seconds"] - boxes[1]["seconds"]) <= max(c["seconds"] for c in p["chunks"])


def test_vram_guard_refuses_path_tracer_on_a_24gb_gpu():
    r = rs.resolve(spec(preset="pathtrace"))
    v = rs.vram_check(r, {"total_gb": 24.0, "free_gb": 20.0})
    assert not v["ok"] and "40" in v["why"] and "L4" in v["why"]
    assert rs.vram_check(r, {"total_gb": 48.0, "free_gb": 44.0})["ok"]
    forced = rs.resolve(spec(preset="pathtrace", vram={"force": True}))
    assert rs.vram_check(forced, {"total_gb": 24.0, "free_gb": 20.0})["ok"]
    assert rs.vram_check(rs.resolve(spec()), {"total_gb": 24.0, "free_gb": 2.0})["ok"] is False
    assert rs.vram_check(rs.resolve(spec()), None)["ok"]


def test_parse_nvidia_smi():
    g = rs.parse_nvidia_smi("NVIDIA L4, 23034, 4500, 18200, 97\n")
    assert g["name"] == "NVIDIA L4" and 24.0 < g["total_gb"] < 24.3 and g["util_pct"] == 97
    assert rs.parse_nvidia_smi("") is None and rs.parse_nvidia_smi("garbage") is None


def test_frame_times():
    ft = rs.frame_times({10: 100.0, 11: 100.7, 12: 101.5, 13: 102.2})
    assert ft["per_frame"] == {11: 0.7, 12: 0.8, 13: 0.7} and ft["median_s"] == 0.7 and ft["max_s"] == 0.8


def test_frames_on_disk_and_missing():
    r = rs.resolve(spec())
    assert rs.frames_on_disk(r, ["0001.png", "0002.png", "x.png", "0003.jpg", "_render/0004.png"]) == {1, 2}
    assert rs.missing_frames({1, 2, 5}, 0, 7) == [[0, 1], [3, 5], [6, 7]]
    assert rs.runs([3, 4, 5, 9]) == [[3, 6], [9, 10]]


def test_image_ok_spots_truncated_frames():
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 20 + b"IEND\xaeB`\x82"
    assert rs.image_ok(png[:8], png[-16:], len(png))
    assert not rs.image_ok(png[:8], png[-30:-14], len(png) - 14)
    assert rs.image_ok(b"\xff\xd8\xff\xe0", b"\x00\xff\xd9", 100) and not rs.image_ok(b"\xff\xd8", b"\x00\x00", 100)
    assert rs.image_ok(b"\x76\x2f\x31\x01", b"", 1000) and not rs.image_ok(b"\x76\x2f\x31\x01", b"", 10)
    assert not rs.image_ok(b"", b"", 0)


def test_cmdline():
    argv = rs.cmdline("/ue/Engine/Binaries/Linux/UnrealEditor", "/p/Demo.uproject", "/r/_render/c.utxt", log="/r/c.log")
    assert argv[:4] == ["/ue/Engine/Binaries/Linux/UnrealEditor", "/p/Demo.uproject", "MoviePipelineEntryMap", "-game"]
    assert "-MoviePipelineConfig=/r/_render/c.utxt" in argv and "-RenderOffscreen" in argv and "-vulkan" in argv
    assert "-abslog=/r/c.log" in argv and "-Unattended" in argv
    win = rs.cmdline(r"C:\UE\UnrealEditor-Cmd.exe", r"C:\p\Demo.uproject", r"C:\r\c.utxt", offscreen=False)
    assert "-vulkan" not in win and "-RenderOffscreen" not in win


def test_encode_args_h264_with_audio():
    r = rs.resolve(spec())
    argv = rs.encode_args(r, {"kind": "h264", "crf": 16}, 100, 160, 24.0, audio_file="/a.wav", audio_start_s=0)
    s = " ".join(argv)
    assert "-framerate 24 -start_number 100 -i /srv/r/reel/%04d.png" in s.replace("\\", "/")
    assert "-frames:v 60" in s and "libx264" in s and "-crf 16" in s and "yuv420p" in s and "-c:a aac" in s
    assert "-t 2.500000" in s and argv[-1].replace("\\", "/") == "/srv/r/reel/SEQ_Reel.mp4"


def test_encode_args_prores_from_exr_ntsc_silent():
    r = rs.resolve(spec(preset="final_exr", name="cut1"))
    argv = rs.encode_args(r, {"kind": "prores", "profile": 4, "audio": False}, 0, 10, 23.976)
    s = " ".join(argv).replace("\\", "/")
    assert "-apply_trc iec61966_2_1" in s and "24000/1001" in s and "prores_ks -profile:v 4" in s
    assert "yuva444p10le" in s and "-an" in argv and "/FinalImage/%04d.exr" in s and argv[-1].endswith("cut1.mov")
    with pytest.raises(rs.SpecError):
        rs.encode_args(r, {"kind": "png"}, 0, 10, 24.0)


def test_concat_and_mux():
    argv, text = rs.concat_args(["/a/x.mp4", "/a/it's.mp4"], "/a/all.mp4", "/a/l.txt")
    assert text == "file '/a/x.mp4'\nfile '/a/it'\\''s.mp4'\n" and argv[argv.index("-i") + 1] == "/a/l.txt"
    m = rs.mux_audio_args("/v.mov", "/a.wav", "/o.mov", audio_start_s=2.5, prores=True)
    assert "pcm_s24le" in m and "2.500000" in m and "-shortest" in m


def test_assemble_wav_places_chunks_on_the_timeline(tmp_path):
    def mk(name, seconds, value):
        p = tmp_path / name
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(1000)
            w.writeframes(struct.pack("<h", value) * int(1000 * seconds))
        return str(p)
    a, b = mk("a.wav", 1.0, 100), mk("b.wav", 1.0, 200)
    out = rs.assemble_wav([(b, 72), (a, 24)], 0, 96, 24.0, str(tmp_path / "o.wav"))
    assert out["seconds"] == 4.0 and out["parts"] == 2
    with wave.open(out["path"]) as w:
        pcm = w.readframes(w.getnframes())
    vals = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    assert vals[500] == 0 and vals[1500] == 100 and vals[2500] == 0 and vals[3500] == 200


def test_presets_are_all_valid():
    for name in rs.PRESETS:
        r = rs.resolve(spec(preset=name))
        assert r["width"] > 0 and r["outputs"]
    assert rs.resolve(spec(preset="pathtrace"))["path_tracer"] is True
