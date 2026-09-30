"""Sync report: the spec's timing contract (§2), checked on data/vo.json, data/audio.json and audio/vo/vo.wav.

- every cut sits on a beat, and every act's first cut on a downbeat, within one frame;
- lines never overlap, words sit inside their line, and each line sits inside its scene;
- every word that opens a line or follows a pause lights up within one frame after the onset measured on the
  voiceover itself (onsets.py), never ahead of it;
- the film runs 85–95 s.

A ruled exception is listed in data/sync_waivers.json as {"cut <scene>": "<ruling>"}: its problems print as waived and
do not fail the gate. Where each music section starts against the cut it opens is printed for information only.
"""
import argparse
import json
import math
import sys

import numpy as np

from .music_plan import SECTIONS
from .onsets import voice_onsets
from .paths import AUDIO, DATA
from .vo import load_script
from .wav import read_wav

FPS = 30
FRAME = 1 / FPS
LATE = FRAME + 0.002  # a word lights on the first frame at or after its start: up to a frame late, plus 2 ms
SLACK = 1e-4  # vo.json keeps times to 0.1 ms and the voiceover places each take on the nearest sample


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


def lit(start: float) -> float:
    """The first frame time that shows a word starting at `start`: the engine renders frame n at n * (1/FPS) and
    lights a word once its start <= t."""
    n = math.ceil(round(start * FPS, 6))
    while n * FRAME < start:
        n += 1
    while n > 0 and (n - 1) * FRAME >= start:
        n -= 1
    return n * FRAME


def word_sync(vo: dict, samples: np.ndarray, sr: int) -> tuple[list[str], list[dict]]:
    """Measure the spoken onset of every line-opening or post-pause word on the voiceover track, with the same
    voice_onsets that film-pace used, and check that the word lights 0 to one frame (+2 ms) after it. Each line's
    audio is measured on its own, so levels are relative to its own peak as they were in its take."""
    problems, rows = [], []
    for l in vo["lines"]:
        i0, i1 = int(round(l["start"] * sr)), int(round(l["end"] * sr))
        t0 = i0 / sr
        rel = [{**w, "start": w["start"] - t0, "end": w["end"] - t0} for w in l["words"]]
        for k, (w, on) in enumerate(zip(l["words"], voice_onsets(samples[i0:i1], sr, rel))):
            if on is None:
                if k == 0:
                    problems.append(f"{l['id']} word {w['w']!r}: no spoken onset near its start")
                continue
            onset = t0 + on
            err = lit(w["start"]) - onset
            rows.append({"line": l["id"], "word": w["w"], "start": w["start"], "onset": round(onset, 4),
                         "lit": round(lit(w["start"]), 4), "error_ms": round(err * 1000, 1)})
            if err < -SLACK:
                problems.append(f"{l['id']} word {w['w']!r} lights {-err * 1000:.0f} ms ahead of its spoken onset "
                                f"({onset:.3f} s)")
            elif err > LATE + SLACK:
                problems.append(f"{l['id']} word {w['w']!r} lights {err * 1000:.0f} ms after its spoken onset "
                                f"({onset:.3f} s)")
    return problems, rows


def section_table(vo: dict, audio: dict) -> list[dict]:
    """Each music section's start against the cut of the scene it opens (information, not a rule)."""
    opens = {name: scene for name, scene, *_ in SECTIONS}
    cut = {s["id"]: s["start"] for s in vo["scenes"]}
    return [{"section": s["name"], "scene": opens[s["name"]], "start": s["start"], "cut": cut[opens[s["name"]]],
             "delta_ms": round((s["start"] - cut[opens[s["name"]]]) * 1000)}
            for s in audio["sections"] if opens.get(s["name"]) in cut]


def report(problems: list[str], waivers: dict[str, str]) -> tuple[list[str], bool]:
    """The verdict, line by line, and whether it fails. A waiver key ("cut her") covers the problems that name that
    cut; they print as waived and do not fail the gate."""
    lines, failing, waived, used = [], 0, 0, set()
    for p in problems:
        key = next((k for k in waivers if p.startswith(k + " ")), None)
        if key is None:
            failing += 1
            lines.append(f"✗ {p}")
        else:
            waived += 1
            used.add(key)
            lines.append(f"waived: {p} ({waivers[key]})")
    lines += [f"note: waiver {k!r} matches no problem" for k in waivers if k not in used]
    if failing:
        lines.append(f"{failing} problem(s)" + (f", {waived} waived" if waived else ""))
    else:
        lines.append("sync OK" + (f" ({waived} waived)" if waived else ""))
    return lines, failing > 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check the timing contract")
    ap.add_argument("--words", action="store_true", help="list every measured word: onset, first lit frame, error")
    a = ap.parse_args(argv)
    vo = json.loads((DATA / "vo.json").read_text())
    audio = json.loads((DATA / "audio.json").read_text())
    problems = check(vo, audio, load_script())
    y, sr = read_wav(AUDIO / "vo" / "vo.wav")
    word_problems, rows = word_sync(vo, y, sr)
    problems += word_problems
    if a.words:
        for r in rows:
            print(f"  {r['line']:<4} {r['word']:<16} onset {r['onset']:8.3f}  lit {r['lit']:8.3f}  "
                  f"{r['error_ms']:+5.1f} ms")
    if rows:
        errs = [r["error_ms"] for r in rows]
        print(f"word sync: {len(rows)} words measured on vo.wav, each lit {min(errs):+.1f} to {max(errs):+.1f} ms "
              f"after its spoken onset (allowed 0 to +{LATE * 1000:.1f})")
    print("music sections against the cuts they open (information only):")
    for r in section_table(vo, audio):
        print(f"  {r['section']:<22} opens {r['scene']:<8} at {r['start']:7.3f}s   cut {r['cut']:7.3f}s   "
              f"section − cut {r['delta_ms']:+6d} ms")
    wp = DATA / "sync_waivers.json"
    lines, failed = report(problems, json.loads(wp.read_text()) if wp.exists() else {})
    print("\n".join(lines))
    sys.exit(1 if failed else 0)
