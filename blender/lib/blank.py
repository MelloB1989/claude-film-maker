"""The black-frame guard: a frame that comes out blank or bad is rendered again, and one that stays so stops the render.

Why: with two Blender renders sharing the GPU, Cycles 5.2.2 on Metal wrote runs of all-black frames, with no error and a
clean exit code (Task 12). Rendered alone, the same frames were fine. A silent black frame in a delivered plate is not
acceptable, so every frame is checked as soon as it is written (lib/export.py render_frame). A frame is not fit to
deliver (`fault`) when:
  - any RGB value is not finite (NaN, or +-inf from a half-float overflow): the engine's bloom spreads one such pixel
    through its downsample and blur into a black or garbage block of the film, and nothing downstream checks;
  - it is blank: its brightest RGB value is at most 1e-4 in the linear EXR plate, or one code value (1/255) in the 8-bit
    PNG proxy; alpha is not looked at;
  - one of its tiles is black: Cycles 5.2 always renders in tiles (TILE px, laid from the image's bottom-left corner),
    and a tile that failed comes out black while the rest is lit, so the whole frame's brightest value misses it. Every
    tile-sized block must have a value above the limit (the ink world alone reads about 0.006).

  is_blank(px)            blank = the brightest RGB value is at most the limit (NaNs are not blank: fault() says so).
  fault(px, tile=...)     what is wrong with a frame (non-finite values, blank, a black tile), or None.
  render_checked(...)     render, check, and on a bad frame render again, up to MAX_RETRIES more times, logging every
                          attempt. Before retry k it waits k * RETRY_PAUSE s: the incident's runs were 19 and 21 frames
                          long (20 to 40 s of rendering), and an instant retry would land in the same spell. A frame
                          that is still bad raises BadFrameError, naming the shot, the film frame, the fault and the
                          path. A frame the shot declares black is only checked for non-finite values.
  black_ok(SHOT)          the film frames a shot declares legitimately black (SHOT["black_ok"], documented in
                          render.py): the guard does not ask them to be lit.
  parse_force_blank(env)  the test hook's variable, GITLOOM_FORCE_BLANK, which makes export.render_frame render chosen
                          frames black on purpose, to prove the retry path. It does nothing unless it is set.
  frames_spec(frames)     film frames as a --frames value, for the error's "to finish it".

Everything here is bpy-free (tested under the tools project); lib/export.py wires it to Blender.
"""
from __future__ import annotations

import re
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import timing

BLANK_LINEAR = 1e-4  # a linear plate is blank when its brightest RGB value is at most this
TILE = 2048  # px: Cycles' render tile (scene.cycles.tile_size, whose default this is)
MAX_RETRIES = 2  # a bad frame is rendered again up to this many more times, then the render fails
RETRY_PAUSE = 15.0  # s: retry k waits k * RETRY_PAUSE first (15 s, then 30 s)
FORCE_ENV = "GITLOOM_FORCE_BLANK"


def _say(message: str) -> None:
    print(message, flush=True)


def _rgb(px) -> np.ndarray:
    px = np.asarray(px)
    if px.ndim != 3 or px.shape[2] < 3:
        raise ValueError(f"pixels must be (height, width, 3 or 4), not shape {px.shape}")
    return px[..., :3]


def peak(px) -> float:
    """The brightest RGB value of a frame, ignoring NaNs (NaN if they are all NaN; -inf for an empty frame)."""
    rgb = _rgb(px)
    if rgb.size == 0:
        return float("-inf")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an all-NaN frame: nanmax warns, and returns NaN
        return float(np.nanmax(rgb))


def _limit(rgb: np.ndarray, limit: float | None) -> float:
    if limit is not None:
        return limit
    return int(np.iinfo(rgb.dtype).max // 255) if np.issubdtype(rgb.dtype, np.integer) else BLANK_LINEAR


def is_blank(px, limit: float | None = None) -> bool:
    """Is this frame blank: is its brightest RGB value at most `limit`?

    px: (height, width, 3 or 4) pixels; alpha is not looked at. A float array is a linear plate and `limit` defaults to
    BLANK_LINEAR (1e-4); an integer array is an 8-bit proxy and `limit` defaults to one code value (1/255 of full
    scale). An explicit `limit` is in the array's own units. NaNs make the frame NOT blank (a bad frame is not an empty
    one: `fault` says what is wrong with it). An empty frame is blank."""
    rgb = _rgb(px)
    if rgb.size == 0:
        return True
    top = rgb.max()
    if top != top:  # max() passes a NaN through
        return False
    return bool(top <= _limit(rgb, limit))


@dataclass(frozen=True)
class Fault:
    """Why a frame is not fit to deliver."""
    kind: str  # "nonfinite", "blank" or "tile"
    detail: str  # in words, e.g. "3 of 72 RGB values are not finite: 2 NaN, 1 inf"

    @property
    def state(self) -> str:
        return "blank" if self.kind == "blank" else "bad"

    def __str__(self) -> str:
        return f"blank ({self.detail})" if self.kind == "blank" else f"bad: {self.detail}"


def _spans(n: int, size: int, from_end: bool) -> list[tuple[int, int]]:
    """[a, b) spans of `size` covering 0..n, laid from 0, or from n (the last span is then the short one at 0)."""
    if from_end:
        return [(max(0, b - size), b) for b in range(n, 0, -size)]
    return [(a, min(n, a + size)) for a in range(0, n, size)]


def black_tile(px, tile: int = TILE, limit: float | None = None) -> tuple[int, int, int, int] | None:
    """The first tile-sized block of the frame whose brightest RGB value is at most `limit`, as (x0, x1, y0, y1) px from
    the top-left (ends exclusive), or None if every block has light. px is stored top row first; Cycles lays its tiles
    from the image's bottom-left corner (Blender's first row), and the grid laid from the top-left is checked too, so
    the check does not hang on which way up a renderer counts."""
    rgb = _rgb(px)
    h, w = rgb.shape[:2]
    if h <= tile and w <= tile:
        return None  # one tile: the frame itself (is_blank)
    top = _limit(rgb, limit)
    for from_bottom in (True, False):
        for y0, y1 in sorted(_spans(h, tile, from_bottom)):
            for x0, x1 in _spans(w, tile, False):
                block = rgb[y0:y1, x0:x1]
                if block.size and not block.max() > top:  # "not >": a NaN block counts as dark here
                    return x0, x1, y0, y1
    return None


def fault(px, limit: float | None = None, tile: int | None = TILE, black_ok: bool = False) -> Fault | None:
    """What is wrong with this frame, or None if it is fit to deliver: any non-finite RGB value, then (unless the shot
    declares the frame black, `black_ok`) a blank frame, or a black tile of `tile` px (None: no tiles, as in a proxy)."""
    rgb = _rgb(px)
    if np.issubdtype(rgb.dtype, np.floating) and rgb.size:
        nan, inf = int(np.isnan(rgb).sum()), int(np.isinf(rgb).sum())
        if nan or inf:
            return Fault("nonfinite", f"{nan + inf} of {rgb.size} RGB values are not finite: {nan} NaN, {inf} inf")
    if black_ok:
        return None
    if is_blank(rgb, limit):
        return Fault("blank", f"brightest RGB value {peak(rgb):g}")
    if tile:
        box = black_tile(rgb, tile, limit)
        if box is not None:
            x0, x1, y0, y1 = box
            h, w = rgb.shape[:2]
            return Fault("tile", f"a black tile at x {x0}-{x1}, y {y0}-{y1} of the {w}x{h} frame (brightest RGB value "
                                 f"{peak(rgb[y0:y1, x0:x1]):g}), the rest lit")
    return None


class BadFrameError(RuntimeError):
    """A frame came out blank or bad on every attempt, so the render must stop. Its plate stays where it was written."""

    def __init__(self, shot: str, film_frame: int, path: Path, attempts: int, fault: Fault):
        self.shot, self.film_frame, self.path, self.attempts, self.fault = shot, film_frame, path, attempts, fault
        n = f"{attempts} attempt" + ("" if attempts == 1 else "s")
        super().__init__(f"[{shot}] film frame {film_frame} is {fault.state} after {n} ({fault.detail}); the "
                         f"{fault.state} plate is at {path}")


def render_checked(render_once: Callable[[int], np.ndarray], *, shot: str, film_frame: int, path: Path,
                   black_ok: bool = False, tile: int | None = TILE, retries: int = MAX_RETRIES,
                   pause: float = RETRY_PAUSE, log: Callable[[str], None] | None = None,
                   sleep: Callable[[float], None] = time.sleep) -> np.ndarray:
    """Render a frame until it is fit to deliver (`fault`). `render_once(attempt)` (attempt from 1) renders and writes
    the frame and returns its linear RGBA pixels as written; `path` is the plate's file, for the log and the error;
    `tile` the render's tile size in px (None: not rendered in tiles).

    A blank or bad frame is rendered again, up to `retries` more times, waiting k * `pause` s before retry k; every
    attempt that follows a bad one is logged, and the good render is kept. A frame that is still bad raises
    BadFrameError. `black_ok` (a frame the shot declares black) is only checked for non-finite values. Returns the
    pixels of the attempt that was kept."""
    log = log or _say
    attempts = 1 + retries
    where = f"[{shot}] film frame {film_frame}"
    for attempt in range(1, attempts + 1):
        if attempt > 1 and pause > 0:
            sleep(pause * (attempt - 1))
        px = render_once(attempt)
        bad = fault(px, tile=tile, black_ok=black_ok)
        if bad is None:
            if attempt > 1:
                log(f"{where}: attempt {attempt} of {attempts} is lit, every value finite (brightest RGB value "
                    f"{peak(px):g}): kept")
            return px
        if attempt < attempts:
            wait = f" in {pause * attempt:g} s" if pause > 0 else ""
            log(f"{where}: attempt {attempt} of {attempts} came out {bad} at {path}: rendering it again{wait}")
        else:
            log(f"{where}: attempt {attempt} of {attempts} came out {bad} at {path}: giving up")
    raise BadFrameError(shot, film_frame, path, attempts, bad)


def black_ok(shot: dict) -> Callable[[int], bool]:
    """SHOT["black_ok"] as a predicate on film frames: the frames this shot declares legitimately black, which the guard
    skips. It takes what SHOT["look"] takes (a "a-b,c" string, or a list or range of film frames), or a function of the
    film frame. A shot without it has no black frames."""
    spec = shot.get("black_ok")
    if callable(spec):
        return lambda f: bool(spec(f))
    try:
        if isinstance(spec, str) and spec.strip():
            frames = set(timing.parse_frames(spec))
        else:
            frames = {int(f) for f in spec or ()}
    except (TypeError, ValueError) as e:
        raise ValueError(f'SHOT["black_ok"] = {spec!r}: {e}') from e
    return frames.__contains__


def frames_spec(frames) -> str:
    """Film frames as a --frames value (timing.parse_frames' inverse): sorted, each once, runs as a-b, so an error can
    say which frames to render again."""
    runs: list[list[int]] = []
    for f in sorted(set(int(f) for f in frames)):
        if runs and f == runs[-1][1] + 1:
            runs[-1][1] = f
        else:
            runs.append([f, f])
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)


_FORCE_ITEM = re.compile(r"\s*(\d+)(?::(\d+))?\s*")


def parse_force_blank(value: str | None) -> dict[int, int]:
    """GITLOOM_FORCE_BLANK, the test hook: "F" or "F:N" items, comma-separated, each a film frame to render black on its
    first N attempts (default 1). Unset or empty: no frames. Anything else that does not parse raises ValueError, so a
    mistyped hook is noticed and never just does nothing."""
    if value is None or not value.strip():
        return {}
    out: dict[int, int] = {}
    for item in value.split(","):
        m = _FORCE_ITEM.fullmatch(item)
        if not m or (m.group(2) is not None and int(m.group(2)) < 1):
            raise ValueError(f'{FORCE_ENV}={value!r}: expected film frames as "F" or "F:N" (N attempts to blank, at '
                             "least 1), comma-separated")
        out[int(m.group(1))] = int(m.group(2) or 1)
    return out
