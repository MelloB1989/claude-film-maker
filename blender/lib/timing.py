"""Film timing for Blender shots, in film frames. bpy-free: it runs in Blender and under plain pytest.

It reads what the engine reads, from the film's folder (lib/film.py): scene windows from data/timeline.json (the engine
exports it: `cd app && bun scripts/timeline.ts --film <id>`), falling back to the `scenes` of the film's word-timed
voiceover (film.json `vo`, default data/vo.json); lines and their words with measured onsets from that voiceover; beats
and downbeats from the audio analysis (film.json `audio.analysis`, default data/audio.json), or, without one, a grid
synthesised from `audio.bpm` (default 120), `audio.offset` (s, default 0) and `audio.beatsPerBar` (default 4) over the
film's duration. Every file is optional: a film without scene windows can still render shots with explicit frames.

Film frame n shows film time n / fps, and a Blender shot numbers its frames the same way (render.py sets frame_start
to the shot's first film frame), so a keyframe at `frame(t)` lands on the engine's frame for t.

`frame(t)` rounds exactly as the engine's `frameIdx` does (JavaScript's Math.round: a half frame goes up). Python's
round() rounds halves to even and would put some events one frame early: the half-frame drift the plates must not
have. `frame(t)` places an event (a keyframe, a plate index); a scene's window is another rule. The engine shows a
scene on frame n when start <= n / fps < end (engine.ts onScreen and ownedFrames), so `scene_frames` gives the frames
[f0, f1) from the first frame at or after the start to the first at or after the end. Frame ranges are half-open: a
scene's f1 is the next scene's f0.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FPS = 30
GRID = {"bpm": 120.0, "offset": 0.0, "beatsPerBar": 4}  # the synthesised beat grid's defaults (film.json `audio`)


def js_round(x: float) -> int:
    """JavaScript's Math.round: the nearest integer, and a tie goes towards +infinity (2.5 -> 3, -2.5 -> -2)."""
    f = math.floor(x)
    return int(f) + 1 if x - f >= 0.5 else int(f)


def frame(t: float, fps: float = DEFAULT_FPS) -> int:
    """The film frame showing film time t (s): round(t * fps), rounded as the engine rounds."""
    return js_round(t * fps)


def first_frame_from(t: float, fps: float = DEFAULT_FPS) -> int:
    """The first film frame at or after film time t: the engine's ownedFrames `from`. It is counted on the frame times
    themselves, so a time exactly on a frame gives that frame even where t * fps lands an ulp past the integer (8.3 * 30
    is 249.00000000000003, and frame 249 is at 8.3)."""
    f = math.ceil(t * fps)
    while (f - 1) / fps >= t:
        f -= 1
    while f / fps < t:
        f += 1
    return f


@dataclass(frozen=True)
class Word:
    w: str
    start: float
    end: float
    fps: float = DEFAULT_FPS

    @property
    def frame(self) -> int:
        """The film frame of the word's spoken onset."""
        return frame(self.start, self.fps)


def beat_grid(duration: float | None, bpm: float = GRID["bpm"], offset: float = GRID["offset"],
              beats_per_bar: int = GRID["beatsPerBar"]) -> tuple[list[float], list[float]]:
    """A synthesised grid: (beats, downbeats) in s, a beat every 60 / bpm s on the grid through `offset` (beat 0 is a
    downbeat), those in [0, duration); every `beats_per_bar`-th beat from beat 0 is a downbeat. No duration: no beats."""
    if not bpm or bpm <= 0 or beats_per_bar < 1:
        raise ValueError(f"a beat grid needs bpm > 0 and beatsPerBar >= 1 (bpm {bpm}, beatsPerBar {beats_per_bar})")
    if duration is None:
        return [], []
    period = 60.0 / bpm
    k0, k1 = math.ceil(-offset / period - 1e-9), math.ceil((duration - offset) / period - 1e-9)  # beats in [0, duration)
    ks = range(k0, k1)
    beats = [offset + k * period for k in ks]
    return beats, [offset + k * period for k in ks if k % int(beats_per_bar) == 0]


class Timing:
    """A film's timing: scene windows ({"id", "start", "end"} in s), voiceover lines ({"id", "words": [{"w", "start",
    "end"}]}), beats and downbeats (s), at `fps`. `source` names where the scenes came from, for errors."""

    def __init__(self, scenes=(), *, fps: float = DEFAULT_FPS, lines=(), beats=(), downbeats=(),
                 duration: float | None = None, source: str = "the film's timeline"):
        self.fps = fps
        self.source = source
        self.scenes = [dict(s) for s in scenes]
        self.beats = [float(b) for b in beats]
        self.downbeats = [float(b) for b in downbeats]
        self.duration = duration
        self._scenes = {s["id"]: s for s in self.scenes}
        self._lines = {line["id"]: line for line in lines}

    @property
    def scene_ids(self) -> list[str]:
        return [s["id"] for s in self.scenes]

    def frame(self, t: float) -> int:
        """The film frame showing film time t."""
        return frame(t, self.fps)

    def time(self, f: float) -> float:
        """The film time of film frame f."""
        return f / self.fps

    def scene(self, scene_id: str) -> tuple[float, float]:
        """A scene's window in film seconds [start, end)."""
        s = self._scenes.get(scene_id)
        if s is None:
            have = f"scenes: {', '.join(self._scenes)}" if self._scenes else (
                "it has none: export the engine's with `cd app && bun scripts/timeline.ts --film <id>`, or give the "
                "shot explicit \"frames\"")
            raise KeyError(f"no scene {scene_id!r} in {self.source} ({have})")
        return float(s["start"]), float(s["end"])

    def scene_frames(self, scene_id: str) -> tuple[int, int]:
        """The film frames [f0, f1) the engine shows a scene on: f0 is the first frame at or after its start and f1 the
        first at or after its end (engine.ts ownedFrames: first = f0, last = f1 - 1)."""
        start, end = self.scene(scene_id)
        return first_frame_from(start, self.fps), first_frame_from(end, self.fps)

    def line(self, line_id: str) -> dict:
        line = self._lines.get(line_id)
        if line is None:
            raise KeyError(f"no line {line_id!r} in the film's voiceover")
        return line

    def word(self, line_id: str, i: int) -> Word:
        """Word i (from 0) of a line, with its measured onset `start` (s) and `frame`."""
        words = self.line(line_id)["words"]
        if not 0 <= i < len(words):
            raise IndexError(f"{line_id} has {len(words)} words, no word {i}")
        w = words[i]
        return Word(w["w"], w["start"], w["end"], self.fps)

    def beats_in(self, f0: int, f1: int) -> list[int]:
        """The film frames of the beats in [f0, f1), in order."""
        return [f for f in (frame(t, self.fps) for t in self.beats) if f0 <= f < f1]

    def downbeats_in(self, f0: int, f1: int) -> list[int]:
        """The film frames of the downbeats (bar starts) in [f0, f1), in order."""
        return [f for f in (frame(t, self.fps) for t in self.downbeats) if f0 <= f < f1]


def _read(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def load(root: str | Path, *, fps: float = DEFAULT_FPS, timeline: str = "data/timeline.json", vo: str = "data/vo.json",
         audio: str = "data/audio.json", grid: dict | None = None) -> Timing:
    """The timing of the film folder `root`: scenes from `timeline` (else `vo`'s scenes), lines from `vo`, beats from
    `audio` (else the grid synthesised from `grid`'s bpm, offset and beatsPerBar, defaults GRID, over the film's
    duration: the timeline's, else the voiceover's, else the last scene's end). Paths are relative to `root`; a missing
    file is passed over. Raises ValueError when the timeline was exported at another fps than `fps`."""
    root = Path(root)
    tl, voice, analysis = _read(root / timeline), _read(root / vo), _read(root / audio)
    if tl is not None:
        tl_fps = tl.get("fps", fps)
        if abs(float(tl_fps) - float(fps)) > 1e-9:
            raise ValueError(f"{root / timeline} was exported at {tl_fps} fps but the film runs at {fps}: export it "
                             f"again (cd app && bun scripts/timeline.ts --film {root.name})")
        scenes, source = tl.get("scenes", []), str(root / timeline)
    elif voice is not None and voice.get("scenes"):
        scenes, source = voice["scenes"], str(root / vo)
    else:
        scenes, source = [], f"{root} (no {timeline}, no scenes in {vo})"
    duration = (tl or {}).get("duration") or (voice or {}).get("duration") or (
        max((float(s["end"]) for s in scenes), default=None))
    if analysis is not None:
        beats, downbeats = analysis.get("beats", []), analysis.get("downbeats", [])
    else:
        g = {**GRID, **{k: v for k, v in (grid or {}).items() if k in GRID and v is not None}}
        beats, downbeats = beat_grid(duration, float(g["bpm"]), float(g["offset"]), int(g["beatsPerBar"]))
    return Timing(scenes, fps=fps, lines=(voice or {}).get("lines", []), beats=beats, downbeats=downbeats,
                  duration=duration, source=source)


def for_film(film) -> Timing:
    """A film's timing (lib/film.py Film): its folder, its fps, and film.json's `vo` and `audio` settings."""
    cfg = film.config
    audio = cfg.get("audio") or {}
    return load(film.root, fps=film.fps, vo=cfg.get("vo") or "data/vo.json",
                audio=audio.get("analysis") or "data/audio.json", grid=audio)


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
