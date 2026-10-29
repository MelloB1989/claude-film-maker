# film-tools

The audio, timing and delivery pipeline for films made with the engine: voiceover takes, forced alignment, pacing,
placement, a generated or procedural score cut to picture, a beat grid for the engine, sound effects, the voice chain,
a mastered mix with stems, a timing contract, a facts gate for on-screen text, and segmented delivery. Python 3.12,
run with [uv](https://docs.astral.sh/uv/) from `tools/`:

```
cd tools && uv sync
uv run film-temptrack --film showcase --mix      # any tool: uv run film-<name> [--film <id>] ...
uv run pytest -q                                 # the tests make their own films; no network, no keys
```

Every tool works on one film, `films/<id>/` ([docs/CONVENTIONS.md](../docs/CONVENTIONS.md)): `--film <id>` anywhere
on the command line, else `$FILM`, else `showcase`. A film that does not exist is an error that lists `films/*`.
Inputs and outputs live in the film folder (`data/`, `audio/`); renders, auditions and reviews in `out/<id>/`. Paths
the tools record (`data/music_plan.json`) are relative to the film folder. Scene windows come from
`data/timeline.json` (`cd app && bun scripts/timeline.ts --film <id>`), else from `data/vo.json`.

ElevenLabs (voice, music, sound effects, forced alignment) is the only paid service. The key comes from
`$ELEVENLABS_API_KEY`, else from the key file (`pipeline.voice.key_file`, default `~/11labs`); it is never written
anywhere. Credits spent are logged to `audio/credits.log`. Only `film-vo`, `film-realign`, `film-music` and
`film-sfx-lib` call the API; `film-temptrack` makes a score without it.

## The tools

| tool | reads | writes |
|---|---|---|
| `film-init <id> [--title --format --fps --theme --bpm --force]` | | `films/<id>/film.json`, `data/script.json` stub, `.gitignore`; never `film.ts` |
| `film-vo [--only L01,L02] [--takes N] [--speed S]` | `data/script.json`, `pipeline.voice` | `audio/vo/takes/<line>/<k>.{wav,json}` (skips takes already there) |
| `film-realign [--only ...]` | the takes | the takes' word times, measured by forced alignment (1 credit a take) |
| `film-pace [--only ...] [--factor F \| --target-wps W]` | the takes, `audio/vo/selects.json`, `pipeline.voice.pace` | `audio/vo/paced/` (trimmed, time-stretched with Rubber Band when the factor is not 1, each word's spoken `onset`) |
| `film-audition vo \| music [--no-open]` | paced takes, or `audio/music/*.wav` | `out/<id>/auditions/{vo,music}.html` |
| `film-edit` | script, paced takes, selects, `data/edit.json` (optional) | `data/vo.json`, `audio/vo/vo.wav` |
| `film-music [--variants N] [--seed-base S] [--bpm B]` | scene windows, `pipeline.music` | `audio/music/<label>-seed<N>.wav` + `.plan.json`, `data/music_plan.json` (merged, never replaced) |
| `film-temptrack [--bpm --bars \| --duration --beats-per-bar --offset --seed --style --phrase --out --mix --choose]` | `pipeline.music.temp`, `audio.bpm`, scene windows | `audio/music/temp.wav` + `.plan.json`, `data/audio.json`, the pick in `data/music_plan.json` |
| `film-splice --map 0-7,12-15,8-11` | `data/music_plan.json`, `data/audio.json` | `audio/music/<source>-edit.wav`, the edit in `music_plan.json` |
| `film-snap` | `data/vo.json`, `data/audio.json`, script | `data/vo.json`, `audio/vo/vo.wav` (lines on beats, cuts on beats) |
| `film-beats [--music F --bpm B] [--no-automation]` | the chosen score, `data/vo.json`, `audio/vo/vo.wav` | `data/audio.json` (grid, sections, envelopes, onsets) |
| `film-vo-chain` | `audio/vo/vo.wav`, `data/vo.json`, `pipeline.voice.chain` | `audio/vo/vo-chain.wav`, `out/<id>/review/vo-chain.json` |
| `film-sfx-lib probe \| plan \| gen --budget N \| sheet \| backup \| reprocess` | the palette (`pipeline.sfx.palette`) | `audio/sfx/lib/`, `audio/sfx/manifest.json`, `out/<id>/review/sfx/` |
| `film-sfx [--sheet F] [--out F]` | `data/sfx.json` (`cd app && bun scripts/cues.ts --film <id>`), the manifest | `audio/sfx/sfx.wav` |
| `film-mix [--music F] [--no-automation] [--no-sfx] [--no-vo]` | `vo-chain.wav`, the chosen score, `sfx.wav`, `data/audio.json`, `pipeline.mix` | `audio/mix/{mix,vo,music,sfx}.wav`, `out/<id>/review/mix.{json,png}` |
| `film-sync [--words]` | `data/vo.json`, `data/audio.json`, scene windows, `audio/vo/vo.wav`, paced takes | a report; exit 1 on a problem not waived in `data/sync_waivers.json` |
| `film-facts [--scenes DIR]` | `films/<id>/scenes/**/*.strings.json`, `data/facts.json`, vo, script, timeline | a report; exit 1 on a string not on the sheet |
| `film-fonts [--src F --axis wght=600 --out F]` | `pipeline.fonts` | `films/<id>/fonts/` (static instances for opentype.js) |
| `film-deliver segments \| render \| assemble \| check [--segments N] [--scale S] [--mix F]` | scene windows, `pipeline.deliver`, the mix | `out/<id>/deliver/` (segments, `video.mp4`, stems), `out/<id>/<id>-<output>.mp4` |
| `film-anime-fetch --name N --url U [--job --model --prompt --refs --credits --force] \| --list` | a generation's result URL | `assets/gen/<name>.<ext>`, its provenance in `data/gen.json` |
| `film-anime-clips --src F \| --all [--name --from --to --crop --sharpen]` | `assets/gen/clip-*.mp4` | `assets/clips/<name>.mp4` (the film's size and fps) |
| `film-anime-cutout --src F [--out D] [--parts boxes] [--boxes --keep-largest --grow --feather --fill]` | a keyframe | `<out>/fg.png`, `plate.png`, `matte.png` (and `part<N>.png` per `--parts` box) |
| `film-anime-depth --src F [--out F] [--smooth px]` | a plate | its depth map, 16-bit, near = white |
| `film-anime-dialogue takes [--lines --n --force] \| check \| place [--hold] \| list` | `data/dialogue.json`, `data/timeline.json` | `audio/dialogue/takes/`, `audio/dialogue/dialogue.wav`, `data/subs.json`, `data/dialogue_timing.json` |
| `film-anime-score gen [--cues --seed --force] \| list` | `data/score.json` | `audio/score/<cue>.{wav,json}` |
| `film-anime-mix [--png F]` | `data/mix.json`, the dialogue, the score's cues, the sound library, `data/timeline.json` | `audio/mix/mix.wav`, its stems and `mix.json` |

`data/script.json` is `{"lines": [{"id", "scene", "text", "takes"?, "optional"?}], "acts"?: [{"id", "name",
"scenes"}]}`; without acts the scenes form one act in the order the lines name them. `audio/vo/selects.json` is
`{"<line>": {"take": k, "factor": f}}` (checkpoint C1). `data/edit.json` overrides the placement defaults:
`{"lead_in": 0.5, "tail": 1.5, "gap": {"line": 0.35, "scene": 0.8, "act": 1.4}, "scene_lead": 0.3, "overrides":
{"L04": {"gap_before": 2.0}}, "optional": {"L03b": true}}`. The chosen score is `data/music_plan.json`'s `chosen`
(checkpoint C2; `film-splice` points it at the edit), else `pipeline.music.chosen`.

## The chain

With a voiceover, in this order (each step reads what the ones before wrote):

```
film-init <id>                                   once; then copy films/starter/film.ts and write the script
film-vo → film-realign → film-pace → film-audition vo     pick takes in audio/vo/selects.json (C1)
film-edit                                        data/vo.json, audio/vo/vo.wav
film-music → film-audition music   (or)   film-temptrack  pick the score (C2)
film-splice --map ...                            optional: re-order the score's bars to the picture
film-snap → film-beats                           lines and cuts on the beat; the grid for the engine
film-vo-chain
film-sfx-lib gen --budget N → (cd app && bun scripts/cues.ts --film <id>) → film-sfx
film-mix → film-sync → film-deliver render → film-deliver assemble
```

After any change to pacing or placement re-run `film-pace`, `film-edit`, `film-snap`, `film-beats`, `film-mix`,
`film-sync`, so `data/audio.json` describes the snapped voice and the mix plays it. A film without a voice can go
straight from `film-temptrack` (or `film-music`) to the engine: `film-temptrack --mix` writes the beat grid and a
mastered `audio/mix/mix.wav`; `film-mix --no-vo` mixes the score with effects.

`film-temptrack` is a procedural temp score, numpy-synthesised and deterministic for a seed: `pulse` (four-on-the-floor
kick, claps, hats, a ducking sub, a saw pad on a minor progression, risers out of quiet sections) or `cinematic`
(sparse low hits on downbeats, ticks, a sub drone, the pad, risers landing on section downbeats). Sections are
`--phrase` bars; the length is the film's (`data/timeline.json`, else `data/vo.json`) unless `--bars` or `--duration`
say otherwise. The grid it writes is exact, and `film-beats` keeps it (through splices too) instead of tracking it.

## `pipeline` in film.json

All optional; what is left out takes the default below. An unknown key is an error. Paths are relative to the film
folder. `audio.bpm`, `audio.beatsPerBar`, `audio.offset`, `audio.mix`, `audio.analysis`, `fps`, `format` and
`theme` are read from the top of film.json.

```jsonc
"pipeline": {
  "voice": {
    "provider": "elevenlabs",
    "name": "Narrator",                    // how pages and reports name the voice (default "voice")
    "voice_id": "…",                       // required by film-vo
    "model": "eleven_multilingual_v2",
    "output_format": "pcm_48000",          // the pipeline runs at 48 kHz
    "speed": 1.0,
    "settings": { "stability": 0.4 },      // more voice_settings for each request
    "seed": null,
    "key_file": "~/11labs",                // $ELEVENLABS_API_KEY wins; used by every ElevenLabs tool
    "pace": { "factor": 1.0, "min": 0.85, "max": 1.0, "target_wps": null },
    "chain": { "deess": { "thresh_db": -38 } }   // overrides of the voice chain's stages (vochain.CHAIN)
  },
  "music": {
    "provider": "elevenlabs",
    "model": "music_v2_5",
    "bpm": null,                           // else audio.bpm, else 120
    "seed_base": 1, "variants": 3,
    "label": "score",                      // audio/music/<label>-seed<N>.wav
    "styles": ["instrumental"],            // global styles; "<bpm> BPM" is added
    "avoid": ["vocals"],
    "sections": [                          // without sections: one section over the film
      { "name": "intro", "scene": "open", "styles": ["very quiet", "a low drone"], "avoid": ["drums"],
        "adherence": "high", "gain_db": -10, "cutoff_hz": 300 },
      { "name": "build", "scene": "problem", "gain_db": [-10, -3], "cutoff_hz": [300, 4000] },
      { "name": "chorus", "scene": "turn", "styles": ["full groove"], "glide": 0.005 },
      { "name": "drop", "at": 61.2, "gain_db": -12, "glide": 0.12 }
    ],
    "fade_out": 2.0,                       // the mix fades the score out over its last seconds
    "chosen": null,                        // the score when data/music_plan.json chooses none
    "temp": { "style": "pulse", "seed": 1, "phrase": 8 }
  },
  "mix": {
    "lufs": -14.0, "true_peak": -1.0, "limit_dbfs": -2.0,
    "music_gain_db": -4.0, "sfx_gain_db": 0.0,
    "music_duck": { "thresh_db": -26, "ratio": 4, "attack_ms": 20, "release_ms": 350, "knee_db": 9,
                    "range_db": 9, "hold_ms": 250 },
    "sfx_duck": { "thresh_db": -24, "ratio": 2, "attack_ms": 20, "release_ms": 350, "knee_db": 9,
                  "range_db": 4, "hold_ms": 0 },
    "duck_target_db": [6.0, 9.0]           // the music's median duck under the voice film-mix accepts
  },
  "sfx": { "palette": "data/sfx_palette.json", "backup": null },   // backup: a folder every paid take is copied to
  "sync": { "duration": [85, 95] },        // the film's length in seconds; null: no check
  "deliver": {
    "segments": 4, "scale": 1, "samples": "auto",
    "pad": null,                           // letterbox colour; null: the theme's bg
    "outputs": {                           // replaces the default {rough: copy, master: crf 16} whole
      "master": { "crf": 16 },
      "16x9": { "size": [1920, 1080], "maxrate": "12M", "audio_kbps": 256 },
      "9x16": { "size": [1080, 1920], "fit": "crop" },
      "4x5":  { "size": [1080, 1350], "fit": "pad" },
      "1x1":  { "size": [1080, 1080] }
    },
    "hits": [{ "sound": "door_slam", "frame": 161 }]   // cues whose hit must land on picture in every output
  },
  "fonts": [{ "src": "fonts/src/Inter[opsz,wght].ttf", "axes": { "wght": 600 }, "out": "Inter-600.ttf" }]
}
```

A section opens on the bar line at or before its `scene`'s cut (or at `at` seconds); the first starts at 0. Its
`gain_db` / `cutoff_hz` (a value, or `[start, end]` across the section) and `glide` (seconds to move from the previous
section's values) draw the score's arc in the mix and in the engine's envelopes; with sections configured, a section
the score has but the config does not name is an error. An output is `{size (default: the film's size × scale), fit:
pad | crop, codec: libx264 | copy, crf (17), preset (slow), maxrate, bufsize, profile (high), audio_kbps (320)}` and
lands at `out/<id>/<id>-<name>.mp4`; `film-deliver check` verifies frames, rate, size, BT.709 tags, lengths from 0,
48 kHz stereo audio at `mix.lufs` under `mix.true_peak`, and each configured hit. A font's `src` is looked for in the
film folder, then at the repo root; OS/2 weight and width classes follow its `wght` and `wdth` axes.

## Requirements

`ffmpeg`/`ffprobe` (mix, decode, delivery), `rubberband` only for a pacing factor other than 1, `bun` and the engine
for `film-deliver render`. The pipeline runs at 48 kHz; takes are 24-bit WAV, stems 32-bit float.
