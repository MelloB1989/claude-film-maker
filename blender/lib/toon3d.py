"""Anime shading for 3D characters: a modelled cast painted the way a theatrical anime paints a drawn one.

A 3D character shaded as a game shades it (one even toon band, a fixed shadow colour, every line one black) reads as
an avatar pasted into the shot. An anime colour designer paints a character in a base colour and two shades: the 1st
shade where the key light turns away, its edge softened to a gradient, cool under a rainy sky; a deep 2nd shade in
the core of the shadow, in the creases and where something casts its shadow (a chin on the neck, hair on the brow);
a sheen where it is wet; and lines coloured from the surface they go round (a dark brown round skin, a dark blue round
black hair), never black. The key comes from the side each character faces, so each has a key of its own.

- `Tone`: how one kind of surface is painted: where the 1st and 2nd shades fall and how soft their edges are, their
  colours (the lit colour times a tint), a bias (a face kept lit, hair shaded sooner), how much the creases deepen the
  shade, a wet sheen and a highlight band, how far the lit side whitens in a lightning flash, and its line's colour.
- `key(name, objects, toward, ...)`: a sun lighting only `objects` (light linking): one character's key. `aim` turns it
  (keyed per frame: a setup's light). Its strength is `ENERGY` whatever it lights; the shading reads it back as a
  fraction, so a key never brightens a painted colour, only moves the shades.
- `paint(mat, lit=, shade=, normal=, alpha=, tone=, key=)`: the shading built into a material from its own texture
  sockets: the signed facing toward the key (the key's direction, read by drivers off the light), dropped where the key
  is shadowed (the light's own shadow, read back through Shader to RGB), lowered in the creases (ambient occlusion),
  biased, then cut into the base, 1st and 2nd shade with smooth edges, the sheen and highlight over it, whitened by the
  scene's lightning (toon.FLASH). It renders as emission: what is painted is what the plate holds.
- `ink(mat, surface=, alpha=, tone=)`: an outline material's colour from the surface it goes round (`line`).
- `form(ob)`: the mesh's own smooth normals kept as it is posed (FORM), for a tone to shade by (`Tone.form`): a model
  whose custom normals flatten its face (VRoid's, made for one even band) gets back the shading of its nose, brow
  and cheekbones.

The pure halves (`facing`, `shades`, `line`, `smoothstep`, `toward_euler`, `light_axis` and the drivers' expressions)
are tested without Blender in blender/tests/test_toon3d.py. Colours are linear.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

RGB = tuple[float, float, float]

ENERGY = 4.2        # a key's strength (W/m2): a toon.cel prop lit by it bands as under the shots' own sun
FORM = "toon3d_form"    # a mesh attribute (vector per point, object space): its own smooth normals (`form`)


@dataclass(frozen=True)
class Tone:
    """How a kind of surface is painted. The light it gets is its facing toward the key, -1 (away) to 1 (square on),
    dropped toward `cast` where the key is shadowed and by up to `crease` in the creases, plus `bias`; above `cut` it is
    the base colour, below `deep_cut` the 2nd shade, the 1st between, each edge a gradient (`soft`, `deep_soft`)
    either side."""
    shade: RGB = (0.58, 0.6, 0.76)      # the 1st shade: the lit colour times this
    deep: RGB = (0.34, 0.35, 0.52)      # the 2nd shade, times the lit colour
    lit: RGB = (1.0, 1.0, 1.0)          # the base colour times this (a grade on the texture)
    cut: float = 0.0                    # facing where the 1st shade begins (0: where the light grazes)
    soft: float = 0.12
    deep_cut: float = -0.45             # ... and the 2nd
    deep_soft: float = 0.15
    bias: float = 0.0                   # added to the facing: + keeps a surface lit (a face), - shades it sooner
    cast: float = -0.3                  # the facing a cast shadow brings a lit surface down to (below deep_cut: deep)
    crease: float = 0.0                 # how far ambient occlusion lowers the facing in the creases
    crease_reach: float = 0.06          # ... looking this far (m)
    sheen: tuple | None = None          # (colour, width 0..1, strength): a wet fresnel sheen at grazing angles
    spec: tuple | None = None           # (colour, roughness, cut, strength): a highlight band on the lit side
    flash: float = 0.75                 # how far the lit colour goes to the flash's white at a lightning flash's height
    sink: float = 0.25                  # ... and how much darker the shade goes
    line_mul: float = 0.16              # the line's colour: the surface's times this ...
    line_add: RGB = (0.006, 0.007, 0.016)  # ... plus this (a dark blue: lines are never black)
    shaded: bool = True                 # False: the base colour everywhere (eyes, a drawn mouth), still flashed
    form: float = 0.0                   # how far the shading follows the mesh's own form (`form`) over its normals


def smoothstep(e0: float, e1: float, x: float) -> float:
    """0 below e0, 1 above e1, a smooth S between (as Blender's Map Range SMOOTHSTEP)."""
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def facing(ndl: float, visible: float, tone: Tone, occlusion: float = 1.0) -> float:
    """The light a point gets, as `paint` reads it: its facing toward the key `ndl` (-1..1), brought down toward
    `tone.cast` where the key is shadowed (`visible` 0) and by `tone.crease` where occluded (`occlusion` 0), biased."""
    v = min(1.0, max(0.0, visible))
    s = min(ndl, tone.cast) + (ndl - min(ndl, tone.cast)) * v
    return s - tone.crease * (1.0 - min(1.0, max(0.0, occlusion))) + tone.bias


def shades(s: float, color: RGB, tone: Tone, flash: float = 0.0, flash_color: RGB = (0.85, 0.9, 1.0)) -> RGB:
    """The painted colour of a surface of lit colour `color` (before the tone's `lit` grade) at light `s` (facing):
    the base, 1st and 2nd shades with their gradients, whitened by a lightning `flash` (0..1) on the lit side and
    sunk on the shaded."""
    base = tuple(c * g for c, g in zip(color, tone.lit))
    if not tone.shaded:
        k = flash * tone.flash
        return tuple(b + (f - b) * k for b, f in zip(base, flash_color))
    f1 = smoothstep(tone.cut - tone.soft, tone.cut + tone.soft, s)
    f2 = smoothstep(tone.deep_cut - tone.deep_soft, tone.deep_cut + tone.deep_soft, s)
    first = tuple(b * t for b, t in zip(base, tone.shade))
    second = tuple(b * t for b, t in zip(base, tone.deep))
    out = []
    for b, a1, a2, fc in zip(base, first, second, flash_color):
        shade = a2 + (a1 - a2) * f2
        c = shade + (b - shade) * f1
        c *= 1.0 - tone.sink * flash * (1.0 - f1)
        out.append(c + (fc - c) * flash * tone.flash * f1)
    return tuple(out)


def line(surface: RGB, tone: Tone) -> RGB:
    """A line's colour round a surface of colour `surface`: a deep dark of it, tinted (a dark brown round skin, a dark
    blue round black cloth or hair)."""
    return tuple(c * tone.line_mul + a for c, a in zip(surface, tone.line_add))


def toward_euler(toward) -> tuple[float, float, float]:
    """The XYZ Euler angles (radians) that turn a sun to shine from `toward` (the direction from the lit object to the
    light, any length): its -Z along -toward, its Y as near world up as it can be (mathutils'
    to_track_quat('-Z', 'Y'))."""
    x, y, z = (float(v) for v in toward)
    n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-12:
        raise ValueError(f"a light needs a direction, got {toward!r}")
    zc = (x / n, y / n, z / n)                        # the light's +Z: toward it
    up = (0.0, 0.0, 1.0) if abs(zc[2]) < 0.999 else (0.0, 1.0, 0.0)
    # its Y: world up made square to Z; its X: Y x Z
    d = sum(u * w for u, w in zip(up, zc))
    yc = tuple(u - d * w for u, w in zip(up, zc))
    m = math.sqrt(sum(c * c for c in yc))
    yc = tuple(c / m for c in yc)
    xc = (yc[1] * zc[2] - yc[2] * zc[1], yc[2] * zc[0] - yc[0] * zc[2], yc[0] * zc[1] - yc[1] * zc[0])
    # R (columns xc, yc, zc) = Rz Ry Rx: R[2][0] = -sin(ry)
    ry = math.asin(max(-1.0, min(1.0, -xc[2])))
    if abs(math.cos(ry)) > 1e-6:
        rx = math.atan2(yc[2], zc[2])
        rz = math.atan2(xc[1], xc[0])
    else:   # straight up or down: z folds into x
        rx, rz = math.atan2(-zc[1], yc[1]), 0.0
    return rx, ry, rz


def light_axis(euler) -> tuple[float, float, float]:
    """The direction toward a sun (its +Z in the world) turned by XYZ Euler angles `euler` (radians)."""
    rx, ry, rz = (float(a) for a in euler)
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    return cz * sy * cx + sz * sx, sz * sy * cx - cz * sx, cy * cx


# light_axis as driver expressions of the light's Euler angles (x, y, z): Blender's simple expressions, no Python
AXIS_EXPR = ("cos(z)*sin(y)*cos(x)+sin(z)*sin(x)", "sin(z)*sin(y)*cos(x)-cos(z)*sin(x)", "cos(y)*cos(x)")


# ---------------------------------------------------------------------------------------------------- Blender

def key(name: str, objects, toward=(1.0, 0.0, 1.0), *, coll=None, energy: float = ENERGY, angle: float = 2.0,
        color: RGB = (1.0, 1.0, 1.0)):
    """A sun shining from `toward` on `objects` alone (light linking: a key of one character's own), `angle` degrees
    across (its shadows' softness). Linked into `coll` (default the scene's collection). Returns the light object."""
    import bpy

    sun = bpy.data.lights.new(name, "SUN")
    sun.energy = float(energy)
    sun.angle = math.radians(angle)
    sun.color = color
    ob = bpy.data.objects.new(name, sun)
    (coll or bpy.context.scene.collection).objects.link(ob)
    lit = bpy.data.collections.new(f"{name}-lit")
    for o in objects:
        if o.name not in lit.objects:
            lit.objects.link(o)
    ob.light_linking.receiver_collection = lit
    ob["toon3d_energy"] = float(energy)
    aim(ob, toward)
    return ob


def aim(light, toward, frame: int | None = None) -> None:
    """Turn a sun to shine from `toward` (world), keyed at `frame` when given (held: a setup's light is set at its
    cut)."""
    light.rotation_mode = "XYZ"
    light.rotation_euler = toward_euler(toward)
    if frame is not None:
        light.keyframe_insert("rotation_euler", frame=frame)
        from . import toon

        for fc in toon._fcurves(light.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def _axis(nt, light):
    """A vector socket: the direction toward `light` (a sun) in the world, read off its rotation by drivers."""
    xyz = nt.nodes.new("ShaderNodeCombineXYZ")
    xyz.label = f"toward {light.name}"
    for i, expr in enumerate(AXIS_EXPR):
        fc = xyz.inputs[i].driver_add("default_value")
        d = fc.driver
        d.type = "SCRIPTED"
        for v, ch in zip("xyz", ("ROT_X", "ROT_Y", "ROT_Z")):
            var = d.variables.new()
            var.name = v
            var.type = "TRANSFORMS"
            var.targets[0].id = light
            var.targets[0].transform_type = ch
            var.targets[0].transform_space = "WORLD_SPACE"
        d.expression = expr
    return xyz.outputs[0]


class _Graph:
    """Node-building helpers over one material's node tree."""

    def __init__(self, mat):
        self.mat, self.nt = mat, mat.node_tree
        self.N, self.L = self.nt.nodes, self.nt.links

    def link(self, x, sock):
        if isinstance(x, (int, float)):
            sock.default_value = float(x)
        elif isinstance(x, tuple):
            sock.default_value = (*x, 1.0)[:len(sock.default_value)] if len(x) < len(sock.default_value) else x
        else:
            self.L.new(x, sock)

    def math(self, op, a, b=0.0, clamp=False):
        n = self.N.new("ShaderNodeMath")
        n.operation, n.use_clamp = op, clamp
        self.link(a, n.inputs[0])
        self.link(b, n.inputs[1])
        return n.outputs[0]

    def mix(self, a, b, fac, kind="MIX", clamp=True):
        n = self.N.new("ShaderNodeMix")
        n.data_type, n.blend_type, n.clamp_factor = "RGBA", kind, clamp
        for i, x in ((0, fac), (6, a), (7, b)):    # the factor, then the colour A and B (several sockets share a name)
            self.link(x, n.inputs[i])
        return n.outputs[2]

    def scaled(self, color, k):
        """`color` times `k` (a socket or a number; not clamped)."""
        return self.mix((0.0, 0.0, 0.0), color, k, clamp=False)

    def mul(self, a, b):
        return self.mix(a, b, 1.0, "MULTIPLY")

    def add(self, a, b):
        return self.mix(a, b, 1.0, "ADD")

    def step(self, x, lo, hi):
        r = self.N.new("ShaderNodeMapRange")
        r.interpolation_type = "SMOOTHSTEP"
        r.inputs["From Min"].default_value = lo
        r.inputs["From Max"].default_value = hi
        self.link(x, r.inputs["Value"])
        return r.outputs["Result"]

    def luma(self, shader):
        s2r = self.N.new("ShaderNodeShaderToRGB")
        self.L.new(shader, s2r.inputs[0])
        bw = self.N.new("ShaderNodeRGBToBW")
        self.L.new(s2r.outputs["Color"], bw.inputs[0])
        return bw.outputs[0]

    def output(self, color, alpha, *, camera_only: bool = False):
        """`color` as emission, see-through by `alpha` (a socket, or None), on a new active output (every other output
        made inactive). `camera_only`: seen by the camera alone, casting no shadow (an outline's hull round a body
        would shadow all of it)."""
        em = self.N.new("ShaderNodeEmission")
        self.link(color, em.inputs["Color"])
        sh = em.outputs[0]
        if camera_only:
            ray = self.N.new("ShaderNodeLightPath")
            seen = ray.outputs["Is Camera Ray"]
            alpha = seen if alpha is None else self.math("MULTIPLY", alpha, seen)
            self.mat.use_transparent_shadow = True
        if alpha is not None:
            tr = self.N.new("ShaderNodeBsdfTransparent")
            mx = self.N.new("ShaderNodeMixShader")
            self.link(alpha, mx.inputs["Fac"])
            self.L.new(tr.outputs[0], mx.inputs[1])
            self.L.new(sh, mx.inputs[2])
            sh = mx.outputs[0]
        for n in self.N:
            if n.bl_idname == "ShaderNodeOutputMaterial":
                n.is_active_output = False
                n.target = "CYCLES" if n.target == "ALL" else n.target
        out = self.N.new("ShaderNodeOutputMaterial")
        out.name = out.label = "toon3d"
        out.target = "ALL"
        self.L.new(sh, out.inputs["Surface"])
        out.is_active_output = True
        return out


def _coverage(g, alpha, cutoff):
    """The alpha a surface renders with: `alpha` as it is, cut at `cutoff` when given (a mask), or None (opaque)."""
    if alpha is None or cutoff is None:
        return alpha
    return g.math("GREATER_THAN", alpha, float(cutoff) - 1e-4)


def form(ob) -> None:
    """Keep the mesh's own smooth normals, as skinned and posed (its shape keys in), in its FORM attribute: a Geometry
    Nodes modifier right after its armature (Geometry Nodes' normals ignore custom ones). Once per object."""
    import bpy

    if any(m.type == "NODES" and m.node_group is not None and m.node_group.name == FORM for m in ob.modifiers):
        return
    ng = bpy.data.node_groups.get(FORM)
    if ng is None:
        ng = bpy.data.node_groups.new(FORM, "GeometryNodeTree")
        ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        gin, gout = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
        store = ng.nodes.new("GeometryNodeStoreNamedAttribute")
        store.data_type, store.domain = "FLOAT_VECTOR", "POINT"
        store.inputs["Name"].default_value = FORM
        ng.links.new(ng.nodes.new("GeometryNodeInputNormal").outputs["Normal"], store.inputs["Value"])
        ng.links.new(gin.outputs[0], store.inputs["Geometry"])
        ng.links.new(store.outputs[0], gout.inputs[0])
    mod = ob.modifiers.new("toon3d form", "NODES")
    mod.node_group = ng
    after = max((i for i, m in enumerate(ob.modifiers) if m.type == "ARMATURE"), default=-1)
    ob.modifiers.move(len(ob.modifiers) - 1, after + 1)


def _formed(g, n, k: float):
    """The normal `n` turned toward the mesh's own form (FORM, where it has one) by `k`."""
    attr = g.N.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = FORM
    world = g.N.new("ShaderNodeVectorTransform")
    world.vector_type, world.convert_from, world.convert_to = "NORMAL", "OBJECT", "WORLD"
    g.L.new(attr.outputs["Vector"], world.inputs[0])
    mix = g.N.new("ShaderNodeMix")
    mix.data_type, mix.clamp_factor = "VECTOR", True
    mix.inputs[0].default_value = float(k)
    g.link(n, mix.inputs[4])       # the vector A and B (several sockets share a name)
    g.L.new(world.outputs[0], mix.inputs[5])
    unit = g.N.new("ShaderNodeVectorMath")
    unit.operation = "NORMALIZE"
    g.L.new(mix.outputs[1], unit.inputs[0])
    return unit.outputs[0]


def paint(mat, *, lit, factor: RGB = (1.0, 1.0, 1.0), shade=None, normal=None, alpha=None, cutoff: float | None = None,
          tone: Tone = Tone(), key, flash_color: RGB = (0.85, 0.9, 1.0)):
    """Paint `mat` as anime from its own sockets: `lit` its base colour (a colour socket: a texture) times `factor`,
    `shade` the colour its shades are tinted from (default `lit`; times `factor` too), `normal` its shading normal
    (default the geometry's), `alpha` its coverage (a socket, or None for opaque; cut at `cutoff` when given: a mask),
    shaded by `tone` from the sun `key` (key()). A new active output; the material's old nodes stay, unused."""
    from . import toon

    g = _Graph(mat)
    flash = toon.scene_value(g.nt)
    lit = g.mul(lit, tuple(factor))
    base = g.mul(lit, tone.lit)
    col = base
    if tone.shaded:
        shade = g.mul(shade, tuple(factor)) if shade is not None else lit
        # the signed facing toward the key, and how much of the key the light's own shadow lets through
        geo = g.N.new("ShaderNodeNewGeometry")
        n = normal if normal is not None else geo.outputs["Normal"]
        if tone.form > 0:
            n = _formed(g, n, tone.form)
        dot = g.N.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        g.link(n, dot.inputs[0])
        g.L.new(_axis(g.nt, key), dot.inputs[1])
        ndl = dot.outputs["Value"]
        diff = g.N.new("ShaderNodeBsdfDiffuse")
        diff.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        g.link(n, diff.inputs["Normal"])
        got = g.math("MULTIPLY", g.luma(diff.outputs[0]), math.pi / float(key.get("toon3d_energy", ENERGY)))
        visible = g.math("DIVIDE", got, g.math("MAXIMUM", ndl, 0.05))
        # where it faces away the facing alone says it is shaded: count it seen
        visible = g.math("MAXIMUM", visible, g.math("LESS_THAN", ndl, 0.02), clamp=True)
        low = g.math("MINIMUM", ndl, tone.cast)
        s = g.math("ADD", low, g.math("MULTIPLY", g.math("SUBTRACT", ndl, low), visible))
        if tone.crease > 0:
            ao = g.N.new("ShaderNodeAmbientOcclusion")
            ao.inputs["Distance"].default_value = tone.crease_reach
            g.link(n, ao.inputs["Normal"])
            s = g.math("SUBTRACT", s, g.math("MULTIPLY", g.math("SUBTRACT", 1.0, ao.outputs["AO"]), tone.crease))
        # the mesh's own shading bias (toon.BIAS), where it has one
        attr = g.N.new("ShaderNodeAttribute")
        attr.attribute_type = "GEOMETRY"
        attr.attribute_name = toon.BIAS
        s = g.math("ADD", g.math("ADD", s, tone.bias), attr.outputs["Fac"])
        f1 = g.step(s, tone.cut - tone.soft, tone.cut + tone.soft)
        f2 = g.step(s, tone.deep_cut - tone.deep_soft, tone.deep_cut + tone.deep_soft)
        tinted = g.mul(shade, tone.lit)
        col = g.mix(g.mix(g.mul(tinted, tone.deep), g.mul(tinted, tone.shade), f2), base, f1)
        # a lightning flash: the shade sinks, the lit side whitens
        sink = g.math("MULTIPLY", g.math("MULTIPLY", flash, tone.sink), g.math("SUBTRACT", 1.0, f1))
        col = g.scaled(col, g.math("SUBTRACT", 1.0, sink))
        whiten = g.math("MULTIPLY", g.math("MULTIPLY", flash, tone.flash), f1)
        if tone.spec:
            scol, rough, scut, strength = tone.spec
            gl = g.N.new("ShaderNodeBsdfGlossy")
            gl.inputs["Roughness"].default_value = rough
            g.link(n, gl.inputs["Normal"])
            hi = g.step(g.math("MULTIPLY", g.luma(gl.outputs[0]), math.pi / float(key.get("toon3d_energy", ENERGY))),
                        scut - 0.05, scut + 0.05)
            col = g.add(col, g.scaled(scol, g.math("MULTIPLY", g.math("MULTIPLY", hi, f1), strength)))
        if tone.sheen:
            scol, width, strength = tone.sheen
            lw = g.N.new("ShaderNodeLayerWeight")
            lw.inputs["Blend"].default_value = 0.5
            g.link(n, lw.inputs["Normal"])
            rim = g.step(lw.outputs["Facing"], 1.0 - width - 0.04, 1.0 - width + 0.08)
            col = g.add(col, g.scaled(scol, g.math("MULTIPLY", rim, strength)))
    else:
        whiten = g.math("MULTIPLY", flash, tone.flash)
    col = g.mix(col, flash_color, whiten)
    return g.output(col, _coverage(g, alpha, cutoff))


def ink(mat, *, surface, factor: RGB = (1.0, 1.0, 1.0), alpha=None, cutoff: float | None = None, tone: Tone = Tone()):
    """An outline material's colour from the surface it goes round (`surface`, a colour socket, times `factor`):
    `line`, unlit and unflashed (ink stays as drawn in a flash); `alpha` and `cutoff` as `paint`'s. A new active
    output; the old nodes stay, unused."""
    g = _Graph(mat)
    col = g.add(g.scaled(g.mul(g.mul(surface, tuple(factor)), tone.lit), tone.line_mul), tone.line_add)
    return g.output(col, _coverage(g, alpha, cutoff), camera_only=True)
