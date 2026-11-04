"""WP12's bridge ops (unreal/fmbridge/ops/audio.py) against the fake engine."""
import wave

import pytest

from fakeunreal import run_op


def wav(path, seconds, sr=48000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\0\0" * int(seconds * sr))
    return str(path)


@pytest.fixture
def seq(ue):
    ue.add_asset("/Game/Seq/SQ_Test", "LevelSequence")
    return "/Game/Seq/SQ_Test"


def test_import_is_idempotent_and_names_are_sanitised(ue, tmp_path):
    f = wav(tmp_path / "vo" / "L1 take-2.wav", 1.5)
    r = run_op("audio.import", files=[f], folder="/Game/Audio/VO")
    assert r["changed"] and r["sounds"][0]["path"] == "/Game/Audio/VO/L1_take_2"
    assert r["sounds"][0]["duration_s"] == 1.5
    r2 = run_op("audio.import", files=[f], folder="/Game/Audio/VO")
    assert not r2["changed"] and not r2["sounds"][0]["imported"]
    assert len(ue.imports) == 1 and ue.dialogs == []


def test_import_missing_file_changes_nothing(ue, fmb):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("audio.import", files=["/nope/a.wav"])
    assert e.value.code == "not_found" and "push" in e.value.hint
    assert ue.imports == []


def test_place_converges_and_stacks_rows(ue, tmp_path, seq):
    a = run_op("audio.import", files=[wav(tmp_path / "a.wav", 2.0), wav(tmp_path / "b.wav", 1.0)])["sounds"]
    clips = [{"sound": a[0]["path"], "start_frame": 24},
             {"sound": a[1]["path"], "start_s": 2.0, "volume_db": -6},
             {"sound": a[1]["path"], "start_frame": 100, "offset_s": 0.5}]
    r = run_op("audio.place", sequence=seq, clips=clips, track="VO", extend=True)
    assert r["changed"]
    got = {(c["start_frame"], c["end_frame"], c["row"]) for c in r["clips"]}
    assert got == {(24, 72, 0), (48, 72, 1), (100, 112, 0)}  # 2 s at 24 fps; the overlap goes to row 1
    assert r["end_frame"] == 112
    d = run_op("audio.describe", sequence=seq)
    vo = d["tracks"][0]
    assert vo["name"] == "VO" and len(vo["clips"]) == 3
    c48 = next(c for c in vo["clips"] if c["start_frame"] == 48)
    assert c48["volume_db"] == -6.0
    assert next(c for c in vo["clips"] if c["start_frame"] == 100)["offset_s"] == 0.5
    assert not run_op("audio.place", sequence=seq, clips=clips, track="VO")["changed"]
    # a different clip list replaces the track's clips, on the same track
    run_op("audio.place", sequence=seq, clips=[[a[0]["path"], 0]], track="VO")
    d = run_op("audio.describe", sequence=seq)
    assert len(d["tracks"]) == 1 and [c["start_frame"] for c in d["tracks"][0]["clips"]] == [0]


def test_place_validates_before_touching(ue, seq, fmb):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("audio.place", sequence=seq, clips=[{"sound": "/Game/Audio/Nope", "start_frame": 0}])
    assert e.value.code == "not_found"
    assert run_op("audio.describe", sequence=seq)["tracks"] == []
    with pytest.raises(OpError) as e:
        run_op("audio.place", sequence=seq, clips=[{"sound": "/Game/A", "start_frame": 0, "gain": 2}])
    assert e.value.code == "bad_args" and "gain" in e.value.message
    with pytest.raises(OpError) as e:
        run_op("audio.describe", sequence="/Game/Seq/Missing")
    assert "seq.new" in e.value.hint


def test_remove_is_idempotent(ue, tmp_path, seq):
    s = run_op("audio.import", files=[wav(tmp_path / "a.wav", 1.0)])["sounds"][0]["path"]
    run_op("audio.place", sequence=seq, clips=[[s, 0]], track="SFX")
    assert run_op("audio.remove", sequence=seq, track="SFX") == {"changed": True, "removed": ["SFX"]}
    assert run_op("audio.remove", sequence=seq, track="SFX")["changed"] is False


def test_lines_places_a_timing_document(ue, tmp_path, seq):
    root = tmp_path / "vo"
    wav(root / "L1.wav", 1.0)
    wav(root / "L2.wav", 0.5)
    doc = {"kind": "timing", "version": 1, "fps": 48,
           "lines": [{"id": "L1", "wav": "L1.wav", "start_frame": 96}, {"id": "L2", "wav": "L2.wav", "start_frame": 192}]}
    r = run_op("audio.lines", sequence=seq, timing=doc, wav_root=str(root))
    assert r["changed"] and "rescaled" in r["fps_note"]
    assert [(x["id"], x["start_frame"], x["end_frame"]) for x in r["lines"]] == [("L1", 48, 72), ("L2", 96, 108)]
    assert run_op("audio.lines", sequence=seq, timing=doc, wav_root=str(root))["changed"] is False


def test_plan_clips_pure(fmb):
    from fmbridge.ops.audio import plan_clips, db_to_gain, gain_to_db
    p = plan_clips([{"sound": "s", "start_frame": 0, "end_frame": None, "offset_s": 0.25, "volume_db": 0}],
                   {"s": 1.0}, 24)
    assert p[0]["end_frame"] == 18 and p[0]["row"] == 0
    assert abs(gain_to_db(db_to_gain(-6)) + 6) < 1e-9
