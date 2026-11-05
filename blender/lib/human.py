"""Realistic people for Blender shots, made with MakeHuman's MPFB extension (GPL; extensions.blender.org/add-ons/mpfb,
installed once: `blender --command extension install-file -r user_default -e add-on-mpfb-<version>.zip`).

`make(name, sex=..., age=..., ...)` builds a body from a few numbers (sex, age in years, muscle, weight, height,
proportions, ancestry) on MakeHuman's default rig with its skin weights, sets its face from MakeHuman's expression
units, and splits out the shells MakeHuman fits to every body as the parts a person is dressed from: `eyes` (two
eyeballs), `lashes`, `hair` (a scalp shell running down into long hair), `tights` (a bodysuit, neck to wrists and
ankles) and `skirt` (waist to ankles). Everything is built in the rest pose and skinned to the rig, so a garment cut
from a part, or skinned like one (`skin_like`), follows any pose.

A person stands at the origin of its rig facing -y (MakeHuman's front), its left at +x. Pose it in that frame:
`reach("hand.L", at, pole=...)` (IK to a point), `turn(bone, x, y, z)`, `lower(dz)` (a crouch), `grip(side)`;
`breathe(frames, fps, ...)` keys a breath on the spine. Then place and turn the rig, or an empty it is parented to.

`age_value` and `fit_sphere` are numpy only and tested without Blender.
"""
from __future__ import annotations

import importlib
import math
import os
from dataclasses import dataclass, field

import numpy as np

# MakeHuman's age slider: (years, value) at its stops, linear between
AGE_STOPS = ((1.0, 0.0), (11.0, 0.1875), (25.0, 0.5), (90.0, 1.0))
# the parts split out of the body: name -> MakeHuman's helper vertex groups
PARTS = {
    "eyes": ("helper-l-eye", "helper-r-eye"),
    "lashes": ("helper-l-eyelashes-1", "helper-l-eyelashes-2", "helper-r-eyelashes-1", "helper-r-eyelashes-2"),
    "hair": ("helper-hair",),
    "tights": ("helper-tights",),
    "skirt": ("helper-skirt",),
}
# IK: the bone each limb's chain ends on, and the chain's length (the arms and legs each run through a twist bone)
LIMBS = {"hand.L": ("lowerarm02.L", 4), "hand.R": ("lowerarm02.R", 4), "foot.L": ("lowerleg02.L", 4), "foot.R": ("lowerleg02.R", 4)}
TWIST_FREE = ("upperarm01", "upperarm02", "lowerarm01", "lowerarm02", "upperleg01", "upperleg02", "lowerleg01", "lowerleg02")


def age_value(years: float) -> float:
    """MakeHuman's age setting for an age in years: 0 at 1 year, 0.1875 at 11, 0.5 at 25, 1 at 90 (clamped)."""
    ys, vs = zip(*AGE_STOPS)
    return float(np.interp(years, ys, vs))


def fit_sphere(points) -> tuple[np.ndarray, float]:
    """The centre and radius of the sphere best through a cloud of points on (part of) it, by least squares."""
    p = np.asarray(points, float)
    a = np.column_stack([2 * p, np.ones(len(p))])
    sol, *_ = np.linalg.lstsq(a, (p ** 2).sum(axis=1), rcond=None)
    c = sol[:3]
    return c, math.sqrt(max(sol[3] + c @ c, 0.0))


def _mpfb():
    """MPFB's services, from whichever extension repository holds it."""
    import bpy

    for repo in bpy.context.preferences.extensions.repos:
        base = f"bl_ext.{repo.module}.mpfb.services"
        try:
            hs = importlib.import_module(base + ".humanservice")
            ts = importlib.import_module(base + ".targetservice")
            ls = importlib.import_module(base + ".locationservice")
        except ImportError:
            continue
        return hs.HumanService, ts.TargetService, ls.LocationService
    raise RuntimeError("realistic people need MakeHuman's MPFB extension (extensions.blender.org/add-ons/mpfb): "
                       "blender --command extension install-file -r user_default -e add-on-mpfb-<version>.zip")


@dataclass
class Person:
    """A body on its rig, the parts split from it, and the handles (IK targets, poles) its pose is set by."""
    name: str
    body: object
    rig: object
    coll: object
    parts: dict = field(default_factory=dict)
    handles: dict = field(default_factory=dict)

    # ---- where things are ----
    def point(self, bone: str, *, tail: bool = False):
        """A bone's head (or tail) in the world, as posed."""
        import bpy

        bpy.context.view_layer.update()
        pb = self.rig.pose.bones[bone]
        return self.rig.matrix_world @ (pb.tail if tail else pb.head)

    def rest(self, bone: str, *, tail: bool = False):
        """A bone's head (or tail) in the person's own frame, at rest."""
        b = self.rig.data.bones[bone]
        return (b.tail_local if tail else b.head_local).copy()

    # ---- posing ----
    def _handle(self, name: str, at):
        import bpy

        e = self.handles.get(name)
        if e is None:
            e = bpy.data.objects.new(f"{self.name}-{name}", None)
            self.coll.objects.link(e)
            e.parent = self.rig
            e.empty_display_size = 0.04
            self.handles[name] = e
        e.location = at
        return e

    def reach(self, limb: str, at, *, pole, pole_angle: float = -90.0, level: bool = False):
        """IK: `limb` ("hand.L", "hand.R", "foot.L", "foot.R") reaches `at` (the wrist or the ankle, in the person's
        frame) with its elbow or knee toward `pole`. `level`: the hand or foot keeps its rest orientation (a foot flat
        on the ground) instead of following the forearm or shin."""
        bone, chain = LIMBS[limb]
        side = limb[-1]
        for b in TWIST_FREE:
            pb = self.rig.pose.bones.get(f"{b}.{side}")
            if pb is not None:
                pb.lock_ik_y = True  # no twist about the bones' own length
        pb = self.rig.pose.bones[bone]
        c = next((c for c in pb.constraints if c.type == "IK"), None) or pb.constraints.new("IK")
        c.target = self._handle(f"{limb}-target", at)
        c.pole_target = self._handle(f"{limb}-pole", pole)
        c.pole_angle = math.radians(pole_angle)
        c.chain_count = chain
        c.use_stretch = False
        if level:
            end = "wrist" if limb.startswith("hand") else "foot"
            self.hold(f"{end}.{side}")
        return c

    def hold(self, bone: str, rotation=(0.0, 0.0, 0.0)):
        """Keep `bone` at its rest orientation in the person's frame, turned by `rotation` (degrees, XYZ), whatever
        its parents do (a foot flat on the ground, a hand set on a hilt)."""
        from mathutils import Euler

        rest = self.rig.data.bones[bone].matrix_local.to_3x3()
        turn = Euler([math.radians(a) for a in rotation], "XYZ").to_matrix()
        e = self._handle(f"{bone}-hold", self.rest(bone))
        e.rotation_mode = "QUATERNION"
        e.rotation_quaternion = (turn @ rest).to_quaternion()
        pb = self.rig.pose.bones[bone]
        c = next((c for c in pb.constraints if c.type == "COPY_ROTATION"), None) or pb.constraints.new("COPY_ROTATION")
        c.target = e
        c.target_space = c.owner_space = "WORLD"
        return c

    def turn(self, bone: str, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        """Rotate a bone about its own axes (degrees, XYZ), from rest."""
        pb = self.rig.pose.bones[bone]
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))

    def lower(self, dz: float, dy: float = 0.0):
        """Crouch: the hips (and all above them) down by `dz` metres and forward by `dy` (-y, the front)."""
        from mathutils import Vector

        b = self.rig.data.bones["root"]
        self.rig.pose.bones["root"].location = b.matrix_local.to_3x3().inverted() @ Vector((0.0, -dy, -dz))

    def grip(self, side: str, amount: float = 1.0, *, thumb: float = 0.6):
        """Curl a hand's fingers by `amount` (1: a fist round a hilt or a pole) and its thumb by `thumb`."""
        for f in range(2, 6):
            for j, a in ((1, 60), (2, 75), (3, 55)):
                pb = self.rig.pose.bones.get(f"finger{f}-{j}.{side}")
                if pb is not None:
                    pb.rotation_mode = "XYZ"
                    pb.rotation_euler = (math.radians(a * amount), 0.0, 0.0)
        for j, a in ((2, 30), (3, 40)):
            pb = self.rig.pose.bones.get(f"finger1-{j}.{side}")
            if pb is not None:
                pb.rotation_mode = "XYZ"
                pb.rotation_euler = (math.radians(a * thumb), 0.0, 0.0)

    def breathe(self, frames, fps: float, *, rate: float = 0.3, depth: float = 1.0, lean=None, phase: float = 0.0):
        """Key a breath on the chest across `frames`: `rate` breaths a second, the chest lifting `depth` degrees and
        the shoulders with it; `lean(t)` (degrees, t in seconds from the first frame) bends the spine forward over
        the shot (a fighter settling into a stance). Keeps whatever turn the bones already have."""
        base = {b: tuple(self.rig.pose.bones[b].rotation_euler) for b in ("spine02", "spine01", "clavicle.L", "clavicle.R", "spine03")}
        f0 = frames[0]
        for f in frames:
            t = (f - f0) / fps
            s = math.sin(2 * math.pi * (rate * t + phase))
            for b, k in (("spine02", -0.6), ("spine01", -1.0)):
                pb = self.rig.pose.bones[b]
                pb.rotation_euler = (base[b][0] + math.radians(depth * k * s), base[b][1], base[b][2])
                pb.keyframe_insert("rotation_euler", frame=f)
            for b in ("clavicle.L", "clavicle.R"):
                pb = self.rig.pose.bones[b]
                sign = 1 if b.endswith("L") else -1
                pb.rotation_euler = (base[b][0], base[b][1] + sign * math.radians(depth * 0.8 * s), base[b][2])
                pb.keyframe_insert("rotation_euler", frame=f)
            if lean is not None:
                pb = self.rig.pose.bones["spine03"]
                pb.rotation_euler = (base["spine03"][0] + math.radians(lean(t)), base["spine03"][1], base["spine03"][2])
                pb.keyframe_insert("rotation_euler", frame=f)

    def discard(self, *names: str):
        """Delete parts the person is done with (the raw shells once the clothes and the hair are cut from them): they
        have no material and would show grey through and round what was made from them."""
        import bpy

        for n in names:
            ob = self.parts.pop(n, None)
            if ob is not None and ob.name in bpy.data.objects:
                bpy.data.objects.remove(ob, do_unlink=True)

    # ---- dressing ----
    def paint(self, base, regions: dict | None = None):
        """The body's materials: `base` everywhere, `regions` {vertex group: material} over it (MakeHuman's lips,
        fingernails, toenails, ears, scalp)."""
        me = self.body.data
        me.materials.clear()
        me.materials.append(base)
        regions = regions or {}
        gi = {g.name: g.index for g in self.body.vertex_groups}
        members = {}
        for k, (g, mat) in enumerate(regions.items(), start=1):
            me.materials.append(mat)
            idx = gi.get(g)
            if idx is not None:
                members[k] = {v.index for v in me.vertices if any(x.group == idx and x.weight > 0.5 for x in v.groups)}
        for p in me.polygons:
            p.material_index = 0
            for k, vs in members.items():
                if all(v in vs for v in p.vertices):
                    p.material_index = k


def make(name: str, *, sex: float = 1.0, age: float = 25.0, muscle: float = 0.5, weight: float = 0.5, height: float = 0.5,
         proportions: float = 0.5, ancestry=(1 / 3, 1 / 3, 1 / 3), face: dict | None = None, coll=None, subsurf: int = 1,
         targets: dict | None = None) -> Person:
    """A person: `sex` 0 (female) to 1 (male), `age` in years, `muscle`, `weight`, `height` and `proportions` (0 to 1,
    MakeHuman's sliders; proportions 1 the idealised), `ancestry` (asian, caucasian, african) weights, and `face`
    {unit: weight} from MakeHuman's expression units for its main ancestry (eyebrows-left-down, eye-right-slit,
    mouth-compression, ...). `targets` {path: weight} reshapes it with MakeHuman's own targets ("nose/nose-volume-decr",
    "chin/chin-width-decr", ...: an anime head, animeface.head). In the rest pose, its parts split out (`PARTS`), all
    in `coll`."""
    import bpy

    hs, ts, ls = _mpfb()
    coll = coll or bpy.context.scene.collection
    macro = ts.get_default_macro_info_dict()
    macro.update(gender=float(sex), age=age_value(age), muscle=float(muscle), weight=float(weight), height=float(height),
                 proportions=float(proportions))
    asian, caucasian, african = ancestry
    macro["race"] = {"asian": float(asian), "caucasian": float(caucasian), "african": float(african)}
    body = hs.create_human(macro_detail_dict=macro, scale=0.1)
    rig = hs.add_builtin_rig(body, "default")
    if face:
        main = ("asian", "caucasian", "african")[int(np.argmax(ancestry))]
        units = os.path.join(ls.get_mpfb_data("targets"), "expression", "units", main)
        for unit, w in face.items():
            ts.load_target(body, os.path.join(units, f"{unit}.target.gz"), weight=float(w), name=f"face-{unit}")
    for path, w in (targets or {}).items():
        ts.load_target(body, os.path.join(ls.get_mpfb_data("targets"), f"{path}.target.gz"), weight=float(w),
                       name=f"shape-{os.path.basename(path)}")
    # bake the targets into the mesh, so the parts split from it keep their fitted shapes
    with bpy.context.temp_override(object=body, active_object=body, selected_objects=[body], selected_editable_objects=[body]):
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
    body.name = body.data.name = name
    rig.name = rig.data.name = f"{name}-rig"
    for ob in (body, rig):
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        coll.objects.link(ob)
    person = Person(name, body, rig, coll)
    for part, groups in PARTS.items():
        person.parts[part] = _split(body, groups, f"{name}-{part}", coll, rig)
    _keep_only(body, "body")
    for m in list(body.modifiers):
        if m.type == "MASK":
            body.modifiers.remove(m)
    if subsurf:
        s = body.modifiers.new("smooth", "SUBSURF")
        s.levels = s.render_levels = subsurf
    return person


def _members(ob, groups) -> np.ndarray:
    gidx = {ob.vertex_groups[g].index for g in groups if g in ob.vertex_groups}
    m = np.zeros(len(ob.data.vertices), bool)
    for v in ob.data.vertices:
        m[v.index] = any(g.group in gidx and g.weight > 0 for g in v.groups)
    return m


def _subset(src, keep_faces: set, name: str, coll, rig):
    """A new object of `src`'s faces in `keep_faces`, with all its vertex groups and weights, skinned to `rig`."""
    import bmesh
    import bpy

    bm = bmesh.new()
    bm.from_mesh(src.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep_faces], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    for g in src.vertex_groups:
        ob.vertex_groups.new(name=g.name)
    ob.parent = rig
    ob.matrix_parent_inverse = src.matrix_parent_inverse.copy()
    mod = ob.modifiers.new("rig", "ARMATURE")
    mod.object = rig
    for p in me.polygons:
        p.use_smooth = True
    return ob


def _split(body, groups, name: str, coll, rig):
    m = _members(body, groups)
    keep = {p.index for p in body.data.polygons if all(m[v] for v in p.vertices)}
    return _subset(body, keep, name, coll, rig) if keep else None


def _keep_only(ob, group: str):
    """Delete every face of `ob` not wholly in vertex group `group` (MakeHuman's helpers and joint cubes)."""
    import bmesh

    m = _members(ob, [group])
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not all(m[v.index] for v in f.verts)], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    for p in ob.data.polygons:
        p.use_smooth = True


def skin_like(ob, source, rig):
    """Skin `ob` (in the rest pose) like `source`: each vertex takes the weights of the nearest vertex of `source`
    (a garment over a part, a belt round a shell), and an armature modifier on `rig`."""
    from mathutils import kdtree

    src = source.data
    kd = kdtree.KDTree(len(src.vertices))
    for v in src.vertices:
        kd.insert(v.co, v.index)
    kd.balance()
    names = [g.name for g in source.vertex_groups]
    for n in names:
        if n not in ob.vertex_groups:
            ob.vertex_groups.new(name=n)
    gmap = {g.index: ob.vertex_groups[names[g.index]] for g in source.vertex_groups}
    by_group: dict = {}
    for v in ob.data.vertices:
        _, j, _ = kd.find(v.co)
        for g in src.vertices[j].groups:
            by_group.setdefault((g.group, round(g.weight, 4)), []).append(v.index)
    for (gi, w), idx in by_group.items():
        gmap[gi].add(idx, w, "REPLACE")
    ob.parent = rig
    if not any(m.type == "ARMATURE" for m in ob.modifiers):
        mod = ob.modifiers.new("rig", "ARMATURE")
        mod.object = rig
        # skinning first, then whatever else the object has (a subdivision, a wave)
        while ob.modifiers.find("rig") > 0:
            with _ctx(ob):
                import bpy

                bpy.ops.object.modifier_move_up(modifier="rig")
    return ob


def skin_by_height(ob, rig, stops):
    """Skin `ob` (in the rest pose) by height: `stops` [(z, bone), ...] from the top down, each vertex weighted to the
    bones of the two stops it lies between, blended linearly (a trouser leg: the hips, the thigh, the knee, the shin)."""
    zs = [z for z, _ in stops]
    for _, b in stops:
        if b not in ob.vertex_groups:
            ob.vertex_groups.new(name=b)
    by = {}
    for v in ob.data.vertices:
        z = v.co.z
        if z >= zs[0]:
            by.setdefault((stops[0][1], 1.0), []).append(v.index)
            continue
        if z <= zs[-1]:
            by.setdefault((stops[-1][1], 1.0), []).append(v.index)
            continue
        for (z0, b0), (z1, b1) in zip(stops[:-1], stops[1:]):
            if z1 <= z <= z0:
                k = (z0 - z) / max(z0 - z1, 1e-9)
                if b0 == b1:
                    by.setdefault((b0, 1.0), []).append(v.index)
                else:
                    by.setdefault((b0, round(1 - k, 3)), []).append(v.index)
                    by.setdefault((b1, round(k, 3)), []).append(v.index)
                break
    for (b, w), idx in by.items():
        if w > 0:
            ob.vertex_groups[b].add(idx, w, "ADD")
    ob.parent = rig
    if not any(m.type == "ARMATURE" for m in ob.modifiers):
        mod = ob.modifiers.new("rig", "ARMATURE")
        mod.object = rig
        while ob.modifiers.find("rig") > 0:
            import bpy

            with _ctx(ob):
                bpy.ops.object.modifier_move_up(modifier="rig")
    return ob


def bind(ob, rig, bone: str):
    """Skin `ob` wholly to one bone (a headband to the head, a belt to the hips)."""
    g = ob.vertex_groups.get(bone) or ob.vertex_groups.new(name=bone)
    g.add(range(len(ob.data.vertices)), 1.0, "REPLACE")
    ob.parent = rig
    if not any(m.type == "ARMATURE" for m in ob.modifiers):
        mod = ob.modifiers.new("rig", "ARMATURE")
        mod.object = rig
    return ob


def _ctx(ob):
    import bpy

    return bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob])


def eyes(person: Person, material, *, segments: int = 32, rings: int = 16) -> list:
    """Round eyeballs where MakeHuman fits its own (a sphere through each of its helper eyes), weighted to the head;
    `material` (toon.eye) draws the iris on their fronts (-y, the person's front, in their rest space)."""
    import bmesh
    import bpy

    part = person.parts.get("eyes")
    out = []
    me = part.data
    co = np.array([v.co[:] for v in me.vertices])
    # the two eyes: left at +x
    for side, mask in (("L", co[:, 0] > 0), ("R", co[:, 0] <= 0)):
        c, r = fit_sphere(co[mask])
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=r)
        bmesh.ops.translate(bm, verts=bm.verts, vec=tuple(c))
        mesh = bpy.data.meshes.new(f"{person.name}-eye.{side}")
        bm.to_mesh(mesh)
        bm.free()
        for p in mesh.polygons:
            p.use_smooth = True
        mesh.materials.append(material)
        ob = bpy.data.objects.new(mesh.name, mesh)
        person.coll.objects.link(ob)
        bind(ob, person.rig, "head")
        out.append(ob)
    bpy.data.objects.remove(part, do_unlink=True)
    person.parts["eyes"] = out
    return out


def brows(person: Person, material, *, thickness: float = 0.007, length: float = 1.25, arch: float = 0.25, lift: float = 1.45,
          angle: float = 0.0, taper: float = 0.35, push: float = 0.0015) -> list:
    """Eyebrows as thick drawn strokes lying on the brow ridge above each eye: `length` and `lift` in eye radii,
    `arch` the bow, `angle` (degrees) the slant (positive: down toward the nose, a scowl), `taper` the tail's width
    over the head's. Weighted to the head."""
    import bpy
    from mathutils.bvhtree import BVHTree

    bvh = BVHTree.FromObject(person.body, bpy.context.evaluated_depsgraph_get(), deform=False)
    eyes_ = person.parts["eyes"]
    out = []
    for ob in eyes_:
        co = np.array([v.co[:] for v in ob.data.vertices])
        c, r = co.mean(axis=0), np.ptp(co[:, 0]) / 2
        side = 1 if c[0] > 0 else -1     # +x: the left eye; its outer end is further out along +x
        n = 9
        u = np.linspace(-0.5, 0.5, n)     # inner (toward the nose) to outer
        xs = c[0] + side * (u * length * 2 * r + 0.15 * r)
        zs = c[2] + lift * r + arch * r * (1 - (2 * u) ** 2) - math.tan(math.radians(angle)) * (0.5 - u) * length * r
        pts, nrm = [], []
        for x, z in zip(xs, zs):
            hit = bvh.ray_cast((x, c[1] - 0.2, z), (0.0, 1.0, 0.0), 0.4)
            if hit[0] is None:
                continue
            pts.append(np.array(hit[0][:]))
            nrm.append(np.array(hit[1][:]))
        if len(pts) < 3:
            continue
        pts, nrm = np.array(pts), np.array(nrm)
        w = thickness * (1.0 - (1.0 - taper) * np.clip((np.linspace(0, 1, len(pts)) - 0.25) / 0.75, 0, 1))
        tang = np.gradient(pts, axis=0)
        tang /= np.linalg.norm(tang, axis=1, keepdims=True)
        up = np.cross(nrm, tang)
        up /= np.linalg.norm(up, axis=1, keepdims=True)
        up *= np.sign(up[:, 2:3] + 1e-9)
        base = pts + nrm * push
        verts = np.concatenate([base - up * w[:, None] / 2, base + up * w[:, None] / 2])
        k = len(pts)
        faces = [(i, i + 1, k + i + 1, k + i) for i in range(k - 1)]
        me = bpy.data.meshes.new(f"{person.name}-brow.{'L' if side > 0 else 'R'}")
        me.from_pydata(verts.tolist(), [], faces)
        me.materials.append(material)
        o = bpy.data.objects.new(me.name, me)
        person.coll.objects.link(o)
        s = o.modifiers.new("thick", "SOLIDIFY")
        s.thickness = 0.0015
        bind(o, person.rig, "head")
        while o.modifiers.find("rig") > 0:
            with _ctx(o):
                bpy.ops.object.modifier_move_up(modifier="rig")
        out.append(o)
    person.parts["brows"] = out
    return out


def lashes(person: Person, upper, lower=None):
    """The lash lines MakeHuman fits to the lids: the upper (its helper-*-eyelashes-2) in `upper`, the lower
    (-1) in `lower`, or gone when `lower` is None (a dark lower line reads as eyeliner)."""
    import bmesh

    ob = person.parts["lashes"]
    me = ob.data
    low = _members(ob, ("helper-l-eyelashes-1", "helper-r-eyelashes-1")) & ~_members(ob, ("helper-l-eyelashes-2", "helper-r-eyelashes-2"))
    me.materials.clear()
    me.materials.append(upper)
    if lower is None:
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if all(low[v.index] for v in f.verts)], context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bm.to_mesh(me)
        bm.free()
    else:
        me.materials.append(lower)
        for p in me.polygons:
            p.material_index = 1 if all(low[v] for v in p.vertices) else 0
    return ob


def attach(ob, person: Person, bone: str):
    """Carry `ob` with `bone` from now on, keeping it where it is in the current pose (a cape built round the posed
    shoulders, a hat on the posed head): bone parenting, so a breath or a turn of that bone moves it."""
    import bpy

    bpy.context.view_layer.update()
    world = ob.matrix_world.copy()
    ob.parent = person.rig
    ob.parent_type = "BONE"
    ob.parent_bone = bone
    bpy.context.view_layer.update()
    ob.matrix_world = world
    return ob
