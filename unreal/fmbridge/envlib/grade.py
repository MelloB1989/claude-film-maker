"""The look in post: colour presets, white balance, LUTs, bloom, grain, vignette and the filmic tone curve, as Unreal
PostProcessSettings fields (snake_case Python names; the ops set each field's bOverride_ flag).

Values are plain JSON: a colour wheel (ColorSaturation, ColorContrast, ColorGamma, ColorGain, ColorOffset and their
Shadows/Midtones/Highlights variants) is [r, g, b, y] where y scales all three (1 = neutral; 0 for ColorOffset); a
tint is [r, g, b] or [r, g, b, a] linear; a LUT is a texture path. The ops turn them into unreal.Vector4/LinearColor
by the field's own type.
"""
from __future__ import annotations

import copy

NEUTRAL4 = [1.0, 1.0, 1.0, 1.0]

# a preset: what it is for (`about`) and its fields; every preset starts from NEUTRAL's tone curve and wheels
NEUTRAL = {
    "white_temp": 6500.0, "white_tint": 0.0,
    "color_saturation": NEUTRAL4, "color_contrast": NEUTRAL4, "color_gamma": NEUTRAL4, "color_gain": NEUTRAL4,
    "color_offset": [0.0, 0.0, 0.0, 0.0],
    "film_slope": 0.88, "film_toe": 0.55, "film_shoulder": 0.26, "film_black_clip": 0.0, "film_white_clip": 0.04,
    "bloom_intensity": 0.675, "bloom_threshold": -1.0, "vignette_intensity": 0.4, "film_grain_intensity": 0.0,
    "scene_fringe_intensity": 0.0,
}

for _w in ("saturation", "contrast", "gamma", "gain", "offset"):  # the band wheels too, so a re-grade resets them
    for _b in ("_shadows", "_midtones", "_highlights"):
        NEUTRAL[f"color_{_w}{_b}"] = [0.0, 0.0, 0.0, 0.0] if _w == "offset" else NEUTRAL4

PRESETS = {
    "neutral": {"about": "Unreal's defaults: the ACES-like filmic curve, a light vignette, no grade", "fields": {}},
    "clean": {"about": "neutral without lens dressing: no vignette, no fringe, gentle bloom (for QA and plates)",
              "fields": {"vignette_intensity": 0.0, "bloom_intensity": 0.2, "bloom_threshold": 1.0}},
    "warm_film": {"about": "warm, soft-contrast film: lifted blacks, a touch of grain and vignette",
                  "fields": {"white_temp": 5800.0, "color_saturation": [1.0, 1.0, 1.0, 0.95],
                             "color_contrast": [1.0, 1.0, 1.0, 0.95], "color_gain": [1.03, 1.0, 0.95, 1.0],
                             "color_offset": [0.004, 0.003, 0.0, 0.0], "film_toe": 0.6, "film_grain_intensity": 0.08,
                             "vignette_intensity": 0.3, "bloom_intensity": 0.3, "bloom_threshold": 1.0}},
    "teal_orange": {"about": "blockbuster: warm skin against teal shadows, punchy contrast",
                    "fields": {"color_saturation_shadows": [0.9, 1.0, 1.1, 1.0], "color_gain_shadows": [0.92, 1.0, 1.06, 1.0],
                               "color_gain_highlights": [1.06, 1.0, 0.92, 1.0], "color_contrast": [1.0, 1.0, 1.0, 1.1],
                               "color_saturation": [1.0, 1.0, 1.0, 1.1], "vignette_intensity": 0.35}},
    "bleach_bypass": {"about": "desaturated, hard contrast, silvery highlights (war, thriller)",
                      "fields": {"color_saturation": [1.0, 1.0, 1.0, 0.55], "color_contrast": [1.0, 1.0, 1.0, 1.3],
                                 "film_slope": 0.95, "film_toe": 0.45, "film_grain_intensity": 0.15,
                                 "vignette_intensity": 0.45}},
    "noir_bw": {"about": "black and white, deep blacks, grain",
                "fields": {"color_saturation": [1.0, 1.0, 1.0, 0.0], "color_contrast": [1.0, 1.0, 1.0, 1.25],
                           "film_toe": 0.5, "film_black_clip": 0.005, "film_grain_intensity": 0.25,
                           "vignette_intensity": 0.55}},
    "golden_hour": {"about": "honeyed warmth, glowing highlights",
                    "fields": {"white_temp": 5200.0, "color_gain_highlights": [1.06, 1.0, 0.88, 1.0],
                               "color_saturation": [1.0, 1.0, 1.0, 1.08], "bloom_intensity": 0.8, "bloom_threshold": 0.8,
                               "vignette_intensity": 0.3}},
    "moonlight": {"about": "day-for-night: cold, low saturation, darker mids (pair with a low exposure)",
                  "fields": {"white_temp": 9000.0, "color_saturation": [0.9, 0.95, 1.1, 0.55],
                             "color_gamma": [1.0, 1.0, 1.0, 0.9], "color_gain": [0.8, 0.9, 1.1, 1.0],
                             "film_toe": 0.6, "film_grain_intensity": 0.1, "vignette_intensity": 0.5}},
    "pastel": {"about": "soft, airy, low contrast with lifted shadows",
               "fields": {"color_contrast": [1.0, 1.0, 1.0, 0.82], "color_saturation": [1.0, 1.0, 1.0, 0.85],
                          "color_offset": [0.012, 0.012, 0.014, 0.0], "bloom_intensity": 0.5, "vignette_intensity": 0.0}},
    "high_contrast": {"about": "crisp and saturated: commercials, sport",
                      "fields": {"color_contrast": [1.0, 1.0, 1.0, 1.2], "color_saturation": [1.0, 1.0, 1.0, 1.2],
                                 "film_slope": 0.95, "vignette_intensity": 0.2}},
    "vintage_fade": {"about": "faded print: milky blacks, warm-green cast, heavy grain",
                     "fields": {"color_offset": [0.03, 0.028, 0.018, 0.0], "color_contrast": [1.0, 1.0, 1.0, 0.85],
                                "color_saturation": [1.0, 1.0, 0.9, 0.8], "color_gain": [1.02, 1.03, 0.94, 1.0],
                                "film_grain_intensity": 0.3, "vignette_intensity": 0.5}},
    "documentary": {"about": "naturalistic: slight desaturation, no lens dressing",
                    "fields": {"color_saturation": [1.0, 1.0, 1.0, 0.92], "vignette_intensity": 0.1,
                               "bloom_intensity": 0.2, "bloom_threshold": 1.0}},
}

# the grade spec's friendly names -> PostProcessSettings fields
ALIASES = {
    "white_balance": "white_temp", "tint": "white_tint", "saturation": "color_saturation", "contrast": "color_contrast",
    "gamma": "color_gamma", "gain": "color_gain", "offset": "color_offset", "bloom": "bloom_intensity",
    "grain": "film_grain_intensity", "vignette": "vignette_intensity", "fringe": "scene_fringe_intensity",
    "chromatic_aberration": "scene_fringe_intensity", "lut": "color_grading_lut", "lut_intensity": "color_grading_intensity",
    "color_tint": "scene_color_tint",
}
WHEELS = {f"color_{w}{band}" for w in ("saturation", "contrast", "gamma", "gain", "offset")
          for band in ("", "_shadows", "_midtones", "_highlights")}


def wheel(v) -> list:
    """A colour wheel value: a number scales all channels ([1, 1, 1, v]); a 3-list is per channel ([r, g, b, 1])."""
    if isinstance(v, (int, float)):
        return [1.0, 1.0, 1.0, float(v)]
    v = [float(x) for x in v]
    return v + [1.0] if len(v) == 3 else v


def fields(spec: dict = None) -> dict:
    """A grade spec (preset + overrides, friendly names allowed) -> PostProcessSettings fields. Overrides apply on top
    of the preset, which applies on top of NEUTRAL, so re-grading never leaves an old preset's fields behind."""
    spec = dict(spec or {})
    name = spec.pop("preset", "neutral")
    if name not in PRESETS:
        raise ValueError(f"unknown grade preset {name!r}; one of {sorted(PRESETS)} (env.presets lists them)")
    out = copy.deepcopy(NEUTRAL)
    out.update(copy.deepcopy(PRESETS[name]["fields"]))
    for k, v in spec.items():
        k = ALIASES.get(k, k)
        if k in WHEELS:
            v = wheel(v)
        if k == "scene_color_tint" and isinstance(v, (list, tuple)) and len(v) == 3:
            v = list(v) + [1.0]
        out[k] = v
    if out.get("color_grading_lut") and "color_grading_intensity" not in out:
        out["color_grading_intensity"] = 1.0
    return out
