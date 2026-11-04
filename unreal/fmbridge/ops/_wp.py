"""World Partition helpers with no `unreal`: a camera frustum's bounding box, box arithmetic, and picking actor
descriptors. ops/wp.py uses them; the tests import this file as is (fakeunreal.pure)."""
from __future__ import annotations

import math


def rot_axes(pitch: float, yaw: float, roll: float) -> tuple:
    """(forward, right, up) unit vectors of a rotation in degrees, as Unreal's FRotationMatrix builds them
    (X forward, Y right, Z up; left-handed)."""
    p, y, r = (math.radians(a) for a in (pitch, yaw, roll))
    sp, cp, sy, cy, sr, cr = math.sin(p), math.cos(p), math.sin(y), math.cos(y), math.sin(r), math.cos(r)
    fwd = (cp * cy, cp * sy, sp)
    right = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
    up = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
    return fwd, right, up


def frustum_box(loc, rot: dict, fov_deg: float, aspect: float = 16 / 9, far_cm: float = 5000.0,
                near_cm: float = 10.0, pad_cm: float = 0.0) -> tuple:
    """Axis-aligned box [min xyz], [max xyz] around what a camera at `loc` with rotation `rot` ({"pitch", "yaw",
    "roll"}) and horizontal field of view `fov_deg` sees out to `far_cm`, grown by `pad_cm` on every side."""
    f, r, u = rot_axes(rot.get("pitch", 0.0), rot.get("yaw", 0.0), rot.get("roll", 0.0))
    th = math.tan(math.radians(min(max(fov_deg, 1e-3), 179.0)) / 2)
    tv = th / max(aspect, 1e-3)
    pts = []
    for d in (near_cm, far_cm):
        for sx in (-1, 1):
            for sy in (-1, 1):
                pts.append([loc[i] + f[i] * d + r[i] * sx * d * th + u[i] * sy * d * tv for i in range(3)])
    lo = [min(p[i] for p in pts) - pad_cm for i in range(3)]
    hi = [max(p[i] for p in pts) + pad_cm for i in range(3)]
    return lo, hi


def frustum_planes(loc, rot: dict, fov_deg: float, aspect: float = 16 / 9, far_cm: float = 5000.0,
                   near_cm: float = 10.0, pad_cm: float = 0.0) -> list:
    """The 6 planes of a camera frustum as (normal, offset), normals pointing inwards: a point p is inside when
    dot(normal, p) >= offset - pad_cm for every plane."""
    f, r, u = rot_axes(rot.get("pitch", 0.0), rot.get("yaw", 0.0), rot.get("roll", 0.0))
    th = math.tan(math.radians(min(max(fov_deg, 1e-3), 179.0)) / 2)
    tv = th / max(aspect, 1e-3)

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    def norm(v):
        n = math.sqrt(dot(v, v)) or 1.0
        return [x / n for x in v]

    planes = [(list(f), dot(f, loc) + near_cm), ([-x for x in f], -(dot(f, loc) + far_cm))]
    for side, t in ((r, th), (u, tv)):
        for sgn in (1, -1):
            n = norm([f[i] * t - sgn * side[i] for i in range(3)])  # inward normal of the side plane
            planes.append((n, dot(n, loc)))
    return [(n, o - pad_cm) for n, o in planes]


def box_in_frustum(lo, hi, planes) -> bool:
    """Whether a box may be seen: False only when all 8 corners are outside one plane (conservative)."""
    corners = [[(lo, hi)[(k >> i) & 1][i] for i in range(3)] for k in range(8)]
    for n, o in planes:
        if all(sum(n[i] * c[i] for i in range(3)) < o for c in corners):
            return False
    return True


def sphere_box(center, radius_cm: float) -> tuple:
    return [c - radius_cm for c in center], [c + radius_cm for c in center]


def union(boxes) -> tuple:
    boxes = list(boxes)
    return ([min(b[0][i] for b in boxes) for i in range(3)], [max(b[1][i] for b in boxes) for i in range(3)])


def intersects(a, b) -> bool:
    return all(a[0][i] <= b[1][i] and b[0][i] <= a[1][i] for i in range(3))


def box_dict(lo, hi) -> dict:
    return {"min": [round(v, 2) for v in lo], "max": [round(v, 2) for v in hi],
            "size_m": [round((hi[i] - lo[i]) / 100.0, 2) for i in range(3)]}


def summarize(descs: list) -> dict:
    """Counts over actor descriptor dicts ({"grid", "spatial", "loaded", "editor_only", "data_layers"})."""
    grids: dict = {}
    for d in descs:
        grids[d["grid"] or "(none)"] = grids.get(d["grid"] or "(none)", 0) + 1
    return {"actors": len(descs), "loaded": sum(1 for d in descs if d["loaded"]),
            "spatially_loaded": sum(1 for d in descs if d["spatial"]),
            "always_loaded": sum(1 for d in descs if not d["spatial"]),
            "editor_only": sum(1 for d in descs if d["editor_only"]), "grids": grids}
