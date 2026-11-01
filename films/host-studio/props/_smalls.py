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

def finish(name, parts, args, origin=None, sharp_angle=40, views=None, post=None, extras=None):
    """Join, origin at the bottom centre of the footprint (or `origin`), tidy, export, report,
    render. views: list of (suffix, view_dir, lens, margin) -- suffix "" is <name>.png."""
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
        render_views(ob, args, views, extras)
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


def render_views(ob, args, views=None, extras=None):
    lo, hi = S.bbox(ob)
    stage(lo, hi)
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
