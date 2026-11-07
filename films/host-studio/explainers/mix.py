"""The explainers' mix: the voice first, the music bed under it, sidechain-ducked, mastered to -14 LUFS integrated and a
-1 dBTP ceiling, 48 kHz stereo 24-bit, exactly the film's length from frame 0 (composite.py muxes it).

    PYTHONPATH=tools python films/host-studio/explainers/music.py fit --film whatsapp --seed 1   # the bed
    PYTHONPATH=tools python films/host-studio/explainers/mix.py --film whatsapp                  # -> audio/<film>/mix.wav

The balance is set by loudness (the karma reel's method, films/host-studio/reel/mix.py): the voice to VOICE_LUFS over
its speech, the bed to MUSIC_LUFS, the bed ducked under the voice (4:1, 25 ms attack, 250 ms hold, 450 ms release, at
most RANGE dB) so it breathes up in the gaps and at the beat changes; then one static gain and the look-ahead limiter,
trimmed until both targets hold.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "tools"))

from filmtools.anime.mix import limiter  # noqa: E402
from filmtools.mix import sidechain_gain  # noqa: E402
from filmtools.vochain import loudness, true_peak  # noqa: E402
from filmtools.wav import SR, read_wav, write_wav  # noqa: E402

TARGET_LUFS, TRUE_PEAK = -14.0, -1.0
VOICE_LUFS = -15.0   # the voice over its speech
MUSIC_LUFS = -21.0   # a bed: ~6 LU under the voice before the duck, ~12-14 LU under it while he/she speaks
DUCK = {"thresh_db": -34.0, "ratio": 4.0, "attack_ms": 25.0, "release_ms": 450.0, "knee_db": 9.0,
        "range_db": 7.0, "hold_ms": 250.0}


def stereo(x: np.ndarray, n: int) -> np.ndarray:
    x = np.asarray(x, np.float64)
    x = np.stack([x, x], 1) if x.ndim == 1 else x[:, :2]
    out = np.zeros((n, 2))
    out[:min(n, len(x))] = x[:n]
    return out


def master(pre: np.ndarray) -> tuple[np.ndarray, float]:
    gain = TARGET_LUFS - loudness(pre, SR)
    ceiling = TRUE_PEAK - 0.3
    for _ in range(8):
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


def mix(film: str) -> dict:
    d = HERE / "audio" / film
    cues = json.loads((d / "cues.json").read_text())
    n = int(round(cues["duration"] * SR))
    v, sr = read_wav(d / "vo.wav")
    assert sr == SR
    voice = stereo(v, n)
    voice *= 10 ** ((VOICE_LUFS - loudness(voice, SR)) / 20)
    bed, sr = read_wav(d / "bed.flac", mono=False)
    assert sr == SR
    music = stereo(bed, n)
    music *= 10 ** ((MUSIC_LUFS - loudness(music, SR)) / 20)
    duck = sidechain_gain(voice.mean(1), n, SR, **DUCK)
    music *= duck[:, None]
    out, gain = master(voice + music)
    write_wav(d / "mix.wav", out.astype(np.float32))
    write_wav(d / "stem-voice.wav", (voice * 10 ** (gain / 20)).astype(np.float32))
    write_wav(d / "stem-music.wav", (music * 10 ** (gain / 20)).astype(np.float32))
    duck_db = [round(float(np.median(20 * np.log10(duck[int(ln["start"] * SR):int(ln["end"] * SR)] + 1e-12))), 1)
               for ln in cues["lines"]]
    rep = {"film": film, "seconds": round(n / SR, 4), "samples": n,
           "lufs": round(loudness(out, SR), 2),
           "true_peak_dbtp": round(max(true_peak(out[:, 0]), true_peak(out[:, 1])), 2),
           "master_gain_db": round(gain, 2), "voice_lufs": VOICE_LUFS, "music_lufs": MUSIC_LUFS,
           "duck_median_db_per_line": dict(zip([ln["id"] for ln in cues["lines"]], duck_db)),
           "bed": json.loads((d / "bed.json").read_text())}
    (d / "mix.json").write_text(json.dumps(rep, indent=1))
    print(f"{film}: {rep['lufs']} LUFS, {rep['true_peak_dbtp']} dBTP, {rep['seconds']} s, duck median "
          f"{np.median(duck_db):.1f} dB")
    return rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", required=True, choices=["whatsapp", "netflix"])
    mix(ap.parse_args().film)


if __name__ == "__main__":
    main()
