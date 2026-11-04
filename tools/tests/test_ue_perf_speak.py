"""B29 perf.speak (filmtools.unreal.perf_speak): text -> TTS -> audio.lines -> speech.to_face -> seq.anim, with a
fake TTS client and a recorded bridge."""
import json
import struct

import pytest

from filmtools.elevenlabs import TTSResult
from filmtools.unreal import perf_speak, post_cli


class FakeTTS:
    def __init__(self):
        self.calls = []

    def tts(self, voice_id, text, model, fmt, speed=None, seed=None, settings=None):
        self.calls.append((voice_id, text, model, fmt))
        n = 48000  # one second
        chars = list(text)
        st = [i * 0.9 / len(chars) for i in range(len(chars))]
        return TTSResult(struct.pack(f"<{n}h", *([0] * n)),
                         {"characters": chars, "character_start_times_seconds": st,
                          "character_end_times_seconds": [t + 0.9 / len(chars) for t in st]}, 7, "req-1")


class Bridge:
    def __init__(self, fail=None):
        self.calls, self.pushed, self.fail = [], [], fail

    def op(self, name, /, **args):
        self.calls.append((name, args))
        if name == self.fail:
            return {"ok": False, "code": "engine", "message": "boom", "hint": "look"}
        if name == "audio.describe":
            return {"ok": True, "result": {"fps": 24, "tracks": []}}
        if name == "perf.face":
            if self.fail == "no-perf":
                return {"ok": False, "code": "not_found", "message": "no op 'perf.face'"}
            return {"ok": True, "result": {"anim": args["anim"] + "_perf"}}
        if name == "speech.to_face":
            return {"ok": True, "result": {"anim": f"/Game/Speech/Anim/AS_{args['name']}", "seconds": 1.0}}
        return {"ok": True, "result": {"changed": True}}

    def push(self, local, remote):
        self.pushed.append((local, remote))
        return {"ok": True}


FACE = {"face_mesh": "/Game/MH/Host/Face", "label": "Host"}
VOICE = {"voice_id": "v1", "model": "eleven_multilingual_v2"}


def test_speak_runs_the_chain_in_order(tmp_path):
    tts, br = FakeTTS(), Bridge()
    r = perf_speak.speak("Welcome in.", line_id="L1", sequence="/Game/Seq/SQ", start_frame=48, face=FACE, voice=VOICE,
                         box_dir="/srv/vo", out_dir=tmp_path, tts=tts, op=br.op, push=br.push, log=lambda m: None)
    assert [c[0] for c in br.calls] == ["audio.describe", "audio.lines", "speech.to_face", "perf.face", "seq.anim"]
    assert br.pushed == [(str(tmp_path / "L1.wav"), "/srv/vo/L1.wav")]
    lines = br.calls[1][1]
    assert lines["replace"] is False and lines["timing"]["lines"][0]["wav"] == "/srv/vo/L1.wav"
    assert lines["timing"]["lines"][0]["start_frame"] == 48
    assert br.calls[2][1] == {"wav": "/srv/vo/L1.wav", "name": "L1", "face_mesh": FACE["face_mesh"],
                              "mood": "CONFIDENCE", "folder": "/Game/Speech"}
    pf = br.calls[3][1]
    assert pf["anim"] == "/Game/Speech/Anim/AS_L1" and pf["wav"] == "/srv/vo/L1.wav" and len(pf["emphasis"]) == 2
    anim = br.calls[4][1]
    assert anim["sections"] == [{"anim": "/Game/Speech/Anim/AS_L1_perf", "start": 48}] and anim["component"] == "Face"
    assert r["line"]["end_frame"] == 72 and [w["w"] for w in r["line"]["words"]] == ["Welcome", "in."]
    assert r["anim"] == "/Game/Speech/Anim/AS_L1_perf" and r["notes"] == []


def test_take_is_reused_unless_text_or_voice_changes(tmp_path):
    tts = FakeTTS()
    kw = dict(line_id="L1", sequence="/Game/Seq/SQ", start_frame=0, face=FACE, box_dir="/srv/vo", out_dir=tmp_path,
              tts=tts, log=lambda m: None)
    perf_speak.speak("Hi.", voice=VOICE, op=Bridge().op, push=Bridge().push, **kw)
    perf_speak.speak("Hi.", voice=VOICE, op=Bridge().op, push=Bridge().push, **kw)
    assert len(tts.calls) == 1
    perf_speak.speak("Hi.", voice={**VOICE, "speed": 1.1}, op=Bridge().op, push=Bridge().push, **kw)
    assert len(tts.calls) == 2
    assert json.loads((tmp_path / "L1.json").read_text())["key"] == perf_speak.take_key("Hi.", {**VOICE, "speed": 1.1})


def test_a_failed_op_stops_the_chain(tmp_path):
    br = Bridge(fail="speech.to_face")
    with pytest.raises(RuntimeError, match="speech.to_face failed: boom"):
        perf_speak.speak("Hi.", line_id="L1", sequence="/Game/Seq/SQ", start_frame=0, face=FACE, voice=VOICE,
                         box_dir="/srv/vo", out_dir=tmp_path, tts=FakeTTS(), op=br.op, push=br.push,
                         log=lambda m: None)
    assert "seq.anim" not in [c[0] for c in br.calls]


def test_dry_run_calls_nothing(tmp_path, capsys):
    br = Bridge()
    assert post_cli.main(["speak", "--text", "Hello there friend", "--id", "L9", "--sequence", "/Game/Seq/SQ",
                          "--start-frame", "10", "--face-mesh", "/Game/F", "--label", "Host", "--box-dir", "/srv/vo",
                          "--out-dir", str(tmp_path), "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] and [s["op"] for s in out["steps"]] == ["audio.lines", "speech.to_face", "perf.face", "seq.anim"]
    assert not (tmp_path / "L9.wav").exists() and br.calls == []


def test_without_perf_face_the_raw_solve_plays(tmp_path):
    br = Bridge(fail="no-perf")
    r = perf_speak.speak("Hi.", line_id="L1", sequence="/Game/Seq/SQ", start_frame=0, face=FACE, voice=VOICE,
                         box_dir="/srv/vo", out_dir=tmp_path, tts=FakeTTS(), op=br.op, push=br.push,
                         log=lambda m: None)
    assert r["anim"] == "/Game/Speech/Anim/AS_L1" and "not on this bridge" in r["notes"][0]
    assert br.calls[-1][1]["sections"][0]["anim"] == "/Game/Speech/Anim/AS_L1"


def test_emphasis_from_words():
    words = [{"w": "a", "start_frame": 10, "end_frame": 12}, {"w": "long", "start_frame": 12, "end_frame": 22},
             {"w": "b", "start_frame": 22, "end_frame": 24}]
    e = perf_speak.emphasis(words, 24, 10)
    assert e[0] == [0.0, 0.6] and e[1][1] == 1.0 and e[2][0] == round(12 / 24, 3)
