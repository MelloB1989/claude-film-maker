"""Upper arm vs torso clearance from posed vertices (round 7: 'her right boob is covering the upper limb of her right
hand'; the operator). Pure Python: the editor op (qa.limb_clearance) feeds it posed Body + upper-garment vertices and
bone positions.

Points are split by bone segments: ARM points lie within arm_r cm of the upper arm (shoulder -> elbow), between
arm_t[0] and arm_t[1] along it (the armpit junction excluded); TORSO points lie within torso_r cm of the spine
(spine_03 -> neck_01) and are not arm points. Clearance = min over arm points of the distance to the nearest torso
point, NEGATIVE where the arm point is nearer the spine axis than that torso point (the arm inside the torso's volume:
a breast covering the arm). Distances past `reach` read as reach."""
from __future__ import annotations

import math


def seg(p, a, b) -> tuple:
    """(t along a->b clamped to [0, 1], distance from p to the segment)."""
    ab = [b[i] - a[i] for i in range(3)]
    L2 = sum(c * c for c in ab) or 1e-9
    t = max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / L2))
    q = [a[i] + t * ab[i] for i in range(3)]
    return t, math.dist(p, q)


def classify(points, arm, torso, *, arm_r: float = 9.0, torso_r: float = 30.0, arm_t=(0.35, 0.95)) -> tuple:
    """(arm points, torso points) of `points` for one side: arm = (shoulder, elbow), torso = (spine_03, neck_01)."""
    A, T = [], []
    for p in points:
        t, d = seg(p, *arm)
        if d <= arm_r and arm_t[0] <= t <= arm_t[1]:
            A.append(p)
            continue
        if d <= arm_r:  # the shoulder cap or the elbow: neither side
            continue
        if seg(p, *torso)[1] <= torso_r:
            T.append(p)
    return A, T


def clearance(arm_pts, torso_pts, torso, *, cell: float = 3.0, reach: float = 10.0) -> dict:
    """{"cm": min signed clearance (negative = inside), "at": the worst arm point, "n_arm", "n_torso"}."""
    if not arm_pts or not torso_pts:
        return {"cm": None, "error": f"{len(arm_pts)} arm / {len(torso_pts)} torso points", "n_arm": len(arm_pts),
                "n_torso": len(torso_pts)}
    grid = {}
    for q in torso_pts:
        grid.setdefault(tuple(int(math.floor(c / cell)) for c in q), []).append(q)
    k = int(math.ceil(reach / cell))
    best, at = reach, None
    for p in arm_pts:
        cx, cy, cz = (int(math.floor(c / cell)) for c in p)
        near, dmin = None, reach
        for dx in range(-k, k + 1):
            for dy in range(-k, k + 1):
                for dz in range(-k, k + 1):
                    for q in grid.get((cx + dx, cy + dy, cz + dz), ()):
                        d = math.dist(p, q)
                        if d < dmin:
                            dmin, near = d, q
        if near is None:
            continue
        signed = dmin if seg(p, *torso)[1] >= seg(near, *torso)[1] else -dmin
        if signed < best:
            best, at = signed, p
    return {"cm": round(best, 2), "at": [round(c, 1) for c in at] if at else None, "n_arm": len(arm_pts),
            "n_torso": len(torso_pts)}
