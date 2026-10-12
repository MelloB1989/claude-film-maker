"""film-temptrack: a procedural temp score, so a film can be cut to a beat with no paid audio.

The score is synthesised from scratch (numpy; the loudness meter is the voice chain's BS.1770 one) on an exact grid:
beat k sits at offset + k · 60/bpm, and every bar has --beats-per-bar beats. Two styles:

- pulse: four-on-the-floor kick, claps on the off beats, closed and open hats, a sub bass that ducks under the kick,
  a band-limited saw pad on a minor progression, and a noise riser into each section after a quiet one;
- cinematic: sparse low hits on downbeats, ticks, a sustained sub drone, the pad, and risers that land on the
  downbeat of each new section.

Sections are --phrase bars long (default 8) and arranged by style (intro, groove or build, break or peak, outro).
Every voice is band-limited, every hit starts and ends on a short fade, the master fades in over 5 ms and out over
the last bar (at most 2 s), and a gentle bus compressor and a smooth look-ahead limiter bring it to about the film's
loudness target (pipeline.mix.lufs, −14 LUFS) with sample peaks at or under −1.5 dBFS. One seed, one score: the same
arguments always write the same samples.

It writes the WAV (48 kHz stereo 24-bit, default audio/music/temp.wav) with its sidecar (<name>.plan.json: the
section timing film-beats and film-splice read), and the exact grid into data/audio.json in film-beats' schema, its
envelopes and onsets taken from the stems it synthesised (the vocal envelope is zero, there are no vocal onsets). It
records the score as the chosen one in data/music_plan.json when nothing is chosen yet (or with --choose), and
--mix copies it to the film's mix (film.json audio.mix) so the player has audio before film-mix runs.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import cli, config, timeline
from .vochain import loudness
from .wav import SR, write_wav

STYLES = ("pulse", "cinematic")
FPS = 100  # the analysis frame rate, as film-beats writes it
CEILING_DBFS = -1.5  # the limiter's sample-peak ceiling: true peaks stay under −1 dBFS
MAX_LIMIT_DB = 6.0  # more gain reduction than this and the score is left quieter than the target instead

# minor-key progressions, in semitones over the root; each degree's triad quality
PROGRESSIONS = [(0, 8, 3, 10), (0, 5, 8, 7), (0, 10, 8, 10), (0, 3, 10, 5), (0, 8, 5, 7)]
QUALITY = {0: (0, 3, 7), 3: (0, 4, 7), 5: (0, 3, 7), 7: (0, 4, 7), 8: (0, 4, 7), 10: (0, 4, 7)}
ROOTS = (45, 46, 47, 48, 49, 50, 52)  # A2 … E3: the bass a few octaves below, the pad above


def midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


# ---------------------------------------------------------------- the grid and the arrangement

@dataclass(frozen=True)
class Grid:
    """An exact beat grid: `bars` bars of `bpb` beats at `bpm`, the first beat at `offset`, `duration` seconds."""
    bpm: float
    bpb: int
    bars: int
    offset: float
    duration: float

    @property
    def period(self) -> float:
        return 60.0 / self.bpm

    @property
    def bar(self) -> float:
        return self.bpb * self.period

    @property
    def beats(self) -> np.ndarray:
        k = np.arange(self.bars * self.bpb + 1)
        t = self.offset + k * self.period
        return t[t < self.duration - 1e-9]

    @property
    def downbeats(self) -> np.ndarray:
        return self.beats[::self.bpb]

    def bar_start(self, b: int) -> float:
        return self.offset + b * self.bar


def make_grid(bpm: float, bpb: int = 4, bars: int | None = None, duration: float | None = None,
              offset: float = 0.0) -> Grid:
    """The grid for `bars` bars, or for as many bars as cover `duration` seconds (which is then kept exactly)."""
    if bpm <= 0 or bpb < 1 or offset < 0:
        raise ValueError("bpm must be positive, beats per bar at least 1 and the offset not negative")
    bar = 60.0 * bpb / bpm
    if bars is None and duration is None:
        raise ValueError("give bars or a duration")
    if bars is None:
        bars = max(1, math.ceil((duration - offset) / bar - 1e-9))
    if duration is None:
        duration = offset + bars * bar
    if bars < 1 or duration <= offset:
        raise ValueError("the score needs at least one bar")
    return Grid(float(bpm), int(bpb), int(bars), float(offset), float(duration))


def arrangement(n: int, style: str) -> list[str]:
    """The kind of each of n sections."""
    if style == "pulse":
        if n == 1:
            return ["groove"]
        kinds = ["intro"] + ["groove"] * (n - 1)
        if n >= 4:
            kinds[n - 2 if n < 6 else n - 3] = "break"
        if n >= 6:
            kinds[-1] = "outro"
        return kinds
    if n == 1:
        return ["build"]
    outro = n >= 5
    rest = n - 1 - outro
    peaks = max(1, rest // 2)
    return ["intro"] + ["build"] * (rest - peaks) + ["peak"] * peaks + (["outro"] if outro else [])


def sections(grid: Grid, style: str, phrase: int = 8) -> list[dict]:
    """[{name, kind, bar0, bar1, start, end}]: phrase-long sections (the last may be shorter), named by kind and
    numbered where a kind repeats. The first starts at 0, the last ends with the film."""
    phrase = max(1, min(phrase, grid.bars))
    n = math.ceil(grid.bars / phrase)
    kinds = arrangement(n, style)
    seen: dict[str, int] = {}
    out = []
    for i, kind in enumerate(kinds):
        seen[kind] = seen.get(kind, 0) + 1
        b0, b1 = i * phrase, min((i + 1) * phrase, grid.bars)
        out.append({"name": kind if seen[kind] == 1 else f"{kind} {seen[kind]}", "kind": kind, "bar0": b0, "bar1": b1,
                    "start": 0.0 if i == 0 else grid.bar_start(b0),
                    "end": grid.duration if i == n - 1 else grid.bar_start(b1)})
    return out


# ---------------------------------------------------------------- band-limited voices

def _fft_band(x: np.ndarray, sr: int, lo: float, hi: float, soft: float = 0.3) -> np.ndarray:
    """x through a zero-phase band-pass with raised-cosine skirts `soft` octaves wide (lo 0: a low-pass)."""
    n = x.shape[-1]
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / sr)
    with np.errstate(divide="ignore"):
        oct_f = np.log2(np.maximum(f, 1e-9))
    g = np.ones_like(f)
    if lo > 0:
        u = np.clip((oct_f - (np.log2(lo) - soft)) / soft, 0, 1)
        g *= 0.5 - 0.5 * np.cos(np.pi * u)
    u = np.clip(((np.log2(hi) + soft) - oct_f) / soft, 0, 1)
    g *= 0.5 - 0.5 * np.cos(np.pi * u)
    return np.fft.irfft(spec * g, n)


def _fade(x: np.ndarray, sr: int, fin: float = 0.001, fout: float = 0.01) -> np.ndarray:
    x = x.copy()
    a, b = min(len(x), max(1, int(fin * sr))), min(len(x), max(1, int(fout * sr)))
    shape = (-1,) + (1,) * (x.ndim - 1)
    x[:a] *= np.linspace(0, 1, a).reshape(shape)
    x[-b:] *= np.linspace(1, 0, b).reshape(shape)
    return x


def kick(sr: int, rng) -> np.ndarray:
    n = int(0.45 * sr)
    t = np.arange(n) / sr
    f = 46 + 110 * np.exp(-t / 0.03)
    body = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.2)
    click = _fft_band(rng.standard_normal(n), sr, 1500, 5000) * np.exp(-t / 0.003)
    return _fade(0.95 * body + 0.08 * click / (np.abs(click).max() + 1e-12), sr)


def clap(sr: int, rng) -> np.ndarray:
    n = int(0.3 * sr)
    t = np.arange(n) / sr
    noise = _fft_band(rng.standard_normal(n), sr, 900, 4000)
    env = sum(np.where(t >= d, np.exp(-(t - d) / 0.004), 0.0) for d in (0.0, 0.009, 0.018))
    env = env + np.where(t >= 0.024, 0.6 * np.exp(-(t - 0.024) / 0.07), 0.0)
    x = noise * env
    return _fade(0.8 * x / np.abs(x).max(), sr, 0.0005, 0.02)


def hat(sr: int, rng, open_: bool = False) -> np.ndarray:
    dur, tau = (0.3, 0.11) if open_ else (0.06, 0.018)
    n = int(dur * sr)
    t = np.arange(n) / sr
    x = _fft_band(rng.standard_normal(n), sr, 7000, 15000) * np.exp(-t / tau)
    return _fade(0.6 * x / np.abs(x).max(), sr, 0.0005, 0.01)


def boom(sr: int, rng) -> np.ndarray:
    n = int(1.6 * sr)
    t = np.arange(n) / sr
    f = 36 + 40 * np.exp(-t / 0.08)
    body = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.55)
    sub = 0.4 * np.sin(np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.7)
    thump = _fft_band(rng.standard_normal(n), sr, 0, 280) * np.exp(-t / 0.05)
    x = body + sub + 0.5 * thump / (np.abs(thump).max() + 1e-12)
    return _fade(0.95 * x / np.abs(x).max(), sr, 0.002, 0.2)


def tick(sr: int, rng) -> np.ndarray:
    n = int(0.05 * sr)
    t = np.arange(n) / sr
    x = _fft_band(rng.standard_normal(n), sr, 2500, 7000) * np.exp(-t / 0.009)
    return _fade(0.5 * x / np.abs(x).max(), sr, 0.0005, 0.01)


def riser(sr: int, rng, seconds: float) -> np.ndarray:
    """Band-passed noise swelling and a chirp sweeping 200 Hz → 1.6 kHz, ending at its last sample (a downbeat),
    stereo: each side its own noise."""
    n = max(2, int(seconds * sr))
    t = np.arange(n) / sr
    u = t / seconds
    sweep = 200 * 8 ** u
    chirp = np.sin(2 * np.pi * np.cumsum(sweep) / sr)
    out = np.empty((n, 2))
    for ch in range(2):
        noise = _fft_band(rng.standard_normal(n), sr, 1500, 9000, soft=0.6)
        noise /= np.abs(noise).max() + 1e-12
        out[:, ch] = (0.5 * noise * u ** 2.5 + 0.25 * chirp * u ** 2)
    out = _fade(out, sr, 0.05, 0.004)
    return 0.7 * out / np.abs(out).max()


def wavetable(harmonics: int = 24, size: int = 4096) -> np.ndarray:
    """One cycle of a mellow band-limited saw: harmonics up to `harmonics`, rolled off above the eighth."""
    ph = np.arange(size) / size
    k = np.arange(1, harmonics + 1)
    amp = (1 / k) * np.exp(-k / 9)
    table = (amp[:, None] * np.sin(2 * np.pi * k[:, None] * ph[None, :])).sum(axis=0)
    return table / np.abs(table).max()


def osc(freq: np.ndarray, sr: int, table: np.ndarray, phase0: float = 0.0) -> np.ndarray:
    """A wavetable read at a per-sample frequency; the phase runs on across frequency changes (no clicks)."""
    ph = (phase0 + np.cumsum(freq) / sr) % 1.0
    idx = ph * len(table)
    i0 = idx.astype(np.int64) % len(table)
    frac = idx - np.floor(idx)
    return table[i0] * (1 - frac) + table[(i0 + 1) % len(table)] * frac


def _smooth(x: np.ndarray, sr: int, seconds: float) -> np.ndarray:
    """A centred moving average `seconds` long (level changes glide instead of stepping)."""
    w = max(1, int(seconds * sr))
    c = np.concatenate([[0.0], np.cumsum(np.pad(x, (w // 2, w - w // 2 - 1), mode="edge"))])
    return (c[w:] - c[:-w]) / w


# ---------------------------------------------------------------- the score

@dataclass
class Score:
    audio: np.ndarray  # (n, 2) master
    stems: dict[str, np.ndarray]  # name → (n, 2), as mixed (before the master's dynamics)
    onsets: dict[str, list[list[float]]]  # kick, snare, hat, vocal: [[t, strength]]
    sections: list[dict]
    grid: Grid
    lufs: float
    limit_db: float


def _place(bus: np.ndarray, x: np.ndarray, t: float, sr: int, gain: float = 1.0, pan: float = 0.0) -> None:
    i = int(round(t * sr))
    if i >= len(bus):
        return
    if i < 0:  # a riser longer than the time before its downbeat starts cut, never late
        x, i = x[-i:], 0
    th = (np.clip(pan, -1, 1) + 1) * np.pi / 4
    x = x[:len(bus) - i]
    if x.ndim == 1:
        bus[i:i + len(x), 0] += gain * np.cos(th) * x
        bus[i:i + len(x), 1] += gain * np.sin(th) * x
    else:
        bus[i:i + len(x)] += gain * x


def synthesize(grid: Grid, style: str = "pulse", seed: int = 1, phrase: int = 8, sr: int = SR) -> tuple[dict, dict, list]:
    """The stems ({name: (n, 2)}), the onsets they hold and the sections, before mixing."""
    if style not in STYLES:
        raise ValueError(f"style must be one of {', '.join(STYLES)}, not {style!r}")
    rng = np.random.default_rng(seed)
    n = int(round(grid.duration * sr))
    secs = sections(grid, style, phrase)
    root = int(rng.choice(ROOTS))
    prog = PROGRESSIONS[int(rng.integers(len(PROGRESSIONS)))]
    names = ("kick", "clap", "hat", "boom", "tick", "sub", "pad", "riser")
    st = {k: np.zeros((n, 2)) for k in names}
    on: dict[str, list[list[float]]] = {"kick": [], "snare": [], "hat": [], "vocal": []}
    sounds = {"kick": kick(sr, rng), "clap": clap(sr, rng), "hats": [hat(sr, rng) for _ in range(4)],
              "open": hat(sr, rng, True), "boom": boom(sr, rng), "ticks": [tick(sr, rng) for _ in range(3)]}
    p, bpb = grid.period, grid.bpb
    pad_level = np.zeros(n)
    sub_level = np.zeros(n)
    duck = np.ones(n)  # the sub's sidechain under the kick (pulse)
    chord_bars = 1 if style == "pulse" else 2

    def hit(stem: str, sound: np.ndarray, t: float, vel: float, onset: str | None, pan: float = 0.0) -> None:
        if t >= grid.duration:
            return
        _place(st[stem], sound, t, sr, vel, pan)
        if onset:
            on[onset].append([round(t, 6), round(vel, 3)])

    for si, sec in enumerate(secs):
        kind = sec["kind"]
        a, b = int(round(sec["start"] * sr)), int(round(sec["end"] * sr))
        nxt = secs[si + 1]["kind"] if si + 1 < len(secs) else None
        pad_level[a:b] = {"intro": 0.55, "groove": 0.45, "break": 0.8, "outro": 0.5, "build": 0.6, "peak": 0.75}[kind]
        sub_level[a:b] = {"intro": 0.35, "groove": 0.8, "break": 0.0, "outro": 0.6, "build": 0.45, "peak": 0.7}[kind]
        nbars = sec["bar1"] - sec["bar0"]
        for bi in range(sec["bar0"], sec["bar1"]):
            t0 = grid.bar_start(bi)
            last_bar = bi == sec["bar1"] - 1
            late_half = (bi - sec["bar0"]) >= nbars / 2
            for k in range(bpb):
                t = t0 + k * p
                if style == "pulse":
                    fill = kind == "groove" or (kind == "outro" and not late_half)
                    if fill:
                        v = 0.92 + 0.08 * rng.random()
                        hit("kick", sounds["kick"], t, v, "kick")
                        i0 = int(round(t * sr))
                        m = min(n - i0, int(0.35 * sr))
                        if m > 0:
                            duck[i0:i0 + m] = np.minimum(duck[i0:i0 + m],
                                                         1 - 0.75 * np.exp(-np.arange(m) / (0.09 * sr)))
                        if k % 2 == 1:
                            hit("clap", sounds["clap"], t, 0.75 + 0.1 * rng.random(), "snare")
                    if kind in ("groove", "intro", "outro", "break"):
                        off = t + p / 2
                        is_open = fill and k == bpb - 1 and bi % 2 == 1
                        vel = {"groove": 0.7, "intro": 0.45, "outro": 0.5, "break": 0.3}[kind]
                        snd = sounds["open"] if is_open else sounds["hats"][int(rng.integers(4))]
                        hit("hat", snd, off, vel * (0.85 + 0.15 * rng.random()), "hat", pan=0.25)
                        if kind == "groove" and late_half:
                            for q in (0.25, 0.75):
                                hit("hat", sounds["hats"][int(rng.integers(4))], t + q * p,
                                    0.3 + 0.1 * rng.random(), "hat", pan=-0.2)
                else:
                    if kind == "intro" and bi == sec["bar0"] and k == 0:
                        hit("boom", sounds["boom"], t, 0.8, "kick")
                    if kind == "build" and k == 0:
                        hit("boom", sounds["boom"], t, 0.55 + 0.35 * (bi - sec["bar0"] + 1) / nbars, "kick")
                    if kind == "peak" and k in (0, bpb // 2 if bpb > 2 else 0):
                        hit("boom", sounds["boom"], t, 0.95 if k == 0 else 0.7, "kick")
                    if kind == "outro" and bi == sec["bar0"] and k == 0:
                        hit("boom", sounds["boom"], t, 1.0, "kick")
                    if kind in ("build", "peak"):
                        hit("tick", sounds["ticks"][k % 3], t, 0.35 + 0.1 * rng.random(), "hat", pan=0.3)
                    if kind == "peak":
                        hit("tick", sounds["ticks"][(k + 1) % 3], t + p / 2, 0.22, "hat", pan=-0.3)
            if last_bar and nxt is not None and (style == "cinematic" or kind in ("intro", "break")):
                length = grid.bar if style == "pulse" else min(2 * grid.bar, (sec["end"] - sec["start"]))
                land = secs[si + 1]["start"]
                r = riser(sr, rng, length)
                _place(st["riser"], r, land - len(r) / sr, sr, 0.55 if style == "pulse" else 0.6)

    # tonal voices: the progression, one chord per `chord_bars` bars
    chord_of = np.zeros(n, dtype=np.int64)
    for bi in range(grid.bars):
        a = int(round(grid.bar_start(bi) * sr)) if bi else 0
        b = int(round(grid.bar_start(bi + 1) * sr)) if bi + 1 < grid.bars else n
        chord_of[a:b] = prog[(bi // chord_bars) % len(prog)]
    bass = np.array([midi_hz(root - 12 + d) for d in range(12)])[chord_of % 12]
    sub = np.sin(2 * np.pi * np.cumsum(bass) / sr) + 0.12 * np.sin(4 * np.pi * np.cumsum(bass) / sr)
    level = _smooth(sub_level, sr, 0.15) * (duck if style == "pulse" else 1.0)
    st["sub"] = np.stack([sub * level, sub * level], axis=1) * 0.5
    table = wavetable()
    pad = np.zeros((n, 2))
    for v in range(3):
        note = np.zeros(n)
        for deg, tones in QUALITY.items():
            m = chord_of == deg
            if m.any():
                note[m] = midi_hz(root + 12 + deg + tones[v])
        for ch, det in enumerate((1.004, 0.996)):
            pad[:, ch] += osc(note * det, sr, table, phase0=0.13 * v + 0.37 * ch)
    pad = _fft_band(pad.T, sr, 0, 2400, soft=1.0).T
    st["pad"] = pad * (_smooth(pad_level, sr, 0.6)[:, None] * 0.12)
    for k in on:
        on[k].sort()
    return st, on, secs


GAINS_DB = {"kick": -1.0, "clap": -6.0, "hat": -11.0, "boom": 0.0, "tick": -9.0, "sub": -5.0, "pad": -11.0,
            "riser": -10.0}


def _compress(x: np.ndarray, sr: int, thresh_db: float = -20.0, ratio: float = 2.0, max_db: float = 4.0,
              attack: float = 0.01, release: float = 0.15) -> np.ndarray:
    """A gentle bus compressor: 10 ms RMS blocks, an attack/release one-pole on the level, 2:1 above thresh_db, at
    most max_db of gain reduction, the gain interpolated between block centres."""
    blk = int(0.01 * sr)
    nb = -(-len(x) // blk)
    pw = np.zeros(nb * blk)
    pw[:len(x)] = (x ** 2).mean(axis=1)
    lvl = 10 * np.log10(pw.reshape(nb, blk).mean(axis=1) + 1e-12)
    aa, ar = math.exp(-0.01 / attack), math.exp(-0.01 / release)
    env, e = np.empty(nb), lvl[0]
    for i, v in enumerate(lvl.tolist()):
        e = (aa if v > e else ar) * e + (1 - (aa if v > e else ar)) * v
        env[i] = e
    red = np.clip((env - thresh_db) * (1 - 1 / ratio), 0, max_db)
    g = 10 ** (-np.interp(np.arange(len(x)), (np.arange(nb) + 0.5) * blk, red) / 20)
    return x * g[:, None]


def limit(x: np.ndarray, sr: int, ceiling_db: float = CEILING_DBFS, look: float = 0.005,
          hold: float = 0.05) -> tuple[np.ndarray, float]:
    """A smooth look-ahead peak limiter (offline, so it delays nothing): the gain each 1 ms block needs, held for
    `hold` and anticipated by `look`, averaged over `look`, never above what any sample needs. (out, max dB taken)."""
    ceil = 10 ** (ceiling_db / 20)
    blk = int(0.001 * sr)
    nb = -(-len(x) // blk)
    pk = np.zeros(nb * blk)
    pk[:len(x)] = np.abs(x).max(axis=1)
    need = np.minimum(1.0, ceil / np.maximum(pk.reshape(nb, blk).max(axis=1), 1e-12))
    a, r = max(1, int(round(look / 0.001))), max(1, int(round(hold / 0.001)))
    padded = np.pad(need, (r, a), constant_values=1.0)
    win = np.lib.stride_tricks.sliding_window_view(padded, a + r + 1).min(axis=1)  # block b: min over [b-r, b+a]
    h = a // 2
    c = np.concatenate([[0.0], np.cumsum(np.pad(win, (h, h), mode="edge"))])
    g_blk = (c[2 * h + 1:] - c[:-2 * h - 1]) / (2 * h + 1)
    g = np.interp(np.arange(len(x)), (np.arange(nb) + 0.5) * blk, g_blk)
    y = x * g[:, None]
    over = np.abs(y).max()
    if over > ceil:  # the last fraction of a sample's worth of interpolation
        y *= ceil / over
    return y, float(-20 * np.log10(max(g.min(), 1e-12)))


def master(stems: dict[str, np.ndarray], sr: int, target_lufs: float = -14.0) -> tuple[np.ndarray, float, float]:
    """The stems summed at GAINS_DB, compressed, gained to `target_lufs` and limited, with the fades: (audio, LUFS,
    the limiter's deepest gain reduction in dB). Where the target would take more than MAX_LIMIT_DB of limiting, the
    score is left that much quieter."""
    mix = sum(stems[k] * 10 ** (GAINS_DB[k] / 20) for k in stems)
    mix = _compress(mix, sr)
    n = len(mix)
    fade_out = min(2.0, n / sr / 4)
    env = np.ones(n)
    fi, fo = min(n, int(0.005 * sr)), min(n, int(fade_out * sr))
    env[:fi] = np.linspace(0, 1, fi)
    env[n - fo:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo))
    mix = mix * env[:, None]
    gain = target_lufs - loudness(mix, sr)
    for _ in range(5):
        out, lim = limit(mix * 10 ** (gain / 20), sr)
        if lim > MAX_LIMIT_DB + 0.05:  # back off: the score stays quieter rather than squashed
            gain -= lim - MAX_LIMIT_DB
            continue
        got = loudness(out, sr)
        step = target_lufs - got
        if abs(step) <= 0.3 or (step > 0 and lim >= MAX_LIMIT_DB - 0.05):
            return out.astype(np.float32), got, lim
        gain += step
    out, lim = limit(mix * 10 ** (gain / 20), sr)
    return out.astype(np.float32), loudness(out, sr), lim


def render(grid: Grid, style: str = "pulse", seed: int = 1, phrase: int = 8, target_lufs: float = -14.0,
           sr: int = SR) -> Score:
    stems, on, secs = synthesize(grid, style, seed, phrase, sr)
    audio, lufs, lim = master(stems, sr, target_lufs)
    mixed = {k: v * 10 ** (GAINS_DB[k] / 20) for k, v in stems.items()}
    return Score(audio, mixed, on, secs, grid, lufs, lim)


# ---------------------------------------------------------------- the analysis, in film-beats' schema

def _frames_rms(x: np.ndarray, n: int, sr: int) -> np.ndarray:
    hop = sr // FPS
    y = np.zeros(n * hop)
    m = min(len(x), n * hop)
    y[:m] = (np.asarray(x, np.float64)[:m] ** 2).mean(axis=1) if x.ndim == 2 else np.asarray(x)[:m] ** 2
    return np.sqrt(y.reshape(n, hop).mean(axis=1))


def _norm(x: np.ndarray) -> np.ndarray:
    """0..1, with the loudest 1% clipping at 1 (half the peak, for sparse signals), as film-beats normalises."""
    if not len(x) or float(x.max()) <= 0:
        return np.zeros_like(x)
    return np.clip(x / max(float(np.percentile(x, 99)), 0.5 * float(x.max())), 0.0, 1.0)


def analysis(score: Score, sr: int = SR) -> dict:
    """data/audio.json for the score: the exact grid and sections, and the envelopes and onsets of the stems."""
    g = score.grid
    n = int(math.ceil(g.duration * FPS - 1e-9))
    st = score.stems
    env = lambda *names: _norm(_frames_rms(sum(st[k] for k in names), n, sr))  # noqa: E731
    r3 = lambda a: [round(float(v), 3) for v in a]  # noqa: E731
    r6 = lambda a: [round(float(v), 6) for v in a]  # noqa: E731
    low = env("kick", "boom", "sub")
    return {
        "duration": round(g.duration, 6), "bpm": round(g.bpm, 6), "beat_period": round(g.period, 6),
        "time_signature": g.bpb, "beats": r6(g.beats), "downbeats": r6(g.downbeats),
        "sections": [{"name": s["name"], "start": round(s["start"], 6), "end": round(s["end"], 6)}
                     for s in score.sections],
        "fps": FPS,
        "rms": r3(_norm(_frames_rms(score.audio, n, sr))), "low": r3(low), "mid": r3(env("clap", "pad")),
        "high": r3(env("hat", "tick", "riser")), "vocal": [0.0] * n,
        "drums": r3(env("kick", "clap", "hat", "boom", "tick")), "bass": r3(env("sub", "boom")),
        "other": r3(env("pad", "riser")),
        "onsets": {k: [list(o) for o in v] for k, v in score.onsets.items()},
        "grid_error_ms": 0.0, "grid_fit": 1.0,
    }


# ---------------------------------------------------------------- CLI

def write(score: Score, out: Path, film: config.Film, args: dict, choose: bool = False) -> dict:
    """The WAV, its sidecar, data/audio.json, and the pick in data/music_plan.json when there is none (or `choose`)."""
    fp = film.paths
    write_wav(out, score.audio)
    meta = {"bpm": score.grid.bpm, "sections": [{"name": s["name"], "start": round(s["start"], 6),
                                                 "end": round(s["end"], 6)} for s in score.sections]}
    out.with_suffix(".plan.json").write_text(json.dumps(
        {"format": "temptrack", "plan": None, "meta": meta, "temptrack": args}, indent=1))
    a = analysis(score)
    film.analysis_path.parent.mkdir(parents=True, exist_ok=True)
    film.analysis_path.write_text(json.dumps(a))
    mp_path = fp.data / "music_plan.json"
    mp = json.loads(mp_path.read_text()) if mp_path.exists() else {}
    try:
        rel = fp.rel(out)
    except ValueError:
        rel = None  # a file outside the film is never the pick
    if rel and (choose or not mp.get("chosen")):
        mp = {**mp, "chosen": rel, "chosen_meta": meta}
        mp.pop("edit", None)
        mp.setdefault("variants", [])
        if rel not in mp["variants"]:
            mp["variants"].append(rel)
        mp_path.write_text(json.dumps(mp, indent=1))
    return a


def main(argv=None):
    ap = cli.parser("A procedural temp score on an exact beat grid, with data/audio.json to cut to")
    ap.add_argument("--bpm", type=float, help="tempo (default: pipeline.music.bpm, else audio.bpm, else 120)")
    length = ap.add_mutually_exclusive_group()
    length.add_argument("--bars", type=int, help="how many bars (default: the film's length, else 16)")
    length.add_argument("--duration", type=float, help="seconds, kept exactly (default: the film's length)")
    ap.add_argument("--beats-per-bar", type=int, help="beats per bar (default: audio.beatsPerBar, else 4)")
    ap.add_argument("--offset", type=float, help="the first beat's time in seconds (default: audio.offset, else 0)")
    ap.add_argument("--seed", type=int, help="the score's seed (default: pipeline.music.temp.seed)")
    ap.add_argument("--style", choices=STYLES, help="default: pipeline.music.temp.style")
    ap.add_argument("--phrase", type=int, help="bars per section (default: pipeline.music.temp.phrase)")
    ap.add_argument("--out", type=Path, help="the WAV (default: audio/music/temp.wav)")
    ap.add_argument("--mix", action="store_true", help="also copy it to the film's mix (film.json audio.mix)")
    ap.add_argument("--choose", action="store_true", help="make it the chosen score even if another is chosen")
    a = cli.parse(ap, argv)
    film = config.load()
    temp = film.music["temp"]
    bpm = a.bpm or film.bpm or 120.0
    bpb = a.beats_per_bar or film.beats_per_bar
    offset = a.offset if a.offset is not None else float(film.audio.get("offset", 0.0))
    duration = a.duration
    if a.bars is None and duration is None:
        windows = timeline.load(film.paths.data)
        if windows:
            duration = windows["duration"]
    grid = make_grid(bpm, bpb, a.bars if a.bars is not None else (None if duration else 16), duration, offset)
    style, seed = a.style or temp["style"], a.seed if a.seed is not None else int(temp["seed"])
    phrase = a.phrase or int(temp["phrase"])
    score = render(grid, style, seed, phrase, float(film.mix["lufs"]))
    out = a.out or film.paths.audio / "music" / "temp.wav"
    args = {"style": style, "seed": seed, "bpm": bpm, "beats_per_bar": bpb, "bars": grid.bars, "offset": offset,
            "duration": grid.duration, "phrase": phrase}
    write(score, out, film, args, a.choose)
    if a.mix:
        film.mix_path.parent.mkdir(parents=True, exist_ok=True)
        film.mix_path.write_bytes(out.read_bytes())
    peak = 20 * np.log10(np.abs(score.audio).max() + 1e-12)
    print(f"{out} · {style} · seed {seed} · {bpm:g} BPM · {grid.bars} bars of {bpb} · {grid.duration:.3f} s · "
          f"{score.lufs:.1f} LUFS · peak {peak:.1f} dBFS · limiter ≤ {score.limit_db:.1f} dB")
    for s in score.sections:
        print(f"  {s['name']:<12} bars {s['bar0']:>3}–{s['bar1'] - 1:<3} {s['start']:7.3f} → {s['end']:7.3f}")
    print(f"{film.analysis_path}" + (f" · {film.mix_path}" if a.mix else ""))
