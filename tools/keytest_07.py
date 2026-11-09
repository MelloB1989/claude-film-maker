"""agent-07: is her neckline band the key light's shadow? MCU f29 at finals spec with ExpKey's cast_shadows off (temp)."""
import json, sys, time
sys.path.insert(0, "../films/host-studio/explainers")
import render as R, set as S
from filmtools.unreal import client
S.client = client
S.guard("boxb", "i-0d7684b44eacf7043")
seq = S.SEQ["her"]
S.op("seq.camera_cuts", path=seq, cuts=[["CAM_MCU", 0]])
try:
    S.op("level.set", label="ExpKey", component="RectLightComponent", props={"cast_shadows": False})
    S.op("mh.leader", label="Presenter")
    sp = R.spec("her", "netflix", 1, "CAM_MCU", 0, 30, "final")
    sp.update(out_dir="/srv/ue/explainer/renders/netflix/diag_keynoshadow/shot01_CAM_MCU", name="exp_diag_keyns", overwrite=True)
    rep = S.ok(client.op("render.job", timeout=3600, spec=sp)); print("render", rep.get("status"), rep.get("frames"))
finally:
    S.op("level.set", label="ExpKey", component="RectLightComponent", props={"cast_shadows": True})
    e = json.load(open("../films/host-studio/explainers/edl/netflix.json"))
    S.op("seq.camera_cuts", path=seq, cuts=S.edl_cuts(e))
    print("key shadows back:", S.ex("from fmbridge.ops import level as L\nimport unreal\nresult = L.actor('ExpKey').get_component_by_class(unreal.RectLightComponent).cast_shadows"))
