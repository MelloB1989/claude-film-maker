"""hoodie: a black cotton-fleece hoodie thrown onto the right-hand end of the credenza (a Mr. Robot nod).

Run headless (on the Mac, through the fleet wrapper):
    blender -b --factory-startup -P films/host-studio/props/hoodie.py -- --out films/host-studio/props/out

How it is made
  1. A flat sewing pattern (cm, u across the garment, v up from the hem, seen from the front): body, two
     set-in sleeves with rib cuffs, rib hem, and a hood flipped up above the neckline. The front layer has
     the hood's face opening cut out of it and carries the pocket outline; the back layer is whole.
     Both layers are triangulated (constrained Delaunay) with the seams as constrained edges and share
     their vertices along the sewn outline (side seams, underarms, shoulders, sleeve tops, hood), so the
     garment is one closed double-layer envelope, open only at the hem, the cuffs and the face opening.
  2. It is laid out face down over the credenza's front-right corner, 14% smaller than its pattern: the
     shoulders a little out past the front edge, the hood beyond them, the body packed back toward the wall in
     soft waves, the sleeves folded across the back at the armholes, crossed.
  3. Blender's cloth solver (self-collision on, the credenza, wall and floor as colliders) drops it from a few
     cm; it grows back to full size as it settles, so it bunches on the top, the shoulders and the hood fall
     and hang down the front at the corner.
  4. Loop subdivision, a settle onto the collider surfaces, seam grooves, then a 3.5 mm solidify with
     rounded rims at the open edges; the kangaroo pocket is a second thickened layer on the front; metal
     eyelets; flat drawcords from a small rope simulation lying on the draped garment, with metal aglets.
  5. A flat patch on the front-facing side near the credenza-top height is found (and pressed flat) for
     the sticky note; its centre and normal go to out/hoodie_note.json.

Origin: the credenza top's right back corner, Blender (0, 0, 72 cm). The credenza itself is not exported.
"""

import argparse
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector, geometry
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

NAME = "hoodie"

# ---------------------------------------------------------------- the credenza (cm, Blender frame)
TOP_Z = 72.0
TOP_T = 2.5            # top slab thickness
TOP_X = 45.0           # front of the top (the top's outline is the credenza's outline)
OVER = 1.5             # the top overhangs the carcass by this at the front and the end
LEN = 190.0
ORIGIN = (0.0, 0.0, TOP_Z)   # top's right back corner

# ---------------------------------------------------------------- garment pattern (cm)
TH = math.radians(25.0)                       # sleeve angle below horizontal in the flat pattern
SR = np.array([22.5, 66.5])                   # shoulder point (right half; u > 0)
NR = np.array([8.5, 69.0])                    # neck side point
HEM_V = 6.5                                   # rib hem height
CUFF_AT = 55.0                                # cuff seam, along the sleeve from the shoulder point
SLEEVE_LEN = 62.0
EYELET = np.array([9.9, 75.0])                # drawcord eyelets on the hood's front band (+-u)

GROOVES = {"hem_seam", "armhole", "cuff_seam", "neck_front", "neck_back", "hood_cf", "hood_cb", "channel"}

# ---------------------------------------------------------------- the drape
# Thrown face down onto the front-right corner: the shoulders a little out past the front edge, the hood beyond
# them (both fall and hang down the front, the hood at the corner); the body packed back toward the wall in soft
# waves; the sleeves folded across the back at the armholes, crossed. It is laid out COMPRESS smaller than its
# pattern, dropped from a few cm, and grows back to full size as it settles, so it bunches and piles.
# Plane coordinates (a, b) are the pattern's (u, v); heights are above the top (+ = away from the credenza).
ALPHA = math.radians(10.0)            # hood direction, from +X toward +Y
NECK = np.array([50.0, -19.0])        # centre of the shoulder line (pattern v = SR[1])
Z0 = TOP_Z + 5.6                      # dropped from this height
E_GAP = 0.35                          # half the gap between the layers at the start
B1 = 54.0                             # below this pattern height the body is packed along its length
SLACK = 0.6                           # ... into this fraction of its length (lowered if it would stretch)
WAVE_A, WAVE_L = 4.2, 14.0            # ... in waves this high and this long
B2, CA, WAVE2_A, WAVE2_L = 31.0, 0.74, 2.0, 14.0   # below B2, across too: packed to CA of its width, in waves
FOLD_A_AT, FOLD_A_R = 2.0, 1.2        # sleeves: folded across the back just past the armhole, over rolls this
FOLD_B_AT, FOLD_B_R = 2.0, 2.0        # ... radius (the second lies over the first)
COMPRESS = 0.86                       # the whole garment starts this much smaller than its pattern
USE_PINS = True
FRICTION = 80.0


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog=NAME)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--h", type=float, default=1.42, help="cloth-sim edge length, cm")
    ap.add_argument("--frames", type=int, default=420)
    ap.add_argument("--quality", type=int, default=8)
    ap.add_argument("--reuse-sim", action="store_true", help="load <out>/hoodie_sim.npz instead of simulating")
    ap.add_argument("--sim-only", action="store_true")
    ap.add_argument("--grey", action="store_true", help="debug: light grey fleece in the previews")
    ap.add_argument("--snapshots", default="", help="comma-separated frames to save as debug .npy")
    ap.add_argument("--no-pins", action="store_true", help="debug: no pinned shoulders")
    return ap.parse_args(argv)


# ================================================================ 2D helpers

def catmull(ctrl, per=10):
    pts = S.catmull_rom([(p[0], p[1], 0.0) for p in ctrl], per_seg=per)
    return [np.array((p[0], p[1])) for p in pts]


def resample(pts, h):
    """Polyline -> points about h apart; both ends kept."""
    pts = [np.asarray(p, float) for p in pts]
    seg = [np.linalg.norm(pts[i + 1] - pts[i]) for i in range(len(pts) - 1)]
    total = sum(seg)
    n = max(1, int(round(total / h)))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    out = []
    for k in range(n + 1):
        d = total * k / n
        i = int(min(np.searchsorted(cum, d, side="right") - 1, len(seg) - 1))
        t = (d - cum[i]) / seg[i] if seg[i] > 0 else 0.0
        out.append(pts[i] + (pts[i + 1] - pts[i]) * t)
    out[0], out[-1] = pts[0], pts[-1]
    return out


def inside(poly, P):
    poly = np.asarray(poly, float)
    P = np.asarray(P, float)
    x, y = P[:, 0][:, None], P[:, 1][:, None]
    x1, y1 = poly[:, 0][None], poly[:, 1][None]
    x2, y2 = np.roll(poly[:, 0], -1)[None], np.roll(poly[:, 1], -1)[None]
    cond = (y1 > y) != (y2 > y)
    xint = x1 + (y - y1) * (x2 - x1) / np.where(np.abs(y2 - y1) < 1e-12, 1e-12, y2 - y1)
    return ((cond & (x < xint)).sum(1) % 2) == 1


def seg_dist(P, A, B):
    """Min distance from each point in P to the segments A[i]-B[i]."""
    P = np.asarray(P, float)
    A = np.asarray(A, float)
    B = np.asarray(B, float)
    AB = B - A
    L2 = (AB ** 2).sum(1) + 1e-12
    out = np.empty(len(P))
    for s in range(0, len(P), 400):
        Q = P[s:s + 400]
        AP = Q[:, None, :] - A[None]
        t = np.clip((AP * AB[None]).sum(2) / L2[None], 0.0, 1.0)
        D = AP - t[..., None] * AB[None]
        out[s:s + 400] = np.sqrt((D ** 2).sum(2)).min(1)
    return out


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def mirror(pts):
    return [np.array((-p[0], p[1])) for p in pts]


# ================================================================ the pattern

def sleeve_pt(along, across):
    a = np.array([math.cos(TH), -math.sin(TH)])
    n = np.array([-math.sin(TH), -math.cos(TH)])
    return SR + along * a + across * n


def sleeve_along(p, side):
    """Distance along the sleeve axis from the shoulder point, for the sleeve on `side` (+1/-1)."""
    a = np.array([math.cos(TH), -math.sin(TH)])
    q = np.array([p[0] * side, p[1]])
    return float((q - SR) @ a)


UR = sleeve_pt(14.5, 18.1)   # underarm


def pattern_pieces():
    """Right-half outline segments, CCW from the hem centre: (kind, name, control points, smooth)."""
    sl = sleeve_pt
    return [
        ("open", "hem", [(0, 0), (25.5, 0)], False),
        ("join", "side", [(25.5, 0), (26.8, HEM_V)], False),
        ("join", "side", [(26.8, HEM_V), (27.5, 22.0), UR], True),
        ("join", "under", [UR, sl(25, 16.2), sl(40, 13.6), sl(CUFF_AT - 0.2, 11.0)], True),
        ("join", "under", [sl(CUFF_AT - 0.2, 11.0), sl(CUFF_AT, 9.4)], False),
        ("join", "under", [sl(CUFF_AT, 9.4), sl(SLEEVE_LEN, 9.0)], False),
        ("open", "cuff", [sl(SLEEVE_LEN, 9.0), sl(SLEEVE_LEN + 0.3, 4.5), sl(SLEEVE_LEN, 0)], True),
        ("join", "top", [sl(SLEEVE_LEN, 0), sl(CUFF_AT, 0)], False),
        ("join", "top", [sl(CUFF_AT, 0), SR], False),
        ("join", "shoulder", [SR, NR], False),
        ("join", "hood", [NR, (12.3, 74), (14.3, 81), (15.0, 89), (14.2, 96.5), (11.5, 102), (6.5, 105.3),
                          (0, 106.3)], True),
    ]


def build_outline(h):
    right = pattern_pieces()
    segs = []
    for kind, name, ctrl, smooth in right:
        pts = catmull(ctrl) if smooth else [np.asarray(c, float) for c in ctrl]
        segs.append((kind, name, resample(pts, h)))
    for kind, name, pts in reversed(list(segs)):
        segs.append((kind, name, list(reversed(mirror(pts)))))
    verts, kinds, names = [], [], []
    for kind, name, pts in segs:
        for p in pts[:-1]:
            verts.append(np.asarray(p, float))
            kinds.append(kind)       # kind of the edge from this vertex to the next
            names.append(name)
    return np.array(verts), kinds, names


def hole_curve():
    """Face opening of the hood (front layer only), CCW, as dense points + the key indices."""
    right = [(0, 62.5), (3.0, 64.0), (5.5, 67.5), (7.5, 72.0), (9.2, 78.0), (10.0, 84.0), (9.5, 90.0),
             (7.8, 95.0), (4.5, 98.0), (0, 99.0)]
    left = [(-u, v) for (u, v) in reversed(right[1:-1])]
    ctrl = right + left + [right[0]]
    per = 10
    dense = catmull(ctrl, per)
    return ctrl, dense, per


def pocket_polygon():
    open_r = [(17.0, 17.5), (15.6, 22.6), (13.7, 26.4), (11.5, 29.0)]
    opening = catmull(open_r)
    right = [np.array((17.0, HEM_V))] + opening
    left = list(reversed(mirror(right)))
    return right, left, opening


def constraints(h):
    """[(layers, kind, points)] with layers in {"F", "B", "FB"}."""
    out = []
    # hem seam (both), through the pocket's bottom corners
    for a, b in (((-26.8, HEM_V), (-17.0, HEM_V)), ((-17.0, HEM_V), (17.0, HEM_V)), ((17.0, HEM_V), (26.8, HEM_V))):
        out.append(("FB", "hem_seam", resample([a, b], h)))
    arm = resample(catmull([SR, (24.2, 58.0), (25.8, 51.0), UR]), h)
    out.append(("FB", "armhole", arm))
    out.append(("FB", "armhole", mirror(arm)))
    cs = resample([sleeve_pt(CUFF_AT, 0), sleeve_pt(CUFF_AT, 9.4)], h)
    out.append(("FB", "cuff_seam", cs))
    out.append(("FB", "cuff_seam", mirror(cs)))
    # front: pocket outline
    pr, pl, _ = pocket_polygon()
    side = resample([pr[0], pr[1]], h)
    out.append(("F", "pocket", side))
    out.append(("F", "pocket", mirror(side)))
    op = resample(pr[1:], h)
    out.append(("F", "pocket_open", op))
    out.append(("F", "pocket_open", mirror(op)))
    out.append(("F", "pocket", resample([pr[-1], mirror([pr[-1]])[0]], h)))
    # front: face opening (closed), split at its key points
    ctrl, dense, per = hole_curve()
    keys = [0, 1, 9, len(ctrl) - 2, len(ctrl) - 1]          # V bottom, (3,64), top, (-3,64), V bottom
    for i0, i1 in zip(keys, keys[1:]):
        out.append(("F", "hole", resample(dense[i0 * per:i1 * per + 1], h)))
    neck = resample(catmull([NR, (6.2, 66.3), ctrl[1]]), h)
    out.append(("F", "neck_front", neck))
    out.append(("F", "neck_front", mirror(neck)))
    out.append(("F", "hood_cf", resample([ctrl[9], (0, 106.3)], h)))
    # drawcord channel stitch: the face opening offset 2.2 cm into the band, over the top
    i0, i1 = 4 * per, (len(ctrl) - 5) * per
    seg = np.array(dense[i0:i1 + 1])
    tan = np.gradient(seg, axis=0)
    tan /= np.linalg.norm(tan, axis=1)[:, None]
    nrm = np.stack([tan[:, 1], -tan[:, 0]], 1)
    out.append(("F", "channel", resample(list(seg + 2.2 * nrm), h)))
    # back: neckline and hood centre-back seam
    out.append(("B", "neck_back", resample(catmull([(-8.5, 69.0), (-4.0, 67.8), (0, 67.5)]), h)))
    out.append(("B", "neck_back", resample(catmull([(0, 67.5), (4.0, 67.8), (8.5, 69.0)]), h)))
    out.append(("B", "hood_cb", resample([(0, 67.5), (0, 106.3)], h)))
    return out


def triangulate(outline, cons, h, hole=None, extra=()):
    """Constrained Delaunay of the outline + constraint lines + a hex lattice; returns verts, tris, edge kinds."""
    V, key = [], {}

    def vid(p):
        k = (round(float(p[0]), 4), round(float(p[1]), 4))
        if k not in key:
            key[k] = len(V)
            V.append((float(p[0]), float(p[1])))
        return key[k]

    B = len(outline)
    ids = [vid(p) for p in outline]
    assert ids == list(range(B)), "outline has duplicate points"
    E = [(i, (i + 1) % B) for i in range(B)]
    ekind = {}
    segA, segB = [outline], [np.roll(outline, -1, axis=0)]
    for kind, pts in cons:
        cid = [vid(p) for p in pts]
        for a, b in zip(cid, cid[1:]):
            if a != b:
                E.append((a, b))
                ekind[(min(a, b), max(a, b))] = kind
        segA.append(np.array(pts[:-1]))
        segB.append(np.array(pts[1:]))
    segA, segB = np.concatenate(segA), np.concatenate(segB)
    # hex lattice
    lo, hi = outline.min(0), outline.max(0)
    pts = []
    dy = h * math.sqrt(3) / 2
    for j, y in enumerate(np.arange(lo[1] + dy / 2, hi[1], dy)):
        off = (h / 2) if j % 2 else 0.0
        for x in np.arange(lo[0] + off, hi[0], h):
            pts.append((x, y))
    pts = np.array(pts)
    keep = inside(outline, pts)
    if hole is not None:
        keep &= ~inside(hole, pts)
    pts = pts[keep]
    pts = pts[seg_dist(pts, segA, segB) > 0.6 * h]
    for p in list(pts) + list(extra):
        V.append((float(p[0]), float(p[1])))
    res = geometry.delaunay_2d_cdt([Vector(p) for p in V], E, [], 0, 1e-5, True)
    vout, fout, orig_v = res[0], res[2], res[3]
    remap = []
    for i, ov in enumerate(orig_v):
        if ov:
            remap.append(ov[0])
        else:
            print(f"[{NAME}] warning: CDT added vertex at {tuple(vout[i])}")
            remap.append(len(V))
            V.append((vout[i][0], vout[i][1]))
    V = np.array(V)
    tris = np.array([[remap[i] for i in f] for f in fout if len(f) == 3])
    cen = V[tris].mean(1)
    ok = inside(outline, cen)
    if hole is not None:
        ok &= ~inside(hole, cen)
    tris = tris[ok]
    # CCW in (u, v)
    a, b, c = V[tris[:, 0]], V[tris[:, 1]], V[tris[:, 2]]
    cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    tris[cross < 0] = tris[cross < 0][:, ::-1]
    return V, tris, ekind


def outline_chords(tris, B):
    """Interior edges between two outline vertices (would join the layers): their midpoints, to split them."""
    fix = []
    for t in tris:
        for k in range(3):
            a, b = int(t[k]), int(t[(k + 1) % 3])
            if a < B and b < B and (a - b) % B not in (1, B - 1):
                fix.append((a, b, int(t[(k + 2) % 3])))
    return fix


def build_layer(outline, cons, h, hole=None):
    extra = []
    for _ in range(6):
        V, tris, ek = triangulate(outline, cons, h, hole, extra)
        fix = outline_chords(tris, len(outline))
        if not fix:
            return V, tris, ek
        for a, b, c in fix:
            m = (V[a] + V[b]) / 2
            extra.append(m + 0.35 * (V[c] - m))
    raise RuntimeError("could not remove outline chords")


def build_pattern(h):
    outline, kinds, names = build_outline(h)
    B = len(outline)
    cons = constraints(h)
    ctrl, dense, per = hole_curve()
    hole = np.array(dense[:-1])
    fcons = [(k, p) for (l, k, p) in cons if "F" in l]
    bcons = [(k, p) for (l, k, p) in cons if "B" in l]
    Vf, Tf, Ef = build_layer(outline, fcons, h, hole)
    Vb, Tb, Eb = build_layer(outline, bcons, h)
    shared = np.array([kinds[i] == "join" or kinds[i - 1] == "join" for i in range(B)])
    return dict(outline=outline, kinds=kinds, names=names, B=B, shared=shared, hole=hole,
                Vf=Vf, Tf=Tf, Ef=Ef, Vb=Vb, Tb=Tb, Eb=Eb)


# ================================================================ the double-layer garment mesh

def region_of(c, layer, pocket_poly):
    """0 fleece, 1 rib (hem / cuffs), 2 fleece under the pocket (front)."""
    if c[1] < HEM_V:
        return 1
    for side in (1, -1):
        if c[0] * side > 25 and sleeve_along(c, side) > CUFF_AT:
            return 1
    if layer == 0 and inside(pocket_poly, [c])[0]:
        return 2
    return 0


def assemble(pat):
    B, shared = pat["B"], pat["shared"]
    Vf, Tf, Vb, Tb = pat["Vf"], pat["Tf"], pat["Vb"], pat["Tb"]
    nf = len(Vf)
    gid_b = np.empty(len(Vb), int)
    uv = list(Vf)
    layer = [2 if (i < B and shared[i]) else 0 for i in range(nf)]
    for i in range(len(Vb)):
        if i < B and shared[i]:
            gid_b[i] = i
        else:
            gid_b[i] = len(uv)
            uv.append(Vb[i])
            layer.append(1)
    uv = np.array(uv)
    layer = np.array(layer)
    faces = [tuple(int(x) for x in t) for t in Tf] + [tuple(int(gid_b[x]) for x in t[::-1]) for t in Tb]
    flayer = [0] * len(Tf) + [1] * len(Tb)
    pr, pl, _ = pocket_polygon()
    pocket_poly = np.array(pr + pl)
    fregion = [region_of(uv[list(f)].mean(0), fl, pocket_poly) for f, fl in zip(faces, flayer)]
    # sewn outline edges (shared by the layers), seams to groove
    joined = set()
    for i in range(B):
        if pat["kinds"][i] == "join":
            a, b = i, (i + 1) % B
            joined.add((min(a, b), max(a, b)))
    seams = {}
    for (a, b), kind in pat["Ef"].items():
        if kind in GROOVES:
            seams[(min(a, b), max(a, b), 0)] = kind
    for (a, b), kind in pat["Eb"].items():
        if kind in GROOVES:
            ga, gb = int(gid_b[a]), int(gid_b[b])
            seams[(min(ga, gb), max(ga, gb), 1)] = kind
    # open outline edges (hem, cuffs) and the face opening are the garment's free edges
    # distance to the sewn outline, for the starting gap between the layers
    ol = pat["outline"]
    jA = np.array([ol[i] for i in range(B) if pat["kinds"][i] == "join"])
    jB = np.array([ol[(i + 1) % B] for i in range(B) if pat["kinds"][i] == "join"])
    djoin = seg_dist(uv, jA, jB)
    return dict(uv=uv, layer=layer, faces=np.array(faces), flayer=np.array(flayer), fregion=np.array(fregion),
                joined=joined, seams=seams, djoin=djoin, nf=nf)


# ================================================================ starting pose over the credenza's corner

def sleeve_frame(p, side):
    """(along, across) of pattern points p in the sleeve on `side`'s frame."""
    a = np.array([math.cos(TH), -math.sin(TH)])
    n = np.array([-math.sin(TH), -math.cos(TH)])
    q = np.stack([p[:, 0] * side, p[:, 1]], 1) - SR
    return q @ a, q @ n


def fold(P, hgt, region, hinge, d_from, d_to, r):
    """Fold the part of `region` past a line through `hinge` (plane coords) up and over: a strip running along
    d_from comes back along d_to, over a roll of radius r resting on the cloth at the hinge."""
    line = d_from + d_to
    line /= np.linalg.norm(line)
    nrm = np.array([line[1], -line[0]])
    if d_from @ nrm < 0:
        nrm = -nrm
    s = (P - hinge) @ nrm
    sel = region & (s > 0)
    near = region & (np.abs(s) < 1.5)
    hb = float(np.median(hgt[near])) if near.any() else 0.0
    P, hgt = P.copy(), hgt.copy()
    for i in np.where(sel)[0]:
        si, h = s[i], hgt[i] - hb
        base = P[i] - si * nrm
        if si < math.pi * r:
            th = si / r
            P[i] = base + (r - h) * math.sin(th) * nrm
            hgt[i] = hb + r - (r - h) * math.cos(th)
        else:
            P[i] = base - (si - math.pi * r) * nrm
            hgt[i] = hb + 2 * r - h
    return P, hgt, sel


def fold_sleeve(uv, hgt):
    """The sleeves crossed on the back, as when a hoodie is folded: each folded at the armhole straight across
    the back, the end-side one (u > 0) first, the other over it."""
    sel = np.zeros(len(uv), bool)
    P = uv
    for side, at, r in ((1, FOLD_A_AT, FOLD_A_R), (-1, FOLD_B_AT, FOLD_B_R)):
        along, across = sleeve_frame(uv, side)
        sleeve = (uv[:, 0] * side > 15.0) & (across < 19.5) & (along > -3.0)
        d = np.array([side * math.cos(TH), -math.sin(TH)])
        sr, ur = np.array([side * SR[0], SR[1]]), np.array([side * UR[0], UR[1]])
        chord = (ur - sr) / np.linalg.norm(ur - sr)
        d1 = 2 * (d @ chord) * chord - d                     # the sleeve's way after a fold along the chord
        hinge = 0.5 * (sr + ur) + at * d
        # the hinge in today's plane coords (the first fold does not move the second sleeve)
        P, hgt, s1 = fold(P, hgt, sleeve, hinge, d, d1, r)
        sel |= s1
    return P, hgt, sel


def top_inside(xy):
    """Distance inside the top's outline (negative outside)."""
    return np.minimum(np.minimum(TOP_X - xy[:, 0], -xy[:, 1]), xy[:, 0])


def lay_out(P, hgt, slack):
    """Plane coords -> 3D above the top: the hood and shoulders straight out over the front edge, the body behind
    them packed in waves (along it from B1 down, across it from B2 down)."""
    b0 = SR[1]
    bb = np.linspace(-5.0, b0, 800)
    c = np.where(bb > B1, 1.0, slack + (1 - slack) * smoothstep((bb - (B1 - 6.0)) / 6.0))
    # sigma(b): distance along the spine from the shoulder line into the body (negative up into the hood)
    sig = np.concatenate([[0.0], np.cumsum(0.5 * (c[1:] + c[:-1]) * np.diff(bb))])
    sig = sig[-1] - sig
    H = np.array([math.cos(ALPHA), math.sin(ALPHA)])
    U = np.array([-H[1], H[0]])                                       # face down: the pattern's +u is to +Y
    a = P[:, 0] * COMPRESS
    b = b0 + (P[:, 1] - b0) * COMPRESS
    sg = np.where(b < b0, np.interp(b, bb, sig), b0 - b)
    ramp = smoothstep((B1 - b) / 8.0)
    ramp2 = smoothstep((B2 - b) / 10.0)                               # across: below the sleeves only
    a = a * (1.0 - (1.0 - CA) * ramp2)
    xy = NECK - sg[:, None] * H + a[:, None] * U
    z = Z0 + ramp * WAVE_A * np.sin(2 * math.pi * sg / WAVE_L) + ramp2 * WAVE2_A * np.sin(2 * math.pi * a / WAVE2_L)
    # waves fade out near the edges, so the cloth turns over them cleanly
    fade = smoothstep((top_inside(xy) - 2.0) / 12.0)
    return np.column_stack([xy, Z0 + (z - Z0) * fade + hgt])


def edge_stretch(X, uv, faces, sel=None):
    E = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    L = np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
    L0 = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)
    return L / np.maximum(L0, 1e-9)


def start_pose(g):
    """Mid-surface laid out and folded, then each layer moved off it along its own normal (outward)."""
    P, hgt, folded = fold_sleeve(g["uv"].copy(), np.zeros(len(g["uv"])))
    slack = SLACK
    for _ in range(14):
        Xm = lay_out(P, hgt, slack)
        r = edge_stretch(Xm, g["uv"], g["faces"])
        # (the folded sleeve's rolls on the waves stretch a little); the hem must stay off the wall
        if np.percentile(r, 99.5) <= 1.03 and Xm[:, 0].min() > 2.0:
            break
        slack *= 0.94
    w = smoothstep(g["djoin"] / 2.5)
    X = Xm + vertex_normals(Xm, g["faces"]) * (E_GAP * w)[:, None]
    r2 = edge_stretch(X, g["uv"], g["faces"])
    print(f"[{NAME}] start pose: slack {slack:.2f}, mid-surface stretch max {r.max():.3f}, "
          f"with the layer gap {r2.max():.3f} (99.9% {np.percentile(r2, 99.9):.3f})")
    g["folded"] = folded
    return X


# ================================================================ environment (cm): the credenza, wall, floor

def rbox_sdf(P, lo, hi, r):
    c = (np.array(lo) + np.array(hi)) / 2
    half = (np.array(hi) - np.array(lo)) / 2 - r
    q = np.abs(P - c) - half
    return np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(1), 0) - r


def env_sdf(P):
    P = np.atleast_2d(P)
    top = rbox_sdf(P, (0, -LEN, TOP_Z - TOP_T), (TOP_X, 0, TOP_Z), 0.2)
    body = rbox_sdf(P, (0, -LEN + OVER, 0), (TOP_X - OVER, -OVER, TOP_Z - TOP_T + 0.01), 0.2)
    wall = P[:, 0] + 0.0
    floor = P[:, 2] + 0.0
    return np.minimum(np.minimum(top, body), np.minimum(wall, floor))


def env_grad(P, eps=0.01):
    g = np.zeros_like(P)
    for k in range(3):
        d = np.zeros(3)
        d[k] = eps
        g[:, k] = (env_sdf(P + d) - env_sdf(P - d)) / (2 * eps)
    n = np.linalg.norm(g, axis=1)[:, None]
    return g / np.maximum(n, 1e-9)


# ================================================================ cloth simulation

def add_collider(name, lo, hi, friction, bevel=0.003):
    ob = S.box(name, [x * 0.01 for x in lo], [x * 0.01 for x in hi], S.material("_collider", (0.5, 0.5, 0.5), 0.5))
    if bevel:
        S.bevel(ob, bevel, 2, 30)
    ob.modifiers.new("Collision", "COLLISION")
    col = ob.collision
    col.cloth_friction = friction
    col.thickness_outer = 0.001
    col.damping = 0.6
    return ob


def pin_weights(g, X0):
    """Friction, standing in: the front layer of the chest, lying on the credenza top under
    everything else, stays where it starts (in the sim a heavy hoodie this far over the edge slides off)."""
    v = g["uv"][:, 1]
    on_top = (top_inside(X0[:, :2]) > 7.0) & (X0[:, 2] > TOP_Z)
    trough = X0[:, 2] < TOP_Z + 1.3                        # where the packed body's waves touch down
    return ((g["layer"] == 0) & on_top & trough & ~g["folded"] & (v > 8.0) & (v < 50.0)).astype(float)


def simulate(X0, faces, args, pins=None):
    sc = bpy.context.scene
    me = bpy.data.meshes.new("hoodie_sim")
    me.from_pydata((X0 * 0.01).tolist(), [], faces.tolist())
    me.update()
    ob = bpy.data.objects.new("hoodie_sim", me)
    sc.collection.objects.link(ob)
    cols = [
        add_collider("_c_top", (0, -LEN, TOP_Z - TOP_T), (TOP_X, 0, TOP_Z), FRICTION),
        add_collider("_c_body", (0, -LEN + OVER, 0), (TOP_X - OVER, -OVER, TOP_Z - TOP_T), FRICTION),
        add_collider("_c_wall", (-20, -LEN, 0), (0, 60, 200), 20, bevel=0),
        add_collider("_c_floor", (-20, -LEN, -10), (200, 150, 0), 40, bevel=0),
    ]
    if pins is not None:
        vg = ob.vertex_groups.new(name="pin")
        for i, w in enumerate(pins):
            if w > 1e-3:
                vg.add([i], float(w), "REPLACE")
    mod = ob.modifiers.new("Cloth", "CLOTH")
    st, cs = mod.settings, mod.collision_settings
    if pins is not None:
        st.vertex_group_mass = "pin"
        st.pin_stiffness = 2.0
    # the garment was laid out COMPRESS smaller than its pattern: it grows back as it settles, into folds
    st.shrink_min = -(1.0 / COMPRESS - 1.0)
    st.quality = args.quality
    st.mass = 0.5
    st.air_damping = 1.2
    st.bending_model = "ANGULAR"
    st.tension_stiffness = 45.0
    st.compression_stiffness = 12.0
    st.shear_stiffness = 6.0
    st.bending_stiffness = 0.3
    st.tension_damping = 6.0
    st.compression_damping = 6.0
    st.shear_damping = 6.0
    st.bending_damping = 0.6
    cs.use_collision = True
    cs.collision_quality = 4
    cs.distance_min = 0.0045
    cs.use_self_collision = True
    cs.self_distance_min = 0.004
    cs.self_friction = 25.0
    cs.self_impulse_clamp = 0.0
    sc.frame_start = 1
    sc.frame_end = args.frames
    mod.point_cache.frame_start = 1
    mod.point_cache.frame_end = args.frames
    snaps = {int(x) for x in args.snapshots.split(",") if x.strip()}
    t0 = time.time()
    for f in range(1, args.frames + 1):
        sc.frame_set(f)
        if f % 10 == 0 or f in snaps:
            ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
            co = np.array([v.co[:] for v in ev.data.vertices]) * 100.0
            print(f"[{NAME}] frame {f}/{args.frames}  {time.time() - t0:.0f}s  zmin {co[:, 2].min():.1f}"
                  f"  envmin {env_sdf(co).min():.2f}", flush=True)
            if f in snaps:
                np.save(os.path.join(args.out, f"hoodie_snap_{f}.npy"), co)
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    X = np.array([v.co[:] for v in ev.data.vertices]) * 100.0
    bpy.data.objects.remove(ob, do_unlink=True)
    for c in cols:
        bpy.data.objects.remove(c, do_unlink=True)
    return X


# ================================================================ mesh processing (cm)

def edge_key(a, b, fl, joined):
    k = (min(a, b), max(a, b))
    return k if k in joined else (k[0], k[1], fl)


def loop_subdivide(m):
    """One Loop subdivision of the garment, carrying pattern uv, layer, region, seams and sewn edges."""
    X, F, fl, joined, seams = m["X"], m["faces"], m["flayer"], m["joined"], m["seams"]
    nv = len(X)
    emap, edges, opp = {}, [], []
    fe = np.zeros((len(F), 3), int)
    for fi, f in enumerate(F):
        for k in range(3):
            a, b, c = int(f[k]), int(f[(k + 1) % 3]), int(f[(k + 2) % 3])
            key = edge_key(a, b, int(fl[fi]), joined)
            if key not in emap:
                emap[key] = len(edges)
                edges.append((a, b, key))
                opp.append([])
            ei = emap[key]
            opp[ei].append(c)
            fe[fi, k] = ei
    nbr = [set() for _ in range(nv)]
    bnbr = [[] for _ in range(nv)]
    for (a, b, key), o in zip(edges, opp):
        nbr[a].add(b)
        nbr[b].add(a)
        if len(o) == 1:
            bnbr[a].append(b)
            bnbr[b].append(a)
    newX = np.empty((nv + len(edges), 3))
    for v in range(nv):
        if bnbr[v]:
            if len(bnbr[v]) == 2:
                newX[v] = 0.75 * X[v] + 0.125 * (X[bnbr[v][0]] + X[bnbr[v][1]])
            else:
                newX[v] = X[v]
        else:
            n = len(nbr[v])
            beta = 3.0 / 16 if n == 3 else 3.0 / (8 * n)
            newX[v] = (1 - n * beta) * X[v] + beta * X[list(nbr[v])].sum(0)
    uv = np.concatenate([m["uv"], np.zeros((len(edges), 2))])
    layer = np.concatenate([m["layer"], np.zeros(len(edges), int)])
    new_joined, new_seams = set(), {}
    for ei, ((a, b, key), o) in enumerate(zip(edges, opp)):
        vi = nv + ei
        if len(o) == 2:
            newX[vi] = 0.375 * (X[a] + X[b]) + 0.125 * (X[o[0]] + X[o[1]])
        else:
            newX[vi] = 0.5 * (X[a] + X[b])
        uv[vi] = 0.5 * (m["uv"][a] + m["uv"][b])
        if len(key) == 2:
            layer[vi] = 2
            new_joined.add((min(a, vi), max(a, vi)))
            new_joined.add((min(b, vi), max(b, vi)))
        else:
            layer[vi] = key[2]
            if key in seams:
                for x in (a, b):
                    new_seams[(min(x, vi), max(x, vi), key[2])] = seams[key]
    nF, nfl, nreg = [], [], []
    for fi, f in enumerate(F):
        a, b, c = (int(x) for x in f)
        mab, mbc, mca = nv + fe[fi, 0], nv + fe[fi, 1], nv + fe[fi, 2]
        for t in ((a, mab, mca), (mab, b, mbc), (mca, mbc, c), (mab, mbc, mca)):
            nF.append(t)
            nfl.append(fl[fi])
            nreg.append(m["fregion"][fi])
    return dict(m, X=newX, faces=np.array(nF), flayer=np.array(nfl), fregion=np.array(nreg), uv=uv,
                layer=layer, joined=new_joined, seams=new_seams)


def vertex_normals(X, F):
    a, b, c = X[F[:, 0]], X[F[:, 1]], X[F[:, 2]]
    fn = np.cross(b - a, c - a)
    vn = np.zeros_like(X)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1)[:, None], 1e-12)


def smooth_normals(X, F, iters=4):
    """Vertex normals averaged over the neighbours a few times (the pocket rides on these)."""
    vn = vertex_normals(X, F)
    nb = neighbours(len(X), F)
    for _ in range(iters):
        vn = np.array([vn[s].mean(0) if len(s) else vn[i] for i, s in enumerate(nb)])
        vn /= np.maximum(np.linalg.norm(vn, axis=1)[:, None], 1e-9)
    return vn


def neighbours(n, F):
    nb = [set() for _ in range(n)]
    for f in F:
        a, b, c = (int(x) for x in f)
        nb[a].update((b, c))
        nb[b].update((a, c))
        nb[c].update((a, b))
    return [np.array(sorted(s)) for s in nb]


def taubin(X, nb, iters=2, lam=0.5, mu=-0.53, fixed=None):
    X = X.copy()
    for _ in range(iters):
        for w in (lam, mu):
            avg = np.array([X[s].mean(0) if len(s) else X[i] for i, s in enumerate(nb)])
            d = (avg - X) * w
            if fixed is not None:
                d[fixed] = 0
            X += d
    return X


def settle(X, target=0.25, reach=0.8):
    """Push the cloth out of the colliders to `target` cm and draw what hovers within `reach` onto them."""
    d = env_sdf(X)
    g = env_grad(X)
    move = np.zeros(len(X))
    under = d < target
    move[under] = target - d[under]
    band = (d >= target) & (d < reach)
    f = np.clip((reach - d[band]) / (reach - 0.5), 0, 1)
    move[band] = -(d[band] - target) * f
    return X + g * move[:, None]


def lift_for_pocket(m):
    """Where the pocket lies between the garment and the credenza (face down), lift the garment, and whatever is
    piled on it, enough to make room for the pocket's own layer."""
    X, F = m["X"], m["faces"]
    pv = np.unique(F[m["fregion"] == 2])
    vn = smooth_normals(X, F)
    need = THICK + 0.035 + 0.12 + THICK / 2 + 0.25
    d = env_sdf(X[pv] + vn[pv] * need)
    bad = d < 0.0
    if not bad.any():
        return X, 0.0
    src, D = X[pv[bad]], env_grad(X[pv[bad]] + vn[pv[bad]] * need) * (-d[bad])[:, None]
    disp = np.zeros_like(X)
    for s0 in range(0, len(X), 2000):
        Q = X[s0:s0 + 2000]
        dist = np.sqrt(((Q[:, None, :] - src[None]) ** 2).sum(2))
        j = dist.argmin(1)
        f = smoothstep(1.0 - dist[np.arange(len(Q)), j] / 3.0)
        disp[s0:s0 + 2000] = D[j] * f[:, None]
    return X + disp, float(np.linalg.norm(D, axis=1).max())


def boundary_loops(F):
    """Edges used by one face (oriented as in that face)."""
    cnt = {}
    for f in F:
        for k in range(3):
            a, b = int(f[k]), int(f[(k + 1) % 3])
            key = (min(a, b), max(a, b))
            cnt.setdefault(key, []).append((a, b))
    return [v[0] for v in cnt.values() if len(v) == 1]


def solidify(X, F, thick, uv_of, mat_of_face, keep_inner=True, rim_round=0.85):
    """Thicken a triangle surface by `thick` (centred), with rounded rims on its free edges.

    Returns verts, faces (lists), per-face material index, per-face-corner uvs, and the outer vertex ids."""
    vn = vertex_normals(X, F)
    n = len(X)
    h = thick / 2
    outer = X + vn * h
    inner = X - vn * h
    verts = list(outer) + list(inner)
    faces, mats, uvs = [], [], []
    for fi, f in enumerate(F):
        a, b, c = (int(x) for x in f)
        faces.append((a, b, c))
        mats.append(mat_of_face[fi])
        uvs.append([uv_of(a, 0), uv_of(b, 0), uv_of(c, 0)])
        if keep_inner:
            faces.append((n + c, n + b, n + a))
            mats.append(mat_of_face[fi])
            uvs.append([uv_of(c, 1), uv_of(b, 1), uv_of(a, 1)])
    # rims: a half-round from the outer to the inner shell, bulging outward
    bedges = boundary_loops(F)
    bdir = np.zeros_like(X)
    face_of_edge = {}
    for fi, f in enumerate(F):
        for k in range(3):
            face_of_edge[(int(f[k]), int(f[(k + 1) % 3]))] = fi
    for a, b in bedges:
        e = X[b] - X[a]
        cen = X[F[face_of_edge[(a, b)]]].mean(0)
        out = np.cross(e, vn[a] + vn[b])
        if out @ (0.5 * (X[a] + X[b]) - cen) < 0:
            out = -out
        out /= max(np.linalg.norm(out), 1e-12)
        bdir[a] += out
        bdir[b] += out
    bverts = sorted({v for e in bedges for v in e})
    rows = {}
    for v in bverts:
        d = bdir[v] / max(np.linalg.norm(bdir[v]), 1e-12)
        ids = [v]
        for ang in (45, 90, 135):
            r = math.radians(ang)
            p = X[v] + vn[v] * h * math.cos(r) + d * h * math.sin(r) * rim_round
            ids.append(len(verts))
            verts.append(p)
        ids.append(n + v)
        rows[v] = ids
    for a, b in bedges:
        fi = face_of_edge[(a, b)]
        ra, rb = rows[a], rows[b]
        for k in range(4):
            # face (a,b,..) is CCW seen from outside, so the rim runs b->a on the outer row
            faces.append((rb[k], ra[k], ra[k + 1], rb[k + 1]))
            mats.append(mat_of_face[fi])
            ua, ub = uv_of(a, 0), uv_of(b, 0)
            dv = thick * 0.01 / 4
            uvs.append([(ub[0], ub[1] + dv * k), (ua[0], ua[1] + dv * k), (ua[0], ua[1] + dv * (k + 1)),
                        (ub[0], ub[1] + dv * (k + 1))])
    return np.array(verts), faces, mats, uvs, n


# ================================================================ locating pattern points on the draped surface

def locate(uvp, m, layer=0):
    """3D point, normal (and face) of the draped front/back layer at pattern position uvp."""
    F, uv, X = m["faces"], m["uv"], m["X"]
    sel = np.where(m["flayer"] == layer)[0]
    for fi in sel:
        a, b, c = F[fi]
        p0, p1, p2 = uv[a], uv[b], uv[c]
        d = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
        if abs(d) < 1e-12:
            continue
        l0 = ((p1[1] - p2[1]) * (uvp[0] - p2[0]) + (p2[0] - p1[0]) * (uvp[1] - p2[1])) / d
        l1 = ((p2[1] - p0[1]) * (uvp[0] - p2[0]) + (p0[0] - p2[0]) * (uvp[1] - p2[1])) / d
        l2 = 1 - l0 - l1
        if min(l0, l1, l2) >= -1e-6:
            return l0 * X[a] + l1 * X[b] + l2 * X[c], fi, (a, b, c), (l0, l1, l2)
    raise ValueError(f"pattern point {uvp} not on layer {layer}")


# ================================================================ small solids with uvs

def lathe_uv(profile, segs, mat_frame):
    """Revolve (r, z) cm round local Z, transform by the 4x4 `mat_frame`; quads, uvs in m."""
    verts, faces, uvs = [], [], []
    rings = []
    arc = [0.0]
    for i in range(1, len(profile)):
        arc.append(arc[-1] + math.dist(profile[i], profile[i - 1]))
    for r, z in profile:
        ring = []
        for k in range(segs + 1):
            a = 2 * math.pi * k / segs
            p = mat_frame @ Vector((r * math.cos(a), r * math.sin(a), z))
            ring.append(len(verts))
            verts.append(np.array(p[:]))
        rings.append(ring)
    rmax = max(r for r, _ in profile)
    for i in range(len(profile) - 1):
        for k in range(segs):
            faces.append((rings[i][k], rings[i][k + 1], rings[i + 1][k + 1], rings[i + 1][k]))
            u0, u1 = 2 * math.pi * rmax * k / segs * 0.01, 2 * math.pi * rmax * (k + 1) / segs * 0.01
            uvs.append([(u0, arc[i] * 0.01), (u1, arc[i] * 0.01), (u1, arc[i + 1] * 0.01), (u0, arc[i + 1] * 0.01)])
    return verts, faces, uvs


def frame_matrix(origin, zdir, xhint=None):
    z = Vector(zdir).normalized()
    x = Vector(xhint) if xhint is not None else z.orthogonal()
    x = (x - x.dot(z) * z)
    if x.length < 1e-6:
        x = z.orthogonal()
    x.normalize()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(origin)
    return m


# ================================================================ drawcords (a little rope simulation)

def rope(start, out_dir, length, seg, surf_bvh, other=None, iters=700):
    n = int(round(length / seg)) + 1
    P = np.zeros((n, 3))
    P[0] = start
    P[1] = start + out_dir * seg
    down = np.array([0.0, 0.0, -1.0])
    rc = 0.26
    for i in range(2, n):
        # lay the cord out by walking down the garment's surface: never through the cloth or the credenza
        loc, nrm, _i, dist = surf_bvh.find_nearest(Vector(P[i - 1]), 3.0)
        d = down.copy()
        if loc is not None:
            nn = np.array(nrm[:])
            d = d - (d @ nn) * nn
            if np.linalg.norm(d) < 0.2:
                d = down - 0.5 * nn
        P[i] = P[i - 1] + seg * d / np.linalg.norm(d)
        for _ in range(3):
            loc, nrm, _i, dist = surf_bvh.find_nearest(Vector(P[i]), 3.0)
            if loc is not None and (Vector(P[i]) - loc).dot(nrm) < rc:
                P[i] = np.array((loc + nrm * rc)[:])
            sd = env_sdf(P[i:i + 1])[0]
            if sd < rc:
                P[i] = P[i] + env_grad(P[i:i + 1])[0] * (rc - sd)
    prev = P.copy()
    g = np.array([0.0, 0.0, -981.0])
    dt = 1.0 / 240
    for it in range(iters):
        damp = 0.96
        vel = (P - prev) * damp
        prev = P.copy()
        P = P + vel + g * dt * dt
        P[0] = start
        for _ in range(8):
            P[1] = 0.5 * P[1] + 0.5 * (start + out_dir * seg)
            for i in range(n - 1):
                d = P[i + 1] - P[i]
                L = np.linalg.norm(d)
                corr = (L - seg) / max(L, 1e-9) * d
                if i == 0:
                    P[i + 1] -= corr
                else:
                    P[i] += 0.5 * corr
                    P[i + 1] -= 0.5 * corr
            # bending: a flat braided cord is fairly stiff
            mid = 0.5 * (P[:-2] + P[2:])
            P[1:-1] += 0.08 * (mid - P[1:-1])
            P[0] = start
            # collisions: the environment, the garment, the other cord
            sd = env_sdf(P)
            hit = sd < rc
            if hit.any():
                P[hit] += env_grad(P[hit]) * (rc - sd[hit])[:, None]
            for i in range(2, n):
                loc, nrm, _i, dist = surf_bvh.find_nearest(Vector(P[i]), 3.0)
                if loc is None:
                    continue
                h = (Vector(P[i]) - loc).dot(nrm)
                if h < rc:
                    P[i] = np.array((loc + nrm * rc)[:])
                elif h < rc + 1.5:
                    # fleece is grippy: a cord near the cloth lies on it rather than hanging free
                    P[i] = P[i] - np.array(nrm[:]) * (h - rc) * 0.2
            if other is not None:
                for i in range(2, n):
                    d = np.linalg.norm(other - P[i], axis=1)
                    j = int(d.argmin())
                    if d[j] < 0.32:
                        P[i] += (P[i] - other[j]) / max(d[j], 1e-6) * (0.32 - d[j])
    return P


def cord_mesh(P, surf_bvh, width=0.9, thick=0.22, taper_len=2.6):
    """Sweep a flat cord along P; it lies flat on the garment, narrowing into the aglet at the end."""
    n = len(P)
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1)[:, None]
    B = np.zeros_like(P)
    prev = None
    for i in range(n):
        loc, nrm, _i, dist = surf_bvh.find_nearest(Vector(P[i]), 2.0)
        cand = np.array(nrm[:]) if loc is not None else (prev if prev is not None else np.array([1.0, 0, 0]))
        if prev is not None and cand @ prev < 0:
            cand = -cand
        cand = cand - (cand @ T[i]) * T[i]
        cand /= max(np.linalg.norm(cand), 1e-9)
        B[i] = cand
        prev = cand
    for _ in range(6):
        B[1:-1] = 0.5 * B[1:-1] + 0.25 * (B[:-2] + B[2:])
        B -= (B * T).sum(1)[:, None] * T
        B /= np.linalg.norm(B, axis=1)[:, None]
    W = np.cross(T, B)
    arcl = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    L = arcl[-1]
    prof = S.rounded_rect(1.0, 1.0, 0.45, segs=3)
    verts, faces, uvs = [], [], []
    m = len(prof)
    perim = [0.0]
    for k in range(1, m + 1):
        perim.append(perim[-1] + math.dist(prof[k % m], prof[k - 1]))
    for i in range(n):
        t = np.clip((L - arcl[i]) / taper_len, 0, 1)
        w = 0.36 + (width - 0.36) * smoothstep(t)
        th = 0.30 + (thick - 0.30) * smoothstep(t)
        for (a, b) in prof:
            verts.append(P[i] + W[i] * a * w + B[i] * b * th)
    for i in range(n - 1):
        for k in range(m):
            k2 = (k + 1) % m
            faces.append((i * m + k, i * m + k2, (i + 1) * m + k2, (i + 1) * m + k))
            uvs.append([(perim[k] * 0.01, arcl[i] * 0.01), (perim[k + 1] * 0.01, arcl[i] * 0.01),
                        (perim[k + 1] * 0.01, arcl[i + 1] * 0.01), (perim[k] * 0.01, arcl[i + 1] * 0.01)])
    # caps
    c0 = len(verts)
    verts.append(P[0])
    c1 = len(verts)
    verts.append(P[-1])
    for k in range(m):
        k2 = (k + 1) % m
        faces.append((c0, k2, k))
        uvs.append([(0, 0), (0.002, 0), (0, 0.002)])
        faces.append((c1, (n - 1) * m + k, (n - 1) * m + k2))
        uvs.append([(0, 0), (0.002, 0), (0, 0.002)])
    return verts, faces, uvs, T[-1]


# ================================================================ the note patch

def find_patch(Xo, No, ok, occluders, keep_away, z_range=(58.0, 69.0), strict=True):
    """Best 8x8 cm patch on the outer surface facing +X: returns centre, normal, max deviation (cm)."""
    tree = occluders
    idx = np.where(ok & (No[:, 0] > 0.55) & (Xo[:, 2] > z_range[0]) & (Xo[:, 2] < z_range[1]))[0]
    best = None
    for i in idx[::2]:
        c = Xo[i]
        if np.linalg.norm(keep_away - c, axis=1).min() < 10.0:
            continue
        near = np.where(np.linalg.norm(Xo - c, axis=1) < 6.5)[0]
        near = near[(No[near] @ No[i]) > 0.3]
        if len(near) < 12:
            continue
        P = Xo[near]
        cen = P.mean(0)
        _u, _s, vt = np.linalg.svd(P - cen)
        n = vt[2] if vt[2] @ No[i] > 0 else -vt[2]
        hx = np.cross([0, 0, 1.0], n)
        hx /= max(np.linalg.norm(hx), 1e-9)
        up = np.cross(n, hx)
        q = P - c
        a, b, hgt = q @ hx, q @ up, q @ n
        sq = (np.abs(a) <= 4.0) & (np.abs(b) <= 4.0)
        if sq.sum() < 10 or not ok[near[sq]].all():
            continue
        # the square must be covered by this one sheet (no gaps where the surface turns away)
        cover = np.histogram2d(a[sq], b[sq], bins=4, range=[[-4, 4], [-4, 4]])[0]
        if (cover == 0).any():
            continue
        dev = hgt[sq].max() - hgt[sq].min()
        # visible from the front and along the normal
        vis = True
        for d in (n, np.array([1.0, 0, 0]), np.array([0.85, -0.45, 0.25])):
            d = d / np.linalg.norm(d)
            hit = tree.ray_cast(Vector(c + n * 0.15), Vector(d), 300.0)
            if hit[0] is not None:
                vis = False
                break
        if not vis and strict:
            continue
        score = dev + 0.03 * abs(c[2] - 64.0) + 0.4 * (1 - n[0])
        if best is None or score < best[0]:
            best = (score, c, n, dev)
    if best is None:
        if strict:
            print(f"[{NAME}] WARNING: no visible flat patch in z {z_range}; relaxing")
            return find_patch(Xo, No, ok, occluders, np.full((1, 3), 1e6), (45.0, 75.0), strict=False)
        raise RuntimeError("no flat front-facing patch found")
    return best[1], best[2], best[3]


def flatten_patch(X, vn, c, n, half, r_in=6.0, r_out=9.5):
    """Press the cloth under the note flat: lift the facing sheet (mid-surface X) onto the plane through its
    most outward point. Only ever moves cloth outward, toward the note, so nothing behind is touched."""
    q = X - c
    hgt = q @ n
    rad = np.linalg.norm(q - np.outer(hgt, n), axis=1)
    sheet = (rad < r_out) & (np.abs(hgt + half) < 1.2) & ((vn @ n) > 0.3)
    core = sheet & (rad < r_in)
    h0 = hgt[core].max()
    f = smoothstep((r_out - rad[sheet]) / (r_out - r_in))
    d = np.maximum(h0 - hgt[sheet], 0.0) * f
    X = X.copy()
    X[sheet] += np.outer(d, n)
    return X, float(d.max())


# ================================================================ materials and preview

def materials(grey):
    fleece_col = (0.32, 0.32, 0.33) if grey else (0.026, 0.026, 0.028)
    rib_col = (0.26, 0.26, 0.27) if grey else (0.020, 0.020, 0.022)
    mats = [
        S.material("M_Fleece", fleece_col, 0.97, specular=0.22),
        S.material("M_Rib", rib_col, 0.92, specular=0.25),
        S.material("M_Drawcord", (0.03, 0.03, 0.032), 0.8, specular=0.3),
        S.material("M_Aglet", (0.70, 0.70, 0.72), 0.3, metallic=1.0),
    ]
    # brushed fleece: a soft sheen at grazing angles, no gloss
    for m, sheen in ((mats[0], 0.35), (mats[1], 0.25), (mats[2], 0.15)):
        bsdf = next((nd for nd in m.node_tree.nodes if nd.type == "BSDF_PRINCIPLED"), None)
        if bsdf is not None:
            for key, val in (("Sheen Weight", sheen), ("Sheen Roughness", 0.65)):
                if key in bsdf.inputs:
                    bsdf.inputs[key].default_value = val
    return mats


def build_object(name, verts_m, faces, mat_idx, uvs, mats):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts_m], [], [tuple(f) for f in faces])
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", list(mat_idx))
    uvl = me.uv_layers.new(name="UVMap")
    flat = [c for face_uv in uvs for uv in face_uv for c in uv]
    uvl.data.foreach_set("uv", flat)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def clear_preview():
    for nm in ("_floor", "_key", "_fill", "_rim", "_cam", "_frame", "_box_top", "_box_body", "_note", "_wall"):
        ob = bpy.data.objects.get(nm)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)


def frame_helper(lo, hi):
    me = bpy.data.meshes.new("_frame")
    me.from_pydata([(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], [], [])
    ob = bpy.data.objects.new("_frame", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def note_object(c_m, n, size=0.076):
    n = Vector(n).normalized()
    hx = Vector((0, 0, 1)).cross(n).normalized()
    up = n.cross(hx)
    m = Matrix((hx, up, n)).transposed().to_4x4()
    m.translation = Vector(c_m) + n * 0.0004
    ob = S.box("_note", (-size / 2, -size / 2, 0), (size / 2, size / 2, 0.0004),
               S.material("_NoteYellow", (0.95, 0.80, 0.12), 0.65))
    ob.matrix_world = m
    return ob


THICK = 0.35   # fleece thickness, cm
STUDIO_CAM = (TOP_X + 300.0, -250.0, 160.0)   # the studio camera (cm, this frame), aimed at the top's front corner


def shells(m):
    """Solidified garment (with seam grooves) and the kangaroo pocket on its front, from the mid-surface."""
    Xs, F = m["X"], m["faces"]
    vn = vertex_normals(Xs, F)
    uvp, lay = m["uv"], m["layer"]
    seam_v = np.zeros(len(Xs), bool)
    for (a, b, _l) in m["seams"]:
        seam_v[a] = seam_v[b] = True

    def uv_garment(v, shell):
        u, w = uvp[v]
        if lay[v] == 1:
            u = -u + 200.0
        return (u * 0.01 + 4.0 * shell, w * 0.01)

    mat_face = [1 if r == 1 else 0 for r in m["fregion"]]
    gv, gf, gm, guv, n_outer = solidify(Xs, F, THICK, uv_garment, mat_face)
    gv[:n_outer] -= vn * np.where(seam_v, 0.05, 0.0)[:, None]
    # kangaroo pocket: a second layer of fleece on the front, its slanted openings standing a little proud
    pf = np.where(m["fregion"] == 2)[0]
    pverts = sorted({int(v) for f in F[pf] for v in f})
    pmap = {v: i for i, v in enumerate(pverts)}
    PF = np.array([[pmap[int(v)] for v in F[fi]] for fi in pf])
    _r, _l, opening = pocket_polygon()
    op = np.array(opening)
    mop = np.array(mirror(op))
    dop = seg_dist(uvp[pverts], np.concatenate([op[:-1], mop[:-1]]), np.concatenate([op[1:], mop[1:]]))
    lift = THICK + 0.035 + 0.12 * smoothstep(1 - dop / 3.0)
    # offset along smoothed normals, so the pocket rides over tight folds without kinking
    pn_s = smooth_normals(Xs, F)
    PX = Xs[pverts] + pn_s[pverts] * lift[:, None]

    def uv_pocket(v, shell):
        u, w = uvp[pverts[v]]
        return (u * 0.01 + 8.0 + 2.0 * shell, w * 0.01)

    pv, pfc, pm, puv, pn = solidify(PX, PF, THICK, uv_pocket, [0] * len(PF))
    return dict(vn=vn, gv=gv, gf=gf, gm=gm, guv=guv, n_outer=n_outer, pv=pv, pf=pfc, pm=pm, puv=puv, pn=pn)


def outer_tree(sh):
    """BVH of the outer surfaces only (garment and pocket), for things lying on the hoodie."""
    n, pn = sh["n_outer"], sh["pn"]
    verts = [Vector(v) for v in sh["gv"][:n]] + [Vector(v) for v in sh["pv"][:pn]]
    faces = [tuple(f) for f in sh["gf"] if max(f) < n] + [tuple(x + n for x in f) for f in sh["pf"] if max(f) < pn]
    return BVHTree.FromPolygons(verts, faces)


# ================================================================ main

def main():
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)
    S.reset_scene()
    t0 = time.time()

    pat = build_pattern(args.h)
    g = assemble(pat)
    X0 = start_pose(g)
    print(f"[{NAME}] pattern: {len(g['uv'])} verts, {len(g['faces'])} tris  (front {len(pat['Tf'])}, "
          f"back {len(pat['Tb'])})  start env clearance {env_sdf(X0).min():.2f} cm  {time.time() - t0:.1f}s")

    cache = os.path.join(args.out, "hoodie_sim.npz")
    X = None
    if args.reuse_sim and os.path.exists(cache):
        z = np.load(cache)
        if z["faces"].shape == g["faces"].shape and (z["faces"] == g["faces"]).all():
            X = z["X"]
            print(f"[{NAME}] reusing {cache}")
        else:
            print(f"[{NAME}] cache topology differs; simulating")
    if X is None:
        X = simulate(X0, g["faces"], args, pin_weights(g, X0) if USE_PINS and not args.no_pins else None)
        np.savez(cache, X=X, faces=g["faces"], X0=X0, uv=g["uv"], layer=g["layer"])
    if args.sim_only:
        return

    # -------------------------------------------------- smooth, subdivide, settle
    m = dict(g, X=X)
    nb = neighbours(len(X), g["faces"])
    m["X"] = taubin(X, nb, iters=2)
    m = loop_subdivide(m)
    m["X"] = settle(settle(m["X"]))
    m["X"], plift = lift_for_pocket(m)
    m["X"], plift2 = lift_for_pocket(m)
    plift += plift2
    if plift:
        print(f"[{NAME}] garment lifted up to {plift * 10:.1f} mm over the pocket")
    F = m["faces"]

    # first pass: shells, then the eyelets and drawcords lying on them
    sh = shells(m)
    parts = []   # (verts cm, faces, material slot, uvs)
    surf_tree = outer_tree(sh)
    starts = []
    for side in (1, -1):
        p, fi, tri, bary = locate(np.array([EYELET[0] * side, EYELET[1]]), m, layer=0)
        nrm = sum(w * sh["vn"][v] for w, v in zip(bary, tri))
        nrm /= np.linalg.norm(nrm)
        top = p + nrm * THICK / 2
        prof = [(0.24, -0.06), (0.24, 0.07), (0.28, 0.12), (0.37, 0.14), (0.46, 0.115), (0.50, 0.05),
                (0.50, -0.02), (0.44, -0.06), (0.24, -0.06)]
        ev, ef, euv = lathe_uv(prof, 24, frame_matrix(top, nrm))
        parts.append((ev, ef, 3, euv))
        hv, hf, huv = lathe_uv([(0.0, 0.0), (0.245, 0.0)], 16, frame_matrix(top + nrm * 0.005, nrm))
        parts.append((hv, hf, 2, huv))       # dark floor of the eyelet hole
        starts.append((top + nrm * 0.1, nrm))
    paths = []
    for k, (start, nrm) in enumerate(starts):
        paths.append(rope(start, nrm, [16.0, 22.0][k], 0.5, surf_tree, paths[0] if paths else None))
    for P in paths:
        P = P.copy()
        arcl = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        cut = int(np.searchsorted(arcl, arcl[-1] - 2.2 + 0.25))
        cv, cf, cuv, _t = cord_mesh(P[:cut + 1], surf_tree)
        parts.append((cv, cf, 2, cuv))
        dirn = (P[cut] - P[cut - 1]) / max(np.linalg.norm(P[cut] - P[cut - 1]), 1e-9)
        a0 = P[cut] - dirn * 0.25
        d = P[-1] - a0
        Lg = float(np.linalg.norm(d))
        prof = [(0.0, -0.02), (0.205, -0.02), (0.215, 0.05), (0.215, 0.30), (0.19, 0.36), (0.205, 0.42),
                (0.205, Lg - 0.30), (0.17, Lg - 0.08), (0.10, Lg), (0.0, Lg + 0.01)]
        av, af, auv = lathe_uv(prof, 20, frame_matrix(a0, d))
        parts.append((av, af, 3, auv))
    # last guard for the small solids: anything grazing the credenza is nudged out (0.3 mm clear)
    for k, (v, f, mt, uv) in enumerate(parts):
        v = np.array(v)
        d = env_sdf(v)
        bad = d < 0.03
        if bad.any():
            v[bad] += env_grad(v[bad]) * (0.03 - d[bad])[:, None]
        parts[k] = (v, f, mt, uv)
    keep_away = np.concatenate([np.array(v) for (v, _f, _m, _u) in parts])

    # -------------------------------------------------- the note patch: find it, press it flat, rebuild
    n_out = sh["n_outer"]
    plain = np.ones(len(m["X"]), bool)
    for fi, f in enumerate(F):
        if m["fregion"][fi] != 0:
            plain[list(f)] = False
    occ_v, occ_f = list(sh["gv"]) + list(sh["pv"]), \
        [tuple(f) for f in sh["gf"]] + [tuple(x + len(sh["gv"]) for x in f) for f in sh["pf"]]
    for (v, f, _mt, _u) in parts:
        b0 = len(occ_v)
        occ_v += list(v)
        occ_f += [tuple(x + b0 for x in ff) for ff in f]
    occ_tree = BVHTree.FromPolygons([Vector(v) for v in occ_v], occ_f)
    Xo = sh["gv"][:n_out]
    c, n, dev = find_patch(Xo, vertex_normals(Xo, F), plain, occ_tree, keep_away)
    m["X"], lift = flatten_patch(m["X"], sh["vn"], c, n, THICK / 2)
    sh = shells(m)
    Xo = sh["gv"][:n_out]
    q = Xo - c
    hgt = q @ n
    hx = np.cross([0, 0, 1.0], n)
    hx /= np.linalg.norm(hx)
    up = np.cross(n, hx)
    sq = (np.abs(q @ hx) <= 4) & (np.abs(q @ up) <= 4) & (hgt > -1.0) & (hgt < 2.0)
    top_h = hgt[sq].max()
    dev_after = top_h - hgt[sq].min()
    note_c = c + n * top_h
    yaw = math.degrees(math.atan2(n[1], n[0]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, float(n[2])))))
    note = {"x": round(float(note_c[0] - ORIGIN[0]), 2), "y": round(float(note_c[1] - ORIGIN[1]), 2),
            "z": round(float(note_c[2] - ORIGIN[2]), 2), "yaw": round(yaw, 1), "pitch": round(pitch, 1)}
    with open(os.path.join(args.out, "hoodie_note.json"), "w") as fh:
        json.dump(note, fh, indent=2)
    print(f"[{NAME}] note patch: {note}  normal ({n[0]:.3f}, {n[1]:.3f}, {n[2]:.3f})  "
          f"relief before {dev * 10:.1f} mm, after {dev_after * 10:.1f} mm (lifted up to {lift * 10:.1f} mm)")

    # -------------------------------------------------- one mesh
    mats = materials(args.grey)
    allv, allf, allm, alluv = [], [], [], []

    def add(v, f, mt, uv):
        base = len(allv)
        allv.extend(list(v))
        allf.extend([tuple(x + base for x in ff) for ff in f])
        allm.extend(mt if isinstance(mt, list) else [mt] * len(f))
        alluv.extend(uv)

    add(sh["gv"], sh["gf"], sh["gm"], sh["guv"])
    add(sh["pv"], sh["pf"], sh["pm"], sh["puv"])
    for v, f, mt, uv in parts:
        add(v, f, mt, uv)
    V = np.array(allv)
    for label, arr in (("garment", sh["gv"]), ("pocket", sh["pv"])) + tuple(
            (f"part{i}", np.array(p[0])) for i, p in enumerate(parts)):
        d = env_sdf(np.array(arr))
        if d.min() < 0:
            j = int(d.argmin())
            print(f"[{NAME}]   {label}: {int((d < 0).sum())} inside, worst {d.min() * 10:.2f} mm at {np.round(arr[j], 1)}")
    # nothing inside the credenza, the wall or the floor
    clear = env_sdf(V)
    print(f"[{NAME}] min clearance to the credenza / wall / floor: {clear.min() * 10:.2f} mm "
          f"({(clear < 0).sum()} vertices inside)")
    ob = build_object(NAME, V * 0.01, allf, allm, alluv, mats)
    S.set_origin(ob, (ORIGIN[0] * 0.01, ORIGIN[1] * 0.01, ORIGIN[2] * 0.01))
    S.tidy(ob, sharp_angle=85)
    fbx = os.path.join(args.out, NAME + ".fbx")
    S.export_fbx(ob, fbx)
    lo, hi = S.bbox(ob)
    print("=" * 60)
    print(f"{NAME}: exported {fbx}")
    print(f"{NAME}: materials {[mm.name for mm in ob.data.materials]}")
    print(f"{NAME}: triangles {S.tri_count(ob)}")
    print(f"{NAME}: bbox cm  X {lo.x*100:.1f}..{hi.x*100:.1f}  Y {lo.y*100:.1f}..{hi.y*100:.1f}"
          f"  Z {lo.z*100:.1f}..{hi.z*100:.1f}")
    print(f"[{NAME}] total {time.time() - t0:.0f}s")
    print("=" * 60)
    if args.no_render:
        return
    render_all(ob, args, note_c, n)


def render_all(ob, args, note_c, n):
    o = Vector(ORIGIN) * 0.01
    note_m = Vector(note_c) * 0.01 - o
    S.render_preview(ob, os.path.join(args.out, NAME + ".png"), (1.0, 0.85, 0.75), args.samples, lens=60)
    clear_preview()
    S.render_preview(ob, os.path.join(args.out, NAME + "_front.png"), (1.0, 0.0, 0.06), args.samples, lens=60)
    clear_preview()
    # on a light-oak stand-in for the credenza, from the front-left like credenza.jpg
    oak = S.material("_Oak", (0.62, 0.44, 0.27), 0.55)
    top = S.box("_box_top", (0, -0.75, -TOP_T * 0.01), (TOP_X * 0.01, 0, 0), oak)
    S.bevel(top, 0.002, 2)
    body = S.box("_box_body", (0, -0.75 + OVER * 0.01, -TOP_Z * 0.01), ((TOP_X - OVER) * 0.01, -OVER * 0.01,
                                                                          -TOP_T * 0.01), oak)
    S.bevel(body, 0.002, 2)
    note_object(note_m, n)
    lo, hi = S.bbox(ob)
    frame_helper((0.0, -0.55, -TOP_Z * 0.01), (max(hi.x, 0.5), hi.y + 0.02, max(hi.z, 0.05)))
    S.render_preview(bpy.data.objects["_frame"], os.path.join(args.out, NAME + "_on_box.png"),
                     (1.0, -0.62, 0.42), args.samples, lens=50)
    clear_preview()
    # from the studio camera's direction: it stands 300 cm out in front and 250 cm to the left of the corner (Unreal
    # +Y, which is this frame's -Y once the FBX is imported) at 160 cm, and looks at the corner; a long lens for its
    # flat perspective from 4 m away
    top = S.box("_box_top", (0, -0.75, -TOP_T * 0.01), (TOP_X * 0.01, 0, 0), oak)
    body = S.box("_box_body", (0, -0.75 + OVER * 0.01, -TOP_Z * 0.01), ((TOP_X - OVER) * 0.01, -OVER * 0.01,
                                                                          -TOP_T * 0.01), oak)
    note_object(note_m, n)
    frame_helper((0.0, -0.45, -0.45), (max(hi.x, 0.5), hi.y + 0.02, max(hi.z, 0.05)))
    cam = Vector(STUDIO_CAM) - Vector((TOP_X, 0.0, TOP_Z))
    S.render_preview(bpy.data.objects["_frame"], os.path.join(args.out, NAME + "_studio.png"),
                     tuple(cam), args.samples, lens=85)
    clear_preview()
    # close-up of the note patch, from about 60 cm
    top = S.box("_box_top", (0, -0.75, -TOP_T * 0.01), (TOP_X * 0.01, 0, 0), oak)
    body = S.box("_box_body", (0, -0.75 + OVER * 0.01, -TOP_Z * 0.01), ((TOP_X - OVER) * 0.01, -OVER * 0.01,
                                                                          -TOP_T * 0.01), oak)
    note_object(note_m, n)
    c = note_m
    frame_helper((c.x - 0.12, c.y - 0.15, c.z - 0.15), (c.x + 0.02, c.y + 0.15, c.z + 0.12))
    S.render_preview(bpy.data.objects["_frame"], os.path.join(args.out, NAME + "_close.png"),
                     (1.0, -0.35, 0.25), args.samples, lens=60, floor=False)
    clear_preview()
    for nm in ("_box_top", "_box_body", "_note"):
        x = bpy.data.objects.get(nm)
        if x is not None:
            bpy.data.objects.remove(x, do_unlink=True)


if __name__ == "__main__":
    main()
