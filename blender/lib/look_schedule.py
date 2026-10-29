"""The look schedule: one file that gives every shot of a film its place on the film's colour arc, its light, its
satsuei, its rain and its mist, so shots built by different hands grade as one film. bpy-free.

films/<id>/data/look.json (paths: lib/film.py):
  {
    "arc": {"cold": {<sections>}, "warm": {<sections>}},  the two ends of the colour arc
    "base": {<sections>},                                  what every shot starts from, before the arc (optional)
    "shots": {"<scene id>": {"warm": W, "lightning": [s, ...], <sections>}, ...}
  }
A shot's `warm` (0 cold .. 1 warm, default 0) blends the arc's two ends; its own sections then override the blend, field
by field. The sections, every field optional (the dataclasses below give the defaults):
  grade    the engine's post over the shot (app post.ts PostParams, by its names): exposure, saturation, contrast,
           warmth, tint, lift, bloom, halation, vignette, grain. The ENGINE applies it, over the plate (film.ts reads
           this file): a shot builder never bakes it into its plate.
  light    the world's light, for the shot builder: key, key_strength, sky, fog, ambient, rim (the sky's rim), accent
           (the vermilion: Shinza's headband, the lantern), warm (the gold of the sun after the rain)
  satsuei  the compositor's base Look for the cast (lib/satsuei.py): gain, saturation, haze, haze_amount, para,
           para_amount, wrap, wrap_width. Rims, the para's direction and the flash belong to a setup: the shot adds them
  rain     density (1 is the film's full rain, 0 none), count (at density 1), speed (m/s; keyed toward 0 it slows to a
           stop), wind, length, width, alpha, color. A number alone is the density
  mist     density (0..1), color (default: the light's fog)
`lightning` lists the times (s into the shot) a strike lands, for the shot (toon.lightning) and the sound to share.

Values: a number, a colour, or keys over the shot. A colour is "#rrggbb" (sRGB, as a palette is written) or [r, g, b]
(linear); this module hands every colour back linear. Keys are [[s, value], ...], s from the shot's start, eased
in-out-sine between keys and held before the first and after the last: exactly the engine's PostKeys (trackAt), so a
grade keyed here moves in Blender and in the engine on the same frames. `warm` can be keyed too ([[0, 0], [5.5, 0.4]]:
the board, as the rain stops).

    from lib import look_schedule
    sched = look_schedule.load(film)            # an empty schedule (every default) when the film has no look.json
    shot = sched.shot("board")                  # ShotLook; ctx.look in a shot's build() (render.py)
    s = shot.at(2.0)                            # State at 2 s into the shot: s.warm, s.grade, s.light, s.satsuei, ...
    s = ctx.look_at(f)                          # the same at film frame f
    comp.key(f, s.look(rims=(...), para_from=(0.5, 1), para_to=(0.5, 0)))   # satsuei.Look, the shot's own on top
    toon.rain(..., count=s.rain.count, speed=s.rain.speed, alpha=s.rain.alpha)
    shot.keyed("rain.density")                  # does it change over the shot (key it per frame, or set it once)
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields, replace
from pathlib import Path

from .theme import hex_to_linear

SECTIONS = ("grade", "light", "satsuei", "rain", "mist")
SHOT_KEYS = {"warm", "lightning", *SECTIONS}


@dataclass(frozen=True)
class Grade:
    """The engine's post over the shot (app/src/engine/post.ts PostParams); the default changes nothing."""
    exposure: float = 1.0
    saturation: float = 1.0
    contrast: float = 1.0
    warmth: float = 0.0
    tint: float = 0.0
    lift: float = 0.0
    bloom: float = 0.3
    halation: float = 0.12
    vignette: float = 0.42
    grain: float = 0.06

    def post(self) -> dict:
        """As the engine's post parameters."""
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class Light:
    """The world's light (linear colours)."""
    key: tuple = (1.0, 1.0, 1.0)
    key_strength: float = 1.0
    sky: tuple = (0.5, 0.5, 0.5)
    fog: tuple = (0.5, 0.5, 0.5)
    ambient: tuple = (0.03, 0.03, 0.03)
    rim: tuple = (0.6, 0.68, 0.85)
    accent: tuple = (0.578, 0.051, 0.027)  # #c8402e
    warm: tuple = (0.694, 0.371, 0.069)    # #d9a44a


@dataclass(frozen=True)
class Satsuei:
    """The compositor's base look for the cast (lib/satsuei.py Look's fields that are the scene's, not a setup's).
    `haze` None is the light's fog."""
    gain: tuple = (1.0, 1.0, 1.0)
    saturation: float = 1.0
    haze: tuple | None = None
    haze_amount: float = 0.0
    para: tuple = (0.45, 0.47, 0.6)
    para_amount: float = 0.0
    wrap: float = 0.0
    wrap_width: float = 0.02


@dataclass(frozen=True)
class Rain:
    """The rain at an instant: `count` drops at density 1, `drops` at this density."""
    density: float = 1.0
    count: int = 5200
    speed: float = 9.5
    wind: float = 1.8
    length: float = 0.34
    width: float = 0.0055
    alpha: float = 0.3
    color: tuple = (0.78, 0.81, 0.86)

    @property
    def drops(self) -> int:
        """How many drops fall at this density."""
        return max(0, round(self.count * max(self.density, 0.0)))

    @property
    def falling(self) -> bool:
        return self.drops > 0 and self.alpha > 0


@dataclass(frozen=True)
class Mist:
    density: float = 0.5
    color: tuple | None = None   # None: the light's fog


_TYPES = {"grade": Grade, "light": Light, "satsuei": Satsuei, "rain": Rain, "mist": Mist}
_COLORS = {("light", f.name) for f in fields(Light) if f.name != "key_strength"} | {
    ("satsuei", "gain"), ("satsuei", "haze"), ("satsuei", "para"), ("rain", "color"), ("mist", "color")}
_INTS = {("rain", "count")}


@dataclass(frozen=True)
class State:
    """A shot's look at an instant."""
    warm: float
    grade: Grade
    light: Light
    satsuei: Satsuei
    rain: Rain
    mist: Mist

    def look(self, **setup):
        """The satsuei.Look for the cast: this state's base, with a setup's own (rims, para_from, para_to, flash, ...)
        on top. Any base field can be overridden too."""
        from .satsuei import Look

        base = {f.name: getattr(self.satsuei, f.name) for f in fields(Satsuei)}
        if base["haze"] is None:
            base["haze"] = self.light.fog
        base.update(setup)
        if "rims" in base:
            base["rims"] = tuple(base["rims"])
        return Look(**base)

    @property
    def mist_color(self) -> tuple:
        return self.mist.color if self.mist.color is not None else self.light.fog


# ---------------------------------------------------------------------------------------------------- values

def ease(x: float) -> float:
    """In-out sine (the engine's PostKeys easing)."""
    return 0.5 - 0.5 * math.cos(math.pi * x)


def is_keys(v) -> bool:
    """[[s, value], ...]: a list of pairs whose first is a time (a colour [r, g, b] is a list of numbers)."""
    return (isinstance(v, list) and len(v) > 0 and all(
        isinstance(k, (list, tuple)) and len(k) == 2 and isinstance(k[0], (int, float)) and not isinstance(k[0], bool)
        for k in v))


def _lerp(a, b, x: float):
    if isinstance(a, tuple):
        return tuple(p + (q - p) * x for p, q in zip(a, b))
    return a + (b - a) * x


def keys_at(keys, t: float):
    """The value of `keys` at t: eased between keys, held outside them (engine postkeys.ts trackAt)."""
    k = sorted(keys, key=lambda p: p[0])
    if t <= k[0][0]:
        return k[0][1]
    for (t0, v0), (t1, v1) in zip(k, k[1:]):
        if t < t1:
            return _lerp(v0, v1, ease((t - t0) / max(1e-9, t1 - t0)))
    return k[-1][1]


def _value(where: str, section: str, name: str, v):
    """A field's value as this module hands it back (a colour linear, a tuple), or keys of them. Raises ValueError."""
    if is_keys(v):
        return [(float(t), _value(where, section, name, x)) for t, x in v]
    if (section, name) in _COLORS:
        if v is None and name in ("haze", "color"):
            return None
        if isinstance(v, str):
            try:
                return tuple(hex_to_linear(v))
            except Exception as e:
                raise ValueError(f"{where}: {section}.{name} {v!r} is not a colour (#rrggbb)") from e
        if isinstance(v, (list, tuple)) and len(v) == 3 and all(isinstance(c, (int, float)) for c in v):
            return tuple(float(c) for c in v)
        raise ValueError(f"{where}: {section}.{name} {v!r} is not a colour (\"#rrggbb\" or linear [r, g, b])")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{where}: {section}.{name} {v!r} is not a number")
    return float(v)


def _section(where: str, section: str, d) -> dict:
    """A section of look.json checked and converted: {field: value or keys}."""
    if section == "rain" and not isinstance(d, dict):
        d = {"density": d}  # a number (or keys) alone is the density
    if not isinstance(d, dict):
        raise ValueError(f"{where}: {section} is an object of fields")
    names = {f.name for f in fields(_TYPES[section])}
    unknown = sorted(set(d) - names)
    if unknown:
        raise ValueError(f"{where}: {section} has no field {', '.join(unknown)} (fields: {', '.join(sorted(names))})")
    return {k: _value(where, section, k, v) for k, v in d.items()}


def _sections(where: str, d: dict, allowed=SECTIONS) -> dict:
    if not isinstance(d, dict):
        raise ValueError(f"{where} is an object")
    unknown = sorted(set(d) - set(allowed))
    if unknown:
        raise ValueError(f"{where} has no {', '.join(unknown)} (it has: {', '.join(sorted(allowed))})")
    return {s: _section(where, s, v) for s, v in d.items() if s in SECTIONS}


# ---------------------------------------------------------------------------------------------------- the schedule

class ShotLook:
    """One shot's look over its time (s from the shot's start). `start` is the shot's start in film time, or None."""

    def __init__(self, scene: str, arc: dict, base: dict, own: dict, start: float | None = None):
        self.scene, self.start = scene, start
        self._arc, self._base = arc, base
        self._warm = own.get("warm", 0.0)
        self._own = {s: v for s, v in own.items() if s in SECTIONS}
        self.lightning = tuple(own.get("lightning", ()))

    def __repr__(self) -> str:
        return f"ShotLook({self.scene!r})"

    def warm(self, t: float) -> float:
        w = keys_at(self._warm, t) if is_keys(self._warm) else self._warm
        return min(max(float(w), 0.0), 1.0)

    def keyed(self, path: str = "") -> bool:
        """Whether the look changes over the shot: anything at all (""), a section ("rain") or a field
        ("rain.density"). A keyed `warm` moves every field the arc's ends disagree on."""
        section, _, name = path.partition(".")

        def moves(d: dict) -> bool:
            for s, flds in d.items():
                if section and s != section:
                    continue
                for n, v in flds.items():
                    if (not name or n == name) and is_keys(v):
                        return True
            return False

        if path in ("", "warm") and is_keys(self._warm):
            return True
        if is_keys(self._warm) and path != "warm":
            cold, warm = self._arc.get("cold", {}), self._arc.get("warm", {})
            for s in SECTIONS:
                if section and s != section:
                    continue
                c, w = cold.get(s, {}), warm.get(s, {})
                if any((not name or n == name) and n in c and n in w and c[n] != w[n] for n in set(c) | set(w)):
                    return True
        return moves(self._base) or moves(self._own) or moves(self._arc.get("cold", {})) or moves(self._arc.get("warm", {}))

    def at(self, t: float) -> State:
        """The look at t s into the shot."""
        w = self.warm(t)
        cold, warm = self._arc.get("cold", {}), self._arc.get("warm", {})

        def val(v):
            return keys_at(v, t) if is_keys(v) else v

        out = {}
        for s, typ in _TYPES.items():
            vals: dict = {}
            for layer in (self._base.get(s, {}),):
                vals.update({n: val(v) for n, v in layer.items()})
            c, h = cold.get(s, {}), warm.get(s, {})
            for n in set(c) | set(h):
                a, b = val(c.get(n, h.get(n))), val(h.get(n, c.get(n)))
                vals[n] = b if a is None or b is None else _lerp(a, b, w)
            vals.update({n: val(v) for n, v in self._own.get(s, {}).items()})
            for n in [n for n in vals if (s, n) in _INTS]:
                vals[n] = round(vals[n])
            out[s] = replace(typ(), **vals)
        return State(warm=w, **out)

    def at_film(self, t: float) -> State:
        """The look at film time t (needs `start`)."""
        if self.start is None:
            raise ValueError(f"{self.scene}: the shot's start is not known (no scene window in the timeline)")
        return self.at(t - self.start)


class Schedule:
    """A film's look schedule (look.json, checked). `shot(scene)` is a scene's ShotLook; a scene the file does not name
    gets the base and the arc's cold end."""

    def __init__(self, data: dict | None = None, where: str = "look.json", starts: dict | None = None):
        data = data or {}
        if not isinstance(data, dict):
            raise ValueError(f"{where}: the look schedule is an object")
        unknown = sorted(set(data) - {"arc", "base", "shots"} - {k for k in data if k.startswith("//")})
        if unknown:
            raise ValueError(f"{where}: no {', '.join(unknown)} (it has arc, base and shots)")
        arc = data.get("arc", {})
        if not isinstance(arc, dict) or set(arc) - {"cold", "warm"}:
            raise ValueError(f"{where}: arc has two ends, cold and warm")
        self.where = where
        self.arc = {end: _sections(f"{where} arc.{end}", v) for end, v in arc.items()}
        self.base = _sections(f"{where} base", data.get("base", {}))
        self.shots: dict[str, dict] = {}
        for sid, d in (data.get("shots") or {}).items():
            w = f"{where} shots.{sid}"
            if not isinstance(d, dict):
                raise ValueError(f"{w} is an object")
            unknown = sorted(set(d) - SHOT_KEYS - {k for k in d if k.startswith("//")})
            if unknown:
                raise ValueError(f"{w} has no {', '.join(unknown)} (it has: {', '.join(sorted(SHOT_KEYS))})")
            own = _sections(w, {k: v for k, v in d.items() if k in SECTIONS})
            if "warm" in d:
                own["warm"] = _value(w, "shot", "warm", d["warm"])
            if "lightning" in d:
                ts = d["lightning"]
                if not isinstance(ts, list) or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in ts):
                    raise ValueError(f"{w}: lightning lists times (s into the shot)")
                own["lightning"] = [float(x) for x in ts]
            self.shots[sid] = own
        self.starts = dict(starts or {})

    def shot(self, scene: str) -> ShotLook:
        return ShotLook(scene, self.arc, self.base, self.shots.get(scene, {}), self.starts.get(scene))

    def check(self, scenes) -> list[str]:
        """Problems against the film's scene ids: a shot here that is not a scene, a scene with no entry."""
        scenes = list(scenes)
        out = [f"{self.where}: shots.{s} is not a scene of the film" for s in self.shots if s not in scenes]
        out += [f"{self.where}: scene {s} has no entry (it gets the base and the cold end)" for s in scenes
                if s not in self.shots]
        return out


def path(film) -> Path:
    """Where a film's look schedule is: films/<id>/data/look.json."""
    return film.root / "data" / "look.json"


def load(film, timeline: dict | None = None) -> Schedule:
    """The film's look schedule (an empty one, every default, when it has no look.json), each shot's start taken from
    `timeline` (data/timeline.json's content; read from the film when not given, when it exists)."""
    p = path(film)
    data = json.loads(p.read_text()) if p.exists() else {}
    if timeline is None:
        tp = film.root / "data" / "timeline.json"
        timeline = json.loads(tp.read_text()) if tp.exists() else {}
    starts = {s["id"]: float(s["start"]) for s in timeline.get("scenes", []) if "id" in s and "start" in s}
    return Schedule(data, str(p.relative_to(film.repo)) if p.is_relative_to(film.repo) else str(p), starts)
