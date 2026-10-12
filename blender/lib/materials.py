"""Materials in the film's palette.

Colours are palette roles of the theme in use (lib/theme.py: render.py sets the film's) or sRGB '#rrggbb' hexes;
Blender's shader inputs are linear (the working space is Linear Rec.709, the engine's), so every colour goes through
`linear()`. `satin` matches the engine's satin surface (a soft dielectric with a thin clear coat and a little sheen);
`gloss` is a product finish (a clear-coated paint); `fiber` is thread: a matte fibre with a sheen, and optionally an
emissive core so a strand halates in the engine's post. Only the accents may glow (accent, accent2 and their shades):
keep an fg or bg material's `emissive` at 0.

`linear` is bpy-free (tested without Blender); the builders import bpy when called.
"""
from __future__ import annotations

from . import theme


def linear(color: str) -> tuple[float, float, float]:
    """A palette role of the theme in use (fg, accent, ...) or an sRGB '#rrggbb' as linear RGB."""
    return theme.linear(color)


def _rgba(color: str) -> tuple[float, float, float, float]:
    return (*linear(color), 1.0)


def _tag(color: str) -> str:
    return color.strip("#")


def _principled(name: str):
    """A new material whose tree is one Principled BSDF into the output; returns (material, bsdf)."""
    import bpy

    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:  # Blender < 5 made node trees on request
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if bsdf is None:
        nt.nodes.clear()
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat, bsdf


def satin(color: str, *, roughness: float = 0.38, coat: float = 0.25, sheen: float = 0.3, name: str | None = None):
    """Satin: a soft dielectric with a thin clear coat and a little sheen (the engine's MeshPhysicalMaterial satin:
    roughness 0.38, clearcoat 0.25 at 0.12, sheen 0.3 at 0.6)."""
    mat, b = _principled(name or f"satin_{_tag(color)}")
    b.inputs["Base Color"].default_value = _rgba(color)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = 0.12
    b.inputs["Sheen Weight"].default_value = sheen
    b.inputs["Sheen Roughness"].default_value = 0.6
    b.inputs["Sheen Tint"].default_value = _rgba(color)
    return mat


def gloss(color: str, *, roughness: float = 0.18, coat: float = 1.0, coat_roughness: float = 0.03,
          metallic: float = 0.0, name: str | None = None):
    """A product finish: a clear-coated paint (its base at `roughness` under a near-mirror coat), so a hero object
    carries crisp highlights of the key and the rim over its own colour. `metallic` > 0 turns the base to metal."""
    mat, b = _principled(name or f"gloss_{_tag(color)}")
    b.inputs["Base Color"].default_value = _rgba(color)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = coat_roughness
    b.inputs["Coat IOR"].default_value = 1.5
    return mat


def fiber(color: str, sheen: float = 0.6, emissive: float = 0.0, *, roughness: float = 0.62, name: str | None = None):
    """Thread fibre: matte, with a fabric sheen that lights up at grazing angles. `emissive` > 0 gives the strand a
    glowing core in its own colour (for the accents: the engine's bloom keys on their chroma)."""
    mat, b = _principled(name or f"fiber_{_tag(color)}")
    b.inputs["Base Color"].default_value = _rgba(color)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Specular IOR Level"].default_value = 0.35
    b.inputs["Sheen Weight"].default_value = sheen
    b.inputs["Sheen Roughness"].default_value = 0.35
    b.inputs["Sheen Tint"].default_value = (1.0, 1.0, 1.0, 1.0)
    if emissive > 0:
        b.inputs["Emission Color"].default_value = _rgba(color)
        b.inputs["Emission Strength"].default_value = emissive
    return mat


def emission(color: str, strength: float = 1.0, *, name: str | None = None):
    """A flat emitter (burned-in labels, light cards): shows `color` at `strength` whatever the lighting."""
    import bpy

    mat = bpy.data.materials.new(name or f"emit_{_tag(color)}")
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = _rgba(color)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat
