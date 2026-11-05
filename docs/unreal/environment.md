# Environments, lighting & look (WP5: `env.*`, `light.*`, `look.*`)

The sky, the air, the light and the picture's look, all driven by numbers: the sun by time and place, a physical sky,
clouds, HDRI, fog, exposure in EV100, colour grades, Lumen/VSM/HWRT quality, and lights placed as rigs around a subject
with intensities in lux and ratios. One **environment spec** declares all of it and converges. Every change can be
checked without a viewport: `env.describe` (state as numbers), `light.measure` (analytic lux) and `env.meter` /
`env.check` (scene luminance and image statistics through a camera).

Code: `unreal/fmbridge/ops/env.py`, `ops/light.py`, `ops/_envutil.py` (helpers), `unreal/fmbridge/envlib/` (all the
maths and the planner, pure Python: sun, photometry, lights, rig, grade, quality, stats, spec), the client kinds
`tools/filmtools/unreal/env_kind.py`, schemas `tools/filmtools/unreal/schemas/{environment,lighting}.schema.json`,
examples `examples/unreal/{environment,lighting}/`, selftest `unreal/fmbridge/selftest/env.py`. `look.*` (older, in
`ops/look.py`) still works and is still the way to make materials, cameras and quick stills. Its lighting ops
(`look.light/sky/fog/post/channels`) are now a thin layer over the same writers as `light.*`/`env.*` (B56: one engine
path, pinned by `tests/test_ue_look_legacy.py` against the old implementation, deliberate differences listed there):
they keep their labels (`FM_Sun`, `FM_Fog`, ...), sRGB colours and arguments, and take over (adopt) lights saved by
the old code instead of failing as a conflict. For new work prefer `env.*`/`light.*`: physical units, specs, describe.

## 1. Recipes

**A whole environment from a preset, then check it**
```bash
film-ue op env.presets                                   # environment presets, times of day, grades, rigs, practicals
film-ue apply examples/unreal/environment/exterior-golden.yaml
film-ue plan  examples/unreal/environment/exterior-golden.yaml   # -> no steps: converged
film-ue op env.describe                                  # sun elevation/azimuth/lux, exposure ev100, fog, post, lights
film-ue op env.check camera=Wide                         # pass/issues/metrics: mean, clipping, crush, cast
```
Check: `"converged": true`; `env.check` `pass: true`. A failing issue's `fix` says what to change ("too dark by ~1.3
stops: lower env exposure ev100 by 1.3 or scale the lights by x2.5").

**The sun at a real place and time** (NOAA solar position; named times are solved for that day)
```bash
film-ue op env.atmosphere preset=hazy                     # first: with an atmosphere the sun is 120000 lux, tinted by the sky
film-ue op env.sun time=17:20 lat=19.07 lon=72.88 date=2026-11-05 tz=5.5 north_yaw_deg=-60
film-ue op env.sun time=golden_evening lat=19.07 lon=72.88 date=2026-11-05 tz=5.5   # the moment it is 6 deg up
film-ue op env.sun elevation_deg=25 azimuth_deg=240       # or explicit (compass azimuth, clockwise from north)
```
`north_yaw_deg` is the level yaw of geographic north (0 = +X). Check: `env.describe` -> `sun.elevation_deg`,
`azimuth_deg`, `hour`.

**Day/night (moods)**: put the night as a mood in the spec, then switch:
```bash
film-ue apply examples/unreal/environment/studio-day-night.yaml   # day
film-ue op env.mood mood=night spec_name=studio                    # only the differences run
film-ue op env.mood spec_name=studio                               # back
```
This generalises `films/host-studio/unreal/studio.py`'s `MOOD` switch: the mood overlay is merged over the spec, so a
mood lists only what changes (`sun: false`, a lower `exposure.ev100`, a cooler window, a dimmer rig).

**Light a character with a rig** (lux and ratio, not raw intensities)
```bash
film-ue op light.rig subject=Host camera=HostCam preset=interview key_lux=900 prefix=Host_
film-ue op light.rig subject=Host camera=HostCam preset=rembrandt key_lux=700 ratio=5 key_side=right \
    'lights={"rim":{"rel":1.6,"temperature":3200},"kicker":{}}' channels='[1]' prefix=Host_
film-ue op light.rig subject=Host camera=HostCam preset=loop key_side=short prefix=Host_   # key the far cheek
film-ue op light.measure 'at=[0,0,165]' key=Host_Key fill=Host_Fill      # lux per light, total, EV100, ratio
film-ue op light.channels 'assign={"Host":[0,1]}'                        # the character takes channel 1 (rig) and 0 (room)
```
Check: `light.rig` returns `measured` (key lux at the subject and the measured ratio). The subject point is ~eye height
of the actor's bounds; pass `socket=head` (a MetaHuman bone) or `subject_offset=[0,0,165]` to be exact.

**Expose by numbers**
```bash
film-ue op env.exposure mode=manual ev100=8.5          # fixed: a scene that meters EV100 8.5 renders mid grey
film-ue op env.exposure mode=manual ev100=auto         # from the brightest rig key (incident meter) or the sun
film-ue op env.exposure mode=auto min_ev100=4 max_ev100=12 speed=2
film-ue op env.meter camera=HostCam                    # scene.metered_ev100 vs the exposure: scene.stops_over
```
Closed loop (B50): measure a region and move the exposure, or the key light, until it reads at the target:
```bash
film-ue op env.autoexpose camera=HostCam subject=Host part=face target_stops=0.7      # skin ~2/3 stop over grey
film-ue op env.autoexpose camera=HostCam 'region=[0.4,0.2,0.6,0.45]' adjust=lights 'lights=["Host_Key","Host_Fill"]'
```
Check: `converged`, `iterations` (setting, display, error_stops), `before`/`after`; a re-run is `changed: false`.
The display target for 0 stops is `MID_GREY_DISPLAY` (0.46); the selftest records what a real grey card reads
(`grey_card_display`): set the constant to it if they differ.

EV100 guide: sun 14-15, overcast 12-13, bright interior / studio key 800-1000 lux 8.5, living room 5-6, night street
3-4, stylised moonlight 0-2 (`env.presets` -> `exposure_ev100`).

**Grade, quality, HDRI, fog, captures**
```bash
film-ue op env.grade preset=teal_orange 'fields={"vignette":0.2,"white_balance":6000,"lut":"/Game/LUT/T_Film"}'
film-ue op env.quality preset=cinematic                # cvars now + post fields; returns render_cvars for MRQ jobs
film-ue op env.fog preset=interior_haze extinction=0.1 # light shafts through a window: volumetric fog + a sun or rect
film-ue op env.hdri cubemap=/Game/HDRI/T_Courtyard rotation_deg=90   # sky light from an HDRI (backdrop=true: plugin)
film-ue op env.reflection_capture label=Room shape=box 'loc=[0,0,150]' 'extent_cm=[400,300,150]'
film-ue op env.captures_rebuild                         # slow on static-lit levels: it runs a lighting build
```

**Practicals** (fixtures in frame, physical output: lumens / nits)
```bash
film-ue op light.practical label=DeskLamp type=desk_lamp 'loc=[-180,60,140]' 'look_at=[-180,60,75]'
film-ue op light.practical label=TV type=screen 'loc=[-250,0,120]' 'look_at=[0,0,120]' nits=250
```
Pair each with an emissive surface at the same nits (WP2's `mat.*` emissive master: `Luminance_nits`), so what the
camera sees and what the light casts agree.

**The presets, in numbers** (`film-ue op env.preset name=<preset>`; B16)

| preset | sun | sky / fog | exposure (EV100) | grade | what it reads as |
|---|---|---|---|---|---|
| exterior_day | afternoon (35 deg), 120 klx above the atmosphere (~60 klx on level ground) | clear atmosphere, clouds, light fog | auto from the sun: 14.6 | neutral | clear afternoon |
| exterior_golden | golden_evening (6 deg) | hazy (Mie x3), clouds, haze | auto: 10.0 (a 6 deg sun on the ground ~2.3 klx) | golden_hour | low warm sun, long shadows |
| exterior_overcast | noon, 25 klx, 20 deg soft | hazy, thick clouds, sky light 1.5 | 12.5 | documentary | soft shadowless daylight |
| exterior_blue_hour | -5 deg (civil twilight) | clear, light fog | 6 | neutral, 7000 K | even blue light |
| exterior_night | none; moon 0.5 lux, 4100 K | clear, sky light 0.3 | 1 | moonlight | stylised moonlit night |
| interior_day | afternoon through the windows | clear, sky light 1, interior haze | 8.5 (a room at ~800 lux) | warm_film | a room by day |
| interior_night | none | sky light 0.05, interior haze | 5 (practicals ~50-100 lux) | warm_film | a room at night |
| studio_black | none | none | auto from the rig key (800 lux -> 8.3) | clean | black void, your rig only |
| studio_grey | none | captured sky light 0.5, grey ground | auto from the rig key | clean | soft grey studio |

Lux on a subject and the EV100 to expose it (incident, `photometry.ev100_from_illuminance`): 100000 -> 15.3,
10000 -> 12.0, 1000 -> 8.6, 800 -> 8.3, 500 -> 7.6, 100 -> 5.3, 50 -> 4.3, 5 -> 1.0, 0.25 (full moon) -> -3.3.

## 2. Op reference (`film-ue describe env`, `film-ue describe light`)

| op | what |
|---|---|
| `env.sun` / `env.moon` | the sun by time+place (NOAA) / named time / explicit; a moon (atmosphere light index 1) |
| `env.atmosphere` | SkyAtmosphere: presets clear crisp hazy smoggy dusty, haze/rayleigh multipliers |
| `env.clouds` | VolumetricCloud layer (km) |
| `env.sky_light` | realtime / captured / cubemap sky light; recaptures when changed (multi-tick) |
| `env.hdri` | HDRI: sky light from a cubemap, optional HDRIBackdrop (multi-tick) |
| `env.fog` | height + volumetric fog: presets none light haze mist dense ground interior_haze |
| `env.exposure` | manual EV100 / physical camera / auto range, on Env_Post |
| `env.grade` | grade presets (neutral clean warm_film teal_orange bleach_bypass noir_bw golden_hour moonlight pastel high_contrast vintage_fade documentary) + overrides |
| `env.post` | raw PostProcessSettings fields (override flags set for you), `clear` to un-override |
| `env.quality` | preview draft final cinematic no_gi: cvars + post fields (+ project renderer settings) |
| `env.cvars` | console variables, converging |
| `env.reflection_capture`, `env.captures_rebuild` | sphere/box captures; rebuild (slow, experimental) |
| `env.remove` | parts or everything a spec made |
| `env.describe` | everything above + lights, rigs, channels, owners, as numbers |
| `env.plan`, `env.apply`, `env.mood` | the spec: plan, converge (multi-tick), switch mood |
| `env.preset` | a whole environment from a preset (+ overrides): env.apply of a one-line spec |
| `env.presets`, `env.schema` | names and the JSON Schema |
| `env.meter`, `env.check` | scene/display statistics through a camera (or a region); a pass/issues verdict (camera or PNG) |
| `env.autoexpose` | closed loop: exposure or key light until a region (box, subject, face) hits a target in stops |
| `light.add` | one light, converging: lux at a point / candelas / lumens / nits, kelvin or colour, size, cone, IES, channels |
| `light.rig` | rigs: three_point interview loop rembrandt butterfly clamshell split high_key low_key noir silhouette window |
| `light.practical` | bulb lamp candle fire downlight desk_lamp streetlight tube led_strip neon screen phone window |
| `light.describe`, `light.measure` | lights as numbers; analytic lux at a point (no render) |
| `light.channels`, `light.remove` | lighting channels; remove by labels / rig / owner |

Every mutating op returns `changed` and converges: a re-run with the same arguments changes nothing. Env actors are
`Env_Sun`, `Env_Moon`, `Env_Atmosphere`, `Env_Clouds`, `Env_SkyLight`, `Env_HDRI`, `Env_Fog`, `Env_Post`; everything
the ops make is tagged `fm_env` + `fm_owner:<spec name>` and nothing else is ever modified or removed (an actor with the
same label that the ops did not make is a `conflict`).

## 3. Spec kinds: `environment` and `lighting`

```yaml
kind: environment            # lighting: only lights / rigs / practicals / channels (+ moods)
version: 1
name: studio                 # the owner: prune removes only what this name made
preset: interior_day         # exterior_day exterior_golden exterior_overcast exterior_blue_hour exterior_night
                             # interior_day interior_night studio_black studio_grey
mood: null                   # or one of moods (film-ue apply --set / env.mood)
sun: {time: "16:30", lat: 19.07, lon: 72.88, date: "2026-11-05", tz: 5.5, north_yaw_deg: -60}  # or false
moon: {elevation_deg: 40, intensity_lux: 1}
atmosphere: {preset: hazy, haze: 3}
clouds: {bottom_km: 1.5, height_km: 4}
sky_light: {intensity: 1.0}                    # mode realtime|captured|cubemap
hdri: {cubemap: /Game/HDRI/T_Sky, rotation_deg: 90, backdrop: false}
fog: {preset: interior_haze, extinction: 0.1}
exposure: {mode: manual, ev100: auto}          # auto: from the first rig's key_lux, else the sun
grade: {preset: warm_film, vignette: 0.2}
quality: final                                 # or {preset: cinematic, megalights: true}
post: {bloom_threshold: 1.0}                   # raw fields, last word
lights: {Window: {kind: rect, loc: [-250, 200, 150], look_at: [0, 0, 120], nits: 2000, width_cm: 120, height_cm: 150}}
rigs: {Host: {subject: Host, camera: HostCam, preset: interview, key_lux: 900, channels: [1]}}   # lights Host_Key...
practicals: {Lamp: {type: lamp, loc: [-200, -150, 120]}}
channels: {Host: [0, 1]}
reflection_captures: {Room: {shape: box, loc: [0, 0, 150], extent_cm: [400, 300, 150]}}
cvars: {r.HairStrands.SkyLighting: 0}
moods: {night: {sun: false, exposure: {ev100: 5}, grade: {preset: moonlight}}}
checks: {camera: HostCam, targets: {mean: [0.3, 0.55], clipped_max: 0.01}}
prune: true
```

- Merge order: preset, then the spec, then the mood (dicts merge key by key; `false`/`null` removes a section).
- The planner (`envlib/spec.py`, pure) resolves everything it can offline (sun position, lux, exposure, grade,
  quality, candelas) and compares with `env.describe` in the same terms: converged = an empty second plan. The same
  planner runs inside `env.apply` and behind `film-ue apply` (`env_kind.py`), so they always agree.
- Unknown fields are errors with did-you-mean, before anything changes (`fogg` -> "did you mean 'fog'?").
- Kinds `order`: environment 40, lighting 41 (after layout 30, before cameras 50).
- Examples: `examples/unreal/environment/studio-day-night.yaml`, `exterior-golden.yaml`, `hdri-product.yaml`,
  `examples/unreal/lighting/noir-alley.yaml` (tested: validate, plan, apply on the fake, converge).
- Regenerate the schemas after changing the tables: `cd tools && python -m filmtools.unreal.env_kind` (a test fails
  when they drift).

## 4. Units and conventions

- Light intensity: candelas for rect/spot/point (the ops set `intensity_units` Candelas), lux for directional.
  `lux` + `at` = the illuminance at that point on a surface facing the light (inverse square). `lumens` use Unreal's own
  conversion (point 4 pi, spot 2 pi (1 - cos half-angle), rect pi). `nits` x area for rect lights (screens, windows).
- Rig `ratio` is (key + fill) : fill (2 flat, 3 classic, 4 dramatic, 8 noir); `rel` is a multiple of the key's lux.
- Exposure is photographic EV100 (K = 12.5 reflected, C = 250 incident). Manual mode sets
  `AutoExposureBias = 0.526 - EV100` with physical camera exposure OFF, so a cine camera's aperture never changes the
  brightness (it would: `CineCameraComponent.cpp:709` writes its aperture into DepthOfFieldFstop). Unreal's own EV100
  (auto exposure min/max with the extended luminance range) is photographic EV100 - 0.526.
- Colours are linear [r, g, b]. FColor-backed properties (light colour, fog albedo, ground albedo) are 8-bit sRGB: the
  planner quantises the wanted colour the same way, so re-plans do not chase rounding.
- Rotations `{"pitch","yaw","roll"}`; the sun's light points the way light travels (pitch = -elevation).

## 5. Gotchas

- **HWRT needs ray tracing in the project.** `r.Lumen.HardwareRayTracing 1` does nothing unless the project has
  `r.RayTracing` on (`URendererSettings.bEnableRayTracing`, editor restart). `env.quality project=true` writes the GI,
  reflections, VSM and HWRT settings, not `bEnableRayTracing` (that needs a restart: do it in provisioning).
- **`r.MegaLights.Enable` does not exist** in 5.8: `r.MegaLights.EnableForProject` and the post field `mega_lights`.
- **Code defaults are not project defaults**: GI 0, reflections 2, VSM 0, extended luminance range 0 in code; a new
  project's DefaultEngine.ini has 1, 1, 1, True. Quality presets set them explicitly. If a project has the extended
  luminance range OFF, `mode: auto` min/max are read as luminance, not EV100 (manual is unaffected).
- **Sun intensity with and without an atmosphere.** Under a SkyAtmosphere the sun is the light above the atmosphere
  (120000 lux, 6500 K) and the atmosphere attenuates and tints it; without one, `auto` uses a clear-sky model by
  elevation (and a kelvin by elevation). Create the atmosphere before the sun (the planner orders it so).
- **Interiors with a physical sun**: the window will be blown out at an interior exposure (as on a real set). Add a
  `window` rect light (nits) for wrap, dim with `sky_light.intensity`, or grade.
- **Hair strands and the sky light**: `r.HairStrands.SkyLighting 0` indoors (unreal/README.md), put it in `cvars`.
- **Reflection captures** only rebuild through a lighting build (`LevelEditorSubsystem.build_light_maps(..., True)`;
  no console command exists). With Lumen reflections they are only a fallback; skip them unless translucency needs them.
- **HDRI**: an `.hdr` becomes a long-lat TextureCube only when `[TextureImporter] LoadHdrAsLongLatCubemap=1` (or the
  import is unattended); an `.exr` always imports as a 2D texture. The HDRIBackdrop plugin is off by default; its
  Blueprint variables (`cubemap`, `intensity`, `size`) could not be verified (no plugin Content in the source mirror):
  `env.hdri backdrop=true` reports them in `warnings` if they differ.
- **SceneColorHDR metering**: `env.meter` reads the capture raw (`bNormalize=False`, else values clamp to 0..1).
  Whether SceneColorHDR is pre-exposed in 5.8 is the one number the selftest calibrates (`meter_offset_stops`).
- **Rig subjects** default to ~eye height of the actor's bounds (0.86 of the half-height above centre); for a seated
  or posed character pass `socket=` or `subject_offset=`. `key_side: short|broad` takes the subject actor's yaw as
  the way its face points (+X front); if a character's mesh faces another axis in its actor, pass `facing_yaw_deg`.
- **Ownership**: a spec prunes only what its `name` made. Two specs that both define `sun` fight over `Env_Sun`.
- **Lights spawn Stationary** in the engine; the ops make theirs Movable (Lumen is dynamic; a Stationary light in an
  unbuilt level shows "lighting needs rebuild" and preview shadows in stills). Lights made elsewhere keep theirs.
- **Box captures**: the influence box is the actor's scale in cm (`ReflectionCaptureComponent.cpp:1358`), not a
  property: `extent_cm` sets the scale.

## 6. API_NOTES (verified on the UE 5.8.4 source box unless marked)

Paths are relative to the engine root; `C/` = `Engine/Source/Runtime/Engine/Classes/Components/`, `E/` =
`Engine/Source/Runtime/Engine/Classes/Engine/`. All light/sky/fog properties are BlueprintReadOnly + interp or
EditAnywhere: settable with `set_editor_property` only (PropertyAccessUtil.cpp:723), never by attribute.

| Python | C++ | file:line | verified |
|---|---|---|---|
| light `intensity`, `light_color` (FColor), `cast_shadows` | ULightComponentBase | C/LightComponentBase.h:37/44/58 | yes |
| `set_light_color(LinearColor, srgb=True)` | ULightComponent::SetLightColor | C/LightComponent.h:296 | yes |
| `temperature`, `use_temperature`, `specular_scale`, `diffuse_scale` | ULightComponent | C/LightComponent.h:57/69/90/96 | yes |
| `lighting_channels` (FLightingChannels channel0..2) | ULightComponent / UPrimitiveComponent | C/LightComponent.h:193, C/PrimitiveComponent.h:830, E/EngineTypes.h:563 | yes |
| `ies_texture`, `use_ies_brightness`, `ies_brightness_scale` | ULightComponent | C/LightComponent.h:219/223/227 | yes |
| `indirect_lighting_intensity`, `volumetric_scattering_intensity` | ULightComponentBase | C/LightComponentBase.h:116/120 | yes |
| `intensity_units` (LightUnits UNITLESS CANDELAS LUMENS EV NITS), `attenuation_radius` | ULocalLightComponent | C/LocalLightComponent.h:28/46, E/Scene.h:83 | yes |
| unit conversions (unitless = cd x 625, lumens, EV = 2^EV nits) | GetUnitsConversionFactor | Engine/Private/Components/LocalLightComponent.cpp:146-225, RectLightComponent.cpp:194/233, SpotLightComponent.cpp:97 | yes |
| `source_width/height`, `barn_door_angle/length` | URectLightComponent | C/RectLightComponent.h:33/40/46/52 | yes |
| `inner_cone_angle`, `outer_cone_angle` | USpotLightComponent | C/SpotLightComponent.h:23/27 | yes |
| `source_radius`, `soft_source_radius`, `source_length` | UPointLightComponent | C/PointLightComponent.h:45/52/59 | yes |
| `light_source_angle`, `atmosphere_sun_light(_index)`, `cast_cloud_shadows` | UDirectionalLightComponent | C/DirectionalLightComponent.h:138/164/170/198 | yes |
| SkyAtmosphere `rayleigh_scattering_scale`, `mie_scattering_scale`, `mie_absorption_scale`, `mie_anisotropy`, `multi_scattering_factor`, `ground_albedo` (FColor), `height_fog_contribution` | USkyAtmosphereComponent | C/SkyAtmosphereComponent.h:94/108/116/124/79/66/160 | yes |
| `aerial_pespective_view_distance_scale` (engine spelling) | USkyAtmosphereComponent | C/SkyAtmosphereComponent.h:156 | yes |
| `layer_bottom_altitude`, `layer_height`, `set_material()` | UVolumetricCloudComponent | C/VolumetricCloudComponent.h:36/40/186 | yes |
| default cloud material `/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst` | ctor | Engine/Private/Components/VolumetricCloudComponent.cpp:72 | path yes, asset not (no Content in mirror) |
| sky light `real_time_capture`, `source_type` (SkyLightSourceType.SLS_CAPTURED_SCENE / SLS_SPECIFIED_CUBEMAP), `cubemap`, `source_cubemap_angle`, `lower_hemisphere_is_black`, `lower_hemisphere_color`, `recapture_sky()` | USkyLightComponent | C/SkyLightComponent.h:108/112/116/120/143/146/304 | yes |
| fog `fog_density`, `fog_height_falloff`, `fog_inscattering_luminance` (5.x name), `start_distance`, `fog_max_opacity`, `fog_cutoff_distance` | UExponentialHeightFogComponent | C/ExponentialHeightFogComponent.h:23/30/43/120/116/128 | yes |
| `enable_volumetric_fog`, `volumetric_fog_albedo` (FColor), `volumetric_fog_extinction_scale`, `volumetric_fog_distance`, `volumetric_fog_scattering_distribution`, `volumetric_fog_emissive` | same | :136/151/163/169/144/159 | yes |
| PostProcessVolume `settings`, `priority`, `blend_weight`, `enabled`, `unbound` | APostProcessVolume | E/PostProcessVolume.h:28/35/43/47/51 | yes |
| PostProcessSettings fields + `override_<field>` | FPostProcessSettings | E/Scene.h:710 (exposure 1491-2022, colour 1507-1621, bloom 1629/1640, Lumen 1767-1866, mega_lights 1887, vignette 2143, grain 2181, LUT 2296/2300) | yes |
| `override_b_mega_lights` (bOverride_bMegaLights) | | E/Scene.h:805 | name form assumed; `env.post` tries both spellings |
| manual exposure = 2^(bias - EVcam), LensAttenuation 0.78 -> LuminanceMax 1 | GetEyeAdaptationScalarParameters, CalculateManualAutoExposure | Engine/Source/Runtime/Renderer/Private/PostProcess/PostProcessEyeAdaptation.cpp:376/446/519/596-715/810 | yes |
| cine camera writes its aperture into DepthOfFieldFstop | UCineCameraComponent | Engine/Source/Runtime/CinematicCamera/Private/CineCameraComponent.cpp:703-709 | yes |
| EV100ToLuminance = 2^EV | | Engine/Source/Runtime/RenderCore/Public/RenderUtils.h:744-768 | yes |
| captures: Sphere/BoxReflectionCapture, `influence_radius`, `box_transition_distance`, `brightness` | | E/SphereReflectionCapture.h:17, E/BoxReflectionCapture.h:16, C/SphereReflectionCaptureComponent.h:19, C/BoxReflectionCaptureComponent.h:19, C/ReflectionCaptureComponent.h:51 | yes |
| box influence = actor scale | UpdatePreviewShape | Engine/Private/Components/ReflectionCaptureComponent.cpp:1358 | yes |
| `SceneComponent.set_mobility(ComponentMobility.MOVABLE)`; lights default Stationary | SetMobility | C/SceneComponent.h:1296; Engine/Private/Light.cpp:190/244, RectLight.cpp:12, SpotLight.cpp:27 | yes |
| `LevelEditorSubsystem.build_light_maps(quality, with_reflection_captures)` | BuildLightMaps | Editor/LevelEditor/Public/LevelEditorSubsystem.h:222 | yes |
| SceneCapture2D `capture_component2d` (property: GetCaptureComponent2D is not a UFUNCTION), `capture_source`, `texture_target`, `fov_angle`, `capture_scene()`, `always_persist_rendering_state` | | E/SceneCapture2D.h:23, C/SceneCaptureComponent.h:81/132, C/SceneCaptureComponent2D.h:44/80/299 | yes |
| `RenderingLibrary.create_render_target2d(world, w, h, format)`, `read_render_target_raw(world, rt, normalize)` | UKismetRenderingLibrary | Engine/Classes/Kismet/KismetRenderingLibrary.h:48/192; normalize clamps: KismetRenderingLibrary.cpp:328 | yes |
| `SystemLibrary.execute_console_command`, `get_console_variable_float_value` | UKismetSystemLibrary | Engine/Classes/Kismet/KismetSystemLibrary.h:604/622 | yes |
| cvars r.DynamicGlobalIlluminationMethod, r.ReflectionMethod, r.Shadow.Virtual.Enable, r.Lumen.HardwareRayTracing(.LightingMode), r.Lumen.Reflections.HardwareRayTracing, r.VolumetricFog.GridPixelSize/GridSizeZ, r.Shadow.Virtual.ResolutionLodBiasDirectional, r.Lumen.TraceMeshSDFs, r.MegaLights.EnableForProject | | Renderer/Private/IndirectLightRendering.cpp:93/104, VirtualShadowMaps/VirtualShadowMapArray.cpp:161, Lumen/LumenHardwareRayTracingCommon.cpp:17/33, Lumen/LumenReflectionHardwareRayTracing.cpp:25, VolumetricFog.cpp:118/126, VirtualShadowMaps/VirtualShadowMapClipmap.cpp:43, Lumen/LumenDiffuseIndirect.cpp:97, MegaLights/MegaLights.cpp:27 | yes |
| RendererSettings `dynamic_global_illumination`, `reflections`, `shadow_map_method`, `use_hardware_ray_tracing_for_lumen` | URendererSettings | E/RendererSettings.h:600/605/668/621 | yes |
| HDRIBackdrop Blueprint `/HDRIBackdrop/Blueprints/HDRIBackdrop`, plugin off by default | | Engine/Plugins/Runtime/HDRIBackdrop/HDRIBackdrop.uplugin:13, HDRIBackdropPlacement.cpp:12 | path yes; BP variables **not verified** |
| .hdr import as long-lat cubemap: `[TextureImporter] LoadHdrAsLongLatCubemap` | UTextureFactory | Editor/UnrealEd/Private/Factories/EditorFactories.cpp:3503-3584 | yes |
| IES import: UTextureFactory -> UTextureLightProfile | | EditorFactories.cpp:2832/3601 | yes |
| embedded Python 3.11.8 | | Engine/Source/ThirdParty/Python3/Linux/include/patchlevel.h:26 | yes |
| `unreal.LightingChannels` (struct: channel0..2) | FLightingChannels (BlueprintType) | Engine/Source/Runtime/Engine/Classes/Engine/EngineTypes.h:563-584 | yes |
| `unreal.Vector4` (colour wheels: ColorSaturation ...) | FVector4 (noexport) | Engine/Source/Runtime/CoreUObject/Public/UObject/NoExportTypes.h:637 | yes |
| `unreal.LightingBuildQuality.QUALITY_PREVIEW..QUALITY_PRODUCTION` | ELightingBuildQuality | Engine/Source/Runtime/Engine/Classes/Engine/EngineTypes.h:1006 | yes |
| `unreal.get_default_object(cls)` | PythonScriptPlugin GetDefaultObject | Engine/Plugins/Experimental/PythonScriptPlugin/Source/PythonScriptPlugin/Private/PyCore.cpp:1624/2080 | yes |
| look.py (legacy material graphs) `MaterialExpressionCollectionParameter` | UMaterialExpressionCollectionParameter | Engine/Source/Runtime/Engine/Public/Materials/MaterialExpressionCollectionParameter.h:18 | yes |
| `MaterialExpressionComponentMask` | UMaterialExpressionComponentMask | Engine/Source/Runtime/Engine/Public/Materials/MaterialExpressionComponentMask.h:13 | yes |
| `MaterialExpressionConstant3Vector` | UMaterialExpressionConstant3Vector | Engine/Source/Runtime/Engine/Public/Materials/MaterialExpressionConstant3Vector.h:12 | yes |
| `MaterialExpressionDivide` / `Multiply` / `Subtract` / `Min` | UMaterialExpressionDivide / Multiply / Subtract / Min | Engine/Source/Runtime/Engine/Public/Materials/MaterialExpressionDivide.h:13, MaterialExpressionMultiply.h:13, MaterialExpressionSubtract.h:13, MaterialExpressionMin.h:13 | yes |
| `MaterialExpressionOneMinus` / `Saturate` | UMaterialExpressionOneMinus / Saturate | Engine/Source/Runtime/Engine/Public/Materials/MaterialExpressionOneMinus.h:13, MaterialExpressionSaturate.h:12 | yes |
| `MaterialExpressionMaterialFunctionCall` | UMaterialExpressionMaterialFunctionCall | Engine/Source/Runtime/Engine/Public/Materials/MaterialExpressionMaterialFunctionCall.h:80 | yes |
| `MaterialExpressionScalarParameter` / `VectorParameter` | UMaterialExpressionScalarParameter / VectorParameter | Engine/Source/Runtime/Engine/Public/Materials/MaterialExpressionScalarParameter.h:23, MaterialExpressionVectorParameter.h:13 | yes |
| `MaterialExpressionTextureCoordinate` / `TextureSampleParameter2D` | UMaterialExpressionTextureCoordinate / TextureSampleParameter2D | Engine/Source/Runtime/Engine/Public/Materials/MaterialExpressionTextureCoordinate.h:12, MaterialExpressionTextureSampleParameter2D.h:14 | yes |
| `MaterialParameterCollection`, `CollectionScalarParameter` | UMaterialParameterCollection, FCollectionScalarParameter | Engine/Source/Runtime/Engine/Public/Materials/MaterialParameterCollection.h:78/43 | yes |
| `MaterialParameterCollectionFactoryNew` | UMaterialParameterCollectionFactoryNew | Engine/Source/Editor/UnrealEd/Classes/Factories/MaterialParameterCollectionFactoryNew.h:15 | yes |
| `TextureCompressionSettings` (TC_MASKS ...) | TextureCompressionSettings (UENUM) | Engine/Source/Runtime/Engine/Classes/Engine/TextureDefines.h:391 | yes |
| SunPosition plugin (`get_sun_position`) | not used: envlib/sun.py is NOAA in pure Python (plugin off by default) | Plugins/Runtime/SunPosition/SunPosition.uplugin:13 | yes |

## 7. Selftest (`film-ue selftest env`, ~4 min on the L4, needs a GPU)

Builds a scratch level (floor, an 18% grey card, a pillar, two cameras) and proves: the **meter calibration** (a key
of 800 lux on the grey card meters EV100 8.52 and reads mid grey; metrics `meter_offset_stops`, `grey_card_display`);
`light.add`/`rig`/`practical` give the candelas and lux the maths says and converge; the sun lands where NOAA says and
reads back; every env op converges; one stop more exposure brightens the picture; `noir_bw` has no cast; `env.check`
passes a good frame and fails an underexposed one with a fix; a full spec converges, moods switch day -> night -> day,
prune removes only the spec's own; errors are actionable. Stills: the card, noir, golden hour, night. On the fake
engine it runs end to end in `tests/test_ue_env_selftest.py` (the three picture-dependent checks are judged on the box).

**If `meter_offset_stops` is not ~0 tomorrow**: SceneColorHDR is pre-exposed (or in other units). Correct it with one
constant in `env.meter` (scale the HDR pixels by 2^-offset before `scene_stats`) and re-run; nothing else depends on it.

## 8. Day-1 triage (`film-ue selftest env` on the GPU box)

Read `selftest-reports/<time>/env.json`: each failed check has `got`/`want`/`detail`; notes and metrics carry the two
calibration numbers. A check that fails with `status: error` and "has no property X" / "could not set X" is an engine
name: the row for X in §6 says where to look.

| selftest check (or symptom) | likely cause | fix |
|---|---|---|
| "the grey card meters within 0.5 stop of the prediction" (metric `meter_offset_stops` = d) | SceneColorHDR is pre-exposed or not in cd/m2 in 5.8 | set `METER_OFFSET_STOPS = d` in `unreal/fmbridge/ops/env.py` (one constant, applied in env.meter), `film-ue install`, re-run; nothing else depends on it |
| "the grey card reads as a mid grey (0.3..0.62)" (metric `grey_card_display`) | a scene capture does not take the world's unbound post volume (exposure), or the filmic curve maps grey elsewhere | if the value is steady but not 0.46: set `MID_GREY_DISPLAY` to it (env.py); if it is near 0 or 1: copy Env_Post's settings onto the capture (`_captures`: `cc.set_editor_property("post_process_settings", ...)`, `post_process_blend_weight` 1) |
| "one stop more exposure brightens the image", "env.check fails an underexposed card", "env.autoexpose converges" | the same: the final-colour capture ignores Env_Post | as the row above (post settings on the capture); then re-run |
| env.meter error "the scene/display capture read back no pixels" | editor without a real RHI (`-nullrhi`), or `read_render_target_raw` answered in another form | run the editor `-RenderOffscreen` (not -nullrhi); else print `type(px)` in `_captures` and unwrap it (it handles list, tuple, None) |
| "light.describe reads the candelas back" / "light.add converges" (`props` lists `intensity_units` every run) | `intensity_units` read back as another enum form | `_envutil.to_json` enum branch and `light._candelas` parse `LightUnits.CANDELAS`: print `U.to_json(c.get_editor_property("intensity_units"))` and match it |
| any "... converges" fails with `props: [light_color]` / `[volumetric_fog_albedo]` / `[ground_albedo]` | an FColor reads back 1 step off | the planner quantises with `photometry.quantize_fcolor`; widen `_envutil.same` for Color to 1/255 |
| "env.sun elevation is NOAA's" ok but "describe reads the sun's azimuth back" fails | the actor's yaw normalised to another range | `sun.from_rotation` takes yaw modulo 360: check `fm_north` tag on Env_Sun |
| "env.quality sets its cvars" | a cvar name missing in this build | `film-ue op editor.cvars names='["r.VolumetricFog.GridPixelSize"]'`; drop it from `envlib/quality.py` cvars() |
| "noir_bw has no colour cast" | colour wheels (FVector4) not applied | `_envutil.coerce` makes `unreal.Vector4` for `color_*` fields: check `env.describe` post `color_saturation` is `[1,1,1,0]` |
| "the day spec converges" / "a second plan is empty" fails | describe and plan disagree on one value | `film-ue op env.plan spec=@spec.json`: each step's `why` names the field ("differs in ['x']"); compare `env.describe` with `envlib.spec.desired(spec)` for it and fix the normaliser (envlib/spec.py norm_*) |
| "env.captures_rebuild ran" note / slow | the lighting build runs with static lighting on | harmless with Lumen; skip captures (they are a fallback) |
| "env.preset studio_grey converges" fails | sky light `captured` recapture timing | re-run; if it persists, add `yield 2` after `recapture_sky` in env.sky_light |
| stills look "lighting needs to be rebuilt" | a light from elsewhere is Stationary | the ops make theirs Movable; set others with `level.set` (`mobility`) |
| `env.hdri backdrop=true` warnings | HDRIBackdrop Blueprint variables named differently (unverified) | list them: `film-ue exec -c "import unreal; a=[x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors() if x.get_actor_label()=='Env_HDRI'][0]; result=sorted(p for p in dir(a) if not p.startswith('_'))"` and fix the names in env.hdri (env.py: `("cubemap", ...), ("intensity", ...), ("size", ...)`) |
| `env.quality project=true` says `restart_required` | expected: GI/VSM/HWRT are project settings | restart the editor (`film-ue --box linux editor restart`); HWRT also needs `r.RayTracing=True` (editor.project_setting) |

## 9. HANDOFF

State (2026-11-05 night, agent-08, branch `fleet/agent-08/ue-env`, all merged into `ue-helpers`): WP5 code, unit
tests (pure, fake ops, spec kinds through WP11's engine, legacy look.* golden), selftest, examples and this doc are
done; B16, B17 (light.rig), B50 (env.autoexpose), B56 (look.* as a layer), B57 fixes (project settings through
editor.project_setting, clouds material) done. Full ue suite green. NOTHING has run on a real engine yet.

Tomorrow on the GPU box, in order:
1. `film-ue selftest env` (~4 min). Use §8 for any failure. Read the two calibration numbers: `meter_offset_stops`
   (set `METER_OFFSET_STOPS` if |d| > 0.05) and `grey_card_display` (set `MID_GREY_DISPLAY` if it differs from 0.46).
2. Look at the stills (calibration_card, noir, golden_hour, night).
3. In the host studio: `film-ue apply examples/unreal/environment/studio-day-night.yaml`, then
   `film-ue op env.mood mood=night spec_name=studio`; `env.check camera=HostCam`. studio.py itself still uses
   look.* (now the same engine path); its volumetric fog will now really be on (B56): check the studio still.

Unproven (no engine tonight): SceneColorHDR units (calibration above); whether scene captures take the unbound post
volume; HDRIBackdrop Blueprint variables; `env.captures_rebuild` timing; FColor/enum read-back forms (§8 rows).

Not done (ideas, not started): light functions (`light_function_material`) and rect `source_texture` ops (APIs
verified); an IES import helper (WP2's assets.import makes the TextureLightProfile); studio.py moved onto an
environment spec.
