"""The explainers' presenter shots as film-farm jobs: the same renders as explainers/render.py (one folder per shot,
shot<NN>_<CAM>/<frame>.png with SEQUENCE frame numbers, ±6 handles, the round-6 final settings), but split over the
farm's boxes. Every chunk runs the round-6 guards first on its own fresh editor (hook below): the cut track set to
the shot's camera alone, mh.leader, then agent-06's guard (no Test_*/FMQA_* or second presenter, leaders == Body,
her face lit through the camera). The guard's numbers go into the chunk's done.json for the gates.

    python films/host-studio/farm/explainer.py --who her --edl films/host-studio/explainers/edl/netflix.json \
        --film netflix --preset final --out /tmp/jobs [--shots 1,2]
    for j in /tmp/jobs/*.json; do film-farm submit FARM "$j"; done

Face rule: every frame has a presenter in it: private, ue-linux/private/ only (validation refuses anything else).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPLAINERS = HERE.parent / "explainers"

LEVELS = {"her": "/Game/Explainer/ExplainerSet", "him": "/Game/Explainer/ExplainerSet_Him"}
SEQ = {"her": "/Game/Explainer/SEQ_Explain_Her", "him": "/Game/Explainer/SEQ_Explain_Him"}
ACTOR = {"her": "Presenter", "him": "Host"}
OUT = "s3://rf-render-788655295054-apne1/ue-linux/private/renders/r7/farm/explain"  # private Tokyo bucket (cost ruling)
# explainers/render.py's (round 6b, box B's V2 finals)
CVARS = {"r.SSS.Quality": 1, "r.SSS.HalfRes": 0, "r.HairStrands.LODMode": 0, "r.HairStrands.AutoLOD.Bias": 1.0,
         "r.HairStrands.UseCardsInsteadOfStrands": 0, "r.HairStrands.SkyLighting": 0,
         "r.Streaming.FullyLoadUsedTextures": 1, "r.Streaming.PoolSize": 12000}
PRESETS = {
    "preview": {"preset": "preview", "spatial": 1, "temporal": 2, "width": 1920, "height": 1080, "warmup_render": 16},
    "final": {"preset": "final", "spatial": 4, "temporal": 8, "width": 1920, "height": 1080, "aa_method": "none",
              "warmup_render": 24},
}

# run on the worker before every chunk (film-farm's ue "hook"): op(name, **args) is the box's bridge
HOOK = r'''
def state_of(job):
    """What this worker renders from (agent-09's shot.farm_state_parity): the id in the project sync's STATE.json
    (agent-06 writes it at the root of the pushed project delta), else the box's AMI."""
    import json, os, urllib.request
    for s in job["ue"].get("sync") or []:
        p = os.path.join(s["local"], "STATE.json")
        if os.path.exists(p):
            return "sync:" + str(json.load(open(p)).get("id"))
    try:
        tok = urllib.request.urlopen(urllib.request.Request(
            "http://169.254.169.254/latest/api/token", method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"}), timeout=2).read().decode()
        return "ami:" + urllib.request.urlopen(urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/ami-id", headers={"X-aws-ec2-metadata-token": tok}),
            timeout=2).read().decode()
    except Exception as e:
        return "unknown:" + type(e).__name__


def before_chunk(op, job, chunk):
    a = job["ue"]["hook_args"]
    state, want = state_of(job), a.get("expect_state")
    if want and state != want:  # a stale sync or the wrong image: refuse before any render time is spent
        return {"ok": False, "why": "state %s != expected %s" % (state, want), "state": state}
    actor, cam, seq = a["actor"], a["camera"], a["sequence"]
    op("seq.camera_cuts", path=seq, cuts=[[cam, 0]])        # this shot's camera alone (in memory: never saved)
    op("mh.leader", label=actor)                            # leaders are lost on every editor start
    bad = [lab for lab, cls, _ in op("level.actors")
           if lab.startswith(("Test_", "FMQA_")) or (("BP_Host" in cls or "BP_Presenter" in cls) and lab != actor)]
    lead = op("mh.leader_check", label=actor)
    out = {"strays": bad, "leaders_ok": int(bool(lead.get("pass"))), "state": state}
    frame = (max(chunk["start"], chunk["render_from"]) + chunk["end"]) // 2
    path = "/srv/farm/_guard/%s_%s_f%04d.png" % (job["id"], cam, frame)
    op("seq.scrub", path=seq, frame=frame)
    eyes = op("level.bone", label=actor, component="Face",
              bones=["FACIAL_L_Eye", "FACIAL_R_Eye", "FACIAL_C_LipLower"])
    pts = op("cam.project", camera=cam, points=dict(eyes.items()))["points"]
    us, vs = [p["u"] for p in pts.values()], [p["v"] for p in pts.values()]
    box = [max(0.0, min(us) - 0.01), max(0.0, min(vs) - 0.01), min(1.0, max(us) + 0.01), min(1.0, max(vs) + 0.02)]
    op("seq.still", path=seq, frame=frame, camera=cam, out=path, width=960, height=540, settle=24)
    face = op("qa.exposure", image=path, regions={"face": box})["metrics"]["regions"]["face"]["mean"]
    out.update(face_luma=round(face, 1), face_ok=int(50 <= face <= 230), guard_frame=frame)
    out["ok"] = bool(not bad and out["leaders_ok"] and out["face_ok"])
    out["why"] = "; ".join(w for w, c in (("strays " + ",".join(bad), bad), ("leaders", not out["leaders_ok"]),
                                           ("face luma %s" % out["face_luma"], not out["face_ok"])) if c)
    return out
'''


def shot_camera(s: dict) -> str:
    """explainers/set.py's: agent-11's PANEL shots (her in the left half, a graphic panel on the right) use CAM_MCU_L;
    graphics shots have none."""
    cam = s.get("camera")
    if not cam or s.get("kind") == "gfx":
        return ""
    return "CAM_MCU_L" if s.get("kind") == "panel" and cam == "CAM_MCU" else cam


def render_plan(edl: dict, handles: int = 6) -> list:
    """Every presenter shot as [n, camera, first, end) with ±handles, clamped (explainers/set.py's)."""
    end = int(edl.get("frames") or max(s["f1"] for s in edl["shots"]))
    return [[s["n"], shot_camera(s), max(0, s["f0"] - handles), min(end, s["f1"] + handles)]
            for s in edl["shots"] if shot_camera(s)]


def jobs(who: str, film: str, edl: dict, preset: str, chunk: int = 96, preroll: int = 24, sync: list | None = None,
         state: str = "") -> list:
    out = []
    for n, cam, f0, f1 in render_plan(edl):
        spec = {"sequence": SEQ[who], "level": LEVELS[who], "preroll": "cut", "warmup_engine": 22,
                "shutter_timing": "open", "zero_pad": 4, "cvars": CVARS, **PRESETS[preset]}
        out.append({
            "id": f"{film}-{preset}-s{n:02d}-{cam.lower().replace('_', '-')}"[:48],
            "engine": "ue", "frames": [f0, f1], "cuts": [], "chunk": chunk, "preroll": preroll,
            "privacy": "private", "presenter": True,
            "output": {"prefix": f"{OUT}/{film}/{preset}/shot{n:02d}_{cam}/", "ext": "png", "pad": 4, "fps": 24},
            "ue": {"spec": spec, "fresh_editor": True, "wait_compile": True, "stall_s": 900, "sync": sync or [],
                   "hook": HOOK, "hook_args": {"actor": ACTOR[who], "camera": cam, "sequence": SEQ[who],
                                                "expect_state": state}},
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--who", required=True, choices=sorted(ACTOR))
    ap.add_argument("--edl", required=True)
    ap.add_argument("--film", required=True)
    ap.add_argument("--preset", default="final", choices=sorted(PRESETS))
    ap.add_argument("--shots", help="only these shot numbers (comma list)")
    ap.add_argument("--chunk", type=int, default=96)
    ap.add_argument("--sync", action="append", default=[], metavar="S3=LOCAL",
                    help="a delta to sync onto each box first (repeat), e.g. "
                         "s3://B/ue-linux/private/project/HostStudio=/srv/ue/projects/HostStudio")
    ap.add_argument("--state", default="", help="the passed scene state every chunk must render: sync:<STATE.json id> "
                    "or ami:<id> (the hook refuses a chunk on any other)")
    ap.add_argument("--out", required=True, help="folder for the job files")
    a = ap.parse_args()
    edl = json.loads(Path(a.edl).read_text())
    sync = [{"s3": x.split("=", 1)[0], "local": x.split("=", 1)[1]} for x in a.sync]
    js = jobs(a.who, a.film, edl, a.preset, a.chunk, sync=sync, state=a.state)
    if a.shots:
        keep = {int(x) for x in a.shots.split(",")}
        js = [j for j, (n, *_r) in zip(js, render_plan(edl)) if n in keep]
    Path(a.out).mkdir(parents=True, exist_ok=True)
    for j in js:
        (Path(a.out) / f"{j['id']}.json").write_text(json.dumps(j, indent=1) + "\n")
        print(j["id"], j["frames"], j["output"]["prefix"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
