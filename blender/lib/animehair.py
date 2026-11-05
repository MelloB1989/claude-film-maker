"""Anime hair, as TV anime draws it: a few dozen big clean locks, each a smooth ribbon with a crescent (or lens)
section, crisp edges and a sharp point, laid along designed paths (from a crown whorl or a hairline, hugging the skull,
then falling free with gravity, flare, swoop and curl) over a smooth cap that fills the gaps; and a toon material with a
crisp shade band and the bright band anime hair carries round the head (the "angel ring"), broken into one highlight a
lock.

A style is a list of `Lock`s (where each grows, which way it is combed, how long and wide, how it falls); `grow(...)`
builds them into one mesh bound to the head, with the attributes the material reads. `fan(...)` makes a row of locks
round the head with seeded variation, the usual way to fill a style.

Locks are swept in numpy (`profile`, `taper`, `resample`, `sweep` are numpy only and tested without Blender); finding
the scalp and laying the paths use Blender's BVH. Angles round the head as in lib/hair.py: azimuth 0 at the front (-y),
positive toward the person's left (+x), 180 at the back; elevation 0 at the skull's middle, 90 at its top. Positions
are in the person's frame (the rest pose).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from . import human


@dataclass
class Lock:
    """One lock of hair: it grows at (`az`, `el`) degrees on the skull, is combed away from the style's whorl (or
    toward `toward`, or turned `heading` degrees from that), lies on the head for `hug` of its `length` standing `lift`
    off it, then falls free: gravity `fall`, `flare` outward, `swoop` sideways (+ toward the person's left), its point
    curling `curl` degrees out (+) or in (-) and the lock turning `twist` degrees about itself by the tip."""
    az: float
    el: float
    length: float = 0.18
    width: float = 0.045
    depth: float = 0.3
    hug: float = 0.5
    lift: float = 0.012
    fall: float = 1.0
    flare: float = 0.3
    swoop: float = 0.0
    curl: float = 0.0
    twist: float = 0.0
    heading: float = 0.0
    toward: tuple | None = None
    kind: str = "crescent"
    peak: float = 0.3
    point: float = 0.9
    root: float = 0.55


# ---- numpy halves ----

def profile(kind: str = "crescent", n: int = 6) -> np.ndarray:
    """A lock's section, (2n - 2, 2): x across (-1 to 1), y out from the head (0 to 1 at the crown of the outer arc).
    The outer arc runs from x -1 to 1, the inner back; they meet in sharp edges at x -1 and 1. "crescent": the inner
    arc bows outward too, a lock curving round the head, thick in the middle and thin at the edges; "lens": the inner
    arc bows toward the head."""
    x = np.linspace(-1.0, 1.0, n)
    outer = np.column_stack([x, 1.0 - x ** 2])
    k = 0.42 if kind == "crescent" else -0.45
    xi = x[::-1][1:-1]
    inner = np.column_stack([xi, k * (1.0 - xi ** 2)])
    return np.concatenate([outer, inner])


def taper(u, *, peak: float = 0.3, point: float = 0.9, root: float = 0.55) -> np.ndarray:
    """A lock's width along it (u 0 at the root to 1 at the tip), 0 to 1: `root` of its width where it grows, widening
    to the full width at `peak`, then narrowing to a sharp point (`point` < 1 keeps it fuller, > 1 thins it sooner)."""
    u = np.clip(np.asarray(u, float), 0.0, 1.0)
    rise = root + (1.0 - root) * np.sin(0.5 * math.pi * np.clip(u / max(peak, 1e-6), 0.0, 1.0))
    fall = np.where(u <= peak, 1.0, np.clip((1.0 - u) / max(1.0 - peak, 1e-6), 0.0, 1.0) ** point)
    return rise * fall


def resample(points, n: int) -> np.ndarray:
    """`points` (k, 3) as a smooth curve of `n` points evenly spaced along it (Catmull-Rom through them)."""
    p = np.asarray(points, float)
    if len(p) < 3:
        t = np.linspace(0, 1, n)[:, None]
        return p[0] * (1 - t) + p[-1] * t
    ext = np.concatenate([2 * p[:1] - p[1:2], p, 2 * p[-1:] - p[-2:-1]])
    dense = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for t in np.linspace(0, 1, 8, endpoint=False):
            t2, t3 = t * t, t * t * t
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dense.append(p[-1])
    dense = np.array(dense)
    seg = np.linalg.norm(np.diff(dense, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    target = np.linspace(0, s[-1], n)
    return np.column_stack([np.interp(target, s, dense[:, k]) for k in range(3)])


def sweep(path, outs, widths, depths, prof, *, twist=None):
    """Sweep the section `prof` (profile) along `path` (k, 3): at each point, x across the lock `widths` (k,) wide and
    y along `outs` (k, 3: away from the head) `depths` (k,) deep, turned `twist` (k,) radians about the path. The
    last point is the lock's sharp tip (one vertex); the root is capped. Returns (verts (V, 3), faces, along (V,),
    across (V,), edges: the vertex pairs of the two sharp edges, to crease)."""
    p = np.asarray(path, float)
    k = len(p)
    t = np.gradient(p, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    o = np.asarray(outs, float)
    o = o - t * np.sum(o * t, axis=1, keepdims=True)
    o /= np.maximum(np.linalg.norm(o, axis=1, keepdims=True), 1e-9)
    a = np.cross(t, o)
    a /= np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)
    if twist is not None:
        tw = np.asarray(twist, float)[:, None]
        a, o = a * np.cos(tw) + o * np.sin(tw), o * np.cos(tw) - a * np.sin(tw)
    m = len(prof)
    w = np.asarray(widths, float) / 2
    d = np.asarray(depths, float)
    verts, along, across = [], [], []
    for i in range(k - 1):
        for x, y in prof:
            verts.append(p[i] + a[i] * x * w[i] + o[i] * y * d[i])
            along.append(i / (k - 1))
            across.append(x)
    verts.append(p[-1])
    along.append(1.0)
    across.append(0.0)
    faces = [tuple(range(m - 1, -1, -1))]
    for i in range(k - 2):
        for j in range(m):
            a0, a1 = i * m + j, i * m + (j + 1) % m
            faces.append((a0, a1, a1 + m, a0 + m))
    tip = (k - 1) * m
    base = (k - 2) * m
    for j in range(m):
        faces.append((base + j, base + (j + 1) % m, tip))
    # the sharp edges: where the outer and inner arcs meet (section points 0 and n - 1)
    n_outer = (m + 2) // 2
    edges = []
    for j in (0, n_outer - 1):
        for i in range(k - 2):
            edges.append((i * m + j, (i + 1) * m + j))
    return np.array(verts), faces, np.array(along), np.array(across), edges


def fan(az, el, *, rng=None, jitter: float = 0.0, **lock) -> list:
    """Locks at azimuths `az` (degrees, a list) and elevation `el` (one, or one each), the rest of their settings from
    `lock`; `jitter` varies each setting that much (a fraction) either way, seeded by `rng`."""
    rng = rng or np.random.default_rng(1)
    els = el if isinstance(el, (list, tuple, np.ndarray)) else [el] * len(az)
    out = []
    for a, e in zip(az, els):
        kw = dict(lock)
        if jitter:
            for key in ("length", "width", "lift", "fall", "flare", "hug"):
                if key in kw and isinstance(kw[key], (int, float)):
                    kw[key] = kw[key] * (1.0 + rng.uniform(-jitter, jitter))
            for key in ("swoop", "curl", "twist", "heading"):
                if key in kw and isinstance(kw[key], (int, float)):
                    kw[key] = kw[key] + rng.uniform(-jitter, jitter) * (abs(kw[key]) + (8.0 if key != "swoop" else 0.15))
        out.append(Lock(az=float(a + (rng.uniform(-3, 3) if jitter else 0.0)), el=float(e + (rng.uniform(-3, 3) if jitter else 0.0)), **kw))
    return out


def direction(az: float, el: float) -> np.ndarray:
    """The unit vector from the skull's middle at azimuth `az` and elevation `el` (degrees)."""
    a, e = math.radians(az), math.radians(el)
    return np.array([math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)])


def over(d, b) -> np.ndarray:
    """The waypoint a lock combed from direction `d` to direction `b` (from the skull's middle) passes, so it goes over
    the skull and never round under it: their midpoint, raised the more the two face apart (from the forehead to a
    bun at the nape it climbs over the crown). Numpy only."""
    d, b = np.asarray(d, float), np.asarray(b, float)
    m = (d + b) * 0.5 + np.array([0.0, 0.0, 0.65 * (1.0 - float(d @ b)) / 2])
    return m / np.linalg.norm(m)


def arc(d, b, r: float) -> float:
    """How far a lock combed over the skull (radius `r`) from direction `d` to `b` travels, by way of `over`."""
    m = over(d, b)
    return (math.acos(float(np.clip(np.asarray(d) @ m, -1, 1))) + math.acos(float(np.clip(m @ np.asarray(b), -1, 1)))) * r


# ---- in Blender ----

class Head:
    """The skull to lay hair on: its middle and radius (MakeHuman's scalp, hair.scalp), and the body to project onto
    (rays out from the middle) and to keep falling hair outside of."""

    def __init__(self, person):
        import bpy
        from mathutils.bvhtree import BVHTree

        from . import hair

        self.person = person
        c, r = hair.scalp(person)
        self.center, self.radius = np.asarray(c, float), float(r)
        self.bvh = BVHTree.FromObject(person.body, bpy.context.evaluated_depsgraph_get(), deform=False)

    def surface(self, d):
        """Where the ray from the skull's middle along `d` leaves the skin, and the skin's normal there (outward)."""
        from mathutils import Vector

        hit = self.bvh.ray_cast(Vector(self.center), Vector(d), 0.5)
        if hit[0] is None:
            p = self.center + np.asarray(d) * self.radius
            return p, np.asarray(d)
        n = np.array(hit[1][:])
        if n @ np.asarray(d) < 0:
            n = -n
        return np.array(hit[0][:]), n

    def outside(self, p, margin: float):
        """`p` pushed out of the body to at least `margin` off its skin."""
        from mathutils import Vector

        loc, n, _, dist = self.bvh.find_nearest(Vector(p))
        if loc is None:
            return p
        loc, n = np.array(loc[:]), np.array(n[:])
        off = (p - loc) @ n
        return p + n * (margin - off) if off < margin else p


def path(head: Head, lock: Lock, whorl, *, steps: int = 24) -> tuple[np.ndarray, np.ndarray]:
    """A lock's path: from its root, combed over the skull (away from `whorl`, a direction from the skull's middle,
    or toward its `toward` point) for `hug` of its length standing off the head by a lift rising to `lift`, then free.
    Returns (points (k, 3), outward directions (k, 3)), resampled smooth."""
    c, R = head.center, head.radius
    d = direction(lock.az, lock.el)
    W = np.asarray(whorl, float)
    W = W / np.linalg.norm(W)
    s = lock.length / steps
    n_hug = max(1, int(round(steps * lock.hug)))
    pts, outs = [], []
    heading = math.radians(lock.heading)
    if lock.toward is not None:
        b = np.asarray(lock.toward, float) - c
        b /= np.linalg.norm(b)
        waypoint, passed = over(d, b), False
    for k in range(n_hug + 1):
        sp, n = head.surface(d)
        u = k / max(n_hug, 1)
        lift = lock.lift * (0.35 + 0.65 * math.sin(0.5 * math.pi * u))
        pts.append(sp + n * lift)
        outs.append(n)
        if lock.toward is not None:
            # by way of the raised midpoint, then on to the point
            if not passed and d @ waypoint > math.cos(0.1):
                passed = True
            tgt = b if passed else waypoint
            t = tgt - d * (tgt @ d)
        else:
            t = d * (W @ d) - W
        if np.linalg.norm(t) < 1e-6:
            t = np.cross(d, (0.0, 0.0, 1.0))
        t /= np.linalg.norm(t)
        if heading:
            t = t * math.cos(heading) + np.cross(d, t) * math.sin(heading)
        d = d + t * s / R
        d /= np.linalg.norm(d)
    p = pts[-1].copy()
    tdir = pts[-1] - pts[-2] if len(pts) > 1 else outs[-1]
    tdir /= np.linalg.norm(tdir)
    out_h = p - c
    out_h[2] = 0.0
    out_h /= max(np.linalg.norm(out_h), 1e-9)
    sw = np.array([1.0 if lock.swoop >= 0 else -1.0, 0.0, 0.0])     # the person's left is +x
    gain = 18.0 * s
    for k in range(n_hug + 1, steps + 1):
        v = (k - n_hug) / max(steps - n_hug, 1)
        tdir = tdir + (np.array([0.0, 0.0, -1.0]) * lock.fall + out_h * lock.flare + sw * abs(lock.swoop)) * gain
        if lock.curl:
            tdir = tdir + out_h * math.tan(math.radians(abs(lock.curl))) * (1 if lock.curl > 0 else -1) * gain * 2.5 * v
        tdir /= np.linalg.norm(tdir)
        p = p + tdir * s
        p = head.outside(p, 0.006)
        pts.append(p.copy())
        o = p - c
        o /= np.linalg.norm(o)
        outs.append(o)
    pts = np.array(pts)
    outs = np.array(outs)
    n = max(12, steps + 4)
    rp = resample(pts, n)
    # outward directions along the resampled path: nearest of the originals, smoothed
    idx = np.clip(np.searchsorted(np.linspace(0, 1, len(outs)), np.linspace(0, 1, n)), 0, len(outs) - 1)
    ro = outs[idx]
    for _ in range(2):
        ro[1:-1] = (ro[:-2] + 2 * ro[1:-1] + ro[2:]) / 4
    return rp, ro


def grow(person, name: str, locks: list, *, whorl=(0.0, 0.35, 0.94), material=None, n: int = 6, steps: int = 24,
         subsurf: int = 1, crease: bool = True, seed: int = 1) -> object:
    """The style's locks as one mesh bound to the head: each swept (`n` points an arc of its section) along its path,
    its two edges creased so a subdivision keeps them crisp; attributes `hair_along` (0 root to 1 tip), `hair_across`
    (-1 to 1) and `hair_rest` (where each vertex sits from the skull's middle, at rest) for the material."""
    import bpy

    from . import shapes

    head = Head(person)
    verts, faces, along, across, creases = [], [], [], [], []
    for lk in locks:
        pts, outs = path(head, lk, whorl, steps=steps)
        k = len(pts)
        u = np.linspace(0, 1, k)
        w = lk.width * taper(u, peak=lk.peak, point=lk.point, root=lk.root)
        d = w * lk.depth * (1.0 - 0.35 * u)
        tw = np.radians(lk.twist) * u ** 1.5 if lk.twist else None
        v, f, al, ac, ed = sweep(pts, outs, w, d, profile(lk.kind, n), twist=tw)
        base = len(verts)
        verts.extend(v.tolist())
        faces.extend(tuple(base + i for i in face) for face in f)
        along.extend(al.tolist())
        across.extend(ac.tolist())
        creases.extend((base + a, base + b) for a, b in ed)
    ob = shapes.mesh_object(name, verts, faces, material, person.coll, smooth=True)
    me = ob.data
    rest = np.array(verts) - head.center
    for nm, vals, typ in (("hair_along", along, "FLOAT"), ("hair_across", across, "FLOAT")):
        at = me.attributes.new(nm, typ, "POINT")
        at.data.foreach_set("value", np.asarray(vals, np.float32))
    at = me.attributes.new("hair_rest", "FLOAT_VECTOR", "POINT")
    at.data.foreach_set("vector", rest.astype(np.float32).ravel())
    if crease and creases:
        key = {tuple(sorted(e)) for e in creases}
        cr = me.attributes.get("crease_edge") or me.attributes.new("crease_edge", "FLOAT", "EDGE")
        vals = np.zeros(len(me.edges), np.float32)
        for e in me.edges:
            if tuple(sorted(e.vertices)) in key:
                vals[e.index] = 1.0
        cr.data.foreach_set("value", vals)
    human.bind(ob, person.rig, "head")      # skinned first, then smoothed
    if subsurf:
        sm = ob.modifiers.new("smooth", "SUBSURF")
        sm.levels = 1
        sm.render_levels = subsurf
    # neighbours cross where they overlap: draw their outlines and the partings, not where they pass through each other
    ob.lineart.usage = "NO_INTERSECTION"
    person.parts[name] = ob
    return ob


def material(name: str, lit, shade, *, look=None, highlight=None, ring=(0.42, 0.6), zigzag: float = 0.035, teeth: int = 11,
             edge: float = 0.62, cut: float = 0.4, soft: float = 0.015, flash: float | None = None, lines=None):
    """Anime hair's toon material: flat `lit` and `shade` by the light (cut at `cut`, edges `soft`), whitening with a
    lightning flash, and where given the `highlight` band round the head between `ring` (the sines of its lower and
    upper elevation from the skull's middle) on the lit side, its edges zigzagging (`zigzag` high, `teeth` round the
    head), kept off each lock's edges (inside `edge` of its width), so it breaks into one highlight a lock. `lines`
    (colour, width): a drawn line along both edges of every lock, `width` of its half-width (the partings between
    sections of pale hair, which the outline alone leaves unbroken). Reads the attributes `grow` writes; faded to the
    fog like toon.cel."""
    import bpy

    from . import toon

    look = look or toon.Look()
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    L = nt.links

    def m(op, a, b=None, c=None, clamp=False):
        x = nt.nodes.new("ShaderNodeMath")
        x.operation = op
        x.use_clamp = clamp
        for sock, val in ((x.inputs[0], a), (x.inputs[1], b), (x.inputs[2], c)):
            if val is None:
                continue
            if isinstance(val, (int, float)):
                sock.default_value = val
            else:
                L.new(val, sock)
        return x.outputs[0]

    def step(val, lo, hi):
        r = nt.nodes.new("ShaderNodeMapRange")
        r.interpolation_type = "SMOOTHSTEP"
        for key, x in (("From Min", lo), ("From Max", hi)):
            if isinstance(x, (int, float)):
                r.inputs[key].default_value = x
            else:
                L.new(x, r.inputs[key])
        L.new(val, r.inputs["Value"])
        return r.outputs["Result"]

    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    L.new(diff.outputs[0], s2r.inputs[0])
    lum = nt.nodes.new("ShaderNodeRGBToBW")
    L.new(s2r.outputs["Color"], lum.inputs[0])
    litmask = step(lum.outputs[0], cut - soft, cut + soft)
    k = look.flash_amount if flash is None else flash
    lit_col = toon.flashed(nt, lit, look.flash_lit, k) if k > 0 else None
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    L.new(litmask, mix.inputs["Factor"])
    mix.inputs["A"].default_value = (*shade, 1.0)
    if lit_col is not None:
        L.new(lit_col, mix.inputs["B"])
    else:
        mix.inputs["B"].default_value = (*lit, 1.0)
    col = mix.outputs["Result"]
    if highlight is not None:
        rest = nt.nodes.new("ShaderNodeAttribute")
        rest.attribute_type = "GEOMETRY"
        rest.attribute_name = "hair_rest"
        nv = nt.nodes.new("ShaderNodeVectorMath")
        nv.operation = "NORMALIZE"
        L.new(rest.outputs["Vector"], nv.inputs[0])
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        L.new(nv.outputs[0], sep.inputs[0])
        az = m("ARCTAN2", sep.outputs["X"], m("MULTIPLY", sep.outputs["Y"], -1.0))
        zig = m("MULTIPLY", m("SINE", m("MULTIPLY", az, float(teeth))), zigzag)
        zig = m("ADD", zig, m("MULTIPLY", m("SINE", m("ADD", m("MULTIPLY", az, float(teeth) * 2.3), 1.3)), zigzag * 0.4))
        z = m("SUBTRACT", sep.outputs["Z"], zig)
        lo, hi = ring
        band = m("MULTIPLY", step(z, lo - 0.006, lo + 0.006), m("SUBTRACT", 1.0, step(z, hi - 0.006, hi + 0.006)))
        ac = nt.nodes.new("ShaderNodeAttribute")
        ac.attribute_type = "GEOMETRY"
        ac.attribute_name = "hair_across"
        inner = m("SUBTRACT", 1.0, step(m("ABSOLUTE", ac.outputs["Fac"]), edge - 0.08, edge))
        hl = m("MULTIPLY", m("MULTIPLY", band, inner), litmask)
        hmix = nt.nodes.new("ShaderNodeMix")
        hmix.data_type = "RGBA"
        L.new(hl, hmix.inputs["Factor"])
        L.new(col, hmix.inputs["A"])
        hmix.inputs["B"].default_value = (*highlight, 1.0)
        col = hmix.outputs["Result"]
    if lines is not None:
        lc, lw = lines
        ac2 = nt.nodes.new("ShaderNodeAttribute")
        ac2.attribute_type = "GEOMETRY"
        ac2.attribute_name = "hair_across"
        ln = step(m("ABSOLUTE", ac2.outputs["Fac"]), 1.0 - lw, 1.0 - lw * 0.45)
        lmix = nt.nodes.new("ShaderNodeMix")
        lmix.data_type = "RGBA"
        L.new(ln, lmix.inputs["Factor"])
        L.new(col, lmix.inputs["A"])
        lmix.inputs["B"].default_value = (*lc, 1.0)
        col = lmix.outputs["Result"]
    col = toon._fog_mix(nt, col, look)
    em = nt.nodes.new("ShaderNodeEmission")
    L.new(col, em.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    L.new(em.outputs[0], out.inputs["Surface"])
    return mat


def cap(person, name: str, *, hem, push: float = 0.008, material=None, smooth: int = 4) -> object:
    """The smooth cap under the locks, so the head never shows between them: the scalp shell cut to `hem` (a height
    round the head, hair.hem_profile), welded, smoothed and pushed `push` off the skull; it draws only its outline."""
    from . import hair

    ob = hair.mass(person, name, hem=hem, push=push, material=material, detail=2, weld=0.009, smooth=smooth)
    c, _ = hair.scalp(person)
    me = ob.data
    co = np.array([v.co[:] for v in me.vertices]) - np.asarray(c)
    at = me.attributes.new("hair_rest", "FLOAT_VECTOR", "POINT")
    at.data.foreach_set("vector", co.astype(np.float32).ravel())
    return ob
