from pathlib import Path

import pytest
from conftest import make_film

from filmtools import cli, paths


def test_root_is_the_repo_holding_app_and_tools():
    root = paths.find_root()
    assert (root / "app" / "package.json").is_file() and (root / "tools" / "pyproject.toml").is_file()
    assert paths.APP == root / "app" and paths.FONTS == root / "fonts" and paths.FILMS == root / "films"


def test_find_root_rejects_outside_paths(tmp_path: Path):
    with pytest.raises(RuntimeError, match="not inside the film repo"):
        paths.find_root(tmp_path)


def test_find_root_needs_both_markers(tmp_path: Path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "pyproject.toml").write_text("")
    with pytest.raises(RuntimeError):
        paths.find_root(tmp_path / "tools")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "package.json").write_text("{}")
    assert paths.find_root(tmp_path / "tools") == tmp_path.resolve()


def test_a_films_folders(tmp_path):
    fp = make_film(tmp_path, "alpha")
    assert fp.dir == tmp_path / "films" / "alpha"
    assert (fp.data, fp.audio, fp.config) == (fp.dir / "data", fp.dir / "audio", fp.dir / "film.json")
    assert fp.out == tmp_path / "out" / "alpha"
    assert fp.path("audio/mix/mix.wav") == fp.dir / "audio" / "mix" / "mix.wav"
    assert fp.rel(fp.dir / "audio" / "music" / "a.wav") == "audio/music/a.wav"


def test_a_missing_film_lists_the_films_there_are(tmp_path):
    make_film(tmp_path, "alpha")
    make_film(tmp_path, "beta")
    with pytest.raises(paths.FilmNotFound, match="no film 'gamma'.*alpha, beta"):
        paths.film_paths("gamma", tmp_path)
    with pytest.raises(SystemExit):  # a CLI prints it and exits 1
        paths.film_paths("gamma", tmp_path)
    assert paths.film_paths("gamma", tmp_path, must_exist=False).dir == tmp_path / "films" / "gamma"


def test_the_film_is_the_option_else_FILM_else_showcase(monkeypatch):
    assert paths.film_id("x") == "x"
    assert paths.film_id() == "showcase"
    monkeypatch.setenv("FILM", "from-env")
    assert paths.film_id() == "from-env" and paths.film_id("x") == "x"


def test_current_resolves_FILM_lazily_under_the_root(tmp_path, monkeypatch):
    make_film(tmp_path, "alpha")
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setenv("FILM", "alpha")
    assert paths.current().id == "alpha"
    assert paths.DATA == tmp_path / "films" / "alpha" / "data"  # the lazy module attributes follow the selection
    assert (paths.FILM, paths.FILM_DIR, paths.OUT) == ("alpha", tmp_path / "films" / "alpha", tmp_path / "out" / "alpha")
    paths.use_film(make_film(tmp_path, "beta"))
    assert paths.AUDIO == tmp_path / "films" / "beta" / "audio"


def test_without_a_selection_a_missing_default_film_is_a_clear_error():
    with pytest.raises(paths.FilmNotFound, match="no film 'showcase'"):
        paths.current()


def test_take_film_strips_the_option_wherever_it_stands():
    assert cli.take_film(["--film", "a", "render", "--segments", "2"]) == ("a", ["render", "--segments", "2"])
    assert cli.take_film(["render", "--film=b"]) == ("b", ["render"])
    assert cli.take_film(["vo", "--no-open"]) == (None, ["vo", "--no-open"])
    with pytest.raises(SystemExit, match="needs a film id"):
        cli.take_film(["--film"])


def test_film_argv_selects_the_film_and_a_parser_lists_it(tmp_path, monkeypatch):
    make_film(tmp_path, "alpha")
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    ap = cli.parser("x")
    ap.add_argument("--only")
    a = cli.parse(ap, ["--only", "L1", "--film", "alpha"])
    assert a.only == "L1" and paths.current().id == "alpha"
    assert "--film" in ap.format_help()
    with pytest.raises(paths.FilmNotFound):
        cli.film_argv(["--film", "nope"])


def test_without_the_option_a_selected_film_stands(film):
    cli.film_argv(["--only", "x"])
    assert paths.current() == film
