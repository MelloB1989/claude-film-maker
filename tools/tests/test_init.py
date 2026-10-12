import json

import pytest

from filmtools import config, init, paths
from filmtools.vo import load_script


def test_a_scaffolded_film_is_one_every_tool_reads(tmp_path):
    fp, written = init.scaffold("my-film", tmp_path, title="My Film", fmt="vertical", fps=24, theme="noir", bpm=96)
    assert fp.dir == tmp_path / "films" / "my-film"
    assert {p.relative_to(fp.dir).as_posix() for p in written} == {
        "film.json", "data/script.json", "data/.gitkeep", "audio/.gitkeep"}
    assert not (fp.dir / "film.ts").exists() and not (fp.dir / "scenes").exists()  # the engine's to write
    f = config.load(fp)
    assert (f.id, f.title, f.size, f.fps, f.raw["theme"], f.bpm, f.beats_per_bar) == (
        "my-film", "My Film", (1080, 1920), 24, "noir", 96.0, 4)
    assert f.voice["voice_id"] == "" and f.music["temp"]["style"] == "pulse" and f.mix["lufs"] == -14.0
    assert f.mix_path == fp.dir / "audio" / "mix" / "mix.wav" and f.raw["vo"] == "data/vo.json"
    s = load_script(fp.data / "script.json")
    assert s["lines"][0]["scene"] in s["acts"][0]["scenes"] and s["lines"][0]["takes"] == 2


def test_an_explicit_size_and_the_default_title(tmp_path):
    fp, _ = init.scaffold("square_one", tmp_path, fmt=init.parse_format("1280x720"))
    f = config.load(fp)
    assert f.size == (1280, 720) and f.title == "Square One"
    with pytest.raises(Exception, match="WxH"):
        init.parse_format("huge")


def test_an_existing_film_is_kept_unless_forced(tmp_path):
    fp, _ = init.scaffold("a", tmp_path, title="First")
    fp.config.write_text(json.dumps({**json.loads(fp.config.read_text()), "title": "Edited"}))
    _, written = init.scaffold("a", tmp_path, title="Second")
    assert written == [] and config.load(fp).title == "Edited"
    _, written = init.scaffold("a", tmp_path, title="Second", force=True)
    assert fp.config in written and config.load(fp).title == "Second"


@pytest.mark.parametrize("bad", ["My Film", "-x", "../up", "Caps"])
def test_an_id_is_a_folder_name(tmp_path, bad):
    with pytest.raises(SystemExit, match="lowercase"):
        init.scaffold(bad, tmp_path)


def test_film_init_writes_under_the_repo_and_checks_the_theme(capsys, tmp_path):
    init.main(["demo", "--title", "Demo", "--bpm", "100"])
    fp = paths.film_paths("demo")
    assert config.load(fp).bpm == 100.0
    out = capsys.readouterr().out
    assert "films/starter/film.ts" in out and "--film demo" in out
    init.main(["--film", "other"])
    assert paths.film_paths("other").config.is_file()
    themes = tmp_path / "themes.json"
    themes.write_text(json.dumps({"noir": {}, "paper": {}}))
    assert init.themes(themes) == ["noir", "paper"] and init.themes(tmp_path / "missing.json") is None
    with pytest.raises(SystemExit):
        init.main(["x", "--fps", "0"])
