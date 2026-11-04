"""Numbers that say whether a performance will read as alive or robotic, without looking at it.

Each check returns the shape every QA check uses: {"name", "pass", "metric", "threshold", "why"}; `report(curves)`
runs the lot on an animation's curves ({name: (times, values)}) and adds a summary. The thresholds are the operator's
"too robotic" complaints turned into measurements:

- frozen_head      share of time the head is perfectly still (no micro-motion): robotic when over 20%
- head_linear      share of the head's moving time at constant speed (straight lines between keys): robotic over 50%
- head_jitter      share of the head's motion energy above 6 Hz: a solver's buzz
- blink_rate       blinks per minute in 8..35
- blink_regularity coefficient of variation of the intervals: under 0.25 is a metronome
- blink_shape      the open must take longer than the close
- asymmetry        the two sides of the face are not identical (|L - R| over the expression, > 3%)
- expression_range the face moves at all beyond the mouth (brows/cheeks/eyes peak over 0.1)
- gaze_shifts      the eyes move (some eye-look change over 2 deg every 10 s of a long shot)
"""
from __future__ import annotations

import math

from . import blinks as B
from . import curves as C
from .rig import PREFIX, HeadSigns


def _check(name, ok, metric, threshold, why):
    return {"name": name, "pass": bool(ok), "metric": round(metric, 4) if isinstance(metric, float) else metric,
            "threshold": threshold, "why": why}


def _regular(curve: tuple, rate: float = 60.0) -> tuple:
    t, v = curve
    if not t:
        return [], []
    g = C.grid(t[0], t[-1], rate)
    return g, C.resample(t, v, g)


def head_speed(curves: dict, rate: float = 60.0) -> tuple:
    """(times, angular speed deg/s) of the head from HeadYaw/Pitch/Roll."""
    names = [n for n in ("HeadYaw", "HeadPitch", "HeadRoll") if n in curves]
    if not names:
        return [], []
    t0 = min(curves[n][0][0] for n in names if curves[n][0])
    t1 = max(curves[n][0][-1] for n in names if curves[n][0])
    g = C.grid(t0, t1, rate)
    d = [C.derivative(g, C.resample(*curves[n], g)) for n in names]
    return g, [math.sqrt(sum(x[i] ** 2 for x in d)) for i in range(len(g))]


def frozen_head(curves: dict, still_deg_s: float = 0.05, limit: float = 0.2) -> dict:
    t, sp = head_speed(curves)
    if not sp:
        return _check("frozen_head", False, 1.0, limit, "no head curves (HeadYaw/Pitch/Roll): the head never moves")
    share = sum(1 for s in sp if s < still_deg_s) / len(sp)
    return _check("frozen_head", share <= limit, share, limit,
                  f"{share:.0%} of the time the head is perfectly still (under {still_deg_s} deg/s); a living head "
                  f"always drifts a little: add micro-motion (perf.face head layer)")


def head_linear(curves: dict, limit: float = 0.5, vmin_deg_s: float = 4.0, amax_deg_s2: float = 6.0) -> dict:
    """Share of the time the head is moving (over `vmin_deg_s`) at a constant velocity (acceleration under
    `amax_deg_s2`): keyframes joined by straight lines score ~0.9-1.0, eased organic motion ~0.1-0.3."""
    names = [n for n in ("HeadYaw", "HeadPitch", "HeadRoll") if n in curves and curves[n][0]]
    if not names:
        return _check("head_linear", True, 0.0, limit, "no head curves")
    t0 = min(curves[n][0][0] for n in names)
    t1 = max(curves[n][0][-1] for n in names)
    g = C.grid(t0, t1, 30.0)  # at frame rate: dense keys are not straight lines
    vs = [C.derivative(g, C.resample(*curves[n], g)) for n in names]
    acc = [C.derivative(g, v) for v in vs]
    moving = linear = 0
    for i in range(len(g)):
        if math.sqrt(sum(v[i] ** 2 for v in vs)) > vmin_deg_s:
            moving += 1
            if math.sqrt(sum(a[i] ** 2 for a in acc)) < amax_deg_s2:
                linear += 1
    if not moving:
        return _check("head_linear", True, 0.0, limit, "the head never moves faster than "
                      f"{vmin_deg_s} deg/s (fine for a still listener; see frozen_head)")
    share = linear / moving
    return _check("head_linear", share <= limit, share, limit,
                  f"{share:.0%} of the head's motion is at constant speed (straight lines between keys): robotic "
                  "above 50%; ease it (perf.face solver_head='soften' or 'replace')")


def head_jitter(curves: dict, cutoff_hz: float = 6.0, limit: float = 0.25) -> dict:
    names = [n for n in ("HeadYaw", "HeadPitch", "HeadRoll") if n in curves]
    if not names:
        return _check("head_jitter", True, 0.0, limit, "no head curves")
    hi = tot = 0.0
    for n in names:
        g, v = _regular(curves[n])
        if len(v) < 8:
            continue
        lo = C.lowpass(v, 60.0, cutoff_hz)
        dv = C.derivative(g, v)
        dlo = C.derivative(g, lo)
        tot += sum(x * x for x in dv)
        hi += sum((a - b) ** 2 for a, b in zip(dv, dlo))
    share = hi / tot if tot > 0 else 0.0
    return _check("head_jitter", share <= limit, share, limit,
                  f"{share:.0%} of the head's motion is buzz above {cutoff_hz} Hz: soften it (perf.face "
                  "solver_head='soften')")


def blink_stats(curves: dict) -> dict:
    name = PREFIX + "eyeBlinkL"
    if name not in curves:
        return {"count": 0}
    t, v = _regular(curves[name], 120.0)
    bl = B.detect(t, v, 0.5)
    dur = (t[-1] - t[0]) if t else 0.0
    starts = [b[0] for b in bl]
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    mean = sum(gaps) / len(gaps) if gaps else 0.0
    cv = (math.sqrt(sum((g - mean) ** 2 for g in gaps) / len(gaps)) / mean) if gaps and mean > 0 else 0.0
    # close vs open: time from 10% to the peak, and from the peak down to 10%, per blink
    closes, opens = [], []
    for a, b, peak in bl:
        idx = [i for i, x in enumerate(t) if a - 0.15 <= x <= b + 0.15]
        i_pk = max(idx, key=lambda i: v[i])
        low = 0.1 * v[i_pk]
        i = i_pk
        while i > 0 and v[i] > low:  # back to where the lid started closing
            i -= 1
        k = i_pk
        while k + 1 < len(v) and v[k + 1] >= v[i_pk] - 1e-3:  # the shut plateau counts toward neither
            k += 1
        j = k
        while j + 1 < len(v) and v[j] > low:  # on to where it is open again
            j += 1
        closes.append(t[i_pk] - t[i])
        opens.append(t[j] - t[k])
    return {"count": len(bl), "per_min": (len(bl) / dur * 60.0) if dur > 0 else 0.0, "interval_cv": cv,
            "close_s": sum(closes) / len(closes) if closes else 0.0,
            "open_s": sum(opens) / len(opens) if opens else 0.0, "duration_s": dur}


def blink_checks(curves: dict, min_shot_s: float = 6.0) -> list:
    st = blink_stats(curves)
    if not st.get("count"):
        dur = 0.0
        for n, (t, _) in curves.items():
            if t:
                dur = max(dur, t[-1] - t[0])
        ok = dur < min_shot_s
        return [_check("blink_rate", ok, 0.0, [8, 35], f"no blinks in {dur:.1f} s: a face that never blinks stares; "
                       "add the blink layer (perf.face layers=['blinks'])")]
    d = st["duration_s"]
    if d >= 20.0:
        ok = 8 <= st["per_min"] <= 35
    else:  # too short for a rate: at least one per 8 s and no more than one per 1.2 s
        ok = int(d // 8) <= st["count"] <= max(1, math.ceil(d / 1.2))
    out = [_check("blink_rate", ok, st["per_min"], [8, 35],
                  f"{st['count']} blinks in {d:.1f} s = {st['per_min']:.1f}/min (people: ~12-26; shots under 20 s "
                  "are judged by count)")]
    if st["count"] >= 4:
        out.append(_check("blink_regularity", st["interval_cv"] >= 0.25, st["interval_cv"], 0.25,
                          f"the blink intervals vary by {st['interval_cv']:.2f} (std/mean); under 0.25 they tick like "
                          "a metronome"))
    out.append(_check("blink_shape", st["open_s"] > st["close_s"], round(st["open_s"] - st["close_s"], 3), 0.0,
                      f"lids close in {st['close_s'] * 1000:.0f} ms and open in {st['open_s'] * 1000:.0f} ms; a real "
                      "blink opens slower than it closes"))
    return out


def asymmetry(curves: dict, limit: float = 0.03) -> dict:
    pairs = []
    for n in curves:
        if n.startswith(PREFIX) and n.endswith("L") and not n.endswith("eyeBlinkL") and "eyeLook" not in n:
            r = n[:-1] + "R"
            if r in curves:
                pairs.append((n, r))
    if not pairs:
        return _check("asymmetry", True, 0.0, limit, "no paired expression curves")
    diffs, peak = [], 0.0
    for l_, r in pairs:
        tl, vl = curves[l_]
        tr, vr = curves[r]
        if not tl or not tr:
            continue
        g = C.grid(min(tl[0], tr[0]), max(tl[-1], tr[-1]), 30.0)
        a, b = C.resample(tl, vl, g), C.resample(tr, vr, g)
        m = max(max(a), max(b))
        if m < 0.05:
            continue
        peak = max(peak, m)
        act = [(x, y) for x, y in zip(a, b) if max(x, y) > 0.02]  # where the expression is on
        diffs.append(sum(abs(x - y) for x, y in act) / max(1e-6, sum(max(x, y) for x, y in act)))
    if not diffs:
        return _check("asymmetry", True, 0.0, limit, "no expression strong enough to judge")
    d = sum(diffs) / len(diffs)
    return _check("asymmetry", d >= limit, d, limit,
                  f"the face's two sides differ by {d:.1%} of the expression over {len(diffs)} paired curves; a perfectly "
                  "mirrored face looks synthetic (give expressions asym=0.1-0.3)")


def expression_range(curves: dict, limit: float = 0.1) -> dict:
    keys = ("brow", "eyeCheekRaise", "eyeSquint", "eyeWiden", "noseWrinkle", "mouthCornerPull")
    peak = 0.0
    for n, (t, v) in curves.items():
        if n.startswith(PREFIX) and n[len(PREFIX):].startswith(keys) and v:
            peak = max(peak, max(v))
    return _check("expression_range", peak >= limit, peak, limit,
                  f"the upper face peaks at {peak:.2f}; under {limit} it reads blank (add brow flashes on emphasis "
                  "or a mood)")


def gaze_activity(curves: dict, signs: HeadSigns | None = None, min_shift_deg: float = 2.0,
                  per_s: float = 10.0) -> dict:
    from .eyes import angles_from_rig
    a = angles_from_rig(curves, signs)
    t = a.get("times") or []
    if len(t) < 2:
        return _check("gaze_shifts", True, 0.0, 0, "no eye-look curves")
    dur = t[-1] - t[0]
    n, last = 0, a["L"][0]
    for y, p in a["L"]:
        if math.hypot(y - last[0], p - last[1]) >= min_shift_deg:
            n += 1
            last = (y, p)
    need = int(dur // per_s)
    return _check("gaze_shifts", n >= need, n, need,
                  f"{n} eye movements of {min_shift_deg}+ deg in {dur:.1f} s; eyes that never move stare")


def report(curves: dict, signs: HeadSigns | None = None) -> dict:
    """Every check on an animation's curves, and {"pass": all passed, "failed": [names]}."""
    checks = [frozen_head(curves), head_linear(curves), head_jitter(curves), *blink_checks(curves),
              asymmetry(curves), expression_range(curves), gaze_activity(curves, signs)]
    failed = [c["name"] for c in checks if not c["pass"]]
    return {"pass": not failed, "failed": failed, "checks": checks, "blinks": blink_stats(curves)}
