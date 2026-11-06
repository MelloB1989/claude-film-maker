"""Scope: judge a character only where the cut shows them. A per-character check (head stability, lips, hair,
garment clip) that reads frames where the character is off screen judges motion nobody sees. Round 5: his
blink_nod 2.89 at f1294-1306 sat inside S16, HER close-up, while he turned back to the lens off camera
(orchestrator: the correct scope, not a waiver).

    shots = [{"id": "S16", "start": 1200, "end": 1320, "cast": ["her"]}, ...]   (the shot table's cast lists)
    rng = visible_ranges(shots, "him")          # [[start, end), ...] merged
    kept, dropped = split(samples, rng)         # samples: {frame: value}

A shot's cast list is the scope. An on-screen test (projected bones inside the frame) can narrow it further with
`narrow(ranges, frames_on_screen)`; it never widens it."""
from __future__ import annotations


def visible_ranges(shots: list, who: str) -> list:
    """Merged [start, end) frame ranges of the shots whose cast includes `who`."""
    rs = sorted([int(s["start"]), int(s["end"])] for s in shots if who in (s.get("cast") or ()))
    out = []
    for a, b in rs:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def in_ranges(frame, ranges: list) -> bool:
    f = int(frame)
    return any(a <= f < b for a, b in ranges)


def split(samples: dict, ranges: list) -> tuple:
    """(kept, dropped) of {frame: value}: kept are the frames inside `ranges`."""
    kept = {f: v for f, v in samples.items() if in_ranges(f, ranges)}
    return kept, {f: v for f, v in samples.items() if f not in kept}


def window_in(start, end, ranges: list) -> bool:
    """A window (e.g. a blink, [start, end] inclusive) counts only when it lies wholly inside one range."""
    return any(a <= int(start) and int(end) < b for a, b in ranges)


def narrow(ranges: list, frames_on_screen) -> list:
    """`ranges` cut down to the frames an on-screen test passed (never wider than the cast scope)."""
    on = sorted(int(f) for f in frames_on_screen if in_ranges(f, ranges))
    out = []
    for f in on:
        if out and f == out[-1][1]:
            out[-1][1] = f + 1
        else:
            out.append([f, f + 1])
    return out
