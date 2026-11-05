# Round 3 renders (Linux GPU box, UE 5.8.4): plan and settings

Owner: agent-05 (render plan and quality). Runs: agent-07, the only editor driver, with `film-ue apply`.
The 13 shots of `/Game/Reel/SEQ_Reel` (shots.py), 1560 frames at 24 fps, **16:9 1920x1080 only** (no 9:16, no
4K unless the operator asks: then `preset: 4k`, the same files). Everything is rendered on Linux; nothing from v2's
Windows renders is reused.

## Order (the GPU never idles: queue the next step before one ends)

| # | What | File | Frames | When |
|---|---|---|---|---|
| 1 | Preview of the whole reel (960x540, 1 sample, JPG) | `10-preview.yaml` | 1560 | after every rebuild of SEQ_Reel; agent-09 reviews it, agent-06 roughs the cut |
| 2 | Calibration A/B: TSR x 8 vs no AA 2 spatial x 8, 24 frames of S17 (two presenters, strand hair) | `20-calibrate.yaml` (twice) | 2 x 24 | once, before finals; I pick the AA and set it in `30-final.yaml` |
| 3 | Finals, set shots V01-V05, S11, S12, N01 (no presenters: independent of the MetaHuman and the performances) | `30-final.yaml` | 960 | right after 2 |
| 4 | Finals, presenter shots S13, S15, S16, S17, S18, one at a time as each is approved (performance, his MetaHuman, her watch/collar/hair, framing) | `30-final.yaml --set batch=S13 --set 'shots=["Reel_S13"]'` | 120 each | as they land |
| 5 | A shot that changed after its final | `... --set overwrite=true` | 120 | as needed |

Frames: `/srv/ue/reel/r3/<preview|final|cal_A|cal_B>/<master frame:04d>.png` (S13 is 0960..1079), a report per
job in `_render/<name>.report.json` (time per frame, VRAM peak, missing frames), and the sequence's WAV. agent-06
pulls them with `film-ue pull`.

## Settings (and why)

- `preset: final`: 8 temporal samples (motion blur through the cameras' shutter, the sub-frame motion that keeps the
  faces from strobing), 32 warm-up frames per shot (TSR/Lumen history), the film-quality cvars (`QUALITY_CVARS`:
  Lumen, VSM SMRT shadows, hair MSAA 8, DOF and motion blur quality 4) and `r.HairStrands.SkyLighting 0`.
- Plus full-resolution skin subsurface (`r.SSS.Quality 1`, `r.SSS.HalfRes 0`): round 3 is about the faces.
- One MRQ job per shot (`chunking: shot`), each from its shot's first frame; a chunk that resumes mid-shot is
  pre-rolled from the shot start (`preroll: cut`) so cloth and hair arrive as in a full-shot render.
- Resume is on: a re-run after a crash or a cancel renders only the missing frames. `overwrite` only for a changed
  shot.
- PIE executor (DECISIONS, day 1). MRQ's game overrides force cinematic scalability and LOD 0 for meshes; the hair
  pop at 0:39-0:40 of v2 is agent-09's (groom LOD/sim/binding): if it needs a render cvar, it goes in `cvars` here.

## Time

The core's cost model says ~14 min for the set shots and ~8 min for the presenter shots, but it is calibrated on
simple scenes: MetaHumans with strand hair and Lumen at film quality were 8-15 s a frame at 4K on Windows (PLAN.md
section 5), so expect roughly 2-4 s a frame at 1080p, i.e. ~1-2 h for all 1560 frames. Step 2's reports replace the
guess; I post the measured numbers.
