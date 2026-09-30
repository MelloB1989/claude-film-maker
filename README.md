# GitLoom launch film

*I Don't Forget. I Commit.* is a 90-second, code-rendered launch film for GitLoom.

- Design: `docs/specs/2026-09-30-gitloom-launch-film-design.md`
- Plans: `docs/plans/`

## Stages

| stage | command (from `tools/`) | writes |
|---|---|---|
| voice takes | `uv run film-vo` | `audio/vo/takes/` |
| pacing | `uv run film-pace` | `audio/vo/paced/` |
| listening pages | `uv run film-audition vo` / `music` | `out/auditions/*.html` |
| placement | `uv run film-edit` | `data/vo.json`, `audio/vo/vo.wav` |
| score | `uv run film-music` | `audio/music/`, `data/music_plan.json` |
| beat grid | `uv run film-beats --music <wav>` | `data/audio.json` |
| snapping | `uv run film-snap` | `data/vo.json`, `audio/vo/vo.wav` |
| mix | `uv run film-mix --music <wav>` | `audio/mix/mix.wav` |
| fonts | `uv run film-fonts` | `app/public/fonts/` |
| sync report | `uv run film-sync` | stdout, exit 1 on failure |

The engine lives in `app/` (`bun install`, `bunx vite`, `bun scripts/render.ts …`).

The ElevenLabs key is read from `~/11labs` at runtime and never stored in this repo.
