#!/usr/bin/env python3
"""Harness for the TITLES library (ec/titles.jsx) until the core builder exists.

Builds a MAIN comp (1920x1080, 30 fps, 900 f) with the clips as plain layers named SHOT_<id> at their EDL frames, a
disabled MATTE_<id> layer where a matte exists, runs `TITLES.build(main, E, ctx)` and renders the frames you ask for.

  python3 tools/filmtools/amv2/test_titles.py build  --out out/titles            # writes out/titles/titles_test.ecproj
  python3 tools/filmtools/amv2/test_titles.py frames --out out/titles --set key   # entry+2 / hold / exit-2 of every title
  python3 tools/filmtools/amv2/test_titles.py frames --out out/titles --frames 305,320,333 [--scale 0.5]

`--set key` renders, for each title, f+2, the middle of the hold and f1-3 (the last frames are f1-1; "exit -2" = f1-3).
Matte for S10 (AMAZING) is the old roto A03_sunset_mask (33 frames); other shots have no matte here, so SPIDER-MAN falls
back to in front of the subject (the library's documented fallback). $AMV2_DATA/mattes/<clip>/ is used when it exists.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import titles_spec  # noqa: E402

EC = os.environ.get("EFFECTCRAFT_CLI") or "/home/nikhil/code/film-making/bin/artcraft/effectcraft-0.10.0-linux-x86_64/bin/effectcraft-cli"
ROTO = "/home/nikhil/code/film-making/handover/amv_handover/project/roto"
LIBS = ["titles"]


def load_edl():
    with open(os.path.join(REPO, "films", "timeless", "amv2", "edl.json")) as fh:
        return json.load(fh)


def matte_dirs(E):
    """shot id -> matte frame folder (png sequence)."""
    out = {}
    data = os.environ.get("AMV2_DATA")
    for s in E["shots"]:
        cand = []
        if data:
            cand.append(os.path.join(data, "mattes", s["clip"]))
        cand.append(os.path.join(ROTO, s["clip"]))
        for c in cand:
            if os.path.isdir(c) and any(n.endswith(".png") for n in os.listdir(c)):
                out[s["id"]] = c
                break
    return out


def build_jsx(E, project_path):
    titles_spec.extend(E)
    mattes = matte_dirs(E)
    shots = [{"id": s["id"], "clip": s["clip"], "file": s["file"], "a": s["a"], "b": s["b"], "src0": s["src"][0]} for s in E["shots"]]
    # only the shots a title touches are imported: the harness stays small
    need = set()
    for i in range(len(E["titles"])):
        for k in ("shot", "behind"):
            v = E["x"]["titles"][k].get(str(i))
            if v:
                need.add(v)
    for s in E["shots"]:
        for T in E["titles"]:
            if s["a"] < T["f1"] and s["b"] > T["f"]:
                need.add(s["id"])
    shots = [s for s in shots if s["id"] in need]
    pre = """
var E = %s;
var SHOTS = %s;
var MATTES = %s;
var OUT = %s;
var FPS = E.fps;
var proj = app.project;
var main = proj.items.addComp("MAIN", E.w, E.h, 1, E.dur / FPS, FPS);
main.shutterAngle = 270; main.shutterPhase = -135; main.motionBlurSamplesPerFrame = 12;
var LAY = {}, MAT = {};
function T_(f) { return f / FPS; }
for (var i = 0; i < SHOTS.length; i++) {
    var s = SHOTS[i];
    var it = proj.importFile(new ImportOptions(new File(s.file)));
    var l = main.layers.add(it);
    l.name = "SHOT_" + s.id;
    l.startTime = T_(s.a) - s.src0; l.inPoint = T_(s.a); l.outPoint = T_(s.b);
    LAY[s.id] = l;
    if (MATTES[s.id]) {
        var o = new ImportOptions(new File(MATTES[s.id] + "/00000.png")); o.sequence = true;
        var mi = proj.importFile(o);
        try { mi.mainSource.conformFrameRate = FPS; } catch (e) {}
        var ml = main.layers.add(mi);
        ml.name = "MATTE_" + s.id; ml.startTime = T_(s.a); ml.inPoint = T_(s.a); ml.outPoint = T_(s.b); ml.enabled = false;
        MAT[s.id] = ml;
    }
}
var ctx = { fps: FPS, w: E.w, h: E.h, root: %s, data: %s, src: "clips", elements: proj.rootFolder,
    log: function (m) { writeLn("[ctx] " + m); },
    shot: function (id) { return LAY[id] || null; }, shotComp: function (id) { return null; },
    matte: function (id) { return MAT[id] || null; } };
""" % (json.dumps(E), json.dumps(shots), json.dumps(mattes), json.dumps(project_path), json.dumps(REPO), json.dumps(os.environ.get("AMV2_DATA", "")))
    libs = ""
    for lib in LIBS:
        with open(os.path.join(HERE, "ec", lib + ".jsx")) as fh:
            libs += fh.read() + "\n"
    post = """
var res = TITLES.build(main, E, ctx);
writeLn("TITLES.build -> " + JSON.stringify(res));
proj.save(new File(OUT));
"""
    return pre + libs + post


def do_build(out):
    os.makedirs(out, exist_ok=True)
    proj = os.path.abspath(os.path.join(out, "titles_test.ecproj"))
    E = load_edl()
    jsx = os.path.join(out, "titles_test_build.jsx")
    with open(jsx, "w") as fh:
        fh.write(build_jsx(E, proj))
    r = subprocess.run([EC, "script", jsx, "--empty"], capture_output=True, text=True)
    print(r.stdout[-3000:], r.stderr[-3000:])
    if r.returncode:
        sys.exit(r.returncode)
    return proj


def key_frames(E):
    fr = []
    for i, T in enumerate(E["titles"]):
        if T["style"].startswith("blender_"):
            continue
        n = T["f1"] - T["f"]
        fr.append((i, T["style"], T["text"], [T["f"] + 2, T["f"] + n // 2, T["f1"] - 3]))
    return fr


def do_frames(out, frames, scale):
    proj = os.path.abspath(os.path.join(out, "titles_test.ecproj"))
    for f in frames:
        png = os.path.join(out, "f%04d.png" % f)
        cmd = [EC, "render-frame", "--project", proj, "--comp", "MAIN", "--frame", str(f), "--out", png]
        if scale != 1:
            cmd += ["--scale", str(scale)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(f, (r.stdout + r.stderr).strip().splitlines()[-1:])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "frames", "all"])
    ap.add_argument("--out", default=os.path.join(REPO, "out", "titles"))
    ap.add_argument("--frames", default="")
    ap.add_argument("--set", default="")
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()
    if a.cmd in ("build", "all"):
        do_build(a.out)
    if a.cmd in ("frames", "all"):
        E = load_edl()
        fr = [int(x) for x in a.frames.split(",") if x]
        if a.set == "key":
            for _, _, _, ff in key_frames(E):
                fr += ff
        do_frames(a.out, sorted(set(fr)), a.scale)
