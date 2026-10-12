# lib/film.py: which film a run works on, what its film.json says, and where its shots, tracks and plates live
# (docs/CONVENTIONS.md). Every film is a fixture under tmp_path (conftest make_film).
import json

import pytest

from lib import film, theme

from conftest import PRESETS


# --------------------------------------------------------------------------------------------- picking the film

def test_the_film_is_the_option_else_film_env_else_showcase():
    assert film.film_id("demo", {"FILM": "other"}) == "demo"
    assert film.film_id(None, {"FILM": "other"}) == "other"
    assert film.film_id(None, {}) == "showcase" == film.DEFAULT_FILM
    assert film.film_id("", {"FILM": ""}) == "showcase"  # empty is unset
    assert film.FILM_ENV == "FILM"


def test_the_film_env_is_read_from_the_process_environment(monkeypatch):
    monkeypatch.setenv("FILM", "from-env")
    assert film.film_id() == "from-env"
    monkeypatch.delenv("FILM")
    assert film.film_id() == "showcase"


@pytest.mark.parametrize("bad", ["../x", "a/b", ".hidden", "a b", "..", "x..y"])
def test_a_film_id_is_a_plain_folder_name(bad):
    with pytest.raises(ValueError, match="folder name"):
        film.film_id(bad, {})


def test_load_reads_the_films_film_json(make_film):
    repo = make_film("demo", format="vertical", fps=24, theme="paper")
    f = film.load("demo", repo)
    assert f.id == "demo" and f.config["title"] == "Demo" and f.repo == repo
    assert f.size == (1080, 1920) and (f.width, f.height) == (1080, 1920) and f.aspect == pytest.approx(9 / 16)
    assert f.fps == 24 and isinstance(f.fps, int)
    assert f.theme.name == "paper" and f.theme["bg"] == PRESETS["paper"]["bg"]


def test_load_takes_film_from_the_environment(make_film):
    repo = make_film("envfilm")
    assert film.load(None, repo, environ={"FILM": "envfilm"}).id == "envfilm"


def test_a_missing_film_names_the_films_there_are(make_film):
    repo = make_film("demo")
    make_film("alpha")
    with pytest.raises(FileNotFoundError, match=r"no film 'showcase'.*films: alpha, demo"):
        film.load(None, repo, environ={})
    assert film.available(repo) == ["alpha", "demo"]


def test_a_film_json_whose_id_is_not_its_folder_is_refused(make_film):
    repo = make_film("demo")
    (repo / "films" / "demo" / "film.json").write_text(json.dumps({"id": "other"}))
    with pytest.raises(ValueError, match="must be its folder's name, 'demo'"):
        film.load("demo", repo)


# ------------------------------------------------------------------------------------------------ format and fps

@pytest.mark.parametrize("fmt, size", [
    (None, (1920, 1080)), ("landscape", (1920, 1080)), ("vertical", (1080, 1920)), ("square", (1080, 1080)),
    ("portrait", (1080, 1350)), ("cinema", (1920, 804)), ({"width": 1280, "height": 720}, (1280, 720)),
])
def test_the_format_is_a_preset_or_a_size(fmt, size):
    assert film.parse_format(fmt) == size


@pytest.mark.parametrize("bad", ["imax", {"width": 1920}, {"width": 0, "height": 10}, {"width": 19.5, "height": 10},
                                 {"width": True, "height": 10}, 1080])
def test_a_bad_format_is_refused(bad):
    with pytest.raises(ValueError):
        film.parse_format(bad)


def test_fps_defaults_to_30_and_may_be_fractional():
    assert film.parse_fps(None) == 30
    assert film.parse_fps(25) == 25 and film.parse_fps(24.0) == 24 and isinstance(film.parse_fps(24.0), int)
    assert film.parse_fps(29.97) == 29.97
    for bad in (0, -24, "30", True, float("nan")):
        with pytest.raises(ValueError):
            film.parse_fps(bad)


def test_a_film_json_without_format_fps_or_theme_takes_the_defaults(make_film):
    f = film.load("demo", make_film("demo"))
    assert f.size == (1920, 1080) and f.fps == 30
    assert f.theme == theme.resolve("noir", PRESETS)  # the engine's default preset
    assert f.proxy_res == (960, 540)


def test_the_proxy_is_half_the_logical_frame():
    assert film.Film("x", {"format": "vertical"}).proxy_res == (540, 960)
    assert film.Film("x", {"format": "portrait"}).proxy_res == (540, 675)
    assert film.Film("x", {"format": "cinema"}).proxy_res == (960, 402)
    assert film.Film("x", {"format": {"width": 1001, "height": 501}}).proxy_res == (500, 250)  # round half to even


# ------------------------------------------------------------------------------------------------------- theme

def test_the_theme_extends_a_preset_with_overrides(make_film):
    f = film.load("demo", make_film("demo", theme={"extends": "noir", "accent": "#3d7bff"}))
    assert f.theme.name == "noir*" and f.theme["accent"] == "#3d7bff" and f.theme["bg"] == PRESETS["noir"]["bg"]


def test_a_theme_that_does_not_resolve_fails_when_asked_for(make_film):
    f = film.load("demo", make_film("demo", theme="sepia"))
    with pytest.raises(theme.ThemeError, match="unknown theme 'sepia'"):
        f.theme


def test_presets_can_be_handed_in(tmp_path):
    f = film.Film("x", {"theme": "paper"}, repo=tmp_path, presets=PRESETS)  # no themes.json under tmp_path
    assert f.theme.kind == "light"


# ------------------------------------------------------------------------------------------------------ layout

def test_the_layout_is_the_conventions(tmp_path):
    f = film.Film("demo", {}, repo=tmp_path)
    assert f.root == tmp_path / "films/demo"
    assert f.path("audio/mix/mix.wav") == tmp_path / "films/demo/audio/mix/mix.wav"  # film.json paths
    assert f.shot_path("hero_orbit") == tmp_path / "films/demo/blender/shots/hero_orbit.py"
    assert f.track_path("hero_orbit") == tmp_path / "films/demo/data/track/hero_orbit.json"
    assert f.look_path("hero_orbit") == tmp_path / "films/demo/data/look/hero_orbit.json"
    # what is rendered goes under out/<id>/: the plate, its proxy beside it, look stills, saved scenes
    p = f.plate_paths("hero_orbit", 7)
    assert p.exr == tmp_path / "out/demo/plates/hero_orbit/0007.exr"
    assert p.proxy == tmp_path / "out/demo/plates/hero_orbit/proxy/0007.png"
    assert f.plates_dir("hero_orbit") == p.exr.parent
    assert f.look_still("hero_orbit", 47) == tmp_path / "out/demo/look/hero_orbit/0047.png"
    assert f.blend_path("hero_orbit") == tmp_path / "out/demo/blender/hero_orbit.blend"


def test_shots_are_the_films_shot_files_and_spec_is_its_look_file(tmp_path):
    f = film.Film("demo", {}, repo=tmp_path)
    assert f.shots() == [] and f.spec("hero") is None
    f.shots_dir.mkdir(parents=True)
    for name in ("hero.py", "b.py", "_helpers.py", "notes.txt"):
        (f.shots_dir / name).write_text("")
    assert f.shots() == ["b", "hero"]
    f.look_path("hero").parent.mkdir(parents=True)
    f.look_path("hero").write_text(json.dumps({"fstop": 2.0}))
    assert f.spec("hero") == {"fstop": 2.0}
