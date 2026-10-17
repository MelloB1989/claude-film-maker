"""The SAU_EDITZ outro's look in Blender/Cycles: materials, world, lights, god-ray volume, rings, sparks, camera rig and
the compositor (bloom, vignette, flashes, pixel dissolve). Every animated value is sampled from `outro_schedule` at
each comp frame, so the keyframes are linear between whole frames and Cycles' motion blur (301 deg) sees the true curve.

Units: 1 BU = 100 AE px; the camera is at y = -20 looking along +y, letters face it (-y), z is up.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Euler, Vector

from . import outro_schedule as sch

RED = (0.86, 0.06, 0.09)
NAVY = (0.05, 0.12, 0.42)
BEVEL_C = (1.0, 0.30, 0.30)


# --- helpers ----------------------------------------------------------------------------------------------------------
def key(obj_or_sock, path, frame, value=None, index=-1):
    """Insert one keyframe; objects take `path` as a data path, sockets animate their default_value."""
    if value is not None:
        setattr(obj_or_sock, path, value)
    obj_or_sock.keyframe_insert(path, index=index, frame=frame)


def linearize(id_block):
    ad = id_block.animation_data
    if not ad or not ad.action:
        return
    for fc in all_fcurves(ad.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def all_fcurves(action):
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


def _node(nt, kind, x, y, **kw):
    n = nt.nodes.new(kind)
    n.location = (x, y)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


# --- materials --------------------------------------------------------------------------------------------------------
def _principled(nt, **inputs):
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    for k, v in inputs.items():
        if k in p.inputs:
            p.inputs[k].default_value = v
    return p


def _fade_wrap(nt, shader):
    """Surface -> (Transparent, shader) mixed by the object's alpha (object colour A): the 8 f fade-in of each letter."""
    info = nt.nodes.new("ShaderNodeObjectInfo")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(info.outputs["Alpha"], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(shader, mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])


def face_material():
    """Glossy red with a clear-coat, a faint black web pattern (the Spider-Man face of the AE build, ref 06 §5)."""
    m = bpy.data.materials.new("sau_face")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    p = _principled(nt, **{"Metallic": 0.35, "Roughness": 0.26, "Coat Weight": 1.0, "Coat Roughness": 0.04,
                           "Specular IOR Level": 0.7})
    # web: spokes from the glyph's own centre (object coords) darkening the red
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    ang = nt.nodes.new("ShaderNodeMath"); ang.operation = "ARCTAN2"
    nt.links.new(sep.outputs["Z"], ang.inputs[0]); nt.links.new(sep.outputs["X"], ang.inputs[1])
    spokes = nt.nodes.new("ShaderNodeMath"); spokes.operation = "MULTIPLY"; spokes.inputs[1].default_value = 4.0   # |sin(4 a)| = 0 on 8 spokes
    nt.links.new(ang.outputs[0], spokes.inputs[0])
    sp_s = nt.nodes.new("ShaderNodeMath"); sp_s.operation = "SINE"; nt.links.new(spokes.outputs[0], sp_s.inputs[0])
    sp_a = nt.nodes.new("ShaderNodeMath"); sp_a.operation = "ABSOLUTE"; nt.links.new(sp_s.outputs[0], sp_a.inputs[0])
    # spoke line = 1 - smoothstep(0.0, 0.05, |sin|)
    sp_m = nt.nodes.new("ShaderNodeMapRange"); sp_m.inputs["From Min"].default_value = 0.0; sp_m.inputs["From Max"].default_value = 0.06
    sp_m.inputs["To Min"].default_value = 1.0; sp_m.inputs["To Max"].default_value = 0.0; sp_m.clamp = True
    nt.links.new(sp_a.outputs[0], sp_m.inputs["Value"])
    vec = nt.nodes.new("ShaderNodeVectorMath"); vec.operation = "LENGTH"
    xz = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sep.outputs["X"], xz.inputs["X"]); nt.links.new(sep.outputs["Z"], xz.inputs["Z"])
    nt.links.new(xz.outputs[0], vec.inputs[0])
    rs = nt.nodes.new("ShaderNodeMath"); rs.operation = "MULTIPLY"; rs.inputs[1].default_value = 7.0
    nt.links.new(vec.outputs["Value"], rs.inputs[0])
    rf = nt.nodes.new("ShaderNodeMath"); rf.operation = "FRACT"; nt.links.new(rs.outputs[0], rf.inputs[0])
    rm = nt.nodes.new("ShaderNodeMapRange"); rm.inputs["From Min"].default_value = 0.0; rm.inputs["From Max"].default_value = 0.07
    rm.inputs["To Min"].default_value = 1.0; rm.inputs["To Max"].default_value = 0.0; rm.clamp = True
    nt.links.new(rf.outputs[0], rm.inputs["Value"])
    web = nt.nodes.new("ShaderNodeMath"); web.operation = "MAXIMUM"
    nt.links.new(sp_m.outputs[0], web.inputs[0]); nt.links.new(rm.outputs[0], web.inputs[1])
    mixc = nt.nodes.new("ShaderNodeMix"); mixc.data_type = "RGBA"
    mixc.inputs["A"].default_value = (*RED, 1)
    mixc.inputs["B"].default_value = (0.25, 0.005, 0.012, 1)
    f = nt.nodes.new("ShaderNodeMath"); f.operation = "MULTIPLY"; f.inputs[1].default_value = 0.55
    nt.links.new(web.outputs[0], f.inputs[0]); nt.links.new(f.outputs[0], mixc.inputs["Factor"])
    nt.links.new(mixc.outputs["Result"], p.inputs["Base Color"])
    _fade_wrap(nt, p.outputs[0])
    return m


def bevel_material():
    m = bpy.data.materials.new("sau_bevel")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    p = _principled(nt, **{"Base Color": (*BEVEL_C, 1), "Metallic": 0.6, "Roughness": 0.16, "Coat Weight": 0.6,
                           "Specular IOR Level": 1.0, "Emission Color": (1.0, 0.2, 0.2, 1), "Emission Strength": 0.25})
    _fade_wrap(nt, p.outputs[0])
    return m


def side_material():
    m = bpy.data.materials.new("sau_side")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    p = _principled(nt, **{"Base Color": (*NAVY, 1), "Metallic": 0.9, "Roughness": 0.32, "Anisotropic": 0.4,
                           "Specular IOR Level": 0.8})
    _fade_wrap(nt, p.outputs[0])
    return m


def glow_material(name, colour, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*colour, 1)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


# --- world, lights, volume ---------------------------------------------------------------------------------------------
def build_world():
    """Near-black navy sky with a faint red haze at the horizon (ref 06 §6, kept subtle: the film cuts in from black)."""
    w = bpy.data.worlds.new("outro_world")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.018, 0.003, 0.008, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.0015, 0.0025, 0.009, 1)
    nt.links.new(sep.outputs["Z"], ramp.inputs[0])
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(ramp.outputs[0], bg.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs[0], out.inputs[0])
    bpy.context.scene.world = w
    return w


def _area(name, loc, size, power, colour, target=(0, 0, 0), shape="RECTANGLE", camera_visible=False):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = shape
    ld.size = size[0]
    if shape == "RECTANGLE":
        ld.size_y = size[1]
    ld.energy = power
    ld.color = colour
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    aim(ob, target)
    ob.visible_camera = camera_visible
    return ob


def aim(ob, target):
    d = Vector(target) - Vector(ob.location)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def build_lights(n, f0):
    """KEY warm, RIM blue, TOP cool (ref 06 §3 lights, AE px / 100), softbox strips for the glossy reflections, two
    back spots that carve the god rays, and the moving SWEEP."""
    lights = {}
    lights["key"] = _area("KEY warm", (-9, -14, 8), (7, 4), 3000, (1.0, 0.95, 0.9))
    lights["rim"] = _area("RIM blue", (15, 5, -3), (5, 14), 4500, (0.35, 0.55, 1.0))
    lights["top"] = _area("TOP cool", (2, -3, 15), (14, 4), 4000, (0.7, 0.8, 1.0))
    lights["strip_l"] = _area("STRIP left", (-12, -9, 1), (1.2, 12), 1200, (1, 1, 1))
    lights["strip_r"] = _area("STRIP right", (11, -11, 1), (1.2, 12), 900, (1, 0.9, 0.85))
    # back spots: shine at the camera from behind the word through the volume, the word blocks them = god rays
    for i, (x, z) in enumerate(((-3.2, 2.0), (3.6, 1.2))):
        sd = bpy.data.lights.new(f"RAY {i}", "SPOT")
        sd.energy = 2500
        sd.spot_size = math.radians(48)
        sd.spot_blend = 0.9
        sd.shadow_soft_size = 0.15
        sd.color = (1.0, 0.45, 0.4) if i == 0 else (0.45, 0.6, 1.0)
        ob = bpy.data.objects.new(sd.name, sd)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = (x, 9.0, z)
        aim(ob, (x * 0.2, -20.0, 0.0))
        lights[f"ray{i}"] = ob
        for f in range(0, n):          # the shafts fade up with the letters: the film cuts in from black
            sd.energy = 2500 * sch.smooth(f / 45.0)
            sd.keyframe_insert("energy", frame=f0 + f)
        linearize(sd)
    sd = bpy.data.lights.new("SWEEP", "SPOT")
    sd.spot_size = math.radians(55)
    sd.spot_blend = 0.6
    sd.shadow_soft_size = 0.6
    sd.energy = 0
    sw = bpy.data.objects.new("SWEEP", sd)
    bpy.context.scene.collection.objects.link(sw)
    lights["sweep"] = sw
    for f in range(0, n):
        s = sch.sweep(f)
        sw.location = (s["x"], -7.0, 2.6)
        aim(sw, (s["x"] * 0.55, 0.0, 0.0))
        sd.energy = 16000 * s["level"]
        for path in ("location", "rotation_euler"):
            sw.keyframe_insert(path, frame=f0 + f)
        sd.keyframe_insert("energy", frame=f0 + f)
    linearize(sw)
    linearize(sd)
    return lights


def build_volume():
    """A cube of thin, noisy scattering fog around the word: the back spots turn into shafts in it."""
    bpy.ops.mesh.primitive_cube_add(size=1)
    ob = bpy.context.active_object
    ob.name = "FOG"
    ob.scale = (46, 36, 24)
    ob.location = (0, 0, 0)
    ob.visible_shadow = False
    m = bpy.data.materials.new("sau_fog")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.35
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.6
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    mp = nt.nodes.new("ShaderNodeMapRange")
    mp.inputs["From Min"].default_value = 0.3
    mp.inputs["From Max"].default_value = 0.8
    mp.inputs["To Min"].default_value = 0.35
    mp.inputs["To Max"].default_value = 1.6
    nt.links.new(noise.outputs["Fac"], mp.inputs["Value"])
    sc = nt.nodes.new("ShaderNodeVolumeScatter")
    sc.inputs["Anisotropy"].default_value = 0.55
    sc.inputs["Color"].default_value = (0.8, 0.85, 1.0, 1)
    sc.inputs["Density"].default_value = 0.02
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 0.014
    nt.links.new(mp.outputs[0], mul.inputs[0])
    nt.links.new(mul.outputs[0], sc.inputs["Density"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(sc.outputs[0], out.inputs["Volume"])
    ob.data.materials.append(m)
    return ob


# --- rings and sparks ---------------------------------------------------------------------------------------------------
def build_rings(n, f0):
    rings = []
    for i, (xpx, col) in enumerate(sch.RINGS):
        bpy.ops.mesh.primitive_torus_add(major_radius=1.3, minor_radius=0.035, major_segments=96, minor_segments=10,
                                         rotation=(math.pi / 2, 0, 0))
        ob = bpy.context.active_object
        ob.name = f"RING {i}"
        ob.location = (xpx * sch.PX, 3.0, 3.0)
        m = glow_material(f"sau_ring{i}", col, 1.0)
        ob.data.materials.append(m)
        ob.visible_shadow = False
        em = m.node_tree.nodes["Emission"].inputs["Strength"]
        for f in range(0, n):
            r = sch.ring(i, f, n)
            ob.scale = (r["scale"],) * 3
            ob.keyframe_insert("scale", frame=f0 + f)
            em.default_value = 14.0 * r["opacity"]
            em.keyframe_insert("default_value", frame=f0 + f)
        linearize(ob)
        linearize(m.node_tree)
        rings.append(ob)
    return rings


def build_sparks(layout, n, f0):
    flights = sch.flights()
    mesh = bpy.data.meshes.new("spark")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    bm.to_mesh(mesh)
    bm.free()
    mat = glow_material("sau_spark", (1.0, 0.55, 0.3), 40.0)
    mesh.materials.append(mat)
    objs = []
    for k, sp in enumerate(sch.sparks(flights, n)):
        slot = layout["slots"][sp["slot"]]
        ob = bpy.data.objects.new(f"SPARK {k}", mesh)
        bpy.context.scene.collection.objects.link(ob)
        ob.visible_shadow = False
        base = Vector((slot["x"], 0.0, slot["z"]))
        for f in range(max(0, sp["born"] - 1), min(n, sp["born"] + sp["life"] + 2)):
            dx, dy, dz, s = sch.spark_state(sp, f)
            ob.location = base + Vector((dx, dy - 0.7, dz))
            ob.scale = (s,) * 3
            ob.keyframe_insert("location", frame=f0 + f)
            ob.keyframe_insert("scale", frame=f0 + f)
        linearize(ob)
        objs.append(ob)
    return objs


# --- camera ---------------------------------------------------------------------------------------------------------------
def build_camera(n, f0):
    """ORBIT empty at the origin, camera 20 BU behind it (AE zoom 2000 at z -2000), DoF focused on the word. The AE
    LOGO scale push (114 -> 100 -> 97 %) is a dolly: distance = 20 / scale."""
    orbit = bpy.data.objects.new("ORBIT", None)
    bpy.context.scene.collection.objects.link(orbit)
    orbit.rotation_mode = "ZXY"
    cd = bpy.data.cameras.new("CAM")
    cd.lens = 2000.0 / 1920.0 * 36.0
    cd.sensor_width = 36.0
    cd.clip_end = 200
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 0.9
    cam = bpy.data.objects.new("CAM", cd)
    bpy.context.scene.collection.objects.link(cam)
    cam.parent = orbit
    cam.rotation_euler = (math.pi / 2, 0, 0)
    cd.dof.focus_object = None
    for f in range(0, n):
        c = sch.camera(f, n)
        rx, ry, rz = (math.radians(a) for a in c["orbit"])
        orbit.rotation_euler = Euler((-rx * 0.8, rz, -ry), "ZXY")   # pitch, roll, yaw about the word's centre
        dist = sch.CAM_DIST * 100.0 / c["scale"]
        cam.location = (0, -dist, 0)
        cd.dof.focus_distance = dist
        orbit.keyframe_insert("rotation_euler", frame=f0 + f)
        cam.keyframe_insert("location", frame=f0 + f)
        cd.dof.keyframe_insert("focus_distance", frame=f0 + f)
    linearize(orbit)
    linearize(cam)
    linearize(cd)
    bpy.context.scene.camera = cam
    return cam


# --- letters' animation ---------------------------------------------------------------------------------------------------
def animate_letters(objs, n, f0):
    flights = sch.flights()
    for ob, fl in zip(objs, flights):
        rest = Vector(ob["rest"])
        for f in range(0, n):
            st = sch.letter_state(fl, f)
            ob.location = rest + Vector(st["off"])
            rx, ry, rz = (math.radians(a) for a in st["rot"])
            tx, ty = (math.radians(a) for a in st["tilt"])
            # AE: X pitch, Y spin about the vertical axis, Z roll about the view axis -> Blender X, Z, Y
            ob.rotation_euler = Euler((rx + tx, rz, ry + ty), "XYZ")
            ob.color = (1, 1, 1, st["opacity"])
            ob.keyframe_insert("location", frame=f0 + f)
            ob.keyframe_insert("rotation_euler", frame=f0 + f)
            ob.keyframe_insert("color", frame=f0 + f)
        linearize(ob)


# --- compositor -------------------------------------------------------------------------------------------------------------
def block_noise_image(w, h, block=14, seed=5):
    """The pixel dissolve's threshold map: one random value per 14x14 block (AE Block Dissolve)."""
    import random
    rnd = random.Random(seed)
    bw, bh = (w + block - 1) // block, (h + block - 1) // block
    vals = [[rnd.random() for _ in range(bw)] for _ in range(bh)]
    img = bpy.data.images.new("dissolve_blocks", w, h, alpha=False, float_buffer=True)
    px = []
    for y in range(h):
        row = vals[y // block]
        for x in range(w):
            v = row[x // block]
            px.extend((v, v, v, 1.0))
    img.pixels.foreach_set(px)
    img.colorspace_settings.name = "Non-Color"
    img.pack()
    return img


def build_compositor(n, f0, w, h):
    sc = bpy.context.scene
    nt = bpy.data.node_groups.new("outro_comp", "CompositorNodeTree")
    sc.compositing_node_group = nt
    nt.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = _node(nt, "CompositorNodeRLayers", 0, 0)
    gl = _node(nt, "CompositorNodeGlare", 260, 0)
    gl.inputs["Type"].default_value = "Bloom"
    gl.inputs["Threshold"].default_value = 0.9
    gl.inputs["Size"].default_value = 0.7
    gl.inputs["Quality"].default_value = "High"
    nt.links.new(rl.outputs["Image"], gl.inputs["Image"])
    # vignette: black at 70 % outside an ellipse, feathered (outro.jsx VIGNETTE)
    el = _node(nt, "CompositorNodeEllipseMask", 260, -300)
    el.inputs["Size"].default_value = (0.62, 0.66)
    el.inputs["Position"].default_value = (0.5, 0.5)
    bl = _node(nt, "CompositorNodeBlur", 480, -300)
    bl.inputs["Size"].default_value = (0.2 * w / 2, 0.2 * w / 2)
    nt.links.new(el.outputs["Mask"], bl.inputs["Image"])
    inv = _node(nt, "ShaderNodeMath", 700, -300, operation="SUBTRACT")
    inv.inputs[0].default_value = 1.0
    nt.links.new(bl.outputs["Image"], inv.inputs[1])
    vf = _node(nt, "ShaderNodeMath", 900, -300, operation="MULTIPLY")
    vf.inputs[1].default_value = 0.7
    nt.links.new(inv.outputs[0], vf.inputs[0])
    black = (0, 0, 0, 1)
    vmix = _node(nt, "ShaderNodeMix", 1100, 0, data_type="RGBA")
    vmix.inputs["B"].default_value = black
    nt.links.new(gl.outputs["Image"], vmix.inputs["A"])
    nt.links.new(vf.outputs[0], vmix.inputs["Factor"])
    # flashes: hit (white add) and end (screen-ish add)
    fl = _node(nt, "ShaderNodeMix", 1320, 0, data_type="RGBA", blend_type="ADD")
    fl.inputs["B"].default_value = (1.0, 0.96, 0.95, 1)
    nt.links.new(vmix.outputs["Result"], fl.inputs["A"])
    # pixel dissolve
    img = block_noise_image(w, h)
    im = _node(nt, "CompositorNodeImage", 1100, -300)
    im.image = img
    cmp_ = _node(nt, "ShaderNodeMath", 1320, -300, operation="LESS_THAN")
    nt.links.new(im.outputs["Image"], cmp_.inputs[0])
    dm = _node(nt, "ShaderNodeMix", 1560, 0, data_type="RGBA")
    dm.inputs["B"].default_value = black
    nt.links.new(fl.outputs["Result"], dm.inputs["A"])
    nt.links.new(cmp_.outputs[0], dm.inputs["Factor"])
    go = _node(nt, "NodeGroupOutput", 1800, 0)
    nt.links.new(dm.outputs["Result"], go.inputs[0])
    for f in range(0, n):
        fx = sch.end_fx(f, n)
        fl.inputs["Factor"].default_value = max(fx["hit"], fx["flash_end"])
        gl.inputs["Strength"].default_value = fx["bloom"] * 0.35
        cmp_.inputs[1].default_value = 1.01 if fx["black"] else fx["dissolve"] * 1.0005
        for sock in (fl.inputs["Factor"], gl.inputs["Strength"], cmp_.inputs[1]):
            sock.keyframe_insert("default_value", frame=f0 + f)
    linearize(nt)
    return nt
