# Round 3 renders (Linux GPU box, UE 5.8.4): plan and settings

Owner: agent-05 (render plan and quality). Runs: agent-07, the only editor driver, with `film-ue apply`.
The 13 shots of `/Game/Reel/SEQ_Reel` (shots.py), 1560 frames at 24 fps, **16:9 1920x1080 only** (no 9:16, no
4K unless the operator asks: then `preset: 4k`, the same files). Everything is rendered on Linux; nothing from v2's
Windows renders is reused.

## Order (the GPU never idles: queue the next step before one ends)

| # | What | File | Frames | When |
|---|---|---|---|---|
| 1 | Preview of the whole reel (960x540, 1 sample, JPG), one directory per build | `10-preview.yaml --set build=<film sha>` | 1584 | after every rebuild of SEQ_Reel; agent-09 reviews it, agent-06 roughs the cut |
| 2 | Calibration A/B/C: TSR 1x8, no AA 2x8, no AA 4x8; 24 frames of S17 (two presenters, strand hair) | `20-calibrate.yaml` (three times) | 3 x 24 | done 17:39: C picked |
| 2b | The cut test: 718-721 across V05 -> S11, shutter open vs centre | `25-cuttest.yaml` (`--set shutter=center` for the old look) | 2 x 4 | once the core shutter_timing is in the box tree |
| 3 | Finals, set shots V01-V05, S11, S12, N01 (no presenters: independent of the MetaHuman and the performances) | `30-final.yaml` | 960 | right after 2 |
| 4 | Finals, presenter shots S13, S15, S16, S17, S18, one at a time as each is approved (performance, his MetaHuman, her watch/collar/hair, framing) | `30-final.yaml --set batch=S13 --set 'shots=["Reel_S13"]'` | 120 each | as they land |
| 5 | A shot that changed after its final | `... --set overwrite=true` | 120 | as needed |

Frames: `/srv/ue/reel/r3/<preview/<build>|final_c|cal_A|cal_B|cal_C>/<master frame:04d>.png` (S13 is 0960..1079; the
sequence's 12-frame handles are -0012..-0001 and 1560..1571, so a full pass is 1584 frames), a report per
job in `_render/<name>.report.json` (time per frame, VRAM peak, missing frames), and the sequence's WAV.
The frames stay on the box: QA, contact sheets, crops, encodes and the cut run there (ffmpeg/python on the box);
only small things come down (sheets, crops, the final MP4s). No bulk frame pulls to kali (home line, AWS egress).

## Keeping them: box -> S3 before the box ends (22:30 UTC)

The presenter shots show the operator's MetaHuman, so every round-3 frame is kept only under the private prefix,
written from the box (its role), never to kali. Each upload is KMS-encrypted in the command itself, whatever the
bucket's default (as core's `sync._sse` does for private uploads): `--sse aws:kms`, plus `--sse-kms-key-id` with the
key in the box setting `kms_key` when it is set (else the account's aws/s3 key):

    KMS="--sse aws:kms"   # + " --sse-kms-key-id <the box setting kms_key>" when that setting is set
    for d in final_c cal_A cal_B cal_C; do
      aws s3 sync /srv/ue/reel/r3/$d s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3/$d/ $KMS
    done

Each job's report is inside its own out_dir (`final_c/_render/`, `cal_A/_render/`, ...: render.job writes
`<out_dir>/_render/<name>.report.json`), so the reports (settings, timings) go with their frames; there is no
`r3/_render/` of its own. The previews are not kept.

agent-07 runs it once the last final is in (and again after any re-render), and only after karmax and agent-10 have
agent-07's report on the bucket and its policy (the default encryption is not verified yet).

## Settings (and why)

- `preset: final`: 8 temporal samples (motion blur through the cameras' shutter, the sub-frame motion that keeps the
  faces from strobing), 32 warm-up frames per shot (TSR/Lumen history), the film-quality cvars (`QUALITY_CVARS`:
  Lumen, VSM SMRT shadows, hair MSAA 8, DOF and motion blur quality 4) and `r.HairStrands.SkyLighting 0`.
- Plus full-resolution skin subsurface (`r.SSS.Quality 1`, `r.SSS.HalfRes 0`): round 3 is about the faces.
- One MRQ job per shot (`chunking: shot`), each from its shot's first frame; a chunk that resumes mid-shot is
  pre-rolled from the shot start (`preroll: cut`) so cloth and hair arrive as in a full-shot render.
- Resume is on: a re-run after a crash or a cancel renders only the missing frames, and a second apply converges.
  `overwrite: true` only for a changed shot, once (an apply with it re-plans the job every time, so it never reports
  converged).
- PIE executor (DECISIONS, day 1). MRQ's game overrides force cinematic scalability and LOD 0 for meshes; the hair
  pop at 0:39-0:40 of v2 is agent-09's (groom LOD/sim/binding): if it needs a render cvar, it goes in `cvars` here.

## Time (measured: calibration, 17:04 UTC, 24 frames of S17, both presenters)

| | AA | samples | s/frame | VRAM peak | RSS peak | fine-detail shimmer | sharpness (Laplacian var) |
|---|---|---|---|---|---|---|---|
| A | TSR | 1 x 8 | 0.68 | 11.6 GB | 6.4 GB | 0.00428 | 0.00022 |
| B | none | 2 x 8 | 1.24 | 10.9 GB | 7.7 GB | 0.00494 (+15%) | 0.00049 |
| **C (picked)** | none | 4 x 8 | **2.49** | 13.3 GB | 9.7 GB | 0.00492 | 0.00047 |

**C for the finals** (in `30-final.yaml`, with `shutter_timing: open`). TSR (A) looked calmest but **erased the
under-shelf LED strips** entirely (1.6 cm, sub-pixel; agent-09 confirmed they are real: only under the shelves above
the lens), which N01 is about. B and C keep them; C's edges are smoother than B's. C's shimmer equals B's (its
24 frames were rendered after a performance change, so that number does not separate them). A full pass at C is
~66 min (1584 x 2.49 s + ~12 s a shot): the set without V04 ~36 min, the presenter shots ~26 min.
Sheets: `/srv/ue/reel/r3/cal_AB_crops.jpg`, `cal_AC_crops.jpg` (frame 1344).

**The cut flash.** The TSR set finals (16:57, `final/`) had a double exposure on the first frame of S11 (720) and
S12 (780): MRQ's shutter is centred on the frame, so frame N's temporal samples start before the camera cut keyed on
N. `shutter_timing: open` (core, fleet/agent-05/render-shutter) samples [N, N+shutter). `25-cuttest.yaml` checks it on
718-721. Every cut had it; the finals go to `final_c/`, and `final/` is superseded.

A's first run (16:47) crashed at PIE start (a SIGSEGV in Python's GC inside UE's CollectGarbage after a burst of
bridge probes), not from the settings: start renders from a fresh or quiet editor.
