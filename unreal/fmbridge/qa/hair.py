"""Hair continuity: does a character's hair keep its length and mass from frame to frame and across cuts?

Round 4's operator note: "at 01:00 her hair again becomes short!" (the S17 -> S18 cut, a wide shot). A groom that
switches LOD (strands -> cards -> helmet mesh) as the character gets small in frame draws SHORTER, thinner hair;
nothing in a frame-by-frame look check sees it, because each frame is a plausible picture. Only a comparison does.

The measure, per frame, from a hair-only mask (a groom-only depth capture in the editor: qa.hair_continuity; or a
dark-pixel matte in a box on rendered frames: `luma_mask`):

- `reach`: how far the hair falls below the head, in head units: (lowest hair row - the head bone's row) / (the
  upper-chest bone's row - the head bone's row), both bones projected through the shot camera. Zoom-free, so a
  close shot and a wide shot of the same hair read the same; shoulder-length hair reads ~1, a bob ~0.5.
- `area`: hair pixels / (head unit in px)^2, also zoom-free: thinner or shorter hair reads less.
- With no bones (`scale_px` None), both fall back to the mask's own width (a weaker, pose-dependent measure: the
  result says `norm: "width"`).

Judged:
- across each cut, for the same character: the mean of the last `k` frames of the outgoing shot against the first
  `k` of the incoming one: |relative change| of reach > `cut_reach` or of area > `cut_area` FAILS;
- within a shot, frame to frame: a jump > `pop_reach` / `pop_area` FAILS (a pop: an LOD switch mid-shot).

Thresholds (THRESHOLDS, overridable): a reach change of 12% is ~2 cm on shoulder-length hair, well above what
hair simulation or a head turn moves between two consecutive frames (~1-3%), and well below a strands->cards
switch on MetaHuman long hair (the cards end at the shoulders: round 3's "shorter green hair, the cards, from f1217").
They are a first line: the round-5 probe re-reads round 4's S17->S18 frames and must FAIL there.
"""
from __future__ import annotations

from .issues import issue

THRESHOLDS = {"cut_reach": 0.12, "cut_area": 0.25, "pop_reach": 0.08, "pop_area": 0.15, "k": 4, "min_px": 40,
              "cut_pop": 1.8}  # cut_pop: round 4 S17->S18 read 2.57 (MAD 2.57 vs 0.88/1.00); shots' own pairs vary <= ~1.3
LOW_Q, HIGH_Q = 0.02, 0.98  # robust extremes: a few stray strand pixels do not move the reach


def _quantile(sorted_vals: list, q: float) -> float:
    if not sorted_vals:
        return float("nan")
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return float(sorted_vals[i])


def mask_stats(mask, width: int, height: int, head_v: float | None = None, chest_v: float | None = None) -> dict:
    """One frame's hair numbers from a mask (row-major, truthy = hair; `width` x `height`). `head_v`/`chest_v`: the
    head and upper-chest bones' rows as frame fractions (0 top .. 1 bottom), from the shot camera.
    Returns {"pixels", "box" [x0,y0,x1,y1] px, "top", "bottom" (robust rows), "reach", "area", "norm"}."""
    rows, cols = [], []
    n = 0
    for i, m in enumerate(mask):
        if m:
            rows.append(i // width)
            cols.append(i % width)
            n += 1
    out = {"pixels": n, "width": width, "height": height}
    if n == 0:
        return {**out, "reach": 0.0, "area": 0.0, "norm": "empty"}
    rows.sort()
    cols.sort()
    top, bottom = _quantile(rows, LOW_Q), _quantile(rows, HIGH_Q)
    left, right = _quantile(cols, LOW_Q), _quantile(cols, HIGH_Q)
    out.update(box=[left, top, right, bottom], top=top, bottom=bottom)
    if head_v is not None and chest_v is not None and abs(chest_v - head_v) * height > 2:
        unit = abs(chest_v - head_v) * height
        out.update(reach=round((bottom - head_v * height) / unit, 4), area=round(n / unit ** 2, 4), norm="bones",
                   unit_px=round(unit, 2))
    else:
        unit = max(1.0, right - left + 1)
        out.update(reach=round((bottom - top + 1) / unit, 4), area=round(n / unit ** 2, 4), norm="width",
                   unit_px=round(unit, 2))
    return out


def luma_mask(img, box, max_luma: float = 40.0) -> tuple:
    """A dark-hair matte on a rendered frame when no hair pass exists: pixels inside `box` (frame fractions
    [x0, y0, x1, y1]) darker than `max_luma` (0-255, Rec.709 on the 8-bit values). Black/dark hair over a lighter
    set and skin; the box (the character's head and shoulders, from the bones) keeps dark set pieces out.
    Returns (mask, width, height) of the WHOLE frame (False outside the box), so the rows stay frame rows."""
    w, h, c = img.w, img.h, img.c
    x0, y0 = int(box[0] * w), int(box[1] * h)
    x1, y1 = int(round(box[2] * w)), int(round(box[3] * h))
    d = img.data
    mask = bytearray(w * h)
    for y in range(max(0, y0), min(h, y1)):
        base = y * w
        for x in range(max(0, x0), min(w, x1)):
            p = (base + x) * c
            lum = 0.2126 * d[p] + 0.7152 * d[p + 1] + 0.0722 * d[p + 2] if c >= 3 else d[p]
            if lum < max_luma:
                mask[base + x] = 1
    return mask, w, h


def saturated(stats: dict, box, height: int, margin_px: float = 2.0) -> bool:
    """A matte whose robust bottom reaches the box's bottom edge measured the box, not the hair (at night a dark
    garment below the hair joins the matte): such a frame is not a measure (round 5 P3 on round 4's S17/S18)."""
    return bool(stats.get("pixels")) and stats.get("bottom", 0) >= box[3] * height - 1 - margin_px


def box_diff(a, b, box) -> float:
    """Mean absolute luma difference (0-255) of two frames inside `box` (frame fractions)."""
    if (a.w, a.h) != (b.w, b.h):
        raise ValueError(f"frame sizes differ: {a.w}x{a.h} vs {b.w}x{b.h}")
    w, h, ca, cb = a.w, a.h, a.c, b.c
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(round(box[2] * w)), int(round(box[3] * h))
    da, db = a.data, b.data
    tot, n = 0.0, 0
    for y in range(max(0, y0), min(h, y1)):
        for x in range(max(0, x0), min(w, x1)):
            pa, pb = (y * w + x) * ca, (y * w + x) * cb
            la = 0.2126 * da[pa] + 0.7152 * da[pa + 1] + 0.0722 * da[pa + 2] if ca >= 3 else da[pa]
            lb = 0.2126 * db[pb] + 0.7152 * db[pb + 1] + 0.0722 * db[pb + 2] if cb >= 3 else db[pb]
            tot += abs(la - lb)
            n += 1
    return tot / n if n else 0.0


def cut_pop(frames: dict, cut: int, box, floor: float = 0.5) -> dict:
    """A pop at a cut whose camera does not change (S17 -> S18: S18 is S17's end, locked off): the change across
    the cut (cut-1 -> cut) inside the head box, over the larger of the neighbours' (cut-2 -> cut-1, cut -> cut+1),
    which hold the motion and the light changes of each shot. `frames`: {frame: Image}. A hair simulation that
    restarts with a new render job, or a groom that switches LOD at the cut, reads several times its neighbours.
    Returns {"cut", "d_cut", "d_before", "d_after", "ratio"} or {"cut", "missing": [...]}."""
    need = [cut - 2, cut - 1, cut, cut + 1]
    missing = [f for f in need if f not in frames]
    if missing:
        return {"cut": cut, "missing": missing}
    d_cut = box_diff(frames[cut - 1], frames[cut], box)
    d_b = box_diff(frames[cut - 2], frames[cut - 1], box)
    d_a = box_diff(frames[cut], frames[cut + 1], box)
    return {"cut": cut, "d_cut": round(d_cut, 3), "d_before": round(d_b, 3), "d_after": round(d_a, 3),
            "ratio": round(d_cut / max(d_b, d_a, floor), 3)}


def _rel(a: float, b: float) -> float:
    return (b - a) / a if abs(a) > 1e-9 else (0.0 if abs(b) < 1e-9 else float("inf"))


def _mean(vals: list) -> float:
    return sum(vals) / len(vals) if vals else float("nan")


def judge(series: dict, cuts: list, character: str = "", thresholds: dict | None = None) -> dict:
    """Judge one character's per-frame hair numbers. `series`: {frame: mask_stats(...)} (frames the character is
    measured in; missing frames are fine). `cuts`: [[shot, first_frame, end_frame_exclusive], ...] in order.
    Returns {"pass", "issues", "cuts": [{from, to, frame, reach: [a, b, rel], area: [...]}], "pops": [...],
    "thresholds"}."""
    t = {**THRESHOLDS, **(thresholds or {})}
    k, min_px = int(t["k"]), int(t["min_px"])
    sat = sorted(int(f) for f, s in series.items() if s.get("saturated"))
    frames = {int(f): s for f, s in series.items() if s.get("pixels", 0) >= min_px and not s.get("saturated")}
    norms = {s.get("norm") for s in frames.values()}
    issues, cut_rows, pops = [], [], []
    if sat:
        issues.append(issue("hair.matte_saturated", "fail", f"{character}: the hair matte reaches the box's bottom "
                            f"edge in {len(sat)} frames (f{sat[0]}..f{sat[-1]}): it measured the box (dark clothing "
                            "joined it), not the hair, so these frames are not a measure",
                            "use the editor's groom-only capture (qa.hair_continuity), lower max_luma, or the "
                            "cut_pop check (frame differences, no matte)", subject=character))
    if "width" in norms:
        issues.append(issue("hair.norm_width", "warn", f"{character}: no bones for some frames, so reach/area are "
                            "normalised by the hair's own width (pose-dependent across a cut)",
                            "give the head/chest bones (qa.hair_continuity does) so the measure is zoom-free",
                            subject=character))
    shots = [(str(s), int(a), int(b)) for s, a, b in cuts]
    for (sa, a0, a1), (sb, b0, b1) in zip(shots, shots[1:]):
        before = [frames[f] for f in range(a1 - 1, a0 - 1, -1) if f in frames][:k]
        after = [frames[f] for f in range(b0, b1) if f in frames][:k]
        if not (before and after):
            continue  # the character is not in both shots: no continuity to keep
        ra, rb = _mean([s["reach"] for s in before]), _mean([s["reach"] for s in after])
        aa, ab = _mean([s["area"] for s in before]), _mean([s["area"] for s in after])
        dr, da = _rel(ra, rb), _rel(aa, ab)
        row = {"from": sa, "to": sb, "frame": b0, "reach": [round(ra, 4), round(rb, 4), round(dr, 4)],
               "area": [round(aa, 4), round(ab, 4), round(da, 4)]}
        cut_rows.append(row)
        bad = []
        if abs(dr) > t["cut_reach"]:
            bad.append(f"reach {ra:.3f} -> {rb:.3f} ({dr:+.1%}, line {t['cut_reach']:.0%})")
        if abs(da) > t["cut_area"]:
            bad.append(f"area {aa:.3f} -> {ab:.3f} ({da:+.1%}, line {t['cut_area']:.0%})")
        if bad:
            row["fail"] = True
            issues.append(issue("hair.cut_jump", "fail",
                                f"{character}: hair changes across the cut {sa} -> {sb} at f{b0}: " + "; ".join(bad)
                                + (" (SHORTER)" if dr < 0 else ""),
                                "lock the grooms (film-ue op groom.lock labels=...; render with its render_cvars), "
                                "then re-render both shots and re-run this check",
                                subject=character, frame=b0, value=round(dr, 4), expected=t["cut_reach"]))
    for s, a0, a1 in shots:
        prev = None
        for f in range(a0, a1):
            cur = frames.get(f)
            if cur is None:
                prev = None
                continue
            if prev is not None:
                dr, da = _rel(prev["reach"], cur["reach"]), _rel(prev["area"], cur["area"])
                if abs(dr) > t["pop_reach"] or abs(da) > t["pop_area"]:
                    pops.append({"shot": s, "frame": f, "reach": round(dr, 4), "area": round(da, 4)})
                    issues.append(issue("hair.pop", "fail",
                                        f"{character}: hair pops inside {s} at f{f}: reach {dr:+.1%}, area {da:+.1%} "
                                        f"(lines {t['pop_reach']:.0%} / {t['pop_area']:.0%})",
                                        "an LOD switch mid-shot: groom.lock, or a hair simulation reset (warm-up "
                                        "frames before the shot: render preroll)", subject=character, frame=f))
            prev = cur
    return {"pass": not any(i["severity"] == "fail" for i in issues), "character": character, "issues": issues,
            "cuts": cut_rows, "pops": pops, "frames": len(frames), "thresholds": t}
