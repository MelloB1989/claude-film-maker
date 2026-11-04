"""Layout math with no engine: boxes, patterns (row, grid, circle), seeded Poisson-disk scatter, resting heights,
snapping and alignment. Pure Python 3.11, shared by the layout ops and their unit tests (and importable client-side).

Units: cm. Boxes are (min, max) corner triples, [x, y, z]. Z is up.
"""
from __future__ import annotations

import fnmatch
import math
import random

Box = tuple  # ((x0, y0, z0), (x1, y1, z1))


def box_from_bounds(origin, extent) -> Box:
    """An actor's (origin, half extent) as returned by get_actor_bounds, as a (min, max) box."""
    o, e = list(origin), [abs(v) for v in extent]
    return (tuple(o[i] - e[i] for i in range(3)), tuple(o[i] + e[i] for i in range(3)))


def box_center(b: Box) -> tuple:
    return tuple((b[0][i] + b[1][i]) / 2 for i in range(3))


def box_size(b: Box) -> tuple:
    return tuple(b[1][i] - b[0][i] for i in range(3))


def overlap_xy(a: Box, b: Box, margin: float = 0.0) -> bool:
    """Whether two boxes overlap seen from above (their footprints intersect by more than `margin` cm)."""
    return all(a[0][i] < b[1][i] - margin and b[0][i] < a[1][i] - margin for i in (0, 1))


def overlap_depth(a: Box, b: Box) -> float:
    """How far two boxes interpenetrate (cm, the smallest axis overlap); 0 when they do not touch."""
    d = [min(a[1][i], b[1][i]) - max(a[0][i], b[0][i]) for i in range(3)]
    return max(0.0, min(d))


def rest_z(moving: Box, supports: list, floor: float | None = 0.0, gap: float = 0.0) -> float | None:
    """The Z offset to add to `moving` so its bottom rests on the highest support under its footprint whose top is
    not above the moving box's own centre (so a shelf above it does not count), or on `floor`. None when nothing
    is under it and there is no floor."""
    cz = box_center(moving)[2]
    tops = [s[1][2] for s in supports if overlap_xy(moving, s) and s[1][2] <= cz + 1e-6]
    if floor is not None:
        tops.append(floor)
    if not tops:
        return None
    return max(tops) + gap - moving[0][2]


def snap(v: float, step: float) -> float:
    return round(v / step) * step if step else v


def row(count: int, start, step) -> list:
    """`count` points from `start` by `step` ([dx, dy, dz] cm)."""
    return [[start[i] + step[i] * k for i in range(3)] for k in range(count)]


def grid(count: int, start, step, cols: int) -> list:
    """`count` points in rows of `cols`: X by step[0] across a row, Y by step[1] between rows, Z constant."""
    cols = max(1, int(cols))
    return [[start[0] + step[0] * (k % cols), start[1] + step[1] * (k // cols), start[2]] for k in range(count)]


def circle(count: int, center, radius: float, start_deg: float = 0.0, arc_deg: float = 360.0) -> list:
    """`count` points on a circle (or an arc) around `center`, counter-clockwise seen from above."""
    full = abs(arc_deg - 360.0) < 1e-9
    n = count if full else max(1, count - 1)
    out = []
    for k in range(count):
        a = math.radians(start_deg + arc_deg * k / n)
        out.append([center[0] + radius * math.cos(a), center[1] + radius * math.sin(a), center[2]])
    return out


def yaw_to(src, dst) -> float:
    """Yaw (degrees) that turns X-forward at `src` toward `dst`."""
    return math.degrees(math.atan2(dst[1] - src[1], dst[0] - src[0]))


def poisson(count: int, region, min_dist: float, seed: int = 0, exclude: list | None = None,
            tries: int = 30) -> list:
    """Up to `count` [x, y] points in `region` ([[x0, y0], [x1, y1]]), no two closer than `min_dist` cm and none in
    an `exclude` rectangle ([[x0, y0], [x1, y1]], e.g. a table's footprint), the same for the same seed (Bridson's
    algorithm on a grid, deterministic). Fewer points come back when the region is full."""
    (x0, y0), (x1, y1) = region
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    rng = random.Random(seed)
    exclude = exclude or []
    cell = min_dist / math.sqrt(2) if min_dist > 0 else max(x1 - x0, y1 - y0, 1.0)
    grid_: dict = {}
    pts: list = []
    active: list = []

    def ok(p):
        if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1):
            return False
        if any(e[0][0] <= p[0] <= e[1][0] and e[0][1] <= p[1] <= e[1][1] for e in exclude):
            return False
        if min_dist <= 0:
            return True
        gx, gy = int((p[0] - x0) / cell), int((p[1] - y0) / cell)
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                q = grid_.get((gx + dx, gy + dy))
                if q is not None and (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 < min_dist ** 2:
                    return False
        return True

    def add(p):
        pts.append(p)
        active.append(p)
        grid_[(int((p[0] - x0) / cell), int((p[1] - y0) / cell))] = p

    for _ in range(tries * 10):  # a first point that is not excluded
        p = [rng.uniform(x0, x1), rng.uniform(y0, y1)]
        if ok(p):
            add(p)
            break
    while active and len(pts) < count:
        i = rng.randrange(len(active))
        base = active[i]
        for _ in range(tries):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(min_dist, 2 * min_dist) if min_dist > 0 else rng.uniform(0, max(x1 - x0, y1 - y0))
            p = [base[0] + r * math.cos(a), base[1] + r * math.sin(a)]
            if ok(p):
                add(p)
                break
        else:
            active.pop(i)
    return [[round(p[0], 3), round(p[1], 3)] for p in pts[:count]]


def jitter(n: int, seed: int, lo: float, hi: float) -> list:
    """n values uniform in [lo, hi], the same for the same seed (a different stream from poisson's)."""
    rng = random.Random(f"jitter:{seed}:{lo}:{hi}")
    return [rng.uniform(lo, hi) if hi > lo else lo for _ in range(n)]


def align(boxes: dict, axis: str, to: str, ref: float | None = None) -> dict:
    """Per label, the offset along `axis` (x|y|z) that lines its box up: `to` min|max|center, on `ref` (cm) or, by
    default, on the extreme (min of mins, max of maxes) or the mean centre of all of them."""
    i = "xyz".index(axis)
    if to not in ("min", "max", "center"):
        raise ValueError(f"align to must be min|max|center, not {to!r}")
    vals = {k: (b[0][i] if to == "min" else b[1][i] if to == "max" else box_center(b)[i]) for k, b in boxes.items()}
    if ref is None:
        ref = (min(vals.values()) if to == "min" else max(vals.values()) if to == "max"
               else sum(vals.values()) / len(vals))
    return {k: ref - v for k, v in vals.items()}


def distribute(boxes: dict, order: list, axis: str, start: float | None = None, end: float | None = None,
               gap: float | None = None) -> dict:
    """Per label (in `order`), the offset along `axis` that spaces the boxes evenly: centres from `start` to `end`
    (default: the first and last box's current centres), or edge to edge `gap` cm apart from the first box."""
    i = "xyz".index(axis)
    c = {k: box_center(boxes[k])[i] for k in order}
    if gap is not None:
        pos, out = boxes[order[0]][0][i] if start is None else start, {}
        for k in order:
            size = boxes[k][1][i] - boxes[k][0][i]
            out[k] = (pos + size / 2) - c[k]
            pos += size + gap
        return out
    s = c[order[0]] if start is None else start
    e = c[order[-1]] if end is None else end
    n = max(1, len(order) - 1)
    return {k: (s + (e - s) * j / n) - c[k] for j, k in enumerate(order)}


def local_to_world(origin, yaw_deg: float, offset) -> list:
    """A point `offset` ([forward, right, up] cm in an actor's yaw frame) from `origin`, in world space."""
    a = math.radians(yaw_deg)
    f, r, u = offset
    return [origin[0] + f * math.cos(a) - r * math.sin(a), origin[1] + f * math.sin(a) + r * math.cos(a),
            origin[2] + u]


def match(label: str, pattern: str) -> bool:
    """Label filter: a glob (`Chair_*`) when it has wildcards, else a case-insensitive substring."""
    if not pattern:
        return True
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatchcase(label.lower(), pattern.lower())
    return pattern.lower() in label.lower()


def numbered(prefix: str, k: int, count: int) -> str:
    """The label of the k-th actor of a pattern: Prefix_00 (two digits; three past 99)."""
    return f"{prefix}_{k:0{max(2, len(str(count - 1)))}d}"
