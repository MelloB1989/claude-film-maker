"""The look: materials (surface, emissive, glass), lights (rect, spot, point), atmosphere (volumetric fog), post-process
and cine cameras, plus quick stills through a camera for checking a frame without a render."""
from __future__ import annotations

import math
import os

import unreal

from . import op
from .assets import EAL, load
from .level import actor, look_rot, spawn, vec

MEL = unreal.MaterialEditingLibrary
BASE = "/Game/FM/Materials"


# a kind's graph revision: bump it when a kind's graph changes, and the next look.material rebuilds that parent in
# place (its instances keep their values); a parent is otherwise made once per project and never rebuilt
REV = {"GlowWipe": 2, "ScreenBlink": 1}  # GlowWipe 2: U masked to R only (rev 1's R+G mask failed to compile)


def _base(kind: str):
    """The parameterised parent materials the instances come from (made once per project, rebuilt on a new REV)."""
    path = f"{BASE}/M_FM_{kind}"
    rev = str(REV.get(kind, 1))
    if EAL.does_asset_exist(path):
        m = load(path)
        if EAL.get_metadata_tag(m, "fm_rev") == rev or kind not in REV:
            return m
        MEL.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(f"M_FM_{kind}", BASE, unreal.Material,
                                                                     unreal.MaterialFactoryNew())
    EAL.set_metadata_tag(m, "fm_rev", rev)

    def param(cls, name, x, y, default=None):
        e = MEL.create_material_expression(m, cls, x, y)
        e.set_editor_property("parameter_name", name)
        if default is not None:
            e.set_editor_property("default_value", default)
        return e
    col = param(unreal.MaterialExpressionVectorParameter, "Color", -500, 0)
    if kind in ("Pbr", "PbrMasked", "Sheer", "Glow", "GlowWipe"):
        _pbr(m, kind, col, param)
        MEL.recompile_material(m)
        EAL.save_asset(path)
        return m
    if kind in ("Screen", "ScreenBlink", "Textured"):  # Color tints a texture (Tex), tiled `Tiling` times
        uv = MEL.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -1100, -200)
        til = param(unreal.MaterialExpressionScalarParameter, "Tiling", -1100, -100, 1.0)
        uvm = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -900, -150)
        MEL.connect_material_expressions(uv, "", uvm, "A")
        MEL.connect_material_expressions(til, "", uvm, "B")
        tex = param(unreal.MaterialExpressionTextureSampleParameter2D, "Tex", -700, -200)
        tex.set_editor_property("texture", load("/Engine/EngineResources/DefaultTexture"))
        MEL.connect_material_expressions(uvm, "", tex, "UVs")
        tint = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -350, -50)
        MEL.connect_material_expressions(tex, "RGB", tint, "A")
        MEL.connect_material_expressions(col, "", tint, "B")
        col = tint
    if kind in ("Screen", "ScreenBlink"):  # a lit display: the picture is emitted, the glass is glossy black
        k = param(unreal.MaterialExpressionScalarParameter, "Intensity", -500, 200, 4.0)
        mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -200, 100)
        MEL.connect_material_expressions(col, "", mul, "A")
        MEL.connect_material_expressions(k, "", mul, "B")
        if kind == "ScreenBlink":
            mul = _blink(m, uv, mul, param)
        MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        black = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -200, 300)
        MEL.connect_material_property(black, "", unreal.MaterialProperty.MP_BASE_COLOR)
        MEL.connect_material_property(param(unreal.MaterialExpressionScalarParameter, "Roughness", -500, 400, 0.15), "",
                                      unreal.MaterialProperty.MP_ROUGHNESS)
    elif kind == "Emissive":
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        k = param(unreal.MaterialExpressionScalarParameter, "Intensity", -500, 200, 10.0)
        mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -250, 100)
        MEL.connect_material_expressions(col, "", mul, "A")
        MEL.connect_material_expressions(k, "", mul, "B")
        MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    else:  # Surface, Textured, Glass
        MEL.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
        for name, prop, d, y in (("Roughness", unreal.MaterialProperty.MP_ROUGHNESS, 0.6, 200),
                                 ("Metallic", unreal.MaterialProperty.MP_METALLIC, 0.0, 300),
                                 ("Specular", unreal.MaterialProperty.MP_SPECULAR, 0.5, 400)):
            MEL.connect_material_property(param(unreal.MaterialExpressionScalarParameter, name, -500, y, d), "", prop)
        if kind == "Glass":
            m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
            # lit as a surface (per-light specular), not as a volume: in the volume mode clear glass reads white
            m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
            MEL.connect_material_property(param(unreal.MaterialExpressionScalarParameter, "Opacity", -500, 500, 0.2), "",
                                          unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.save_asset(path)
    return m


def _blink(m, uv, emitted, param):
    """ScreenBlink: the emitted picture dimmed to `Blink` inside the UV rectangle CursorU0-U1 x CursorV0-V1 (a text
    cursor baked into the texture, keyed on and off in a sequence); 1 - (1 - Blink) x inside."""
    def ex(cls, x, y, *ins, **props):
        e = MEL.create_material_expression(m, cls, x, y)
        for k, v in props.items():
            e.set_editor_property(k, v)
        for (src, pin), slot in zip(ins, ("A", "B")):
            MEL.connect_material_expressions(src, "", e, slot if len(ins) > 1 else pin)
        return e

    def above(a, b, x, y):  # 1 where a > b (a hard step)
        d = ex(unreal.MaterialExpressionSubtract, x, y, (a, ""), (b, ""))
        return ex(unreal.MaterialExpressionSaturate, x + 300, y, (ex(unreal.MaterialExpressionMultiply, x + 150, y,
                                                                     (d, "A"), const_b=1000.0), ""))
    inside = None
    for i, (ch, lo, hi) in enumerate((("r", "CursorU0", "CursorU1"), ("g", "CursorV0", "CursorV1"))):
        c = ex(unreal.MaterialExpressionComponentMask, -1100, 700 + 300 * i, (uv, ""),
               **{k: k == ch for k in "rgba"})  # one channel: a new mask has R and G on
        y = 650 + 300 * i
        a = above(c, param(unreal.MaterialExpressionScalarParameter, lo, -1100, y + 100, 0.0), -900, y)
        b = above(param(unreal.MaterialExpressionScalarParameter, hi, -1100, y + 200, 0.0), c, -900, y + 150)
        both = ex(unreal.MaterialExpressionMultiply, -400, y, (a, ""), (b, ""))
        inside = both if inside is None else ex(unreal.MaterialExpressionMultiply, -300, 800, (inside, ""), (both, ""))
    off = ex(unreal.MaterialExpressionOneMinus, -400, 1300,
             (param(unreal.MaterialExpressionScalarParameter, "Blink", -600, 1300, 1.0), ""))
    lit = ex(unreal.MaterialExpressionOneMinus, -150, 1000, (ex(unreal.MaterialExpressionMultiply, -250, 1000,
                                                                (inside, ""), (off, "")), ""))
    return ex(unreal.MaterialExpressionMultiply, -100, 100, (emitted, ""), (lit, ""))


def _white(linear: bool) -> str:
    """A plain white texture of the right kind for a sampler (a colour one, or linear for masks): a sampler given a
    texture of the wrong kind renders the engine's checker instead."""
    name = f"T_FM_White{'Linear' if linear else ''}"
    path = f"/Game/FM/Textures/{name}"
    if not EAL.does_asset_exist(path):
        import struct
        import zlib
        png = os.path.join(unreal.Paths.project_saved_dir(), "fmbridge_white.png")
        row = b"\x00" + b"\xff\xff\xff" * 4
        chunk = lambda tag, data: (struct.pack(">I", len(data)) + tag + data
                                   + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
        with open(png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(row * 4)) + chunk(b"IEND", b""))
        t = unreal.AssetImportTask()
        t.filename, t.destination_path, t.destination_name = png, "/Game/FM/Textures", name
        t.automated, t.replace_existing, t.save = True, True, True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
        tex = load(path)
        tex.set_editor_property("srgb", not linear)
        if linear:
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        EAL.save_asset(path)
    return path


def _pbr(m, kind: str, col, param) -> None:
    """The textured kinds. Pbr: Tex (albedo) x Color, Normal, Mask (R roughness x Roughness, G metallic x Metallic),
    all tiled `Tiling` times. PbrMasked: Pbr cut out by Tex's alpha, two-sided (an engraving, a leaf). Sheer: a thin
    two-sided fabric that light passes through (foliage shading), Opacity dithered so it stays sorted, plus a little
    Glow of its own colour (backlit sheers). Glow: Tex x Color x Intensity added on top, unlit (a halo, a light leak).
    GlowWipe: Glow revealed left to right: lit where the card's U (0 at its left edge, unscaled by Tiling) is below
    `Reveal`, over a soft edge `Softness` wide (a sign switching on letter by letter, keyed in a sequence)."""
    def sample(name, x, y, default, stype):
        e = param(unreal.MaterialExpressionTextureSampleParameter2D, name, x, y)
        e.set_editor_property("texture", load(default))
        e.set_editor_property("sampler_type", getattr(unreal.MaterialSamplerType, stype))
        MEL.connect_material_expressions(uvm, "", e, "UVs")
        return e

    def mul(a, a_out, b, b_out, x, y):
        e = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, x, y)
        MEL.connect_material_expressions(a, a_out, e, "A")
        MEL.connect_material_expressions(b, b_out, e, "B")
        return e

    uv = MEL.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -1500, 0)
    til = param(unreal.MaterialExpressionScalarParameter, "Tiling", -1500, 100, 1.0)
    uvm = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -1300, 50)
    MEL.connect_material_expressions(uv, "", uvm, "A")
    MEL.connect_material_expressions(til, "", uvm, "B")
    tex = sample("Tex", -1000, -300, _white(False), "SAMPLERTYPE_COLOR")
    base = mul(tex, "RGB", col, "", -600, -200)
    P = unreal.MaterialProperty
    if kind in ("Glow", "GlowWipe"):
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
        k = param(unreal.MaterialExpressionScalarParameter, "Intensity", -600, 0, 10.0)
        glow = mul(base, "", k, "", -300, -100)
        if kind == "GlowWipe":  # saturate((Reveal - U) / Softness): 0 right of the edge, 1 once it has passed
            u = MEL.create_material_expression(m, unreal.MaterialExpressionComponentMask, -1300, 400)
            for c in "rgba":  # just U: a new mask has R and G on, and a float2 here fails to compile (a checker)
                u.set_editor_property(c, c == "r")
            MEL.connect_material_expressions(uv, "", u, "")
            reveal = param(unreal.MaterialExpressionScalarParameter, "Reveal", -1300, 500, 1.0)
            soft = param(unreal.MaterialExpressionScalarParameter, "Softness", -1300, 600, 0.03)
            sub = MEL.create_material_expression(m, unreal.MaterialExpressionSubtract, -1100, 450)
            MEL.connect_material_expressions(reveal, "", sub, "A")
            MEL.connect_material_expressions(u, "", sub, "B")
            div = MEL.create_material_expression(m, unreal.MaterialExpressionDivide, -900, 500)
            MEL.connect_material_expressions(sub, "", div, "A")
            MEL.connect_material_expressions(soft, "", div, "B")
            sat = MEL.create_material_expression(m, unreal.MaterialExpressionSaturate, -700, 500)
            MEL.connect_material_expressions(div, "", sat, "")
            glow = mul(glow, "", sat, "", -150, 0)
        MEL.connect_material_property(glow, "", P.MP_EMISSIVE_COLOR)
        return
    nrm = sample("Normal", -1000, 0, "/Engine/EngineMaterials/DefaultNormal", "SAMPLERTYPE_NORMAL")
    msk = sample("Mask", -1000, 300, _white(True), "SAMPLERTYPE_MASKS")  # TC_MASKS textures
    MEL.connect_material_property(base, "", P.MP_BASE_COLOR)
    MEL.connect_material_property(nrm, "RGB", P.MP_NORMAL)
    rough = param(unreal.MaterialExpressionScalarParameter, "Roughness", -700, 300, 0.6)
    metal = param(unreal.MaterialExpressionScalarParameter, "Metallic", -700, 400, 0.0)
    MEL.connect_material_property(mul(msk, "R", rough, "", -400, 300), "", P.MP_ROUGHNESS)
    MEL.connect_material_property(mul(msk, "G", metal, "", -400, 400), "", P.MP_METALLIC)
    MEL.connect_material_property(param(unreal.MaterialExpressionScalarParameter, "Specular", -700, 500, 0.5), "",
                                  P.MP_SPECULAR)
    if kind == "PbrMasked":
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        m.set_editor_property("two_sided", True)
        MEL.connect_material_property(tex, "A", P.MP_OPACITY_MASK)
    if kind == "Sheer":
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        m.set_editor_property("two_sided", True)
        op_ = param(unreal.MaterialExpressionScalarParameter, "Opacity", -700, 650, 0.6)
        cov = mul(msk, "B", op_, "", -450, 650)  # Mask's B: the weave's open area (white = thread)
        # the engine's DitherTemporalAA function: partial coverage as a temporal dither, resolved by TSR / MRQ samples
        dither = MEL.create_material_expression(m, unreal.MaterialExpressionMaterialFunctionCall, -250, 650)
        dither.set_editor_property("material_function",
                                   load("/Engine/Functions/Engine_MaterialFunctions02/Utility/DitherTemporalAA"))
        if MEL.connect_material_expressions(cov, "", dither, "Alpha Threshold"):
            MEL.connect_material_property(dither, "Result", P.MP_OPACITY_MASK)
        else:
            MEL.connect_material_property(cov, "", P.MP_OPACITY_MASK)
        trans = param(unreal.MaterialExpressionVectorParameter, "Transmission", -700, 800,
                      unreal.LinearColor(0.9, 0.85, 0.75, 1.0))
        MEL.connect_material_property(trans, "", P.MP_SUBSURFACE_COLOR)
        glow = param(unreal.MaterialExpressionScalarParameter, "Glow", -700, 900, 0.0)
        MEL.connect_material_property(mul(base, "", glow, "", -400, 900), "", P.MP_EMISSIVE_COLOR)


@op("look.material")
def material(name: str, color=(1.0, 1.0, 1.0), kind: str = "Surface", roughness: float = None, metallic: float = None,
             specular: float = None, intensity: float = None, opacity: float = None, texture: str = "",
             tiling: float = None, normal: str = "", mask: str = "", glow: float = None, transmission=None,
             folder: str = "/Game/FM/Materials", scalars: dict = None) -> str:
    """A material instance: kind Surface (color, roughness, metallic, specular), Textured (a texture tinted by color,
    tiled), Screen (an emitted texture x intensity behind glossy glass), Emissive (color x intensity, unlit), Glass
    (translucent, opacity), ScreenBlink (Screen with a baked-in cursor that blinks: scalars Blink 0-1 and the cursor's
    UV rectangle CursorU0, CursorU1, CursorV0, CursorV1), Pbr (texture, normal and mask maps; mask R x roughness,
    G x metallic), PbrMasked (Pbr cut out by the texture's alpha), Sheer (backlit thin fabric: mask B x opacity,
    dithered; transmission colour, glow), Glow (texture x color x intensity, additive) or GlowWipe (Glow revealed left to right: scalars Reveal 0-1 and
    Softness). `scalars` sets any other scalar parameters by name. Colours are linear. Re-running updates it."""
    path = f"{folder}/{name}"
    parent = _base(kind)
    mi = load(path) if EAL.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property("parent", parent)
    MEL.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(*color, 1.0))
    defaults = {"Tex": _white(False), "Normal": "/Engine/EngineMaterials/DefaultNormal", "Mask": _white(True)}
    for k, v in (("Tex", texture), ("Normal", normal), ("Mask", mask)):
        if v or kind in ("Pbr", "PbrMasked", "Sheer"):  # an unused map goes back to its plain default
            if k != "Tex" or v or kind not in ("Glow", "GlowWipe"):
                MEL.set_material_instance_texture_parameter_value(mi, k, load(v or defaults[k]))
    if transmission is not None:
        MEL.set_material_instance_vector_parameter_value(mi, "Transmission", unreal.LinearColor(*transmission, 1.0))
    for k, v in (("Roughness", roughness), ("Metallic", metallic), ("Specular", specular), ("Intensity", intensity),
                 ("Opacity", opacity), ("Tiling", tiling), ("Glow", glow), *(scalars or {}).items()):
        if v is not None:
            MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
    EAL.save_asset(path)
    return path


@op("look.apply")
def apply(label: str, material: str, slot=0) -> str:
    """Put a material on an actor's static meshes, in slot `slot`: its index or its name (an FBX's material name)."""
    for c in actor(label).get_components_by_class(unreal.StaticMeshComponent):
        if isinstance(slot, str):
            c.set_material_by_name(slot, load(material))
        else:
            c.set_material(slot, load(material))
    return label


@op("look.slots")
def slots(label: str, materials: dict = None) -> dict:
    """An actor's material slots by name ({slot: material}); `materials` sets those named (unknown names are
    reported, not guessed)."""
    out, missing = {}, []
    for c in actor(label).get_components_by_class(unreal.StaticMeshComponent):
        names = [str(n) for n in c.get_material_slot_names()]
        for name, mat in (materials or {}).items():
            if name in names:
                c.set_material_by_name(name, load(mat))
            else:
                missing.append(name)
        for k, name in enumerate(names):
            m = c.get_material(k)
            out[name] = m.get_path_name().split(".")[0] if m else None
    if missing:
        out["_missing"] = sorted(set(missing))
    return out


@op("look.light")
def light(label: str, kind: str = "rect", loc=(0, 0, 200), look_at=None, intensity: float = 10.0, color=None,
          temperature: float = None, width: float = 100, height: float = 100, cone: float = 30, radius: float = 2000,
          shadows: bool = True, specular: float = 1.0, volumetric: float = 1.0, barn_angle: float = None) -> str:
    """A light: kind rect (width/height, barn doors), spot (cone), point; aimed at `look_at`; colour (sRGB 0-1) or
    temperature (K); intensity in candelas."""
    cls = {"rect": "RectLight", "spot": "SpotLight", "point": "PointLight"}[kind]
    spawn(label, cls=cls, loc=loc)
    a = actor(label)
    if look_at is not None:
        a.set_actor_rotation(look_rot(loc, look_at), False)
    c = a.get_component_by_class(getattr(unreal, cls + "Component"))
    c.set_editor_property("intensity", float(intensity))
    if color is not None:
        r, g, b = [int(round(max(0.0, min(1.0, x)) * 255)) for x in color]  # sRGB 0-1; FColor by keyword (its order is BGRA)
        c.set_editor_property("light_color", unreal.Color(r=r, g=g, b=b, a=255))
    if temperature:
        c.set_editor_property("use_temperature", True)
        c.set_editor_property("temperature", float(temperature))
    c.set_editor_property("attenuation_radius", float(radius))
    c.set_editor_property("cast_shadows", shadows)
    c.set_editor_property("specular_scale", float(specular))
    c.set_editor_property("volumetric_scattering_intensity", float(volumetric))
    if kind == "rect":
        c.set_editor_property("source_width", float(width))
        c.set_editor_property("source_height", float(height))
        if barn_angle is not None:
            c.set_editor_property("barn_door_angle", float(barn_angle))
            c.set_editor_property("barn_door_length", 40.0)
    if kind == "spot":
        c.set_editor_property("outer_cone_angle", float(cone))
        c.set_editor_property("inner_cone_angle", float(cone) * 0.6)
    return label


@op("look.sky")
def sky(elevation: float = 30.0, azimuth: float = 0.0, lux: float = 60000.0, temperature: float = 5600.0,
        sky_intensity: float = 1.0, shadow_softness: float = 0.5, channels: list = (0,)) -> dict:
    """Daylight: a sun (directional light, `lux`) from `azimuth` degrees (0 = shining along +X, i.e. from behind the
    back wall towards the camera; 90 = shining along +Y) and `elevation` above the horizon, a sky atmosphere and a
    real-time captured sky light. `shadow_softness` is the sun's source angle in degrees."""
    spawn("FM_Sun", cls="DirectionalLight", loc=(0, 0, 500))
    sun = actor("FM_Sun")
    sun.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=-float(elevation), yaw=float(azimuth)), False)
    c = sun.get_component_by_class(unreal.DirectionalLightComponent)
    for k, v in (("intensity", float(lux)), ("use_temperature", True), ("temperature", float(temperature)),
                 ("atmosphere_sun_light", True), ("light_source_angle", float(shadow_softness)), ("cast_shadows", True)):
        c.set_editor_property(k, v)
    lc = unreal.LightingChannels()
    for k in range(3):
        lc.set_editor_property(f"channel{k}", k in channels)
    c.set_editor_property("lighting_channels", lc)
    spawn("FM_Atmosphere", cls="SkyAtmosphere", loc=(0, 0, 0))
    spawn("FM_SkyLight", cls="SkyLight", loc=(0, 0, 400))
    s = actor("FM_SkyLight").get_component_by_class(unreal.SkyLightComponent)
    s.set_editor_property("real_time_capture", True)
    s.set_editor_property("intensity", float(sky_intensity))
    return {"sun": "FM_Sun", "sky": "FM_SkyLight", "atmosphere": "FM_Atmosphere"}


@op("look.fog")
def fog(density: float = 0.02, volumetric: bool = True, albedo=(0.9, 0.9, 1.0), extinction: float = 0.5,
        height_falloff: float = 0.2, start: float = 0.0) -> str:
    """Exponential height fog with volumetric fog: haze in the air for light shafts and depth."""
    spawn("FM_Fog", cls="ExponentialHeightFog", loc=(0, 0, 0))
    c = actor("FM_Fog").get_component_by_class(unreal.ExponentialHeightFogComponent)
    for k, v in (("fog_density", density), ("fog_height_falloff", height_falloff), ("start_distance", start),
                 ("volumetric_fog", volumetric), ("volumetric_fog_albedo", unreal.Color(r=int(albedo[0] * 255), g=int(albedo[1] * 255), b=int(albedo[2] * 255), a=255)),
                 ("volumetric_fog_extinction_scale", extinction), ("fog_max_opacity", 1.0)):
        try:
            c.set_editor_property(k, v)
        except Exception:
            pass
    return "FM_Fog"


@op("look.post")
def post(settings: dict, label: str = "FM_Post") -> dict:
    """An unbound post-process volume; `settings` are PostProcessSettings fields (each override flag set for you)."""
    try:
        a = actor(label)
    except ValueError:
        spawn(label, cls="PostProcessVolume")
        a = actor(label)
    a.set_editor_property("unbound", True)
    s = a.get_editor_property("settings")
    applied = {}
    for k, v in settings.items():
        if isinstance(v, str) and "." in v:  # an enum, e.g. "AutoExposureMethod.AEM_MANUAL"
            e, m = v.split(".", 1)
            v = getattr(getattr(unreal, e), m)
        try:
            s.set_editor_property("override_" + k, True)
        except Exception:
            pass
        s.set_editor_property(k, v)
        applied[k] = str(v)
    a.set_editor_property("settings", s)
    return applied


@op("look.camera")
def camera(label: str, loc, look_at, focal: float = 50.0, aperture: float = 2.0, focus: float = None,
           filmback=(36.0, 20.25), pilot: bool = True) -> str:
    """A cine camera aimed at `look_at`, focused on it (or at `focus` cm); full-frame 16:9 filmback by default."""
    spawn(label, cls="CineCameraActor", loc=loc)
    a = actor(label)
    a.set_actor_rotation(look_rot(loc, look_at), False)
    c = a.get_cine_camera_component()
    fb = c.get_editor_property("filmback")
    fb.set_editor_property("sensor_width", float(filmback[0]))
    fb.set_editor_property("sensor_height", float(filmback[1]))
    c.set_editor_property("filmback", fb)
    c.set_editor_property("current_focal_length", float(focal))
    c.set_editor_property("current_aperture", float(aperture))
    fs = c.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.MANUAL)
    fs.set_editor_property("manual_focus_distance", float(focus) if focus else (vec(loc) - vec(look_at)).length())
    c.set_editor_property("focus_settings", fs)
    if pilot:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).pilot_level_actor(a)
    return label


@op("look.still")
def still(camera_label: str, path: str, width: int = 1920, height: int = 1080, timeout: float = 60.0):
    """A still through a camera at the viewport's quality, written to `path` on the workstation (png). A multi-tick
    job: it returns once the file is on disk."""
    import time
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    for _ in range(4):  # let streaming and temporal history settle on the current pose
        yield
    unreal.AutomationLibrary.take_high_res_screenshot(width, height, path, actor(camera_label))
    end = time.time() + timeout
    while time.time() < end:
        yield 0.2
        if os.path.exists(path) and os.path.getsize(path) > 0:
            yield 0.3  # the writer may still be flushing
            return {"path": path, "bytes": os.path.getsize(path)}
    raise TimeoutError(f"no still at {path} after {timeout}s")


@op("look.card")
def card(label: str, loc, width: float, height: float, material: str, yaw: float = 0.0, offset: float = 0.0) -> str:
    """A flat picture (a screen, a sign, a print) standing upright and facing +X turned by `yaw`, its image the right
    way up and unmirrored from the front; `offset` pushes it out along its facing (cm), e.g. to sit on a box's front."""
    fx, fy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    p = [loc[0] + fx * offset, loc[1] + fy * offset, loc[2]]
    # the engine plane: normal +Z, U along +X, V along +Y; this turns the normal to +X, U to -Y, V to -Z
    spawn(label, shape="plane", loc=p, rot_={"pitch": 0, "yaw": -90 + yaw, "roll": 90}, scale=[width / 100, height / 100, 1])
    apply(label, material)
    return label


@op("look.channels")
def channels(labels: list, channels: list = (0,)) -> dict:
    """Lighting channels (0-2) for actors: on a light, which surfaces it lights; on a mesh, character or groom, which
    lights reach it. The studio rule: the host's lights on 1 only, the set's on 0, the host itself on 0 and 1."""
    out = {}
    for lab in labels:
        a = actor(lab)
        lc = unreal.LightingChannels()
        for k in range(3):
            lc.set_editor_property(f"channel{k}", k in channels)
        n = 0
        # by name, fetched afresh each time: on a Blueprint actor (a MetaHuman) a property change reruns its
        # construction script, which replaces the other components, so references taken earlier go stale
        names = [c.get_name() for c in a.get_components_by_class(unreal.SceneComponent)]
        for name in names:
            c = next((c for c in actor(lab).get_components_by_class(unreal.SceneComponent) if c.get_name() == name), None)
            if isinstance(c, (unreal.LightComponent, unreal.PrimitiveComponent)):
                c.set_editor_property("lighting_channels", lc)
                n += 1
        out[lab] = n
    return out


@op("look.focus_track")
def focus_track(camera_label: str, target: str, offset=(0.0, 0.0, 0.0)) -> str:
    """Keep a cine camera focused on an actor as either moves: `offset` is in the target's own frame (cm), e.g. a
    MetaHuman's eyes above its feet."""
    c = actor(camera_label).get_cine_camera_component()
    fs = c.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.TRACKING)
    tr = fs.get_editor_property("tracking_focus_settings")
    tr.set_editor_property("actor_to_track", actor(target))
    tr.set_editor_property("relative_offset", vec(offset))
    fs.set_editor_property("tracking_focus_settings", tr)
    c.set_editor_property("focus_settings", fs)
    return camera_label
