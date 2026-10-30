"""Toon: flat 2D-cartoon drawings made from simple 3D shapes (blender/draw.py renders them).

The look: every surface a flat colour (an emission shader seen through the Standard view, so a colour renders exactly as
its hex), inked by Line Art: a heavier outer line on contours, a lighter inner line on creases, material edges and
intersections, both resampled, smoothed, tapered at the ends and given a faint, slow hand wobble that never boils.
Marks that are already ink (eyes, brows, mouths, seams) live in the `face` collection, which Line Art never draws.
Ink keeps its weight on screen: each inked group's radius is set from its distance to the camera and the lens.

Nothing here names a film. The film's style (films/<id>/data/look/toon.json) gives
  colors   {"name": "#rrggbb", ...}: every colour a drawing uses, by name (a "#hex" is taken as is)
  ink      {"color": "ink", "px": 6.3, "inner": 0.66, "taper": 0.3, "smooth": 0.6, "wobble": 0.012,
            "wobble_scale": 0.025, "sample": 0.012, "chain": 0.001}  (px: the outer line's width on a 1920 px wide
            frame; chain: Line Art joins stroke ends closer than this, as a fraction of the frame; raise it a little
            when tapered lines on curved shapes such as hands come out dashed)
  cast     {"<who>": {...person spec, see Person...}}

    t = Toon(scene, style)
    t.blob("rock", (0, 0, 0), (3, 2, 1), "rock", shape=t.lumpy(0.2, seed=3))
    t.card("door", t.rect(1, 2, 0, 1), 0.02, "door", loc=(0, 2.5, 0))
    cam = t.camera("cam", (0, -9, 1.6), (0, 0, 1.5), lens=60)
    t.ink(cam)            # one outer + one inner Line Art pass per inked group (t.group(...)), weights held on screen
"""
from __future__ import annotations

import json
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector

from . import hand as handlib

D2R = math.radians
SENSOR = 36.0          # mm, the camera's sensor width (fit horizontal)
INK_K = 0.71           # measured: a Line Art radius r draws a line INK_K * r * px_per_m wide
INK_DEFAULTS = {"color": "#161412", "px": 6.3, "inner": 0.66, "taper": 0.3, "smooth": 0.6, "wobble": 0.012,
                "wobble_scale": 0.025, "sample": 0.012, "chain": 0.001}


def srgb_to_linear(h: str) -> tuple[float, float, float, float]:
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda x: x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    return (*[f(x) for x in c], 1.0)


def rect(w, h, cx=0.0, cz=0.0):
    """A rectangle's corners in the XZ plane, centred at (cx, cz)."""
    return [(cx - w / 2, cz - h / 2), (cx + w / 2, cz - h / 2), (cx + w / 2, cz + h / 2), (cx - w / 2, cz + h / 2)]


def ring(cx, cz, rx, rz, n=64, a0=0.0, a1=2 * math.pi):
    """Points on an ellipse (or an arc of one) in the XZ plane."""
    full = abs(a1 - a0 - 2 * math.pi) < 1e-9
    k = n if full else n - 1
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / k), cz + rz * math.sin(a0 + (a1 - a0) * i / k)) for i in range(n)]


def leaf(w, h, n=16):
    """A pointed leaf / lens outline in XZ, its base at the origin, pointing up +Z."""
    right = [(w * math.sin(math.pi * k / n), h * k / n) for k in range(n + 1)]
    left = [(-w * math.sin(math.pi * k / n), h * k / n) for k in range(n - 1, 0, -1)]
    return right + left


def densify(pts, n=6):
    """Points along a polyline, n per segment (for marks laid on curved surfaces)."""
    out = []
    for a, b in zip(pts, pts[1:]):
        out += [tuple(a[j] + (b[j] - a[j]) * i / n for j in range(len(a))) for i in range(n)]
    out.append(tuple(pts[-1]))
    return out


class Toon:
    rect = staticmethod(rect)
    ring = staticmethod(ring)
    leaf = staticmethod(leaf)
    densify = staticmethod(densify)

    def __init__(self, scene, style: dict):
        self.sc = scene
        self.colors = dict(style.get("colors", {}))
        self.inkspec = {**INK_DEFAULTS, **style.get("ink", {})}
        self.cast = style.get("cast", {})
        self.mats: dict[str, bpy.types.Material] = {}
        self.groups: list[tuple[bpy.types.Collection, float | None]] = []
        self.face = self._coll("face")
        self.face.lineart_usage = "EXCLUDE"
        self.cut = self._coll("cutters", render=False)
        self.plain = self._coll("plain")      # flat, never inked (skies, glows, beams)
        self.occluders: list = []             # shapes that hide every group's ink (a sea plane), drawing none of their own
        self.cur = self.group("set")

    # ---- collections ----
    def _coll(self, name, render=True):
        c = bpy.data.collections.new(name)
        self.sc.collection.children.link(c)
        c.hide_render = not render
        return c

    def group(self, name, distance: float | None = None):
        """A new inked group (its own Line Art passes, weight held at its distance; None: measured from its objects)
        and the collection new shapes go into."""
        c = self._coll(name)
        self.groups.append((c, distance))
        self.cur = c
        return c

    def occluder(self, o):
        """o hides the ink of every group behind it (Line Art only sees the collection it draws, so a sea in its own
        group would not hide a hull's submerged outline), and draws no ink of its own."""
        o.lineart.usage = "OCCLUSION_ONLY"
        self.occluders.append(o)
        return o

    def use(self, c):
        self.cur = c
        return c

    @staticmethod
    def link(o, c):
        for uc in list(o.users_collection):
            uc.objects.unlink(o)
        c.objects.link(o)

    # ---- colour ----
    def hex(self, name: str) -> str:
        if name.startswith("#"):
            return name
        if name not in self.colors:
            raise KeyError(f"toon: no colour '{name}' in the film's style (data/look/toon.json colors)")
        return self.colors[name]

    def lin(self, name: str):
        return srgb_to_linear(self.hex(name))

    def mat(self, name: str, alpha: float = 1.0):
        key = f"{name}@{alpha}"
        if key in self.mats:
            return self.mats[key]
        m = bpy.data.materials.new(f"flat {key}")
        try:
            m.use_nodes = True
        except Exception:
            pass
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs[0].default_value = self.lin(name)
        em.inputs[1].default_value = 1.0
        if alpha < 1.0:
            tr = nt.nodes.new("ShaderNodeBsdfTransparent")
            mix = nt.nodes.new("ShaderNodeMixShader")
            mix.inputs[0].default_value = alpha
            nt.links.new(tr.outputs[0], mix.inputs[1])
            nt.links.new(em.outputs[0], mix.inputs[2])
            nt.links.new(mix.outputs[0], out.inputs[0])
            for attr, v in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
                try:
                    setattr(m, attr, v)
                except (AttributeError, TypeError):
                    pass
        else:
            nt.links.new(em.outputs[0], out.inputs[0])
        m.diffuse_color = self.lin(name)
        self.mats[key] = m
        return m

    # ---- objects ----
    def empty(self, name, loc=(0, 0, 0), parent=None, rot=(0, 0, 0), scale=(1, 1, 1)):
        e = bpy.data.objects.new(name, None)
        self.sc.collection.objects.link(e)
        e.parent = parent
        e.location = loc
        e.rotation_euler = rot
        e.scale = scale
        return e

    def _mesh(self, name, bm, col, c, parent, loc, rot, scale, smooth, alpha=1.0):
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        if smooth:
            for p in me.polygons:
                p.use_smooth = True
        o = bpy.data.objects.new(name, me)
        (c or self.cur).objects.link(o)
        o.parent = parent
        o.location = loc
        o.rotation_euler = rot
        o.scale = scale
        if col:
            me.materials.append(self.mat(col, alpha))
        return o

    def blob(self, name, loc, scale, col, c=None, parent=None, rot=(0, 0, 0), shape=None, n=2.0, seg=64, alpha=1.0):
        """A sphere scaled to `scale` (or a superellipsoid of exponent n: a rounded box as n grows), optionally
        reshaped per vertex by shape(v) on the unit shape."""
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(8, seg // 2), radius=1)
        for v in bm.verts:
            if n != 2.0:
                q = sum(abs(a) ** n for a in v.co) ** (1 / n)
                v.co = v.co / max(q, 1e-6)
            if shape:
                v.co = Vector(shape(v.co.copy()))
        return self._mesh(name, bm, col, c, parent, loc, rot, scale, True, alpha)

    def card(self, name, pts, depth, col, c=None, parent=None, loc=(0, 0, 0), rot=(0, 0, 0), alpha=1.0):
        """A flat cut-out: polygon pts [(x, z)] in the XZ plane facing -Y, `depth` thick (towards +Y)."""
        bm = bmesh.new()
        vs = [bm.verts.new((x, 0, z)) for x, z in pts]
        f = bm.faces.new(vs)
        if f.normal.y > 0:
            f.normal_flip()
        if depth > 0:
            r = bmesh.ops.extrude_face_region(bm, geom=[f])
            bmesh.ops.translate(bm, verts=[e for e in r["geom"] if isinstance(e, bmesh.types.BMVert)], vec=(0, depth, 0))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return self._mesh(name, bm, col, c, parent, loc, rot, (1, 1, 1), False, alpha)

    def cyl(self, name, loc, r, depth, col, c=None, parent=None, rot=(0, 0, 0), r2=None, seg=64, caps=True, alpha=1.0):
        """A cylinder (or a frustum, top radius r2) along local Z, centred at loc."""
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=caps, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=depth)
        o = self._mesh(name, bm, col, c, parent, loc, rot, (1, 1, 1), True, alpha)
        return o

    def sleeve(self, name, loc, r, depth, col, c=None, parent=None, rot=(0, 0, 0), r2=None, wall=0.022, seg=48):
        """A hollow frustum along local Z (bottom radius r, top r2), open at the bottom: a cuff whose opening inks as
        a ring (its rim and the edge of the hole are creases); the top closed."""
        r2 = r if r2 is None else r2
        bm = bmesh.new()

        def ring_(rad, z):
            return [bm.verts.new((rad * math.cos(2 * math.pi * i / seg), rad * math.sin(2 * math.pi * i / seg), z))
                    for i in range(seg)]
        ob, ot = ring_(r, -depth / 2), ring_(r2, depth / 2)
        ib, it = ring_(r - wall, -depth / 2), ring_(r2 - wall, depth / 2 - wall)
        for a, b in ((ob, ot), (it, ib), (ib, ob)):
            for i in range(seg):
                j = (i + 1) % seg
                bm.faces.new((a[i], a[j], b[j], b[i]))
        bm.faces.new(ot)
        bm.faces.new(list(reversed(it)))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return self._mesh(name, bm, col, c, parent, loc, rot, (1, 1, 1), True)

    def box(self, name, loc, size, col, c=None, parent=None, rot=(0, 0, 0)):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1)
        return self._mesh(name, bm, col, c, parent, loc, rot, size, False)

    def torus(self, name, loc, R, r, col, c=None, parent=None, rot=(0, 0, 0), seg=64, arc=2 * math.pi):
        """A ring (or an arc of one) of tube radius r round a circle of radius R in the XY plane."""
        bm = bmesh.new()
        n2 = 12
        full = abs(arc - 2 * math.pi) < 1e-9
        rings = []
        for i in range(seg if full else seg + 1):
            a = arc * i / seg
            ca, sa = math.cos(a), math.sin(a)
            rings.append([bm.verts.new(((R + r * math.cos(b)) * ca, (R + r * math.cos(b)) * sa, r * math.sin(b)))
                          for b in [2 * math.pi * j / n2 for j in range(n2)]])
        pairs = list(zip(rings, rings[1:] + ([rings[0]] if full else [])))
        for ra, rb in pairs:
            for j in range(n2):
                bm.faces.new((ra[j], ra[(j + 1) % n2], rb[(j + 1) % n2], rb[j]))
        if not full:
            for rr in (rings[0], rings[-1]):
                bm.faces.new(rr)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return self._mesh(name, bm, col, c, parent, loc, rot, (1, 1, 1), True)

    def line(self, name, pts, parent=None, width=0.006, col="ink", c=None, poly=False, closed=False, taper=True):
        """An inked mark: a tube through 3D points (a brush stroke, thin at both ends unless taper=False)."""
        cu = bpy.data.curves.new(name, "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = width
        cu.bevel_resolution = 4
        cu.use_fill_caps = True
        sp = cu.splines.new("POLY" if poly else "NURBS")
        sp.points.add(len(pts) - 1)
        sp.use_cyclic_u = closed
        if not poly:
            sp.order_u = min(3, len(pts))
            sp.use_endpoint_u = True
        for i, (p, co) in enumerate(zip(sp.points, pts)):
            p.co = (*co, 1)
            if taper and not closed and len(pts) > 2:
                p.radius = 0.3 + 0.7 * math.sin(math.pi * i / (len(pts) - 1)) ** 0.7
        o = bpy.data.objects.new(name, cu)
        (c or self.face).objects.link(o)
        o.parent = parent
        cu.materials.append(self.mat(self._inkname() if col == "ink" else col))
        return o

    def _inkname(self):
        c = self.inkspec["color"]
        return c if c.startswith("#") or c in self.colors else INK_DEFAULTS["color"]

    def boolean(self, o, cutter, op="DIFFERENCE"):
        b = o.modifiers.new(op.lower(), "BOOLEAN")
        b.operation = op
        b.object = cutter
        b.solver = "EXACT"
        self.link(cutter, self.cut)
        cutter.hide_render = True
        cutter.display_type = "WIRE"
        return b

    # ---- shape functions (for blob(shape=...)) ----
    @staticmethod
    def lumpy(amount=0.15, seed=1, freq=3):
        """Irregular rock: the unit shape pushed in and out by a few random lobes."""
        rnd = random.Random(seed)
        lobes = [(Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))).normalized(), rnd.uniform(-1, 1))
                 for _ in range(freq * 3)]

        def f(v):
            n = v.normalized() if v.length > 1e-6 else v
            k = 1 + amount * sum(w * max(0.0, n.dot(d)) ** 3 for d, w in lobes)
            return tuple(v * k)
        return f

    @staticmethod
    def teardrop(power=1.5):
        """Pointed towards -Z."""
        def f(v):
            x, y, z = v
            if z < 0:
                k = (1 + z) ** power
                x *= k
                y *= k
            return (x, y, z)
        return f

    @staticmethod
    def flat_bottom(z0=-0.3):
        def f(v):
            x, y, z = v
            return (x, y, max(z, z0))
        return f

    # ---- surfaces ----
    def update(self):
        bpy.context.view_layer.update()

    def onto(self, target, p_parent, d_parent=(0, 1, 0), lift=0.004):
        """Project a point (in target's parent space) along d onto target's surface: (point, normal) in parent space."""
        self.update()
        d_parent = Vector(d_parent).normalized()
        M = target.matrix_basis
        Mi = M.inverted()
        o = Mi @ (Vector(p_parent) - d_parent * 5)
        d = (Mi.to_3x3() @ d_parent).normalized()
        hit, loc, nrm, _ = target.ray_cast(o, d)
        if not hit:
            raise RuntimeError(f"toon: no hit on {target.name} at {tuple(p_parent)}")
        n = (M.to_3x3().inverted().transposed() @ nrm).normalized()
        return M @ loc + n * lift, n

    @staticmethod
    def facing(n):
        """The rotation turning a card's -Y normal onto n."""
        return Vector((0, -1, 0)).rotation_difference(Vector(n)).to_euler()

    @staticmethod
    def orient(n, roll=0.0, up=(0, 0, 1)):
        """Local -Y along n, local +Z up the surface, rolled `roll` degrees about n."""
        n = Vector(n).normalized()
        u = Vector(up)
        z = (u - n * n.dot(u)).normalized()
        z = Quaternion(n, D2R(roll)) @ z
        y = -n
        x = y.cross(z)
        return Matrix((x, y, z)).transposed().to_euler()

    def mark_on(self, name, target, pts, parent, d=(0, 1, 0), lift=0.005, width=0.006, col="ink", n=6, taper=True,
                poly=False, closed=False):
        """An ink mark laid on target's surface through pts [(x, y, z)] (target's parent space), projected along d."""
        dense = densify(pts, n) if n > 1 and not poly else [tuple(p) for p in pts]
        return self.line(name, [tuple(self.onto(target, Vector(p), d, lift)[0]) for p in dense], parent, width, col,
                         poly=poly, closed=closed, taper=taper)

    # ---- show / hide over time ----
    @staticmethod
    def show(o, on=(), off=()):
        for f in on:
            o.hide_render = False
            o.keyframe_insert("hide_render", frame=f)
        for f in off:
            o.hide_render = True
            o.keyframe_insert("hide_render", frame=f)

    # ---- camera, world, ink, render ----
    def camera(self, name, loc, at, lens=50.0, roll=0.0):
        d = bpy.data.cameras.new(name)
        d.lens = lens
        d.sensor_fit = "HORIZONTAL"
        d.sensor_width = SENSOR
        d.clip_end = 2000
        o = bpy.data.objects.new(name, d)
        self.sc.collection.objects.link(o)
        o.location = loc
        q = (Vector(at) - Vector(loc)).to_track_quat("-Z", "Y")
        if roll:
            q = q @ Quaternion((0, 0, 1), D2R(roll))
        o.rotation_euler = q.to_euler()
        self.sc.camera = o
        return o

    def world(self, col):
        w = bpy.data.worlds.new("toon world")
        self.sc.world = w
        try:
            w.use_nodes = True
        except Exception:
            pass
        bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
        bg.inputs[0].default_value = self.lin(col)
        bg.inputs[1].default_value = 1.0
        return w

    def _distance(self, c, cam):
        pts = []
        self.update()
        for o in c.all_objects:
            if o.type in {"MESH", "CURVE"} and o not in self.occluders:
                pts += [o.matrix_world @ Vector(b) for b in o.bound_box]
        if not pts:
            return None
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        centre = (lo + hi) / 2
        fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
        return max(0.05, (centre - cam.matrix_world.translation).dot(fwd))

    def radius_for(self, distance, cam, px=None):
        """The Line Art radius that draws a line `px` wide (on a 1920 px wide frame) at `distance` from cam."""
        px = self.inkspec["px"] if px is None else px
        ppm = 1920 * cam.data.lens / (SENSOR * distance)
        return px / (INK_K * ppm)

    def ink(self, cam, extra=None):
        """Line Art for every inked group: an outer pass (contours) and an inner pass (creases, material edges,
        intersections), each resampled, smoothed, tapered and wobbled. Weights held on screen at each group's
        distance from cam (measured, or the group's own)."""
        s = self.inkspec
        if os.environ.get("TOON_NO_INK"):      # (for looking at the flat colour alone)
            return []
        inkm = bpy.data.materials.new("ink")
        bpy.data.materials.create_gpencil_data(inkm)
        inkm.grease_pencil.color = self.lin(self._inkname())
        made = []
        dists = {c.name: dist or self._distance(c, cam) for c, dist in self.groups}
        for c, dist in self.groups:
            if not any(o.type in {"MESH", "CURVE"} and o not in self.occluders for o in c.all_objects):
                continue
            for o in self.occluders:
                if c not in o.users_collection:
                    c.objects.link(o)
            d = dists[c.name]
            r_out = self.radius_for(d, cam)
            for inner in (False, True):
                lc = bpy.context.view_layer.layer_collection.children[c.name]
                bpy.context.view_layer.active_layer_collection = lc
                bpy.ops.object.grease_pencil_add(type="LINEART_COLLECTION")
                gp = bpy.context.active_object
                gp.name = f"ink {c.name} {'inner' if inner else 'outer'}"
                self.link(gp, self.sc.collection)
                la = next(m for m in gp.modifiers if m.type == "LINEART")
                la.source_type = "COLLECTION"
                la.source_collection = c
                la.use_contour = not inner
                la.use_crease = la.use_material = la.use_intersection = inner
                la.use_loose = False
                la.use_crease_on_smooth = False
                la.radius = r_out * (s["inner"] if inner else 1.0)
                la.chaining_image_threshold = s["chain"]
                gp.data.materials.clear()
                gp.data.materials.append(inkm)
                la.target_material = inkm
                k = d / 8.6     # resampling and wobble scale with distance, so they look the same on screen
                sm = gp.modifiers.new("sample", "GREASE_PENCIL_SIMPLIFY")
                sm.mode = "SAMPLE"
                sm.length = s["sample"] * k
                if s["smooth"] > 0:
                    so = gp.modifiers.new("smooth", "GREASE_PENCIL_SMOOTH")
                    so.factor = s["smooth"]
                    so.step = 3
                if s["taper"] > 0:
                    th = gp.modifiers.new("taper", "GREASE_PENCIL_THICKNESS")
                    th.thickness_factor = s["taper"]
                    th.use_custom_curve = True
                    cm = th.custom_curve
                    pts = cm.curves[0].points
                    pts[0].location = (0, 1)
                    pts[1].location = (1, 1)
                    pts.new(0.12, 0)
                    pts.new(0.88, 0)
                    cm.update()
                if s["wobble"] > 0:
                    nz = gp.modifiers.new("wobble", "GREASE_PENCIL_NOISE")
                    nz.factor = s["wobble"] * k
                    nz.factor_thickness = 0.0
                    nz.factor_strength = 0.0
                    nz.factor_uvs = 0.0
                    nz.noise_scale = s["wobble_scale"]
                    nz.use_random = False
                made.append((gp.name, round(la.radius, 4), round(d, 2)))
        return made

    def render_settings(self, res, taa=4):
        sc = self.sc
        try:
            sc.render.engine = "BLENDER_EEVEE"
        except TypeError as e:
            raise RuntimeError(f"toon: EEVEE not available ({e})")
        sc.eevee.taa_render_samples = taa
        for k, v in (("view_transform", "Standard"), ("look", "None")):
            try:
                setattr(sc.view_settings, k, v)
            except TypeError:
                pass
        sc.view_settings.exposure = 0.0
        sc.view_settings.gamma = 1.0
        sc.render.use_motion_blur = False
        sc.render.resolution_x, sc.render.resolution_y = res
        sc.render.resolution_percentage = 100
        sc.render.film_transparent = False
        im = sc.render.image_settings
        im.file_format = "PNG"
        im.color_mode = "RGB"
        im.color_depth = "8"
        im.compression = 15


# ---------------------------------------------------------------- hands

class Hand:
    """A cartoon hand (lib/hand.py's shape and poses) as a mesh per pose, shown in turn: a coarse cage of palm,
    fingers and thumb under a subdivision surface (clean even faces, so the ink runs in one smooth line).

    Hand(t, side, parent, skin, size=0.62, pose="rest", subdiv=2, detail="full"): side -1 a right hand, +1 a left
    (Person's sides); size: its scale (about the wrist to the middle fingertip); subdiv 3 for a close-up; detail
    "mitten" for a hand small on screen (the fingers as one). Built in parent's space, the wrist at its origin, the
    fingers along -Z, the palm facing -Y. .pose(pose, frame) shows a pose (a name in lib/hand.POSES or a dict), keyed
    at frame if given; .anchor(name) is a point to hold things by (lib/hand.anchor) in parent space, for the pose shown.
    """

    def __init__(self, t: Toon, side, parent, skin, size=0.62, pose="rest", name="hand", c=None, subdiv=2,
                 detail="full"):
        self.t, self.side, self.parent, self.skin, self.size, self.name = t, side, parent, skin, size, name
        self.subdiv, self.detail = subdiv, detail
        self.c = c or t.cur
        self.meshes: dict[str, list] = {}
        self.current = None
        self.pose(pose)

    @staticmethod
    def _key(pose):
        return pose if isinstance(pose, str) else json.dumps(pose, sort_keys=True)

    def pose(self, pose, frame=None):
        key = self._key(pose)
        if key not in self.meshes:
            self.meshes[key] = self._build(pose, len(self.meshes))
            for o in self.meshes[key]:
                o.hide_render = bool(self.current is not None)     # not shown before now
        for k, objs in self.meshes.items():
            for o in objs:
                if frame is not None and not (o.animation_data and o.animation_data.action):
                    o.keyframe_insert("hide_render", frame=1)      # holds what it was until now
                o.hide_render = k != key
                if frame is not None:
                    o.keyframe_insert("hide_render", frame=frame)
        self.current = pose
        return self

    def anchor(self, name=None):
        p, _ = handlib.anchor(self.current, name)
        return Vector((p[0] * self.side, p[1], p[2])) * self.size

    def _build(self, pose, i):
        objs = []
        for part, (verts, faces) in handlib.cage(pose, self.detail).items():
            bm = bmesh.new()
            vs = [bm.verts.new(Vector((x * self.side, y, z)) * self.size) for x, y, z in verts]
            for f in faces:
                bm.faces.new([vs[k] for k in f])
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            name = f"{self.name} {part}{i}"
            o = self.t._mesh(name, bm, self.skin, self.c, self.parent, (0, 0, 0), (0, 0, 0), (1, 1, 1), True)
            ss = o.modifiers.new("subsurf", "SUBSURF")
            ss.levels = ss.render_levels = self.subdiv
            objs.append(o)
        return objs


# ---------------------------------------------------------------- people

EXPRESSIONS = {
    # name: (brows, mouth)
    "neutral": ("neutral", "neutral"),
    "smile": ("raised", "smile"),
    "worried": ("worried", "worried"),
    "sad": ("sad", "frown"),
    "tired": ("tired", "flat"),
    "surprised": ("raised", "open"),
    "stern": ("angry", "flat"),
    "content": ("neutral", "smile"),
}
BROWS = {   # (inner, middle, outer) heights above the eye line, as fractions of the head radius
    "neutral": (0.29, 0.34, 0.3),
    "raised": (0.38, 0.43, 0.36),
    "worried": (0.38, 0.36, 0.27),
    "sad": (0.36, 0.33, 0.25),
    "angry": (0.24, 0.3, 0.34),
    "tired": (0.27, 0.3, 0.27),
}
MOUTHS = {  # points (x, z) as fractions of the head radius, z below the eye line
    "neutral": [(-0.18, -0.4), (0.0, -0.43), (0.17, -0.4)],
    "smile": [(-0.2, -0.37), (-0.1, -0.43), (0.0, -0.45), (0.1, -0.43), (0.19, -0.37)],
    "worried": [(-0.17, -0.44), (-0.07, -0.4), (0.03, -0.44), (0.15, -0.41)],
    "frown": [(-0.17, -0.45), (-0.08, -0.41), (0.0, -0.4), (0.08, -0.41), (0.16, -0.45)],
    "flat": [(-0.16, -0.42), (0.16, -0.42)],
    "open": None,   # a small dark oval
}


class Person:
    """A cartoon person: a soft-jawed head with dot eyes and ink marks for brows and mouth, optional hair, beard,
    moustache and cap; a rounded-box torso with collar, buttons and pockets; sleeved arms on shoulder/elbow/wrist pivots
    with posable hands (Hand: lib/hand.POSES); optional legs. Everything hangs off `root` (feet at its origin when legs are
    on; otherwise the torso stands on it as a medium-shot bust).

    spec (the film's cast entry; colours by name):
      skin, coat, collar ("coat"), buttons (None), pockets (True), trousers, boots,
      hair {"style": "cap" | "sides" | "none", "color"}, beard {"color"} | None, moustache {"color"} | None,
      cap {"color", "band", "visor", "badge"} | None, brows {"color", "width"}, nose ("mark" | "round"),
      eye (size), build (torso width), legs (bool),
      hand {"size": 0.75, "subdiv": 2 (3 for close-ups), "detail": "full" | "mitten" (for a small, far figure)}

    Poses and faces are keyed at frames (or set once for a still): expression(name, frame), eyes(state, frame),
    blink(frame), arm(side, elbow, hand, frame, palm, fingers), hand(side, pose, frame), head(turn, tilt, nod, frame);
    hold(side, obj, offset, rot, at) puts a prop in a hand. Points are in the person's own space:
    x to the person's left (screen right when facing the camera), -y in front, z up.
    """

    def __init__(self, t: Toon, spec: dict, name="person", loc=(0, 0, 0), rot=(0, 0, 0), parent=None, scale=1.0,
                 expression="neutral", hands=("rest", "rest")):
        self.t, self.s, self.name = t, spec, name
        self.legs = bool(spec.get("legs", False))
        self.root = t.empty(name, loc, parent, rot=rot, scale=(scale,) * 3)
        self.base = 0.95 if self.legs else 0.0        # torso lift above the root when standing on legs
        self.parts: dict[str, object] = {}
        self.hands: dict[int, Hand] = {}
        self._torso()
        self._head()
        self.arms = {s: self._arm(s, hands[0 if s < 0 else 1]) for s in (-1, 1)}
        for s, a in self.arms.items():
            z = a["shoulder"].location.z
            self.arm(s, (0.58 * s, 0.02, z - 0.58), (0.62 * s, -0.06, z - 1.14))
        if self.legs:
            self._legs()
        self._expr_objs: dict[str, list] = {}
        self._faces()
        self.expression(expression)
        self.eyes("open")

    # -- body --
    def _torso(self):
        t, s = self.t, self.s
        w = s.get("build", 0.6)
        b = self.base

        def shape(v):
            x, y, z = v
            if z > 0.35:
                x *= 1 - 0.5 * (z - 0.35) ** 1.6
            return (x, y, z)
        if self.legs:
            self.torso = t.blob(f"{self.name} torso", (0, 0, b + 0.52), (w, 0.38, 0.72), s.get("coat", "coat"),
                                parent=self.root, shape=shape, n=2.6)
            self.neck_z = b + 1.18
        else:
            self.torso = t.blob(f"{self.name} torso", (0, 0, 0.32), (w, 0.38, 1.12), s.get("coat", "coat"),
                                parent=self.root, shape=shape, n=2.6)
            self.neck_z = 1.43
        t.cyl(f"{self.name} neck", (0, 0.02, self.neck_z), 0.14, 0.24, s.get("skin", "skin"), parent=self.root)
        col = s.get("collar", s.get("coat", "coat"))
        for k in (-1, 1):
            p, nrm = t.onto(self.torso, (0.1 * k, 0, self.neck_z - 0.1), lift=0.0)
            flap = [(0.0, 0.03), (0.2 * k, 0.0), (0.15 * k, -0.17), (0.02 * k, -0.06)]
            t.card(f"{self.name} collar{k}", flap, 0.02, col, parent=self.root, loc=p - nrm * 0.005,
                   rot=(D2R(-24), D2R(-6 * k), 0))
        top, bot = self.neck_z - 0.16, (b + 0.0 if self.legs else 0.3)
        zs = [top + (bot - top) * i / 3 for i in range(4)]
        t.mark_on(f"{self.name} placket", self.torso, [(0.0, 0, z) for z in zs], self.root, lift=0.006, width=0.0045)
        if s.get("buttons"):
            for i in range(3 if not self.legs else 4):
                z = top - 0.12 - i * (0.26 if not self.legs else 0.2)
                p, nrm = t.onto(self.torso, (0.06, 0, z), lift=0.0)
                bt = t.cyl(f"{self.name} button{i}", p, 0.03, 0.02, s["buttons"], parent=self.root, rot=t.facing(nrm))
                bt.rotation_euler.rotate_axis("X", D2R(90))
        if s.get("pockets", True):
            pz = (b + 0.62) if self.legs else 0.86
            for k in (-1, 1):
                cx = 0.3 * k
                t.mark_on(f"{self.name} pocket{k}", self.torso,
                          [(cx - 0.11, 0, pz - 0.05), (cx - 0.11, 0, pz - 0.27), (cx + 0.11, 0, pz - 0.27), (cx + 0.11, 0, pz - 0.05)],
                          self.root, lift=0.006, width=0.0045, poly=True, n=1, taper=False)
                t.mark_on(f"{self.name} flap{k}", self.torso,
                          [(cx - 0.125, 0, pz), (cx + 0.125, 0, pz), (cx + 0.125, 0, pz - 0.05), (cx - 0.125, 0, pz - 0.05)],
                          self.root, lift=0.006, width=0.0045, poly=True, closed=True, n=1, taper=False)

    def _arm(self, side, hand):
        t, s = self.t, self.s
        coat = s.get("coat", "coat")

        def sleeve(v):
            x, y, z = v
            k = 1 - 0.14 * (1 - z) / 2
            return (x * k, y * k, z)
        sh = t.empty(f"{self.name} shoulder{side}", (0.47 * side, 0, self.neck_z - 0.35), self.root)
        t.blob(f"{self.name} upper{side}", (0, 0, -0.29), (0.13, 0.13, 0.36), coat, parent=sh, shape=sleeve)
        el = t.empty(f"{self.name} elbow{side}", (0, 0, -0.58), sh)
        # the forearm: a sleeve from a round elbow, open at the cuff (its rim and hole ink as the cuff); in it the wrist,
        # which follows the forearm and ends in a ball the hand turns on (so a bent wrist stays inside the cuff)
        t.blob(f"{self.name} elbowball{side}", (0, 0, 0), (0.117, 0.117, 0.117), coat, parent=el)
        t.sleeve(f"{self.name} fore{side}", (0, 0, -0.26), 0.122, 0.52, coat, parent=el, r2=0.115)
        skin = s.get("skin", "skin")
        for o in (t.cyl(f"{self.name} wristskin{side}", (0, 0, -0.49), 0.074, 0.14, skin, parent=el, seg=32),
                  t.blob(f"{self.name} wristball{side}", (0, 0, -0.56), (0.074, 0.074, 0.074), skin, parent=el, seg=32)):
            o.lineart.usage = "NO_INTERSECTION"     # no ring where the hand's heel meets it
        wr = t.empty(f"{self.name} wrist{side}", (0, 0, -0.56), el)
        for o in (sh, el, wr):
            o.rotation_mode = "QUATERNION"
        hs = s.get("hand", {})
        self.hands[side] = Hand(t, side, wr, skin, size=hs.get("size", 0.75), pose=hand,
                                name=f"{self.name} hand{side}", subdiv=hs.get("subdiv", 2),
                                detail=hs.get("detail", "full"))
        return {"shoulder": sh, "elbow": el, "wrist": wr}

    def _legs(self):
        t, s = self.t, self.s
        self.hips = {}
        for k in (-1, 1):
            hp = t.empty(f"{self.name} hip{k}", (0.2 * k, 0, 0.95), self.root)
            t.blob(f"{self.name} thigh{k}", (0, 0, -0.24), (0.15, 0.15, 0.3), s.get("trousers", "trousers"), parent=hp)
            kn = t.empty(f"{self.name} knee{k}", (0, 0, -0.48), hp)
            t.blob(f"{self.name} shin{k}", (0, 0, -0.22), (0.13, 0.13, 0.28), s.get("trousers", "trousers"), parent=kn)
            t.blob(f"{self.name} boot{k}", (0, -0.08, -0.44), (0.15, 0.22, 0.09), s.get("boots", "boots"), parent=kn, n=2.6)
            for o in (hp, kn):
                o.rotation_mode = "QUATERNION"
            self.hips[k] = (hp, kn)

    @staticmethod
    def _q(frm, at):
        return Vector((0, 0, -1)).rotation_difference((Vector(at) - Vector(frm)).normalized())

    def _aim(self, arm, elbow_at, hand_at):
        sh, el = arm["shoulder"], arm["elbow"]
        qs = self._q(sh.location, elbow_at)
        qe = Vector((0, 0, -1)).rotation_difference(qs.inverted() @ (Vector(hand_at) - Vector(elbow_at)).normalized())
        sh.rotation_quaternion, el.rotation_quaternion = qs, qe
        return qs, qe

    def arm(self, side, elbow, hand, frame=None, palm=None, fingers=None):
        """Point the upper arm at `elbow` and the forearm at `hand` (the wrist; person space), and turn the hand so
        its palm faces `palm` (a direction; default: in and back, so a hanging hand shows its back) with the fingers
        along `fingers` (default: on from the forearm; a bent wrist otherwise). Keyed at frame if given."""
        a = self.arms[side]
        qs, qe = self._aim(a, elbow, hand)
        R = self.hand_frame(side, palm, Vector(fingers) if fingers else Vector(hand) - Vector(elbow))
        a["wrist"].rotation_quaternion = (qs @ qe).inverted() @ R.to_quaternion()
        if frame is not None:
            for k in ("shoulder", "elbow", "wrist"):
                a[k].keyframe_insert("rotation_quaternion", frame=frame)

    @staticmethod
    def hand_frame(side, palm, fingers):
        """The rotation (a 3x3 matrix) that turns a Hand built in its own frame so its palm faces `palm` and its
        fingers point along `fingers` (also for a Hand on its own, outside a Person)."""
        f = Vector(fingers).normalized()
        pd = Vector(palm) if palm else Vector((-side, 0.8, 0))
        y = -(pd - f * pd.dot(f))
        if y.length < 1e-6:       # palm given along the fingers: any turn will do
            y = f.orthogonal()
        y.normalize()
        z = -f
        return Matrix((y.cross(z), y, z)).transposed()

    def reach(self, side, target, palm, fingers, at=None, pole=None, frame=None):
        """Put the hand's anchor (`at`: grip, pinch, tip, palm, default the pose's own; or a point in the hand's space,
        such as the tip of something held) on target (person space), the palm facing `palm`, the fingers along
        `fingers`; the elbow solved (two-bone), bending towards `pole` (default: where the forearm runs most nearly on
        into the hand). Keyed at frame if given.
        Returns how far short the arm fell (0 when it reached)."""
        a = self.arms[side]
        R = self.hand_frame(side, palm, fingers)
        p = Vector(at) if isinstance(at, (tuple, list, Vector)) else self.hands[side].anchor(at)
        wrist = Vector(target) - R @ p
        S = a["shoulder"].location.copy()
        L1, L2 = -a["elbow"].location.z, -a["wrist"].location.z
        v = wrist - S
        d = v.length
        short = max(0.0, d - (L1 + L2) * 0.999)
        d = min(max(d, abs(L1 - L2) + 1e-3), (L1 + L2) * 0.999)
        u = v.normalized()
        x = (L1 * L1 - L2 * L2 + d * d) / (2 * d)
        if pole:
            pl = Vector(pole)
        else:       # the elbow that keeps the forearm most in line with the hand (the least bent wrist), a little low
            pl = (wrist - Vector(fingers).normalized() * L2) - (S + u * x) + Vector((side * 0.1, 0, -0.15))
        n = pl - u * pl.dot(u)
        n = n.normalized() if n.length > 1e-6 else Vector((0, 0, -1))
        elbow = S + u * x + n * math.sqrt(max(0.0, L1 * L1 - x * x))
        self.arm(side, elbow, S + u * d, frame, palm, fingers)
        return short

    def hand(self, side, pose, frame=None):
        """Show a hand pose (lib/hand.POSES name or dict), keyed at frame if given."""
        return self.hands[side].pose(pose, frame)

    def leg(self, side, knee, foot, frame=None):
        hp, kn = self.hips[side]
        qh = self._q(hp.location, knee)
        qk = Vector((0, 0, -1)).rotation_difference(qh.inverted() @ (Vector(foot) - Vector(knee)).normalized())
        hp.rotation_quaternion, kn.rotation_quaternion = qh, qk
        if frame is not None:
            hp.keyframe_insert("rotation_quaternion", frame=frame)
            kn.keyframe_insert("rotation_quaternion", frame=frame)

    def hold(self, side, obj, offset=(0, 0, 0), rot=(0, 0, 0), at=None):
        """Parent obj to a hand at its anchor (`at`: grip, pinch, tip, palm; default the pose's own) plus offset, in
        the hand's space (the fingers along -Z, the palm facing -Y, the thumb towards +X on the left hand, -X on the
        right). A bar held in a grip runs along X."""
        obj.parent = self.arms[side]["wrist"]
        obj.location = self.hands[side].anchor(at) + Vector(offset)
        obj.rotation_euler = rot
        return obj

    # -- head --
    def _head(self):
        t, s = self.t, self.s
        self.head = t.empty(f"{self.name} head", (0, 0.02, self.neck_z + 0.07), self.root)
        self.R, self.SX, self.HC = 0.55, 1.06, 0.5
        R, SX, HC = self.R, self.SX, self.HC
        skin = s.get("skin", "skin")

        def jaw(v):
            x, y, z = v
            if z < 0:
                k = -z
                x *= 1 - 0.17 * k ** 1.7
                y *= 1 - 0.06 * k
                z *= 1 + 0.05 * k
            return (x, y, z)
        self.skull = t.blob(f"{self.name} skull", (0, 0, HC), (R * SX, R, R), skin, parent=self.head, shape=jaw)
        for k in (-1, 1):
            ear = t.blob(f"{self.name} ear{k}", (0.565 * k, 0.03, HC - 0.03), (0.075, 0.1, 0.125), skin, parent=self.head)
            ln = [tuple(t.onto(ear, (0.565 * k, 0.03 + y, HC - 0.03 + z), (-k, 0, 0), lift=0.004)[0])
                  for y, z in [(0.035, 0.06), (-0.015, 0.045), (-0.035, 0.0), (-0.02, -0.045), (0.02, -0.06)]]
            t.line(f"{self.name} earin{k}", ln, self.head, width=0.0055)
        hair = s.get("hair", {"style": "cap", "color": "hair"})
        style = hair.get("style", "cap")
        if style == "cap":
            h = t.blob(f"{self.name} hair", (0, 0.03, HC + 0.035), (0.572 * SX, 0.578, 0.572), hair.get("color", "hair"), parent=self.head)
            t.boolean(h, t.blob(f"{self.name} facecut", (0.1, -0.9, HC - 0.26), (0.78, 0.72, 0.72), None, parent=self.head, rot=(0, 0.22, 0)))
            t.boolean(h, t.blob(f"{self.name} botcut", (0, 0.25, HC + 0.08 - 1.0), (1, 1, 1), None, parent=self.head, n=8))
            fr = t.blob(f"{self.name} fringe", (-0.06, -0.36, HC + 0.33), (0.3, 0.15, 0.11), hair.get("color", "hair"), parent=self.head, rot=(D2R(-32), D2R(-20), D2R(6)))
            t.boolean(h, fr, "UNION")
        elif style == "sides":     # what shows under a cap: tufts over the ears and round the back
            for k in (-1, 1):
                t.blob(f"{self.name} tuft{k}", (0.5 * k, 0.12, HC + 0.12), (0.12, 0.2, 0.17), hair.get("color", "hair"), parent=self.head, rot=(0, D2R(-15 * k), 0))
            t.blob(f"{self.name} nape", (0, 0.32, HC + 0.05), (0.45, 0.22, 0.2), hair.get("color", "hair"), parent=self.head)
        if s.get("cap"):
            self._cap(s["cap"])
        if s.get("beard"):
            self._beard(s["beard"])
        if s.get("moustache"):
            m = s["moustache"]
            for k in (-1, 1):
                p, n = self.on_face(0.09 * k, -0.15, lift=0.0)
                t.blob(f"{self.name} tache{k}", p + n * 0.03, (0.14, 0.05, 0.06), m.get("color", "beard"), parent=self.head,
                       rot=t.orient(n, roll=-18 * k))
        # eyes: dark ovals stuck to the face; closed eyes are ink arcs
        es = s.get("eye", 1.0)
        self.eye_objs, self.eye_closed = [], []
        for k in (-1, 1):
            p, n = self.on_face(0.19 * k, 0.02, lift=-0.012)
            e = t.blob(f"{self.name} eye{k}", p, (0.036 * es, 0.024, 0.054 * es), t._inkname(),
                       c=t.face, parent=self.head, rot=t.facing(n), seg=32)
            e.rotation_mode = "XYZ"
            self.eye_objs.append(e)
            arc = [(0.19 * k + 0.055 * math.cos(a), 0.0, HC + 0.015 - 0.03 * math.sin(a)) for a in [math.pi * i / 6 for i in range(7)]]
            self.eye_closed.append(t.mark_on(f"{self.name} lid{k}", self.skull, arc, self.head, width=0.006, n=1))
        nose = s.get("nose", "mark")
        if nose == "round":
            p, n = self.on_face(-0.02, -0.06, lift=-0.02)
            t.blob(f"{self.name} nose", p, (0.075, 0.07, 0.065), skin, parent=self.head, rot=t.facing(n))
        else:
            self.mark("nose", [(-0.025, -0.04), (-0.055, -0.085), (-0.012, -0.1)], width=0.0065)

    def _cap(self, cap):
        t, HC = self.t, self.HC
        g = t.empty(f"{self.name} capg", (0, 0.03, HC + 0.36), self.head, rot=(D2R(-8), 0, 0))
        t.cyl(f"{self.name} capband", (0, 0, 0.0), 0.53, 0.14, cap.get("band", cap.get("color", "cap")), parent=g, r2=0.55)
        t.cyl(f"{self.name} capcrown", (0, 0.0, 0.14), 0.55, 0.16, cap.get("color", "cap"), parent=g, r2=0.6)
        t.blob(f"{self.name} captop", (0, 0, 0.22), (0.6, 0.6, 0.06), cap.get("color", "cap"), parent=g)
        visor = [(math.cos(a) * 0.5, math.sin(a) * 0.3) for a in [math.pi * i / 20 for i in range(21)]]
        t.card(f"{self.name} visor", [(0.8 * x, -z) for x, z in visor], 0.025, cap.get("visor", "ink"), parent=g,
               loc=(0, -0.5, -0.06), rot=(D2R(72), 0, 0))
        if cap.get("badge"):
            t.blob(f"{self.name} badge", (0, -0.555, 0.05), (0.06, 0.02, 0.05), cap["badge"], parent=g)

    def _beard(self, beard):
        t, HC, R = self.t, self.HC, self.R
        col = beard.get("color", "beard")
        b = t.blob(f"{self.name} beard", (0, -0.02, HC - 0.05), (R * self.SX + 0.04, R + 0.05, R + 0.03), col,
                   parent=self.head, shape=lambda v: (v.x * (1 - 0.12 * max(0, -v.z)), v.y, v.z * (1 + 0.35 * max(0, -v.z) ** 2)))
        # the top edge: low under the nose, rising over the cheeks to the sideburns
        t.boolean(b, t.blob(f"{self.name} beardface", (0, -0.62, HC + 0.36), (0.5, 0.62, 0.52), None, parent=self.head))
        t.boolean(b, t.blob(f"{self.name} beardtop", (0, 0, HC + 0.12 + 1.0), (1.3, 1.3, 1.0), None, parent=self.head, n=6))
        t.boolean(b, t.blob(f"{self.name} beardback", (0, 1.15, HC), (1.2, 1.0, 1.4), None, parent=self.head, n=6))
        self.beard = b

    def on_face(self, x, z, lift=0.004):
        """A point on the face (x across, z above the eye line, head space) and its normal."""
        return self.t.onto(self.skull, (x, 0, self.HC + z), lift=lift)

    def mark(self, name, pts, width=0.0058, col="ink", target=None):
        target = target or self.skull
        return self.t.mark_on(f"{self.name} {name}", target, [(x, 0, self.HC + z) for x, z in pts], self.head,
                              width=width, col=col)

    def _faces(self):
        R = self.R
        bc = self.s.get("brows", {})
        bw = bc.get("width", 0.0095)
        bcol = bc.get("color", "ink")
        self._brows, self._mouths = {}, {}
        for name, (a, m, o) in BROWS.items():
            self._brows[name] = [self.mark(f"brow{name}{k}", [(0.09 * k, a * R + 0.0), (0.19 * k, m * R + 0.01), (0.29 * k, o * R)], width=bw, col=bcol)
                                 for k in (-1, 1)]
        target = self.beard if self.s.get("beard") else None
        for name, pts in MOUTHS.items():
            if pts is None:
                p, n = self.on_face(0.0, -0.42 * R, lift=-0.01)
                self._mouths[name] = [self.t.blob(f"{self.name} mouthopen", p, (0.05, 0.02, 0.055), self.t._inkname(),
                                                  c=self.t.face, parent=self.head, rot=self.t.facing(n), seg=24)]
            else:
                pts2 = [(x * R, z * R) for x, z in pts]
                try:
                    self._mouths[name] = [self.mark(f"mouth{name}", pts2, width=0.0075, target=target)]
                except RuntimeError:
                    self._mouths[name] = [self.mark(f"mouth{name}", pts2, width=0.0075)]

    # -- faces over time --
    def expression(self, name, frame=None):
        brows, mouth = EXPRESSIONS[name]
        for k, objs in self._brows.items():
            for o in objs:
                self._vis(o, k == brows, frame)
        for k, objs in self._mouths.items():
            for o in objs:
                self._vis(o, k == mouth, frame)

    def eyes(self, state="open", frame=None):
        for e, c in zip(self.eye_objs, self.eye_closed):
            self._vis(e, state == "open", frame)
            self._vis(c, state == "closed", frame)

    def blink(self, frame, length=2):
        self.eyes("open", frame - 1)
        self.eyes("closed", frame)
        self.eyes("open", frame + length)

    def look(self, dx=0.0, dz=0.0, frame=None):
        """Shift the pupils across the face (head-space units), keyed at frame."""
        if not hasattr(self, "_eye_base"):
            self._eye_base = [Vector(e.location) for e in self.eye_objs]
        for e, b in zip(self.eye_objs, self._eye_base):
            e.location = b + Vector((dx, 0, dz))
            if frame is not None:
                e.keyframe_insert("location", frame=frame)

    def head_pose(self, turn=0.0, tilt=0.0, nod=0.0, frame=None):
        self.head.rotation_euler = (D2R(nod), D2R(tilt), D2R(turn))
        if frame is not None:
            self.head.keyframe_insert("rotation_euler", frame=frame)

    @staticmethod
    def _vis(o, on, frame):
        o.hide_render = not on
        if frame is not None:
            o.keyframe_insert("hide_render", frame=frame)
