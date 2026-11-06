"""The numbers behind blender/garment_fit.py (refit a garment to a body with real ease), numpy only, so they are tested
without Blender (blender/tests/test_garmentfit.py).

A garment fits when every vertex stands off the body by an EASE that depends on where it is: close at the collar
and the shoulder seam (it hangs from there), more over the chest, most at the waist and the hem (it falls), some
round the sleeves. A uniform offset (a WPO inflate, a shrinkwrap with one offset) is a shell: it reads as armor.

- `regions(weights, groups)`: each vertex's region from its dominant bone (its skin weights).
- `targets(region, ease_cm)`: the target ease per vertex.
- `fit_displacement(dist, normal, target, ...)`: how far to move each vertex along the body normal so its distance
  reaches at least the target (and at most target + slack: a garment much looser than intended is drawn in a little).
- `smooth_field(values, nbrs, iters, pinned)`: Laplacian smoothing of a per-vertex field (the displacement, not the
  positions: the garment keeps its own folds and seams; the corrective-smooth idea).
- `transfer_weights(points, tris_xyz_idx, weights)`: skin weights from the body's nearest triangle, barycentric.
- `limit_normalize(W, max_inf)`: at most max_inf influences, rows summing to 1.
- `colours(ease, pinned)`: vertex colours for the cloth setup (R = ease / 5 cm, G = pinned): T3b's cloth.setup
  reads them for max distance.
- `ease_report(dist, region)`: the distribution per region (what qa.garment_look measures in the editor).
"""
from __future__ import annotations

import numpy as np

# bone-name stems -> region (first match wins; MetaHuman body skeleton names)
REGION_BONES = (
    ("collar", ("neck_", "head")),
    ("shoulder", ("clavicle_",)),
    ("sleeve", ("upperarm_", "lowerarm_")),
    ("chest", ("spine_05", "spine_04")),
    ("waist", ("spine_03", "spine_02")),
    ("hem", ("spine_01", "pelvis", "thigh_")),
)
REGIONS = ("collar", "shoulder", "sleeve", "chest", "waist", "hem", "other")
# a regular-fit cotton tee on a slim-to-average male (cm, garment to skin): fashion grading puts a regular tee's
# chest at +8-12 cm of girth over the body, i.e. ~1.3-1.9 cm of radial ease; slim fit ~0.8-1.2 (research doc)
EASE_CM = {"collar": 0.8, "shoulder": 0.6, "sleeve": 1.4, "chest": 1.6, "waist": 2.4, "hem": 2.8, "other": 1.2}
MIN_EASE_CM = 0.5   # nowhere closer: depth precision (~0.3 cm at 3 m) and skinning error under motion
PINNED = ("collar", "shoulder")


def regions(weights: np.ndarray, groups: list) -> np.ndarray:
    """Region index (into REGIONS) per vertex from its dominant bone. weights: (n, len(groups))."""
    reg_of_group = np.full(len(groups), REGIONS.index("other"))
    for gi, g in enumerate(groups):
        for r, stems in REGION_BONES:
            if any(g.startswith(s) or g == s for s in stems):
                reg_of_group[gi] = REGIONS.index(r)
                break
    if weights.size == 0:
        return np.zeros(0, int)
    dom = np.argmax(weights, axis=1)
    out = reg_of_group[dom]
    out[weights.max(1) <= 0] = REGIONS.index("other")
    return out


def targets(region: np.ndarray, ease_cm: dict | None = None) -> np.ndarray:
    e = {**EASE_CM, **(ease_cm or {})}
    table = np.array([e[r] for r in REGIONS], float)
    return table[region]


def fit_displacement(dist: np.ndarray, target: np.ndarray, *, min_ease: float = MIN_EASE_CM, slack: float = 3.0,
                     pull: float = 0.35) -> np.ndarray:
    """Signed move along the body normal per vertex (cm, + = out): up to max(target, min_ease) where it is closer
    (inside the body: dist < 0, all the way out); where it is looser than target + slack, `pull` of the excess back
    in (a garment that stands off is drawn towards the body, never through the target)."""
    want = np.maximum(target, min_ease)
    d = np.zeros_like(dist, float)
    close = dist < want
    d[close] = want[close] - dist[close]
    loose = dist > want + slack
    d[loose] = -pull * (dist[loose] - want[loose] - slack)
    return d


def neighbours(n: int, tris: np.ndarray) -> list:
    """Vertex adjacency from triangles (lists of neighbour indices)."""
    nb = [set() for _ in range(n)]
    for a, b, c in np.asarray(tris, int):
        nb[a].update((b, c))
        nb[b].update((a, c))
        nb[c].update((a, b))
    return [np.fromiter(s, int, len(s)) for s in nb]


def smooth_field(values: np.ndarray, nbrs: list, iters: int = 10, lam: float = 0.5,
                 pinned: np.ndarray | None = None, floor: np.ndarray | None = None) -> np.ndarray:
    """Laplacian smoothing of a per-vertex scalar (or vector) field; pinned vertices keep their value; with `floor`,
    no value drops below it (a push-out stays a push-out)."""
    v = np.array(values, float)
    for _ in range(max(0, iters)):
        avg = np.array([v[nb].mean(0) if len(nb) else v[i] for i, nb in enumerate(nbrs)])
        nv = v + lam * (avg - v)
        if pinned is not None:
            nv[pinned] = v[pinned]
        if floor is not None:
            nv = np.maximum(nv, floor)
        v = nv
    return v


def barycentric(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-12:
        return np.array((1.0, 0.0, 0.0))
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    r = np.clip(np.array((1 - v - w, v, w)), 0, 1)
    return r / max(r.sum(), 1e-9)


def transfer_weights(points: np.ndarray, hits: list, body_x: np.ndarray, body_t: np.ndarray,
                     body_w: np.ndarray) -> np.ndarray:
    """Skin weights at points from the body: hits[i] = (nearest point on the body, triangle index) or None (then the
    nearest body vertex). body_w: (n_body, n_groups). The Data Transfer modifier's 'nearest face interpolated', in
    numpy: Blender's BVHTree gives the hits."""
    out = np.zeros((len(points), body_w.shape[1]), float)
    for i, h in enumerate(hits):
        if h is None:
            j = int(np.argmin(((body_x - points[i]) ** 2).sum(1)))
            out[i] = body_w[j]
            continue
        q, ti = h
        t = body_t[ti]
        out[i] = barycentric(np.asarray(q, float), *body_x[t]) @ body_w[t]
    return out


def limit_normalize(W: np.ndarray, max_inf: int = 8, floor: float = 0.01) -> np.ndarray:
    W = np.array(W, float)
    W[W < floor] = 0
    if W.shape[1] > max_inf:
        idx = np.argsort(-W, axis=1)[:, max_inf:]
        np.put_along_axis(W, idx, 0, axis=1)
    s = W.sum(1, keepdims=True)
    return np.where(s > 0, W / np.maximum(s, 1e-12), W)


def colours(ease: np.ndarray, pinned: np.ndarray) -> np.ndarray:
    """RGBA per vertex for the cloth setup: R = ease / 5 cm (0..1), G = 1 where pinned (skinned, no sim), B 0, A 1."""
    out = np.zeros((len(ease), 4), float)
    out[:, 0] = np.clip(np.asarray(ease, float) / 5.0, 0, 1)
    out[:, 1] = np.asarray(pinned, bool).astype(float)
    out[:, 3] = 1.0
    return out


def ease_report(dist: np.ndarray, region: np.ndarray, max_cm: float = 15.0) -> dict:
    """Per region and overall: n, p10/median/p90 of the distance to the body, the share under 0 (inside) and under
    MIN_EASE_CM (too tight); spread = (p90 - p10) / median overall (a shell reads < ~0.5)."""
    out = {}
    d = np.asarray(dist, float)
    ok = np.abs(d) <= max_cm
    for ri, r in enumerate(REGIONS):
        m = ok & (region == ri)
        if m.any():
            x = d[m]
            out[r] = {"n": int(m.sum()), "p10": round(float(np.percentile(x, 10)), 3),
                      "median": round(float(np.median(x)), 3), "p90": round(float(np.percentile(x, 90)), 3),
                      "inside": round(float((x < 0).mean()), 4), "tight": round(float((x < MIN_EASE_CM).mean()), 4)}
    if ok.any():
        x = d[ok]
        med = float(np.median(x))
        out["all"] = {"n": int(ok.sum()), "median": round(med, 3), "inside": round(float((x < 0).mean()), 4),
                      "tight": round(float((x < MIN_EASE_CM).mean()), 4),
                      "spread": round(float((np.percentile(x, 90) - np.percentile(x, 10)) / med), 3) if med > 1e-6
                      else None}
    return out


def fit_gate(report: dict, *, max_inside: float = 0.0, max_tight: float = 0.02, min_spread: float = 0.6) -> list:
    """Problems with a fit, as plain strings (garment_fit.py exits 1 on any): verts inside the body, too many under
    MIN_EASE_CM, or an even shell (spread under min_spread)."""
    out = []
    a = report.get("all", {})
    if not a:
        return ["no garment vertex within reach of the body: wrong body, or not in the same pose/units"]
    if a["inside"] > max_inside:
        out.append(f"{100 * a['inside']:.2f}% of the garment's verts are inside the body (limit {100 * max_inside}%)")
    if a["tight"] > max_tight:
        out.append(f"{100 * a['tight']:.1f}% of the verts closer than {MIN_EASE_CM} cm (limit {100 * max_tight}%)")
    if a.get("spread") is not None and a["spread"] < min_spread:
        out.append(f"the ease is even (spread {a['spread']} < {min_spread}): a shell; drape it (--drape-frames)")
    return out


def edges_of(tris: np.ndarray) -> np.ndarray:
    """Unique undirected edges (m, 2) of a triangle list."""
    t = np.asarray(tris, int)
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    e.sort(axis=1)
    return np.unique(e, axis=0)


def harmonic_fill(values: np.ndarray, known: np.ndarray, edges: np.ndarray, iters: int = 400) -> np.ndarray:
    """Fill a per-vertex field where `known` is False by repeated neighbour averaging (Jacobi on the graph
    Laplacian), the known vertices held: the smooth interpolation of a displacement into a region it was not
    measured in. Vectorised over edges (30k-vertex bodies in seconds)."""
    v = np.array(values, float)
    known = np.asarray(known, bool)
    n = len(v)
    deg = np.zeros(n)
    np.add.at(deg, edges[:, 0], 1)
    np.add.at(deg, edges[:, 1], 1)
    deg = np.maximum(deg, 1)[:, None] if v.ndim > 1 else np.maximum(deg, 1)
    if (~known).any() and known.any():
        start = v[known].mean(0)
        v[~known] = start
    for _ in range(max(0, iters)):
        acc = np.zeros_like(v)
        np.add.at(acc, edges[:, 0], v[edges[:, 1]])
        np.add.at(acc, edges[:, 1], v[edges[:, 0]])
        nv = acc / deg
        v = np.where(known[:, None] if v.ndim > 1 else known, v, nv)
    return v


def vertex_normals(X: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals (unit)."""
    t = np.asarray(T, int)
    fn = np.cross(X[t[:, 1]] - X[t[:, 0]], X[t[:, 2]] - X[t[:, 0]])
    vn = np.zeros_like(X, float)
    for k in range(3):
        np.add.at(vn, t[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)


def morph_onto(ref_x: np.ndarray, ref_t: np.ndarray, nearest, match_cm: float = 1.5, iters: int = 400,
               tangent_cm: float = 0.5) -> tuple:
    """Another person's UNCUT body (ref_x, ref_t) moved onto a cut body of the person wanted: where a ref vertex
    has the cut body within match_cm (nearest(p) -> closest point on the cut body, or None), it moves there; the
    rest (the region the cut removed: under the garment) moves by the harmonic fill of those displacements.
    A match that is mostly a slide along the skin (tangential part over tangent_cm) is the hole's edge seen from
    inside the hole: left to the fill. Returns (morphed vertices, known mask, stats)."""
    disp = np.zeros_like(ref_x, float)
    known = np.zeros(len(ref_x), bool)
    N = vertex_normals(np.asarray(ref_x, float), ref_t)
    for i, p in enumerate(ref_x):
        q = nearest(p)
        if q is None:
            continue
        d = np.asarray(q, float) - p
        tang = d - (d @ N[i]) * N[i]  # a slide along the skin: the nearest point is the cut's edge, not a match
        if np.linalg.norm(d) <= match_cm and np.linalg.norm(tang) <= tangent_cm:
            disp[i] = d
            known[i] = True
    filled = harmonic_fill(disp, known, edges_of(ref_t), iters)
    mag = np.linalg.norm(filled, axis=1)
    return ref_x + filled, known, {"matched": round(float(known.mean()), 4),
                                   "fill_median_cm": round(float(np.median(mag[~known])), 3) if (~known).any() else 0.0,
                                   "fill_max_cm": round(float(mag[~known].max()), 3) if (~known).any() else 0.0}
