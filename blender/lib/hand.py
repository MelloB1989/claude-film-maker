"""A cartoon hand: a soft palm, four sausage fingers and a thumb, posed by joint angles, as a coarse quad cage whose
subdivision surface is the hand (the way hands are box-modelled: clean, even faces, so Line Art draws one smooth line
round them). Pure geometry (no bpy, so it tests under plain Python): toon.Hand turns it into meshes.

The hand's own frame: the wrist joint at the origin, the hand about 1 long (wrist to the middle fingertip, held flat),
the fingers along -Z, the palm facing -Y, the thumb on +X. That is a left hand; a right hand is it mirrored in X.

A pose: {"fingers": [(spread, knuckle, middle, tip) for the index, middle, ring and little fingers],
         "thumb": (out, forward, knuckle, tip)}
in degrees. Spread turns a finger towards the thumb; the three joints curl it towards the palm. The thumb swings out
from the index in the palm's plane, forward out of it, then curls across the palm. "touch": "pinch" (or "pen") solves
the thumb to meet the index fingertip instead. POSES are the named ones; a pose may start from one ({"base": "rest",
"thumb": ...}). Every pose keeps the thumb clear of the fingers (GAP), so the two never run into each other.

Two meshes: the palm with the fingers (one cage: the fingers grow out of the palm's knuckle edge, webbed at the
knuckles; at the top a heel that ends just past the wrist joint, the arm carrying the wrist), and the thumb (its own tube, rooted in the heel of the palm, so its line runs down into the palm the
way a drawn thumb's does).
"""
from __future__ import annotations

import math

# name, knuckle pivot, segment lengths (base, middle, tip), radius at the knuckle, at the tip
FINGERS = (
    ("index", (0.180, 0.0, -0.385), (0.190, 0.125, 0.105), 0.060, 0.053),
    ("middle", (0.060, 0.0, -0.405), (0.210, 0.140, 0.110), 0.061, 0.054),
    ("ring", (-0.060, 0.0, -0.390), (0.190, 0.130, 0.105), 0.059, 0.052),
    ("little", (-0.176, 0.0, -0.355), (0.150, 0.100, 0.090), 0.054, 0.047),
)
# the thumb: its base in the heel of the palm, segment lengths (metacarpal, base, tip), radius at the base, at the tip
THUMB = ((0.10, -0.02, -0.06), (0.19, 0.14, 0.12), 0.076, 0.06)
# the palm cage: knuckle-row columns (x, between the fingers), the wrist and middle rows (z, width scale), half
# thickness; rings are sized a little over the radius they round to (RING), never wider than WEB (half a finger's pitch)
PALM = {"columns": (0.240, 0.120, 0.0, -0.118, -0.232), "rows": ((0.03, 0.76), (-0.2, 0.98)), "half_thick": 0.09,
        "knuckle_above": 0.05, "arch": 0.016, "wrist": 0.62}
RING, WEB = 1.08, 0.06
GAP = 0.012     # the thumb's least gap to the fingers

POSES = {
    # a hand at rest: fingers gently curled, the little finger most
    "rest": {"fingers": [(3, 12, 20, 10), (0, 16, 26, 12), (-3, 20, 30, 14), (-7, 24, 34, 16)],
             "thumb": (26, 34, 6, 10)},
    # a flat hand, fingers together (waving, pressing, stopping)
    "flat": {"fingers": [(2, 0, 2, 0), (0, 0, 2, 0), (-2, 0, 2, 0), (-5, 0, 2, 0)], "thumb": (32, 10, 0, 4)},
    # an open hand, fingers spread
    "open": {"fingers": [(11, 2, 4, 2), (1, 2, 4, 2), (-8, 2, 4, 2), (-18, 3, 5, 3)], "thumb": (54, 16, 0, 6)},
    # palm up, fingers easy (explaining, offering)
    "cup": {"fingers": [(6, 18, 22, 8), (0, 22, 26, 10), (-5, 26, 30, 12), (-11, 30, 34, 14)], "thumb": (46, 18, 0, 8)},
    # the index out, the rest curled, the thumb over the middle finger
    "point": {"fingers": [(2, 0, 4, 2), (-2, 86, 100, 56), (-4, 90, 100, 56), (-6, 94, 100, 56)],
              "thumb": (6, 58, 26, 22)},
    "fist": {"fingers": [(0, 86, 100, 56), (-1, 88, 100, 56), (-3, 90, 100, 56), (-5, 94, 100, 56)],
             "thumb": (4, 62, 32, 26)},
    # round a bar or a handle (anchor "grip": the channel through the fingers, along X)
    "grip": {"fingers": [(0, 52, 62, 36), (-1, 55, 64, 38), (-3, 58, 66, 40), (-5, 62, 68, 42)],
             "thumb": (10, 64, 22, 18)},
    # round a cup or a bottle (anchor "grip", along X)
    "wrap": {"fingers": [(0, 35, 45, 30), (-1, 37, 47, 32), (-3, 39, 49, 34), (-5, 42, 51, 36)],
             "thumb": (18, 60, 10, 10)},
    # carrying by a handle: the fingers hooked, the thumb easy
    "hook": {"fingers": [(0, 18, 80, 46), (-1, 20, 84, 48), (-3, 22, 86, 50), (-5, 24, 88, 52)],
             "thumb": (24, 28, 4, 6)},
    # the thumb and index tips together (a match, a thread); the other fingers tucked
    "pinch": {"fingers": [(0, 36, 46, 20), (-2, 50, 64, 34), (-4, 60, 76, 42), (-7, 68, 82, 46)],
              "thumb": (30, 50, 10, 10), "touch": "pinch"},
    # holding a pen to write: index and thumb on the pen, the middle finger under it, the rest tucked
    "pen": {"fingers": [(2, 30, 30, 10), (-1, 40, 54, 28), (-4, 62, 80, 46), (-8, 70, 86, 50)],
            "thumb": (30, 46, 8, 8), "touch": "pen"},
    # palm down on a surface, fingers easy
    "table": {"fingers": [(7, 6, 10, 4), (0, 7, 11, 4), (-6, 8, 12, 5), (-13, 9, 13, 6)], "thumb": (42, 8, 0, 2)},
}
ANCHOR_OF = {"grip": "grip", "wrap": "grip", "fist": "grip", "hook": "grip", "pinch": "pinch", "pen": "pinch", "point": "tip"}


# ---- vectors (tuples) ----
def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = length(a)
    return mul(a, 1.0 / n) if n > 1e-12 else a


def rotate(v, axis, deg):
    """v turned deg degrees about axis (right-handed)."""
    k = unit(axis)
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return add(add(mul(v, c), mul(cross(k, v), s)), mul(k, dot(k, v) * (1 - c)))


def toward(v, target, deg):
    """v turned deg degrees towards the direction target."""
    ax = cross(v, target)
    if length(ax) < 1e-9:
        return v
    return rotate(v, ax, deg)


# ---- poses ----
def resolve(pose) -> dict:
    """A pose by name or dict (with an optional "base") as {"fingers": [4 x 4 angles], "thumb": (4 angles), "touch"}."""
    if isinstance(pose, str):
        if pose not in POSES:
            raise KeyError(f"hand: no pose '{pose}' (known: {sorted(POSES)})")
        pose = POSES[pose]
    base = resolve(pose["base"]) if "base" in pose else {"fingers": POSES["rest"]["fingers"], "thumb": POSES["rest"]["thumb"]}
    out = {"fingers": [tuple(float(x) for x in f) for f in pose.get("fingers", base["fingers"])],
           "thumb": tuple(float(x) for x in pose.get("thumb", base["thumb"])),
           "touch": pose.get("touch", base.get("touch") if "base" in pose else None)}
    if len(out["fingers"]) != 4 or any(len(f) != 4 for f in out["fingers"]) or len(out["thumb"]) != 4:
        raise ValueError("hand: a pose has 4 fingers of (spread, knuckle, middle, tip) and a thumb of 4 angles")
    if out["touch"]:
        out["thumb"] = solve_touch(out, out["touch"])
    out["thumb"] = clear_thumb(out)
    return out


def clear_thumb(p):
    """The pose's thumb, lifted forward and uncurled as little as will keep it GAP clear of the fingers."""
    o, f, k, t = p["thumb"]

    def gap(th):
        return _thumb_gap({**p, "thumb": th})
    if gap((o, f, k, t)) >= GAP:
        return (o, f, k, t)
    tries = sorted(((df, dk) for df in range(0, 42, 2) for dk in range(0, 32, 2)), key=lambda d: d[0] ** 2 + d[1] ** 2)
    for df, dk in tries:
        th = (o, f + df, max(0.0, k - dk), max(0.0, t - dk))
        if gap(th) >= GAP:
            return th
    return (o, f, k, t)


def chain(base, d, f, lengths, bends):
    """A digit's joint points from base along d, bending towards f (deg) before each segment, and each segment's
    frame (direction, curl direction)."""
    pts, frames = [base], []
    p = base
    for seg, bend in zip(lengths, bends):
        if bend:
            ax = cross(d, f)
            d, f = rotate(d, ax, bend), rotate(f, ax, bend)
        p = add(p, mul(d, seg))
        pts.append(p)
        frames.append((d, f))
    return pts, frames


def radii(r0, r1, lengths):
    total = sum(lengths)
    out, acc = [r0], 0.0
    for seg in lengths:
        acc += seg
        out.append(r0 + (r1 - r0) * acc / total)
    return out


def finger(i, angles):
    """(joint points, radii, segment frames) of finger i posed by (spread, knuckle, middle, tip)."""
    _, base, lengths, r0, r1 = FINGERS[i]
    spread, k, m, t = angles
    d = rotate((0.0, 0.0, -1.0), (0.0, -1.0, 0.0), spread)
    pts, frames = chain(base, d, (0.0, -1.0, 0.0), lengths, (k, m, t))
    return pts, radii(r0, r1, lengths), frames


def thumb(angles):
    """(joint points: base, knuckle, middle joint, tip; radii; segment frames) of the thumb."""
    base, lengths, r0, r1 = THUMB
    out, fwd, k, t = angles
    d = rotate((0.0, 0.0, -1.0), (0.0, -1.0, 0.0), out)
    d = toward(d, (0.0, -1.0, 0.0), fwd)
    across = unit((-1.0, -0.35, 0.0))
    f = unit(sub(across, mul(d, dot(across, d))))
    pts, frames = chain(base, d, f, lengths, (0.0, k, t))
    return pts, radii(r0, r1, lengths), frames


def solve_touch(p, kind="pinch"):
    """Thumb angles that bring the thumb tip onto the index fingertip's pad (pen: a pen's width off it)."""
    ipts, irs, ifr = finger(0, p["fingers"][0])
    rt = THUMB[3]
    gap = irs[-1] + rt + (0.07 if kind == "pen" else GAP + 0.004)
    target = add(ipts[-1], add(mul(ifr[-1][1], gap), mul(ifr[-1][0], -0.02)))

    def err(a):
        return length(sub(thumb((a[0], a[1], a[2], a[2] * 0.8))[0][-1], target))
    best = min(((o, f_, k) for o in range(-10, 75, 5) for f_ in range(0, 105, 5) for k in range(0, 75, 5)), key=err)
    step = 2.5
    while step > 0.2:
        cand = [(best[0] + a * step, best[1] + b * step, best[2] + c * step)
                for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)]
        best = min(cand, key=err)
        step /= 2
    return (best[0], best[1], best[2], best[2] * 0.8)


def capsules(p) -> list:
    """(a, b, ra, rb) of every finger and thumb segment of a resolved pose; the thumb's three last."""
    out = []
    for i in range(4):
        pts, rs, _ = finger(i, p["fingers"][i])
        out += [(pts[j], pts[j + 1], rs[j], rs[j + 1]) for j in range(3)]
    tpts, trs, _ = thumb(p["thumb"])
    return out + [(tpts[j], tpts[j + 1], trs[j], trs[j + 1]) for j in range(3)]


def thumb_gap(pose) -> float:
    """The narrowest gap between the thumb's two last segments and the fingers' two last."""
    return _thumb_gap(resolve(pose))


def _thumb_gap(p) -> float:
    caps = capsules(p)
    th = caps[-2:]
    fing = [c for i, c in enumerate(caps[:12]) if i % 3]
    return min(_cap_gap(a, b) for a in th for b in fing)


def _cap_gap(c1, c2, n=12):
    """Gap between two capsules (sampled along the first)."""
    a, b, ra, rb = c1
    best = 1e9
    for k in range(n + 1):
        t = k / n
        q = add(a, mul(sub(b, a), t))
        r = ra + (rb - ra) * t
        a2, b2, ra2, rb2 = c2
        ab = sub(b2, a2)
        u = max(0.0, min(1.0, dot(sub(q, a2), ab) / max(dot(ab, ab), 1e-12)))
        best = min(best, length(sub(q, add(a2, mul(ab, u)))) - r - (ra2 + (rb2 - ra2) * u))
    return best


# ---- the cage ----
def _ring(c, d, f, w, h):
    """Four points round c across direction d (w to the sides, h towards f), anticlockwise about d."""
    s = unit(cross(f, d))
    return [add(add(c, mul(s, w)), mul(f, h)), add(add(c, mul(s, -w)), mul(f, h)),
            add(add(c, mul(s, -w)), mul(f, -h)), add(add(c, mul(s, w)), mul(f, -h))]


def _joint(c, fa, fb, a):
    """A ring at a joint between segment frames fa and fb: on the bisector, deepened so a bend keeps its thickness."""
    d = unit(add(fa[0], fb[0]))
    f = unit(add(fa[1], fb[1]))
    k = 1.0 / max(0.6, dot(fa[0], d))
    return _ring(c, d, f, a[0], a[1] * k)


def _size(r, wide=True):
    return (min(r * RING, WEB) if wide else r * RING, r * RING)


def _digit_rings(pts, rs, frames, start_frame, wide=True):
    """The rings of a finger or thumb after its root: a joint ring at each joint, one mid-segment, then the tip and a
    small dome ring beyond it (the last ring is capped). wide False: not held to a finger's pitch (the thumb)."""
    out = [_joint(pts[0], start_frame, frames[0], _size(rs[0], wide))]
    for j, (d, f) in enumerate(frames):
        mid = add(pts[j], mul(sub(pts[j + 1], pts[j]), 0.5))
        out.append(_ring(mid, d, f, *_size((rs[j] + rs[j + 1]) / 2, wide)))
        if j + 1 < len(frames):
            out.append(_joint(pts[j + 1], frames[j], frames[j + 1], _size(rs[j + 1], wide)))
    d, f = frames[-1]
    out.append(_ring(pts[-1], d, f, *_size(rs[-1], wide)))
    rt = rs[-1]
    out.append(_ring(add(pts[-1], mul(d, rt * 0.8)), d, f, *(x * 0.5 for x in _size(rt, wide))))
    return out


class _Mesh:
    def __init__(self):
        self.verts, self.faces = [], []

    def v(self, co):
        self.verts.append(tuple(co))
        return len(self.verts) - 1

    def loop(self, pts):
        return [self.v(p) for p in pts]

    def bridge(self, a, b):
        """Quads joining loop a to loop b (same length), b turned (and if need be reversed) to line up with a."""
        n = len(a)
        cands = [[b[(i + o) % n] for i in range(n)] for o in range(n)]
        cands += [list(reversed(c)) for c in cands]
        b = min(cands, key=lambda c: sum(length(sub(self.verts[a[i]], self.verts[c[i]])) for i in range(n)))
        for i in range(n):
            self.faces.append((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
        return b

    def tube(self, base, rings):
        """Loops through rings from the base loop, the last one capped."""
        cur = base
        for r in rings:
            cur = self.bridge(cur, self.loop(r))
        self.faces.append(tuple(cur))


def cage(pose, detail="full") -> dict:
    """The posed hand as a coarse closed quad mesh {"hand": (verts, faces)}; its subdivision surface (two or three
    levels) is the hand. Faces are not consistently wound (recalculate normals).
    detail "mitten": the four fingers as one (curled as the middle finger), for a hand small on screen, where four
    fingers' worth of lines would knot into a blot."""
    p = resolve(pose)
    m = _Mesh()
    cols, ht = PALM["columns"], PALM["half_thick"]
    pz = [f[1][2] for f in FINGERS]
    kz = [pz[0] + 0.02] + [(pz[i - 1] + pz[i]) / 2 for i in range(1, 4)] + [pz[3] + 0.02]
    G = {}
    rows = [*PALM["rows"], (None, 1.0)]
    for k, (z, wk) in enumerate(rows):
        for j, cx in enumerate(cols):
            arch = PALM["arch"] * (1 - (cx / cols[0]) ** 2)
            zz = kz[j] + PALM["knuckle_above"] if z is None else z
            G["F", k, j] = m.v((cx * wk, -ht, zz))
            G["B", k, j] = m.v((cx * wk, ht + arch, zz))
    # the thumb grows from the palm's corner by the wrist: from its front face when it comes forward, from its side
    # when it reaches out (whichever face it leaves more squarely), so its root never folds back over the palm
    tpts, trs, tframes = thumb(p["thumb"])
    front = [G["F", 0, 0], G["F", 1, 0], G["F", 1, 1], G["F", 0, 1]]
    side = [G["F", 0, 0], G["B", 0, 0], G["B", 1, 0], G["F", 1, 0]]

    def centre(q):
        return mul(add(add(m.verts[q[0]], m.verts[q[1]]), add(m.verts[q[2]], m.verts[q[3]])), 0.25)
    use_side = dot(unit(sub(tpts[1], centre(side))), (1, 0, 0)) > dot(unit(sub(tpts[1], centre(front))), (0, -1, 0))
    for k in range(2):
        for j in range(4):
            if (k, j) != (0, 0) or use_side:
                m.faces.append((G["F", k, j], G["F", k + 1, j], G["F", k + 1, j + 1], G["F", k, j + 1]))
            m.faces.append((G["B", k, j], G["B", k, j + 1], G["B", k + 1, j + 1], G["B", k + 1, j]))
        for j in (0, 4):
            if (k, j) != (0, 0) or not use_side:
                m.faces.append((G["F", k, j], G["B", k, j], G["B", k + 1, j], G["F", k + 1, j]))
    palm_frame = ((0.0, 0.0, -1.0), (0.0, -1.0, 0.0))
    if detail == "mitten":
        # the fingers as one: a wide tube along the middle finger's curl, as broad as the knuckles; an index posed
        # apart from the rest (pointing) keeps its own
        lone = sum(abs(a - b) for a, b in zip(p["fingers"][0][1:], p["fingers"][1][1:])) > 60
        j0 = 1 if lone else 0
        if lone:
            pts, rs, frames = finger(0, p["fingers"][0])
            m.tube([G["F", 2, 0], G["F", 2, 1], G["B", 2, 1], G["B", 2, 0]], _digit_rings(pts, rs, frames, palm_frame))
        pts, rs, frames = finger(1 if not lone else 2, p["fingers"][1 if not lone else 2])
        base = [G["F", 2, j] for j in range(j0, 5)] + [G["B", 2, j] for j in reversed(range(j0, 5))]
        n_ = 5 - j0
        xs = [1.0 - 2.0 * i / (n_ - 1) for i in range(n_)]
        mid_x = (cols[j0] + cols[4]) / 2
        w0 = (cols[j0] - cols[4]) / 2 * 0.9
        pts = [(q[0] - pts[0][0] + mid_x, q[1], q[2]) for q in pts]      # the curl centred on the mitten
        rings = []

        def mring(c, d, f, w, h):
            s_ = unit(cross(f, d))
            return ([add(add(c, mul(s_, w * x)), mul(f, h)) for x in xs] +
                    [add(add(c, mul(s_, w * x)), mul(f, -h)) for x in reversed(xs)])
        for j, (d, f) in enumerate(frames):
            if j:
                fa, fb = frames[j - 1], frames[j]
                db, fbis = unit(add(fa[0], fb[0])), unit(add(fa[1], fb[1]))
                rings.append(mring(pts[j], db, fbis, w0 * (1 - 0.07 * j), rs[j] * RING / max(0.6, dot(fa[0], db))))
            mid = add(pts[j], mul(sub(pts[j + 1], pts[j]), 0.5))
            rings.append(mring(mid, d, f, w0 * (1 - 0.07 * (j + 0.5)), (rs[j] + rs[j + 1]) / 2 * RING))
        d, f = frames[-1]
        rings.append(mring(pts[-1], d, f, w0 * 0.78, rs[-1] * RING))
        rings.append(mring(add(pts[-1], mul(d, rs[-1] * 0.8)), d, f, w0 * 0.55, rs[-1] * RING * 0.5))
        m.tube(base, rings)
    else:
        for i in range(4):
            pts, rs, frames = finger(i, p["fingers"][i])
            base = [G["F", 2, i], G["F", 2, i + 1], G["B", 2, i + 1], G["B", 2, i]]
            m.tube(base, _digit_rings(pts, rs, frames, palm_frame))
    # the heel: the palm's top edge rounded off just past the wrist joint (the arm carries the wrist itself)
    top = [G["F", 0, j] for j in range(5)] + [G["B", 0, j] for j in reversed(range(5))]
    w = PALM["wrist"] / PALM["rows"][0][1]
    m.tube(top, [[(m.verts[i][0] * w, m.verts[i][1] * 0.9, 0.09) for i in top]])
    # the thumb, out of that face (the thenar mound forms where it leaves), from its knuckle on
    pts, rs, frames = tpts, trs, tframes
    base = side if use_side else front
    c = centre(base)
    d = unit(sub(pts[1], c))
    f = unit(sub(frames[0][1], mul(d, dot(frames[0][1], d))))
    mound = _ring(mul(add(c, pts[1]), 0.5), d, f, *(x * 1.05 for x in _size(rs[0], False)))   # the thenar
    m.tube(base, [mound] + _digit_rings(pts[1:], rs[1:], frames[1:], frames[0], wide=False))
    return {"hand": (m.verts, m.faces)}


# ---- holding ----
def _seg_dist(c, a, b):
    ab = sub(b, a)
    t = max(0.0, min(1.0, dot(sub(c, a), ab) / max(dot(ab, ab), 1e-12)))
    return length(sub(c, add(a, mul(ab, t))))


def _inside(pt, poly):
    """Point (y, z) inside polygon [(y, z)] (even-odd)."""
    y, z = pt
    n, inside = len(poly), False
    for i in range(n):
        (y1, z1), (y2, z2) = poly[i], poly[(i + 1) % n]
        if (z1 > z) != (z2 > z) and y < y1 + (z - z1) * (y2 - y1) / (z2 - z1):
            inside = not inside
    return inside


def anchor(pose, name=None):
    """A point to hold things by, in the hand's frame (x, y, z) and its clear radius:
    grip: the channel the curled fingers close round (a bar through it runs along X); pinch: between the thumb and
    index tips; tip: the index fingertip; palm: on the palm's face. name None: the pose's own (ANCHOR_OF, else palm)."""
    key = pose if isinstance(pose, str) else None
    p = resolve(pose)
    name = name or ANCHOR_OF.get(key, "palm")
    ht = PALM["half_thick"] * 0.85        # the subdivided palm's face lies inside its cage
    bottom = -0.43
    if name == "tip":
        pts, rs, frames = finger(0, p["fingers"][0])
        return add(pts[-1], mul(frames[-1][0], rs[-1])), 0.0
    if name == "pinch":
        ipts, irs, _ = finger(0, p["fingers"][0])
        tpts, trs, _ = thumb(p["thumb"])
        return mul(add(ipts[-1], tpts[-1]), 0.5), max(0.0, (length(sub(ipts[-1], tpts[-1])) - irs[-1] - trs[-1]) / 2)
    if name == "palm":
        return (0.02, -ht - 0.01, -0.21), 0.0
    if name != "grip":
        raise KeyError(f"hand: no anchor '{name}' (grip, pinch, tip, palm)")
    caps = capsules(p)
    mid = finger(1, p["fingers"][1])[0]
    x = mid[0][0]
    # the channel: closed by the palm's face just above the knuckles, the middle finger and back from its tip
    poly = [(-ht, bottom + 0.2)] + [(q[1], q[2]) for q in mid]
    best, clear = None, -1.0
    for iy in range(80):
        for iz in range(120):
            c = (x, -ht - 0.6 * iy / 79, 0.0 - 1.1 * iz / 119)
            if not _inside((c[1], c[2]), poly):
                continue
            dmin = -ht - c[1] if c[2] > bottom else length(sub(c, (x, 0.0, bottom))) - ht
            for a, b, ra, rb in caps:
                dmin = min(dmin, _seg_dist(c, a, b) - (ra + rb) / 2)
            if dmin > clear:
                best, clear = c, dmin
    if best is None:
        raise ValueError("hand: this pose closes round nothing (no grip)")
    return best, clear
