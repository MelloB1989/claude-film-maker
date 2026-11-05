"""Read-only probe for note 3's hair pop (her hair shortens at the shoulders at 0:39-0:40 of the v2 45 s cut: master
f1416-1440, the end of S17's crane out). Lists what decides the Presenter's groom LOD: her groom components (asset,
binding, LOD count, forced LOD, the asset's per-LOD geometry type and screen size), the LODSync component, the hair
LOD cvars, and the Python names of the LOD setters. Changes nothing.

    film-ue exec films/host-studio/reel/hair_lod_probe.py
"""
import unreal

LABEL = "Presenter"


def _try(f, *a):
    try:
        v = f(*a)
        return v if isinstance(v, (bool, int, float, str, type(None))) else str(v)
    except Exception as e:  # noqa: BLE001 - a probe: report what fails
        return f"ERR {type(e).__name__}: {e}"[:200]


def _prop(o, name):
    return _try(o.get_editor_property, name)


acts = [a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
        if a.get_actor_label() == LABEL]
out = {"actor": None, "grooms": [], "lodsync": [], "skel": [], "cvars": {}, "api": {}}
if acts:
    a = acts[0]
    out["actor"] = a.get_path_name()
    for c in a.get_components_by_class(unreal.GroomComponent):
        g = {"name": c.get_name(), "visible": _try(c.is_visible)}
        ga = c.get_editor_property("groom_asset")
        g["asset"] = ga.get_path_name() if ga else None
        b = _try(lambda: c.get_editor_property("binding_asset"))
        g["binding"] = b
        for n in ("get_num_lods", "get_forced_lod", "get_desired_sync_lod", "get_num_sync_lods"):
            if hasattr(c, n):
                g[n] = _try(getattr(c, n))
        for n in ("lod_forced_index", "forced_lod", "simulation_settings", "enable_simulation", "use_cards"):
            g[n] = _prop(c, n)
        if ga:
            lods = []
            try:
                for grp in ga.get_editor_property("hair_groups_lod"):
                    lods.append([{k: _prop(l, k) for k in ("geometry_type", "screen_size", "curve_decimation",
                                                            "vertex_decimation", "bind_type", "simulation")}
                                 for l in grp.get_editor_property("lods")])
            except Exception as e:  # noqa: BLE001
                lods = f"ERR {e}"[:200]
            g["asset_lods"] = lods
            g["asset_lod_mode"] = _prop(ga, "lod_mode")
            g["asset_auto_lod_bias"] = _prop(ga, "auto_lod_bias")
            g["asset_enable_simulation"] = _try(lambda: str(ga.get_editor_property("enable_simulation")))
        out["grooms"].append(g)
    if hasattr(unreal, "LODSyncComponent"):
        for c in a.get_components_by_class(unreal.LODSyncComponent):
            out["lodsync"].append({k: _prop(c, k) for k in ("forced_lod", "min_lod", "num_lods", "components_to_sync",
                                                            "custom_lod_mapping")})
    # day 1 of round 3: build.py --lod0 found LODSync/skeletal components named TRASH_* (left by a Blueprint
    # recompile): which components are live (registered, attached to the actor's root) and which are stale?
    out["components"] = [{"name": c.get_name(), "class": c.get_class().get_name(), "registered": _try(c.is_registered),
                          "attach": _try(lambda: c.get_attach_parent().get_name() if c.get_attach_parent() else None),
                          "visible": _try(c.is_visible) if hasattr(c, "is_visible") else None}
                         for c in a.get_components_by_class(unreal.ActorComponent)]
    out["class"] = a.get_class().get_path_name()
    for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
        out["skel"].append({"name": c.get_name(), "forced_lod_model": _prop(c, "forced_lod_model"),
                            "min_lod_model": _prop(c, "min_lod_model")})
for cv in ("r.HairStrands.Enable", "r.HairStrands.LODMode", "r.HairStrands.ForceLOD", "r.HairStrands.Cards.ForceLOD",
           "r.HairStrands.UseCardsInsteadOfStrands", "r.HairStrands.Simulation", "r.ForceLOD", "r.SkeletalMeshLODBias",
           "r.HairStrands.LODBias", "r.HairStrands.Strands.MaxLOD"):
    out["cvars"][cv] = _try(unreal.SystemLibrary.get_console_variable_int_value, cv)
for cls, words in ((getattr(unreal, "GroomComponent", None), ("lod", "simulat", "reset")),
                   (getattr(unreal, "LODSyncComponent", None), ("lod",))):
    if cls:
        out["api"][cls.__name__] = sorted(n for n in dir(cls) if any(w in n.lower() for w in words))
result = out
