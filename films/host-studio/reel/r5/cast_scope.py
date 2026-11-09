"""Round 5: each presenter's visible frames, from the shot table's cast lists (shots.py), for every per-character
gate check (head stability, lips, hair, garment): judge a character only where the cut shows them.

    python3 films/host-studio/reel/r5/cast_scope.py > /srv/ue/reel/r5/qa/scope.json
    -> {"him": [[start, end), ...], "her": [...], "shots": [{"id", "start", "end", "cast"}]}

Checks read it with unreal/fmbridge/qa/scope.py (window_in for a blink window, split for per-frame samples)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from shots import SHOTS  # noqa: E402


def _ranges(shots: list, who: str) -> list:
    """Merged [start, end) of the shots that cast `who` (the same rule as core qa/scope.py visible_ranges, which
    the checks use on this file's "shots")."""
    out = []
    for a, b in sorted([s["start"], s["end"]] for s in shots if who in s["cast"]):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def table() -> dict:
    shots = [{"id": s.id, "start": s.start, "end": s.end, "cast": list(s.cast)} for s in SHOTS]
    who = sorted({c for s in shots for c in s["cast"]})
    return {**{w: _ranges(shots, w) for w in who}, "shots": shots}


if __name__ == "__main__":
    print(json.dumps(table(), indent=1))
