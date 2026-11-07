# explain-whatsapp: log (agent-08, round 6, 07 Nov 2026, IST)

The graphics for the WhatsApp explainer ("How WhatsApp delivers 100 billion messages a day"): nine beats built on the
engine's Scene2D, timed by agent-11's EDL (`data/edl.json`, copied from fleet/agent-11/r6-explainers
`films/host-studio/explainers/edl/whatsapp.json`; every shot is its EDL length + 12 tail frames).

- `films/explain-whatsapp`: every beat full frame, back to back (the review cut; `<scene>_full.mov`).
- `films/explain-whatsapp-panel`: the panel beats (connect, ticks, media) in the GFX.md panel box (x 1010-1860,
  y 150-930) over black, then over grey; `tools/matte.py` pulls straight colour + alpha from the pair
  (`<scene>_panel.mov`, ProRes 4444).
- `tools/deliver.py FULL.mov PANEL_MATTES.mov OUTDIR [--png]` cuts the per-scene movs.

## Facts on screen, and their sources

| on screen | source |
|---|---|
| 100+ billion messages a day | WhatsApp (Will Cathcart), Oct 2020: "100 billion messages a day" |
| 2,000,000 connections on one server (2012) | WhatsApp engineering blog, "1 million is so 2011", Jan 2012 (2M+ TCP connections on one FreeBSD/Erlang box) |
| one Erlang process per connection, a few KB each | WhatsApp's Erlang talks (Rick Reed, Erlang Factory 2012/2014); a BEAM process starts at ~338 words (~2.7 KB) |
| delivered, then deleted | WhatsApp FAQ/privacy: messages are deleted from servers once delivered; undelivered ones are kept up to 30 days |
| ✓ / ✓✓ / blue ✓✓ | WhatsApp FAQ "How to check read receipts" |
| encrypted once, server fans out; groups up to 1,024 | WhatsApp security whitepaper (Sender Keys for groups); group limit 1,024 (2022) |
| Signal protocol, E2E by default since 2016 | WhatsApp/Open Whisper Systems announcement, 5 Apr 2016 |
| media: encrypted blob in a blob store, key in the message | WhatsApp security whitepaper, "Transmitting media and other attachments" |

## Timeline

| IST | |
|---|---|
| 16:21 | brief in; worktree, engine read |
| 16:45 | agent-11's EDL + GFX.md in; retimed to 24 fps, words on each shot's clock |
| 17:05 | palette ruling: warm charcoal base + #25D366 accent (GFX.md) |
| 17:10 | render box i-015fd21ff361148cc set up (Chrome, bun, sharded software render), shared with agent-12 |
| 17:15 | contact sheet v2 to the orchestrator |
| 17:40 | v3/v4: labels >= 30 px, depth (perspective floor, parallax planes, contact shadows, extrusion, near bokeh), caption band y > 0.85 clear by clip |
| 17:50 | finals rendering on the box (10 shards per film) |
| 17:00 | finals v1 rendered on the box (1028 full frames + 818 matte frames, 10 shards each, ~70 s per film at ~13 fps) |
| 17:05 | self-review: Erlang callout, queue 'waits', key pill overflowed their boxes; fixed (5a90a2d1) |
| 17:10 | finals v2 rendered from 5a90a2d1 and uploaded to s3://rf-render-788655295054-aps1/ue-linux/gfx/explain-whatsapp/ (the box role cannot write ue-linux/r6/gfx/) |

## Deliverables (s3://rf-render-788655295054-aps1/ue-linux/gfx/explain-whatsapp/)

- `<scene>_full.mov` for all nine beats (title, connect, erlang, store, ticks, group, e2e, media, end): ProRes 422 HQ,
  1920x1080, 24 fps, EDL frames + 12 tail frames.
- `<scene>_panel.mov` for connect, ticks, media: ProRes 4444 with alpha (straight), the card in the panel box;
  `<scene>_panel_png.tar`: the same as RGBA PNGs.
- `review/review_full.mp4` (all beats back to back), `review/review_panels.mp4` (the panels over a warm stand-in plate).
- Alpha check: outside the card only its soft shadow (max alpha ~0.05 at the card's edge, 0.12 just under it); card
  ~0.85 (0.78 card over its shadow).
