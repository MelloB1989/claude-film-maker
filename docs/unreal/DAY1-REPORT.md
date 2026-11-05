# DAY1-REPORT: the Unreal helpers on a real GPU box

Box: i-0f7a6ac044b75e922 (g6.4xlarge, 1x L4 24 GB, Ubuntu 22.04, ap-south-1b), UE 5.8.4 source build, project
HostStudio, from `main` 31c57577. Runs: `film-ue selftest` in the planned order (`film-ue selftest plan`), then the
demo (examples/unreal/demo). Fixes go to `fleet/agent-13/day1-<area>` off main, merged by agent-10.

Live table (newest result per area; times are wall clock on the box):

| # | area | result | time | failures | fix (branch / commit) | rerun | stills |
|---|---|---|---|---|---|---|---|
| 0 | first-run (agent-07) | pending | | | | | |
| 1 | platform | pending | | | | | |
| 2 | dx | pending | | | | | |
| 3 | assets | pending | | | | | |
| 4 | layout | pending | | | | | |
| 5 | mh | pending | | | | | |
| 6 | anim | pending | | | | | |
| 7 | seq | pending | | | | | |
| 8 | cam | pending | | | | | |
| 9 | render | pending | | | | | |
| 10 | qa | pending | | | | | |
| 11 | audio | pending | | | | | |
| 12 | env | pending | | | | | |
| 13 | foliage | pending | | | | | |
| 14 | pose | pending | | | | | |
| 15 | wp | pending | | | | | |
| D | demo | pending | | | | | |

## Log

(each run: when, what, the report folder, what was learned)

## Merged (agent-10)

Every day-1 fix goes through the gate (dx gen, the ue suite, dx docs) onto `fleet/agent-10/day1`, which main
fast-forwards to.

| when | what | from | gate |
|---|---|---|---|
| before the run | Blender tests start Blender only when `BLENDER` is set | agent-10 06f89092 | 1021 passed |
| before the run | this report | agent-13 day1-report 84211934 | |
| first-run | `editor.wait_compile` uses `AutomationLibrary` (the ScriptName); the file inbox writes the /exec result shape | agent-07 f580b805 | 1021 passed |
| first-run | `editor.api_names`: every `unreal.<Name>` the bridge uses, checked against the live module | agent-10 184437aa | 1025 passed |
| first-run | `transport.get` in parts (SSM output cap) | agent-07 6a6bc809 | 1027 passed |
| dx | `view.capture`: show-only/hidden lists through the component's calls (EditInstanceOnly properties) | agent-13 f9bbd4fd | 1027 passed |
| batch 1-3 | agent-13: `view` render-target cache per world (72a80945), `seq` bounded section ranges set before the range (f36288d1), `dx` scratch cleanup after GC (f8195902) | agent-13 | 1027 passed |
| batch 1-3 | `wp._box`: `unreal.Box(min, max)` (`is_valid=` is refused live); the fake's Box now refuses it too | agent-10 d06c4b69 + agent-13 8f9320ac | 1027 passed |
| platform | Vulkan SM6 target in setup/first-run; `film-ue plugin-build` (FabScript built on the box in ~20 s); project sync keeps plugin binaries | agent-07 260a1de2, e1a8d90c | 1034 passed |
| mat | MP_CUSTOM_DATA0/1 (hidden from Python in 5.8) skipped and reported | agent-13 bb6d57c0 | 1034 passed |
| api_names | box run: 3 missing of 242. USD import now says the USDImporter plugin is off; `EMetaHuman` was a docstring hit (the scan reads code only now); `MoviePipelineEditorBlueprintLibrary` is agent-13's render fix | agent-10 befdc58d | 1034 passed |
| batch 5 | dx: scratch level left by an earlier run (da9fa76f); render: MRQ editor module on demand, 5.8 AOV folders, JPEG frames are `.jpeg` (48f97794) | agent-13 | 1034 passed |
| demo | manual exposure (`AEM_MANUAL`), outputs and voice under /srv/ue/demo | agent-13 bd2c487a | 1035 passed |
| env | display capture RTF_RGBA8_SRGB (/255), sky light without channels: env 38/6 -> 56/0 on the box | agent-08 68bbed7c | 1035 passed |
| seq | the fake resets a bounded section's range like the engine; a seq selftest check | agent-06 d94b05af | 1035 passed |
| cam | convergence on the engine (float32 focus, rotations by axes), stills at the filmback aspect, shot.plan lists missing cameras, coverage names | agent-11 c83bf93e | 1035 passed |
