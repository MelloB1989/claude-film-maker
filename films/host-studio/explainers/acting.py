"""The explainers' acting sheet (round 7: performance): per VO line the emotion, intensity and lean, the face moments
(brow flashes, Duchenne smiles, nods, tilts, glances) and the gestures (type, hand, target, size), each pinned to an
exact word, resolved against the VO alignment (audio/<film>/cues.json) into seconds and sequence frames.

    python3 films/host-studio/explainers/acting.py            # -> acting/her.json + ACTING.md, and the checks

Re-run after any VO rebuild and every beat moves with the voice, like edl.py. Times are on the VO clock: t = 0 is
sequence frame 0 (frame = round(t * 24)). A word reference is (line, word[, occurrence][, stress]): `stress` is where
the stressed syllable sits as a fraction of the word (0 = its start), and the apex of a face move or the stroke of a
gesture lands there.

Timing conventions (agent-04 face, agent-01/agent-10 body):
- brow flash: rise 0.12 s before the apex, apex on the stressed syllable, 0.35-0.5 s total, back to the line's base;
- smile: onset 0.30 s before the apex, apex on the word, held `hold` s, then eases to the line's base smile;
- nod / tilt: apex on the stressed syllable (a nod is down-then-up, 0.35 s; a tilt holds until the next head move);
- gesture: preparation from `prep` s before the stroke (default 0.30), stroke on the stressed syllable, held `hold`
  s, then a retraction to a HIGH REST (hands up, elbows off the torso), not the desk, unless `rest` says so.

Staging (the operator's notes, R7_common.md): hands off the body and above the desk while she speaks; elbows out so
the upper arms clear the torso and breasts by >= 3 cm; the mic is on HER LEFT, so big gestures are her RIGHT hand, or
both hands in front of her sternum (inside her shoulder line), never past her left shoulder line; her left hand alone
only small and low. The graphic panel (CAM_MCU_L shots) is on frame right = HER LEFT: a deictic to it is her right hand
across the body, open palm, chest height, stopping ~15 cm left of her sternum (under the mic head, never into it),
with her head and eyes turning ~10 deg that way and straight back to the lens.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FPS = 24

ARC = {"hook": "curiosity", "body": "confident clarity", "payoff": "satisfied delight"}

# ------------------------------------------------------------------------------------------------ her: Netflix
# face moves: (kind, wordref, extra)   kinds: brow_flash | brow_one (side) | brow_hold | smile (duchenne, amount,
#   hold) | smile_soft | squint | nod | tilt (side, deg) | glance (dir, dur) | shake
# gestures:   (type, hand, wordref, extra)  types: beat | open_palm | count | deictic | size | press | carry | place
#   | point_viewer | pinch | ladder | sweep | release | chop | wave_off | raise_finger | high_low
HER = {
    "film": "netflix", "who": "her",
    "pre": {  # before the first word (t 0-0.75 s, on CAM_MCU)
        "note": "Already alive when the cut opens: a soft closed-mouth smile building, a small head tilt to her right "
                "(4 deg), an inhale with the shoulders rising 1 cm, hands up off the desk in a loose high rest "
                "(fingertips touching, forearms just off the desk edge, elbows out). A small lean in from 0.4 s.",
        "face": [("smile_soft", 0.15, {"amount": 0.35}), ("tilt", 0.2, {"side": "R", "deg": 4})],
        "lean": [(0.4, 4)],
    },
    "lines": {
        "N01": {
            "arc": "hook", "emotion": "curious, conspiratorial warmth: 'you'll like this'", "intensity": 0.75,
            "base": {"smile": 0.25, "brows": 0.1},
            "face": [("brow_flash", ("N01", "Netflix"), {}),
                     ("brow_one", ("N01", "over"), {"side": "R", "hold": 1.0, "note": "the conspiratorial one brow"}),
                     ("tilt", ("N01", "over"), {"side": "R", "deg": 6}),
                     ("nod", ("N01", "million"), {}),
                     ("smile", ("N01", "million"), {"amount": 0.7, "hold": 0.6}),
                     ("smile", ("N01", "members"), {"amount": 0.85, "hold": 0.5, "note": "full Duchenne: cheeks up, "
                                                                                          "eyes squint"})],
            "gestures": [
                ("open_palm", "R", ("N01", "Netflix"), {"size": "small", "target": "camera",
                                                        "note": "palm up and slightly out, chest height, presenting"}),
                ("size", "both", ("N01", "million"), {"start": ("N01", "three"), "size": "big", "target": "front",
                                                      "note": "hands start 15 cm apart in front of her sternum on "
                                                              "'three', spread to shoulder width on 'million': a huge "
                                                              "number; L hand stays below the mic"}),
                ("beat", "R", ("N01", "paying"), {"size": "small", "target": "camera"}),
            ],
            "lean": [(("N01", "over"), 7), (("N01", "members"), 4)],
        },
        "N02": {
            "arc": "hook", "emotion": "delight, easy confidence: the magic moment", "intensity": 0.8,
            "base": {"smile": 0.4, "brows": 0.1},
            "face": [("brow_flash", ("N02", "Hit"), {}),
                     ("smile", ("N02", "starts.", 1, 0.3), {"amount": 0.9, "hold": 0.6, "note": "Duchenne, squint"}),
                     ("nod", ("N02", "starts.", 1, 0.3), {})],
            "gestures": [
                ("press", "R", ("N02", "play,"), {"size": "small", "target": "camera",
                                                  "note": "index finger presses an imaginary play button toward the "
                                                          "lens, collarbone height so it enters the CU"}),
                ("release", "both", ("N02", "starts.", 1, 0.3), {"size": "medium", "target": "front",
                                                                "note": "fingers spring open outward, 'ta-da', "
                                                                        "shoulders lift"}),
            ],
            "lean": [(("N02", "Hit"), 6), (("N02", "starts."), 3)],
        },
        "N03": {
            "arc": "hook", "emotion": "intrigue, a twist", "intensity": 0.7,
            "base": {"smile": 0.15, "brows": 0.15},
            "face": [("brow_one", ("N03", "But"), {"side": "R", "hold": 0.8}),
                     ("shake", ("N03", "doesn't"), {"note": "a small head shake, 2 deg"}),
                     ("smile_soft", ("N03", "cloud."), {"amount": 0.5, "note": "a knowing half smile"})],
            "gestures": [
                ("raise_finger", "R", ("N03", "But"), {"size": "small", "target": "up", "note": "'wait a second'"}),
                ("wave_off", "R", ("N03", "cloud."), {"size": "medium", "target": "her right, up",
                                                      "note": "a light palm-down wave away to her right"}),
            ],
            "lean": [(("N03", "But"), 6), (("N03", "cloud."), 3)],
        },
        "N04": {
            "arc": "body", "emotion": "confident clarity with insider pride", "intensity": 0.7,
            "base": {"smile": 0.25, "brows": 0.05},
            "face": [("brow_flash", ("N04", "own"), {}),
                     ("nod", ("N04", "servers,"), {}),
                     ("smile", ("N04", "called"), {"amount": 0.55, "hold": 0.6}),
                     ("brow_flash", ("N04", "Open"), {}),
                     ("nod", ("N04", "Appliances.", 1, 0.35), {})],
            "gestures": [
                ("place", "both", ("N04", "builds"), {"size": "medium", "target": "front",
                                                      "note": "palms facing, shoulder width, setting a box down in "
                                                              "front of her on 'builds', firm on 'servers'"}),
                ("open_palm", "R", ("N04", "own"), {"size": "small", "target": "camera"}),
                ("beat", "R", ("N04", "Open"), {"size": "small", "target": "camera"}),
                ("beat", "R", ("N04", "Appliances.", 1, 0.35), {"size": "small", "target": "camera",
                                                               "note": "two descending beats, the naming"}),
            ],
            "lean": [(("N04", "own"), 6), (("N04", "Appliances."), 4)],
        },
        "N05": {
            "arc": "body", "emotion": "generous surprise", "intensity": 0.65, "off_cam": True,
            "base": {"smile": 0.3, "brows": 0.1},
            "face": [("brow_flash", ("N05", "free,"), {}), ("smile", ("N05", "free,"), {"amount": 0.7, "hold": 0.5}),
                     ("nod", ("N05", "networks.", 1, 0.3), {})],
            "gestures": [("open_palm", "R", ("N05", "free,"), {"size": "medium", "target": "camera",
                                                               "note": "offering"}),
                         ("sweep", "both", ("N05", "inside"), {"size": "medium", "target": "front",
                                                               "note": "hands circle a space in front of her"})],
            "lean": [(("N05", "free,"), 5)],
        },
        "N06": {
            "arc": "body", "emotion": "curious, clever: a neat trick", "intensity": 0.75,
            "base": {"smile": 0.3, "brows": 0.1},
            "face": [("brow_flash", ("N06", "Every"), {"note": "the bar names this one"}),
                     ("glance", ("N06", "Every"), {"dir": "up, her right", "dur": 0.45,
                                                   "note": "agent-04's THINK beat; back on the lens by 'Netflix'"}),
                     ("smile", ("N06", "predicts", 1, 0.3), {"amount": 0.6, "hold": 0.5, "note": "sly"}),
                     ("tilt", ("N06", "area"), {"side": "L", "deg": 5, "note": "toward the panel"}),
                     ("nod", ("N06", "watch."), {})],
            "gestures": [
                ("deictic", "R", ("N06", "Every"), {"size": "medium", "target": "panel (her left)",
                                                    "note": "introduces the panel: cross-body open palm, chest height, "
                                                            "stops 15 cm left of the sternum, under the mic head; "
                                                            "head and eyes turn 10 deg with it, back by 'Netflix'"}),
                ("open_palm", "R", ("N06", "predicts", 1, 0.3), {"size": "medium", "target": "front",
                                                                 "note": "a small circle, palm up: a crystal ball"}),
                ("point_viewer", "R", ("N06", "your"), {"size": "small", "target": "camera",
                                                         "note": "open hand toward the lens, not a jabbing finger"}),
            ],
            "lean": [(("N06", "Every"), 4), (("N06", "your"), 8), (("N06", "watch."), 5)],
        },
        "N07": {
            "arc": "body", "emotion": "satisfied: it's already there", "intensity": 0.7,
            "base": {"smile": 0.35, "brows": 0.05},
            "face": [("nod", ("N07", "box"), {}),
                     ("smile", ("N07", "near"), {"amount": 0.8, "hold": 0.5, "note": "Duchenne"})],
            "gestures": [
                ("carry", "both", ("N07", "copies"), {"size": "medium", "target": "front",
                                                      "note": "lifts a box from her right and carries it in an arc to "
                                                              "the centre front, set down on 'box' (in front of the "
                                                              "sternum, never past her left shoulder line)"}),
                ("open_palm", "R", ("N07", "you."), {"size": "small", "target": "camera"}),
            ],
            "lean": [(("N07", "near"), 6)],
        },
        "N08": {
            "arc": "body", "emotion": "explaining, crisp clarity", "intensity": 0.7,
            "base": {"smile": 0.2, "brows": 0.1},
            "note": "CU: gestures held high (collarbone to chin) so the hands enter the bottom of the frame; the "
                    "shoulders carry the rest",
            "face": [("glance", ("N08", "Each"), {"dir": "her right", "dur": 0.35,
                                                  "note": "agent-04's THINK beat; back on the lens by 'title'"}),
                     ("nod", ("N08", "encoded", 1, 0.3), {}),
                     ("brow_flash", ("N08", "many"), {}),
                     ("smile", ("N08", "bitrates."), {"amount": 0.55, "hold": 0.5})],
            "gestures": [
                ("size", "both", ("N08", "many"), {"size": "small", "target": "front",
                                                   "note": "hands frame a small box on 'many'..."}),
                ("size", "both", ("N08", "sizes"), {"size": "big", "target": "front",
                                                    "note": "...and widen to shoulder width on 'sizes'"}),
                ("ladder", "R", ("N08", "bitrates."), {"size": "medium", "target": "up",
                                                       "note": "flat palm steps up three rungs"}),
            ],
            "lean": [(("N08", "many"), 5)],
        },
        "N09": {
            "arc": "body", "emotion": "playful contrast", "intensity": 0.75, "off_cam": True,
            "base": {"smile": 0.35, "brows": 0.1},
            "face": [("smile", ("N09", "cartoon"), {"amount": 0.7, "hold": 0.5}),
                     ("brow_flash", ("N09", "action"), {}), ("smile_soft", ("N09", "each"), {"amount": 0.5}),
                     ("nod", ("N09", "ladder."), {})],
            "gestures": [("pinch", "R", ("N09", "fewer"), {"size": "small", "target": "front"}),
                         ("size", "both", ("N09", "action"), {"size": "big", "target": "front"}),
                         ("ladder", "R", ("N09", "ladder."), {"size": "medium", "target": "up"})],
            "lean": [(("N09", "action"), 5)],
        },
        "N10": {
            "arc": "body", "emotion": "matter-of-fact clarity", "intensity": 0.6, "off_cam": True,
            "base": {"smile": 0.2, "brows": 0.05},
            "face": [("brow_flash", ("N10", "chunks"), {}), ("nod", ("N10", "long."), {})],
            "gestures": [("chop", "R", ("N10", "cut"), {"size": "medium", "target": "front"}),
                         ("size", "both", ("N10", "few"), {"size": "small", "target": "front",
                                                           "note": "a few seconds: hands a short span apart"})],
            "lean": [],
        },
        "N11": {
            "arc": "body", "emotion": "clever, personal", "intensity": 0.65, "off_cam": True,
            "base": {"smile": 0.3, "brows": 0.05},
            "face": [("smile", ("N11", "picks"), {"amount": 0.6, "hold": 0.4}), ("nod", ("N11", "rung"), {})],
            "gestures": [("point_viewer", "R", ("N11", "Your"), {"size": "small", "target": "camera"}),
                         ("pinch", "R", ("N11", "picks"), {"size": "small", "target": "front"})],
            "lean": [(("N11", "Your"), 6)],
        },
        "N12": {
            "arc": "body", "emotion": "question, then easy reassurance", "intensity": 0.8,
            "base": {"smile": 0.25, "brows": 0.1},
            "face": [("brow_hold", ("N12", "Network"), {"hold": 0.9, "note": "brows up and held through 'dips?', "
                                                                             "the bar names this one"}),
                     ("tilt", ("N12", "dips?"), {"side": "R", "deg": 6}),
                     ("smile", ("N12", "little"), {"amount": 0.8, "hold": 0.6, "note": "reassuring Duchenne"}),
                     ("squint", ("N12", "softer."), {}),
                     ("nod", ("N12", "softer."), {})],
            "gestures": [
                ("deictic", "R", ("N12", "dips?"), {"size": "medium", "target": "panel (her left)",
                                                    "note": "flat palm-down hand dips toward the panel (cross-body, "
                                                            "chest height, under the mic head)"}),
                ("open_palm", "R", ("N12", "next"), {"size": "medium", "target": "camera", "note": "it's fine"}),
                ("pinch", "R", ("N12", "little"), {"size": "small", "target": "camera",
                                                    "note": "thumb and index almost touching"}),
            ],
            "lean": [(("N12", "Network"), 2), (("N12", "next"), 6)],
        },
        "N13": {
            "arc": "body", "emotion": "confident, brisk list, then a clean landing", "intensity": 0.75,
            "base": {"smile": 0.3, "brows": 0.05},
            "note": "THE 00:44 SHOT (WIDE): the rejected v2b sat here with hands clasped and upper arms pinned into the "
                    "torso. Elbows 20+ cm off the torso the whole line; the count hand out to her right at chest "
                    "height; the shoulders and torso turn a little with each count",
            "face": [("brow_flash", ("N13", "login,"), {}),
                     ("glance", ("N13", "Your"), {"dir": "up, her right", "dur": 0.3,
                                                  "note": "agent-04's THINK beat, quick"}),
                     ("nod", ("N13", "profile,"), {}),
                     ("brow_flash", ("N13", "recommendations:", 1, 0.6), {}),
                     ("smile", ("N13", "AWS."), {"amount": 0.85, "hold": 0.6, "note": "Duchenne"}),
                     ("nod", ("N13", "AWS."), {})],
            "gestures": [
                ("count", "R", ("N13", "login,"), {"size": "medium", "target": "her right, chest height",
                                                   "note": "index up (1)"}),
                ("count", "R", ("N13", "profile,"), {"size": "medium", "target": "her right, chest height",
                                                     "note": "+ middle (2)"}),
                ("count", "R", ("N13", "recommendations:", 1, 0.6), {"size": "medium",
                                                                     "target": "her right, chest height",
                                                                     "note": "+ ring (3)"}),
                ("open_palm", "both", ("N13", "that"), {"size": "big", "target": "front",
                                                         "note": "palms up, spread to shoulder width: 'all of it'; "
                                                                 "L hand below and inside the mic line"}),
                ("beat", "R", ("N13", "AWS."), {"size": "medium", "target": "camera"}),
            ],
            "lean": [(("N13", "login,"), 4), (("N13", "that"), 8), (("N13", "AWS."), 5)],
        },
        "N14": {
            "arc": "body", "emotion": "clear, simple mechanics", "intensity": 0.65, "off_cam": True,
            "base": {"smile": 0.25, "brows": 0.05},
            "face": [("brow_flash", ("N14", "AWS"), {}), ("nod", ("N14", "box."), {}),
                     ("smile", ("N14", "streams"), {"amount": 0.6, "hold": 0.5})],
            "gestures": [("press", "R", ("N14", "play,"), {"size": "small", "target": "camera"}),
                         ("deictic", "R", ("N14", "points"), {"size": "medium", "target": "her right"}),
                         ("open_palm", "both", ("N14", "streams"), {"size": "medium", "target": "front"})],
            "lean": [(("N14", "points"), 5)],
        },
        "N15": {
            "arc": "payoff", "emotion": "satisfied clarity: the two halves click", "intensity": 0.8,
            "base": {"smile": 0.4, "brows": 0.05},
            "face": [("brow_flash", ("N15", "cloud"), {}),
                     ("nod", ("N15", "decides.", 1, 0.35), {}),
                     ("smile", ("N15", "box"), {"amount": 0.7, "hold": 0.4}),
                     ("nod", ("N15", "delivers.", 1, 0.35), {}),
                     ("smile", ("N15", "delivers.", 1, 0.35), {"amount": 0.9, "hold": 0.5, "note": "Duchenne"})],
            "gestures": [
                ("high_low", "R", ("N15", "cloud"), {"size": "medium", "target": "up, her right",
                                                     "note": "open palm raised to chin height: up there"}),
                ("place", "both", ("N15", "box"), {"size": "medium", "target": "front, low",
                                                    "note": "both hands come down to the front: right here"}),
                ("beat", "both", ("N15", "delivers.", 1, 0.35), {"size": "medium", "target": "front"}),
            ],
            "lean": [(("N15", "cloud"), 4), (("N15", "box"), 7)],
        },
        "N16": {
            "arc": "payoff", "emotion": "satisfied delight", "intensity": 0.9,
            "base": {"smile": 0.6, "brows": 0.05},
            "face": [("brow_flash", ("N16", "That's"), {}),
                     ("smile", ("N16", "just"), {"amount": 1.0, "hold": 1.0, "note": "the biggest Duchenne of the "
                                                                                    "film, held into the cut"}),
                     ("tilt", ("N16", "plays."), {"side": "R", "deg": 5}),
                     ("nod", ("N16", "plays."), {})],
            "gestures": [("release", "both", ("N16", "plays."), {"size": "medium", "target": "front",
                                                                 "note": "palms up, a small outward 'ta-da', the "
                                                                         "shoulders lift; held to the cut"})],
            "lean": [(("N16", "That's"), 6), (("N16", "plays."), 4)],
        },
    },
}

TEST = {"netflix": {
    "spans": [{"camera": "CAM_MCU", "f0": 0, "f1": 196, "lines": ["N01", "N02", "N03"],
               "why": "the hook on one camera: curiosity, the one brow, the 'three hundred million' spread, the play "
                      "press and the 'just starts' Duchenne, then the 'But...' twist"},
              {"camera": "CAM_WIDE", "f0": 1040, "f1": 1162, "lines": ["N13"],
               "why": "the rejected 00:44 shot: the count, elbows off the torso, arm-breast clearance, the waist fit"}],
    "optional": {"camera": "CAM_MCU", "f0": 196, "f1": 305, "lines": ["N04"],
                 "why": "append for a literal 'lines 1-4' (+4.5 s, 17.8 s total)"},
}}

# ------------------------------------------------------------------------------------------------ resolve

DUR = {"brow_flash": 0.45, "brow_one": 0.8, "brow_hold": 0.9, "smile": 0.6, "smile_soft": 0.8, "squint": 0.4,
       "nod": 0.35, "tilt": 1.2, "glance": 0.4, "shake": 0.5}
LEAD = {"brow_flash": 0.12, "brow_one": 0.15, "brow_hold": 0.12, "smile": 0.30, "smile_soft": 0.35, "squint": 0.15,
        "nod": 0.15, "tilt": 0.25, "glance": 0.10, "shake": 0.15}
NON_MOUTH = {"brow_flash", "brow_one", "brow_hold", "smile", "smile_soft", "squint"}


def load(film: str) -> tuple[dict, dict]:
    cues = json.loads((HERE / "audio" / film / "cues.json").read_text())
    edl = json.loads((HERE / "edl" / f"{film}.json").read_text())
    return cues, edl


def word_t(lines: dict, ref) -> tuple[float, str]:
    if isinstance(ref, (int, float)):
        return float(ref), ""
    line, word, occ, stress = (list(ref) + [1, 0.0])[:4] if len(ref) < 4 else ref
    if len(ref) == 3:
        occ, stress = ref[2], 0.0
    hits = [w for w in lines[line]["words"] if w["w"].strip(",.?:!").lower() == word.strip(",.?:!").lower()]
    if len(hits) < occ:
        raise SystemExit(f"{line}: no word {word!r} (occurrence {occ}) in {lines[line]['text']!r}")
    w = hits[occ - 1]
    return round(w["start"] + stress * (w["end"] - w["start"]), 3), w["w"]


def fr(t: float) -> int:
    return int(round(t * FPS))


def resolve(sheet: dict) -> dict:
    cues, edl = load(sheet["film"])
    lines = {ln["id"]: ln for ln in cues["lines"]}
    where = {}
    for s in edl["shots"]:
        for i in s["lines"]:
            where[i] = {"shot": s["n"], "kind": s["kind"], "camera": (s.get("camera", "") +
                        ("_L" if s["kind"] == "panel" else "")) or None, "gfx": s.get("gfx"), "f0": s["f0"],
                        "f1": s["f1"]}
    out = {"film": sheet["film"], "who": sheet["who"], "fps": FPS, "clock": "VO t=0 = sequence frame 0",
           "arc": ARC, "staging": __doc__.split("Staging")[1].split("\n\n")[0].strip(" ():\n"),
           "conventions": {"lead_s": LEAD, "dur_s": DUR}, "pre": None, "lines": [], "test": TEST[sheet["film"]]}
    pre = sheet["pre"]
    out["pre"] = {"note": pre["note"], "face": [{"kind": k, "t": t, "f": fr(t), **x} for k, t, x in pre["face"]],
                  "lean": [{"t": t, "f": fr(t), "deg": d} for t, d in pre["lean"]]}
    for ln in cues["lines"]:
        spec = sheet["lines"][ln["id"]]
        face = []
        for kind, ref, x in spec["face"]:
            t, w = word_t(lines, ref)
            lead = LEAD[kind]
            dur = x.get("hold", 0) + DUR[kind] if kind in ("smile", "smile_soft") else x.get("hold", DUR[kind])
            face.append({"kind": kind, "word": w, "t": t, "f": fr(t), "onset_t": round(t - lead, 3),
                         "end_t": round(t - lead + max(dur, lead + 0.15), 3), **{k: v for k, v in x.items()
                                                                                  if k != "hold"},
                         **({"hold": x["hold"]} if "hold" in x else {})})
        gest = []
        for typ, hand, ref, x in spec["gestures"]:
            t, w = word_t(lines, ref)
            prep = x.get("prep", 0.30)
            g = {"type": typ, "hand": hand, "word": w, "stroke_t": t, "stroke_f": fr(t),
                 "prep_t": round(t - prep, 3), "prep_f": fr(t - prep), "hold_s": x.get("hold", 0.25),
                 "size": x.get("size", "medium"), "target": x.get("target", "camera")}
            if "start" in x:
                st, sw = word_t(lines, x["start"])
                g["prep_t"], g["prep_f"], g["start_word"] = round(st - 0.15, 3), fr(st - 0.15), sw
            if "note" in x:
                g["note"] = x["note"]
            gest.append(g)
        lean = [{"word": word_t(lines, r)[1], "t": word_t(lines, r)[0], "f": fr(word_t(lines, r)[0]), "deg": d}
                for r, d in spec["lean"]]
        row = {"id": ln["id"], "text": ln["text"], "t0": ln["start"], "t1": ln["end"], "f0": ln["start_f"],
               "f1": ln["end_f"], **where[ln["id"]], "on_cam": not spec.get("off_cam", False),
               "arc": spec["arc"], "arc_target": ARC[spec["arc"]], "emotion": spec["emotion"],
               "intensity": spec["intensity"], "base": spec["base"], "face": face, "gestures": gest, "lean": lean}
        if "note" in spec:
            row["note"] = spec["note"]
        out["lines"].append(row)
    words = json.loads((HERE / "cues" / f"{sheet['who']}.json").read_text())["words"]
    widx = {}
    for i, w in enumerate(words):
        widx.setdefault((w["line"], w["w"]), i)
    for row in out["lines"]:
        for ev in row["face"] + row["gestures"]:
            ev["word_i"] = widx.get((row["id"], ev["word"]))
        row["face04"] = face04(row)
        row["body01"] = body01(row)
    out["checks"] = checks(out)
    return out


MOOD = {"curiosity": "SURPRISE", "confident clarity": "HAPPINESS", "satisfied delight": "HAPPINESS"}


def face04(row: dict) -> dict:
    """agent-04's shape: words named by text (+ word_i, the index in cues/<who>.json words)."""
    ref = lambda f: {"word": f["word"], "word_i": f["word_i"], "t": f["t"]}  # noqa: E731
    v = {"line": row["id"], "emotion": row["emotion"], "intensity": row["intensity"],
         "solver_mood": MOOD[row["arc_target"]], "brow": [], "smile": [], "curious": [], "warm": [], "nod": [],
         "tilt": [], "glance": [], "squint": [], "shake": []}
    for f in row["face"]:
        k = f["kind"]
        if k == "brow_flash":
            v["brow"].append(ref(f))
        elif k in ("brow_one", "brow_hold"):
            v["curious"].append({**ref(f), "kind": "one_brow" if k == "brow_one" else "brows_held",
                                 "side": f.get("side"), "hold_s": f.get("hold")})
        elif k == "smile":
            v["smile"].append({**ref(f), "kind": "duchenne" if f.get("amount", 0) >= 0.7 else "soft",
                               "amount": f.get("amount"), "hold_s": f.get("hold")})
        elif k == "smile_soft":
            v["warm"].append({**ref(f), "amount": f.get("amount")})
        elif k == "nod":
            v["nod"].append({**ref(f), "kind": "yes"})
        elif k == "tilt":
            v["tilt"].append({**ref(f), "deg": f["deg"], "side": f["side"]})
        else:
            v[k].append({**ref(f), **({"dir": f["dir"], "dur_s": f["dur"]} if k == "glance" else {})})
    return {k: x for k, x in v.items() if x != []}


BODY_TYPE = {"beat": "beat", "open_palm": "open", "release": "open", "point_viewer": "open", "sweep": "open",
             "count": "count", "deictic": "deictic", "size": "size", "pinch": "size", "ladder": "size",
             "place": "size", "carry": "size", "high_low": "deictic", "press": "beat", "chop": "beat",
             "wave_off": "deictic", "raise_finger": "beat"}


def body01(row: dict) -> dict:
    """agent-01's shape: type in beat|open|count|deictic|size (`detail` keeps the sheet's own name), hand r|l|both."""
    g = [{"type": BODY_TYPE[x["type"]], "detail": x["type"], "hand": x["hand"].lower(), "word": x["word"],
          "word_i": x["word_i"], "stroke_t": x["stroke_t"], "prep_t": x["prep_t"], "hold_s": x["hold_s"],
          "size": x["size"], "target": x["target"]} for x in row["gestures"]]
    return {"line": row["id"], "on_cam": row["on_cam"], "camera": row["camera"], "gestures": g,
            "lean": [{"kind": "in" if x["deg"] >= 5 else "neutral", "deg": x["deg"], "word": x["word"], "t": x["t"]}
                     for x in row["lean"]],
            "rest_after": True}


def checks(a: dict) -> dict:
    """The R7 performance rows, as planned on paper (agent-09 measures the render; this proves the plan can pass)."""
    speak = sum(ln["t1"] - ln["t0"] for ln in a["lines"])
    on = [ln for ln in a["lines"] if ln["on_cam"]]
    smiles = sum(1 for ln in a["lines"] for f in ln["face"] if f["kind"] == "smile")
    brows = sum(1 for ln in a["lines"] for f in ln["face"] if f["kind"] in ("brow_flash", "brow_one", "brow_hold"))
    rates, holds, repeats = {}, {}, []
    for ln in a["lines"]:
        d = ln["t1"] - ln["t0"]
        rates[ln["id"]] = round(len(ln["gestures"]) / d, 2)
        # the longest stretch of the line with no non-mouth face move under way
        spans = sorted((f["onset_t"], f["end_t"]) for f in ln["face"] if f["kind"] in NON_MOUTH | {"nod", "tilt"})
        gap, cur = 0.0, ln["t0"]
        for s0, s1 in spans:
            gap = max(gap, s0 - cur)
            cur = max(cur, s1)
        holds[ln["id"]] = round(max(gap, ln["t1"] - cur), 2)
        g = ln["gestures"]
        repeats += [f"{ln['id']} {x['type']}@{x['word']}" for p, x in zip(g, g[1:])
                    if p["type"] == x["type"] and p["type"] not in ("beat", "count", "size")]
    return {"speaking_s": round(speak, 2), "smiles_per_min": round(smiles / speak * 60, 1),
            "brow_flash_per_min": round(brows / speak * 60, 1),
            "gesture_onsets_per_s": {"all": round(sum(len(ln["gestures"]) for ln in a["lines"]) / speak, 2),
                                     "per_line": rates},
            "neutral_hold_max_s": {"max": max(holds.values()), "per_line": holds},
            "same_gesture_twice": repeats, "on_cam_lines": [ln["id"] for ln in on]}


# ------------------------------------------------------------------------------------------------ the readable sheet

def md(a: dict) -> str:
    who = {"her": "Her (Netflix, Tripti)", "him": "Him (WhatsApp, Tarun)"}[a["who"]]
    o = [f"## {who}", "", f"Arc: hook = **{ARC['hook']}**, body = **{ARC['body']}**, payoff = **{ARC['payoff']}**. "
         "Times are seconds on the VO clock (t 0 = sequence frame 0); `f` is the 24 fps frame.", "",
         f"**Before the first word (0-{a['lines'][0]['t0']:.2f} s):** {a['pre']['note']}", ""]
    for ln in a["lines"]:
        cam = ln["camera"] if ln["on_cam"] else f"off camera (graphic `{ln['gfx']}`): continuity only"
        o += [f"### {ln['id']}  {ln['t0']:.2f}-{ln['t1']:.2f} s  ·  {cam}", "", f"> {ln['text']}", "",
              f"- **{ln['emotion']}**, intensity {ln['intensity']} ({ln['arc']}: {ln['arc_target']}); base smile "
              f"{ln['base']['smile']}, brows {ln['base']['brows']}"]
        if ln.get("note"):
            o.append(f"- **Note:** {ln['note']}")
        o.append("- **Face:** " + "; ".join(
            f"{f['kind'].replace('_', ' ')}"
            + (f" {f['side']}" if "side" in f else "") + (f" {f['deg']}°" if "deg" in f else "")
            + (f" {f['amount']}" if "amount" in f else "") + f" on *{f['word']}* {f['t']:.2f} s (f{f['f']})"
            + (f" ({f['note']})" if "note" in f else "") for f in ln["face"]))
        o.append("- **Gestures:** " + "; ".join(
            f"{g['type'].replace('_', ' ')} [{g['hand']}, {g['size']}, to {g['target']}] stroke on *{g['word']}* "
            f"{g['stroke_t']:.2f} s (f{g['stroke_f']}), prep from {g['prep_t']:.2f}"
            + (f" (from *{g['start_word']}*)" if "start_word" in g else "")
            + (f": {g['note']}" if "note" in g else "") for g in ln["gestures"]))
        if ln["lean"]:
            o.append("- **Lean:** " + ", ".join(f"{x['deg']}° on *{x['word']}* {x['t']:.2f} s" for x in ln["lean"]))
        o.append("")
    c = a["checks"]
    o += ["### The plan against the R7 rows", "",
          f"- smiles {c['smiles_per_min']}/min (>= 4), brow flashes {c['brow_flash_per_min']}/min (>= 6)",
          f"- gesture onsets {c['gesture_onsets_per_s']['all']}/s over the speech (0.5-1.2)",
          f"- longest planned neutral stretch inside a line {c['neutral_hold_max_s']['max']} s (<= 1.5)",
          f"- the same gesture twice in a row: {', '.join(c['same_gesture_twice']) or 'none'}", ""]
    t = a["test"]
    o += ["### The TEST span", ""] + [f"- {s['camera']} frames {s['f0']}-{s['f1']} ({(s['f1'] - s['f0']) / FPS:.2f} s"
                                     f", {' '.join(s['lines'])}): {s['why']}" for s in t["spans"]]
    tot = sum(s["f1"] - s["f0"] for s in t["spans"]) / FPS
    op = t["optional"]
    o += [f"- total {tot:.2f} s. Optional: {op['camera']} {op['f0']}-{op['f1']} ({' '.join(op['lines'])}), {op['why']}",
          ""]
    return "\n".join(o)


HEAD = """# Acting sheets (round 7: performance)

The operator rejected her Netflix v2b on acting: a flat face (mouth-only solves), hands clasped and upper arms pinned to
the torso (00:44), her right upper arm into her breast, and the waist fit. This is the director's sheet the face
(agent-04) and body (agent-01, agent-10) builds follow, line by line. `acting.py` writes it from the VO alignment
(`acting/<who>.json` is the machine copy, with every time in seconds and frames); re-run it after a VO change.

**Staging, for every line:** hands off the body and above the desk while she speaks, rest (hands loosely together,
forearms on the desk edge) only in the pauses; elbows out so the upper arms clear the torso and breasts by >= 3 cm;
shoulders back and down, chest open, 4-8° forward lean on emphasis; the shoulders and torso move with every gesture.
The mic is on HER LEFT: big gestures are the right hand, or both hands in front of the sternum inside the shoulder
line, never past her left shoulder line; the left hand alone only small and low. The graphic panel (`CAM_MCU_L`) is on
frame right = her left: a deictic to it is the right hand across the body, open palm, chest height, stopping ~15 cm
left of the sternum, under the mic head, the head and eyes turning ~10° with it and straight back to the lens. Off-camera
lines (graphics full frame) keep her alive for continuity: the next on-camera shot can open mid-gesture.

"""


def main() -> None:
    (HERE / "acting").mkdir(exist_ok=True)
    a = resolve(HER)
    (HERE / "acting" / "her.json").write_text(json.dumps(a, indent=1) + "\n")
    (HERE / "ACTING.md").write_text(HEAD + md(a))
    c = a["checks"]
    print(json.dumps({k: v for k, v in c.items() if k != "on_cam_lines"}, indent=1))


if __name__ == "__main__":
    main()
