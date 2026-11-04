"""One light, in one canonical form: what `light.add` takes (after normalising), what `light.describe` returns and what
the planner compares. Also the practical-light presets (bulbs, candles, lamps, screens, neon, fire, windows).

Canonical light (every key optional except label/kind/loc):
    label, kind (rect|spot|point|directional), loc [x,y,z] cm, rotation {"pitch","yaw","roll"} deg,
    intensity_cd (rect/spot/point, candelas) | intensity_lux (directional), temperature_k (None = use color),
    color [r,g,b] linear 0-1, width_cm/height_cm (rect), barn_door_deg/barn_door_length_cm (rect),
    cone_deg/inner_cone_deg (spot, outer/inner half-angles), source_radius_cm/soft_radius_cm/source_length_cm
    (point/spot), radius_cm (attenuation), shadows, channels [0..2], ies (a TextureLightProfile path),
    ies_brightness (bool: use the profile's own brightness), specular, volumetric, indirect, diffuse.
"""
from __future__ import annotations

import math

from . import photometry as ph

KINDS = {"rect": "RectLight", "spot": "SpotLight", "point": "PointLight", "directional": "DirectionalLight"}
COMPONENT = {"rect": "RectLightComponent", "spot": "SpotLightComponent", "point": "PointLightComponent",
             "directional": "DirectionalLightComponent"}

# canonical key -> the engine property it sets (on the light component); unit conversions are done by the op
PROPS = {
    "intensity_cd": "intensity", "intensity_lux": "intensity", "temperature_k": "temperature",
    "width_cm": "source_width", "height_cm": "source_height", "barn_door_deg": "barn_door_angle",
    "barn_door_length_cm": "barn_door_length", "cone_deg": "outer_cone_angle", "inner_cone_deg": "inner_cone_angle",
    "source_radius_cm": "source_radius", "soft_radius_cm": "soft_source_radius", "source_length_cm": "source_length",
    "radius_cm": "attenuation_radius", "shadows": "cast_shadows", "specular": "specular_scale",
    "volumetric": "volumetric_scattering_intensity", "indirect": "indirect_lighting_intensity",
    "diffuse": "diffuse_scale", "ies": "ies_texture", "ies_brightness": "use_ies_brightness",
    "softness_deg": "light_source_angle",
}
ONLY = {"width_cm": {"rect"}, "height_cm": {"rect"}, "barn_door_deg": {"rect"}, "barn_door_length_cm": {"rect"},
        "cone_deg": {"spot"}, "inner_cone_deg": {"spot"}, "source_radius_cm": {"point", "spot"},
        "soft_radius_cm": {"point", "spot"}, "source_length_cm": {"point", "spot"},
        "radius_cm": {"rect", "spot", "point"}, "intensity_cd": {"rect", "spot", "point"},
        "intensity_lux": {"directional"}, "softness_deg": {"directional"}}
INPUT = set(PROPS) | {"label", "kind", "loc", "rotation", "look_at", "color", "channels", "lux", "at", "lumens",
                      "nits", "role", "tags"}


def look_rotation(src, target) -> dict:
    """Unreal's FindLookAtRotation (MakeRotFromX of target - src): yaw from atan2(y, x), pitch from the rise, no roll."""
    d = [target[i] - src[i] for i in range(3)]
    yaw = math.degrees(math.atan2(d[1], d[0]))
    pitch = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
    return {"pitch": round(pitch, 4), "yaw": round(yaw, 4), "roll": 0.0}


def forward(rot: dict) -> list:
    """The forward (X) axis of a rotation {"pitch","yaw","roll"}."""
    p, y = math.radians(rot.get("pitch", 0.0)), math.radians(rot.get("yaw", 0.0))
    return [math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)]


def normalize(spec: dict, label: str = None) -> dict:
    """A light spec (friendly: look_at, lux at a point, lumens, nits) to the canonical form. Raises ValueError with
    the fix on anything it cannot use."""
    s = dict(spec)
    if label:
        s.setdefault("label", label)
    bad = set(s) - INPUT
    if bad:
        from difflib import get_close_matches
        near = {b: get_close_matches(b, sorted(INPUT), 1) for b in bad}
        raise ValueError(f"light {s.get('label')!r}: unknown key(s) " + ", ".join(
            f"{b!r}" + (f" (did you mean {near[b][0]!r}?)" if near[b] else "") for b in sorted(bad)))
    kind = s.get("kind", "rect")
    if kind not in KINDS:
        raise ValueError(f"light {s.get('label')!r}: kind {kind!r} is not one of {sorted(KINDS)}")
    out = {"label": s["label"], "kind": kind, "loc": [float(v) for v in s.get("loc", (0, 0, 200))]}
    if s.get("rotation") is not None:
        r = s["rotation"]
        out["rotation"] = {"pitch": float(r.get("pitch", 0)), "yaw": float(r.get("yaw", 0)), "roll": float(r.get("roll", 0))}
    elif s.get("look_at") is not None:
        out["rotation"] = look_rotation(out["loc"], s["look_at"])
    for k in ("cone_deg", "inner_cone_deg"):
        if k in s:
            out[k] = float(s[k])
    if kind == "spot":
        out.setdefault("cone_deg", 30.0)
        out.setdefault("inner_cone_deg", round(out["cone_deg"] * 0.6, 4))
    # intensity: candelas direct, or lux at a point / at the aim (inverse square), or lumens, or nits x area (rect)
    if kind == "directional":
        out["intensity_lux"] = float(s.get("intensity_lux", s.get("lux", 10.0)))
    elif "intensity_cd" in s:
        out["intensity_cd"] = float(s["intensity_cd"])
    elif "lux" in s:
        at = s.get("at", s.get("look_at"))
        if at is None:
            raise ValueError(f"light {out['label']!r}: lux needs `at` (or look_at): the point that gets that lux")
        out["intensity_cd"] = round(ph.candelas_for_lux(float(s["lux"]), math.dist(out["loc"], at)), 4)
    elif "lumens" in s:
        out["intensity_cd"] = round(ph.lumens_to_candelas(float(s["lumens"]), kind, out.get("cone_deg", 44.0)), 4)
    elif "nits" in s:
        if kind != "rect":
            raise ValueError(f"light {out['label']!r}: nits (surface luminance) needs a rect light")
        area = float(s.get("width_cm", 100)) * float(s.get("height_cm", 100)) / 1e4
        out["intensity_cd"] = round(float(s["nits"]) * area, 4)
    else:
        out["intensity_cd"] = 10.0
    if s.get("color") is not None:
        out["color"] = ph.quantize_fcolor(s["color"])  # LightColor is an FColor (8-bit sRGB)
        out["temperature_k"] = None
    else:
        out["temperature_k"] = float(s.get("temperature_k", 6500.0))
    for k in PROPS:
        if k in s and k not in out and k not in ("intensity_cd", "intensity_lux", "temperature_k"):
            if kind not in ONLY.get(k, {kind}):
                raise ValueError(f"light {out['label']!r}: {k} does not apply to a {kind} light")
            v = s[k]
            out[k] = v if isinstance(v, (bool, str)) or v is None else float(v)
    if s.get("channels") is not None:
        ch = sorted({int(c) for c in s["channels"]})
        if any(c not in (0, 1, 2) for c in ch):
            raise ValueError(f"light {out['label']!r}: lighting channels are 0, 1, 2; got {ch}")
        out["channels"] = ch
    if kind != "directional" and "radius_cm" not in out:
        out["radius_cm"] = auto_radius(out["intensity_cd"])
    return out


def auto_radius(cd: float, floor_lux: float = 0.05) -> float:
    """An attenuation radius (cm) where the light has fallen to about `floor_lux`: far enough to not cut visibly,
    near enough to keep the light cheap. At least 500 cm, at most 20000."""
    r = 100.0 * math.sqrt(max(cd, 0.0) / floor_lux)
    return float(round(min(20000.0, max(500.0, r)), -1))


# ----------------------------------------------------------------------------------------------- practicals

PRACTICALS = {
    # type: kind, lumens (or nits), temperature, size, and what it is
    "bulb": {"about": "a bare 60 W-equivalent bulb (800 lm, 2700 K)", "kind": "point", "lumens": 800.0,
             "temperature_k": 2700.0, "source_radius_cm": 3.0},
    "lamp": {"about": "a shaded table/floor lamp: a dim warm glow (450 lm, 2700 K, soft)", "kind": "point",
             "lumens": 450.0, "temperature_k": 2700.0, "source_radius_cm": 15.0},
    "candle": {"about": "a candle flame (12 lm, 1850 K), short reach", "kind": "point", "lumens": 12.0,
               "temperature_k": 1850.0, "source_radius_cm": 0.8, "radius_cm": 400.0},
    "fire": {"about": "a fireplace or campfire (2000 lm, 1900 K, large)", "kind": "point", "lumens": 2000.0,
             "temperature_k": 1900.0, "source_radius_cm": 30.0},
    "downlight": {"about": "a ceiling downlight pointing down (600 lm, 3000 K, 35 deg)", "kind": "spot",
                  "lumens": 600.0, "temperature_k": 3000.0, "cone_deg": 35.0, "source_radius_cm": 4.0, "aim": "down"},
    "desk_lamp": {"about": "an angled desk lamp (400 lm, 3000 K, 50 deg)", "kind": "spot", "lumens": 400.0,
                  "temperature_k": 3000.0, "cone_deg": 50.0, "source_radius_cm": 5.0},
    "streetlight": {"about": "a sodium-orange street lamp from 6 m (8000 lm, 2100 K, 60 deg)", "kind": "spot",
                    "lumens": 8000.0, "temperature_k": 2100.0, "cone_deg": 60.0, "source_radius_cm": 10.0, "aim": "down"},
    "tube": {"about": "a fluorescent/LED tube (2000 lm, 4000 K, 120 x 4 cm)", "kind": "rect", "lumens": 2000.0,
             "temperature_k": 4000.0, "width_cm": 120.0, "height_cm": 4.0},
    "led_strip": {"about": "a warm LED strip under a shelf (300 lm, 3000 K, 100 x 1 cm)", "kind": "rect", "lumens": 300.0,
                  "temperature_k": 3000.0, "width_cm": 100.0, "height_cm": 1.0, "aim": "down"},
    "neon": {"about": "a neon sign glow (coloured, 150 nits over 80 x 30 cm)", "kind": "rect", "nits": 150.0,
             "color": [1.0, 0.1, 0.4], "width_cm": 80.0, "height_cm": 30.0},
    "screen": {"about": "a monitor or TV face (200 nits, 6500 K, 60 x 34 cm)", "kind": "rect", "nits": 200.0,
               "temperature_k": 6500.0, "width_cm": 60.0, "height_cm": 34.0, "shadows": False},
    "phone": {"about": "a phone screen lighting a face (400 nits, 6500 K, 7 x 15 cm)", "kind": "rect", "nits": 400.0,
              "temperature_k": 6500.0, "width_cm": 7.0, "height_cm": 15.0, "shadows": False},
    "window": {"about": "daylight through a window as an area light (2000 nits, 6500 K, 120 x 150 cm)", "kind": "rect",
               "nits": 2000.0, "temperature_k": 6500.0, "width_cm": 120.0, "height_cm": 150.0},
}


def practical(spec: dict, label: str = None) -> dict:
    """A practical spec {type, loc, look_at?, ...overrides} to a canonical light (normalize). `aim: down` (the
    preset's or the spec's) points it straight down; `scale` multiplies its output."""
    s = dict(spec)
    t = s.pop("type", None)
    if t not in PRACTICALS:
        raise ValueError(f"practical {label or s.get('label')!r}: type {t!r} is not one of {sorted(PRACTICALS)}")
    base = {k: v for k, v in PRACTICALS[t].items() if k != "about"}
    aim = s.pop("aim", base.pop("aim", None))
    scale = float(s.pop("scale", 1.0))
    merged = {**base, **s}
    if "intensity_cd" in s:  # an explicit intensity wins over the preset's lumens/nits
        merged.pop("lumens", None)
        merged.pop("nits", None)
    if "color" in s:
        merged.pop("temperature_k", None)
    if aim == "down" and "look_at" not in merged and "rotation" not in merged:
        merged["rotation"] = {"pitch": -90.0, "yaw": 0.0, "roll": 0.0}
    out = normalize(merged, label)
    out["intensity_cd"] = round(out["intensity_cd"] * scale, 4)
    if "radius_cm" not in s and "radius_cm" not in PRACTICALS[t]:
        out["radius_cm"] = auto_radius(out["intensity_cd"])
    return out


def differs(want: dict, have: dict, tol: float = 1e-3) -> list:
    """The canonical keys of `want` whose value differs from `have` (numbers within a relative/absolute tolerance)."""
    def same(a, b):
        if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
            return a == b
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(a - b) <= tol * max(1.0, abs(a), abs(b))
        if isinstance(a, dict) and isinstance(b, dict):
            return all(same(a.get(k), b.get(k)) for k in set(a) | set(b))
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
        return a == b
    out = []
    for k, v in want.items():
        if k in ("label", "role", "tags"):
            continue
        if k == "rotation" and k in have and have[k] is not None:
            if not same_rotation(v, have[k], tol * 100):
                out.append(k)
            continue
        if not same(v, have.get(k)):
            out.append(k)
    return out


def same_rotation(a: dict, b: dict, tol_deg: float = 0.05) -> bool:
    """Two rotations aim the same way (forward vectors within `tol_deg`) and roll alike: yaw 180 == yaw -180."""
    fa, fb = forward(a), forward(b)
    c = max(-1.0, min(1.0, sum(x * y for x, y in zip(fa, fb))))
    return math.degrees(math.acos(c)) <= tol_deg and abs(((a.get("roll", 0) - b.get("roll", 0)) + 180) % 360 - 180) <= tol_deg
