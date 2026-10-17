"""Measure per-shot picture statistics (shared by grade_spec.py and the before/after contact sheet).

Needs numpy and an ffmpeg binary; `grade_spec` falls back to the cached `grade_stats.json` when either is missing.
All values are on the gamma-encoded 0..1 scale.
"""
import os
import shutil
import subprocess

FFMPEG_FALLBACK = "/home/nikhil/code/film-making/bin/ffmpeg"
SW, SH = 480, 270


def ffmpeg_bin():
    return shutil.which("ffmpeg") or (FFMPEG_FALLBACK if os.path.exists(FFMPEG_FALLBACK) else None)


def read_frame(path, t, size=(SW, SH)):
    """One RGB frame (uint8 HxWx3) at time t seconds, or None."""
    import numpy as np
    ff = ffmpeg_bin()
    if not ff:
        return None
    w, h = size
    p = subprocess.run([ff, "-v", "error", "-ss", "%.4f" % t, "-i", path, "-frames:v", "1", "-vf", "scale=%d:%d" % (w, h),
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if len(p.stdout) != w * h * 3:
        return None
    return np.frombuffer(p.stdout, np.uint8).reshape(h, w, 3)


def luma(rgb):
    f = rgb.astype("float32") / 255.0
    return f[..., 0] * 0.2126 + f[..., 1] * 0.7152 + f[..., 2] * 0.0722


def hsv(rgb):
    """(h in degrees, s, v) float arrays."""
    import numpy as np
    f = rgb.astype("float32") / 255.0
    mx, mn = f.max(-1), f.min(-1)
    d = mx - mn
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    h = np.zeros_like(mx)
    m = d > 1e-6
    rc = m & (mx == r)
    gc = m & (mx == g) & ~rc
    bc = m & ~rc & ~gc
    h[rc] = ((g - b)[rc] / d[rc]) % 6
    h[gc] = (b - r)[gc] / d[gc] + 2
    h[bc] = (r - g)[bc] / d[bc] + 4
    return h * 60.0, np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0), mx


def stats(frames, flash_ok=False):
    """Pool pixels of several RGB frames into one stats dict."""
    import numpy as np
    L = np.concatenate([luma(f).ravel() for f in frames])
    H, S, V = [np.concatenate([a.ravel() for a in z]) for z in zip(*[hsv(f) for f in frames])]
    R = np.concatenate([f.reshape(-1, 3) for f in frames]).astype("float32") / 255.0
    p = np.percentile(L, [1, 5, 50, 95, 99])
    clip = float(np.mean(R.max(1) >= 0.985) * 100)
    crush = float(np.mean(L <= 0.012) * 100)
    R8 = R * 255
    sk = (H >= 8) & (H <= 45) & (S >= 0.2) & (S <= 0.65) & (V >= 0.35) & (R8[:, 0] > 95) & (R8[:, 1] > 40) & (R8[:, 2] > 20) \
        & (R.max(1) - R.min(1) > 15 / 255) & (np.abs(R8[:, 0] - R8[:, 1]) > 15) & (R[:, 0] > R[:, 1]) & (R[:, 0] > R[:, 2])
    d = {"p1": round(float(p[0]), 4), "p5": round(float(p[1]), 4), "p50": round(float(p[2]), 4), "p95": round(float(p[3]), 4),
         "p99": round(float(p[4]), 4), "clip": round(clip, 3), "crush": round(crush, 3),
         "sat": round(float(S[V > 0.1].mean()) if (V > 0.1).any() else 0.0, 4),
         "white": [round(float(np.percentile(R[:, c], 99.5)), 4) for c in range(3)],
         "mean_rgb": [round(float(R[:, c].mean()), 4) for c in range(3)],
         "skin": round(float(sk.mean()), 4)}
    d["skin_hue"] = round(float(np.median(H[sk])), 1) if sk.sum() > 200 else None
    return d


def clip_times(shot, n=6):
    lo, hi = sorted(shot["src"])
    if hi - lo < 0.05:
        return [lo]
    return [lo + (hi - lo) * (i + 0.5) / n for i in range(n)]


def measure_shot(shot, path=None, n=6):
    fr = [read_frame(path or shot["file"], t) for t in clip_times(shot, n)]
    fr = [f for f in fr if f is not None]
    return (stats(fr) if fr else None), fr
