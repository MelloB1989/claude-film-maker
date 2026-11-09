"""Round 7 (agent-04): the presenter's FACE acts. The operator rejected her v2b: "her expression is pale, no emotion at
all". Our solves were mouth-only and the face plan added only random brow flashes. This module turns a per-line acting
sheet (agent-11's acting/<who>.json, or the DRAFT below until it lands) into perf.face expression events on exact
words: brow flashes, Duchenne smiles (corner pull + cheek raise + eye squint, the cheek and squint a beat after the
mouth), a curious one-brow look with a head tilt, warmth. Between them, filler keeps the face changing every 2-4 s,
with no neutral hold over ~1.2 s while she speaks. head.py merges the result into the face plan, so perform.py's face
step needs nothing new.

What stays as round 6 proved:
- the lip-sync: an expression's mouth share is the corner pull and dimple only, scaled by `MOUTH_MIX` under a talking
  mouth. The jaw and upper lip (an open smile) move only in pauses, and stop `LIP_CLEAR_S` before the next word;
- blink_head still: the expressions add no head motion, and tilt ease windows are kept free of blinks;
- the eyes: no expression drives eyeLook, so gaze and the lock are untouched.

Tilts are agent-01's (on the body: the face's roll curve does not move the head on the live face). They go to
acting/tilts_<who>.json, roll + = toward her own right shoulder.

    cd tools && uv run python ../films/host-studio/explainers/acting.py plan --who her [--lines N01-N04,N13]
    cd tools && uv run python ../films/host-studio/explainers/acting.py check --who her [--lines ...]

`check` is the offline pre-check: perfkit's face.build with these events on her voice, measured as agent-09's
face.curves_* rows (active >= 0.15; smile = corner pull >= 0.25 with cheek >= 0.2; a brow flash is a rise >= 0.2 for
< 1.2 s; neutral hold = the longest speaking run with nothing active), absolute and relative to each channel's 20th
percentile (the render gate's neutral).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from itertools import groupby
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "unreal" / "fmbridge"))
sys.path.insert(0, str(HERE))
from perfkit import audio as AU  # noqa: E402
from perfkit import face as FACE  # noqa: E402
from perfkit.rig import MOUTH, PREFIX  # noqa: E402

FILM = {"him": "whatsapp", "her": "netflix"}
SEED = {"him": 81, "her": 82}
MOUTH_MIX = 0.75     # an expression's mouth share while the mouth talks (perf.face mouth_mix; r6 default 0.5)
LIP_CLEAR_S = 0.15   # a jaw/upper-lip expression (open smile) is gone this long before the next word
FILL_GAP_S = 0.7     # speaking time with nothing active before a filler starts at the next word
CAMERA_SIDE = "R"    # the cameras are at her right-front: a one-sided look reads on that side

# Recipes as perfkit expression presets ({raw curve: (weight, delay_s)}, "*" both sides), fractions of full range.
# Duchenne: AU12 (corner pull) with AU6 (cheek raise / orbicularis oculi) a beat later; a polite smile is AU12 alone.
RECIPES = {
    "duchenne": {"mouthCornerPull*": (0.75, 0.0), "eyeCheekRaise*": (0.7, 0.08), "eyeSquintInner*": (0.35, 0.1),
                 "noseNasolabialDeepen*": (0.3, 0.05), "mouthDimple*": (0.12, 0.0), "browRaiseOuter*": (0.08, 0.05)},
    "open_smile": {"mouthCornerPull*": (0.7, 0.0), "eyeCheekRaise*": (0.65, 0.07), "eyeSquintInner*": (0.32, 0.1),
                   "noseNasolabialDeepen*": (0.3, 0.04), "mouthUpperLipRaise*": (0.15, 0.03), "jawOpen": (0.08, 0.0),
                   "browRaiseOuter*": (0.1, 0.05)},
    "warm": {"mouthCornerPull*": (0.4, 0.0), "eyeCheekRaise*": (0.35, 0.1), "eyeSquintInner*": (0.15, 0.12),
             "mouthDimple*": (0.08, 0.0)},
    "brow_flash": {"browRaiseIn*": (0.55, 0.0), "browRaiseOuter*": (0.6, 0.01), "eyeWiden*": (0.08, 0.02)},
    "question": {"browRaiseIn*": (0.65, 0.0), "browRaiseOuter*": (0.75, 0.0), "eyeWiden*": (0.15, 0.02),
                 "mouthCornerPull*": (0.15, 0.1)},
    # curious / conspiratorial: the camera-side brow up, the other eye a touch narrowed, a half smile
    "curious": {f"browRaiseOuter{CAMERA_SIDE}": (0.6, 0.0), f"browRaiseIn{CAMERA_SIDE}": (0.35, 0.0),
                f"browRaiseOuter{'L' if CAMERA_SIDE == 'R' else 'R'}": (0.12, 0.02),
                f"eyeSquintInner{'L' if CAMERA_SIDE == 'R' else 'R'}": (0.2, 0.05),
                f"mouthCornerPull{CAMERA_SIDE}": (0.3, 0.08), f"eyeCheekRaise{CAMERA_SIDE}": (0.2, 0.1)},
    "squint_smile": {"eyeSquintInner*": (0.35, 0.0), "eyeCheekRaise*": (0.35, 0.03), "mouthCornerPull*": (0.3, 0.0)},
    # a pleasant resting face under it all (the confident presenter's baseline; the gate's 20th percentile)
    "base": {"mouthCornerPull*": (0.12, 0.0), "eyeCheekRaise*": (0.08, 0.05)},
}
OPEN = {"open_smile"}  # recipes with jaw/upper lip: pauses only
FILLERS = ["warm", "brow_flash", "squint_smile", "curious", "brow_flash", "warm"]

# The sheet's conventions (agent-11, acting/<who>.json "conventions"): each beat's apex `t` is the stressed syllable;
# the expression starts lead_s before it and holds dur_s from its start (or the beat's own hold_s after the apex).
LEAD = {"brow": 0.12, "question": 0.15, "curious": 0.15, "smile": 0.3, "soft": 0.35, "warm": 0.35, "squint": 0.15,
        "open": 0.0}
DUR = {"brow": 0.45, "question": 0.7, "curious": 0.9, "smile": 0.6, "soft": 0.8, "warm": 0.8, "squint": 0.4,
       "open": 0.0}
# kind: (recipe, attack_s, release_s)
# a Duchenne's onset is slow, 8-15 frames (r7 research, agent-04:2 FACE_RESEARCH.md): 0.4 s
KINDS = {"brow": ("brow_flash", 0.12, 0.35), "question": ("question", 0.14, 0.45), "smile": ("duchenne", 0.4, 0.6),
         "soft": ("warm", 0.25, 0.5), "warm": ("warm", 0.3, 0.6), "curious": ("curious", 0.25, 0.5),
         "squint": ("squint_smile", 0.15, 0.4), "open": ("open_smile", 0.25, 0.45)}
# the orchestrator's calibration (07 Nov): a full Duchenne (>= 0.8) only on the payoffs; mid-line smiles 0.4-0.6,
# varied and asymmetric, over a warm 0.2-0.4 base
PAYOFFS = {"her": {("N01", "members"), ("N02", "starts"), ("N07", "near"), ("N13", "aws"), ("N16", "just"),
                   ("N16", "plays")},
           "him": {("W01", "messages"), ("W03", "how"), ("W11", "read"), ("W16", "hands"), ("W17", "billion")}}
# The audio solve (the orchestrator, 07 Nov, after the operator's tutorial + Epic's audio-driven animation docs): FULL
# FACE with a solver mood per line, blinks and head off, so the solve moves brows, cheeks and lids with the speech; the
# word-timed events above ride on it as an additive layer (perf.face adds them to the solve's curves in a copy:
# the solve asset is untouched, the result is the baked face anim that renders). The mood per line follows the arc:
# hook playful, body confident, payoff lines excited, the "Network dips?" question a light surprise.
FULL_SOLVE = os.environ.get("FACE_SOLVE", "full") == "full"  # FACE_SOLVE=mouth: round 6's mouth-only solves (the A/B)
SOLVE_MOOD = {
    "her": {**{k: ("PLAYFULNESS", 0.65) for k in ("N01", "N02")}, "N03": ("PLAYFULNESS", 0.6),
            **{k: ("CONFIDENCE", 0.5) for k in ("N04", "N05", "N06", "N08", "N09", "N10", "N11", "N14")},
            "N12": ("SURPRISE", 0.3), "N13": ("CONFIDENCE", 0.55),
            **{k: ("EXCITEMENT", 0.8) for k in ("N07", "N15", "N16")}},  # payoffs 0.8-1.0 (FACE_RESEARCH.md)
    # him (agent-11's acting/him.json, the orchestrator: "warmer/playful"): hook W01-W03 playful, the body HAPPINESS
    # as his sheet has it (warmer than her confident), the "read" reveal and the payoff lines W16-W17 excited; his set
    # has the cameras on his right too (set_him.json), so CAMERA_SIDE holds
    "him": {**{k: ("PLAYFULNESS", 0.65) for k in ("W01", "W02")}, "W03": ("PLAYFULNESS", 0.7),
            **{k: ("HAPPINESS", 0.5) for k in ("W04", "W05", "W06", "W08", "W09", "W12", "W14", "W15")},
            "W07": ("PLAYFULNESS", 0.55), "W10": ("PLAYFULNESS", 0.55), "W13": ("HAPPINESS", 0.6),
            "W11": ("EXCITEMENT", 0.7), **{k: ("EXCITEMENT", 0.8) for k in ("W16", "W17")}},
}
SOLVE_DEFAULT = ("CONFIDENCE", 0.5)
BASE_UNDER_SOLVE = 0.5  # the warm base's share over a full-face solve (its mood already smiles)


def solve_mood(who: str, lid: str) -> tuple:
    """(mood, intensity) for line `lid`'s audio solve (speech.to_face mood=, intensity=)."""
    return SOLVE_MOOD.get(who, {}).get(lid, SOLVE_DEFAULT)


# perform.py SPEECH_GAIN (his rig gives little mouth travel, r4): perf.face's speech_gain multiplies the mouth curves
# (rig.MOUTH: mouth*, jaw*, ...) of the finished face, ours included, so a smile's mouth weights are divided by it
# his head: the acting nods at half depth (09 Nov, T-d: head.drift_deg 2.668 against 1.5; head_stages put it on the
# sync's face head; offline (perfkit.head.compose) the acting nods took his drift 0.6 -> 2.8 and the beat nods to 3.5)
NOD_SCALE = {"him": 0.5}
MOUTH_GAIN = {"him": 1.7}
MID_SMILE = (0.4, 0.6)
BASE_SMILE = (0.2, 0.4)
DEFAULT_AMOUNT = {"brow": 0.85, "question": 0.9, "curious": 0.85, "smile": 0.55, "soft": 0.5, "warm": 0.5,
                  "squint": 0.6, "open": 0.85}

# A draft in the sheet's face04 shape (word by text; apex = the word's onset + 0.1 s) for a presenter with no sheet.
DRAFT = {
    "her": {
        "N01": {"emotion": "curious", "brow": ["Netflix"], "curious": ["over"], "smile": [["members", "duchenne", 0.85]]},
        "N02": {"emotion": "delight", "brow": ["Hit"], "smile": [["starts", "duchenne", 0.9]], "pause_smile": True},
        "N03": {"emotion": "curious", "curious": ["But"], "warm": ["cloud"]},
    },
}


def cue(who: str) -> dict:
    return json.loads((HERE / "cues" / f"{who}.json").read_text())


def _norm(w: str) -> str:
    return "".join(ch for ch in w.lower() if ch.isalnum() or ch == "'")


def lines(cu: dict) -> dict:
    """{line id: [word dicts]} in time order."""
    return {k: list(g) for k, g in groupby(cu["words"], key=lambda w: w["line"])}


def _word(cu: dict, lid: str, ref) -> dict:
    """A word by its index in cue["words"] (word_i), or by its text in the line."""
    if isinstance(ref, dict):
        if "word_i" in ref:
            return cu["words"][ref["word_i"]]
        ref = ref.get("word")
    if isinstance(ref, int):
        return cu["words"][ref]
    words = lines(cu)[lid]
    for w in words:
        if _norm(w["w"]) == _norm(ref):
            return w
    raise ValueError(f"no word {ref!r} in {lid}: {' '.join(w['w'] for w in words)!r}")


def beats(who: str) -> dict:
    """{line id: {"emotion", "base", "pause_smile", "beats": [{"kind", "word", "apex", "amount", "hold_s", "side",
    "deg"}]}} from agent-11's sheet (lines[].face04 and .base), else the DRAFT."""
    cu = cue(who)
    p = HERE / "acting" / f"{who}.json"
    src = {}
    if p.exists():
        for ln in json.loads(p.read_text()).get("lines", []):
            f = dict(ln.get("face04") or {})
            f["base"] = ln.get("base") or {}
            src[ln["id"]] = f
    else:
        for lid, f in DRAFT.get(who, {}).items():
            g = {"emotion": f.get("emotion", ""), "pause_smile": f.get("pause_smile", False)}
            for k in ("brow", "question", "curious", "warm", "squint", "nod", "tilt", "shake"):
                g[k] = [{"word": x} if isinstance(x, str) else {"word": x[0], "deg": x[1]} for x in f.get(k, [])]
            g["smile"] = [{"word": x[0], "kind": x[1], "amount": x[2]} for x in f.get("smile", [])]
            src[lid] = g
    out = {}
    for lid, f in src.items():
        bs = []
        for key in ("brow", "question", "curious", "smile", "warm", "squint", "nod", "tilt", "shake"):
            for item in f.get(key, []):
                w = _word(cu, lid, item)
                apex = float(item.get("t", w["t0"] + 0.1))
                kind = key
                if key == "smile":
                    kind = "smile" if item.get("kind", "duchenne") == "duchenne" else "soft"
                if key == "curious" and item.get("kind") == "brows_held":
                    kind = "question"
                bs.append({"kind": kind, "word": w, "apex": apex, "amount": item.get("amount"),
                           "shape": item.get("shape") or "",
                           "hold_s": item.get("hold_s"), "side": item.get("side"), "deg": item.get("deg"),
                           "nod_kind": item.get("kind") if key == "nod" else None})
        out[lid] = {"emotion": f.get("emotion", ""), "base": f.get("base") or {},
                    "pause_smile": bool(f.get("pause_smile")) or lid in ("N02", "N16"), "beats": bs}
    return out


def _next_word_t(cu: dict, t: float) -> float:
    nxt = [w["t0"] for w in cu["words"] if w["t0"] > t + 1e-3]
    return min(nxt) if nxt else cu["length_s"]


def _ev(kind: str, apex: float, rng: random.Random, amount: float | None = None, hold_s: float | None = None,
        side: str | None = None, until: float | None = None) -> dict:
    recipe, att, rel = KINDS[kind]
    rec = dict(RECIPES[recipe])
    if kind == "curious" and side and side != CAMERA_SIDE:  # the sheet's side wins: mirror the one-sided look
        rec = {(n[:-1] + ("L" if n.endswith("R") else "R")) if n[-1] in "LR" else n: v for n, v in rec.items()}
    t = apex - LEAD[kind]
    end = until if until is not None else (apex + hold_s if hold_s else t + DUR[kind])
    k = amount if amount is not None else DEFAULT_AMOUNT[kind]
    asym = rng.uniform(-0.35, 0.35)
    return {"preset": rec, "name": kind, "t": round(t, 3), "until": round(max(end, t + att), 3),
            "intensity": round(k * rng.uniform(0.93, 1.07), 3), "attack_s": att, "release_s": rel, "sustain": 0.85,
            "asym": round(asym, 2)}


def speaking(cu: dict, gap: float = 0.3) -> list:
    """[(t0, t1)] speaking runs: words merged across gaps under `gap` s."""
    out = []
    for w in cu["words"]:
        if out and w["t0"] - out[-1][1] < gap:
            out[-1][1] = w["t1"]
        else:
            out.append([w["t0"], w["t1"]])
    return [tuple(x) for x in out]


def _amount(who: str, lid: str, b: dict, rng: random.Random, notes: list) -> float | None:
    """The orchestrator's calibration of a smile's amount: a full Duchenne (>= 0.8) only on a payoff (the sheet's kind
    "duchenne"), every other smile 0.4-0.6."""
    if b["kind"] not in ("smile", "soft"):
        return b["amount"]
    if b["kind"] == "smile":
        if PAYOFFS.get(who) and (lid, _norm(b["word"]["w"])) not in PAYOFFS[who]:
            notes.append(f"{lid} {b['word']['w']}: a full Duchenne off the payoff list")
        return max(0.8, b["amount"] or 0.85)
    a = b["amount"] if b["amount"] is not None else rng.uniform(*MID_SMILE)
    return round(min(MID_SMILE[1], max(MID_SMILE[0], a)) * rng.uniform(0.95, 1.05), 3)


def shaped(e: dict, shape: str) -> dict:
    """A smile event shaped as the sheet says (agent-11's "shape": lopsided L/R, sly, amused, closed, open lips).
    The mouth share stays the corner pull and dimple: "open lips" opens them only in a pause, never over speech."""
    sh = shape.lower()
    rec = dict(e["preset"])
    if "lopsided l" in sh:
        e["asym"] = 0.8
    elif "lopsided r" in sh:
        e["asym"] = -0.8
    if "sly" in sh:  # the camera-side eye narrows a touch more, a hint of the brow
        rec[f"eyeSquintInner{CAMERA_SIDE}"] = (0.3, 0.08)
        rec[f"browRaiseOuter{'L' if CAMERA_SIDE == 'R' else 'R'}"] = (0.15, 0.05)
    if "amused" in sh:
        for side in "LR":
            rec[f"eyeCheekRaise{side}"] = (0.5, 0.08)
    e["preset"] = rec
    e["shape"] = shape
    return e


def plan(who: str, only: set | None = None) -> dict:
    """{"expressions", "nods", "tilts", "avoid_blinks", "mouth_mix", "brow_chance", "notes"} for perf.face (whole take;
    `only` keeps the events of those lines: a test)."""
    cu = cue(who)
    rng = random.Random(SEED[who])
    ev, nods, tilts, notes = [], [], [], []
    by_line = lines(cu)
    for lid, L in beats(who).items():
        if only and lid not in only:
            continue
        words = by_line[lid]
        t0, t1 = words[0]["t0"], words[-1]["t1"]
        nxt = _next_word_t(cu, t1)
        base = min(BASE_SMILE[1], max(BASE_SMILE[0], float(L["base"].get("smile", 0.3))))
        if FULL_SOLVE:
            base *= BASE_UNDER_SOLVE
        # the warm base over the line (ramps in before the first word, out in the pause after)
        ev.append({"preset": RECIPES["warm"], "name": "base", "t": round(t0 - 0.45, 3),
                   "until": round(min(t1 + 0.3, nxt - 0.2), 3), "intensity": round(base, 3), "attack_s": 0.4,
                   "release_s": 0.5, "sustain": 0.95, "alive": 0.12, "asym": round(rng.uniform(-0.25, 0.25), 2)})
        for b in L["beats"]:
            k = b["kind"]
            if k in KINDS:
                e = _ev(k, b["apex"], rng, _amount(who, lid, b, rng, notes), b["hold_s"], b["side"])
                if b["shape"]:
                    e = shaped(e, b["shape"])
                if k in ("smile", "soft") and b["word"] is not words[-1]:
                    e["until"] = round(max(e["t"] + 0.3, min(e["until"], _next_word_t(cu, b["word"]["t1"]) + 0.6)), 3)
                ev.append(e)
            elif k == "nod":
                nods.append({"t": round(b["apex"] - 0.15, 3), "kind": "nod", "depth_deg": 2.5 * NOD_SCALE.get(who, 1.0)})
            elif k == "shake":
                nods.append({"t": round(b["apex"] - 0.15, 3), "kind": "shake", "depth_deg": 3.0 * NOD_SCALE.get(who, 1.0)})
            elif k == "tilt":
                deg = float(b["deg"] or 4.0) * (1.0 if (b["side"] or "R") == "R" else -1.0)
                tilts.append({"t": round(b["apex"] - 0.25, 3), "until": round(b["apex"] + 0.95, 3), "roll_deg": deg,
                              "ease_s": 0.4})
        if L["pause_smile"] and nxt >= cu["length_s"]:
            # the take's last line: a closed Duchenne held to the end. lipsync.check wants the mouth shut in the end
            # silence (box B, 08 Nov: the open smile's jaw read "opens 0.11 (allowed 0.1)" at f1386-1427)
            ev.append({**_ev("smile", t1 + 0.05, rng, 0.85, until=round(nxt - 0.3, 3)), "name": "smile_hold"})
        elif L["pause_smile"]:  # an open smile into the pause after the line (teeth; no lip-sync to keep)
            end = nxt - LIP_CLEAR_S - KINDS["open"][2]
            if end - t1 > 0.35:
                ev.append(_ev("open", t1 + 0.05, rng, 0.85, until=round(end, 3)))
            else:
                notes.append(f"{lid}: pause {nxt - t1:.2f} s too short for an open smile")
    ev = fill(cu, ev, rng, only)
    g = MOUTH_GAIN.get(who, 1.0)
    if g != 1.0:  # perform.py's speech_gain scales every mouth curve after the layer: keep the smiles' mouth share
        for e in ev:
            e["preset"] = {n: ((w[0] / g, w[1]) if n.startswith(("mouth", "jaw")) else w)
                           for n, w in e["preset"].items()}
    # no blink while a tilt eases in or out (r6: a blink on a tilt's release read as a nod)
    avoid = []
    for t in tilts:
        avoid += [[round(t["t"] - 0.1, 3), round(t["t"] + t["ease_s"] + 0.1, 3)],
                  [round(t["until"] - 0.1, 3), round(t["until"] + t["ease_s"] + 0.1, 3)]]
    return {"expressions": ev, "nods": nods, "tilts": tilts, "avoid_blinks": avoid, "mouth_mix": MOUTH_MIX,
            "brow_chance": 0.0, "notes": notes}


def _active_spans(ev: list) -> list:
    return sorted((e["t"] + e.get("attack_s", 0.25) * 0.5, e["until"]) for e in ev if e["name"] != "base")


def fill(cu: dict, ev: list, rng: random.Random, only: set | None = None) -> list:
    """Filler events so no speaking run goes over FILL_GAP_S with nothing active: at the next word onset after a gap,
    the next of FILLERS that differs from the last event's kind."""
    words = [w for w in cu["words"] if not only or w["line"] in only]
    last_kind = None
    k = rng.randrange(len(FILLERS))
    for a, b in speaking({**cu, "words": words}):
        t = a
        while t < b:
            act = [s for s in _active_spans(ev) if s[1] > t]
            nxt_on = min([s[0] for s in act], default=b + 9)
            cover = [s for s in act if s[0] <= t]
            if cover:
                t = max(s[1] for s in cover)
                continue
            if nxt_on - t <= FILL_GAP_S:
                t = nxt_on
                continue
            # a gap: the first word starting at or after t + 0.3 inside this run
            cands = [w for w in words if t + 0.3 <= w["t0"] < b - 0.2]
            if not cands:
                break
            w = cands[0]
            kind = FILLERS[k % len(FILLERS)]
            k += 1
            if kind == last_kind:
                kind = FILLERS[k % len(FILLERS)]
                k += 1
            last_kind = kind
            kk = {"warm": "warm", "brow_flash": "brow", "squint_smile": "squint", "curious": "curious"}[kind]
            e = _ev(kk, w["t0"] + 0.1, rng, DEFAULT_AMOUNT[kk] * (1.0 if kk == "brow" else 0.8))
            e["until"] = round(max(e["until"], w["t0"] + 0.9), 3)
            e["name"] = f"fill:{kind}"
            ev.append(e)
            t = e["until"]
    return sorted(ev, key=lambda e: e["t"])


# ------------------------------------------------------------------------------------------------------ pre-check

ROLES = {"brow": ("browRaiseIn", "browRaiseOuter"), "squint": ("eyeCheekRaise", "eyeSquintInner"),
         "smile": ("mouthCornerPull",)}
ACTIVE, SMILE_PULL, SMILE_CHEEK, FLASH_RISE, FLASH_MAX_S = 0.15, 0.25, 0.2, 0.4, 1.2  # brow 0.40: agent-09 (v2b 0)


def role_values(curves: dict, times: list) -> dict:
    """{role: [per-frame max over its curves, both sides]}."""
    from perfkit import curves as C
    out = {}
    for role, stems in ROLES.items():
        cols = [C.resample(*curves[n], times) for n in curves
                if n.startswith(PREFIX) and n[len(PREFIX):].rstrip("LR").startswith(stems) and curves[n][0]]
        out[role] = [max(c[i] for c in cols) if cols else 0.0 for i in range(len(times))]
    return out


def rows(curves: dict, cu: dict, only: set | None = None, fps: float = 24.0, relative: bool = False) -> dict:
    """agent-09's face.curves_* rows over the speaking frames."""
    words = [w for w in cu["words"] if not only or w["line"] in only]
    runs = speaking({**cu, "words": words})
    t0, t1 = runs[0][0], runs[-1][1]
    times = [t0 + i / fps for i in range(int((t1 - t0) * fps) + 1)]
    rv = role_values(curves, times)
    if relative:
        for role, col in rv.items():
            base = sorted(col)[int(0.2 * (len(col) - 1))]
            rv[role] = [max(0.0, v - base) for v in col]
    talk = [any(a <= t <= b for a, b in runs) for t in times]
    active = [max(rv[r][i] for r in rv) >= ACTIVE for i in range(len(times))]
    n_talk = sum(talk)
    frac = sum(1 for a, s in zip(active, talk) if a and s) / max(1, n_talk)
    hold, run, where = 0, 0, None
    for i, (a, s) in enumerate(zip(active, talk)):
        run = run + 1 if (s and not a) else 0
        if run > hold:
            hold, where = run, round(times[i] - run / fps, 2)
    smiles, on = 0, False
    for i in range(len(times)):  # with hysteresis: a held smile's drift across the line is one smile
        if not on and rv["smile"][i] >= SMILE_PULL and rv["squint"][i] >= SMILE_CHEEK:
            smiles, on = smiles + 1, True
        elif on and (rv["smile"][i] < 0.8 * SMILE_PULL or rv["squint"][i] < 0.8 * SMILE_CHEEK):
            on = False
    flashes, start = 0, None
    for i, v in enumerate(rv["brow"]):  # the same hysteresis as agent-09's render rows (off below 80 %)
        if v >= FLASH_RISE and start is None:
            start = i
        elif v < 0.8 * FLASH_RISE and start is not None:
            flashes += (i - start) / fps < FLASH_MAX_S
            start = None
    minutes = n_talk / fps / 60.0
    return {"expr_active_frac": round(frac, 3), "smile_per_min": round(smiles / minutes, 2),
            "brow_flash_per_min": round(flashes / minutes, 2), "neutral_hold_max_s": round(hold / fps, 2), "neutral_hold_at_s": where,
            "speaking_s": round(n_talk / fps, 2)}


LINES = {"expr_active_frac": (">=", 0.6), "smile_per_min": (">=", 4.0), "brow_flash_per_min": (">=", 6.0),
         "neutral_hold_max_s": ("<=", 1.5)}


def check(who: str, only: set | None = None) -> dict:
    """perfkit's face.build (expressions and brows only, on the voice) with plan(), measured as the gate's rows."""
    p = plan(who, only)
    cu = cue(who)
    wav = HERE / "audio" / FILM[who] / "vo.wav"
    env = AU.Envelope.from_wav(str(wav))
    r = FACE.build(0.0, cu["length_s"], base={}, layers=("expressions", "brows"), expressions=p["expressions"],
                   emphasis=env.emphasis(), speech=env.at, mouth_mix=p["mouth_mix"], brow_chance=p["brow_chance"],
                   seed=SEED[who], speech_gain=[(0.0, cu["length_s"], MOUTH_GAIN[who])] if who in MOUTH_GAIN else [])
    out = {"abs": rows(r["curves"], cu, only), "rel20": rows(r["curves"], cu, only, relative=True)}
    out["pass"] = all((v >= x if op == ">=" else v <= x) for m in ("abs", "rel20")
                      for k, (op, x) in LINES.items() for v in [out[m][k]])
    out["events"] = len(p["expressions"])
    out["mouth_curves"] = sorted({n[len(PREFIX):] for n in r["curves"] if n in MOUTH})
    out["notes"] = p["notes"]
    return out


# ------------------------------------------------------------------------------------- solve test (on the box)

def _sheet_line(who: str, lid: str) -> dict:
    p = HERE / "acting" / f"{who}.json"
    for ln in json.loads(p.read_text())["lines"] if p.exists() else []:
        if ln["id"] == lid:
            return ln
    return {}


def families(cur: dict) -> dict:
    """{curve family: peak} of a solve's curves (brow, cheek, squint, eyeLook, blink, mouth, head)."""
    fam = {"brow_up": ("browRaise",), "brow_hard": ("browDown", "browLateral"), "cheek": ("eyeCheekRaise",), "squint": ("eyeSquintInner",),
           "smile": ("mouthCornerPull",), "eyeLook": ("eyeLook",), "blink": ("eyeBlink",), "lids": ("eyeWiden",
           "eyeLidPress", "eyeRelax", "eyeUpperLid", "eyeLowerLid"), "jaw": ("jawOpen",)}
    out = {}
    for k, stems in fam.items():
        vals = [max(map(abs, v)) for n, (t, v) in cur.items() if v and n.startswith(PREFIX)
                and n[len(PREFIX):].startswith(stems)]
        out[k] = round(max(vals), 3) if vals else None
    out["head"] = round(max([max(map(abs, v)) for n, (t, v) in cur.items() if v and n.startswith("Head")
                             and n != "HeadControlSwitch"] or [0.0]), 3)
    return out


def solvetest(who: str, lid: str, intensity: float | None = None, mood_override: str = "") -> dict:
    """On box B (the driver runs it): line `lid` solved FULL FACE in its solve mood (SOLVE_MOOD), and MOUTH ONLY in the
    same mood, beside round 6's mouth-only CONFIDENCE solve (AS_exp_<lid>). For each: the non-mouth families' peaks, the
    gate's face rows over the line (as solved, no perfkit layer), the jaw against round 6's (the lips must not
    change), and lipsync.check of the full solve against its WAV (perform.py bias's call). Nothing is placed."""
    import perform as PF
    from perfkit import curves as C
    cl = PF.client()
    ln = next(x for x in PF.cues(who)["lines"] if x["id"] == lid)
    mood, k0 = solve_mood(who, lid)
    mood = mood_override or mood
    k = intensity if intensity is not None else k0
    mesh = PF.mesh_of(who, "Face")
    wav = PF.box(who, Path(ln["file"]).name)
    out = {"line": lid, "mood": mood, "intensity": k, "anims": {}}
    names = {"r6_mouth_confidence": PF.line_anim(lid)}
    for mask in ("full", "mouth"):
        r = PF.ok(cl.op("speech.to_face", wav=wav, name=f"exp_{lid}_{mask}_{mood.lower()}", face_mesh=mesh, mood=mood,
                        intensity=k, process_mask=mask, head=False, blinks=False, fallback=False, timeout=1800))
        names[f"{mask}_{mood.lower()}"] = r["anim"]
        out["anims"][f"{mask}_{mood.lower()}"] = {"anim": r["anim"], "options": r.get("options"),
                                                   "missing": r.get("missing_options"), "timing": r.get("timing")}
    words = [w for w in cue(who)["words"] if w["line"] == lid]
    off = ln["file_start"]  # the line WAV's t=0 on the take's clock
    lcue = {"words": [{**w, "t0": w["t0"] - off, "t1": w["t1"] - off} for w in words]}
    curves, jaw = {}, {}
    for key, anim in names.items():
        cur = {n: (tv[0], tv[1]) for n, tv in PF.ok(cl.op("anim.read_curves", anim=anim)).items()}
        curves[key] = cur
        out.setdefault("families", {})[key] = families(cur)
        out.setdefault("rows", {})[key] = rows(cur, lcue)
        jn = PREFIX + "jawOpen"
        if jn in cur:
            g = C.grid(0.0, ln["file_len"], 24.0)
            jaw[key] = C.resample(*cur[jn], g)
    ref = jaw.get("r6_mouth_confidence")
    if ref:
        out["jaw_vs_r6"] = {k2: round((sum((a - b) ** 2 for a, b in zip(v, ref)) / len(ref)) ** 0.5, 4)
                            for k2, v in jaw.items() if k2 != "r6_mouth_confidence"}
    fa = names[f"full_{mood.lower()}"]
    r = PF.ok(cl.op("lipsync.check", anim=fa, anim_frame=ln["file_start_f"], wav=wav, wav_frame=ln["file_start_f"],
                    lines=[{"id": lid, "f0": ln["start_f"], "f1": ln["end_f"]}], fps=PF.FPS,
                    reference=[{"anim": fa, "frame": ln["file_start_f"]}], timeout=600))
    out["lipsync_full"] = {"pass": r["pass"], "line": r["lines"].get(lid),
                           "issues": [i["message"] for i in r.get("issues", [])]}
    return out


def per_frame(cur: dict, length_s: float, fps: float = 24.0) -> dict:
    """{frame: {curve: value}} of the role curves (agent-09's qa_perf.face_rows_curves input), take frame = t * fps."""
    from perfkit import curves as C
    stems = tuple(x for v in ROLES.values() for x in v) + ("browDown", "browLateral")  # + agent-09's frown_frac
    names = [n for n in cur if n.startswith(PREFIX) and n[len(PREFIX):].startswith(stems) and cur[n][0]]
    fr = list(range(int(length_s * fps) + 1))
    cols = {n: C.resample(*cur[n], [f / fps for f in fr]) for n in names}
    return {f: {n: round(cols[n][i], 4) for n in names} for i, f in enumerate(fr)}


def boxcheck(who: str, anim: str, only: set | None = None, spans: str = "") -> dict:
    """The gate's face rows on what the box made (default the final face, AS_exp_<who>_gaze: solve + perfkit + gaze),
    over the speaking frames (the test lines with `only`). Also saves the role curves per frame
    (out/explainers/face/<who>/frames_<anim name>.json) for agent-09's qa_perf.face_rows_curves on `spans`
    (spans_<film>.json), whose rows are printed too when that module is in the tree."""
    import perform as PF
    cur = {n: (tv[0], tv[1]) for n, tv in PF.ok(PF.client().op("anim.read_curves", anim=anim)).items()}
    cu = cue(who)
    out = {"anim": anim, "abs": rows(cur, cu, only), "rel20": rows(cur, cu, only, relative=True)}
    fr = per_frame(cur, cu["length_s"])
    p = ROOT / "out" / "explainers" / "face" / who / f"frames_{anim.rsplit('/', 1)[-1]}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fr))
    out["frames_file"] = str(p)
    if spans:
        try:
            from filmtools.unreal import qa_perf as Q
            out["gate09"] = Q.face_rows_curves(fr, 24.0, json.loads(Path(spans).read_text()))
        except ImportError:
            out["gate09"] = "qa_perf not in this tree (fleet/agent-09/r7-perf-gate): send frames_file to agent-09"
    out["pass"] = all((out[m][k] >= x if op == ">=" else out[m][k] <= x) for m in ("abs", "rel20")
                      for k, (op, x) in LINES.items())
    return out


def _only(s: str | None) -> set | None:
    if not s:
        return None
    out = set()
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out |= {f"N{i:02d}" if a.startswith("N") else f"W{i:02d}" for i in range(int(a[1:]), int(b[1:]) + 1)}
        else:
            out.add(part)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["plan", "check", "tilts", "solvetest", "boxcheck"])
    ap.add_argument("--spans", help="boxcheck: agent-09's spans_<film>.json (master frames) for the gate's rows")
    ap.add_argument("--anim", help="boxcheck: the face animation (default /Game/Explainer/Perf/AS_exp_<who>_gaze)")
    ap.add_argument("--line", default="N01", help="solvetest: the line")
    ap.add_argument("--intensity", type=float, help="solvetest: the solver mood's intensity (default SOLVE_MOOD's)")
    ap.add_argument("--mood", help="solvetest: the solver mood (default SOLVE_MOOD's, e.g. PLAYFULNESS for N01)")
    ap.add_argument("--who", default="her")
    ap.add_argument("--lines", help="e.g. N01-N04,N13 (a test); default every line")
    a = ap.parse_args()
    only = _only(a.lines)
    if a.cmd == "plan":
        print(json.dumps(plan(a.who, only), indent=1))
    elif a.cmd == "tilts":
        p = HERE / "acting" / f"tilts_{a.who}.json"
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(plan(a.who, only)["tilts"], indent=1) + "\n")
        print(p)
    elif a.cmd == "solvetest":
        r = solvetest(a.who, a.line, a.intensity, a.mood or "")
        out = ROOT / "out" / "explainers" / "face" / a.who / f"solvetest_{a.line}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(r, indent=1))
        print(json.dumps(r, indent=1))
    elif a.cmd == "boxcheck":
        r = boxcheck(a.who, a.anim or f"/Game/Explainer/Perf/AS_exp_{a.who}_gaze", only, a.spans or "")
        print(json.dumps(r, indent=1))
        sys.exit(0 if r["pass"] else 1)
    else:
        r = check(a.who, only)
        print(json.dumps(r, indent=1))
        sys.exit(0 if r["pass"] else 1)


if __name__ == "__main__":
    main()
