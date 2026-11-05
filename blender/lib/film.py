"""The film a Blender run works on: which one, its film.json, and where everything of it lives (docs/CONVENTIONS.md).

Which film, first match wins: an explicit id (render.py --film <id>), the FILM environment variable, then DEFAULT_FILM.
`load()` reads films/<id>/film.json; the fields Blender uses:
  format   the logical frame: a preset (FORMATS: landscape 1920x1080, vertical 1080x1920, square 1080x1080,
           portrait 1080x1350, cinema 1920x804) or {"width": W, "height": H} px. Default landscape.
  fps      film frames per second (default 30): Blender's frame n is film frame n, at n / fps s.
  theme    the palette (lib/theme.py): a preset in app/src/engine/themes.json or {"extends": preset, ...}.
  vo, audio.analysis, audio.bpm/offset/beatsPerBar   timing (lib/timing.py for_film).

Where things live, for film <id> and shot <shot> (paths in film.json are relative to the film's folder):
  films/<id>/blender/shots/<shot>.py        the shot (render.py --shot <shot>)
  films/<id>/data/timeline.json             the scene windows the engine exports (else data/vo.json's scenes)
  films/<id>/data/look/<shot>.json          optional: the shot's world, shared with the engine scene that composites it
                                            (render.py hands it to build() as ctx.spec)
  films/<id>/data/track/<shot>.json         tracked anchors, written by render.py (small; committed)
  out/<id>/plates/<shot>/####.exr           the plate: linear half-float RGBA, #### = film frame - the shot's f0
  out/<id>/plates/<shot>/proxy/####.png     its 8-bit sRGB proxy at half the logical size
  out/<id>/look/<shot>/<film frame>.png     look stills (look mode)
  out/<id>/blender/<shot>.blend             --save-blend
out/ is $FILM_OUT when it is set (a review renders its stills there, leaving the film's plates be).

bpy-free (tested without Blender).
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_FILM = "showcase"
FILM_ENV = "FILM"
OUT_ENV = "FILM_OUT"
FORMATS = {
    "landscape": (1920, 1080),
    "vertical": (1080, 1920),
    "square": (1080, 1080),
    "portrait": (1080, 1350),
    "cinema": (1920, 804),
}
DEFAULT_FORMAT = "landscape"
DEFAULT_FPS = 30
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def film_id(explicit: str | None = None, environ=None) -> str:
    """The film to work on: `explicit` (--film), else $FILM, else DEFAULT_FILM. Raises ValueError for an id that is not
    a plain folder name (letters, digits, '_', '-', '.'; no path)."""
    env = os.environ if environ is None else environ
    fid = explicit or env.get(FILM_ENV) or DEFAULT_FILM
    if not _ID.fullmatch(fid) or ".." in fid:
        raise ValueError(f"film id {fid!r} is not a folder name under films/ (letters, digits, '_', '-', '.')")
    return fid


def parse_format(fmt) -> tuple[int, int]:
    """film.json `format` as the logical (width, height) px: a preset's name (FORMATS) or {"width": W, "height": H}."""
    if fmt is None:
        return FORMATS[DEFAULT_FORMAT]
    if isinstance(fmt, str):
        if fmt not in FORMATS:
            raise ValueError(f"unknown format {fmt!r} (presets: {', '.join(FORMATS)}; "
                             'or {"width": W, "height": H})')
        return FORMATS[fmt]
    if isinstance(fmt, dict):
        w, h = fmt.get("width"), fmt.get("height")
        if isinstance(w, int) and isinstance(h, int) and not isinstance(w, bool) and w > 0 and h > 0:
            return w, h
        raise ValueError(f"format {fmt!r}: width and height must be positive whole px")
    raise ValueError(f"format {fmt!r}: a preset's name ({', '.join(FORMATS)}) or {{\"width\": W, \"height\": H}}")


def parse_fps(fps) -> float | int:
    """film.json `fps` (default 30): a positive number; a whole one comes back as an int."""
    if fps is None:
        return DEFAULT_FPS
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0:
        raise ValueError(f"fps {fps!r}: a positive number of frames per second")
    return int(fps) if float(fps).is_integer() else float(fps)


@dataclass(frozen=True)
class PlatePaths:
    exr: Path
    proxy: Path


class Film:
    """A film's config and layout. `config` is film.json's content ({} for every default); `repo` the checkout the
    films/ and out/ folders are in; `presets` the theme presets (default: the engine's themes.json, read when the theme
    is first asked for)."""

    def __init__(self, film_id: str, config: dict | None = None, repo: str | Path = REPO, presets: dict | None = None):
        self.id = film_id
        self.config = dict(config or {})
        self.repo = Path(repo)
        self.size = parse_format(self.config.get("format"))
        self.fps = parse_fps(self.config.get("fps"))
        self._presets = presets
        self._theme = None
        self._timing = None

    def __repr__(self) -> str:
        return f"Film({self.id!r}, {self.width}x{self.height} @ {self.fps} fps)"

    # the frame
    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]

    @property
    def aspect(self) -> float:
        return self.width / self.height

    @property
    def proxy_res(self) -> tuple[int, int]:
        """The proxies' size: half the logical frame (rounded)."""
        return max(1, round(self.width / 2)), max(1, round(self.height / 2))

    # the palette and the clock
    @property
    def theme(self):
        """film.json's `theme`, resolved (lib/theme.py; raises ThemeError if it does not resolve)."""
        if self._theme is None:
            from . import theme

            presets = self._presets if self._presets is not None else theme.load_presets(self.repo / theme.PRESETS_REL)
            self._theme = theme.resolve(self.config.get("theme"), presets)
        return self._theme

    def timing(self):
        """The film's timing (lib/timing.py for_film), loaded once."""
        if self._timing is None:
            from . import timing

            self._timing = timing.for_film(self)
        return self._timing

    # the film's own folder
    @property
    def root(self) -> Path:
        return self.repo / "films" / self.id

    def path(self, rel: str | Path) -> Path:
        """A path in film.json, relative to the film's folder."""
        return self.root / rel

    @property
    def shots_dir(self) -> Path:
        return self.root / "blender" / "shots"

    def shot_path(self, shot: str) -> Path:
        return self.shots_dir / f"{shot}.py"

    def shots(self) -> list[str]:
        """The film's shots: the names of films/<id>/blender/shots/*.py (not those starting with '_' or '.')."""
        if not self.shots_dir.is_dir():
            return []
        return sorted(p.stem for p in self.shots_dir.glob("*.py") if not p.name.startswith(("_", ".")))

    def track_path(self, shot: str) -> Path:
        return self.root / "data" / "track" / f"{shot}.json"

    def look_path(self, shot: str) -> Path:
        return self.root / "data" / "look" / f"{shot}.json"

    def spec(self, shot: str) -> dict | None:
        """The shot's shared world (data/look/<shot>.json), or None when it has none."""
        p = self.look_path(shot)
        return json.loads(p.read_text()) if p.exists() else None

    # what is rendered
    @property
    def out(self) -> Path:
        """out/<id>/ in the repo, or under $FILM_OUT."""
        root = os.environ.get(OUT_ENV)
        return (Path(root) if root else self.repo / "out") / self.id

    def plates_dir(self, shot: str) -> Path:
        return self.out / "plates" / shot

    def plate_paths(self, shot: str, index: int) -> PlatePaths:
        """Where frame `index` (film frame - the shot's f0) of a shot's plate goes: the EXR and its proxy."""
        n = f"{index:04d}"
        d = self.plates_dir(shot)
        return PlatePaths(d / f"{n}.exr", d / "proxy" / f"{n}.png")

    def look_still(self, shot: str, film_frame: int) -> Path:
        """A look-mode still, named by film frame."""
        return self.out / "look" / shot / f"{film_frame:04d}.png"

    def blend_path(self, shot: str) -> Path:
        return self.out / "blender" / f"{shot}.blend"


def available(repo: str | Path = REPO) -> list[str]:
    """The films in a checkout: the folders under films/ with a film.json."""
    d = Path(repo) / "films"
    return sorted(p.parent.name for p in d.glob("*/film.json")) if d.is_dir() else []


def load(film: str | None = None, repo: str | Path = REPO, *, environ=None, presets: dict | None = None) -> Film:
    """The film `film` (else $FILM, else DEFAULT_FILM: film_id) from <repo>/films/<id>/film.json. Raises
    FileNotFoundError naming the films there are when it has no film.json, and ValueError when the file's `id` is not
    its folder's name or a field Blender reads is malformed."""
    fid = film_id(film, environ)
    path = Path(repo) / "films" / fid / "film.json"
    if not path.exists():
        have = available(repo)
        raise FileNotFoundError(f"no film {fid!r}: {path} does not exist (films: {', '.join(have) or 'none'}; pick one "
                                f"with --film <id> or {FILM_ENV}=<id>)")
    config = json.loads(path.read_text())
    if not isinstance(config, dict):
        raise ValueError(f"{path}: film.json holds an object")
    if config.get("id", fid) != fid:
        raise ValueError(f"{path}: its id is {config['id']!r}, but it must be its folder's name, {fid!r}")
    return Film(fid, config, repo, presets)
