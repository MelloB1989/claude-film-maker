# DAY1-REPORT: the Unreal helpers on a real GPU box

Box: i-0f7a6ac044b75e922 (g6.4xlarge, 1x L4 24 GB, Ubuntu 22.04, ap-south-1b), UE 5.8.4 source build, project
HostStudio, from `main` 31c57577. Runs: `film-ue selftest` in the planned order (`film-ue selftest plan`), then the
demo (examples/unreal/demo). Fixes go to `fleet/agent-13/day1-<area>` off main, merged by agent-10.

Live table (newest result per area; times are wall clock on the box):

| # | area | result | time | failures | fix (branch / commit) | rerun | stills |
|---|---|---|---|---|---|---|---|
| 0 | first-run (agent-07) | OK except dx | ~19:20 | dx: view.still | (dx row) | platform 48/0 | |
| 1 | platform | OK 48/0 (first-run) | 60 s | | | | |
| 2 | dx | OK 32/0 (bridge + client) | 13 s | view.capture writes; dx_client delete refused | day1-view 72a80945; day1-dx f8195902 (GC before delete) | OK 32/0 | |
| 3 | assets | rerunning | | MP_CUSTOM_DATA0 hidden in 5.8 (mat skips it now); then 'could not create the scratch level' (an old level from batch 1) | day1-mat bb6d57c0; day1-dx da9fa76f | batch 5 | |
| 4 | layout | OK 36/0 | 11 s | (was: view.capture error) | day1-view | OK 36/0 | stills in report |
| 5 | mh | rerunning | | hair has no 'Melanin' param (item_params empty before assembly? agent-04's probe pending); scratch level as assets | agent-04; day1-dx da9fa76f | batch 5 | |
| 6 | anim | 18/4 + ERROR | 39 s | view.capture (fixed); head curves do not turn the head; face.alive; describe.face_curves | agent-01 | rerunning | |
| 7 | seq | 31/13 -> 42/2 | 20 s | section ranges collapsed to the whole sequence (SetStart/EndFrameBounded after set_range) | day1-seq f36288d1 | 42/2 | |
| 8 | cam | 25/14 + ERROR | 14 s | view.capture; projection markers / framing rows off | agent-11 | rerunning | |
| 9 | render | 20/1 + ERROR | 37 s | MoviePipelineEditorBlueprintLibrary not in unreal (module not loaded); AOV folders are FinalImage<material> in 5.8 | day1-render 8d74a7d4 (load_module on demand; check accepts 5.8 names); day1-seq | batch 5 | |
| 10 | qa | ERROR -> 26/6 | 27 s | view.capture (fixed); default capture gamma; per-cut stills (seq fix) | agent-09; day1-view, day1-seq | rerunning | |
| 11 | audio | OK 17/0 | 10 s | | | | |
| 12 | env | 38/6 + ERROR | ~60 s | SkyLightComponent has no lighting_channels (env.py:260); exposure 0-255 vs 0-1; autoexpose oscillates | agent-08 | rerunning | |
| 13 | foliage | OK 20/0 | 30 s | | | | |
| 14 | pose | ERROR 0/0 | 7 s | anim.py:1008 rig_keys: the engine made no control rig track | needs an owner (agent-01 has no task) | | |
| 15 | wp | OK 17/0 | 5 s | unreal.Box(min, max, is_valid) refused (FBox native make: 2 args) | day1-wp 8f9320ac | OK 17/0 | |
| D | demo | pending | | | | | |

## Log

- 19:28 batch 1 (assets..wp, kali reports/192856-assets): view.capture failed every still (EditInstanceOnly
  ShowOnlyActors/HiddenActors; then a stale cached render target); seqcore collapsed every section range; plus
  area-specific live API gaps (see rows). audio, foliage OK first time.
- 19:34 batch 2 (dx qa layout env, reports/193354-dx) with day1-view installed: layout OK, dx bridge OK, qa 26/6.
- 19:40 batch 3 (seq render cam qa anim env) with day1-seq installed: seq 42/2, render 20/1, cam 27/14 (projection
  ~3x too wide: the capture's FOV?), qa 30/2. editor.api_names (242 checked): missing EMetaHuman, MoviePipelineEditor-
  BlueprintLibrary, UsdStageImportOptions.
- 14:05 UTC editor restart for agent-07's FabScript (loaded). Batch 4 (assets mh wp pose dx anim render): wp OK, dx OK
  32/0; assets and mh could not create their scratch level (left by batch 1) -> day1-dx da9fa76f.
- 14:12 UTC batch 5 (assets mh render cam env anim qa seq) with every fix so far installed.
