"""Painted materials for anime and ink-wash backgrounds: a cel-banded surface (toon.cel's lit and shade by the light
it gets) that a background painter would have brushed rather than filled flat.

`wash(name, lit, shade, ...)` adds, each off unless asked:
- `mottle`: the tone wandering a little across the surface (wet mud, weathered wood, a slope's scrub), in patches
  about `mottle_scale` m across;
- `brush`: dry-brush streaks, noise drawn out along `brush_dir` (down a mountain's face, along planks), darkening
  (`brush` > 0) or lifting (< 0) the tone where the brush caught;
- `mist`: sumi's gradient: the surface fading into `mist` toward the foot of `mist_z` (world z from, to: all mist at
  the first, none at the second), its edge broken by noise `mist_noise` m high, so a ridge's crest stands dark and its
  foot dissolves into the mist below (each ridge the same ink: the layers come from the mist between them).

All of it then fades to the look's fog with distance like every toon material, and whitens with the scene's lightning
(toon.FLASH) by `flash`. It renders as emission. Colours linear RGB.
"""
from __future__ import annotations


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


def _mix(nt, k, a, b):
    from . import toon

    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    for sock, v in (("Factor", k), ("A", a), ("B", b)):
        if isinstance(v, tuple):
            mx.inputs[sock].default_value = toon._rgba(v)
        elif isinstance(v, (int, float)):
            mx.inputs[sock].default_value = float(v)
        else:
            nt.links.new(v, mx.inputs[sock])
    return mx.outputs["Result"]


def _noise(nt, vec, scale: float, detail: float = 3.0, roughness: float = 0.55):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = roughness
    nt.links.new(vec, n.inputs["Vector"])
    return n.outputs["Fac"]


def wash(name: str, lit, shade, *, look=None, cut: float = 0.38, soft: float = 0.03, flash: float | None = None,
         mottle: float = 0.0, mottle_scale: float = 2.0, brush: float = 0.0, brush_scale: float = 1.0,
         brush_dir: str = "z", brush_stretch: float = 12.0, mist=None, mist_z=(0.0, 50.0), mist_noise: float = 0.0):
    """A painted toon material (see the module): the lit and shade colours banded by the light at `cut`, mottled,
    dry-brushed and washed into mist as asked, faded to the fog."""
    import bpy

    from . import toon

    look = look or toon.Look()
    mat = bpy.data.materials.new(name)
    mat["toon_lit"] = list(lit)
    nt = toon.nodes(mat)
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(diff.outputs[0], s2r.inputs[0])
    lum = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(s2r.outputs["Color"], lum.inputs[0])
    band = nt.nodes.new("ShaderNodeMapRange")
    band.interpolation_type = "SMOOTHSTEP"
    band.inputs["From Min"].default_value = cut - soft
    band.inputs["From Max"].default_value = cut + soft
    nt.links.new(lum.outputs[0], band.inputs["Value"])
    k = look.flash_amount if flash is None else flash
    lit_c = toon.flashed(nt, lit, look.flash_lit, k) if k > 0 else lit
    col = _mix(nt, band.outputs["Result"], shade, lit_c)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    pos = geo.outputs["Position"]
    if mottle:
        m = _noise(nt, pos, 1.0 / mottle_scale, 4.0, 0.6)
        gain = _math(nt, "ADD", _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", m, 0.5), 2.0 * mottle), 1.0)
        vm = nt.nodes.new("ShaderNodeVectorMath")
        vm.operation = "SCALE"
        nt.links.new(col, vm.inputs[0])
        nt.links.new(gain, vm.inputs["Scale"])
        col = vm.outputs[0]
    if brush:
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(pos, sep.inputs[0])
        comb = nt.nodes.new("ShaderNodeCombineXYZ")
        for axis in "XYZ":
            s = 1.0 / brush_stretch if axis.lower() == brush_dir else 1.0
            nt.links.new(_math(nt, "MULTIPLY", sep.outputs[axis], s / brush_scale), comb.inputs[axis])
        streak = nt.nodes.new("ShaderNodeMapRange")
        streak.inputs["From Min"].default_value = 0.55
        streak.inputs["From Max"].default_value = 0.68
        nt.links.new(_noise(nt, comb.outputs[0], 4.0, 6.0, 0.7), streak.inputs["Value"])
        gain = _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", streak.outputs["Result"], brush))
        vm = nt.nodes.new("ShaderNodeVectorMath")
        vm.operation = "SCALE"
        nt.links.new(col, vm.inputs[0])
        nt.links.new(gain, vm.inputs["Scale"])
        col = vm.outputs[0]
    if mist is not None:
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(pos, sep.inputs[0])
        z = sep.outputs["Z"]
        if mist_noise:
            z = _math(nt, "ADD", z, _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", _noise(nt, pos, 0.012, 3.0), 0.5),
                                          2.0 * mist_noise))
        mk = nt.nodes.new("ShaderNodeMapRange")
        mk.interpolation_type = "SMOOTHSTEP"
        mk.inputs["From Min"].default_value = mist_z[0]
        mk.inputs["From Max"].default_value = mist_z[1]
        mk.inputs["To Min"].default_value = 1.0
        mk.inputs["To Max"].default_value = 0.0
        nt.links.new(z, mk.inputs["Value"])
        col = _mix(nt, mk.outputs["Result"], col, toon.flashed(nt, mist, look.flash_lit, look.flash_fog))
    col = toon._fog_mix(nt, col, look)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat
