"""Round 4 (agent-02): does his tee's World Position Offset (FM_Inflate, the neckline term) reach the render at all?
The AFTER pass showed his tee's depth unchanged to 0.1 cm with FM_Inflate 0.4 + FM_Neck 2.5 (the patch the same size).
At one frame (SHOT/FRAME, default S13 f1078, the shot's camera) his tee alone is depth-captured as worn, then with
FM_Inflate 4 cm, then with the neckline term forced on everywhere (FM_Neck 4, Z0 0, Z1 1, front 0, bias 1); the worn
values are put back in a finally. Also reports the tee's material chain, whether its master's WPO pin is wired, and
the component's WPO-related settings. Editor-side, multi-tick; numbers only (stills: none). Run:
    film-ue exec -c "exec(open('<tree>/films/host-studio/reel/r4/wpo_probe.py').read())"
"""
import os
import unreal

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or "/srv/ue/r3tree/films/host-studio/reel/r4/x"))
TREE = globals().get("CHECKOUT") or "/srv/ue/r3tree"
_ns = {"RUN": False, "LABEL": "Host", "__name__": "clip_pass"}
exec(compile(open(TREE + "/films/host-studio/reel/r4/clip_pass.py").read(), "clip_pass.py", "exec"), _ns)
SHOT = globals().get("SHOT", "Reel_S13")
FRAME = int(globals().get("FRAME", 1078))
MEL = unreal.MaterialEditingLibrary
KEYS = ("FM_Inflate", "FM_Neck", "FM_NeckZ0", "FM_NeckZ1", "FM_NeckFront", "FM_NeckFrontBias")


def chain_info(mi):
    out, x = [], mi
    while isinstance(x, unreal.MaterialInstance):
        out.append(f"{type(x).__name__}:{x.get_path_name()}")
        x = x.get_editor_property("parent")
    info = {"chain": out, "master": x.get_path_name() if x else None}
    if x is not None:
        n = MEL.get_material_property_input_node(x, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
        info["wpo_node"] = type(n).__name__ if n else None
        info["master_scalars"] = [str(s) for s in MEL.get_scalar_parameter_names(x) if str(s).startswith("FM_")]
        for p in ("used_with_skeletal_mesh", "blend_mode", "material_domain"):
            try:
                info[p] = str(x.get_editor_property(p))
            except Exception as e:  # noqa: BLE001
                info[p] = f"? {e}"
    return info


def comp_info(c):
    out = {"name": c.get_name(), "mesh": c.get_skeletal_mesh_asset().get_path_name()}
    for p in ("evaluate_world_position_offset", "world_position_offset_disable_distance", "mesh_deformer",
              "forced_lod_model", "skin_cache_usage", "render_static", "cpu_skinning"):
        try:
            out[p] = str(c.get_editor_property(p))
        except Exception as e:  # noqa: BLE001
            out[p] = "?"
    try:
        out["nanite"] = str(c.get_skeletal_mesh_asset().get_editor_property("nanite_settings").get_editor_property("enabled"))
    except Exception:
        out["nanite"] = "?"
    return out


def probe():
    a = _ns["find_actor"]("Host")
    cuts = {cc: (int(s), int(e)) for cc, s, e in _ns["call"]("seq.cuts", path=_ns["SEQ"])}
    yield from _ns["_scrub"](_ns["SEQ"], FRAME, 10)
    info = _ns["camera_info"](_ns["cut_camera"](_ns["SEQ"], FRAME), aspect=16 / 9)
    L = _ns["layers"](a)
    tee = L["tee"]
    mats = list(zip([str(n) for n in tee.get_material_slot_names()], tee.get_materials()))
    rep = {"shot": SHOT, "frame": FRAME, "in_cut": cuts.get(SHOT), "comp": comp_info(tee), "layers": sorted(L),
           "slots": {n: (m.get_path_name() if m else None) for n, m in mats}}
    shirt = [m for n, m in mats if m is not None and "shirt" in n.lower()]
    mi = shirt[0] if shirt else None
    if mi is None:
        rep["error"] = "no Shirt slot"
        return rep
    rep["mat"] = chain_info(mi)
    rep["mi_class"] = type(mi).__name__
    worn = {}
    for k in KEYS:
        try:
            worn[k] = float(MEL.get_material_instance_scalar_parameter_value(mi, k))
        except Exception:  # noqa: BLE001
            worn[k] = None
    rep["worn"] = worn

    def depth():
        rt = yield from _ns["capture"](info, 480, 270, "depth", show_only=[tee], warmup=4)
        return _ns["read_pixels"](rt, "r")[0]

    def setv(vals):
        for k, v in vals.items():
            if v is not None:
                MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))

    base = yield from depth()
    runs = {}
    try:
        for name, vals in (("inflate4", {"FM_Inflate": 4.0}),
                           ("neck_everywhere4", {"FM_Neck": 4.0, "FM_NeckZ0": 0.0, "FM_NeckZ1": 1.0,
                                                 "FM_NeckFront": 0.0, "FM_NeckFrontBias": 1.0})):
            setv(vals)
            for _ in range(6):
                yield
            d = yield from depth()
            setv(worn)
            for _ in range(3):
                yield
            both = [(b - x) for b, x in zip(base, d) if b < _ns["EMPTY"] and x < _ns["EMPTY"]]
            both.sort()
            cov = (sum(1 for b in base if b < _ns["EMPTY"]), sum(1 for x in d if x < _ns["EMPTY"]))
            runs[name] = {"px_base_new": cov, "nearer_cm_median": round(both[len(both) // 2], 3) if both else None,
                          "nearer_cm_p90": round(both[int(len(both) * 0.9)], 3) if both else None}
    finally:
        setv(worn)
        _ns["remove_rig"]()
    rep["runs"] = runs
    again = yield from depth()
    rep["restored_same"] = max((abs(b - x) for b, x in zip(base, again) if b < _ns["EMPTY"] and x < _ns["EMPTY"]),
                               default=None)
    return rep


result = probe()
