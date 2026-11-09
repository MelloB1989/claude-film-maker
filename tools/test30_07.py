"""agent-07: the orchestrator's pre-batch check — the FIRST 30 frames of her MCU (shot 1) with the finals' exact spec,
guarded, then f29 full-res to private review. Run from the tree's tools/ with FILM_UE_BOX=boxb."""
import json, os, sys, time
sys.path.insert(0, "../films/host-studio/explainers")
import render as R, set as S
from filmtools.unreal import client
S.client = client
S.guard("boxb", "i-0d7684b44eacf7043")
seq = S.SEQ["her"]
S.op("seq.camera_cuts", path=seq, cuts=[["CAM_MCU", 0]])
try:
    S.op("mh.leader", label="Presenter")
    g = S.guard_scene("her", "CAM_MCU", 15)
    print("guard", g)
    if not g["ok"]:
        raise SystemExit("guard failed")
    sp = R.spec("her", "netflix", 1, "CAM_MCU", 0, 30, "final")
    sp["out_dir"] = "/srv/ue/explainer/renders/netflix/test30/shot01_CAM_MCU"
    sp["name"] = "exp_netflix_test30_shot01_CAM_MCU"
    t = time.time()
    rep = S.ok(client.op("render.job", timeout=3600, spec=sp))
    print("render", rep.get("status"), rep.get("frames"), f"{time.time() - t:.0f} s")
finally:
    e = json.load(open("../films/host-studio/explainers/edl/netflix.json"))
    S.op("seq.camera_cuts", path=seq, cuts=S.edl_cuts(e))
print(S.ex("""import subprocess
r = subprocess.run(["aws", "s3", "cp", "--sse", "aws:kms", "--only-show-errors",
    "/srv/ue/explainer/renders/netflix/test30/shot01_CAM_MCU/0029.png",
    "s3://rf-render-788655295054-aps1/ue-linux/private/renders/r6/review/explain/r6c/her_test30_CAM_MCU_f0029.png"],
    capture_output=True, text=True)
result = [r.returncode, r.stderr[-200:]]"""))
