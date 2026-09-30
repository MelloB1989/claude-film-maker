"""Draw the score's arc in the mix: a gain lane and a low-pass lane keyed to the analysed sections (spec §5.2).

The music model ignores per-section loudness, so the arc is drawn here, exactly on the beat grid. The cold open is
muffled at −10 dB (low-pass 300 Hz, a heartbeat through a wall). The ex sweeps the filter open to 4 kHz and climbs to
−3 dB. Her opens fully on its first downbeat (the reveal on "Not me"). The tour stays open. Honest dips 12 dB into the
score's own drop within 120 ms. Proof and everywhere slams back on its first downbeat. The last 2 s fade out.
"""
import numpy as np
from scipy.signal import butter, lfilter, lfilter_zi

OPEN = 20000.0
FADE_OUT = 2.0
BLOCK = 256
# section: (gain dB at start, gain dB at end, cutoff Hz at start, cutoff Hz at end, glide-in seconds)
RULES: dict[str, tuple[float, float, float, float, float]] = {
    "cold open": (-10.0, -10.0, 300.0, 300.0, 0.0),
    "the ex": (-10.0, -3.0, 300.0, 4000.0, 0.0),
    "her": (0.0, 0.0, OPEN, OPEN, 0.005),
    "the tour": (0.0, 0.0, OPEN, OPEN, 0.0),
    "honest": (-12.0, -12.0, OPEN, OPEN, 0.12),
    "proof and everywhere": (0.0, 0.0, OPEN, OPEN, 0.005),
    "weave": (0.0, 0.0, OPEN, OPEN, 0.0),
}


def lanes(sections: list[dict], sr: int, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-sample gain (linear) and low-pass cutoff (Hz). Within a section the gain moves linearly in dB and the
    cutoff geometrically. A section with a glide-in moves there from the previous section's end values over that
    many seconds. Unlisted names and any time outside the sections stay open at 0 dB."""
    t = np.arange(n) / sr
    gain_db = np.zeros(n)
    cut = np.full(n, OPEN)
    prev: tuple[float, float] | None = None
    for s in sections:
        g0, g1, c0, c1, glide = RULES.get(s["name"], (0.0, 0.0, OPEN, OPEN, 0.0))
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
    f = int(FADE_OUT * sr)
    if n > f:
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
