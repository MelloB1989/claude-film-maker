# explain-netflix — graphics log (round 6, 07 Nov, IST)

The cutaway graphics for the Netflix explainer ("How Netflix streams to 300 million people without buffering").
Timing, look and deliverables follow agent-11's `films/host-studio/explainers/GFX.md` and `edl/netflix.json`
(branch fleet/agent-11/r6-explainers); `data/edl.json` is a copy of the EDL.

- 16:20 brief. Blocked the shots out from the outline: title, oca, prefill, ladder, abr, buffer, planes, end card,
  lower third.
- 16:45 EDL + cue sheet landed: 24 fps, per-shot frames, every word on the shot's clock. Each scene builds on its VO
  words (`NfScene.cue(word)`: the word's frame + 2), shots run their EDL frame count + a 12 frame tail.
- 16:55 palette: warm charcoal series base (orchestrator ruling, GFX.md), Netflix red #E50914 accent, amber #C8874A
  secondary (the control plane, the network line, the fill window). No logos: generic server, house, cloud, TV glyphs.
- 17:10 contact sheet v1 to the orchestrator (s3 ue-linux/gfx/explain-netflix/review/contact_v1.png).
- 17:35 orchestrator notes on v1: labels >= 28 px, an overlap in planes, the internet cloud too faint, more depth.
  Done: every full-frame shot now stands on a 3D stage (lib.ts): studio, cards, diagram, glow and labels on five planes
  at different depths, a slow seeded dolly + drift, the engine's depth of field (the studio falls well out of focus,
  cards sit just behind their content); chunk blocks and appliances drawn with depth; labels min 28 px; non-essential
  labels dropped.
- Alpha: panel shots and the lower third render twice, over black and over grey (VITE_NF_MATTE), and tools/alpha.py
  recovers straight alpha (glow kept as coverage max(a, max(B))); ProRes 4444 with alpha.

## Facts on screen
- "300+ million members": the script's softened figure (Netflix reported 301.6 M paid memberships in Jan 2025).
- Open Connect Appliances are given to qualifying ISPs free and sit inside their networks (Netflix Open Connect
  overview, openconnect.netflix.com).
- Nightly fill in off-peak hours with titles predicted to be popular (Open Connect "proactive caching" / fill window).
  The demand curve is an illustrative shape, no axis values beyond clock hours.
- Per-title encoding (Netflix Tech Blog, Dec 2015): ladder bars are illustrative, no bitrate numbers on screen.
- ABR: chunks "a few seconds", the player picks a rung per chunk from its throughput and buffer.
- Control plane on AWS (sign-in, profiles, recommendations, search, licence, steering to an OCA); video from OCAs.
