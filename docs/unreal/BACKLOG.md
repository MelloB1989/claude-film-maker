# ue-helpers backlog

These items are beyond the work packages. When your WP is finished to a high standard, take the next unclaimed
item:

1. Claim it: `fleetctl tell agent-10 "claim B12"`. The lead marks the claim here.
2. Branch `fleet/<you>/ue-b12-<slug>` from `origin/ue-helpers`.
3. Push the branch and report it like a WP chunk.

Every item needs code, unit tests on the fake, a selftest where the engine is involved, and a doc section. "Area"
is the WP whose files the item mostly touches. Coordinate with that owner.

Status: `open`, `claimed <agent>`, `review`, `merged <sha>`.

| id | item | area | size | status |
|---|---|---|---|---|
| B01 | `ops/_util.py`: one home for vec/rot/colour parsing, actor-by-label with did-you-mean, asset free/ensure-folder, frame/second conversion. Migrate level/look/seq/anim to it without changing their signatures | WP0 | M | claimed agent-10 |
| B02 | `level.find`: actors by label glob, class, tag, within a radius/box, with transform + bounds; `level.describe` the whole level as JSON (counts by class, lights, cameras, sequences) | WP6 | M | merged (agent-10, ue-layout) |
| B03 | Layout primitives: `layout.place` (on floor via a downward trace, snap to grid, align to another actor's face), `layout.array` (row/grid/circle of an asset), `layout.scatter` (Poisson-disk with seed and exclusion zones) | WP6 | L | merged (agent-10, ue-layout) |
| B04 | `scene` spec kind: actors, assets, transforms, materials, lights, cameras in one YAML; plan/apply on top of level.* and look.*; round-trip `film-ue describe scene > scene.yaml` | WP6 | L | merged (agent-10, ue-layout) |
| B05 | Penetration and overlap check: `qa.overlaps` (actor pairs whose bounds or collision meshes intersect, depth in cm), `qa.floating` (actors not resting on anything) | WP10 | M | merged (agent-09) |
| B06 | `qa.framing`: for a camera at a frame, a target actor/bone's screen-space box, % of frame, headroom, lead room, rule-of-thirds distance, and whether it is clipped by the frame edge | WP10/WP7 | M | merged (agent-09) |
| B07 | `qa.exposure`: histogram, mean/median luma, clipped %, crushed %, per-region (face box) exposure from a still; verdict vs a target EV range | WP10 | S | merged (agent-09) |
| B08 | Contact sheet with labels: shots × frames grid with frame number, camera, shot name burnt in; client-side (PIL) from pulled stills | WP10 | S | merged (agent-09) |
| B09 | Still diff: two stills to a diff image + SSIM/PSNR/mean abs diff; used by selftests to prove "the change changed the picture" and regressions | WP10 | S | merged (agent-09) |
| B10 | Undo-safe "scratch" context: `with scratch("/Game/_Selftest/x")` creates a temporary level/folder, tears it down even on failure (no dialogs) | WP11 | S | open |
| B11 | `film-ue doctor`: checks the box end to end (bridge up, engine version, plugins enabled: MRQ, MetaHuman, Python Editor Script; GPU/RHI, disk, DDC, Epic login state) and prints fixes | WP1/WP11 | M | merged (agent-10) |
| B12 | Plugin/project settings op: `editor.plugins` (list/enable, needs restart flag), `editor.cvars` (get/set/snapshot/restore a set of cvars), `editor.project_setting` | WP1 | M | open |
| B13 | Asset dependency + reference report: `assets.refs` (who uses this), `assets.deps`; `assets.audit` unused/missing/broken (checkerboard) materials | WP2 | M | claimed agent-02 |
| B14 | Texture import rules: sRGB/compression by suffix and by content (normal-map detection), virtual textures off/on, max size; `assets.texture_set` imports a PBR set (BaseColor/Normal/ORM) and builds an MI | WP2 | M | claimed agent-02 |
| B15 | Material library: a small set of master materials (opaque PBR, masked foliage, glass, emissive screen, decal) created by code with documented parameters; `mat.instance` converges an MI from a dict of params | WP2/WP5 | L | claimed agent-02 |
| B16 | HDRI/sky environment presets: `env.preset` (studio, overcast, golden hour, night interior) building sky/sun/fog/post consistently; numbers in lux/EV documented | WP5 | M | open |
| B17 | Light rigs: `light.rig` three-point/key-fill-rim around a target actor at distances and angles relative to a camera, with lighting channels | WP5/WP7 | M | open |
| B18 | Camera from description: `cam.frame` "medium close-up of Host from 30° left at eye level" → placement, focal length, focus; inverse `cam.describe` in the same words | WP7 | L | claimed agent-11 |
| B19 | Camera moves: dolly/truck/crane/orbit/push-in as parametric keyframe generators (ease curves), written in one batched call | WP7/WP8 | M | claimed agent-11 (moves merged; batched write waits on WP8 seq.apply) |
| B20 | Shot list → sequence: a `shotlist` spec (shots with camera, duration_s, subject, action) building subsequences/camera cuts in one apply | WP8 | L | open |
| B21 | Timecode utilities: frames↔seconds↔SMPTE at any rate (23.976, 29.97 drop-frame), shared by client and bridge (pure module) | WP8 | S | open |
| B22 | Retime/conform: change a sequence's display rate or stretch a section, keeping keys and audio aligned | WP8 | M | open |
| B23 | Render farm split: `render.split` a job into N chunks across boxes with pre-roll, and `render.stitch` back with frame-exact checks (missing/duplicate frames) | WP9 | M | claimed agent-05 |
| B24 | Render QA: per-frame checks on a finished render (black frames, NaN/firefly detection on EXR, flicker = luma delta spikes, missing frames) | WP9/WP10 | M | claimed agent-05 |
| B25 | Audio: `audio.mix` stems into a sequence with levels in dB and fades in frames; loudness check (LUFS) client-side | WP12 | M | merged (agent-03) |
| B26 | Delivery presets: ProRes 422 HQ, H.264 web, 9:16 crop with safe-area check, burnt-in captions from SRT; ffmpeg argv generated from a spec | WP12 | M | merged (agent-03) |
| B27 | MetaHuman spec round-trip: `film-ue describe character Host > host.yaml` and apply it to a fresh preset to get the same character (body, skin, hair, wardrobe) | WP3 | L | open |
| B28 | Groom/hair tuning ops: density, width, melanin/redness, sky-lighting cvar guard (README trap) with numeric before/after | WP3/WP5 | S | claimed agent-09 |
| B29 | Face performance from text: `perf.speak` text → TTS file (client) → speech.to_face → seq.anim on the face, one call | WP4/WP12 | M | claimed agent-03 |
| B30 | Retargeting: `anim.retarget` a Mixamo/UE mannequin anim onto a MetaHuman body (IK retargeter assets made by code) | WP4 | L | open |
| B31 | Pose library: `anim.pose` apply a named pose (sit, lean, hands on hips) via control rig or baked anim; numeric check of end-effector positions | WP4 | L | open |
| B32 | Op call journal: every mutating op appends {op, args, result, ms} to Saved/fmbridge/journal.jsonl; `film-ue journal` shows it; replay a journal on a fresh level | WP1/WP11 | M | open |
| B33 | Bridge auth hardening + request size limits + `/op` batch endpoint (several ops in one request, one tick budget) | WP1 | S | open |
| B34 | SDK examples: 5 end-to-end scripts in `examples/unreal/` (empty level → lit set → character → camera → render 2 s) that run as tomorrow's demo | WP11 | M | open |
| B35 | `GUIDE.md` for Claude: the 20 most common tasks as copy-paste recipes, with the expected JSON output of each step | WP11 | M | open |
| B36 | Fab: list/import owned Fab assets by code (Fab plugin at Engine/Plugins/Fab), or document precisely why not headless and the narrowest UI fallback | WP2 | L | claimed agent-02 |
| B37 | World Partition / large level support: load/unload regions, data layers on/off by op | WP6 | M | open |
| B38 | Physics settle: drop props with physics sim for N ticks then bake transforms (realistic resting objects), multi-tick | WP6 | M | merged (agent-10) |
| B39 | Foliage/PCG: scatter foliage by code (InstancedFoliage / PCG graph with parameters), deterministic seed | WP5/WP6 | L | open |
| B40 | Static analysis gate: a test that every engine API name used under unreal/fmbridge appears in some doc's API_NOTES table (keeps the "verify APIs" rule honest) | WP0 | S | merged (agent-10) |
| B41 | Fake engine fidelity: a Sequencer fake (ext_seq) good enough to unit-test track/section/key writes and batching | WP8 | M | open |
| B42 | Cross-platform path helper: box paths (Windows/Linux) for project/Saved/renders used everywhere instead of string joins | WP1 | S | open |
| B43 | Visual baselines: qa.baseline save/compare/list (golden stills + metrics per selftest/check under Saved/fmbridge/baselines, client pull/push), selftest harness compares each t.still to its baseline (SSIM/diff in the report): the first GPU run sets them, later runs regress | WP10/WP11 | M | merged (agent-09; harness hook with agent-13) |
| B44 | Data layers: level.layers (list, visible, loaded), level.layer_add (create + put actors in), level.layer_set (visible/loaded in editor); partitioned worlds only, a clear `unsupported` otherwise | WP6 | M | merged (agent-10) |
