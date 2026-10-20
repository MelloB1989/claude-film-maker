"""Timeless v2: shot time remap. Pure math (stdlib only), so it is unit-tested without the EffectCraft binary.

A shot of n comp frames [a, b) plays the clip window src[0] -> src[1] (seconds in the clip's own timeline) with one of the
EDL speed profiles. `remap(shot)` returns `T(i)`: the source time shown at comp frame a+i, with
`T(0) == src[0]` and `T(n) == src[1]` exactly (the boundary b itself; the last displayed frame is b-1). Beyond [0, n] (the
transition handles) the speed of the end continues, then the caller clamps to the clip.

Profiles (relative speed w(x) over normalised time x in 0..1, `T = src0 + (src1-src0) * int(w)/int(w)`):
  const     w = 1
  velocity  fast -> slow (the middle third plays at 0.25 of the peak) -> fast, smooth shoulders
  land      fast -> slow (lands on 0.25 of the peak)
  launch    slow -> fast
  reverse   const; the direction comes from src[0] > src[1] (any profile may run backwards)

`source_cut`: the clip has its own cut at source time `tc` (the first frame of the new scene). The remap is made
piecewise (each side keeps the profile's shape, scaled) so that `T(F - a) == tc` exactly: the cut lands on comp frame F.
"""
from __future__ import annotations

import bisect
import math

SLOW = 0.25          # the slow end of the velocity profiles, relative to the peak
N_INT = 4000         # integration steps over 0..1 (smooth curve, monotonic by construction)


def smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def speed_w(profile: str, x: float) -> float:
    """Relative speed at normalised time x (always > 0)."""
    if profile in ("const", "reverse"):
        return 1.0
    if profile == "velocity":
        bump = smoothstep(0.12, 0.36, x) * (1 - smoothstep(0.64, 0.88, x))   # 1 through the middle third
        return 1.0 - (1.0 - SLOW) * bump
    if profile == "land":
        return SLOW + (1.0 - SLOW) * (1 - smoothstep(0.05, 0.95, x))
    if profile == "launch":
        return SLOW + (1.0 - SLOW) * smoothstep(0.05, 0.95, x)
    raise ValueError(f"unknown speed profile {profile!r}")


class Remap:
    """The source-time function of one shot. Call it with a comp frame offset i (0 = the shot's first frame)."""

    def __init__(self, src, n, profile="const", cut=None):
        """`cut` = (frame_offset_i, source_time_tc) or None."""
        self.s0, self.s1 = float(src[0]), float(src[1])
        self.n = int(n)
        self.profile = profile
        self.cut = cut
        # cumulative integral of w on a fine grid; I(x) for any x
        w = [speed_w(profile, k / N_INT) for k in range(N_INT + 1)]
        self._cum = [0.0]
        for k in range(N_INT):
            self._cum.append(self._cum[-1] + 0.5 * (w[k] + w[k + 1]) / N_INT)
        self._w0, self._w1 = w[0], w[-1]
        self.xc = None
        if cut is not None:
            i, tc = cut
            if not 0 < i < n:
                raise ValueError(f"source_cut offset {i} outside the shot (0, {n})")
            self.xc = i / n
            lo, hi = sorted((self.s0, self.s1))
            if not lo < tc < hi:
                raise ValueError(f"source cut {tc} outside the source window {self.s0}..{self.s1}")
            # fraction of the source travel before the cut
            self.fc = (tc - self.s0) / (self.s1 - self.s0)
            self.tc = tc

    def _I(self, x):
        """Integral of w from 0 to x, x in [0, 1], linear inside a grid cell."""
        pos = x * N_INT
        k = min(int(pos), N_INT - 1)
        w_k = speed_w(self.profile, k / N_INT)
        w_x = speed_w(self.profile, x)
        return self._cum[k] + 0.5 * (w_k + w_x) * (x - k / N_INT)

    def _frac(self, x):
        """Fraction (0..1 over the window) of the source travel done at normalised time x; extends linearly outside."""
        tot = self._cum[-1]
        if x <= 0:
            return x * self._w0 / tot
        if x >= 1:
            return 1.0 + (x - 1) * self._w1 / tot
        if self.xc is None:
            return self._I(x) / tot
        Ic = self._I(self.xc)
        if x <= self.xc:
            return self.fc * self._I(x) / Ic
        return self.fc + (1 - self.fc) * (self._I(x) - Ic) / (tot - Ic)

    def __call__(self, i):
        if i == 0:
            return self.s0
        if i == self.n:
            return self.s1
        if self.cut is not None and i == self.cut[0]:
            return self.tc
        return self.s0 + (self.s1 - self.s0) * self._frac(i / self.n)


def remap_keys(rm: Remap, hin, hout, fps, clip_len=None, src_fps=60.0, cut_eps=0.1):
    """[(comp time offset in s from the first handle frame, source time)] one key per comp frame i in [-hin, n+hout),
    clamped to the clip (`clip_len` seconds, last frame at clip_len - 1/src_fps). `time 0` = frame a - hin.

    With a source cut at frame F the key at F is nudged `cut_eps` of a source frame past tc (so floating-point never
    rounds the frame down onto the old scene), and two extra keys at F-0.5 / F-0.5+1ms hold the old scene across the
    motion-blur shutter (frame F-1's samples reach F-0.625, frame F's start at F-0.375): no ghost across the cut."""
    ks = []
    top = None if clip_len is None else max(0.0, clip_len - 1.0 / src_fps)

    def clamp(v):
        v = max(0.0, v)
        return v if top is None else min(v, top)

    sf = 1.0 / src_fps
    for i in range(-hin, rm.n + hout):
        v = rm(i)
        if rm.cut is not None and i == rm.cut[0]:
            v = rm.tc + cut_eps * sf * (1 if rm.s1 > rm.s0 else -1)
        ks.append(((i + hin) / fps, clamp(v)))
    if rm.cut is not None:
        i = rm.cut[0]
        sgn = 1 if rm.s1 > rm.s0 else -1
        pre = clamp(rm.tc - sgn * 0.5 * sf)
        post = clamp(rm.tc + sgn * cut_eps * sf)
        ks = [k for k in ks if abs(k[0] - (i + hin) / fps) > 1e-9]
        ks += [((i - 0.5 + hin) / fps, pre), ((i - 0.5 + hin) / fps + 0.001, post), ((i + hin) / fps, post)]
        ks.sort()
        # the frame F-1 key must stay in the old scene
        ks = [(t, (min(v, pre) if sgn > 0 else max(v, pre)) if t < (i - 0.5 + hin) / fps else v) for t, v in ks]
    return ks
