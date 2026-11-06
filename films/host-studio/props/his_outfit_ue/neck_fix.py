"""Round 4 (agent-02): his tee's inflate rebuilt so it reaches the render, on the level as it stands (no rebuild).
wpo_probe.py: his worn tee (/Game/FM/ClothOp) moved 0.0 cm even at FM_Inflate 4; wpo_probe2.py: why: MetaHuman's
fabric master runs on Material Attributes, so the plain WPO pin it was wired to is ignored.
  1. his worn tee's chain (instances + master) is copied into neck_inflate.FOLDER (/Game/FM/ClothOp3), the master
     copy gets neck_inflate.add_neck_inflate (the offset through its material attributes) and only the copies are
     reparented or compiled (nothing being drawn); the FM_ knobs (the worn ones, or KNOBS) go on the new instance;
  2. the new instance goes on his tee's Shirt slot;
  3. CHECK: his tee alone is depth-captured at FRAME through its camera, before and after: it must come nearer by
     at least MIN_CM (median) and its base colour stay within MAX_COLOUR; if not (or on any error), the worn
     instance goes back on and the result says so (ok False, error).
Editor-side, multi-tick, numbers only. Run (box tree T):
    film-ue exec -c "CHECKOUT='$T'; exec(open(CHECKOUT + '/films/host-studio/props/his_outfit_ue/neck_fix.py').read())"
On a fresh build host_swap.py (HOST op, NECK_MASTER) builds the same offset from MetaHuman's own master.
"""
import importlib.util
import os

import unreal

TREE = globals().get("CHECKOUT") or "/srv/ue/r3tree"
LABEL = globals().get("LABEL", "Host")
FRAME = int(globals().get("FRAME", 1078))
MIN_CM = float(globals().get("MIN_CM", 0.2))
MAX_COLOUR = float(globals().get("MAX_COLOUR", 0.02))  # mean linear base colour, per channel
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
KEYS = ("FM_Inflate", "FM_Neck", "FM_NeckZ0", "FM_NeckZ1", "FM_NeckFront", "FM_NeckFrontBias")
KNOBS = globals().get("KNOBS") or {}  # forced values (else the worn copy's), e.g. after a restore from disk

_ns = {"RUN": False, "LABEL": LABEL, "__name__": "clip_pass"}
exec(compile(open(TREE + "/films/host-studio/reel/r4/clip_pass.py").read(), "clip_pass.py", "exec"), _ns)
_spec = importlib.util.spec_from_file_location(
    "neck_inflate", os.path.join(TREE, "films/host-studio/props/his_outfit_ue/neck_inflate.py"))
ni = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ni)


def copy_chain(worn):
    """His worn tee's chain copied into ni.FOLDER: the master (ni.add_neck_inflate on the copy: the offset through
    its material attributes) and every instance above it, each copy parented on the one below; only the copies are
    ever reparented or compiled (nothing being drawn). Returns the new worn instance."""
    chain, x = [], worn
    while isinstance(x, unreal.MaterialInstance):
        chain.append(x)
        x = x.get_editor_property("parent")
    src_master = x
    dst = f"{ni.FOLDER}/{src_master.get_name()}_N"
    if not EAL.does_asset_exist(dst):
        EAL.duplicate_asset(src_master.get_path_name().split(".")[0], dst)
        m = EAL.load_asset(dst)
        ni.add_neck_inflate(m)
    m = EAL.load_asset(dst)
    if ni.MARK not in [str(n) for n in MEL.get_scalar_parameter_names(m)]:
        raise RuntimeError(f"{dst} has no {ni.MARK}: its offset is not on its material attributes")
    made, parent = [dst], m
    for mi in reversed(chain):
        name = (f"{LABEL}_{mi.get_name()}_Inflate" if mi is worn and not mi.get_name().endswith("_Inflate")
                else f"{mi.get_name()}_N")
        path = f"{ni.FOLDER}/{name}"
        if not EAL.does_asset_exist(path):
            EAL.duplicate_asset(mi.get_path_name().split(".")[0], path)
        c = EAL.load_asset(path)
        if c.get_editor_property("parent") != parent:
            MEL.set_material_instance_parent(c, parent)
        made.append(path)
        parent = c
    for path in made:
        EAL.save_asset(path)
    return parent, made


def fix():
    from fmbridge.ops import mh
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

    def colour():  # his tee's base colour alone: Break/Make must pass every attribute through unchanged
        rt = yield from _ns["capture"](info, 480, 270, "base_color", show_only=[tee()], warmup=2)
        r, g, b = _ns["read_pixels"](rt, "rgb")
        px = [(x, y, z) for x, y, z in zip(r, g, b) if x + y + z > 1e-4]
        return [round(sum(p[k] for p in px) / max(1, len(px)), 4) for k in range(3)]

    c = tee()
    i = slot(c)
    worn = c.get_materials()[i]
    rep = {"worn": worn.get_path_name(), "folder": ni.FOLDER}
    knobs = {k: float(MEL.get_material_instance_scalar_parameter_value(worn, k)) for k in KEYS}
    rep["knobs_worn"] = dict(knobs)
    knobs.update({k: float(v) for k, v in KNOBS.items()})
    rep["knobs"] = knobs
    base = yield from depth()
    rep["colour_before"] = yield from colour()
    ok = False
    try:
        new, made = copy_chain(worn)
        rep["made"] = made
        for k, v in knobs.items():
            MEL.set_material_instance_scalar_parameter_value(new, k, v)
        MEL.set_material_instance_scalar_parameter_value(new, ni.MARK, 1.0)
        MEL.update_material_instance(new)
        EAL.save_asset(new.get_path_name().split(".")[0])
        for _ in range(2):
            yield
        unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
        for _ in range(8):
            yield
        tee().set_material(slot(tee()), new)
        for _ in range(6):
            yield
        rep["new"] = new.get_path_name()
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
        rep["colour_after"] = yield from colour()
        dc = max(abs(x - y) for x, y in zip(rep["colour_before"], rep["colour_after"]))
        rep["colour_drift"] = round(dc, 4)
        ok = med >= MIN_CM and dc <= MAX_COLOUR
    except Exception as e:  # noqa: BLE001  (the worn tee goes back on below; the reason goes in the result)
        rep["error"] = f"{type(e).__name__}: {e}"
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
