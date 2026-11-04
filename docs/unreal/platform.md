# Platform & runtime (WP1)

The ground everything else stands on: **boxes** (a Windows workstation, a temporary Linux GPU box, this machine)
reached the same way whatever the OS, the **editor** kept alive on them, the **bridge** inside the editor that runs
ops as **jobs** you can start, watch, cancel and find again, and what a box keeps in **S3**.

Op areas: `editor.`, `bridge.`, `jobs.` (in the editor). Client: `tools/filmtools/unreal/{transport, workstation,
profiles, boxes, editorsvc, sync, client, cli_platform}.py`. Box side: `unreal/linux/` (setup.sh, the editor unit,
ue-epic.sh, the watchdog).

## 1. Recipes

### A temporary GPU box, from nothing to a running editor

```bash
film-ue box up gpu1 --type g6.4xlarge --ttl 4h --like linux     # launches it; makes profile gpu1 (settings from "linux")
film-ue --box gpu1 provision --engine-s3 s3://B/ue-linux --version 5.8.4 \
    --project-src s3://B/ue-projects/HostStudio --project HostStudio --level /Game/Studio/Studio \
    --epic-s3 s3://B/ue-linux/secrets/epic/eos_sdk.tgz
film-ue --box gpu1 sync ddc restore                            # compiled shaders: skips ~20 min of first open
film-ue --box gpu1 install                                     # the bridge (restarts the editor the first time)
film-ue --box gpu1 editor status                               # unit, bridge, last crash, the watchdog's view
film-ue --box gpu1 editor wait_compile --timeout-s 3600        # (op) until no shader compiles
```

Check: `film-ue --box gpu1 health` answers with `bridge: 2`; `film-ue box ls` shows the box with its time left.

The box ends itself: at its TTL (the watchdog, plus a systemd timer as a backstop), or after `--idle` minutes with
nothing happening (no bridge call or job, GPU and CPU quiet, nobody logged in). Powering off terminates it. Before
it ends, the editor is stopped, so its unit saves the Epic sign-in to S3.

### The first morning on a new box: one resumable command

```bash
film-ue --box gpu1 first-run [--epic] [--voice demo_line.wav]   # settings, reach, editor, bridge, shaders, doctor,
                                                                 # epic, selftest platform+dx, the demo's stage 0
film-ue --box gpu1 first-run --status                            # where it stopped, and the next command
```

Each step checks one thing and fixes what it safely can: it starts the editor, installs or updates the bridge, and
waits out the shader compile. On a failure it stops, prints the exact next command (`next: ...`), and keeps its
progress in the profile. Running it again continues from there. `--from STEP` reruns from a step, `--restart`
reruns everything. Steps that need a person (the Epic sign-in, the voice line) say so.

### Bake a ready box into an image (the next box starts in minutes)

```bash
film-ue box image gpu1 --label hs [--wait]     # editor stopped, sign-in and tokens removed, then an AMI; reboots once
film-ue box images                             # newest first: ami, project, engine, state, snapshots
film-ue box up gpu2 --like linux --ami latest  # the newest image for that profile's project
film-ue box image-rm ami-...                   # deregister + delete its snapshots (they cost money while kept)
```

The image holds the engine, the project, the warm DDC and the bridge. It holds no Epic sign-in (the new box restores
it from S3 at the editor's start) and no TTL: the watchdog in it keeps idle protection only, and `box up` gives the
new box its own TTL.

### Keep a box, give it more time, end it

```bash
film-ue box extend gpu1 --ttl 2h        # 2 h from now (tag, watchdog and backstop all updated)
film-ue box keepalive gpu1              # reset the idle clock (e.g. before a long think)
film-ue box status gpu1                 # what kept it busy last minute, and the time left
film-ue --box gpu1 sync project up      # put the project back in S3 first (refused with unsaved packages)
film-ue --box gpu1 sync ddc save
film-ue box down gpu1 [--forget]        # terminate (and forget the profile)
```

### Several boxes

```bash
film-ue profile ls                      # every profile, the current one marked
film-ue profile use gpu1                # commands without --box now go to gpu1
film-ue --box win health                # one command on another box
film-ue profile copy gpu1 gpu2          # same settings, no instance
```

### Long work: start it, watch it, cancel it, find it again

Every bridge call is a job. `film-ue op` waits for it, polling, so a dropped tunnel or a bridge reload does not lose
it:

```python
from filmtools.unreal import client
jid = client.submit("render.mrq", sequence="/Game/Reel/SEQ_Reel", level="/Game/Studio/Studio", out_dir="...")
client.wait(jid, timeout=3600, on_progress=lambda j: print(j["progress"], j["message"]))
client.jobs(state="running")            # [{id, name, state, progress, message, ...}]
client.cancel(jid)                      # a multi-tick job stops at its next step and runs its clean-up
client.job(jid)                         # its result, for 24 h, across bridge reloads
```

From the CLI: `film-ue job ID [--wait]` (WP11), or the ops `film-ue op jobs.list state=running`,
`jobs.get id=...`, `jobs.cancel id=...`.

An op reports progress by yielding a dict: `yield {"progress": i / n, "message": f"frame {i}/{n}", "wait": 0.1}`.
A `try/finally` around its loop runs on cancel (the generator is closed).

### The editor service

```bash
film-ue editor status                     # unit (state, restarts, pid), bridge health, last crash, watchdog decision
film-ue editor restart --wait             # and wait for the bridge (fails fast with the crash if the unit dies)
film-ue editor log 300                    # the editor's own log; --journal for the unit's
film-ue editor crashes 5                  # Saved/Crashes: when, the exception, the fatal line, out-of-memory
film-ue editor restart --once-args="-AUTH_TYPE=exchangecode -AUTH_PASSWORD=..."   # arguments for one start only
film-ue editor describe                   # (op) engine, RHI, level, unsaved packages, idle cap, memory, jobs
film-ue editor cvar --name r.RayTracing   # (op) read; --value 0 to set
film-ue editor idle --fps 10              # (op) cap an offscreen editor between jobs
```

On Windows the editor lives in the logged-in desktop session (DCV): `status`, `log`, `crashes` and `stop` work from
here, but not `start`.

### The Epic sign-in (MetaHuman cloud services, Fab)

```bash
film-ue epic-login                  # signed in already? done. Else prints a code: anyone with the account opens
                                    # https://www.epicgames.com/activate on their own device and enters it
film-ue epic-login --fab            # Fab's own sign-in (a separate Epic client), same device-code flow
film-ue epic-login --exchange-code-cmd ./my-helper     # no person: the helper prints a single-use exchange code
film-ue sync epic status|save|restore
```

The sign-in is the EOS SDK's persistent credential (`~/.local/share/.eos_sdk/keychain/<id>/persistent_auth/
credential`, ~6 months). The unit restores it from `epic_s3` (SSE-KMS) before the editor starts and saves it after
the editor stops, so a refreshed token is kept and a new box starts signed in. It signs in to the **whole Epic
account**. Never print it, copy it elsewhere, or run `Fab.Logout` / `Fab.SetEnvironment` (both delete it;
`editor.console` refuses them).

### Run something on a box

```bash
film-ue sh 'nvidia-smi; df -h /srv' [--root]      # the box's own shell (bash; PowerShell on Windows)
film-ue push LOCAL REMOTE / pull REMOTE LOCAL      # one file through the bridge
film-ue pull-dir REMOTE_DIR LOCAL_DIR              # a folder (S3 / rsync / copy, by transport)
```

## 2. Op reference (`film-ue ops editor`, `ops bridge`, `ops jobs`)

| op | what |
|---|---|
| `editor.describe` | engine, platform, python, RHI, project, open level, unsaved packages, idle cap, shader workers, memory, jobs |
| `editor.cvar(name, value=None)` | read a console variable, or set it and read it back (`changed`) |
| `editor.console(command)` | run a console command (refuses Fab.Logout, Fab.SetEnvironment, quit) |
| `editor.idle(fps=30, realtime=False)` | cap an offscreen editor between jobs |
| `editor.wait_compile(timeout_s, settle_s, finish)` | multi-tick: until no ShaderCompileWorker, then finish asset compilation |
| `editor.gc()` | collect garbage; memory before/after |
| `editor.epic_exchange_code(code)` | hand the MetaHuman services a single-use exchange code (never returned or journaled) |
| `editor.plugins(enable, disable, prefix)` | enabled plugins; turn plugins on/off in the .uproject (`restart_required`) |
| `editor.cvars(names, values, snapshot, restore)` | several cvars at once; a named snapshot to put them back later (survives a bridge reload) |
| `editor.project_setting(file, section, key, value)` | read/write Config/Default<file>.ini, comments and arrays untouched (`restart_required`) |
| `bridge.health` | the /health answer as an op |
| `jobs.list(state, name, limit)`, `jobs.get(id)`, `jobs.cancel(id)` | the bridge's jobs |

HTTP (what the client speaks): `POST /op`, `POST /exec` (`{"async": true}` returns the job id), `POST /batch`,
`GET /job?id=`, `GET /jobs?state=&name=&limit=`, `POST /job/cancel`, `GET /health`, `GET|PUT /file?path=`,
`GET /log?lines=`; `/screen` and `/gui` only on a Windows desktop. Every request carries the token from
`Saved/fmbridge.token` (compared in constant time). JSON requests are capped at 32 MB and a `PUT /file` at 4 GB
(413 above). `/file` paths must be absolute and inside the project, the temp folder or the editor user's home:
`FMBRIDGE_FILE_ROOTS` (os.pathsep-separated) adds roots, and anything else is 403.

### Plugins, console variables and project settings

```bash
film-ue op editor.plugins prefix=Movie                                # enabled plugins
film-ue op editor.plugins 'enable=["MovieRenderPipeline"]'            # .uproject; then: film-ue editor restart --wait
film-ue op editor.cvars 'values={"r.RayTracing": 0}' snapshot=pre      # change several, remember the old values
film-ue op editor.cvars restore=pre                                   # put them back
film-ue op editor.project_setting section=/Script/Engine.RendererSettings key=r.RayTracing value=True
```

### Several ops in one call

```python
client.batch([("level.spawn", {"label": "Key", "asset": "/Game/M/SM_Box", "loc": [0, 0, 50]}),
              ("look.light", {"label": "Key", "kind": "rect"})])
# {"ok", "result": {"ok", "ran", "of", "results": [{"ok", "i", "name", "result" | "code", "message", "hint", ...}]}}
```

The ops run in order as one job (plain ops back to back in one tick, a multi-tick one across ticks before the next).
The batch stops at the first failure unless `stop_on_error=False`, and takes at most 500 calls.

## 3. Transports and settings

| transport | commands | bridge | folders | for |
|---|---|---|---|---|
| `ssm` (default) | AWS-RunShellScript / RunPowerShellScript | SSM port-forward (or `--bridge ssm`: curl on the box per call) | through the box's S3 bucket | EC2 boxes we own |
| `ssh` | `sudo bash -s` / `powershell -Command -` over OpenSSH | `ssh -L` | rsync (Linux), scp (Windows) | a box someone else owns |
| `local` | a local shell | the bridge's own port | copies | the editor on this machine |

Settings live per profile in `~/.config/film-ue[.NAME].json` (`FILM_UE_CONF_DIR` moves them): `os`, `transport`,
`instance`, `region`, `ssh`, `ssh_key`, `user`, `service`, `project_dir`, `port`, `local_port`, `bucket`, `epic_s3`,
`project_s3`, `ddc_s3`, `engine_dir`. `film-ue set --KEY VALUE` writes them; `box up` writes a temporary box's.

## 4. Spec kinds

None: boxes and the editor are imperative on purpose (a TTL, a restart, a sync happen *now*).

## 5. Gotchas

- **Unsaved packages block a new-process render and a project upload.** The new-process MRQ executor asks to save
  first, and unattended that question waits forever (render.mrq refuses instead). `sync project up` refuses too.
  `editor.describe` lists them under `dirty`.
- **The first open of a project on a new box compiles ~13,700 shaders (~21 min on 8 cores).** `sync ddc restore`
  before the first start, `editor.wait_compile` before stills or renders, `sync ddc save` after.
- **An offscreen editor holds the GPU at full load between jobs** if its viewport stays realtime. The bridge idles it
  at start (30 fps cap, realtime off; MRQ lifts the cap while it renders).
- **"Use less CPU when in background" also stops rendering when the editor has no focus**, which a remote editor
  never has. `UEditorPerformanceSettings` is not exposed to Python by name, so the bridge sets the property on its
  defaults object found by path, using the C++ property name.
- **A blocking call holds the game thread**, and then nothing else runs (the old blocking `mh.rig` waited forever
  for a browser sign-in). Long work must be a generator. `bridge.health`'s `last_tick_s` shows a stuck thread, and
  the watchdog restarts an editor stuck past `--stall`.
- **A job that was running when the editor crashed is gone.** The journal only records jobs that finished or were
  cancelled cleanly. `client.wait` then raises `JobGone`: look at `film-ue editor crashes`.
- **`--once-args` values start with a dash:** write `--once-args="-A -B"`.
- **SSM caps one command near 100 KB.** `transport.put` sends bigger files in parts. Folders go by `push_dir`.
- **Fab reads an exchange code only from the command line, and only when its tab opens** (a desktop). Offscreen,
  use `epic-login --fab` (device code).
- **The exchange-code route uses Epic's launcher OAuth client outside the launcher** (§12c of
  docs/linux/engine.md). It is unofficial, so film-ue never holds the refresh token: your helper does. It is untested
  whether an exchange-code login leaves a saved sign-in. `epic-login` tells you which happened.

## 6. API_NOTES (UE 5.8.4 source, /srv/ue-src/UnrealEngine-5.8.4 on the source box; all verified tonight)

| API (Python) | source | note |
|---|---|---|
| `unreal.register_slate_post_tick_callback` | Plugins/Experimental/PythonScriptPlugin/.../PySlate.cpp:123 | the bridge's game-thread tick |
| `unreal.find_object(None, "/Script/UnrealEd.Default__EditorPerformanceSettings")` | PythonScriptPlugin/.../PyCore.cpp:2073 | the class is `UCLASS(minimalapi)` with nothing BlueprintVisible: Editor/UnrealEd/Classes/Editor/EditorPerformanceSettings.h:31 |
| `obj.set_editor_property("bThrottleCPUWhenNotForeground", False)` | PyWrapperObject.cpp:749-771 (FindEditorPropertyImpl: `Class->FindPropertyByName` on the real class) | property at EditorPerformanceSettings.h:74; effect EditorEngine.cpp:1807 (no rendering without focus), :5335 |
| `LevelEditorSubsystem.editor_set_viewport_realtime` | Editor/LevelEditor/Public/LevelEditorSubsystem.h:69 | idle cap |
| `t.MaxFPS` | Runtime/Engine/Private/UnrealEngine.cpp:12136 | idle cap |
| `SystemLibrary.execute_console_command` | Runtime/Engine/Classes/Kismet/KismetSystemLibrary.h:604 | editor.console, editor.cvar set |
| `SystemLibrary.get_console_variable_string_value` (+ float/int/bool) | KismetSystemLibrary.h:613 (:622, :631, :640) | editor.cvar read; "" for an unknown name |
| `SystemLibrary.collect_garbage` | KismetSystemLibrary.h:1823 | editor.gc |
| `SystemLibrary.get_engine_version` | KismetSystemLibrary.h:215 | health |
| `EditorLoadingAndSavingUtils.get_dirty_map_packages` / `get_dirty_content_packages` | Editor/UnrealEd/Public/FileHelpers.h:136 / :144 | editor.describe dirty |
| `UnrealEditorSubsystem.get_editor_world` | Editor/UnrealEd/Public/Subsystems/UnrealEditorSubsystem.h:49 | editor.describe level |
| `AutomationBlueprintFunctionLibrary.finish_loading_before_screenshot` | Developer/FunctionalTesting/Public/AutomationBlueprintFunctionLibrary.h:80 (impl .cpp:702: FAssetCompilingManager::FinishAllCompilation) | blocks until asset/shader compilation is done; called after the workers drained |
| `unreal.Paths.project_saved_dir / project_log_dir / get_project_file_path / convert_relative_path_to_full` | Runtime/Engine/Classes/Kismet/BlueprintPathsLibrary.h:173 / :284 / :391 / :519 (`ScriptName="Paths"`, :16) | |
| CVar `MetaHuman.Cloud.Config.ExchangeCode` | Plugins/MetaHuman/MetaHumanSDK/.../Cloud/MetaHumanCloudAuthentication.cpp:316 (Epic's own use: MetaHumanTDSUtils.cpp:131) | editor.epic_exchange_code |
| `-NoMetaHumanAccountPortalLoginFallback` | MetaHumanCloudAuthentication.cpp:262 | fail fast instead of a browser |
| `Fab.Login`, `Fab.Logout`, `Fab.SetEnvironment` | Plugins/Fab/Source/Fab/Private/FabConsoleCommands.cpp:28, :19, :43 | Logout and SetEnvironment delete the persistent auth |
| `FPlatformProcess::LaunchURL` → `/usr/bin/xdg-open URL` | Runtime/Core/Private/Unix/UnixPlatformProcess.cpp:712 | why `BROWSER=ue-epic-url` captures the device-code page on a box with no desktop |
| `PluginBlueprintLibrary.get_enabled_plugin_names` | Runtime/Engine/Public/PluginBlueprintLibrary.h:48 | editor.plugins |
| `PluginBlueprintLibrary.get_plugin_descriptor_file_path` | PluginBlueprintLibrary.h:74 | a bool UFUNCTION with an out parameter returns the out value, or None for false (PythonScriptPlugin/.../PyGenUtil.cpp:1161) |
| (no API enables a plugin) | — | editor.plugins edits the .uproject's "Plugins" list; the engine reads it at start |
| embedded Python 3.11 | Engine/Source/ThirdParty/Python3 (python_v3.11.x.tps) | no 3.12 syntax under unreal/ |

## 7. Selftest

`film-ue selftest platform` (`unreal/fmbridge/selftest/platform.py`) takes about a minute, or up to 30 on a first
open while shaders compile, and needs nothing. It proves:

- the bridge answers (protocol 2), ticks and runs unthrottled;
- `editor.describe` reports the engine, the RHI (Vulkan SM6 on Linux) and the level;
- a console variable round-trips and converges;
- the console refuses Fab.Logout and quit;
- the idle cap applies and converges;
- `editor.wait_compile` finishes;
- gc runs;
- a job runs across ticks with progress, is listed, is cancelled with its `finally` run, and is journaled;
- an unknown job is `not_found`;
- a failed job carries `code: bad_args` beside its traceback.

It passes on the fake engine (`tests/test_ue_platform_selftest.py`).

The client phase, `tools/filmtools/unreal/selftests/platform.py`, runs right after it and takes about a minute over
SSM:

- a 150 KB file round-trips through the bridge and through the command channel (in parts);
- a job started over HTTP reports progress, keeps answering after the tunnel is dropped, is listed and is
  cancelled;
- an unknown job is `JobGone`;
- a batch stops at its failing call and says why;
- the editor service status, the crash reports and a dry-run sync plan all answer.

It passes against the real server on the fake engine (`tests/test_ue_platform_client.py`).

Unit tests: `tests/test_fmbridge_jobs.py`, `test_ue_platform_*.py` (ops, client against the real server over HTTP,
profiles, boxes, watchdog, editor service, sync, CLI), `test_unreal_transport.py`, `test_unreal_linux.py`.

## 8. HANDOFF

**Done:** everything above, with every AWS call mocked. That includes:

- B12: editor.plugins, editor.cvars and editor.project_setting.
- B33: constant-time token, size limits, /file roots, /batch.
- B49: film-ue first-run.
- B54: box image, images, image-rm, and `box up --ami latest`.
- The client-phase selftest.
- The watchdog's on_exit, and `box up --save-ddc-on-exit`. Nothing in `boxes`/`sync`/`editorsvc` has run against AWS:
the operator's rule for the night.

**Run first on the next GPU box:** `film-ue --box NAME first-run` does the list below for you and stops with the
next command. In detail:

1. `box up` (check the user-data runs: `systemctl status ue-watchdog.timer film-ue-ttl.timer`, and
   `/etc/film-ue/watchdog.json`).
2. `provision`.
3. `sync ddc restore`.
4. `install`.
5. `selftest platform`.
6. `editor restart --wait`.
7. `sync epic status`.
8. `box status` (the watchdog's last decision).
9. Let it idle for `--idle` minutes on purpose: it must power off and terminate.

**Open / unverified:**

- the exchange-code route end to end, and whether it leaves a saved sign-in;
- `set_editor_property` by C++ name on the performance settings CDO (the source says yes; watch the log for "could
  not stop background throttling");
- Windows: `transport.put` in parts and `editorsvc` crashes through PowerShell are tested only as strings;
- `sync status` against a real bucket;
- spot interruption (the profile then finds nothing; `box ls` shows it).

**Left for the CLI owner (WP11), agreed:** cli.py's own `provision`/`editor`/`epic-login`/`desktop` go once this
branch is in ue-helpers (cli_platform then serves them; `editor` service verbs via opcli.EXTENSIONS). `install`
still lives in cli.py and sends the bridge in 80 KB printf parts (the lead's fix). It could use `transport.put` (parts
for both shells) when it moves here.

**Next ideas:**

- A Windows "editor start" through a scheduled task in the logged-in session.
- `install` moved here onto `transport.put`, so one code path serves both shells.
- `box image` on a schedule after a long session.
