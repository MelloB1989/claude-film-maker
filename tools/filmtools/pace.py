"""Pace a take: cut the silence around the words (never the speech the aligner left outside them), then time-stretch
with Rubber Band's R3 engine (pitch and timbre are kept; nothing is pitch-shifted). Jean runs slow, so the default
tightens by 10%. Each word that opens the line or follows a pause then gets its spoken onset, measured on the paced
audio (onsets.py), as `onset` (seconds into the paced take, or null)."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .onsets import voice_onsets
from .paths import AUDIO
from .wav import read_wav, write_wav

MIN_FACTOR, MAX_FACTOR = 0.85, 1.0  # never slow her down, never squeeze more than 15%
DEFAULT_FACTOR = 0.9


def _widen(samples: np.ndarray, sr: int, start: float, end: float, thresh_db: float, frame: float = 0.005):
    """Move `start` earlier and `end` later over audio that runs on, unbroken, from the words and stays within
    `thresh_db` of the take's loudest frame. Forced alignment starts the first word late and ends the last one early:
    on Jean's 106 takes speech runs a median 85 ms before the first aligned word and 80-110 ms after the last, so
    cutting at its times removed audio within 30 dB of the take's peak from the start of 97 takes and the end of 25.
    At -45 dB no speech is left outside: Jean's room tone is typically below -60 dB and what remains beyond the
    widened cut is a start-up transient and an end-of-file blip."""
    n = int(frame * sr)
    m = len(samples) // n
    if m == 0:
        return start, end
    rms = np.sqrt(np.mean(samples[:m * n].reshape(m, n) ** 2, axis=1))
    loud = rms > rms.max() * 10 ** (thresh_db / 20)
    i = i0 = min(int(round(start * sr)) // n, m - 1)
    while i > 0 and loud[i - 1]:
        i -= 1
    j = j0 = min(int(round(end * sr)) // n, m - 1)
    while j < m - 1 and loud[j + 1]:
        j += 1
    return (i * n / sr if i < i0 else start), ((j + 1) * n / sr if j > j0 else end)


def trim(samples: np.ndarray, sr: int, words: list[dict], pad: float = 0.04, thresh_db: float = -45.0):
    first, last = _widen(samples, sr, words[0]["start"], words[-1]["end"], thresh_db)
    a = max(0.0, first - pad)
    b = min(len(samples) / sr, last + 2 * pad)
    out = samples[int(round(a * sr)):int(round(b * sr))].copy()
    f = int(0.005 * sr)
    if len(out) > 2 * f:
        ramp = np.linspace(0.0, 1.0, f, dtype=np.float32)
        out[:f] *= ramp
        out[-f:] *= ramp[::-1]
    return out, [{**w, "start": w["start"] - a, "end": w["end"] - a} for w in words]


def speech_rate(words: list[dict]) -> float:
    span = words[-1]["end"] - words[0]["start"]
    return len(words) / span if span > 0 else 0.0


def factor_for(words: list[dict], target_wps: float) -> float:
    r = speech_rate(words)
    return 1.0 if r <= 0 else float(np.clip(r / target_wps, MIN_FACTOR, MAX_FACTOR))


def stretch(samples: np.ndarray, sr: int, factor: float, rubberband: str = "rubberband") -> np.ndarray:
    if abs(factor - 1.0) < 1e-4:
        return samples.copy()
    if not shutil.which(rubberband):
        raise RuntimeError("rubberband not found: brew install rubberband")
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "in.wav", Path(td) / "out.wav"
        write_wav(src, samples, sr)
        subprocess.run([rubberband, "-q", "-3", "-t", f"{factor:.6f}", str(src), str(dst)], check=True)
        out, _ = read_wav(dst)
    return out


def pace_take(take_wav: Path, take_json: Path, out_dir: Path, factor: float) -> dict:
    meta = json.loads(take_json.read_text())
    x, sr = read_wav(take_wav)
    x, words = trim(x, sr, meta["words"])
    y = stretch(x, sr, factor)
    words = [{**w, "start": round(w["start"] * factor, 4), "end": round(w["end"] * factor, 4)} for w in words]
    words = [{**w, "onset": on} for w, on in zip(words, voice_onsets(y, sr, words))]
    out = {**meta, "factor": factor, "duration": round(len(y) / sr, 4), "words": words}
    write_wav(out_dir / take_wav.name, y, sr)
    (out_dir / take_json.name).write_text(json.dumps(out, indent=1))
    return out


def load_selects(path: Path = AUDIO / "vo" / "selects.json") -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Trim and time-stretch voiceover takes")
    ap.add_argument("--only", help="comma-separated line ids")
    ap.add_argument("--factor", type=float, default=DEFAULT_FACTOR, help="duration multiplier (0.9 = 10%% faster)")
    ap.add_argument("--target-wps", type=float, help="pick each take's factor from a target speech rate instead")
    a = ap.parse_args(argv)
    selects = load_selects()
    only = set(a.only.split(",")) if a.only else None
    takes_root, paced_root = AUDIO / "vo" / "takes", AUDIO / "vo" / "paced"
    n = 0
    for tj in sorted(takes_root.glob("*/*.json")):
        line = tj.parent.name
        if only and line not in only:
            continue
        meta = json.loads(tj.read_text())
        k = selects.get(line, {}).get("factor")
        if k is None:
            k = factor_for(meta["words"], a.target_wps) if a.target_wps else a.factor
        out = pace_take(tj.with_suffix(".wav"), tj, paced_root / line, float(np.clip(k, MIN_FACTOR, MAX_FACTOR)))
        n += 1
        print(f"{line} take {out['take']}: ×{out['factor']:.2f} → {out['duration']:.2f}s")
    print(f"{n} takes paced")
