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
- 07 Nov ~01:30 IST (r7, agent-04): her face acts. Cause of the "pale" face: mouth-only solves, plus a plan that
  added only random brow flashes (brow_chance 0.45) and no smiles. `face_acting.py` turns agent-11's sheet
  (v1.1) into perf.face events on the exact words: brows, curious one-brow, Duchenne (cheek + squint) only on the
  5 payoffs, soft 0.4-0.6 elsewhere over a warm base, nods and a shake, and filler past 0.7 s of neutral speech.
  The lips stay the solve's (corner pull and dimple only, x0.75 while talking). Tilts go to agent-01's body.
  Offline rows pass: active 0.88, smiles 27/min, brows 22/min, neutral hold 0.79 s. FACE_R7.md is the driver's sheet.
## Round 7 garment: her bottoms at the waist (agent-05, branch fleet/agent-05/r7-waist; task 0c7d, with agent-02)

| IST | |
|---|---|
| 23:15 | Brief: "her skirt or whatever she is wearing below is not fit to her". Her bottoms are her_outfit.py's Trousers (fitted to her A-pose, weights smoothed 30x over the garment), leader-posed seated |
| 23:30 | agent-06's garment.export (read-only) → box B /srv/ue/fit/her_r7 (live meshes: Trousers_Under_Top, Body_Under_Top) + the uncut SKM_Presenter_Trousers |
| 23:35 | `props/her_waist_r7.py` probe (24 sectors x 5 heights through the band, AS_exp_her_body seated): the uncut band stands 0.62-1.97 cm off her waist (front 0.7-0.9, sides 0.9-2.0); the live cut copy has lost 7.4k verts incl. the band's INNER face (r6b's Trousers-under-Top 6 cm cut): a hollow band, gap 0.7-2.2 cm, and a step down to the Top |
| 23:50 | Refit in her seated pose, carried back to the bind pose by each vertex's inverse skinning: Top tuck 0.12 cm off her skin (under the band), the band 0.42 cm over it, her body's weights unsmoothed through the band ramping to the trousers' own 5-13 cm under it, seams welded. Seated after: band gap 0.41-0.52 cm in every sector, 0 body/Top pokes. Standing it would sit up to 0.7 cm inside her belly: a seated-only asset (_R7W). ~3k verts at her seated front hip crease (9-13 cm under the edge) read inside her skin: left alone; Body-under-Trousers now hides her skin there |
| 23:58 | setplan: GARMENT_SRC Top/Trousers → SKM_Presenter_{Top,Trousers}_R7W; GARMENT_HIDES her: the inner layer under the outer one (Top under Trousers 2.5, Body under Top 6, Body under Trousers 2.5), the Trousers-under-Top cut dropped. Import: `her_outfit_ue/import_r7_waist.py` (agent-06) |
- 07 Nov 23:55-08 Nov 00:20 agent-08 (`fleet/agent-08/r7-humanize`): the mocap-library route was dropped (the operator:
  no motion libraries, "we can't show same animations"; nothing was downloaded). `gesture_style.py` is the layer that
  makes gesturekit's generated motion human: a seeded draw per gesture (film line + index + hand: amplitude, height,
  wrist angles, finger offsets and spread, timing +-40 ms, path bulge), min-jerk preps skewed late, stroke overshoot
  and settle, drifting holds, co-articulated retracts, the wrist leading in and following out, a pinky-to-index
  finger cascade and never-frozen finger micro-motion. Her full take on her skeleton read: build passes, arm
  clearance 3.8/3.8 cm, most similar gesture pair 0.842 (his 0.741, across 0.84; without it 25 identical pairs per
  film). The left hand's draw is bounded (a 1.17x draw put her forearm on the mic arm, fingers in the desk).
- 08 Nov 01:10 IST: overnight prep for composite v3. `comp_box.sh` runs the whole composite on a box in one command,
  CPU only (graphics sync, composite.py, contact + stills, qa_av all with filmtools so qc_ok runs, upload to private review).
  It's staged on box B as /srv/ue/explain/src4 (src3 + qa_av.py + comp_box.sh). WhatsApp graphics-only dry run
  `PLACEHOLDER=1 comp_box.sh whatsapp p1 none`: 1352 f, -14.1/-1.7, text_match 1 (157 words / 46 captions), onset 84 ms,
  facts 1, qc_ok 1. SFX for the v3 graphics: `sfx.py` made 9 cues x 2 takes (~118 credits) with ElevenLabs sound
  generation, picked by measurement; `place` lays each film's sfx_v3.json on the timeline and `mix.py --sfx` adds the
  stems (a fake list held -14.03/-1.67). The v3 graphics and hit lists land ~07:30 IST (agent-12 netflix, agent-13 whatsapp).

## Speech-driven gestures (agent-10, branch fleet/agent-10/r7-gesture)

| IST | |
|---|---|
| 23:50 | Licence survey of open speech-to-gesture models (r7/gesture_model.md): every model with body + fingers is non-commercial (BEAT2 / SMPL-X / ZEGGS / MPI / CC-NC). Orchestrator: no NC output anywhere |
| 23:58 | Mocap-clip planner started on agent-08's Mixamo list; dropped at the operator's call: no motion libraries, every gesture generated by code |
| 00:05 | prosody.py (syllable nuclei, stressed = loudest, local vocal energy over speech only) + plan.py -> acting/timing_her.json for agent-01's gesturekit hook: apex 80-200 ms before the stressed peak, amp/speed by energy, 7 beats on secondary stresses, rest > 0.6 s, chained post-stroke holds |
| 00:10 | evaluate.py (agent-09's body rows on agent-01's Performer): whole 0.42 -> 0.58 onsets/s, MCU test 0.61 -> 1.07, WIDE 1.09, hands up 0.975, clearance >= 3.57 cm. 18/50 strokes still under the 40 cm/s beat line: same-pose successors (counts 2-3, N04 'Appliances.'), sent to agent-01. Stick preview (not her) frame-synced to vo.wav: test span + full 60 s |

## Box B driver, night of 7-8 Nov (agent-06, branch fleet/agent-06/r7-boxb)

| IST | |
|---|---|
| 01:58 | Her TEST chain_T2 (cams, FACE_SOLVE=full face pass) started on agent-01's 1b8797f4 body + the new mic. Cams old vs new < 0.2 deg |
| ~04:10 | kali rebooted, its /tmp was wiped (driver trees + box conf), and chain_T2 died mid-face (exit 255). pc2 was down too |
| night | agent-11 drove box B meanwhile: body --perform at 7976d7b6 (0 issues, clearance L 5.92 / R 5.30), face, head (on_lens 0.916), hands (MCU 1.0, CU 0.889, WIDE 1.0), TEST render netflix_r7F shots 1,2,11 done 04:10 IST, test_clip r7F 13.25 s for the orchestrator. Level saved |
| 08:37 | Box B spot-stopped (service-initiated). Nothing unsaved |
| 09:00 | agent-06 back. Rebuilt the kali driver (/tmp/fleet-agent-06-ue/r7: tree 102de420 = r7-body 7976d7b6 merged, fu, sether, conf film-ue.boxb.json). start-instances: InsufficientInstanceCapacity. Retrying the same instance every 10 min (no new spend). On-demand / other-AZ question is with the orchestrator |
## Round 7 garment (agent-02, branch fleet/agent-02/r7-garment; measures in `reel/r7/garment_measure.py`)

| IST (8 Nov) | What |
|---|---|
| 00:10-00:40 | `garment_measure.py` waist + arms. Fixes found on box B runs: the actor's forward is 90 deg off her facing (angles now from her skeleton); the arm/torso split needed the arm radius, an open-edge sign rule, a shoulder floor and a nearer-the-spine rule; a ref-pose self-check gates every arms run |
| 00:40 | v2b waist: `waist_fit_cm` 1.04 at her LEFT side (90 deg), front 0.56, no poke. Orchestrator's eye (WIDE f1100 3x): the band flares out past the Top's side line on her left = the operator's "not fit" |
| 01:00 | agent-05's R7W (seated refit): fit 0.0 but her belly pokes out through the front band, +0.32..0.59 cm on the R7 body (qa.clip Body>Trousers 2.6 % in the WIDE). agent-09 splits the row: `waist_fit_cm` <= 0.75 (must_fail v2b 1.04) + `waist_poke_cm` <= 0.1 (must_fail R7W +0.49), on-screen frames only |
| 01:20 | R7W2 (agent-05, fitted over her UE-posed belly from `export_posed.py` at f1080/270/150/870): fit 0.28, poke -0.26 on f150/270/870/1080. Orchestrator: waist PASS by eye (WIDE f1100 3x). Her TEST renders in R7W2 with the cuts Top<Trousers 2.5, Body<Top 6, Body<Trousers 2.5 |
| 01:20 | Arms (`upperarm_torso_clear_cm`): self-check passes (ref pose +5.19, 0 inside); agent-01's elbows-out R7 frames read +5.7..+8.7. Pending before it gates: the v2b reading (must_fail, her right arm at 00:44) |
| 02:10 | Arms VALID: v2b (SEQ_Explain_Her_v2b, f1044-1104:3) -8.19 cm, both upper arms inside the Top/breast the whole 00:43.5-00:46 hold, self-check passing every frame; R7 elbows-out controls +5.7..+7.1. Gate: `upperarm_torso_clear_cm` >= 3 on screen, must_fail v2b. The sign is solid; the depth is approximate |
| 10:08 | Orchestrator: replace box B. AMI ami-0549070f5f5f9a2a2 from stopped box B. Spot g6e.4xlarge: no capacity in 1a or 1b for 10 min (1c doesn't offer g6e), so box C i-076cd8c1839dbbd8d ON-DEMAND in 1a at 10:19 |
| 10:28 | Box C verified (both levels, SEQs, Perf/r7A, r7B, v2b, SM_MicBoom_her, _R7W/_R7W2 garments, set_her/him), her level re-led. Box B's spot request sir-kri7mksg cancelled, box B terminated |
| 10:35 | Operator: no on-demand, spot only. Box C saved, API-stopped 10:40, AMI ami-03d0ee853276c5958 (newest state), box C terminated 10:42. agent-07's spot hunter launches box D from it |
| 10:45 | Ready for box D: her verify at r7-body 773091c2 (rest 25,10,-4; her MCU hands line 0.5): bless signs (kali out/ was wiped; live c95d1126), body --perform, arms on rest frames, cams, preview, FACE_SOLVE=full all --from sync, render CAM_MCU shot 1 (netflix_r7R). Then his chain (x/newbox.sh repoints the driver) |
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

### Editor boxes, 8 Nov evening (agent-06, IST)

| IST | What |
|---|---|
| 14:20 | Box D (Mumbai g4dn.4xlarge T4, spot) from box C's AMI: core install; T4 feasibility CAM_MCU f0-30 at the finals preset: 199 s, peak VRAM 9.9 GB of 15, no GPU errors. |
| 14:30-15:00 | Her chain on 1e88aca8: gates first read the sequence before the new seat was bound (body writes only the seat; preview binds it); re-ordered. "Stale life layer" parity of 44-47 cm later traced to a CLOCK slip: editor dumps are 24 fps sequence frames, arm_track.json is 30 fps; parity now matches by time (agent-13 parity.py). |
| 15:00 | Box D terminated (spot request cancelled). Her chain moved to Tokyo T2 (g6e.2xlarge spot, restored from the Tokyo bucket); his to Tokyo T. Kali cannot read box-written private/ objects: parity/rows/rest filters run on the boxes, numbers only come back. |
| 15:30-18:30 | Body iterations ac3dc14a -> 906d80d3 -> 8a45d961 -> b4325b5b (her), up to 9eaf6a4b / ea9eadc0 / aba900fe (him): mic occlusion per cut camera, finger snaps eased, life scaled for him. Box T killed twice by the kill switch re-arm (stale idle points) and once by Tokyo capacity; T2 spot-interrupted 11:42-11:49 UTC mid face pass. |
| 19:15 | Her T2 gates on b4325b5b: parity --shoulder 0.919 cm, all rows on the kit track (finger_snap 0), rest 16.36 cm, arms rest + gesture pass (agent-02 949cde7c), hands_in_frame MCU 0.797 / CU 0.529 / WIDE 1.0, head gate pass (on_lens 0.916). Breath z 1.62 mm (target 2-3.5) goes to the finals' life (d85ecdc6). |
| 19:33 | Her verify render netflix_r7H shots 1, 2, 11 at the finals preset on T2 (7 min); Tokyo private review/explain/netflix_r7H/final/. T2 saved + API-stopped for the orchestrator's review. |
- 08 Nov 13:20 IST (agent-11): acting sheets per the orchestrator's elbow rulings: at most ~1/3 of strokes at/above the upper
  chest (off-camera strokes at the sternum, 5 non-key visible ones pinned; her 0.326, him 0.302; 7154f0db) and nothing at
  the chin (CU strokes and N15 'cloud' at the collarbone; 5a2c042e; agent-01 sets APEX_Z collarbone 22). v3 mixes with the
  graphics' SFX lists (agent-12 93 hits, agent-13 75): -14.03/-1.66 and -14.06/-1.71 (e936898c). agent-12's final Netflix
  v3 graphics (8-sample, 809e29eb) synced to gfx/v3/explain-netflix (12 objects). No box (spot only, none up), so the
  graphics-only Netflix dry composite ran on the build host in a container: 1427 f, lufs_err 0.0, TP -1.7, format_ok 1,
  captions 1, onset 84 ms, facts 1, qc_ok 1; lower third top-left as planned. composite.py now counts the picture's frames
  with framecrc: ffmpeg 6.1 prints no frame= on a stream copy (the check read -1).

- 2026-11-08 15:01 IST agent-11: r7 cost policy. comp_box.sh takes RENDER_BUCKET (Tokyo box -> Tokyo bucket; f36709f9) and from a Tokyo box copies only the mp4, master and srt to Mumbai private (9c7a6321). One approved server-side copy of gfx/v3 Mumbai -> rf-render-788655295054-apne1 (25 objects, 3.37 GB, matches). Asked agent-06/07 to write final frames to the Tokyo private prefix.
- 08 Nov 19:50-20:25 IST agent-08 (R7 hands lead, `fleet/agent-08/r7-hands`): the operator on her verify, 00:08: "the
  finger -> it looks like zombie". Cause: gesturekit's shapes were curl offsets on the rig's reference curl with the
  PIP/DIP clamped at -5, so her counted right index sat at MCP 12-19 / PIP 19 / DIP 21 (the intrinsic-minus claw), and
  the desk hand's DIPs at 7-18 (flat). `handshape.py` replaces them with named whole-hand poses as ABSOLUTE anatomical
  targets: one closure per finger through an MCP-first synergy (DIP = 0.67 PIP), the relaxed cascade, spread narrowing
  as the fingers close, and the thumb (palmar abduction out of the palm's plane + MCP/IP flexion, fitted by its tip).
  Each joint turns by target - the rig's measured reference, so both rigs work. Merged agent-01's LIST kind (4bdf1518)
  and agent-11's LIST sheets (963f561d): no finger counts are left in either sheet. Her take offline: build pass 0
  issues; claw 0, DIP/PIP out of band 0, fold at the limit 0; snaps 1.01/min. The catalogue take
  (`perform.py body --perform --catalogue`, AS_exp_<who>_hands_cat) and side builds (`--suffix`) feed the stills on T2.
| 11:15 (08 Nov) | agent-13, R7 movement director: r7/naturalness.py + r7/NATURALNESS.md (research, 12 rows + 2 guards for agent-09, run on her old 404db805 / r7F TEST 52ab5ea2 / 773091c2 / 58f6e0aa). Main finding: her right upper arm sits 78 deg off hanging at strokes (elbows up and out), 64 at rest; wrists deviate 31-33 deg; the hand rotation leads the arm by 18 ms; the left hand travels 0.27 of the right on two-hand strokes |
| 12:48 (08 Nov) | agent-13: agent-01 r7-body 7652457b passes all 14 naturalness rows + 2 guards, whole take and TEST spans (r7/naturalness_her*.json). Measure fix: still frames (< 2.5 cm/s) are trimmed off movement ends; with the overshoot off the holds are dead still and the next speed minimum sat at the hold end, inflating peak/mean |
| 13:10 (08 Nov) | agent-13: agent-01 r7-body 1e88aca8 (hold life + finger life) passes all 16 naturalness rows (15 + mirror guard), whole take and TEST spans, on 0.1 mm dumps; released to agent-06 for the verify body |
| 2026-11-08 15:29 IST | agent-13 | r7 movement: agent-01 desk rest ac3dc14a passes all 18 naturalness rows offline (whole take + verify spans; lag 48.5, flexext 24.6); numbers r7/naturalness_her_desk*.json; render gated on parity <= 1 cm + rows on the editor dump |
| 2026-11-08 15:39 IST | agent-13 | r7 movement: FPS FIX. --span and parity read the 24 fps film frames as the 30 fps dump frames: the "stale layer" (44/47 cm parity) was that, the editor matches offline to ~0.4 cm. Now matched by time. In the true verify windows 8d17a4ed / ac3dc14a FAIL wrist_flexext_p90 43.4 (right wrist extends to -54 on the counts t44-46.5 and the beat/deictic t6-7.3) |
| 2026-11-08 15:44 IST | agent-13 | r7 movement: 906d80d3 (agent-01 count/raise_finger wrist) passes all 18 rows, whole take (flexext 21.5) and the true verify windows (flexext 20.8, bells 0.600 on the line); released behind parity; T2 parity 1.08 with the rebuilt life layer, 0.72 seat-only |
| 2026-11-08 15:58 IST | agent-13 | r7 movement: 8a45d961 (agent-01 MOVE_MIN_S 0.3, trunk lean 0.25 s, right drift x1.3) passes all 18 rows, whole take and verify windows at 30 fps AND resampled at 24 (bells 0.933 / holds 0.44 in the windows); released |
| 2026-11-08 17:21 IST | agent-13 | r7 movement: b4325b5b (agent-01 hand heading + finger ease) passes all 19 rows incl. finger_snap (whole 1.05 /min, windows 0), at 30 fps and an exact 24 fps solve; 30->24 interpolation error in the windows 0.62 cm (was 3.04); released |
| 2026-11-08 20:28 IST | agent-13 | r7 GATE OWNER (agent-09 rate-limited): branch fleet/agent-13/r7-gate off 178a28bf; agent-08 hand rows added (claw, DIP/PIP, fold_at_limit, cascade, thumb_flat/stiff, hold_over_collar; report hold_chest, claw_score); parity text time-matched; n/a-able move rows |
| 2026-11-08 22:10 IST | agent-06 | Editor boxes after the power cut. T2 (her) on agent-08's 928407cb: body, life, gates. Parity --shoulder 0.306 seat / 0.407 placed. Rest 19.18. Arms on _Arms: bust 3.56/3.81, side 1.25/1.31. hands_in_frame placed MCU 0.723 / CU 0.392 / WIDE 1.0. Breath z 2.65 mm @ 12.1/min. Waist: no visible skin. Catalogue v3 (30 ok, 3 SKIP) and 00:08 after v3 are in private/review/explain/hands/. FOUND: the place stage lifts her from spine_04 up by +2.6 z / -0.55 x (spine_03 0.00), so the resting hands float over the desk; --shoulder parity cancels it, and agent-13's --torso row and the rows on the placed dump now catch it. mp_pilot (agent-12 kling_her_t1) rendered CAM_WIDE + CAM_MCU 0-239 preview to private/review/explain/mp_pilot/kling_t1/ (parity 1.12 worst, p95 0.28). T (him): agent-01 66785bbe fails its own body check (hands_out_of_frame MCU 0.45, arm_outfit -1.2), and merged with 928407cb fails desk.finger; T stays stopped for the combined sha. |

### Round 7 her waist 2 + arm girth (agent-05, branch fleet/agent-05/r7-girth; task 917b, with agent-02, agent-06 on T2)

| IST (8 Nov) | What |
|---|---|
| ~20:00 | The operator: "some clipping near her waist", arms "a little bit (not much) thin". netflix_r7H WIDE f1034-1167: skin through the band's lower edge |
| ~20:30 | Cause: body.hide_under picks the skin to hide in the REF pose with an outward ray only; R7W2 was fitted seated and carried back to bind, so at her hip crease it sits INSIDE her skin there: never covered, and rings=2 widened each miss. agent-02 (current body): skin 0.75-0.79 cm out at +-40 deg (front hip crease), 6.3 cm under the band edge, ~170 verts, every frame |
| ~20:40 | hide_under: inside_cm (a short ray in along -normal also counts) + fill_max (small uncovered islands with the garment in reach everywhere). Her Body<Trousers 4.0 / inside 3 / fill 400, Top<Trousers inside 2. arm_girth.py: upper arm + forearm +10 % round the bone axis by her own arm weights (deltoid ramps in over 30 %, the watch band's 6.5 cm and the hands 0), the Top's sleeves by the same field; new _Arms assets, setplan EXPL_ARMS (default on) |
| T2 | arm_girth: radius upper 3.48 -> 3.83, fore 2.77 -> 3.04 (both sides), max move 0.47 cm, hands/watch 0, verts equal, Top bones = body's. Body<Trousers: inside 80, filled [120, 80, 79, 4, 4, 1, 1] (the hip crease; arms 7.1k and feet 3.5k islands untouched). agent-02: waist skin poke 0.79 -> none, fit 0.02; arms on _Arms rest bust 3.59 / side 1.73, gesture 3.97 / 1.71 (pass). T2 saved on the originals + the new hides until the girth is approved |

| ~21:30 | Orchestrator APPROVED by eye: the waist after = clean dark trousers, no see-through gap at the band; _Arms reads subtly fuller, sleeves follow, the watch sits fine. _Arms + the new hides = her level of record |

Her setup of record (any box, from r7-girth or a tree with it merged):
1. fmbridge with garment.py at r7-girth (body.hide_under inside_cm / fill_max) loaded in the editor.
2. Once per project (refuses to overwrite; already done on T2):
   `film-ue exec -c "STAGE='apply'; SCALE=0.10; exec(open('<tree>/films/host-studio/props/her_outfit_ue/arm_girth.py').read())"`
   -> SKM_Presenter_F_BodyMesh_Arms, SKM_Presenter_Top_R7W_Arms. `STAGE='check'` re-reads them (radius +10 %, hands/watch 0).
3. `set.py --who her --steps garments,dress` with EXPL_ARMS unset (= 1): the Body/Top on _Arms, then the hides
   Top<Trousers 2.5/inside 2, Body<Top 6, Body<Trousers 4/inside 3/fill 400; check the Body<Trousers line's filled
   list is the hip crease only (T2: [120, 80, 79, 4, 4, 1, 1]). Leaders pass, then save (assets + level).
4. Gates on it: agent-02 waist_skin_poke_cm <= 0 (WIDE), arms rest + gesture (bust >= 3, side >= 0.5).
EXPL_ARMS=0 gives the slim originals (with the new hides) for comparisons only.

2026-11-08 23:32 IST | agent-06 | r7I (the operator's look at her hands). Her offline body --perform on 963942f4 + agent-08 02505b92 (r7-boxb d5a05e8f) reported 0 issues, so T2 ran: cams -> body (pass, the offline rows) -> life -> place (check placed pass). Placed gates (dump with fingertips): parity 0.446 / --shoulder 0.309 / --torso 0.186 (placed = seat). claw 0, palm_to_camera 0, rest_contact 0, spread 3.2. finger_snap 9.0/min FAIL (known; rendered by the orchestrator's call). Rendered shots 1/2/11 at --preset final, 293 frames in 365 s (1.25 s/frame incl. warmup), private. Her solve.json re-derived from the existing face anims and box WAVs with no re-solve; 18 face assets' curve + uasset hashes identical before/after; lips numbers measured. T2 saved and stopped.
- 09 Nov (agent-05, branch fleet/agent-05/r7-nowatch): HER WATCH DROPPED (the operator on r7I WIDE: "watch is clipping
  through hand, drop the watch"). `props/her_outfit_ue/dress_her.py` WATCH = False: set.py's dress step destroys the
  HerWatch actor in her level and its check fails while one is there (no visibility key to undo). Studio/reel tools
  that still list HerWatch (studio.py makes it, reel/cast_gate.py checks it) are unchanged: re-dressing a reel level
  with this dress_her removes the watch there too.

2026-11-09 04:45 IST | agent-06 | Night of 08-09 Nov, box driver (T2 her, T him).
- Her r7J (agent-01 0fa53868): 0 FAIL. Parity 0.364 / 0.247 / 0.186, arms 3.72/1.28 and 3.97/1.32. Watch dropped first (agent-05 r7-nowatch; set.py dress, HerWatch actors [] checked, then save).
- Her finals A (netflix_r7A) and B (agent-08 ff93e054, netflix_finals_B): 9 shots, 923 frames at --preset final, about 1.4 s/frame. render.py's post() hit an ffmpeg stderr decode error after every shot rendered; encoded and synced by hand (post_manual.sh). B gates: 0 FAIL, parity 0.357 / 0.214 / 0.186.
- Orchestrator picked B; agent-11 composited it on T2 (netflix_r6_r7B), approved by eye and delivered. A's composite kept as the backup. Her head screen boxes (render px) were sent to agent-04 for the lower-third / panel geometry check. T2 saved + API-stopped.
- Him (box T, branch fleet/agent-06/r7-him e3f0bc15 = e7903a6e + agent-01 9dc4db55 + aad624a9): him_sweep on the box (8 Performer variants, rows only). REST_WRIST_UNDER=0.5 picked: TEST spans 0-179 + 422-480 pass every row, rest_contact 0; whole-take finger_snap 6.4/min still open for his finals. Confirmed with arm_track_who + naturalness on the box.
- His body build on aad624a9 then failed its own check (nothing written): desk.wrist (both wrists z 73.3 against the desk top 71.0 at t 0-0.4, the lowered opening rest) and floor.ball (+1.26 cm). Not framing-only (agent-04), so T saved + API-stopped. Next T run: agent-01's fix, body build first, then rows / LAYERS / flank / re-gate / head stages / 13 s TEST.
- His body reads stay on box T and are deleted after each run; only rows leave it.

2026-11-09 07:20 IST | agent-06 | Him, 05:00-07:20 (boxes T, T-b, T-c, T-d; branch fleet/agent-06/r7-him).
- Base: agent-01 3c2adc79 fixed desk.wrist / floor.ball, then their combined 73804954 (r7-him 4913ee72; garment_measure guards 29696d4c, b41a96a2). Body pass 1691 keys. Sweep: TEST spans all pass. Whole-take snaps 2.1/min fall only in graphics shots 5/7/9; the orchestrator ruled on-camera only, so 0. ROT_LAG_ADD=0.03 left out (TEST lag 29.8).
- No refit (orchestrator): agent-05's flank push at 05:01 only wrote /Game/Host/Fit/SKM_Host_Outfit_R7Flank. No him_flank.json, so set.py never dressed him with it; his original outfit stays.
- Spot: T was interrupted at 05:50, T-b at 06:04 and T-c at 06:18. T-d (g6.4xlarge, 1a) came up from the 05:56 image. Chains are resumable: stage markers on kali, a save after each stage, finals per shot with existing S3 shots skipped.
- Binding proof on T-d. Head state parity 102/102. cull_live identical. Fingertips: kali has no skeleton, so the box adds them (edit_track2 ax03 + tips_box). Tips p50 2.34 cm. On-screen parity 0.501, --shoulder 0.381, --torso 0.177. hands_in_frame MCU 0.61, CU 0.40, WIDE 1.0.
- Gate fails on 73804954: rest_contact_rendered (tented rests at t 2.8 and 7.6; agent-01) and head.drift_deg 2.668 (band 0.15-1.5). head_stages: seat 0.0, body 3.45, so the drift comes from agent-04's head plan baked on at sync. Fixed by agent-04 in c1e15f42 (his acting nods at half depth, beat nods off), picked onto r7-him as 4a231011.
- Black band (orchestrator stop-ship, cleared 07:1x): the binding stills showed a dark band round his torso. Level inventory: no stray actors, original components, leaders pass. Cause: view.still on a cold-booted T-d (image-backed disk, textures not yet resident). The first still was 41-86 luma darker over the torso; two re-renders on the warm editor match the 05:02 before-still there. chain_Tfin_him now renders two throwaway warm-up passes after every (re)start before shot 1.

2026-11-09 09:05 IST | agent-06 | His finals rendered (T-d; r7-him 2144fc7e).
- 71cba6b1 (agent-01 3680e60b REST_HOLD=True + agent-04 c1e15f42): head drift 1.484 (pass) but nods 0/min (the half-depth nods fall under the detector), and REST_HOLD=True added an on-camera snap (l 6.7 s, f161, CU; TEST 6.02/min).
- Box sweep of agent-01 84e46b3e (REST_HOLD False/True/0.2/0.3/0.45): no build met agent-04's rule. The orchestrator picked 0.2: TEST [], rest heel 0 frames over line-0.5, and its one extra snap (r 39.5 = f948) is in a graphics shot, so it doesn't count under the on-camera rule. Built as agent-01 857aa5b4.
- agent-04 5194d443: 4 payoff nods (W01/W03/W11/W17) at full depth, the rest at 0.2, beats off.
- T11c on 2144fc7e passed every gate. Body issues []. Rows TEST []. On-screen parity 0.506 / shoulder 0.386 / torso 0.177. rest_contact_rendered 0: one frame, f66 l (heel 3.72), excluded under agent-04's ruling as a lift onset; the gate's nearest-frame gesture_w was 0.075, interpolated 0.1415. Head gate: drift 1.158, nods 5.37/min, on_lens 0.917. hif MCU 0.609, CU 0.395, WIDE 1.0. The orchestrator passed the stills and the arms by eye.
- x/rc_frames.py lists rendered rest_contact frames with the track's gesture_w both nearest and interpolated. x/head_box_him.py gives his head screen boxes: shot01 MCU [732,329,1010,630]; panel shots 04/08/12 MCU_L about [261-266, 301-304, 581-585, 640-646].
- Finals 08:15-09:04, after the warm-up stills: 9 shots, 907 frames with handles, all in S3 Tokyo private renders/r7/explain/whatsapp_finals_him/final/ with an mp4 each. The script's final check misread the counts (a trailing blank line from the box shell); fixed.
