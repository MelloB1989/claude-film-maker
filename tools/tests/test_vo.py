import json

import numpy as np
import pytest

from gitloom_film.elevenlabs import TTSResult
from gitloom_film.vo import generate_takes, load_script

QUIET = {"log": lambda *_: None}


class FakeClient:
    def __init__(self):
        self.calls = []

    def tts(self, voice_id, text, model_id, output_format, speed=None, seed=None):
        self.calls.append((voice_id, text, model_id, output_format, speed))
        n = len(text)
        al = {"characters": list(text), "character_start_times_seconds": [i * 0.05 for i in range(n)],
              "character_end_times_seconds": [(i + 1) * 0.05 for i in range(n)]}
        return TTSResult(np.zeros(4800, dtype="<i2").tobytes(), al, 2, "rid")


LINES = [{"id": "L01", "scene": "thread", "text": "Your agent forgets.", "takes": 2},
         {"id": "L02", "scene": "thread", "text": "Hi.", "takes": 1}]


def test_generates_takes_with_metadata(tmp_path):
    c = FakeClient()
    assert generate_takes(LINES, c, tmp_path, 1.12, **QUIET) == 3
    meta = json.loads((tmp_path / "L01" / "1.json").read_text())
    assert [w["w"] for w in meta["words"]] == ["Your", "agent", "forgets."]
    assert meta["duration"] == pytest.approx(0.1) and meta["speed"] == 1.12 and meta["cost"] == 2
    assert c.calls[0] == ("eVItLK1UvXctxuaRV2Oq", "Your agent forgets.", "eleven_v4", "pcm_48000", 1.12)


def test_rerun_never_pays_twice(tmp_path):
    c = FakeClient()
    generate_takes(LINES, c, tmp_path, 1.12, **QUIET)
    assert generate_takes(LINES, c, tmp_path, 1.12, **QUIET) == 0
    assert len(c.calls) == 3


def test_half_written_take_is_regenerated(tmp_path):
    (tmp_path / "L02").mkdir(parents=True)
    (tmp_path / "L02" / "1.wav").write_bytes(b"partial")  # WAV without its JSON: an interrupted run
    c = FakeClient()
    assert generate_takes(LINES[1:], c, tmp_path, 1.12, **QUIET) == 1
    assert json.loads((tmp_path / "L02" / "1.json").read_text())["take"] == 1


def test_only_and_takes_override(tmp_path):
    c = FakeClient()
    assert generate_takes(LINES, c, tmp_path, 1.0, only={"L02"}, takes=3, **QUIET) == 3
    assert {p.name for p in (tmp_path / "L02").iterdir()} == {"1.wav", "1.json", "2.wav", "2.json", "3.wav", "3.json"}
    assert not (tmp_path / "L01").exists()


def test_script_matches_the_spec():
    s = load_script()
    ids = [l["id"] for l in s["lines"]]
    assert len(ids) == 33 and ids[0] == "L01" and ids[-1] == "L32" and "L18b" in ids
    scenes = [sc for a in s["acts"] for sc in a["scenes"]]
    assert scenes == ["thread", "ex", "her", "repo", "loom", "diff", "cite", "braid", "merkle", "graph",
                      "honest", "proof", "connect", "anywhere", "weave"]
    assert all(l["scene"] in scenes for l in s["lines"])
