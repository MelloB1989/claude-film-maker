"""Water and wet surfaces from code for anime and ink-wash shots: a river or a puddle whose surface the rain dimples
with rings (or that lies still as a mirror once it stops), and a wet sheen over any toon material.

- `surface(name, base, light, ...)`: water as a painting draws it: `base` with long drifting streaks of `light`, two
  sizes of rain rings opening and fading across it, and the world reflected in it (EEVEE ray tracing) through the
  rings' ripples. Its weather is three Value nodes a shot may key (`key`): RAIN (0 still, 1 a downpour: the rings, and
  how far they break the reflection), MIRROR (how much of the world it reflects) and SHINE (glitter: light caught in
  the swell, for a low sun on calm water).
- `wet(mat, amount)`: a toon material (toon.cel's emission) given a glossy coat on top: planks and mud glistening in
  the rain, or after it. Its WET Value node is keyable.
- `puddle_outline(...)` (numpy only, tested without Blender) and `puddle(...)`: a flat irregular pool lying on the
  ground, for `surface` (a smaller `scale`: rings sized to a puddle).

World axes as the shots use them: z up. Colours linear RGB.
"""
from __future__ import annotations

import math

import numpy as np

RAIN, MIRROR, SHINE, WET = "rain", "mirror", "shine", "wet"   # the keyable Value nodes, by name


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


def _math(nt, op: str, a, b=None, *, clamp: bool = False):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    m.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = float(v)
        else:
            nt.links.new(v, m.inputs[i])
    return m.outputs[0]


def _rings(nt, vec, t, scale: float, speed: float, width: float):
    """Rain rings in Voronoi cells of size 1/`scale`: in each a ring grows from its middle and fades, each cell at its
    own phase. Returns the ring's strength (0..1), also its height for a bump."""
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = scale
    nt.links.new(vec, vor.inputs["Vector"])
    phase = nt.nodes.new("ShaderNodeMath")
    phase.operation = "MULTIPLY_ADD"
    phase.inputs[1].default_value = speed
    nt.links.new(t, phase.inputs[0])
    nt.links.new(vor.outputs["Color"], phase.inputs[2])     # the cell's random colour (its red) offsets the phase
    fr = _math(nt, "FRACT", phase.outputs[0])
    off = _math(nt, "SUBTRACT", vor.outputs["Distance"], _math(nt, "MULTIPLY", fr, 0.45))
    ring = nt.nodes.new("ShaderNodeMapRange")
    ring.interpolation_type = "SMOOTHSTEP"
    ring.inputs["From Min"].default_value = width
    ring.inputs["From Max"].default_value = 0.0
    nt.links.new(_math(nt, "ABSOLUTE", off), ring.inputs["Value"])
    fade = _math(nt, "SUBTRACT", 1.0, fr)
    k = _math(nt, "MULTIPLY", ring.outputs["Result"], _math(nt, "MULTIPLY", fade, fade))
    return k


def surface(name: str, base, light, *, look=None, scene=None, rain: float = 1.0, mirror: float = 0.35,
            shine: float = 0.0, shine_color=(1.0, 0.8, 0.5), scale: float = 1.0, streaks: float = 1.0,
            roughness: float = 0.04, ripple: float = 0.25, flow=(0.15, 0.0)):
    """Water: `base` with drifting streaks of `light` (`streaks` 0 for none: a puddle), rain rings sized for
    `scale` (1 a river seen from a jetty; 3 or more a puddle's fine ones) opening across it with RAIN, a reflection by
    MIRROR (glossy, `roughness`) broken by the rings' ripples (`ripple` their bump strength) and a gentle swell, and
    with SHINE glints of `shine_color` where the swell catches the light. `flow` (m/s, x and y) carries the streaks
    downstream. Faded to the look's fog (toon.Look) with distance."""
    import bpy

    from . import toon

    look = look or toon.Look()
    scene = scene or bpy.context.scene
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    k_rain, k_mirror, k_shine = _value(nt, RAIN, rain), _value(nt, MIRROR, mirror), _value(nt, SHINE, shine)
    # in world metres: a plane scaled up keeps its rings their size
    wsep = nt.nodes.new("ShaderNodeSeparateXYZ")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nt.links.new(geo.outputs["Position"], wsep.inputs[0])
    t = toon.frame_value(nt, scene)
    # streaks: noise stretched along the flow, drifting with it
    speed = math.hypot(*flow) or 1.0
    fx, fy = (flow[0] / speed, flow[1] / speed) if any(flow) else (1.0, 0.0)
    along = _math(nt, "ADD", _math(nt, "MULTIPLY", wsep.outputs["X"], fx), _math(nt, "MULTIPLY", wsep.outputs["Y"], fy))
    across = _math(nt, "SUBTRACT", _math(nt, "MULTIPLY", wsep.outputs["Y"], fx), _math(nt, "MULTIPLY", wsep.outputs["X"], fy))
    sx = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", along, _math(nt, "MULTIPLY", t, math.hypot(*flow))), 0.08 / scale)
    sy = _math(nt, "MULTIPLY", across, 1.6 / scale)
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sx, comb.inputs["X"])
    nt.links.new(sy, comb.inputs["Y"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    noise.inputs["Detail"].default_value = 3.0
    nt.links.new(comb.outputs[0], noise.inputs["Vector"])
    streak = nt.nodes.new("ShaderNodeMapRange")
    streak.inputs["From Min"].default_value = 0.56
    streak.inputs["From Max"].default_value = 0.66
    nt.links.new(noise.outputs["Fac"], streak.inputs["Value"])
    streak_k = _math(nt, "MULTIPLY", streak.outputs["Result"], streaks)
    # two sizes of rain rings, in world metres
    big = _rings(nt, geo.outputs["Position"], t, 2.2 / scale * 0.5, 1.3, 0.03)
    fine = _rings(nt, geo.outputs["Position"], _math(nt, "MULTIPLY", t, 1.7), 5.5 / scale * 0.5, 1.9, 0.025)
    rings = _math(nt, "MULTIPLY", _math(nt, "MAXIMUM", big, _math(nt, "MULTIPLY", fine, 0.7)), k_rain)
    tot = _math(nt, "MAXIMUM", streak_k, rings, clamp=True)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = toon._rgba(base)
    mix.inputs["B"].default_value = toon._rgba(light)
    nt.links.new(tot, mix.inputs["Factor"])
    col = mix.outputs["Result"]
    # the swell: a slow broad noise; under SHINE its crests glitter
    swell = nt.nodes.new("ShaderNodeTexNoise")
    swell.inputs["Scale"].default_value = 0.9 / scale
    swell.inputs["Detail"].default_value = 4.0
    sw_vec = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(_math(nt, "MULTIPLY", wsep.outputs["X"], 0.35), sw_vec.inputs["X"])
    nt.links.new(_math(nt, "MULTIPLY", wsep.outputs["Y"], 1.4), sw_vec.inputs["Y"])
    nt.links.new(_math(nt, "MULTIPLY", t, 0.25), sw_vec.inputs["Z"])
    nt.links.new(sw_vec.outputs[0], swell.inputs["Vector"])
    glint = nt.nodes.new("ShaderNodeMapRange")
    glint.inputs["From Min"].default_value = 0.66
    glint.inputs["From Max"].default_value = 0.72
    nt.links.new(swell.outputs["Fac"], glint.inputs["Value"])
    gmix = nt.nodes.new("ShaderNodeMix")
    gmix.data_type = "RGBA"
    nt.links.new(_math(nt, "MULTIPLY", glint.outputs["Result"], k_shine, clamp=True), gmix.inputs["Factor"])
    nt.links.new(col, gmix.inputs["A"])
    gmix.inputs["B"].default_value = toon._rgba(shine_color)
    col = toon._fog_mix(nt, gmix.outputs["Result"], look)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    # the reflection, through a bump of the rings (as strong as the rain) and the swell
    height = _math(nt, "ADD", _math(nt, "MULTIPLY", _math(nt, "MAXIMUM", big, fine), k_rain),
                   _math(nt, "MULTIPLY", swell.outputs["Fac"], 0.35))
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = ripple
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(height, bump.inputs["Height"])
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = roughness
    nt.links.new(bump.outputs["Normal"], gl.inputs["Normal"])
    gcol = nt.nodes.new("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(k_mirror, gcol.inputs[ch])
    nt.links.new(gcol.outputs[0], gl.inputs["Color"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(em.outputs[0], add.inputs[0])
    nt.links.new(gl.outputs[0], add.inputs[1])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return mat


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
