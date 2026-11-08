"""garment_fast.NpEngine against garment_measure.PyEngine: the same arm numbers on the same synthetic body (needs
numpy + scipy: the tools env).
    cd tools && uv run python ../films/host-studio/reel/r7/test_garment_fast.py"""
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import garment_fast as gf  # noqa: E402
import garment_measure as gm  # noqa: E402
from test_garment_measure import box_torso, sphere  # noqa: E402

SPINE_Z = [20, 26, 32, 38, 44, 50, 56]


def rot(axis, ang):
    x, y, z = gm.norm(axis)
    c, s = math.cos(ang), math.sin(ang)
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def cylinder(a, b, r, rings=24, n=16):
    """Open tube a -> b: (P, T), outward winding."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    u = gm.norm(tuple(b - a))
    e1 = gm.norm(gm.cross(u, (0, 0, 1) if abs(u[2]) < 0.9 else (1, 0, 0)))
    e2 = gm.cross(u, e1)
    P = []
    for i in range(rings + 1):
        c = a + (b - a) * i / rings
        for j in range(n):
            th = 2 * math.pi * j / n
            P.append(tuple(c + r * (math.cos(th) * np.asarray(e1) + math.sin(th) * np.asarray(e2))))
    T = []
    for i in range(rings):
        for j in range(n):
            p0, p1 = i * n + j, i * n + (j + 1) % n
            q0, q1 = p0 + n, p1 + n
            T += [(p0, p1, q1), (p0, q1, q0)]
    m = tuple((a + b) / 2)
    out = []
    for t in T:
        nn = gm.tri_normal(*(P[i] for i in t))
        cen = tuple(sum(P[i][k] for i in t) / 3 for k in range(3))
        w = gm.sub(cen, m)
        w = gm.sub(w, tuple(x * gm.dot(w, u) for x in u))
        out.append(t if gm.dot(nn, w) > 0 else (t[0], t[2], t[1]))
    return P, out


def body(pose):
    """A torso sphere (r 12 at z 40) + two upper-arm tubes; pose: {side: elbow point}, rest = A-pose."""
    sh = {"l": (0.0, -15.0, 55.0), "r": (0.0, 15.0, 55.0)}
    rest_el = {"l": (0.0, -31.0, 36.0), "r": (0.0, 31.0, 36.0)}
    tP, tT = sphere((0, 0, 40), 12.0, 24)
    P, T, arm_ix = list(tP), list(tT), {}
    for sd in ("r", "l"):
        aP, aT = cylinder(sh[sd], rest_el[sd], 3.5)
        off = len(P)
        el = pose.get(sd, rest_el[sd])
        v0 = np.subtract(rest_el[sd], sh[sd])
        v1 = np.subtract(el, sh[sd])
        ax = np.cross(v0, v1)
        ang = math.atan2(np.linalg.norm(ax), v0 @ v1)
        Rm = rot(tuple(ax), ang) if np.linalg.norm(ax) > 1e-9 else np.eye(3)
        P += [tuple(np.asarray(sh[sd]) + Rm @ (np.asarray(p) - sh[sd])) for p in aP]
        T += [(a + off, b + off, c + off) for a, b, c in aT]
        arm_ix[sd] = (off, len(P))
    bones = {}
    for sd in ("r", "l"):
        el = pose.get(sd, rest_el[sd])
        bones[f"clavicle_{sd}"] = (0.0, 3.0 * (1 if sd == "r" else -1), 55.0)
        bones[f"upperarm_{sd}"] = sh[sd]
        bones[f"lowerarm_{sd}"] = el
        hand = tuple(np.asarray(el) + (np.asarray(el) - sh[sd]) * 0.9)
        bones[f"hand_{sd}"] = hand
        bones[f"middle_01_{sd}"] = tuple(np.asarray(hand) + (0, 0, -8))
        bones[f"thigh_{sd}"] = (0.0, 8.0 * (1 if sd == "r" else -1), 18.0)
        bones[f"calf_{sd}"] = (20.0, 8.0 * (1 if sd == "r" else -1), 15.0)
        bones[f"foot_{sd}"] = (20.0, 8.0 * (1 if sd == "r" else -1), -20.0)
    chain = [(0.0, 0.0, float(z)) for z in SPINE_Z]
    return P, T, bones, chain


def segs_of(bones, chain):
    s = {f"spine:{a}": (chain[i], chain[i + 1]) for i, a in enumerate(gm.SPINE[:-1])}
    s["neck"] = (chain[-1], (0.0, 0.0, 70.0))
    for sd in ("l", "r"):
        s[f"clavicle_{sd}"] = (bones[f"clavicle_{sd}"], bones[f"upperarm_{sd}"])
        s[f"upperarm_{sd}"] = (bones[f"upperarm_{sd}"], bones[f"lowerarm_{sd}"])
        s[f"lowerarm_{sd}"] = (bones[f"lowerarm_{sd}"], bones[f"hand_{sd}"])
        s[f"hand_{sd}"] = (bones[f"hand_{sd}"], bones[f"middle_01_{sd}"])
        s[f"thigh_{sd}"] = (bones[f"thigh_{sd}"], bones[f"calf_{sd}"])
        s[f"calf_{sd}"] = (bones[f"calf_{sd}"], bones[f"foot_{sd}"])
    return s


def make_D(pose, as_np):
    rP, rT, rb, rc = body({})
    pP, pT, pb, pc = body(pose)
    tP, tT = sphere((0, 0, 40), 12.6, 20)
    tT = [(a, c, b) for a, b, c in tT]   # a garment shell's inner face points in: the chain turns it out
    conv = (lambda P: np.asarray(P, float)) if as_np else (lambda P: P)
    convT = (lambda T: np.asarray(T, np.int64)) if as_np else (lambda T: T)
    segs = segs_of(rb, rc)
    rest_bones = {n: (segs, {sd: rb[f"upperarm_{sd}"] for sd in ("l", "r")}) for n in ("Body", "Top")}
    return {"parts": ["Body", "Top"],
            "posed": {"Body": (conv(pP), convT(pT)), "Top": (conv(tP), convT(tT))},
            "rest": {"Body": (conv(rP), convT(rT)), "Top": (conv(tP), convT(tT))},
            "rest_bones": rest_bones, "rest_chain": {"Body": rc, "Top": rc}, "chain": pc,
            "assets": {"Body": "/Game/T/Body", "Top": "/Game/T/Top"},
            "bones": {k: pb[k] for k in ("clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r", "lowerarm_l",
                                         "lowerarm_r")},
            "head": [0, 0, 70], "facing_f": (1.0, 0.0, 0.0),
            "facing_diag": {"facing_vs_actor_deg": 0, "facing_flipped_by_knees": False}}


def flat(d, pre=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flat(v, f"{pre}{k}."))
        else:
            out[f"{pre}{k}"] = v
    return out


def compare(pose, G=None):
    G = G or {}
    t0 = time.time()
    a = gm.arms_compute(make_D(pose, False), G, gm.PyEngine())
    t1 = time.time()
    b = gm.arms_compute(make_D(pose, True), G, gf.NpEngine())
    t2 = time.time()
    fa, fb = flat(a), flat(b)
    diff = {k: (fa.get(k), fb.get(k)) for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)}
    return a, b, diff, (t1 - t0, t2 - t1)


def test_closest_on_tris_matches():
    rnd = random.Random(7)
    pts, A, B, C = [], [], [], []
    for _ in range(3000):
        A.append([rnd.uniform(-5, 5) for _ in range(3)])
        B.append([rnd.uniform(-5, 5) for _ in range(3)])
        C.append([rnd.uniform(-5, 5) for _ in range(3)])
        pts.append([rnd.uniform(-9, 9) for _ in range(3)])
    q = gf.closest_on_tris(*(np.asarray(x) for x in (pts, A, B, C)))
    for i in range(len(pts)):
        assert np.allclose(q[i], gm.closest_on_tri(tuple(pts[i]), tuple(A[i]), tuple(B[i]), tuple(C[i])), atol=1e-9)


def test_nearest_is_exact():
    P, T = box_torso()
    sP, sT = sphere((30, 0, 0), 6.0, 20)
    P2 = list(P) + list(sP)
    T2 = list(T) + [(a + len(P), b + len(P), c + len(P)) for a, b, c in sT]
    ents = gm.torso_tris(P2, T2, set(range(len(P2))), "Body")
    ts = gf.NpEngine().tris(np.asarray(P2, float), np.asarray(T2), range(len(P2)), "Body", None)
    grid = gm.TriGrid(ents, 2.0)
    rnd = random.Random(3)
    pts = np.array([[rnd.uniform(-15, 45), rnd.uniform(-20, 20), rnd.uniform(-30, 30)] for _ in range(800)])
    d, q, k = gf.nearest(ts, pts, 20.0)
    for i, p in enumerate(pts):
        h = grid.nearest(tuple(p), 20.0)
        if h is None:
            assert k[i] < 0
        else:
            assert k[i] >= 0 and abs(h[0] - d[i]) < 1e-9


def test_engines_agree_hanging_and_into_the_bust():
    # left arm hanging ~1 cm off her side; right upper arm swung forward into the bust
    a, b, diff, (tp, tn) = compare({"l": (2.0, -17.5, 30.0), "r": (16.0, 4.0, 38.0)})
    assert not diff, diff
    assert a["sides"]["r"]["zones"]["front"]["clear_cm"] < 0          # the 00:44 kind: inside, front zone
    assert a["sides"]["l"]["zones"]["side"]["clear_cm"] > 0           # beside her: outside
    for sd in ("l", "r"):
        assert a["sides"][sd]["rest_clear_cm"] > 0 and a["sides"][sd]["rest_verts_lt0"] == 0
        for z in ("front", "side"):
            assert a["sides"][sd]["zones"][z]["rest_verts_lt0"] == 0
    print(f"hanging/bust: python {tp:.2f} s, numpy {tn:.2f} s; r front {a['sides']['r']['zones']['front']['clear_cm']}"
          f", l side {a['sides']['l']['zones']['side']['clear_cm']}")


def test_engines_agree_rest_pose_and_cache():
    a, b, diff, _ = compare({})
    assert not diff, diff
    D = make_D({"l": (2.0, -17.5, 30.0)}, True)
    cache = {}
    x = gm.arms_compute(D, {}, gf.NpEngine(), cache)
    y = gm.arms_compute(D, {}, gf.NpEngine(), cache)   # second frame from the cache: same numbers
    assert flat(x) == flat(y)


if __name__ == "__main__":
    n = 0
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            n += 1
    print(n, "pass")
