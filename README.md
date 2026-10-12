# claude-film-maker

A film engine for code-rendered launch films, product reels and social cuts. Every frame is a pure function of time,
rendered by three.js and GLSL in the browser: kinetic type that lands on the beat and on the voice, extruded 3D type,
floating UI panels in a studio with depth of field, data blocks, animated backgrounds, transitions, film looks
(bloom, halation, grain, grades), true motion blur, and a Python audio pipeline that makes the voice, the score, the
sound design and the final mix.

It began as the engine behind the GitLoom launch film (kept on the `gitloom-film` branch) and is now generic: a
film is a folder, `films/<id>/`, and nothing in the engine, the kits or the pipelines names a film.

## Quick start

```bash
cd app && bun install
bunx vite                                   # the player: http://localhost:5173/?film=showcase
bun scripts/new.ts my-film --theme ember --format vertical --bpm 118
bun scripts/render.ts stills --film my-film --t 1,2.5,4
bun scripts/render.ts video  --film my-film --samples auto     # → out/my-film/my-film.mp4
```

Player keys: space play/pause, ←/→ 1 s (shift 5 s), `,`/`.` one frame, `[`/`]` previous/next shot, `l` loop,
`g` safe-area guides, `p` save the frame as PNG, `h` hide the UI.

## A film

```ts
// films/my-film/film.ts
import { defineFilm } from '@engine/film';
import { TitleCard, KineticText, EndCard } from '@kit/text';
import { Counter } from '@kit/data';
import { Captions } from '@kit/overlays';
import config from './film.json';   // { id, title, format, fps, theme, audio: { bpm } }

export default defineFilm({
  ...config,
  vo: [{ text: 'Ship your story in ninety seconds.', start: 2.4, end: 4.6 }],
  scenes: [
    { id: 'open', scene: TitleCard, length: { bars: 2 }, params: { kicker: 'v2', title: 'Written in code.' } },
    { id: 'line', scene: KineticText, length: { bars: 2 }, transition: { kind: 'whip', dir: [1, 0] },
      params: { sync: 'vo', text: 'Ship your story\nin ninety seconds.', emphasis: ['ninety'] } },
    { id: 'stat', scene: Counter, length: { bars: 2 }, transition: 'xfade', params: { value: 91.4, suffix: '%', land: { beat: 4 } } },
    { id: 'end', scene: EndCard, length: { bars: 3 }, transition: { kind: 'zoom', scale: 3 }, params: { name: 'Acme', cta: 'Start free' } },
  ],
  overlays: [{ id: 'caps', scene: Captions, params: { style: 'karaoke' } }],
});
```

Shots play back to back for a length in seconds, beats or bars of the film's grid (the analysed score's, or a
synthetic grid at `audio.bpm`). Each comes in from the one before by a transition. Overlays play over them, and the
film's look applies to every frame. Every kit block is configured by `params` alone; a film's own scenes go in
`films/<id>/scenes/` (see `films/starter/` and `films/gallery-type/scenes/pulse.ts`).

`film.json` sets the format (`landscape`, `vertical`, `square`, `portrait`, `cinema` or `{ width, height }`), fps, the
theme (`noir`, `midnight`, `ember`, `aurora`, `mono`, `paper`, or a preset with colours overridden), the audio and the
pipeline settings. Colours are roles (`bg`, `fg`, `accent`, `accent2`, …), never hues, so one film re-themes in a line.

## The kits

| kit | import | blocks |
|---|---|---|
| type | `@kit/text` | KineticText (9 reveals, synced to stagger, beats or the voice), TitleCard, EndCard, Quote, LowerThird, Heading, BulletList, FeatureList, Marquee |
| data | `@kit/data` | Counter (odometer, split-flap or count-up), BarChart, LineChart, StatGrid, Compare, Figure |
| overlays | `@kit/overlays` | Captions (karaoke, line, pop), Watermark, ProgressBar, SafeArea |

Reference: [docs/KIT.md](docs/KIT.md). Example films: `films/gallery-type`, `films/gallery-type-vertical`.

## Sound

`tools/` (Python, `uv run film-<tool> --film <id>`) makes and mixes the sound: ElevenLabs voice takes, forced
alignment and pacing, a generated score or a free procedural temp track (`film-temptrack --mix`), cuts and lines
snapped to the beat, a beat grid the engine animates to, a sound-effects library rendered from the engine's cue sheet,
a voice chain, and a mastered mix with stems. See [tools/README.md](tools/README.md) and
[docs/PIPELINE-AUDIO.md](docs/PIPELINE-AUDIO.md).

```bash
cd tools && uv sync
uv run film-temptrack --film my-film --mix       # a score, the beat grid and the mix, no paid audio
```

## Rendering

`app/scripts/render.ts` drives the player in headless Chromium: `stills`, `sheet` (a contact sheet; `--cuts`,
`--transition <from>-<to>`), `video` (H.264, or `--prores`; `--samples auto` for adaptive motion blur; `--scale 2` for
4K) and `perf`. `tools/` `film-deliver` renders long films in resumable segments and encodes the named outputs.
Hero shots can be rendered in Blender as plates the engine composites: [docs/PIPELINE-BLENDER.md](docs/PIPELINE-BLENDER.md).

## Layout

```
app/          the engine (src/engine), the kits (src/kit), the player (src/main.ts), scripts (render, new, timeline, cues)
films/<id>/   film.json, film.ts, scenes/, assets/, data/, audio/   (docs/CONVENTIONS.md)
tools/        the audio, timing and delivery pipeline (Python)
blender/      the Blender plate pipeline
docs/         conventions, kit reference, pipelines, credits
out/<id>/     renders, stills, sheets, reviews (gitignored)
```

## Tests

```bash
cd app && bun test src && bun run typecheck
cd tools && uv run pytest -q
```

Credits and licences: [docs/CREDITS.md](docs/CREDITS.md).
