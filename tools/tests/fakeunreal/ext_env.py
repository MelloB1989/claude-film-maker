"""WP5's fakes: environment and light actors with the engine's defaults, so env.*/light.* ops read real-looking values.

- Light components start as the engine's do (intensity_units Candelas for local lights in 5.x new defaults are
  Unitless in code: we start Unitless, as ULocalLightComponent's ctor, so ops must set the unit), temperature 6500
  off, white light colour, lighting channels [0].
- SkyAtmosphere / VolumetricCloud / SphereReflectionCapture / BoxReflectionCapture actors with their components.
- PostProcessVolume.settings is a PostProcessSettings struct with override_<field> flags (False) and defaults.
- Vector4 and LightingChannels value types; RendererSettings default object.
"""
from . import core


class Vector4(core.Object):
    def __init__(self, x=0.0, y=0.0, z=0.0, w=0.0):
        super().__init__("Vector4")
        object.__setattr__(self, "x", float(x))
        object.__setattr__(self, "y", float(y))
        object.__setattr__(self, "z", float(z))
        object.__setattr__(self, "w", float(w))

    def __eq__(self, o):
        return isinstance(o, Vector4) and (self.x, self.y, self.z, self.w) == (o.x, o.y, o.z, o.w)

    def __repr__(self):
        return f"Vector4({self.x}, {self.y}, {self.z}, {self.w})"


class LightingChannels(core.Object):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name or "LightingChannels", outer, **props)
        self._props.setdefault("channel0", True)
        self._props.setdefault("channel1", False)
        self._props.setdefault("channel2", False)


def _white():
    return core.Color(r=255, g=255, b=255, a=255)


LIGHT = {"intensity": 5000.0, "light_color": None, "use_temperature": False, "temperature": 6500.0,
         "cast_shadows": True, "specular_scale": 1.0, "diffuse_scale": 1.0, "volumetric_scattering_intensity": 1.0,
         "indirect_lighting_intensity": 1.0, "ies_texture": None, "use_ies_brightness": False,
         "ies_brightness_scale": 1.0}
LOCAL = {"intensity_units": "UNITLESS", "attenuation_radius": 1000.0}
POINT = {"source_radius": 0.0, "soft_source_radius": 0.0, "source_length": 0.0}
SPOT = {"inner_cone_angle": 0.0, "outer_cone_angle": 44.0}
RECT = {"source_width": 64.0, "source_height": 64.0, "barn_door_angle": 88.0, "barn_door_length": 20.0}
DIRECTIONAL = {"intensity": 10.0, "light_source_angle": 0.5357, "atmosphere_sun_light": False,
               "atmosphere_sun_light_index": 0, "cast_cloud_shadows": False}
SKY = {"intensity": 1.0, "real_time_capture": False, "source_type": "CAPTURED", "cubemap": None,
       "source_cubemap_angle": 0.0, "lower_hemisphere_is_black": True,
       "lower_hemisphere_color": None, "cast_shadows": True}
FOG = {"fog_density": 0.02, "fog_height_falloff": 0.2, "start_distance": 0.0, "fog_max_opacity": 1.0,
       "fog_cutoff_distance": 0.0, "fog_inscattering_luminance": None, "enable_volumetric_fog": False,
       "volumetric_fog_albedo": None, "volumetric_fog_extinction_scale": 1.0, "volumetric_fog_distance": 6000.0,
       "volumetric_fog_scattering_distribution": 0.2, "volumetric_fog_emissive": None}
ATMO = {"rayleigh_scattering_scale": 0.0331, "mie_scattering_scale": 0.003996, "mie_absorption_scale": 0.000444,
        "mie_anisotropy": 0.8, "multi_scattering_factor": 1.0, "aerial_pespective_view_distance_scale": 1.0,
        "height_fog_contribution": 1.0, "ground_albedo": None}
POST = {"auto_exposure_method": None, "auto_exposure_bias": 1.0, "auto_exposure_apply_physical_camera_exposure": True,
        "auto_exposure_min_brightness": -10.0, "auto_exposure_max_brightness": 20.0, "auto_exposure_speed_up": 3.0,
        "auto_exposure_speed_down": 1.0, "camera_iso": 100.0, "camera_shutter_speed": 60.0,
        "depth_of_field_fstop": 4.0, "white_temp": 6500.0, "white_tint": 0.0, "film_slope": 0.88, "film_toe": 0.55,
        "film_shoulder": 0.26, "film_black_clip": 0.0, "film_white_clip": 0.04, "bloom_intensity": 0.675,
        "bloom_threshold": -1.0, "vignette_intensity": 0.4, "film_grain_intensity": 0.0, "scene_fringe_intensity": 0.0,
        "color_grading_intensity": 1.0, "color_grading_lut": None, "scene_color_tint": None,
        "dynamic_global_illumination_method": None, "reflection_method": None, "lumen_final_gather_quality": 1.0,
        "lumen_reflection_quality": 1.0, "lumen_scene_detail": 1.0, "lumen_scene_lighting_quality": 1.0,
        "lumen_max_trace_distance": 20000.0, "lumen_surface_cache_resolution": 1.0, "lumen_ray_lighting_mode": None,
        "mega_lights": False}


def _defaults(obj, table: dict, fake) -> None:
    for k, v in table.items():
        if k in obj._props:
            continue
        if k in ("light_color",):
            v = _white()
        elif k in ("lower_hemisphere_color", "scene_color_tint"):
            v = core.LinearColor(0.0, 0.0, 0.0, 1.0) if k == "lower_hemisphere_color" else core.LinearColor(1, 1, 1, 1)
        elif k in ("fog_inscattering_luminance",):
            v = core.LinearColor(0.447, 0.638, 1.0, 1.0)
        elif k in ("volumetric_fog_albedo", "ground_albedo"):
            v = core.Color(r=255, g=255, b=255, a=255) if k == "volumetric_fog_albedo" else core.Color(r=170, g=170, b=170, a=255)
        elif k == "volumetric_fog_emissive":
            v = core.LinearColor(0.0, 0.0, 0.0, 1.0)
        elif k == "intensity_units":
            v = getattr(fake.LightUnits, v)
        elif k == "source_type":
            v = fake.SkyLightSourceType.SLS_CAPTURED_SCENE
        elif k == "auto_exposure_method":
            v = fake.AutoExposureMethod.AEM_HISTOGRAM
        elif k == "dynamic_global_illumination_method":
            v = fake.DynamicGlobalIlluminationMethod.LUMEN
        elif k == "reflection_method":
            v = fake.ReflectionMethod.LUMEN
        elif k == "lumen_ray_lighting_mode":
            v = fake.LumenRayLightingModeOverride.DEFAULT
        obj._props[k] = v
    obj._props.setdefault("lighting_channels", LightingChannels())


def install(fake):
    fake.Vector4 = Vector4
    fake.LightingChannels = LightingChannels
    fake._classes.update({"Vector4": Vector4, "LightingChannels": LightingChannels})

    def with_defaults(cls, *tables):
        orig = cls.__init__

        def __init__(self, name=None, outer=None, **props):
            orig(self, name, outer, **props)
            for t in tables:
                _defaults(self, t, fake)
        cls.__init__ = __init__

    # a fresh subclass per fake so patching never leaks between tests
    def sub(base, name, *tables, extra=None):
        cls = type(name, (base,), dict(extra or {}, __module__="unreal"))
        with_defaults(cls, *tables)
        fake._classes[name] = cls
        setattr(fake, name, cls)
        return cls

    PLC = sub(core.PointLightComponent, "PointLightComponent", LIGHT, LOCAL, POINT)
    SLC = sub(core.SpotLightComponent, "SpotLightComponent", LIGHT, LOCAL, POINT, SPOT)
    RLC = sub(core.RectLightComponent, "RectLightComponent", LIGHT, LOCAL, RECT)
    DLC = sub(core.DirectionalLightComponent, "DirectionalLightComponent", LIGHT, DIRECTIONAL)
    SKC = sub(core.SkyLightComponent, "SkyLightComponent", SKY,
              extra={"recapture_sky": lambda self: fake.calls.append(("SkyLightComponent.recapture_sky", (), {}))})
    FGC = sub(core.ExponentialHeightFogComponent, "ExponentialHeightFogComponent", FOG)
    for comp, cls in ((PLC, "PointLight"), (SLC, "SpotLight"), (RLC, "RectLight"), (DLC, "DirectionalLight")):
        prop = getattr(core, cls).COMPONENTS[0][0]
        sub(getattr(core, cls), cls, extra={"COMPONENTS": ((prop, comp),)})
    sub(core.SkyLight, "SkyLight", extra={"COMPONENTS": (("light_component", SKC),)})
    sub(core.ExponentialHeightFog, "ExponentialHeightFog", extra={"COMPONENTS": (("component", FGC),)})

    SAC = sub(core.SceneComponent, "SkyAtmosphereComponent", ATMO)
    sub(core.Actor, "SkyAtmosphere", extra={"COMPONENTS": (("component", SAC),)})

    def set_material(self, m):
        self._props["material"] = m
    VCC = sub(core.SceneComponent, "VolumetricCloudComponent", {"layer_bottom_altitude": 5.0, "layer_height": 10.0,
                                                                "material": None}, extra={"set_material": set_material})
    sub(core.Actor, "VolumetricCloud", extra={"COMPONENTS": (("volumetric_cloud_component", VCC),)})

    RCC = sub(core.SceneComponent, "ReflectionCaptureComponent", {"brightness": 1.0})
    SRC = sub(RCC, "SphereReflectionCaptureComponent", {"influence_radius": 3000.0})
    BRC = sub(RCC, "BoxReflectionCaptureComponent", {"box_transition_distance": 100.0})
    sub(core.Actor, "SphereReflectionCapture", extra={"COMPONENTS": (("capture_component", SRC),)})
    sub(core.Actor, "BoxReflectionCapture", extra={"COMPONENTS": (("capture_component", BRC),)})

    class PostProcessSettings(core.Object):
        def __init__(self, name=None, outer=None, **props):
            super().__init__(name or "PostProcessSettings", outer, **props)
            _defaults(self, POST, fake)
            for k in list(self._props):
                if k != "lighting_channels":
                    self._props["override_" + k] = False
            self._props["override_b_mega_lights"] = False
            for w in ("saturation", "contrast", "gamma", "gain", "offset"):
                for band in ("", "_shadows", "_midtones", "_highlights"):
                    k = f"color_{w}{band}"
                    self._props[k] = Vector4(0, 0, 0, 0) if w == "offset" else Vector4(1, 1, 1, 1)
                    self._props["override_" + k] = False

        def get_editor_property(self, name):
            if name not in self._props:
                raise Exception(f"Failed to find property '{name}' on PostProcessSettings")
            return self._props[name]

    fake.PostProcessSettings = PostProcessSettings
    fake._classes["PostProcessSettings"] = PostProcessSettings

    def ppv_init(self, name=None, outer=None, **props):
        core.Actor.__init__(self, name, outer, **props)
        self._props.update({"settings": PostProcessSettings(), "unbound": False, "priority": 0.0,
                            "blend_weight": 1.0, "enabled": True})
    sub(core.PostProcessVolume, "PostProcessVolume", extra={"__init__": ppv_init})

    rs = core.Object("RendererSettings")
    rs._props.update({"dynamic_global_illumination": fake.DynamicGlobalIlluminationMethod.LUMEN,
                      "reflections": fake.ReflectionMethod.LUMEN,
                      "shadow_map_method": fake.ShadowMapMethod.VIRTUAL_SHADOW_MAPS,
                      "use_hardware_ray_tracing_for_lumen": False})
    fake._singletons[fake.RendererSettings] = rs

    # cvars: execute_console_command "name value" updates fake.cvars (the getters read it)
    orig = fake.SystemLibrary.execute_console_command

    def execute_console_command(world_context_object, command, specific_player=None):
        orig(world_context_object, command, specific_player)
        parts = str(command).split()
        if len(parts) == 2:
            try:
                fake.cvars[parts[0]] = float(parts[1])
            except ValueError:
                pass
    fake.SystemLibrary.execute_console_command = staticmethod(execute_console_command)
