"""The score's composition plan, from film.json pipeline.music: one section per story beat, each a whole number of
bars, starting on the bar line at or before the cut of the scene it opens, so the music has turned by the time the
picture does.

A section is {"name", "scene" (the scene it opens) or "at" (seconds), "styles", "avoid", "adherence" ("high" or
"low"), "lines" (sung lines, rarely)}; the first section starts at 0 whatever it names. Without sections the score is
one section over the film, split into equal whole-bar sections where the API's 120 s limit needs it.
"""
import math

MIN_MS, MAX_MS = 3000, 120000  # the API's section lengths


def bar_seconds(bpm: float, beats_per_bar: int = 4) -> float:
    return 60.0 * beats_per_bar / bpm


def default_sections(duration: float, bpm: float, beats_per_bar: int = 4) -> list[dict]:
    """One section over the film, or as few equal whole-bar sections as keep each within MAX_MS."""
    bar = bar_seconds(bpm, beats_per_bar)
    bars = max(1, math.ceil(duration / bar - 1e-9))
    n = max(1, math.ceil(bars * bar * 1000 / MAX_MS))
    if n == 1:
        return [{"name": "score", "at": 0.0}]
    per = math.ceil(bars / n)
    return [{"name": f"score {i + 1}", "at": i * per * bar} for i in range(n)]


def _start(sec: dict, starts: dict[str, float]) -> float:
    if "at" in sec:
        return float(sec["at"])
    if "scene" not in sec:
        raise SystemExit(f"music section {sec.get('name')!r} needs a scene it opens (or an 'at' time)")
    if sec["scene"] not in starts:
        raise SystemExit(f"music section {sec['name']!r} opens scene {sec['scene']!r}, which the film does not have "
                         f"(scenes: {', '.join(starts)})")
    return starts[sec["scene"]]


def section_bounds(vo: dict, sections: list[dict], bpm: float, min_bars: int = 2, beats_per_bar: int = 4) -> list[float]:
    """Each section's start on the bar line at or before its scene's cut (whole bars, at least `min_bars` each), and
    the end of the last bar the film reaches. `vo` is any {duration, scenes: [{id, start}]} (timeline.load())."""
    bar = bar_seconds(bpm, beats_per_bar)
    starts = {s["id"]: s["start"] for s in vo["scenes"]}
    bars = [0] + [math.floor(_start(s, starts) / bar + 1e-9) for s in sections[1:]] + [math.ceil(vo["duration"] / bar)]
    for i in range(1, len(bars)):
        bars[i] = max(bars[i], bars[i - 1] + min_bars)
    return [b * bar for b in bars]


def tempo_style(bpm: float) -> str:
    return f"{bpm:g} BPM"


def build_plan(vo: dict, bpm: float = 120.0, music: dict | None = None, beats_per_bar: int = 4) -> tuple[dict, dict]:
    """(the readable section plan, its timing meta {bpm, sections: [{name, start, end}]}). `music` is
    pipeline.music: styles, avoid and sections."""
    music = music or {}
    sections = music.get("sections") or default_sections(vo["duration"], bpm, beats_per_bar)
    names = [s.get("name") for s in sections]
    if not all(names) or len(set(names)) != len(names):
        raise SystemExit(f"music sections need distinct names, not {names}")
    b = section_bounds(vo, sections, bpm, beats_per_bar=beats_per_bar)
    out = []
    for i, s in enumerate(sections):
        dur_ms = int(round((b[i + 1] - b[i]) * 1000))
        if not MIN_MS <= dur_ms <= MAX_MS:
            raise ValueError(f"section {s['name']!r} is {dur_ms} ms; the API allows {MIN_MS}–{MAX_MS}")
        out.append({"section_name": s["name"], "positive_local_styles": list(s.get("styles", [])),
                    "negative_local_styles": list(s.get("avoid", [])), "duration_ms": dur_ms,
                    "lines": list(s.get("lines", [])), "context_adherence": s.get("adherence", "high")})
    styles = list(music.get("styles", []))
    if tempo_style(bpm) not in styles:
        styles.append(tempo_style(bpm))
    plan = {"positive_global_styles": styles, "negative_global_styles": list(music.get("avoid", [])), "sections": out}
    meta = {"bpm": bpm, "sections": [{"name": s["name"], "start": round(b[i], 4), "end": round(b[i + 1], 4)}
                                     for i, s in enumerate(sections)]}
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
