"""The `audio` spec kind's planner (pure) and the shipped examples."""
import json
from pathlib import Path

import pytest
import yaml

from filmtools.unreal import audio_kind, audio_timing, post_cut

REPO = Path(__file__).resolve().parents[2]
EX = REPO / "examples" / "unreal"


def spec(**kw):
    s = {"kind": "audio", "version": 1, "name": "a", "sequence": "/Game/Seq/SQ",
         "tracks": [{"name": "Music", "clips": [{"sound": "/Game/Audio/Score", "start_frame": 0, "volume_db": -4}]}]}
    s.update(kw)
    return s


def test_plan_places_then_converges():
    st = {"fps": 24, "tracks": []}
    steps = audio_kind.plan(spec(), st)
    assert [s["op"] for s in steps] == ["audio.place"] and "missing" in steps[0]["why"]
    st = {"fps": 24, "tracks": [{"name": "Music", "clips": [{"sound": "/Game/Audio/Score", "start_frame": 0,
                                                             "offset_s": 0.0, "volume_db": -4.0}]}]}
    assert audio_kind.plan(spec(), st) == []
    st["tracks"][0]["clips"][0]["volume_db"] = 0.0
    assert audio_kind.plan(spec(), st)[0]["why"].startswith("track Music holds 1")


def test_plan_timing_track_predicts_sound_names():
    doc = json.loads((EX / "audio/timing.json").read_text())
    s = spec(tracks=[{"name": "VO", "timing": doc, "folder": "/Game/Audio/VO"}], remove_others=True)
    st = {"fps": 24, "tracks": [{"name": "Old", "clips": []}]}
    steps = audio_kind.plan(s, st)
    assert [x["op"] for x in steps] == ["audio.lines", "audio.remove"]
    st = {"fps": 24, "tracks": [{"name": "VO", "clips": [
        {"sound": "/Game/Audio/VO/L1", "start_frame": 24}, {"sound": "/Game/Audio/VO/L2", "start_frame": 96}]}]}
    assert audio_kind.plan(s, st) == []


def test_plan_errors():
    with pytest.raises(ValueError, match="does not exist"):
        audio_kind.plan(spec(), {"missing": True})
    with pytest.raises(ValueError, match="either timing or clips"):
        audio_kind.plan(spec(tracks=[{"name": "X"}]), {"fps": 24, "tracks": []})


def test_examples_validate():
    s = yaml.safe_load((EX / "audio/voice-and-score.yaml").read_text())
    schema = json.loads((REPO / "tools/filmtools/unreal/schemas/audio.schema.json").read_text())
    assert set(s) <= set(schema["properties"])
    assert audio_timing.validate(json.loads((EX / "audio/timing.json").read_text())) == []
    d = post_cut.load_spec(EX / "delivery/two-shots.yaml")
    assert post_cut.length(d["edl"]) == 120 and len(post_cut.plan(d)) == 10
