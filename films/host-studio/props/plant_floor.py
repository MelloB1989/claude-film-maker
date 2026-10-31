"""plant_floor: a tall monstera deliciosa in a matte off-white ceramic cylinder pot.

Run headless:
    blender -b --factory-startup -P films/host-studio/props/plant_floor.py -- --out films/host-studio/props/out

Writes <out>/plant_floor.fbx and <out>/plant_floor.png (1200x1200 preview) and prints the
exported bounding box in cm. 1 Blender unit = 1 m; origin at the bottom centre of the pot.
Seeded (--seed), so a run is reproducible.
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

NAME = "plant_floor"

# Pot: off-white matte ceramic cylinder.
POT_H = 0.35
POT_R_TOP = 0.160
POT_R_BOT = 0.150
POT_WALL = 0.012
SOIL_Z = 0.315

LEAF_THICK = 0.002


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


# ---------------------------------------------------------------- monstera leaf

def leaf_outline(L, theta, ws, power, tip):
    """Cordate margin in leaf space: x lateral, y along the midrib, base (petiole) at origin."""
    rr = ((1 + math.cos(theta)) / 2) ** power
    r = L * rr * (1 - tip * (1 - math.exp(-(theta / 0.4) ** 2)))
    return r * math.sin(theta) * ws, r * math.cos(theta)


def build_leaf(rng, L, mature):
    """Flat-then-shaped monstera blade in leaf space. Returns (verts, faces, midrib points).

    The half-blade is a (u, s) grid: u runs from the basal sinus (0) to the tip (1) along the
    margin, s from the midrib (0) to the margin (1) along a lateral vein. Splits are columns of
    cells left out from the margin inwards; fenestrations are small slots near the midrib.
    """
    nu, ns = 40, 14
    theta_max = math.radians(157)
    ws, power, tip = 0.80, 0.80, 0.12
    cup = rng.uniform(0.18, 0.30)
    margin_droop = rng.uniform(0.45, 0.75)
    droop = rng.uniform(0.12, 0.28)
    wave = rng.uniform(0.006, 0.014)
    wave_ph = rng.uniform(0, 6.28)

    def shape_z(x, y):
        ax = abs(x)
        z = cup * ax - margin_droop * ax * ax / L - droop * L * (max(y, 0) / L) ** 2
        z += wave * L * math.sin(7.0 * ax / L + wave_ph) * (ax / (0.5 * L))
        return z

    verts, faces = [], []
    us = [(i / nu) for i in range(nu + 1)]
    ss = [(j / ns) for j in range(ns + 1)]

    for side in (-1, 1):
        # Splits: columns of missing cells from the margin inwards.
        cut = {}
        if mature:
            nsplit = rng.randint(6, 8)
            lo, hi = 4, nu - 5
            cols = []
            span = (hi - lo) / nsplit
            for k in range(nsplit):
                c = int(lo + span * (k + 0.5) + rng.uniform(-span * 0.2, span * 0.2))
                cols.append(c)
            for c in cols:
                depth = rng.uniform(0.24, 0.42)
                for j in range(ns):
                    s_mid = (ss[j] + ss[j + 1]) / 2
                    if s_mid > depth:
                        cut[(c, j)] = True
            # Fenestrations: slots between neighbouring splits, near the midrib.
            for a, b in zip(cols, cols[1:]):
                if b - a >= 4 and rng.random() < 0.45:
                    c = (a + b) // 2
                    j0 = 2
                    for j in range(j0, j0 + 2):
                        cut[(c, j)] = True
        base = len(verts)
        for i, u in enumerate(us):
            mx, my = leaf_outline(L, theta_max * (1 - u), ws, power, tip)
            ay = L * u ** 4
            for j, s in enumerate(ss):
                x = side * mx * s
                y = ay + (my - ay) * s
                verts.append(Vector((x, y, shape_z(x, y))))
        for i in range(nu):
            for j in range(ns):
                if (i, j) in cut:
                    continue
                a = base + i * (ns + 1) + j
                b = base + (i + 1) * (ns + 1) + j
                faces.append([a, b, b + 1, a + 1] if side > 0 else [a, a + 1, b + 1, b])

    midrib = []
    for k in range(31):
        y = 0.88 * L * k / 30
        midrib.append(Vector((0, y, shape_z(0, y))))
    return verts, faces, midrib


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


# ---------------------------------------------------------------- the plant

def build(seed):
    rng = random.Random(seed)
    mats = {
        "pot": make_material("M_Pot", (0.70, 0.67, 0.61), 0.78),
        "soil": make_material("M_Soil", (0.035, 0.024, 0.016), 0.95),
        "leaf": make_material("M_Leaf", (0.006, 0.042, 0.008), 0.45),
        "leaf_young": make_material("M_LeafYoung", (0.022, 0.110, 0.016), 0.42),
        "stem": make_material("M_Stem", (0.050, 0.140, 0.035), 0.55),
        "root": make_material("M_Root", (0.110, 0.070, 0.040), 0.85),
    }
    objects = []

    # Pot: rounded base, straight slightly tapered wall, rounded rim, inner wall down below the soil.
    prof = [(0.0, 0.0)]
    bev = 0.008
    for k in range(5):
        a = math.pi / 2 * k / 4
        prof.append((POT_R_BOT - bev + bev * math.sin(a), bev - bev * math.cos(a)))
    for k in range(1, 8):
        t = k / 8
        prof.append((POT_R_BOT + (POT_R_TOP - POT_R_BOT) * t, bev + (POT_H - 0.01 - bev) * t))
    rr = POT_WALL / 2
    cx, cz = POT_R_TOP - rr, POT_H - rr
    for k in range(7):
        a = math.pi * k / 6
        prof.append((cx + rr * math.cos(a), cz + rr * math.sin(a)))
    prof.append((POT_R_TOP - POT_WALL, POT_H - 0.03))
    prof.append((POT_R_TOP - POT_WALL - 0.002, SOIL_Z - 0.03))
    v, f = lathe(prof, 64)
    objects.append(mesh_object("pot", v, f, mats["pot"]))

    # Soil: a low mound inside the rim.
    soil_r = POT_R_TOP - POT_WALL - 0.001
    sprof = [(0.0, SOIL_Z + 0.012)]
    for k in range(1, 9):
        t = k / 8
        sprof.append((soil_r * t, SOIL_Z + 0.012 * (1 - t * t)))
    sprof.append((soil_r - 0.002, SOIL_Z - 0.02))
    v, f = lathe(sprof, 48)
    v = [Vector(p) + Vector((0, 0, 0.003 * math.sin(p[0] * 90) * math.cos(p[1] * 70))) for p in v]
    objects.append(mesh_object("soil", v, f, mats["soil"]))
    pot_tree = bvh(*lathe([(POT_R_BOT, 0), (POT_R_TOP, POT_H), (POT_R_TOP - POT_WALL, POT_H)], 32))

    # Two short thick stems (the climbing stem with nodes) that the petioles rise from.
    trunks = []
    for k, (tx, ty, lean, h) in enumerate([(-0.035, 0.020, (0.10, 0.06), 0.16),
                                           (0.040, -0.025, (-0.06, -0.12), 0.12)]):
        base = Vector((tx, ty, SOIL_Z - 0.03))
        top = base + Vector((lean[0] * h, lean[1] * h, h))
        pts = [base.lerp(top, i / 12) for i in range(13)]
        radii = [0.019 - 0.004 * i / 12 + (0.002 if i % 4 == 2 else 0.0) for i in range(13)]
        v, f = tube(pts, radii, sides=14)
        objects.append(mesh_object(f"trunk{k}", v, f, mats["stem"]))
        trunks.append(top)
        # An aerial root arching from the stem side into the soil.
        side = Vector((math.cos(k * 2.6 + 0.8), math.sin(k * 2.6 + 0.8), 0))
        r0 = base.lerp(top, 0.7) + side * 0.016
        r3 = Vector((tx, ty, SOIL_Z)) + side * 0.09 + Vector((0, 0, -0.005))
        pts = bezier(r0, r0 + side * 0.05 + Vector((0, 0, 0.01)), r3 + Vector((0, 0, 0.05)), r3, 16)
        v, f = tube(pts, [0.0045 - 0.0015 * i / 16 for i in range(17)], sides=8)
        objects.append(mesh_object(f"root{k}", v, f, mats["root"]))

    # Leaves: lower ones further out and lower-pitched, upper ones higher, closer in, younger.
    n_leaves = 13
    placed = []  # (verts_world, faces, tree, petiole_tree)
    golden = math.radians(137.5)
    az0 = rng.uniform(0, 2 * math.pi)
    for k in range(n_leaves):
        h = k / (n_leaves - 1)
        young = k >= n_leaves - 2
        ok = False
        for attempt in range(80):
            across = rng.uniform(0.25, 0.30) if young else rng.uniform(0.33, 0.45)
            L = across / 0.96
            az = az0 + k * golden + rng.uniform(-0.35, 0.35) + attempt * 0.21
            jz = 0.66 + 0.92 * h + rng.uniform(-0.05, 0.05)
            jr = 0.42 - 0.26 * h + rng.uniform(-0.04, 0.04)
            outward = Vector((math.cos(az), math.sin(az), 0))
            junction = Vector((0, 0, 0)) + outward * jr + Vector((0, 0, jz))
            pitch = math.radians((8 if young else 38 - 26 * h) + rng.uniform(-8, 8))
            yaw = az + rng.uniform(-0.3, 0.3)
            d = Vector((math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), -math.sin(pitch)))
            frame = leaf_frame(d, rng.uniform(-0.25, 0.25))

            lrng = random.Random(rng.random())
            lv, lf, midrib = build_leaf(lrng, L, mature=not young)
            wv = [junction + frame @ p for p in lv]
            mr = [junction + frame @ (p + Vector((0, 0, 0.0015))) for p in midrib]

            trunk = min(trunks, key=lambda t: (t.xy - junction.xy).length)
            start = trunk + Vector((rng.uniform(-0.01, 0.01), rng.uniform(-0.01, 0.01), -0.01))
            hb = (junction.xy - start.xy).normalized()
            hb = Vector((hb.x, hb.y, 0))
            span = (junction - start).length
            elev = math.radians(rng.uniform(12, 38))
            tangent = (hb * math.cos(elev) + Vector((0, 0, 1)) * math.sin(elev)).normalized()
            ppts = bezier(start, start + Vector((0, 0, 0.55 * span)) + hb * 0.02,
                          junction - tangent * 0.42 * span, junction, 40)
            pr = [0.0085 - 0.0030 * i / 40 for i in range(41)]
            pv, pf = tube(ppts, pr, sides=10)

            tree = bvh(wv, lf)
            # Upper petiole only for collision tests: the bases legitimately bunch at the stems.
            upper = [p for p in ppts[12:]]
            uv, uf = tube(upper, pr[12:], sides=6, caps=False)
            utree = bvh(uv, uf)
            clash = bool(tree.overlap(pot_tree)) or min(p.z for p in wv) < POT_H + 0.05
            for ov, of, otree, outree in placed:
                if clash:
                    break
                if tree.overlap(otree) or too_close(wv, otree, 0.012):
                    clash = True
                elif tree.overlap(outree) or utree.overlap(otree):
                    clash = True
            if not clash:
                ok = True
                break
        if not ok:
            print(f"[{NAME}] leaf {k}: no clean placement, skipped")
            continue
        placed.append((wv, lf, tree, utree))
        ob = mesh_object(f"leaf{k}", wv, lf, mats["leaf_young" if young else "leaf"])
        solidify(ob, LEAF_THICK)
        objects.append(ob)
        v, f = tube(mr, [0.0045 * (1 - i / 30) + 0.0008 for i in range(31)], sides=6)
        objects.append(mesh_object(f"midrib{k}", v, f, mats["leaf_young" if young else "leaf"]))
        objects.append(mesh_object(f"petiole{k}", pv, pf, mats["stem"]))
    print(f"[{NAME}] leaves placed: {len(placed)}")

    # Join everything into one mesh with its origin at the bottom centre.
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
        render_preview(plant, os.path.join(out, NAME + ".png"), args.samples, (1.0, -1.15, 0.42))
    size = (hi - lo) * 100
    print(f"[{NAME}] triangles: {tris}")
    print(f"[{NAME}] bbox cm: min ({lo.x*100:.1f}, {lo.y*100:.1f}, {lo.z*100:.1f}) "
          f"max ({hi.x*100:.1f}, {hi.y*100:.1f}, {hi.z*100:.1f}) "
          f"size {size.x:.1f} x {size.y:.1f} x {size.z:.1f}")


main()
