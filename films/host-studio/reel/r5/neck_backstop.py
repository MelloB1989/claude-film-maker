"""Round 5 (agent-02), the NECK BACKSTOP ("route B", docs/unreal/research/garment-fit.md §3): MetaHuman's own head
hidden face map, set to SHRINK (not cull) his face mesh's lower neck under the tee's collar, so a big head turn
(S17 f1397) cannot bring the face mesh out through the collar even where the collar lags. Only if (A)'s qa.clip
still reads neck_px > 0. It needs a MetaHuman REBUILD (the map is applied at assembly), i.e. the full re-dress after.

Verified on the 5.8.4 source: UMetaHumanSkeletalMeshEditorPipeline / UMetaHumanOutfitEditorPipeline
HeadHiddenFaceMapTexture {Texture, Settings{MaxCullValue 0.1, MinKeepValue 0.9, MaxShrinkDistance 0}}; per skin
vertex the map is sampled in its UV space (max of R, G, B); ComputeShrinkWeight = 1 - clamp((p - MaxCull) / (MinKeep -
MaxCull)); a triangle fully under p <= MaxCull is REMOVED, and MaxCull < 0 is INVALID (the whole assembly fails). So
MaxCull is 0.0 and the band is drawn from p = 1/255 (full shrink, never culled) to 1 (white: untouched).

    STAGE='mask'  (read-only on the project): the face verts under the tee (a ray out along the skin normal meets
                  the Tee within REACH cm, rest pose), each weighted by its distance under the collar edge (0 at the
                  edge, 1 at RAMP cm below), rasterised into the head's UV 0 as a grey PNG at OUT.
    STAGE='apply' (writes assets): imports the PNG (/Game/Host/Fit/T_Host_NeckHidden, sRGB off), duplicates the
                  default garment's wardrobe item WI to /Game/Host/Fit/WI_Host_DefaultGarment_Neck and sets its head
                  hidden face map (MaxShrinkDistance SHRINK_CM). Then (garment.md §5b): mh.add_item that WI in the
                  Outfits slot, mh.build, and the re-dress chain.
    film-ue exec -c "STAGE='mask'; WI='<default garment WI_>'; exec(open('<tree>/films/host-studio/reel/r5/neck_backstop.py').read())"
"""
import os

import unreal

STAGE = globals().get("STAGE", "mask")
LABEL = globals().get("LABEL", "Host")
TEE = globals().get("TEE", "Tee")  # the refit tee's component
REACH = float(globals().get("REACH", 4.0))  # cm: a face vert this far under the cloth (along its normal) is covered
RAMP = float(globals().get("RAMP", 3.0))  # cm under the collar edge to full shrink
DILATE_CM = float(globals().get("DILATE_CM", 0.0))  # round 5b: uncovered face verts this close ABOVE the collar edge
# also shrink, EDGE_W fading to 0 at DILATE_CM (a turn brings the neck out right at the line, where nothing was covered)
EDGE_W = float(globals().get("EDGE_W", 0.0))
DILATE_W = float(globals().get("DILATE_W", EDGE_W))  # the dilated band's weight at the line (visible skin: keep small)  # the shrink weight AT the collar edge (round 5b: a turn exposes the
# neck right at the edge, where a 0 ramp start left it unshrunk; 0.3 = 30 % of SHRINK_CM there)
SHRINK_CM = float(globals().get("SHRINK_CM", 1.5))
SIZE = int(globals().get("SIZE", 1024))
OUT = globals().get("OUT") or "/srv/ue/reel/r5/garment/neck_hidden.png"
DEST = "/Game/Host/Fit"
WI = globals().get("WI", "")

AU, SP, MQ, LU = (unreal.GeometryScript_AssetUtils, unreal.GeometryScript_MeshSpatial, unreal.GeometryScript_MeshQueries,
                  unreal.GeometryScript_List)
EAL = unreal.EditorAssetLibrary


def pick(res, cls):
    items = res if isinstance(res, tuple) else (res,)
    return next((x for x in items if type(x).__name__ == cls), items[0])


def _names(name):
    """A property's spellings: the snake_case one, then the C++ one (an EditAnywhere-only UPROPERTY has no Python
    name; get/set_editor_property still find it by its C++ name: box, 06 Nov)."""
    camel = "".join(w[:1].upper() + w[1:] for w in name.split("_"))
    return [name, camel]


def gp(obj, name):
    err = None
    for n in _names(name):
        try:
            return obj.get_editor_property(n)
        except Exception as e:  # noqa: BLE001
            err = e
    raise err


def sp(obj, name, value):
    err = None
    for n in _names(name):
        try:
            obj.set_editor_property(n, value)
            return
        except Exception as e:  # noqa: BLE001
            err = e
    raise err


def dm_of(skm):
    dm = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_index", 0)
    AU.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
    return dm


def mask():
    from fmbridge.qa import image as I
    host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
                if a.get_actor_label() == LABEL)
    comps = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
    tee_c = comps.get(TEE) or next((c for n, c in comps.items() if n not in ("Face", "Body") and any(
        "shirt" in (m.get_name().lower() if m else "") for m in c.get_materials())), None)
    if tee_c is None:
        raise RuntimeError(f"no {TEE} component and none with a shirt material: TEE=<the garment's component> "
                           f"(components: {sorted(comps)})")
    face, tee = dm_of(comps["Face"].get_skeletal_mesh_asset()), dm_of(tee_c.get_skeletal_mesh_asset())
    V = list(LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(face, False), "GeometryScriptVectorList")))
    N = list(LU.convert_vector_list_to_array(pick(unreal.GeometryScript_Normals.get_mesh_per_vertex_normals(face),
                                                  "GeometryScriptVectorList")))
    # GetMeshPerVertexUVs: UE's camel-case splitter makes it get_mesh_per_vertex_u_vs (box, 06 Nov); either spelling
    uvs = getattr(unreal.GeometryScript_UVs, "get_mesh_per_vertex_u_vs", None) or \
        getattr(unreal.GeometryScript_UVs, "get_mesh_per_vertex_uvs")
    UV = list(LU.convert_uv_list_to_array(pick(uvs(face, 0), "GeometryScriptUVList")))
    all_ids = getattr(MQ, "get_all_triangle_i_ds", None) or getattr(MQ, "get_all_triangle_ids")
    tids = list(LU.convert_index_list_to_array(pick(all_ids(face), "GeometryScriptIndexList")))
    tris = []
    for t in tids:
        iv = pick(MQ.get_triangle_indices(face, t), "IntVector")
        tris.append((iv.x, iv.y, iv.z))
    TV = list(LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(tee, False), "GeometryScriptVectorList")))
    top = max(p.z for p in TV)
    bvh = pick(SP.build_bvh_for_mesh(tee), "GeometryScriptDynamicMeshBVH")
    q = unreal.GeometryScriptSpatialQueryOptions()
    cov = [False] * len(V)
    for i, (p, n) in enumerate(zip(V, N)):
        if p.z > top:
            continue
        ln = n.length() or 1.0
        hit = pick(SP.find_nearest_ray_intersection_with_mesh(tee, bvh, p, n * (1.0 / ln), q), "GeometryScriptRayHitResult")
        cov[i] = bool(hit.get_editor_property("hit")) and float(hit.get_editor_property("ray_parameter")) <= REACH
    # the collar edge: uncovered verts that share a triangle with a covered one
    edge = set()
    for a, b, c in tris:
        k = (cov[a], cov[b], cov[c])
        if any(k) and not all(k):
            edge.update(i for i in (a, b, c) if not cov[i])
    E = [V[i] for i in edge]
    w = [0.0] * len(V)
    for i, c in enumerate(cov):
        if c and E:
            d = min((V[i] - e).length() for e in E)
            w[i] = EDGE_W + (1.0 - EDGE_W) * max(0.0, min(1.0, d / RAMP))
    dil = 0
    if DILATE_CM > 0 and E:
        for i, c in enumerate(cov):
            if c or V[i].z > top:
                continue
            d = min((V[i] - e).length() for e in E)
            if d < DILATE_CM:
                w[i] = DILATE_W * (1.0 - d / DILATE_CM)
                dil += 1
    val = [1.0 - w[i] if (cov[i] or w[i] > 0) else 1.0 for i in range(len(V))]
    img = bytearray([255] * (SIZE * SIZE))
    drawn = 0
    for a, b, c in tris:
        if min(val[a], val[b], val[c]) >= 1.0:
            continue
        P = [(UV[i].x * SIZE, UV[i].y * SIZE, val[i]) for i in (a, b, c)]
        x0, x1 = int(max(0, min(p[0] for p in P))), int(min(SIZE - 1, max(p[0] for p in P) + 1))
        y0, y1 = int(max(0, min(p[1] for p in P))), int(min(SIZE - 1, max(p[1] for p in P) + 1))
        (ax, ay, av), (bx, by, bv), (cx, cy, cv) = P
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                l1 = ((by - cy) * (x + 0.5 - cx) + (cx - bx) * (y + 0.5 - cy)) / den
                l2 = ((cy - ay) * (x + 0.5 - cx) + (ax - cx) * (y + 0.5 - cy)) / den
                l3 = 1 - l1 - l2
                if min(l1, l2, l3) < -0.02:
                    continue
                # never 0: with MaxCullValue 0 a pixel at 0 CULLS; 1/255 still shrinks fully (weight 0.996)
                v = max(1, int(round(255 * max(0.0, min(1.0, l1 * av + l2 * bv + l3 * cv)))))
                j = y * SIZE + x
                if v < img[j]:
                    img[j] = v
                    drawn += 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    I.write(I.Image(SIZE, SIZE, 1, img), OUT)
    return {"tee_component": tee_c.get_name(), "face_verts": len(V), "covered": sum(cov), "edge_verts": len(edge), "dilated": dil, "full_shrink": sum(1 for x in w if x >= 1),
            "px_drawn": drawn, "png": OUT, "uv_valid": bool(UV) and len(UV) == len(V)}


def apply():
    if not WI:
        raise RuntimeError("WI= the default garment's wardrobe item (garment.hidden_face_maps / mh.palette)")
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", OUT)
    t.set_editor_property("destination_path", DEST)
    t.set_editor_property("destination_name", "T_Host_NeckHidden")
    for k in ("automated", "replace_existing", "save"):
        t.set_editor_property(k, True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    tex = EAL.load_asset(f"{DEST}/T_Host_NeckHidden")
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE)
    EAL.save_asset(f"{DEST}/T_Host_NeckHidden")
    dst = f"{DEST}/WI_Host_DefaultGarment_Neck"
    if not EAL.does_asset_exist(dst):
        EAL.duplicate_asset(WI, dst)
    wi = EAL.load_asset(dst)
    ed = gp(gp(wi, "pipeline"), "editor_pipeline")
    h = gp(ed, "head_hidden_face_map_texture")
    sp(h, "texture", tex)
    s = gp(h, "settings")
    # 0.0, not below: TryCombineHiddenFaceMaps rejects MaxCullValue < 0 as invalid and the WHOLE assembly fails
    # (MetaHumanGeometryRemoval.cpp:45-52; box, 06 Nov: Body/Face/grooms came out empty). The mask never goes
    # below 1/255, so nothing is culled
    sp(s, "max_cull_value", 0.0)
    sp(s, "min_keep_value", 0.9)
    sp(s, "max_shrink_distance", SHRINK_CM)
    sp(h, "settings", s)
    sp(ed, "head_hidden_face_map_texture", h)
    EAL.save_asset(dst)
    back = gp(ed, "head_hidden_face_map_texture")
    bs = gp(back, "settings")
    bt = gp(back, "texture")
    return {"wi": dst, "texture": tex.get_path_name(), "editor_pipeline": type(ed).__name__, "read_back": {
        "texture": bt.get_path_name() if bt else None,
        "max_cull_value": gp(bs, "max_cull_value"),
        "min_keep_value": gp(bs, "min_keep_value"),
        "max_shrink_distance": gp(bs, "max_shrink_distance")},
        "next": f"mh.add_item character=<his MH_> item={dst} slot=Outfits; mh.build; the re-dress chain (garment.md §5b)"}


result = mask() if STAGE == "mask" else apply()
