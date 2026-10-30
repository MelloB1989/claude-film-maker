# The kit

Every kit block is a Scene configured by `params` alone, so a film uses it from `film.ts` without writing code:

```ts
{ id: 'stat', scene: Counter, length: { bars: 2 }, transition: 'xfade', params: { value: 91.4, suffix: '%', land: { beat: 4 } } }
```

Each block's source starts with a comment that lists every param; this page is the overview. Sizes are reference px of
a 1080 px short side, so a block looks the same in every format. Positions (`x`, `y`, widths) are fractions of the
frame. Colours are palette roles (`fg`, `fgDim`, `accent`, `accent2`, `surface`, ...) or `#rrggbb`. Times (`at`,
`land`, `delay`) are a `TimeRef`: seconds after the shot starts, `{ beat: n }` or `{ bar: n }` on the film's grid.

## Params every block takes

| param | default | |
|---|---|---|
| `background` | `'theme'` | `'theme'` (the bg role), `'none'` (transparent: for overlays and stacking), a role, `#hex`, or `{ from, to, angle }` (a gradient) |
| `glow` | 3 | the level the block's glow layer is added at (0: no glow). Only accents glow; `fg` never blooms |
| `exit` | `'none'` | `'fade'`, `'rise'`, `'sink'` (blocks that leave unit by unit also take `'blur'`) over `exitDur` s at the shot's end |

## Type: `@kit/text`

| block | what it does | key params |
|---|---|---|
| `KineticText` | the hero type block: lines that land word by word, glyph by glyph or line by line | `text` or `lines`, `reveal` (`rise` `slam` `blur` `track` `typewriter` `scramble` `wipe` `fade` `ghost`), `unit`, `sync` (`stagger` `beats` `vo`), `emphasis`, `emphasisStyle` (`glow` `marker` `underline`), `kicker`, `sub`, `size`, `align`, `x`, `y`, per-line `at` and `diff` (`-` strikes, `+` glows) |
| `TitleCard` | a film's opening or a chapter title, with an accent rule | `title`, `kicker`, `sub`, `rule`, and every KineticText param |
| `EndCard` | the name, tagline, a call-to-action pill and a URL, with a logo | `name`, `tagline`, `cta`, `url`, `logo` (`assets/logo.svg`), `aura` |
| `Quote` | a pull quote with a glowing quote mark | `quote`, `by`, `byline`, `sync: 'vo'` |
| `LowerThird` | a name and title in the lower third | `name`, `title`, `side`, `at`, `color` |
| `BulletList` | items landing on the beat with drawn marks | `items`, `icon`, `title`, `kicker`, `focus`, `every` |
| `FeatureList` | feature cards in a grid, one per beat | `items: [{ title, desc, icon }]`, `title`, `columns` |
| `Marquee` | rows of big words scrolling across | `words`, `rows`, `speed`, `outline`, `tilt`, `emphasis` |

## Data: `@kit/data`

| block | what it does | key params |
|---|---|---|
| `Counter` | a big number rolling, flipping or counting to its value, landing on a beat | `value`, `prefix`, `suffix`, `style` (`roll` `flip` `count`), `land`, `dur`, `label`, `kicker` |
| `BarChart` | bars growing in on the beat, one highlighted | `data: [{ label, value, highlight }]`, `orientation`, `suffix`, `title`, `every` |
| `LineChart` | a line drawing itself, an accent fill under it, a glowing head | `data`, `labels`, `every` or `dur`, `area`, `grid` |
| `StatGrid` | two to four stats landing in turn | `stats: [{ value, label, prefix, suffix }]`, `style`, `every` |
| `Compare` | before → after, with a delta badge | `from`, `to`, `suffix`, `delta`, `land` |

## Overlays: `@kit/overlays`

Overlays go in `film.ts` `overlays` (default: the whole film), drawn over whatever shot is on screen.

| block | what it does | key params |
|---|---|---|
| `Captions` | social captions from the voiceover, word by word | `style` (`karaoke` `pop` `line`), `position`, `maxWords`, `box`, `highlight` |
| `Watermark` | a corner label or logo | `text`, `image`, `corner` |
| `ProgressBar` | a thin progress bar with chapter ticks | `position`, `marks`, `color` |
| `SafeArea` | action/title-safe guides and a feed's UI zones (for layout checks) | `thirds`, `social` |

## 3D: `@kit/3d`

Blocks on the engine's Stage: a dim studio, depth of field and supersampling; extruded type and logos in satin with
glowing accent seams. Every block takes a camera move (`camera`: `push`, `pull`, `orbit`, `drift`, `dolly`, `crane`,
`static`, or keys), `whip` (a whip out on the cut), depth-of-field params (`dof`, `fstop`, `focus: 'auto'`), the light
rig's levels, and `background` (`'none'` stacks it). Full reference: [kit/3d.md](kit/3d.md).

| block | what it does | key params |
|---|---|---|
| `Hero3D` | an extruded headline landing word by word, glyph by glyph or line by line | `text`, `emphasis`, `reveal` (`slam` `rise` `tip` `drop` `scale`), `sync` (`stagger` `beats` `vo`), `exit` (`fall` `blow` `scatter`), `pulse` |
| `Panel3D` | terminals, editors, JSON and chat panels floating in 3D, typing in | `panels` or `panel` (`kind`, `title`, `lines`, `type`), `layout` (`single` `pair` `stack` `fan`), `highlight` |
| `GlyphCloud` | thousands of glyphs drifting past the lens, resolving into a word | `resolve`, `resolveAt`, `count`, `sparkle` |
| `Logo3D` | the film's SVG extruded and bevelled, spinning in; colour fills take the accent | `logo`, `name`, `reveal` (`spin` `rise` `scale`), `tagline` |
| `Cards3D` | editorial cards in a carousel, fan, stack or grid, advancing on the beat | `cards: [{ title, lines, image }]`, `layout`, `every` |

## Backgrounds, layering and media: `@kit/bg`, `@kit/stack`, `@kit/media`

Full reference: [kit/bg-media.md](kit/bg-media.md).

| block | what it does | key params |
|---|---|---|
| `Aurora`, `MeshGradient`, `Grid`, `Particles`, `Warp` | shader backgrounds in the theme's accents | `color`, `color2`, `intensity`, `speed`, `scale`, `seed`, `pulse` (`beat` `downbeat`), `glow` |
| `Stack` | several blocks layered in one shot; layers above the first default to a transparent background | `layers: [{ scene, params, blend, opacity, start, end, fade }]` |
| `Image` | a picture, framed, with a Ken Burns move and an entry | `src`, `fit`, `from`/`to`, `radius`, `shadow`, `entry` |
| `Video` | a clip, frame-exact (`bun scripts/media.ts --film <id>` extracts its frames) | `src`, `clipStart`, `rate`, `loop`, and Image's framing |

Image and Video also take `src: 'frames/<name>'`: an image sequence rendered straight into `out/<id>/media/<name>/` (Blender, say) with a `meta.json` `{ fps, count, width, height }`, plus `"ext": "png"` for lossless frames (default `jpg`). `count: 1` is a still.
| `Device` | a screenshot or clip in a browser window or a phone | `device` (`browser` `phone`), `src`, `url`, `scroll`, `rim` |

## Transitions, looks and beat effects: `@kit/fx`

Full reference: [kit/fx.md](kit/fx.md).

- **Transitions**, on a shot (`transition: 'wipe'` or `{ kind: 'iris', edge: 'accent2' }`): `cut`, `whip`, `zoom`,
  `match`, `xfade`, `dip`, `wipe`, `iris`, `slide`, `spin`, `flash`, `glitch`.
- **Looks**, on the film (`"look"` in film.json) or a shot (`look`): `film`, `clean`, `cinematic`, `neon`, `dreamy`,
  `gritty`, `retro`. The grade params (`saturation`, `contrast`, `warmth`, `tint`, `lift`, `letterbox`, `scanlines`)
  go in any `post`.
- **`BeatFx`**, an overlay: `punch` (zoom kicks), `shake`, `flash`, `pump` (exposure) and `bars` (letterbox),
  each `on` beats, downbeats, backbeats or given times.

## Your own scenes

A film's own scenes go in `films/<id>/scenes/*.ts` and are loaded lazily (`scene: () => import('./scenes/pulse')`).
The quickest start is `Scene2D` (`@kit/scene2d`): it clears the background, owns a Canvas2D layer in logical px and a
glow layer that blooms, and composites them; the scene only draws.

```ts
import { Scene2D, glowInk, type Frame } from '@kit/scene2d';
import { W, H } from '@engine/gl';
import { rgba } from '@engine/palette';
import { F, font } from '@engine/type';
import { onBeat } from '@engine/motion';

export default class Pulse extends Scene2D {
  draw(c: CanvasRenderingContext2D, f: Frame) {
    const r = (150 + 60 * onBeat(f, 0.3)) * this.u;
    c.font = font(F.display(87.5, 800), 64 * this.u);
    c.textAlign = 'center';
    c.fillStyle = rgba('fg');
    c.fillText(this.p('word', 'Pulse'), W / 2, H / 2);
    const g = this.glow;                     // added as light: blooms
    g.strokeStyle = glowInk('accent', onBeat(f));
    g.lineWidth = 6 * this.u;
    g.beginPath(); g.arc(W / 2, H / 2, r, 0, Math.PI * 2); g.stroke();
  }
}
```

Rules every scene keeps: a frame is a pure function of its time (`f.t`, `f.lt`, the beat grid in `Frame`, the
voiceover), randomness is seeded (`@engine/util` `hash`, `mulberry32`), and `dispose()` frees what it made. The engine
renders motion-blur sub-frames out of order and seeks anywhere. For 3D, `@engine/stage` (Stage, CameraRig, depth of
field), `@engine/type3d` (extruded type), `@engine/panels` (UI panels), `@engine/glyphs` (glyph fields) and
`@engine/thread3d` are the building blocks the 3D kit uses.
