"""agent-07: her neckline band split — MCU f29 at finals spec with her Top as is, then on TEMP children of MI_K_HerTop:
white (Tex → engine white, Color 1) and flatnormal (Normal → engine default normal); component override only, put
back after; 3x crops x960-1200 y560-860 → private review/explain_her/strip/."""
import json, sys, time
sys.path.insert(0, "../films/host-studio/explainers")
import render as R, set as S
from filmtools.unreal import client
S.client = client
S.guard("boxb", "i-0d7684b44eacf7043")
seq = S.SEQ["her"]
TOP = "/Game/Studio/Materials/MI_K_HerTop"
VAR = {"white": {"Tex": "/Engine/EngineResources/WhiteSquareTexture", "Color": [1.0, 1.0, 1.0, 1.0]},
       "flatnormal": {"Normal": "/Engine/EngineMaterials/DefaultNormal"}}
swap = """import unreal
from fmbridge.ops import level as L
c = next(c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == "Top")
i = c.get_material_index("M_Top")
c.set_material(i, unreal.load_asset({mi!r}))
result = [i, c.get_material(i).get_path_name()]"""
variants = sys.argv[1:] or ["asis", "white", "flatnormal"]
S.op("seq.camera_cuts", path=seq, cuts=[["CAM_MCU", 0]])
try:
    for v in variants:
        mi = TOP
        if v != "asis":
            mi = f"/Game/Explainer/Materials/MI_Exp_HerTop_Diag_{v}"
            S.op("mat.instance", path=mi, parent=TOP, params=VAR[v])
        print(v, S.ex(swap.format(mi=mi)))
        S.op("mh.leader", label="Presenter")
        sp = R.spec("her", "netflix", 1, "CAM_MCU", 0, 30, "final")
        sp.update(out_dir=f"/srv/ue/explainer/renders/netflix/diag_{v}/shot01_CAM_MCU", name=f"exp_diag_{v}", overwrite=True)
        t = time.time(); rep = S.ok(client.op("render.job", timeout=3600, spec=sp))
        print(v, rep.get("status"), rep.get("frames"), f"{time.time() - t:.0f} s")
finally:
    print("restore", S.ex(swap.format(mi=TOP)))
    S.op("mh.leader", label="Presenter")
    e = json.load(open("../films/host-studio/explainers/edl/netflix.json"))
    S.op("seq.camera_cuts", path=seq, cuts=S.edl_cuts(e))
print(S.ex(f"""import subprocess, os
os.makedirs("/srv/ue/explainer/review/strip", exist_ok=True)
rc = []
for v in {variants!r}:
    src = f"/srv/ue/explainer/renders/netflix/diag_{{v}}/shot01_CAM_MCU/0029.png"
    dst = f"/srv/ue/explainer/review/strip/her_MCU_f0029_{{v}}_crop3x.png"
    rc.append(subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf",
                              "crop=240:300:960:560,scale=720:900:flags=neighbor", dst]).returncode)
r = subprocess.run(["aws", "s3", "cp", "--recursive", "--sse", "aws:kms", "--only-show-errors", "/srv/ue/explainer/review/strip",
                    "s3://rf-render-788655295054-aps1/ue-linux/private/renders/r6/review/explain_her/strip/"], capture_output=True, text=True)
result = [rc, r.returncode, r.stderr[-200:]]"""))
