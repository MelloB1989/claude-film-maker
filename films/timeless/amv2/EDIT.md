# Timeless v2: the edit, from scratch (EffectCraft + Blender)

The first rebuild re-created the After Effects plan stage by stage. The user was not satisfied with it, so v2 starts over.
v2 keeps the brief (Tobey -> Andrew -> Tom, the first 30 s of the Timeless guitar cover, SAU_EDITZ, 1920x1080, 30 fps,
900 frames, a 3D outro). It throws away the old plan, look and code path.

- **EffectCraft (0.10.0) is the editor and compositor.** It plays the After Effects role: comps, footage with time remap, camera
  moves with motion blur, transitions, text, glows and grade. Everything is built by script from `edl.json`, and the
  `.ecproj` is a deliverable the user can open and edit.
- **Blender (5.2) is the 3D department.** It renders the SAU_EDITZ outro, the chrome TIMELESS title and the multiverse rift
  element. Each comes in as an RGBA image sequence, a footage layer in EffectCraft. The `.blend` files are deliverables.
- **Python** does only data prep: the EDL, RIFE 240 fps footage, subject mattes, the audio mix and the orchestration.

Source of truth: `edl.py` -> `edl.json`. Never hand-edit edl.json or the generated .ecproj.

## What was wrong with v1 (do not repeat)
- The grade was deep-fried: crushed blacks, blown and creamy highlights, halation everywhere, and the footage looked soft and
  muddy. **v2 is clean and crisp.** Highlights roll off and never clip into cream. Skin stays skin. Bloom appears only above
  a high threshold. There is a light sharpen (the clips are soft upscales) and only fine grain.
- Titles were inconsistent and some looked cheap: a pink haze halo, a cut-off "Spi", a dated bevel and a cheesy gold
  reflection. **v2 titles are few, sharp and legible**, with one visual language per kind (below).
- Ghost frames came from blending across source cuts, and some moves were stiff. **v2 uses 240 fps RIFE sources that never
  interpolate across a source cut. Every cut is a designed move.**
- The outro was plain (letters plus three circles). **v2's outro is a new 3D piece.**

## Concept: "three Spider-Men, one multiverse"
Each act is a universe with its own Spider-Verse earth number, palette and motion character. The acts are joined by two
showpiece transitions (the rift and the drop portal). The edit closes on a triptych of the three masks with a 3D chrome
TIMELESS, which shatters into the outro.

| act | frames | earth | motion | look |
|---|---|---|---|---|
| Tobey | 0-252 (guitar intro, quiet) | EARTH-96283 | floating slow motion (0.4-0.7x), long eased drifts, soft light sweeps | warm gold highlights, teal shadows, gentle halation |
| Andrew | 252-480 (build) | EARTH-120703 | rising: spins, whips, velocity ramps; shots tighten 48 -> 12 f | cool cyan/blue, amber sunset accents, crisp |
| Tom | 480-819 (drop) | EARTH-199999 | hard: impact cuts on the hits, shakes, ink frames, velocity ramps | rich red/orange vs steel blue, punchy |
| Outro | 819-900 | - | Blender 3D SAU_EDITZ | - |

## Beat map (measured on timeless_full.wav, 0-30 s; frames at 30 fps)
The guitar cover drifts against any fixed BPM grid, so cuts sit on measured onsets (spectral flux), not on a grid.
- Intro onsets: 17, 50, 83, 118, 151, 175, 201, 235, 251, 284, 300.
- Build: 317, 336*, 369*, 400, 416, 427, 436*, 453*, 468 (riser), then the **drop hit at f480**. RMS steps 0.37 -> 0.54 at
  479-480 and peaks around 484-488. (* = the cut is placed on the half-beat between weaker onsets.)
- Tom: 519, 536, 554, 570, 587, 604, 620, 631, 656 (3.2, the biggest), 686, 700, 732, 777, 785, 794 (three strong hits =
  the triptych panels), 802, 807, **819 (3.7, the outro hit)**, 828, 837, 844, 854, 860, 880, 892, 897.
- `HITS` in edl.py lists (frame, strength). Strength >= 2.5 gets a flash or ink frame and a shake; 1.8-2.5 gets a chromatic
  hit or a shake.

## Transitions (xout of shot A meets xin of shot B at the cut frame b == a')
The cut lands on the fastest, blurriest frame. Motion blur stays on (shutter 270 deg, 16+ samples). The velocity at the
cut is continuous: A's exit speed matches B's entry speed and direction. Exits accelerate (ease-in), entries decelerate
(expo-out). Mirror-edge Motion Tile hides the edges on every zoom-out, rotation and whip.

| name | A exit (last frames) | B entry (first frames) |
|---|---|---|
| `zoom_in` -> `pull_out` | A pushes 100 -> 260 % on `focus` over 5 f, ease-in | B lands from 260 -> 100 % over 9 f, expo-out. The classic zoom-through |
| `zoom_in` -> `zoom_in` | A pushes in as above | B continues pushing in from 100 % (no landing), for push sequences |
| `zoom_out` -> `zoom_out` | A shrinks 100 -> 55 % over 5 f (mirror tile) | B starts at 160 % and settles to 100 % over 8 f |
| `whip_l/r/u/d` | A slides 0 -> 1.3 frame widths in the direction over 4 f | B slides in from the opposite side, decelerating over 8 f |
| `spin_cw/ccw` | A rotates 0 -> 50 deg and scales 100 -> 150 % over 5 f | B rotates -50 -> 0 deg, 150 -> 100 % over 9 f |
| `impact` | hard cut ON the hit | B punches 115 -> 100 % over 6 f, decaying shake 6 f, flash 2 f (white or ink) |
| `light_sweep` | A drifts and a soft white light sweep crosses the frame | B appears under the sweep's brightest frame; 6 f, no dip to black |
| `open_lightsweep` | black | B fades up under a lens light sweep over 12 f |
| `glitch_dark` / `glitch_electric` | 3 f of RGB split, slice offsets and a 1-frame stutter | B enters with the same glitch decaying over 4 f; electric adds blue lightning glow |
| `rift` (f246-258) | push into Tobey's left iris (901, 390); the iris tears into a swirling multiverse rift (Blender RGBA element), with a caption flip EARTH-96283 -> EARTH-120703 | Andrew's lens (A01 played in reverse) pulls out of the rift |
| `drop_portal` (f468-492) | A09 slams into Andrew's lens (1110, 443) on the riser, with shake and speed lines | white flash on f480, a shockwave ring, chromatic split; Tom's M01 pulls out of the lens |
| `panel_slam` (f777-819) | M14 freezes into the first panel's frame | the triptych: one panel per hit (777, 785, 794), TIMELESS 3D at 802, the panels shatter into the outro at 819 |

## Titles (one language per kind)
- `sub`: voice subtitles. Clean white condensed caps with a soft dark shadow, word-synced (each word pops 0-2 f after it is
  spoken: voice_lines.json word times + the cue frame). Lower third (y about 930), never over eyes.
- `namecard`: actor name in wide-tracked thin caps, a thin rule and a small sub line (years). It slides in with a mask
  reveal and slides out. Lower left.
- `caption_box`: the Spider-Verse comic caption box: a yellow rectangle with a black ink border, offset print shadow and
  halftone fill, with the earth number in a bold comic face. It pops in with an overshoot and a 1-frame CMY misregistration.
  Top left.
- `novax`: hero words (user preference). A distressed condensed italic with a white-to-hue gradient fill, a light sweep
  with bloom, then it settles to an outline, plus a thin white sub and a tag on a rough black brush bar. Use a different
  palette each time. Where `behind` is set, the word sits behind the subject's matte. It must be crisp and fully in frame
  from its first frame.
- `blender_chrome3d`: the 3D chrome TIMELESS over the triptych (Blender RGBA render).
- Watermark: SAU_EDITZ, small, bottom centre, 70 % white, on every frame until the outro.

## Layer order in MAIN (top -> bottom)
watermark, titles, fx overlays (flash solids, ink frames, light sweeps, rift/Blender elements, letterbox), the camera-shake
adjustment, the grade adjustments (per act), fx adjustments (chromatic, glitch), the shot layers (each shot a precomp: the
footage with time remap and per-shot effects), with the transition keys on the precomp layers.

## Deliverables
`out/timeless/amv2/`: `Timeless_v2_SAU_EDITZ.mp4` (with the new mix), `timeless_v2.ecproj` (opens in EffectCraft with
relative or relinkable media), `blender/outro_v2.blend`, `blender/titles3d.blend`, `blender/rift.blend`, and the mix wav.
