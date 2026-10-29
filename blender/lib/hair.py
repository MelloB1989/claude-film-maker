"""Hair for the people of lib/human.py, in an anime look: a mass cut from the scalp shell MakeHuman fits to every head
(its hem shaped round the head: bangs at the front, the sides, the back), locks over it (flat tapering strands combed
along the mass and falling free below it, or drawn back toward a point), and a bun with a pin for hair worn up.

`hem_profile` and `ribbon` are numpy only and tested without Blender. Angles round the head: 0 at the front (-y),
positive toward the person's left (+x), +-pi at the back.
"""
from __future__ import annotations

import math

import numpy as np

from . import human


def hem_profile(front: float, side: float, back: float):
    """A hem round the head as a function of the angle round it: `front` (the bangs' height) at 0, `side` at +-pi/2,
    `back` at +-pi, eased between."""
    def hem(a: float) -> float:
        u = abs((a + math.pi) % (2 * math.pi) - math.pi)          # 0 front .. pi back
        if u < math.pi / 2:
            k = (1 - math.cos(2 * u)) / 2
            return front + (side - front) * k
        k = (1 - math.cos(2 * (u - math.pi / 2))) / 2
        return side + (back - side) * k
    return hem


def ribbon(points, normals, widths, thickness: float = 0.002):
    """A flat strip along `points` (k, 3) lying on a surface of `normals` (k, 3): `widths` (k,) across, `thickness`
    through. Returns (verts, faces): four vertices a point (a thin box section), capped at both ends; with `thickness`
    0, two a point (one flat strip, the finest strand the line art can outline)."""
    p = np.asarray(points, float)
    nrm = np.asarray(normals, float)
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    t = np.gradient(p, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    across = np.cross(nrm, t)
    across /= np.maximum(np.linalg.norm(across, axis=1, keepdims=True), 1e-9)
    w = np.asarray(widths, float)[:, None] / 2
    if thickness <= 0:
        # one flat strip, two vertices a point: the line art draws only its outline
        verts = np.concatenate([[p[i] - across[i] * w[i], p[i] + across[i] * w[i]] for i in range(len(p))])
        faces = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(p) - 1)]
        return verts, faces
    h = thickness / 2
    verts = []
    for i in range(len(p)):
        for sa, sn in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(p[i] + across[i] * sa * w[i] + nrm[i] * sn * h)
    faces = []
    k = len(p)
    for i in range(k - 1):
        a, b = 4 * i, 4 * (i + 1)
        for j in range(4):
            faces.append((a + j, a + (j + 1) % 4, b + (j + 1) % 4, b + j))
    faces.append((3, 2, 1, 0))
    faces.append(tuple(4 * (k - 1) + j for j in range(4)))
    return np.array(verts), faces


def _angle(x: float, y: float, cx: float, cy: float) -> float:
    return math.atan2(x - cx, -(y - cy))


def refine(ob, cuts: int = 2):
    """Subdivide a part's faces `cuts` times over (its weights carried along), so a hem cut across it is fine-grained:
    MakeHuman's hair shell has faces a hand high, and a cut keeps or drops each whole."""
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    bm.to_mesh(ob.data)
    bm.free()
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def mass(person, name: str, *, hem, push: float = 0.006, ragged: float = 0.0, count: int = 9, material=None, seed: int = 1,
         subsurf: int = 1, detail: int = 0, weld: float = 0.0, smooth: int = 0):
    """The hair's mass: the faces of the person's hair shell above `hem(angle)` (a height for each angle round the
    head, hem_profile), pushed out `push`, the hem `ragged` (metres) in `count` points; `detail` subdivides the shell
    first (refine) for a closer cut, `weld` (metres) joins its strips into one surface first, `smooth` evens out its
    folds that many times (all but the hem). Skinned like the shell."""
    from . import garments

    src = person.parts["hair"]
    if detail:
        refine(src, detail)
    co = np.array([v.co[:] for v in src.data.vertices])
    top = co[co[:, 2] > co[:, 2].max() - 0.12]
    cx, cy = top[:, 0].mean(), top[:, 1].mean()
    rng = np.random.default_rng(seed)
    phase = rng.uniform(0, 2 * math.pi)

    def line(a):
        return hem(a) - ragged * (0.5 + 0.5 * math.cos(count * a + phase))

    def keep(p, w):
        return p[2] > line(_angle(p[0], p[1], cx, cy))

    def edge(p):
        # lay the cut's edge on the hem itself (the faces it crossed leave it stepped)
        h = line(_angle(p[0], p[1], cx, cy))
        return (p[0], p[1], h) if p[2] - h < 0.05 else None

    if weld:
        # MakeHuman's shell is strips side by side: weld them into one surface, or the line art draws every seam
        import bmesh

        bm = bmesh.new()
        bm.from_mesh(src.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=weld)
        bm.to_mesh(src.data)
        bm.free()
    ob = garments.cut(person, name, "hair", keep=keep, push=push, material=material, subsurf=subsurf, edge=edge)
    if smooth:
        # even out the folds where the shell's strips meet (the crown): they ink as little stars; the hem stays put
        import bmesh

        bm = bmesh.new()
        bm.from_mesh(ob.data)
        inner = [v for v in bm.verts if not v.is_boundary]
        for _ in range(smooth):
            bmesh.ops.smooth_vert(bm, verts=inner, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        bm.to_mesh(ob.data)
        bm.free()
    # the shell's own folds would ink as creases across the hair: draw only its outline
    ob.lineart.use_crease_override = True
    ob.lineart.crease_threshold = math.radians(100)
    return ob


def locks(person, name: str, over, *, count: int = 60, length=(0.12, 0.22), width=(0.018, 0.032), thickness: float = 0.003,
          toward=None, flare: float = 0.25, jitter: float = 0.25, lift: float = 0.003, min_z: float | None = None,
          max_z: float | None = None, front: float = 1.0, steps: int = 8, material=None, seed: int = 1, where=None,
          until: float = 0.0, taper: float = 1.3):
    """Locks of hair rooted over the hair mass `over`: `count` flat strands `length` long and `width` wide at the
    root, tapering to a point, combed along the mass's surface (down it, or drawn toward the point `toward` in the
    person's frame) and falling free past its edge, spreading out by `flare`. Roots between `min_z` and `max_z`;
    `front` < 1 thins the roots over the face (0: none in front). Skinned like the mass."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    from . import shapes

    rng = np.random.default_rng(seed)
    me = over.data
    co = np.array([v.co[:] for v in me.vertices])
    cx, cy = co[:, 0].mean(), co[:, 1].mean()
    bvh = BVHTree.FromObject(over, bpy.context.evaluated_depsgraph_get(), deform=False)
    polys = [p for p in me.polygons if (min_z is None or p.center.z > min_z) and (max_z is None or p.center.z < max_z)
             and (where is None or where(p.center.x, p.center.y, p.center.z))]
    area = np.array([p.area for p in polys])
    # thin the roots over the face
    for i, p in enumerate(polys):
        a = abs(_angle(p.center.x, p.center.y, cx, cy))
        if a < math.pi / 3:
            area[i] *= front
    pick = rng.choice(len(polys), size=count, p=area / area.sum())
    verts, faces = [], []
    for li, pi in enumerate(pick):
        poly = polys[pi]
        # a random point on the face
        vs = [Vector(me.vertices[i].co) for i in poly.vertices]
        wts = rng.dirichlet(np.ones(len(vs)))
        root = sum((v * float(w) for v, w in zip(vs, wts)), Vector((0, 0, 0)))
        hit = bvh.find_nearest(root)
        pos, nrm = (hit[0], hit[1]) if hit[0] is not None else (root, Vector(poly.normal))
        L = rng.uniform(*length)
        step = L / steps
        side = Vector((rng.normal(0, jitter), rng.normal(0, jitter), 0.0))
        pts, nrms = [np.array(pos + nrm * lift)], [np.array(nrm)]
        p, n = Vector(pos), Vector(nrm)
        free = False
        d_prev = None
        for s in range(steps):
            if toward is not None:
                g = Vector(toward) - p
                if g.length < until + step * 0.5:
                    break
                g.normalize()
            else:
                g = Vector((0.0, 0.0, -1.0))
            if not free:
                d = g - n * g.dot(n) + side * 0.4
            else:
                d = d_prev * 0.6 + g * 0.4 + side * 0.15
                out = Vector((p.x - cx, p.y - cy, 0.0))
                if out.length > 1e-6:
                    out.normalize()
                    d += out * flare
            d.normalize()
            q = p + d * step
            if not free:
                h = bvh.find_nearest(q)
                if h[0] is not None and (h[0] - q).length < step * 1.2 and h[1].dot(n) > 0.2:
                    p, n = h[0], h[1]
                    q = p
                else:
                    free = True
                    p = q
            else:
                p = q
            d_prev = d
            pts.append(np.array(q + n * lift))
            nrms.append(np.array(n))
        if len(pts) < 2:
            continue
        w0 = rng.uniform(*width)
        widths = w0 * np.clip(1.0 - np.linspace(0, 1, len(pts)) ** taper, 0.04, 1.0)
        v, f = ribbon(np.array(pts), np.array(nrms), widths, thickness)
        base = len(verts)
        verts.extend(v.tolist())
        faces.extend(tuple(base + i for i in face) for face in f)
    ob = shapes.mesh_object(name, verts, faces, material, person.coll, smooth=True)
    human.skin_like(ob, over, person.rig)
    person.parts[name] = ob
    return ob


def bun(person, name: str, at, size=(0.055, 0.045, 0.045), *, material=None, pin=None, pin_material=None, turns: int = 3) -> list:
    """Hair drawn up into a bun at `at` (the person's frame): a ball `size` (radii) with a coil of hair round it, and a
    pin through it (`pin`: (length, radius, angle in degrees from level)). Bound to the head."""
    from . import shapes

    cx, cy, cz = at
    rx, ry, rz = size
    obs = [shapes.ellipsoid(f"{name}", at, size, material=material, coll=person.coll, n=16)]
    pts, nrm = [], []
    k = 60
    for i in range(k):
        u = i / (k - 1)
        a = 2 * math.pi * turns * u
        r = 1.02 - 0.35 * u
        x = cx + rx * r * math.cos(a)
        z = cz + rz * r * math.sin(a)
        y = cy + ry * (0.6 * u + 0.35)
        pts.append((x, y, z))
        nrm.append((math.cos(a), 0.3, math.sin(a)))
    v, f = ribbon(np.array(pts), np.array(nrm), np.full(k, min(rx, rz) * 0.45), 0.004)
    obs.append(shapes.mesh_object(f"{name}-coil", v.tolist(), f, material, person.coll, smooth=True))
    if pin is not None:
        length, radius, ang = pin
        a = math.radians(ang)
        d = np.array([math.cos(a), 0.0, math.sin(a)])
        c = np.array(at) + np.array([0.0, ry * 0.3, 0.0])
        obs.append(shapes.cylinder(f"{name}-pin", tuple(c - d * length / 2), tuple(c + d * length / 2), radius,
                                   material=pin_material or material, coll=person.coll, n=8))
    for ob in obs:
        human.bind(ob, person.rig, "head")
    return obs


def tube(points, normals, widths, depth: float = 0.45, sides: int = 8):
    """A lock with a rounded section along `points` (k, 3) lying on a surface of `normals` (k, 3): `widths` (k,)
    across, `depth` of that through (flattened against the head; one for all, or one a point); the last width 0 makes
    a point. Returns (verts, faces), capped at the root. Numpy only."""
    p = np.asarray(points, float)
    nrm = np.asarray(normals, float)
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    t = np.gradient(p, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    across = np.cross(nrm, t)
    across /= np.maximum(np.linalg.norm(across, axis=1, keepdims=True), 1e-9)
    up = np.cross(t, across)
    w = np.asarray(widths, float) / 2
    dep = np.broadcast_to(np.asarray(depth, float), (len(p),))
    ang = np.linspace(0, 2 * math.pi, sides, endpoint=False)
    verts = []
    for i in range(len(p)):
        for a in ang:
            verts.append(p[i] + across[i] * w[i] * math.cos(a) + up[i] * w[i] * dep[i] * math.sin(a))
    faces = []
    k = len(p)
    for i in range(k - 1):
        for j in range(sides):
            a0, a1 = i * sides + j, i * sides + (j + 1) % sides
            faces.append((a0, a1, a1 + sides, a0 + sides))
    faces.append(tuple(range(sides - 1, -1, -1)))
    return np.array(verts), faces


def clumps(person, name: str, over, *, count: int = 40, length=(0.1, 0.2), width=(0.03, 0.05), depth: float = 0.45,
           toward=None, flare: float = 0.3, jitter: float = 0.2, curl: float = 0.0, lift: float = 0.004, where=None,
           min_z: float | None = None, front: float = 1.0, steps: int = 10, material=None, seed: int = 1, away=None,
           sides: int = 8, lines: int = 0, line_material=None, line_width: float = 0.0012):
    """Anime hair in clumps: `count` locks rooted over the hair mass `over`, each `width` across at the root with a
    rounded section (`depth` of its width through), combed along the mass (down it, or toward the point `toward`) and
    falling free past its edge, flaring out by `flare`, curving sideways by `curl` (metres) and ending in a sharp point;
    the line art outlines each clump as drawn hair does. Roots where `where(x, y, z)` and above `min_z`; `front` < 1
    thins them over the face. `away` (a point: the crown's whorl) combs them out from it over the head, falling
    straight once free. `sides` rounds their section (16 keeps the line art from drawing creases along them); `lines`
    strand lines a clump drawn along its top in `line_material` (an object of their own, `<name>-strands`, kept out of
    the line art). Skinned like the mass."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    from . import shapes

    rng = np.random.default_rng(seed)
    me = over.data
    co = np.array([v.co[:] for v in me.vertices])
    cx, cy = co[:, 0].mean(), co[:, 1].mean()
    bvh = BVHTree.FromObject(over, bpy.context.evaluated_depsgraph_get(), deform=False)
    polys = [p for p in me.polygons if (min_z is None or p.center.z > min_z)
             and (where is None or where(p.center.x, p.center.y, p.center.z))]
    area = np.array([p.area for p in polys])
    for i, p in enumerate(polys):
        if abs(_angle(p.center.x, p.center.y, cx, cy)) < math.pi / 3:
            area[i] *= front
    pick = rng.choice(len(polys), size=count, p=area / area.sum())
    verts, faces = [], []
    sverts, sfaces = [], []
    for pi in pick:
        poly = polys[pi]
        vs = [Vector(me.vertices[i].co) for i in poly.vertices]
        wts = rng.dirichlet(np.ones(len(vs)))
        root = sum((v * float(w) for v, w in zip(vs, wts)), Vector((0, 0, 0)))
        hit = bvh.find_nearest(root)
        pos, nrm = (hit[0], hit[1]) if hit[0] is not None else (root, Vector(poly.normal))
        L = rng.uniform(*length)
        step = L / steps
        side = Vector((rng.normal(0, jitter), rng.normal(0, jitter), 0.0))
        bend = rng.normal(0, 1) * curl
        p, n = Vector(pos), Vector(nrm)
        pts, nrms = [np.array(p + n * lift)], [np.array(n)]
        free, d_prev = False, None
        for s in range(steps):
            if toward is not None:
                g = (Vector(toward) - p).normalized()
            elif away is not None and not free:
                g = (p - Vector(away)).normalized() + Vector((0.0, 0.0, -0.35))
                g.normalize()
            else:
                g = Vector((0.0, 0.0, -1.0))
            if not free:
                d = g - n * g.dot(n) + side * 0.35
            else:
                d = d_prev * 0.65 + g * 0.35 + side * 0.1
                out = Vector((p.x - cx, p.y - cy, 0.0))
                if out.length > 1e-6:
                    d += out.normalized() * flare
            d.normalize()
            q = p + d * step
            if not free:
                h = bvh.find_nearest(q)
                if h[0] is not None and (h[0] - q).length < step * 1.2 and h[1].dot(n) > 0.2:
                    p, n = h[0], h[1]
                    q = p
                else:
                    free = True
                    p = q
            else:
                p = q
            d_prev = d
            u = (s + 1) / steps
            sway = n.cross(d).normalized() * bend * math.sin(math.pi * u)
            pts.append(np.array(q + n * lift + sway))
            nrms.append(np.array(n))
        k = len(pts)
        u = np.linspace(0, 1, k)
        w0 = rng.uniform(*width)
        widths = w0 * np.minimum(0.75 + 2.5 * u, 1.0) * (1.0 - u) ** 0.85
        v, f = tube(np.array(pts), np.array(nrms), widths, depth, sides)
        base = len(verts)
        verts.extend(v.tolist())
        faces.extend(tuple(base + i for i in face) for face in f)
        if lines:
            sv, sf = _strands(np.array(pts), np.array(nrms), widths, depth, lines, line_width, rng)
            sbase = len(sverts)
            sverts.extend(sv)
            sfaces.extend(tuple(sbase + i for i in face) for face in sf)
    ob = shapes.mesh_object(name, verts, faces, material, person.coll, smooth=True)
    human.skin_like(ob, over, person.rig)
    person.parts[name] = ob
    if lines and sverts:
        so = shapes.mesh_object(f"{name}-strands", sverts, sfaces, line_material or material, person.coll, smooth=True)
        so.lineart.usage = "EXCLUDE"
        human.skin_like(so, over, person.rig)
        person.parts[f"{name}-strands"] = so
    return ob


def _strands(pts, nrms, widths, depth: float, lines: int, line_width: float, rng):
    """Strand lines along a clump's top (its outer side), from a fifth of the way along to near its point, each a
    fine flat strip a hair off the surface."""
    t = np.gradient(pts, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    n = nrms / np.maximum(np.linalg.norm(nrms, axis=1, keepdims=True), 1e-9)
    across = np.cross(n, t)
    across /= np.maximum(np.linalg.norm(across, axis=1, keepdims=True), 1e-9)
    up = np.cross(t, across)
    k = len(pts)
    verts, faces = [], []
    for j in range(lines):
        a = math.pi / 2 + (j - (lines - 1) / 2) * 0.7 + rng.normal(0, 0.12)
        i0, i1 = int(k * rng.uniform(0.12, 0.25)), int(k * rng.uniform(0.72, 0.88))
        if i1 - i0 < 3:
            continue
        sl = slice(i0, i1)
        w = (widths / 2)[sl]
        surf = (pts[sl] + across[sl] * (w * math.cos(a))[:, None] + up[sl] * (w * depth * math.sin(a) + 0.0004)[:, None])
        sn = across[sl] * math.cos(a) + up[sl] * math.sin(a)
        lw = line_width * np.sin(np.linspace(0.15, math.pi - 0.15, i1 - i0)) ** 0.5
        v, f = ribbon(surf, sn, lw, 0.0)
        base = len(verts)
        verts.extend(np.asarray(v).tolist())
        faces.extend(tuple(base + i for i in face) for face in f)
    return verts, faces


def scalp(person) -> tuple:
    """The skull's middle and radius: the sphere through MakeHuman's scalp (the body's "scalp" vertex group), at rest."""
    m = human._members(person.body, ["scalp"])
    co = np.array([v.co[:] for v in person.body.data.vertices])[m]
    return human.fit_sphere(co)


def hairline(person, hem, angles, *, center=None) -> list:
    """Points on the scalp along a hairline: for each angle round the head (0 the front, + toward the person's left),
    where the skin at that angle reaches the height `hem(angle)`, found by rays out from the skull's middle."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    bvh = BVHTree.FromObject(person.body, bpy.context.evaluated_depsgraph_get(), deform=False)
    c = Vector(center if center is not None else scalp(person)[0])
    out = []
    for a in angles:
        h = Vector((math.sin(a), -math.cos(a), 0.0))
        best = None
        for e in np.linspace(-1.2, 1.4, 80):
            d = h * math.cos(e) + Vector((0.0, 0.0, math.sin(e)))
            hit = bvh.ray_cast(c, d, 0.4)
            if hit[0] is None:
                continue
            err = abs(hit[0].z - hem(a))
            if best is None or err < best[0]:
                best = (err, hit[0].copy())
        if best is not None:
            out.append(tuple(best[1]))
    return out


def sections(person, name: str, roots, toward, *, width: float = 0.05, thickness: float = 0.014, lift: float = 0.0015,
             end: float = 0.02, puff=None, wobble: float = 0.003, steps: int = 18, sides: int = 10, material=None, seed: int = 1,
             center=None) -> object:
    """Hair combed back in sections, as anime draws it: from each root on the scalp (`roots`, hairline) a section
    `width` across and `thickness` deep runs over the skull toward `toward` (a bun), lying on the scalp (found by rays
    out from the skull's middle), swelling through its middle, narrowing as it goes and ending `end` short of the bun.
    `puff(t, root)` adds depth along a section (volume above the ears, t 0 at the root to 1 at the end). Neighbours
    overlap, so the line art draws the parting between them. One object, bound to the head."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    from . import shapes

    rng = np.random.default_rng(seed)
    bvh = BVHTree.FromObject(person.body, bpy.context.evaluated_depsgraph_get(), deform=False)
    c = Vector(center if center is not None else scalp(person)[0])
    b = Vector(toward)
    db = (b - c).normalized()
    verts, faces = [], []
    for root in roots:
        r = Vector(root)
        d0 = (r - c).normalized()
        # over the skull, not round it: through a midpoint raised the more the root and the bun face apart (a section
        # from the forehead goes over the crown, one from the temple over the upper side, one from the nape just up)
        dm = ((d0 + db) * 0.5 + Vector((0.0, 0.0, 0.65 * (1.0 - d0.dot(db)) / 2))).normalized()
        w0, h0 = width * rng.uniform(0.88, 1.12), thickness * rng.uniform(0.85, 1.2)
        pts, nrms, ws, hs = [], [], [], []
        phase = rng.uniform(0, 2 * math.pi)
        for k in range(steps + 1):
            t = k / steps
            d = (d0 * (1 - 2 * t) + dm * 2 * t if t < 0.5 else dm * (2 - 2 * t) + db * (2 * t - 1)).normalized()
            hit = bvh.ray_cast(c, d, 0.4)
            if hit[0] is None:
                continue
            sp, n = hit[0], hit[1]
            if n.dot(d) < 0:
                n = -n
            if (sp - b).length < end and k > 2:
                break
            h = h0 * (0.45 + 0.75 * math.sin(math.pi * min(1.0, t * 1.15))) + (puff(t, root) if puff else 0.0)
            w = w0 * min(1.0, 0.55 + 4.0 * t) * (1.0 - 0.5 * t)
            side = n.cross(d).normalized() * wobble * math.sin(phase + 7.0 * t)
            pts.append(np.array(sp + n * (lift + h * 0.5) + side))
            nrms.append(np.array(n))
            ws.append(w)
            hs.append(h)
        if len(pts) < 3:
            continue
        ws[-1] *= 0.4
        v, f = tube(np.array(pts), np.array(nrms), np.array(ws), np.array(hs) / np.maximum(np.array(ws), 1e-6), sides)
        base = len(verts)
        verts.extend(v.tolist())
        faces.extend(tuple(base + i for i in face) for face in f)
    ob = shapes.mesh_object(name, verts, faces, material, person.coll, smooth=True)
    # neighbours cross where they overlap: draw their outlines and partings, not where they pass through each other
    ob.lineart.usage = "NO_INTERSECTION"
    human.bind(ob, person.rig, "head")
    person.parts[name] = ob
    return ob


def coil(person, name: str, at, *, axis=(0.0, 1.0, 0.0), radius: float = 0.03, thick: float = 0.011, turns: float = 2.3,
         material=None, pin=None, pin_material=None, sides: int = 8) -> list:
    """A bun of wound hair at `at` (the person's frame): a thick strand coiled `turns` times, spiralling in, its
    loops stacked out along `axis` (away from the head), `radius` across, over a small core so nothing shows through;
    `pin` (length, radius, angle in degrees from level) through it. Bound to the head."""
    from . import shapes

    a = np.asarray(axis, float)
    a /= np.linalg.norm(a)
    e1 = np.cross(a, (0.0, 0.0, 1.0))
    if np.linalg.norm(e1) < 1e-6:
        e1 = np.array([1.0, 0.0, 0.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    c = np.asarray(at, float)
    k = int(28 * turns)
    pts, nrm, ws = [], [], []
    for i in range(k):
        u = i / (k - 1)
        ang = 2 * math.pi * turns * u
        radial = e1 * math.cos(ang) + e2 * math.sin(ang)
        r = radius * (1.0 - 0.55 * u)
        pts.append(c + radial * r + a * thick * (1.5 * u - 0.3))
        nrm.append(a * 0.6 + radial * 0.4)
        ws.append(2 * thick * (1.0 - 0.25 * u) * min(1.0, (1.0 - u) * 8 + 0.15))
    v, f = tube(np.array(pts), np.array(nrm), np.array(ws), 0.8, sides)
    obs = [shapes.mesh_object(f"{name}", v.tolist(), f, material, person.coll, smooth=True),
           shapes.ellipsoid(f"{name}-core", tuple(c - a * thick * 0.2), (radius * 0.75, radius * 0.75, radius * 0.75), material=material,
                            coll=person.coll, n=12)]
    if pin is not None:
        length, pr, deg = pin
        t = math.radians(deg)
        d = e1 * math.cos(t) + e2 * math.sin(t)
        pc = c + a * thick * 0.6
        obs.append(shapes.cylinder(f"{name}-pin", tuple(pc - d * length / 2), tuple(pc + d * length / 2), pr,
                                   material=pin_material or material, coll=person.coll, n=8))
    for ob in obs:
        human.bind(ob, person.rig, "head")
    return obs
