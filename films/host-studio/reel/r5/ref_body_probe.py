"""Round 5 (agent-02), READ-ONLY: which skeletal mesh is Host_Op's UNCUT body? (G3 read silhouette 2.30 against
/Game/Host/Unpacked/Host/Body/SKM_Host_BodyMesh: an earlier build's or Trey's body, or a cut one.)

Every SkeletalMesh under ROOTS whose name has body/combined in it is compared, in the reference pose, with the body
Host wears now (MetaHuman-cut under his garments):
- same: of 1500 of the WORN body's verts, the distance to the candidate's surface (median, p95, cm): the same person
  reads median < 0.05 and p95 < 0.3;
- extra: of 3000 of the CANDIDATE's verts, the share farther than 0.2 cm from the worn body: what the worn one lacks.
  His uncut body = same person AND extra > 5% (the torso under the tee and shorts).
    film-ue exec <tree>/films/host-studio/reel/r5/ref_body_probe.py
Returns {"worn": path, "candidates": {path: {verts, skeleton, same_median_cm, same_p95_cm, extra_share, verdict}}}.
"""
import unreal

ROOTS = globals().get("ROOTS") or ["/Game/Host", "/Game/Characters", "/Game/MetaHumans"]
AU, SP, MQ, LU = (unreal.GeometryScript_AssetUtils, unreal.GeometryScript_MeshSpatial, unreal.GeometryScript_MeshQueries,
                  unreal.GeometryScript_List)
EAL = unreal.EditorAssetLibrary


def pick(res, cls):
    items = res if isinstance(res, tuple) else (res,)
    return next((x for x in items if type(x).__name__ == cls), items[0])


def dm_of(skm):
    dm = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_index", 0)
    AU.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
    return dm


def verts(dm):
    return list(LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList")))


def dists(points, dm, k):
    bvh = pick(SP.build_bvh_for_mesh(dm), "GeometryScriptDynamicMeshBVH")
    q = unreal.GeometryScriptSpatialQueryOptions()
    out = []
    for p in points[::max(1, len(points) // k)]:
        tp = pick(SP.find_nearest_point_on_mesh(dm, bvh, p, q), "GeometryScriptTrianglePoint")
        if tp.get_editor_property("valid"):
            out.append((p - tp.get_editor_property("position")).length())
    return sorted(out)


def pct(xs, f):
    return round(xs[min(len(xs) - 1, int(f * len(xs)))], 3) if xs else None


host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == "Host")
worn = next(c for c in host.get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == "Body")
worn_m = worn.get_skeletal_mesh_asset()
wdm = dm_of(worn_m)
wv = verts(wdm)
res = {"worn": worn_m.get_path_name().split(".")[0], "worn_verts": len(wv), "candidates": {}}
seen = set()
for root in ROOTS:
    if not EAL.does_directory_exist(root):
        continue
    for p in EAL.list_assets(root, recursive=True, include_folder=False):
        p = p.split(".")[0]
        n = p.rsplit("/", 1)[1].lower()
        if p in seen or not ("body" in n or "combined" in n):
            continue
        seen.add(p)
        m = EAL.load_asset(p)
        if not isinstance(m, unreal.SkeletalMesh):
            continue
        try:
            cdm = dm_of(m)
            cv = verts(cdm)
            same = dists(wv, cdm, 1500)
            extra = dists(cv, wdm, 3000)
        except Exception as e:  # noqa: BLE001
            res["candidates"][p] = {"error": str(e)}
            continue
        ex = round(sum(1 for d in extra if d > 0.2) / max(1, len(extra)), 4)
        med, p95 = pct(same, 0.5), pct(same, 0.95)
        is_same = med is not None and med < 0.05 and p95 < 0.3
        sk = m.get_editor_property("skeleton")
        res["candidates"][p] = {"verts": len(cv), "skeleton": sk.get_path_name().split(".")[0] if sk else None,
                                "same_median_cm": med, "same_p95_cm": p95, "extra_share": ex,
                                "verdict": ("HIS UNCUT BODY" if is_same and ex > 0.05 else
                                            "his worn (cut) body" if is_same else "another body")}
result = res
