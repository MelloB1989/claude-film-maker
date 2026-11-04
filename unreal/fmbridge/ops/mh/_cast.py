"""MetaHuman variations (B47): N distinct, plausible `character` specs from one seed and a few ranges, for background
extras. Pure Python (no `unreal`): the editor op mh.variants and the client's `cast` spec kind
(tools/filmtools/unreal/mh_cast.py) both run this file.

Deterministic: member i is drawn from its own generator seeded "<seed>:<i>:<attempt>", so the same seed always gives
the same cast, and raising `count` keeps the first members as they were. Distinct: a candidate too close to an earlier
member (in a normalised space of face blend, body, skin tone, hair colour) is redrawn, up to `max_attempts`.

Age has no MetaHuman parameter: it is mapped by rule of thumb onto what does exist (grey hair/brows from ~35 on,
teeth worn down and gums receding from ~50, a little rougher skin). Judge the contact sheet.

    kind: cast
    version: 1
    name: cafe-extras
    seed: 7
    count: 6
    folder: /Game/Characters/Extras        # members are <folder>/MH_<prefix><NN>
    prefix: Extra
    presets: {female: [Ada, Vivian], male: [Jorge, Trey]}   # or one list
    sex: any                               # any | female | male | a share of female, e.g. 0.5
    age: [22, 70]                          # years
    height_cm: {female: [155, 178], male: [165, 192]}       # or one range
    fat: [-2, 1.5]
    muscularity: [-1, 1.2]
    skin_tone: {u: [0.15, 0.85], v: [0.3, 0.65]}
    hair: {female: [WI_Hair_L_Straight, ...], male: [WI_Hair_S_BuzzCut, ...], melanin: [0.1, 1.0], redness: [0, 0.4]}
    beard: {chance: 0.35, items: [WI_Beard_S_Stubble]}      # men only
    outfits: [WI_Outfit_Casual, ...]
    eyes: {u: [0.05, 0.95], v: [0.2, 0.8], patterns: [Iris001, Iris002, Iris003]}
    rig: full                              # passed to every member (none: shape only)
    build: true
"""
from __future__ import annotations

import math
import random

DEFAULTS = {
    "count": 4, "prefix": "Extra", "sex": "any", "age": [20, 70], "fat": [-2.0, 1.5], "muscularity": [-1.0, 1.0],
    "skin_tone": {"u": [0.1, 0.9], "v": [0.25, 0.7]},
    "eyes": {"u": [0.05, 0.95], "v": [0.2, 0.8], "patterns": ["Iris001", "Iris002", "Iris003", "Iris004", "Iris005"]},
    "min_distance": 0.35, "max_attempts": 40, "rig": "full", "build": True,
}
HEIGHT = {"female": [155.0, 178.0], "male": [165.0, 192.0]}
SEX_AXIS = {"female": [0.8, 2.2], "male": [-2.2, -0.8]}  # Creator's Masculine/Feminine constraint


class CastError(ValueError):
    """A bad cast spec (the op turns it into an OpError bad_args)."""


def _rng(lo_hi, r: random.Random, what: str) -> float:
    if isinstance(lo_hi, (int, float)):
        return float(lo_hi)
    if not (isinstance(lo_hi, (list, tuple)) and len(lo_hi) == 2):
        raise CastError(f"{what}: a range is [low, high] or one number, not {lo_hi!r}")
    lo, hi = float(lo_hi[0]), float(lo_hi[1])
    if hi < lo:
        raise CastError(f"{what}: [low, high] with low <= high, not {lo_hi!r}")
    return lo + (hi - lo) * r.random()


def _by_sex(v, sex: str, what: str):
    """A value given per sex ({female: ..., male: ...}) or for all."""
    if isinstance(v, dict) and ("female" in v or "male" in v):
        if sex not in v:
            raise CastError(f"{what}: no entry for {sex}")
        return v[sex]
    return v


def _pool(v, sex: str, what: str) -> list:
    v = _by_sex(v, sex, what)
    if isinstance(v, str):
        v = [v]
    if not v:
        raise CastError(f"{what}: an empty pool")
    return list(v)


def _sex(spec: dict, r: random.Random) -> str:
    s = spec.get("sex", "any")
    if s in ("female", "male"):
        return s
    try:
        share = 0.5 if s == "any" else float(s)
    except (TypeError, ValueError):
        share = -1.0
    if not 0 <= share <= 1:
        raise CastError(f"sex: any, female, male or a share of female 0..1, not {s!r}")
    return "female" if r.random() < share else "male"


def draw(spec: dict, i: int, attempt: int) -> dict:
    """One candidate's traits (plain numbers and names) for member i."""
    r = random.Random(f"{spec['seed']}:{i}:{attempt}")
    sex = _sex(spec, r)
    presets = _pool(spec.get("presets") or [], sex, "presets")
    a = r.choice(presets)
    others = [p for p in presets if p != a]
    b = r.choice(others) if others else a
    w = round(0.5 + 0.4 * r.random(), 3)  # the main face 50..90 %
    age = _rng(spec.get("age", DEFAULTS["age"]), r, "age")
    t = {
        "sex": sex, "age": round(age, 1), "face": {a: w, b: round(1 - w, 3)} if b != a else {a: 1.0},
        "height": round(_rng(_by_sex(spec.get("height_cm", HEIGHT), sex, "height_cm"), r, "height_cm"), 1),
        "fat": round(_rng(spec.get("fat", DEFAULTS["fat"]), r, "fat"), 2),
        "muscularity": round(_rng(spec.get("muscularity", DEFAULTS["muscularity"]), r, "muscularity"), 2),
        "masfem": round(_rng(SEX_AXIS[sex], r, "sex"), 2),
        "face_pos": round(presets.index(a) / max(1, len(presets) - 1), 3),  # which base face, for distinctness
    }
    tone = spec.get("skin_tone", DEFAULTS["skin_tone"])
    t["skin_u"] = round(_rng(tone.get("u", [0.1, 0.9]), r, "skin_tone.u"), 3)
    t["skin_v"] = round(_rng(tone.get("v", [0.25, 0.7]), r, "skin_tone.v"), 3)
    eyes = {**DEFAULTS["eyes"], **(spec.get("eyes") or {})}
    t["eye_u"] = round(_rng(eyes["u"], r, "eyes.u"), 3)
    t["eye_v"] = round(_rng(eyes["v"], r, "eyes.v"), 3)
    t["iris"] = r.choice(list(eyes["patterns"]))
    hair = spec.get("hair") or {}
    items = _by_sex({k: v for k, v in hair.items() if k in ("female", "male")} or hair.get("items") or [], sex,
                    "hair") if hair else []
    t["hair"] = r.choice(list(items)) if items else ""
    t["melanin"] = round(_rng(hair.get("melanin", [0.1, 1.0]), r, "hair.melanin"), 3)
    t["redness"] = round(_rng(hair.get("redness", [0.0, 0.35]), r, "hair.redness"), 3)
    beard = spec.get("beard") or {}
    t["beard"] = ""
    if sex == "male" and beard.get("items") and r.random() < float(beard.get("chance", 0.3)):
        t["beard"] = r.choice(list(beard["items"]))
    outfits = spec.get("outfits") or []
    t["outfit"] = r.choice(list(_pool(outfits, sex, "outfits"))) if outfits else ""
    return t


def age_look(age: float) -> dict:
    """Rule-of-thumb ageing onto parameters MetaHuman has (not an age model)."""
    grey = min(1.0, max(0.0, (age - 35.0) / 40.0))
    worn = min(1.0, max(0.0, (age - 45.0) / 40.0))
    return {"whiteness": round(grey ** 1.5 * 0.9, 3), "worn_down": round(worn * 0.6, 3),
            "receding_gums": round(worn * 0.5, 3), "roughness": round(1.02 + 0.08 * worn, 3)}


def vector(t: dict) -> list:
    """A trait set as a point in a 0..1-ish space for distinctness (face blend, sex, body, tone, hair, eyes)."""
    return [t["masfem"] / 4.4 + 0.5, (t["height"] - 150) / 45, (t["fat"] + 3) / 6, (t["muscularity"] + 3) / 6,
            t["skin_u"], t["skin_v"], t["melanin"], t["redness"], t["age"] / 90, t["eye_u"] * 0.5, t["face_pos"]]


def distance(a: dict, b: dict) -> float:
    va, vb = vector(a), vector(b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(va, vb)))


def member_spec(spec: dict, i: int, t: dict) -> dict:
    """The `character` spec of member i with traits t."""
    folder = spec["folder"].rstrip("/")
    name = f"{spec.get('prefix', DEFAULTS['prefix'])}{i + 1:02d}"
    look = age_look(t["age"])
    out = {
        "kind": "character", "version": 1, "name": name, "asset": f"{folder}/MH_{name}",
        "description": f"{spec.get('name', 'cast')} member {i + 1}: {t['sex']}, ~{t['age']:.0f}",
        "from": {"preset": max(t["face"].items(), key=lambda kv: kv[1])[0]},
        "face": {"blend": t["face"]} if len(t["face"]) > 1 else {},
        "body": {"Height": t["height"], "Fat": t["fat"], "Muscularity": t["muscularity"],
                 "Masculine/Feminine": t["masfem"]},
        "skin": {"u": t["skin_u"], "v": t["skin_v"], "roughness": look["roughness"]},
        "eyes": {"both": {"iris": {"iris_pattern": t["iris"], "primary_color_u": t["eye_u"],
                                   "primary_color_v": t["eye_v"]}}},
        "teeth": {"worn_down": look["worn_down"], "receding_gums": look["receding_gums"]},
        "grooms": {"Eyebrows": {"melanin": t["melanin"], "redness": t["redness"],
                                "params": {"Whiteness": look["whiteness"]}}},
        "rig": spec.get("rig", DEFAULTS["rig"]),
    }
    if not out["face"]:
        del out["face"]
    if t["hair"]:
        out["grooms"]["Hair"] = {"item": t["hair"], "melanin": t["melanin"], "redness": t["redness"],
                                 "params": {"Whiteness": look["whiteness"]}}
    if (spec.get("beard") or {}).get("items"):  # a cast with beards: everyone else is clean-shaven
        out["grooms"]["Beard"] = ({"item": t["beard"], "melanin": t["melanin"], "redness": t["redness"],
                                   "params": {"Whiteness": look["whiteness"]}} if t["beard"] else "none")
    if t["outfit"]:
        out["outfit"] = {"item": t["outfit"]}
    if out["rig"] == "none":
        out["build"] = False
    elif spec.get("build", True) is False:
        out["build"] = False
    else:
        out["build"] = {"name": name, **(spec["build"] if isinstance(spec.get("build"), dict) else {})}
    return out


def validate(spec: dict) -> dict:
    s = {**DEFAULTS, **spec}
    for k in ("seed", "folder", "presets"):
        if k not in spec:
            raise CastError(f"a cast needs `{k}`")
    if not str(s["folder"]).startswith("/Game/"):
        raise CastError(f"folder must be a /Game/ path, not {s['folder']!r}")
    if not 1 <= int(s["count"]) <= 200:
        raise CastError(f"count 1..200, not {s['count']!r}")
    return s


def generate(spec: dict) -> dict:
    """The cast: {"members": [character specs], "traits": [per member], "distances": [nearest earlier member],
    "attempts": [per member]}. Same seed, same cast; a larger count keeps the first members."""
    s = validate(spec)
    traits, members, nearest, attempts = [], [], [], []
    for i in range(int(s["count"])):
        best, best_d, used = None, -1.0, 0
        for attempt in range(int(s["max_attempts"])):
            used = attempt + 1
            t = draw(s, i, attempt)
            d = min((distance(t, o) for o in traits), default=float("inf"))
            if d > best_d:
                best, best_d = t, d
            if d >= float(s["min_distance"]):
                break
        traits.append(best)
        members.append(member_spec(s, i, best))
        nearest.append(None if best_d == float("inf") else round(best_d, 3))
        attempts.append(used)
    return {"members": members, "traits": traits, "distances": nearest, "attempts": attempts}
