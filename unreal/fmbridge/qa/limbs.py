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


# --- hands in the shot's frame (round 7: 'the gestures happen BELOW the MCU frame'; the orchestrator) --------------
HAND_LINES = {"MCU": 0.6, "CU": 0.1, "WIDE": 0.95}  # share of speaking frames, by camera kind
PARTIAL_KINDS = ("CU",)  # the orchestrator (08 Nov): in a CU a hand counts when at least PARTLY visible


def cam_kind(camera: str) -> str:
    """CAM_MCU / CAM_MCU_L -> MCU, CAM_CU -> CU, CAM_WIDE -> WIDE (by name)."""
    c = camera.upper()
    return "WIDE" if "WIDE" in c else "CU" if "_CU" in c and "MCU" not in c else "MCU"


def hand_in(points_px: list, w: int, h: int, margin: int = 0) -> bool:
    """A hand is fully in frame when every one of its points (wrist + fingertips, projected) is inside the picture
    and in front of the lens."""
    return bool(points_px) and all(z > 0 and margin <= x < w - margin and margin <= y < h - margin
                                   for x, y, z in points_px)


def hand_part(points_px: list, w: int, h: int) -> bool:
    """A hand is at least PARTLY in frame when any of its points is inside the picture and in front of the lens."""
    return any(z > 0 and 0 <= x < w and 0 <= y < h for x, y, z in points_px)


def hands_fracs(rows: dict) -> dict:
    """rows: {frame: {"camera": name, "in": bool (>= 1 hand fully in frame), "part": bool (>= 1 hand partly)}} ->
    {kind: {"frac", "n", "line", "cameras", "rule"}} per camera kind; a CU counts a partly visible hand."""
    out = {}
    for f, r in rows.items():
        k = cam_kind(r["camera"])
        o = out.setdefault(k, {"in": 0, "n": 0, "line": HAND_LINES[k], "cameras": set()})
        o["n"] += 1
        o["in"] += int(bool(r.get("part", r["in"]) if k in PARTIAL_KINDS else r["in"]))
        o["cameras"].add(r["camera"])
    return {k: {"frac": round(o["in"] / o["n"], 3), "n": o["n"], "line": o["line"], "cameras": sorted(o["cameras"]),
                "rule": "partly visible" if k in PARTIAL_KINDS else "fully in frame"} for k, o in out.items()}


# --- resting hands vs the chest (round 7: 'both hands hover at the TOP OF HER CHEST ... like claws'; the orchestrator) --
def _t_raw(p, a, b) -> float:
    ab = [b[i] - a[i] for i in range(3)]
    L2 = sum(c * c for c in ab) or 1e-9
    return sum((p[i] - a[i]) * ab[i] for i in range(3)) / L2


def torso_cloud(points, torso, limbs, *, torso_r: float = 30.0, limb_r: float = 9.0, fingers=(), finger_r: float = 3.5)\
        -> list:
    """The torso surface points: within torso_r of the spine segment (spine_01 -> neck_01) AND projecting onto it
    (unclamped t in [0, 1]: the lap and thighs below the pelvis never count), and not within limb_r of any limb
    segment (upper arms, forearms) nor within finger_r of any FINGER segment (hand -> each fingertip: the other hand's
    fingers are not chest; agent-06 found the first version measuring hand-to-hand on her 'hands loosely together'
    rest)."""
    out = []
    for p in points:
        if not 0.0 <= _t_raw(p, *torso) <= 1.0 or seg(p, *torso)[1] > torso_r:
            continue
        if any(seg(p, *ls)[1] <= limb_r for ls in limbs) or any(seg(p, *fs)[1] <= finger_r for fs in fingers):
            continue
        out.append(p)
    return out


def nearest(points, cloud, *, cell: float = 4.0, reach: float = 40.0) -> dict:
    """{"cm": the min distance from any of `points` to the cloud (capped at reach), "at": that point}."""
    if not points or not cloud:
        return {"cm": None, "error": f"{len(points)} hand / {len(cloud)} torso points"}
    grid = {}
    for q in cloud:
        grid.setdefault(tuple(int(math.floor(c / cell)) for c in q), []).append(q)
    k = int(math.ceil(reach / cell))
    best, at = reach, None
    for p in points:
        cx, cy, cz = (int(math.floor(c / cell)) for c in p)
        for dx in range(-k, k + 1):
            for dy in range(-k, k + 1):
                for dz in range(-k, k + 1):
                    for q in grid.get((cx + dx, cy + dy, cz + dz), ()):
                        d = math.dist(p, q)
                        if d < best:
                            best, at = d, p
    return {"cm": round(best, 2), "at": [round(c, 1) for c in at] if at else None}
