"""Photometry for lighting by numbers: exposure values, luminance, illuminance, light units and colour temperature.

Two EV conventions meet here and are kept apart by name:
- photographic EV100 (`ev100_*`): the exposure a light meter at ISO 100 gives, with the reflected-light calibration
  K = 12.5 (luminance L = 2^EV100 * K / 100 cd/m2) and the incident one C = 250 (illuminance E = 2^EV100 * C / 100 lux).
  Use it to think: an overcast day is EV100 ~12, a bright office ~7-8, a candle-lit room ~3-4.
- Unreal's light "EV" unit (`ue_light_ev_*`): RenderUtils.h EV100ToLuminance, luminance = 2^EV (LuminanceMax 1), no K.

All Unreal light intensities here are in its own default units: candelas for point/spot/rect lights (ELightUnits
Candelas), lux for a directional light, cd/m2 for an emissive surface or sky (with "extend default luminance range",
the 5.x default, one unit of scene colour is 1 cd/m2).
"""
from __future__ import annotations

import math

K_REFLECTED = 12.5  # the reflected-light meter calibration constant (ISO 2720)
C_INCIDENT = 250.0  # the incident-light meter calibration constant (flat diffuser)
MIDDLE_GREY = 0.18

# rough scene illuminance (lux) and the EV100 they meter at, for choosing exposure by eye
SCENES = {
    "direct_sun": 100000.0, "overcast_day": 10000.0, "shade_daylight": 20000.0, "dark_overcast": 1000.0,
    "tv_studio": 1000.0, "office": 500.0, "living_room": 100.0, "dim_interior": 50.0, "street_night": 15.0,
    "candle_lit": 5.0, "full_moon": 0.25, "starlight": 0.001,
}


def ev100_from_luminance(cd_m2: float) -> float:
    """The EV100 a spot meter gives for a surface of this luminance (cd/m2)."""
    return math.log2(max(cd_m2, 1e-12) * 100.0 / K_REFLECTED)


def luminance_from_ev100(ev100: float) -> float:
    """The luminance (cd/m2) a spot meter reads as `ev100`; the grey that exposure renders as middle grey."""
    return 2.0 ** ev100 * K_REFLECTED / 100.0


def ev100_from_illuminance(lux: float) -> float:
    """The EV100 an incident meter gives under this illuminance (lux): 2.5 lux = EV100 0, 1000 lux ~ EV100 8.6."""
    return math.log2(max(lux, 1e-12) * 100.0 / C_INCIDENT)


def illuminance_from_ev100(ev100: float) -> float:
    return 2.0 ** ev100 * C_INCIDENT / 100.0


def ev100_camera(fstop: float, shutter_s: float, iso: float = 100.0) -> float:
    """The scene EV100 a camera setting is correct for: log2(N^2 / t) - log2(ISO / 100)."""
    return math.log2(fstop * fstop / shutter_s) - math.log2(iso / 100.0)


def camera_for_ev100(ev100: float, fstop: float = 4.0, iso: float = 100.0) -> dict:
    """A shutter time (s) that exposes `ev100` at this f-stop and ISO."""
    t = fstop * fstop / (2.0 ** (ev100 + math.log2(iso / 100.0)))
    return {"fstop": fstop, "iso": iso, "shutter_s": t, "shutter": f"1/{round(1 / t)}" if t < 1 else f"{t:.2f}s"}


def luminance_of_lit_surface(lux: float, albedo: float = MIDDLE_GREY) -> float:
    """A diffuse (Lambertian) surface of `albedo` under `lux` has luminance albedo * E / pi (cd/m2)."""
    return albedo * lux / math.pi


# ------------------------------------------------------------------------------------------- Unreal light units

def ue_light_ev_to_nits(ev: float) -> float:
    """Unreal's EV light unit to luminance (cd/m2): RenderUtils.h EV100ToLuminance = 2^EV."""
    return 2.0 ** ev


def nits_to_ue_light_ev(nits: float) -> float:
    return math.log2(max(nits, 1e-12))


def lumens_to_candelas(lumens: float, kind: str, cone_deg: float = 44.0) -> float:
    """Unreal's own conversion (LocalLightComponent.cpp GetUnitsConversionFactor, RectLightComponent.cpp): a point light
    spreads over 4 pi sr, a spot over its outer cone 2 pi (1 - cos half-angle), a rect light is Lambertian (pi).
    `cone_deg` is the spot's outer cone half-angle (Unreal's OuterConeAngle)."""
    if kind == "point":
        return lumens / (4.0 * math.pi)
    if kind == "spot":
        c = min(math.cos(math.radians(cone_deg)), 1 - 1e-6)
        return lumens / (2.0 * math.pi * (1.0 - c))
    if kind == "rect":
        return lumens / math.pi
    raise ValueError(f"lumens_to_candelas: kind {kind!r} is not point/spot/rect")


def candelas_to_lumens(cd: float, kind: str, cone_deg: float = 44.0) -> float:
    return cd / lumens_to_candelas(1.0, kind, cone_deg)


def candelas_for_lux(lux: float, distance_cm: float, incidence_deg: float = 0.0) -> float:
    """The intensity (cd) a light needs to give `lux` at `distance_cm` (inverse square law), on a surface turned
    `incidence_deg` away from it (cosine law)."""
    d = distance_cm / 100.0
    return lux * d * d / max(math.cos(math.radians(incidence_deg)), 1e-3)


def lux_from_candelas(cd: float, distance_cm: float, incidence_deg: float = 0.0) -> float:
    d = max(distance_cm / 100.0, 1e-3)
    return cd * max(math.cos(math.radians(incidence_deg)), 0.0) / (d * d)


def spot_falloff(angle_deg: float, inner_deg: float, outer_deg: float) -> float:
    """Unreal's spot cone attenuation: 1 inside the inner cone, smoothly to 0 at the outer (a squared linear ramp in
    cosine, as the deferred shader's SpotAttenuation)."""
    if angle_deg >= outer_deg:
        return 0.0
    co, ci = math.cos(math.radians(outer_deg)), math.cos(math.radians(max(min(inner_deg, outer_deg - 1e-3), 0.0)))
    t = (math.cos(math.radians(angle_deg)) - co) / max(ci - co, 1e-6)
    t = max(0.0, min(1.0, t))
    return t * t


def inverse_square_falloff(distance_cm: float, radius_cm: float) -> float:
    """Unreal's inverse-squared attenuation window near the attenuation radius: (1 - (d/r)^4)^2, clamped."""
    if radius_cm <= 0:
        return 1.0
    x = min(distance_cm / radius_cm, 1.0)
    return max(0.0, 1.0 - x ** 4) ** 2


# --------------------------------------------------------------------------------------- Unreal exposure (post)
# PostProcessEyeAdaptation.cpp (API_NOTES: exposure): at the default r.EyeAdaptation.LensAttenuation 0.78 the luminance
# scale LuminanceMax is 1, and in AEM_Manual the exposure multiplies scene luminance by 2^(AutoExposureBias - EVcam),
# EVcam = log2(N^2 * ShutterSpeed * 100 / ISO) when AutoExposureApplyPhysicalCameraExposure is on, else 0. A cine camera
# writes its own aperture into DepthOfFieldFstop (CineCameraComponent.cpp:709), so with physical exposure on a change
# of aperture changes brightness: the "manual" mode here turns it off and the bias alone sets the exposure.
# Calibration: a reflected meter reading EV100 e sees a luminance 0.125 * 2^e; exposing it to middle grey (0.18 before
# the tone curve) needs 2^bias = 0.18 / (0.125 * 2^e), so bias = UE_EV_OFFSET - e. Unreal's own "EV100" (the auto
# exposure min/max brightness with the extended luminance range on: white point 2^EV, average 0.18 x that) is the
# photographic EV100 minus the same offset.
UE_EV_OFFSET = math.log2(MIDDLE_GREY / (K_REFLECTED / 100.0))  # 0.526


def ue_manual_bias_for_ev100(ev100: float) -> float:
    """AutoExposureBias for AEM_Manual with physical camera exposure OFF that exposes a scene metering `ev100`."""
    return round(UE_EV_OFFSET - ev100, 4)


def ev100_for_ue_manual_bias(bias: float) -> float:
    return round(UE_EV_OFFSET - bias, 4)


def ue_ev100(ev100: float) -> float:
    """Photographic EV100 -> Unreal's EV100 (AutoExposureMin/MaxBrightness with the extended luminance range)."""
    return round(ev100 - UE_EV_OFFSET, 4)


def ev100_from_ue(ue_ev: float) -> float:
    return round(ue_ev + UE_EV_OFFSET, 4)


def ue_physical_ev100(fstop: float, shutter_speed: float, iso: float) -> float:
    """Unreal's EVcam for physical camera exposure; `shutter_speed` is in 1/s as Unreal stores it (60 = 1/60 s)."""
    return math.log2(fstop * fstop * shutter_speed * 100.0 / max(1.0, iso))


def ue_exposure_scale(bias: float, physical_ev100: float = 0.0) -> float:
    """What AEM_Manual multiplies scene luminance by before the tone curve."""
    return 2.0 ** (bias - physical_ev100)


# --------------------------------------------------------------------------------------------- colour temperature

def kelvin_to_rgb(kelvin: float) -> tuple:
    """An approximate linear-light sRGB colour (max channel 1) of a black body at `kelvin` (1000-40000 K), after
    Tanner Helland's fit, converted from display to linear: for display swatches and colour checks; Unreal lights take
    the temperature itself (use_temperature)."""
    t = max(1000.0, min(40000.0, kelvin)) / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        r = 329.698727446 * (t - 60) ** -0.1332047592
        g = 288.1221695283 * (t - 60) ** -0.0755148492
        b = 255.0
    srgb = [max(0.0, min(255.0, c)) / 255.0 for c in (r, g, b)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    m = max(lin)
    return tuple(round(c / m, 4) for c in lin)


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    c = max(0.0, c)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def luma(rgb) -> float:
    """Rec.709 relative luminance of linear RGB."""
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
