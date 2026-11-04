"""The ENVIRONMENT and LIGHTING specs: validation, presets, moods, and the planner that turns a spec plus the level's
current state (`env.describe`) into the op calls that converge the level to it.

A spec is one JSON/YAML object:

    kind: environment          # or "lighting" (lights, rigs, practicals and channels only)
    version: 1
    name: studio               # owns what it makes: prune only ever removes actors this spec name made
    preset: interior_day       # optional base (PRESETS); the spec's own fields merge over it
    mood: night                # optional: which of `moods` to apply (plan(..., mood=) overrides it)
    sun: {time: "16:30", lat: 19.07, lon: 72.88, date: 2026-11-05, tz: 5.5, north_yaw_deg: 0}
    atmosphere: {preset: hazy}
    clouds: {bottom_km: 1.5, height_km: 6}
    sky_light: {intensity: 1.0}
    fog: {preset: haze, volumetric: true}
    exposure: {mode: manual, ev100: auto}
    grade: {preset: warm_film, vignette: 0.2}
    quality: final
    lights: {Window: {kind: rect, loc: [-250, 200, 150], look_at: [0, 0, 120], nits: 2000}}
    rigs: {Host: {subject: Host, subject_offset: [0, 0, 165], camera: HostCam, preset: interview, key_lux: 900}}
    practicals: {Lamp: {type: lamp, loc: [-200, -150, 120]}}
    channels: {Host: [0, 1]}
    reflection_captures: {RoomCapture: {shape: box, loc: [0, 0, 150], extent_cm: [400, 400, 200]}}
    cvars: {r.HairStrands.SkyLighting: 0}
    moods: {night: {sun: false, moon: {}, exposure: {ev100: 5}, grade: {preset: moonlight}}}
    checks: {camera: HostCam, targets: {mean: [0.3, 0.55], clipped_max: 0.01}}

A section set to false (or null) removes what it made. With `prune: true` (the default) anything this spec name made
earlier that the spec no longer asks for is removed too; actors the spec did not make are never touched.

The planner is pure: plan(spec, state) -> [{"op", "args", "why"}]. `state` is env.describe's result. Converged
means a second plan is empty. Everything resolvable without the engine is resolved here (the sun's position, lux,
exposure from the key light, grades, quality cvars, light candelas), so the comparison is like for like.
"""
from __future__ import annotations

import copy
import difflib
import math

from . import grade as grade_lib
from . import lights as lights_lib
from . import photometry as ph
from . import quality as quality_lib
from . import rig as rig_lib
from . import sun as sun_lib

KINDS = ("environment", "lighting")
VERSION = 1
PREFIX = "Env_"
LABELS = {"sun": "Env_Sun", "moon": "Env_Moon", "atmosphere": "Env_Atmosphere", "clouds": "Env_Clouds",
          "sky_light": "Env_SkyLight", "hdri": "Env_HDRI", "fog": "Env_Fog", "post": "Env_Post"}

ENV_SECTIONS = ("sun", "moon", "atmosphere", "clouds", "sky_light", "hdri", "fog", "exposure", "grade", "quality",
                "post", "reflection_captures", "cvars")
LIGHT_SECTIONS = ("lights", "rigs", "practicals", "channels")
META = ("kind", "version", "name", "preset", "mood", "moods", "prune", "checks", "description")

# ------------------------------------------------------------------------------------------- section fields
SECTION_FIELDS = {
    "sun": {"time": "local time 'HH:MM', decimal hours, or a named time of day (env.presets: times)",
            "lat": "latitude, degrees north", "lon": "longitude, degrees east", "date": "YYYY-MM-DD",
            "tz": "time zone, hours east of UTC", "elevation_deg": "sun elevation above the horizon (overrides time)",
            "azimuth_deg": "compass azimuth, degrees clockwise from north",
            "north_yaw_deg": "the level yaw of geographic north (0 = +X)",
            "intensity_lux": "illuminance; 'auto' = 120000 with an atmosphere (it attenuates), else by elevation",
            "temperature_k": "colour temperature; 'auto' = 6500 with an atmosphere (it tints), else by elevation",
            "softness_deg": "the sun's angular diameter (shadow softness), 0.5357 is the real sun",
            "channels": "lighting channels [0..2]", "cloud_shadows": "cast shadows from volumetric clouds"},
    "moon": {"elevation_deg": "moon elevation", "azimuth_deg": "compass azimuth", "north_yaw_deg": "level yaw of north",
             "intensity_lux": "illuminance (full moon ~0.25; stylised night 0.5-2)", "temperature_k": "kelvin",
             "softness_deg": "angular size", "channels": "lighting channels"},
    "atmosphere": {"preset": "clear|crisp|hazy|smoggy|dusty", "haze": "x Mie scattering (aerosols)",
                   "rayleigh": "x Rayleigh scattering (sky blueness)", "aerial_distance_scale": "x aerial perspective",
                   "mie_anisotropy": "0-1 forward scattering of haze", "ground_albedo": "[r,g,b] linear",
                   "multi_scattering": "multi-scattering factor", "height_fog_contribution": "0-1"},
    "clouds": {"bottom_km": "cloud layer bottom altitude, km", "height_km": "cloud layer thickness, km",
               "material": "a volumetric cloud material path (default: the engine's simple clouds)"},
    "sky_light": {"mode": "realtime|captured|cubemap", "intensity": "scale", "cubemap": "a TextureCube path",
                  "cubemap_angle_deg": "rotation of the cubemap", "lower_hemisphere_black": "bool",
                  "lower_hemisphere_color": "[r,g,b] linear", "channels": "lighting channels",
                  "cast_shadows": "bool"},
    "hdri": {"cubemap": "a TextureCube path (an .hdr imported as a long-lat cubemap)", "intensity": "sky light scale",
             "rotation_deg": "yaw of the image", "backdrop": "also show it as a backdrop (HDRIBackdrop plugin)",
             "size_cm": "backdrop size"},
    "fog": {"preset": "none|light|haze|mist|dense|ground|interior_haze", "density": "fog density",
            "falloff": "height falloff", "height_cm": "fog base height (actor z)", "start_cm": "start distance",
            "max_opacity": "0-1", "cutoff_cm": "cutoff distance (0 = none)", "color": "inscattering [r,g,b] linear",
            "volumetric": "bool: volumetric fog (light shafts)", "albedo": "volumetric albedo [r,g,b]",
            "extinction": "volumetric extinction scale", "distance_cm": "volumetric fog view distance",
            "scattering": "volumetric scattering distribution (-0.9..0.9, 0.2 = slightly forward)",
            "emissive": "volumetric emissive [r,g,b]"},
    "exposure": {"mode": "manual|physical|auto", "ev100": "the scene EV100 to expose for, or 'auto' (from the key light / sun)",
                 "compensation": "stops brighter (+) or darker (-)", "fstop": "physical: aperture",
                 "shutter_s": "physical: shutter time, s", "iso": "physical: ISO",
                 "min_ev100": "auto: the darkest scene EV100 it adapts to", "max_ev100": "auto: the brightest",
                 "speed": "auto: adaptation speed (stops/s)"},
    "grade": None,  # grade presets + PostProcessSettings fields + aliases (grade.ALIASES): checked in grade.fields
    "quality": None,  # a preset name or {preset, overrides}: checked in quality.resolve
    "post": None,     # raw PostProcessSettings fields
    "cvars": None,    # {name: value}
    "reflection_captures": {"shape": "sphere|box", "loc": "[x,y,z] cm", "radius_cm": "sphere influence radius",
                            "extent_cm": "box half-size [x,y,z] cm", "transition_cm": "box blend distance",
                            "brightness": "scale"},
    "rigs": {"subject": "an actor label or [x,y,z] cm", "subject_offset": "[x,y,z] cm added (e.g. eye height)",
             "socket": "a socket/bone on the subject's skeletal mesh to light (e.g. 'head')",
             "camera": "a camera label or [x,y,z]", "facing_yaw_deg": "the subject's facing when there is no camera",
             "preset": "a rig preset (env.presets: rigs)", "key_lux": "lux on the subject from the key",
             "ratio": "lighting ratio (key+fill):fill", "lights": "per-role overrides {role: {...} | null}",
             "key_side": "left|right (camera-left/right)", "scale": "x distances and sizes",
             "temperature_k": "every light's kelvin", "channels": "lighting channels for every light"},
}

# ------------------------------------------------------------------------------------------- presets
ATMOSPHERE = {  # Earth defaults (USkyAtmosphereComponent ctor) and multipliers
    "base": {"rayleigh_scattering_scale": 0.0331, "mie_scattering_scale": 0.003996, "mie_absorption_scale": 0.000444,
             "mie_anisotropy": 0.8, "multi_scattering_factor": 1.0, "aerial_pespective_view_distance_scale": 1.0,
             "height_fog_contribution": 1.0, "ground_albedo": [0.402, 0.402, 0.402]},
    "presets": {"clear": {}, "crisp": {"haze": 0.4}, "hazy": {"haze": 3.0, "aerial_distance_scale": 1.5},
                "smoggy": {"haze": 8.0, "mie_absorption": 5.0, "aerial_distance_scale": 2.0},
                "dusty": {"haze": 5.0, "ground_albedo": [0.5, 0.38, 0.25], "mie_anisotropy": 0.7}},
}
FOG = {
    "none": {"density": 0.0, "volumetric": False},
    "light": {"density": 0.005, "falloff": 0.2, "volumetric": False},
    "haze": {"density": 0.02, "falloff": 0.2, "volumetric": True, "extinction": 0.5},
    "mist": {"density": 0.05, "falloff": 0.5, "volumetric": True, "extinction": 1.0},
    "dense": {"density": 0.2, "falloff": 0.3, "volumetric": True, "extinction": 2.0},
    "ground": {"density": 0.3, "falloff": 2.0, "height_cm": 0.0, "volumetric": True, "extinction": 1.0},
    "interior_haze": {"density": 0.0005, "falloff": 0.02, "volumetric": True, "extinction": 0.05,
                      "albedo": [0.95, 0.93, 0.9]},
}
FOG_DEFAULT = {"density": 0.02, "falloff": 0.2, "height_cm": 0.0, "start_cm": 0.0, "max_opacity": 1.0,
               "cutoff_cm": 0.0, "color": [0.45, 0.5, 0.6], "volumetric": True, "albedo": [1.0, 1.0, 1.0],
               "extinction": 1.0, "distance_cm": 6000.0, "scattering": 0.2, "emissive": [0.0, 0.0, 0.0]}

PRESETS = {
    "exterior_day": {"about": "outdoors, clear afternoon: physical sun and sky, clouds, light haze",
                     "sun": {"time": "afternoon"}, "atmosphere": {"preset": "clear"}, "clouds": {},
                     "sky_light": {}, "fog": {"preset": "light"}, "exposure": {"mode": "manual", "ev100": "auto"},
                     "grade": {"preset": "neutral"}, "quality": "final"},
    "exterior_golden": {"about": "outdoors at golden hour: low warm sun, haze, glowing grade",
                        "sun": {"time": "golden_evening"}, "atmosphere": {"preset": "hazy"}, "clouds": {},
                        "sky_light": {}, "fog": {"preset": "haze"}, "exposure": {"mode": "manual", "ev100": "auto"},
                        "grade": {"preset": "golden_hour"}, "quality": "final"},
    "exterior_overcast": {"about": "outdoors under cloud: soft shadowless light",
                          "sun": {"time": "noon", "softness_deg": 20.0, "intensity_lux": 25000.0},
                          "atmosphere": {"preset": "hazy"}, "clouds": {"height_km": 8.0}, "sky_light": {"intensity": 1.5},
                          "fog": {"preset": "light"}, "exposure": {"mode": "manual", "ev100": 12.5},
                          "grade": {"preset": "documentary"}, "quality": "final"},
    "exterior_blue_hour": {"about": "after sunset: the sky lights everything blue, no direct sun",
                           "sun": {"time": "blue_hour"}, "atmosphere": {"preset": "clear"}, "sky_light": {},
                           "fog": {"preset": "light"}, "exposure": {"mode": "manual", "ev100": 6.0},
                           "grade": {"preset": "neutral", "white_balance": 7000}, "quality": "final"},
    "exterior_night": {"about": "moonlit night, stylised to read (day-for-night grade)",
                       "sun": False, "moon": {}, "atmosphere": {"preset": "clear"}, "sky_light": {"intensity": 0.3},
                       "fog": {"preset": "light"}, "exposure": {"mode": "manual", "ev100": 1.0},
                       "grade": {"preset": "moonlight"}, "quality": "final"},
    "interior_day": {"about": "a room by day: sun and sky through the windows, soft interior haze",
                     "sun": {"time": "afternoon"}, "atmosphere": {"preset": "clear"}, "sky_light": {"intensity": 1.0},
                     "fog": {"preset": "interior_haze"}, "exposure": {"mode": "manual", "ev100": 8.5},
                     "grade": {"preset": "warm_film"}, "quality": "final"},
    "interior_night": {"about": "a room at night: practicals and a dim blue window, warm grade",
                       "sun": False, "atmosphere": {"preset": "clear"}, "sky_light": {"intensity": 0.05},
                       "fog": {"preset": "interior_haze"}, "exposure": {"mode": "manual", "ev100": 5.0},
                       "grade": {"preset": "warm_film"}, "quality": "final"},
    "studio_black": {"about": "a black void: only your own lights (rigs); for product and character tests",
                     "sun": False, "atmosphere": False, "clouds": False, "sky_light": False, "fog": False,
                     "exposure": {"mode": "manual", "ev100": "auto"}, "grade": {"preset": "clean"}, "quality": "final"},
    "studio_grey": {"about": "a soft grey studio: an even dim sky light plus your rig",
                    "sun": False, "atmosphere": False, "clouds": False,
                    "sky_light": {"mode": "captured", "intensity": 0.5, "lower_hemisphere_black": False,
                                  "lower_hemisphere_color": [0.18, 0.18, 0.18]},
                    "fog": False, "exposure": {"mode": "manual", "ev100": "auto"}, "grade": {"preset": "clean"},
                    "quality": "final"},
}
MOOD_EXAMPLE = {"night": {"sun": False, "moon": {}, "exposure": {"ev100": 5.0}, "grade": {"preset": "moonlight"}}}


# ------------------------------------------------------------------------------------------- helpers

class SpecError(ValueError):
    """A spec problem, with where (a dotted path) and what to do."""

    def __init__(self, where: str, message: str, hint: str = ""):
        super().__init__(f"{where}: {message}" + (f" ({hint})" if hint else ""))
        self.where, self.message_, self.hint = where, message, hint


def merge(base, over):
    """Deep merge: dicts merge key by key; anything else in `over` (a list, a number, False/None) replaces."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = copy.deepcopy(base)
        for k, v in over.items():
            out[k] = merge(out.get(k), v) if k in out else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def _did_you_mean(k, allowed) -> str:
    m = difflib.get_close_matches(str(k), sorted(allowed), 1, 0.6)
    return f"did you mean {m[0]!r}?" if m else f"allowed: {', '.join(sorted(allowed))}"


def _off(v) -> bool:
    return v is False or v is None


def resolve(spec: dict, mood: str = None) -> dict:
    """The effective spec: the preset, then the spec's own fields, then the mood's overlay. Validates everything."""
    if not isinstance(spec, dict):
        raise SpecError("spec", "a spec is one object (mapping)")
    kind = spec.get("kind", "environment")
    if kind not in KINDS:
        raise SpecError("kind", f"{kind!r} is not a kind this planner handles", f"one of {KINDS}")
    if int(spec.get("version", VERSION)) != VERSION:
        raise SpecError("version", f"version {spec.get('version')} is not supported", f"this planner reads version {VERSION}")
    sections = (ENV_SECTIONS + LIGHT_SECTIONS) if kind == "environment" else LIGHT_SECTIONS
    allowed = set(sections) | set(META)
    for k in spec:
        if k not in allowed:
            raise SpecError(k, f"unknown field for a {kind} spec", _did_you_mean(k, allowed))
    out = {}
    if spec.get("preset"):
        if kind != "environment":
            raise SpecError("preset", "only an environment spec takes a preset")
        if spec["preset"] not in PRESETS:
            raise SpecError("preset", f"unknown preset {spec['preset']!r}", _did_you_mean(spec["preset"], PRESETS))
        out = {k: copy.deepcopy(v) for k, v in PRESETS[spec["preset"]].items() if k != "about"}
    out = merge(out, {k: v for k, v in spec.items() if k not in ("moods",)})
    mood = mood if mood is not None else spec.get("mood")
    if mood:
        moods = spec.get("moods") or {}
        if mood not in moods:
            raise SpecError("mood", f"no mood {mood!r} in this spec", f"moods: {sorted(moods) or 'none defined'}")
        bad = set(moods[mood]) - set(sections)
        if bad:
            raise SpecError(f"moods.{mood}", f"unknown field(s) {sorted(bad)}", _did_you_mean(sorted(bad)[0], sections))
        out = merge(out, moods[mood])
    out["mood"] = mood or None
    out["kind"] = kind
    out.setdefault("name", "env")
    out.setdefault("prune", True)
    _validate_sections(out)
    return out


def _validate_sections(s: dict) -> None:
    for sec, fields in SECTION_FIELDS.items():
        v = s.get(sec)
        if _off(v) or fields is None:
            continue
        if sec in ("reflection_captures", "rigs"):
            if not isinstance(v, dict):
                raise SpecError(sec, "a mapping of label -> settings")
            for lab, item in v.items():
                if _off(item):
                    continue
                for k in item:
                    if k not in fields:
                        raise SpecError(f"{sec}.{lab}.{k}", "unknown field", _did_you_mean(k, fields))
            continue
        if not isinstance(v, dict):
            raise SpecError(sec, "a mapping of settings (or false to remove it)")
        for k in v:
            if k not in fields:
                raise SpecError(f"{sec}.{k}", "unknown field", _did_you_mean(k, fields))
    for k in ("lights", "practicals"):
        if not _off(s.get(k)) and not isinstance(s.get(k), dict):
            raise SpecError(k, "a mapping of label -> light settings")


# ------------------------------------------------------------------------------------------- normalise sections

def norm_sun(v: dict, atmosphere: bool, label: str = LABELS["sun"], moon: bool = False) -> dict:
    v = dict(v or {})
    north = float(v.get("north_yaw_deg", 0.0))
    if moon:
        pos = {"elevation": float(v.get("elevation_deg", 35.0)), "azimuth": float(v.get("azimuth_deg", 120.0))}
    else:
        rs = {k: v[k] for k in ("time", "lat", "lon", "date", "tz") if k in v}
        if "elevation_deg" in v:
            rs["elevation"] = v["elevation_deg"]
            rs["azimuth"] = v.get("azimuth_deg", 180.0)
        elif "azimuth_deg" in v:
            rs["azimuth"] = v["azimuth_deg"]
        try:
            pos = sun_lib.resolve(rs)
        except ValueError as e:
            raise SpecError("sun", str(e)) from None
    el, az = float(pos["elevation"]), float(pos["azimuth"])
    lux = v.get("intensity_lux", "auto")
    if lux == "auto":
        lux = 0.5 if moon else (sun_lib.SOLAR_LUX if atmosphere else sun_lib.direct_lux(el))
    temp = v.get("temperature_k", "auto")
    if temp == "auto":
        temp = 4100.0 if moon else (6500.0 if atmosphere else sun_lib.sun_kelvin(el))
    out = {"label": label, "elevation_deg": round(el, 4), "azimuth_deg": round(az, 4), "north_yaw_deg": north,
           "rotation": sun_lib.light_rotation(el, az, north), "intensity_lux": float(lux), "temperature_k": float(temp),
           "softness_deg": float(v.get("softness_deg", 1.0 if moon else 0.5357)),
           "atmosphere_index": 1 if moon else 0}
    if "channels" in v:
        out["channels"] = sorted(int(c) for c in v["channels"])
    if not moon:
        out["cloud_shadows"] = bool(v.get("cloud_shadows", True))
    if pos.get("hour") is not None:
        out["hour"] = pos["hour"]
    return out


def norm_atmosphere(v: dict) -> dict:
    v = dict(v or {})
    p = v.pop("preset", "clear")
    if p not in ATMOSPHERE["presets"]:
        raise SpecError("atmosphere.preset", f"unknown {p!r}", _did_you_mean(p, ATMOSPHERE["presets"]))
    v = {**ATMOSPHERE["presets"][p], **v}
    b = dict(ATMOSPHERE["base"])
    b["mie_scattering_scale"] *= float(v.get("haze", 1.0))
    b["mie_absorption_scale"] *= float(v.get("mie_absorption", 1.0))
    b["rayleigh_scattering_scale"] *= float(v.get("rayleigh", 1.0))
    b["aerial_pespective_view_distance_scale"] *= float(v.get("aerial_distance_scale", 1.0))
    for k, f in (("mie_anisotropy", "mie_anisotropy"), ("multi_scattering", "multi_scattering_factor"),
                 ("height_fog_contribution", "height_fog_contribution")):
        if k in v:
            b[f] = float(v[k])
    if "ground_albedo" in v:
        b["ground_albedo"] = [float(c) for c in v["ground_albedo"]]
    b["ground_albedo"] = ph.quantize_fcolor(b["ground_albedo"])  # an FColor property
    return {"label": LABELS["atmosphere"], **{k: (round(x, 7) if isinstance(x, float) else x) for k, x in b.items()}}


def norm_clouds(v: dict) -> dict:
    v = dict(v or {})
    out = {"label": LABELS["clouds"], "bottom_km": float(v.get("bottom_km", 5.0)), "height_km": float(v.get("height_km", 10.0))}
    if v.get("material"):
        out["material"] = v["material"]
    return out


def norm_sky_light(v: dict, atmosphere: bool, hdri: dict = None) -> dict:
    v = dict(v or {})
    mode = v.get("mode") or ("cubemap" if hdri else "realtime" if atmosphere else "captured")
    if mode not in ("realtime", "captured", "cubemap"):
        raise SpecError("sky_light.mode", f"{mode!r} is not realtime|captured|cubemap")
    out = {"label": LABELS["sky_light"], "mode": mode,
           "intensity": float(v.get("intensity", (hdri or {}).get("intensity", 1.0)))}
    if mode == "cubemap":
        cube = v.get("cubemap") or (hdri or {}).get("cubemap")
        if not cube:
            raise SpecError("sky_light.cubemap", "mode cubemap needs a cubemap (or an hdri section)")
        out["cubemap"] = cube
        out["cubemap_angle_deg"] = float(v.get("cubemap_angle_deg", (hdri or {}).get("rotation_deg", 0.0)))
    out["lower_hemisphere_black"] = bool(v.get("lower_hemisphere_black", True))
    if "lower_hemisphere_color" in v:
        out["lower_hemisphere_color"] = [float(c) for c in v["lower_hemisphere_color"]]
    if "channels" in v:
        out["channels"] = sorted(int(c) for c in v["channels"])
    if "cast_shadows" in v:
        out["cast_shadows"] = bool(v["cast_shadows"])
    return out


def norm_hdri(v: dict) -> dict:
    v = dict(v or {})
    if not v.get("cubemap"):
        raise SpecError("hdri.cubemap", "an hdri needs a TextureCube path",
                        "import the .hdr with assets.import (LoadHdrAsLongLatCubemap=1, see environment.md)")
    return {"label": LABELS["hdri"], "cubemap": v["cubemap"], "intensity": float(v.get("intensity", 1.0)),
            "rotation_deg": float(v.get("rotation_deg", 0.0)), "backdrop": bool(v.get("backdrop", False)),
            "size_cm": float(v.get("size_cm", 15000.0))}


def norm_fog(v: dict) -> dict:
    v = dict(v or {})
    p = v.pop("preset", None)
    base = dict(FOG_DEFAULT)
    if p is not None:
        if p not in FOG:
            raise SpecError("fog.preset", f"unknown {p!r}", _did_you_mean(p, FOG))
        base.update(FOG[p])
    base.update(v)
    out = {"label": LABELS["fog"]}
    for k, d in FOG_DEFAULT.items():
        x = base.get(k, d)
        out[k] = bool(x) if isinstance(d, bool) else [float(c) for c in x] if isinstance(d, list) else float(x)
    out["albedo"] = ph.quantize_fcolor(out["albedo"])  # VolumetricFogAlbedo is an FColor
    return out


def norm_capture(label: str, v: dict) -> dict:
    shape = v.get("shape", "sphere")
    if shape not in ("sphere", "box"):
        raise SpecError(f"reflection_captures.{label}.shape", f"{shape!r} is not sphere|box")
    out = {"label": label, "shape": shape, "loc": [float(c) for c in v.get("loc", (0, 0, 150))],
           "brightness": float(v.get("brightness", 1.0))}
    if shape == "sphere":
        out["radius_cm"] = float(v.get("radius_cm", 3000.0))
    else:
        out["extent_cm"] = [float(c) for c in v.get("extent_cm", (500, 500, 250))]
        out["transition_cm"] = float(v.get("transition_cm", 100.0))
    return out


def key_lux_of(s: dict):
    """The main light's lux at the subject, for exposure 'auto': the first rig's key, else a horizontal surface under
    the sun (direct x sin(elevation) plus ~20% sky), else None."""
    rigs = {k: v for k, v in (s.get("rigs") or {}).items() if not _off(v)}
    if rigs:
        r = rigs[sorted(rigs)[0]]
        return float(r.get("key_lux", 800.0))
    sun = s.get("sun")
    if not _off(sun):
        n = norm_sun(sun, atmosphere=False)
        el = n["elevation_deg"]
        if el > 0:
            return sun_lib.direct_lux(el) * math.sin(math.radians(el)) * 1.2
    return None


def exposure_fields(v: dict, s: dict) -> dict:
    """The exposure section to PostProcessSettings fields (see photometry: calibration)."""
    v = dict(v or {})
    mode = v.get("mode", "manual")
    comp = float(v.get("compensation", 0.0))
    if mode not in ("manual", "physical", "auto"):
        raise SpecError("exposure.mode", f"{mode!r} is not manual|physical|auto")
    if mode == "auto":
        out = {"auto_exposure_method": "AutoExposureMethod.AEM_HISTOGRAM", "auto_exposure_bias": comp,
               "auto_exposure_apply_physical_camera_exposure": False,
               "auto_exposure_min_brightness": ph.ue_ev100(float(v.get("min_ev100", -2.0))),
               "auto_exposure_max_brightness": ph.ue_ev100(float(v.get("max_ev100", 16.0)))}
        if "speed" in v:
            out["auto_exposure_speed_up"] = out["auto_exposure_speed_down"] = float(v["speed"])
        return out
    if mode == "physical":
        return {"auto_exposure_method": "AutoExposureMethod.AEM_MANUAL",
                "auto_exposure_apply_physical_camera_exposure": True,
                "auto_exposure_bias": round(ph.UE_EV_OFFSET + comp, 4),
                "camera_iso": float(v.get("iso", 100.0)), "camera_shutter_speed": 1.0 / float(v.get("shutter_s", 1 / 48)),
                "depth_of_field_fstop": float(v.get("fstop", 4.0))}
    ev = v.get("ev100", "auto")
    if ev == "auto":
        lux = key_lux_of(s)
        ev = ph.ev100_from_illuminance(lux) if lux else 9.0
    return {"auto_exposure_method": "AutoExposureMethod.AEM_MANUAL",
            "auto_exposure_apply_physical_camera_exposure": False,
            "auto_exposure_bias": round(ph.ue_manual_bias_for_ev100(float(ev)) + comp, 4)}


def post_fields(s: dict) -> dict:
    """Every PostProcessSettings field the spec sets: quality, then exposure, then grade, then raw `post`."""
    out = {}
    if not _off(s.get("quality")):
        try:
            out.update(quality_lib.post_fields(s["quality"]))
        except ValueError as e:
            raise SpecError("quality", str(e)) from None
    if not _off(s.get("exposure")):
        out.update(exposure_fields(s["exposure"], s))
    if not _off(s.get("grade")):
        try:
            out.update(grade_lib.fields(s["grade"]))
        except ValueError as e:
            raise SpecError("grade", str(e)) from None
    if not _off(s.get("post")):
        out.update(s["post"])
    return out


def cvars_of(s: dict) -> dict:
    out = {}
    if not _off(s.get("quality")):
        out.update(quality_lib.cvars(s["quality"]))
    out.update(s.get("cvars") or {})
    return out


def desired(spec: dict, mood: str = None) -> dict:
    """The effective spec resolved to the canonical state env.describe reports (the parts the planner compares)."""
    s = resolve(spec, mood)
    env = s["kind"] == "environment"
    atmo = env and not _off(s.get("atmosphere"))
    d = {"name": s["name"], "kind": s["kind"], "prune": bool(s.get("prune", True)), "mood": s.get("mood"),
         "off": sorted(k for k in ENV_SECTIONS if k in s and _off(s[k]))}  # explicitly false: remove even if another spec made it
    if env:
        d["sun"] = None if _off(s.get("sun")) else norm_sun(s["sun"], atmo)
        d["moon"] = None if _off(s.get("moon")) else norm_sun(s["moon"], atmo, LABELS["moon"], moon=True)
        d["atmosphere"] = norm_atmosphere(s["atmosphere"]) if atmo else None
        d["clouds"] = None if _off(s.get("clouds")) else norm_clouds(s["clouds"])
        d["hdri"] = None if _off(s.get("hdri")) else norm_hdri(s["hdri"])
        d["sky_light"] = None if _off(s.get("sky_light")) and not d["hdri"] else norm_sky_light(
            s.get("sky_light") or {}, atmo, d["hdri"])
        d["fog"] = None if _off(s.get("fog")) else norm_fog(s["fog"])
        d["post"] = post_fields(s)
        d["cvars"] = cvars_of(s)
        d["captures"] = {k: norm_capture(k, v) for k, v in (s.get("reflection_captures") or {}).items() if not _off(v)}
    lights = {}
    for lab, v in (s.get("lights") or {}).items():
        if _off(v):
            continue
        try:
            lights[lab] = lights_lib.normalize(v, lab)
        except ValueError as e:
            raise SpecError(f"lights.{lab}", str(e)) from None
    for lab, v in (s.get("practicals") or {}).items():
        if _off(v):
            continue
        try:
            lights[lab] = lights_lib.practical(v, lab)
        except ValueError as e:
            raise SpecError(f"practicals.{lab}", str(e)) from None
    d["lights"] = lights
    d["rigs"] = {}
    for name, v in (s.get("rigs") or {}).items():
        if _off(v):
            continue
        args = rig_args(name, v)
        d["rigs"][args["prefix"]] = args
    d["channels"] = {k: sorted(int(c) for c in v) for k, v in (s.get("channels") or {}).items()}
    d["checks"] = s.get("checks")
    return d


def rig_args(name: str, v: dict) -> dict:
    """A rig section to light.rig's arguments (validated against the rig presets now, not in the editor)."""
    v = dict(v)
    if "subject" not in v:
        raise SpecError(f"rigs.{name}.subject", "a rig needs a subject (an actor label or [x, y, z])")
    if v.get("preset", "three_point") not in rig_lib.PRESETS:
        raise SpecError(f"rigs.{name}.preset", f"unknown rig preset {v.get('preset')!r}",
                        _did_you_mean(v.get("preset"), rig_lib.PRESETS))
    if "camera" not in v and "facing_yaw_deg" not in v:
        raise SpecError(f"rigs.{name}", "a rig needs `camera` (label or point) or `facing_yaw_deg`")
    args = {"prefix": f"{name}_", **{k: v[k] for k in v}}
    args.setdefault("preset", "three_point")
    return args


# ------------------------------------------------------------------------------------------- the planner

def _num_same(a, b, tol=1e-3):
    return lights_lib.differs({"v": a}, {"v": b}, tol) == []


def plan(spec: dict, state: dict, mood: str = None) -> list:
    """The op calls that take the level from `state` (env.describe) to `spec`, in order: removals, sky and air,
    post and cvars, captures, lights, rigs, channels. Empty when the level already matches."""
    d = desired(spec, mood)
    state = state or {}
    owner = d["name"]
    steps = []

    def step(op, args, why):
        steps.append({"op": op, "args": args, "why": why})

    owned = {lab for lab, o in (state.get("owners") or {}).items() if o == owner}

    if d["kind"] == "environment":
        for part in ("atmosphere", "sun", "moon", "clouds", "hdri", "sky_light", "fog"):
            want, have = d[part], state.get(part)
            if want is None:
                if have and (have.get("label") in owned or (part in d["off"] and have.get("owner"))):
                    step("env.remove", {"parts": [part]}, f"{part}: not in the spec")
                continue
            diff = lights_lib.differs({k: v for k, v in want.items() if k not in ("hour",)}, have or {})
            if not have or diff:
                op = {"moon": "env.moon"}.get(part, f"env.{part}")
                args = {k: v for k, v in want.items() if k not in ("label", "rotation", "hour")}
                if part in ("sun", "moon"):
                    args = {k: args[k] for k in args if k not in ("cloud_shadows",) or part == "sun"}
                step(op, {**args, "owner": owner}, f"{part}: " + ("missing" if not have else f"differs in {diff}"))
        have_post = state.get("post") or {}
        changed = {k: v for k, v in d["post"].items() if not _num_same(_jsonish(v), _jsonish(have_post.get(k)))}
        stale = sorted(set(state.get("post_owned_fields") or []) - set(d["post"])) if d["prune"] else []
        if changed or stale:
            step("env.post", {"fields": changed, "clear": stale, "owner": owner},
                 f"post: {len(changed)} field(s) differ" + (f", {len(stale)} to clear" if stale else ""))
        have_cv = state.get("cvars") or {}
        cv = {k: v for k, v in d["cvars"].items() if not _num_same(v, have_cv.get(k))}
        if cv:
            step("env.cvars", {"cvars": cv}, f"cvars: {sorted(cv)} differ")
        have_caps = state.get("captures") or {}
        for lab, want in d["captures"].items():
            diff = lights_lib.differs(want, have_caps.get(lab) or {})
            if lab not in have_caps or diff:
                step("env.reflection_capture", {**{k: v for k, v in want.items()}, "owner": owner},
                     f"capture {lab}: " + ("missing" if lab not in have_caps else f"differs in {diff}"))
        if d["prune"]:
            gone = sorted(lab for lab in have_caps if lab in owned and lab not in d["captures"])
            if gone:
                step("light.remove", {"labels": gone}, "reflection captures no longer in the spec")

    have_lights = state.get("lights") or {}
    rig_owned = {lab for lab, L in have_lights.items() if L.get("rig")}
    for lab, want in d["lights"].items():
        have = have_lights.get(lab)
        diff = lights_lib.differs(want, have or {})
        if not have or diff:
            step("light.add", {**{k: v for k, v in want.items() if k != "role"}, "owner": owner},
                 f"light {lab}: " + ("missing" if not have else f"differs in {diff}"))
    have_rigs = state.get("rigs") or {}
    for prefix, args in d["rigs"].items():
        h = have_rigs.get(prefix)
        moved = h and (not _num_same(h.get("subject_point"), h.get("subject_now"), 1e-4)
                       or not _num_same(h.get("camera_point"), h.get("camera_now"), 1e-4))
        if not h or _jsonish(rig_lib.comparable(h.get("args"))) != _jsonish(rig_lib.comparable(args)) or moved:
            step("light.rig", {**args, "owner": owner},
                 f"rig {prefix}: " + ("missing" if not h else "the subject or camera moved" if moved else "settings differ"))
    if d["prune"]:
        gone = sorted(lab for lab in have_lights if lab in owned and lab not in d["lights"] and lab not in rig_owned)
        if gone:
            step("light.remove", {"labels": gone}, "lights no longer in the spec")
        for prefix, h in have_rigs.items():
            if prefix not in d["rigs"] and h.get("owner") == owner:
                step("light.remove", {"rig": prefix}, f"rig {prefix} no longer in the spec")
    have_ch = state.get("channels") or {}
    ch = {k: v for k, v in d["channels"].items() if have_ch.get(k, [0]) != v}
    if ch:
        step("light.channels", {"assign": ch}, f"lighting channels differ for {sorted(ch)}")
    return steps


def _jsonish(v):
    if isinstance(v, tuple):
        return [_jsonish(x) for x in v]
    if isinstance(v, list):
        return [_jsonish(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonish(x) for k, x in sorted(v.items())}
    return v


# ------------------------------------------------------------------------------------------- JSON schema

def json_schema(kind: str = "environment") -> dict:
    """The kind's JSON Schema (draft 2020-12), generated from the same tables the validator uses."""
    def obj(fields, desc=""):
        return {"type": "object", "description": desc, "additionalProperties": False,
                "properties": {k: {"description": v} for k, v in fields.items()}}

    def off_or(o):
        return {"anyOf": [o, {"type": "boolean", "const": False}, {"type": "null"}], "description": o.get("description", "")}

    light_props = {k: {"description": "see envlib/lights.py: canonical light"} for k in sorted(lights_lib.INPUT)}
    light = {"type": "object", "additionalProperties": False, "properties": light_props}
    practical = {"type": "object", "additionalProperties": False,
                 "properties": {**light_props, "type": {"enum": sorted(lights_lib.PRACTICALS)},
                                "aim": {"enum": ["down"]}, "scale": {"type": "number"}}, "required": ["type"]}
    props = {
        "kind": {"const": kind}, "version": {"const": VERSION}, "name": {"type": "string",
                                                                          "description": "owner name: prune scope"},
        "description": {"type": "string"},
        "mood": {"type": ["string", "null"], "description": "the mood to apply (a key of moods)"},
        "prune": {"type": "boolean", "description": "remove what this spec made earlier and no longer asks for"},
        "checks": {"type": "object", "description": "env.check: {camera, targets} (envlib/stats.py check targets)"},
        "lights": {"type": "object", "additionalProperties": off_or(light), "description": "label -> light"},
        "practicals": {"type": "object", "additionalProperties": off_or(practical), "description": "label -> practical"},
        "rigs": {"type": "object", "additionalProperties": off_or(obj(SECTION_FIELDS["rigs"], "a lighting rig")),
                 "description": "name -> rig; its lights are labelled <name>_<Role>"},
        "channels": {"type": "object", "additionalProperties": {"type": "array", "items": {"enum": [0, 1, 2]}},
                     "description": "actor label -> lighting channels"},
    }
    if kind == "environment":
        props["preset"] = {"enum": sorted(PRESETS), "description": "a base environment"}
        for sec in ENV_SECTIONS:
            f = SECTION_FIELDS.get(sec)
            if sec == "reflection_captures":
                props[sec] = {"type": "object", "additionalProperties": off_or(obj(f, "a reflection capture")),
                              "description": "label -> capture"}
            elif sec == "quality":
                props[sec] = {"anyOf": [{"enum": sorted(quality_lib.PRESETS)},
                                        {"type": "object", "additionalProperties": False,
                                         "properties": {k: {} for k in sorted(quality_lib.KEYS)}},
                                        {"const": False}, {"type": "null"}],
                              "description": "Lumen/VSM/HWRT preset (envlib/quality.py)"}
            elif sec == "grade":
                keys = sorted(set(grade_lib.NEUTRAL) | set(grade_lib.ALIASES) | {"preset", "color_grading_lut",
                                                                                "color_grading_intensity", "scene_color_tint"})
                props[sec] = off_or({"type": "object", "additionalProperties": False,
                                     "properties": {k: {} for k in keys}, "description": "colour grade"})
                props[sec]["anyOf"][0]["properties"]["preset"] = {"enum": sorted(grade_lib.PRESETS)}
            elif sec in ("post", "cvars"):
                props[sec] = {"type": "object", "description": "raw PostProcessSettings fields" if sec == "post"
                              else "console variables"}
            else:
                props[sec] = off_or(obj(f, sec))
        sections = list(ENV_SECTIONS) + list(LIGHT_SECTIONS)
    else:
        sections = list(LIGHT_SECTIONS)
    props["moods"] = {"type": "object", "description": "name -> a partial spec merged over this one",
                      "additionalProperties": {"type": "object", "additionalProperties": False,
                                               "properties": {k: props[k] for k in sections}}}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://claude-film-maker/schemas/{kind}.schema.json", "title": f"{kind} spec",
            "type": "object", "additionalProperties": False, "required": ["kind"], "properties": props}
