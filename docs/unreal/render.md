# render: Movie Render Queue by code (WP9)

Renders a level sequence to frames, sound and video with no UI. You give a **RENDER SPEC**, and `render.job` turns it
into one MRQ job per camera cut. Each job resumes from the frames already on disk and is pre-rolled from its shot
start, so cloth arrives where a full-shot render would have it. The job guards against unsaved maps, modal stalls and
running out of VRAM, and writes a JSON report (time per frame, VRAM, errors). `render.encode` turns the frames into
H.264/ProRes with the WAV laid under them. `film-ue render check` gives per-frame QA.

Code: `unreal/fmbridge/ops/render.py` (ops), `unreal/fmbridge/render_spec.py` (pure: schema, presets, planner,
ffmpeg/cmdline argv; the client imports it too), `tools/filmtools/unreal/render.py` (`film-ue render ...` and the
`render` spec kind), `tools/filmtools/unreal/schemas/render.schema.json`, `unreal/fmbridge/selftest/render.py`,
`examples/unreal/render/*.yaml`. Tests: `tools/tests/test_ue_render*.py` (fake MRQ: `fakeunreal/ext_render.py`).

## Recipes

**Render a sequence at final quality (resumable).**

```bash
cat > /tmp/r.yaml <<'EOF'
kind: render
version: 1
name: reel_final
sequence: /Game/Reel/SEQ_Reel
level: /Game/Studio/Studio
out_dir: /srv/ue/renders/reel_final
preset: final
EOF
film-ue render estimate /tmp/r.yaml          # chunks, pre-roll, minutes; nothing renders
film-ue render run /tmp/r.yaml               # progress on stderr; prints the report; exit 0 when status ok
film-ue apply /tmp/r.yaml                    # the same through the spec engine (plans nothing once done)
```

Check: the report's `status` is `ok`, `frames` is the number planned, and every chunk has `missing: []`. The report is
`<out_dir>/_render/<name>.report.json`, with `measured.s_per_frame` and `vram_peak_gb`. Run it again: it renders
nothing (`changed: false`).

**Resume after a crash or a cancel.** Run the same spec again. Complete frames are skipped, and a frame cut off by
the crash is rendered again: PNG must end in IEND, JPEG in FFD9. Each cut restarts at its first missing frame, and
the engine evaluates the frames before it from the cut start without rendering them.

**Only some shots, or a range.** Use `shots: [Reel_S15, Reel_S16]` (camera labels, or 0-based cut indices) or
`frames: [1196, 1220]` (end exclusive). A range that starts mid-shot is pre-rolled from that shot's start.

**A few frames for a still or a contact sheet.**
`film-ue op render.frames sequence=/Game/Reel/SEQ_Reel 'frames=[1200,1260]' out_dir=/srv/stills preset=draft`.
It returns `{"frames": {frame: path}, "cameras": {frame: label}}`. Use preset `draft` for PNG; `preview` writes JPG.
Pass `overwrite=true` when out_dir is shared with other stills. WP10's `view.still mode=mrq` uses it.

**Review video with sound.** Add `{kind: h264, crf: 18}` to `outputs`: the job encodes it on the box when every frame
is there. Or run `film-ue render video SPEC [--kind prores]`. To encode on your own machine after pulling the frames,
run `film-ue render video SPEC --local DIR --fps 24 [--audio mix.wav]`. For the delivery master (an edit, a mix,
captions, several aspect ratios), use WP12's `film-post`. `render.encode` is for one job's frames.

**EXR for grading, with AOVs.** Use `preset: final_exr` (16-bit half EXR, PIZ, depth and motion vectors), or add
`passes: [depth, motion_vectors, lighting_only, object_id]`. With more than one pass the frames go to
`<out_dir>/<pass>/NNNN.ext`; the beauty pass is in `FinalImage/`. `object_id` needs the MoviePipelineMaskRenderPass
plugin enabled in the project.

**Split a render over boxes.** `film-ue render estimate SPEC --boxes 2` balances the chunks by estimated time; each
chunk stays whole and pre-rolls itself. Run the spec on each box with that box's `shots`. Pull the frames and run
`film-ue render stitch SPEC --boxes 2 --local A --local B`. It lists missing frames per box, and duplicates (frames
found in two folders) for you to compare before you keep one.

**Render with no editor in the loop.** With `executor: cmdline`, the job writes an MRQ queue manifest per chunk and
runs `UnrealEditor <uproject> MoviePipelineEntryMap -game -MoviePipelineConfig=<manifest> -RenderOffscreen
-Unattended ...` itself. The child is in its own session, so it survives an editor restart. `film-ue render cmdline
SPEC` only writes the manifests and prints the argv, so you can run them elsewhere. Exit codes: 0 ok, 1 critical,
2 no sequence, 3 no config.

**QA a finished render.** Run `film-ue render check SPEC --local DIR` (frames pulled locally; ffmpeg for luma). It
returns a check (`pass`, `metric`, `why`) with `missing`, `corrupt` (truncated files), `black` (mean luma under 4/255)
`flicker` (a one-frame luma spike over 4x the median frame-to-frame change and over 2/255; a steady fade is not
flicker), and for EXR `nan_frames` (NaN/Inf pixels) and `firefly_frames` (a lone pixel over 1.0 and over 20x the
mean of its 8 neighbours), read as linear float through ffmpeg.

**Compare two renders (A/B).** Run `film-ue op render.compare a=DIR_A b=DIR_B ['frames=[s,e]'] sheet=/path/ab.png`.
It gives per-frame SSIM/PSNR (ffmpeg's ssim/psnr filters on the box; without ffmpeg, WP10's qa.compare at 480 px on
PNG), the worst frames, and a check at `min_ssim` (0.98). Use it for a pre-rolled chunk against the full shot
(`examples/unreal/render/preroll_ab.yaml`), for Linux against Windows reference frames, or for today against
yesterday. The sheet puts the worst frames side by side.

**How fast will it be?** Run `render.plan` (estimate) before and look at `report.measured` after. The next plan of
the same job uses the measured seconds per sample.

## Op reference (`film-ue ops render`)

| op | what | multi-tick |
|---|---|---|
| `render.presets` | the presets and what each is for | |
| `render.plan spec=` | resolved settings, chunks with pre-roll, frames skipped by resume, estimate, box split, VRAM guard | |
| `render.job spec= [stall_s=900]` | render a spec to the end, resuming; report; encodes video outputs | yes |
| `render.frames sequence= frames= out_dir= [preset level width height cvars overwrite]` | a few frames through their cuts | yes |
| `render.status` | job in progress / last: status, chunk, frames, elapsed, GPU now | |
| `render.cancel` | stop the job (MRQ or the child process); a re-run resumes | |
| `render.describe [out_dir name]` | rendering?, last report summary, frames on disk | |
| `render.gpu` | VRAM total/used/free, utilisation (nvidia-smi), editor RSS | |
| `render.manifest spec=` | per chunk: an MRQ queue manifest (.utxt) and its command line | |
| `render.encode spec= [start end outputs]` | ffmpeg H.264 / H.265 / ProRes from the frames + WAV chunks | yes |
| `render.compare a= b= [frames ext min_ssim worst every sheet method]` | per-frame SSIM/PSNR of two renders, worst frames, sheet | yes |
| `render.concat parts= out_file= [audio audio_offset_s]` | join videos without re-encoding, optional audio | yes |
| `render.mrq ...` / `render.progress out_dir=` | the older start-and-poll pair (films call them); `preroll_from=` added | |

Client: `film-ue render validate | estimate | run | cmdline | video | check | stitch | schema`. These names avoid the
op verbs, which are generated commands.

## The RENDER SPEC (kind `render`)

The schema is `tools/filmtools/unreal/schemas/render.schema.json` (`film-ue render schema`). Only `sequence` and
`out_dir` are required; the preset fills in the rest.

| field | default | meaning |
|---|---|---|
| `preset` | final | preview, draft, final, final_exr, 4k, pathtrace (below) |
| `level` | the open level | map to render; must exist on disk |
| `frames` / `shots` | all | [start, end) in sequence frames / camera labels or cut indices |
| `width`, `height` | preset | pixels |
| `spatial`, `temporal` | preset | samples (path tracer: spatial = samples per pixel); temporal = motion-blur sub-steps |
| `warmup_render`, `warmup_engine` | preset | frames rendered and discarded at a shot start (TSR history) / ticked without rendering when there is no pre-roll |
| `preroll` | cut | `cut`: a chunk after its cut's first frame is pre-rolled from it; `none`: start cold |
| `aa_method` | project's | none, fxaa, taa, msaa, tsr, smaa |
| `shutter_timing` | MRQ's (center) | center, open, close: where a frame's temporal samples sit. `open` keeps a camera cut on frame N out of the frame before it: with a centred shutter a shot's first frame blends the previous shot's camera (round 3, S11 f720 / S12 f780) |
| `path_tracer`, `quality` | preset | renderer; film-quality cvars (Lumen, VSM SMRT 16x16, hair MSAA 8, DOF/blur 4) |
| `cvars` | {} | extra cvars, on top of `t.MaxFPS 0` and `r.HairStrands.SkyLighting 0` (always) |
| `passes` | [beauty] | beauty, depth, motion_vectors, unlit, lighting_only, detail_lighting, reflections_only, object_id |
| `outputs` | preset | png (alpha), jpg, exr (compression, multilayer), bmp, wav, h264/h265 (crf), prores (profile 0-5), with audio true/path/false |
| `executor` | pie | pie (in the editor), process (child -game process), cmdline (manifest + process, no editor) |
| `save_dirty` | true | process/cmdline: save unsaved packages first, or refuse |
| `chunking` | shot | shot, none (one job), or N frames per job |
| `resume` / `overwrite` | true / false | skip complete frames / delete the range first |
| `file_name`, `zero_pad` | {frame_number}, 4 | MRQ format; `{render_pass}/{frame_number}` with several passes |
| `boxes` | 1 | plan the chunks over N boxes |
| `game_overrides` | absent | MRQ Game Overrides to set: cinematic_quality, texture_streaming (none/disabled/fully_load), lod_zero, disable_hlods, high_quality_shadows, shadow_distance_scale, view_distance_scale, flush_streaming; absent = MRQ's defaults as before |
| `vram` | 40 GB, 97 %, false | `path_tracer_min_gb`, `abort_pct` (cancel before the driver OOMs), `force` |

Presets:

| preset | size | samples | warm-up | cvars | outputs | for |
|---|---|---|---|---|---|---|
| preview | 960x540 | 1x1 | 8 | base | jpg | a look in seconds |
| draft | 1920x1080 | 1x4 | 16 | base | png | motion and timing |
| final | 1920x1080 | 1x8 | 32 | quality | png + wav | the reel's finals (0.73 s/frame on an L4) |
| final_exr | 1920x1080 | 1x8 | 32 | quality | exr + wav, depth, motion vectors | grading, compositing |
| 4k | 3840x2160 | 1x8 | 32 | quality | png + wav | UHD |
| pathtrace | 1920x1080 | 16x1 | 8 engine | base | exr | reference stills on a big GPU |

Example specs: `examples/unreal/render/` (reel_final, shot_preview, grade_exr, farm_4k).

## Gotchas

- **Chunks start at shot starts, or are pre-rolled.** Cloth started cold mid-shot hangs differently (S15 overshirt,
  docs/linux/engine.md P6). The planner sets MRQ's `bUseCameraCutForWarmUp` for any chunk after its cut's first
  frame, so the engine evaluates the sequence frame by frame from the cut start without rendering. Frame 0 of a
  shot can still differ (TSR/cloth history at the cut); judge it on its own.
- **The new-process executor saves first, or it stalls.** It prompts to save dirty packages before launching; with
  `-unattended` nobody answers and nothing renders, with no log line (P3). `render.job` saves first (`save_dirty`, the
  default) or refuses. For the PIE executor the map must exist on disk at least once: `level.save` first. The stall
  guard (`stall_s`, no new frame for 15 min) cancels any other silent hang.
- **The path tracer OOMs a 24 GB L4 with strand hair** (22.5 of 23 GB in ~25 s, then the editor dies, P5). Hair out
  of the ray-tracing BVH (`r.HairStrands.Raytracing 0`) fits but renders bald. The job refuses the path tracer under
  40 GB unless `vram.force`. Denoising runs on the CPU on Linux (~2.4 s per frame, warm-ups included). Render each
  camera cut as its own job: the temporal denoiser carries history across a cut.
- **VRAM abort.** The job samples nvidia-smi every ~2 s and cancels at `abort_pct` (97 %). It may not be fast enough
  for a sudden spike: it is a guard, not a guarantee.
- **ProRes/DNx MRQ outputs are Win64/Mac only** (plugin PlatformAllowList), and MRQ's MP4 encoder has only a Windows
  backend. Video is therefore always ffmpeg from the image frames, on every OS. Install ffmpeg on the render box
  (`apt-get install -y ffmpeg`), or encode locally with `--local`.
- **EXR is linear.** `render.encode` converts it with the sRGB curve (`-apply_trc iec61966_2_1`), so a video from
  EXR looks like one from PNG.
- **The WAV is per chunk**, at `_render/audio/<start>-<end>.wav`. Encode places the chunks on the timeline (gaps are
  silence). MRQ's WAV output is experimental and renders silence on a box with no audio device (5.8.4 fixed the
  crash).
- **`find_or_add_setting_by_class` matches subclasses** unless `exact_match`: the path-tracer pass *is a* deferred
  pass. The ops always pass `exact_match=True`.
- **PNG writes alpha by default in MRQ** (`bWriteAlpha = true` in the constructor). The spec's default is
  `alpha: false`.
- **Game Overrides are always on.** MRQ adds `MoviePipelineGameOverrideSetting` as a transient setting even when a job
  does not list it (`IgnoreTransientFilters`, MoviePipelineGameOverrideSetting.h:66; PrimaryConfig.cpp:33). Its
  defaults apply to every render: cinematic scalability, `p.ChaosCloth.UseTimeStepSmoothing 0` (cloth stays right
  with temporal samples), `p.Chaos.ImmPhys.MinStepTime 0`, `Slate.bAllowThrottling 0` and
  `wp.Runtime.BlockOnSlowStreaming 0` (MoviePipelineGameOverrideSetting.cpp:150-170). The reel's renders had them
  too, so we add nothing. To change one (say `texture_streaming: fully_load` for blurry far textures, or
  `lod_zero: false` to save memory on a big world), set `game_overrides` in the spec; only the keys you give change.
- **Frames are numbered by the sequence's display-rate frame** (`{frame_number}`, 4 digits), the same as the
  reel's `<master frame>.png`.
- **An idle offscreen editor holds the GPU at 97 %**; the bridge caps it (`t.MaxFPS`), and every render sets
  `t.MaxFPS 0` while it runs.

## API_NOTES

All verified on the UE 5.8.4 source box (`/srv/ue-src/UnrealEngine-5.8.4`). Paths are relative to
`Engine/Plugins/MovieScene/MovieRenderPipeline/Source/` unless they start with `Engine/`. The Python name is the
snake_case of the reflected name.

| API (Python) | source | notes |
|---|---|---|
| `unreal.load_module('MovieRenderPipelineEditor')` | Engine/Plugins/Experimental/PythonScriptPlugin/Source/PythonScriptPlugin/Private/PyCore.cpp:2071 | day 1: loads the module and generates its Python types when `MoviePipelineEditorBlueprintLibrary` is missing |
| `MoviePipelineEditorBlueprintLibrary.save_queue_to_manifest_file` | MovieRenderPipelineEditor/Public/MoviePipelineEditorBlueprintLibrary.h:41 | the new-process executor's queue manifest |
| `MoviePipelineQueueSubsystem.get_queue / render_queue_with_executor / is_rendering / get_active_executor` | MovieRenderPipelineEditor/Public/MoviePipelineQueueSubsystem.h:27,52,67,93 | editor subsystem; render_queue_with_executor returns the executor |
| `MoviePipelineQueue.allocate_new_job / delete_all_jobs` | MovieRenderPipelineCore/Public/MoviePipelineQueue.h:804,818 | |
| `MoviePipelineExecutorJob.sequence` (set_editor_property: PostEditChangeProperty calls the SetSequence BlueprintSetter, which Python cannot call; MoviePipelineQueue.cpp:185, PyGenUtil.cpp:1620), `map / job_name` (full object paths /Game/A/B.B, for the {sequence_name}/{level_name} tokens), `get_configuration`, `set_config_mode(MoviePipelineConfigMode.PRESET)` | MoviePipelineQueue.h:692,696,688,529,548 | 5.8 jobs have Preset/Graph/Basic modes; we use Preset (legacy settings) |
| `MoviePipelineConfigBase.find_or_add_setting_by_class(cls, include_disabled, exact_match)` | MoviePipelineConfigBase.h:145 | exact_match matters (subclasses) |
| `MoviePipelineOutputSetting.output_directory, file_name_format, output_resolution, override_existing_output, handle_frame_count, use_custom_playback_range, custom_start_frame, custom_end_frame, zero_pad_frame_numbers` | MovieRenderPipelineCore/Public/MoviePipelineOutputSetting.h:39-108 | custom range overrides the sequence's playback range (MoviePipeline.cpp:202) |
| `DirectoryPath(path)` (FDirectoryPath.Path) | Engine/Source/Runtime/CoreUObject/Public/UObject/SoftObjectPath.h:759 | USTRUCT(BlueprintType), Path BlueprintReadWrite: the type of output_directory |
| `IntPoint(x, y)` (FIntPoint.X/Y) | Engine/Source/Runtime/CoreUObject/Public/UObject/NoExportTypes.h:1009 | BlueprintType core struct: the type of output_resolution |
| `MoviePipelineAntiAliasingSetting.spatial_sample_count, temporal_sample_count, override_anti_aliasing, anti_aliasing_method, render_warm_up_count, use_camera_cut_for_warm_up, engine_warm_up_count` | MoviePipelineAntiAliasingSetting.h:49-101 | camera-cut warm-up = the cut's frames before the range, evaluated per frame (MoviePipelineBlueprintLibrary.cpp:745, MoviePipeline.cpp:1235) |
| `AntiAliasingMethod.AAM_NONE/FXAA/TEMPORAL_AA/MSAA/TSR/SMAA` | Engine/Source/Runtime/Engine/Public/SceneUtils.h:44 | |
| `MoviePipelineConsoleVariableSetting.add_or_update_console_variable(name, float)` | MovieRenderPipelineSettings/Public/MoviePipelineConsoleVariableSetting.h:103 | |
| `MoviePipelineDeferredPassBase.additional_post_process_materials` (`MoviePipelinePostProcessPass.enabled, material, high_precision_output, use_lossless_compression`) | MovieRenderPipelineRenderPasses/Public/MoviePipelineDeferredPasses.h:19,156 | constructor seeds WorldDepth + MotionVectors disabled (Private/MoviePipelineDeferredPasses.cpp:55-66) |
| `MoviePipelineDeferredPass_PathTracer / _Unlit / _LightingOnly / _DetailLighting / _ReflectionsOnly` | MoviePipelineDeferredPasses.h:327,236,281,258,304 | |
| `MoviePipelineObjectIdRenderPass` | Engine/Plugins/MovieScene/MoviePipelineMaskRenderPass/.../MoviePipelineObjectIdPass.h:12 | plugin must be enabled |
| `MoviePipelineImageSequenceOutput_PNG(write_alpha) / _JPG / _BMP` | MovieRenderPipelineRenderPasses/Public/MoviePipelineImageSequenceOutput.h:84,103,107,67 | PNG alpha defaults true |
| `MoviePipelineImageSequenceOutput_EXR.compression (EXRCompressionFormat), multilayer` | MovieRenderPipelineRenderPasses/Public/MoviePipelineEXROutput.h:231,237,53 | |
| `MoviePipelineWaveOutput.file_name_format_override` | MovieRenderPipelineRenderPasses/Public/MoviePipelineWaveOutput.h:35 | |
| `MoviePipelinePIEExecutor`, `MoviePipelineNewProcessExecutor` | MovieRenderPipelineEditor/Public/*.h | PIE uses job.map as GlobalMapOverride (Private/MoviePipelinePIEExecutor.cpp:206); unsaved map = silent finish offscreen (:119) |
| NewProcess save prompt | MovieRenderPipelineEditor/Private/MoviePipelineNewProcessExecutor.cpp:36-43 | `SaveDirtyPackages(bPromptUserToSave=true, ...)`: the stall |
| `MoviePipelineGameOverrideSetting.cinematic_quality_settings, texture_streaming (MoviePipelineTextureStreamingMethod NONE/DISABLED/FULLY_LOAD), use_lod_zero, disable_hlods (ScriptName), use_high_quality_shadows, shadow_distance_scale, override_view_distance_scale, view_distance_scale, flush_streaming_managers` | MovieRenderPipelineCore/Public/MoviePipelineGameOverrideSetting.h:14,87-143 | transient default on every job (:66 IgnoreTransientFilters) |
| `MoviePipelineInProcessExecutorSettings.additional_command_line_arguments` | MovieRenderPipelineCore/Public/MoviePipelineInProcessExecutorSettings.h:50 | -RenderOffscreen for the child on Linux |
| `MoviePipelineExecutorBase.cancel_all_jobs`, `on_executor_errored_delegate(executor, pipeline, is_fatal, error_text)` | MovieRenderPipelineCore/Public/MoviePipelineExecutor.h:176,313,25 | |
| `MoviePipelineEditorBlueprintLibrary.save_queue_to_manifest_file(queue) -> (queue, path)` (non-bool return + out: a tuple, PythonScriptPlugin PyGenUtil.cpp:1152-1180) | MovieRenderPipelineEditor/Public/MoviePipelineEditorBlueprintLibrary.h:41 | writes Saved/MovieRenderPipeline/QueueManifest.utxt; we copy it per chunk |
| Command line `-game -MoviePipelineConfig=<.utxt or asset>` | MovieRenderPipelineCore/Private/MovieRenderPipelineCommandLine.cpp:195-300 | relative paths are under Saved/; exit codes MovieRenderPipelineCoreModule.h:70 |
| `MovieSceneSequenceExtensions.get_display_rate / get_playback_start / get_playback_end / find_tracks_by_type` | Engine/Plugins/MovieScene/SequencerScripting/.../MovieSceneSequenceExtensions.h:98,174,192,59 | |
| `LevelSequenceEditorBlueprintLibrary.get_current_level_sequence / close_level_sequence` | Engine/Plugins/MovieScene/LevelSequenceEditor/.../LevelSequenceEditorBlueprintLibrary.h:42,72 | an open Sequencer is closed before a render |
| `EditorAssetLibrary.does_asset_exist` | Engine/Plugins/Editor/EditorScriptingUtilities/.../EditorAssetLibrary.h:70 | |
| `EditorLoadingAndSavingUtils.get_dirty_map_packages / get_dirty_content_packages / save_dirty_packages(maps, content)` | Engine/Source/Editor/UnrealEd/Public/FileHelpers.h:136,144,108 | no prompt |
| `Paths.engine_dir / get_project_file_path / convert_relative_path_to_full` | Engine/Source/Runtime/Engine/Classes/Kismet/BlueprintPathsLibrary.h:41,391 | |
| `Paths.project_content_dir` (render.job: a saved level's .umap on disk) | Engine/Source/Runtime/Engine/Classes/Kismet/BlueprintPathsLibrary.h (`ProjectContentDir`, beside `ProjectSavedDir` :173; line not re-checked: the source box was down on day 1) | |
| `PrimitiveComponent.set_simulate_physics`, `SceneComponent.set_mobility` (selftest) | Engine/Source/Runtime/Engine/Classes/Components/PrimitiveComponent.h:1661, SceneComponent.h:1296 | |
| ProRes / DNx / MP4 outputs: not used | Engine/Plugins/Media/AppleProResMedia/AppleProResMedia.uplugin:20 (Win64, Mac), AvidDNxMedia.uplugin:19 (Win64); MovieRenderPipelineMP4Encoder/Private has only Windows/ | hence ffmpeg |

## Selftest

`film-ue selftest render` (`unreal/fmbridge/selftest/render.py`) takes about 4-6 minutes on an L4 and needs a GPU.
It builds a floor, a falling physics cube, a light, two cameras and a 48-frame sequence with two cuts. It then proves
each of these:

- plan and job: 48 frames, a report, and a re-run that renders nothing;
- resume: six deleted frames come back as one chunk pre-rolled from the cut start, matching the full shot by PSNR
  (≥ 35 dB) and closer than a cold start (the falling cube is where the full render had it);
- `render.frames` returns the right camera per frame;
- the depth and motion-vector EXR folders;
- the new-process executor after a save;
- `render.manifest` plus a command-line render with no editor;
- the H.264 encode, when ffmpeg is installed;
- the path-tracer guard (refused under 40 GB, rendered above);
- cancel and resume.

Metrics: s/frame, measured seconds per sample, VRAM peak, and the job times. On the fake engine it runs end to end
in `tools/tests/test_ue_render_selftest.py`.

## Day-1 triage

When a `film-ue selftest render` check fails (or a real render misbehaves), find the row and apply the fix. Logs:
`film-ue log 400 | grep -E "LogMovieRenderPipeline|LogPython|Error"`. The job report is
`<out_dir>/_render/<name>.report.json`. Code pointers are in `unreal/fmbridge/ops/render.py` unless noted.

| failing check / symptom | likely cause | fix |
|---|---|---|
| `render.gpu sees the GPU` | no `nvidia-smi` on PATH for the editor process | harmless for rendering (the VRAM guard is skipped); `sudo apt-get install -y nvidia-utils-<driver>` or add it to the service's PATH |
| `job ok` false, chunk error "the render never started" | map not on disk, or a modal waiting | `film-ue op level.save`; check the log for `UnsavedMapFailureDialog`; for the process executor make sure `save_dirty` is true |
| `job ok` false, "MRQ refused to start the queue" / AttributeError on a setting | a Python name differs in 5.8 (`set_config_mode`, `EXRCompressionFormat`, `AntiAliasingMethod`) | `film-ue exec` with `print(dir(unreal.MoviePipelineAntiAliasingSetting))` etc.; correct the name in `_configure` / `_AA`; API_NOTES lists the source line |
| `job frames` < 48 with no error | `custom_end_frame` interpreted inclusively, or frames written under another name | `ls <out_dir>`; if names are not `NNNN.png`, check `file_name_format` and `zero_pad_frame_numbers` in `_configure`; `rs.frames_on_disk` must match the names |
| `re-run converges` false | frames failing `image_ok` (a format we do not recognise), so resume re-renders | `python -c` with `render_spec.image_ok` on a frame's head and tail; extend `image_ok` (render_spec.py) |
| `resume plans one pre-rolled chunk` wrong | camera-cut sections not where `seq.cuts` says | `film-ue op seq.cuts path=...`; the planner trusts it |
| `pre-rolled chunk matches the full-shot render` / `render.compare ... passes` false | MRQ camera-cut warm-up did not run (log: "no warmup range was detected") or physics/cloth is not deterministic across PIE sessions | log line present: the cut does not start before the chunk (check seq.cuts); no log line but PSNR low: compare `psnr_cold` too; if equal, the warm-up ran but sim differs: report `ab_min_ssim` and render chunks from shot starts (`preroll: none` + `chunking: shot`) as the fallback |
| `pre-roll is closer ... than a cold start` false, both PSNR high | the falling cube left the frame or landed before frame 30 (scene, not render) | ignore if both ≥ 35 dB; else move the cube (selftest `_build`) |
| `AOV folders` names differ | MRQ names post-process passes differently from the material name | `ls <out_dir>`; set the right folder names in `render_spec.PASSES` (second field) |
| `EXR frames per pass` 0 | EXR plugin module (`UEOpenExrRTTI`) missing in the build | check `MovieRenderPipeline.uplugin` modules load; fall back to `outputs: [{kind: png}]` for AOVs |
| `new-process executor renders` false, status `stalled` | the child did not start: save prompt (dirty packages) or no `-RenderOffscreen` | `film-ue log` for "Launching a new process"; `save_dirty: true`; check Project Settings > Movie Render Pipeline > Additional Command Line Arguments contains `-RenderOffscreen` (`_offscreen_child`) |
| `command-line render` false, exit code 1-3 | 1: crash/critical (see the chunk's `.log`); 2: sequence path; 3: manifest path | open `<out_dir>/_render/<chunk>.log`; for 3 check the `.utxt` exists and the path has no spaces; the argv is in the report (`chunks[].argv`): run it by hand over ssh |
| `command-line render` hangs | the child waits on a display / Vulkan device | check `-RenderOffscreen` and `-vulkan` are in the argv (`render_spec.cmdline`) and that the child inherits the editor's environment (no DISPLAY); never add `-nullrhi` (it renders nothing) |
| `H.264 of 48 frames` false | ffmpeg missing or no libx264 | `apt-get install -y ffmpeg`; or `film-ue render video SPEC --local DIR` on the client |
| `path tracer refused under 40 GB` false on an L4 | `nvidia-smi` missing, so the guard could not read VRAM | install nvidia-utils (row 1); never `vram.force` on the L4 (P5 killed the editor) |
| `cancel` / `cancelled job reports cancelled` false | `cancel_all_jobs` did not stop PIE quickly, or the job finished first | harmless if the job finished; else check the log for MRQ's cancel line |
| a real render: `vram_abort` | VRAM above 97 % | lower `width/height`/`temporal`, drop AOVs, restart the editor (RSS/VRAM growth), or a bigger GPU |
| a real render: `s_per_frame` ≫ 0.73 at final 1080p | shaders compiling during the job, cold DDC, or different cvars | render a 24-frame chunk twice (second run is the number); check `r.ScreenPercentage` and the quality cvars in the report's `spec.cvars` |
| a real render: WAV missing or silent | MRQ WAV is experimental; no audio device on Linux | ignore for picture; mix audio outside (WP12 film-post) |

## HANDOFF

State at 2026-11-05 ~01:30 UTC (agent-05, branch `fleet/agent-05/ue-render`, merged into `ue-helpers` by the lead):

- **Done:**
  - the spec, schema and presets;
  - the planner: chunks per cut, resume, cut pre-roll, a box split, and estimates calibrated by reports;
  - every op above, including `render.compare` (B51);
  - `game_overrides` (opt-in);
  - the client CLI and spec kind;
  - B23 (split, stitch) and B24 (frame QA: missing, corrupt, black, flicker, EXR NaN/Inf/fireflies);
  - the fake MRQ, 80+ unit tests, the selftest (~5 min, GPU), and this doc.

  Also mine: B37 World Partition (`docs/unreal/wp.md`). B57 audit fixes are in (sequence and map as full object
  paths; the sequence set by property write). A **Day-1 triage** table sits just above this section.
- **First hour on the GPU box (morning notes; the lead may quote them).** Each step: the command, then what a
  pass looks like.
  1. **Selftest.** `film-ue selftest render` (~5 min). Every check passes, except "path tracer refused under 40 GB",
     which on an L4 is the expected refusal: it passes when the code is `unsupported`. The report's metrics:
     - `s_per_frame_480p_draft`: a sanity number only.
     - `vram_peak_gb`: should stay far under 24 at 480p.
     - `ab_min_ssim`: ≥ 0.98, the pre-roll on the physics cube.
     - `psnr_preroll_vs_full_min` ≥ 35 dB and ≥ `psnr_cold_vs_full_min`: the pre-roll beats a cold start.
     - `process_job_s` and `cmdline_job_s`: they prove the two out-of-editor executors launch; expect a minute or
       two for the cmdline child's engine start.
  2. **Calibration against the PoC.** `film-ue render run` of one reel shot with `preset: final` (1080p, 8
     temporal, 32 warm-up, quality cvars, same as the PoC). Then `film-ue render status`. In the report:
     - `measured.s_per_frame` should be near **0.73 s** (P3: 0.72-0.75 on the L4). Over ~1 s means something
       differs from the PoC (shader compile, the DDC, cvars). Check `measured.sample_s_1080p` ≈ 0.09.
     - `vram_peak_gb` should be ~6-10 GB for one presenter (P4: 6.4-7.1; S15 with two presenters 10.3).
     - Every chunk has `status: ok` and `missing: []`, and the report's `errors` is empty.
     The next `render.plan` of the same job uses the measured cost for its estimate.
  3. **Cloth A/B (the real proof of the pre-roll).** `examples/unreal/render/preroll_ab.yaml` with
     `sequence: /Game/Reel/SEQ_Reel`, the full doc `shots: [Reel_S15]`, the chunk doc `frames: [1136, 1160]`. Then
     `render.compare a=<full> b=<chunk> 'frames=[1136,1160]' sheet=...`. Pass is `pass: true` (SSIM ≥ 0.98 on every
     frame). If it fails, open the sheet: the overshirt hanging open at her right shoulder is the P6 signature of a
     cold start, which means the camera-cut warm-up did not run. Look in the log for MRQ's "no warmup range was
     detected" warning, and check that the shot's camera cut section really starts at 1080.
  4. **VRAM guard.** `film-ue render plan` of a `preset: pathtrace` spec: `vram.ok` is false with the L4 message;
     `render.job` refuses with `unsupported`. Do not use `vram.force` on the L4: P5 crashed the editor twice.
  5. **If anything hangs.** `render.status` shows the chunk and its frame count. A chunk with no new frame for
     `stall_s` (15 min) is cancelled and marked `stalled`. `film-ue log` will show MRQ's lines
     (`LogMovieRenderPipeline`). Re-running the spec resumes.
- **Unproven until then (if a check fails, start from API_NOTES):**
  - the cmdline executor's child command line on Linux (`-vulkan`, `MoviePipelineEntryMap` with a queue manifest);
  - the AOV folder names MRQ writes (`{render_pass}` for a post-process material is assumed to be the material's
    name);
  - a sub-folder in the WAV's `file_name_format_override`;
  - the selftest's physics pre-roll PSNR ≥ 35 dB;
  - `MoviePipelineTextureStreamingMethod` member names (`NONE`/`DISABLED`/`FULLY_LOAD`).
- **Later:** a Movie Render Graph backend, only if a feature needs it (the legacy preset configuration is used on
  purpose: it is what was proven on Linux).
