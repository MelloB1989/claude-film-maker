# dx: Claude's developer experience (WP11)

Everything an agent needs to drive Unreal without a UI: every op as a command (`film-ue <area> <verb> --arg v`) and as
typed Python (`ue.<area>.<verb>(arg=v)`), both generated from one op schema; `film-ue describe` to discover; errors
that say what to do next; declarative specs (`film-ue plan` / `apply`) that converge and verify; and the selftest
harness (`film-ue selftest`) that runs every area's acceptance test on a box and writes one report.

Start with [GUIDE.md](GUIDE.md) for how to approach a film task end to end. This file is the reference and the
contract other WPs build on (§4 kinds, §5 selftests, §6 CLI hooks).

## 1. Recipes

**Find the op for a job, and how to call it** (offline: no box needed)
```bash
film-ue describe                      # the areas, with op counts
film-ue describe look                 # one area's ops, one line each (~ = multi-tick)
film-ue describe look.light           # arguments, types, defaults, units, the docstring, the source line
film-ue describe light                # a prefix or a near miss: what matches
film-ue describe --json seq.key_float # the same as data
film-ue describe --live look          # what the RUNNING bridge has (a newer box)
```
Check: the `film-ue look light ...` and `ue.look.light(...)` lines it prints are the call.

**Call an op**
```bash
film-ue level spawn --label Box --shape cube --loc 0,0,50 --rot yaw=30
film-ue level move --label Box --look-at 0,0,100 --json        # one JSON document on stdout, also on failure
film-ue seq new --path /Game/Demo/Seq --end 96 --dry-run       # validate offline, print the request, send nothing
film-ue look light --args @key.yaml                            # arguments from a file (flags given too win)
film-ue render mrq --sequence ... --level ... --out-dir ... --async   # a job id; then:
film-ue job 3f2a9c1b07de --wait --json
```
Values: numbers and strings as typed; lists as `0,0,300` or JSON; dicts as `k=v,k=v` or JSON; `@file` (JSON/YAML),
`-` (stdin), `null`. Bool flags: `--replace`, `--no-replace`, `--replace false`. Flags are the argument names with `-`
(`--look-at`); a trailing `_` is dropped (`rot_` is `--rot`). Exit codes: 0 ok, 1 the op failed, 2 a bad call caught
offline (nothing was sent), 3 no bridge. An op argument named like a film-ue flag keeps the name; the flag becomes
`--call-<flag>` (`look.still --timeout 60 --call-timeout 900`).

**From Python**
```python
from filmtools.unreal.sdk import Unreal, OpError
ue = Unreal()                                   # the box film-ue talks to (FILM_UE_BOX / --box)
ue.level.spawn(label="Box", shape="cube", loc=[0, 0, 50])
job = ue.render.mrq(sequence=..., level=..., out_dir=..., _wait=False)
frames = job.wait(timeout=3600, on_progress=print)
try:
    ue.level.move(label="Bxo", loc=[0, 0, 0])
except OpError as e:
    print(e.code, e.message, e.hint, e.candidates)   # not_found, ..., "film-ue level actors --contains Bxo", [...]
ue.call("area.verb", **args)                    # an op this checkout's SDK does not know yet (a newer bridge)
```
Arguments are keyword-only and spelled as the op spells them (`rot_`, `cls`); a Python keyword gets a trailing `_`
(`ue.assets.import_`). `_wait` and `_timeout` are the SDK's own. An argument left out takes the op's default ON THE
BRIDGE (the SDK sends only what you pass). Argument names are checked against the schema before anything is sent.

Worked scripts: [examples/unreal/sdk](../../examples/unreal/sdk/README.md) (level and set, light + exposure check, a
MetaHuman, a camera by shot grammar + framing check, a 2 s render).

**Converge the editor to a spec**
```bash
film-ue plan --kinds                  # the kinds; film-ue plan --kinds actor: its fields, types, defaults, units
film-ue plan scene.yaml               # the steps apply would run, with why; nothing changes
film-ue plan scene.yaml --state st.json   # plan OFFLINE against a state you give ({kind: {name: state}})
film-ue apply scene.yaml --json       # run the steps, re-describe, re-plan: "converged": true when nothing is left
film-ue apply scene.yaml --set fps=30 --only actor,level
```
Check: `"converged": true`. When false, `left` lists what is still pending and why.

**Run the acceptance tests on a box**
```bash
film-ue selftest plan                 # OFFLINE: the run order, durations, needs (--md: the morning-report table)
film-ue selftest --list               # the areas with a selftest, what each needs, which will skip here
film-ue selftest dx                   # one area
film-ue selftest                      # all of them in the plan's order; stops if a gate (platform, dx) fails
film-ue selftest look seq --keep      # keep the scratch levels to look at
```
Check: `selftest-reports/<time>/summary.md` (status per area, failures with got/want, stills) and `summary.json`.

**See what was done to the level, and rebuild it** (the op journal, B32)
```bash
film-ue journal tail --n 20 --json                # the last ops that changed something: op, args, ms, result
film-ue journal tail --prefix level. --since-s 600
film-ue journal clear                             # before building something you will want to replay
film-ue journal replay --dry-run                  # what would run; without --dry-run it runs (multi-tick)
```
Every op whose `mutates` is True or unset is appended to `Saved/fmbridge/journal.jsonl` by an `ops.after_call` hook
(journal.*, selftest.*, ops.* are not); a multi-tick op is recorded when it starts and its outcome folded in when the
job registry reports it (`jobs.on_finish`, when WP1's jobs.py has it).

**After changing or adding ops** (in the same commit)
```bash
film-ue dx gen      # rewrite tools/filmtools/unreal/ops_schema.json (committed) and sdk/_generated.py (not
                    # committed: the SDK builds itself in memory from the ops when the file is absent or stale)
film-ue dx check    # exit 1 when they are stale (tests/test_ue_dx.py fails too)
film-ue dx lint     # ops that are hard for an agent: no docstring, untyped required args, not area.verb, broken;
                    # kind schemas without descriptions or with additionalProperties not false
film-ue dx docs     # every `film-ue <area> <verb> --flag` line in the docs parses against the op schema
film-ue dx sdk      # every ue.<area>.<verb>(...) / ue.call("a.v") in examples/ and films/*/unreal/ matches the schema
film-ue dx coverage # which ops each selftest exercises (statically), and the op areas with no selftest
```
`ops_schema.json` can conflict in a merge when two branches both regenerated it: take either side and run
`film-ue dx gen` again.

## 2. Reference

| command | what |
|---|---|
| `film-ue <area> <verb> [--flags]` | any op (`opcli`), `--json --dry-run --async --timeout --args --verbose --live` |
| `film-ue describe [area\|area.verb\|prefix] [--json] [--live]` | ops, offline from the schema (`--live`: the bridge's) |
| `film-ue describe --live level\|actors TEXT\|seq PATH\|cuts PATH\|components LABEL\|assets PATH` | the editor's state |
| `film-ue describe --live <kind> NAME` | one spec kind's state, as plan sees it (`actor Box`, `scene office`, `render demo`) |
| `film-ue job ID [--wait] [--json]` | an `--async` op's state, or its result |
| `film-ue plan SPEC... [--state FILE] [--only K] [--set N=V] [--json]` | the steps |
| `film-ue apply SPEC... [--dry-run] [--stop] [--only K] [--set N=V] [--json]` | converge and verify |
| `film-ue selftest [AREA...\|all] [--list] [--keep] [--out DIR] [--no-pull] [--json]` | acceptance tests |
| `film-ue dx gen\|check\|lint\|docs\|sdk [FILE...]\|coverage` | the generated layers; op/schema lint; doc commands against the schema |

Bridge ops of this area: `selftest.list`, `selftest.run` (multi-tick), `selftest.cleanup`; `journal.tail`,
`journal.clear`, `journal.record`, `journal.replay` (multi-tick). `ops.schema` / `ops.broken` /
`list` are the lead's (ops/__init__.py).

Files (all WP11 unless noted):

| file | |
|---|---|
| `tools/filmtools/unreal/schema.py` | static op schema (AST over `unreal/fmbridge/ops/**`), `index()` for the generators, `lint()` |
| `tools/filmtools/unreal/ops_schema.json` | the committed snapshot (for a tools/ without unreal/) |
| `tools/filmtools/unreal/opcli.py` | the generated `film-ue <area> <verb>` |
| `tools/filmtools/unreal/sdk/` | `Unreal`, `OpError`, `Job`; `gen.py` (writes `_generated.py`, gitignored: a readable copy) |
| `tools/filmtools/unreal/errors.py` | `Problem`, `explain()` (bridge answer -> code/message/hint/candidates), `check_args()` |
| `tools/filmtools/unreal/describe.py` | `film-ue describe` |
| `tools/filmtools/unreal/spec.py`, `jsonschema_lite.py`, `kinds/` | the plan/apply engine; generic kinds level/actor/op |
| `tools/filmtools/unreal/schemas/{level,actor,op}.schema.json` | the generic kinds' schemas (other kinds: their WP) |
| `tools/filmtools/unreal/selftest.py`, `selftests/` | `film-ue selftest`; client phases |
| `tools/filmtools/unreal/dxcli.py`, `cli.py` | the commands; the hooks for other areas (§6) |
| `unreal/fmbridge/selftest/__init__.py`, `ops/selftest.py` | the harness, in the editor |
| `unreal/fmbridge/selftest/dx.py`, `tools/filmtools/unreal/selftests/dx.py` | this area's own selftest |
| `tools/tests/test_ue_dx*.py`, `tools/tests/fakeunreal/ext_dx.py` | tests; the fake's basic shapes and `UClass.get_name` |

## 3. The schema

`schema.extract()` reads every `@op("area.verb", mutates=, idempotent=, tags=)` under `unreal/fmbridge/ops/` with
`ast` (no `unreal`, no box) into exactly the shape the bridge's `ops.schema` answers (CONVENTIONS §2), plus `areas`
(each area module's docstring line). A test (`test_static_schema_equals_live_ops_schema`) runs the live one on the
fake engine and requires them to be equal, field for field. The one known difference: a default that is not a JSON
literal is `null` statically and its `repr` live.

`schema.index()` adds what the generators need: per param the CLI `flag`, a `value` kind (int, float, bool, str, list,
dict, any; from the annotation, else the default's type), `nullable`, `help` (from an `Args:` section), `choices`
(only from an explicit "`name` one of a, b, c" in the docstring); per op `examples` (lines starting `film-ue ` or
after `Example:`) and `summary` (the first sentence, `e.g.`-safe). **Annotate your arguments**: an unannotated
argument with no default is `any` (the CLI guesses: JSON, `k=v` dict, number list, else text).

## 4. Specs: the engine and writing a kind

Format (CONVENTIONS §7): YAML (documents split by `---`) or JSON (an object or a list). Every document is one thing:
`kind`, `version: 1`, `name` (the key; a kind may use another key, e.g. `level` uses `path`), and the kind's fields.
Two engine documents: `{kind: vars, vars: {...}}` (then `${name}` in any string after it; `"${n}"` alone keeps the
value's type; `--set n=v` wins) and `{kind: include, files: [...]}` (relative to the including file).

The engine (`spec.py`): load -> validate each document against `schemas/<kind>.schema.json` (`additionalProperties:
false`: a typo is an error with "did you mean"; the envelope `kind`/`version`/`name`/`description` is always allowed;
top-level `default`s are filled in) -> describe (the kind's reader, through the SDK) -> `plan(spec, state)` -> steps,
each checked against the op schema (a planner that names an unknown op or argument fails at plan time with
candidates) -> apply runs them in kind `order`, then file order -> describe and plan again: **converged = the second
plan is empty**. A failing step stops that document (`--stop`: everything) and is reported with the bridge's code,
message and hint.

**Writing a kind** (in your own module: `tools/filmtools/unreal/<area>_kinds.py` or any `filmtools/unreal/*.py`; the
engine finds modules that call `register_kind(` or define `SPEC_KINDS`, imports each once, and skips a broken one
with a warning):

```python
from filmtools.unreal.spec import register_kind

def plan(spec: dict, state: dict | None) -> list[dict]:
    """PURE: no unreal, no I/O. state is what describe returned (None = it does not exist)."""
    if state is None:
        return [{"op": "light.add", "args": {"label": spec["name"], "kind": spec["type"]}, "why": "no such light"}]
    if abs(state["intensity_cd"] - spec["intensity_cd"]) > 0.01:
        return [{"op": "light.set", "args": {"label": spec["name"], "intensity_cd": spec["intensity_cd"]},
                 "why": f"intensity {state['intensity_cd']} -> {spec['intensity_cd']}"}]
    return []

def describe(ue, spec):                       # ue is filmtools.unreal.sdk.Unreal: call your describe op
    return ue.light.describe(label=spec["name"]).get("light")

register_kind("lighting", plan, describe, order=40, doc="Lights by label: ...")
# or, one call for every document of the kind:  register_kind(..., describe_many=lambda ue, specs: {name: state})
# or, declaratively:  SPEC_KINDS = [{"name": "render", "plan": plan, "describe": describe, "order": 90}]
```

- A step is `{"op", "args", "why"}`; optional `"timeout"` (s) and `"always": true` (a step that runs on every apply
  and does not count against convergence: the `op` kind's).
- `order`: level 0, assets 10, characters 20, layout 30, lighting 40, cameras 50, sequences 60, shots 70, op 80,
  renders 90.
- The schema goes in `tools/filmtools/unreal/schemas/<kind>.schema.json` (draft 2020-12 subset: type, properties,
  required, additionalProperties, enum, const, min/max, items/prefixItems, min/maxItems, pattern, oneOf/anyOf/allOf,
  `$ref` to `#/$defs`, default). Every property has a `description` with its unit (a test checks it for mine).
- Helpers: `filmtools.unreal.kinds.same(have, want, tol)` (numbers within tol, `"angle:0.05"` for degrees modulo 360,
  lists and dicts element-wise) and `changed(spec, state, {field: tol})`.
- Test the planner with plain dicts (no fake needed) and `spec.plan(docs, state={kind: {name: state}})`; test apply on
  the fake with the `FakeBridge` transport in `tests/test_ue_dx_e2e.py` (copy it).
- Examples: `examples/unreal/<kind>/*.yaml`, loaded by a test.

Generic kinds (WP11, `kinds/core.py`): `level` (open it, or create it), `actor` (any actor by label: `shape` | `asset` |
`cls`, `loc`, `rot` or `look_at`, `size` or `scale`, `material`; a moved actor is moved back with one `level.move`, a
changed class respawns it), `op` (one op call per apply). `actor` stands in until WP6's layout kinds exist.

## 5. Selftests: the contract

`unreal/fmbridge/selftest/<area>.py` (Python 3.11, runs in the editor):

```python
"""What it proves (one paragraph). Takes ~2 min. Needs: GPU."""      # Takes + Needs: checked by a test, and
                                                                     # read by `film-ue selftest plan` (estimates)
REQUIRES = ["gpu"]          # optional: gpu, display, linux, windows, epic_login, mh_cloud. Unmet -> skipped, not failed
AREAS = ["light", "look"]   # optional: op prefixes it covers (default: the module name); drives ops_covered/ops_missed
NEEDS_LEVEL = True          # optional: a fresh scratch level /Game/_Selftest/<area>/L_<area> opened first
TIMEOUT = 600               # optional: seconds (default 900)

def run(t):                 # may be a generator: yield ticks the editor once, yield 0.5 waits
    key = t.prefix + "Key"                                   # ST_<area>_: name everything you make with it
    t.op("light.add", label=key, kind="rect", loc=[0, 0, 200])    # an op, recorded as covered
    r = yield from t.op("look.still", ...)                   # a multi-tick op comes back as a generator
    t.check("intensity", got, 25.0, tol=0.01)                # numbers within tol; lists/dicts element-wise
    t.ok("visible", cond, detail="...")
    t.near("exposure", ev, 0.0, rel=0.1)
    t.raises("bad kind is bad_args", "light.add", code="bad_args", label=key, kind="nope")   # OpError + hint
    t.idempotent("light.add converges", "light.add", label=key, kind="rect")  # 2nd run: changed == False
    path = yield from t.still("key", camera=t.prefix + "Cam")  # PNG in the report folder (view.still, else look.still)
    t.metric("render_s_per_frame", 0.73, "s"); t.note("..."); t.artifact(t.path("curves.json"))
    t.skip("no Epic sign-in")                                # stops: skipped
    return {...}                                             # lands in report["extra"]
```

- Nothing raises out of `check/ok/near/raises/idempotent`: one failure does not hide the next. An exception out of
  `run` is recorded (with what passed before it) as `status: error`.
- `t.scratch` (`/Game/_Selftest/<area>`) holds every asset you make; the harness deletes it afterwards and goes back to
  the level that was open (or a blank one) unless `--keep`. `t.out` is the report folder on the box, `t.box` the
  engine, platform, command line and capabilities.
- Outside a selftest (any op or exec'd script that needs a throwaway place): `from fmbridge.ops._scratch import scratch`
  then `with scratch("/Game/_Scratch/<name>") as s:` (a fresh level at `s.level`, `s.prefix` for labels; back to the
  previous level and the folder deleted on exit, also on an exception or a closed generator; `level=False` stays in
  the open level and destroys `s.prefix*` actors on exit; only /Game/_Scratch and /Game/_Selftest are allowed). The
  harness uses the same code.
- `t.call(op, ...)` runs a short multi-tick op to its end without ticking (for a test that is not a generator).
- Report (`<out>/<area>.json`): `{area, ok, status: done|skipped|error, passed, failed, checks: [{name, ok, got, want,
  detail, ms}], ops_covered, ops_missed, stills, artifacts, notes, metrics (incl. op_ms per op), errors, extra, box,
  ms, report}`.
- A client phase (optional): `tools/filmtools/unreal/selftests/<area>.py` with `def run(ue, t)` (the SDK, and a
  `ClientT` with check/ok/note/metric/skip, `t.scratch = /Game/_Selftest/<area>_client`): run by `film-ue selftest`
  after the bridge phase. Use it for what only the client can test (specs through the SDK, the CLI). Clean up with
  `ue.call("selftest.cleanup", area="<area>_client")`.
- Unit-test your selftest on the fake: `run_op("selftest.run", area="<area>", out_dir=str(tmp_path))` and assert the
  report has no failures that the fake can judge (see `tests/test_ue_dx_selftest.py`).

## 6. CLI hooks for other areas

- `tools/filmtools/unreal/cli_<area>.py` with `register(sub)` (add your subparsers) and `dispatch(a) -> bool` (run one,
  True if it was yours): found and wired automatically; a broken one is reported and skipped. Do not add a command
  named like an op area (`film-ue <area> ...` is the generated op command).
- Hand-written commands beside an area's generated ones (`film-ue render plan spec.yaml` next to the op
  `film-ue render mrq`): add `"area": "module:function"` to `opcli.EXTENSIONS` (function takes argv, returns an exit
  code; op verbs always win). `render` is wired to `filmtools.unreal.render:main` (WP9).

## 7. Gotchas

- `film-ue dx gen` after every op change, or `test_snapshot_and_sdk_are_current` fails: the SDK follows the ops by
  itself, only the committed snapshot can be stale (and `ue.call("area.verb")` reaches any op the bridge has).
- Specs never contain secrets or film-specific paths outside `films/<id>/`.
- `apply` re-describes everything after running: a kind whose describe is slow makes apply slow; give it
  `describe_many` (one op call for all documents of the kind).
- `film-ue --box NAME <area> <verb>` works; `--box` must come before the area.
- The `actor` kind compares location within 0.5 cm, rotation within 0.05 degrees, scale within 0.001: an op that snaps
  or offsets actors (to the floor, to a socket) will look like drift; give such things their own kind.
- `selftest.run` deletes `/Game/_Selftest/<area>`: never put anything you want to keep there.
- A selftest that opens a modal dialog wedges the unattended editor: free paths before creating (CONVENTIONS §6).

## 8. API_NOTES (engine APIs this area calls; verified on the 5.8.4 source box)

| Python | C++ | file:line | verified |
|---|---|---|---|
| `EditorActorSubsystem.get_all_level_actors()` | `GetAllLevelActors` | Engine/Source/Editor/UnrealEd/Public/Subsystems/EditorActorSubsystem.h:166 | yes |
| `UnrealEditorSubsystem.get_editor_world()` | `GetEditorWorld` | Engine/Source/Editor/UnrealEd/Public/Subsystems/UnrealEditorSubsystem.h:49 | yes |
| `LevelEditorSubsystem.new_level(path)` | `NewLevel` | Engine/Source/Editor/LevelEditor/Public/LevelEditorSubsystem.h:147 | yes |
| `LevelEditorSubsystem.load_level(path)` | `LoadLevel` | Engine/Source/Editor/LevelEditor/Public/LevelEditorSubsystem.h:167 | yes |
| `EditorAssetLibrary.does_asset_exist / load_asset` | `DoesAssetExist` / `LoadAsset` | Engine/Plugins/Editor/EditorScriptingUtilities/Source/EditorScriptingUtilities/Public/EditorAssetLibrary.h:70 / :37 | yes |
| `EditorAssetLibrary.delete_directory / does_directory_exist` | `DeleteDirectory` / `DoesDirectoryExist` | same file :156 / :301 | yes |
| `Actor.get_actor_label()` | `GetActorLabel` (editor) | Engine/Source/Runtime/Engine/Classes/GameFramework/Actor.h:2734 | yes |
| `Actor.get_actor_location / get_actor_rotation` | `K2_GetActorLocation` / `K2_GetActorRotation` | Actor.h:1568 / :1589 | yes |
| `Actor.get_actor_scale3d()` | `GetActorScale3D` | Actor.h:1710 | yes |
| `Actor.tags` | `TArray<FName> Tags` (BlueprintReadWrite) | Actor.h:1344 | yes |
| `SystemLibrary.get_command_line()` | `GetCommandLine` | Engine/Source/Runtime/Engine/Classes/Kismet/KismetSystemLibrary.h:2047 | yes |
| `SystemLibrary.get_engine_version()` | `GetEngineVersion` | KismetSystemLibrary.h:215 | yes |
| `Object.get_path_name()` | `GetPathName` | Engine/Source/Runtime/CoreUObject/Public/UObject/UObjectBaseUtility.h:381 | yes |
| `FrameRate.numerator / denominator` | `FFrameRate` fields | Engine/Source/Runtime/Core/Public/Misc/FrameRate.h:38 / :43 | yes |
| embedded Python | 3.11 | Engine/Source/ThirdParty/Python3/python_v3.11.x.tps | yes |

Not verified, assumed: none. Capabilities use the command line (`-nullrhi`, `-RenderOffscreen`) and, on Linux, the
Epic sign-in store `~/.local/share/.eos_sdk` (docs/linux/engine.md), not an engine API.

## 9. Selftest

`film-ue selftest dx` (~30 s, needs nothing). Bridge phase (`unreal/fmbridge/selftest/dx.py`): no broken op module;
`ops.schema` has the CONVENTIONS shape for every op and names the same ops as `list`; every op has a docstring and an
area.verb name; an unknown op is `not_found` with candidates; a misspelt argument is `bad_args` with a hint;
`level.spawn` converges on a label; `level.move` moves; a generator job ticks; a still through a camera. Client phase
(`selftests/dx.py`): a 4-document spec validates, plans, applies, converges (second plan empty), a moved actor is
fixed with exactly one `level.move`, `film-ue level actors --json` answers, a missing actor is an actionable error.
On the fake engine the whole thing passes in tests (`test_film_ue_selftest_dx_end_to_end`).

## 10. HANDOFF

State (fleet/agent-13/ue-dx, merged into ue-helpers by the lead as it lands):

- Done and tested on the fake (tools/tests/test_ue_dx*.py, ~95 tests): schema (static == live, field for field),
  generated CLI, SDK, describe, errors, job, plan/apply engine + generic kinds + bridge-planned scene/shot, selftest
  harness + ops + client runner + client phases, baselines hook (WP10), `dx gen|check|lint|docs`, GUIDE.md, the skill
  (.claude/skills/film-ue/SKILL.md), the demo (examples/unreal/demo) with its README.
- NOT run on a real editor yet (no GPU box tonight). First thing tomorrow on the box: `film-ue install`,
  `film-ue selftest dx` (must be all OK: it exercises the registry, the error contract, spawn/move, a still, and on
  the client side plan/apply/drift and the generated CLI), then `film-ue selftest` (all areas), then the demo README.
- Things most likely to need a fix on the real box, in order: (1) the `actor` kind's exec snippets (READ_ACTORS uses
  get_actor_location/rotation/scale3d and `a.tags`: verified APIs, but the str() of an FName tag is assumed); (2)
  `selftest._fresh_level` on a path whose level is loaded elsewhere (delete_asset of a loaded world: it steps aside to
  the blank level first); (3) the demo's `host_bp` / `face_mesh` paths (where mh.build puts them: README stage 1 says
  how to check and set them); (4) `look.post` setting names in 30-look.yaml (auto_exposure_method/bias); (5) the
  `capabilities()` display check on Linux (DISPLAY env inside the editor).
- cli.py's provision/editor/epic-login/desktop are gone (c95ad6c): WP1's cli_platform.py has them; `film-ue editor
  status|restart|log|...` reach its editor_cli through opcli.EXTENSIONS, `film-ue editor describe|cvar|...` are ops.
- Known gaps: no `--prune` in the engine (scene has its own `prune:`); `film-ue apply` has no per-step progress output
  (it prints at the end; use `--json` and read `items`); the SDK's Job polls every 2 s (WP1's client.wait with
  on_progress could replace it); kind schemas of other WPs are validated only for what jsonschema_lite supports
  (no `if/then`, `dependentRequired`, `format`).
- Backlog: B10 scratch context DONE (ops/_scratch.py); B34 SDK examples DONE (examples/unreal/sdk, `dx sdk` checker).
  B32 op journal DONE (ops/journal.py + the after_call hook in ops/__init__.py; the job outcome line needs
  `jobs.on_finish` from WP1: asked agent-07). B35 DONE: docs/unreal/RECIPES.md, generated by tools/tests/recipes_gen.py (20 tasks run on the fake engine through
  the generated CLI, their --json answers under each command; test_ue_dx_recipes.py keeps it running).
  B46 DONE: `film-ue selftest plan [--md|--json]` (tools/filmtools/unreal/selftest_plan.py): order platform, dx, then
  assets, layout, look, mh, anim, perf, seq, cam, render, qa, audio, then the rest; `film-ue selftest` runs in that
  order and stops after a failed gate unless --keep-going.
  B48 DONE: tools/tests/test_ue_dx_demo.py applies the WHOLE demo (examples/unreal/demo/demo.yaml, every stage) on the
  fake engine through the spec engine, the SDK and every area's ops, then requires the second plan to be empty. It
  provides only what a box has and the fake does not (a preset, the sign-in, the audio solve, a WAV, Body/Face
  components with a standing pose, the template idle). KNOWN (what cannot converge, with why): the scene's Blueprint
  actor: fixed by the lead in WP6 (scene.state reports `blueprint`), so KNOWN is now empty. Found and fixed on
  the way: the demo's host_bp/face_mesh paths (<folder>/Unpacked/<name>/...).
