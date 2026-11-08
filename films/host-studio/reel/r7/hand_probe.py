"""Round 7 (agent-02, for agent-13's move.rest_contact_bad_frames): how high the hand_<s> joint head (the wrist) and
the <finger>_01 joint heads sit above a flat surface the hand rests on palm-down, from the Body mesh's REF pose.
READ-ONLY on the level except a temp SkeletalMeshActor (FMQA_R7Hand_*) at the origin, removed at the end. Numbers
only come out (presenter geometry stays on the box).

    film-ue exec -c "LABEL='Presenter'; exec(open('<tree>/films/host-studio/reel/r7/hand_probe.py').read())"

Per hand, the skin of the palm and fingers (thumb and forearm left out, by the nearest bone segment) is projected on
the plane along the hand (hand -> middle_01) x its palm normal (the side the thumb tip sits on). `rest_heights` (pure,
tested off the box) finds the resting line: the edge of the projection's convex hull on the palm side that starts at
the heel of the palm (the hull's contact nearest the wrist) and runs distally; heights are taken square to it.
  heel_flat:   the surface square to the palm normal, touching the heel only (the hand tipped up off its fingers)
  heel_pads:   the surface touching the heel and the next contact out (the knuckle or finger pads, as the ref pose's
               fingers lie: its MCP/PIP flexion is printed so the reading can be judged against MCP ~20 / PIP ~30)
  dorsal_cm:   the wrist head's depth under the BACK of the hand (a check: the palm side must be the thicker one)
"""
import json
import math

HANDP = "FMQA_R7Hand"
FINGERS = ("index", "middle", "ring", "pinky")


def _hull_lower(pts):
    """Monotone chain: the hull chain with the LARGEST y (the palm side, y = toward the surface), left to right."""
    pts = sorted(set(pts))
    out = []
    for p in pts:
        while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                 - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) >= 0:
            out.pop()
        out.append(p)
    return out


def _height(j, a, b):
    """Distance of 2-D point j from the line ab, + when j is on the off-surface side (smaller y)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return ((j[0] - a[0]) * dy - (j[1] - a[1]) * dx) / L


def rest_heights(pts, joints, heel_x):
    """pts: [(x along the hand, y toward the palm surface)] of palm + finger skin; joints: {name: (x, y)} (the wrist
    at its own coordinates); heel_x: contacts at x <= heel_x count as the heel. Returns {heel_flat: {name: cm},
    heel_pads: {name: cm}, contacts: [[x, y] of the two contacts]}."""
    hull = _hull_lower(pts)
    heel = [p for p in hull if p[0] <= heel_x]
    if not heel:
        return None
    h0 = max(heel, key=lambda p: p[1])                       # the deepest heel point
    flat = {k: round(h0[1] - v[1], 2) for k, v in joints.items()}
    i = hull.index(h0)
    if i + 1 >= len(hull):
        return {"heel_flat": flat, "heel_pads": None, "contacts": [list(h0)]}
    h1 = hull[i + 1]                                         # the next contact distally along the palm-side hull
    pads = {k: round(_height(v, h0, h1), 2) for k, v in joints.items()}
    return {"heel_flat": flat, "heel_pads": pads, "contacts": [[round(h0[0], 2), round(h0[1], 2)],
                                                                [round(h1[0], 2), round(h1[1], 2)]],
            "tilt_deg": round(math.degrees(math.atan2(h1[1] - h0[1], h1[0] - h0[0])), 1)}


def _run(G):
    import unreal
    MQ, LU, SU = unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List, unreal.GeometryScript_SceneUtils
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    def pick(res, cls):
        items = res if isinstance(res, tuple) else (res,)
        return next((x for x in items if type(x).__name__ == cls), items[0])

    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

    def unit(a):
        n = math.sqrt(dot(a, a))
        return (a[0] / n, a[1] / n, a[2] / n)

    def seg_d(p, a, b):
        ab, ap = sub(b, a), sub(p, a)
        L = dot(ab, ab)
        t = max(0.0, min(1.0, dot(ap, ab) / L)) if L > 1e-12 else 0.0
        return math.dist(p, (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t))

    def ang(a, b, c):  # flexion at b: 0 = straight
        u, v = unit(sub(b, a)), unit(sub(c, b))
        return round(math.degrees(math.acos(max(-1.0, min(1.0, dot(u, v))))), 1)

    def cleanup():
        for a in list(EAS.get_all_level_actors()):
            if a.get_actor_label().startswith(HANDP):
                EAS.destroy_actor(a)

    label = G.get("LABEL", "Presenter")
    host = next(a for a in EAS.get_all_level_actors() if a.get_actor_label() == label)
    cs = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
    out = {"label": label, "body_mesh": cs["Body"].get_skeletal_mesh_asset().get_path_name(), "hands": {}}
    cleanup()
    try:
        ra = EAS.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        ra.set_actor_label(f"{HANDP}_Body")
        rc = ra.get_editor_property("skeletal_mesh_component")
        rc.set_skeletal_mesh_asset(cs["Body"].get_skeletal_mesh_asset())

        def loc(b):
            if rc.get_bone_index(b) < 0:
                raise RuntimeError(f"no bone {b}")
            v = rc.get_socket_location(b)
            return (v.x, v.y, v.z)

        if math.dist(loc("neck_01"), loc("spine_05")) < 2.0:
            raise RuntimeError("the temp ref-pose actor has no pose yet: run again")
        opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
        lod = unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
        lod.set_editor_property("lod_index", 0)
        opts.set_editor_property("requested_lod", lod)
        dm = unreal.DynamicMesh()
        SU.copy_mesh_from_component(rc, dm, opts, True)
        P = [(p.x, p.y, p.z) for p in LU.convert_vector_list_to_array(
            pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList"))]
        for sd in ("l", "r"):
            H = loc(f"hand_{sd}")
            segs = {"forearm": (loc(f"lowerarm_{sd}"), H)}
            j01 = {}
            for f in FINGERS + ("thumb",):
                chain = ([loc(f"{f}_metacarpal_{sd}")] if f != "thumb" else [H]) + \
                        [loc(f"{f}_0{k}_{sd}") for k in (1, 2, 3)]
                tip = tuple(c + (c - b) for b, c in zip(chain[-2], chain[-1]))
                chain = ([H] if f != "thumb" else []) + chain + [tip]
                for k, (a, b) in enumerate(zip(chain, chain[1:])):
                    segs[f"{f}:{k}"] = (a, b)
                if f != "thumb":
                    j01[f] = chain[2]                      # <finger>_01's head (H, metacarpal, _01, ...)
            u = unit(sub(loc(f"middle_01_{sd}"), H))
            lat = sub(j01["index"], j01["pinky"])
            lat = unit(sub(lat, tuple(x * dot(lat, u) for x in u)))
            n = cross(u, lat)
            if dot(sub(loc(f"thumb_03_{sd}"), H), n) < 0:
                n = (-n[0], -n[1], -n[2])                  # palm side: where the thumb tip sits
            pts = []
            for p in P:
                if math.dist(p, H) > 25.0:
                    continue
                best = min(segs, key=lambda k: seg_d(p, *segs[k]))
                if best == "forearm" or best.startswith("thumb"):
                    continue
                q = sub(p, H)
                pts.append((dot(q, u), dot(q, n)))
            joints = {"hand": (0.0, 0.0)}
            joints.update({f"{f}_01": (dot(sub(j, H), u), dot(sub(j, H), n)) for f, j in j01.items()})
            L = dot(sub(j01["middle"], H), u)
            r = rest_heights(pts, joints, 0.4 * L) or {"error": "no heel contact"}
            r["dorsal_cm"] = round(-min(y for x, y in pts if x <= 0.4 * L), 2) if pts else None
            r["palm_len_cm"] = round(L, 2)
            r["ref_flexion_deg"] = {f: {"mcp": ang(loc(f"{f}_metacarpal_{sd}"), loc(f"{f}_01_{sd}"),
                                                   loc(f"{f}_02_{sd}")),
                                        "pip": ang(loc(f"{f}_01_{sd}"), loc(f"{f}_02_{sd}"), loc(f"{f}_03_{sd}"))}
                                    for f in FINGERS}
            r["skin_pts"] = len(pts)
            out["hands"][sd] = r
    finally:
        cleanup()
    return out


if __name__ != "__main__" and "LABEL" in globals():
    result = _run({k: globals()[k] for k in ("LABEL",) if k in globals()})
    print("HAND " + json.dumps(result))
