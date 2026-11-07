# Round 6 explainers — log

Producer: agent-11. Times IST, 07 Nov 2026. Branch `fleet/agent-11/r6-explainers` (off `film/host-studio`).

## What is here

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

## Timeline

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

## Fact check

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
<<<<<<< HEAD

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
=======
- 16:40 `composite.py` written; WhatsApp placeholder rendered on the build host (3 m 52 s with the ProRes master).
  First look: cuts, panels, lower third and the kinetic captions land; captions split "over a hundred / billion" →
  chunking rewritten (clauses at punctuation, long clauses split evenly, never after a lead-in word).
- 16:46 placeholder cuts of both films (graphics + VO + mix + captions + lower third + grey presenter slugs), timing
  locked: out/explainers/placeholder/{whatsapp,netflix}_r6_placeholder.mp4 (+ .srt) in the shared worktree.
- 16:55 ruling: captions on every line, over graphics too, one band in the bottom 15 %. Placeholders re-rendered.
  agent-09 QA on them: captions.text_match 1 (157/157, 144/144), onset 84 ms, -14.1/-1.7 and -14.0/-1.7, 1080p 48 kHz.

## Running the composite on a box (drivers)

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
>>>>>>> origin/fleet/agent-11/r6-explainers
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
