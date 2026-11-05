"""Read-only probe for her hair's green/teal ends on Linux (round 3 preview, S16 f1217/f1277): v2 fixed them with
studio.py's MI_K_HerHair* (children of the preset's MI_WI_Hair_L_Straight_Hair*, hairMelanin 1.0, hairRedness 0.05),
set only if the parent loads. Lists the Presenter's Hair groom materials per slot, whether the parents and the
MI_K_HerHair* exist, what else is in her Grooms folder, and the melanin/redness each slot's material has. Changes
nothing.

    film-ue exec films/host-studio/reel/hair_look_probe.py
"""
import unreal

GROOMS = "/Game/Host/Unpacked/Presenter/Grooms"
PARENTS = [f"{GROOMS}/MI_WI_Hair_L_Straight_Hair{s}" for s in ("", "_Cards", "_Helmet")]
EAL = unreal.EditorAssetLibrary


def _try(f):
    try:
        v = f()
        return v if isinstance(v, (bool, int, float, str, type(None), list, dict)) else str(v)
    except Exception as e:  # noqa: BLE001 - a probe: report what fails
        return f"ERR {type(e).__name__}: {e}"[:200]


def _scalars(mi):
    out = {}
    for n in ("hairMelanin", "hairRedness", "HairRoughness", "hairDye"):
        out[n] = _try(lambda: unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(mi, n))
    return out


out = {"parents": {p: EAL.does_asset_exist(p) for p in PARENTS},
       "k_hair": {}, "grooms_folder": _try(lambda: sorted(EAL.list_assets(GROOMS, recursive=False))[:40]),
       "her_hair_mis": _try(lambda: sorted(a for a in EAL.list_assets("/Game", recursive=True)
                                            if "MI_K_HerHair" in a)[:10]),
       "hair": None}
for a in out["her_hair_mis"] if isinstance(out["her_hair_mis"], list) else []:
    mi = unreal.load_asset(a)
    out["k_hair"][a] = {"parent": _try(lambda: mi.get_editor_property("parent").get_path_name()),
                        **_scalars(mi)}
acts = [a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
        if a.get_actor_label() == "Presenter"]
if acts:
    for c in acts[0].get_components_by_class(unreal.GroomComponent):
        if c.get_name() != "Hair":
            continue
        ga = c.get_editor_property("groom_asset")
        h = {"component": c.get_path_name(), "asset": ga.get_path_name() if ga else None, "slots": []}
        n = _try(lambda: c.get_num_materials())
        for i in range(n if isinstance(n, int) else 0):
            m = c.get_material(i)
            row = {"slot": i, "material": m.get_path_name() if m else None}
            if isinstance(m, unreal.MaterialInstance):
                row.update(_scalars(m))
                row["parent"] = _try(lambda: m.get_editor_property("parent").get_path_name())
            h["slots"].append(row)
        h["override_materials"] = _try(lambda: [x.get_path_name() if x else None
                                                for x in c.get_editor_property("override_materials")])
        out["hair"] = h
result = out
