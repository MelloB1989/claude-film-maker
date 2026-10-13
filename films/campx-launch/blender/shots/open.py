"""open: the cold open (9 s). Near-total darkness; at f24 one hard, narrow shaft of light snaps on like a stage light and
slices down through drifting dust onto the nearest stack of answer scripts. On 'thousands of answer scripts' (f95) the
camera cranes up and back (fast, easing out) to show the true scale, rows of stacks to a vanishing point, while more
shafts switch on in sequence down the hall like a cathedral lighting up; loose pages drift down through the beams. On
'Millions of handwritten pages' (f151) the hero page lifts off the nearest stack and flies toward the camera as the
camera pushes in to meet it, with a hard rack focus and a backlit rim on its edges; by f269 it fills the frame,
face-on, evenly lit and razor sharp, ready for the match cut.

Cheap by design (<= 3 s per 1920x1080 frame at 96 spp on an RTX 4090): the stacks are a dozen shared meshes instanced
a couple of thousand times, the shafts are spot lights plus camera-only emissive cones (no volumes), the dust is small
spheres lit by the beams, and the haze is a depth fade in the materials. Everything is seeded and every animated value
is a pure function of the frame, so a re-render is identical.

Roles used: fg (paper), bg/bg2/surface2 (world, floor, haze), accentDim/accent/accent2 (the thin rim sweep on the hero
page's edge), ruleStrong (the cool ambient). The beams are a 4300 K blackbody.
Emissive non-accent bits: the beam cones (blackbody, camera-only) and the haze (surface2, kept faint).
"""
from __future__ import annotations

import math
import random

import numpy as np

SHOT = {"frames": [0, 270], "look": "15,40,100,130,170,230,269", "black_ok": "0-23"}

# ---- scale: a booklet is 0.316 x 0.475 m (the sheets' own aspect)
W, H = 0.316, 0.475
HERO_XY = (0.04, 2.3)  # the nearest stack, on the aisle
HERO_TOP = 0.95  # the hero stack's height (m)
LIFT0, LIFT1 = 151, 258  # the page's flight (frames): it lifts on the VO's 'Millions' (5.03 s)
FOV = 30.0  # vertical, degrees
FILL = 0.93  # the page's share of the frame height at the end
SHEETS = ["giet_38189_p03", "giet_38179_p03", "giet_38205_p04", "giet_38189_p05", "giet_38179_p06", "giet_38205_p07"]
HERO_SHEET = "hires_38189_p01"
HERO_UNDER = "hires_38189_p02"
HEIGHTS = [0.75, 0.95, 1.15, 1.35, 1.6, 1.85, 2.1, 2.4, 2.8, 3.3]
BEAM = np.array([0.30, -0.35, -1.0]) / np.linalg.norm([0.30, -0.35, -1.0])  # shafts fall toward the camera (backlight)
BEAM_TOP = 14.0  # the height the shafts come from
FIRST_ON = 24  # the first shaft snaps on
KEY_W = 60.0  # the page key at full (W)
# the shafts: (x, y, z of the spot they land on, switch-on frame); the first is the hero stack's
SHAFTS = [(HERO_XY[0], HERO_XY[1], HERO_TOP, FIRST_ON)] + [
    (x, y, 0.0, 97 + 5 * i)
    for i, (x, y) in enumerate([(-0.9, 5.6), (1.1, 9.0), (-0.2, 12.8), (1.6, 17.0), (-1.4, 21.5), (0.5, 27.0),
                                (-0.8, 33.5), (1.3, 41.0), (-0.3, 50.0)])
]
# camera keys: position and look target
P0, T0 = np.array([0.16, 0.42, 1.10]), np.array([0.04, 2.3, 0.97])
P1, T1 = np.array([0.15, 0.72, 1.14]), np.array([0.04, 2.3, 1.00])
P2, T2 = np.array([0.22, -5.2, 4.2]), np.array([0.0, 13.0, 0.2])
P3, T3 = np.array([0.08, -0.35, 1.72]), np.array([0.05, 8.0, 1.36])
CRANE0, CRANE1 = 95, 150
PUSH0, PUSH1 = 151, 262


def sstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def sstep5(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


def crane_ease(x: float, a: float = 0.08) -> float:
    """Fast then a long ease-out (a cubic out), with a few frames of ease-in so the start is not a jolt."""
    x = min(1.0, max(0.0, x))
    xe = (x * x / (2 * a) if x < a else x - a / 2) / (1 - a / 2)
    return 1 - (1 - xe) ** 3


def shaft_on(f: float, f_on: float) -> float:
    """A stage light: a fast ease-in over ~5 frames, a touch of overshoot, settle."""
    x = (f - f_on) / 5.0
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0 + 0.06 * math.exp(-(x - 1) * 1.2) * (1 if x < 4 else 0)
    return 1 - (1 - x) ** 3


# ----------------------------------------------------------------------------------------------- camera path

def cam_look(f: float) -> tuple[np.ndarray, np.ndarray]:
    if f < CRANE0:
        e = max(0.0, f) / CRANE0
        return P0 + (P1 - P0) * e, T0 + (T1 - T0) * e
    if f < PUSH0:
        e = crane_ease((f - CRANE0) / (CRANE1 - CRANE0))
        return P1 + (P2 - P1) * e, T1 + (T2 - T1) * e
    e = sstep5((f - PUSH0) / (PUSH1 - PUSH0))
    tail = max(0.0, f - PUSH1) / 20.0  # a creep of a centimetre or two so the stop is not dead
    pos = P2 + (P3 - P2) * e
    pos = pos + (T3 - P3) / np.linalg.norm(T3 - P3) * 0.015 * min(tail, 1.0)
    return pos, T2 + (T3 - T2) * e


def cam_pose(f: float) -> tuple[np.ndarray, float, float]:
    """(position, pitch deg, yaw deg) at film frame f."""
    p, t = cam_look(f)
    d = t - p
    pitch = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
    yaw = math.degrees(math.atan2(d[0], d[1]))
    return p, pitch, -yaw


def cam_basis(pitch: float, yaw: float):
    """forward, right, up (world) for the camera at pitch/yaw degrees (yaw 0 looks down +y; Blender's z rotation)."""
    p, w = math.radians(pitch), math.radians(-yaw)
    fwd = np.array([math.sin(w) * math.cos(p), math.cos(w) * math.cos(p), math.sin(p)])
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    return fwd, right, up


def page_dist_end() -> float:
    return H / (FILL * 2 * math.tan(math.radians(FOV) / 2))


def page_state(f: float):
    """(position, 3x3 rotation matrix with columns = page x, y, normal, progress) at frame f."""
    cp, pitch, yaw = cam_pose(f)
    fwd, right, up = cam_basis(pitch, yaw)
    p = sstep5((f - LIFT0) / (LIFT1 - LIFT0))
    start = np.array([HERO_XY[0], HERO_XY[1], HERO_TOP + 0.002])
    end_pos = cp + fwd * page_dist_end()
    q = p ** 1.3
    pos = start + (end_pos - start) * q
    pos[2] += 0.32 * math.sin(math.pi * min(1.0, p * 1.25)) * (1 - p) ** 0.6  # it lifts first, then flies
    pos[0] += 0.08 * math.sin(math.pi * p) * (1 - p)  # a gentle drift sideways
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

    fog_gain = []  # (socket, strength): the haze comes up with the light

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
        fog_gain.append((em.inputs["Strength"], strength))
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

    # ---- the hall: rows of stacks either side of the aisle, running to a vanishing point in the haze
    aisle = 0.62
    placed = 0
    row = 0
    y = -6.5
    while y < 72.0:
        x0 = 0.42 * (row % 2)
        for side in (-1, 1):
            x = aisle + 0.3 + (x0 if side > 0 else 0.42 - x0)
            while x < 13.0:
                px, py = side * (x + rnd.uniform(-0.05, 0.05)), y + rnd.uniform(-0.06, 0.06)
                near_hero = math.hypot(px - HERO_XY[0], py - HERO_XY[1]) < 0.85
                if not near_hero and rnd.random() > 0.05:
                    gap = abs(px) - aisle
                    hi = int(round(rnd.gauss(5.0 if gap < 1.5 else 3.6, 1.8)))
                    if rnd.random() < 0.05:
                        hi = len(HEIGHTS) - 1  # the odd tower
                    me, h = variants[min(len(HEIGHTS) - 1, max(0, hi))]
                    if gap < 2.5 and rnd.random() < 0.10:
                        me, h = lows[rnd.randrange(len(lows))]
                    ob = bpy.data.objects.new("stack", me)
                    ob.location = (px, py, 0.0)
                    lean = 0.6 + 0.12 * h
                    ob.rotation_euler = (math.radians(rnd.uniform(-lean, lean)), math.radians(rnd.uniform(-lean, lean)),
                                         math.radians(rnd.uniform(-5, 5)))
                    coll.objects.link(ob)
                    placed += 1
                x += 0.84
        y += 0.98
        row += 1
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

    # ---- math-node helper
    def mth(nt, op, a, b=None, clamp=False):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        for k, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[k].default_value = float(v)
            else:
                nt.links.new(v, n.inputs[k])
        return n.outputs[0]

    # ---- the hero page: a thin slab, a real sheet with its ink deepened; the brand gradient is only a thin rim
    # light gliding along the page's edge, never a wash
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
    bsdf.inputs["Roughness"].default_value = 0.72
    bsdf.inputs["Specular IOR Level"].default_value = 0.2
    bsdf.inputs["Subsurface Weight"].default_value = 0.0
    uvn = nt.nodes.new("ShaderNodeTexCoord")
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = image(HERO_SHEET)
    img.interpolation = "Cubic"
    img.extension = "EXTEND"
    nt.links.new(uvn.outputs["UV"], img.inputs["Vector"])
    # ink mask from the scan's luminance: the ink is pushed darker so the handwriting reads crisp at any exposure
    ink = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(img.outputs["Color"], ink.inputs["Color"])
    inkm = nt.nodes.new("ShaderNodeMapRange")
    inkm.inputs[1].default_value, inkm.inputs[2].default_value = 0.80, 0.30
    nt.links.new(ink.outputs[0], inkm.inputs[0])
    deepen = mth(nt, "MULTIPLY_ADD", inkm.outputs[0], -0.6)
    deepen.node.inputs[2].default_value = 1.0
    dk = nt.nodes.new("ShaderNodeMix")
    dk.data_type, dk.blend_type = "RGBA", "MULTIPLY"
    dk.inputs[0].default_value = 1.0
    nt.links.new(img.outputs["Color"], dk.inputs[6])
    dkc = nt.nodes.new("ShaderNodeCombineColor")
    for k in range(3):
        nt.links.new(deepen, dkc.inputs[k])
    nt.links.new(dkc.outputs[0], dk.inputs[7])
    paper = nt.nodes.new("ShaderNodeMix")
    paper.data_type, paper.blend_type = "RGBA", "MULTIPLY"
    paper.inputs[0].default_value = 1.0
    paper.inputs[7].default_value = lin("fg", 0.97)
    nt.links.new(dk.outputs[2], paper.inputs[6])
    nt.links.new(paper.outputs[2], bsdf.inputs["Base Color"])
    bump_n = nt.nodes.new("ShaderNodeTexNoise")
    bump_n.inputs["Scale"].default_value = 900.0
    bump_n.inputs["Detail"].default_value = 3.0
    nt.links.new(uvn.outputs["UV"], bump_n.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    bump.inputs["Distance"].default_value = 0.0004
    nt.links.new(bump_n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    # the rim: distance to the page's nearest edge (m), a band ~2.5 mm wide, times a sweep gliding along u + 0.35 v
    sepuv = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uvn.outputs["UV"], sepuv.inputs[0])
    u, v = sepuv.outputs["X"], sepuv.outputs["Y"]
    du = mth(nt, "MULTIPLY", mth(nt, "MINIMUM", u, mth(nt, "SUBTRACT", 1.0, u)), W)
    dv = mth(nt, "MULTIPLY", mth(nt, "MINIMUM", v, mth(nt, "SUBTRACT", 1.0, v)), H)
    dedge = mth(nt, "MINIMUM", du, dv)
    edge = mth(nt, "SUBTRACT", 1.0, mth(nt, "DIVIDE", dedge, 0.0025), clamp=True)
    edge = mth(nt, "MULTIPLY", edge, edge)
    pos_v = nt.nodes.new("ShaderNodeValue")
    pos_v.label = "sweep"
    diag = mth(nt, "MULTIPLY_ADD", v, 0.35)
    nt.links.new(u, diag.node.inputs[2])
    sub = mth(nt, "SUBTRACT", diag, pos_v.outputs[0])
    band = mth(nt, "EXPONENT", mth(nt, "MULTIPLY", mth(nt, "MULTIPLY", sub, sub), -1.0 / (0.16 ** 2)))
    gradpos = nt.nodes.new("ShaderNodeMapRange")
    gradpos.inputs[1].default_value, gradpos.inputs[2].default_value = -0.3, 0.3
    nt.links.new(sub, gradpos.inputs[0])
    grad = nt.nodes.new("ShaderNodeValToRGB")
    grad.color_ramp.elements[0].position, grad.color_ramp.elements[0].color = 0.0, lin("accentDim")
    mid = grad.color_ramp.elements.new(0.5)
    mid.color = lin("accent")
    grad.color_ramp.elements[2].position, grad.color_ramp.elements[2].color = 1.0, lin("accent2")
    nt.links.new(gradpos.outputs[0], grad.inputs["Fac"])
    rim_k = nt.nodes.new("ShaderNodeValue")
    rim_k.label = "rim gain"
    strength = mth(nt, "MULTIPLY", mth(nt, "MULTIPLY", edge, band), rim_k.outputs[0])
    nt.links.new(grad.outputs["Color"], bsdf.inputs["Emission Color"])
    nt.links.new(strength, bsdf.inputs["Emission Strength"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    pme.materials.append(pm)
    page = bpy.data.objects.new("page", pme)
    coll.objects.link(page)
    sol = page.modifiers.new("slab", "SOLIDIFY")
    sol.thickness, sol.offset = 0.0011, 0.0
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
    cam.data.clip_start, cam.data.clip_end = 0.05, 110.0
    scene.camera = cam

    # ---- lights: an indigo fill from above (the shadows' colour), a soft key that follows the camera and lights the
    # page alone, a backlight behind the page for its rim, a faint cool fill at the camera
    def aim(ob, target):
        ob.rotation_euler = (Vector(tuple(target)) - ob.location).to_track_quat("-Z", "Y").to_euler()

    fill_d = bpy.data.lights.new("indigo", "AREA")
    fill_d.shape, fill_d.size, fill_d.size_y = "RECTANGLE", 18.0, 60.0
    fill_d.color = lin("ruleStrong")[:3]
    fill = bpy.data.objects.new("indigo", fill_d)
    fill.location = (0.0, 25.0, 18.0)
    coll.objects.link(fill)
    aim(fill, (0.0, 25.0, 0.0))

    page_only = bpy.data.collections.new("page_receivers")  # light linking: these light the page alone
    page_only.objects.link(page)
    key_d = bpy.data.lights.new("page_key", "AREA")
    key_d.shape, key_d.size, key_d.size_y = "RECTANGLE", 1.8, 1.8
    key_d.use_temperature, key_d.temperature = True, 4800
    key = bpy.data.objects.new("page_key", key_d)
    coll.objects.link(key)
    key.light_linking.receiver_collection = page_only
    back_d = bpy.data.lights.new("page_back", "AREA")
    back_d.shape, back_d.size, back_d.size_y = "RECTANGLE", 0.5, 0.5
    back_d.use_temperature, back_d.temperature = True, 4300
    back = bpy.data.objects.new("page_back", back_d)
    coll.objects.link(back)
    back.light_linking.receiver_collection = page_only

    cf_d = bpy.data.lights.new("cam_fill", "AREA")
    cf_d.shape, cf_d.size, cf_d.size_y = "RECTANGLE", 2.5, 2.5
    cf_d.color = lin("ruleStrong")[:3]
    camfill = bpy.data.objects.new("cam_fill", cf_d)
    coll.objects.link(camfill)

    # ---- the shafts: a hard narrow spot each, plus a camera-only emissive cone (brightest through its middle, where
    # the eye looks through the most air) with dust streaks, switched on like stage lights
    import bmesh

    shafts = []  # (spot data, cone gain socket, base energy, base gain, switch-on frame)

    def cone_material(seed):
        mat = bpy.data.materials.new("beam")
        mat.use_nodes = True
        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        add = nt.nodes.new("ShaderNodeAddShader")
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        em = nt.nodes.new("ShaderNodeEmission")
        bb = nt.nodes.new("ShaderNodeBlackbody")
        bb.inputs["Temperature"].default_value = 4300.0
        nt.links.new(bb.outputs[0], em.inputs["Color"])
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.5
        core = mth(nt, "POWER", mth(nt, "SUBTRACT", 1.0, lw.outputs["Facing"]), 4.0)  # soft radial falloff
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["UV"], sep.inputs[0])
        # along (v: 0 at the source, 1 where it lands): fade in from the source, a little brighter low down
        along = mth(nt, "MULTIPLY", mth(nt, "POWER", sep.outputs["Y"], 0.8),
                    mth(nt, "SUBTRACT", 1.0, mth(nt, "POWER", sep.outputs["Y"], 12.0)))
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.noise_dimensions = "4D"
        nz.inputs["Scale"].default_value = 3.0
        nz.inputs["W"].default_value = seed
        ob_c = nt.nodes.new("ShaderNodeTexCoord")
        nt.links.new(ob_c.outputs["Object"], nz.inputs["Vector"])
        nzr = nt.nodes.new("ShaderNodeMapRange")
        nzr.inputs[1].default_value, nzr.inputs[2].default_value = 0.3, 0.75
        nzr.inputs[3].default_value, nzr.inputs[4].default_value = 0.45, 1.0
        nt.links.new(nz.outputs["Fac"], nzr.inputs[0])
        nz2 = nt.nodes.new("ShaderNodeTexNoise")  # a slow break-up along the beam's length
        nz2.inputs["Scale"].default_value = 1.0
        nz2.inputs["Detail"].default_value = 1.0
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (0.0, 6.0, 0.0)
        mp.inputs["Location"].default_value = (seed, 0.0, 0.0)
        nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
        nt.links.new(mp.outputs[0], nz2.inputs["Vector"])
        nzr2 = nt.nodes.new("ShaderNodeMapRange")
        nzr2.inputs[1].default_value, nzr2.inputs[2].default_value = 0.35, 0.65
        nzr2.inputs[3].default_value, nzr2.inputs[4].default_value = 0.7, 1.0
        nt.links.new(nz2.outputs["Fac"], nzr2.inputs[0])
        brk = mth(nt, "MULTIPLY", nzr.outputs[0], nzr2.outputs[0])
        cd = nt.nodes.new("ShaderNodeCameraData")  # never a hot wall of light right at the lens
        nr = nt.nodes.new("ShaderNodeMapRange")
        nr.inputs[1].default_value, nr.inputs[2].default_value = 0.6, 2.5
        nt.links.new(cd.outputs["View Distance"], nr.inputs[0])
        gain = nt.nodes.new("ShaderNodeValue")
        k = mth(nt, "MULTIPLY", mth(nt, "MULTIPLY", mth(nt, "MULTIPLY", core, along), brk),
                mth(nt, "MULTIPLY", nr.outputs[0], gain.outputs[0]))
        nt.links.new(k, em.inputs["Strength"])
        nt.links.new(tr.outputs[0], add.inputs[0])
        nt.links.new(em.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
        return mat, gain.outputs[0]

    mote_specs = []
    for si, (tx, ty, tz, f_on) in enumerate(SHAFTS):
        target = np.array([tx, ty, tz])
        spot_half = math.radians(1.5 if si == 0 else 2.0)
        L = (BEAM_TOP - tz) / -BEAM[2]
        apex = target - BEAM * L
        sd = bpy.data.lights.new(f"shaft{si}", "SPOT")
        sd.spot_size, sd.spot_blend, sd.shadow_soft_size = 2 * spot_half, 0.12, 0.02
        sd.use_temperature, sd.temperature = True, 4300
        sp = bpy.data.objects.new(f"shaft{si}", sd)
        sp.location = tuple(apex)
        coll.objects.link(sp)
        aim(sp, target)
        # the cone, apex to the floor beyond the target
        L2 = (BEAM_TOP - 0.0) / -BEAM[2]
        a1 = BEAM / np.linalg.norm(BEAM)
        e1 = np.cross(a1, [0, 0, 1.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(e1, a1)
        bm = bmesh.new()
        uvl_b = bm.loops.layers.uv.new("uv")
        NS = 160
        tip = [bm.verts.new(tuple(apex + a1 * 0.05)) for _ in range(NS)]
        rad = L2 * math.tan(spot_half) * 0.92
        ring = [bm.verts.new(tuple(apex + a1 * L2 + rad * (math.cos(2 * math.pi * k / NS) * e1 +
                                                        math.sin(2 * math.pi * k / NS) * e2))) for k in range(NS)]
        for k in range(NS):
            k2 = (k + 1) % NS
            fc = bm.faces.new((tip[k], tip[k2], ring[k2], ring[k]))
            for lp, uvp in zip(fc.loops, ((k / NS, 0), ((k + 1) / NS, 0), ((k + 1) / NS, 1), (k / NS, 1))):
                lp[uvl_b].uv = uvp
        me = bpy.data.meshes.new(f"beam{si}")
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()  # smooth normals: the falloff across the beam is continuous, no facets
        cmat, gsock = cone_material(si * 1.7)
        me.materials.append(cmat)
        ob = bpy.data.objects.new(f"beam{si}", me)
        coll.objects.link(ob)
        ob.visible_shadow = ob.visible_diffuse = ob.visible_glossy = ob.visible_transmission = False
        ob.visible_volume_scatter = False
        energy = 6300.0 if si == 0 else 14000.0
        shafts.append((sd, gsock, energy, 0.4 if si == 0 else 0.32, f_on))
        # dust inside this beam's lower part: the near one thick with it
        for _ in range(170 if si == 0 else (40 if si < 5 else 0)):
            uu = rnd.uniform(0.45, 1.0) * (L - 0.05) + 0.05
            rr = math.sqrt(rnd.random()) * uu * math.tan(spot_half) * 0.95
            th = rnd.uniform(0, 2 * math.pi)
            mote_specs.append(apex + a1 * uu + rr * (math.cos(th) * e1 + math.sin(th) * e2))

    # ---- dust: small spheres drifting in the beams (lit by them: only the ones in the light show)
    ico = bpy.data.meshes.new("mote")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    bm.to_mesh(ico)
    bm.free()
    mm = materials.satin("fg", roughness=0.4, coat=0.0, sheen=0.5, name="mote")
    ico.materials.append(mm)

    for pos in mote_specs:
        r = rnd.uniform(0.0025, 0.007)
        drift = (rnd.uniform(-0.03, 0.03), rnd.uniform(-0.03, 0.03), rnd.uniform(-0.035, 0.01))
        ph = rnd.uniform(0, 6.28)
        ob = bpy.data.objects.new("mote", ico)
        ob.scale = (r, r, r)
        coll.objects.link(ob)
        for f in (first, ctx.f0 + 90, ctx.f0 + 180, last):
            tt = (f - first) / 30.0
            ob.location = (pos[0] + drift[0] * tt + 0.03 * math.sin(tt * 1.3 + ph), pos[1] + drift[1] * tt,
                           pos[2] + drift[2] * tt + 0.02 * math.cos(tt * 0.9 + ph))
            ob.keyframe_insert("location", frame=f)

    # ---- loose pages drifting down in slow motion through the shafts (seeded)
    lp_mats = []
    for si_, nm in enumerate(SHEETS):
        m = bpy.data.materials.new(f"loose{si_}")
        m.use_nodes = True
        lnt = m.node_tree
        for n in list(lnt.nodes):
            lnt.nodes.remove(n)
        lout = lnt.nodes.new("ShaderNodeOutputMaterial")
        lb = lnt.nodes.new("ShaderNodeBsdfPrincipled")
        lb.inputs["Roughness"].default_value = 0.75
        lb.inputs["Specular IOR Level"].default_value = 0.2
        limg = lnt.nodes.new("ShaderNodeTexImage")
        limg.image = image(nm)
        ltc = lnt.nodes.new("ShaderNodeTexCoord")
        lnt.links.new(ltc.outputs["UV"], limg.inputs["Vector"])
        lmul = lnt.nodes.new("ShaderNodeMix")
        lmul.data_type, lmul.blend_type = "RGBA", "MULTIPLY"
        lmul.inputs[0].default_value = 1.0
        lmul.inputs[7].default_value = lin("fg", 0.85)
        lnt.links.new(limg.outputs["Color"], lmul.inputs[6])
        lnt.links.new(lmul.outputs[2], lb.inputs["Base Color"])
        finish(m, lb.outputs["BSDF"])
        lp_mats.append(m)
    lp_meshes = []
    for k, m in enumerate(lp_mats):
        me = bpy.data.meshes.new(f"loose{k}")
        nb = 6
        lv = [((i / nb - 0.5) * W, (j / 8 - 0.5) * H, 0.0) for j in range(9) for i in range(nb + 1)]
        lf = [(j * (nb + 1) + i, j * (nb + 1) + i + 1, (j + 1) * (nb + 1) + i + 1, (j + 1) * (nb + 1) + i)
              for j in range(8) for i in range(nb)]
        me.from_pydata(lv, [], lf)
        me.shade_smooth()
        luv = me.uv_layers.new(name="uv")
        for poly in me.polygons:
            for li in poly.loop_indices:
                vx, vy, _ = me.vertices[me.loops[li].vertex_index].co
                luv.data[li].uv = (vx / W + 0.5, vy / H + 0.5)
        me.materials.append(m)
        lp_meshes.append(me)
    lrnd = random.Random(31)
    loose = []
    while len(loose) < 34:
        if len(loose) < 20:  # most fall through a beam
            tx, ty, tz, _ = SHAFTS[lrnd.randrange(1, 6)]
            z0 = lrnd.uniform(1.6, 5.5)
            ctr = np.array([tx, ty, tz]) - BEAM * (z0 - tz) / -BEAM[2]
            x, y = ctr[0] + lrnd.gauss(0, 0.35), ctr[1] + lrnd.gauss(0, 0.35)
        else:
            x, y, z0 = lrnd.uniform(-4.0, 4.0), lrnd.uniform(-2.5, 24.0), lrnd.uniform(1.5, 6.5)
        if y < 3.2 and abs(x) < 1.0:
            continue  # keep the camera's path and the hero's flight clear
        t0 = np.array(SHAFTS[0][:3])
        if any(np.hypot(*(np.array([x, y]) - (t0 - BEAM * (z - t0[2]) / -BEAM[2])[:2])) < 0.8 for z in (z0, z0 - 1.3)):
            continue  # and the first shaft: a page falling through it would shadow the hero stack
        loose.append((x, y, z0, lrnd.uniform(0.07, 0.14), lrnd.uniform(0, 6.28), lrnd.uniform(-0.6, 0.6),
                      lrnd.uniform(0.15, 0.35), lrnd.randrange(len(lp_meshes))))
    for li_, (x, y, z0, vz, ph, spin, rock, mi) in enumerate(loose):
        ob = bpy.data.objects.new(f"loose{li_}", lp_meshes[mi])
        ob.rotation_mode = "XYZ"
        coll.objects.link(ob)
        bend_l = ob.modifiers.new("curl", "SIMPLE_DEFORM")
        bend_l.deform_method, bend_l.deform_axis = "BEND", "X"
        bend_l.angle = 0.35
        for f in range(first, last + 1, 3):
            tt = f / 30.0
            ob.location = (x + 0.12 * math.sin(tt * 0.8 + ph), y + 0.06 * math.cos(tt * 0.6 + ph), z0 - vz * tt)
            ob.rotation_euler = (rock * math.sin(tt * 0.9 + ph), rock * 0.7 * math.cos(tt * 0.7 + ph * 1.3),
                                 ph + spin * tt)
            ob.keyframe_insert("location", frame=f)
            ob.keyframe_insert("rotation_euler", frame=f)

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
    fade.scale = (0.3, 0.3, 1.0)
    coll.objects.link(fade)

    # ---- animation: everything a function of the frame, keyed on every frame (plus one beyond each end)
    for f in range(first, last + 1):
        cp, pitch, yaw = cam_pose(f)
        cam.location = tuple(cp)
        cam.rotation_euler = (math.radians(90 + pitch), 0.0, math.radians(yaw))
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
        fwd, right, up = cam_basis(pitch, yaw)

        pos, r1, p = page_state(f)
        q0 = Quaternion((1, 0, 0, 0))
        q1 = Matrix(r1.tolist()).to_quaternion()
        qm = q0.slerp(q1, sstep5(min(1.0, p * 1.08)))
        wob = math.sin(math.pi * min(1.0, p * 1.1)) * (1 - p)
        qm = qm @ Quaternion((0, 0, 1), 0.30 * wob) @ Quaternion((1, 0, 0), -0.10 * wob)
        page.location = tuple(pos)
        page.rotation_quaternion = qm
        page.keyframe_insert("location", frame=f)
        page.keyframe_insert("rotation_quaternion", frame=f)
        bend.angle = 0.28 * math.sin(math.pi * min(1.0, p * 1.05)) ** 1.5 * (1 - p)
        bend.keyframe_insert("angle", frame=f)
        twist.angle = 0.07 * wob
        twist.keyframe_insert("angle", frame=f)
        # the rim sweep glides along the edge once the page is up (u + 0.35 v runs 0..1.35)
        pos_v.outputs[0].default_value = -0.35 + 2.0 * sstep((f - 185.0) / 84.0)
        pos_v.outputs[0].keyframe_insert("default_value", frame=f)
        rim_k.outputs[0].default_value = 1.6 * sstep((f - 175.0) / 30.0)
        rim_k.outputs[0].keyframe_insert("default_value", frame=f)

        # the shafts: off, then each snaps on at its frame
        n_on = 0.0
        for sd, gsock, energy, g, f_on in shafts:
            o = shaft_on(f, f_on)
            n_on += min(o, 1.0)
            sd.energy = energy * o
            sd.keyframe_insert("energy", frame=f)
            gsock.default_value = g * o
            gsock.keyframe_insert("default_value", frame=f)
        hall = sstep((f - CRANE0) / 50.0)  # the hall's air and ambient come up with the cathedral
        fill_d.energy = 200.0 + 3200.0 * hall
        fill_d.keyframe_insert("energy", frame=f)
        for sock, base in fog_gain:
            sock.default_value = base * (0.06 + 0.22 * min(1.0, shaft_on(f, FIRST_ON)) + 0.72 * hall)
            sock.keyframe_insert("default_value", frame=f)

        camfill.location = tuple(cp + up * 0.6 - fwd * 0.5)
        camfill.rotation_euler = (math.radians(90 + pitch), 0.0, math.radians(yaw))
        camfill.keyframe_insert("location", frame=f)
        camfill.keyframe_insert("rotation_euler", frame=f)
        cf_d.energy = 6.0 + 30.0 * hall
        cf_d.keyframe_insert("energy", frame=f)
        # the page's soft key: from just above and behind the camera, so the page lands evenly lit
        kp = cp + up * 0.55 - fwd * 0.6 + right * -0.25
        key.location = tuple(kp)
        key.rotation_euler = (Vector(pos.tolist()) - Vector(kp.tolist())).to_track_quat("-Z", "Y").to_euler()
        key.keyframe_insert("location", frame=f)
        key.keyframe_insert("rotation_euler", frame=f)
        key_d.energy = KEY_W * sstep((f - LIFT0 - 15.0) / 80.0)
        key_d.keyframe_insert("energy", frame=f)
        # the backlight: behind and above the page (from the camera), for the bright rim on its edges
        bp = pos + fwd * 0.45 + up * 0.32
        back.location = tuple(bp)
        back.rotation_euler = (Vector(pos.tolist()) - Vector(bp.tolist())).to_track_quat("-Z", "Y").to_euler()
        back.keyframe_insert("location", frame=f)
        back.keyframe_insert("rotation_euler", frame=f)
        back_d.energy = 40.0 * sstep((f - LIFT0) / 25.0)
        back_d.keyframe_insert("energy", frame=f)

        # focus: the lit stack top, then deep into the hall for the reveal; on 'Millions' it holds on the hall while
        # the page comes in soft, then racks hard onto the page, which lands razor sharp
        dist_page = float(np.linalg.norm(pos - cp))
        stack = float(np.linalg.norm(np.array([HERO_XY[0], HERO_XY[1], HERO_TOP]) - cp))
        hallpt = float(np.linalg.norm(np.array([0.0, 11.0, 0.8]) - cp))
        fd = stack + (hallpt - stack) * sstep((f - CRANE0 - 5.0) / 40.0)
        fd = fd + (dist_page - fd) * sstep5((f - 186.0) / 26.0)
        cam.data.dof.focus_distance = fd
        cam.data.dof.keyframe_insert("focus_distance", frame=f)

        # black fade: opacity 1 -> 0 over frames 2..18 (the darkness then holds until the first shaft)
        fmix.inputs[0].default_value = 1.0 - sstep((f - 2.0) / 16.0)
        fmix.inputs[0].keyframe_insert("default_value", frame=f)

    # world: nearly black, a trace of indigo so the far haze has somewhere to go
    from lib import lights

    lights.world_color("bg2", 0.3)
