"""Round 5, probe G7 (agent-02), READ-ONLY: his tee's material slots as worn, each with its material's parent chain
and the inflate parameters, so the refit Tee is dressed with the plain MetaHuman instance (no WPO chain). Run:
    film-ue exec $T/films/host-studio/reel/r5/tee_slots.py
Returns {component: [{slot, material, chain: [parents...], plain: first parent outside /Game/FM, wpo: {param: v}}]}.
"""
import unreal

MEL = unreal.MaterialEditingLibrary
out = {}
host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == "Host")
for c in host.get_components_by_class(unreal.SkeletalMeshComponent):
    if c.get_name() in ("Body", "Face", "Trousers"):
        continue
    rows = []
    for slot, m in zip(c.get_material_slot_names(), c.get_materials()):
        chain, x = [], m
        while isinstance(x, unreal.MaterialInstance):
            chain.append(x.get_path_name().split(".")[0])
            x = x.get_editor_property("parent")
        if x is not None:
            chain.append(x.get_path_name().split(".")[0])
        wpo = {}
        if isinstance(m, unreal.MaterialInstanceConstant):
            names = [str(n) for n in MEL.get_scalar_parameter_names(m)]
            for k in ("FM_Inflate", "FM_Neck", "FM_Patch"):
                if k in names:
                    wpo[k] = MEL.get_material_instance_scalar_parameter_value(m, k)
        plain = next((p for p in chain if not p.startswith("/Game/FM/") and "Inflate" not in p), None)
        if plain is None and chain and "_Inflate" in chain[0]:  # cloth_inflate's copy: Host_<MI>_Inflate[_N_P...]
            want = chain[0].rsplit("/", 1)[1][len("Host_"):].split("_Inflate")[0]
            ar = unreal.AssetRegistryHelpers.get_asset_registry()
            hits = [str(d.package_name) for d in ar.get_all_assets() if str(d.asset_name) == want]
            plain = sorted(hits, key=lambda h: (h.startswith("/Game/FM/"), len(h)))[0] if hits else None
        rows.append({"slot": str(slot), "material": chain[0] if chain else None, "chain": chain, "plain": plain,
                     "wpo": wpo})
    m = c.get_skeletal_mesh_asset()
    out[c.get_name()] = {"mesh": m.get_path_name() if m else None, "slots": rows}
result = out
