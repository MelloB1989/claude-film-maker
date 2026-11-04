"""WP11's generic spec kinds (level, actor, op) and helpers any kind's planner can use. Areas register their own
kinds from their own modules with filmtools.unreal.spec.register_kind (docs/unreal/dx.md "Writing a kind")."""
from __future__ import annotations

import math


def same(have, want, tol=0.0) -> bool:
    """want ~ have: numbers within tol, angles modulo 360 (tol "angle:0.05"), lists/dicts element-wise (a dict
    compares the keys `want` gives), bools only with bools."""
    if isinstance(tol, str) and tol.startswith("angle:"):
        t = float(tol.split(":", 1)[1])
        if isinstance(want, dict) and isinstance(have, dict):
            return all(same(have.get(k, 0.0), want.get(k, 0.0), tol) for k in set(want) | set(have))
        if isinstance(want, (int, float)) and isinstance(have, (int, float)):
            return abs((float(want) - float(have) + 180.0) % 360.0 - 180.0) <= t
    if isinstance(want, bool) or isinstance(have, bool):
        return isinstance(want, bool) and isinstance(have, bool) and want == have
    if isinstance(want, (int, float)) and isinstance(have, (int, float)):
        return math.isclose(float(want), float(have), abs_tol=float(tol or 0.0))
    if isinstance(want, (list, tuple)) and isinstance(have, (list, tuple)):
        return len(want) == len(have) and all(same(h, w, tol) for h, w in zip(have, want))
    if isinstance(want, dict) and isinstance(have, dict):
        return all(k in have and same(have[k], v, tol) for k, v in want.items())
    return want == have


def changed(spec: dict, state: dict, fields: dict) -> dict:
    """{field: wanted value} for each field in `fields` ({field: tolerance}) the spec gives and the state differs on."""
    return {f: spec[f] for f, tol in fields.items() if spec.get(f) is not None and not same(state.get(f), spec[f], tol)}
