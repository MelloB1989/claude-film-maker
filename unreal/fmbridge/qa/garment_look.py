"""Does a garment read as cloth, or as ARMOR? The 'armor index': the round-4 tee on the karma reel passed every
clipping number and still looked to the operator like "heavy armor inside his shirt": a smooth, thick, rigid shell
at an even distance from the body, with no folds and no motion of its own. Each of those is measurable:

| term | measured | cloth | armor |
|---|---|---|---|
| ease | per-vertex distance garment -> the UNCUT body (cm), torso verts | median 0.8-3 cm, varies a lot (tight at the shoulders, loose at the waist and hem, folds) | an even offset (a shell: small spread), or a balloon (median > ~4 cm) |
| wpo | the garment materials' inflate parameters (FM_Inflate, FM_Neck, FM_Patch ...) | 0: the ease is geometry | a World Position Offset push: the silhouette grows evenly, shadows, collision and cloth do not see it |
| thickness | the garment's rim (hem, collar, cuffs) wall, cm | jersey 0.05-0.3 | > 0.6: a thick shell |
| silhouette | (garment U body px) / body px in the garment's rows, the uncut body as reference | 1.0-1.10 | > 1.2: bulked out |
| detail | high-frequency energy of the garment's normals (world-normal capture), mean |N - blur(N)| | folds and a wrinkle normal map | smooth: ~0 |
| motion | the garment's motion relative to the body under it, rms(d(g - b)) / rms(d b) over frames | > ~0.1 with a cloth sim (hem, sleeves) | 0: skinned only, moves as a rigid part of the body |

Each term maps to an armor score 0..1 (a linear ramp between its 'cloth' and 'armor' values); the index is their
weighted mean over the terms measured. FAIL when the index is >= 0.5 or a hard rule breaks (a WPO inflate over
`wpo_max_cm`). The thresholds for `detail` and `motion` are provisional until calibrated on the box (the reel's
round-5 probes: her fitted top and overshirt as the cloth reference, the round-4 tee as armor).

Pure Python: the qa.garment_look op measures in the editor and calls look(); tests call it on synthetic numbers."""
from __future__ import annotations

import math

from .issues import issue

# term: (cloth value, armor value, weight). ease_spread is (p90 - p10) / median; the others as in the table.
RAMPS = {
    "ease_spread": (1.0, 0.4, 1.0),
    "ease_median": (3.0, 5.0, 0.5),
    "thickness": (0.3, 0.8, 0.75),
    "silhouette": (1.10, 1.25, 1.0),
    "detail": (0.035, 0.012, 1.5),   # provisional (probe G3)
    "motion": (0.12, 0.03, 1.5),     # provisional (probe G4)
    "wpo": (0.0, 0.5, 1.0),
}
WPO_MAX_CM = 0.2
INFLATE_PARAMS = ("FM_Inflate", "FM_Neck", "FM_Patch")
FAIL_AT, WARN_AT = 0.5, 0.35

FIX = {
    "ease_spread": "the garment sits at an even offset from the body (a shell): refit it by drape (garment.fit "
                   "drape_frames>0) so it hangs: tight at the shoulders and collar, loose at the waist and hem",
    "ease_median": "the garment stands far off the body (a balloon): lower garment.fit ease_cm, remove any WPO inflate",
    "thickness": "the garment's wall is thick: garment.fit thickness_cm 0.1-0.25 (jersey), and no inflate on a "
                 "closed shell",
    "silhouette": "the garment bulks the figure out: less ease, no WPO inflate; check the reference body is the uncut "
                  "one of the same build",
    "detail": "the garment's surface is smooth: give it folds (garment.fit drape) and a wrinkle/knit normal map with "
              "a cotton roughness 0.7-0.9 and a sheen (the cloth shading model or Substrate fuzz)",
    "motion": "the garment moves exactly with the body: simulate it (cloth.setup preset cotton_tee: T3b), or at least "
              "skin its hem and sleeves looser",
    "wpo": "the ease is a World Position Offset push: remove it (FM_Inflate 0, no neck patch) and give the garment real "
           "geometric ease with garment.fit",
}


def ramp(v: float, good: float, bad: float) -> float:
    """0 at `good`, 1 at `bad`, linear between and clamped (either direction)."""
    if good == bad:
        return 0.0 if v == good else 1.0
    t = (v - good) / (bad - good)
    return max(0.0, min(1.0, t))


def percentile(xs, q: float) -> float:
    s = sorted(xs)
    if not s:
        return float("nan")
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def ease_stats(ease_cm, max_cm: float = 15.0) -> dict:
    """Per-vertex garment->body distances (cm, + = outside the body): the distribution's p10/median/p90, its spread
    (p90 - p10) / median, the share inside the body (< 0: clipping in 3D) and under 0.3 cm (painted on). Distances
    past max_cm (sleeve ends over air, a hem below the body) are left out."""
    xs = [float(e) for e in ease_cm if e == e and abs(e) <= max_cm]
    if not xs:
        return {"n": 0}
    med = percentile(xs, 0.5)
    p10, p90 = percentile(xs, 0.1), percentile(xs, 0.9)
    return {"n": len(xs), "p10": round(p10, 3), "median": round(med, 3), "p90": round(p90, 3),
            "spread": round((p90 - p10) / med, 3) if med > 1e-6 else None,
            "inside": round(sum(1 for x in xs if x < 0) / len(xs), 4),
            "tight": round(sum(1 for x in xs if 0 <= x < 0.3) / len(xs), 4)}


def silhouette_ratio(garment: list, body: list, w: int, h: int, empty: float = 1.0e7) -> dict:
    """(garment U body) px / body px over the rows the garment covers, from depth layers of the garment and the UNCUT
    reference body captured alone from one camera: how much the garment bulks the figure out."""
    rows = {i // w for i in range(w * h) if garment[i] < empty}
    if not rows:
        return {"rows": 0, "ratio": None}
    un = bd = 0
    for y in rows:
        for i in range(y * w, (y + 1) * w):
            g, b = garment[i] < empty, body[i] < empty
            un += g or b
            bd += b
    return {"rows": len(rows), "union_px": un, "body_px": bd, "ratio": round(un / bd, 4) if bd else None}


def _blur(ch: list, w: int, h: int, r: int) -> list:
    """Box blur (separable, clamped edges)."""
    tmp = [0.0] * (w * h)
    for y in range(h):
        row = ch[y * w:(y + 1) * w]
        acc = [0.0]
        for v in row:
            acc.append(acc[-1] + v)
        for x in range(w):
            a, b = max(0, x - r), min(w, x + r + 1)
            tmp[y * w + x] = (acc[b] - acc[a]) / (b - a)
    out = [0.0] * (w * h)
    for x in range(w):
        col = [tmp[y * w + x] for y in range(h)]
        acc = [0.0]
        for v in col:
            acc.append(acc[-1] + v)
        for y in range(h):
            a, b = max(0, y - r), min(h, y + r + 1)
            out[y * w + x] = (acc[b] - acc[a]) / (b - a)
    return out


def erode(mask: set, w: int, h: int, r: int) -> set:
    """Pixels of mask whose (2r+1)^2 neighbourhood is all in mask (drops the silhouette edge, where normals jump)."""
    out = set()
    for i in mask:
        y, x = divmod(i, w)
        if all(0 <= y + dy < h and 0 <= x + dx < w and (y + dy) * w + x + dx in mask
               for dy in range(-r, r + 1) for dx in range(-r, r + 1)):
            out.add(i)
    return out


def detail_energy(normals: tuple, mask: set, w: int, h: int, radius: int = 3, edge: int = 2) -> dict:
    """High-frequency energy of a garment's normals: normals = (nx, ny, nz) channel lists (world normal capture,
    -1..1, or 0..1 encoded: anything affine is fine, it is a difference), mask = the garment's pixels. Per pixel
    |N - blur_radius(N)| (L1 over the channels), averaged over the mask eroded by `edge` px. A smooth shell reads
    ~0; folds and a wrinkle normal map read higher."""
    inner = erode(mask, w, h, edge)
    if not inner:
        return {"px": 0, "energy": None}
    blurred = [_blur(list(c), w, h, radius) for c in normals]
    tot = 0.0
    for i in inner:
        tot += sum(abs(c[i] - b[i]) for c, b in zip(normals, blurred))
    return {"px": len(inner), "energy": round(tot / len(inner), 5)}


def secondary_motion(garment_frames: list, body_frames: list) -> dict:
    """How much the garment moves on its own: garment_frames[f][k] and body_frames[f][k] are matched points (a
    garment vertex and the body point under it at the first frame, carried along), [x, y, z] cm, over consecutive
    frames. ratio = rms over frames and points of the change in (g - b) / rms of the body's own change. Skinned-only
    garments read ~0 (they ride the body); a simulated tee's hem and sleeves read 0.1+."""
    num = den = 0.0
    n = 0
    for f in range(1, min(len(garment_frames), len(body_frames))):
        G0, G1, B0, B1 = garment_frames[f - 1], garment_frames[f], body_frames[f - 1], body_frames[f]
        for g0, g1, b0, b1 in zip(G0, G1, B0, B1):
            rel = [(g1[k] - b1[k]) - (g0[k] - b0[k]) for k in range(3)]
            mv = [b1[k] - b0[k] for k in range(3)]
            num += sum(r * r for r in rel)
            den += sum(m * m for m in mv)
            n += 1
    if n == 0 or den <= 1e-12:
        return {"n": n, "ratio": None, "body_rms_cm": 0.0}
    return {"n": n, "ratio": round(math.sqrt(num / den), 4), "body_rms_cm": round(math.sqrt(den / n), 4)}


def wpo_inflate_cm(params: dict) -> float:
    """The largest push a garment material's inflate parameters make (cm): FM_Inflate + FM_Neck + FM_Patch, as
    mh.cloth_inflate and the round-4 neck patch named them."""
    return round(sum(max(0.0, float(params.get(k, 0.0) or 0.0)) for k in INFLATE_PARAMS if k in params), 3)


def look(m: dict, subject: str = "", *, ramps: dict | None = None, wpo_max_cm: float = WPO_MAX_CM,
         fail_at: float = FAIL_AT, warn_at: float = WARN_AT) -> dict:
    """The armor index from measurements (any subset):
    m = {"ease": ease_stats(...), "thickness_cm": float, "silhouette": ratio, "detail": energy,
         "motion": ratio, "wpo": {param: value} or cm}.
    Returns {"pass", "verdict" ('cloth' | 'borderline' | 'armor'), "index", "terms": {term: {value, score, weight}},
    "issues", "missing": [terms not measured]}."""
    R = {**RAMPS, **(ramps or {})}
    vals = {}
    e = m.get("ease") or {}
    if e.get("n"):
        if e.get("spread") is not None:
            vals["ease_spread"] = e["spread"]
        vals["ease_median"] = e["median"]
    for k_in, k in (("thickness_cm", "thickness"), ("silhouette", "silhouette"), ("detail", "detail"),
                    ("motion", "motion")):
        v = m.get(k_in)
        if isinstance(v, dict):
            v = v.get("ratio", v.get("energy"))
        if v is not None:
            vals[k] = float(v)
    w = m.get("wpo")
    if w is not None:
        vals["wpo"] = wpo_inflate_cm(w) if isinstance(w, dict) else float(w)
    terms, num, den = {}, 0.0, 0.0
    for k, v in vals.items():
        good, bad, wt = R[k]
        s = ramp(v, good, bad)
        terms[k] = {"value": v, "score": round(s, 3), "weight": wt, "cloth": good, "armor": bad}
        num += s * wt
        den += wt
    index = round(num / den, 3) if den else None
    issues = []
    hard = False
    if vals.get("wpo", 0.0) > wpo_max_cm:
        hard = True
        issues.append(issue("garment.wpo_inflate", "fail",
                            f"{subject}: the garment's ease is a World Position Offset push of {vals['wpo']:.2f} cm "
                            f"(limit {wpo_max_cm}): it grows the silhouette evenly and neither shadows nor cloth "
                            f"collision see it", FIX["wpo"], subject=subject, value=vals["wpo"], expected=wpo_max_cm))
    if e.get("n") and e.get("inside", 0) > 0.01:
        issues.append(issue("garment.inside_body", "warn",
                            f"{subject}: {100 * e['inside']:.1f}% of the garment's verts are inside the body",
                            "garment.fit pushes them out to min_ease_cm; check the reference body matches the build",
                            subject=subject, value=e["inside"]))
    for k, t in sorted(terms.items(), key=lambda kv: -kv[1]["score"]):
        if t["score"] >= 0.5 and k != "wpo":
            issues.append(issue(f"garment.armor_{k}", "fail" if t["score"] >= 0.75 else "warn",
                                f"{subject}: {k} {t['value']:g} reads as armor (cloth {t['cloth']}, armor "
                                f"{t['armor']}; score {t['score']})", FIX[k], subject=subject, value=t["value"],
                                expected=t["cloth"]))
    verdict = "armor" if hard or (index is not None and index >= fail_at) else \
        "borderline" if index is not None and index >= warn_at else "cloth"
    if verdict == "armor" and not hard:
        issues.insert(0, issue("garment.armor", "fail", f"{subject}: armor index {index} (fail at {fail_at})",
                               "fix the terms with the highest scores first", subject=subject, value=index,
                               expected=fail_at))
    missing = [k for k in RAMPS if k not in terms]
    return {"pass": verdict != "armor" and index is not None, "verdict": verdict, "index": index, "terms": terms,
            "issues": issues, "missing": missing}
