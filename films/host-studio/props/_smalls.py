"""Helpers for the small shelf props (bitcoin_coin, pickaxe, candle, the vases, lyzn_block).

Builds on _studio.py (join, tidy, set_origin, export_fbx, bbox) and adds what these props need:
lathes and lofts that carry their own UVs, box/planar UV projection, a UV test image for label
slots, and a preview stage (a light-oak board against a warm plaster wall, lit like the shelves)
that renders the 3/4, front and close-up views from one scene.

Units: 1 Blender unit = 1 m. CM / MM convert.
"""
import math
import os

import bpy
import bmesh
from mathutils import Matrix, Vector

import _studio as S

CM = 0.01
MM = 0.001
TAU = 2 * math.pi


# --------------------------------------------------------------------------- materials

def principled(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def set_input(node, names, value):
    """Set the first input of `node` that exists among `names` (the names moved between versions)."""
    for key in (names if isinstance(names, (list, tuple)) else [names]):
        if key in node.inputs:
            node.inputs[key].default_value = value
            return True
    return False


def glassy(m, roughness=0.0, ior=1.5, tint=(1.0, 1.0, 1.0), frost=0.0, frost_color=(0.92, 0.91, 0.89),
           backfaces=True):
    """Clear (or frosted) glass / acrylic for the Eevee preview.

    The Principled node keeps transmission 1 and the IOR (what an exporter reads); the surface the
    preview renders is a blended mix: Fresnel-weighted gloss over a see-through layer, optionally
    clouded by a milky translucent layer (`frost`). Eevee's screen-traced refraction leaves black
    bands wherever a ray only sees glass, so blending is the look that holds up here. Shadow rays
    pass through."""
    b = principled(m)
    set_input(b, ["Transmission Weight", "Transmission"], 1.0)
    set_input(b, "IOR", ior)
    set_input(b, "Roughness", roughness)
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND"),
                      ("use_transparency_overlap", backfaces), ("show_transparent_back", backfaces),
                      ("use_transparent_shadow", True), ("use_backface_culling", not backfaces)):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    fres = nt.nodes.new("ShaderNodeFresnel")
    fres.inputs["IOR"].default_value = ior
    gloss = nt.nodes.new("ShaderNodeBsdfGlossy" if "ShaderNodeBsdfGlossy" in dir(bpy.types) else "ShaderNodeBsdfAnisotropic")
    gloss.inputs["Roughness"].default_value = max(roughness, 0.02)
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    clear.inputs["Color"].default_value = (*tint, 1)
    body = clear
    if frost > 0:
        diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
        diff.inputs["Color"].default_value = (*frost_color, 1)
        fm = nt.nodes.new("ShaderNodeMixShader")
        fm.inputs[0].default_value = frost
        nt.links.new(clear.outputs[0], fm.inputs[1])
        nt.links.new(diff.outputs[0], fm.inputs[2])
        body = fm
    fk = nt.nodes.new("ShaderNodeMath")
    fk.operation = "MULTIPLY"
    fk.inputs[1].default_value = 0.6
    nt.links.new(fres.outputs[0], fk.inputs[0])
    surf = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fk.outputs[0], surf.inputs[0])
    nt.links.new(body.outputs[0], surf.inputs[1])
    nt.links.new(gloss.outputs[0], surf.inputs[2])
    lp = nt.nodes.new("ShaderNodeLightPath")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    sh = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Shadow Ray"], sh.inputs[0])
    nt.links.new(surf.outputs[0], sh.inputs[1])
    nt.links.new(tr.outputs[0], sh.inputs[2])
    nt.links.new(sh.outputs[0], out.inputs["Surface"])
    return m


def roughness_noise(m, lo, hi, scale=400.0, detail=6.0):
    """Drive roughness with a noise texture between lo and hi (wear, polish marks)."""
    nt = m.node_tree
    b = principled(m)
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = detail
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0.35
    ramp.inputs["From Max"].default_value = 0.65
    ramp.inputs["To Min"].default_value = lo
    ramp.inputs["To Max"].default_value = hi
    nt.links.new(tex.outputs["Fac"], ramp.inputs["Value"])
    nt.links.new(ramp.outputs["Result"], b.inputs["Roughness"])
    return m


def uv_test_image(name="_UVTest", size=512):
    """Generated label test image: U tints red to the right, V tints green upwards, a grid,
    a white border, an arrow pointing up and the word UP under it."""
    import numpy as np
    img = bpy.data.images.get(name)
    if img is not None:
        return img
    img = bpy.data.images.new(name, size, size, alpha=False)
    u = (np.arange(size) + 0.5)[None, :] / size
    v = (np.arange(size) + 0.5)[:, None] / size
    U = np.broadcast_to(u, (size, size))
    V = np.broadcast_to(v, (size, size))
    rgb = np.zeros((size, size, 3))
    rgb[..., 0] = 0.15 + 0.7 * U
    rgb[..., 1] = 0.15 + 0.7 * V
    rgb[..., 2] = 0.30
    grid = ((U * 8) % 1 < 0.012) | ((V * 8) % 1 < 0.012)
    rgb[grid] = 0.55

    def fill(mask, c):
        rgb[mask] = c

    def rect(x0, x1, y0, y1):
        return (U >= x0) & (U <= x1) & (V >= y0) & (V <= y1)

    fill((U < 0.03) | (U > 0.97) | (V < 0.03) | (V > 0.97), 1.0)
    fill(rect(0.46, 0.54, 0.30, 0.62), 1.0)                                  # arrow shaft
    fill((V >= 0.60) & (V <= 0.84) & (np.abs(U - 0.5) <= (0.84 - V) * 0.6), 1.0)  # arrow head
    for r in ((0.36, 0.39, 0.08, 0.22), (0.45, 0.48, 0.08, 0.22), (0.36, 0.48, 0.08, 0.11),   # U
              (0.53, 0.56, 0.08, 0.22), (0.53, 0.64, 0.19, 0.22), (0.53, 0.64, 0.135, 0.165),  # P
              (0.61, 0.64, 0.135, 0.22)):
        fill(rect(*r), 1.0)
    fill(rect(0.86, 0.95, 0.47, 0.53), (1.0, 0.2, 0.2))                       # red tab: +U side
    rgba = np.concatenate([rgb, np.ones((size, size, 1))], axis=-1)
    img.pixels.foreach_set(rgba.astype(np.float32).ravel())
    img.pack()
    return img


def label_material(name):
    """A label slot: the orchestrator textures it; the preview shows the UV test image."""
    m = S.material(name, (0.8, 0.8, 0.8), 0.5)
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = uv_test_image()
    nt.links.new(tex.outputs["Color"], principled(m).inputs["Base Color"])
    return m


# --------------------------------------------------------------------------- mesh building

def obj(bm, name, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def arc_lengths(profile):
    s = [0.0]
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        s.append(s[-1] + math.hypot(r1 - r0, z1 - z0))
    return s


def lathe_uv(name, profile, mats, segs=64, mat_split=None, warp=None, r_ref=None):
    """Revolve a (r, z) profile (metres) around Z, with UVs.

    Points with r == 0 become poles. `mat_split(i)` gives the slot of the band between points i
    and i + 1. `warp(theta, r, z) -> (x, y, z)` replaces the plain (r cos, r sin, z) placement
    (hand-thrown wobble). UVs: U = theta * r_ref (metres around the widest girth), V = arc length
    down the profile (metres), so a tiling texture keeps one scale everywhere."""
    if r_ref is None:
        r_ref = max(r for r, _ in profile)
    s = arc_lengths(profile)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    rings = []
    for r, z in profile:
        if r <= 1e-9:
            rings.append([bm.verts.new((0.0, 0.0, z) if warp is None else warp(0.0, 0.0, z))])
            continue
        ring = []
        for k in range(segs):
            th = TAU * k / segs
            co = (r * math.cos(th), r * math.sin(th), z) if warp is None else warp(th, r, z)
            ring.append(bm.verts.new(co))
        rings.append(ring)
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        slot = mat_split(i) if mat_split else 0
        for k in range(segs):
            k2 = (k + 1) % segs
            u0, u1 = TAU * k / segs * r_ref, TAU * (k + 1) / segs * r_ref
            um = (u0 + u1) / 2
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                vs, uvs = (a[0], b[k], b[k2]), ((um, s[i]), (u0, s[i + 1]), (u1, s[i + 1]))
            elif len(b) == 1:
                vs, uvs = (a[k], a[k2], b[0]), ((u0, s[i]), (u1, s[i]), (um, s[i + 1]))
            else:
                vs = (a[k], a[k2], b[k2], b[k])
                uvs = ((u0, s[i]), (u1, s[i]), (u1, s[i + 1]), (u0, s[i + 1]))
            f = bm.faces.new(vs)
            f.material_index = slot
            for loop, uv in zip(f.loops, uvs):
                loop[uvl].uv = uv
    return obj(bm, name, mats)


def loft(name, rings, mats, cap0=None, cap1=None):
    """Skin a list of rings (each a list of points, same count, closed loops) with UVs.

    cap0 / cap1: None (open), a point (a pole the ring closes to) or "ngon".
    UVs: U = distance along the loft (metres, through the ring centres), V = distance around
    each ring (metres): wood grain on U runs along the part."""
    rings = [[Vector(p) for p in r] for r in rings]
    m = len(rings[0])
    cents = [sum(r, Vector()) / m for r in rings]
    us = [0.0]
    for c0, c1 in zip(cents, cents[1:]):
        us.append(us[-1] + (c1 - c0).length)
    vs_all = []
    for r in rings:
        acc = [0.0]
        for k in range(m):
            acc.append(acc[-1] + (r[(k + 1) % m] - r[k]).length)
        vs_all.append(acc)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    bv = [[bm.verts.new(p) for p in r] for r in rings]
    for i in range(len(rings) - 1):
        for k in range(m):
            k2 = (k + 1) % m
            f = bm.faces.new((bv[i][k], bv[i][k2], bv[i + 1][k2], bv[i + 1][k]))
            for loop, uv in zip(f.loops, ((us[i], vs_all[i][k]), (us[i], vs_all[i][k + 1]),
                                          (us[i + 1], vs_all[i + 1][k + 1]), (us[i + 1], vs_all[i + 1][k]))):
                loop[uvl].uv = uv
    for cap, ring, ui, vv, end in ((cap0, bv[0], us[0], vs_all[0], 0), (cap1, bv[-1], us[-1], vs_all[-1], 1)):
        if cap is None:
            continue
        if isinstance(cap, str):
            f = bm.faces.new(ring if end else list(reversed(ring)))
            for loop in f.loops:
                co = loop.vert.co
                loop[uvl].uv = (co.x, co.y)
            continue
        pole = bm.verts.new(cap)
        du = (Vector(cap) - (cents[0] if end == 0 else cents[-1])).length
        up = ui - du if end == 0 else ui + du
        for k in range(m):
            k2 = (k + 1) % m
            tri = (ring[k2], ring[k], pole) if end == 0 else (ring[k], ring[k2], pole)
            f = bm.faces.new(tri)
            uv_k, uv_k2 = (ui, vv[k]), (ui, vv[k + 1])
            pole_uv = (up, (vv[k] + vv[k + 1]) / 2)
            for loop, uv in zip(f.loops, ((uv_k2, uv_k, pole_uv) if end == 0 else (uv_k, uv_k2, pole_uv))):
                loop[uvl].uv = uv
    return obj(bm, name, mats)


def box_uv(bm, scale=1.0, grain=0):
    """World-scale box projection on a bmesh (1 UV unit = `scale` metres). The face's dominant
    normal axis picks the plane; `grain` (0 = X, 1 = Y, 2 = Z) is the axis U follows wherever the
    plane contains it, so wood grain runs along the part."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        plane = [i for i in range(3) if i != ax]
        if grain in plane:
            ua, va = grain, [i for i in plane if i != grain][0]
        else:
            ua, va = plane
        for loop in f.loops:
            co = loop.vert.co
            loop[uvl].uv = (co[ua] / scale, co[va] / scale)


def non_manifold_edges(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return n


def bake(ob):
    """Apply modifiers (into a new object, the old one is removed)."""
    return S._bake(ob)


# --------------------------------------------------------------------------- preview stage

def _oak_material():
    m = bpy.data.materials.get("_PreviewOak")
    if m is not None:
        return m
    m = S.material("_PreviewOak", (0.56, 0.40, 0.25), 0.48)
    nt = m.node_tree
    b = principled(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (70.0, 2.2, 70.0)     # streaks run along Y (the board)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 8.0
    nz.inputs["Roughness"].default_value = 0.62
    set_input(nz, "Distortion", 0.6)
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.30, (0.36, 0.22, 0.11, 1)
    els[1].position, els[1].color = 0.72, (0.55, 0.38, 0.21, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def _plaster_material():
    m = bpy.data.materials.get("_PreviewPlaster")
    if m is not None:
        return m
    m = S.material("_PreviewPlaster", (0.74, 0.64, 0.52), 0.92)
    nt = m.node_tree
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 60.0
    nz.inputs["Detail"].default_value = 6.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], principled(m).inputs["Normal"])
    return m


def _world(strength=0.6):
    sc = bpy.context.scene
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    nt = world.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    bg.inputs["Strength"].default_value = strength
    path = None
    try:
        d = bpy.utils.system_resource("DATAFILES", path="studiolights/world")
        for cand in ("interior.exr", "studio.exr", "courtyard.exr"):
            if os.path.exists(os.path.join(d, cand)):
                path = os.path.join(d, cand)
                break
    except Exception:
        path = None
    if path:
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(path, check_existing=True)
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    else:
        bg.inputs["Color"].default_value = (0.2, 0.18, 0.16, 1)


def stage(lo, hi, wall_gap=None, board=True, light_scale=1.0):
    """A light-oak board under the props, a warm plaster wall behind them (towards -X), an
    interior HDRI and three soft, warm area lights scaled to the props' size."""
    sc = bpy.context.scene
    size = max((hi - lo).length, 0.05)
    centre = (lo + hi) / 2
    _world()
    if board:
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=max(size * 8, 1.0),
                              matrix=Matrix.Translation((centre.x, centre.y, lo.z - 0.0002)))
        obj(bm, "_board", [_oak_material()])
    gap = wall_gap if wall_gap is not None else max(size * 0.45, 0.05)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=max(size * 8, 1.0),
                          matrix=Matrix.Translation((lo.x - gap, centre.y, lo.z)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    obj(bm, "_wall", [_plaster_material()])

    def area(name, loc_dir, energy, scale, color):
        light = bpy.data.lights.new(name, "AREA")
        light.shape = "DISK"
        light.size = size * scale
        light.energy = energy * size * size * light_scale
        light.color = color
        ob = bpy.data.objects.new(name, light)
        sc.collection.objects.link(ob)
        d = Vector(loc_dir).normalized()
        ob.location = centre + d * size * 2.2
        ob.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()

    area("_key", (0.45, -1.0, 0.8), 95, 1.0, (1.0, 0.90, 0.78))       # warm, high, from front-left
    area("_fill", (1.0, 0.8, 0.3), 12, 2.0, (0.95, 0.95, 1.0))        # soft daylight from front-right
    area("_top", (-0.15, 0.1, 1.0), 30, 1.2, (1.0, 0.82, 0.62))        # under-shelf LED above
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    for attr, val in (("use_shadows", True), ("use_raytracing", True), ("ray_tracing_method", "SCREEN"),
                      ("use_fast_gi", True), ("use_gtao", True),
                      ("shadow_ray_count", 2), ("shadow_step_count", 8)):
        if hasattr(sc.eevee, attr):
            try:
                setattr(sc.eevee, attr, val)
            except Exception:
                pass
    try:
        sc.eevee.ray_tracing_options.resolution_scale = "1"
        sc.eevee.ray_tracing_options.screen_trace_quality = 0.5
    except Exception:
        pass
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
        sc.view_settings.exposure = -0.45
    except Exception:
        pass
    sc.render.resolution_x = sc.render.resolution_y = 1200
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"


def shoot(path, lo, hi, view_dir, lens=70, margin=1.12, samples=64, aim=None):
    """Point a camera along -view_dir at the box lo..hi (fitting it), render to path."""
    sc = bpy.context.scene
    cam = sc.camera
    if cam is None:
        cam = bpy.data.objects.new("_cam", bpy.data.cameras.new("_cam"))
        sc.collection.objects.link(cam)
        sc.camera = cam
    cam.data.lens = lens
    v = Vector(view_dir).normalized()
    cam.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    dg = bpy.context.evaluated_depsgraph_get()
    co, _ = cam.camera_fit_coords(dg, [c for p in corners for c in p])
    centre = (lo + hi) / 2 if aim is None else Vector(aim)
    cam.location = centre + (Vector(co) - (lo + hi) / 2) * margin
    size = (hi - lo).length
    cam.data.clip_start = size * 0.01
    cam.data.clip_end = size * 200
    sc.eevee.taa_render_samples = samples
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


# --------------------------------------------------------------------------- finishing

def finish(name, parts, args, origin=None, sharp_angle=40, views=None, post=None, extras=None, glossy=False):
    """Join, origin at the bottom centre of the footprint (or `origin`), tidy, export, report,
    render. views: list of (suffix, view_dir, lens, margin) -- suffix "" is <name>.png.
    glossy: preview on glossy_stage() (rectangular softboxes to reflect)."""
    if len(parts) == 1:
        ob = bake(parts[0])
        ob.name = ob.data.name = name
    else:
        ob = S.join(name, parts)
    if origin is None:
        lo, hi = S.bbox(ob)
        origin = ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)
    S.set_origin(ob, origin)
    S.tidy(ob, sharp_angle)
    if post:
        post(ob)
    if not ob.data.uv_layers:
        raise RuntimeError(f"{name}: no UVs")
    os.makedirs(args.out, exist_ok=True)
    fbx = os.path.join(args.out, name + ".fbx")
    S.export_fbx(ob, fbx)
    report(ob)
    if not args.no_render:
        render_views(ob, args, views, extras, glossy)
    return ob


def report(ob):
    lo, hi = S.bbox(ob)
    name = ob.name
    print("=" * 60)
    print(f"{name}: materials {[m.name for m in ob.data.materials]}")
    print(f"{name}: triangles {S.tri_count(ob)}  non-manifold edges {non_manifold_edges(ob)}"
          f"  uv layers {[u.name for u in ob.data.uv_layers]}")
    print(f"{name}: bbox cm  X {lo.x*100:.2f}..{hi.x*100:.2f}  Y {lo.y*100:.2f}..{hi.y*100:.2f}"
          f"  Z {lo.z*100:.2f}..{hi.z*100:.2f}")
    d = (hi - lo) * 100
    print(f"{name}: size cm  {d.x:.2f} x {d.y:.2f} x {d.z:.2f}")
    print("=" * 60)


def render_views(ob, args, views=None, extras=None, glossy=False):
    lo, hi = S.bbox(ob)
    (glossy_stage if glossy else stage)(lo, hi)
    if extras:
        extras(ob)
    views = views or [("", (1.0, -0.75, 0.85), 70, 1.15), ("_front", (1.0, 0.0, 0.08), 70, 1.15)]
    for v in views:
        suffix, vd, lens, margin = v[:4]
        box = v[4] if len(v) > 4 else (lo, hi)
        shoot(os.path.join(args.out, ob.name + suffix + ".png"), box[0], box[1], vd, lens=lens,
              margin=margin, samples=args.samples)


# --------------------------------------------------------------------------- thrown ceramics

def thrown_warp(height, seed, amp=0.010, lean=0.0015, ripple=0.00012, pitch=0.010):
    """Hand-thrown irregularity for lathe_uv: a low-order out-of-round that drifts with height,
    a slight lean of the upper part and faint throwing lines on the walls."""
    import random
    rnd = random.Random(seed)
    terms = [(m, rnd.uniform(0, TAU), rnd.uniform(-2.5, 2.5), a)
             for m, a in ((2, amp), (3, amp * 0.55), (5, amp * 0.22))]
    lean_dir = rnd.uniform(0, TAU)
    rph = rnd.uniform(0, TAU)

    def warp(th, r, z):
        t = max(0.0, min(1.0, z / height))
        cx = lean * t * t * math.cos(lean_dir)
        cy = lean * t * t * math.sin(lean_dir)
        if r <= 0:
            return (cx, cy, z)
        mult = 1 + sum(a * math.sin(m * th + ph + tw * t) for m, ph, tw, a in terms)
        body = math.sin(math.pi * min(1.0, max(0.0, (t - 0.04) / 0.92))) ** 0.5   # none at foot or lip
        rr = r * mult + ripple * body * math.sin(TAU * z / pitch + rph + 0.6 * math.sin(th + rph))
        return (rr * math.cos(th) + cx, rr * math.sin(th) + cy, z)
    return warp


def smooth_profile(pts, max_len):
    """Resample a polyline profile through its points with a Catmull-Rom spline, at most
    `max_len` between rings, so a curved wall has no visible kinks in silhouette."""
    out = [pts[0]]
    ext = [pts[0]] + list(pts) + [pts[-1]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = (Vector(ext[j]) for j in (i - 1, i, i + 1, i + 2))
        n = max(1, math.ceil((p2 - p1).length / max_len))
        for k in range(1, n + 1):
            t = k / n
            q = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                       + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)
            out.append((max(0.0, q.x) if pts[0][0] > 0 or i > 1 or k > 0 else 0.0, q.y))
    out[0], out[-1] = pts[0], pts[-1]
    return out


def vase(name, outer_cm, inner_cm, mat, seed, budget=5900, max_segs=96, **warp_kw):
    """A hollow thrown vase: outer profile from the foot centre up over the lip, then the inside
    down to the inner floor, in cm. Wall thickness comes from the two profiles. The outer wall is
    resampled smooth (rings at most 1 cm apart), the inside coarser; the segment count is the most that keeps
    the mesh within `budget` triangles."""
    outer = smooth_profile(outer_cm, 1.0)
    inner = smooth_profile([outer_cm[-1]] + list(inner_cm), 2.5)[1:]
    prof = [(r * CM, z * CM) for r, z in outer + inner]
    bands = len(prof) - 1
    segs = min(max_segs, int(budget / (2 * bands)) // 4 * 4)
    height = max(z for _, z in prof)
    print(f"{name}: {len(prof)} profile rings x {segs} segments")
    return lathe_uv(name, prof, [mat], segs, warp=thrown_warp(height, seed, **warp_kw))


def speckle_material(name, base, speck, roughness, fine=(420.0, 0.70), coarse=(140.0, 0.78)):
    """Glaze with dense fine dark specks and sparser larger ones (iron in the clay), for the preview."""
    m = S.material(name, base, roughness)
    nt = m.node_tree
    b = principled(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    masks = []
    for scale, thr in (fine, coarse):
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = scale
        nz.inputs["Detail"].default_value = 2.0
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = thr
        mr.inputs["From Max"].default_value = thr + 0.02
        nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
        masks.append(mr.outputs["Result"])
    mx = nt.nodes.new("ShaderNodeMath")
    mx.operation = "MAXIMUM"
    nt.links.new(masks[0], mx.inputs[0])
    nt.links.new(masks[1], mx.inputs[1])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (*base, 1)
    mix.inputs[7].default_value = (*speck, 1)
    nt.links.new(mx.outputs[0], mix.inputs["Factor"])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    bump_src = nt.nodes.new("ShaderNodeTexNoise")
    bump_src.inputs["Scale"].default_value = 90.0
    bump_src.inputs["Detail"].default_value = 4.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    nt.links.new(bump_src.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def point_light(name, loc, energy, color=(1.0, 0.62, 0.30), radius=0.004):
    light = bpy.data.lights.new(name, "POINT")
    light.energy = energy
    light.color = color
    light.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    return ob


# --------------------------------------------------------------------------- premium glazed ceramics

def _cr_chain(pts, per_cm=60):
    """Centripetal Catmull-Rom through (r, z) points (cm), densely sampled (no overshoot).
    Returns (dense points, index of each control point in the dense list)."""
    P = [Vector(p) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out, idx = [P[1]], [0]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + max((p1 - p0).length, 1e-6) ** 0.5
        t2 = t1 + max((p2 - p1).length, 1e-6) ** 0.5
        t3 = t2 + max((p3 - p2).length, 1e-6) ** 0.5
        n = max(2, math.ceil((p2 - p1).length * per_cm))
        for k in range(1, n + 1):
            t = t1 + (t2 - t1) * k / n
            a1 = p0 * ((t1 - t) / (t1 - t0)) + p1 * ((t - t0) / (t1 - t0))
            a2 = p1 * ((t2 - t) / (t2 - t1)) + p2 * ((t - t1) / (t2 - t1))
            a3 = p2 * ((t3 - t) / (t3 - t2)) + p3 * ((t - t2) / (t3 - t2))
            b1 = a1 * ((t2 - t) / (t2 - t0)) + a2 * ((t - t0) / (t2 - t0))
            b2 = a2 * ((t3 - t) / (t3 - t1)) + a3 * ((t - t1) / (t3 - t1))
            out.append(b1 * ((t2 - t) / (t2 - t1)) + b2 * ((t - t1) / (t2 - t1)))
        idx.append(len(out) - 1)
    return out, idx


def fillet(a, c, b, r, n=6):
    """Points of a circular fillet of radius r (cm) at corner c between the lines a-c and c-b."""
    a, c, b = Vector(a), Vector(c), Vector(b)
    d0, d1 = (a - c).normalized(), (b - c).normalized()
    half = math.acos(max(-1.0, min(1.0, d0.dot(d1)))) / 2
    if half < 1e-3 or half > math.pi / 2 - 1e-3:
        return [tuple(c)]
    t = r / math.tan(half)
    p0, p1 = c + d0 * t, c + d1 * t
    centre = c + (d0 + d1).normalized() * (r / math.sin(half))
    a0 = math.atan2(p0.y - centre.y, p0.x - centre.x)
    a1 = math.atan2(p1.y - centre.y, p1.x - centre.x)
    da = (a1 - a0 + math.pi) % TAU - math.pi
    return [(centre.x + r * math.cos(a0 + da * k / n), centre.y + r * math.sin(a0 + da * k / n)) for k in range(n + 1)]


def lip_roll(r_out, r_in, z_top, n=10):
    """A rounded lip: a half circle over the top from the outer wall (r_out) to the inner (r_in)."""
    rc, rad = (r_out + r_in) / 2, (r_out - r_in) / 2
    return [(rc + rad * math.cos(math.pi * k / n), z_top - rad + rad * math.sin(math.pi * k / n)) for k in range(n + 1)]


def adaptive(dense, max_len, max_turn_deg, min_len=0.01, coarse=None):
    """Pick points from a dense polyline: a new point whenever the run since the last one is
    longer than max_len or the direction has turned more than max_turn_deg (cm).
    coarse = (first index, max_len, max_turn_deg): looser limits from that index on."""
    out = [dense[0]]
    last_dir = None
    acc = 0.0
    lim = math.radians(max_turn_deg)
    for i in range(1, len(dense)):
        if coarse and i == coarse[0]:
            max_len, lim = coarse[1], math.radians(coarse[2])
        seg = dense[i] - dense[i - 1]
        acc += seg.length
        d = (dense[i] - out[-1])
        if d.length < 1e-9:
            continue
        if last_dir is None:
            last_dir = seg.normalized()
        turn = math.acos(max(-1.0, min(1.0, seg.normalized().dot(last_dir)))) if seg.length > 1e-9 else 0
        if acc >= min_len and (acc >= max_len or turn >= lim or i == len(dense) - 1):
            out.append(dense[i])
            last_dir = seg.normalized()
            acc = 0.0
    if (out[-1] - dense[-1]).length > 1e-9:
        out.append(dense[-1])
    return out


def _cum(pts):
    s = [0.0]
    for p0, p1 in zip(pts, pts[1:]):
        s.append(s[-1] + (p1 - p0).length)
    return s


class Curve:
    """A dense 2D polyline (cm) with arc-length lookup: at(s) -> point, normal(s) -> outward normal
    (to the right of the travel direction, i.e. away from the axis on the outer wall going up)."""

    def __init__(self, dense):
        self.p = dense
        self.s = _cum(dense)
        self.length = self.s[-1]

    def _seg(self, s):
        import bisect
        s = max(0.0, min(self.length, s))
        i = max(1, min(len(self.s) - 1, bisect.bisect_left(self.s, s)))
        return i, s

    def at(self, s):
        i, s = self._seg(s)
        s0, s1 = self.s[i - 1], self.s[i]
        t = 0.0 if s1 <= s0 else (s - s0) / (s1 - s0)
        return self.p[i - 1].lerp(self.p[i], t)

    def tangent(self, s, h=0.02):
        d = self.at(s + h) - self.at(s - h)
        return d.normalized() if d.length > 1e-12 else Vector((0, 1))

    def normal(self, s):
        t = self.tangent(s)
        return Vector((t.y, -t.x))

    def s_at_z(self, z, s_lo=0.0, s_hi=None):
        """First arc length (searching from s_lo) where the curve rises through height z."""
        s_hi = self.length if s_hi is None else s_hi
        for i in range(1, len(self.p)):
            if self.s[i] < s_lo or self.s[i - 1] > s_hi:
                continue
            z0, z1 = self.p[i - 1].y, self.p[i].y
            if (z0 - z) * (z1 - z) <= 0 and z1 != z0:
                return self.s[i - 1] + (self.s[i] - self.s[i - 1]) * (z - z0) / (z1 - z0)
        raise ValueError(f"height {z} not on the curve")


def _arc_of(curve, picks):
    """Arc lengths of points picked (in order) from the curve's own dense list."""
    out, j = [], 0
    for q in picks:
        while j < len(curve.p) and (curve.p[j] - q).length_squared > 1e-18:
            j += 1
        out.append(curve.s[min(j, len(curve.p) - 1)])
    return out


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def glazed_vase(name, under, outer, inner, mats, glaze_z, drips, segs=176, seed=1, pool=None,
                glaze_t=0.035, bead=0.075, wobble=0.0016, lean=0.0007, ripple=0.00003,
                max_len=0.75, max_turn=3.8, inner_depth=4.5):
    """A thrown, glazed vase with an unglazed foot, as one closed shell.

    Profiles are (r, z) control points in cm, joined in order: `under` (the base from the centre
    out over the foot ring to where the body starts: raw clay), `outer` (the body from just above
    the foot up to the start of the lip roll) and `inner` (from the end of the lip roll down the
    inside to the inner floor centre). Each part is a centripetal Catmull-Rom spline, resampled
    adaptively (rings closer where the profile turns), so silhouettes stay smooth up close.

    The glaze: everything above the glaze line is slot 0 (glaze), below it slot 1 (M_ClayFoot).
    The line sits at height `glaze_z` cm and dips into `drips` [(theta deg, length cm, width cm)]
    -- rounded tongues. Above the line the surface stands proud by the glaze thickness, which
    rises from nothing at the line to a soft rolled bead (`bead`, cm) and settles to `glaze_t`;
    the drips carry a heavier bead at their tips. `pool` = (z0, z1, extra cm): extra glaze
    pooled in a band (the shoulder). The ring rows near the line follow it exactly, so the
    material border is a clean curve. A colour attribute "Glaze" records R = glaze build-up
    (bead, drips, pool), G = thin glaze (the lip) and B = cavity (0 at the lip, 1 from 2.5 cm
    down inside the neck), for the material.

    UVs: U = theta x the widest radius (m), V = arc length along the profile (m)."""
    import random
    rnd = random.Random(seed)
    TH = math.radians
    # ---- the profile: one spline through under + outer + inner (lip roll at the start of inner)
    pts = [tuple(p) for p in under] + [tuple(p) for p in outer] + [tuple(p) for p in inner]
    dense, idx = _cr_chain(pts, 80)
    curve = Curve(dense)
    s_under_end = curve.s[idx[len(under) - 1]]
    s_outer_end = curve.s[idx[len(under) + len(outer) - 1]]
    s_line0 = curve.s_at_z(glaze_z, s_under_end)

    # ---- the glaze line as a function of theta (arc length along the profile)
    r_line = curve.at(s_line0).x

    def tongue(length, width):
        """A drip as a depth table over u (cm across): parallel sides, a round tip of radius
        width / 2, and soft concave roots (the raw shape smoothed with a Gaussian)."""
        r = width / 2
        us = [3 * r * (2 * k / 600 - 1) for k in range(601)]
        raw = [(length - r + r * math.sqrt(max(0.0, 1 - (u / r) ** 2))) if abs(u) < r else 0.0 for u in us]
        sig = 0.28 * r
        du = us[1] - us[0]
        kern = [math.exp(-0.5 * (k * du / sig) ** 2) for k in range(-int(3 * sig / du), int(3 * sig / du) + 1)]
        ks = sum(kern)
        h = len(kern) // 2
        sm = [sum(kern[m] * raw[min(600, max(0, i + m - h))] for m in range(len(kern))) / ks for i in range(601)]
        peak = max(sm)
        sm = [v * length / peak for v in sm]                 # keep the full length after smoothing
        return us[0], du, sm

    tables = [(TH(d_th), tongue(length, width)) for d_th, length, width in drips]

    def drip_f(th):
        best = 0.0
        for th0, (u0, du, tab) in tables:
            u = ((th - th0 + math.pi) % TAU - math.pi) * r_line
            x = (u - u0) / du
            if 0 <= x < len(tab) - 1:
                i = int(x)
                best = max(best, tab[i] + (tab[i + 1] - tab[i]) * (x - i))
        return best

    def wav(th):        # a gently wandering line: hand-dipped, not machined
        return 0.08 * math.sin(2 * th + 0.7) + 0.05 * math.sin(3 * th + 2.1) + 0.03 * math.sin(7 * th + 0.3)

    def line_s(th):
        return s_line0 + wav(th) - drip_f(th)

    # ---- theta samples: even, plus extra around each drip
    ths = [TAU * k / segs for k in range(segs)]
    for d_th, length, width in drips:
        half = (width * 1.1) / r_line
        n_extra = 24
        ths += [TH(d_th) + half * (2 * k / n_extra - 1) for k in range(n_extra + 1)]
    ths = sorted({round(t % TAU, 6) for t in ths})
    merged = [ths[0]]
    for t in ths[1:]:
        if t - merged[-1] > 0.0015:
            merged.append(t)
    ths = merged

    # the glaze line sampled per column, for the true distance from a point to the line
    col_u = [t * r_line for t in ths]
    col_e = [line_s(t) for t in ths]
    circ = TAU * r_line

    def edge_distance(th, s, d_up):
        """Distance (cm, in the unrolled surface) from (th, s) to the nearest point of the
        glaze line, searching the columns within d_up across."""
        import bisect
        u = th * r_line
        best = d_up
        k0 = bisect.bisect_left(col_u, u)
        for step in (1, -1):
            k = k0 if step == 1 else k0 - 1
            for _ in range(len(col_u)):
                du = abs(((col_u[k % len(col_u)] - u) + circ / 2) % circ - circ / 2)
                if du > best:
                    break
                best = min(best, math.hypot(du, s - col_e[k % len(col_u)]))
                k += step
        return best

    # ---- rows: fixed arc lengths except a band that follows the glaze line
    # rows: fine outside and over the lip, coarse once the inside is past the neck (never seen)
    height = max(p.y for p in dense)
    i_out = idx[len(under) + len(outer) - 1]
    i_deep = next(i for i in range(i_out, len(dense)) if dense[i].y < height - inner_depth)
    sb = _arc_of(curve, adaptive(dense, max_len, max_turn, coarse=(i_deep, 1.5, 9.0)))
    band_lo = s_under_end + 0.05                        # band from just above the foot ...
    band_hi = s_line0 + 1.6                             # ... to 1.6 cm above the glaze line
    fixed_lo = [s for s in sb if s < band_lo - 1e-6] + [band_lo]
    fixed_hi = [band_hi] + [s for s in sb if s > band_hi + 1e-6]
    rel = [-0.30, -0.14, -0.05, 0.0, 0.025, 0.06, 0.11, 0.18, 0.28, 0.42, 0.62, 0.9, 1.25]
    n_below = 7

    def rows_for(th):
        e = line_s(th)
        lo_edge = e + rel[0]
        assert lo_edge > band_lo + 0.08, f"{name}: a drip runs into the foot"
        below = [band_lo + (lo_edge - band_lo) * k / n_below for k in range(1, n_below)]
        edge = [e + d for d in rel]
        top = edge[-1]
        above = [top + (band_hi - top) * k / 4 for k in range(1, 4)]
        return fixed_lo + below + edge + above + fixed_hi

    def thickness(th, s):
        """(glaze thickness cm, build-up 0..1) at profile arc length s on the outer wall."""
        if s <= s_under_end:
            return 0.0, 0.0
        d = s - line_s(th)
        if d <= 0:
            return 0.0, 0.0
        d = edge_distance(th, s, d)                    # distance across the line, not just up
        if s > s_outer_end:
            return glaze_t, 0.0
        df = drip_f(th)
        b = bead * (1.0 + 1.3 * min(1.0, df / 0.5))
        rise = math.sqrt(max(0.0, 1 - (1 - min(d, 0.06) / 0.06) ** 2))      # rolled edge
        bump = math.exp(-((d - 0.10) / 0.16) ** 2)
        t = rise * (glaze_t + (b - glaze_t) * bump * (1 if d > 0.10 else 1.0))
        build = bump * (0.6 + 0.4 * min(1.0, df / 0.4))
        if pool:
            z = curve.at(s).y
            pz0, pz1, extra = pool
            w = smoothstep(pz0, (pz0 + pz1) / 2, z) * (1 - smoothstep((pz0 + pz1) / 2, pz1, z))
            t += extra * w
            build = max(build, w * 0.8)
        # no taper at the very top of the outer wall: the lip carries glaze_t
        return t, build

    # ---- hand-thrown warp (tiny: a premium piece, but not a machined one)
    terms = [(m, rnd.uniform(0, TAU), rnd.uniform(-2.0, 2.0), a)
             for m, a in ((2, wobble), (3, wobble * 0.5), (5, wobble * 0.15))]
    lean_dir = rnd.uniform(0, TAU)
    rph = rnd.uniform(0, TAU)

    def place(th, r, z):
        t = max(0.0, min(1.0, z / height))
        cx, cy = lean * CM * 100 * t * t * math.cos(lean_dir), lean * CM * 100 * t * t * math.sin(lean_dir)
        body = math.sin(math.pi * min(1.0, max(0.0, (t - 0.06) / 0.88))) ** 0.5
        mult = 1 + body * sum(a * math.sin(m * th + ph + tw * t) for m, ph, tw, a in terms)
        rr = r * mult + body * ripple * 100 * math.sin(TAU * z / 1.15 + rph + 0.6 * math.sin(th + rph))
        return Vector((rr * math.cos(th) * CM + cx, rr * math.sin(th) * CM + cy, z * CM))

    r_ref = max(p.x for p in dense) * CM
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    rows_all = [rows_for(th) for th in ths]
    n_rows = len(rows_all[0])
    assert all(len(r) == n_rows for r in rows_all)
    grid, info = [], []
    pole0 = pole1 = None
    for j in range(n_rows):
        ring, ring_info = [], []
        for i, th in enumerate(ths):
            s = rows_all[i][j]
            p = curve.at(s)
            t, build = thickness(th, s) if s < s_outer_end + 1e-9 else (glaze_t, 0.0)
            if s >= s_outer_end:
                t, build = glaze_t, 0.0
            if t:
                p = p + curve.normal(s) * t
            ring_info.append((s, build, p.x))
            if p.x <= 1e-6:
                ring.append(None)
                continue
            ring.append(bm.verts.new(place(th, p.x, p.y)))
        grid.append(ring)
        info.append(ring_info)
    # poles: first and last rows sit on the axis
    first = 0 if grid[0][0] is not None else 1
    last = n_rows - 1 if grid[-1][0] is not None else n_rows - 2
    if first == 1:
        pole0 = bm.verts.new(place(0, 0, curve.at(rows_all[0][0]).y))
    if last == n_rows - 2:
        pole1 = bm.verts.new(place(0, 0, curve.at(rows_all[0][-1]).y))
    n = len(ths)
    glaze_line = [line_s(th) for th in ths]

    def slot_of(i, j):
        s_mid = (rows_all[i][j] + rows_all[i][j + 1]) / 2
        s_mid2 = (rows_all[(i + 1) % n][j] + rows_all[(i + 1) % n][j + 1]) / 2
        lim = (glaze_line[i] + glaze_line[(i + 1) % n]) / 2
        return 0 if (s_mid + s_mid2) / 2 > lim else 1

    for j in range(first, last):
        for i in range(n):
            i2 = (i + 1) % n
            th0, th1 = ths[i], ths[i2] if i2 else TAU
            vs = (grid[j][i], grid[j][i2], grid[j + 1][i2], grid[j + 1][i])
            f = bm.faces.new(vs)
            f.material_index = slot_of(i, j)
            uvs = ((th0 * r_ref, info[j][i][0] * CM), (th1 * r_ref, info[j][i2][0] * CM),
                   (th1 * r_ref, info[j + 1][i2][0] * CM), (th0 * r_ref, info[j + 1][i][0] * CM))
            for loop, uv in zip(f.loops, uvs):
                loop[uvl].uv = uv
    for pole, j, flip in ((pole0, first, False), (pole1, last, True)):
        if pole is None:
            continue
        for i in range(n):
            i2 = (i + 1) % n
            th0, th1 = ths[i], ths[i2] if i2 else TAU
            tri = (grid[j][i2], grid[j][i], pole) if not flip else (grid[j][i], grid[j][i2], pole)
            f = bm.faces.new(tri)
            f.material_index = 1 if not flip else 0
            s_ring, s_pole = info[j][i][0] * CM, rows_all[0][0 if not flip else -1] * CM
            uv_t = {grid[j][i]: (th0 * r_ref, s_ring), grid[j][i2]: (th1 * r_ref, s_ring),
                    pole: ((th0 + th1) / 2 * r_ref, s_pole)}
            for loop in f.loops:
                loop[uvl].uv = uv_t[loop.vert]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.index_update()
    vinfo = {}
    for j in range(n_rows):
        for i in range(n):
            if grid[j][i] is not None:
                vinfo[grid[j][i].index] = (j, i)
    ob = obj(bm, name, mats)
    # colour attribute: R build-up, G thin glaze (the lip and the very top of the outer wall)
    me = ob.data
    ca = me.color_attributes.new("Glaze", "BYTE_COLOR", "CORNER")
    lip_mid = s_outer_end + 0.28                 # just past the top of the lip roll, outside
    lip_in = s_outer_end + 0.75                  # the lip roll's inner end
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            if vi not in vinfo:
                continue
            j, i = vinfo[vi]
            s, build, _r = info[j][i]
            thin = 0.6 * math.exp(-((s - lip_mid) / 0.13) ** 2)          # the glaze runs thin over the lip
            cavity = smoothstep(lip_in + 0.1, lip_in + 2.0, s)               # down inside the neck
            ca.data[li].color = (min(1.0, build), thin, cavity, 1.0)
    print(f"{name}: {n_rows} rows x {n} columns, glaze line at s={s_line0:.2f} cm")
    return ob


def softbox(name, centre, aim, w, h, energy, color=(1.0, 0.96, 0.9)):
    """A rectangular area light (a softbox: reads as a soft rectangle in glossy highlights)."""
    light = bpy.data.lights.new(name, "AREA")
    light.shape = "RECTANGLE"
    light.size, light.size_y = w, h
    light.energy = energy
    light.color = color
    ob = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = centre
    d = (Vector(aim) - Vector(centre)).normalized()
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def glossy_stage(lo, hi, light_scale=0.75, box_side=1.0, wall_gap=None):
    """stage() with rectangular softboxes instead of disks (crisp rectangular highlights) plus a
    tall softbox at the front-right, and finer ray-traced reflections, for glazed and polished
    props."""
    stage(lo, hi, wall_gap=wall_gap, light_scale=light_scale)
    for ob in bpy.context.scene.objects:            # softboxes, not disks: rectangular highlights
        if ob.type == "LIGHT" and ob.data.type == "AREA":
            ob.data.shape = "RECTANGLE"
            ob.data.size_y = ob.data.size * 1.4
    size = max((hi - lo).length, 0.05)
    centre = (lo + hi) / 2
    softbox("_softbox", centre + Vector((0.9, 0.75 * box_side, 0.55)).normalized() * size * 2.6, centre,
            size * 0.55, size * 1.1, 60 * size * size * light_scale)
    sc = bpy.context.scene
    try:
        sc.eevee.use_raytracing = True
        sc.eevee.ray_tracing_options.resolution_scale = "1"
        sc.eevee.ray_tracing_options.screen_trace_quality = 0.75
        sc.eevee.ray_tracing_options.use_denoise = True
    except Exception:
        pass


def rounded(poly, radii, n=6):
    """A polyline (cm) with each interior corner replaced by a circular fillet of radii[i - 1]."""
    out = [tuple(poly[0])]
    for i in range(1, len(poly) - 1):
        out += fillet(poly[i - 1], poly[i], poly[i + 1], radii[i - 1], n)
    out.append(tuple(poly[-1]))
    return out


def foot_ring(recess_z, r_in, r_out, foot_h, ledge, body_start, radii=(0.12, 0.08, 0.07, 0.04, 0.06)):
    """The underside and trimmed foot of a thrown pot, from the base centre out (cm): a shallow
    recessed base, a slanted inner foot wall, a flat foot ring (r_in..r_out) standing on z = 0, a
    near-vertical outer foot wall `foot_h` high, a small trimmed ledge `ledge` wide and on to the
    first body point. Corners are filleted: crisp, but not razor sharp."""
    poly = [(0.0, recess_z + 0.01), (r_in * 0.55, recess_z + 0.005), (r_in - 0.10, recess_z), (r_in, 0.0),
            (r_out, 0.0), (r_out + 0.02, foot_h), (r_out + 0.02 + ledge, foot_h + 0.06), body_start]
    return rounded(poly, (1e-4,) + tuple(radii))[:-1]


def glaze_material(name, color, roughness, thin=None, pooled=None, subsurface=0.0, orange_peel=0.006):
    """Glossy glaze for the preview. Reads the vase's "Glaze" colour attribute: R (build-up:
    bead, drips, pooling) blends towards `pooled`, G (thin glaze over the lip) towards `thin`.
    A faint orange-peel bump keeps the reflections from looking machined."""
    m = S.material(name, color, roughness, specular=0.5)
    nt = m.node_tree
    b = principled(m)
    set_input(b, "IOR", 1.52)
    if subsurface:
        set_input(b, ["Subsurface Weight", "Subsurface"], subsurface)
        set_input(b, "Subsurface Radius", (0.002, 0.0015, 0.001))
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Glaze"
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(attr.outputs["Color"], sep.inputs["Color"])
    col = None
    for ch, target in (("Red", pooled), ("Green", thin)):
        if target is None:
            continue
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(sep.outputs[ch], mix.inputs["Factor"])
        if col is None:
            mix.inputs[6].default_value = (*color, 1)
        else:
            nt.links.new(col, mix.inputs[6])
        mix.inputs[7].default_value = (*target, 1)
        col = mix.outputs[2]
    if col is not None:
        nt.links.new(col, b.inputs["Base Color"])
    cavity_darken(m, sep.outputs["Blue"])
    if orange_peel:
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 160.0
        nz.inputs["Detail"].default_value = 2.0
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = orange_peel
        nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def cavity_darken(m, cavity, amount=0.9):
    """Darken the base colour down inside the neck (Eevee's probes light the inside of a narrow
    neck as if it were open; in Unreal, Lumen does this by itself)."""
    nt = m.node_tree
    b = principled(m)
    sock = b.inputs["Base Color"]
    src = sock.links[0].from_socket if sock.links else None
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY_ADD"
    nt.links.new(cavity, k.inputs[0])
    k.inputs[1].default_value = -amount
    k.inputs[2].default_value = 1.0
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    if src is not None:
        nt.links.new(src, mul.inputs[6])
    else:
        mul.inputs[6].default_value = tuple(sock.default_value)
    nt.links.new(k.outputs[0], mul.inputs[7])
    nt.links.new(mul.outputs[2], sock)
    spec = nt.nodes.new("ShaderNodeMath")              # and no bright reflections in there
    spec.operation = "MULTIPLY_ADD"
    nt.links.new(cavity, spec.inputs[0])
    spec.inputs[1].default_value = -0.45
    spec.inputs[2].default_value = 0.5
    for key in ("Specular IOR Level", "Specular"):
        if key in b.inputs:
            nt.links.new(spec.outputs[0], b.inputs[key])
            break


def clay_foot_material(name="M_ClayFoot"):
    """Raw buff stoneware: matte, a fine sandy grain and sparse iron specks."""
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    base = (0.50, 0.375, 0.24)
    m = S.material(name, base, 0.86)
    dot_speckle(m, base, (0.20, 0.12, 0.065), layers=((900.0, 0.14, 0.6), (260.0, 0.10, 0.9)))
    nt = m.node_tree
    nz = nt.nodes.new("ShaderNodeTexNoise")             # fine sandy tooth
    nz.inputs["Scale"].default_value = 1400.0
    nz.inputs["Detail"].default_value = 2.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.0002
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], principled(m).inputs["Normal"])
    return m


VASE_VIEWS = [
    ("", (1.0, 0.75, 0.85), 70, 1.15),
    ("_front", (1.0, 0.0, 0.08), 70, 1.15),
]


def dot_speckle(m, base, speck, layers=((700.0, 0.16, 0.55), (220.0, 0.12, 0.86))):
    """Replace a material's base colour by round iron specks (Voronoi dots): each layer is
    (scale, dot radius in cells, share of cells left empty). Object-space, so it reads at scale."""
    nt = m.node_tree
    b = principled(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    acc = None
    for scale, radius, empty in layers:
        vo = nt.nodes.new("ShaderNodeTexVoronoi")
        vo.inputs["Scale"].default_value = scale
        set_input(vo, "Randomness", 0.9)
        nt.links.new(tc.outputs["Object"], vo.inputs["Vector"])
        size = nt.nodes.new("ShaderNodeMapRange")          # per-cell dot size: some tiny, some full
        size.inputs["To Min"].default_value = radius * 0.35
        size.inputs["To Max"].default_value = radius
        sepc = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(vo.outputs["Color"], sepc.inputs["Color"])
        nt.links.new(sepc.outputs["Green"], size.inputs["Value"])
        inside = nt.nodes.new("ShaderNodeMath")
        inside.operation = "LESS_THAN"
        nt.links.new(vo.outputs["Distance"], inside.inputs[0])
        nt.links.new(size.outputs["Result"], inside.inputs[1])
        keep = nt.nodes.new("ShaderNodeMath")
        keep.operation = "GREATER_THAN"
        nt.links.new(sepc.outputs["Red"], keep.inputs[0])
        keep.inputs[1].default_value = empty
        dot = nt.nodes.new("ShaderNodeMath")
        dot.operation = "MULTIPLY"
        nt.links.new(inside.outputs[0], dot.inputs[0])
        nt.links.new(keep.outputs[0], dot.inputs[1])
        if acc is None:
            acc = dot.outputs[0]
        else:
            mx = nt.nodes.new("ShaderNodeMath")
            mx.operation = "MAXIMUM"
            nt.links.new(acc, mx.inputs[0])
            nt.links.new(dot.outputs[0], mx.inputs[1])
            acc = mx.outputs[0]
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(acc, mix.inputs["Factor"])
    mix.inputs[6].default_value = (*base, 1)
    mix.inputs[7].default_value = (*speck, 1)
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    return mix.outputs[2]
