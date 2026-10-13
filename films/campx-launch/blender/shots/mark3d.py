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
FONT = "app/public/fonts/Geist-500.ttf"  # the engine's text face (Inter is not in the repo)

LABELS = ["Augmented matrix formed", "Row-reduced to echelon form", "Rank of the matrix = 3",
          "Solution: x = 1, y = 1, z = 1"]
# the typeset answer lines, continuing read3d's transcription of hires_38189_p02: (text, tile it threads to or None)
LINES = [("the Augmented matrix AB is", 0), ("By using Elementary row operations", None),
         ("to reduce the matrix into Echelon form.", 1), ("R2 \u2192 R2 \u2212 2R1", None),
         ("the rank of the matrix = 3", 2), ("x = 1, y = 1, z = 1", 3)]
# seconds into the shot (film 49.0 s), on the VO: the tiles appear under "Each answer is checked against your answer
# key," (49.5-51.75 s); the threads land one by one on "point by point." (51.9, 52.25, 52.6, 53.0 s); then a calm hold
# under "Medha suggests a mark," while the engine lands its pill top right (54.6 s). The cut is at 55.0 s.
TILE_IN = [0.5 + 0.5 * i for i in range(4)]  # tile i starts fading in (0.7 s)
THREAD_ARRIVE = [2.9, 3.25, 3.6, 4.0]
THREAD_D = 0.65  # each thread's flight
TILE_W, TILE_H, TILE_T = 2.3, 0.48, 0.05
TILE_X, TILE_Z0, TILE_DZ = 1.6, 0.42, -0.64
LINE_X, LINE_Z0, LINE_DZ, LINE_EM = -3.25, 1.2, -0.52, 0.165
LABEL_EM = 0.15


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
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 6, 2, 3
    cy.transmission_bounces, cy.transparent_max_bounces, cy.volume_bounces = 6, 8, 0
    cy.caustics_reflective = cy.caustics_refractive = False

    def lin(c):
        return tuple(c) if isinstance(c, (tuple, list)) else theme.linear(c)

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

    # the ghost of the handwritten page (read3d's page) and one more behind it
    sheet("page_a", "hires_38189_p02.jpg", (-2.1, 2.0, -0.05), 4.5, (0.0, 0.0, math.radians(3.0)), 0.065, 0.28,
          0.10, 1)
    sheet("page_b", "hires_38189_p01.jpg", (-4.6, 3.2, 0.5), 4.3, (0.0, 0.0, math.radians(-5)), 0.05, 0.25, 0.1, 2)

    # ------------------------------------------------------------------ the answer lines (read3d's typeset style)
    def typeset_mat(name, role, glow):
        """read3d's typeset material: fg faces, a faint accent glow on the side walls."""
        m = bpy.data.materials.new(name)
        nt = m.node_tree
        nt.nodes.clear()
        N, L = nt.nodes.new, nt.links.new
        b = N("ShaderNodeBsdfPrincipled")
        b.inputs["Base Color"].default_value = (*lin(role), 1.0)
        b.inputs["Roughness"].default_value = 0.3
        b.inputs["Coat Weight"].default_value = 0.5
        geo = N("ShaderNodeNewGeometry")
        dot = N("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        dot.inputs[1].default_value = (0.0, 0.0, 1.0)  # the text's own face normal (local z, before rotation)
        tc = N("ShaderNodeVectorTransform")
        tc.vector_type, tc.convert_from, tc.convert_to = "NORMAL", "WORLD", "OBJECT"
        L(geo.outputs["Normal"], tc.inputs["Vector"])
        L(tc.outputs["Vector"], dot.inputs[0])
        ab = N("ShaderNodeMath")
        ab.operation = "ABSOLUTE"
        L(dot.outputs["Value"], ab.inputs[0])
        inv = N("ShaderNodeMath")
        inv.operation, inv.use_clamp = "SUBTRACT", True
        inv.inputs[0].default_value = 1.0
        L(ab.outputs["Value"], inv.inputs[1])
        sq = N("ShaderNodeMath")
        sq.operation = "POWER"
        sq.inputs[1].default_value = 3.0
        L(inv.outputs["Value"], sq.inputs[0])
        b.inputs["Emission Color"].default_value = (*lin("accent"), 1.0)
        mg = N("ShaderNodeMath")
        mg.operation = "MULTIPLY"
        mg.inputs[1].default_value = glow
        L(sq.outputs["Value"], mg.inputs[0])
        L(mg.outputs["Value"], b.inputs["Emission Strength"])
        out = N("ShaderNodeOutputMaterial")
        L(b.outputs["BSDF"], out.inputs["Surface"])
        return m

    type_hi = typeset_mat("type", "fg", 2.0)
    type_lo = typeset_mat("type_dim", "fgDim", 0.6)
    line_obs = []
    for i, (body, tile) in enumerate(LINES):
        ob = text(f"line{i}", body, LINE_EM, type_hi if tile is not None else type_lo,
                  (LINE_X, 0.35, LINE_Z0 + i * LINE_DZ), extrude=0.004)
        ob.rotation_euler = (math.radians(90), 0, 0)
        line_obs.append(ob)
    bpy.context.view_layer.update()
    line_w = [max(ob.dimensions.x, 0.5) for ob in line_obs]

    # ------------------------------------------------------------------ the key-point tiles
    fg, a2 = np.array(lin("fg")), np.array(lin("accent2"))
    warm = tuple((0.55 * a2 + 0.45 * fg * np.array([1.0, 0.62, 0.28])).tolist())  # amber from accent2 + warm fg
    frame_path = rounded_rect(TILE_W, TILE_H, 0.09)
    rv, rf, ru = tube(frame_path, 0.0017, seg=8, closed=True)

    def plane(name, w, h, loc):
        me = bpy.data.meshes.new(name)
        me.from_pydata([(-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2)], [],
                       [(0, 1, 2, 3)])
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        coll.objects.link(ob)
        return ob

    def glow_card_mat(name, dim_role, lit_col, gain, half):
        """The tile's inner light: a soft horizontal gradient (brightest where the thread arrives, on the left), dim
        accentDim at rest, `lit_col` x `gain` when 'lit' is 1; `half` lights only the left half (partial credit)."""
        m = bpy.data.materials.new(name)
        m.cycles.emission_sampling = "NONE"
        nt = m.node_tree
        nt.nodes.clear()
        N, L = nt.nodes.new, nt.links.new
        lit = value_node(nt, "lit", 0.0)
        fade = value_node(nt, "fade", 0.0)
        tcn = N("ShaderNodeTexCoord")
        sep = N("ShaderNodeSeparateXYZ")
        L(tcn.outputs["Generated"], sep.inputs[0])
        gx = N("ShaderNodeMapRange")  # x 0..1 -> 1..0.15
        gx.inputs["To Min"].default_value, gx.inputs["To Max"].default_value = 1.0, 0.15
        L(sep.outputs["X"], gx.inputs["Value"])
        gz = N("ShaderNodeMath")  # a soft vertical falloff: 1 - (2z - 1)^2
        gz.operation = "MULTIPLY_ADD"
        gz.inputs[1].default_value, gz.inputs[2].default_value = 2.0, -1.0
        L(sep.outputs["Z"], gz.inputs[0])
        gz2 = N("ShaderNodeMath")
        gz2.operation = "MULTIPLY"
        L(gz.outputs[0], gz2.inputs[0])
        L(gz.outputs[0], gz2.inputs[1])
        gz3 = N("ShaderNodeMath")
        gz3.operation, gz3.use_clamp = "SUBTRACT", True
        gz3.inputs[0].default_value = 1.0
        L(gz2.outputs[0], gz3.inputs[1])
        gp = N("ShaderNodeMath")
        gp.operation = "POWER"
        gp.inputs[1].default_value = 2.0
        L(gx.outputs[0], gp.inputs[0])
        g = N("ShaderNodeMath")
        g.operation = "MULTIPLY"
        L(gp.outputs[0], g.inputs[0])
        L(gz3.outputs[0], g.inputs[1])
        if half:
            hm = N("ShaderNodeMapRange")  # 1 left of 0.42, 0 right of 0.58
            hm.inputs["From Min"].default_value, hm.inputs["From Max"].default_value = 0.42, 0.58
            hm.inputs["To Min"].default_value, hm.inputs["To Max"].default_value = 1.0, 0.0
            hm.interpolation_type = "SMOOTHSTEP"
            L(sep.outputs["X"], hm.inputs["Value"])
            g2 = N("ShaderNodeMath")
            g2.operation = "MULTIPLY"
            L(g.outputs[0], g2.inputs[0])
            L(hm.outputs[0], g2.inputs[1])
            g = g2
        mix = N("ShaderNodeMix")
        mix.data_type = "RGBA"
        L(lit.outputs[0], mix.inputs[0])
        mix.inputs[6].default_value = (*lin(dim_role), 1)
        mix.inputs[7].default_value = (*lit_col, 1)
        st = N("ShaderNodeMath")  # 0.35 at rest -> gain when lit
        st.operation = "MULTIPLY_ADD"
        st.inputs[1].default_value, st.inputs[2].default_value = gain - 0.35, 0.35
        L(lit.outputs[0], st.inputs[0])
        s1 = N("ShaderNodeMath")
        s1.operation = "MULTIPLY"
        L(st.outputs[0], s1.inputs[0])
        L(g.outputs[0], s1.inputs[1])
        s2 = N("ShaderNodeMath")
        s2.operation = "MULTIPLY"
        L(s1.outputs[0], s2.inputs[0])
        L(fade.outputs[0], s2.inputs[1])
        em = N("ShaderNodeEmission")
        L(mix.outputs[2], em.inputs["Color"])
        L(s2.outputs[0], em.inputs["Strength"])
        out = N("ShaderNodeOutputMaterial")
        L(em.outputs[0], out.inputs["Surface"])
        return m, lit, fade

    def flat_mesh(name, verts, faces, loc, u=None):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in verts], [], faces)
        me.shade_smooth()
        if u is not None:
            me.attributes.new("u", "FLOAT", "POINT").data.foreach_set("value", u)
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        coll.objects.link(ob)
        return ob

    tiles = []
    for i, label in enumerate(LABELS):
        full = i < 3
        z = TILE_Z0 + i * TILE_DZ
        y = 0.1 + 0.22 * ((i % 2) - 0.5)
        col = lin("accent") if full else warm
        front = y - TILE_T / 2
        # frosted dark glass: a bevelled slab
        me = bpy.data.meshes.new(f"glass{i}")
        me.from_pydata([(-.5, -.5, -.5), (.5, -.5, -.5), (.5, .5, -.5), (-.5, .5, -.5),
                        (-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)], [],
                       [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (3, 0, 4, 7)])
        for poly in me.polygons:
            poly.use_smooth = True
        gl = bpy.data.objects.new(f"glass{i}", me)
        gl.scale = (TILE_W, TILE_T, TILE_H)
        bev = gl.modifiers.new("bev", "BEVEL")
        bev.width, bev.segments, bev.limit_method = 0.022, 4, "ANGLE"
        bev.harden_normals = False
        gl.location = (TILE_X, y, z)
        coll.objects.link(gl)
        gm = bpy.data.materials.new(f"glass{i}")
        b = next(n for n in gm.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        b.inputs["Base Color"].default_value = (*(c * 0.75 for c in lin("fgDim")), 1)
        b.inputs["Roughness"].default_value = 0.3
        b.inputs["Transmission Weight"].default_value = 1.0
        b.inputs["IOR"].default_value = 1.45
        b.inputs["Coat Weight"].default_value = 0.6
        b.inputs["Coat Roughness"].default_value = 0.04
        gfade = with_fade(gm, 0.0)
        me.materials.append(gm)
        # the inner glow, just behind the glass
        card = plane(f"card{i}", TILE_W - 0.08, TILE_H - 0.06, (TILE_X, y + TILE_T / 2 + 0.012, z))
        cmat, clit, cfade = glow_card_mat(f"card{i}", "accentDim", col, 0.38 if full else 0.34, not full)
        card.data.materials.append(cmat)
        # the rim: a hairline on the front edge, lit from the thread's arrival point round the tile
        rim = flat_mesh(f"rim{i}", rv + np.array([TILE_X, front - 0.002, z]), rf, (0, 0, 0), ru)
        stops = ["accentBright", "accent", "accentBright"] if full else [warm, warm, warm]
        rmat, rp, rt = emit_mat(f"rim{i}", stops, 1.6 if full else 1.0)
        rim.data.materials.append(rmat)
        # the label: Geist Medium in warm white, legible at 1080p
        lab_mat = materials.satin("fg", roughness=0.4, coat=0.2, sheen=0.0, name=f"label{i}")
        lab = text(f"label{i}", label, LABEL_EM, lab_mat,
                   (TILE_X - TILE_W / 2 + 0.2, front - 0.006, z - LABEL_EM * 0.34), extrude=0.003)
        lab.rotation_euler = (math.radians(90), 0, 0)
        lfade = with_fade(lab_mat, 0.0)
        # the mark: a check in a ring (full), or a ring half filled (partial)
        cx, cz = TILE_X + TILE_W / 2 - 0.26, z
        th = np.linspace(math.pi / 2, math.pi / 2 + 2 * math.pi, 96, endpoint=False)
        ring_c = np.column_stack([0.105 * np.cos(th), np.zeros_like(th), 0.105 * np.sin(th)])
        rv2, rf2, _ = tube(ring_c, 0.0042, seg=8, closed=True)
        ring = flat_mesh(f"ring{i}", rv2 + np.array([cx, front - 0.004, cz]), rf2, (0, 0, 0),
                         np.repeat(np.arange(96) / 96, 8))
        mark_stops = ["accentBright", "accentBright"] if full else [warm, warm]
        ringm, ring_p, _ = emit_mat(f"ring{i}", mark_stops, 2.2 if full else 1.4)
        ring.data.materials.append(ringm)
        marks = [(ring_p, 1.02)]
        if full:
            chk = np.array([[-0.05, 0, 0.0], [-0.015, 0, -0.038], [0.055, 0, 0.042]])
            chk = np.vstack([chk[0] + (chk[1] - chk[0]) * s for s in np.linspace(0, 1, 12)] +
                            [chk[1] + (chk[2] - chk[1]) * s for s in np.linspace(0, 1, 20)[1:]])
            cv, cf, cu = tube(chk, 0.0065, seg=8)
            ck = flat_mesh(f"check{i}", cv + np.array([cx, front - 0.006, cz]), cf, (0, 0, 0), cu)
            ckm, ck_p, _ = emit_mat(f"check{i}", mark_stops, 3.0)
            ck.data.materials.append(ckm)
            marks.append((ck_p, 1.05))
        else:
            hv = [(0.0, 0.0, 0.0)] + [(0.085 * math.cos(a), 0.0, 0.085 * math.sin(a))
                                      for a in np.linspace(math.pi / 2, 3 * math.pi / 2, 33)]
            hf = [(0, k, k + 1) for k in range(1, 33)]
            half = flat_mesh(f"half{i}", hv, hf, (cx, front - 0.004, cz))
            hm = materials.emission("accent2", 0.0, name=f"half{i}")
            hm.cycles.emission_sampling = "NONE"
            hn = next(n for n in hm.node_tree.nodes if n.bl_idname == "ShaderNodeEmission")
            hn.inputs["Color"].default_value = (*warm, 1)
            hn.inputs["Strength"].default_value = 1.3
            hfade = with_fade(hm, 0.0)
            half.data.materials.append(hm)
            marks.append((hfade, 1.0))
        # light the surroundings from behind the tile (energy keyed)
        ld = bpy.data.lights.new(f"tile_light{i}", "AREA")
        ld.shape, ld.size, ld.size_y = "RECTANGLE", TILE_W, TILE_H
        ld.color = col
        ld.energy = 0.0
        lo = bpy.data.objects.new(f"tile_light{i}", ld)
        lo.location = (TILE_X, y + 0.7, z)
        lo.rotation_euler = (math.radians(-90), 0, 0)
        coll.objects.link(lo)
        tiles.append(dict(full=full, y=y, z=z, fades=(gfade, lfade, cfade), lit=clit, rp=rp, light=ld,
                          marks=marks))

    # ------------------------------------------------------------------ the threads, and the keys
    for i, (body, tile) in enumerate(LINES):
        if tile is None:
            continue
        T = tiles[tile]
        p0 = np.array([LINE_X + line_w[i] + 0.12, 0.33, LINE_Z0 + i * LINE_DZ + LINE_EM * 0.34])
        p3 = np.array([TILE_X - TILE_W / 2 - 0.02, T["y"] - TILE_T / 2 - 0.004, T["z"]])
        dx = p3[0] - p0[0]
        c = bezier(p0, p0 + np.array([0.45 * dx, -0.6, 0.12]), p3 - np.array([0.4 * dx, -0.45 - 0.08 * tile, 0.0]),
                   p3, 160)
        verts, faces, u = tube(c, 0.0075, seg=8)
        stops = ["accentDim", "accent", "accent2Bright"] if tile < 3 else ["accentDim", "accent2", warm]
        mat, p, t = emit_mat(f"thread{tile}", stops, 3.0, travel=True)
        thr = flat_mesh(f"thread{tile}", verts, faces, (0, 0, 0), u)
        thr.data.materials.append(mat)
        t0, t1 = F(THREAD_ARRIVE[tile] - THREAD_D), F(THREAD_ARRIVE[tile])
        for f, v in ((first, 0.0), (t0, 0.0), (t1, 1.02), (last, 1.02)):
            key(p.outputs[0], f, v)
        key(t.outputs[0], first, 0.0)
        key(t.outputs[0], last, 2.4)
        # the tile fades in a beat before its thread leaves
        a0 = TILE_IN[tile]
        for nd in T["fades"]:
            for f, v in ((first, 0.0), (F(a0), 0.0), (F(a0 + 0.7), 1.0), (last, 1.0)):
                key(nd.outputs[0], f, v)
        # ... and lights as it arrives: the inner glow, the rim from the arrival point, then the mark
        for f, v in ((first, 0.0), (t1 - 2, 0.0), (t1 + 13, 1.0), (last, 1.0)):
            key(T["lit"].outputs[0], f, v)
        reach = 1.02 if T["full"] else 0.5
        for f, v in ((first, 0.0), (t1 - 3, 0.0), (t1 + 12, reach), (last, reach)):
            key(T["rp"].outputs[0], f, v)
        for k, (sock, top) in enumerate(T["marks"]):
            s0 = t1 + 5 + 7 * k
            for f, v in ((first, 0.0), (s0, 0.0), (s0 + 10, top), (last, top)):
                key(sock.outputs[0] if hasattr(sock, "outputs") else sock, f, v)
        ls = T["light"]
        for f, v in ((first, 0.0), (t1 - 2, 0.0), (t1 + 13, 5.0 if T["full"] else 2.5),
                     (last, 5.0 if T["full"] else 2.5)):
            ls.energy = v
            ls.keyframe_insert("energy", frame=f)

    # ------------------------------------------------------------------ light: a soft key on the answers and the
    # page, a hairline strip for crisp highlights on the glass, a rim from behind for the glass edges
    lights.studio(key=None, rim=None, fill=None, world="bg", world_strength=0.5)
    lights._light("key", "AREA", 300.0, Vector((-5.2, -3.6, 3.0)), Vector((-2.6, 0.6, 0.2)), size=2.0,
                  temperature=5600)
    fill = lights._light("fill", "AREA", 30.0, Vector((4.0, -4.0, -1.2)), Vector((1.0, 0.3, -0.4)),
                         temperature=6800)
    fill.data.shape, fill.data.size, fill.data.size_y = "RECTANGLE", 7.0, 2.0  # broad: no disc in the glass
    strip = lights._light("strip", "AREA", 120.0, Vector((1.9, -3.2, 3.6)), Vector((1.9, 0.1, -0.4)),
                          temperature=6500)
    strip.data.shape, strip.data.size, strip.data.size_y = "RECTANGLE", 5.0, 0.12
    rim = lights._light("rim", "AREA", 700.0, Vector((4.8, 3.6, 1.6)), Vector((1.6, 0.1, -0.5)),
                        temperature=7200)
    rim.data.shape, rim.data.size, rim.data.size_y = "RECTANGLE", 0.12, 3.0  # a strip: hairline edge highlights

    # ------------------------------------------------------------------ camera: a slow arc, answers -> key points
    target = Vector((0.05, 0.3, -0.2))
    dist = 8.6
    pivot = bpy.data.objects.new("orbit", None)
    pivot.location = tuple(target)
    coll.objects.link(pivot)
    a0, a1 = -15.0, 11.0
    span = ctx.f1 - ctx.f0
    for f, x in ((first, -0.3), (last, 0.05)):  # the pivot drifts right with the arc: answers, then key points
        pivot.location = (x, target.y, target.z)
        pivot.rotation_euler = (0, 0, math.radians(a0 + (a1 - a0) * (f - ctx.f0) / span))
        pivot.keyframe_insert("rotation_euler", frame=f)
        pivot.keyframe_insert("location", frame=f)
    cam = rig.engine_camera("camera", fstop=1.6, size=ctx.size)
    cam.data.lens = rig.lens_mm(26.0)
    focus = bpy.data.objects.new("focus", None)
    coll.objects.link(focus)
    # rack focus: the answer lines first, the key points by the end
    for f, pos in ((first, (-1.8, 0.35, 0.4)), (F(2.4), (-1.0, 0.33, 0.0)), (F(3.8), (TILE_X - 0.6, 0.1, -0.3)),
                   (last, (TILE_X - 0.4, 0.1, -0.4))):
        focus.location = pos
        focus.keyframe_insert("location", frame=f)
    cam.data.dof.focus_object = focus
    cam.parent = pivot
    elev = math.radians(4.0)
    cam.location = Vector((0.0, -dist * math.cos(elev), dist * math.sin(elev)))
    cam.rotation_euler = (-cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    cam.data.clip_end = 60.0


def _repo_root():
    from pathlib import Path
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "blender" / "render.py").exists():
            return parent
    return p.parents[4]
