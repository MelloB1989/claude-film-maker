"""Bind an mp2mh build on the box (docs/MOCAP_PILOT.md): push the doc (gesturekit.build's own format, as perform.py's
BODY job writes it), write it as an AnimSequence on her body mesh (the mesh path read on the box, as BODY does),
and optionally put it on the Body track of a sequence (normally a scratch copy) from frame 0. The Face track is left as
it is. It goes through perform.py's own client, push and run, so the box, its kit dir and its token are perform's.

    python -m filmtools.mocap.bind DOC.json --kit <r7 checkout>/films/host-studio/explainers [--who her] \
        [--name kling_t1] [--seq /Game/.../SEQ_scratch] [--life]

The anim: /Game/Explainer/Perf/AS_exp_<who>_mocap_<name>. --life also adds her life layer (AS_exp_<who>_life) on row 2,
as cmd_place does.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WRITE = r"""
import json, unreal
from fmbridge.ops.anim import model_keys, new as anim_new
from fmbridge.ops.perf_body import _write_tracks
P = json.loads(PARAMS)
def job():
    g = {"PARAMS": json.dumps({"label": P["label"], "idle": P["idle"], "world": P["world"]})}
    exec(P["read"], g)  # perform.READ: the skeleton read on the box, for its mesh path
    data = g["result"]
    doc = json.loads(open(P["doc"]).read())
    yield
    anim_new(path=P["out"], skeleton=data["mesh"], length_s=doc["length_s"], fps=doc["fps"], replace=True)
    a = unreal.load_asset(P["out"])
    n = model_keys(a)
    tracks = {b: [(v["t"], v["q"], v["s"])] * n for b, v in doc["const"].items()}
    for b, ks in doc["keyed"].items():
        if len(ks) != n:
            ks = [ks[min(len(ks) - 1, int(round(i * (len(ks) - 1) / max(1, n - 1))))] for i in range(n)]
        tracks[b] = [(k["t"], k["q"], k["s"]) for k in ks]
    yield
    _write_tracks(a, tracks, n)
    unreal.EditorAssetLibrary.save_asset(P["out"])
    return {"written": True, "out": P["out"], "keys": n, "bones": len(tracks), "mesh": data["mesh"]}
result = job()
"""


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("doc")
    ap.add_argument("--kit", required=True)
    ap.add_argument("--who", default="her")
    ap.add_argument("--name", default="mocap")
    ap.add_argument("--seq", help="a sequence to put it on (Body track, from frame 0); a scratch copy, never SEQ_<who>")
    ap.add_argument("--life", action="store_true", help="her life layer on row 2 as well")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(a.kit).resolve()))
    import perform as PF  # noqa: E402
    doc = json.loads(Path(a.doc).read_text())
    remote = PF.box(a.who, "kit", f"mocap_{a.name}.doc.json")
    PF.client().push(str(Path(a.doc).resolve()), remote)
    out = f"{PF.ANIM}/AS_exp_{a.who}_mocap_{a.name}"
    r = PF.run(WRITE, {"read": PF.READ, "label": PF.LABEL[a.who], "idle": PF.IDLE, "world": PF.WORLD_BONES,
                       "doc": remote, "out": out}, 1800)
    res = {"write": r}
    if a.seq:
        if a.seq == PF.SEQ.get(a.who):
            raise SystemExit(f"{a.seq} is her sequence of record: bind to a scratch copy")
        n = int(doc.get("n_keys") or round(doc["length_s"] * doc["fps"]) + 1)  # every key: frames 0..n-1 (agent-06:
        #   [0, length*fps) left the last key, frame 240 of a 10 s take, past the section)
        secs = [{"anim": out, "start": 0, "end": n, "loop": False}]
        if a.life:
            secs.append({"anim": f"{PF.ANIM}/AS_exp_{a.who}_life", "start": 0, "end": n, "loop": False, "row": 2})
        res["place"] = PF.ok(PF.client().op("seq.anim", path=a.seq, label=PF.LABEL[a.who], component="Body",
                                           sections=secs))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
