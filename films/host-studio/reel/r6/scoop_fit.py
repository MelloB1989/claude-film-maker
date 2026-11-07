"""Round 6 (agent-02, the orchestrator's ruling on HER neckline strip): turn the Top's scoop EDGE in against her skin.

test30 f29 (her MCU): a flat mid-grey band with hard edges runs down the inside of her neckline on her left. strip_id
(no back faces, no hidden/extra mesh; Top front vs Face skin) and the orchestrator's 3x look: it is the Top's own
neckline edge/binding seen at a grazing angle because the edge STANDS OFF the skin. Fix the geometry, not the
material (a brighten flickers in motion): pull the neckline edge in to <= 0.3 cm off the skin.

  measure  per frame (scrubbed F+1 then F, as qa.clip): the Top's neckline = the open boundary loop nearest the spine
           axis (vertices welded by position first: the posed render copy splits verts at UV seams). For every loop
           vertex: its signed stand-off from the nearest skin (posed Face/Body; the skin normal oriented away from
           the spine axis, so a poke reads < 0), its sector (24 x 15 deg round the spine_05 -> neck_01 axis, a
           torso-rigid frame) and the skin normal in spine_05's local space. Per sector: loop stand-off min/p50/max,
           and the BAND's (every Top vert within BAND_CM of the loop) minimum stand-off: the binding's inner face.
  pull     on a NEW asset (a copy of the Top's own mesh, never the original): per sector the pull is
           min over frames of (loop p50 - TARGET), capped by the band's room (band min - FLOOR, so the inner face
           never goes into the skin) and CAP, smoothed 1-2-1 round the sectors. Every rest vertex within RIB of the
           rest neckline moves by the full pull along -skin normal (the binding moves whole, its width and thickness
           kept), then a cosine to 0 over FALL down the Top. Nothing else moves. Written back with Geometry Script
           (positions only; skin weights, UVs, materials kept), then read back.
  verify   = measure again after the driver swaps the copy onto her Top component: sides p50 <= 0.3, band < 0 = 0.

Driver (where film-ue runs; numbers only come out, no pixels):
    cd <tree>/tools && uv run python ../films/host-studio/reel/r6/scoop_fit.py --box conf measure \
        --seq <SEQ> --frames 29,<more> --out /srv/ue/reel/r6/explain_her/scoop/m0
    ... pull --from /srv/ue/reel/r6/explain_her/scoop/m0 --dest /Game/Host/Presenter_Top/SKM_Presenter_Top_Scoop1
    (swap the copy onto Presenter's Top component, as for the Overshirt RW2; materials as worn)
    ... measure --seq <SEQ> --frames 29,<more> --out /srv/ue/reel/r6/explain_her/scoop/m1
"""
import json
import math

NS = 24
TARGET, FLOOR, CAP = 0.2, 0.1, 1.5  # cm (test30 f29 reads 1.4-1.8 cm along the view at the edge)
REST_BODY = "FMQA_ScoopRestBody"


# ---------------------------------------------------------------------------------------- pure (tested off the box)
def weld_keys(pos: list, grid: float = 0.02) -> list:
    """Vertex id -> a key shared by vertices at the same position (render copies split verts at UV seams)."""
    return [(round(p[0] / grid), round(p[1] / grid), round(p[2] / grid)) for p in pos]


def boundary_loops(tris: list, keys: list, min_len: int = 12) -> list:
    """Open-boundary loops of a triangle soup, in WELDED keys: [[vertex id (one per key), ...], ...], longest first.
    An edge is open when exactly one triangle uses it (by keys)."""
    count, rep = {}, {}
    for t in tris:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            ka, kb = keys[a], keys[b]
            if ka == kb:
                continue
            rep.setdefault(ka, a)
            rep.setdefault(kb, b)
            e = (ka, kb) if ka < kb else (kb, ka)
            count[e] = count.get(e, 0) + 1
    adj = {}
    for (ka, kb), c in count.items():
        if c == 1:
            adj.setdefault(ka, []).append(kb)
            adj.setdefault(kb, []).append(ka)
    seen, loops = set(), []
    for start in adj:
        if start in seen:
            continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            k = stack.pop()
            comp.append(rep[k])
            for n in adj[k]:
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        if len(comp) >= min_len:
            loops.append(comp)
    loops.sort(key=len, reverse=True)
    return loops


def normals_and_span(tris: list, pos: list, keys: list) -> tuple:
    """Per WELDED key: the area-weighted mean face normal (unit) and the SPAN, the largest angle (deg) between two
    incident face normals. A thin closed shell folds over at its edges (outer face -> inner face): span ~90-180 there,
    ~0-30 on the flat."""
    acc, fn = {}, {}
    for t in tris:
        a, b, c = (pos[i] for i in t)
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        ln = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
        if ln < 1e-12:
            continue
        nu = (n[0] / ln, n[1] / ln, n[2] / ln)
        for i in t:
            k = keys[i]
            m = acc.get(k, (0.0, 0.0, 0.0))
            acc[k] = (m[0] + n[0], m[1] + n[1], m[2] + n[2])
            fn.setdefault(k, []).append(nu)
    nrm, span = {}, {}
    for k, m in acc.items():
        ln = math.sqrt(sum(c * c for c in m)) or 1.0
        nrm[k] = (m[0] / ln, m[1] / ln, m[2] / ln)
        ns = fn[k]
        lo = min((a[0] * b[0] + a[1] * b[1] + a[2] * b[2] for i, a in enumerate(ns) for b in ns[i + 1:]), default=1.0)
        span[k] = math.degrees(math.acos(max(-1.0, min(1.0, lo))))
    return nrm, span


def rim_components(tris: list, keys: list, span: dict, span_deg: float = 70.0, min_len: int = 12) -> list:
    """The fold-over rims of a closed shell: connected sets (by mesh edges, welded) of keys whose span >= span_deg,
    as [[vertex id (one per key), ...], ...], largest first."""
    rep, adj = {}, {}
    for t in tris:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            ka, kb = keys[a], keys[b]
            rep.setdefault(ka, a)
            rep.setdefault(kb, b)
            if ka != kb and span.get(ka, 0) >= span_deg and span.get(kb, 0) >= span_deg:
                adj.setdefault(ka, set()).add(kb)
                adj.setdefault(kb, set()).add(ka)
    seen, comps = set(), []
    for k0 in adj:
        if k0 in seen:
            continue
        comp, stack = [], [k0]
        seen.add(k0)
        while stack:
            k = stack.pop()
            comp.append(rep[k])
            for n in adj[k]:
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        if len(comp) >= min_len:
            comps.append(comp)
    comps.sort(key=len, reverse=True)
    return comps


def sector(th: float) -> int:
    return int((th % 360.0) // (360.0 / NS)) % NS


def interp(vals: list, th: float) -> float:
    """Linear between sector centres, circular."""
    x = (th % 360.0) / (360.0 / NS) - 0.5
    i = math.floor(x)
    f = x - i
    return vals[i % NS] * (1 - f) + vals[(i + 1) % NS] * f


def falloff(d: float, rib: float, fall: float) -> float:
    if d <= rib:
        return 1.0
    x = (d - rib) / max(fall, 1e-6)
    return 0.5 * (1.0 + math.cos(math.pi * x)) if x < 1.0 else 0.0


def plan(frames: list, target: float = TARGET, floor: float = FLOOR, cap: float = CAP) -> dict:
    """frames: [measure result, ...] -> {"pull": [NS] cm, "nrm": [NS] local unit vectors, "why": [NS]}."""
    raw, why, nrm, rooms = [0.0] * NS, [""] * NS, [[0.0, 0.0, 0.0] for _ in range(NS)], [cap] * NS
    for s in range(NS):
        want, room, nv = None, None, [0.0, 0.0, 0.0]
        for fr in frames:
            row = fr["sectors"][s]
            if not row:
                continue
            w = row["loop_p50"] - target
            want = w if want is None else min(want, w)
            if row.get("band_min") is not None:
                r = row["band_min"] - floor
                room = r if room is None else min(room, r)
            nv = [a + b for a, b in zip(nv, row["nrm"])]
        ln = math.sqrt(sum(c * c for c in nv))
        if want is None or ln < 1e-6:
            why[s], rooms[s] = "no loop", 0.0  # unmeasured: never moved
            continue
        nrm[s] = [c / ln for c in nv]
        if room is not None:
            rooms[s] = max(0.0, min(cap, room))
        p = max(0.0, want)
        if p > rooms[s]:
            p, why[s] = rooms[s], (f"room {room:.2f}" if room is not None and room < cap else "cap")
        raw[s] = p
    # smoothing may only RAISE a sector towards its neighbours (a peak keeps its full pull), never over its own room
    pull = [min(rooms[s], max(raw[s], (raw[(s - 1) % NS] + 2 * raw[s] + raw[(s + 1) % NS]) / 4.0)) for s in range(NS)]
    return {"pull": [round(p, 3) for p in pull], "nrm": [[round(c, 4) for c in v] for v in nrm], "why": why,
            "raw": [round(p, 3) for p in raw]}


# ---------------------------------------------------------------------------------------- editor
def _editor(G: dict):
    import unreal
    AU, MQ, LU, SU = (unreal.GeometryScript_AssetUtils, unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List,
                      unreal.GeometryScript_SceneUtils)
    SP = unreal.GeometryScript_MeshSpatial
    EAL = unreal.EditorAssetLibrary
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    W = unreal.RelativeTransformSpace.RTS_WORLD
    label, top_name = G.get("LABEL", "Presenter"), G.get("TOP", "Top")
    band_cm, rib, fall = float(G.get("BAND_CM", 2.0)), float(G.get("RIB", 1.0)), float(G.get("FALL", 2.5))

    def pick(res, cls):
        items = res if isinstance(res, tuple) else (res,)
        return next((x for x in items if type(x).__name__ == cls), items[0])

    def actor(lab):
        return next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == lab), None)

    def posed(c):
        opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
        lod = unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
        lod.set_editor_property("lod_index", 0)
        opts.set_editor_property("requested_lod", lod)
        dm = unreal.DynamicMesh()
        SU.copy_mesh_from_component(c, dm, opts, True)
        return dm

    def asset_dm(skm):
        dm = unreal.DynamicMesh()
        lod = unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property("lod_index", 0)
        AU.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
        return dm

    def verts(dm):
        return list(LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(dm, False),
                                                         "GeometryScriptVectorList")))

    def tris(dm):
        fn = getattr(MQ, "get_all_triangle_indices", None)
        if fn:
            tl = pick(fn(dm, False), "GeometryScriptTriangleList")
            arr = LU.convert_triangle_list_to_array(tl)
            return [(int(t.x), int(t.y), int(t.z)) for t in arr]
        out = []
        for tid in range(MQ.get_num_triangle_ids(dm)):
            iv = pick(MQ.get_triangle_indices(dm, tid), "IntVector")
            out.append((int(iv.x), int(iv.y), int(iv.z)))
        return out

    class Frame:
        """Torso-rigid: spine_05 local; axis from spine_05's origin to neck_01 (a child bone: constant in this frame)."""

        def __init__(self, T, body):
            self.T = T
            self.o = T.inverse_transform_location(body.get_socket_location("neck_01"))
            self.u = self.o * (1.0 / (self.o.length() or 1.0))
            ax = min((unreal.Vector(1, 0, 0), unreal.Vector(0, 1, 0), unreal.Vector(0, 0, 1)),
                     key=lambda v: abs(v.dot(self.u)))
            e1 = ax - self.u * ax.dot(self.u)
            self.e1 = e1 * (1.0 / e1.length())
            self.e2 = self.u.cross(self.e1)

        def local(self, p):
            return self.T.inverse_transform_location(p)

        def cyl(self, q):  # local point -> (t along the axis from neck_01, r from the axis, theta deg, unit radial)
            t = q.dot(self.u)
            w = q - self.u * t
            r = w.length()
            th = math.degrees(math.atan2(w.dot(self.e2), w.dot(self.e1))) % 360.0
            return t - self.o.length(), r, th, (w * (1.0 / r) if r > 1e-6 else self.e1)

    def neckline(V, fr):
        P = [(p.x, p.y, p.z) for p in V]
        K = weld_keys(P)
        loops, how = boundary_loops(tris_cache, K), "open boundary"
        if not loops:  # her Top is a closed shell (round 6): the neckline is where it folds from outer to inner face
            _, span = normals_and_span(tris_cache, P, K)
            loops, how = rim_components(tris_cache, K, span, float(G.get("SPAN_DEG", 70.0))), "fold rim"
        if not loops:
            raise RuntimeError("the Top has no open boundary and no fold rim (try SPAN_DEG lower)")
        how_used[0] = how
        scored = []
        for lp in loops:
            cs = [fr.cyl(fr.local(V[i])) for i in lp]
            scored.append((sum(c[1] for c in cs) / len(cs), lp, cs))
        scored.sort(key=lambda x: x[0])
        return scored[0][1], [{"n": len(s[1]), "mean_r": round(s[0], 2),
                               "t": [round(min(c[0] for c in s[2]), 1), round(max(c[0] for c in s[2]), 1)]}
                              for s in scored[:5]]

    how_used = [""]
    host = actor(label)
    cs = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
    body, top = cs["Body"], cs[top_name]
    stage = G.get("STAGE", "measure")

    if stage == "measure":
        T = body.get_socket_transform("spine_05", W)
        fr = Frame(T, body)
        tdm = posed(top)
        V = verts(tdm)
        tris_cache = tris(tdm)
        loop, cand = neckline(V, fr)
        skins = []
        for k in ("Face", "Body"):
            if k in cs and cs[k].is_visible():
                dm = posed(cs[k])
                skins.append((dm, pick(SP.build_bvh_for_mesh(dm), "GeometryScriptDynamicMeshBVH")))
        qo = unreal.GeometryScriptSpatialQueryOptions()

        def standoff(p):
            best = None
            for dm, bvh in skins:
                tp = pick(SP.find_nearest_point_on_mesh(dm, bvh, p, qo), "GeometryScriptTrianglePoint")
                if not tp.get_editor_property("valid"):
                    continue
                q = tp.get_editor_property("position")
                if best is None or (p - q).length() < best[0]:
                    n = pick(MQ.get_triangle_face_normal(dm, tp.get_editor_property("triangle_id")), "Vector")
                    best = ((p - q).length(), q, n)
            if best is None:
                return None
            _, q, n = best
            nl = T.inverse_transform_direction(n)
            ql = fr.local(q)
            radial = ql - fr.u * ql.dot(fr.u)  # away from the spine axis: outward on chest and neck
            if nl.dot(radial) < 0:
                nl, n = nl * -1.0, n * -1.0
            return (p - q).dot(n), nl

        rows = [[] for _ in range(NS)]
        lp_local = []
        for i in loop:
            ql = fr.local(V[i])
            t, r, th, _ = fr.cyl(ql)
            so = standoff(V[i])
            lp_local.append(ql)
            if so:
                rows[sector(th)].append((so[0], so[1], t))
        band = [[] for _ in range(NS)]
        inner, outer = [[] for _ in range(NS)], [[] for _ in range(NS)]
        Pt = [(p.x, p.y, p.z) for p in V]
        Kt = weld_keys(Pt)
        vn, _ = normals_and_span(tris_cache, Pt, Kt)
        loopset = set(loop)
        lo_t = min(fr.cyl(q)[0] for q in lp_local) - band_cm
        for i, p in enumerate(V):
            if i in loopset:
                continue
            ql = fr.local(p)
            t, r, th, _ = fr.cyl(ql)
            if t < lo_t or r > 20.0:
                continue
            if min((ql - q).length() for q in lp_local) > band_cm:
                continue
            so = standoff(p)
            if so:
                band[sector(th)].append(so[0])
                n = vn.get(Kt[i])
                if n:  # the shell's own normal vs the skin's (local): towards the skin = its inner face
                    nl = T.inverse_transform_direction(unreal.Vector(*n))
                    (inner if nl.dot(so[1]) < 0 else outer)[sector(th)].append(so[0])
        sectors = []
        for s in range(NS):
            if not rows[s]:
                sectors.append(None)
                continue
            ss = sorted(x[0] for x in rows[s])
            nv = [sum(getattr(x[1], k) for x in rows[s]) / len(rows[s]) for k in ("x", "y", "z")]
            sectors.append({"n": len(ss), "loop_min": round(ss[0], 3), "loop_p50": round(ss[len(ss) // 2], 3),
                            "loop_max": round(ss[-1], 3), "nrm": [round(c, 4) for c in nv],
                            "t": [round(min(x[2] for x in rows[s]), 1), round(max(x[2] for x in rows[s]), 1)],
                            "band_n": len(band[s]), "band_min": round(min(band[s]), 3) if band[s] else None,
                            "band_lt0": sum(1 for x in band[s] if x < 0),
                            "inner_p50": round(sorted(inner[s])[len(inner[s]) // 2], 3) if inner[s] else None,
                            "outer_p50": round(sorted(outer[s])[len(outer[s]) // 2], 3) if outer[s] else None})
        fwd = T.inverse_transform_direction(host.get_actor_forward_vector())
        hd = body.get_socket_location("head")
        return {"neckline_by": how_used[0], "loop_candidates": cand, "loop_n": len(loop), "sectors": sectors,
                "actor_forward_deg": round(math.degrees(math.atan2(fwd.dot(fr.e2), fwd.dot(fr.e1))) % 360.0, 1),
                "head_w": [round(hd.x, 2), round(hd.y, 2), round(hd.z, 2)], "top_mesh": top.get_skeletal_mesh_asset().get_path_name()}

    if stage == "pull":
        src = top.get_skeletal_mesh_asset()
        dest, PULL, NRM = G["DEST"], G["PULL"], G["NRM"]
        if EAL.does_asset_exist(dest):
            raise RuntimeError(f"{dest} exists: pass a new DEST (never overwrite a rendered asset)")
        old = actor(REST_BODY)
        if old:
            EAS.destroy_actor(old)
        # the ref pose: the Body mesh unanimated at the origin (asset verts' space; collar_fit's setup, proven), gone
        # again before this stage returns
        rb = EAS.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        try:
            rb.set_actor_label(REST_BODY)
            rc = rb.get_editor_property("skeletal_mesh_component")
            rc.set_skeletal_mesh_asset(body.get_skeletal_mesh_asset())
            Ts = rc.get_socket_transform("spine_05", W)
            nk = rc.get_socket_location("neck_01")
            if (nk - Ts.translation).length() < 2.0:
                raise RuntimeError("the temp rest Body has no ref pose yet: run pull again")

            class _B:  # Frame wants a body with sockets in the same space as T
                @staticmethod
                def get_socket_location(_):
                    return nk
            fr = Frame(Ts, _B)
        finally:
            EAS.destroy_actor(rb)
        dup = EAL.duplicate_asset(src.get_path_name().split(".")[0], dest)
        if dup is None:
            raise RuntimeError(f"duplicate {src.get_path_name()} -> {dest} failed")
        dm = asset_dm(dup)
        V = verts(dm)
        tris_cache = tris(dm)
        loop, cand = neckline(V, fr)
        lp_local = [fr.local(V[i]) for i in loop]
        ME = unreal.GeometryScript_MeshBasicEditing
        moved, mx, outside = 0, 0.0, 0
        for i, p in enumerate(V):
            ql = fr.local(p)
            t, r, th, _ = fr.cyl(ql)
            if r > 22.0:
                continue
            d = min((ql - q).length() for q in lp_local)
            w = falloff(d, rib, fall)
            amt = w * interp(PULL, th)
            if amt <= 0.005:
                continue
            n = unreal.Vector(*[interp([v[k] for v in NRM], th) for k in range(3)])
            n = n * (1.0 / (n.length() or 1.0))
            ME.set_vertex_position(dm, i, fr.T.transform_location(ql - n * amt), True)
            moved += 1
            mx = max(mx, amt)
        opts = unreal.GeometryScriptCopyMeshToAssetOptions()
        for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", False),
                     ("enable_remove_degenerates", False), ("use_original_vertex_order", True),
                     ("replace_materials", False)):
            try:
                opts.set_editor_property(k, v)
            except Exception:  # noqa: BLE001
                pass
        lod = unreal.GeometryScriptMeshWriteLOD()
        lod.set_editor_property("lod_index", 0)
        AU.copy_mesh_to_skeletal_mesh(dm, dup, opts, lod)
        EAL.save_asset(dest)
        back, orig = verts(asset_dm(dup)), verts(asset_dm(src))
        d_rest = sorted((a - b).length() for a, b in zip(back, orig)) if len(back) == len(orig) else None
        far = 0
        if d_rest:
            for a, b in zip(back, orig):
                if (a - b).length() > 0.01 and min((fr.local(b) - q).length() for q in lp_local) > rib + fall + 0.1:
                    far += 1
        return {"dest": dest, "src": src.get_path_name(), "neckline_by": how_used[0], "loop_candidates": cand, "loop_n": len(loop),
                "verts": [len(back), len(orig)], "moved_verts": moved, "max_pull_cm": round(mx, 3),
                "rest_moved_gt_0.01": sum(1 for x in d_rest if x > 0.01) if d_rest else "vertex count changed",
                "moved_outside_zone": far, "rest_max_cm": round(d_rest[-1], 3) if d_rest else None,
                "slots_as_worn": {str(s): (m.get_path_name() if m else None)
                                  for s, m in zip(top.get_material_slot_names(), top.get_materials())}}

    if stage == "cleanup":
        x = actor(REST_BODY)
        if x:
            EAS.destroy_actor(x)
        return {"removed": bool(x)}
    raise RuntimeError(f"STAGE {stage}?")


# ---------------------------------------------------------------------------------------- driver
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
    ap.add_argument("--box", required=True, help="workstation profile (FILM_UE_BOX); 'conf' = the conf dir's default")
    ap.add_argument("--label", default="Presenter")
    ap.add_argument("--top", default="Top")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--seq", required=True)
    m.add_argument("--frames", required=True, help="comma list (test30 f29 first)")
    m.add_argument("--out", required=True)
    p = sub.add_parser("pull")
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--target", type=float, default=TARGET)
    p.add_argument("--cap", type=float, default=CAP)
    p.add_argument("--rib", type=float, default=1.0)
    p.add_argument("--fall", type=float, default=2.5)
    p.add_argument("--dry", action="store_true", help="print the plan only")
    sub.add_parser("cleanup")
    a = ap.parse_args(argv)
    if a.box != "conf":
        os.environ["FILM_UE_BOX"] = a.box
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
    from filmtools.unreal import client
    g = {"LABEL": a.label, "TOP": a.top}
    if a.cmd == "cleanup":
        print(json.dumps(_exec(client, "cleanup", **g)))
        return 0
    if a.cmd == "measure":
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        per, last = {}, None
        for f in (int(x) for x in a.frames.split(",") if x):
            for ff in (f + 1, f):
                r = client.op("seq.scrub", path=a.seq, frame=ff)
                if not r.get("ok"):
                    raise SystemExit(f"seq.scrub {ff}: {r}")
            res = _exec(client, "measure", **g)
            if last is not None and res["head_w"] == last:
                print(f"WARN f{f}: head did not move since the last frame (pose not updated?)")
            last = res["head_w"]
            per[f] = res
            worst = max(((s["loop_p50"], k * 15) for k, s in enumerate(res["sectors"]) if s), default=None)
            print(f"f{f}: loop {res['loop_n']} verts, worst sector p50 stand-off {worst} (cm, deg), band<0 "
                  f"{sum(s['band_lt0'] for s in res['sectors'] if s)}, forward at {res['actor_forward_deg']} deg",
                  flush=True)
        (out / "measure.json").write_text(json.dumps(per))
        print("neckline by", next(iter(per.values()))["neckline_by"], "| sector rows: deg, [loop min, p50, max, band min, "
              "band<0, t range, inner-face p50, outer-face p50]")
        print(json.dumps({"loop_candidates": next(iter(per.values()))["loop_candidates"],
                          "sectors_f0": [(k * 15, s and [s["loop_min"], s["loop_p50"], s["loop_max"], s["band_min"],
                                                         s["band_lt0"], s["t"], s["inner_p50"], s["outer_p50"]]) for k, s in
                                         enumerate(next(iter(per.values()))["sectors"])]}, indent=None))
        return 0
    per = json.loads((Path(a.src) / "measure.json").read_text())
    pl = plan(list(per.values()), target=a.target, cap=a.cap)
    print(json.dumps({"pull": [(k * 15, pl["pull"][k], pl["why"][k]) for k in range(NS)]}))
    if a.dry:
        return 0
    try:
        res = _exec(client, "pull", **g, DEST=a.dest, PULL=pl["pull"], NRM=pl["nrm"], RIB=a.rib, FALL=a.fall)
    finally:
        print("cleanup:", json.dumps(_exec(client, "cleanup", **g)))
    print(json.dumps(res, indent=1))
    (Path(a.src) / "pull.json").write_text(json.dumps({"plan": pl, "result": res}))
    print("next: swap", a.dest, "onto", a.label, a.top, "(materials as worn), then measure again")
    return 0


if __name__ == "__main__" and "_G" not in globals():
    import sys as _sys
    if len(_sys.argv) > 1:  # the driver CLI (an `unreal` stub may be importable off the box: never decide by that)
        raise SystemExit(main())
    result = _editor(globals())
