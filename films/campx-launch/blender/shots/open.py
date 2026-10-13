"""open: the cold open (9 s). Darkness, then a slow low dolly forward through a hall of towering answer-script stacks
receding into haze under a high slit of light; near the end of the dolly one page lifts off the nearest stack, turns
to face the camera and rises toward it. A light sweep in the brand gradient crosses its handwriting and by the last
frame the page nearly fills the frame, in focus, ready to match-cut into the macro handwriting.

Cheap by design (target <= 6 s per 1280x720 frame at 24 samples + OIDN on 16 vCPU): the stacks are a dozen shared
meshes instanced a few hundred times, the shafts are camera-only emissive ribbons (no volumes), the dust is a few
dozen small spheres lit by the beam, and the haze is a depth fade in the materials. Everything is seeded and every
animated value is a pure function of the frame, so a re-render is identical.

Roles used: fg (paper), bg/bg2/surface2 (world, floor, haze), accentDim/accent/accent2 (the sweep), ruleStrong (the cool
ambient). The beam is the key's own colour (a 4300 K blackbody).
Emissive non-accent bits: the shafts (fg, kept faint) and the haze (surface2, kept faint).
"""
from __future__ import annotations

import math
import random

import numpy as np

SHOT = {"frames": [0, 270], "look": "0,45,110,175,215,269", "black_ok": "0-6"}

# ---- scale: a booklet is 0.316 x 0.475 m (the sheets' own aspect), stacks are towering
W, H = 0.316, 0.475
HERO_XY = (0.04, 2.3)  # the nearest stack, on the aisle
HERO_TOP = 0.95  # the hero stack's height (m)
LIFT0, LIFT1 = 150, 269  # the page's flight (frames): it lifts on the VO's 'Millions' (5.0 s)  # the page's flight (frames)
FOV = 30.0  # vertical, degrees
FILL = 0.93  # the page's share of the frame height on the last frame
SHEETS = ["giet_38189_p03", "giet_38179_p03", "giet_38205_p04", "giet_38189_p05", "giet_38179_p06", "giet_38205_p07"]
HERO_SHEET = "hires_38189_p01"
HERO_UNDER = "hires_38189_p02"
HEIGHTS = [1.2, 1.7, 2.2, 2.8, 3.4, 4.0, 4.7, 5.4, 6.2, 7.0]
WINDOW = np.array([-7.0, 16.0, 27.0])  # where the light comes from
WINDOW_AIM = np.array([1.0, 6.0, 0.0])


def sstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def sstep5(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


# ----------------------------------------------------------------------------------------------- camera path

def cam_pose(f: float) -> tuple[np.ndarray, float, float]:
    """(position, pitch deg, yaw deg) at film frame f."""
    t = f / 180.0
    e = sstep(min(t, 1.0))
    tail = max(0.0, f - 180.0) / 90.0  # a creep of a few cm after the dolly ends, so the stop is not dead
    y = -4.2 + 4.2 * e + 0.12 * (1 - (1 - min(tail, 1.0)) ** 2)
    z = 0.34 + 0.46 * sstep(f / 130.0) + 0.38 * sstep((f - 120.0) / 110.0)
    x = 0.05 * math.sin(f / 70.0)
    pitch = 2.0 + 3.2 * sstep(f / 120.0) - 6.4 * sstep((f - 120.0) / 110.0)
    yaw = 1.2 * math.sin(f / 95.0)
    return np.array([x, y, z]), pitch, yaw


def cam_basis(pitch: float, yaw: float):
    """forward, right, up (world) for the camera at pitch/yaw degrees (yaw 0 looks down +y)."""
    p, w = math.radians(pitch), math.radians(yaw)
    fwd = np.array([math.sin(w) * math.cos(p), math.cos(w) * math.cos(p), math.sin(p)])
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    return fwd, right, up


def page_dist_end() -> float:
    return H / (FILL * 2 * math.tan(math.radians(FOV) / 2))


def page_state(f: float):
    """(position, 3x3 rotation matrix with columns = page x, y, normal, curl, progress) at frame f."""
    cp, pitch, yaw = cam_pose(f)
    fwd, right, up = cam_basis(pitch, yaw)
    p = sstep((f - LIFT0) / 125.0)
    # start: lying on the stack top (flat, text up the +y); end: facing the camera
    start = np.array([HERO_XY[0], HERO_XY[1], HERO_TOP + 0.002])
    end_pos = cp + fwd * page_dist_end()
    lift = math.sin(math.pi * min(1.0, p * 1.15)) * 0.22 * (1 - p)  # a rise, then settle
    pos = start + (end_pos - start) * (p ** 1.15) + np.array([0.0, 0.0, 0.0])
    pos[2] += lift + 0.30 * sstep(p / 0.35) * (1 - sstep((p - 0.35) / 0.65))
    pos[0] += 0.10 * math.sin(math.pi * p) * (1 - p)  # a gentle drift sideways
    # orientation: slerp flat -> facing, with a late-leaning turn
    r1 = np.stack([right, up, -fwd], axis=1)
    return pos, r1, p


# ------------------------------------------------------------------------------------------------- the shot

def build(ctx):
    import bpy
    from mathutils import Matrix, Quaternion, Vector

    from lib import materials, rig, theme

    scene, coll = ctx.scene, ctx.scene.collection
    first, last = ctx.f0 - 1, ctx.f1
    rnd = random.Random(7)
    sheets_dir = ctx.film.path("assets/sheets")

    c = scene.cycles
    c.max_bounces, c.diffuse_bounces, c.glossy_bounces = 2, 1, 1
    c.transmission_bounces, c.volume_bounces, c.transparent_max_bounces = 0, 0, 8
    c.caustics_reflective = c.caustics_refractive = False
    c.use_fast_gi = False
    c.denoising_prefilter = "FAST"

    def lin(role, s=1.0):
        r, g, b = theme.linear(role)
        return (r * s, g * s, b * s, 1.0)

    def image(name):
        return bpy.data.images.load(str(sheets_dir / f"{name}.jpg"), check_existing=True)

    # ---- shared bits of node trees
    def fog_mix(nt, shader_out, density=0.07, strength=0.3):
        """Fade a shader into a dim indigo haze with the distance from the camera (a fake, volume-free atmosphere)."""
        cam = nt.nodes.new("ShaderNodeCameraData")
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = -density
        nt.links.new(cam.outputs["View Distance"], mul.inputs[0])
        ex = nt.nodes.new("ShaderNodeMath")
        ex.operation = "EXPONENT"
        nt.links.new(mul.outputs[0], ex.inputs[0])
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        nt.links.new(ex.outputs[0], inv.inputs[1])
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = lin("surface2")
        em.inputs["Strength"].default_value = strength
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(inv.outputs[0], mix.inputs[0])
        nt.links.new(shader_out, mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        return mix.outputs[0]

    def finish(mat, shader_out, fog=True, **kw):
        nt = mat.node_tree
        out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        src = fog_mix(nt, shader_out, **kw) if fog else shader_out
        nt.links.new(src, out.inputs["Surface"])

    # ---- the stacks: one mesh + one material per height, sides banded like paper edges, a sheet on top
    def box_mesh(name, h, seed=0):
        """A stack of booklet bundles (each 3.5-6.5 cm, nudged and turned a little), with per-face attributes: tone
        (each bundle's paper age) and top (1 on the top face of the last bundle, which carries a real sheet)."""
        r = random.Random(1000 + seed)
        hw, hd = W / 2, H / 2
        v, fcs, tone, top, uvs = [], [], [], [], []
        z = 0.0
        while z < h - 1e-4:
            loose = r.random() < 0.07
            t = min(h - z, 0.0025 if loose else r.uniform(0.011, 0.026))
            if h - z - t < 0.02:
                t = h - z
            ox, oy = r.gauss(0, 0.0055), r.gauss(0, 0.0055)
            if loose:
                ox, oy = r.choice((-1, 1)) * r.uniform(0.015, 0.04), r.gauss(0, 0.02)
            a = math.radians(r.gauss(0, 4.0 if loose else 1.6))
            sx, sy = 1 + r.uniform(-0.015, 0.01), 1 + r.uniform(-0.015, 0.01)
            ca, sa = math.cos(a), math.sin(a)
            base = len(v)
            for zz in (z, z + t):
                for px, py in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)):
                    px, py = px * sx, py * sy
                    v.append((ox + px * ca - py * sa, oy + px * sa + py * ca, zz))
            bt = 1.0 if loose else r.uniform(0.78, 1.0)
            is_last = z + t >= h - 1e-4
            for k, fc in enumerate([(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]):
                if k == 0 and z > 0:
                    continue  # the bottom of a bundle sits on the one below
                fcs.append(tuple(base + q for q in fc))
                tone.append(bt)
                top.append(1.0 if (k == 1 and is_last) else 0.0)
                uvs.append([(0, 0), (1, 0), (1, 1), (0, 1)] if (k == 1 and is_last) else [(0.02, 0.02)] * 4)
            z += t
        me = bpy.data.meshes.new(name)
        me.from_pydata(v, [], fcs)
        uvl = me.uv_layers.new(name="uv")
        for poly, uv4 in zip(me.polygons, uvs):
            for k, li in enumerate(poly.loop_indices):
                uvl.data[li].uv = uv4[k]
        for nm, vals in (("tone", tone), ("top", top)):
            at = me.attributes.new(nm, "FLOAT", "FACE")
            at.data.foreach_set("value", vals)
        return me

    def stack_material(i, h):
        mat = bpy.data.materials.new(f"stack{i}")
        mat.use_nodes = True
        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Roughness"].default_value = 0.78
        bsdf.inputs["Specular IOR Level"].default_value = 0.25
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Generated"], sep.inputs[0])
        # paper-edge bands: fine lines (a sheet or two) plus a booklet boundary every ~18 mm
        fine = nt.nodes.new("ShaderNodeTexWave")
        fine.wave_type, fine.bands_direction = "BANDS", "Z"
        fine.inputs["Scale"].default_value = h / 0.0035
        fine.inputs["Distortion"].default_value = 0.0
        fine.inputs["Detail"].default_value = 0.0
        nt.links.new(tc.outputs["Generated"], fine.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[0].color = lin("fgDim", 0.92)
        ramp.color_ramp.elements[1].position = 0.7
        ramp.color_ramp.elements[1].color = lin("fg", 0.98)
        nt.links.new(fine.outputs["Fac"], ramp.inputs["Fac"])
        edge_mul = nt.nodes.new("ShaderNodeMix")
        edge_mul.data_type, edge_mul.blend_type = "RGBA", "MULTIPLY"
        edge_mul.inputs[0].default_value = 1.0
        nt.links.new(ramp.outputs["Color"], edge_mul.inputs[6])
        # bundles of booklets ~11 cm tall, each its own tone and a slightly darker seam between them
        zm = nt.nodes.new("ShaderNodeMath")
        zm.operation, zm.inputs[1].default_value = "MULTIPLY", h / 0.05
        nt.links.new(sep.outputs["Z"], zm.inputs[0])
        fl = nt.nodes.new("ShaderNodeMath")
        fl.operation = "FLOOR"
        nt.links.new(zm.outputs[0], fl.inputs[0])
        fr = nt.nodes.new("ShaderNodeMath")
        fr.operation = "FRACT"
        nt.links.new(zm.outputs[0], fr.inputs[0])
        wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
        wn.noise_dimensions = "2D"
        fo = nt.nodes.new("ShaderNodeMath")
        fo.operation, fo.inputs[1].default_value = "ADD", float(i) * 3.7
        nt.links.new(fl.outputs[0], fo.inputs[0])
        nt.links.new(fo.outputs[0], wn.inputs["Vector"])
        btone = nt.nodes.new("ShaderNodeMapRange")
        btone.inputs[3].default_value, btone.inputs[4].default_value = 0.8, 1.0
        nt.links.new(wn.outputs["Value"], btone.inputs[0])
        seam = nt.nodes.new("ShaderNodeMapRange")
        seam.inputs[1].default_value, seam.inputs[2].default_value = 0.0, 0.07
        seam.inputs[3].default_value, seam.inputs[4].default_value = 0.6, 1.0
        nt.links.new(fr.outputs[0], seam.inputs[0])
        bt2 = nt.nodes.new("ShaderNodeMath")
        bt2.operation = "MULTIPLY"
        tone_at = nt.nodes.new("ShaderNodeAttribute")
        tone_at.attribute_name = "tone"
        nt.links.new(tone_at.outputs["Fac"], bt2.inputs[0])
        bt2.inputs[1].default_value = 1.0
        # fake occlusion: darker toward the floor
        aoz = nt.nodes.new("ShaderNodeMath")
        aoz.operation, aoz.inputs[1].default_value = "MULTIPLY", h
        nt.links.new(sep.outputs["Z"], aoz.inputs[0])
        aor = nt.nodes.new("ShaderNodeMapRange")
        aor.inputs[1].default_value, aor.inputs[2].default_value = 0.0, 2.2
        aor.inputs[3].default_value, aor.inputs[4].default_value = 0.18, 1.0
        nt.links.new(aoz.outputs[0], aor.inputs[0])
        bt3 = nt.nodes.new("ShaderNodeMath")
        bt3.operation = "MULTIPLY"
        nt.links.new(bt2.outputs[0], bt3.inputs[0])
        nt.links.new(aor.outputs[0], bt3.inputs[1])
        cov = nt.nodes.new("ShaderNodeCombineColor")
        for k in range(3):
            nt.links.new(bt3.outputs[0], cov.inputs[k])
        nt.links.new(cov.outputs[0], edge_mul.inputs[7])
        # per-object variation (age, tone) from the object's random number
        info = nt.nodes.new("ShaderNodeObjectInfo")
        tone = nt.nodes.new("ShaderNodeMapRange")
        tone.inputs[3].default_value, tone.inputs[4].default_value = 0.65, 1.0
        nt.links.new(info.outputs["Random"], tone.inputs[0])
        vary = nt.nodes.new("ShaderNodeMix")
        vary.data_type, vary.blend_type = "RGBA", "MULTIPLY"
        vary.inputs[0].default_value = 1.0
        nt.links.new(edge_mul.outputs[2], vary.inputs[6])
        gray = nt.nodes.new("ShaderNodeCombineColor")
        for k in range(3):
            nt.links.new(tone.outputs[0], gray.inputs[k])
        nt.links.new(gray.outputs[0], vary.inputs[7])
        warm = nt.nodes.new("ShaderNodeMix")
        warm.data_type, warm.blend_type = "RGBA", "MULTIPLY"
        warm.inputs[0].default_value = 1.0
        warm.inputs[7].default_value = lin("fg", 0.95)
        nt.links.new(vary.outputs[2], warm.inputs[6])
        # the top face: a real sheet
        img = nt.nodes.new("ShaderNodeTexImage")
        img.image = image(SHEETS[i % len(SHEETS)])
        nt.links.new(tc.outputs["UV"], img.inputs["Vector"])
        isTop = nt.nodes.new("ShaderNodeMath")
        isTop.operation, isTop.inputs[1].default_value = "GREATER_THAN", 0.5
        top_at = nt.nodes.new("ShaderNodeAttribute")
        top_at.attribute_name = "top"
        nt.links.new(top_at.outputs["Fac"], isTop.inputs[0])
        pick = nt.nodes.new("ShaderNodeMix")
        pick.data_type = "RGBA"
        nt.links.new(isTop.outputs[0], pick.inputs[0])
        nt.links.new(warm.outputs[2], pick.inputs[6])
        topc = nt.nodes.new("ShaderNodeMix")
        topc.data_type, topc.blend_type = "RGBA", "MULTIPLY"
        topc.inputs[0].default_value = 1.0
        topc.inputs[7].default_value = lin("fg", 0.78)
        nt.links.new(img.outputs["Color"], topc.inputs[6])
        nt.links.new(topc.outputs[2], pick.inputs[7])
        nt.links.new(pick.outputs[2], bsdf.inputs["Base Color"])
        finish(mat, bsdf.outputs["BSDF"])
        return mat

    lows = []
    for i, h in enumerate((0.38, 0.55, 0.72)):
        me = box_mesh(f"stack_low{i}", h, seed=50 + i)
        me.materials.append(stack_material(i + 2, h))
        lows.append((me, h))
    variants = []
    for i, h in enumerate(HEIGHTS):
        me = box_mesh(f"stack_h{i}", h, seed=i)
        me.materials.append(stack_material(i, h))
        variants.append((me, h))
    # the hero's own stack: a real height, a different sheet on top than the page that leaves it
    hero_me = box_mesh("stack_hero", HERO_TOP, seed=99)
    hm = stack_material(3, HERO_TOP)
    next(n for n in hm.node_tree.nodes if n.bl_idname == "ShaderNodeTexImage").image = image(HERO_UNDER)
    hero_me.materials.append(hm)
    hs = bpy.data.objects.new("stack_hero", hero_me)
    hs.location = (*HERO_XY, 0.0)
    coll.objects.link(hs)

    # ---- the hall: a seeded scatter, dense and tall about the aisle, thinning into the haze
    aisle = 0.62
    placed = 0
    y = -5.5
    while y < 30.0:
        x = -7.0
        while x < 7.0:
            jx, jy = rnd.uniform(-0.22, 0.22), rnd.uniform(-0.25, 0.25)
            px, py = x + jx, y + jy
            gap = abs(px) - aisle
            near_hero = math.hypot(px - HERO_XY[0], py - HERO_XY[1]) < 0.85
            skip = rnd.random() < (0.10 + 0.012 * max(0.0, py))  # gaps, more of them the farther away
            if gap > 0 and not near_hero and not skip:
                hi = min(len(HEIGHTS) - 1, int(abs(rnd.gauss(0.55 - gap * 0.03, 0.3)) * len(HEIGHTS)) + 1)
                if py < 1.0:
                    hi = max(hi, 3)
                me, h = variants[hi]
                if 0.0 < gap < 2.5 and py > -2.0 and rnd.random() < 0.16:
                    me, h = lows[rnd.randrange(len(lows))]
                ob = bpy.data.objects.new("stack", me)
                ob.location = (px, py, 0.0)
                lean = 0.9 + 0.12 * h
                ob.rotation_euler = (math.radians(rnd.uniform(-lean, lean)), math.radians(rnd.uniform(-lean, lean)),
                                     math.radians(rnd.uniform(-7, 7)))
                coll.objects.link(ob)
                placed += 1
            x += rnd.uniform(0.75, 1.1)
        y += rnd.uniform(0.85, 1.2)
    print(f"open: {placed} stacks")

    # ---- the floor
    fme = bpy.data.meshes.new("floor")
    s = 120.0
    fme.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    fm = materials.satin("bg2", roughness=0.55, coat=0.0, sheen=0.0, name="floor")
    b = next(n for n in fm.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    finish(fm, b.outputs["BSDF"], density=0.06, strength=0.45)
    fme.materials.append(fm)
    floor = bpy.data.objects.new("floor", fme)
    coll.objects.link(floor)

    # ---- the hero page: a thin curved slab, a real sheet, the light sweep in the brand gradient on its ink
    NX, NY = 20, 28
    verts = [((i / NX - 0.5) * W, (j / NY - 0.5) * H, 0.0) for j in range(NY + 1) for i in range(NX + 1)]
    faces = [(j * (NX + 1) + i, j * (NX + 1) + i + 1, (j + 1) * (NX + 1) + i + 1, (j + 1) * (NX + 1) + i)
             for j in range(NY) for i in range(NX)]
    pme = bpy.data.meshes.new("page")
    pme.from_pydata(verts, [], faces)
    pme.shade_smooth()
    uvl = pme.uv_layers.new(name="uv")
    for poly in pme.polygons:
        for li in poly.loop_indices:
            vx, vy, _ = pme.vertices[pme.loops[li].vertex_index].co
            uvl.data[li].uv = (vx / W + 0.5, vy / H + 0.5)
    pm = bpy.data.materials.new("page")
    pm.use_nodes = True
    nt = pm.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    bsdf.inputs["Subsurface Weight"].default_value = 0.0
    uvn = nt.nodes.new("ShaderNodeTexCoord")
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = image(HERO_SHEET)
    img.interpolation = "Cubic"
    img.extension = "EXTEND"
    nt.links.new(uvn.outputs["UV"], img.inputs["Vector"])
    paper = nt.nodes.new("ShaderNodeMix")
    paper.data_type, paper.blend_type = "RGBA", "MULTIPLY"
    paper.inputs[0].default_value = 1.0
    paper.inputs[7].default_value = lin("fg", 0.97)
    nt.links.new(img.outputs["Color"], paper.inputs[6])
    nt.links.new(paper.outputs[2], bsdf.inputs["Base Color"])
    bump_n = nt.nodes.new("ShaderNodeTexNoise")
    bump_n.inputs["Scale"].default_value = 900.0
    bump_n.inputs["Detail"].default_value = 3.0
    nt.links.new(uvn.outputs["UV"], bump_n.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.0006
    nt.links.new(bump_n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    # ink mask from the scan's luminance, and the sweep band along u + 0.35 v
    ink = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(img.outputs["Color"], ink.inputs["Color"])
    inkm = nt.nodes.new("ShaderNodeMapRange")
    inkm.inputs[1].default_value, inkm.inputs[2].default_value = 0.88, 0.45
    nt.links.new(ink.outputs[0], inkm.inputs[0])
    sepuv = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uvn.outputs["UV"], sepuv.inputs[0])
    diag = nt.nodes.new("ShaderNodeMath")
    diag.operation = "MULTIPLY_ADD"
    diag.inputs[1].default_value = 0.35
    nt.links.new(sepuv.outputs["Y"], diag.inputs[0])
    nt.links.new(sepuv.outputs["X"], diag.inputs[2])
    pos_v = nt.nodes.new("ShaderNodeValue")
    pos_v.label = "sweep"
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    nt.links.new(diag.outputs[0], sub.inputs[0])
    nt.links.new(pos_v.outputs[0], sub.inputs[1])
    # band profile: exp(-(d/w)^2), asymmetric colour ramp across it (indigo trailing, magenta, coral leading)
    sq = nt.nodes.new("ShaderNodeMath")
    sq.operation = "MULTIPLY"
    nt.links.new(sub.outputs[0], sq.inputs[0])
    nt.links.new(sub.outputs[0], sq.inputs[1])
    neg = nt.nodes.new("ShaderNodeMath")
    neg.operation, neg.inputs[1].default_value = "MULTIPLY", -1.0 / (0.075 ** 2)
    nt.links.new(sq.outputs[0], neg.inputs[0])
    band = nt.nodes.new("ShaderNodeMath")
    band.operation = "EXPONENT"
    nt.links.new(neg.outputs[0], band.inputs[0])
    gradpos = nt.nodes.new("ShaderNodeMapRange")
    gradpos.inputs[1].default_value, gradpos.inputs[2].default_value = -0.16, 0.16
    nt.links.new(sub.outputs[0], gradpos.inputs[0])
    grad = nt.nodes.new("ShaderNodeValToRGB")
    grad.color_ramp.elements[0].position, grad.color_ramp.elements[0].color = 0.0, lin("accentDim")
    mid = grad.color_ramp.elements.new(0.5)
    mid.color = lin("accent")
    grad.color_ramp.elements[2].position, grad.color_ramp.elements[2].color = 1.0, lin("accent2")
    nt.links.new(gradpos.outputs[0], grad.inputs["Fac"])
    amt = nt.nodes.new("ShaderNodeMath")  # band x (a soft paper wash + the ink lit up)
    amt.operation = "MULTIPLY_ADD"
    amt.inputs[1].default_value, amt.inputs[2].default_value = 2.6, 0.22
    nt.links.new(inkm.outputs[0], amt.inputs[0])
    amt2 = nt.nodes.new("ShaderNodeMath")
    amt2.operation = "MULTIPLY"
    nt.links.new(band.outputs[0], amt2.inputs[0])
    nt.links.new(amt.outputs[0], amt2.inputs[1])
    strength = nt.nodes.new("ShaderNodeMath")
    strength.operation, strength.inputs[1].default_value = "MULTIPLY", 2.3
    nt.links.new(amt2.outputs[0], strength.inputs[0])
    nt.links.new(grad.outputs["Color"], bsdf.inputs["Emission Color"])
    nt.links.new(strength.outputs[0], bsdf.inputs["Emission Strength"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    pme.materials.append(pm)
    page = bpy.data.objects.new("page", pme)
    coll.objects.link(page)
    sol = page.modifiers.new("slab", "SOLIDIFY")
    sol.thickness, sol.offset = 0.0007, 0.0
    bend = page.modifiers.new("curl", "SIMPLE_DEFORM")
    bend.deform_method, bend.deform_axis = "BEND", "X"
    bend.angle = 0.0
    twist = page.modifiers.new("twist", "SIMPLE_DEFORM")
    twist.deform_method, twist.deform_axis = "TWIST", "Y"
    twist.angle = 0.0
    page.rotation_mode = "QUATERNION"

    # ---- the camera
    cam = rig.engine_camera("camera", fstop=2.0, size=ctx.size)
    cam.data.lens = rig.lens_mm(FOV)
    cam.data.clip_start, cam.data.clip_end = 0.05, 90.0
    scene.camera = cam

    # ---- lights: the high slit (spot + a visible slit), an indigo fill from above, a key that follows the camera
    def aim(ob, target):
        ob.rotation_euler = (Vector(target) - ob.location).to_track_quat("-Z", "Y").to_euler()

    spot_d = bpy.data.lights.new("slit", "SPOT")
    spot_d.energy, spot_d.spot_size, spot_d.spot_blend, spot_d.shadow_soft_size = 120000.0, math.radians(30), 0.55, 0.9
    spot_d.use_temperature, spot_d.temperature = True, 4300
    spot = bpy.data.objects.new("slit", spot_d)
    spot.location = tuple(WINDOW)
    coll.objects.link(spot)
    aim(spot, WINDOW_AIM)
    # the slit itself, a bright narrow rectangle far down the hall so the glare reads as a window
    win_d = bpy.data.lights.new("window", "AREA")
    win_d.shape, win_d.size, win_d.size_y, win_d.energy = "RECTANGLE", 1.6, 11.0, 9000.0
    win_d.use_temperature, win_d.temperature = True, 4800
    win = bpy.data.objects.new("window", win_d)
    win.location = (-2.0, 52.0, 9.0)
    coll.objects.link(win)
    aim(win, (0.0, 0.0, 3.0))
    fill_d = bpy.data.lights.new("indigo", "AREA")
    fill_d.shape, fill_d.size, fill_d.size_y, fill_d.energy = "RECTANGLE", 14.0, 40.0, 9000.0
    fill_d.color = lin("ruleStrong")[:3]
    fill = bpy.data.objects.new("indigo", fill_d)
    fill.location = (0.0, 18.0, 16.0)
    coll.objects.link(fill)
    aim(fill, (0.0, 18.0, 0.0))
    key_d = bpy.data.lights.new("page_key", "AREA")
    key_d.shape, key_d.size, key_d.size_y = "RECTANGLE", 0.9, 0.9
    key_d.use_temperature, key_d.temperature = True, 4500
    key = bpy.data.objects.new("page_key", key_d)
    coll.objects.link(key)
    lit = bpy.data.collections.new("page_key_receivers")  # light linking: the key lights the page alone
    lit.objects.link(page)
    key.light_linking.receiver_collection = lit

    cf_d = bpy.data.lights.new("cam_fill", "AREA")
    cf_d.shape, cf_d.size, cf_d.size_y, cf_d.energy = "RECTANGLE", 2.5, 2.5, 90.0
    cf_d.color = lin("ruleStrong")[:3]  # the cool side: indigo ambient against the warm key
    camfill = bpy.data.objects.new("cam_fill", cf_d)
    coll.objects.link(camfill)

    # ---- shafts: camera-only emissive ribbons along the beam, crossed, fading along their length and across
    d = (WINDOW_AIM - WINDOW)
    d = d / np.linalg.norm(d)
    h_dir = np.cross(d, [0, 0, 1.0])
    h_dir /= np.linalg.norm(h_dir)
    v_dir = np.cross(h_dir, d)
    length = 30.0

    shaft_gain = []  # (socket, strength): the beam fades as the page takes the frame

    def shaft_material(strength, seed):
        mat = bpy.data.materials.new("shaft")
        mat.use_nodes = True
        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        mix = nt.nodes.new("ShaderNodeMixShader")
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        em = nt.nodes.new("ShaderNodeEmission")
        bb = nt.nodes.new("ShaderNodeBlackbody")  # the beam is the key's own light: its colour temperature
        bb.inputs["Temperature"].default_value = 4300.0
        nt.links.new(bb.outputs[0], em.inputs["Color"])
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["UV"], sep.inputs[0])
        # across: sin(pi u)^2 ; along: v * (1-v)^0.5 fade (a hot start, a long fall-off)
        a = nt.nodes.new("ShaderNodeMath")
        a.operation, a.inputs[1].default_value = "MULTIPLY", math.pi
        nt.links.new(sep.outputs["X"], a.inputs[0])
        sn = nt.nodes.new("ShaderNodeMath")
        sn.operation = "SINE"
        nt.links.new(a.outputs[0], sn.inputs[0])
        sq = nt.nodes.new("ShaderNodeMath")
        sq.operation, sq.inputs[1].default_value = "POWER", 3.0
        nt.links.new(sn.outputs[0], sq.inputs[0])
        al = nt.nodes.new("ShaderNodeMath")
        al.operation, al.inputs[1].default_value = "POWER", 0.6
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        nt.links.new(sep.outputs["Y"], inv.inputs[1])
        nt.links.new(inv.outputs[0], al.inputs[0])
        ml = nt.nodes.new("ShaderNodeMath")
        ml.operation = "MULTIPLY"
        nt.links.new(sq.outputs[0], ml.inputs[0])
        nt.links.new(al.outputs[0], ml.inputs[1])
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 5.0
        nz.noise_dimensions = "4D"
        nz.inputs["W"].default_value = seed
        nt.links.new(tc.outputs["UV"], nz.inputs["Vector"])
        nzr = nt.nodes.new("ShaderNodeMapRange")
        nzr.inputs[1].default_value, nzr.inputs[2].default_value = 0.35, 0.75
        nzr.inputs[3].default_value, nzr.inputs[4].default_value = 0.35, 1.0
        nt.links.new(nz.outputs["Fac"], nzr.inputs[0])
        m2 = nt.nodes.new("ShaderNodeMath")
        m2.operation = "MULTIPLY"
        nt.links.new(ml.outputs[0], m2.inputs[0])
        nt.links.new(nzr.outputs[0], m2.inputs[1])
        # near-camera fade (view distance 0.5..3 m)
        cd = nt.nodes.new("ShaderNodeCameraData")
        nr = nt.nodes.new("ShaderNodeMapRange")
        nr.inputs[1].default_value, nr.inputs[2].default_value = 0.8, 4.0
        nt.links.new(cd.outputs["View Distance"], nr.inputs[0])
        m3 = nt.nodes.new("ShaderNodeMath")
        m3.operation = "MULTIPLY"
        nt.links.new(m2.outputs[0], m3.inputs[0])
        nt.links.new(nr.outputs[0], m3.inputs[1])
        k = nt.nodes.new("ShaderNodeMath")
        k.operation, k.inputs[1].default_value = "MULTIPLY", strength
        shaft_gain.append((k.inputs[1], strength))
        nt.links.new(m3.outputs[0], k.inputs[0])
        em.inputs["Strength"].default_value = 1.0
        nt.links.new(k.outputs[0], mix.inputs[0])
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        # the mix factor drives how much emission: scale the emission colour by the factor's small value
        return mat

    shaft_specs = [(-1.4, 1.6, 0.55), (-0.3, 2.4, 0.8), (0.9, 1.2, 0.6), (1.9, 2.0, 0.5), (3.2, 1.6, 0.4), (0.4, 4.5, 0.25)]
    for si, (off, wdt, stg) in enumerate(shaft_specs):
        for kind, wdir in (("h", h_dir), ("v", v_dir)):
            me = bpy.data.meshes.new(f"shaft{si}{kind}")
            o = WINDOW + h_dir * off
            p = [o - wdir * wdt / 2, o + wdir * wdt / 2, o + wdir * wdt / 2 + d * length, o - wdir * wdt / 2 + d * length]
            me.from_pydata([tuple(q) for q in p], [], [(0, 1, 2, 3)])
            uvs = me.uv_layers.new(name="uv")
            for li, uvp in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
                uvs.data[li].uv = uvp
            me.materials.append(shaft_material(stg, si * 1.7 + (0.4 if kind == "v" else 0.0)))
            ob = bpy.data.objects.new(f"shaft{si}{kind}", me)
            coll.objects.link(ob)
            ob.visible_shadow = ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = False
            ob.visible_volume_scatter = False

    # ---- dust: small spheres drifting in the beam (lit by it: only the ones in the light show)
    ico = bpy.data.meshes.new("mote")
    import bmesh

    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    bm.to_mesh(ico)
    bm.free()
    mm = materials.satin("fg", roughness=0.4, coat=0.0, sheen=0.5, name="mote")
    ico.materials.append(mm)
    def mote(pos, r, drift, ph):
        ob = bpy.data.objects.new("mote", ico)
        ob.scale = (r, r, r)
        coll.objects.link(ob)
        for f in (first, ctx.f0 + 90, ctx.f0 + 180, last):
            tt = (f - first) / 30.0
            ob.location = (pos[0] + drift[0] * tt + 0.04 * math.sin(tt * 1.3 + ph), pos[1] + drift[1] * tt,
                           pos[2] + drift[2] * tt + 0.03 * math.cos(tt * 0.9 + ph))
            ob.keyframe_insert("location", frame=f)

    for mi in range(420):  # along the beam, inside its cone, where the camera passes
        u = rnd.uniform(0.62, 1.0)
        c0 = WINDOW + (WINDOW_AIM - WINDOW) * u
        off = h_dir * rnd.gauss(0, 1.3) + v_dir * rnd.gauss(0, 1.3)
        pos = c0 + off
        if not (-2.0 < pos[1] < 14.0 and 0.15 < pos[2] < 6.0):
            continue
        mote(pos, rnd.uniform(0.003, 0.009), (rnd.uniform(-0.03, 0.03), rnd.uniform(-0.01, 0.05), rnd.uniform(-0.04, 0.02)),
             rnd.uniform(0, 6.28))
    for mi in range(60):  # around where the page ends: out of focus behind it
        pos = (rnd.uniform(-1.2, 1.2), rnd.uniform(1.4, 5.0), rnd.uniform(0.6, 2.2))
        mote(pos, rnd.uniform(0.004, 0.01), (rnd.uniform(-0.02, 0.02), rnd.uniform(-0.01, 0.02), rnd.uniform(-0.02, 0.01)),
             rnd.uniform(0, 6.28))

    # ---- the fade from black: a camera-only black plane in front of the lens whose opacity is keyed
    fade_me = bpy.data.meshes.new("fade")
    fade_me.from_pydata([(-1, -1, -0.12), (1, -1, -0.12), (1, 1, -0.12), (-1, 1, -0.12)], [], [(0, 1, 2, 3)])
    fm2 = bpy.data.materials.new("fade")
    fm2.use_nodes = True
    fnt = fm2.node_tree
    for n in list(fnt.nodes):
        fnt.nodes.remove(n)
    fout = fnt.nodes.new("ShaderNodeOutputMaterial")
    fmix = fnt.nodes.new("ShaderNodeMixShader")
    ftr = fnt.nodes.new("ShaderNodeBsdfTransparent")
    fem = fnt.nodes.new("ShaderNodeEmission")
    fem.inputs["Color"].default_value = (0, 0, 0, 1)
    fnt.links.new(ftr.outputs[0], fmix.inputs[1])
    fnt.links.new(fem.outputs[0], fmix.inputs[2])
    fnt.links.new(fmix.outputs[0], fout.inputs["Surface"])
    fade_me.materials.append(fm2)
    fade = bpy.data.objects.new("fade", fade_me)
    fade.parent = cam
    fade.visible_shadow = fade.visible_diffuse = fade.visible_glossy = fade.visible_transmission = False
    coll.objects.link(fade)

    # ---- animation: everything a function of the frame, keyed on every frame (plus one beyond each end)
    focus_ex = [0.0]
    for f in range(first, last + 1):
        cp, pitch, yaw = cam_pose(f)
        cam.location = tuple(cp)
        cam.rotation_euler = (math.radians(90 + pitch), 0.0, math.radians(yaw))
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
        fwd, right, up = cam_basis(pitch, yaw)

        pos, r1, p = page_state(f)
        # the page's orientation: flat -> facing, turning gracefully (a slight roll and yaw in between)
        q0 = Quaternion((1, 0, 0, 0))
        q1 = Matrix(r1.tolist()).to_quaternion()
        qm = q0.slerp(q1, sstep5(p))
        wob = math.sin(math.pi * min(1.0, p * 1.1)) * (1 - p)
        qm = qm @ Quaternion((0, 0, 1), 0.35 * wob) @ Quaternion((1, 0, 0), -0.12 * wob)
        page.location = tuple(pos)
        page.rotation_quaternion = qm
        page.keyframe_insert("location", frame=f)
        page.keyframe_insert("rotation_quaternion", frame=f)
        bend.angle = 0.3 * math.sin(math.pi * min(1.0, p * 1.05)) ** 1.5 * (1 - p) + 0.03
        bend.keyframe_insert("angle", frame=f)
        twist.angle = 0.08 * wob
        twist.keyframe_insert("angle", frame=f)
        pos_v.outputs[0].default_value = -0.4 + 1.9 * sstep5((f - 205.0) / 60.0)
        pos_v.outputs[0].keyframe_insert("default_value", frame=f)

        camfill.location = tuple(cp + up * 0.6 - fwd * 0.5)
        camfill.rotation_euler = (math.radians(90 + pitch), 0.0, math.radians(yaw))
        camfill.keyframe_insert("location", frame=f)
        camfill.keyframe_insert("rotation_euler", frame=f)
        # key light on the page, rising with it
        kp = cp + right * -0.7 + up * 0.55 - fwd * 0.2
        key.location = tuple(kp)
        key.rotation_euler = (Vector(pos.tolist()) - Vector(kp.tolist())).to_track_quat("-Z", "Y").to_euler()
        key.keyframe_insert("location", frame=f)
        key.keyframe_insert("rotation_euler", frame=f)
        key_d.energy = 0.0 + 110.0 * sstep((f - LIFT0 + 10.0) / 80.0)
        key_d.keyframe_insert("energy", frame=f)
        dim = 1.0 - 0.75 * sstep((f - LIFT0 - 25.0) / 80.0)
        cf_d.energy = 90.0 * dim * dim
        for sock, base in shaft_gain:
            sock.default_value = base * (0.15 + 0.85 * dim)
            sock.keyframe_insert("default_value", frame=f)
        cf_d.keyframe_insert("energy", frame=f)
        fill_d.energy = 9000.0 * (0.25 + 0.75 * dim)
        spot_d.energy = 120000.0 * (0.5 + 0.5 * dim)
        spot_d.keyframe_insert("energy", frame=f)
        fill_d.keyframe_insert("energy", frame=f)

        # focus: on the middle of the hall, then the hero stack, then the page, which lands sharp
        dist_page = float(np.linalg.norm(pos - cp))
        stack = float(np.linalg.norm(np.array([HERO_XY[0], HERO_XY[1], HERO_TOP]) - cp))
        far = 7.0 - 3.6 * sstep(f / 130.0)
        fd = far + (stack - far) * sstep((f - 90.0) / 80.0)
        fd = fd + (dist_page - fd) * sstep((f - LIFT0 - 2.0) / 70.0)
        fd += 0.35 * (1 - sstep((f - LIFT0 - 55.0) / 55.0)) * sstep((f - LIFT0 - 2.0) / 20.0)  # lags, then locks on
        cam.data.dof.focus_distance = fd
        cam.data.dof.keyframe_insert("focus_distance", frame=f)

        # black fade: opacity 1 -> 0 over frames 6..42 (the mix factor is 0 = transparent, 1 = black)
        fmix.inputs[0].default_value = 1.0 - sstep((f - 6.0) / 36.0)
        fmix.inputs[0].keyframe_insert("default_value", frame=f)
        fade.location = (0.0, 0.0, 0.0)
    fade.scale = (0.3, 0.3, 1.0)

    # linear keys on the straight-line data would be fine; everything keyed per frame so the interpolation is moot
    # (the shaft materials' emission is the Mix factor above times the colour; the fade plane is camera-only)

    # world: nearly black, a trace of indigo so the far haze has somewhere to go
    from lib import lights

    lights.world_color("bg2", 0.8)
