# render.py's wiring, without Blender: a stub bpy lets it import, and prepare() finds the film, puts its theme in use,
# loads and checks the shot and gives its window; Ctx hands build() the film's frame, fps, theme and timing.
import importlib.util
import json
import shutil
import sys
import types
from argparse import Namespace
from pathlib import Path

import pytest

from lib import theme

from conftest import PRESETS

BLENDER = Path(__file__).resolve().parents[1]
EXAMPLES = BLENDER / "examples" / "shots"


@pytest.fixture
def render(monkeypatch):
    """render.py imported against a stub bpy (only its module-level import needs one), and the theme in use restored
    after the test."""
    if importlib.util.find_spec("bpy") is None:
        monkeypatch.setitem(sys.modules, "bpy", types.ModuleType("bpy"))
    spec = importlib.util.spec_from_file_location("render_under_test", BLENDER / "render.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, mod)  # its dataclass looks its module up while it is made
    spec.loader.exec_module(mod)
    keep = theme._current
    yield mod
    theme._current = keep


@pytest.fixture
def demo(make_film):
    """A vertical 24 fps film in the paper theme with both examples as its shots and a scene "hero" from 2 s to 6 s."""
    repo = make_film("demo", format="vertical", fps=24, theme="paper")
    root = repo / "films" / "demo"
    (root / "blender" / "shots").mkdir(parents=True)
    for name in ("hero_orbit", "smoke_cube"):
        shutil.copy(EXAMPLES / f"{name}.py", root / "blender" / "shots" / f"{name}.py")
    (root / "data").mkdir()
    (root / "data" / "timeline.json").write_text(json.dumps(
        {"fps": 24, "duration": 8.0, "scenes": [{"id": "open", "start": 0.0, "end": 2.0},
                                                {"id": "hero", "start": 2.0, "end": 6.0}]}))
    return repo


def test_prepare_loads_the_films_shot_and_puts_its_theme_in_use(render, demo):
    f, name, mod, shot, f0, f1 = render.prepare(Namespace(film="demo", shot="hero_orbit"), demo)
    assert (f.id, f.size, f.fps) == ("demo", (1080, 1920), 24)
    assert name == "hero_orbit" and shot is mod.SHOT and callable(mod.build)
    assert (f0, f1) == (48, 144)  # the scene "hero", 2 s to 6 s at 24 fps
    assert theme.current().name == "paper" and theme.linear("bg") == theme.hex_to_linear(PRESETS["paper"]["bg"])


def test_prepare_takes_a_shot_file_by_path_and_explicit_frames_need_no_scene(render, demo):
    f, name, _mod, _shot, f0, f1 = render.prepare(Namespace(film="demo", shot=str(EXAMPLES / "smoke_cube.py")), demo)
    assert name == "smoke_cube" and (f0, f1) == (40, 60)
    assert f.plate_paths(name, 0).exr == demo / "out/demo/plates/smoke_cube/0000.exr"


def test_prepare_fails_before_building_on_a_bad_shot_or_window(render, demo):
    shots = demo / "films" / "demo" / "blender" / "shots"
    (shots / "typo.py").write_text('SHOT = {"scene": "hero", "trak": ["x"]}\n\ndef build(ctx):\n    pass\n')
    with pytest.raises(ValueError, match="unknown keys"):
        render.prepare(Namespace(film="demo", shot="typo"), demo)
    (shots / "elsewhere.py").write_text('SHOT = {"scene": "credits"}\n\ndef build(ctx):\n    pass\n')
    with pytest.raises(KeyError, match="no scene 'credits'.*open, hero"):
        render.prepare(Namespace(film="demo", shot="elsewhere"), demo)
    with pytest.raises(FileNotFoundError, match="hero_orbit, smoke_cube"):
        render.prepare(Namespace(film="demo", shot="missing"), demo)
    with pytest.raises(FileNotFoundError, match="no film 'nope'"):
        render.prepare(Namespace(film="nope", shot="hero_orbit"), demo)


def test_ctx_gives_build_the_films_frame_fps_theme_and_clock(render, demo):
    f, name, _mod, _shot, f0, f1 = render.prepare(Namespace(film="demo", shot="hero_orbit"), demo)
    ctx = render.Ctx(None, f, name, "preview", f0, f1, (540, 960), f.timing(), f.spec(name))
    assert ctx.size == (1080, 1920) and ctx.fps == 24 and ctx.theme.name == "paper"
    assert ctx.frame(2.0) == 48 and ctx.time(60) == 2.5
    assert ctx.spec is None  # no data/look/hero_orbit.json
    look = demo / "films" / "demo" / "data" / "look"
    look.mkdir(parents=True)
    (look / "hero_orbit.json").write_text(json.dumps({"orbitDeg": 50}))
    assert f.spec(name) == {"orbitDeg": 50}
