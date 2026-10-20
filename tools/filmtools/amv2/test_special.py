"""Harness for ec/special.jsx while the core builder (ecbuild.py) does not exist.

    python3 tools/filmtools/amv2/test_special.py --frames 244-262 --out /work/out/rift
    python3 tools/filmtools/amv2/test_special.py --build-only          # just write the .ecproj

It builds a MAIN with the clips as plain layers named SHOT_<id> (test_special_harness.jsx), runs special_spec.extend(),
then SPECIAL.build(), saves the project and renders the frames with `effectcraft-cli render-frame`.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.dirname(HERE))
EC = os.environ.get("EFFECTCRAFT_CLI") or "/home/nikhil/code/film-making/bin/artcraft/effectcraft-0.10.0-linux-x86_64/bin/effectcraft-cli"
DATA = os.environ.get("AMV2_DATA") or ("/home/nikhil/code/film-making/work/timeless_v2" if os.path.isdir("/home/nikhil/code/film-making/work/timeless_v2") else "/work/out/data")
SHOTS = ["S07", "S08", "S09", "S10", "S16", "S17", "S18", "S19", "S31", "S32"]


def load_edl():
    sys.path.insert(0, os.path.join(ROOT, "films", "timeless", "amv2"))
    import edl
    return json.loads(json.dumps(edl.build()))


def make_script(E, project, shots, src="clips", samples=16):
    from amv2 import special_spec
    special_spec.extend(E, dict(root=ROOT, data=DATA))
    cfg = dict(root=ROOT, data=DATA, src=src, shots=shots, samples=samples)
    parts = ["var E = %s;\nvar CFG = %s;\nvar OUT_PROJECT = %s;\n" % (json.dumps(E), json.dumps(cfg), json.dumps(project))]
    for p in ("test_special_harness.jsx", os.path.join("ec", "special.jsx")):
        parts.append(open(os.path.join(HERE, p)).read())
    parts.append("SPECIAL.build(main, E, ctx);\napp.project.save(new File(OUT_PROJECT));\n$.writeln('saved ' + OUT_PROJECT);\n")
    return "\n".join(parts)


def frames_arg(s, step):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1, step))
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", default="")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--out", default="/work/out/special")
    ap.add_argument("--project", default="")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--src", default="clips")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    project = a.project or os.path.join(a.out, "special_test.ecproj")
    if not a.no_build:
        script = os.path.join(a.out, "build.jsx")
        open(script, "w").write(make_script(load_edl(), project, SHOTS, a.src, a.samples))
        t = time.time()
        r = subprocess.run([EC, "script", script, "--empty"], capture_output=True, text=True)
        print(r.stdout[-3000:], r.stderr[-2000:], "build %.1fs" % (time.time() - t))
        if r.returncode:
            sys.exit(r.returncode)
    if a.build_only or not a.frames:
        return

    def render(f):
        out = os.path.join(a.out, "%04d.png" % f)
        cmd = [EC, "render-frame", "--project", project, "--comp", "MAIN", "--frame", str(f), "--out", out]
        if a.scale != 1.0:
            cmd += ["--scale", str(a.scale)]
        t = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        return f, time.time() - t, (r.stdout + r.stderr).strip()[-200:]

    with ThreadPoolExecutor(a.jobs) as ex:
        for f, dt, msg in ex.map(render, frames_arg(a.frames, a.step)):
            print("frame %d %.1fs %s" % (f, dt, msg))


if __name__ == "__main__":
    main()
