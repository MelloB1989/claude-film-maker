# karma — the launch reel

A 65-second cinematic reel that introduces the karma studio and its two presenters, for social: a 16:9 master
(3840×2160) and a 9:16 cut (1080×1920) cropped from it. This is the plan and the previs; nothing here is final film.

- **Shots:** 18, in one master sequence, 1560 frames at 24 fps (65.0 s), every cut on a bar line of a 96 bpm score.
- **Shot table as code:** [`shots.py`](shots.py) holds every shot's timing, lens, camera keys, focus pulls, light
  state, cast and 9:16 crop. This document's shot list is generated from it, the previs places its cameras from it,
  and the reel's sequence builder (task R3 below) should read it too. Change the table, not the prose.
- **Previs:** [`previs/`](previs/) (contact sheet `previs/contact.jpg`), made with [`previs.py`](previs.py).

## 1. Concept and tone

**"Everything in this room has a story."** The reel is a day in the studio compressed into a minute: it opens in
soft morning light on an empty room, walks the camera over the owner's things in macro as the sun goes down, and on
the drop the halo of the karma sign switches on, letter by letter, and the room becomes its night self. Only then
do we meet the people: him, lit out of silhouette in front of the sign, then a hand-off by focus pull to her by the
shelves, then both together, and the title.

Tone: calm, warm, premium, personal. Slow, deliberate camera (sliders, cranes, pushes; no handheld, no shake),
shallow depth of field on the macro passes, real lenses on a full-frame back. Nothing flashy in the edit: the cuts
fall on the downbeats, the energy comes from the light and the music. The presenters speak little, and the room
does most of the talking. Reference points for the feel: Apple's product macro films (light raking across
material), *Kinfolk*/*Cereal* interiors, the slow "studio tour" openers of creator channels, Fincher-like locked-off
precision for the presenter shots.

Three rules that keep it premium:

1. **Light is the story.** Day → golden → dusk → blue → ignition → night is one continuous light timeline (one
   shared set of light keys), so every shot sits at its true time of day and the cut never jumps in light.
2. **Every macro shot moves, and every move ends on a detail that reads**: a title on a spine, the V and the
   heart, a date, a name. A viewer who pauses finds a story in each frame.
3. **The presenters are introduced by light and focus, not by effects**: a key light ramp for him, a focus pull
   for her.

## 2. Music, beats and structure

**Tempo: 96 bpm, 4/4.** At 24 fps a beat is exactly 15 frames and a bar 60 frames (2.5 s), so every beat lands on
a whole frame and every cut on a bar line is frame-exact. 26 bars = 65 s.

| Section | Bars | Time | Shots | Music | Light |
|---|---|---|---|---|---|
| A. Morning | 1–4 | 0:00–0:10 | S01–S02 | felt piano motif over a warm pad and vinyl room tone; no drums | DAY |
| B. The things | 5–12 | 0:10–0:30 | S03–S10, one bar each | a soft brushed kick enters on bar 5; bass on bar 7; hats on bar 9; a riser through bar 12; the last beat of bar 12 drops out (a breath) | GOLDEN → DUSK → BLUE |
| C. Ignition (the drop) | 13–14 | 0:30–0:35 | S11–S12 | **the drop on bar 13 beat 1**: a sub hit, the full groove, a low drone (tanpura-like) | IGNITION → NIGHT |
| D. Him | 15–18 | 0:35–0:45 | S13–S14 | the groove thins under the voice (no lead), music ducks 6–9 dB | NIGHT+KEY |
| E. Hand-off, her | 19–22 | 0:45–0:55 | S15–S16 | a lift on bar 21 (a counter-melody enters with her) | NIGHT+KEY |
| F. Together, title | 23–26 | 0:55–1:05 | S17–S18 | the motif returns in full; the last chord on bar 25 beat 1 rings out over the title | NIGHT → NIGHT-DIM |

The beats that are hit on purpose (frame = (bar−1)·60 + (beat−1)·15):

- bar 5 beat 1 (f240): the first kick, cut to the seven spines.
- bar 8 beat 1 (f420): the coin's ping lands with the kick.
- bar 12 beat 4 (f705): the needle drop's crackle, then silence until the drop.
- **bar 13 beat 1 (f720): the drop.** The first letter of the sign ignites; letters 2–5 on beats 2, 3, 4 and 4&
  (f735, f750, f765, f772).
- bar 14 beats 1–4 (f780–825): the four downlight groups pop on, one per beat.
- bar 16 beat 1 (f900): his key light ramps up (12 frames); his eyes come up to the lens; line 1 starts on beat 3 (f930).
- bar 20 beat 1 (f1140): the focus pull from him to her (18 frames).
- bar 25 beat 1 (f1440): the last chord; the title fades in over beats 2–4.
- f1536–1559: the fade to black on the halo.

### Music brief (licence-free)

- **Style:** cinematic downtempo / organic house. Felt piano and Rhodes, tape-warm pads, soft brushed kick and
  shakers, round sub bass; a single sustained Indian drone colour (tanpura or a bowed string) under the drop to tie
  in the Samarkan letterforms and the crate's Indian hip-hop, without pastiche. Key: D minor (Dorian lift on the
  hand-off). No vocals.
- **References for feel only** (never sampled, never imitated melodically): Bonobo, "Kerala" (organic build);
  Tycho, "Awake" (warmth, pace); Ritviz's softer productions (Indian colour in electronic music); Lane 8's
  deep-house risers (the pre-drop breath).
- **How:** generate it with the repo's score pipeline: `music_plan.py` sections in whole bars (A 4, B 8, C 2, D 4,
  E 4, F 4 = 26 bars at 96 bpm) → `music.py` (ElevenLabs Music: the operator's choice; key: the fleet secret `elevenlabs`), then `beats.py` to measure the grid against the cut (grid fit ≥ 0.9, else
  regenerate). Until it exists, cut to `temptrack.py`'s procedural score at 96 bpm (owned outright, no licence
  question at all); it is also the fallback if the generated score does not fit.
- **Never:** commercial tracks, the crate's artists' music (the record crate is visual only), stock libraries with
  attribution clauses.

### Sound design

Stereo, mixed under the music with `mix.py` (−14 LUFS, −1 dBTP), effects from `sfxlib.py`/`sfx.py` (generated,
licence-free), each one-shot aligned to its frame:

- Bed: room tone throughout; birds outside during DAY/GOLDEN, crossfading to distant crickets and a far-off city
  hum by BLUE; the halo's faint electrical hum from the drop on.
- Macro foley, one per shot and on its beat: a finger on book cloth (S03), a polaroid flick (S04), a glassy tick
  (S05), a coin's ring and a mined "tink" on the rack (S06), a gimbal servo whirr and an LED blip (S07), three
  keystrokes and a cursor tick per beat (S08), a calendar page settling (S09), the needle drop and crackle (S10).
- Ignition: a relay clunk per letter, an electrical swell and a sub "whoomph" on the drop; four relay clicks for the
  downlights (S12); a soft "thunk" for his key light (S13).
- Presenters: light cloth movement only; no footsteps (nobody walks).
- Title: the last chord's tail, the halo hum last to fade.

### Voice lines

Two presenters, four short lines (about 16 s of speech in 65 s). **Approved by the operator as written**
(2026-11-01).

| Line | Who | When | Text | Mood (`speech.to_face`) |
|---|---|---|---|---|
| L1 | him | f930–1080 (S13→S14) | "This is karma. Everything on these shelves is a story — seven of them, built one late night at a time." | CONFIDENCE 0.8 |
| L2 | him | f1110–1150 (S15) | "She'll tell you the next one." | HAPPINESS 0.6 |
| L3 | her | f1158–1310 (S15→S16) | "Tech, explained the way we'd want it explained: calm, honest, and made right here." | CONFIDENCE 0.9 |
| L4 | him, then her | f1360–1410 (S17) | him: "Welcome…" — her: "…to karma." | HAPPINESS 0.7 |

Voices: **ElevenLabs** (operator's decision): one male voice for him, one female voice for her, through
`vo.py` (a few takes per line, chosen by listening, not dozens). The API key is the fleet secret `elevenlabs`, used
only through `fleetctl secret exec ELEVENLABS_API_KEY=elevenlabs -- …`. Each line becomes a face with
`speech.to_face`, as in `films/host-studio/shot.py`.

## 3. Lighting states

One shared light timeline (§5, task R2) moves the room through these states; each shot just sits at its time.

| State | When | What changes from studio.py |
|---|---|---|
| DAY | f0–240 | studio.py's day, but the **halo off** (halo card intensity 0, Halo0–8 at 0) |
| GOLDEN | f240–480 | the sun falls 28° → 8°, 5100 K → 3200 K, 30 → 8 klx; WindowSky warms; exposure bias 8.3 → 8.8 |
| DUSK | f480–660 | the sun 8° → −3°; window cools; shelf LEDs 1.3 → 1.5; exposure → 9.2 |
| BLUE | f660–720 | studio.py night's sky and window; the outside card crossfades day → night; only LEDs and candle |
| IGNITION | f720–780 | halo letters on in turn (card wipe + Halo0–8 ramped in pairs), 10-frame ease-in each, slight overshoot |
| NIGHT | f780– | the four downlight groups pop on, one per beat in bar 14; exposure 9.6 (studio.py night) |
| NIGHT+KEY | f840–1440 | the presenters' channel-1 lights (Key, Fill, HairLight, RimWarm, RimWindow, EyeLight), re-aimed for the two marks; Key ramps 0 → 5.5 over f900–912 |
| NIGHT-DIM | f1440– | practicals −30% over two bars; the halo holds; fade to black f1536–1559 |

## 4. Shot list

The timecodes are of the master (frame 0 = 0:00.00). Coordinates are cm in the studio's frame (back wall at
x = −260, camera side +X, screen-left +Y). The presenters' reel marks: him at (30, 40, 0), her at (−50, −55, 0),
both facing the camera (+X); in the level today both stand at the origin.

<!-- shots:begin -->

### S01 · Light through the olive — 0:00.00–0:05.00 (bars 1–2, f0–119, 5.0 s)

- **Camera:** 85 mm full frame, T2. Slow lateral truck (screen-right to left) through the olive's crown, 25 cm over 5 s. From `[-130, 165, 160]` → `[-130, 188, 160]`, aimed at `[-215, 222, 152]`.
- **In frame:** olive leaves backlit by the sheers, the window's glow blooming between them; 70% out of focus.
- **Light:** DAY.
- **Action:** the leaves are still (static mesh); a faint dust drift in the volumetric fog.
- **Sound:** room tone, birds outside, a felt-piano motif enters.
- **Into the next:** cut on bar 3. **9:16:** crop centred at 55% of the width. **Previs:** [`previs/S01.png`](previs/S01.png).

### S02 · The room — 0:05.00–0:10.00 (bars 3–4, f120–239, 5.0 s)

- **Camera:** 28 mm full frame, T5.6. Slow push and settle down: crane from 170 to 150 cm, dolly in 45 cm. From `[300, -35, 172]` → `[255, -35, 150]`, aimed at `[-260, 15, 140]`.
- **In frame:** the whole set: sheers and olive left, slat wall and the unlit sign centre, shelves and credenza right, stool.
- **Light:** DAY.
- **Action:** empty room; sun patches on the rug.
- **Sound:** the curtain breathes (soft air), a clock-like tick doubles the tempo.
- **Into the next:** cut on bar 5 (first kick). **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S02.png`](previs/S02.png).

### S03 · Seven spines — 0:10.00–0:12.12 (bars 5–5, f240–299, 2.5 s)

- **Camera:** 100 mm full frame, T4. Macro slider parallel to the shelf, 44 cm screen-left to right along the green spines. From `[-196, -100, 212]` → `[-196, -144, 212]`, aimed at `[-236, -148, 211]`.
- **In frame:** the seven dark-green spines, titles reading bottom to top: Socify, Noobsverse, Lyzn, Avidia, Respawn, Noobspaces, Noobs Learning; cloth texture, gilt titles.
- **Light:** GOLDEN.
- **Sound:** a finger along book cloth, a soft kick lands with the cut.
- **Into the next:** cut. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S03.png`](previs/S03.png).

### S04 · V and the heart — 0:12.12–0:15.00 (bars 6–6, f300–359, 2.5 s)

- **Camera:** 85 mm full frame, T2. Slow push-in, 12 cm, with a rack from the vase behind to the polaroid. From `[-185, -140, 214]` → `[-196, -147, 210]`, aimed at `[-239, -163, 205]`.
- **Focus pull:** +0 f: 73 cm, +36 f: 47 cm.
- **In frame:** the polaroid (the V and the heart) leaning on the books, the speckled vase soft behind it.
- **Light:** GOLDEN.
- **Sound:** a polaroid's soft flick.
- **Into the next:** cut. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S04.png`](previs/S04.png).

### S05 · lyzn — 0:15.00–0:17.12 (bars 7–7, f360–419, 2.5 s)

- **Camera:** 65 mm full frame, T2.8. Orbit around the acrylic block, 35 deg at 50 cm radius, the sun's glint crawling across its edge. From `[-196.7, -179.1, 208]` → `[-198.0, -209.1, 208]`, aimed at `[-245, -192, 205]`.
- **In frame:** the frosted lyzn block, its engraved word catching the light, the shelf LED strip a line of bokeh above.
- **Light:** GOLDEN.
- **Sound:** a glassy tick on beat 3.
- **Into the next:** cut. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S05.png`](previs/S05.png).

### S06 · The coin and the pickaxe — 0:17.12–0:20.00 (bars 8–8, f420–479, 2.5 s)

- **Camera:** 100 mm full frame, T2.8. Low push at shelf height, 11 cm, focus racks from the coin to the pickaxe on beat 3. From `[-190, -160, 168]` → `[-200, -165, 168]`, aimed at `[-250, -178, 169]`.
- **Focus pull:** +0 f: 59 cm, +30 f: 54 cm, +42 f: 59 cm.
- **In frame:** the coin on its walnut stand in front, the brass pickaxe behind; the candle's flame soft at frame left.
- **Light:** GOLDEN.
- **Sound:** a coin's ring (a single ping on beat 1), a mined 'tink' on the rack.
- **Into the next:** cut. **9:16:** crop centred at 45% of the width. **Previs:** [`previs/S06.png`](previs/S06.png).

### S07 · The drone — 0:20.00–0:22.12 (bars 9–9, f480–539, 2.5 s)

- **Camera:** 50 mm full frame, T2.8. Crane down from a three-quarter top view to eye level with the gimbal, ending on its red LED. From `[-222, -124, 205]` → `[-212, -116, 178]`, aimed at `[-247.5, -124, 167]`.
- **In frame:** the mini drone on the shelf, props folded, the gimbal lens and the red front LED.
- **Light:** DUSK.
- **Sound:** a gimbal servo whirr, an LED blip on beat 4.
- **Into the next:** cut. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S07.png`](previs/S07.png).

### S08 · hello, friend — 0:22.12–0:25.00 (bars 10–10, f540–599, 2.5 s)

- **Camera:** 65 mm full frame, T2.8. Pedestal down and slight truck from the red print to the terminal's root prompt. From `[-195, -100, 150]` → `[-200, -90, 133]`, aimed at `[-248, -82, 129]`.
- **In frame:** the framed red print, then the slim terminal display: root@mellob:~# and its cursor.
- **Light:** DUSK.
- **Action:** the terminal's cursor blinks on the beat (material param, new).
- **Sound:** three keystrokes, a cursor tick per beat.
- **Into the next:** cut. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S08.png`](previs/S08.png).

### S09 · 27 NOV — 0:25.00–0:27.12 (bars 11–11, f600–659, 2.5 s)

- **Camera:** 50 mm full frame, T1.8. A slow 8 cm drift, focus racking from the MelloB block (foreground) to the 27 NOV calendar. From `[-195, -85, 86]` → `[-199, -90, 85]`, aimed at `[-224, -150, 78]`.
- **Focus pull:** +0 f: 46 cm, +24 f: 46 cm, +40 f: 94 cm.
- **In frame:** the walnut MelloB nameplate soft in the foreground, the calendar's 27 NOV pulling sharp behind.
- **Light:** DUSK.
- **Sound:** a calendar page settling.
- **Into the next:** cut. **9:16:** crop centred at 60% of the width. **Previs:** [`previs/S09.png`](previs/S09.png).

### S10 · The crate — 0:27.12–0:30.00 (bars 12–12, f660–719, 2.5 s)

- **Camera:** 65 mm full frame, T2.8. Push-in 30 cm into the crate's front sleeve, ending on the name KARMA in its artist list. From `[-150, -150, 100]` → `[-182, -154, 96]`, aimed at `[-232, -157, 90]`.
- **In frame:** the walnut crate of LPs: SEEDHE MAUT, KR$NA, RAFTAAR, KARMA, BELLA on the front sleeve.
- **Light:** BLUE.
- **Action:** the shelf LEDs carry the frame; the window goes blue behind.
- **Sound:** needle drop and vinyl crackle, a riser, then silence on beat 4 (+).
- **Into the next:** smash cut on the drop (bar 13). **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S10.png`](previs/S10.png).

### S11 · The sign lights — 0:30.00–0:32.12 (bars 13–13, f720–779, 2.5 s)

- **Camera:** 40 mm full frame, T4. Slow push-in from below, 60 cm, as the halo ignites letter by letter (k a r m a on beats 1-4, + 'a' on 4&). From `[-40, 10, 150]` → `[-95, 15, 170]`, aimed at `[-256, 25, 228]`.
- **In frame:** the slat wall and the black Samarkan letters in near dark, the warm halo flaring behind each in turn.
- **Light:** IGNITION.
- **Sound:** the drop: a sub hit, a relay clunk and electrical hum per letter, the full beat comes in.
- **Into the next:** cut on bar 14. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S11.png`](previs/S11.png).

### S12 · The studio comes on — 0:32.12–0:35.00 (bars 14–14, f780–839, 2.5 s)

- **Camera:** 28 mm full frame, T5.6. The S02 frame at night (a match), a slow 30 cm push. From `[300, -35, 165]` → `[270, -35, 155]`, aimed at `[-260, 15, 140]`.
- **In frame:** the whole room at night: the sign lit, downlights popping on the beats (credenza, slats, olive, shelves).
- **Light:** NIGHT.
- **Sound:** four relay clicks on the beats.
- **Into the next:** cut on bar 15. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S12.png`](previs/S12.png).

### S13 · Him — 0:35.00–0:40.00 (bars 15–16, f840–959, 5.0 s)

- **Camera:** 35 mm full frame, T2.8. Slow push, 30 cm; his key light ramps up on bar 16 beat 1 (12 frames): a light reveal. From `[230, 70, 152]` → `[200, 62, 156]`, aimed at `[30, 40, 162]`.
- **In frame:** him on his mark, a silhouette against the halo-lit slats, then lit; shelves soft screen-right.
- **Light:** NIGHT+KEY.
- **Action:** head down, lifts his gaze to the lens on bar 16 beat 1, starts line 1 on beat 3.
- **Sound:** the key light's soft 'thunk'; VO L1.
- **Into the next:** cut on bar 17. **9:16:** crop centred at 42% of the width. **Previs:** [`previs/S13.png`](previs/S13.png).

### S14 · His line — 0:40.00–0:45.00 (bars 17–18, f960–1079, 5.0 s)

- **Camera:** 65 mm full frame, T2. Medium close-up, a 6 degree arc and a 10 cm push while he speaks. From `[175, 58, 172]` → `[165, 46, 172]`, aimed at `[30, 40, 170]`.
- **In frame:** him, chest up, the sign's halo behind his shoulder, eyes on the lens (gaze lock).
- **Light:** NIGHT+KEY.
- **Action:** line 1 continues, one open-hand gesture.
- **Sound:** VO L1, music ducks 6-9 dB.
- **Into the next:** cut on bar 19. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S14.png`](previs/S14.png).

### S15 · The hand-off — 0:45.00–0:50.00 (bars 19–20, f1080–1199, 5.0 s)

- **Camera:** 85 mm full frame, T2. Near locked-off (a 7 cm drift) on his shoulder line; the focus pulls from him (195 cm) to her (304 cm) in 18 frames on bar 20. From `[220, 85, 165]` → `[214, 80, 165]`, aimed at `[-10, -10, 162]`.
- **Focus pull:** +0 f: 195 cm, +60 f: 195 cm, +78 f: 304 cm.
- **In frame:** him sharp in the foreground frame-left, her soft in the background frame-right by the shelves.
- **Light:** NIGHT+KEY.
- **Action:** he says L2 and turns his head to her; she looks up from him to the lens and starts L3.
- **Sound:** VO L2 then L3.
- **Into the next:** cut on bar 21. **9:16:** crop centred at 62% of the width. **Previs:** [`previs/S15.png`](previs/S15.png).

### S16 · Her line — 0:50.00–0:55.00 (bars 21–22, f1200–1319, 5.0 s)

- **Camera:** 65 mm full frame, T2. Medium close-up, a slow 10 cm push, the shelf LEDs as bokeh behind her. From `[110, -40, 158]` → `[100, -42, 158]`, aimed at `[-50, -55, 156]`.
- **In frame:** her, chest up, hoops and watch, the shelves and their things soft behind.
- **Light:** NIGHT+KEY.
- **Action:** line 3 continues; a small gesture with the watch hand.
- **Sound:** VO L3.
- **Into the next:** cut on bar 23. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S16.png`](previs/S16.png).

### S17 · Together — 0:55.00–1:00.00 (bars 23–24, f1320–1439, 5.0 s)

- **Camera:** 28 mm full frame, T4. Crane up and back 150 cm into the wide, keeping the sign centred. From `[170, -5, 150]` → `[320, -10, 195]`, aimed at `[-100, -5, 172]`.
- **In frame:** both on their marks under the sign, the whole studio opening up around them.
- **Light:** NIGHT+KEY.
- **Action:** him: 'Welcome' / her: 'to karma.'; both settle, a small smile to the lens.
- **Sound:** VO L4, the theme's last phrase.
- **Into the next:** cut on bar 25. **9:16:** crop centred at 50% of the width. **Previs:** [`previs/S17.png`](previs/S17.png).

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
| Talk gestures (an open hand, a small wave toward her) | S14, S15, S16 | Not in the engine's MetaHuman content as far as is known (to confirm: `previs.py --animations` lists it). Options, best first: (a) Mixamo "Talking"/"Explaining" clips (free, royalty-free) retargeted with an IK Retargeter onto the MetaHuman body; never commit the clips to this public repo; (b) Epic's free Game Animation Sample (locomotion, a few idles); (c) hand-keyed bone poses written with `anim.bake_pose`-style bone tracks | **must be made** (task R4) |
| His head down → up to the lens | S13 | a head-pitch curve on his face anim before L1 (`anim.set_curve`) | doable with existing ops |
| Walking | — | avoided on purpose: no shot needs it (foot sliding, cost) | — |

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

## 6. Task split for the fleet

Only the Unreal operator agent touches the editor (renders, MetaHuman rebuilds, studio.py, running the reel's
scripts); everyone else writes code and data, tests offline what can be tested, and hands it over.

| Task | What | Needs | Who | Size |
|---|---|---|---|---|
| **R1. Sequencer ops** | `seq.key_float`, `seq.key_color`, `seq.key_visible`, `seq.key_material`, `seq.anim` (sections at offsets with blends), `seq.audio`, `seq.stills` across the cut, `gaze_lock(target=…)`; docstrings and `film-ue ops` listing; a test sequence | — | 1 agent | 1 day |
| **R2. Light timeline** | `reel/rig.py` (what the day build lacks) and `reel/light.py`: the states of §3 as data, the halo wipe material (`GlowWipe` in `look.material`), the ignition, the downlight pops, keys onto `SEQ_Reel` | R1 | 1 agent | 1 day |
| **R3. Cameras and the cut** | `reel/build.py`: the Reel_* cameras and their keys from `shots.py`, orbit/arc helpers, focus pulls, camera cuts, the presenters' marks and visibility; refine framings from the previs and the animatic | R1 | 1 agent | 1 day |
| **R4. Performances** | the VO (ElevenLabs via `vo.py`), `speech.to_face` per line, idle/line/idle sections, gestures (retarget), the hand-off look, reactions, gaze locks for both | R1 | agent-03:2 | 1–2 days |
| **R5. Score and sound** | temp track now (`temptrack.py`, 96 bpm, 26 bars); the ElevenLabs score from the section plan; the SFX palette and cue sheet on the frames of §2/§4; the mix | — | agent-11 | 1 day (can start now) |
| **R6. Post and delivery** | `reel/cut.py`: frames → 16:9 master, the 9:16 crop from `vcrop`, the title overlay (Geist and the Samarkan wordmark), captions for L1–L4 (burned-in for social), loudness, the deliverables | — | 1 agent | ½ day (can start now) |
| **R7. Execution in Unreal** | install R1, run R2/R3/R4 in the editor, the animatic, the calibration renders, the final renders by shot range; bring frames back through S3 | R1–R4 | the Unreal operator agent | 1 day of machine time |

Order: R5 and R6 start at once; R1 first among the Unreal tasks; R2, R3 and R4 in parallel once R1 lands; R7
runs the animatic as soon as R2 and R3 exist (with idles only), and the finals once R4 is in.

## 7. Decisions and open questions

Decided by the operator (2026-11-01):

- **The words:** lines L1–L4 as written, voiced with ElevenLabs (a male voice for him, a female voice for her).
- **The title card:** the karma wordmark, then "a studio by MelloB".
- **The score:** ElevenLabs Music.

Still open:

1. **Names on screen.** Should the presenters be named (a lower third), or stay "him" and "her"?
2. **Seven products.** Is it fine to read every spine title on screen (S03), and to show the V-and-heart polaroid
   up close (S04)? It is personal.
3. **The crate's artists.** The names are on screen (S10); none of their music is used. Fine?
4. **Length.** 65 s is planned; a 45 s cut drops S01, S05, S07, S09 and shortens S13/S17 by a bar each. Wanted too?
5. **Marks.** The plan moves him to (30, 40) and her to (−50, −55) only inside the reel's sequence; the level is
   unchanged. Is that acceptable, or should the reel have its own level copy?
