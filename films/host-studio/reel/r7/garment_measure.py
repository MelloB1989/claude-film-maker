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
         Zones (orchestrator, round 7 ee99f626: the rule is for the arm swallowed by the BUST, not a relaxed arm by
         the ribcage): each torso triangle is front or side by where it sits on the ref pose, within FRONT_DEG (60)
         of her forward round the spine or not. upperarm_bust_clear_cm (front, >= 3) and upperarm_side_clear_cm
         (side, >= 0.5: no penetration, light contact reads natural), each with its own ref-pose self-check;
         upperarm_torso_clear_cm stays as the min of both. INSIDE is decided on the whole torso, never on a zone
         alone (zone_clearance: a zone is an open patch, and a point beside her side read -9.5 cm 'behind' the
         front patch's far edge on T2's rest frames while the whole torso read +1.5).
  waist  garment.waist_fit_cm: her bottoms' waistband against what is under it, in 24 sectors (15 deg) round the
         axis pelvis -> spine_03, 0 deg = HER forward (up x her left, from her thighs; checked by her knees), + towards
         her left. Per sector, in 1 cm cells down the
         band (BAND_CM from the trousers' top edge): radii from the axis of the trousers (inner/outer) and of the
         outermost layer under them (the Top, else her skin). gap = trousers inner - under (stand-off), poke = under -
         trousers outer (> 0: skin or Top OUT through the waistband). Plus per sector: the edge height, the Top's
         lowest point vs the edge (tuck > 0 = tucked; < 0 = a band of bare skin between them), the Top lying OVER the
         band (blousing), and the edge height above her natural waist (the narrowest girth of her skin).
         Gate keys (agent-09's split, front half): waist_fit_cm = worst gap or bare skin (<= 0.75; v2b 1.04);
         waist_poke_cm = worst poke (<= 0.1; R7W +0.46, seen as qa.clip Body>Trousers in the WIDE).
         waist_skin_poke_cm (all round) / waist_skin_poke_front_cm (round 7, orchestrator: seated frames must read 0;
         her skin through the band's lower edge in the WIDE, which a cell's max radius can hide): per skin vertex
         from RIM_CM (0.5) below the edge down POKE_CM (10), only skin nearest a torso/hip/thigh bone, the signed
         distance to the nearest trousers triangle (normal away from the axis; out only at alignment >= POKE_ALIGN
         0.5). <= 0 = nothing out; the console names the worst vertex's deg and depth below the edge.

Run where film-ue runs (the box driver); per frame it scrubs F+1 then F (as qa.clip):
    cd <tree>/tools && uv run python ../films/host-studio/reel/r7/garment_measure.py --box conf arms \\
        --seq <SEQ> --frames 1290-1400:5 --out /srv/ue/reel/r7/garment/arms_v2b
    ... waist --seq <SEQ> --frames 1290-1400:5,<more> --out /srv/ue/reel/r7/garment/waist_v2b
    ... cleanup     (removes the temp ref-pose actors if a run was cut off)
    arms --engine fast [--tree /srv/ue/r7tree]: the editor writes the posed meshes (the ref pose once) to a box-local
        /tmp dir and runs garment_fast.py in the box's tree with uv (numpy; same numbers: test_garment_fast.py); only
        the numbers come back to the driver, wherever it runs; the files are removed at the end (cleanup). Each
        reading records its seconds.
--frames: comma list of F or A-B or A-B:STEP. Pure helpers are tested off the box (test_garment_measure.py).
"""
import json
import math

NS = 24
REST = "FMQA_R7Rest"
DUMP_ROOT = "/tmp/fmqa_r7_arms_"   # the fast path's box-local mesh files (presenter geometry: box only)
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


def arm_sets(lab, rest_P, shoulder, side, arm_t0=0.3, axilla_cm=7.0, arm_r=None, margin=1.5, torso_t0=0.45,
             sleeves=False):
    """(arm vertex ids, torso vertex ids) for one side from the ref-pose labels. Arm: nearest segment upperarm_<s>,
    t >= arm_t0 and within arm_r of the bone (v2b run 1: without the radius, her side's skin under the A-pose arm was
    'arm' and sat inside the Top: -10.4 cm everywhere). Torso: nearest a spine/clavicle segment, or nearest that upper
    arm but farther than arm_r + margin from it AND past torso_t0 down the bone (her side under the arm; v2b r7w: with
    no t floor the deltoid/armpit at t 0.25, 5.1 cm off the bone, was 'torso' next to arm points at t 0.3, and the
    self-check read -4.4); either way > axilla_cm from the shoulder. sleeves (a garment with sleeves, his tee): no
    vertex nearest an upper arm is torso (his loose sleeve, > arm_r + margin off the bone, read as torso round his own
    arm: about -5 cm on 130-210 verts in every frame)."""
    arm, torso = [], []
    for i, (n, t, d) in lab.items():
        if n == f"upperarm_{side}" and t >= arm_t0 and (arm_r is None or d <= arm_r):
            arm.append(i)
        elif (is_torso_seg(n) or (not sleeves and arm_r is not None and n == f"upperarm_{side}" and d > arm_r + margin
                                  and t >= torso_t0)) and \
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
            out.append((pa, pb, pc, n, (tag, a)))
    return out


def chain_dist(p, chain):
    return min(seg_t(p, a, b)[0] for a, b in zip(chain, chain[1:]))


def front_deg(p, chain, fwd):
    """How far round from her front p is (0 = straight ahead, 180 = her back): the angle between fwd and p's offset
    from the nearest spine segment, both taken square to that segment (a lean or a stoop does not move the zones)."""
    best = None
    for a, b in zip(chain, chain[1:]):
        d, t = seg_t(p, a, b)
        if best is None or d < best[0]:
            best = (d, a, b, t)
    _, a, b, t = best
    u = norm(sub(b, a))
    w = sub(p, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t))
    w = sub(w, tuple(x * dot(w, u) for x in u))
    f = sub(fwd, tuple(x * dot(fwd, u) for x in u))
    nw, nf = math.sqrt(dot(w, w)), math.sqrt(dot(f, f))
    if nw < 1e-9 or nf < 1e-9:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(w, f) / (nw * nf)))))


def front_flags(rest_entries, chain, fwd, front=60.0):
    """Per triangle: True = front zone, by where it sits on the ref pose (within FRONT_DEG of her forward round the
    spine: the bust and the front of the Top, what the camera sees the arm against); False = side (ribcage, back)."""
    return [front_deg(tuple((r[0][k] + r[1][k] + r[2][k]) / 3 for k in range(3)), chain, fwd) <= front
            for r in rest_entries]


def split_front(entries, rest_entries, chain, fwd, front=60.0):
    """(front, side) triangle lists; rest_entries line up with entries one for one."""
    fr, sd = [], []
    for e, f in zip(entries, front_flags(rest_entries, chain, fwd, front)):
        (fr if f else sd).append(e)
    return fr, sd


def clearance(grid, arm_pts, max_d=20.0, align=0.5, chain=None):
    """Signed clearance of each arm point to the grid's surface: (min, its record, count < 0, count < 3 cm)."""
    worst, neg, lt3 = None, 0, 0
    for i, p in arm_pts:
        hit = grid.nearest(p, max_d)
        if hit is None:
            continue
        d, q, k = hit
        al = dot(norm(sub(p, q)), grid.tris[k][3]) if d > 1e-6 else 1.0
        # inside only when the point lies (mostly) BEHIND the face: at the torso patch's open edge (where the arm and
        # the armpit were cut out) the nearest point is on that edge and the face normal says nothing (v2b2's
        # ref-pose -13.7 cm: arm points beside the patch, read as 'behind' it)
        # and only when it is nearer the spine than the face is (R7 f1104: a raised arm 13.9 cm off a curved
        # patch read as 'behind' it; nothing can be inside her torso by more than its own depth)
        s = -d if al <= -align and (chain is None or chain_dist(p, chain) < chain_dist(q, chain)) else d
        neg += s < 0
        lt3 += s < 3.0
        if worst is None or s < worst[0]:
            worst = (s, i, q, grid.tris[k][4], round(al, 2))
    return worst, neg, lt3


def zone_clearance(full, zone_of, grids, arm_pts, max_d=20.0, align=0.5, chain=None):
    """Per-zone signed clearance with the INSIDE test on the whole torso (full; zone_of[k] = the zone of full's
    triangle k). A zone alone is an open patch: a point beside her SIDE lay 'behind' the far edge of the front patch
    and read ~-9.5 cm in the front zone while the whole torso read +1.5 (T2 rest, 8a45d961). So: a point inside the
    whole torso counts negative in the zone of its nearest triangle only; every other reading is the plain distance
    to that zone. {zone: (worst, count < 0, count < 3 cm)}, worst as clearance()."""
    out = {z: [None, 0, 0] for z in grids}
    for i, p in arm_pts:
        hit = full.nearest(p, max_d)
        inside_z = None
        if hit is not None:
            d, q, k = hit
            al = dot(norm(sub(p, q)), full.tris[k][3]) if d > 1e-6 else 1.0
            if al <= -align and (chain is None or chain_dist(p, chain) < chain_dist(q, chain)):
                inside_z = zone_of[k]
                rec = (-d, i, q, full.tris[k][4], round(al, 2))
        for z, g in grids.items():
            if z == inside_z:
                r = rec
            else:
                h = g.nearest(p, max_d)
                if h is None:
                    continue
                dz, qz, kz = h
                alz = dot(norm(sub(p, qz)), g.tris[kz][3]) if dz > 1e-6 else 1.0
                r = (dz, i, qz, g.tris[kz][4], round(alz, 2))
            o = out[z]
            o[1] += r[0] < 0
            o[2] += r[0] < 3.0
            if o[0] is None or r[0] < o[0][0]:
                o[0] = r
    return {z: tuple(v) for z, v in out.items()}


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
            pokes.append((round(max(c["top"], c["skin"]) - c["tout"], 2), j,
                          "Top" if c["top"] >= c["skin"] else "skin"))
            over.append(round(c["top"] - c["tout"], 2) if c["top"] else None)
        tuck = round(edge[s] - hem[s], 2) if hem[s] is not None else None
        out.append({"deg": sector_deg(s), "edge_t": round(edge[s], 2), "tuck": tuck,
                    "gap_max": max(gaps) if gaps else None, "gap_p50": sorted(gaps)[len(gaps) // 2] if gaps else None,
                    "poke_max": max(pokes)[0] if pokes else None,
                    "poke_row": max(pokes)[1] if pokes else None, "poke_by": max(pokes)[2] if pokes else None,
                    "top_over_max": max((x for x in over if x is not None), default=None), "cells": len(gaps)})
    return out


def surface_poke(trou_P, trou_T, skin, cy, edge, poke_cm=10.0, rim_cm=0.5, align=0.5, cell=2.0, max_d=6.0):
    """Per skin vertex (round 7, her WIDE: skin through the band's lower edge, which a 15 deg x 1 cm cell's max radius
    can hide): signed distance to the nearest trousers triangle, its normal turned away from the axis (cy), + = OUT
    through the cloth. Only for skin from rim_cm below the trousers' edge (edge[sector], cylindrical t) down poke_cm,
    and an out-reading counts only clearly in front of the face (alignment >= align; at a hole's edge, a fly or a
    seam, the nearest point is on the edge and the reading is oblique). skin: [(i, p)], already only torso/hip/thigh
    skin (hands on the lap sit outside the cloth by right). Returns {poke_cm (all round), poke_front_cm (|deg| <= 90),
    verts_gt0, verts_gt01, verts, where} with where = the worst's vertex, deg, cm below the edge and alignment."""
    tris = []
    for a, b, c in trou_T:
        pa, pb, pc = trou_P[a], trou_P[b], trou_P[c]
        n = tri_normal(pa, pb, pc)
        if n == (0.0, 0.0, 0.0):  # a collapsed triangle (her trousers have some: T2's first run, a zero division)
            continue
        m = ((pa[0] + pb[0] + pc[0]) / 3, (pa[1] + pb[1] + pc[1]) / 3, (pa[2] + pb[2] + pc[2]) / 3)
        q = sub(m, cy.o)
        t = dot(q, cy.u)
        if dot(n, (q[0] - cy.u[0] * t, q[1] - cy.u[1] * t, q[2] - cy.u[2] * t)) < 0:
            n = (-n[0], -n[1], -n[2])
        tris.append((pa, pb, pc, n, a))
    grid = TriGrid(tris, cell)
    worst, front, gt0, gt01, n_in = None, None, 0, 0, 0
    for i, p in skin:
        t, r, th = cy(p)
        e = edge[sector(th)]
        if e is None or t > e - rim_cm or t < e - poke_cm:
            continue
        hit = grid.nearest(p, max_d)
        if hit is None:
            continue
        n_in += 1
        d, q, k = hit
        al = dot(norm(sub(p, q)), tris[k][3]) if d > 1e-6 else 0.0
        s = d if al >= align else -d
        gt0 += s > 0
        gt01 += s > 0.1
        rec = (s, i, round(th), round(e - t, 1), round(al, 2))
        if worst is None or s > worst[0]:
            worst = rec
        if abs(th) <= 90.0 and (front is None or s > front[0]):
            front = rec
    if worst is None:
        return {"poke_cm": None, "poke_front_cm": None, "verts_gt0": 0, "verts_gt01": 0, "verts": 0, "where": None}
    return {"poke_cm": round(worst[0], 2), "poke_front_cm": front and round(front[0], 2), "verts_gt0": gt0,
            "verts_gt01": gt01, "verts": n_in,
            "where": {"vert": worst[1], "deg": worst[2], "below_edge_cm": worst[3], "align": worst[4]}}


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
    """The gate numbers over the front half (|deg| <= front), agent-09's split (r7: one number hid R7W's poke):
    waist_fit_cm = the worst of gap_max and bare skin (-tuck), floored at 0; waist_poke_cm = the worst poke_max
    (> 0: skin or Top out past the band). Returns (fit, why, poke, poke_why)."""
    fit, why, poke, pwhy = 0.0, None, None, None
    for s in sectors:
        if not s or abs(s["deg"]) > front:
            continue
        for k, v in (("gap", s["gap_max"]), ("bare_skin", -s["tuck"] - bare_tol if s["tuck"] is not None else None)):
            if v is not None and v > fit:
                fit, why = v, f"{k} at {s['deg']} deg"
        if s["poke_max"] is not None and (poke is None or s["poke_max"] > poke):
            poke, pwhy = s["poke_max"], f"{s.get('poke_by')} at {s['deg']} deg, row {s.get('poke_row')}"
    return round(fit, 2), why, poke, pwhy


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


def to_seq_frames(frames, src_fps, seq_fps):
    """Source frames -> the sequence's own frames BY TIME (t = f / src_fps; the orchestrator's rule: never frame to
    frame across clocks, arm_track is 30 fps, the sequence 24). [(seq_frame, src_frame, t_s)], first source frame wins
    when two land on one sequence frame."""
    out, seen = [], set()
    for f in frames:
        t = f / float(src_fps)
        g = int(round(t * float(seq_fps)))
        if g not in seen:
            seen.add(g)
            out.append((g, f, round(t, 4)))
    return out


class PyEngine:
    """The arm measure's geometry in plain Python (the editor has no numpy). garment_fast.NpEngine: the same calls
    with numpy/scipy, for the driver on the box (the numbers agree: test_garment_fast.py)."""

    def __init__(self, cell=2.0):
        self.cell = cell

    def label_rest(self, P, segs, used):
        return label_rest(P, segs, used)

    def tris(self, P, T, keep, tag, chain):
        return torso_tris(P, T, set(keep), tag, chain)

    def cat(self, sets):
        return [e for ts in sets for e in ts]

    def take(self, ts, flags, want):
        return [e for e, f in zip(ts, flags) if f == want]

    def n(self, ts):
        return len(ts)

    def flags(self, ts, chain, fwd, front):
        return front_flags(ts, chain, fwd, front)

    def clear(self, ts, idx, P, max_d, chain):
        return clearance(TriGrid(ts, self.cell), [(i, P[i]) for i in idx], max_d, chain=chain)

    def zclear(self, full, zof, zones, idx, P, max_d, chain):
        return zone_clearance(TriGrid(full, self.cell), zof, {z: TriGrid(t, self.cell) for z, t in zones.items()},
                              [(i, P[i]) for i in idx], max_d, chain=chain)


def rigid_map(p, a0, b0, a1, b1):
    """p moved with the segment a0 -> b0 onto a1 -> b1 (the smallest rotation about a0, then a0 -> a1): the Body's
    ref-pose arm put into a garment's own ref pose, for that garment's self-check."""
    u0, u1 = norm(sub(b0, a0)), norm(sub(b1, a1))
    v = sub(p, a0)
    k = cross(u0, u1)
    s_, c = math.sqrt(dot(k, k)), dot(u0, u1)
    if s_ > 1e-9:
        k = (k[0] / s_, k[1] / s_, k[2] / s_)
        kv, kd = cross(k, v), dot(k, v)
        v = tuple(v[i] * c + kv[i] * s_ + k[i] * kd * (1 - c) for i in range(3))
    elif c < 0:
        v = (-v[0], -v[1], -v[2])
    return (a1[0] + v[0], a1[1] + v[1], a1[2] + v[2])


def _min_check(results):
    """Several self-checks of one kind -> one: the lowest reading, the inside counts summed."""
    rs = [r for r in results if r[0] is not None]
    if not rs:
        return (None, 0, 0)
    w = min(rs, key=lambda r: r[0][0])[0]
    return (w, sum(r[1] for r in rs), sum(r[2] for r in rs))


def arms_compute(D, G, E, cache=None):
    """body.upperarm_*_clear_cm for one frame from the posed + ref-pose meshes (D: what the editor read; E: PyEngine
    or garment_fast.NpEngine). cache: kept between the frames of one run (labels, the arm/torso split, the zones and
    the ref-pose self-check do not change from frame to frame)."""
    cache = {} if cache is None else cache
    parts, posed, rest = D["parts"], D["posed"], D["rest"]
    rest_bones, rest_chain, chain, B = D["rest_bones"], D["rest_chain"], D["chain"], D["bones"]
    out = {"frame_head": D["head"], "parts": {}, "sides": {}, "rest_cached": D.get("rest_cached", []),
           **D["facing_diag"]}
    labels = {}
    for n in parts:
        (Pp, Tp), (Pr, Tr) = posed[n], rest[n]
        if len(Pp) != len(Pr) or len(Tp) != len(Tr):
            raise RuntimeError(f"{n}: posed {len(Pp)} verts/{len(Tp)} tris vs ref pose {len(Pr)}/{len(Tr)}: the "
                               "render copies do not line up")
        key = ("labels", n, D["assets"][n], len(Pp), len(Tp))
        if key not in cache:
            cache[key] = E.label_rest(Pr, rest_bones[n][0], sorted({int(i) for t in Tp for i in t}))
        labels[n] = cache[key]
        # its ref pose vs the Body's: the shared joints' largest offset (0 = one pose, the rest check is valid)
        mis = max(math.dist(a, b) for k in rest_bones["Body"][0] for a, b in
                  zip(rest_bones["Body"][0][k], rest_bones[n][0][k]))
        out["parts"][n] = {"verts": len(Pp), "tris": len(Tp), "rest_vs_body_cm": round(mis, 2),
                           "upperarm_verts": {sd: sum(1 for x in labels[n].values() if x[0] == f"upperarm_{sd}")
                                              for sd in ("l", "r")}}
    # her forward on the ref pose, for the bust/front vs side zones (the same up x (left - right) as facing(),
    # flipped the same way as the posed one)
    rb0, rc0 = rest_bones["Body"][0], rest_chain["Body"]
    rest_fwd = norm(cross(norm(sub(rc0[3], rc0[0])), sub(rb0["clavicle_l"][0], rb0["clavicle_r"][0])))
    if out["facing_flipped_by_knees"]:
        rest_fwd = tuple(-x for x in rest_fwd)
    front = float(G.get("FRONT_DEG", 60.0))
    cy = Cyl(chain[0], chain[3], D["facing_f"], sub(B["clavicle_l"], B["clavicle_r"]))  # her left, a direction
    max_d, ax = float(G.get("MAX_D", 20.0)), float(G.get("AXILLA_CM", 7.0))
    P = posed["Body"][0]
    knobs = tuple(G.get(k) for k in ("ARM_R", "ARM_R_X", "ARM_T0", "AXILLA_CM", "FRONT_DEG", "MAX_D", "SLEEVES"))

    def rec_of(w, ua, la):
        tq, _, thq = cy(w[2])
        return {"clear_cm": round(w[0], 2), "arm_t": round(seg_t(P[w[1]], ua, la)[1], 2), "torso_part": w[3][0],
                "align": w[4], "torso_t_cm": round(tq, 1), "torso_deg": round(thq)}

    for sd in ("r", "l"):
        skey = ("side", sd, tuple((n, D["assets"][n], len(posed[n][0])) for n in parts), knobs)
        if skey not in cache:
            sh = rest_bones["Body"][1][sd]
            r_med = arm_radius(labels["Body"], sd)
            arm_r = float(G["ARM_R"]) if G.get("ARM_R") else (r_med * float(G.get("ARM_R_X", 1.3)) if r_med else None)
            arm, _ = arm_sets(labels["Body"], rest["Body"][0], sh, sd, float(G.get("ARM_T0", 0.3)), ax, arm_r)
            torso, flags, skipped, rest_sets, rzone, rq_of = {}, {}, [], [], {"front": [], "side": []}, {}
            sleeves = str(G.get("SLEEVES", "0")) == "1"
            for n in parts:
                torso[n] = arm_sets(labels[n], rest[n][0], rest_bones[n][1][sd], sd, 1.1, ax, arm_r,
                                    sleeves=sleeves and n != "Body")[1]
                rq = rq_of[n] = E.tris(rest[n][0], rest[n][1], torso[n], n, rest_chain[n] if n != "Body" else None)
                flags[n] = E.flags(rq, rc0, rest_fwd, front)
                if out["parts"][n]["rest_vs_body_cm"] <= 1.0:  # one ref pose for both: one combined check
                    rest_sets.append(rq)
                    rzone["front"].append(E.take(rq, flags[n], True))
                    rzone["side"].append(E.take(rq, flags[n], False))
                else:
                    skipped.append(n)
            # self-check: the same sets on the ref pose (arms out, clear of the torso) must read > 0, else the
            # arm/torso split is wrong and the posed number means nothing
            RP = rest["Body"][0]
            checks = [E.clear(E.cat(rest_sets), arm, RP, max_d, rest_chain["Body"])]
            rf, rs = E.cat(rzone["front"]), E.cat(rzone["side"])
            zchecks = [E.zclear(E.cat([rf, rs]), ["front"] * E.n(rf) + ["side"] * E.n(rs), {"front": rf, "side": rs},
                                arm, RP, max_d, rest_chain["Body"])]
            # a garment on a ref pose of its own (his outfit, Epic's default: rest_vs_body > 1 cm, no check before):
            # its own check, with the Body's arm moved onto that garment's upper-arm bone
            a0, b0 = rest_bones["Body"][0][f"upperarm_{sd}"]
            for n in skipped:
                a1, b1 = rest_bones[n][0][f"upperarm_{sd}"]
                RPm = [tuple(float(x) for x in p) for p in RP]
                for i in arm:
                    RPm[i] = rigid_map(RPm[i], a0, b0, a1, b1)
                checks.append(E.clear(rq_of[n], arm, RPm, max_d, rest_chain[n]))
                nf, ns = E.take(rq_of[n], flags[n], True), E.take(rq_of[n], flags[n], False)
                zchecks.append(E.zclear(E.cat([nf, ns]), ["front"] * E.n(nf) + ["side"] * E.n(ns),
                                        {"front": nf, "side": ns}, arm, RPm, max_d, rest_chain[n]))
            rw, rneg, _ = _min_check(checks)
            rz = {z: _min_check([zc[z] for zc in zchecks]) for z in ("front", "side")}
            cache[skey] = (arm, r_med, arm_r, torso, flags, skipped, (rw, rneg), rz)
        arm, r_med, arm_r, torso, flags, skipped, (rw, rneg), rz = cache[skey]
        pe = {n: E.tris(posed[n][0], posed[n][1], torso[n], n, chain if n != "Body" else None) for n in parts}
        entries = E.cat([pe[n] for n in parts])
        worst, neg, lt3 = E.clear(entries, arm, P, max_d, chain)
        pf = E.cat([E.take(pe[n], flags[n], True) for n in parts])
        ps = E.cat([E.take(pe[n], flags[n], False) for n in parts])
        zr = E.zclear(E.cat([pf, ps]), ["front"] * E.n(pf) + ["side"] * E.n(ps), {"front": pf, "side": ps},
                      arm, P, max_d, chain)
        ua, la = B[f"upperarm_{sd}"], B[f"lowerarm_{sd}"]
        rec = {"arm_verts": len(arm), "torso_tris": E.n(entries), "verts_lt0": neg, "verts_lt3": lt3,
               "arm_r_med": r_med and round(r_med, 2), "arm_r": arm_r and round(arm_r, 2),
               "rest_clear_cm": rw and round(rw[0], 2), "rest_verts_lt0": rneg,
               "rest_part": rw and rw[3][0], "rest_check_skips": [], "rest_check_mapped": skipped,
               "sleeves": str(G.get("SLEEVES", "0")) == "1"}
        if rw and rw[0] < 0:  # why the self-check failed: the arm point and the torso face, by their ref labels
            ln, lt, ld = labels["Body"][rw[1]]
            tn, tt, td = labels[rw[3][0]].get(rw[3][1], ("?", 0.0, 0.0))
            rec["rest_worst"] = {"arm": [ln, round(lt, 2), round(ld, 2)], "torso": [rw[3][0], tn, round(tt, 2),
                                 round(td, 2)], "align": rw[4], "dist": round(abs(rw[0]), 2)}
        rec["zones"] = {}
        for z, pz in (("front", pf), ("side", ps)):
            (w, zneg, zlt3), (zrw, zrneg, _) = zr[z], rz[z]
            r = {"tris": E.n(pz), "verts_lt0": zneg, "verts_lt3": zlt3, "rest_clear_cm": zrw and round(zrw[0], 2),
                 "rest_verts_lt0": zrneg}
            if w:
                r.update(rec_of(w, ua, la))
            rec["zones"][z] = r
        if worst:
            rec.update(rec_of(worst, ua, la))
        out["sides"][sd] = rec
    cl = [r["clear_cm"] for r in out["sides"].values() if "clear_cm" in r]
    out["upperarm_torso_clear_cm"] = min(cl) if cl else None
    # the orchestrator's split (round 7, ee99f626): >= 3 cm off the bust/front, >= 0.5 cm (no penetration) at the side
    for z, key in (("front", "upperarm_bust_clear_cm"), ("side", "upperarm_side_clear_cm")):
        zl = [r["zones"][z]["clear_cm"] for r in out["sides"].values() if "clear_cm" in r["zones"][z]]
        out[key] = min(zl) if zl else None
    out["front_deg"] = front
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

    def cleanup(dumps=False):
        if dumps:  # the fast path's box-local mesh files: only at the end of a run (`cleanup` stage)
            import glob as _gl
            import shutil as _sh
            for d in _gl.glob(DUMP_ROOT + "*"):
                _sh.rmtree(d, ignore_errors=True)
        n = 0
        for a in list(EAS.get_all_level_actors()):
            if a.get_actor_label().startswith(REST):
                EAS.destroy_actor(a)
                n += 1
        return n

    stage = G.get("STAGE")
    if stage == "cleanup":
        return {"removed": cleanup(dumps=True)}
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
        # each part is labelled on ITS OWN ref pose (v2b2: the Top labelled on the Body's ref bones read its sleeves
        # as torso, the arm inside its own sleeve at about -arm radius, and the self-check failed at -13.7)
        rest, rest_bones, rest_chain, rest_fresh = {}, {}, {}, set()
        # the ref pose and its labels depend only on the mesh asset: kept in the editor's interpreter between the
        # frames of ONE driver run (RUN, new per CLI call: an asset refit between runs is never read stale; box D ran
        # ~1 min a frame, much of it this). CACHE=0 rebuilds every frame
        cache = getattr(unreal, "_fmqa_r7_rest", None)
        if cache is None or cache.get("run") != G.get("RUN") or not G.get("RUN") or str(G.get("CACHE", "1")) == "0":
            cache = {"run": G.get("RUN")}
            setattr(unreal, "_fmqa_r7_rest", cache)
        keys = {n: (n, c.get_skeletal_mesh_asset().get_path_name(), len(posed[n][0]), len(posed[n][1]))
                for n, c in parts}
        cleanup()
        try:
            for n, c in parts:
                if keys[n] in cache:
                    rest[n], rest_bones[n], rest_chain[n] = cache[keys[n]][:3]
                    continue
                ra = EAS.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
                ra.set_actor_label(f"{REST}_{n}")
                rc = ra.get_editor_property("skeletal_mesh_component")
                rc.set_skeletal_mesh_asset(c.get_skeletal_mesh_asset())
                if math.dist(loc(rc, "neck_01"), loc(rc, "spine_05")) < 2.0:
                    raise RuntimeError("the temp ref-pose actor has no pose yet: run arms again")
                rest_fresh.add(n)
                rest[n] = mesh_of(rc)
                rest_bones[n] = segs_of(rc), {sd: loc(rc, f"upperarm_{sd}") for sd in ("l", "r")}
                rest_chain[n] = [loc(rc, b) for b in SPINE]
                cache[keys[n]] = (rest[n], rest_bones[n], rest_chain[n])
        finally:
            cleanup()
        D = {"parts": [n for n, _ in parts], "posed": posed, "rest": rest, "rest_bones": rest_bones,
             "rest_chain": rest_chain, "chain": [loc(body, b) for b in SPINE],
             "assets": {n: c.get_skeletal_mesh_asset().get_path_name() for n, c in parts},
             "bones": {b: loc(body, b) for b in ("clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r",
                                                  "lowerarm_l", "lowerarm_r")},
             "head": [round(x, 2) for x in head], "rest_cached": sorted(n for n in keys if n not in rest_fresh)}
        D["facing_f"], D["facing_diag"] = facing("clavicle_l", "clavicle_r")
        if G.get("ENGINE") == "fast":
            # the fast path (round 7, the orchestrator: ~1 min a frame on one core while the box idles): the meshes go
            # to a box-local dir and numpy computes in a process ON THE BOX (garment_fast.py in the box's tree, its
            # tools env); only the numbers come back. Presenter geometry never leaves the box; `cleanup` removes it
            import array as _ar
            import os as _os
            import subprocess as _sp
            dd = f"{DUMP_ROOT}{G.get('RUN') or 'norun'}"
            _os.makedirs(dd, exist_ok=True)

            def put(name, rows, code):
                with open(_os.path.join(dd, name), "wb") as fh:
                    _ar.array(code, [x for r in rows for x in r]).tofile(fh)

            meta = {k: D[k] for k in ("parts", "chain", "assets", "bones", "head", "facing_f", "facing_diag",
                                      "rest_bones", "rest_chain")}
            meta["counts"] = {n: [len(posed[n][0]), len(posed[n][1])] for n in D["parts"]}
            meta["rest_cached"] = D["rest_cached"]
            if not cache.get(("dumped", dd)):
                for n in D["parts"]:
                    put(f"rest_{n}.f64", rest[n][0], "d")
                    put(f"tris_{n}.i32", posed[n][1], "i")
                cache[("dumped", dd)] = True
            for n in D["parts"]:
                put(f"posed_{n}.f64", posed[n][0], "d")
            with open(_os.path.join(dd, "meta.json"), "w") as fh:
                json.dump(meta, fh)
            tree = G.get("TREE", "/srv/ue/r7tree")
            uv = G.get("UV") or next((x for x in (_os.path.expanduser("~/.local/bin/uv"), "/usr/local/bin/uv",
                                                  "/usr/bin/uv") if _os.path.exists(x)), "uv")
            cmd = [uv, "run", "--project", f"{tree}/tools", "python", f"{tree}/films/host-studio/reel/r7/garment_fast.py",
                   dd, json.dumps({k: v for k, v in G.items() if k not in ("STAGE",)})]
            r = _sp.run(cmd, capture_output=True, text=True, timeout=600)
            lines = [x for x in r.stdout.splitlines() if x.startswith("RESULT ")]
            if r.returncode != 0 or not lines:
                raise RuntimeError(f"garment_fast on the box failed ({r.returncode}): {r.stderr[-1500:]}")
            return json.loads(lines[-1][7:])
        return arms_compute(D, G, PyEngine(float(G.get("CELL", 2.0))), cache)

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
        score, why, poke, pwhy = waist_score(secs, float(G.get("FRONT_DEG", 90.0)))
        # per-vertex poke (surface_poke): her skin nearest a torso/hip/thigh bone (a hand on her lap is outside the
        # cloth by right), against the posed trousers' own triangles
        BP, BT = mesh_of(body)
        segs = {f"spine:{a}": (loc(body, a), loc(body, b)) for a, b in zip(SPINE, SPINE[1:])}
        for sd in ("l", "r"):
            segs[f"thigh_{sd}"] = (loc(body, f"thigh_{sd}"), loc(body, f"calf_{sd}"))
            for a, b in ((f"upperarm_{sd}", f"lowerarm_{sd}"), (f"lowerarm_{sd}", f"hand_{sd}"),
                         (f"hand_{sd}", f"middle_01_{sd}"), (f"middle_01_{sd}", f"middle_03_{sd}"),
                         (f"thumb_01_{sd}", f"thumb_03_{sd}")):
                segs[f"arm:{a}"] = (loc(body, a), loc(body, b))
        used = {i for t in BT for i in t}
        lo_t = float(G.get("POKE_CM", 10.0))
        near = [i for i in used if top_t - lo_t - 2.0 <= cy(BP[i])[0] <= top_t + 1.0]
        lab = label_rest(BP, segs, near)
        skin_v = [(i, BP[i]) for i in near if not lab[i][0].startswith("arm:")]
        TP, TT = mesh_of(trou)
        sp = surface_poke(TP, TT, skin_v, cy, [s and s["edge_t"] for s in secs], lo_t,
                          float(G.get("RIM_CM", 0.5)), float(G.get("POKE_ALIGN", 0.5)), float(G.get("CELL", 2.0)))
        front = [s for s in secs if s and abs(s["deg"]) <= 90]
        res = {"frame_head": [round(x, 2) for x in head], "waist_fit_cm": score, "worst": why,
               "waist_poke_cm": poke, "poke_where": pwhy, "waist_skin_poke_cm": sp["poke_cm"],
               "waist_skin_poke_front_cm": sp["poke_front_cm"], "skin_poke": sp, **fdiag,
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
    import time
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", required=True, help="workstation profile (FILM_UE_BOX); 'conf' = the conf dir's default")
    ap.add_argument("--label", default="Presenter")
    sub_ = ap.add_subparsers(dest="cmd", required=True)
    for name in ("arms", "waist"):
        m = sub_.add_parser(name)
        m.add_argument("--seq", required=True)
        m.add_argument("--frames", required=True, help="F, A-B or A-B:STEP, comma separated, at --frames-fps")
        m.add_argument("--seq-fps", type=float, default=24.0, help="the sequence's display rate (seq.scrub's frames)")
        m.add_argument("--frames-fps", type=float, default=None,
                       help="the clock --frames were taken on (arm_track: 30); default the sequence's own")
        m.add_argument("--out", required=True)
        m.add_argument("--set", action="append", default=[], help="KEY=VALUE knob (ARM_T0, AXILLA_CM, BAND_CM, ...)")
        if name == "arms":
            m.add_argument("--engine", choices=("editor", "fast"), default="editor",
                           help="editor: all in the editor's Python (~1 min/frame); fast: the editor writes the meshes "
                                "to a box-local dir and runs garment_fast.py ON THE BOX with numpy (only numbers return)")
            m.add_argument("--tree", default=None, help="the repo checkout ON THE BOX for --engine fast "
                                                         "(default /srv/ue/r7tree); its tools env needs numpy+scipy")
    sub_.add_parser("cleanup")
    a = ap.parse_args(argv)
    if a.box != "conf":
        os.environ["FILM_UE_BOX"] = a.box
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
    from filmtools.unreal import client
    g = {"LABEL": a.label, "RUN": f"{os.getpid()}-{os.urandom(4).hex()}"}
    if a.cmd == "cleanup":
        print(json.dumps(_exec(client, "cleanup", **g)))
        return 0
    for kv in a.set:
        k, _, v = kv.partition("=")
        g[k] = v
    if a.cmd == "arms" and a.engine == "fast":
        g["ENGINE"] = "fast"
        if a.tree:
            g["TREE"] = a.tree
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    per, last = {}, None
    src_fps = a.frames_fps or a.seq_fps
    plan = to_seq_frames(parse_frames(a.frames), src_fps, a.seq_fps)
    if src_fps != a.seq_fps:
        print(f"frames at {src_fps:g} fps -> sequence {a.seq_fps:g} fps by time: "
              + ", ".join(f"{sf}->{g}" for g, sf, _ in plan), flush=True)
    clock = {g: (sf, t) for g, sf, t in plan}
    for f, _, _ in plan:
        for ff in (f + 1, f):
            r = client.op("seq.scrub", path=a.seq, frame=ff)
            if not r.get("ok"):
                raise SystemExit(f"seq.scrub {ff}: {r}")
        t0 = time.time()
        res = _exec(client, a.cmd, **g)
        res["seconds"] = round(time.time() - t0, 2)
        if a.cmd == "arms" and not per:
            print("parts:", json.dumps(res["parts"]), flush=True)
        if last is not None and res["frame_head"] == last:
            print(f"WARN f{f}: head did not move since the last frame (pose not updated?)")
        last = res["frame_head"]
        res["clock"] = {"seq_frame": f, "seq_fps": a.seq_fps, "src_frame": clock[f][0], "src_fps": src_fps,
                        "t_s": clock[f][1]}
        per[f] = res
        if a.cmd == "arms":
            print(f"f{f}: bust/front {res['upperarm_bust_clear_cm']} (>= 3), side {res['upperarm_side_clear_cm']} (>= 0.5) | "
                  + " | ".join(f"{sd} {z}: {zr.get('clear_cm')} cm (arm_t {zr.get('arm_t')}, {zr.get('torso_part')} at t "
                               f"{zr.get('torso_t_cm')} cm, {zr.get('torso_deg')} deg; <0 {zr['verts_lt0']}, <3 "
                               f"{zr['verts_lt3']}; rest {zr.get('rest_clear_cm')}/{zr.get('rest_verts_lt0')}; "
                               f"{zr['tris']} tris)"
                               for sd, r in res["sides"].items() for z, zr in r["zones"].items()), flush=True)
            print(f"f{f}: clear {res['upperarm_torso_clear_cm']} (facing vs actor {res['facing_vs_actor_deg']} deg) | "
                  + " | ".join(
                f"{sd}: {r.get('clear_cm')} cm (arm_t {r.get('arm_t')}, {r.get('torso_part')} at t {r.get('torso_t_cm')}"
                f" cm, {r.get('torso_deg')} deg; <0 {r['verts_lt0']}, <3 {r['verts_lt3']} of {r['arm_verts']}; arm_r "
                f"{r.get('arm_r')}; rest {r.get('rest_clear_cm')}/{r.get('rest_verts_lt0')} {r.get('rest_part')}"
                f"{' mapped ' + ','.join(r['rest_check_mapped']) if r.get('rest_check_mapped') else ''}"
                f"{' WHY ' + json.dumps(r['rest_worst']) if r.get('rest_worst') else ''})"
                for sd, r in res["sides"].items()), flush=True)
        else:
            sp = res.get("skin_poke") or {}
            print(f"f{f}: waist_fit {res['waist_fit_cm']} cm ({res['worst']}), waist_poke {res['waist_poke_cm']} cm "
                  f"({res['poke_where']}); SKIN POKE {sp.get('poke_cm')} cm all round, {sp.get('poke_front_cm')} front "
                  f"(>0 {sp.get('verts_gt0')}, >0.1 {sp.get('verts_gt01')} of {sp.get('verts')}; {sp.get('where')}) ("
                  f"facing vs actor "
                  f"{res['facing_vs_actor_deg']} deg, knee flip {res['facing_flipped_by_knees']}); edge above waist "
                  f"{res['edge_above_natural_waist_cm']} cm, edge wave {res['edge_wave_front_cm']}; sectors "
                  "[deg, edge_t, tuck, gap_max, poke_max, top_over]: " + json.dumps(
                      [[s["deg"], s["edge_t"], s["tuck"], s["gap_max"], s["poke_max"], s["top_over_max"]]
                       for s in res["sectors"] if s]), flush=True)
    if a.cmd == "arms" and a.engine == "fast":
        _exec(client, "cleanup", **g)  # the box-local mesh files and any temp actors
    (out / f"{a.cmd}.json").write_text(json.dumps(per))
    keys = (["upperarm_bust_clear_cm", "upperarm_side_clear_cm", "upperarm_torso_clear_cm"] if a.cmd == "arms"
            else ["waist_fit_cm", "waist_poke_cm", "waist_skin_poke_cm", "waist_skin_poke_front_cm"])
    for key in keys:
        vals = {f: r[key] for f, r in per.items() if r.get(key) is not None}
        if vals:
            fw = (min if key.startswith("upperarm_") else max)(vals, key=vals.get)
            print(json.dumps({"measure": key, "worst_frame": fw, "worst": vals[fw], "frames": len(per),
                              "file": str(out / f"{a.cmd}.json")}))
    return 0


if __name__ == "__main__" and "_G" not in globals():
    import sys as _sys
    if len(_sys.argv) > 1:  # the driver CLI (an `unreal` stub may be importable off the box: never decide by that)
        raise SystemExit(main())
