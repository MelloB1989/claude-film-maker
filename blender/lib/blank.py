"""The black-frame guard: a frame that comes out blank is rendered again, and one that stays blank stops the render.

Why: with two Blender renders sharing the GPU, Cycles 5.2.2 on Metal wrote runs of all-black frames, with no error and a
clean exit code (Task 12). Rendered alone, the same frames were fine. A silent black frame in a delivered plate is not
acceptable, so every frame is checked as soon as it is written (lib/export.py render_frame).

  is_blank(px)            blank = the brightest RGB value is at most 1e-4 in the linear EXR plate, or one code value
                          (1/255) in the 8-bit PNG proxy; alpha is not looked at. A frame with NaNs is NOT blank (a
                          bad frame is not an empty one) and its NaNs are logged.
  render_checked(...)     render, check, and on a blank frame render again, up to MAX_RETRIES more times, logging every
                          attempt. Before retry k it waits k * RETRY_PAUSE s: the incident's runs were 19 and 21 frames
                          long (20 to 40 s of rendering), and an instant retry would land in the same spell. A frame
                          that is still blank raises BlankFrameError, naming the shot, the film frame and the path.
  black_ok(SHOT)          the film frames a shot declares legitimately black (SHOT["black_ok"], documented in
                          render.py): the guard skips them.
  parse_force_blank(env)  the test hook's variable, GITLOOM_FORCE_BLANK, which makes export.render_frame render chosen
                          frames black on purpose, to prove the retry path. It does nothing unless it is set.
  frames_spec(frames)     film frames as a --frames value, for the error's "to finish it".

Everything here is bpy-free (tested under the tools project); lib/export.py wires it to Blender.
"""
from __future__ import annotations

import logging
import re
import time
import warnings
from pathlib import Path
from typing import Callable

import numpy as np

from . import timing

BLANK_LINEAR = 1e-4  # a linear plate is blank when its brightest RGB value is at most this
MAX_RETRIES = 2  # a blank frame is rendered again up to this many more times, then the render fails
RETRY_PAUSE = 15.0  # s: retry k waits k * RETRY_PAUSE first (15 s, then 30 s)
FORCE_ENV = "GITLOOM_FORCE_BLANK"

_log = logging.getLogger(__name__)


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


def is_blank(px, limit: float | None = None, log: Callable[[str], None] | None = None) -> bool:
    """Is this frame blank: is its brightest RGB value at most `limit`?

    px: (height, width, 3 or 4) pixels; alpha is not looked at. A float array is a linear plate and `limit` defaults to
    BLANK_LINEAR (1e-4); an integer array is an 8-bit proxy and `limit` defaults to one code value (1/255 of full
    scale). An explicit `limit` is in the array's own units. NaNs make the frame NOT blank, and are reported through
    `log(message)` (default: a warning on the logging module). An empty frame is blank."""
    rgb = _rgb(px)
    if limit is None:
        limit = int(np.iinfo(rgb.dtype).max // 255) if np.issubdtype(rgb.dtype, np.integer) else BLANK_LINEAR
    if rgb.size == 0:
        return True
    top = rgb.max()
    if top != top:  # max() passes a NaN through
        (log or _log.warning)(f"{int(np.isnan(rgb).sum())} of {rgb.size} RGB values are NaN: "
                              "the frame is not counted as blank")
        return False
    return bool(top <= limit)


class BlankFrameError(RuntimeError):
    """A frame came out blank on every attempt, so the render must stop. Its blank plate stays where it was written."""

    def __init__(self, shot: str, film_frame: int, path: Path, attempts: int, peak_value: float):
        self.shot, self.film_frame, self.path, self.attempts, self.peak = shot, film_frame, path, attempts, peak_value
        n = f"{attempts} attempt" + ("" if attempts == 1 else "s")
        super().__init__(f"[{shot}] film frame {film_frame} is blank after {n} (brightest RGB value {peak_value:g}); "
                         f"the blank plate is at {path}")


def render_checked(render_once: Callable[[int], np.ndarray], *, shot: str, film_frame: int, path: Path,
                   black_ok: bool = False, retries: int = MAX_RETRIES, pause: float = RETRY_PAUSE,
                   log: Callable[[str], None] | None = None,
                   sleep: Callable[[float], None] = time.sleep) -> np.ndarray:
    """Render a frame until it is lit. `render_once(attempt)` (attempt from 1) renders and writes the frame and returns
    its linear RGBA pixels as written; `path` is the plate's file, for the log and the error.

    A blank frame is rendered again, up to `retries` more times, waiting k * `pause` s before retry k; every attempt
    that follows a blank one is logged, and the lit render is kept. A frame that is still blank raises BlankFrameError.
    `black_ok` (a frame the shot declares black) skips the check. Returns the pixels of the attempt that was kept."""
    log = log or _say
    attempts = 1 + retries
    where = f"[{shot}] film frame {film_frame}"
    for attempt in range(1, attempts + 1):
        if attempt > 1 and pause > 0:
            sleep(pause * (attempt - 1))
        px = render_once(attempt)
        if black_ok:
            return px
        if not is_blank(px, log=lambda message: log(f"{where}: {message}")):
            if attempt > 1:
                log(f"{where}: attempt {attempt} of {attempts} is lit (brightest RGB value {peak(px):g}): kept")
            return px
        top = peak(px)
        if attempt < attempts:
            wait = f" in {pause * attempt:g} s" if pause > 0 else ""
            log(f"{where}: attempt {attempt} of {attempts} came out blank (brightest RGB value {top:g}) at {path}: "
                f"rendering it again{wait}")
        else:
            log(f"{where}: attempt {attempt} of {attempts} came out blank (brightest RGB value {top:g}) at {path}: "
                "giving up")
    raise BlankFrameError(shot, film_frame, path, attempts, top)


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
