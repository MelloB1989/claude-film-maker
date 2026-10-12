"""Mix the voice over the score and the effects. The music ducks under the voice through a sidechain compressor
(about 6–9 dB for a spoken voice). Mastering is a static gain to the loudness target (film.json pipeline.mix.lufs,
default −14 LUFS) followed by a peak limiter (limit_dbfs, default −2 dBFS) that keeps the true peak under true_peak
(−1 dBTP), at 48 kHz / 24-bit; it replaces two-pass loudnorm, whose gain riding would flatten the drawn arc. Given the
analysed sections, the score's arc (automate.py) is drawn into the music before it is ducked."""
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from . import cli, config, timeline
from .automate import FADE_OUT, apply, duck_lanes, lanes, rules_from
from .wav import read_wav, write_wav

DEFAULTS = config.PIPELINE_DEFAULTS["mix"]
TARGET_I = DEFAULTS["lufs"]
TP_MAX = DEFAULTS["true_peak"]
LIMIT_DBFS = DEFAULTS["limit_dbfs"]  # sample-peak ceiling; the true peak lands ~0.3–0.6 dB higher
MUSIC_GAIN_DB = DEFAULTS["music_gain_db"]
MUSIC_DUCK = config.MUSIC_DUCK
SFX_DUCK = config.SFX_DUCK
DET_BLOCK = 48  # 1 ms detector blocks at 48 kHz
IDLE_GUARD_S = 0.15  # the limiter counts as busy this long either side of a sample over its ceiling


def settings_of(settings: dict | None) -> dict:
    """pipeline.mix over its defaults (the ducks merge key by key)."""
    s = {**DEFAULTS, **(settings or {})}
    s["music_duck"] = {**MUSIC_DUCK, **(settings or {}).get("music_duck", {})}
    s["sfx_duck"] = {**SFX_DUCK, **(settings or {}).get("sfx_duck", {})}
    return s


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


def loudnorm(src: Path, out: Path, target: float = TARGET_I, limit_dbfs: float = LIMIT_DBFS) -> dict:
    """Static gain to `target` LUFS, then a peak limiter at `limit_dbfs`. ffmpeg's loudnorm rides the gain whenever
    the peaks don't fit linearly or the loudness range is over its target, which would flatten the drawn arc; a static
    gain keeps it. `latency=1` makes the limiter's look-ahead delay-free: without it the whole mix would land 5 ms
    (239 samples) late against the picture."""
    gain = target - measure(src)["I"]
    for _ in range(3):
        af = (f"volume={gain:.3f}dB,"
              f"alimiter=limit={10 ** (limit_dbfs / 20):.4f}:attack=5:release=50:level=0:latency=1")
        _ff(["-i", str(src), "-af", af, "-ar", "48000", "-c:a", "pcm_s24le", str(out)])
        r = measure(out)
        if abs(r["I"] - target) <= 0.2:
            break
        gain += target - r["I"]
    return r


def mix(vo: Path, music: Path, out: Path, sections: list[dict] | None = None, rules: dict | None = None,
        fade_out: float = FADE_OUT, settings: dict | None = None) -> dict:
    """A quick two-stem mix (ffmpeg's sidechain), mastered like the final one: the voice over the score."""
    s = settings_of(settings)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        if sections:
            y, sr = read_wav(music, mono=False)
            music = Path(td) / "music-auto.wav"
            write_wav(music, apply(y, sr, *lanes(sections, sr, len(y), rules, fade_out)), sr)
        pre = Path(td) / "pre.wav"
        premix(vo, music, pre)
        return loudnorm(pre, out, s["lufs"], s["limit_dbfs"])


# ---------------------------------------------------------------- the final mix with stems

# The score sits at music_gain_db (−4 dB) into the mix: ~6 LU or more under a processed voice's words, while between
# lines the arc plays as drawn (the master gain barely moves: the voice carries the loudness).
# Sidechains keyed by the voice (config.MUSIC_DUCK / SFX_DUCK). The music ducks 6–9 dB under it (4:1, a 20 ms attack,
# a 350 ms release and a 250 ms hold, so the score breathes back between phrases instead of pumping in the breaths
# between words); its depth is capped so the score never drops out. The effects duck lightly (2:1, about 3 dB): they
# stay up front. The thresholds suit a processed voice whose 1 ms-power envelope (held through breaths) sits near
# −16 dBFS mid-phrase.


def _stereo(y: np.ndarray, n: int) -> np.ndarray:
    y = np.asarray(y, np.float64)
    y = np.stack([y, y], axis=1) if y.ndim == 1 else y[:, :2]
    out = np.zeros((n, 2))
    out[:min(n, len(y))] = y[:n]
    return out


def sidechain_gain(key: np.ndarray, n: int, sr: int, thresh_db: float, ratio: float, attack_ms: float,
                   release_ms: float, knee_db: float, range_db: float, hold_ms: float = 0.0) -> np.ndarray:
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
    hold = int(round(hold_ms * 1e-3 * bsr))
    since = hold + 1
    for i, p in enumerate(pw.tolist()):
        if p > e:
            e, since = aa * e + (1 - aa) * p, 0
        else:
            since += 1
            if since > hold:  # a breath shorter than the hold keeps the duck where the word left it
                e = ar * e + (1 - ar) * p
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


def buses(vo: Path | None, music: Path, sfx: Path | None, sections: list[dict] | None = None,
          ducks: list[dict] | None = None, sfx_gain_db: float | None = None, rules: dict | None = None,
          fade_out: float = FADE_OUT, settings: dict | None = None, duration: float | None = None) -> dict:
    """The three buses before the master gain, stereo float64: {vo, music, sfx, music_raw, sfx_raw, sr}, where *_raw
    is the bus before the voice's sidechain (for the duck measurements). They last `duration` seconds (the film's),
    else as long as the voice, else (no voice: `vo` None) as long as the music."""
    s = settings_of(settings)
    m, sr = read_wav(music, mono=False)
    if vo is not None:
        v, vsr = read_wav(vo)
        if vsr != sr:
            raise ValueError(f"{music}: {sr} Hz, the voice is {vsr} Hz")
    else:
        v = np.zeros(len(m))
    n = int(round(duration * sr)) if duration is not None else len(v)
    v = np.pad(v, (0, max(0, n - len(v))))[:n]
    if sections:
        m = apply(m, sr, *lanes(sections, sr, len(m), rules, fade_out))
    mu = _stereo(m, n) * 10 ** (s["music_gain_db"] / 20)
    if sfx is not None:
        x, ssr = read_wav(sfx, mono=False)
        if ssr != sr:
            raise ValueError(f"{sfx}: {ssr} Hz, the voice is {sr} Hz")
        gain = s["sfx_gain_db"] if sfx_gain_db is None else sfx_gain_db
        sx = _stereo(x, n) * 10 ** (gain / 20)
    else:
        sx = np.zeros((n, 2))
    ducks = ducks or []
    every = duck_lanes(ducks, sr, n, "all").astype(np.float64)[:, None]
    mu = mu * duck_lanes(ducks, sr, n, "music").astype(np.float64)[:, None] * every
    sx = sx * every
    gm = sidechain_gain(v, n, sr, **s["music_duck"])[:, None]
    gs = sidechain_gain(v, n, sr, **s["sfx_duck"])[:, None]
    return {"vo": _stereo(v, n), "music": mu * gm, "sfx": sx * gs, "music_raw": mu, "sfx_raw": sx, "sr": sr}


def _limiter_busy(pre: np.ndarray, sr: int, ceiling_db: float) -> np.ndarray:
    hot = np.abs(pre).max(axis=1) > 10 ** (ceiling_db / 20) * 0.98
    if not hot.any():
        return hot
    g = int(IDLE_GUARD_S * sr)
    c = np.concatenate([[0], np.cumsum(hot)])
    i = np.arange(len(hot))
    return (c[np.minimum(i + g + 1, len(hot))] - c[np.maximum(i - g, 0)]) > 0


def mix_stems(vo: Path | None, music: Path, sfx: Path | None, out_dir: Path, sections: list[dict] | None = None,
              ducks: list[dict] | None = None, sfx_gain_db: float | None = None, rules: dict | None = None,
              fade_out: float = FADE_OUT, settings: dict | None = None, duration: float | None = None) -> dict:
    """The final mix: the voice on top, the score (its arc drawn, the sheet's ducks, then ducked under the voice) and
    the effects (the sheet's 'all' ducks, then a light duck under the voice), summed, a static gain to the loudness
    target and the limiter (latency=1). Writes out_dir/mix.wav (48 kHz / 24-bit stereo) and the stems
    out_dir/{vo,music,sfx}.wav (48 kHz stereo, 32-bit float): each stem is its bus times the same static gain, before
    the limiter, so the stems sum to the mix wherever the limiter is idle; the voice's peaks run up to a few dB over
    0 dBFS there, which a 24-bit stem would clip."""
    s = settings_of(settings)
    target, tp_max = s["lufs"], s["true_peak"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    b = buses(vo, music, sfx, sections, ducks, sfx_gain_db, rules, fade_out, s, duration)
    sr = b["sr"]
    pre = b["vo"] + b["music"] + b["sfx"]
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "pre.wav"
        _float_wav(src, pre, sr)
        gain, ceiling = target - measure(src)["I"], s["limit_dbfs"]
        for _ in range(6):
            _float_wav(src, pre * 10 ** (gain / 20), sr)
            af = f"alimiter=limit={10 ** (ceiling / 20):.4f}:attack=5:release=50:level=0:latency=1"
            _ff(["-i", str(src), "-af", af, "-ar", "48000", "-c:a", "pcm_s24le", str(out_dir / "mix.wav")])
            r = measure(out_dir / "mix.wav")
            if abs(r["I"] - target) <= 0.05 and r["TP"] <= tp_max:
                break
            gain += target - r["I"]
            if r["TP"] > tp_max:  # a sample-peak limiter misses intersample overs on hard transients: lower it
                ceiling -= r["TP"] - tp_max + 0.2
    g = 10 ** (gain / 20)
    peaks = {}
    for name in ("vo", "music", "sfx"):
        y = b[name] * g
        peaks[name] = float(20 * np.log10(np.abs(y).max() + 1e-20))
        _float_wav(out_dir / f"{name}.wav", y, sr)  # 32-bit float: pre-limiter peaks run over 0 dBFS
    mixed, _ = read_wav(out_dir / "mix.wav", mono=False)
    stems = sum(read_wav(out_dir / f"{k}.wav", mono=False)[0].astype(np.float64) for k in ("vo", "music", "sfx"))
    idle = ~_limiter_busy(pre * g, sr, ceiling)
    res = (stems - mixed)[idle]
    ref = np.sqrt(np.mean(mixed[idle] ** 2)) if idle.any() else 0.0
    resid = float(20 * np.log10(np.sqrt(np.mean(res ** 2)) / ref + 1e-20)) if ref > 0 else -200.0
    lim = _blocks_db(pre * g, 480) - _blocks_db(mixed, 480)
    return {**r, "duck_db": duck_depth(b["music_raw"], b["music"], b["vo"][:, 0], sr),
            "sfx_duck_db": duck_depth(b["sfx_raw"], b["sfx"], b["vo"][:, 0], sr),
            "stem_residual_db": resid, "gain_db": float(gain), "ceiling_db": float(ceiling), "stem_peak_db": peaks,
            "limiter_max_db": float(lim.max()), "limiter_busy_pct": float(100 * np.mean(lim > 0.5))}


# ---------------------------------------------------------------- the listening proxies (out/<id>/review/mix.*)

SFX_NEAR_DB = 6.0  # a word with the effects within this of the voice is flagged


def _rms_db(x: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(np.asarray(x, np.float64) ** 2) + 1e-20))


def _kweight(y: np.ndarray, sr: int) -> np.ndarray:
    from .vochain import _K1, _K2, _filt
    assert sr == 48000, "the K-weighting coefficients are for 48 kHz"
    y = np.asarray(y, np.float64)
    return _filt(_filt(y.mean(axis=1) if y.ndim == 2 else y, _K1), _K2)


def review(out_dir: Path, vo_data: dict, sheet: dict | None, png: Path | None = None,
           sections: list[dict] | None = None, scenes: list[dict] | None = None) -> dict:
    """Per scene (`scenes`, default vo_data's): the mix's integrated loudness and sample peak, and the effects
    against the voice word by word (stem RMS over each word; a word with the effects within SFX_NEAR_DB of the voice
    is flagged) and the score against the words as loudness (K-weighted, LU). Then the loudest effects moments
    (100 ms windows, at least 1 s apart) with the cues under them, and per music section bed_I: the score and effects
    without the voice, the arc as drawn."""
    out_dir = Path(out_dir)
    scenes = vo_data["scenes"] if scenes is None else scenes
    mix, sr = read_wav(out_dir / "mix.wav", mono=False)
    st = {k: read_wav(out_dir / f"{k}.wav", mono=False)[0] for k in ("vo", "music", "sfx")}
    cues = (sheet or {}).get("cues", [])
    kw = {k: _kweight(st[k], sr) for k in ("vo", "music")}  # the words against the score, as loudness
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for sc in scenes:
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
                    words.append({"line": ln["id"], "i": i, "w": w["w"], "t": w["start"], "sfx_to_vo_db": f - v,
                                  "music_to_vo_lu": _rms_db(kw["music"][wa:wb]) - _rms_db(kw["vo"][wa:wb])})
            near = [w for w in words if w["sfx_to_vo_db"] > -SFX_NEAR_DB]
            bed = Path(td) / "bed.wav"
            _float_wav(bed, st["music"][a:b] + st["sfx"][a:b], sr)
            rows.append({"id": sc["id"], "start": sc["start"], "end": sc["end"], **{
                "I": measure(seg)["I"], "bed_I": measure(bed)["I"],
                "peak_dbfs": float(20 * np.log10(np.abs(mix[a:b]).max() + 1e-20)),
                "sfx_rms_db": _rms_db(st["sfx"][a:b]), "music_rms_db": _rms_db(st["music"][a:b]),
                "vo_rms_db": _rms_db(st["vo"][a:b]),
                "sfx_to_vo_median_db": float(np.median([w["sfx_to_vo_db"] for w in words])) if words else None,
                "music_to_vo_median_lu": float(np.median([w["music_to_vo_lu"] for w in words])) if words else None,
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
        scene = next((s["id"] for s in scenes if s["start"] <= t < s["end"]), None)
        peaks.append({"t": round(t, 2), "scene": scene, "sfx_rms_db": float(blk[i]),
                      "sfx_to_mix_db": float(blk[i] - mixb[i]), "cues": under})
        if len(peaks) == 12:
            break
    arc = []
    with tempfile.TemporaryDirectory() as td:
        for sec in sections or []:
            a, b = int(sec["start"] * sr), int(sec["end"] * sr)
            bed = Path(td) / "bed.wav"
            _float_wav(bed, st["music"][a:b] + st["sfx"][a:b], sr)
            arc.append({"name": sec["name"], "start": sec["start"], "end": sec["end"], "bed_I": measure(bed)["I"]})
    res = {"scenes": rows, "sections": arc, "sfx_peaks": peaks,
           "flagged_words": sum(len(s["sfx_near_voice"]) for s in rows)}
    if png is not None:
        _plot(st, vo_data, scenes, sr, png)
    return res


def _plot(st: dict, vo_data: dict, scenes: list[dict], sr: int, png: Path) -> None:
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
    cols = min(3, max(1, len(scenes)))
    rows = max(1, math.ceil(len(scenes) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 3.2 * rows), constrained_layout=True, squeeze=False)
    colors = {"vo": "#e6e6e6", "music": "#4c9be8", "sfx": "#e8804c"}
    for ax in axes.flat[len(scenes):]:
        ax.set_visible(False)
    for ax, s in zip(axes.flat, scenes):
        ax.set_facecolor("#141414")
        m = (tt >= s["start"] - 0.3) & (tt < s["end"] + 0.3)
        for ln in vo_data["lines"]:
            for w in ln["words"]:
                if s["start"] - 0.3 <= w["start"] < s["end"] + 0.3:
                    ax.axvspan(w["start"], w["end"], color="#383838", lw=0)
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
    ap = cli.parser("The final mix: the processed voice, the score's arc ducked under it and the effects, mastered "
                    "to the film's loudness target, into audio/mix/{mix,vo,music,sfx}.wav")
    ap.add_argument("--music", help="score WAV, relative to the film folder (default: the chosen score)")
    ap.add_argument("--no-automation", action="store_true",
                    help="mix the score as it is, without drawing its arc from the analysed sections")
    ap.add_argument("--no-sfx", action="store_true", help="no effects and no sheet ducks")
    ap.add_argument("--no-vo", action="store_true", help="no voice: the score (and effects) over the film's length")
    a = cli.parse(ap, argv)
    film = config.load()
    fp, s = film.paths, settings_of(film.mix)
    vo = None if a.no_vo else fp.audio / "vo" / "vo-chain.wav"
    if vo is not None and not vo.is_file():
        raise SystemExit(f"{vo} is missing: run film-vo-chain first (or mix with --no-vo)")
    sfx = None if a.no_sfx else fp.audio / "sfx" / "sfx.wav"
    if sfx is not None and not sfx.is_file():
        raise SystemExit(f"{sfx} is missing: run film-sfx first (or mix with --no-sfx)")
    from .music import chosen_score, load_plan
    from .sfx import load_sheet
    sheet = None if a.no_sfx else load_sheet()
    rel = a.music or chosen_score(load_plan(), film)
    if not rel or not (fp.dir / rel).is_file():
        raise SystemExit("no score to mix: set 'chosen' in data/music_plan.json or pipeline.music.chosen, run "
                         "film-temptrack, or pass --music")
    music = fp.dir / rel
    analysis = json.loads(film.analysis_path.read_text()) if film.analysis_path.is_file() else None
    if analysis is None and not a.no_automation:
        raise SystemExit("data/audio.json is missing: run film-beats (or mix with --no-automation)")
    sections = None if a.no_automation else analysis["sections"]
    windows = timeline.load(fp.data)
    duration = windows["duration"] if windows else None
    out = film.mix_path.parent
    m = mix_stems(vo, music, sfx, out, sections=sections, ducks=(sheet or {}).get("ducks"),
                  rules=rules_from(film.music), fade_out=float(film.music["fade_out"]), settings=s,
                  duration=duration)
    if film.mix_path.name != "mix.wav":
        film.mix_path.write_bytes((out / "mix.wav").read_bytes())
    lo, hi = s["duck_target_db"]
    checks = {"loudness": abs(m["I"] - s["lufs"]) <= 0.5, "true peak": m["TP"] <= s["true_peak"],
              "stems": m["stem_residual_db"] <= -30}
    if vo is not None:
        checks["duck"] = lo <= m["duck_db"] <= hi
    how = ("raw" if a.no_automation else "automated") + (" · no sfx" if a.no_sfx else "") + \
        (" · no voice" if vo is None else "")
    print(f"{fp.rel(out / 'mix.wav')} · {how} · {m['I']:.1f} LUFS · {m['TP']:.1f} dBTP · LRA {m['LRA']:.1f} LU · "
          f"music duck {m['duck_db']:.1f} dB · sfx duck {m['sfx_duck_db']:.1f} dB · "
          f"stem residual {m['stem_residual_db']:.0f} dB · limiter ≤ {m['limiter_max_db']:.1f} dB "
          f"({m['limiter_busy_pct']:.1f}% of the film)")
    vo_json = fp.data / "vo.json"
    if vo is not None and vo_json.is_file():
        vo_data = json.loads(vo_json.read_text())
        review_dir = fp.out / "review"
        r = review(out, vo_data, sheet, png=review_dir / "mix.png", sections=(analysis or {}).get("sections"),
                   scenes=windows["scenes"] if windows else None)
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "mix.json").write_text(json.dumps({"master": m, **r}, indent=1))
        print("scene        LUFS  bed LUFS  peak   music−vo (LU)  sfx−vo (dB), medians over the words   "
              "sfx within 6 dB of a word")
        for sc in r["scenes"]:
            fmt = lambda k: "     —" if sc[k] is None else f"{sc[k]:6.1f}"  # noqa: E731
            fl = ", ".join(f"{w['line']}:{w['w']} ({w['sfx_to_vo_db']:+.1f})" for w in sc["sfx_near_voice"])
            print(f"{sc['id']:<11} {sc['I']:6.1f}  {sc['bed_I']:6.1f}  {sc['peak_dbfs']:6.1f}   "
                  f"{fmt('music_to_vo_median_lu')}          {fmt('sfx_to_vo_median_db')}"
                  f"                                {fl}")
        print("the arc, score and effects without the voice (LUFS): " +
              " · ".join(f"{x['name']} {x['bed_I']:.1f}" for x in r["sections"]))
        print("loudest effects: " + " · ".join(f"{p['t']:.2f} {p['scene']} ({p['sfx_to_mix_db']:+.1f} dB re mix)"
                                                 for p in r["sfx_peaks"][:5]))
        print(f"{review_dir / 'mix.json'} · {review_dir / 'mix.png'}")
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise SystemExit("⚠ outside target: " + ", ".join(bad))
