"""Contact sheets: many frames in one image, each labelled (frame, camera, what a check said) and framed in its
status colour, with a title bar. One picture Claude can read for a whole shot, a turntable or a before/after."""
from __future__ import annotations

import math

from . import draw
from .image import Image, fit, paste, read, resize, rgb


def contact_sheet(cells: list, cols: int = 0, cell_width: int = 480, title: str = "", gap: int = 6,
                  bg=(24, 24, 24), label_scale: int = 0) -> Image:
    """A grid of frames. `cells`: each an Image, a path, or a dict {"image": Image|path, "label": str,
    "status": ok|info|warn|fail, "note": str}. `cols` 0 picks a near-square grid. Every cell is fitted to
    `cell_width` and to the tallest cell's aspect; a label strip (and an optional note line) sits under each."""
    items = [c if isinstance(c, dict) else {"image": c} for c in cells]
    if not items:
        raise ValueError("contact_sheet: no cells")
    imgs = []
    for it in items:
        im = it["image"]
        im = read(im) if isinstance(im, str) else im
        imgs.append(rgb(fit(im, cell_width)) if im.w > cell_width else rgb(im))
    n = len(imgs)
    cols = cols or max(1, math.ceil(math.sqrt(n * 9 / 16)) if n > 2 else n)
    cols = min(cols, n)
    rows = math.ceil(n / cols)
    cw = max(i.w for i in imgs)
    ch = max(i.h for i in imgs)
    s = label_scale or max(1, round(cw / 400))
    has_note = any(it.get("note") for it in items)
    lh = (draw.GLYPH_H * s + 6) * (2 if has_note else 1)
    th = draw.GLYPH_H * (s + 1) + 12 if title else 0
    W = cols * cw + (cols + 1) * gap
    H = th + rows * (ch + lh) + (rows + 1) * gap
    sheet = Image(W, H, 3, fill=tuple(bg))
    if title:
        draw.text(sheet, gap, 6, title, "white", s + 1)
    for k, (it, im) in enumerate(zip(items, imgs)):
        r, c = divmod(k, cols)
        x = gap + c * (cw + gap)
        y = th + gap + r * (ch + lh + gap)
        if (im.w, im.h) != (cw, ch):  # letterbox a smaller or differently shaped frame in its cell
            px, py = x + (cw - im.w) // 2, y + (ch - im.h) // 2
        else:
            px, py = x, y
        paste(sheet, im, px, py)
        st = it.get("status")
        if st:
            draw.rect(sheet, x - 3, y - 3, x + cw + 3, y + ch + 3, st, 3)
        lab = str(it.get("label", ""))
        if lab:
            maxc = max(1, cw // (draw.GLYPH_W * s))
            draw.text(sheet, x, y + ch + 4, lab[:maxc], "white" if not st else st, s)
        if it.get("note"):
            maxc = max(1, cw // (draw.GLYPH_W * s))
            draw.text(sheet, x, y + ch + 4 + draw.GLYPH_H * s + 6, str(it["note"])[:maxc], "grey", s)
    return sheet


def side_by_side(a: Image, b: Image, labels=("A", "B"), height: int = 0) -> Image:
    """Two frames next to each other at one height (a before/after, a frame and its reference)."""
    hh = height or min(a.h, b.h)
    a2 = resize(rgb(a), max(1, round(a.w * hh / a.h)), hh)
    b2 = resize(rgb(b), max(1, round(b.w * hh / b.h)), hh)
    return contact_sheet([{"image": a2, "label": labels[0]}, {"image": b2, "label": labels[1]}], cols=2,
                         cell_width=max(a2.w, b2.w))
