# Explainer gate log (round 6, agent-09)

The spec is `gate_spec.json` and the method is `QA.md`. Every verdict goes here when it is run. The rulings below are
the orchestrator's (cc-64d05f6e), 07 Nov 2026. Each is a scope change or a measure fix, never a waiver.

## Rulings

| ruling | what it changes |
|---|---|
| captions | Every VO line is captioned, over the graphics too, in one band at the bottom 15%. The graphics keep that band clear (`gfx.caption_band_clear`). |
| facts | W06 ("two million") is kept and sourced (WhatsApp's 2012 engineering blog). W17 is softened to "over a hundred billion" (agent-11). |
| INFO for the explainers | `garment.silhouette_pct` and `shot.render_matches_r4`: there is no seated or round-4 reference for these films. |
| cloth NOT ATTEMPTED | His tee is Epic's default garment and her top stays skinned. |
| lips | `lips.render_lag_frames` and `render_conclusive` are INFO: the render measure is invalid. `lips.eye_onsets` is the orchestrator's signed strip. `lead_in_cm` uses the silence-proper window (agent-01, the approved 2.5 f anticipation); the short-gap lines are covered by the silence rows and `eye_onsets`. |
| netflix occlusions | clip_r7 was the overshirt run. V2 (no overshirt) uses `r6b_v2_clip` as its baseline: the forearm and hands sit in front of the top, so they count as occlusions, and later runs are judged against it + 0.01. |
| leaders | `garment.leaders_ok` is a hard pre-render row on every final job (the r6n0 lesson). |
| streaming | `shot.streaming_settled`: warm-up in the render spec and a clean first frame. This came from the CU f1300 tile blocks. |
| grain, close shots | `shot.grain_sigma` ≤ 1.0 (Immerkaer sigma on wall + neck, by projection). f300 (3.10) and MCU_1330 (14.55) fail it; the finals-spec MCU test f29 (0.69) passes. |
| grain, WIDE | `shot.grain_wide_sigma` ≤ 0.8 on flat patches only (wall + a second plaster patch). f300's wall (1.002) fails it; netflix V2 shot 11 (0.55) passes. The WIDE neck and desk patches are INFO (texture at that scale). Evidence: the orchestrator's 1:1 look at shot 11 f1100. |
| his move to box B | `garment.head_state_parity`: agent-06's `him_state` manifest (sha256), and cull_live reading 912 culled verts at z 144.2-153.3, as on box A. |

## Her neckline strip (netflix V2)

The orchestrator ruled on 07 Nov, about 23:10 IST.

- **The defect:** a dark grey strip, about 10 px wide, ran down the inside of her scoop neckline on her left (test30
  MCU f29, x about 1040-1075, y about 600-830 at 1080p). It read as a strap.
- **The cause:** the rim key light's shadow from her own Top onto her skin at the edge (agent-02's diagnosis, key-shadow
  ON/OFF). It was not the texture and not the geometry. Edge1N did not help, so no asset change ships; her original Top
  asset is restored.
- **The fix:** `Top.cast_shadow` OFF, set through setplan + set.py so it is reproducible. Recorded in r5/garment.md:
  rim key-shadow, so turn Top.cast_shadow off for tight tops.
- **The strip measure:** 0.884 with p10 188 after the fix, against 0.717 with p10 77 as rendered.
- **The evidence:** the orchestrator compared it against test30 at 1:1. The band becomes a soft light-grey inner edge
  that reads as real fabric. The rest of the torso is identical: knit, under-bust shading, sleeve hems, chair.
- **WIDE shot 11:** stays as rendered, because the band cannot be seen at WIDE scale. If it is ever re-rendered, check
  her shadow on the chair and desk.

## Verdicts

### Netflix v2b: SIGN (07 Nov, about 23:45 IST)

- **Command:** `gate_film.py --film netflix numbers/netflix/*.json --out numbers/netflix/verdict.json`.
- **Result:** 55 PASS, 9 INFO (each by a ruling, reason in the row), 3 NOT ATTEMPTED (cloth), 0 FAIL, 0 WAIVED.
- **Sources:** box B (agent-07, `fleet/agent-07/r6-boxb`), head (agent-04 7266f001), cut v2b (agent-11), graphics band
  (agent-12, film/explain-netflix), the orchestrator's eye strip and eye_onsets.
- **Delivered:** the orchestrator delivered v2b to the operator at 23:29.

| area | result |
|---|---|
| lips | lag 0.77 f, track 0.897, onset 77 ms, silences, cues fresh; eye_onsets 6/6 lines 1.1-1.9 f lead |
| head | blink nod 0.048 / locked 0.103, buzz 0.031, drift 1.03, frozen 0.33 s, nods 8.8/min, blinks 19.3/min, on lens 0.915, saccades 1.41/s, glances 5.3/min |
| body | breath 14.1/min, 2.71 mm; desk, mic and knee contact 0 |
| garment | visible neck poke 0, wpo 0, armor 0.0, hem 0.955, excess over the V2 baseline 0, leaders 1 on every job |
| set | chair/desk 0 px, the mic never on the mouth (0), props overlap 0 (depth-confirmed) |
| shot | cameras 1, streaming 1, grain close 0.742 / WIDE 0.552 |
| exposure | static background patch, all 9 shots: jump 0.007, drift 0.023 |
| hair | lock 1, render cvars 1, cut reach 2.68 %, pop reach 0.0 % |
| cut v2b | -14.0 LUFS / -1.7 dBTP, 1920x1080, 59.46 s, captions 144/144 with onset 84 ms, facts sourced, qc 1, caption band 1 |
| eye | real_person, light, hair_garment and graphics all 1 |

**Scope notes:**

- **Exposure is read on a STATIC background patch (agent-09's change).** The face box measured her shading as she turns
  against the key (fixed box 0.17 / 0.27, tracked worse). Exposure is locked manual in the render spec.
- **The exposure value now covers all 9 shots.** The 3 CUs (02, 07, 14) are read on a static out-of-focus background
  region: 0.005 / 0.023, 0.005 / 0.016 and 0.005 / 0.011. The worst over every shot is jump 0.007, drift 0.023. The
  orchestrator accepted the scope.
- **Spec bug fixed before the run:** an override had dropped `set.props_overlap`'s line. A test now catches any spec
  item without a line.



- *(history)* **Netflix v2** (box B, agent-07): all 9 shots rendered, the guard OK on every job.
  - Cut rows: -14.0 LUFS / -1.7 dBTP, format 1, 59.46 s, captions 144/144 words, onset 84 ms, facts 1, qc 1.
  - The orchestrator's frame-wise watch: picture, lips (~1.7 f lead), hair at the cuts, neckline, grain and mix all
    PASS.
  - ONE fix, composite only (agent-11): the captions over her white top are too faint. The fix is a black backing
    plate at about 45 % alpha behind every caption, dimmed upcoming words at >= 70 % opacity, the same position and
    size, and the 56.08 s audio cut fixed. That makes v2b. The cut rows are re-run on v2b.
  - Still to come from box B: grain per job, clip vs r6b_v2_clip, exposure (tracked boxes), box.json.
- **WhatsApp:** not started. The head-state pull to box B comes first.
