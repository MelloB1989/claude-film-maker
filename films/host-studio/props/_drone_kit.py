"""_drone_kit — helpers for the drone props only (drone.py, drone_remote.py, drone_combo.py).

Parts are modelled in centimetres, one object per material group; assemble() scales them to metres,
joins them, triangulates n-gons, adds box-projected UVs (1 UV unit = 1 m), puts the origin at the bottom
centre of the footprint and tidies normals/sharp edges with _studio.tidy.
"""
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import _studio as S

CM = 0.01


# ---------------------------------------------------------------- maths

def spow(v, e):
    return math.copysign(abs(v) ** e, v)


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def pchip(keys):
    """Monotone cubic through [(x, y)] keys -> f(x), flat outside the keys."""
    xs = [float(k[0]) for k in keys]
    ys = [float(k[1]) for k in keys]
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def f(x):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = max(j for j in range(n - 1) if xs[j] <= x)
        t = (x - xs[i]) / h[i]
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1])
    return f


def fillet(pts, radii, steps=4):
    """Round the interior corners of an open 2D polyline (quadratic arcs); radii: number or per-point list."""
    if not isinstance(radii, (list, tuple)):
        radii = [0] + [radii] * (len(pts) - 2) + [0]
    out = [tuple(pts[0])]
    for i in range(1, len(pts) - 1):
        p, a, b = Vector(pts[i]), Vector(pts[i - 1]), Vector(pts[i + 1])
        r = radii[i]
        if r <= 0:
            out.append(tuple(p))
            continue
        da, db = a - p, b - p
        d = min(r, da.length * 0.48, db.length * 0.48)
        p0, p1 = p + da.normalized() * d, p + db.normalized() * d
        for k in range(steps + 1):
            t = k / steps
            q = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p + t * t * p1
            out.append((q.x, q.y))
    out.append(tuple(pts[-1]))
    return out


def chaikin(pts, iterations=2):
    """Corner-cutting smoothing of a closed 2D outline."""
    for _ in range(iterations):
        new = []
        n = len(pts)
        for i in range(n):
            a, b = Vector(pts[i]), Vector(pts[(i + 1) % n])
            new.append(tuple(a * 0.75 + b * 0.25))
            new.append(tuple(a * 0.25 + b * 0.75))
        pts = new
    return pts


def ccw(pts):
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts)))
    return pts if area > 0 else list(reversed(pts))


def inset(pts, d):
    """Offset a CCW closed outline inwards by d (mitred at the vertices)."""
    n = len(pts)
    out = []
    for i in range(n):
        p, a, b = Vector(pts[i]), Vector(pts[i - 1]), Vector(pts[(i + 1) % n])
        e1, e2 = (p - a).normalized(), (b - p).normalized()
        n1, n2 = Vector((-e1.y, e1.x)), Vector((-e2.y, e2.x))
        nv = (n1 + n2).normalized()
        out.append(tuple(p + nv * d / max(0.5, nv.dot(n1))))
    return out


def frame(p, n, up=(0, 0, 1)):
    """Matrix at p whose local +Z is n (local X horizontal-ish, from `up` x n)."""
    z = Vector(n).normalized()
    x = Vector(up).cross(z)
    if x.length < 1e-6:
        x = z.orthogonal()
    x.normalize()
    y = z.cross(x)
    return Matrix(((x.x, y.x, z.x, p[0]), (x.y, y.y, z.y, p[1]), (x.z, y.z, z.z, p[2]), (0, 0, 0, 1)))


# ---------------------------------------------------------------- bmesh builders (all add into a bmesh)

def add_box(bm, lo, hi, m=None, slot=0):
    lo, hi = Vector(lo), Vector(hi)
    mat = Matrix.Translation((lo + hi) / 2) @ Matrix.Diagonal((*(hi - lo), 1.0))
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=(m @ mat) if m else mat)
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = slot


def add_lathe(bm, prof, m=None, segs=32, slot=0, rmod=None, phase=0.0):
    """Revolve a closed (r, z) profile (first and last r == 0) around local Z."""
    rings = []
    for r, z in prof:
        if r <= 1e-9:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            ring = []
            for k in range(segs):
                a = phase + 2 * math.pi * k / segs
                rr = rmod(r, z, a) if rmod else r
                ring.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), z)))
            rings.append(ring)
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        if len(A) == 1 and len(B) == 1:
            continue
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(A) == 1:
                f = bm.faces.new((A[0], B[k], B[k2]))
            elif len(B) == 1:
                f = bm.faces.new((A[k], A[k2], B[0]))
            else:
                f = bm.faces.new((A[k], A[k2], B[k2], B[k]))
            f.material_index = slot
    if m is not None:
        bmesh.ops.transform(bm, matrix=m, verts=[v for ring in rings for v in ring])


def add_grid(bm, rings, cap0="ngon", cap1="ngon", slot=0):
    """Skin closed rings of equal length; caps: 'ngon', a pole point, or None."""
    vr = [[bm.verts.new(p) for p in ring] for ring in rings]
    m = len(vr[0])
    for i in range(len(vr) - 1):
        A, B = vr[i], vr[i + 1]
        for k in range(m):
            k2 = (k + 1) % m
            bm.faces.new((A[k], A[k2], B[k2], B[k])).material_index = slot
    for ring, cap, rev in ((vr[0], cap0, True), (vr[-1], cap1, False)):
        if cap is None:
            continue
        if isinstance(cap, str):
            bm.faces.new(list(reversed(ring)) if rev else ring).material_index = slot
        else:
            pv = bm.verts.new(cap)
            for k in range(m):
                k2 = (k + 1) % m
                bm.faces.new((ring[k], ring[k2], pv)).material_index = slot
    return vr


def add_tube(bm, pts, prof_fn, hint=(0, 0, 1), slot=0, caps=True):
    """Sweep prof_fn(u) -> [(a, b)] (a along the hint-side normal, b along tangent x normal) along pts."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tans = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    nrm = Vector(hint) - Vector(hint).dot(tans[0]) * tans[0]
    nrm.normalize()
    rings = []
    for i in range(n):
        t = tans[i]
        nrm = (nrm - nrm.dot(t) * t).normalized()
        b = t.cross(nrm)
        rings.append([tuple(pts[i] + a * nrm + c * b) for a, c in prof_fn(i / (n - 1))])
    cap = "ngon" if caps else None
    return add_grid(bm, rings, cap, cap, slot)


def add_prism(bm, outline, p0, p1, up=(1, 0, 0), slot=0):
    """Extrude a 2D outline [(a, b)] from p0 to p1 (a along `up` projected off the axis)."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = (p1 - p0).normalized()
    u = Vector(up) - Vector(up).dot(ax) * ax
    if u.length < 1e-6:
        u = ax.orthogonal()
    u.normalize()
    v = ax.cross(u)
    rings = [[tuple(base + a * u + b * v) for a, b in outline] for base in (p0, p1)]
    add_grid(bm, rings, "ngon", "ngon", slot)


def add_superellipsoid(bm, centre, radii, n=2.6, segs=32, rings=16, slot=0):
    c = Vector(centre)
    rx, ry, rz = radii
    rs = []
    for i in range(1, rings):
        th = -math.pi / 2 + math.pi * i / rings
        ring = []
        for k in range(segs):
            ph = 2 * math.pi * k / segs
            ring.append((c.x + rx * spow(math.cos(th), 2 / n) * spow(math.cos(ph), 2 / n),
                         c.y + ry * spow(math.cos(th), 2 / n) * spow(math.sin(ph), 2 / n),
                         c.z + rz * spow(math.sin(th), 2 / n)))
        rs.append(ring)
    add_grid(bm, rs, Vector((c.x, c.y, c.z - rz)), Vector((c.x, c.y, c.z + rz)), slot)


# ---------------------------------------------------------------- objects

def mk(name, bm, mats, bevel=None, segs=2, angle=35, cut=None):
    """Object from a bmesh (local cm), with an optional boolean cut and bevel, modifiers applied.

    Faces of the cutter keep their own material_index, so a recess can be lined with a second slot."""
    if not isinstance(mats, (list, tuple)):
        mats = [mats]
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if os.environ.get("DBG"):
        print(f"  mk {name}: {len(bm.verts)} verts {len(bm.faces)} faces")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for mt in mats:
        me.materials.append(mt)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    cutter = None
    if cut is not None:
        bmesh.ops.recalc_face_normals(cut, faces=cut.faces)
        cme = bpy.data.meshes.new(name + "_cut")
        cut.to_mesh(cme)
        cut.free()
        for mt in mats:
            cme.materials.append(mt)
        cutter = bpy.data.objects.new(name + "_cut", cme)
        bpy.context.scene.collection.objects.link(cutter)
        cutter.hide_render = True
        mod = ob.modifiers.new("cut", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.use_self = True
        mod.use_hole_tolerant = True
        mod.material_mode = "INDEX"
        mod.object = cutter
    if bevel:
        mod = ob.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = segs
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(angle)
    if ob.modifiers:
        dg = bpy.context.evaluated_depsgraph_get()
        new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.clear()
        old = ob.data
        ob.data = new
        bpy.data.meshes.remove(old)
        new.name = name
    if cutter is not None:
        cme = cutter.data
        bpy.data.objects.remove(cutter, do_unlink=True)
        bpy.data.meshes.remove(cme)
    return ob


def bvh_of(objs):
    bm = bmesh.new()
    for o in objs:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        tmp.transform(o.matrix_world)
        me = bpy.data.meshes.new("_tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def bvh_bm(bm):
    """BVH of a bmesh being built, with outward face normals (so hit() returns real normals)."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    return BVHTree.FromBMesh(bm)


def hit(bvh, origin, direction):
    loc, nrm, _i, _d = bvh.ray_cast(Vector(origin), Vector(direction).normalized())
    if loc is None:
        raise RuntimeError(f"ray from {origin} along {direction} missed")
    if nrm.length < 1e-6:
        raise RuntimeError(f"ray from {origin}: zero normal (bmesh normals not computed)")
    return loc, nrm.normalized()


# ---------------------------------------------------------------- materials

def _bsdf(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _set(b, key, val):
    if key in b.inputs:
        b.inputs[key].default_value = val


def materials():
    M = {
        "body": S.material("M_DroneBody", (0.42, 0.41, 0.385), 0.44, specular=0.5),
        "dark": S.material("M_DroneDark", (0.026, 0.027, 0.030), 0.5, specular=0.45),
        "motor": S.material("M_Motor", (0.2, 0.2, 0.21), 0.34, metallic=0.9),
        "prop": S.material("M_Prop", (0.20, 0.205, 0.21), 0.28, specular=0.5),
        "gimbal": S.material("M_GimbalBlack", (0.012, 0.012, 0.013), 0.36, specular=0.5),
        "lens": S.material("M_Lens", (0.004, 0.005, 0.007), 0.0, specular=0.5),
        "led": S.material("M_LedFront", (0.9, 0.05, 0.03), 0.25),
        "ctrl": S.material("M_ControllerBody", (0.055, 0.057, 0.061), 0.58, specular=0.4),
    }
    b = _bsdf(M["lens"])
    _set(b, "Coat Weight", 1.0)
    _set(b, "Coat Roughness", 0.02)
    _set(b, "Alpha", 0.9)
    _set(b, "IOR", 1.6)
    _set(b, "Thin Film Thickness", 420.0)
    _set(b, "Thin Film IOR", 1.38)
    b = _bsdf(M["prop"])
    _set(b, "Alpha", 0.86)
    for m in (M["lens"],):
        for attr, val in (("use_raytrace_refraction", True), ("use_screen_refraction", True)):
            if hasattr(m, attr):
                setattr(m, attr, val)
    b = _bsdf(M["led"])
    for key in ("Emission Color", "Emission"):
        if key in b.inputs:
            b.inputs[key].default_value = (1.0, 0.06, 0.03, 1)
            break
    b.inputs["Emission Strength"].default_value = 3.0
    return M


# ---------------------------------------------------------------- finishing

def box_uv(bm):
    """World-scale box projection, 1 UV unit = 1 m."""
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        nv = f.normal
        k = max(range(3), key=lambda i: abs(nv[i]))
        a, b = [i for i in range(3) if i != k]
        for loop in f.loops:
            co = loop.vert.co
            loop[uv].uv = (co[a], co[b])


def assemble(name, parts, sharp_angle=40):
    """cm parts -> one metre-scale mesh, origin at the bottom centre of its footprint.

    Returns (object, origin) where origin is the old position (m) of the new origin."""
    sc = Matrix.Scale(CM, 4)
    print(name + ": part triangles", ", ".join(f"{p.name} {S.tri_count(p)}" for p in parts))
    if os.environ.get("DBG"):
        for p in parts:
            bm = bmesh.new()
            bm.from_mesh(p.data)
            bad = [e for e in bm.edges if not e.is_manifold]
            if bad:
                print(f"  {p.name}: {len(bad)} non-manifold, e.g. {[tuple(round(c, 2) for c in e.verts[0].co) for e in bad[:3]]}")
            bm.free()
    for p in parts:
        p.matrix_world = sc @ p.matrix_world
    ob = S.join(name, parts)
    lo, hi = S.bbox(ob)
    origin = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    S.set_origin(ob, origin)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    box_uv(bm)
    bm.to_mesh(ob.data)
    bm.free()
    S.tidy(ob, sharp_angle)
    return ob, origin


def report(ob, path):
    lo, hi = S.bbox(ob)
    d = (hi - lo) * 100
    print("=" * 60)
    print(f"{ob.name}: exported {path}")
    print(f"{ob.name}: materials {[m.name for m in ob.data.materials]}")
    print(f"{ob.name}: triangles {S.tri_count(ob)}")
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    print(f"{ob.name}: non-manifold edges {sum(1 for e in bm.edges if not e.is_manifold)}, "
          f"UV layers {len(ob.data.uv_layers)}")
    bm.free()
    print(f"{ob.name}: bbox cm  X {lo.x*100:.1f}..{hi.x*100:.1f}  Y {lo.y*100:.1f}..{hi.y*100:.1f}"
          f"  Z {lo.z*100:.1f}..{hi.z*100:.1f}")
    print(f"{ob.name}: size cm  {d.x:.1f} x {d.y:.1f} x {d.z:.1f}")
    print("=" * 60)


def export(ob, args):
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, ob.name + ".fbx")
    S.export_fbx(ob, path)
    report(ob, path)
    return path


def shoot(ob, path, view_dir=None, lens=60, margin=1.08, loc=None, target=None):
    """Re-aim the preview camera set up by S.render_preview and render again."""
    sc = bpy.context.scene
    cam = sc.camera
    cam.data.lens = lens
    if loc is not None:
        cam.location = Vector(loc)
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    else:
        v = Vector(view_dir).normalized()
        lo, hi = S.bbox(ob)
        centre = (lo + hi) / 2
        cam.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
        corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        dg = bpy.context.evaluated_depsgraph_get()
        co, _ = cam.camera_fit_coords(dg, [c for p in corners for c in p])
        cam.location = centre + (Vector(co) - centre) * margin
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------- drone v2: lofts, profiles, shelf scene

def mirror_half(half):
    """Half outline [(y, z)] from bottom centre (y=0) round +y to top centre (y=0) -> closed CCW outline."""
    return list(half) + [(-y, z) for y, z in reversed(half[1:-1])]


def end_curve(u, p):
    """Superelliptic end: scale factor at fraction u (0 at the start of the rounding, 1 at the tip)."""
    u = min(max(u, 0.0), 1.0)
    return (1.0 - u ** p) ** (1.0 / p)


def end_stations(x_flat, x_end, n, p):
    """Stations between the start of an end rounding and (excluding) its tip, dense towards the tip."""
    out = []
    for k in range(1, n):
        th = k / n * math.pi / 2
        u = math.sin(th) ** (2.0 / p)
        out.append(x_flat + u * (x_end - x_flat))
    return out


def loft(bm, stations, section, cap0, cap1, slot=0):
    """Skin section(x) -> [(y, z)] (constant length) along x; caps as for add_grid."""
    rings = [[(x, y, z) for y, z in section(x)] for x in stations]
    return add_grid(bm, rings, cap0, cap1, slot)


def naca(x, t):
    """NACA 4-digit half thickness at chord fraction x for thickness ratio t (max = t/2)."""
    return 5 * t * (0.2969 * math.sqrt(max(x, 0.0)) - 0.126 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3
                    - 0.1036 * x ** 4)


def foil(h, t, n=10, blunt=0.05):
    """Closed symmetric aerofoil section [(a, b)]: chord h along a (leading edge at +h/2), max thickness t."""
    xs = [0.5 * (1 - math.cos(math.pi * k / n)) for k in range(n + 1)]

    def half(x):
        return t * naca(x, 1.0) + blunt * x / 2
    side1 = [(h / 2 - x * h, half(x)) for x in xs]
    side2 = [(h / 2 - x * h, -half(x)) for x in reversed(xs[1:])]
    return side1 + side2


def conform_strip(bvh, pts, dirn, prof, bm, lift=0.0, slot=0):
    """A small swept strip (rib, bead) lying on a surface: raycast each point of pts along dirn."""
    path, nrm0 = [], None
    for p in pts:
        loc, n = hit(bvh, Vector(p) - Vector(dirn) * 20, dirn)
        path.append(loc + n * lift)
        nrm0 = nrm0 or n
    add_tube(bm, path, lambda u: prof, hint=tuple(nrm0), slot=slot)


def oak():
    """Light oak for preview shelves, grain along world Y."""
    m = S.material("_Oak", (0.62, 0.43, 0.25), 0.55)
    nt = m.node_tree
    bsdf = _bsdf(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 0.025, 1.0)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 110.0
    wave.inputs["Distortion"].default_value = 14.0
    wave.inputs["Detail"].default_value = 4.0
    wave.inputs["Detail Scale"].default_value = 1.5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.50, 0.32, 0.17, 1)
    ramp.color_ramp.elements[1].color = (0.64, 0.45, 0.27, 1)
    ramp.color_ramp.elements[0].position = 0.2
    ramp.color_ramp.elements[1].position = 0.75
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def area_light(name, loc, target, energy, size, color=(1.0, 0.86, 0.7), shape="RECTANGLE", size_y=None):
    light = bpy.data.lights.new(name, "AREA")
    light.shape = shape
    light.size = size
    if size_y is not None:
        light.size_y = size_y
    light.energy = energy
    light.color = color
    ob = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = Vector(loc)
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob
