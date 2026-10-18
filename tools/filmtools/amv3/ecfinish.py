"""Timeless v3: the EffectCraft finishing comp FINISH (grade, lens FX, glow, 2D titles, outro) and the final render.

    python -m filmtools.amv3.ecfinish build  --stage DIR [--outro DIR] [--out build/amv3/finish.ecproj] [--emit-only]
    python -m filmtools.amv3.ecfinish render --stage DIR [--res full|half] [--frames A-B] [--name NAME] [--procs 2]
                                             [--threads 8] [--no-encode] [--audio WAV]

--stage: the stage pass folder with plate/ text/ light/ (+ zvec.json), e.g. `$AMV3_DATA/stage/<name>` or the stand-in
`$AMV3_DATA/finish/standin` (filmtools.amv3.standin). A pass with no frames is skipped. --outro defaults to
`$AMV2_DATA/blender/outro` (v2 outro frames NNNN.png 0819-0899).

build: E = edl.json + finish_spec.extend (E.x.finish, E.x.titles) -> one script = data + ec/grade3.jsx + ec/lens.jsx +
v2's ec/titles.jsx (unchanged) + ec/finish.jsx -> `effectcraft-cli script` -> the .ecproj (exit 1 on any WARN).
render: ONE render-queue job that builds on the VM (the passes and $AMV2_DATA live there), keeps the project in
`$AMV3_DATA/builds/<name>.ecproj` (the queue's rsync --delete wipes build/), renders 48-frame chunks with `procs` workers,
and copies `out/timeless/amv3/frames_<name>/` back; then here: check, encode h264 CRF 16 yuv420p with the mix
(`$AMV2_DATA/mix.wav` until the v3 mix exists) -> `out/timeless/amv3/Timeless_v3[_<name>].mp4`, timings json.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import ecrender as R
from . import finish_spec

HERE = Path(__file__).resolve().parent
ROOT = R.ROOT
EDL = ROOT / "films/timeless/amv3/edl.json"
EC = HERE / "ec"
V2_TITLES = ROOT / "tools/filmtools/amv2/ec/titles.jsx"
OUT = ROOT / "out/timeless/amv3"
AMV2 = os.environ.get("AMV2_DATA", "/home/nikhil/code/film-making/work/timeless_v2")
DEF_OUTRO = f"{AMV2}/blender/outro"
MIX = Path("/home/nikhil/code/film-making/work/timeless_v2/mix.wav")


def build_script(stage, outro, out_project):
    E = json.loads(EDL.read_text())
    E = finish_spec.extend(E, stage, outro)
    parts = [f"var E = {json.dumps(E)};\nvar OUT_PROJECT = {json.dumps(str(out_project))};\n"]
    for p in (EC / "grade3.jsx", EC / "lens.jsx", V2_TITLES, EC / "finish.jsx"):
        parts.append(f"// ===== {p.name} =====\n" + p.read_text())
    return "\n".join(parts), E


def build(stage, outro=DEF_OUTRO, out=None, emit_only=False):
    out = Path(out or ROOT / "build/amv3/finish.ecproj").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    script, E = build_script(stage, outro, out)
    jsx = out.with_suffix(".build.jsx")
    jsx.write_text(script)
    P = E["x"]["finish"]["passes"]
    print(f"wrote {jsx} ({len(script) // 1024} KiB); passes: " +
          ", ".join(f"{k}={'%d f from %d (%dx%d)' % (v['n'], v['start'], v['w'], v['h']) if v else 'none'}" for k, v in P.items()))
    if emit_only:
        return 0
    r = subprocess.run([R.local_cli(), "script", str(jsx), "--empty"], capture_output=True, text=True)
    sys.stdout.write(r.stdout[-4000:])
    if r.returncode:
        sys.stderr.write(r.stderr[-4000:])
        return r.returncode
    warns = [l for l in r.stdout.splitlines() if l.startswith("WARN")]
    print(f"{out}: {len(warns)} warnings")
    return 1 if warns else 0


def render(stage, outro, name, res, frames, procs, threads, encode=True, audio=None):
    a, b = (int(x) for x in frames.split("-"))
    b += 1
    proj_rel = f"build/amv3/{name}.ecproj"
    fdir_rel = f"out/timeless/amv3/frames_{name}"
    runner = R.write_runner(name, proj_rel, "FINISH", fdir_rel, R.chunks(a, b, 48), procs, threads, res)
    keep = f"$AMV3_DATA/builds/{name}.ecproj"
    cmd = (f"mkdir -p {fdir_rel} build/amv3 && (cd tools && python -m filmtools.amv3.ecfinish build --stage '{stage}' "
           f"--outro '{outro}' --out ../{proj_rel}) > {fdir_rel}/build.log 2>&1; brc=$?; echo BUILD rc=$brc; "
           f"tail -n 12 {fdir_rel}/build.log; [ $brc -eq 0 ] || exit $brc; mkdir -p $AMV3_DATA/builds && cp {proj_rel} {keep}; "
           f"bash {runner}")
    job = R.submit(f"agent05-{name}", cmd, fdir_rel, procs * threads)
    print("submitted", job, flush=True)
    rc, log, secs = R.wait(job)
    print(log[-2500:])
    fdir = ROOT / fdir_rel
    miss = R.missing(fdir, a, b)
    ch = R.chunk_stats(log)
    t = dict(name=name, stage=stage, frames=[a, b], res=res, procs=procs, threads=threads, wall=round(secs, 1),
             sec_per_frame=round(secs / (b - a), 3), chunk_sec_per_frame=[round(float(c["secs"]) / (int(c["b"]) - int(c["a"])), 2) for c in ch],
             peak_rss_mb=max([int(c["rss_mb"]) for c in ch] or [0]), missing=len(miss), rc=rc)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"timings_{name}.json").write_text(json.dumps(t, indent=1))
    print(json.dumps(t))
    if rc or miss:
        raise SystemExit(f"render failed: rc {rc}, {len(miss)} missing (first {miss[:8]}); see {fdir}/err_*.txt, build.log")
    if encode:
        mp4 = OUT / ("Timeless_v3.mp4" if name == "final" else f"Timeless_v3_{name}.mp4")
        aud = audio or (MIX if MIX.exists() else None)
        R.encode(fdir, a, b, mp4, aud)
        print("encoded", mp4, "audio", aud)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("build", "render"))
    ap.add_argument("--stage", required=True)
    ap.add_argument("--outro", default=DEF_OUTRO)
    ap.add_argument("--out")
    ap.add_argument("--emit-only", action="store_true")
    ap.add_argument("--name", default="draft")
    ap.add_argument("--res", default="half")
    ap.add_argument("--frames", default="0-899")
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--no-encode", action="store_true")
    ap.add_argument("--audio")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        return build(a.stage, a.outro, a.out, a.emit_only)
    return render(a.stage, a.outro, a.name, a.res, a.frames, a.procs, a.threads, not a.no_encode, a.audio)


if __name__ == "__main__":
    sys.exit(main())
