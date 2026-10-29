"""Text brushed in with ink: calligraphy that writes itself, stroke after stroke, as a brush lays it down.

A font's glyph is filled outlines; most of a brush-drawn character's strokes are separate islands of it (a Mincho
font's dots, its left-falling sweeps, the parts of a radical). Each island is written as a brush writes a stroke: from
the end it starts at to the end it leaves, along its longest axis (left to right for one that lies across, top to bottom
for one that stands up), its wet front ragged with the bristles' dry brush; the strokes of a character in the order a
hand writes them (top to bottom, then left to right), the characters one after another, each stroke taking time in
proportion to its length.

- `axis(points)`: an island's writing direction and extent (PCA, signed as a hand writes).
- `order(islands)`: the order of a character's islands (top first, then left).
- `schedule(lengths, start, end, gap)`: each stroke's (start, duration) within [start, end], the gaps between them.
- `build(text, font, ...)`: the text in Blender, one character under another (`vertical`) or across, each island a
  stroke with its timing written onto the mesh, and an ink material that reveals it over the scene's time. Returns
  the object (its collection, place and scale are the caller's).

The pure parts are numpy only and tested without Blender.
"""
from __future__ import annotations

import math

import numpy as np


def axis(points) -> tuple[np.ndarray, np.ndarray, float]:
    """(origin, direction, length) of the stroke an island draws: its principal axis through its centre, pointing
    the way a hand writes it (rightward for a stroke more across than up, else downward), origin at its start."""
    P = np.asarray(points, float)[:, :2]
    c = P.mean(0)
    Q = P - c
    if len(P) < 2 or np.allclose(Q, 0):
        return c, np.array([0.0, -1.0]), 0.0
    w, v = np.linalg.eigh(Q.T @ Q)
    d = v[:, int(np.argmax(w))]
    if abs(d[0]) >= abs(d[1]):
        d = d if d[0] > 0 else -d
    else:
        d = d if d[1] < 0 else -d
    s = Q @ d
    return c + d * s.min(), d, float(s.max() - s.min())


def order(islands) -> list[int]:
    """The writing order of a character's islands (each an (n, 2) array of points, y up): by their tops, highest
    first, those within a band of each other left to right."""
    tops = [(float(np.max(np.asarray(p)[:, 1])), float(np.min(np.asarray(p)[:, 0]))) for p in islands]
    if not tops:
        return []
    span = max(t for t, _ in tops) - min(float(np.min(np.asarray(p)[:, 1])) for p in islands)
    band = 0.12 * max(span, 1e-9)
    return sorted(range(len(islands)), key=lambda i: (-round(tops[i][0] / band), tops[i][1]))


def schedule(lengths, start: float, end: float, gap: float = 0.25, *, breaks=(), break_gap: float = 0.0) -> list[tuple[float, float]]:
    """Each stroke's (start, duration) in [start, end]: in turn, each taking time in proportion to its length (a
    short dot never less than a fifth of an average stroke), a pause of `gap` of an average stroke's time between
    them, and `break_gap` more after each stroke index in `breaks` (the end of a character)."""
    L = np.asarray(lengths, float)
    if len(L) == 0:
        return []
    if end <= start:
        raise ValueError("schedule: the strokes need end after start")
    mean = L.mean() if L.mean() > 0 else 1.0
    L = np.maximum(L, 0.2 * mean)
    breaks = {int(i) for i in breaks if 0 <= int(i) < len(L) - 1}
    unit = (end - start) / (L.sum() + (gap * (len(L) - 1) + break_gap * len(breaks)) * mean)
    out, t = [], start
    for i, x in enumerate(L):
        out.append((t, float(x * unit)))
        t += (x + gap * mean + (break_gap * mean if i in breaks else 0.0)) * unit
    return out


def _islands(me):
    """The mesh's islands as lists of vertex indices (faces sharing vertices are one island)."""
    parent = list(range(len(me.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for poly in me.polygons:
        vs = list(poly.vertices)
        for a in vs[1:]:
            ra, rb = find(vs[0]), find(a)
            if ra != rb:
                parent[ra] = rb
    groups = {}
    for i in range(len(me.vertices)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def build(name: str, text: str, font: str, *, coll=None, size: float = 1.0, vertical: bool = True, spacing: float = 1.02,
          start: float = 0.0, end: float = 2.0, gap: float = 0.25, char_gap: float = 0.6, color=(0.012, 0.011, 0.013),
          opacity: float = 1.0, dry: float = 0.5, bleed=(0.08, 0.04, 0.03), scene=None, extrude: float = 0.0):
    """`text` in `font` (a .ttf/.otf path), each character `size` m, one under another (`vertical`) or across, written
    stroke by stroke between `start` and `end` (s of the scene's time; `char_gap` of an average stroke's time between
    characters as well as `gap` between strokes), in an ink of `color` (linear) at `opacity`, its wet front ragged by
    `dry` (0 a clean wipe) and a faint warm `bleed` where the ink has just landed. One mesh object at the origin, the
    text's top centre there (vertical) or its left middle (across), laid in the x-y plane facing +z. Returns it."""
    import bpy

    scene = scene or bpy.context.scene
    fnt = bpy.data.fonts.load(str(font), check_existing=True)
    chars = [c for c in text if not c.isspace()]
    pieces = []          # per character: [(island vertices (k, 3), faces), ...] in the text's frame
    for k, ch in enumerate(chars):
        cu = bpy.data.curves.new(f"{name}-tmp{k}", "FONT")
        cu.body = ch
        cu.font = fnt
        cu.size = size
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        cu.extrude = extrude
        ob = bpy.data.objects.new(f"{name}-tmp{k}", cu)
        scene.collection.objects.link(ob)
        bpy.context.view_layer.update()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        off = np.array([0.0, -k * size * spacing - size / 2, 0.0]) if vertical else np.array([k * size * spacing + size / 2, 0.0, 0.0])
        V = np.array([v.co[:] for v in me.vertices]) + off
        isl = []
        for idx in _islands(me):
            sel = set(idx)
            remap = {v: j for j, v in enumerate(idx)}
            faces = [tuple(remap[v] for v in p.vertices) for p in me.polygons if p.vertices[0] in sel]
            isl.append((V[idx], faces))
        pieces.append(isl)
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)
    # the order and the timing: characters in turn, each one's islands as a hand writes them
    strokes = []
    for k, isl in enumerate(pieces):
        for j in order([v for v, _ in isl]):
            o, d, length = axis(isl[j][0])
            strokes.append((k, isl[j], o, d, length))
    breaks = [i for i, (a, b) in enumerate(zip(strokes, strokes[1:])) if a[0] != b[0]]
    times = schedule([s[4] for s in strokes], start, end, gap, breaks=breaks, break_gap=char_gap)
    verts, faces, us, t0s, durs = [], [], [], [], []
    for (k, (V, F), o, d, length), (ts, td) in zip(strokes, times):
        base = len(verts)
        u = ((V[:, :2] - o) @ d) / max(length, 1e-9)
        verts.extend(map(tuple, V))
        faces.extend(tuple(base + i for i in f) for f in F)
        us.extend(np.clip(u, 0, 1))
        t0s.extend([ts] * len(V))
        durs.extend([td] * len(V))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    for aname, vals in (("brush_u", us), ("brush_t0", t0s), ("brush_dur", durs)):
        a = me.attributes.new(aname, "FLOAT", "POINT")
        a.data.foreach_set("value", np.asarray(vals, np.float32))
    ob = bpy.data.objects.new(name, me)
    (coll or scene.collection).objects.link(ob)
    me.materials.append(ink(f"{name}-ink", color=color, opacity=opacity, dry=dry, bleed=bleed, scene=scene))
    ob.visible_shadow = False
    return ob


def ink(name: str, *, color=(0.012, 0.011, 0.013), opacity: float = 1.0, dry: float = 0.5, bleed=(0.08, 0.04, 0.03),
        scene=None):
    """The brushed ink: a stroke is there where its `brush_u` is behind the brush's front (the scene's time through
    its `brush_t0` and `brush_dur`), the front ragged by streaky noise (`dry`), a warm `bleed` just behind it fading as
    the ink settles, dry-brush streaks thinning it a little along its length."""
    import bpy

    from . import toon

    scene = scene or bpy.context.scene
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    N, L = nt.nodes, nt.links

    def attr(n):
        a = N.new("ShaderNodeAttribute")
        a.attribute_type = "GEOMETRY"
        a.attribute_name = n
        return a.outputs["Fac"]

    def m(op, a, b=0.0, c=None, clamp=False):
        x = N.new("ShaderNodeMath")
        x.operation, x.use_clamp = op, clamp
        for s, v in ((x.inputs[0], a), (x.inputs[1], b), (x.inputs[2], c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                s.default_value = v
            else:
                L.new(v, s)
        return x.outputs[0]

    t = toon.frame_value(nt, scene)
    prog = m("DIVIDE", m("SUBTRACT", t, attr("brush_t0")), attr("brush_dur"))
    tc = N.new("ShaderNodeTexCoord")
    noise = N.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 9.0
    noise.inputs["Detail"].default_value = 6.0
    L.new(tc.outputs["Object"], noise.inputs["Vector"])
    streak = N.new("ShaderNodeTexWave")
    streak.wave_type = "BANDS"
    streak.inputs["Scale"].default_value = 26.0
    streak.inputs["Distortion"].default_value = 6.0
    streak.inputs["Detail"].default_value = 4.0
    L.new(tc.outputs["Object"], streak.inputs["Vector"])
    # where the front is: progress overshoots so the stroke's end fills; the noise rags it
    front = m("SUBTRACT", m("MULTIPLY", prog, 1.0 + 0.25 * dry), m("MULTIPLY_ADD", noise.outputs["Fac"], 0.25 * dry, -0.12 * dry))
    behind = m("SUBTRACT", front, attr("brush_u"))
    on = N.new("ShaderNodeMapRange")
    on.interpolation_type = "SMOOTHSTEP"
    on.inputs["From Min"].default_value = 0.0
    on.inputs["From Max"].default_value = 0.035
    L.new(behind, on.inputs["Value"])
    # dry brush: streaks along the stroke thin the ink where the brush ran dry toward its end
    dryness = m("MULTIPLY", m("MULTIPLY", attr("brush_u"), attr("brush_u")), dry)
    thin = m("SUBTRACT", 1.0, m("MULTIPLY", m("SUBTRACT", 1.0, streak.outputs["Fac"]), m("MULTIPLY", dryness, 0.6)))
    alpha = m("MULTIPLY", m("MULTIPLY", on.outputs["Result"], thin, clamp=True), opacity)
    wet = N.new("ShaderNodeMapRange")
    wet.inputs["From Min"].default_value = 0.0
    wet.inputs["From Max"].default_value = 0.25
    wet.inputs["To Min"].default_value = 1.0
    wet.inputs["To Max"].default_value = 0.0
    L.new(behind, wet.inputs["Value"])
    col = N.new("ShaderNodeMix")
    col.data_type = "RGBA"
    col.inputs["A"].default_value = (*color, 1.0)
    col.inputs["B"].default_value = (*bleed, 1.0)
    L.new(m("MULTIPLY", wet.outputs["Result"], 0.6), col.inputs["Factor"])
    em = N.new("ShaderNodeEmission")
    L.new(col.outputs["Result"], em.inputs["Color"])
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    L.new(alpha, mx.inputs["Fac"])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    out = N.new("ShaderNodeOutputMaterial")
    L.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    return mat
