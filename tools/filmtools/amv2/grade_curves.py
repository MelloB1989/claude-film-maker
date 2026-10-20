"""Measure each act's tone curve (luma in -> luma out, after trims-free look + limiter) with a vertical grey ramp rendered
through GRADE.build, and write grade_curves.json. grade_spec uses it so the per-shot trims aim at the FINAL picture.

    python grade_curves.py          (needs effectcraft-cli, numpy and PIL; rerun after changing G.LOOKS / G.FINISH)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_grade as tg  # noqa: E402

OUT = os.path.join(HERE, "grade_curves.json")
N = 33


def run(outdir="/tmp/grade_curves"):
    import numpy as np
    from PIL import Image
    E = tg.load_edl()
    E["shots"] = []
    E["x"] = {"grade": {"shots": {}, "skip": ["glow", "grain", "sharpen", "vignette"]}}
    body = open(os.path.join(HERE, "ec", "grade.jsx")).read()
    fps, w, h = E["fps"], E["w"], E["h"]
    js = "\n".join([
        "var E = %s;" % json.dumps(E),
        "var ctx = {fps:%d, w:%d, h:%d, log:function(m){$.writeln(m);}};" % (fps, w, h),
        "var main = app.project.items.addComp('MAIN', %d, %d, 1, %d/%d, %d);" % (w, h, E["dur"], fps, fps),
        "var r = main.layers.addSolid([1,1,1],'ramp',%d,%d,1,main.duration);" % (w, h),
        "var rp = r.property('ADBE Effect Parade').addProperty('ADBE Ramp');",
        "rp.property('Start of Ramp').setValue([0,0]); rp.property('End of Ramp').setValue([0,%d]);" % h,
        "rp.property('Start Color').setValue([0,0,0,1]); rp.property('End Color').setValue([1,1,1,1]);",
        body, "GRADE.build(main, E, ctx);",
        "app.project.save(new File(%s));" % json.dumps(outdir + "/c.ecproj")])
    os.makedirs(outdir, exist_ok=True)
    open(outdir + "/c.jsx", "w").write(js)
    subprocess.run([tg.EC, "script", outdir + "/c.jsx", "--empty"], check=True, capture_output=True)
    curves = {}
    for act, f in (("tobey", 100), ("andrew", 360), ("tom", 650)):
        o = "%s/%s.png" % (outdir, act)
        subprocess.run([tg.EC, "render-frame", "--project", outdir + "/c.ecproj", "--comp", "MAIN", "--frame", str(f), "--out", o],
                       check=True, capture_output=True)
        a = np.asarray(Image.open(o).convert("RGB")).astype(float) / 255
        H = a.shape[0]
        xs, ys = [], []
        for i in range(N):
            t = i / (N - 1)
            y = min(H - 1, max(0, int(round(t * (H - 1)))))
            xs.append(t)
            y0, y1 = max(0, y - 6), min(H, y + 7)
            ys.append(float(a[y0:y1, 900:1020].mean(axis=(0, 1)) @ np.array([0.2126, 0.7152, 0.0722])))
        curves[act] = {"x": xs, "y": [round(v, 4) for v in ys]}
    json.dump(curves, open(OUT, "w"), indent=1)
    return curves


if __name__ == "__main__":
    c = run()
    for k, v in c.items():
        print(k, [round(x, 2) for x in v["y"][::4]])
