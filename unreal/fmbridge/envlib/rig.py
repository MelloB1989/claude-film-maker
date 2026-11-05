"""Lighting rigs by spec: key, fill, rim, hair, kicker, eye and background lights placed relative to a subject and a
camera, with intensities set from a target illuminance on the subject and lighting ratios rather than raw numbers.

Geometry. The reference axis runs from the subject towards the camera (or along the subject's facing when there is no
camera). A light's `angle` is measured around the subject from that axis: 0 at the camera, 90 at the subject's side,
180 behind. `side` is as seen from the camera: "left" (camera-left) or "right"; "center" means angle 0/180 exactly.
`elevation` is degrees above the subject point, `distance` cm from it. Every light aims at the subject point (plus
`aim_offset`). Unreal is left-handed with Z up: seen from above, yaw grows clockwise, so for an axis of yaw A the
camera's left is yaw A + 90.

Intensity. `lux` is the illuminance the light alone gives at the subject point on a surface facing the light (what an
incident meter pointed at the light reads); its candelas follow from the inverse-square law (photometry.candelas_for_lux).
The key's lux is the rig's `key_lux`; the fill comes from the lighting `ratio` (key+fill : fill, so a ratio of 2 is flat,
4 is dramatic, 8 is noir: fill = key / (ratio - 1)); rims and the rest are multiples of the key (`rel`).
"""
from __future__ import annotations

import copy
import math

from . import photometry as ph

# role defaults: where it stands, how big and soft, what colour, how bright relative to the key
ROLE = {
    "key": {"kind": "rect", "angle": 45.0, "side": "key", "elevation": 30.0, "distance": 220.0, "width": 120.0,
            "height": 120.0, "temperature": 5600.0, "rel": 1.0},
    "fill": {"kind": "rect", "angle": 40.0, "side": "opposite", "elevation": 10.0, "distance": 260.0, "width": 180.0,
             "height": 180.0, "temperature": 5600.0},
    "rim": {"kind": "rect", "angle": 140.0, "side": "opposite", "elevation": 30.0, "distance": 200.0, "width": 30.0,
            "height": 120.0, "temperature": 5600.0, "rel": 1.2},
    "rim2": {"kind": "rect", "angle": 140.0, "side": "key", "elevation": 30.0, "distance": 200.0, "width": 30.0,
             "height": 120.0, "temperature": 5600.0, "rel": 0.8},
    "hair": {"kind": "rect", "angle": 175.0, "side": "key", "elevation": 60.0, "distance": 180.0, "width": 60.0,
             "height": 40.0, "temperature": 5000.0, "rel": 0.8, "aim_offset": [0, 0, 15]},
    "kicker": {"kind": "rect", "angle": 115.0, "side": "key", "elevation": 10.0, "distance": 220.0, "width": 30.0,
               "height": 150.0, "temperature": 5600.0, "rel": 0.6},
    "eye": {"kind": "rect", "angle": 0.0, "side": "center", "elevation": 2.0, "distance": 180.0, "width": 25.0,
            "height": 25.0, "temperature": 5600.0, "rel": 0.05, "shadows": False},
    "background": {"kind": "spot", "angle": 180.0, "side": "center", "elevation": 25.0, "distance": 250.0, "cone": 40.0,
                   "temperature": 5600.0, "rel": 0.5, "aim_offset": [0, 0, 0], "aim": "behind", "behind": 150.0},
}

# named rigs: the roles they use and how they differ from the role defaults; `ratio` sets the fill
PRESETS = {
    "three_point": {"about": "the classic: a soft key 45 deg off camera, a fill on the other side at 3:1, a rim behind",
                    "ratio": 3.0, "lights": {"key": {}, "fill": {}, "rim": {}}},
    "interview": {"about": "talking head: soft key, gentle 2.5:1 fill, hair light and an eye light for catchlights",
                  "ratio": 2.5, "lights": {"key": {"angle": 40.0}, "fill": {}, "hair": {}, "eye": {}}},
    "loop": {"about": "key 35 deg off and 35 up: a small nose shadow looping towards the cheek, 3:1",
             "ratio": 3.0, "lights": {"key": {"angle": 35.0, "elevation": 35.0}, "fill": {}, "rim": {"rel": 0.9}}},
    "rembrandt": {"about": "key 55 deg off and 45 up: a lit triangle on the shadow cheek, moody 4:1",
                  "ratio": 4.0, "lights": {"key": {"angle": 55.0, "elevation": 45.0}, "fill": {"elevation": 5.0},
                                           "rim": {"rel": 0.7}}},
    "butterfly": {"about": "paramount: key straight on and high, a butterfly shadow under the nose, fill from below",
                  "ratio": 3.0, "lights": {"key": {"angle": 0.0, "side": "center", "elevation": 45.0},
                                           "fill": {"angle": 0.0, "side": "center", "elevation": -20.0, "distance": 150.0,
                                                    "width": 120.0, "height": 40.0},
                                           "hair": {}}},
    "clamshell": {"about": "beauty: key above and fill below the lens, both soft, nearly shadowless (2:1)",
                  "ratio": 2.0, "lights": {"key": {"angle": 0.0, "side": "center", "elevation": 35.0, "width": 150.0,
                                                   "height": 80.0},
                                           "fill": {"angle": 0.0, "side": "center", "elevation": -25.0, "distance": 150.0,
                                                    "width": 150.0, "height": 50.0},
                                           "rim": {"rel": 0.8}, "rim2": {"rel": 0.8}}},
    "split": {"about": "key at 90 deg: half the face lit, half dark; no fill", "ratio": None,
              "lights": {"key": {"angle": 90.0, "elevation": 10.0}, "rim": {"rel": 0.5}}},
    "high_key": {"about": "bright and even: a big frontal key, 1.5:1 fill, background lit to white",
                 "ratio": 1.5, "lights": {"key": {"angle": 25.0, "width": 200.0, "height": 200.0}, "fill": {"angle": 30.0},
                                          "rim": {"rel": 0.6}, "background": {"rel": 1.2}}},
    "low_key": {"about": "dark and dramatic: a hard side key at 8:1 and a strong rim, little else",
                "ratio": 8.0, "lights": {"key": {"kind": "spot", "angle": 70.0, "elevation": 35.0, "cone": 25.0},
                                         "fill": {"width": 240.0, "height": 240.0}, "rim": {"rel": 1.8}}},
    "noir": {"about": "hard spot key high and to the side through the dark, no fill, a cold rim",
             "ratio": None, "lights": {"key": {"kind": "spot", "angle": 60.0, "elevation": 50.0, "cone": 20.0,
                                               "temperature": 4300.0},
                                       "rim": {"rel": 1.5, "temperature": 7500.0}}},
    "silhouette": {"about": "the subject dark against a lit background, edged by two rims", "ratio": None,
                   "lights": {"rim": {"rel": 1.0}, "rim2": {"rel": 1.0}, "background": {"rel": 4.0}}},
    "window": {"about": "one big soft source from the side like a window, a bounce fill at 3:1",
               "ratio": 3.0, "lights": {"key": {"angle": 70.0, "elevation": 15.0, "width": 250.0, "height": 250.0,
                                                "distance": 300.0, "temperature": 6000.0},
                                        "fill": {"temperature": 5000.0}}},
}

FIELDS = {"kind", "angle", "side", "elevation", "distance", "width", "height", "cone", "temperature", "color", "rel",
          "lux", "candelas", "aim_offset", "aim", "behind", "shadows", "channels", "label", "barn_angle", "softness",
          "ies", "specular", "volumetric", "enabled"}


def _yaw_of(v) -> float:
    return math.degrees(math.atan2(v[1], v[0]))


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def plan(subject, camera=None, facing: float = None, preset: str = "three_point", key_lux: float = 800.0,
         ratio: float = None, lights: dict = None, prefix: str = "Rig_", key_side: str = "left", scale: float = 1.0,
         temperature: float = None, channels=None, subject_yaw: float = None) -> list:
    """The lights of a rig as a list of light specs (label, kind, loc, look_at, candelas, lux at the subject, size,
    temperature, ...). `subject` is the point to light [x, y, z] (cm: a face, not the feet); `camera` [x, y, z] or
    `facing` (the subject's yaw) sets the reference axis. `lights` overrides or adds roles ({"rim": {"rel": 2}},
    {"fill": None} drops one). `key_side` flips the rig; `scale` multiplies every distance and size; `temperature`
    sets every light's; `channels` puts every light on those lighting channels."""
    if preset not in PRESETS:
        raise ValueError(f"unknown rig preset {preset!r}; one of {sorted(PRESETS)} (light.rig_presets lists them)")
    if key_side not in ("left", "right", "short", "broad"):
        raise ValueError(f"key_side must be left|right (camera-left/right) or short|broad, not {key_side!r}")
    p = PRESETS[preset]
    ratio = p["ratio"] if ratio is None else ratio
    roles = copy.deepcopy(p["lights"])
    for role, over in (lights or {}).items():
        if over is None:
            roles.pop(role, None)
            continue
        bad = set(over) - FIELDS
        if bad:
            raise ValueError(f"rig light {role!r}: unknown field(s) {sorted(bad)}; allowed: {sorted(FIELDS)}")
        roles.setdefault(role, {}).update(over)
    subject = [float(x) for x in subject]
    if camera is not None:
        axis = _yaw_of(_sub(camera, subject))
    elif facing is not None:
        axis = float(facing)
    else:
        raise ValueError("a rig needs the camera position or the subject's facing yaw")
    if key_side in ("short", "broad"):
        key_side = short_broad(key_side, axis, subject_yaw)
    other = "right" if key_side == "left" else "left"
    out = []
    for role, over in roles.items():
        base = ROLE.get(role) or ROLE.get(role.rstrip("0123456789")) or ROLE["kicker"]  # a new role: a kicker-like accent
        s = {**base, **over}
        if s.get("enabled") is False:
            continue
        side = {"key": key_side, "opposite": other}.get(s["side"], s["side"])
        if side not in ("left", "right", "center"):
            raise ValueError(f"rig light {role!r}: side {s['side']!r} is not key/opposite/left/right/center")
        sign = {"left": 1.0, "right": -1.0, "center": 0.0}[side]
        ang = float(s["angle"])
        yaw = axis + (sign * ang if side != "center" else (0.0 if ang < 90 else 180.0))
        el = math.radians(float(s["elevation"]))
        d = float(s["distance"]) * scale
        if s.get("aim") == "behind":  # a background light: stands behind the subject and lights the wall further back
            back = [subject[0] - math.cos(math.radians(axis)) * s.get("behind", 150.0) * scale,
                    subject[1] - math.sin(math.radians(axis)) * s.get("behind", 150.0) * scale, subject[2]]
            loc = [subject[0] - math.cos(math.radians(axis)) * 40 * scale, subject[1] - math.sin(math.radians(axis)) * 40 * scale,
                   subject[2] + d * math.sin(el)]
            target = back
        else:
            loc = [subject[0] + d * math.cos(el) * math.cos(math.radians(yaw)),
                   subject[1] + d * math.cos(el) * math.sin(math.radians(yaw)), subject[2] + d * math.sin(el)]
            off = s.get("aim_offset") or [0, 0, 0]
            target = [subject[0] + off[0], subject[1] + off[1], subject[2] + off[2]]
        dist = math.dist(loc, target)
        if "candelas" in s:
            cd = float(s["candelas"])
            lux = ph.lux_from_candelas(cd, dist)
        else:
            if "lux" in s:
                lux = float(s["lux"])
            elif role == "fill":
                lux = 0.0 if not ratio else key_lux / max(ratio - 1.0, 1e-3)
            else:
                lux = key_lux * float(s.get("rel", 1.0))
            cd = ph.candelas_for_lux(lux, dist)
        spec = {"label": s.get("label") or f"{prefix}{role[0].upper()}{role[1:]}", "role": role, "kind": s["kind"],
                "loc": [round(v, 2) for v in loc], "look_at": [round(v, 2) for v in target],
                "candelas": round(cd, 4), "lux": round(lux, 3), "distance": round(dist, 2),
                "temperature": float(temperature if temperature is not None else s.get("temperature", 5600.0)),
                "shadows": bool(s.get("shadows", True))}
        if s.get("color") is not None:
            spec["color"] = list(s["color"])
        if s["kind"] == "rect":
            spec["width"], spec["height"] = float(s.get("width", 100.0)) * scale, float(s.get("height", 100.0)) * scale
            if s.get("barn_angle") is not None:
                spec["barn_angle"] = float(s["barn_angle"])
        elif s["kind"] == "spot":
            spec["cone"] = float(s.get("cone", 30.0))
        elif s["kind"] == "point" and s.get("softness") is not None:
            spec["source_radius"] = float(s["softness"])
        for k in ("ies", "specular", "volumetric"):
            if s.get(k) is not None:
                spec[k] = s[k]
        ch = s.get("channels", channels)
        if ch is not None:
            spec["channels"] = list(ch)
        out.append(spec)
    return out


def short_broad(kind: str, axis: float, subject_yaw) -> str:
    """Camera-left/right for short or broad lighting. The face turns away from the lens by d = subject_yaw - axis
    (axis: the yaw from the subject to the camera); a positive d turns it towards camera-left. Short lighting keys
    the side of the face turned away from the camera (the side it turns to); broad keys the side facing the lens."""
    if subject_yaw is None:
        raise ValueError("short/broad lighting needs the subject's facing (subject_yaw, or a subject actor) and a camera")
    d = (float(subject_yaw) - axis + 180.0) % 360.0 - 180.0
    turned = "left" if d >= 0 else "right"
    return turned if kind == "short" else ("right" if turned == "left" else "left")


def _dir(a, b):
    v = _sub(b, a)
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def illuminance_at(lights: list, point, normal=None) -> dict:
    """What each light gives at `point` (lux), analytically: inverse square, the cosine on a surface with `normal`
    (or a surface facing each light when None), the spot cone and the attenuation window, no shadows or bounce.
    `lights` are light specs (plan's, or light.describe's: loc, look_at or forward, kind, candelas, cone, radius)."""
    per = {}
    for L in lights:
        if L.get("kind") == "directional":
            lux = float(L.get("lux", L.get("intensity", 0.0)))
            if normal is not None:
                lux *= max(0.0, -sum(a * b for a, b in zip(L["forward"], normal)))
            per[L["label"]] = round(lux, 4)
            continue
        loc = L["loc"]
        to_p = _dir(loc, point)
        d = math.dist(loc, point)
        cd = float(L.get("candelas", 0.0))
        e = cd / max((d / 100.0) ** 2, 1e-6)
        fwd = L.get("forward") or (_dir(loc, L["look_at"]) if L.get("look_at") else None)
        if L.get("kind") == "spot" and fwd:
            off = math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(fwd, to_p))))))
            outer = float(L.get("cone", 30.0))
            e *= ph.spot_falloff(off, float(L.get("inner_cone", outer * 0.6)), outer)
        elif L.get("kind") == "rect" and fwd:
            c = sum(a * b for a, b in zip(fwd, to_p))  # a rect light emits forward only, Lambertian
            e *= max(0.0, c)
        if normal is not None:
            e *= max(0.0, -sum(a * b for a, b in zip(to_p, normal)))
        if L.get("radius"):
            e *= ph.inverse_square_falloff(d, float(L["radius"]))
        per[L["label"]] = round(e, 4)
    total = sum(per.values())
    return {"lux": round(total, 4), "per_light": per, "ev100": round(ph.ev100_from_illuminance(total), 3) if total > 0 else None}


def ratio_of(lights: list, point, key: str, fill: str) -> float:
    """The lighting ratio (key + fill) : fill measured at `point` from two of the lights."""
    per = illuminance_at(lights, point)["per_light"]
    f = per.get(fill, 0.0)
    return float("inf") if f <= 0 else round((per.get(key, 0.0) + f) / f, 4)


def to_lights(planned: list) -> list:
    """plan()'s light specs as canonical lights (envlib.lights.normalize), each keeping its role."""
    from . import lights as lights_lib
    out = []
    for p in planned:
        s = {"label": p["label"], "kind": p["kind"], "loc": p["loc"], "look_at": p["look_at"],
             "intensity_cd": p["candelas"], "shadows": p.get("shadows", True)}
        if p.get("color") is not None:
            s["color"] = p["color"]
        else:
            s["temperature_k"] = p.get("temperature", 5600.0)
        for a, b in (("width", "width_cm"), ("height", "height_cm"), ("cone", "cone_deg"), ("barn_angle", "barn_door_deg"),
                     ("source_radius", "source_radius_cm"), ("ies", "ies"), ("specular", "specular"),
                     ("volumetric", "volumetric"), ("channels", "channels")):
            if p.get(a) is not None:
                s[b] = p[a]
        L = lights_lib.normalize(s)
        L["role"] = p["role"]
        out.append(L)
    return out


# light.rig's argument defaults (a test checks they match the op's signature): the planner fills them in on both
# sides before comparing a spec's rig with the one recorded on the level
RIG_DEFAULTS = {"camera": None, "facing_yaw_deg": None, "preset": "three_point", "key_lux": 800.0, "ratio": None,
                "lights": None, "key_side": "left", "scale": 1.0, "temperature_k": None, "channels": None,
                "subject_offset": None, "socket": ""}


def comparable(args: dict) -> dict:
    """Rig arguments with the defaults filled in and the empty ones dropped (numbers as floats)."""
    out = {}
    for k, v in {**RIG_DEFAULTS, **(args or {})}.items():
        if v is None or v == "" or k == "owner":
            continue
        out[k] = float(v) if isinstance(v, int) and not isinstance(v, bool) else v
    return out
