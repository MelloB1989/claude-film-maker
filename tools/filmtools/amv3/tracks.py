"""Timeless v3: eye/lens tracks on the plates (runs on the render VM: numpy + opencv, python 3.10).

    python tools/filmtools/amv3/tracks.py [--data $AMV3_DATA] [--only S08,S17] [--probe] [--sheets-copy out/tracks_sheets]

For every shot with a `focus` in edl.json (the CUTS points iris / exit_lens / lens_a / lens_b are the same points on the
same shots) writes `<data>/tracks/<id>.json` = {"point", "anchors", "frames": {"<f>": [x, y]}} in plate pixels for every
plate frame, and a check sheet `<data>/tracks/_sheets/<id>.jpg` (crosshair on 8 frames, full frame + 3x zoom).

Method: hand-checked ANCHORS (frame -> pixel, picked by eye on --probe sheets: gridded zooms of the plates) and dense
optical flow (DIS) between consecutive plate frames. Between two anchors the point is propagated forward from the left
one and backward from the right one and the two paths are cross-faded (drift cancels at both anchors); outside the
first/last anchor it is propagated one way. Each step moves the point by the median flow in a small window around it,
then refines it by template matching against the previous frame's patch (scaled by the local flow divergence, so the
big zooms of S09/S17 stay locked). Frames that repeat a source frame (holds) repeat the point.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

# Hand-checked anchors per shot: {comp frame: [x, y]} in plate pixels. Seeds from edl.json are replaced by the values
# read off the --probe sheets (gridded zooms); every value here was checked by eye.
ANCHORS = {
    "S01": {0: [975, 445]},                                   # centre of the dark lens (screen left); EDL 960,470
    "S03": {83: [920, 560]},                                  # on the glove's second finger (EDL seed was background)
    "S05": {151: [1023, 512]},                                # the lens's specular highlight (chained blob)
    "S08": {235: [906, 390], 241: [903, 390], 251: [903, 391]},   # iris centre
    "S09": {252: [1036, 546]},                                # lens mesh: the pull-out's zoom centre
    "S10": {321: [860, 440]},                                 # screen-left lens (EDL 915,600 is below it)
    "S16": {460: [1010, 290]},                                # screen-right lens (EDL 990,565 is on the mask fabric)
    "S17": {479: [1110, 443]},                                # point on the lens glass next to the reflected figure
    "S18": {480: [1115, 445]},                                # lens centre (bright blob centroid every frame)
    "S25": {620: [507, 375], 641: [530, 375], 655: [547, 375]},   # Tom's screen-left eye (EDL 700,470 is the cheek)
}
# per-frame refinement: (luma threshold, ROI half size) -> centroid of the bright component under the point
BLOB = {"S18": (150, 220)}
# chained highlight tracking (the lens is blurry glass: flow drifts): each frame's centroid seeds the next
BLOB_SEQ = {"S05": (190, 30)}
POINTS = {
    "S01": "Tobey mask: right eye lens (screen left)",
    "S03": "Tobey: left eye (screen right)",
    "S05": "black suit: specular highlight on the lens",
    "S08": "Tobey: left iris (screen right) centre",
    "S09": "Andrew: lens (exit lens of the eye tunnel)",
    "S10": "Andrew mask: lens",
    "S16": "Andrew: blue lens centre",
    "S17": "Andrew A09: lens centre (push-in target)",
    "S18": "Tom M01: lens centre (pull-out origin)",
    "S25": "Tom: eye the shuriken passes",
}


def load_plates(data, sid):
    d = data / "plates" / sid
    meta = json.loads((d / "plate.json").read_text())
    fs = sorted(int(f) for f in meta["frames"])
    return d, meta, fs


def read(d, f):
    return cv2.imread(str(d / f"f_{f:05d}.jpg"))


# ------------------------------------------------------------------ probe sheets (for picking anchors by eye)
def grid_crop(img, cx, cy, half, zoom, step):
    """A crop of +-half px around (cx, cy), zoomed, with a labelled grid every `step` plate px."""
    h, w = img.shape[:2]
    x0, y0 = int(cx - half), int(cy - half)
    pad = cv2.copyMakeBorder(img, half, half, half, half, cv2.BORDER_CONSTANT, value=(40, 40, 40))
    c = pad[y0 + half:y0 + 3 * half, x0 + half:x0 + 3 * half]
    c = cv2.resize(c, (2 * half * zoom, 2 * half * zoom), interpolation=cv2.INTER_CUBIC)
    for g in range((x0 // step) * step, x0 + 2 * half + 1, step):
        if g < x0:
            continue
        X = (g - x0) * zoom
        cv2.line(c, (X, 0), (X, c.shape[0]), (0, 255, 255) if g % (5 * step) == 0 else (0, 160, 160), 1)
        if g % (2 * step) == 0:
            cv2.putText(c, str(g), (X + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA)
    for g in range((y0 // step) * step, y0 + 2 * half + 1, step):
        if g < y0:
            continue
        Y = (g - y0) * zoom
        cv2.line(c, (0, Y), (c.shape[1], Y), (0, 255, 255) if g % (5 * step) == 0 else (0, 160, 160), 1)
        if g % (2 * step) == 0:
            cv2.putText(c, str(g), (2, Y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA)
    return c


def cross(img, x, y, col=(0, 0, 255), r=14, t=1):
    x, y = int(round(x)), int(round(y))
    cv2.line(img, (x - r, y), (x - 4, y), col, t, cv2.LINE_AA)
    cv2.line(img, (x + 4, y), (x + r, y), col, t, cv2.LINE_AA)
    cv2.line(img, (x, y - r), (x, y - 4), col, t, cv2.LINE_AA)
    cv2.line(img, (x, y + 4), (x, y + r), col, t, cv2.LINE_AA)


def label(img, text, x=4, y=18, s=0.55):
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, s, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, s, (255, 255, 255), 1, cv2.LINE_AA)


def probe(data, sid, seed, frames, out, half=60, zoom=4, step=10, cols=3):
    """Zoomed crops (+-half px, x zoom, labelled grid every `step` px) around the seed, a small full-frame inset."""
    d, meta, fs = load_plates(data, sid)
    tiles = []
    for f in frames:
        img = read(d, f)
        pt = seed.get(f) if isinstance(seed, dict) else seed
        z = grid_crop(img, pt[0], pt[1], half, zoom, step)
        full = img.copy()
        cross(full, *pt, r=60, t=6)
        full = cv2.resize(full, (192, 108), interpolation=cv2.INTER_AREA)
        z[z.shape[0] - 108:, z.shape[1] - 192:] = full
        label(z, f"{sid} f{f} s{meta['frames'][str(f)]['src240']} seed {pt}", x=4, y=z.shape[0] - 8, s=0.5)
        tiles.append(z)
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(str(out), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])


# ------------------------------------------------------------------ tracking
class Flow:
    def __init__(self):
        self.dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self.cache = {}

    def __call__(self, A, B, key):
        if key not in self.cache:
            ga = cv2.cvtColor(A, cv2.COLOR_BGR2GRAY)
            gb = cv2.cvtColor(B, cv2.COLOR_BGR2GRAY)
            self.cache[key] = self.dis.calc(ga, gb, None)
        return self.cache[key]


def step_point(fl, A, B, p, win=12):
    """Move p from frame A to frame B: median flow in a window, scale from the flow's local divergence, then a
    template-match refinement of A's patch (resized by that scale) inside a small search box in B."""
    h, w = fl.shape[:2]
    x, y = p
    x0, x1 = int(max(0, x - win)), int(min(w, x + win + 1))
    y0, y1 = int(max(0, y - win)), int(min(h, y + win + 1))
    v = fl[y0:y1, x0:x1].reshape(-1, 2)
    dx, dy = np.median(v[:, 0]), np.median(v[:, 1])
    # local scale: flow at +-R around p
    R = 40
    def at(px, py):
        px, py = int(np.clip(px, 0, w - 1)), int(np.clip(py, 0, h - 1))
        return fl[py, px]
    sx = 1 + (at(x + R, y)[0] - at(x - R, y)[0]) / (2 * R)
    sy = 1 + (at(x, y + R)[1] - at(x, y - R)[1]) / (2 * R)
    s = float(np.clip(0.5 * (sx + sy), 0.8, 1.25))
    q = np.array([x + dx, y + dy])
    # template refinement
    T = 24
    if T < x < w - T and T < y < h - T:
        patch = A[int(y) - T:int(y) + T, int(x) - T:int(x) + T]
        ps = max(8, int(round(2 * T * s)))
        patch = cv2.resize(patch, (ps, ps), interpolation=cv2.INTER_LINEAR)
        S = ps // 2 + 10
        qx, qy = int(round(q[0])), int(round(q[1]))
        if S < qx < w - S and S < qy < h - S:
            reg = B[qy - S:qy + S, qx - S:qx + S]
            r = cv2.matchTemplate(reg, patch, cv2.TM_CCOEFF_NORMED)
            _, mv, _, ml = cv2.minMaxLoc(r)
            if mv > 0.6:
                # sub-pixel peak
                mx, my = ml
                def sub(a, b, c):
                    den = a - 2 * b + c
                    return 0.0 if abs(den) < 1e-6 else 0.5 * (a - c) / den
                ox = sub(r[my, mx - 1], r[my, mx], r[my, mx + 1]) if 0 < mx < r.shape[1] - 1 else 0
                oy = sub(r[my - 1, mx], r[my, mx], r[my + 1, mx]) if 0 < my < r.shape[0] - 1 else 0
                cand = np.array([qx - S + mx + ox + ps / 2, qy - S + my + oy + ps / 2])
                if np.hypot(*(cand - q)) < 6:
                    q = 0.5 * q + 0.5 * cand
    return [float(q[0]), float(q[1])]


def propagate(frames, imgs, src, flow, start, p0, direction):
    """{f: point} from frame `start` with point p0, moving through `frames` (sorted) in `direction` (+1/-1)."""
    i = frames.index(start)
    out = {start: list(p0)}
    p = list(p0)
    rng = range(i + 1, len(frames)) if direction > 0 else range(i - 1, -1, -1)
    prev = start
    for k in rng:
        f = frames[k]
        if src[f] != src[prev]:
            A, B = imgs[prev], imgs[f]
            fl = flow(A, B, (src[prev], src[f]))
            p = step_point(fl, A, B, p)
        out[f] = list(p)
        prev = f
    return out


def blob_centroid(img, p, thr, R):
    """Centroid of the connected bright region (luma > thr) nearest to p inside a +-R box, or None."""
    h, w = img.shape[:2]
    x0, y0 = int(max(0, p[0] - R)), int(max(0, p[1] - R))
    x1, y1 = int(min(w, p[0] + R)), int(min(h, p[1] + R))
    g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    m = (cv2.GaussianBlur(g, (5, 5), 0) > thr).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return None
    px, py = p[0] - x0, p[1] - y0
    best = min(range(1, n), key=lambda i: (lab[int(np.clip(py, 0, lab.shape[0] - 1)), int(np.clip(px, 0, lab.shape[1] - 1))] != i,
                                          np.hypot(cen[i][0] - px, cen[i][1] - py) - 0.01 * st[i][4]))
    if st[best][4] < 20:
        return None
    return [float(cen[best][0] + x0), float(cen[best][1] + y0)]


def track(data, sid, anchors):
    d, meta, fs = load_plates(data, sid)
    src = {f: meta["frames"][str(f)]["src240"] for f in fs}
    imgs = {f: read(d, f) for f in fs}
    flow = Flow()
    ak = sorted(anchors)
    res = {}
    # before the first anchor / after the last: one-way
    res.update(propagate(fs, imgs, src, flow, ak[0], anchors[ak[0]], -1))
    res.update(propagate(fs, imgs, src, flow, ak[-1], anchors[ak[-1]], +1))
    for a, b in zip(ak, ak[1:]):
        fw = propagate(fs, imgs, src, flow, a, anchors[a], +1)
        bw = propagate(fs, imgs, src, flow, b, anchors[b], -1)
        for f in fs:
            if a <= f <= b:
                t = (f - a) / (b - a)
                t = t * t * (3 - 2 * t)
                res[f] = [(1 - t) * fw[f][0] + t * bw[f][0], (1 - t) * fw[f][1] + t * bw[f][1]]
    if sid in BLOB:
        thr, R = BLOB[sid]
        for f in fs:
            c = blob_centroid(imgs[f], res[f], thr, R)
            if c is not None:
                res[f] = c
    if sid in BLOB_SEQ:
        thr, R = BLOB_SEQ[sid]
        a0 = ak[0]
        for direction in (+1, -1):
            p = list(anchors[a0])
            order = [f for f in fs if f >= a0] if direction > 0 else [f for f in reversed(fs) if f <= a0]
            for f in order:
                c = blob_centroid(imgs[f], p, thr, R)
                if c is not None and np.hypot(c[0] - p[0], c[1] - p[1]) < R:
                    p = c
                res[f] = list(p)
    # holds repeat exactly
    for f in fs:
        for g in fs:
            if g < f and src[g] == src[f]:
                res[f] = res[g]
                break
    return {f: [round(res[f][0], 2), round(res[f][1], 2)] for f in fs}, imgs, meta


def check_sheet(sid, pts, imgs, meta, anchors, out, n=8):
    fs = sorted(pts)
    a, b = meta["a"], meta["b"]
    inside = [f for f in fs if a <= f < b]
    pick = sorted(set([inside[round(i * (len(inside) - 1) / (n - 3))] for i in range(n - 2)] + [fs[0], fs[-1]]))
    tiles = []
    for f in pick:
        img = imgs[f].copy()
        x, y = pts[f]
        full = img.copy()
        cross(full, x, y, r=50, t=4)
        full = cv2.resize(full, (480, 270), interpolation=cv2.INTER_AREA)
        label(full, f"{sid} f{f} ({x:.0f},{y:.0f})" + ("  ANCHOR" if f in anchors else ""), s=0.5)
        z = grid_crop(img, x, y, 45, 3, 10)
        cross(z, z.shape[1] / 2, z.shape[0] / 2, col=(0, 0, 255), r=30, t=1)
        z = cv2.resize(z, (270, 270), interpolation=cv2.INTER_CUBIC)
        tiles.append(np.hstack([full, z]))
    rows = [np.hstack(tiles[i:i + 2]) if i + 1 < len(tiles) else np.hstack([tiles[i], np.zeros_like(tiles[i])])
            for i in range(0, len(tiles), 2)]
    cv2.imwrite(str(out), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--edl", default=str(ROOT / "films/timeless/amv3/edl.json"))
    ap.add_argument("--data", default=os.environ.get("AMV3_DATA", "/home/nikhil/code/film-making/work/timeless_v3"))
    ap.add_argument("--only", default="")
    ap.add_argument("--probe", default="", help="frames to probe per shot: 'auto' or 'S08:235,240;S17:470,479'")
    ap.add_argument("--sheets-copy", default="")
    ap.add_argument("--probe-zoom", default="60,4,10", help="half,zoom,step of the probe crops")
    ap.add_argument("--probe-tag", default="")
    a = ap.parse_args(argv)
    E = json.loads(Path(a.edl).read_text())
    data = Path(a.data)
    shots = [s for s in E["shots"] if s.get("focus")]
    if a.only:
        shots = [s for s in shots if s["id"] in a.only.split(",")]
    copy = Path(a.sheets_copy) if a.sheets_copy else None
    if copy:
        copy.mkdir(parents=True, exist_ok=True)
    if a.probe:
        sd = data / "tracks" / "_probe"
        sd.mkdir(parents=True, exist_ok=True)
        req = {}
        if a.probe != "auto":
            for part in a.probe.split(";"):
                k, v = part.split(":")
                req[k] = [int(x) for x in v.split(",")]
        for s in shots:
            _, meta, fs = load_plates(data, s["id"])
            fr = req.get(s["id"]) or sorted(set([s["a"] + round(i * (s["b"] - 1 - s["a"]) / 5) for i in range(6)]))
            seed = ANCHORS.get(s["id"]) or s["focus"]
            if isinstance(seed, dict):
                ks = sorted(seed)
                seed = {f: seed[min(ks, key=lambda k: abs(k - f))] for f in fr}
            half, zoom, step = (int(x) for x in a.probe_zoom.split(","))
            name = f"{s['id']}{a.probe_tag}.jpg"
            probe(data, s["id"], seed, fr, sd / name, half=half, zoom=zoom, step=step)
            if copy:
                shutil.copy(sd / name, copy / f"probe_{name}")
            print(f"[tracks] probe {s['id']} frames {fr}", flush=True)
        return
    td = data / "tracks"
    (td / "_sheets").mkdir(parents=True, exist_ok=True)
    for s in shots:
        anchors = {int(k): v for k, v in (ANCHORS.get(s["id"]) or {s["a"]: s["focus"]}).items()}
        pts, imgs, meta = track(data, s["id"], anchors)
        (td / f"{s['id']}.json").write_text(json.dumps(dict(
            id=s["id"], clip=s["clip"], point=POINTS.get(s["id"], "focus"), anchors={str(k): v for k, v in anchors.items()},
            frames={str(f): p for f, p in pts.items()}), indent=0))
        check_sheet(s["id"], pts, imgs, meta, anchors, td / "_sheets" / f"{s['id']}.jpg")
        if copy:
            shutil.copy(td / "_sheets" / f"{s['id']}.jpg", copy / f"{s['id']}.jpg")
        print(f"[tracks] {s['id']}: {len(pts)} frames, anchors {sorted(anchors)}", flush=True)


if __name__ == "__main__":
    main()
