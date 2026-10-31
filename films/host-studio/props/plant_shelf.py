"""plant_shelf: a small golden pothos in a terracotta pot, vines trailing over the +X rim.

Run headless:
    blender -b --factory-startup -P films/host-studio/props/plant_shelf.py -- --out films/host-studio/props/out

Writes <out>/plant_shelf.fbx and <out>/plant_shelf.png (1200x1200 preview) and prints the
exported bounding box in cm. 1 Blender unit = 1 m; origin at the bottom centre of the pot.
The trailing side faces +X (toward the camera on the shelf). Seeded (--seed), so a run is
reproducible. The golden variegation is a point colour attribute "Col" on the leaves; M_Leaf's
base colour is the plain green.
"""

import argparse
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

NAME = "plant_shelf"

# Terracotta pot, ~12 cm.
POT_H = 0.115
POT_R_TOP = 0.064
POT_R_BODY = 0.058
POT_R_BOT = 0.046
COLLAR_Z = 0.088
SOIL_Z = 0.103

LEAF_THICK = 0.0012
X_BACK = -0.115  # nothing further back than this (toward the wall)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(prog=NAME)
    p.add_argument("--out", default="films/host-studio/props/out")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--samples", type=int, default=96)
    p.add_argument("--no-render", action="store_true")
    return p.parse_args(argv)


# ---------------------------------------------------------------- scene / materials

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


def make_material(name, color, roughness, **extra):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    for k, v in extra.items():
        bsdf.inputs[k].default_value = v
    m.diffuse_color = (*color, 1.0)
    m.roughness = roughness
    return m


def mesh_object(name, verts, faces, material, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material)
    for poly in me.polygons:
        poly.use_smooth = smooth
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ---------------------------------------------------------------- generic geometry

def lathe(profile, segments):
    """Revolve a (r, z) profile around Z. Points with r == 0 become a single pole."""
    verts, faces, rings = [], [], []
    for r, z in profile:
        if r < 1e-9:
            rings.append([len(verts)] * segments)
            verts.append((0.0, 0.0, z))
        else:
            ring = []
            for s in range(segments):
                a = 2 * math.pi * s / segments
                ring.append(len(verts))
                verts.append((r * math.cos(a), r * math.sin(a), z))
            rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for s in range(segments):
            t = (s + 1) % segments
            quad = [a[s], a[t], b[t], b[s]]
            uniq = []
            for q in quad:
                if q not in uniq:
                    uniq.append(q)
            if len(uniq) >= 3:
                faces.append(uniq)
    return verts, faces


def bezier(p0, p1, p2, p3, n):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append(p0 * u ** 3 + p1 * 3 * u * u * t + p2 * 3 * u * t * t + p3 * t ** 3)
    return pts


def catmull(points, per_seg):
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for k in range(per_seg):
            t = k / per_seg
            t2, t3 = t * t, t * t * t
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(points[-1])
    return out


def tube(points, radii, sides=10, caps=True):
    """Sweep a circle along a polyline with parallel-transport frames; capped with fans."""
    n = len(points)
    tangents = []
    for i in range(n):
        a = points[max(i - 1, 0)]
        b = points[min(i + 1, n - 1)]
        tangents.append((b - a).normalized())
    ref = Vector((0, 0, 1)) if abs(tangents[0].z) < 0.9 else Vector((1, 0, 0))
    normal = tangents[0].cross(ref).normalized()
    verts, faces = [], []
    for i in range(n):
        if i > 0:
            axis = tangents[i - 1].cross(tangents[i])
            if axis.length > 1e-9:
                ang = tangents[i - 1].angle(tangents[i])
                normal = (Matrix.Rotation(ang, 3, axis.normalized()) @ normal).normalized()
        binormal = tangents[i].cross(normal)
        for s in range(sides):
            a = 2 * math.pi * s / sides
            verts.append(points[i] + (normal * math.cos(a) + binormal * math.sin(a)) * radii[i])
    for i in range(n - 1):
        for s in range(sides):
            t = (s + 1) % sides
            faces.append([i * sides + s, i * sides + t, (i + 1) * sides + t, (i + 1) * sides + s])
    if caps:
        c0 = len(verts)
        verts.append(points[0].copy())
        c1 = len(verts)
        verts.append(points[-1].copy())
        last = (n - 1) * sides
        for s in range(sides):
            t = (s + 1) % sides
            faces.append([c0, t, s])
            faces.append([c1, last + s, last + t])
    return verts, faces


def bvh(verts, faces):
    return BVHTree.FromPolygons([tuple(v) for v in verts], faces, all_triangles=False, epsilon=0.0)


def too_close(verts, tree, clearance, stride=3):
    for v in verts[::stride]:
        hit = tree.find_nearest(v, clearance)
        if hit[0] is not None:
            return True
    return False


# ---------------------------------------------------------------- leaf placement

def leaf_frame(direction, roll):
    d = direction.normalized()
    x = d.cross(Vector((0, 0, 1)))
    if x.length < 1e-6:
        x = Vector((1, 0, 0))
    x.normalize()
    n = x.cross(d)
    rot = Matrix.Rotation(roll, 3, d)
    x, n = rot @ x, rot @ n
    return Matrix((x, d, n)).transposed()


def solidify(ob, thickness):
    mod = ob.modifiers.new("solidify", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = 0.0
    mod.use_even_offset = True
    mod.use_rim = True
    mod.material_offset_rim = 1
    ob.data.materials.append(ob.data.materials[0])
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        # The 2 mm rim is shaded flat so the margin does not read as a puffy bead.
        poly.use_smooth = poly.material_index == 0
        poly.material_index = 0
    me.materials.pop(index=1)


# ---------------------------------------------------------------- pothos leaf

def smoothstep(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def leaf_outline(L, theta, ws, power, tip):
    """Cordate margin in leaf space: x lateral, y along the midrib, base (petiole) at origin."""
    rr = ((1 + math.cos(theta)) / 2) ** power
    r = L * rr * (1 - tip * (1 - math.exp(-(theta / 0.35) ** 2)))
    return r * math.sin(theta) * ws, r * math.cos(theta)


def build_leaf(rng, L):
    """Heart-shaped pothos blade folded slightly along the midrib, with golden streak colours.

    Returns (verts, faces, colours per vertex, midrib points), all in leaf space.
    """
    nu, ns = 18, 7
    theta_max = math.radians(150)
    ws, power, tip = 0.74, 0.95, 0.22
    fold = rng.uniform(0.10, 0.22)
    droop = rng.uniform(0.10, 0.25)
    curl = rng.uniform(0.2, 0.6)
    ph1, ph2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
    gold = rng.uniform(0.45, 0.85)

    def shape_z(x, y):
        ax = abs(x)
        return fold * ax - curl * ax * ax / L - droop * L * (max(y, 0) / L) ** 2

    verts, faces, cols = [], [], []
    for side in (-1, 1):
        base = len(verts)
        for i in range(nu + 1):
            u = i / nu
            mx, my = leaf_outline(L, theta_max * (1 - u), ws, power, tip)
            ay = L * u ** 2.2
            # Golden variegation: streaks that run along the lateral veins, fading at the midrib.
            streak = 0.5 + 0.5 * math.sin(u * 41 + ph1 + side) * math.sin(u * 13 + ph2)
            for j in range(ns + 1):
                s = j / ns
                x = side * mx * s
                y = ay + (my - ay) * s
                verts.append(Vector((x, y, shape_z(x, y))))
                g = smoothstep(1.0 - 0.45 * gold, 1.0, streak) * smoothstep(0.15, 0.6, s) * (0.6 + 0.4 * math.sin(s * 5 + ph2 + i)) * 0.95
                cols.append(GREEN.lerp(GOLD, g))
        for i in range(nu):
            for j in range(ns):
                a = base + i * (ns + 1) + j
                b = base + (i + 1) * (ns + 1) + j
                faces.append([a, b, b + 1, a + 1] if side > 0 else [a, a + 1, b + 1, b])
    midrib = [Vector((0, 0.85 * L * k / 10, shape_z(0, 0.85 * L * k / 10))) for k in range(11)]
    return verts, faces, cols, midrib


def set_colors(ob, cols=None):
    """Point colour attribute 'Col' (the golden variegation). Non-leaf parts get white."""
    me = ob.data
    attr = me.color_attributes.new("Col", "BYTE_COLOR", "POINT")
    if cols is None:
        for d in attr.data:
            d.color = (1, 1, 1, 1)
        return
    # mesh_object() merged duplicate vertices, so look colours up by position.
    lut = {}
    for v, c in cols:
        lut[(round(v.x, 5), round(v.y, 5), round(v.z, 5))] = c
    for mv, d in zip(me.vertices, attr.data):
        c = lut.get((round(mv.co.x, 5), round(mv.co.y, 5), round(mv.co.z, 5)), GREEN)
        d.color = (c.x, c.y, c.z, 1)


GREEN = Vector((0.050, 0.200, 0.016))
GOLD = Vector((0.560, 0.480, 0.090))


def leaf_material():
    m = make_material("M_Leaf", tuple(GREEN), 0.38)
    nt = m.node_tree
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Col"
    nt.links.new(attr.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    return m


# ---------------------------------------------------------------- the plant

def build(seed):
    rng = random.Random(seed)
    mats = {
        "pot": make_material("M_Pot", (0.42, 0.15, 0.07), 0.88),
        "soil": make_material("M_Soil", (0.035, 0.024, 0.016), 0.95),
        "leaf": leaf_material(),
        "stem": make_material("M_Stem", (0.10, 0.20, 0.035), 0.55),
    }
    objects = []

    # Terracotta pot: tapered body, a thicker collar at the top, rounded rim.
    prof = [(0.0, 0.0), (POT_R_BOT - 0.003, 0.0), (POT_R_BOT, 0.003)]
    for k in range(1, 6):
        t = k / 5
        prof.append((POT_R_BOT + (POT_R_BODY - POT_R_BOT) * t, 0.003 + (COLLAR_Z - 0.003) * t))
    prof += [(POT_R_TOP - 0.001, COLLAR_Z), (POT_R_TOP, COLLAR_Z + 0.002)]
    rr = 0.004
    for k in range(7):
        a = math.pi * k / 6
        prof.append((POT_R_TOP - rr + rr * math.cos(a), POT_H - rr + rr * math.sin(a)))
    prof.append((POT_R_TOP - 2 * rr - 0.002, POT_H - 0.012))
    prof.append((POT_R_BODY - 0.010, SOIL_Z - 0.015))
    v, f = lathe(prof, 48)
    pot = mesh_object("pot", v, f, mats["pot"])
    set_colors(pot)
    objects.append(pot)
    pot_tree = bvh(v, f)

    soil_r = POT_R_TOP - 2 * rr - 0.003
    sprof = [(0.0, SOIL_Z + 0.006)]
    for k in range(1, 7):
        t = k / 6
        sprof.append((soil_r * t, SOIL_Z + 0.006 * (1 - t * t)))
    sprof.append((soil_r - 0.002, SOIL_Z - 0.012))
    v, f = lathe(sprof, 36)
    soil = mesh_object("soil", v, f, mats["soil"])
    set_colors(soil)
    objects.append(soil)

    stems = []    # (tree, polyline) of every stem and vine
    placed = []   # (verts, tree) of every leaf blade

    def add_stem(name, pts, r0, r1):
        radii = [r0 + (r1 - r0) * i / (len(pts) - 1) for i in range(len(pts))]
        v, f = tube(pts, radii, sides=8)
        ob = mesh_object(name, v, f, mats["stem"])
        set_colors(ob)
        objects.append(ob)
        stems.append(bvh(v, f))

    def try_leaf(name, attach, out_dir, L, pitch_range, roll_range, petiole, sag, lrng,
                 allow_low=False):
        # The shelf is 28 cm deep with the wall behind (-X): keep the back of the plant in.
        """Place one leaf on a short petiole from `attach`, retrying orientations on a clash."""
        for attempt in range(40):
            yaw_jit = lrng.uniform(-0.5, 0.5)
            od = Matrix.Rotation(yaw_jit, 3, "Z") @ out_dir
            od.z = 0
            od.normalize()
            pitch = math.radians(lrng.uniform(*pitch_range))
            d = Vector((od.x * math.cos(pitch), od.y * math.cos(pitch), -math.sin(pitch)))
            frame = leaf_frame(d, math.radians(lrng.uniform(*roll_range)))
            plen = petiole * lrng.uniform(0.8, 1.2)
            elev = math.radians(lrng.uniform(20, 50)) if not allow_low else math.radians(lrng.uniform(-10, 20))
            pdir = (od * math.cos(elev) + Vector((0, 0, math.sin(elev)))).normalized()
            base = attach + pdir * plen
            lv, lf, lc, mr = build_leaf(lrng, L)
            wv = [base + frame @ p for p in lv]
            tree = bvh(wv, lf)
            if tree.overlap(pot_tree) or min(p.z for p in wv) < 0.004 or min(p.x for p in wv) < X_BACK:
                continue
            if any(tree.overlap(t) for t in stems):
                continue
            if any(tree.overlap(t) or too_close(wv, t, 0.004) for _, t in placed):
                continue
            placed.append((wv, tree))
            ob = mesh_object(name, wv, lf, mats["leaf"])
            set_colors(ob, list(zip(wv, lc)))
            solidify(ob, LEAF_THICK)
            objects.append(ob)
            mid = attach.lerp(base, 0.5) + Vector((0, 0, sag * plen))
            v, f = tube(bezier(attach, mid, mid, base, 8), [0.0016] * 9, sides=6)
            pob = mesh_object(name + "_petiole", v, f, mats["stem"])
            set_colors(pob)
            objects.append(pob)
            mrw = [base + frame @ (p + Vector((0, 0, 0.0006))) for p in mr]
            v, f = tube(mrw, [0.0012 * (1 - i / 10) + 0.0004 for i in range(11)], sides=5)
            mob = mesh_object(name + "_midrib", v, f, mats["leaf"])
            set_colors(mob, [(p, GREEN) for p in v])
            objects.append(mob)
            return True
        print(f"[{NAME}] {name}: no clean placement, skipped")
        return False

    # Top cluster: short arching stems out of the soil, leaves alternating along them.
    n_up = 6
    az0 = rng.uniform(0, 2 * math.pi)
    for k in range(n_up):
        az = az0 + 2 * math.pi * k / n_up + rng.uniform(-0.3, 0.3)
        out = Vector((math.cos(az), math.sin(az), 0))
        if out.x < 0:
            out.x *= 0.5
        start = Vector((0, 0, SOIL_Z - 0.01)) + out * rng.uniform(0.0, 0.02)
        height = rng.uniform(0.09, 0.17)
        reach = rng.uniform(0.03, 0.06)
        end = start + out * reach + Vector((0, 0, height))
        pts = bezier(start, start + Vector((0, 0, height * 0.6)), end - out * reach * 0.2, end, 14)
        add_stem(f"stem{k}", pts, 0.0028, 0.002)
        side = Vector((-out.y, out.x, 0))
        nodes = [0.45, 0.75, 1.0]
        for n, t in enumerate(nodes):
            p = pts[int(t * 14)]
            sgn = 1 if n % 2 == 0 else -1
            odir = (out * 0.8 + side * sgn * 0.7).normalized() if t < 1.0 else out
            L = rng.uniform(0.075, 0.10) if t < 1.0 else rng.uniform(0.055, 0.07)
            try_leaf(f"leaf_s{k}_{n}", p, odir, L, (-25, 12), (-15, 15), 0.035, 0.3,
                     random.Random(rng.random()))

    # Trailing vines: out of the soil on the +X side, over the rim and down the side of the pot
    # (they stop just above the shelf, so the prop can stand anywhere on it).
    for k, (y0, drop, run) in enumerate([(-0.034, 0.050, 0.0), (0.004, 0.110, 0.0), (0.036, 0.085, 0.0)]):
        y = y0
        rim_r = POT_R_TOP + 0.010
        p = [Vector((0.030, y, SOIL_Z - 0.005)),
             Vector((0.050, y, POT_H + 0.008)),
             Vector((rim_r, y + 0.004, POT_H + 0.002)),
             Vector((rim_r + 0.010, y + 0.008, POT_H - 0.03))]
        z_end = max(POT_H - 0.03 - drop, 0.006)
        p.append(Vector((rim_r + 0.016, y + 0.012 + rng.uniform(-0.01, 0.01), (POT_H - 0.03 + z_end) / 2)))
        p.append(Vector((rim_r + 0.022 + (0.01 if run else 0), y + 0.016, z_end + (0.01 if run else 0))))
        if run:
            p.append(Vector((rim_r + 0.03 + run, y + 0.02 + rng.uniform(-0.01, 0.01), 0.0035)))
        pts = catmull(p, 6)
        add_stem(f"vine{k}", pts, 0.0024, 0.0016)
        # Leaves along the vine every ~4 cm of arc length, alternating sides, facing out (+X).
        acc, last, n = 0.0, 0.0, 0
        for i in range(1, len(pts)):
            acc += (pts[i] - pts[i - 1]).length
            if acc - last > 0.040 and acc > 0.05:
                last = acc
                sgn = 1 if n % 2 == 0 else -1
                odir = Vector((1.0, 0.55 * sgn, 0)).normalized()
                L = rng.uniform(0.050, 0.072)
                if pts[i].z < 0.03:  # lying on the shelf: leaves flat-ish
                    pr, low = (-15, 10), True
                else:                 # hanging: tips down, faces toward +X
                    pr, low = (45, 75), True
                try_leaf(f"leaf_v{k}_{n}", pts[i], odir, L, pr, (-30, 30), 0.022, 0.15,
                         random.Random(rng.random()), allow_low=low)
                n += 1
    print(f"[{NAME}] leaves placed: {len(placed)}")

    bpy.ops.object.select_all(action="DESELECT")
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    plant = bpy.context.view_layer.objects.active
    plant.name = NAME
    plant.data.name = NAME
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return plant


# ---------------------------------------------------------------- export / preview

def stats(ob):
    xs = [v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in xs), min(v.y for v in xs), min(v.z for v in xs)))
    hi = Vector((max(v.x for v in xs), max(v.y for v in xs), max(v.z for v in xs)))
    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    return lo, hi, tris


def export(ob, path):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"MESH"},
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
        axis_forward="-Y", axis_up="Z", mesh_smooth_type="FACE",
        use_mesh_modifiers=True, add_leaf_bones=False, bake_space_transform=False,
    )


def render_preview(ob, path, samples, view_dir):
    scene = bpy.context.scene
    lo, hi, _ = stats(ob)
    center = (lo + hi) / 2
    radius = (hi - lo).length / 2

    world = bpy.data.worlds.new("preview")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.18, 0.18, 0.18, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    scene.world = world

    bpy.ops.mesh.primitive_plane_add(size=radius * 40, location=(0, 0, 0))
    bpy.context.active_object.is_shadow_catcher = True

    def area(name, direction, size, power):
        d = Vector(direction).normalized()
        light = bpy.data.lights.new(name, "AREA")
        light.size = size * radius
        light.energy = power * radius * radius
        lo_ = bpy.data.objects.new(name, light)
        lo_.location = center + d * radius * 4
        lo_.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(lo_)

    area("key", (0.6, -1.0, 1.1), 3.0, 260)
    area("fill", (-1.0, -0.4, 0.5), 4.0, 90)
    area("rim", (-0.3, 1.0, 0.9), 2.0, 140)

    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("cam", cam_data)
    d = Vector(view_dir).normalized()
    fov = 2 * math.atan(18 / cam_data.lens)
    dist = radius / math.sin(fov / 2) * 0.80
    cam.location = center + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(cam)
    scene.camera = cam

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    tmp = path + ".rgba.png"
    scene.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    flatten_over_grey(tmp, path)
    os.remove(tmp)


def flatten_over_grey(src, dst, grey=0.46):
    """Put the transparent render (shadow-catcher shadows in its alpha) over flat mid-grey."""
    import numpy as np
    img = bpy.data.images.load(src)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    a = px[:, 3:4]
    px[:, :3] = px[:, :3] * a + grey * (1 - a)
    px[:, 3] = 1.0
    out = bpy.data.images.new("preview_flat", w, h, alpha=False)
    out.colorspace_settings.name = img.colorspace_settings.name
    out.pixels.foreach_set(px.ravel())
    out.filepath_raw = dst
    out.file_format = "PNG"
    out.save()


def main():
    args = parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    reset_scene()
    plant = build(args.seed)
    lo, hi, tris = stats(plant)
    export(plant, os.path.join(out, NAME + ".fbx"))
    if not args.no_render:
        render_preview(plant, os.path.join(out, NAME + ".png"), args.samples, (1.0, -0.75, 0.42))
    size = (hi - lo) * 100
    print(f"[{NAME}] triangles: {tris}")
    print(f"[{NAME}] bbox cm: min ({lo.x*100:.1f}, {lo.y*100:.1f}, {lo.z*100:.1f}) "
          f"max ({hi.x*100:.1f}, {hi.y*100:.1f}, {hi.z*100:.1f}) "
          f"size {size.x:.1f} x {size.y:.1f} x {size.z:.1f}")


main()
