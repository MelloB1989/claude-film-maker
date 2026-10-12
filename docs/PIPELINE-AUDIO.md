# The audio pipeline

`tools/` is a Python package (`filmtools`, run with `uv run film-<name>` from `tools/`) that makes a film's sound and
delivers it. It works on one film at a time, like the engine and Blender ([CONVENTIONS.md](CONVENTIONS.md)):
`--film <id>`, else `$FILM`, else `showcase`; it reads and writes `films/<id>/data/` and `films/<id>/audio/`, and puts
renders and reviews in `out/<id>/`. Its settings are the `pipeline` section of `films/<id>/film.json`.

What it does, in order:

1. **Voice**: ElevenLabs takes of `data/script.json` (`film-vo`), re-timed by forced alignment (`film-realign`),
   trimmed and paced with each word's spoken onset measured (`film-pace`), auditioned (`film-audition vo`) and placed
   on the timeline with scene windows derived (`film-edit` → `data/vo.json`, `audio/vo/vo.wav`).
2. **Score**: ElevenLabs Music from a section plan keyed to the scenes (`film-music`), or a procedural temp score on
   an exact grid with no paid audio (`film-temptrack`); cut to picture bar by bar (`film-splice`).
3. **Sync**: lines nudged onto beats and cuts onto beats and downbeats (`film-snap`); the beat grid, sections,
   envelopes and onsets the engine animates to (`film-beats` → `data/audio.json`).
4. **Effects**: a cached, budgeted ElevenLabs sound library (`film-sfx-lib`) rendered from the engine's cue sheet
   (`data/sfx.json`, `bun scripts/cues.ts`) into a stem (`film-sfx`).
5. **Mix**: the voice chain (`film-vo-chain`), then the voice over the score's drawn arc and the effects, with
   sidechain ducks, mastered to the film's target (default −14 LUFS, −1 dBTP) with stems (`film-mix` → `audio/mix/mix.wav`, which the player
   plays and `render.ts` muxes).
6. **Checks**: the timing contract (`film-sync`) and the on-screen facts gate (`film-facts`).
7. **Delivery**: segmented, resumable renders through `app/scripts/render.ts`, assembled with the mix and encoded to
   the named outputs (`film-deliver`).

Scene windows come from the engine's `data/timeline.json` (`bun scripts/timeline.ts --film <id>`), else from
`data/vo.json`. `film-init <id>` scaffolds the film's `film.json` and script stub; the timeline itself (`film.ts`,
scenes) is the engine's.

Every tool, the `pipeline` schema with an example, and the recommended chain are in
[tools/README.md](../tools/README.md).
