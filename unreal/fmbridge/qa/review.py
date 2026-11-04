"""The REVIEW: everything the checks found about a shot (or a scene, a character) in one JSON and one image.

A review is built from "panels", one per frame looked at: {"image": path|Image, "label", "frame", "camera",
"boxes", "issues", "metrics"}; plus scene-level issues that belong to no frame (floating props, a continuity
diff). It writes:

  review.json   {"verdict": ok|info|warn|fail, "counts", "summary": [one line per problem, worst first],
                 "issues": [...], "panels": [{"label", "frame", "camera", "status", "image", "issues"}], ...}
  review.png    a contact sheet: each frame with its problems boxed and labelled in their severity colour, a status
                border, and the worst problems written under the grid

so Claude reads the JSON first, then looks at the one picture to confirm."""
from __future__ import annotations

import json
import os

from . import draw
from .image import Image, fit, paste, read, rgb
from .issues import count, worst
from .overlay import overlay
from .sheet import contact_sheet

_RANK = {"fail": 0, "warn": 1, "info": 2}


def summarize(issues: list, limit: int = 30) -> list:
    """One line per issue, worst first: "[warn] frame 48 CamA: Ada's feet are just cut off ... -> widen ..."."""
    lines = []
    for i in sorted(issues, key=lambda i: _RANK.get(i["severity"], 3)):
        where = " ".join(str(x) for x in (f"frame {i['frame']}" if i.get("frame") is not None else "",
                                          i.get("camera") or "") if x)
        s = f"[{i['severity']}] {where + ': ' if where else ''}{i['message']}"
        if i.get("fix"):
            s += f" -> {i['fix']}"
        lines.append(s)
    return lines[:limit]


def build(panels: list, out_dir: str, title: str = "review", scene_issues: list | None = None, cell_width: int = 640,
          guides=("thirds",), extra: dict | None = None, name: str = "review") -> dict:
    """Write {out_dir}/{name}.json and {name}.png from panels (see the module doc) and scene-level issues; returns
    the report dict (with "json" and "image" paths)."""
    os.makedirs(out_dir, exist_ok=True)
    all_issues = list(scene_issues or [])
    cells, pan_out = [], []
    for k, p in enumerate(panels):
        iss = list(p.get("issues") or [])
        for i in iss:
            if p.get("frame") is not None:
                i.setdefault("frame", p["frame"])
            if p.get("camera"):
                i.setdefault("camera", p["camera"])
        all_issues += iss
        st = worst(iss)
        img = p.get("image")
        cell_img = None
        if img is not None:
            try:
                im = read(img) if isinstance(img, str) else img
                im = fit(rgb(im), cell_width)
                boxes = list(p.get("boxes") or [])
                for i in iss:
                    if i.get("box"):
                        boxes.append({"box": i["box"], "label": i["code"].split(".")[-1], "color": i["severity"]})
                cell_img = overlay(im, guides=guides, boxes=boxes, points=p.get("points") or ())
            except (OSError, ValueError) as e:
                all_issues.append({"code": "review.image_unreadable", "severity": "warn",
                                   "message": f"panel {p.get('label', k)}: {e}", "frame": p.get("frame")})
                st = worst(iss + [{"severity": "warn"}])
        if cell_img is None:
            cell_img = Image(cell_width, cell_width * 9 // 16, 3, fill=(40, 40, 40))
            draw.text(cell_img, 10, 10, "no image", "grey", 2)
        top = sorted(iss, key=lambda i: _RANK.get(i["severity"], 3))
        note = top[0]["code"].split(".", 1)[-1] if top else ""
        if len(top) > 1:
            note += f" +{len(top) - 1}"
        cells.append({"image": cell_img, "label": p.get("label") or f"frame {p.get('frame', k)}", "status": st,
                      "note": note})
        pan_out.append({"label": p.get("label"), "frame": p.get("frame"), "camera": p.get("camera"), "status": st,
                        "image": img if isinstance(img, str) else None, "issues": len(iss),
                        **({"metrics": p["metrics"]} if p.get("metrics") else {})})
    verdict = worst(all_issues)
    counts = count(all_issues)
    lines = summarize(all_issues)
    head = f"{title}: {verdict.upper()}  ({counts['fail']} fail, {counts['warn']} warn, {counts['info']} info)"
    if cells:
        sheet = contact_sheet(cells, cell_width=cell_width, title=head)
    else:
        sheet = Image(cell_width * 2, 60, 3, fill=(24, 24, 24))
        draw.text(sheet, 8, 8, head, "white", 3)
    sheet = _with_text(sheet, lines[:14] or ["no problems found"], verdict)
    png = os.path.join(out_dir, f"{name}.png")
    from .image import write
    write(sheet, png)
    report = {"title": title, "verdict": verdict, "counts": counts, "summary": lines, "issues": all_issues,
              "panels": pan_out, "image": png, **(extra or {})}
    js = os.path.join(out_dir, f"{name}.json")
    report["json"] = js
    with open(js, "w") as f:
        json.dump(report, f, indent=1, default=str)
    return report


def _with_text(sheet: Image, lines: list, verdict: str) -> Image:
    """The sheet with a text panel under it listing the problems, each line in its severity colour."""
    s = max(1, round(sheet.w / 900))
    wrapped = []
    for ln in lines:
        sev = ln[1:5] if ln.startswith("[") else "info"
        for k, part in enumerate(draw.wrap(ln, sheet.w - 16, s).split("\n")):
            wrapped.append((part if k == 0 else "   " + part, sev if sev in draw.COLORS else "white"))
    lh = draw.GLYPH_H * s + 4
    out = Image(sheet.w, sheet.h + lh * len(wrapped) + 12, 3, fill=(16, 16, 16))
    paste(out, sheet, 0, 0)
    y = sheet.h + 6
    for txt, sev in wrapped:
        draw.text(out, 8, y, txt, sev if sev in ("fail", "warn") else "white", s)
        y += lh
    draw.rect(out, 0, 0, out.w, out.h, verdict if verdict in draw.COLORS else "grey", 4)
    return out
