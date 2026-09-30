"""Beat grid, sections, envelopes and onsets for the engine (data/audio.json).

The score is generated at one tempo, so the grid is a straight line fitted to librosa's tracked beats. It carries
on through drumless stretches (the cold open, the honesty drop-out) where a tracker loses the beat. `grid_fit`
measures the grid against the audio's own onsets. Below 0.9 the tempo drifts, and a human decides (regenerate the
score, or cut on its downbeats); the music is the truth (spec §5.2). The envelopes and band onsets are taken from
the music as the mix plays it, with its automation drawn in.
"""
import argparse
import json

import librosa
import numpy as np

from .automate import apply, lanes
from .paths import AUDIO, DATA, ROOT
from .wav import read_wav

FPS = 100
HOP = 256
# The onset envelope peaks after the attack it sees: 0.7 to 1.4 frames on clicks, kicks and ticks at 22-48 kHz, and
# a little more once the tracker has stepped it onto whole frames. Beats and onsets are read off it, so both are
# shifted back by this much (frames, so it scales with the sample rate).
LAG = 1.5
# A fitted phase within this much of a whole period is a first beat just before 0 (at most 30 ms), not a late one.
WRAP = 0.03


def fit_grid(beats: np.ndarray, duration: float) -> tuple[np.ndarray, float, float]:
    period = float(np.median(np.diff(beats)))
    ang = 2 * np.pi * (beats % period) / period
    phase = float((np.angle(np.mean(np.exp(1j * ang))) % (2 * np.pi)) / (2 * np.pi) * period)
    idx = np.round((beats - phase) / period)
    near = np.abs(beats - (phase + idx * period)) < 0.2 * period
    # The line is the median of the pairwise slopes, not a least-squares fit: the tracker leaves stray beats at the
    # ends and a drifting run through a fade-out, and one of those tilts a least-squares line by a tenth of a percent.
    x, b = idx[near], beats[near]
    i, j = np.triu_indices(len(x), 1)
    span = x[j] - x[i]
    period = float(np.median((b[j] - b[i])[span != 0] / span[span != 0]))
    phase = float(np.median(b - period * x)) % period
    resid = beats - (phase + np.round((beats - phase) / period) * period)
    grid = np.arange(phase, duration, period)
    if phase > period - WRAP:  # a first beat a hair before 0 wrapped round to the end of the period: keep it
        grid = np.concatenate([[phase - period], grid])
    return grid, period, float(np.median(np.abs(resid)))


def _norm(x: np.ndarray) -> np.ndarray:
    """0..1, with the loudest 1% clipping at 1 (half the peak, for sparse signals like a voice)."""
    if not len(x) or float(x.max()) <= 0:
        return np.zeros_like(x)
    return np.clip(x / max(float(np.percentile(x, 99)), 0.5 * float(x.max())), 0.0, 1.0)


def grid_fit(grid: np.ndarray, onset_times: np.ndarray, active: np.ndarray) -> float:
    beats = grid[active]
    if not len(beats) or not len(onset_times):
        return 0.0
    i = np.searchsorted(onset_times, beats)
    lo = onset_times[np.clip(i - 1, 0, len(onset_times) - 1)]
    hi = onset_times[np.clip(i, 0, len(onset_times) - 1)]
    return float(np.mean(np.minimum(np.abs(beats - lo), np.abs(beats - hi)) < 0.03))


def _fit(x: np.ndarray, n: int) -> np.ndarray:
    return np.pad(x, (0, max(0, n - len(x))))[:n]


def _band(S: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    band = S[(freqs >= lo) & (freqs < hi)]
    return np.sqrt(np.mean(band ** 2, axis=0)) if len(band) else np.zeros(S.shape[1])


def _onsets(env: np.ndarray) -> list[list[float]]:
    flux = np.maximum(0.0, np.diff(env, prepend=env[0]))
    if flux.max() <= 0:
        return []
    flux = flux / flux.max()
    peaks = librosa.util.peak_pick(flux, pre_max=3, post_max=3, pre_avg=10, post_avg=10, delta=0.07, wait=10)
    return [[round(p / FPS, 3), round(float(flux[p]), 3)] for p in peaks]


def _downbeat_phase(beats: np.ndarray, low: np.ndarray, starts: list[float], period: float) -> int:
    at = low[np.clip(np.round(beats * FPS).astype(int), 0, len(low) - 1)]
    best, best_score = 0, -np.inf
    for p in range(4):
        db = beats[p::4]
        dist = np.mean([np.min(np.abs(db - s)) for s in starts]) / period if starts and len(db) else 0.0
        score = at[p::4].mean() - at.mean() - 0.5 * dist
        if score > best_score:
            best, best_score = p, score
    return best


def _envelopes(y: np.ndarray, sr: int, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """low, mid and high band envelopes and the RMS, at FPS, each 0..1."""
    hop = max(1, sr // FPS)
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    low, mid, high = (_norm(_fit(_band(S, freqs, lo, hi), n)) for lo, hi in ((20, 150), (150, 2000), (4000, 16000)))
    return low, mid, high, _norm(_fit(librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0], n))


def analyze(y: np.ndarray, sr: int, meta: dict, vo: dict | None = None, vo_y: np.ndarray | None = None,
            automate: bool = True) -> dict:
    """The beat grid, downbeats and sections come from the score as generated. The envelopes and band onsets that
    drive the visuals come from the music as heard: with `automate`, the mix's arc (automate.py) is drawn over
    those sections first, so the honest dip and the muffled cold open show in them as they do in the mix."""
    duration = len(y) / sr
    n = int(np.ceil(duration * FPS))
    lag = LAG * HOP / sr  # onset times are read off the envelope, so every one of them is this late
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    _, bf = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, hop_length=HOP, start_bpm=meta["bpm"],
                                    tightness=400, trim=False)
    tracked = librosa.frames_to_time(bf, sr=sr, hop_length=HOP) - lag
    beats, period, err = fit_grid(tracked, duration)
    low, _, _, rms = _envelopes(y, sr, n)
    onset_t = librosa.onset.onset_detect(onset_envelope=oenv, sr=sr, hop_length=HOP, units="time",
                                         backtrack=False) - lag
    # an audible stretch: sound within a beat of the beat. Loudness at the instant would keep only the beats that
    # land on a hit, and hits are shorter than the gaps between them, so a drifting grid would still score well.
    sounding = np.convolve((rms > 0.05).astype(float), np.ones(2 * round(period * FPS) + 1), mode="same") > 0
    active = sounding[np.clip(np.round(beats * FPS).astype(int), 0, n - 1)]
    fit = grid_fit(beats, onset_t, active)
    starts = [s["start"] for s in meta["sections"]]
    downs = beats[_downbeat_phase(beats, low, starts, period)::4]
    snapped = [float(downs[np.argmin(np.abs(downs - s))]) if i else 0.0 for i, s in enumerate(starts)]
    sections = [{"name": s["name"], "start": round(snapped[i], 3),
                 "end": round(snapped[i + 1], 3) if i + 1 < len(snapped) else round(duration, 3)}
                for i, s in enumerate(meta["sections"])]
    if automate:  # from here on, the music as heard
        y = apply(y, sr, *lanes(sections, sr, len(y)))
        oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    low, mid, high, rms = _envelopes(y, sr, n)
    t = np.arange(n) / FPS
    drums = _norm(np.interp(t, librosa.frames_to_time(np.arange(len(oenv)), sr=sr, hop_length=HOP) - lag, oenv))
    vocal = np.zeros(n)
    if vo_y is not None:
        vr = max(1, sr // FPS) if len(vo_y) else 1
        vocal = _norm(_fit(librosa.feature.rms(y=vo_y, frame_length=2048, hop_length=vr)[0], n))
    vocal_on = [[w["start"], 1.0] for l in (vo or {}).get("lines", []) for w in l["words"]]
    r3 = lambda a: [round(float(v), 3) for v in a]  # noqa: E731
    return {
        "duration": round(duration, 3), "bpm": round(60.0 / period, 3), "beat_period": round(period, 5),
        "time_signature": 4, "beats": r3(beats), "downbeats": r3(downs), "sections": sections, "fps": FPS,
        "rms": r3(rms), "low": r3(low), "mid": r3(mid), "high": r3(high), "vocal": r3(vocal), "drums": r3(drums),
        "bass": r3(low), "other": r3(mid),
        "onsets": {"kick": _onsets(low), "snare": _onsets(mid), "hat": _onsets(high), "vocal": vocal_on},
        "grid_error_ms": round(err * 1000, 1), "grid_fit": round(fit, 3),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Analyse the chosen score into data/audio.json")
    ap.add_argument("--music", help="WAV to analyse (default: the chosen variant in data/music_plan.json)")
    ap.add_argument("--no-automation", action="store_true",
                    help="take the envelopes from the score as generated (to go with film-mix --no-automation)")
    a = ap.parse_args(argv)
    mp = json.loads((DATA / "music_plan.json").read_text())
    path = ROOT / (a.music or mp["chosen"] or "")
    if not path.is_file():
        raise SystemExit("no chosen score: set 'chosen' in data/music_plan.json (checkpoint C2)")
    y, sr = read_wav(path)
    vo = json.loads((DATA / "vo.json").read_text())
    vo_y, vsr = read_wav(AUDIO / "vo" / "vo.wav")
    if vsr != sr:
        vo_y = librosa.resample(vo_y, orig_sr=vsr, target_sr=sr)
    meta = mp.get("chosen_meta") or mp["meta"]  # the pick's own section timing; `meta` is the latest film-music run's
    out = analyze(y, sr, meta, vo, vo_y, automate=not a.no_automation)
    (DATA / "audio.json").write_text(json.dumps(out))
    print(f"{out['bpm']} BPM · grid fit {out['grid_fit']:.2f} · grid error {out['grid_error_ms']} ms · "
          f"{len(out['beats'])} beats · {len(out['downbeats'])} downbeats"
          + ("" if out["grid_fit"] >= 0.9 else "   ⚠ the tempo drifts: ask the user (regenerate, or cut on downbeats)"))
    for s in out["sections"]:
        print(f"  {s['name']:<22} {s['start']:7.3f} → {s['end']:7.3f}")
