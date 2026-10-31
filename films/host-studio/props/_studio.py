"""Shared helpers for the host-studio prop scripts (Blender Python, headless).

Each prop script imports this module from its own directory, builds its parts as
separate mesh objects (one material each), then calls finish(), which joins them
into one mesh, fixes normals and smoothing, exports the FBX, renders the preview
and prints the bounding box in cm.

Units: 1 Blender unit = 1 m.
"""
import argparse
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector


# --------------------------------------------------------------------------- setup

def parse_args(script_file):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(script_file)), "out"))
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--samples", type=int, default=64)
    return ap.parse_args(argv)


def reset_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for block in list(coll):
            coll.remove(block)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0


def material(name, color, roughness, metallic=0.0, specular=None):
    """A Principled material; the base colour is also put on the viewport colour."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    rgba = (*color, 1.0)
    m.diffuse_color = rgba
    m.roughness = roughness
    m.metallic = metallic
    bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if specular is not None:
            for key in ("Specular IOR Level", "Specular"):
                if key in bsdf.inputs:
                    bsdf.inputs[key].default_value = specular
                    break
    return m


# --------------------------------------------------------------------------- mesh building

def obj_from_bm(bm, name, mat, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def frame_to(p0, p1):
    """Matrix whose local +Z runs from p0 towards p1, origin at the midpoint."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    return Matrix.Translation((p0 + p1) / 2) @ rot, d.length


def cylinder(name, p0, p1, r, mat, segs=24, r2=None):
    m, length = frame_to(p0, p1)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                          radius1=r, radius2=r if r2 is None else r2, depth=length, matrix=m)
    return obj_from_bm(bm, name, mat)


def box(name, lo, hi, mat):
    lo, hi = Vector(lo), Vector(hi)
    size = hi - lo
    m = Matrix.Translation((lo + hi) / 2) @ Matrix.Diagonal((*size, 1.0))
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    return obj_from_bm(bm, name, mat)


def prism(name, outline, p0, p1, mat, up=(1, 0, 0)):
    """Extrude a convex 2D outline [(u, v)] from p0 to p1 (u along `up` projected)."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = (p1 - p0).normalized()
    u = Vector(up) - Vector(up).dot(ax) * ax
    if u.length < 1e-6:
        u = ax.orthogonal()
    u.normalize()
    v = ax.cross(u)
    bm = bmesh.new()
    rings = []
    for base in (p0, p1):
        rings.append([bm.verts.new(base + a * u + b * v) for a, b in outline])
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((rings[0][i], rings[0][j], rings[1][j], rings[1][i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[1])
    return obj_from_bm(bm, name, mat)


def knurl_outline(r, teeth=18, depth=0.08):
    pts = []
    for i in range(teeth * 2):
        a = math.pi * i / teeth
        rr = r if i % 2 == 0 else r * (1 - depth)
        pts.append((rr * math.cos(a), rr * math.sin(a)))
    return pts


def circle_outline(r, segs=24):
    return [(r * math.cos(2 * math.pi * i / segs), r * math.sin(2 * math.pi * i / segs)) for i in range(segs)]


def rounded_rect(w, h, r, segs=4):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(segs + 1):
            a = math.radians(a0 + 90 * k / segs)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def lathe(name, profile, mats, segs=64, matrix=None, mat_split=None):
    """Revolve a (r, z) profile around local Z. Points with r == 0 become poles.

    `mats` is a list of materials; `mat_split(i)` gives the slot for the band
    between profile points i and i + 1 (default slot 0)."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        if r <= 1e-9:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * k / segs),
                                        r * math.sin(2 * math.pi * k / segs), z)) for k in range(segs)])
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        slot = mat_split(i) if mat_split else 0
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                f = bm.faces.new((a[0], b[k], b[k2]))
            elif len(b) == 1:
                f = bm.faces.new((a[k], a[k2], b[0]))
            else:
                f = bm.faces.new((a[k], a[k2], b[k2], b[k]))
            f.material_index = slot
    if matrix is not None:
        bm.transform(matrix)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def sweep(name, points, profile, mat, hint=(1, 0, 0), caps=True, closed=False):
    """Sweep a 2D profile [(u, v)] along a polyline with rotation-minimising frames."""
    pts = [Vector(p) for p in points]
    n = len(pts)
    tans = []
    for i in range(n):
        if closed:
            t = pts[(i + 1) % n] - pts[i - 1]
        else:
            t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        tans.append(t.normalized())
    nrm = Vector(hint) - Vector(hint).dot(tans[0]) * tans[0]
    if nrm.length < 1e-6:
        nrm = tans[0].orthogonal()
    nrm.normalize()
    bm = bmesh.new()
    rings = []
    for i in range(n):
        t = tans[i]
        nrm = (nrm - nrm.dot(t) * t).normalized()
        b = t.cross(nrm)
        rings.append([bm.verts.new(pts[i] + u * nrm + v * b) for u, v in profile])
    m = len(profile)
    last = n if closed else n - 1
    for i in range(last):
        a, c = rings[i], rings[(i + 1) % n]
        for k in range(m):
            k2 = (k + 1) % m
            bm.faces.new((a[k], a[k2], c[k2], c[k]))
    if caps and not closed:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    return obj_from_bm(bm, name, mat)


def catmull_rom(ctrl, per_seg=12):
    """Smooth curve through control points (endpoints included)."""
    c = [Vector(p) for p in ctrl]
    c = [c[0] * 2 - c[1]] + c + [c[-1] * 2 - c[-2]]
    out = []
    for i in range(1, len(c) - 2):
        p0, p1, p2, p3 = c[i - 1], c[i], c[i + 1], c[i + 2]
        for s in range(per_seg):
            t = s / per_seg
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    out.append(c[-2])
    return out


def bevel(ob, width, segments=2, angle=35):
    mod = ob.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle)
    return ob


# --------------------------------------------------------------------------- finishing

def _bake(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    me.transform(ob.matrix_world)
    new = bpy.data.objects.new(ob.name + "_baked", me)
    bpy.context.scene.collection.objects.link(new)
    bpy.data.objects.remove(ob, do_unlink=True)
    return new


def join(name, objects):
    objects = [_bake(o) for o in objects]
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    return ob


def tidy(ob, sharp_angle=40):
    """Outward normals, smooth faces, sharp edges above `sharp_angle` degrees."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    lim = math.radians(sharp_angle)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if not e.is_manifold:
            e.smooth = False
            continue
        e.smooth = e.calc_face_angle(0.0) <= lim
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def set_origin(ob, origin):
    """Move mesh so that the world point `origin` becomes (0, 0, 0); apply transforms."""
    ob.data.transform(Matrix.Translation(-Vector(origin)))
    ob.matrix_world = Matrix.Identity(4)


def bbox(ob):
    vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return lo, hi


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def export_fbx(ob, path):
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"MESH"},
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
        axis_forward="-Y", axis_up="Z", mesh_smooth_type="FACE",
        use_mesh_modifiers=True, add_leaf_bones=False, bake_space_transform=False,
        path_mode="STRIP")


def render_preview(ob, path, view_dir, samples=64, lens=60, margin=1.12, floor=True):
    sc = bpy.context.scene
    lo, hi = bbox(ob)
    centre = (lo + hi) / 2
    size = (hi - lo).length

    # neutral mid-grey world and floor
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    grey = 0.18
    if bg is not None:
        bg.inputs["Color"].default_value = (grey, grey, grey, 1)
        bg.inputs["Strength"].default_value = 1.0
    if floor:
        fm = material("_PreviewFloor", (grey, grey, grey), 0.8)
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size * 20,
                              matrix=Matrix.Translation((centre.x, centre.y, lo.z - 0.0005)))
        obj_from_bm(bm, "_floor", fm)

    # soft lights scaled to the prop
    def area(name, direction, energy, scale):
        light = bpy.data.lights.new(name, "AREA")
        light.shape = "DISK"
        light.size = size * scale
        light.energy = energy * size * size
        lo_ = bpy.data.objects.new(name, light)
        sc.collection.objects.link(lo_)
        d = Vector(direction).normalized()
        lo_.location = centre + d * size * 2.2
        lo_.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()

    v = Vector(view_dir).normalized()
    side = v.cross(Vector((0, 0, 1))).normalized()
    area("_key", v * 0.6 + side * 0.9 + Vector((0, 0, 0.9)), 110, 1.4)
    area("_fill", v * 0.8 - side * 0.8 + Vector((0, 0, 0.3)), 35, 2.0)
    area("_rim", -v * 1.0 + Vector((0, 0, 0.8)), 70, 1.0)

    cam_data = bpy.data.cameras.new("_cam")
    cam_data.lens = lens
    cam = bpy.data.objects.new("_cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x = sc.render.resolution_y = 1200
    sc.render.resolution_percentage = 100
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    dg = bpy.context.evaluated_depsgraph_get()
    co, _scale = cam.camera_fit_coords(dg, [c for p in corners for c in p])
    cam.location = co
    cam.location = centre + (Vector(co) - centre) * margin
    cam_data.clip_start = size * 0.01
    cam_data.clip_end = size * 100

    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    eevee = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    try:
        sc.render.engine = eevee
        sc.eevee.taa_render_samples = samples
        for attr in ("use_shadows", "use_raytracing"):
            if hasattr(sc.eevee, attr):
                setattr(sc.eevee, attr, True)
    except Exception:
        sc.render.engine = "CYCLES"
        sc.cycles.samples = samples
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def finish(name, parts, origin, view_dir, args, sharp_angle=40, lens=60, floor=True):
    """Join parts, tidy, set origin, export FBX, render PNG, print stats."""
    ob = join(name, parts)
    set_origin(ob, origin)
    tidy(ob, sharp_angle)
    os.makedirs(args.out, exist_ok=True)
    fbx = os.path.join(args.out, name + ".fbx")
    export_fbx(ob, fbx)
    lo, hi = bbox(ob)
    dims = (hi - lo) * 100
    print("=" * 60)
    print(f"{name}: exported {fbx}")
    print(f"{name}: materials {[m.name for m in ob.data.materials]}")
    print(f"{name}: triangles {tri_count(ob)}")
    print(f"{name}: bbox cm  X {lo.x*100:.1f}..{hi.x*100:.1f}  Y {lo.y*100:.1f}..{hi.y*100:.1f}"
          f"  Z {lo.z*100:.1f}..{hi.z*100:.1f}")
    print(f"{name}: size cm  {dims.x:.1f} x {dims.y:.1f} x {dims.z:.1f}")
    print("=" * 60)
    if not args.no_render:
        render_preview(ob, os.path.join(args.out, name + ".png"), view_dir, args.samples, lens=lens, floor=floor)
    return ob
