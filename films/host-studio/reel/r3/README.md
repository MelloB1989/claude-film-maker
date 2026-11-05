# Round 3 renders (Linux GPU box, UE 5.8.4): plan and settings

Owner: agent-05 (render plan and quality). Runs: agent-07, the only editor driver, with `film-ue apply`.
The 13 shots of `/Game/Reel/SEQ_Reel` (shots.py), 1560 frames at 24 fps, **16:9 1920x1080 only** (no 9:16, no
4K unless the operator asks: then `preset: 4k`, the same files). Everything is rendered on Linux; nothing from v2's
Windows renders is reused.

## HANDOFF, end of night 1 (05 Nov, 03:10 IST): the renders. Read with ROUND3.md "STATE AT END OF NIGHT 1"

The box is terminated, and `/srv/ue/reel/r3` went with it. What was kept is under
`s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3/` (KMS; agent-10 verified the saves).

**Verified (agent-07's final_check/camcheck JSON on the box):**
- Settings: C = no AA, 4x8, `shutter_timing: open` (the cut double exposure is gone), light.py constant hold steps
  (V03 f479 is lit whole), and full-res SSS.
- Time: 2.49 s/frame on S17 (both presenters) and ~1.65 s/frame on the set shots, with a 15.9 GB VRAM peak.
- final_c: V03, V04, V05, S12 and N01 pass both checks.

**Not good or not verified:**
- final_c V01 was rendered on a stale camera (scale 1.14). V02 and S11 are inconclusive (low ncc). All three need a
  re-render; the overnight camfix never ran.
- No presenter final (S13-S18) has been rendered with these settings.
- The likeness in cast_op4 is not render-side, and nobody has seen it: is the iris brown, is the hair straight, is the
  tee hem fixed? (ROUND3.md: agent-04 and the operator.) The render settings are the same for either presenter.

**Next, once ROUND3.md steps 1-5 are done** (restore, the operator's pick, the fixes, `build.py --cameras`, the gate):
1. Render everything into a FRESH folder, `final_d`. Do not reuse final_c: the cameras are rebuilt, and resume would
   keep its stale frames. All 13 shots at C take ~70 min. Before each batch, run `level.save` and `probe_cam --check`
   on the batch's shots.

       film-ue apply films/host-studio/reel/r3/30-final.yaml --set final=final_d --set batch=set \
         --set 'shots=["Reel_V01","Reel_V02","Reel_V03","Reel_V04","Reel_V05","Reel_S11","Reel_S12","Reel_N01"]'
       film-ue apply films/host-studio/reel/r3/30-final.yaml --set final=final_d --set batch=cast \
         --set 'shots=["Reel_S13","Reel_S15","Reel_S16","Reel_S17","Reel_S18"]'   # or one shot per batch

2. Checks on the box: `FINAL=final_d final_check.py`, then `camcheck.py` (see below). Re-render a failing shot into a
   fresh folder (`final_e`), or move its frames aside first.
3. The cuts (agent-06), on the box:
   - `R3_FINAL=final_d R3_CUT=/srv/ue/reel/r3/cut/final cut.sh final --fill-from none --cuts 65s`, then `--cuts 45s`.
   - 65 s is all 13 shots (1560 frames). 45 s drops V04 and N01. Both are 1080p 16:9.
4. Keep (dry-run first):
   - `film-ue sync dir up --local /srv/ue/reel/r3/final_d --s3 $P/final_d/`
   - the cuts to `$P/cuts/`.
   - If Host_Op is the presenter, nothing goes to kali or shoot/.
   - If Trey passes, the finals show no operator face, but the box's `face_data` makes film-ue refuse `shoot/`. Do not
     work around it: ask karmax/agent-10 for the route (the Trey preview reached shoot/r3/preview/ by theirs).

Still open in core: BACKLOG B68 (`overwrite: true` never converges). Until it is fixed, use a fresh folder per take.

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

## Before every final batch (the camera rule)

V01, V02 and S11's first C finals (17:58) and the old V05 were rendered on cameras that existed only as unsaved editor
state, lost at the 18:27 re-open from disk. So, before any `30-final.yaml` apply: `level.save`, then agent-07's
`probe_cam --check` on the shots in the batch (exit 1 = no render). After a batch, two read-only checks on the box
(`uv run --no-project --with pillow --with numpy python -I <script>` from the box tree):

- `final_check.py`: every report under `final_c/_render`, and each shot's frames: count, missing, unreadable, black,
  and brightness jumps between frames (`FINAL=<dir>` for another folder).
- `camcheck.py CAMDIR FINALDIR 90,270,...`: a draft frame per shot rendered with the current cameras
  (`render.frames ... preset=draft`) against the final's; the zoom and shift that align them. Match = scale
  1.00 +-0.02 and shift under 1%. A low ncc (under ~0.5) means the fit did not lock (a dark frame): check another
  frame of the shot.

## Keeping them: box -> S3 before the box ends (the face rule)

The operator's rule (karmax, final): **everything that shows the operator's MetaHuman (Host_Op: S13-S18, both full
cuts, any still) lives only under `s3://rf-render-788655295054-aps1/ue-linux/private/`, KMS-encrypted, written by the
box's role. None of it goes to `shoot/` or is pulled to kali.** Uploads use film-ue (core `sync dir`, fleet/agent-05/
sync-dir), never a raw `aws s3 cp`: with the box setting `face_data` set, it refuses any destination outside
`.../private/` and adds `--sse aws:kms` (with `kms_key` when set) itself. Run on the box, from the box tree's tools/:

    P=s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3
    film-ue sync dir up --local /srv/ue/reel/r3/final_c --s3 $P/final_c/     # frames + _render reports
    film-ue sync dir up --local /srv/ue/reel/r3/cal_C   --s3 $P/cal_C/       # (cal_A, cal_B the same)
    # the cuts with him (agent-06's 65 s and 45 s): --s3 $P/cuts/

`--dry-run` prints the exact command first. Each job's report is inside its out_dir (`final_c/_render/`), so it goes
with its frames.

To kali's disk (not /tmp), through agent-07/agent-10, only what shows no operator face: no-face MP4s (set shots, her
work), the stock-MetaHuman preview and frames-free copies of the reports (`_render/*.report.json`). The superseded
`final/` (TSR), the previews and the `*_old` folders are not kept.

agent-07 runs it once the last final is in (and again after any re-render), and only after karmax and agent-10 have
agent-07's report on the bucket and its policy.

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
