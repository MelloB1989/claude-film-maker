# qa / view: Claude's eyes (WP10)

Claude cannot see the editor. These ops make pictures with no viewport (`view.*`) and turn pictures, cameras, bones
and bounds into numbers and **issues** (`qa.*`): what is wrong, where in the frame, and which op fixes it. One
`qa.review` gathers everything for a shot or a sequence into `review.json` (read it first) and `review.png` (one
picture to confirm it).

The arithmetic is pure Python in `unreal/fmbridge/qa/` (no `unreal`, no PIL, numpy when present). The same code runs
in the editor (the ops) and on the operator's side on pulled stills (`film-qa`, `tools/filmtools/unreal/qa_local.py`).

## Recipes

**See what a camera sees** (no viewport; ~0.1-1 s)
```bash
film-ue op view.still out=/srv/qa/a.png camera=CamA width_px=1280 height_px=720 'guides=["thirds","safe"]'
film-ue op view.still out=/srv/qa/b.png sequence=/Game/Seq/S010 frame=48     # the cut's camera, the shot's pose
film-ue op view.still out=/srv/qa/c.png 'loc=[300,300,200]' 'look_at=[0,0,100]' fov_deg=40   # an ad-hoc camera
film-ue pull /srv/qa/a.png a.png
```
Check: the result's `path`, `camera_info` (loc, rot, horizontal fov, aspect). `mode=mrq` renders the frame through
Movie Render Queue (WP9's `render.frames`, the final look, slower); `mode=viewport` is the old high-res screenshot.

**The whole cut on one sheet**
```bash
film-ue op view.stills sequence=/Game/Seq/S010 out_dir=/srv/qa/s010 per_shot=3
```
Check: `sheet.png`, each cell labelled "frame camera".

**Is the shot right? (one call)**
```bash
film-ue op qa.review sequence=/Game/Seq/S010 out_dir=/srv/qa/s010 per_shot=2 'subjects=["Ada"]' \
   'expect={"Ada":{"size":["MS","MCU"]},"image":{"stops":[-2,0]}}' 'ignore=["Floor","Walls"]'
film-ue pull /srv/qa/s010/review.png review.png
```
Check: `pass` (no `fail` issue), `summary` (one line per problem, worst first, each with its fix). Read
`review.json` → `issues[]`: `{code, severity, message, fix, frame, camera, subject, box, value, expected}`. Boxes are
frame fractions [x0, y0, x1, y1]; the same boxes are drawn on `review.png` in the severity colour.

**Frame a character**
```bash
film-ue op qa.framing 'subjects=["Ada"]' camera=CamA 'expect={"size":"MCU"}' still_out=/srv/qa/framing.png
```
Check: `metrics.subjects.Ada`: `size` (ECU/CU/MCU/MS/MLS/LS/ELS), `headroom` (crown's distance from the top, fraction
of frame height), `eyes` [u, v], `looks` and `look_room`; issues `framing.headroom_low|high`, `framing.joint_cut`
(an edge on a knee/ankle/wrist/elbow), `framing.feet_cut`, `framing.limb_cut`, `framing.look_room`, `framing.size`,
`framing.out_of_frame`. Characters are read from their bones (UE5 mannequin / MetaHuman names; eyes from the Face's
FACIAL_L/R_Eye, crown from the Face's bounds); anything else from its bounds. To place a camera for a size:
`fmbridge.qa.framing.suggest(cam, bones, "MCU")` (pure) or WP7's `cam.*`.

**Clothes: does skin show through?**
```bash
film-ue op qa.parts label=Ada                                   # component names
film-ue op qa.penetration label=Ada views=6 out_dir=/srv/qa/pen # or camera=CamA, or sequence=... frame=...
```
Check: `metrics.views.<view>.fraction` (share of the garment's pixels with skin in front), `worst_cm`; the stills
have the offending pixels painted magenta. Fix: `mh.cloth_inflate`, or `anim.bake_follow` when face and body drift.

**Is anything floating or sunk into something?**
```bash
film-ue op qa.floating 'ignore=["Pendant"]'
film-ue op qa.overlaps 'ignore=["Floor","Walls"]' 'ignore_pairs=[["Book","Shelf"]]'
```
Check: `metrics.gaps` (cm to what is under each actor; `fix` holds the exact `level.move`), `metrics.pairs`
[a, b, share of the smaller box, depth_cm to move apart].

**Exposure, colour, focus of a still**
```bash
film-ue op qa.exposure image=/srv/qa/a.png 'target_stops=[-2,-0.5]' 'regions={"face":[0.4,0.1,0.6,0.4]}'
film-ue op qa.image image=/srv/qa/a.png 'subjects={"Ada":[0.35,0.1,0.65,0.95]}' 'expect={"cast":"warm"}'
```
Check: `exposure.stops` (mean scene luminance in stops from 18% grey: 0 averages to mid grey, a dark mood is -1..-2),
`clipped_high_pct`, `clipped_low_pct`, `verdict` (ok/under/over/clipped/flat), `color.cast_toward`; per subject
`sharpness` (soft subject on a sharp frame = focus miss) and `stops`.

**Did my change change the picture? / regression against yesterday**
```bash
film-ue op qa.compare image=/srv/qa/new/00048.png reference=/srv/qa/ref/00048.png out_diff=/srv/qa/diff.png
film-ue op qa.review sequence=/Game/Seq/S010 out_dir=/srv/qa/new reference_dir=/srv/qa/ref
```
Check: `ssim` (1 identical; > 0.95 same picture; 0.8-0.95 same shot with changes; < 0.6 different), `psnr` dB,
`changed` (grid cells with their boxes), the heatmap.

**Regression against golden stills (baselines, B43)**
```bash
film-ue op qa.baseline_check suite=film/s010 name=00048 image=/srv/qa/s010/00048.png   # 1st run: created
film-ue op qa.baseline_check suite=film/s010 name=00048 image=/srv/qa/s010/00048.png   # later: match/differs
film-ue op qa.review sequence=/Game/Seq/S010 out_dir=/srv/qa/s010 baseline=film/s010   # every frame, one call
film-ue op qa.baseline_save suite=film/s010 name=00048 image=/srv/qa/new.png overwrite=true   # accept a change
film-ue op qa.baseline_list suite=film
uv run film-qa baseline pull baselines/ --suite film      # mirror to the operator's side (PNG + JSON)
uv run film-qa baseline check baselines/ film/s010 frames/*.png --diff-dir diffs/   # offline, by file stem
uv run film-qa baseline push baselines/                   # accepted locally -> the box
```
Check: `metrics.status` = created | match | differs (warn) | different (fail) | updated, `ssim`, `stops_shift`
(exposure drift is reported even when the structure matches), `diff` (heatmap). Baselines live on the box under
`<project>/Saved/fmbridge/baselines/<suite>/<name>.png|.json` (`$FMBRIDGE_BASELINES` overrides); a baseline's JSON may
carry its own `thresholds.min_ssim` for a noisy shot (`qa.baseline_save min_ssim=0.9`). The selftest harness checks
every `t.still` against `selftest/<area>/<name>` (mode auto: the first GPU run creates them).

**Hair: tune and measure it (B28: `groom.*`)**
```bash
film-ue op groom.describe label=Ada                       # components, per-group overrides, hair params, the cvar
film-ue op groom.measure label=Ada views=4 out_dir=/srv/qa/hair
film-ue op groom.set label=Ada component=Hair melanin=0.95 redness=0.1 width_cm=0.008 shadow_density=0.7 \
   measure_views=2 out_dir=/srv/qa/hair                   # before/after in numbers
film-ue op groom.sky_lighting enable=false measure_label=Ada   # the README's white-hair trap, as a number
```
Check: `groom.measure` gives, per view (front, back, sides from the face's direction), the hair's `share_of_head`
(hair pixels / head+hair silhouette: thinner or shorter hair shows more scalp; a density proxy), its colour in the
lit scene (`mean_rgb`, `stops`, `saturation`, `name`); `groom.set ... measure_views=N` returns `before`, `after` and
`delta`. Melanin up = darker (stops down); redness up = hue toward red/orange; width/shadow_density/length_scale move
`share_of_head`. `lost` in the result lists anything a Blueprint construction script reset. `strand_fraction` (real
strand count) edits the shared groom asset and rebuilds it: only with `edit_asset=true`. Pass `render_cvars` from
`groom.sky_lighting` to render ops so MRQ renders with the guard too.

**What changed in the level?**
```bash
film-ue op qa.snapshot out=/srv/qa/before.json
...                                                  # edits
film-ue op qa.diff before=/srv/qa/before.json        # or after=/srv/qa/after.json
```

**Turntable an asset or a character**
```bash
film-ue op view.turntable target=Ada out_dir=/srv/qa/ada views=8 isolate=true
```

**On the operator's machine, on pulled stills** (no editor)
```bash
uv run film-qa review frames/ --reference ref/      # exposure/continuity/reference per frame: review.json + .png
uv run film-qa sheet sheet.png frames/*.png --labels a,b,c --title S010
uv run film-qa compare new.png old.png --diff diff.png
uv run film-qa overlay a.png a_guides.png --guides thirds,safe,aspect:2.39 --box 0.4,0.1,0.6,0.9:Ada
uv run film-qa framing camera.json bones.json --expect-size MCU   # camera.json from view.camera
```
Every command prints JSON and exits 1 when a `fail` issue was found.

## Op reference

`film-ue ops view` / `film-ue ops qa` (or `film-ue describe qa`) give the full docstrings.

| op | what | multi-tick |
|---|---|---|
| `view.still` | PNG through a camera / a cut at a frame / an ad-hoc camera; mode capture, mrq, viewport | yes |
| `view.stills` | stills through a sequence's edit (per_shot per cut) + `sheet.png` | yes |
| `view.turntable` | N views around an actor (+ sheet), optionally isolated | yes |
| `view.sheet` | contact sheet of PNGs on the box (labels, status borders, title) | |
| `view.overlay` | guides (thirds, safe, center, golden, headroom, grid:NxM, aspect:R), boxes, points, caption | |
| `view.camera` | camera as numbers; world points / actor bounds projected into the frame | |
| `qa.image` | exposure, clipping, cast, flat frame, per-subject focus/brightness | |
| `qa.exposure` | histogram (32 bins), luma stats, clipping, stops, per region, vs a target range | |
| `qa.compare` | SSIM, PSNR, changed cells, colour shift, diff heatmap | |
| `qa.framing` | shot size, headroom, eyeline, joint/feet/limb cuts, look room, side | yes |
| `qa.parts` | an actor's primitive components (for penetration's body/garments) | |
| `qa.penetration` | skin through garments from depth captures (views around, or a camera) | yes |
| `qa.floating` | gap under each actor (line traces) | |
| `qa.overlaps` | interpenetrating bounds, share and depth | |
| `qa.snapshot` / `qa.diff` | the level as JSON; what changed | |
| `qa.review` | all of it for a sequence or a camera: review.json + review.png (`baseline=<suite>` too) | yes |
| `qa.baseline_save` / `_compare` / `_check` / `_list` / `_remove` | golden stills by suite/name; regress against them | |
| `groom.describe` | grooms on an actor: per-group instance overrides, hair material params, the sky cvar | |
| `groom.set` | per instance: width_cm, root/tip scale, shadow density, LOD bias, length; melanin, redness, roughness, white, light, dye, any param; strand_fraction (asset, opt-in); before/after | yes |
| `groom.measure` | hair coverage (share of the head silhouette) and colour per view | yes |
| `groom.sky_lighting` | the r.HairStrands.SkyLighting guard, with render_cvars and an optional before/after | yes |

Every `qa.*` returns `{"pass", "issues", "metrics"}` (CONVENTIONS §8). Issue codes (dotted, stable):
`image.flat`, `exposure.under|over|clipped_highlights|crushed_shadows|subject_dark`, `color.cast|cast_expected`,
`focus.subject_soft`, `compare.differs|region_changed|color_shift|no_reference`, `framing.*` (above),
`mesh.penetration|garments_not_seen|penetration_skipped|floating|unsupported|sunk|overlap`,
`continuity.added|removed|changed|exposure_jump|hue_jump|cast_jump|structure`, `review.image_unreadable`,
`baseline.missing|differs|different|region|exposure|shape`.

Pure modules (import `fmbridge.qa.<m>`; client: `filmtools.unreal.qa_local.qa()`): `image` (Image, PNG
read/write, resize, crop, colour), `draw` (5x7 font), `overlay`, `sheet`, `metrics`, `compare`, `framing` (Camera,
project, screen_box, check, suggest), `geometry`, `continuity`, `review`, `issues`.

## Spec kind: `qa`

`examples/unreal/qa/s010_review.yaml`; schema `tools/filmtools/unreal/schemas/qa.schema.json`; planner
`tools/filmtools/unreal/qa_kinds.py`. A qa spec lists checks (review, turntables, penetration, floating, overlaps,
snapshot); every step is `always` (checks change nothing, so they never "converge" away): `film-ue apply qa.yaml`
runs them all.

```yaml
kind: qa
version: 1
name: s010-review
out_dir: /srv/qa/s010
review: {sequence: /Game/Seq/S010, per_shot: 2, subjects: [Ada], expect: {Ada: {size: [MS, MCU]}}}
penetration: [{label: Ada, views: 6}]
floating: {ignore: [Pendant]}
```

## Gotchas

- **Scene capture is not the final render.** `view.still` mode capture is a SceneCapture2D with the camera's
  post-process settings and 8 warm-up captures (rendering state kept, so TAA and Lumen settle), but no motion blur,
  and DoF only as the post settings carry it. Use it for framing, layout, exposure trends and continuity; use
  `mode=mrq` (render.frames) for a frame you would judge as final.
- **Gamma.** The capture's render target is `RTF_RGBA8` by default: Final Color LDR is already display-encoded, and
  a non-float 8-bit target exports as PNG unchanged (TextureRenderTarget2D.cpp:704 gives 8-bit targets display gamma
  2.2). The selftest measures RGBA8 against RGBA8_SRGB and a viewport still (`capture_gamma` metric): if SRGB wins on
  the box, change `capture()`'s default in ops/view.py.
- **Depth needs 32-bit floats.** `read_render_target_raw` reads only RGBA8, RGBA16f and RGBA32f
  (KismetRenderingLibrary.cpp:337-351); fp16 depth steps ~0.3 cm at 3 m, as coarse as the penetration tolerance, so
  depth captures use `RTF_RGBA32F`. Pass `False` for normalize (raw values: depth in cm).
- **Empty depth pixels** read as huge values; anything >= 1e7 cm counts as "nothing here" (`EMPTY_DEPTH`). If the
  selftest's penetration fails with garment_pixels = everything, check what an empty pixel reads on the box.
- **Hits starting inside something** (`initial_overlap`) are skipped by `qa.floating`: an actor sunk into another
  reads from its other sample points, and `qa.overlaps` reports the overlap.
- **Line traces need collision** on what is underneath. A floor without collision makes everything "unsupported".
- **Bounds are axis-aligned.** `qa.overlaps` over-reports for rotated or hollow things (a shelf around its books):
  `ignore_pairs`, and confirm with a still.
- **Horizontal FOV is what the output keeps.** A cine camera's FOV is computed from its filmback width; when the
  output aspect differs from the filmback's, the frame height differs from the camera's (`view.camera` reports
  `aspect_mismatch`). Render at the filmback's aspect.
- **Penetration is view-based**: it finds what a camera would see. A poke-through on the back of a garment needs a view
  from behind (`views=6`), and a shot's camera + frame finds exactly what that shot shows.
- **MetaHuman component names** are Body, Face (skin) and Torso, Legs, Feet (clothes). Other characters: `qa.parts`,
  then pass `body=` / `garments=`, which may also name whole actors.
- **The capture rig** is one transient actor `FMQA_Capture`; every op removes it when it ends. If one is left after a
  crash, the next capture reuses and removes it.
- **Pure-Python speed in the editor**: without numpy, decoding a 1080p PNG takes a few seconds (the Paeth filter);
  the checks shrink to 480 px first. Prefer `width_px` <= 1280 for stills you will analyse, or run the analysis on
  the client (`film-qa`, numpy). If PythonFoundationPackages is enabled on the box, numpy is used automatically.
- **Heuristics, not verdicts**: `focus.subject_soft` also fires on plain untextured subjects (it is `info` unless the
  gap is large); cross-cut exposure/hue jumps are `info` under 1 stop / always for hue. State intent with `expect`.

## API_NOTES

Every engine API the WP10 ops use, checked on the UE 5.8.4 source box (`/srv/ue-src/UnrealEngine-5.8.4`). Python
names are the snake_case of the reflected names. Paths are relative to `Engine/Source/` unless they say otherwise.

| API (Python) | source | verified |
|---|---|---|
| `unreal.SceneCapture2D`, `.capture_component2d` (VisibleAnywhere, BlueprintReadOnly) | Runtime/Engine/Classes/Engine/SceneCapture2D.h:16, :22-23 | yes |
| `SceneCaptureComponent2D.fov_angle` | Runtime/Engine/Classes/Components/SceneCaptureComponent2D.h:43-44 | yes |
| `.texture_target` | SceneCaptureComponent2D.h:79-80 | yes |
| `.post_process_settings` (interp: editable), `.post_process_blend_weight` | SceneCaptureComponent2D.h:86-91 | yes |
| `.capture_scene()` (BlueprintCallable) | SceneCaptureComponent2D.h:298 | yes |
| `SceneCaptureComponent.capture_source` (interp), `.primitive_render_mode` | Runtime/Engine/Classes/Components/SceneCaptureComponent.h:77-81 | yes |
| `.capture_every_frame`, `.capture_on_movement` | SceneCaptureComponent.h:84-89 | yes |
| `.always_persist_rendering_state` | SceneCaptureComponent.h:131-132 | yes |
| `.hidden_actors`, `.show_only_actors` | SceneCaptureComponent.h:139-148 | yes |
| `.show_only_component`, `.show_only_actor_components`, `.clear_show_only_components` (BlueprintCallable) | SceneCaptureComponent.h:226-249 | yes |
| `unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR / SCS_SCENE_DEPTH / ...` | Runtime/Engine/Classes/Engine/EngineTypes.h:534-547 | yes |
| `unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST / PRM_RENDER_SCENE_PRIMITIVES` | SceneCaptureComponent.h:60-67 | yes |
| `unreal.RenderingLibrary` (UKismetRenderingLibrary, ScriptName) | Runtime/Engine/Classes/Kismet/KismetRenderingLibrary.h:32 | yes |
| `RenderingLibrary.create_render_target2d(world, w, h, format, clear, mips, uav)` | KismetRenderingLibrary.h:48 | yes |
| `RenderingLibrary.export_render_target(world, rt, dir, name)`: PNG for 8-bit, EXR/HDR for float | KismetRenderingLibrary.h:144; Private/KismetRenderingLibrary.cpp:263-279 | yes |
| `RenderingLibrary.read_render_target_raw(world, rt, normalize)`: RGBA8/16f/32f only; returns the list or None | KismetRenderingLibrary.h:192; KismetRenderingLibrary.cpp:300-360, 497-527 | yes |
| `RenderingLibrary.read_render_target_pixel(world, rt, x, y)` → FColor (sRGB 8-bit; float targets converted with sRGB; an unsupported format gives FColor::Red, alpha 255, so `_opaque` keeps the PNG) | KismetRenderingLibrary.h:151-152; Private/KismetRenderingLibrary.cpp:381-400 | yes |
| bool return + out params → Python returns the outs or None | Engine/Plugins/Experimental/PythonScriptPlugin/.../PyGenUtil.cpp:1161 | yes |
| `unreal.TextureRenderTargetFormat.RTF_RGBA8 / RTF_RGBA8_SRGB / RTF_RGBA16F / RTF_RGBA32F` | Runtime/Engine/Classes/Engine/TextureRenderTarget2D.h:23-43 | yes |
| `TextureRenderTarget2D.size_x / size_y` (BlueprintReadOnly) | TextureRenderTarget2D.h:107-113 | yes |
| 8-bit target display gamma (2.2) | Runtime/Engine/Private/TextureRenderTarget2D.cpp:704-720 | yes |
| `CineCameraActor.get_cine_camera_component()` | Runtime/CinematicCamera/Public/CineCameraActor.h:89-90 | yes |
| `CineCameraComponent.get_horizontal_field_of_view()` | Runtime/CinematicCamera/Public/CineCameraComponent.h:107-108 | yes |
| `CineCameraComponent.filmback`, `.current_focal_length` | CineCameraComponent.h:37-38, :65-66 | yes |
| `CameraActor.camera_component` | Runtime/Engine/Classes/Camera/CameraActor.h:29-30 | yes |
| `CameraComponent.field_of_view`, `.aspect_ratio`, `.post_process_settings` | Runtime/Engine/Classes/Camera/CameraComponent.h:43-44, :107-108, :352-353 | yes |
| `SceneComponent.get_world_location / get_world_rotation` (K2_ ScriptName) | Runtime/Engine/Classes/Components/SceneComponent.h:661-666 | yes |
| `SceneComponent.get_socket_location(name)` (bones are sockets) | SceneComponent.h:808-809 | yes |
| `SkinnedMeshComponent.get_bone_index / get_bone_name / get_num_bones` | Runtime/Engine/Classes/Components/SkinnedMeshComponent.h:1143-1165 | yes |
| `SkeletalMeshComponent.get_skeletal_mesh_asset()` | Runtime/Engine/Classes/Components/SkeletalMeshComponent.h:374-375 | yes |
| `MeshComponent.get_materials()` | Runtime/Engine/Classes/Components/MeshComponent.h:33-34 | yes |
| `SystemLibrary.get_component_bounds(c)` → (origin, extent, radius) | Runtime/Engine/Classes/Kismet/KismetSystemLibrary.h:1756-1757 | yes |
| `SystemLibrary.line_trace_single(world, start, end, TraceTypeQuery, complex, ignore, DrawDebugTrace, ignore_self)` → HitResult or None | KismetSystemLibrary.h:1269-1270 | yes |
| `unreal.TraceTypeQuery.TRACE_TYPE_QUERY1` (Visibility) | Runtime/Engine/Classes/Engine/EngineTypes.h:1274-1276 | yes |
| `unreal.DrawDebugTrace.NONE` | KismetSystemLibrary.h:30-34 | yes |
| `HitResult.to_tuple()` / `GameplayStatics.break_hit_result` order (blocking, initial_overlap, time, distance, ...) | Runtime/Engine/Classes/Kismet/GameplayStatics.h:1077-1078 (NativeBreakFunc) | yes |
| `Actor.get_actor_bounds(only_colliding)` → (origin, extent) | Runtime/Engine/Classes/GameFramework/Actor.h:1610-1611 | yes |
| `Actor.is_hidden_ed()` | Actor.h:2619-2620 | yes |
| `Actor.set_actor_location_and_rotation(loc, rot, sweep, teleport)` | Actor.h:1682-1683 | yes |
| `UnrealEditorSubsystem.get_editor_world()` | Editor/UnrealEd/Public/Subsystems/UnrealEditorSubsystem.h:49 | yes |
| `LightComponent.intensity / light_color / temperature`, `CineCameraComponent.current_aperture` (read in qa.snapshot; missing ones skipped) | read with get_editor_property, failures ignored | partly |
| `unreal.GroomComponent` (a MeshComponent), `.groom_asset` (BlueprintReadWrite), `.binding_asset` (BlueprintReadOnly) | Engine/Plugins/Runtime/HairStrands/Source/HairStrandsCore/Public/GroomComponent.h:29, :35-37, :50-52 | yes |
| `GroomComponent.groom_groups_desc` (BlueprintReadWrite, TArray<FHairGroupDesc>) | GroomComponent.h:271-273 | yes |
| `HairGroupDesc.hair_width / _override, hair_root_scale, hair_tip_scale, hair_shadow_density, lod_bias, hair_length_scale` (+ `_override` flags) | HairStrandsCore/Public/GroomDesc.h:18-82 | yes |
| `GroomAsset.hair_groups_interpolation` (BlueprintGetter/Setter) → `.decimation_settings.curve_decimation` (EditAnywhere) | HairStrandsCore/Public/GroomAsset.h:517-518, :629-630; GroomAssetInterpolation.h:76-78, :205-206 | yes |
| MetaHuman hair material params `hairMelanin, hairRedness, HairRoughness, WhiteAmount, LightAmount, HairDye` | Engine/Plugins/MetaHuman/MetaHumanCharacter/Source/MetaHumanDefaultPipeline/Public/Item/MetaHumanDefaultGroomPipeline.h:26-44 (MaterialParamName) | yes |
| `PrimitiveComponent.create_dynamic_material_instance(index, source, name)` | Runtime/Engine/Classes/Components/PrimitiveComponent.h:1628-1629 | yes |
| `MaterialInstanceDynamic.set_scalar_parameter_value / get_scalar_parameter_value (K2_ ScriptName) / set_vector_parameter_value` | Runtime/Engine/Public/Materials/MaterialInstanceDynamic.h:23-24, :56-57, :108-109 | yes |
| `unreal.MaterialInstanceConstant` (UCLASS BlueprintType; groom `_get_scalar` reads a constant instance through MaterialEditingLibrary) | Runtime/Engine/Public/Materials/MaterialInstanceConstant.h:19-20 | yes |
| `MaterialEditingLibrary.get_scalar_parameter_names / get_vector_parameter_names / get_material_instance_scalar_parameter_value` | Editor/MaterialEditor/Public/MaterialEditingLibrary.h:501-506, :416-417 | yes |
| `r.HairStrands.SkyLighting` (cvar), `SystemLibrary.get_console_variable_int_value` | Runtime/Renderer/Private/HairStrands/HairStrandsEnvironment.cpp:38; KismetSystemLibrary.h:630-631 | yes |
| `Actor.get_actor_forward_vector` | Runtime/Engine/Classes/GameFramework/Actor.h (K2 BlueprintCallable; used by every area) | yes (in use) |
| `EditorActorSubsystem.get_all_level_actors / spawn_actor_from_class / destroy_actor`, `SystemLibrary.get_engine_version`, `EditorAssetLibrary.*` | used by every area; proven on the box (unreal/README.md) | yes (in use) |

## Selftest

`unreal/fmbridge/selftest/qa.py` (`film-ue selftest qa`): ~2 min on the L4, needs a GPU, no assets beyond
/Engine/BasicShapes. It builds a floor, a pillar, resting/floating/sunk cubes, a sun and sky, two cameras, a
sphere-in-a-cube penetration rig and a two-cut sequence, then proves every `view.*` and `qa.*` op (list in its
docstring), including that the capture's projection agrees with the picture and which capture format matches the
viewport's gamma. With a MetaHuman under /Game/MetaHumans it also checks its garments and framing. Stills and
reports land in the selftest's report folder (`qa/`). It was dry-run end to end on the fake engine (all checks pass
there except what only an engine can tell).

## HANDOFF

Where WP10 stopped (2026-11-05 night, agent-09):

- Done: the pure core (`unreal/fmbridge/qa/`, 60+ unit tests incl. numpy-vs-pure agreement), all `view.*`/`qa.*` ops
  with fake-engine tests (`tools/tests/fakeunreal/ext_qa.py` renders bounds boxes + depth layers), the selftest, the
  `qa` spec kind, `film-qa` on the client, this doc.
- Unproven until the GPU box: everything that touches the renderer: capture gamma (the selftest decides), empty-depth
  value (EMPTY_DEPTH), Lumen warm-up count (8) is enough, `capture_source` set through set_editor_property on an
  `interp` property, show-only lists with skeletal meshes (MetaHuman parts), `read_render_target_raw` speed at
  256-384 px (expected ~0.1 s), `HitResult.to_tuple()` field order.
- B43 baselines (fleet/agent-09/ue-b43-baselines): store/compare/check in `fmbridge/qa/baseline.py`, `qa.baseline_*`
  ops, `qa.review baseline=`, `film-qa baseline pull|push|check|list`. The harness hook (T.still -> baseline check,
  `film-ue selftest --baseline auto|compare|update|off`) is agent-13's file: the patch was sent to them. The match
  threshold (SSIM 0.95 at 480 px) is a guess until two GPU runs of the same scene are compared: tune MIN_SSIM then.
- B28 grooms (fleet/agent-09/ue-b28-groom): `ops/groom.py` + `fakeunreal/ext_groom.py` + `test_ue_groom.py`. Unproven
  until a GPU box with a built MetaHuman: that GroomGroupsDesc writes survive the MetaHuman Blueprint's construction
  script (the op reads back and reports `lost`), and that the hair MIC's params are named as the pipeline header says
  on a built character (groom.describe's `scalar_names` shows them). agent-04's mh.groom sets the same look at BUILD
  time (character asset); groom.* is per instance, per shot.
- Not done / ideas: occlusion of a subject by another actor in frame (a line trace camera→bone; WP7 started one in
  camkit), checker-texture (failed material) detection in stills, per-frame penetration across a whole shot
  (`qa.review checks=["penetration"]` does it per sampled frame; a dense scan would be a separate op), WP7's
  cut-grammar checks (`cam.*`) are not called from `qa.review` yet: add them to the review's per-cut loop once
  `cam.check` is stable (agent-11 calls `qa.framing.check` from its side).
