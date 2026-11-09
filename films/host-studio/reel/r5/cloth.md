# Round 5: cloth (T3b, agent-08): his tee and her overshirt as real Chaos cloth

**NOT RUN YET.** This is the plan for the orchestrator's single GPU session.
- Core: `fleet/agent-08/r5-cloth` (ops `cloth.*`, `qa.cloth`, the FMCloth plugin). Docs:
  `docs/unreal/cloth.md`, `docs/unreal/research/cloth-physics.md`.
- Film: this branch (`fleet/agent-08/r5-film-cloth`): this plan and `cloth_gate.py`.

**The operator's complaint:** "his chest still looks like he wore some heavy armor inside".

**Cause (measured in round 4's notes, confirmed in the source; research doc §1):**
- His tee had no clothing data, so it was skinned and moved rigidly.
- A World Position Offset inflate made it a smooth, thick shell.
- No check measured cloth motion.

**The fix:**
- agent-02 refits the tee with real ease and removes the inflate (`reel/r5/garment.md`, branch
  `fleet/agent-02/r5-film-garment`).
- Then this plan makes it cloth (`cotton_tee`) and makes her overshirt cloth (`overshirt_light`).
- Then it proves both alive and sound, with the gate's numbers.

## Order in the GPU session

- **Prerequisites:**
  - The core branches are merged into the box tree.
  - `film-ue install` has been run.
  - agent-02's garment plan has run through its step 3: the refit tee is dressed as component `Tee` on Host, with
    no ClothOp material chain, and `mh.leader_check` passes.
- Paths on the box:
  - `T` = the box tree;
  - `C=/srv/ue/reel/r5/cloth`;
  - `G=/srv/ue/reel/r5/garment` (agent-02's).
- Sequence: `/Game/Reel/SEQ_Reel`.
- Shots:

| shot | frames | presenters |
|---|---|---|
| S13 | 960-1080 | him |
| S15 | 1080-1200 | both |
| S16 | 1200-1320 | her |
| S17 | 1320-1440 | both |
| S18 | 1440-1560 | both |

Steps 0-3 are probes: stop and report if one fails its expected result. Steps 4-7 are the round-5 work.

### P-C0. What simulates today (read-only, 10 s)
```bash
film-ue op cloth.describe label=Host > $C/describe_host_before.json
film-ue op cloth.describe label=Presenter > $C/describe_her_before.json
```
**Expected:**
- Host: `skinned_only` contains `Tee` (and `SkeletalMesh`, the hidden default garment).
- Presenter: `skinned_only` contains `Overshirt`, `Top` and `Trousers`.
- If `cloth_components` lists a MetaHuman outfit cloth component with `simulation_enabled: true`, note it: that is a
  default outfit already simulating. It does not change the plan.

### P-C1. Build the plugin; setup writes maps and config (~3 min with the editor restart)
```bash
film-ue plugin-build FMCloth && film-ue editor restart && film-ue health
film-ue exec -c "print(hasattr(unreal, 'FMCloth'))"                                    # True
# re-dress after the restart if agent-02's plan says so (component settings live on the placed actor)
film-ue op cloth.setup label=Host component=Tee preset=cotton_tee dry_run=true > $C/setup_tee_dry.json
film-ue op cloth.setup label=Host component=Tee preset=cotton_tee > $C/setup_tee.json
film-ue op cloth.describe label=Host component=Tee > $C/describe_tee.json
```
**Expected:**
- `plugin-build` compiles 2 files (~20-60 s, like FabScript).
- In the dry run, `maps.torso.max_cm` is 3.0, `maps.collar.max_cm` is 0, `maps.sleeve.max_cm` is ~2.0 and
  `problems` is `[]`.
- In `setup_tee.json`:
  - `changed: true`, `points` in the thousands, `readback_max_cm` 3.0, `config.missing: []`;
  - `config.set.density` 0.15, `config.set.bending_stiffness_weighted` `{low: 0.08, high: 0.08}`;
  - `settings.teleport_distance_threshold` 50.
- In `describe_tee.json`: `simulating: true`, `solver.dynamic_particles > 0`, `clothing[0].physics_asset` = the
  body's physics asset.

**If it fails:**
- A compile error: read it, fix `unreal/plugins/FMCloth`, rebuild. The calls were all checked on the 5.8.4 source;
  the include paths are the likely culprit.
- `config.missing` non-empty, or set values not read back: Python cannot write the config objects. Report the keys.
  The cloth still runs on the engine defaults, which are too stiff (bending 1.0).
- `colours: false`: agent-02's fit colours did not arrive (P-C2). The rule-only maps are fine for this round.

### P-C2. Fit colours (5 s)
```bash
film-ue exec -c "import fmbridge.ops.cloth as C; m=C.garment('Host','Tee').get_skeletal_mesh_asset(); p,c=C._render_colours(m); print(len(p), None if c is None else (sum(1 for x in c if x[1]>0.5), c[:3]))"
```
**Expected:** a few thousand points. The pinned count (G > 0.5) is about the collar band and the shoulder seams (5-15%
of the points), and R values are in 0..1. If every R is near 0.21 (≈ sRGB 0.5 linearised), the colours came in as
sRGB: note it for agent-02.

### P-C3. Is the tee alive? (the check that would have caught round 4; ~1-2 min per run)
```bash
mkdir -p $C/qa
film-ue op qa.cloth label=Host component=Tee sequence=/Game/Reel/SEQ_Reel start=960 end=1080 > $C/qa/S13_960-1080.json
film-ue op qa.cloth label=Host component=Tee sequence=/Game/Reel/SEQ_Reel start=1080 end=1200 > $C/qa/S15_1080-1200.json
# A/B: the same check with the cloth taken off reproduces round 4 (then put it back)
film-ue op cloth.remove label=Host component=Tee && \
film-ue op qa.cloth label=Host component=Tee sequence=/Game/Reel/SEQ_Reel start=960 end=1080 > $C/qa_r4like_S13.json
film-ue op cloth.setup label=Host component=Tee preset=cotton_tee
```
**Expected:**
- S13 and S15: `pass: true`; `metrics.zones.hem.motion_cm` 0.3-1.5 (his gestures); `collar.slip_cm` < 0.3;
  `max_speed_cm_s` < 120; no `cloth.cold_start`.
- The A/B: `cloth.no_clothing` (fail). That is round 4 measured: alive = 0.

**If it fails:**
- `cloth.not_simulating` with `solver.dynamic_particles > 0`: `SimulatedPositions` reads nothing. Check
  `wait_for_parallel_cloth_task` in `describe`, and report it.
- `cloth.dead`: raise the torso `to_cm` with `'overrides={"zones": {"torso": {"to_cm": 4}}}'`, or lower bending to
  0.05. Re-run.
- `cloth.explosion` at a frame: is a physics-asset capsule inside the tee at rest? Try `collision_thickness` 0.2.
  Report the frame.

### P-C4. Penetration under simulation (with agent-02, ~1 min)
```bash
film-ue op cloth.preroll sequence=/Game/Reel/SEQ_Reel frame=1100 'labels=["Host"]' mode=play start=1080
# then agent-02's qa.clip on frame 1100 (their plan's step, layer_masks=true), output to $G/clip
```
**Expected:** `neck_px` 0 and Face>tee 0 at f1100 with the cloth settled, matching agent-02's static number.
If the cloth sinks into the neck, `collar.slip_cm` in P-C3 says so: pin the collar wider (agent-02's G colour).

### P-C5. (Optional) cache determinism (~5 min)
```bash
# needs ChaosCaching enabled in the .uproject + restart; skip if not enabled
film-ue op cloth.cache label=Host mode=record ; film-ue render run r5/cloth_s13_test.yaml   # records
film-ue op cloth.cache label=Host mode=play   ; film-ue render run r5/cloth_s13_test.yaml   # out_dir B
film-ue op render.compare a=<A dir> b=<B dir> 'frames=[960,1079]'
film-ue op cloth.cache label=Host mode=off
```
**Expected:** SSIM ≥ 0.995 on the tee between two `play` renders. If the bindings break (the 5.8.1 report), restore
the sequence from disk (`level.open`) and leave `mode=off`. Live cloth with warm-up is the round-5 method either way.

### P-C6. The 24 fps cloth step (2 min)
```bash
film-ue exec -c "unreal.SystemLibrary.execute_console_command(None, 'p.MaxPhysicsDeltaTime 0.05')"
film-ue op qa.cloth label=Host component=Tee sequence=/Game/Reel/SEQ_Reel start=960 end=1080 > $C/qa_dt05_S13.json
film-ue exec -c "unreal.SystemLibrary.execute_console_command(None, 'p.MaxPhysicsDeltaTime 0.0333')"
```
**Expected:** hem `motion_cm` within ±25% of P-C3's. A large difference means the editor-side check and the render
(1/192 s steps) disagree. Report it; do not change the project setting this round.

### P-C7. (Optional) temporal vs spatial samples on one shot (~4 min)
Render S15 1080-1130 twice:
- with the `final` preset (8 temporal);
- with `temporal: 1, spatial: 8`.

Then `render.compare` and look at the overshirt and tee edges for twitching. **Expected:** no visible twitch with 8
temporal at our low iteration counts; otherwise note it for agent-05 (render presets).

## 4. Her overshirt (~1 min)
```bash
film-ue op cloth.setup label=Presenter component=Overshirt preset=overshirt_light > $C/setup_overshirt.json
film-ue op qa.cloth label=Presenter component=Overshirt sequence=/Game/Reel/SEQ_Reel start=1200 end=1320 > $C/qa/S16_1200-1320.json
```
**Expected:** `maps.torso.max_cm` 6.0, and `pass: true` with hem `motion_cm` ≥ 0.3.
Her Top and Trousers stay skinned this round (tight top; trousers barely visible).

## 5. Settings after any respawn, and the render check (10 s)
```bash
film-ue op cloth.settings label=Host ; film-ue op cloth.settings label=Presenter
film-ue render plan <the r5 final spec> --json > $C/plan.json
film-ue op cloth.render_check "chunks=$(jq -c .chunks $C/plan.json)" warmup_engine=<spec's> warmup_render=32 'presets_used=["cotton_tee","overshirt_light"]'
```
**Expected:** `need: 54`. With `final` (warmup_render 32, warmup_engine 0) it answers `ok: false, warmup_engine: 22`:
set `warmup_engine: 22` in the r5 render spec(s) and re-check (`ok: true`). Chunks are per shot from the shot start.

## 6. Short test render per presenter shot (~6 min)
A preview of each presenter shot through the orchestrator's r5 render spec, with `warmup_engine: 22`:
- S13 f1000-1060 (his L1 gesture);
- S15 f1080-1140;
- S16 f1240-1300;
- S17 f1320-1380.

Look at the tee's chest and hem, and her overshirt's open front:
- folds that move with his turns;
- no balloon;
- no pop on the first frame;
- no hem hanging into the trousers.

Then the finals as the orchestrator schedules them.

## 7. The gate numbers (on the box, ~1 min)
```bash
python $T/films/host-studio/reel/r5/cloth_gate.py --qa $C/qa \
  --r5 '/srv/ue/reel/r5/final/{frame:04d}.png' --r4 '/srv/ue/reel/r4/final_d/{frame:04d}.png' \
  --mask '$G/clip/Reel_{shot}_{frame:04d}_tee.png' --frames S13:1000,1030,1060 S15:1100,1150 \
  --out $C/gate_cloth.json
```
Adjust `--r5`/`--r4` to where the finals land: render.md numbers frames by the master frame, 4 digits. The masks are
agent-02's `qa.clip` with `layer_masks=true`.

**Expected (lines: agent-09's gate v2):**
- `garment.cloth_alive` ≥ 0.30 (round 4: 0.0);
- `garment.cloth_sound` = 1 (round 4: 0);
- `garment.cloth_detail_ratio` ≥ 1.25 (round 4: 1.0 by construction).

Feed `$C/gate_cloth.json` to `film-qa gate`. Any `error` fails the item: rerun the missing input.

## Risks

- **The plugin build:** compiled nowhere yet. Every engine call is checked on the source, but a missing include or
  module dependency is possible (P-C1). The fallback is the round-4 tee, which fails the gate.
- **The Python write to the cloth config objects** (`cloth_configs` is VisibleAnywhere/Instanced): if refused, the
  cloth runs on engine defaults (stiff). A follow-up adds `SetConfig` to FMCloth.
- **Collision gaps at the MetaHuman neck/shoulders.** The collar and shoulders are pinned (0 cm) for that reason;
  watch `collar.slip_cm` and agent-02's `neck_px`.
- **MRQ temporal samples vs the editor check** (P-C6, P-C7): `qa.cloth` judges the editor-side simulation, not the
  render.
- **Time:** P-C0 to P-C4 plus steps 4-7 take ~20 min of box time plus renders.
