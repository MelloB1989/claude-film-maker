"""Sync report: the spec's timing contract (§2), checked on data/vo.json, data/audio.json and audio/vo/vo.wav.

- every cut sits on a beat, and every act's first cut on a downbeat, within one frame;
- lines never overlap, words sit inside their line, and each line sits inside its scene;
- every word that opens a line or follows a pause lights up within one frame after the onset measured on the
  voiceover itself (onsets.py), never ahead of it, each measured in the window its take gave film-pace;
- every line's first word lights no more than 40 ms after the first audible frame (-30 dB) in its window, whatever
  that sound is (the any-sound check);
- the film runs 85–95 s.

The words are measured in the windows each line's paced take gave film-pace (audio/vo/paced/<line>/<take>.json), on
the voiceover film-edit and film-snap assembled from those takes. If film-pace has been run again since (a new factor
makes a new take), vo.wav and vo.json still hold the old one, and every measurement would be of the old audio in the
new take's windows. So each take must still match its placed line (as many words; the same length, within 1 ms), and
film-sync stops if one does not, asking for film-edit and then film-snap.

A ruled exception is listed in data/sync_waivers.json as {"cut <scene>": "<ruling>"}. It covers only that act cut's
"off the downbeat" problem, which then prints as waived and does not fail the gate; an act cut off the beat grid, and
every other problem, can't be waived. Where each music section starts against the cut it opens is printed for
information only.
"""
import argparse
import json
import math
import re
import sys

import numpy as np

from .music_plan import SECTIONS
from .onsets import AFTER, BEFORE, ON_DB, frames, voice_onsets
from .paths import AUDIO, DATA
from .vo import load_script
from .wav import read_wav

FPS = 30
FRAME = 1 / FPS
LATE = FRAME + 0.002  # a word lights on the first frame at or after its start: up to a frame late, plus 2 ms
SLACK = 1e-4  # vo.json keeps times to 0.1 ms and the voiceover places each take on the nearest sample
ANY_SOUND = 0.040  # a line's first word lights at most this long after the first audible frame in its window
TAKE_SLACK = 0.001  # s: a paced take lasts as long as its placed line, to the sample (vo.json keeps 0.1 ms)
WAIVABLE = re.compile(r"(cut \S+) at \S+ is \d+ ms off the downbeat")


def check(vo: dict, audio: dict, script: dict) -> list[str]:
    problems = []
    beats, downs = np.asarray(audio["beats"]), np.asarray(audio["downbeats"])
    act_first = {a["scenes"][0] for a in script["acts"]}

    def off(grid, t):
        return float(np.min(np.abs(grid - t))) if len(grid) else float("inf")

    for s in vo["scenes"][1:]:
        d = off(beats, s["start"])
        if s["id"] in act_first and d > FRAME + 1e-9:
            problems.append(f"cut {s['id']} at {s['start']:.3f}s: act cut not on a beat "
                            f"({d * 1000:.0f} ms off the nearest beat)")
        elif s["id"] in act_first and (dd := off(downs, s["start"])) > FRAME + 1e-9:
            problems.append(f"cut {s['id']} at {s['start']:.3f}s is {dd * 1000:.0f} ms off the downbeat")
        elif d > FRAME + 1e-9:
            problems.append(f"cut {s['id']} at {s['start']:.3f}s is {d * 1000:.0f} ms off the beat")
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


def stale_takes(vo: dict, takes: dict[str, dict]) -> list[str]:
    """Each line's paced take (its JSON: `duration` and `words`) against the line as vo.json places it: a take with
    another number of words, or another length (by TAKE_SLACK or more), is not the take vo.wav and vo.json hold."""
    problems = []
    for l in vo["lines"]:
        t = takes[l["id"]]
        if len(t["words"]) != len(l["words"]):
            problems.append(f"{l['id']} take {l['take']} has {len(t['words'])} words, but its line in vo.json has "
                            f"{len(l['words'])}")
        span = l["end"] - l["start"]
        if abs(t["duration"] - span) >= TAKE_SLACK:
            problems.append(f"{l['id']} take {l['take']} lasts {t['duration']:.3f} s, but its line in vo.json lasts "
                            f"{span:.3f} s")
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


def _line(l: dict, samples: np.ndarray, sr: int, takes: dict | None) -> tuple[np.ndarray, float, list[dict]]:
    """A line's own audio, its start on the film's clock, and its words' times relative to that start: the take's
    aligned times when given (the windows film-pace measured in), else vo.json's."""
    i0, i1 = int(round(l["start"] * sr)), int(round(l["end"] * sr))
    t0 = i0 / sr
    if takes is not None:
        rel = [{"w": w["w"], "start": w["start"], "end": w["end"]} for w in takes[l["id"]]]
    else:
        rel = [{**w, "start": w["start"] - t0, "end": w["end"] - t0} for w in l["words"]]
    return samples[i0:i1], t0, rel


def word_sync(vo: dict, samples: np.ndarray, sr: int, takes: dict | None = None) -> tuple[list[str], list[dict]]:
    """Measure the spoken onset of every line-opening or post-pause word on the voiceover track, with the same
    voice_onsets that film-pace used, and check that the word lights 0 to one frame (+2 ms) after it. Each line's
    audio is measured on its own, so levels are relative to its own peak as they were in its take. `takes` maps a
    line id to its take's words (aligned times, relative to the line): a word whose onset is a long consonant ahead
    of its voice is placed well before its aligned start, so only the take's own window still reaches the voice."""
    problems, rows = [], []
    for l in vo["lines"]:
        seg, t0, rel = _line(l, samples, sr, takes)
        for k, (w, on) in enumerate(zip(l["words"], voice_onsets(seg, sr, rel))):
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


def any_sound(vo: dict, samples: np.ndarray, sr: int, takes: dict | None = None) -> list[str]:
    """Each line's first word lights no more than ANY_SOUND after the first audible frame (at or above -30 dB of the
    line's peak) in its onset window, whatever that sound is: a check on the onset rule itself."""
    problems = []
    for l in vo["lines"]:
        seg, t0, rel = _line(l, samples, sr, takes)
        db, _, n = frames(seg, sr)
        w, r = l["words"][0], rel[0]
        a = math.ceil(max(0.0, r["start"] - BEFORE) * sr / n - 1e-9)
        b = min(math.floor(min(r["start"] + AFTER, r["end"]) * sr / n + 1e-9), len(db) - 1)
        first = next((j for j in range(a, b + 1) if db[j] >= ON_DB), None)
        if first is None:
            problems.append(f"{l['id']} word {w['w']!r}: no audible sound in its window")
            continue
        heard = t0 + first * n / sr
        if lit(w["start"]) - heard > ANY_SOUND + SLACK:
            problems.append(f"{l['id']} word {w['w']!r} lights {(lit(w['start']) - heard) * 1000:.0f} ms after the "
                            f"first sound in its window ({heard:.3f} s)")
    return problems


def section_table(vo: dict, audio: dict) -> list[dict]:
    """Each music section's start against the cut of the scene it opens (information, not a rule)."""
    opens = {name: scene for name, scene, *_ in SECTIONS}
    cut = {s["id"]: s["start"] for s in vo["scenes"]}
    return [{"section": s["name"], "scene": opens[s["name"]], "start": s["start"], "cut": cut[opens[s["name"]]],
             "delta_ms": round((s["start"] - cut[opens[s["name"]]]) * 1000)}
            for s in audio["sections"] if opens.get(s["name"]) in cut]


def report(problems: list[str], waivers: dict[str, str]) -> tuple[list[str], bool]:
    """The verdict, line by line, and whether it fails. A waiver key ("cut her") covers that act cut's "off the
    downbeat" problem only; it prints as waived and does not fail the gate. Nothing else can be waived."""
    lines, failing, waived, used = [], 0, 0, set()
    for p in problems:
        m = WAIVABLE.fullmatch(p)
        key = m.group(1) if m and m.group(1) in waivers else None
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
    wav = AUDIO / "vo" / "vo.wav"
    if not wav.is_file():
        raise SystemExit("audio/vo/vo.wav is missing: run film-edit, then film-snap, to assemble the voiceover")
    vo = json.loads((DATA / "vo.json").read_text())
    audio = json.loads((DATA / "audio.json").read_text())
    problems = check(vo, audio, load_script())
    paced = {}
    for l in vo["lines"]:
        p = AUDIO / "vo" / "paced" / l["id"] / f"{l['take']}.json"
        if not p.is_file():
            raise SystemExit(f"{p.relative_to(AUDIO.parent)} is missing: run film-pace")
        paced[l["id"]] = json.loads(p.read_text())
    stale = stale_takes(vo, paced)
    if stale:
        raise SystemExit("\n".join(stale) + "\nthe paced takes are not the ones vo.wav and vo.json were assembled "
                         "from: run film-edit, then film-snap")
    takes = {line_id: doc["words"] for line_id, doc in paced.items()}
    y, sr = read_wav(wav)
    word_problems, rows = word_sync(vo, y, sr, takes)
    problems += word_problems + any_sound(vo, y, sr, takes)
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
