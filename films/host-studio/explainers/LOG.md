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
    aws s3 sync s3://rf-render-788655295054-aps1/ue-linux/r6/gfx/<film>/ /srv/r6/<film>/gfx/
    python3 /srv/r6/explainers-src/films/host-studio/explainers/composite.py --film <film> \
        --presenter /srv/r6/<film>/presenter --gfx /srv/r6/<film>/gfx --out /srv/r6/<film>/out --tag v1
    aws s3 cp --recursive /srv/r6/<film>/out/ s3://rf-render-788655295054-aps1/ue-linux/private/renders/r6/review/explain/

`--placeholder` lets any missing presenter shot or graphic stand in as a labelled slug (a partial cut for review);
without it a missing input stops the run and names the file.
