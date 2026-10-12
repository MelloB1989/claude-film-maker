# The Blender plate pipeline

Some shots are better made in Blender than in the engine: a glossy hero object, real depth of field, thousands of
fibres. `blender/render.py` renders such a shot headless into a **plate**, one linear EXR per film frame, and the
engine composites the plate into the scene that shows it, under its own look, overlays and transitions. The shot can
also **track** points (empties) so the engine's type and marks sit on the 3D object frame by frame.

Everything here works on one film at a time, picked as everywhere else (docs/CONVENTIONS.md): `--film <id>`, else
`$FILM`, else `showcase`. Nothing in `blender/lib` names a film; a film's shots live in its own folder.

```
films/<id>/
  film.json                     format, fps, theme (read by Blender too)
  blender/shots/<shot>.py       the film's Blender shots
  data/timeline.json            scene windows, exported by the engine (cd app && bun scripts/timeline.ts --film <id>)
  data/look/<shot>.json         optional: a shot's world (camera, sizes, tuning), shared with its engine scene
  data/track/<shot>.json        written by render.py: tracked anchors (small; committed)
out/<id>/
  plates/<shot>/####.exr        written by render.py: the plate, #### = film frame - the shot's first frame (f0)
  plates/<shot>/proxy/####.png  its 8-bit proxy, for previews
  look/<shot>/<frame>.png       look-mode stills
  blender/<shot>.blend          --save-blend
```

## Requirements

- **Blender** 4.2 LTS or later (the pipeline was developed on 5.x), headless. `blender` on the `PATH`, or set
  `BLENDER` to the binary and run `"$BLENDER" -b -P ...` (on macOS:
  `/Applications/Blender.app/Contents/MacOS/Blender`). Commands run from anywhere: paths are found from the repo.
- **A GPU** for finals: Cycles tries OptiX, CUDA, HIP, oneAPI and Metal in turn and renders on the first backend with a
  device. `FILM_GPU=CUDA` (or a comma list, or `none`) pins the choice. Previews and look frames fall back to the CPU;
  a final stops rather than spend hours on the CPU, unless `--allow-cpu`.
- The engine's `app/src/engine/themes.json` (the theme presets) in the checkout.

## Adding a shot to a film

1. Start from an example: `cp blender/examples/shots/hero_orbit.py films/<id>/blender/shots/` (see
   [blender/examples/README.md](../blender/examples/README.md)), or write one.
2. Give it a window: a `scene` id from the film's timeline, or explicit `frames`.
3. Render a look pass, then previews, then the final; composite the plate in the engine scene.

### The shot file

A shot is a Python file defining `SHOT` and `build(ctx)`. Import `bpy` and `lib` inside `build()`, so the file loads
(and its pure helpers can be tested) without Blender.

```python
SHOT = {"scene": "hero", "track": ["hero", "callout"]}

def build(ctx):
    import bpy
    from lib import lights, materials, rig
    ...  # make the objects, the camera (scene.camera), the lights, the animation
```

| `SHOT` key | meaning |
|---|---|
| `scene` | The engine scene the plate composites into: with `frames` left at `"scene"`, the shot spans exactly the film frames the engine shows that scene on (from `data/timeline.json`, else `data/vo.json`'s `scenes`). |
| `frames` | `"scene"` (default), or `[f0, f1]`: explicit film frames, half-open. Explicit frames need no timeline. |
| `track` | Names of objects (usually empties) whose screen positions are written to `data/track/<shot>.json` for every frame of the shot, in every mode. |
| `look` | The film frames look mode renders when `--frames` is not given: `"a-b,c"` or a list. |
| `black_ok` | Film frames that are meant to be black (a fade from black): the blank-frame guard does not ask them to be lit. `"a-b,c"`, a list or range, or a function of the film frame. Declare only what is meant to be black. |

Any other key is an error, so a misspelt `trak` cannot pass for a shot that tracks nothing.

Blender's frame numbers **are** film frames: `render.py` sets `frame_start = f0`, so a key at `ctx.frame(t)` lands on
the engine's frame for film time `t`. Key one frame beyond each end (`ctx.f0 - 1`, `ctx.f1`) so the motion blur on the
first and last frames matches the middle.

### What `build(ctx)` gets

| `ctx.` | |
|---|---|
| `scene` | The fresh scene: Cycles (or EEVEE), the film's fps, AgX view, centred motion blur, a black world. |
| `film` | The film (`lib/film.py` `Film`): `id`, `config` (film.json), paths. |
| `shot`, `mode` | The shot's name, `look` / `preview` / `final`. |
| `f0`, `f1` | The shot's film frames, `[f0, f1)`. |
| `res` | The render size in px. |
| `size` | The film's **logical** frame, `(width, height)`: what tracks and the engine's px are in. |
| `fps` | The film's fps. |
| `theme` | The film's resolved theme; it is also **in use**, so library calls take palette roles. |
| `timing` | Scene windows, voiceover words (`word(line, i).frame`), `beats_in(f0, f1)`, `downbeats_in(f0, f1)`. Beats come from the audio analysis, or a grid synthesised from film.json's `audio.bpm`, `offset`, `beatsPerBar`. |
| `spec` | `films/<id>/data/look/<shot>.json` parsed, or `None`: the world the shot shares with its engine scene. |
| `frame(t)`, `time(f)` | Film time to film frame (rounded as the engine rounds) and back. |

### Colour: palette roles

Never write a hex into a shot. The film's theme is in use when `build()` runs, and the library takes **roles**:
`bg`, `bg2`, `surface`, `surface2`, `rule`, `ruleStrong`, `fg`, `fgDim`, `fgFaint`, `accent`, `accentBright`,
`accentDim`, `accent2`, `accent2Bright`, `accent2Dim` (docs/CONVENTIONS.md).

```python
materials.gloss("fg")                      # clear-coated product finish
materials.satin("surface2")                # the engine's satin
materials.emission("accent", 4.0)          # a glowing element
lights.studio(world="bg")                  # key, rim, fill; the world in the theme's background
theme.linear("accent2")                    # linear RGB, for anything else
```

Only the accents may glow: the engine's bloom keys on them, so keep `fg` and `bg` materials non-emissive. The world
is the theme's `bg`, so an opaque plate meets the engine's background without a seam.

### The camera

For a plate the engine draws over (or a 3D engine scene that intercuts with it), share the camera: `lib/rig.py` is the
engine's `CameraRig` in Python (keys of time, position, target, vertical fov, roll; the same spline and eases), and
`rig.engine_camera(size=ctx.size)` is the engine's gate, 20.25 mm tall and fit vertically, so a vertical fov means the
same thing in both renderers in every format. Put the keys in `data/look/<shot>.json` and read them on both sides.

### The library

`blender/lib`: `film`, `theme`, `timing`, `cli` (bpy-free), `setup`, `lights`, `materials`, `rig`, `export` and the
render guards `blank`, `handlers`, `scan`. Hero motifs, each colour by role, geometry pure numpy:

| module | motif |
|---|---|
| `thread` | `ply_thread` (plies twisted round a path, with fuzz); `fibre_rope` / `MacroRope` (a 3-ply rope fibre by fibre that can fray and part); `strand_thread` (an `fg` 3-ply with an `accent` and an `accent2` strand glowing in its grooves, lit on cue with `strand_glow`; its numbers from the engine's `app/src/engine/thread-look.json`, a film's own `data/look/thread.json` overriding them: `thread.strand_preset(ctx.film)`). |
| `bead` | An engraved glass bead (bore, chamfered lips, text etched round its face in any font). |
| `braid` | A three-strand plait whose pattern rides its material; threads that move along their own length. |
| `weave` | A loom: warp lanes, plain weave, the shed, and a weaving clock that lays a pick on every beat. |

Geometry a frame handler moves needs `thread.deform_blur(ob)` or Cycles renders it sharp under motion blur;
`blender/check_deform.py --film <id> --shot <shot>` lists objects that miss it.

## Commands

```sh
blender -b -P blender/render.py -- [--film <id>] --shot <shot> --mode look|preview|final
        [--frames a-b,c] [--res WxH] [--samples N] [--engine cycles|eevee] [--save-blend] [--allow-cpu]
blender -b -P blender/render.py -- [--film <id>] --shot <shot> --scan [--expect-res WxH]
blender -b -P blender/check_deform.py -- [--film <id>] --shot <shot> [--shot ...]
```

`--shot` is a name in `films/<id>/blender/shots/`, or a path to any shot file (named by its stem).

| mode | render size | samples | frames | writes |
|---|---|---|---|---|
| `look` | half the logical frame (960x540 for 1920x1080) | 32 | `--frames`, else `SHOT["look"]`, else all | plates + AgX stills |
| `preview` | half the logical frame | 16 | all, or `--frames` | plates |
| `final` | 4/3 of the logical frame (2560x1440 for 1920x1080) | 128 | all, or `--frames` | plates |

Sizes follow the film's format: a vertical film previews at 540x960 and finals at 1440x2560. `--res` overrides the
size but must keep the film's aspect. `--frames` are film frames, inclusive; an empty `--frames` is an error, never
"every frame". `--scan` renders nothing: it checks the shot's plates against its window (all there, none extra, one
size, none blank or bad, no jump in level) and exits 3 on any problem; `--expect-res` demands one size (a final's).

| exit | meaning |
|---|---|
| 0 | every frame written, or the scan found nothing wrong |
| 1 | an error, including a frame-change handler that raised (the frame would show a stale pose) |
| 3 | a frame stayed blank or bad after two retries, or the scan found a problem; the message says which `--frames` finish the run |

Environment: `FILM` (the film), `FILM_GPU` (GPU backends), `FILM_FORCE_BLANK=F[:N],...` (test hook: film frame F
renders black on its first N attempts, to prove the retry).

### The guards

- **Blank frames.** Two renders sharing a GPU have written runs of black frames with a clean exit. Every frame is
  checked as its EXR lands: not finite anywhere, blank (brightest value at most 1e-4 linear), or a black render tile
  makes it bad; it is rendered again (after 15 s, then 30 s), and a frame still bad stops the run with exit 3.
- **Handlers.** A frame-change handler that raises (Blender prints it and carries on) fails its frame with exit 1.
- **Scan.** `--scan` after a render, before compositing.

## Outputs

- **Plate:** `out/<id>/plates/<shot>/####.exr`, linear half-float RGBA (ZIP), premultiplied alpha, in the scene's
  linear working space (Linear Rec.709, the engine's linear sRGB). No view transform: the engine applies its own look.
  `####` is the plate index, film frame minus `f0`. A new render of a frame replaces it.
- **Proxy:** `out/<id>/plates/<shot>/proxy/####.png`, 8-bit sRGB with straight alpha at half the logical size,
  encoded from the EXR with the plain sRGB transfer (clipped at 1): the preview's stand-in.
- **Look stills:** `out/<id>/look/<shot>/<film frame>.png` (look mode), through AgX, for looking at.
- **Track:** `films/<id>/data/track/<shot>.json`, one sample per film frame from `f0`, positions in the film's
  logical px from the top-left, `visible` 1 when the point is in front of the camera and inside the frame:

  ```json
  { "fps": 30, "f0": 181, "width": 1920, "height": 1080,
    "anchors": { "hero": [[960.0, 540.0, 1], [961.2, 540.1, 1]], "callout": [[1310.5, 498.2, 1]] } }
  ```

  Samples are taken at each frame's own time, the middle of the motion-blur shutter, where the plate's blur is
  centred.

## Compositing in the engine

The engine's `Plate` (`app/src/engine/plates.ts`) reads a shot's frames from `out/<id>/plates/<shot>/####.exr`, and
the proxies from `out/<id>/plates/<shot>/proxy/####.png` in previews (or a draft export that opts into them). The
plate index for film time `t` is the engine's frame for `t` minus `f0`, so plate frame `n` is on screen on exactly
film frame `f0 + n`. An export awaits every frame's EXR and fails rather than show a neighbour. `plate.draw()` lays
the frame into the scene's linear buffer, replacing it or over it by its premultiplied alpha; the engine's look,
bloom and grain then apply to the plate as to anything the engine draws.

`Track` (`app/src/engine/track.ts`) reads `films/<id>/data/track/<shot>.json` and gives an anchor's position and
visibility at any time (interpolated between frames), in the same logical px the engine lays type in, so a label can
ride the hero.

A scene that composites a plate typically does this (in outline; plates.ts and track.ts have the exact API):

```ts
const plate = new Plate('hero_orbit', f0);           // f0: the shot's first film frame (the track file has it)
const track = await Track.load('hero_orbit');
// prepare(t): await plate.prepare(t)
// render(t):  plate.draw(renderer, comp, out, t); then draw a label at track.at('callout', t)
```

## Testing

The bpy-free half (film selection, format, fps, theme, timing, paths, the shot contract, the guards, the motifs'
geometry, the examples' framing) runs without Blender:

```sh
cd blender && python3 -m pytest -q        # needs numpy and pytest
```

Tests build their films under a temporary folder and never read the repo's `films/`; the engine's own files
(`themes.json`, `palette.ts`, `thread-look.json`, `thread3d.ts`, `util.ts`) are cross-checked when the checkout has
them. To prove the pipeline end to end on a machine with Blender, render the smoke test into any film and scan it:

```sh
blender -b -P blender/render.py -- --film <id> --shot blender/examples/shots/smoke_cube.py --mode preview
blender -b -P blender/render.py -- --film <id> --shot blender/examples/shots/smoke_cube.py --scan
```
