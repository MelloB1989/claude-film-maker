# Explainer graphics v3: the style guide (round 7)

For both explainers (`films/explain-netflix`, `films/explain-whatsapp`), so they read as one series. The engine pieces
are in `app/src/kit/motion/` (`@kit/motion`, see the end of this file). Scene code stays in `films/<id>/scenes/`.

The operator's brief: **energetic, "people should not be bored"**. The v2 problems were dark UI cards, small thin
text and static diagrams that read as slides. v3 replaces slides with **objects in a lit 3D space, a camera that is
always going somewhere, data you can see moving, and big type that lands on the word.**

## 1. The five rules (when in doubt)

1. **Something moves in every frame.** The camera never stops: it drifts at rest and makes a move on each beat. Data
   flows continuously. No element sits fully still for more than ~0.5 s, except in the 12-frame end hold, where
   the camera keeps a slow drift.
2. **One idea per beat, said big.** At most ~6 words of type on screen at once. A hero word fills a third of the
   frame width.
3. **Land on the word.** Every element arrives on the VO word that names it, landing 0-3 frames AFTER the word starts
   (`cue(word)`). Each element gets anticipation, then a fast move, then an overshoot that settles.
4. **Light means data.** Accent light only marks what is alive: packets, streams and the thing the voice names. The rest
   is lit matte material in the dark.
5. **Depth always.** Three planes in every shot (foreground dust or a blurred element, the subject, a background
   haze or floor), real perspective and focus fall-off. Never a flat card facing the lens with nothing around it.

## 2. Palette

The series base stays the warm charcoal of the presenter's studio (the 07 Nov ruling), pushed deeper and richer so
the light reads.

| role | hex | use |
|---|---|---|
| `void` | `#0A0706` | the far background, behind the haze |
| `bg` | `#120E0B` | the ground and floor base |
| `haze` | `#2A1A12` | the volumetric glow behind the subject (radial, low on the frame) |
| `surface` | `#211A15` | matte objects: servers, boxes, slabs (a physical material, roughness 0.5) |
| `edge` | `#F2ECE4` at 0.25 | the lit bevel and edge highlight on slabs |
| `fg` | `#FFF6EC` | type: warm white, satin |
| `fgDim` | `#A89E92` | secondary labels |
| **accent** | Netflix `#E50914` / WhatsApp `#25D366` | the film's hero light: data, the named thing |
| `accentHot` | Netflix `#FF4D4D` / WhatsApp `#6BFFA8` | the hot core of a packet or stream (bloom carries the colour) |
| `accent2` | `#FFB547` | the secondary system: the control plane, the clock, warnings, "the network". Amber, both films |
| `cool` | `#53BDEB` | WhatsApp only: the blue tick and delivered state. Netflix never uses blue |

- Bloom is chroma-gated in post (neutral white never blooms). A glow is an **accent at emissive 3-6**, not white. A
  hot core is `accentHot` at 6-10.
- Per shot: one accent plus amber at most. Never both films' accents together.
- The ground is never flat black and never white.

## 3. Type (1920x1080; read on a phone)

| level | face | size (px cap height, at rest) | where |
|---|---|---|---|
| **Hero** | Bricolage Grotesque 800, **extruded 3D** (Type3D, depth 0.16 em) | 150-240 px tall glyphs | the one word or number of the shot ("300M+", "FREE", "CHUNKS") |
| **Headline** | Bricolage 800, extruded or flat | 90-120 px | a short phrase ("Every night") |
| **Label** | Geist 600, flat on a plane in 3D | **56 px min** | names of things ("ISP network", "AWS") |
| **Tag** | JetBrains Mono 500, caps, tracking +6 % | 40 px min | small facts, clock times, "4K / 1080p / 480p" |

- Nothing below 40 px. One weight jump per shot (800 hero vs 600 label). Labels sit at most 2 per object.
- Type sits in 3D space and catches the light: satin warm white (`Mat.satinBone`), an accent word with the lit rim
  (`Mat.accent`).
- Kinetic entrances (KineticText), glyph stagger 1-2 frames:
  - `rise`: glyphs come up from below the baseline, rotate from -70° on X, overshoot 6 %. The default.
  - `slam`: the word scales 1.6 → 0.96 → 1 in 6 frames, with a punch zoom (post zoom 1.03) and a sub hit. For the hero
    number only.
  - `flip`: glyphs turn on Y from 90°. For swaps ("1080p" → "720p").
  - `type`: mono glyphs appear one per frame with a cursor. For code and keys.
- Emphasis on a stressed word: an accent emissive pulse (rim 3 → 8 → 3 over 10 frames), and the glyphs scale 1.08.
- Exits: words leave by moving TOWARD the camera and blurring out through the focus plane, or they get pushed off by
  the next element. Never a plain fade.

## 4. Motion

- **Easing:** no linear moves except packets in flight.
  - Entrances: `antic` (a 2-3 frame pull-back of 4-8 %) → `outExpo` main move (6-10 frames) → `spring` settle
    (overshoot 6-10 %, damped by ~14 frames).
  - Camera: `inOutCubic` between keys, with an `outExpo` arrive on cuts.
- **Timing (24 fps):** a small element takes 6-8 frames, a hero 8-12 frames, a camera move 18-36 frames. Stagger
  groups by 2-3 frames per item, never all at once.
- **Energy budget:** each shot has one *big* move (a camera swoop, a slam, a burst). Put it on the line's key word.
- **Secondary motion:** idle objects breathe (a scale of ±1 % at 0.5 Hz, staggered), packets keep flowing, and
  status LEDs blink.
- **Data flow:** packets are glowing capsules (`Flow`), stretched along their direction of travel with speed (a 1.5-3x
  stretch), 30-120 in flight on a busy link. Links are thin `Beam` tubes that draw on before the packets ride them.
  Fan-out shows as one stream splitting into many. Buffers are segment blocks that drop in and stack with a spring.

## 5. Depth and camera

- **Lens:** fov 26-32 (a 40-50 mm feel). DoF on: f/2.0-2.8 with focus on the subject. Foreground dust and near
  objects fall well out of focus.
- **Camera language** (cam(t) in MotionScene):
  - **Arrive:** every shot opens with the camera already moving and decelerating into its first framing over 8-10
    frames (`arrive`: from 12-20 % further away, or a 6-10° yaw, with an outExpo settle). This is the cut transition:
    a presenter shot cuts INTO motion, never onto a still.
  - **Push** toward the subject on its reveal word. **Orbit** 8-15° round a 3D object while it builds.
    **Track** along a data path following a packet. **Rack focus** from foreground to background when the story moves
    there.
  - The always-on drift: ±0.6 % position noise and ±0.3° roll, never zero.
- **Planes:** foreground (z near, dust, the edge of a blurred object), subject, background (haze glow, the floor grid
  fading into the void, distant out-of-focus nodes).
- **Floor:** a dark reflective-ish floor with a 1-unit grid at 6 % fading out with distance: it grounds objects in a
  space.

## 6. Transition kit (shots are cut in the composite: the transitions live inside each shot)

| move | frames | use |
|---|---|---|
| `arrive` | first 8-10 | every full-frame shot: the camera lands in motion (whip-settle, push-settle) |
| `streak` | first 6 | optional: an accent light streak crosses the frame and reveals the scene (a whip feel). Use on the first gfx after a presenter shot |
| `flash` | 2 | a post flash of 0.15-0.25 on a slam (the hero number, "FREE") |
| `punch` | 4 | post zoom 1.00 → 1.035 → 1.00 on a hit |
| `glitch` | 4-6 | "Network dips?" only: an RGB split (ca) and shake |
| `hold` | last 12 | the end state is kept, with the camera still drifting slowly (the composite's handle) |

Panels (`*_panel`, alpha over the presenter): the card scales up from 0.92 with an overshoot from the presenter's side
(left → right) in 10 frames, then its content builds. The card is frosted dark glass (`#1A1410` at 78 %) with an accent
top edge line.

## 7. Safe areas

- **The bottom 15 % (y 918-1080) stays clear** of text and key visuals: the composite draws captions there. A floor and
  haze may pass through it.
- Title-safe is 5 % on the sides. Hero type is centred or on the thirds.
- Panels: the box x 1010-1860, y 150-930, with the content above y 770 in that box.

## 8. SFX hit list (for agent-11's mix)

Each film writes `films/<id>/data/sfx_v3.json`: `[{ "shot": "<gfx id>", "f": <frame on the shot clock>, "sfx": "<cue>",
"gain": <dB>, "note": "..." }]`. The cue vocabulary:

| cue | sound | when |
|---|---|---|
| `whoosh_in` | an airy whoosh, 8-10 frames, its peak at the settle | every camera arrive |
| `swoosh_fast` | a short whip | a streak or a fast camera swoop |
| `hit_sub` | a sub boom plus a transient | a hero slam (one per film section at most) |
| `pop` | a tight click-pop | small elements landing (labels, blocks): pitch up across a stagger |
| `tick` | a UI tick | counters, a clock, mono type-on (per glyph, low gain) |
| `data_stream` | a granular shimmer loop, f..f_end | packets flowing (duck under the VO) |
| `riser` | a 0.5-1 s riser into a payoff | before the end payoff and big reveals |
| `glitch` | a digital stutter | network dips |
| `chime` | a soft bright ping | success states (playing, delivered, the blue tick) |

Gain is relative to the VO bed: pops -18 dB, whooshes -14 dB, hits -10 dB, loops -24 dB.

## 9. Facts

Every graphic's facts are unchanged (`films/host-studio/explainers/facts_<film>.json`). Numbers keep the script's
softening ("300+ million", "100+ billion", "2 million (2012)"). No brand logos: generic glyphs only, and the words
Netflix, WhatsApp and AWS as plain text.

## 10. `@kit/motion`, the engine pieces

| piece | what |
|---|---|
| `MotionScene` | Scene3D for v3 shots: `build()`, `pose(t)`, `cam(t)`. Gives `cue(word)`, `arrive()`, `post(t)` (bloom, punch, flash, shake, ca), and the environment: haze, floor and dust |
| `KineticText` | Type3D with the word-synced entrances above, emphasis pulses and exits |
| `Flow` | instanced glowing packets along a curve: rate, speed, stretch, colour, a burst |
| `Beam` | a glowing tube that draws on along a path (and can pulse) |
| `Slab` | a rounded box or card in matte surface with a lit edge and an optional accent rim |
| `Label` | flat type (Geist/Mono) on a plane in 3D, auto-sized to px at the subject's depth |
| `motion` | `antic`, `spring`, `overshoot`, `settle`, `stagger`, `pulse`, `win` |
| `hdr(role, k)` | a palette colour as HDR linear (for emissive and basic materials that bloom) |
