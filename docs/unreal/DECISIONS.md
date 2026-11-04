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

- **WP9: renders use MRQ's legacy preset configuration**, not Movie Render Graph: it is what rendered the reel on
  Windows and passed the Linux PoC (P3/P4/P6); the job sets `set_config_mode(PRESET)` explicitly.
- **WP9: video is always ffmpeg from image frames.** MRQ's ProRes/DNx outputs are Win64/Mac-only plugins and its MP4
  encoder has only a Windows backend (5.8.4 source), so in-engine video would differ per OS.
- **WP9: one MRQ job per camera cut by default, pre-rolled from the cut start** (MRQ camera-cut warm-up) when a chunk
  starts mid-shot: the cloth rule from docs/linux/engine.md P6, applied by the planner instead of by hand.
- **WP9: the path tracer is refused under 40 GB VRAM** unless `vram.force` (P5: 1080p with strand hair killed the
  editor on a 24 GB L4).
