"""fmbridge.qa: Claude's eyes. Pure Python (the standard library; numpy when it is there), no `unreal` import, so the
same code runs inside the editor (the qa.* ops in fmbridge/ops/qa.py) and on the operator's side (filmtools.unreal.qa
and `film-ue qa ...`, on stills pulled from the box), and is unit-tested without an engine.

- image:      Image (8-bit RGB/RGBA/grey), PNG read/write, crop, resize, sRGB <-> linear
- draw:       rectangles, lines, crosses, text (a built-in 5x7 font): annotate without PIL
- overlay:    guides (thirds, safe frames, centre, aspect masks, grids), labelled boxes and points
- sheet:      contact sheets: a grid of labelled frames with a status border, a title
- metrics:    histograms, exposure (clipping, stops from mid grey), colour per region, sharpness, flat frames
- compare:    PSNR, SSIM (with a per-cell map), a diff heatmap: a frame against a reference or a previous version
- framing:    a pinhole camera model of an Unreal camera; shot size, headroom, cut-offs at joints, look room
- geometry:   bounds: floating objects, overlaps; depth-layer penetration (garment vs body)
- continuity: scene snapshots and their diffs (what moved, changed colour, appeared, vanished)
- review:     issues -> a REVIEW report (JSON) and one image that shows what is wrong

Every check returns plain dicts; problems are `issues`: {"code", "severity" (fail|warn|info), "message", "fix", ...}
so Claude can act on them without reading pictures.
"""
from .issues import issue, worst  # noqa: F401
