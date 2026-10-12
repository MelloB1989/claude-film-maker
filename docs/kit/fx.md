# Effects: transitions, looks and beat effects

Everything here is set by params in a film's `film.ts` (and `film.json` for the film's look). Every value is a pure
function of time, colours are palette roles or `#hex`, only accents glow, and every effect works in landscape, vertical
and square. `films/gallery-fx` shows all of it.

## Transitions

A shot comes in from the one before it by `transition`: a kind, or a spec without its pair.

```ts
{ id: 'b', scene: KineticText, length: { bars: 1 }, transition: 'wipe' },
{ id: 'c', scene: Counter, length: { bars: 1 }, transition: { kind: 'iris', center: [1340, 470], edge: 'accent2', pre: 0.3, post: 0.3 } },
```

Every kind takes `pre` / `post` (seconds either side of the cut, default 0.25; 0 for `cut`; each at most 0.5 s and 25%
of its shot), `fromMode` / `toMode` (`'hold'` | `'run'`) and `ease` (`'inOutQuart'`, `'inOutCubic'`, `'outExpo'`). A
bad spec fails at load, naming the pair and the rule.

| kind | what it does | its fields |
|---|---|---|
| `cut` | a hard cut, no window | — |
| `whip` | both pictures race along, motion-blurred | `dir` (required: where the camera travels), `distance` |
| `zoom` | push through A, emerge from B | `center`, `scale` (5), `bFrom` (1.6) |
| `match` | B shows first where A is brightest (a luma key) | `soft` (0.12) |
| `xfade` | a dissolve | — |
| `dip` | A to ink, ink to B | — |
| `wipe` | a soft edge sweeps across, B behind it | `dir` (0: left to right), `soft` (px, 6% of the short side), `edge` |
| `iris` | a circle grows from a point, B inside | `center` (px, frame centre), `soft`, `edge` |
| `slide` | B slides in over A; A recedes as a card (shrinks, dims, drifts, rounds), B's edge shadowing it | `dir` (180: B enters from the right) |
| `spin` | a rotational whip about the centre, both turning and scaling, blurred along the arc | `angle` (90°, sign = way), `scale` (1.3) |
| `flash` | A blows out into an exposure flash, B emerges from it | `color` (`'fg'`, or a role / #hex) |
| `glitch` | slice tears, blocks and an RGB split around a hard switch, seeded by the pair | `amount` (1) |

- `dir` is a unit vector (`[0, -1]`, +y down) or an angle in degrees (0 right, 90 down); a whip takes either.
- `edge: 'accent' | 'accent2' | null`: a thin glowing line on a wipe's edge or an iris's ring. Its core is drawn crisp
  at the frame's own time; its spill and the reveal behind it are motion-blurred.
- Sounds: a whip, slide and spin whoosh (`whoosh_whip`) and a zoom rushes (`whoosh_zoom`) by default; map any kind in
  `sfx.transitions` (`{ glitch: 'glitch_hit', wipe: null }`).

## Looks

A look is a preset of post parameters: on the film (`"look": "cinematic"` in film.json, or `look` in FilmSpec) and on
any shot (`look` on its ShotSpec), with `post` still applied over it.

| look | character |
|---|---|
| `film` | the engine's look (default): bloom, halation, a little fringe, grain and vignette |
| `clean` | crisp product video: less bloom and halation, no fringe, a whisper of grain |
| `cinematic` | 2.39 letterbox, warmer, an S-curve, deeper vignette, a touch less saturated |
| `neon` | wide hot bloom and halation, richer colour, a faint accent wash |
| `dreamy` | wide soft bloom, lifted blacks, a flatter curve, warm |
| `gritty` | hard contrast, heavy grain, cool and desaturated, deep vignette |
| `retro` | scanlines, a strong fringe, warm and faded |

Resolution, last wins: DEFAULT_POST → the film's look → the film's `post` → a shot's look (replacing the film's look
on that shot) → the film's `post` again → the shot's `post` → the scene's returned overrides → each overlay's. Inside a
transition the side the frame is on wins, so a look changes on the cut (`engine/looks.ts`).

The grade parameters (any `post`, all neutral by default, and a neutral grade renders exactly as before):

| param | neutral | meaning |
|---|---|---|
| `saturation` | 1 | 0 grey, above 1 richer (about luma, in light) |
| `contrast` | 1 | an S-curve about mid-grey keeping black and white; above 1 deeper |
| `warmth` | 0 | white balance, −1 cool to 1 warm, luma kept |
| `tint`, `tintColor` | 0, `'accent'` | a soft-light wash of a role over the picture |
| `lift` | 0 | black level raised toward the theme's bg2 hue (0.03-0.1: a faded print) |
| `letterbox` | 0 | the picture's aspect between bars (2.39); bars in bg, at most 13% of the short side each |
| `scanlines` | 0 | 0..1 CRT lines |

Plus the film look's own: `exposure`, `bloom`, `bloomThreshold`, `bloomKnee`, `bloomRadius`, `halation`, `ca`,
`grain`, `vignette`.

```ts
export default defineFilm({ ...config, look: 'cinematic', post: { grain: 0.06 }, scenes: [
  { id: 'hero', scene: TitleCard, length: { bars: 2 }, look: 'neon', post: { letterbox: 0 } },
] });
```

## Beat effects (`@kit/fx`)

`BeatFx` is an overlay: it draws nothing (or a flash frame of a role's light) and returns post overrides on the beat.

```ts
overlays: [{ id: 'hits', scene: BeatFx, start: 8, end: 16, params: {
  punch: true,                                   // zoom kick on every beat
  shake: { on: 'downbeat', amount: 10 },
  flash: { on: 'bar', every: 2, color: 'accent', amount: 0.2 },
  pump: { amount: -0.1 },                        // duck the exposure on the beat
  bars: { aspect: 2.39, in: { beat: 1 }, out: { bar: 3 } },
} }],
```

| param | defaults | |
|---|---|---|
| `punch` | `on 'beat'`, `amount 0.035` | zoom: the house spring's kick (5 Hz, damping 0.6) landing on the hit; never below 1 |
| `shake` | `on 'downbeat'`, `amount 14` (ref px), `decay 0.25`, `freq 22`, `seed 1` | seeded noise, with the zoom that hides the frame's edges |
| `flash` | `on 'downbeat'`, `amount 0.3`, `decay 0.16`, `color 'fg'` | `'fg'`: the post flash; any other role: a frame of its light |
| `pump` | `on 'beat'`, `amount 0.12`, `decay 0.25` | exposure 1 + amount at the hit (negative ducks) |
| `bars` | `aspect 2.39`, `in 0`, `out` | letterbox bars springing in and out |
| `from`, `to` | the overlay's window | where hits may fall |

Each effect is off when absent, `true` for its defaults, or an object. `on`: `'beat'`, `'downbeat'` (= `'bar'`),
`'backbeat'` (beats 2 and 4) or a list of TimeRefs (s from the overlay's start, `{ beat }`, `{ bar }`); `every`: every
n-th hit. While an effect is on, BeatFx owns that post key; between hits the shot's own value holds.

The helpers are pure and exported for custom scenes:

```ts
import { punch, shake, flash, pump, bars } from '@kit/fx';
render(f, out) {
  // ...draw...
  return { zoom: punch(f, { on: 'beat', grid: this.ctx.audio }), shake: shake(f, { on: [1.2, 3.4] }) };
}
```
