"""xfx-B harness: extract stand-in plates (comp-frame JPGs) for the xfx-B windows until $AMV3_DATA/plates exists.

python blender/amv3/xfx/_harness/testplates.py --out out/tp  (runs on the render VM: needs cv2 and $AMV2_DATA/src240)
Constant-speed mapping of the shot's src range over [a, b), extended linearly into the handles, clamped to the clip.
"""
import argparse
import json
import os
import shutil

import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
EDL = os.path.join(ROOT, "../../../../films/timeless/amv3/edl.json")
NEED = {"S14": (428, 447), "S15": (428, 447), "S17": (464, 496), "S18": (476, 520), "S20": (544, 566),
        "S21": (548, 566), "S32": (756, 790)}


def extract(name, path240, path60, src0, src1, a, b, f0, f1, out, scale):
    if os.path.exists(path240):
        cap, fps = cv2.VideoCapture(path240), 240.0
    else:
        cap, fps = cv2.VideoCapture(path60), 60.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    ok = True
    while ok:
        ok, im = cap.read()
        if ok:
            frames.append(im)
    n = len(frames)
    d = os.path.join(out, name)
    os.makedirs(d, exist_ok=True)
    for f in range(f0, f1):
        t = src0 + (f + 0.5 - a) / (b - a) * (src1 - src0)
        k = min(max(int(round(t * fps)), 0), n - 1)
        im = frames[k]
        if scale != 1.0:
            im = cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        cv2.imwrite(os.path.join(d, "f_%05d.jpg" % f), im, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(name, f0, f1, "src frames", n, "fps", fps, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()
    E = json.load(open(EDL))
    v2 = os.environ.get("AMV2_DATA", "/home/nikhil/code/film-making/work/timeless_v2")
    v3 = os.environ.get("AMV3_DATA", "/home/nikhil/code/film-making/work/timeless_v3")
    for k in ("plates", "mattes", "depth", "tracks"):
        p = os.path.join(v3, k)
        print("AMV3", k, sorted(os.listdir(p))[:40] if os.path.isdir(p) else "missing", flush=True)
    print("src240", sorted(os.listdir(os.path.join(v2, "src240")))[:60] if os.path.isdir(os.path.join(v2, "src240")) else "missing")
    for s in E["shots"]:
        if s["id"] in NEED:
            f0, f1 = NEED[s["id"]]
            extract(s["id"], os.path.join(v2, "src240", "clip_%s.mp4" % s["clip"]), s["file"], s["src"][0], s["src"][1],
                    s["a"], s["b"], f0, f1, a.out, a.scale)
    for p in E["triptych"]["panels"]:
        extract(p["id"], os.path.join(v2, "src240", "clip_%s.mp4" % p["clip"]), p["file"], p["src"][0], p["src"][1],
                p["f"], 836, p["f"] - 4, 836, a.out, a.scale)
    od = os.path.join(v2, "blender", "outro")
    os.makedirs(os.path.join(a.out, "outro"), exist_ok=True)
    if os.path.isdir(od):
        for f in range(819, 840):
            src = os.path.join(od, "%04d.png" % f)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(a.out, "outro", "%04d.png" % f))
    print("outro", sorted(os.listdir(os.path.join(a.out, "outro")))[:3])
    tr = os.path.join(v3, "tracks")
    if os.path.isdir(tr):
        shutil.copytree(tr, os.path.join(a.out, "tracks"), dirs_exist_ok=True)


if __name__ == "__main__":
    main()
