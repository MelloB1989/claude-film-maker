"""Head stability: does the head move with the blinks, and does it buzz? The measurement behind perf.face's report,
qa.head_stability (the head bone sampled in Sequencer) and the render-level check (face landmarks on the frames).

Round 4, the operator on her: "every time she blinks her head nods a little down like a jitter, looks very very
odd". Real blinks never move the head (the eyeball dips 1-5 deg down and in during a blink, Collewijn et al. 1985;
the head does not), and the MetaHuman rig couples no blink curve to the head or neck. A head that dips with the
blinks is our pipeline's doing: a speech solve's head kept under ours, a chin dip of a turn that carries a gaze
blink, a beat nod on a stressed word that draws a blink (docs/unreal/research/blinks-head-stability.md).

What is measured, on the head's pitch (degrees, + = up) at any regular rate:

- nod depth of one blink: the largest departure of the pitch from the straight line (the chord) between the edges
  of the blink's window (`pre` before the lid starts to close, `post` after it is open again). A smooth turn or a
  slow drift through the window is a near-straight line and scores ~0; a dip and return scores its depth.
- the blink-triggered average (BTA): each blink's pitch from -0.2 s to +0.5 s around the onset, detrended by its
  chord, averaged over the blinks. Independent motion averages out; a nod locked to the blinks stays. The same over
  control onsets away from any blink is the baseline.
- in/out speed: the median of the peak pitch speed inside the blink windows against the same in equal windows
  outside them.
- jitter: what is left of each axis off a local cubic fit over 0.2 s (Savitzky-Golay: it follows a smooth turn
  however fast, so only buzz, snapped keys and twitches are left), as RMS and as spikes (frames over `spike_deg`).

Thresholds (`LIMITS`) are set so that the round-4 face fails (her gaze blinks alone dipped 0.8-1.6 deg, three of
nine blinks, perfkit offline) and a still head under the same blinks passes; see the research doc for the rest.
"""
from __future__ import annotations

import math

from . import curves as C

LIMITS = {
    "nod_deg": 0.5,          # a blink whose window departs from the chord by this much "nods"
    "nod_share": 0.2,        # FAIL when more than this share of the blinks nod
    "bta_deg": 0.3,          # FAIL when the blink-triggered average departs this far...
    "bta_ratio": 2.0,        # ...and by this many times the control's
    "speed_ratio": 2.5,      # FAIL when the head moves this much faster inside blink windows...
    "speed_min_deg_s": 6.0,  # ...and that peak speed is over this (a still head's ratios are noise)
    "jitter_rms_deg": 0.08,  # FAIL on buzz: RMS residual off the local fit, any axis
    "turn_deg": 20.0,        # a blink window whose head yaws this much is a turn's blink, not judged as a nod
    "turn_dip_deg": 2.0,     # ...but a turn whose pitch departs this much is flagged (head_turn_dip, a warning)
    "spike_deg": 0.5,        # FAIL on any residual over this (a twitch; the sharpest planned onsets leave ~0.4)
}
PRE, POST = 0.1, 0.12        # a blink's window around its lid motion (s)
BTA = (-0.2, 0.5)            # the blink-triggered average's span around the onset (s)


def _check(name, ok, metric, threshold, why):
    return {"name": name, "pass": bool(ok), "metric": round(metric, 4) if isinstance(metric, float) else metric,
            "threshold": threshold, "why": why}


def blink_windows(times: list, closure: list, threshold: float = 0.5) -> list:
    """[(onset, end)] of the blinks in a lid-closure signal (0 open .. 1 shut): where it is over `threshold`,
    widened to where the lid starts to move (closure over 0.1) and is back (under 0.1)."""
    out, i, n = [], 0, len(times)
    while i < n:
        if closure[i] >= threshold:
            a = i
            while a > 0 and closure[a - 1] > 0.1:
                a -= 1
            b = i
            while b < n - 1 and closure[b + 1] > 0.1:
                b += 1
            out.append((times[a], times[b]))
            i = b + 1
        else:
            i += 1
    return out


def _segment(times: list, values: list, t0: float, t1: float) -> tuple:
    idx = [i for i, t in enumerate(times) if t0 <= t <= t1]
    return [times[i] for i in idx], [values[i] for i in idx]


def chord_departure(times: list, values: list, t0: float, t1: float) -> list:
    """values minus the straight line joining them at t0 and t1, on the samples in [t0, t1]."""
    if t1 <= t0 or not times:
        return []
    a, b = C.at(times, values, t0), C.at(times, values, t1)
    ts, vs = _segment(times, values, t0, t1)
    return [v - (a + (b - a) * (t - t0) / (t1 - t0)) for t, v in zip(ts, vs)]


def nod_depth(times: list, pitch: list, onset: float, end: float, pre: float = PRE, post: float = POST) -> float:
    """The signed largest departure of the pitch from its chord over a blink's window (- = the head dipped)."""
    d = chord_departure(times, pitch, max(times[0], onset - pre), min(times[-1], end + post))
    return max(d, key=abs) if d else 0.0


def triggered_average(times: list, pitch: list, onsets: list, span: tuple = BTA, rate: float = 60.0) -> tuple:
    """(lags, mean detrended pitch) over the onsets whose span fits inside the signal."""
    lags = C.grid(span[0], span[1], rate)
    rows = []
    for o in onsets:
        a, b = o + span[0], o + span[1]
        if a < times[0] or b > times[-1]:
            continue
        va, vb = C.at(times, pitch, a), C.at(times, pitch, b)
        rows.append([C.at(times, pitch, o + lg) - (va + (vb - va) * (lg - span[0]) / (span[1] - span[0]))
                     for lg in lags])
    if not rows:
        return lags, []
    return lags, [sum(r[i] for r in rows) / len(rows) for i in range(len(lags))]


def control_onsets(t0: float, t1: float, windows: list, span: tuple = BTA, step: float = 0.37) -> list:
    """Onsets on a grid whose span touches no blink window: the baseline for the triggered average."""
    out, t = [], t0 - span[0]
    while t + span[1] <= t1:
        a, b = t + span[0], t + span[1]
        if not any(a < w1 + PRE and w0 - PRE < b for w0, w1 in windows):
            out.append(t)
        t += step
    return out


def _peak_speed(times: list, values: list, t0: float, t1: float) -> float:
    ts, vs = _segment(times, values, t0, t1)
    if len(ts) < 3:
        return 0.0
    return max(abs(x) for x in C.derivative(ts, vs))


def savgol(values: list, half: int) -> list:
    """Savitzky-Golay smoothing (a cubic fitted over 2*half+1 samples, its centre value): it follows a smooth move
    however fast, so what it leaves out is buzz and spikes, not turns. The ends keep their values."""
    m = max(2, int(half))
    den = (2 * m - 1) * (2 * m + 1) * (2 * m + 3)
    w = [(3 * (3 * m * m + 3 * m - 1) - 15 * j * j) / den for j in range(-m, m + 1)]
    n = len(values)
    return [sum(w[j + m] * values[i + j] for j in range(-m, m + 1)) if m <= i < n - m else values[i]
            for i in range(n)]


def jitter(times: list, values: list, window_s: float = 0.2) -> dict:
    """{"rms_deg", "max_deg", "residual"} of one axis against its local cubic fit over `window_s` (savgol): a
    smooth turn, nod or drift leaves ~0; a buzz, a snapped key or a one-frame twitch does not."""
    if len(times) < 8:
        return {"rms_deg": 0.0, "max_deg": 0.0, "residual": [0.0] * len(times)}
    rate = (len(times) - 1) / (times[-1] - times[0])
    half = max(2, round(window_s * rate / 2))
    res = [v - w for v, w in zip(values, savgol(values, half))]
    core = res[half:-half] or res
    return {"rms_deg": math.sqrt(sum(x * x for x in core) / len(core)), "max_deg": max(abs(x) for x in core),
            "residual": res}


def check(times: list, pitch: list, blinks: list, yaw: list | None = None, roll: list | None = None,
          limits: dict | None = None, jitter_s: float = 0.2, source: str = "curves", seen: list | None = None) -> dict:
    """Every head-stability check on a regularly sampled head (degrees) and its blinks [(onset, end)] (s).
    Returns {"pass", "failed", "checks", "blinks": [{"t", "nod_deg"}], "bta": {...}, "jitter": {...}}; each
    check says what to do about a failure. `source` (curves|bones|render) only words the messages."""
    L = {**LIMITS, **(limits or {})}
    checks, per = [], []
    given = list(blinks)
    blinks = [(float(a), float(b)) for a, b in given if b > times[0] and a < times[-1]]
    if given and not blinks:  # r5 box: the blinks on another clock than the samples: never judge that as "no nods"
        raise ValueError(f"none of the {len(given)} blinks ({given[0][0]:.2f}-{given[-1][1]:.2f} s) falls inside the "
                         f"samples ({times[0]:.2f}-{times[-1]:.2f} s): give both on the same clock")
    fix = ("perf.face blink_head='still' (the default) and solver_head='replace' (the default): the head is then "
           "perfkit's alone and no blink window carries a nod; then re-check")
    # a blink whose window runs off either end of the samples has no chord to judge against (r5 box: his last blink,
    # cut by the end of his screen time, scored 5.8 deg): listed as "edge", never judged
    cut = [{"t": round(a, 3), "nod_deg": round(nod_depth(times, pitch, a, b), 3)} for a, b in blinks
            if a - PRE < times[0] or b + POST > times[-1]]
    blinks = [(a, b) for a, b in blinks if a - PRE >= times[0] and b + POST <= times[-1]]
    # `seen`: the spans [(t0, t1)] the face is on screen (the shots' cast): a blink off screen is listed, not judged
    # (r5 box: his return turn in S16, her single)
    unseen = []
    if seen is not None:
        unseen = [{"t": round(a, 3), "nod_deg": round(nod_depth(times, pitch, a, b), 3)} for a, b in blinks
                  if not any(s0 <= a and b <= s1 for s0, s1 in seen)]
        blinks = [(a, b) for a, b in blinks if any(s0 <= a and b <= s1 for s0, s1 in seen)]
    # a blink on a big head turn (the gaze-evoked blink: every head turn over ~17 deg carries one, Evinger 1994) is
    # not a nod: the head's pitch along a 60-95 deg turn is the turn's path (r5 box: his return turn dipped 4.6 deg
    # with its blink, his face flat). Listed as "turn" with the departure; head_turn_dip warns on a big one.
    turns = []
    if yaw:
        def swing(a, b):
            seg = _segment(times, yaw, max(times[0], a - PRE), min(times[-1], b + POST))[1]
            return max(seg) - min(seg) if seg else 0.0
        turns = [{"t": round(a, 3), "nod_deg": round(nod_depth(times, pitch, a, b), 3), "yaw_deg": round(swing(a, b), 1)}
                 for a, b in blinks if swing(a, b) >= L["turn_deg"]]
        blinks = [(a, b) for a, b in blinks if swing(a, b) < L["turn_deg"]]
    if blinks:
        for a, b in blinks:
            per.append({"t": round(a, 3), "nod_deg": round(nod_depth(times, pitch, a, b), 3)})
        nods = [p for p in per if abs(p["nod_deg"]) >= L["nod_deg"]]
        share = len(nods) / len(per)
        worst = max(per, key=lambda p: abs(p["nod_deg"]))
        checks.append(_check(
            "blink_nod", share <= L["nod_share"], share, L["nod_share"],
            f"{len(nods)} of {len(per)} blinks move the head over {L['nod_deg']} deg (worst {worst['nod_deg']:+.2f} "
            f"deg at {worst['t']:.2f} s; - = down). A blink never moves the head: {fix}"))
        lags, bta = triggered_average(times, pitch, [a for a, _ in blinks])
        _, ctl = triggered_average(times, pitch, control_onsets(times[0], times[-1], blinks))
        bta_dev = max((abs(x) for x in bta), default=0.0)
        ctl_dev = max((abs(x) for x in ctl), default=0.0)
        ratio = bta_dev / max(ctl_dev, 0.05)
        checks.append(_check(
            "blink_locked", not (bta_dev >= L["bta_deg"] and ratio >= L["bta_ratio"]), bta_dev, L["bta_deg"],
            f"averaged over the blinks the head departs {bta_dev:.2f} deg ({ratio:.1f}x the {ctl_dev:.2f} deg away "
            f"from blinks): a nod that comes with every blink, even where each one is small. {fix}"))
        inside = [_peak_speed(times, pitch, a - PRE, b + POST) for a, b in blinks]
        width = sorted(b - a + PRE + POST for a, b in blinks)[len(blinks) // 2]
        outside = [_peak_speed(times, pitch, t, t + width)
                   for t in control_onsets(times[0], times[-1], blinks, (0.0, width), width)]
        med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0.0  # noqa: E731
        sp_in, sp_out = med(inside), med(outside)
        sp_ratio = sp_in / max(sp_out, 0.5)
        checks.append(_check(
            "blink_speed", not (sp_ratio >= L["speed_ratio"] and sp_in >= L["speed_min_deg_s"]), sp_ratio,
            L["speed_ratio"],
            f"the head's pitch moves {sp_in:.1f} deg/s (median peak) inside blink windows against {sp_out:.1f} deg/s "
            f"outside. {fix}"))
    else:
        bta, lags, bta_dev, ctl_dev = [], [], 0.0, 0.0
    if turns:
        big = max(turns, key=lambda x: abs(x["nod_deg"]))
        ok = abs(big["nod_deg"]) < L["turn_dip_deg"]
        c = _check("head_turn_dip", ok, abs(big["nod_deg"]), L["turn_dip_deg"],
                   f"the head's pitch departs {big['nod_deg']:+.2f} deg along a {big['yaw_deg']} deg turn at "
                   f"{big['t']:.2f} s (the blink there is the turn's own): a dip or bob in the turn's path; on screen, "
                   "look at the neck/torso turn timing (perf.turn_head, the torso plan)")
        c["severity"] = "warn"
        checks.append(c)
    jit = {}
    for name, v in (("pitch", pitch), ("yaw", yaw), ("roll", roll)):
        if v:
            j = jitter(times, v, jitter_s)
            spikes = [round(times[i], 3) for i, x in enumerate(j["residual"]) if abs(x) > L["spike_deg"]]
            edge = max(1, int(len(times) / max(times[-1] - times[0], 1e-6) * 0.1))
            spikes = [t for t in spikes if times[edge] <= t <= times[-1 - edge]]
            jit[name] = {"rms_deg": round(j["rms_deg"], 4), "max_deg": round(j["max_deg"], 3), "spikes": spikes[:20]}
    if jit:
        rms = max(j["rms_deg"] for j in jit.values())
        spikes = sorted({t for j in jit.values() for t in j["spikes"]})
        axis = max(jit, key=lambda k: jit[k]["rms_deg"])
        checks.append(_check(
            "head_buzz", rms <= L["jitter_rms_deg"] and not spikes, rms, L["jitter_rms_deg"],
            f"{axis} carries {rms:.3f} deg RMS of buzz (off its {jitter_s} s local fit), {len(spikes)} spike frames over "
            f"{L['spike_deg']} deg (first {spikes[:5]}): a solver's buzz or a snapped key. perf.face "
            "solver_head='replace' (or 'clean': spike removal and a low-pass), and no beat nods faster than 0.15 s"))
    failed = [c["name"] for c in checks if not c["pass"] and c.get("severity") != "warn"]
    return {"pass": not failed, "failed": failed, "checks": checks, "source": source, "blinks": per, "edge": cut,
            "turns": turns, "unseen": unseen,
            "bta": {"lags": [round(x, 3) for x in lags][::3], "mean_deg": [round(x, 3) for x in bta][::3],
                    "peak_deg": round(bta_dev, 3), "control_deg": round(ctl_dev, 3)},
            "jitter": jit}


# --- inputs: rig curves, sampled bones -----------------------------------------------------------------------------

def from_curves(curves: dict, signs=None, rate: float = 60.0, threshold: float = 0.5) -> dict:
    """{"times", "pitch", "yaw", "roll", "blinks"} in the character's frame from a face animation's curves (the head
    curves through rig.HeadSigns, the blinks from eyeBlinkL/R)."""
    from .head import from_rig
    from .rig import BLINKS
    head = from_rig(curves, signs)
    spans = [curves[n][0] for n in BLINKS if n in curves and curves[n][0]]
    spans += [t for t, _ in head.values() if t]
    if not spans:
        return {"times": [], "pitch": [], "yaw": [], "roll": [], "blinks": []}
    t0, t1 = min(s[0] for s in spans), max(s[-1] for s in spans)
    g = C.grid(t0, t1, rate)
    out = {"times": g}
    for k in ("pitch", "yaw", "roll"):
        out[k] = C.resample(*head[k], g) if k in head else [0.0] * len(g)
    clos = [0.0] * len(g)
    for n in BLINKS:
        if n in curves:
            clos = [max(a, b) for a, b in zip(clos, C.resample(*curves[n], g))]
    out["blinks"] = blink_windows(g, clos, threshold)
    return out


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _norm(v):
    n = math.sqrt(_dot(v, v)) or 1.0
    return [x / n for x in v]


def from_bones(frames: list, fps: float, samples: list, forward: list, up: list = (0.0, 0.0, 1.0)) -> dict:
    """{"times", "pitch", "yaw", "roll"} of a head bone sampled in Sequencer: `samples` one per frame as seq.sample
    gives them ([x, y, z, axis_x(3), axis_y(3), axis_z(3)], world), `forward` the actor's forward (world). The
    bone's local axes are whatever the skeleton has: the one nearest the actor's forward at the first frame is the
    face's forward, the one nearest the actor's side its lateral. pitch = elevation of that forward (+ up), yaw its
    heading about `up` against the actor's forward (+ = to the actor's left in a left-handed Unreal world: the sign
    is the world's; only motion matters here), roll the lateral axis's elevation."""
    up = _norm(list(up))
    fwd = _norm(list(forward))
    side = _norm([up[1] * fwd[2] - up[2] * fwd[1], up[2] * fwd[0] - up[0] * fwd[2], up[0] * fwd[1] - up[1] * fwd[0]])
    if not samples:
        return {"times": [], "pitch": [], "yaw": [], "roll": []}
    axes0 = [samples[0][3:6], samples[0][6:9], samples[0][9:12]]
    fi = max(range(3), key=lambda i: abs(_dot(axes0[i], fwd)))
    fs = 1.0 if _dot(axes0[fi], fwd) >= 0 else -1.0
    li = max((i for i in range(3) if i != fi), key=lambda i: abs(_dot(axes0[i], side)))
    ls = 1.0 if _dot(axes0[li], side) >= 0 else -1.0
    pitch, yaw, roll = [], [], []
    prev = None
    for s in samples:
        ax = [s[3:6], s[6:9], s[9:12]]
        f = _norm([fs * x for x in ax[fi]])
        lat = _norm([ls * x for x in ax[li]])
        pitch.append(math.degrees(math.asin(max(-1.0, min(1.0, _dot(f, up))))))
        y = math.degrees(math.atan2(_dot(f, side), _dot(f, fwd)))
        if prev is not None:  # unwrap
            while y - prev > 180:
                y -= 360
            while y - prev < -180:
                y += 360
        prev = y
        yaw.append(y)
        roll.append(math.degrees(math.asin(max(-1.0, min(1.0, _dot(lat, up))))))
    return {"times": [f / fps for f in frames], "pitch": pitch, "yaw": yaw, "roll": roll,
            "axes": {"forward": ["xyz"[fi], fs], "lateral": ["xyz"[li], ls]}}


# --- the fix: keep the head out of the blinks ------------------------------------------------------------------------

def _hermite(p0, m0, p1, m1, u, h):
    u2, u3 = u * u, u * u * u
    return ((2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * h * m0 + (-2 * u3 + 3 * u2) * p1
            + (u3 - u2) * h * m1)


def bridge(times: list, values: list, t0: float, t1: float) -> list:
    """values with [t0, t1] replaced by the cubic that joins the outside smoothly (same value and slope at both
    ends): whatever happened inside the window (a dip, a spike) is gone; a turn or a drift through it goes on."""
    n = len(times)
    if n < 4 or t1 <= t0:
        return list(values)
    dt = (times[-1] - times[0]) / (n - 1)
    a, b = max(times[0], t0), min(times[-1], t1)
    if b - a < 2 * dt:
        return list(values)
    p0, p1 = C.at(times, values, a), C.at(times, values, b)
    m0 = (p0 - C.at(times, values, a - 2 * dt)) / (2 * dt) if a - 2 * dt >= times[0] else 0.0
    m1 = (C.at(times, values, b + 2 * dt) - p1) / (2 * dt) if b + 2 * dt <= times[-1] else 0.0
    h = b - a
    return [_hermite(p0, m0, p1, m1, (t - a) / h, h) if a < t < b else v for t, v in zip(times, values)]


def still_through_blinks(times: list, values: list, blinks: list, tol_deg: float = 0.15, pre: float = PRE,
                         post: float = POST) -> tuple:
    """(values, n bridged): every blink window whose head departs from its chord by more than `tol_deg` is bridged
    (see `bridge`). Windows that overlap are merged first."""
    spans = sorted((a - pre, b + post) for a, b in blinks)
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    out, n = list(values), 0
    for a, b in merged:
        d = chord_departure(times, out, max(times[0], a), min(times[-1], b))
        if d and max(abs(x) for x in d) > tol_deg:
            out = bridge(times, out, a, b)
            n += 1
    return out, n


def hampel(values: list, half: int = 3, k: float = 3.0) -> tuple:
    """(values, n replaced): a sample further than k * 1.4826 * MAD from the median of its 2*half+1 neighbours is
    replaced by that median (spike removal before any low-pass, so a spike does not smear into a bump)."""
    out, n = list(values), 0
    for i in range(len(values)):
        win = sorted(values[max(0, i - half):i + half + 1])
        med = win[len(win) // 2]
        mad = sorted(abs(x - med) for x in win)[len(win) // 2] * 1.4826
        if abs(values[i] - med) > k * max(mad, 1e-4):
            out[i] = med
            n += 1
    return out, n


class OneEuro:
    """The One Euro filter (Casiez, Roussel & Vogel, CHI 2012): a low-pass whose cutoff rises with speed, so a still
    head is calm and a turn is not lagged. Tune: beta=0, lower `min_cutoff` until a hold is calm, then raise `beta`
    until fast moves stop lagging; `d_cutoff` 1 Hz. For head degrees at 24-60 Hz: min_cutoff 0.8, beta 0.02."""

    def __init__(self, rate: float, min_cutoff: float = 0.8, beta: float = 0.02, d_cutoff: float = 1.0):
        self.rate, self.min_cutoff, self.beta, self.d_cutoff = rate, min_cutoff, beta, d_cutoff

    def _a(self, cutoff):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau * self.rate)

    def run(self, values: list) -> list:
        if not values:
            return []
        x, dx, out = values[0], 0.0, [values[0]]
        for v in values[1:]:
            d = (v - x) * self.rate
            dx += self._a(self.d_cutoff) * (d - dx)
            x += self._a(self.min_cutoff + self.beta * abs(dx)) * (v - x)
            out.append(x)
        return out


def clean(times: list, values: list, blinks: list = (), rate: float = 60.0, cutoff_hz: float = 1.5,
          gain: float = 0.5) -> tuple:
    """A speech solver's head channel made safe to keep under perfkit's: on a regular grid, spikes removed (Hampel),
    each blink window bridged (the solver's own blinks and ours: its head nods with its blinks), low-passed without
    delay at `cutoff_hz`, scaled about its mean by `gain`. Returns (grid, values, {"spikes", "bridged"})."""
    if not times:
        return [], [], {"spikes": 0, "bridged": 0}
    g = C.grid(times[0], times[-1], rate)
    v = C.resample(times, values, g)
    v, spikes = hampel(v)
    v, bridged = still_through_blinks(g, v, list(blinks), tol_deg=0.0)
    v = C.lowpass(v, rate, cutoff_hz)
    mean = sum(v) / len(v)
    return g, [mean + (x - mean) * gain for x in v], {"spikes": spikes, "bridged": bridged}
