"""27 title: the end of the episode over the warm valley. The sun is out over the river (rf/valley.py, gold, the
clouds open); the camera drifts slowly along the slope. A wash of pale mist blooms over the right of the frame like
paper, and on it 「雨渡し」 is brushed in, stroke by stroke, top to bottom (blender/lib/brushtext.py); on the last drum
(3.25 s in) a vermilion seal is stamped under it and THE RAIN FERRY comes up beside it, then 第一話「一閃」 and its
English; つづく is brushed in at the bottom right, and the picture goes to black as the flute dies away.

The lettering hangs before the lens (parented to the camera), so it stays put while the valley drifts behind it.
"""
from __future__ import annotations

import math
from pathlib import Path

SHOT = {"scene": "title", "look": "2700,2740,2760,2790,2830,2862", "black_ok": lambda f: f >= 2869}

FONTS = Path(__file__).resolve().parents[2] / "fonts"
JP = FONTS / "ShipporiMincho-SemiBold.ttf"
EN = FONTS / "CormorantGaramond.ttf"
LENS = 30.0
DEPTH = 3.0                  # m before the lens the lettering hangs (the frame is 2.025 m tall there)
OFFSET = (60.0, 140.0, -10.0)  # the camera's place from the opening's (m): further down the slope, nearer the river
DRIFT = (16.0, 10.0)         # how far it drifts to the right and along its view over the shot (m)
# the lettering, in s into the shot (the last drum at 3.25 s: 114.85 in the mix)
PAPER = (0.05, 1.1)          # the pale wash blooms
BRUSH = (0.55, 3.0)          # 「雨渡し」
SEAL = 3.25                  # stamped on the drum
NAME = (3.3, 1.0)            # THE RAIN FERRY: in at, over
EPISODE = (4.0, 0.9)         # 第一話「一閃」
ENGLISH = (4.45, 0.9)        # Episode 1 · One Flash
TSUZUKU = (5.6, 6.5)         # つづく, brushed
BLACK = (6.9, 7.95)          # to black
INK = (0.011, 0.010, 0.012)
PAPER_COLOR = (0.86, 0.80, 0.69)   # #efe8da, linear
EN_INK = (0.022, 0.018, 0.016)


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def _fading(name: str, color, *, strength: float = 1.0):
    """An emission material whose opacity is its "fade" input (keyed). Returns (material, the fade socket)."""
    import bpy

    from lib import toon

    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    mx.inputs["Fac"].default_value = 0.0
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    return mat, mx.inputs["Fac"]


def _words(name: str, text: str, font, size: float, color, parent, at, *, spacing: float = 1.0, align="LEFT"):
    """A line of type hanging before the lens at `at` (x, y in metres at DEPTH), fading by its material."""
    import bpy

    cu = bpy.data.curves.new(name, "FONT")
    cu.body = text
    cu.font = bpy.data.fonts.load(str(font), check_existing=True)
    cu.size = size
    cu.space_character = spacing
    cu.align_x, cu.align_y = align, "CENTER"
    mat, fade = _fading(name, color)
    cu.materials.append(mat)
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    ob.location = (at[0], at[1], -DEPTH)
    ob.visible_shadow = False
    return ob, fade


def paper_material(scene):
    """A soft wash of pale paper-coloured mist, densest in its middle, its edges torn by noise (its "fade" keyed)."""
    import bpy

    from lib import toon

    mat = bpy.data.materials.new("title-paper")
    nt = toon.nodes(mat)
    N, L = nt.nodes, nt.links
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Generated"], sep.inputs[0])

    def m(op, a, b=0.0):
        x = N.new("ShaderNodeMath")
        x.operation = op
        for s, v in ((x.inputs[0], a), (x.inputs[1], b)):
            if isinstance(v, (int, float)):
                s.default_value = v
            else:
                L.new(v, s)
        return x.outputs[0]

    dx = m("MULTIPLY", m("SUBTRACT", sep.outputs["X"], 0.5), 2.0)
    dy = m("MULTIPLY", m("SUBTRACT", sep.outputs["Y"], 0.5), 2.0)
    r = m("SQRT", m("ADD", m("MULTIPLY", dx, dx), m("MULTIPLY", dy, dy)))
    noise = N.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.65
    L.new(tc.outputs["Generated"], noise.inputs["Vector"])
    torn = m("ADD", r, m("MULTIPLY", m("SUBTRACT", noise.outputs["Fac"], 0.5), 0.55))
    soft = N.new("ShaderNodeMapRange")
    soft.interpolation_type = "SMOOTHSTEP"
    soft.inputs["From Min"].default_value = 0.95
    soft.inputs["From Max"].default_value = 0.35
    L.new(torn, soft.inputs["Value"])
    fade = N.new("ShaderNodeValue")
    fade.name = "fade"
    a = m("MULTIPLY", soft.outputs["Result"], fade.outputs[0])
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*PAPER_COLOR, 1.0)
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    L.new(a, mx.inputs["Fac"])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    out = N.new("ShaderNodeOutputMaterial")
    L.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    return mat, fade.outputs[0]


def build(ctx):
    import sys

    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import brushtext, cinema, shapes
    from rf import valley

    scene = ctx.scene
    scene.render.use_motion_blur = False
    scene.view_settings.view_transform = "Standard"
    scene.eevee.use_raytracing = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 0.0, 0.0, 1)

    base = Vector(valley.camera_location())
    aim0 = Vector(valley.AIM)
    fwd = (aim0 - base).normalized()
    flat = Vector((fwd.x, fwd.y, 0.0)).normalized()
    right = flat.cross(Vector((0, 0, 1)))
    start = base + right * OFFSET[0] + flat * OFFSET[1] + Vector((0, 0, OFFSET[2]))
    aim0 = aim0 + right * 160.0 + Vector((0, 0, 90.0))
    valley.build(scene, cam=tuple(start))

    end = start + right * DRIFT[0] + flat * DRIFT[1]
    rig = cinema.film(ctx, [cinema.Setup("vista", 0.0, cinema.drift(cinema.line(start, end, aim0, aim0 + right * DRIFT[0]),
                                                                    0.25, cycles=0.3),
                                         lens=LENS, fstop=11.0, focus=1500.0, ease="sine",
                                         shake=cinema.Shake(breath=0.015))], clip=(0.3, 20000.0))
    cam = rig.camera

    t0 = ctx.time(ctx.f0)
    # the paper wash behind the calligraphy (right of the middle) and the words
    pmat, pfade = paper_material(scene)
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    paper = bpy.context.active_object
    paper.name = "paper"
    paper.parent = cam
    paper.location = (0.2, 0.0, -DEPTH - 0.05)
    paper.scale = (3.4, 2.3, 1.0)
    paper.data.materials.append(pmat)
    paper.visible_shadow = False

    # 「雨渡し」 brushed down the right third; scene time is film time, so its window is the shot's start plus
    title = brushtext.build("title-calligraphy", "雨渡し", str(JP), size=0.39, vertical=True, spacing=1.0,
                            start=t0 + BRUSH[0], end=t0 + BRUSH[1], gap=0.3, char_gap=0.9, color=INK, dry=0.65, scene=scene)
    title.parent = cam
    title.location = (0.62, 0.64, -DEPTH)
    tsuzuku = brushtext.build("tsuzuku", "つづく", str(JP), size=0.085, vertical=False, spacing=1.05,
                              start=t0 + TSUZUKU[0], end=t0 + TSUZUKU[1], gap=0.2, char_gap=0.3, color=INK, dry=0.4,
                              scene=scene)
    tsuzuku.parent = cam
    tsuzuku.location = (1.27, -0.86, -DEPTH)

    # the seal: a vermilion square with 一閃 cut into it, stamped on the drum
    accent = tuple(ctx.look_at(ctx.f0).light.accent)
    seal_root = bpy.data.objects.new("seal", None)
    scene.collection.objects.link(seal_root)
    seal_root.parent = cam
    seal_root.location = (0.43, -0.6, -DEPTH + 0.01)
    smat, sfade = _fading("seal", accent, strength=1.0)
    sq = shapes.box("seal-square", (0, 0, 0), (0.15, 0.15, 0.002), material=smat)
    sq.parent = seal_root
    sq.visible_shadow = False
    cut, cfade = _words("seal-cut", "一閃", JP, 0.06, PAPER_COLOR, seal_root, (0.0, 0.0), align="CENTER")
    cut.location = (0.0, 0.0, 0.002)
    cut.rotation_euler = (0, 0, 0)
    cut.data.body = "一\n閃"
    cut.data.space_line = 0.95

    name, nfade = _words("title-name", "THE RAIN FERRY", EN, 0.135, EN_INK, cam, (-0.25, 0.02), spacing=1.32,
                         align="RIGHT")
    episode, efade = _words("title-episode", "第一話「一閃」", JP, 0.078, accent, cam, (-0.25, -0.15), spacing=1.15,
                            align="RIGHT")
    english, gfade = _words("title-english", "Episode 1 · One Flash", EN, 0.06, (0.05, 0.042, 0.036), cam, (-0.25, -0.26),
                            spacing=1.18, align="RIGHT")

    # the black at the end
    bmat, bfade = _fading("fade", (0.0, 0.0, 0.0))
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    black = bpy.context.active_object
    black.name = "black"
    black.parent = cam
    black.location = (0.0, 0.0, -0.5)
    black.scale = (2.0, 2.0, 1.0)
    black.data.materials.append(bmat)
    black.visible_shadow = False

    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = ctx.time(f) - t0
        valley.key(scene, f, ctx.look_at(f), sun=1.0)
        pfade.default_value = 0.78 * ease((t - PAPER[0]) / (PAPER[1] - PAPER[0]))
        pfade.keyframe_insert("default_value", frame=f)
        # the seal: struck down from a little larger, all at once
        s = (t - SEAL) * ctx.fps
        on = 1.0 if s >= 0 else 0.0
        k = 1.0 + 0.35 * max(0.0, 1.0 - s / 3.0) if s >= 0 else 1.0
        seal_root.scale = (k, k, k)
        seal_root.keyframe_insert("scale", frame=f)
        for sock in (sfade, cfade):
            sock.default_value = on * 0.95
            sock.keyframe_insert("default_value", frame=f)
        for sock, (a, d) in ((nfade, NAME), (efade, EPISODE), (gfade, ENGLISH)):
            sock.default_value = ease((t - a) / d)
            sock.keyframe_insert("default_value", frame=f)
        # THE RAIN FERRY settles as it comes in: its tracking closing a little
        name.data.space_character = 1.32 + 0.12 * (1 - ease((t - NAME[0]) / (NAME[1] * 1.6)))
        name.data.keyframe_insert("space_character", frame=f)
        bfade.default_value = ease((t - BLACK[0]) / (BLACK[1] - BLACK[0]))
        bfade.keyframe_insert("default_value", frame=f)
