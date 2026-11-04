"""Continuity: what changed between two states of a scene, or two frames that should match. A snapshot is plain
JSON (qa.snapshot writes it from the editor): {"actors": {label: {"class", "loc", "rot", "scale", "bounds",
"hidden", "materials": [...], "props": {...}}}, "meta": {...}}. diff() reports actors added, removed, moved,
turned, rescaled, re-materialed, shown/hidden and changed properties, each over a tolerance, as issues."""
from __future__ import annotations

import math

from .issues import issue

TOL = {"loc_cm": 0.5, "rot_deg": 0.5, "scale": 0.005, "prop": 1e-4}


def _dist(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _ang(a: float, b: float) -> float:
    d = (b - a + 180) % 360 - 180
    return abs(d)


def diff(before: dict, after: dict, tol: dict | None = None, ignore=(), severity: str = "info") -> dict:
    """Changes from `before` to `after` (snapshots). `ignore` labels (or prefixes ending in '*') to skip, e.g. the
    QA capture rig. `severity` of a change: "info" when comparing versions (changes are expected, just listed);
    use "warn" when the two should be identical (a continuity check between shots that share a set).
    Returns {"added", "removed", "changed": {label: {what: [before, after]}}, "issues"}."""
    t = {**TOL, **(tol or {})}

    def skip(lab: str) -> bool:
        return any(lab == p or (p.endswith("*") and lab.startswith(p[:-1])) for p in ignore)

    A = {k: v for k, v in before.get("actors", {}).items() if not skip(k)}
    B = {k: v for k, v in after.get("actors", {}).items() if not skip(k)}
    added, removed = sorted(set(B) - set(A)), sorted(set(A) - set(B))
    changed, issues = {}, []
    for lab in added:
        issues.append(issue("continuity.added", severity, f"{lab} ({B[lab].get('class', '?')}) appeared at {B[lab].get('loc')}",
                            subject=lab))
    for lab in removed:
        issues.append(issue("continuity.removed", severity, f"{lab} ({A[lab].get('class', '?')}) is gone (was at "
                            f"{A[lab].get('loc')})", subject=lab))
    for lab in sorted(set(A) & set(B)):
        a, b, ch = A[lab], B[lab], {}
        if a.get("loc") and b.get("loc") and _dist(a["loc"], b["loc"]) > t["loc_cm"]:
            ch["loc"] = [a["loc"], b["loc"]]
        if a.get("rot") and b.get("rot"):
            d = max(_ang(a["rot"].get(k, 0), b["rot"].get(k, 0)) for k in ("pitch", "yaw", "roll"))
            if d > t["rot_deg"]:
                ch["rot"] = [a["rot"], b["rot"]]
        if a.get("scale") and b.get("scale") and max(abs(x - y) for x, y in zip(a["scale"], b["scale"])) > t["scale"]:
            ch["scale"] = [a["scale"], b["scale"]]
        for k in ("hidden", "materials", "class", "mesh"):
            if k in a and k in b and a[k] != b[k]:
                ch[k] = [a[k], b[k]]
        pa, pb = a.get("props", {}), b.get("props", {})
        for k in sorted(set(pa) | set(pb)):
            va, vb = pa.get(k), pb.get(k)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and not isinstance(va, bool):
                if abs(va - vb) > t["prop"] * max(1.0, abs(va)):
                    ch[f"props.{k}"] = [va, vb]
            elif isinstance(va, list) and isinstance(vb, list) and len(va) == len(vb) and all(
                    isinstance(x, (int, float)) for x in va + vb):
                if max((abs(x - y) for x, y in zip(va, vb)), default=0) > t["prop"] * max(1.0, *map(abs, va)):
                    ch[f"props.{k}"] = [va, vb]
            elif va != vb:
                ch[f"props.{k}"] = [va, vb]
        if ch:
            changed[lab] = ch
            what = []
            if "loc" in ch:
                what.append(f"moved {_dist(*ch['loc']):.1f} cm")
            if "rot" in ch:
                what.append("turned")
            if "scale" in ch:
                what.append("rescaled")
            if "hidden" in ch:
                what.append("hidden" if ch["hidden"][1] else "shown")
            if "materials" in ch:
                what.append("materials changed")
            what += [k for k in ch if k.startswith("props.")]
            issues.append(issue("continuity.changed", severity, f"{lab}: {', '.join(what)}", subject=lab,
                                value={k: v for k, v in ch.items()}))
    return {"added": added, "removed": removed, "changed": changed, "issues": issues,
            "summary": f"{len(added)} added, {len(removed)} removed, {len(changed)} changed"}


def frames(a_metrics: dict, b_metrics: dict, cmp: dict | None = None, name: str = "", max_stop_jump: float = 0.5,
           max_hue_jump: float = 25.0) -> list:
    """Continuity between two frames that should look alike (across a cut in one scene, or the same frame in two
    versions): exposure jumps, colour/hue jumps, and (with a compare() result) structural change.
    `a_metrics` / `b_metrics` are metrics.analyze() results."""
    out = []
    ea, eb = a_metrics["exposure"], b_metrics["exposure"]
    js = eb["stops"] - ea["stops"]
    if abs(js) > max_stop_jump:
        out.append(issue("continuity.exposure_jump", "warn", f"{name} exposure jumps {js:+.2f} stops",
                         "match the lights/exposure between the shots", value=round(js, 2)))
    ca, cb = a_metrics["color"], b_metrics["color"]
    if min(ca["hue_strength"], cb["hue_strength"]) > 0.05:
        dh = _ang(ca["hue"], cb["hue"])
        if dh > max_hue_jump:
            out.append(issue("continuity.hue_jump", "warn", f"{name} overall hue moves {dh:.0f} degrees "
                             f"({ca['name']} -> {cb['name']})", "match light colours/grade between the shots",
                             value=round(dh, 1)))
    dc = {k: round(cb["cast"][k] - ca["cast"][k], 3) for k in "rgb"}
    if max(abs(v) for v in dc.values()) > 0.08:
        out.append(issue("continuity.cast_jump", "info", f"{name} white balance shifts {dc}", value=dc))
    if cmp and cmp.get("verdict") == "different":
        out.append(issue("continuity.structure", "info", f"{name} the frames are different pictures (SSIM "
                         f"{cmp['ssim']:.2f}): expected across a cut, not within a shot", value=cmp["ssim"]))
    return out
