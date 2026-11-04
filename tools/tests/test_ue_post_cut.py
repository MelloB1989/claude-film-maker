"""The generic delivery pipeline (filmtools.unreal.post_cut, film-post): the spec, the edit, captions, frames and the
ffmpeg argv, all without running ffmpeg."""
import json
from pathlib import Path

import pytest

from filmtools.unreal import audio_timing, post_cli, post_cut as pc

PNG_1x1 = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x07\x80\x00\x00\x048\x08\x02\x00\x00\x00")  # 1920x1080 header


def spec_doc(**kw):
    d = {"kind": "delivery", "version": 1, "name": "demo", "fps": 24, "out": "out",
         "shots": [{"id": "S01", "start": 0, "end": 48, "frames": "r/S01"},
                   {"id": "S02", "start": 48, "end": 120, "frames": "r/S02"}],
         "outputs": [{"name": "master", "preset": "prores4444"}]}
    d.update(kw)
    return d


def test_validate_defaults_and_errors(tmp_path):
    s = pc.validate(spec_doc(), tmp_path)
    assert s["edl"] == [[0, 120]]  # back-to-back shots are one piece
    with pytest.raises(pc.SpecError, match="unknown key"):
        pc.validate(spec_doc(outptus=[]))
    with pytest.raises(pc.SpecError, match="preset"):
        pc.validate(spec_doc(outputs=[{"name": "x", "preset": "dnxhd"}]))
    with pytest.raises(pc.SpecError, match="outside the shots"):
        pc.validate(spec_doc(edl=[[100, 200]]))
    with pytest.raises(pc.SpecError, match="inside S01"):
        pc.validate(spec_doc(shots=[{"id": "S01", "start": 0, "end": 48, "frames": "a"},
                                    {"id": "S02", "start": 40, "end": 60, "frames": "b"}]))
    with pytest.raises(pc.SpecError, match="no captions section"):
        pc.validate(spec_doc(outputs=[{"name": "w", "preset": "h264", "captions": "burn"}]))
    with pytest.raises(pc.SpecError, match="not both"):
        pc.validate(spec_doc(audio={"mix": "m.wav", "music": "x.wav"}))


def test_edit_math():
    segs = [[0, 24], [48, 120]]
    assert pc.length(segs) == 96
    assert pc.to_out(segs, 30) is None and pc.to_out(segs, 50) == 26
    assert pc.spans_out(segs, 20, 60) == [(20, 24), (24, 36)]
    assert pc.timecode(24 * 61 + 5, 24) == "00:01:01:05"


def test_cmx3600_one_event_per_shot_piece(tmp_path):
    s = pc.validate(spec_doc(edl=[[12, 24], [40, 60]]), tmp_path)
    edl = pc.cmx3600(s)
    events = [ln for ln in edl.splitlines() if ln[:3].isdigit()]
    assert len(events) == 3  # 12-24 (S01), 40-48 (S01), 48-60 (S02)
    assert events[2].endswith("00:00:00:20 00:00:01:08")
    assert "* FROM CLIP NAME: S02" in edl


def test_captions_follow_words_and_the_edit():
    doc = audio_timing.from_lines([{"id": "L1", "wav": "a", "start_frame": 0, "duration_s": 4, "text":
                                    "Hello there, my friend. How are you?",
                                    "words": [{"w": w, "start_frame": f, "end_frame": f + 8} for w, f in
                                              [("Hello", 2), ("there,", 10), ("my", 20), ("friend.", 28),
                                               ("How", 50), ("are", 58), ("you?", 66)]]}], 24)
    cues = pc.caption_cues(doc, max_chars=24, hold_frames=6)
    assert [c[2] for c in cues] == ["Hello there, my friend.", "How are you?"]
    assert cues[0][:2] == [2, 42] and cues[1][:2] == [50, 80]
    srt, vtt = pc.captions_text(cues, [[0, 24], [48, 120]], 24)
    assert srt.startswith("1\n00:00:00,083 --> 00:00:01,000\nHello there, my friend.")
    assert "00:00:01.083 --> 00:00:02.333\nHow are you?" in vtt


def test_find_frames_both_numberings_and_missing(tmp_path):
    s = pc.validate(spec_doc(), tmp_path)
    (tmp_path / "r/S01").mkdir(parents=True)
    (tmp_path / "r/S02").mkdir(parents=True)
    for f in range(48):  # S01 on the sequence's clock
        (tmp_path / f"r/S01/{f:04d}.png").write_bytes(PNG_1x1)
    for f in range(70):  # S02 numbered from 0, two frames short
        (tmp_path / f"r/S02/{f:04d}.png").write_bytes(PNG_1x1)
    found = pc.find_frames(s)
    assert found[47].name == "0047.png" and found[48].name == "0000.png"
    assert pc.missing_report(s, found) == "S02 118-119 (2 frames)"
    assert pc.png_size(found[0]) == (1920, 1080)
    with pytest.raises(pc.SpecError, match="fill: slate"):
        pc.stage(s, found, tmp_path / "work", (1920, 1080))


def test_encode_args_vertical_crop_and_captions(tmp_path):
    s = pc.validate(spec_doc(captions={}, outputs=[
        {"name": "v", "preset": "h264", "aspect": "9:16", "height": 1920, "captions": "burn",
         "crop": {"S01": [[0, 0.3], [24, 0.6]]}}]), tmp_path)
    o = s["outputs"][0]
    argv = pc.encode_args(s, o, tmp_path / "seq", tmp_path / "mix.wav", (1920, 1080), tmp_path / "demo.srt",
                          tmp_path / "o.mp4")
    vf = argv[argv.index("-vf") + 1]
    assert vf.startswith("crop=w=608:h=1080:x='floor(if(lt(n\\,48)")
    assert "scale=1080:1920" in vf and "subtitles=" in vf
    assert argv[argv.index("-frames:v") + 1] == "120"
    assert "-itsoffset" not in argv and "-shortest" not in argv and "-ss" not in argv
    with pytest.raises(pc.SpecError, match="wider"):
        pc.encode_args(s, {"name": "w", "preset": "h264", "aspect": "21:9"}, tmp_path, tmp_path, (1920, 1080),
                       None, tmp_path / "x.mp4")


def test_audio_args():
    a = pc.cut_audio_args(Path("in.wav"), [[0, 24], [48, 72]], 24, Path("o.wav"))
    g = a[a.index("-filter_complex") + 1]
    assert "acrossfade=d=0.012" in g and "apad=whole_dur=2.000000,atrim=end=2.000000" in g
    one = pc.cut_audio_args(Path("in.wav"), [[24, 48]], 24, Path("o.wav"))
    assert "atrim=start=1.000000:end=2.000000" in one[one.index("-af") + 1]
    doc = audio_timing.from_lines([{"id": "L1", "wav": "L1.wav", "start_frame": 48, "duration_s": 1,
                                    "volume_db": -3}], 24)
    v = pc.vo_bus_args(doc, Path("/vo"), Path("vo.wav"), 24)
    assert "/vo/L1.wav" in v and "adelay=2000:all=1,volume=-3.00dB" in v[v.index("-filter_complex") + 1]


def test_plan_and_cli(tmp_path, capsys):
    (tmp_path / "vo").mkdir()
    timing = audio_timing.from_lines([{"id": "L1", "wav": "L1.wav", "start_frame": 10, "duration_s": 1,
                                       "text": "Hi.", "words": [{"w": "Hi.", "start_frame": 12, "end_frame": 20}]}], 24)
    (tmp_path / "vo/timing.json").write_text(json.dumps(timing))
    doc = spec_doc(audio={"timing": "vo/timing.json"}, captions={},
                   outputs=[{"name": "master", "preset": "prores4444"}, {"name": "web", "preset": "h264",
                                                                          "height": 720, "captions": "burn"}])
    (tmp_path / "spec.json").write_text(json.dumps(doc))
    s = pc.load_spec(tmp_path / "spec.json")
    steps = pc.plan(s)
    assert [x.what.split(" ")[0] for x in steps] == ["stage", "voice", "voice", "sound", "captions", "encode",
                                                     "encode", "cut.json:"]
    assert steps[-2].writes.endswith("out/demo-web.mp4")
    assert post_cli.main(["plan", str(tmp_path / "spec.json"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["frames"] == 120
    assert post_cli.main(["captions", str(tmp_path / "spec.json")]) == 0
    assert "Hi." in capsys.readouterr().out
    assert post_cli.main(["frames", str(tmp_path / "spec.json"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["needed"] == {"S01": [[0, 48]], "S02": [[48, 120]]}


def test_cli_timing_and_handoff(tmp_path, capsys):
    (tmp_path / "lines.json").write_text(json.dumps({"fps": 24, "lines": [
        {"id": "L1", "wav": "L1.wav", "start_s": 1, "duration_s": 2, "speaker": "host"}]}))
    assert post_cli.main(["timing", "--lines", str(tmp_path / "lines.json"), "-o", str(tmp_path / "t.json")]) == 0
    assert json.loads(capsys.readouterr().out)["lines"] == 1
    (tmp_path / "faces.json").write_text(json.dumps({"host": {"face_mesh": "/Game/F", "label": "Host"}}))
    assert post_cli.main(["handoff", str(tmp_path / "t.json"), "--faces", str(tmp_path / "faces.json")]) == 0
    assert json.loads(capsys.readouterr().out)[0]["place"]["start_frame"] == 24
