# Backgrounds, Stack and media

Kit blocks a film uses by params alone: animated shader backgrounds (`@kit/bg`), `Stack` to layer blocks in one shot
(`@kit/stack`), and screenshots and clips framed and moved (`@kit/media`). `films/gallery-bg` shows every one.

## Backgrounds (`@kit/bg`)

One fullscreen GLSL pass each, a pure function of film time (no feedback buffers), dithered, laid out on the frame's
short side so landscape, vertical and square all work. Shared params (`kit/bg/base.ts`):

| param | default | |
|---|---|---|
| `color`, `color2` | `'accent'`, `'accent2'` | the two inks: palette roles or `#hex` |
| `background` | `'theme'` | the base: `'theme'`, a role, `#hex`, `{ from, to, angle? }`, or `'none'` (transparent, premultiplied: stack it) |
| `intensity` | 1 | how bright the inks are |
| `speed`, `scale`, `seed` | 1, 1, 0 | motion speed, feature size, another arrangement |
| `pulse`, `pulseAmount` | `'none'`, 0.35 | `'beat'` or `'downbeat'`: swells on the grid and decays (motion.ts onBeat / onDownbeat) |
| `glow` | 1.8 | the level the hottest cores reach. Only an accent (or a saturated `#hex`) is driven past white to bloom; `fg` never is |
| `clock`, `offset` | `'film'`, 0 | `'film'`: one background continues across cuts; `'shot'`: starts at the shot |

| block | its own params |
|---|---|
| `Aurora` | `ribbons` 3, `height` 0.5, `spread` 0.3, `rays` 1, `stars` 0.4 |
| `MeshGradient` | `colors` (up to 6 inks), `blobs` 5, `size` 0.55, `warp` 0.35, `depth` 0.6 |
| `Grid` | `mode` `'floor'` \| `'dots'` \| `'lines'`, `cell` 1, `line` 1.4 px, `horizon` 0.42, `tilt` 0°, `drift` [0, 1], `light` 0.8 |
| `Particles` | `layers` 5, `density` 1, `focus` 0.45, `bokeh` 1, `drift` [0.15, 0.6], `mix` 0.35 |
| `Warp` | `boost` 3 (the beat's speed kick, integrated exactly from the grid), `streak` 1, `density` 1, `center` [0.5, 0.5], `inked` 0.45, `haze` 0.5 |

```ts
{ id: 'open', scene: Aurora, length: { bars: 2 }, params: { pulse: 'downbeat', intensity: 0.8 } },
{ id: 'floor', scene: Grid, length: { bars: 2 }, params: { horizon: 0.36, pulse: 'beat' } },
```

A new background extends `BgScene` and writes `vec4 effect(vec2 p, vec2 uv)`: premultiplied light and its coverage.

## Stack (`@kit/stack`)

One shot made of layers, bottom first. Each layer is any scene with its own params, rendered into a scratch HDR target
at its own time and composited premultiplied over the layers below (as the engine composites overlays).

| layer field | default | |
|---|---|---|
| `scene` | | a Scene class or `() => import('./scenes/x')` |
| `params` | | the layer's params; it also gets `shot` (the shot's id), and every layer above the first defaults to `background: 'none'` |
| `blend` | `'normal'` | `'normal'` \| `'add'` \| `'screen'` \| `'multiply'` |
| `opacity` | 1 | 0..1 |
| `start`, `end` | the shot's | s from the shot's start; a negative `end` counts back from its end. The layer's blocks time their reveals and exits from this window |
| `offset` | 0 | s added to the layer's clock |
| `fade` | 0 | s it fades in after `start` and out before `end` |
| `post` | true | whether its post overrides count (merged bottom to top) |

Stack's own `background` (default `'theme'`) is under the first layer. Its handles are the smallest of its layers', it is
stateful if a layer is, and `prepare(t)` reaches the layers on screen. `checkLayers` validates the params at init.

```ts
{ id: 'title', scene: Stack, length: { bars: 2 }, params: { layers: [
  { scene: MeshGradient, params: { intensity: 0.8 } },
  { scene: Particles, params: { intensity: 0.7 }, blend: 'screen' },
  { scene: TitleCard, params: { title: 'Depth, for free.' }, start: 0.3 },
] } },
```

## Media (`@kit/media`)

`Image`, `Video` and `Device` are Scene2D blocks: `background`, `exit` and `glow` work as on every 2D block, and over a
background they go in a Stack. Media live in the film's folder (`films/<id>/assets/`, `src: 'assets/x.png'`).

Framing params (`kit/media/frame.ts`): `src` (required), `x`, `y` (centre, 0.5), `w`, `h` (box, fractions of the
frame; Image 1, 1), `fit` `'cover'` | `'contain'` (the box takes the picture's aspect), `from`/`to` Ken Burns keys
`{ zoom, x, y }` (pan −1..1 of the slack; Image default zoom 1 → 1.06), `radius`, `shadow` 0..1 (`shadowColor`
`'#000000'`), `border` (a role), `entry` `'none'` | `'fade'` | `'rise'` | `'scale'` | `'wipe'` (`delay`, `entryDur` 0.8),
`drift` [x, y] ref px over the shot, `float` (a slow bob).

- `Image`: a picture, full frame by default.
- `Video`: the same for a clip, plus `clipStart` (s), `rate` 1, `loop` true.
- `Device`: `device` `'browser'` (window lights `lights` `'mono'` or three colours, URL bar `url`, width `w`, screen
  `aspect` 1.6) or `'phone'` (bezel `bezel` `'#08080a'`, dynamic island, height `h` 0.8), `scroll` (0..1, or
  `[from, to]` over `scrollAt` [s, s]) to scroll a tall screenshot, `rim` 0.35 (an accent rim light that blooms,
  `rimColor`), `float` 6, `shadow` 1, `entry` `'rise'`. `src` may be a clip too.

### The clip workflow

Clips play from frames, never from the browser's decoder, so every exported frame is exact:

1. Put the clip in `films/<id>/assets/` (mp4, m4v, mov, webm, mkv).
2. `cd app && bun scripts/media.ts --film <id>` (or `--src assets/x.mp4`; `--force` redoes it) extracts it at the
   film's frame rate to `out/<id>/media/<name>/0000.jpg…` with `meta.json` (`out/` is never committed; rerun after
   replacing a clip).
3. The block loads the frames a frame needs in `prepare(t)` (an LRU, as plates are). Every motion-blur sub-frame of a
   film frame shows the same clip frame (`clipFrame`). Without extracted frames the player falls back to a `<video>`
   element (best effort) and an export fails, naming the command.

```ts
{ id: 'demo', scene: Stack, length: { bars: 2 }, params: { layers: [
  { scene: Particles },
  { scene: Video, params: { src: 'assets/demo.mp4', fit: 'contain', w: 0.7, h: 0.7, radius: 14, shadow: 1, entry: 'scale' } },
] } },
{ id: 'app', scene: Device, length: 4, params: { device: 'phone', src: 'assets/feed.png', scroll: [0, 1] } },
```
