"""Cut the score to picture on its bar grid.

A bar map lists, for each output bar, the source bar to play there. Bars are cut on the analysed downbeats. Wherever
consecutive output bars aren't consecutive in the source, the join is an equal-power crossfade centred on the output
bar line: the outgoing bar's continuation fades out while the incoming bar's lead-in fades in, so its downbeat still
lands exactly on the line. Tempo and sound are untouched; only the order of bars changes.
"""
import argparse
import json

import numpy as np

from .paths import DATA, ROOT
from .wav import read_wav, write_wav


def parse_map(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = (int(v) for v in part.split("-"))
            if b < a:
                raise ValueError(f"descending range {part!r}")
            out.extend(range(a, b + 1))
        else:
            out.append(int(part))
    return out


def _window(y: np.ndarray, a: int, b: int) -> np.ndarray:
    """y[a:b] with zeros where the window runs past either end."""
    pad_l, pad_r = max(0, -a), max(0, b - len(y))
    seg = y[max(0, a):min(len(y), b)]
    widths = [(pad_l, pad_r)] + [(0, 0)] * (y.ndim - 1)
    return np.pad(seg, widths)


def splice(y: np.ndarray, sr: int, edges: list[float], bar_map: list[int], xfade: float = 0.01) -> np.ndarray:
    cut = [int(round(e * sr)) for e in edges]
    n_bars = len(cut) - 1
    if any(not 0 <= b < n_bars for b in bar_map):
        raise ValueError(f"bar map refers to bars outside 0..{n_bars - 1}")
    short = [b for b in bar_map[:-1] if cut[b + 1] > len(y)]
    if short:  # its piece would be short, so every join after it would sit that much off its bar line
        raise ValueError(f"bar {short[0]} runs past the end of the file, so it can only end the map")
    pieces = [y[:cut[0]]] + [y[cut[b]:cut[b + 1]] for b in bar_map]
    if bar_map and bar_map[-1] == n_bars - 1:
        pieces.append(y[cut[-1]:])
    out = np.concatenate(pieces, axis=0).astype(np.float32)
    h = max(1, int(round(xfade * sr / 2)))
    theta = np.linspace(0.0, np.pi / 2, 2 * h, dtype=np.float32)
    fo, fi = np.cos(theta), np.sin(theta)
    if y.ndim == 2:
        fo, fi = fo[:, None], fi[:, None]
    pos = cut[0]
    for i in range(1, len(bar_map)):
        a, b = bar_map[i - 1], bar_map[i]
        pos += cut[a + 1] - cut[a]
        if b == a + 1:
            continue
        tail = _window(y, cut[a + 1] - h, cut[a + 1] + h)
        head = _window(y, cut[b] - h, cut[b] + h)
        lo, hi = max(0, pos - h), min(len(out), pos + h)
        out[lo:hi] = (tail * fo + head * fi)[lo - (pos - h):hi - (pos - h)]
    return out


# The tempo is fitted, so it is a hair off the generator's and the grid ends a few ms past the end of the file (13 ms
# over seed 11's 39 bars). A final bar that is all but there still counts as a bar.
END_SLACK = 0.05


def bar_edges(downbeats: list[float], bar: float, duration: float) -> list[float]:
    """Downbeats extended by whole bars to the last bar of the track, which may fall END_SLACK short of complete."""
    d = list(downbeats)
    while d[-1] + bar <= duration + END_SLACK:
        d.append(d[-1] + bar)
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description="Re-order the chosen score's bars to fit the picture")
    ap.add_argument("--map", required=True, help="source bar per output bar, e.g. 0-27,32-35,24-27,36-38")
    a = ap.parse_args(argv)
    mp_path = DATA / "music_plan.json"
    mp = json.loads(mp_path.read_text())
    src = mp.get("edit", {}).get("source") or mp["chosen"]
    audio = json.loads((DATA / "audio.json").read_text())
    y, sr = read_wav(ROOT / src, mono=False)
    edges = bar_edges(audio["downbeats"], 4 * audio["beat_period"], len(y) / sr)
    out = splice(y, sr, edges, parse_map(a.map))
    dst = f"{src.removesuffix('.wav')}-edit.wav"
    write_wav(ROOT / dst, out, sr)
    mp["edit"] = {"source": src, "map": a.map}
    mp["chosen"] = dst
    mp_path.write_text(json.dumps(mp, indent=1))
    print(f"{dst}: {len(out) / sr:.3f}s from {len(edges) - 1} source bars (map {a.map})")
