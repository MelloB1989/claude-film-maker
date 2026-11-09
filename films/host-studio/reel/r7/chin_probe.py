"""Round 7 (agent-02, for agent-13's hand_near_face row via agent-09): how far below the head bone the chin (soft-tissue
menton, the lowest point of the chin) sits, in z, on the Face mesh's REF pose. READ-ONLY on the level except a temp
SkeletalMeshActor (FMQA_R7Chin_*) at the origin, removed at the end. Numbers only come out (presenter geometry stays
on the box).

    film-ue exec -c "LABEL='Presenter'; exec(open('<tree>/films/host-studio/reel/r7/chin_probe.py').read())"

Menton (pure `menton`, tested off the box): the midline (|lateral| < MID_CM of the head bone, lateral from the Body's
ref-pose clavicles) is profiled top-down as its frontmost point per 0.5 cm of z; the pogonion is the lowest local
max of that profile within POG_CM of the nose tip's forward reach (an Adam's apple sits further back); the menton is
the lowest midline vertex below the pogonion and no more than BACK_CM behind it. chin_below_head_cm = head z - menton z.
"""
import json
import math

CHIN = "FMQA_R7Chin"


def menton(P, head, lat, up=(0.0, 0.0, 1.0), mid_cm=0.75, pog_cm=6.0, back_cm=3.0, bin_cm=0.5):
    """P: ref-pose vertex positions; head: head bone; lat: unit lateral (either sign). Forward is square to lat and
    up, signed toward the bulk of the face. Returns a dict of numbers relative to the head bone (cm), or None."""
    def d(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    fwd = (lat[1] * up[2] - lat[2] * up[1], lat[2] * up[0] - lat[0] * up[2], lat[0] * up[1] - lat[1] * up[0])
    rel = [(p[0] - head[0], p[1] - head[1], p[2] - head[2]) for p in P]
    if sum(d(r, fwd) for r in rel) < 0:
        fwd = (-fwd[0], -fwd[1], -fwd[2])
    mid = [(d(r, fwd), d(r, up)) for r in rel if abs(d(r, lat)) < mid_cm and d(r, fwd) > 0]
    if not mid:
        return None
    prof = {}
    for f, z in mid:
        k = math.floor(z / bin_cm)
        if k not in prof or f > prof[k][0]:
            prof[k] = (f, z)
    rows = [prof[k] for k in sorted(prof, reverse=True)]           # top -> down
    i_nose = max(range(len(rows)), key=lambda i: rows[i][0])
    f_nose = rows[i_nose][0]
    peaks = [i for i in range(i_nose + 1, len(rows) - 1)
             if rows[i][0] >= rows[i - 1][0] and rows[i][0] >= rows[i + 1][0] and rows[i][0] > f_nose - pog_cm]
    if not peaks:
        return None
    f_pog, z_pog = rows[peaks[-1]]
    low = [z for f, z in mid if z < z_pog and f >= f_pog - back_cm]
    if not low:
        return None
    z_men = min(low)
    alt = {f"back_{b}": round(-min(z for f, z in mid if z < z_pog and f >= f_pog - b), 2) for b in (2.0, 4.0)}
    return {"chin_below_head_cm": round(-z_men, 2), "pogonion_below_head_cm": round(-z_pog, 2),
            "pogonion_fwd_cm": round(f_pog, 2), "nose_fwd_cm": round(f_nose, 2), "chin_below_head_alt": alt,
            "midline_verts": len(mid)}


def _run(G):
    import unreal
    MQ, LU, SU = unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List, unreal.GeometryScript_SceneUtils
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    def pick(res, cls):
        items = res if isinstance(res, tuple) else (res,)
        return next((x for x in items if type(x).__name__ == cls), items[0])

    def loc(c, bone):
        if c.get_bone_index(bone) < 0:
            raise RuntimeError(f"{c.get_skeletal_mesh_asset().get_path_name()} has no bone {bone}")
        v = c.get_socket_location(bone)
        return (v.x, v.y, v.z)

    def verts(c):
        opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
        lod = unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
        lod.set_editor_property("lod_index", 0)
        opts.set_editor_property("requested_lod", lod)
        dm = unreal.DynamicMesh()
        SU.copy_mesh_from_component(c, dm, opts, True)
        return [(p.x, p.y, p.z) for p in LU.convert_vector_list_to_array(
            pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList"))]

    def cleanup():
        for a in list(EAS.get_all_level_actors()):
            if a.get_actor_label().startswith(CHIN):
                EAS.destroy_actor(a)

    label = G.get("LABEL", "Presenter")
    host = next(a for a in EAS.get_all_level_actors() if a.get_actor_label() == label)
    cs = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
    out = {"label": label}
    cleanup()
    try:
        ref = {}
        for n in ("Body", G.get("FACE", "Face")):
            ra = EAS.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
            ra.set_actor_label(f"{CHIN}_{n}")
            rc = ra.get_editor_property("skeletal_mesh_component")
            rc.set_skeletal_mesh_asset(cs[n].get_skeletal_mesh_asset())
            ref[n] = rc
            out[f"{n.lower()}_mesh"] = cs[n].get_skeletal_mesh_asset().get_path_name()
        body, face = ref["Body"], ref[G.get("FACE", "Face")]
        if math.dist(loc(body, "neck_01"), loc(body, "spine_05")) < 2.0:
            raise RuntimeError("the temp ref-pose actor has no pose yet: run again")
        lv = [a - b for a, b in zip(loc(body, "clavicle_l"), loc(body, "clavicle_r"))]
        n = math.sqrt(sum(x * x for x in lv))
        head = loc(face, "head")
        out["face_head_vs_body_head_cm"] = round(math.dist(head, loc(body, "head")), 2)
        out.update(menton(verts(face), head, tuple(x / n for x in lv)) or {"error": "no menton found"})
    finally:
        cleanup()
    return out


if __name__ != "__main__" and "LABEL" in globals():
    result = _run({k: globals()[k] for k in ("LABEL", "FACE") if k in globals()})
    print("CHIN " + json.dumps(result))
