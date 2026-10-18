"""Write a test EDL with some cuts switched to the `layer` module (edl.json itself is the operator's to change).

  python blender/amv3/tests/layer_edl.py out.json C02:keep C06:keep C31:keep C09:sweep C30:sweep:from=R,depth=0.4,pre=8 (pre/post move the window)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(HERE, "..", "..", "..", "films", "timeless", "amv3", "edl.json")
E = json.load(open(src))
out = sys.argv[1]
for spec in sys.argv[2:]:
    cid, mode, *rest = spec.split(":")
    p = dict(mode=mode)
    for kv in (rest[0].split(",") if rest else []):
        k, v = kv.split("=")
        try:
            v = float(v)
        except ValueError:
            pass
        p[k] = v
    c = next(c for c in E["cuts"] if c["id"] == cid)
    if "pre" in p:
        c["w0"] = c["f"] - int(p.pop("pre"))
    if "post" in p:
        c["w1"] = c["f"] + int(p.pop("post"))
    c["type"], c["p"] = "layer", p
json.dump(E, open(out, "w"), indent=1)
print(out)
