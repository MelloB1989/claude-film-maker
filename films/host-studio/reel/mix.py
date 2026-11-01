"""The karma reel's mix (PLAN.md §2, task R5): the score, the effects and the presenters' voices, mastered to -14 LUFS
integrated and -1 dBTP, 48 kHz stereo 24-bit, exactly 65.000 s from frame 0 (R6's cut.py takes it as --mix).

    cd tools && python ../films/host-studio/reel/mix.py                       # the voice from audio/vo/ if it is there
    cd tools && python ../films/host-studio/reel/mix.py --vo-dir DIR          # R4's stems: DIR/vo_him.wav, vo_her.wav
    cd tools && python ../films/host-studio/reel/mix.py --line L1=l1.wav ...  # or single lines, placed on LINES' frames
    cd tools && python ../films/host-studio/reel/mix.py --no-vo               # music and effects only

In: audio/score/score.wav (score.py), audio/sfx/beds.wav and fx.wav (sfx.py), and the voice: R4's per-presenter stems
(65 s, master time 0, each line already on its frame), or line files placed so their first sample lands on the line's
frame. Out: audio/mix/mix.wav, the stems after the master gain (music, voice, beds, fx: they sum to the mix before the
limiter), mix.json (loudness, true peak, the duck under each line) and mix.png.

The balance is set by loudness, not by fixed faders, so a new take of the score or of a line keeps it: the score is
brought to MUSIC_LUFS and the voice to VOICE_LUFS (each integrated, gated: the voice is measured over its speech), the
effects stay as sfx.py leveled them against the score. Under the voice the score ducks 6-9 dB (a sidechain keyed by the
voice: 4:1, 25 ms attack, a 250 ms hold so it does not pump between words, 450 ms release) and the beds about 3 dB;
the one-shots do not duck (they are cued between the lines). Then one static gain to -14 LUFS and a look-ahead peak
limiter to the true-peak ceiling, trimmed until both hold (no loudnorm gain riding: the score's arc stays as drawn).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "tools"))

import shots as S  # noqa: E402
from filmtools.anime.mix import limiter  # noqa: E402
from filmtools.mix import sidechain_gain  # noqa: E402
from filmtools.vochain import loudness, true_peak  # noqa: E402
from filmtools.wav import SR, read_wav, write_wav  # noqa: E402

AUDIO = HERE / "audio"
FPS = S.FPS
SPF = SR // FPS
TOTAL = S.SHOTS[-1].end
N = TOTAL * SPF  # 3 120 000

TARGET_LUFS, TRUE_PEAK = -14.0, -1.0
MUSIC_LUFS = -16.0  # the score alone, before the master gain
VOICE_LUFS = -15.5  # the voice over its speech: ~6-9 LU over the ducked score where it speaks
BEDS_DB, FX_DB = 0.0, 0.0  # sfx.py's levels are already set against a score at MUSIC_LUFS
MUSIC_DUCK = {"thresh_db": -34.0, "ratio": 4.0, "attack_ms": 25.0, "release_ms": 450.0, "knee_db": 9.0,
              "range_db": 8.0, "hold_ms": 250.0}
BEDS_DUCK = {**MUSIC_DUCK, "ratio": 2.0, "range_db": 3.0}

# The lines on the master's clock (R4's measured speech, PLAN.md §2 "Voice lines"; R6's captions use the same):
# name -> (first frame, last frame, who). A line file given with --line lands its first sample on its first frame.
LINES = {
    "L1": (930, 1069, "him"), "L2": (1110, 1141, "him"), "L3": (1158, 1305, "her"),
    "L4a": (1360, 1373, "him"), "L4b": (1386, 1403, "her"),
}


def _stereo(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, np.float64)
    x = np.stack([x, x], axis=1) if x.ndim == 1 else x[:, :2]
    out = np.zeros((N, 2))
    out[:min(N, len(x))] = x[:N]
    return out


def load(path: Path) -> np.ndarray:
    x, sr = read_wav(path, mono=False)
    if sr != SR:
        raise SystemExit(f"{path}: {sr} Hz, the mix is {SR} Hz")
    return _stereo(x)


def voice(vo_dir: Path | None, lines: dict[str, Path]) -> tuple[np.ndarray | None, str]:
    """The voice on the master's clock, and where it came from."""
    if lines:
        v = np.zeros((N, 2))
        for name, p in lines.items():
            if name not in LINES:
                raise SystemExit(f"no line {name!r} (lines: {', '.join(LINES)})")
            x, sr = read_wav(p, mono=True)
            if sr != SR:
                raise SystemExit(f"{p}: {sr} Hz")
            a = LINES[name][0] * SPF
            n = min(len(x), N - a)
            v[a:a + n] += np.asarray(x[:n], np.float64)[:, None]
        return v, "lines " + ", ".join(f"{k}={p}" for k, p in lines.items())
    if vo_dir is not None:
        stems = [vo_dir / "vo_him.wav", vo_dir / "vo_her.wav"]
        if all(p.is_file() for p in stems):
            return sum(load(p) for p in stems), f"stems {vo_dir}/vo_him.wav + vo_her.wav"
        if (vo_dir / "vo.wav").is_file():
            return load(vo_dir / "vo.wav"), f"stem {vo_dir}/vo.wav"
    return None, "none"


def _to(x: np.ndarray, lufs: float) -> tuple[np.ndarray, float]:
    g = lufs - loudness(x, SR)
    return x * 10 ** (g / 20), g


def master(pre: np.ndarray) -> tuple[np.ndarray, float]:
    """A static gain to TARGET_LUFS, then the limiter at a ceiling a little under TRUE_PEAK, trimmed until the
    integrated loudness is within 0.1 LU and the true peak (4x oversampled) under the ceiling."""
    gain = TARGET_LUFS - loudness(pre, SR)
    ceiling = TRUE_PEAK - 0.3
    for _ in range(6):
        out = limiter(pre * 10 ** (gain / 20), ceiling)
        lu = loudness(out, SR)
        tp = max(true_peak(out[:, 0]), true_peak(out[:, 1]))
        if tp > TRUE_PEAK - 0.05:
            ceiling -= tp - (TRUE_PEAK - 0.1)
            continue
        if abs(lu - TARGET_LUFS) <= 0.1:
            break
        gain += TARGET_LUFS - lu
    return out, gain


def duck_report(music_gain: np.ndarray) -> dict:
    """The score's gain reduction under each line: the median and the deepest, in dB."""
    rep = {}
    for name, (f0, f1, who) in LINES.items():
        g = 20 * np.log10(music_gain[f0 * SPF:(f1 + 1) * SPF] + 1e-12)
        rep[name] = {"who": who, "median_db": round(float(np.median(g)), 1), "deepest_db": round(float(g.min()), 1)}
    return rep


def mix(vo_dir: Path | None, lines: dict[str, Path], no_vo: bool = False, png: bool = True) -> dict:
    music, g_music = _to(load(AUDIO / "score" / "score.wav"), MUSIC_LUFS)
    beds = load(AUDIO / "sfx" / "beds.wav") * 10 ** (BEDS_DB / 20)
    fx = load(AUDIO / "sfx" / "fx.wav") * 10 ** (FX_DB / 20)
    v, src = (None, "none (--no-vo)") if no_vo else voice(vo_dir, lines)
    duck = np.ones(N)
    if v is not None:
        v, g_voice = _to(v, VOICE_LUFS)
        key = v.mean(axis=1)
        duck = sidechain_gain(key, N, SR, **MUSIC_DUCK)
        music = music * duck[:, None]
        beds = beds * sidechain_gain(key, N, SR, **BEDS_DUCK)[:, None]
    else:
        v, g_voice = np.zeros((N, 2)), None
    stems = {"music": music, "voice": v, "beds": beds, "fx": fx}
    out, gain = master(sum(stems.values()))
    d = AUDIO / "mix"
    d.mkdir(parents=True, exist_ok=True)
    write_wav(d / "mix.wav", out.astype(np.float32))
    for k, x in stems.items():
        write_wav(d / f"stem-{k}.wav", (x * 10 ** (gain / 20)).astype(np.float32))
    rep = {
        "lufs": round(loudness(out, SR), 2), "true_peak_dbtp": round(max(true_peak(out[:, 0]), true_peak(out[:, 1])), 2),
        "seconds": round(len(out) / SR, 4), "samples": len(out), "master_gain_db": round(gain, 2),
        "voice": src, "score_gain_db": round(g_music, 2), "voice_gain_db": round(g_voice, 2) if g_voice else None,
        "stems_lufs": {k: round(loudness(x * 10 ** (gain / 20), SR), 1) if np.abs(x).max() > 0 else None
                       for k, x in stems.items()},
        "duck": duck_report(duck) if g_voice is not None else None,
        "sections_lufs": sections_loudness(out),
    }
    (d / "mix.json").write_text(json.dumps(rep, indent=1))
    if png:
        plot(stems, gain, out, d / "mix.png")
    return rep


def sections_loudness(out: np.ndarray) -> dict:
    """Each shot's loudness (BS.1770 over the shot), to see the arc: quiet morning, the drop, the voice."""
    return {s.id: round(loudness(out[s.start * SPF:s.end * SPF], SR), 1) for s in S.SHOTS}


def plot(stems: dict, gain: float, out: np.ndarray, png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(18, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    hop = SR // 20

    def lev(x):
        m = x.mean(axis=1) if x.ndim == 2 else x
        nb = len(m) // hop
        return np.arange(nb) / 20, 20 * np.log10(np.sqrt(np.mean(m[:nb * hop].reshape(nb, hop) ** 2, axis=1)) + 1e-9)
    for k, x in stems.items():
        if np.abs(x).max() > 0:
            ax.plot(*lev(x * 10 ** (gain / 20)), lw=0.8, label=k)
    ax.plot(*lev(out), lw=0.5, color="k", alpha=0.5, label="mix")
    for s in S.SHOTS:
        ax.axvline(s.start / FPS, color="k", alpha=0.2, lw=0.6)
        ax.text(s.start / FPS + 0.1, -4, s.id, fontsize=7)
    for name, (f0, f1, who) in LINES.items():
        ax.axvspan(f0 / FPS, (f1 + 1) / FPS, color="C1" if who == "him" else "C4", alpha=0.08)
        ax.text(f0 / FPS, -70, name, fontsize=7)
    ax.set_ylim(-75, 0)
    ax.set_ylabel("RMS dBFS (50 ms)")
    ax.legend(loc="lower left", ncol=5, fontsize=8)
    ax.set_title("karma reel mix: stems after the master gain; shots and voice lines marked")
    # short-term loudness (3 s), BS.1770, every 0.5 s
    ts = np.arange(0, TOTAL / FPS - 3, 0.5)
    st = [loudness(out[int(t * SR):int((t + 3) * SR)], SR) for t in ts]
    ax2.plot(ts + 1.5, st, lw=1)
    ax2.axhline(TARGET_LUFS, color="r", lw=0.6)
    ax2.set_ylabel("short-term LUFS")
    ax2.set_ylim(-40, -6)
    ax2.set_xlabel("s")
    fig.tight_layout()
    fig.savefig(png, dpi=90)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vo-dir", type=Path, default=AUDIO / "vo", help="R4's stems (vo_him.wav, vo_her.wav)")
    ap.add_argument("--line", action="append", default=[], help="NAME=path, a line placed on its frame")
    ap.add_argument("--no-vo", action="store_true")
    a = ap.parse_args(argv)
    lines = dict(s.split("=", 1) for s in a.line)
    rep = mix(a.vo_dir, {k: Path(v) for k, v in lines.items()}, a.no_vo)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
