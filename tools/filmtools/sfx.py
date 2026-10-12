"""The SFX bus: every cue of the sheet (data/sfx.json, built by app/scripts/cues.ts) rendered from the picked library
takes (audio/sfx/manifest.json) into one stereo stem.

A one-shot is placed so that its hit (the take's `hit_s`: its onset, peak or end, as the palette aligns it) lands on
round(t·sr), exactly; a take that would start before the film is cut, never shifted. Gain is in dB onto the take
(every take is normalised to −1 dBFS peak). Pan is constant power (−3 dB each side at centre). A bed (a cue with
`dur`) tiles its loop with 50 ms equal-power seams, fades 30 ms in and out, and is cut to `dur`.

film-sfx writes audio/sfx/sfx.wav (48 kHz / 24-bit stereo, the length of the voice).
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from .paths import AUDIO, DATA
from .wav import SR, read_wav, write_wav

SEAM_S = 0.05
EDGE_S = 0.03


def load_sheet(path: Path = DATA / "sfx.json") -> dict:
    s = json.loads(Path(path).read_text())
    return {"cues": s.get("cues", []), "ducks": s.get("ducks", []), "fps": s.get("fps", 30)}


def pan_gains(pan: float) -> tuple[float, float]:
    th = (float(np.clip(pan, -1.0, 1.0)) + 1) * math.pi / 4
    return math.cos(th), math.sin(th)


def tile(loop: np.ndarray, n: int, sr: int) -> np.ndarray:
    """The loop repeated to n samples, each copy crossfaded into the next over SEAM_S with sin/cos (equal power),
    and EDGE_S raised-cosine fades at both ends."""
    x = int(round(SEAM_S * sr))
    if len(loop) <= 2 * x:
        raise ValueError(f"a loop of {len(loop)} samples is too short for {SEAM_S * 1e3:.0f} ms seams")
    ph = (np.arange(x) + 0.5) / x * (math.pi / 2)
    fin, fout = np.sin(ph), np.cos(ph)
    out = np.zeros(n + len(loop), np.float64)
    pos, first = 0, True
    while pos < n:
        c = loop.astype(np.float64).copy()
        if not first:
            c[:x] *= fin
        c[-x:] *= fout
        out[pos:pos + len(c)] += c
        pos += len(loop) - x
        first = False
    out = out[:n]
    e = min(int(round(EDGE_S * sr)), n // 2)
    if e:
        ramp = 0.5 * (1 - np.cos(np.pi * (np.arange(e) + 0.5) / e))
        out[:e] *= ramp
        out[n - e:] *= ramp[::-1]
    return out


def _take(lib: Path, pick: dict, cache: dict) -> np.ndarray:
    w = pick["wav"]
    if w not in cache:
        y, sr = read_wav(lib / w)
        if sr != SR:
            raise ValueError(f"{w}: {sr} Hz, the bus is {SR} Hz")
        cache[w] = y.astype(np.float64)
    return cache[w]


def render_bus(sheet: dict, manifest: dict, lib: Path, duration: float, sr: int = SR) -> np.ndarray:
    n = int(round(duration * sr))
    bus = np.zeros((n, 2), np.float64)
    picks, cache = manifest["picks"], {}
    for c in sheet["cues"]:
        name = c["sound"]
        if name not in picks:
            raise KeyError(f"unknown sound {name!r} (cue {c.get('id', '?')}): not in the library's picks")
        if not 0 <= c["t"] < duration:
            raise ValueError(f"cue {c.get('id', name)} at {c['t']:.3f} s is outside the film (0–{duration:.3f} s)")
        p = picks[name]
        y = _take(Path(lib), p, cache)
        at = int(round(c["t"] * sr))
        if c.get("dur") is not None:
            y = tile(y, int(round(c["dur"] * sr)), sr)
            start = at
        else:
            if p.get("hit_s") is None:
                raise ValueError(f"{name} has no hit_s and cue {c.get('id', name)} has no dur")
            start = at - int(round(p["hit_s"] * sr))
        a, b = max(start, 0), min(start + len(y), n)
        if b <= a:
            continue
        g = 10 ** (c.get("gain", 0) / 20)
        gl, gr = pan_gains(c.get("pan", 0))
        seg = y[a - start:b - start] * g
        bus[a:b, 0] += seg * gl
        bus[a:b, 1] += seg * gr
    return bus.astype(np.float32)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render the cue sheet into audio/sfx/sfx.wav")
    ap.add_argument("--sheet", default=str(DATA / "sfx.json"))
    ap.add_argument("--out", default=str(AUDIO / "sfx" / "sfx.wav"))
    a = ap.parse_args(argv)
    sheet = load_sheet(Path(a.sheet))
    manifest = json.loads((AUDIO / "sfx" / "manifest.json").read_text())
    vo = json.loads((DATA / "vo.json").read_text())
    duration = float(vo["duration"])
    bus = render_bus(sheet, manifest, AUDIO / "sfx" / "lib", duration)
    write_wav(Path(a.out), bus)
    pk = 20 * np.log10(np.abs(bus).max() + 1e-12)
    print(f"{a.out} · {len(sheet['cues'])} cues · {duration:.3f} s · peak {pk:.1f} dBFS")
