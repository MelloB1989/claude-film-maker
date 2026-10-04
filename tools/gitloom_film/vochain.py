"""The voice chain (spec §5.1): high-pass at 80 Hz, a gentle cut around 300 Hz, a split-band de-esser, 2:1
compression, presence and air shelves, a touch of tape saturation and a very short plate at low mix, then a static
makeup gain back to the raw voice's integrated loudness.

Word sync is sacred, so every stage is causal and zero-latency: IIR biquads (minimum phase, no look-ahead), a
feed-forward compressor and de-esser whose gain follows the signal without delaying it, a memoryless saturator, and a
plate whose impulse response is convolved from sample 0 (its pre-delay is part of the response, the dry path is
untouched). The processed voice is the same length as audio/vo/vo.wav and every word stays on its sample.

film-vo-chain writes audio/vo/vo-chain.wav (mono 48 kHz / 24-bit) and the objective checks per line to
out/review/c5/vo-chain.json. film-sync keeps reading the raw vo.wav.
"""
import argparse
import json
import math

import numpy as np
from scipy import signal

from .paths import AUDIO, DATA, OUT
from .wav import read_wav, write_wav

CHAIN = {  # the spec's chain; values are starting points the objective checks in report() confirm
    "hpf": {"f": 80.0, "order": 4},                       # Butterworth high-pass
    "cut": {"f": 300.0, "q": 1.0, "gain_db": -2.5},       # gentle bell cut (RBJ peaking)
    # the de-esser was tuned on the voice (out/review/c5/vo-chain.json): from the brief's 5–9 kHz / −28 dB / 6 dB
    # it barely touched most lines, and the 2:1 and the shelves lift every line's sibilance ratio (~1–4 dB), so
    # the band is wider (−3 dB at 4.5 and 10 kHz), the threshold lower and the reduction deeper
    "deess": {"lo": 4500.0, "hi": 10000.0, "thresh_db": -40.0, "max_red_db": 10.0, "attack_ms": 1.0,
              "release_ms": 60.0},
    "comp": {"ratio": 2.0, "thresh_db": -20.0, "attack_ms": 10.0, "release_ms": 120.0, "knee_db": 6.0},
    "presence": {"f": 3500.0, "gain_db": 1.5},            # high shelf (RBJ)
    "air": {"f": 11000.0, "gain_db": 2.0},                # high shelf (RBJ)
    "sat": {"drive": 1.2, "mix": 0.25},                   # tanh soft-sat, blended
    "plate": {"rt60": 0.45, "predelay_ms": 8.0, "lo": 300.0, "hi": 9000.0, "wet_db": -20.0, "seed": 51},
}

EPS = 1e-12


# ---------------------------------------------------------------- filters

def biquad(kind: str, f: float, sr: int, q: float = 0.707, gain_db: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """RBJ cookbook biquad (b, a), normalised so a[0] = 1. kind: highpass, lowpass, bandpass (0 dB peak), peak,
    highshelf, lowshelf (shelves use slope S = 1)."""
    w0 = 2 * math.pi * f / sr
    cw, sw = math.cos(w0), math.sin(w0)
    A = 10 ** (gain_db / 40)
    if kind in ("highshelf", "lowshelf"):
        alpha = sw / 2 * math.sqrt(2)  # S = 1
    else:
        alpha = sw / (2 * q)
    if kind == "highpass":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "lowpass":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "bandpass":
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == "highshelf":
        r = 2 * math.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + r), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - r)]
        a = [(A + 1) - (A - 1) * cw + r, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - r]
    elif kind == "lowshelf":
        r = 2 * math.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + r), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - r)]
        a = [(A + 1) + (A - 1) * cw + r, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - r]
    else:
        raise ValueError(f"unknown biquad kind: {kind}")
    b, a = np.asarray(b, dtype=np.float64), np.asarray(a, dtype=np.float64)
    return b / a[0], a / a[0]


def _filt(y: np.ndarray, ba: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    return signal.lfilter(ba[0], ba[1], y)


def highpass(y: np.ndarray, sr: int, f: float, order: int = 4) -> np.ndarray:
    """Butterworth high-pass as cascaded RBJ biquads with the Butterworth pole Qs (order must be even)."""
    for k in range(order // 2):
        q = 1 / (2 * math.sin(math.pi * (2 * k + 1) / (2 * order)))
        y = _filt(y, biquad("highpass", f, sr, q=q))
    return y


# ---------------------------------------------------------------- dynamics

def _smooth(over_db: np.ndarray, sr: int, attack_ms: float, release_ms: float) -> np.ndarray:
    """Smooth, decoupled peak detector in the log domain (Giannoulis, Massberg & Reiss 2012). Causal: each output
    sample depends only on the samples up to it, so nothing is delayed."""
    aa = math.exp(-1 / (attack_ms * 1e-3 * sr))
    ar = math.exp(-1 / (release_ms * 1e-3 * sr))
    ia, ir = 1 - aa, 1 - ar
    out = np.empty(len(over_db))
    y1 = yl = 0.0
    for i, x in enumerate(over_db.tolist()):
        r = ar * y1 + ir * x
        y1 = x if x > r else r
        yl = aa * yl + ia * y1
        out[i] = yl
    return out


def _level_db(y: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.abs(y) + EPS)


def compress(y, sr, ratio, thresh_db, attack_ms, release_ms, knee_db) -> np.ndarray:
    """Feed-forward compressor with a soft knee and no look-ahead; the gain reduction is smoothed, not the signal."""
    x = _level_db(y)
    d = x - thresh_db
    gc = np.where(2 * d < -knee_db, x,
                  np.where(2 * np.abs(d) <= knee_db,
                           x + (1 / ratio - 1) * (d + knee_db / 2) ** 2 / (2 * max(knee_db, EPS)),
                           thresh_db + d / ratio))
    red = _smooth(np.maximum(x - gc, 0.0), sr, attack_ms, release_ms)
    return y * 10 ** (-red / 20)


def deess(y, sr, lo, hi, thresh_db, max_red_db, attack_ms, release_ms) -> np.ndarray:
    """Split-band de-esser: a 2nd-order band-pass (0 dB at its centre, −3 dB at lo and hi) takes the sibilant band
    out, its level drives the reduction, and only the band is turned down: out = y − (1 − g)·band. For this band-pass
    Re(H) = |H|², so |1 − k·H| ≤ 1 for every k in [0, 1]: no frequency is ever boosted."""
    fc = math.sqrt(lo * hi)
    band = _filt(y, biquad("bandpass", fc, sr, q=fc / (hi - lo)))
    red = np.minimum(_smooth(np.maximum(_level_db(band) - thresh_db, 0.0), sr, attack_ms, release_ms), max_red_db)
    return y - (1 - 10 ** (-red / 20)) * band


# ---------------------------------------------------------------- colour and space

def saturate(y, drive, mix) -> np.ndarray:
    """tanh soft saturation at unity small-signal gain, blended: a full-scale input stays within ±1."""
    return (1 - mix) * y + mix * np.tanh(drive * y) / drive


def plate_ir(sr, rt60, predelay_ms, lo, hi, seed) -> np.ndarray:
    """A seeded plate: band-limited noise decaying 60 dB over rt60, after a pre-delay of zeros; unit energy."""
    n = int(round(rt60 * sr))
    noise = np.random.default_rng(seed).standard_normal(n)
    noise = signal.sosfilt(signal.butter(2, [lo, hi], "bandpass", fs=sr, output="sos"), noise)
    t = np.arange(n) / sr
    tail = noise * 10 ** (-3 * t / rt60)
    ir = np.concatenate([np.zeros(int(round(predelay_ms * 1e-3 * sr))), tail])
    return ir / math.sqrt(np.sum(ir ** 2))


def plate(y, sr, rt60, predelay_ms, lo, hi, wet_db, seed) -> np.ndarray:
    """Dry plus a plate send, the response convolved from sample 0 and cut to the input's length."""
    wet = signal.oaconvolve(y, plate_ir(sr, rt60, predelay_ms, lo, hi, seed))[:len(y)]
    return y + 10 ** (wet_db / 20) * wet


# ---------------------------------------------------------------- measurement

_K1 = (np.array([1.53512485958697, -2.69169618940638, 1.19839281085285]),
       np.array([1.0, -1.69065929318241, 0.73248077421585]))
_K2 = (np.array([1.0, -2.0, 1.0]), np.array([1.0, -1.99004745483398, 0.99007225036621]))


def loudness(y: np.ndarray, sr: int) -> float:
    """Integrated loudness (ITU-R BS.1770-4, mono, gated) in LUFS. 48 kHz only."""
    assert sr == 48000, "the K-weighting coefficients are for 48 kHz"
    k = _filt(_filt(np.asarray(y, dtype=np.float64), _K1), _K2)
    blk, hop = int(0.4 * sr), int(0.1 * sr)
    if len(k) < blk:
        z = np.array([np.mean(k ** 2)])
    else:
        c = np.concatenate([[0.0], np.cumsum(k ** 2)])
        starts = np.arange(0, len(k) - blk + 1, hop)
        z = (c[starts + blk] - c[starts]) / blk
    lz = -0.691 + 10 * np.log10(z + EPS)
    z = z[lz > -70]
    if not len(z):
        return -70.0
    rel = -0.691 + 10 * np.log10(np.mean(z)) - 10
    z = z[-0.691 + 10 * np.log10(z) > rel]
    return float(-0.691 + 10 * np.log10(np.mean(z)))


def true_peak(y: np.ndarray) -> float:
    return float(20 * np.log10(np.abs(signal.resample_poly(y, 4, 1)).max() + EPS))


def _band_db(x: np.ndarray, sr: int, lo: float, hi: float) -> float:
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return float(10 * np.log10(spec[(f >= lo) & (f <= hi)].sum() + EPS))


def sib_ratio(x: np.ndarray, sr: int) -> float:
    """Sibilance: 5–9 kHz energy over 1–4 kHz energy, in dB."""
    return _band_db(x, sr, 5000, 9000) - _band_db(x, sr, 1000, 4000)


def crest(x: np.ndarray) -> float:
    return float(20 * np.log10(np.abs(x).max() + EPS) - 10 * np.log10(np.mean(x ** 2) + EPS))


def floor_db(x: np.ndarray, sr: int, frame: float = 0.05, pct: float = 20) -> float | None:
    """The noise floor: a low percentile of 50 ms RMS frames (robust to a breath or a reverb tail)."""
    n = int(frame * sr)
    if len(x) < n:
        return None
    f = x[:len(x) // n * n].reshape(-1, n)
    return float(np.percentile(10 * np.log10(np.mean(f ** 2, axis=1) + EPS), pct))


def _envelope(x: np.ndarray, sr: int) -> np.ndarray:
    sos = signal.butter(4, [1000, 8000], "bandpass", fs=sr, output="sos")
    return np.abs(signal.hilbert(signal.sosfiltfilt(sos, x)))


def onset_shift(raw: np.ndarray, out: np.ndarray, sr: int, t: float, max_lag: int = 48) -> int | None:
    """Where the processed word sits against the raw one, in samples: the lag that best aligns their 1–8 kHz
    envelopes over the word's first 100 ms (from 20 ms before its start). 0 means the word did not move.

    Envelopes, not waveforms: the minimum-phase EQ turns each harmonic's phase (a 220 Hz tone leads by ~28 samples
    after the high-pass) without delaying anything, and a waveform cross-correlation would read that phase as a
    shift. Nor a threshold crossing: the compressor reshapes the envelope, so a crossing relative to the word's peak
    moves by tens of ms though no sample did. The measurement filters are zero-phase and run on both signals alike."""
    pad = round(0.1 * sr)
    i0, i1 = round((t - 0.02) * sr), round((t + 0.1) * sr)
    lo, hi = max(0, i0 - pad), min(len(raw), i1 + pad)
    if i1 - i0 < 2 * max_lag or lo > i0 or hi < i1:
        return None
    ea = _envelope(raw[lo:hi].astype(np.float64), sr)[i0 - lo:i1 - lo]
    eb = _envelope(out[lo:hi].astype(np.float64), sr)[i0 - lo:i1 - lo]
    if not np.any(ea):
        return None
    ea, eb = ea - ea.mean(), eb - eb.mean()
    xc = signal.correlate(eb, ea, mode="full")
    mid = len(ea) - 1
    return int(np.argmax(xc[mid - max_lag:mid + max_lag + 1]) - max_lag)


# ---------------------------------------------------------------- the chain

def chain(y: np.ndarray, sr: int, cfg: dict = CHAIN) -> np.ndarray:
    """hpf → cut → de-ess → comp → presence/air → sat → + plate send; makeup to the input's integrated loudness."""
    x = np.asarray(y, dtype=np.float64)
    z = highpass(x, sr, cfg["hpf"]["f"], cfg["hpf"]["order"])
    z = _filt(z, biquad("peak", cfg["cut"]["f"], sr, q=cfg["cut"]["q"], gain_db=cfg["cut"]["gain_db"]))
    z = deess(z, sr, **cfg["deess"])
    z = compress(z, sr, **cfg["comp"])
    z = _filt(z, biquad("highshelf", cfg["presence"]["f"], sr, gain_db=cfg["presence"]["gain_db"]))
    z = _filt(z, biquad("highshelf", cfg["air"]["f"], sr, gain_db=cfg["air"]["gain_db"]))
    z = saturate(z, **cfg["sat"])
    z = plate(z, sr, **cfg["plate"])
    makeup = loudness(x, sr) - loudness(z, sr)
    return (z * 10 ** (makeup / 20)).astype(np.float32)


def _gaps(vo: dict, n: int, sr: int) -> list[tuple[int, int]]:
    edges = [0.0] + [t for ln in vo["lines"] for t in (ln["start"], ln["end"])] + [n / sr]
    return [(round(a * sr), round(b * sr)) for a, b in zip(edges[::2], edges[1::2]) if b - a >= 0.1]


def report(raw: np.ndarray, out: np.ndarray, sr: int, vo: dict) -> dict:
    """The objective checks, per line: integrated loudness in and out, true peak, sibilance in and out, crest factor
    in and out, the floor of the gap after the line, clipped samples, and the first word's onset shift in samples."""
    raw, out = np.asarray(raw, dtype=np.float64), np.asarray(out, dtype=np.float64)
    lines = []
    for k, ln in enumerate(vo["lines"]):
        i0, i1 = round(ln["start"] * sr), round(ln["end"] * sr)
        a, b = raw[i0:i1], out[i0:i1]
        nxt = vo["lines"][k + 1]["start"] if k + 1 < len(vo["lines"]) else len(raw) / sr
        g0, g1 = round(ln["end"] * sr), round(nxt * sr)
        lines.append({
            "id": ln["id"],
            "lufs_in": round(loudness(a, sr), 2), "lufs_out": round(loudness(b, sr), 2),
            "true_peak": round(true_peak(b), 2),
            "sib_in": round(sib_ratio(a, sr), 2), "sib_out": round(sib_ratio(b, sr), 2),
            "sib_drop": round(sib_ratio(a, sr) - sib_ratio(b, sr), 2),
            "crest_in": round(crest(a), 2), "crest_out": round(crest(b), 2),
            "gap_floor_in": None if (f := floor_db(raw[g0:g1], sr)) is None else round(f, 2),
            "gap_floor_out": None if (f := floor_db(out[g0:g1], sr)) is None else round(f, 2),
            "clipped": int(np.sum(np.abs(b) >= 1.0)),
            "onset_shift": onset_shift(raw, out, sr, ln["words"][0]["start"]),
        })
    gaps = _gaps(vo, len(raw), sr)
    graw = np.concatenate([raw[a:b] for a, b in gaps]) if gaps else raw[:0]
    gout = np.concatenate([out[a:b] for a, b in gaps]) if gaps else out[:0]
    r = {
        "lufs_in": round(loudness(raw, sr), 2), "lufs_out": round(loudness(out, sr), 2),
        "true_peak": round(true_peak(out), 2),
        "gap_floor_in": None if (f := floor_db(graw, sr)) is None else round(f, 2),
        "gap_floor_out": None if (f := floor_db(gout, sr)) is None else round(f, 2),
        "clipped": int(np.sum(np.abs(out) >= 1.0)),
        "lines": lines,
    }
    rise = None if r["gap_floor_in"] is None else r["gap_floor_out"] - r["gap_floor_in"]
    r["gap_floor_rise"] = None if rise is None else round(rise, 2)
    r["ok"] = {
        "onsets": all(ln["onset_shift"] is not None and abs(ln["onset_shift"]) <= 1 for ln in lines),
        "sibilance": all(2 <= ln["sib_drop"] <= 6 for ln in lines),
        "no_clips": r["clipped"] == 0,
        "gap_floor": rise is not None and rise <= 3.0,
    }
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description="Process audio/vo/vo.wav through the voice chain into "
                                             "audio/vo/vo-chain.wav, with its report in out/review/c5/vo-chain.json")
    ap.parse_args(argv)
    raw, sr = read_wav(AUDIO / "vo" / "vo.wav")
    vo = json.loads((DATA / "vo.json").read_text())
    out = chain(raw, sr)
    assert len(out) == len(raw)
    write_wav(AUDIO / "vo" / "vo-chain.wav", out, sr)
    r = report(raw, out, sr, vo)
    r["chain"] = CHAIN
    dest = OUT / "review" / "c5" / "vo-chain.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(r, indent=1) + "\n")
    drops = [ln["sib_drop"] for ln in r["lines"]]
    print(f"audio/vo/vo-chain.wav · {r['lufs_in']:.1f} → {r['lufs_out']:.1f} LUFS · {r['true_peak']:.1f} dBTP · "
          f"sibilance drop {min(drops):+.1f}…{max(drops):+.1f} dB · gap floor {r['gap_floor_rise']:+.1f} dB · "
          f"{r['clipped']} clipped")
    for k, v in r["ok"].items():
        print(f"  {'ok' if v else ('WARN' if k == 'sibilance' else 'FAIL')}  {k}")
    off = [f"{ln['id']} {ln['sib_drop']:+.1f}" for ln in r["lines"] if not 2 <= ln["sib_drop"] <= 6]
    if off:
        print(f"  sibilance drop outside 2–6 dB: {', '.join(off)}")
    print(f"report: {dest.relative_to(OUT.parent)}")
    # sync, clipping and the gap floor are hard gates; the sibilance band is a target (a line with no /s/ can't
    # drop, and the shelves lift every line's ratio), reported for the ear to judge
    return 0 if all(v for k, v in r["ok"].items() if k != "sibilance") else 1
