# ue-helpers conventions

This file is binding for every work package (WP) on `ue-helpers`. The lead (agent-10, WP0) owns it. When something
here is unclear or wrong, tell the lead (`fleetctl tell agent-10 "..."`). If you get no answer in about 10 minutes,
decide for yourself and record the decision in `DECISIONS.md`.

**Who it is for:** Claude, an agent that drives Unreal Engine 5.8 with no UI. Every op, spec and doc is written so
that an agent can:

- discover it (`film-ue ops`, `ops.schema`),
- call it without guessing (keyword arguments, units in the names and docstrings),
- re-run it safely (idempotent),
- check the result without looking at a viewport (numbers, stills, reports),
- recover from a failure (actionable errors).

## 1. Where code lives

```
unreal/                      runs INSIDE the editor (embedded Python 3.11.8: no 3.12 syntax; tests enforce it)
  init_unreal.py             starts the bridge                                    WP1
  fmbridge/server.py         HTTP endpoint, game-thread queue, multi-tick jobs     WP1
  fmbridge/errors.py         OpError, closest(), not_found()                       WP1 (created by WP0)
  fmbridge/ops/__init__.py   @op registry, auto-discovery, ops.schema, list        WP0
  fmbridge/ops/<area>.py     the ops of one area (or a package ops/<area>/)        the area's WP
  fmbridge/ops/_<name>.py    shared helpers, not ops (not auto-imported)          whoever creates it, see §9
  fmbridge/selftest/         harness + selftest.run                                WP11
  fmbridge/selftest/<area>.py one area's acceptance test for the GPU box          the area's WP
tools/filmtools/unreal/      runs on the CLIENT (Python 3.12, uv)
  cli.py                     film-ue (framing, generated area commands)           WP11
  schema.py, ops_schema.json offline op schema (AST) + committed snapshot          WP11
  sdk.py                     generated Python API                                  WP11
  spec/ (or apply.py)        film-ue plan/apply engine, kind registry              WP11
  client.py, workstation.py, transport/boxes/...                                    WP1
  <area>_*.py                client-side helpers of one area (spec kinds, checks) the area's WP
tools/tests/
  fakeunreal/                the shared fake engine                               WP0
  fakeunreal/ext_<area>.py   an area's own fakes (def install(fake))              the area's WP
  test_ue_<area>*.py         an area's unit tests                                 the area's WP
docs/unreal/
  CONVENTIONS.md DECISIONS.md BACKLOG.md MORNING-REPORT.md README.md               WP0
  <area>.md                  the area's guide (§10)                               the area's WP
films/<id>/                  scene code only: nothing generic                     the film
```

Areas and owners. The area prefix is the first part of every op name in the area.

| WP | area prefix(es) | owner | files beyond the pattern |
|---|---|---|---|
| WP1 platform & runtime | `editor.`, `bridge.`, `jobs.` | agent-07 | server.py, inbox.py, errors.py, fmbridge/jobs.py, client.py, workstation.py, linuxbox.py, unreal/linux/, tools/filmtools/unreal/linux/ |
| WP2 assets, import, materials, Fab | `assets.`, `mat.`, `fab.` | agent-02 | ops/assets.py |
| WP3 MetaHuman creation | `mh.` | agent-04 | ops/mh.py |
| WP4 animation & performance | `anim.`, `speech.`, `perf.` | agent-01 | ops/anim.py, ops/speech.py |
| WP5 environments, lighting, look | `env.`, `light.`, `look.` | agent-08 | ops/look.py |
| WP6 layout, set dressing, scene specs | `level.`, `layout.`, `scene.` | **unowned** (agent-12 is stopped by the operator); the lead takes it or reassigns it | ops/level.py |
| WP7 cameras & shooting | `cam.`, `shot.` | agent-11 | (look.camera and look.focus_track stay in look.py until WP7 replaces them) |
| WP8 Sequencer core | `seq.` | agent-06 | ops/seq.py, ops/seqcore/ |
| WP9 rendering & output | `render.` | agent-05 | ops/render.py |
| WP10 QA & visual feedback | `qa.`, `view.` | agent-09 | |
| WP11 Claude DX | `ops.` (beyond schema/list), `selftest.` | agent-13 | cli.py, schema.py, sdk.py, spec engine, selftest harness, docs/unreal/GUIDE.md |
| WP12 audio, post, delivery | `audio.`, `post.`, `deliver.` | agent-03 | |

You may edit a file another WP owns only for a small, mechanical fix that unblocks you, such as an import or a
renamed helper. Say so in your commit message and tell the owner. A real change in someone else's area goes to them
as a request, or to the lead.

## 2. Ops

```python
from . import op
from ..errors import OpError, not_found

@op("light.add", mutates=True, idempotent=True, tags=["lighting"])
def add(*, label: str, kind: str = "rect", loc: list = (0, 0, 200), intensity_cd: float = 10.0) -> dict:
    """Make or update a light named `label` (one call converges: re-running moves/retunes the same light).

    Args: label: the actor label. kind: rect|spot|point|directional. loc: [x, y, z] cm. intensity_cd: candela.
    Returns: {"label", "changed": bool, "path"}.
    Example: film-ue op light.add label=Key kind=rect 'loc=[150,120,230]' intensity_cd=25
    """
```

- **Name:** `area.verb`, all lower case with underscores, using one of your area prefixes. Use the standard verbs
  where they fit:
  - `describe`: read the state as JSON, no change.
  - `find`/`list`: search.
  - `add`: create or converge.
  - `set`: change properties.
  - `remove`: delete. It is idempotent: removing nothing is fine.
  - `apply`: converge to a spec.
  - `check`: a numeric QA verdict.
  - `still`: render an image.
  - A domain verb for anything else (`mh.rig`, `render.mrq`).
- **Arguments:** new ops take keyword-only arguments (`*,` first), and every argument is JSON-serialisable. Put the
  unit in the name when it is not the default unit (`duration_s`, `intensity_cd`, `fov_deg`, `focal_mm`). Existing
  ops keep their positional-or-keyword signatures. Never rename an existing op's arguments without keeping the old
  name as an alias.
- **Results:** JSON-serialisable values (the server converts a Vector to a list and an object to its path, but
  return plain values yourself). Mutating ops return a dict that includes `"changed": bool`. Results use stable keys
  in snake_case and no engine reprs.
- **Docstring:** the first line is one sentence for the listing. The body gives the arguments with their units, what
  comes back, and one `Example:` line that can be pasted into `film-ue op`. WP11 builds the CLI help and the SDK from
  the docstring.
- **Flags** (`@op(..., mutates=, idempotent=, tags=)`): set `mutates` and `idempotent` on every new op. Useful tags:
  `slow` (more than 10 s), `gpu`, `windows-only`, `linux-only`, `experimental`, `needs-epic-login`.
- **Registration:** a file in `ops/` registers by being there. `ops/__init__.py` imports every module and
  subpackage. Do not edit it. A module named `_x.py` is a helper and is not imported on its own. Registering the
  same op name from two modules fails at import, so check `film-ue ops <prefix>` first.
- **Schema:** `film-ue op ops.schema` (live) or `tools/filmtools/unreal/ops_schema.json` (offline, by WP11) returns
  every op as `{"name","area","verb","module","file","line","summary","doc","params":[{"name","kind","type",
  "required","default"}],"returns","multi_tick","mutates","idempotent","tags"}`. Both produce exactly this shape.

## 3. Units and addressing

| what | unit / form |
|---|---|
| distance, location | centimetres, `[x, y, z]`, Z up, X forward, Y right (Unreal's left-handed frame) |
| rotation | degrees, a dict `{"pitch", "yaw", "roll"}`. **Never positional** (`unreal.Rotator(a, b, c)` is roll, pitch, yaw) |
| scale | `[x, y, z]` factors, or one number |
| colour | `[r, g, b]` or `[r, g, b, a]` linear 0..1 (`unreal.Color` positional is B, G, R, A: always keywords) |
| colour temperature | kelvin |
| light intensity | the light's own unit, named (`intensity_cd`, `intensity_lux`, `intensity_ev`) |
| time in a sequence | **frames at the sequence's display rate** (int). Seconds only where named `_s` |
| durations | seconds, `_s` |
| angles of view | `fov_deg`, focal length `focal_mm`, filmback `sensor_mm` [w, h] |
| assets | package path `/Game/Folder/Name` (accept `/Game/Folder/Name.Name` too; return the package path) |
| actors | label (unique in the level). Ops that create an actor take `label` and converge on it |
| files on the box | absolute paths. Client-side helpers move files (`client.push/pull`) |
| images | PNG for stills (8-bit sRGB) unless asked. EXR for linear |

## 4. Errors

Raise `OpError` from `fmbridge.errors` (or the `not_found(kind, name, existing, hint=)` helper) for anything the
caller can fix. It needs:

- `code`: one of `not_found`, `bad_args`, `conflict`, `unsupported`, `timeout`, `engine`, `failed`.
- `message`: what went wrong, naming the thing.
- `hint`: what to do next, naming the op (`"list them with level.find"`).
- `candidates`: the nearest valid names (`closest()`).

The server answers `{"ok": false, "code", "message", "hint", "candidates", "details", "error": <traceback>}`. Any
other exception comes back as `code: "exception"`. Never swallow an engine failure. Most engine calls return
`False`/`None` on failure instead of raising, so check the return value and raise an `OpError` with
`code="engine"`.

Validate cheap things (argument values, assets existing) **before** touching the level, so that a bad call changes
nothing.

## 5. Idempotency and convergence

- Running an op twice with the same arguments leaves the same state as running it once: no second actor, no
  `_1` asset, no duplicate track or key. Find what is there by label or path, then update or create it.
- Report `changed` honestly. A re-run that changed nothing returns `changed: false`.
- Specs (§7) converge: `apply` diffs the spec against `describe` and makes only the needed calls.

## 6. Engine safety (the traps that cost us days: unreal/README.md "What the host taught us")

- **No modal dialogs, ever.** The editor runs `-unattended` and offscreen. Free an asset path before you create or
  import over it (`assets.free`). Never call anything that opens a window or a "save changes?" prompt. The fake
  records would-be dialogs in `ue.dialogs`, so assert it stays empty.
- **Game thread only.** Ops run on the game thread, so never touch `unreal` from another thread.
- **Multi-tick for anything long.** Write the op as a generator: `yield` lets the editor tick once, `yield 0.5`
  waits half a second, and `return` gives the result. Use it for compiles, scrubs, renders, waiting for
  shaders/assets/DDC, and polling. Never `time.sleep()` on the game thread, and never block for more than about a
  second without yielding. Generators are called as `yield from other_op(...)` from other generators. A bare call
  does nothing.
- **Batch engine writes.** Write keys in batches (`set_*_keys` / one channel call with arrays), not one call per
  key. Per-key Sequencer writes jammed the game thread.
- **Never change a material while it is drawn.** See the README trap.
- **Blueprint components go stale.** Re-fetch them by name after any property change on a Blueprint actor.
- **Save explicitly.** An op that creates assets saves them (`EditorAssetLibrary.save_asset`) unless the caller
  passes `save=False`. Level changes are saved by `level.save`, not implicitly.
- **Verify APIs against the source.** Every engine API you call must be checked on the UE 5.8.4 source box
  (`rg` over `/srv/ue-src/UnrealEngine-5.8.4`; the Python name is the snake_case of the reflected UFUNCTION or
  UPROPERTY, which must be BlueprintCallable, ScriptMethod or EditAnywhere/BlueprintReadWrite). Record it in your
  doc's API_NOTES (§10). No guessing.
- **Platform.** Linux (UE 5.8.4 source build, Vulkan SM6, offscreen) is the target, and Windows must keep working.
  Anything platform-specific is guarded by `sys.platform` and tagged.

## 7. Declarative specs

- **Format:** YAML or JSON. One document is one object with `kind`, `version` (int), `name`, and the kind's
  fields. A file may hold several documents (YAML `---`). Units follow §3.
- **Kinds:** one per area noun, owned by the area: `character` (WP3, not "metahuman"), `performance` (WP4), `environment`/`lighting`
  (WP5), `scene`/`layout` (WP6), `camera`/`shot` (WP7), `sequence` (WP8), `render` (WP9), `qa` (WP10),
  `audio`/`delivery` (WP12).
- **Schema:** each kind has a JSON Schema (draft 2020-12) in `tools/filmtools/unreal/schemas/<kind>.schema.json`,
  owned by the kind's WP. WP11's engine validates it. Every property has a `description` with its unit. Unknown
  keys are errors (`additionalProperties: false`), so a typo cannot silently do nothing.
- **Planner:** a kind registers with WP11's engine (the API is in `docs/unreal/dx.md`) a function
  `plan(spec, state) -> list[{"op": name, "args": {...}, "why": str}]`. `state` comes from the area's
  `<area>.describe` op. Planning is pure Python with no `unreal`, so it is unit-tested with plain dicts. Apply runs
  the steps and re-describes. Converged means the second plan is empty.
- **CLI:** `film-ue plan <spec>` shows the steps, `film-ue apply <spec>` runs them, `film-ue describe <kind>
  [name] --json` reads state, and `--dry-run` works everywhere.
- **Examples:** each kind ships `examples/unreal/<kind>/*.yaml` that validate in a unit test.

## 8. Feedback for Claude

Every visual change must be checkable without a UI:

- Each area exposes `describe` (numbers).
- Areas whose changes are visual expose `still` or a `qa.*` check (WP10 provides the generic ones: viewport-free
  stills, contact sheets, exposure/histogram, framing of a target in a camera, bounds/penetration, visibility).
- A check op returns `{"pass": bool, "issues": [issue, ...], "metrics": {...}}`. `pass` is true when no issue has
  severity `fail`.
- An issue is `{"code", "severity": "fail"|"warn"|"info", "message", "fix", "frame", "camera", "subject", "box",
  "value", "expected"}`:
  - `code`: a stable dotted id, `area.snake_case` (`framing.headroom_low`, `exposure.clipped_highlights`,
    `mesh.penetration`).
  - `fix`: the op call or change that would resolve it.
  - `box`: `[x0, y0, x1, y1]` in 0..1 image coordinates.
  - Fields that do not apply are omitted.

  WP10 owns the shape. WP7's lens and cut checks use it too.
- Images return `{"path": <file on the box>, "width", "height"}`. The client pulls them.

## 9. Shared helpers

Small generic helpers (vec/rot parsing, actor-by-label, asset free, frame/second conversion) go in
`ops/_util.py`, owned by the lead. Add to it only in a commit that does nothing else, so it merges cleanly, and tell
the lead. Until it lands, the existing `level.actor`, `level.vec`, `level.look_rot`, `assets.load` and `assets.free`
are the shared helpers. Import them and do not copy them.

## 10. Tests, selftests, docs

- **Unit tests:** `tools/tests/test_ue_<area>*.py`, pytest. Use the `ue` fixture (a fresh fake engine) and `fmb`
  (the ops imported against it), plus `fakeunreal.run_op(name, **args)` and `drive(gen)` for multi-tick. Extend the
  fake for your area in `tools/tests/fakeunreal/ext_<area>.py` (`def install(fake)`, loaded automatically) rather
  than editing `core.py`. If core needs a change, send it to the lead. Pure logic (planners, math, timecode, diff)
  is tested without the fake. Tests must run in well under a second each, with no network and no engine.
  - Run them: `cd tools && uv run --group dev pytest -q tests/test_ue_<area>*.py`. On a fleet container without
    uv: `python3 -m venv /work/.venv && /work/.venv/bin/pip install pytest pyyaml`, then
    `/work/.venv/bin/python -m pytest -q tests/test_ue_*.py`.
  - `tests/test_ue_runtime.py` must stay green: every op module imports, every op has a docstring, names are
    `area.verb`, and the code is 3.11 syntax.
- **Selftest:** `unreal/fmbridge/selftest/<area>.py`, run tomorrow on the GPU box by `film-ue selftest <area>`
  (WP11's harness: `docs/unreal/dx.md` has the contract, `def run(t)` with `t.check/still/scratch`). It builds a
  scratch level, exercises every op of the area at least once, re-runs one to prove idempotency, writes stills, and
  leaves no trace outside its scratch folder `/Game/_Selftest/<area>/`. It is your acceptance test, and it must say
  in its docstring how long it takes and what it needs (GPU, Epic login, assets).
- **Docs:** `docs/unreal/<area>.md`, in this order:
  1. What the area does, in 3 lines.
  2. **Recipes:** task, then the exact commands, then what to check.
  3. **Op reference:** short, with a pointer to `film-ue ops <area>`.
  4. **Spec kinds** with an example.
  5. **Gotchas.**
  6. **API_NOTES:** a table of every engine API used, with the source file:line on the source box and whether it
     was verified.
  7. **Selftest:** what it proves and how long it takes.
  8. **HANDOFF:** where you stopped. Required before your quota runs out.

## 11. Git

- Branch `fleet/<you>/ue-<area>` from `origin/ue-helpers`. Push often. Tell the lead when a reviewable chunk is
  pushed (`fleetctl tell agent-10 "ue-<area> ready at <sha>: <one line>"`).
- To pick up other WPs' work, merge `origin/ue-helpers` into your branch. Do not rebase once you have pushed. Never
  push to `ue-helpers`, `main` or `anime/rain-ferry`.
- Commit messages say what changed and why. They end with `Co-Authored by MelloB's coding agent <build@mellob.in>`.
- No secrets, no engine source (EULA), and no binaries over about 1 MB. Stills for docs go under
  `docs/unreal/img/`, small JPGs.
- NO AWS tonight (operator's order). The only remote you touch is the read-only UE source box.
