"""mix_fix: the handover's mix.py with the two outro defects of the Timeless mix repaired (see audit_audio.py).

    PYTHONPATH=tools python -m filmtools.amv.mix_fix --film films/timeless --song <timeless_full.wav> \
        --sfx <handover>/project/sfx [--out films/timeless/audio/mix/mix_fixed.wav] [--original] [--verify]

The mix is rebuilt exactly as handover `project/scripts/mix.py` builds it (music 0..dur at 0.85, ducked under the
voice lines, SFX placed by `hit_offset`, outro sink, tanh limiter at -1 dBFS); only the outro differs:

1. The sink low-pass runs in 14 segments, one `sosfilt` call each. mix.py started every call from a zero filter
   state, so each segment boundary (3.57 frames apart, f815-f862) cut the filter's ringing and clicked. Here the
   state `zf` of one segment is the `zi` of the next (same order, coefficients move on), so the output is continuous.
2. `fade[s2:] = 0` stepped from gain 0.1 (-35 dBFS) to digital silence at f897.0. Here the last TAPER seconds before
   s2 ramp (raised cosine) from the fade's value there to 0, so the audio ends smoothly at s2.

Nothing before the sink (f812) is touched, and every later stage is per-sample (sum, tanh), so the mix is
sample-identical to the original before f812. `--original` rebuilds the unpatched mix (to prove the rebuild itself
is faithful); `--verify` compares the result with the film's `mix.wav` and checks the three properties above.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR, TAPER = 48000, 0.080


def build(film: Path, song_path: Path, sfx_dir: Path, fixed: bool = True) -> np.ndarray:
    plan = json.loads((film / "amv" / "plan.json").read_text())
    FPS, DUR = plan["fps"], plan["dur"]
    N = int(DUR / FPS * SR)
    song, sr = sf.read(song_path, always_2d=True)
    assert sr == SR
    mus = song[:N].copy() * 0.85
    duck = np.ones(N)
    stereo = lambda x: x if x.ndim == 2 else np.stack([x, x], 1)  # noqa: E731
    voice_bus = np.zeros((N, 2))
    for v in plan.get("voice", []):
        y, vsr = sf.read(film / v["file"], always_2d=True)
        assert vsr == SR, v["file"]
        y = stereo(y) * 10 ** (v.get("db", 0) / 20)
        s = int(v["f"] / FPS * SR)
        e = min(N, s + len(y))
        voice_bus[s:e] += y[:e - s]
        a, b = max(0, s - int(0.08 * SR)), min(N, e + int(0.15 * SR))
        duck[a:b] = np.minimum(duck[a:b], 10 ** (v.get("duck", -6) / 20))
    k = int(0.06 * SR)
    duck = np.convolve(duck, np.ones(k) / k, "same")
    mus *= duck[:, None]
    # outro sink: progressive low-pass then fade
    o = plan["outro"]
    f0, f1, f2 = o["f"], o["f"] + 50, DUR - 3
    s0, s1, s2 = int(f0 / FPS * SR), int(f1 / FPS * SR), int(f2 / FPS * SR)
    steps = 14
    seg = (s1 - s0) // steps
    zi = None
    for i in range(steps):
        fc = 20000 * (300 / 20000) ** ((i + 1) / steps)
        sos = butter(2, fc, fs=SR, output="sos")
        a = s0 + i * seg
        b = N if i == steps - 1 else a + seg
        if fixed:  # keep the filter state across segments
            mus[a:b], zi = sosfilt(sos, mus[a:b], axis=0, zi=np.zeros((sos.shape[0], 2, 2)) if zi is None else zi)
        else:
            mus[a:b] = sosfilt(sos, mus[a:b], axis=0)
    fade = np.ones(N)
    fade[s1:s2] = np.linspace(1, 0.1, s2 - s1)
    fade[s2:] = 0
    if fixed:  # the last TAPER s before s2 go to 0 on a raised cosine instead of stepping
        t0 = s2 - int(TAPER * SR)
        u = np.linspace(0.0, 1.0, s2 - t0, endpoint=False)
        fade[t0:s2] *= 0.5 * (1 + np.cos(np.pi * u))
    mus *= fade[:, None]
    if plan.get("predrop"):
        pa, pb = int(plan["predrop"][0] / FPS * SR), int(plan["predrop"][1] / FPS * SR)
        sos = butter(2, 180, btype="high", fs=SR, output="sos")
        mus[pa:pb] = sosfilt(sos, mus[pa:pb], axis=0) * 0.9
    kit = json.loads((sfx_dir / "sfx_kit.json").read_text())
    sfx_bus = np.zeros((N, 2))
    for e in plan.get("sfx", []):
        K = kit[e["name"]]
        y, _ = sf.read(sfx_dir / K["file"], always_2d=True)
        y = y * 10 ** (e.get("db", -10) / 20)
        s = int(e["f"] / FPS * SR - K["hit_offset"] * SR)
        a, b = max(0, s), min(N, s + len(y))
        if b > a:
            sfx_bus[a:b] += y[a - s:b - s]
    mix = mus + sfx_bus + voice_bus
    peak = 10 ** (-1 / 20)
    return (np.tanh(mix / peak * 0.9) * peak).astype(np.float32)


def db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.asarray(x, np.float64) ** 2)) + 1e-12))


def verify(film: Path, new: np.ndarray, original: np.ndarray) -> bool:
    from . import audit_audio as A
    plan = json.loads((film / "amv" / "plan.json").read_text())
    fps, dur = plan["fps"], plan["dur"]
    fr = lambda f: int(round(f * SR / fps))  # noqa: E731
    ok = True
    print("(a) max abs difference against mix.wav, per region (float32 samples):")
    for name, a, b in (("f0-811", 0, 812), ("f812-896 (sink)", 812, 897), ("f897-899 (tail)", 897, dur)):
        d = float(np.abs(new[fr(a):fr(b)] - original[fr(a):fr(b)]).max())
        print(f"    {name:<18} {d:.3e}" + ("  identical" if d == 0 else ""))
        if a == 0 and d != 0:
            ok = False
    mono = new.mean(axis=1)
    tr = [(t * fps, s) for t, s in A.transients(mono, SR, 4.0) if 815 <= t * fps <= 862]
    runs = A.even_runs([f for f, _ in tr])
    old = [(t * fps, s) for t, s in A.transients(original.mean(axis=1), SR, 4.0) if 815 <= t * fps <= 862]
    print(f"(b) transients >= 4 in f815-862: {len(tr)} (original {len(old)}); even runs of >= 5: {len(runs)} "
          f"(original {len(A.even_runs([f for f, _ in old]))})")
    ok &= not runs
    hc = A.hard_cuts(mono, SR, fps)
    print(f"    hard cuts: {len(hc)} (original {len(A.hard_cuts(original.mean(axis=1), SR, fps))})")
    ok &= not hc
    a, b = fr(812), fr(dur)
    pn, po = float(np.abs(new[a:b]).max()), float(np.abs(original[a:b]).max())
    rn, ro = db(new[a:b]), db(original[a:b])
    print(f"(c) outro f812-899: rms {rn:.2f} dBFS (original {ro:.2f}, diff {rn - ro:+.2f} dB); "
          f"peak {20 * np.log10(pn):.2f} dBFS (original {20 * np.log10(po):.2f}, diff {20 * np.log10(pn / po):+.2f} dB)")
    ok &= abs(rn - ro) <= 0.5 and abs(20 * np.log10(pn / po)) <= 0.5
    print("PASS" if ok else "FAIL")
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--film", required=True, type=Path)
    ap.add_argument("--song", required=True, type=Path, help="the full song (handover audio/timeless_full.wav)")
    ap.add_argument("--sfx", required=True, type=Path, help="the sfx kit folder (handover project/sfx)")
    ap.add_argument("--out", type=Path, help="default: <film>/audio/mix/mix_fixed.wav")
    ap.add_argument("--original", action="store_true", help="rebuild the unpatched mix instead")
    ap.add_argument("--verify", action="store_true", help="compare with the film's mix.wav")
    a = ap.parse_args(argv)
    mix = build(a.film, a.song, a.sfx, fixed=not a.original)
    out = a.out or a.film / "audio" / "mix" / ("mix_rebuilt.wav" if a.original else "mix_fixed.wav")
    sf.write(out, mix, SR, subtype="PCM_16")  # the format of mix.wav
    mix, _ = sf.read(out, dtype="float32", always_2d=True)  # compare what is on disk
    print("wrote", out)
    ref, _ = sf.read(a.film / "audio" / "mix" / "mix.wav", dtype="float32", always_2d=True)
    if a.original:
        print("rebuild vs mix.wav: max abs diff", float(np.abs(mix - ref).max()))
        return 0
    return 0 if not a.verify or verify(a.film, mix, ref) else 1


if __name__ == "__main__":
    sys.exit(main())
