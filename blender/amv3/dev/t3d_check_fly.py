"""Print the text_fly camera plan per frame (no Blender): zoom/pan/roll/pitch rates and card coverage.
python3 blender/amv3/dev/t3d_check_fly.py   (from the repo root)"""
import json, math, os, sys, types
sys.modules.setdefault("mathutils", types.SimpleNamespace(Quaternion=None))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from xfx import text_fly as tf  # noqa: E402
E = json.load(open(os.path.join(HERE, "../../../films/timeless/amv3/edl.json")))
S = {s["id"]: s for s in E["shots"]}
VF = math.radians(16.15)
for c in [c for c in E["cuts"] if c["type"] == "text_fly"]:
    T = dict(c, a=S[c["a"]], b=S[c["b"]])
    pl = tf.plan(T, None)
    print(c["id"], "peak x%.2f land x%.2f" % (pl["s_peak"], pl["s_land"]))
    for f in range(c["w0"], c["w1"] + 1):
        side, st, ph = tf.state_at(pl, f - 1e-4 if f == c["w1"] else f)
        sx, sy = tf.safe_c(st.s, st.cx, st.cy, st.r, 1.0)
        # pitch moves the view centre on the card by D tan(ph) (approx., small keystone ignored)
        dy = (1866.7 / st.s) * math.tan(math.radians(ph))
        top_ok = st.cy - dy - 540.0 / st.s >= -1 and st.cy - dy + 540.0 / st.s <= 1081
        ok = abs(sx - st.cx) < 1 and abs(sy - st.cy) < 1 and top_ok
        print("%d %s s %.2f ds %+.3f c %4.0f,%4.0f r %+5.1f dr %+.2f pitch %+5.1f pan %3.0f px/f %s" % (
            f, side, st.s, st.ds, st.cx, st.cy, st.r, st.dr, ph, math.hypot(st.dcx, st.dcy) * st.s,
            "" if ok else "EDGE"))
