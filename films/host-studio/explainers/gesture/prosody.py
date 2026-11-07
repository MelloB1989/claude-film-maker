"""Prosody of the VO: where her voice stresses, from vo.wav and the cues' word times (round 7, agent-10).

Per word:
- its syllable nuclei: peaks of a prominence curve (loudness z + pitch z, 40 ms smoothed) at least 90 ms apart and
  within 6 dB of the word's loudest; the loudest is the word's stressed syllable (`peak_t`), the rest `nuclei`;
- a stress score 0..1 from the nucleus loudness, its pitch excursion above her median and the word's length;
- `energy`: her local vocal energy 0..1 (loudness over ~0.5 s, the film's 5th-95th percentile).
The planner places each gesture's stroke apex 80-200 ms BEFORE the stressed syllable's peak and scales its amplitude
and speed by `energy`; secondary stresses (strong nuclei / content words between gestures) take beats.

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
    from scipy.ndimage import gaussian_filter1d, uniform_filter1d
    sp = env > np.percentile(env, 30)
    ez = (env - env[sp].mean()) / (env[sp].std() + 1e-9)
    pz = np.where(f0 > 0, st / (np.abs(st[f0 > 0]).std() + 1e-9), 0.0)
    prom = gaussian_filter1d(ez + 0.6 * pz, 8)  # 40 ms
    nw = int(0.5 / HOP)  # loudness over ~0.5 s of SPEECH only (a line's first word is not diluted by the pause)
    loud = uniform_filter1d(env * sp, nw) / np.maximum(uniform_filter1d(sp.astype(float), nw), 1e-3)
    lo, hi = np.percentile(loud[sp], 5), np.percentile(loud[sp], 95)
    energy = np.clip((loud - lo) / (hi - lo), 0, 1)
    words = []
    for ln in cues["lines"]:
        for wi, w in enumerate(ln["words"]):
            m = (t >= w["start"]) & (t <= w["end"])
            if not m.any():
                continue
            k = np.flatnonzero(m)
            pk = k[np.argmax(env[k])]
            v = k[f0[k] > 0]
            # nuclei: local maxima of the prominence, >= 90 ms apart, within 6 dB of the word's loudest
            cand = [i for i in k[1:-1] if prom[i] >= prom[i - 1] and prom[i] >= prom[i + 1] and env[i] >= env[pk] - 6]
            cand.sort(key=lambda i: -prom[i])
            nuc = []
            for i in cand:
                if all(abs(i - j) * HOP >= 0.09 for j in nuc):
                    nuc.append(i)
            nuc = nuc or [pk]
            main = max(nuc, key=lambda i: env[i])  # the stressed syllable: the loudest nucleus
            words.append({"line": ln["id"], "i": wi, "w": w["w"], "start": w["start"], "end": w["end"],
                          "peak_t": round(float(t[main]), 3),
                          "nuclei": [{"t": round(float(t[i]), 3), "prom": round(float(prom[i]), 2)}
                                     for i in sorted(nuc)],
                          "prom": round(float(prom[main]), 2), "energy": round(float(energy[main]), 3),
                          "db": float(env[main]),
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
            "energy": [round(float(v), 3) for v in energy[::4]], "energy_hop": HOP * 4, "energy_t0": 0.015}


if __name__ == "__main__":
    film = sys.argv[1] if len(sys.argv) > 1 else "netflix"
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    res = analyse(film)
    (out / f"prosody_{film}.json").write_text(json.dumps(res, indent=1))
    for w in sorted(res["words"], key=lambda w: -w["stress"])[:20]:
        print(w["line"], w["w"], w["peak_t"], w["stress"])
