"""Motion metrics: turn "smooth" into numbers, per frame, for any video or PNG/JPG frame folder.

    python -m filmtools.amv3.motion_metrics VIDEO_OR_DIR --out DIR [--width 480] [--start F] [--end F]
    python -m filmtools.amv3.motion_metrics --compare DIR_A DIR_B ... --out table.md

Per frame (row f compares frame f-1 -> f; all px figures are in 1080-line units, so 4:5 and 16:9 videos compare):
- global camera motion: a similarity transform fitted (RANSAC) to the dense DIS optical flow on a grid:
  `zoom` (d ln scale / f, + = picture grows = push in), `rot` (deg / f, + = picture turns clockwise on screen),
  `tx`, `ty` (px / f of the frame centre), `gspeed` (RMS displacement of the fitted model over the frame, px / f),
  `inl` (RANSAC inlier ratio; `gfail` = 1 where the fit is not trusted: inl < 0.1 or a cut)
- `flow_med`, `flow_mean`: median / mean optical-flow magnitude (subject + camera), px / f
- `sharp`: variance of the Laplacian (960-wide grey); `sharp_rel`: sharp / the 75th percentile of its shot (the
  stretch between two detected cuts), so 1.0 = as sharp as the shot normally is and < 0.5 = smeared
- `luma`: mean Rec.709 luma 0-255
- `resid`: mean abs error after warping f back onto f-1 with the flow (low = same picture moved; high = new picture);
  `hist_d`: Bhattacharyya distance of HS histograms; `cut` = 1 on the first frame of a new shot;
  `dup` = 1 on a repeated frame (identical to the previous one while the neighbours move: judder)

Derived (summary.json): % still frames, speed-ratio jumps outside cut windows, per-cut acceleration curves, smear frames
per cut, frames to re-sharpen, cut speed peak. See films/timeless/amv3/REFS.md "Motion metrics".

Caveats: on fully smeared frames flow under-reads the true camera speed (the motion is inside the blur, not between
frames); those frames show up as low sharp_rel, and gfail when the fit breaks. Burnt-in text and letterbox bars pull the
fit toward zero; the grid skips a 4 % border.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

STILL_PX = 0.5          # median flow below this (px/f, 1080 units) = a still frame
SLOW_PX = 4.0           # mean flow below this (px/f) outside transitions = a near-static frame (v2's "dead" holds)
JUMP_FLOOR = 2.0        # speeds below this are floored before taking ratios (noise)
JUMP_RATIO = 1.35       # EDIT.md motion rule: speed may change by at most x1.35 per frame outside accelerations
CUT_GUARD = 6           # frames either side of a cut excluded from the "outside cuts" stats
SMEAR_REL = 0.5         # sharp_rel below this = smeared
SHARP_REL = 0.8         # sharp_rel at or above this (2 frames running) = landed sharp


# ---------------------------------------------------------------- frame sources
def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg  # static build with libdav1d (AV1 references)
    return imageio_ffmpeg.get_ffmpeg_exe()


def _probe(path: Path) -> tuple[int, int, float]:
    cap = cv2.VideoCapture(str(path))
    w, h, fps = int(cap.get(3)), int(cap.get(4)), cap.get(5) or 30.0
    cap.release()
    if w and h:
        return w, h, fps
    out = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    import re
    m = re.search(r"Video:.*?(\d{3,5})x(\d{3,5}).*?([\d.]+) fps", out)
    if not m:
        raise SystemExit(f"cannot probe {path}")
    return int(m.group(1)), int(m.group(2)), float(m.group(3))


def frames(src: Path, width: int, start: int = 0, end: int | None = None):
    """Yield (frame, BGR uint8 frame at `width` px wide). Video via an ffmpeg pipe, or a folder of images (sorted;
    the frame number is the last number in the file name, e.g. f_00480.png -> 480)."""
    if src.is_dir():
        import re
        files = sorted(p for p in src.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
        nums = [re.findall(r"\d+", p.stem) for p in files]
        # frame number from the file name (stage passes are f_NNNNN.png = comp frame), else the index
        idx = [int(n[-1]) for n in nums] if all(nums) else list(range(len(files)))
        for i, p in zip(idx, files):
            if i < start:
                continue
            if end is not None and i >= end:
                break
            im = cv2.imread(str(p), cv2.IMREAD_COLOR)
            h = round(im.shape[0] * width / im.shape[1] / 2) * 2
            yield i, cv2.resize(im, (width, h), interpolation=cv2.INTER_AREA)
        return
    w0, h0, _ = _probe(src)
    h = round(h0 * width / w0 / 2) * 2
    cmd = [_ffmpeg(), "-v", "error", "-i", str(src), "-vf", f"scale={width}:{h}:flags=area",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = width * h * 3
    i = 0
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            if i >= start and (end is None or i < end):
                yield i, np.frombuffer(buf, np.uint8).reshape(h, width, 3)
            i += 1
            if end is not None and i >= end:
                break
    finally:
        p.stdout.close()
        p.kill()
        p.wait()


def source_height(src: Path) -> int:
    if src.is_dir():
        f = next(p for p in sorted(src.iterdir()) if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
        return cv2.imread(str(f)).shape[0]
    return _probe(src)[1]


# ---------------------------------------------------------------- per-frame measures
def _grid(h: int, w: int, step: int = 6, border: float = 0.04):
    ys = np.arange(int(h * border), int(h * (1 - border)), step)
    xs = np.arange(int(w * border), int(w * (1 - border)), step)
    gx, gy = np.meshgrid(xs, ys)
    return np.stack([gx.ravel(), gy.ravel()], 1).astype(np.float32)


def _fit_similarity(pts, flow, w, h):
    """Similarity (scale, rot, translation of the centre) fitted to flow vectors at pts, RANSAC."""
    d = flow[pts[:, 1].astype(int), pts[:, 0].astype(int)]
    dst = pts + d
    M, inl = cv2.estimateAffinePartial2D(pts, dst, method=cv2.RANSAC, ransacReprojThreshold=max(1.0, w / 320),
                                         maxIters=3000, confidence=0.995)
    if M is None:
        return None
    a, b = M[0, 0], M[1, 0]
    s = math.hypot(a, b)
    rot = math.degrees(math.atan2(b, a))
    c = np.array([w / 2, h / 2])
    tc = M[:, :2] @ c + M[:, 2] - c
    model = pts @ M[:, :2].T + M[:, 2] - pts
    rms = float(np.sqrt((model ** 2).sum(1).mean()))
    return dict(zoom=math.log(s), rot=rot, tx=float(tc[0]), ty=float(tc[1]), gspeed=rms,
                inl=float(inl.mean()) if inl is not None else 0.0)


def _hs_hist(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [30, 16], [0, 180, 0, 256])
    return cv2.normalize(hist, hist).flatten()


def measure(src: Path, width: int = 480, start: int = 0, end: int | None = None, log=print) -> list[dict]:
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    rows, prev = [], None
    for i, bgr in frames(src, max(width, 960), start, end):
        big = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        small_bgr = cv2.resize(bgr, (width, round(bgr.shape[0] * width / bgr.shape[1])), interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2GRAY)
        h, w = g.shape
        k = 1080.0 / h                                 # analysis px -> 1080-line px
        lap = cv2.Laplacian(big, cv2.CV_32F, ksize=3)
        luma = float((0.2126 * bgr[..., 2] + 0.7152 * bgr[..., 1] + 0.0722 * bgr[..., 0]).mean())
        row = dict(frame=i, sharp=float(lap.var()), luma=luma)
        hist = _hs_hist(small_bgr)
        if prev is not None:
            pg, phist = prev
            flow = dis.calc(pg, g, None)
            mag = np.linalg.norm(flow, axis=2)
            row["flow_med"] = float(np.median(mag)) * k
            row["flow_mean"] = float(mag.mean()) * k
            gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
            back = cv2.remap(g, gx + flow[..., 0], gy + flow[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            row["resid"] = float(np.abs(back.astype(np.float32) - pg.astype(np.float32)).mean())
            row["hist_d"] = float(cv2.compareHist(phist, hist, cv2.HISTCMP_BHATTACHARYYA))
            fit = _fit_similarity(_GRID(h, w), flow, w, h)
            if fit:
                for key in ("tx", "ty", "gspeed"):
                    fit[key] *= k
                row.update(fit)
        prev = (g, hist)
        rows.append(row)
        if i % 100 == 0:
            log(f"  frame {i}")
    return rows


_grid_cache: dict = {}


def _GRID(h, w):
    if (h, w) not in _grid_cache:
        _grid_cache[(h, w)] = _grid(h, w, step=max(4, w // 80))
    return _grid_cache[(h, w)]


# ---------------------------------------------------------------- cuts and derived stats
def detect_cuts(rows: list[dict]) -> None:
    """Mark row["cut"] = 1 on the first frame of a new shot: the flow cannot explain the new picture (residual far above
    the local level) and the colour histogram jumps. Peaks only (one frame per cut)."""
    n = len(rows)
    res = np.array([r.get("resid", 0.0) for r in rows])
    hd = np.array([r.get("hist_d", 0.0) for r in rows])
    score = np.zeros(n)
    for i in range(1, n):
        lo, hi = max(1, i - 15), min(n, i + 16)
        local = np.median(np.r_[res[lo:i], res[i + 1:hi]]) if hi - lo > 1 else res[i]
        score[i] = (res[i] / max(local, 2.0)) * (0.5 + 2.0 * hd[i])
    for i, r in enumerate(rows):
        r["cut_score"] = float(score[i])
        r["cut"] = 0
    for i in range(1, n):
        if score[i] < 2.5 or (res[i] < 10 and hd[i] < 0.3):
            continue
        if min(rows[i - 1]["luma"], rows[i]["luma"]) < 6:       # fading from/to black, not a cut
            continue
        if score[i] >= score[max(1, i - 3):i + 4].max():
            rows[i]["cut"] = 1


def _segments(rows):
    cuts = [r["frame"] for r in rows if r["cut"]]
    edges = [rows[0]["frame"]] + cuts + [rows[-1]["frame"] + 1]
    return list(zip(edges[:-1], edges[1:]))


def finish(rows: list[dict]) -> None:
    by = {r["frame"]: r for r in rows}
    for a, b in _segments(rows):
        vals = [by[f]["sharp"] for f in range(a, b)]
        ref = max(np.percentile(vals, 75), 1e-6)
        for f in range(a, b):
            by[f]["sharp_rel"] = by[f]["sharp"] / ref
    for r in rows:
        r["gfail"] = int(r["cut"] == 1 or r.get("inl", 0.0) < 0.1 or "gspeed" not in r)
    # duplicated frames (frame-rate conversion / encoder repeats): identical to the previous frame while the neighbours
    # move. They are judder, and they would fake a x50 speed jump, so they are counted and skipped by the jump stats.
    for i in range(1, len(rows) - 1):
        r = rows[i]
        fm, nb = r.get("flow_mean", 9), min(rows[i - 1].get("flow_mean", 0), rows[i + 1].get("flow_mean", 0))
        r["dup"] = int((r.get("resid", 9) < 0.3 and fm < 0.3 and nb > 2.0)
                       or (nb > 4.0 and fm < 0.12 * nb and r.get("gspeed", 9) < 0.5))   # repeat + grain/flicker
    rows[0]["dup"] = rows[-1]["dup"] = 0


def detect_events(rows: list[dict]) -> None:
    """Transitions = hard cuts (event 1) + smear-throughs (event 2): a run of >= 2 frames that are both fast
    (mean flow >= 45 px/f) and smeared (sharpness < 0.35 x its +-30 f neighbourhood's 75th percentile) with no hard
    cut within 6 f. The cut of a zoom-through is often hidden inside the smear (a dissolve inside the blur); the event
    frame is the fastest frame of the run."""
    n = len(rows)
    sharp = np.array([r["sharp"] for r in rows])
    flow = np.array([r.get("flow_mean", 0.0) for r in rows])
    loc = np.zeros(n)
    for i in range(n):
        loc[i] = sharp[i] / max(np.percentile(sharp[max(0, i - 30):i + 31], 75), 1e-6)
    for i, r in enumerate(rows):
        r["sharp_loc"] = float(loc[i])
        r["event"] = 1 if r["cut"] else 0
    cut_idx = [i for i, r in enumerate(rows) if r["cut"]]
    i = 0
    while i < n:
        if flow[i] >= 45 and loc[i] < 0.35:
            j = i
            while j + 1 < n and flow[j + 1] >= 45 and loc[j + 1] < 0.35:
                j += 1
            dark = min(r["luma"] for r in rows[i:j + 1]) < 12           # a fade from/to black, not a transition
            if j > i and not dark and not any(i - 6 <= c <= j + 6 for c in cut_idx):
                rows[i + int(np.argmax(flow[i:j + 1]))]["event"] = 2
            i = j + 1
        else:
            i += 1


def _longest(rows, pred):
    """Longest run of consecutive frames satisfying pred."""
    run = best = 0
    prev = None
    for r in rows:
        if pred(r):
            run = run + 1 if prev is not None and r["frame"] == prev + 1 and run else 1
            best = max(best, run)
        else:
            run = 0
        prev = r["frame"]
    return best


def _med(v):
    v = [x for x in v if x is not None]
    return round(float(np.median(v)), 2) if v else None


def summarize(rows: list[dict], name: str) -> dict:
    by = {r["frame"]: r for r in rows}
    f0, f1 = rows[0]["frame"], rows[-1]["frame"]
    hard = [r["frame"] for r in rows if r["cut"]]
    cuts = [r["frame"] for r in rows if r["event"]]          # every transition: hard cuts + smear-throughs
    near = set()
    for c in cuts:
        near.update(range(c - CUT_GUARD, c + CUT_GUARD + 1))
    moving = [r for r in rows[1:] if not r["cut"] and not r["dup"]]
    still = [r for r in moving if r.get("flow_med", 0) < STILL_PX]
    still_g = [r for r in moving if not r["gfail"] and r.get("gspeed", 0) < STILL_PX and r.get("flow_med", 0) < STILL_PX]

    # longest run of still frames
    run = best = 0
    best_end = None
    for r in moving:
        run = run + 1 if r.get("flow_med", 0) < STILL_PX else 0
        if run > best:
            best, best_end = run, r["frame"]

    # speed-ratio jumps outside cut windows (floored), between consecutive non-duplicate frames:
    # camera speed (similarity fit; skipped where the fit failed) and picture speed (mean flow)
    seq = [r for r in rows[8:] if not r["dup"]]          # skip the first frames (fade-ins)
    jumps, fjumps = [], []
    for a, b in zip(seq[:-1], seq[1:]):
        f = b["frame"]
        if f in near or a["frame"] in near:
            continue
        va, vb = max(a["flow_mean"], JUMP_FLOOR), max(b["flow_mean"], JUMP_FLOOR)
        fjumps.append((max(va, vb) / min(va, vb), f))
        if a["gfail"] or b["gfail"]:
            continue
        va, vb = max(a["gspeed"], JUMP_FLOOR), max(b["gspeed"], JUMP_FLOOR)
        jumps.append((max(va, vb) / min(va, vb), f))
    jr = np.array([j[0] for j in jumps]) if jumps else np.array([1.0])
    fr = np.array([j[0] for j in fjumps]) if fjumps else np.array([1.0])
    worst = sorted(fjumps, reverse=True)[:10]

    percut = []
    bounds = [f0] + cuts + [f1 + 1]
    for k, c in enumerate(cuts):
        def val(f, key):
            r = by.get(f)
            if r is None or key not in r or r["dup"] or (key in ("gspeed", "zoom", "rot") and r["gfail"]):
                return None
            return r[key]

        def p75(lo, hi):
            v = [by[f]["sharp"] for f in range(lo, hi) if f in by]
            return max(np.percentile(v, 75), 1e-6) if v else 1.0
        # sharpness relative to the shot each frame belongs to (A before the transition frame, B from it on)
        ref_a, ref_b = p75(bounds[k], c), p75(c, bounds[k + 2])
        rel = {f: by[f]["sharp"] / (ref_a if f < c else ref_b) for f in range(c - 10, c + 16) if f in by}
        # smear = the contiguous run of smeared frames that touches the transition frame
        smear = []
        for step in (-1, 1):
            f = c if step == 1 else c - 1
            while f in rel and rel[f] < SMEAR_REL and abs(f - c) <= 10:
                smear.append(f)
                f += step
        sharp_at = None
        for f in range(c, c + 15):
            if rel.get(f, 0) >= SHARP_REL and rel.get(f + 1, 0) >= SHARP_REL:
                sharp_at = f - c
                break
        legible_at = next((f - c for f in range(c, c + 15) if rel.get(f, 0) >= SMEAR_REL), None)
        flow = {f: val(f, "flow_mean") for f in range(c - 10, c + 16)}
        pre = [flow[f] for f in range(c - 8, c)]
        post = [flow[f] for f in range(c + 1, c + 13)]
        # acceleration into the transition: per-frame growth of picture speed over the 4 frames before its peak
        acc = None
        if all(flow.get(f) for f in (c - 5, c - 1)) and flow[c - 5] > 1:
            acc = round((flow[c - 1] / flow[c - 5]) ** 0.25, 2)
        dec = None
        if all(flow.get(f) for f in (c + 1, c + 9)) and flow[c + 9] > 1:
            dec = round((flow[c + 1] / flow[c + 9]) ** 0.125, 2)
        # the worst single-frame speed step on the way in (c-8..c-1) and on the way out (c+1..c+12): a smooth ease
        # changes speed by a steady factor per frame, a square-wave move (v2) jumps x5+ in one frame
        def steps(lo, hi, up):
            out = []
            for f in range(lo, hi):
                x, y = flow.get(f), flow.get(f + 1)
                if x is None or y is None:
                    continue
                x, y = max(x, JUMP_FLOOR), max(y, JUMP_FLOOR)
                out.append(y / x if up else x / y)
            return round(max(out), 2) if out else None
        step_in, step_out = steps(c - 8, c - 1, True), steps(c + 1, c + 12, False)
        # speed continuity across the transition: picture speed just after / just before
        across = round(flow[c + 1] / flow[c - 1], 2) if flow.get(c - 1) and flow.get(c + 1) else None
        # direction continuity: dominant zoom / roll sign before vs after (|zoom| >= 1 %/f, |roll| >= 0.3 deg/f)
        zp = [v for v in (val(f, "zoom") for f in range(c - 4, c)) if v is not None]
        zq = [v for v in (val(f, "zoom") for f in range(c + 1, c + 5)) if v is not None]
        zdir = None
        if zp and zq and abs(np.median(zp)) >= 0.01 and abs(np.median(zq)) >= 0.01:
            zdir = "push->push" if np.median(zp) > 0 and np.median(zq) > 0 else \
                   "pull->pull" if np.median(zp) < 0 and np.median(zq) < 0 else \
                   "push->pull" if np.median(zp) > 0 else "pull->push"
        peak = max([v for v in (flow.get(f) for f in range(c - 2, c + 3)) if v is not None], default=None)
        r2 = lambda v: None if v is None else round(v, 2)  # noqa: E731
        percut.append(dict(cut=c, kind="hard" if c in hard else "smear", pre_flow=[r2(v) for v in pre],
                           post_flow=[r2(v) for v in post],
                           sharp_rel=[round(rel.get(f, float("nan")), 2) for f in range(c - 4, c + 11)],
                           smear_frames=len(smear), legible=legible_at, resharpen=sharp_at, accel_per_f=acc, decel_per_f=dec,
                           speed_across=across, step_in=step_in, step_out=step_out, zoom_dir=zdir, peak_flow=r2(peak),
                           zoom_pre=[round(v * 100, 1) for v in zp], zoom_post=[round(v * 100, 1) for v in zq],
                           rot_pre=[r2(val(f, "rot")) for f in range(c - 3, c)],
                           rot_post=[r2(val(f, "rot")) for f in range(c + 1, c + 4)]))

    shot_len = np.diff([f0] + cuts + [f1 + 1]) if cuts else np.array([f1 - f0 + 1])
    hold = [r for r in moving if r["frame"] not in near and not r["gfail"]]
    sm = [p["smear_frames"] for p in percut]
    rs = [p["resharpen"] for p in percut if p["resharpen"] is not None]
    pk = [p["peak_flow"] for p in percut if p["peak_flow"] is not None]
    return dict(
        name=name, frames=len(rows), first=f0, last=f1, cuts=cuts, n_cuts=len(cuts), hard_cuts=hard,
        smear_throughs=[f for f in cuts if f not in hard],
        shot_len_median=float(np.median(shot_len)), shot_len_min=int(shot_len.min()), shot_len_max=int(shot_len.max()),
        still_pct=round(100 * len(still) / max(1, len(moving)), 1),
        still_global_pct=round(100 * len(still_g) / max(1, len(moving)), 1),
        longest_still_run=best, longest_still_run_end=best_end,
        hold_gspeed_median=round(float(np.median([r["gspeed"] for r in hold])), 2) if hold else None,
        hold_gspeed_p10=round(float(np.percentile([r["gspeed"] for r in hold], 10)), 2) if hold else None,
        hold_flow_median=round(float(np.median([r["flow_mean"] for r in hold])), 2) if hold else None,
        jump_ratio_p50=round(float(np.percentile(jr, 50)), 3), jump_ratio_p95=round(float(np.percentile(jr, 95)), 3),
        jump_ratio_max=round(float(jr.max()), 2), jump_pct_over=round(100 * float((jr > JUMP_RATIO).mean()), 1),
        flow_jump_p50=round(float(np.percentile(fr, 50)), 3), flow_jump_p95=round(float(np.percentile(fr, 95)), 3),
        flow_jump_max=round(float(fr.max()), 2), flow_jump_pct_over=round(100 * float((fr > JUMP_RATIO).mean()), 1),
        worst_jumps=[dict(frame=f, ratio=round(v, 2)) for v, f in worst],
        dup_frames=[r["frame"] for r in rows if r["dup"]],
        dup_pct=round(100 * sum(r["dup"] for r in rows) / len(rows), 1),
        smear_frames_median=float(np.median(sm)) if sm else None,
        cuts_with_smear_pct=round(100 * sum(1 for s in sm if s >= 2) / max(1, len(sm)), 1),
        hard_cuts_pct=round(100 * sum(1 for s in sm if s == 0) / max(1, len(sm)), 1),
        legible_median=_med([p["legible"] for p in percut]),
        resharpen_median=float(np.median(rs)) if rs else None, resharpen_max=max(rs) if rs else None,
        cut_peak_flow_median=round(float(np.median(pk)), 1) if pk else None,
        accel_per_f_median=_med([p["accel_per_f"] for p in percut]),
        decel_per_f_median=_med([p["decel_per_f"] for p in percut]),
        step_in_median=_med([p["step_in"] for p in percut]), step_out_median=_med([p["step_out"] for p in percut]),
        step_out_p90=round(float(np.percentile([p["step_out"] for p in percut if p["step_out"]], 90)), 2)
        if any(p["step_out"] for p in percut) else None,
        speed_across_median=_med([p["speed_across"] for p in percut]),
        speed_across_bad_pct=round(100 * sum(1 for p in percut if p["speed_across"] and not 0.5 <= p["speed_across"] <= 2)
                                   / max(1, sum(1 for p in percut if p["speed_across"])), 1),
        zoom_dir_counts={d: sum(1 for p in percut if p["zoom_dir"] == d)
                         for d in ("push->push", "pull->pull", "push->pull", "pull->push", None)},
        hold_zoom_median=round(100 * float(np.median([abs(r["zoom"]) for r in hold])), 2) if hold else None,
        hold_roll_median=round(float(np.median([abs(r["rot"]) for r in hold])), 3) if hold else None,
        zoom_reversed_pct=round(100 * sum(1 for p in percut if p["zoom_dir"] in ("push->pull", "pull->push"))
                                / max(1, sum(1 for p in percut if p["zoom_dir"])), 1),
        longest_slow_run=_longest([r for r in moving if r["frame"] not in near], lambda r: r.get("flow_mean", 0) < SLOW_PX),
        slow_pct=round(100 * sum(1 for r in moving if r["frame"] not in near and r.get("flow_mean", 0) < SLOW_PX)
                       / max(1, sum(1 for r in moving if r["frame"] not in near)), 1),
        gfail_pct=round(100 * sum(r["gfail"] for r in rows[1:]) / max(1, len(rows) - 1), 1),
        per_cut=percut,
    )


# ---------------------------------------------------------------- outputs
COLS = ["frame", "cut", "dup", "gspeed", "zoom", "rot", "tx", "ty", "inl", "gfail", "flow_med", "flow_mean", "sharp",
        "sharp_rel", "sharp_loc", "event", "luma", "resid", "hist_d", "cut_score"]


def write_csv(rows, path: Path):
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        for r in rows:
            w.writerow(["" if r.get(c) is None else (round(r[c], 4) if isinstance(r.get(c), float) else r.get(c, ""))
                        for c in COLS])


def read_csv(path: Path) -> list[dict]:
    out = []
    with path.open() as fh:
        for r in csv.DictReader(fh):
            out.append({k: (int(v) if k in ("frame", "cut", "gfail", "dup", "event") else float(v)) for k, v in r.items() if v != ""})
    return out


def plot(rows, summary, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    f = np.array([r["frame"] for r in rows])

    def col(k):
        return np.array([r.get(k, np.nan) if not (k == "gspeed" and r["gfail"]) else np.nan for r in rows], float)

    ink, muted, accent, cutc = "#1f2328", "#8c959f", "#2f6fdd", "#d1495b"
    fig, ax = plt.subplots(5, 1, figsize=(18, 11), sharex=True, gridspec_kw=dict(hspace=0.12))
    ax[0].plot(f, col("flow_mean"), color=muted, lw=1, label="mean flow")
    ax[0].plot(f, col("gspeed"), color=accent, lw=1.6, label="camera (similarity fit)")
    ax[0].set_yscale("symlog", linthresh=2)
    ax[0].axhline(STILL_PX, color=muted, lw=0.6, ls=":")
    ax[0].set_ylabel("px / frame")
    ax[0].legend(loc="upper right", frameon=False, fontsize=8)
    ax[1].plot(f, col("zoom") * 100, color=accent, lw=1.2)
    ax[1].axhline(0, color=muted, lw=0.6)
    ax[1].set_ylabel("zoom %/f")
    ax[2].plot(f, col("rot"), color=accent, lw=1.2)
    ax[2].axhline(0, color=muted, lw=0.6)
    ax[2].set_ylabel("roll deg/f")
    ax[3].plot(f, np.clip(col("sharp_rel"), 0, 2), color=accent, lw=1.2)
    ax[3].axhline(SMEAR_REL, color=muted, lw=0.6, ls=":")
    ax[3].set_ylabel("sharpness rel")
    ax[4].plot(f, col("luma"), color=accent, lw=1.2)
    ax[4].set_ylabel("luma")
    ax[4].set_xlabel("frame")
    for a in ax:
        for c in summary["cuts"]:
            a.axvline(c, color=cutc, lw=0.7, alpha=0.6)
        a.grid(axis="y", color="#d0d7de", lw=0.5)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        a.tick_params(colors=ink, labelsize=8)
    ax[4].xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(30))
    ax[0].set_title(f"{summary['name']}: {summary['n_cuts']} cuts (red), still {summary['still_pct']} %, "
                    f"jump p95 x{summary['jump_ratio_p95']}, smear/cut {summary['smear_frames_median']}, "
                    f"re-sharpen {summary['resharpen_median']} f", loc="left", fontsize=10, color=ink)
    fig.savefig(path, dpi=90, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- compare
TABLE = [("frames", "frames"), ("n_cuts", "transitions (hard + smear)"), ("shot_len_median", "median shot len (f)"),
         ("still_pct", "still frames % (median flow < 0.5 px/f)"), ("longest_still_run", "longest still run (f)"),
         ("hold_gspeed_median", "hold camera speed median (px/f)"), ("hold_gspeed_p10", "hold camera speed p10 (px/f)"),
         ("hold_flow_median", "hold mean flow median (px/f)"),
         ("slow_pct", "% near-static hold frames (mean flow < 4 px/f)"),
         ("longest_slow_run", "longest near-static run (f)"),
         ("hold_zoom_median", "hold zoom rate median (%/f)"), ("hold_roll_median", "hold roll median (deg/f)"),
         ("jump_ratio_p95", "camera speed jump ratio p95 (outside cuts)"),
         ("jump_pct_over", "% frames camera speed jumps > x1.35"),
         ("flow_jump_p95", "picture speed (mean flow) jump ratio p95"), ("flow_jump_max", "picture speed jump max"),
         ("flow_jump_pct_over", "% frames picture speed jumps > x1.35"), ("dup_pct", "% duplicated frames"), ("smear_frames_median", "smear frames per cut (median)"),
         ("cuts_with_smear_pct", "% cuts with >= 2 smear frames"), ("hard_cuts_pct", "% hard cuts (0 smear)"),
         ("legible_median", "frames after cut until B is legible, sharp_rel >= 0.5 (median)"),
         ("resharpen_median", "frames after cut until B is sharp, sharp_rel >= 0.8 (median)"), ("resharpen_max", "re-sharpen max"),
         ("cut_peak_flow_median", "cut peak flow (px/f, median)"),
         ("accel_per_f_median", "acceleration into cut (x per frame, median)"),
         ("decel_per_f_median", "deceleration after cut (x per frame, median)"),
         ("step_in_median", "worst 1-frame speed step into a cut (median)"),
         ("step_out_median", "worst 1-frame speed drop out of a cut (median)"),
         ("step_out_p90", "worst 1-frame speed drop out of a cut (p90)"),
         ("speed_across_median", "speed after / before cut (median)"),
         ("speed_across_bad_pct", "% cuts with speed step outside x0.5-x2"),
         ("zoom_dir_counts", "zoom direction across cut"),
         ("zoom_reversed_pct", "% zoom cuts that reverse the zoom sign"), ("gfail_pct", "% frames fit failed")]


def compare(dirs: list[Path]) -> str:
    sums = [json.loads((d / "summary.json").read_text()) for d in dirs]
    lines = ["| metric | " + " | ".join(s["name"] for s in sums) + " |", "|---|" + "---|" * len(sums)]
    for key, label in TABLE:
        lines.append(f"| {label} | " + " | ".join(str(s.get(key)) for s in sums) + " |")
    return "\n".join(lines) + "\n"


# The v3 gate (films/timeless/amv3/REFS.md "Targets for v3"): (key, op, limit, label). Each limit sits inside the range
# of the three references (each passes all but ref a's upload dups) and v2 fails 12 of 16.
GATES = [("slow_pct", "<=", 5.0, "near-static hold frames %"),
         ("longest_slow_run", "<=", 4, "longest near-static run (f)"),
         ("hold_flow_median", ">=", 12.0, "hold picture speed median (px/f)"),
         ("hold_zoom_median", ">=", 1.5, "hold zoom rate median (%/f)"),
         ("flow_jump_max", "<=", 7.5, "picture-speed jump outside cuts, max"),
         ("flow_jump_p95", "<=", 2.1, "picture-speed jump outside cuts, p95"),
         ("step_out_median", "<=", 2.3, "worst 1-frame drop out of a cut, median"),
         ("step_out_p90", "<=", 4.0, "worst 1-frame drop out of a cut, p90"),
         ("step_in_median", "<=", 2.6, "worst 1-frame step into a cut, median"),
         ("accel_per_f_median", "range", (1.35, 1.7), "acceleration into the cut (x/f)"),
         ("decel_per_f_median", "range", (1.15, 1.27), "deceleration out of the cut (x/f)"),
         ("cut_peak_flow_median", ">=", 150.0, "cut peak picture speed median (px/f)"),
         ("zoom_reversed_pct", "<=", 20.0, "zoom cuts reversing the zoom sign %"),
         ("hard_cuts_pct", "<=", 20.0, "hard cuts (0 smear frames) %"),
         ("smear_frames_median", ">=", 3, "smear frames per cut, median"),
         ("dup_pct", "<=", 0.0, "duplicated frames % (ref a: upload artefact)")]


def gate(summary: dict) -> tuple[bool, str]:
    ok_all, lines = True, []
    for key, op, lim, label in GATES:
        v = summary.get(key)
        if v is None:
            ok, want = False, "n/a"
        elif op == "range":
            ok, want = lim[0] <= v <= lim[1], f"{lim[0]}-{lim[1]}"
        else:
            ok, want = (v <= lim) if op == "<=" else (v >= lim), f"{op} {lim}"
        ok_all &= ok
        lines.append(f"{'PASS' if ok else 'FAIL'}  {label:<45} {v!s:>8}   (target {want})")
    return ok_all, "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?", help="video file or folder of frames")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name")
    ap.add_argument("--width", type=int, default=480, help="analysis width for flow (sharpness uses >= 960)")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int)
    ap.add_argument("--reuse", action="store_true",
                    help="re-derive summary/plot from metrics.csv in --out (cut to --start/--end; writes metrics_<a>_<b>.csv)")
    ap.add_argument("--compare", nargs="+", help="output dirs of earlier runs -> markdown table at --out")
    ap.add_argument("--gate", action="store_true", help="check the summary against the v3 targets; exit 1 on a FAIL")
    a = ap.parse_args(argv)
    if a.compare:
        Path(a.out).write_text(compare([Path(d) for d in a.compare]))
        print(Path(a.out).read_text())
        return
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    src = Path(a.src) if a.src else None
    name = a.name or (src.stem if src else out.name)
    if a.reuse:
        rows = [r for r in read_csv(out / "metrics.csv")
                if r["frame"] >= a.start and (a.end is None or r["frame"] < a.end)]
    else:
        rows = measure(src, a.width, a.start, a.end)
    detect_cuts(rows)
    finish(rows)
    detect_events(rows)
    s = summarize(rows, name)
    write_csv(rows, out / ("metrics.csv" if not a.reuse else f"metrics_{a.start}_{a.end}.csv"))
    (out / "summary.json").write_text(json.dumps(s, indent=1))
    plot(rows, s, out / "plot.png")
    print(json.dumps({k: v for k, v in s.items() if k != "per_cut"}, indent=1))
    if a.gate:
        ok, text = gate(s)
        (out / "gate.txt").write_text(text + "\n")
        print(text)
        raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
