# Round 5 (06 Nov, Linux GPU box): log and state

Box driver: agent-06. Orchestrator: cc-64d05f6e. Plan: [r5/PLAN.md](r5/PLAN.md). Times UTC (IST = UTC+5:30).
Box i-0284d544cdf14905e (g6.4xlarge, L4), up 11:28 (orchestrator), TTL shutdown 17:29. /srv/ue on the root EBS (intact).
Box tree `/srv/ue/r5tree` (r3tree kept as round 4 left it); outputs under `/srv/ue/reel/r5/{garment,cloth,hair,qa,final}`.
Driven from kali: `/tmp/fleet-agent-06-ue/r5/fu film-ue …` (FILM_UE_CONF_DIR `/tmp/fleet-agent-06-ue/r5/conf`,
face_data=yes, local port 18806); the kali tree is this branch (`fleet/agent-06/r5-drive`), pulled from
`fleet/agent-10/r5-film-integrate`. Probe JSON on kali under `/tmp/fleet-agent-06-ue/r5/probes/` (copied to `$Q`).

## Log

Times marked ~ were written from memory, not read off a clock (corrected at 12:11); the order is right.

| UTC | What |
|---|---|
| 11:28 | Box up (orchestrator; ap-south-1b capacity retries). Health ok, uptime 50 s |
| 11:30 | Pre-session reel tests: kbuild has no `uv` in the image, so they did not run there (run on kali later) |
| 11:32 | 0.2 L4, driver 580.178.04, 3.3 GB used; `film-ue doctor` OK: 5.8.4, Vulkan SM6, 350 ops, 173 GB free |
| 11:38 | 0.3 box tree `/srv/ue/r5tree` @8c2cff19 (git archive through S3 tmp `ue-linux/tmp/agent06/r5/`); `film-ue install` 155 files; `ops.broken` `{}` |
| 11:36 | **Pre-session T1 step 1 (cues)**: stems = agent-11 reel-sound `audio/vo/vo_{him,her}.wav` (round 4's, Nov 1). `measured: true`, no `silent`. voice_frame vs plan: L1 1007.3 (1020), L2 1110.1 (1095), L3a 1157.8 (1158), L3b 1201.8 (1215), L4a 1359.8 (1350), L4b 1386.0 (1386); **4 `moved`** (L1 −12.7, L2 +15.1, L3b −13.2, L4a +9.8 f). Trap: `cmd_cues` reads the plan from cues.json when it exists, so a 2nd run overwrote voice_frame_planned and cleared the warnings (file deleted, re-run once) |
| 11:40 | **0.4 FMCloth: 3 failures, all fixed in the timebox.** (a) `Precompiled rules assembly …/UE5Rules.dll does not exist` (restored engine has no Engine/Intermediate): QueryTargets with the installed marker off compiled the rules (17 s). (b) `PrimaryAssetId.generated.h` not found (no engine UHT headers): `Build.sh UnrealEditor … -SkipBuild`, marker off. (GenerateClangDatabase first: exit 6, and it writes to UnrealEditorGCD anyway.) (c) `FMClothLibrary.cpp:98:36` no matching `NewObject` (UPackage incomplete): `#include "UObject/Package.h"`. Build OK (6 actions). Fixes merged by agent-08 / agent-10 → 91bd7db4 |
| 11:49 | 0.4 `editor restart --wait` 35 s; `hasattr(unreal, 'FMCloth')` True |
| 11:52 | Trees → 91bd7db4 (diff: setup.sh plugin step + its test + the include; the built plugin stands) |
| 11:53 | 0.5 lipsync.check, qa.head_stability, groom.lock, qa.clip, qa.cloth all describe. 0.6 Studio open after restart (`level.open` wants `path=`, not `name=`); Host BP_Host_Op_C, Presenter BP_Presenter_C, no TRASH_ components; probe_cam 13/13 OK |
| ~11:54 | **agent-01: the VO stems ≠ the delivered mix.** mix.wav has L1 ~f1021-1044, L2 ~f1097; the stems put L1 ~14 f early: the operator's 0.7 s. **Orchestrator decision: the delivered mix is canonical**; each line WAV is located in mix.wav by cross-correlation and those offsets are the cues; L3 split by VAD (or solved whole). agent-01 adds a stem-vs-mix check (must fail round 4's stems). **Phase 4 on hold until then** |
| ~11:55 | 0.7 partly: only L1/L2/L3/L4a/L4b.wav exist (no L3a/L3b), so `perf.py push` and `lips.py push` stop on L3a.wav. vo_him/vo_her/cues.json pushed by hand. `perf.py calibrate` waits for agent-01's cues fix |
| ~11:56 | **1.1** groom.lock_check: `pass: false`; LODMode 1.0, AutoLOD.Bias 0.1; LODSync forced_lod 0, Hair `listed: true`, live_lod 0, all groups STRANDS, no group error. Host Hair length_scale 0.85. As expected |
| ~11:57 | **1.4** perf.check her_face: fails blink_nod 0.25 (0.2), blink_locked 0.306 (0.3); head_buzz 0.057 ok; 12 blinks. **Per-blink nods are positive** (t2.76 +0.37, t8.06 +1.49, t12.56 +0.53, t13.26 +0.68), not PLAN's −0.8…−1.6. her_solve: fails gaze_shifts, blink_nod 0.5; blink_locked 0.219 (passes); 2 blinks |
| ~11:58 | **1.5 DEVIATION**: `perf.py head` rc 1 only on his head_buzz (yaw 0.348° RMS, spikes from 10.25 s). blink_source curves, but **blinks = [] for both** (her closure samples reach 0.995), gate head.blink_nod_deg 0.0 "no blinks measured". The gate head check does not fail round 4: head gate work stopped, sent to agent-04 |
| ~11:59 | 1.6 `lips.py probe` (against the stems' cues, i.e. the wrong reference): every stage "scattered". him L1 −0.6 f (to the stem; ~−14 f to the mix), onset 0.87 s; L2 +17.3; L4a −5.5. her L3a +9.9, L3b +4.9, L4b +10.3; her silence worst_open 0.58 (f1408-1450). Stages 3-6 change nothing. 0_line_L1/L3b errored (round 4 never made those anims) |
| ~12:00 | 1.2 qa.hair_continuity S15-S18 (editor): cut_reach 1.07 % (< 12: the editor sees no drop at f1440); **hair.pop inside S15 f1081/1082** (reach +8.9 % / −12.2 %) |
| ~12:01 | Trees → 3996efec; `lips.py cues` from the mix: L1/L2/L3/L4a.wav **not in mix.wav** (0.04-0.16), L4b 0.309 (spurious f1245) |
| ~12:02 | **1.3 DEVIATION**: hair_spec + film-qa hair on r3/final_d S17/S18: `pass: true`, cut_reach 0.15 % (r4 should fail). agent-09: the L*<40 matte saturates at night (dark clothes) and S18 is locked off on S17's end frame, so LOD cannot jump at the cut. Cut-pair probe (head box [0.545,0.552,0.663,0.830]): 1439→1440 SSIM 0.9863 / MAD 2.57 vs neighbours 0.9985-0.9991 / 0.87-1.14; whole frame SSIM 0.991 vs 0.998/0.997; dark area −2.4 % and holds. **New cause: S18 is its own MRQ job → new PIE world → her hair sim restarts at f1440.** Fix (PLAN updated, 5d572120): S17+S18 as ONE job; gate `hair.cut_pop_ratio` (line 1.8, r4 2.57) |
| ~12:03 | Trees → ecc31c24 (install). Head gate re-judged offline from the saved samples (agent-04 clock fix): r4 blink_nod 5.846 at Host f1550-1562 = an edge artefact (fixed d4485bf4) → **r4 blink_nod_deg 2.696 (Presenter f1395-1407), blink_locked_deg 0.416**: both fail their lines |
| ~12:04 | 1.9 G1: no GeometryScript/Exporter name missing; missing ChaosClothWeightedValue, ClothMassMode (cloth.py), UsdStageImportOptions. G7: SHIRT_SLOT `M_DG_bodyShapeF_Shirt` (ClothOp4 `_Inflate_N_P`, wpo 0.15/0.75/1.76), `plain` null → PLAIN_MI `/Game/Host/Unpacked/Host_Op/Clothing/MI_WI_DefaultGarment_M_DG_bodyShapeF_Shirt`. G5 skipped (no change this round) |
| ~12:05 | 1.11 P-C0: Host skinned_only [SkeletalMesh, Trousers]; Presenter [Overshirt, Top, Trousers]: nothing simulates |
| ~12:05 | 1.10 G3: `garment.py:299` `Array: Slice step must be 1` (fixed in place, agent-02 46240214). G3 Host: **armor, index 0.283** (wpo 2.66 scores 1; silhouette 2.30 and motion 0.226 implausible). G3b her Top: cloth 0.192, detail 0.105 vs his 0.0497. agent-02: silhouette/motion capture broken on the box → weight 0; detail ramp recalibrated → **r4 armor_index 0.538** |
| ~12:06 | agent-02 ref_body probe: no "his uncut body" exists (SKM_Host_BodyMesh is uncut, 30455 v, median 0.45 / p95 1.2 cm from his); fallback `garment-fit --morph-ref` (2da3ce99) |
| ~12:07 | Take search (04987546): no take of any line is in the committed mix. Control: agent-07's r6b-audio mix (Nov 1 12:16) holds the line WAVs at 0.73-0.86 → the committed mix (agent-13, Nov 1 14:50) carries other VO |
| ~12:08 | Orchestrator (B) re-mix from the round-4 stems: done on kali (−14.1/−1.7, 45 s −14.07/−1.7; cues pass 0.73-0.86), then **(B) STOPPED, reverted, nothing committed**: agent-01 found those stems are the v1 script (L1 9.2 s from f929, not v2's 1.3 s at f1020). The delivered v2 mix stays. **Orchestrator: option D** — separate the voice from the committed mix (demucs on the box, agent-01's step), cut per line, solve from that |
| ~12:09 | 3.5 her overshirt: setup refused: her FBX's own vertex colours read as "all pinned" (max distance 0 everywhere); `use_colours=false` then fails writing config (`drag` is a ChaosClothWeightedValue struct, not a float; that struct is not exposed to Python). With agent-08. 108,533 sim particles (agent-08: watch sim time) |
| ~12:09 | Phase 2 §1 garment.export: 14 files, all present, sizes > 0 |
| ~12:10 | **Blender was gone from the box** (round 4's /srv/ue/tools/blender-4.2): 4.2.23 LTS reinstalled from download.blender.org. `garment-fit` runs on the box (it reads --src locally) |
| 12:11 | Clock check: earlier rows corrected to ~ times. Trees → 52c38525 |
| 12:13 | Fit #1 (`--morph-ref --drape-frames 40`): morph matched 74.5 %, cut region median 0.203 / max 1.311 cm. FAIL: ease 2.92 (loose); every pose test "5.99 cm" = a tool bug (the hidden shorts counted, capped at 6 cm). #2 (`--weights transfer`) = #1 (transfer is the default). Neither counts (orchestrator) |
| 12:15 | 3.5 overshirt: `use_colours=false` → simulating, 82,243 dynamic / 25,548 kinematic particles; config.missing 16 keys (C++-only names) |
| 12:17 | qa.cloth S16: not_simulating, body 0 cm, sim_time 0 → agent-08: editor cloth needs bUpdateClothInEditor + RecreateClothingActors (5ab872da, f4c2420b) |
| 12:18 | Fit #3 (fixed pose test, `--drape-frames 0`): ease median **1.747**, spread 0.945, collar 1.09, shoulder 1.10, chest 1.68, waist 2.44, hem 2.87, sleeve 1.47, 0 % inside at rest. Pose tests 310-505 verts inside (2.3-4.6 cm): the face rode neck_02 rigidly (agent-02 57908a4f) |
| 12:19 | **Option D (orchestrator):** the v2 voice separated from the delivered mix (agent-01: demucs htdemucs, committed `audio/vo_sep/`, 890afabf). `lips.py cues`: pass, mix_score 1.0 on every line; onsets L1 1019.76, L2 1094.4, L3a 1157.76, L3b 1214.88, L4a 1350.0, L4b 1385.52. The committed mix is unchanged |
| 12:21 | 0.7 lips push + perf push (perf.py reads `vo/L*.wav`: the vo_sep line WAVs copied there by hand) + **calibrate him, her OK** (signs measured, dead []) |
| 12:23 | Cloth tick proof: sim_time 0 with SetUpdateClothInEditor, with viewport realtime, and (12:31) with AlwaysTickPoseAndRefreshBones (recently_rendered false). **The offscreen editor never steps cloth → agent-08 fallback: no qa.cloth; judge alive in the step-6 previews + cloth_detail_ratio** |
| 12:25 | **4.1 solve**: 6 lines (L3a/L3b separate) MOUTH_ONLY, head DISABLED, timing ok, missing [] (15 s total) |
| 12:27 | Fit #4 #a crashed in the new pose test and the CLI re-read #3's report (f78e2871). **Fit #4** (out4): FAIL on pose tests only, 59-72 verts/anim excluding armpit (info ~110): chest ~40 (≤ 1.53 cm), sleeve 9-17, hem 1-4 (≤ 2.61), waist 1-4, chest@face 3-12, **collar@face 1 vert 1.4-1.9 cm** in 6/9 anims |
| 12:29 | **4.2 bias**: L1 +0.39 f r 0.397 pass; **L2 −18.22 r 0.234 FAIL**; L4a −0.45 r 0.543 pass; L3a +0.16 r 0.883 pass; **L3b −1.39 r 0.492 FAIL**; **L4b +16.42 r 0.432 FAIL**; mean_lag −0.0215 s. agent-01 suspects the check (held first/last keys); compose ON HOLD |
| 12:30 | 6.3 (early, independent) **groom.lock** persist: LODMode 0, Bias 1.0, DefaultEngine.ini; lock_check pass. Re-checked at 7.3 |
| 12:31 | **DEVIATION (orchestrator-approved): fit #4 imported although its static pose test FAILs** ("do not import a FAIL", garment.md §2). Why: the rest fit is in every range, the pose test counts verts behind hidden/cut body, and the gate is Phase 6 qa.clip on the real render (neck_px 0, Body>Tee ≤ 0.001); if it fails, ONE refit with +0.4 cm on the clipping regions, then decide; never WPO. `mh.import_garment` bounds [32.5, 20.6, 45.1]; slots `MI_WI_DefaultGarment_M_DG_bodyShapeF_{Shirt,Short}` (material keyed by that name); mh.dress ok (SkeletalMesh shirt ×4 + Tee short hidden); leader_check pass (gap 0.0); dress_him ok, Tee in seq_sections ×3; level.save |
| 12:33 | **3.1** cloth.setup Host Tee cotton_tee: config.missing [] (17 set), readback 3.0, torso 3.0 / sleeve 2.0; overshirt re-set: missing [], readback 6.0. cloth.settings both, level.save. agent-08: the weighted values (bending etc.) live only on the editor sim, so MRQ would render the engine-default bending 1.0 → C++ `FMCloth.SetWeightedConfig` coming (plugin-build + restart before Phase 7) |
| 12:34 | **6.1 qa.clip pass 1 (fit #4, transferred weights)**: wpo 0, armor 0.251, Body>tee 0.00022, neck_px 1 (S15 f1152/1198, ≤ 0.5 cm), **Trousers>tee up to 6.4 % / 3 cm in S17 end + S18** (the trousers were skinned to copy the old tee's hem weights) |
| 12:37 | FMCloth `SetConfigValue` (agent-08 8c21e6f9): plugin-build (6 actions, 63 s), editor restart. The weighted cloth config now lives on the asset (MRQ gets it): overshirt bending 0.25, tether 1.02 |
| 12:39 | Refit (the one approved) Fit2 `--weights keep --ease collar 1.2`. After restart: lock_check failed on the new Tee (forced_lod) → groom.lock |
| 12:41 | cloth.setup Tee on the new mesh dropped Tee + Trousers leader pose (asset edit re-creates the components; agent-08 f4fb2ab2 re-leads). Order kept: cloth.setup → mh.dress → dress_him → cloth.settings → groom.lock → leader_check → level.save |
| 12:43 | **4.2 bias** (agent-01's fixed metric: onset/silence judged, voice lag reported): all 6 pass. **4.3 compose** him, her; **check --stage solve: both in sync** (ref lag ≤ 0.8 f, ref r ≥ 0.969; silence ≤ 0.001). **Phase 4 PASS** |
| 12:44 | qa.clip pass 2 (Fit2): Trousers>tee 0, armor 0.194; **neck 112 px / 2.9 cm at S17 f1397** (the collar no longer follows his neck on the turn). Orchestrator: (A) mixed weights; never (B) Fit2 or (C) fit #4 |
| 12:47 | 5.1 naturalize, check: him nod 0 / locked 0.064; her nod 0 / locked 0.189. Lips face stage in sync |
| 12:54 | 5.3 `perf.py stage` (the Test_ sequences were missing) → sync, gaze; lips final in sync |
| 12:56 | 5.4 place; lips placed in sync. 5.5 head FAIL (him 2.62° at f1294-1306); 5.6 her S15 look 32.5° off. **Cause: I had skipped calibrate_body and the unmeasured `perf.py looks`** (agent-01) |
| 12:57 | Fit3 (`--weights blend`: transferred on collar/shoulder/chest/sleeve) → qa.clip pass 3: neck 3 px S15 f1150 (≤ 1.1 cm), S17 turn 0; Trousers>tee 0.57 % (0.5 cm) |
| 13:02 | Fit4 (#8: blend on collar/shoulder/sleeve only, collar ease 1.5; agent-02) |
| 13:13 | **Phase 5 redone** (calibrate_body, looks, naturalize, stage, sync, gaze, place): **looks all 4 on plan** (her S15 +0.2°); lips in sync at face/final/placed; her head passes (nod 0, locked 0.265); **his head still fails: blink_nod 2.891° at f1294-1306, locked 0.726** (big turns; agent-04: the turn path, not a nod; with agent-04/agent-01). Fit4 imported, dressed, cloth (bending 0.08 on the asset), lock, leaders, saved |
| 13:16 | qa.clip pass 4 (Fit4, final motion): neck 1 px (S15 f1150/1152, ≤ 1.2 cm), Trousers>tee 0.13-0.53 % (≤ 0.68 cm, S17 end + S18), Body>tee 0, armor 0.126, wpo 0 |
| 13:17 | **Her S16 preview** (preview preset, f1240-1299) → `private/renders/r5/review/S16_f1240-1300_preview.mp4` (audio offset first set wrong at 50.417 s, fixed to 51.667 s and re-uploaded) |
| 13:20 | Mouth boxes (him 248 f, her 274 f) + `lips.py refcurves`. **1.7** (render vs the v2 solves, round 4's 65 s cut): him L1 −1.36 / L2 +16.95 / L4a −9.01, FAIL (sensitive); her L3a pass, L3b/L4b inconclusive (small boxes) |
| 13:22 | Editor restarted on its own during the torso-lock chain (no crash recorded; uptime 549 s at 13:31); state on disk intact (Fit4 dressed, lock, leaders). `perf.py head` in that chain hit "no actor 'Host'" and was re-run |
| 13:25 | Fit #9 (collar 1.8, waist 3.0, hem 3.4, blend collar/shoulder/sleeve) |
| 13:27 | **ORCHESTRATOR STOP**: her S16 preview: overshirt cloth collapsed/shredded; face dark and muddy. No previews/finals until fixed |
| 13:29 | **Her overshirt restored to round 4**: cloth.remove (LOD0 s0 unbound; `is_section_using_cloth` False; `disable_cloth_simulation` on the actor); leaders OK; saved |
| 13:31 | **Face A/B**: fixed face box [0.4486,0.4591,0.5866,0.7044] (her S16 mouth box) at f1270: round 4 final_d 119.2 (+0.51 stops, cast r 0.149); **r5 FINAL-quality still** (`r5/75-still.yaml`) 127.6 (+0.68, cast r 0.137) = +0.17 stops; the preview frame 20.1 (−4.15). **Cause: the preview preset (plus the collapsed cloth), not light/hair/skin**. Orchestrator: (b)-(d) not needed |
| 13:31 | Torso phase-lock (agent-01 207211f1): sync him, gaze, place, looks (all 4 on plan), **head (on-screen scope, turn blinks in — orchestrator ruling B): him blink_nod 1.553° at f1127-1139 (S15 turn out), locked 0.458 → FAIL**; her pass (0.0 / 0.265). Orchestrator: counter-pitch (agent-04 + agent-01), then report |
| 13:33 | **Orchestrator: no cloth sim on his tee this round** (closed shell; `garment.cloth_*` NOT_ATTEMPTED, signed). cloth.remove Host Tee; re-dress (a later step had dropped Tee/Trousers leaders again: leader_check + re-dress now runs before every render) |
| 13:35 | 1.7 re-run with agent-01's box search (97e88bbc): round 4 FAILS (him L2 +25.95; her L4b −18.91 render_mismatch); L1, L4a, L3a, L3b pass on round 4 (asked agent-01) |
| 13:37 | **Fit5 (#9) qa.clip pass 5: PASS, no issues**: neck_px 0, Body>tee 0.00067 (S17 f1368), Trousers>tee 0, wpo 0, **armor 0.109** (r4 0.538). `$G/gate_garment.json` written. `70-preview.yaml` switched to FINAL quality |
| 13:38-13:47 | **His previews** (final quality, `r5/70-preview.yaml` → `private/renders/r5/review/`): S13 f1000-1060, S15 f1080-1140, S17 f1320-1380 (153-164 s each). Her S16 f1270 final still → orchestrator: **PASS by eye** (face bright, overshirt intact, hair full) |
| 13:44 | **Orchestrator: S13 FAILS by eye: Fit5's collar floats** (a rolled cowl off his neck; the numbers passed). Fix: Epic's collar band kept, the neck backstop, a collar_gap/roll check (agent-02 f4300854) |
| 13:49 | His head after agent-01's vertical-axis turn (728c13f3): blink_locked 0.19 PASS; **blink_nod 1.41° at f1130-1133 still FAILS** (agent-04/agent-01 on it) |
| 13:55 | **Orchestrator: S15 preview looks WIDE, and the hem flares like a skirt.** probe_cam --check 13/13 OK (I had not run it before the previews: my miss). S15 camera = plan (85 mm). A single S15 still at f1100 matches round 4 (SSIM 0.837), but the S15 preview job's frames match nothing of round 4's S15 (0.18) and are closest to S17's wide (0.35): **cause not found**; render-side guard `shot.render_matches_r4` added (agent-09) |
| 14:00 | **Fit5 must-fail**: collar_gap 2.447 cm, collar_roll 6/6 (FAIL); hem_flare 1.02 (measured the hidden shorts: agent-02 bb736ccd) |
| 14:02-14:07 | Fit #10 (`--keep-regions collar`), Fit6 with a 15-frame drape (hem 6.6 cm: rejected), **Fit6 = out12** (no drape, keep collar, straight hem, waist 2.6 / hem 2.0) |
| 14:05:43 | Editor's last save. **Power cut on the fleet; the box was stopped at 14:10 by the orchestrator, restarted ~14:18** (disk intact; in-memory state after 14:05:43 lost). Kali /tmp also wiped: the driver profile was rebuilt |
| 14:10 | His trousers refit to Fit6 (r5_trousers.sh, scipy into Saved/r5_trousers/pylib --no-deps) had FINISHED (178 s) before the stop |
| 14:20 | Restart checklist: health, doctor (371 ops), install, ops.broken {}, FMCloth True, Studio open, no TRASH_, lock pass, probe_cam 13/13. agent-04's tilt probe (Host f1120-1160) |
| 14:21 | **Fit6 imported** (ease 1.831; waist 2.63, hem 2.10 p90 2.47, chest 1.71, sleeve 1.47, collar kept 743 v) + **SKM_Host_Trousers_R5**; dressed; `dress_him.py` dropped Tee/Trousers leaders → re-dress → leaders OK; saved |
| 14:23 | Backstop mask: `neck_backstop.py` line 63 used `get_mesh_per_vertex_uvs` (5.8.4: `get_mesh_per_vertex_u_vs`; patched in a copy). Mask: covered 1207, full_shrink 928, uv_valid, `neck_hidden.png` |
| 14:24 | qa.clip/look on Fit6 + Trousers R5 (before the backstop): collar_gap 5.47, roll 6/6, Trousers>tee 0.7 % (2.8 cm, S17/S18), neck 32 px. **Cause (agent-02, 868ef94e): `--morph-ref` bound/exported the tee on the REFERENCE person's skeleton**, so Unreal skinned it with the other person's joint offsets (Fit3-6's floating collar and trousers) |
| 14:30 | Head after agent-01's neck_01 guard (ddc8eaec): sync says "this face turns its head itself" (turn step skipped); blink_nod 1.41 still |
| 14:34 | Orchestrator (iv): Epic's own default garment, no WPO, + the backstop. Mask on Epic's tee (covered 1160); apply (C++-name fix 58bfebe2); `mh.add_item Outfits=WI_Host_DefaultGarment_Neck` + `mh.build` (102 s) + host_swap → **Host's Body/Face meshes and every groom EMPTY**. Cause (agent-02, 5.8.4 MetaHumanGeometryRemoval.cpp:45-52): MaxCullValue < 0 (the −0.01 "never cull") is rejected and the whole outfit assembly fails. Backstop OUT for tonight |
| 14:39 | **Recovered by rebuilding with the original `WI_DefaultGarment`** (105 s) + host_swap: Body, Face, all grooms, default garment back. groom.set (melanin 1.0, redness 0.08; Hair length 0.85), groom.lock, drive_faces, **look_check ok on every item**, saved. (No snapshot restore needed) |
| 14:50 | **Fit7 = out13, the refit on HIS skeleton** ("morph: the skeleton is HIS"): collar 1.22, waist 2.63, hem 2.10, chest 1.68, sleeve 1.47 |
| 14:57 | Post-respawn head chain: lips placed in sync for both; **his looks broke (S15 −38.4°, S17 −24.4°)**; head blink_nod 1.03 |
| 15:00 | **Fit7 + Trousers R5**: neck_px **0 without any backstop**, armor **0.006**, wpo 0, hem angle 6.1°; FAIL collar_gap 1.62 / roll 6/6 and Trousers>tee 0.6-0.7 % (≤ 2.8 cm) |
| 15:01 | **Fit7 + round 4's SKM_Host_Trousers_Op** (S17/S18): **Trousers>tee 0.0**, Body>tee 0.00034, neck 0. Saved as the state on disk. **Orchestrator: HOLD** (the tee won't pass gate + eye by 15:45): bank, wrap, power off |
| 15:03 | `perf.py calibrate --who him` (twice, drive_faces between): **turn_on 'Face', yaw_bone null**: his turn stays off after the respawn; open (agent-01) |
| 15:04-15:10 | **Her S16 1080p final** (r3/30-final, batch S16, warmup_engine 22, hair cvars) into `/srv/ue/reel/r5/final`: 120 frames, 377 s; SSIM vs round 4's same frames 0.83-0.89 (same camera). The signs file was restored from the 14:09 snapshot (same content: turn_on Face both; the bad copy kept as `.bad-1503`) |
| 15:10-15:16 | `perf.py restage --who him` (the Test_ staging was stale after the respawn) → sync → gaze → place: **looks all on plan again** (him S15 +0.6, S17 +0.8; her +0.2, +0.9); lips placed in sync both; head: her PASS (0.0 / 0.265), **him blink_nod 1.414° at f1130-1133 FAIL** (locked 0.19 passes). sync still skips the turn ("this face turns its head itself"), so the vertical-axis turn (ddc8eaec) was never exercised. Saved |
| 15:17-15:19 | assets.save_all + level.save (no dirty packages); editor stopped. **Synced to private/ (KMS), counts = local**: `renders/r5/box_r5` 2250 = 2250, `project/HostStudio` (with Saved/, minus Logs/Crashes/Intermediate/DDC) 4514 = 4514, `r5tree_end` 1763 = 1763, `renders/r5/final_d` (S16) 122 = 122; head-object aws:kms on final_d/1200.png, SKM_Host_Tee_Fit7.uasset, signs_Face_Archetype_Skeleton.json, gate_garment.json, .tree-rev. DDC → `private/ddc/5.8.4` (ddc-s3 set to the private prefix: face_data refuses a public one) |

## STATE AT END OF ROUND 5 (06 Nov, HOLD, ~15:30 UTC)

**Decision (orchestrator, 15:01): HOLD the finals for the next session.** No tee passed the gate and the eye by
21:15 IST. Everything is synced to private/ and the box is powered off (`film-ue down`).

### What is done and proved
- **Lips (T1), the operator's "no lip sync"**: round 4's faces were solved from the v1-script audio while the delivered
  mix plays v2 (the stems on disk were v1; the mix's own VO was gone). **Option D**: the v2 voice separated from the
  committed mix (demucs htdemucs), cut per line (`audio/vo_sep/`, voice.json provenance); cues from it pass at mix
  score 1.0 on all 6 lines (L1 1019.76, L2 1094.4, L3a 1157.76, L3b 1214.88, L4a 1350.0, L4b 1385.52). 6 mouth-only
  solves (AS_reel5_L1…L4b), composed per presenter: **in sync against each line's own solve at its mix place at every
  stage** (solve/face/final/placed; ref lag ≤ 0.8 f, r ≥ 0.97, silences ≤ 0.001). Render check (`lips render
  --reference`, activity-picked crop) **fails round 4's 65 s cut on all 6 lines** (worst |28.8| f).
- **Her (T2/T4)**: blink_nod 0.0, blink_locked 0.265 (round 4: 2.70 / 0.416); looks on plan; S16 final banked;
  orchestrator by eye: face, overshirt (round 4's, no cloth) and hair PASS at f1270. The hair lock (LODMode 0,
  Bias 1.0, persisted) passes; **S17 + S18 must render as ONE MRQ job** (the hair sim restarts on a new job: round 4's
  "short at 01:00" is that step, measured 2.6× the neighbours' frame difference).
- **His tee (T3a)**: the root causes of the floating collar and the trousers were found (the fit exported on the
  reference person's skeleton: agent-02 868ef94e). **Fit7** (`SKM_Host_Tee_Fit7`, his skeleton; collar 1.22 / chest
  1.68 / waist 2.63 / hem 2.10 / sleeve 1.47 cm) + round 4's **`SKM_Host_Trousers_Op`** is what he wears on disk:
  **neck_px 0 without any backstop, Trousers>tee 0, Body>tee 0.00034, armor 0.006 (round 4 0.538), wpo 0, hem angle
  6.1°**. Open: **collar_gap 1.62 cm, collar_roll 6/6** (line 0.8 / 0).
- Cameras: probe_cam 13/13; the render-side guard `shot.render_matches_r4` (SSIM vs round 4's frame) is in gate v2.

### Open (next session)
1. **His collar**: Fit8 = Fit7 with a tighter collar (agent-02: the band's ease vs the neck), re-measure collar_gap /
   roll; keep `SKM_Host_Trousers_Op`. Never WPO. The neck backstop is NOT needed with Fit7 (neck_px 0); if it ever
   is: MaxCullValue must be ≥ 0 (agent-02 6646f917), or the MetaHuman assembly comes out empty.
2. **His head**: blink_nod 1.41° at f1130-1133 (S15 turn-out); his turn goes through the face-curve path, so the
   vertical-axis fix is not exercised (agent-01/agent-04). After any respawn: `perf.py restage --who him` first.
3. **The S15 preview anomaly**: a 70-preview job of S15 f1080-1140 rendered a wide view (SSIM 0.18 vs round 4) while a
   single S15 still matched (0.84); not explained. Every render is now checked with `shot.render_matches_r4`.
4. Then: his S13/S15/S17 previews (final quality, `r5/70-preview.yaml`) → the orchestrator's eye → presenter finals
   S13, S15, **S17+S18 as one job** (S16 is banked) → final_check/final_qa → hair (cut_pop_ratio), heads, lips
   render (9.5) → cuts (captions from the vo_sep cues.json) → gate v2 (`--spec r5/gate_spec.json`; garment.cloth_*
   NOT_ATTEMPTED per the orchestrator) → the orchestrator's eye.
5. On a fresh kali: `lips.py cues` regenerates out/…/vo (deterministic from vo_sep); copy vo_sep L*.wav into vo/ for
   perf.py push; `lips.py push`, `perf.py push`.

### Where things are
- Box disk (root EBS) = the saved project; also `s3://…/ue-linux/private/project/HostStudio` (with Saved/, minus
  Logs/Crashes/Intermediate/DDC), `private/renders/r5/box_r5` (all of /srv/ue/reel/r5: probes, clip/look passes,
  stills, previews, S16 final), `private/r5tree_end` (the box tree), `private/renders/r5/review/` (the previews and the
  S16 still), the orchestrator's outage snapshots (`project_r5_snapshot`, `renders/r5/box_r5_snap`, `r5tree_snapshot`).
- Kali probes: `/tmp/fleet-agent-06-ue/r5/probes/` (also copied in part to the shared t1-probes folder).

## Round 5b (06 Nov, the finishing GPU session)

Box driver: agent-06. Orchestrator: cc-64d05f6e. Box i-0284d544cdf14905e as **gr6.4xlarge** (L4, 128 GB; no g6.4xlarge
capacity), up 16:08 UTC (orchestrator), self-terminate 20:10. Trees `cb3109b6` (film/host-studio 4b8f6463 +
r5-film-integrate d8d5b26e), driven from kali as in round 5 (branch `fleet/agent-06/r5b`).

| UTC | What |
|---|---|
| 16:10 | Trees → cb3109b6 (full archive to kali + `/srv/ue/r5tree`). doctor OK (5.8.4, Vulkan SM6, 371 ops, 163 GB free); `install` 157 files; `ops.broken` `{}`; FMCloth True |
| 16:12 | **Fit8 A** (collar ease 0.4) and **Fit8 B** (`--keep-regions collar --keep-ramp-cm 3`, collar out of blend) in Blender on the box in parallel (Fit7's args from out13's report). `garment-fit` must run ON the box (reads --src locally): `python3 -c 'from filmtools.unreal.cli import main' garment-fit …` from `/srv/ue/r5tree/tools` (no uv there) |
| 16:15 | Studio open: look_check ok (no fix), lock_check pass, Host wears SKM_Host_Tee_Fit7 + SKM_Host_Trousers_Op. **Leaders had dropped** (Tee/Trousers leader None after the editor start): mh.dress + dress_him → leaders OK (Body), saved |
| 16:17 | probe_cam --check **13/13 OK**; framing.py rc 0 (kept in kali `b/probe_check.txt`, `b/framing.txt`) |
| 16:18 | Fit8 A: rest in range (ease 1.749; **collar median 0.96**, p10 0.58 / p90 1.35; chest 1.68, waist 2.63, hem 2.10, sleeve 1.47); Fit8 B: ease 1.831, collar kept, collar@face 0 in every anim. **Both FAIL the static pose test only** (armpit/chest/sleeve 66-114 v ≤ 2.3 cm, the same set as Fit7, also `pass: false`). agent-02 + orchestrator: import both (round-5 deviation; qa.clip on the render is the judge) |
| 16:22 | Snapshot `/Game/Host/Snap/BP_Host_Op_r5b_preFit8` + on disk `/srv/ue/reel/r5/b/snap/BP_Host_Op.preFit8.uasset`. Imported **SKM_Host_Tee_Fit8B** (bounds 32.5/20.3/43.7) then **_Fit8A** (32.5/20.3/45.0); new assets, Fit7 untouched. Spare A2 (collar 0.0, min-ease 0.3 → out14A2) on CPU |
| 16:25 | **Fit8B gate: FAIL**: collar_gap 5.289, roll 6/6, **neck_px 77 (S15 f1128**; S13 1-7 px, S15 29-77 px at every frame), Face>tee 0.025, Trousers>tee 0, Body>tee 0.00046, armor 0.267, wpo 0, hem 6.1°. Dropped, no backstop (agent-02: the kept band stays in the export's space, not his skeleton: Fit6's 5.47 again) |
| 16:27 | **Fit8A gate: FAIL** collar_gap **1.616** (= Fit7 to the mm), roll 6/6; neck_px 0, Trousers>tee 0, Body>tee 0.00046, armor 0.237 (Fit7 read 0.006; agent-02: the ref-body capture, under the < 0.5 line), wpo 0, hem 6.1°. A2 (collar 0.0, min-ease 0.3) finished rc 1, not imported (superseded by A3) |
| 16:30 | Trees → 0a47c564 (r5-film-integrate 144024a5: gate_numbers.py, naturalize `--no-turn-blinks`); install 157, ops.broken {}. Head chain waits for agent-01's turn_by=bones (5e771ce9) |
| 16:35 | slotdiff Fit7 vs Fit8A: the 803-v innermost neck ring (all slot 0 Shirt) moved 0.006 cm median: the fit's "collar" region (n 291) is not the ring qa.garment_look measures. **Fit8A3** (`--slack 0 --passes 8`, other regions pinned at Fit7's medians): collar median 1.07 (looser than A), pose tests FAIL as before; imported as SKM_Host_Tee_Fit8A3 and gated |
| 16:31 | **Fit8A3 gate: FAIL**: collar_gap 1.733, roll 6/6, **neck_px 3 (S15 f1150)**, Body>tee 0.00021, Trousers>tee 0, armor 0.254, wpo 0, hem 6.2°. Host re-dressed in **Fit7** + Trousers_Op (leaders OK, saved) |
| 16:32 | **Orchestrator: preview S13/S15/S17 now in Fit7** (to judge the 1.62 cm / roll 6/6 collar by eye; his S15 head turn is the old one, known open) |
| 16:33-16:36 | S13 preview f1000-1059 (final quality, 161 s): probe_cam 13/13, framing ok, leaders OK, groom.lock pass before it. `film-ue apply` says "NOT converged: 60 frames left" although all 60 frames are written (frames = [A, B) end-exclusive): the runner now counts the PNGs instead (`b/post.sh` on the box: count → `gate_numbers ssim` (box `~/.local/bin/uv`) → mp4 with mix.wav at A/24 s → private/review, KMS) |
| 16:35 | Fit9 R1/R2 (agent-02 455c320f, `--neck-ring-cm 2 --collar-slack 0`): **"neck ring: 1 verts"** and `collar_slack None` in the report (not passed through) → R1 = R2, collar med 1.02; inner ring moved 0.066 cm. Stopped, not imported; back to agent-02 |
| 16:46 | Fit7 previews done (as above): render_matches_r4 S13 0.938, S15 0.766, S17 0.892 (line 0.5) → `private/renders/r5/review/S1{3,5,7}_f…_preview.mp4`. Fit9 R2 gate (fixed ring, 683 v, collar med 0.37): gap 0.637, roll 6/6, neck_px 5 (S15 f1150) |
| 16:48 | **Orchestrator: Fit7 FAILS by eye** (two dark ovals on his chest, a hood-like collar, a near-white tee): the Blender-fit tee is out for tonight. **Path (iv)**: MetaHuman's own default garment, WPO 0, + the neck backstop (6646f917) in ONE add_item + ONE build; Fit9 skipped |
| 16:49 | Snapshots `/Game/Host/Snap/{BP_Host_Op,Host_Op}_snap_r5b` + `.uasset` copies (`/srv/ue/reel/r5/b/snap2`). The 14:34 mask (Epic's tee, covered 1160) had **79,431 px at 0** (MaxCull 0 would CULL them): floored to 1/255 as 6646f917 draws it (original `neck_hidden.r5-1435.png`). apply read_back: max_cull 0.0, min_keep 0.9, shrink 1.5 |
| 16:50-16:53 | `mh.add_item Outfits=WI_Host_DefaultGarment_Neck` + `mh.build` (129 s, ok); **the editor CRASHED in host_swap** (texture streaming on a stale skinned asset: `KnownSkinnedAsset == CurrentSkinnedAsset` ensure, then an Array index assert). After the restart: BP has Body, Face, Host_Op_Outfits, grooms Hair/Eyebrows/Fuzz/Eyelashes/Mustache (Beard none); the stale Fit9R2 `Tee` component removed; the default garment's Shirt slots were still `M_FM_Hidden` (old hide_slots) → set back to the assembled MI; host_swap (INFLATE 0, op colour), leaders pass |
| 16:58 | `perf.py calibrate --who him` (turn_by=bones, b2356cf0): **"no local axis of Body.head turns Host's head"** (every Body bone axis ~2.3-3.0° pitch, ~0 yaw). The Face IS led (Face/Body head + neck_01 equal to 0.001 cm at f1170; same setup as hers). agent-01/04: curve path |
| 17:05 | **Garment gate (iv)**: collar gap 0.15-0.20 at f1000-1397 (5.289 at f960 = one stray rim vert, fixed by agent-02 923d8b6a), roll 6/6 (band spread), wpo 0, Body>tee 7e-05, Trousers>tee 0, armor 0.329, hem 7.8°; **neck_px 296 (S15 f1128)**. **Cause: the 16:52 build was never saved** (crash): BP_Host_Op, the face mesh and Host_Op_Outfits on disk are 15:17's; only Host_Op (character, with the Neck WI) saved at 16:53 → no shrink live |
| 17:06-17:12 | `film-ue op perf.calibrate label=Host turn_by=auto`: turn_on Face, yaw_gain 1.0, **turn_strength 1.041** (round 5: ~0.34), fresh yaw_table (old file `.r5`). naturalize `--no-turn-blinks` → restage → sync → gaze → place: **looks pass** (him S15 +0.6, S17 +0.8; her +0.2, +1.0); **head: him blink_nod 0.0, blink_locked 0.084, head_buzz 0.047 flagged**; her 0.0 / 0.265; lips placed in sync. dress_him, leaders, lock, saved |
| 17:13 | Orchestrator: render S13/S15/S17 previews AS-IS (judge all but the neck); neck fix in parallel (agent-02 50f8566a: RAMP 1, EDGE_W 0.3, REACH 5, SHRINK 3.0; build, save the assets BEFORE level work) |
| 17:13-17:24 | **(iv) previews AS-IS** (`…/review/S1{3,5,7}_f…_preview_iv.mp4`; render_matches_r4 S13 0.972, S15 0.798, S17 0.978). **Orchestrator: PASS by eye except the small patch at the left of his neckline** (charcoal cotton crew-neck, collar right, no armour/flare; hair, mustache, her good) |
| 17:23 | Neck fix (agent-02 50f8566a): mask TEE='SkeletalMesh' RAMP 1.0 EDGE_W 0.3 REACH 5 → covered 1160, edge 89, full_shrink 1049; apply SHRINK 3.0 (read_back ok). **mh.build SKIPPED** ("changed": false: it thinks the BP is up to date) → `mh.build force=true` 128 s; `assets.save folder=/Game/Host` BEFORE any level step, level.open, host_swap: **no crash** this time |
| 17:27-17:35 | shrink_live by_surface (agent-02 52f502d8): **LIVE**, 1129 face verts moved > 0.5 cm, max 2.99, z 143.9-153.2 (by index: the build reorders the face's verts). Restage → sync → gaze → place → looks (unchanged) → head (unchanged) → lips in sync → dress_him, lock, save. **Editor neck pass: neck_px 296 → 9**: S13/S17/S18 0; S15 4-9 px ≤ 0.91 cm at f1082/1128/1175/1198 (the collar edge, where EDGE_W 0.3 × 3 cm = 0.9 cm). Collar: agent-02's 923d8b6a misreads the band (2.6, n ~185); the real reading is 0.15-0.20 |
| 17:35 | 8 set shots (f0000-0959) copied from `r3/final_d` into `r5/final` (1080 frames with S16) |
| 17:40 | Neck loop 2 (agent-02): EDGE_W 0.7, REACH 6.0, SHRINK 3.0, RAMP 1.0 → build force → save → reopen → swap → restage chain → pass |
| 17:44-17:46 | Neck loop 2 (EDGE_W 0.7, REACH 6): **neck_px 3** (S15 f1150 1, f1152 3, f1175 3 px ≤ 0.5 cm); S13/S17/S18 0. S15 preview (whole shot, loop 2) + 400 % crops → orchestrator: no skin through by eye |
| 17:56-18:04 | Loop 3 (DILATE 1.5/0.3): **worse**, neck_px 19 (the shrunk visible skin above the line loses its rim columns). Loop 2's mask kept (`neck_hidden.loop2.png`) |
| 17:55 | **Orchestrator: her GREY PATCH** on her white top (S15 f1166-1199). Editor-side stills could not isolate it: `75-still.yaml` loads Studio from disk and the sequence drives visibility, so editor visibility / hidden-in-game toggles (and later a saved-level toggle) never reach the render (pixel-identical outputs). Her `SKM_Presenter_Overshirt` was 127.7 MB (round 5's cloth data still inside) vs 32.3 MB in `project_r4_snapshot` |
| 18:08 | Restore window: level saved, `film-ue editor stop`, round-4 overshirt asset copied in (r5 copy kept at `/srv/ue/reel/r5/b/snap4`), loop 2's mask back, editor start, lock, her leaders; cloth.describe: Overshirt clothing [] (was Cloth_Overshirt), all skinned_only. His loop-2 build + re-dress + head chain: neck_px 3 reproduced |
| 18:09-18:23 | Loop 4 (agent-02 mask_seams, CPU): 83 neck verts split across UV seams (confirmed), but redraw/pad/consistent/scale 4 either left 12-13 split or shrank 934-1494 visible verts: NO-GO. S15 goes with loop 2 |
| 18:20-18:51 | **Finals** (r3/30-final, out `/srv/ue/reel/r5/final`, probe 13/13 + framing + leaders + groom.lock/lock_check before each job): S16 re-render 389 s, S13 301 s, S15 407 s (warmup_engine 64), **S17+S18 ONE job** 703 s. Trap: S16's `overwrite=true` DELETED every other frame in final/ (the copied set shots): **tool item: a final render must never delete frames outside its range**; set shots + V01's 12 handle frames re-copied from r3/final_d (1584 frames = round 4's) |
| 18:44 | S15 final neck crops (fixed box, nearest x4) r5 vs r4 → orchestrator: no skin through, BUT a ragged lip + dark crevice at the neck's lower edge in his sharp frames (f1085/1100/1128); S13 too (a see-through gap at the collar opening). S15/S13 do not pass as rendered |
| 18:52-19:10 | Post-finals on the box CPU (`b/postfinals_box.sh`): the box needs its own film-ue config for editor-driven tools (`/srv/ue/reel/r5/b/conf/film-ue.json`, `transport: local`). final_qa with the cut PASS; shot.cameras_ok 1 (13/13); render_matches_r4 0.806; hair: cut_pop_ratio **1.372** (round 4 2.57; S17+S18 as one job fixed the 01:00 pop), cut_reach 1.96, pop_reach 8.93 (editor S15 f1082, pre-existing start tilt, ruled not a blocker); settle S15 12.3 = round 4's 13.8 (her start tilt-in is pre-existing; agent-04's place fix b22f3372 removes it). **Candidate cuts** 65 s + 45 s (captions on the vo_sep cues) → `private/renders/r5/review/candidate_unsigned/` (UNSIGNED) |
| 18:53 | Open-edge check (b07e8fd1): **shrunk_on_open_edge 92/92**: the shrink pulls the face mesh's open lower edge off the body = the tear. Loop 5 (BOUND 2.0, RAMP 2.5, EDGE_W 0) and 5b (new texture name) builds ran but the face = loop 2 (1133 moved, z 144); mask_diff: the loop-5 PNG ≈ loop 2 (BOUND not in the PNG) |
| 19:10 | Garment re-run with the collar roll fix (main b8631197) and silhouette vs round 4's `r4/clip/Host_after`: silhouette_pct 2.66, collar gap 2.2-2.4 on every frame, roll 6/6: the 3 cm shrink pulls the neck ~2.3 cm off the collar (orchestrator) |
| 19:24-19:38 | **Loop 6** (agent-02 mask RAMP 1, EDGE_W 0, BOUND 2.0 + the orchestrator's SHRINK 1.2, texture T_Host_NeckHidden6): the build took (shrink_live max 1.195, lowest z 144.6) but **neck_px 113** (S15 f1128; S15 37-113 px ≤ 1.39 cm; S13/S17/S18 0), collar gap 1.21-1.38, roll 6/6. **Neck HOLD for round 6** (the root fix is the fit) |
| 19:16-19:20 | Lips render on the candidate cut (box, agent-01's steps): **all 6 lines fail** (him L1 +14.6, L2 +3.9, L4a +12.3; her L3a −7.6, L3b +3.3, L4b −15.5 f), and the round-4 control fails too (L1 +6.6, L2 +17.0, L4a +12.4); curve gate items pass (lag 0.8, track_r 0.972, silence 0.001). The orchestrator's eye: onsets 0-2 f. With agent-01 |
| 19:13 | Her asset diff vs round 4 (size): only Studio.umap and SEQ_Reel differ; every mesh/material/physics/clothing asset of hers = round 4. **Her grey patch persists in the candidate (S17 f1350, both sides of her chest)**: render-side batch (sequence visibility keys) at S17 f1350 |

### Gate v2 at the end of round 5b (agent-09): the candidate REFUSES; its failing rows are round 6's start list

The candidate (loop-2 finals in `/srv/ue/reel/r5/final`, cuts in `private/renders/r5/review/candidate_unsigned/`) is
**UNSIGNED**: gate v2 (`r5/gate_spec.json`) REFUSES it. Numbers come from the box's post-finals and the garment re-run at
19:10 (main b8631197 + film 3aa77b73). No waiver is written on any row, and none is possible: lips, head, garment and
hair are complaint areas.

**FAIL (round 6 starts here)**

| item | value | line | where | cause / round-6 work |
|---|---|---|---|---|
| garment.neck_px | 3 px | 0 | S15 f1152/f1175 (soft frames; his sharp frames read 0) | Epic's collar does not fit HIS neck. The backstop trades poke for gap: SHRINK 3.0 tears the face's open lower edge (shrunk_on_open_edge 92/92) and leaves a 2.3 cm gap; SHRINK 1.2 pokes 113 px. Fit the collar to his neck (agent-02, r5/garment.md); backstop only as a ≤ 0.5 cm safety. The S15 sharp/soft split draft was never committed |
| garment.collar_gap_cm | 2.2-2.4 | 0.8 | every frame | the same: the shrink pulls the visible neck ~2.3 cm off the collar (orchestrator, by eye in the S13 crops: a dark ring and a see-through gap) |
| garment.collar_roll | 6/6 | 0 | every frame | the same band; re-read after the fit |
| garment.silhouette_pct | 2.66 % | 2.0 | vs round 4's `r4/clip/Host_after` | WORSE than round 4 (2.23) on the same garment. Re-measure after the fit |
| lips.render_lag_frames | worst 15.5 f | 1 | all 6 lines (him L1 +14.6, L2 +3.9, L4a +12.3; her L3a −7.6, L3b +3.3, L4b −15.5) | **the render lip measure is invalid** (agent-01): the round-4 control fails too (L1 +6.64, L2 +16.95, L4a +12.38); the scatter is random in sign while every curve item passes (lag 0.8 f, track_r 0.97, silences 0.001) and the orchestrator's eye reads onsets 0-2 f on L1, L2, L4; not repeatable (round 4 L1 −1.36 → +6.64 with new boxes); the 6 f "sensitive" control is tautological for any cross-correlation. Round 6 (agent-01, r5/lipsync.md on `fleet/agent-01/r5b-head`): a landmark-based mouth opening (mediapipe) vs the reference curves, with a real null control, validated on round 4 L1 (~−17 f) and a +6 f shifted mux before it gates |
| hair.pop_reach_pct | 8.93 % | 8 | S15 f1082 (editor) | her start tilt-in f1080-1083, the same in round 4 (start motion 13.8 vs 12.3). Cause: `place()` cross-fades idle→baked on screen; fix on `fleet/agent-04/r5b-film-settle` (b475dfe5, b22f3372), NOT rendered (S15 was not re-rendered once the neck held). The conditional exclusion (`hair_pop_exclude`) was not committed: the fix makes it unnecessary |

**PASS**: head.blink_nod_deg (him 0.316, her 0.0; line 0.6), head.blink_locked_deg (0.265; 0.3), garment.wpo_cm 0,
garment.armor_index 0.329 (0.5), garment.pair_fraction 7e-05 (0.001), garment.hem_flare_ratio 0.557 (1.15),
shot.cameras_ok 1 (13/13), shot.render_matches_r4 0.806 (0.5; S15 f1152), hair.lock 1, hair.render_cvars 1,
hair.cut_reach_pct 1.96 (12; every cut she is on screen, editor groom-only), **hair.cut_pop_ratio 1.372** (1.8; round 4
2.57: S17+S18 as ONE job fixed the operator's "short at 01:00"), the lips curve items. final_qa with the cut: PASS.

**NOT ATTEMPTED** (the orchestrator's ruling): garment.cloth_alive / cloth_sound / cloth_detail_ratio.
**INFO**: garment.silhouette_ratio 2.30 (an untrusted capture), shot.start_motion_ratio 12.33 (round 4 13.81).

**Open at the end of round 5b, besides the table**: her grey patches on the white top (S17 f1350, both sides of her
chest; S15). They are NOT her assets (all = round 4 by size); the render-side batch at S17 f1350 (H0 / overshirt hidden /
hair hidden / hair shadow off / lock released) decides between garment geometry and her full-count hair.

**What the gate learned this session (tools, all on r5-film-integrate)**

- Four items had no producer, so the sign would have refused them as "not measured": `r5/gate_numbers.py` writes
  shot.cameras_ok, shot.render_matches_r4, hair.lock and hair.render_cvars (ba43f60b).
- The pixel cut pop ran on EVERY cut, so camera changes read as pops: it now reads only held-camera cuts (`pop_cuts`,
  854b0d71).
- The night luma matte read cut_reach 156.5 % without flagging saturation: night renders feed only the pixel pop
  (`--qa-pop`, 51a36628), and the editor's groom-only reach stands.
- neck_px cannot see a torn skin edge ABOVE the collar (the orchestrator's eye did). Whole-crop SSIM vs round 4 did not
  separate it either (ragged 0.835-0.871 vs clean 0.839-0.863), so it is not proposed as a line. Round 6 needs a
  neckline-edge measure, or the eye stays the only judge of the tear.
- The settle measure on a large box moved the same in round 4 and round 5, so it is a diagnostic (INFO), never a line.
