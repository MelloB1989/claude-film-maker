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
