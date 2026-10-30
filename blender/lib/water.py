"""Water and wet surfaces from code for anime and ink-wash shots: a river or a puddle whose surface the rain dimples
with rings (or that lies still as a mirror once it stops), and a wet sheen over any toon material.

- `surface(name, base, light, ...)`: water as an anime background painter draws it: a dark body with the current
  drifting across it in soft patches and a few thin lines, the rain pocking it with rings in three layers (dense and
  fine near the lens, broader off in the distance) and flecks where the drops strike, and the world reflected in it
  (EEVEE ray tracing), more at a grazing angle, broken by the rings and the chop, all fading into the fog. Its
  weather is three Value nodes a shot may key (`key`): RAIN (0 still, 1 a downpour: how many cells ring, the chop,
  the roughness), MIRROR (how much of the world it reflects) and SHINE (glints sparkling along the sun's path).
- `probe(...)`: a sphere light probe, so a reflection whose rays leave the frame still finds the sky and the set.
- `wet(mat, amount)`: a toon material (toon.cel's emission) given a glossy coat on top: planks and mud glistening in
  the rain, or after it. Its WET Value node is keyable.
- `puddle_outline(...)` (numpy only, tested without Blender) and `puddle(...)`: a flat irregular pool lying on the
  ground, for `surface` (a smaller `scale`: rings sized to a puddle).

World axes as the shots use them: z up. Colours linear RGB.
"""
from __future__ import annotations

import math

import numpy as np

RAIN, MIRROR, SHINE, WET, FOAM = "rain", "mirror", "shine", "wet", "foam"   # the keyable Value nodes, by name


def puddle_outline(center, radius: float, *, seed: int = 1, n: int = 24, wobble: float = 0.28,
                   stretch: float = 1.0, angle: float = 0.0) -> np.ndarray:
    """(n, 2): an irregular pool's rim round `center` (x, y): about `radius`, wobbling by `wobble` of it (a few slow
    lobes, never pinched to nothing), `stretch` times as long along `angle` (radians from +x) as across it."""
    rng = np.random.default_rng(seed)
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    r = np.ones(n)
    for k, amp in ((2, 0.55), (3, 0.3), (5, 0.15)):
        r += wobble * amp * np.sin(k * a + rng.uniform(0, 2 * math.pi))
    r = radius * np.clip(r, 0.45, None)
    x, y = r * np.cos(a) * stretch, r * np.sin(a)
    c, s = math.cos(angle), math.sin(angle)
    return np.c_[center[0] + c * x - s * y, center[1] + s * x + c * y]


def _value(nt, name: str, v: float):
    node = nt.nodes.new("ShaderNodeValue")
    node.name = node.label = name
    node.outputs[0].default_value = v
    return node.outputs[0]


def _math(nt, op: str, a, b=None, c=None, *, clamp: bool = False):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    m.use_clamp = clamp
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = float(v)
        else:
            nt.links.new(v, m.inputs[i])
    return m.outputs[0]


def _vmath(nt, op: str, a, b=None):
    m = nt.nodes.new("ShaderNodeVectorMath")
    m.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (tuple, list)):
            m.inputs[i].default_value = tuple(float(c) for c in v)
        else:
            nt.links.new(v, m.inputs[i])
    return m.outputs["Value" if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else "Vector"]


def _ramp(nt, v, lo: float, hi: float, *, smooth: bool = True):
    """0 at `lo` .. 1 at `hi` (either way round), clamped."""
    r = nt.nodes.new("ShaderNodeMapRange")
    if smooth:
        r.interpolation_type = "SMOOTHSTEP"
    for sock, x in (("From Min", lo), ("From Max", hi), ("Value", v)):
        if isinstance(x, (int, float)):
            r.inputs[sock].default_value = float(x)
        else:
            nt.links.new(x, r.inputs[sock])
    return r.outputs["Result"]


def _xyz(nt, x, y, z=None):
    c = nt.nodes.new("ShaderNodeCombineXYZ")
    for ax, v in zip("XYZ", (x, y, z)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            c.inputs[ax].default_value = float(v)
        else:
            nt.links.new(v, c.inputs[ax])
    return c.outputs[0]


# the rain rings' layers, for a river seen from a jetty (`surface`'s scale 1): (cell size m, rings a second per cell,
# ring width (of a cell), from how far (m) they fade out .. to where they are gone): fine and dense close to the lens,
# fewer, broader ones further off, each fading before it would shimmer into noise
RING_LAYERS = ((0.28, 0.9, 0.035, 5.0, 12.0), (0.6, 0.75, 0.03, 10.0, 28.0), (1.3, 0.6, 0.028, 22.0, 70.0))


def ring_layers(scale: float = 1.0, layers=RING_LAYERS) -> list:
    """`layers` for a surface of `scale` (a puddle's smaller): cell sizes and fade distances times it, never fading
    closer than a metre. Pure Python."""
    return [(cell * scale, rate, width, max(1.0, near * scale), max(2.0, far * scale)) for cell, rate, width, near, far
            in layers]


def _rings(nt, xy, t, dist, k_rain, cell: float, rate: float, width: float, near: float, far: float, seed: float):
    """One layer of rain rings over world `xy` (a vector, metres): in Voronoi cells of `cell` m a drop lands at the
    cell's point and its ring opens out to nearly the cell's edge and fades, each cell at its own phase and its own
    pace; only as many cells ring as the rain is hard (RAIN 0.3: about a third). The ring thickens a little with the
    distance `dist` (a painter's line, not a sliver) and fades out from `near` to `far` m. Returns (ring, crown): the
    ring's strength 0..1 (its height for the bump too) and the bright fleck where the drop has just struck."""
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.voronoi_dimensions = "3D"
    vor.inputs["Scale"].default_value = 1.0 / cell
    vor.inputs["Randomness"].default_value = 0.85
    # a third coordinate off the seed keeps the layers' cells apart
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(xy, sep.inputs[0])
    nt.links.new(_xyz(nt, sep.outputs["X"], sep.outputs["Y"], seed), vor.inputs["Vector"])
    rnd = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(vor.outputs["Color"], rnd.inputs[0])
    pace = _math(nt, "MULTIPLY_ADD", rnd.outputs["Green"], 0.6, 0.7)            # 0.7 .. 1.3 times `rate`
    phase = _math(nt, "MULTIPLY_ADD", _math(nt, "MULTIPLY", t, pace), rate, rnd.outputs["Red"])
    fr = _math(nt, "FRACT", phase)
    grow = _math(nt, "POWER", fr, 0.6)                         # fast out of the strike, slowing as it spreads
    radius = _math(nt, "MULTIPLY", grow, 0.42 * cell)
    d = vor.outputs["Distance"]                                # metres (the vector is in metres times 1/cell)
    d_m = _math(nt, "MULTIPLY", d, cell)
    w = _math(nt, "MULTIPLY_ADD", dist, 0.0016, width * cell)  # thicker far off
    off = _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", d_m, radius))
    ring = _ramp(nt, off, w, _math(nt, "MULTIPLY", w, 0.15))
    fade = _math(nt, "SUBTRACT", 1.0, fr)
    life = _math(nt, "MULTIPLY", fade, fade)
    # how many cells ring: those whose own number is under the rain's
    on = _ramp(nt, _math(nt, "SUBTRACT", _math(nt, "MULTIPLY", k_rain, 1.1), rnd.outputs["Blue"]), 0.0, 0.12)
    lod = _ramp(nt, dist, far, near)
    k = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", ring, life), _math(nt, "MULTIPLY", on, lod))
    crown = _math(nt, "MULTIPLY", _ramp(nt, d_m, 0.07 * cell + 0.0015 * 1.0, 0.0),
                  _math(nt, "MULTIPLY", _ramp(nt, fr, 0.09, 0.0), _math(nt, "MULTIPLY", on, lod)))
    return k, crown


def _fog_k(nt, look):
    """How far toward the look's fog a surface this far from the camera goes (toon._fog_mix's), 0..1."""
    cam = nt.nodes.new("ShaderNodeCameraData")
    r = _ramp(nt, cam.outputs["View Distance"], look.fog_near, look.fog_far, smooth=False)
    return _math(nt, "MULTIPLY", _math(nt, "POWER", r, look.fog_power), look.fog_max), cam.outputs["View Distance"]


def surface(name: str, base, light, *, look=None, scene=None, rain: float = 1.0, mirror: float = 0.35,
            shine: float = 0.0, shine_color=(1.0, 0.8, 0.5), scale: float = 1.0, streaks: float = 1.0,
            roughness: float = 0.04, ripple: float = 0.25, flow=(0.15, 0.0), sun=None, sky=None):
    """Water as an anime background painter draws it: a body of `base`, the slow current drawn across it in soft
    patches and a few thin meandering lines of `light` drifting downstream at `flow` (m/s, x and y; `streaks` how
    much: 0 for a puddle), and over it the world reflected (EEVEE ray tracing) by MIRROR, more at a grazing angle
    than looking down into it, as water does, through a slow swell and the rain's ripples.

    The rain (RAIN 0..1, keyable) pocks it with rings in three layers (RING_LAYERS, sized for `scale`: 1 a river
    seen from a jetty, 0.3 or so a puddle): fine and dense near the lens, broader further off, each fading before it
    would shimmer; a fleck of `light` where each drop strikes; their ripples break the reflection into broken
    vertical smears; the harder it rains, the more cells ring and the rougher the mirror. Without rain the surface
    goes still: a near-mirror with a long gentle swell, and with SHINE glints of `shine_color` sparkling along the
    path of the sun (`sun`: the direction toward it, world; None: overhead, no path). `sky` (default the look's fog)
    is the pale light a grazing surface shows where the reflection finds nothing. Everything fades to the look's fog
    (toon.Look) with distance, the reflection too."""
    import bpy

    from . import toon

    look = look or toon.Look()
    scene = scene or bpy.context.scene
    sky = tuple(sky or look.fog)
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    k_rain, k_mirror, k_shine = _value(nt, RAIN, rain), _value(nt, MIRROR, mirror), _value(nt, SHINE, shine)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    wsep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], wsep.inputs[0])
    t = toon.frame_value(nt, scene)
    fog_k, dist = _fog_k(nt, look)
    # the current: the water drifts downstream; rings drift with it
    speed = math.hypot(*flow)
    fx, fy = (flow[0] / speed, flow[1] / speed) if speed else (1.0, 0.0)
    X = _math(nt, "SUBTRACT", wsep.outputs["X"], _math(nt, "MULTIPLY", t, flow[0]))
    Y = _math(nt, "SUBTRACT", wsep.outputs["Y"], _math(nt, "MULTIPLY", t, flow[1]))
    drift = _xyz(nt, X, Y, 0.0)
    along = _math(nt, "ADD", _math(nt, "MULTIPLY", X, fx), _math(nt, "MULTIPLY", Y, fy))
    across = _math(nt, "SUBTRACT", _math(nt, "MULTIPLY", Y, fx), _math(nt, "MULTIPLY", X, fy))
    # ... in soft patches, long with the flow, the body a little lighter and darker in them ...
    patch = nt.nodes.new("ShaderNodeTexNoise")
    patch.inputs["Scale"].default_value = 1.0
    patch.inputs["Detail"].default_value = 2.0
    nt.links.new(_xyz(nt, _math(nt, "MULTIPLY", along, 0.05 / scale), _math(nt, "MULTIPLY", across, 0.22 / scale),
                      _math(nt, "MULTIPLY", t, 0.03)), patch.inputs["Vector"])
    body = nt.nodes.new("ShaderNodeMix")
    body.data_type = "RGBA"
    body.inputs["A"].default_value = toon._rgba(tuple(c * 0.75 for c in base))
    body.inputs["B"].default_value = toon._rgba(tuple(c * 1.35 for c in base))
    nt.links.new(_math(nt, "MULTIPLY_ADD", _ramp(nt, patch.outputs["Fac"], 0.35, 0.65), streaks, 0.5 * (1 - streaks)),
                 body.inputs["Factor"])
    # ... and a few thin lines where the current shears, meandering, broken, faint, drawn only near
    lines = nt.nodes.new("ShaderNodeTexNoise")
    lines.inputs["Scale"].default_value = 1.0
    lines.inputs["Detail"].default_value = 3.0
    nt.links.new(_xyz(nt, _math(nt, "MULTIPLY", along, 0.12 / scale), _math(nt, "MULTIPLY", across, 0.9 / scale),
                      _math(nt, "MULTIPLY", t, 0.05)), lines.inputs["Vector"])
    contour = _ramp(nt, _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", lines.outputs["Fac"], 0.5)), 0.012, 0.0)
    broken = _ramp(nt, patch.outputs["Fac"], 0.45, 0.6)
    line_k = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", contour, broken),
                   _math(nt, "MULTIPLY", _ramp(nt, dist, 45.0 * scale, 8.0 * scale), 0.35 * streaks))
    # the rain's rings and the flecks of its strikes
    rings, crowns = None, None
    for k, layer in enumerate(ring_layers(scale)):
        r, c = _rings(nt, drift, t, dist, k_rain, *layer, seed=3.7 * k + 0.5)
        rings = r if rings is None else _math(nt, "MAXIMUM", rings, r)
        crowns = c if crowns is None else _math(nt, "MAXIMUM", crowns, c)
    marks = _math(nt, "MAXIMUM", _math(nt, "MAXIMUM", _math(nt, "MULTIPLY", rings, 0.8), crowns), line_k, clamp=True)
    col = nt.nodes.new("ShaderNodeMix")
    col.data_type = "RGBA"
    nt.links.new(body.outputs["Result"], col.inputs["A"])
    col.inputs["B"].default_value = toon._rgba(light)
    nt.links.new(marks, col.inputs["Factor"])
    # the sky's pale light on a grazing surface (where the reflection's rays find no geometry, a probe gives the rest)
    inc = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Incoming"], inc.inputs[0])
    cos_i = _math(nt, "ABSOLUTE", inc.outputs["Z"])
    fres = _math(nt, "MULTIPLY_ADD", _math(nt, "POWER", _math(nt, "SUBTRACT", 1.0, cos_i), 5.0), 0.98, 0.02)
    # the swell: long and slow, across the flow
    swell = nt.nodes.new("ShaderNodeTexNoise")
    swell.inputs["Scale"].default_value = 1.0
    swell.inputs["Detail"].default_value = 3.0
    swell.inputs["Roughness"].default_value = 0.45
    nt.links.new(_xyz(nt, _math(nt, "MULTIPLY", along, 0.25 / scale), _math(nt, "MULTIPLY", across, 0.7 / scale),
                      _math(nt, "MULTIPLY", t, 0.12)), swell.inputs["Vector"])
    # the rain's chop: fine, quick, as hard as the rain (the reflection smeared, not mirrored)
    chop = nt.nodes.new("ShaderNodeTexNoise")
    chop.inputs["Scale"].default_value = 7.0 / scale
    chop.inputs["Detail"].default_value = 2.0
    nt.links.new(_xyz(nt, X, _math(nt, "MULTIPLY", Y, 1.0), _math(nt, "MULTIPLY", t, 1.5)), chop.inputs["Vector"])
    # glints along the sun's path, sparkling on the swell (SHINE)
    glint = None
    if sun is not None:
        sx, sy, sz = sun
        n = math.sqrt(sx * sx + sy * sy + sz * sz) or 1.0
        # the view's ray off a level surface
        refl = _vmath(nt, "MULTIPLY", geo.outputs["Incoming"], (-1.0, -1.0, 1.0))
        toward = _vmath(nt, "DOT_PRODUCT", refl, (sx / n, sy / n, sz / n))
        path = _ramp(nt, toward, 0.86, 0.995)
        spark = nt.nodes.new("ShaderNodeTexVoronoi")
        spark.inputs["Scale"].default_value = 1.0
        nt.links.new(_xyz(nt, _math(nt, "MULTIPLY", along, 2.2 / scale), _math(nt, "MULTIPLY", across, 5.0 / scale),
                          _math(nt, "MULTIPLY", t, 1.3)), spark.inputs["Vector"])
        fleck = _ramp(nt, spark.outputs["Distance"], 0.13, 0.03)
        crest = _ramp(nt, swell.outputs["Fac"], 0.45, 0.62)
        glint = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", path, k_shine),
                      _math(nt, "MULTIPLY_ADD", _math(nt, "MULTIPLY", fleck, crest), 1.6, _math(nt, "MULTIPLY", path, 0.25)))
    gmix = nt.nodes.new("ShaderNodeMix")
    gmix.data_type = "RGBA"
    gmix.blend_type = "ADD"
    nt.links.new(col.outputs["Result"], gmix.inputs["A"])
    gmix.inputs["B"].default_value = toon._rgba(tuple(c * 2.0 for c in shine_color))
    if glint is not None:
        nt.links.new(glint, gmix.inputs["Factor"])
    else:
        gmix.inputs["Factor"].default_value = 0.0
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(toon.flashed(nt, gmix.outputs["Result"], look.flash_lit, 0.25), em.inputs["Color"])
    # the reflection, through the bump of the rings, the swell and the chop
    height = _math(nt, "ADD", _math(nt, "MULTIPLY", rings, 0.6),
                   _math(nt, "ADD", _math(nt, "MULTIPLY", swell.outputs["Fac"], 0.5),
                         _math(nt, "MULTIPLY", chop.outputs["Fac"], _math(nt, "MULTIPLY", k_rain, 0.35))))
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = ripple
    bump.inputs["Distance"].default_value = 0.02 * scale
    nt.links.new(height, bump.inputs["Height"])
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    nt.links.new(_math(nt, "MULTIPLY_ADD", k_rain, 0.06, roughness), gl.inputs["Roughness"])
    nt.links.new(bump.outputs["Normal"], gl.inputs["Normal"])
    gl.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    # how much of it is the world's reflection: MIRROR, much more at a grazing angle (the rings' marks stay painted
    # over it)
    k_refl = _math(nt, "MULTIPLY", _math(nt, "MINIMUM", _math(nt, "MULTIPLY_ADD", fres, 2.4, 0.35), 1.0), k_mirror)
    k_refl = _math(nt, "MULTIPLY", k_refl, _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", marks, 0.7)), clamp=True)
    mirror_mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(k_refl, mirror_mix.inputs["Fac"])
    nt.links.new(em.outputs[0], mirror_mix.inputs[1])
    nt.links.new(gl.outputs[0], mirror_mix.inputs[2])
    # a breath of the sky's light on it at a grazing angle, whatever the reflection finds
    skyem = nt.nodes.new("ShaderNodeEmission")
    skyem.inputs["Color"].default_value = toon._rgba(sky)
    nt.links.new(_math(nt, "MULTIPLY", fres, _math(nt, "MULTIPLY_ADD", k_mirror, -0.3, 0.3)), skyem.inputs["Strength"])
    lit = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(mirror_mix.outputs[0], lit.inputs[0])
    nt.links.new(skyem.outputs[0], lit.inputs[1])
    # the distance's fog over all of it
    fog = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(toon.flashed(nt, look.fog, look.flash_lit, look.flash_fog), fog.inputs["Color"])
    fmix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fog_k, fmix.inputs["Fac"])
    nt.links.new(lit.outputs[0], fmix.inputs[1])
    nt.links.new(fog.outputs[0], fmix.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(fmix.outputs[0], out.inputs["Surface"])
    return mat


def probe(name: str, coll, location, *, radius: float = 60.0, resolution: str | None = None):
    """A sphere light probe at `location` reaching `radius` m: what a water surface's (or a wet plank's) reflection
    falls back on where its rays leave the frame (the sky, the far bank, the hut behind the lens), as EEVEE captures it
    each frame. Returns the object."""
    import bpy

    lp = bpy.data.lightprobes.new(name, "SPHERE")
    lp.influence_distance = radius
    if hasattr(lp, "clip_end"):
        lp.clip_end = 3000.0
    if resolution and hasattr(lp, "resolution"):
        lp.resolution = resolution
    ob = bpy.data.objects.new(name, lp)
    ob.location = location
    coll.objects.link(ob)
    return ob


def wet(mat, amount: float = 0.25, *, roughness: float = 0.12, tint=(1.0, 1.0, 1.0)):
    """`mat` (a toon material: an emission into its output) with a glossy coat over it: the world's light caught in
    a wet surface, `amount` (the WET Value node; 0 dry) of a reflection of `roughness`, tinted. Returns `mat`."""
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    if not out.inputs["Surface"].links:
        return mat
    src = out.inputs["Surface"].links[0].from_socket
    k = _value(nt, WET, amount)
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = roughness
    gcol = nt.nodes.new("ShaderNodeCombineColor")
    for ch, tv in zip(("Red", "Green", "Blue"), tint):
        nt.links.new(_math(nt, "MULTIPLY", k, tv), gcol.inputs[ch])
    nt.links.new(gcol.outputs[0], gl.inputs["Color"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(src, add.inputs[0])
    nt.links.new(gl.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return mat


def key(mat, node: str, frames_values) -> None:
    """Key `mat`'s Value node `node` (RAIN, MIRROR, SHINE, WET) to [(frame, value), ...]."""
    sock = mat.node_tree.nodes[node].outputs[0]
    for f, v in frames_values:
        sock.default_value = float(v)
        sock.keyframe_insert("default_value", frame=f)


def waterline(verts, edges, z: float) -> np.ndarray:
    """(k, 2): where a mesh's `edges` (pairs of indices into `verts`, (n, 3) world) cross the level `z`. Numpy only."""
    v = np.asarray(verts, float)
    e = np.asarray(edges, int).reshape(-1, 2)
    if not len(e):
        return np.zeros((0, 2))
    a, b = v[e[:, 0]], v[e[:, 1]]
    cross = (a[:, 2] - z) * (b[:, 2] - z) < 0
    a, b = a[cross], b[cross]
    k = ((z - a[:, 2]) / (b[:, 2] - a[:, 2]))[:, None]
    return (a + (b - a) * k)[:, :2]


def collar_ring(points, width: float, *, n: int = 32, pad: float = 0.01):
    """A band `width` wide hugging the outline of `points` (k, 2: a waterline) from outside: round its middle, at `n`
    bearings, from just past the furthest point that way (`pad` beyond it) out by `width`. Returns (verts (2n, 2),
    quads [(a, b, c, d)], how far out each vertex is (2n,): 0 the inner edge, 1 the outer). Numpy only."""
    p = np.asarray(points, float)
    c = p.mean(axis=0)
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    d = np.c_[np.cos(a), np.sin(a)]
    reach = np.max((p - c) @ d.T, axis=0) + pad            # the outline's support in each direction
    inner = c + d * reach[:, None]
    outer = c + d * (reach + width)[:, None]
    verts = np.r_[inner, outer]
    quads = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return verts, quads, np.r_[np.zeros(n), np.ones(n)]


def foam(name: str, color=(0.75, 0.78, 0.82), *, look=None, scene=None, amount: float = 1.0, scale: float = 1.0):
    """Foam and ripples where water meets something standing in it (a `collar`'s band, its "out" attribute 0 at the
    thing, 1 at the band's edge): a broken lace of `color` thick against it and thinning out, churning, with a few
    ripple rings running out from it; more of it the harder it rains (RAIN, keyable like a surface's) and how much at
    all by FOAM. Faded to the look's fog."""
    import bpy

    from . import toon

    look = look or toon.Look()
    scene = scene or bpy.context.scene
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    k_rain, k_foam = _value(nt, RAIN, 1.0), _value(nt, FOAM, amount)
    t = toon.frame_value(nt, scene)
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "out"
    out_ = at.outputs["Fac"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    lace = nt.nodes.new("ShaderNodeTexVoronoi")
    lace.feature = "DISTANCE_TO_EDGE"
    lace.inputs["Scale"].default_value = 9.0 / scale
    nt.links.new(_vmath(nt, "ADD", geo.outputs["Position"], _xyz(nt, 0.0, 0.0, _math(nt, "MULTIPLY", t, 0.35))),
                 lace.inputs["Vector"])
    churn = nt.nodes.new("ShaderNodeTexNoise")
    churn.inputs["Scale"].default_value = 5.0 / scale
    churn.inputs["Detail"].default_value = 3.0
    nt.links.new(_vmath(nt, "ADD", geo.outputs["Position"], _xyz(nt, 0.0, 0.0, _math(nt, "MULTIPLY", t, 0.6))),
                 churn.inputs["Vector"])
    # thick at the thing and thinning out, more of it in a downpour
    reach = _math(nt, "MULTIPLY_ADD", k_rain, 0.35, 0.3)
    dense = _ramp(nt, out_, reach, 0.0)
    strands = _ramp(nt, lace.outputs["Distance"], 0.09, 0.02)
    edge = _ramp(nt, _math(nt, "ADD", churn.outputs["Fac"], _math(nt, "MULTIPLY", dense, 0.6)), 0.55, 0.75)
    lace_k = _math(nt, "MAXIMUM", _math(nt, "MULTIPLY", strands, dense), _math(nt, "MULTIPLY", edge, dense))
    # ripples running out from it
    wave = _math(nt, "FRACT", _math(nt, "SUBTRACT", _math(nt, "MULTIPLY", out_, 2.5), _math(nt, "MULTIPLY", t, 0.9)))
    ripple = _math(nt, "MULTIPLY", _ramp(nt, _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", wave, 0.5)), 0.07, 0.0),
                   _math(nt, "MULTIPLY", _ramp(nt, out_, 1.0, 0.2), 0.55))
    alpha = _math(nt, "MULTIPLY", _math(nt, "MAXIMUM", lace_k, ripple), k_foam, clamp=True)
    alpha = _math(nt, "MULTIPLY", alpha, _ramp(nt, out_, 1.0, 0.75))           # never a hard outer edge
    fog_k, _ = _fog_k(nt, look)
    col = nt.nodes.new("ShaderNodeMix")
    col.data_type = "RGBA"
    col.inputs["A"].default_value = toon._rgba(color)
    nt.links.new(toon.flashed(nt, look.fog, look.flash_lit, look.flash_fog), col.inputs["B"])
    nt.links.new(fog_k, col.inputs["Factor"])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(toon.flashed(nt, col.outputs["Result"], look.flash_lit, 0.4), em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(alpha, mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mix.outputs[0], o.inputs["Surface"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    return mat


def collar(name: str, objects, z: float, material, coll, *, width: float = 0.35, n: int = 32, follow=None):
    """Foam round where each of `objects` (meshes, or lists of meshes standing as one: a post of staves) stands in
    water at height `z`: one band per object crossing it
    (`collar_ring` round its waterline), all in one mesh with the "out" attribute `foam` reads, a hair over the
    water. `follow`: an object the thing moves with (a boat's root): the band then follows its x, y and heading, but
    stays on the water while the boat bobs. Objects not crossing `z` are skipped. Returns the object (None: none
    crossed)."""
    import bpy
    from mathutils import Vector

    from . import shapes

    verts, faces, outs = [], [], []
    inv = None
    if follow is not None:
        bpy.context.view_layer.update()
        inv = follow.matrix_world.inverted()
    for group in objects:
        pts = []
        for ob in group if isinstance(group, (list, tuple)) else (group,):
            if ob.type != "MESH":
                continue
            me = ob.data
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            mw = np.array(ob.matrix_world)
            world = co @ mw[:3, :3].T + mw[:3, 3]
            if world[:, 2].min() >= z or world[:, 2].max() <= z:
                continue
            ed = np.empty(len(me.edges) * 2, int)
            me.edges.foreach_get("vertices", ed)
            pts.append(waterline(world, ed.reshape(-1, 2), z))
        pts = np.concatenate(pts) if pts else np.zeros((0, 2))
        if len(pts) < 3:
            continue
        v2, quads, o = collar_ring(pts, width, n=n)
        base = len(verts)
        for x, y in v2:
            p = (x, y, z + 0.004)
            if inv is not None:
                q = inv @ Vector(p)
                p = (q.x, q.y, 0.004)
            verts.append(p)
        faces += [tuple(base + i for i in q) for q in quads]
        outs += list(o)
    if not faces:
        return None
    ob = shapes.mesh_object(name, verts, faces, material, coll, smooth=False)
    a = ob.data.attributes.new("out", "FLOAT", "POINT")
    a.data.foreach_set("value", np.asarray(outs, np.float32))
    ob.visible_shadow = False
    ob.lineart.usage = "EXCLUDE"
    if follow is not None:
        cl = ob.constraints.new("COPY_LOCATION")
        cl.target = follow
        cl.use_z = False
        ob.location.z = z
        cr = ob.constraints.new("COPY_ROTATION")
        cr.target = follow
        cr.use_x = cr.use_y = False
    return ob


def puddle(name: str, material, coll, center, radius: float, z: float, *, seed: int = 1, n: int = 24,
           stretch: float = 1.0, angle: float = 0.0):
    """A pool lying flat at height `z`: a fan over `puddle_outline`."""
    from . import shapes

    rim = puddle_outline(center, radius, seed=seed, n=n, stretch=stretch, angle=angle)
    verts = [(center[0], center[1], z)] + [(x, y, z) for x, y in rim]
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    ob = shapes.mesh_object(name, verts, faces, material, coll, smooth=False)
    ob.visible_shadow = False
    ob.lineart.usage = "OCCLUSION_ONLY"     # its rim is water meeting mud, not an edge to ink
    return ob
