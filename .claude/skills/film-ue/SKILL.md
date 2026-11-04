---
name: film-ue
description: Drive Unreal Engine 5.8 with no UI through film-ue and the filmtools.unreal SDK — MetaHumans, sets, lights, cameras, Sequencer, renders, QA. Use for any task in claude-film-maker that touches Unreal (unreal/, tools/filmtools/unreal/, docs/unreal/, examples/unreal/, a film's Unreal scene), for writing or reviewing bridge ops, spec kinds or selftests, and for running the demo or selftests on a GPU box.
---

# film-ue: Unreal by code

You cannot see the editor. Every change is declared or called through `film-ue` (run from `tools/`: `uv run film-ue`),
and every result is checked with numbers and pictures you pull back. Read `docs/unreal/GUIDE.md` once per session;
`docs/unreal/dx.md` is the tool reference; `docs/unreal/CONVENTIONS.md` is binding for code.

## The loop (every task)

1. Health: on a new box `film-ue --box NAME first-run [--epic]` (resumable checklist, prints the next command on a
   failure); otherwise `film-ue doctor`, `film-ue op ops.broken` (must be `{}`).
2. Look: `film-ue describe --live level`, `film-ue <area> describe ... --json`.
3. Find ops OFFLINE: `film-ue describe` -> `film-ue describe <area>` -> `film-ue describe <area.verb>`.
4. Prefer a spec when a kind exists (`film-ue plan --kinds`): `film-ue plan X.yaml`, then `film-ue apply X.yaml --json`;
   require `"converged": true`. Otherwise call ops: `film-ue <area> <verb> --flag v --json` (`--dry-run` first when
   unsure; `--async` + `film-ue job ID --wait` for long ones).
5. Verify with numbers (`qa.*`, the area's `describe`) AND a picture: `film-ue view stills --sequence S --out-dir D`
   then `film-ue pull D/sheet.png /tmp/sheet.png` and Read it.

## Calling conventions

- Flags are argument names with `-`; lists `0,0,300` or JSON; dicts `yaw=90,pitch=-10` or JSON; `@file.json`.
- Units: cm, degrees as `{pitch, yaw, roll}` (never positional), frames at the sequence rate; unit suffixes in names
  (`focal_mm`, `duration_s`). Actors by label, assets by `/Game/...` package path.
- `--json` always when you read the answer. Exit 2 = bad call caught offline (use `error.candidates`); 1 = the op
  failed (do what `error.hint` says); 3 = no bridge (`film-ue status`, `film-ue editor status`).
- Python: `from filmtools.unreal.sdk import Unreal, OpError; ue = Unreal(); ue.level.spawn(label=..., shape="cube")`.

## Specs

One document per thing: `kind`, `version: 1`, `name`, fields; `---` between; `kind: vars` (`${name}`), `kind:
include`; `order: N` to stage; `kind: op` with `unless: {op, args, has}` for steps with no kind. Unknown fields are
errors with "did you mean". Plan offline with `--state state.json`. Example of everything:
`examples/unreal/demo/` (README.md: stage by stage, with expected output).

## Writing code here

- Ops: `unreal/fmbridge/ops/<area>.py`, `@op("area.verb", mutates=, idempotent=, tags=)`, keyword-only args with units,
  docstring with `Args:` and one `Example:` line, raise `fmbridge.errors.OpError(msg, code=, hint=, candidates=)`,
  return `changed`. Python 3.11 in `unreal/`. Long work = generator (`yield`). Verify every engine API on the UE
  source box (rg) and record it in your area doc's API_NOTES.
- After any op change: `film-ue dx gen` (schema snapshot + SDK), `film-ue dx check`, `film-ue dx lint`.
- A spec kind: `register_kind(name, plan, describe, order=)` in your module, pure `plan(spec, state) -> [{"op",
  "args", "why"}]`, schema in `tools/filmtools/unreal/schemas/<kind>.schema.json` (dx.md §4).
- A selftest: `unreal/fmbridge/selftest/<area>.py` with `def run(t)` (dx.md §5), docstring says `Takes ~N` and
  `Needs: ...`; run `film-ue selftest <area>` on a box.
- Tests: `tools/tests/test_ue_<area>*.py` on the fake engine (`ue`/`fmb` fixtures, `run_op`, `drive`); run all ue tests
  (`tests/test_ue_*.py tests/test_unreal_*.py tests/test_fmbridge_jobs.py`) before you push.

## Traps

No modal dialogs ever (free paths before creating). Multi-tick ops must be `yield from`-ed. A face played by
Sequencer stops following the body (`anim.bake_follow`). Hair goes white indoors (`r.HairStrands.SkyLighting 0`).
Cloth needs pre-roll from the shot start. Path tracing OOMs on a 24 GB L4. Never change a material while it is drawn.
Nothing film-specific outside `films/<id>/`. No secrets anywhere.
