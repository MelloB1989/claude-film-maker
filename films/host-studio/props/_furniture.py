"""Helpers shared by the furniture props (shelf, credenza, stool); builds on _studio.

- wood(): a preview material with procedural grain driven by the UVs, so the previews show
  that the grain runs along U (Unreal replaces the material by slot name anyway).
- bake(): apply an object's modifiers in place.
- uv_box(): world-scale box projection (1 UV unit = 1 m) with the grain along U.
- uv_tube(): UVs for round parts (legs, rails): U along the axis, V around it.
- finalize(): join, origin, tidy, weighted normals, FBX export, stats.
- Preview: stage() / shoot() render several views of one scene.
"""
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

import _studio as S

AXES = "xyz"


# --------------------------------------------------------------------------- materials

def _srgb(c):
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def wood(name, light, dark, roughness=0.5, ring=16.0, contrast=1.0, end_grain=False, seed=0.0):
    """Principled wood driven by UV: grain lines run along U. Colours are sRGB 0..1.

    Flat-sawn figure (two distorted band waves -> thin darker lines), pore streaks along U,
    slow colour drift along the board. With end_grain, growth rings seen in section."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = S.material(name, _srgb(light), roughness)
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")

    def node(kind, op=None, **inputs):
        n = nodes.new(kind)
        if op:
            n.operation = op
        for k, v in inputs.items():
            if isinstance(v, bpy.types.NodeSocket):
                links.new(v, n.inputs[k])
            else:
                n.inputs[k].default_value = v
        return n

    def maprange(value, f0, f1, t0, t1):
        return node("ShaderNodeMapRange", Value=value, **{"From Min": f0, "From Max": f1,
                                                         "To Min": t0, "To Max": t1}).outputs["Result"]

    def math_(op, a, b, c=None):
        n = nodes.new("ShaderNodeMath")
        n.operation = op
        for i, v in enumerate((a, b) if c is None else (a, b, c)):
            if isinstance(v, bpy.types.NodeSocket):
                links.new(v, n.inputs[i])
            else:
                n.inputs[i].default_value = v
        return n.outputs["Value"]

    uvw = nodes.new("ShaderNodeTexCoord").outputs["UV"]
    if end_grain:
        mp = node("ShaderNodeMapping", Vector=uvw, Location=(0.31 + seed, -0.55, 0))
        dist = node("ShaderNodeVectorMath", "LENGTH", Vector=mp.outputs["Vector"])
        nz = node("ShaderNodeTexNoise", Vector=mp.outputs["Vector"], Scale=5.0, Detail=2.0)
        r = math_("MULTIPLY_ADD", nz.outputs["Fac"], 0.01)
        links.new(dist.outputs["Value"], r.node.inputs[2])
        sn = math_("SINE", math_("MULTIPLY", r, 2 * math.pi / 0.0025), 0)
        line = maprange(sn, 0.55, 1.0, 0.0, 0.8)
        pores = node("ShaderNodeTexNoise", Vector=uvw, Scale=700.0, Detail=0.0).outputs["Fac"]
    else:
        # ring coordinate: V, bent slowly along the board and warped by noise, cut into thin
        # darker lines (late wood) every ~1/ring m, plus faint fine lines in between
        mp = node("ShaderNodeMapping", Vector=uvw, Location=(seed, seed * 0.37, seed * 0.71),
                  Scale=(1.1, 7.0, 1.0))
        sep = node("ShaderNodeSeparateXYZ", Vector=uvw)
        u, v = sep.outputs["X"], sep.outputs["Y"]
        warp = node("ShaderNodeTexNoise", Vector=mp.outputs["Vector"], Scale=1.0, Detail=3.0,
                    Roughness=0.55).outputs["Fac"]
        bend = math_("SINE", math_("MULTIPLY_ADD", u, 1.9, seed * 5.0), 0)
        coord = math_("MULTIPLY_ADD", bend, 0.022, v)
        coord = math_("MULTIPLY_ADD", warp, 0.06, coord)
        # uneven ring spacing and line strength, so the figure is not a regular pinstripe
        jm = node("ShaderNodeMapping", Vector=uvw, Location=(seed * 2, 0.5, 0), Scale=(0.6, 30.0, 1.0))
        jit = node("ShaderNodeTexNoise", Vector=jm.outputs["Vector"], Scale=1.0, Detail=1.0).outputs["Fac"]
        coord = math_("MULTIPLY_ADD", jit, 0.012, coord)
        sm = node("ShaderNodeMapping", Vector=uvw, Location=(seed, 1.3, 0), Scale=(0.35, 70.0, 1.0))
        strength = maprange(node("ShaderNodeTexNoise", Vector=sm.outputs["Vector"], Scale=1.0,
                                 Detail=0.0).outputs["Fac"], 0.3, 0.7, 0.15, 1.0)
        s1 = math_("SINE", math_("MULTIPLY", coord, 2 * math.pi * ring / 0.16), 0)
        s2 = math_("SINE", math_("MULTIPLY", coord, 2 * math.pi * ring * 3.7 / 0.16), 0)
        l1 = maprange(s1, 0.80, 1.0, 0.0, 0.75)
        l2 = maprange(s2, 0.7, 1.0, 0.0, 0.18)
        line = math_("MAXIMUM", math_("MULTIPLY", l1, strength), l2)
        pm = node("ShaderNodeMapping", Vector=uvw, Location=(seed * 3, 0, 0), Scale=(28.0, 900.0, 1.0))
        pores = node("ShaderNodeTexNoise", Vector=pm.outputs["Vector"], Scale=1.0, Detail=1.0).outputs["Fac"]
    line = math_("MULTIPLY", line, contrast)
    ramp = node("ShaderNodeValToRGB", Fac=line)
    ramp.color_ramp.elements[0].color = (*_srgb(light), 1)
    ramp.color_ramp.elements[1].color = (*_srgb(dark), 1)
    pore = maprange(pores, 0.56, 0.74, 0.0, 1.0)
    pore_f = maprange(pore, 0.0, 1.0, 1.0, 0.8)
    big = node("ShaderNodeTexNoise", Vector=mp.outputs["Vector"], Scale=1.3, Detail=1.0).outputs["Fac"]
    big_f = maprange(big, 0.3, 0.7, 0.92, 1.06)
    c1 = node("ShaderNodeVectorMath", "SCALE", Vector=ramp.outputs["Color"], Scale=pore_f)
    c2 = node("ShaderNodeVectorMath", "SCALE", Vector=c1.outputs["Vector"], Scale=big_f)
    links.new(c2.outputs["Vector"], bsdf.inputs["Base Color"])
    links.new(maprange(line, 0.0, 1.0, roughness - 0.05, roughness + 0.05), bsdf.inputs["Roughness"])
    bump = node("ShaderNodeBump", Height=pore, Strength=0.12, Distance=0.0003)
    bump.invert = True
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def emissive(name, color, strength, roughness=0.4):
    m = S.material(name, _srgb(color), roughness)
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    for key in ("Emission Color", "Emission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = (*_srgb(color), 1)
            break
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = strength
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.0
    return m


def plain(name, color, roughness, metallic=0.0):
    return S.material(name, _srgb(color), roughness, metallic)


# --------------------------------------------------------------------------- mesh helpers

def bake(ob):
    """Apply all modifiers of `ob` in place (keeps the object and its materials)."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)
    return ob


def bevel_box(name, lo, hi, mat, width, segments=3):
    ob = S.box(name, lo, hi, mat)
    mod = ob.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.profile = 0.5
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(35)
    mod.use_clamp_overlap = True
    return bake(ob)


def boolean_cut(ob, cutter):
    mod = ob.modifiers.new("Cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    bake(ob)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return ob


def _uv_layer(bm):
    return bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")


def uv_box(ob, grain, offset=(0.0, 0.0), end_slot=None, end_test=None):
    """World-scale box projection, grain along U.

    `grain` is the axis ('x', 'y' or 'z') the wood fibres run along. A face whose dominant
    normal is the grain axis is end grain: it gets U/V from the other two axes, and the
    material slot `end_slot` if given (and `end_test(face_centre)` is true, when given)."""
    g = AXES.index(grain)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uv = _uv_layer(bm)
    for f in bm.faces:
        n = f.normal
        a = max(range(3), key=lambda i: abs(n[i]))
        if a != g:
            u_ax, v_ax = g, 3 - a - g
        else:
            u_ax, v_ax = [i for i in range(3) if i != g]
            if end_slot is not None and (end_test is None or end_test(f.calc_center_median())):
                f.material_index = end_slot
        for lp in f.loops:
            co = ob.matrix_world @ lp.vert.co
            lp[uv].uv = (co[u_ax] + offset[0], co[v_ax] + offset[1])
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def uv_tube(ob, p0, p1, offset=(0.0, 0.0)):
    """U along the axis p0 -> p1 (metres), V around it (arc length at the local radius)."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = (p1 - p0).normalized()
    ref = Vector((0, 0, 1)) if abs(ax.z) < 0.9 else Vector((1, 0, 0))
    e1 = ax.cross(ref).normalized()
    e2 = ax.cross(e1)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uv = _uv_layer(bm)
    for f in bm.faces:
        pts = []
        for lp in f.loops:
            d = lp.vert.co - p0
            t = d.dot(ax)
            r = (d - t * ax)
            ang = math.atan2(r.dot(e2), r.dot(e1))
            pts.append((lp, t, ang, r.length))
        # caps (all points in a plane across the axis): planar map
        if abs(f.normal.dot(ax)) > 0.8:
            for lp, t, ang, rl in pts:
                lp[uv].uv = (rl * math.cos(ang) + offset[0], rl * math.sin(ang) + offset[1])
            continue
        angs = [p[2] for p in pts]
        if max(angs) - min(angs) > math.pi:
            angs = [a + 2 * math.pi if a < 0 else a for a in angs]
        rad = max(p[3] for p in pts) or 0.01
        for (lp, t, _a, _r), a in zip(pts, angs):
            lp[uv].uv = (t + offset[0], a * rad + offset[1])
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def mesh(name, verts, faces, mats, slots=None):
    """Object from raw verts/faces; `slots[i]` is the material index of face i."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.validate()
    for m in mats:
        me.materials.append(m)
    if slots:
        for p, s in zip(me.polygons, slots):
            p.material_index = s
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return ob


# --------------------------------------------------------------------------- finishing

def finalize(name, parts, origin, sharp_angle=40, weighted=True):
    """Join parts into one mesh, origin, tidy, weighted normals. Returns the object."""
    ob = S.join(name, parts)
    S.set_origin(ob, origin)
    S.tidy(ob, sharp_angle)
    if weighted:
        mod = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
        mod.keep_sharp = True
        mod.weight = 50
        mod.mode = "FACE_AREA"
    return ob


def export(ob, args):
    os.makedirs(args.out, exist_ok=True)
    fbx = os.path.join(args.out, ob.name + ".fbx")
    S.export_fbx(ob, fbx)
    stats(ob, fbx)
    return fbx


def stats(ob, fbx=""):
    lo, hi = S.bbox(ob)
    me = ob.data
    print("=" * 60)
    print(f"{ob.name}: exported {fbx}")
    print(f"{ob.name}: materials {[m.name for m in me.materials]}")
    print(f"{ob.name}: triangles {S.tri_count(ob)}")
    print(f"{ob.name}: bbox cm  X {lo.x*100:.2f}..{hi.x*100:.2f}  Y {lo.y*100:.2f}..{hi.y*100:.2f}"
          f"  Z {lo.z*100:.2f}..{hi.z*100:.2f}")
    print(f"{ob.name}: uv layers {[l.name for l in me.uv_layers]}")
    bm = bmesh.new()
    bm.from_mesh(me)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bnd = sum(1 for e in bm.edges if e.is_boundary)
    print(f"{ob.name}: non-manifold edges {nm} (boundary {bnd}), verts {len(bm.verts)}")
    bm.free()
    print("=" * 60)


# --------------------------------------------------------------------------- preview

def stage(floor=True, wall_x=None, wall_color=(0.93, 0.91, 0.87), floor_z=0.0, grey=0.18, extent=12.0):
    """Neutral world plus an optional floor and a wall facing +X at `wall_x`."""
    sc = bpy.context.scene
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        bg.inputs["Color"].default_value = (grey, grey, grey, 1)
        bg.inputs["Strength"].default_value = 1.0
    if floor:
        fm = S.material("_PreviewFloor", (grey, grey, grey), 0.8)
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=extent,
                              matrix=Matrix.Translation((0, 0, floor_z - 0.0005)))
        S.obj_from_bm(bm, "_floor", fm)
    if wall_x is not None:
        wm = S.material("_PreviewWall", _srgb(wall_color), 0.9)
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=extent,
                              matrix=Matrix.Translation((wall_x, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
        S.obj_from_bm(bm, "_wall", wm)
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    eevee = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    sc.render.engine = eevee
    for attr in ("use_shadows", "use_raytracing"):
        if hasattr(sc.eevee, attr):
            setattr(sc.eevee, attr, True)
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.render.resolution_x = sc.render.resolution_y = 1200
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"


def _clear(prefix):
    for o in list(bpy.context.scene.objects):
        if o.name.startswith(prefix):
            data = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if isinstance(data, bpy.types.Light):
                bpy.data.lights.remove(data)
            elif isinstance(data, bpy.types.Camera):
                bpy.data.cameras.remove(data)


def shoot(path, view_dir, lo, hi, samples=64, lens=60, margin=1.12, target=None, distance=None,
          key=110, fill=35, rim=70, light_size=None, up_shift=0.0):
    """Render one view. The camera looks along -view_dir and frames the box lo..hi,
    or sits `distance` from `target` when both are given. Lights follow the view."""
    _clear("_v_")
    sc = bpy.context.scene
    lo, hi = Vector(lo), Vector(hi)
    centre = (lo + hi) / 2 if target is None else Vector(target)
    size = light_size or (hi - lo).length
    v = Vector(view_dir).normalized()
    side = v.cross(Vector((0, 0, 1)))
    side = side.normalized() if side.length > 1e-6 else Vector((0, 1, 0))

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

    area("_v_key", v * 0.6 + side * 0.9 + Vector((0, 0, 0.9)), key, 1.4)
    area("_v_fill", v * 0.8 - side * 0.8 + Vector((0, 0, 0.3)), fill, 2.0)
    if rim:
        area("_v_rim", -v * 1.0 + Vector((0, 0, 0.8)), rim, 1.0)

    cam_data = bpy.data.cameras.new("_v_cam")
    cam_data.lens = lens
    cam_data.shift_y = up_shift
    cam = bpy.data.objects.new("_v_cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
    if distance is not None:
        cam.location = centre + v * distance
    else:
        corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        dg = bpy.context.evaluated_depsgraph_get()
        co, _scale = cam.camera_fit_coords(dg, [c for p in corners for c in p])
        cam.location = centre + (Vector(co) - centre) * margin
    span = (hi - lo).length + (cam.location - centre).length
    cam_data.clip_start = 0.005
    cam_data.clip_end = span * 10
    sc.eevee.taa_render_samples = samples
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print(f"rendered {path}")


def led_light(name, centre, length, width=0.014, energy=20.0, color=(1.0, 0.72, 0.45)):
    """Preview only: a strip area light pointing down (-Z), long along Y, standing in for
    the glowing LED diffuser (Eevee's emissive faces light little around them)."""
    light = bpy.data.lights.new(name, "AREA")
    light.shape = "RECTANGLE"
    light.size = length
    light.size_y = width
    light.energy = energy
    light.color = color
    ob = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = centre
    ob.rotation_euler = (0, 0, math.pi / 2)
    return ob


# --------------------------------------------------------------------------- shared materials

def oak():
    """Light oak, as in the concept: honey-blond, satin oil finish."""
    return wood("M_Oak", (0.83, 0.65, 0.44), (0.63, 0.46, 0.28), roughness=0.5, ring=11.0)


def oak_end():
    return wood("M_OakEnd", (0.75, 0.57, 0.37), (0.58, 0.42, 0.25), roughness=0.6, end_grain=True)


def black_metal(name="M_Plinth"):
    """Black powder-coated steel."""
    return plain(name, (0.035, 0.035, 0.037), 0.42, metallic=0.0)
