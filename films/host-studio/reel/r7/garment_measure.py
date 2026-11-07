"""Round 7 (agent-02, GARMENT): two per-frame measures on her posed meshes in the editor. Numbers only come out.

  arms   body.upperarm_torso_clear_cm: per side, the min SIGNED distance from her upper-arm skin to her torso surface
         (her torso skin and the torso part of the Top), < 0 = the arm is INSIDE the torso/breast/Top. The operator's
         v2b 00:44 (her right upper arm under/into her right breast) must read < 0; the bar is >= 3 cm.
         Which vertex is arm and which is torso is decided ONCE on the ref pose (a temp unanimated copy of the same
         asset at the origin, the A-pose: arms clear of the torso), by the nearest bone segment; the posed render
         mesh has the same vertices in the same order. Arm = nearest segment upperarm_<s>, from ARM_T0 (0.3) of the
         way from the shoulder joint to the elbow (the armpit fold is skin joined to the torso: it always reads 0),
         and within ARM_R_X (1.3) x the arm's own radius of the bone (v2b run 1 without it: her side's skin under the
         A-pose arm counted as arm, inside the Top, -10.4 cm in every frame). Self-check: the same split on the ref
         pose must read rest_clear_cm > 0.
         Torso = nearest segment on the spine chain or a clavicle, farther than AXILLA_CM from that shoulder joint.
         The Top's sleeves are left out the same way. Distance = to the nearest torso TRIANGLE; the sign from the
         triangle's normal (her skin's own; the Top's turned away from the spine chain: it is a closed shell).
  waist  garment.waist_fit_cm: her bottoms' waistband against what is under it, in 24 sectors (15 deg) round the
         axis pelvis -> spine_03, 0 deg = HER forward (up x her left, from her thighs; checked by her knees), + towards
         her left. Per sector, in 1 cm cells down the
         band (BAND_CM from the trousers' top edge): radii from the axis of the trousers (inner/outer) and of the
         outermost layer under them (the Top, else her skin). gap = trousers inner - under (stand-off), poke = under -
         trousers outer (> 0: skin or Top OUT through the waistband). Plus per sector: the edge height, the Top's
         lowest point vs the edge (tuck > 0 = tucked; < 0 = a band of bare skin between them), the Top lying OVER the
         band (blousing), and the edge height above her natural waist (the narrowest girth of her skin).
         waist_fit_cm (the gate number) = the worst of front-half gap and poke and bare skin (cm).

Run where film-ue runs (the box driver); per frame it scrubs F+1 then F (as qa.clip):
    cd <tree>/tools && uv run python ../films/host-studio/reel/r7/garment_measure.py --box conf arms \\
        --seq <SEQ> --frames 1290-1400:5 --out /srv/ue/reel/r7/garment/arms_v2b
    ... waist --seq <SEQ> --frames 1290-1400:5,<more> --out /srv/ue/reel/r7/garment/waist_v2b
    ... cleanup     (removes the temp ref-pose actors if a run was cut off)
--frames: comma list of F or A-B or A-B:STEP. Pure helpers are tested off the box (test_garment_measure.py).
"""
import json
import math

NS = 24
REST = "FMQA_R7Rest"
SPINE = ["pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01"]


# ---------------------------------------------------------------------------------------- pure (tested off the box)
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    n = math.sqrt(dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


def seg_t(p, a, b):
    """(distance from p to segment ab, t in [0, 1] of the closest point)."""
    ab = sub(b, a)
    L = dot(ab, ab)
    t = max(0.0, min(1.0, dot(sub(p, a), ab) / L)) if L > 1e-12 else 0.0
    c = (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)
    return math.dist(p, c), t


def closest_on_tri(p, a, b, c):
    """Closest point to p on triangle abc (Ericson, Real-Time Collision Detection 5.1.5)."""
    ab, ac, ap = sub(b, a), sub(c, a), sub(p, a)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a
    bp = sub(p, b)
    d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return (a[0] + ab[0] * v, a[1] + ab[1] * v, a[2] + ab[2] * v)
    cp = sub(p, c)
    d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return (a[0] + ac[0] * w, a[1] + ac[1] * w, a[2] + ac[2] * w)
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return (b[0] + (c[0] - b[0]) * w, b[1] + (c[1] - b[1]) * w, b[2] + (c[2] - b[2]) * w)
    den = 1.0 / (va + vb + vc)
    v, w = vb * den, vc * den
    return (a[0] + ab[0] * v + ac[0] * w, a[1] + ab[1] * v + ac[1] * w, a[2] + ab[2] * v + ac[2] * w)


class TriGrid:
    """Triangles hashed by bounding box into CELL cm cells; nearest() = the closest triangle to a point."""

    def __init__(self, tris, cell=2.0):
        """tris: [(a, b, c, normal, tag)]."""
        self.tris, self.cell, self.g = tris, cell, {}
        for k, (a, b, c, _, _) in enumerate(tris):
            lo = [int(math.floor(min(a[i], b[i], c[i]) / cell)) for i in range(3)]
            hi = [int(math.floor(max(a[i], b[i], c[i]) / cell)) for i in range(3)]
            for x in range(lo[0], hi[0] + 1):
                for y in range(lo[1], hi[1] + 1):
                    for z in range(lo[2], hi[2] + 1):
                        self.g.setdefault((x, y, z), []).append(k)

    def nearest(self, p, max_d=20.0):
        """(distance, closest point, triangle index) or None within max_d."""
        cx, cy, cz = (int(math.floor(p[i] / self.cell)) for i in range(3))
        best, seen = None, set()
        for r in range(int(max_d / self.cell) + 2):
            if best is not None and best[0] < (r - 1) * self.cell:
                break
            for x in range(cx - r, cx + r + 1):
                for y in range(cy - r, cy + r + 1):
                    for z in range(cz - r, cz + r + 1):
                        if max(abs(x - cx), abs(y - cy), abs(z - cz)) != r:
                            continue
                        for k in self.g.get((x, y, z), ()):
                            if k in seen:
                                continue
                            seen.add(k)
                            a, b, c, _, _ = self.tris[k]
                            q = closest_on_tri(p, a, b, c)
                            d = math.dist(p, q)
                            if best is None or d < best[0]:
                                best = (d, q, k)
        return best if best is not None and best[0] <= max_d else None


def tri_normal(a, b, c):
    return norm(cross(sub(b, a), sub(c, a)))


def label_rest(P, segs, used=None):
    """Per vertex: (name of the nearest segment, t along it, distance). segs: {name: (a, b)}. used: vertex ids."""
    out = {}
    for i in (used if used is not None else range(len(P))):
        best = None
        for n, (a, b) in segs.items():
            d, t = seg_t(P[i], a, b)
            if best is None or d < best[0]:
                best = (d, n, t)
        out[i] = (best[1], best[2], best[0])
    return out


def arm_radius(lab, side, lo=0.6, hi=0.95):
    """Median distance of the upper arm's skin from its bone on the free lower part (t lo..hi) at the ref pose."""
    ds = sorted(d for n, t, d in lab.values() if n == f"upperarm_{side}" and lo <= t <= hi)
    return ds[len(ds) // 2] if ds else None


def is_torso_seg(n):
    return n.startswith("spine:") or n.startswith("clavicle_")


def arm_sets(lab, rest_P, shoulder, side, arm_t0=0.3, axilla_cm=7.0, arm_r=None, margin=1.0):
    """(arm vertex ids, torso vertex ids) for one side from the ref-pose labels. Arm: nearest segment upperarm_<s>,
    t >= arm_t0 and within arm_r of the bone (v2b run 1: without the radius, her side's skin under the A-pose arm was
    'arm' and sat inside the Top: -10.4 cm everywhere). Torso: nearest a spine/clavicle segment, or nearest that upper
    arm but farther than arm_r + margin from it (her side under the arm); either way > axilla_cm from the shoulder."""
    arm, torso = [], []
    for i, (n, t, d) in lab.items():
        if n == f"upperarm_{side}" and t >= arm_t0 and (arm_r is None or d <= arm_r):
            arm.append(i)
        elif (is_torso_seg(n) or (arm_r is not None and n == f"upperarm_{side}" and d > arm_r + margin)) and \
                math.dist(rest_P[i], shoulder) > axilla_cm:
            torso.append(i)
    return arm, torso


def spine_out(p, chain):
    """Unit vector from the nearest point of the spine chain (posed joint list) to p."""
    best = None
    for a, b in zip(chain, chain[1:]):
        d, t = seg_t(p, a, b)
        if best is None or d < best[0]:
            best = (d, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t))
    return norm(sub(p, best[1]))


def torso_tris(P, T, keep, tag, chain=None):
    """Triangles of mesh (P, T) whose three corners are all in keep, as TriGrid entries. chain: turn each normal
    away from the spine chain (a closed garment shell: its inner face points in)."""
    out = []
    for a, b, c in T:
        if a in keep and b in keep and c in keep:
            pa, pb, pc = P[a], P[b], P[c]
            n = tri_normal(pa, pb, pc)
            if chain is not None:
                m = ((pa[0] + pb[0] + pc[0]) / 3, (pa[1] + pb[1] + pc[1]) / 3, (pa[2] + pb[2] + pc[2]) / 3)
                if dot(n, spine_out(m, chain)) < 0:
                    n = (-n[0], -n[1], -n[2])
            out.append((pa, pb, pc, n, tag))
    return out


def clearance(grid, arm_pts, max_d=20.0):
    """Signed clearance of each arm point to the grid's surface: (min, its record, count < 0, count < 3 cm)."""
    worst, neg, lt3 = None, 0, 0
    for i, p in arm_pts:
        hit = grid.nearest(p, max_d)
        if hit is None:
            continue
        d, q, k = hit
        s = d if dot(sub(p, q), grid.tris[k][3]) >= 0 else -d
        neg += s < 0
        lt3 += s < 3.0
        if worst is None or s < worst[0]:
            worst = (s, i, q, grid.tris[k][4])
    return worst, neg, lt3


class Cyl:
    """Cylindrical coordinates round the axis o -> o + u; 0 deg along fwd, + towards left."""

    def __init__(self, o, top, fwd, left):
        self.o = o
        self.u = norm(sub(top, o))
        f = sub(fwd, tuple(x * dot(fwd, self.u) for x in self.u))
        self.f = norm(f)
        self.l = cross(self.u, self.f)
        if dot(self.l, left) < 0:
            self.l = (-self.l[0], -self.l[1], -self.l[2])

    def __call__(self, p):
        q = sub(p, self.o)
        t = dot(q, self.u)
        w = (q[0] - self.u[0] * t, q[1] - self.u[1] * t, q[2] - self.u[2] * t)
        return t, math.sqrt(dot(w, w)), math.degrees(math.atan2(dot(w, self.l), dot(w, self.f)))


def sector(th):
    return int(((th + 7.5) % 360.0) // 15.0) % NS


def sector_deg(s):
    d = s * 15
    return d - 360 if d > 180 else d


def waist_sectors(trou, top, skin, band_cm=4.0, out_cm=2.5):
    """trou/top/skin: [(t, r, th)] (already cylindrical; top/skin may be empty). Per sector (24): the edge (max t of
    the trousers), per 1 cm cell down the band: gap / poke; the Top's lowest t (hem) and the Top over the band."""
    edge = [None] * NS
    for t, r, th in trou:
        s = sector(th)
        if edge[s] is None or t > edge[s]:
            edge[s] = t
    cells = {}

    def cell(s, t):
        if edge[s] is None or t > edge[s] + 0.5 or t < edge[s] - band_cm:
            return None
        return (s, int((edge[s] - t) // 1.0))

    for t, r, th in trou:
        k = cell(sector(th), t)
        if k is not None:
            c = cells.setdefault(k, {"tin": 1e9, "tout": 0.0, "top": 0.0, "skin": 0.0})
            c["tin"], c["tout"] = min(c["tin"], r), max(c["tout"], r)
    hem = [None] * NS
    for t, r, th in top:
        s = sector(th)
        if hem[s] is None or t < hem[s]:
            hem[s] = t
    for name, pts in (("top", top), ("skin", skin)):
        for t, r, th in pts:
            k = cell(sector(th), t)
            if k is not None and k in cells and r <= cells[k]["tout"] + out_cm:  # beyond: an arm/hand, not a poke
                cells[k][name] = max(cells[k][name], r)
    out = []
    for s in range(NS):
        if edge[s] is None:
            out.append(None)
            continue
        gaps, pokes, over = [], [], []
        for (ss, j), c in sorted(cells.items()):
            if ss != s:
                continue
            under = c["top"] or c["skin"]
            if not under:
                continue
            if j >= 1:  # the edge row itself is the band's rim (its own thickness folds there)
                gaps.append(round(c["tin"] - under, 2))
            pokes.append(round(max(c["top"], c["skin"]) - c["tout"], 2))
            over.append(round(c["top"] - c["tout"], 2) if c["top"] else None)
        tuck = round(edge[s] - hem[s], 2) if hem[s] is not None else None
        out.append({"deg": sector_deg(s), "edge_t": round(edge[s], 2), "tuck": tuck,
                    "gap_max": max(gaps) if gaps else None, "gap_p50": sorted(gaps)[len(gaps) // 2] if gaps else None,
                    "poke_max": max(pokes) if pokes else None,
                    "top_over_max": max((x for x in over if x is not None), default=None), "cells": len(gaps)})
    return out


def natural_waist(skin, lo, hi):
    """t (cm along the axis) of the narrowest skin girth between lo and hi: per 1 cm slice the median radius."""
    rows = {}
    for t, r, th in skin:
        if lo <= t <= hi and r < 25.0:
            rows.setdefault(int(t // 1.0), []).append(r)
    best = None
    for k, rs in rows.items():
        if len(rs) < 24:
            continue
        rs.sort()
        m = rs[len(rs) // 2]
        if best is None or m < best[1]:
            best = (k + 0.5, m)
    return best


def waist_score(sectors, front=90.0, bare_tol=0.0):
    """The gate number: the worst over the front half (|deg| <= front) of gap_max, poke_max and bare skin (-tuck)."""
    worst, why = 0.0, None
    for s in sectors:
        if not s or abs(s["deg"]) > front:
            continue
        for k, v in (("gap", s["gap_max"]), ("poke", s["poke_max"]),
                     ("bare_skin", -s["tuck"] - bare_tol if s["tuck"] is not None else None)):
            if v is not None and v > worst:
                worst, why = v, f"{k} at {s['deg']} deg"
    return round(worst, 2), why


def parse_frames(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            rng, _, step = part.partition(":")
            a, b = (int(x) for x in rng.split("-"))
            out.extend(range(a, b + 1, int(step or 1)))
        else:
            out.append(int(part))
    return out


# ---------------------------------------------------------------------------------------- editor
def _editor(G: dict):
    import unreal
    MQ, LU, SU = unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List, unreal.GeometryScript_SceneUtils
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    W = unreal.RelativeTransformSpace.RTS_WORLD
    label = G.get("LABEL", "Presenter")

    def pick(res, cls):
        items = res if isinstance(res, tuple) else (res,)
        return next((x for x in items if type(x).__name__ == cls), items[0])

    def actor(lab):
        return next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == lab), None)

    def mesh_of(c):
        opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
        lod = unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
        lod.set_editor_property("lod_index", 0)
        opts.set_editor_property("requested_lod", lod)
        dm = unreal.DynamicMesh()
        SU.copy_mesh_from_component(c, dm, opts, True)
        P = [(p.x, p.y, p.z) for p in LU.convert_vector_list_to_array(
            pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList"))]
        fn = getattr(MQ, "get_all_triangle_indices", None)
        if fn:
            T = [(int(t.x), int(t.y), int(t.z)) for t in LU.convert_triangle_list_to_array(
                pick(fn(dm, False), "GeometryScriptTriangleList"))]
        else:
            T = []
            for tid in range((getattr(MQ, "get_num_triangle_i_ds", None) or MQ.get_num_triangle_ids)(dm)):
                iv = pick(MQ.get_triangle_indices(dm, tid), "IntVector")
                if iv.x >= 0:
                    T.append((int(iv.x), int(iv.y), int(iv.z)))
        return P, [t for t in T if t[0] >= 0]

    def fwd_of(a):
        v = a.get_actor_forward_vector()
        return (v.x, v.y, v.z)

    def facing(lb, rb, lo="pelvis", hi="spine_03"):
        """Her own forward from her skeleton (not the actor's: v2b's angles came out 90 deg round): up x (left -
        right) in UE's frame (X fwd, Y right, Z up), checked against her knees (seated: in front of the pelvis)."""
        u = norm(sub(loc(body, hi), loc(body, lo)))
        f = norm(cross(u, sub(loc(body, lb), loc(body, rb))))
        knees = tuple((a + b) / 2 for a, b in zip(loc(body, "calf_l"), loc(body, "calf_r")))
        flipped = dot(f, sub(knees, loc(body, "pelvis"))) < 0
        if flipped:
            f = (-f[0], -f[1], -f[2])
        af = fwd_of(host)
        ang = math.degrees(math.atan2(dot(cross(af, f), u), dot(af, f)))
        return f, {"facing_vs_actor_deg": round(ang), "facing_flipped_by_knees": flipped}

    def loc(c, bone):
        v = c.get_socket_location(bone)
        return (v.x, v.y, v.z)

    def cleanup():
        n = 0
        for a in list(EAS.get_all_level_actors()):
            if a.get_actor_label().startswith(REST):
                EAS.destroy_actor(a)
                n += 1
        return n

    stage = G.get("STAGE")
    if stage == "cleanup":
        return {"removed": cleanup()}
    host = actor(label)
    cs = {c.get_name(): c for c in host.get_components_by_class(unreal.SkeletalMeshComponent)}
    body = cs["Body"]
    head = loc(body, "head")

    if stage == "arms":
        top = cs.get(G.get("TOP", "Top"))
        parts = [("Body", body)] + ([("Top", top)] if top is not None and top.is_visible() else [])

        def segs_of(c):
            s = {f"spine:{a}": (loc(c, a), loc(c, b)) for a, b in zip(SPINE, SPINE[1:])}
            s["neck"] = (loc(c, "neck_01"), loc(c, "head"))
            for sd in ("l", "r"):
                s[f"clavicle_{sd}"] = (loc(c, f"clavicle_{sd}"), loc(c, f"upperarm_{sd}"))
                s[f"upperarm_{sd}"] = (loc(c, f"upperarm_{sd}"), loc(c, f"lowerarm_{sd}"))
                s[f"lowerarm_{sd}"] = (loc(c, f"lowerarm_{sd}"), loc(c, f"hand_{sd}"))
                s[f"hand_{sd}"] = (loc(c, f"hand_{sd}"), loc(c, f"middle_01_{sd}"))
                s[f"thigh_{sd}"] = (loc(c, f"thigh_{sd}"), loc(c, f"calf_{sd}"))
                s[f"calf_{sd}"] = (loc(c, f"calf_{sd}"), loc(c, f"foot_{sd}"))
            return s

        posed = {n: mesh_of(c) for n, c in parts}
        rest, rest_bones, rest_chain = {}, None, None
        cleanup()
        try:
            for n, c in parts:
                ra = EAS.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
                ra.set_actor_label(f"{REST}_{n}")
                rc = ra.get_editor_property("skeletal_mesh_component")
                rc.set_skeletal_mesh_asset(c.get_skeletal_mesh_asset())
                if math.dist(loc(rc, "neck_01"), loc(rc, "spine_05")) < 2.0:
                    raise RuntimeError("the temp ref-pose actor has no pose yet: run arms again")
                rest[n] = mesh_of(rc)
                if n == "Body":
                    rest_bones = segs_of(rc), {sd: loc(rc, f"upperarm_{sd}") for sd in ("l", "r")}
                    rest_chain = [loc(rc, b) for b in SPINE]
        finally:
            cleanup()
        chain = [loc(body, b) for b in SPINE]
        out = {"frame_head": [round(x, 2) for x in head], "parts": {}, "sides": {},
               **facing("clavicle_l", "clavicle_r")[1]}
        labels = {}
        for n, _ in parts:
            (Pp, Tp), (Pr, Tr) = posed[n], rest[n]
            if len(Pp) != len(Pr) or len(Tp) != len(Tr):
                raise RuntimeError(f"{n}: posed {len(Pp)} verts/{len(Tp)} tris vs ref pose {len(Pr)}/{len(Tr)}: the "
                                   "render copies do not line up")
            used = sorted({i for t in Tp for i in t})
            labels[n] = label_rest(Pr, rest_bones[0], used)
            out["parts"][n] = {"verts": len(Pp), "tris": len(Tp)}
        for sd in ("r", "l"):
            sh = rest_bones[1][sd]
            r_med = arm_radius(labels["Body"], sd)
            arm_r = float(G["ARM_R"]) if G.get("ARM_R") else (r_med * float(G.get("ARM_R_X", 1.3)) if r_med else None)
            arm, _ = arm_sets(labels["Body"], rest["Body"][0], sh, sd, float(G.get("ARM_T0", 0.3)),
                              float(G.get("AXILLA_CM", 7.0)), arm_r)
            entries, rest_entries = [], []
            for n, _ in parts:
                _, torso = arm_sets(labels[n], rest[n][0], sh, sd, 1.1, float(G.get("AXILLA_CM", 7.0)), arm_r)
                entries += torso_tris(posed[n][0], posed[n][1], set(torso), n, chain if n != "Body" else None)
                rest_entries += torso_tris(rest[n][0], rest[n][1], set(torso), n, rest_chain if n != "Body" else None)
            grid = TriGrid(entries, float(G.get("CELL", 2.0)))
            P = posed["Body"][0]
            worst, neg, lt3 = clearance(grid, [(i, P[i]) for i in arm], float(G.get("MAX_D", 20.0)))
            # self-check: the same sets on the ref pose (arms out, clear of the torso) must read > 0, else the
            # arm/torso split is wrong and the posed number means nothing
            rw, rneg, _ = clearance(TriGrid(rest_entries, float(G.get("CELL", 2.0))),
                                    [(i, rest["Body"][0][i]) for i in arm], float(G.get("MAX_D", 20.0)))
            ua, la = loc(body, f"upperarm_{sd}"), loc(body, f"lowerarm_{sd}")
            rec = {"arm_verts": len(arm), "torso_tris": len(entries), "verts_lt0": neg, "verts_lt3": lt3,
                   "arm_r_med": r_med and round(r_med, 2), "arm_r": arm_r and round(arm_r, 2),
                   "rest_clear_cm": rw and round(rw[0], 2), "rest_verts_lt0": rneg}
            if worst:
                s, i, q, tag = worst
                cy = Cyl(chain[0], chain[3], facing("clavicle_l", "clavicle_r")[0],
                         sub(loc(body, "clavicle_l"), loc(body, "clavicle_r")))  # her left, a direction
                tq, _, thq = cy(q)
                rec.update({"clear_cm": round(s, 2), "arm_t": round(seg_t(P[i], ua, la)[1], 2), "torso_part": tag,
                            "torso_t_cm": round(tq, 1), "torso_deg": round(thq)})
            out["sides"][sd] = rec
        cl = [r["clear_cm"] for r in out["sides"].values() if "clear_cm" in r]
        out["upperarm_torso_clear_cm"] = min(cl) if cl else None
        return out

    if stage == "waist":
        trou, top = cs[G.get("TROUSERS", "Trousers")], cs.get(G.get("TOP", "Top"))
        fw, fdiag = facing("thigh_l", "thigh_r")
        cy = Cyl(loc(body, "pelvis"), loc(body, "spine_03"), fw,
                 sub(loc(body, "clavicle_l"), loc(body, "clavicle_r")))  # her left, a direction

        def cyl_pts(c, rmax=40.0):
            P, T = mesh_of(c)
            used = {i for t in T for i in t}
            pts = [cy(P[i]) for i in used]
            return [x for x in pts if x[1] < rmax], len(T)

        tp, tn = cyl_pts(trou)
        topp, topn = cyl_pts(top) if top is not None and top.is_visible() else ([], 0)
        skin, _ = cyl_pts(body)
        band = float(G.get("BAND_CM", 4.0))
        secs = waist_sectors(tp, topp, skin, band, float(G.get("OUT_CM", 2.5)))
        lo = min(t for t, _, _ in tp) if tp else -5.0
        top_t = max(s["edge_t"] for s in secs if s) if any(secs) else 0.0
        nw = natural_waist(skin, top_t - 15.0, top_t + 15.0)
        score, why = waist_score(secs, float(G.get("FRONT_DEG", 90.0)))
        front = [s for s in secs if s and abs(s["deg"]) <= 90]
        res = {"frame_head": [round(x, 2) for x in head], "waist_fit_cm": score, "worst": why, **fdiag,
               "trousers_mesh": trou.get_skeletal_mesh_asset().get_path_name(), "trousers_tris": tn,
               "top_tris": topn, "natural_waist_t": nw and round(nw[0], 1),
               "edge_above_natural_waist_cm": nw and round(sorted(s["edge_t"] for s in front)[len(front) // 2] - nw[0], 1)
               if front else None,
               "edge_wave_front_cm": round(max(s["edge_t"] for s in front) - min(s["edge_t"] for s in front), 2)
               if front else None, "trousers_t_low": round(lo, 1), "sectors": secs}
        orig = G.get("ORIG_TROUSERS", "/Game/Host/Presenter_Outfit/SKM_Presenter_Trousers")
        if orig and res["trousers_mesh"].split(".")[0] != orig:
            AU = unreal.GeometryScript_AssetUtils
            dm = unreal.DynamicMesh()
            rl = unreal.GeometryScriptMeshReadLOD()
            rl.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
            rl.set_editor_property("lod_index", 0)
            try:
                AU.copy_mesh_from_skeletal_mesh(unreal.load_asset(orig), dm,
                                                unreal.GeometryScriptCopyMeshFromAssetOptions(), rl)
                res["orig_trousers_tris"] = MQ.get_triangle_count(dm)
            except Exception as e:  # noqa: BLE001
                res["orig_trousers_tris"] = f"? {e}"
        return res
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
    sub_ = ap.add_subparsers(dest="cmd", required=True)
    for name in ("arms", "waist"):
        m = sub_.add_parser(name)
        m.add_argument("--seq", required=True)
        m.add_argument("--frames", required=True, help="F, A-B or A-B:STEP, comma separated")
        m.add_argument("--out", required=True)
        m.add_argument("--set", action="append", default=[], help="KEY=VALUE knob (ARM_T0, AXILLA_CM, BAND_CM, ...)")
    sub_.add_parser("cleanup")
    a = ap.parse_args(argv)
    if a.box != "conf":
        os.environ["FILM_UE_BOX"] = a.box
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
    from filmtools.unreal import client
    g = {"LABEL": a.label}
    if a.cmd == "cleanup":
        print(json.dumps(_exec(client, "cleanup", **g)))
        return 0
    for kv in a.set:
        k, _, v = kv.partition("=")
        g[k] = v
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    per, last = {}, None
    for f in parse_frames(a.frames):
        for ff in (f + 1, f):
            r = client.op("seq.scrub", path=a.seq, frame=ff)
            if not r.get("ok"):
                raise SystemExit(f"seq.scrub {ff}: {r}")
        res = _exec(client, a.cmd, **g)
        if last is not None and res["frame_head"] == last:
            print(f"WARN f{f}: head did not move since the last frame (pose not updated?)")
        last = res["frame_head"]
        per[f] = res
        if a.cmd == "arms":
            print(f"f{f}: clear {res['upperarm_torso_clear_cm']} (facing vs actor {res['facing_vs_actor_deg']} deg) | "
                  + " | ".join(
                f"{sd}: {r.get('clear_cm')} cm (arm_t {r.get('arm_t')}, {r.get('torso_part')} at t {r.get('torso_t_cm')}"
                f" cm, {r.get('torso_deg')} deg; <0 {r['verts_lt0']}, <3 {r['verts_lt3']} of {r['arm_verts']}; arm_r "
                f"{r.get('arm_r')}; rest {r.get('rest_clear_cm')}/{r.get('rest_verts_lt0')})"
                for sd, r in res["sides"].items()), flush=True)
        else:
            print(f"f{f}: waist_fit {res['waist_fit_cm']} cm ({res['worst']}; facing vs actor "
                  f"{res['facing_vs_actor_deg']} deg, knee flip {res['facing_flipped_by_knees']}); edge above waist "
                  f"{res['edge_above_natural_waist_cm']} cm, edge wave {res['edge_wave_front_cm']}; sectors "
                  "[deg, edge_t, tuck, gap_max, poke_max, top_over]: " + json.dumps(
                      [[s["deg"], s["edge_t"], s["tuck"], s["gap_max"], s["poke_max"], s["top_over_max"]]
                       for s in res["sectors"] if s]), flush=True)
    (out / f"{a.cmd}.json").write_text(json.dumps(per))
    key = "upperarm_torso_clear_cm" if a.cmd == "arms" else "waist_fit_cm"
    vals = {f: r[key] for f, r in per.items() if r.get(key) is not None}
    if vals:
        fw = (min if a.cmd == "arms" else max)(vals, key=vals.get)
        print(json.dumps({"measure": key, "worst_frame": fw, "worst": vals[fw], "frames": len(per),
                          "file": str(out / f"{a.cmd}.json")}))
    return 0


if __name__ == "__main__" and "_G" not in globals():
    import sys as _sys
    if len(_sys.argv) > 1:  # the driver CLI (an `unreal` stub may be importable off the box: never decide by that)
        raise SystemExit(main())
