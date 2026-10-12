# The bpy-free parts of blender/ run under plain Python with numpy and pytest, no Blender needed:
#   cd blender && python3 -m pytest -q
# Put blender/ on the path so the tests import `lib` the way render.py does inside Blender.
#
# Nothing here reads the repo's films/ or data/: a test that needs a film builds one under tmp_path (`make_film`), and
# theme presets come from PRESETS below, not from the engine's themes.json (test_theme.py cross-checks that file when
# the checkout has it).
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import theme  # noqa: E402

# Two presets in the engine's shape (app/src/engine/themes.json), copied so the tests stand alone.
PRESETS = {
    "noir": {
        "kind": "dark",
        "bg": "#110d10", "bg2": "#161114", "surface": "#1e181c", "surface2": "#282027", "rule": "#2b2229",
        "ruleStrong": "#3e323b", "fg": "#ede7ea", "fgDim": "#a99fa5", "fgFaint": "#6f6469",
        "accent": "#c22b45", "accentBright": "#dc4a63", "accentDim": "#8e1f35",
        "accent2": "#4aad63", "accent2Bright": "#6fcb85", "accent2Dim": "#1c3324",
    },
    "paper": {
        "kind": "light",
        "bg": "#f3efe7", "bg2": "#ebe5da", "surface": "#ffffff", "surface2": "#f7f3ec", "rule": "#dcd3c5",
        "ruleStrong": "#c2b6a3", "fg": "#17141a", "fgDim": "#5a5560", "fgFaint": "#8f8a93",
        "accent": "#d6283f", "accentBright": "#e8475c", "accentDim": "#9b1a2c",
        "accent2": "#1f8a5b", "accent2Bright": "#2fae75", "accent2Dim": "#cfe8db",
    },
}


@pytest.fixture
def presets() -> dict:
    return json.loads(json.dumps(PRESETS))


@pytest.fixture
def noir():
    """The noir preset in use (theme.use), restored to what was in use after the test."""
    keep = theme._current
    yield theme.use(theme.resolve("noir", PRESETS))
    theme._current = keep


@pytest.fixture
def make_film(tmp_path):
    """make_film(id, **film.json fields) writes a repo under tmp_path with films/<id>/film.json and the PRESETS as the
    engine's themes.json, and returns the repo root."""
    def make(film_id: str = "demo", **config) -> Path:
        repo = tmp_path
        presets_file = repo / "app" / "src" / "engine" / "themes.json"
        presets_file.parent.mkdir(parents=True, exist_ok=True)
        presets_file.write_text(json.dumps(PRESETS))
        folder = repo / "films" / film_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "film.json").write_text(json.dumps({"id": film_id, "title": film_id.title(), **config}))
        return repo

    return make
