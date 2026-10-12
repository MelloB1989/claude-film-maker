# Conventions (engine ⇄ pipeline contract)

The repo is a reusable film engine. A *film* is a folder under `films/<id>/`; the engine (`app/`), the audio pipeline
(`tools/`) and the Blender plate pipeline (`blender/`) all work on one film at a time. Nothing in `app/src/engine`,
`app/src/kit`, `tools/` or `blender/lib` may name a particular film, product, voice or palette.

## Picking the film

Every entry point takes the film the same way, first match wins:

1. an explicit option: `--film <id>` (CLI tools, `render.ts`, Blender's `render.py`), `?film=<id>` (the player URL);
2. the `FILM` environment variable;
3. the default film id, `showcase`.

## Layout

```
films/<id>/
  film.json          shared config: read by the engine, the Python tools and Blender (schema below)
  film.ts            the timeline (TypeScript, engine only): defineFilm({...}) with scenes, transitions, overlays
  scenes/*.ts        the film's own scene modules (kit scenes need none)
  sfx/*.ts           optional SFX cue sheets (app/scripts/cues.ts → data/sfx.json)
  fonts/             optional extra fonts the film registers
  assets/            images, videos, SVG logos the scenes load (served at /films/<id>/assets/...)
  blender/shots/*.py optional Blender shots (blender/render.py --film <id> --shot <name>)
  data/              script.json, edit.json, vo.json, audio.json, music_plan.json, sfx.json, sfx_palette.json,
                     facts.json, timeline.json, track/<shot>.json, look/<shot>.json  (each optional)
  audio/             vo/ (takes, paced, selects.json, vo.wav), music/, sfx/ (lib, manifest.json), mix/mix.wav
out/<id>/            everything rendered (gitignored): renders, stills, sheets, auditions, review, plates/<shot>/
```

Paths inside `film.json` are relative to the film folder.

## film.json

```jsonc
{
  "id": "showcase",                 // must equal the folder name
  "title": "Showcase",
  "format": "landscape",            // preset: landscape 1920x1080 | vertical 1080x1920 | square 1080x1080 |
                                    // portrait 1080x1350 | cinema 1920x804 — or { "width": W, "height": H } (logical px)
  "fps": 30,
  "theme": "noir",                  // a preset in app/src/engine/themes.json, or { "extends": "noir", "accent": "#..." }
  "audio": {                        // all optional: a film may be silent
    "mix": "audio/mix/mix.wav",     // what the player plays and render.ts muxes
    "analysis": "data/audio.json",  // beat grid + features (film-beats); without it the grid is synthesised:
    "bpm": 120, "offset": 0, "beatsPerBar": 4
  },
  "vo": "data/vo.json",             // optional word-timed voiceover (film-edit / film-snap)
  "pipeline": { ... }               // Python tools only: voice, music, sfx, mix, deliver settings (tools/README.md)
}
```

## Timeline export

The engine resolves `film.ts` into scene windows and writes them for the other pipelines:
`films/<id>/data/timeline.json` = `{ "fps": 30, "duration": 30.0, "scenes": [{ "id": "open", "start": 0, "end": 4.2 }] }`
(`cd app && bun scripts/timeline.ts --film <id>`). Blender and the Python tools read scene windows from it, falling back
to `data/vo.json`'s `scenes` when it is missing.

## Palette roles

Themes name colours by role, never by hue. The engine's GLSL constants are `C_<ROLE>` in SCREAMING_SNAKE
(`C_BG`, `C_FG_DIM`, `C_ACCENT2_BRIGHT`, …).

| role | use | (the original GitLoom name) |
|---|---|---|
| `bg`, `bg2` | background, its lifted shade | ink, ink2 |
| `surface`, `surface2` | panels, cards | panel, panel2 |
| `rule`, `ruleStrong` | hairlines, borders | rule, ruleStrong |
| `fg`, `fgDim`, `fgFaint` | type and marks at three strengths | bone, boneDim, boneFaint |
| `accent`, `accentBright`, `accentDim` | the primary accent (also `−`, removal) | blood, bloodBright, bloodDim |
| `accent2`, `accent2Bright`, `accent2Dim` | the secondary accent (also `+`, addition) | moss, —, mossDim |

Only the accents glow (look.ts `glow('accent' | 'accent2' | ...)`); `fg` never blooms.

## Output

`out/<id>/` holds renders (`<id>.mp4`), `stills/`, `sheets/`, `auditions/`, `review/`, `plates/<shot>/####.exr` and
`plates/<shot>/proxy/####.png`. Tracks go to `films/<id>/data/track/<shot>.json` (committed, small).
