"""Round 4 (agent-02), after wpo_probe.py read 0.0 cm for FM_Inflate 4 on his tee: WHY its WPO does nothing.
1. His tee master's graph facts: use_material_attributes (then the plain WPO pin is ignored), what drives the
   MaterialAttributes pin, the WPO pin's node, the engine version.
2. A bare test material (WPO = vertex normal x 4 cm, nothing else) compiled in /Game/FM/ClothOpTest, put on his tee's
   Shirt slot for one depth capture, the worn instance put back and the test folder deleted in a finally: does a
   skeletal WPO reach this capture at all? Editor-side, multi-tick, numbers only. Run:
    film-ue exec -c "exec(open('<tree>/films/host-studio/reel/r4/wpo_probe2.py').read())"
"""
import unreal

TREE = globals().get("CHECKOUT") or "/srv/ue/r3tree"
_ns = {"RUN": False, "LABEL": "Host", "__name__": "clip_pass"}
exec(compile(open(TREE + "/films/host-studio/reel/r4/clip_pass.py").read(), "clip_pass.py", "exec"), _ns)
FRAME = int(globals().get("FRAME", 1078))
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
TEST = "/Game/FM/ClothOpTest"
MP = unreal.MaterialProperty


def node(m, prop):
    try:
        n = MEL.get_material_property_input_node(m, prop)
        return type(n).__name__ if n else None
    except Exception as e:  # noqa: BLE001
        return f"? {e}"


def probe():
    a = _ns["find_actor"]("Host")
    yield from _ns["_scrub"](_ns["SEQ"], FRAME, 10)
    info = _ns["camera_info"](_ns["cut_camera"](_ns["SEQ"], FRAME), aspect=16 / 9)
    tee = _ns["layers"](a)["tee"]
    names = [str(n) for n in tee.get_material_slot_names()]
    idx = next(i for i, n in enumerate(names) if "shirt" in n.lower())
    worn = tee.get_materials()[idx]
    x = worn
    while isinstance(x, unreal.MaterialInstance):
        x = x.get_editor_property("parent")
    rep = {"engine": unreal.SystemLibrary.get_engine_version(), "master": x.get_path_name()}
    for p in ("use_material_attributes", "shading_model", "blend_mode", "used_with_skeletal_mesh"):
        try:
            rep[p] = str(x.get_editor_property(p))
        except Exception as e:  # noqa: BLE001
            rep[p] = f"? {e}"
    rep["pin_wpo"] = node(x, MP.MP_WORLD_POSITION_OFFSET)
    rep["pin_attributes"] = node(x, getattr(MP, "MP_MATERIAL_ATTRIBUTES", MP.MP_WORLD_POSITION_OFFSET))
    rep["pin_base_color"] = node(x, MP.MP_BASE_COLOR)
    rep["n_expressions"] = MEL.get_num_material_expressions(x)

    def depth():
        rt = yield from _ns["capture"](info, 480, 270, "depth", show_only=[tee], warmup=4)
        return _ns["read_pixels"](rt, "r")[0]

    base = yield from depth()
    try:
        if EAL.does_directory_exist(TEST):
            EAL.delete_directory(TEST)
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_WpoTest", TEST, unreal.Material,
                                                                     unreal.MaterialFactoryNew())
        n = MEL.create_material_expression(m, unreal.MaterialExpressionVertexNormalWS, -400, 0)
        c = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -400, 100)
        c.set_editor_property("r", 4.0)
        mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -200, 50)
        MEL.connect_material_expressions(n, "", mul, "A")
        MEL.connect_material_expressions(c, "", mul, "B")
        MEL.connect_material_property(mul, "", MP.MP_WORLD_POSITION_OFFSET)
        m.set_editor_property("used_with_skeletal_mesh", True)
        MEL.recompile_material(m)
        for _ in range(30):
            yield
        tee.set_material(idx, m)
        for _ in range(10):
            yield
        d = yield from depth()
        both = sorted(b - v for b, v in zip(base, d) if b < _ns["EMPTY"] and v < _ns["EMPTY"])
        rep["bare_wpo4"] = {"nearer_cm_median": round(both[len(both) // 2], 3) if both else None,
                            "nearer_cm_p90": round(both[int(len(both) * 0.9)], 3) if both else None,
                            "px": [sum(1 for b in base if b < _ns["EMPTY"]), sum(1 for v in d if v < _ns["EMPTY"])]}
    finally:
        tee.set_material(idx, worn)
        for _ in range(5):
            yield
        _ns["remove_rig"]()
        if EAL.does_directory_exist(TEST):
            EAL.delete_directory(TEST)
        rep["cleaned"] = not EAL.does_directory_exist(TEST)
        rep["slot_back"] = tee.get_materials()[idx].get_path_name() == worn.get_path_name()
    return rep


result = probe()
