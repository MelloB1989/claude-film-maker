"""The sun: its position for a place, a date and a local time (NOAA's solar calculator), named times of day, and how to
point Unreal's directional light at it.

Conventions. Compass azimuth is degrees clockwise from geographic north (90 = east). Elevation is degrees above the
horizon. In the level, `north_yaw` is the Unreal yaw (degrees) of geographic north: 0 puts north along +X. Unreal is
left-handed with Z up, so seen from above yaw turns from +X towards +Y, clockwise like a compass: the sun's direction
(from the scene towards the sun) has yaw `north_yaw + azimuth`, and the directional light, which points the way the
light travels, gets pitch `-elevation` and yaw `north_yaw + azimuth + 180`.
"""
from __future__ import annotations

import datetime as _dt
import math

# named times of day: the sun's elevation (deg) and whether it is the morning (rising) or the evening (setting) one
TIMES = {
    "night": (-20.0, "evening"),         # astronomical night: moon and stars
    "dusk": (-9.0, "evening"),           # nautical twilight: deep blue, last light on the horizon
    "blue_hour": (-5.0, "evening"),      # civil twilight: even blue light, no shadows
    "sunset": (0.5, "evening"),
    "golden_evening": (6.0, "evening"),  # low warm sun, long shadows
    "afternoon": (35.0, "evening"),
    "noon": (90.0, "noon"),              # as high as it gets that day
    "morning": (30.0, "morning"),
    "golden_morning": (6.0, "morning"),
    "sunrise": (0.5, "morning"),
    "dawn": (-5.0, "morning"),
}
# a nominal compass azimuth for each when no place is given: morning sun in the east, evening in the west
NOMINAL_AZIMUTH = {"morning": 100.0, "noon": 180.0, "evening": 260.0}

SOLAR_LUX = 120000.0  # the sun above the atmosphere, as Unreal's SkyAtmosphere expects it (it applies transmittance)


def _jd(date: _dt.date, hours_utc: float) -> float:
    y, m, d = date.year, date.month, date.day
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5 + hours_utc / 24.0


def position(lat: float, lon: float, date, hour: float, tz: float = 0.0, refraction: bool = True) -> dict:
    """The sun at latitude `lat`, longitude `lon` (east positive), on `date` (a date or "YYYY-MM-DD") at local `hour`
    (decimal hours, e.g. 16.5) in time zone `tz` (hours east of UTC). Returns {"elevation", "azimuth"} in degrees
    (compass azimuth, clockwise from north) and the solar noon, sunrise and sunset in local decimal hours (None at
    polar day/night)."""
    if isinstance(date, str):
        date = _dt.date.fromisoformat(date)
    jd = _jd(date, hour - tz)
    t = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    mr = math.radians(m)
    c = (math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t)) + math.sin(2 * mr) * (0.019993 - 0.000101 * t)
         + math.sin(3 * mr) * 0.000289)
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    eps0 = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))
    decl = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(app_long))))
    yv = math.tan(math.radians(eps / 2)) ** 2
    l0r = math.radians(l0)
    eq_time = 4 * math.degrees(yv * math.sin(2 * l0r) - 2 * e * math.sin(mr) + 4 * e * yv * math.sin(mr) * math.cos(2 * l0r)
                               - 0.5 * yv * yv * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * mr))  # minutes
    true_solar_min = (hour * 60.0 + eq_time + 4 * lon - 60 * tz) % 1440.0
    ha = true_solar_min / 4.0 - 180.0 if true_solar_min / 4.0 >= 0 else true_solar_min / 4.0 + 180.0
    latr, declr = math.radians(lat), math.radians(decl)
    cos_zen = math.sin(latr) * math.sin(declr) + math.cos(latr) * math.cos(declr) * math.cos(math.radians(ha))
    zen = math.degrees(math.acos(max(-1.0, min(1.0, cos_zen))))
    elev = 90.0 - zen
    if refraction and elev > -0.575:
        te = math.tan(math.radians(elev))
        if elev > 85:
            r = 0.0
        elif elev > 5:
            r = 58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5
        else:
            r = 1735 + elev * (-518.2 + elev * (103.4 + elev * (-12.79 + elev * 0.711)))
        elev += r / 3600.0
    sz = math.sin(math.radians(zen))
    if abs(sz) < 1e-9 or abs(math.cos(latr)) < 1e-9:
        az = 180.0 if lat > decl else 0.0
    else:
        ca = (math.sin(latr) * math.cos(math.radians(zen)) - math.sin(declr)) / (math.cos(latr) * sz)
        a = math.degrees(math.acos(max(-1.0, min(1.0, ca))))
        az = (a + 180.0) % 360.0 if ha > 0 else (540.0 - a) % 360.0
    noon = (720.0 - 4 * lon - eq_time + tz * 60.0) / 60.0
    cos_ha0 = (math.cos(math.radians(90.833)) / (math.cos(latr) * math.cos(declr)) - math.tan(latr) * math.tan(declr))
    if -1.0 <= cos_ha0 <= 1.0:
        ha0 = math.degrees(math.acos(cos_ha0))
        rise, sett = noon - ha0 * 4 / 60.0, noon + ha0 * 4 / 60.0
    else:
        rise = sett = None
    return {"elevation": round(elev, 4), "azimuth": round(az, 4), "declination": round(decl, 4),
            "solar_noon": round(noon % 24, 4), "sunrise": None if rise is None else round(rise % 24, 4),
            "sunset": None if sett is None else round(sett % 24, 4)}


def time_for(name_or_elevation, lat: float, lon: float, date, tz: float = 0.0, which: str = "") -> float:
    """The local decimal hour when the sun reaches a named time of day (TIMES) or an elevation, on the morning or the
    evening side (`which`: morning/evening; a name brings its own). "noon" is the solar noon. Raises ValueError when the
    sun never gets there that day (polar day/night, or higher than the day's noon)."""
    if isinstance(name_or_elevation, str):
        if name_or_elevation not in TIMES:
            raise ValueError(f"unknown time of day {name_or_elevation!r}; one of {sorted(TIMES)} or an hour like '16:30'")
        target, side = TIMES[name_or_elevation]
        which = which or side
    else:
        target, which = float(name_or_elevation), which or "evening"
    noon = position(lat, lon, date, 12.0, tz)["solar_noon"]
    top = position(lat, lon, date, noon, tz)["elevation"]
    if which == "noon":
        return noon
    if target > top:
        raise ValueError(f"the sun only reaches {top:.1f} deg on {date} at lat {lat}; asked for {target} deg")
    lo, hi = (noon - 12.0, noon) if which == "morning" else (noon, noon + 12.0)
    f = (lambda h: position(lat, lon, date, h, tz)["elevation"] - target)
    if which == "morning":  # rising: f goes - to +
        if f(lo) > 0:
            raise ValueError(f"the sun never goes below {target} deg on {date} at lat {lat} (polar day)")
    elif f(hi) > 0:
        raise ValueError(f"the sun never goes below {target} deg on {date} at lat {lat} (polar day)")
    for _ in range(60):
        mid = (lo + hi) / 2
        if (f(mid) < 0) == (which == "morning"):
            lo = mid
        else:
            hi = mid
    return round(((lo + hi) / 2) % 24, 4)


def parse_hour(v) -> float:
    """'16:30' / '16:30:15' / 16.5 to decimal hours."""
    if isinstance(v, (int, float)):
        return float(v)
    parts = [float(p) for p in str(v).split(":")]
    return parts[0] + (parts[1] if len(parts) > 1 else 0) / 60 + (parts[2] if len(parts) > 2 else 0) / 3600


def air_mass(elevation: float) -> float:
    """Kasten & Young (1989) relative optical air mass for a sun `elevation` degrees up (large near the horizon)."""
    if elevation <= -0.5:
        return float("inf")
    z = 90.0 - max(elevation, -0.5)
    return 1.0 / (math.cos(math.radians(z)) + 0.50572 * (96.07995 - z) ** -1.6364)


def direct_lux(elevation: float, turbidity: float = 0.21) -> float:
    """Clear-sky direct sun illuminance on a surface facing the sun (lux), from the air mass: for a sun light used
    WITHOUT a SkyAtmosphere (which would attenuate it itself). ~100 klx at noon, ~10 klx near 5 deg, 0 below."""
    m = air_mass(elevation)
    return 0.0 if math.isinf(m) else round(128000.0 * math.exp(-turbidity * m), 1)


def sun_kelvin(elevation: float) -> float:
    """The colour temperature of the direct sun at an elevation (no atmosphere simulation): 2000 K at the horizon,
    about 3500 K at 10 deg, 5000 K at 30 deg, 5800 K overhead."""
    if elevation <= 0:
        return 2000.0
    pts = [(0, 2000), (3, 2600), (6, 3000), (10, 3500), (20, 4500), (30, 5000), (45, 5500), (90, 5800)]
    for (e0, k0), (e1, k1) in zip(pts, pts[1:]):
        if elevation <= e1:
            return round(k0 + (k1 - k0) * (elevation - e0) / (e1 - e0), 1)
    return 5800.0


def light_rotation(elevation: float, azimuth: float, north_yaw: float = 0.0) -> dict:
    """The directional light's rotation for a sun at `elevation` and compass `azimuth`: {"pitch", "yaw", "roll"}."""
    return {"pitch": -float(elevation), "yaw": round((north_yaw + azimuth + 180.0) % 360.0, 4), "roll": 0.0}


def from_rotation(pitch: float, yaw: float, north_yaw: float = 0.0) -> dict:
    """The inverse of light_rotation: the sun's elevation and compass azimuth from a directional light's rotation."""
    return {"elevation": round(-pitch, 4), "azimuth": round((yaw - 180.0 - north_yaw) % 360.0, 4)}


def resolve(spec: dict) -> dict:
    """A sun spec to {elevation, azimuth, hour?, source}. Accepts, in order of precedence:
    - {"elevation": deg, "azimuth": deg}  (compass azimuth),
    - {"time": "16:30" | 16.5 | "golden_evening", "lat", "lon", "date", "tz"}  (a place: NOAA),
    - {"time": "golden_evening", "azimuth"?: deg}  (no place: the named elevation, a nominal azimuth)."""
    spec = dict(spec or {})
    if "elevation" in spec:
        return {"elevation": float(spec["elevation"]), "azimuth": float(spec.get("azimuth", 180.0)), "source": "explicit"}
    t = spec.get("time", "afternoon")
    place = all(k in spec for k in ("lat", "lon"))
    if place:
        date = spec.get("date") or _dt.date.today().isoformat()
        tz = float(spec.get("tz", round(float(spec["lon"]) / 15.0)))
        if isinstance(t, str) and t in TIMES:
            hour = time_for(t, float(spec["lat"]), float(spec["lon"]), date, tz)
        else:
            hour = parse_hour(t)
        p = position(float(spec["lat"]), float(spec["lon"]), date, hour, tz)
        return {"elevation": p["elevation"], "azimuth": float(spec.get("azimuth", p["azimuth"])), "hour": round(hour, 4),
                "date": str(date), "sunrise": p["sunrise"], "sunset": p["sunset"], "source": "noaa"}
    if isinstance(t, str) and t in TIMES:
        elev, side = TIMES[t]
        if t == "noon":
            elev = 65.0
        return {"elevation": elev, "azimuth": float(spec.get("azimuth", NOMINAL_AZIMUTH[side])), "source": "named"}
    # an hour without a place: a symmetric day, sunrise 6:00, noon 12:00 at 60 deg, sunset 18:00
    h = parse_hour(t)
    elev = 60.0 * math.sin(math.pi * (h - 6.0) / 12.0) if 6.0 <= h <= 18.0 else -20.0
    az = 90.0 + (h - 6.0) * 15.0
    return {"elevation": round(elev, 4), "azimuth": float(spec.get("azimuth", az % 360)), "hour": h, "source": "nominal-day"}
