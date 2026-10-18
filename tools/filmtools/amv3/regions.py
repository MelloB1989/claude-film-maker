"""Timeless v3: exact eye-opening / mask-lens region masks for the nested zooms (SAM 2.1 video predictor on the plates).
pod_regions.sh runs `sam` on a RunPod 4090 and `post` + `sheets` + `verify` on the VM; everything also runs on CPU.

    python regions.py sam    --data DIR [--only S08,S17] [--device cuda|cpu] [--model large|base_plus|small|tiny]
                             [--frames A-B | N] [--out DIR]
    python regions.py post   --data DIR [--only ...] [--out DIR]
    python regions.py sheets --data DIR [--only ...] [--out DIR]
    python regions.py verify --data DIR [--only ...] [--out DIR]

DIR holds `plates/<id>/f_NNNNN.jpg` + `plate.json` (plates.py) and `tracks/<id>.json` (tracks.py). Writes, under --out
(default DIR/regions):
  <id>/<kind>/_raw/f_NNNNN.png  SAM 2 probability (8-bit, sigmoid of the mask logits) at plate resolution, one per
                                UNIQUE plate frame (held frames repeat a src240 frame and are not re-run).
  <id>/<kind>/f_NNNNN.png       the region: 8-bit grey alpha, 255 = inside, hard edge with ~1-2 px antialiasing (the
                                stage feathers it), every plate frame in the shot's range.
  <id>/<kind>/region.json       {"shot", "kind", "frames": {"<f>": {cx, cy, w, h, area, angle}}, ...}: alpha centroid
                                and the oriented bbox (cv2.minAreaRect of the region outline, angle in degrees), plate px.
  _sheets/<id>_<kind>.jpg       check sheet: 8 frames with the outline (full frame + zoomed crop around the region).

Method (`sam`): per shot, the plate frames of SPECS[id]["frames"] (deduplicated by src240), either the full plate or a
square crop of +-crop px that follows the track, upscaled to 1024 px (small eyes: the eyelid edge lands on SAM's grid
at 4-10x the plate resolution). Prompts on a few frames: positive clicks at the track point and offsets from it
(sclera / lens glass), negative clicks on the brow / lids / mask fabric, optionally a box. Propagated forward from the
first prompt frame and backward from the last; where both passes cover a frame their logits are averaged.
`post`: threshold 0.5, an optional small opening (SPECS "open", px: cuts thin bridges onto lashes), keep the component
under the track point (else the nearest), fill holes, then a motion-compensated temporal blend with the neighbouring unique frames (aligned on the region centroid) that is skipped whenever
the neighbour's aligned shape differs (IoU < 0.9 or area off by > 8 %): no lag on zooms or blinks. Antialias: a
0.7 px gaussian on the hard mask.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

W, H = 1920, 1080
SAM_PX = 1024
MODELS = {"large": "facebook/sam2.1-hiera-large", "base_plus": "facebook/sam2.1-hiera-base-plus",
          "small": "facebook/sam2.1-hiera-small", "tiny": "facebook/sam2.1-hiera-tiny"}

# Per shot: kind, plate frame range (inclusive), crop half size (None = full plate), prompt frames, and prompts as
# offsets from the track point at that frame (plate px): pos / neg clicks, box [x0, y0, x1, y1]. Picked on gridded
# zooms of the plates (probe sheets), see the notes.
SPECS = {
    "S08": dict(kind="eye", frames=(219, 267), crop=96, prompt=[219, 241, 262],
                pos=[[0, 0], [-31, 5], [37, 2]], neg=[[0, -33], [0, -40], [0, 40], [-62, 10], [66, 0]],
                box=[-47, -38, 57, 32], open=2,
                note="Tobey's screen-left eye; opening ~860-958 x 352-418, upper lid at y~367 above the iris"),
    "S25": dict(kind="eye", frames=(604, 672), crop=200, prompt=[604, 630, 656],
                pos=[[0, 0], [-80, -5], [42, 10]], neg=[[0, 70], [0, -85], [110, 25]],
                box=[-185, -62, 65, 48], open=3,
                note="Tom's screen-left eye (the shuriken passes it); upper lid in deep shadow"),
    "S31": dict(kind="eye", frames=(728, 775), crop=48, prompt=[744, 760, 775],
                pos=[[0, 0], [-10, 1], [13, 1]], neg=[[0, 13], [0, -15], [-26, 2], [30, 2]],
                box=[-19, -11, 23, 10], open=1,
                note="Tom on the train: his LEFT eye = screen right (the screen-left one is under his hair); "
                     "opening ~970-1008 x 275-291, 40 px wide"),
    "S01": dict(kind="lens", frames=(0, 66), crop=340, prompt=[0, 33, 65],
                pos=[[0, 0], [-60, -60], [120, 15]], neg=[[150, -150], [-160, 100], [20, 190], [260, 30]],
                note="Tobey's mask, screen-left lens: the grey glass inside the black frame"),
    "S05": dict(kind="lens", frames=(135, 191), crop=None, prompt=[135, 165, 190],
                pos=[[0, 0], [150, -100]], neg=[[-200, 200], [-250, -150]],
                note="black suit lens: the textured blue glass (track = its specular highlight); runs off frame"),
    "S16": dict(kind="lens", frames=(437, 484), crop=260, prompt=[437, 460, 483],
                pos=[[0, 0], [0, 100], [50, -100]], neg=[[-150, 0], [200, 0], [0, 200]],
                note="Andrew's blue lenses: the screen-right teardrop lens"),
    "S17": dict(kind="lens", frames=(452, 496), crop=None, prompt=[452, 479],
                pos=[[0, 0], [-250, 150], [250, 100]], neg=[[-200, -300], [0, -230]],
                note="Andrew A09: the whole blue lens (hex mesh + curved reflections) inside the black rim"),
    "S18": dict(kind="lens", frames=(464, 535), crop=150, prompt=[464, 500, 534],
                pos=[[0, 0], [40, -35], [-70, 25]], neg=[[0, 90], [-60, -60], [100, 20]],
                note="Tom M01: the cream lens glass (not its black frame)"),
    "S09": dict(kind="lens", frames=(236, 316), crop=None, prompt=[244, 262, 282],
                abs={244: dict(pos=[[1000, 600], [500, 250], [1300, 650]], neg=[[300, 800], [1700, 250], [1850, 100], [100, 900]]),
                     262: dict(pos=[[1000, 600], [700, 300], [1500, 700]], neg=[[300, 900], [1800, 160], [80, 1000]]),
                     282: dict(pos=[[1000, 500], [1600, 400], [800, 800]], neg=[[150, 950], [200, 1000]])},
                note="Andrew A01: everything inside the lens rim (mesh, then the city through it)"),
}
# shots without a tracks.py track: anchors (frame -> eye centre), linear in between, held outside
ANCHORS = {"S31": {728: [988, 283], 744: [988, 283], 760: [979, 284], 775: [977, 285]}}


def log(*a):
    print("[regions]", *a, flush=True)


def shot_ids(only):
    ids = list(SPECS)
    if only:
        keep = set(only.split(","))
        ids = [i for i in ids if i in keep]
    return ids


def plate_frames(data, sid, rng=None):
    meta = json.loads((data / "plates" / sid / "plate.json").read_text())
    a, b = rng or SPECS[sid]["frames"]
    fs = sorted(int(f) for f in meta["frames"] if a <= int(f) <= b)
    return meta, fs


def unique_frames(meta, fs):
    """{frame: representative frame}: frames that show the same src240 frame share the first one."""
    rep, first = {}, {}
    for f in fs:
        k = meta["frames"][str(f)].get("src240", f)
        first.setdefault(k, f)
        rep[f] = first[k]
    return rep


def track(data, sid, fs):
    """{frame: (x, y)} for every frame in fs."""
    if sid in ANCHORS:
        A = ANCHORS[sid]
        ks = sorted(A)
        return {f: (float(np.interp(f, ks, [A[k][0] for k in ks])), float(np.interp(f, ks, [A[k][1] for k in ks])))
                for f in fs}
    fr = json.loads((data / "tracks" / f"{sid}.json").read_text())["frames"]
    ks = sorted(int(k) for k in fr)
    return {f: (float(np.interp(f, ks, [fr[str(k)][0] for k in ks])), float(np.interp(f, ks, [fr[str(k)][1] for k in ks])))
            for f in fs}


def crop_box(pt, half):
    """Square window of side 2*half around pt, shifted to stay inside the plate."""
    side = 2 * half
    x0 = int(round(min(max(pt[0] - half, 0), W - side)))
    y0 = int(round(min(max(pt[1] - half, 0), H - side)))
    return x0, y0, side


def prompts_at(spec, f, pt):
    """(points, labels, box) in plate px for prompt frame f."""
    if "abs" in spec:
        p = spec["abs"][f]
        pos, neg, box = p["pos"], p["neg"], p.get("box")
    else:
        pos = [[pt[0] + dx, pt[1] + dy] for dx, dy in spec["pos"]]
        neg = [[pt[0] + dx, pt[1] + dy] for dx, dy in spec.get("neg", [])]
        b = spec.get("box")
        box = [pt[0] + b[0], pt[1] + b[1], pt[0] + b[2], pt[1] + b[3]] if b else None
    pts = np.array(pos + neg, np.float32)
    lab = np.array([1] * len(pos) + [0] * len(neg), np.int32)
    return pts, lab, (np.array(box, np.float32) if box is not None else None)


def outdir(a, data):
    return Path(a.out) if a.out else data / "regions"


# ------------------------------------------------------------------------------------------------------------- sam
def cmd_sam(a, data):
    import torch
    from sam2.sam2_video_predictor import SAM2VideoPredictor

    dev = a.device
    pred = SAM2VideoPredictor.from_pretrained(MODELS[a.model], device=dev)
    log("model", MODELS[a.model], "on", dev)
    out = outdir(a, data)
    for sid in shot_ids(a.only):
        spec = SPECS[sid]
        t0 = time.time()
        rng = None
        if a.frames.isdigit():                        # N frames around the first prompt frame (tests)
            n = int(a.frames)
            rng = (spec["prompt"][0] - n // 2, spec["prompt"][0] - n // 2 + n - 1)
        elif a.frames:
            rng = tuple(int(x) for x in a.frames.split("-"))
        meta, fs = plate_frames(data, sid, rng)
        rep = unique_frames(meta, fs)
        uf = sorted(set(rep.values()))
        tr = track(data, sid, fs)
        idx = {f: i for i, f in enumerate(uf)}
        tmp = Path(tempfile.mkdtemp(prefix=f"reg_{sid}_"))
        boxes = {}
        for f in uf:
            img = cv2.imread(str(data / "plates" / sid / f"f_{f:05d}.jpg"))
            if spec["crop"]:
                x0, y0, side = crop_box(tr[f], spec["crop"])
                c = cv2.resize(img[y0:y0 + side, x0:x0 + side], (SAM_PX, SAM_PX), interpolation=cv2.INTER_CUBIC)
                boxes[f] = (x0, y0, side)
            else:
                c = img
                boxes[f] = (0, 0, None)
            cv2.imwrite(str(tmp / f"{idx[f]:05d}.jpg"), c, [cv2.IMWRITE_JPEG_QUALITY, 97])

        def to_in(f, xy):
            x0, y0, side = boxes[f]
            if side is None:
                return xy
            k = SAM_PX / side
            xy = np.array(xy, np.float32).reshape(-1, 2).copy()
            xy[:, 0] = (xy[:, 0] - x0) * k
            xy[:, 1] = (xy[:, 1] - y0) * k
            return xy

        ac = torch.autocast("cuda", dtype=torch.bfloat16) if dev.startswith("cuda") else torch.autocast("cpu", enabled=False)
        with torch.inference_mode(), ac:
            st = pred.init_state(video_path=str(tmp))
            todo = {rep[p]: p for p in spec["prompt"] if p in rep}      # unique frame -> prompt frame (abs key)
            if not todo:                                  # --frames test window without a prompt frame: its middle
                mid = uf[len(uf) // 2]
                todo = {mid: min(spec["abs"], key=lambda k: abs(k - mid)) if "abs" in spec else mid}
            pfs = sorted(todo)
            for p in pfs:
                pts, lab, box = prompts_at(spec, todo[p], tr[p])
                kw = dict(inference_state=st, frame_idx=idx[p], obj_id=1, points=to_in(p, pts), labels=lab)
                if box is not None:
                    kw["box"] = to_in(p, box.reshape(2, 2)).reshape(4)
                pred.add_new_points_or_box(**kw)
            logits = {}
            for rev in (False, True):
                for fi, _ids, m in pred.propagate_in_video(st, reverse=rev):
                    lg = m[0, 0].float().cpu().numpy()
                    logits.setdefault(fi, []).append(lg)
            pred.reset_state(st)
        d = out / sid / spec["kind"] / "_raw"
        d.mkdir(parents=True, exist_ok=True)
        for f in uf:
            lg = np.mean(logits[idx[f]], axis=0)
            x0, y0, side = boxes[f]
            full = np.full((H, W), -30.0, np.float32)
            if side is None:
                full = cv2.resize(lg, (W, H), interpolation=cv2.INTER_LINEAR) if lg.shape != (H, W) else lg
            else:
                full[y0:y0 + side, x0:x0 + side] = cv2.resize(lg, (side, side), interpolation=cv2.INTER_AREA)
            prob = 1.0 / (1.0 + np.exp(-np.clip(full, -30, 30)))
            cv2.imwrite(str(d / f"f_{f:05d}.png"), np.round(prob * 255).astype(np.uint8))
        (d / "sam.json").write_text(json.dumps(dict(model=MODELS[a.model], frames=uf, rep={str(k): v for k, v in rep.items()},
                                                    prompt_frames=pfs, crop=spec["crop"], seconds=round(time.time() - t0, 1)), indent=1))
        shutil.rmtree(tmp, ignore_errors=True)
        log(f"{sid} {spec['kind']}: {len(uf)} unique of {len(fs)} frames, prompts {pfs}, {time.time() - t0:.1f} s")


# ------------------------------------------------------------------------------------------------------------ post
def fill_holes(m):
    inv = (m == 0).astype(np.uint8)
    n, lab = cv2.connectedComponents(inv, connectivity=4)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    holes = (inv > 0) & ~np.isin(lab, list(border))
    out = m.copy()
    out[holes] = 1
    return out


def keep_component(m, seed):
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    if n <= 1:
        return m.astype(np.uint8), False
    x, y = int(round(min(max(seed[0], 0), W - 1))), int(round(min(max(seed[1], 0), H - 1)))
    k = lab[y, x]
    hit = k != 0
    if not hit:                                   # nearest component (by its pixels) to the seed
        ys, xs = np.nonzero(lab)
        j = np.argmin((xs - x) ** 2 + (ys - y) ** 2)
        k = lab[ys[j], xs[j]]
    return (lab == k).astype(np.uint8), bool(hit)


def shift(img, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR, borderValue=0)


def centroid(m):
    mo = cv2.moments(m, binaryImage=False)
    if mo["m00"] <= 0:
        return None
    return mo["m10"] / mo["m00"], mo["m01"] / mo["m00"]


def geom(alpha):
    m = (alpha >= 128).astype(np.uint8)
    c = centroid(alpha.astype(np.float32) / 255.0)
    if c is None or m.sum() == 0:
        return None
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    (rx, ry), (rw, rh), ang = cv2.minAreaRect(max(cs, key=cv2.contourArea))
    return dict(cx=round(c[0], 2), cy=round(c[1], 2), w=round(rw, 2), h=round(rh, 2),
                area=int(m.sum()), angle=round(ang, 2))


def cmd_post(a, data):
    out = outdir(a, data)
    for sid in shot_ids(a.only):
        spec = SPECS[sid]
        d = out / sid / spec["kind"]
        raw = d / "_raw"
        if not (raw / "sam.json").exists():
            log(f"{sid}: no SAM output in {raw}, skipped")
            continue
        sj = json.loads((raw / "sam.json").read_text())
        uf = sj["frames"]
        rep = {int(k): v for k, v in sj["rep"].items()}
        tr = track(data, sid, sorted(rep))
        masks, probs, misses = {}, {}, []
        for f in uf:
            p = cv2.imread(str(raw / f"f_{f:05d}.png"), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
            hard = (p >= 0.5).astype(np.uint8)
            r = spec.get("open", 0)                   # morphological opening: cuts thin bridges onto lashes / lids
            if r:
                hard = cv2.morphologyEx(hard, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
            m, hit = keep_component(hard, tr[f])
            if not hit:
                misses.append(f)
            m = fill_holes(m)
            masks[f] = m
            probs[f] = m.astype(np.float32)
        # motion-compensated temporal blend over unique frames, skipped where the shape changes
        sm, blended = {}, 0
        for i, f in enumerate(uf):
            c0 = centroid(masks[f])
            acc, wsum = probs[f] * 0.5, 0.5
            for j in (i - 1, i + 1):
                if j < 0 or j >= len(uf) or c0 is None:
                    continue
                g = uf[j]
                c1 = centroid(masks[g])
                if c1 is None:
                    continue
                sh = shift(probs[g], c0[0] - c1[0], c0[1] - c1[1])
                a0, a1 = masks[f].sum(), (sh >= 0.5).sum()
                inter = ((sh >= 0.5) & (masks[f] > 0)).sum()
                iou = inter / max(1, a0 + a1 - inter)
                if iou >= 0.9 and abs(a1 - a0) <= 0.08 * max(a0, 1):
                    acc += 0.25 * sh
                    wsum += 0.25
                    blended += 1
            sm[f] = acc / wsum
        frames = {}
        for f in sorted(rep):
            hard = (sm[rep[f]] >= 0.5).astype(np.float32)
            alpha = np.clip(cv2.GaussianBlur(hard, (0, 0), 0.7) * 255.0 + 0.5, 0, 255).astype(np.uint8)
            cv2.imwrite(str(d / f"f_{f:05d}.png"), alpha)
            frames[str(f)] = geom(alpha)
        empty = [f for f, g in frames.items() if g is None]
        (d / "region.json").write_text(json.dumps(dict(
            shot=sid, kind=spec["kind"], note=spec.get("note", ""), plate_px=[W, H], model=sj["model"],
            crop=sj["crop"], prompt_frames=sj["prompt_frames"], track_misses=misses, empty=empty,
            frames=frames), indent=1))
        log(f"{sid} {spec['kind']}: {len(frames)} frames, blended {blended} neighbour pairs, "
            f"track point outside the region on {len(misses)} unique frames {misses[:8]}, empty {empty[:8]}")


# ---------------------------------------------------------------------------------------------------------- sheets
def outline(img, alpha, col, t=1):
    cs, _ = cv2.findContours((alpha >= 128).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(img, cs, -1, col, t, cv2.LINE_AA)


def cmd_sheets(a, data):
    out = outdir(a, data)
    (out / "_sheets").mkdir(parents=True, exist_ok=True)
    for sid in shot_ids(a.only):
        spec = SPECS[sid]
        d = out / sid / spec["kind"]
        if not (d / "region.json").exists():
            continue
        R = json.loads((d / "region.json").read_text())
        fs = sorted(int(f) for f in R["frames"])
        tr = track(data, sid, fs)
        pick = [fs[int(round(i * (len(fs) - 1) / 7))] for i in range(8)]
        top, bot = [], []
        for f in pick:
            img = cv2.imread(str(data / "plates" / sid / f"f_{f:05d}.jpg"))
            al = cv2.imread(str(d / f"f_{f:05d}.png"), cv2.IMREAD_GRAYSCALE)
            g = R["frames"][str(f)]
            full = img.copy()
            outline(full, al, (0, 255, 0), 4)
            cv2.drawMarker(full, (int(tr[f][0]), int(tr[f][1])), (0, 0, 255), cv2.MARKER_CROSS, 40, 4)
            full = cv2.resize(full, (480, 270), interpolation=cv2.INTER_AREA)
            cv2.putText(full, f"f{f}", (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(full, f"f{f}", (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
            top.append(full)
            if g is None:
                bot.append(np.zeros((480, 480, 3), np.uint8))
                continue
            ys, xs = np.nonzero(al >= 128)
            cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
            half = int(max(xs.max() - xs.min(), ys.max() - ys.min()) * 0.75) + 8
            pad = cv2.copyMakeBorder(img, half, half, half, half, cv2.BORDER_CONSTANT)
            pa = cv2.copyMakeBorder(al, half, half, half, half, cv2.BORDER_CONSTANT)
            x0, y0 = int(cx), int(cy)                     # in padded coords the window is [x0, x0 + 2 half)
            z = cv2.resize(pad[y0:y0 + 2 * half, x0:x0 + 2 * half], (480, 480), interpolation=cv2.INTER_CUBIC)
            za = cv2.resize(pa[y0:y0 + 2 * half, x0:x0 + 2 * half], (480, 480), interpolation=cv2.INTER_LINEAR)
            outline(z, za, (0, 255, 0), 1)
            cv2.putText(z, f"x{480 / (2 * half):.1f} area {g['area']}", (6, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (255, 255, 255), 1, cv2.LINE_AA)
            bot.append(z)
        top = np.hstack(top)
        bot = np.hstack([cv2.resize(b, (480, 480)) for b in bot])
        head = np.zeros((34, top.shape[1], 3), np.uint8)
        cv2.putText(head, f"{sid} {spec['kind']}  {fs[0]}..{fs[-1]}  {spec.get('note', '')}", (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
        sheet = np.vstack([head, top, bot])
        p = out / "_sheets" / f"{sid}_{spec['kind']}.jpg"
        cv2.imwrite(str(p), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if a.sheets_copy:
            Path(a.sheets_copy).mkdir(parents=True, exist_ok=True)
            shutil.copy(p, Path(a.sheets_copy) / p.name)
        log("sheet", p)


# ---------------------------------------------------------------------------------------------------------- verify
def cmd_verify(a, data):
    out = outdir(a, data)
    bad = []
    for sid in shot_ids(a.only):
        spec = SPECS[sid]
        d = out / sid / spec["kind"]
        meta, fs = plate_frames(data, sid)
        have = [f for f in fs if (d / f"f_{f:05d}.png").exists()]
        rj = d / "region.json"
        R = json.loads(rj.read_text()) if rj.exists() else {"frames": {}}
        empty = [f for f in fs if R["frames"].get(str(f)) is None]
        jumps = []
        prev = None
        for f in fs:
            g = R["frames"].get(str(f))
            if g and prev:
                if abs(g["area"] - prev["area"]) > 0.35 * max(prev["area"], 1):
                    jumps.append(f)
            prev = g or prev
        ok = len(have) == len(fs) and not empty
        log(f"{sid} {spec['kind']}: {len(have)}/{len(fs)} frames, empty {len(empty)}, area jumps > 35 % at {jumps[:10]}"
            + ("" if ok else "  INCOMPLETE"))
        if not ok:
            bad.append(sid)
    if bad:
        log("incomplete:", ",".join(bad))
        sys.exit(1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("sam", "post", "sheets", "verify"):
        p = sub.add_parser(n)
        p.add_argument("--data", default=os.environ.get("AMV3_DATA", "/home/nikhil/code/film-making/work/timeless_v3"))
        p.add_argument("--only", default="")
        p.add_argument("--out", default="", help="default DATA/regions")
        p.add_argument("--sheets-copy", default="")
    sub.choices["sam"].add_argument("--device", default="cuda")
    sub.choices["sam"].add_argument("--model", choices=tuple(MODELS), default="large")
    sub.choices["sam"].add_argument("--frames", default="", help="A-B: only these plate frames, or N: N frames around the first prompt frame (tests)")
    a = ap.parse_args(argv)
    data = Path(a.data)
    {"sam": cmd_sam, "post": cmd_post, "sheets": cmd_sheets, "verify": cmd_verify}[a.cmd](a, data)


if __name__ == "__main__":
    main()
