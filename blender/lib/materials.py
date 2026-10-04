"""The film's palette as Blender materials.

Palette hexes are sRGB, as designed; Blender's shader inputs are linear (the working space is Linear Rec.709, the
engine's), so every colour goes through `linear()`. The satin matches the engine's satin bone (stage.ts harness,
Task 4's glyphs); `fiber` is the thread's: a matte fibre with a sheen, and an emissive core for the blood and moss
strands so they halate in the engine's post (only blood and moss may glow; keep bone's `emissive` at 0).

`linear` and PALETTE are bpy-free (tested under the tools project); the builders import bpy when called.
"""
from __future__ import annotations

PALETTE = {
    "ink": "#110d10", "ink2": "#161114", "panel": "#1e181c", "panel2": "#282027",
    "rule": "#2b2229", "ruleStrong": "#3e323b",
    "bone": "#ede7ea", "boneDim": "#a99fa5", "boneFaint": "#6f6469",
    "blood": "#c22b45", "bloodBright": "#dc4a63", "bloodDim": "#8e1f35",
    "moss": "#4aad63", "mossDim": "#1c3324",
}


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear(color: str) -> tuple[float, float, float]:
    """A palette name or an sRGB '#rrggbb' as linear RGB."""
    hexa = color if color.startswith("#") else PALETTE.get(color)
    if hexa is None:
        raise KeyError(f"not a palette colour: {color!r} (palette: {', '.join(PALETTE)})")
    n = int(hexa[1:], 16)
    return tuple(_to_linear(((n >> s) & 255) / 255) for s in (16, 8, 0))  # type: ignore[return-value]


def _rgba(color: str) -> tuple[float, float, float, float]:
    return (*linear(color), 1.0)


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
    mat, b = _principled(name or f"satin_{color.strip('#')}")
    b.inputs["Base Color"].default_value = _rgba(color)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = 0.12
    b.inputs["Sheen Weight"].default_value = sheen
    b.inputs["Sheen Roughness"].default_value = 0.6
    b.inputs["Sheen Tint"].default_value = _rgba(color)
    return mat


def fiber(color: str, sheen: float = 0.6, emissive: float = 0.0, *, roughness: float = 0.62, name: str | None = None):
    """Thread fibre: matte, with a fabric sheen that lights up at grazing angles. `emissive` > 0 gives the strand a
    glowing core in its own colour (for blood and moss: the engine's bloom keys on their chroma)."""
    mat, b = _principled(name or f"fiber_{color.strip('#')}")
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

    mat = bpy.data.materials.new(name or f"emit_{color.strip('#')}")
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
