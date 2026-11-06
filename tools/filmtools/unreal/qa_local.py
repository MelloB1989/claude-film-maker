"""film-qa: Claude's eyes on the operator's side, on stills already pulled from the box (film-ue pull / pull-dir):
the same checks as the editor's qa.* ops (unreal/fmbridge/qa, imported from the repo), with no editor running.

    film-qa image STILL [--expect-stops LO HI] [--subject NAME=x0,y0,x1,y1 ...]   exposure, colour, focus: issues
    film-qa compare STILL REFERENCE [--diff OUT.png] [--min-ssim 0.9]            SSIM/PSNR, changed cells, heatmap
    film-qa sheet OUT.png STILL... [--labels a,b,..] [--cols N] [--width 480] [--title T]   a labelled contact sheet
    film-qa overlay STILL OUT.png [--guides thirds,safe] [--box x0,y0,x1,y1[:label]] [--caption TEXT]
    film-qa review DIR [--reference DIR] [--out DIR] [--title T]                 every PNG/JPG in DIR: one review
    film-qa framing CAMERA.json BONES.json [--subject NAME] [--expect-size MCU]  the framing check from numbers
    film-qa baseline pull DIR [--suite S]        the box's baselines (qa.baseline_list) mirrored into DIR
    film-qa baseline push DIR [--suite S]        DIR's baselines onto the box (accept them there)
    film-qa baseline check DIR SUITE STILL...    stills against local baselines DIR/SUITE/<stem>.png (offline;
                                                 --mode auto|compare|update: auto creates missing ones)
    film-qa baseline list DIR [--suite S]        what DIR holds
    film-qa hair SPEC.json [--out OUT.json]      hair continuity across cuts on rendered frames (a dark-hair matte
                                                 in a box per shot): SPEC {"character", "cuts": [[shot, first,
                                                 end]], "frames_glob" | "frames": {frame: path}, "boxes": {shot:
                                                 [x0,y0,x1,y1]}, "anchors"?: {frame: [head_v, chest_v]},
                                                 "max_luma"?, "thresholds"?}
    film-qa gate NUMBERS.json... [--spec SPEC.json] [--waive ITEM=REASON] [--by NAME] [--out OUT.json]
                                                 the review gate v2 (qa/gate.py): SIGN or REFUSE; NUMBERS files
                                                 are {item: value} or any op result with a "gate" dict
    film-qa gate --lines [--spec SPEC.json]      does every item's line fail the round-4 value it must catch?
    film-qa head DIR --fps 24 [--box x0,y0,x1,y1] [--out R.json]   the head through the blinks, from the frames
                                                 (face landmarks; needs `uv run --with mediapipe==0.10.21`)
    film-qa head-samples QA_OUT.json             re-judge qa.head_stability's saved samples (out=), offline
    film-qa head-gate OUT.json QA_OUT.json...     gate v2's head.blink_nod_deg + head.blink_locked_deg

Every command prints JSON ({"pass", "issues", "metrics", ...}) and exits 1 when a "fail" issue was found, so a
script (or Claude) can branch on it. JPEG and other formats need Pillow (`uv sync --extra anime` has it); PNG never
does. With numpy present (it is, in tools/) the image work is vectorised.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
QA_DIR = ROOT / "unreal" / "fmbridge" / "qa"
IMAGE_EXT = (".png", ".jpg", ".jpeg")


def qa():
    """fmbridge.qa as a standalone package `fmqa` (importing fmbridge itself would need the editor's `unreal`)."""
    if "fmqa" in sys.modules:
        return sys.modules["fmqa"]
    spec = importlib.util.spec_from_file_location("fmqa", QA_DIR / "__init__.py", submodule_search_locations=[str(QA_DIR)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fmqa"] = mod
    spec.loader.exec_module(mod)
    for sub in ("image", "draw", "overlay", "sheet", "metrics", "compare", "framing", "geometry", "continuity", "review",
                "baseline", "hair", "gate"):
        __import__(f"fmqa.{sub}")
    return mod


def _result(issues: list, metrics: dict, **extra) -> dict:
    q = qa()
    return {"pass": q.worst(issues) != "fail", "issues": issues, "metrics": metrics, **extra}


def image(path: str, subjects: dict | None = None, expect: dict | None = None) -> dict:
    """qa.image on a local still."""
    q = qa()
    r = sys.modules["fmqa.metrics"].analyze(sys.modules["fmqa.image"].read(path), subjects=subjects, expect=expect)
    iss = r.pop("issues")
    return _result(iss, r, image=path)


def compare(path: str, reference: str, diff: str = "", min_ssim: float = 0.9) -> dict:
    """qa.compare on local stills; `diff` writes the heatmap."""
    qa()
    im, cm = sys.modules["fmqa.image"], sys.modules["fmqa.compare"]
    a, b = im.read(path), im.read(reference)
    r = cm.against_reference(a, b, name=os.path.basename(path), min_ssim=min_ssim)
    extra = {}
    if diff:
        A, B = cm._same(b, a, 480)
        im.write(cm.diff_image(A, B), diff)
        extra["diff"] = diff
    iss = r.pop("issues")
    return _result(iss, r, **extra)


def sheet(out: str, paths: list, labels: list | None = None, cols: int = 0, width: int = 480, title: str = "") -> dict:
    """A labelled contact sheet of local stills (label default: the file name)."""
    qa()
    im, sh = sys.modules["fmqa.image"], sys.modules["fmqa.sheet"]
    cells = [{"image": p, "label": (labels[k] if labels and k < len(labels) else Path(p).stem)} for k, p in enumerate(paths)]
    s = sh.contact_sheet(cells, cols=cols, cell_width=width, title=title)
    im.write(s, out)
    return {"path": out, "width": s.w, "height": s.h, "cells": len(cells)}


def overlay(path: str, out: str, guides=("thirds",), boxes=(), caption: str = "") -> dict:
    qa()
    im, ov = sys.modules["fmqa.image"], sys.modules["fmqa.overlay"]
    o = ov.overlay(im.read(path), guides=guides, boxes=boxes, caption=caption)
    im.write(o, out)
    return {"path": out, "width": o.w, "height": o.h}


def review(folder: str, out: str = "", reference: str = "", title: str = "") -> dict:
    """A review of every still in a folder (sorted by name): exposure/colour per frame, continuity between
    neighbours, a reference comparison per file name when `reference` is given; review.json + review.png in `out`
    (default the folder)."""
    qa()
    im, mt, cm, ct, rv = (sys.modules[f"fmqa.{m}"] for m in ("image", "metrics", "compare", "continuity", "review"))
    files = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXT and not p.stem.startswith(("review", "sheet")))
    if not files:
        raise SystemExit(f"no PNG/JPG stills in {folder}")
    panels, prev = [], None
    for p in files:
        img = im.read(str(p))
        an = mt.analyze(img)
        iss = list(an["issues"])
        if reference:
            rp = Path(reference) / p.name
            if rp.is_file():
                iss += cm.against_reference(img, im.read(str(rp)), name=p.name)["issues"]
            else:
                iss.append(qa().issue("compare.no_reference", "info", f"no reference {rp}"))
        if prev is not None:
            iss += ct.frames(prev, an, name=f"{files[len(panels) - 1].stem} -> {p.stem}:")
        prev = an
        frame = int(p.stem) if p.stem.isdigit() else None
        panels.append({"image": str(p), "label": p.stem, "frame": frame, "issues": iss,
                       "metrics": {"exposure": an["exposure"]}})
    rep = rv.build(panels, out or folder, title=title or Path(folder).name)
    return {"pass": rep["verdict"] != "fail", "verdict": rep["verdict"], "counts": rep["counts"],
            "summary": rep["summary"], "issues": rep["issues"], "report": rep["json"], "image": rep["image"]}


def framing(camera: dict, bones: dict, subject: str = "subject", expect: dict | None = None) -> dict:
    """framing.check from numbers (a camera dict as view.camera returns it, bones as {bone: [x,y,z]})."""
    qa()
    fr = sys.modules["fmqa.framing"]
    r = fr.check(fr.Camera.from_dict(camera), subject, bones=bones, expect=expect)
    iss = r.pop("issues")
    return _result(iss, r)


def baseline_pull(local_dir: str, suite: str = "", client=None) -> dict:
    """Mirror the box's baselines (all, or a suite) into local_dir: <local_dir>/<suite>/<name>.png + .json."""
    client = client or _client()
    r = client.op("qa.baseline_list", suite=suite)
    if not r.get("ok", True):
        raise SystemExit(r.get("error") or r.get("message") or "qa.baseline_list failed")
    res = r.get("result", r)
    got = []
    for b in res["baselines"]:
        rel = b["rel"]
        dst = Path(local_dir) / rel
        client.pull(b["png"], str(dst))
        client.pull(b["json"], str(dst.with_suffix(".json")))
        got.append(rel)
    return {"root": res["root"], "pulled": got, "dir": local_dir}


def baseline_push(local_dir: str, suite: str = "", client=None) -> dict:
    """Put local baselines (PNG + JSON pairs under local_dir, or its `suite` sub-folder) onto the box's root."""
    client = client or _client()
    r = client.op("qa.baseline_list", suite="")
    if not r.get("ok", True):
        raise SystemExit(r.get("error") or r.get("message") or "qa.baseline_list failed")
    res = r.get("result", r)
    root = str(res["root"]).rstrip("/\\")
    base = Path(local_dir) / suite if suite else Path(local_dir)
    sent = []
    for png in sorted(base.rglob("*.png")):
        js = png.with_suffix(".json")
        if not js.is_file():
            continue
        rel = png.relative_to(local_dir).as_posix()
        client.push(str(png), f"{root}/{rel}")
        client.push(str(js), f"{root}/{rel[:-4]}.json")
        sent.append(rel)
    return {"root": root, "pushed": sent}


def baseline_check(local_dir: str, suite: str, stills: list, mode: str = "auto", diff_dir: str = "") -> dict:
    """Stills against local baselines (offline): one record per still, named by its file stem."""
    q = qa()
    bl = sys.modules["fmqa.baseline"]
    out, issues = [], []
    for p in stills:
        d = str(Path(diff_dir) / f"diff_{Path(p).name}") if diff_dir else ""
        r = bl.check(local_dir, suite, Path(p).stem, p, mode=mode, diff_out=d)
        issues += [dict(i, image=p) for i in r.pop("issues")]
        out.append(r)
    return {"pass": q.worst(issues) != "fail", "issues": issues, "metrics": {"stills": out}}


def hair(spec: dict) -> dict:
    """Hair continuity on rendered frames (qa/hair.py): per frame a dark-pixel matte inside the shot's box (the
    character's head and shoulders), measured against the head/chest rows when `anchors` gives them."""
    import glob
    import re
    qa()
    h, im = sys.modules["fmqa.hair"], sys.modules["fmqa.image"]
    frames = {int(k): v for k, v in (spec.get("frames") or {}).items()}
    if spec.get("frames_glob"):
        for p in sorted(glob.glob(spec["frames_glob"])):
            m = re.findall(r"\d+", Path(p).stem)
            if m:
                frames.setdefault(int(m[-1]), p)
    cuts = [[str(c[0]), int(c[1]), int(c[2])] for c in spec["cuts"]]
    k = int((spec.get("thresholds") or {}).get("k", h.THRESHOLDS["k"]))
    want = set()  # only the frames next to a cut, unless "all": true
    for i, (_, a0, a1) in enumerate(cuts):
        want |= set(range(a0, a1)) if spec.get("all") else set(range(a0, min(a1, a0 + k))) | set(range(max(a0, a1 - k), a1))
    anchors = {int(f): v for f, v in (spec.get("anchors") or {}).items()}
    series = {}
    for f in sorted(want & set(frames)):
        shot = next((s for s, a0, a1 in cuts if a0 <= f < a1), None)
        box = (spec.get("boxes") or {}).get(shot)
        if not box:
            continue
        mask, w, hh = h.luma_mask(im.read(frames[f]), box, float(spec.get("max_luma", 40.0)))
        hv, cv = anchors.get(f, (None, None))
        series[f] = h.mask_stats(mask, w, hh, head_v=hv, chest_v=cv)
    r = h.judge(series, cuts, spec.get("character", ""), spec.get("thresholds"))
    cut_pct = max([abs(c["reach"][2]) * 100 for c in r["cuts"]] or [0.0])
    pop_pct = max([abs(p["reach"]) * 100 for p in r["pops"]] or [0.0])
    r["gate"] = {"hair.cut_reach_pct": round(cut_pct, 2), "hair.pop_reach_pct": round(pop_pct, 2)}
    r["metrics"] = {"frames_measured": len(series), "frames_found": len(frames)}
    if not series:
        r["pass"] = False
        r["issues"].append({"code": "hair.no_frames", "severity": "fail", "message": "no frame next to a cut was "
                            "measured: check frames_glob/frames and that every shot has a box"})
    return r


def gate(paths: list, spec_path: str = "", waive: list | None = None, by: str = "") -> dict:
    """The review gate v2 over merged number files."""
    qa()
    g = sys.modules["fmqa.gate"]
    numbers = {}
    for p in paths:
        d = json.loads(Path(p).read_text())
        numbers.update(d.get("gate", d.get("numbers", d)) if isinstance(d, dict) else {})
    spec = json.loads(Path(spec_path).read_text()) if spec_path else None
    if spec and "spec" in spec and "items" not in spec:
        spec = spec["spec"]
    w = {}
    for item in waive or []:
        k, _, reason = item.partition("=")
        w[k.strip()] = (reason.strip(), by)
    r = g.judge(numbers, waivers=w, spec=spec)
    r["pass"] = r["verdict"] == "SIGN"
    return r


def _client():
    from . import client
    return client


def _box(s: str) -> dict:
    coords, _, label = s.partition(":")
    return {"box": [float(v) for v in coords.split(",")], "label": label}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="film-qa", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("image")
    a.add_argument("still")
    a.add_argument("--expect-stops", nargs=2, type=float)
    a.add_argument("--subject", action="append", default=[], help="NAME=x0,y0,x1,y1 (fractions)")
    c = sub.add_parser("compare")
    c.add_argument("still")
    c.add_argument("reference")
    c.add_argument("--diff", default="")
    c.add_argument("--min-ssim", type=float, default=0.9)
    s = sub.add_parser("sheet")
    s.add_argument("out")
    s.add_argument("stills", nargs="+")
    s.add_argument("--labels", default="")
    s.add_argument("--cols", type=int, default=0)
    s.add_argument("--width", type=int, default=480)
    s.add_argument("--title", default="")
    o = sub.add_parser("overlay")
    o.add_argument("still")
    o.add_argument("out")
    o.add_argument("--guides", default="thirds")
    o.add_argument("--box", action="append", default=[])
    o.add_argument("--caption", default="")
    r = sub.add_parser("review")
    r.add_argument("folder")
    r.add_argument("--reference", default="")
    r.add_argument("--out", default="")
    r.add_argument("--title", default="")
    f = sub.add_parser("framing")
    f.add_argument("camera_json")
    f.add_argument("bones_json")
    f.add_argument("--subject", default="subject")
    f.add_argument("--expect-size", default="")
    bp = sub.add_parser("baseline")
    bp.add_argument("action", choices=("pull", "push", "check", "list"))
    bp.add_argument("dir")
    bp.add_argument("rest", nargs="*", help="check: SUITE STILL...")
    bp.add_argument("--suite", default="")
    bp.add_argument("--mode", default="auto", choices=("auto", "compare", "update"))
    bp.add_argument("--diff-dir", default="")
    hp = sub.add_parser("hair")
    hp.add_argument("spec")
    hp.add_argument("--out", default="")
    gp = sub.add_parser("gate")
    gp.add_argument("numbers", nargs="*")
    gp.add_argument("--spec", default="")
    gp.add_argument("--waive", action="append", default=[], help="ITEM=REASON (refused on complaint items)")
    gp.add_argument("--by", default="", help="who waives (required for a waiver)")
    gp.add_argument("--lines", action="store_true", help="check the lines against round 4's values")
    gp.add_argument("--out", default="")
    hd = sub.add_parser("head")
    hd.add_argument("folder")
    hd.add_argument("--fps", type=float, default=24.0)
    hd.add_argument("--box", default="", help="x0,y0,x1,y1 (fractions): the face to judge in a two-shot")
    hd.add_argument("--model", default="")
    hd.add_argument("--out", default="")
    hs = sub.add_parser("head-samples")
    hs.add_argument("path")
    hg = sub.add_parser("head-gate")
    hg.add_argument("out")
    hg.add_argument("results", nargs="+")
    hg.add_argument("--seen", default="", help="LABEL=f0-f1,f0-f1;LABEL=...: master frames each face is on screen")
    x = ap.parse_args(argv)
    if x.cmd == "head-gate":
        from . import qa_head as QH
        seen = {lab: [[int(v) for v in sp.split("-")] for sp in spans.split(",")]
                for lab, _, spans in (part.partition("=") for part in x.seen.split(";") if part)} if x.seen else None
        g = QH.gate(x.results, seen=seen)
        Path(x.out).write_text(json.dumps(g, indent=1))
        print(json.dumps(g, indent=1))
        raise SystemExit(0 if all("error" not in it and it["value"] <= it["line"] for it in g["gate"].values()) else 1)
    if x.cmd in ("head", "head-samples"):
        from . import qa_head as QH
        if x.cmd == "head":
            tr = QH.track(QH.frames_in(x.folder), x.fps, [float(v) for v in x.box.split(",")] if x.box else None,
                          x.model)
            res = QH.judge(tr)
            if x.out:
                Path(x.out).write_text(json.dumps({**res, "track": tr}))
        else:
            res = QH.samples(x.path)
        print(json.dumps(res, indent=1))
        raise SystemExit(0 if res["pass"] else 1)
    if x.cmd == "image":
        subs = {k: [float(v) for v in b.split(",")] for k, _, b in (s_.partition("=") for s_ in x.subject)}
        res = image(x.still, subs or None, {"stops": x.expect_stops} if x.expect_stops else None)
    elif x.cmd == "compare":
        res = compare(x.still, x.reference, x.diff, x.min_ssim)
    elif x.cmd == "sheet":
        res = sheet(x.out, x.stills, [v for v in x.labels.split(",")] if x.labels else None, x.cols, x.width, x.title)
    elif x.cmd == "overlay":
        res = overlay(x.still, x.out, [g for g in x.guides.split(",") if g], [_box(b) for b in x.box], x.caption)
    elif x.cmd == "baseline":
        if x.action == "pull":
            res = baseline_pull(x.dir, x.suite)
        elif x.action == "push":
            res = baseline_push(x.dir, x.suite)
        elif x.action == "list":
            qa()
            res = {"baselines": sys.modules["fmqa.baseline"].list_(x.dir, x.suite)}
        else:
            if len(x.rest) < 2:
                raise SystemExit("film-qa baseline check DIR SUITE STILL...")
            res = baseline_check(x.dir, x.rest[0], x.rest[1:], x.mode, x.diff_dir)
    elif x.cmd == "review":
        res = review(x.folder, x.out, x.reference, x.title)
    elif x.cmd == "hair":
        res = hair(json.loads(Path(x.spec).read_text()))
    elif x.cmd == "gate":
        if x.lines:
            qa()
            sp = json.loads(Path(x.spec).read_text()) if x.spec else None
            fails = sys.modules["fmqa.gate"].lines_fail(spec=sp)
            res = {"pass": all(v is not False for v in fails.values()), "lines_fail_round4": fails}
        else:
            if not x.numbers:
                raise SystemExit("film-qa gate NUMBERS.json... (or --lines)")
            res = gate(x.numbers, x.spec, x.waive, x.by)
    else:
        cam = json.loads(Path(x.camera_json).read_text())
        cam = cam.get("camera", cam)  # view.camera's whole result works too
        res = framing(cam, json.loads(Path(x.bones_json).read_text()), x.subject,
                      {"size": x.expect_size} if x.expect_size else None)
    if getattr(x, "out", "") and x.cmd in ("hair", "gate"):
        Path(x.out).parent.mkdir(parents=True, exist_ok=True)
        Path(x.out).write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))
    if isinstance(res, dict) and res.get("pass") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
