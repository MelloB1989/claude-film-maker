"""Sync report: the spec's timing contract (§2), checked on data/vo.json and data/audio.json.

- every cut sits on a beat, and every act's first cut on a downbeat, within one frame;
- lines never overlap, words sit inside their line, and each line sits inside its scene;
- the film runs 85–95 s.
"""
import argparse
import json
import sys

import numpy as np

from .paths import DATA
from .vo import load_script

FRAME = 1 / 30


def check(vo: dict, audio: dict, script: dict) -> list[str]:
    problems = []
    beats, downs = np.asarray(audio["beats"]), np.asarray(audio["downbeats"])
    act_first = {a["scenes"][0] for a in script["acts"]}
    for s in vo["scenes"][1:]:
        on_down = s["id"] in act_first
        grid = downs if on_down else beats
        d = float(np.min(np.abs(grid - s["start"]))) if len(grid) else float("inf")
        if d > FRAME + 1e-9:
            problems.append(f"cut {s['id']} at {s['start']:.3f}s is {d * 1000:.0f} ms off the "
                            f"{'downbeat' if on_down else 'beat'}")
    prev_end = -np.inf
    scenes = {s["id"]: s for s in vo["scenes"]}
    for l in vo["lines"]:
        if l["start"] < prev_end - 1e-9:
            problems.append(f"{l['id']} overlaps the line before it")
        prev_end = l["end"]
        for w in l["words"]:
            if not l["start"] - 1e-6 <= w["start"] <= w["end"] <= l["end"] + 1e-6:
                problems.append(f"{l['id']} word {w['w']!r} lies outside its line")
        sc = scenes[l["scene"]]
        if not (sc["start"] <= l["words"][0]["start"] and l["words"][-1]["end"] <= sc["end"] + 1e-6):
            problems.append(f"{l['id']} is not inside its scene {sc['id']}")
    if not 85.0 <= vo["duration"] <= 95.0:
        problems.append(f"duration {vo['duration']:.2f}s is outside 85–95 s")
    return problems


def main(argv=None):
    argparse.ArgumentParser(description="Check the timing contract").parse_args(argv)
    problems = check(json.loads((DATA / "vo.json").read_text()), json.loads((DATA / "audio.json").read_text()),
                     load_script())
    for p in problems:
        print("✗", p)
    print("sync OK" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
