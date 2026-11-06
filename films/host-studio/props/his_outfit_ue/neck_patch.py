"""Round 4 (agent-02): his tee pushed out ONLY where his face mesh pierces it (the orchestrator on cast_op5: the
neckline term of neck_fix.py ballooned the collar into a mock-neck and padded his chest).
  1. FIND: at FRAMES ((shot, frame), each through its own scrub), on the posed meshes (geometry; the tee's WPO is not
     in it): his face verts below the tee's top, within 6 cm of it, out of it by more than 0.1 cm along its normal,
     and reached from his spine_05 -> neck_02 axis only THROUGH the tee (not his throat seen through the neckline).
     Each one's nearest tee triangle's verts are looked up on a reference-pose copy of the tee (a temporary actor,
     no animation: the space the material's pre-skinned position reads), giving the patch: centre C, radius R (the
     farthest of them from C, + 1 cm) and depth (the deepest, + 0.8 cm, 1.5-3 cm).
  2. BUILD: his worn tee's chain copied into FOLDER (/Game/FM/ClothOp4); the master copy gets
     neck_inflate.add_patch (WPO += normal x FM_Patch x falloff, through its material attributes); only copies are
     reparented or compiled. Knobs: FM_Inflate INFLATE (0.2), FM_Neck 0, FM_Patch*, from 1. (PATCH overrides any).
  3. SWAP onto every slot that wore the old instance; CHECK his tee's base colour within 0.02 (else, or on any error,
     the old instance goes back on: ok False).
Editor-side, multi-tick, numbers only. Run (box tree T):
    film-ue exec -c "CHECKOUT='$T'; exec(open(CHECKOUT + '/films/host-studio/props/his_outfit_ue/neck_patch.py').read())"
Then the Host clip pass; the gate adds his tee's silhouette vs the pre-check (reel/r4 tee_silhouette.py).
"""
import importlib.util
import os

import unreal

TREE = globals().get("CHECKOUT") or "/srv/ue/r3tree"
LABEL = globals().get("LABEL", "Host")
FOLDER = globals().get("FOLDER", "/Game/FM/ClothOp4")
FRAMES = globals().get("FRAMES") or [("Reel_S13", 1078), ("Reel_S15", 1105), ("Reel_S15", 1130), ("Reel_S15", 1198),
                                     ("Reel_S17", 1322), ("Reel_S17", 1410), ("Reel_S18", 1493)]
INFLATE = float(globals().get("INFLATE", 0.2))
PATCH = globals().get("PATCH") or {}
FIND_ONLY = bool(globals().get("FIND_ONLY", False))
CLUSTER = globals().get("CLUSTER", "largest")  # which cluster of pierce points gets the push (index, or the largest)
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary

_ns = {"RUN": False, "LABEL": LABEL, "__name__": "clip_pass"}
exec(compile(open(TREE + "/films/host-studio/reel/r4/clip_pass.py").read(), "clip_pass.py", "exec"), _ns)
_spec = importlib.util.spec_from_file_location(
    "neck_inflate", os.path.join(TREE, "films/host-studio/props/his_outfit_ue/neck_inflate.py"))
ni = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ni)
_pick = None
SU, SP, MQ, LU = (unreal.GeometryScript_SceneUtils, unreal.GeometryScript_MeshSpatial,
                  unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List)


def _copy(comp, world):
    opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
    opts.set_editor_property("requested_lod", lod)
    dm = unreal.DynamicMesh()
    SU.copy_mesh_from_component(comp, dm, opts, world)
    return dm


def _verts(dm):
    return LU.convert_vector_list_to_array(_pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList"))


def ref_tee(asset):
    """His tee in its reference pose, mesh space (a temporary actor without animation; removed at once)."""
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    a = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, -50000))
    try:
        c = a.get_editor_property("skeletal_mesh_component")
        c.set_skeletal_mesh_asset(asset)
        return _verts(_copy(c, False))
    finally:
        eas.destroy_actor(a)


def find(L, ref):
    """The tee vert ids next to his face verts that pierce it at the current frame, and the deepest (cm)."""
    tee_c, face_c, body_c = L["tee"], L["Face"], L["Body"]
    tee = _copy(tee_c, True)
    tv = _verts(tee)
    if len(tv) != len(ref):
        raise RuntimeError(f"posed tee has {len(tv)} verts, reference copy {len(ref)}: the ids do not match")
    bvh = _pick(SP.build_bvh_for_mesh(tee), "GeometryScriptDynamicMeshBVH")
    q = unreal.GeometryScriptSpatialQueryOptions()
    top = max(p.z for p in tv)
    a0, a1 = body_c.get_socket_location("spine_05"), body_c.get_socket_location("neck_02")
    ax = a1 - a0
    L2 = max(ax.dot(ax), 1e-6)
    ids, deep, n = {}, 0.0, 0
    for p in _verts(_copy(face_c, True)):
        if p.z > top:
            continue
        tp = _pick(SP.find_nearest_point_on_mesh(tee, bvh, p, q), "GeometryScriptTrianglePoint")
        if not tp.get_editor_property("valid"):
            continue
        dv = p - tp.get_editor_property("position")
        if dv.length() > 6.0:
            continue
        tid = tp.get_editor_property("triangle_id")
        sd = dv.dot(_pick(MQ.get_triangle_face_normal(tee, tid), "Vector"))
        if sd <= 0.1:
            continue
        t = max(0.0, min(1.0, (p - a0).dot(ax) / L2))
        o = a0 + ax * t
        d = p - o
        dist = d.length()
        if dist < 1e-3:
            continue
        hit = _pick(SP.find_nearest_ray_intersection_with_mesh(tee, bvh, o, d * (1.0 / dist), q),
                    "GeometryScriptRayHitResult")
        if not (hit.get_editor_property("hit") and float(hit.get_editor_property("ray_parameter")) < dist - 0.05):
            continue
        n += 1
        deep = max(deep, sd)
        tri = _pick(MQ.get_triangle_indices(tee, tid), "IntVector")
        for k in (tri.x, tri.y, tri.z):
            ids[k] = max(ids.get(k, 0.0), sd)
    return ids, deep, n


def clusters(ref, ids, link=2.5):
    """The pierce points (tee vert ids -> depth) in single-link clusters (link cm, reference pose), largest first:
    [(ids, centre, radius, deepest)]. His neck meets the collar in more than one place; the patch is one of them."""
    left, out = set(ids), []
    while left:
        seed = left.pop()
        group, stack = [seed], [seed]
        while stack:
            i = stack.pop()
            near = [j for j in left if (ref[i] - ref[j]).length() <= link]
            for j in near:
                left.discard(j)
                group.append(j)
                stack.append(j)
        pts = [ref[i] for i in group]
        c = [sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts), sum(p.z for p in pts) / len(pts)]
        rad = max(((p.x - c[0]) ** 2 + (p.y - c[1]) ** 2 + (p.z - c[2]) ** 2) ** 0.5 for p in pts)
        out.append((group, c, rad, max(ids[i] for i in group)))
    out.sort(key=lambda g: -len(g[0]))
    return out


def copy_chain(worn):
    chain, x = [], worn
    while isinstance(x, unreal.MaterialInstance):
        chain.append(x)
        x = x.get_editor_property("parent")
    dst = f"{FOLDER}/{x.get_name()}_P"
    if not EAL.does_asset_exist(dst):
        EAL.duplicate_asset(x.get_path_name().split(".")[0], dst)
        ni.add_patch(EAL.load_asset(dst))
    m = EAL.load_asset(dst)
    if "FM_Patch" not in [str(k) for k in MEL.get_scalar_parameter_names(m)]:
        raise RuntimeError(f"{dst} has no FM_Patch")
    made, parent = [dst], m
    for mi in reversed(chain):
        path = f"{FOLDER}/{mi.get_name()}_P"
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


def run():
    global _pick
    from fmbridge.ops.mh.actor import _pick as pk
    from fmbridge.ops import mh
    _pick = pk
    a = _ns["find_actor"](LABEL)
    L = _ns["layers"](a)
    asset = L["tee"].get_skeletal_mesh_asset()
    ref = ref_tee(asset)
    rep = {"frames": {}, "ref_verts": len(ref)}
    ids, deep = {}, 0.0
    for shot, f in FRAMES:
        yield from _ns["_scrub"](_ns["SEQ"], int(f), 10)
        got, d, n = find(_ns["layers"](a), ref)
        rep["frames"][f"{shot}@{f}"] = {"face_verts_out": n, "deepest_cm": round(d, 2), "tee_verts": len(got)}
        for k, v in got.items():
            ids[k] = max(ids.get(k, 0.0), v)
        deep = max(deep, d)
        yield
    if not ids:
        rep["error"] = "no face vert pierces his tee at FRAMES"
        return rep
    cl = clusters(ref, ids)
    rep["clusters"] = [{"verts": len(c), "centre": [round(v, 2) for v in ctr], "radius": round(rad, 2),
                        "deepest_cm": round(dp, 2)} for c, ctr, rad, dp in cl]
    pick = cl[int(CLUSTER)] if str(CLUSTER).isdigit() else cl[0]  # default: the largest
    _, (cx, cy, cz), r, deep = pick
    knobs = {"FM_Inflate": INFLATE, "FM_Neck": 0.0, "FM_Patch": round(min(3.0, max(1.5, deep + 0.8)), 2),
             "FM_PatchX": round(cx, 2), "FM_PatchY": round(cy, 2), "FM_PatchZ": round(cz, 2),
             "FM_PatchR": round(r + 1.0, 2), "FM_PatchF": 3.0}
    knobs.update({k: float(v) for k, v in PATCH.items()})
    rep.update(patch_tee_verts=len(ids), deepest_cm=round(deep, 2), knobs=knobs)
    if FIND_ONLY:
        return rep
    tee = _ns["layers"](a)["tee"]
    slot = next(i for i, n_ in enumerate(tee.get_material_slot_names()) if "shirt" in str(n_).lower())
    worn = tee.get_materials()[slot]
    rep["worn"] = worn.get_path_name()
    s, f = FRAMES[0]
    yield from _ns["_scrub"](_ns["SEQ"], int(f), 10)
    info = _ns["camera_info"](_ns["cut_camera"](_ns["SEQ"], int(f)), aspect=16 / 9)

    def colour():
        rt = yield from _ns["capture"](info, 480, 270, "base_color", show_only=[_ns["layers"](a)["tee"]], warmup=2)
        r_, g_, b_ = _ns["read_pixels"](rt, "rgb")
        px = [(x, y, z) for x, y, z in zip(r_, g_, b_) if x + y + z > 1e-4]
        return [round(sum(p_[k] for p_ in px) / max(1, len(px)), 4) for k in range(3)]

    def swap(old, new_):
        cc = _ns["layers"](a)["tee"]
        hit = [k for k, m in enumerate(cc.get_materials()) if m is not None and m.get_path_name() == old.get_path_name()]
        for k in hit:
            cc.set_material(k, new_)
        return hit

    rep["colour_before"] = yield from colour()
    if worn.get_path_name().startswith(FOLDER + "/") and "FM_Patch" in [
            str(k) for k in MEL.get_scalar_parameter_names(worn)]:  # built already: new values only (safe while drawn)
        for k, v in knobs.items():
            MEL.set_material_instance_scalar_parameter_value(worn, k, float(v))
        EAL.save_asset(worn.get_path_name().split(".")[0])
        for _ in range(8):
            yield
        rep["colour_after"] = yield from colour()
        rep.update(retuned=True, ok=True, slots_now=[m.get_path_name().rsplit("/", 1)[-1] if m else None
                                                     for m in _ns["layers"](a)["tee"].get_materials()])
        _ns["remove_rig"]()
        return rep
    ok, new = False, None
    try:
        new, made = copy_chain(worn)
        rep["made"] = made
        for k, v in knobs.items():
            MEL.set_material_instance_scalar_parameter_value(new, k, float(v))
        MEL.update_material_instance(new)
        EAL.save_asset(new.get_path_name().split(".")[0])
        for _ in range(2):
            yield
        unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
        for _ in range(8):
            yield
        rep["slots_swapped"] = swap(worn, new)
        for _ in range(8):
            yield
        rep["colour_after"] = yield from colour()
        rep["colour_drift"] = round(max(abs(x - y) for x, y in zip(rep["colour_before"], rep["colour_after"])), 4)
        ok = rep["colour_drift"] <= 0.02 and bool(rep["slots_swapped"])
    except Exception as e:  # noqa: BLE001
        rep["error"] = f"{type(e).__name__}: {e}"
    finally:
        if not ok and new is not None:
            swap(new, worn)
            for _ in range(4):
                yield
        _ns["remove_rig"]()
    rep["ok"] = ok
    rep["slots_now"] = [m.get_path_name().rsplit("/", 1)[-1] if m else None
                        for m in _ns["layers"](a)["tee"].get_materials()]
    rep["leader"] = mh.leader_check(label=LABEL)["pass"]
    return rep


result = run()
