"""Visual baselines: golden stills (and their numbers) kept by name, and every later still compared against them.

    <root>/<suite>/<name>.png    the golden still (8-bit PNG)
    <root>/<suite>/<name>.json   {"suite", "name", "created", "updated", "size", "metrics": {exposure, color}, "meta",
                                  "thresholds"?}

`suite` groups them ("selftest/look", "film/host-studio/s010"); `name` is the still's name in it. The bridge keeps them
under Saved/fmbridge/baselines on the box (qa.baseline_* ops); `film-qa baseline pull|push` mirrors them to the
operator's side. The first run makes them; every later run regresses against them:

    check(root, suite, name, still)  ->  {"status": "created" | "match" | "differs" | "different", "ssim", ...}

Render noise between runs (Lumen, TAA, streaming) keeps SSIM around 0.97-0.995 for an unchanged scene at 480 px, so a
match is SSIM >= 0.95 by default; a baseline's json may carry its own "thresholds" for a noisy shot.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time

from . import compare as _compare
from . import image as _image
from . import metrics as _metrics
from .issues import issue

MIN_SSIM = 0.95       # >= : match
FAIL_SSIM = 0.75      # <  : a different picture (fail); between: differs (warn)
MAX_STOP_SHIFT = 0.5  # exposure moving more than this many stops is reported even when SSIM matches
_SAFE = re.compile(r"[^A-Za-z0-9_.\-]+")


def safe(part: str) -> str:
    """A suite or name part as a file-system-safe string (slashes in a suite make sub-folders)."""
    out = _SAFE.sub("_", str(part)).strip("._")
    if not out:
        raise ValueError(f"empty baseline name from {part!r}")
    return out


def paths(root: str, suite: str, name: str) -> tuple:
    d = os.path.join(root, *[safe(p) for p in str(suite).replace("\\", "/").split("/") if p])
    return os.path.join(d, safe(name) + ".png"), os.path.join(d, safe(name) + ".json")


def _summary(img) -> dict:
    small = _image.fit(img, 480)
    e = _metrics.exposure(small)
    c = _metrics.color(small)
    return {"exposure": {k: e[k] for k in ("mean", "stops", "clipped_high_pct", "clipped_low_pct", "verdict")},
            "color": {k: c[k] for k in ("mean_rgb", "name", "cast_toward", "cast_amount")}}


def get(root: str, suite: str, name: str) -> dict | None:
    """The baseline's record (with "png" and "json" paths), or None."""
    png, js = paths(root, suite, name)
    if not (os.path.isfile(png) and os.path.isfile(js)):
        return None
    with open(js) as f:
        rec = json.load(f)
    rec.update(png=png, json=js)
    return rec


def save(root: str, suite: str, name: str, still: str, meta: dict | None = None, overwrite: bool = False,
         thresholds: dict | None = None) -> dict:
    """Keep `still` as the baseline suite/name. An existing one is kept unless `overwrite` (then replaced).
    Returns the record plus "changed"."""
    if not os.path.isfile(still):
        raise FileNotFoundError(f"no still at {still}")
    have = get(root, suite, name)
    if have and not overwrite:
        return {**have, "changed": False}
    img = _image.read(still)
    png, js = paths(root, suite, name)
    os.makedirs(os.path.dirname(png), exist_ok=True)
    if still.lower().endswith(".png"):
        shutil.copyfile(still, png)
    else:
        _image.write(img, png)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    rec = {"suite": suite, "name": name, "created": (have or {}).get("created", now), "updated": now,
           "size": [img.w, img.h], "metrics": _summary(img), "meta": dict(meta or {}), "source": still}
    if thresholds or (have or {}).get("thresholds"):
        rec["thresholds"] = thresholds or have["thresholds"]
    with open(js, "w") as f:
        json.dump(rec, f, indent=1)
    rec.update(png=png, json=js, changed=True)
    return rec


def compare(root: str, suite: str, name: str, still: str, diff_out: str = "", min_ssim: float | None = None,
            fail_ssim: float | None = None) -> dict:
    """`still` against its baseline: {"status": "no_baseline" | "match" | "differs" | "different", "ssim", "psnr",
    "changed" (grid cells), "stops_shift", "mean_shift", "diff"?, "issues"}."""
    base = get(root, suite, name)
    if base is None:
        return {"status": "no_baseline", "suite": suite, "name": name, "issues": [
            issue("baseline.missing", "info", f"no baseline {suite}/{name}", "save one with qa.baseline_save")]}
    th = base.get("thresholds") or {}
    lo = float(min_ssim if min_ssim is not None else th.get("min_ssim", MIN_SSIM))
    bad = float(fail_ssim if fail_ssim is not None else th.get("fail_ssim", FAIL_SSIM))
    a, b = _image.read(base["png"]), _image.read(still)
    try:
        r = _compare.compare(a, b)
    except ValueError as e:
        return {"status": "different", "suite": suite, "name": name, "issues": [
            issue("baseline.shape", "fail", f"{suite}/{name}: {e}", "re-render at the baseline's size, or replace it "
                  "(qa.baseline_save overwrite=true)", expected=base.get("size"), value=[b.w, b.h])]}
    now = _summary(b)
    stops = round(now["exposure"]["stops"] - base["metrics"]["exposure"]["stops"], 3)
    status = "match" if r["ssim"] >= lo else "different" if r["ssim"] < bad else "differs"
    out = {"status": status, "suite": suite, "name": name, "ssim": r["ssim"], "psnr": r["psnr"], "changed": r["changed"],
           "mean_shift": r["mean_shift"], "stops_shift": stops, "thresholds": {"min_ssim": lo, "fail_ssim": bad},
           "baseline": base["png"], "baseline_updated": base.get("updated")}
    issues = []
    if status != "match":
        issues.append(issue("baseline.differs" if status == "differs" else "baseline.different",
                            "warn" if status == "differs" else "fail",
                            f"{suite}/{name} moved from its baseline: SSIM {r['ssim']:.3f} (match >= {lo}), "
                            f"{len(r['changed'])} cells changed, exposure {stops:+.2f} stops",
                            "look at the diff; if the change is intended, accept it (qa.baseline_save overwrite=true)",
                            value=r["ssim"], expected=lo))
        for c in r["changed"][:6]:
            issues.append(issue("baseline.region", "info", f"cell {c['cell']} SSIM {c['ssim']:.2f}", box=c["box"],
                                value=c["ssim"]))
    elif abs(stops) > MAX_STOP_SHIFT:
        issues.append(issue("baseline.exposure", "warn", f"{suite}/{name} matches its baseline in structure but its "
                            f"exposure moved {stops:+.2f} stops", "check lights/exposure changes", value=stops))
    if diff_out and status != "match":
        A, B = _compare._same(a, b, 480)
        _image.write(_compare.diff_image(A, B), diff_out)
        out["diff"] = diff_out
    out["issues"] = issues
    return out


def check(root: str, suite: str, name: str, still: str, mode: str = "auto", diff_out: str = "", meta=None) -> dict:
    """What a harness calls per still. mode: "auto" (compare when a baseline exists, else create it), "compare" (never
    create), "update" (replace the baseline with this still), "off". Returns compare()'s result, or a record with
    status "created" / "updated" / "off"."""
    if mode == "off":
        return {"status": "off", "suite": suite, "name": name, "issues": []}
    if mode == "update":
        rec = save(root, suite, name, still, meta=meta, overwrite=True)
        return {"status": "updated", "suite": suite, "name": name, "baseline": rec["png"], "issues": []}
    if mode not in ("auto", "compare"):
        raise ValueError(f"baseline mode {mode!r}: auto, compare, update or off")
    if get(root, suite, name) is None and mode == "auto":
        rec = save(root, suite, name, still, meta=meta)
        return {"status": "created", "suite": suite, "name": name, "baseline": rec["png"], "issues": []}
    return compare(root, suite, name, still, diff_out=diff_out)


def list_(root: str, suite: str = "") -> list:
    """Every baseline under root (or one suite and its sub-suites): [{"suite", "name", "updated", "size", "png",
    "json"}], sorted."""
    out = []
    base = os.path.join(root, *[safe(p) for p in suite.replace("\\", "/").split("/") if p]) if suite else root
    if not os.path.isdir(base):
        return out
    for d, _, files in os.walk(base):
        for f in files:
            if not f.endswith(".json"):
                continue
            js = os.path.join(d, f)
            png = js[:-5] + ".png"
            if not os.path.isfile(png):
                continue
            try:
                with open(js) as fh:
                    rec = json.load(fh)
            except (OSError, ValueError):
                continue
            out.append({"suite": rec.get("suite", os.path.relpath(d, root).replace(os.sep, "/")),
                        "name": rec.get("name", f[:-5]), "updated": rec.get("updated"), "size": rec.get("size"),
                        "png": png, "json": js, "rel": os.path.relpath(png, root).replace(os.sep, "/")})
    return sorted(out, key=lambda r: (r["suite"], r["name"]))


def remove(root: str, suite: str, name: str) -> bool:
    """Delete one baseline; False when there was none."""
    png, js = paths(root, suite, name)
    gone = False
    for p in (png, js):
        if os.path.isfile(p):
            os.remove(p)
            gone = True
    return gone
