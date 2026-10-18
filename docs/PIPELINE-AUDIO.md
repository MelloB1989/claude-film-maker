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

## Timeless v3 mix (task v3-mix, agent-03, 2026-10-18)

    PYTHONPATH=tools python -m filmtools.amv3.mix3 --stems           # -> $AMV3_DATA/mix.wav, cues3.csv, mix3_report.json
    PYTHONPATH=tools python -m filmtools.amv3.audit_mix3 --json $AMV3_DATA/mix3_audit.json --png $AMV3_DATA/mix3_audit.png
    PYTHONPATH=tools python -m filmtools.amv3.listen3 --full          # v2 picture + v3 mix, frame numbers burnt in

- Needs numpy, scipy, soundfile, matplotlib, Pillow, imageio-ffmpeg (Python 3.10+). The render VM has no soundfile:
  build locally (about 4 min on the container) and copy the wav to the VM.
- v2's song, voice, ducking and master chain are reused from `filmtools.amv2.mix`, unchanged. Each CUTS entry gets a
  layered design synthesized by `filmtools.amv3.sfx3`, with no third-party samples (see `films/timeless/amv3/SFX-CREDITS.md`).
- Levels are calibrated per transition (`mix3.calibrate`). Each transition's own layers lift the 3-12 kHz band at the
  cut by `LIFT[type]` dB over the song; the references measure +4-8 dB (`filmtools.amv3.analysis.ref_audio`). Three caps:
  the layers stay `UNDER` (2 dB) below the music across the window, add at most `PUMP` (1 dB) of master-limiter gain
  reduction, and the trim stays in [-12, +18] dB. Impact layers (thump, impact, slap, thunder, metal slam, debris)
  keep fixed gains, set to sit with the song's kick.
- Pitfalls: Python's `hash()` of a string is randomized per process, so seed with `zlib.crc32` or the SFX change
  on every run. The imageio-ffmpeg static build has no `drawtext`: burn labels with PIL. When piping a range out of an
  ffmpeg decoder, do not `wait()` on it after reading N frames; close its stdout and terminate it (it can block on a
  full pipe forever).
