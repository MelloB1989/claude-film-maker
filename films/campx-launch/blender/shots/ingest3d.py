"""ingest3d: INGESTION plate for the CampX launch film (film frames [630, 870), 8 s). Cut 2.

One precise machine on a dark glossy floor, beat by beat on the voiceover (local frame L = film frame - 630):
  L 15-78   "Upload one ZIP of scanned scripts."  A rounded glass archive block holding a neat stack of six booklets
            glides in and lands on a glowing upload line. A seam of accent light runs along it, the glass clears, and
            the booklets slide out, top first, into a perfectly spaced line on two thin light rails to the scan gate.
  L 89-144  "CampX splits every booklet,"         The line glides through the gate (a thin frame of light). Past it
            each booklet splits: its pages flip up in a staggered cascade and slot into an aligned grid wall behind.
  L 156-183 "reads its cover,"                    The last (hero) booklet slows past the gate and rises, tilted to a
            close camera. A scan line passes over its cover (a real St. Peter's cover, identity fields pre-softened:
            assets/sheets/cover_002_soft.jpg) and thin accent boxes with tiny labels snap onto PHOTO, NAME,
            HALL TICKET and QR.
  L 191-240 "removes the student's identity,"     The boxes fill, wipe the fields to blank paper and dissolve into
            fine motes; the cover peels off its spine and burns away; the anonymous pages lift towards the grid's last
            column. The camera ends on a slow drift.

One continuous camera move. Deterministic. Palette roles only; only accent / accent2 emit. Keys run one frame beyond
each end for motion blur.
"""
from __future__ import annotations

import math
import random

SHOT = {"frames": [630, 870], "look": "650,690,730,760,800,830,869"}

N_BOOK = 6  # the last one is the hero
HERO = N_BOOK - 1
N_PAGE = 2  # two pages per booklet: a calm, legible cascade
PAGE_W, PAGE_H = 0.21, 0.297
BODY = 0.010  # the paper block under the leaves
TH = 0.0032  # leaf spacing
BOOK_T = BODY + N_PAGE * TH + 0.003
SHEETS = "assets/sheets"
COVER = "cover_002_soft"
PAGES = ([f"giet_{b}_p{n:02d}" for b in (38179, 38189, 38205) for n in range(2, 9)]
         + [f"hires_38189_p0{n}" for n in range(1, 5)])

# ZIP block and line-up
SLAB_X = -2.05
STK = 0.028  # booklet pitch in the block's stack
SLAB_LAND = 38
SEAM = (38, 50)
GLASS_FADE = (48, 60)
SLIDE0, SLIDE_STEP, SLIDE_N = 54, 3, 18
LINE_X0, LINE_PITCH = -0.40, 0.26  # booklet j waits at LINE_X0 - j * LINE_PITCH
RUN0, SPEED = 80, 0.036  # the line starts gliding at L 80 (8-frame ease in), m per frame
SPLIT_X = 0.16  # past the gate: where a booklet splits
FLIGHT = 36
# grid wall behind the gate, one column per booklet, page 0 on top
GX0, GPX, GY, GZ0, GPZ, GSCALE = 0.55, 0.19, 1.05, 0.24, 0.255, 0.8
# hero: leaves the line at L 118, comes to rest at x 0.34, rises and tilts to the camera
HERO_STOP = (118, 160, 0.34)
HERO_RISE = (146, 168, 0.11, 35.0)  # start, end, height, tilt (deg)
SCAN = (157, 171)
SNAP = (167, 4)  # first box snaps at L 167, then every 4 frames
FILL = (192, 2, 8)  # start, stagger, frames
WIPE = (200, 6)
PEEL = (212, 232, -165.0)
BURN = (216, 238)
HERO_LAUNCH, HERO_FLIGHT = 228, 80  # only a gentle lift before the cut
# detection boxes on cover_002 in a 1200 x 1773 reference (the image is 1196 x 1768): x0, y0, x1, y1, label side
REF_W, REF_H = 1200.0, 1773.8
FIELDS = [("PHOTO", (628, 236, 797, 404), "top"), ("NAME", (278, 408, 470, 440), "right"),
          ("HALL TICKET", (276, 364, 440, 398), "right"), ("QR", (136, 1642, 234, 1735), "right")]
# camera: (local frame, position, target, vertical fov); Blender coordinates, z up
CAM = [(-1, (-3.05, -1.25, 0.42), (-2.45, 0.05, 0.08), 30.0),
       (40, (-2.55, -1.35, 0.48), (-1.95, 0.05, 0.08), 30.0),
       (78, (-1.75, -1.65, 0.62), (-1.0, 0.15, 0.12), 32.0),
       (115, (-0.45, -1.95, 0.85), (0.45, 0.45, 0.42), 34.0),
       (146, (0.22, -1.10, 0.64), (0.36, 0.06, 0.16), 30.0),
       (170, (0.38, -0.66, 0.56), (0.34, 0.02, 0.10), 28.0),
       (241, (0.47, -0.74, 0.58), (0.36, 0.04, 0.12), 29.0)]
FOCUS = [(-1, (-2.6, 0.0, 0.08)), (40, (-2.05, 0.0, 0.08)), (78, (-1.2, 0.0, 0.05)), (115, (0.3, 0.4, 0.3)),
         (150, (0.34, 0.0, 0.12))]


def smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def smoother(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


def hermite(keys, t: float):
    """Cubic Hermite through keys [(t, value or tuple)], tangents from the neighbours (Catmull-Rom on uneven times),
    flat at both ends. Returns a float or a tuple."""
    ts = [k[0] for k in keys]
    vs = [k[1] if isinstance(k[1], tuple) else (k[1],) for k in keys]
    n = len(keys)
    if t <= ts[0]:
        out = vs[0]
    elif t >= ts[-1]:
        out = vs[-1]
    else:
        i = max(j for j in range(n - 1) if ts[j] <= t)
        h = ts[i + 1] - ts[i]
        u = (t - ts[i]) / h

        def tan(j):
            if j == 0 or j == n - 1:
                return tuple(0.0 for _ in vs[j])
            return tuple((vs[j + 1][c] - vs[j - 1][c]) / (ts[j + 1] - ts[j - 1]) for c in range(len(vs[j])))

        m0, m1 = tan(i), tan(i + 1)
        h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
        out = tuple(h00 * vs[i][c] + h10 * h * m0[c] + h01 * vs[i + 1][c] + h11 * h * m1[c] for c in range(len(vs[i])))
    return out[0] if not isinstance(keys[0][1], tuple) else out


def run_d(L: float) -> float:
    """How far the line has glided since RUN0 (an 8-frame ease into SPEED)."""
    t = L - RUN0
    if t <= 0:
        return 0.0
    if t < 8:
        return SPEED * t * t / 16
    return SPEED * (t - 4)


def slab_x(L: float) -> float:
    return hermite([(-1, -3.25), (SLAB_LAND, SLAB_X)], L)


def slab_z(L: float) -> float:
    return 0.10 * (1 - smoother((L + 1) / (SLAB_LAND + 1)))


def line_x(j: int, L: float) -> float:
    x = LINE_X0 - j * LINE_PITCH + run_d(L)
    if j == HERO and L > HERO_STOP[0]:
        a, b, xe = HERO_STOP
        x0 = LINE_X0 - j * LINE_PITCH + run_d(a)
        u, h = min(1.0, (L - a) / (b - a)), b - a
        x = (2 * u ** 3 - 3 * u ** 2 + 1) * x0 + (u ** 3 - 2 * u ** 2 + u) * h * SPEED + (-2 * u ** 3 + 3 * u ** 2) * xe
    return x


def book_pose(j: int, L: float):
    """(x, z) of booklet j's base: in the block, sliding out, on the line."""
    s = SLIDE0 + SLIDE_STEP * j
    zin = slab_z(L) + 0.012 + (N_BOOK - 1 - j) * STK
    if L <= s:
        return slab_x(L), zin
    u = (L - s) / SLIDE_N
    if u >= 1:
        return line_x(j, L), 0.0
    e = smoother(u)
    x = slab_x(L) + (line_x(j, L) - slab_x(L)) * e
    z = zin * (1 - smooth(u / 0.75))
    return x, z


def split_frame(j: int) -> int:
    return min(range(RUN0, 241), key=lambda L: abs(line_x(j, L) - SPLIT_X))


def launch_frame(j: int, k: int) -> int:
    if j == HERO:
        return HERO_LAUNCH + 4 * k
    return split_frame(j) + 8 * k


def slot(j: int, k: int):
    return (GX0 + GPX * j, GY, GZ0 + GPZ * (N_PAGE - 1 - k))


def hero_rise(L: float):
    a, b, h, tilt = HERO_RISE
    u = smoother((L - a) / (b - a))
    return h * u, math.radians(tilt) * u


def field_box(box):
    """A field's (x0, y0, x1, y1) in the cover's local metres (x right, y towards the header)."""
    x0, y0, x1, y1 = box
    return ((x0 / REF_W - 0.5) * PAGE_W, (0.5 - y1 / REF_H) * PAGE_H, (x1 / REF_W - 0.5) * PAGE_W,
            (0.5 - y0 / REF_H) * PAGE_H)


def build(ctx):
    import bmesh
    import bpy
    from mathutils import Matrix, Quaternion, Vector

    from lib import lights, materials, rig, theme

    scene, coll = ctx.scene, ctx.scene.collection
    f0 = ctx.f0
    last = ctx.f1 - ctx.f0  # one beyond the end
    rnd = random.Random(2026)

    c = scene.cycles
    c.max_bounces, c.diffuse_bounces, c.glossy_bounces = 8, 2, 4
    c.transmission_bounces, c.volume_bounces, c.transparent_max_bounces = 6, 0, 10
    c.caustics_reflective = c.caustics_refractive = False
    c.sample_clamp_indirect = 6.0

    def F(L):
        return f0 + L

    def key(ob, path, L):
        ob.keyframe_insert(path, frame=F(L))

    def keyval(sock, val, L):
        sock.default_value = val
        sock.keyframe_insert("default_value", frame=F(L))

    def fcurves(idblock):
        ad = idblock.animation_data
        if not (ad and ad.action):
            return []
        out = []
        for layer in getattr(ad.action, "layers", []):
            for strip in layer.strips:
                for bag in strip.channelbags:
                    out += list(bag.fcurves)
        return out or list(getattr(ad.action, "fcurves", []))

    def interp(idblock, kind):
        for fc in fcurves(idblock):
            for kp in fc.keyframe_points:
                kp.interpolation = kind

    # ------------------------------------------------------------------------------------------ images, materials
    img_cache = {}

    def image(name):
        if name not in img_cache:
            img_cache[name] = bpy.data.images.load(str(ctx.film.path(f"{SHEETS}/{name}.jpg")), check_existing=True)
        return img_cache[name]

    def paper(name, tint=1.0, rough=0.72, translucent=0.0):
        mat = bpy.data.materials.new("paper_" + name)
        nt = mat.node_tree
        b = nt.nodes["Principled BSDF"]
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image(name)
        tex.interpolation = "Linear"
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        mix.inputs[7].default_value = (*[v * tint for v in theme.linear("fg")], 1.0)
        nt.links.new(tex.outputs["Color"], mix.inputs[6])
        nt.links.new(mix.outputs[2], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = rough
        b.inputs["Specular IOR Level"].default_value = 0.25
        b.inputs["Sheen Weight"].default_value = 0.3
        if translucent:
            out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
            tl = nt.nodes.new("ShaderNodeBsdfTranslucent")
            nt.links.new(mix.outputs[2], tl.inputs["Color"])
            ms = nt.nodes.new("ShaderNodeMixShader")
            ms.inputs[0].default_value = translucent
            nt.links.new(b.outputs["BSDF"], ms.inputs[1]); nt.links.new(tl.outputs[0], ms.inputs[2])
            nt.links.new(ms.outputs[0], out.inputs["Surface"])
        return mat

    def faded_emission(name, role, strength, alpha0=0.0):
        """An emission behind an animatable opacity (a Value node named 'a')."""
        mat = bpy.data.materials.new(name)
        nt = mat.node_tree
        nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*theme.linear(role), 1.0)
        em.inputs["Strength"].default_value = strength
        a = nt.nodes.new("ShaderNodeValue"); a.name = "a"; a.outputs[0].default_value = alpha0
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        ms = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(a.outputs[0], ms.inputs[0])
        nt.links.new(tr.outputs[0], ms.inputs[1]); nt.links.new(em.outputs[0], ms.inputs[2])
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(ms.outputs[0], out.inputs["Surface"])
        mat.cycles.emission_sampling = "NONE"
        return mat, a.outputs[0], em.inputs["Strength"]

    page_mats = [paper(n, translucent=0.2) for n in PAGES]

    # the hero's cover: paper + a burn-away threshold with an accent edge (Value node 'dissolve')
    cover_mat = paper(COVER, tint=0.93, rough=0.55)
    cover_mat.name = "cover_hero"
    nt = cover_mat.node_tree
    b = nt.nodes["Principled BSDF"]
    out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    texco = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 14.0
    noise.inputs["Detail"].default_value = 4.0
    nt.links.new(texco.outputs["UV"], noise.inputs["Vector"])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(texco.outputs["UV"], sep.inputs["Vector"])
    # v = 0.3 noise + 0.7 (1 - u): it burns from the free edge towards the spine
    m1 = nt.nodes.new("ShaderNodeMath"); m1.operation = "MULTIPLY"; m1.inputs[1].default_value = 0.3
    nt.links.new(noise.outputs["Fac"], m1.inputs[0])
    m2 = nt.nodes.new("ShaderNodeMath"); m2.operation = "MULTIPLY_ADD"
    m2.inputs[1].default_value, m2.inputs[2].default_value = -0.7, 0.7
    nt.links.new(sep.outputs["X"], m2.inputs[0])
    v = nt.nodes.new("ShaderNodeMath"); v.operation = "ADD"
    nt.links.new(m1.outputs[0], v.inputs[0]); nt.links.new(m2.outputs[0], v.inputs[1])
    d = nt.nodes.new("ShaderNodeValue"); d.name = "dissolve"; d.outputs[0].default_value = 0.0
    thr = nt.nodes.new("ShaderNodeMath"); thr.operation = "MULTIPLY_ADD"
    thr.inputs[1].default_value, thr.inputs[2].default_value = 1.1, -0.06
    nt.links.new(d.outputs[0], thr.inputs[0])
    alive = nt.nodes.new("ShaderNodeMath"); alive.operation = "GREATER_THAN"
    nt.links.new(v.outputs[0], alive.inputs[0]); nt.links.new(thr.outputs[0], alive.inputs[1])
    thr2 = nt.nodes.new("ShaderNodeMath"); thr2.operation = "ADD"; thr2.inputs[1].default_value = 0.035
    nt.links.new(thr.outputs[0], thr2.inputs[0])
    edge_lt = nt.nodes.new("ShaderNodeMath"); edge_lt.operation = "LESS_THAN"
    nt.links.new(v.outputs[0], edge_lt.inputs[0]); nt.links.new(thr2.outputs[0], edge_lt.inputs[1])
    edge = nt.nodes.new("ShaderNodeMath"); edge.operation = "MULTIPLY"
    nt.links.new(edge_lt.outputs[0], edge.inputs[0]); nt.links.new(alive.outputs[0], edge.inputs[1])
    em = nt.nodes.new("ShaderNodeEmission")
    ramp = nt.nodes.new("ShaderNodeMix"); ramp.data_type = "RGBA"
    ramp.inputs[6].default_value = (*theme.linear("accent"), 1.0)
    ramp.inputs[7].default_value = (*theme.linear("accent2"), 1.0)
    nt.links.new(sep.outputs["Y"], ramp.inputs[0])
    nt.links.new(ramp.outputs[2], em.inputs["Color"])
    es = nt.nodes.new("ShaderNodeMath"); es.operation = "MULTIPLY"; es.inputs[1].default_value = 12.0
    nt.links.new(edge.outputs[0], es.inputs[0])
    nt.links.new(es.outputs[0], em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(b.outputs["BSDF"], add.inputs[0]); nt.links.new(em.outputs["Emission"], add.inputs[1])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mixs = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(alive.outputs[0], mixs.inputs[0])
    nt.links.new(tr.outputs[0], mixs.inputs[1]); nt.links.new(add.outputs[0], mixs.inputs[2])
    nt.links.new(mixs.outputs[0], out.inputs["Surface"])
    cover_mat.cycles.emission_sampling = "NONE"

    # ------------------------------------------------------------------------------------------------ geometry
    def sheet_mesh(name, nx=6, ny=9, curl=0.0, seed=0):
        r = random.Random(seed)
        bow_y = r.uniform(-1, 1) * curl * 0.4
        verts, faces, uvs = [], [], []
        for jj in range(ny + 1):
            for ii in range(nx + 1):
                u, vv = ii / nx, jj / ny
                x, y = (u - 0.5) * PAGE_W, (vv - 0.5) * PAGE_H
                z = curl * (1 - (2 * u - 1) ** 2) + bow_y * (1 - (2 * vv - 1) ** 2)
                verts.append((x, y, z))
                uvs.append((u, vv))
        for jj in range(ny):
            for ii in range(nx):
                a = jj * (nx + 1) + ii
                faces.append((a, a + 1, a + nx + 2, a + nx + 1))
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.shade_smooth()
        uv = me.uv_layers.new(name="UV")
        for poly in me.polygons:
            for li, vi in zip(poly.loop_indices, poly.vertices):
                uv.data[li].uv = uvs[vi]
        return me

    def sheet(name, mat, thickness, curl, seed, nx=6, ny=9):
        ob = bpy.data.objects.new(name, sheet_mesh(name, nx, ny, curl, seed))
        ob.data.materials.append(mat)
        mod = ob.modifiers.new("thick", "SOLIDIFY")
        mod.thickness, mod.offset = thickness, -1.0
        coll.objects.link(ob)
        return ob

    def box(cx, cy, cz, sx, sy, sz, verts, faces):
        o = len(verts)
        for dx in (-1, 1):
            for dy in (-1, 1):
                for dz in (-1, 1):
                    verts.append((cx + dx * sx / 2, cy + dy * sy / 2, cz + dz * sz / 2))
        for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
            faces.append(tuple(o + i for i in f))

    def mesh_ob(name, verts, faces, mat):
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        return ob

    def quad(x0, y0, x1, y1, z=0.0):
        return [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [(0, 1, 2, 3)]

    # floor: deep ink, a clear coat with controlled, slightly softened reflections
    fm = materials.satin("bg", roughness=0.45, coat=1.0, sheen=0.0, name="floor")
    fb = fm.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (*theme.linear("bg2"), 1.0)
    fb.inputs["Coat Roughness"].default_value = 0.06
    fb.inputs["Specular IOR Level"].default_value = 0.15
    mesh_ob("floor", *quad(-60, -60, 60, 60), fm)

    # the scan gate: a thin frame of light, accent at the foot -> accent2 at the head, and a faint sheet inside
    GATE_Y, GATE_H, BAR = 0.22, 0.36, 0.004

    def gradient_emission(name, strength, alpha=None, falloff=0.0):
        mat = bpy.data.materials.new(name)
        nt = mat.node_tree
        nt.nodes.clear()
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sp = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sp.inputs["Vector"])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs[1].default_value, mr.inputs[2].default_value = 0.0, GATE_H
        nt.links.new(sp.outputs["Z"], mr.inputs[0])
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"
        mx.inputs[6].default_value = (*theme.linear("accent"), 1.0)
        mx.inputs[7].default_value = (*theme.linear("accent2"), 1.0)
        nt.links.new(mr.outputs[0], mx.inputs[0])
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Strength"].default_value = strength
        nt.links.new(mx.outputs[2], e.inputs["Color"])
        if falloff:
            inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
            nt.links.new(mr.outputs[0], inv.inputs[1])
            pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = falloff
            nt.links.new(inv.outputs[0], pw.inputs[0])
            sm = nt.nodes.new("ShaderNodeMath"); sm.operation = "MULTIPLY"; sm.inputs[1].default_value = strength
            nt.links.new(pw.outputs[0], sm.inputs[0])
            nt.links.new(sm.outputs[0], e.inputs["Strength"])
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        if alpha is None:
            nt.links.new(e.outputs[0], o.inputs["Surface"])
        else:
            t = nt.nodes.new("ShaderNodeBsdfTransparent")
            ms = nt.nodes.new("ShaderNodeMixShader")
            ms.inputs[0].default_value = alpha
            nt.links.new(t.outputs[0], ms.inputs[1]); nt.links.new(e.outputs[0], ms.inputs[2])
            nt.links.new(ms.outputs[0], o.inputs["Surface"])
        return mat

    gv, gf = [], []
    for sy in (-1, 1):
        box(0, sy * GATE_Y, GATE_H / 2, BAR, BAR, GATE_H, gv, gf)
    box(0, 0, GATE_H, BAR, 2 * GATE_Y + BAR, BAR, gv, gf)
    box(0, 0, 0.0005, BAR, 2 * GATE_Y + BAR, 0.001, gv, gf)
    gate = mesh_ob("gate", gv, gf, gradient_emission("gate_light", 7.0))
    gate.visible_shadow = False
    gs = next(n for n in gate.data.materials[0].node_tree.nodes if n.bl_idname == "ShaderNodeEmission").inputs["Strength"]
    keyval(gs, 7.0, 140); keyval(gs, 0.12, 168)  # the gate recedes in the close-up
    laser = mesh_ob("laser", [(0, -GATE_Y, 0), (0, GATE_Y, 0), (0, GATE_Y, GATE_H), (0, -GATE_Y, GATE_H)],
                    [(0, 1, 2, 3)], gradient_emission("laser_plane", 2.0, alpha=0.02, falloff=3.0))

    # upload line across the track under the block; two thin rails from the block to the gate and on
    up_mat, up_a, up_s = faded_emission("upload_line", "accent", 3.0, alpha0=1.0)
    upl = mesh_ob("upload_line", *quad(-0.003, -0.26, 0.003, 0.26, 0.0006), up_mat)
    upl.location = (SLAB_X - 0.17, 0, 0)
    for L, s_ in ((-1, 1.2), (SLAB_LAND - 4, 1.6), (SLAB_LAND, 9.0), (SLAB_LAND + 10, 3.0), (last, 2.4)):
        keyval(up_s, s_, L)
    rail_mat, rail_a, _ = faded_emission("rails", "accentBright", 2.2, alpha0=1.0)
    rails = []
    rail_len = 0.0 - (SLAB_X + 0.17) + 1.6
    for sy in (-1, 1):
        rv, rf = quad(0, sy * 0.165 - 0.0012, rail_len, sy * 0.165 + 0.0012, 0.0006)
        r_ = mesh_ob(f"rail_{sy}", rv, rf, rail_mat)
        r_.location = (SLAB_X + 0.17, 0, 0)
        r_.scale = (1e-4, 1, 1); key(r_, "scale", -1); key(r_, "scale", 48)
        r_.scale = (1, 1, 1); key(r_, "scale", 70)
        rails.append(r_)
    keyval(rail_a, 1.0, 140); keyval(rail_a, 0.0, 168)  # gone for the close-up

    # ---------------------------------------------------------------------------------------- the ZIP block
    sw, sd, sh = PAGE_W + 0.06, PAGE_H + 0.06, 0.012 + N_BOOK * STK + 0.012
    glass = bpy.data.materials.new("zip_glass")
    gnt = glass.node_tree
    gbs = gnt.nodes["Principled BSDF"]
    gbs.inputs["Base Color"].default_value = (*theme.linear("fg"), 1.0)
    gbs.inputs["Transmission Weight"].default_value = 1.0
    gbs.inputs["Roughness"].default_value = 0.06
    gbs.inputs["IOR"].default_value = 1.45
    gbs.inputs["Coat Weight"].default_value = 0.6
    gout = next(n for n in gnt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    ga = gnt.nodes.new("ShaderNodeValue"); ga.name = "a"; ga.outputs[0].default_value = 1.0
    gtr = gnt.nodes.new("ShaderNodeBsdfTransparent")
    gms = gnt.nodes.new("ShaderNodeMixShader")
    gnt.links.new(ga.outputs[0], gms.inputs[0])
    gnt.links.new(gtr.outputs[0], gms.inputs[1]); gnt.links.new(gbs.outputs["BSDF"], gms.inputs[2])
    gnt.links.new(gms.outputs[0], gout.inputs["Surface"])
    sv, sf = [], []
    box(0, 0, sh / 2, sw, sd, sh, sv, sf)
    slab = mesh_ob("zip", sv, sf, glass)
    bev = slab.modifiers.new("round", "BEVEL")
    bev.width, bev.segments, bev.harden_normals = 0.022, 5, True
    slab.data.shade_smooth()
    slab.visible_shadow = False
    seam_mat, seam_a, seam_s = faded_emission("seam", "accentBright", 10.0, alpha0=1.0)
    # the seam: a fine line round the block's waist, drawn from the back-left corner along the front and round
    seam = mesh_ob("seam", *quad(0, -0.0011, sw + 0.002, 0.0011), seam_mat)
    seam2 = mesh_ob("seam_b", *quad(0, -0.0011, sw + 0.002, 0.0011), seam_mat)
    for L in sorted(set(list(range(-1, SLAB_LAND + 1, 3)) + [SLAB_LAND, GLASS_FADE[1] + 2, last])):
        x, z = slab_x(L), slab_z(L)
        slab.location = (x, 0, z); key(slab, "location", L)
        seam.location = (x - sw / 2 - 0.001, -sd / 2 - 0.0005, z + sh * 0.55)
        seam.rotation_euler = (math.radians(90), 0, 0)
        seam2.location = (x - sw / 2 - 0.001, sd / 2 + 0.0005, z + sh * 0.55)
        seam2.rotation_euler = (math.radians(90), 0, 0)
        key(seam, "location", L); key(seam, "rotation_euler", L)
        key(seam2, "location", L); key(seam2, "rotation_euler", L)
    for s_ob in (seam, seam2):
        s_ob.scale = (1e-4, 1, 1); key(s_ob, "scale", -1); key(s_ob, "scale", SEAM[0])
        s_ob.scale = (1, 1, 1); key(s_ob, "scale", SEAM[1])
    keyval(seam_s, 10.0, SEAM[1]); keyval(seam_s, 22.0, SEAM[1] + 2); keyval(seam_s, 10.0, GLASS_FADE[0] + 4)
    keyval(seam_a, 1.0, GLASS_FADE[0]); keyval(seam_a, 0.0, GLASS_FADE[1])
    keyval(ga.outputs[0], 1.0, GLASS_FADE[0]); keyval(ga.outputs[0], 0.0, GLASS_FADE[1])
    slab.scale = (1, 1, 1); key(slab, "scale", GLASS_FADE[0])
    slab.scale = (1.05, 1.05, 1.08); key(slab, "scale", GLASS_FADE[1])
    slab.hide_render = False; slab.keyframe_insert("hide_render", frame=F(-1))
    slab.hide_render = True; slab.keyframe_insert("hide_render", frame=F(GLASS_FADE[1] + 1))
    for s_ob in (seam, seam2):
        s_ob.hide_render = False; s_ob.keyframe_insert("hide_render", frame=F(-1))
        s_ob.hide_render = True; s_ob.keyframe_insert("hide_render", frame=F(GLASS_FADE[1] + 1))

    # ------------------------------------------------------------------------------------ booklets and pages
    edge = bpy.data.materials.new("page_edges")
    ent = edge.node_tree
    eb = ent.nodes["Principled BSDF"]
    etc = ent.nodes.new("ShaderNodeTexCoord")
    wave = ent.nodes.new("ShaderNodeTexWave")
    wave.wave_type, wave.bands_direction = "BANDS", "Z"
    wave.inputs["Scale"].default_value = 260.0
    ent.links.new(etc.outputs["Object"], wave.inputs["Vector"])
    er = ent.nodes.new("ShaderNodeMix"); er.data_type = "RGBA"
    er.inputs[6].default_value = (*[v * 0.55 for v in theme.linear("fg")], 1.0)
    er.inputs[7].default_value = (*[v * 0.92 for v in theme.linear("fg")], 1.0)
    ent.links.new(wave.outputs["Fac"], er.inputs[0])
    ent.links.new(er.outputs[2], eb.inputs["Base Color"])
    eb.inputs["Roughness"].default_value = 0.8

    def hero_T(L):
        x, _ = book_pose(HERO, L)
        h, rx = hero_rise(L)
        return Matrix.Translation((x, 0, h)) @ Matrix.Rotation(rx, 4, "X")

    def base_T(j, L):
        if j == HERO:
            return hero_T(L)
        x, z = book_pose(j, L)
        return Matrix.Translation((x, 0, z))

    def put(ob, M, L, prev):
        loc, q, _ = M.decompose()
        if prev.get(ob.name) is not None:
            q.make_compatible(prev[ob.name])
        prev[ob.name] = q
        ob.location, ob.rotation_quaternion = loc, q
        key(ob, "location", L); key(ob, "rotation_quaternion", L)

    prev = {}
    q_slot = Quaternion((1, 0, 0), math.radians(90))
    for j in range(N_BOOK):
        bv, bf = [], []
        box(0, 0, BODY / 2, PAGE_W - 0.004, PAGE_H - 0.004, BODY, bv, bf)
        blk = mesh_ob(f"block_{j}", bv, bf, edge)
        blk.rotation_mode = "QUATERNION"
        bm_ = blk.modifiers.new("bevel", "BEVEL")
        bm_.width, bm_.segments = 0.0012, 2
        L_a = launch_frame(j, 0)
        L_b = launch_frame(j, N_PAGE - 1) + 10
        end = last if j == HERO else min(last, L_b + 1)
        Ls = sorted(set(list(range(-1, end + 1, 2)) + [end]))
        for L in Ls:
            put(blk, base_T(j, L), L, prev)
            u = 0.0 if j == HERO else smooth((L - L_a) / (L_b - L_a))
            blk.scale = (1 - 0.15 * u, 1 - 0.15 * u, max(1e-4, 1 - u))
            key(blk, "scale", L)
        if j != HERO:
            blk.hide_render = False; blk.keyframe_insert("hide_render", frame=F(-1))
            blk.hide_render = True; blk.keyframe_insert("hide_render", frame=F(L_b + 1))
        for k in range(N_PAGE):
            ix = (j * N_PAGE + k) % len(PAGES)
            pg = sheet(f"page_{j}_{k}", page_mats[ix], 0.0011, 0.0018, seed=100 + j * 10 + k)
            pg.rotation_mode = "QUATERNION"
            zk = BODY + 0.0015 + (N_PAGE - 1 - k) * TH
            La = launch_frame(j, k)
            fl = HERO_FLIGHT if j == HERO else FLIGHT
            sl = Vector(slot(j, k))
            M0 = base_T(j, La) @ Matrix.Translation((0, 0, zk))
            p0, q0, _ = M0.decompose()
            for L in sorted(set(list(range(-1, min(La, last) + 1, 2)) + [min(La, last)])):
                put(pg, base_T(j, L) @ Matrix.Translation((0, 0, zk)), L, prev)
            if La >= last:
                continue
            for L in list(range(La + 2, min(La + fl, last) + 1, 2)) + ([last] if La + fl < last else []):
                u = min(1.0, (L - La) / fl)
                ea, eb_ = smoother(u), smoother((u - 0.14) / 0.86)
                p = p0.lerp(sl, eb_) + Vector((0, 0.0, 0.07 * math.sin(math.pi * ea)))
                q = q0.slerp(q_slot, smoother(u / 0.72))
                s_ = 1 + (GSCALE - 1) * eb_
                put(pg, Matrix.Translation(p) @ q.to_matrix().to_4x4(), L, prev)
                pg.scale = (s_, s_, s_); key(pg, "scale", L)
            pg.scale = (1, 1, 1); key(pg, "scale", La)

    # ------------------------------------------------------------------------------------------ the hero cover
    z_top = BODY + 0.0015 + N_PAGE * TH + 0.0012
    cv = sheet("cover_hero", cover_mat, 0.0012, 0.0, seed=300, nx=12, ny=16)
    cv.rotation_mode = "QUATERNION"
    cv.visible_shadow = False

    def cover_M(L):
        a, b, ang = PEEL
        bb = math.radians(ang) * smoother((L - a) / (b - a))
        return (hero_T(L) @ Matrix.Translation((-PAGE_W / 2, 0, z_top)) @ Matrix.Rotation(bb, 4, "Y")
                @ Matrix.Translation((PAGE_W / 2, 0, 0)))

    for L in sorted(set(list(range(-1, last + 1, 2)) + [last])):
        put(cv, cover_M(L), L, prev)
    dsock = cover_mat.node_tree.nodes["dissolve"].outputs[0]
    for L, val in ((-1, 0.0), (BURN[0], 0.0), (BURN[1], 1.0), (last, 1.0)):
        keyval(dsock, val, L)

    # scan line over the cover (child of the cover, cover-local coordinates)
    sc_mat, sc_a, _ = faded_emission("scanline", "accentBright", 9.0)
    scn = mesh_ob("scanline", *quad(-PAGE_W / 2 - 0.002, -0.00028, PAGE_W / 2 + 0.002, 0.00028, 0.0009), sc_mat)
    scn.parent = cv
    glow_mat, glow_a, _ = faded_emission("scanglow", "accent", 0.9)
    glow = mesh_ob("scanglow", *quad(-PAGE_W / 2, -0.0035, PAGE_W / 2, 0.0035, 0.0007), glow_mat)
    glow.parent = scn
    for L in range(SCAN[0] - 1, SCAN[1] + 2):
        u = smooth((L - SCAN[0]) / (SCAN[1] - SCAN[0]))
        scn.location = (0, -PAGE_H / 2 - 0.004 + (PAGE_H + 0.008) * u, 0)
        key(scn, "location", L)
    for sock, a_ in ((sc_a, 1.0), (glow_a, 0.3)):
        keyval(sock, 0.0, SCAN[0] - 2); keyval(sock, a_, SCAN[0]); keyval(sock, a_, SCAN[1] - 1)
        keyval(sock, 0.0, SCAN[1] + 1)

    # detection boxes, labels and the redaction fills
    LW = 0.0007
    motes_at = []
    pme = bpy.data.meshes.new("mote")
    bmm = bmesh.new()
    bmesh.ops.create_icosphere(bmm, subdivisions=1, radius=1.0)
    bmm.to_mesh(pme)
    bmm.free()
    pme_a, pme_b = pme, pme.copy()
    pme_a.materials.append(materials.emission("accentBright", 12.0, name="mote_a"))
    pme_b.materials.append(materials.emission("accent2Bright", 12.0, name="mote_b"))
    paper_rgb = tuple(v * 0.8 for v in theme.linear("fg"))
    for n, (label, ref, side) in enumerate(FIELDS):
        x0, y0, x1, y1 = field_box(ref)
        pad = 0.0015
        x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        hw, hh = (x1 - x0) / 2, (y1 - y0) / 2
        bmat, b_a, _ = faded_emission(f"box_{n}", "accentBright", 6.0)
        vv, ff = [], []
        for (ax0, ay0, ax1, ay1) in ((-hw, -hh, hw, -hh + LW), (-hw, hh - LW, hw, hh), (-hw, -hh, -hw + LW, hh),
                                     (hw - LW, -hh, hw, hh)):
            o = len(vv)
            vv += [(ax0, ay0, 0), (ax1, ay0, 0), (ax1, ay1, 0), (ax0, ay1, 0)]
            ff.append((o, o + 1, o + 2, o + 3))
        frame_ob = mesh_ob(f"box_{n}", vv, ff, bmat)
        frame_ob.parent = cv
        frame_ob.location = (cx, cy, 0.0012)
        # label
        cu = bpy.data.curves.new(f"label_{n}", "FONT")
        cu.body, cu.size = label, 0.0052
        cu.materials.append(bmat)
        lab = bpy.data.objects.new(f"label_{n}", cu)
        coll.objects.link(lab)
        lab.parent = cv
        lab.location = ((x0 + 0.0005, y1 + 0.0018, 0.0012) if side == "top" else (x1 + 0.0028, cy - 0.0018, 0.0012))
        # fill: transparent -> accent glow -> blank paper
        fmat = bpy.data.materials.new(f"fill_{n}")
        fnt = fmat.node_tree
        fnt.nodes.clear()
        fa = fnt.nodes.new("ShaderNodeValue"); fa.name = "a"
        fw = fnt.nodes.new("ShaderNodeValue"); fw.name = "w"
        fem = fnt.nodes.new("ShaderNodeEmission")
        fem.inputs["Color"].default_value = (*theme.linear("accent"), 1.0)
        fem.inputs["Strength"].default_value = 3.5
        fdf = fnt.nodes.new("ShaderNodeBsdfDiffuse")
        fdf.inputs["Color"].default_value = (*paper_rgb, 1.0)
        fm1 = fnt.nodes.new("ShaderNodeMixShader")
        fnt.links.new(fw.outputs[0], fm1.inputs[0]); fnt.links.new(fem.outputs[0], fm1.inputs[1])
        fnt.links.new(fdf.outputs[0], fm1.inputs[2])
        ftr = fnt.nodes.new("ShaderNodeBsdfTransparent")
        fm2 = fnt.nodes.new("ShaderNodeMixShader")
        fnt.links.new(fa.outputs[0], fm2.inputs[0]); fnt.links.new(ftr.outputs[0], fm2.inputs[1])
        fnt.links.new(fm1.outputs[0], fm2.inputs[2])
        fo = fnt.nodes.new("ShaderNodeOutputMaterial")
        fnt.links.new(fm2.outputs[0], fo.inputs["Surface"])
        fmat.cycles.emission_sampling = "NONE"
        fill = mesh_ob(f"fill_{n}", *quad(-hw + LW, -hh + LW, hw - LW, hh - LW, 0), fmat)
        fill.parent = cv
        fill.location = (cx, cy, 0.0008)
        fill.visible_shadow = False
        # timing
        ts = SNAP[0] + SNAP[1] * n
        frame_ob.scale = (1.35, 1.35, 1); key(frame_ob, "scale", ts - 1)
        frame_ob.scale = (1, 1, 1); key(frame_ob, "scale", ts + 3)
        keyval(b_a, 0.0, ts - 1)
        keyval(b_a, 1.0, ts + 1)
        tf = FILL[0] + FILL[1] * n
        keyval(fa.outputs[0], 0.0, tf); keyval(fa.outputs[0], 1.0, tf + FILL[2])
        keyval(fw.outputs[0], 0.0, WIPE[0] + FILL[1] * n); keyval(fw.outputs[0], 1.0, WIPE[0] + FILL[1] * n + WIPE[1])
        keyval(b_a, 1.0, WIPE[0] + FILL[1] * n); keyval(b_a, 0.0, WIPE[0] + FILL[1] * n + 8)
        keyval(fa.outputs[0], 1.0, PEEL[0]); keyval(fa.outputs[0], 0.0, PEEL[0] + 6)  # the blank patch leaves with the cover
        motes_at.append((cx, cy, hw, hh, WIPE[0] + FILL[1] * n))

    for (cx, cy, hw, hh, t0) in motes_at:
        cnt = int(40 + 3000 * hw * hh)
        for m in range(cnt):
            sp = t0 + rnd.randint(0, 9)
            lp = Vector((cx + (rnd.random() * 2 - 1) * hw, cy + (rnd.random() * 2 - 1) * hh, 0.002))
            M = cover_M(sp)
            p0 = M @ lp
            nrm = (M.to_3x3() @ Vector((0, 0, 1))).normalized()
            drift = nrm * (0.03 + 0.05 * rnd.random()) + Vector(((rnd.random() - 0.5) * 0.04,
                                                                 0.02 + 0.03 * rnd.random(), 0.05 * rnd.random()))
            life = rnd.randint(26, 44)
            rad = rnd.choice([0.0007, 0.0009, 0.0012, 0.0016])
            mote = bpy.data.objects.new(f"mote_{len(motes_at)}_{m}_{t0}", pme_a if rnd.random() < 0.6 else pme_b)
            coll.objects.link(mote)
            ph = rnd.random() * 6.28
            mote.scale = (0, 0, 0); key(mote, "scale", sp - 1)
            for qn in range(6):
                t = qn / 5
                L = sp + int(t * life)
                e = smooth(t)
                curl = Vector((math.sin(ph + 5 * t), math.cos(ph * 1.3 + 4 * t), 0.0)) * 0.012 * t
                mote.location = p0 + drift * e + curl
                key(mote, "location", L)
                fade = 1.0 if t < 0.5 else 1 - smooth((t - 0.5) / 0.5)
                s_ = rad * fade * (smooth(t / 0.15) if t < 0.15 else 1.0)
                mote.scale = (s_, s_, s_); key(mote, "scale", L)
            mote.scale = (0, 0, 0); key(mote, "scale", sp + life + 1)

    # ---------------------------------------------------------------------------------------- camera and light
    focus = bpy.data.objects.new("focus", None)
    coll.objects.link(focus)
    cam = rig.engine_camera("camera", fstop=2.4, size=ctx.size)
    cam.data.dof.focus_object = focus
    cam.data.clip_end = 100
    scene.camera = cam
    pos_k = [(k_[0], k_[1]) for k_ in CAM]
    tgt_k = [(k_[0], k_[2]) for k_ in CAM]
    fov_k = [(k_[0], k_[3]) for k_ in CAM]
    for L in sorted(set(list(range(-1, last + 1, 2)) + [last])):
        pos, tgt = Vector(hermite(pos_k, L)), Vector(hermite(tgt_k, L))
        cam.location = pos
        cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = rig.lens_mm(hermite(fov_k, L))
        fo = Vector(hermite(FOCUS, L))
        if L >= 140:  # ride the hero's cover once it is the subject
            hc = hero_T(L) @ Vector((0, 0.02, z_top))
            fo = fo.lerp(hc, smooth((L - 140) / 20))
        focus.location = fo
        key(cam, "location", L); key(cam, "rotation_euler", L)
        cam.data.keyframe_insert("lens", frame=F(L)); key(focus, "location", L)
    cam.data.dof.aperture_fstop = 2.4

    lights.studio(key=None, rim=None, fill=None, world="bg", world_strength=1.0)

    def area(name, power, loc, tgt, size, color=None, temp=6200, sy=None, glossy=False):
        d_ = bpy.data.lights.new(name, "AREA")
        d_.energy, d_.size, d_.shape = power, size, "RECTANGLE"
        d_.size_y = sy or size
        if color:
            d_.color = theme.linear(color)
        else:
            d_.use_temperature, d_.temperature = True, temp
        ob = bpy.data.objects.new(name, d_)
        ob.location = loc
        ob.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        coll.objects.link(ob)
        ob.visible_glossy = glossy
        return ob

    for ob in scene.objects:
        if ob.name.startswith(("mote_", "laser", "scanline", "scanglow", "box_", "label_", "seam", "rail_",
                               "upload_line")):
            ob.visible_diffuse = ob.visible_shadow = ob.visible_transmission = ob.visible_volume_scatter = False
    for m in bpy.data.materials:
        if m.name.startswith(("mote", "gate_light")):
            m.cycles.emission_sampling = "NONE"

    k1 = area("key", 12, (-0.6, -1.0, 2.4), (-0.6, 0.2, 0.0), 3.2, sy=1.0)
    k1.data.spread = math.radians(70)
    area("hero_key", 4.5, (0.1, -0.7, 1.0), (0.34, 0.0, 0.1), 0.6, sy=0.4, temp=5600)
    area("grid_fill", 26, (0.7, -2.4, 1.3), (0.7, 0.75, 0.6), 1.8, sy=1.2)
    bl = area("backlight", 160, (0.7, 2.2, 0.9), (0.7, 0.75, 0.6), 2.4, sy=1.4, temp=5600)
    bl.data.spread = math.radians(35)
    area("rim", 60, (1.8, 1.6, 1.6), (0.7, 0.5, 0.4), 1.0, sy=0.8, temp=7500)
    # a long soft strip the glass block and the floor may reflect: one controlled highlight
    area("glass_strip", 14, (-2.05, 0.35, 1.1), (-2.05, 0.0, 0.0), 1.4, sy=0.08, temp=6800, glossy=True)
    area("gate_wash_a", 4, (-0.4, -0.5, 0.3), (0, 0, 0.1), 0.4, color="accent")
    area("gate_wash_b", 4, (0.4, 0.5, 0.4), (0, 0, 0.1), 0.4, color="accent2")
    area("zip_wash", 3, (-2.05, -0.6, 0.25), (-2.05, 0, 0.05), 0.5, color="accent")
