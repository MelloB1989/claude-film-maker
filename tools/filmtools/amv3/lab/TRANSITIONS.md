# EffectCraft 0.10 transition effects on real cuts (task v3-finish, operator request 2026-10-18)

Probe: `lab/transitions_probe.jsx` (one comp per pair x effect, 12 f, A = end of the outgoing clip over B = start of the
incoming clip, completion eased 0 -> 100 over frames 2..9, cut on frame 6). Pairs: S12 -> S13 (A04 bridge flip ->
A05 top-down fall) and S26 -> S27 (M09 punches -> M10 tank snap), handover 60 fps clips, no grade.
Rendered at half res locally (`render-frame --scale 0.5`); strips `out/tprobe/strip_S12S13.png`, `strip_S26S27.png`
(rows = effects, columns = frames 2-9).

    sed "s#OUT_PROJECT#$PWD/build/amv3/transitions_probe.ecproj#" tools/filmtools/amv3/lab/transitions_probe.jsx > build/amv3/tp.jsx
    effectcraft-cli script build/amv3/tp.jsx --empty
    effectcraft-cli --project build/amv3/transitions_probe.ecproj render-frame --comp T_S26S27_shatter --frame 6 --scale 0.5 --out x.png

| rank | effect | what it looks like (seen in the strips) | premium / cheap | ms/frame (half res, 4-core box) | where in the edit |
|---|---|---|---|---|---|
| 1 | **Shatter** (Glass, 14 reps, extrusion 0.15, force radius keyed 0 -> 0.9 over 4 f, gravity 0) | A breaks into real extruded 3D glass shards that tumble off and reveal B underneath; reads as an impact, holds up at speed | **premium** on a hit (dark side faces; give it a rim light / Bevel and a light-pass glint) | 540 | accent the **slam C22** and the punches (S26 shake@656, punch@508/631/700/732) as an overlay burst; a cheaper 2.5D alternative to Blender shards where Blender has none (dome_shards and lens_shatter stay Blender) |
| 2 | **Gradient Wipe** driven by a matte or depth (probe used A's luma) | B grows out of A along the gradient; with the subject matte it becomes the refs' subject-motion wipe (c 494-499) | **premium** with matte/depth + 2-4 f soft edge + motion blur; cheap-looking with plain luma (blotchy) | 540 | the new **layer** cuts (C02, C06 keep; C09, C30 sweep) as a finishing assist on the matte edge; depth-driven for whips C13/C19/C23/C29 (far plane first) |
| 3 | **CC Light Rays** (on B, intensity 320 decaying x0.62/f) | volumetric rays out of B's own highlights, decaying in 4-5 f | **premium** if kept to 3-5 f and colour-from-source | ~1200 (with Burst) | landing accent of the nested zooms and hits (C01, C05, C12, C18, C25 landings; the triptych slams 777/785/794) |
| 4 | **CC Glass Wipe** (gradient = A, displacement 60, softness 25) | refractive liquid edge (B seen through warped glass of A) | premium-ish, organic | 480 | **symbiote C04** (goo edge), **web_wipe C27** enrichment, a soft match on a layer cut |
| 5 | **Card Wipe** (5x9, random axis/direction, 35 % timing random, camera Y -14) | a wall of cards flips over from A to B in 3D | mid: black gaps between cards look cheap; needs a lit/blurred void behind and a slower 10-14 f window | 590 | **cube C11** alternative (comic-panel feel), or a hit on the drop build; not for whips |
| 6 | **CC Twister** (axis 30) | the frame twists like a ribbon/page with shading, B on its back | mid-cheap: reads as a 2000s slideshow transition | 1030 | flip **C03** alternative at most |
| 7 | **CC WarpoMatic** (B revealed, warp 90) | brightness-driven warp dissolve, very close to Glass Wipe | mid | 550 | covered by Glass Wipe |
| 8 | **CC Light Wipe** (round) | a hard white ring iris opening | **cheap** (flat white ring) | 320 | no (the sling ring/eye portals are Blender) |
| 9 | **CC Scatterize** (scatter 260, twist 90) | A dissolves into coarse noisy pixel dust | **cheap** (noise, no light) | 930 | no |
| - | **CC Light Burst 2.5** (on A into the cut) | at intensity 200 / ray length 140 it whited the frame out for 3 f (too strong in this probe) | needs a retest at ~60 / 40 | (incl. above) | possible pre-cut zoom streak accent; the finishing already has radial smear + leak there |

Notes: none of these replaces a whip (the motion is the transition; whips stay Blender camera moves with smear).
All completion-based transitions are 2D wipes at heart; the premium ones are those that bring light or depth
(Shatter's real 3D pieces, rays from the picture's highlights, matte/depth-driven wipes). Render cost is negligible
next to the 0.4-1.5 s/frame finishing comp.
