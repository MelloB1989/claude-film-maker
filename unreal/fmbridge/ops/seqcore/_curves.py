"""Keys and curves, pure (no `unreal`): the key forms ops accept, interpolation names, a predictive evaluator, angle
unwrapping, look-at rotations and key reduction for dense (baked) data.

A KEY in canonical form is a list: [frame, value, interp] or [frame, value, interp, tangents], where
  frame   display frames at the sequence rate (int, or float for a sub-frame key)
  value   float (float/double channels), bool (bool channels), int (byte/integer channels), str (string channels)
  interp  "auto" | "smart" | "linear" | "constant" | "user" | "break"   (the interpolation LEAVING that key)
  tangents (optional, cubic keys only) {"arrive": slope, "leave": slope, "arrive_weight", "leave_weight"} in value
          units per display frame; given tangents make the key "user" (or "break" when arrive != leave).

Accepted on input (normalize_keys): [f, v], [f, v, interp], [f, v, interp, tangents], {"frame"|"f"|"t", "value"|"v",
"interp", "tangents"|"arrive"/"leave"}. Times may be "2s", "48f", "00:00:02:00" when a Rate is given.
"""
from __future__ import annotations

import math
from typing import Callable, Iterable

INTERPS = ("auto", "smart", "linear", "constant", "user", "break")
_ALIASES = {"step": "constant", "stepped": "constant", "hold": "constant", "const": "constant", "cubic": "auto",
            "smooth": "auto", "smart_auto": "smart", "smartauto": "smart", "lin": "linear", "bezier": "user",
            "auto": "auto", "smart": "smart", "linear": "linear", "constant": "constant", "user": "user",
            "break": "break"}
# the engine's EMovieSceneKeyInterpolation member for each name (add_key's `interpolation`)
KEY_INTERPOLATION = {"auto": "AUTO", "smart": "SMART_AUTO", "linear": "LINEAR", "constant": "CONSTANT", "user": "USER",
                     "break": "BREAK"}


class KeyError_(ValueError):
    """A key the op cannot take; the message names where (keys[3]) and what to write instead."""


def interp_name(v) -> str:
    s = str(v or "auto").strip().lower()
    if s not in _ALIASES:
        raise KeyError_(f"unknown interpolation {v!r}: use one of {', '.join(INTERPS)}")
    return _ALIASES[s]


def interp_from_engine(interp_mode: str, tangent_mode: str = "") -> str:
    """Name a key read back from the engine: ERichCurveInterpMode (RCIM_CONSTANT/LINEAR/CUBIC) and
    ERichCurveTangentMode (RCTM_AUTO/SMART_AUTO/USER/BREAK) -> "constant", "linear", "auto", "smart", "user", "break"."""
    i = str(interp_mode).upper().rsplit(".", 1)[-1]
    t = str(tangent_mode).upper().rsplit(".", 1)[-1]
    if "CONSTANT" in i:
        return "constant"
    if "LINEAR" in i:
        return "linear"
    if "SMART" in t:
        return "smart"
    if "BREAK" in t:
        return "break"
    if "USER" in t:
        return "user"
    return "auto"


def _num(v, what: str):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    raise KeyError_(f"{what}: expected a number, got {v!r}")


def normalize_keys(keys: Iterable, *, interp: str = "auto", value: Callable | None = None, rate=None,
                   where: str = "keys", sort: bool = True, dedupe: bool = True) -> list:
    """Keys in any accepted form -> canonical [[frame, value, interp(, tangents)], ...], sorted by frame; a later key
    at the same frame replaces an earlier one (dedupe). `value` converts/validates each value (e.g. float, bool);
    `rate` (a _time.Rate) lets times be written "2s" or as timecode."""
    from ._time import snap
    default = interp_name(interp)
    out = []
    for i, k in enumerate(keys or []):
        at = f"{where}[{i}]"
        tangents = None
        if isinstance(k, dict):
            f = next((k[n] for n in ("frame", "f", "t", "time") if n in k), None)
            v = next((k[n] for n in ("value", "v") if n in k), None)
            how = k.get("interp", default)
            tangents = k.get("tangents") or ({n: k[n] for n in ("arrive", "leave", "arrive_weight", "leave_weight")
                                              if n in k} or None)
            if f is None or ("value" not in k and "v" not in k):
                raise KeyError_(f"{at}: a key dict needs 'frame' and 'value', got {sorted(k)}")
        elif isinstance(k, (list, tuple)) and len(k) >= 2:
            f, v = k[0], k[1]
            how = k[2] if len(k) > 2 and k[2] is not None else default
            if len(k) > 3:
                tangents = k[3]
            if len(k) > 4:
                raise KeyError_(f"{at}: a key is [frame, value(, interp(, tangents))], got {len(k)} items")
        else:
            raise KeyError_(f"{at}: a key is [frame, value] or {{'frame', 'value'}}, got {k!r}")
        if rate is not None and not isinstance(f, (int, float)):
            f = rate.parse_time(f)
        f = _num(f, f"{at} frame")
        if isinstance(f, bool):
            raise KeyError_(f"{at}: frame must be a number, got {f!r}")
        try:
            v = value(v) if value else v
        except (TypeError, ValueError) as e:
            raise KeyError_(f"{at} value {v!r}: {e}") from None
        how = interp_name(how)
        if tangents:
            if not isinstance(tangents, dict):
                raise KeyError_(f"{at}: tangents is a dict {{'arrive', 'leave'}}, got {tangents!r}")
            bad = set(tangents) - {"arrive", "leave", "arrive_weight", "leave_weight"}
            if bad:
                raise KeyError_(f"{at}: unknown tangent fields {sorted(bad)} (arrive, leave, arrive_weight, "
                                f"leave_weight)")
            tangents = {n: float(x) for n, x in tangents.items()}
            if how in ("auto", "smart"):
                both = "arrive" in tangents and "leave" in tangents
                how = "break" if both and abs(tangents["arrive"] - tangents["leave"]) > 1e-9 else "user"
        key = [snap(float(f)), v, how] + ([tangents] if tangents else [])
        out.append(key)
    if sort:
        out.sort(key=lambda k: k[0])  # stable: equal frames keep their order, so the later one wins below
    if dedupe:
        uniq: list = []
        for k in out:
            if uniq and uniq[-1][0] == k[0]:
                uniq[-1] = k
            else:
                uniq.append(k)
        out = uniq
    return out


# --- prediction: what a channel will read at a frame ------------------------------------------------------------------

def _auto_slopes(keys: list) -> list:
    """Approximate slopes at each key for auto/smart tangents: Catmull-Rom (centred difference), flat at the first and
    last key and at local extremes (Sequencer clamps auto tangents so curves do not overshoot)."""
    n = len(keys)
    s = [0.0] * n
    for i in range(n):
        k = keys[i]
        if len(k) > 3 and k[3]:
            continue
        if 0 < i < n - 1:
            (f0, v0), (f1, v1), (f2, v2) = (keys[i - 1][:2]), (k[:2]), (keys[i + 1][:2])
            if (v1 - v0) * (v2 - v1) <= 0:
                s[i] = 0.0  # an extreme or a flat: clamped
            else:
                s[i] = (v2 - v0) / (f2 - f0) if f2 != f0 else 0.0
    return s


def evaluate(keys: list, frame: float, default=None):
    """The value a channel with canonical `keys` gives at `frame` (display frames): held before the first key and
    after the last (constant extrapolation, Sequencer's default), stepped after a "constant" key, straight after a
    "linear" one, cubic Hermite otherwise (auto tangents approximated, user tangents exact for unweighted keys).
    Non-numeric values (bool, int, str) always step. No keys: `default`. For checks and planning; the engine's own
    evaluation (seq.eval) is the truth."""
    if not keys:
        return default
    if frame <= keys[0][0]:
        return keys[0][1]
    if frame >= keys[-1][0]:
        return keys[-1][1]
    lo, hi = 0, len(keys) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if keys[mid][0] <= frame:
            lo = mid
        else:
            hi = mid
    a, b = keys[lo], keys[hi]
    if isinstance(a[1], (bool, str)) or not isinstance(a[1], (int, float)) or isinstance(b[1], (bool, str)):
        return a[1]
    how = a[2] if len(a) > 2 else "auto"
    if how == "constant":
        return a[1]
    u = (frame - a[0]) / (b[0] - a[0])
    if how == "linear":
        return a[1] + (b[1] - a[1]) * u
    slopes = _auto_slopes(keys)
    m0 = (a[3].get("leave", slopes[lo]) if len(a) > 3 and a[3] else slopes[lo])
    m1 = (b[3].get("arrive", slopes[hi]) if len(b) > 3 and b[3] else slopes[hi])
    if (b[2] if len(b) > 2 else "auto") in ("constant", "linear") and not (len(b) > 3 and b[3]):
        # the key we arrive at is not cubic: Sequencer still eases into it with its auto slope
        pass
    dt = b[0] - a[0]
    u2, u3 = u * u, u * u * u
    return ((2 * u3 - 3 * u2 + 1) * a[1] + (u3 - 2 * u2 + u) * dt * m0 + (-2 * u3 + 3 * u2) * b[1]
            + (u3 - u2) * dt * m1)


def sample(keys: list, frames: Iterable[float], default=None) -> list:
    return [evaluate(keys, f, default) for f in frames]


# --- angles, look-at ---------------------------------------------------------------------------------------------------

def unwrap(angles: list, start: float | None = None) -> list:
    """Degrees made continuous: each angle moved by whole turns to within 180 of the one before (a yaw keyed 170 then
    -170 turns 20 degrees, not 340). `start`: the angle the first one should be nearest to."""
    out = []
    prev = start
    for a in angles:
        a = float(a)
        if prev is not None:
            a -= 360.0 * round((a - prev) / 360.0)
        out.append(a)
        prev = a
    return out


def look_at(src, dst) -> dict:
    """The rotation {"pitch", "yaw", "roll"} (degrees) that points an actor's X axis from `src` at `dst` (world cm,
    Z up), roll 0: what cameras and lights want."""
    dx, dy, dz = (float(b) - float(a) for a, b in zip(src, dst))
    if abs(dx) < 1e-9 and abs(dy) < 1e-9 and abs(dz) < 1e-9:
        raise ValueError(f"look_at: the target {list(dst)} is the location itself")
    return {"pitch": math.degrees(math.atan2(dz, math.hypot(dx, dy))), "yaw": math.degrees(math.atan2(dy, dx)),
            "roll": 0.0}


# --- reduction of dense keys -------------------------------------------------------------------------------------------

def reduce(samples: list, tol: float, interp: str = "linear") -> list:
    """Dense samples [[frame, value], ...] (a bake, one per frame) reduced to the fewest keys whose straight-line
    interpolation stays within `tol` of every sample (Ramer-Douglas-Peucker on the value axis). Returns canonical
    keys with `interp` ("linear": exact within tol; "auto" smooths, and may then deviate a little more). The first
    and last samples are always kept."""
    pts = [(float(s[0]), float(s[1])) for s in samples]
    if len(pts) <= 2:
        return [[_snapf(f), v, interp] for f, v in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        (f0, v0), (f1, v1) = pts[i], pts[j]
        worst, at = -1.0, -1
        for k in range(i + 1, j):
            f, v = pts[k]
            pred = v0 + (v1 - v0) * (f - f0) / (f1 - f0) if f1 != f0 else v0
            d = abs(v - pred)
            if d > worst:
                worst, at = d, k
        if worst > tol and at > 0:
            keep[at] = True
            stack += [(i, at), (at, j)]
    return [[_snapf(f), v, interp] for (f, v), k in zip(pts, keep) if k]


def _snapf(f: float):
    from ._time import snap
    return snap(f)


def keys_equal(a: list, b: list, tol: float = 1e-4) -> bool:
    """Two canonical key lists equal: same frames, same interps, values within `tol` (relative for big values),
    tangents within tol when either gives them."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if abs(float(x[0]) - float(y[0])) > 1e-6 or (x[2] if len(x) > 2 else "auto") != (y[2] if len(y) > 2 else "auto"):
            return False
        if not values_equal(x[1], y[1], tol):
            return False
        tx, ty = (x[3] if len(x) > 3 else None) or {}, (y[3] if len(y) > 3 else None) or {}
        if tx or ty:
            for n in set(tx) | set(ty):
                if n in tx and n in ty and not values_equal(tx[n], ty[n], tol):
                    return False
    return True


def values_equal(a, b, tol: float = 1e-4) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str) or a is None or b is None:
        return a == b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(values_equal(x, y, tol) for x, y in zip(a, b))
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    return abs(fa - fb) <= tol * max(1.0, abs(fa), abs(fb))


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
