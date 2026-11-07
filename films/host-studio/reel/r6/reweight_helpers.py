"""Round 6 (agent-02, for agent-07): move a garment's skin weights OFF MetaHuman's RBF helper / corrective joints onto
the core chain, on a NEW asset. Her overshirt (SKM_Presenter_Overshirt) carries ~60 % of its shoulder weight on
helpers (upperarm_twistCor_*, clavicle_pec/scap/out, upperarm_out/fwd/bck/in, bicep/tricep, lowerarm_fwd/out/in/bck,
spine_04_latissimus, ...): the body's volume push, sized for skin, balloons loose cloth with the elbows forward.

Per vertex: every influence on a non-core bone goes to its core target: the same name with twistCor -> twist when
that bone exists, else its nearest CORE ancestor (the component's own hierarchy); influences on one bone are summed
and the vertex renormalised. Positions, UVs, normals, materials and LODs > 0 are untouched; nothing is moved.
In the editor with Geometry Script (the same library shoulder_weights.py reads with), no FBX round trip.

STAGE='apply' (writes ONE new asset DEST, never the original): duplicate, reweight LOD0, save; then reads the copy
back: helper_weight_share must be 0.0 and positions identical. STAGE='check' (read-only): the same read-back on DEST.
Swap the copy onto her component only in her explainer level, then stills at the worst frames.

    film-ue exec -c "STAGE='apply'; LABEL='Presenter'; COMP='Overshirt'; DEST='/Game/Host/Presenter_Overshirt/SKM_Presenter_Overshirt_RW'; exec(open('<tree>/films/host-studio/reel/r6/reweight_helpers.py').read())"
"""
import re

import unreal

STAGE = globals().get("STAGE", "check")
LABEL = globals().get("LABEL", "Presenter")
COMP = globals().get("COMP", "Overshirt")
DEST = globals().get("DEST", "/Game/Host/Presenter_Overshirt/SKM_Presenter_Overshirt_RW")
# FAMILIES: only helpers whose name starts with one of these move (comma list); "" = every helper. Round 6 RW (all
# helpers) fixed the balloon but opened holes where her collar meets the shoulder: the clavicle_*/spine_* helpers
# also keep the collar/yoke on the body. RW2 = "upperarm,lowerarm": the cap and sleeve only.
FAMILIES = tuple(f for f in globals().get("FAMILIES", "").split(",") if f)
EAL = unreal.EditorAssetLibrary
CORE = re.compile(r"^(root|pelvis|spine_0[1-5]|neck_0[12]|head|clavicle_[lr]|upperarm_[lr]|upperarm_twist_0[12]_[lr]|"
                  r"lowerarm_[lr]|lowerarm_twist_0[12]_[lr]|hand_[lr]|"
                  r"(thumb|index|middle|ring|pinky)_(0[1-3]|metacarpal)_[lr]|thigh_[lr]|thigh_twist_0[12]_[lr]|"
                  r"calf_[lr]|calf_twist_0[12]_[lr]|foot_[lr]|ball_[lr])$")


def pick(res, cls):
    items = res if isinstance(res, tuple) else (res,)
    return next((x for x in items if type(x).__name__ == cls), items[0])


def lib():
    for n in ("GeometryScript_BoneWeights", "GeometryScript_MeshBoneWeights", "GeometryScript_SkinWeights"):
        if hasattr(unreal, n):
            return getattr(unreal, n)
    raise RuntimeError("no Geometry Script bone-weight library: " +
                       str(sorted(n for n in dir(unreal) if "eight" in n and "GeometryScript" in n)))


def dm_of(skm):
    dm = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_index", 0)
    unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(),
                                                                  lod)
    return dm


def positions(dm):
    return list(unreal.GeometryScript_List.convert_vector_list_to_array(
        pick(unreal.GeometryScript_MeshQueries.get_all_vertex_positions(dm, False), "GeometryScriptVectorList")))


def weights(BW, dm, v):
    res = BW.get_vertex_bone_weights(dm, v)
    ws = next((x for x in (res if isinstance(res, tuple) else (res,)) if isinstance(x, (list, unreal.Array))), [])
    return [(int(w.get_editor_property("bone_index")), float(w.get_editor_property("weight"))) for w in ws]


host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == LABEL)
comp = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}[COMP]
nb = comp.get_num_bones()
names = [str(comp.get_bone_name(i)) for i in range(nb)]
index = {n: i for i, n in enumerate(names)}


def target(i: int) -> int:
    n = names[i]
    if CORE.match(n) or (FAMILIES and not n.startswith(FAMILIES)):
        return i
    alt = n.replace("twistCor", "twist")
    if alt != n and alt in index and CORE.match(alt):
        return index[alt]
    p = n
    for _ in range(64):
        p = str(comp.get_parent_bone(p))
        if not p or p == "None":
            break
        if CORE.match(p):
            return index[p]
    return i  # no core ancestor (should not happen): leave it


T = [target(i) for i in range(nb)]
BW = lib()


def share(dm):
    hw = tw = 0.0
    for v in range(len(positions(dm))):
        for i, w in weights(BW, dm, v):
            tw += w
            if 0 <= i < nb and not CORE.match(names[i]):
                hw += w
    return round(hw / max(tw, 1e-9), 4)


if STAGE == "apply":
    src = comp.get_skeletal_mesh_asset()
    if EAL.does_asset_exist(DEST):
        raise RuntimeError(f"{DEST} exists: pass a new DEST (never overwrite)")
    dup = EAL.duplicate_asset(src.get_path_name().split(".")[0], DEST)
    dm = dm_of(dup)
    P0 = positions(dm)
    moved = 0
    for v in range(len(P0)):
        ws = weights(BW, dm, v)
        acc = {}
        for i, w in ws:
            j = T[i] if 0 <= i < nb else i
            acc[j] = acc.get(j, 0.0) + w
        if len(acc) == len(ws) and all(T[i] == i for i, _ in ws if 0 <= i < nb):
            continue
        tot = sum(acc.values()) or 1.0
        new = []
        for j, w in sorted(acc.items(), key=lambda kv: -kv[1])[:8]:  # UE keeps up to 8 influences on import
            bw = unreal.GeometryScriptBoneWeight()
            bw.set_editor_property("bone_index", j)
            bw.set_editor_property("weight", w / tot)
            new.append(bw)
        BW.set_vertex_bone_weights(dm, v, new)
        moved += 1
    opts = unreal.GeometryScriptCopyMeshToAssetOptions()
    for k, val in (("enable_recompute_normals", False), ("enable_recompute_tangents", False),
                   ("enable_remove_degenerates", False), ("use_original_vertex_order", True),
                   ("replace_materials", False)):
        try:
            opts.set_editor_property(k, val)
        except Exception:  # noqa: BLE001
            pass
    lod = unreal.GeometryScriptMeshWriteLOD()
    lod.set_editor_property("lod_index", 0)
    unreal.GeometryScript_AssetUtils.copy_mesh_to_skeletal_mesh(dm, dup, opts, lod)
    EAL.save_asset(DEST)
    back = dm_of(EAL.load_asset(DEST))
    P1 = positions(back)
    dpos = max(((a - b).length() for a, b in zip(P0, P1)), default=0.0) if len(P0) == len(P1) else None
    result = {"dest": DEST, "src": src.get_path_name(), "verts": [len(P0), len(P1)], "reweighted_verts": moved,
              "positions_max_diff_cm": round(dpos, 5) if dpos is not None else "vertex count changed",
              "helper_weight_share": {"before": share(dm_of(src)), "after": share(back)},
              "remap_examples": {names[i]: names[T[i]] for i in range(nb) if T[i] != i and
                                 any(k in names[i] for k in ("upperarm", "clavicle", "lowerarm", "latissimus"))
                                 and names[i].endswith("_r")}}
else:
    m = EAL.load_asset(DEST)
    result = {"dest": DEST, "helper_weight_share": share(dm_of(m)), "verts": len(positions(dm_of(m)))}
