# Round 5 (06 Nov, Linux GPU box): log and state

Box driver: agent-06. Orchestrator: cc-64d05f6e. Plan: [r5/PLAN.md](r5/PLAN.md). Times UTC (IST = UTC+5:30).
Box i-0284d544cdf14905e (g6.4xlarge, L4), up 11:28 (orchestrator), TTL shutdown 17:29. /srv/ue on the root EBS (intact).
Box tree `/srv/ue/r5tree` (r3tree kept as round 4 left it); outputs under `/srv/ue/reel/r5/{garment,cloth,hair,qa,final}`.
Driven from kali: `/tmp/fleet-agent-06-ue/r5/fu film-ue …` (FILM_UE_CONF_DIR `/tmp/fleet-agent-06-ue/r5/conf`,
face_data=yes, local port 18806); the kali tree is this branch (`fleet/agent-06/r5-drive`), pulled from
`fleet/agent-10/r5-film-integrate`. Probe JSON on kali under `/tmp/fleet-agent-06-ue/r5/probes/` (copied to `$Q`).

## Log

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
| 11:55 | **agent-01: the VO stems ≠ the delivered mix.** mix.wav has L1 ~f1021-1044, L2 ~f1097; the stems put L1 ~14 f early: the operator's 0.7 s. **Orchestrator decision: the delivered mix is canonical**; each line WAV is located in mix.wav by cross-correlation and those offsets are the cues; L3 split by VAD (or solved whole). agent-01 adds a stem-vs-mix check (must fail round 4's stems). **Phase 4 on hold until then** |
| 11:58 | 0.7 partly: only L1/L2/L3/L4a/L4b.wav exist (no L3a/L3b), so `perf.py push` and `lips.py push` stop on L3a.wav. vo_him/vo_her/cues.json pushed by hand. `perf.py calibrate` waits for agent-01's cues fix |
| 12:00 | **1.1** groom.lock_check: `pass: false`; LODMode 1.0, AutoLOD.Bias 0.1; LODSync forced_lod 0, Hair `listed: true`, live_lod 0, all groups STRANDS, no group error. Host Hair length_scale 0.85. As expected |
| 12:03 | **1.4** perf.check her_face: fails blink_nod 0.25 (0.2), blink_locked 0.306 (0.3); head_buzz 0.057 ok; 12 blinks. **Per-blink nods are positive** (t2.76 +0.37, t8.06 +1.49, t12.56 +0.53, t13.26 +0.68), not PLAN's −0.8…−1.6. her_solve: fails gaze_shifts, blink_nod 0.5; blink_locked 0.219 (passes); 2 blinks |
| 12:05 | **1.5 DEVIATION**: `perf.py head` rc 1 only on his head_buzz (yaw 0.348° RMS, spikes from 10.25 s). blink_source curves, but **blinks = [] for both** (her closure samples reach 0.995), gate head.blink_nod_deg 0.0 "no blinks measured". The gate head check does not fail round 4: head gate work stopped, sent to agent-04 |
