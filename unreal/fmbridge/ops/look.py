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


def _base(kind: str):
    """The parameterised parent materials the instances come from (made once per project)."""
    path = f"{BASE}/M_FM_{kind}"
    if EAL.does_asset_exist(path):
        return load(path)
    at = unreal.AssetToolsHelpers.get_asset_tools()
    m = at.create_asset(f"M_FM_{kind}", BASE, unreal.Material, unreal.MaterialFactoryNew())

    def param(cls, name, x, y, default=None):
        e = MEL.create_material_expression(m, cls, x, y)
        e.set_editor_property("parameter_name", name)
        if default is not None:
            e.set_editor_property("default_value", default)
        return e
    col = param(unreal.MaterialExpressionVectorParameter, "Color", -500, 0)
    if kind in ("Screen", "Textured"):  # Color tints a texture (Tex), tiled `Tiling` times
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
    if kind == "Screen":  # a lit display: the picture is emitted, the glass is glossy black
        k = param(unreal.MaterialExpressionScalarParameter, "Intensity", -500, 200, 4.0)
        mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -200, 100)
        MEL.connect_material_expressions(col, "", mul, "A")
        MEL.connect_material_expressions(k, "", mul, "B")
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
            MEL.connect_material_property(param(unreal.MaterialExpressionScalarParameter, "Opacity", -500, 500, 0.2), "",
                                          unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.save_asset(path)
    return m


@op("look.material")
def material(name: str, color=(1.0, 1.0, 1.0), kind: str = "Surface", roughness: float = None, metallic: float = None,
             specular: float = None, intensity: float = None, opacity: float = None, texture: str = "",
             tiling: float = None, folder: str = "/Game/FM/Materials") -> str:
    """A material instance: kind Surface (color, roughness, metallic, specular), Textured (a texture tinted by color,
    tiled), Screen (an emitted texture x intensity behind glossy glass), Emissive (color x intensity, unlit) or Glass
    (translucent, opacity). Colours are linear. Re-running updates it."""
    path = f"{folder}/{name}"
    parent = _base(kind)
    mi = load(path) if EAL.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property("parent", parent)
    MEL.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(*color, 1.0))
    if texture:
        MEL.set_material_instance_texture_parameter_value(mi, "Tex", load(texture))
    for k, v in (("Roughness", roughness), ("Metallic", metallic), ("Specular", specular), ("Intensity", intensity),
                 ("Opacity", opacity), ("Tiling", tiling)):
        if v is not None:
            MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
    EAL.save_asset(path)
    return path


@op("look.apply")
def apply(label: str, material: str, slot: int = 0) -> str:
    """Put a material on an actor's static meshes."""
    for c in actor(label).get_components_by_class(unreal.StaticMeshComponent):
        c.set_material(slot, load(material))
    return label


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
