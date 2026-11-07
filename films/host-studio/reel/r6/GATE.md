# Round 6 karma gate (agent-09)

**SIGN** at 07 Nov 2026, about 20:40 IST, for his r6 finals (box A: S13, S15 with warm-up 64, S17+S18 as one job;
S16 and the set shots stay) and the 65 s + 45 s cuts under `private/renders/r6/review/karma/cut/`.

- **Spec:** `gate_spec.json`.
- **Numbers:** `numbers/`:

  | file | source |
  |---|---|
  | `box.json` | agent-06, `fleet/agent-06/r6-boxa` 228c108f |
  | `garment.json` | agent-02, `fleet/agent-02/r6-neck` 4dcb8113 (final: INFO rows carry null + the reason; measured values in `*_info` rows: collar gap 3.562, roll 3, silhouette 31.73) |
  | `lips.json` | agent-01's `lips_numbers.py`, run by agent-06 |
  | `head.json` | agent-04 |
  | `eye_onsets.json` | the orchestrator's signed strip |

- **Verdict:** `numbers/verdict.json`: 27 PASS, 12 INFO, 3 NOT ATTEMPTED, nothing FAIL or WAIVED.

```
film-qa gate numbers/box.json numbers/garment.json numbers/lips.json numbers/head.json numbers/eye_onsets.json \
  --spec films/host-studio/reel/r6/gate_spec.json --out numbers/verdict.json
```

## What passed (the operator's complaints first)

- **His neck ("weird, looks like it has a cut"):**
  - `garment.neck_px` 0 on the VISIBLE measure (skin islands plus tongues over 3 cm, seen pixels only). It must fail
    r6n1's blob, which reads 39.
  - `open_edge_shrunk` 0: the backstop shrink is off.
  - The cull moved no kept vertex (0.0 cm). Every culled vertex sits at least 1.5 cm under the collar.
  - `leaders_ok` 1 on all 3 final jobs.
  - Face luma is 0.967-1.035 of round 4, measured on per-image face boxes. The r6n0 dark face read 0.119.
- **Lips:**
  - Lag 0.8 f, track_r 0.972, onset lead 10 ms.
  - The silences read 0.001 and 0.0 (open and busy).
  - The cues are fresh.
  - The orchestrator's eye on the rendered cut: every visible line has a 1-2 f lead. L3a is hidden by her hair.
- **Head:** blink nod 0.466 deg (line 0.6), locked 0.128 deg (line 0.3).
- **Hair:**
  - Cut pop 1.304 at S17 to S18 (the operator's 01:00). Round 4 read 2.57.
  - Pop reach 1.61, which includes S15 f1082, the r5b fail at 8.93, now fixed by agent-04's place fix.
  - Cut reach 3.47. Lock and render cvars both 1.
- **Shot:** cameras 13/13, render matches round 4 at 0.81, final_qa with the cut passes.
- **Garment bulk:** armor 0.317, wpo 0, pair fraction 0, hem flare 0.551.

## INFO and NOT ATTEMPTED, each by the orchestrator's ruling (scope changes, not waivers)

| item | value | reason (cc-64d05f6e, 07 Nov) |
|---|---|---|
| lips.render_lag_frames, render_conclusive | not run | the render lip measure is invalid: in r5b the round-4 control also failed, with random sign |
| lips.lead_in_cm | not measurable | the editor lip-bone readers see a frozen face on SEQ_Reel (round-7 tool item). Covered by the silence rows on the same curves and by the eye on the cut |
| garment.collar_gap_cm, collar_roll | 1.514 cm / 3 (whole band, pre-fix) | the measure is unvalidated on Epic's default tee with a face cull: three iterations disagreed (0.29-3.56 cm) (round-7 tool item). The orchestrator's eye on the finals' 1:1 crops judged the collar natural from every camera |
| garment.silhouette_pct | +31.73 | the reference is round 4's different performance (pose). Same garment; armor is the bulk guard |
| garment.neck_rim_px | 289 | the old rim count, kept so the re-scope is visible |
| garment.silhouette_ratio, shot.start_motion_ratio, shot.settle_step_deg | 2.30 / 3.36 / 0.253 | diagnostics |
| garment.cloth_* | not attempted | his tee is Epic's closed-shell default garment, so no sim (rounds 5 and 6) |

## Measure fixes this round (on main, each with its must-fail)

| measure | commit | must-fail |
|---|---|---|
| neck_visible | agent-02 e71f06fa/a7511df9 | r6n1's blob, 39 px |
| collar roll, wall verts only | agent-02 f41af577 | Fit5, rolled lip, fold |
| lipsync onset bounded by the previous line | agent-01 341ae3c2 | |
| qa.clip props + mouth | agent-09 0ce1c3ae | |
| gate `range` op | agent-09 0b3bbf5c | |

The camera-facing and per-sector collar work (agent-02 b454f979, 8bc9bc3b) is merged on `fleet/agent-09/r6-integrate`
but NOT asked for main: it did not validate on the box, which is the round-7 item.

## Round-7 tool items

- The editor lip-bone readers are frozen on SEQ_Reel's rig.
- The collar gap/roll measure needs validating against the eye on known collars.
- The silhouette reference must match the pose: same performance, the previous accepted garment state.
- face_luma: some frames fell back to the projected face box (`all_detected` false).
