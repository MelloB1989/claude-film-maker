# karma reel: round 3 (the Linux shoot)

Director and integrator: agent-10. Round 3 re-shoots the whole reel on the Linux GPU box
(i-0f7a6ac044b75e922, project HostStudio, level `/Game/Studio/Studio`). It uses v2's shot table (`shots.py`, PLAN.md
§4) and the core helpers on `main` (2bf01e0c, day-1 tested). Nothing from the Windows v2 renders is mixed in.

Branches:
- Film code goes on `film/host-studio`. Each owner works on `fleet/<agent>/r3-<topic>` off it and sends me the sha,
  and I merge.
- Core fixes go to `main` through my gate: a branch off main, sent to me.
- Only agent-07 drives the editor. Everyone else sends agent-07 a branch and the command to run.

## The operator's notes, and what we do about each

| # | note | what changes | owner |
|---|---|---|---|
| 1 | Faces and movement read robotic: head, eyes, blinks, brows, smiles, micro-motion, sway, gestures (**top priority**) | every presenter shot's face and body go through perfkit: `perf.face` (softened solver head, micro-motion, overshoot-and-settle turns, saccades with blinks, irregular asymmetric blinks, brow flashes and smiles on stressed words), v2's smoothstep holds become gaze and expression events, a body life layer (breath, weight shift, sway) over the idle, and 1-2 gestures if they read. Judged on `anim.check` numbers plus before/after stills | agent-01 |
| 2 | He is replaced by a MetaHuman that resembles the operator | capture (`MySlate_3`, private: pulled on the box only) -> identity -> character -> rig/textures/build -> body at the operator's height and build -> outfit re-fit (charcoal trousers, grey tee). The actor keeps the label **`Host`**, so build/light/perf code is unchanged. Eye height and standing height go to agent-11 | agent-04 |
| 3a | Her watch must sit flat on the back of her LEFT wrist | re-seat the watch's socket/offset on her left hand: dial on the back of the wrist, strap flat | agent-02 |
| 3b | Her overshirt collar clips into her neck/hair | reshape the collar so it rolls naturally with clearance (Blender headless **on the GPU box only**), re-import, check every angle of S15/S16/S17 | agent-02 |
| 3c | Her hair shortens at the shoulders at 0:39-0:40 of the v2 cut | find the pop (groom LOD switch, sim reset at the cut, or binding) and make it stable for whole shots; prove it on the frames around the cut | agent-09 |
| 4 | 16:9 only, 1080p first, all on Linux, every shot rendered from its first frame | no 9:16 outputs (`vcrop` unused). 1080p PNG, preset final, one MRQ job per shot from its first frame (cloth pre-roll), resumable. 4K only if the operator asks | agent-05 (plan), agent-07 (runs) |

Cameras (agent-11): his shots S13 and S15 follow his eye height (`EYES_HIM`, `shots.lifted`). `framing.py` checks
every presenter shot: cut above the knee, the whole head in frame, his head under the sign. Heights come from agent-04.

QA (agent-09): stills and a contact sheet for every rendered shot (framing, clipping, the watch, the collar, the hair)
before I approve a final.

The cut (agent-06): 65 s and 45 s, 16:9, with captions from `LINES`/cues.json and loudness to spec, built with the
reel's assembly tooling (`cut.py`, `assemble.py`, `mix.py`, `mix45.py`). The 45 s cut keeps v2's splices: N01 and
V04 are dropped.

## Shots: what changes per shot

| shot | time | cast | round 3 changes | final needs |
|---|---|---|---|---|
| V01 shelves | 0:00-0:07.12 | none | re-render on Linux | studio build |
| V02 credenza | 0:07.12-0:15 | none | re-render | studio build |
| V03 window + olive | 0:15-0:20 | none | re-render | studio build |
| V04 slats + sign | 0:20-0:25 | none | re-render (not in the 45 s cut) | studio build |
| V05 the room | 0:25-0:30 | none | re-render | studio build |
| S11 sign lights | 0:30-0:32.12 | none | re-render (the halo, letter by letter) | studio build |
| S12 studio on | 0:32.12-0:35 | none | re-render | studio build |
| N01 shelves at night | 0:35-0:40 | none | re-render (not in the 45 s cut) | studio build |
| S13 him | 0:40-0:45 | him | new him; perfkit face (head down -> up to the lens, L1, smirk); camera at his eye height | 2, 1, cameras |
| S15 hand-off | 0:45-0:50 | him, her | new him; perfkit face/body; his head turns to her; her L3a; collar, watch, hair | 2, 1, 3a-c, cameras |
| S16 her line | 0:50-0:55 | her | perfkit face (L3b, head tilt on "yourself"); watch and collar in frame | 1, 3a-c |
| S17 together | 0:55-1:00 | him, her | both: the glance on "comes around", then both to the lens; cut above the knee; the hair pop is here (end of the crane out, 45 s cut 0:39-0:40 = f1416-1440): presenters pinned to LOD 0 (agent-09) | 2, 1, 3a-c, cameras |
| S18 title | 1:00-1:05 | him, her | a natural idle with life (not frozen); the practicals dim | 2, 1, 3a-c |

## The presenter gate (nothing with presenters reaches the operator before it passes)

The operator watched preview 1 and found it worse than v2: she clipped through her clothes, there was no lip
movement, and he showed no improvement. It had none of the presenter setup and should never have gone out. So from
now on nothing with presenters goes to the operator until agent-09 signs a written checklist with numbers
(`reel/cast_gate.py`: frames, then `cast_gate.py engine` on the box; `perf.py verify` for the face numbers):

| | check | how it is measured | pass |
|---|---|---|---|
| a | lips move with the VO in every speaking frame, still between lines | `perf.py verify`: per-line jaw/mouth range and std on the placed face, and the silences; frames: mouth motion on vs off the lines | every line moves, every silence is still |
| b | garments and watch follow the body in every presenter frame | stills across each shot (sleeves vs arms, trousers, collar, the watch on the back of the LEFT wrist); `probe_dress.py` engine numbers | no A-pose, no gap, no clip, watch seated |
| c | her hair black end to end | `cast_gate.py`: ends minus roots, teal_g | at most 0.02 |
| d | the natural-performance layer is on | `anim.check` (blinks irregular, head moves, gaze shifts), `perf.py verify` | all checks pass |
| e | him too: the same naturalize and body life on the current male presenter until the operator's MetaHuman replaces him | as (a) and (d) with `--who him` | as (a) and (d) |

The deliverable that follows the gate is the cast preview, S13-S18 at 960x540 with audio. Then the presenter finals,
each after its stills are approved.

Runbook before any presenter render (and again after any re-place or editor restart): `restore_leader.py` ->
`perf.py drive_faces` -> `perf.py place` (both) -> `props/her_outfit_ue/dress_her.py` -> `seq_dress.py`
(the garments take Body's animation in SEQ_Reel, and the watch and hoops get attach tracks, so a level reload can't
undo them) -> `probe_dress.py`. The face steps per presenter are agent-01's (`--who her|him`: solve, compose,
calibrate, naturalize, check, stage/sync/gaze, calibrate_body, life, place, verify).

## Privacy: the operator's face

From the operator, 22:30 IST: once the operator's MetaHuman exists, the project and the DDC are saved only under
`s3://rf-render-788655295054-aps1/ue-linux/private/` (SSE-KMS; only the box's role can read it), and only from the box.
The core enforces this (main): when the box setting `face_data` is set, `film-ue sync project up` and `sync ddc
save` refuse any destination outside `.../private/`. Without it, the project sync always leaves out the face assets
(`Content/Host/OperatorCapture`, `Host_Op*`, `Unpacked/Host*`, `Capture/operator-face`). Capture Manager's converted
frames (`~/.config/Epic/CaptureManager/Media/HostStudio/`, outside the project) are in no sync at all; keep it so. The pre-face DDC was saved
at 17:00 to the normal prefix, which is fine. At the end, the final DDC and project go to `private/ddc/5.8.4/` and
`private/project/HostStudio/`.

Bucket check (agent-07, read-only, 17:2x UTC): the default encryption is SSE-S3 (AES256), not KMS, so every private
upload passes `--sse aws:kms` itself (core `sync._sse`; the r3 README keep step). The bucket policy denies `GetObject`
on `ue-linux/private/*` to everyone but the box role `ue-workstation`. It does not deny list, put or delete there,
or unencrypted puts. Tightening it is a bucket-policy change for the operator; we changed nothing.

The box ends at **22:30 UTC** (operator's extension). Finished work leaves the box only as the small things below.

## Bandwidth and cost: work on the box, bring down only small things

From the orchestrator: kali sits on the operator's 30 Mbps home line, and every box/S3 -> kali download is billed
AWS egress. So **no bulk frame pulls to kali**. QA, contact sheets, crops, encodes and the cut (agent-06) run on the
GPU box (ffmpeg/python there: 16 vCPU, 400+ GB free). What comes down: contact sheets, crops, gate numbers and the
final MP4s for the operator (the orchestrator pulls those). kali `/tmp` is RAM-backed (tmpfs): keep it nearly empty.
Before the box ends, the frames we keep go box -> S3 (same region, no egress), not to kali. agent-07 lists what is
under `/home/nikhil/code/.worktrees/agent-07/out` and deletes it once the shoot is delivered.

## Order of work (the box is never idle)

The editor is the bottleneck: renders and character work both need it. Long set-shot renders fill the box while the
character and performance work happens offline or in Epic's cloud. agent-07 keeps this queue and always starts the
next item before the current one ends.

1. **Rebuild on Linux** (agent-07): bring the box checkout to `film/host-studio`, rebuild the studio and SEQ_Reel
   from code: studio `build.py`, reel `build.py`, `rig.py` (the OutsideNight card and the downlights: `light.py`
   needs them), `light.py --seq`, `vo.py cues --from <project>/Saved/Import/reel`,
   then REEL_PERF.md's 'Re-placing after a studio rebuild' runbook (her garments' leader pose with
   `restore_leader.py`, `perf.py drive_faces`, `perf.py place`), then `props/her_outfit_ue/dress_her.py` LAST:
   it sets her garments' leader (Body), her hair's materials and the hoops' and watch's seats in one pass, reads them
   back and raises unless all hold (each earlier step re-creates her components and undoes them: bind-pose garments,
   teal hair). Without it the presenters stand unperformed or undressed, then render agent-05's `r3/10-preview.yaml`. agent-09 checks the preview.
2. **The operator's capture** (agent-04, run by agent-07): pull `MySlate_3` on the box (the box role only) and run
   identity from the footage. While the cloud solve runs, the editor is free for item 3.
3. **AA calibration** (agent-05): `r3/20-calibrate.yaml` (24 frames of S17, A/B). Pick the settings for the finals.
4. **Set-shot finals**: V01-V05, S11, S12, N01 (`r3/30-final.yaml`), one shot per job, about 1150 frames. These
   fill the box while items 5-7 are prepared. Each finished shot goes to agent-09 for QA.
5. **Her fixes** (agent-02 watch and collar; agent-09 hair), then **her performance** (agent-01, S16 first).
   Stills to me, then the S16 final.
6. **His character** (agent-04): character -> body -> outfit -> build. Then agent-11 sets `EYES_HIM`/`TOP_HIM`,
   agent-07 re-runs `build.py cameras()`, and agent-01 does his performance (S13).
7. **Presenter finals**, each after I approve its stills, in this order: S16, S13, S15, S17, S18.
8. **The cut** (agent-06): the 65 s and 45 s cuts as finals arrive (preview frames stand in until then), then
   captions and the mix. My final review, then the deliverables.

If something blocks the editor (a cloud wait, a fix in progress), agent-07 renders the next set shot.

## Open inputs

- **VO**: round 3 keeps v2's lines and selects (`vo_selects.json`: him Tarun, her Tripti). The built WAVs and
  cues.json (`out/host-studio/reel/vo/`) were made on the v2 workstation. If neither the box nor S3 has them,
  `vo.py takes` re-makes the same takes (same seed and settings) with the ElevenLabs key from `fleetctl secret`, then
  `vo.py build`. Who holds the key: asked of the orchestrator.
- **v2's Unreal assets on the box** (`/Game/Speech`, `/Game/Reel/Perf`): agent-07 checks. If they are missing,
  everything is re-solved (`speech.to_face` on Linux 5.8: proven by agent-07's check).
- **4K**: only if the operator confirms.
- **His hair, facial hair and brows (note 2)**: not known. Built with a PLACEHOLDER (short dark hair, stubble, medium
  brows) that the operator should correct. The choices live in one place, `operator_mh.py` `GROOMS`, so a correction
  is `STAGE='grooms'` plus one `mh.build` (about 95 s). Asked of the operator through the orchestrator.

## Log

(newest last: what was run, the result, and what is next)

- agent-07: box tree = film/host-studio @502124ff (box paths instead of C:\UEProjects); rebuild + preview queued.
- agent-09: the hair pop is S17's crane out (f1416-1440 in the 45 s cut), not N01: the groom drops LOD as she
  shrinks in frame, and MRQ's lod_zero pins meshes but not grooms. `build.py lod0()` pins both presenters' grooms and
  meshes (merged @2b85fb54); to be proven on the preview's S17 f1400-1440.
- agent-07: the studio rebuilt on Linux at 16:24 UTC (81 actors). The order is build -> rig -> light -> 10-preview.
  karma-linux 104ac6f0 restores light.py apply(): the box-path patch had emptied it.
- agent-09: lod0 pins LODSync and the skeletal meshes. Grooms have no Python LOD setter in 5.8, so LODSync drives
  them. The pinned components are named TRASH_* (stale after a Blueprint recompile?): a probe checks whether they
  are live.
- VO: v2's line WAVs survived in the project; `vo.py cues` rebuilds cues.json and the stems, with no ElevenLabs call
  and estimated word times.
- agent-07: the first preview (16:29-16:52) ran before the re-place runbook, so its presenter shots don't show the
  performances; its set shots are fine. 10-preview now takes `--set 'shots=[...]'` to re-render the presenter range.
- Preview 1 QA (agent-09, 16:30 build): all 1560 frames are there. V01-V03, V05, S11 (the halo letter by letter),
  S12 (downlights on the beats) and N01 are OK. **V04 has a one-frame brightness step at f530** (luma 98 -> 77): the
  sun's intensity reaches exactly 0 there. agent-09 is fixing it in light.py (end at ~2 lux, off once BLUE), so V04's
  final waits. The report marks V01 'incomplete' with all frames on disk: a core counting bug (agent-05).
- Host and Presenter are fresh after the rebuild: no TRASH_* components. Him placed; she is placed by agent-01's steps.
- Set-shot finals (without V04) start after the AA calibration.
- Bind pose in preview 1's S17/S18 (operator): that preview ran before restore_leader; `dress_her.py` (agent-02) is now
  the checked last step. The watch sits 3.6 cm above the wrist, dial on the back of the wrist. The collar is still
  in Blender on the box. To prove it: a cast preview (S13, S15-S18) after the runbook, checked by agent-09.
- Set-shot finals done at 16:57 UTC (V01-V03, V05, S11, S12, N01: 852 frames, 431 s); pulled to kali.
- Cast preview 1df0cb0c-cast (17:02) against the gate: (b) PASS by eye (sleeves follow, the watch on the back of
  the left wrist, the collar sits); (c) FAIL, teal_g +0.069 even with MI_K_HerHair on all slots: a material A/B is
  next; (a) S16 PASS on frames, S13 waits for the engine numbers; (d)/(e) FAIL: naturalize was not applied
  (calibrate failed on a dead HeadRoll: fixed in core 45e8146b).
- Orchestrator rule: no bulk frame pulls to kali; QA, encodes and the cut run on the box; only sheets, crops and final MP4s come down.
- Bucket check (agent-07): default SSE-S3, not KMS, so every private upload passes `--sse aws:kms`; only the box role can read private/. Reported to karmax.
- AA pick (agent-05): A, TSR 1x8, the 30-final default. On S17: 0.68 s/frame, 11.6 GB VRAM; B shimmers ~15% more, flickers ~7% more and draws hard lines on the shelf fronts. A full pass is ~20 min. The 16:47 crash was a Python GC SIGSEGV at PIE start after bridge probes, so renders start from a quiet editor.
- AA pick revised, on hold (agent-05): TSR (A) erases the real under-shelf LED strips (1.6 cm, sub-pixel), which matters for N01, V01 and any shot of the upper shelves. Calibration C (no AA, 4x8, ~2.4 s/frame) is running. The 16:57 set finals are not signed off until the pick, and will likely be re-rendered (~40 min).
- Gate on cast2 (agent-09, 17:35): NOT signed.
  - (a) lips PASS: jaw on lines vs between lines is her 12.6x, him 8.6x; every line opens the jaw.
  - (c) hair PASS: ends vs roots -0.024 (cast1 +0.069). The 11-variant A/B is void (scene capture differs), so no material change.
  - (d)/(e) alive PASS: anim.check passes on both; 12 blinks each.
  - (b) OPEN: the watch is now measured from hand_l (<= 1.5 cm). qa.penetration stills are needed. There is a neck/collar seam from the body life layer, which is now off (agent-01 95f25d36) until life is baked in before sync.
  - Head turns: on 5.8 no face curve turns the head, so turns go on the face anim's neck/head bones before sync (agent-01, in progress).
  - cast3 (95f25d36) is being checked.
- Core: agent-05's shutter_timing (render-shutter a86f35f2) fixes the double-exposed first frames at cuts (S11 f720, S12 f780). It is bounced only for a missing API_NOTES row.
- Preview-1 rough cut on the box: 13 of 13 shots, mixes on spec (agent-06). It stays on the box until the gate passes.
- AA pick C (agent-05): no AA, 4x8, shutter open, out to final_c; 2.49 s/frame, 13.3 GB VRAM. TSR's final/ is superseded (it erased the LED strips and double-exposed the cuts). Core a7de4e4b (shutter_timing) is on main.
- Cut test with the shutter open: f720 is clean (agent-07). The final_c set re-render started at 17:57:47 (~36 min).
- Gate on cast3 (agent-09):
  - (a) PASS: S16 3.64x, S13 2.13x; every line on both.
  - (b) PASS: the watch holds a steady 3.6 cm from hand_l. The garment flags are the necklines only, which is the depth check's limit. The collar is clean at full res (S15, S16).
  - (d)/(e) PASS: both eyes shut on 1 frame (f1291, him off screen), which goes to 0 with agent-01's staggered rerun.
  - (c) FAIL at full size: green patches in her ends over the olive overshirt. It is coverage (thin tips), not colour, so a strand coverage A/B follows (hair_cover_ab).
- Head turns: core fe5d335f (agent-01) writes the turn on the neck/head bones on 5.8, and verify measures it. Rerun queued as chain13, then the cast4 preview and the gate.
- final_c set re-render finished at 18:23 (pick C, shutter open); the check and rough cut run on the box CPU.
- Operator MetaHuman (note 2): the ingest is OK. Identity failed conform DEPTH_INPUT (no contours tracked on the promoted frames), so Host stays Trey this cycle and agent-04 is diagnosing. Cutoff: if Host_Op is not built by ~20:15 UTC, round 3 ships with Trey (the swap, re-dress, measure, calibrate, preview and gate need ~1.5 h).
- chain13b on Trey (bcdda51c): calibrate/naturalize her then him, head turns on the bones, runbook, verify, then cast4 + the gate.
- hair_cover_ab hit B68 (overwrite never converges); it reruns with an out_dir per variant.
- WRAP.md (agent-13): the last hour on the box, 21:30-22:30 UTC.
- final_c set check (agent-05): 852/852 frames, 1.64 s/frame, 15.9 GB; the cut flashes are gone. A new defect: V03 f479 was half-lit into V04's state because light steps were baked as two linear keys. Fixed with constant hold keys (74b48a83).
- V04 sun (agent-09 d0eea488): the sun eases to 2 lux and never reaches 0 before the S11 cut.
- Re-render after one light.py re-apply: V04 and V05 whole, plus step frames 359, 479, 794 and 959, into final_c with resume. Old frames are deleted or moved, not overwritten (B68). Presenter step frames 1199 and 1319 come with the presenter finals.
- Operator MetaHuman retry B (agent-04 9450cb90): solve in a separate exec and warm the tracker models. Fallback C (one-image landmarks) is uncertain and would give a weaker likeness; if it comes to C, the operator decides before any swap.
- Set finals in final_c: V03/V04 clean after fix1. V05 re-rendered and on plan; its 18:13 frames were ~1.27x tight because they were rendered from unsaved editor state (the level was re-opened from disk at 18:27). camcheck_1900 renders 1 frame per set shot and compares it with final_c (scale 1.00 +-0.02, shift <1%) to catch any other shot from that job. **Rule:** every final batch is preceded by level.save or level.open from disk.
- Operator MetaHuman: identity conformed (Epic's initialize_contour_data_for_footage_frame); Host_Op built at 19:01. The swap's outfit step crashed and the half-swapped Host rendered unlit; agent-04 is fixing it. Swap back to Trey if not fixed by 19:30.
- cast4 gate (Trey): (a)(b)(d)(e) PASS. (c) FAIL: the groom dropped to cards from f1217 because an earlier hair_cover run re-created the component without the LOD-0 pin. hair_cover_ab now re-pins it, and build.py --lod0 runs before cast5.
- Core on main 4ae66b6b: the head turn goes on the body's neck (5.8's face copies its neck from the body), and the faces' blinks avoid each other.
- **OPERATOR DECISION (00:35 IST / 19:05 UTC): the operator's MetaHuman is built tomorrow.** Tonight's only goal is a full 65 s preview at 960x540 with audio, with the current presenters (Trey + her) and all the fixes, through agent-09's gate, encoded on the box, uploaded to `s3://rf-render-788655295054-aps1/ue-linux/shoot/r3/preview/`. Then the private saves (project, DDC, operator-MH assets) and power off. No more renders.
  - Box order:
    1. Trey restored, dress_her, lod0.
    2. hair_cover_ab (gate c).
    3. The head-turn chain on Trey (timebox ~20:05 UTC, else no turns).
    4. level.save + probe_cam, then one whole-reel 960x540 preview render.
    5. agent-09 QA/gate, agent-06's encode on the box, the upload on agent-10's go.
    6. WRAP step 4.
  - The V01/V02/S11 finals were rendered on stale cameras (camcheck_1900: V01 1.14x, V02/S11 differ). Re-render them tomorrow, with level.save + probe_cam --check first.

- **OVERNIGHT PLAN (cc-64d05f6e, 01:15 IST / 19:45 UTC), supersedes the 00:35 decision: the operator is asleep and the work continues.**
  1. The fixes preview first (unchanged), then its key goes to cc-64d05f6e.
  2. The operator MetaHuman as HIM:
     - agent-04's chain from r3-operator-mh @ 82037d27, run by agent-07;
     - charcoal trousers and a grey tee;
     - placeholder hair and beard;
     - heights measured for agent-11;
     - the face and head-turn pass on both presenters.
  3. A cast preview through agent-09's gate. Then merge r3-operator-mh and set HOST=op.
  4. 1080p finals of every shot at pick C. Fresh out_dir, with level.save + probe_cam --check first.
  5. agent-06's 65 s and 45 s cuts on the box, then the upload to `ue-linux/shoot/r3/final/`.
  6. The wrap: WRAP steps 3 and 4 (private/, SSE-KMS, head-object) start by 21:45 UTC whatever the state. Power-off by 22:10 UTC (03:40 IST); any extension up to 04:00 IST and beyond is asked for, with frames and minutes.
  - idle-guard.sh on the box powers it off after 45 min with no new files under /srv/ue and the GPU under 20%. `/srv/ue/.guard-keepalive` is only for real quiet steps.
  - chain28: her calibrate PASSED (the settle fix). HeadRoll turns weakly and HeadPitch is dead on her, so verify's head_turns at f1100/f1392 is the truth for the gate (agent-01).

- **Finals routing (karmax, 20:10 UTC):**
  - Anything showing the operator's MetaHuman lives only under `ue-linux/private/` (SSE-KMS). That covers frames, S13-S18 and both full cuts.
  - None of it goes to kali or to shoot/.
  - `shoot/r3/final/` takes only the no-face shots and frame-free reports.
  - The kali disk (not /tmp) takes only the Trey preview, the no-face MP4s and the reports.
  - The working end is 22:10 UTC: agent-07 powers off by hand after the head-object check. The box's own 22:30 UTC poweroff is the backstop.
- chain28 verify: the head turns are in (her 26.1/28.3 deg, him -53.1/-21.1 deg) and lip sync passes on both. Her tilt on "yourself" is lost (HeadPitch dead).

- **FIXES PREVIEW DELIVERED (20:11 UTC):**
  - Key: `s3://rf-render-788655295054-aps1/ue-linux/shoot/r3/preview/karma-r3-preview-960x540.mp4`. 19.4 MB, 65.000 s, 960x540 with audio.
  - agent-09's gate is SIGNED: (a)(b)(d)(e) pass, head turns in. In (c) the pop is fixed and the green tint is OPEN.
  - Open for the finals: her S16 neckline under-layer edge, the S15 blend jumps and the his LOD0 pin.
  - The key was told to cc-64d05f6e.

## Tomorrow (round 3, day 2): the list

1. Restore the box from private S3 (project + DDC), then agent-04 re-runs the ingest from the raw take (`private/operator-face/MySlate_3/`, ~1 min). The identity is already solved and Host_Op is already built.
2. Flip him to the operator's MetaHuman:
   - `host_swap.py` (r3-operator-mh, unmerged until then) + rebind, the outfit, K.channels, clip checks;
   - measure, then agent-11's `framing.py --him`;
   - hair/beard: a placeholder until the operator answers (`operator_mh.py` GROOMS, then STAGE='grooms' + mh.build).
3. agent-01's face chain on both: calibrate (it failed on her tonight with old signs: find out why), naturalize her then him, turn_head, verify head_turns + both-eyes-shut.
4. Her hair: the green tint is NOT coverage. hair_cover found no winner, and the green sits inside the lengths beside her face. Do a full parameter dump of MI_K_HerHair and its parent, then fix the material/colour. Gate (c) needs black end to end. The pop at 0:39-0:40 is fixed by the LOD-0 pin.
5. Set finals: move V01, V02 and S11 out of final_c to final_c_<shot>_old, then re-render them at C after level.save + probe_cam --check, then camcheck 90/270/750/775. Good already: V03, V04, V05, S12, N01.
6. The presenter gate on a cast preview. Then presenter finals S13-S18 at C, one per approved shot, with the camera rule.
7. Cut: agent-06's cut.sh final --fill-from none. Keep step to private/renders/r3 (KMS + head-object). Then the private project/DDC save.
8. Core backlog: B68 (overwrite never converges: the take field); render.encode's pattern for frames before 0. Narrow PRIVATE_EXCLUDES' `Unpacked/Host/*` (Trey's build, not face data) when Trey's BP needs syncing.

### Added overnight (05 Nov, 20:00-21:00 UTC)

9. The operator MetaHuman likeness (agent-04):
   - Skin: a closed loop on the box. Match the mean cheek/forehead colour of the capture front frame against a neutral-lit Host_Op still by stepping mh.skin u/v. The numbers stay on the box. Texture-from-capture is to be scoped, not promised.
   - The grooms come from the operator's answer, plus the character-side colour path (preview collection).
   - A TEETH identity pose at ~16 s of the capture.
   - More promoted frames (chin up/down), then re-conform.
   - The trousers' waist, if the tee-hem patches survive chest 104.
10. Her hair green (agent-09): the strands are drawn green, not lit (the overshirt and the Lumen/scatter cvars change green_px by <0.01).
    - Re-run cards_helmet_black with the not-black check.
    - If that doesn't win, check the groom's strand data on Linux (Hair_L_Straight).
    - Gate: green_px <= 0.05 per region.
11. TRASH_ components after the outfit blocks (Host and Trey): do a respawn + re-dress, so that lod0 and drive_faces hit the live components. agent-09 won't sign finals with TRASH_ in lod0.
12. The first run of agent-01's `perf.py place --cleanup` (ME from REEL_PERF_ME), then level.list for Test_. Pull main a9107015 (seq rebind exact, agent-11) into the box tree.
13. The 1080p finals of every shot (fresh dir) with whichever presenter passes, then agent-06's 65 s + 45 s cuts. Anything with Host_Op goes to private/ only.
