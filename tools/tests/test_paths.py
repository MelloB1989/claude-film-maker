from pathlib import Path

import pytest

from gitloom_film import paths


def test_root_is_the_film_repo():
    assert (paths.ROOT / "docs" / "specs").is_dir()
    assert (paths.ROOT / "tools" / "pyproject.toml").is_file()


def test_named_dirs_hang_off_root():
    assert paths.DATA == paths.ROOT / "data"
    assert paths.AUDIO == paths.ROOT / "audio"
    assert paths.OUT == paths.ROOT / "out"
    assert paths.APP == paths.ROOT / "app"
    assert paths.FONTS == paths.ROOT / "fonts"


def test_find_root_rejects_outside_paths(tmp_path: Path):
    with pytest.raises(RuntimeError, match="not inside the gitloom-film repo"):
        paths.find_root(tmp_path)
