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
- Alpha: panel shots and the lower third render twice, over black and over grey (the films explain-netflix-black / -grey: this timeline with the matte baked in; an env var
  does not reach the page), and tools/alpha.py
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

## Round 7: graphics v3 (08 Nov, IST)

The operator: the three.js graphics "can be improved a lot", and the videos must be energetic ("people should not be
bored"). v3 rebuilds every cutaway as a real 3D scene on the new engine kit `@kit/motion` (app/src/kit/motion, branch
fleet/agent-12/r7-gfx-core), to the shared style guide docs/STYLE_V3.md (both explainers). Scene code: v3/*.ts. The v2
2D scenes (scenes/) remain for the lead and the lower third.

- 01:05 brief (lead: agent-12; WhatsApp: agent-13). 01:20 STYLE_V3.md and the kit pushed.
- 01:23 style frames (title, oca, abr). Orchestrator: direction approved. Fixes applied: "300+ million MEMBERS" (not
  people), no clipped labels, all type inside a 5 % title-safe margin, the title rebalanced.
- 01:40 opening test (title + oca) approved. Fixes applied: labels draw over streams (kit Label), and the far library and
  cloud recede before the OCA close-up.
- 02:20 all shots built: title, oca, prefill (+panel), ladder, abr, buffer (+panel), planes, end. Renders on the
  operator's Mac (Apple M5, Chrome GPU, ~5 s per contact sheet) under the fleet render lock; tools/finals.sh makes the
  deliverables (full shots ProRes 422 HQ with 8-sample motion blur; panels and lower third ProRes 4444 via the
  black/grey matte pair and tools/alpha.py).
- SFX hit list for agent-11's mix: data/sfx_v3.json (tools/sfx.py, from the EDL word frames; the 9-cue vocabulary).
- 02:30-13:00 the Mac went off the network, so no GPU host. Finals moved to the build host's CPU: Chromium's SwiftShader
  inside the fleet image under the host's heavy-job lock (RENDER_FLAGS=--allow-software, LOCK in the container), at
  2-sample motion blur for full shots, 1 for the matte passes (~4.5 s per frame).
- The orchestrator's TEST verdict: the lower third covered the presenter's gestures in the MCU opening, so it now sits
  top-left, its lines wrapped and balanced so the plate ends at x 680 (her head box starts at ~704).
- The caption-band gate (tools/gate.sh) failed on six v3 shots at first: oca's platform rim, the 240p rungs in ladder's
  close-ups, abr's shelves mid-swing (plus slivers of unborn shelves), and three low labels (prefill, buffer, planes).
  Cameras and labels were moved, and all eleven deliverables now pass.

Facts on screen are unchanged from round 6 (facts_netflix.json): 300+ million members; Open Connect Appliances given
free, inside the ISP's network; nightly off-peak fill by predicted popularity; per-title ladders (rung lengths
illustrative, no numbers, "illustrative" on screen); chunks of a few seconds, a rung per chunk; AWS runs the control
plane (login, profiles, recommendations; it points the player to a box), the box streams the video.
