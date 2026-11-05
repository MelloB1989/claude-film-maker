"""The presenters' bodies: MetaHuman Creator's parametric body by measurement constraints (cm; Fat, Muscularity and
Masculine/Feminine unitless), then Epic's cloud rig and the cinematic build into the Blueprints the studio places
(/Game/Host/Unpacked/<name>/BP_<name>). Faces, skin and grooms are not touched. None frees a constraint.

    cd tools && uv run python ../films/host-studio/bodies.py [--who him,her] [--no-build]

Afterwards rerun unreal/studio.py (it respawns her and re-dresses both) and check them with bodycheck.py.
"""
from __future__ import annotations

import argparse
import json
import time

from filmtools.unreal import client

from stills import ok

BODIES = {
    # him: a fit, athletic man; a V-taper (shoulders and chest well over the waist), defined arms, no gut
    "him": ("/Game/Host/Host_Trey", "Host", {
        "Height": 182, "Across Shoulder": 46.5, "Front Interscye Length": 42, "Chest": 108, "Underbust": None,
        "Waist": 74, "High Hip": 80, "Hip": 92, "Neck Base": 41, "Neck": 38.5, "Bicep": 35.5, "Forearm": 29,
        "Thigh": 56, "Knee": 34, "Calf": 37, "Fat": -2.8, "Muscularity": 1.6, "Masculine/Feminine": -1.6}),
    # op (round 3): the operator's MetaHuman, replacing him in the Host role. 180 cm, fit: lean-athletic in a tee, NOT
    # bulky (the round-2 note on his over-built chest still says what to avoid): shoulders over the waist without a
    # pronounced V, a flat stomach, natural arms. The face comes from the operator's capture (identity), not from here.
    "op": ("/Game/Host/Host_Op", "Host", {
        "Height": 180, "Across Shoulder": 45, "Front Interscye Length": 40, "Chest": 100, "Underbust": None,
        "Waist": 79, "High Hip": 85, "Hip": 95, "Neck Base": 40, "Neck": 38, "Bicep": 31.5, "Forearm": 27.5,
        "Thigh": 54, "Knee": 37, "Calf": 36.5, "Fat": -1.4, "Muscularity": 0.7, "Masculine/Feminine": -1.5}),
    # her: slim and clearly feminine; a defined bust over a narrow waist, curved hips, slender arms and shoulders
    "her": ("/Game/Host/Presenter_F", "Presenter", {
        "Height": 168, "Across Shoulder": 33, "Front Interscye Length": 31, "Chest": 94, "Bust Span": 19.5,
        "Shoulder to Apex": 25.5, "Underbust": 70, "Waist": 61, "High Hip": 76, "Hip": 94, "Neck Base": 34,
        "Neck": 31.6, "Neck to Waist": 35.5, "Bicep": 23, "Forearm": 19.5, "Thigh": 50, "Calf": 33, "Fat": -1.8,
        "Muscularity": 0.0, "Masculine/Feminine": 1.9}),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="him,her")
    ap.add_argument("--no-build", action="store_true", help="only set the constraints")
    a = ap.parse_args()
    for who in a.who.split(","):
        char, name, m = BODIES[who]
        print(who, json.dumps(ok(client.op("mh.body", character=char, measurements=m))))
        if a.no_build:
            continue
        for step, args in (("mh.rig", {"character": char}), ("mh.build", {"character": char, "name": name})):
            t0 = time.time()
            print(step, ok(client.op(step, timeout=3600, **args)), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
