"""Sequencer time, pure (no `unreal`): frame rates, display frames, ticks, seconds and timecode.

A level sequence counts time in two rates: the DISPLAY rate (what the user sees: 24, 25, 30000/1001 fps) and the TICK
resolution (what keys and sections are stored in: 24000/s by default, 60000 in some templates). Every op here takes
and returns display frames; only a few engine calls (a section's start offset, easing, parameter keys) want ticks, and
`Rate.to_ticks` makes them.

    r = Rate.parse("23.976")            # Rate(24000, 1001)
    r.seconds(48)                       # 2.002
    r.frame(2.002)                      # 48.0
    r.timecode(86400 + 12)              # "01:00:00:12"   (non-drop; "01:00:00;12" drop-frame for 29.97/59.94)
    r.parse_time("00:00:02:00")         # 48.0 frames; also "2s", "48f", "1.5", 48
    ticks(48, r, Rate(24000))           # 48048 ticks at 24000/s
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

# the common names an agent might write for a rate
_NAMED = {
    "film": (24, 1), "24": (24, 1), "23.976": (24000, 1001), "23.98": (24000, 1001), "ntsc_film": (24000, 1001),
    "pal": (25, 1), "25": (25, 1), "29.97": (30000, 1001), "ntsc": (30000, 1001), "30": (30, 1), "48": (48, 1),
    "50": (50, 1), "59.94": (60000, 1001), "60": (60, 1), "120": (120, 1),
}
DEFAULT_TICKS = 24000  # UMovieScene's default tick resolution (UE 5.x: 24000 frames per second)


@dataclass(frozen=True)
class Rate:
    """A frame rate as numerator/denominator, like unreal.FrameRate."""
    numerator: int
    denominator: int = 1

    def __post_init__(self):
        if self.numerator <= 0 or self.denominator <= 0:
            raise ValueError(f"a frame rate must be positive, got {self.numerator}/{self.denominator}")

    @staticmethod
    def parse(v) -> "Rate":
        """24, 23.976, "30000/1001", "29.97", "ntsc", [24000, 1001], {"numerator", "denominator"}, or an
        unreal.FrameRate (anything with numerator/denominator)."""
        if isinstance(v, Rate):
            return v
        if hasattr(v, "numerator") and hasattr(v, "denominator") and not isinstance(v, (int, float, Fraction)):
            return Rate(int(v.numerator), int(v.denominator))
        if isinstance(v, dict):
            return Rate(int(v["numerator"]), int(v.get("denominator", 1)))
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return Rate(int(v[0]), int(v[1]))
        s = str(v).strip().lower().removesuffix("fps").strip()
        if s in _NAMED:
            return Rate(*_NAMED[s])
        if "/" in s:
            n, d = s.split("/", 1)
            return Rate(int(n), int(d))
        try:
            f = float(s)
        except ValueError:
            raise ValueError(f"not a frame rate: {v!r} (try 24, 25, 30, 23.976, 29.97, '30000/1001')") from None
        if f <= 0:
            raise ValueError(f"a frame rate must be positive, got {v!r}")
        if abs(f - round(f)) < 1e-9:
            return Rate(int(round(f)))
        for n, d in ((24000, 1001), (30000, 1001), (60000, 1001), (48000, 1001), (120000, 1001)):
            if abs(f - n / d) < 0.01:
                return Rate(n, d)
        fr = Fraction(f).limit_denominator(1001)
        return Rate(fr.numerator, fr.denominator)

    @property
    def fps(self) -> float:
        return self.numerator / self.denominator

    @property
    def fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    def seconds(self, frame: float) -> float:
        """Display frames to seconds."""
        return float(Fraction(frame).limit_denominator(10 ** 6) / self.fraction) if isinstance(frame, float) else \
            float(Fraction(frame) / self.fraction)

    def frame(self, seconds: float) -> float:
        """Seconds to (fractional) display frames."""
        return float(seconds) * self.fps

    def frames_ceil(self, seconds: float) -> int:
        """Whole frames that cover `seconds` (a clip of 2.01 s at 24 fps needs 49 frames)."""
        return int(math.ceil(round(float(seconds) * self.fps, 6)))

    def is_drop(self) -> bool:
        """Drop-frame timecode applies to the NTSC rates 29.97 and 59.94."""
        return self.denominator == 1001 and self.numerator in (30000, 60000)

    def timecode(self, frame: int, drop: bool | None = None) -> str:
        """Display frame -> "HH:MM:SS:FF" (";FF" for drop-frame, the default at 29.97/59.94). Negative frames get a
        leading "-"."""
        frame = int(round(frame))
        sign = "-" if frame < 0 else ""
        frame = abs(frame)
        nominal = int(round(self.fps))
        drop = self.is_drop() if drop is None else drop
        if drop:
            d = 2 * nominal // 30  # frames dropped per minute: 2 at 29.97, 4 at 59.94
            per10 = nominal * 600 - 9 * d
            per1 = nominal * 60 - d
            tens, rem = divmod(frame, per10)
            frame += 9 * d * tens + (d * ((rem - d) // per1) if rem > d else 0)
        ff = frame % nominal
        s = frame // nominal
        return f"{sign}{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}{';' if drop else ':'}{ff:02d}"

    def from_timecode(self, tc: str) -> int:
        """"HH:MM:SS:FF" (or ";FF" drop-frame) -> display frame."""
        m = re.fullmatch(r"(-?)(\d+):(\d\d):(\d\d)([:;.])(\d+)", tc.strip())
        if not m:
            raise ValueError(f"not a timecode: {tc!r} (want HH:MM:SS:FF)")
        sign, hh, mm, ss, sep, ff = m.groups()
        nominal = int(round(self.fps))
        total_min = int(hh) * 60 + int(mm)
        frame = (total_min * 60 + int(ss)) * nominal + int(ff)
        if sep == ";" or (sep != ":" and self.is_drop()):
            d = 2 * nominal // 30
            frame -= d * (total_min - total_min // 10)
        return -frame if sign else frame

    def parse_time(self, v) -> float:
        """A time as display frames: a number (frames), "48f", "2s"/"2.5s", "1m30s", "500ms", "HH:MM:SS:FF"."""
        if isinstance(v, bool):
            raise ValueError(f"not a time: {v!r}")
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().lower()
        if ":" in s:
            return float(self.from_timecode(s))
        m = re.fullmatch(r"(-?[\d.]+)\s*f(rames?)?", s)
        if m:
            return float(m.group(1))
        m = re.fullmatch(r"(?:(-?[\d.]+)\s*m(?!s))?\s*(?:(-?[\d.]+)\s*s)?", s)
        if m and (m.group(1) or m.group(2)):
            return self.frame(float(m.group(1) or 0) * 60 + float(m.group(2) or 0))
        m = re.fullmatch(r"(-?[\d.]+)\s*ms", s)
        if m:
            return self.frame(float(m.group(1)) / 1000)
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"not a time: {v!r} (frames 48, '48f', '2s', '1m30s', '500ms' or 'HH:MM:SS:FF')") from None

    def to_ticks(self, frame: float, ticks: "Rate | int" = DEFAULT_TICKS) -> int:
        return to_ticks(frame, self, ticks)

    def from_ticks(self, tick: int, ticks: "Rate | int" = DEFAULT_TICKS) -> float:
        return from_ticks(tick, self, ticks)

    def __str__(self) -> str:
        return f"{self.numerator}" if self.denominator == 1 else f"{self.numerator}/{self.denominator}"

    def to_json(self):
        return {"numerator": self.numerator, "denominator": self.denominator, "fps": round(self.fps, 6)}


def _ticks_rate(ticks) -> Rate:
    return ticks if isinstance(ticks, Rate) else Rate.parse(ticks)


def to_ticks(frame: float, display: Rate, ticks: "Rate | int" = DEFAULT_TICKS) -> int:
    """Display frames (may be fractional) to the tick resolution, rounded to the nearest tick (as FFrameRate::
    TransformTime(...).RoundToFrame() does)."""
    t = _ticks_rate(ticks)
    v = Fraction(frame).limit_denominator(10 ** 6) * t.fraction / display.fraction
    return int(math.floor(v + Fraction(1, 2)))


def from_ticks(tick: int, display: Rate, ticks: "Rate | int" = DEFAULT_TICKS) -> float:
    t = _ticks_rate(ticks)
    return float(Fraction(int(tick)) * display.fraction / t.fraction)


def convert(frame: float, src: Rate, dst: Rate) -> float:
    """A frame at one display rate as a frame at another (same instant)."""
    return float(Fraction(frame).limit_denominator(10 ** 6) * dst.fraction / src.fraction)


def snap(frame: float, tol: float = 1e-6):
    """A frame as an int when it is whole (within tol), else the float: keys at whole frames compare and print
    cleanly."""
    r = round(frame)
    return int(r) if abs(frame - r) <= tol else float(frame)


STANDARD_TICKS = (24000, 48000, 60000, 120000, 240000)


def ticks_per_frame(display: Rate, ticks: "Rate | int") -> float:
    t = _ticks_rate(ticks)
    return float(t.fraction / display.fraction)


def compatible_ticks(display_rates, current: int = DEFAULT_TICKS) -> int:
    """A tick resolution (per second) on which every one of `display_rates` lands on whole ticks: `current` when it
    does already, else the smallest standard one that does (24000 suits 24/25/30/48/60 and 23.976; 29.97 and 59.94
    need 60000). Sequencer warns, and frames drift by sub-ticks, on an incompatible pair."""
    rates = [Rate.parse(r) for r in display_rates]

    def ok(t):
        return all((Fraction(t) / r.fraction).denominator == 1 for r in rates)
    if ok(current):
        return int(current)
    for t in STANDARD_TICKS:
        if ok(t):
            return t
    raise ValueError(f"no standard tick resolution fits {[str(r) for r in rates]}")
