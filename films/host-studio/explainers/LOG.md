# Explainers (round 6): log

Times IST. One section per author, rebuilt from each author's branch tip at integration (agent-09, assemble_log.py); edit your own section on your own branch.

## Set, light, cameras (agent-07)

| IST | What |
|---|---|
| 16:20 | Brief in. Layout agreed with agent-01 (actor root on the chair mark (20,-20,0), yaw 0, forearms on the desk), agent-05 (SM_PodcastChair seat 45, SM_WalnutDesk 110x55 top 74, SM_MicBoom posed from the clamp (70,32.6,74) on the desk's +Y edge to a capsule at (44,-6,99)), agent-11 (EDL: CAM_MCU / CAM_CU / CAM_WIDE + CAM_MCU_L for the PANEL shots) |
| 16:30 | `setplan.py` (numbers + offline framing check) and `set.py` (the box driver) written. `python3 setplan.py --check --who her|him`: all rules pass (mic below and >2 mouth-heights clear of the mouth in every camera, eyes in the upper third, the lowered sign at u 0.71 in the MCU, CAM_MCU_L keeps her and the mic left of x 940) |
| 16:41 | Box B up (orchestrator): i-0d7684b44eacf7043, g6e.4xlarge L40S, persistent spot. kali driver `/tmp/fleet-agent-07-ue/r6/fu` (profile `boxb`, port 18817); first editor start compiled shaders ~10 min |
| 16:47-16:48 | **assets.duplicate of the open Studio map, then level.open of the copy, crashed the editor twice** (EditorServer.cpp:2544, the old world still referenced). set.py now saves the open Studio AS the new map (EditorLoadingAndSavingUtils.save_map) and opens it: no crash |
| 16:50 | set.py level/props/light/cameras/seq/save on box B: studio host lights + Karma*/Reel_ cameras + Host deleted in the copy, sign lowered, agent-05's props imported with PBR instances (mat.pbr from props.json, Tiling 1), cameras from the EDL (9 cuts, PANEL → CAM_MCU_L), drift keyed |
| 16:52 | agent-01's body/life/preview: bodycheck FAIL (wrists 30-50 cm off). Cause 1 (mine): **a MetaHuman BP faces +Y at actor yaw 0** (her eye bones split along X) → actor yaw -90. Cause 2 (agent-01): her mesh's bones are longer than the skeleton reference (pelvis +7.48 cm) → fe5ab6c0. Re-run: **bodycheck PASS** (desk/mic/knee 0) |
| 16:57 | Her seated eyes measured at f60: (30.55,-18.76,120.43), mouth (32.5,-18.7,113.6) → setplan FACE; cameras re-aimed; **focus track offsets re-taken on the scrubbed seated pose** (unscrubbed they held her standing eye, z 158: ~2.7 cm focus error at the CU's ±1.2 cm depth of field). Garment leaders had dropped after agent-01's steps → dress_her.py (set.py `dress` step now) |
| 16:59-17:04 | Exposure: physical-camera exposure OFF (f/2 and f/2.8 cameras cut with no jump), bias is compensation (higher = brighter); her rig x2 (channel 1) and bias -1.4 → face ~150/255 in the MCU. The daylight window + sheers top-left of the MCU clip (~26 % of the frame) and do not answer the outside card or the sun; left as a soft bright window for the orchestrator's eye |
| 17:00 | **seq.still's `camera` loses to the sequence's camera cut track**: r1/r2 stills were all the MCU. set.py stills now set the cut track to each camera alone and put the edit back |
| 17:05 | Review stills r3 (MCU, CU, WIDE, MCU_L, SIDE; f60) → `private/renders/r6/review/explain/r3/` (KMS) → orchestrator. agent-01's face chain (`perform.py all --who her --from cams`) started on box B |
| 17:08 | **Orchestrator r3**: no window in any presenter frame, sign clear of her head, forearms resting, shoulder poke. Cameras moved to the +Y side (backgrounds = the shelves wall; window opening: 0 points in any frame, offline rule added), boom MIRRORED (local X scale -1 at yaw -90: clamp (70,-72.6,74), capsule (44,-34,99)), lights mirrored (key on the far side), desk 12.5 cm in (x 38..93), sign lowered 30 cm (out of MCU/CU/MCU_L, wholly in the WIDE) |
| 17:12 | Bridge reinstalled: film/host-studio tip + agent-09's qa.clip set rows (0ce1c3ae): runs on the engine, ops.broken {}. The editor restarts on install: everything saved first. A 61 MB `film-ue push` through the bridge restarted the editor: files go via s3 since |
| 17:15-17:25 | agent-01's resting pose (33c54724 → cea4bf84 → 1f8db30f): elbows planted, forearms on the top, contacts lifted; bodycheck PASS. Garment cuts on copies (`garments` step): Top under Overshirt (reach 6), Trousers under Top, Body under Top. qa.clip's Top>Overshirt row reads the overshirt's OPEN FRONT (chest centre), not a poke (agent-09 investigating) |
| 17:25 | Exposure after the light swap: bias -0.7 → -0.4, her rig x2.8 (face ~115-140/255 MCU/CU). r5 stills → orchestrator: "big step up"; asks shoes or a modesty panel, the WIDE's empty right half, the floor sun streaks |
| 17:35-17:45 | agent-05's SM_WalnutDesk_Panel (modesty panel), SM_FloorLamp (sheer shade, emissive bulb, a 2700 K practical point light), SM_FloorSnakePlant; the -Y wall dressed with copies of SlatPanel/OliveTree + a warm grazer (`dressing` step). **Sun OFF** in the explainer level: her rig gives ~20 lux at her face, so any direct sun patch clips (the window is out of frame) |
| 17:38-17:50 | agent-01's face chain (`perform.py all --who her --from cams --fresh`, onset-window fix installed in the bridge): every stage PASS; numbers committed (lips lag 0.77 f, track r 0.897, onset lead 77 ms, lead_in 0.0001 cm) |
| 17:51-17:54 | r6 stills → orchestrator: **PASS by eye** (watch: dither on the lapel edges in the still → finals' AA). Previews shot 1 MCU / 7 CU / 11 WIDE with the mix → `private/renders/r6/explain/netflix/preview/` |
| 17:56 | qa.clip after the chain: Body>Desk / Desk>Overshirt / Trousers>Chair 0, mouth 0; Body>Chair 8 px + Chair>Trousers 2 px (WIDE) with agent-01. Finals of all 9 presenter shots started (4x8, film cvars, png, garment.leaders_ok read before every job → numbers/netflix/box.json) |
| 17:58-18:09 | agent-01's dde4d4ec body (hips lifted, lean 19°) → 'all --from sync' PASS. qa.clip clip_r7: every set row 0 (chair, desk, mic over mouth); the three garment rows (Top>Overshirt open front, Body>Top wrist, Trousers>Top waist) judged by the orchestrator's eye as OCCLUSIONS → clip_r7 is agent-09's baseline |
| 18:05 | **Strays**: ExplainerSet carried the reel's parked Test_perf_Her, Test_perf_Him (a full BP_Host_Op) and 5 Test_perf_S1x cameras (z -2500) from the Studio copy → deleted; set.py's level step deletes Test_*/FMQA_*; render.py's guard (strays, leaders, face luma in a still through the job's camera) before every job |
| 18:11-18:31 | **HER FINALS**: 9 shots, 4x8, film cvars, PNG + H.264 with the mix → `private/renders/r6/explain/netflix/final/`; guard ok on every job (face luma 119-157); numbers/netflix/box.json garment.leaders_ok 1. Orchestrator: shimmer check PASS |
| 18:35 | **Netflix composite v1** on box B (agent-11's composite.py via `uv run --with pillow`; the box has no pip): netflix_r6_v1.mp4 + ProRes master + srt + contact sheet + f60/f480/f1000 → `private/renders/r6/review/explain/` |

## The set (setplan.py)

- Level `/Game/Explainer/ExplainerSet`: a duplicate of `/Game/Studio/Studio` (so her round-4 overshirt and his loop-2
  neck come along as the box has them); the studio's standing-host lights (Key, Fill, HairLight, RimWarm, RimWindow,
  EyeLight), its Karma* cameras, every Reel_ camera and the other presenter are deleted in the duplicate only. The
  karma sign (+ SignHalo, Halo0-8) comes down 78 cm so it sits in the seated MCU's background (u 0.71, v 0.17).
- Presenter seated on the chair mark (20,-20,0) facing +X; cameras on her right-front (azimuth -20° MCU, -17° CU, -9°
  WIDE), the mic from her left (+Y), low: from every camera the capsule is below and to screen-left of the mouth.
- Light (channel 1 only; the presenter on 0+1, the set's practicals as in the studio): ExpKey 160x120 soft box at
  +45° / 28° up from her left (the window side, short lighting), ExpFill 180x180 from the camera side at -55°, ExpRim
  warm 3100 K strip back-right, ExpHair 3600 K top-back, ExpEye 22x22 by the lens for catchlights. Candela from the
  studio's host rig scaled by distance squared. Exposure manual (bias 8.3, locked).
- Cameras (full-frame 16:9, focus tracking her camera-side eye bone FACIAL_R_Eye):
  CAM_MCU 60 mm f/2 at 165 cm, CAM_CU 85 mm f/2 at 128 cm, CAM_WIDE 35 mm f/2.8 at 320 cm, CAM_MCU_L = CAM_MCU turned
  so her eyes sit at u 0.27. A very subtle drift (≤0.4 cm lens, ≤0.3 cm aim, slow sines 3.7-9.1 s) keyed every 6 f.
- Hand-off to box A (agent-06): `cd tools && uv run python ../films/host-studio/explainers/set.py --box <A profile>
  --instance i-0284d544cdf14905e --who him --edl ../films/host-studio/explainers/edl/whatsapp.json` (all steps; Host
  on the mark at yaw -90, Presenter deleted in HIS copy). Then agent-01's `perform.py body/life/preview --who him`,
  then measure his seated eyes (level.bone Face FACIAL_L/R_Eye, FACIAL_C_LipUpper at f60 after seq.scrub) into
  setplan FACE["him"], and re-run `--steps cameras,seq,dress,save` so the cameras and the focus offsets follow his
  real eyes. Stills: `--stills <tag> --frame 60 --extra-cams CAM_SIDE --edl …`. Renders: render.py.
- Box A replay additions: `--steps level,props,dressing,light,cameras,seq,garments,dress,save` (garments: none for him
  yet); his FACE is an estimate (FACE_ESTIMATED: the sign rule waits, agent-09 holds his film until it is re-enabled).
- Gotchas: duplicate+open of the open map crashes (set.py does save-as); seq.still ignores `camera` under a cut track
  (set.py handles it); any perform/body step can drop the garment leaders (run `--steps dress,save` after it); an
  unsaved change is lost when a tool reopens the level (save after every step).

## Producer (agent-11)

Producer: agent-11. Times IST, 07 Nov 2026. Branch `fleet/agent-11/r6-explainers` (off `film/host-studio`).

### What is here

| File | What |
|---|---|
| `scripts.json` | both scripts, one line = one face solve, grouped into beats |
| `vo.py`, `selects.json` | ElevenLabs takes (him: Tarun `qr9D67rNgxf5xNgv46nx`, her: Tripti `ET6E1GmpkG4a6Sotpwm3`, the karma reel's voices), the selects, the build |
| `audio/<film>/lines/*.wav`, `vo.wav`, `cues.json` | the lines (48 kHz 24-bit mono), the VO on the film's clock, the cue sheet (every word in s and frames, 24 fps) |
| `edl.py`, `edl/<film>.json/.csv` | the edit: shots as runs of lines, cut mid-pause; every word on each shot's own clock |
| `cues/him.json`, `cues/her.json` | agent-04's head-plan cues (on-camera spans, think beats) |
| `GFX.md` | the graphics brief: one shared look, deliverables, S3 folder |
| `music.py`, `audio/<film>/bed.flac` | ElevenLabs Music bed per film, sections keyed to the beats |
| `mix.py`, `audio/<film>/mix.wav`, `mix.json` | voice over the ducked bed, −14 LUFS / ≤ −1 dBTP |
| `facts_<film>.json` | every claim with its source (agent-09's `qa_av.py facts`) |
| `composite.py` | the final composite (runs on a box) |

### Timeline

- 16:19 brief in. Worktree, voices found in `films/host-studio/reel/vo.py`.
- 16:21 scripts v1 (162 / 167 words). Two takes a line at speed 1.0: Tripti reads at 2.2 words/s, Netflix ran ~85 s.
- 16:23 scripts v2: trimmed to 156 / 144 words; speed him 1.06, her 1.14; three takes a line. Selects picked by
  measure (no stray pause inside a phrase, no stretched word, then the tighter read): `selects.json`.
- 16:25 VO built: gaps 0.34 s inside a beat, 0.80 s at a beat change, 0.8 s lead, 2.0 s tail.
  WhatsApp 56.6 s, Netflix 59.5 s. EDLs, cue sheets and the graphics brief sent to agent-01/04/06/07/08/12.
- 16:28 palette to dark-warm (the orchestrator's brief to the graphics agents: consistent with the karma set).
- 16:30 head cues for agent-04. Music: two seeds per film; seed 1 picked for both (a quieter hook, a lift, a resolve
  on the last line; seed 2 of Netflix sat flatter and fell off early).
- 16:33 agent-09's first read: W17 unsoftened → "That's over a hundred billion messages a day." retaken; WhatsApp now
  56.33 s (1352 f), only shots 14-15 moved. Mixes: WhatsApp −14.05 LUFS / −1.71 dBTP, Netflix −14.03 / −1.68,
  bed ducked a median 7 dB under the voice.

### Fact check

Every number on screen or in the voice is softened or sourced; the sources are in `facts_whatsapp.json` and
`facts_netflix.json`. Notes on the wording:

- **"over a hundred billion messages"**: Meta's figure since Oct 2020 is "more than 100 billion a day".
- **"One server once held two million"**: WhatsApp's Jan 2012 post "1 million is so 2011" (2M+ connections, one
  server). "once" keeps it in the past.
- **"almost none of them stay on its servers"**: messages are deleted once delivered; undelivered ones wait up to 30
  days; backups are the user's choice, not WhatsApp's servers' store. "almost" covers the queue.
- **On-screen extras (graphics, approved by the orchestrator)**: groups up to 1,024 members (Meta, Nov 2022, with
  Communities: https://about.fb.com/news/2022/11/whatsapp-communities-launch/); end-to-end encryption by default
  since April 2016 (https://blog.whatsapp.com/end-to-end-encryption).
- **Ticks**: one grey = sent to the server; two grey = delivered to the phone; blue = read (WhatsApp Help Center).
- **Groups**: Sender Keys: encrypt once, server-side fan-out (WhatsApp security whitepaper).
- **Media**: AES-256 key per attachment, the encrypted blob uploaded, key + hash in the E2E message (whitepaper).
  The script says "blob store"; the graphics may label it "media servers / CDN" as secondary.
- **"over three hundred million paying members"**: 301.6M paid memberships at the end of 2024 (Netflix Q4 2024
  letter). Memberships are accounts, so the script says members, not people.
- **OCAs free inside ISPs, nightly fill**: Open Connect overview (free to qualifying ISPs; proactive fill in an
  off-peak window by predicted popularity).
- **Per-title ladders**: Netflix tech blog, "Per-Title Encode Optimization" (Dec 2015). No bitrates on screen.
- **Chunks "a few seconds long"**: kept vague on purpose (Netflix segment lengths vary by client and codec).
- **Control plane on AWS, data plane on OCAs**: Open Connect overview and Netflix's AWS material; the player asks AWS,
  AWS returns the OCAs to fetch from.
- 16:40 `composite.py` written; WhatsApp placeholder rendered on the build host (3 m 52 s with the ProRes master).
  First look: cuts, panels, lower third and the kinetic captions land; captions split "over a hundred / billion" →
  chunking rewritten (clauses at punctuation, long clauses split evenly, never after a lead-in word).
- 16:46 placeholder cuts of both films (graphics + VO + mix + captions + lower third + grey presenter slugs), timing
  locked: out/explainers/placeholder/{whatsapp,netflix}_r6_placeholder.mp4 (+ .srt) in the shared worktree.
- 16:55 ruling: captions on every line, over graphics too, one band in the bottom 15 %. Placeholders re-rendered.
  agent-09 QA on them: captions.text_match 1 (157/157, 144/144), onset 84 ms, -14.1/-1.7 and -14.0/-1.7, 1080p 48 kHz.

### Running the composite on a box (drivers)

    git -C <repo> fetch origin fleet/agent-11/r6-explainers
    git -C <repo> worktree add /srv/r6/explainers-src origin/fleet/agent-11/r6-explainers   # code, audio, fonts
    python3 -m pip install --user pillow imageio-ffmpeg     # if the box's ffmpeg lacks libx264/prores_ks, pass
                                                            # --ffmpeg "$(python3 -c 'import imageio_ffmpeg as i;print(i.get_ffmpeg_exe())')"
    aws s3 sync s3://rf-render-788655295054-aps1/ue-linux/private/renders/r6/explain/<film>/final/ /srv/r6/<film>/presenter/
    aws s3 sync s3://rf-render-788655295054-aps1/ue-linux/gfx/explain-<film>/ /srv/r6/<film>/gfx/
    python3 /srv/r6/explainers-src/films/host-studio/explainers/composite.py --film <film> \
        --presenter /srv/r6/<film>/presenter --gfx /srv/r6/<film>/gfx --out /srv/r6/<film>/out --tag v1
    aws s3 cp --recursive /srv/r6/<film>/out/ s3://rf-render-788655295054-aps1/ue-linux/private/renders/r6/review/explain/

`--placeholder` lets any missing presenter shot or graphic stand in as a labelled slug (a partial cut for review);
without it a missing input stops the run and names the file.

### Netflix v2b (delivered)

- v2 (agent-07, box B): composite.py's one-pass mux cut the audio to 56.08 of 59.46 s (`-frames:v` ended the file
  while the audio lagged the graph); agent-07 remuxed it by hand. Fixed in f6239dd5: the picture is encoded alone,
  then each file is remuxed with the mix (`-c:v copy -t`).
- Orchestrator's look: picture, lips, hair, neckline, grain and mix pass; captions too faint over her white top.
  e60e5a39: a rounded backing plate on every caption (black 45 %, 16/8 px pad, radius 12) and the waiting words at
  70 %.
- v2b on box B (CPU, beside the editor): `/srv/ue/explain/comp3.sh netflix v2b "48 240 600"` (agent-07's comp2.sh on
  src3 = src2 + the new composite.py). Both files 1427 f / 59.458 s; qa_av all: -14.0/-1.7, text_match 1 (144 words,
  37 captions), onset 84 ms, facts 1, qc_ok 1 (needs `PYTHONPATH=<tools> uv run --with numpy --with pillow`).
  Approved and delivered by the orchestrator.

## Performances (agent-01, branch `fleet/agent-01/r6-perf`)

`perform.py` (the driver, every step on the box through the bridge), `seatkit.py` (the seated body, pure Python,
tested in `test_seatkit.py`), `gestures.json` (the emphasis gestures per line).

- 16:20 brief in. No seated or talk-gesture animation in the engine's MetaHuman content, and 5.8 cannot make the body's
  Control Rig track from Python (round 5), so the seated body is FK bone tracks written into an AnimSequence: the
  idle's first pose as the base, the seated pose solved over it (hips over the chair mark at seat + 9.5 cm, pelvis
  back 6°, a 12-14° lean, a 6° chest turn to the cameras, head kept level; two-bone IK legs to the floor and arms to
  the desk, hands semi-pronated, fingertips cleared by wrist extension). Breathing is `anim.body_life` on top.
- 16:55 her skeleton read on box A (read-only probe, Presenter: 342 bones, the idle's 342 tracks): the idle turns the
  body 3.6° and splays the feet, so the facing is snapped to the component's axis (+Y) and that turn is undone. The
  curled idle fingers reached 3 cm into the desk: the wrist extends until they clear (her 20°/15°).
- 17:05 her legs are short for the seat: the thighs met the seat's front edge 3.7 cm low, so her heels come up 5 cm
  (balls on the floor). The whole take checks clean every 6 frames (seat, desk, floor, mic and boom) through the
  gestures. The in-editor build was proven on box A as a probe (read and solve, nothing written). His body is built on
  box A only (face rule: his skeleton never leaves the box).
- 17:10 commands to agent-07 for her body, life, preview, bodycheck and the stills (3 cameras + a side view).
- 17:30 small automatic hand settles where nothing is scripted for 5.5 s.
- 17:50 box B, first body: she floated ~7 cm, forearms in the air. Two causes, probed read-only: (1) her mesh's bones
  are longer than the skeleton asset's reference that AnimPose evaluates on (thigh 43.5 vs 40.2 cm), and the engine
  plays the pelvis at animated + (mesh ref − skeleton ref) = +7.48 cm; (2) her Blueprint's Body is unrotated (actor yaw
  −90 to face +X, agent-07). Fix: solve on the mesh's own lengths, write each translation as wanted − that offset;
  checks in the Body component's frame. Re-run: bodycheck vs seatkit 0 cm.
- 18:20 her lips check failed "mouth 1.0 s early" on N02-N16: the check's onset window reached into the previous line
  (0.34 s gaps); N01 −0.05 s, each solve alone 0.000 s. Core fix `fleet/agent-01/r6-lipsync-onset`; the solver's real
  1-2 f late opening gets a 2.5 f lead (r5/lipsync.md, approved).
- 18:40 the orchestrator's r3 stills: forearms resting ON the desk. New arm solve: elbows planted on the top, forearms
  lying on it, gestures swing the forearm about the elbow; shoulders down 4°, lean 18°, chest square; the set's desk
  came in 12.5 cm and the mic moved to her left (gesture hands mirrored).
- 19:05 bodycheck: the deeper breathing (2.45 mm, 14/min) dipped the resting hands 0.8 cm into the top on each
  exhale: forearms rest 0.6-0.8 cm higher. Her face chain goes next (cams, compose with the lead, face, sync, gaze,
  place, numbers).

## Props (agent-05, branch fleet/agent-05/r6-props)

| IST | |
|---|---|
| 16:20 | Brief: chair, broadcast mic on desk boom with cable, walnut desk, optional headphones/plant; Blender headless on box A CPU (agent-06's slot: `/srv/ue/props_r6`, nice 15, `-t 6`, never the editor/project/reel paths) |
| 16:35 | `props/explainer/_pbr.py` (12 tileable 2K PBR sets drawn in numpy, UVs, UCX, FBX) + `build.py`; dims matched to agent-07's layout (chair (20,-20,0), desk centre (78,-20,0) top 74, mic from her left +Y) |
| 16:58 | Debug run on box A (256 px textures, no renders): all four FBX re-import at the built size in cm (chair 79.7 x 69 x 86, desk 55 x 110 x 74, mic boom 48 x 30.9 x 77, plant 12.9 x 12.8 x 43.9) |
| 17:02 | Full run: textures 70 s; FBX + textures + props.json → `s3://…/ue-linux/props/explainer/` |
| 17:10 | By eye: walnut figure too burl-like, leaf bands lost in noise → redrawn (rift-sawn walnut, clean sansevieria bands), job restarted |
| 17:15 | agent-07: UV0 has the tile baked in (material Tiling 1); plant moved to (100,25,74) by the clamp; headphones skipped (optional) |
| 17:25 | Chair preview: the desk's legs were never joined into SM_WalnutDesk (they floated in the scene) → fixed, re-uploaded; gentler normals on fine metals/rubber/plastic |
| 17:50 | Previews by eye: chair, desk, mic, plant, set (agent-07 frame) good; brushed alu still read hammered: not denoise (256 spp no-denoise test showed it) but low-frequency ROUGHNESS blotches on a mirror-like metal → alu varies only along its streaks; fixed (test render clean) |
| 18:05 | agent-07 moved the desk in (near edge x 38) and mirrored the boom to the -Y edge (scale -1 at yaw -90): no re-pose needed. Armrest 63.0 vs apron underside 63.4 noted |
| 18:30 | A full re-run died at once: `cd && rm && nohup … &` on one line ran the whole chain in a subshell that SSM killed with the command → relaunch with `setsid nohup` on its own line |
| 18:45 | Orchestrator (via agent-07): her feet never seen, WIDE's empty right → SM_WalnutDesk_Panel, SM_FloorLamp (practical, SOCKET_Bulb), SM_FloorSnakePlant; all 7 FBX re-import at size; uploaded with all textures |

## Round 7: performance (agent-11, director)

- 07 Nov 23:43 IST: her acting sheet, first draft. `acting.py` resolves a per-line sheet (emotion, intensity, base
  smile/brows, face moves and gestures on exact words, lean) against the VO alignment into `acting/her.json` (seconds +
  frames, plus `face04` / `body01` views for agent-04 and agent-01) and `ACTING.md`. On paper: 19.4 smiles/min, 20.6
  brow moves/min, 0.87 gesture onsets/s, longest neutral stretch inside a line 1.41 s, no gesture twice in a row.
  TEST span: CAM_MCU f0-196 (N01-N03) + CAM_WIDE f1040-1162 (N13) = 13.25 s; N04 (f196-305) optional.
- 07 Nov 23:47 IST: the orchestrator approved v1 as direction, with two calibrations, applied: full Duchenne (>= 0.8)
  only on five payoffs (members, just starts, near you, AWS, just plays), mid-line smiles 0.4-0.6 with a shape /
  asymmetry each; gesture amplitude `amp` per stroke and HELD strokes (`held`, `hold_s` 0.5-1.0). His 17 lines
  (`acting/him.json`), same staging and calibration (payoffs: messages, Here's how, read it, your hands, a day): 0.94
  onsets/s, longest neutral stretch <= 1.5 s; his TEST span CAM_MCU f0-179 (W01-W03) + CAM_WIDE f422-480 (W07).
- 08 Nov 01:10 IST: overnight prep for composite v3. `comp_box.sh` runs the whole composite on a box in one command,
  CPU only (graphics sync, composite.py, contact + stills, qa_av all with filmtools so qc_ok runs, upload to private review).
  It's staged on box B as /srv/ue/explain/src4 (src3 + qa_av.py + comp_box.sh). WhatsApp graphics-only dry run
  `PLACEHOLDER=1 comp_box.sh whatsapp p1 none`: 1352 f, -14.1/-1.7, text_match 1 (157 words / 46 captions), onset 84 ms,
  facts 1, qc_ok 1. SFX for the v3 graphics: `sfx.py` made 9 cues x 2 takes (~118 credits) with ElevenLabs sound
  generation, picked by measurement; `place` lays each film's sfx_v3.json on the timeline and `mix.py --sfx` adds the
  stems (a fake list held -14.03/-1.67). The v3 graphics and hit lists land ~07:30 IST (agent-12 netflix, agent-13 whatsapp).
- 08 Nov 02:14-03:20 IST (agent-11, interim box B driver: agent-06 and the pc2 agents unreachable): box B was
  spot-reclaimed at 02:14:51 (no g6e capacity in ap-south-1a; the persistent request restarted it itself at 02:21). Nothing
  was lost: agent-06's cams + `FACE_SOLVE=full all --from face` had been saved (assets 01:58-02:10, level 02:12). After
  the restart the editor opened /Game/Studio, and the SSM tunnel was stale (`film-ue close` + `tunnel`). Her level was
  reopened and the garments re-led, then agent-06's chain_T2 resumed from head sample. Head gate on fresh data:
  on_lens 0.916, every span >= 0.82 (the head's own aim off the lens: 1.1-1.8 deg MCU/WIDE, 6.9-7.4 deg CU). Face
  (gate09, whole take): active 0.83, smiles 20.8/min, brows 29.2/min, neutral 0.79 s, frown 0. Hands in frame: MCU 1.0,
  CU 0.89, WIDE 1.0. ARMS FAIL: the left upper arm is inside the Top by up to 7.05 cm at f66 and f1118-1136, the two
  big two-hand spreads where the sheet keeps the left hand inside the mic line (N01 "million", N13 "that"); the right
  arm is 5.8-8.5 cm clear. The arms measure's cleanup leaves the garments unled: re-lead (`mh.leader`) before any
  render. The TEST render (shots 1,2,11) started anyway, so the face can be judged while the arms are fixed.
- 08 Nov 02:20-02:45 IST: agent-13's WhatsApp v3 batch 1 (12 files) synced to gfx/v3/explain-whatsapp; graphics-only dry
  composite g3a on box B: all 9 graphics, 1352 f, lufs err 0.1, TP -1.7, text_match 1, onset 84 ms, facts 1, qc_ok 1.
- 08 Nov 03:30-04:15 IST (agent-11, box B): the TEST's WIDE shot hit a Vulkan GPU crash (TerminateOnGPUCrash); the
  editor restarted itself, and a shot-11-only retry rendered clean. agent-10 found the left-arm cause: gesture_style's
  MIC_L (7 out, 3.5 cm below the sternum point) straightened her left arm on all 14 two-hand gestures, so the elbow rose
  into her chest. d2589d46 (9 out, level) failed the body's own mic check from CAM_WIDE at t 46.4. 7976d7b6 (9 out,
  2 cm below) passes. Applied as two files on agent-06's driver tree: body --perform 0 issues, all --from sync passes,
  head on_lens 0.916, mesh arms over every two-hand gesture (80 frames) L min 5.92 / R min 5.30 cm (f66: -7.05 ->
  +6.30). TEST render netflix_r7F (shots 1, 2, 11) 04:04-04:10; `test_clip.sh` on the box composites the film with
  placeholders and cuts the TEST spans: netflix_r7F_TEST.mp4 (13.25 s) + stills, private review, to the orchestrator.
- 2026-11-08 ~05:55 IST, agent-11: agent-13's WhatsApp v3 polish pass (12 files, soft caption band, no full-frame
  flashes on the panels) re-synced to gfx/v3/explain-whatsapp. Dry composite g3b: 1352 f, lufs err 0.1, TP -1.7,
  text_match 1, onset 84 ms, facts 1, qc_ok 1 (same as g3a).
- 2026-11-08 09:05 IST, agent-11: box B spot-stopped at 08:37 IST (03:07 UTC) with no capacity, idle since r7F, so
  nothing was lost. kali rebooted and wiped the interim driver trees under /tmp. agent-06 is back and drives box B
  again; handed over with the r7F state, re-lead before every render, and numbers_test not yet run.
- 08 Nov 10:29 IST (agent-11): the orchestrator's TEST verdict (her rest pose to agent-01/10/08; the lower third off the
  gesture zone). The lower third moves TOP-LEFT: agent-12 bakes it into Netflix's lowerthird.mov (plate right edge x 680,
  370c2c3d); composite.py's drawn card (WhatsApp) is x 96-660, y 80-243 with the title wrapped, clear of the MCU head
  (setplan projection from x ~704). comp_box.sh PRES_S3 pulls agent-07's farm finals. Box C (agent-06's, CPU only):
  WhatsApp dry composite g4: card measured at x 96-619, y 81-241 (f48 vs f4); 1352 f, lufs_err 0.1, TP -1.7, captions 1,
  onset 84 ms, facts 1, qc_ok 1.
- 08 Nov 13:20 IST (agent-11): acting sheets per the orchestrator's elbow rulings: at most ~1/3 of strokes at/above the upper
  chest (off-camera strokes at the sternum, 5 non-key visible ones pinned; her 0.326, him 0.302; 7154f0db) and nothing at
  the chin (CU strokes and N15 'cloud' at the collarbone; 5a2c042e; agent-01 sets APEX_Z collarbone 22). v3 mixes with the
  graphics' SFX lists (agent-12 93 hits, agent-13 75): -14.03/-1.66 and -14.06/-1.71 (e936898c). agent-12's final Netflix
  v3 graphics (8-sample, 809e29eb) synced to gfx/v3/explain-netflix (12 objects). No box (spot only, none up), so the
  graphics-only Netflix dry composite ran on the build host in a container: 1427 f, lufs_err 0.0, TP -1.7, format_ok 1,
  captions 1, onset 84 ms, facts 1, qc_ok 1; lower third top-left as planned. composite.py now counts the picture's frames
  with framecrc: ffmpeg 6.1 prints no frame= on a stream copy (the check read -1).

- 2026-11-08 15:01 IST agent-11: r7 cost policy. comp_box.sh takes RENDER_BUCKET (Tokyo box -> Tokyo bucket; f36709f9) and from a Tokyo box copies only the mp4, master and srt to Mumbai private (9c7a6321). One approved server-side copy of gfx/v3 Mumbai -> rf-render-788655295054-apne1 (25 objects, 3.37 GB, matches). Asked agent-06/07 to write final frames to the Tokyo private prefix.

- 2026-11-08 23:04 IST agent-11: the operator's fallback for her hands prepared offline, NOT applied: FALLBACK_HER.md (8 shots chest-up: 01 02 04 06 07 10 13 14; shot 11 WIDE rest_only f1034-1168). R7 hands sheets: no finger counting (her N13, his W10/W11/W16 LIST; his W04/W06 place); raise_finger kept on her N03 and his W12 (catalogue passed).

- 2026-11-09 04:13 IST agent-11: her finals composited on T2 (CPU): A (netflix_r6_r7A) and the pick B (netflix_r6_r7B, finals_B ff93e054): 1427 f, -14.0 LUFS / -1.7 dBTP, captions 1, facts 1, qc_ok 1; agent-04 comp_check all pass (black 0, dup 0, A/V 0 ms). Keys under Tokyo private renders/r6/review/explain/. The box static ffmpeg 7.0.2 cut the picture to 299 f (as ffmpeg 9 did on the build host); rerun with a user-space ffmpeg 6.0.1, which comp_box.sh now prefers.

- 2026-11-09 09:20 IST agent-11: his finals (whatsapp_finals_him, r7-him 2144fc7e) composited on T-d (CPU, ffmpeg 6.0.1): whatsapp_r6_r7fin, 1352 f / 56.33 s, -14.1 LUFS / -1.7 dBTP, captions 1 (84 ms), facts 1, qc_ok 1; comp_check all pass (black 0, dup 0, A/V 0 ms). The drawn lower third clears his head by 93 px; the panels by 358-402 px (alpha > 32). agent-04 PASS. Keys under Tokyo private renders/r6/review/explain/; mp4, master and srt also in Mumbai private.
