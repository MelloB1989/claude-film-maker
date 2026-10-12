import json

import pytest
from conftest import make_film

from filmtools import config


def load(tmp_path, **doc):
    return config.load(make_film(tmp_path, **doc))


def test_defaults_fill_an_empty_pipeline(tmp_path):
    f = load(tmp_path)
    assert (f.id, f.title, f.fps, f.size) == ("demo", "Demo", 30, (1920, 1080))
    assert f.voice["provider"] == "elevenlabs" and f.voice["voice_id"] is None and f.voice["key_file"] == "~/11labs"
    assert f.voice["pace"] == {"factor": 1.0, "min": 0.85, "max": 1.0, "target_wps": None}
    assert f.mix["lufs"] == -14.0 and f.mix["true_peak"] == -1.0 and f.mix["music_duck"] == config.MUSIC_DUCK
    assert f.music["sections"] == [] and f.music["chosen"] is None and f.bpm is None and f.beats_per_bar == 4
    assert set(f.deliver["outputs"]) == {"rough", "master"} and f.deliver["hits"] == []
    assert f.sfx["palette"] == "data/sfx_palette.json" and f.sync["duration"] is None and f.fonts == []
    assert f.mix_path == f.paths.dir / "audio" / "mix" / "mix.wav"
    assert f.analysis_path == f.paths.dir / "data" / "audio.json"


def test_the_pipeline_merges_over_the_defaults(tmp_path):
    f = load(tmp_path, audio={"bpm": 96, "beatsPerBar": 3, "mix": "audio/mix/final.wav"}, fps=24, format="portrait",
             pipeline={"voice": {"voice_id": "abc", "pace": {"factor": 0.9}, "settings": {"stability": 0.4}},
                       "mix": {"lufs": -16, "music_duck": {"range_db": 6.0}},
                       "deliver": {"outputs": {"9x16": {"size": [1080, 1920]}}}})
    assert f.voice["voice_id"] == "abc" and f.voice["model"] == config.PIPELINE_DEFAULTS["voice"]["model"]
    assert f.voice["pace"] == {"factor": 0.9, "min": 0.85, "max": 1.0, "target_wps": None}  # merged key by key
    assert f.voice["settings"] == {"stability": 0.4}
    assert f.mix["lufs"] == -16 and f.mix["music_duck"]["range_db"] == 6.0 and f.mix["music_duck"]["ratio"] == 4.0
    assert f.deliver["outputs"] == {"9x16": {"size": [1080, 1920]}}  # the outputs replace the defaults whole
    assert (f.fps, f.size, f.bpm, f.beats_per_bar) == (24, (1080, 1350), 96.0, 3)
    assert f.mix_path == f.paths.dir / "audio" / "mix" / "final.wav"
    assert config.PIPELINE_DEFAULTS["voice"]["voice_id"] is None  # the defaults are never mutated


def test_the_music_tempo_wins_over_the_engines(tmp_path):
    assert load(tmp_path, audio={"bpm": 96}, pipeline={"music": {"bpm": 100}}).bpm == 100.0


@pytest.mark.parametrize("pipeline, where", [
    ({"voices": {}}, "pipeline.voices"),
    ({"voice": {"voiceid": "x"}}, "pipeline.voice.voiceid"),
    ({"mix": {"music_duck": {"depth": 3}}}, "pipeline.mix.music_duck.depth"),
])
def test_an_unknown_setting_is_an_error_not_a_silent_default(tmp_path, pipeline, where):
    with pytest.raises(SystemExit, match=rf"unknown setting {where}\b"):
        load(tmp_path, pipeline=pipeline)


def test_format_presets_and_explicit_sizes(tmp_path):
    for fmt, size in config.FORMATS.items():
        assert config.size_of(fmt) == size
    assert config.size_of({"width": 1280, "height": 720}) == (1280, 720)
    with pytest.raises(SystemExit, match="format must be one of"):
        load(tmp_path, format="widescreen")


def test_a_required_setting_names_itself_and_the_file(tmp_path):
    f = load(tmp_path)
    with pytest.raises(SystemExit, match=r"set pipeline\.voice\.voice_id in .*films/demo/film\.json"):
        f.require("voice", "voice_id")


def test_the_id_must_match_the_folder_and_the_file_must_exist(tmp_path):
    fp = make_film(tmp_path)
    fp.config.write_text(json.dumps({"id": "other"}))
    with pytest.raises(SystemExit, match="must equal the folder name"):
        config.load(fp)
    fp.config.unlink()
    with pytest.raises(SystemExit, match="film-init demo"):
        config.load(fp)
    fp.config.write_text("{not json")
    with pytest.raises(SystemExit, match="not valid JSON"):
        config.load(fp)


def test_load_reads_the_current_film(film):
    assert config.load().paths == film
