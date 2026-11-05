"""Her hair's teal ends on Linux 5.8 (round 3, gate c): an A/B of stills on S16 f1280 through Reel_S16, one per
variant of the hair material (her MI_K_HerHair* instances, all three slots) or of the hair cvars, each set, captured
and put back (nothing saved). agent-09 measures the ends' colour against the roots (cast_gate.py's HAIR boxes).

    cd tools && uv run python ../films/host-studio/reel/hair_teal_ab.py --out /srv/ue/reel/r3/hair_ab [--mode capture|mrq]

The material's parameter names are listed first (the run prints them): a variant whose names the material lacks is
reported, not silently a copy of the base.
"""
from __future__ import annotations

import argparse
import json

from filmtools.unreal import client

SEQ, CAM, FRAME = "/Game/Reel/SEQ_Reel", "Reel_S16", 1280
MIS = [f"/Game/Studio/Materials/MI_K_HerHair{s}" for s in ("", "_Cards", "_Helmet")]
VARIANTS = [
    {"name": "base"},
    {"name": "redness_0.3", "scalars": {"hairRedness": 0.3}},
    {"name": "melanin_0.9", "scalars": {"hairMelanin": 0.9}},
    {"name": "white_light_0", "scalars": {"WhiteAmount": 0.0, "LightAmount": 0.0}},
    {"name": "rough_0.6", "scalars": {"HairRoughness": 0.6}},
    {"name": "dye_warm", "vectors": {"HairDye": [0.06, 0.035, 0.02]}},
    {"name": "no_scatter_scene", "cvars": {"r.HairStrands.ScatterSceneLighting": 0}},
    {"name": "no_lumen_hair", "cvars": {"r.Lumen.HairStrands.LightingMode": 0, "r.HairStrands.Lumen": 0}},
    {"name": "no_multiscatter", "cvars": {"r.HairStrands.SkyLighting.IntegrationType": 0,
                                          "r.HairStrands.DeepShadow.Enable": 0}},
]

NAMES = """
import unreal
MEL = unreal.MaterialEditingLibrary
result = {p: {"scalars": [str(n) for n in MEL.get_scalar_parameter_names(unreal.load_asset(p))],
              "vectors": [str(n) for n in MEL.get_vector_parameter_names(unreal.load_asset(p))]} for p in MIS}
"""

SET = """
import unreal
MEL, SL = unreal.MaterialEditingLibrary, unreal.SystemLibrary
w = unreal.EditorLevelLibrary.get_editor_world()
old = {"scalars": {}, "vectors": {}, "cvars": {}}
for p in MIS:
    mi = unreal.load_asset(p)
    for k, v in V.get("scalars", {}).items():
        old["scalars"].setdefault(p, {})[k] = MEL.get_material_instance_scalar_parameter_value(mi, k)
        MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
    for k, v in V.get("vectors", {}).items():
        c = MEL.get_material_instance_vector_parameter_value(mi, k)
        old["vectors"].setdefault(p, {})[k] = [c.r, c.g, c.b, c.a]
        MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v, 1.0))
    MEL.update_material_instance(mi)
for k, v in V.get("cvars", {}).items():
    old["cvars"][k] = SL.get_console_variable_float_value(k)
    SL.execute_console_command(w, f"{k} {v}")
result = old
"""

RESTORE = """
import unreal
MEL, SL = unreal.MaterialEditingLibrary, unreal.SystemLibrary
w = unreal.EditorLevelLibrary.get_editor_world()
for p, d in OLD["scalars"].items():
    mi = unreal.load_asset(p)
    for k, v in d.items():
        MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
    MEL.update_material_instance(mi)
for p, d in OLD["vectors"].items():
    mi = unreal.load_asset(p)
    for k, v in d.items():
        MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v))
    MEL.update_material_instance(mi)
for k, v in OLD["cvars"].items():
    SL.execute_console_command(w, f"{k} {v}")
result = True
"""


def ok(res):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="a directory on the box for the stills")
    ap.add_argument("--mode", default="capture", help="view.still mode: capture (seconds) or mrq (the final look)")
    a = ap.parse_args()
    names = ok(client.exec_code(f"MIS = {MIS!r}\n" + NAMES))
    have_s = set.intersection(*({x.lower() for x in n["scalars"]} for n in names.values()))  # FNames: any case
    have_v = set.intersection(*({x.lower() for x in n["vectors"]} for n in names.values()))
    rep = {"names": names, "stills": {}}
    for v in VARIANTS:
        missing = [k for k in v.get("scalars", {}) if k.lower() not in have_s] + [
            k for k in v.get("vectors", {}) if k.lower() not in have_v]
        if missing:
            rep["stills"][v["name"]] = {"skipped": f"the material has no {missing}"}
            continue
        old = ok(client.exec_code(f"MIS = {MIS!r}\nV = {v!r}\n" + SET))
        try:
            r = ok(client.op("view.still", out=f"{a.out}/{v['name']}.png", sequence=SEQ, frame=FRAME, camera=CAM,
                             width_px=960, height_px=540, mode=a.mode,
                             **({"level": "/Game/Studio/Studio"} if a.mode == "mrq" else {})))
            rep["stills"][v["name"]] = {"path": r["path"], "set": v}
        finally:
            ok(client.exec_code(f"OLD = {old!r}\n" + RESTORE))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
