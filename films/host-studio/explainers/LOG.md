# Explainers (round 6): log

Times IST. Box B driver: agent-07 (set, light, cameras, HER explainer). Box A: agent-06 (HIS explainer, replays set.py).

## Set, light, cameras (agent-07)

| IST | What |
|---|---|
| 16:20 | Brief in. Layout agreed with agent-01 (actor root on the chair mark (20,-20,0), yaw 0, forearms on the desk), agent-05 (SM_PodcastChair seat 45, SM_WalnutDesk 110x55 top 74, SM_MicBoom posed from the clamp (70,32.6,74) on the desk's +Y edge to a capsule at (44,-6,99)), agent-11 (EDL: CAM_MCU / CAM_CU / CAM_WIDE + CAM_MCU_L for the PANEL shots) |
| 16:50 | `setplan.py` (numbers + offline framing check) and `set.py` (the box driver) written. `python3 setplan.py --check --who her|him`: all rules pass (mic below and >2 mouth-heights clear of the mouth in every camera, eyes in the upper third, the lowered sign at u 0.71 in the MCU, CAM_MCU_L keeps her and the mic left of x 940) |

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
- Hand-off to box A: `set.py --box <A profile> --instance <A id> --who him` (same numbers with his eye height;
  `setplan.py --json --who him` prints the spec).

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
