"""Film timing for Blender shots, in film frames. bpy-free: it runs in Blender and under the tools project's pytest.

It reads the same locked files the engine reads: data/vo.json (scene windows, lines and their words with measured
onsets) and data/audio.json (beats and downbeats). Film frame n shows song time n / 30, and a Blender shot numbers its
frames the same way (render.py sets frame_start to the shot's first film frame), so a keyframe at `frame(t)` lands on
the engine's frame for t.

`frame(t)` rounds exactly as the engine's `frameIdx` does (JavaScript's Math.round: a half frame goes up). Python's
round() rounds halves to even and would put some events one frame early: the half-frame drift the plates must not
have. Frame ranges are half-open, [f0, f1), like the engine's scene windows: a scene's f1 is the next scene's f0.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

FPS = 30
REPO = Path(__file__).resolve().parents[2]


def js_round(x: float) -> int:
    """JavaScript's Math.round: the nearest integer, and a tie goes towards +infinity (2.5 -> 3, -2.5 -> -2)."""
    f = math.floor(x)
    return int(f) + 1 if x - f >= 0.5 else int(f)


def frame(t: float) -> int:
    """The film frame showing song time t (s): round(t * 30), rounded as the engine rounds."""
    return js_round(t * FPS)


@dataclass(frozen=True)
class Word:
    w: str
    start: float
    end: float

    @property
    def frame(self) -> int:
        """The film frame of the word's spoken onset."""
        return frame(self.start)


class Timing:
    """The film's timing data: `load()` gives the repo's, `load(root)` another checkout's (or a test fixture's)."""

    def __init__(self, vo: dict, audio: dict):
        self.vo = vo
        self.audio = audio
        self._scenes = {s["id"]: s for s in vo["scenes"]}
        self._lines = {line["id"]: line for line in vo["lines"]}

    def scene_frames(self, scene_id: str) -> tuple[int, int]:
        """A scene's window as film frames [f0, f1)."""
        s = self._scenes.get(scene_id)
        if s is None:
            raise KeyError(f"no scene {scene_id!r} in vo.json (scenes: {', '.join(self._scenes)})")
        return frame(s["start"]), frame(s["end"])

    def line(self, line_id: str) -> dict:
        line = self._lines.get(line_id)
        if line is None:
            raise KeyError(f"no line {line_id!r} in vo.json")
        return line

    def word(self, line_id: str, i: int) -> Word:
        """Word i (from 0) of a line, with its measured onset `start` (s) and `frame`."""
        words = self.line(line_id)["words"]
        if not 0 <= i < len(words):
            raise IndexError(f"{line_id} has {len(words)} words, no word {i}")
        w = words[i]
        return Word(w["w"], w["start"], w["end"])

    def beats_in(self, f0: int, f1: int) -> list[int]:
        """The film frames of the beats in [f0, f1), in order."""
        return _frames_in(self.audio["beats"], f0, f1)

    def downbeats_in(self, f0: int, f1: int) -> list[int]:
        """The film frames of the downbeats (bar starts) in [f0, f1), in order."""
        return _frames_in(self.audio["downbeats"], f0, f1)


def _frames_in(times: list[float], f0: int, f1: int) -> list[int]:
    return [f for f in (frame(t) for t in times) if f0 <= f < f1]


def load(root: str | Path | None = None) -> Timing:
    """Read <root>/data/vo.json and <root>/data/audio.json (root: the repo)."""
    data = Path(root or REPO) / "data"
    vo = json.loads((data / "vo.json").read_text())
    audio = json.loads((data / "audio.json").read_text())
    return Timing(vo, audio)


_film: Timing | None = None


def film() -> Timing:
    """The repo's timing, loaded once."""
    global _film
    if _film is None:
        _film = load()
    return _film


def scene_frames(scene_id: str) -> tuple[int, int]:
    return film().scene_frames(scene_id)


def word(line_id: str, i: int) -> Word:
    return film().word(line_id, i)


def beats_in(f0: int, f1: int) -> list[int]:
    return film().beats_in(f0, f1)


def downbeats_in(f0: int, f1: int) -> list[int]:
    return film().downbeats_in(f0, f1)


_PART = re.compile(r"(\d+)(?:-(\d+))?")


def parse_frames(spec: str) -> list[int]:
    """A --frames value: film frames as `a-b` (inclusive) or a single frame, comma-separated; sorted, each once."""
    out: set[int] = set()
    for part in spec.split(","):
        m = _PART.fullmatch(part.strip())
        if not m:
            raise ValueError(f"bad --frames part {part!r}: use a, a-b or a list of them (film frames)")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) is not None else a
        if b < a:
            raise ValueError(f"bad --frames range {part!r}: the end is before the start")
        out.update(range(a, b + 1))
    return sorted(out)
