"""Round 7 (agent-05): slim HIS outfit's flank under the relaxed upper arm (orchestrator ruling A, 08-09 Nov).

His relaxed upper arms sit up to ~8 cm inside his outfit's flank (agent-02: l -7.87 at f84, arm_t 0.46, flank +79
deg, 32 cm up the spine; r -6.59 at f0). The split: agent-01 opens the elbows (up to ~20-25 deg abduction at rest),
this tool takes the REMAINDER out of the cloth, capped (CAP, <= ~4 cm), blended so no dent reads from the front
cameras. The same method as her waist: measured on the posed frames, solved per vertex, carried back to the bind pose.

  1. MEASURE (driver: seq.scrub each frame, then the editor's 'frame' stage): each torso vertex of the outfit (nearer
     the spine than the upper arm on the ref pose, as agent-02's SLEEVES=1 split; between the hips and the shoulders,
     on that arm's side), posed: its offset from the upper arm's
     axis (upperarm -> lowerarm, posed sockets) in the arm's cross-section. The arm is a tube of its own measured
     radius R(t) (her/his body's REF mesh, the arm-weighted verts' p90 radius per 5 % of the upper arm). need = how
     far the vertex must move toward his spine axis (MEDIAL: perpendicular to the arm, toward the spine line
     spine_03 -> spine_05) to sit outside the tube by MARGIN. Medial, not 'away from the axis': at ~8 cm the cloth is
     past the arm's axis, where 'away' is outward. Each frame's need is carried to the bind pose by the vertex's
     dominant bone (its posed world transform inverted, then its reference transform), and the worst frame wins per
     vertex. Kept on the box (OUT/accum.json); only numbers come back. Also per frame: how deep the arm is in his
     BODY's torso (the cloth can never clear more than the body allows: that part is agent-01's).
  2. PUSH: a field over the outfit's torso in the bind pose: D(v) = max over needing u of need(u) x K(|v - u|) (K = 1
     within CORE_CM, cosine^2 to 0 over FALL_CM), the direction the K-weighted mean, none on the sleeve,
     capped at CAP: a broad soft hollow, never a crease. Written on a COPY (DEST) of the mesh his BP renders (the
     component's own asset: MetaHuman's resized garment), weights/UVs/normals/vertex order untouched.
  3. CHECK: dress DEST on the component (setplan GARMENT_SRC him), then MEASURE again with OUT2: need <= 0 where the
     cap allowed, and agent-02's garment_measure arms (side >= 0.5 every frame). The body under it: body.hide_under
     Body under SkeletalMesh with inside_cm (the slimmed flank sits inside his skin in the bind pose too) and
     `within` = the push's spheres (only the flank's skin goes).

Face rule: runs on the box; the copy is a project asset; accum.json stays on the box; the JSON printed holds numbers.

Driver (where film-ue runs):
    cd tools && uv run python ../films/host-studio/reel/r7/him_flank.py --box <profile> measure --out /srv/ue/fit/him_flank/m1 \
        --frames 0-66:6,84-150:6,422-458:6
    ... push --out /srv/ue/fit/him_flank/m1 --dest /Game/Host/Fit/SKM_Host_Outfit_R7Flank --cap 4.0
    ... measure --out /srv/ue/fit/him_flank/m2 --frames <same>        (after the copy is dressed)
"""
import json
import math

LABEL = "Host"
SEQ = "/Game/Explainer/SEQ_Explain_Him"
ARM = ("upperarm", "lowerarm", "bicep", "tricep", "elbow")
SLEEVE_FADE = 3.0  # cm into the sleeve (nearer the upper arm than the spine by): the push fades to 0 over it
MARGIN = 0.7       # cm outside the arm tube (the gate's 0.5 + 0.2)
T_RANGE = (0.12, 0.95)  # of the upper arm, shoulder -> elbow: where the tube counts (the armpit is the shoulder's)
CORE_CM, FALL_CM = 1.5, 7.0
SIDE_MIN = 3.0     # cm off the mid-sagittal plane (bind) to belong to a side


# ------------------------------------------------------------------------------------------ pure (tested off the box)
def medial_need(w, u, a_dir, R, margin):
    """The cloth point at offset w from the arm axis (perpendicular part taken here), u = unit medial direction
    (perpendicular to the arm, toward the spine), R the tube radius. How far along +u it must move to sit outside the
    tube by margin (0 when it already does or lies beyond the tube's side). Pure: tuples."""
    wa = sum(w[k] * a_dir[k] for k in range(3))
    wp = tuple(w[k] - wa * a_dir[k] for k in range(3))
    a = sum(wp[k] * u[k] for k in range(3))
    b2 = sum(x * x for x in wp) - a * a
    rr = (R + margin) ** 2
    if b2 >= rr:
        return 0.0
    return max(0.0, math.sqrt(rr - b2) - a)


def kernel(d, core=CORE_CM, fall=FALL_CM):
    if d <= core:
        return 1.0
    if d >= core + fall:
        return 0.0
    c = math.cos(0.5 * math.pi * (d - core) / fall)
    return c * c


def field(zone, needs, cap, core=CORE_CM, fall=FALL_CM):
    """zone {vid: (x, y, z)} bind positions; needs {vid: (need, (dx, dy, dz) unit bind direction)} -> {vid: (mag,
    unit dir)}: D(v) = max_u need_u K(|v-u|), direction the K x need weighted mean. Grid-hashed. Pure."""
    cell = core + fall
    grid = {}
    for u, (s, d) in needs.items():
        p = zone[u]
        grid.setdefault(tuple(int(math.floor(c / cell)) for c in p), []).append(u)
    out = {}
    for v, p in zone.items():
        k0 = tuple(int(math.floor(c / cell)) for c in p)
        best, acc = 0.0, [0.0, 0.0, 0.0]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for u in grid.get((k0[0] + dx, k0[1] + dy, k0[2] + dz), ()):
                        q = zone[u]
                        dd = math.sqrt(sum((p[i] - q[i]) ** 2 for i in range(3)))
                        k = kernel(dd, core, fall)
                        if k <= 0:
                            continue
                        s, d = needs[u]
                        best = max(best, s * k)
                        for i in range(3):
                            acc[i] += s * k * d[i]
        n = math.sqrt(sum(x * x for x in acc))
        if best > 1e-4 and n > 1e-9:
            out[v] = (min(cap, best), tuple(x / n for x in acc))
    return out


def parse_frames(spec: str) -> list:
    """'0-66:6,84-150:6,422' -> frames (each range with its last frame)."""
    out = set()
    for part in (x for x in spec.split(",") if x):
        rng, _, st = part.partition(":")
        if "-" in rng:
            a, b = (int(x) for x in rng.split("-"))
            out |= set(range(a, b + 1, int(st or 1))) | {b}
        else:
            out.add(int(rng))
    return sorted(out)


# ------------------------------------------------------------------------------------------------- editor side
def _editor(G: dict):
    import os
    import unreal
    AU, MQ, LU, SU = (unreal.GeometryScript_AssetUtils, unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List,
                      unreal.GeometryScript_SceneUtils)
    EAL = unreal.EditorAssetLibrary
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    W = unreal.RelativeTransformSpace.RTS_WORLD
    label, gname, out_dir = G.get("LABEL", LABEL), G.get("GARMENT", "SkeletalMesh"), G["OUT"]
    os.makedirs(out_dir, exist_ok=True)

    def pick(res, cls):
        items = res if isinstance(res, tuple) else (res,)
        return next((x for x in items if type(x).__name__ == cls), items[0])

    def bwlib():
        for n in ("GeometryScript_BoneWeights", "GeometryScript_MeshBoneWeights", "GeometryScript_SkinWeights"):
            if hasattr(unreal, n):
                return getattr(unreal, n)
        raise RuntimeError("no Geometry Script bone-weight library")

    BW = bwlib()
    host = next(a for a in EAS.get_all_level_actors() if a.get_actor_label() == label)
    comps = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
    body, garm = comps["Body"], comps[gname]

    def asset_dm(skm):
        dm = unreal.DynamicMesh()
        lod = unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property("lod_index", 0)
        AU.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
        return dm

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
        return [(p.x, p.y, p.z) for p in LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(dm, False),
                                                                                 "GeometryScriptVectorList"))]

    def weights(dm, v):
        res = BW.get_vertex_bone_weights(dm, v)
        ws = next((x for x in (res if isinstance(res, tuple) else (res,)) if isinstance(x, (list, unreal.Array))), [])
        return [(int(w.get_editor_property("bone_index")), float(w.get_editor_property("weight"))) for w in ws]

    def ref_skeleton(mesh):
        comp = unreal.SkeletalMeshComponent()
        comp.set_skeletal_mesh_asset(mesh)
        names = [str(comp.get_bone_name(i)) for i in range(comp.get_num_bones())]
        world = {}
        for i, b in enumerate(names):
            p = str(comp.get_parent_bone(b))
            t = comp.get_ref_pose_transform(i)
            world[b] = t if not p or p == "None" else unreal.MathLibrary.compose_transforms(t, world[p])
        return names, world

    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def unit(a):
        n = math.sqrt(dot(a, a)) or 1.0
        return (a[0] / n, a[1] / n, a[2] / n)

    def v3(p):
        return (p.x, p.y, p.z)

    def seg_dist(p, a, b):
        t = min(1.0, max(0.0, seg_t(p, a, b)))
        q = tuple(a[k] + (b[k] - a[k]) * t for k in range(3))
        return math.sqrt(dot(sub(p, q), sub(p, q)))

    def seg_t(p, s, e):
        d = sub(e, s)
        return dot(sub(p, s), d) / dot(d, d)

    stage = G["STAGE"]
    setup_path = os.path.join(out_dir, "setup.json")

    if stage == "setup":
        gmesh = garm.get_skeletal_mesh_asset()
        bmesh = body.get_skeletal_mesh_asset()
        gnames, gref = ref_skeleton(gmesh)
        bnames, bref = ref_skeleton(bmesh)
        H = {b: v3(bref[b].translation) for b in ("pelvis", "neck_01", "upperarm_l", "upperarm_r", "lowerarm_l",
                                                   "lowerarm_r")}
        mid = tuple((H["upperarm_l"][k] + H["upperarm_r"][k]) / 2 for k in range(3))
        lat = unit(sub(H["upperarm_l"], H["upperarm_r"]))
        # the arm tube's radius per 5 % of the upper arm, from the body's ref mesh (p90 of the arm-weighted verts)
        bdm = asset_dm(bmesh)
        bp = verts(bdm)
        R = {}
        for side in ("l", "r"):
            s, e = H[f"upperarm_{side}"], H[f"lowerarm_{side}"]
            a_dir = unit(sub(e, s))
            bins = [[] for _ in range(20)]
            for v, p in enumerate(bp):
                if dot(sub(p, mid), lat) * (1 if side == "l" else -1) < SIDE_MIN:
                    continue
                t = seg_t(p, s, e)
                if not 0.0 <= t < 1.0:
                    continue
                aw = sum(w for i, w in weights(bdm, v) if 0 <= i < len(bnames) and bnames[i].startswith(ARM)
                         and bnames[i].endswith("_" + side))
                if aw < 0.8:
                    continue
                w = sub(p, s)
                wa = dot(w, a_dir)
                r = math.sqrt(max(0.0, dot(w, w) - wa * wa))
                if r < 15.0:
                    bins[int(t * 20)].append(r)
            R[side] = [round(sorted(b)[int(0.9 * (len(b) - 1))], 3) if b else None for b in bins]
        # the outfit's torso verts per side (bind), their dominant bone and arm weight
        gdm = asset_dm(gmesh)
        gp = verts(gdm)
        zmin, zmax = H["pelvis"][2] + 10.0, H["neck_01"][2]
        zone = {}
        for v, p in enumerate(gp):
            if not zmin <= p[2] <= zmax:
                continue
            lo = dot(sub(p, mid), lat)
            if abs(lo) < SIDE_MIN:
                continue
            side = "l" if lo > 0 else "r"
            ws = weights(gdm, v)
            dom = gnames[max(ws, key=lambda x: x[1])[0]] if ws else "spine_05"
            # sleeve or torso by GEOMETRY on the ref pose, as agent-02's arms measure splits them (SLEEVES=1: nearest
            # the upper arm = sleeve): a flank vertex skinned mostly to the arm but nearer the spine is torso here
            # too, so it is measured and pushed. Slot 1 = how far into the sleeve, cm (d_spine - d_arm; <= 0 torso)
            sl = seg_dist(p, H["pelvis"], H["neck_01"]) - seg_dist(p, H[f"upperarm_{side}"], H[f"lowerarm_{side}"])
            zone[v] = [side, round(sl, 3), dom, [round(x, 4) for x in p]]
        doms = sorted({z[2] for z in zone.values()})
        refT = {b: [list(v3(gref[b].translation)), [gref[b].rotation.x, gref[b].rotation.y, gref[b].rotation.z,
                                                     gref[b].rotation.w]] for b in doms}
        S = {"garment_asset": gmesh.get_path_name().split(".")[0], "body_asset": bmesh.get_path_name().split(".")[0],
             "R": R, "zone": zone, "refT": refT, "lat": lat, "mid": mid, "verts": len(gp)}
        with open(setup_path, "w") as fh:
            json.dump(S, fh)
        with open(os.path.join(out_dir, "accum.json"), "w") as fh:
            json.dump({}, fh)
        return {"garment": S["garment_asset"], "body": S["body_asset"], "verts": len(gp), "zone_verts": len(zone),
                "zone_sleeve": sum(1 for z in zone.values() if z[1] > 0), "R_l": R["l"], "R_r": R["r"],
                "dominant_bones": doms[:40]}

    S = json.load(open(setup_path))

    if stage == "frame":
        acc_path = os.path.join(out_dir, "accum.json")
        acc = json.load(open(acc_path))
        gpos = verts(posed(garm))
        bpos = verts(posed(body))
        sock = {b: v3(body.get_socket_location(b)) for b in ("upperarm_l", "lowerarm_l", "upperarm_r", "lowerarm_r",
                                                              "spine_03", "spine_05")}
        spine0, spine1 = sock["spine_03"], sock["spine_05"]
        sdir = unit(sub(spine1, spine0))
        posedT = {}
        frame_out = {"frame": G.get("F"), "need": {}, "body_in_arm_cm": {}}
        for side in ("l", "r"):
            s, e = sock[f"upperarm_{side}"], sock[f"lowerarm_{side}"]
            a_dir = unit(sub(e, s))
            Rs = S["R"][side]
            worst, n_need = None, 0
            for vs, (zs, aw, dom, _) in S["zone"].items():
                if zs != side or aw > 0:
                    continue
                p = gpos[int(vs)]
                t = seg_t(p, s, e)
                if not T_RANGE[0] <= t <= T_RANGE[1]:
                    continue
                Rt = Rs[min(19, int(t * 20))]
                if Rt is None:
                    continue
                q = tuple(s[k] + a_dir[k] * t * math.sqrt(dot(sub(e, s), sub(e, s))) for k in range(3))
                # medial: from the axis point toward the spine line, perpendicular to the arm
                sp = tuple(spine0[k] + sdir[k] * dot(sub(q, spine0), sdir) for k in range(3))
                m = sub(sp, q)
                m = sub(m, tuple(a_dir[k] * dot(m, a_dir) for k in range(3)))
                u = unit(m)
                need = medial_need(sub(p, q), u, a_dir, Rt, float(G.get("MARGIN", MARGIN)))
                if need <= 0:
                    continue
                n_need += 1
                if dom not in posedT:  # from his Body (the leader): a follower's own bones may read at rest
                    posedT[dom] = body.get_socket_transform(dom if body.get_bone_index(dom) >= 0 else "spine_05", W)
                pt = posedT[dom]
                rq = S["refT"][dom][1]
                rref = unreal.Quat(rq[0], rq[1], rq[2], rq[3])
                dl = pt.inverse_transform_direction(unreal.Vector(*[x * need for x in u]))
                db = rref.rotate_vector(dl)
                cur = acc.get(vs)
                if cur is None or need > cur[0]:
                    acc[vs] = [round(need, 3), [round(db.x / need, 4), round(db.y / need, 4), round(db.z / need, 4)],
                               G.get("F")]
                if worst is None or need > worst[0]:
                    worst = (round(need, 2), round(t, 2))
            # the arm in his BODY's torso (information: the part no cloth refit can give)
            deep = 0.0
            for p in bpos[::3]:
                lo = dot(sub(p, sock["spine_03"]), unit(sub(sock["upperarm_l"], sock["upperarm_r"])))
                if (lo > 0) != (side == "l"):
                    continue
                t = seg_t(p, s, e)
                if not T_RANGE[0] <= t <= T_RANGE[1]:
                    continue
                Rt = Rs[min(19, int(t * 20))]
                q = tuple(s[k] + a_dir[k] * t * math.sqrt(dot(sub(e, s), sub(e, s))) for k in range(3))
                w = sub(p, q)
                wa = dot(w, a_dir)
                r = math.sqrt(max(0.0, dot(w, w) - wa * wa))
                if Rt and r < Rt * 0.98:
                    deep = max(deep, Rt - r)
            frame_out["need"][side] = {"verts": n_need, "worst_cm_t": worst}
            frame_out["body_in_arm_cm"][side] = round(deep, 2)
        with open(acc_path, "w") as fh:
            json.dump(acc, fh)
        frame_out["arm_l"] = [round(x, 1) for x in sock["upperarm_l"]]
        return frame_out

    if stage == "summary":
        acc = json.load(open(os.path.join(out_dir, "accum.json")))
        out = {}
        for side in ("l", "r"):
            ns = sorted((v[0] for k, v in acc.items() if S["zone"][k][0] == side), reverse=True)
            fr = {}
            for k, v in acc.items():
                if S["zone"][k][0] == side:
                    fr[v[2]] = fr.get(v[2], 0) + 1
            out[side] = {"verts": len(ns), "max_cm": ns[0] if ns else 0, "p90_cm": ns[len(ns) // 10] if ns else 0,
                         "worst_frames": sorted(fr.items(), key=lambda x: -x[1])[:6]}
        return out

    if stage == "push":
        acc = json.load(open(os.path.join(out_dir, "accum.json")))
        cap = float(G.get("CAP", 4.0))
        zone = {int(k): tuple(z[3]) for k, z in S["zone"].items()}
        needs = {int(k): (v[0], tuple(v[1])) for k, v in acc.items()}
        F = field(zone, needs, cap, float(G.get("CORE", CORE_CM)), float(G.get("FALL", FALL_CM)))
        aw = {int(k): z[1] for k, z in S["zone"].items()}
        src = S["garment_asset"]
        gdm = asset_dm(EAL.load_asset(src))
        gp = verts(gdm)
        new = list(gp)
        moved = {"l": [0, 0.0], "r": [0, 0.0]}
        for v, (mag, d) in F.items():
            damp = min(1.0, max(0.0, 1.0 - aw[v] / SLEEVE_FADE))  # the sleeve takes a fading share: no step at the armhole
            mag *= damp
            if mag <= 1e-4:
                continue
            new[v] = tuple(gp[v][k] + mag * d[k] for k in range(3))
            sd = S["zone"][str(v)][0]
            moved[sd][0] += 1
            moved[sd][1] = max(moved[sd][1], round(mag, 3))
        dest = G["DEST"]
        if EAL.does_asset_exist(dest):
            raise RuntimeError(f"{dest} exists: pass a new DEST (never overwrite)")
        EAL.duplicate_asset(src, dest)
        dup = EAL.load_asset(dest)
        ddm = asset_dm(dup)
        ME = getattr(unreal, "GeometryScript_MeshEdits", None) or unreal.GeometryScript_MeshBasicEdits
        ME.set_all_mesh_vertex_positions(ddm, pick(LU.convert_array_to_vector_list([unreal.Vector(*p) for p in new]),
                                                   "GeometryScriptVectorList"))
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
        AU.copy_mesh_to_skeletal_mesh(ddm, dup, opts, lod)
        EAL.save_asset(dest)
        back = verts(asset_dm(EAL.load_asset(dest)))
        off = max(math.sqrt(dot(sub(a, b), sub(a, b))) for a, b in zip(back, new)) if len(back) == len(new) else None
        # the spheres body.hide_under `within` takes: each side's moved region (centroid, radius + 2 cm)
        spheres = []
        for side in ("l", "r"):
            pts = [new[v] for v in F if S["zone"][str(v)][0] == side]
            if pts:
                c = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
                r = max(math.sqrt(dot(sub(p, c), sub(p, c))) for p in pts) + 2.0
                spheres.append([round(c[0], 2), round(c[1], 2), round(c[2], 2), round(r, 2)])
        return {"dest": dest, "src": src, "cap": cap, "moved": moved, "needing": len(needs),
                "verts": [len(gp), len(back)], "write_off_cm": round(off, 5) if off is not None else "count changed",
                "within": spheres}

    raise RuntimeError(f"STAGE {stage}?")


# ------------------------------------------------------------------------------------------------ driver
def _exec(client, stage: str, **g) -> dict:
    src = open(__file__).read()
    code = f"import json as _j\n_G = _j.loads({json.dumps(json.dumps({'STAGE': stage, **g}))})\n{src}\nresult = _editor(_G)\n"
    r = client.exec_code(code, timeout=900)
    if not r.get("ok"):
        raise SystemExit(f"{stage}: {json.dumps(r)[:2000]}")
    return r["result"]


def main(argv=None) -> int:
    import argparse
    import os
    import sys
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", required=True, help="the workstation profile (FILM_UE_BOX); 'conf' = the conf dir's")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--out", required=True, help="a directory ON THE BOX (setup.json, accum.json stay there)")
    m.add_argument("--frames", default="0-66:6,84-150:6,422-458:6")
    m.add_argument("--seq", default=SEQ)
    m.add_argument("--margin", type=float, default=MARGIN)
    m.add_argument("--garment", default="SkeletalMesh")
    p = sub.add_parser("push")
    p.add_argument("--out", required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--cap", type=float, default=4.0, help="max push, cm (orchestrator: the remainder, <= ~4)")
    p.add_argument("--core", type=float, default=CORE_CM)
    p.add_argument("--fall", type=float, default=FALL_CM)
    a = ap.parse_args(argv)
    if a.box != "conf":
        os.environ["FILM_UE_BOX"] = a.box
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
    from filmtools.unreal import client

    if a.cmd == "measure":
        print("setup:", json.dumps(_exec(client, "setup", OUT=a.out, GARMENT=a.garment)), flush=True)
        last = None
        for i, f in enumerate(parse_frames(a.frames)):
            for ff in (f + 1, f):
                r = client.op("seq.scrub", path=a.seq, frame=ff)
                if not r.get("ok"):
                    raise SystemExit(f"seq.scrub {ff}: {r}")
            res = _exec(client, "frame", OUT=a.out, GARMENT=a.garment, F=f, MARGIN=a.margin)
            if last is not None and res["arm_l"] == last:
                print(f"WARN f{f}: upperarm_l did not move since the last frame (pose not updated?)")
            last = res["arm_l"]
            print(f"f{f}: need {json.dumps(res['need'])} body in arm {json.dumps(res['body_in_arm_cm'])}", flush=True)
        print("summary:", json.dumps(_exec(client, "summary", OUT=a.out, GARMENT=a.garment), indent=1))
        return 0
    print(json.dumps(_exec(client, "push", OUT=a.out, DEST=a.dest, CAP=a.cap, CORE=a.core, FALL=a.fall), indent=1))
    print("next: setplan GARMENT_SRC him SkeletalMesh -> DEST and GARMENT_HIDES him Body under SkeletalMesh with "
          "inside_cm + within (the spheres above); set.py --who him --steps garments,dress; measure again; agent-02's arms")
    return 0


if __name__ == "__main__" and "_G" not in globals():
    try:
        import unreal  # noqa: F401
    except ImportError:
        raise SystemExit(main())
    result = _editor(globals())
