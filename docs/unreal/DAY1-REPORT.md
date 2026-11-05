# DAY1-REPORT: the Unreal helpers on a real GPU box

Box: i-0f7a6ac044b75e922 (g6.4xlarge, 1x L4 24 GB, Ubuntu 22.04, ap-south-1b), UE 5.8.4 source build, project
HostStudio, from `main` 31c57577. Runs: `film-ue selftest` in the planned order (`film-ue selftest plan`), then the
demo (examples/unreal/demo). Fixes go to `fleet/agent-13/day1-<area>` off main, merged by agent-10.

Live table (newest result per area; times are wall clock on the box):

| # | area | result | time | failures | fix (branch / commit) | rerun | stills |
|---|---|---|---|---|---|---|---|
| 0 | first-run (agent-07) | OK except dx | ~19:20 | dx: view.still | (dx row) | platform 48/0 | |
| 1 | platform | OK 48/0 (first-run) | 60 s | | | | |
| 2 | dx | bridge 20/0 OK; client cleanup refused | 10 s | view.capture EditInstanceOnly writes; dx_client delete refused (level still referenced) | day1-view 72a80945; day1-dx f8195902 (GC before delete) | bridge OK after day1-view; client pending day1-dx | |
| 3 | assets | ERROR after 15/0 | 4 s | mat.py:36 MaterialProperty has no MP_CUSTOM_DATA0 | agent-02 | | |
| 4 | layout | OK 36/0 | 11 s | (was: view.capture error) | day1-view | OK 36/0 | stills in report |
| 5 | mh | ERROR after 25/0 | 58 s | wardrobe.py:261 hair has no 'Melanin' param (item_params empty live) | agent-04 | | |
| 6 | anim | 18/4 + ERROR | 39 s | view.capture (fixed); head curves do not turn the head; face.alive; describe.face_curves | agent-01 | rerunning | |
| 7 | seq | 31/13 -> 42/2 | 20 s | section ranges collapsed to the whole sequence (SetStart/EndFrameBounded after set_range) | day1-seq f36288d1 | 42/2 | |
| 8 | cam | 25/14 + ERROR | 14 s | view.capture; projection markers / framing rows off | agent-11 | rerunning | |
| 9 | render | 12/9 + ERROR -> 20/1 + ERROR | 37 s | MoviePipelineEditorBlueprintLibrary missing (render.py:363); AOV folder names; cuts (seq fix) | agent-05; day1-seq | 20/1 | |
| 10 | qa | ERROR -> 26/6 | 27 s | view.capture (fixed); default capture gamma; per-cut stills (seq fix) | agent-09; day1-view, day1-seq | rerunning | |
| 11 | audio | OK 17/0 | 10 s | | | | |
| 12 | env | 38/6 + ERROR | ~60 s | SkyLightComponent has no lighting_channels (env.py:260); exposure 0-255 vs 0-1; autoexpose oscillates | agent-08 | rerunning | |
| 13 | foliage | OK 20/0 | 30 s | | | | |
| 14 | pose | ERROR 0/0 | 6 s | anim.py:1008 rig_keys: the engine made no control rig track | agent-01/pose owner | | |
| 15 | wp | ERROR after 9/0 | 6 s | wp.py:32 unreal.Box(min=, max=, is_valid=) not accepted | agent-10 | | |
| D | demo | pending | | | | | |

## Log

- 19:28 batch 1 (assets..wp, kali reports/192856-assets): view.capture failed every still (EditInstanceOnly
  ShowOnlyActors/HiddenActors; then a stale cached render target); seqcore collapsed every section range; plus
  area-specific live API gaps (see rows). audio, foliage OK first time.
- 19:34 batch 2 (dx qa layout env, reports/193354-dx) with day1-view installed: layout OK, dx bridge OK, qa 26/6.
- 19:40 batch 3 (seq render cam qa anim env) with day1-seq installed: seq 42/2, render 20/1, ...
