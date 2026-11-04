"""A voice's loudness over time, with the standard library only (the editor's Python has no numpy): where the
speaker pauses (phrase ends, for blinks and resets) and where they stress a word (emphasis, for beat nods and brow
flashes), so a performance can follow the line without anyone marking it by hand.

    env = Envelope.from_wav("/path/line1.wav")
    env.at(1.2)        # loudness 0..1 at 1.2 s
    env.pauses()       # [(t0, t1)] silences over 0.25 s
    env.emphasis()     # [(t, strength 0..1)]: syllable peaks that stand out from their neighbourhood
"""
from __future__ import annotations

import array
import math
import sys
import wave

from . import curves as C


class Envelope:
    """Loudness (RMS in dB, mapped to 0..1 over the clip's own range) at `rate` Hz from t=0."""

    def __init__(self, values: list, rate: float = 100.0, offset_s: float = 0.0):
        self.rate, self.offset_s = rate, offset_s
        self.values = values
        self.times = [offset_s + i / rate for i in range(len(values))]

    @property
    def duration_s(self) -> float:
        return len(self.values) / self.rate

    @classmethod
    def from_wav(cls, path: str, rate: float = 100.0, offset_s: float = 0.0, floor_db: float = -50.0) -> "Envelope":
        """Read a PCM WAV (8/16/24/32-bit, any channels; mixed to mono) into an envelope."""
        with wave.open(path, "rb") as w:
            ch, width, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
        return cls.from_pcm(raw, width, ch, sr, rate, offset_s, floor_db)

    @classmethod
    def from_pcm(cls, raw: bytes, width: int, channels: int, sample_rate: int, rate: float = 100.0,
                 offset_s: float = 0.0, floor_db: float = -50.0) -> "Envelope":
        if width == 2:
            a = array.array("h")
            a.frombytes(raw)
            if sys.byteorder == "big":
                a.byteswap()
            scale = 32768.0
        elif width == 4:
            a = array.array("i")
            a.frombytes(raw)
            if sys.byteorder == "big":
                a.byteswap()
            scale = 2147483648.0
        elif width == 1:
            a = array.array("h", (b - 128 for b in raw))
            scale = 128.0
        elif width == 3:
            a = array.array("i", (int.from_bytes(raw[i:i + 3], "little", signed=True) for i in range(0, len(raw), 3)))
            scale = 8388608.0
        else:
            raise ValueError(f"unsupported sample width {width}")
        hop = max(1, int(sample_rate / rate))
        mono = a[::channels] if channels > 1 else a  # the first channel is plenty for loudness
        # sum of squares per hop, once; each frame's window is two hops
        sq = [sum(x * x for x in mono[i:i + hop]) for i in range(0, len(mono), hop)]
        dbs = []
        for k in range(max(1, len(sq) - 1)):
            n = min(len(mono) - k * hop, 2 * hop)
            if n <= 0:
                break
            acc = sq[k] + (sq[k + 1] if k + 1 < len(sq) else 0.0)
            rms = math.sqrt(acc / n) / scale
            dbs.append(20.0 * math.log10(max(rms, 1e-9)))
        if not dbs:
            return cls([0.0], rate, offset_s)
        top = sorted(dbs)[int(len(dbs) * 0.98)]
        lo = max(floor_db, top - 45.0)
        vals = [C.clamp((d - lo) / max(1e-6, top - lo)) for d in dbs]
        return cls(vals, rate, offset_s)

    def at(self, t: float) -> float:
        i = (t - self.offset_s) * self.rate
        if i < 0 or i >= len(self.values) - 1:
            return 0.0
        k = int(i)
        u = i - k
        return self.values[k] * (1 - u) + self.values[k + 1] * u

    def smoothed(self, cutoff_hz: float = 6.0) -> list:
        return C.lowpass(self.values, self.rate, cutoff_hz, passes=1)

    def pauses(self, threshold: float = 0.18, min_s: float = 0.25) -> list:
        """Silences (loudness under `threshold` for at least `min_s`): [(t0, t1)], leading/trailing silence
        included."""
        sm = self.smoothed(8.0)
        out, start = [], None
        for i, v in enumerate(sm):
            t = self.offset_s + i / self.rate
            if v < threshold and start is None:
                start = t
            elif v >= threshold and start is not None:
                if t - start >= min_s:
                    out.append((round(start, 3), round(t, 3)))
                start = None
        if start is not None and self.offset_s + len(sm) / self.rate - start >= min_s:
            out.append((round(start, 3), round(self.offset_s + len(sm) / self.rate, 3)))
        return out

    def phrase_ends(self, **kw) -> list:
        """The start of each pause that follows speech: where a phrase ends."""
        first_voice = next((self.offset_s + i / self.rate for i, v in enumerate(self.values) if v > 0.3), None)
        return [p[0] for p in self.pauses(**kw) if first_voice is not None and p[0] > first_voice]

    def emphasis(self, min_gap_s: float = 0.35, k: float = 0.6, window_s: float = 1.2, top: int | None = None) -> list:
        """Stressed syllables: local maxima of the smoothed loudness that stand `k` standard deviations above the
        mean of the `window_s` around them, at least `min_gap_s` apart; [(t, strength 0..1)], strongest kept when
        `top` is given (in time order either way)."""
        sm = self.smoothed(5.0)
        n = len(sm)
        half = max(1, int(window_s * self.rate / 2))
        cands = []
        for i in range(1, n - 1):
            if not (sm[i] >= sm[i - 1] and sm[i] > sm[i + 1] and sm[i] > 0.35):
                continue
            seg = sm[max(0, i - half):min(n, i + half)]
            mean = sum(seg) / len(seg)
            sd = math.sqrt(sum((x - mean) ** 2 for x in seg) / len(seg)) or 1e-6
            z = (sm[i] - mean) / sd
            if z >= k:
                cands.append((self.offset_s + i / self.rate, z, sm[i]))
        cands.sort(key=lambda c: -c[1])
        picked = []
        for t, z, v in cands:
            if all(abs(t - p[0]) >= min_gap_s for p in picked):
                picked.append((t, z, v))
        if top:
            picked = picked[:top]
        zmax = max((p[1] for p in picked), default=1.0)
        return sorted((round(t, 3), round(min(1.0, 0.4 + 0.6 * z / zmax), 2)) for t, z, v in picked)

    def talking(self, threshold: float = 0.2) -> list:
        """Spans where the voice is on: [(t0, t1)], the complement of pauses within the clip."""
        ps = self.pauses(threshold)
        out, t = [], self.offset_s
        for a, b in ps:
            if a > t:
                out.append((round(t, 3), a))
            t = b
        end = self.offset_s + self.duration_s
        if end > t:
            out.append((round(t, 3), round(end, 3)))
        return out
