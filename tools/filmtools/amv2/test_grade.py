"""Test harness for ec/grade.jsx (no core builder needed).

Builds a MAIN comp with the clips as plain layers SHOT_<id> at their EDL frames, runs grade_spec.extend + GRADE.build,
saves the project and renders the requested frames.

    python test_grade.py build  [--no-grade] [--out DIR]          # writes DIR/grade_test.jsx + .ecproj
    python test_grade.py frames F1 F2 ... [--no-grade] [--out DIR]  # + render-frame per frame -> DIR/<tag>_f<N>.png
    python test_grade.py sheet  [--out DIR]                       # before/after contact sheet (contact_sheet.py)
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EC = os.environ.get("EFFECTCRAFT", "/home/nikhil/code/film-making/bin/artcraft/effectcraft-0.10.0-linux-x86_64/bin/effectcraft-cli")
sys.path.insert(0, HERE)


def load_edl():
    return json.load(open(os.path.join(ROOT, "films/timeless/amv2/edl.json")))


def make_script(E, with_grade=True, ctx_extra=None):
    """The JSX text: prelude (E, ctx, plain-layer MAIN) + grade.jsx + the build call, the way the core concatenates libs."""
    fps = E["fps"]
    shots = [dict(id=s["id"], clip=s["clip"], file=s["file"], a=s["a"], b=s["b"], lo=min(s["src"])) for s in E["shots"]]
    pre = ["var E = %s;" % json.dumps(E),
           "var SHOTS = %s;" % json.dumps(shots),
           "var ctx = {fps:%d, w:%d, h:%d, root:%s, data:'', src:'clips', elements:null, log:function(m){$.writeln('[ctx] '+m);}};" % (
               fps, E["w"], E["h"], json.dumps(ROOT)),
           "var main = app.project.items.addComp('MAIN', %d, %d, 1, %d/%d, %d);" % (E["w"], E["h"], E["dur"], fps, fps),
           "var _L = {};",
           "(function(){ for (var i = 0; i < SHOTS.length; i++) { var S = SHOTS[i];",
           "  var it = app.project.importFile(new ImportOptions(new File(S.file)));",
           "  var l = main.layers.add(it); l.name = 'SHOT_' + S.id;",
           "  l.startTime = S.a / ctx.fps - S.lo; l.inPoint = S.a / ctx.fps; l.outPoint = S.b / ctx.fps;",
           "  _L[S.id] = l; } })();",
           "ctx.shot = function(id){ return _L[id]; };",
           "ctx.shotComp = function(id){ return null; };",
           "ctx.matte = function(id){ return null; };"]
    body = open(os.path.join(HERE, "ec", "grade.jsx")).read()
    post = ["GRADE.build(main, E, ctx);"] if with_grade else []
    return "\n".join(pre) + "\n" + body + "\n" + "\n".join(post) + "\n"


def build(out, with_grade=True):
    import grade_spec
    E = load_edl()
    grade_spec.extend(E, {"root": ROOT, "data": os.environ.get("AMV2_DATA", ""), "src": "clips"})
    os.makedirs(out, exist_ok=True)
    tag = "graded" if with_grade else "plain"
    js = make_script(E, with_grade) + "\napp.project.save(new File(%s));\n" % json.dumps(os.path.join(out, "%s.ecproj" % tag))
    p = os.path.join(out, "%s.jsx" % tag)
    open(p, "w").write(js)
    r = subprocess.run([EC, "script", p, "--empty"], capture_output=True, text=True)
    sys.stdout.write(r.stdout[-3000:] + r.stderr[-2000:])
    return os.path.join(out, "%s.ecproj" % tag)


def render_frames(proj, frames, out, tag, scale=None):
    outs = []
    for f in frames:
        o = os.path.join(out, "%s_f%d.png" % (tag, f))
        cmd = [EC, "render-frame", "--project", proj, "--comp", "MAIN", "--frame", str(f), "--out", o]
        if scale:
            cmd += ["--scale", str(scale)]
        subprocess.run(cmd, check=True, capture_output=True)
        outs.append(o)
    return outs


def ab(out, frames, scale):
    """Render plain + graded frames, print the stats of each pair and write ab_<frame>.png (plain left, graded right)."""
    import grade_measure as gm
    import numpy as np
    from PIL import Image
    pp = build(out, False)
    gp = build(out, True)
    a = render_frames(pp, frames, out, "plain", scale)
    b = render_frames(gp, frames, out, "graded", scale)
    for f, fa, fb in zip(frames, a, b):
        ia, ib = Image.open(fa).convert("RGB"), Image.open(fb).convert("RGB")
        sa, sb = gm.stats([np.asarray(ia)]), gm.stats([np.asarray(ib)])
        print("f%-4d plain p1 %.3f p50 %.3f p99 %.3f clip %5.2f sat %.2f | graded p1 %.3f p50 %.3f p99 %.3f clip %5.2f sat %.2f skin %s" % (
            f, sa["p1"], sa["p50"], sa["p99"], sa["clip"], sa["sat"], sb["p1"], sb["p50"], sb["p99"], sb["clip"], sb["sat"], sb["skin_hue"]))
        w = Image.new("RGB", (ia.width * 2, ia.height))
        w.paste(ia, (0, 0))
        w.paste(ib, (ia.width, 0))
        w.save(os.path.join(out, "ab_%d.png" % f))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "frames", "ab"])
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("frames", nargs="*", type=int)
    ap.add_argument("--no-grade", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "out/timeless/amv2/grade_test"))
    a = ap.parse_args()
    if a.cmd == "ab":
        ab(a.out, a.frames, a.scale or 0.5)
        sys.exit(0)
    proj = build(a.out, not a.no_grade)
    if a.cmd == "frames":
        print(render_frames(proj, a.frames, a.out, "plain" if a.no_grade else "graded"))
