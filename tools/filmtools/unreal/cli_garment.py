"""film-ue garment-fit: refit a garment to a MetaHuman's body with real ease, in headless Blender, ON THE BOX (the
body is face data: it never leaves it). The step between two ops (docs/unreal/garment.md):

    film-ue op garment.export label=Host out_dir=/srv/ue/fit/host 'sequences=["/Game/Reel/SEQ_Reel"]'
    film-ue garment-fit --src /srv/ue/fit/host --garment tee --out /srv/ue/fit/host/out [--drape-frames 40] \
        [--ease '{"chest": 1.8}'] [--only-slots shirt] [--blender /srv/ue/tools/blender-4.2/blender]
    film-ue op mh.import_garment fbx=/srv/ue/fit/host/out/garment_fit_tee.fbx dest=/Game/Host/Fit/SKM_Host_Tee_Fit

It runs blender/garment_fit.py (lib/garmentfit.py has the numbers), then reads fit_report.json and says, in words,
what passed and what to change. Exit 0 on pass, 1 on a failed fit (the FBX is written but must not be imported),
2 when it could not run. `--report <fit_report.json>` re-reads a report without running Blender.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from pathlib import Path

NAMES = ("garment-fit",)
ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "blender" / "garment_fit.py"
PASS_THROUGH = ("garment", "out", "ease", "min_ease", "slack", "pull", "smooth_iters", "passes", "drape_frames",
                "weights", "thickness", "only_slots", "collider", "anim_samples")


def register(sub) -> None:
    p = sub.add_parser("garment-fit", help="refit a garment to the body with real ease (headless Blender, on the box)")
    p.add_argument("--src", help="garment.export's out_dir (body/face/ref_body/garment_*.fbx, manifest.json)")
    p.add_argument("--garment", default="tee")
    p.add_argument("--out")
    p.add_argument("--ease", default="", help='JSON {region: cm}: collar shoulder sleeve chest waist hem other')
    p.add_argument("--min-ease", type=float)
    p.add_argument("--slack", type=float)
    p.add_argument("--pull", type=float)
    p.add_argument("--smooth-iters", type=int)
    p.add_argument("--passes", type=int)
    p.add_argument("--drape-frames", type=int)
    p.add_argument("--weights", choices=("transfer", "keep"))
    p.add_argument("--thickness", type=float)
    p.add_argument("--only-slots", default="")
    p.add_argument("--collider", default="")
    p.add_argument("--anim-samples", type=int)
    p.add_argument("--blender", default="", help="the Blender binary (default $BLENDER, /srv/ue/tools/blender-*)")
    p.add_argument("--report", default="", help="only judge this fit_report.json")
    p.add_argument("--json", action="store_true")


def blender_bin(given: str = "") -> str:
    for c in (given, os.environ.get("BLENDER", ""), *sorted(glob.glob("/srv/ue/tools/blender-*/blender"))[-1:]):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    from shutil import which
    return which("blender") or ""


def command(a, blender: str) -> list:
    """The Blender command line for args `a` (argparse namespace or dict)."""
    d = vars(a) if not isinstance(a, dict) else a
    cmd = [blender, "-b", "--factory-startup", "--python-exit-code", "2", "-P", str(SCRIPT), "--", "--src", d["src"]]
    for k in PASS_THROUGH:
        v = d.get(k)
        if v in (None, ""):
            continue
        cmd += ["--" + k.replace("_", "-"), str(v)]
    return cmd


def judge(rep: dict) -> dict:
    """Plain words from a fit report: {"pass", "lines": [...], "next": [...]}."""
    lines, nxt = [], []
    b, a = rep.get("before", {}).get("all", {}), rep.get("after", {}).get("all", {})
    if b and a:
        lines.append(f"ease median {b.get('median')} -> {a.get('median')} cm, spread {b.get('spread')} -> "
                     f"{a.get('spread')}, inside the body {100 * b.get('inside', 0):.2f}% -> {100 * a.get('inside', 0):.2f}%")
    for r in ("collar", "shoulder", "chest", "waist", "hem", "sleeve"):
        x = rep.get("after", {}).get(r)
        if x:
            lines.append(f"  {r:8s} p10 {x['p10']:5.2f}  median {x['median']:5.2f}  p90 {x['p90']:5.2f} cm  (n {x['n']})")
    for k, v in (rep.get("poses") or {}).items():
        lines.append(f"pose test {k}: {v['inside']} verts inside" + (f" (deepest {v['deepest_cm']} cm at f{v['frame']})"
                                                                     if v["inside"] else ""))
    probs = rep.get("problems") or []
    for p in probs:
        if "shell" in p:
            nxt.append("drape it: --drape-frames 40 (the hem and sleeves fall, folds form)")
        elif "inside the body" in p and "pose test" in p:
            nxt.append("weights: --weights transfer (from the uncut body), or more ease where it clips (--ease)")
        elif "inside" in p or "closer than" in p:
            nxt.append("raise --min-ease or the region's --ease; check the export is the same build (garment.export)")
    if rep.get("pass"):
        nxt.append(f"import: film-ue op mh.import_garment fbx={rep.get('fbx')} dest=/Game/<who>/Fit/SKM_<who>_<garment>_Fit; "
                   "then mh.dress (materials without any WPO inflate) and qa.clip + qa.garment_look")
    return {"pass": bool(rep.get("pass")), "problems": probs, "lines": lines, "next": list(dict.fromkeys(nxt))}


def dispatch(a) -> bool:
    if a.cmd != "garment-fit":
        return False
    if a.report:
        rep = json.loads(Path(a.report).read_text())
    else:
        if not (a.src and a.out):
            raise SystemExit("garment-fit needs --src (garment.export's out_dir) and --out")
        if not os.path.isfile(os.path.join(a.src, "ref_body.fbx")) or \
                not os.path.isfile(os.path.join(a.src, f"garment_{a.garment}.fbx")):
            sys.stderr.write(f"no ref_body.fbx / garment_{a.garment}.fbx in {a.src}: run film-ue op garment.export\n")
            raise SystemExit(2)
        bl = blender_bin(a.blender)
        if not bl:
            sys.stderr.write("no Blender: pass --blender or set $BLENDER (the box has /srv/ue/tools/blender-*)\n")
            raise SystemExit(2)
        os.makedirs(a.out, exist_ok=True)
        log = os.path.join(a.out, "garment_fit.log")
        with open(log, "w") as fh:
            rc = subprocess.run(command(a, bl), stdout=fh, stderr=subprocess.STDOUT).returncode
        rp = os.path.join(a.out, "fit_report.json")
        if not os.path.isfile(rp):
            sys.stderr.write(f"Blender exited {rc} with no report: see {log}\n")
            raise SystemExit(2)
        rep = json.loads(Path(rp).read_text())
    j = judge(rep)
    if a.json:
        print(json.dumps(j, indent=1))
    else:
        print("PASS" if j["pass"] else "FAIL: " + "; ".join(j["problems"]))
        for line in j["lines"] + ["next: " + n for n in j["next"]]:
            print(line)
    raise SystemExit(0 if j["pass"] else 1)
