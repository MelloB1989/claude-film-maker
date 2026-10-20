"""Timeless v3 finishing: stand-in stage passes until the Blender stage renders exist.

    python -m filmtools.amv3.standin submit [--frames 0-818] [--res full|half]   # build + render on the VM (queue)
    python -m filmtools.amv3.standin proj                                        # only write the stand-in project
    python -m filmtools.amv3.standin light --plate DIR --out DIR                 # (VM) light pass from a plate pass

The v2 final frames are graded and carry v2's titles, so grading them again (and putting the titles on top a second time)
would say nothing about the v3 finish. The stand-in plate is v2's own EffectCraft project (`final.ecproj`) rendered with
every GRADE, FX, TITLE, WATERMARK and graphic SPECIAL layer switched off: v2's camera, cuts, rift, drop portal and
triptych, ungraded, which is what a stage `plate` pass is. (The triptych panels keep the panel grade v2 baked into
its precomp.) The `light` pass is the plate's own highlights (smoothstep of luma 0.80..0.96, colour kept) on black.
The `text` pass is left empty (ecfinish skips a pass that has no frames).

Output on the VM: `$AMV3_DATA/finish/standin/{plate,light}/f_NNNNN.png`, copied back to `out/standin/{plate,light}/`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ecrender as R

V2_PROJ = Path("/home/nikhil/code/.worktrees/cfm-amv2/out/timeless/amv2/frames_final/final.ecproj")
PROJ = R.ROOT / "build/amv3/standin_plate.ecproj"
OFF = ("WATERMARK", "TITLE", "GRADE", "FX", "OUTRO", "SPECIAL_CAPTION", "SPECIAL_DROP_FLASH", "SPECIAL_SHATTER_FLASH",
       "SPECIAL_RIFT_FLASH", "SPECIAL_CHROMA_SPLIT", "SPECIAL_RIFT_CHROMA", "SPECIAL_SPEEDLINES")


def make_proj(src=V2_PROJ, out=PROJ):
    J = json.loads(Path(src).read_text())
    main = next(v for v in J["items"].values() if v["kind"].get("type") == "Comp" and v["name"] == "MAIN")
    off = []
    for L in main["kind"]["layers"]:
        if L["name"].startswith(OFF) and L["switches"]["video"]:
            L["switches"]["video"] = False
            off.append(L["name"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(J))
    print(f"{out}: {len(off)} layers off, {len(main['kind']['layers']) - len(off)} kept")
    return out


def light(plate, out):
    """(VM: numpy + opencv) the plate's highlights on black, as RGB PNGs of the same names."""
    import cv2
    import numpy as np
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(Path(plate).glob("f_*.png")):
        im = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        rgb = im[..., :3].astype(np.float32) / 255.0
        a = im[..., 3:4].astype(np.float32) / 255.0 if im.shape[2] == 4 else 1.0
        y = rgb[..., 0:1] * 0.0722 + rgb[..., 1:2] * 0.7152 + rgb[..., 2:3] * 0.2126      # BGR
        t = np.clip((y - 0.80) / 0.16, 0, 1)
        m = t * t * (3 - 2 * t) * a
        cv2.imwrite(str(out / p.name), np.clip(rgb * m * 255.0 + 0.5, 0, 255).astype(np.uint8))
        n += 1
    print(f"light: {n} frames -> {out}")


def submit(frames="0-818", res="full", procs=2, threads=8, wait=True, job="agent05-standin"):
    a, b = (int(x) for x in frames.split("-"))
    b += 1
    make_proj()
    fdir = "out/standin/plate"
    runner = R.write_runner(job, R.rel(PROJ), "MAIN", fdir, R.chunks(a, b, 48), procs, threads, res)
    keep = "$AMV3_DATA/finish/standin"
    cmd = (f"bash {runner} && (cd tools && python -m filmtools.amv3.standin light --plate ../{fdir} --out ../out/standin/light) "
           f"&& mkdir -p {keep} && cp -r out/standin/plate out/standin/light {keep}/ && ls {keep}/plate | wc -l")
    name = R.submit(job, cmd, "out/standin", procs * threads)
    print("submitted", name)
    if not wait:
        return 0
    rc, log, secs = R.wait(name)
    print(log[-1500:])
    miss = R.missing(R.ROOT / fdir, a, b)
    print(json.dumps(dict(rc=rc, wall=round(secs, 1), per_frame=round(secs / (b - a), 3), missing=len(miss))))
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("submit", "proj", "light"))
    ap.add_argument("--frames", default="0-818")
    ap.add_argument("--res", default="full")
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--job", default="agent05-standin")
    ap.add_argument("--plate")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "proj":
        make_proj()
        return 0
    if a.cmd == "light":
        light(a.plate, a.out)
        return 0
    return submit(a.frames, a.res, wait=not a.no_wait, job=a.job)


if __name__ == "__main__":
    sys.exit(main())
