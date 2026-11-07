"""agent-07: agent-02's Edge1N on her Top (component mesh swap, materials as worn), MCU f29 + CU f120 at finals spec,
3x crops + the band metric; the original Top goes back on after (until the orchestrator OKs the fix)."""
import json, sys, time
sys.path.insert(0, "../films/host-studio/explainers")
import render as R, set as S
from filmtools.unreal import client
S.client = client
S.guard("boxb", "i-0d7684b44eacf7043")
seq = S.SEQ["her"]
ORIG, FIX = "/Game/Host/Presenter_Outfit/SKM_Presenter_Top", "/Game/Host/Presenter_Outfit/SKM_Presenter_Top_Edge1N"
swap = """import unreal
from fmbridge.ops import level as L
c = next(c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == "Top")
mats = [c.get_material(i) for i in range(c.get_num_materials())]
c.set_skeletal_mesh_asset(unreal.load_asset({m!r}))
for i, m in enumerate(mats):
    c.set_material(i, m)
result = [c.get_skeletal_mesh_asset().get_name(), [m.get_name() for m in mats]]"""
jobs = [("CAM_MCU", 0, 30, "MCU", 29), ("CAM_CU", 98, 121, "CU", 120)]
try:
    print("swap", S.ex(swap.format(m=FIX)))
    S.op("mh.leader", label="Presenter")
    print("leaders", S.op("mh.leader_check", label="Presenter").get("pass"))
    for cam, f0, f1, tag, fr in jobs:
        S.op("seq.camera_cuts", path=seq, cuts=[[cam, 0]])
        sp = R.spec("her", "netflix", 1, cam, f0, f1, "final")
        sp.update(out_dir=f"/srv/ue/explainer/renders/netflix/fix_edge1n/{tag}", name=f"exp_fix_{tag}", overwrite=True)
        t = time.time(); rep = S.ok(client.op("render.job", timeout=3600, spec=sp))
        print(tag, rep.get("status"), rep.get("frames"), f"{time.time() - t:.0f} s")
finally:
    print("restore", S.ex(swap.format(m=ORIG)))
    S.op("mh.leader", label="Presenter")
    e = json.load(open("../films/host-studio/explainers/edl/netflix.json"))
    S.op("seq.camera_cuts", path=seq, cuts=S.edl_cuts(e))
print(S.ex("""import subprocess, os
D = "/srv/ue/explainer/renders/netflix/fix_edge1n"; O = "/srv/ue/explainer/review/strip"
os.makedirs(O, exist_ok=True)
rc = [subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{D}/MCU/0029.png", "-vf",
                      "crop=240:300:960:560,scale=720:900:flags=neighbor", f"{O}/her_MCU_f0029_edge1N_crop3x.png"]).returncode]
for t, f in (("MCU", "0029"), ("CU", "0120")):
    rc.append(subprocess.run(["cp", f"{D}/{t}/{f}.png", f"{O}/her_{t}_f{f}_edge1N_full.png"]).returncode)
r = subprocess.run(["aws", "s3", "cp", "--recursive", "--sse", "aws:kms", "--only-show-errors", O,
                    "s3://rf-render-788655295054-aps1/ue-linux/private/renders/r6/review/explain_her/strip/"], capture_output=True, text=True)
result = [rc, r.returncode]"""))
