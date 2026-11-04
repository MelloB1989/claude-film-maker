# GUIDE: driving Unreal with no UI, for Claude

You are an agent making a film in Unreal Engine 5.8 on a remote box with no screen. Everything goes through
`film-ue` (from `tools/`: `uv run film-ue ...`) or the Python SDK. This guide is how to approach a task end to end;
[dx.md](dx.md) is the reference for the tools, [CONVENTIONS.md](CONVENTIONS.md) for units and rules, and each area's
`docs/unreal/<area>.md` for its recipes. [RECIPES.md](RECIPES.md) has 20 common tasks with their real JSON answers.
The worked example of everything here is
[examples/unreal/demo](../../examples/unreal/demo/README.md).

## The loop

Every task is the same loop. Do not skip the last two steps: you cannot see the editor, so you only know what you
measured.

1. **Look** at the state: `film-ue describe --live level`, `film-ue level describe ...`, `film-ue <area> describe`.
2. **Find** the ops: `film-ue describe <area>`, `film-ue describe <area.verb>` (offline, instant).
3. **Declare** the result as a spec (YAML) when a kind exists (`film-ue plan --kinds`); else call ops.
4. **Plan** (`film-ue plan spec.yaml`), read the steps and their `why`, then **apply** (`film-ue apply spec.yaml`).
5. **Verify** with numbers: `"converged": true`, the area's `describe`, `qa.*` checks.
6. **Look at a picture**: `view.still` / `view.stills` (a contact sheet of the cut), pull the PNG, read it.

## Before anything: is the box healthy?

```bash
film-ue health                  # the bridge answers: engine, platform, queue
film-ue op ops.broken           # {} = every op module imported (else: each broken one's traceback)
film-ue selftest --list         # capabilities: gpu, epic_login, ... and which tests will skip
film-ue selftest dx             # 30 s: the registry, errors, specs, CLI, on THIS box
```
If `film-ue health` fails: `film-ue status` (is the box up?), then `film-ue editor status` / `film-ue editor log`.
After editing anything under `unreal/`, `film-ue install` puts it on the box (seconds).

## Finding and calling ops

```bash
film-ue describe                       # areas
film-ue describe cam                   # one line per op, ~ marks multi-tick ones
film-ue describe cam.frame             # arguments with types, defaults, units; the docstring; an example
film-ue cam frame --camera CAM_A --subjects '["Host"]' --size MCU --dry-run   # check the call, send nothing
film-ue cam frame --camera CAM_A --subjects '["Host"]' --size MCU --json      # call it
```
- Always `--json` when you will read the answer: one JSON document, also on failure. Exit 2 means the call was bad
  and nothing was sent (read `error.candidates`); 1 means the op ran and failed (read `error.hint`); 3 no bridge.
- Long ops (renders, MetaHuman cloud calls, solves) take `--async`: you get a job id; `film-ue job ID --wait`.
- In Python (scripts, loops, anything with logic), the SDK: `ue = Unreal(); ue.cam.frame(camera=..., subjects=[...], size="MCU")`. It raises
  `OpError` with `.code .message .hint .candidates`.
- Units are in the names (`focal_mm`, `duration_s`, `intensity_cd`); distances are cm, rotations `{pitch, yaw, roll}`
  degrees, times in a sequence are frames at its rate (CONVENTIONS §3).

## Specs: say what you want, let apply converge

Prefer a spec to a chain of op calls whenever a kind exists: it is idempotent (apply twice = apply once), it
verifies itself (re-plans after applying), and it is a file you can diff, review and re-run tomorrow.

```bash
film-ue plan --kinds                  # level, scene, shot, audio, render, op, ... with their order
film-ue plan --kinds scene            # one kind's fields
film-ue plan set.yaml                 # steps, nothing changes
film-ue apply set.yaml --json         # read "converged" and, if false, "left"
```
- One document per thing (`kind`, `version: 1`, `name`, fields). Several in a file with `---`. Shared values in a
  `kind: vars` document (`${name}`); other files with `kind: include`.
- A misspelt field is an error with "did you mean"; fix the spec, do not work around it.
- Things with no kind yet: `kind: op` documents (one op call each). Give them `unless: {op, args, has}` (a read op
  that says the work is done) so they converge too; otherwise they re-run on every apply (cheap, idempotent ops only).
- `order: N` on a document runs it between kinds (the demo builds the MetaHuman before the set that places it).
- Plan offline against a state you have (`--state state.json`) to test a spec change without a box.

## Recipes

**A set.** A `scene` spec (WP6: [layout.md](layout.md)): actors by label with `shape`/`asset`/`class`, `loc`, `rot`,
`size`/`scale`, `relative` placement, `drop: true` to rest on what is under it, tags and folders. Check: `film-ue qa
floating --json`, `film-ue qa overlaps --json`; a still from a camera.

**A character.** MetaHuman from a preset, cloud rig, textures, build (WP3: [metahuman.md](metahuman.md); the demo's
stage 1). Needs the Epic sign-in on the box (`film-ue selftest --list` shows `epic_login`). Check:
`film-ue view turntable --target Host --out-dir ...` and `film-ue qa penetration ...` for clothes.

**Light and look.** Lights by label, fog, post (WP5: [look.md](look.md)). Check exposure with numbers, not taste:
`film-ue qa image --image still.png --json` (clipping, mean stops) on a still through the shot's camera.

**A performance.** A voice line to a face (`speech.to_face`), body animation sections (`seq.anim`), face and body as
one skeleton (`anim.bake_follow` / `anim.head_to_body`), eyes on the lens (`anim.gaze_lock`) (WP4:
[animation.md](animation.md)). Check: `seq.sample` bone positions, a still at a frame mid-line.

**Shots.** A `shot` spec (WP7: [cameras.md](cameras.md)): shots by size (`WS`, `MCU`, `CU`...), angle, side, lens; moves;
focus on a subject; times in frames, seconds or dialogue lines. The solver frames from the real skeleton. Check:
`film-ue shot check ...`, `film-ue cam check_cut ...` (the 180-degree line, the 30-degree rule), then `film-ue view
stills --sequence ... --out-dir ...` and LOOK at the contact sheet.

**Review.** `film-ue qa review --sequence ... --out-dir ...`: one JSON (`pass`, `summary` worst first, `issues` each
with a `fix`) and one picture. Fix the fails, re-apply, review again (WP10: [qa.md](qa.md)).

**Render.** A `render` spec, preset `preview` first, then `final` (WP9: [render.md](render.md)). Path tracing does not
fit the 24 GB L4. Check: `film-ue render progress --out-dir ...`; pull a frame and look.

**Deliver.** Pull the frames (`film-ue pull-dir`), then `film-post` with a `delivery` spec (WP12: [post.md](post.md)).

## Reading failures

| you see | it means | do |
|---|---|---|
| `error [bad_args]` exit 2, `candidates` | a misspelt op or argument, caught before sending | use the candidate; `film-ue describe <op>` |
| `error [not_found]` with candidates | the actor/asset/track is not there (or is spelt differently) | the `hint` names the listing op: run it |
| `error [timeout]` with a job id | still running | `film-ue job ID --wait`; raise `--timeout` next time |
| `error [bridge_down]` exit 3 | no bridge | `film-ue health`, `film-ue status`, `film-ue editor status` |
| `error [engine]` | the engine refused | the message is the engine's; check the editor log (`film-ue log 200`) |
| apply `"converged": false` | something did not stick | `left` shows what a second plan still wants and why |
| a plan step `?` ERROR in a kind's describe | the reader failed (often: an earlier stage has not run yet) | apply the earlier stage first |
| `film-ue op ops.broken` non-empty | an op module failed to import on the box | fix it, `film-ue install` |

## Traps (each cost a day; the ops already handle them, your scripts must too)

- **Never open a modal dialog.** The editor runs unattended: a "save?" or "overwrite?" prompt wedges it. Free a path
  before creating over it (`assets.free`), and never call editor UI functions.
- **Rotations are dicts, never positional** (`unreal.Rotator(a, b, c)` is roll, pitch, yaw). Colours by keyword
  (`unreal.Color` positional is B, G, R, A).
- **Multi-tick ops are generators**: in exec'd code `yield from op(...)` inside a generator; a bare call does nothing.
- **A face played by Sequencer** stops following the body: bake them together (`anim.bake_follow`).
- **Hair goes white indoors in daylight**: `r.HairStrands.SkyLighting 0`.
- **Cloth needs pre-roll**: render a shot from its start, not from the middle.
- **Path tracing OOMs on the 24 GB L4.** Use deferred (Lumen) renders.
- **Never change a material while it is drawn** (an assert takes the editor down): ops that do it are multi-tick for
  a reason.
- **The editor may come up on an Untitled level**: a spec's `level` document opens the right one first.
- More in [../../unreal/README.md](../../unreal/README.md) and [../linux/engine.md](../linux/engine.md).

## Rules

- Nothing film-specific in `unreal/` or `tools/`: scenes live in `films/<id>/` (specs, small scripts).
- No secrets in specs, commits or messages. No AWS unless the task says so.
- After changing ops: `film-ue dx gen` (schema + SDK), `film-ue dx check`, then the tests.
