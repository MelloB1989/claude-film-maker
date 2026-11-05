"""Sounds synthesised from scratch for the anime mix (film-anime-mix cues named `synth:<kind>`), each a pure function
of its arguments: the same call always gives the same samples. 48 kHz mono float32, peaking near −1 dBFS.

    taiko     a big drum: a pitched membrane that drops onto its note, a second mode, the stick's crack, a short room
              (f0 62 Hz, decay 1.6 s, crack 1)
    ring      the high ring of a held breath, two pure tones beating against each other (f 2900 Hz, dur 4.5 s)
    subdrop   a sine falling through the floor under an impact (f0 70 Hz to f1 28 Hz, dur 2.2 s)
    riser     noise and a tone rising into a hit, ending exactly at its length (dur 2 s)
    swell     a reversed cymbal-like breath swelling into a cut (dur 1.2 s)
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000


def _norm(y: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    m = float(np.abs(y).max()) or 1.0
    return (y / m * 10 ** (peak_db / 20)).astype(np.float32)


def _fade(y: np.ndarray, a: float = 0.002, b: float = 0.02) -> np.ndarray:
    na, nb = int(a * SR), int(b * SR)
    if na:
        y[:na] *= np.linspace(0, 1, na)
    if nb:
        y[-nb:] *= np.linspace(1, 0, nb)
    return y


def taiko(f0: float = 62.0, decay: float = 1.6, crack: float = 1.0, seed: int = 1) -> np.ndarray:
    n = int((decay * 2.2 + 0.2) * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    # the membrane starts high and drops onto its note within ~50 ms (the skin's tension after the strike)
    f = f0 * (1 + 0.9 * np.exp(-t / 0.035))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (decay * 0.45))
    second = 0.35 * np.sin(2 * np.pi * np.cumsum(f * 1.59) / SR) * np.exp(-t / (decay * 0.18))
    third = 0.15 * np.sin(2 * np.pi * np.cumsum(f * 2.13) / SR) * np.exp(-t / (decay * 0.09))
    stick = rng.standard_normal(n) * np.exp(-t / 0.012)
    stick = sosfilt(butter(2, [180, 2600], "bandpass", fs=SR, output="sos"), stick) * 0.9 * crack
    y = body + second + third + stick
    # a short wooden room
    ir = np.zeros(int(0.25 * SR))
    for dt, g in [(0.013, 0.3), (0.029, 0.22), (0.047, 0.16), (0.071, 0.11), (0.103, 0.07), (0.151, 0.04)]:
        ir[int(dt * SR)] = g
    ir[0] = 1.0
    y = np.convolve(y, ir)[:n]
    return _norm(_fade(y, 0.0005, 0.05))


def ring(f: float = 2900.0, dur: float = 4.5, beat: float = 5.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.minimum(1, t / 0.35) * np.exp(-np.maximum(0, t - 0.35) / (dur * 0.6))
    y = (np.sin(2 * np.pi * f * t) + 0.7 * np.sin(2 * np.pi * (f + beat) * t) + 0.15 * np.sin(2 * np.pi * f * 2.01 * t)) * env
    return _norm(_fade(y, 0.01, 0.4), -6.0)


def subdrop(f0: float = 70.0, f1: float = 28.0, dur: float = 2.2) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / (dur * 0.25))
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (dur * 0.45))
    y = np.tanh(1.4 * y)
    return _norm(_fade(y, 0.001, 0.2))


def riser(dur: float = 2.0, seed: int = 2) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    k = (t / dur) ** 2
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    blk = 1024
    for i in range(0, n, blk):
        fc = 300 + 7000 * k[min(i, n - 1)]
        sos = butter(2, [max(60, fc * 0.6), min(SR / 2 - 100, fc * 1.4)], "bandpass", fs=SR, output="sos")
        out[i:i + blk] = sosfilt(sos, noise[i:i + blk])
    tone = np.sin(2 * np.pi * np.cumsum(90 + 600 * k) / SR) * 0.25
    y = (out + tone) * (0.05 + 0.95 * k)
    return _norm(_fade(y, 0.05, 0.004))


def swell(dur: float = 1.2, seed: int = 3) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    y = sosfilt(butter(2, [2500, 12000], "bandpass", fs=SR, output="sos"), rng.standard_normal(n))
    y *= np.exp((t - dur) / (dur * 0.28))
    return _norm(_fade(y, 0.01, 0.003), -3.0)


KINDS = {"taiko": taiko, "ring": ring, "subdrop": subdrop, "riser": riser, "swell": swell}


def make(kind: str, **args) -> np.ndarray:
    if kind not in KINDS:
        raise SystemExit(f"no synth sound {kind!r} (have {', '.join(KINDS)})")
    return KINDS[kind](**args)
