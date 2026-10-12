"""ingest3d: INGESTION plate for the CampX launch film (film frames [630, 870), 8 s).

A dark studio floor with a soft sheen. Closed answer booklets glide left to right along an invisible track through a
SCAN GATE (a tall thin frame of light, accent at the foot to accent2 at the head, with a faint laser plane). As each
booklet crosses the gate a scan line flickers over it, its cover sheet lifts off and dissolves (a noise-threshold
burn with an accent edge) into a drift of tiny glowing particles, and its inner pages fan out and fly to settle in a
neat floating grid on the right, one column per booklet (7 booklets x 4 pages = 28 pages). The camera trucks right
and pulls back, so the last frames show the ordered grid with the gate glowing at the left.

Designed for a CPU VM: instanced particle spheres, thin solidified slabs, no volumetrics, few bounces, transparent
only on the dissolving covers. Everything is deterministic (random.Random with fixed seeds). Colour: palette roles
only; only accent / accent2 emit. Motion blur is turned off (the finals run on CPUs without it); keys are still set
one frame beyond each end.
"""
from __future__ import annotations

import math
import random

SHOT = {"frames": [630, 870], "look": "660,700,740,790,840,868"}

N_BOOK = 7
N_PAGE = 4
PAGE_W, PAGE_H = 0.21, 0.297  # m, A4 / sqrt(2)-ish: the booklet's footprint
BOOK_PITCH = 0.52  # spacing of booklets along the track
SPEED = BOOK_PITCH / 22.0  # m per frame
FIRST_GATE = 34  # local frame the first booklet's centre crosses the gate
GATE_EVERY = 22
FLIGHT = 30  # frames a page takes from the stack to its slot
GRID_X0, GRID_PITCH_X = 0.78, 0.275
GRID_Z0, GRID_PITCH_Z = 0.36, 0.37
GRID_Y = 0.55
SHEETS = "assets/sheets"
COVERS = ["giet_38179_p01", "giet_38189_p01", "giet_38205_p01"]
PAGES = ([f"giet_{b}_p{n:02d}" for b in (38179, 38189, 38205) for n in range(2, 9)]
         + [f"hires_38189_p0{n}" for n in range(1, 5)])


def smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def smoother(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


def gate_frame(i: int) -> int:
    return FIRST_GATE + GATE_EVERY * i


def book_x(i: int, L: float) -> float:
    return (L - gate_frame(i)) * SPEED


def slot(i: int, k: int) -> tuple[float, float, float]:
    """Grid slot of page k of booklet i: column i, row k (page 0 on top)."""
    return (GRID_X0 + GRID_PITCH_X * i, GRID_Y, GRID_Z0 + GRID_PITCH_Z * (N_PAGE - 1 - k))


def launch_frame(i: int, k: int) -> int:
    return gate_frame(i) + 6 + 4 * k


def settle_frame(i: int, k: int) -> int:
    return launch_frame(i, k) + FLIGHT


def build(ctx):
    import bpy
    from mathutils import Euler, Vector

    from lib import lights, materials, rig, theme

    scene, coll = ctx.scene, ctx.scene.collection
    f0 = ctx.f0
    last_local = ctx.f1 - ctx.f0  # one beyond the end
    rnd = random.Random(2026)

    c = scene.cycles
    c.max_bounces, c.diffuse_bounces, c.glossy_bounces = 6, 2, 3
    c.transmission_bounces, c.volume_bounces, c.transparent_max_bounces = 2, 0, 8
    c.caustics_reflective = c.caustics_refractive = False
    c.sample_clamp_indirect = 6.0

    def F(L):
        return f0 + L

    def key(ob, path, L, index=-1, interp="BEZIER"):
        ob.keyframe_insert(path, index=index, frame=F(L))

    def linear_all(ob, kind="LINEAR"):
        act = ob.animation_data.action
        for layer in getattr(act, "layers", []):
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        for k in fc.keyframe_points:
                            k.interpolation = kind

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
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        mix.inputs[7].default_value = (*[v * tint for v in theme.linear("fg")], 1.0)  # warm paper
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

    page_mats = [paper(n, translucent=0.22) for n in PAGES]
    cover_mats = []
    for i in range(N_BOOK):
        name = COVERS[i % len(COVERS)]
        mat = paper(name, tint=0.86)
        mat.name = f"cover_{i}"
        nt = mat.node_tree
        gm = nt.nodes.new("ShaderNodeGamma")
        gm.inputs["Gamma"].default_value = 6.0  # deepen the faint print: a plain printed cover
        tx = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage")
        mx0 = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeMix")
        nt.links.new(tx.outputs["Color"], gm.inputs["Color"])
        nt.links.new(gm.outputs["Color"], mx0.inputs[6])
        b = nt.nodes["Principled BSDF"]
        out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        texco = nt.nodes.new("ShaderNodeTexCoord")
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 22.0
        noise.inputs["Detail"].default_value = 4.0
        nt.links.new(texco.outputs["UV"], noise.inputs["Vector"])
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(texco.outputs["UV"], sep.inputs["Vector"])
        # v = 0.62 noise + 0.38 sweep along the booklet's length (the scan line's side first)
        m1 = nt.nodes.new("ShaderNodeMath"); m1.operation = "MULTIPLY"; m1.inputs[1].default_value = 0.6
        nt.links.new(noise.outputs["Fac"], m1.inputs[0])
        m2 = nt.nodes.new("ShaderNodeMath"); m2.operation = "MULTIPLY_ADD"; m2.inputs[1].default_value = 0.4
        m2.inputs[2].default_value = 0.0
        nt.links.new(sep.outputs["Y"], m2.inputs[0])
        v = nt.nodes.new("ShaderNodeMath"); v.operation = "ADD"
        nt.links.new(m1.outputs[0], v.inputs[0]); nt.links.new(m2.outputs[0], v.inputs[1])
        d = nt.nodes.new("ShaderNodeValue"); d.name = "dissolve"; d.outputs[0].default_value = 0.0
        thr = nt.nodes.new("ShaderNodeMath"); thr.operation = "MULTIPLY_ADD"
        thr.inputs[1].default_value = 1.25; thr.inputs[2].default_value = -0.1
        nt.links.new(d.outputs[0], thr.inputs[0])
        alive = nt.nodes.new("ShaderNodeMath"); alive.operation = "GREATER_THAN"
        nt.links.new(v.outputs[0], alive.inputs[0]); nt.links.new(thr.outputs[0], alive.inputs[1])
        thr2 = nt.nodes.new("ShaderNodeMath"); thr2.operation = "ADD"; thr2.inputs[1].default_value = 0.05
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
        es = nt.nodes.new("ShaderNodeMath"); es.operation = "MULTIPLY"; es.inputs[1].default_value = 10.0
        nt.links.new(edge.outputs[0], es.inputs[0])
        nt.links.new(es.outputs[0], em.inputs["Strength"])
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(b.outputs["BSDF"], add.inputs[0]); nt.links.new(em.outputs["Emission"], add.inputs[1])
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mixs = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(alive.outputs[0], mixs.inputs[0])
        nt.links.new(tr.outputs[0], mixs.inputs[1]); nt.links.new(add.outputs[0], mixs.inputs[2])
        nt.links.new(mixs.outputs[0], out.inputs["Surface"])
        cover_mats.append(mat)

    # ------------------------------------------------------------------------------------------------ geometry
    def sheet_mesh(name, nx=6, ny=9, curl=0.0, seed=0):
        """A sheet in the xy plane (W x H, centred, normal +z), UV-mapped, bowed by `curl` m across its width and
        a little along its length."""
        r = random.Random(seed)
        bow_y = r.uniform(-1, 1) * curl * 0.4
        twist = r.uniform(-1, 1) * curl * 0.5
        verts, faces, uvs = [], [], []
        for j in range(ny + 1):
            for i in range(nx + 1):
                u, v = i / nx, j / ny
                x, y = (u - 0.5) * PAGE_W, (v - 0.5) * PAGE_H
                z = curl * (1 - (2 * u - 1) ** 2) + bow_y * (1 - (2 * v - 1) ** 2) + twist * (u - 0.5) * (v - 0.5) * 4
                verts.append((x, y, z))
                uvs.append((u, v))
        for j in range(ny):
            for i in range(nx):
                a = j * (nx + 1) + i
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
        mod.thickness = thickness
        mod.offset = -1.0
        coll.objects.link(ob)
        return ob

    # floor: dark, a soft reflective sheen
    fme = bpy.data.meshes.new("floor")
    s = 60.0
    fme.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    fm = materials.satin("bg", roughness=0.5, coat=1.0, sheen=0.0, name="floor")
    fb = fm.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (*theme.linear("bg2"), 1.0)
    fb.inputs["Coat Roughness"].default_value = 0.09
    fb.inputs["Specular IOR Level"].default_value = 0.2
    fme.materials.append(fm)
    floor = bpy.data.objects.new("floor", fme)
    coll.objects.link(floor)

    # the scan gate: a frame of four bars + a faint laser plane, accent (foot) -> accent2 (head)
    GATE_Y, GATE_H, BAR = 0.34, 0.66, 0.006

    def box(cx, cy, cz, sx, sy, sz, verts, faces):
        o = len(verts)
        for dx in (-1, 1):
            for dy in (-1, 1):
                for dz in (-1, 1):
                    verts.append((cx + dx * sx / 2, cy + dy * sy / 2, cz + dz * sz / 2))
        for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
            faces.append(tuple(o + i for i in f))

    gv, gf = [], []
    for sy in (-1, 1):
        box(0, sy * GATE_Y, GATE_H / 2, BAR, BAR, GATE_H, gv, gf)
    box(0, 0, GATE_H, BAR, 2 * GATE_Y + BAR, BAR, gv, gf)
    box(0, 0, 0.0, BAR, 2 * GATE_Y + BAR, BAR, gv, gf)
    gme = bpy.data.meshes.new("gate")
    gme.from_pydata(gv, [], gf)

    def gradient_emission(name, strength, alpha=None):
        mat = bpy.data.materials.new(name)
        nt = mat.node_tree
        nt.nodes.clear()
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs[1].default_value, mr.inputs[2].default_value = 0.0, GATE_H
        nt.links.new(sep.outputs["Z"], mr.inputs[0])
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"
        mx.inputs[6].default_value = (*theme.linear("accent"), 1.0)
        mx.inputs[7].default_value = (*theme.linear("accent2"), 1.0)
        nt.links.new(mr.outputs[0], mx.inputs[0])
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = strength
        nt.links.new(mx.outputs[2], em.inputs["Color"])
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        if alpha is None:
            nt.links.new(em.outputs[0], out.inputs["Surface"])
        else:
            tr = nt.nodes.new("ShaderNodeBsdfTransparent")
            ms = nt.nodes.new("ShaderNodeMixShader")
            ms.inputs[0].default_value = alpha
            nt.links.new(tr.outputs[0], ms.inputs[1]); nt.links.new(em.outputs[0], ms.inputs[2])
            nt.links.new(ms.outputs[0], out.inputs["Surface"])
        return mat

    gme.materials.append(gradient_emission("gate_light", 14.0))
    gate = bpy.data.objects.new("gate", gme)
    coll.objects.link(gate)
    # laser plane inside the frame
    lme = bpy.data.meshes.new("laser")
    lme.from_pydata([(0, -GATE_Y, 0), (0, GATE_Y, 0), (0, GATE_Y, GATE_H), (0, -GATE_Y, GATE_H)], [], [(0, 1, 2, 3)])
    lme.materials.append(gradient_emission("laser_plane", 2.0, alpha=0.035))
    gsv, gsf = [], []
    box(0, 0, 0, 0.002, 2 * GATE_Y, 0.0025, gsv, gsf)
    gsme = bpy.data.meshes.new("gate_scan")
    gsme.from_pydata(gsv, [], gsf)
    gsme.materials.append(materials.emission("accentBright", 16.0, name="gate_scan"))
    gscan = bpy.data.objects.new("gate_scan", gsme)
    coll.objects.link(gscan)
    for L in range(-1, last_local + 1, 4):
        gscan.location = (0, 0, 0.03 + (GATE_H - 0.06) * (0.5 - 0.5 * math.cos(L / 46.0 * math.pi)))
        key(gscan, "location", L)
    laser = bpy.data.objects.new("laser", lme)
    coll.objects.link(laser)

    # scan line: a thin emissive strip on the booklet under the laser, flickering while a booklet crosses
    sme = bpy.data.meshes.new("scanline")
    sme.from_pydata([(-0.0025, -PAGE_H / 2 - 0.01, 0), (0.0025, -PAGE_H / 2 - 0.01, 0), (0.0025, PAGE_H / 2 + 0.01, 0),
                     (-0.0025, PAGE_H / 2 + 0.01, 0)], [], [(0, 1, 2, 3)])
    scm = materials.emission("accentBright", 9.0, name="scanline")
    sme.materials.append(scm)
    scan = bpy.data.objects.new("scanline", sme)
    scan.location = (0.0, 0.0, 0.012)
    coll.objects.link(scan)
    strength_in = next(n for n in scm.node_tree.nodes if n.bl_idname == "ShaderNodeEmission").inputs["Strength"]
    fl = random.Random(7)
    # visibility via scale: zero outside the booklets' crossings (constant keys); strength flickers inside
    scan.scale = (1, 0.0001, 1)
    key(scan, "scale", -2)
    for i in range(N_BOOK):
        g = gate_frame(i)
        a, b = g - 6, g + 6
        scan.scale = (1, 0.0001, 1); key(scan, "scale", a - 1)
        scan.scale = (1, 1, 1); key(scan, "scale", a)
        scan.scale = (1, 1, 1); key(scan, "scale", b)
        scan.scale = (1, 0.0001, 1); key(scan, "scale", b + 1)
        for L in range(a, b + 1):
            strength_in.default_value = 9.0 * fl.choice([0.35, 0.7, 1.0, 1.0, 0.5, 1.2])
            strength_in.keyframe_insert("default_value", frame=F(L))
    scan.scale = (1, 0.0001, 1); key(scan, "scale", last_local)
    linear_all(scan, "CONSTANT")
    ad = scm.node_tree.animation_data
    if ad and ad.action:
        for layer in getattr(ad.action, "layers", []):
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        for k in fc.keyframe_points:
                            k.interpolation = "CONSTANT"

    # ------------------------------------------------------------------------------------ booklets and pages
    TH = 0.0034
    # shared tiny particle mesh
    pme = bpy.data.meshes.new("mote")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    bm.to_mesh(pme)
    bm.free()
    pme.shade_smooth()
    pme_a, pme_b = pme, pme.copy()
    pme_a.materials.append(materials.emission("accentBright", 14.0, name="mote_a"))
    pme_b.materials.append(materials.emission("accent2Bright", 14.0, name="mote_b"))

    pages = []  # (ob, i, k)
    for i in range(N_BOOK):
        g = gate_frame(i)
        # inner pages: stacked, page k in the stack from the top; cover on top
        for k in range(N_PAGE):
            ix = (i * N_PAGE + k) % len(PAGES)
            pg = sheet(f"page_{i}_{k}", page_mats[ix], 0.0012, 0.0025, seed=100 + i * 10 + k)
            pages.append((pg, i, k))
            zst = 0.003 + (N_PAGE - 1 - k) * TH
            rest = Vector((0, 0, zst))
            # track: on the invisible track until launch, then fan + fly
            L_la, L_se = launch_frame(i, k), settle_frame(i, k)
            sl = Vector(slot(i, k))
            start_L = -1
            Ls = [start_L, L_la]
            # path samples
            def pos_at(L):
                if L <= L_la:
                    return Vector((book_x(i, L), 0.0, zst)), (0.0, 0.0, 0.0)
                u = (L - L_la) / FLIGHT
                x0 = book_x(i, L_la)
                fan_u = smooth(u / 0.28)  # first part: fan out above the stack
                fan = Vector((0.015 * (k - 1.5) * fan_u, 0.0, 0.11 + 0.035 * k)) * fan_u
                p0 = Vector((x0, 0.0, zst)) + fan
                fly_u = smoother((u - 0.18) / 0.82)
                arc = Vector((0, -0.22 * math.sin(math.pi * fly_u), 0.10 * math.sin(math.pi * fly_u)))
                p = p0.lerp(sl, fly_u) + arc
                rx = math.radians(90) * smoother((u - 0.12) / 0.7)
                rz = math.radians((k - 1.5) * 9) * fan_u * (1 - smooth((u - 0.5) / 0.4))
                return p, (rx, 0.0, rz)
            for L in list(range(-1, L_la, 12)) + [L_la]:
                p, r = pos_at(L)
                pg.location, pg.rotation_euler = p, r
                key(pg, "location", L); key(pg, "rotation_euler", L)
            for L in range(L_la + 3, L_se, 3):
                p, r = pos_at(L)
                pg.location, pg.rotation_euler = p, r
                key(pg, "location", L); key(pg, "rotation_euler", L)
            pg.location, pg.rotation_euler = sl, (math.radians(90), 0, 0)
            key(pg, "location", L_se); key(pg, "rotation_euler", L_se)
            # slow float after settling: drift back and a hair of tilt
            pg.location = sl + Vector((0, 0.05, 0.015 * (1 if (i + k) % 2 else -1)))
            pg.rotation_euler = (math.radians(90) + 0.012 * ((i * 3 + k) % 3 - 1), 0, 0.01 * ((i + k) % 3 - 1))
            key(pg, "location", last_local); key(pg, "rotation_euler", last_local)

        # cover
        cv = sheet(f"cover_{i}", cover_mats[i], 0.0014, 0.0015, seed=300 + i)
        z_top = 0.003 + N_PAGE * TH + 0.001
        gd = g - 2
        cv.visible_shadow = False
        cv.hide_render = False
        cv.keyframe_insert("hide_render", frame=F(-1))
        cv.hide_render = True
        cv.keyframe_insert("hide_render", frame=F(g + 18))
        cv.keyframe_insert("hide_render", frame=F(last_local))
        for L in sorted(set(list(range(-1, gd + 1, 12)) + list(range(gd, g + 24, 3)))):
            u = smooth((L - g) / 20.0)
            x = book_x(i, L) - (0.0 if L < g else 0.6 * (L - g) * SPEED * smooth((L - g) / 8))
            cv.location = (x, 0.0, z_top + 0.14 * u)
            cv.rotation_euler = (math.radians(-9) * u, math.radians(6) * u, math.radians(5) * u)
            key(cv, "location", L); key(cv, "rotation_euler", L)
        nt = cover_mats[i].node_tree
        dnode = nt.nodes["dissolve"]
        for L, val in ((-1, 0.0), (g - 3, 0.0), (g + 17, 1.0), (last_local, 1.0)):
            dnode.outputs[0].default_value = val
            dnode.outputs[0].keyframe_insert("default_value", frame=F(L))
        # motes: spawn on the cover as it lifts; drift up and away on slow curls; shrink to nothing
        for j in range(105):
            sp = g - 1 + int(rnd.random() ** 1.2 * 18)
            u0 = smooth((sp - g) / 20.0)
            cx = book_x(i, sp) - 0.6 * max(0, sp - g) * SPEED * smooth((sp - g) / 8)
            p0 = Vector((cx + (rnd.random() - 0.5) * PAGE_W * 0.95, (rnd.random() - 0.5) * PAGE_H * 0.95,
                         z_top + 0.14 * u0 + 0.01))
            life = rnd.randint(46, 78)
            rad = rnd.choice([0.0016, 0.0022, 0.003, 0.0045]) * (1.0 + rnd.random() * 0.6)
            mote = bpy.data.objects.new(f"mote_{i}_{j}", pme_a if rnd.random() < 0.55 else pme_b)
            coll.objects.link(mote)
            drift = Vector(((rnd.random() - 0.35) * 0.25, (rnd.random() - 0.5) * 0.3, 0.10 + rnd.random() * 0.34))
            ph = rnd.random() * 6.28
            n = 5
            mote.scale = (0.0, 0.0, 0.0)
            key(mote, "scale", sp - 1)
            for q in range(n + 1):
                t = q / n
                L = sp + int(t * life)
                e = smooth(t * 0.9 + 0.1 * t)
                curl = Vector((math.sin(ph + 5 * t) * 0.05, math.cos(ph * 1.3 + 4 * t) * 0.05,
                               math.sin(ph + 3 * t) * 0.03)) * t
                mote.location = p0 + drift * (0.15 * t + 0.85 * e) + curl
                key(mote, "location", L)
                fade = (1.0 if t < 0.55 else 1 - smooth((t - 0.55) / 0.45)) * (smooth(t / 0.08) if t < 0.08 else 1.0)
                tw = 1.0 + 0.35 * math.sin(ph * 2 + t * 18)
                s_ = rad * fade * tw
                mote.scale = (s_, s_, s_)
                key(mote, "scale", L)
            mote.scale = (0, 0, 0)
            key(mote, "scale", sp + life + 1)

    # ---------------------------------------------------------------------------------------- camera and light
    focus = bpy.data.objects.new("focus", None)
    coll.objects.link(focus)
    cam = rig.engine_camera("camera", fstop=2.6, size=ctx.size)
    cam.data.dof.focus_object = focus
    cam.data.clip_end = 100
    scene.camera = cam
    A = dict(pos=Vector((-1.15, -1.75, 0.62)), tgt=Vector((0.12, 0.0, 0.2)), fov=30.0)
    B = dict(pos=Vector((0.95, -2.95, 0.95)), tgt=Vector((1.3, 0.3, 0.74)), fov=36.0)
    for L in range(-1, last_local + 1, 6):
        u = smoother((L + 1) / (last_local + 1))
        pos = A["pos"].lerp(B["pos"], u)
        tgt = A["tgt"].lerp(B["tgt"], u)
        # early on the focus sits at the gate; later on the grid (which is where the eye is)
        fo = Vector((0.0, 0.0, 0.14)).lerp(Vector((1.52, GRID_Y, 0.66)), smooth((L - 60) / 150.0))
        cam.location = pos
        cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = rig.lens_mm(A["fov"] + (B["fov"] - A["fov"]) * u)
        focus.location = fo
        key(cam, "location", L); key(cam, "rotation_euler", L)
        cam.data.keyframe_insert("lens", frame=F(L)); key(focus, "location", L)
    cam.data.dof.aperture_fstop = 2.6

    lights.studio(key=None, rim=None, fill=None, world="bg", world_strength=1.0)
    # broad soft overhead key over the track and grid, a rim from behind the grid, accent washes at the gate
    def area(name, power, loc, tgt, size, color=None, temp=6200, shape="RECTANGLE", sy=None):
        d = bpy.data.lights.new(name, "AREA")
        d.energy, d.size, d.shape = power, size, shape
        if shape == "RECTANGLE":
            d.size_y = sy or size
        if color:
            d.color = theme.linear(color)
        else:
            d.use_temperature, d.temperature = True, temp
        ob = bpy.data.objects.new(name, d)
        ob.location = loc
        ob.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        coll.objects.link(ob)
        return ob

    # the cost on CPUs: hundreds of tiny emitters must not enter the light tree, and only the camera and the floor's
    # reflection need to see the glows (the washes light the scene for them)
    for m in bpy.data.materials:
        if m.name.startswith(("mote", "scanline", "laser", "cover_")):
            m.cycles.emission_sampling = "NONE"
    for ob in scene.objects:
        if ob.name.startswith(("mote_", "laser", "scanline", "gate_scan")):
            ob.visible_diffuse = ob.visible_shadow = ob.visible_transmission = ob.visible_volume_scatter = False
        if ob.name == "gate":
            ob.visible_shadow = False

    k = area("key", 70, (0.4, -1.2, 2.6), (0.6, 0.2, 0.0), 1.6, sy=1.0)
    k.data.spread = math.radians(60)
    gf = area("grid_fill", 45, (1.6, -2.6, 1.4), (1.6, 0.5, 0.8), 1.8, sy=1.2)
    bl = area("backlight", 260, (1.65, 1.9, 0.95), (1.65, 0.5, 0.95), 2.6, sy=1.7, temp=5600)
    rm = area("rim", 90, (2.8, 1.8, 2.0), (1.4, 0.4, 0.6), 1.0, sy=0.8, temp=7500)
    wa = area("gate_wash_a", 18, (-0.5, -0.6, 0.35), (0, 0, 0.1), 0.4, color="accent")
    wb = area("gate_wash_b", 18, (0.5, 0.6, 0.45), (0, 0, 0.1), 0.4, color="accent2")
    for ob in (k, gf, bl, rm, wa, wb):
        ob.visible_glossy = False  # the floor reflects the gate and the pages, never a light
