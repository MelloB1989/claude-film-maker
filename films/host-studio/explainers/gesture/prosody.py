"""Prosody of the VO: where her voice stresses, from vo.wav and the cues' word times (round 7, agent-10).

Per word: its loudness peak (the syllable nucleus), its pitch excursion above her running median and its length, put
together into a stress score in 0..1 with the time of the peak. The planner puts gesture strokes (the sheet's, and the
micro-beats between them) on these peaks: a stroke lands on the stressed syllable's nucleus, not the word's start.

    python gesture/prosody.py netflix        -> gesture/out/prosody_netflix.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
EXPL = HERE.parent
HOP = 0.005  # s


def load(film: str):
    cues = json.loads((EXPL / "audio" / film / "cues.json").read_text())
    x, sr = sf.read(EXPL / cues["vo"], always_2d=True)
    return cues, x.mean(axis=1).astype(np.float64), sr


def envelope(x, sr):
    """Loudness (dB, 30 ms window) every HOP, band-passed to the voice (80 Hz - 4 kHz) so breaths count less."""
    from scipy.signal import butter, sosfiltfilt
    sos = butter(4, [80, 4000], btype="band", fs=sr, output="sos")
    y = sosfiltfilt(sos, x)
    hop, win = int(HOP * sr), int(0.03 * sr)
    n = 1 + (len(y) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    rms = np.sqrt((y[idx] ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms)


def pitch(x, sr, fmin=120.0, fmax=450.0):
    """F0 in Hz every HOP (0 = unvoiced): a plain YIN on 16 kHz audio, 40 ms frames."""
    from scipy.signal import resample_poly
    y = resample_poly(x, 16000, sr)
    sr2 = 16000
    hop, win = int(HOP * sr2), int(0.04 * sr2)
    tmin, tmax = int(sr2 / fmax), int(sr2 / fmin)
    n = 1 + (len(y) - win - tmax) // hop
    f0 = np.zeros(n)
    for i in range(n):
        s = y[i * hop: i * hop + win + tmax]
        if np.sqrt((s[:win] ** 2).mean()) < 1e-3:
            continue
        # difference function by FFT autocorrelation
        w = s[:win]
        d = np.array([((w - s[t:t + win]) ** 2).sum() for t in range(tmax + 1)])
        cm = d.copy()
        cm[1:] = d[1:] * np.arange(1, tmax + 1) / np.maximum(np.cumsum(d[1:]), 1e-12)
        cm[0] = 1
        band = cm[tmin:tmax + 1]
        k = np.argmax(band < 0.15) if (band < 0.15).any() else None
        if k is None:
            continue
        t = tmin + k
        while t + 1 <= tmax and cm[t + 1] < cm[t]:
            t += 1
        f0[i] = sr2 / t
    return f0


def analyse(film: str) -> dict:
    cues, x, sr = load(film)
    env = envelope(x, sr)
    f0 = pitch(x, sr)
    n = min(len(env), len(f0))
    env, f0 = env[:n], f0[:n]
    t = np.arange(n) * HOP + 0.015
    voiced = f0[f0 > 0]
    st = np.zeros(n)
    st[f0 > 0] = 12 * np.log2(f0[f0 > 0] / np.median(voiced))  # semitones from her median
    words = []
    for ln in cues["lines"]:
        for wi, w in enumerate(ln["words"]):
            m = (t >= w["start"]) & (t <= w["end"])
            if not m.any():
                continue
            k = np.flatnonzero(m)
            pk = k[np.argmax(env[k])]
            v = k[f0[k] > 0]
            words.append({"line": ln["id"], "i": wi, "w": w["w"], "start": w["start"], "end": w["end"],
                          "peak_t": round(float(t[pk]), 3), "db": float(env[pk]),
                          "st": float(np.percentile(st[v], 90)) if len(v) else 0.0,
                          "dur": w["end"] - w["start"]})

    def z(key):
        a = np.array([w[key] for w in words])
        return (a - a.mean()) / (a.std() + 1e-9)

    score = 0.45 * z("db") + 0.35 * z("st") + 0.2 * z("dur")
    lo, hi = np.percentile(score, 5), np.percentile(score, 95)
    for w, s in zip(words, score):
        w["stress"] = round(float(np.clip((s - lo) / (hi - lo), 0, 1)), 3)
        w["db"], w["st"], w["dur"] = round(w["db"], 1), round(w["st"], 2), round(w["dur"], 3)
    return {"film": film, "hop": HOP, "words": words,
            "env_db": [round(float(v), 1) for v in env[::4]], "env_hop": HOP * 4}


if __name__ == "__main__":
    film = sys.argv[1] if len(sys.argv) > 1 else "netflix"
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    res = analyse(film)
    (out / f"prosody_{film}.json").write_text(json.dumps(res, indent=1))
    for w in sorted(res["words"], key=lambda w: -w["stress"])[:20]:
        print(w["line"], w["w"], w["peak_t"], w["stress"])
