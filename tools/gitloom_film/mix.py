"""Mix the voice over the score. The music ducks under her through a sidechain compressor (about 6–9 dB for a spoken
voice). Mastering is a static gain to −14 LUFS followed by a peak limiter at −2 dBFS, which keeps the true peak under
−1 dBTP, at 48 kHz / 24-bit; it replaces two-pass loudnorm, whose gain riding would flatten the drawn arc. Given the
analysed sections, the score's arc (automate.py) is drawn into the music before it is ducked."""
import argparse
import json
import re
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from .automate import apply, duck_lanes, lanes
from .paths import AUDIO, DATA, OUT, ROOT
from .wav import read_wav, write_wav

TARGET_I = -14.0


def _ff(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", *args], capture_output=True, text=True,
                          check=True)


def premix(vo: Path, music: Path, out: Path, music_gain_db: float = -2.0) -> None:
    graph = ("[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[vo][key];"
             f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={music_gain_db}dB[mu];"
             "[mu][key]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=350:makeup=1[duck];"
             "[duck][vo]amix=inputs=2:normalize=0:duration=longest[mix]")
    _ff(["-i", str(vo), "-i", str(music), "-filter_complex", graph, "-map", "[mix]", "-ar", "48000",
         "-c:a", "pcm_s24le", str(out)])


def measure(path: Path) -> dict:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True, check=True)
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    lra = re.search(r"LRA:\s+(-?[\d.]+) LU", tail)
    return {"I": float(re.search(r"I:\s+(-?[\d.]+) LUFS", tail).group(1)),
            "TP": float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail).group(1)),
            "LRA": float(lra.group(1)) if lra else None}


TP_MAX = -1.0
LIMIT_DBFS = -2.0  # sample-peak ceiling; the true peak lands ~0.3–0.6 dB higher, still under −1.0 dBTP


def loudnorm(src: Path, out: Path) -> dict:
    """Static gain to −14 LUFS, then a peak limiter at −2 dBFS. ffmpeg's loudnorm rides the gain whenever the peaks
    don't fit linearly or the loudness range is over its target, which would flatten the drawn arc; a static gain
    keeps it. `latency=1` makes the limiter's look-ahead delay-free: without it the whole mix would land 5 ms
    (239 samples) late against the picture."""
    gain = TARGET_I - measure(src)["I"]
    for _ in range(3):
        af = (f"volume={gain:.3f}dB,"
              f"alimiter=limit={10 ** (LIMIT_DBFS / 20):.4f}:attack=5:release=50:level=0:latency=1")
        _ff(["-i", str(src), "-af", af, "-ar", "48000", "-c:a", "pcm_s24le", str(out)])
        r = measure(out)
        if abs(r["I"] - TARGET_I) <= 0.2:
            break
        gain += TARGET_I - r["I"]
    return r


def mix(vo: Path, music: Path, out: Path, sections: list[dict] | None = None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        if sections:
            y, sr = read_wav(music, mono=False)
            music = Path(td) / "music-auto.wav"
            write_wav(music, apply(y, sr, *lanes(sections, sr, len(y))), sr)
        pre = Path(td) / "pre.wav"
        premix(vo, music, pre)
        return loudnorm(pre, out)


# ---------------------------------------------------------------- the final mix with stems (Plan 3)

MUSIC_GAIN_DB = -2.0  # the score into the mix, as Plan 1's premix
# Sidechains keyed by her voice. The music ducks 6–9 dB under her (Plan 1's 4:1 with a 20 ms attack and a 350 ms
# release, here in true milliseconds, so the score breathes back between phrases instead of pumping between words);
# its depth is capped so the score never drops out. The effects duck lightly (2:1, about 3 dB): they stay up front.
# Thresholds were set on her processed voice, whose 1 ms-power envelope sits near −18 dBFS mid-phrase: the music's
# median duck while she speaks is 7.6 dB (a quarter of the time at the 9 dB cap), the effects' 3.1 dB.
MUSIC_DUCK = {"thresh_db": -28.0, "ratio": 4.0, "attack_ms": 20.0, "release_ms": 350.0, "knee_db": 9.0,
              "range_db": 9.0}
SFX_DUCK = {"thresh_db": -24.0, "ratio": 2.0, "attack_ms": 20.0, "release_ms": 350.0, "knee_db": 9.0,
            "range_db": 4.0}
DET_BLOCK = 48  # 1 ms detector blocks at 48 kHz
IDLE_GUARD_S = 0.15  # the limiter counts as busy this long either side of a sample over its ceiling


def _stereo(y: np.ndarray, n: int) -> np.ndarray:
    y = np.asarray(y, np.float64)
    y = np.stack([y, y], axis=1) if y.ndim == 1 else y[:, :2]
    out = np.zeros((n, 2))
    out[:min(n, len(y))] = y[:n]
    return out


def sidechain_gain(key: np.ndarray, n: int, sr: int, thresh_db: float, ratio: float, attack_ms: float,
                   release_ms: float, knee_db: float, range_db: float) -> np.ndarray:
    """Per-sample linear gain from a feed-forward compressor keyed by `key` (mono): the key's power in 1 ms blocks,
    smoothed with an attack/release one-pole, its RMS level through a soft-knee gain computer, the reduction capped at
    range_db. The gain is causal (each block's gain reaches the samples after it) and moves linearly in between."""
    k = np.zeros(n)
    k[:min(n, len(key))] = np.asarray(key, np.float64)[:n]
    nb = -(-n // DET_BLOCK)
    pw = np.zeros(nb * DET_BLOCK)
    pw[:n] = k ** 2
    pw = pw.reshape(nb, DET_BLOCK).mean(axis=1)
    bsr = sr / DET_BLOCK
    aa, ar = math.exp(-1 / (attack_ms * 1e-3 * bsr)), math.exp(-1 / (release_ms * 1e-3 * bsr))
    env = np.empty(nb)
    e = 0.0
    for i, p in enumerate(pw.tolist()):
        c = aa if p > e else ar
        e = c * e + (1 - c) * p
        env[i] = e
    over = 10 * np.log10(env + 1e-20) - thresh_db
    slope = 1 - 1 / ratio
    red = np.where(2 * over < -knee_db, 0.0,
                   np.where(2 * np.abs(over) <= knee_db, slope * (over + knee_db / 2) ** 2 / (2 * max(knee_db, 1e-9)),
                            slope * over))
    red = np.minimum(red, range_db)
    centres = (np.arange(nb) + 1) * DET_BLOCK - 1  # a block's gain is known at its last sample
    return (10 ** (-np.interp(np.arange(n), centres, red, left=0.0) / 20)).astype(np.float64)


def _blocks_db(x: np.ndarray, blk: int) -> np.ndarray:
    x = x if x.ndim == 1 else x.mean(axis=1)
    nb = len(x) // blk
    return 10 * np.log10(np.mean(x[:nb * blk].reshape(nb, blk) ** 2, axis=1) + 1e-20)


def duck_depth(music_bus: np.ndarray, ducked: np.ndarray, vo: np.ndarray, sr: int) -> float:
    """The median drop (dB) from music_bus to ducked over the 10 ms blocks where the voice speaks (within 30 dB of
    its loud blocks, its 95th percentile) and the bus is playing."""
    blk = int(0.01 * sr)
    n = min(len(music_bus), len(ducked), len(vo))
    v, a, b = _blocks_db(np.asarray(vo)[:n], blk), _blocks_db(np.asarray(music_bus)[:n], blk), \
        _blocks_db(np.asarray(ducked)[:n], blk)
    speaking = (v > np.percentile(v, 95) - 30) & (v > -70) & (a > -90)
    return float(np.median(a[speaking] - b[speaking])) if speaking.any() else 0.0


def _float_wav(path: Path, y: np.ndarray, sr: int) -> None:
    sf.write(str(path), np.asarray(y, np.float32), sr, subtype="FLOAT")


def buses(vo: Path, music: Path, sfx: Path | None, sections: list[dict] | None = None,
          ducks: list[dict] | None = None, sfx_gain_db: float = 0.0) -> dict:
    """The three buses before the master gain, stereo float64, the voice's length: {vo, music, sfx, music_raw,
    sfx_raw, sr}, where *_raw is the bus before the voice's sidechain (for the duck measurements)."""
    v, sr = read_wav(vo)
    n = len(v)
    m, msr = read_wav(music, mono=False)
    if msr != sr:
        raise ValueError(f"{music}: {msr} Hz, the voice is {sr} Hz")
    if sections:
        m = apply(m, sr, *lanes(sections, sr, len(m)))
    mu = _stereo(m, n) * 10 ** (MUSIC_GAIN_DB / 20)
    if sfx is not None:
        s, ssr = read_wav(sfx, mono=False)
        if ssr != sr:
            raise ValueError(f"{sfx}: {ssr} Hz, the voice is {sr} Hz")
        sx = _stereo(s, n) * 10 ** (sfx_gain_db / 20)
    else:
        sx = np.zeros((n, 2))
    ducks = ducks or []
    every = duck_lanes(ducks, sr, n, "all").astype(np.float64)[:, None]
    mu = mu * duck_lanes(ducks, sr, n, "music").astype(np.float64)[:, None] * every
    sx = sx * every
    gm = sidechain_gain(v, n, sr, **MUSIC_DUCK)[:, None]
    gs = sidechain_gain(v, n, sr, **SFX_DUCK)[:, None]
    return {"vo": _stereo(v, n), "music": mu * gm, "sfx": sx * gs, "music_raw": mu, "sfx_raw": sx, "sr": sr}


def _limiter_busy(pre: np.ndarray, sr: int, ceiling_db: float) -> np.ndarray:
    hot = np.abs(pre).max(axis=1) > 10 ** (ceiling_db / 20) * 0.98
    if not hot.any():
        return hot
    g = int(IDLE_GUARD_S * sr)
    c = np.concatenate([[0], np.cumsum(hot)])
    i = np.arange(len(hot))
    return (c[np.minimum(i + g + 1, len(hot))] - c[np.maximum(i - g, 0)]) > 0


def mix_stems(vo: Path, music: Path, sfx: Path | None, out_dir: Path, sections: list[dict] | None = None,
              ducks: list[dict] | None = None, sfx_gain_db: float = 0.0) -> dict:
    """The final mix: her voice on top, the score (its arc drawn, the sheet's ducks, then ducked under her) and the
    effects (the sheet's 'all' ducks, then a light duck under her), summed, a static gain to −14 LUFS and the −2 dBFS
    limiter (latency=1). Writes out_dir/mix.wav (48 kHz / 24-bit stereo) and the stems out_dir/{vo,music,sfx}.wav
    (48 kHz stereo, 32-bit float): each stem is its bus times the same static gain, before the limiter, so the stems
    sum to the mix wherever the limiter is idle; the voice's peaks run up to a few dB over 0 dBFS there, which a
    24-bit stem would clip."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    b = buses(vo, music, sfx, sections, ducks, sfx_gain_db)
    sr = b["sr"]
    pre = b["vo"] + b["music"] + b["sfx"]
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "pre.wav"
        _float_wav(src, pre, sr)
        gain, ceiling = TARGET_I - measure(src)["I"], LIMIT_DBFS
        for _ in range(6):
            _float_wav(src, pre * 10 ** (gain / 20), sr)
            af = f"alimiter=limit={10 ** (ceiling / 20):.4f}:attack=5:release=50:level=0:latency=1"
            _ff(["-i", str(src), "-af", af, "-ar", "48000", "-c:a", "pcm_s24le", str(out_dir / "mix.wav")])
            r = measure(out_dir / "mix.wav")
            if abs(r["I"] - TARGET_I) <= 0.2 and r["TP"] <= TP_MAX:
                break
            gain += TARGET_I - r["I"]
            if r["TP"] > TP_MAX:  # a sample-peak limiter misses intersample overs on hard transients: lower it
                ceiling -= r["TP"] - TP_MAX + 0.2
    g = 10 ** (gain / 20)
    peaks = {}
    for name in ("vo", "music", "sfx"):
        y = b[name] * g
        peaks[name] = float(20 * np.log10(np.abs(y).max() + 1e-20))
        _float_wav(out_dir / f"{name}.wav", y, sr)  # 32-bit float: pre-limiter peaks run over 0 dBFS
    mixed, _ = read_wav(out_dir / "mix.wav", mono=False)
    stems = sum(read_wav(out_dir / f"{s}.wav", mono=False)[0].astype(np.float64) for s in ("vo", "music", "sfx"))
    idle = ~_limiter_busy(pre * g, sr, ceiling)
    res = (stems - mixed)[idle]
    ref = np.sqrt(np.mean(mixed[idle] ** 2)) if idle.any() else 0.0
    resid = float(20 * np.log10(np.sqrt(np.mean(res ** 2)) / ref + 1e-20)) if ref > 0 else -200.0
    lim = _blocks_db(pre * g, 480) - _blocks_db(mixed, 480)
    return {**r, "duck_db": duck_depth(b["music_raw"], b["music"], b["vo"][:, 0], sr),
            "sfx_duck_db": duck_depth(b["sfx_raw"], b["sfx"], b["vo"][:, 0], sr),
            "stem_residual_db": resid, "gain_db": float(gain), "ceiling_db": float(ceiling), "stem_peak_db": peaks,
            "limiter_max_db": float(lim.max()), "limiter_busy_pct": float(100 * np.mean(lim > 0.5))}


# ---------------------------------------------------------------- the listening proxies (out/review/c5/mix.*)

SFX_NEAR_DB = 6.0  # a word with the effects within this of her voice is flagged


def _rms_db(x: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(np.asarray(x, np.float64) ** 2) + 1e-20))


def review(out_dir: Path, vo_data: dict, sheet: dict | None, png: Path | None = None) -> dict:
    """Per scene: the mix's integrated loudness and sample peak, and the effects against her voice word by word
    (stem RMS over each word; a word with the effects within SFX_NEAR_DB of the voice is flagged). Then the loudest
    effects moments (100 ms windows, at least 1 s apart) with the cues under them, and the honest → proof contrast."""
    out_dir = Path(out_dir)
    mix, sr = read_wav(out_dir / "mix.wav", mono=False)
    st = {k: read_wav(out_dir / f"{k}.wav", mono=False)[0] for k in ("vo", "music", "sfx")}
    cues = (sheet or {}).get("cues", [])
    scenes = []
    with tempfile.TemporaryDirectory() as td:
        for sc in vo_data["scenes"]:
            a, b = int(sc["start"] * sr), int(sc["end"] * sr)
            seg = Path(td) / "seg.wav"
            _float_wav(seg, mix[a:b], sr)
            words = []
            for ln in vo_data["lines"]:
                if ln["scene"] != sc["id"]:
                    continue
                for i, w in enumerate(ln["words"]):
                    wa, wb = int(w["start"] * sr), int(w["end"] * sr)
                    v, f = _rms_db(st["vo"][wa:wb]), _rms_db(st["sfx"][wa:wb])
                    words.append({"line": ln["id"], "i": i, "w": w["w"], "t": w["start"], "sfx_to_vo_db": f - v})
            near = [w for w in words if w["sfx_to_vo_db"] > -SFX_NEAR_DB]
            scenes.append({"id": sc["id"], "start": sc["start"], "end": sc["end"], **{
                "I": measure(seg)["I"], "peak_dbfs": float(20 * np.log10(np.abs(mix[a:b]).max() + 1e-20)),
                "sfx_rms_db": _rms_db(st["sfx"][a:b]), "music_rms_db": _rms_db(st["music"][a:b]),
                "vo_rms_db": _rms_db(st["vo"][a:b]),
                "sfx_to_vo_median_db": float(np.median([w["sfx_to_vo_db"] for w in words])) if words else None,
                "words": len(words), "sfx_near_voice": near,
                "cues": sum(1 for c in cues if sc["start"] <= c["t"] < sc["end"])}})
    win = int(0.1 * sr)
    sx = st["sfx"].mean(axis=1) if st["sfx"].ndim == 2 else st["sfx"]
    nb = len(sx) // win
    blk = 10 * np.log10(np.mean(sx[:nb * win].reshape(nb, win) ** 2, axis=1) + 1e-20)
    mixb = 10 * np.log10(np.mean(mix.mean(axis=1)[:nb * win].reshape(nb, win) ** 2, axis=1) + 1e-20)
    peaks = []
    for i in np.argsort(blk)[::-1]:
        t = (i + 0.5) * win / sr
        if any(abs(t - p["t"]) < 1.0 for p in peaks):
            continue
        under = sorted({f"{c['sound']}@{c['t']:.3f}" for c in cues if -0.15 <= t - c["t"] <= 0.25})
        scene = next((s["id"] for s in vo_data["scenes"] if s["start"] <= t < s["end"]), None)
        peaks.append({"t": round(t, 2), "scene": scene, "sfx_rms_db": float(blk[i]),
                      "sfx_to_mix_db": float(blk[i] - mixb[i]), "cues": under})
        if len(peaks) == 12:
            break
    res = {"scenes": scenes, "sfx_peaks": peaks, "flagged_words": sum(len(s["sfx_near_voice"]) for s in scenes)}
    if png is not None:
        _plot(st, vo_data, sr, png)
    return res


def _plot(st: dict, vo_data: dict, sr: int, png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    hop = int(0.05 * sr)
    curves = {}
    for k, y in st.items():
        y = y.mean(axis=1) if y.ndim == 2 else y
        nb = len(y) // hop
        curves[k] = 10 * np.log10(np.mean(y[:nb * hop].reshape(nb, hop) ** 2, axis=1) + 1e-20)
    tt = (np.arange(len(curves["vo"])) + 0.5) * hop / sr
    sc = vo_data["scenes"]
    fig, axes = plt.subplots(5, 3, figsize=(18, 16), constrained_layout=True)
    colors = {"vo": "#e8e0d4", "music": "#4aad63", "sfx": "#c0392b"}
    for ax, s in zip(axes.flat, sc):
        ax.set_facecolor("#110d10")
        m = (tt >= s["start"] - 0.3) & (tt < s["end"] + 0.3)
        for ln in vo_data["lines"]:
            for w in ln["words"]:
                if s["start"] - 0.3 <= w["start"] < s["end"] + 0.3:
                    ax.axvspan(w["start"], w["end"], color="#3a3236", lw=0)
        for k in ("music", "sfx", "vo"):
            ax.plot(tt[m], np.maximum(curves[k][m], -80), color=colors[k], lw=0.9, label=k)
        for x in (s["start"], s["end"]):
            ax.axvline(x, color="#888", lw=0.8, ls="--")
        ax.set_ylim(-70, 0)
        ax.set_title(s["id"])
        ax.grid(alpha=0.15)
    axes.flat[0].legend(loc="lower right", fontsize=8)
    fig.suptitle("stem RMS (50 ms, dBFS) per scene · words shaded · cuts dashed")
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, dpi=80)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description="The final mix: her processed voice, the score's arc ducked under her and "
                                 "the effects, mastered to −14 LUFS, into audio/mix/{mix,vo,music,sfx}.wav")
    ap.add_argument("--music", help="score WAV (default: the chosen variant)")
    ap.add_argument("--no-automation", action="store_true",
                    help="mix the score as it is, without drawing its arc from the analysed sections")
    ap.add_argument("--no-sfx", action="store_true", help="no effects and no sheet ducks (Plan 1's mix)")
    a = ap.parse_args(argv)
    vo = AUDIO / "vo" / "vo-chain.wav"
    if not vo.is_file():
        raise SystemExit(f"{vo} is missing: run film-vo-chain first")
    sfx = None if a.no_sfx else AUDIO / "sfx" / "sfx.wav"
    if sfx is not None and not sfx.is_file():
        raise SystemExit(f"{sfx} is missing: run film-sfx first (or mix with --no-sfx)")
    from .sfx import load_sheet
    sheet = None if a.no_sfx else load_sheet()
    music = ROOT / (a.music or json.loads((DATA / "music_plan.json").read_text())["chosen"])
    sections = None if a.no_automation else json.loads((DATA / "audio.json").read_text())["sections"]
    out = AUDIO / "mix"
    m = mix_stems(vo, music, sfx, out, sections=sections, ducks=(sheet or {}).get("ducks"))
    vo_data = json.loads((DATA / "vo.json").read_text())
    r = review(out, vo_data, sheet, png=OUT / "review" / "c5" / "mix.png")
    report = {"master": m, **r}
    (OUT / "review" / "c5").mkdir(parents=True, exist_ok=True)
    (OUT / "review" / "c5" / "mix.json").write_text(json.dumps(report, indent=1))
    checks = {"loudness": abs(m["I"] - TARGET_I) <= 0.5, "true peak": m["TP"] <= TP_MAX,
              "duck": 6.0 <= m["duck_db"] <= 9.0, "stems": m["stem_residual_db"] <= -30}
    how = ("raw" if a.no_automation else "automated") + (" · no sfx" if a.no_sfx else "")
    print(f"audio/mix/mix.wav · {how} · {m['I']:.1f} LUFS · {m['TP']:.1f} dBTP · LRA {m['LRA']:.1f} LU · "
          f"music duck {m['duck_db']:.1f} dB · sfx duck {m['sfx_duck_db']:.1f} dB · "
          f"stem residual {m['stem_residual_db']:.0f} dB · limiter ≤ {m['limiter_max_db']:.1f} dB "
          f"({m['limiter_busy_pct']:.1f}% of the film)")
    print("scene        LUFS   peak   sfx−vo (median, per word)   flagged")
    for sc in r["scenes"]:
        med = "—" if sc["sfx_to_vo_median_db"] is None else f"{sc['sfx_to_vo_median_db']:6.1f} dB"
        fl = ", ".join(f"{w['line']}:{w['w']} ({w['sfx_to_vo_db']:+.1f})" for w in sc["sfx_near_voice"])
        print(f"{sc['id']:<11} {sc['I']:6.1f} {sc['peak_dbfs']:6.1f}   {med:>10}               {fl}")
    print("out/review/c5/mix.json · out/review/c5/mix.png")
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise SystemExit("⚠ outside target: " + ", ".join(bad))
