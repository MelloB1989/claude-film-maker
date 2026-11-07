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

- **Netflix V2:** shot 11 (WIDE) passes grain. The neckline is fixed (`Top.cast_shadow` off), so her 8 close shots are
  rendering. The full gate runs on composite v2.
- **WhatsApp:** not started. The head-state pull to box B comes first.
