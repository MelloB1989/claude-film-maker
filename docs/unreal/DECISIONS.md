# ue-helpers decisions

Newest at the bottom. Each entry gives the date, who decided, the decision and why. Agents add decisions they had
to make alone (no answer from the lead within 10 minutes), tagged with their WP.

- **2026-11-05 WP0 agent-10: integration base.** `ue-helpers` = `anime/rain-ferry` + `fleet/agent-06-2/reel`. reel
  already contains operator, his-outfit, overshirt, reel-perf and nearly all of reel-v2, and carries the fmbridge
  fixes: free before create, batched curve writes, cloth_inflate multi-tick, look GlowWipe, restore_leader. On top
  of it come reel-assembly, linux-workflow, linux-build, and the docs from linux-engine, linux-inventory and
  linux-cost. Film content (films/host-studio) came along with reel. It is scene code and stills under films/, not
  core, and splitting it out would have cost hours for no gain. Head: dfd4b7b.
- **WP0: ops auto-discovery.** `ops/__init__.py` imports every module and subpackage under `ops/` independently.
  12 WPs adding modules would otherwise all conflict on one import line. A broken module is reported (`ops.broken`,
  `list`'s `!broken`) instead of wedging the bridge, which was a README trap.
- **WP0: op metadata.** `@op(name, mutates=, idempotent=, tags=)`. The registry schema has one shape for the live
  `ops.schema` and the offline AST extraction (WP11, `tools/filmtools/unreal/schema.py`). There is no
  import-with-fake export: the AST route needs no engine and no fake.
- **WP0: errors.** `fmbridge/errors.py` `OpError(code, message, hint, candidates)`. The server keeps the traceback in
  `error` for compatibility and adds the structured fields. `ops.call` checks the arguments against the signature
  before running anything.
- **WP0: the embedded Python is 3.11.8** (UE 5.8.4 `Engine/Source/ThirdParty/Python3/Linux/include/patchlevel.h`).
  Everything under `unreal/` must parse as 3.11. `test_ue_runtime.py` enforces it. The client stays 3.12.
- **WP0: fake engine.** `tools/tests/fakeunreal/` is an in-memory editor with real value types (Rotator positional
  order roll, pitch, yaw; Color positional B, G, R, A, as in the engine) and recorded stubs for the rest. Areas
  extend it in `ext_<area>.py`. It records would-be modal dialogs in `ue.dialogs`.
- **WP0: WP6 is unowned.** agent-12 is stopped by the operator. level.py, layout and scene specs fall to the lead, or
  to the first WP that finishes, through BACKLOG.
- **WP0 (asked by WP9): specs.** WP11 owns the loader and the plan/apply engine. JSON and YAML are both accepted,
  and PyYAML becomes a direct client dependency. Schemas live in
  `tools/filmtools/unreal/schemas/<kind>.schema.json`, owned per kind.
- **WP0 (asked by WP9): stills.** WP9 provides `render.frames` (N frames at a preset through MRQ). WP10 builds
  `qa.*`/`view.*` stills and contact sheets on it. `look.still` and `seq.still` stay as the quick paths.
- **WP0 (asked by WP1): CLI hooks.** WP11 owns `cli.py`. Other WPs add subcommands through a
  `register(subparsers)` hook module (`cli_<area>.py`) that WP11 wires in, or through a `main(argv)` entry point.
- **WP12: one timing document.** Voice line timing is a `timing` document (`filmtools.unreal.audio_timing`): frames
  on the sequence's clock, words per line. `audio.lines` places it in Unreal, `performance_handoff` gives WP4 the
  `speech.to_face` args and the face's frame per line, and `film-post` mixes and captions from it, so picture, faces
  and mix agree by construction. It is kind `timing` (data, never applied); the applied spec kind is `audio`.
- **WP12: the mix is made in post, not rendered by MRQ.** Unreal's audio tracks are for timing; `film-post` builds
  and masters the mix (filmtools.mix) from the same timing. MRQ's wave output stays unused.
- **WP12: captions burn through libass** (ffmpeg `subtitles`) instead of the reel's Pillow overlays; titles are
  film-specific and stay in films/<id>/.
- **2026-11-05 WP0: PyYAML is a direct client dependency** (tools/pyproject.toml). uv.lock already resolves pyyaml (it is a transitive dependency), but the lock was not regenerated on the fleet (no uv there): the first `uv run` on a dev machine updates it. Commit that.
- **WP10: the QA arithmetic is pure Python in `unreal/fmbridge/qa/`** (stdlib, numpy when importable, no PIL), so
  one implementation runs in the editor (whose Python has no numpy unless PythonFoundationPackages pip-installed it)
  and on the client (`film-qa`, loaded standalone so `unreal` is never needed), and is unit-tested both ways.
- **WP10: viewport-free stills default to a SceneCapture2D** (one transient `FMQA_Capture` actor, removed after each
  op), not MRQ: ~1 s and no level save. `view.still mode=mrq` goes through WP9's `render.frames` (preset draft, PNG,
  a private folder per still) for a final look. The capture target is RGBA8_SRGB (day 1 on the box: closer to the
  viewport than RGBA8); the selftest measures both.
- **WP10/WP7 split (agreed with agent-11, confirmed by the lead):** WP7 owns the lens (`camkit.lens`) and the grammar
  between shots (180-degree line, 30-degree rule, DoF, safe areas); WP10 owns per-frame subject framing
  (`fmbridge.qa.framing.check`: size, headroom, joint/feet/limb cuts, look room) and the review that gathers both.
  `qa.framing.Camera` keeps its own projection (horizontal FOV kept, the engine's default); it agrees with camkit's
  when the output aspect is the filmback's.
- **WP10: garment penetration is measured in screen space** from two depth captures (skin alone, garments alone)
  per view: what a viewer would see, from a shot's camera or from views around the character. Skinned vertex
  positions are not reachable from Python, and bounds or physics capsules are too coarse for cloth.
- **WP10: issue codes are dotted `area.snake_case`** and every check returns `{"pass", "issues", "metrics"}`
  (CONVENTIONS §8).
- **WP7 agent-11: camkit is a pure package at `unreal/fmbridge/camkit/`** (approved by the lead), not `ops/_x.py`:
  the camera maths (lens, framing solver, moves, coverage, shot lists, cut checks, PNG sheets) imports nothing from
  `unreal`, so it is unit-tested without the fake and can be imported by client tools and by WP10's QA (one
  projection: `camkit.lens.project`).
- **WP7: default filmback "16:9 Digital Film" (23.76 x 13.365 mm)**, the engine's own default, so "a 50 mm" means
  what it means on a Super 35 cinema camera. `look.camera` (WP5) defaults to 16:9 DSLR (full frame): a 50 mm there
  is a 33 mm here (`camkit.lens.equivalent_focal`).
- **WP7: shot sizes are anchored between joints.** Each size puts the frame's top on the head (headroom per size)
  and the bottom edge between two landmarks (MCU: 30% of the way from chest to waist), never on a joint. Sizes are
  measured, not guessed: `framing.classify` names the nearest size of any frame.
- **WP7: left and right.** A subject's `side` is its own left/right (the camera on its left sees its left cheek). A
  scene's side of the line is left/right of the line from the first subject to the second, seen from above; in
  Unreal's left-handed frame `checks.side_of_line` is negative on the left. Shot lists and coverage choose each
  single's own side so every camera stays on the scene's side.
- **WP7: moves are baked keys**, not camera-shake assets or rig constraints: every `step` frames (default 2) the
  camera's transform (and focal/focus when they change) is computed in Python and keyed through WP8's ops, so a
  move is deterministic, checkable before it is written, and handheld noise is seeded. Rails and cranes (the engine's
  rigs) are there too (`cam.rig`, `cam.rig_move`) for a physical-looking dolly.
- **WP7: shot.apply converges by hash.** The spec's hash and camera list are stored as asset metadata on the
  sequence (`fm_shot_spec`, `fm_shot_cameras`); the same spec again changes nothing, a changed one rewrites the
  cameras' tracks and the cut track, and cameras it no longer uses are removed.

- **WP9: renders use MRQ's legacy preset configuration**, not Movie Render Graph: it is what rendered the reel on
  Windows and passed the Linux PoC (P3/P4/P6); the job sets `set_config_mode(PRESET)` explicitly.
- **WP9: video is always ffmpeg from image frames.** MRQ's ProRes/DNx outputs are Win64/Mac-only plugins and its MP4
  encoder has only a Windows backend (5.8.4 source), so in-engine video would differ per OS.
- **WP9: one MRQ job per camera cut by default, pre-rolled from the cut start** (MRQ camera-cut warm-up) when a chunk
  starts mid-shot: the cloth rule from docs/linux/engine.md P6, applied by the planner instead of by hand.
- **WP9: the path tracer is refused under 40 GB VRAM** unless `vram.force` (P5: 1080p with strand hair killed the
  editor on a 24 GB L4).
- **2026-11-05 WP0 (from WP11): the SDK's typed layer is not committed.** `tools/filmtools/unreal/sdk/_generated.py`
  is built in memory from the current ops at import, and git ignores it: it conflicted on every merge and can now
  never be stale. `ops_schema.json` stays committed. On a conflict, take either side and run `film-ue dx gen`.
- **WP0: fake engine extensions never replace a core method another area may also need.** They register instead:
  `fake.tag_providers` for asset registry tags, the bone table on `SkinnedMeshComponent`, and subclasses of core's
  classes. This came after three cross-area fake collisions tonight: bones, CineCameraComponent's FOV, material
  parameters and registry tags.
- **WP0: merge gate.** Every merge into ue-helpers goes through `dx gen`, then the whole ue suite (`test_ue_*`,
  `test_unreal_*`, `test_fmbridge_jobs`) with numpy, Pillow and soundfile installed, then `dx docs` as a warning.
  Nothing is pushed on red.
- **2026-11-05 WP5 agent-08: exposure is photographic EV100, and manual mode turns physical camera exposure off.**
  The manual scale is 2^(bias - EVcam) (PostProcessEyeAdaptation.cpp), and a cine camera writes its aperture into
  DepthOfFieldFstop (CineCameraComponent.cpp:709), so with physical exposure on, an aperture change would change
  brightness. `env.exposure mode=manual ev100=E` sets bias = 0.526 - E (a metered grey renders at 0.18). `physical`
  mode is still there for when a camera's settings should decide.
- **WP5: one planner, two front doors.** The environment/lighting planner is pure Python under
  `unreal/fmbridge/envlib/spec.py`. `env.apply` runs it in the editor, and `film-ue apply` runs it through
  `tools/filmtools/unreal/env_kind.py` (which loads envlib standalone), so the two never disagree.
- **WP5: ownership by tag.** Every env/light actor carries `fm_env` + `fm_owner:<spec name>`. Prune and replace only
  touch those. An existing same-label actor the ops did not make is a `conflict`. Rig records and the post-field list
  live in hex-encoded actor tags (FName-safe), so they travel with the level.
- **WP5: the sun is NOAA in pure Python**, not the SunPosition plugin (off by default, and its actor is a Blueprint).
- **WP5: B17 (light rigs) is covered by `light.rig`.** Agreed with agent-11 (WP7), who is not building one.
- **2026-11-05 WP4 agent-01: the eyes lead the head by default.** The brief said "head leads the eyes"; in people
  the eyes start a gaze shift (saccade) and the head follows 20-60 ms later while the eyes counter-rotate (VOR), and
  animators teach "eyes lead". Both are built: `character.lead: eyes` (default) or `head` (the head sets off first,
  a deliberate or heavy look). Decided alone (orchestrator offline).
- **WP4: performance synthesis is a pure package (`unreal/fmbridge/perfkit/`), not op code.** It has no `unreal`
  import, so it is unit-tested without the fake, runs on the client (`perf_kind` plans offline with it), and the ops
  stay thin. It lives beside `camkit`, outside `ops/` (auto-discovery would import it as ops).
- **WP4: one continuous face animation per performance.** perf.compose places every line's speech solve at its time
  in one face animation and lays the head, eyes, blinks and expressions over the whole timeline, instead of one face
  section per line: no head/eye jumps at line boundaries, and one fingerprint decides convergence.
- **WP4: nod kinds are `nod`, `beat`, `up`, `shake`.** YAML 1.1 reads a bare `yes`/`no` as a boolean; `yes`/`no`
  are still accepted from JSON/Python.
- **WP4: "robotic" is measured.** `anim.check` = perfkit.metrics: constant-velocity share of head motion (keyed
  straight lines score 0.9+, eased motion < 0.3), frozen-head share, >6 Hz jitter, blink rate/irregularity/shape,
  left-right asymmetry, upper-face range, gaze activity. Thresholds were tuned on synthetic robotic and natural
  curves in the tests; tune them on the first real renders.
- **2026-11-05 WP2 agent-02: materials split with WP5.** `mat.*` (ops/mat.py) owns the master materials, built by
  code into `/Game/FM/Lib` from graph specs (12 masters, presets, `mat.graph` for any material); WP5 keeps `look.*`
  as it is and may build on `from .mat import master`. Emissive is in nits (`Luminance_nits`, cd/m2) to pair with
  WP5's photometric practicals. Agreed with agent-08.
- **WP2: `EAL` falls back to the EditorAssetSubsystem.** EditorAssetLibrary lives in the EditorScriptingUtilities
  plugin, off by default; `ops/assets.py` exports `EAL = unreal.EditorAssetLibrary if present else the subsystem`
  (same calls). Modules that call `unreal.EditorAssetLibrary` directly are listed in assets.md HANDOFF.
- **WP2: material slots belong to the `material` kind.** Assets apply before materials (order 10 vs 12), so a
  material document names the mesh slots it goes on (`assign`); the `asset` kind has no material field.
- **WP2: Fab without a window.** Sign-in through the plugin's own saved credential (`fab.login` opens a Fab tab:
  the only trigger of its persist login); downloads from a signed URL are fetched and imported in Python (Megascans
  through the plugin's own InterchangeMegascansPipeline); Epic's AddToProject is reachable only through a small C++
  reflection plugin (`unreal/plugins/FabScript`), optional, needed for unreal-engine packs. A listing id -> signed
  URL needs Fab's web page: `fab_shim.py` (headless Chromium), experimental.
- **WP2: redirectors are fixed by resaving referencers** (AssetTools.FixupReferencers has no UFUNCTION).
- **Day 1: renders go through the in-editor PIE executor only** (agent-10, lead). On the 5.8.4 Linux box the MRQ
  editor library (`MoviePipelineEditorBlueprintLibrary`) never appears in Python, even after
  `load_module('MovieRenderPipelineEditor')`, and the new-process and command-line executors need it for the queue
  manifest. PIE rendered the demo's 168 frames and every render selftest check, so it is the route: `render.job`
  keeps refusing `executor: process|cmdline` with `unsupported` (and a hint to use pie) when the library is missing,
  and the render selftest notes that instead of failing it. Revisit if a film needs renders that survive an
  editor crash (the reason for a separate process): then build the module into the project, as FabScript is.
- **Day 1: the render selftest cancels once frames are landing** (it waited a fixed 40 ticks; on an L4 the draft
  job finished first, so the cancel came after the last frame and the job rightly said ok).
