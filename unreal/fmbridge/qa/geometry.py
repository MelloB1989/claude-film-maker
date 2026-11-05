"""Mesh checks in numbers: objects floating above what is under them, objects overlapping (interpenetrating
props), and garment-vs-body penetration measured from two depth layers rendered from the same camera.

Penetration, the way a viewer sees it: render the depth of the body alone and of the garments alone from a camera
(qa.penetration does it with two scene captures, show-only lists). Where the garment covers a pixel and the body is
nearer than the garment there by more than a tolerance, skin pokes through cloth in that view. Viewed from several
angles (a turntable) or from the shot's own camera across its frames, that is the penetration that would show."""
from __future__ import annotations

import math

from .issues import issue

INF = float("inf")


# --- bounds ------------------------------------------------------------------------------------------------------

def aabb(origin, extent) -> tuple:
    """(min, max) corners from Unreal's (origin, box extent = half size)."""
    return (tuple(o - e for o, e in zip(origin, extent)), tuple(o + e for o, e in zip(origin, extent)))


def overlap_volume(a: tuple, b: tuple) -> float:
    """Intersection volume of two (min, max) boxes, cm^3."""
    v = 1.0
    for k in range(3):
        d = min(a[1][k], b[1][k]) - max(a[0][k], b[0][k])
        if d <= 0:
            return 0.0
        v *= d
    return v


def separation(a: tuple, b: tuple) -> float:
    """How far (cm) one box must move, along its best axis, to stop overlapping the other (0 when apart)."""
    d = [min(a[1][k], b[1][k]) - max(a[0][k], b[0][k]) for k in range(3)]
    return max(0.0, min(d)) if all(x > 0 for x in d) else 0.0


def volume(b: tuple) -> float:
    return max(0.0, (b[1][0] - b[0][0]) * (b[1][1] - b[0][1]) * (b[1][2] - b[0][2]))


def overlaps(items: dict, min_fraction: float = 0.05, ignore_pairs=(), touching_cm: float = 1.0) -> dict:
    """Pairs of objects whose bounds interpenetrate. `items` {label: (origin, extent)}. A pair counts when the
    shared volume is over `min_fraction` of the smaller box (a cup on a table shares a sliver: not counted; a chair
    sunk into a table does). Boxes are shrunk by `touching_cm` first, so objects resting on each other do not count.
    Bounds are axis-aligned: a rotated or hollow object over-reports, so treat a hit as "look here", and confirm
    with a still (the issue says which pair and where).
    Returns {"pairs": [[a, b, fraction, depth_cm]], "issues"}; depth_cm: how far to move one apart."""
    boxes = {}
    for lab, (o, e) in items.items():
        e2 = [max(0.0, x - touching_cm) for x in e]
        boxes[lab] = aabb(o, e2)
    skip = {frozenset(p) for p in ignore_pairs}
    labs = sorted(boxes)
    pairs, issues = [], []
    for i, a in enumerate(labs):
        for b in labs[i + 1:]:
            if frozenset((a, b)) in skip:
                continue
            v = overlap_volume(boxes[a], boxes[b])
            if v <= 0:
                continue
            small = min(volume(boxes[a]), volume(boxes[b])) or 1.0
            f = v / small
            if f >= min_fraction:
                pairs.append([a, b, round(f, 3), round(separation(boxes[a], boxes[b]), 2)])
    for a, b, f, depth in sorted(pairs, key=lambda p: -p[2]):
        lo = [max(boxes[a][0][k], boxes[b][0][k]) for k in range(3)]
        hi = [min(boxes[a][1][k], boxes[b][1][k]) for k in range(3)]
        centre = [round((lo[k] + hi[k]) / 2, 1) for k in range(3)]
        issues.append(issue("mesh.overlap", "warn" if f < 0.5 else "fail",
                            f"{a} and {b} interpenetrate: their bounds share {100 * f:.0f}% of the smaller one, "
                            f"{depth:.1f} cm deep, around {centre}", f"move one apart (level.move label={b!r} loc=...) or, if intended "
                            "(a prop inside a container), ignore the pair", subject=f"{a}|{b}", value=f, depth_cm=depth, at=centre))
    return {"pairs": pairs, "issues": issues}


def floating(items: dict, ground: dict, tolerance_cm: float = 1.0, max_check_cm: float = 500.0) -> dict:
    """Objects hovering. `items` {label: (origin, extent)}, `ground` {label: distance in cm from the bottom of its
    bounds down to the first thing under it (a line trace: qa.floating does it), or None when nothing is under it
    within max_check_cm}. Over `tolerance_cm` is floating; 0 or less is resting (or sunk, when well below 0).
    Returns {"gaps": {label: cm}, "issues"}."""
    gaps, issues = {}, []
    for lab in sorted(items):
        g = ground.get(lab)
        gaps[lab] = None if g is None else round(float(g), 2)
        if g is None:
            issues.append(issue("mesh.unsupported", "info", f"nothing under {lab} within {max_check_cm:.0f} cm "
                                "(meant to hang or fly?)", "lower it onto a surface (level.move) or ignore",
                                subject=lab))
        elif g > tolerance_cm:
            o, e = items[lab]
            issues.append(issue("mesh.floating", "warn" if g < 10 else "fail", f"{lab} floats {g:.1f} cm above "
                                "what is under it", f"lower it by {g:.1f} cm (level.move label={lab!r} "
                                f"loc=[{o[0]:.1f}, {o[1]:.1f}, {o[2] - g:.1f}]), or let physics rest it "
                                f"(layout.settle labels=[{lab!r}])", subject=lab, value=round(g, 2)))
        elif g < -max(tolerance_cm, 2.0):
            issues.append(issue("mesh.sunk", "info", f"{lab}'s bounds go {-g:.1f} cm into what is under it "
                                "(sunk, or its bounds are loose)", "raise it if it should rest on the surface",
                                subject=lab, value=round(g, 2)))
    return {"gaps": gaps, "issues": issues}


# --- depth layers ------------------------------------------------------------------------------------------------

def penetration(body: list, garment: list, w: int, h: int, tolerance_cm: float = 0.3, max_depth: float = 1e6) -> dict:
    """Skin through cloth from two depth layers of one view: `body` and `garment` are w*h depths (cm, row-major;
    >= max_depth or inf where the layer has nothing). A pixel penetrates where the garment is there and the body is
    nearer than it by more than `tolerance_cm`. Returns {"pixels", "garment_pixels", "fraction", "box" (fractions),
    "worst_cm", "mask" (bytearray 0/255, for an overlay), "clusters": [{"box", "pixels", "worst_cm"}]}."""
    n = w * h
    if len(body) != n or len(garment) != n:
        raise ValueError(f"depth layers must be {w}x{h} = {n} values (got {len(body)}, {len(garment)})")
    mask = bytearray(n)
    gp = hits = 0
    worst = 0.0
    for i in range(n):
        g = garment[i]
        if g >= max_depth or g != g:
            continue
        gp += 1
        b = body[i]
        if b < max_depth and g - b > tolerance_cm:
            mask[i] = 255
            hits += 1
            worst = max(worst, g - b)
    clusters = _clusters(mask, w, h, body, garment)
    box = None
    if hits:
        xs = [c["px"][0] for c in clusters] + [c["px"][2] for c in clusters]
        ys = [c["px"][1] for c in clusters] + [c["px"][3] for c in clusters]
        box = [min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h]
    return {"pixels": hits, "garment_pixels": gp, "fraction": round(hits / gp, 5) if gp else 0.0,
            "box": [round(v, 4) for v in box] if box else None, "worst_cm": round(worst, 2), "mask": mask,
            "clusters": [{k: v for k, v in c.items() if k != "px"} for c in clusters]}


def _clusters(mask: bytearray, w: int, h: int, body, garment, limit: int = 12) -> list:
    """4-connected blobs of the mask, biggest first: box (fractions, and px for internal use), pixel count, depth."""
    seen = bytearray(len(mask))
    out = []
    for start in range(len(mask)):
        if not mask[start] or seen[start]:
            continue
        stack, seen[start] = [start], 1
        x0 = y0 = 10 ** 9
        x1 = y1 = -1
        cnt, worst = 0, 0.0
        while stack:
            i = stack.pop()
            y, x = divmod(i, w)
            cnt += 1
            worst = max(worst, garment[i] - body[i])
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for j in ((i - 1) if x > 0 else -1, (i + 1) if x < w - 1 else -1, i - w, i + w):
                if 0 <= j < len(mask) and mask[j] and not seen[j]:
                    seen[j] = 1
                    stack.append(j)
        out.append({"px": [x0, y0, x1 + 1, y1 + 1], "box": [round(x0 / w, 4), round(y0 / h, 4), round((x1 + 1) / w, 4),
                    round((y1 + 1) / h, 4)], "pixels": cnt, "worst_cm": round(worst, 2)})
    out.sort(key=lambda c: -c["pixels"])
    return out[:limit]


def penetration_issues(result: dict, subject: str, view: str = "", min_fraction: float = 0.002,
                       min_pixels: int = 6, frame=None, camera=None) -> list:
    """Issues from a penetration() result: a fail over 2% of the garment, a warn over `min_fraction`."""
    out = []
    if result["pixels"] < min_pixels or result["fraction"] < min_fraction:
        return out
    sev = "fail" if result["fraction"] > 0.02 else "warn"
    for c in result["clusters"][:4]:
        if c["pixels"] < min_pixels:
            continue
        out.append(issue("mesh.penetration", sev, f"{subject}'s body shows through the garment"
                         + (f" from {view}" if view else "") + f": {c['pixels']} px, up to {c['worst_cm']:.1f} cm deep "
                         f"({100 * result['fraction']:.1f}% of the garment in view)",
                         "inflate the garment (mh.cloth_inflate) or bake face/body to one skeleton (anim.bake_follow); "
                         "check the pose at this frame", subject=subject, box=c["box"], value=c["worst_cm"],
                         frame=frame, camera=camera or (view or None)))
    return out


def mask_overlay(img, mask: bytearray, color=(255, 0, 255), alpha: float = 0.7):
    """Paint a w*h 0/255 mask (the image's size, or scaled to it) onto a copy of img."""
    from .image import Image, rgb, resize
    out = rgb(img).copy()
    mw = int(round(math.sqrt(len(mask) * out.w / out.h))) if len(mask) != out.w * out.h else out.w
    mh = len(mask) // mw if mw else 0
    m = Image(mw, mh, 1, bytearray(mask))
    if (mw, mh) != (out.w, out.h):
        m = resize(m, out.w, out.h)
    for i, v in enumerate(m.data):
        if v > 64:
            o = 3 * i
            for k in range(3):
                out.data[o + k] = int(out.data[o + k] * (1 - alpha) + color[k] * alpha)
    return out
