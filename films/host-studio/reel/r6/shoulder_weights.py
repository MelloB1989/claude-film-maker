"""Round 6 (agent-02, for agent-07/agent-01): WHICH bones a garment's shoulder is skinned to. READ-ONLY.

Her overshirt balloons at the right shoulder in the seated explainer pose. First suspect after the pose: the cap is
weighted (by a weight transfer from the body) to MetaHuman's RBF-driven helper / corrective joints round the
shoulder (upperarm_out/fwd/bck/in, upperarm_correctiveRoot, clavicle_out/scap, ...), whose volume push is sized for
skin and reads as a rounded pad on loose cloth with the elbows forward.

For the garment asset (LOD0, source), every vertex with weight on a shoulder bone of SIDE (clavicle*/upperarm*
names ending _<side>) is in the set; per bone: verts influenced, mean and max weight, and whether the bone is a
CORE chain bone (clavicle, upperarm, upperarm twist, lowerarm, spine, neck) or a HELPER. Both sides are reported
(the other side is the control). Helpers carrying real weight on the ballooning side = reweight those verts onto
the core bones.

    film-ue exec -c "LABEL='Presenter'; COMP='Overshirt'; exec(open('<tree>/films/host-studio/reel/r6/shoulder_weights.py').read())"
"""
import unreal

LABEL = globals().get("LABEL", "Presenter")
COMP = globals().get("COMP", "Overshirt")
MIN_W = float(globals().get("MIN_W", 0.05))
CORE = ("clavicle_", "upperarm_", "upperarm_twist_01_", "upperarm_twist_02_", "lowerarm_", "spine_", "neck_")


def pick(res, cls):
    items = res if isinstance(res, tuple) else (res,)
    return next((x for x in items if type(x).__name__ == cls), items[0])


def lib():
    for n in ("GeometryScript_BoneWeights", "GeometryScript_MeshBoneWeights", "GeometryScript_SkinWeights"):
        if hasattr(unreal, n):
            return getattr(unreal, n)
    have = sorted(n for n in dir(unreal) if "eight" in n and "GeometryScript" in n)
    raise RuntimeError(f"no Geometry Script bone-weight library in this build; candidates: {have}")


def is_core(name: str) -> bool:
    base = name.rsplit("_", 1)[0] + "_" if name.endswith(("_l", "_r")) else name
    return any(base == c for c in CORE) or name.startswith(("spine_", "neck_"))


host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == LABEL)
comps = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
if COMP not in comps:
    raise RuntimeError(f"no component {COMP}: {sorted(comps)}")
comp = comps[COMP]
skm = comp.get_skeletal_mesh_asset()
nb = comp.get_num_bones()
names = [str(comp.get_bone_name(i)) for i in range(nb)]

dm = unreal.DynamicMesh()
lod = unreal.GeometryScriptMeshReadLOD()
lod.set_editor_property("lod_index", 0)
unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
BW = lib()
fn = getattr(BW, "get_vertex_bone_weights")
nv = len(unreal.GeometryScript_List.convert_vector_list_to_array(
    pick(unreal.GeometryScript_MeshQueries.get_all_vertex_positions(dm, False), "GeometryScriptVectorList")))

stats = {"l": {}, "r": {}}
setv = {"l": 0, "r": 0}
helper_dominant = {"l": 0, "r": 0}
for v in range(nv):
    res = fn(dm, v)
    ws = next((x for x in (res if isinstance(res, tuple) else (res,)) if isinstance(x, (list, unreal.Array))), [])
    pairs = [(int(w.get_editor_property("bone_index")), float(w.get_editor_property("weight"))) for w in ws]
    pairs = [(names[i] if 0 <= i < nb else f"#{i}", w) for i, w in pairs if w > 0]
    for side in ("l", "r"):
        sh = [(n, w) for n, w in pairs if n.endswith("_" + side) and n.startswith(("clavicle", "upperarm"))]
        if not sh or max(w for _, w in sh) < MIN_W:
            continue
        setv[side] += 1
        top = max(pairs, key=lambda p: p[1])
        if not is_core(top[0]):
            helper_dominant[side] += 1
        for n, w in pairs:
            s = stats[side].setdefault(n, [0, 0.0, 0.0])
            s[0] += 1
            s[1] += w
            s[2] = max(s[2], w)

out = {"mesh": skm.get_path_name(), "bones": nb, "verts": nv, "min_w": MIN_W}
for side in ("r", "l"):
    rows = sorted(stats[side].items(), key=lambda kv: -kv[1][1])
    out[side] = {"shoulder_verts": setv[side], "helper_dominant_verts": helper_dominant[side],
                 "bones": [{"bone": n, "core": is_core(n), "verts": s[0], "mean_w": round(s[1] / s[0], 3),
                            "max_w": round(s[2], 3)} for n, s in rows[:25]],
                 "helper_weight_share": round(sum(s[1] for n, s in rows if not is_core(n))
                                              / max(1e-9, sum(s[1] for _, s in rows)), 3)}
result = out
