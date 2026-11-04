"""Foliage scatter maths with no engine: where each instance goes, which mesh, its yaw, scale and tilt, the same for
the same seed. Pure Python 3.11, shared by the foliage ops and their unit tests (and importable client-side).

A scatter is a dict (the foliage.scatter op's arguments):

    {"seed": 7,
     "region": {"rect": [[x0, y0], [x1, y1]]} | {"circle": [cx, cy, r]} | {"ring": [cx, cy, r0, r1]}
               | {"polygon": [[x, y], ...]},
     "meshes": [{"mesh": "/Game/Env/SM_Grass", "weight": 3, "scale": [0.8, 1.2], "tilt_deg": 5,
                 "yaw": "random" | [lo, hi] | fixed, "z_offset_cm": 0, "align_to_normal": false}],
     "density_per_m2": 2.0 | "count": 400,       # how many (density over the region's area)
     "min_dist_cm": 40,                          # spacing (default from the density)
     "exclude": [{"rect": ...} | {"circle": ...}] (+ footprints of actors, resolved by the op),
     "patchiness": 0..1, "patch_cm": 400}       # clumps: thin out where a seeded noise field is low

Points come from _layout.poisson (Bridson, seeded) over the region's bounding rectangle, kept when inside the region
and outside every exclusion; patchiness keeps a point with a probability that follows a smooth value-noise field.
"""
from __future__ import annotations

import hashlib
import json
import math
import random

try:
    from ._layout import poisson
except ImportError:  # imported on its own (tests' fakeunreal.pure, client tools): the sibling by path
    import importlib.util as _ilu
    import os as _os
    import sys as _sys
    _spec = _ilu.spec_from_file_location("fmbridge_pure_ops__layout",
                                         _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_layout.py"))
    _layout = _sys.modules.get("fmbridge_pure_ops__layout") or _ilu.module_from_spec(_spec)
    if "fmbridge_pure_ops__layout" not in _sys.modules:
        _sys.modules["fmbridge_pure_ops__layout"] = _layout
        _spec.loader.exec_module(_layout)
    poisson = _layout.poisson


def region_box(region: dict) -> tuple:
    """The region's bounding rectangle [[x0, y0], [x1, y1]] and its area (cm^2)."""
    if "rect" in region:
        (x0, y0), (x1, y1) = region["rect"]
        x0, x1 = sorted((float(x0), float(x1)))
        y0, y1 = sorted((float(y0), float(y1)))
        return [[x0, y0], [x1, y1]], (x1 - x0) * (y1 - y0)
    if "circle" in region:
        cx, cy, r = (float(v) for v in region["circle"])
        return [[cx - r, cy - r], [cx + r, cy + r]], math.pi * r * r
    if "ring" in region:
        cx, cy, r0, r1 = (float(v) for v in region["ring"])
        r0, r1 = sorted((r0, r1))
        return [[cx - r1, cy - r1], [cx + r1, cy + r1]], math.pi * (r1 * r1 - r0 * r0)
    if "polygon" in region:
        pts = [(float(p[0]), float(p[1])) for p in region["polygon"]]
        if len(pts) < 3:
            raise ValueError("a polygon region needs at least 3 points")
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        area = abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts)))) / 2
        return [[min(xs), min(ys)], [max(xs), max(ys)]], area
    raise ValueError(f"region {region!r}: one of rect, circle, ring, polygon")


def inside(region: dict, x: float, y: float) -> bool:
    if "rect" in region:
        (x0, y0), (x1, y1) = region_box(region)[0]
        return x0 <= x <= x1 and y0 <= y <= y1
    if "circle" in region:
        cx, cy, r = (float(v) for v in region["circle"])
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    if "ring" in region:
        cx, cy, r0, r1 = (float(v) for v in region["ring"])
        r0, r1 = sorted((r0, r1))
        d = (x - cx) ** 2 + (y - cy) ** 2
        return r0 * r0 <= d <= r1 * r1
    if "polygon" in region:  # even-odd ray casting
        pts = region["polygon"]
        c = False
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi, xj, yj = float(pts[i][0]), float(pts[i][1]), float(pts[j][0]), float(pts[j][1])
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                c = not c
            j = i
        return c
    raise ValueError(f"region {region!r}: one of rect, circle, ring, polygon")


def _noise(seed: int, cell: float):
    """A smooth 2D value-noise field 0..1 (bilinear over a seeded lattice with smoothstep), cell `cell` cm."""
    cache: dict = {}

    def lattice(i: int, j: int) -> float:
        k = (i, j)
        if k not in cache:
            cache[k] = random.Random(f"patch:{seed}:{i}:{j}").random()
        return cache[k]

    def at(x: float, y: float) -> float:
        fx, fy = x / cell, y / cell
        i, j = math.floor(fx), math.floor(fy)
        tx, ty = fx - i, fy - j
        sx, sy = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        a = lattice(i, j) + (lattice(i + 1, j) - lattice(i, j)) * sx
        b = lattice(i, j + 1) + (lattice(i + 1, j + 1) - lattice(i, j + 1)) * sx
        return a + (b - a) * sy
    return at


def _excluded(ex: list, x: float, y: float) -> bool:
    for e in ex:
        if inside(e, x, y):
            return True
    return False


def plan(args: dict) -> dict:
    """The instances of a scatter before they meet the ground: {"instances": [{"x", "y", "mesh": index, "yaw",
    "scale": [sx, sy, sz], "tilt": [pitch, roll], "z_offset"}], "area_m2", "target", "min_dist_cm", "counts":
    [per mesh]}. Raises ValueError naming the bad argument."""
    seed = int(args.get("seed", 0))
    region = args.get("region") or {}
    box, area = region_box(region)
    meshes = args.get("meshes") or []
    if not meshes:
        raise ValueError("meshes: give at least one {mesh: /Game/...}")
    for i, m in enumerate(meshes):
        if not isinstance(m, dict) or not str(m.get("mesh", "")).startswith("/"):
            raise ValueError(f"meshes[{i}]: {{mesh: /Game/..., weight, scale: [lo, hi], tilt_deg, yaw}}")
    if "count" in args and args["count"] is not None:
        target = int(args["count"])
    elif args.get("density_per_m2") is not None:
        target = int(round(float(args["density_per_m2"]) * area / 1e4))
    else:
        raise ValueError("give count or density_per_m2")
    if target < 0:
        raise ValueError("count must be >= 0")
    dens = target / max(area / 1e4, 1e-9)
    md = args.get("min_dist_cm")
    min_dist = float(md) if md is not None else (0.5 * 100.0 / math.sqrt(dens) if dens > 0 else 0.0)
    exclude = list(args.get("exclude") or [])
    patch = float(args.get("patchiness", 0.0))
    field = _noise(seed, float(args.get("patch_cm", 400.0))) if patch > 0 else None
    # oversample the bounding box so the region (and the patches) still get their share
    frac = area / max((box[1][0] - box[0][0]) * (box[1][1] - box[0][1]), 1e-9)
    want = int(math.ceil(target / max(frac, 1e-6) / max(1.0 - 0.5 * patch, 0.1) * 1.15)) + 4
    keep: list = []
    for _ in range(4):  # Bridson with one seed extends the same sequence: ask for more until enough survive
        pts = poisson(want, box, min_dist, seed=seed)
        keep = []
        rng_keep = random.Random(f"keep:{seed}")
        for x, y in pts:
            if not inside(region, x, y) or _excluded(exclude, x, y):
                continue
            if field is not None:
                p = (1.0 - patch) + patch * (field(x, y) ** 2) * 2.0
                if rng_keep.random() > min(1.0, p):
                    continue
            keep.append((x, y))
        if len(keep) >= target or len(pts) < want:  # enough, or the box is full at this spacing
            break
        want *= 2
    keep = keep[:target]
    weights = [max(0.0, float(m.get("weight", 1.0))) for m in meshes]
    tot = sum(weights) or 1.0
    rng = random.Random(f"inst:{seed}")
    out = []
    counts = [0] * len(meshes)
    for x, y in keep:
        r = rng.random() * tot
        k = 0
        while k < len(weights) - 1 and r > weights[k]:
            r -= weights[k]
            k += 1
        m = meshes[k]
        sc = m.get("scale", [1.0, 1.0])
        lo, hi = (sc, sc) if isinstance(sc, (int, float)) else sc
        s = rng.uniform(float(lo), float(hi))
        yaw = m.get("yaw", "random")
        if yaw == "random":
            yv = rng.uniform(0.0, 360.0)
        elif isinstance(yaw, (list, tuple)):
            yv = rng.uniform(float(yaw[0]), float(yaw[1]))
        else:
            yv = float(yaw)
            rng.random()
        t = float(m.get("tilt_deg", 0.0))
        tilt = [rng.uniform(-t, t), rng.uniform(-t, t)] if t else [0.0, 0.0]
        sz = s * rng.uniform(*(m.get("height_jitter") or [1.0, 1.0]))
        out.append({"x": round(x, 3), "y": round(y, 3), "mesh": k, "yaw": round(yv, 3),
                    "scale": [round(s, 4), round(s, 4), round(sz, 4)], "tilt": [round(tilt[0], 3), round(tilt[1], 3)],
                    "z_offset": float(m.get("z_offset_cm", 0.0))})
        counts[k] += 1
    return {"instances": out, "area_m2": round(area / 1e4, 4), "target": target, "min_dist_cm": round(min_dist, 2),
            "counts": counts, "short": max(0, target - len(out))}


def normal_rotation(normal) -> tuple:
    """(pitch, roll) degrees that tilt an instance's up axis onto a surface normal (Unreal: X forward, Y right)."""
    nx, ny, nz = (float(v) for v in normal)
    pitch = math.degrees(math.atan2(-nx, nz))  # tipping toward +X lowers the nose: negative pitch for +X slope
    roll = math.degrees(math.atan2(ny, math.hypot(nx, nz)))
    return pitch, roll


def slope_deg(normal) -> float:
    nx, ny, nz = (float(v) for v in normal)
    n = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return math.degrees(math.acos(max(-1.0, min(1.0, nz / n))))


def args_hash(args: dict) -> str:
    """A stable fingerprint of a scatter's arguments (what convergence compares)."""
    return hashlib.sha1(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:16]


def asset_name(prefix: str, index: int, mesh: str) -> str:
    """The foliage type asset of a scatter's mesh: FT_<prefix>_<index>_<mesh name>."""
    stem = mesh.rsplit("/", 1)[-1].split(".")[0]
    clean = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in f"FT_{prefix}_{index}_{stem}")
    return clean[:100]
