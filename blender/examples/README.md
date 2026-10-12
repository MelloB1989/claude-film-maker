# Example Blender shots

Shots belong to films. A film's Blender shots live in `films/<id>/blender/shots/<shot>.py`, and
`blender/render.py --film <id> --shot <shot>` renders them into plates the engine composites. This folder holds
shots to start from; nothing renders from here unless you point `--shot` at the file.

| shot | what it is | needs |
|---|---|---|
| `shots/hero_orbit.py` | A product-style hero: a glossy torus knot in the theme's `fg` with a glowing `accent` ring, three-point light, a slow orbit with shallow focus over a studio floor. Tracks `hero` (its centre) and `callout` (a point on its rim). | a scene `hero` in the film's timeline |
| `shots/smoke_cube.py` | The pipeline's smoke test: a spinning cube, a tracked corner and the film frame number burned in, over film frames 40 to 59. | nothing (explicit frames) |

Both take every colour from the film's theme and frame themselves for the film's format (landscape, vertical,
square, portrait, cinema), so they work in any film unchanged.

## Use one in a film

```sh
mkdir -p films/<id>/blender/shots
cp blender/examples/shots/hero_orbit.py films/<id>/blender/shots/
```

`hero_orbit` spans the frames the engine shows the scene `hero` on, read from `films/<id>/data/timeline.json`
(export it with `cd app && bun scripts/timeline.ts --film <id>`). Name a scene of your film `hero`, or edit the
shot's `SHOT["scene"]` to the scene its plate composites into, or give it explicit film frames:
`SHOT = {"frames": [0, 150], "track": ["hero", "callout"]}`.

Tune its look without editing it: `films/<id>/data/look/hero_orbit.json` (every key optional; the engine scene can
read the same file):

```json
{ "orbitDeg": 30, "spinDeg": -20, "fov": 24, "fstop": 2.8, "elevationDeg": 14, "color": "fg", "glow": "accent",
  "glowStrength": 4.0 }
```

## Render it

`blender` is Blender 4.2 or later on the `PATH`, or `$BLENDER` (on macOS
`/Applications/Blender.app/Contents/MacOS/Blender`).

```sh
blender -b -P blender/render.py -- --film <id> --shot hero_orbit --mode look      # quick stills, through AgX
blender -b -P blender/render.py -- --film <id> --shot hero_orbit --mode preview   # half-size plates
blender -b -P blender/render.py -- --film <id> --shot hero_orbit --mode final     # 4/3-size plates, on the GPU
blender -b -P blender/render.py -- --film <id> --shot hero_orbit --scan           # check the plates
```

Or try an example in a film without copying it, by path:

```sh
blender -b -P blender/render.py -- --film <id> --shot blender/examples/shots/smoke_cube.py --mode preview
```

It writes `out/<id>/plates/<shot>/####.exr` (the plate), `out/<id>/plates/<shot>/proxy/####.png` (its proxy) and
`films/<id>/data/track/<shot>.json` (the tracked anchors, in the film's logical px). The whole contract, the options
and how the engine composites a plate: [docs/PIPELINE-BLENDER.md](../../docs/PIPELINE-BLENDER.md).
