"""Free ambience and one-shot effects, synthesised with numpy: the effects stem without a paid generation.

film-ambience reads data/ambience.json and writes audio/sfx/sfx.wav (48 kHz / 24-bit stereo, the length of the film:
data/timeline.json's duration, else data/vo.json's), the file film-mix mixes as the effects stem.

    {"seed": 1,
     "beds": [{"sound": "sea", "start": 0, "end": 40, "gain_db": -18, "fade": 1.5, "intensity": 0.5},
              {"sound": "wind", "scene": "s2", "until": "s4", "gain_db": -24}],
     "hits": [{"sound": "thunder", "at": 8.0, "gain_db": -10, "duration": 5},
              {"sound": "match_strike", "scene": "s3", "offset": 0.4, "gain_db": -12, "pan": 0.2}]}

Beds (`sea waves_storm wind rain room_tone fire_crackle`) run from start to end (or from the window of `scene` to the
end of `until`, else of `scene`) with raised-cosine fades of `fade` seconds (default 1.5). `intensity` (0..1, default
0.5) deepens the modulation and trades about ±4 dB of level. Hits (`thunder wave_crash match_strike pen_scratch
footsteps gull bell door boat_creak cup`) begin sounding at `at` (or `scene` start, plus `offset`); `duration` sets
the length where the sound has one. `gain_db` is the level of the sound's peak (a bed's loudest sample) before the
mix. Everything is a function of `seed`: the same sheet renders the same samples. If the sum would pass -1.5 dBFS the
whole stem is scaled down, so it never clips.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import signal

from . import cli, paths, timeline
from .wav import SR, write_wav

CEILING_DB = -1.5
BEDS = ("sea", "waves_storm", "wind", "rain", "room_tone", "fire_crackle")
HITS = ("thunder", "wave_crash", "match_strike", "pen_scratch", "footsteps", "gull", "bell", "door", "boat_creak",
        "cup", "knock")


# ---- building blocks ---------------------------------------------------------------------------------------------

def noise(rng, n: int) -> np.ndarray:
    return rng.standard_normal(n)


def _filt(kind: str, x: np.ndarray, f, sr: int = SR, order: int = 2) -> np.ndarray:
    sos = signal.butter(order, f, btype=kind, fs=sr, output="sos")
    return signal.sosfilt(sos, x)


def lp(x, f, sr=SR, order=2):
    return _filt("lowpass", x, f, sr, order)


def hp(x, f, sr=SR, order=2):
    return _filt("highpass", x, f, sr, order)


def bp(x, lo, hi, sr=SR, order=2):
    return _filt("bandpass", x, [lo, hi], sr, order)


def slow(rng, n: int, hz: float, sr: int = SR) -> np.ndarray:
    """Smooth random control in about −1..1 that wanders at roughly `hz`."""
    m = int(n * hz / sr) + 4
    pts = rng.uniform(-1, 1, m)
    return np.interp(np.arange(n) / sr * hz, np.arange(m), pts)


def peak_norm(x: np.ndarray) -> np.ndarray:
    p = np.abs(x).max()
    return x / p if p > 0 else x


def bump(n: int, rise: float, fall: float, sr: int = SR) -> np.ndarray:
    """Unit-height envelope: raised-cosine rise over `rise` s, then raised-cosine fall over `fall` s (n samples)."""
    r, f = max(int(rise * sr), 1), max(int(fall * sr), 1)
    e = np.zeros(n)
    a = 0.5 - 0.5 * np.cos(np.pi * np.arange(min(r, n)) / r)
    e[:len(a)] = a
    if r < n:
        k = min(f, n - r)
        e[r:r + k] = 0.5 + 0.5 * np.cos(np.pi * np.arange(k) / f)
    return e


def add_at(buf: np.ndarray, x: np.ndarray, at: int) -> None:
    a, b = max(at, 0), min(at + len(x), len(buf))
    if b > a:
        buf[a:b] += x[a - at:b - at]


def decay(n: int, tau: float, attack: float = 0.002, sr: int = SR) -> np.ndarray:
    t = np.arange(n) / sr
    return np.exp(-t / tau) * np.minimum(t / attack, 1.0) if attack > 0 else np.exp(-t / tau)


def stereo_from(l: np.ndarray, r: np.ndarray, width: float = 0.7) -> np.ndarray:
    """Two independent signals mixed to a gentle width: 1 = fully independent, 0 = mono."""
    m = (l + r) / 2
    return np.stack([m + (l - m) * width, m + (r - m) * width], axis=1)


# ---- beds: each returns (n, 2) with peak 1 ------------------------------------------------------------------------

def _waves(rng, n, sr, inten, lo, hi, cutoff, hiss, rough, dens):
    """Swells of low-passed noise at random periods lo..hi s; a soft hiss peaks on each break."""
    ev, t = [], rng.uniform(0, hi / 2)
    while t < n / sr + hi:
        p = rng.uniform(lo, hi)
        ev.append((t, p, rng.uniform(0.6, 1.0)))
        t += p
    chans = []
    for c in range(2):
        env, hsenv = np.zeros(n), np.zeros(n)
        for t, p, a in ev:
            t0 = t + (0.25 * c)
            at = int(t0 * sr)
            m = int(p * 1.4 * sr)
            bmp = bump(m, p * 0.62, p * 0.78, sr)
            add_at(env, a * bmp * (0.55 + 0.45 * inten), at)
            hb = bump(int(p * sr), p * 0.55, p * 0.45, sr) ** 2
            add_at(hsenv, a * hb, at + int(p * 0.2 * sr))
        body = lp(noise(rng, n), cutoff, sr, 3)
        body = peak_norm(body) * (dens + (1 - dens) * env)
        if rough:
            body *= 1 + rough * peak_norm(lp(noise(rng, n), 9, sr))
        hs = peak_norm(bp(noise(rng, n), 1800, 7000, sr)) * hsenv * hiss
        chans.append(body + hs)
    return stereo_from(chans[0], chans[1], 0.8)


def bed_sea(rng, n, sr, inten):
    return _waves(rng, n, sr, inten, 4, 8, 380, 0.22, 0.0, 0.25)


def bed_waves_storm(rng, n, sr, inten):
    return _waves(rng, n, sr, inten, 3, 6, 230, 0.4, 0.35, 0.4)


def bed_wind(rng, n, sr, inten):
    chans = []
    for c in range(2):
        out = np.zeros(n)
        for lo, hi, hz, w in ((180, 420, 0.13, 1.0), (450, 1000, 0.21, 0.7), (1100, 2600, 0.33, 0.35)):
            band = peak_norm(bp(noise(rng, n), lo, hi, sr))
            amp = np.clip(0.55 + (0.35 + 0.35 * inten) * slow(rng, n, hz, sr), 0.02, None) ** 2
            out += w * band * amp
        gust = np.clip(0.3 + 0.7 * slow(rng, n, 0.08, sr) * (0.4 + inten), 0.05, None)
        chans.append(out * gust)
    # a faint whistle that drifts
    f = 520 + 260 * slow(rng, n, 0.1, sr)
    wh = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.clip(slow(rng, n, 0.12, sr), 0, None) ** 2 * 0.05 * inten
    return stereo_from(chans[0] + wh, chans[1] + np.roll(wh, int(0.02 * sr)), 0.8)


def bed_rain(rng, n, sr, inten):
    chans = []
    for _ in range(2):
        hiss = hp(noise(rng, n), 1800, sr) * 0.5
        dens = 250 + 900 * inten
        imp = (rng.random(n) < dens / sr) * rng.random(n) ** 2
        drops = hp(signal.lfilter([1], [1, -0.9], imp), 2500, sr)
        chans.append(hiss * (0.6 + 0.4 * inten) + drops * 14)
    return stereo_from(chans[0], chans[1], 0.9)


def bed_room_tone(rng, n, sr, inten):
    t = np.arange(n) / sr
    chans = []
    for c in range(2):
        low = lp(noise(rng, n), 160, sr, 2)
        air = hp(lp(noise(rng, n), 4000, sr), 800, sr) * 0.08
        hum = 0.06 * np.sin(2 * np.pi * 50 * t + c) + 0.03 * np.sin(2 * np.pi * 100 * t)
        chans.append(peak_norm(low) + air + hum * (0.5 + inten))
    return stereo_from(chans[0], chans[1], 0.6)


def bed_fire_crackle(rng, n, sr, inten):
    out = np.zeros((n, 2))
    rum = lp(noise(rng, n), 260, sr, 2)
    out += 0.25 * peak_norm(rum)[:, None] * (0.6 + 0.4 * (1 + slow(rng, n, 0.7, sr))[:, None] / 2)
    t = rng.exponential(0.1)
    while t < n / sr:
        m = int(rng.uniform(0.01, 0.05) * sr)
        pop = bp(noise(rng, m + 64), rng.uniform(900, 2500), rng.uniform(3500, 7000), sr)[64:] * decay(m, m / sr / 3, 0.0005)
        a = rng.random() ** 2 * (0.3 + 0.7 * rng.random())
        pan = rng.uniform(0.2, 0.8)
        for c, g in enumerate((pan, 1 - pan)):
            add_at(out[:, c], pop * a * g * 2, int(t * sr))
        t += rng.exponential(1 / (3 + 14 * inten))
    return out


# ---- hits: each returns mono, loudest sample about 1, sounding at sample 0 ----------------------------------------

def hit_thunder(rng, d, sr):
    n = int(d * sr)
    out = np.zeros(n)
    m = int(0.35 * sr)
    crack = hp(noise(rng, m), 900, sr) * decay(m, 0.05, 0.0005, sr)
    add_at(out, crack * 1.0, 0)
    for _ in range(4):  # the crack tears: smaller bursts trailing it
        k = int(rng.uniform(0.05, 0.14) * sr)
        add_at(out, hp(noise(rng, k), 500, sr) * decay(k, 0.03, 0.001, sr) * rng.uniform(0.15, 0.4),
               int(rng.uniform(0.03, 0.5) * sr))
    rum = lp(noise(rng, n), rng.uniform(110, 180), sr, 3)
    env = bump(n, 0.25, max(d - 0.25, 0.1), sr) ** 1.5 * np.exp(-np.arange(n) / sr / (d / 3))
    mod = np.clip(1 + 0.6 * slow(rng, n, 1.5, sr), 0.1, None)
    out += peak_norm(rum) * env * mod * 0.9
    return out


def hit_wave_crash(rng, d, sr):
    n = int(d * sr)
    env = bump(n, 0.012, d - 0.012, sr)
    body = peak_norm(lp(noise(rng, n), 500, sr, 3)) * env * 0.7
    hiss = peak_norm(bp(noise(rng, n), 1500, 8000, sr)) * bump(n, 0.02, d * 0.8, sr) ** 2 * 0.6
    return body + hiss


def hit_match_strike(rng, d, sr):
    n = int(d * sr)
    out = np.zeros(n)
    m = int(0.18 * sr)
    scr = bp(noise(rng, m), 2500, 8000, sr) * (0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 38 * np.arange(m) / sr)))
    add_at(out, scr * bump(m, 0.004, 0.175, sr) * 0.6, 0)
    f = int(max(d - 0.2, 0.3) * sr)
    wh = noise(rng, f)
    sweep = np.zeros(f)
    for lo, hi, w in ((300, 900, 1.0), (900, 2500, 0.8), (2500, 6000, 0.4)):
        sweep += w * bp(wh, lo, hi, sr)
    fe = bump(f, 0.04, f / sr - 0.04, sr) ** 2
    add_at(out, peak_norm(sweep) * fe * 0.8, int(0.2 * sr))
    # a few sizzles on the flame
    for _ in range(6):
        c = int(rng.uniform(0.25, 0.9) * sr)
        s = int(0.01 * sr)
        add_at(out, hp(noise(rng, s), 2500, sr) * decay(s, 0.003, 0.0003, sr) * 0.3, c)
    return out


def hit_pen_scratch(rng, d, sr):
    n = int(d * sr)
    out = np.zeros(n)
    t = 0.0
    while t < d:
        L = rng.uniform(0.06, 0.15)
        m = int(L * sr)
        s = bp(noise(rng, m), rng.uniform(2200, 3200), rng.uniform(5500, 8000), sr)
        e = np.sin(np.pi * np.arange(m) / m) ** 0.5 * np.minimum(np.arange(m) / (0.003 * sr), 1)
        add_at(out, s * e * rng.uniform(0.5, 1.0), int(t * sr))
        t += L + rng.uniform(0.03, 0.09)
    return out


def hit_footsteps(rng, d, sr):
    n = int(d * sr)
    out = np.zeros(n)
    t, i = 0.0, 0
    while t < d - 0.1:
        m = int(0.22 * sr)
        tt = np.arange(m) / sr
        f = 95 * np.exp(-tt * 12) + 55
        th = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt / 0.05)
        sc = lp(noise(rng, m), 700, sr) * np.exp(-tt / 0.02) * 0.6
        a = (1.0 if i % 2 == 0 else 0.8) * rng.uniform(0.8, 1.0)
        add_at(out, (th + sc) * np.minimum(tt / 0.002, 1) * a, int(t * sr))
        t += 0.5 + rng.uniform(-0.04, 0.04)
        i += 1
    return out


def hit_gull(rng, d, sr):
    n = int(d * sr)
    out = np.zeros(n)
    k = int(rng.integers(3, 5))
    t = 0.0
    for i in range(k):
        L = rng.uniform(0.2, 0.34) * (1.4 if i == k - 1 else 1)
        if t + L > d:
            break
        m = int(L * sr)
        tt = np.arange(m) / sr
        f0 = rng.uniform(2000, 2600)
        f = f0 * (1.0 - 0.45 * (tt / L) ** 0.8) + 60 * np.sin(2 * np.pi * 28 * tt)
        ph = 2 * np.pi * np.cumsum(f) / sr
        y = np.sin(ph) + 0.45 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)
        y *= bump(m, 0.02, L - 0.02, sr) ** 0.7 * np.minimum(tt / 0.004, 1)
        add_at(out, y * (1.0 - 0.1 * i), int(t * sr))
        t += L + rng.uniform(0.07, 0.14)
    return out


def hit_bell(rng, d, sr, freq=None):
    n = int(d * sr)
    f0 = freq or rng.uniform(330, 440)
    tt = np.arange(n) / sr
    out = np.zeros(n)
    for i, r in enumerate((0.5, 1.0, 1.19, 1.56, 2.0, 2.51, 2.74, 3.0, 4.07)):
        tau = d / 5 / (1 + 0.7 * i)
        out += np.sin(2 * np.pi * f0 * r * tt + rng.uniform(0, 6.28)) * np.exp(-tt / tau) / (1 + 0.5 * i)
    return out * np.minimum(tt / 0.002, 1)


def hit_door(rng, d, sr):
    n = int(d * sr)
    out = np.zeros(n)
    k = int(0.012 * sr)
    add_at(out, bp(noise(rng, k), 1500, 5000, sr) * decay(k, 0.003, 0.0003, sr) * 0.5, 0)  # latch
    m = int(0.4 * sr)
    tt = np.arange(m) / sr
    th = np.sin(2 * np.pi * np.cumsum(70 * np.exp(-tt * 8) + 45) / sr) * np.exp(-tt / 0.09)
    body = lp(noise(rng, m), 500, sr) * np.exp(-tt / 0.05) * 0.6
    add_at(out, (th + body) * np.minimum(tt / 0.003, 1), int(0.12 * sr))
    return out


def hit_boat_creak(rng, d, sr):
    n = int(d * sr)
    tt = np.arange(n) / sr
    out = np.zeros(n)
    ph = 2 * np.pi * np.cumsum(110 + 60 * np.sin(2 * np.pi * 0.9 * tt) + 25 * slow(rng, n, 14, sr)) / sr
    saw = signal.sawtooth(ph) * (1 + 0.5 * np.sign(np.sin(ph * 0.5)))
    res = bp(saw, 350, 1100, sr) + 0.6 * bp(saw, 1200, 2200, sr)
    env = np.clip(0.2 + 0.9 * np.sin(2 * np.pi * 0.7 * tt + rng.uniform(0, 3)), 0, 1) * bump(n, 0.05, d - 0.05, sr)
    return res * env


def hit_cup(rng, d, sr):
    n = int(d * sr)
    out = np.zeros(n)
    tt = np.arange(n) / sr
    for t0, a in ((0.0, 1.0), (0.11, 0.35)):
        base = rng.uniform(3100, 3500) * (1.04 if a < 1 else 1)
        y = np.zeros(n)
        for r, w, tau in ((1.0, 1.0, 0.12), (1.52, 0.6, 0.08), (2.31, 0.35, 0.05)):
            y += w * np.sin(2 * np.pi * base * r * tt) * np.exp(-tt / tau)
        k = int(0.004 * sr)
        y[:k] += hp(noise(rng, k), 3000, sr) * 0.8
        add_at(out, y * a * np.minimum(tt / 0.0008, 1), int(t0 * sr))
    return out


def hit_knock(rng, d, sr):
    """One knuckle rap on something hard and hollow (a door, a crust): a click, then a short woody thud."""
    n = int(d * sr)
    out = np.zeros(n)
    tt = np.arange(n) / sr
    k = int(0.006 * sr)
    add_at(out, bp(noise(rng, k), 1800, 6000, sr) * decay(k, 0.0015, 0.0002, sr) * 0.6, 0)
    f0 = rng.uniform(170, 210)
    th = np.sin(2 * np.pi * np.cumsum(f0 * (1 + 0.6 * np.exp(-tt * 60))) / sr) * np.exp(-tt / 0.045)
    wood = bp(noise(rng, n), 300, 1400, sr) * np.exp(-tt / 0.02) * 0.5
    return out + (th + wood) * np.minimum(tt / 0.001, 1)


BED_FN = {"sea": bed_sea, "waves_storm": bed_waves_storm, "wind": bed_wind, "rain": bed_rain,
          "room_tone": bed_room_tone, "fire_crackle": bed_fire_crackle}
# sound: (function, default duration in seconds)
HIT_FN = {"thunder": (hit_thunder, 5.0), "wave_crash": (hit_wave_crash, 3.0), "match_strike": (hit_match_strike, 1.0),
          "pen_scratch": (hit_pen_scratch, 1.2), "footsteps": (hit_footsteps, 3.0), "gull": (hit_gull, 1.6),
          "bell": (hit_bell, 5.0), "door": (hit_door, 0.6), "boat_creak": (hit_boat_creak, 1.6),
          "cup": (hit_cup, 0.5), "knock": (hit_knock, 0.3)}


# ---- the sheet ---------------------------------------------------------------------------------------------------

def _window(windows: list[dict], sid: str, what: str) -> dict:
    for w in windows:
        if w["id"] == sid:
            return w
    have = ", ".join(w["id"] for w in windows) or "none"
    raise ValueError(f"{what}: unknown scene {sid!r} (scenes: {have})")


def resolve_bed(b: dict, windows: list[dict], duration: float, i: int) -> tuple[float, float]:
    what = f"bed {i} ({b.get('sound')})"
    if "scene" in b:
        start = _window(windows, b["scene"], what)["start"]
        end = _window(windows, b.get("until", b["scene"]), what)["end"]
    elif "start" in b and "end" in b:
        start, end = float(b["start"]), float(b["end"])
    else:
        raise ValueError(f"{what}: needs start and end, or scene")
    end = min(end, duration)
    if not 0 <= start < end:
        raise ValueError(f"{what}: window {start:.3f}-{end:.3f} s is empty or outside the film (0-{duration:.3f} s)")
    return start, end


def resolve_hit(h: dict, windows: list[dict], duration: float, i: int) -> float:
    what = f"hit {i} ({h.get('sound')})"
    if "at" in h:
        t = float(h["at"])
    elif "scene" in h:
        t = _window(windows, h["scene"], what)["start"]
    else:
        raise ValueError(f"{what}: needs at, or scene")
    t += float(h.get("offset", 0.0))
    if not 0 <= t < duration:
        raise ValueError(f"{what}: at {t:.3f} s is outside the film (0-{duration:.3f} s)")
    return t


def _pan(x: np.ndarray, pan: float) -> np.ndarray:
    th = (float(np.clip(pan, -1, 1)) + 1) * np.pi / 4
    return np.stack([x * np.cos(th), x * np.sin(th)], axis=1)


def render(doc: dict, windows: list[dict], duration: float, sr: int = SR) -> np.ndarray:
    """The stem, (round(duration·sr), 2) float32, for an ambience sheet and the scene windows
    [{id, start, end}]. Unknown sounds, scenes or windows are a ValueError."""
    seed = int(doc.get("seed", 1))
    n = int(round(duration * sr))
    bus = np.zeros((n, 2))
    beds, hits = doc.get("beds", []), doc.get("hits", [])
    for i, b in enumerate(beds):
        if b.get("sound") not in BED_FN:
            raise ValueError(f"bed {i}: unknown sound {b.get('sound')!r} (beds: {', '.join(BEDS)})")
    for i, h in enumerate(hits):
        if h.get("sound") not in HIT_FN:
            raise ValueError(f"hit {i}: unknown sound {h.get('sound')!r} (hits: {', '.join(HITS)})")
    for i, b in enumerate(beds):
        start, end = resolve_bed(b, windows, duration, i)
        a, z = int(round(start * sr)), min(int(round(end * sr)), n)
        m = z - a
        inten = float(np.clip(b.get("intensity", 0.5), 0, 1))
        rng = np.random.default_rng([seed, 0, i])
        y = BED_FN[b["sound"]](rng, m, sr, inten)
        y = y / max(np.abs(y).max(), 1e-12)
        f = min(int(round(float(b.get("fade", 1.5)) * sr)), m // 2)
        if f:
            ramp = 0.5 - 0.5 * np.cos(np.pi * (np.arange(f) + 0.5) / f)
            y[:f] *= ramp[:, None]
            y[m - f:] *= ramp[::-1, None]
        g = 10 ** ((float(b.get("gain_db", -18)) + (inten - 0.5) * 8) / 20)
        bus[a:z] += y * g
    for i, h in enumerate(hits):
        fn, dflt = HIT_FN[h["sound"]]
        t = resolve_hit(h, windows, duration, i)
        d = float(h.get("duration", dflt))
        if d <= 0:
            raise ValueError(f"hit {i} ({h['sound']}): duration must be positive")
        rng = np.random.default_rng([seed, 1, i])
        y = fn(rng, d, sr, h["freq"]) if h["sound"] == "bell" and "freq" in h else fn(rng, d, sr)
        y = y / max(np.abs(y).max(), 1e-12)
        e = min(int(0.02 * sr), len(y) // 4)
        y[len(y) - e:] *= np.linspace(1, 0, e)  # no click at the tail
        g = 10 ** (float(h.get("gain_db", -12)) / 20)
        st = _pan(y * g, float(h.get("pan", 0.0)))
        at = int(round(t * sr))
        z = min(at + len(y), n)
        bus[at:z] += st[:z - at] * np.sqrt(2)
    peak = np.abs(bus).max()
    ceil = 10 ** (CEILING_DB / 20)
    if peak > ceil:
        bus *= ceil / peak
    return bus.astype(np.float32)


def load_sheet(path: Path | None = None) -> dict:
    path = Path(path) if path is not None else paths.current().data / "ambience.json"
    if not path.is_file():
        raise SystemExit(f"{path} is missing: write {{\"seed\": 1, \"beds\": [...], \"hits\": [...]}} (see filmtools/ambience.py)")
    return json.loads(path.read_text())


def main(argv=None):
    ap = cli.parser("Synthesise data/ambience.json into audio/sfx/sfx.wav: free beds and one-shots, no paid call")
    ap.add_argument("--sheet", help="the ambience sheet (default: data/ambience.json)")
    ap.add_argument("--out", help="the stem (default: audio/sfx/sfx.wav)")
    a = cli.parse(ap, argv)
    fp = paths.current()
    doc = load_sheet(Path(a.sheet) if a.sheet else None)
    tl = timeline.require(fp.data)
    out = Path(a.out) if a.out else fp.audio / "sfx" / "sfx.wav"
    try:
        bus = render(doc, tl["scenes"], tl["duration"])
    except ValueError as e:
        raise SystemExit(str(e))
    write_wav(out, bus)
    pk = 20 * np.log10(np.abs(bus).max() + 1e-12)
    print(f"{out} · {len(doc.get('beds', []))} beds · {len(doc.get('hits', []))} hits · {tl['duration']:.3f} s · "
          f"peak {pk:.1f} dBFS")
