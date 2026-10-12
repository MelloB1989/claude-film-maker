"""mark3d: MARKING. Dark space; typeset answer lines float on the left over the faint ghost of the handwritten page;
four answer-key points stand on the right as frosted glass tiles with a thin accent rim. Luminous threads (a tube with
the brand gradient travelling along it) shoot from the relevant answer lines to each tile in turn; a tile lights as its
thread connects: the first three fully (accent), the last one partially (a dimmer accent2 glow: partial credit). The
camera arcs slowly from the answer side to the key-point side and ends on a calm frame with the top right left empty
for the engine's overlay (the suggested mark is drawn by the engine, not here).

Everything is keyed (no handlers): thread growth, tile light and fades are keyed Value nodes / light energies, so the
frames are deterministic. Colours are palette roles; only accents glow.
"""
from __future__ import annotations

import math

import numpy as np

SHOT = {"scene": "mark3d", "frames": [1470, 1650], "look": "1470,1530,1590,1648,1649"}

SHEETS = "films/campx-launch/assets/sheets"
FONT = "app/public/fonts/Geist-500.ttf"

LABELS = ["Augmented matrix formed", "Row-reduced to echelon form", "Rank of the matrix = 3",
          "Solution: x = 1, y = 1, z = 1"]
# the typeset answer lines (the transcription): (text, tile it threads to or None)
LINES = [("3x + y − z = 3", 0), ("2x − 8y + z = −5", None), ("R2 → R2 − 2R1", 1),
         ("R3 → 2R3 − 5R2", None), ("rank of the matrix = 3", 2), ("x = 1, y = 1, z = 1", 3)]
# seconds into the shot: thread i leaves at THREAD_T[i], arrives THREAD_D later
THREAD_T = [0.9, 1.9, 2.9, 3.9]
THREAD_D = 0.9
TILE_W, TILE_H, TILE_T = 1.55, 0.40, 0.035
TILE_X, TILE_Z0, TILE_DZ = 1.35, 0.55, -0.56


# ---------------------------------------------------------------------------------------------- pure geometry

def rounded_rect(w: float, h: float, r: float, n: int = 160) -> np.ndarray:
    """A closed rounded-rectangle path in the XZ plane (n, 3), starting at the left edge's middle."""
    pts = []
    hw, hh = w / 2 - r, h / 2 - r
    per = 2 * (2 * hw + 2 * hh) + 2 * math.pi * r
    for s in np.linspace(0, per, n, endpoint=False):
        # walk: left-mid up, top-left arc, top, top-right arc, right down, bottom-right arc, bottom, bottom-left arc
        segs = [(hh, "v"), (math.pi * r / 2, "a"), (2 * hw, "h"), (math.pi * r / 2, "a"), (2 * hh, "v"),
                (math.pi * r / 2, "a"), (2 * hw, "h"), (math.pi * r / 2, "a"), (hh, "v")]
        pos = np.array([-w / 2, 0.0])
        d = np.array([0.0, 1.0])
        ang = 0.0
        rem = s
        for L, k in segs:
            step = min(rem, L)
            if k == "a":
                # arc turning clockwise (towards +x from up)
                a0 = ang
                th = step / r
                cx, cz = pos + r * np.array([d[1], -d[0]])  # centre to the right of travel
                pa = math.atan2(pos[1] - cz, pos[0] - cx)
                pa -= th
                pos = np.array([cx + r * math.cos(pa), cz + r * math.sin(pa)])
                ang = a0 - th
                d = np.array([-math.sin(ang), math.cos(ang)])
            else:
                pos = pos + d * step
            rem -= step
            if rem <= 1e-12:
                break
        pts.append((pos[0], 0.0, pos[1]))
    return np.array(pts)


def bezier(p0, p1, p2, p3, n: int) -> np.ndarray:
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.asarray(p, float) for p in (p0, p1, p2, p3))
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3


def tube(c: np.ndarray, radius: float, seg: int = 6, closed: bool = False):
    """A tube along centreline c (n, 3) with parallel-transport rings: (verts, faces, u) where u in 0..1 runs along it."""
    c = np.asarray(c, float)
    n = len(c)
    T = np.gradient(c, axis=0) if not closed else (np.roll(c, -1, 0) - np.roll(c, 1, 0))
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    ref = np.array([0.0, 1.0, 0.0]) if abs(T[0, 1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    U = np.zeros_like(c)
    u = ref - T[0] * np.dot(ref, T[0])
    for i in range(n):
        u = u - T[i] * np.dot(u, T[i])
        u /= np.linalg.norm(u)
        U[i] = u
    V = np.cross(T, U)
    a = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    rings = c[:, None] + radius * (np.cos(a)[None, :, None] * U[:, None] + np.sin(a)[None, :, None] * V[:, None])
    rows = n if closed else n - 1
    faces = [(i * seg + j, i * seg + (j + 1) % seg, ((i + 1) % n) * seg + (j + 1) % seg, ((i + 1) % n) * seg + j)
             for i in range(rows) for j in range(seg)]
    if closed:
        s = np.arange(n) / n
        uu = np.minimum(s, 1 - s) * 2
    else:
        uu = np.linspace(0, 1, n)
    return rings.reshape(-1, 3), faces, np.repeat(uu, seg)


def curl_grid(w: float, h: float, nx: int, ny: int, curl: float, twist: float):
    """A paper sheet's vertices (nx*ny, 3) in its own XZ plane with a slight curl (bow along x, a lifted corner)."""
    xs = np.linspace(-w / 2, w / 2, nx)
    zs = np.linspace(-h / 2, h / 2, ny)
    X, Z = np.meshgrid(xs, zs)
    Y = curl * (X / (w / 2)) ** 2 + twist * (X / (w / 2)) * (Z / (h / 2))
    uv = np.stack([(X + w / 2) / w, (Z + h / 2) / h], -1).reshape(-1, 2)
    return np.stack([X, Y, Z], -1).reshape(-1, 3), uv


def grid_faces(nx: int, ny: int):
    return [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
            for j in range(ny - 1) for i in range(nx - 1)]


# ------------------------------------------------------------------------------------------------------ the shot

def build(ctx):
    import bpy
    from mathutils import Vector

    from lib import lights, materials, rig, theme

    scene, coll = ctx.scene, ctx.scene.collection
    repo = _repo_root()
    first, last = ctx.f0 - 1, ctx.f1  # a frame beyond each end, for the motion blur
    fps = ctx.fps

    def F(s):
        return ctx.f0 + round(s * fps)

    cy = scene.cycles
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 3, 1, 2
    cy.transmission_bounces, cy.transparent_max_bounces, cy.volume_bounces = 3, 4, 0
    cy.adaptive_threshold = 0.03
    cy.caustics_reflective = cy.caustics_refractive = False

    lin = theme.linear

    def key(sock, frame, value):
        sock.default_value = value
        sock.keyframe_insert("default_value", frame=frame)

    def value_node(nt, name, v=0.0):
        n = nt.nodes.new("ShaderNodeValue")
        n.name = n.label = name
        n.outputs[0].default_value = v
        return n

    def with_fade(mat, fade_node_value=1.0):
        """Wrap the material's surface in Mix(Transparent, shader, fade): returns the fade Value node."""
        nt = mat.node_tree
        out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        src = out.inputs["Surface"].links[0].from_socket
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        fade = value_node(nt, "fade", fade_node_value)
        nt.links.new(fade.outputs[0], mix.inputs[0])
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(src, mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        return fade

    def emit_mat(name, color_stops, strength, mask_max=1.0, travel=False):
        """Emission driven by a keyed 'p' (progress along the mesh's attribute u) with a travelling pulse. Returns
        (material, p value node, t value node)."""
        mat = bpy.data.materials.new(name)
        mat.node_tree.nodes.clear() if mat.node_tree else None
        nt = mat.node_tree
        N = nt.nodes
        L = nt.links
        att = N.new("ShaderNodeAttribute")
        att.attribute_name = "u"
        att.attribute_type = "GEOMETRY"
        p = value_node(nt, "p", 0.0)
        t = value_node(nt, "t", 0.0)
        ramp = N.new("ShaderNodeValToRGB")
        L.new(att.outputs["Fac"], ramp.inputs["Fac"])
        cr = ramp.color_ramp
        cr.elements[0].position, cr.elements[0].color = 0.0, (*lin(color_stops[0]), 1)
        cr.elements[1].position, cr.elements[1].color = 1.0, (*lin(color_stops[-1]), 1)
        if len(color_stops) == 3:
            e = cr.elements.new(0.5)
            e.color = (*lin(color_stops[1]), 1)
        # mask = (u < p) with a soft head
        sub = N.new("ShaderNodeMath")
        sub.operation = "SUBTRACT"
        L.new(p.outputs[0], sub.inputs[0])
        L.new(att.outputs["Fac"], sub.inputs[1])
        mul = N.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.use_clamp = True
        mul.inputs[1].default_value = 60.0
        L.new(sub.outputs[0], mul.inputs[0])
        # head glint: bright spot where u is just behind p while the thread is growing
        head = N.new("ShaderNodeMath")
        head.operation = "MULTIPLY"
        head.inputs[1].default_value = -4000.0
        sq = N.new("ShaderNodeMath")
        sq.operation = "MULTIPLY"
        L.new(sub.outputs[0], sq.inputs[0])
        L.new(sub.outputs[0], sq.inputs[1])
        L.new(sq.outputs[0], head.inputs[0])
        ex = N.new("ShaderNodeMath")
        ex.operation = "EXPONENT"
        L.new(head.outputs[0], ex.inputs[0])
        # travelling pulse: bump of fract(u*2 - t)
        pu = N.new("ShaderNodeMath")
        pu.operation = "MULTIPLY"
        pu.inputs[1].default_value = 2.0
        L.new(att.outputs["Fac"], pu.inputs[0])
        ps = N.new("ShaderNodeMath")
        ps.operation = "SUBTRACT"
        L.new(pu.outputs[0], ps.inputs[0])
        L.new(t.outputs[0], ps.inputs[1])
        fr = N.new("ShaderNodeMath")
        fr.operation = "FRACT"
        L.new(ps.outputs[0], fr.inputs[0])
        sine = N.new("ShaderNodeMath")
        sine.operation = "SINE"
        mulpi = N.new("ShaderNodeMath")
        mulpi.operation = "MULTIPLY"
        mulpi.inputs[1].default_value = math.pi
        L.new(fr.outputs[0], mulpi.inputs[0])
        L.new(mulpi.outputs[0], sine.inputs[0])
        pw = N.new("ShaderNodeMath")
        pw.operation = "POWER"
        pw.inputs[1].default_value = 6.0
        L.new(sine.outputs[0], pw.inputs[0])
        # strength = base*(0.5 + 3*pulse*travel) + 6*head
        pk = N.new("ShaderNodeMath")
        pk.operation = "MULTIPLY_ADD"
        pk.inputs[1].default_value = 3.0 if travel else 0.0
        pk.inputs[2].default_value = 0.6
        L.new(pw.outputs[0], pk.inputs[0])
        hk = N.new("ShaderNodeMath")
        hk.operation = "MULTIPLY_ADD"
        hk.inputs[1].default_value = 2.5
        L.new(ex.outputs[0], hk.inputs[0])
        L.new(pk.outputs[0], hk.inputs[2])
        em = N.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = strength
        L.new(ramp.outputs["Color"], em.inputs["Color"])
        s2 = N.new("ShaderNodeMath")
        s2.operation = "MULTIPLY"
        L.new(hk.outputs[0], s2.inputs[0])
        s2.inputs[1].default_value = strength
        L.new(s2.outputs[0], em.inputs["Strength"])
        tr = N.new("ShaderNodeBsdfTransparent")
        mix = N.new("ShaderNodeMixShader")
        mm = N.new("ShaderNodeMath")
        mm.operation = "MINIMUM"
        mm.inputs[1].default_value = mask_max
        L.new(mul.outputs[0], mm.inputs[0])
        # also respect the mask ceiling on u (partial rim): zero where u > mask_max handled by caller's p ceiling
        L.new(mm.outputs[0], mix.inputs[0])
        L.new(tr.outputs[0], mix.inputs[1])
        L.new(em.outputs[0], mix.inputs[2])
        out = N.new("ShaderNodeOutputMaterial")
        L.new(mix.outputs[0], out.inputs["Surface"])
        mat.cycles.emission_sampling = "NONE"  # thin glows: lit by the tile lights, not sampled as mesh lights
        return mat, p, t

    # ------------------------------------------------------------------ fonts
    font = bpy.data.fonts.load(str(repo / FONT))

    def text(name, body, size, mat, pos, extrude=0.004, align="LEFT"):
        cu = bpy.data.curves.new(name, "FONT")
        cu.body = body
        cu.font = font
        cu.size = size
        cu.extrude = extrude
        cu.align_x = align
        cu.resolution_u = 3
        tmp = bpy.data.objects.new(name + "_curve", cu)
        coll.objects.link(tmp)
        me = bpy.data.meshes.new_from_object(tmp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        bpy.data.objects.remove(tmp)
        me.materials.clear()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)  # a static mesh: no re-tessellation per frame
        ob.location = pos
        coll.objects.link(ob)
        return ob

    # ------------------------------------------------------------------ the ghost pages (real scans, thin slabs)
    def sheet(name, img, pos, h, rot, tint, curl, twist, seed):
        w = h / 1.505
        verts, uv = curl_grid(w, h, 28, 40, curl, twist)
        faces = grid_faces(28, 40)
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts.tolist(), [], faces)
        uvl = me.uv_layers.new(name="uv")
        for poly in me.polygons:
            for li, vi in zip(poly.loop_indices, poly.vertices):
                uvl.data[li].uv = tuple(uv[vi])
        me.shade_smooth()
        mat = bpy.data.materials.new(name)
        nt = mat.node_tree
        nt.nodes.clear()
        N, L = nt.nodes, nt.links
        tex = N.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(repo / SHEETS / img))
        tex.image.colorspace_settings.name = "sRGB"
        tex.interpolation = "Cubic"
        mulc = N.new("ShaderNodeMix")
        mulc.data_type = "RGBA"
        mulc.blend_type = "MULTIPLY"
        mulc.inputs[0].default_value = 1.0
        mulc.inputs[7].default_value = (*lin("fg")[:3], 1.0)
        mulc.inputs[7].default_value = tuple(c * tint for c in lin("fg")) + (1.0,)
        L.new(tex.outputs["Color"], mulc.inputs[6])
        b = N.new("ShaderNodeBsdfPrincipled")
        L.new(mulc.outputs[2], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.78
        b.inputs["Sheen Weight"].default_value = 0.3
        out = N.new("ShaderNodeOutputMaterial")
        L.new(b.outputs[0], out.inputs["Surface"])
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = pos
        ob.rotation_euler = rot
        sol = ob.modifiers.new("thick", "SOLIDIFY")
        sol.thickness = 0.004
        coll.objects.link(ob)
        return ob, mat

    sheet("page_a", "hires_38189_p01.jpg", (-1.35, 1.5, 0.05), 3.3, (0.0, 0.0, math.radians(2.0)), 0.2, 0.30,
          0.10, 1)
    sheet("page_b", "hires_38189_p02.jpg", (-3.9, 2.4, 0.3), 3.3, (0.0, 0.0, math.radians(-4)), 0.07, 0.25, 0.1, 2)

    # ------------------------------------------------------------------ the answer lines (typeset)
    paper = materials.satin("fg", roughness=0.5, coat=0.15, sheen=0.1, name="type")
    paper.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = tuple(c * 0.9 for c in lin("fg")) + (1,)
    line_obs = []
    LX, LZ0, LDZ = -2.35, 0.95, -0.34
    dim = materials.satin("fgDim", roughness=0.5, coat=0.1, sheen=0.1, name="type_dim")
    for i, (body, tile) in enumerate(LINES):
        ob = text(f"line{i}", body, 0.17, paper if tile is not None else dim, (LX, 0.35, LZ0 + i * LDZ),
                  extrude=0.006)
        ob.rotation_euler = (math.radians(90), 0, 0)
        line_obs.append(ob)
    bpy.context.view_layer.update()
    line_w = [max(ob.dimensions.x, 0.5) for ob in line_obs]
    # lines rise in, faintly, at the start (they are the continuing transcription)

    # ------------------------------------------------------------------ the key-point tiles
    frame_path = rounded_rect(TILE_W + 0.04, TILE_H + 0.04, 0.07)
    rv, rf, ru = tube(frame_path, 0.0045, seg=8, closed=True)
    tiles = []
    for i, label in enumerate(LABELS):
        full = i < 3
        z = TILE_Z0 + i * TILE_DZ
        y = 0.1 + 0.28 * ((i % 2) - 0.5)
        accent = "accent" if full else "accent2"
        # glass slab: a bevelled box
        me = bpy.data.meshes.new(f"glass{i}")
        me.from_pydata([(-.5, -.5, -.5), (.5, -.5, -.5), (.5, .5, -.5), (-.5, .5, -.5),
                        (-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)], [],
                       [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (3, 0, 4, 7)])
        gl = bpy.data.objects.new(f"glass{i}", me)
        gl.scale = (TILE_W, TILE_T, TILE_H)
        bev = gl.modifiers.new("bev", "BEVEL")
        bev.width = 0.04
        bev.segments = 3
        bev.limit_method = "ANGLE"
        gl.location = (TILE_X, y, z)
        coll.objects.link(gl)
        for poly in me.polygons:
            poly.use_smooth = True
        gmat_ = bpy.data.materials.new(f"glass{i}")
        nt = gmat_.node_tree
        b = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        b.inputs["Base Color"].default_value = (*lin("fg"), 1)
        b.inputs["Roughness"].default_value = 0.32  # frosted
        b.inputs["Transmission Weight"].default_value = 1.0
        b.inputs["IOR"].default_value = 1.45
        b.inputs["Specular IOR Level"].default_value = 0.6
        gfade = with_fade(gmat_, 0.0)
        me.materials.append(gmat_)
        # the lit core: a soft emissive card just behind the glass's centre
        cm = bpy.data.meshes.new(f"core{i}")
        cm.from_pydata([(-.5, 0, -.5), (.5, 0, -.5), (.5, 0, .5), (-.5, 0, .5)], [], [(0, 1, 2, 3)])
        core = bpy.data.objects.new(f"core{i}", cm)
        core.scale = (TILE_W * 0.9, 1, TILE_H * 0.8)
        core.location = (TILE_X, y + 0.03, z)
        coll.objects.link(core)
        cmat = materials.emission(accent, 0.0, name=f"core{i}")
        cmat.cycles.emission_sampling = "NONE"
        cm.materials.append(cmat)
        cnode = next(n for n in cmat.node_tree.nodes if n.bl_idname == "ShaderNodeEmission")
        # rim: thin outline whose lit fraction grows from the thread's arrival point
        rme = bpy.data.meshes.new(f"rim{i}")
        rme.from_pydata((rv + np.array([TILE_X, y - TILE_T / 2 - 0.004, z])).tolist(), [], rf)
        rme.shade_smooth()
        rme.attributes.new("u", "FLOAT", "POINT").data.foreach_set("value", ru)
        stops = ["accentBright", "accent", "accentBright"] if full else ["accent2Bright", "accent2", "accent2Bright"]
        rmat, rp, rt = emit_mat(f"rim{i}", stops, 1.5 if full else 0.9, travel=full)
        rme.materials.append(rmat)
        rim = bpy.data.objects.new(f"rim{i}", rme)
        coll.objects.link(rim)
        # label
        lab_mat = materials.satin("fg", roughness=0.45, coat=0.1, sheen=0.0, name=f"label{i}")
        lab = text(f"label{i}", label, 0.085, lab_mat, (TILE_X - TILE_W / 2 + 0.09, y - TILE_T / 2 - 0.012,
                                                        z - 0.03), extrude=0.003)
        lab.rotation_euler = (math.radians(90), 0, 0)
        lfade = with_fade(lab_mat, 0.0)
        # light the surroundings from the tile (energy keyed)
        ld = bpy.data.lights.new(f"tile_light{i}", "AREA")
        ld.shape, ld.size = "RECTANGLE", TILE_W
        ld.size_y = TILE_H
        ld.color = lin(accent)
        ld.energy = 0.0
        ld.use_shadow = False
        lo = bpy.data.objects.new(f"tile_light{i}", ld)
        lo.location = (TILE_X, y + 0.30, z)
        lo.rotation_euler = (math.radians(-90), 0, 0)
        coll.objects.link(lo)
        tiles.append(dict(full=full, y=y, z=z, gfade=gfade, lfade=lfade, cnode=cnode, rp=rp, rt=rt, light=ld,
                          gl=gl, core=core, rim=rim, lab=lab))

    # ------------------------------------------------------------------ the threads
    for i, (body, tile) in enumerate(LINES):
        if tile is None:
            continue
        T = tiles[tile]
        ob = line_obs[i]
        p0 = np.array([LX + line_w[i] + 0.08, 0.30, LZ0 + i * LDZ + 0.085])
        p3 = np.array([TILE_X - TILE_W / 2 - 0.03, T["y"] - 0.02, T["z"]])
        dz = p3[2] - p0[2]
        c = bezier(p0, p0 + np.array([0.9, -0.55, 0.25 * np.sign(dz) + 0.1]),
                   p3 - np.array([0.9, -0.5 - 0.1 * tile, 0.0]), p3, 140)
        verts, faces, u = tube(c, 0.0065, seg=6)
        me = bpy.data.meshes.new(f"thread{tile}")
        me.from_pydata(verts.tolist(), [], faces)
        me.shade_smooth()
        me.attributes.new("u", "FLOAT", "POINT").data.foreach_set("value", u)
        stops = ["accentDim", "accent", "accent2Bright"] if tile < 3 else ["accentDim", "accent2", "accent2Bright"]
        mat, p, t = emit_mat(f"thread{tile}", stops, 3.2, travel=True)
        me.materials.append(mat)
        th = bpy.data.objects.new(f"thread{tile}", me)
        coll.objects.link(th)
        # a small bloom bead at the head is the 'head' term of the shader; keys:
        t0, t1 = F(THREAD_T[tile]), F(THREAD_T[tile] + THREAD_D)
        key(p.outputs[0], first, 0.0)
        key(p.outputs[0], t0, 0.0)
        key(p.outputs[0], t1, 1.02)
        key(p.outputs[0], last, 1.02)
        key(t.outputs[0], first, 0.0)
        key(t.outputs[0], last, 3.0)
        # the tile: fade in a beat before the thread leaves, light as it arrives
        a0 = max(0.0, THREAD_T[tile] - 0.9)
        for nd in (T["gfade"], T["lfade"]):
            key(nd.outputs[0], first, 0.0)
            key(nd.outputs[0], F(a0), 0.0)
            key(nd.outputs[0], F(a0 + 0.7), 1.0)
            key(nd.outputs[0], last, 1.0)
        lit = 1.0 if T["full"] else 0.4
        # the rim ignites at arrival: its own progress runs 0..(1 | 0.55 for the partial tile)
        reach = 1.02 if T["full"] else 0.55
        for nd, node in ((T["rp"], None),):
            key(nd.outputs[0], first, 0.0)
            key(nd.outputs[0], t1 - 3, 0.0)
            key(nd.outputs[0], t1 + 12, reach)
            key(nd.outputs[0], last, reach)
        key(T["rt"].outputs[0], first, 0.0)
        key(T["rt"].outputs[0], last, 2.0)
        es = T["cnode"].inputs["Strength"]
        key(es, first, 0.0)
        key(es, t1 - 2, 0.0)
        key(es, t1 + 14, 0.14 * lit if T["full"] else 0.06)
        key(es, last, 0.14 * lit if T["full"] else 0.06)
        ls = T["light"]
        for f, v in ((first, 0.0), (t1 - 2, 0.0), (t1 + 14, 14.0 * lit), (last, 14.0 * lit)):
            ls.energy = v
            ls.keyframe_insert("energy", frame=f)
        # tiles drift up a little as they arrive
        g = T["gl"]
        for ob in (g, T["core"], T["rim"], T["lab"]):
            pass

    # ------------------------------------------------------------------ the floor of space: none; lights
    lights.studio(key=None, rim=None, fill=None, world="bg", world_strength=0.4)
    key_l = lights._light("key", "AREA", 150.0, Vector((-3.4, -3.2, 2.6)), Vector((-1.2, 0.5, 0.0)), size=2.4,
                          temperature=6000)
    lights._light("fill", "AREA", 25.0, Vector((3.2, -3.0, -0.8)), Vector((0.8, 0.3, -0.2)), size=3.0,
                  temperature=6500)
    # a cool-warm rim from behind lifts the tiles' glass edges and the page edges
    rim_l = lights._light("rim", "SPOT", 900.0, Vector((3.4, 2.6, 1.4)), Vector((1.0, 0.1, -0.2)), spot_size=0.7,
                          soft=0.05, temperature=7000)

    import os
    abl = os.environ.get("MARK3D_ABL", "")
    if "pages" in abl:
        for o in list(bpy.data.objects):
            if o.name.startswith("page"):
                bpy.data.objects.remove(o)
    if "glass" in abl:
        for o in list(bpy.data.objects):
            if o.name.startswith("glass"):
                bpy.data.objects.remove(o)
    if "mb" in abl:
        scene.render.use_motion_blur = False
    # ------------------------------------------------------------------ camera: a slow arc, answers -> key points
    target = Vector((-0.05, 0.3, -0.05))
    dist = 6.6
    pivot = bpy.data.objects.new("orbit", None)
    pivot.location = tuple(target)
    coll.objects.link(pivot)
    a0, a1 = -17.0, 13.0
    for f, a in ((first, a0 + (a1 - a0) * (first - ctx.f0) / (last - ctx.f0)), (last, a1)):
        pivot.rotation_euler = (0, 0, math.radians(a))
        pivot.keyframe_insert("rotation_euler", frame=f)
    cam = rig.engine_camera("camera", fstop=2.0, size=ctx.size)
    cam.data.lens = rig.lens_mm(26.0)
    focus = bpy.data.objects.new("focus", None)
    coll.objects.link(focus)
    # rack focus: the answer lines first, the key points at the end
    for f, pos in ((first, (-1.5, 0.35, 0.3)), (F(2.2), (-0.2, 0.3, 0.0)), (last, (TILE_X, 0.1, -0.3))):
        focus.location = pos
        focus.keyframe_insert("location", frame=f)
    cam.data.dof.focus_object = focus
    cam.parent = pivot
    elev = math.radians(5.0)
    cam.location = Vector((0.0, -dist * math.cos(elev), dist * math.sin(elev)))
    cam.rotation_euler = (-cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    cam.data.clip_end = 60.0
    if "dof" in abl:
        cam.data.dof.use_dof = False


def _repo_root():
    from pathlib import Path
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "blender" / "render.py").exists():
            return parent
    return p.parents[4]
