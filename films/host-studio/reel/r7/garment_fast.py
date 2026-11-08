"""garment_measure's arm geometry with numpy/scipy (round 7, the orchestrator: the pure-Python measure ran ~1 min a
frame on one core while the GPU box idled). NpEngine has PyEngine's calls and gives the same numbers
(test_garment_fast.py runs both on the same meshes); garment_measure's driver uses it with --engine fast, on the box,
from the meshes the editor hands it (the arms_dump stage). Never imported in the editor (no numpy there).

Nearest triangle: exact. A KD-tree on the triangle centroids gives the k nearest; a point is settled once the k-th
centroid is farther than (best distance + the largest centroid-to-corner radius), else k grows (to all triangles).
"""
import numpy as np
from scipy.spatial import cKDTree

import garment_measure as gm


class TS:
    """A set of torso triangles: corners A, B, C (k x 3), unit normals N, and each one's (part, first vertex)."""

    def __init__(self, A, B, C, N, part, vi):
        self.A, self.B, self.C, self.N = A, B, C, N
        self.part, self.vi = part, vi

    def __len__(self):
        return len(self.A)

    @staticmethod
    def empty():
        z = np.zeros((0, 3))
        return TS(z, z, z, z, np.zeros(0, dtype=object), np.zeros(0, dtype=np.int64))


def _unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.where(n > 1e-12, v / np.where(n > 1e-12, n, 1.0), 0.0)


def _chain_near(p, chain):
    """Per point: (distance to the chain, the nearest point on it), the first nearest segment as gm.seg_t's loop."""
    ch = np.asarray(chain, dtype=float)
    best_d = np.full(len(p), np.inf)
    best_c = np.zeros_like(p)
    for a, b in zip(ch[:-1], ch[1:]):
        ab = b - a
        L = ab @ ab
        t = np.clip(((p - a) @ ab) / L, 0.0, 1.0) if L > 1e-12 else np.zeros(len(p))
        c = a + t[:, None] * ab
        d = np.linalg.norm(p - c, axis=1)
        m = d < best_d
        best_d = np.where(m, d, best_d)
        best_c[m] = c[m]
    return best_d, best_c


def closest_on_tris(p, a, b, c):
    """gm.closest_on_tri row by row (Ericson 5.1.5), the same regions in the same order."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    with np.errstate(divide="ignore", invalid="ignore"):
        den = 1.0 / (va + vb + vc)
        out = a + ab * (vb * den)[:, None] + ac * (vc * den)[:, None]
        w6 = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        r6 = b + (c - b) * w6[:, None]
        w5 = d2 / (d2 - d6)
        r5 = a + ac * w5[:, None]
        v3 = d1 / (d1 - d3)
        r3 = a + ab * v3[:, None]
    # the highest-priority region last (gm returns at the first that holds)
    for m, r in (((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), r6),
                 ((vb <= 0) & (d2 >= 0) & (d6 <= 0), r5),
                 ((d6 >= 0) & (d5 <= d6), c),
                 ((vc <= 0) & (d1 >= 0) & (d3 <= 0), r3),
                 ((d3 >= 0) & (d4 <= d3), b),
                 ((d1 <= 0) & (d2 <= 0), a)):
        out = np.where(m[:, None], r, out)
    return out


def nearest(ts, pts, max_d=20.0, k0=32):
    """Exact nearest triangle per point: (d, q, k) arrays, k = -1 where none is within max_d."""
    m = len(pts)
    d_out, q_out, k_out = np.full(m, np.inf), np.zeros((m, 3)), np.full(m, -1, dtype=np.int64)
    n = len(ts)
    if n == 0 or m == 0:
        return d_out, q_out, k_out
    cent = (ts.A + ts.B + ts.C) / 3.0
    R = float(np.max(np.maximum(np.maximum(np.linalg.norm(ts.A - cent, axis=1), np.linalg.norm(ts.B - cent, axis=1)),
                                np.linalg.norm(ts.C - cent, axis=1))))
    tree = cKDTree(cent)
    todo = np.arange(m)
    k = min(k0, n)
    while todo.size:
        dk, ik = tree.query(pts[todo], k=k)
        if k == 1:
            dk, ik = dk[:, None], ik[:, None]
        t, kk = ik.shape
        P = np.repeat(pts[todo], kk, axis=0)
        flat = ik.reshape(-1)
        q = closest_on_tris(P, ts.A[flat], ts.B[flat], ts.C[flat])
        d = np.linalg.norm(P - q, axis=1).reshape(t, kk)
        dmin = d.min(axis=1)
        # ties (a shared edge or corner): the lowest triangle index, so the pick does not hang on the tree's order
        tie = d <= dmin[:, None] + 1e-9
        j = np.argmin(np.where(tie, ik, np.iinfo(np.int64).max), axis=1)
        rows = np.arange(t)
        done = (kk >= n) | (dk[:, -1] - R >= dmin) | (dk[:, 0] - R > max_d)
        sel = todo[done]
        d_out[sel] = dmin[done]
        q_out[sel] = q.reshape(t, kk, 3)[rows[done], j[done]]
        k_out[sel] = ik[rows[done], j[done]]
        todo = todo[~done]
        k = min(k * 4, n)
    far = d_out > max_d
    k_out[far] = -1
    return d_out, q_out, k_out


def _signed(ts, pts, d, q, k, align, chain):
    """(s, al, valid) as gm.clearance: inside only behind the face (al <= -align) and nearer the spine than it."""
    valid = k >= 0
    kk = np.where(valid, k, 0)
    nrm = ts.N[kk] if len(ts) else np.zeros((len(pts), 3))
    al = np.where(d > 1e-6, np.einsum("ij,ij->i", _unit(pts - q), nrm), 1.0)
    inside = al <= -align
    if chain is not None:
        inside &= _chain_near(pts, chain)[0] < _chain_near(q, chain)[0]
    return np.where(inside, -d, d), al, valid


def _worst(s, valid, idx, q, ts, k, al):
    """(worst record as gm.clearance's, count < 0, count < 3): the first lowest in arm order."""
    if not valid.any():
        return (None, 0, 0)
    sv = np.where(valid, s, np.inf)
    j = int(np.argmin(sv))
    rec = (float(s[j]), int(idx[j]), tuple(float(x) for x in q[j]), (ts.part[k[j]], int(ts.vi[k[j]])),
           round(float(al[j]), 2))
    return (rec, int(np.sum(valid & (s < 0))), int(np.sum(valid & (s < 3.0))))


class NpEngine:
    """PyEngine's calls on numpy arrays (P: n x 3, T: m x 3)."""

    def __init__(self, cell=2.0, align=0.5):
        self.align = align

    def label_rest(self, P, segs, used):
        P = np.asarray(P, dtype=float)
        used = np.asarray(used, dtype=np.int64)
        X = P[used]
        names = list(segs)
        best_d = np.full(len(X), np.inf)
        best_t = np.zeros(len(X))
        best_n = np.zeros(len(X), dtype=np.int64)
        for si, nm in enumerate(names):
            a, b = (np.asarray(v, dtype=float) for v in segs[nm])
            ab = b - a
            L = ab @ ab
            t = np.clip(((X - a) @ ab) / L, 0.0, 1.0) if L > 1e-12 else np.zeros(len(X))
            d = np.linalg.norm(X - (a + t[:, None] * ab), axis=1)
            m = d < best_d
            best_d, best_t, best_n = np.where(m, d, best_d), np.where(m, t, best_t), np.where(m, si, best_n)
        return {int(i): (names[n], float(t), float(d)) for i, n, t, d in zip(used, best_n, best_t, best_d)}

    def tris(self, P, T, keep, tag, chain):
        P, T = np.asarray(P, dtype=float), np.asarray(T, dtype=np.int64)
        mask = np.zeros(len(P), dtype=bool)
        mask[np.asarray(list(keep), dtype=np.int64)] = True
        T = T[mask[T].all(axis=1)]
        A, B, C = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
        N = _unit(np.cross(B - A, C - A))
        if chain is not None and len(T):
            m = (A + B + C) / 3.0
            o = _unit(m - _chain_near(m, chain)[1])
            N = np.where((np.einsum("ij,ij->i", N, o) < 0)[:, None], -N, N)
        return TS(A, B, C, N, np.full(len(T), tag, dtype=object), T[:, 0].copy())

    def cat(self, sets):
        sets = [s for s in sets if len(s)]
        if not sets:
            return TS.empty()
        return TS(*(np.concatenate([getattr(s, f) for s in sets]) for f in ("A", "B", "C", "N", "part", "vi")))

    def take(self, ts, flags, want):
        m = np.asarray(flags, dtype=bool) == want
        if not len(ts):
            return TS.empty()
        return TS(ts.A[m], ts.B[m], ts.C[m], ts.N[m], ts.part[m], ts.vi[m])

    def n(self, ts):
        return len(ts)

    def flags(self, ts, chain, fwd, front):
        if not len(ts):
            return []
        m = (ts.A + ts.B + ts.C) / 3.0
        ch = np.asarray(chain, dtype=float)
        best_d = np.full(len(m), np.inf)
        best_u, best_c = np.zeros_like(m), np.zeros_like(m)
        for a, b in zip(ch[:-1], ch[1:]):
            ab = b - a
            L = ab @ ab
            t = np.clip(((m - a) @ ab) / L, 0.0, 1.0) if L > 1e-12 else np.zeros(len(m))
            c = a + t[:, None] * ab
            d = np.linalg.norm(m - c, axis=1)
            sel = d < best_d
            best_d = np.where(sel, d, best_d)
            best_c[sel] = c[sel]
            best_u[sel] = np.asarray(gm.norm(tuple(ab)))
        w = m - best_c
        w = w - best_u * np.einsum("ij,ij->i", w, best_u)[:, None]
        f = np.asarray(fwd, dtype=float)[None, :] - best_u * (best_u @ np.asarray(fwd, dtype=float))[:, None]
        nw, nf = np.linalg.norm(w, axis=1), np.linalg.norm(f, axis=1)
        ok = (nw >= 1e-9) & (nf >= 1e-9)
        with np.errstate(divide="ignore", invalid="ignore"):
            cosv = np.clip(np.einsum("ij,ij->i", w, f) / (nw * nf), -1.0, 1.0)
        deg = np.where(ok, np.degrees(np.arccos(np.where(ok, cosv, 1.0))), 0.0)
        return list(deg <= front)

    def clear(self, ts, idx, P, max_d, chain):
        idx = np.asarray(idx, dtype=np.int64)
        pts = np.asarray(P, dtype=float)[idx]
        d, q, k = nearest(ts, pts, max_d)
        s, al, valid = _signed(ts, pts, d, q, k, self.align, chain)
        return _worst(s, valid, idx, q, ts, k, al)

    def zclear(self, full, zof, zones, idx, P, max_d, chain):
        idx = np.asarray(idx, dtype=np.int64)
        pts = np.asarray(P, dtype=float)[idx]
        d, q, k = nearest(full, pts, max_d)
        s, al, valid = _signed(full, pts, d, q, k, self.align, chain)
        zof = np.asarray(zof, dtype=object)
        inside = valid & (s < 0)
        izone = np.where(inside, zof[np.where(k >= 0, k, 0)] if len(zof) else "", "")
        out = {}
        for z, ts in zones.items():
            dz, qz, kz = nearest(ts, pts, max_d)
            vz = kz >= 0
            kk = np.where(vz, kz, 0)
            nz = ts.N[kk] if len(ts) else np.zeros((len(pts), 3))
            alz = np.where(dz > 1e-6, np.einsum("ij,ij->i", _unit(pts - qz), nz), 1.0)
            use_full = izone == z
            sv = np.where(use_full, s, dz)
            qv = np.where(use_full[:, None], q, qz)
            av = np.where(use_full, al, alz)
            vv = use_full | vz
            if not vv.any():
                out[z] = (None, 0, 0)
                continue
            j = int(np.argmin(np.where(vv, sv, np.inf)))
            if use_full[j]:
                tag = (full.part[k[j]], int(full.vi[k[j]]))
            else:
                tag = (ts.part[kz[j]], int(ts.vi[kz[j]]))
            rec = (float(sv[j]), int(idx[j]), tuple(float(x) for x in qv[j]), tag, round(float(av[j]), 2))
            out[z] = (rec, int(np.sum(vv & (sv < 0))), int(np.sum(vv & (sv < 3.0))))
        return out


def load_dump(dd, meta, rest=None):
    """The arms_dump stage's files -> garment_measure.arms_compute's D (rest: the first frame's ref pose, reused)."""
    import os
    D = {k: meta[k] for k in ("parts", "chain", "assets", "bones", "head", "facing_f", "facing_diag")}
    D["posed"], D["rest_cached"] = {}, []
    if rest is None:
        rest = {"rest": {}, "rest_bones": meta["rest_bones"], "rest_chain": meta["rest_chain"], "tris": {}}
        for n in meta["parts"]:
            nv, nt = meta["counts"][n]
            rest["tris"][n] = np.fromfile(os.path.join(dd, f"tris_{n}.i32"), dtype=np.int32).reshape(nt, 3).astype(np.int64)
            rest["rest"][n] = (np.fromfile(os.path.join(dd, f"rest_{n}.f64"), dtype=np.float64).reshape(nv, 3),
                               rest["tris"][n])
    for n in meta["parts"]:
        nv, nt = meta["counts"][n]
        if n not in rest["tris"] or len(rest["tris"][n]) != nt or len(rest["rest"][n][0]) != nv:
            raise RuntimeError(f"{n}: {nv} verts/{nt} tris now vs the run's first frame: the mesh changed mid-run")
        D["posed"][n] = (np.fromfile(os.path.join(dd, f"posed_{n}.f64"), dtype=np.float64).reshape(nv, 3),
                         rest["tris"][n])
    D["rest"], D["rest_bones"], D["rest_chain"] = rest["rest"], rest["rest_bones"], rest["rest_chain"]
    return D, rest
