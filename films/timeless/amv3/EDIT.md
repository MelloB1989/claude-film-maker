# Timeless v3: every shot in one 3D stage (Blender) + EffectCraft finishing

**The user on v2 (2026-10-18):** "the transitions are not smooth at all, also the transitions are simple, something more 3d
crazy would be nice. use best of blender and effectcraft. everything must be mesmerising. it has to be perfect give your
best." They sent three reference edits for "how smooth the transitions are" (`/home/nikhil/code/film-making/work/refs_v3/`):
- `a/iXZkJuUqOS8.mp4`: eitaX, "We ready?" Spider-Man Brand New Day, 28 s, 1350x1080 (4:5), 30 fps
- `b/N3TshMrwhGk.mp4`: eitaX, Spider-Man 2 "Newest Tank", 35 s, 1920x1080, 30 fps
- `c/GKI0-Xw4f4w.mp4`: sanchezae, "We Ready?" Brand New Day, 23 s, 1350x1080, 30 fps

Contact sheets with frame numbers: `refs_v3/<x>/sheets/` (every frame, c) and `sheets2/` (every 2nd frame, a and b). The
research write-up with numbers is `films/timeless/amv3/REFS.md` (being written by the research agents).

v3 keeps v2's footage, song, cut frames, voice cues, 2D titles, outro and mix timing. **It replaces the camera, every
transition and the hero titles.**

## Why v2 felt rough (operator's frame study, v2 vs the references)
1. **v2 shots hold still.** Between transitions the picture barely moves (f40-48, f60-79 of v2 are near-static), then a
   2-frame whip snaps. In all three references the camera is *always* travelling: slow push/pull/roll drift that flows
   straight into the next transition's acceleration. There is never a dead frame.
2. **v2's transitions are short 2D moves with little blur.** v2 kept "cut+1 readable" and limited the blur. The references
   do the opposite: **2-4 frames of abstract, fully smeared picture** (radial/directional blur with chromatic split and a
   light leak) where neither shot is readable. The eye reads it as one continuous fast camera move, not as a cut.
3. **Velocity jumps.** v2 exits accelerate over 4-5 f but B often lands from a different speed/direction (a zoom-in into a
   whip, a spin into a static hold) and some cuts are plain hard cuts (f65 -> f66). The references always continue the
   direction: zoom into A -> B arrives zoomed-in and pulls out; roll clockwise -> B lands still rolling clockwise and settles.
4. **Flat flashes.** v2 used full-frame white flashes (f55-56). The references use coloured light leaks and bloom that come
   from the picture itself (warm orange, cyan) and only rarely a white frame on the biggest hit.
5. **2D titles over the picture.** The references' hero words are **big chunky 3D extruded letters inside the scene**,
   lit, in perspective, behind the subject, flying in, assembling, exploding into 3D chunks, and the camera flies *through*
   them into the next shot (eitaX: CHANCE, NEED, TOOK, PARKER, VENOM, YEAH, WE READY?, SPIDER-MAN; sanchezae: SPIDER-MAN /
   BRAND NEW DAY laid into the street).

## What the references do (operator's notes; REFS.md has the measured numbers)
- Shots last 14-60 f; transitions every 0.5-2 s; the whole edit is one continuous camera.
- **Zoom-through** (the workhorse, ~60 % of cuts): A accelerates into a point (expo-in, 4-8 f), 2-4 f of extreme radial or
  directional blur with chromatic aberration and a warm/cool light leak, B decelerates out of the blur (expo-out 8-14 f)
  and keeps drifting. c: 213-222, 317-322, 358-362, 379-382, 398-402; a: 266-270, 284-286, 300-302, 332-338, 348-352.
- **Eye portal**: push into an eye, the next shot is inside the iris, pull out of it (a: 60-70; c: 160-178). Smooth because
  the zoom never pauses and the inner shot is already moving.
- **Ring portals**: Doctor Strange sling ring, orange sparks, the next shot inside the ring (a: 166-180; a/c: red swirl
  rings 110-124, 436-444).
- **Subject-motion wipes and match cuts**: a hand or body crossing the lens wipes to the next shot (c: 494-499, 397-399).
- **Background swap / 3D camera**: the subject stays while the camera travels into a new 3D world (c: 280-300, 583-602).
- **3D text**: in perspective in the scene, lit, behind the subject, assembling and exploding (a: 198-262, b: 60-80,
  266-288, 420-430, 450-456, 540-548, 596-606, 630-638); text laid on the ground (a: 402-426).
- **Energy overlays**: lightning (b: 360-400), sparks, glints, lens flares; colour flashes of the scene's own hue.
- Grade: rich contrast, deep but not crushed blacks, saturated reds and teal, strong bloom on highlights.

## v3 architecture: "one camera, every shot a card in 3D space"
1. **Plates** (Python, VM): each shot's frames at comp frame rate with the speed ramp applied, from the 240 fps RIFE source,
   with 16-frame handles: `$AMV3_DATA/plates/<shot>/f_NNNNN.jpg` (NNNNN = comp frame, absolute). Also triptych panels
   `P1-P3`. Ungraded.
2. **Prep** (RunPod 4090): subject mattes (BiRefNet) and depth (Video Depth Anything) on the plates:
   `$AMV3_DATA/mattes/<shot>/f_NNNNN.png`, `$AMV3_DATA/depth/<shot>/f_NNNNN.png` (16-bit, near = white); eye/lens tracks
   `$AMV3_DATA/tracks/<shot>.json` ({"frames": {"<f>": [x, y]}}, clip pixels) for every shot with a focus point.
3. **Stage** (Blender 5.2, Cycles OPTIX on RunPod; CPU tests on the VM): `blender/amv3/stage.py` builds ONE scene from
   edl.json. Every shot is a **card**: a 16:9 plane, 1.92 x 1.08 m (1 px = 1 mm), emission shader playing the shot's plate
   in comp time (optionally depth-displaced, optionally alpha from the matte). One camera **CAM** (35 mm lens, 36 mm
   sensor) moves continuously through all 900 frames with real Cycles motion blur. Holds and flow transitions are core;
   signature transitions and titles are modules. Renders three passes per frame (below).
4. **Finishing** (EffectCraft, VM): composites the passes, grades per act (v2 GRADE lib), adds lens FX in each transition
   window (chromatic split, radial blur boost, lens distortion, light leaks, bloom; flash only where the EDL says),
   glow on the light pass, the 2D titles (v2 TITLES: subs, name cards, caption boxes), the outro, the watermark and grain.
5. **Mix** (Python): v2 mix re-aimed at v3's transitions (whoosh risers into each blur window, glass, electric, sparks).

### The motion rules (the smoothness contract; the stage's gate checks them)
- **The camera never stops.** Every frame of 0-819 has picture motion. Holds are C1 curves (Hermite) from the incoming
  transition's exit velocity to the outgoing transition's entry velocity. Measured on the references (REFS.md): hold drift
  is 1.5-3.5 %/f of zoom (45-100 %/s), never under ~1 %/f; a reversal takes 5-7 f and is smooth.
- **Measured transition shape** (REFS.md, ref c): A's attack is expo-in, the speed about doubling each frame over the last
  3-4 A frames (zoom +1, +4, +9, +20..30 %/f); 1-3 smeared frames (median 2); B leaves the smear at the SAME speed and
  decays expo-out (x0.75-0.85 per frame, 10 % of peak after 7-12 f); B's first 2-4 frames are also lens-defocused (real
  DOF rack focus) and carry 5-15 px of chromatic split fading over 6-10 f. Zoom sign may flip behind the smear; speed
  magnitude and the screen direction of pan/roll carry through.
- **Velocity is continuous at every window edge**: the camera speed changes by at most x1.35 per frame outside the
  intended accelerations; no step changes. Inside a transition the speed follows one ease (accelerate into the cut, decelerate
  out of it), peaking at the cut.
- **Direction continues through the cut**: zoom-in into A -> B arrives zoomed in and pulls out (or keeps pushing for
  `mode: push`); roll keeps its sign; a whip's direction carries into B's landing.
- **Real motion blur**: Cycles camera/object motion blur, shutter 0.75 frame (centred) in holds, up to 1.0 in transition
  windows. 2-4 frames around each cut are smeared on purpose. The landing must be sharp within 3-4 frames after the
  blur peak.
- **No dead frames, no black frames** (except the intentional open from black and the outro), no visible card edges
  unless the transition shows the card as an object in 3D on purpose (cube, flip, triptych, shatter), and then the void
  behind is a lit environment (dark act-tinted fog, web strands, bokeh), never flat black.

### Card space and camera state (shared by the core and every module)
- A card's "hold state" is the 2D picture transform v2 used: `s` = picture scale (1.0 = the card exactly fills the frame),
  `c` = [x, y] the card pixel at frame centre, `r` = roll in degrees (+ = picture turns clockwise on screen). Rates per frame:
  `ds` (d ln s / frame), `dc` (px/frame), `dr` (deg/frame).
- `ctx.pose(card, state)` -> camera world location + rotation that shows that state (camera facing the card's normal).
  Fill distance with the 35 mm lens = 1.92 * 35 / 36 = 1.8667 m; distance = fill / s.
- **Sets**: every shot has a home set (its card at its own world origin, 100 m apart). A transition may work in the home
  sets (camera moves on A's card, then **teleports** to B's set at the half frame `cut - 0.5`) or build a private set at
  its own origin with copies of the A and B cards (true 3D: B behind A, cube faces, tunnels). The camera teleports between
  sets only at half frames, and the shutter (<= 0.95 frame) never straddles a teleport.
- Transition contract: `bounds(T, ctx) -> {"A": state at w0 with rates, "B": state at w1 with rates}` declares the
  window's entry and exit; the core solves the holds to meet them; `build(T, ctx)` keys the camera inside [w0, w1) and
  adds objects. The entry and exit poses must equal `ctx.pose(card, state)` at w0 / w1 with matching rates (the gate checks
  this by finite differences).

### Passes (render outputs per frame, all 1920x1080, straight alpha PNG)
- `plate/` RGB: everything visible (cards + 3D transition objects + energy FX), the picture.
- `text/` RGBA: 3D titles only; the subject's matte card acts as a holdout so words sit behind the subject where
  `behind=True`. Finishing comps it over the graded plate.
- `light/` RGB on black: only the emissive FX (sparks, lightning, rings, glints, shard rims) for EffectCraft's glow (add).
- Optional `zvec` per-frame camera speed (json) for finishing's lens FX intensity.

## Transitions (one per cut, see CUTS in edl.py)
Flow types (stage core):
| type | 3D move |
|---|---|
| `open` | from black: the camera pulls back out of darkness onto S01 (scale 1.9 -> hold), depth parallax, light sweep |
| `zt` | zoom-through. A accelerates into its focus (expo-in to `peak` x), roll accumulates; teleport at the half frame; B starts at `land` x on its focus and decelerates (expo-out) into its hold drift. `mode: push`: B keeps pushing in. 2-3 smeared frames. |
| `whip` | 3D whip pan: A and B are neighbours on a ring of cards around the camera (or above/below for U/D); the camera yaws/pitches `angle` degrees with an ease-in-out that overshoots 2-3 % and settles. The gap between cards is filled by smeared light (act-tinted haze cards), never black. |
| `cube` | A and B on two faces of a cube; the camera pulls back slightly and the cube turns 90 deg (dir), real perspective, motion blur, edge glints. |
| `flip` | A swings open on a hinge like a door/comic page toward the camera revealing B behind; the camera pushes through the opening. |
| `slam` | B lands like a superhero landing: a fast dolly in with depth-displaced parallax (3D photo), camera shake, a dust shockwave ring. |

Signature modules (xfx-A, xfx-B, text3d):
| type | owner | 3D idea |
|---|---|---|
| `symbiote` (151) | xfx-A | black symbiote goo (metaball/geometry tendrils with glossy wet highlights) crawls in from the frame edges over Tobey, swallows the camera; S05 (black suit lens) emerges as the goo peels away |
| `eye_tunnel` (236-264) | xfx-A | push into Tobey's left iris (tracked); the iris opens as a hole in the card; the camera flies through a **multiverse tunnel**: walls of floating cards (frames of all three eras), web strands and light rings, spiralling (camera roll); exits through Andrew's lens into S09's pull-out |
| `sling_ring` (611-626) | xfx-A | an orange Doctor Strange spark ring (particles with motion blur, embers, sigil glyphs) opens on S24's kick; S25 is inside it; the camera pushes through the ring |
| `web_wipe` (680-692) | xfx-A | 3D web strands shoot from behind the camera across S27, wrap it and yank it away revealing S28 |
| `lens_shatter` (469-494, the DROP) | xfx-B | the camera slams into Andrew's lens (A09); on f480 the lens glass shatters into 3D shards (refraction rims, motion blur) that fly past the camera with a shockwave ring; Tom's lens (M01) pulls out behind them |
| `lightning` (430-445) | xfx-B | Electro's 3D lightning bolts strike across S14, crack it into shards lit from inside, S15 behind |
| `dome_shards` (overlay, 550-562) | xfx-B | real glass shards burst at the camera on top of the S20 -> S21 roll zoom-through |
| `triptych` (777-819) | xfx-B | three 3D comic panels slam in on 777/785/794 with camera parallax and depth; TIMELESS (text3d) lands at 802; on 819 everything shatters into shards flying past the camera into the outro |
| `text_fly` (327-345, 648-662) | text3d | the camera flies through the 3D title (AMAZING, SPIDER-MAN): letters rush past with motion blur, then the next shot (S11 dive / S26) |

## Titles
- `text3d` (Blender stage, text3d agent): AMAZING (S10), SPIDER-MAN (S25), BRAND NEW DAY (S31-S32), TIMELESS (triptych).
  Big chunky extruded condensed italic letters (the user's Novax look in 3D): bevelled, white-to-hue gradient face, glossy
  metal/emissive edge in the palette colour, a light sweep that crosses them, then they settle to a glowing outline
  state; lit by the act's colours; in perspective inside the scene and tracked to the card so they live in the shot;
  behind the subject (matte holdout) where `behind=True`. Animations: `assemble` (letters fly in from depth, rotate into
  place, staggered), `fly_in`, `slam_letters` (one letter per beat), `slam`; exits `fly_through@F`, `shatter@F` (explode
  into 3D chunks like eitaX a: 230-246).
- 2D (EffectCraft, v2 TITLES lib unchanged): `sub` (voice subtitles), `namecard`, `caption_box`, watermark.

## Look (finishing)
v2's per-act grade is the base (clean, crisp, no crushed blacks, no creamy highlights). Add the references' richness:
saturated reds/teal, deeper contrast, strong highlight bloom above a high threshold, light leaks in transition windows
in the act's colours (Tobey warm gold, Andrew cyan + amber, Tom red-orange), fine grain.

## Budget and machines
RunPod spend cap: $10 total for the project, ~$2.8 used by v1+v2 (balance 16.05 -> stop at 8.8). A 4090 pod costs
~$0.7/h. Test on the VM (CPU) at quarter/half res; the full stage render runs once per round on the pod.
Never Azure / az cli.
