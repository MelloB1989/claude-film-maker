"""One batch of the gesture library on box B (agent-08, R7): per clip, dump the Mixamo FBX (Blender), retarget onto her
skeleton (elbows cleared), annotate, mirror it when its left hand leads (the mic is on her LEFT) and preview it on the
mannequin. Steps run one after another (never in parallel), under the caller's `nice`.

    nice -n 15 python3 batch.py catalog.json FBX_DIR her_body_read.json WORK_DIR --blender BIN [--only id,id] [--no-preview]

WORK_DIR/<id>/: dump.json, rtg.json (agent-10 / agent-01's clip), entry.json (library entry), preview.mp4.
WORK_DIR/library.json: every entry so far (copied into the repo as films/host-studio/explainers/gesture/library.json).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import annotate as A  # noqa: E402
import retarget as R  # noqa: E402


def blender(bin_, script, *args):
    cmd = [bin_, "-b", "--factory-startup", "-t", "4", "-P", str(HERE / script), "--", *map(str, args)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{script} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")


def one(clip, fbx_dir, skel, work, bin_, preview):
    d = work / clip["id"]
    d.mkdir(parents=True, exist_ok=True)
    fbx = fbx_dir / clip["file"]
    if not (d / "dump.json").exists():
        blender(bin_, "mixamo_dump_blender.py", fbx, d / "dump.json")
    dump = json.load(open(d / "dump.json"))
    tg = R.Target(skel)
    res = R.Retarget(tg, dump).run()
    ann = A.annotate(res["joints"])
    mirrored = False
    if clip.get("mirror", ann["left_dominant"]):
        res = R.Retarget(tg, R.mirror_dump(dump)).run()
        ann = A.annotate(res["joints"])
        mirrored = True
    json.dump(res, open(d / "rtg.json", "w"))
    e = A.entry(dict(clip, mirrored=mirrored), ann)
    e.update(file=f"{clip['id']}/rtg.json", source_file=clip["file"], clearance_fixes=res["clearance_fixes"],
             clearance_max_deg=round(res["clearance_max_deg"], 1))
    json.dump(e, open(d / "entry.json", "w"), indent=1)
    if preview:
        blender(bin_, "preview_blender.py", d / "rtg.json", work / "skeleton.json", d / "preview.mp4",
                f"{clip['id']}{' (mirrored)' if mirrored else ''}")
    return e


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("catalog")
    ap.add_argument("fbx_dir", type=Path)
    ap.add_argument("skeleton", type=Path)
    ap.add_argument("work", type=Path)
    ap.add_argument("--blender", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--no-preview", action="store_true")
    a = ap.parse_args(argv)
    a.work.mkdir(parents=True, exist_ok=True)
    skel = json.load(open(a.skeleton))
    json.dump(skel, open(a.work / "skeleton.json", "w"))
    clips = json.load(open(a.catalog))["clips"]
    if a.only:
        want = a.only.split(",")
        clips = [c for c in clips if c["id"] in want]
    lib_path = a.work / "library.json"
    lib = json.load(open(lib_path)) if lib_path.exists() else {"clips": []}
    have = {c["id"]: i for i, c in enumerate(lib["clips"])}
    for c in clips:
        if not (a.fbx_dir / c["file"]).exists():
            print(c["id"], "SKIP: no FBX")
            continue
        t0 = time.time()
        try:
            e = one(c, a.fbx_dir, skel, a.work, a.blender, not a.no_preview)
        except Exception as ex:  # one bad clip never stops the batch
            print(c["id"], "FAIL", ex)
            continue
        if e["id"] in have:
            lib["clips"][have[e["id"]]] = e
        else:
            have[e["id"]] = len(lib["clips"])
            lib["clips"].append(e)
        json.dump(lib, open(lib_path, "w"), indent=1)
        print(c["id"], f"{time.time() - t0:.0f}s", "events", len(e["events"]), "hand", e["hand"],
              "energy", e["energy"], "mirrored", e["mirrored"], "clear", e["clearance_fixes"], e["clearance_max_deg"])


if __name__ == "__main__":
    main(sys.argv[1:])
