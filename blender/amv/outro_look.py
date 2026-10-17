"""The SAU_EDITZ outro's look in Blender/Cycles: materials, world, lights, god-ray volume, rings, sparks, camera rig and
the compositor (bloom, vignette, flashes, pixel dissolve). Every animated value is sampled from `outro_schedule` at
each comp frame, so the keyframes are linear between whole frames and Cycles' motion blur (301 deg) sees the true curve.

Units: 1 BU = 100 AE px; the camera is at y = -20 looking along +y, letters face it (-y), z is up.
"""
from __future__ import annotations

import math
import os
import tempfile

import bpy
from mathutils import Euler, Vector

from . import outro_schedule as sch

RED = (0.85, 0.015, 0.04)
NAVY = (0.02, 0.06, 0.30)
BEVEL_C = (1.0, 0.12, 0.08)


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
    p = _principled(nt, **{"Metallic": 0.55, "Roughness": 0.18, "Coat Weight": 1.0, "Coat Roughness": 0.02,
                           "Specular IOR Level": 1.0})
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
    mixc.inputs["B"].default_value = (0.1, 0.0, 0.004, 1)
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
    p = _principled(nt, **{"Base Color": (*BEVEL_C, 1), "Metallic": 1.0, "Roughness": 0.1, "Coat Weight": 1.0,
                           "Specular IOR Level": 1.0, "Emission Color": (1.0, 0.1, 0.08, 1), "Emission Strength": 0.15})
    _fade_wrap(nt, p.outputs[0])
    return m


def side_material():
    m = bpy.data.materials.new("sau_side")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    p = _principled(nt, **{"Base Color": (*NAVY, 1), "Metallic": 1.0, "Roughness": 0.2, "Anisotropic": 0.3,
                           "Specular IOR Level": 1.0})
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
    ramp.color_ramp.elements[0].color = (0.006, 0.001, 0.003, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.0004, 0.0008, 0.003, 1)
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
    """KEY warm, a hard cool-white rim on one side and a blue rim on the other so every edge reads against the black
    (art direction after draft 1), TOP cool, softbox strips for the glossy reflections, and the moving SWEEP."""
    lights = {}
    lights["key"] = _area("KEY warm", (-9, -14, 8), (7, 4), 3500, (1.0, 0.95, 0.9))
    lights["rim_w"] = _area("RIM white", (-13, 7, 4), (2.5, 14), 18000, (0.88, 0.94, 1.0))
    lights["rim_b"] = _area("RIM blue", (15, 5, -3), (3.0, 14), 18000, (0.22, 0.42, 1.0))
    lights["top"] = _area("TOP cool", (2, -3, 15), (14, 4), 4500, (0.7, 0.8, 1.0))
    lights["strip_l"] = _area("STRIP left", (-12, -9, 1), (1.2, 12), 2400, (1, 1, 1))
    lights["strip_r"] = _area("STRIP right", (11, -11, 1), (1.2, 12), 1800, (1, 0.9, 0.85))
    sd = bpy.data.lights.new("SWEEP", "SPOT")
    sd.spot_size = math.radians(40)
    sd.spot_blend = 0.5
    sd.shadow_soft_size = 0.4
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


def build_shafts(n, f0):
    """Cheap god rays: long soft light planes fanning out from behind the word (no volume rendering: that cost 13 s a
    frame on a 4090). Additive-looking emission with a transparent falloff along and across each plane."""
    import bmesh
    me = bpy.data.meshes.new("shaft")
    bm = bmesh.new()
    vs = [bm.verts.new(c) for c in ((-0.5, 0, 0), (0.5, 0, 0), (0.5, 1, 0), (-0.5, 1, 0))]
    bm.faces.new(vs)
    bm.to_mesh(me)
    bm.free()
    shafts = []
    for i in range(9):
        red = i % 2 == 0
        m = bpy.data.materials.new(f"sau_shaft{i}")
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs[0])
        al = nt.nodes.new("ShaderNodeMath"); al.operation = "ABSOLUTE"
        nt.links.new(sep.outputs["X"], al.inputs[0])
        across = nt.nodes.new("ShaderNodeMapRange")
        across.inputs["From Min"].default_value = 0.5; across.inputs["From Max"].default_value = 0.0
        nt.links.new(al.outputs[0], across.inputs["Value"])
        along = nt.nodes.new("ShaderNodeMapRange")
        along.inputs["From Min"].default_value = 1.0; along.inputs["From Max"].default_value = 0.0
        nt.links.new(sep.outputs["Y"], along.inputs["Value"])
        prod = nt.nodes.new("ShaderNodeMath"); prod.operation = "MULTIPLY"
        nt.links.new(across.outputs[0], prod.inputs[0]); nt.links.new(along.outputs[0], prod.inputs[1])
        sq = nt.nodes.new("ShaderNodeMath"); sq.operation = "POWER"; sq.inputs[1].default_value = 2.0
        nt.links.new(prod.outputs[0], sq.inputs[0])
        gain = nt.nodes.new("ShaderNodeMath"); gain.operation = "MULTIPLY"; gain.inputs[1].default_value = 0.4
        nt.links.new(sq.outputs[0], gain.inputs[0])
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (1.0, 0.12, 0.08, 1) if red else (0.2, 0.4, 1.0, 1)
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(gain.outputs[0], mix.inputs[0])
        nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2])
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        piv = bpy.data.objects.new(f"SHAFT pivot {i}", None)
        bpy.context.scene.collection.objects.link(piv)
        piv.location = (0.0, 8.0, 0.8)
        ob = bpy.data.objects.new(f"SHAFT {i}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = piv
        ob.rotation_euler = (math.pi / 2, 0, 0)             # the plane's length runs up the screen
        ob.scale = (0.7 + 0.3 * (i % 3), 34.0, 1.0)
        ob.data.materials.clear()
        ob.data.materials.append(m)
        ob.visible_shadow = False
        base = math.radians(-80 + i * 20)
        for f in range(0, n):
            piv.rotation_euler = (0.0, base + math.radians(6) * (f / n) * (1 if red else -1), 0.0)
            piv.keyframe_insert("rotation_euler", frame=f0 + f)
            em.inputs["Strength"].default_value = (0.5 if red else 0.6) * sch.smooth(f / 45.0)
            em.inputs["Strength"].keyframe_insert("default_value", frame=f0 + f)
        linearize(piv)
        linearize(nt)
        shafts.append(ob)
    return shafts


# --- rings and sparks ---------------------------------------------------------------------------------------------------
def build_rings(n, f0):
    rings = []
    for i, (xpx, col) in enumerate(sch.RINGS):
        bpy.ops.mesh.primitive_torus_add(major_radius=1.3, minor_radius=0.045, major_segments=96, minor_segments=10,
                                         rotation=(math.pi / 2, 0, 0))
        ob = bpy.context.active_object
        ob.name = f"RING {i}"
        ob.location = (xpx * sch.PX, 3.0, 3.3)
        m = glow_material(f"sau_ring{i}", col, 1.0)
        ob.data.materials.append(m)
        ob.visible_shadow = False
        em = m.node_tree.nodes["Emission"].inputs["Strength"]
        for f in range(0, n):
            r = sch.ring(i, f, n)
            ob.scale = (r["scale"],) * 3
            ob.keyframe_insert("scale", frame=f0 + f)
            em.default_value = 26.0 * r["opacity"] * (1.0 + 1.5 * r["pop"])
            em.keyframe_insert("default_value", frame=f0 + f)
        linearize(ob)
        linearize(m.node_tree)
        rings.append(ob)
        _ring_flare(i, col, n, f0)
    return rings


def _ring_flare(i, col, n, f0):
    """The horizontal lens streak when a ring pops, as an emissive plane behind it (a compositor streak glare at full
    resolution cost more than the whole Cycles frame)."""
    import bmesh
    me = bpy.data.meshes.new(f"flare{i}")
    bm = bmesh.new()
    bm.faces.new([bm.verts.new(c) for c in ((-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0))])
    bm.to_mesh(me)
    bm.free()
    m = bpy.data.materials.new(f"sau_flare{i}")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    fall = []
    for axis, power in (("X", 3.0), ("Y", 2.0)):
        ab = nt.nodes.new("ShaderNodeMath"); ab.operation = "ABSOLUTE"
        nt.links.new(sep.outputs[axis], ab.inputs[0])
        mp = nt.nodes.new("ShaderNodeMapRange")
        mp.inputs["From Min"].default_value = 0.5; mp.inputs["From Max"].default_value = 0.0
        nt.links.new(ab.outputs[0], mp.inputs["Value"])
        pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = power
        nt.links.new(mp.outputs[0], pw.inputs[0])
        fall.append(pw)
    prod = nt.nodes.new("ShaderNodeMath"); prod.operation = "MULTIPLY"
    nt.links.new(fall[0].outputs[0], prod.inputs[0]); nt.links.new(fall[1].outputs[0], prod.inputs[1])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*col, 1)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(prod.outputs[0], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    ob = bpy.data.objects.new(f"FLARE {i}", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_euler = (math.pi / 2, 0, 0)
    ob.location = (sch.RINGS[i][0] * sch.PX, 3.4, 3.3)
    ob.scale = (9.0, 0.6, 1.0)
    ob.data.materials.append(m)
    ob.visible_shadow = False
    for f in range(0, n):
        em.inputs["Strength"].default_value = 14.0 * sch.ring(i, f, n)["pop"]
        em.inputs["Strength"].keyframe_insert("default_value", frame=f0 + f)
    linearize(nt)


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
def write_gray_png(path, rows):
    """8-bit grayscale PNG from a list of bytes rows (Blender's own Image.save wrote black for generated images)."""
    import struct
    import zlib

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def block_noise_image(w, h, block=14, seed=5):
    """The pixel dissolve's threshold map: one random value per 14x14 block (AE Block Dissolve), as a packed PNG."""
    import random
    rnd = random.Random(seed)
    bw, bh = (w + block - 1) // block, (h + block - 1) // block
    vals = [[int(rnd.random() * 254) + 1 for _ in range(bw)] for _ in range(bh)]
    rows = [[vals[y // block][x // block] for x in range(w)] for y in range(h)]
    path = os.path.join(tempfile.mkdtemp(prefix="outro_blocks_"), "blocks.png")
    write_gray_png(path, rows)
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = "Non-Color"
    img.pack()
    return img


def vignette_image(w=160, h=90):
    """Vignette weight 1 inside / 0 outside, a feathered ellipse 0.62 W x 0.66 H (outro.jsx), as a tiny packed PNG."""
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            r = math.hypot(((x + 0.5) / w - 0.5) / 0.31, ((y + 0.5) / h - 0.5) / 0.33)
            row.append(int(255 * (1.0 - sch.smooth((r - 0.6) / 0.9)) + 0.5))
        rows.append(row)
    path = os.path.join(tempfile.mkdtemp(prefix="outro_vig_"), "vignette.png")
    write_gray_png(path, rows)
    img = bpy.data.images.load(path)
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
    gl.inputs["Quality"].default_value = "Low"
    nt.links.new(rl.outputs["Image"], gl.inputs["Image"])
    # vignette (outro.jsx VIGNETTE: black at 70 % outside a feathered ellipse) from a tiny gradient image scaled up:
    # a full-res ellipse mask + 190 px blur was the compositor's most expensive step
    vg = _node(nt, "CompositorNodeImage", 260, -300)
    vg.image = vignette_image()
    sv = _node(nt, "CompositorNodeScale", 480, -300)
    sv.inputs["Type"].default_value = "Render Size"
    sv.inputs["Frame Type"].default_value = "Stretch"
    sv.inputs["Interpolation"].default_value = "Bilinear"
    nt.links.new(vg.outputs["Image"], sv.inputs["Image"])
    inv = _node(nt, "ShaderNodeMath", 700, -300, operation="SUBTRACT")
    inv.inputs[0].default_value = 1.0
    nt.links.new(sv.outputs["Image"], inv.inputs[1])
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
    fl.inputs["B"].default_value = (1.0, 1.0, 1.0, 1)
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
    fi = _node(nt, "ShaderNodeMix", 1780, 0, data_type="RGBA")      # the cut in from black: the implode ends on black
    fi.inputs["B"].default_value = black
    nt.links.new(dm.outputs["Result"], fi.inputs["A"])
    go = _node(nt, "NodeGroupOutput", 2000, 0)
    nt.links.new(fi.outputs["Result"], go.inputs[0])
    for f in range(0, n):
        fx = sch.end_fx(f, n)
        fl.inputs["Factor"].default_value = max(fx["hit"], fx["flash_end"])   # white, added
        gl.inputs["Strength"].default_value = fx["bloom"] * 0.35
        cmp_.inputs[1].default_value = 1.01 if fx["black"] else fx["dissolve"] * 1.0005
        fi.inputs["Factor"].default_value = fx["fade_in"]
        for sock in (fl.inputs["Factor"], gl.inputs["Strength"], cmp_.inputs[1], fi.inputs["Factor"]):
            sock.keyframe_insert("default_value", frame=f0 + f)
    linearize(nt)
    return nt
