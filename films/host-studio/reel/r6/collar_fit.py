"""Round 6, K1 (agent-02): fit Epic's collar to HIS neck, not his neck to the collar (r5/garment.md §10).

Round 5b proved the neck a FIT problem: Epic's default tee, as MetaHuman resized it to his body, has a collar ring
SMALLER than his face mesh's neck at the collar line (neck_px 296, up to ~1.9 cm deep on the S15 turn), and the face
shrink backstop only trades that poke for a gap and a torn open edge. This tool enlarges the collar instead:

  1. MEASURE, over every frame of his shots (default S13/S15/S17/S18, every STEP frames + the known neck frames), in
     a TORSO-rigid neck frame (spine_05's transform applied to the rest neck axis neck_01 -> head; angle round it
     from spine_05, so the tee's collar keeps its coordinates frame to frame): per angle sector (15 deg) and height
     bin (0.5 cm) the face's outer neck radius and the tee's inner radius. need = face + CLEAR - tee.
  2. PUSH, on a COPY of the mesh his BP renders (the assembled, resized garment: the SkeletalMesh component's own
     asset, so MetaHuman's resizing is kept; round 5's Fit6/8B floated because they edited the unresized asset):
     every tee vertex moves radially out by P(angle, height) = max over measured bins of need x K(height
     difference), K = 1 from the bin's height up to the top and RIB_CM below it (the rib band moves as one: its
     height and thickness are kept, both walls move the same), then a cosine to 0 over FALL_CM down the tee. Sectors
     are smoothed (max over +-1, then 1-2-1), so the collar stays round, never lumpy. Nothing else moves.
  3. VERIFY: the copy's rest shape moved only in the collar region; posed (dressed as Tee, vs Epic's SkeletalMesh)
     it matches his worn tee everywhere outside the collar (skin weights survived the write-back); and the measure
     re-run on the dressed copy reads need <= 0 everywhere (no face outside the collar on any frame) BEFORE qa.clip.

The face it measures must be UNSHRUNK: either after the no-shrink rebuild (the backstop off), or FACE_REF = his
unpacked face mesh on a temp actor leader-posed to his Face (the box still carries loop 2's 3 cm shrink).

Face rule: everything runs on the box; the copy is a project asset (private s3 only). The JSON written here holds
radii (numbers), never images.

Driver (where film-ue runs; --box picks the workstation, never the default):
    cd tools && uv run python ../films/host-studio/reel/r6/collar_fit.py --box <instance> measure \
        --face-ref /Game/.../SKM_Host_Op_FaceMesh --out /work/r6neck/m1
    ... push --from /work/r6neck/m1 --dest /Game/Host/Fit/SKM_Host_Tee_R6Collar
    ... measure --tee Tee --out /work/r6neck/m2        (after mh.dress: need <= 0 everywhere)
Editor-side stages (film-ue exec -c "STAGE='setup'; ...; exec(open('<tree>/.../collar_fit.py').read())"):
    setup | frame | push | verify | cleanup
"""
import json
import math

NS = 24  # angle sectors (15 deg)
T0, T1, DT = -12.0, 8.0, 0.5  # height bins along the neck axis from neck_01, cm
NB = int(round((T1 - T0) / DT))
R_MAX = 16.0  # cm from the neck axis: farther is shoulder/chest, never the collar
REF_FACE = "FMQA_NeckRefFace"
REF_BODY = "FMQA_NeckRestBody"
NEW_TEE = "FMQA_NeckTee"


def _sector(th: float) -> int:
    return int((th % 360.0) // (360.0 / NS)) % NS


def _bin(t: float) -> int:
    return int((t - T0) // DT)


# ---------------------------------------------------------------------------------------- pure (tested off the box)
def smooth_sectors(p: list) -> list:
    """Circular max over +-1 sector, then a 1-2-1 average: a round collar, no lump at one sector."""
    n = len(p)
    m = [max(p[(i - 1) % n], p[i], p[(i + 1) % n]) for i in range(n)]
    return [(m[(i - 1) % n] + 2 * m[i] + m[(i + 1) % n]) / 4.0 for i in range(n)]


def kernel(d: float, rib: float, fall: float) -> float:
    """Weight at a height d (cm) above a bin that needs a push (d < 0: below it): 1 at and above it and RIB below
    it (the rib band moves whole), then a cosine to 0 over FALL."""
    if d >= -rib:
        return 1.0
    x = (-d - rib) / max(fall, 1e-6)
    return 0.5 * (1.0 + math.cos(math.pi * x)) if x < 1.0 else 0.0


def push_grid(need: list, rib: float = 2.0, fall: float = 4.5) -> list:
    """need[s][b] (cm, None = not measured) -> P[s][b] >= 0: per sector, max over bins of need x kernel, then
    the sectors smoothed bin by bin."""
    P = []
    for s in range(NS):
        col = need[s]
        row = []
        for b in range(NB):
            tb = T0 + (b + 0.5) * DT
            v = 0.0
            for b2, n in enumerate(col):
                if n is None or n <= 0:
                    continue
                v = max(v, n * kernel(tb - (T0 + (b2 + 0.5) * DT), rib, fall))
            row.append(v)
        P.append(row)
    for b in range(NB):
        sm = smooth_sectors([P[s][b] for s in range(NS)])
        for s in range(NS):
            P[s][b] = sm[s]
    return P


def sample(P: list, th: float, t: float) -> float:
    """P at an angle (deg) and height (cm), bilinear (sectors wrap; outside the bins 0)."""
    x = (th % 360.0) / (360.0 / NS) - 0.5
    y = (t - T0) / DT - 0.5
    if y < -0.5 or y > NB - 0.5:
        return 0.0
    s0 = math.floor(x)
    b0 = max(0, min(NB - 1, math.floor(y)))
    b1 = max(0, min(NB - 1, b0 + 1))
    fx, fy = x - s0, min(1.0, max(0.0, y - b0))
    s0, s1 = s0 % NS, (s0 + 1) % NS
    return ((1 - fx) * (1 - fy) * P[s0][b0] + fx * (1 - fy) * P[s1][b0] + (1 - fx) * fy * P[s0][b1]
            + fx * fy * P[s1][b1])


def worst_need(frames: dict, clear: float) -> tuple:
    """frames {frame: {"face": [[r|None]*NB]*NS, "tee": [...]}} -> (need[s][b] worst over frames, where[s][b])."""
    need = [[None] * NB for _ in range(NS)]
    where = [[None] * NB for _ in range(NS)]
    for f, g in frames.items():
        F, T = g["face"], g["tee"]
        for s in range(NS):
            for b in range(NB):
                if F[s][b] is None or T[s][b] is None:
                    continue
                n = F[s][b] + clear - T[s][b]
                if need[s][b] is None or n > need[s][b]:
                    need[s][b], where[s][b] = n, f
    return need, where


def summarize(need: list, where: list, P: list | None = None) -> dict:
    """Per sector: worst need, its height and frame, and the push at the collar."""
    rows = []
    for s in range(NS):
        best = max(((n, b) for b, n in enumerate(need[s]) if n is not None), default=None)
        row = {"sector_deg": s * 360 // NS}
        if best:
            row.update({"need_cm": round(best[0], 2), "t_cm": T0 + (best[1] + 0.5) * DT, "frame": where[s][best[1]]})
        if P is not None:
            row["push_max_cm"] = round(max(P[s]), 2)
        rows.append(row)
    pos = [r["need_cm"] for r in rows if r.get("need_cm") is not None]
    return {"sectors": rows, "worst_need_cm": round(max(pos), 2) if pos else None,
            "sectors_poking": sum(1 for x in pos if x > 0)}


# ------------------------------------------------------------------------------------------------ editor side
def _editor(G: dict):
    import unreal
    AU, MQ, LU, SU = (unreal.GeometryScript_AssetUtils, unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List,
                      unreal.GeometryScript_SceneUtils)
    EAL = unreal.EditorAssetLibrary
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    W = unreal.RelativeTransformSpace.RTS_WORLD
    label = G.get("LABEL", "Host")

    def pick(res, cls):
        items = res if isinstance(res, tuple) else (res,)
        return next((x for x in items if type(x).__name__ == cls), items[0])

    def actor(lab):
        return next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == lab), None)

    def comps(a):
        return {c.get_name(): c for c in a.get_components_by_class(unreal.SkeletalMeshComponent)}

    def tee_comp(cs):
        want = G.get("TEE", "")
        if want:
            if want in cs:
                return cs[want]
            ref = actor(want)  # a temp actor's label (NEW_TEE)
            if ref:
                return ref.get_editor_property("skeletal_mesh_component")
            raise RuntimeError(f"no tee component {want}: {sorted(cs)}")
        return cs.get("Tee") or cs["SkeletalMesh"]

    def posed(c):
        opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
        lod = unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
        lod.set_editor_property("lod_index", 0)
        opts.set_editor_property("requested_lod", lod)
        dm = unreal.DynamicMesh()
        SU.copy_mesh_from_component(c, dm, opts, True)
        return dm

    def verts(dm):
        return list(LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(dm, False),
                                                         "GeometryScriptVectorList")))

    def asset_dm(skm):
        dm = unreal.DynamicMesh()
        lod = unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property("lod_index", 0)
        AU.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
        return dm

    def inv_pos(T, p):
        return T.inverse_transform_location(p)

    def spawn(lab, mesh, at=None):
        old = actor(lab)
        if old:
            EAS.destroy_actor(old)
        loc = at.get_actor_location() if at else unreal.Vector(0, 0, 0)
        rot = at.get_actor_rotation() if at else unreal.Rotator(0, 0, 0)
        x = EAS.spawn_actor_from_class(unreal.SkeletalMeshActor, loc, rot)
        x.set_actor_label(lab)
        c = x.get_editor_property("skeletal_mesh_component")
        c.set_skeletal_mesh_asset(mesh)
        return x, c

    class Frame:
        """The torso-rigid neck frame, stored in spine_05's local space."""

        def __init__(self, d):
            self.o, self.u, self.e1, self.e2 = (unreal.Vector(*d[k]) for k in ("o", "u", "e1", "e2"))

        def cyl(self, q):  # spine-local point -> (t, r, theta deg, unit radial)
            v = q - self.o
            t = v.dot(self.u)
            w = v - self.u * t
            r = w.length()
            th = math.degrees(math.atan2(w.dot(self.e2), w.dot(self.e1))) % 360.0
            return t, r, th, (w * (1.0 / r) if r > 1e-6 else self.e1)

    def grids(pts, T, fr, keep_max: bool):
        g = [[None] * NB for _ in range(NS)]
        for p in pts:
            t, r, th, _ = fr.cyl(inv_pos(T, p))
            if r > R_MAX or not (T0 <= t < T1):
                continue
            s, b = _sector(th), _bin(t)
            cur = g[s][b]
            if cur is None or (r > cur if keep_max else r < cur):
                g[s][b] = r
        return [[None if x is None else round(x, 3) for x in row] for row in g]

    def pose_check(F, T):
        """Sanity per frame: the face's median radius 2-4 cm above neck_01 (his neck: ~5-7 cm; a face read at rest
        while the body moves reads far off) and how many face verts fall in that slab at all."""
        fr0 = Frame(G["FRAME"])
        rs = sorted(fr0.cyl(inv_pos(T, p))[1] for p in F[::5] if 2.0 <= fr0.cyl(inv_pos(T, p))[0] <= 4.0)
        return {"neck_r_p50": round(rs[len(rs) // 2], 2) if rs else None, "n": len(rs)}

    stage = G.get("STAGE", "setup")
    host = actor(label)
    cs = comps(host)
    body = cs["Body"]

    if stage == "setup":
        # the rest neck frame: his Body mesh unanimated at the origin (ref pose), in spine_05's local space
        rb, rc = spawn(REF_BODY, body.get_skeletal_mesh_asset())
        Ts = rc.get_socket_transform("spine_05", W)
        o, hd = inv_pos(Ts, rc.get_socket_location("neck_01")), inv_pos(Ts, rc.get_socket_location("head"))
        u = hd - o
        if u.length() < 2.0:  # a just-spawned component without bone transforms reads every socket at its origin
            EAS.destroy_actor(rb)
            raise RuntimeError(f"rest neck_01 -> head is {u.length():.2f} cm: the temp Body has no ref pose yet; "
                               "run setup again")
        u = u * (1.0 / (u.length() or 1.0))
        x = Ts.inverse_transform_direction(unreal.Vector(1, 0, 0))
        e1 = x - u * x.dot(u)
        e1 = e1 * (1.0 / (e1.length() or 1.0))
        e2 = u.cross(e1)
        fy = Ts.inverse_transform_direction(unreal.Vector(0, -1, 0))  # report only: where -Y (his front?) falls
        frame = {"o": [o.x, o.y, o.z], "u": [u.x, u.y, u.z], "e1": [e1.x, e1.y, e1.z], "e2": [e2.x, e2.y, e2.z],
                 "minus_y_deg": round(math.degrees(math.atan2(fy.dot(e2), fy.dot(e1))) % 360.0, 1),
                 "spine05_rest": [Ts.translation.x, Ts.translation.y, Ts.translation.z]}
        EAS.destroy_actor(rb)
        out = {"frame": frame, "tee_component": tee_comp(cs).get_name(),
               "tee_mesh": tee_comp(cs).get_skeletal_mesh_asset().get_path_name(),
               "face_mesh": cs["Face"].get_skeletal_mesh_asset().get_path_name()}
        if G.get("FACE_REF"):
            m = EAL.load_asset(G["FACE_REF"])
            if not isinstance(m, unreal.SkeletalMesh):
                raise RuntimeError(f"FACE_REF {G['FACE_REF']} is not a skeletal mesh")
            fa, fc = spawn(REF_FACE, m, host)
            fc.set_world_transform(cs["Face"].get_world_transform(), False, False)
            fc.set_leader_pose_component(cs["Face"], True)
            out["face_ref"] = m.get_path_name()
        rest = asset_dm(tee_comp(cs).get_skeletal_mesh_asset())
        out["tee_rest_inner"] = grids(verts(rest), Ts, Frame(frame), keep_max=False)  # actor at identity: Ts = rest
        return out

    fr = Frame(G["FRAME"])
    if stage == "frame":
        Ts = body.get_socket_transform("spine_05", W)
        ref = actor(REF_FACE)
        fc = ref.get_editor_property("skeletal_mesh_component") if ref else cs["Face"]
        F = verts(posed(fc))
        out = {"face": grids(F, Ts, fr, keep_max=True), "tee": grids(verts(posed(tee_comp(cs))), Ts, fr, keep_max=False),
               "neck01_w": [round(c, 2) for c in (lambda v: (v.x, v.y, v.z))(body.get_socket_location("neck_01"))],
               "head_w": [round(c, 2) for c in (lambda v: (v.x, v.y, v.z))(body.get_socket_location("head"))],
               "face_src": "ref" if ref else "Face", "pose": pose_check(F, Ts)}
        if ref and G.get("CHECK_REF"):  # the ref face vs the worn face above the collar: ~0 when they agree
            live = verts(posed(cs["Face"]))
            hi = [p for p in live if fr.cyl(inv_pos(Ts, p))[0] > 3.0]
            dm = posed(fc)
            SP = unreal.GeometryScript_MeshSpatial
            bvh = pick(SP.build_bvh_for_mesh(dm), "GeometryScriptDynamicMeshBVH")
            q = unreal.GeometryScriptSpatialQueryOptions()
            d = sorted((p - pick(SP.find_nearest_point_on_mesh(dm, bvh, p, q), "GeometryScriptTrianglePoint")
                        .get_editor_property("position")).length() for p in hi[::7])
            out["ref_vs_face_above_t3"] = {"n": len(d), "p50": round(d[len(d) // 2], 3) if d else None,
                                           "p95": round(d[int(0.95 * (len(d) - 1))], 3) if d else None}
        return out

    if stage == "push":
        src = tee_comp(cs).get_skeletal_mesh_asset()
        dest = G["DEST"]
        P = G["PUSH"]
        if EAL.does_asset_exist(dest):
            raise RuntimeError(f"{dest} exists: pass a new DEST (never overwrite a rendered asset)")
        dup = EAL.duplicate_asset(src.get_path_name().split(".")[0], dest)
        if dup is None:
            raise RuntimeError(f"duplicate {src.get_path_name()} -> {dest} failed")
        rb, rc = spawn(REF_BODY, body.get_skeletal_mesh_asset())
        Ts = rc.get_socket_transform("spine_05", W)
        EAS.destroy_actor(rb)
        dm = asset_dm(dup)
        V = verts(dm)
        ME = unreal.GeometryScript_MeshBasicEditing
        moved, mx, zone = 0, 0.0, {"t_min": None, "t_max": None, "r_max": 0.0}
        for i, p in enumerate(V):
            q = inv_pos(Ts, p)
            t, r, th, rad = fr.cyl(q)
            if r > R_MAX:
                continue
            d = sample(P, th, t)
            if d <= 0.005:
                continue
            ME.set_vertex_position(dm, i, Ts.transform_location(q + rad * d), True)
            moved += 1
            mx = max(mx, d)
            zone["t_min"] = t if zone["t_min"] is None else min(zone["t_min"], t)
            zone["t_max"] = t if zone["t_max"] is None else max(zone["t_max"], t)
            zone["r_max"] = max(zone["r_max"], r)
        opts = unreal.GeometryScriptCopyMeshToAssetOptions()
        for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", False),
                     ("enable_remove_degenerates", False), ("use_original_vertex_order", True),
                     ("replace_materials", False)):
            try:
                opts.set_editor_property(k, v)
            except Exception:  # noqa: BLE001  (not every 5.x has every flag)
                pass
        lod = unreal.GeometryScriptMeshWriteLOD()
        lod.set_editor_property("lod_index", 0)
        AU.copy_mesh_to_skeletal_mesh(dm, dup, opts, lod)
        EAL.save_asset(dest)
        # proof 1: rest shape, by surface: what moved, and nothing outside the collar zone
        back = verts(asset_dm(dup))
        orig = verts(asset_dm(src))
        d_rest = sorted((a - b).length() for a, b in zip(back, orig)) if len(back) == len(orig) else None
        mats = {str(s): (m.get_path_name() if m else None) for s, m in zip(tee_comp(cs).get_material_slot_names(),
                                                                          tee_comp(cs).get_materials())}
        return {"dest": dest, "src": src.get_path_name(), "verts": [len(back), len(orig)], "moved_verts": moved,
                "max_push_cm": round(mx, 3), "zone": {k: (round(v, 2) if v is not None else None)
                                                      for k, v in zone.items()},
                "rest_moved_gt_0.01": sum(1 for x in d_rest if x > 0.01) if d_rest else "vertex count changed",
                "rest_max_cm": round(d_rest[-1], 3) if d_rest else None, "slots_as_worn": mats,
                "lods": dup.get_lod_num() if hasattr(dup, "get_lod_num") else None}

    if stage == "verify":
        # after mh.dress: the copy (component Tee) vs Epic's (SkeletalMesh), both posed as worn, by surface; outside
        # the collar zone ~0 = the skin weights survived the write-back. (Not a temp actor on leader pose: a
        # follower spawned by a script is NOT posed when read on the CPU: round 6 S1 read his face ref at rest, and
        # qa.garment_look's ref body read nonsense in round 5 for the same reason)
        Ts = body.get_socket_transform("spine_05", W)
        A = verts(posed(cs[G.get("NEW", "Tee")]))
        dm = posed(cs[G.get("OLD", "SkeletalMesh")])
        SP = unreal.GeometryScript_MeshSpatial
        bvh = pick(SP.build_bvh_for_mesh(dm), "GeometryScriptDynamicMeshBVH")
        q = unreal.GeometryScriptSpatialQueryOptions()
        inside, outside = [], []
        lo = float(G.get("ZONE_T_MIN", -12.0))
        for p in A[::3]:
            t, r, _, _ = fr.cyl(inv_pos(Ts, p))
            d = (p - pick(SP.find_nearest_point_on_mesh(dm, bvh, p, q), "GeometryScriptTrianglePoint")
                 .get_editor_property("position")).length()
            (inside if (r <= R_MAX and t >= lo - 1.0) else outside).append(d)
        inside.sort()
        outside.sort()

        def st(x):
            return {"n": len(x), "p50": round(x[len(x) // 2], 3), "p99": round(x[int(0.99 * (len(x) - 1))], 3),
                    "max": round(x[-1], 3)} if x else {"n": 0}
        return {"collar_zone": st(inside), "elsewhere": st(outside)}

    if stage == "cleanup":
        gone = []
        for lab in (REF_FACE, REF_BODY, NEW_TEE):
            a = actor(lab)
            if a:
                EAS.destroy_actor(a)
                gone.append(lab)
        return {"removed": gone}
    raise RuntimeError(f"STAGE {stage}?")


# ------------------------------------------------------------------------------------------------ driver
def _exec(client, stage: str, **g) -> dict:
    src = open(__file__).read()
    code = f"import json as _j\n_G = _j.loads({json.dumps(json.dumps({'STAGE': stage, **g}))})\n{src}\nresult = _editor(_G)\n"
    r = client.exec_code(code, timeout=900)
    if not r.get("ok"):
        raise SystemExit(f"{stage}: {json.dumps(r)[:2000]}")
    return r["result"]


def his_frames(client, seq: str, shots: list, step: int, extra: list) -> list:
    r = client.op("seq.cuts", path=seq)
    if not r.get("ok"):
        raise SystemExit(f"seq.cuts: {r}")
    cuts = {c: (int(s), int(e)) for c, s, e in r["result"]}
    out = set(extra)
    for sh in shots:
        s, e = cuts[sh]
        out |= set(range(s, e, step)) | {e - 1}
    return sorted(out)


def main(argv=None) -> int:
    import argparse
    import os
    import sys
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", required=True, help="the workstation profile (FILM_UE_BOX) to talk to; 'conf' = the "
                    "default film-ue.json of the conf dir in use (a driver's private dir holding one box's profile)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--out", required=True)
    m.add_argument("--face-ref", default="", help="UNRELIABLE (round 6 S1): a script-spawned leader-pose follower reads at rest on the CPU; measure the live Face after backstop_off instead")
    m.add_argument("--tee", default="", help="component (Tee / SkeletalMesh) or the temp copy actor FMQA_NeckTee")
    m.add_argument("--seq", default="/Game/Reel/SEQ_Reel")
    m.add_argument("--shots", default="Reel_S13,Reel_S15,Reel_S17,Reel_S18")
    m.add_argument("--step", type=int, default=3)
    m.add_argument("--extra", default="985,1040,1082,1085,1100,1104,1128,1150,1152,1175,1198,1340,1390,1397,1404,"
                   "1442,1500")
    m.add_argument("--clear", type=float, default=0.3)
    m.add_argument("--frames", default="", help="only these frames (comma list)")
    p = sub.add_parser("push")
    p.add_argument("--from", dest="src", required=True, help="a measure --out dir")
    p.add_argument("--dest", required=True)
    p.add_argument("--rib", type=float, default=2.0)
    p.add_argument("--fall", type=float, default=4.5)
    p.add_argument("--seq", default="/Game/Reel/SEQ_Reel")
    v = sub.add_parser("verify", help="after mh.dress: Tee vs SkeletalMesh posed, elsewhere ~0")
    v.add_argument("--from", dest="src", required=True)
    v.add_argument("--frames", default="1128,1397")
    v.add_argument("--seq", default="/Game/Reel/SEQ_Reel")
    sub.add_parser("cleanup")
    a = ap.parse_args(argv)
    if a.box != "conf":
        os.environ["FILM_UE_BOX"] = a.box
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
    from filmtools.unreal import client

    if a.cmd == "cleanup":
        print(json.dumps(_exec(client, "cleanup"), indent=1))
        return 0
    if a.cmd == "measure":
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        g = {"FACE_REF": a.face_ref, "TEE": a.tee}
        setup = _exec(client, "setup", **g)
        (out / "setup.json").write_text(json.dumps(setup))
        print(json.dumps({k: v for k, v in setup.items() if k != "tee_rest_inner"}, indent=1))
        frames = ([int(x) for x in a.frames.split(",")] if a.frames else
                  his_frames(client, a.seq, a.shots.split(","), a.step, [int(x) for x in a.extra.split(",") if x]))
        per, last = {}, None
        for i, f in enumerate(frames):
            for ff in (f + 1, f):
                r = client.op("seq.scrub", path=a.seq, frame=ff)
                if not r.get("ok"):
                    raise SystemExit(f"seq.scrub {ff}: {r}")
            g2 = {**g, "FRAME": setup["frame"], "CHECK_REF": bool(a.face_ref) and i == 0}
            res = _exec(client, "frame", **g2)
            if res.get("ref_vs_face_above_t3"):
                print("ref face vs worn face above the collar:", res["ref_vs_face_above_t3"])
            if last is not None and res["head_w"] == last:
                print(f"WARN f{f}: head bone did not move since the last frame (pose not updated?)")
            last = res["head_w"]
            per[f] = res
            if i % 20 == 0:
                print(f"{i + 1}/{len(frames)} f{f}", flush=True)
        (out / "frames.json").write_text(json.dumps(per))
        need, where = worst_need(per, a.clear)
        s = summarize(need, where)
        fw = []
        for f, g in per.items():
            n1, _ = worst_need({f: g}, a.clear)
            w = max((x for row in n1 for x in row if x is not None), default=None)
            fw.append((w if w is not None else -99, f, g.get("pose")))
        fw.sort(reverse=True)
        s["worst_frames"] = [{"frame": f, "need_cm": round(w, 2), "pose": p} for w, f, p in fw[:12]]
        s["median_frame_need_cm"] = round(sorted(w for w, _, _ in fw)[len(fw) // 2], 2) if fw else None
        (out / "need.json").write_text(json.dumps({"need": need, "where": where, "clear": a.clear,
                                                   "frames": frames, "summary": s}))
        print(json.dumps(s, indent=1))
        return 0
    if a.cmd == "verify":
        src = Path(a.src)
        setup = json.loads((src / "setup.json").read_text())
        res = json.loads((src / "push.json").read_text())["result"]
        for f in (int(x) for x in a.frames.split(",") if x):
            for ff in (f + 1, f):
                client.op("seq.scrub", path=a.seq, frame=ff)
            v = _exec(client, "verify", FRAME=setup["frame"], ZONE_T_MIN=res["zone"]["t_min"] or -12.0)
            print(f"verify f{f}:", json.dumps(v))
        return 0
    # push
    src = Path(a.src)
    nd = json.loads((src / "need.json").read_text())
    setup = json.loads((src / "setup.json").read_text())
    P = push_grid(nd["need"], a.rib, a.fall)
    print(json.dumps(summarize(nd["need"], nd["where"], P)["sectors"]))
    res = _exec(client, "push", FRAME=setup["frame"], PUSH=P, DEST=a.dest, TEE="")
    print(json.dumps(res, indent=1))
    print("next: mh.dress the copy as Tee, then: collar_fit.py --box .. verify --from", a.src)
    (src / "push.json").write_text(json.dumps({"P": P, "rib": a.rib, "fall": a.fall, "result": res}))
    return 0


if __name__ == "__main__" and "_G" not in globals():
    try:
        import unreal  # noqa: F401
    except ImportError:
        raise SystemExit(main())
    result = _editor(globals())  # film-ue exec FILE with STAGE=... set in -c
