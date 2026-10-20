"""Test plates for the xfx-A harness until $AMV3_DATA/plates exists.

Writes <out>/plates/<shot>/f_NNNNN.jpg (NNNNN = comp frame) for [a - HANDLE, b + HANDLE) with a linear source-time map
(the real plates apply the speed ramps; close enough to test a transition). Needs ffmpeg on PATH or $FFMPEG.
usage: python3 testplates.py --edl films/timeless/amv3/edl.json --out <dir> --shots S08,S09 [--width 1920]
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import tempfile

ap = argparse.ArgumentParser()
ap.add_argument("--edl", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--shots", required=True)
ap.add_argument("--width", type=int, default=1920)
a = ap.parse_args()
E = json.load(open(a.edl))
ff = os.environ.get("FFMPEG", "ffmpeg")
H = E["handle"]
for sid in a.shots.split(","):
    s = next(x for x in E["shots"] if x["id"] == sid)
    dst = os.path.join(a.out, "plates", sid)
    if os.path.isdir(dst) and len(os.listdir(dst)) >= s["b"] - s["a"] + 2 * H:
        continue
    os.makedirs(dst, exist_ok=True)
    tmp = tempfile.mkdtemp()
    subprocess.run([ff, "-v", "error", "-i", s["file"], "-vf", f"scale={a.width}:-2", "-q:v", "3",
                    os.path.join(tmp, "s_%05d.jpg")], check=True)
    src = sorted(glob.glob(os.path.join(tmp, "s_*.jpg")))
    n = len(src)
    t0, t1 = s["src"]
    for f in range(s["a"] - H, s["b"] + H):
        t = t0 + (f - s["a"] + 0.5) / (s["b"] - s["a"]) * (t1 - t0)
        k = min(n - 1, max(0, int(round(t * 60))))
        shutil.copy(src[k], os.path.join(dst, f"f_{f:05d}.jpg"))
    shutil.rmtree(tmp)
    print(sid, s["clip"], n, "src frames ->", s["b"] - s["a"] + 2 * H)
