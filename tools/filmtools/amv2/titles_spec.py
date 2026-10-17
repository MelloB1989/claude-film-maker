"""TITLES library data prep (EffectCraft v2): everything Python computes for `ec/titles.jsx`.

The core builder imports this module and calls `extend(E, ctx_py)` before it writes the script; the result lands in
`E["x"]["titles"]` and `ec/titles.jsx` reads it as `E.x.titles`.

  sub:    {title index -> {"pages": [[{"w": "WHO", "f": 10, "join": false}, ...], ...]}}
          Word-synced subtitles. A word appears `f` = the measured reveal frame from cues.csv, else voice cue frame + ceil(word t0 * fps) (0 to <1 frame after it is
          spoken, so well inside the 0-2 frame brief). `join` = the word ends in a hyphen and the next word sticks to it
          ("Spider-" + "Man." -> SPIDER-MAN.). A sentence ending in . ? ! starts a new page.
  shot:   {title index -> id of the shot the title belongs to (the shot holding its in frame)}
  behind: {title index -> id of the shot whose MATTE_<id> the word sits behind} (only for titles with `behind`)
  cut:    {title index -> the transition the title leaves on (the `xout` of the shot ending on f1) or None}
  act:    {title index -> act id}
"""
import csv
import json
import math
import os
import re

HANDOVER_VOICE = "/home/nikhil/code/film-making/handover/amv_handover/audio/voice"


def _voice_lines(E):
    for d in (E.get("voice_dir"), HANDOVER_VOICE):
        if d and os.path.exists(os.path.join(d, "voice_lines.json")):
            with open(os.path.join(d, "voice_lines.json")) as fh:
                return {v["name"]: v for v in json.load(fh)}
    return {}


def measured_reveals(E):
    """cues.csv (mix agent, measured spoken onsets): {voice name: [reveal frame per word, in order]}; {} when absent."""
    out = {}
    for d in (os.environ.get("AMV2_DATA"), "/home/nikhil/code/film-making/work/timeless_v2"):
        p = os.path.join(d, "cues.csv") if d else None
        if p and os.path.exists(p):
            with open(p) as fh:
                for r in csv.DictReader(fh):
                    if r["kind"] != "word":
                        continue
                    m = re.match(r"(\S+) spoken f(\d+) reveal f(\d+)", r["note"])
                    if m:
                        out.setdefault(m.group(1), []).append((r["name"], int(m.group(3))))
            return out
    return out


def sub_pages(words, cue_f, fps, reveals=None):
    """words = voice_lines.json words; returns pages of {"w","f","join"} with absolute frames."""
    pages, page = [], []
    for i, w in enumerate(words):
        f = cue_f + int(math.ceil(w["t0"] * fps - 1e-6))
        if reveals and len(reveals) == len(words) and reveals[i][0].lower() == w["w"].lower():
            f = reveals[i][1]                       # measured spoken onset + 1 (cues.csv)
        txt = w["w"].upper()
        page.append({"w": txt, "f": f, "join": txt.endswith("-")})
        if txt[-1] in ".?!" and i + 1 < len(words):
            pages.append(page)
            page = []
    if page:
        pages.append(page)
    return pages


def extend(E, ctx_py=None):
    fps = E["fps"]
    shots = E["shots"]
    voice = {v["name"]: v for v in E.get("voice", [])}
    lines = _voice_lines(E)
    rev = measured_reveals(E)
    X = {"sub": {}, "shot": {}, "behind": {}, "cut": {}, "act": {}}
    by_clip = {s["clip"]: s["id"] for s in shots}
    for i, T in enumerate(E["titles"]):
        host = next((s for s in shots if s["a"] <= T["f"] < s["b"]), None)
        X["shot"][str(i)] = host["id"] if host else None
        end = next((s for s in shots if s["b"] == T["f1"]), None)
        X["cut"][str(i)] = end["xout"] if end else None
        act = next((a for a in E["acts"] if a["f0"] <= T["f"] < a["f1"]), None)
        X["act"][str(i)] = act["id"] if act else None
        if T.get("behind"):
            b = T["behind"]
            X["behind"][str(i)] = b if b in {s["id"] for s in shots} else by_clip.get(b)
        if T["style"] == "sub":
            cue = voice.get(T.get("voice"))
            vl = lines.get(T.get("voice"))
            if cue and vl:
                X["sub"][str(i)] = {"pages": sub_pages(vl["words"], cue["f"], fps, rev.get(T.get("voice")))}
    E.setdefault("x", {})["titles"] = X
    return E


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "..", "..", "films", "timeless", "amv2", "edl.json")) as fh:
        E = json.load(fh)
    extend(E)
    print(json.dumps(E["x"]["titles"], indent=1))
