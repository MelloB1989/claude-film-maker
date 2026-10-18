"""Test data dir for text3d until the v3 mattes land: <out>/{plates,tracks,depth} -> $AMV3_DATA, and
mattes/<shot>/f_NNNNN.png -> the v2 BiRefNet mattes ($AMV2_DATA/mattes/<clip>/<src240 index>.png) via plate.json.
python dev/t3d_testdata.py <out> S10 S25 S32"""
import json
import os
import sys

A3 = os.environ.get("AMV3_DATA", "/home/nikhil/code/film-making/work/timeless_v3")
A2 = os.environ.get("AMV2_DATA", "/home/nikhil/code/film-making/work/timeless_v2")
out = os.path.abspath(sys.argv[1])
os.makedirs(out, exist_ok=True)
for d in ("plates", "tracks", "depth"):
    src, dst = os.path.join(A3, d), os.path.join(out, d)
    if os.path.exists(src) and not os.path.lexists(dst):
        os.symlink(src, dst)
for sid in sys.argv[2:]:
    real = os.path.join(A3, "mattes", sid)
    dst = os.path.join(out, "mattes", sid)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.lexists(dst):
        continue
    if os.path.isdir(real):
        os.symlink(real, dst)
        print(sid, "real v3 mattes")
        continue
    pj = json.load(open(os.path.join(A3, "plates", sid, "plate.json")))
    mdir = os.path.join(A2, "mattes", pj["clip"])
    if not os.path.isdir(mdir):
        print(sid, "no v2 mattes for", pj["clip"])
        continue
    os.makedirs(dst)
    n = 0
    for f, fr in pj["frames"].items():
        p = os.path.join(mdir, "%05d.png" % int(fr["src240"]))
        if os.path.exists(p):
            os.symlink(p, os.path.join(dst, "f_%05d.png" % int(f)))
            n += 1
    print(sid, n, "v2 matte frames from", mdir)
