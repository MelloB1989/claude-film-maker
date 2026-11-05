"""Her hair's teal ends on Linux 5.8 (round 3, gate c): an A/B of stills on S16 (--frame, f1236) through Reel_S16,
one per variant of the hair material (her MI_K_HerHair* instances, all three slots), of the hair cvars or of what is
behind the lengths (the overshirt hidden), each set, captured and put back (nothing saved):

    cd tools && uv run python ../films/host-studio/reel/hair_teal_ab.py --out /srv/ue/reel/r3/hair_ab --mode mrq

then the ends' hue against the crown, on the box (only hue.json and hue_sheet.jpg leave it):

    uv run --with pillow --with numpy python ../films/host-studio/reel/cast_gate.py hue /srv/ue/reel/r3/hair_ab \\
        --out /srv/ue/reel/r3/hair_ab/_hue

The material's parameter names are listed first (the run prints them): a variant whose names the material lacks is
reported, not silently a copy of the base.
"""
from __future__ import annotations

import argparse
import json

from filmtools.unreal import client

SEQ, CAM = "/Game/Reel/SEQ_Reel", "Reel_S16"
MIS = [f"/Game/Studio/Materials/MI_K_HerHair{s}" for s in ("", "_Cards", "_Helmet")]
VARIANTS = [
    {"name": "base"},
    # night1 (cc-64d05f6e): the material is neutral (hair_params.json: melanin 1.0, every dye white, no ombre), so
    # the green is light: the olive overshirt behind and under the lengths, seen through or bounced onto the strands
    {"name": "overshirt_hidden", "hide": ["Overshirt"]},
    # f1236 A/B (20:26): no change with the overshirt hidden or either lighting cvar, so the green strands are drawn
    # green. cast4 showed green CARDS: the cards/helmet geometry behind the strands, in the cards MIs. Black dye on
    # those only (mis: the MI names' ends) blacks them out without touching the strands' look
    {"name": "cards_helmet_black", "mis": ["_Cards", "_Helmet"], "vectors": {"hairDye": [0.0, 0.0, 0.0]}},
    {"name": "melanin_0.3", "scalars": {"hairMelanin": 0.3}},
    {"name": "redness_0.3", "scalars": {"hairRedness": 0.3}},
    {"name": "melanin_0.9", "scalars": {"hairMelanin": 0.9}},
    {"name": "white_light_0", "scalars": {"WhiteAmount": 0.0, "LightAmount": 0.0}},
    {"name": "rough_0.6", "scalars": {"HairRoughness": 0.6}},
    {"name": "dye_warm", "vectors": {"HairDye": [0.06, 0.035, 0.02]}},
    # which geometry draws the ends at S16's size: auto LOD (cvar 1) may pick cards, whose own texture carries colour;
    # manual (0) lets LODSync's pin (LOD 0, strands) decide; cards forced on shows what the cards look like
    {"name": "lodmode_manual", "cvars": {"r.HairStrands.LODMode": 0}},
    {"name": "cards_forced", "cvars": {"r.HairStrands.UseCardsInsteadOfStrands": 1}},
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
for p in [p for p in MIS if not V.get("mis") or any(p.endswith(x) for x in V["mis"])]:
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
her = next(x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
           if x.get_actor_label() == "Presenter")
old["hide"] = []
for c in her.get_components_by_class(unreal.PrimitiveComponent):
    if c.get_name() in V.get("hide", []):
        c.set_visibility(False, True)
        old["hide"].append(c.get_name())
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
her = next(x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
           if x.get_actor_label() == "Presenter")
for c in her.get_components_by_class(unreal.PrimitiveComponent):
    if c.get_name() in OLD.get("hide", []):
        c.set_visibility(True, True)
result = True
"""


LIGHTS = """
import unreal
out = []
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    for c in a.get_components_by_class(unreal.LightComponent):
        k = c.get_editor_property("light_color")
        r, g, b = k.r / 255, k.g / 255, k.b / 255
        p = c.get_world_location()
        out.append({"actor": a.get_actor_label(), "comp": c.get_name(), "cls": c.get_class().get_name(),
                    "rgb": [round(r, 3), round(g, 3), round(b, 3)], "green": round(g - max(r, b) / 2 - r / 2, 3),
                    "intensity": round(c.get_editor_property("intensity"), 3), "visible": c.is_visible(),
                    "temp_on": bool(c.get_editor_property("use_temperature")),
                    "temp": round(c.get_editor_property("temperature"), 0), "at": [round(p.x), round(p.y), round(p.z)]})
MEL = unreal.MaterialEditingLibrary
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    for c in a.get_components_by_class(unreal.MeshComponent):
        for i in range(c.get_num_materials()):
            m = c.get_material(i)
            if not isinstance(m, unreal.MaterialInstance):
                continue
            names = [str(n) for n in MEL.get_vector_parameter_names(m)]
            sc = {str(n): MEL.get_material_instance_scalar_parameter_value(m, n)
                  for n in MEL.get_scalar_parameter_names(m) if "emiss" in str(n).lower()}
            for n in names:
                if "emiss" not in n.lower() and not (sc and "color" in n.lower()):
                    continue
                k = MEL.get_material_instance_vector_parameter_value(m, n)
                strength = max(sc.values()) if sc else 1.0
                if max(k.r, k.g, k.b) * strength <= 0:
                    continue
                p = c.get_world_location()
                out.append({"actor": a.get_actor_label(), "comp": c.get_name(), "cls": "emissive:" + m.get_name(),
                            "param": n, "rgb": [round(k.r, 3), round(k.g, 3), round(k.b, 3)],
                            "green": round(k.g - k.r / 2 - k.b / 2, 3), "intensity": round(strength, 3),
                            "visible": c.is_visible(), "at": [round(p.x), round(p.y), round(p.z)]})
result = sorted(out, key=lambda x: -x["green"])[:60]
"""


def ok(res):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="a directory on the box for the stills")
    ap.add_argument("--mode", default="capture", help="view.still mode: capture (seconds) or mrq (the final look)")
    ap.add_argument("--frame", type=int, default=1236, help="S16's master frame (night1's green: 1236, 1300)")
    ap.add_argument("--only", default="", help="comma-separated variant names (default: all)")
    ap.add_argument("--lights", action="store_true", help="only list the level's lights and emissive MIs, greenest first (read-only)")
    a = ap.parse_args()
    if a.lights:
        print(json.dumps(ok(client.exec_code(LIGHTS)), indent=1))
        return
    names = ok(client.exec_code(f"MIS = {MIS!r}\n" + NAMES))
    have_s = set.intersection(*({x.lower() for x in n["scalars"]} for n in names.values()))  # FNames: any case
    have_v = set.intersection(*({x.lower() for x in n["vectors"]} for n in names.values()))
    rep = {"names": names, "stills": {}}
    for v in [v for v in VARIANTS if not a.only or v["name"] in a.only.split(",")]:
        missing = [k for k in v.get("scalars", {}) if k.lower() not in have_s] + [
            k for k in v.get("vectors", {}) if k.lower() not in have_v]
        if missing:
            rep["stills"][v["name"]] = {"skipped": f"the material has no {missing}"}
            continue
        old = ok(client.exec_code(f"MIS = {MIS!r}\nV = {v!r}\n" + SET))
        try:
            r = ok(client.op("view.still", out=f"{a.out}/{v['name']}.png", sequence=SEQ, frame=a.frame, camera=CAM,
                             width_px=960, height_px=540, mode=a.mode,
                             **({"level": "/Game/Studio/Studio"} if a.mode == "mrq" else {})))
            rep["stills"][v["name"]] = {"path": r["path"], "set": v}
        finally:
            ok(client.exec_code(f"OLD = {old!r}\n" + RESTORE))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
