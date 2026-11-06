# Round 5: the ONE GPU session (all tracks, in order)

agent-10 (T0) merged the five track plans into this one session. NOT RUN YET: the orchestrator runs it.

| track | owner | plan | what it fixes |
|---|---|---|---|
| T1 | agent-01 | [lipsync.md](lipsync.md) | his lips 0.7 s early, no tracking |
| T2 | agent-04 | [blinks.md](blinks.md) | her head nods with every blink |
| T3a | agent-02 | [garment.md](garment.md) | his tee reads as armour, clips at the neck |
| T3b | agent-08 | [cloth.md](cloth.md) | his tee and her overshirt never simulate |
| T4 | agent-09 | [hair.md](hair.md) | her hair goes short at S17->S18 (f1440), plus gate v2 |

**Using this plan**
- Each step below names the track plan's step. That plan holds the full command, the expected numbers and the
  "if it fails" branches. This page holds the **order**, the **time**, the **numbers that decide** and the **stop
  conditions**.
- The probes are prefixed with their track (T1.P1, T3b.P-C3, ...), because the track IDs collide: T1's P3 is not
  T4's P3.
- The research and the rules are in [docs/unreal/research/README.md](../../../../docs/unreal/research/README.md).
  The delivery checklist is in docs/unreal/GUIDE.md, "Before you deliver a character shot".

**Code:**
- core `fleet/agent-10/r5-integrate` (the five core tracks, off main 85ce6b84, so main fast-forwards);
- film `fleet/agent-10/r5-film-integrate` (film/host-studio + that core + the five `r5-film-*` branches, plus this
  file).

The box tree must be at the film branch's head.

**Face rule (as ever).** Host_Op frames, crops, FBXs and stills stay on the box and in s3 `private/`. Every number
below is a number; the orchestrator looks at Host_Op by eye from `private/`.

**Paths on the box:**
- `T` = the box tree;
- `R=../films/host-studio/reel`, from `$T/tools`;
- `G=/srv/ue/reel/r5/garment`, `C=/srv/ue/reel/r5/cloth`, `H=/srv/ue/reel/r5/hair`, `Q=/srv/ue/reel/r5/qa`;
- finals into `/srv/ue/reel/r5/final`.

**Total: ~5 h of box time** (the estimates add up to ~4 h 20 min; the rest is margin). Set the box's TTL tag to 6 h
at start. Sync before ANY stop (round 4's lesson).

---

## Before the session (kali, no box, ~10 min)

1. **The merge.** Fast-forward main and film/host-studio (the orchestrator). The box tree is then the film head.
   Re-run the reel tests on it: `cd tools && uv run --with pillow --with numpy pytest -q ../films/host-studio/reel`.
2. **T1 step 1, measured cues** (local, ~1 min): `uv run python $R/r5/lips.py cues`.
   - **Expect:** `measured: true`, and each `voice_frame` within ±2 of plan: L1 ≈ 1020, L2 ≈ 1095, L3a ≈ 1158,
     L3b ≈ 1215, L4a ≈ 1350, L4b ≈ 1400.
   - A `moved` warning means the measured frame wins.
   - **STOP** on a `silent` line: the stems are not the mix's.
3. Optional: `uv pip install stable-ts` for word timings (CPU). Without it, the words are estimated and flagged.

## Phase 0: the box up, the new code in (~30 min)

| # | step | expect | stop if |
|---|---|---|---|
| 0.1 | `film-ue up` (i-0284d544cdf14905e; /srv/ue is on the root EBS since round 4) | running, `/health` ok | the disk lost /srv/ue: re-provision as ROUND4 07:44 (project from `private/project/HostStudio`, ~20 min more) |
| 0.2 | `nvidia-smi`; `film-ue doctor` | the L4 is visible, rhi ok | no GPU: the kernel/driver step (ROUND4 02:44, setup.sh `driver`) |
| 0.3 | box tree → the film head; `film-ue install`; `film-ue op ops.broken` | `{}` | any broken module: fix it before anything else |
| 0.4 | **T3b.P-C1a** `film-ue plugin-build FMCloth && film-ue editor restart --wait && film-ue health`; `film-ue exec -c "print(hasattr(unreal, 'FMCloth'))"` | 2 files compile (20-60 s); `True` | a compile error: fix `unreal/plugins/FMCloth` (most likely an include or module dependency), rebuild. **Max 20 min**, then go on without cloth: T3b is skipped and `garment.cloth_*` fail the gate |
| 0.5 | `film-ue describe lipsync.check`, `qa.head_stability`, `groom.lock`, `qa.clip`, `qa.cloth` | each one describes | a missing op = stale install: 0.3 again |
| 0.6 | `level.open` Studio, then `r3/probe_cam.py ... --check` (the 13 Reel_ cameras) | 13/13 OK, no TRASH_ on Host/Presenter | TRASH_: respawn + re-dress (r3/DRESS.md), then go on |
| 0.7 | T1 step 2: `lips.py push`; `perf.py push`; `perf.py calibrate --who him,her` (Saved/ is not synced) | push lists the WAVs and cues; calibrate ok (heads within the yaw table) | calibrate fails as at ROUND4 04:35: agent-01's fixes are in; report it, do not go on to Phase 3 |

The editor restart in 0.4 comes FIRST on purpose. A restart reopens the level from disk, so every later step's
live state (dressing, cloth settings, hair pins) is made after it.

## Phase 1: read-only probes of ROUND 4's state (~35 min)

Run these BEFORE anything changes the level or the animations: they measure round 4. Their numbers are round 4's
column in gate v2 (`tools/tests/data/gate_r4_numbers.json`) and prove each new check fails what the operator saw.
Record each number in `$Q/r4_probes.json`.

| # | probe | command (in the track plan) | expected (round 4) | if not |
|---|---|---|---|---|
| 1.1 | T4.P1/P2 | `groom.lock_check 'labels=["Host","Presenter"]' > $H/check_before.json` | `pass: false`: LODMode 1, AutoLOD.Bias 0.1; Hair `listed` (true or false: record it); LOD 0 STRANDS for every group, `groups[].geometry` present (the `lo_ds` name) | `groups` has an `error`: the P2 exec in hair.md, then tell agent-09 (groom._lods) |
| 1.2 | T4.P4 (before) | `qa.hair_continuity ... shots S15-S18 out=$H/editor_before.json` | S17→S18 reach drop > 12% (FAIL) | < 12%: the editor capture does not see it; rely on 1.3 |
| 1.3 | T4.P3 | `hair_spec.py --frames-dir /srv/ue/reel/r3/final_d --cuts S17,S18` → `film-qa hair` | `pass: false`, `hair.cut_jump` at f1440, reach drop > 12% | < 12%: hair.md's P3 branch (area, the lowered line); **the line must fail round 4 before it gates round 5** |
| 1.4 | T2.P1, P2 | `perf.check anim=.../AS_reel_her_face`, `.../AS_reel_her_solve` | face: `blink_nod`/`blink_locked` fail, dips −0.8…−1.6° near t 2.7, 12.5, 13.2 s; solve: `blink_locked` ≥ 0.3° or nod share > 0.2 | the solve passes: cause 2 was minor (fine, the fix covers it) |
| 1.5 | T2.P3, P5 | `perf.py head --seq /Game/Reel/SEQ_Reel` | exit 1; her `head.blink_nod_deg` ≥ 1.0 (around f1377-1389); `blink_source: curves`, 10-14 blinks | `given`: the anim instance does not expose the curves (P5); the fallback spans are used. Note it |
| 1.6 | T1.P1 | `lips.py probe --who him`, `--who her` (~6 min) | stages 0-1 in sync; the first stage at ≈ −17 frames on L1 is the bug; stage 6 ≈ −17 with silence issues near f975-1015 | stage 6 in sync: the render/mux moved it, and 1.7 decides |
| 1.7 | T1.P3 (control) | `film-ue lips render` on round 4's 65 s clean H.264 (`private/renders/r4/final`), him | L1 FAILS at ≈ −17 frames, `sensitive: true` | it passes: **the render gate cannot be trusted**. Report, and gate on the curve check only |
| 1.8 | T2.P4 | `film-qa head` on round 4's S17 frames, her half (`--with mediapipe==0.10.21`) | `head.blink_nod` fails or `blink_locked` ≥ 0.45 | no internet path for mediapipe: skip (the bone check 1.5 is the gate item) |
| 1.9 | T3a.G1, G7, G5 | `editor.api_names`; `exec r5/tee_slots.py`; `mh.palette` + `garment.hidden_face_maps` | no GeometryScript/Exporter name missing; SHIRT_SLOT and PLAIN_MI written down; head map shrink 0.0 | a name missing: garment.export/qa.garment_look will fail; tell agent-02 |
| 1.10 | T3a.G3, G3b | `qa.garment_look label=Host ... out_dir=$G/look_r4` (and her Top) | his: `verdict: armor`, `wpo` 2.66, index ≥ 0.5, motion ~0; hers: `detail` above his | his index < 0.5: still FAIL on the WPO rule; send the `terms` to agent-02 |
| 1.11 | T3b.P-C0 | `cloth.describe label=Host`, `label=Presenter` | Host `skinned_only` ⊇ Tee, SkeletalMesh; her ⊇ Overshirt, Top, Trousers | a MetaHuman outfit cloth component already simulating: note it, the plan holds |

**Gate check, no box needed:** `film-qa gate --lines --spec $R/r5/gate_spec.json` with the probes' numbers in place
of the estimates. **Expect:** every line fails its round-4 value. **STOP** the gate work (not the session) on a line
that passes round 4, and tell its track.

## Phase 2: his tee refit (T3a steps 1-3, ~25 min)

1. `garment.export label=Host out_dir=$G/fit ...` (garment.md §1): `files` all `[path, true, bytes > 0]`.
   **STOP** if `ref_body` reads as cut: the fit needs the whole body.
2. `film-ue garment-fit --src $G/fit --garment tee --only-slots <shirt> --drape-frames 40 ...` (§2, CPU, 5-10 min).
   - **Expect:** PASS; ease median 1.4-2.0 cm with spread ≥ 0.8; 0.00% inside; collar ≥ 0.8 cm; every pose test
     shows 0 verts inside.
   - On FAIL, apply §2's fixes (`--drape-frames 60`, collar/sleeve/shoulder ease, `--min-ease 0.6`). Max 3 runs,
     then stop T3a and keep round 4's tee (the gate will refuse it).
3. `mh.import_garment`, then `mh.dress` (Tee, no WPO), then `mh.leader_check`, then `dress_him.py`, then
   `level.save` (§3).
   - **Expect:** bounds within 1 cm of the default garment; leader bone gap < 0.1 cm; `Tee` in `seq_sections`.

From here on, any respawn / host_swap / re-place means: re-run §3's dress + dress_him, `cloth.settings` (Phase 3)
and `groom.lock` (Phase 6).

## Phase 3: cloth on the refit tee and her overshirt (T3b, ~20 min)

| # | step | expect | stop if |
|---|---|---|---|
| 3.1 | T3b.P-C1b `cloth.setup label=Host component=Tee preset=cotton_tee` (dry run first) | `changed: true`, `readback_max_cm` 3.0, `config.missing: []`, density 0.15, bending 0.08; describe: `simulating: true`, dynamic particles > 0 | `config.missing` non-empty: the cloth runs on the stiff defaults. Go on, but expect `cloth.dead`; FMCloth `SetConfig` is round 6 |
| 3.2 | T3b.P-C2 the fit colours | a few thousand points, 5-15% pinned (G > 0.5) | every R ≈ 0.21: sRGB colours; note it for agent-02 (rule-only maps are fine) |
| 3.3 | T3b.P-C3 `qa.cloth` S13 960-1080 and S15 1080-1200; then the A/B (`cloth.remove` → qa.cloth → `cloth.setup` again) | S13/S15 `pass`, hem `motion_cm` 0.3-1.5, collar slip < 0.3, max speed < 120 cm/s; the A/B `cloth.no_clothing` (round 4 = alive 0) | `cloth.dead`: torso `to_cm` 4 or bending 0.05, max 2 tries; `explosion`: `collision_thickness` 0.2. Still failing: report the frame, go on (the gate refuses `cloth_alive`) |
| 3.4 | T3b.P-C6 `p.MaxPhysicsDeltaTime 0.05` A/B on S13 | hem motion within ±25% of 3.3 | a bigger change: report it; no project change this round |
| 3.5 | T3b §4 her overshirt: `cloth.setup ... preset=overshirt_light`, `qa.cloth` S16 1200-1320 | torso max 6.0 cm, `pass`, hem ≥ 0.3 cm | as 3.3 |
| 3.6 | `level.save` | | |

Skip T3b.P-C5 (cache) and P-C7 (temporal vs spatial) unless the finals show cloth twitching: they are optional.

## Phase 4: his and her mouths, one line at a time (T1 steps 4-6, ~25 min)

1. `lips.py solve` (6 lines, 1-2 min each). This includes **T1.P4**.
   - **Expect:** per line `timing.ok`, `options.process_mask: MOUTH_ONLY`, `head_movement_mode: DISABLED`,
     `missing: []`.
   - If `missing` lists the Process Mask: go on (compose takes only the speech curves) and say so.
2. **T1.P2** `lips.py bias`.
   - **Expect:** each line |lag| ≤ 1, corr ≥ 0.5, `mean_lag_s` within ±0.04.
   - This calibrates the gate's `track_r` line (0.35): record the real corr values. If `mean_lag_s` is outside
     ±0.04, pass it as `expected_lag_s` from here on.
3. `lips.py compose --who him`, then `--who her`; `lips.py check --who him|her --stage solve`.
   - **Expect:** exit 0, `diagnosis: in sync`; per line |lag| ≤ 1, corr ≥ 0.5, onset ≤ 0.25 s, silence `worst_open`
     < 0.05.
   - **STOP** Phase 5 on a failure here: the per-line solve itself is wrong. Send the JSON to agent-01.

## Phase 5: the faces (T2's naturalize inside T1's loop, ~40 min)

The order is T2's (her first: his blinks avoid hers). T1's stage checks run after each step.

1. `perf.py naturalize --who her`, then `--who him`; then `perf.py check --who him,her`.
   - **Expect:** per face, `blink_nod` 0.0, `blink_locked` < 0.15, `blink_speed` < 1.5, `head_buzz` < 0.06.
   - Also `plan.solver_head: replace`, `blink_head: still`, `blink_guard` 0-10 (> 15: look at `plan.nods`),
     `blink_rate` 12-30/min, `clash_frames: []`.
2. `lips.py check --who him|her --stage face`: exit 0.
   - A failure here, where `solve` passed, means a perfkit layer moved the mouth: send the JSON to agent-04.
3. T1 step 7, the rest of round 4's loop: `perf.py sync`, `gaze` (and `turn_head`, as in ROUND4 08:21), then
   `lips.py check --stage final`: exit 0.
   - **SPEECH_GAIN:** try 1.3 for him (perf.py `SPEECH_GAIN`) before round 4's 1.7. Keep the lowest gain that still
     passes `corr` and reads open by eye. Max 2 tries.
4. `perf.py place --seq /Game/Reel/SEQ_Reel`, then `lips.py check --stage placed` for both.
   - **Expect:** exit 0; one Face section at START (960 him, 1080 her), offset 0, rate 1.0.
   - These two JSONs are the gate's lips `--curve` inputs.
5. `perf.py head --seq /Game/Reel/SEQ_Reel` (T2's gate).
   - **Expect:** exit 0; `head.blink_nod_deg` ≤ 0.6 (expected 0.1-0.35); `head.blink_locked_deg` ≤ 0.3 (expected
     < 0.15); `head_buzz` ≤ 0.08.
   - Writes `out/host-studio/reel/perf/qa/gate_head.json`.
   - On a FAIL, blinks.md §2 (a body nod: an `avoid_blinks` span; buzz: `qa.head_stability ... out=` +
     `film-qa head-samples`).
6. agent-01's look check (`perf.py looks --measured`, round 4's gate d): heads within 15° of plan, the right way.
7. `level.save`.

## Phase 6: measure the garment, lock the hair (~30 min)

1. **T3a §4** (~15 min): `qa.clip` (S13, S15, S17, S18 + the extra frames, `layer_masks=true`), `qa.garment_look`,
   then `film-ue garment-gate ... --first-pass --out $G/gate_garment.json`.
   - **Expect:** `neck_px` 0 every frame; pairs ≤ 0.001; `wpo_cm` 0; `armor_index` ≤ 0.35 with the sim (0.3-0.45
     without); `silhouette_ratio` 1.04-1.10.
   - `neck_px > 0`: garment.md §5 (refit with collar 1.1, max one more fit: Phase 2 + 3.1 again). Never add WPO.
2. **T3b.P-C4**: `cloth.preroll ... frame=1100 mode=play start=1080`, then `qa.clip` at f1100.
   - **Expect:** `neck_px` 0 and Face>tee 0 with the cloth settled.
3. **T4 steps 2-4** (~10 min): `groom.lock 'labels=["Host","Presenter"]' persist=true > $H/lock.json`.
   - **Expect:** `pass: true` and `render_cvars` = the three hair cvars.
   - A `listed but LODSync has not resolved it yet` note: `level.save`, then `level.open`, then `groom.lock_check`
     until Hair shows `live_lod: 0`. After a `level.open`, re-check the dressing (`mh.leader_check`) and
     `cloth.settings`.
   - Then `level.save`; `qa.hair_continuity ... out=$H/editor_after.json`. **Expect:** pass, `hair.cut_reach_pct`
     < 12 (S17→S18 under ~5).
   - Then `groom.lock_check > $H/check_after.json`.

## Phase 7: render setup and test renders (~25 min + the orchestrator's eye)

1. `cloth.settings label=Host`, `label=Presenter`. Then `film-ue render plan <r5 final spec> --json > $C/plan.json`
   and `cloth.render_check ... warmup_render=32 presets_used=["cotton_tee","overshirt_light"]`.
   - **Expect:** `need: 54`; with `final` it answers `ok: false, warmup_engine: 22`.
   - **Set `warmup_engine: 22` in `r3/30-final.yaml`** (it already carries the hair cvars and `preroll: cut`).
     Re-check: `ok: true`.
2. `lips.py boxes --who him`, `--who her`: the mouth boxes for the render gate.
3. `groom.lock_check` again, right before rendering: `pass: true`.
4. **Test previews** (T3b §6, ~6 min): S13 f1000-1060, S15 f1080-1140, S16 f1240-1300, S17 f1320-1380, through the
   r5 spec at preview quality with `warmup_engine: 22`.
   - **The orchestrator looks** at: tee folds moving with his turns, no balloon, no first-frame pop, no hem in the
     trousers; her overshirt's open front; his neck at S15 f1082-1128; her hair at S17's end.
   - **STOP** the finals on anything the operator named. Fix it in its phase, then preview again (max 1 retry per
     issue, then decide with the operator).
   - **T4.P5:** in the render log, `r.HairStrands.LODMode` reads 0.

## Phase 8: presenter finals (~35 min)

S13, S15, S16, S17, S18 at 1080p into `/srv/ue/reel/r5/final`, one batch per shot, `probe_cam --check` before each
(round 4: ~4-6 min a shot; strands at full count add a few %: **T4.P6**, compare S18's s/frame with round 4's).
- The 8 set shots stay as they are in `private/renders/r4/final_d` (no presenter in them). Copy them in for the cut.
- Then `final_check` and `final_qa` on all 13 shots.
- **Expect:** no missing, black or jumping frames.
- **STOP** on a GPU fault (round 4: Xid 109 / TerminateOnGPUCrash on Reel_V03). Retry the shot once; a second fault
  stops the session: sync, then report.

## Phase 9: checks on the frames (~25 min, CPU on the box)

| # | check | command | expect |
|---|---|---|---|
| 9.1 | hair (T4 step 6) | `r5/hair_spec.py --who her --frames-dir /srv/ue/reel/r5/final --cuts S15,S16,S17,S18` → `film-qa hair` | `pass`, `hair.cut_reach_pct` < 12 at f1440 |
| 9.2 | heads (T2 §3) | `film-qa head` on her shots (her half) and his S13/S15/S17 | `pass`, `blink_nod` ≤ 0.2, `blink_locked` < 0.45 |
| 9.3 | cloth (T3b §7) | `r5/cloth_gate.py --qa $C/qa --r5 ... --r4 ... --mask $G/clip/... --out $C/gate_cloth.json` | `cloth_alive` ≥ 0.30, `cloth_sound` 1, `cloth_detail_ratio` ≥ 1.25 |
| 9.4 | the cut | the 65 s and 45 s cuts as in round 4. **Rebuild the captions from the new measured cues.json, never round 3's** | -14 ± 1 LUFS, ≤ -1 dBTP, frames 1560 / 1080, captions within 2 frames |
| 9.5 | lips on the render (T1 step 10) | `film-ue lips render --video <new 65 s clean H.264> ... --who him` (and her) | each line `verdict: pass`, \|lag\| ≤ 1, `sensitive: true`; exit 2 (inconclusive) = fix the box, not the gate |
| 9.6 | lips numbers (T1 step 11) | `film-ue lips gate --curve ... --render ... --cues ... --stem ... --out $Q/lips_gate.json` | `lips.cues_fresh` 1 |

## Phase 10: the gate, then the eye (~10 min)

1. Write `$H/hair_gate.json` (hair.md, gate step 1): `hair.lock` = check_after's pass; `hair.render_cvars` 1;
   the reach numbers from 9.1.
2. `film-qa gate --lines --spec $R/r5/gate_spec.json`: `pass: true`.
3. Sign:

   ```
   film-qa gate $H/hair_gate.json $Q/lips_gate.json <gate_head.json> $G/gate_garment.json $C/gate_cloth.json \
       --spec $R/r5/gate_spec.json --out /srv/ue/reel/r5/gate.json
   ```

   - **Expect:** `verdict: SIGN`, exit 0.
   - On REFUSE, each failing item names its command: fix it in its phase, re-render only the affected shots,
     re-gate.
   - **No waiver on lips, head, garment or hair: the gate refuses it.**
4. Only then: the orchestrator watches both cuts by eye, from `private/`, before anything goes to the operator.

## Phase 11: wrap (~15 min)

As round 4's wrap (ROUND4 09:40-09:52):
1. Sync `/srv/ue/reel/r5` → `private/renders/r5/box_r5`, the finals → `private/renders/r5/final_d`, and the
   deliverables → `private/renders/r5/final`. Check counts and `aws:kms` on each.
2. Save the assets and the level. Then project → `private/project/HostStudio`, DDC → `private/ddc/5.8.4`.
3. Stop the editor, then `film-ue down`.

## Expected numbers, all in one place (gate v2)

| item | line | round 4 (value or the probe that measures it) | round 5 expected | measured at step |
|---|---|---|---|---|
| lips.lag_frames | ≤ 1 | ~17 (L1) | ≤ 1 | 5.4 / 1.6 |
| lips.track_r | ≥ 0.35 (calibrate at 4.2) | probe 1.6 | ≥ 0.5 | 5.4 |
| lips.onset_lead_ms | ≤ 250 | ~600-800 | ≤ 250 | 5.4 |
| lips.silence_open / _busy | ≤ 0.10 / ≤ 0.25 | probe 1.6 | < 0.05 / few % | 5.4 |
| lips.render_lag_frames, render_conclusive | ≤ 1, == 1 | probe 1.7 (≈ 17) | ≤ 1, 1 | 9.5 |
| lips.cues_fresh | == 1 | 0 | 1 | before the session |
| head.blink_nod_deg | ≤ 0.6 | ≥ 1.0 (probe 1.5) | 0.1-0.35 | 5.5 |
| head.blink_locked_deg | ≤ 0.3 | probe 1.5 | < 0.15 | 5.5 |
| garment.neck_px | 0 | 3 | 0 | 6.1 |
| garment.pair_fraction | ≤ 0.001 | 0 | 0 | 6.1 |
| garment.wpo_cm | ≤ 0.2 | 2.66 | 0 | 6.1 |
| garment.armor_index | < 0.5 | ≥ 0.5 (probe 1.10) | ≤ 0.35 | 6.1 |
| garment.silhouette_ratio | ≤ 1.12 | probe 1.10 | 1.04-1.10 | 6.1 |
| garment.cloth_alive | ≥ 0.30 cm | 0.0 | 0.3-1.5 | 9.3 |
| garment.cloth_sound | == 1 | 0 | 1 | 9.3 |
| garment.cloth_detail_ratio | ≥ 1.25 | 1.0 | ≥ 1.25 | 9.3 |
| hair.lock | == 1 | 0 | 1 | 6.3 |
| hair.render_cvars | == 1 | 0 | 1 | Phase 7 |
| hair.cut_reach_pct | < 12 | > 12 (probe 1.3) | < 5 | 9.1 |

## Open risks (read before starting)

1. **FMCloth has never been compiled.** Every call was checked against the 5.8.4 source by agent-08 and again by
   agent-10. A missing include or module dependency is still possible: 0.4 time-boxes it. Without it, T3b is out
   and the gate refuses `cloth_*`.
2. **Cloth config by Python** (`cloth_configs` is VisibleAnywhere/Instanced) may be refused. The cloth then runs on
   the stiff engine defaults (3.1).
3. **HeadMovementMode sits in the performance's "Visualization" category** (MetaHumanPerformance.h:245-247).
   `DISABLED` may shape only the export, not the solve's head curves. Harmless here:
   - perf.face `solver_head=replace` drops the solve's head anyway (T2);
   - 1.4 / 5.1 measure it.
4. **A respawn undoes three things** (round 3-4's recurring trap): the dressing, the cloth settings and the hair
   lock. After any respawn, `level.open` or `groom.set`, re-run Phase 2 §3, 3.6/7.1 and 6.3. The gate's `hair.lock`
   and the 7.3 re-check catch a missed lock.
5. **Calibrations and VO live in Saved/,** which no sync keeps. 0.7 re-pushes them; an editor crash mid-session
   does not lose them, but a re-provision does.
6. **The thresholds are from synthetic tests and need the real numbers:**
   - lips `track_r` 0.35: from 4.2;
   - garment detail/motion terms: from 1.10;
   - the hair matte: from 1.3.

   Each probe's branch says what to do when it reads otherwise. Agree a changed line with its owner before signing.
7. **The GPU faults on Reel_V03** (round 4, twice) are not investigated. This session renders only presenter
   shots; V03 is not re-rendered.
8. **Core code that lived only on film/host-studio.** Round 4 put `speech_gain` into perfkit (`perf.face`) on the
   film branch only. The film merge keeps it next to T2's `blink_head` and `preset`, but main does not have it.
   When film/host-studio is fast-forwarded, main still lacks it, so a fresh box from main would miss
   `speech_gain`. Port it to main in round 6.
9. **Time:** ~5 h of box time. If the session runs long, cut in this order:
   - T3b's optional probes;
   - 1.8 (mediapipe);
   - the SPEECH_GAIN tries (keep 1.7);
   - the 45 s cut.

   Never cut the gate or the Phase-1 probes: they are what makes this round's numbers mean something.
