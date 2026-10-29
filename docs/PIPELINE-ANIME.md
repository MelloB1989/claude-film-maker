# The anime pipeline

A 2D anime short made from generated key art and clips: characters and locations designed once and kept consistent
by reference, keyframes for every shot, the shots that need real motion animated image-to-video, the rest laid out as
2.5D multiplane shots in the engine, a cast of voices with subtitles, a composed score in cues, a sound library and a
mix, and Blender for the shot that needs true depth. The first film made with it is `films/rain-ferry/` (*The Rain
Ferry*, about two minutes: `STORY.md` is its bible and shot list).

Everything works on one film at a time (docs/CONVENTIONS.md: `--film <id>`). The generation services are reached from
outside the repo (an agent's tools, a web app): the pipeline starts where a result URL exists, and keeps the provenance.

```
STORY.md ─► sheets, key art ─► keyframes ─┬─► clips (image to video) ─► film-anime-clips ─► media.ts ─┐
                                          ├─► film-anime-cutout / film-anime-depth ──────────────────┤
                                          └─► blender/shots/<shot>.py ─► render.py (EEVEE) ──────────┤
                                                                                                     ▼
data/dialogue.json ─► film-anime-dialogue takes ─► check ─► place ──► subs.json ──► film.ts (@kit/anime) ─► render.ts
data/score.json ─► film-anime-score ─┐                                                   ▲
data/sfx_palette.json ─► film-sfx-lib ┼─► data/mix.json ─► film-anime-mix ─► mix.wav ────┘
                                      synth.py ┘
```

## 1. Design and key art

Write the film first: characters (a paragraph of look each), the look of the world, the script with its English
lines, and a shot list that says for each shot whether it is a clip, a 2.5D shot or a Blender plate.

- **Character sheets** (front, side, back, three expressions) and one **location key**. Every later image is made
  with the sheets and the key as references, and its prompt names the art style in words (never an artist).
- **Keyframes**, one per shot, 16:9 at 2K. A 2.5D shot uses its keyframe directly, so it wants the most care.
- Fetch every result with its provenance (job, model, prompt, references, cost) into `data/gen.json`:

```sh
uv run film-anime-fetch --film <id> --name key-ferry --url <result url> --job <id> --model gpt_image_2_5 \
    --credits 1 --refs sheet-tsuru --prompt "..."          # assets/gen/key-ferry.png
uv run film-anime-fetch --film <id> --list                 # what the film has, and what it cost
```

A re-roll keeps the old picture as `<name>.v1` (`--force`).

## 2. Clips

Image-to-video from the keyframe (the start frame). Prompt the motion and the camera only, and repeat the style
("hand-drawn 2D ink-wash anime animation, consistent line art and texture"); ask for one action. Expect the model to
over-reach in the second half of a clip (a charge became a tidal wave): plan to use the first two or three seconds of
an action clip, played at `rate` 0.5 to 0.75 when it needs to last (held frames read as animating on twos).

```sh
uv run film-anime-clips --film <id> --all        # assets/gen/clip-*.mp4 → assets/clips/<name>.mp4, film size and fps
cd app && bun scripts/media.ts --film <id> --src assets/clips/<name>.mp4 --q 2
```

## 3. 2.5D layers

```sh
uv run film-anime-cutout --film <id> --src assets/gen/key-refuse.png --keep-largest 1   # assets/layers/refuse/
uv run film-anime-cutout --film <id> --src assets/gen/key-standoff.png --out assets/layers/standoff2 \
    --parts "0,0.25,0.42,0.86;0.66,0.1,0.93,0.86"          # one layer per figure: part1.png, part2.png
uv run film-anime-depth --film <id> --src assets/layers/refuse/plate.png                 # depth.png beside it
```

The cutout is skytnt's anime segmentation (ONNX, CPU); a small figure the whole frame misses is found on its own crop
(`--parts`). The plate behind is filled by push-pull: soft, right for the few pixels a camera move uncovers. A move
that opens up a lot (a Blender dolly between two figures) needs a painted plate: grow the figures' matte, upload it as
a mask and inpaint (Nano Banana 2, `is_inpaint`), then resize the result onto the keyframe's grid.

## 4. The cut: `@kit/anime`

| block | what it does |
|---|---|
| `Parallax` | layered pictures at depths under a camera move (pan, push, roll, handheld drift); a depth map gives one painting relief of its own; `breathe` keeps a still figure alive |
| `PlateShot` | a Blender plate as a shot |
| `Rain` | depth layers of streaks, splashes on a ground band, lightning, and a clock that slows to a stop (`slow`) |
| `Mist`, `Smoke`, `Rays`, `Paper` | fog banks and veil, a pipe's wisp, god rays with dust motes, the paper's grain over the film |
| `SpeedLines` | manga focus lines or parallel streaks, redrawn on twos |
| `PostKeys` | any post parameter keyed over a shot or an overlay: impact strobes (`invert` stepped), flashes, shakes, the grade's arc, letterbox bars sliding in and out |
| `InkReveal` | brush calligraphy brushed onto the frame down the page, its red seal stamped after |
| `Words`, `Subtitles` | title-card type; anime subtitles from `data/subs.json` |

Clips play through `@kit/media` `Video` (`clipStart`, `rate`, `loop: false`), weather and grade stacked over them in a
`Stack`. The `ink` transition (engine `transition.ts`) bleeds B in through spreading blots with a dark wet rim.

Grade the film cold and let it warm: a film-wide `post` (saturation, contrast, warmth) and per-shot `PostKeys` for the
turns (the duel desaturates, the ending warms and blooms).

## 5. Dialogue and subtitles

`data/dialogue.json` holds the cast (voice, model, settings) and the lines (`ja` as written, `tts` as spoken with audio
tags and kana readings, `en` subtitles, `shot` and `at` placing each line, `inner` for an inner voice):

```sh
uv run film-anime-dialogue --film <id> takes --n 2    # ElevenLabs v3 takes, cached by request
uv run film-anime-dialogue --film <id> check          # Whisper transcribes every take: flags tags read aloud, wrong lines
uv run film-anime-dialogue --film <id> place          # audio/dialogue/dialogue.wav, data/subs.json, dialogue_timing.json
```

Choose takes by `take` in the script. `check` caught a take that said a different word altogether and a line garbled
after a sigh: run it before choosing. Re-run `place` after any change to the cut (it reads `data/timeline.json`).

## 6. Score, sound and mix

- **Score** in cues (`data/score.json`): each cue a few sections of styles, placed at a film time, composed by
  ElevenLabs Music: `uv run film-anime-score --film <id> gen`. Leave the duel's held breath to the effects.
- **Sound library**: `data/sfx_palette.json` and `film-sfx-lib` (beds loop; one-shots align on their onset).
- **Synth** (`synth.py`): taiko, a high ring, a sub drop, a riser, a swell, by name in the mix (`synth:taiko`).
- **Mix**: `data/mix.json` (dialogue air, music keys and ducking, beds with gain and low-pass keys, cues with gain, pan,
  reverb) → `uv run film-anime-mix --film <id> --png levels.png`: `audio/mix/mix.wav` at −16 LUFS under −1 dBTP, and
  the stems.

## 7. Blender plates

A shot that needs true depth is a Blender plate (docs/PIPELINE-BLENDER.md): `films/<id>/blender/shots/<shot>.py`,
rendered with EEVEE, composited by `PlateShot`. *The Rain Ferry*'s `freeze` rebuilds the duel's keyframe as cards
(the clean plate, then each fighter on a card of their own), hangs 3,600 frozen drops in the air and glides the camera
between the fighters with a physically sampled depth of field: 120 frames at 1080p in under four minutes on an M5.

```sh
blender -b -P blender/render.py -- --film <id> --shot freeze --mode look --engine eevee --frames 1635,1695,1753
blender -b -P blender/render.py -- --film <id> --shot freeze --mode final --engine eevee --samples 64 --res 1920x1080
blender -b -P blender/render.py -- --film <id> --shot freeze --scan
```

### Shots made entirely in Blender

A shot can also be built from nothing but code: the set, the cast, the weather and the light, in a 2D anime look
(flat cel bands, ink line art, an ink-wash distance). *The Rain Ferry*'s `standoff` is one. The parts every film can
use are in the core:

| module | what it makes |
|---|---|
| `blender/lib/toon.py` | the look: `cel` toon materials (lit, shade, an optional mid band, faded to the fog by distance), `ink` (Grease Pencil Line Art over a collection), `water` (streaks, rain rings, a ray-traced reflection), `mist_card`, `rain` and `splashes` (Geometry Nodes, a pure function of time, so any frame renders on its own), `flutter` (wind), `lightning` and `bolt` |
| `blender/lib/shapes.py` | lofts along paths, ellipsoids, lathes, boxes, cylinders, spikes and strips, flat decals |
| `blender/lib/anime.py` | characters: a rig of two empties (`upper` breathes), a drawn face as decals by mood and age, hair locks, a headband with tails, `breathe` |
| `blender/lib/landscape.py` | ridge after ridge of mountains, ink-painting pines, a bank, a river, a sky card, banks of mist |
| `blender/lib/props.py` | a pier plank by plank, a thatched hut with its lit door, a covered boat, a paper lantern |
| `blender/castsheet.py` | a cast sheet per character (front, three quarters, side, back and the head) in the film's look |

A film keeps only what is its own under `films/<id>/blender/`: its cast's designs (`rf/cast.py`: colours,
proportions, joints, costume), its places (`rf/sets.py`: where the pieces stand), and its shots (`shots/<shot>.py`:
the camera, the blocking, the timing).

Lightning is one scene property, `toon.FLASH` (0 to 1), that every toon material, the sky, the rain and the splashes
read: `toon.lightning(scene, [2.1], frames, fps, f0)` keys it (one frame of white-out, a quick fall, a second flicker),
the lit bands whiten while the shade stays, the far ridges (`cel(..., flash=0)`) stand dark against a white sky, and
`toon.bolt` draws the fork only while it flashes. Give the strike a `thunder` cue in `data/mix.json`.

```sh
blender -b -P blender/castsheet.py -- --film <id> --module rf.cast --builders shinza,tsuru --res 480x720
blender -b -P blender/render.py -- --film <id> --shot standoff --mode look --engine eevee --frames 1431,1482 --res 1920x1080
blender -b -P blender/render.py -- --film <id> --shot standoff --mode final --engine eevee --samples 32
```

The pure halves (lofted rings, the eye's outline, ridges, the bank, a strike's flash, a bolt's path) are tested
without Blender: `cd blender && python3 -m pytest -q tests/test_anime_parts.py`.

### Realistic people

Characters with real anatomy (proportions, hands, a modelled face) are built on MakeHuman's MPFB extension, installed
once into Blender (GPL; the bodies and their shells are MakeHuman's CC0 assets):

```sh
blender --command extension install-file -r user_default -e add-on-mpfb-v2.0.18.zip   # from extensions.blender.org/add-ons/mpfb
```

| module | what it makes |
|---|---|
| `blender/lib/human.py` | `make(name, sex, age (years), muscle, weight, height, proportions, ancestry, face)`: a body on MakeHuman's rig with its skin weights, its face from MakeHuman's expression units, and the shells MakeHuman fits to every body split out as parts (`eyes`, `lashes`, `hair`, `tights`, `skirt`); `eyes` (round eyeballs drawn by `toon.eye`), `lashes` (the upper lash line), `brows`, `skin_like`, `skin_by_height` and `bind` (skin anything to the rig), `attach` (bone-parent what is built round the posed body); posing in the person's frame: `reach` (IK), `hold`, `turn`, `lower`, `grip`, `breathe`; `discard` drops the raw shells once dressed |
| `blender/lib/garments.py` | clothes cut from the shells and skinned like them: `cut` (with `flare` for skirts, `v_neck`, `above`, a feathered or snapped edge), `legs` (wide divided trousers: a hakama), `belt` (an obi or a headband following the real cross-section, with a knot and ribbon tails), `lapels` (a kimono's crossed collar) |
| `blender/lib/hair.py` | `mass` (the scalp shell cut to a hem round the head: `hem_profile`), `scalp` and `hairline`; `clumps` (anime clumps flowing from a crown whorl, with strand lines), `sections` (hair combed back in inked sections), `locks` (flat strands), `tube`, `ribbon`; `bun` and `coil` (hair wound up, with a pin) |
| `blender/lib/props.py`, `marks.py` | `straw_cape` (a mino: tiers of fine straw tied at the neck, weighted for the wind); `marks.strokes` (ink lines drawn onto a face: age lines, scars) |

Everything is built in the rest pose (MakeHuman's front is -y) and skinned, then posed; a film's cast builder wraps the
rig in a root empty turned to face +x, so shots place and turn characters as before. Builders return the root, the
rig, the head's centre (for `castsheet.py`), the parts the wind moves (`toon.flutter(..., pin=True)` holds a ribbon at its root) and a `breathe(frames, fps)` that keys the breath.
The numpy halves (the age slider, the eyeball's fit, flare and pleats, the V-neck, a belt's outline, a hair hem, a
strand) are tested without Blender in `blender/tests/test_people.py`.

### Drawn characters (cels)

A TV anime draws its cast in 2D over its backgrounds, and that is what reads as anime: designed silhouettes, ink
lines that swell and taper, flat colour with one or two drawn shadow shapes. Characters can be drawn from code the same
way and set into a Blender shot as Grease Pencil: `blender/lib/cels.py`.

| piece | what it is |
|---|---|
| `Drawing` | one frame of a character: named layers bottom to top, each a list of `Fill`s and `Line`s in the drawing's own units (x right, y up); a layer can be clipped to others (`mask=("skin",)`: a cel shadow inside the skin, an iris inside the eye's white) |
| `spline`, `line`, `fill` | smooth curves through control points (sharp at `corners`); a tapered ink line; a flat fill |
| `lock`, `ribbon`, `teeth`, `zig`, `drop` | a lock of hair coming to a point (with `inner` for its shaded half); a band round a centre line (a cloth tail); jagged edges (a shadow's, a hair sheen's); a bead of water |
| `Eye` | an anime eye: white, iris, pupil, highlights, lash line with its flick, lower lid and crease, opening and closing (`open`) and looking about (`look`) |
| `bend`, `wave`, `blend`, `twos` | motion: a swing about a root growing toward the tip, a travelling wave along a line, in-betweens, drawing frames on twos |
| `flash` | a colour in a lightning flash: lit colours bleach to a cold white, shades sink, ink stays (`Drawing.recolor`) |
| `build(name, {frame: Drawing}, scale=)` | one Grease Pencil object in its local x-z plane; a drawing holds until the next |

A film's drawn character is a module of functions of time returning drawings (`films/<id>/blender/rf/<name>_cels.py`:
`closeup(t, flash=, eyes=)` in head units, `full(t, flash=)` in metres, feet on y 0); the shot calls them on twos and
places the objects as cards facing the camera. Judge a drawing on a cel sheet before it goes into a shot:

```sh
blender -b --factory-startup -P blender/celsheet.py -- --film <id> --module rf.shinza_cels --draw sheet \
    --times 0.3,1.5,2.6 --res 700x800 --box=-0.85,-0.75,0.65,1.25
```

Grease Pencil in Blender 5.2: a stroke fills when its `fill_id` is set (`hide_stroke` hides its line), colours are per
stroke and point (linear, so `cels.linear` converts the sRGB a palette is written in), layers are unlit
(`use_lights` off), and an object hides behind the scene's meshes only when the view layer's Z pass is on (`build`
turns it on), so rain falls in front of a drawn face. The pure parts are tested in `blender/tests/test_cels.py`.

### Compositing (satsuei)

A cel laid flat over a lit background reads as a sticker: evenly lit skin in a storm, no light from the world on it,
no air between the lens and it. An anime's compositing stage (撮影, satsuei) fixes that after the drawing, and
`blender/lib/satsuei.py` does the same in Blender's compositor. `setup(scene, cast)` renders the cast collection on a
view layer of its own ("cast") and the rest on the first ("world"), hides the cast wherever the world's depth is nearer
(Grease Pencil writes the depth pass), and lays it back over the world through a `Look`:

| knob | what it does |
|---|---|
| `gain`, `saturation` | the light's level and colour on the cast, and how much colour the weather leaves it |
| `haze`, `haze_amount` | the air between the lens and the cast: lifts its darks toward the air's colour, so keep it small |
| `para`, `para_amount`, `para_from`, `para_to` | a gradient multiplied over the frame: the side away from the key and the bottom fall into shadow |
| `rims` (up to 3 `Rim`s) | light along the silhouette on the side it comes from (`toward`, on screen), `width` in frame heights, fading in by `soft` |
| `wrap`, `wrap_width` | the blurred world bleeding over the cast's edges (small for small figures: it washes out thin limbs) |
| `flash`, `flash_color` | a cold rim all round, for a lightning frame (pair it with a strong `Rim` from the bolt's side) |

`comp.key(frame, look)` keys a look per frame (in increasing order; an input is keyed only where it changes) and
`comp.hold()` makes every key constant, so each setup of a shot keeps its own light across a cut. Widths are in frame
heights, so a look renders the same at any size. A shot that never calls `setup` is untouched (the compositor stays
off, one view layer). Grade gently: drawings with painted shading wash out under a strong gain and haze, and a strong
rim reads as an outline. Drawn layers that stand in front of the cast, such as rain redrawn on a card, are graded with
it, so draw them brighter by the look's gain.

EEVEE 5.2 leaves a view layer's depth pass all zeros on a frame where it has Grease Pencil objects but every one is
hidden (line art keyed off in a close-up); the cast would then vanish behind everything. `setup` adds an empty Grease
Pencil object to the world that is never hidden. The pure half (`values`, `shift`, `axis`) is tested in
`blender/tests/test_satsuei.py`.

## 8. Render

```sh
cd app && bun scripts/timeline.ts --film <id>
bun scripts/render.ts stills --film <id> --t ...          # one still per shot is the quickest review
bun scripts/render.ts video --film <id> --samples auto    # out/<id>/<id>.mp4, the mix muxed in
```

## What *The Rain Ferry* cost

Measured from the services' balances (`data/gen.json` records each picture and clip's own cost):

| what | service | spend |
|---|---|---|
| 2 sheets, 1 location key, 27 keyframes, 1 re-roll, 1 clean plate, 2 style tests | Higgsfield (GPT Image 2.5 medium 2K at 1 credit, Nano Banana 2 at 2) | 33 credits |
| 16 clips of 6 s and 1 model test (Hailuo 2.3 fast at 4, Hailuo 2.3 at 6, Seedance 2.0 Mini at 5) | Higgsfield | 77 credits |
| 15 lines, 2 takes each, and one line re-taken | ElevenLabs v3 | about 450 credits |
| 20 sound effects and beds | ElevenLabs sound generation (about 10 credits a second) | 560 credits |
| 2 score cues, 103 s | ElevenLabs Music (billed a little after the call returns) | about 1,235 credits |

Lessons: both services rate-limit concurrent jobs (three or four at a time); the video service may answer with a preset
recommendation instead of a job (resubmit with `declined_preset_id`); check every voice take; budget music by the
subscription's counter a minute after the call, not the response.
