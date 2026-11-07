# Round 6 explainers — graphics brief (producer: agent-11)

Timing source of truth: `edl/<film>.json` (every shot's frames, its VO lines and every word on the shot's own clock:
`words[].f` = frame from the shot's first frame). Re-run `python3 films/host-studio/explainers/edl.py` after a VO
rebuild; scene lengths follow. 24 fps, 1920x1080, 16:9.

## One shared look (both films, so they read as one series)

- **Series tag** (lower third on the first presenter shot, frames 12-84): `SYSTEM DESIGN IN 60 SECONDS` in Geist 600
  caps, tracking +8 %, over the film's topic line in Geist 400. No presenter names (the repo is public).
- **Ground (dark-warm, matching the karma studio set):** warm charcoal `#120E0B` → `#1E1813` radial with a soft amber
  glow `#C8874A` at 6 % top-left (the key light's side), a faint 64 px blueprint grid at 4 % warm white, slow parallax
  drift, soft film grain (2 %) and a vignette. Never flat black, never pure white.
- **Type:** titles Bricolage Grotesque 800; labels and UI Geist 500/600; numbers, keys, packets, code JetBrains Mono
  500. Fonts: `fonts/src/` and `app/public/fonts/`.
- **Colour:** neutrals `#F2ECE4` (text), `#A89E92` (secondary), `#241D18` (cards, 1 px `#3B3129` border, 14 px radius,
  soft shadow). One accent per film: WhatsApp `#25D366` (blue-tick `#53BDEB`), Netflix `#E50914`. Accent only on the
  thing the voice is naming, at the moment it names it.
- **Motion:** eased (cubic out, 10-16 frame moves), elements build on the VO word that names them (`words[].f`, land
  0-3 frames AFTER the word starts), nothing pops without a 4-6 frame ease, depth via subtle 2.5D parallax and
  soft glow on live links. Packets travel as small glowing capsules along curved paths. Hold the final state at least
  12 frames before the cut.
- **No brand logos** (no WhatsApp/Netflix/AWS marks): use generic glyphs (chat bubble, play triangle, server racks,
  cloud). Words "WhatsApp", "Netflix", "AWS" may appear as plain text.
- **Numbers on screen** must match the script's softening: "100+ billion messages a day", "2 million connections on
  one server (2012)", "300+ million members". Extra on-screen facts allowed only if sourced in LOG.md (e.g. groups up
  to 1,024, end-to-end by default since 2016).

## Deliverables per scene

- `<scene>_full.mov`: full frame, ProRes 422 HQ, exactly the shot's frame count from `edl/<film>.json` (+12 tail
  handle frames that keep the end state).
- `<scene>_panel.mov` for the "panel" scenes: ProRes 4444 with alpha, the graphic laid out inside the right panel box
  x 1010-1860, y 150-930 (presenter sits left of x 960), on a frosted card (`#1A1410` at 78 %, 18 px radius,
  1 px `#3B3129`); everything outside the card transparent.
- Keep a full-frame version of every panel scene too (fallback if a presenter shot fails).
- Upload: `s3://rf-render-788655295054-aps1/ue-linux/r6/gfx/<film>/` (graphics carry no face data), or hand the box
  driver a branch + render command. `composite.py` reads `<scene>_full.mov` / `<scene>_panel.mov` from that folder.
- Captions are NOT the graphics' job: composite.py draws word-chunk captions on presenter and panel shots. Full-frame
  scenes carry their own keyword text; keep the bottom 160 px clear of important content on panel scenes.
