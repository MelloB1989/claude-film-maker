"""Audio around the reference transitions: band envelopes aligned on the cut frame.

    PYTHONPATH=tools python -m filmtools.amv3.analysis.ref_audio <ref.mp4> <cut,cut,...> <out.png> [--fps 30]

Per cut, the energy (dB) of three bands over [-30, +20] frames around the cut: sub (30-90 Hz, impacts/booms), body
(150-1500 Hz) and air (3-12 kHz, whooshes/risers/glass), each relative to its median over the whole song so the
bed is ~0 dB. Prints, per cut, when the air band starts rising (first frame >= 3 dB over its level 30 f before),
the frame of the air peak and of the sub peak, and the decay to half after the cut; plots the per-cut curves and
their median. The references are finished mixes (music + SFX), so these are the SFX shapes as heard over the song.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

import numpy as np
import scipy.signal as sg

SR = 48000
BANDS = {"sub": (30, 90), "body": (150, 1500), "air": (3000, 12000)}


def load(path: str) -> np.ndarray:
    import imageio_ffmpeg
    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def band_env(x: np.ndarray, fps: float) -> dict[str, np.ndarray]:
    """dB per video frame (RMS over the frame) of each band."""
    n = int(len(x) / SR * fps)
    out = {}
    for k, (lo, hi) in BANDS.items():
        y = sg.sosfiltfilt(sg.butter(4, [lo, hi], "band", fs=SR, output="sos"), x)
        e = np.array([np.sqrt(np.mean(y[int(i / fps * SR):int((i + 1) / fps * SR)] ** 2) + 1e-12) for i in range(n)])
        d = 20 * np.log10(e)
        out[k] = d - np.median(d)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("cuts")
    ap.add_argument("out")
    ap.add_argument("--fps", type=float, default=30)
    a = ap.parse_args(argv)
    cuts = [int(c) for c in a.cuts.split(",")]
    env = band_env(load(a.ref), a.fps)
    lo, hi = -30, 20
    rel = np.arange(lo, hi)
    curves = {k: [] for k in BANDS}
    print("cut  air_rise  air_peak  sub_peak  air_half_after  (frames rel. to cut; air dB at peak, sub dB at peak)")
    for c in cuts:
        seg = {k: v[c + lo:c + hi] for k, v in env.items()}
        if len(seg["air"]) < hi - lo:
            continue
        for k in BANDS:
            curves[k].append(seg[k])
        air, sub = seg["air"], seg["sub"]
        base = np.median(air[:8])
        win = slice(-lo - 15, -lo + 6)                          # look for the peak from -15 to +5
        ip = int(np.argmax(air[win])) + win.start
        rise = next((i for i in range(ip, -1, -1) if air[i] < base + 3), 0) + 1
        isub = int(np.argmax(sub[-lo - 4:-lo + 6])) - 4
        half = next((i for i in range(ip, len(air)) if air[i] < air[ip] - 6), len(air) - 1)
        print(f"{c:4d}  {rise + lo:+4d}      {ip + lo:+4d}      {isub:+4d}      {half + lo:+4d}"
              f"           air {air[ip] - base:+5.1f} dB  sub {sub[isub - lo]:+5.1f} dB")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(len(BANDS), 1, figsize=(10, 8), sharex=True)
    for ax, k in zip(axs, BANDS):
        for y in curves[k]:
            ax.plot(rel, y, color="0.75", lw=0.8)
        ax.plot(rel, np.median(curves[k], axis=0), color="C3", lw=2, label="median")
        ax.axvline(0, color="k", lw=0.8)
        ax.set_ylabel(f"{k} dB")
        ax.grid(alpha=0.3)
    axs[0].set_title(f"{a.ref.split('/')[-1]}: band energy around {len(curves['air'])} cuts (0 = cut frame)")
    axs[-1].set_xlabel("frames from the cut")
    fig.tight_layout()
    fig.savefig(a.out, dpi=90)
    print("median air curve:", " ".join(f"{v:+.0f}" for v in np.median(curves["air"], axis=0)))
    print("median sub curve:", " ".join(f"{v:+.0f}" for v in np.median(curves["sub"], axis=0)))


if __name__ == "__main__":
    sys.exit(main())
