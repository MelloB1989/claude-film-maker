"""GRADE spec: per-shot normalisation trims for ec/grade.jsx.

The core builder imports this module and calls `extend(E, ctx_py)`. We put everything under `E["x"]["grade"]`:

    E.x.grade.shots[<shot id>]   = {lev, ch, sat, hue, before, after}   (one entry per MAIN shot)
    E.x.grade.panels[<index>]    = same, for the triptych panels (SPECIAL can apply them with GRADE.applyTrim)
    E.x.grade.targets            = the targets the trims aim at

A trim is exactly the parameters of two EffectCraft effects, so JS applies it without any maths:
    lev = {ib, iw, g, ob, ow}   Levels (Individual Controls): RGB input black / input white / gamma / output black / output white
    ch  = {r, g, b}             the same effect's Red/Green/Blue Output White (white balance: the strong channel is pulled down)
    sat = Hue/Saturation master saturation (-100..100, an HSL saturation scale of 1 + sat/100)
    hue = Hue/Saturation master hue in degrees (skin hue nudge, usually 0)
EffectCraft's Pro Levels is master levels first, then the channel levels (checked against renders, error < 0.001), and
Hue/Saturation with a negative value is an exact HSL saturation scale. `model()` below mirrors both in numpy, so the
`after` stats are a prediction of what the trims do before the look.

Pixel samples (6 frames per shot, 480x270, 3000 px) are cached in `grade_samples.npz` and the finished trims in
`grade_trims.json`, so the core machine does not need ffmpeg or the clips: with numpy only, the trims are recomputed from the
samples; without numpy, `grade_trims.json` is used. `python grade_spec.py --remeasure` rebuilds the samples from the clips.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "grade_samples.npz")
TRIMS = os.path.join(HERE, "grade_trims.json")
CURVES = os.path.join(HERE, "grade_curves.json")
NPX = 3000

# what the normalisation aims at (gamma-encoded 0..1, luma = Rec.709 weights)
TARGETS = {
    "p50_range": [0.26, 0.44],      # shots inside it keep their median; outside it is pulled 60 % (dark) / 40 % (bright) toward it
    "p99": 0.86, "p99_act": {"tobey": 0.86, "andrew": 0.88, "tom": 0.91},                  # white point: dark shots are lifted toward it, blown ones are compressed toward it
    "black": 0.006,                 # output black, just off zero
    "white_out": 0.94,              # per-shot output white; the finishing limiter adds 0.955
    "sat_range": {"tobey": [0.34, 0.50], "andrew": [0.32, 0.46], "tom": [0.30, 0.42]}, "sat_pull": 0.8,   # mean HSV saturation band before the look (the look adds ~10 %): a shot outside it is pulled 80 % of the way to the edge
    "skin_hue": 22.0, "skin_lo": 12.0, "skin_hi": 32.0, "skin_min": 0.03,
    "wb_strength": 0.35, "wb_floor": 0.88, "wb_min_cast": 0.08,
    "gamma_range": [0.7, 2.2],
}


def _np():
    try:
        import numpy
        return numpy
    except Exception:
        return None


# ---------------------------------------------------------------- model of the two effects
def model(P, t):
    """Apply a trim to RGB pixels P (N x 3, 0..1): Pro Levels (master, then channel output white), then Hue/Saturation."""
    np = _np()
    lev, ch = t["lev"], t["ch"]
    x = np.clip((P - lev["ib"]) / max(lev["iw"] - lev["ib"], 1e-4), 0, 1) ** (1.0 / lev["g"])
    x = lev["ob"] + (lev["ow"] - lev["ob"]) * x
    x = x * np.array([ch["r"], ch["g"], ch["b"]])
    if t.get("hue"):
        x = _hue_rotate(x, t["hue"])
    if t.get("sat"):
        x = _hsl_sat(x, 1.0 + t["sat"] / 100.0)
    return np.clip(x, 0, 1)


def _hsl_sat(x, f):
    np = _np()
    mx, mn = x.max(1), x.min(1)
    l = (mx + mn) / 2
    d = mx - mn
    den = 1 - np.abs(2 * l - 1)
    s = np.where(d > 1e-9, d / np.maximum(den, 1e-6), 0)
    s2 = np.clip(s * f, 0, 1)
    scale = np.where(d > 1e-9, s2 * den / np.maximum(d, 1e-9), 1)
    return np.clip(l[:, None] + (x - l[:, None]) * scale[:, None], 0, 1)


def _hue_rotate(x, deg):
    """Hue rotation about the grey axis (Rodrigues); close to HSL hue rotation for the small angles we use."""
    np = _np()
    a = np.deg2rad(deg)
    k = np.ones(3) / np.sqrt(3)
    c, s = np.cos(a), np.sin(a)
    return np.clip(x * c + np.cross(k, x) * s + k[None] * (x @ k)[:, None] * (1 - c), 0, 1)


def _luma(P):
    return P[:, 0] * 0.2126 + P[:, 1] * 0.7152 + P[:, 2] * 0.0722


def _mean_sat(P):
    np = _np()
    mx, mn = P.max(1), P.min(1)
    ok = mx > 0.1
    return float((((mx - mn) / np.maximum(mx, 1e-6))[ok]).mean()) if ok.any() else 0.0


def _pstats(P):
    np = _np()
    L = _luma(P)
    p = np.percentile(L, [1, 5, 50, 95, 99])
    return {"p1": round(float(p[0]), 4), "p5": round(float(p[1]), 4), "p50": round(float(p[2]), 4), "p95": round(float(p[3]), 4),
            "p99": round(float(p[4]), 4), "clip": round(float(np.mean(P.max(1) >= 0.985) * 100), 3),
            "sat": round(_mean_sat(P), 4)}


def _skin(P):
    np = _np()
    mx, mn = P.max(1), P.min(1)
    d = mx - mn
    r, g, b = P[:, 0], P[:, 1], P[:, 2]
    h = np.zeros(len(P))
    m = d > 1e-6
    rc = m & (mx == r)
    gc = m & (mx == g) & ~rc
    bc = m & ~rc & ~gc
    h[rc] = ((g - b)[rc] / d[rc]) % 6
    h[gc] = (b - r)[gc] / d[gc] + 2
    h[bc] = (r - g)[bc] / d[bc] + 4
    h *= 60
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    R8, G8, B8 = r * 255, g * 255, b * 255
    sk = (h >= 8) & (h <= 45) & (s >= 0.2) & (s <= 0.65) & (mx >= 0.35) & (R8 > 95) & (G8 > 40) & (B8 > 20) & (d * 255 > 15) \
        & (np.abs(R8 - G8) > 15) & (r > g) & (r > b)           # the classic RGB skin locus, plus an HSV band
    return float(sk.mean()), (float(np.median(h[sk])) if sk.sum() > 40 else None)


# ---------------------------------------------------------------- the trim for one shot
def _curve(act):
    """The act look + limiter tone curve (grade_curves.json) as a function of luma, or identity."""
    np = _np()
    try:
        c = json.load(open(CURVES))[act]
        return lambda x: np.interp(x, c["x"], c["y"])
    except Exception:
        return lambda x: x


def solve(P, act="tom"):
    """Trim parameters (and before/after stats) for pixel samples P (N x 3, 0..1)."""
    np = _np()
    T = TARGETS
    C = _curve(act)
    T99 = T["p99_act"].get(act, T["p99"])
    before = _pstats(P)
    sk_frac, sk_hue = _skin(P)
    before["skin"] = round(sk_frac, 4)
    before["skin_hue"] = None if sk_hue is None else round(sk_hue, 1)

    # 1. white balance from the white point (skipped when the white point is clipped or the shot is dark)
    w = np.percentile(P, 99.5, axis=0)
    ch = {"r": 1.0, "g": 1.0, "b": 1.0}
    if w.min() < 0.97 and before["p99"] > 0.25 and (w.max() - w.min()) / max(w.max(), 1e-3) > T["wb_min_cast"]:
        c = (w.mean() / np.maximum(w, 1e-3)) ** T["wb_strength"]
        c = np.clip(c / c.max(), T["wb_floor"], 1.0)
        ch = {k: round(float(v), 4) for k, v in zip("rgb", c)}
    P1 = P * np.array([ch["r"], ch["g"], ch["b"]])
    L1 = _luma(P1)
    p1, p5, p50, p99 = np.percentile(L1, [1, 5, 50, 99])
    M1 = P1.max(1)

    # 2. targets for the median and the white point
    lo, hi = T["p50_range"]
    t50 = p50 + 0.8 * (lo - p50) if p50 < lo else (p50 - 0.4 * (p50 - hi) if p50 > hi else p50)
    if p50 < hi:
        t50 = max(t50, p50 * 1.12)                           # never pull a dark shot below its source
    t99 = p99 + 0.5 * (T99 - p99) if p99 < T99 else T99 + 0.25 * (p99 - T99)
    ib = round(float(min(0.5 * p5, 0.04)), 4)
    ob = T["black"]

    # 3. grid search the levels (iw, g, ow) for the closest median and white point with a small clip budget
    best = None
    g_lo, g_hi = T["gamma_range"]
    for ow in (0.9, 0.92, T["white_out"]):
        for iw in np.arange(0.40, 1.0001, 0.02):
            for g in np.arange(g_lo, g_hi + 1e-9, 0.05):
                def f(x):
                    return ob + (ow - ob) * np.clip((x - ib) / (iw - ib), 0, 1) ** (1.0 / g)
                a50, a99 = C(f(p50)), C(f(p99))
                clip = np.mean(C(f(M1)) >= 0.96) * 100
                floor_pen = 40 * max(0.0, p50 * 1.08 - a50) ** 2 if p50 < hi else 0.0
                cost = floor_pen + 4 * (a50 - t50) ** 2 + 2 * (a99 - t99) ** 2 + 0.3 * (np.log(g)) ** 2 + 0.6 * (1 - iw) ** 2 \
                    + 0.5 * max(0.0, clip - 0.2) ** 2
                if best is None or cost < best[0]:
                    best = (cost, float(iw), float(g), float(ow))
    _, iw, g, ow = best
    t = {"lev": {"ib": ib, "iw": round(iw, 3), "g": round(g, 3), "ob": ob, "ow": round(ow, 3)}, "ch": ch, "sat": 0, "hue": 0}

    # 4. skin hue nudge (only when skin is a real part of the frame and well outside the band)
    if sk_hue is not None and sk_frac >= T["skin_min"] and not (T["skin_lo"] <= sk_hue <= T["skin_hi"]):
        t["hue"] = round(float(np.clip((T["skin_hue"] - sk_hue) * 0.5, -8, 8)), 1)

    # 5. saturation: bisect the master-saturation value so the predicted mean HSV saturation lands on the target
    Pn = model(P, t)
    s0 = _mean_sat(Pn)
    s_lo, s_hi = T["sat_range"][act]
    s_t = s0 + T["sat_pull"] * (min(max(s0, s_lo), s_hi) - s0)
    lo_s, hi_s = -70.0, 60.0
    for _ in range(14):
        mid = (lo_s + hi_s) / 2
        t2 = dict(t, sat=mid)
        if _mean_sat(model(P, t2)) < s_t:
            lo_s = mid
        else:
            hi_s = mid
    t["sat"] = round(float(np.clip((lo_s + hi_s) / 2, -60, 45)), 1)
    after = _pstats(model(P, t))
    sk2 = _skin(model(P, t))
    after["skin"] = round(sk2[0], 4)
    after["skin_hue"] = None if sk2[1] is None else round(sk2[1], 1)
    t["before"], t["after"] = before, after
    return t


# ---------------------------------------------------------------- sampling
def _key(shot):
    lo, hi = sorted(shot["src"])
    return "%s_%.3f_%.3f" % (shot["clip"], lo, hi)


def remeasure(E, workers=4):
    """Decode the clips and write grade_samples.npz (one NPX x 3 uint8 array per shot window)."""
    np = _np()
    sys.path.insert(0, HERE)
    import grade_measure as gm
    from concurrent.futures import ThreadPoolExecutor
    items = list(E["shots"]) + [dict(p, id="P%d" % i) for i, p in enumerate(E["triptych"]["panels"])]
    rng = np.random.RandomState(7)

    def one(s):
        fr = [gm.read_frame(s["file"], t) for t in gm.clip_times(s, 6)]
        fr = [f for f in fr if f is not None]
        if not fr:
            return _key(s), None
        px = np.concatenate([f.reshape(-1, 3) for f in fr])
        return _key(s), px
    out = {}
    with ThreadPoolExecutor(workers) as ex:
        for k, px in ex.map(one, items):
            if px is not None:
                out[k] = px[rng.choice(len(px), NPX, replace=False)]
    np.savez_compressed(SAMPLES, **out)
    return out


def _load_samples(E):
    np = _np()
    if np is None or not os.path.exists(SAMPLES):
        return None
    z = np.load(SAMPLES)
    return {k: z[k].astype("float64") / 255.0 for k in z.files}


def compute(E):
    items = [(s["id"], s) for s in E["shots"]] + [("P%d" % i, dict(p, id="P%d" % i)) for i, p in enumerate(E["triptych"]["panels"])]
    smp = _load_samples(E)
    out = {"shots": {}, "panels": {}}
    for sid, s in items:
        px = None if smp is None else smp.get(_key(s))
        if px is None:
            continue
        a_f = s.get("a", s.get("f", 800))
        act = "tobey" if a_f < 252 else ("andrew" if a_f < 480 else "tom")
        t = solve(px, act)
        t["clip"] = s["clip"]
        (out["panels"] if sid.startswith("P") else out["shots"])[sid[1:] if sid.startswith("P") else sid] = t
    return out


def neutral():
    return {"lev": {"ib": 0.0, "iw": 1.0, "g": 1.0, "ob": TARGETS["black"], "ow": TARGETS["white_out"]},
            "ch": {"r": 1.0, "g": 1.0, "b": 1.0}, "sat": 0, "hue": 0}


def extend(E, ctx_py=None):
    """Called by the core before the script is written."""
    g = None
    try:
        g = compute(E) if _np() is not None else None
    except Exception as e:                                   # never break the build over a measurement
        sys.stderr.write("grade_spec: compute failed (%s), using the cache\n" % e)
    if not g or not g["shots"]:
        if os.path.exists(TRIMS):
            g = json.load(open(TRIMS))
        else:
            g = {"shots": {}, "panels": {}}
    for s in E["shots"]:                                     # any shot without a measurement still gets the safe levels
        g["shots"].setdefault(s["id"], neutral())
    g["targets"] = TARGETS
    E.setdefault("x", {})["grade"] = g
    return E


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--remeasure", action="store_true", help="decode the clips and rewrite grade_samples.npz")
    ap.add_argument("--print", action="store_true")
    a = ap.parse_args()
    edl = json.load(open(os.path.join(HERE, "..", "..", "..", "films/timeless/amv2/edl.json")))
    if a.remeasure:
        remeasure(edl)
    g = compute(edl)
    json.dump(g, open(TRIMS, "w"), indent=1)
    if a.print:
        for k, t in list(g["shots"].items()) + [("P" + k, v) for k, v in g["panels"].items()]:
            b, af = t["before"], t["after"]
            print("%-4s %-18s p1 %.3f>%.3f p50 %.3f>%.3f p99 %.3f>%.3f clip %5.2f>%5.2f sat %.2f>%.2f | lev %s ch %s sat %s hue %s" % (
                k, t["clip"][:18], b["p1"], af["p1"], b["p50"], af["p50"], b["p99"], af["p99"], b["clip"], af["clip"], b["sat"], af["sat"],
                t["lev"], [t["ch"]["r"], t["ch"]["g"], t["ch"]["b"]], t["sat"], t["hue"]))
