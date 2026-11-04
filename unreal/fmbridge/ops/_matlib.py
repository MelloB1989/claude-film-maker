"""The material library's masters as graph specs (pure data, built by `mat.master` through _matgraph).

Every master is a parameterised parent: an instance (`mat.instance`) sets its parameters, nobody edits the master.
Parameters are documented in PARAMS (name -> what it does, with units) and listed by `mat.masters`.

Defaults are chosen so that an instance with no parameters set renders as a plain mid-grey surface of its kind, and
every texture parameter has a default texture of the matching kind (a colour map gets a white sRGB texture, a data
map a linear TC_MASKS one, a normal map a flat normal): a sampler fed a texture of the wrong kind draws the
engine's checker instead (unreal/README.md).

Units: colours are linear 0..1; emissive is in nits (cd/m2), since the engine's scene colour is in cd/m2 (Scene.h:
auto-exposure min/max "in pixel luminance (cd/m2)"): an emissive of 1.0 is 1 nit before exposure.
"""
from __future__ import annotations

LIB = "/Game/FM/Lib"
TEX = f"{LIB}/Textures"
# the library's own default textures (made by mat.master on first use: 4x4 PNGs, settings per kind)
DEFAULT_TEXTURES = {
    "T_Lib_White": {"rgb": (255, 255, 255), "srgb": True, "compression": "TC_DEFAULT"},
    "T_Lib_WhiteLinear": {"rgb": (255, 255, 255), "srgb": False, "compression": "TC_MASKS"},
    "T_Lib_Black": {"rgb": (0, 0, 0), "srgb": True, "compression": "TC_DEFAULT"},
    "T_Lib_FlatNormal": {"rgb": (128, 128, 255), "srgb": False, "compression": "TC_NORMALMAP"},
    # packed AO/Roughness/Metallic: AO 1, roughness 1, metallic 1, so the scalars Roughness/Metallic are the values
    "T_Lib_ORM": {"rgb": (255, 255, 255), "srgb": False, "compression": "TC_MASKS"},
}
WHITE, WHITE_LIN, BLACK, FLAT, ORM = (f"{TEX}/{n}" for n in DEFAULT_TEXTURES)

PARAMS = {
    "Tint": "linear colour multiplied into the base colour map (or the colour itself when no map is set)",
    "BaseColorMap": "base colour texture (sRGB)",
    "NormalMap": "tangent-space normal map (DirectX green; import OpenGL maps with flip_green)",
    "NormalStrength": "0 flat .. 1 as authored .. 2 exaggerated",
    "ORMMap": "packed map: R ambient occlusion, G roughness, B metallic (linear, TC_MASKS)",
    "AOMap": "ambient occlusion (R, linear)", "RoughnessMap": "roughness (R, linear)",
    "MetallicMap": "metallic (R, linear)",
    "Roughness": "0 mirror .. 1 matte; multiplies the roughness map's value (no map: it is the roughness)",
    "Metallic": "0 dielectric .. 1 metal; multiplies the metallic map (no map: it is the metallic)",
    "Specular": "dielectric reflectance, 0.5 = 4% (the default for almost everything)",
    "AOStrength": "0 ignores the AO map .. 1 full",
    "Tiling": "UV repeats of every map (1 = once over the mesh's UVs)",
    "OpacityMap": "cut-out mask (R, linear): white kept, black cut", "Opacity": "0 clear .. 1 solid",
    "UseBaseAlpha": "static switch: cut out by the base colour map's alpha instead of OpacityMap",
    "TranslucencyMap": "light passing through leaves/fabric (sRGB colour)",
    "Transmission": "linear colour of the light passing through (multiplies TranslucencyMap)",
    "IOR": "index of refraction of glass/liquid (1.0 none, 1.33 water, 1.5 glass)",
    "Color": "linear colour (normalised: its brightness comes from Luminance_nits)",
    "EmissiveMap": "emitted picture (sRGB)",
    "Luminance_nits": "emitted luminance in cd/m2 (nits): 100-300 a screen, 1000+ a lamp shade, 10000+ a bulb",
    "ScreenRoughness": "roughness of the glossy glass in front of a screen",
    "FuzzColor": "cloth sheen colour seen at grazing angles", "Cloth": "0..1 blend of the cloth sheen layer",
    "SubsurfaceColor": "colour of the light scattered under the surface (skin, wax, marble)",
    "SubsurfaceAmount": "0 none .. 1 full scattering (the subsurface opacity)",
    "DecalOpacity": "0 invisible .. 1 full decal",
}


def _uv(n: dict) -> None:
    n["uv"] = {"type": "TexCoord"}
    n["tiling"] = {"type": "Scalar", "name": "Tiling", "default": 1.0, "group": "UV"}
    n["uvt"] = {"type": "Multiply", "in": {"A": "uv", "B": "tiling"}}


def _tex(name: str, default: str, sampler: str, group: str = "Maps") -> dict:
    return {"type": "Texture", "name": name, "texture": default, "sampler": sampler, "group": group,
            "in": {"UVs": "uvt"}}


def _sc(name: str, default: float, group: str = "Surface") -> dict:
    return {"type": "Scalar", "name": name, "default": float(default), "group": group}


def _vec(name: str, default, group: str = "Surface") -> dict:
    return {"type": "Vector", "name": name, "default": list(default) + [1.0] * (4 - len(default)), "group": group}


def _surface(orm: bool) -> tuple:
    """Shared lit PBR core: base colour x tint, strength-scaled normal, roughness/metallic/AO from maps x scalars."""
    n: dict = {}
    _uv(n)
    n["base"] = _tex("BaseColorMap", WHITE, "color")
    n["tint"] = _vec("Tint", (0.5, 0.5, 0.5))
    n["col"] = {"type": "Multiply", "in": {"A": "base.RGB", "B": "tint.RGB"}}
    n["nrm"] = _tex("NormalMap", FLAT, "normal")
    n["nstr"] = _sc("NormalStrength", 1.0)
    n["nflat"] = {"type": "Lerp", "in": {"A": [0.0, 0.0, 1.0], "B": "nrm.RGB", "Alpha": "nstr"}}
    n["rough_s"] = _sc("Roughness", 0.5)
    n["metal_s"] = _sc("Metallic", 0.0)
    n["spec"] = _sc("Specular", 0.5)
    n["aostr"] = _sc("AOStrength", 1.0)
    if orm:
        n["orm"] = _tex("ORMMap", ORM, "masks")
        r, m, ao = "orm.G", "orm.B", "orm.R"
    else:
        n["aom"] = _tex("AOMap", WHITE_LIN, "masks")
        n["rgh"] = _tex("RoughnessMap", WHITE_LIN, "masks")
        n["mtl"] = _tex("MetallicMap", WHITE_LIN, "masks")
        r, m, ao = "rgh.R", "mtl.R", "aom.R"
    n["rough"] = {"type": "Multiply", "in": {"A": r, "B": "rough_s"}}
    n["metal"] = {"type": "Multiply", "in": {"A": m, "B": "metal_s"}}
    n["ao"] = {"type": "Lerp", "in": {"A": 1.0, "B": ao, "Alpha": "aostr"}}
    outs = {"BaseColor": "col", "Normal": "nflat", "Roughness": "rough", "Metallic": "metal", "Specular": "spec",
            "AmbientOcclusion": "ao"}
    return n, outs


def opaque(orm: bool = False) -> dict:
    n, outs = _surface(orm)
    return {"description": "opaque PBR" + (" (packed ORM map)" if orm else " (separate AO/roughness/metallic maps)"),
            "blend": "opaque", "shading": "default_lit", "usage": ["skeletal_mesh", "instanced", "nanite"],
            "nodes": n, "outputs": outs}


def masked(orm: bool = False) -> dict:
    n, outs = _surface(orm)
    n["opm"] = _tex("OpacityMap", WHITE_LIN, "masks")
    n["usealpha"] = {"type": "Switch", "name": "UseBaseAlpha", "default": False, "group": "Opacity",
                     "in": {"True": "base.A", "False": "opm.R"}}
    outs["OpacityMask"] = "usealpha"
    return {"description": "cut-out PBR (leaves, fences, lace): opacity map or base alpha, two-sided",
            "blend": "masked", "shading": "default_lit", "two_sided": True, "opacity_mask_clip": 0.333,
            "usage": ["skeletal_mesh", "instanced", "nanite"], "nodes": n, "outputs": outs}


def foliage() -> dict:
    spec = masked(orm=False)
    n, outs = spec["nodes"], spec["outputs"]
    n["trm"] = _tex("TranslucencyMap", WHITE, "color")
    n["trc"] = _vec("Transmission", (0.45, 0.6, 0.2), "Foliage")
    n["sss"] = {"type": "Multiply", "in": {"A": "trm.RGB", "B": "trc.RGB"}}
    outs["SubsurfaceColor"] = "sss"
    spec.update(description="foliage: cut-out, two-sided foliage shading with light passing through the leaf",
                shading="two_sided_foliage", nodes=n, outputs=outs)
    return spec


def glass() -> dict:
    n: dict = {"tint": _vec("Tint", (0.9, 0.95, 1.0)), "op": _sc("Opacity", 0.15),
               "rough": _sc("Roughness", 0.05), "spec": _sc("Specular", 0.5), "ior": _sc("IOR", 1.5),
               "metal": _sc("Metallic", 0.0)}
    return {"description": "glass/clear plastic/liquid: translucent, lit per pixel as a surface (lit as a volume, "
                           "clear glass reads white in a bright room), refraction by IOR",
            "blend": "translucent", "shading": "default_lit", "translucency_lighting": "surface_per_pixel",
            "two_sided": False, "usage": ["skeletal_mesh", "instanced"], "nodes": n,
            "outputs": {"BaseColor": "tint.RGB", "Opacity": "op", "Roughness": "rough", "Specular": "spec",
                        "Metallic": "metal", "Refraction": "ior"}}


def emissive() -> dict:
    n: dict = {}
    _uv(n)
    n["em"] = _tex("EmissiveMap", WHITE, "color")
    n["col"] = _vec("Color", (1.0, 1.0, 1.0), "Emission")
    n["nits"] = _sc("Luminance_nits", 100.0, "Emission")
    n["c"] = {"type": "Multiply", "in": {"A": "em.RGB", "B": "col.RGB"}}
    n["out"] = {"type": "Multiply", "in": {"A": "c", "B": "nits"}}
    return {"description": "unlit emitter (light panels, lamp shades, signs, a sky card): Color x EmissiveMap x "
                           "Luminance_nits cd/m2", "blend": "opaque", "shading": "unlit",
            "usage": ["skeletal_mesh", "instanced", "nanite"], "nodes": n, "outputs": {"EmissiveColor": "out"}}


def screen() -> dict:
    spec = emissive()
    n = spec["nodes"]
    n["rough"] = _sc("ScreenRoughness", 0.12, "Screen")
    spec.update(description="a lit display: the picture is emitted (Luminance_nits) behind glossy black glass that "
                            "still reflects the room", shading="default_lit",
                outputs={"EmissiveColor": "out", "BaseColor": [0.0, 0.0, 0.0], "Roughness": "rough",
                         "Specular": 0.5})
    return spec


def cloth() -> dict:
    n, outs = _surface(orm=False)
    n["fuzz"] = _vec("FuzzColor", (0.6, 0.6, 0.6), "Cloth")
    n["cl"] = _sc("Cloth", 1.0, "Cloth")
    n["rough_s"]["default"] = 0.7
    outs.update({"SubsurfaceColor": "fuzz.RGB", "CustomData0": "cl"})
    return {"description": "fabric (velvet, cotton, wool): the cloth shading model's sheen layer, FuzzColor x Cloth",
            "blend": "opaque", "shading": "cloth", "usage": ["skeletal_mesh", "instanced", "clothing"],
            "nodes": n, "outputs": outs}


def skin() -> dict:
    n, outs = _surface(orm=False)
    n["tint"]["default"] = [0.6, 0.45, 0.38, 1.0]
    n["rough_s"]["default"] = 0.45
    n["sssc"] = _vec("SubsurfaceColor", (0.85, 0.25, 0.15), "Subsurface")
    n["ssa"] = _sc("SubsurfaceAmount", 0.8, "Subsurface")
    outs.update({"SubsurfaceColor": "sssc.RGB", "Opacity": "ssa"})
    outs.pop("Metallic", None)  # skin is never metal
    for k in ("mtl", "metal", "metal_s"):
        n.pop(k)
    return {"description": "skin-safe subsurface (non-MetaHuman skin, wax, marble, fruit): the Subsurface shading "
                           "model, which needs no profile asset; MetaHuman skin keeps its own materials",
            "blend": "opaque", "shading": "subsurface", "usage": ["skeletal_mesh", "morph_targets"],
            "nodes": n, "outputs": outs}


def unlit() -> dict:
    n: dict = {}
    _uv(n)
    n["base"] = _tex("BaseColorMap", WHITE, "color")
    n["tint"] = _vec("Tint", (1.0, 1.0, 1.0))
    n["col"] = {"type": "Multiply", "in": {"A": "base.RGB", "B": "tint.RGB"}}
    return {"description": "unlit picture (a backdrop, a sky dome, a card that should not take light): "
                           "BaseColorMap x Tint shown as is", "blend": "opaque", "shading": "unlit",
            "two_sided": True, "usage": ["instanced"], "nodes": n, "outputs": {"EmissiveColor": "col"}}


def decal() -> dict:
    n: dict = {}
    _uv(n)
    n["base"] = _tex("BaseColorMap", WHITE, "color")
    n["tint"] = _vec("Tint", (1.0, 1.0, 1.0))
    n["col"] = {"type": "Multiply", "in": {"A": "base.RGB", "B": "tint.RGB"}}
    n["nrm"] = _tex("NormalMap", FLAT, "normal")
    n["opm"] = _tex("OpacityMap", WHITE_LIN, "masks")
    n["dop"] = _sc("DecalOpacity", 1.0)
    n["a"] = {"type": "Multiply", "in": {"A": "opm.R", "B": "base.A"}}
    n["op"] = {"type": "Multiply", "in": {"A": "a", "B": "dop"}}
    n["rough"] = _sc("Roughness", 0.6)
    return {"description": "deferred decal (stains, posters, wear): base colour, normal and roughness projected, "
                           "faded by OpacityMap x base alpha x DecalOpacity",
            "domain": "deferred_decal", "blend": "translucent", "shading": "default_lit", "nodes": n,
            "outputs": {"BaseColor": "col", "Normal": "nrm.RGB", "Roughness": "rough", "Opacity": "op"}}


MASTERS = {
    "opaque": lambda: opaque(False), "opaque_orm": lambda: opaque(True), "masked": lambda: masked(False),
    "masked_orm": lambda: masked(True), "foliage": foliage, "glass": glass, "emissive": emissive, "screen": screen,
    "cloth": cloth, "skin": skin, "unlit": unlit, "decal": decal,
}


def master_path(name: str) -> str:
    """'opaque_orm' -> '/Game/FM/Lib/M_Lib_OpaqueOrm'."""
    return f"{LIB}/M_Lib_" + "".join(p.capitalize() for p in name.split("_"))
