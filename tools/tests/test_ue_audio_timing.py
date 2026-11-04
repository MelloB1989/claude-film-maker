"""The line-timing document (filmtools.unreal.audio_timing): pure, no engine."""
import wave

import pytest

from filmtools.unreal import audio_timing as at


def wav(path, seconds, sr=48000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\0\0" * int(seconds * sr))
    return path


def test_from_lines_reads_durations_and_puts_words_on_the_clock(tmp_path):
    wav(tmp_path / "L1.wav", 2.0)
    doc = at.from_lines([{"id": "L1", "wav": "L1.wav", "start_s": 1.0, "speaker": "host", "text": "Hi there",
                          "words": [{"w": "Hi", "start": 0.1, "end": 0.4}, {"w": "there", "start": 0.5, "end": 1.0}]}],
                        24, root=tmp_path)
    ln = doc["lines"][0]
    assert (ln["start_frame"], ln["end_frame"], ln["duration_s"]) == (24, 72, 2.0)
    assert [(w["start_frame"], w["end_frame"]) for w in ln["words"]] == [(26, 34), (36, 48)]
    assert at.validate(doc) == []


def test_from_lines_errors_are_actionable(tmp_path):
    with pytest.raises(at.TimingError, match="unknown key"):
        at.from_lines([{"id": "a", "wav": "x.wav", "start_frame": 0, "duration_s": 1, "strat": 3}], 24)
    with pytest.raises(at.TimingError, match="not a readable WAV"):
        at.from_lines([{"id": "a", "wav": "missing.wav", "start_frame": 0}], 24, root=tmp_path)
    with pytest.raises(at.TimingError, match="repeat"):
        at.from_lines([{"id": "a", "wav": "x", "start_frame": 0, "duration_s": 1}] * 2, 24)


def test_from_vo_json_and_cues_json():
    vo = {"lines": [{"id": "L2", "start": 2.0, "end": 3.0, "take": 2, "text": "Go",
                     "words": [{"w": "Go", "start": 2.1, "end": 2.5}]}]}
    d = at.from_vo_json(vo, 30, speaker="narrator")
    ln = d["lines"][0]
    assert ln["wav"] == "audio/vo/paced/L2/2.wav" and (ln["start_frame"], ln["end_frame"]) == (60, 90)
    assert ln["words"][0]["start_frame"] == 63
    cues = {"fps": 24, "lines": {"L1": {"who": "him", "text": "Yes", "wav": "L1.wav", "file_frame": 95.6,
                                        "end_frame": 120.2, "words": [{"w": "Yes", "start": 100, "end": 110}]}}}
    c = at.from_cues_json(cues)["lines"][0]
    assert (c["start_frame"], c["end_frame"], c["speaker"]) == (96, 121, "him")


def test_validate_overlaps_rescale():
    doc = at.from_lines([{"id": "a", "wav": "a", "start_frame": 0, "duration_s": 2, "speaker": "x"},
                         {"id": "b", "wav": "b", "start_frame": 30, "duration_s": 1, "speaker": "x"},
                         {"id": "c", "wav": "c", "start_frame": 30, "duration_s": 1, "speaker": "y"}], 24)
    assert at.overlaps(doc) == [("a", "b")]
    assert len(at.overlaps(doc, speaker_only=False)) == 3
    r = at.rescale(doc, 48)
    assert r["lines"][1]["start_frame"] == 60 and r["fps"] == 48
    bad = {**doc, "kind": "x"}
    assert at.validate(bad)


def test_performance_handoff():
    doc = at.from_lines([{"id": "L1", "wav": "L1.wav", "start_frame": 10, "duration_s": 1, "speaker": "host",
                          "mood": "HAPPINESS"},
                         {"id": "N1", "wav": "N1.wav", "start_frame": 40, "duration_s": 1, "speaker": "narrator"}], 24)
    h = at.performance_handoff(doc, {"host": {"face_mesh": "/Game/MH/Host/Face", "label": "Host"}},
                               wav_root="/srv/vo")
    assert len(h) == 1
    assert h[0]["speech"] == {"wav": "/srv/vo/L1.wav", "name": "L1", "face_mesh": "/Game/MH/Host/Face",
                              "mood": "HAPPINESS", "folder": "/Game/Speech"}
    assert h[0]["place"] == {"label": "Host", "component": "Face", "start_frame": 10, "end_frame": 34, "offset_s": 0.0}
