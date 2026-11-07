"""agent-07: shot.grain for her final jobs — first and last frame of each, flat patches projected through that shot's
camera at that frame (wall plaster right of the shelves; her neck shadow under the jaw; the desk top in front of her
hands where it is in frame). Writes patches JSON for the box-side qa_av grain run. Usage: grainjob.py n,cam,f0,f1 ..."""
import json, sys
sys.path.insert(0, "../films/host-studio/explainers")
import set as S
from filmtools.unreal import client
S.client = client
S.guard("boxb", "i-0d7684b44eacf7043")
seq = S.SEQ["her"]
out = {}
for arg in sys.argv[1:]:
    n, cam, f0, f1 = arg.split(",")
    for fr in (int(f0), int(f1) - 1):
        S.op("seq.scrub", path=seq, frame=fr)
        b = S.op("level.bone", label="Presenter", component="Body", bones=["hand_l", "hand_r", "neck_01"])
        hx = (b["hand_l"][0] + b["hand_r"][0]) / 2 + 7.0
        hy = (b["hand_l"][1] + b["hand_r"][1]) / 2
        nk = b["neck_01"]
        pts = {"desk_a": [hx, hy - 4, 71.2], "desk_b": [hx + 6, hy + 4, 71.2],
               "wall_a": [-258, -232, 150], "wall_b": [-258, -248, 128],
               "neck_a": [nk[0] + 6.5, nk[1] + 2.5, nk[2] + 1.0], "neck_b": [nk[0] + 6.0, nk[1] - 2.5, nk[2] - 2.0]}
        pr = S.op("cam.project", camera=cam, points=pts)["points"]
        box = {}
        for k in ("desk", "wall", "neck"):
            us = [pr[f"{k}_a"]["u"], pr[f"{k}_b"]["u"]]; vs = [pr[f"{k}_a"]["v"], pr[f"{k}_b"]["v"]]
            bx = [min(us) - 0.012, min(vs) - 0.012, max(us) + 0.012, max(vs) + 0.012]
            if bx[0] >= 0 and bx[1] >= 0 and bx[2] <= 1 and bx[3] <= 1:
                box[k] = [round(x, 4) for x in bx]
        out[f"shot{int(n):02d}_{cam}/{fr:04d}.png"] = box
print(json.dumps(out))
