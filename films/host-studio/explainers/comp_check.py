"""Composite checks qa_av.py does not cover (agent-04, gate owner, 09 Nov): black frames, duplicated frames inside the
presenter's shots, and the picture/sound sync against the mix that was laid in. Numbers only; it runs where the
composite is (the box: a presenter render never leaves it).

    python3 comp_check.py CUT.mp4 --mix MIX.wav [--edl edl/<film>.json] [--fps 24] [--json OUT] [--gate OUT]

Rows:
  cut.black_frames == 0         frames whose mean luma < 0.02 for >= 1 frame (ffmpeg blackdetect, pix_th 0.10)
  cut.dup_frames_presenter == 0 a frame byte-identical to the one before inside a presenter/panel shot (a rendered take
                                never repeats a frame: breath and micro-motion move every one; graphics shots may hold)
  cut.av_offset_ms <= 42        |lag| of the cut's audio against MIX by envelope cross-correlation (one 24 fps frame)
  cut.av_len_diff_ms <= 42      |video duration - audio duration|
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

import numpy as np


def black_frames(cut: str, fps: float) -> dict:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", cut, "-vf",
                          f"blackdetect=d={1.0 / fps:.4f}:pix_th=0.10:pic_th=0.98", "-an", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    spans = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", out)]
    return {"frames": int(round(sum(b - a for a, b in spans) * fps)), "spans": spans[:10]}


def frame_hashes(cut: str) -> list:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", cut, "-an", "-f", "framemd5", "-"],
                         capture_output=True, text=True).stdout
    return [ln.split(",")[-1].strip() for ln in out.splitlines() if ln and not ln.startswith("#")]


def dup_frames(hashes: list, keep) -> dict:
    d = [i for i in range(1, len(hashes)) if hashes[i] == hashes[i - 1] and keep(i)]
    return {"frames": len(d), "first": d[:20]}


def presenter_mask(edl_path: str | None, fps: float):
    """frame -> True inside a presenter or panel shot of agent-11's edl/<film>.json (shots[].kind 'pres'/'panel';
    f0/f1 master frames, f1 exclusive). Graphics shots ('gfx') may hold a frame on purpose."""
    if not edl_path:
        return lambda i: True
    e = json.loads(open(edl_path).read())
    spans = [(int(s["f0"]), int(s["f1"])) for s in e["shots"] if str(s.get("kind", "")).lower() != "gfx"]
    return lambda i: any(a <= i < b for a, b in spans)


def read_wav_mono(path: str, rate: int = 8000) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-ac", "1", "-ar", str(rate),
                          "-f", "s16le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0


def envelope(x: np.ndarray, rate: int, hop_ms: float = 2.0) -> np.ndarray:
    h = max(1, int(rate * hop_ms / 1000))
    n = len(x) // h
    e = np.sqrt((x[: n * h].reshape(n, h) ** 2).mean(axis=1))
    return e - e.mean()


def av_offset_ms(cut: str, mix: str, max_ms: float = 500.0, rate: int = 8000) -> dict:
    """the lag (ms) that best aligns the cut's audio envelope with the mix's; + = the cut's audio is LATE."""
    a, b = envelope(read_wav_mono(cut, rate), rate), envelope(read_wav_mono(mix, rate), rate)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    hop = 2.0
    m = int(max_ms / hop)
    best, best_k = -1e18, 0
    for k in range(-m, m + 1):
        if k >= 0:
            c = float(np.dot(a[k:], b[: n - k]))
        else:
            c = float(np.dot(a[: n + k], b[-k:]))
        if c > best:
            best, best_k = c, k
    norm = float(np.sqrt(np.dot(a, a) * np.dot(b, b))) or 1.0
    return {"offset_ms": round(best_k * hop, 1), "corr": round(best / norm, 3)}


def durations(cut: str) -> dict:
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", cut],
                                  capture_output=True, text=True).stdout)
    d = {s["codec_type"]: float(s.get("duration", 0) or 0) for s in j.get("streams", [])}
    return {"video_s": d.get("video"), "audio_s": d.get("audio")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cut")
    ap.add_argument("--mix", required=True)
    ap.add_argument("--edl")
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--json")
    ap.add_argument("--gate")
    a = ap.parse_args(argv)
    bl = black_frames(a.cut, a.fps)
    dp = dup_frames(frame_hashes(a.cut), presenter_mask(a.edl, a.fps))
    av = av_offset_ms(a.cut, a.mix)
    du = durations(a.cut)
    len_diff = abs((du["video_s"] or 0) - (du["audio_s"] or 0)) * 1000
    rows = {"cut.black_frames": bl["frames"], "cut.dup_frames_presenter": dp["frames"],
            "cut.av_offset_ms": abs(av["offset_ms"]), "cut.av_len_diff_ms": round(len_diff, 1)}
    lines = {"cut.black_frames": ("==", 0), "cut.dup_frames_presenter": ("==", 0), "cut.av_offset_ms": ("<=", 42.0),
             "cut.av_len_diff_ms": ("<=", 42.0)}
    ok = {k: (v == lines[k][1] if lines[k][0] == "==" else v <= lines[k][1]) for k, v in rows.items()}
    rep = {"rows": rows, "pass": ok, "all_pass": all(ok.values()),
           "detail": {"black": bl, "dup": dp, "av": av, "durations": du}}
    if a.json:
        open(a.json, "w").write(json.dumps(rep, indent=1))
    if a.gate:
        open(a.gate, "w").write(json.dumps({"gate": {k: {"value": v, "where": a.cut.split("/")[-1]}
                                                     for k, v in rows.items()}}, indent=1))
    print(json.dumps(rep, indent=1))
    return 0 if rep["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
