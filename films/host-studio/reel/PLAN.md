# karma — the launch reel (PLAN v2)

A 65-second cinematic reel that introduces the karma studio and its two presenters, for social: a 16:9 master
(3840×2160) and a 9:16 cut (1080×1920) cropped from it, plus a 45 s cut.

**v2 (2026-11-01) is the operator's review of the v1 preview applied.** What changed, and why:

- **No shot singles out one object.** v1's macro passes (the V-and-heart polaroid, the drone, the coin, the crate's
  KARMA, …) are gone. The easter eggs stay on the set and pass by inside wider, unhurried glides; nothing is centred,
  held on or racked to. The viewer discovers them, or doesn't.
- **The studio is revealed piece by piece, then whole.** Shelves → credenza and records → window and olive → slat wall
  and the (dark) sign, one glide each, the light falling from morning to blue hour across them; then the first and
  only full view of the room (the payoff), the sign igniting on the drop, the same wide at night.
- **More night.** The night wide (S12), a night glide along the shelves (N01), and every presenter shot at night.
- **Lines that tease, not explain.** Four short lines, 8.3 s of speech in all (v1: ~16 s).
- **The look:** agent-08's lighting/material pass on the set (studio.py and light.py's values) is what the renders use.

- **Shots:** 13, in one master sequence, 1560 frames at 24 fps (65.0 s), every cut on a bar line of the 96 bpm score.
- **Shot table as code:** [`shots.py`](shots.py) holds every shot's timing, lens, camera keys, focus, light state,
  cast, 9:16 crop **and the voice lines (`LINES`)**. This document's shot list is generated from it
  ([`plan.py`](plan.py)); build.py, motion.py, light.py, perf.py, vo.py, mix.py and cut.py read it. Change the table.
- **Previs v2:** [`previs/v2/contact.jpg`](previs/v2/contact.jpg): the new glides at the start, middle and end of
  each move (scratch cameras in the level's own day light, so the light is not the reel's; framing and lens only).

## 1. Concept and tone

**"You found us."** The reel is a day in the studio compressed into a minute, seen as a visitor would discover it:
an empty room in the morning, its corners one at a time, never the whole; at blue hour, finally, the whole room; on the
drop the karma sign lights letter by letter and the room becomes its night self. A slow look at the shelves by night,
and only then the people, who are expecting you. They give nothing away.

Tone: calm, warm, premium, a little playful at the end. Slow, deliberate camera (sliders and cranes, no handheld), real
lenses on a full-frame back, shallow depth of field that drifts with the move. The cuts fall on the bar lines; the energy
comes from the light and the music.

Rules:

1. **Light is the story.** Day → golden → dusk → blue → ignition → night on one shared light timeline: every shot
   sits at its true time of day and the cut never jumps in light.
2. **Areas, not objects.** Every glide frames a whole area with several things in it, keeps moving, and is aimed a
   little ahead of its move or along it, never at a thing. Focus drifts slowly (a few cm of distance over the shot),
   so details fall in and out of sharpness by themselves. No racks onto objects, no push-ins onto objects, no holds.
3. **The wide is earned.** The whole room is seen once by day's end (V05), and once at night (S12, the same frame).
4. **The presenters are introduced by light and focus**: a key light ramp for him, a focus pull for her.

## 2. Music, beats and structure

**Tempo: 96 bpm, 4/4.** A beat is 15 frames, a bar 60 frames (2.5 s); 26 bars = 65 s. **The score's sections and
every bar line are unchanged from v1** (the ElevenLabs take, conformed by agent-11's score.py), so the score is not
re-generated; the effects and the mix follow the new shots and lines.

| Section | Bars | Time | Shots | Music | Light |
|---|---|---|---|---|---|
| A. Morning | 1–4 | 0:00–0:10 | V01 shelves (bars 1–3), V02 credenza begins (bar 4) | felt piano, warm pad, vinyl room tone; no drums | DAY |
| B. The reveal | 5–12 | 0:10–0:30 | V02 (to bar 6), V03 window and olive (7–8), V04 slats and sign (9–10), V05 the room (11–12) | the soft kick enters on bar 5 (mid-V02), sub on 7, the groove arrives filtered on bar 9, the riser over 11–12, bar 12 beat 4 drops out (the breath) | DAY → GOLDEN → DUSK → BLUE |
| C. Ignition (the drop) | 13–14 | 0:30–0:35 | S11 sign, S12 the room at night | **the drop on bar 13 beat 1** | IGNITION → NIGHT |
| D. Night, then him | 15–18 | 0:35–0:45 | N01 night glide (15–16), S13 him (17–18) | the drumless breakdown under N01; the groove returns on bar 17 with his reveal | NIGHT → NIGHT+KEY |
| E. Hand-off, her | 19–22 | 0:45–0:55 | S15 hand-off, S16 her | the lift on bar 21 with her | NIGHT+KEY |
| F. Together, title | 23–26 | 0:55–1:05 | S17 together, S18 title | the motif returns; the last chord on bar 25 rings over the title | NIGHT → NIGHT-DIM |

The beats hit on purpose (frame = (bar−1)·60 + (beat−1)·15):

- bar 5 beat 1 (f240): the first kick, mid-glide along the credenza (no cut: the room is waking, not being shown).
- bar 12 beat 4 (f705): the needle drop's crackle on the wide (the turntable is in the room), then silence.
- **bar 13 beat 1 (f720): the drop.** The sign's letters on beats 1, 2, 3, 4 and 4& (f720, 735, 750, 765, 772).
- bar 14 beats 1–4 (f780–825): the four downlight groups pop on, one per beat (S12, the V05 frame at night).
- bar 17 beat 1 (f960): the groove returns on his silhouette; **bar 17 beat 3 (f990)**: his key light ramps up (12
  frames) and his eyes come up to the lens; **bar 18 beat 1 (f1020): L1.**
- bar 20 beat 1 (f1140): the focus pull from him to her (18 frames); L3a on f1158.
- bar 25 beat 1 (f1440): the last chord; the title fades in over beats 2–4. f1536–1559: the fade to black on the halo.

### Voice lines

Him and her, six utterances in four lines, **8.3 s of speech** in 65 s. Short, playful, confident; nothing explains,
everything teases. Text and frames: `shots.LINES` (the first word lands on the frame given).

| Line | Who | Voice starts | Text | Beat | Delivery |
|---|---|---|---|---|---|
| L1 | him | f1020 (bar 18) | "Took you long enough." | the tease: he was expecting you | an amused, unhurried drawl, a small smirk after |
| L2 | him | f1095 (bar 19 b2) | "Ask her what's next." | the hand-off | light, a half-turn of the head to her |
| L3a | her | f1158 (after the pull) | "Nice try." | the wink: she won't tell | dry, a half-smile to the lens |
| L3b | her | f1215 (bar 21 b2) | "Some things you have to see for yourself." | the intrigue | calm, a beat after "Some things" |
| L4a | him | f1350 (bar 23 b3) | "What goes around…" | the sign-off, set up | warm, trailing |
| L4b | her | f1386 | "…comes around. That's karma." | the sign-off, landed | a beat before "That's karma.", a smile |

Voices: ElevenLabs `eleven_multilingual_v2`, **Tarun** for him and **Tripti** for her (the voices auditioned and
chosen in v1, same settings). 3–5 takes a line, chosen on spectrograms and measures: `vo_selects.json` says which and
why. The leading ellipsis of L4b is the captions' only: read aloud it gave a breathy artefact, so the voice is sent
the words without it (`vo.py spoken()`).

### Sound design (changes from v1)

The macro foley that belonged to single objects (book cloth, polaroid flick, glass tick, coin ring, pickaxe tink,
gimbal whirr, LED blip, keystrokes, calendar page) is **dropped**: it would point at the objects the picture no longer
points at. The room speaks instead: room tone, birds by day thinning to crickets and a far city by blue hour, the
sheers breathing on V03, the needle drop and crackle into the drop, the ignition's relays and hum, the downlights'
contactors, his key light's thunk (now f990), light cloth on the presenters' turns. Mix: −14 LUFS, −1 dBTP, the score
ducking ~8 dB under the voice.

## 3. Lighting states

One shared light timeline (`light.py`) moves the room through these states; each shot sits at its time. **v2 moves
the state boundaries** so each reveal glide sits in its own light. agent-08's pass changes the values (studio.py and
light.py's constants), not these times.

| State | When (v2) | Shots | What changes |
|---|---|---|---|
| DAY | f0–180 | V01 | studio.py's day, **halo off** |
| GOLDEN | f180–480 | V02, V03 | the sun 28° → 8°, 5100 K → 3200 K, 30 → 8 klx; WindowSky warms; exposure 8.3 → 8.8 |
| DUSK | f480–600 | V04 | the sun 8° → −3°; the window cools; shelf LEDs 1.3 → 1.5; exposure → 9.2 |
| BLUE | f600–720 | V05 | studio.py night's sky; **the window reads blue**; only LEDs and the candle; sign off |
| IGNITION | f720–780 | S11 | the halo letters on in turn on the beats (**v1's render showed the whole halo lit from f720: fix in progress**) |
| NIGHT | f780– | S12, N01 | the four downlights pop on, one per beat in bar 14; **the window blue-black** (v1's S12 had it white) |
| NIGHT+KEY | f960–1440 | S13–S17 | the presenters' lights; hair and rims from f960 (him a silhouette), **Key ramps f990–1002** |
| NIGHT-DIM | f1440– | S18 | practicals −30% over two bars; the halo holds; fade to black f1536–1559 |

## 4. Shot list

Coordinates are cm in the studio's frame (back wall at x = −260, camera side +X, screen-left +Y). The presenters'
reel marks: him at (30, 40, 0), her at (−50, −55, 0), both facing the camera (+X). Shot ids kept from v1 keep their
frames (S11, S12 are unchanged and already rendered); the new ones are V01–V05 and N01.

<!-- shots:begin -->

### V01 · The shelves — 0:00.00–0:07.12 (bars 1–3, f0–179, 7.5 s)

- **Camera:** 40 mm full frame, T2. A slow crane down the four shelves, top board to bottom, 100 cm, drifting 25 cm screen-right to left and a little oblique, so the boards and their things stream up through the frame in parallax. From `[-90, -178, 250]` → `[-90, -153, 150]`, aimed at `[-250, -128, 140]`.
- **Focus:** +0 f: 178 cm, +90 f: 192 cm, +180 f: 180 cm.
- **In frame:** the shelves as a whole, the full 150 cm width, two to three boards tall at a time: books, vases, frames, the maker's things, the trailing pothos at frame left, the LED strips under each board; nothing centred, held on or racked to: the details pass by and the eye finds them.
- **Light:** DAY.
- **Action:** the morning sun raking across the boards.
- **Sound:** room tone, birds outside, the felt-piano motif.
- **Into the next:** cut on bar 4. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/v2/contact.jpg`](previs/v2/contact.jpg).

### V02 · The credenza — 0:07.12–0:15.00 (bars 4–6, f180–359, 7.5 s)

- **Camera:** 40 mm full frame, T2. Slow lateral dolly along the credenza top, screen-right to left (the opposite way to V01), low, looking slightly down across it, 125 cm. From `[-115, -215, 118]` → `[-115, -90, 110]`, aimed at `[-245, -50, 82]`.
- **Focus:** +0 f: 140 cm, +100 f: 125 cm, +180 f: 138 cm.
- **In frame:** the credenza's top as a whole: the record crate, the calendar, the walnut block, headphones, the turntable, the hoodie's sleeve at the start; the shelves' LED glow above the frame; nothing centred, held on or racked to: the details pass by and the eye finds them.
- **Light:** GOLDEN.
- **Action:** the light warms as the sun drops.
- **Sound:** the first kick lands mid-glide (bar 5), the room waking up.
- **Into the next:** cut on bar 7. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/v2/contact.jpg`](previs/v2/contact.jpg).

### V03 · The window and the olive — 0:15.00–0:20.00 (bars 7–8, f360–479, 5.0 s)

- **Camera:** 75 mm full frame, T2.8. A rising lateral crane square to the window, 3 m off the olive, its crown crossing the glowing sheers, 30 cm across and 40 cm up; a 75 holds the frame to the window (y 120-300), so the side wall stays out and the slats and sign stay out for V04, and the crown, about two thirds of the frame wide, drifts from just right of centre to the right third. From `[100, 210, 115]` → `[100, 240, 155]`, aimed at `[-220, 240, 150]`.
- **Focus:** +0 f: 292 cm, +60 f: 304 cm, +120 f: 298 cm.
- **In frame:** the window and the olive as a whole: the sheers lit gold by the low sun, the leaves in silhouette and translucent against them, the pot and the light on the floor at the start.
- **Light:** GOLDEN.
- **Action:** the sun low and long through the sheers; the window holds detail.
- **Sound:** birds thinning outside, the sheers breathe.
- **Into the next:** cut on bar 9. **9:16:** crop centred at 45% of the width. **Previs:** [`previs/v2/contact.jpg`](previs/v2/contact.jpg).

### V04 · The slats and the sign — 0:20.00–0:25.00 (bars 9–10, f480–599, 5.0 s)

- **Camera:** 35 mm full frame, T2.8. A slow crane up the slat wall, drifting screen-right, to the unlit sign; the sign arrives at the top of the frame, never centred, still dark. From `[-60, 70, 115]` → `[-60, 45, 165]`, aimed at `[-260, 15, 192]`.
- **Focus:** +0 f: 205 cm, +120 f: 205 cm.
- **In frame:** the walnut slats in the last light, their rhythm filling the frame, the black karma letters arriving unlit at the top; the pothos' vines and the shelves' first LEDs at frame right.
- **Light:** DUSK.
- **Action:** the window cooling; the shelf LEDs coming up.
- **Sound:** crickets begin, a far city; the riser starts (bar 11 is next).
- **Into the next:** cut on bar 11. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/v2/contact.jpg`](previs/v2/contact.jpg).

### V05 · The room — 0:25.00–0:30.00 (bars 11–12, f600–719, 5.0 s)

- **Camera:** 28 mm full frame, T5.6. The payoff: the first and only view of the whole studio before the drop: S02's push and settle (crane 172 to 150 cm, dolly in 45 cm), settling into the frame S12 holds at night. From `[300, -35, 172]` → `[255, -35, 150]`, aimed at `[-260, 15, 140]`.
- **In frame:** the whole set at blue hour: the window blue, the olive, the slat wall and the dark sign centre, the shelves and the credenza glowing on their LEDs, the stool.
- **Light:** BLUE.
- **Action:** empty room; the last of the light.
- **Sound:** the riser, then silence on bar 12 beat 4 (the breath).
- **Into the next:** smash cut on the drop (bar 13). **9:16:** crop centred at 50% of the width. **Previs:** [`previs/v2/contact.jpg`](previs/v2/contact.jpg).

### S11 · The sign lights — 0:30.00–0:32.12 (bars 13–13, f720–779, 2.5 s)

- **Camera:** 40 mm full frame, T4. Slow push-in from below, 60 cm, as the halo ignites letter by letter (k a r m a on beats 1-4, + 'a' on 4&). From `[-40, 14, 150]` → `[-95, 30, 170]`, aimed at `[-256, 22, 228]`.
- **In frame:** the slat wall and the black Samarkan letters in near dark, the warm halo flaring behind each in turn.
- **Light:** IGNITION.
- **Sound:** the drop: a sub hit, a relay clunk and electrical hum per letter, the full beat comes in.
- **Into the next:** cut on bar 14. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S11.jpg`](previs/S11.jpg).

### S12 · The studio comes on — 0:32.12–0:35.00 (bars 14–14, f780–839, 2.5 s)

- **Camera:** 28 mm full frame, T5.6. The V05 frame at night (a match), a slow 30 cm push. From `[300, -35, 165]` → `[270, -35, 155]`, aimed at `[-260, 15, 140]`.
- **In frame:** the whole room at night: the sign lit, downlights popping on the beats (credenza, slats, olive, shelves), the window blue-black.
- **Light:** NIGHT.
- **Sound:** four relay clicks on the beats.
- **Into the next:** cut on bar 15. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S12.jpg`](previs/S12.jpg).

### N01 · The shelves at night — 0:35.00–0:40.00 (bars 15–16, f840–959, 5.0 s)

- **Camera:** 50 mm full frame, T2. A night glide: from the lit sign's edge along the shelves, screen-left to right, 115 cm, slightly oblique so the boards' LED lines converge; the halo's spill leaves frame left. From `[-110, 20, 184]` → `[-110, -95, 178]`, aimed at `[-252, -170, 176]`.
- **Focus:** +0 f: 140 cm, +60 f: 156 cm, +120 f: 144 cm.
- **In frame:** the shelves at night: warm LED lines under each board, the things on them half silhouette, half lit, the downlight's pool, the blue-black window reflected in a frame's glass; nothing centred, held on or racked to: the details pass by and the eye finds them.
- **Light:** NIGHT.
- **Action:** the room at rest.
- **Sound:** the score's drumless breakdown; the halo's hum, crickets.
- **Into the next:** cut on bar 17. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/v2/contact.jpg`](previs/v2/contact.jpg).

### S13 · Him — 0:40.00–0:45.00 (bars 17–18, f960–1079, 5.0 s)

- **Camera:** 35 mm full frame, T2.8. Slow push, 30 cm; his key light ramps up on bar 17 beat 3 (12 frames): a light reveal. From `[230, 70, 152]` → `[200, 62, 156]`, aimed at `[30, 40, 162]`.
- **In frame:** him on his mark, a silhouette against the halo-lit slats, then lit; shelves soft screen-right.
- **Light:** NIGHT+KEY.
- **Action:** head down; lifts his gaze to the lens with the key light (bar 17 beat 3); L1 on bar 18 beat 1, then a small smirk held to the cut.
- **Sound:** the groove returns (bar 17); the key light's soft 'thunk'; VO L1.
- **Into the next:** cut on bar 19. **9:16:** crop centred at 42% of the width. **Previs:** [`previs/S13.jpg`](previs/S13.jpg).

### S15 · The hand-off — 0:45.00–0:50.00 (bars 19–20, f1080–1199, 5.0 s)

- **Camera:** 85 mm full frame, T2. Near locked-off (a 7 cm drift) on his shoulder line; the focus pulls from him (195 cm) to her (304 cm) in 18 frames on bar 20. From `[220, 85, 165]` → `[214, 80, 165]`, aimed at `[-10, -10, 162]`.
- **Focus:** +0 f: 195 cm, +60 f: 195 cm, +78 f: 304 cm.
- **In frame:** him sharp in the foreground frame-left, her soft in the background frame-right by the shelves.
- **Light:** NIGHT+KEY.
- **Action:** he says L2 and turns his head to her; she looks up from him to the lens: L3a, a half-smile.
- **Sound:** VO L2 then L3a.
- **Into the next:** cut on bar 21. **9:16:** crop centred at 62% of the width. **Previs:** [`previs/S15.jpg`](previs/S15.jpg).

### S16 · Her line — 0:50.00–0:55.00 (bars 21–22, f1200–1319, 5.0 s)

- **Camera:** 65 mm full frame, T2. Medium close-up, a slow 10 cm push, the shelf LEDs as bokeh behind her. From `[110, -40, 158]` → `[100, -42, 158]`, aimed at `[-50, -55, 156]`.
- **In frame:** her, chest up, hoops and watch, the shelves and their things soft behind.
- **Light:** NIGHT+KEY.
- **Action:** L3b to the lens, unhurried, a small tilt of the head on 'yourself'.
- **Sound:** VO L3b; the lift (bar 21).
- **Into the next:** cut on bar 23. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S16.jpg`](previs/S16.jpg).

### S17 · Together — 0:55.00–1:00.00 (bars 23–24, f1320–1439, 5.0 s)

- **Camera:** 28 mm full frame, T4. Crane up and back 150 cm into the wide, keeping the sign centred. From `[170, -5, 150]` → `[320, -10, 195]`, aimed at `[-100, -5, 172]`.
- **In frame:** both on their marks under the sign, the whole studio at night opening up around them.
- **Light:** NIGHT+KEY.
- **Action:** him: L4a / her: L4b; a glance between them on 'comes around', then both to the lens, a small smile.
- **Sound:** VO L4a, L4b; the theme's last phrase.
- **Into the next:** cut on bar 25. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S17.jpg`](previs/S17.jpg).

### S18 · Title — 1:00.00–1:05.00 (bars 25–26, f1440–1559, 5.0 s)

- **Camera:** 28 mm full frame, T4. Locked off on the end of S17; the practicals ease down, the halo holds; title type fades in. From `[320, -10, 195]` → `[320, -10, 195]`, aimed at `[-100, -5, 172]`.
- **In frame:** the wide with the lit sign; the title over it (the karma wordmark, then "a studio by MelloB"), then a fade to black on the halo.
- **Light:** NIGHT-DIM.
- **Action:** both hold, a natural idle.
- **Sound:** the final chord and a sub tail; the halo's hum fades last.
- **Into the next:** fade to black (last 24 frames). **9:16:** crop centred at 50% of the width.

<!-- shots:end -->

## 5. Technical breakdown

### How the reel is assembled in Unreal

- **One master sequence, `/Game/Reel/SEQ_Reel`** (1560 frames + 12-frame handles), 24 fps, built by a script
  (`films/host-studio/reel/build.py`, task R3) from `shots.py`. One sequence rather than eighteen means the light
  timeline, the presenters' performances and the cameras share one clock, and a cut can be moved by editing a
  number. The cameras are level actors `Reel_S01` … `Reel_S18` (full-frame 16:9 back, `look.camera`), each moved
  by `seq.key_transform` over its own range and switched by `seq.camera_cuts`.
- **The level stays as studio.py builds it (day).** Everything the reel changes (lights, materials, visibility,
  the presenters' marks) is a track in the sequence, so closing the sequence restores the studio and the stills
  (`stills.py`) keep working. A one-time `reel/rig.py` (task R2) only *adds* what the day build lacks: the night's
  four downlights at intensity 0, a second outside card (night) at 0, and the Reel_* cameras.
- **Renders:** `render.mrq` per shot range (`start`/`end`), 3840×2160 PNG, the existing `QUALITY_CVARS`, plus
  `r.HairStrands.SkyLighting 0`. Post (`reel/cut.py`, task R6): frames → ProRes 4444 master → H.264 16:9 and the 9:16
  crop (per-shot crop centre `vcrop` from `shots.py`; a 1215-px-wide window of the 4K frame, scaled to 1080×1920,
  so the vertical cut needs no second render), the title as a 2D overlay, the mix muxed in.

### What each kind of shot uses

| Shot kind | Shots | Existing ops | New |
|---|---|---|---|
| Camera moves (truck, push, crane, pedestal) | all | `look.camera`, `seq.key_transform` (auto tangents give ease in/out at the ends) | — |
| Orbit / arc | S05, S14 | `seq.key_transform` with a key every 6 frames along the arc | `shots.py` helper `orbit(center, r, a0, a1, z, frames)` |
| Focus pulls (rack focus) | S04, S06, S09, S15 | `look.camera(focus=…)` sets one distance | **`seq.key_float`** on `CameraComponent` `FocusSettings.ManualFocusDistance` |
| Lens/aperture changes | (none planned) | — | the same `seq.key_float` (`CurrentFocalLength`, `CurrentAperture`) |
| Day → night | S01–S12 | `look.sky`, `look.light` (set once) | **`seq.key_transform`** on `FM_Sun` (elevation), **`seq.key_float`** on light `Intensity`/`Temperature`, sky light `Intensity`, the post volume's `Settings.AutoExposureBias`; **`seq.key_color`** on `LightColor` |
| The sign igniting letter by letter | S11 | `look.card` (SignHalo), `look.light` (Halo0–8) | **`seq.key_material`** (a component material parameter track) and a halo material with a **left-to-right wipe** parameter (`look.material` kind `GlowWipe`: the card's U compared to a `Reveal` scalar, soft edge); Halo0–8 keyed in pairs |
| Practicals (LEDs, terminal cursor) | S07–S10, S08 | the emissive materials | `seq.key_material` on `Intensity`; the cursor blink as a `Blink` scalar on the Screen material (stepped keys on the beats) |
| Presenters on reel marks, shown/hidden | S11–S18 | `seq.key_transform` (one key per mark) | **`seq.key_visible`** (Presenter, HerEarL/R, HerWatch, Stool, Host) |
| Talking | S13–S17 | `speech.to_face`, `anim.bake_follow`, `anim.head_to_body`, `anim.gaze_lock` | **`seq.anim`**: several sections per track at frame offsets with blend-in/out (idle → line → idle), for both presenters in one sequence; `seq.shot` binds only one actor |
| Him looking at her (hand-off) | S15 | `anim.gaze_lock` (eyes to the camera) | `anim.gaze_lock(target=…)`: aim the eyes at a point or actor instead of a camera for a frame range; a head-yaw curve via `anim.set_curve` |
| Reference audio in the sequence | — | `seq.shot(audio=…)` | **`seq.audio`**: VO and the score at offsets (timing only; the final mix is done in post) |
| Previs of the whole cut | — | `seq.stills` (one camera), `look.still` | `seq.stills` across the camera cut track (each frame through its own shot's camera) |

All the new ops are small additions next to `seq.key_transform` in `unreal/fmbridge/ops/seq.py`: Sequencer's
property tracks (`MovieSceneFloatTrack` / `MovieSceneColorTrack` / `MovieSceneBoolTrack` with `set_property_name_and_path`),
`MovieSceneVisibilityTrack`, `MovieSceneComponentMaterialTrack`, and extra `MovieSceneSkeletalAnimationTrack`
sections. They follow the traps in `unreal/README.md`: rotators and colours by keyword, components fetched afresh by
name on a MetaHuman (its construction script replaces them), and keys added by `unreal.FrameNumber`.

### The presenters' animation

| Need | Shots | Source | Status |
|---|---|---|---|
| Standing idle, body | S13–S18 | `/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle` (engine MetaHuman content) | **available** (used by stills.py and shot.py) |
| Talking face (lip-sync, blinks, brows, head motion) | S13–S17 | `speech.to_face` from each line's WAV, in a mood | **available** (the pipeline of shot.py) |
| Face and body as one skeleton; eyes on the lens | S13–S17 | `anim.bake_follow`, `anim.head_to_body`, `anim.gaze_lock` | **available** |
| Eyes and head turned to the partner | S15 | `anim.gaze_lock` with a target point; a head-yaw curve | **op change** (small) |
| Silent reactions (a smile, a nod, listening) | S15, S17, S18 | `speech.to_face` on a near-silent WAV (breaths, an "mm") then smile/brow curves with `anim.set_curve`/`anim.scale_curves` | doable with existing ops |
| Talk gestures (an open hand, a small wave toward her) | S14, S15, S16 | **Not in the engine's MetaHuman content** (checked: `previs/metahuman_animations.json`, 56 clips). Options, best first: (a) Mixamo "Talking"/"Explaining" clips (free, royalty-free) retargeted with an IK Retargeter onto the MetaHuman body; never commit the clips to this public repo; (b) Epic's free Game Animation Sample (locomotion, a few idles); (c) hand-keyed bone poses written with `anim.bake_pose`-style bone tracks | **must be made** (task R4) |
| His head down → up to the lens | S13 | a head-pitch curve on his face anim before L1 (`anim.set_curve`) | doable with existing ops |
| Walking | — | avoided on purpose: no shot needs it. If wanted later, the engine has walk start/loop/stop clips (`UEFNAnimPreset/Locomotion/AS_MH_Neutral_Walk_*`, F/B/L/R) | available, unused |
| Facial expressions between lines | S15, S17, S18 | `TemplateAnimations/Expression_Loops/HappyA,B` (and Sad, Surprise, Fear, Anger loops) and `Facial_Poses/Happy`, as a face layer or a curve source | **available** |
| A second standing idle | S13–S18 | `TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_f_idle`, `UEFNAnimPreset/Locomotion/AS_MH_Neutral_Stand_Idle_Loop` (so the two presenters do not breathe in sync) | **available** |

Her accessories (hoops on the ear bones, the watch on the forearm) are attached to her bones, so they follow her
transform keys and animation.

### Render time (estimates — calibrate before committing)

Lumen deferred through Movie Render Queue at 3840×2160 with `QUALITY_CVARS`, 8 temporal samples, motion blur,
on the workstation's GPU: about **8–15 s per frame** with a MetaHuman (hair strands) in frame, 5–10 s without.

| Pass | Frames | Estimate |
|---|---|---|
| Previs of the cut (1280×720, 1 sample, viewport `seq.stills` every 6th frame) | ~260 stills | 20–30 min |
| Animatic (1280×720, MRQ, 1 temporal sample, every frame) | 1560 | 45–75 min |
| Final 4K, macro and room shots S01–S12 (840 frames) | 840 | 1.2–2.3 h |
| Final 4K, presenter shots S13–S18 (720 frames) | 720 | 1.6–3.0 h |
| **Final 4K, everything (+ handles)** | ~1700 | **~3–5.5 h** |

The path tracer is not worth it for this reel (hair strands, translucent sheers and volumetric fog take minutes a
frame: tens of hours); at most, the title frame S18 could be path traced as a still. **Calibrate first:** render
24 frames of S14 and 24 of S11 at final settings and scale. Renders are one at a time and only by the Unreal
operator agent.

## 6. Who does what (v2)

| Who | What | Status |
|---|---|---|
| agent-13 (director) | PLAN v2, `shots.py` (shots + `LINES`), `motion.py` eases, previs v2; the VO (`vo.py`, new takes and selects, `cues.json`); the effects and mix re-cut (`sfx.py` cues, `mix.py`, `mix45.py`) | this branch |
| agent-10 | R3/R4: `build.py` from the v2 shot table (new Reel_ cameras, S14 gone, S13 moved), the performances for the new lines (face solves from the v2 VO, S13's late reveal, S15's hand-off and L3a, S16, S17's glance) | to do |
| agent-08 | the look: lighting/material polish in studio.py and light.py's values; the blue window at BLUE and NIGHT; **no accent light on any single prop** | in progress |
| agent-05:2 | S11's letter-by-letter ignition (halo) | in progress |
| agent-06:2 | R7: merge, build, relight, render: V01–V05 and N01 as soon as the build is in (no presenters: independent of R4); S13–S18 once R4's v2 performances land | S11/S12 rendered |
| agent-07 | R6: the cut (`cut.py`, `assemble.py`) from the v2 table, captions from `LINES`/cues.json, the 45 s cut, the deliverables | following v2 |

**45 s cut:** master frames `[(0,120), (240,360), (420,480), (660,840), (960,1560)]` (18 bars, every splice on a bar
line): V01's first 2 bars, V02's bars 5–6, V03's bar 8, V05's bar 12 into the drop, S11–S12, then S13 to the end
(N01 and V04 are the shots dropped).

## 7. Decisions and open questions

Decided by the operator (2026-11-01): ElevenLabs voices (a male voice for him, a female voice for her); the title card
(the karma wordmark, then "a studio by MelloB"); the score by ElevenLabs Music; **v2 review**: no shot singles out an
easter egg; the studio revealed area by area, then whole; more night; better light; short cheeky lines that tease.

Open (my defaults in brackets):

1. **Names on screen** (none: they stay "him" and "her").
2. **The lines** above are new: the operator has not heard them yet. Re-takes are cheap (a few credits a line).
3. **The crate's artists** pass by on the credenza glide (V02), unfocused on; none of their music is used.
4. **Marks** stay sequence-only (the level is unchanged).
