"""Synthesized SFX for the v3 transitions (numpy/scipy only, deterministic per seed).

Every generator returns `(y, hit)`: `y` a (n, 2) float64 stereo signal at 48 kHz normalised to a -1 dBFS sample peak
(like the v2 kit, so cue gains read the same), `hit` the sample of `y` that lands on the cue frame (the peak of a
swell, the attack of an impact). Durations are in seconds. `pan` is -1 (left) .. +1 (right), equal-power.

Building blocks: `band_noise` (white noise shaped by a time-varying log-frequency band in the STFT domain: whooshes,
winds, risers), `env_*` amplitude envelopes, `grains` (sparse impulsive events: crackle, debris, glass), `modes`
(decaying inharmonic partials: glass, metal), `room` (a short synthetic stereo reverb to glue the layers).
Python 3.10 compatible (the render VM).
"""
from __future__ import annotations

import zlib

import numpy as np
import scipy.signal as sg

SR = 48000
PEAK = 10 ** (-1 / 20)


# ---------------------------------------------------------------- helpers

def _t(dur: float) -> np.ndarray:
    return np.arange(int(round(dur * SR))) / SR


def norm(y: np.ndarray, peak: float = PEAK) -> np.ndarray:
    m = np.abs(y).max()
    return y * (peak / m) if m > 0 else y


def stereo(m: np.ndarray, pan=0.0) -> np.ndarray:
    """Mono (n,) -> (n, 2), equal-power pan (a scalar or a per-sample array in -1..1)."""
    p = (np.clip(pan, -1, 1) + 1) * np.pi / 4
    return np.stack([m * np.cos(p), m * np.sin(p)], axis=1)


def fade(y: np.ndarray, a: float = 0.002, b: float = 0.010) -> np.ndarray:
    """Raised-cosine fade in/out so no layer starts or stops with a step."""
    y = y.copy()
    na, nb = max(1, int(a * SR)), max(1, int(b * SR))
    ra = 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / na)
    rb = 0.5 + 0.5 * np.cos(np.pi * np.arange(nb) / nb)
    y[:na] *= ra[:, None] if y.ndim == 2 else ra
    y[-nb:] *= rb[:, None] if y.ndim == 2 else rb
    return y


def mix_at(n: int, parts) -> np.ndarray:
    """Sum (start_sample, (m, 2) signal, gain) parts into an (n, 2) buffer."""
    out = np.zeros((n, 2))
    for s, y, g in parts:
        a, b = max(0, s), min(n, s + len(y))
        if b > a:
            out[a:b] += y[a - s:b - s] * g
    return out


def interp_curve(t: np.ndarray, pts) -> np.ndarray:
    """Piecewise curve through [(time, value), ...] (values interpolated in log for > 0 sequences)."""
    tt, vv = zip(*pts)
    vv = np.array(vv, float)
    if (vv > 0).all():
        return np.exp(np.interp(t, tt, np.log(vv)))
    return np.interp(t, tt, vv)


def env_swell(n_pre: int, n_post: int, rise_db: float = 36.0, tail_tau: float = 0.06, curve: float = 1.0) -> np.ndarray:
    """Exponential rise of `rise_db` over n_pre samples to 1.0 at sample n_pre (the peak), then an exponential decay.
    `curve` > 1 holds the start lower and leans the rise towards the peak (a reverse-cymbal shape)."""
    x = np.linspace(0, 1, n_pre, endpoint=False) ** curve
    up = 10 ** (rise_db * (x - 1) / 20)
    down = np.exp(-np.arange(n_post) / (tail_tau * SR))
    return np.concatenate([up, down])


def env_hit(n: int, attack: float = 0.002, tau: float = 0.1) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-np.maximum(t - attack, 0) / tau)


def smooth_rand(n: int, rate_hz: float, rng, lo=0.0, hi=1.0) -> np.ndarray:
    """A smooth random curve (cubic through random points every 1/rate s) in [lo, hi]."""
    k = max(4, int(n / SR * rate_hz) + 4)
    pts = rng.uniform(lo, hi, k)
    x = np.linspace(1, k - 2, n)
    i = np.clip(x.astype(int), 1, k - 3)
    u = x - i
    p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]          # Catmull-Rom
    y = 0.5 * (2 * p1 + (p2 - p0) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u ** 2 + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3)
    return np.clip(y, lo, hi)


def band_noise(n: int, center, bw_oct, rng, tilt_db_oct: float = 0.0, chans: int = 2, nper: int = 1024) -> np.ndarray:
    """White noise shaped by a Gaussian band in log2 frequency whose centre (Hz) and width (octaves, = 2 sigma) follow
    per-sample arrays (or scalars). Returns (n, chans), channels independent (decorrelated stereo), unit-ish RMS."""
    hop = nper // 4
    center = np.broadcast_to(np.asarray(center, float), (n,))
    bw_oct = np.broadcast_to(np.asarray(bw_oct, float), (n,))
    out = np.zeros((n, chans))
    for c in range(chans):
        x = rng.standard_normal(n)
        f, tt, Z = sg.stft(x, SR, nperseg=nper, noverlap=nper - hop, boundary="zeros", padded=True)
        idx = np.clip((tt * SR).astype(int), 0, n - 1)
        lf = np.log2(np.maximum(f, 10.0))[:, None]
        lc = np.log2(center[idx])[None, :]
        sig = (bw_oct[idx] / 2)[None, :]
        g = np.exp(-0.5 * ((lf - lc) / sig) ** 2) * 2 ** (tilt_db_oct / 6.02 * (lf - lc))
        _, y = sg.istft(Z * g, SR, nperseg=nper, noverlap=nper - hop, boundary=True)
        y = y[:n] if len(y) >= n else np.pad(y, (0, n - len(y)))
        out[:, c] = y
    r = np.sqrt((out ** 2).mean()) + 1e-12
    return out / r


def hp(y, f, order=2):
    return sg.sosfilt(sg.butter(order, f, "high", fs=SR, output="sos"), y, axis=0)


def lp(y, f, order=2):
    return sg.sosfilt(sg.butter(order, f, "low", fs=SR, output="sos"), y, axis=0)


def bp(y, lo, hi, order=2):
    return sg.sosfilt(sg.butter(order, [lo, hi], "band", fs=SR, output="sos"), y, axis=0)


def chirp_sine(freq: np.ndarray, phase0: float = 0.0) -> np.ndarray:
    return np.sin(phase0 + 2 * np.pi * np.cumsum(freq) / SR)


def modes(n: int, f0: float, ratios, decays, amps, rng, detune: float = 0.0) -> np.ndarray:
    """Sum of decaying sinusoids (a struck object). Mono (n,)."""
    t = np.arange(n) / SR
    y = np.zeros(n)
    for r, d, a in zip(ratios, decays, amps):
        f = f0 * r * (1 + rng.uniform(-detune, detune))
        y += a * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)) * np.exp(-t / d)
    return y


def grains(n: int, times, make, rng, pans=None) -> np.ndarray:
    """Place `make(i, rng) -> mono grain` at each time (s); random pan unless given. (n, 2)."""
    out = np.zeros((n, 2))
    for i, tg in enumerate(times):
        g = make(i, rng)
        s = int(tg * SR)
        if s >= n or s < 0:
            continue
        e = min(n, s + len(g))
        p = rng.uniform(-0.9, 0.9) if pans is None else pans[i]
        out[s:e] += stereo(g[:e - s], p)
    return out


def room(y: np.ndarray, rng, dur: float = 0.9, wet: float = 0.25, damp_hz: float = 5000) -> np.ndarray:
    """Short synthetic stereo reverb: convolution with exponentially decaying decorrelated noise (darkening)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal((n, 2)) * np.exp(-t * 6.9 / dur)[:, None]
    ir = lp(ir, damp_hz)
    ir[: int(0.008 * SR)] = 0                                  # pre-delay
    ir /= np.sqrt((ir ** 2).sum(axis=0))
    w = np.stack([sg.fftconvolve(y[:, c], ir[:, c]) for c in range(2)], axis=1)
    w = np.pad(w, ((0, len(y) + n - len(w)), (0, 0)))
    dry = np.pad(y, ((0, n), (0, 0)))
    return dry * (1 - wet) + w * wet * 3.0


def _rng(seed) -> np.random.Generator:
    """A generator from an int or a string seed (crc32: stable across processes, unlike hash())."""
    return np.random.default_rng(seed if isinstance(seed, int) else zlib.crc32(str(seed).encode()))


# ---------------------------------------------------------------- whooshes

def swell(pre: float, post: float = 0.18, f_from: float = 600, f_to: float = 4500, seed=0, pan_from=0.0, pan_to=0.0,
          rise_db: float = 34, curve: float = 1.6, air: float = 0.5, flutter_hz: float = 0.0):
    """Reverse-swell whoosh: rises over `pre` s (band centre gliding f_from -> f_to, rising pitch for a push, falling
    for a pull) and peaks on the hit, then a quick decay over `post`. A second, airier band follows an octave up."""
    rng = _rng(seed)
    n0, n1 = int(pre * SR), int(post * SR)
    n = n0 + n1
    t = np.arange(n) / SR
    c = interp_curve(t, [(0, f_from), (pre, f_to), (pre + post, f_to * (0.8 if f_to > f_from else 0.9))])
    bw = interp_curve(t, [(0, 0.9), (pre, 1.8), (pre + post, 2.2)])
    body = band_noise(n, c, bw, rng)
    airy = band_noise(n, np.minimum(c * 2.2, 14000), 1.4, rng)
    e = env_swell(n0, n1, rise_db, tail_tau=post / 3.5, curve=curve)
    y = (body + air * airy) * e[:, None]
    if flutter_hz:
        fl = flutter_hz * interp_curve(t, [(0, 0.5), (pre, 1.0), (pre + post, 0.8)])
        y *= (0.65 + 0.35 * np.sin(2 * np.pi * np.cumsum(fl) / SR))[:, None]
    if pan_from or pan_to:
        p = np.interp(t, [0, pre, pre + post], [pan_from, (pan_from + pan_to) / 2 + 0.5 * (pan_to - pan_from) * 0.6, pan_to])
        m = y.mean(axis=1)
        side = (y[:, 0] - y[:, 1]) * 0.5
        y = stereo(m, p) + np.stack([side, -side], axis=1) * 0.5
    return norm(fade(y)), n0


def swish(dur: float = 0.24, peak: float = 0.13, direction: str = "R", seed=0):
    """Fast whip swish: band sweeps up into the peak and back down, panned across in the whip direction (L/R), or
    pitched up (U) / down (D) with a wide centre."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    up = {"U": 1.5, "D": 0.7}.get(direction, 1.0)
    c = interp_curve(t, [(0, 700), (peak, 3200 * up), (dur, 1300 * up)])
    y = band_noise(n, c, interp_curve(t, [(0, 1.0), (peak, 2.2), (dur, 1.4)]), rng)
    e = np.where(t < peak, (t / peak) ** 3, np.exp(-(t - peak) / 0.035))
    y *= e[:, None]
    if direction in "LR":
        s = 1 if direction == "R" else -1
        p = s * np.tanh((t - peak) / 0.05) * 0.85
        y = stereo(y.mean(axis=1) * 1.2, p) + 0.3 * y
    return norm(fade(y)), int(peak * SR)


def whoosh_by(pre: float, post: float, seed=0, pan_dir: int = 1, low: float = 1.0):
    """Heavy pass-by: a big body whoosh whose band drops through the pass point (doppler), amplitude bell around it,
    panned across the stereo field (pan_dir +1 = left to right), with a sub rumble under it."""
    rng = _rng(seed)
    n0, n1 = int(pre * SR), int(post * SR)
    n = n0 + n1
    t = np.arange(n) / SR - pre
    d = 0.06
    vr = t / np.sqrt(t ** 2 + d ** 2)                                     # radial velocity, -1 -> +1 through the pass
    ratio = 1 / (1 + 0.28 * vr)                                         # approaching sharp, receding flat
    c = 900 * ratio ** 2.2
    y = band_noise(n, c, 2.4, rng) + 0.8 * band_noise(n, c * 4.5, 1.6, rng)
    amp = 1 / np.sqrt(t ** 2 + d ** 2) * d
    amp = amp ** 0.8 * np.where(t < 0, 1, np.exp(-t / (post * 0.5)))
    rumble = lp(rng.standard_normal(n), 90, 4) * 2.5 * low
    m = y.mean(axis=1) * amp + rumble * amp
    p = pan_dir * np.tanh(t / 0.07) * 0.9
    out = norm(fade(stereo(m, p) + 0.25 * y * amp[:, None], 0.01, 0.03))
    e = np.convolve(np.abs(out).max(axis=1) ** 2, np.ones(480) / 480, "same")
    return out, int(np.argmax(e))                                      # the hit is the loudest moment of the pass


def riser(dur: float, seed=0, f_from: float = 250, f_to: float = 7000, tone: float = 0.35):
    """Build-up riser into a hit: noise band and a detuned saw-ish tone pair rising ~2 octaves, exponential swell, a
    hard (2 ms) stop on the hit so the impact takes over."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = t / dur
    c = f_from * (f_to / f_from) ** (x ** 1.4)
    y = band_noise(n, c, 1.3 + x, rng)
    f = 110 * 2 ** (2.2 * x ** 1.6)
    ton = sum(np.tanh(2.5 * chirp_sine(f * k * (1 + dt))) / k for k, dt in ((1, 0), (1, 0.006), (2, -0.004), (3, 0.003)))
    ton = hp(ton, 200)
    y = y + tone * np.stack([ton, np.roll(ton, 37)], axis=1)
    e = 10 ** (30 * (x ** 1.8 - 1) / 20)
    y *= e[:, None]
    y[-int(0.002 * SR):] *= np.linspace(1, 0, int(0.002 * SR))[:, None]
    return norm(fade(y, 0.05, 0.002)), n


def shockwave(dur: float = 0.7, seed=0):
    """A whoosh that starts at full on the hit and falls in pitch and level as the wave passes the camera."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    c = interp_curve(t, [(0, 5000), (0.08, 2500), (dur, 180)])
    y = band_noise(n, c, 2.6, rng)
    e = np.minimum(1, t / 0.012) * np.exp(-t / (dur * 0.3))
    p = np.sin(2 * np.pi * 1.1 * t) * 0.6
    return norm(fade(stereo(y.mean(axis=1), p) * e[:, None] + y * e[:, None] * 0.4, 0.001, 0.05)), 0


def air_tail(dur: float = 0.6, seed=0, f: float = 6500):
    """A soft wide airy decay after the hit (the landing breath)."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = band_noise(n, interp_curve(t, [(0, f), (dur, f * 0.55)]), 2.0, rng)
    y *= (np.minimum(1, t / 0.02) * np.exp(-t / (dur / 3.2)))[:, None]
    return norm(fade(y, 0.002, 0.05)), 0


# ---------------------------------------------------------------- impacts

def thump(seed=0, f0: float = 95, f1: float = 40, dur: float = 0.5, click: float = 0.35):
    """Sub thump: a sine falling f0 -> f1 with a short noise click on top. Centre."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.045)
    y = np.tanh(1.6 * chirp_sine(f)) * np.exp(-t / (dur * 0.28)) * np.minimum(1, t / 0.0015)
    ck = lp(rng.standard_normal(n), 3500) * np.exp(-t / 0.006) * click * 3
    return norm(fade(stereo(y + ck), 0.0005, 0.03)), 0


def debris(dur: float = 1.2, seed=0, count: int = 90, tau: float = 0.25, bright: float = 1.0):
    """Falling debris: many short band-limited clicks and small knocks, dense at the hit and thinning out."""
    rng = _rng(seed)
    n = int(dur * SR)
    times = np.sort(np.minimum(rng.exponential(tau, count) + rng.uniform(0, 0.02, count), dur - 0.05))

    def mk(i, r):
        m = int(r.uniform(0.003, 0.03) * SR)
        lo = r.uniform(400, 2500) * bright
        g = bp(r.standard_normal(m), lo, min(lo * r.uniform(2, 4), 16000)) * np.exp(-np.arange(m) / (m / 4))
        return g * r.uniform(0.2, 1.0) * np.exp(-times[i] / (tau * 2))

    y = grains(n, times, mk, rng)
    return norm(fade(y, 0.0005, 0.05)), 0


def impact(seed=0, dur: float = 1.4, deep: float = 1.0, crunch: float = 0.6, debris_amt: float = 0.5):
    """Deep impact: a low sub boom + a mid crunch + debris, through a short room."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    boom, _ = thump(seed=f"{seed}b", f0=70 * deep + 20, f1=30, dur=dur, click=0.6)
    cr = bp(rng.standard_normal(n), 180, 2600, 2) * np.exp(-t / 0.09) * np.minimum(1, t / 0.001)
    cr = np.tanh(3 * cr / (np.abs(cr).max() + 1e-9))
    db_, _ = debris(dur, seed=f"{seed}d", count=70, tau=0.18)
    y = boom * 1.0 + stereo(cr) * crunch * 0.5 + db_ * debris_amt * 0.35
    return norm(room(y, rng, 0.8, 0.2)[:n]), 0


def slap(seed=0, bright: float = 1.0, body_hz: float = 150):
    """Soft paper/panel slap: a broadband flap with a small low body, a little room."""
    rng = _rng(seed)
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    fl = bp(rng.standard_normal(n), 500 * bright, 5500 * bright) * np.exp(-t / 0.022) * np.minimum(1, t / 0.0008)
    body = np.sin(2 * np.pi * body_hz * t) * np.exp(-t / 0.05)
    y = stereo(fl + 0.6 * body)
    return norm(room(y, rng, 0.5, 0.18)[:n]), 0


def metal_slam(seed=0, f0: float = 170):
    """Metallic slam: an impact plus inharmonic plate modes ringing out (with beating pairs) and a bright clang."""
    rng = _rng(seed)
    dur = 1.8
    n = int(dur * SR)
    t = np.arange(n) / SR
    im, _ = impact(seed=f"{seed}i", dur=dur, deep=0.9, crunch=0.4, debris_amt=0.2)
    ratios = [1, 1.004, 1.59, 2.14, 2.31, 2.65, 2.92, 3.56, 4.25, 5.4, 6.63]
    dec = [1.1, 1.0, 0.8, 0.6, 0.55, 0.45, 0.4, 0.3, 0.25, 0.18, 0.12]
    amp = [1, 0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2]
    ml = modes(n, f0, ratios, dec, amp, rng, 0.003)
    mr = modes(n, f0, ratios, dec, amp, rng, 0.003)
    clang = modes(n, 2300, [1, 1.37, 1.81, 2.6], [0.12, 0.09, 0.07, 0.05], [1, 0.7, 0.5, 0.3], rng)
    mt = np.stack([ml, mr], axis=1) + 0.5 * stereo(clang)
    mt *= np.minimum(1, t / 0.001)[:, None]
    y = im + 0.5 * norm(mt)
    return norm(room(y, rng, 1.2, 0.22)[:n]), 0


# ---------------------------------------------------------------- glass, electricity, sparks

def _glass_grain(f_lo: float, f_hi: float, d_lo: float, d_hi: float):
    def mk(i, r):
        d = r.uniform(d_lo, d_hi)
        m = int(d * 5 * SR)
        tt = np.arange(m) / SR
        f = r.uniform(f_lo, f_hi)
        g = modes(m, f, [1, 2.76, 5.40, 8.93], [d, d * 0.6, d * 0.4, d * 0.25], [1, 0.6, 0.35, 0.2], r, 0.01)
        tick = r.standard_normal(m) * np.exp(-tt / 0.0007)
        return (g + 0.6 * hp(tick, 2000)) * r.uniform(0.3, 1.0)
    return mk


def glass(dur: float = 1.6, seed=0, count: int = 260, tau: float = 0.12, crack: float = 1.0, f_lo: float = 1800,
          f_hi: float = 9000):
    """Glass shatter: a broadband crack, then hundreds of ringing glass grains (inharmonic partials, 2-9 kHz), dense on
    the hit and thinning out, spread across the stereo field."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    times = np.minimum(rng.exponential(tau, count), dur - 0.1)
    times[: count // 4] = rng.uniform(0, 0.03, count // 4)       # the burst itself
    times = np.sort(times)
    mk = _glass_grain(f_lo, f_hi, 0.008, 0.06)
    y = grains(n, times, lambda i, r: mk(i, r) * np.exp(-times[i] / (tau * 3)), rng)
    ck = hp(rng.standard_normal(n), 900) * np.exp(-t / 0.018) * np.minimum(1, t / 0.0005)
    y = norm(y) + crack * 0.8 * stereo(ck)
    return norm(room(y, rng, 0.7, 0.2)[:n]), 0


def tinkle(dur: float = 1.8, seed=0, count: int = 40):
    """Sparse falling glass bits after the shatter."""
    rng = _rng(seed)
    n = int(dur * SR)
    times = np.sort(rng.uniform(0, dur - 0.15, count) ** 1.3 * (dur - 0.15) ** -0.3)
    mk = _glass_grain(2500, 8500, 0.02, 0.09)
    y = grains(n, times, lambda i, r: mk(i, r) * (1 - times[i] / dur) ** 1.5, rng)
    return norm(room(y, rng, 0.9, 0.3)[:n]), 0


def crackle(dur: float, seed=0, rate=(60, 260), buzz: float = 0.5, hz: float = 120, swell_to: float = 1.0):
    """Electric crackle: a Poisson train of sharp sparks (rate rising rate[0] -> rate[1] per s) through resonances,
    plus gated mains buzz bursts (arcs). Level grows to `swell_to` at the end (1 = flat)."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    lam = np.interp(t, [0, dur], rate) / SR
    imp = (rng.random(n) < lam) * rng.pareto(2.0, n)
    imp = np.minimum(imp, 8)
    sp = np.zeros((n, 2))
    for c in range(2):
        x = imp * rng.choice([-1, 1], n)
        x = 0.6 * bp(x, 2500, 9000) + 0.4 * bp(x, 900, 2200)
        sp[:, c] = x
    gate = (smooth_rand(n, 18, rng) > 0.62).astype(float)
    gate = np.convolve(gate, np.hanning(int(0.004 * SR)) / (0.002 * SR), "same")
    saw = sum(np.sin(2 * np.pi * hz * k * t + rng.uniform(0, 6)) / k for k in range(1, 12))
    arc = np.tanh(3 * saw) * gate * (0.6 + 0.4 * rng.standard_normal(n).clip(-2, 2) / 2)
    arc = bp(arc, 90, 6000)
    lvl = np.interp(t, [0, dur], [1.0, swell_to])
    y = (norm(sp) + buzz * norm(stereo(arc, smooth_rand(n, 4, rng, -0.6, 0.6)))) * lvl[:, None]
    return norm(fade(y, 0.02, 0.05)), 0


def thunder(seed=0, dur: float = 2.2):
    """Thunder crack: an immediate sharp broadband crack + a crackling rip over 0.25 s + a long rolling low rumble."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    crack = hp(rng.standard_normal(n), 250) * np.exp(-t / 0.035) * np.minimum(1, t / 0.0004)
    rip, _ = crackle(0.35, seed=f"{seed}r", rate=(900, 200), buzz=0.2)
    rum = lp(rng.standard_normal((n, 2)), 160, 4) * (smooth_rand(n, 9, rng, 0.3, 1.0) * np.exp(-t / 0.7)
                                                    * np.minimum(1, t / 0.05))[:, None]
    y = 1.0 * stereo(crack) + 0.5 * np.pad(rip, ((0, n - len(rip)), (0, 0))) + 0.9 * norm(rum)
    return norm(room(y, rng, 1.3, 0.25)[:n]), 0


def sparks_swirl(dur: float, peak: float, seed=0, rot_hz=(1.0, 3.5)):
    """Sling-ring sparks: sizzling crackle whose source circles the listener (rotating pan, accelerating), swelling
    into `peak` and fading after."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    cr, _ = crackle(dur, seed=f"{seed}c", rate=(500, 1600), buzz=0.15, hz=180)
    sz = band_noise(n, 7000, 1.0, rng) * 0.4
    m = (cr.mean(axis=1) + sz.mean(axis=1))
    rot = np.interp(t, [0, peak, dur], [rot_hz[0], rot_hz[1], rot_hz[1] * 0.6])
    ph = 2 * np.pi * np.cumsum(rot) / SR
    p = 0.85 * np.sin(ph)
    lvl = np.where(t < peak, 10 ** (18 * (t / peak - 1) / 20), np.exp(-(t - peak) / (0.35 * (dur - peak) + 1e-3)))
    y = stereo(m * (0.75 + 0.25 * np.cos(ph)), p) * lvl[:, None]          # a little louder in front
    return norm(fade(y, 0.02, 0.05)), int(peak * SR)


def magic_whoosh(pre: float, post: float = 0.4, seed=0, root: float = 220.0):
    """A whoosh through a tuned comb (a shimmering, ringing 'magic' tone) rising into the peak."""
    rng = _rng(seed)
    y, h = swell(pre, post, 500, 5000, seed=f"{seed}s", rise_db=30, curve=1.4)
    out = np.zeros_like(y)
    for k, f in enumerate((root, root * 1.5, root * 2, root * 3)):
        D = int(SR / f)
        b = np.zeros(D + 1)
        b[0] = 1
        a = np.zeros(D + 1)
        a[0], a[D] = 1, -0.93
        out += sg.lfilter(b, a, y, axis=0) / (k + 1)
    return norm(fade(0.5 * y + 0.5 * norm(out) * 0.8)), h


# ---------------------------------------------------------------- symbiote, tunnel, web

def goo(dur: float, snap: float, seed=0):
    """Symbiote: viscous goo crawl (wandering formant squelch + bubble pops, densifying), a low growl swelling to the
    snap, the wet snap itself (a sharp crack + a downward squelch + a small thump) and a peel-away tail."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    k = np.clip(t / snap, 0, 1)
    # squelch: noise through a wandering formant, slow viscous AM
    fc = 260 + 650 * smooth_rand(n, 5, rng)
    sq = band_noise(n, fc, 0.7, rng)
    am = smooth_rand(n, 7, rng, 0.1, 1.0) ** 2
    sq *= (am * (0.25 + 0.75 * k) * np.where(t > snap, np.exp(-(t - snap) / 0.35), 1))[:, None]
    # bubbles: f rises ~60 % over a 10-35 ms pop
    nb = int(dur * 55)
    bt = np.sort(snap * rng.random(nb) ** 0.6)
    bt = np.concatenate([bt, snap + rng.exponential(0.15, nb // 4)])

    def bub(i, r):
        d = r.uniform(0.012, 0.035)
        m = int(d * 3 * SR)
        tt = np.arange(m) / SR
        f0 = r.uniform(220, 950)
        return np.sin(2 * np.pi * np.cumsum(f0 * (1 + 0.6 * tt / d)) / SR) * np.exp(-tt / d) * r.uniform(0.3, 1)

    bb = grains(n, bt, bub, rng)
    # growl: two low detuned saws, wobbling pitch, tanh, low-passed, swelling into the snap
    f = 52 * (1 + 0.04 * (smooth_rand(n, 6, rng) - 0.5)) * (1 + 0.15 * k)
    gr = sum(chirp_sine(f * h * (1 + d)) / h for h in range(1, 8) for d in (0, 0.011))
    gr = lp(np.tanh(1.8 * gr), 700, 2) * (10 ** (24 * (k - 1) / 20)) * np.where(t > snap, np.exp(-(t - snap) / 0.18), 1)
    # the wet snap
    ns = n - int(snap * SR)
    ts = np.arange(ns) / SR
    crack = hp(rng.standard_normal(ns), 1800) * np.exp(-ts / 0.012)
    squish = np.sin(2 * np.pi * np.cumsum(200 + 900 * np.exp(-ts / 0.03)) / SR) * np.exp(-ts / 0.07)
    th = np.sin(2 * np.pi * np.cumsum(45 + 60 * np.exp(-ts / 0.03)) / SR) * np.exp(-ts / 0.12)
    sn = np.zeros(n)
    sn[int(snap * SR):] = 0.9 * crack + 0.8 * squish + 0.9 * th
    y = 0.55 * norm(sq) + 0.4 * norm(bb) + 0.65 * stereo(norm(gr)) + 0.9 * stereo(norm(sn))
    return norm(room(fade(y, 0.05, 0.08), rng, 0.6, 0.15)[:n]), int(snap * SR)


def tunnel(dur: float, pass_t: float, out_t: float, seed=0, chord=(196.0, 293.7, 392.0, 440.0, 587.3, 784.0)):
    """Multiverse tunnel: a rising tunnel wind (resonant bands drifting up), shimmering detuned tones (a slow chord
    with tremolo, gliding up a little), a doppler pass at `pass_t` (a tone + noise source rushing past, left to right)
    and a whoosh out peaking at `out_t`."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = t / dur
    wind = sum(band_noise(n, f0 * 2 ** (1.3 * x) * (1 + 0.08 * smooth_rand(n, 1.5, rng, -1, 1)), 0.35, rng)
               for f0 in (300, 720, 1600))
    wind += 0.6 * band_noise(n, 4500 * 2 ** (0.8 * x), 1.6, rng)
    wl = 10 ** (20 * (np.minimum(t / out_t, 1) - 1) / 20) * np.minimum(1, t / 0.25)
    wind *= wl[:, None]
    glide = 2 ** (1.0 / 12 * x)
    sh = np.zeros((n, 2))
    for i, f in enumerate(chord):
        for c, dt in enumerate((-0.004, 0.004)):
            trem = 0.6 + 0.4 * np.sin(2 * np.pi * rng.uniform(4, 9) * t + rng.uniform(0, 6))
            sh[:, c] += np.sin(2 * np.pi * np.cumsum(f * glide * (1 + dt)) / SR + rng.uniform(0, 6)) * trem / (1 + 0.3 * i)
    sh *= (np.minimum(1, t / 0.4) * np.interp(t, [0, out_t, dur], [0.5, 1, 0.2]))[:, None]
    sh = hp(sh, 150)
    # doppler pass
    tp = t - pass_t
    d = 0.08
    vr = tp / np.sqrt(tp ** 2 + d ** 2)
    ratio = 1 / (1 + 0.22 * vr)
    src = np.tanh(1.5 * chirp_sine(620 * ratio)) + 0.5 * chirp_sine(1240 * ratio * 1.003)
    src = src + band_noise(n, 1800 * ratio, 1.5, rng).mean(axis=1) * 0.8
    dp = stereo(src * (d / np.sqrt(tp ** 2 + d ** 2)) ** 1.2, np.tanh(tp / 0.09) * 0.95)
    wo, h = swell(min(0.5, out_t - pass_t - 0.05), 0.35, 900, 6000, seed=f"{seed}o", rise_db=28)
    y = 0.55 * norm(wind) + 0.35 * norm(sh) + 0.6 * norm(dp)
    so = int(out_t * SR) - h
    y[so:so + len(wo)] += 0.85 * wo[: n - so]
    return norm(fade(y, 0.08, 0.12)), 0


def thwip(seed=0, direction: str = "R"):
    """Web shot: a short tight 'thwip' (band flicks up then down, ~80 ms) with a tiny pop, panned in the shot direction."""
    rng = _rng(seed)
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    c = interp_curve(t, [(0, 1500), (0.018, 5200), (0.08, 2400), (0.16, 1800)])
    y = band_noise(n, c, 0.9, rng).mean(axis=1) * np.minimum(1, t / 0.003) * np.exp(-t / 0.03)
    pop = np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.012)
    s = 1 if direction == "R" else -1
    return norm(fade(stereo(y + 0.4 * pop, np.interp(t, [0, 0.08], [-0.6 * s, 0.7 * s])), 0.0005, 0.02)), int(0.018 * SR)


def rip(dur: float = 0.42, peak: float = 0.12, seed=0, direction: str = "R"):
    """Web rip/yank: a tearing noise (dense irregular micro-bursts, 800-6 kHz) rising into `peak` and tearing away
    across the stereo field, with a low tug under it."""
    rng = _rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = band_noise(n, interp_curve(t, [(0, 1500), (peak, 3500), (dur, 2000)]), 2.0, rng).mean(axis=1)
    tear = (rng.random(n) < np.interp(t, [0, peak, dur], [80, 400, 60]) / SR).astype(float)
    tear = np.convolve(tear, np.hanning(int(0.006 * SR)), "same")
    y *= 0.25 + tear.clip(0, 1.5)
    e = np.where(t < peak, (t / peak) ** 2, np.exp(-(t - peak) / 0.09))
    tug = np.sin(2 * np.pi * np.cumsum(90 + 50 * np.exp(-np.abs(t - peak) / 0.05)) / SR) * np.exp(-np.abs(t - peak) / 0.06)
    s = 1 if direction == "R" else -1
    out = stereo(y * e, np.interp(t, [0, peak, dur], [-0.3 * s, 0.2 * s, 0.9 * s])) + 0.5 * stereo(tug)
    return norm(fade(out, 0.002, 0.03)), int(peak * SR)
