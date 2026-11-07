"""The gesture plan: one timeline of gesture events on the VO clock, from agent-11's acting sheet and the VO's prosody
(round 7, agent-10). It says WHAT the hands do and WHEN; compose.py turns it into motion from licensed mocap clips.

- The sheet's gestures are kept as written (type, hand, size, target, word). Each stroke moves from the word's start
  to its stressed syllable's loudness peak (prosody.py), at most 0.12 s later.
- Between them, while she speaks, micro-beats go on stressed content words wherever a gap would otherwise leave the
  hands still for more than ~1.4 s. The bar: 0.5-1.2 gesture onsets per second while speaking, varied.
- The amplitude varies (the orchestrator, 07 Nov): the sheet's size x the line's intensity x the syllable's stress,
  with a seeded jitter (sheet v1.1 gives its own amp). The sheet's held strokes keep their hold_s, still: no
  micro-beat goes into a hold; the rest get short holds.
- Each event ends either co-articulated into the next one's preparation (the hands never drop between two gestures
  less than 0.6 s apart), or in "ready" (hands up and loose, off the body, while she keeps talking), or in "rest"
  (hands loosely together, forearms on the desk edge) only in pauses of 0.9 s or more.

    python gesture/plan.py netflix  -> gesture/out/plan_netflix.json (needs out/prosody_netflix.json)
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPL = HERE.parent
FILM_WHO = {"netflix": "her", "whatsapp": "him"}

SIZE = {"small": 0.45, "medium": 0.7, "big": 1.0}
STOP = {"a", "an", "the", "and", "but", "of", "to", "in", "on", "at", "it", "is", "its", "it's", "that", "that's",
        "for", "from", "so", "has", "have", "each", "your", "you", "what", "will", "than", "then", "called", "get",
        "them", "their", "all", "be", "by", "with", "doesn't", "come", "over", "every"}
MICRO_TYPES = ("beat", "open_palm", "beat", "flick")  # cycled with a seeded skip: never the same twice in a row
GAP_FILL = 1.4  # s of stillness while speaking that calls for a micro-beat
COART = 0.6  # s: closer than this, a gesture flows into the next one's preparation
REST_PAUSE = 0.9  # s: pauses at least this long go to rest


def bare(w: str) -> str:
    return w.lower().strip(".,?!:;\"'")


def load(film: str):
    who = FILM_WHO[film]
    sheet = json.loads((EXPL / "acting" / f"{who}.json").read_text())
    cues = json.loads((EXPL / "audio" / film / "cues.json").read_text())
    pros = json.loads((HERE / "out" / f"prosody_{film}.json").read_text())
    return sheet, cues, pros


def speech_spans(cues) -> list:
    """[(t0, t1)] of continuous speech: the cue words, joined over gaps shorter than REST_PAUSE."""
    spans = []
    for ln in cues["lines"]:
        for w in ln["words"]:
            if spans and w["start"] - spans[-1][1] < REST_PAUSE:
                spans[-1][1] = max(spans[-1][1], w["end"])
            else:
                spans.append([w["start"], w["end"]])
    return [tuple(s) for s in spans]


def plan(film: str, seed: int = 72) -> dict:
    sheet, cues, pros = load(film)
    rng = random.Random(seed)
    peaks = {(w["line"], w["i"]): w for w in pros["words"]}
    ev = []
    for ln in sheet["lines"]:
        inten = ln.get("intensity", 0.7)
        for g in ln["gestures"]:
            pw = peaks.get((ln["id"], g.get("word_i")))
            stroke = g["stroke_t"]
            if pw and 0 <= pw["peak_t"] - stroke <= 0.12:
                stroke = pw["peak_t"]
            stress = pw["stress"] if pw else 0.6
            held = g.get("held", False)
            if "amp" in g:  # sheet v1.1: its own amplitude, nudged by the syllable's stress and a small jitter
                amp = g["amp"] * (0.92 + 0.16 * stress) * rng.uniform(0.94, 1.06)
            else:
                amp = SIZE.get(g.get("size"), 0.7) * (0.8 + 0.3 * inten) * (0.85 + 0.3 * stress) * rng.uniform(0.9, 1.1)
            hold = g.get("hold_s", 0.25)
            hold = hold if held else max(0.12, hold * rng.uniform(0.6, 1.3))
            ev.append({"line": ln["id"], "src": "sheet", "type": g["type"], "hand": g["hand"], "word": g["word"],
                       "size": g.get("size"), "target": g.get("target"), "note": g.get("note", ""),
                       "count": g.get("count"), "start_word": g.get("start_word"),
                       "prep_t": round(g["prep_t"], 3), "stroke_t": round(stroke, 3),
                       "hold_t": round(stroke + hold, 3), "amp": round(min(1.15, amp), 3), "energy": round(inten, 2),
                       "stress": stress, "held": held, "on_cam": ln.get("on_cam", True)})
    ev.sort(key=lambda e: e["stroke_t"])
    ev = micro_beats(ev, pros, cues, sheet, rng)
    spans = speech_spans(cues)
    ends(ev, spans)
    return {"film": film, "who": FILM_WHO[film], "seed": seed, "events": ev, "speech": spans,
            "stats": stats(ev, spans)}


def micro_beats(ev, pros, cues, sheet, rng) -> list:
    """Micro-beats on stressed content words in the still stretches between the sheet's gestures, while speaking."""
    inten = {ln["id"]: ln.get("intensity", 0.7) for ln in sheet["lines"]}
    words = [w for w in pros["words"] if bare(w["w"]) not in STOP]
    out = list(ev)
    last_type = None
    for _ in range(3):  # a few passes: one gap may take more than one beat
        out.sort(key=lambda e: e["stroke_t"])
        busy = [(e["prep_t"], e["hold_t"]) for e in out]
        added = False
        for w in sorted(words, key=lambda w: -w["stress"]):
            t = w["peak_t"]
            if w["stress"] < 0.45:
                break
            prev_end = max([b for a, b in busy if b <= t] or [-9])
            next_start = min([a for a, b in busy if a >= t] or [99])
            if any(a - 0.05 <= t <= b + 0.05 for a, b in busy):
                continue
            if next_start - prev_end < GAP_FILL or t - prev_end < 0.55 or next_start - t < 0.45:
                continue
            kinds = [k for k in MICRO_TYPES if k != last_type]
            k = rng.choice(kinds)
            last_type = k
            hand = "both" if (k == "open_palm" and rng.random() < 0.3) else "R"
            amp = (0.3 + 0.25 * w["stress"]) * (0.8 + 0.3 * inten.get(w["line"], 0.7)) * rng.uniform(0.85, 1.15)
            prep = max(prev_end + 0.05, t - rng.uniform(0.22, 0.32))
            hold = rng.uniform(0.08, 0.2)
            out.append({"line": w["line"], "src": "micro", "type": k, "hand": hand, "word": w["w"], "size": "small",
                        "target": "camera", "note": "", "count": None, "start_word": None,
                        "prep_t": round(prep, 3), "stroke_t": t, "hold_t": round(t + hold, 3), "amp": round(amp, 3),
                        "energy": inten.get(w["line"], 0.7), "stress": w["stress"], "held": False, "on_cam": True})
            busy.append((prep, t + hold))
            added = True
        if not added:
            break
    out.sort(key=lambda e: e["stroke_t"])
    return out


def ends(ev, spans):
    """How each event ends: 'coart' into the next one's preparation, else 'ready' while speaking, 'rest' in pauses."""
    def in_speech(t):
        return any(a - 0.2 <= t <= b + 0.2 for a, b in spans)

    for i, e in enumerate(ev):
        nxt = ev[i + 1] if i + 1 < len(ev) else None
        gap = (nxt["prep_t"] - e["hold_t"]) if nxt else 99
        if gap < COART:
            e["end"], e["retract_t"] = "coart", round(max(e["hold_t"] + 0.08, nxt["prep_t"]), 3)
            continue
        # a pause at least REST_PAUSE long right after the hold -> rest, else ready
        pause = not in_speech(e["hold_t"] + 0.5) and gap >= REST_PAUSE
        e["end"] = "rest" if pause else "ready"
        e["retract_t"] = round(e["hold_t"] + (0.55 if pause else 0.35), 3)


def stats(ev, spans) -> dict:
    talk = sum(b - a for a, b in spans)
    on = [e for e in ev if any(a - 0.3 <= e["prep_t"] <= b for a, b in spans)]
    rep = sum(1 for a, b in zip(ev, ev[1:]) if a["type"] == b["type"] and a["hand"] == b["hand"]
              and abs(a["amp"] - b["amp"]) < 0.1)
    still = 0.0
    for a, b in zip(ev, ev[1:]):
        g = b["prep_t"] - a["hold_t"]
        if any(x <= a["hold_t"] and b["prep_t"] <= y for x, y in spans):
            still = max(still, g)
    return {"events": len(ev), "sheet": sum(e["src"] == "sheet" for e in ev),
            "micro": sum(e["src"] == "micro" for e in ev), "speaking_s": round(talk, 2),
            "onsets_per_s": round(len(on) / talk, 3), "same_twice": rep, "longest_still_while_speaking_s": round(still, 2),
            "held": sum(e["held"] for e in ev)}


if __name__ == "__main__":
    film = sys.argv[1] if len(sys.argv) > 1 else "netflix"
    res = plan(film)
    (HERE / "out" / f"plan_{film}.json").write_text(json.dumps(res, indent=1))
    for e in res["events"]:
        print(f'{e["line"]} {e["src"]:5} {e["type"]:12} {e["hand"]:4} {e["word"]:14} prep {e["prep_t"]:6.2f} '
              f'stroke {e["stroke_t"]:6.2f} hold {e["hold_t"]:6.2f} -> {e["end"]:5} {e["retract_t"]:6.2f} amp {e["amp"]}')
    print(json.dumps(res["stats"]))
