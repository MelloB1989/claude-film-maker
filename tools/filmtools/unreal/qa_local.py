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
    film-qa head DIR --fps 24 [--box x0,y0,x1,y1] [--out R.json]   the head through the blinks, from the frames
                                                 (face landmarks; needs `uv run --with mediapipe==0.10.21`)
    film-qa head-samples QA_OUT.json             re-judge qa.head_stability's saved samples (out=), offline
    film-qa head-gate OUT.json QA_OUT.json...     gate v2's head.blink_nod_deg from qa.head_stability results

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
                "baseline"):
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
    x = ap.parse_args(argv)
    if x.cmd == "head-gate":
        from . import qa_head as QH
        g = QH.gate(x.results)
        Path(x.out).write_text(json.dumps(g, indent=1))
        it = g["gate"]["head.blink_nod_deg"]
        print(json.dumps(g, indent=1))
        raise SystemExit(0 if "error" not in it and it["value"] <= it["line"] else 1)
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
    else:
        cam = json.loads(Path(x.camera_json).read_text())
        cam = cam.get("camera", cam)  # view.camera's whole result works too
        res = framing(cam, json.loads(Path(x.bones_json).read_text()), x.subject,
                      {"size": x.expect_size} if x.expect_size else None)
    print(json.dumps(res, indent=1, default=str))
    if isinstance(res, dict) and res.get("pass") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
