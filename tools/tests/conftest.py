"""Every test runs against films it makes itself, never against the repo's own films/, data/ or audio/.

The autouse fixture points paths.ROOT at an empty folder (so a tool that resolves a film without one selected fails
instead of reading the repo) and clears $FILM; `film` makes films/demo/ under a temporary root and selects it.
"""
import json
from pathlib import Path

import pytest

from filmtools import paths


def make_film(root: Path, fid: str = "demo", **doc) -> paths.FilmPaths:
    """films/<fid>/ under `root`: a film.json (landscape, 30 fps, plus `doc`), and empty data/ and audio/."""
    d = root / "films" / fid
    (d / "data").mkdir(parents=True, exist_ok=True)
    (d / "audio").mkdir(parents=True, exist_ok=True)
    (d / "film.json").write_text(json.dumps({"id": fid, "title": "Demo", "format": "landscape", "fps": 30, **doc}))
    return paths.film_paths(fid, root)


@pytest.fixture(autouse=True)
def isolated(tmp_path_factory, monkeypatch):
    monkeypatch.delenv("FILM", raising=False)
    monkeypatch.setattr(paths, "ROOT", tmp_path_factory.mktemp("no-repo"))
    paths.reset()
    yield
    paths.reset()


@pytest.fixture
def film(tmp_path) -> paths.FilmPaths:
    """films/demo/ under tmp_path, selected as the current film."""
    return paths.use_film(make_film(tmp_path))
