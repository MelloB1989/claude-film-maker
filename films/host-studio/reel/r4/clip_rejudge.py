"""Round 4: re-run clip_pass.py's rules on the depth layers a pass saved (<shot>_<frame>_depth.bin), off the editor,
on the box (the layers come from frames with Host_Op on the level: they stay there). Writes DIR/clip.json afresh
(the old one kept as clip_pass.json the first time) and prints the worst per pair. Masks are not redrawn.
    python3 films/host-studio/reel/r4/clip_rejudge.py /srv/ue/reel/r4/clip/Host_before3 [--band 3 --tol 0.3 --near 1.5]
"""
import argparse
import array
import glob
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--band", type=float, default=3.0)
    ap.add_argument("--tol", type=float, default=0.3)
    ap.add_argument("--near", type=float, default=1.5)
    ap.add_argument("--fov", default="", help="JSON {shot: horizontal fov deg} for layers saved without it")
    a = ap.parse_args()
    ns = {"RUN": False, "BAND": a.band, "TOL": a.tol, "NEAR": a.near, "__name__": "clip_pass"}
    exec(compile(open(os.path.join(HERE, "clip_pass.py")).read(), "clip_pass.py", "exec"), ns)
    ns.update(BAND=a.band, TOL=a.tol, NEAR=a.near)
    fovs = json.loads(a.fov) if a.fov else {}
    old = os.path.join(a.dir, "clip.json")
    keep = os.path.join(a.dir, "clip_pass.json")
    if os.path.exists(old) and not os.path.exists(keep):
        shutil.copy(old, keep)
    rep = json.load(open(keep)) if os.path.exists(keep) else {"shots": {}}
    rep.update(band_cm=a.band, tol_cm=a.tol, near_cm=a.near, rejudged=True)
    for p in sorted(glob.glob(os.path.join(a.dir, "*_depth.bin"))):
        shot, f = os.path.basename(p)[:-len("_depth.bin")].rsplit("_", 1)
        f = str(int(f))
        with open(p, "rb") as fh:
            n = int.from_bytes(fh.read(4), "little")
            head = json.loads(fh.read(n))
            ns.update(W=head["w"], H=head["h"], FOV=float(head.get("fov") or fovs[shot]))
            d = {}
            for name in head["layers"]:
                x = array.array("f")
                x.fromfile(fh, head["w"] * head["h"])
                d[name] = x
        fr = rep["shots"].setdefault(shot, {}).setdefault(f, {})
        for u, g in ns["pairs"](list(d)):
            r = ns["judge"](d, u, g)
            if (u, g) == ("Face", "tee"):
                fr["neck_px"] = ns["neck_px"](d, r["_mask"])
            r.pop("_mask")
            fr[f"{u}>{g}"] = r
    worst = {}
    for shot, per in rep["shots"].items():
        for f, fr in (per.items() if isinstance(per, dict) else ()):
            for k, v in fr.items():
                if isinstance(v, dict) and "fraction" in v and v["fraction"] >= worst.get(k, (0, None))[0]:
                    worst[k] = (v["fraction"], f"{shot}@{f}")
    rep["worst"] = {k: {"fraction": v[0], "at": v[1]} for k, v in sorted(worst.items())}
    npx = [(fr["neck_px"]["px"], f"{shot}@{f}") for shot, per in rep["shots"].items()
           for f, fr in (per.items() if isinstance(per, dict) else ()) if isinstance(fr, dict) and "neck_px" in fr]
    if npx:
        rep["worst"]["neck_px"] = {"px": max(npx)[0], "at": max(npx)[1]}
    necks = [(fr["neck"]["out"], fr["neck"]["max_out_cm"], f"{shot}@{f}") for shot, per in rep["shots"].items()
             for f, fr in (per.items() if isinstance(per, dict) else ()) if isinstance(fr, dict) and "neck" in fr]
    if necks:
        rep["worst"]["neck"] = {"out": max(necks)[0], "max_out_cm": max(x[1] for x in necks), "at": max(necks)[2]}
    json.dump(rep, open(old, "w"), indent=1)
    print(json.dumps(rep["worst"]))


if __name__ == "__main__":
    main()
