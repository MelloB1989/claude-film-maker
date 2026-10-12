"""Repo-relative paths. Every tool resolves files from the repo root, never from the working directory."""
from pathlib import Path


def find_root(start: Path | None = None) -> Path:
    p = (start or Path(__file__)).resolve()
    for d in [p, *p.parents]:
        if (d / "docs" / "specs").is_dir() and (d / "tools" / "pyproject.toml").is_file():
            return d
    raise RuntimeError(f"not inside the gitloom-film repo: {p}")


ROOT = find_root()
DATA = ROOT / "data"
AUDIO = ROOT / "audio"
OUT = ROOT / "out"
APP = ROOT / "app"
FONTS = ROOT / "fonts"
