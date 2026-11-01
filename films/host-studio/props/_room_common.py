"""Helpers shared by the room scripts (room_shell, window, curtains, rug): the room's dimensions,
world-scale UVs, the preview materials and the interior renders lit by a sun through the window.

Everything is in Blender coordinates (metres). The studio's Y is mirrored by the FBX import, so
Blender Y = -(studio Y): the window, at studio y = +130..+280, sits at Blender y = -2.80..-1.30.
"""
import math
import os

import bpy
import bmesh
from mathutils import Vector

import _studio as S

# ------------------------------------------------------------------ the room (interior faces)
X_BACK = -2.60        # back wall (the window wall), interior face
X_FRONT = 4.20        # front wall, behind the camera
Y_SIDE = 3.30         # side walls at y = +-3.30
Z_CEIL = 3.00
WALL = 0.15           # wall, floor and ceiling thickness, all outside the interior

WIN_Y0, WIN_Y1 = -2.80, -1.30   # window opening (Blender y)
WIN_Z1 = 2.85                   # opening from the floor to 2.85
PANEL_Y0, PANEL_Y1 = -1.10, 0.60  # the slat panel on the back wall: no baseboard here


def ensure_uv(ob, name="UVMap"):
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name=name)
    return me.uv_layers.active


def box_uv(ob, only_mats=None, scale=1.0):
    """World-scale box projection, per face by its dominant normal axis (1 UV = 1 m / scale).

    Faces whose normal is mostly Z get (x, y); mostly X get (y, z); mostly Y get (x, z).
    `only_mats` limits it to faces using those material names."""
    me = ob.data
    uv = ensure_uv(ob)
    mats = [m.name if m else "" for m in me.materials]
    mw = ob.matrix_world
    for poly in me.polygons:
        if only_mats is not None and mats[poly.material_index] not in only_mats:
            continue
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            co = mw @ me.vertices[me.loops[li].vertex_index].co
            if ax == 2:
                u, v = co.x, co.y
            elif ax == 0:
                u, v = co.y, co.z
            else:
                u, v = co.x, co.z
            uv.data[li].uv = (u * scale, v * scale)


def uv_from_attr(bm, uvs):
    """Set the UVs of a bmesh from a dict {vert index: (u, v)} (per-vertex, no seams)."""
    layer = bm.loops.layers.uv.verify()
    for f in bm.faces:
        for lp in f.loops:
            lp[layer].uv = uvs[lp.vert.index]


# ------------------------------------------------------------------ preview materials

def _nodes(m):
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return nt, out


def preview_glass(m):
    """Clear glass that lets shadow rays through (no caustics needed), with a faint reflection."""
    nt, out = _nodes(m)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = (0.94, 0.97, 0.96, 1)
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.02
    fr = nt.nodes.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = 1.5
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fr.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(gl.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    try:
        m.surface_render_method = "BLENDED"
    except Exception:
        pass


def preview_sheer(m, color=(0.86, 0.80, 0.70), opacity=0.74, weave=True):
    """Sheer linen: part see-through, part diffuse, part translucent; a fine weave from the UVs."""
    nt, out = _nodes(m)
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (*color, 1)
    trl = nt.nodes.new("ShaderNodeBsdfTranslucent")
    trl.inputs["Color"].default_value = (color[0], color[1] * 0.97, color[2] * 0.9, 1)
    cloth = nt.nodes.new("ShaderNodeMixShader")
    cloth.inputs[0].default_value = 0.6
    nt.links.new(diff.outputs[0], cloth.inputs[1])
    nt.links.new(trl.outputs[0], cloth.inputs[2])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    if weave:
        # slubby linen: threads along U and V (1 UV = 1 m), opacity varies a little
        tc = nt.nodes.new("ShaderNodeTexCoord")
        wu = nt.nodes.new("ShaderNodeTexWave")
        wu.wave_type = "BANDS"
        wu.bands_direction = "X"
        wu.inputs["Scale"].default_value = 140.0
        wu.inputs["Distortion"].default_value = 2.0
        wu.inputs["Detail"].default_value = 2.0
        wv = nt.nodes.new("ShaderNodeTexWave")
        wv.wave_type = "BANDS"
        wv.bands_direction = "Y"
        wv.inputs["Scale"].default_value = 140.0
        wv.inputs["Distortion"].default_value = 2.0
        nt.links.new(tc.outputs["UV"], wu.inputs["Vector"])
        nt.links.new(tc.outputs["UV"], wv.inputs["Vector"])
        mx = nt.nodes.new("ShaderNodeMath")
        mx.operation = "MAXIMUM"
        nt.links.new(wu.outputs["Fac"], mx.inputs[0])
        nt.links.new(wv.outputs["Fac"], mx.inputs[1])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = opacity - 0.12
        mr.inputs["To Max"].default_value = opacity + 0.10
        nt.links.new(mx.outputs[0], mr.inputs["Value"])
        nt.links.new(mr.outputs[0], mix.inputs[0])
    else:
        mix.inputs[0].default_value = opacity
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(cloth.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    try:
        m.surface_render_method = "DITHERED"
        m.use_backface_culling = False
    except Exception:
        pass


def preview_planks(m, color=(0.50, 0.33, 0.20), plank_len=1.8, plank_w=0.19):
    """Oak planks from the UVs (U along the boards) so the floor's UV direction and scale show."""
    nt, out = _nodes(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.37
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.0015
    br.inputs["Brick Width"].default_value = plank_len
    br.inputs["Row Height"].default_value = plank_w
    br.inputs["Color1"].default_value = (*color, 1)
    br.inputs["Color2"].default_value = (color[0] * 0.82, color[1] * 0.80, color[2] * 0.78, 1)
    br.inputs["Mortar"].default_value = (0.08, 0.05, 0.03, 1)
    nt.links.new(tc.outputs["UV"], br.inputs["Vector"])
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.42
    nt.links.new(br.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])


def preview_wool(m, color=(0.78, 0.71, 0.60)):
    """Cream wool with a fine loop pile from the UVs."""
    nt, out = _nodes(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 260.0
    nz.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["UV"], nz.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = 0.78
    mr.inputs["To Max"].default_value = 1.08
    nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    mul.inputs["A"].default_value = (*color, 1)
    nt.links.new(mr.outputs[0], mul.inputs["B"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.002
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.95
    for k in ("Sheen Weight", "Sheen"):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = 0.6
            break
    nt.links.new(mul.outputs["Result"], bsdf.inputs["Base Color"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])


# Base colours by slot, so every script and the combo agree.
SLOTS = {
    "M_Wall": ((0.74, 0.64, 0.52), 0.85),       # warm limewash plaster
    "M_Ceiling": ((0.80, 0.74, 0.65), 0.9),
    "M_Floor": ((0.50, 0.33, 0.20), 0.42),      # oiled oak, warm
    "M_Baseboard": ((0.45, 0.29, 0.17), 0.5),   # oak, a shade darker than the floor
    "M_WinFrame": ((0.80, 0.76, 0.68), 0.38),   # warm-white satin paint
    "M_Glass": ((0.9, 0.95, 0.94), 0.02),
    "M_Sheer": ((0.86, 0.80, 0.70), 0.9),
    "M_Rod": ((0.025, 0.024, 0.023), 0.45),     # matte black powder-coated steel
    "M_Rug": ((0.78, 0.71, 0.60), 0.95),
}


def slot(name):
    col, rough = SLOTS[name]
    metal = 0.6 if name == "M_Rod" else 0.0
    return S.material(name, col, rough, metallic=metal)


def dress(mat_name, m):
    """Give a slot its preview look (the FBX keeps only the name and base colour)."""
    base = mat_name.split(".")[0]
    if base == "M_Glass":
        preview_glass(m)
    elif base == "M_Sheer":
        preview_sheer(m)
    elif base == "M_Floor":
        preview_planks(m)
    elif base == "M_Rug":
        preview_wool(m)


# ------------------------------------------------------------------ renders

def clear_preview_rig():
    for ob in list(bpy.data.objects):
        if ob.name.startswith("_"):
            bpy.data.objects.remove(ob, do_unlink=True)


def prop_previews(ob, out, name, three_q, front, samples=64, lens=60, floor=True, exposure=0.0):
    """<name>.png from `three_q` and <name>_front.png from `front`, via _studio.render_preview (Eevee)."""
    bpy.context.scene.view_settings.exposure = exposure
    S.render_preview(ob, os.path.join(out, name + ".png"), three_q, samples, lens=lens, floor=floor)
    clear_preview_rig()
    S.render_preview(ob, os.path.join(out, name + "_front.png"), front, samples, lens=lens, floor=floor)
    clear_preview_rig()


def use_cycles(samples=128):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev in ("METAL", "OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = dev
            prefs.get_devices()
            if any(d.type == dev for d in prefs.devices):
                for d in prefs.devices:
                    d.use = True
                sc.cycles.device = "GPU"
                break
        except Exception:
            continue
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    sc.cycles.diffuse_bounces = 4
    sc.cycles.transparent_max_bounces = 48
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False


def sun_and_sky(elev_deg=35.0, azim_deg=22.0, strength=5.5, sky=0.9):
    """A sun outside the window shining into the room (towards +X, down `elev_deg`, turned
    `azim_deg` towards +Y) and a pale sky. The room is closed, so both reach in only through
    the window."""
    sc = bpy.context.scene
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.55, 0.68, 0.85, 1)
    bg.inputs["Strength"].default_value = sky
    e, a = math.radians(elev_deg), math.radians(azim_deg)
    d = Vector((math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), -math.sin(e)))
    light = bpy.data.lights.new("_sun", "SUN")
    light.energy = strength
    light.angle = math.radians(0.8)
    light.color = (1.0, 0.86, 0.68)
    sun = bpy.data.objects.new("_sun", light)
    sc.collection.objects.link(sun)
    sun.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    # a ground outside, so the sky bounce below the horizon is not blue
    g = bmesh.new()
    bmesh.ops.create_grid(g, x_segments=1, y_segments=1, size=30,
                          matrix=__import__("mathutils").Matrix.Translation((-20, 0, -0.16)))
    S.obj_from_bm(g, "_ground", S.material("_Ground", (0.22, 0.25, 0.18), 0.9))


def camera(loc, look_at, lens=24.0):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("_cam")
    cd.lens = lens
    cd.clip_start = 0.02
    cd.clip_end = 100
    cam = bpy.data.objects.new("_cam", cd)
    sc.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(look_at) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    return cam


def render(path, res=1200, exposure=0.0):
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.view_settings.exposure = exposure
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def closeup(ob, path, loc, look, lens, samples=64, exposure=0.0):
    """A close look with _studio's preview lights: set the rig up, then move the camera."""
    bpy.context.scene.view_settings.exposure = exposure
    S.render_preview(ob, path, (1.0, 0.6, 0.5), samples)
    cam = bpy.context.scene.camera
    cam.data.lens = lens
    cam.data.clip_start = 0.005
    cam.location = loc
    cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.render.render(write_still=True)
    clear_preview_rig()
