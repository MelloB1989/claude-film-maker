"""Repo and per-film paths. Every tool resolves files from the repo root and the selected film, never from the
working directory.

A film is a folder `films/<id>/` (docs/CONVENTIONS.md). The film is picked once per process: `--film <id>` on any
CLI (cli.py), else the FILM environment variable, else `showcase`. Library code reads the current film's folders
through `current()` or the lazy module attributes `FILM`, `FILM_DIR`, `DATA`, `AUDIO` and `OUT`, so a test can point
every tool at a temporary film with `use_film(film_paths(id, root=tmp_path))`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FILM = "showcase"


def find_root(start: Path | None = None) -> Path:
    """The repo root: the nearest directory holding both app/package.json and tools/pyproject.toml."""
    p = (start or Path(__file__)).resolve()
    for d in [p, *p.parents]:
        if (d / "app" / "package.json").is_file() and (d / "tools" / "pyproject.toml").is_file():
            return d
    raise RuntimeError(f"not inside the film repo (no app/package.json beside tools/pyproject.toml): {p}")


ROOT = find_root()
FILMS = ROOT / "films"
APP = ROOT / "app"
FONTS = ROOT / "fonts"


class FilmNotFound(SystemExit):
    """No folder for the requested film. A SystemExit, so a CLI prints the message and exits 1."""


@dataclass(frozen=True)
class FilmPaths:
    """One film's folders: `dir` = films/<id>, `data` and `audio` under it, `out` = out/<id> (renders, reviews)."""
    id: str
    dir: Path
    out: Path

    @property
    def data(self) -> Path:
        return self.dir / "data"

    @property
    def audio(self) -> Path:
        return self.dir / "audio"

    @property
    def config(self) -> Path:
        return self.dir / "film.json"

    def path(self, rel: str | Path) -> Path:
        """A path written relative to the film folder (film.json, music_plan.json), resolved."""
        return self.dir / rel

    def rel(self, p: Path) -> str:
        """`p` relative to the film folder, POSIX style, as film.json and music_plan.json record paths."""
        return Path(p).resolve().relative_to(self.dir.resolve()).as_posix()


def film_id(explicit: str | None = None) -> str:
    """The film to work on: `explicit`, else $FILM, else the default film."""
    return explicit or os.environ.get("FILM") or DEFAULT_FILM


def list_films(root: Path | None = None) -> list[str]:
    films = (root or ROOT) / "films"
    return sorted(p.name for p in films.iterdir() if p.is_dir()) if films.is_dir() else []


def film_paths(fid: str, root: Path | None = None, must_exist: bool = True) -> FilmPaths:
    """The paths of film `fid` under `root` (default: the repo root). A missing film folder is a FilmNotFound that
    lists the films there are, unless `must_exist` is false (film-init)."""
    root = Path(root) if root is not None else ROOT
    d = root / "films" / fid
    if must_exist and not d.is_dir():
        have = list_films(root)
        raise FilmNotFound(f"no film {fid!r}: {d} does not exist (films/: {', '.join(have) or 'none yet'}; "
                           "film-init <id> makes one)")
    return FilmPaths(fid, d, root / "out" / fid)


_current: FilmPaths | None = None


def use_film(film: str | FilmPaths | None = None, root: Path | None = None) -> FilmPaths:
    """Select the film every tool works on from here on: a FilmPaths, or an id (None: $FILM, else the default)."""
    global _current
    _current = film if isinstance(film, FilmPaths) else film_paths(film_id(film), root)
    return _current


def current() -> FilmPaths:
    """The selected film, selecting $FILM (else the default film) on first use."""
    return _current if _current is not None else use_film()


def reset() -> None:
    """Forget the selection (the next current() resolves $FILM again)."""
    global _current
    _current = None


_LAZY = {"FILM": lambda f: f.id, "FILM_DIR": lambda f: f.dir, "DATA": lambda f: f.data, "AUDIO": lambda f: f.audio,
         "OUT": lambda f: f.out}


def __getattr__(name: str):
    if name in _LAZY:
        return _LAZY[name](current())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
