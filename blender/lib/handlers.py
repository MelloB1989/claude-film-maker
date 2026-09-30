"""A frame-change handler that raises fails its frame (render.py; lib/export.py render_frame and track).

Blender calls bpy.app.handlers from C. When a handler raises, Blender prints the traceback, clears the exception and
carries on, so neither scene.frame_set() nor bpy.ops.render.render() (whose motion-blur steps set sub-frames and run
the handlers again) ever sees it. A shot posed by a handler (b01_thread.py's `pose`) that raises on one frame or one
motion-blur step keeps the previous pose, or a half-updated one: the frame renders lit, passes the blank guard, is
tracked, and the run exits 0 with a traceback somewhere in a long log.

So once a shot is built, render.py wraps every function in frame_change_pre and frame_change_post (`GUARD.install`).
A wrapped handler that raises records the failure and raises it on to Blender, which still prints it.
render_frame and track reset the record before each frame_set and check it after the frame_set and after the render:
`check` raises HandlerError, and render.py exits 1, naming the frame and the handler with its traceback.

bpy-free: the handler lists are plain Python lists (bpy.app.handlers' are), and the tests drive them as Blender does.
"""
from __future__ import annotations

import functools
import traceback
from dataclasses import dataclass

_MARK = "_gitloom_guarded"


@dataclass(frozen=True)
class Failure:
    handler: str  # "<list> <function>", e.g. "frame_change_pre pose"
    frame: float | None  # the scene's frame (and sub-frame) when it raised, when the handler was given the scene
    error: str  # "IndexError: list index out of range"
    trace: str  # the formatted traceback


class HandlerError(RuntimeError):
    """A frame-change handler raised since the frame was set: the frame shows a stale or half-updated scene."""

    def __init__(self, where: str, failures: list[Failure]):
        self.where, self.failures = where, list(failures)
        first = self.failures[0]
        at = "" if first.frame is None else f" at frame {first.frame:g}"
        more = len(self.failures) - 1
        also = f" (and {more} more failure{'s' if more > 1 else ''} since the frame was set)" if more else ""
        super().__init__(f"{where}: the {first.handler} handler raised {first.error}{at}{also}, so the frame would "
                         f"show a stale pose\n{first.trace.rstrip()}")


def _frame_of(args) -> float | None:
    scene = args[0] if args else None
    try:
        return float(scene.frame_current + scene.frame_subframe)
    except (AttributeError, TypeError):
        return None


class HandlerGuard:
    """Records the exceptions of the handlers it wraps, for `check` to raise."""

    def __init__(self):
        self._failures: list[Failure] = []

    def wrap(self, fn, kind: str):
        """`fn` recording any exception it raises (then raising it on); a function already wrapped is returned as is."""
        if getattr(fn, _MARK, False):
            return fn
        name = f"{kind} {getattr(fn, '__qualname__', None) or repr(fn)}"

        @functools.wraps(fn)
        def guarded(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                self._failures.append(Failure(name, _frame_of(args), f"{type(e).__name__}: {e}", traceback.format_exc()))
                raise

        setattr(guarded, _MARK, True)
        return guarded

    def install(self, **lists) -> int:
        """Wrap, in place, every function in the named handler lists (frame_change_pre=..., frame_change_post=...).
        Returns how many were newly wrapped; installing again wraps only what was added since."""
        n = 0
        for kind, fns in lists.items():
            for i, fn in enumerate(fns):
                if not getattr(fn, _MARK, False):
                    fns[i] = self.wrap(fn, kind)
                    n += 1
        return n

    def reset(self) -> None:
        """Forget earlier failures: call it before the frame_set a check will cover."""
        self._failures.clear()

    def check(self, where: str) -> None:
        """Raise HandlerError for the failures since the last reset or check, if any (and forget them)."""
        if self._failures:
            failures, self._failures = self._failures, []
            raise HandlerError(where, failures)


GUARD = HandlerGuard()  # the one render.py installs and export.py checks
