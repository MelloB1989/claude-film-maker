"""The explainers' acting sheet (round 7: performance): per VO line the emotion, intensity and lean, the face moments
(brow flashes, Duchenne smiles, nods, tilts, glances) and the gestures (type, hand, target, size), each pinned to an
exact word, resolved against the VO alignment (audio/<film>/cues.json) into seconds and sequence frames.

    python3 films/host-studio/explainers/acting.py            # -> acting/her.json, acting/him.json + ACTING.md, checks

Re-run after any VO rebuild and every beat moves with the voice, like edl.py. Times are on the VO clock: t = 0 is
sequence frame 0 (frame = round(t * 24)). A word reference is (line, word[, occurrence][, stress]): `stress` is where
the stressed syllable sits as a fraction of the word (0 = its start), and the apex of a face move or the stroke of a
gesture lands there.

Timing conventions (agent-04 face, agent-01/agent-10 body):
- brow flash: rise 0.12 s before the apex, apex on the stressed syllable, 0.35-0.5 s total, back to the line's base;
- smile: onset 0.30 s before the apex, apex on the word, held `hold` s, then eases to the line's base smile;
- nod / tilt: apex on the stressed syllable (a nod is down-then-up, 0.35 s; a tilt holds until the next head move);
- gesture: preparation from `prep` s before the stroke (default 0.30), stroke on the stressed syllable, held `hold`
  s, then a retraction to a HIGH REST (hands loosely together at the sternum, elbows off the torso: at the MCU
  frame's bottom edge), not the desk, unless `rest` says so;
- gesture space: `apex_height` per stroke (HEIGHT, by camera and size): chest to collarbone in front of the torso,
  so the hands are IN the shot (CAM_MCU's bottom edge is at the sternum, z 85; CAM_CU's above the shoulders, z 102).

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
                "(4 deg), an inhale with the shoulders rising 1 cm, hands loosely together at the sternum in front "
                "of her (fingertips touching, elbows out), at the bottom edge of the MCU frame, not on the desk. A small lean in from 0.4 s.",
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
                     ("smile", ("N01", "million"), {"amount": 0.5, "hold": 0.4, "shape": "lopsided R, closed"}),
                     ("smile", ("N01", "members"), {"amount": 0.85, "hold": 0.5, "note": "full Duchenne (payoff 1/5): cheeks up, "
                                                                                          "eyes squint"})],
            "gestures": [
                ("open_palm", "R", ("N01", "Netflix"), {"size": "small", "target": "camera",
                                                        "note": "palm up and slightly out, chest height, presenting"}),
                ("size", "both", ("N01", "million"), {"start": ("N01", "three"), "size": "big", "target": "front",
                                                      "hold": 0.6, "height": "upper_chest",
                                                      "note": "hands start 15 cm apart in front of her sternum on "
                                                              "'three', spread OUT to shoulder width on 'million' at "
                                                              "chest height (wrists at or below the collarbone), palms in/"
                                                              "forward, the path bowing forward, never up: a huge number; "
                                                              "L hand stays below the mic (if it can't join, the R spreads "
                                                              "out to her right at chest height, never toward the face)"}),
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
                                                  "note": "index finger presses an imaginary play button FORWARD "
                                                          "toward the lens, entering the CU from below at collarbone "
                                                          "height; never up beside the face, never a palm-out wave"}),
                ("release", "both", ("N02", "starts.", 1, 0.3), {"size": "medium", "target": "front",
                                                                "height": "upper_chest",
                                                                "note": "fingers spring open outward and slightly "
                                                                        "DOWN, 'ta-da', shoulders lift; never up "
                                                                        "beside the face"}),
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
                     ("smile", ("N04", "called"), {"amount": 0.5, "hold": 0.6, "shape": "closed, proud"}),
                     ("brow_flash", ("N04", "Open"), {}),
                     ("nod", ("N04", "Appliances.", 1, 0.35), {})],
            "gestures": [
                ("place", "both", ("N04", "builds"), {"size": "medium", "target": "front",
                                                      "hold": 0.5, "note": "palms facing, shoulder width, setting a box down in "
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
            "face": [("brow_flash", ("N05", "free,"), {}), ("smile", ("N05", "free,"), {"amount": 0.5, "hold": 0.4, "shape": "open lips"}),
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
                     ("smile", ("N06", "predicts", 1, 0.3), {"amount": 0.45, "hold": 0.5, "shape": "sly, lopsided R", "note": "sly"}),
                     ("tilt", ("N06", "area"), {"side": "L", "deg": 5, "note": "toward the panel"}),
                     ("nod", ("N06", "watch."), {})],
            "gestures": [
                ("deictic", "R", ("N06", "Every"), {"size": "medium", "target": "panel (her left)",
                                                    "hold": 0.7, "note": "introduces the panel: cross-body open palm, chest height, "
                                                            "stops 15 cm left of the sternum, under the mic head; "
                                                            "head and eyes turn 10 deg with it, back by 'Netflix'"}),
                ("open_palm", "R", ("N06", "predicts", 1, 0.3), {"size": "medium", "target": "front", "height": "sternum",
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
            "note": "CU: gestures held high (at the collarbone, never the chin) so the hands enter the bottom of the frame; the "
                    "shoulders carry the rest",
            "face": [("glance", ("N08", "Each"), {"dir": "her right", "dur": 0.35,
                                                  "note": "agent-04's THINK beat; back on the lens by 'title'"}),
                     ("nod", ("N08", "encoded", 1, 0.3), {}),
                     ("brow_flash", ("N08", "many"), {}),
                     ("smile", ("N08", "bitrates."), {"amount": 0.45, "hold": 0.5, "shape": "lopsided L"})],
            "gestures": [
                ("size", "both", ("N08", "many"), {"size": "small", "target": "front",
                                                   "note": "hands frame a small box on 'many'..."}),
                ("size", "both", ("N08", "sizes"), {"size": "big", "target": "front",
                                                    "hold": 0.5, "note": "...and widen to shoulder width on 'sizes'"}),
                ("ladder", "R", ("N08", "bitrates."), {"size": "medium", "target": "up",
                                                       "note": "flat palm steps up three rungs"}),
            ],
            "lean": [(("N08", "many"), 5)],
        },
        "N09": {
            "arc": "body", "emotion": "playful contrast", "intensity": 0.75, "off_cam": True,
            "base": {"smile": 0.35, "brows": 0.1},
            "face": [("smile", ("N09", "cartoon"), {"amount": 0.55, "hold": 0.4, "shape": "amused, lopsided L"}),
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
            "face": [("smile", ("N11", "picks"), {"amount": 0.45, "hold": 0.4, "shape": "closed"}), ("nod", ("N11", "rung"), {})],
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
                     ("smile", ("N12", "little"), {"amount": 0.55, "hold": 0.6, "shape": "closed, reassuring"}),
                     ("squint", ("N12", "softer."), {}),
                     ("nod", ("N12", "softer."), {})],
            "gestures": [
                ("deictic", "R", ("N12", "dips?"), {"size": "medium", "target": "panel (her left)",
                                                    "note": "flat palm-down hand dips toward the panel (cross-body, "
                                                            "chest height, under the mic head)"}),
                ("open_palm", "R", ("N12", "next"), {"size": "medium", "target": "camera", "note": "it's fine", "height": "sternum"}),
                ("pinch", "R", ("N12", "little"), {"size": "small", "target": "camera",
                                                    "hold": 0.6, "note": "thumb and index almost touching"}),
            ],
            "lean": [(("N12", "Network"), 2), (("N12", "next"), 6)],
        },
        "N13": {
            "arc": "body", "emotion": "confident, brisk list, then a clean landing", "intensity": 0.75,
            "base": {"smile": 0.3, "brows": 0.05},
            "note": "THE 00:44 SHOT (WIDE): the rejected v2b sat here with hands clasped and upper arms pinned into the "
                    "torso. Elbows 20+ cm off the torso the whole line; the R hand LISTS (R7 hands, the operator's 'zombie' "
                    "claw at 00:08): open, palm up/in, placing the three items left to right along a line in front of "
                    "her at chest height, forearm angled toward camera, no hold over 0.6 s; the shoulders and torso "
                    "turn a little with each placement",
            "face": [("brow_flash", ("N13", "login,"), {}),
                     ("glance", ("N13", "Your"), {"dir": "up, her right", "dur": 0.3,
                                                  "note": "agent-04's THINK beat, quick"}),
                     ("nod", ("N13", "profile,"), {}),
                     ("brow_flash", ("N13", "recommendations:", 1, 0.6), {}),
                     ("smile", ("N13", "AWS."), {"amount": 0.85, "hold": 0.6, "note": "Duchenne"}),
                     ("nod", ("N13", "AWS."), {})],
            "gestures": [
                ("list", "R", ("N13", "login,"), {"size": "medium", "target": "front, her midline", "height": "sternum",
                                                  "item": 1, "of": 3,
                                                  "note": "open hand, palm angled up/in, PLACES item 1 of 3 on a line in front of her at chest height (at her midline); the forearm angled toward camera, wrist below the collarbone, a small drift, no finger counting"}),
                ("list", "R", ("N13", "profile,"), {"size": "medium", "target": "front, a hand-width to her right",
                                                    "height": "sternum", "item": 2, "of": 3,
                                                    "note": "open hand, palm angled up/in, PLACES item 2 of 3 on a line in front of her at chest height (a hand-width to her right); the forearm angled toward camera, wrist below the collarbone, a small drift, no finger counting"}),
                ("list", "R", ("N13", "recommendations:", 1, 0.6), {"size": "medium",
                                                                    "target": "front, two hand-widths to her right",
                                                                    "height": "sternum", "item": 3, "of": 3, "hold": 0.5,
                                                                    "note": "open hand, palm angled up/in, PLACES item 3 of 3 on a line in front of her at chest height (two hand-widths to her right, away from the mic); the forearm angled toward camera, wrist below the collarbone, a small drift, no finger counting"}),
                ("open_palm", "both", ("N13", "that"), {"size": "big", "target": "front",
                                                         "hold": 0.7, "note": "palms up, spread to shoulder width: 'all of it'; "
                                                                 "L hand below and inside the mic line"}),
                ("beat", "R", ("N13", "AWS."), {"size": "medium", "target": "camera"}),
            ],
            "lean": [(("N13", "login,"), 4), (("N13", "that"), 8), (("N13", "AWS."), 5)],
        },
        "N14": {
            "arc": "body", "emotion": "clear, simple mechanics", "intensity": 0.65, "off_cam": True,
            "base": {"smile": 0.25, "brows": 0.05},
            "face": [("brow_flash", ("N14", "AWS"), {}), ("nod", ("N14", "box."), {}),
                     ("smile", ("N14", "streams"), {"amount": 0.5, "hold": 0.5, "shape": "open lips"})],
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
                     ("smile", ("N15", "box"), {"amount": 0.45, "hold": 0.3, "shape": "closed"}),
                     ("nod", ("N15", "delivers.", 1, 0.35), {}),
                     ("smile", ("N15", "delivers.", 1, 0.35), {"amount": 0.6, "hold": 0.5, "shape": "open lips, building to N16"})],
            "gestures": [
                ("high_low", "R", ("N15", "cloud"), {"size": "medium", "target": "up, her right", "height": "collarbone",
                                                     "hold": 0.5, "note": "open palm raised to collarbone height: up there"}),
                ("place", "both", ("N15", "box"), {"size": "medium", "target": "front", "height": "sternum",
                                                    "note": "both hands come down to the sternum, the frame's edge: "
                                                            "right here"}),
                ("beat", "both", ("N15", "delivers.", 1, 0.35), {"size": "medium", "target": "front", "height": "sternum"}),
            ],
            "lean": [(("N15", "cloud"), 4), (("N15", "box"), 7)],
        },
        "N16": {
            "arc": "payoff", "emotion": "satisfied delight", "intensity": 0.9,
            "base": {"smile": 0.6, "brows": 0.05},
            "face": [("brow_flash", ("N16", "That's"), {}),
                     ("smile", ("N16", "just"), {"amount": 0.9, "hold": 1.0, "note": "the last full Duchenne, held "
                                                                                    "into the cut"}),
                     ("tilt", ("N16", "plays."), {"side": "R", "deg": 5}),
                     ("nod", ("N16", "plays."), {})],
            "gestures": [("release", "both", ("N16", "plays."), {"size": "medium", "target": "front",
                                                                 "hold": 1.0, "note": "palms up, a small outward 'ta-da', the "
                                                                         "shoulders lift; held to the cut"})],
            "lean": [(("N16", "That's"), 6), (("N16", "plays."), 4)],
        },
    },
}

# ------------------------------------------------------------------------------------------------ him: WhatsApp
# The same staging (his mic is on HIS LEFT too, PERF_HIM.md; the panel on frame right = his left). His colour: warmer,
# a friendly grin and a touch of play where hers is sly; the same calibration (full Duchenne on five payoffs only:
# 'messages' (W01), 'Here's how', 'read it', 'your hands', 'a day').
HIM = {
    "film": "whatsapp", "who": "him",
    "pre": {
        "note": "Already alive when the cut opens: an easy closed-mouth grin building, a small head tilt to his right "
                "(4 deg), an inhale with the shoulders rising 1 cm, hands loosely together at the sternum in front "
                "of him (fingers loosely laced, elbows out), at the bottom edge of the MCU frame, not on the desk. A small lean in from 0.4 s.",
        "face": [("smile_soft", 0.15, {"amount": 0.35}), ("tilt", 0.2, {"side": "R", "deg": 4})],
        "lean": [(0.4, 4)],
    },
    "lines": {
        "W01": {
            "arc": "hook", "emotion": "curious, friendly: 'guess how many'", "intensity": 0.75,
            "base": {"smile": 0.3, "brows": 0.1},
            "face": [("brow_flash", ("W01", "Every"), {}),
                     ("brow_one", ("W01", "over"), {"side": "R", "hold": 0.9}),
                     ("tilt", ("W01", "over"), {"side": "R", "deg": 5}),
                     ("nod", ("W01", "billion"), {}),
                     ("smile", ("W01", "billion"), {"amount": 0.5, "hold": 0.3, "shape": "lopsided R, open lips"}),
                     ("smile", ("W01", "messages."), {"amount": 0.85, "hold": 0.5,
                                                       "note": "full Duchenne (payoff 1/5)"})],
            "gestures": [
                ("open_palm", "R", ("W01", "Every"), {"size": "small", "target": "camera"}),
                ("size", "both", ("W01", "billion"), {"start": ("W01", "hundred"), "size": "big", "target": "front",
                                                      "hold": 0.6, "note": "hands start 15 cm apart in front of his "
                                                                           "sternum, spread to shoulder width; L hand "
                                                                           "below the mic"}),
                ("beat", "R", ("W01", "messages."), {"size": "small", "target": "camera"}),
            ],
            "lean": [(("W01", "over"), 7), (("W01", "messages."), 4)],
        },
        "W02": {
            "arc": "hook", "emotion": "intrigue, the twist", "intensity": 0.7, "off_cam": True,
            "base": {"smile": 0.2, "brows": 0.15},
            "face": [("brow_one", ("W02", "almost"), {"side": "L", "hold": 0.7}),
                     ("shake", ("W02", "none"), {}),
                     ("smile_soft", ("W02", "servers."), {"amount": 0.45})],
            "gestures": [("pinch", "R", ("W02", "almost"), {"size": "small", "target": "front"}),
                         ("wave_off", "R", ("W02", "none"), {"size": "medium", "target": "her right, low",
                                                             "note": "palm-down sweep out to his right: none"})],
            "lean": [(("W02", "almost"), 6)],
        },
        "W03": {
            "arc": "hook", "emotion": "conspiratorial delight: 'let me show you'", "intensity": 0.8,
            "base": {"smile": 0.4, "brows": 0.1},
            "note": "CU, half a second of speech: the face carries it; the hands only enter at the bottom of the frame",
            "face": [("brow_flash", ("W03", "Here's"), {}),
                     ("smile", ("W03", "how."), {"amount": 0.85, "hold": 0.6, "note": "full Duchenne (payoff 2/5)"}),
                     ("nod", ("W03", "how."), {})],
            "gestures": [("open_palm", "both", ("W03", "how."), {"size": "small", "target": "camera", "hold": 0.5,
                                                                 "note": "palms up, collarbone height: here it is"})],
            "lean": [(("W03", "Here's"), 7)],
        },
        "W04": {
            "arc": "body", "emotion": "clear, friendly walkthrough", "intensity": 0.7,
            "base": {"smile": 0.3, "brows": 0.05},
            "face": [("brow_flash", ("W04", "Open"), {}),
                     ("smile", ("W04", "phone"), {"amount": 0.45, "hold": 0.4, "shape": "closed"}),
                     ("nod", ("W04", "connection", 1, 0.4), {}),
                     ("tilt", ("W04", "WhatsApp.", 1, 0.3), {"side": "L", "deg": 5, "note": "toward the panel"})],
            "gestures": [
                ("press", "R", ("W04", "app,"), {"size": "small", "target": "front", "note": "a thumb tap on an "
                                                                                           "imaginary phone"}),
                ("raise_finger", "R", ("W04", "one"), {"size": "small", "target": "up", "note": "one finger: one"}),
                ("deictic", "R", ("W04", "connection", 1, 0.4), {"size": "medium", "target": "panel (his left)",
                                                                 "hold": 0.7,
                                                                 "note": "draws the line from his chest toward the "
                                                                         "panel: cross-body, chest height, stops 15 cm "
                                                                         "left of the sternum under the mic head"}),
            ],
            "lean": [(("W04", "your"), 6)],
        },
        "W05": {
            "arc": "body", "emotion": "fascinated, nerdy delight", "intensity": 0.65, "off_cam": True,
            "base": {"smile": 0.3, "brows": 0.05},
            "face": [("tilt", ("W05", "each"), {"side": "L", "deg": 4}),
                     ("brow_flash", ("W05", "tiny"), {}), ("smile_soft", ("W05", "Erlang"), {"amount": 0.5}),
                     ("nod", ("W05", "process."), {})],
            "gestures": [("place", "both", ("W05", "server,"), {"size": "medium", "target": "front"}),
                         ("pinch", "R", ("W05", "tiny"), {"size": "small", "target": "front", "hold": 0.5}),
                         ("beat", "R", ("W05", "process."), {"size": "small", "target": "camera"})],
            "lean": [(("W05", "tiny"), 5)],
        },
        "W06": {
            "arc": "body", "emotion": "impressed: a big number", "intensity": 0.75, "off_cam": True,
            "base": {"smile": 0.3, "brows": 0.1},
            "face": [("brow_flash", ("W06", "two"), {}),
                     ("smile", ("W06", "million"), {"amount": 0.55, "hold": 0.4, "shape": "open lips"}),
                     ("nod", ("W06", "them."), {})],
            "gestures": [("raise_finger", "R", ("W06", "One"), {"size": "small", "target": "up"}),
                         ("size", "both", ("W06", "million"), {"start": ("W06", "two"), "size": "big",
                                                               "target": "front",
                                                               "note": "spread OUT at chest height (wrists at or below "
                                                                       "the collarbone), bowing forward, never up "
                                                                       "toward the face"})],
            "lean": [(("W06", "two"), 6)],
        },
        "W07": {
            "arc": "body", "emotion": "playful question", "intensity": 0.75,
            "base": {"smile": 0.3, "brows": 0.1},
            "note": "WIDE: elbows 20+ cm off the torso, hands up the whole line (the same fix as her 00:44 shot)",
            "face": [("smile_soft", ("W07", "You"), {"amount": 0.4}),
                     ("brow_flash", ("W07", "send."), {}),
                     ("glance", ("W07", "Is"), {"dir": "up, his right", "dur": 0.35, "note": "agent-04's THINK beat"}),
                     ("brow_hold", ("W07", "friend"), {"hold": 0.6}),
                     ("tilt", ("W07", "online?"), {"side": "R", "deg": 6})],
            "gestures": [
                ("point_viewer", "R", ("W07", "You"), {"size": "small", "target": "camera", "note": "open hand"}),
                ("press", "R", ("W07", "send."), {"size": "medium", "target": "front", "hold": 0.4,
                                                  "note": "a thumb press, crisp"}),
                ("open_palm", "both", ("W07", "online?", 1, 0.3), {"size": "medium", "target": "front",
                                                                    "note": "palms up, a small shrug: well, is he?"}),
            ],
            "lean": [(("W07", "You"), 6), (("W07", "online?"), 3)],
        },
        "W08": {
            "arc": "body", "emotion": "simple, direct", "intensity": 0.6, "off_cam": True,
            "base": {"smile": 0.25, "brows": 0.05},
            "face": [("brow_flash", ("W08", "straight"), {}), ("nod", ("W08", "connection.", 1, 0.3), {})],
            "gestures": [("sweep", "R", ("W08", "straight"), {"size": "medium", "target": "front, down",
                                                              "note": "a flat hand slides straight forward"})],
            "lean": [(("W08", "straight"), 5)],
        },
        "W09": {
            "arc": "body", "emotion": "patient, then a tidy satisfaction", "intensity": 0.7, "off_cam": True,
            "base": {"smile": 0.25, "brows": 0.05},
            "face": [("brow_one", ("W09", "not,"), {"side": "R", "hold": 0.5}),
                     ("tilt", ("W09", "waits."), {"side": "L", "deg": 4}),
                     ("nod", ("W09", "delivered,", 1, 0.3), {}),
                     ("smile", ("W09", "deleted.", 1, 0.3), {"amount": 0.55, "hold": 0.4, "shape": "closed"})],
            "gestures": [("wave_off", "R", ("W09", "not,"), {"size": "small", "target": "her right"}),
                         ("open_palm", "R", ("W09", "waits."), {"size": "small", "target": "camera", "hold": 0.5,
                                                                 "note": "palm out: it waits"}),
                         ("chop", "R", ("W09", "deleted.", 1, 0.3), {"size": "medium", "target": "front",
                                                                     "note": "a crisp wipe: gone"})],
            "lean": [(("W09", "once"), 5)],
        },
        "W10": {
            "arc": "body", "emotion": "playful, knowing: everyone wonders this", "intensity": 0.75,
            "base": {"smile": 0.3, "brows": 0.1},
            "face": [("glance", ("W10", "Your"), {"dir": "his left, to the panel", "dur": 0.35,
                                                  "note": "agent-04's THINK beat, toward the ticks"}),
                     ("brow_hold", ("W10", "ticks?"), {"hold": 0.6}),
                     ("smile", ("W10", "server"), {"amount": 0.45, "hold": 0.3, "shape": "lopsided L"}),
                     ("nod", ("W10", "it."), {})],
            "gestures": [
                ("deictic", "R", ("W10", "ticks?"), {"size": "medium", "target": "panel (his left)", "hold": 0.5,
                                                     "note": "cross-body open palm toward the ticks, under the mic "
                                                             "head"}),
                ("list", "R", ("W10", "One:"), {"size": "medium", "target": "front, his midline", "height": "sternum",
                                                "item": 1, "of": 2,
                                                "note": "open hand, palm angled up/in, PLACES item 1 of 2 on a line in front of him at chest height (back from the panel to his midline); the forearm angled toward camera, wrist below the collarbone, a small drift, no finger counting"}),
                ("beat", "R", ("W10", "has"), {"size": "small", "target": "camera"}),
            ],
            "lean": [(("W10", "Your"), 5)],
        },
        "W11": {
            "arc": "body", "emotion": "building to a little reveal", "intensity": 0.8,
            "base": {"smile": 0.3, "brows": 0.05},
            "face": [("nod", ("W11", "phone."), {}),
                     ("brow_flash", ("W11", "Blue:"), {}),
                     ("smile", ("W11", "read"), {"amount": 0.85, "hold": 0.5,
                                                 "note": "full Duchenne (payoff 3/5): the blue ticks"})],
            "gestures": [
                ("list", "R", ("W11", "Two:"), {"size": "medium", "target": "front, a hand-width to his right",
                                                "height": "sternum", "item": 2, "of": 2,
                                                "note": "open hand, palm angled up/in, PLACES item 2 of 2 on a line in front of him at chest height (a hand-width to his right); the forearm angled toward camera, wrist below the collarbone, a small drift, no finger counting"}),
                ("deictic", "R", ("W11", "Blue:"), {"size": "medium", "target": "panel (his left)", "hold": 0.5,
                                                    "note": "the open hand turns toward the panel's blue ticks"}),
                ("open_palm", "R", ("W11", "read"), {"size": "small", "target": "camera"}),
            ],
            "lean": [(("W11", "Blue:"), 7)],
        },
        "W12": {
            "arc": "body", "emotion": "clever efficiency", "intensity": 0.7, "off_cam": True,
            "base": {"smile": 0.3, "brows": 0.05},
            "face": [("brow_flash", ("W12", "once."), {}), ("nod", ("W12", "once."), {}),
                     ("smile", ("W12", "everyone."), {"amount": 0.5, "hold": 0.4, "shape": "open lips"})],
            "gestures": [("raise_finger", "R", ("W12", "once."), {"size": "small", "target": "up", "hold": 0.5}),
                         ("sweep", "both", ("W12", "fans"), {"size": "big", "target": "front",
                                                             "note": "both hands fan out from the centre"})],
            "lean": [(("W12", "once."), 5)],
        },
        "W13": {
            "arc": "body", "emotion": "reassuring, a little conspiratorial", "intensity": 0.8,
            "base": {"smile": 0.3, "brows": 0.05},
            "note": "CU: the 'no' is the face and a small hand at the bottom of the frame",
            "face": [("brow_hold", ("W13", "can't"), {"hold": 0.6}),
                     ("shake", ("W13", "can't"), {}),
                     ("smile", ("W13", "word"), {"amount": 0.6, "hold": 0.5, "shape": "closed, knowing"})],
            "gestures": [("wave_off", "R", ("W13", "can't"), {"size": "small", "target": "camera",
                                                              "note": "palm out, a small side-to-side 'no'"}),
                         ("beat", "R", ("W13", "word"), {"size": "small", "target": "camera"})],
            "lean": [(("W13", "And"), 6)],
        },
        "W14": {
            "arc": "body", "emotion": "confident trust", "intensity": 0.7, "off_cam": True,
            "base": {"smile": 0.3, "brows": 0.05},
            "face": [("brow_flash", ("W14", "Signal"), {}),
                     ("smile", ("W14", "keys"), {"amount": 0.5, "hold": 0.4, "shape": "closed"}),
                     ("nod", ("W14", "phones."), {})],
            "gestures": [("open_palm", "R", ("W14", "Signal"), {"size": "small", "target": "camera"}),
                         ("point_viewer", "R", ("W14", "your"), {"size": "small", "target": "camera"})],
            "lean": [(("W14", "your"), 5)],
        },
        "W15": {
            "arc": "body", "emotion": "clear, a neat detail", "intensity": 0.7,
            "base": {"smile": 0.25, "brows": 0.05},
            "face": [("glance", ("W15", "Photos"), {"dir": "his left, to the panel", "dur": 0.4,
                                                    "note": "agent-04's THINK beat, with the deictic"}),
                     ("brow_flash", ("W15", "blob"), {}),
                     ("nod", ("W15", "encrypted.", 1, 0.3), {}),
                     ("brow_flash", ("W15", "Only"), {}),
                     ("smile", ("W15", "key"), {"amount": 0.5, "hold": 0.4, "shape": "lopsided R"})],
            "gestures": [
                ("deictic", "R", ("W15", "Photos"), {"size": "small", "target": "panel (his left)",
                                                     "note": "cross-body, under the mic head"}),
                ("place", "both", ("W15", "store,"), {"size": "medium", "target": "front", "hold": 0.5,
                                                      "note": "sets a box down in front of him"}),
                ("pinch", "R", ("W15", "Only"), {"size": "small", "target": "camera", "hold": 0.6,
                                                 "note": "just the key: thumb and index"}),
                ("open_palm", "R", ("W15", "message."), {"size": "small", "target": "front"}),
            ],
            "lean": [(("W15", "Only"), 6)],
        },
        "W16": {
            "arc": "payoff", "emotion": "satisfied, the three ideas land", "intensity": 0.8,
            "base": {"smile": 0.35, "brows": 0.05},
            "face": [("brow_flash", ("W16", "Tiny"), {}),
                     ("nod", ("W16", "processes."), {}),
                     ("brow_flash", ("W16", "Messages"), {}),
                     ("shake", ("W16", "don't"), {}),
                     ("smile", ("W16", "linger."), {"amount": 0.5, "hold": 0.4, "shape": "open lips"}),
                     ("brow_flash", ("W16", "Keys"), {}),
                     ("smile", ("W16", "hands."), {"amount": 0.85, "hold": 0.5, "note": "full Duchenne (payoff 4/5)"}),
                     ("nod", ("W16", "hands."), {})],
            "gestures": [
                ("count", "R", ("W16", "Tiny"), {"size": "small", "target": "his right, chest height",
                                                 "note": "index (1)"}),
                ("count", "R", ("W16", "Messages"), {"size": "medium", "target": "his right, chest height",
                                                     "note": "+ middle (2)"}),
                ("count", "R", ("W16", "Keys"), {"size": "medium", "target": "his right, chest height",
                                                 "hold": 0.5, "note": "+ ring (3)"}),
                ("open_palm", "both", ("W16", "hands."), {"size": "medium", "target": "front", "hold": 0.6,
                                                          "note": "both palms up, showing his hands: literal"}),
            ],
            "lean": [(("W16", "Tiny"), 4), (("W16", "Keys"), 7)],
        },
        "W17": {
            "arc": "payoff", "emotion": "satisfied delight, the bookend", "intensity": 0.9,
            "base": {"smile": 0.55, "brows": 0.05},
            "face": [("brow_flash", ("W17", "That's"), {}),
                     ("smile", ("W17", "billion"), {"amount": 0.9, "hold": 1.0,
                                                    "note": "full Duchenne (payoff 5/5), held into the cut"}),
                     ("tilt", ("W17", "day."), {"side": "R", "deg": 5}),
                     ("nod", ("W17", "day."), {})],
            "gestures": [("size", "both", ("W17", "billion"), {"start": ("W17", "hundred"), "size": "medium",
                                                               "target": "front",
                                                               "note": "the hook's spread again, smaller (CU)"}),
                         ("release", "both", ("W17", "day."), {"size": "small", "target": "front", "hold": 1.0,
                                                               "note": "palms open, held to the cut"})],
            "lean": [(("W17", "That's"), 6)],
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
}, "whatsapp": {
    "spans": [{"camera": "CAM_MCU", "f0": 0, "f1": 179, "lines": ["W01", "W02", "W03"],
               "why": "his hook on one camera: the 'hundred billion' spread, the one brow, the twist and 'Here's how'"},
              {"camera": "CAM_WIDE", "f0": 422, "f1": 480, "lines": ["W07"],
               "why": "his WIDE: hands up, elbows off the torso, the playful question"}],
    "optional": {"camera": "CAM_MCU", "f0": 179, "f1": 273, "lines": ["W04"],
                 "why": "append for the first panel deictic (+3.9 s)"},
}}

# ------------------------------------------------------------------------------------------------ resolve

DUR = {"brow_flash": 0.45, "brow_one": 0.8, "brow_hold": 0.9, "smile": 0.6, "smile_soft": 0.8, "squint": 0.4,
       "nod": 0.35, "tilt": 1.2, "glance": 0.4, "shake": 0.5}
LEAD = {"brow_flash": 0.12, "brow_one": 0.15, "brow_hold": 0.12, "smile": 0.30, "smile_soft": 0.35, "squint": 0.15,
        "nod": 0.15, "tilt": 0.25, "glance": 0.10, "shake": 0.15}
AMP = {"small": 0.3, "medium": 0.55, "big": 0.85}  # stroke amplitude 0-1 (overridable per gesture)
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
                 "size": x.get("size", "medium"), "amp": x.get("amp", AMP[x.get("size", "medium")]),
                 "held": x.get("hold", 0.25) >= 0.5, "target": x.get("target", "camera"),
                 "apex_height": x.get("height", apex_height(where[ln["id"]]["camera"], spec.get("off_cam", False),
                                                            x.get("size", "medium")))}
            if "start" in x:
                st, sw = word_t(lines, x["start"])
                g["prep_t"], g["prep_f"], g["start_word"] = round(st - 0.15, 3), fr(st - 0.15), sw
            for k in ("item", "of"):  # a LIST gesture's place on its line (agent-01's list kind)
                if k in x:
                    g[k] = x[k]
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
            v["smile"].append({**ref(f), "kind": "duchenne" if f.get("amount", 0) >= 0.8 else "soft",
                               "amount": f.get("amount"), "hold_s": f.get("hold"), "shape": f.get("shape")})
        elif k == "smile_soft":
            v["warm"].append({**ref(f), "amount": f.get("amount")})
        elif k == "nod":
            v["nod"].append({**ref(f), "kind": "yes"})
        elif k == "tilt":
            v["tilt"].append({**ref(f), "deg": f["deg"], "side": f["side"]})
        else:
            v[k].append({**ref(f), **({"dir": f["dir"], "dur_s": f["dur"]} if k == "glance" else {})})
    return {k: x for k, x in v.items() if x != []}


# Gesture space (orchestrator, side A review): the apex of a stroke sits chest-to-chin in front of the torso, never at
# desk height. agent-10's framing check (her gesture plane): CAM_MCU's bottom edge is at her sternum point (z 85),
# CAM_CU's above her shoulders (z 102). So in MCU a small beat peaks at the sternum (the hand at the frame's edge),
# medium/big at the upper chest and collarbone (the hands in the frame's lower third); in CU the strokes sit at the
# collarbone (ruling (a): nothing at the chin). Heights, low to high: bust, lower_chest, sternum, upper_chest, collarbone, chin.
HEIGHT = {"CAM_MCU": {"small": "sternum", "medium": "upper_chest", "big": "collarbone"},
          "CAM_MCU_L": {"small": "sternum", "medium": "upper_chest", "big": "collarbone"},
          "CAM_CU": {"small": "collarbone", "medium": "collarbone", "big": "collarbone"},
          "CAM_WIDE": {"small": "lower_chest", "medium": "sternum", "big": "upper_chest"},
          None: {"small": "sternum", "medium": "upper_chest", "big": "collarbone"},  # a gfx line kept on camera: MCU
          #  heights (the TEST span plays N03 on CAM_MCU, and the next shot can open mid-gesture)
          "off": {"small": "sternum", "medium": "sternum", "big": "sternum"}}  # off_cam lines: nobody sees them
# The orchestrator (agent-01's elbow ruling, ee99f626): high apexes are for emphasis. Most strokes sit at mid/lower chest,
# with the collarbone only on the sheet's key beats and the CU moments, and at most ~1/3 at or above the upper chest
# (ELEV_STROKE 60 deg only there). So off-camera strokes stay at the sternum, and a few non-key visible ones are pinned
# there too ("height": the N06/N12 panel opens, the N15 beat, his W10/W11 counts). checks() reports the share.
# The orchestrator's ruling (a), 08 Nov: key beats top out at the upper chest/collarbone (the wrist <= ~22 cm over the
# sternum point; a chin apex needed 70-78 deg of upper-arm lift against the 60 deg line), nothing at the chin.
# The orchestrator's verdict on her verify (netflix_r7H): no hand or finger above the chin or within ~10 cm of the
# face/hair in any cut camera (no sheet line calls for a face gesture); the 'million' size spreads and the N02
# release sit at the upper chest, and the N02 press pushes forward from below.
# R7 hands (agent-08's brief, item 3): no finger counting where a list will do. Her N13 and his W10/W11 LIST: an open
# hand placing each item along a line in front at chest height, held <= 0.6 s; no hold at the shoulder with the
# forearm vertical.
HIGH = ("upper_chest", "collarbone", "chin")
# hands_in_frame_frac (>= 1 hand fully in frame, of the speaking frames), per camera: agent-09's gate row
IN_FRAME = {"CAM_MCU": 0.6, "CAM_MCU_L": 0.6, "CAM_CU": 0.3, "CAM_WIDE": 1.0}


def apex_height(camera: str | None, off_cam: bool, size: str) -> str:
    return HEIGHT["off" if off_cam else camera][size]


BODY_TYPE = {"beat": "beat", "open_palm": "open", "release": "open", "point_viewer": "open", "sweep": "open",
             "count": "count", "list": "list", "deictic": "deictic", "size": "size", "pinch": "size", "ladder": "size",
             "place": "size", "carry": "size", "high_low": "deictic", "press": "beat", "chop": "beat",
             "wave_off": "deictic", "raise_finger": "beat"}


def body01(row: dict) -> dict:
    """agent-01's shape: type in beat|open|count|list|deictic|size (`detail` keeps the sheet's own name), hand r|l|both."""
    g = [{"type": BODY_TYPE[x["type"]], "detail": x["type"], "hand": x["hand"].lower(), "word": x["word"],
          "word_i": x["word_i"], "stroke_t": x["stroke_t"], "prep_t": x["prep_t"], "hold_s": x["hold_s"],
          "size": x["size"], "amp": x["amp"], "held": x["held"], "target": x["target"],
          "apex_height": x["apex_height"], **{k: x[k] for k in ("item", "of") if k in x}} for x in row["gestures"]]
    return {"line": row["id"], "on_cam": row["on_cam"], "camera": row["camera"], "gestures": g,
            "hands_in_frame_min": IN_FRAME.get(row["camera"]) if row["on_cam"] else None,
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
                    if p["type"] == x["type"] and p["type"] not in ("beat", "count", "list", "size")]
    return {"speaking_s": round(speak, 2), "smiles_per_min": round(smiles / speak * 60, 1),
            "brow_flash_per_min": round(brows / speak * 60, 1),
            "gesture_onsets_per_s": {"all": round(sum(len(ln["gestures"]) for ln in a["lines"]) / speak, 2),
                                     "per_line": rates},
            "neutral_hold_max_s": {"max": max(holds.values()), "per_line": holds},
            "same_gesture_twice": repeats,
            "apex_high_share": round(sum(g["apex_height"] in HIGH for ln in a["lines"] for g in ln["gestures"])
                                     / max(1, sum(len(ln["gestures"]) for ln in a["lines"])), 3),
            "on_cam_lines": [ln["id"] for ln in on]}


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
            + (f" {f['amount']}" if "amount" in f else "") + (f" ({f['shape']})" if "shape" in f else "")
            + f" on *{f['word']}* {f['t']:.2f} s (f{f['f']})"
            + (f" ({f['note']})" if "note" in f else "") for f in ln["face"]))
        o.append("- **Gestures:** " + "; ".join(
            f"{g['type'].replace('_', ' ')} [{g['hand']}, {g['size']} {g['amp']}, to {g['target']}]"
            + (f" HELD {g['hold_s']} s" if g["held"] else "") + f" stroke on *{g['word']}* "
            f"{g['stroke_t']:.2f} s (f{g['stroke_f']}), apex at the {g['apex_height'].replace('_', ' ')}, prep from {g['prep_t']:.2f}"
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

**Smiles:** a warm base (0.2-0.4) all the way through; FULL Duchenne (>= 0.8: cheeks up, eyes squint) only on the
five payoffs; mid-line smiles 0.4-0.6, varied in shape and asymmetry. Confident, not giddy. **Gestures:** the
amplitude varies (`amp` 0-1: small 0.3, medium 0.55, big 0.85), and the HELD strokes keep the shape after the stroke
for `hold_s` before retracting: deliberate, confident.

**Gesture space (side A review, agent-10's framing check):** the apex of every stroke sits chest-to-collarbone in front of
the torso, never at desk height. `CAM_MCU`'s bottom edge is at her sternum (z 85 on her gesture plane): small beats
peak at the sternum (the hand at the edge), medium at the upper chest, big at the collarbone, so the hands sit in the
frame's lower third. `CAM_CU`'s bottom edge is above her shoulders (z 102): its strokes at the collarbone, never the
chin (the orchestrator's ruling (a): the wrist <= ~22 cm over the sternum point). At most ~1/3 of the strokes sit at or
above the upper chest (`apex_high_share`): off-camera strokes stay at the sternum. Each gesture carries its `apex_height`; each on-camera line its `hands_in_frame_min` (at least
one hand fully in frame: MCU/MCU_L 0.6, CU 0.3, WIDE 1.0 of the speaking frames). The high rest is hands together at
the sternum, at the MCU frame's edge.

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
    parts = []
    for sheet in (HER, HIM):
        a = resolve(sheet)
        (HERE / "acting" / f"{sheet['who']}.json").write_text(json.dumps(a, indent=1) + "\n")
        parts.append(md(a))
        c = a["checks"]
        print(sheet["who"], json.dumps({k: (v["all"] if k == "gesture_onsets_per_s" else v["max"]
                                            if k == "neutral_hold_max_s" else v) for k, v in c.items()
                                        if k != "on_cam_lines"}))
    (HERE / "ACTING.md").write_text(HEAD + "\n".join(parts))


if __name__ == "__main__":
    main()
