"""Timeless v3 stage: cards (shot planes playing a plate), their materials, holdout mattes and the act void environments.

A card is a 1.92 x 1.08 m plane (1 px = 1 mm) in local XY, normal +Z, UV 0..1, playing an image sequence in comp time
through an Emission shader (Standard view transform -> the plate's sRGB values come out unchanged).
Image sequences: Blender's ImageUser clamps a sequence badly before its first frame, so every sequence the stage uses is
a folder of symlinks `<out>/_seq/<kind>/<shot>/f_00000..f_00899` that point at the nearest existing frame (holds the
first/last plate frame outside the plate range); the image user maps scene frame N to file N.
"""
import math
import os
import random

import bpy
from mathutils import Matrix, Vector

from camlib import CARD_H, CARD_W

NFRAMES = 900


# ---- image sequences ------------------------------------------------------------------------------------------------------
def link_sequence(src_dir, link_dir, ext):
    """Make link_dir/f_00000..f_00899.<ext> -> nearest existing src_dir/f_NNNNN.<ext>. Returns the first link path or None."""
    if not os.path.isdir(src_dir):
        return None
    have = sorted(int(n[2:7]) for n in os.listdir(src_dir) if n.startswith("f_") and n.endswith("." + ext) and n[2:7].isdigit())
    if not have:
        return None
    os.makedirs(link_dir, exist_ok=True)
    j = 0
    for n in range(NFRAMES):
        while j + 1 < len(have) and abs(have[j + 1] - n) <= abs(have[j] - n):
            j += 1
        dst = os.path.join(link_dir, f"f_{n:05d}.{ext}")
        target = os.path.join(os.path.abspath(src_dir), f"f_{have[j]:05d}.{ext}")
        if os.path.islink(dst) or os.path.exists(dst):
            if os.path.islink(dst) and os.readlink(dst) == target:
                continue
            os.remove(dst)
        os.symlink(target, dst)
    return os.path.join(link_dir, f"f_{0:05d}.{ext}")


def load_sequence(first_path, colorspace):
    img = bpy.data.images.load(first_path, check_existing=True)
    img.source = "SEQUENCE"
    try:
        img.colorspace_settings.name = colorspace
    except TypeError:
        pass
    return img


def setup_user(iu):
    """Image user: scene frame N shows file N (frame_start 0, 900 frames, offset -1; see module doc)."""
    iu.frame_start = 0
    iu.frame_duration = NFRAMES
    iu.frame_offset = -1
    iu.use_cyclic = False
    iu.use_auto_refresh = True


# ---- meshes ------------------------------------------------------------------------------------------------------------------
def card_mesh(name, nx=1, ny=1, w=CARD_W, h=CARD_H, tile=1):
    """Plane (w x h) * tile centred at the origin in XY, normal +Z, nx x ny quads; UV 0..1 over the central w x h (so a
    tile = 3 card spans UV -1..2 and a MIRROR texture shows the picture mirror-tiled around the card). Vertex group
    'interior' (see interior_group) keeps the outer border flat under depth displacement."""
    me = bpy.data.meshes.new(name)
    verts, faces, uvs = [], [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / ny
            verts.append(((u - 0.5) * w * tile, (v - 0.5) * h * tile, 0.0))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            x, y, _ = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (x / w + 0.5, y / h + 0.5)
    me.update()
    return me


def interior_group(ob, nx, ny):
    vg = ob.vertex_groups.new(name="interior")
    for j in range(ny + 1):
        for i in range(nx + 1):
            border = min(i, nx - i, j, ny - j)
            wgt = min(1.0, border / 3.0)  # ramp over 3 rows: the edge stays flat, the inside follows the depth
            if wgt > 0:
                vg.add([j * (nx + 1) + i], wgt, "REPLACE")
    return vg


# ---- materials --------------------------------------------------------------------------------------------------------------
def _n(nt, kind, x=0, y=0, **props):
    n = nt.nodes.new(kind)
    n.location = (x, y)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def card_material(name, plate_img, matte_img=None, alpha="none", hole=None, backface=None, sweep=False,
                  extension="EXTEND"):
    """Emission card material. alpha: 'none' | 'matte' (alpha = subject matte). hole: dict(center=[px, py], feather=px)
    -> a 'HoleR' Value node (radius px, the caller keys it). backface: RGB for the card's back (None = the plate).
    sweep: adds a 'Sweep' Value node (diagonal light band position 0..1, the caller keys it) and 'SweepAmt'.
    The Emission strength (node 'Emission', input 1) is the fade (0 = black)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = _n(nt, "ShaderNodeOutputMaterial", 900, 0)
    tc = _n(nt, "ShaderNodeTexCoord", -900, 0)
    tex = _n(nt, "ShaderNodeTexImage", -650, 100, image=plate_img, interpolation="Linear", extension=extension)
    setup_user(tex.image_user)
    nt.links.new(tc.outputs["UV"], tex.inputs["Vector"])
    em = _n(nt, "ShaderNodeEmission", 0, 100, name="Emission", label="Emission")
    em.inputs[1].default_value = 1.0
    col = tex.outputs["Color"]
    if sweep:
        # band = exp(-((u + 0.45 v) / 1.45 - pos)^2 / w^2), colour * (1 + amt * band)
        sep = _n(nt, "ShaderNodeSeparateXYZ", -650, -250)
        nt.links.new(tc.outputs["UV"], sep.inputs[0])
        pos = _n(nt, "ShaderNodeValue", -650, -450, name="Sweep", label="Sweep")
        pos.outputs[0].default_value = -1.0
        amt = _n(nt, "ShaderNodeValue", -650, -550, name="SweepAmt", label="SweepAmt")
        amt.outputs[0].default_value = 0.0
        d = _n(nt, "ShaderNodeMath", -450, -250, operation="MULTIPLY_ADD")
        nt.links.new(sep.outputs[1], d.inputs[0]); d.inputs[1].default_value = 0.45; nt.links.new(sep.outputs[0], d.inputs[2])
        d2 = _n(nt, "ShaderNodeMath", -300, -250, operation="MULTIPLY"); nt.links.new(d.outputs[0], d2.inputs[0])
        d2.inputs[1].default_value = 1 / 1.45
        d3 = _n(nt, "ShaderNodeMath", -150, -250, operation="SUBTRACT"); nt.links.new(d2.outputs[0], d3.inputs[0])
        nt.links.new(pos.outputs[0], d3.inputs[1])
        d4 = _n(nt, "ShaderNodeMath", 0, -250, operation="DIVIDE"); nt.links.new(d3.outputs[0], d4.inputs[0])
        d4.inputs[1].default_value = 0.09
        d5 = _n(nt, "ShaderNodeMath", 150, -250, operation="POWER"); nt.links.new(d4.outputs[0], d5.inputs[0])
        d5.inputs[1].default_value = 2.0
        d6 = _n(nt, "ShaderNodeMath", 300, -250, operation="MULTIPLY"); nt.links.new(d5.outputs[0], d6.inputs[0])
        d6.inputs[1].default_value = -1.0
        d7 = _n(nt, "ShaderNodeMath", 450, -250, operation="EXPONENT"); nt.links.new(d6.outputs[0], d7.inputs[0])
        d8 = _n(nt, "ShaderNodeMath", 600, -250, operation="MULTIPLY_ADD")
        nt.links.new(d7.outputs[0], d8.inputs[0]); nt.links.new(amt.outputs[0], d8.inputs[1]); d8.inputs[2].default_value = 1.0
        mul = _n(nt, "ShaderNodeVectorMath", -150, 100, operation="SCALE")
        nt.links.new(col, mul.inputs[0]); nt.links.new(d8.outputs[0], mul.inputs["Scale"])
        col = mul.outputs[0]
    nt.links.new(col, em.inputs["Color"])
    shader = em.outputs[0]
    if backface is not None:
        geo = _n(nt, "ShaderNodeNewGeometry", 0, 350)
        back = _n(nt, "ShaderNodeBsdfPrincipled", 0, 600)
        back.inputs["Base Color"].default_value = (*backface, 1)
        back.inputs["Roughness"].default_value = 0.35
        mixb = _n(nt, "ShaderNodeMixShader", 250, 200)
        nt.links.new(geo.outputs["Backfacing"], mixb.inputs[0])
        nt.links.new(shader, mixb.inputs[1]); nt.links.new(back.outputs[0], mixb.inputs[2])
        shader = mixb.outputs[0]
    fac = None  # opacity 0..1
    if alpha == "matte" and matte_img is not None:
        mt = _n(nt, "ShaderNodeTexImage", -650, -700, image=matte_img, interpolation="Linear", extension=extension)
        setup_user(mt.image_user)
        nt.links.new(tc.outputs["UV"], mt.inputs["Vector"])
        fac = mt.outputs["Color"]
    if hole:
        # opacity = smoothstep(r - feather, r, dist(px, center)), r keyed on the 'HoleR' value node
        cx, cy = hole["center"]
        fe = float(hole.get("feather", 24.0))
        sep = _n(nt, "ShaderNodeSeparateXYZ", -650, -950)
        nt.links.new(tc.outputs["UV"], sep.inputs[0])
        px = _n(nt, "ShaderNodeMath", -450, -950, operation="MULTIPLY_ADD")
        nt.links.new(sep.outputs[0], px.inputs[0]); px.inputs[1].default_value = 1920.0; px.inputs[2].default_value = -cx
        py = _n(nt, "ShaderNodeMath", -450, -1100, operation="MULTIPLY_ADD")  # pixel y (down) = 1080 (1 - v)
        nt.links.new(sep.outputs[1], py.inputs[0]); py.inputs[1].default_value = -1080.0; py.inputs[2].default_value = 1080.0 - cy
        dist = _n(nt, "ShaderNodeVectorMath", -250, -1000, operation="LENGTH")
        cmb = _n(nt, "ShaderNodeCombineXYZ", -350, -1000)
        nt.links.new(px.outputs[0], cmb.inputs[0]); nt.links.new(py.outputs[0], cmb.inputs[1])
        nt.links.new(cmb.outputs[0], dist.inputs[0])
        rad = _n(nt, "ShaderNodeValue", -450, -1250, name="HoleR", label="HoleR")
        rad.outputs[0].default_value = 0.0
        lo = _n(nt, "ShaderNodeMath", -250, -1250, operation="SUBTRACT")
        nt.links.new(rad.outputs[0], lo.inputs[0]); lo.inputs[1].default_value = fe
        mr = _n(nt, "ShaderNodeMapRange", -50, -1000, interpolation_type="SMOOTHSTEP")
        nt.links.new(dist.outputs["Value"], mr.inputs["Value"])
        nt.links.new(lo.outputs[0], mr.inputs["From Min"]); nt.links.new(rad.outputs[0], mr.inputs["From Max"])
        if fac is not None:
            mm = _n(nt, "ShaderNodeMath", 150, -900, operation="MULTIPLY")
            nt.links.new(fac, mm.inputs[0]); nt.links.new(mr.outputs["Result"], mm.inputs[1])
            fac = mm.outputs[0]
        else:
            fac = mr.outputs["Result"]
    if fac is not None:
        tr = _n(nt, "ShaderNodeBsdfTransparent", 300, -150)
        mix = _n(nt, "ShaderNodeMixShader", 600, 0)
        nt.links.new(fac, mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(shader, mix.inputs[2])
        shader = mix.outputs[0]
    nt.links.new(shader, out.inputs["Surface"])
    return m


def holdout_material(name, matte_img):
    """Text-pass holdout: holdout where the subject matte is white, transparent elsewhere."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = _n(nt, "ShaderNodeOutputMaterial", 600, 0)
    tc = _n(nt, "ShaderNodeTexCoord", -600, 0)
    mt = _n(nt, "ShaderNodeTexImage", -400, 0, image=matte_img, interpolation="Linear", extension="EXTEND")
    setup_user(mt.image_user)
    nt.links.new(tc.outputs["UV"], mt.inputs["Vector"])
    tr = _n(nt, "ShaderNodeBsdfTransparent", 0, 150)
    ho = _n(nt, "ShaderNodeHoldout", 0, -150)
    mix = _n(nt, "ShaderNodeMixShader", 300, 0)
    nt.links.new(mt.outputs["Color"], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(ho.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def emission_material(name, rgb, strength=1.0, alpha=1.0, noise=0.0, radial=False):
    """Glow material: emission rgb * strength, optional opacity alpha, noise breakup (0..1), radial falloff (soft disc)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = _n(nt, "ShaderNodeOutputMaterial", 800, 0)
    em = _n(nt, "ShaderNodeEmission", 200, 100, name="Emission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strength
    fac = None
    tc = _n(nt, "ShaderNodeTexCoord", -800, -200)
    if radial:
        # opacity = (1 - |uv - 0.5| * 2)^2
        vm = _n(nt, "ShaderNodeVectorMath", -600, -200, operation="SUBTRACT")
        nt.links.new(tc.outputs["UV"], vm.inputs[0]); vm.inputs[1].default_value = (0.5, 0.5, 0.0)
        ln = _n(nt, "ShaderNodeVectorMath", -450, -200, operation="LENGTH"); nt.links.new(vm.outputs[0], ln.inputs[0])
        mr = _n(nt, "ShaderNodeMapRange", -300, -200, interpolation_type="SMOOTHSTEP")
        nt.links.new(ln.outputs["Value"], mr.inputs["Value"])
        mr.inputs["From Min"].default_value = 0.5; mr.inputs["From Max"].default_value = 0.0
        fac = mr.outputs["Result"]
    if noise > 0:
        nz = _n(nt, "ShaderNodeTexNoise", -450, -450)
        nz.inputs["Scale"].default_value = 3.0
        nz.inputs["Detail"].default_value = 4.0
        nt.links.new(tc.outputs["Generated"], nz.inputs["Vector"])
        mr2 = _n(nt, "ShaderNodeMapRange", -250, -450)
        nt.links.new(nz.outputs["Fac"], mr2.inputs["Value"])
        mr2.inputs["From Min"].default_value = 0.35; mr2.inputs["From Max"].default_value = 0.75
        mr2.inputs["To Min"].default_value = 1 - noise
        if fac is not None:
            mm = _n(nt, "ShaderNodeMath", -50, -300, operation="MULTIPLY")
            nt.links.new(fac, mm.inputs[0]); nt.links.new(mr2.outputs["Result"], mm.inputs[1])
            fac = mm.outputs[0]
        else:
            fac = mr2.outputs["Result"]
    if alpha < 1.0 or fac is not None:
        a = _n(nt, "ShaderNodeMath", 100, -300, operation="MULTIPLY", name="Alpha")
        a.inputs[1].default_value = alpha
        if fac is not None:
            nt.links.new(fac, a.inputs[0])
        else:
            a.inputs[0].default_value = 1.0
        tr = _n(nt, "ShaderNodeBsdfTransparent", 200, -150)
        mix = _n(nt, "ShaderNodeMixShader", 500, 0)
        nt.links.new(a.outputs[0], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def no_shadow(ob):
    try:
        ob.visible_shadow = False
    except AttributeError:
        pass


# ---- environments -----------------------------------------------------------------------------------------------------------
def build_env_collection(act_id, pal, lib_coll):
    """The act's void: a dark act-tinted fog sphere (inside-facing gradient, never black), soft bokeh discs at depth, faint
    web strands and haze sheets. Built once per act at the world origin inside lib_coll (excluded from rendering); each
    set gets an instance (ctx.env)."""
    coll = bpy.data.collections.new(f"ENV_{act_id}")
    lib_coll.children.link(coll)
    rnd = random.Random(hash(act_id) & 0xFFFF)
    fog, key, rim, leak = pal["fog"], pal["key"], pal["rim"], pal["leak"]

    # fog sphere: emission gradient (brighter towards -Z behind the card, darker behind the camera), noise breakup
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=38.0, location=(0, 0, 0))
    sph = bpy.context.active_object
    sph.name = f"env_{act_id}_fog"
    for c in sph.users_collection:
        c.objects.unlink(sph)
    coll.objects.link(sph)
    m = bpy.data.materials.new(f"env_{act_id}_fog")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = _n(nt, "ShaderNodeOutputMaterial", 700, 0)
    tc = _n(nt, "ShaderNodeTexCoord", -900, 0)
    sep = _n(nt, "ShaderNodeSeparateXYZ", -700, 150)
    nt.links.new(tc.outputs["Normal"], sep.inputs[0])
    grad = _n(nt, "ShaderNodeMapRange", -500, 150)
    nt.links.new(sep.outputs[2], grad.inputs["Value"])
    grad.inputs["From Min"].default_value = 1.0; grad.inputs["From Max"].default_value = -1.0
    nz = _n(nt, "ShaderNodeTexNoise", -700, -150)
    nz.inputs["Scale"].default_value = 2.2; nz.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    ramp = _n(nt, "ShaderNodeValToRGB", -300, -150)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (fog[0] * 0.5, fog[1] * 0.5, fog[2] * 0.5, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (*[min(1.0, x * 1.6) for x in fog], 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    lk = _n(nt, "ShaderNodeMix", -50, 50, data_type="RGBA", blend_type="ADD")
    lk.inputs["Factor"].default_value = 1.0
    nt.links.new(ramp.outputs["Color"], lk.inputs[6])
    gl = _n(nt, "ShaderNodeMath", -250, 300, operation="POWER")
    nt.links.new(grad.outputs["Result"], gl.inputs[0]); gl.inputs[1].default_value = 3.0
    sc = _n(nt, "ShaderNodeVectorMath", -100, 300, operation="SCALE")
    sc.inputs[0].default_value = tuple(x * 0.6 for x in leak)
    nt.links.new(gl.outputs[0], sc.inputs["Scale"])
    nt.links.new(sc.outputs[0], lk.inputs[7])
    em = _n(nt, "ShaderNodeEmission", 200, 0)
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(lk.outputs[2], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    sph.data.materials.append(m)
    no_shadow(sph)

    # bokeh: soft discs scattered behind and around the card plane (-Z is behind the card)
    disc = card_mesh(f"env_{act_id}_disc", 1, 1, 1.0, 1.0)
    mats = [emission_material(f"env_{act_id}_bokeh{i}", c, s, 0.9, radial=True)
            for i, (c, s) in enumerate([(key, 2.0), (rim, 1.6), (leak, 2.4)])]
    disc.materials.append(mats[0])
    for i in range(70):
        ob = bpy.data.objects.new(f"env_{act_id}_bokeh{i}", disc)
        z = -rnd.uniform(2.0, 26.0)
        spread = 2.0 + abs(z) * 0.9
        ob.location = (rnd.uniform(-spread, spread), rnd.uniform(-spread * 0.6, spread * 0.6), z)
        ob.scale = [rnd.uniform(0.08, 0.35) * (1 + abs(z) * 0.05)] * 3
        coll.objects.link(ob)
        ob.material_slots[0].link = "OBJECT"
        ob.material_slots[0].material = mats[i % 3]
        no_shadow(ob)

    # web strands: long thin emissive ribbons radiating behind the card
    strand = card_mesh(f"env_{act_id}_strand", 1, 1, 1.0, 1.0)
    smat = emission_material(f"env_{act_id}_strand", rim, 1.2, 0.45)
    strand.materials.append(smat)
    for i in range(16):
        ob = bpy.data.objects.new(f"env_{act_id}_strand{i}", strand)
        ang = rnd.uniform(0, math.tau)
        z = -rnd.uniform(3.0, 14.0)
        ob.location = (math.cos(ang) * 1.5, math.sin(ang) * 1.0, z)
        ob.rotation_euler = (0, 0, ang)
        ob.scale = (rnd.uniform(8.0, 18.0), 0.006 * (1 + abs(z) * 0.1), 1)
        coll.objects.link(ob)
        no_shadow(ob)

    # haze sheets: big translucent leak-coloured sheets at depth (the light the whips smear)
    sheet = card_mesh(f"env_{act_id}_haze", 1, 1, 1.0, 1.0)
    hmat = emission_material(f"env_{act_id}_haze", leak, 1.0, 0.35, noise=0.9)
    sheet.materials.append(hmat)
    for i in range(6):
        ob = bpy.data.objects.new(f"env_{act_id}_haze{i}", sheet)
        z = -rnd.uniform(4.0, 12.0)
        ob.location = (rnd.uniform(-6, 6), rnd.uniform(-3, 3), z)
        ob.scale = (rnd.uniform(6, 12), rnd.uniform(3, 6), 1)
        coll.objects.link(ob)
        no_shadow(ob)
    return coll


def haze_card(name, rgb, strength, alpha, coll, matrix, size=(3.0, 2.0)):
    """A translucent, noisy, act-tinted light sheet (fills gaps between cards so whips smear light, never black)."""
    me = card_mesh(name, 1, 1, size[0], size[1])
    me.materials.append(emission_material(name, rgb, strength, alpha, noise=0.85))
    ob = bpy.data.objects.new(name, me)
    ob.matrix_world = matrix
    coll.objects.link(ob)
    no_shadow(ob)
    return ob
