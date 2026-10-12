"""Draw the score's arc in the mix: a gain lane and a low-pass lane keyed to the analysed sections.

A music model ignores per-section loudness, so the arc is drawn here, exactly on the beat grid. Each section of
film.json pipeline.music.sections may set `gain_db` (a value, or [start, end] moved linearly in dB), `cutoff_hz` (a
low-pass, a value or [start, end] moved geometrically; default open) and `glide` (seconds to move there from the
previous section's end values; 0 changes on the section's first sample). For example: an intro muffled at -10 dB
(cutoff 300 Hz), a build that sweeps the filter open and climbs to -3 dB, a chorus that opens fully on its first
downbeat, a drop that dips 12 dB within 120 ms. The last `fade_out` seconds (pipeline.music.fade_out) fade out.
"""
import numpy as np
from scipy.signal import butter, lfilter, lfilter_zi

OPEN = 20000.0
FADE_OUT = 2.0
BLOCK = 256
Rule = tuple[float, float, float, float, float]  # (gain dB at start, at end, cutoff Hz at start, at end, glide-in s)


def _pair(v, default: float) -> tuple[float, float]:
    if v is None:
        return default, default
    if isinstance(v, (int, float)):
        return float(v), float(v)
    a, b = v
    return float(a), float(b)


def rules_from(music: dict) -> dict[str, Rule] | None:
    """The automation of pipeline.music.sections, by section name; None when the film configures no sections
    (then nothing is drawn but the fade-out)."""
    secs = music.get("sections") or []
    if not secs:
        return None
    rules = {}
    for s in secs:
        g0, g1 = _pair(s.get("gain_db"), 0.0)
        c0, c1 = _pair(s.get("cutoff_hz"), OPEN)
        rules[s["name"]] = (g0, g1, c0, c1, float(s.get("glide", 0.0)))
    return rules


def lanes(sections: list[dict], sr: int, n: int, rules: dict[str, Rule] | None = None,
          fade_out: float = FADE_OUT) -> tuple[np.ndarray, np.ndarray]:
    """Per-sample gain (linear) and low-pass cutoff (Hz). Within a section the gain moves linearly in dB and the
    cutoff geometrically. A section with a glide-in moves there from the previous section's end values over that
    many seconds. Time outside the sections stays open at 0 dB. Given `rules`, a section with no rule is an error (a
    misspelt name would otherwise play open, silently); without them every section plays open. The last `fade_out`
    seconds fade out along a raised cosine."""
    t = np.arange(n) / sr
    gain_db = np.zeros(n)
    cut = np.full(n, OPEN)
    prev: tuple[float, float] | None = None
    for s in sections if rules is not None else []:
        if s["name"] not in rules:
            raise ValueError(f"no automation rule for section {s['name']!r} (rules: {', '.join(rules)})")
        g0, g1, c0, c1, glide = rules[s["name"]]
        m = (t >= s["start"]) & (t < s["end"])
        if m.any():
            u = (t[m] - s["start"]) / max(1e-9, s["end"] - s["start"])
            g = g0 + (g1 - g0) * u
            c = c0 * (c1 / c0) ** u
            if glide > 0 and prev is not None:
                r = np.clip((t[m] - s["start"]) / glide, 0.0, 1.0)
                g = prev[0] + (g - prev[0]) * r
                c = prev[1] * (c / prev[1]) ** r
            gain_db[m], cut[m] = g, c
        prev = (g1, c1)
    gain = 10 ** (gain_db / 20)
    f = int(fade_out * sr)
    if 0 < f < n:
        gain[-f:] *= 0.5 * (1 + np.cos(np.linspace(0.0, np.pi, f)))
    return gain.astype(np.float32), cut.astype(np.float32)


def apply(y: np.ndarray, sr: int, gain: np.ndarray, cutoff: np.ndarray) -> np.ndarray:
    """Time-varying 2nd-order Butterworth low-pass (coefficients per BLOCK samples, filter state carried across
    blocks, started at steady state), then the gain lane."""
    x = y[:, None] if y.ndim == 1 else y
    out = np.empty(x.shape, dtype=np.float32)
    nyq = sr / 2
    zi = None
    for i in range(0, len(x), BLOCK):
        fc = float(np.clip(cutoff[i:i + BLOCK].mean(), 20.0, 0.95 * nyq))
        b, a = butter(2, fc / nyq)
        if zi is None:
            zi = np.stack([lfilter_zi(b, a) * x[0, ch] for ch in range(x.shape[1])], axis=1)
        blk, zi = lfilter(b, a, x[i:i + BLOCK], axis=0, zi=zi)
        out[i:i + BLOCK] = blk
    out *= gain[:len(out), None]
    return out[:, 0] if y.ndim == 1 else out


DUCK_BUSES = ("music", "all")


def duck_lanes(ducks: list[dict], sr: int, n: int, bus: str) -> np.ndarray:
    """Per-sample linear gain from the cue sheet's ducks on one bus ('music', or 'all' for music and effects; the
    voice is never ducked). A duck holds its full depth over [t, t + dur] and moves there and back along a
    raised-cosine over `fade` seconds either side (cue.ts). Overlapping ducks multiply."""
    if bus not in DUCK_BUSES:
        raise ValueError(f"no duck bus {bus!r} (buses: {', '.join(DUCK_BUSES)})")
    g = np.ones(n)
    t = np.arange(n) / sr
    for d in ducks:
        if d["bus"] != bus:
            continue
        t0, t1, f = d["t"], d["t"] + d["dur"], max(d.get("fade", 0.0), 0.0)
        m = (t >= t0 - f) & (t < t1 + f)
        if not m.any():
            continue
        tt = t[m]
        if f > 0:
            u = np.clip(np.minimum(tt - (t0 - f), (t1 + f) - tt) / f, 0.0, 1.0)  # 0 outside → 1 at full depth
            w = 0.5 * (1 - np.cos(np.pi * u))
        else:
            w = ((tt >= t0) & (tt < t1)).astype(float)
        g[m] *= 10 ** (d["depth"] * w / 20)
    return g.astype(np.float32)
