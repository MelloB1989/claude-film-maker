"""Shot grammar in words, both ways: "medium close-up of Host from 30 degrees left at eye level on a 50mm" becomes
the framing solver's arguments (`parse`), and any camera is described back in the same words (`describe`):
"MCU of Host from 3/4 left (41 deg), eye level, 50 mm f/2.8".

Vocabulary (case-insensitive, any order):
- size: extreme close-up/ECU/choker, close-up/CU, medium close-up/MCU, medium shot/mid shot/MS/waist shot,
  cowboy/american, medium wide/medium long/MWS/MLS/knee shot, wide/full/long shot/WS/FS/LS, extreme wide/
  establishing/EWS/ELS; "two-shot" (a group of the named subjects, MS unless a size is given).
- subjects: the known names found in the text (actor labels or spec subject names), in order.
- angle: front/frontal/head-on, 1/4, 3/4/three-quarter, profile/side, 3/4 back, back/behind, or "<n> deg|degrees|°".
- side: left/right, the subject's own ("from her left" = the camera on her left).
- height: eye level, slightly high/low, high/low (angle), overhead/bird's eye/top down, worm's eye, ground level,
  hip/chest/shoulder/knee level/height.
- lens: "<n>mm" (focal), "<n> m|cm away|from" (distance: the focal length is solved), f/<n> or T<n> (aperture).
- composition: centered, left third, right third; "dutch" [n deg] (default 12).
"""
from __future__ import annotations

import math
import re

from . import framing, geo, lens

SIZE_WORDS = [  # longest first
    (r"extreme\s+close[\s-]*up|\becu\b|\bxcu\b|\bbcu\b|\bchoker\b", "ECU"),
    (r"medium\s+close[\s-]*up|\bmcu\b|\bmcs\b", "MCU"),
    (r"extreme\s+wide|extreme\s+long|establishing|\bews\b|\bels\b|\bxws\b", "EWS"),
    (r"medium\s+wide|medium\s+long|\bmws\b|\bmls\b|knee\s+shot", "MWS"),
    (r"cowboy|american\s+shot|\bamerican\b", "COWBOY"),
    (r"close[\s-]*up|\bcu\b|\bclose\b", "CU"),
    (r"medium\s+shot|mid\s+shot|waist\s+shot|\bms\b|\bmedium\b", "MS"),
    (r"wide\s+shot|full\s+shot|long\s+shot|\bwide\b|\bfull\b|\bws\b|\bfs\b|\bls\b", "WS"),
]
ANGLE_WORDS = [
    (r"3/4\s+back|three[\s-]*quarter\s+back|back\s+3/4", 135.0),
    (r"\b1/4\b|quarter\s+angle", 22.5),
    (r"3/4|three[\s-]*quarters?", 45.0),
    (r"\bprofile\b|\bside\s+on\b|from\s+the\s+side", 90.0),
    (r"\bfrom\s+behind\b|\bback\s+of\b|\brear\b|\bbehind\b", 180.0),
    (r"\bfrontal\b|\bhead[\s-]*on\b|\bfront\b|\bstraight\s+on\b", 0.0),
]
HEIGHT_WORDS = [
    (r"bird'?s?[\s-]*eye|overhead|top[\s-]*down", "overhead"),
    (r"worm'?s?[\s-]*eye", "worm"),
    (r"slight(?:ly)?\s+high", "slight high"),
    (r"slight(?:ly)?\s+low", "slight low"),
    (r"\bhigh(?:\s+angle)?\b", "high"),
    (r"\blow(?:\s+angle)?\b", "low"),
    (r"ground\s+level|from\s+the\s+(?:floor|ground)", "ground"),
    (r"(?:hip|waist)\s+(?:level|height)|from\s+the\s+hip", "hip"),
    (r"chest\s+(?:level|height)", "chest"),
    (r"shoulder\s+(?:level|height)", "shoulder"),
    (r"knee\s+(?:level|height)", "knee"),
    (r"eye[\s-]*level|eye\s+height", "eye"),
]


def parse(text: str, names=()) -> dict:
    """The solver's arguments from a sentence: {"subjects", "size", "angle", "side", "height", "focal_mm",
    "distance_cm", "aperture", "place", "dutch_deg", "unparsed"} (keys only for what the text says; "unparsed" lists
    the words nothing understood, so a caller can say what it ignored)."""
    t = " " + str(text).lower().replace("°", " deg ").replace("degrees", "deg").replace("degree", "deg") + " "
    used = []

    def take(m):
        used.append(m.span())
        return m

    def find(pat):
        """The first match of `pat` that overlaps nothing already understood."""
        for m in re.finditer(pat, t):
            if not any(a < m.end() and m.start() < b for a, b in used):
                return m
        return None

    out: dict = {}
    m = find(r"dutch(?:\s+angle)?(?:\s+(-?\d+(?:\.\d+)?)\s*(?:deg)?)?")
    if m:
        out["dutch_deg"] = float(m.group(1)) if m.group(1) else 12.0
        take(m)
    for pat, key in SIZE_WORDS:
        m = find(pat)
        if m:
            out["size"] = key
            take(m)
            break
    m = find(r"(\d+(?:\.\d+)?)\s*deg\s+(above|below)\s+(?:the\s+)?eyes?(?:[\s-]*(?:level|line))?")
    if m:
        out["height"] = float(m.group(1)) * (1 if m.group(2) == "above" else -1)
        take(m)
    two = find(r"two[\s-]*shot|\b2[\s-]*shot|group\s+shot")
    if two:
        take(two)
        out.setdefault("size", "MS")
        out["group"] = True
    m = find(r"(-?\d+(?:\.\d+)?)\s*deg(?:rees)?")
    if m:
        out["angle"] = abs(float(m.group(1)))
        take(m)
    else:
        for pat, a in ANGLE_WORDS:
            m = find(pat)
            if m:
                out["angle"] = a
                take(m)
                break
    m = find(r"\b(left|right)\b(?!\s+third)")
    if m:
        out["side"] = m.group(1)
        take(m)
    for pat, h in HEIGHT_WORDS if "height" not in out else ():
        m = find(pat)
        if m:
            out["height"] = h
            take(m)
            break
    m = find(r"(\d+(?:\.\d+)?)\s*mm\b")
    if m:
        out["focal_mm"] = float(m.group(1))
        take(m)
    m = find(r"(\d+(?:\.\d+)?)\s*(cm|m|meters?|metres?)\s*(?:away|back|from|off)")
    if m:
        v = float(m.group(1))
        out["distance_cm"] = v if m.group(2) == "cm" else v * 100.0
        take(m)
    m = find(r"\bf\s*/?\s*(\d+(?:\.\d+)?)|\bt\s*(\d+(?:\.\d+)?)\b")
    if m:
        out["aperture"] = float(m.group(1) or m.group(2))
        take(m)
    m = find(r"\b(centered|centred|center|centre|middle)\b")
    if m:
        out["place"] = "center"
        take(m)
    m = find(r"\b(left|right)\s+third\b")
    if m:
        out["place"] = f"{m.group(1)} third"
        take(m)
    found = []
    for n in sorted(set(names), key=len, reverse=True):
        for m in re.finditer(r"(?<![\w])" + re.escape(str(n).lower()) + r"(?![\w])", t):
            if not any(a <= m.start() < b for a, b in used):
                found.append((m.start(), n))
                take(m)
    found.sort()
    if found:
        out["subjects"] = list(dict.fromkeys(n for _, n in found))
    leftover = t
    for a, b in sorted(used, reverse=True):
        leftover = leftover[:a] + " " + leftover[b:]
    filler = {"of", "from", "at", "on", "a", "an", "the", "with", "and", "her", "his", "their", "its", "him",
              "shot", "lens", "angle", "level", "camera", "to", "in", "framed", "frame", "s", "side", "by", "away"}
    out["unparsed"] = [w for w in re.findall(r"[a-z0-9/']+", leftover) if w not in filler]
    return out


def solver_args(parsed: dict) -> dict:
    """parse()'s result as framing.solve's keyword arguments (subjects aside)."""
    a = {k: parsed[k] for k in ("size", "angle", "side", "height", "place") if k in parsed}
    if "dutch_deg" in parsed:
        a["dutch"] = parsed["dutch_deg"]
    if "aperture" in parsed:
        a["aperture"] = parsed["aperture"]
    if "distance_cm" in parsed:
        a["distance"] = parsed["distance_cm"]
        a["focal"] = parsed.get("focal_mm")  # None: the focal length is solved
    elif "focal_mm" in parsed:
        a["focal"] = parsed["focal_mm"]
    return a


ANGLE_NAMES = ((12.0, "front"), (33.0, "1/4"), (67.0, "3/4"), (112.0, "profile"), (157.0, "3/4 back"),
               (181.0, "back"))


def angle_name(deg: float) -> str:
    for lim, name in ANGLE_NAMES:
        if deg < lim:
            return name
    return "back"


PRESET_ELEV = {"eye level": 0.0, "slightly high": 10.0, "slightly low": -10.0, "high angle": 20.0, "low angle": -20.0,
               "overhead": 75.0, "worm's eye": -45.0}


def height_name(elev: float, exact: bool = True) -> str:
    """The height in words: a preset name when the elevation is within 1.5 deg of it (or `exact` False: the nearest
    band), else "<n> deg above|below eye level" (which parse() reads back exactly)."""
    for name, e in PRESET_ELEV.items():
        if abs(elev - e) <= 1.5:
            return name
    if exact:
        return f"{abs(elev):.0f} deg {'above' if elev > 0 else 'below'} eye level"
    if abs(elev) < 4:
        return "eye level"
    if elev >= 55:
        return "overhead"
    if elev <= -35:
        return "worm's eye"
    if abs(elev) < 12:
        return "slightly " + ("high" if elev > 0 else "low")
    return "high angle" if elev > 0 else "low angle"


def relation(cam: dict, subject: dict) -> dict:
    """Where a camera stands relative to a subject: the angle around from its front (0..180) toward which of its
    sides, and the elevation seen from its eyes (degrees)."""
    e = geo.v(subject["points"]["eyes"])
    d = geo.sub(geo.v(cam["loc"]), e)
    yaw_cam = geo.yaw_of(d)
    delta = geo.wrap180(geo.yaw_of(subject["facing"]) - yaw_cam)  # + = toward the subject's left
    elev = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
    return {"angle": abs(delta), "side": "left" if delta > 0 else "right", "elevation": elev,
            "distance": math.hypot(d[0], d[1])}


def describe(cam: dict, subjects) -> str:
    """A camera in shot grammar: "MCU of Host from 3/4 left (41 deg), eye level, 50 mm f/2.8" (several subjects:
    "two-shot (MS) of A and B ..."). The size is measured on the first subject (framing.classify)."""
    subs = subjects if isinstance(subjects, (list, tuple)) else [subjects]
    s = subs[0]
    size = framing.classify(cam, s)["size"] or "?"
    rel = relation(cam, s)
    names = " and ".join(x["name"] for x in subs)
    what = f"two-shot ({size})" if len(subs) == 2 else (f"group shot ({size})" if len(subs) > 2 else size)
    a = angle_name(rel["angle"])
    ang = f"from {a}" if a in ("front", "back") else f"from {a} {rel['side']}"
    ang += f" ({rel['angle']:.0f} deg)"
    parts = [f"{what} of {names} {ang}", height_name(rel["elevation"]), f"{cam['focal']:.0f} mm"]
    if cam.get("aperture"):
        parts[-1] += f" f/{cam['aperture']:g}"
    roll = geo.wrap180(geo.as_rot(cam["rot"])["roll"])
    if abs(roll) >= 3:
        parts.append(f"dutch {roll:.0f} deg")
    p = lens.project(cam, s["points"]["eyes"])
    if p["depth"] > 0 and len(subs) == 1:
        if abs(p["u"] - 0.5) < 0.08:
            parts.append("centered")
        elif abs(p["u"] - 1 / 3) < 0.08:
            parts.append("left third")
        elif abs(p["u"] - 2 / 3) < 0.08:
            parts.append("right third")
    return ", ".join(parts)
