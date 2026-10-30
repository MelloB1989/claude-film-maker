# Your Life As a Lighthouse Keeper: the drawings

Each scene of the film is a Blender **drawing**: `blender/draw.py` builds it from simple 3D shapes in the flat 2D
cartoon style of `blender/lib/toon.py` (flat colours, Line Art ink, dot-eyed people) and renders PNG frames into
`out/lighthouse-keeper/media/<name>/` that the engine plays as `src: 'frames/<name>'`, with its own slow camera
moves (Ken Burns) on top. The style lives in `data/look/toon.json` (colours by name, ink, the cast).

```sh
cd /home/nikhil/code/claude-film-maker
blender -b --factory-startup -P blender/draw.py -- --film lighthouse-keeper --shot <name> --res 960x540 --out /tmp/d   # a draft
blender -b --factory-startup -P blender/draw.py -- --film lighthouse-keeper --shot <name> --frames 1,12 --out /tmp/d  # some frames
blender -b --factory-startup -P blender/draw.py -- --film lighthouse-keeper --shot <name>                # the final
```

`blender` renders on the CPU here (software GL): a still takes ~10 s, a sequence frame ~4–6 s at its final size.

## A drawing file

```python
# one line on what the scene shows
DRAW = {"scene": "wake", "fps": 6}          # fps 0: a still (rendered 3840x2160); 12: smooth motion; 6: snap acting

def build(ctx):
    import _sets as S                       # this folder's shared set pieces (lighthouse, island, sea, sky, ...)
    from lib.toon import Person, D2R
    t = ctx.toon
    t.world("wall_night")                   # the background colour
    t.group("room")                         # an inked group: its line weight is held on screen at its distance
    t.card("wall", t.rect(30, 12, 0, 3), 0.05, "wall_night", loc=(0, 2.5, 0))
    t.group("people")
    k = Person(t, {**t.cast["keeper"], "skin": "skin_night"}, "keeper", loc=(0, 0, 0), hands=("rest", "grip"))
    k.expression("tired", frame=ctx.frame(0)); k.eyes("closed", ctx.frame(0)); k.eyes("open", ctx.frame(0.6))
    t.camera("cam", (0, -9, 2.0), (0, 0, 1.8), lens=70)
```

- `ctx.frame(t)` is the drawing's frame for `t` seconds into the scene (1-based). Key faces and poses there.
- Shapes: `t.blob` (spheres, superellipsoids with `n=`, reshaped by `shape=`: `t.lumpy`, `t.teardrop`,
  `t.flat_bottom`), `t.card` (a flat cut-out polygon in XZ facing -Y, extruded `depth` towards +Y), `t.cyl` (cylinder or
  frustum, `r2=`), `t.box`, `t.torus` (`arc=` for part of a ring), `t.line` (an ink mark through 3D points; `col=` for a
  coloured line), `t.mark_on` (a mark laid on a surface), `t.boolean`, `t.onto` (project onto a surface), `t.facing`,
  `t.orient`. Helpers `t.rect`, `t.ring`, `t.leaf`, `t.densify`.
- Collections: `t.group(name)` starts an inked group (all later shapes go in it, until the next `t.group`/`t.use`);
  `t.face` is ink that is never outlined (marks); `t.plain` is flat colour never outlined (skies, glows, beams, rain,
  flames). Put near and far things in separate groups so each keeps its line weight.
- Colours are names from `data/look/toon.json`; a `"#rrggbb"` literal is fine for a one-off prop. Transparent flat
  colour: `alpha=` on blob/card/cyl (glows, glass).
- `Person(t, spec, name, loc, rot, hands=(right, left), expression=...)`: `.expression(name, frame)` (`neutral smile
  worried sad tired surprised stern content`), `.eyes("open"|"closed", frame)`, `.blink(frame)`, `.look(dx, dz, frame)`,
  `.head_pose(turn, tilt, nod, frame)` (degrees), `.leg(side, knee_at, foot_at, frame)` with `"legs": true` in the spec
  (then the feet stand on the root, shoulders z≈2.1, head pivot z≈2.25). Without legs the bust stands on its root with
  shoulders at z≈1.08 and the chin at z≈1.45. Points are in the person's own space: -y in front, z up, side -1 = the
  person's right = screen left when facing the camera.
- Hands (`blender/lib/hand.py`): poses `rest flat open cup point fist grip wrap hook pinch pen table` or a dict
  (`{"base": "point", "fingers": [...]}`); `.hand(side, pose, frame)` switches pose (snaps, as limited animation does).
  `.arm(side, elbow_at, wrist_at, frame, palm=dir, fingers=dir)` aims the arm and turns the hand; better,
  `.reach(side, target, palm=dir, fingers=dir, at="grip"|"pinch"|"tip"|"palm"|point, frame=f)` puts that part of the
  hand on the target and solves the elbow (it returns how far short it fell). `.hold(side, prop, offset, rot, at=)`
  parents a prop to the hand at its grip (a bar held in a grip runs along the hand's X). For a far, small figure use
  `"hand": {"detail": "mitten"}` in the spec; for a close-up `"hand": {"subdiv": 3}`. A hand on its own (a close-up):
  `Hand(t, side, parent_empty, skin, size, pose)`, turned with `Person.hand_frame(side, palm, fingers)`.
  Night or lamplit variants: override colours in the spec, e.g.
  `{**t.cast["keeper"], "skin": "skin_warm", "coat": "coat_warm", "beard": {"color": "beard_warm"}, "moustache": {"color": "beard_warm"}}`.
  The keeper wears his cap indoors too, except in bed (`"cap": None`).
- One static camera per drawing (`t.camera(name, loc, at, lens)`); the engine adds the push or pan, so leave ~8%
  room round what matters. Long lenses (50–90 mm) keep it flat and drawn.

## Rules

- Do **not** edit `blender/lib/toon.py`, `blender/draw.py` or `_sets.py` (others are working from them). Put your own
  helpers in your drawing files or a new `_<yourname>.py` beside them. If the kit has a bug that blocks you, work round
  it in your file and say so in your report.
- Look at your drafts (Read the PNG) and iterate until they read clearly and look good: clean silhouettes, no stray
  shapes or broken outlines, the keeper on model, nothing important cut by the frame. Then render the final.
- The look to match: `out/lighthouse-keeper/media/open/0000.png` (the opening, done) and the reference style: flat
  pastel colours, thick even dark outlines, simple round dot-eyed faces, sparse uncluttered sets.

## The scenes (length in seconds; the line spoken over it)

| scene | s | line | who draws |
|---|---|---|---|
| open | 5.9 | It's 1891. You are a lighthouse keeper. | done |
| rock | 5.6 | Your whole world is one rock, one tower, and one light that must never go out. | lead |
| wake | 4.4 | You wake at four, before the sun, because the lamp needs you. | A |
| stairs | 4.5 | A hundred and twelve steps. Every morning. Every night. | A |
| lens | 5.8 | You polish the great lens until it gleams, and trim the wick so the flame burns clean. | A |
| log | 7.3 | Every few hours, you write it all down. The wind. The weather. Every ship that passes. | B |
| boat | 2.8 | Once a month, a boat brings supplies. | lead |
| noboat | 3.1 | If the sea is rough, it doesn't come at all. | B |
| meal | 6.4 | So you eat what you stored. Salted fish. Hard bread. Tea, again. | B |
| storm | 4.3 | Some nights, the storm is so loud you can't hear yourself think. | lead |
| ship | 3.9 | Then you see it. A ship, far too close to the rocks. | lead |
| worry | 3.0 | You keep the light turning. And you wait. | A |
| dawn | 5.1 | By morning, the sea is calm. The ship is gone. Safe. | lead |
| alone | 5.2 | Nobody will ever thank you. Most people will never even know your name. | B |
| light | 2.1 | But tonight, like every night, | B |
| end | 4.8 | you light the lamp. | lead |

Word times (seconds into the scene) are in `data/vo.json` (`lines[].words`, minus the scene's `start`).
