# GitLoom launch film

*I Don't Forget. I Commit.* is a 90-second, code-rendered launch film for GitLoom.

- Design: `docs/specs/2026-09-30-gitloom-launch-film-design.md`
- Plans: `docs/plans/`

## Stages

| stage | command (from `tools/`) | writes |
|---|---|---|
| voice takes | `uv run film-vo` | `audio/vo/takes/` |
| word timing | `uv run film-realign` (forced alignment, 1 credit a take) | `audio/vo/takes/*.json` |
| pacing | `uv run film-pace` | `audio/vo/paced/` (with each word's measured `onset`) |
| listening pages | `uv run film-audition vo` / `music` | `out/auditions/*.html` |
| placement | `uv run film-edit` | `data/vo.json`, `audio/vo/vo.wav` |
| score | `uv run film-music` | `audio/music/`, `data/music_plan.json` (merged, never replaced) |
| score cut to picture | `uv run film-splice --map <bars>` | `audio/music/*-edit.wav`, `data/music_plan.json` |
| snapping | `uv run film-snap` | `data/vo.json`, `audio/vo/vo.wav` |
| beat grid | `uv run film-beats` | `data/audio.json` |
| mix | `uv run film-mix` | `audio/mix/mix.wav` |
| fonts | `uv run film-fonts` | `app/public/fonts/` |
| sync report | `uv run film-sync` | stdout, exit 1 on failure |

After any change to pacing or placement (a take swap in `audio/vo/selects.json`, a gap in `data/edit.json`), re-run
the chain in this order, so `data/audio.json`'s vocal data describes the snapped voiceover and the mix plays it:

```
uv run film-pace && uv run film-edit && uv run film-snap && uv run film-beats && uv run film-mix && uv run film-sync
```

`film-beats` and `film-mix` read the chosen score from `data/music_plan.json`. If you pass `--music`, it must name the
spliced `audio/music/score-seed11-edit.wav`, never the raw seed: the raw seed's bars are in another order, so the grid
and the mix would not match the picture. `film-splice` only ever cuts the raw seed (its `edit.source`), on the
downbeats stored at the first splice.

`film-sync` fails on any timing problem except those ruled in `data/sync_waivers.json` (`{"cut <scene>": "<ruling>"}`),
which it prints as `waived:`.

The engine lives in `app/` (`bun install`, `bunx vite`, `bun scripts/render.ts …`).

The ElevenLabs key is read from `~/11labs` at runtime and never stored in this repo.
