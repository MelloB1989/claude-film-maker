"""Anime and manga looks for Blender shots: cel shading, ink lines, distance fog, rain, rippled water and mist.

A shot that should read as 2D animation rather than CG builds its world from these:

- `Look`: the shot's shared settings: the fog's colour and the distances it closes in over, the key light's direction.
- `eye(name, ...)`: an eyeball's toon material (white, iris, pupil, a glint), cel shaded.
- `cel(name, lit, shade, ...)`: a toon material. The light a surface gets (a diffuse BSDF read back as a colour) is
  cut into flat bands, the lit colour above `cut` and the shade below it, an optional `mid` band between, a thin soft
  edge so the cut never aliases, and the whole faded toward the fog with distance from the camera. It renders as
  emission, so what is painted is what the plate holds (the engine grades it).
- `ink(name, collection, radius, ...)`: Grease Pencil Line Art over a collection: contours, creases, intersections and
  silhouettes as ink strokes. Give near things thicker lines than far ones by putting them in their own collections.
- `rain(...)`: a downpour filling a box in front of the camera (Geometry Nodes, a pure function of time: any frame
  renders on its own), streaks tilted by the wind, or frozen in the air for a held breath.
- `splashes(...)`: raindrops landing on a deck or the water: little crowns flicking up and gone, each at a new place
  every time (Geometry Nodes, a pure function of time like the rain).
- `water(...)`: a river: a dark surface with drifting streaks, rain rings opening across it, and the world reflected in
  it (EEVEE ray tracing).
- `mist_card(...)`: a drifting bank of fog on a card, for the layers of an ink-wash distance.
- `flutter(ob, ...)`: wind in cloth and hair (a travelling wave along the object).
- `lightning(scene, strikes, ...)` and `bolt(...)`: a strike of lightning. Every material here listens to one scene
  property, `FLASH` (0 to 1): as it rises the lit bands, the fog, the sky (landscape.sky) and the rain whiten while the
  shade stays put, so a flash reads as one hard manga frame. `lightning` keys it; `bolt` draws the jagged fork, seen only
  while it flashes.

Colours are linear RGB (Blender's working space): pass `theme.linear(role)` for palette roles, or the film's own.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

RGB = tuple[float, float, float]


@dataclass
class Look:
    """What every cel material in a shot shares: fog from `fog_near` to `fog_far` metres from the camera, reaching
    `fog_max` of `fog` at `fog_far` (an ink-wash distance pales but never quite disappears)."""
    fog: RGB = (0.62, 0.64, 0.68)
    fog_near: float = 15.0
    fog_far: float = 400.0
    fog_max: float = 0.92
    fog_power: float = 0.6
    flash_lit: RGB = (0.84, 0.88, 0.96)   # the lit bands' colour at the height of a flash
    flash_amount: float = 0.8             # how far they go toward it
    flash_fog: float = 0.05               # how far the fog goes toward it (little: the distance stays a silhouette)
    # an anime palette's shadows (0 leaves them as given): skin's warm toward red, everything else cool toward
    # blue-violet, by this much (shadow_hue)
    shade_shift: float = 0.0
    # a rim of light round the shadow side's edge, (colour, width 0..1 of the grazing angle, strength), or None
    rim: tuple | None = None
    extras: dict = field(default_factory=dict)


def shadow_hue(lit: RGB, shade: RGB, shift: float) -> RGB:
    """`shade` moved toward an anime shadow's hue by `shift` (0..1), its brightness kept: a skin-like `lit` (warm,
    red over green over blue) gets a warmer, redder shadow, anything else a cooler, blue-violet one. Pure Python."""
    if shift <= 0:
        return shade
    r, g, b = lit
    warm = r > g > b and r > 0.15 and (r - b) > 0.25 * r
    tint = (1.0 + 0.35 * shift, 1.0 - 0.12 * shift, 1.0 - 0.2 * shift) if warm else \
        (1.0 - 0.1 * shift, 1.0 - 0.04 * shift, 1.0 + 0.3 * shift)
    out = [c * t for c, t in zip(shade, tint)]
    lum = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]  # noqa: E731
    k = lum(shade) / max(lum(out), 1e-9)
    return tuple(min(1.0, c * k) for c in out)


FLASH = "flash"  # the scene property every material here follows: 0 dark, 1 the height of a lightning flash
# a mesh attribute (float, per vertex) every cel material adds to the light it reads before cutting it into bands: the
# anime shader's shading bias (a face kept lit, a crease kept dark); a mesh without it reads 0
BIAS = "toon_bias"


def scene_value(nt, prop: str = FLASH):
    """A shader socket reading the scene's custom property `prop` (0 while the scene has none), keyed per frame: one
    value a shot animates and every material follows."""
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = "VIEW_LAYER"
    a.attribute_name = prop
    return a.outputs["Fac"]


def flashed(nt, color, toward: RGB, amount: float):
    """`color` (a socket or a colour) moved toward `toward` by the flash times `amount`."""
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = amount
    nt.links.new(scene_value(nt), k.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(k.outputs[0], mix.inputs["Factor"])
    if isinstance(color, tuple):
        mix.inputs["A"].default_value = _rgba(color)
    else:
        nt.links.new(color, mix.inputs["A"])
    mix.inputs["B"].default_value = _rgba(toward)
    return mix.outputs["Result"]


def _rgba(c: RGB, a: float = 1.0) -> tuple[float, float, float, float]:
    return (c[0], c[1], c[2], a)


def nodes(mat):
    """The material's node tree, emptied (made first where an older Blender makes them on request)."""
    if mat.node_tree is None:  # Blender < 5 made node trees on request
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return nt


def _fog_mix(nt, color_socket, look: Look):
    """The colour faded toward the look's fog by the surface's distance from the camera."""
    cam = nt.nodes.new("ShaderNodeCameraData")
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value = look.fog_near
    rng.inputs["From Max"].default_value = look.fog_far
    rng.inputs["To Min"].default_value = 0.0
    rng.inputs["To Max"].default_value = 1.0
    nt.links.new(cam.outputs["View Distance"], rng.inputs["Value"])
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = look.fog_power
    nt.links.new(rng.outputs["Result"], pw.inputs[0])
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = look.fog_max
    nt.links.new(pw.outputs[0], k.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(flashed(nt, look.fog, look.flash_lit, look.flash_fog), mix.inputs["B"])
    nt.links.new(k.outputs[0], mix.inputs["Factor"])
    nt.links.new(color_socket, mix.inputs["A"])
    return mix.outputs["Result"]


def cel(name: str, lit: RGB, shade: RGB, *, look: Look | None = None, cut: float = 0.42, soft: float = 0.02,
        mid: RGB | None = None, mid_cut: float = 0.2, alpha: float = 1.0, fog: bool = True, flash: float | None = None,
        shift: float | None = None, rim=None, spec: tuple | None = None):
    """A toon material: flat lit and shade colours (and an optional mid band) by the light the surface receives, its
    band edges softened by `soft`, faded to the fog with distance; the lit band whitens with the scene's `FLASH` by
    `flash` (default the look's `flash_amount`; 0 for what should stand dark against a lightning sky, the far ridges).
    `alpha` < 1 blends (dithered: it keeps depth for the depth of field and the ink lines).

    Anime extras, each off unless the call or the look asks: `shift` moves the shadows toward an anime palette's hues
    (shadow_hue; default the look's `shade_shift`); `rim` (colour, width, strength) lights the shadow side's edge, the
    colour None for the surface's own lit colour (light wrapping round it; default the look's `rim`; False for none);
    `spec` (colour, roughness, cut) lays a hard highlight band over the lit side (a hair's sheen)."""
    import bpy

    look = look or Look()
    shift = look.shade_shift if shift is None else shift
    shade = shadow_hue(lit, shade, shift)
    if mid:
        mid = shadow_hue(lit, mid, shift)
    rim = look.rim if rim is None else (rim or None)
    mat = bpy.data.materials.new(name)
    mat["toon_lit"] = list(lit)    # what an outline's tone is drawn from (outline.ink_tone)
    nt = nodes(mat)
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(diff.outputs[0], s2r.inputs[0])
    lum = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(s2r.outputs["Color"], lum.inputs[0])
    # the mesh's shading bias (BIAS), where it has one
    bias = nt.nodes.new("ShaderNodeAttribute")
    bias.attribute_type = "GEOMETRY"
    bias.attribute_name = BIAS
    biased = nt.nodes.new("ShaderNodeMath")
    biased.operation = "ADD"
    nt.links.new(lum.outputs[0], biased.inputs[0])
    nt.links.new(bias.outputs["Fac"], biased.inputs[1])

    def band(at: float, below, above):
        ramp = nt.nodes.new("ShaderNodeMapRange")
        ramp.interpolation_type = "SMOOTHSTEP"
        ramp.inputs["From Min"].default_value = at - soft
        ramp.inputs["From Max"].default_value = at + soft
        nt.links.new(biased.outputs[0], ramp.inputs["Value"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(ramp.outputs["Result"], mix.inputs["Factor"])
        for sock, v in (("A", below), ("B", above)):
            if isinstance(v, tuple):
                mix.inputs[sock].default_value = _rgba(v)
            else:
                nt.links.new(v, mix.inputs[sock])
        band.lit = ramp.outputs["Result"]
        return mix.outputs["Result"]

    k = look.flash_amount if flash is None else flash
    col = band(cut, mid if mid else shade, flashed(nt, lit, look.flash_lit, k) if k > 0 else lit)
    lit_k = band.lit                 # 1 on the lit side of the main cut, 0 in its shadow
    if mid:
        col = band(mid_cut, shade, col)

    def over(color, mask):
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        nt.links.new(mask, mx.inputs["Factor"])
        nt.links.new(col, mx.inputs["A"])
        mx.inputs["B"].default_value = _rgba(color)
        return mx.outputs["Result"]

    def mul(a, b):
        m = nt.nodes.new("ShaderNodeMath")
        m.operation = "MULTIPLY"
        nt.links.new(a, m.inputs[0])
        if isinstance(b, float):
            m.inputs[1].default_value = b
        else:
            nt.links.new(b, m.inputs[1])
        return m.outputs[0]

    if spec:
        scol, rough, scut = spec
        gl = nt.nodes.new("ShaderNodeBsdfGlossy")
        gl.inputs["Roughness"].default_value = rough
        g2r = nt.nodes.new("ShaderNodeShaderToRGB")
        nt.links.new(gl.outputs[0], g2r.inputs[0])
        gl_lum = nt.nodes.new("ShaderNodeRGBToBW")
        nt.links.new(g2r.outputs["Color"], gl_lum.inputs[0])
        sr = nt.nodes.new("ShaderNodeMapRange")
        sr.interpolation_type = "SMOOTHSTEP"
        sr.inputs["From Min"].default_value = scut - soft
        sr.inputs["From Max"].default_value = scut + soft
        nt.links.new(gl_lum.outputs[0], sr.inputs["Value"])
        col = over(scol, mul(sr.outputs["Result"], lit_k))
    if rim:
        rcol, width, strength = rim
        rcol = lit if rcol is None else rcol
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.5
        rr = nt.nodes.new("ShaderNodeMapRange")
        rr.interpolation_type = "SMOOTHSTEP"
        rr.inputs["From Min"].default_value = 1.0 - width - 0.03
        rr.inputs["From Max"].default_value = 1.0 - width + 0.03
        nt.links.new(lw.outputs["Facing"], rr.inputs["Value"])
        shadow = nt.nodes.new("ShaderNodeMath")
        shadow.operation = "SUBTRACT"
        shadow.inputs[0].default_value = 1.0
        nt.links.new(lit_k, shadow.inputs[1])
        col = over(rcol, mul(mul(rr.outputs["Result"], shadow.outputs[0]), float(strength)))
    if fog:
        col = _fog_mix(nt, col, look)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if alpha < 1.0:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader")
        mx.inputs["Fac"].default_value = alpha
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(em.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
        mat.surface_render_method = "DITHERED"
    else:
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def eye(name: str, *, iris: RGB = (0.1, 0.065, 0.04), pupil: RGB = (0.008, 0.007, 0.007), white: RGB = (0.86, 0.85, 0.83),
        iris_size: float = 0.46, pupil_size: float = 0.2, rim: float = 0.08, glint: tuple = (-0.16, 0.2, 0.08),
        look: Look | None = None, cut: float = 0.35, shade: float = 0.6):
    """An eyeball's toon material, for a sphere looking along -y in its rest space (human.eyes): the white, an iris
    `iris_size` across (of the eye's radius) darkening to a rim, the pupil, a glint at `glint` (x, z, size, on the
    front, in radii); then cel shaded like `cel` (the shade `shade` times the colour), so a lid's shadow falls across
    it."""
    import bpy

    look = look or Look()
    mat = bpy.data.materials.new(name)
    nt = nodes(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    v = nt.nodes.new("ShaderNodeVectorMath")
    v.operation = "SUBTRACT"
    v.inputs[1].default_value = (0.5, 0.5, 0.5)
    nt.links.new(tc.outputs["Generated"], v.inputs[0])
    nv = nt.nodes.new("ShaderNodeVectorMath")
    nv.operation = "NORMALIZE"
    nt.links.new(v.outputs[0], nv.inputs[0])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(nv.outputs[0], sep.inputs[0])

    def m(op, a, b=None, clamp=False):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        for sock, x in ((n.inputs[0], a), (n.inputs[1], b)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                sock.default_value = x
            else:
                nt.links.new(x, sock)
        return n.outputs[0]

    # the distance from the eye's front pole, across its face (only on the front half)
    rho = m("SQRT", m("ADD", m("MULTIPLY", sep.outputs["X"], sep.outputs["X"]), m("MULTIPLY", sep.outputs["Z"], sep.outputs["Z"])))
    front = m("LESS_THAN", sep.outputs["Y"], 0.0)

    def disc(radius, soft=0.012):
        r = nt.nodes.new("ShaderNodeMapRange")
        r.interpolation_type = "SMOOTHSTEP"
        r.inputs["From Min"].default_value = radius + soft
        r.inputs["From Max"].default_value = radius - soft
        nt.links.new(rho, r.inputs["Value"])
        return m("MULTIPLY", r.outputs["Result"], front)

    def mix(fac, a, b):
        x = nt.nodes.new("ShaderNodeMix")
        x.data_type = "RGBA"
        nt.links.new(fac, x.inputs["Factor"])
        for sock, c in ((x.inputs["A"], a), (x.inputs["B"], b)):
            if isinstance(c, tuple):
                sock.default_value = _rgba(c)
            else:
                nt.links.new(c, sock)
        return x.outputs["Result"]

    rimc = tuple(c * 0.35 for c in iris)
    inner = mix(disc(iris_size - rim), rimc, iris)              # the iris, its rim darker
    col = mix(disc(iris_size), white, inner)
    col = mix(disc(pupil_size), col, pupil)
    gx, gz, gs = glint
    gd = m("SQRT", m("ADD", m("POWER", m("SUBTRACT", sep.outputs["X"], gx), 2.0), m("POWER", m("SUBTRACT", sep.outputs["Z"], gz), 2.0)))
    gr = nt.nodes.new("ShaderNodeMapRange")
    gr.inputs["From Min"].default_value = gs + 0.01
    gr.inputs["From Max"].default_value = gs - 0.01
    nt.links.new(gd, gr.inputs["Value"])
    col = mix(m("MULTIPLY", gr.outputs["Result"], front), col, (1.0, 1.0, 1.0))
    # cel shading over it: the shade a darker copy of the colour
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(diff.outputs[0], s2r.inputs[0])
    lum = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(s2r.outputs["Color"], lum.inputs[0])
    band = nt.nodes.new("ShaderNodeMapRange")
    band.interpolation_type = "SMOOTHSTEP"
    band.inputs["From Min"].default_value = cut - 0.02
    band.inputs["From Max"].default_value = cut + 0.02
    band.inputs["To Min"].default_value = shade
    nt.links.new(lum.outputs[0], band.inputs["Value"])
    lit = nt.nodes.new("ShaderNodeMix")
    lit.data_type = "RGBA"
    lit.blend_type = "MULTIPLY"
    lit.inputs["Factor"].default_value = 1.0
    nt.links.new(col, lit.inputs["A"])
    comb = nt.nodes.new("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(band.outputs["Result"], comb.inputs[ch])
    nt.links.new(comb.outputs[0], lit.inputs["B"])
    out_col = _fog_mix(nt, lit.outputs["Result"], look)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(out_col, em.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def flat(name: str, color: RGB, *, look: Look | None = None, fog: bool = True, strength: float = 1.0):
    """One flat colour (a sky card, a far ridge, a lantern's glow at strength > 1), faded to the fog."""
    import bpy

    look = look or Look()
    mat = bpy.data.materials.new(name)
    nt = nodes(mat)
    rgb = nt.nodes.new("ShaderNodeRGB")
    rgb.outputs[0].default_value = _rgba(color)
    col = _fog_mix(nt, rgb.outputs[0], look) if fog else rgb.outputs[0]
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    nt.links.new(col, em.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def ink(name: str, collection, *, radius: float = 0.004, color: RGB = (0.02, 0.02, 0.025), opacity: float = 1.0,
        crease: float = 140.0, intersections: bool = True, scene=None, creases: bool = True, drawn: bool = False,
        taper: float = 0.3, smooth: float = 0.8, face_marks: bool = True):
    """Grease Pencil Line Art over `collection`: an object of its own holding the strokes (keep it out of the
    collection). `radius` is the stroke's half-width in metres at the object (a far collection wants a larger one to
    read at the same weight); `crease` the angle under which an edge between faces is drawn (`creases` False: none,
    only contours, intersections and where materials meet: the inner lines a character wants once outline.hull draws
    its silhouette). `drawn`: the strokes read as drawn rather than traced: chains smoothed and a little simplified so
    no polygon steps show (`smooth` 0..1), their ends tapering to `taper` of the width like a brush's. `face_marks`:
    no lines at all from faces marked `freestyle_face` (a face whose features are drawn on, animeface: its outline
    hull draws its silhouette); a collection with no marks draws as before."""
    import bpy

    scene = scene or bpy.context.scene
    gpd = bpy.data.grease_pencils.new(name)
    ob = bpy.data.objects.new(name, gpd)
    scene.collection.objects.link(ob)
    gpd.layers.new("ink")
    mat = bpy.data.materials.new(f"{name}-ink")
    bpy.data.materials.create_gpencil_data(mat)
    mat.grease_pencil.color = _rgba(color, opacity)
    gpd.materials.append(mat)
    mod = ob.modifiers.new("lineart", "LINEART")
    mod.source_type = "COLLECTION"
    mod.source_collection = collection
    mod.target_layer = "ink"
    mod.target_material = mat
    mod.radius = radius
    mod.crease_threshold = math.radians(crease)
    mod.use_intersection = intersections
    mod.use_crease = creases
    mod.use_material = not creases     # without creases, still a line where one material meets another
    mod.use_contour = True
    mod.use_loose = True
    if face_marks:
        mod.use_face_mark = True
        mod.use_face_mark_invert = True        # lines from the unmarked faces only
        mod.use_face_mark_keep_contour = False
    if drawn:
        mod.smooth_tolerance = 0.3 * smooth
        sm = ob.modifiers.new("smooth", "GREASE_PENCIL_SMOOTH")
        sm.factor = smooth
        sm.step = 3
        sm.use_keep_shape = True
        sm.use_smooth_ends = False
        si = ob.modifiers.new("simplify", "GREASE_PENCIL_SIMPLIFY")
        si.mode = "MERGE"
        si.distance = radius * 0.6
        th = ob.modifiers.new("taper", "GREASE_PENCIL_THICKNESS")
        th.thickness_factor = taper
        th.use_custom_curve = True
        cm = th.custom_curve
        pts = cm.curves[0].points
        pts[0].location = (0.0, 1.0)
        pts[1].location = (1.0, 1.0)
        for x in (0.18, 0.82):
            pts.new(x, 0.0)
        cm.update()
    return ob


def collection(name: str, parent=None):
    import bpy

    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def move_to(ob, coll):
    """Put `ob` in `coll` alone (an operator adds new objects to whichever collection is active)."""
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)
    return ob


def frame_value(nt, scene, scale: float = 1.0):
    """A Value node driven by the scene's frame in seconds (times `scale`): a shader's clock."""
    v = nt.nodes.new("ShaderNodeValue")
    fc = v.outputs[0].driver_add("default_value")
    fc.driver.type = "SCRIPTED"
    fps = scene.render.fps / scene.render.fps_base
    fc.driver.expression = f"frame / {fps:.6f} * {scale:.6f}"
    return v.outputs[0]


def water(name: str, base: RGB, light: RGB, *, look: Look | None = None, scene=None, rings: float = 1.0,
          reflect: float = 0.35, scale: float = 1.0):
    """A river under rain: `base` with long drifting streaks of `light`, rain rings opening and fading in cells across
    it (`rings` 0 turns them off), and a glossy reflection mixed in by `reflect` (EEVEE ray traced)."""
    import bpy

    look = look or Look()
    scene = scene or bpy.context.scene
    mat = bpy.data.materials.new(name)
    nt = nodes(mat)
    tex = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tex.outputs["Object"], sep.inputs[0])
    t = frame_value(nt, scene)
    # streaks: noise stretched along x, drifting slowly downstream
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    drift = nt.nodes.new("ShaderNodeMath")
    drift.operation = "MULTIPLY_ADD"
    drift.inputs[1].default_value = 0.15
    nt.links.new(t, drift.inputs[0])
    nt.links.new(sep.outputs["X"], drift.inputs[2])
    sx = nt.nodes.new("ShaderNodeMath")
    sx.operation = "MULTIPLY"
    sx.inputs[1].default_value = 0.08 / scale
    nt.links.new(drift.outputs[0], sx.inputs[0])
    sy = nt.nodes.new("ShaderNodeMath")
    sy.operation = "MULTIPLY"
    sy.inputs[1].default_value = 1.6 / scale
    nt.links.new(sep.outputs["Y"], sy.inputs[0])
    nt.links.new(sx.outputs[0], comb.inputs["X"])
    nt.links.new(sy.outputs[0], comb.inputs["Y"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    noise.inputs["Detail"].default_value = 3.0
    nt.links.new(comb.outputs[0], noise.inputs["Vector"])
    streak = nt.nodes.new("ShaderNodeMapRange")
    streak.inputs["From Min"].default_value = 0.56
    streak.inputs["From Max"].default_value = 0.66
    nt.links.new(noise.outputs["Fac"], streak.inputs["Value"])
    # rain rings: per Voronoi cell, a ring whose radius grows with a phase seeded by the cell
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 2.2 / scale
    nt.links.new(tex.outputs["Object"], vor.inputs["Vector"])
    ph = nt.nodes.new("ShaderNodeMath")
    ph.operation = "MULTIPLY_ADD"
    ph.inputs[1].default_value = 1.3
    nt.links.new(t, ph.inputs[0])
    nt.links.new(vor.outputs["Color"], ph.inputs[2])  # the cell's random colour (its red) offsets the phase
    fr = nt.nodes.new("ShaderNodeMath")
    fr.operation = "FRACT"
    nt.links.new(ph.outputs[0], fr.inputs[0])
    rad = nt.nodes.new("ShaderNodeMath")
    rad.operation = "MULTIPLY"
    rad.inputs[1].default_value = 0.45
    nt.links.new(fr.outputs[0], rad.inputs[0])
    dif = nt.nodes.new("ShaderNodeMath")
    dif.operation = "SUBTRACT"
    nt.links.new(vor.outputs["Distance"], dif.inputs[0])
    nt.links.new(rad.outputs[0], dif.inputs[1])
    ab = nt.nodes.new("ShaderNodeMath")
    ab.operation = "ABSOLUTE"
    nt.links.new(dif.outputs[0], ab.inputs[0])
    ring = nt.nodes.new("ShaderNodeMapRange")
    ring.inputs["From Min"].default_value = 0.03
    ring.inputs["From Max"].default_value = 0.0
    nt.links.new(ab.outputs[0], ring.inputs["Value"])
    fade = nt.nodes.new("ShaderNodeMath")
    fade.operation = "SUBTRACT"
    fade.inputs[0].default_value = 1.0
    nt.links.new(fr.outputs[0], fade.inputs[1])
    rk = nt.nodes.new("ShaderNodeMath")
    rk.operation = "MULTIPLY"
    nt.links.new(ring.outputs["Result"], rk.inputs[0])
    nt.links.new(fade.outputs[0], rk.inputs[1])
    rk2 = nt.nodes.new("ShaderNodeMath")
    rk2.operation = "MULTIPLY"
    rk2.inputs[1].default_value = rings
    nt.links.new(rk.outputs[0], rk2.inputs[0])
    tot = nt.nodes.new("ShaderNodeMath")
    tot.operation = "MAXIMUM"
    tot.use_clamp = True
    nt.links.new(streak.outputs["Result"], tot.inputs[0])
    nt.links.new(rk2.outputs[0], tot.inputs[1])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = _rgba(base)
    mix.inputs["B"].default_value = _rgba(light)
    nt.links.new(tot.outputs[0], mix.inputs["Factor"])
    col = _fog_mix(nt, mix.outputs["Result"], look)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if reflect > 0:
        gl = nt.nodes.new("ShaderNodeBsdfGlossy")
        gl.inputs["Roughness"].default_value = 0.06
        gl.inputs["Color"].default_value = (reflect, reflect, reflect, 1)
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(em.outputs[0], add.inputs[0])
        nt.links.new(gl.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def mist_card(name: str, location, size: tuple[float, float], color: RGB, *, density: float = 0.55, scene=None,
              drift: float = 0.6, seed: float = 0.0, rotation=(math.pi / 2, 0, 0)):
    """A card of drifting fog: a noise bank, densest along its middle and fading to nothing at its top and bottom,
    drifting sideways at `drift` metres a second."""
    import bpy

    scene = scene or bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=1, location=location, rotation=rotation)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], 1)
    mat = bpy.data.materials.new(name)
    nt = nodes(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    t = frame_value(nt, scene, drift / max(size[0], 1e-3))
    sx = nt.nodes.new("ShaderNodeMath")
    sx.operation = "ADD"
    nt.links.new(sep.outputs["X"], sx.inputs[0])
    nt.links.new(t, sx.inputs[1])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sx.outputs[0], comb.inputs["X"])
    nt.links.new(sep.outputs["Y"], comb.inputs["Y"])
    comb.inputs["Z"].default_value = seed
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.5
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.55
    nt.links.new(comb.outputs[0], noise.inputs["Vector"])
    band = nt.nodes.new("ShaderNodeMath")
    band.operation = "SUBTRACT"
    band.inputs[0].default_value = 0.5
    nt.links.new(sep.outputs["Y"], band.inputs[1])
    bab = nt.nodes.new("ShaderNodeMath")
    bab.operation = "ABSOLUTE"
    nt.links.new(band.outputs[0], bab.inputs[0])
    prof = nt.nodes.new("ShaderNodeMapRange")
    prof.inputs["From Min"].default_value = 0.5
    prof.inputs["From Max"].default_value = 0.05
    nt.links.new(bab.outputs[0], prof.inputs["Value"])
    nm = nt.nodes.new("ShaderNodeMapRange")
    nm.inputs["From Min"].default_value = 0.38
    nm.inputs["From Max"].default_value = 0.72
    nt.links.new(noise.outputs["Fac"], nm.inputs["Value"])
    a = nt.nodes.new("ShaderNodeMath")
    a.operation = "MULTIPLY"
    nt.links.new(nm.outputs["Result"], a.inputs[0])
    nt.links.new(prof.outputs["Result"], a.inputs[1])
    a2 = nt.nodes.new("ShaderNodeMath")
    a2.operation = "MULTIPLY"
    a2.inputs[1].default_value = density
    nt.links.new(a.outputs[0], a2.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = _rgba(color)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(a2.outputs[0], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    ob.data.materials.append(mat)
    ob.visible_shadow = False
    return ob


def rain(name: str, box_min, box_max, *, count: int = 9000, speed: float = 9.0, wind: float = 1.2,
         length: float = 0.55, width: float = 0.006, color: RGB = (0.86, 0.89, 0.93), alpha: float = 0.45,
         seed: int = 1, scene=None, frozen: bool = False, coll=None, near: float | None = None, clear: float = 0.0):
    """Rain filling the box [box_min, box_max] (metres): `count` streaks `length` long falling at `speed` m/s with a
    `wind` drift along +x, every drop's place a pure function of the scene's time (Geometry Nodes: each falls through
    the box and wraps back to its top), so any frame renders on its own, in any order. `frozen`: the drops hang where
    they are, short beads instead of streaks (a held breath). `near` (metres): drops closer than that to the active
    camera shrink with their distance, so a close camera sees fine streaks rather than smears across a face; `clear`:
    none at all within that distance of it. From straight above a drop reads as a short dot. Returns the drops'
    object."""
    import bpy
    import numpy as np

    scene = scene or bpy.context.scene
    coll = coll or scene.collection
    lo, hi = np.asarray(box_min, float), np.asarray(box_max, float)
    rng = np.random.default_rng(seed)
    pts = rng.uniform(lo, hi, size=(count, 3))
    me = bpy.data.meshes.new(name)
    me.from_pydata(pts.tolist(), [], [])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)

    # the drop: a thin card facing the camera's way (-y), its long axis along the fall (tilted by the wind)
    L = length * (0.12 if frozen else 1.0)
    tilt = 0.0 if frozen or speed <= 0 else math.atan2(wind, speed)
    dx, dz = math.sin(tilt) * L / 2, math.cos(tilt) * L / 2
    w = width / 2
    dme = bpy.data.meshes.new(f"{name}-drop")
    # ... and a small level diamond across its middle, edge-on to a camera at eye level: from straight above, looking
    # down the fall, a drop reads as a short dot rather than vanishing edge-on
    r = 1.5 * w
    dme.from_pydata([(-dx - w, 0, -dz), (-dx + w, 0, -dz), (dx + w, 0, dz), (dx - w, 0, dz),
                     (-r - dx * 0.4, 0, 0), (0, -r, 0), (r + dx * 0.4, 0, 0), (0, r, 0)], [], [(0, 1, 2, 3), (4, 5, 6, 7)])
    drop = bpy.data.objects.new(f"{name}-drop", dme)
    coll.objects.link(drop)
    drop.hide_render = True
    drop.hide_viewport = True
    mat = bpy.data.materials.new(f"{name}-drop")
    nt = nodes(mat)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(flashed(nt, color, (1.0, 1.0, 1.0), 1.0), em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    fa = nt.nodes.new("ShaderNodeMapRange")  # alpha, up to twice as opaque at the height of a flash
    fa.inputs["To Min"].default_value = alpha
    fa.inputs["To Max"].default_value = min(1.0, alpha * 2.0)
    nt.links.new(scene_value(nt), fa.inputs["Value"])
    nt.links.new(fa.outputs["Result"], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    dme.materials.append(mat)

    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N = ng.nodes
    gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    pos = N.new("GeometryNodeInputPosition")
    sep = N.new("ShaderNodeSeparateXYZ")
    ng.links.new(pos.outputs[0], sep.inputs[0])
    tnode = N.new("GeometryNodeInputSceneTime")

    def wrap(coord, lo_v: float, size: float, rate: float):
        """lo + fract((coord - lo + rate * t) / size) * size, minus coord: the offset that moves a coordinate on
        through the box at `rate` m/s and wraps it."""
        mt = N.new("ShaderNodeMath")
        mt.operation = "MULTIPLY"
        mt.inputs[1].default_value = rate
        ng.links.new(tnode.outputs["Seconds"], mt.inputs[0])
        a = N.new("ShaderNodeMath")
        a.operation = "ADD"
        ng.links.new(coord, a.inputs[0])
        ng.links.new(mt.outputs[0], a.inputs[1])
        b = N.new("ShaderNodeMath")
        b.operation = "SUBTRACT"
        b.inputs[1].default_value = lo_v
        ng.links.new(a.outputs[0], b.inputs[0])
        d = N.new("ShaderNodeMath")
        d.operation = "DIVIDE"
        d.inputs[1].default_value = size
        ng.links.new(b.outputs[0], d.inputs[0])
        f = N.new("ShaderNodeMath")
        f.operation = "FRACT"
        ng.links.new(d.outputs[0], f.inputs[0])
        m2 = N.new("ShaderNodeMath")
        m2.operation = "MULTIPLY_ADD"
        m2.inputs[1].default_value = size
        m2.inputs[2].default_value = lo_v
        ng.links.new(f.outputs[0], m2.inputs[0])
        off = N.new("ShaderNodeMath")
        off.operation = "SUBTRACT"
        ng.links.new(m2.outputs[0], off.inputs[0])
        ng.links.new(coord, off.inputs[1])
        return off.outputs[0]

    comb = N.new("ShaderNodeCombineXYZ")
    if not frozen:
        ng.links.new(wrap(sep.outputs["X"], float(lo[0]), float(hi[0] - lo[0]), wind), comb.inputs["X"])
        ng.links.new(wrap(sep.outputs["Z"], float(lo[2]), float(hi[2] - lo[2]), -speed), comb.inputs["Z"])
    setp = N.new("GeometryNodeSetPosition")
    ng.links.new(gin.outputs[0], setp.inputs["Geometry"])
    ng.links.new(comb.outputs[0], setp.inputs["Offset"])
    info = N.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = drop
    rnd = N.new("FunctionNodeRandomValue")
    rnd.data_type = "FLOAT"
    rnd.inputs["Min"].default_value = 0.65
    rnd.inputs["Max"].default_value = 1.3
    rnd.inputs["Seed"].default_value = seed
    inst = N.new("GeometryNodeInstanceOnPoints")
    ng.links.new(setp.outputs["Geometry"], inst.inputs["Points"])
    ng.links.new(info.outputs["Geometry"], inst.inputs["Instance"])
    # the float output (older Blenders keep one output per data type, newer ones only the active one)
    val = next((o for o in rnd.outputs if o.type == "VALUE" and o.enabled), rnd.outputs[0])
    if near or clear:
        # each drop's distance from the active camera: shrink it nearer than `near`, drop it inside `clear`
        cam = N.new("GeometryNodeInputActiveCamera")
        ci = N.new("GeometryNodeObjectInfo")
        ci.transform_space = "ORIGINAL"
        ng.links.new(cam.outputs[0], ci.inputs["Object"])
        p2 = N.new("GeometryNodeInputPosition")
        dist = N.new("ShaderNodeVectorMath")
        dist.operation = "DISTANCE"
        ng.links.new(p2.outputs[0], dist.inputs[0])
        ng.links.new(ci.outputs["Location"], dist.inputs[1])
        k = N.new("ShaderNodeMapRange")
        k.inputs["From Min"].default_value = 0.0
        k.inputs["From Max"].default_value = float(near or 1e-6)
        k.inputs["To Min"].default_value = 0.0 if near else 1.0
        k.inputs["To Max"].default_value = 1.0
        ng.links.new(dist.outputs["Value"], k.inputs["Value"])
        out_k = k.outputs["Result"]
        if clear:
            gt = N.new("ShaderNodeMath")
            gt.operation = "GREATER_THAN"
            gt.inputs[1].default_value = float(clear)
            ng.links.new(dist.outputs["Value"], gt.inputs[0])
            mk = N.new("ShaderNodeMath")
            mk.operation = "MULTIPLY"
            ng.links.new(out_k, mk.inputs[0])
            ng.links.new(gt.outputs[0], mk.inputs[1])
            out_k = mk.outputs[0]
        sc = N.new("ShaderNodeMath")
        sc.operation = "MULTIPLY"
        ng.links.new(val, sc.inputs[0])
        ng.links.new(out_k, sc.inputs[1])
        val = sc.outputs[0]
    ng.links.new(val, inst.inputs["Scale"])
    ng.links.new(inst.outputs["Instances"], gout.inputs[0])
    mod = ob.modifiers.new(name, "NODES")
    mod.node_group = ng
    ob.visible_shadow = False
    return ob


def _socket(sockets, name: str, kind: str | None = None):
    """A node's socket by name among those in use (a Random Value node keeps a Min and a Max per data type)."""
    return next(o for o in sockets if o.name == name and o.enabled and (kind is None or o.type == kind))


def splashes(name: str, area_min, area_max, *, count: int = 200, rate: float = 1.5, life: float = 0.1, size: float = 0.07,
             color: RGB = (0.8, 0.83, 0.88), alpha: float = 0.55, seed: int = 1, scene=None, coll=None):
    """Raindrops landing on a flat area (a deck, a river) at height area_min[2], seen from -y: `count` little crowns,
    each `size` high, flicking up for `life` seconds `rate` times a second, at a new place in the area every time (a
    pure function of the scene's time, like `rain`). Whitens with a lightning flash. Returns the object."""
    import bpy
    import numpy as np

    scene = scene or bpy.context.scene
    coll = coll or scene.collection
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0.0, 0.0, 0.0)] * count, [], [])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)

    # the crown: thin blades fanning up out of a small ring, in the x-z plane (facing the camera at -y)
    verts, faces = [], []
    for ang, ln in zip((-62, -36, -13, 12, 34, 60), (0.5, 0.85, 1.0, 0.95, 0.8, 0.45)):
        a = math.radians(ang)
        bx = math.sin(a) * 0.18 * size
        w = 0.06 * size
        tip = (bx + math.sin(a) * ln * size, 0.0, math.cos(a) * ln * size)
        b = len(verts)
        verts += [(bx - w * math.cos(a), 0.0, w * math.sin(a)), (bx + w * math.cos(a), 0.0, -w * math.sin(a)), tip]
        faces.append((b, b + 1, b + 2))
    cme = bpy.data.meshes.new(f"{name}-crown")
    cme.from_pydata(verts, [], faces)
    crown = bpy.data.objects.new(f"{name}-crown", cme)
    coll.objects.link(crown)
    crown.hide_render = crown.hide_viewport = True
    mat = bpy.data.materials.new(f"{name}-crown")
    nt = nodes(mat)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(flashed(nt, color, (1.0, 1.0, 1.0), 1.0), em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    mx.inputs["Fac"].default_value = alpha
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    cme.materials.append(mat)

    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    idx = N.new("GeometryNodeInputIndex")
    tnode = N.new("GeometryNodeInputSceneTime")

    def math_node(op, a, b=None):
        m = N.new("ShaderNodeMath")
        m.operation = op
        for sock, v in ((m.inputs[0], a), (m.inputs[1], b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                sock.default_value = v
            else:
                L.new(v, sock)
        return m.outputs[0]

    # each drop's phase, then which landing it is on (the cycle) and how far into it
    ph = N.new("FunctionNodeRandomValue")
    ph.data_type = "FLOAT"
    _socket(ph.inputs, "Seed").default_value = seed
    L.new(idx.outputs[0], _socket(ph.inputs, "ID"))
    c = math_node("MULTIPLY_ADD", tnode.outputs["Seconds"], rate)
    L.new(_socket(ph.outputs, "Value", "VALUE"), c.node.inputs[2])
    cycle = math_node("FLOOR", c)
    age = math_node("DIVIDE", math_node("FRACT", c), rate)   # seconds since it landed
    # where: a fresh place in the area for every landing
    where = N.new("FunctionNodeRandomValue")
    where.data_type = "FLOAT_VECTOR"
    _socket(where.inputs, "Min", "VECTOR").default_value = (area_min[0], area_min[1], area_min[2])
    _socket(where.inputs, "Max", "VECTOR").default_value = (area_max[0], area_max[1], area_min[2])
    _socket(where.inputs, "Seed").default_value = seed + 1
    landing = math_node("ADD", math_node("MULTIPLY", cycle, float(count)), idx.outputs[0])   # a number per drop per landing
    L.new(landing, _socket(where.inputs, "ID"))
    setp = N.new("GeometryNodeSetPosition")
    L.new(gin.outputs[0], setp.inputs["Geometry"])
    L.new(_socket(where.outputs, "Value", "VECTOR"), setp.inputs["Position"])
    # how big: nothing outside its life, growing from half to full height within it, each a little different
    alive = math_node("LESS_THAN", age, life)
    grow = math_node("MULTIPLY_ADD", age, 0.5 / life)
    grow.node.inputs[2].default_value = 0.5
    var = N.new("FunctionNodeRandomValue")
    var.data_type = "FLOAT"
    _socket(var.inputs, "Min", "VALUE").default_value = 0.6
    _socket(var.inputs, "Max", "VALUE").default_value = 1.3
    _socket(var.inputs, "Seed").default_value = seed + 2
    L.new(landing, _socket(var.inputs, "ID"))
    scale = math_node("MULTIPLY", math_node("MULTIPLY", alive, grow), _socket(var.outputs, "Value", "VALUE"))
    info = N.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = crown
    inst = N.new("GeometryNodeInstanceOnPoints")
    L.new(setp.outputs["Geometry"], inst.inputs["Points"])
    L.new(info.outputs["Geometry"], inst.inputs["Instance"])
    L.new(scale, inst.inputs["Scale"])
    L.new(inst.outputs["Instances"], gout.inputs[0])
    mod = ob.modifiers.new(name, "NODES")
    mod.node_group = ng
    ob.visible_shadow = False
    return ob


def flutter(ob, *, height: float = 0.04, width: float = 0.35, speed: float = 0.6, axis: str = "X", start=None,
            pin: bool = False):
    """Wind through cloth or hair: a travelling wave along the object's local `axis`, `height` metres high, scaled by
    the object's "flutter" vertex group where it has one (0 where it is held: a cape's collar, a lock's root). `pin`:
    an object without that group gets one, rising from 0 at its lowest `axis` coordinate (its root, where the wave
    starts) to 1 at its highest (a ribbon's tip), so the root stays where it is tied."""
    if pin and "flutter" not in ob.vertex_groups:
        k = "XYZ".index(axis)
        cs = [v.co[k] for v in ob.data.vertices]
        lo, hi = min(cs), max(cs)
        g = ob.vertex_groups.new(name="flutter")
        for v, c in zip(ob.data.vertices, cs):
            g.add([v.index], ((c - lo) / max(hi - lo, 1e-9)) ** 1.5, "REPLACE")
    w = ob.modifiers.new("flutter", "WAVE")
    if "flutter" in ob.vertex_groups:
        w.vertex_group = "flutter"
    w.use_x = axis == "X"
    w.use_y = axis == "Y"
    w.use_normal = True
    w.height = height
    w.width = width
    w.speed = speed
    w.narrowness = 1.0
    if start is not None:
        w.start_position_object = start
    return w


def strike(x: float, fps: float = 24.0) -> float:
    """A strike's flash `x` seconds after it (0 before): one frame of white-out, a quick fall, a dip, then a second
    flicker an eighth of a second on that dies away."""
    if x < 0:
        return 0.0
    if x < 1.0 / fps:
        return 1.0
    v = 0.8 * math.exp(-(x - 1.0 / fps) * 18.0)
    if x > 0.125:
        v += 0.8 * math.exp(-(x - 0.125) * 10.0)
    return min(1.0, v)


def lightning(scene, strikes, frames, fps: float, f0: int) -> dict:
    """Key the scene's `FLASH` on `frames` (film frames, the shot starting at `f0`) for strikes at `strikes` seconds
    into the shot, held constant between keys (a flash is drawn frame by frame, never tweened). Returns frame -> value
    for whatever else the shot flashes with it."""
    scene[FLASH] = 0.0
    vals = {}
    for f in frames:
        t = (f - f0) / fps
        vals[f] = max([strike(t - s, fps) for s in strikes] + [0.0])
        scene[FLASH] = vals[f]
        scene.keyframe_insert(f'["{FLASH}"]', frame=f)
    for fc in _fcurves(scene.animation_data.action):
        if fc.data_path == f'["{FLASH}"]':
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    return vals


def _fcurves(action) -> list:
    """An action's fcurves: a layered action's (Blender 4.4+) from its channel bags, an older one's directly."""
    out = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in getattr(strip, "channelbags", []):
                    out.extend(bag.fcurves)
    if not out and hasattr(action, "fcurves"):
        out.extend(action.fcurves)
    return out


def bolt_path(start, end, *, seed: int = 1, depth: int = 6, rough: float = 0.22):
    """A jagged line from `start` to `end` in their x-z plane (midpoint displacement: each segment's middle pushed
    sideways by up to `rough` of its length, `depth` times over). Numpy only. Returns (2**depth + 1, 3) points."""
    import numpy as np

    rng = np.random.default_rng(seed)
    pts = np.array([start, end], float)
    for _ in range(depth):
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            d = b - a
            side = np.array([-d[2], 0.0, d[0]])
            n = np.linalg.norm(side)
            side = side / n if n > 1e-9 else side
            out.append((a + b) / 2 + side * np.linalg.norm(d) * rough * rng.uniform(-1, 1))
            out.append(b)
        pts = np.array(out)
    return pts


def bolt(name: str, start, end, *, width: float = 3.0, branches: int = 4, color: RGB = (0.97, 0.98, 1.0), seed: int = 1,
         coll=None, show: float = 0.5):
    """A fork of lightning as a flat ribbon facing the camera (-y) from `start` (the sky) down to `end`, with
    `branches` shorter forks off it, all tapering: drawn only while the scene's `FLASH` is over `show`. Far away it
    wants a far `width` (metres)."""
    import bpy
    import numpy as np

    from . import shapes

    rng = np.random.default_rng(seed)
    start, end = np.asarray(start, float), np.asarray(end, float)
    paths = [(bolt_path(start, end, seed=seed), width)]
    main = paths[0][0]
    for b in range(branches):
        i = int(rng.uniform(0.15, 0.6) * len(main))
        a = main[i]
        reach = np.linalg.norm(end - start) * rng.uniform(0.2, 0.4)
        ang = rng.uniform(0.35, 0.9) * (1 if rng.uniform() < 0.5 else -1)
        tip = a + reach * np.array([math.sin(ang), 0.0, -math.cos(ang)])
        paths.append((bolt_path(a, tip, seed=seed + 17 * (b + 1), depth=4, rough=0.3), width * (0.55 - 0.2 * i / len(main))))
    verts, faces = [], []
    for path, w0 in paths:
        k = len(path)
        base = len(verts)
        for j, p in enumerate(path):
            d = path[min(j + 1, k - 1)] - path[max(j - 1, 0)]
            side = np.array([-d[2], 0.0, d[0]])
            side /= max(np.linalg.norm(side), 1e-9)
            w = w0 * (1.0 - 0.85 * j / (k - 1)) / 2
            verts += [tuple(p - side * w), tuple(p + side * w)]
        faces += [(base + 2 * j, base + 2 * j + 1, base + 2 * j + 3, base + 2 * j + 2) for j in range(k - 1)]
    mat = bpy.data.materials.new(name)
    nt = nodes(mat)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = _rgba(color)
    em.inputs["Strength"].default_value = 1.4
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    on = nt.nodes.new("ShaderNodeMath")
    on.operation = "GREATER_THAN"
    on.inputs[1].default_value = show
    nt.links.new(scene_value(nt), on.inputs[0])
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(on.outputs[0], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    ob = shapes.mesh_object(name, verts, faces, mat, coll or bpy.context.scene.collection, smooth=False)
    ob.visible_shadow = False
    return ob
