"""Round 4 (agent-02): his tee's inflate rebuilt so it reaches the render, on the level as it stands (no rebuild).
wpo_probe.py: his worn tee (/Game/FM/ClothOp) moved 0.0 cm even at FM_Inflate 4; wpo_probe2.py: why (Material
Attributes on MetaHuman's fabric master). neck_inflate.py now feeds the offset in through the attributes, in a fresh
folder (FOLDER, /Game/FM/ClothOp2), so nothing being drawn is recompiled:
  1. his tee's Shirt slot goes back to MetaHuman's own instance (found by name: the worn copy is
     <label>_<original>_Inflate), with the worn copy's colours;
  2. mh.cloth_inflate with neck_inflate.add_neck_inflate builds the new chain and swaps it on; the worn copy's
     FM_ knobs (FM_Inflate, FM_Neck, FM_NeckZ0/Z1/Front/FrontBias) are set on the new instance;
  3. CHECK: his tee alone is depth-captured at FRAME through its camera, before and after: it must come nearer by
     at least MIN_CM (median); if not, the worn copy goes back on and the result says so (ok False).
Editor-side, multi-tick, numbers only. Run (box tree T):
    film-ue exec -c "CHECKOUT='$T'; exec(open(CHECKOUT + '/films/host-studio/props/his_outfit_ue/neck_fix.py').read())"
A later host_swap.py (HOST op) builds the same chain from MetaHuman's instance on a fresh build (its NECK_MASTER).
"""
import importlib.util
import os

import unreal

TREE = globals().get("CHECKOUT") or "/srv/ue/r3tree"
LABEL = globals().get("LABEL", "Host")
FRAME = int(globals().get("FRAME", 1078))
MIN_CM = float(globals().get("MIN_CM", 0.2))
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
KEYS = ("FM_Inflate", "FM_Neck", "FM_NeckZ0", "FM_NeckZ1", "FM_NeckFront", "FM_NeckFrontBias")

_ns = {"RUN": False, "LABEL": LABEL, "__name__": "clip_pass"}
exec(compile(open(TREE + "/films/host-studio/reel/r4/clip_pass.py").read(), "clip_pass.py", "exec"), _ns)
_spec = importlib.util.spec_from_file_location(
    "neck_inflate", os.path.join(TREE, "films/host-studio/props/his_outfit_ue/neck_inflate.py"))
ni = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ni)


def original_of(worn):
    """MetaHuman's own instance the worn copy was made from: <label>_<name>_Inflate -> <name>, under /Game."""
    name = worn.get_name()
    if name.startswith(LABEL + "_"):
        name = name[len(LABEL) + 1:]
    if name.endswith("_Inflate"):
        name = name[:-len("_Inflate")]
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    hits = []
    flt = unreal.ARFilter(package_paths=["/Game"], recursive_paths=True)
    for a in ar.get_assets(flt):
        if str(a.asset_name) == name and not str(a.package_name).startswith("/Game/FM/"):
            hits.append(str(a.package_name))
    pref = [h for h in hits if f"/{LABEL}_" in h or "/Host_Op/" in h] or hits
    if not pref:
        raise RuntimeError(f"no original instance named {name} under /Game")
    return EAL.load_asset(sorted(pref)[0])


def fix():
    from fmbridge.ops import mh
    import fmbridge.ops.mh.actor as act
    a = _ns["find_actor"](LABEL)
    yield from _ns["_scrub"](_ns["SEQ"], FRAME, 10)
    info = _ns["camera_info"](_ns["cut_camera"](_ns["SEQ"], FRAME), aspect=16 / 9)

    def tee():
        return _ns["layers"](a)["tee"]

    def slot(c):
        return next(i for i, n in enumerate(c.get_material_slot_names()) if "shirt" in str(n).lower())

    def depth():
        rt = yield from _ns["capture"](info, 480, 270, "depth", show_only=[tee()], warmup=4)
        return _ns["read_pixels"](rt, "r")[0]

    c = tee()
    i = slot(c)
    worn = c.get_materials()[i]
    rep = {"worn": worn.get_path_name(), "folder": ni.FOLDER}
    knobs = {k: float(MEL.get_material_instance_scalar_parameter_value(worn, k)) for k in KEYS}
    rep["knobs"] = knobs
    orig = original_of(worn)
    rep["original"] = orig.get_path_name()
    master = orig
    while isinstance(master, unreal.MaterialInstance):
        master = master.get_editor_property("parent")
    rep["original_master"] = master.get_path_name()
    rep["use_material_attributes"] = bool(master.get_editor_property("use_material_attributes"))
    base = yield from depth()
    ok = False
    try:
        orig.set_editor_property("vector_parameter_values", worn.get_editor_property("vector_parameter_values"))
        MEL.update_material_instance(orig)
        c.set_material(i, orig)
        for _ in range(4):
            yield
        plain, act._add_inflate = act._add_inflate, ni.add_neck_inflate
        try:
            rep["inflated"] = {k: (v if isinstance(v, (int, float)) else list(v)) for k, v in (yield from mh.cloth_inflate(
                LABEL, cm=knobs["FM_Inflate"], component=c.get_name(), which="Shirt", folder=ni.FOLDER)).items()}
        finally:
            act._add_inflate = plain
        new = tee().get_materials()[slot(tee())]
        rep["new"] = new.get_path_name()
        mh.garment(LABEL, "Shirt", component=tee().get_name(), scalars=knobs)
        for _ in range(8):
            yield
        for cc in a.get_components_by_class(unreal.SkeletalMeshComponent):
            if cc.get_name() not in ("Body", "Face"):
                cc.set_leader_pose_component(_ns["layers"](a)["Body"])
        after = yield from depth()
        both = sorted(b - v for b, v in zip(base, after) if b < _ns["EMPTY"] and v < _ns["EMPTY"])
        med = both[len(both) // 2] if both else 0.0
        rep["nearer_cm_median"] = round(med, 3)
        rep["nearer_cm_p90"] = round(both[int(len(both) * 0.9)], 3) if both else None
        ok = med >= MIN_CM
    finally:
        if not ok:
            tee().set_material(slot(tee()), worn)
            for _ in range(4):
                yield
        _ns["remove_rig"]()
    rep["ok"] = ok
    rep["slot_now"] = tee().get_materials()[slot(tee())].get_path_name()
    rep["leader"] = mh.leader_check(label=LABEL)
    return rep


result = fix()
