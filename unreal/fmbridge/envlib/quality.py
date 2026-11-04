"""Rendering quality presets for lighting: Lumen GI and reflections (software or hardware ray traced), virtual shadow
maps, volumetric fog resolution, as console variables (cvars) and PostProcessSettings fields.

Every cvar name and default was checked in the 5.8.4 source (docs/unreal/environment.md, API_NOTES). Notes:
- r.Lumen.HardwareRayTracing only takes effect when the project has ray tracing on (r.RayTracing, a project setting
  that needs an editor restart: URendererSettings.bEnableRayTracing); without it Lumen falls back to software tracing.
- r.MegaLights.Enable does not exist in 5.8: the project switch is r.MegaLights.EnableForProject and the per-volume
  switch the post setting `mega_lights` (bMegaLights).
- Engine code defaults differ from a new project's DefaultEngine.ini (GI 0 vs 1, reflections 2 vs 1, VSM 0 vs 1): a
  preset always sets them explicitly.
- The path tracer OOMs on a 24 GB L4 (docs/linux/engine.md): no preset uses it.
"""
from __future__ import annotations

GI = {"none": 0, "lumen": 1}                 # r.DynamicGlobalIlluminationMethod (2 = SSGI is deprecated)
REFLECTIONS = {"none": 0, "lumen": 1, "ssr": 2}  # r.ReflectionMethod
GI_ENUM = {"none": "DynamicGlobalIlluminationMethod.NONE", "lumen": "DynamicGlobalIlluminationMethod.LUMEN"}
REFL_ENUM = {"none": "ReflectionMethod.NONE", "lumen": "ReflectionMethod.LUMEN", "ssr": "ReflectionMethod.SCREEN_SPACE"}

PRESETS = {
    "preview": {"about": "fast iteration on a small GPU: software Lumen at low quality, coarse fog, VSM on",
                "gi": "lumen", "reflections": "lumen", "shadows": "vsm", "hwrt": False,
                "lumen": {"final_gather": 0.5, "reflection": 0.5, "scene_detail": 1.0, "scene_lighting": 0.5},
                "fog_grid": [16, 64], "vsm_bias": 0.5},
    "draft": {"about": "balanced: software Lumen at default quality",
              "gi": "lumen", "reflections": "lumen", "shadows": "vsm", "hwrt": False,
              "lumen": {"final_gather": 1.0, "reflection": 1.0, "scene_detail": 1.0, "scene_lighting": 1.0},
              "fog_grid": [16, 64], "vsm_bias": 0.0},
    "final": {"about": "the default for renders: hardware ray traced Lumen, higher gather and reflection quality",
              "gi": "lumen", "reflections": "lumen", "shadows": "vsm", "hwrt": True, "hit_lighting": "reflections",
              "lumen": {"final_gather": 2.0, "reflection": 2.0, "scene_detail": 2.0, "scene_lighting": 2.0},
              "fog_grid": [8, 128], "vsm_bias": -0.5},
    "cinematic": {"about": "the best the L4 can do in MRQ: HWRT Lumen with hit lighting, max gather, fine fog and VSM",
                  "gi": "lumen", "reflections": "lumen", "shadows": "vsm", "hwrt": True, "hit_lighting": "all",
                  "lumen": {"final_gather": 4.0, "reflection": 4.0, "scene_detail": 4.0, "scene_lighting": 4.0},
                  "fog_grid": [4, 128], "vsm_bias": -1.5},
    "no_gi": {"about": "direct light only (checking a rig without bounce): no GI, screen-space reflections",
              "gi": "none", "reflections": "ssr", "shadows": "vsm", "hwrt": False,
              "lumen": {}, "fog_grid": [16, 64], "vsm_bias": 0.0},
}

KEYS = {"preset", "gi", "reflections", "shadows", "hwrt", "hit_lighting", "lumen", "fog_grid", "vsm_bias", "megalights",
        "trace_mesh_sdfs", "cvars"}


def resolve(spec) -> dict:
    """A quality spec: a preset name, or {"preset": ..., overrides}, to the preset dict merged with the overrides."""
    if spec is None:
        spec = "final"
    if isinstance(spec, str):
        spec = {"preset": spec}
    spec = dict(spec)
    name = spec.pop("preset", "final")
    if name not in PRESETS:
        raise ValueError(f"unknown quality preset {name!r}; one of {sorted(PRESETS)}")
    bad = set(spec) - KEYS
    if bad:
        raise ValueError(f"quality: unknown key(s) {sorted(bad)}; allowed: {sorted(KEYS)}")
    q = {k: (dict(v) if isinstance(v, dict) else v) for k, v in PRESETS[name].items() if k != "about"}
    for k, v in spec.items():
        if k == "lumen":
            q["lumen"] = {**q.get("lumen", {}), **v}
        else:
            q[k] = v
    q["preset"] = name
    for k, allowed in (("gi", GI), ("reflections", REFLECTIONS)):
        if q[k] not in allowed:
            raise ValueError(f"quality.{k} must be one of {sorted(allowed)}, not {q[k]!r}")
    if q["shadows"] not in ("vsm", "maps"):
        raise ValueError(f"quality.shadows must be 'vsm' (virtual shadow maps) or 'maps', not {q['shadows']!r}")
    return q


def cvars(spec) -> dict:
    """The console variables of a quality spec (names checked in the 5.8.4 source)."""
    q = resolve(spec)
    out = {
        "r.DynamicGlobalIlluminationMethod": GI[q["gi"]],
        "r.ReflectionMethod": REFLECTIONS[q["reflections"]],
        "r.Shadow.Virtual.Enable": 1 if q["shadows"] == "vsm" else 0,
        "r.Lumen.HardwareRayTracing": 1 if q["hwrt"] else 0,
        "r.Lumen.Reflections.HardwareRayTracing": 1 if q["hwrt"] else 0,
        # 0 surface cache, 1 hit lighting for GI and reflections, 2 hit lighting for reflections only
        "r.Lumen.HardwareRayTracing.LightingMode": {None: 0, "none": 0, "all": 1, "reflections": 2}[q.get("hit_lighting")],
        "r.VolumetricFog.GridPixelSize": int(q["fog_grid"][0]),
        "r.VolumetricFog.GridSizeZ": int(q["fog_grid"][1]),
        "r.Shadow.Virtual.ResolutionLodBiasDirectional": float(q["vsm_bias"]),
    }
    if q.get("trace_mesh_sdfs") is not None:
        out["r.Lumen.TraceMeshSDFs"] = 1 if q["trace_mesh_sdfs"] else 0
    if q.get("megalights") is not None:
        out["r.MegaLights.EnableForProject"] = 1 if q["megalights"] else 0
    out.update(q.get("cvars") or {})
    return out


def post_fields(spec) -> dict:
    """The PostProcessSettings fields of a quality spec (the GI/reflection method and Lumen quality knobs)."""
    q = resolve(spec)
    out = {"dynamic_global_illumination_method": GI_ENUM[q["gi"]], "reflection_method": REFL_ENUM[q["reflections"]]}
    lum = q.get("lumen") or {}
    for k, f in (("final_gather", "lumen_final_gather_quality"), ("reflection", "lumen_reflection_quality"),
                 ("scene_detail", "lumen_scene_detail"), ("scene_lighting", "lumen_scene_lighting_quality"),
                 ("max_trace_distance", "lumen_max_trace_distance"), ("surface_cache", "lumen_surface_cache_resolution")):
        if k in lum:
            out[f] = float(lum[k])
    if q.get("hit_lighting") in ("all", "reflections"):
        out["lumen_ray_lighting_mode"] = ("LumenRayLightingModeOverride.HIT_LIGHTING" if q["hit_lighting"] == "all"
                                          else "LumenRayLightingModeOverride.HIT_LIGHTING_FOR_REFLECTIONS")
    if q.get("megalights") is not None:
        out["mega_lights"] = bool(q["megalights"])
    return out
