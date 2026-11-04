"""Overlays on a frame: composition guides (thirds, safe frames, centre, aspect masks, grids), labelled boxes and
points (a subject's bounds, a bone, where a check found a problem) and a caption. Boxes and points are fractions of
the frame (x right, y down, 0..1), the same space framing.project returns, so a check's output draws as it is."""
from __future__ import annotations

from . import draw
from .image import Image, fit

# EBU R 95 / SMPTE: action-safe 93%, title-safe 90% of the frame (modern HD values)
SAFE = {"action": 0.93, "title": 0.90}
GUIDES = ("thirds", "safe", "center", "grid:N[xM]", "aspect:2.39", "golden", "headroom")


def overlay(img: Image, guides=("thirds",), boxes=(), points=(), caption: str = "", scale: int = 0,
            width: int = 0) -> Image:
    """A copy of `img` (shrunk to `width` first when given) with guides, boxes and points drawn on it.

    guides: names from GUIDES; "grid:4x3" a grid, "aspect:2.39" masks the frame to that aspect (letterbox or
            pillarbox, half-dark so what is cut still shows), "headroom" a line 10% down (the usual top of head in a
            medium shot).
    boxes:  [{"box": [x0, y0, x1, y1], "label": str, "color": name|rgb, "fill": alpha}]
    points: [{"at": [x, y], "label": str, "color": name|rgb}]
    caption: text in a bar along the bottom."""
    out = fit(img, width).copy() if width else img.copy()
    if out.c == 1:
        from .image import rgb
        out = rgb(out)
    w, h = out.w, out.h
    s = scale or max(1, round(w / 640))
    lw = max(1, s)
    for g in guides or ():
        _guide(out, str(g), lw, s)
    for b in boxes or ():
        x0, y0, x1, y1 = b["box"]
        col = b.get("color", "subject")
        X0, Y0, X1, Y1 = round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)
        if b.get("fill"):
            draw.fill(out, X0, Y0, X1, Y1, col, float(b["fill"]))
        draw.rect(out, X0, Y0, max(X1, X0 + 2 * lw), max(Y1, Y0 + 2 * lw), col, 2 * lw)
        if b.get("label"):
            ty = Y0 - draw.GLYPH_H * s - 3 if Y0 - draw.GLYPH_H * s - 3 >= 0 else Y0 + 3
            draw.text(out, max(2, X0 + 2), max(2, ty), b["label"], "white", s, bg=col, bg_alpha=0.85)
    for p in points or ():
        x, y = p["at"]
        col = p.get("color", "subject")
        X, Y = round(x * w), round(y * h)
        draw.cross(out, X, Y, 4 * s, col, lw)
        if p.get("label"):
            draw.text(out, X + 5 * s, Y - 4 * s, p["label"], "white", s, bg="black", bg_alpha=0.5)
    if caption:
        txt = draw.wrap(caption, w - 8, s)
        _, th = draw.text_size(txt, s)
        draw.fill(out, 0, h - th - 6 * s, w, h, "black", 0.65)
        draw.text(out, 4, h - th - 3 * s, txt, "white", s)
    return out


def _guide(out: Image, g: str, lw: int, s: int) -> None:
    w, h = out.w, out.h
    if g == "thirds":
        for k in (1, 2):
            draw.line(out, w * k / 3, 0, w * k / 3, h - 1, "guide", lw, dash=6 * s)
            draw.line(out, 0, h * k / 3, w - 1, h * k / 3, "guide", lw, dash=6 * s)
    elif g == "golden":
        for f in (0.382, 0.618):
            draw.line(out, w * f, 0, w * f, h - 1, "title", lw, dash=4 * s)
            draw.line(out, 0, h * f, w - 1, h * f, "title", lw, dash=4 * s)
    elif g == "safe":
        for name, f in SAFE.items():
            mx, my = w * (1 - f) / 2, h * (1 - f) / 2
            draw.rect(out, round(mx), round(my), round(w - mx), round(h - my), "safe" if name == "action" else "title", lw)
    elif g in ("center", "centre"):
        draw.cross(out, w / 2, h / 2, 10 * s, "guide", lw)
    elif g == "headroom":
        draw.line(out, 0, h * 0.10, w - 1, h * 0.10, "title", lw, dash=3 * s)
    elif g.startswith("grid:"):
        spec = g[5:].lower()
        nx, ny = (spec.split("x") + [spec])[:2] if "x" in spec else (spec, spec)
        nx, ny = int(nx), int(ny)
        for k in range(1, nx):
            draw.line(out, w * k / nx, 0, w * k / nx, h - 1, "guide", lw, dash=3 * s)
        for k in range(1, ny):
            draw.line(out, 0, h * k / ny, w - 1, h * k / ny, "guide", lw, dash=3 * s)
    elif g.startswith("aspect:"):
        a = float(g[7:])
        cur = w / h
        if a > cur:  # wider: letterbox top and bottom
            bh = round((h - w / a) / 2)
            draw.fill(out, 0, 0, w, bh, "mask", 0.6)
            draw.fill(out, 0, h - bh, w, h, "mask", 0.6)
        elif a < cur:  # narrower: pillarbox
            bw = round((w - h * a) / 2)
            draw.fill(out, 0, 0, bw, h, "mask", 0.6)
            draw.fill(out, w - bw, 0, w, h, "mask", 0.6)
    else:
        raise ValueError(f"guide {g!r}: one of {GUIDES}")


def boxes_from_issues(issues: list) -> list:
    """Every issue that has a `box` (or a point `at`) as an overlay box coloured by its severity."""
    out = []
    for i in issues:
        if i.get("box"):
            out.append({"box": i["box"], "label": i.get("short") or i["code"].split(".")[-1], "color": i["severity"]})
    return out
