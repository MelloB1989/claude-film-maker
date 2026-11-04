"""Errors an op raises for Claude to act on: what went wrong, what to try instead, the nearest valid names.

    from ..errors import OpError, closest, not_found
    raise not_found("actor", label, [a.get_actor_label() for a in actors], hint="list them with level.find")

The server answers an OpError with {"ok": false, "code", "message", "hint", "candidates", "error"} instead of a bare
traceback (any other exception still comes back as a traceback in "error"). Codes: not_found, bad_args, conflict
(something is in the way: a dialog would open, an asset is in use), unsupported (this engine/platform cannot),
timeout, engine (the engine refused; its message is in `message`), failed (a check after the change did not pass).
"""
from __future__ import annotations

import difflib

CODES = ("not_found", "bad_args", "conflict", "unsupported", "timeout", "engine", "failed")


class OpError(Exception):
    def __init__(self, message: str, *, code: str = "failed", hint: str = "", candidates: list | tuple = (),
                 details: dict | None = None):
        super().__init__(message)
        self.message, self.code, self.hint = message, code, hint
        self.candidates, self.details = list(candidates), dict(details or {})

    def __str__(self) -> str:
        s = self.message
        if self.candidates:
            s += f"; did you mean {', '.join(map(repr, self.candidates))}?"
        return s + (f" ({self.hint})" if self.hint else "")

    def to_json(self) -> dict:
        return {"code": self.code, "message": self.message, "hint": self.hint, "candidates": self.candidates,
                "details": self.details}


def closest(name: str, names, n: int = 3) -> list:
    """The few names nearest `name` (case-insensitive), for "did you mean"."""
    names = [str(x) for x in names]
    low = {x.lower(): x for x in names}
    return [low[m] for m in difflib.get_close_matches(str(name).lower(), list(low), n=n, cutoff=0.5)]


def not_found(kind: str, name: str, names=(), hint: str = "") -> OpError:
    """An OpError for a missing actor/asset/track/...: `names` are the ones that do exist."""
    return OpError(f"no {kind} {name!r}", code="not_found", candidates=closest(name, names), hint=hint)
