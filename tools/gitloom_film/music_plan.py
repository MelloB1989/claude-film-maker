"""The score's composition plan: one section per story beat, each a whole number of bars, starting at the bar line
nearest its first scene (spec §5.2)."""
import math

PALETTE = ["nocturnal, sensual, minimal electronic", "intimate and expensive-sounding", "tape saturation", "100 BPM",
           "minor key", "instrumental"]
GROOVE_KIT = ["warm sub bass", "soft round kick", "crisp brushed hats", "breathy analog pads",
              "a plucked motif like a taut thread being pulled, muted harp or koto"]
QUIET_NEG = ["drums", "kick", "hi-hats", "bassline", "groove", "loud"]
GLOBAL_NEG = ["EDM drop", "trap hi-hat rolls", "cheesy synth brass", "vocals", "choir", "dubstep wobble"]

# (name, first scene, positive styles, negative styles, context adherence)
SECTIONS: list[tuple[str, str, list[str], list[str], str]] = [
    ("cold open", "thread", ["very quiet", "a low sub drone", "a slow heartbeat pulse in the sub", "a single plucked note",
                             "lots of space"], QUIET_NEG, "high"),
    ("the ex", "ex", ["low-pass filtered pulse", "rising tension", "glassy ticks", "breathy analog pads"],
     ["kick", "full drum kit", "loud"], "high"),
    ("her", "her", GROOVE_KIT + ["kick and warm sub bass enter on the first beat", "sparse, confident groove"], [], "high"),
    ("the tour", "loom", GROOVE_KIT + ["full groove", "sensual bassline", "a subtle variation every 8 bars"], [], "high"),
    ("honest", "honest", ["everything drops out", "near silence", "one soft pad breath"], QUIET_NEG + ["melody"], "low"),
    ("proof and everywhere", "proof", GROOVE_KIT + ["the full groove slams back in on the first beat", "fuller",
                                                    "confident lift"], ["silence", "fade-in", "slow build"], "low"),
    ("weave", "weave", ["one big hit on the first beat", "long reverb tail", "the plucked motif alone to the end",
                        "fading out"], ["drums after the first beat", "abrupt ending"], "high"),
]


def bar_seconds(bpm: float) -> float:
    return 240.0 / bpm


def section_bounds(vo: dict, bpm: float, min_bars: int = 2) -> list[float]:
    bar = bar_seconds(bpm)
    start = {s["id"]: s["start"] for s in vo["scenes"]}
    bars = [0] + [round(start[s[1]] / bar) for s in SECTIONS[1:]] + [math.ceil(vo["duration"] / bar)]
    for i in range(1, len(bars)):
        bars[i] = max(bars[i], bars[i - 1] + min_bars)
    return [b * bar for b in bars]


def build_plan(vo: dict, bpm: float = 100.0) -> tuple[dict, dict]:
    b = section_bounds(vo, bpm)
    sections = []
    for i, (name, _, pos, neg, adherence) in enumerate(SECTIONS):
        dur_ms = int(round((b[i + 1] - b[i]) * 1000))
        if not 3000 <= dur_ms <= 120000:
            raise ValueError(f"section {name!r} is {dur_ms} ms; the API allows 3000–120000")
        sections.append({"section_name": name, "positive_local_styles": pos, "negative_local_styles": neg,
                         "duration_ms": dur_ms, "lines": [], "context_adherence": adherence})
    plan = {"positive_global_styles": PALETTE, "negative_global_styles": GLOBAL_NEG, "sections": sections}
    meta = {"bpm": bpm, "sections": [{"name": n, "start": round(b[i], 4), "end": round(b[i + 1], 4)}
                                     for i, (n, *_) in enumerate(SECTIONS)]}
    return plan, meta


def to_chunks(plan: dict) -> dict:
    """music_v2 and v2.5 take a chunk plan: each section becomes a chunk labelled "[Name]" (sung lines follow the
    label), carrying the global styles plus its own; v1's global/local split does not exist there."""
    return {"chunks": [{
        "text": f"[{s['section_name'].title()}]" + "".join(f"\n{line}" for line in s["lines"]),
        "duration_ms": s["duration_ms"],
        "positive_styles": plan["positive_global_styles"] + s["positive_local_styles"],
        "negative_styles": plan["negative_global_styles"] + s["negative_local_styles"],
        "context_adherence": s.get("context_adherence", "high"),
        "conditioning_ref": None,
        "condition_strength": None,
    } for s in plan["sections"]]}
