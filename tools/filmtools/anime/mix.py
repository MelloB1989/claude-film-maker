"""film-anime-mix: an anime short's sound, mixed: dialogue, the score's cues, beds of ambience and cued effects.

The sheet is films/<id>/data/mix.json:

    { "target_lufs": -16, "true_peak": -1,
      "dialogue": { "gain_db": 0, "room_db": -24 },              the stem from film-anime-dialogue, a little air on it
      "music": { "gain_db": -7, "keys": [[t, dB], ...], "duck_db": 7 },   the score's cues (film-anime-score), keyed over
                                                                 film time and ducked under the dialogue
      "beds": [{ "sound", "from", "to", "gain_db", "keys": [[t, dB], ...], "lowpass": [[t, Hz], ...], "duck_db": 3 }],
      "cues": [{ "sound", "at", "gain_db", "pan", "reverb_db", "lowpass", "args" }] }

A `sound` is a pick of the film's sound library (film-sfx-lib: audio/sfx/manifest.json), placed so its hit lands on
`at`; or `synth:<kind>` (synth.py), made from `args`. Beds are the library's loops tiled across their window. Keys are
[film s, dB] pairs, linear in dB between them and held past the ends; `lowpass` keys sweep a filter (a world gone
muffled while time stands still). Writes audio/mix/mix.wav (48 kHz stereo, 24-bit, at the target loudness under the
true-peak ceiling) and the stems beside it (dialogue, music, ambience, effects, before the master gain).

    uv run film-anime-mix --film <id> [--png out.png]
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import maximum_filter1d
from scipy.signal import butter, lfilter, lfilter_zi, sosfilt

from .. import cli, paths
from ..mix import sidechain_gain
from ..sfx import pan_gains, tile
from ..vochain import loudness, plate, true_peak
from ..wav import read_wav, write_wav
from . import synth

SR = 48000


def keyed(keys: list[list[float]] | None, n: int, default: float = 0.0) -> np.ndarray:
    """Per-sample values from [t, v] keys (linear between, held past the ends)."""
    if not keys:
        return np.full(n, default)
    k = sorted(keys)
    t = np.array([a for a, _ in k]) * SR
    v = np.array([b for _, b in k], dtype=np.float64)
    return np.interp(np.arange(n), t, v)


def db(x: np.ndarray | float) -> np.ndarray | float:
    return 10 ** (np.asarray(x) / 20)


def swept_lowpass(x: np.ndarray, cutoff: np.ndarray, blk: int = 512) -> np.ndarray:
    """A 2-pole low-pass whose cutoff follows `cutoff` (Hz per sample), block by block with its state carried over;
    above 18 kHz the block passes untouched."""
    y = np.empty_like(x)
    zi = None
    for i in range(0, len(x), blk):
        seg = x[i:i + blk]
        fc = float(cutoff[min(i + blk // 2, len(cutoff) - 1)])
        if fc >= 18000:
            y[i:i + blk] = seg
            zi = None
            continue
        b, a = butter(2, max(40.0, fc), "low", fs=SR)
        if zi is None:
            zi = lfilter_zi(b, a)[:, None] * seg[:1]
        y[i:i + blk], zi = lfilter(b, a, seg, axis=0, zi=zi)
    return y


class Library:
    """The film's sound library picks and the synth sounds, decoded once each."""

    def __init__(self, fp):
        self.lib = fp.audio / "sfx" / "lib"
        man = fp.audio / "sfx" / "manifest.json"
        self.picks = json.loads(man.read_text())["picks"] if man.is_file() else {}
        self.cache: dict[str, tuple[np.ndarray, float]] = {}

    def get(self, sound: str, args: dict | None = None) -> tuple[np.ndarray, float]:
        """(mono samples, where its hit is in s)."""
        key = sound + json.dumps(args or {}, sort_keys=True)
        if key not in self.cache:
            if sound.startswith("synth:"):
                self.cache[key] = (synth.make(sound[6:], **(args or {})).astype(np.float64), 0.0)
            else:
                p = self.picks.get(sound)
                if not p:
                    raise SystemExit(f"no sound {sound!r} in the library's picks (film-sfx-lib gen)")
                x, sr = read_wav(self.lib / p["wav"], mono=True)
                if sr != SR:
                    raise SystemExit(f"{p['wav']}: {sr} Hz")
                self.cache[key] = (x.astype(np.float64), float(p.get("hit_s") or 0.0))
        return self.cache[key]


def place(bus: np.ndarray, x: np.ndarray, start: float, pan: float = 0.0, gain: float = 1.0) -> None:
    a = int(round(start * SR))
    l, r = pan_gains(pan)
    lo, hi = max(0, a), min(len(bus), a + len(x))
    if hi <= lo:
        return
    seg = x[lo - a:hi - a] * gain
    bus[lo:hi, 0] += seg * l * math.sqrt(2)
    bus[lo:hi, 1] += seg * r * math.sqrt(2)


def limiter(x: np.ndarray, ceiling_db: float, look_ms: float = 1.5, release_ms: float = 90.0) -> np.ndarray:
    """A look-ahead peak limiter on the 4x-oversampled peak estimate: the gain needed to keep every sample under the
    ceiling, spread over the look-ahead window before the peak and released smoothly after it."""
    ceiling = db(ceiling_db)
    peak = np.abs(x).max(axis=1) * 1.06  # inter-sample headroom
    la = max(1, int(look_ms * 1e-3 * SR))
    env = maximum_filter1d(peak, size=2 * la + 1)
    g = np.minimum(1.0, ceiling / np.maximum(env, 1e-9))
    # release: the gain recovers no faster than release_ms per 1/e
    rel = math.exp(-1 / (release_ms * 1e-3 * SR))
    out = np.empty_like(g)
    cur = 1.0
    for i, v in enumerate(g):
        cur = v if v < cur else v + (cur - v) * rel
        out[i] = cur
    # smooth the attack edge over the look-ahead so it never steps (edge-padded: the ends are not faded)
    k = np.hanning(2 * la + 1)
    smooth = np.convolve(np.pad(out, la, mode="edge"), k / k.sum(), mode="valid")
    out = np.minimum(out, smooth)
    return x * out[:, None]


def mix(png: Path | None = None) -> dict:
    fp = paths.current()
    sheet = json.loads((fp.data / "mix.json").read_text())
    tl = json.loads((fp.data / "timeline.json").read_text())
    n = int(round(tl["duration"] * SR))
    lib = Library(fp)

    # dialogue
    dlg_p = fp.audio / "dialogue" / "dialogue.wav"
    d, _ = read_wav(dlg_p, mono=True)
    dd = np.zeros(n)
    dd[:min(n, len(d))] = d[:n]
    ds = sheet.get("dialogue", {})
    dd = dd * db(ds.get("gain_db", 0))
    if ds.get("room_db") is not None:
        dd = plate(dd, SR, rt60=0.7, predelay_ms=12, lo=300, hi=6000, wet_db=ds["room_db"], seed=5)
    dialogue = np.stack([dd, dd], axis=1)

    # music: the score's cues at their times, keyed, ducked under the dialogue
    ms = sheet.get("music", {})
    music = np.zeros((n, 2))
    score = json.loads((fp.data / "score.json").read_text())
    for name, cue in score["cues"].items():
        wav = fp.audio / "score" / f"{name}.wav"
        if not wav.is_file():
            print(f"(score cue {name} not made: skipped)")
            continue
        x, _ = read_wav(wav, mono=False)
        x = x if x.ndim == 2 else np.stack([x, x], axis=1)
        a = int(round(cue["at"] * SR))
        hi = min(n, a + len(x))
        music[a:hi] += x[:hi - a]
    music *= db(ms.get("gain_db", -7) + keyed(ms.get("keys"), n))[:, None]
    duck = sidechain_gain(dd, n, SR, thresh_db=-32, ratio=4, attack_ms=25, release_ms=450, knee_db=9,
                          range_db=ms.get("duck_db", 7), hold_ms=250)
    music *= duck[:, None]

    # beds
    amb = np.zeros((n, 2))
    for b in sheet.get("beds", []):
        x, _ = lib.get(b["sound"])
        a, z = int(b["from"] * SR), min(n, int(b["to"] * SR))
        bed = tile(x, z - a, SR)
        g = db(b.get("gain_db", 0) + keyed(b.get("keys"), n)[a:z])
        seg = np.stack([bed * g, bed * g], axis=1)
        if b.get("lowpass"):
            seg = swept_lowpass(seg, keyed(b["lowpass"], n, 20000)[a:z])
        if b.get("duck_db"):
            seg *= sidechain_gain(dd, n, SR, thresh_db=-32, ratio=3, attack_ms=40, release_ms=600, knee_db=9,
                                  range_db=b["duck_db"], hold_ms=300)[a:z, None]
        amb[a:z] += seg

    # cued effects
    fx = np.zeros((n, 2))
    for c in sheet.get("cues", []):
        x, hit = lib.get(c["sound"], c.get("args"))
        if c.get("lowpass"):
            x = sosfilt(butter(2, c["lowpass"], "low", fs=SR, output="sos"), x)
        if c.get("reverb_db") is not None:
            x = plate(np.concatenate([x, np.zeros(int(2.5 * SR))]), SR, rt60=2.4, predelay_ms=20, lo=200, hi=7000,
                      wet_db=c["reverb_db"], seed=9)
        place(fx, x, c["at"] - hit, c.get("pan", 0.0), db(c.get("gain_db", 0)))

    stems = {"dialogue": dialogue, "music": music, "ambience": amb, "effects": fx}
    pre = sum(stems.values())
    target, tp = sheet.get("target_lufs", -16.0), sheet.get("true_peak", -1.0)
    gain = target - loudness(pre, SR)
    out = limiter(pre * db(gain), tp - 0.3)
    # one trim pass: the limiter takes a little loudness off the loudest moments
    out *= db(target - loudness(out, SR))
    out = limiter(out, tp - 0.3)
    d_out = fp.audio / "mix"
    d_out.mkdir(parents=True, exist_ok=True)
    write_wav(d_out / "mix.wav", out, SR)
    for k, v in stems.items():
        write_wav(d_out / f"stem-{k}.wav", v * db(gain), SR)
    rep = {"lufs": round(loudness(out, SR), 2), "true_peak_db": round(true_peak(out.mean(axis=1)), 2),
           "master_gain_db": round(gain, 2), "seconds": round(n / SR, 3),
           "stems_lufs": {k: round(loudness(v * db(gain), SR), 1) for k, v in stems.items()}}
    (d_out / "mix.json").write_text(json.dumps(rep, indent=1))
    if png:
        plot(stems, gain, tl, png)
    return rep


def plot(stems: dict, gain: float, tl: dict, png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(18, 5))
    hop = SR // 10
    for k, v in stems.items():
        m = (v * db(gain)).mean(axis=1)
        nb = len(m) // hop
        r = np.sqrt(np.mean(m[: nb * hop].reshape(nb, hop) ** 2, axis=1) + 1e-12)
        ax.plot(np.arange(nb) / 10, 20 * np.log10(r), label=k, lw=0.9)
    for s in tl["scenes"]:
        ax.axvline(s["start"], color="k", alpha=0.15, lw=0.6)
        ax.text(s["start"] + 0.1, -12, s["id"], fontsize=6, rotation=90, va="top")
    ax.set_ylim(-70, -5)
    ax.set_xlabel("film s")
    ax.set_ylabel("RMS dBFS (100 ms)")
    ax.legend(loc="lower left")
    fig.tight_layout()
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, dpi=110)


def main(argv: list[str] | None = None) -> None:
    ap = cli.parser(description="Mix an anime short: dialogue, score cues, ambience beds and effects.")
    ap.add_argument("--png", type=Path, help="a plot of the stems' levels over the film")
    a = cli.parse(ap, argv)
    print(json.dumps(mix(a.png), indent=1))
