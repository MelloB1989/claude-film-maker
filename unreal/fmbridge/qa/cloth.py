"""Is the cloth simulation sound, and is it alive? Pure arithmetic on vertex positions (no `unreal`, no numpy).

The input is, per frame, the garment's SIMULATED positions and its SKINNED positions (the same vertices with the max
distance scaled to 0: where the body alone would put them), sampled vertices only. Their difference D = sim - skinned
is the cloth's own motion, with the body's motion taken out. So:

- explosion / NaN: D is huge or not finite;
- velocity spikes: D changes faster than fabric moves on a presenter (cm/s);
- max distance exceeded: D leaves the painted max distance (the maps did not reach the solver);
- dead ("armour"): D does not vary in the free zones (hem, sleeves) while the body moves;
- anchor slip: D is not ~0 in the pinned zones (collar, shoulder seam): the collar slides into the neck;
- jitter: D buzzes frame to frame (second difference) while the body is still;
- cold start: D changes fast in the first frames and calms down later: the shot was not pre-rolled.

Penetration under simulation is qa.clip's (depth layers, agent-02's) on the same frames; qa.cloth runs it when asked.

    r = judge(frames, sim, skin, zones, max_distance, fps=24, free=["torso", "sleeve"], pinned=["collar"])
    r["pass"], r["issues"], r["metrics"]["zones"]["sleeve"]["motion_cm"]
"""
from __future__ import annotations

import math

from .issues import issue, worst

DEFAULTS = {
    "explode_cm": 25.0,           # |D| beyond this anywhere: the cloth blew up
    "explode_margin_cm": 5.0,     # ... or beyond the vertex's own max distance by this much
    "maxdist_tol_cm": 1.0,        # |D| beyond max distance + this counts as exceeding it
    "maxdist_frac": 0.01,         # share of vertex-frames allowed beyond (collision pushes some out a little)
    "spike_cm_s": 120.0,          # fabric on a presenter does not move this fast relative to the body
    "alive_min_cm": 0.15,         # free-zone motion (temporal std of D, p75) below this while the body moves: dead
    "alive_good_cm": 0.3,         # below this: warn (stiff)
    "body_moves_cm": 2.0,         # the body's own path length (mean over the free vertices) needed to judge "alive"
    "pin_tol_cm": 0.3,            # pinned zones' |D| p95 above this: the anchor slips
    "jitter_cm": 0.12,            # p95 of the second difference of D in still frames
    "still_cm_frame": 0.05,       # a frame is "still" when the body's vertices move less than this (cm/frame)
    "cold_frames": 4,             # the first frames judged for a cold start
    "cold_ratio": 3.0,            # first frames' D speed this many times the rest's ...
    "cold_min_cm_frame": 0.2,     # ... and above this (cm/frame)
}


def _finite(p) -> bool:
    return all(isinstance(c, (int, float)) and math.isfinite(c) for c in p)


def _d(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _n(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _pct(vals: list, q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _std3(seq: list) -> float:
    """The spread of a 3-vector over time: sqrt of the summed per-axis variances (cm)."""
    n = len(seq)
    if n < 2:
        return 0.0
    m = [sum(p[i] for p in seq) / n for i in range(3)]
    return math.sqrt(sum((p[i] - m[i]) ** 2 for p in seq for i in range(3)) / n)


def judge(frames: list, sim: list, skin: list, zones: list, max_distance: list, *, fps: float = 24.0,
          free: list | None = None, pinned: list | None = None, hem: list | None = None, subject: str = "",
          **thresholds) -> dict:
    """The verdict on one garment over consecutive frames. `sim`/`skin`: per frame, a list of [x, y, z] cm (same
    vertices, same order); `zones`: each vertex's zone name; `max_distance`: each vertex's painted max distance (cm);
    `hem`: optional bools, the vertices at the free end of a free zone (judged on their own as "hem").
    Returns {"pass", "verdict", "issues", "metrics": {"frames", "vertices", "max_disp_cm", "max_speed_cm_s",
    "spike_frame", "zones": {zone: {"n", "drape_cm", "motion_cm", "slip_cm", "body_path_cm"}}, ...}}."""
    th = {**DEFAULTS, **thresholds}
    free, pinned = list(free or []), list(pinned or [])
    issues = []
    nf, nv = len(frames), (len(sim[0]) if sim else 0)
    if nf < 3 or nv == 0 or len(sim) != nf or len(skin) != nf:
        return {"pass": False, "verdict": "fail", "issues": [issue(
            "cloth.no_data", "fail", f"need >= 3 frames of sim and skinned positions (got {nf} frames, {nv} vertices)",
            "run qa.cloth over the shot's frames; check cloth.describe shows a simulating garment", subject=subject)],
            "metrics": {"frames": nf, "vertices": nv}}
    # 1. finite
    for f in range(nf):
        bad = sum(1 for p in sim[f] if not _finite(p))
        if bad:
            issues.append(issue("cloth.nan", "fail", f"{bad} simulated vertices are NaN/Inf at frame {frames[f]}",
                                "the solver diverged: lower subdivision/iterations changes nothing here; reset the "
                                "cloth at the shot start (cloth.preroll) and check the physics asset has no "
                                "zero-size shapes", frame=frames[f], subject=subject, value=bad))
            return {"pass": False, "verdict": "fail", "issues": issues, "metrics": {"frames": nf, "vertices": nv}}
    D = [[_d(sim[f][i], skin[f][i]) for i in range(nv)] for f in range(nf)]
    mag = [[_n(D[f][i]) for i in range(nv)] for f in range(nf)]
    max_disp = max(max(row) for row in mag)
    # 2. not simulating at all
    if max_disp < 1e-3:
        issues.append(issue("cloth.not_simulating", "fail",
                            f"the garment never left its skinned pose over {nf} frames (max {max_disp:.4f} cm)",
                            "cloth.describe: is there clothing data bound to a section, is simulation enabled, is "
                            "the max distance painted (cloth.setup)? If it all says yes, the position reader does not "
                            "see cloth (GPU probe P-C3 in docs/unreal/cloth.md)", subject=subject))
    # 3. explosion
    for f in range(nf):
        for i in range(nv):
            lim = min(th["explode_cm"], max_distance[i] + th["explode_margin_cm"]) if max_distance else th["explode_cm"]
            if mag[f][i] > max(lim, th["explode_margin_cm"]):
                issues.append(issue("cloth.explosion", "fail",
                                    f"a vertex is {mag[f][i]:.1f} cm from its skinned place at frame {frames[f]} "
                                    f"(max distance {max_distance[i]:.1f} cm, zone {zones[i]})",
                                    "the cloth blew up: a teleport without reset at a cut (cloth.setup sets the "
                                    "teleport thresholds), a cold start (cloth.preroll), or collision shapes "
                                    "intersecting the garment at rest", frame=frames[f], subject=subject,
                                    value=round(mag[f][i], 2), expected=round(lim, 2)))
                break
        else:
            continue
        break
    # 4. max distance exceeded
    if max_distance:
        over = sum(1 for f in range(nf) for i in range(nv) if mag[f][i] > max_distance[i] + th["maxdist_tol_cm"])
        frac = over / float(nf * nv)
        if frac > th["maxdist_frac"]:
            issues.append(issue("cloth.max_distance_exceeded", "warn",
                                f"{frac:.1%} of vertex-frames leave their painted max distance by > "
                                f"{th['maxdist_tol_cm']} cm", "the painted map is not what the solver uses: re-run "
                                "cloth.setup and read cloth.describe's map stats; or collision pushes the cloth out "
                                "(physics asset capsules too fat)", subject=subject, value=round(frac, 4),
                                expected=th["maxdist_frac"]))
    # 5. speed (relative to the body)
    max_speed, spike_frame = 0.0, None
    for f in range(1, nf):
        for i in range(nv):
            v = _n(_d(D[f][i], D[f - 1][i])) * fps
            if v > max_speed:
                max_speed, spike_frame = v, frames[f]
    if max_speed > th["spike_cm_s"]:
        issues.append(issue("cloth.velocity_spike", "fail",
                            f"cloth moves {max_speed:.0f} cm/s relative to the body at frame {spike_frame} "
                            f"(limit {th['spike_cm_s']:.0f})", "a pop: a teleport at a cut (cloth.setup teleport "
                            "thresholds + reset), an animation jump (seq: check the body keys at that frame), or too "
                            "little damping (preset damping up)", frame=spike_frame, subject=subject,
                            value=round(max_speed, 1), expected=th["spike_cm_s"]))
    # body motion per frame (mean over vertices) and still frames
    body_step = [0.0] + [sum(_n(_d(skin[f][i], skin[f - 1][i])) for i in range(nv)) / nv for f in range(1, nf)]
    still = [f for f in range(1, nf - 1) if body_step[f] < th["still_cm_frame"] and body_step[f + 1] < th["still_cm_frame"]]
    # 6. per zone
    zm = {}
    names = sorted(set(zones))
    hem = list(hem) if hem else None
    groups = {zn: [i for i in range(nv) if zones[i] == zn] for zn in names}
    if hem:
        groups["hem"] = [i for i in range(nv) if hem[i] and zones[i] in free]
    for zn, idx in groups.items():
        if not idx:
            continue
        drape = [sum(mag[f][i] for f in range(nf)) / nf for i in idx]
        motion = [_std3([D[f][i] for f in range(nf)]) for i in idx]
        slip = [mag[f][i] for f in range(nf) for i in idx]
        path = [sum(_n(_d(skin[f][i], skin[f - 1][i])) for f in range(1, nf)) for i in idx]
        jit = [_n(tuple(D[f + 1][i][k] - 2 * D[f][i][k] + D[f - 1][i][k] for k in range(3))) for f in still for i in idx]
        zm[zn] = {"n": len(idx), "drape_cm": round(_pct(drape, 0.75), 3), "motion_cm": round(_pct(motion, 0.75), 3),
                  "slip_cm": round(_pct(slip, 0.95), 3), "body_path_cm": round(sum(path) / len(path), 2),
                  "jitter_cm": round(_pct(jit, 0.95), 3) if jit else 0.0}
    for zn in free + (["hem"] if hem else []):
        m = zm.get(zn)
        if not m:
            continue
        if m["body_path_cm"] < th["body_moves_cm"]:
            issues.append(issue("cloth.alive_unjudged", "info",
                                f"{zn}: the body moves only {m['body_path_cm']} cm over these frames: too still to "
                                "judge whether the cloth is alive", "judge it over frames with a gesture or a turn",
                                subject=subject, region=zn))
        elif m["motion_cm"] < th["alive_min_cm"]:
            issues.append(issue("cloth.dead", "fail",
                                f"{zn}: the cloth moves {m['motion_cm']} cm relative to the body while the body moves "
                                f"{m['body_path_cm']} cm: it reads as a rigid shell (armour)",
                                "cloth.setup with a preset (max distance in the free zones), check cloth.describe "
                                "simulating=true; lower bending/anim-drive stiffness", subject=subject, region=zn,
                                value=m["motion_cm"], expected=th["alive_min_cm"]))
        elif m["motion_cm"] < th["alive_good_cm"]:
            issues.append(issue("cloth.stiff", "warn",
                                f"{zn}: the cloth moves only {m['motion_cm']} cm relative to the body",
                                "raise the free zones' max distance (cloth.setup overrides zones.<zone>.to_cm) or "
                                "lower bending_stiffness", subject=subject, region=zn, value=m["motion_cm"],
                                expected=th["alive_good_cm"]))
    for zn in pinned:
        m = zm.get(zn)
        if m and m["slip_cm"] > th["pin_tol_cm"]:
            issues.append(issue("cloth.anchor_slip", "warn",
                                f"{zn}: pinned cloth moves {m['slip_cm']} cm off the body (p95)",
                                "paint max distance 0 there (cloth.setup; the fit's pinned colour), or anim drive",
                                subject=subject, region=zn, value=m["slip_cm"], expected=th["pin_tol_cm"]))
    for zn, m in zm.items():
        if m["jitter_cm"] > th["jitter_cm"]:
            issues.append(issue("cloth.jitter", "warn",
                                f"{zn}: the cloth buzzes {m['jitter_cm']} cm frame to frame while the body is still",
                                "more damping (preset config.damping 0.1), collision_thickness up 0.2 cm, or "
                                "self-collision off", subject=subject, region=zn, value=m["jitter_cm"],
                                expected=th["jitter_cm"]))
    # 7. cold start: fast settling in the first frames, calm afterwards (and not because the body moved)
    # per frame, the p90 over vertices (the hem settles, the collar does not: a mean would dilute it)
    speed = [0.0] + [_pct([_n(_d(D[f][i], D[f - 1][i])) for i in range(nv)], 0.9) for f in range(1, nf)]
    body90 = [0.0] + [_pct([_n(_d(skin[f][i], skin[f - 1][i])) for i in range(nv)], 0.9) for f in range(1, nf)]
    k = min(th["cold_frames"], nf - 2)
    early = sum(speed[1:k + 1]) / k if k > 0 else 0.0
    rest = sorted(speed[k + 1:])
    later = rest[len(rest) // 2] if rest else 0.0
    body_early = sum(body90[1:k + 1]) / k if k > 0 else 0.0
    cold = (early > th["cold_min_cm_frame"] and early > th["cold_ratio"] * max(later, 1e-6)
            and body_early < early)
    if cold:
        issues.append(issue("cloth.cold_start", "fail",
                            f"the cloth settles {early:.2f} cm/frame over the first {k} frames (later "
                            f"{later:.2f}): it starts from its skinned pose instead of a settled one",
                            "pre-roll the shot: cloth.preroll (engine warm-up held on the first frame, or the camera "
                            "cut's handles), or render.job's preroll", frame=frames[0], subject=subject,
                            value=round(early, 3), expected=round(th["cold_ratio"] * later, 3)))
    metrics = {"frames": nf, "vertices": nv, "max_disp_cm": round(max_disp, 3),
               "max_speed_cm_s": round(max_speed, 1), "spike_frame": spike_frame, "zones": zm,
               "early_cm_frame": round(early, 3), "later_cm_frame": round(later, 3), "still_frames": len(still)}
    v = worst(issues)
    return {"pass": v != "fail", "verdict": v, "issues": issues, "metrics": metrics}


def hem_mask(rest: list, zones: list, free: list, band_cm: float) -> list:
    """True for the vertices within `band_cm` of the bottom of their free zone (rest pose z): a tee's hem. Sleeve
    ends are not covered by height; a free zone ramped `along` gets its hem from `ramp_t` instead (paint.ramp_t >= 0.8)."""
    lows = {}
    for p, zn in zip(rest, zones):
        if zn in free:
            lows[zn] = min(lows.get(zn, p[2]), p[2])
    return [zn in free and p[2] <= lows[zn] + band_cm for p, zn in zip(rest, zones)]


def sample(n: int, k: int, zones: list | None = None) -> list:
    """Indices of up to `k` of `n` vertices, spread evenly, and every zone kept (at least ~k/10 each where it has
    them): the vertices qa.cloth reads each frame (reading all of a 20k-vertex garment per frame is slow in Python)."""
    if n <= k:
        return list(range(n))
    step = n / float(k)
    idx = {int(i * step) for i in range(k)}
    if zones:
        per = max(1, k // 10)
        by: dict = {}
        for i, z in enumerate(zones):
            by.setdefault(z, []).append(i)
        for z, ii in by.items():
            have = sum(1 for i in idx if zones[i] == z)
            if have < per:
                s = max(1, len(ii) // per)
                idx.update(ii[::s][:per])
    return sorted(idx)
