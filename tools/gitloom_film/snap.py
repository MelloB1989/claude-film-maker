"""Put the voice on the beat.

1. Each line moves (at most `tol`) so that its first word lands on the nearest beat, unless that would bring it
   within `min_gap` of a neighbouring line.
2. Each scene then cuts on the last beat that is at least `lead` before its first word and not before the previous
   scene's last word; an act's first scene prefers a downbeat. If no beat fits, the cut takes the latest allowed
   moment, and the sync report flags it.
"""
import argparse
import json

import numpy as np

from .edit import act_spans, write_vo
from .paths import DATA
from .vo import load_script


def _shift(l: dict, d: float) -> dict:
    r = lambda x: round(x + d, 4)  # noqa: E731
    return {**l, "start": r(l["start"]), "end": r(l["end"]),
            "words": [{**w, "start": r(w["start"]), "end": r(w["end"])} for w in l["words"]]}


def snap_lines(lines: list[dict], beats, tol: float = 0.15, min_gap: float = 0.05) -> list[dict]:
    beats = np.asarray(beats)
    out = [dict(l) for l in lines]
    for i, l in enumerate(out):
        first = l["words"][0]["start"]
        d = float(beats[np.argmin(np.abs(beats - first))]) - first
        prev_end = out[i - 1]["end"] if i else -np.inf
        next_start = lines[i + 1]["start"] if i + 1 < len(lines) else np.inf
        if abs(d) <= tol and l["start"] + d >= prev_end + min_gap and l["end"] + d <= next_start - min_gap:
            out[i] = _shift(l, d)
    return out


def cut_scenes(scenes: list[dict], lines: list[dict], beats, downs, act_starts: set[str], duration: float,
               lead: float = 0.12) -> list[dict]:
    beats, downs = np.asarray(beats), np.asarray(downs)
    out = []
    for i, s in enumerate(scenes):
        if i == 0:
            start = 0.0
        else:
            w0 = min(l["words"][0]["start"] for l in lines if l["scene"] == s["id"])
            lo = max(l["words"][-1]["end"] for l in lines if l["scene"] == scenes[i - 1]["id"])
            hi = w0 - lead
            pick = None
            for grid in ([downs] if s["id"] in act_starts else []) + [beats]:
                c = grid[(grid >= lo) & (grid <= hi)]
                if len(c):
                    pick = float(c[-1])
                    break
            start = pick if pick is not None else max(lo, hi)
        out.append({**s, "start": round(start, 4)})
    for i, s in enumerate(out):
        s["end"] = out[i + 1]["start"] if i + 1 < len(out) else duration
    return out


def snap(vo: dict, audio: dict, script: dict) -> dict:
    duration = round(max(vo["duration"], audio["duration"]), 4)
    lines = snap_lines(vo["lines"], audio["beats"])
    act_starts = {a["scenes"][0] for a in script["acts"]}
    scenes = cut_scenes(vo["scenes"], lines, audio["beats"], audio["downbeats"], act_starts, duration)
    return {**vo, "duration": duration, "lines": lines, "scenes": scenes, "acts": act_spans(script, scenes)}


def main(argv=None):
    argparse.ArgumentParser(description="Nudge lines onto beats and cut scenes on beats").parse_args(argv)
    vo = json.loads((DATA / "vo.json").read_text())
    audio = json.loads((DATA / "audio.json").read_text())
    out = snap(vo, audio, load_script())
    moved = sum(1 for a, b in zip(vo["lines"], out["lines"]) if a["start"] != b["start"])
    write_vo(out)
    print(f"{moved}/{len(out['lines'])} lines nudged onto beats · duration {out['duration']:.2f}s")
    for s in out["scenes"]:
        print(f"  {s['id']:<9} {s['start']:7.3f} → {s['end']:7.3f}")
