#!/usr/bin/env python3
"""Harness for ec/fx.jsx: builds a MAIN of plain clip layers named SHOT_<id> at their EDL frames (1x speed from src[0]),
runs FX.buildUnder / FX.buildOver with the core's ctx shape, saves a project and renders frames.

  python test_fx.py build  OUT_DIR [--nofx]          write OUT_DIR/main[_nofx].jsx project
  python test_fx.py frames OUT_DIR F1 F2 ...         render before/after PNG pairs at those MAIN frames
  python test_fx.py pairs  OUT_DIR                   render the standard delivery set
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
EDL = os.path.join(ROOT, "films/timeless/amv2/edl.json")
EC = os.environ.get("EFFECTCRAFT", "/home/nikhil/code/film-making/bin/artcraft/effectcraft-0.10.0-linux-x86_64/bin/effectcraft-cli")
PAIRS = [("hit_686_shake_flash", 687), ("hit_284_chroma", 285), ("glitch_dark_174", 174), ("glitch_electric_435", 435),
         ("sweep_cut_118", 118), ("sweep_open_5", 5), ("letterbox_S25_640", 640), ("fire_M12_715", 715),
         ("ink_587", 587), ("ink_inverted_588", 588), ("ink_656_f1", 657), ("speed_lines_413", 413), ("riser_478", 478),
         ("glint_16", 16), ("flare_258", 258), ("glass_563", 563), ("eye_glow_251", 251), ("sun_318", 318)]


def load_extend(E):
    import importlib.util
    p = os.path.join(HERE, "fx_spec.py")
    spec = importlib.util.spec_from_file_location("fx_spec", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    m.extend(E, {"root": ROOT})
    return E


def jsx(E, project, fx):
    lib = open(os.path.join(HERE, "ec/fx.jsx")).read()
    out = []
    out.append("var E = %s;" % json.dumps(E))
    out.append(lib)
    out.append("""
var FPS=30, W=1920, H=1080;
var main = app.project.items.addComp("MAIN", W, H, 1, 900/30, 30);
var foot = {}, LAY = {}, SC = {};
for (var i=0;i<E.shots.length;i++){
  var S=E.shots[i];
  var it = foot[S.clip]; if(!it){ it = app.project.importFile(new ImportOptions(new File(S.file))); foot[S.clip]=it; }
  var l = main.layers.add(it); l.name = "SHOT_"+S.id;
  l.startTime = S.a/FPS - S.src[0]; l.inPoint = S.a/FPS; l.outPoint = S.b/FPS;
  LAY[S.id]=l;
}
var ctx = {fps:FPS,w:W,h:H,root:%s,data:"",src:"clips",elements:null,log:function(m){$.write("[ctx] "+m+"\\n");},
  shot:function(id){return LAY[id]||null;}, shotComp:function(id){return null;}, matte:function(id){return null;}};
if (%s) { FX.buildUnder(main,E,ctx); FX.buildOver(main,E,ctx); }
app.project.save(new File(%s));
$.write("saved\\n");
""" % (json.dumps(ROOT), "true" if fx else "false", json.dumps(project)))
    return "\n".join(out)


def build(outdir, fx=True):
    os.makedirs(outdir, exist_ok=True)
    E = load_extend(json.load(open(EDL)))
    proj = os.path.join(outdir, "main%s.ecproj" % ("" if fx else "_nofx"))
    js = os.path.join(outdir, "main%s.jsx" % ("" if fx else "_nofx"))
    open(js, "w").write(jsx(E, proj, fx))
    r = subprocess.run([EC, "script", js, "--empty"], capture_output=True, text=True)
    print(r.stdout[-3000:], r.stderr[-2000:])
    return proj


def frames(outdir, fr, names=None):
    for k, f in enumerate(fr):
        for tag, suffix in (("nofx", "_nofx"), ("fx", "")):
            proj = os.path.join(outdir, "main%s.ecproj" % suffix)
            out = os.path.join(outdir, "%s_%s.png" % (names[k] if names else "f%d" % f, tag))
            r = subprocess.run([EC, "render-frame", "--project", proj, "--comp", "MAIN", "--frame", str(f), "--scale", os.environ.get("SCALE","1"), "--out", out],
                               capture_output=True, text=True)
            if r.returncode: print(r.stderr[-500:])


if __name__ == "__main__":
    cmd, outdir = sys.argv[1], sys.argv[2]
    if cmd == "build":
        build(outdir, "--nofx" not in sys.argv)
    elif cmd == "all":
        build(outdir, True); build(outdir, False)
    elif cmd == "frames":
        frames(outdir, [int(x) for x in sys.argv[3:]])
    elif cmd == "pairs":
        frames(outdir, [p[1] for p in PAIRS], [p[0] for p in PAIRS])
