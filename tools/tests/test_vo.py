import json

import numpy as np
import pytest

from filmtools.elevenlabs import TTSResult
from filmtools.vo import generate_takes, load_script, normalize_script

QUIET = {"log": lambda *_: None}
VOICE = {"voice_id": "voice-1", "model": "tts-model", "output_format": "pcm_48000", "speed": 1.12, "settings": {},
         "seed": None}


class FakeClient:
    def __init__(self):
        self.calls = []

    def tts(self, voice_id, text, model_id, output_format, speed=None, seed=None, settings=None):
        self.calls.append((voice_id, text, model_id, output_format, speed, settings))
        n = len(text)
        al = {"characters": list(text), "character_start_times_seconds": [i * 0.05 for i in range(n)],
              "character_end_times_seconds": [(i + 1) * 0.05 for i in range(n)]}
        return TTSResult(np.zeros(4800, dtype="<i2").tobytes(), al, 2, "rid")


LINES = [{"id": "L01", "scene": "open", "text": "Every morning starts.", "takes": 2},
         {"id": "L02", "scene": "open", "text": "Hi.", "takes": 1}]


def test_generates_takes_with_metadata(tmp_path):
    c = FakeClient()
    assert generate_takes(LINES, c, tmp_path, VOICE, **QUIET) == 3
    meta = json.loads((tmp_path / "L01" / "1.json").read_text())
    assert [w["w"] for w in meta["words"]] == ["Every", "morning", "starts."]
    assert meta["duration"] == pytest.approx(0.1) and meta["speed"] == 1.12 and meta["cost"] == 2
    assert meta["voice_id"] == "voice-1" and meta["model_id"] == "tts-model"
    assert c.calls[0] == ("voice-1", "Every morning starts.", "tts-model", "pcm_48000", 1.12, None)


def test_voice_settings_are_sent_and_another_rate_is_refused(tmp_path):
    c = FakeClient()
    generate_takes(LINES[1:], c, tmp_path, {**VOICE, "settings": {"stability": 0.3}}, **QUIET)
    assert c.calls[0][-1] == {"stability": 0.3}
    with pytest.raises(ValueError, match="pcm_48000"):
        generate_takes(LINES, c, tmp_path / "x", {**VOICE, "output_format": "pcm_22050"}, **QUIET)


def test_rerun_never_pays_twice(tmp_path):
    c = FakeClient()
    generate_takes(LINES, c, tmp_path, VOICE, **QUIET)
    assert generate_takes(LINES, c, tmp_path, VOICE, **QUIET) == 0
    assert len(c.calls) == 3


def test_half_written_take_is_regenerated(tmp_path):
    (tmp_path / "L02").mkdir(parents=True)
    (tmp_path / "L02" / "1.wav").write_bytes(b"partial")  # WAV without its JSON: an interrupted run
    c = FakeClient()
    assert generate_takes(LINES[1:], c, tmp_path, VOICE, **QUIET) == 1
    assert json.loads((tmp_path / "L02" / "1.json").read_text())["take"] == 1


def test_only_and_takes_override(tmp_path):
    c = FakeClient()
    assert generate_takes(LINES, c, tmp_path, VOICE, only={"L02"}, takes=3, **QUIET) == 3
    assert {p.name for p in (tmp_path / "L02").iterdir()} == {"1.wav", "1.json", "2.wav", "2.json", "3.wav", "3.json"}
    assert not (tmp_path / "L01").exists()


def test_a_script_without_acts_is_one_act_in_line_order(film):
    (film.data / "script.json").write_text(json.dumps({"title": "Demo", "lines": LINES + [
        {"id": "L03", "scene": "close", "text": "Bye."}, {"id": "L04", "scene": "open", "text": "Again."}]}))
    s = load_script()
    assert s["acts"] == [{"id": "1", "name": "Demo", "scenes": ["open", "close"]}]
    acts = {"acts": [{"id": "I", "name": "A", "scenes": ["close", "open"]}], "lines": LINES}
    assert normalize_script(acts) == acts  # written acts stand


def test_a_missing_script_says_what_writes_one(film):
    with pytest.raises(SystemExit, match="film-init"):
        load_script()


def test_the_voice_must_be_set_before_any_take_is_paid_for(film):
    from filmtools.vo import main
    (film.data / "script.json").write_text(json.dumps({"lines": LINES}))
    with pytest.raises(SystemExit, match=r"pipeline\.voice\.voice_id"):
        main([])
