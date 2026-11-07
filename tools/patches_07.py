"""agent-07: grain patch boxes (frame fractions) for her frames, by projection through each shot camera at its frame:
the desk top just in front of her hands, the plaster wall right of the shelves, her neck shadow under the jaw."""
import json, sys
sys.path.insert(0, "../films/host-studio/explainers")
import set as S
from filmtools.unreal import client
S.client = client
S.guard("boxb", "i-0d7684b44eacf7043")
seq = S.SEQ["her"]
out = {}
for tag, cam, fr in (("test29", "CAM_MCU", 29), ("f300", "CAM_WIDE", 300), ("mcu1330", "CAM_MCU", 1330)):
    S.op("seq.scrub", path=seq, frame=fr)
    b = S.op("level.bone", label="Presenter", component="Body", bones=["hand_l", "hand_r", "neck_01"])
    f = S.op("level.bone", label="Presenter", component="Face", bones=["FACIAL_C_Jaw", "FACIAL_C_LipLower"])
    hx = (b["hand_l"][0] + b["hand_r"][0]) / 2 + 7.0
    hy = (b["hand_l"][1] + b["hand_r"][1]) / 2
    pts = {"desk_a": [hx, hy - 4, 71.2], "desk_b": [hx + 6, hy + 4, 71.2],
           "wall_a": [-258, -232, 150], "wall_b": [-258, -248, 128],
           "neck_a": [b["neck_01"][0] + 6.5, b["neck_01"][1] + 2.5, b["neck_01"][2] + 1.0],
           "neck_b": [b["neck_01"][0] + 6.0, b["neck_01"][1] - 2.5, b["neck_01"][2] - 2.0]}
    pr = S.op("cam.project", camera=cam, points=pts)["points"]
    box = {}
    for k in ("desk", "wall", "neck"):
        us = [pr[f"{k}_a"]["u"], pr[f"{k}_b"]["u"]]; vs = [pr[f"{k}_a"]["v"], pr[f"{k}_b"]["v"]]
        pad = 0.012
        box[k] = [round(min(us) - pad, 4), round(min(vs) - pad, 4), round(max(us) + pad, 4), round(max(vs) + pad, 4)]
    out[tag] = {"camera": cam, "frame": fr, "patches": box}
print(json.dumps(out))
