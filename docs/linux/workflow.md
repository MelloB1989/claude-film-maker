# Unreal on Linux: the tooling and the code-only shoot workflow

Research note for moving the presenter reel's Unreal work (UE 5.8, `films/host-studio/`) from the Windows EC2
workstation to a Linux GPU instance. Sister notes: `engine.md` (engine features on Linux) and `cost.md` (instances,
prices, builds). Desk research and repo reading only: nothing here was run on a Linux box yet. Every claim carries a
source and a confidence (**confirmed** = read in the repo or an official page; **likely** = forum/third-party or
inferred from how the engine works; **unknown** = only a test or the engine source settles it).

**Scope (operator, 2026-11-04):** Unreal is driven **entirely by code**: scene building, camera moves, Sequencer keys,
stills and renders all come from scripts through the bridge (or another code path). Shooting by hand in the viewport
is out, so DCV, Pixel Streaming and latency from India matter only as an optional "look" path (section 6).

## Operator decisions (2026-11-04) — these override the hybrid-period parts below

- **Linux only, no hybrid period, no more Windows boots.** Section 5.3 (lease/sync between two boxes) and step 9 of
  the plan are dropped. If MetaHuman cloud rig/textures or voice-to-face cannot run on Linux, look for a code-only
  alternative rather than keeping Windows.
- **The project comes from an EBS snapshot** of the stopped workstation's volume, mounted read-only (ntfs-3g) on the
  Linux box (`setup.sh windisk` + `project-copy`). Its `Saved/MovieRenders` holds the Windows renders of the reel:
  the PoC compares Linux frames against them (same shots, frames, settings: `poc 4 --ref`).
- **Fab must work on Linux; one interactive Epic sign-in** by the operator is allowed, through a temporary remote
  screen: `film-ue desktop on` (Xorg on the GPU + VNC on the box's localhost, reached only through SSM), then
  `desktop off`. Everything else stays code-only.
- **Round 3 of the reel is rendered entirely on Linux.**
- Facts from the other tasks: the workstation runs UE **5.8.4** (Epic's installed build); the project is content-only
  (no C++, no project plugins; Content 3.7 GB); every MetaHuman plugin ships source with Linux branches; the Linux
  engine is built from tag 5.8.4-release (agent-02, agent-06).

**Code (written, untested on a box):** branch `fleet/agent-07/linux-workflow`, commit af0f9d6: the bridge import-safe
on Linux; `film-ue` with a Linux backend chosen per box (`--os linux`, `--box`); `film-ue provision | editor |
desktop`; `unreal/linux/` (setup.sh, the systemd unit, the launcher); `render.mrq(executor="process")`; the PoC runner
`film-ue poc 1..7` (`tools/filmtools/unreal/poc.py`); offline tests `tools/tests/test_unreal_linux.py`. The Windows
path is unchanged (Windows is still the default `os`).

**Still to change before round 3 runs on Linux:** the reel branches hard-code `C:\UEProjects\HostStudio` (e.g.
`films/host-studio/reel/render.py` `PROJECT`, `bodycheck.py`, `build.py`, `stills.py`, `shot.py`): replace with
`workstation.project("Saved", ...)`. Left to the reel branches' owners to avoid conflicts.

## PoC results (2026-11-04, one g6.4xlarge: 1x L4 24 GB, Ubuntu 22.04, driver 580.178.04-server, UE 5.8.4)

Run with `film-ue --box linux` and `poc.py` against agent-04's run sheet (`docs/linux/engine.md` §9 on
`fleet/agent-04/linux-engine`, where the verdicts are recorded). Outputs: `s3://<bucket>/ue-linux/poc/agent-07/`.

| Check | Result |
|---|---|
| P1 GPU, Vulkan, engine | PASS. Vulkan 1.4 with ray tracing; engine 5.8.4, the same changelist as Windows |
| P2 editor + bridge, no display | PASS. `-RenderOffscreen -unattended`, no `DISPLAY`, VULKAN_SM6 (this must be set in `[/Script/LinuxTargetPlatform.LinuxTargetSettings]`, or the editor uses SM5). First open: 13,729 shaders, 21.4 min on 8 workers. The DDC is kept in S3, so the next box starts warm |
| P3 stills, MRQ through the bridge | PASS. `seq.stills` and `look.still` work offscreen. PIE MRQ: 0.73 s per output frame at 1080p TSR x8 (Windows ≈0.9). The new-process executor never started a child: an unsaved level makes it ask to save, and nothing answers unattended. Fixed (`save_dirty`, fail fast) |
| P4 Lumen HWRT | Active (ProfileGPU shows `HardwareRayTracingCS`, hair BLAS updates). 88.7 ms GPU per temporal sample. The main cost is the virtual shadow maps at film quality (34 ms), not ray tracing. 30-min soak: see engine.md |
| P5 path tracer | FAIL on 24 GB. With strand hair in the BVH, VRAM reaches 22.5 GB and the Vulkan allocator crashes the editor. Without hair in the BVH it fits (7.2 GB), but the hair is gone. The denoiser (OIDN 2.3 via NNE) runs on CPU, ~2.4 s per frame |
| P6 frames vs Windows | PASS. S16: SSIM 0.998, crop colour ΔE ≤ 0.2. S15 (two presenters) from the shot start: SSIM 0.994–0.997. Rule: render chunks from the shot start (cloth needs its history), and report the first frame after a cut separately |
| P7 FBX | PASS. Static props with materials, a skinned garment on `metahuman_base_skel` in cm with a leader pose, and FBX export |
| P8 groom | Binding on a MetaHuman PASS. Alembic import not tested (no groom `.abc` was available) |
| P9 MetaHuman Creator | Preset, body, skin and wardrobe work. Build needs the cloud auto-rig, which needs an Epic sign-in |
| P11 audio to face | PASS. 0.11 s of solver CPU per second of audio (ORT on CPU), 366 frames, lips move |
| P10/P12 sign-in, Fab | BLOCKED. Xorg and VNC come up, but the editor cannot present to X with this driver setup (the EGL ICD swapchain crashes, the GLX ICD is incompatible), so there is nowhere to sign in. Next box: check `vkcube` on an X screen first |

Code changes from the PoC (on this branch): the bridge idles an offscreen editor (no realtime viewport, 30 fps cap)
and MRQ lifts the cap; `render.mrq` refuses the process executor with unsaved packages; `mh.rig` runs across ticks
with a timeout instead of blocking the game thread; `mh.build` raises when nothing was built; the VNC password is a
root-only file on the box.

## 0. Verdict

- **The bridge is already almost platform-neutral.** Of ~2,700 lines, the Windows-only parts are `fmbridge/gui.py`
  (SendInput/GDI/DCV, ~190 lines) and the operator-side transport in `tools/filmtools/unreal` (PowerShell over SSM,
  `Read-/Write-S3Object`, `C:\` paths). Every op in `fmbridge/ops/` uses only the `unreal` API and `os`, and runs
  unchanged on Linux as far as the code shows (confirmed, repo).
- **One hard break:** `fmbridge/__init__.py` imports `gui`, and `gui.py` calls `ctypes.windll` at import, so on Linux
  the whole bridge fails to start (confirmed, repo; agent-04 found the same). A five-line fix.
- **No desktop is needed in the target design**: a long-running `UnrealEditor -RenderOffscreen -unattended` under
  systemd with the bridge inside, reached through the same SSM port-forward. That this editor mode ticks Slate (so the
  bridge's post-tick runner works) and draws its level viewport (so `look.still`/`seq.still` work) is **likely**
  (Epic documents streaming the *full editor* rendered offscreen, marked experimental; BEDLAM runs the full
  `UnrealEditor -RenderOffscreen -vulkan -unattended -ExecCmds='py …'` with MRQ on GPU nodes, 5.3.2,
  https://github.com/ardithho/Unreal_Linux; one 5.8 user reports crash-free offscreen sessions: agent-04's `docs/linux/engine.md` on `fleet/agent-04/linux-engine`)
  but **not proven** for a long-running editor with the bridge: it is PoC 2. Try `SDL_VIDEODRIVER=offscreen` (5.8 is on
  SDL3) before any Xorg/Xvfb.
- **The fallback lane needs no change to the ops**: a headless Xorg on the NVIDIA GPU (virtual screen, no monitor),
  with the editor on `:0`. It keeps today's model (a desktop exists; `xdotool`/`import` replace SendInput/GDI).
- **Can be removed by code**: the DCV login that starts the editor (systemd), the scheduled task, the screen grab
  (engine-side capture), modal dialogs (`-unattended`, plus `assets.free` already on the reel branch). **Cannot yet
  be shown to be removable**: the Epic-account sign-in for Fab and for MetaHuman cloud services (auto-rig, texture
  synthesis). They are not needed to *shoot* a built scene, so during a hybrid period they stay on Windows.
- **Moving the project** needs no Windows boot: snapshot the stopped workstation's volume, attach a copy to the Linux
  box, mount NTFS read-only, copy `Content/`, `Config/`, the `.uproject` and `Plugins/` (if any). The derived data
  cache (shaders) is rebuilt once on Linux (Vulkan SM6), which can take a long time the first time.

## 1. What runs where today (from the repo)

```
operator's Mac / an agent                      EC2 Windows workstation (gr6.4xlarge, L4)
film-ue  ──aws ssm start-session (port-forward)──▶ 127.0.0.1:18765  fmbridge.server inside UnrealEditor
         ──aws ssm send-command AWS-RunPowerShellScript──▶ PowerShell as SYSTEM (token, file drops, S3)
         ──aws s3 sync ◀──▶ bucket ◀──▶ Read-S3Object / Write-S3Object (PowerShell AWS Tools)
operator ──NICE DCV──▶ console desktop; a scheduled task starts the editor after the DCV login
```

Sources: `tools/filmtools/unreal/{workstation,client,cli}.py`, `unreal/fmbridge/*.py`, `unreal/README.md` (all
confirmed). The scheduled task and the DCV-login dependency are **not in the repo**; they are only in the brief. To
read them next time the box is up: `film-ue` → `ws.ps("schtasks /query /fo LIST /v | Select-String -Context 0,30 Unreal")`
and `ws.ps("Get-ScheduledTask | ? TaskName -match 'Unreal|UE|Editor' | Select -Expand Actions")`.

**Exact engine patch (not recorded anywhere):** the bridge already reports it: `film-ue health` returns
`engine` = `unreal.SystemLibrary.get_engine_version()` (e.g. `5.8.x-<CL>+++UE5+Release-5.8`) (confirmed,
`unreal/fmbridge/server.py:257`). Without the editor: `Engine\Build\Build.version` under the engine install
(`ws.ps("Get-Content (Join-Path (Get-ItemProperty 'HKLM:\SOFTWARE\EpicGames\Unreal Engine\5.8').InstalledDirectory 'Engine\Build\Build.version')")`;
the registry key is the launcher's usual one, **likely**; fall back to
`C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat`). Record it in `unreal/README.md`: the Linux engine
must be the **same 5.8.x** (assets saved by a newer engine do not open in an older one).

## 2. Every Windows-specific piece, its Linux equivalent, effort

Effort: S = under an hour, M = half a day, L = a day or more (code only; PoC time is separate).

| # | Piece (repo path) | What it does on Windows | Linux equivalent | Effort | Confidence |
|---|---|---|---|---|---|
| 1 | `unreal/fmbridge/__init__.py` imports `gui`; `gui.py:11-13` `ctypes.windll`, `SetProcessDPIAware()` at import | loads input/screen code | import `gui` lazily (server.py already does per request) and pick a backend by `sys.platform`; a missing backend answers `/gui` with 501 | S | confirmed (repo) |
| 2 | `gui.py` SendInput/SetCursorPos (click, drag, type, keys) | drives the desktop for Fab and a few dialogs | **none** in the offscreen design (no desktop). Fallback lane (Xorg `:0`): `xdotool` (`mousemove`, `click`, `type`, `key ctrl+s`) or python-xlib XTest | none / M | likely |
| 3 | `gui.py` screenshot: `dcv.exe get-screenshot … console`, else GDI BitBlt | `/screen`, the desktop as PNG | offscreen: no desktop, so `/screen` becomes an **engine-side** capture of the active level viewport (`unreal.AutomationLibrary.take_high_res_screenshot` or `HighResShot`), which is what an agent needs anyway. Fallback lane: `import -window root` (ImageMagick) or `xwd`; with DCV on Linux, `dcv get-screenshot` exists too | M | likely; PoC 3 |
| 4 | `server.py:249` `allow_reuse_address = False` ("on Windows reuse lets a second server share the port") | prevents two bridges on one port | on Linux `SO_REUSEADDR` does **not** let two listeners share a port, but without it a quick restart fails with `EADDRINUSE` while old connections sit in TIME_WAIT. Set `allow_reuse_address = sys.platform != "win32"` | S | likely (POSIX socket semantics) |
| 5 | `server.py` paths via `unreal.Paths` (token, logs); `inbox.py` via `os.path` | — | already portable | none | confirmed |
| 6 | `workstation.ps()` → `AWS-RunPowerShellScript` (as SYSTEM, no desktop) | token read, file drops, S3, install fallback | `AWS-RunShellScript` (runs as root through the SSM agent). Ubuntu AMIs ship the SSM agent; the instance needs an IAM role with `AmazonSSMManagedInstanceCore` | S | confirmed (agent on Ubuntu: Canonical tutorial); likely (rest) |
| 7 | `workstation.put_text()` PowerShell `[IO.File]::WriteAllBytes` from base64 | small file writes (install, inbox) | `mkdir -p DIR && echo B64 \| base64 -d > PATH`; then `chown` to the editor's user (SSM runs as root) | S | likely |
| 8 | `push_dir` remote side `Read-S3Object -KeyPrefix … -Folder` | big folders up | `aws s3 sync s3://bucket/prefix DIR --only-show-errors` (AWS CLI v2 on the AMI) | S | likely |
| 9 | `pull_dir` remote side `Write-S3Object -Folder -Recurse` | renders back | `aws s3 sync DIR s3://bucket/prefix` | S | likely |
| 10 | `client.token()` `Get-Content '…\Saved\fmbridge.token' -Raw` | bridge token | `cat PROJECT/Saved/fmbridge.token` (or over the bridge's own `/file` once the tunnel is up) | S | likely |
| 11 | `cli.install()` joins `pd + "\\Content\\Python\\" + …`, `\Saved\Bridge\…`; `get()` uses `Test-Path`/`Get-Content` | copies the bridge in, restarts it via the inbox | a `remote_path(*parts)` helper using `PureWindowsPath` or `PurePosixPath` by the box's OS; `test -f && cat` | S | confirmed (repo) |
| 12 | `workstation.DEFAULTS["project_dir"] = r"C:\UEProjects\HostStudio"`; `cli.py` doc | project location | a per-box `os` + `project_dir` in `~/.config/film-ue.json` (e.g. `/srv/ue/HostStudio`) | S | confirmed |
| 13 | `workstation.password()` + `film-ue password` (`get-password-data`, `pbcopy`) | Administrator password for DCV | not needed (no desktop login). In the fallback lane with DCV, DCV on Linux authenticates a Linux user (PAM) | S (remove) | likely |
| 14 | the editor's start: a **scheduled task after a DCV login** (not in repo) | the editor needs a logged-in desktop | a **systemd unit** (`User=ue`, `Restart=on-failure`) running `UnrealEditor PROJECT.uproject /Game/Studio/Studio -RenderOffscreen -unattended -nosplash -NoLiveCoding -log`; `film-ue up` waits for SSM, then for `/health` | M | likely; PoC 2 |
| 15 | `films/host-studio/build.py:20,93`, `stills.py:17`, `shot.py:20`; reel branch `bodycheck.py:18` (and any other `C:\UEProjects\…` constants on `origin/fleet/agent-06-2/reel`, `origin/fleet/agent-13/reel-v2`) | remote paths for imports, stills, renders | read the project dir from `ws.conf()["project_dir"]` and join with `remote_path()`; never a literal drive path in film code | S–M | confirmed (repo grep) |
| 16 | NICE DCV (Windows server, console session) | the occasional look | optional only (section 6) | — | — |
| 17 | `gui.log_tail()` (in gui.py, used by `/log`) | log tail | portable code, but it lives in gui.py: move it to `server.py` so `/log` does not depend on the GUI module | S | confirmed |
| 18 | Linux file-name case sensitivity | — | UE resolves package names case-insensitively on Linux, but plain `os.path` in ops/films does not: a script that writes `…/saved/stills` vs `Saved` makes two folders. Grep shows the code uses `unreal.Paths` / one spelling; keep it that way | S (review) | likely |

**Not Windows-specific (no change):** all of `fmbridge/ops/*.py` (assets, level, look, mh, speech, anim, seq, render),
`init_unreal.py`, `inbox.py`, the multi-tick job runner, the SSM port-forward itself (`AWS-StartPortForwardingSession`
is OS-neutral on the target side), the S3 upload/download on the operator's side. The ops do depend on engine
features whose *Linux* availability is the engine note's subject; the ones that matter for this workflow are in
section 4.

Total code effort for a working Linux backend of `film-ue` and a Linux-safe bridge: **about 1.5–2 days**, plus the
PoC runs.

## 3. Code only, no desktop: how the editor runs on Linux

### 3.1 The modes Unreal offers (all from the command line)

| Mode | Command | Renders? | Bridge (long-running, multi-tick)? | Use |
|---|---|---|---|---|
| A. Editor, offscreen | `UnrealEditor P.uproject MAP -RenderOffscreen -unattended -nosplash` | yes (Vulkan, no window, no X) | yes, if Slate ticks offscreen (PoC 2) | **the target**: today's bridge, unchanged ops |
| B. One-shot editor script | `UnrealEditor-Cmd P.uproject -ExecutePythonScript=job.py -RenderOffscreen -unattended` | yes | no: exits when the script ends | batch jobs; fallback if A is unstable |
| C. Python commandlet | `UnrealEditor-Cmd P.uproject -run=pythonscript -script=job.py -unattended -nullrhi` | **no** (`-nullrhi`), no level loaded unless the script loads it | no | asset edits with no pixels: imports, material params, Sequencer keys, saves |
| D. MRQ as a game process | `UnrealEditor-Cmd P.uproject MAP -game -MoviePipelineConfig=/Game/…/Queue -RenderOffscreen -windowed -log` (or `-LevelSequence=… -MoviePipelineConfig=Preset`) | yes | no | final renders in their own process (frees the editor's memory; crash-isolated) |
| E. Headless Xorg on the GPU + editor on `:0` | `nvidia-xconfig --virtual=1920x1080 --use-display-device=None`, Xorg as a service, editor with `DISPLAY=:0` | yes | yes | **fallback lane**: a real (invisible) desktop; `xdotool` works; DCV console can attach |

Sources: `-ExecutePythonScript` and the `pythonscript` commandlet (confirmed: Epic, *Scripting the Unreal Editor
using Python*, https://dev.epicgames.com/documentation/unreal-engine/scripting-the-unreal-editor-using-python ;
the commandlet "does not automatically load levels"; Python exists only in the editor, not in `-game`).
`-RenderOffscreen` on Linux with no window manager and `-nullrhi` producing no frames (likely: forum,
https://forums.unrealengine.com/t/ue4-on-linux-from-ssh-with-no-display-but-with-gpu-and-rendering/156716 and
https://forums.unrealengine.com/t/rendering-in-headless-mode-possible/475619). The editor itself rendered offscreen
(likely, Epic documents it, "experimental and may be unstable": *Pixel Streaming in the editor*,
https://dev.epicgames.com/documentation/unreal-engine/pixel-streaming-in-editor, example
`UnrealEditor-Cmd … -RenderOffscreen -EditorPixelStreamingStartOnLaunch=true`). Epic's SDL "offscreen" video driver
for headless machines (confirmed it exists: https://www.phoronix.com/news/SDL-New-Vid-Driver-Offscreen; UE 5.7 moved
Linux from SDL2 to SDL3: MetaHuman/UE 5.7 notes, so the 5.8 behaviour is a PoC item). MRQ command line
(`-MoviePipelineConfig`, `-LevelSequence`, `-MoviePipelineLocalExecutorClass`) (likely: community tutorial
https://forums.unrealengine.com/t/community-tutorial-command-line-rendering-with-unreal-engine-movie-render-queue/681764
and https://forums.unrealengine.com/t/ue5-rendering-from-command-line-not-working-anymore/538400; settled in source
by `Engine/Plugins/MovieScene/MovieRenderPipeline/Source/MovieRenderPipelineCore/Private/MovieRenderPipelineCommandLine.cpp`).
Headless Xorg with a virtual screen on NVIDIA (likely: AWS re:Post DLAMI desktop article,
https://repost.aws/articles/ARpObQqWDSTFaHjaBIhddL2Q).

### 3.2 Recommended shape

- **One long-running editor (mode A)** under systemd, the bridge inside it, the level opened on the command line
  (removes the "Untitled level after a restart" trap). Everything agents do today keeps working: `film-ue op`,
  `exec`, multi-tick jobs, `seq.*`, `look.still`, `render.mrq` (PIE executor).
- **Final renders optionally as mode D**, started *by the bridge* (an op that saves the queue as an asset and spawns
  `UnrealEditor-Cmd … -game -MoviePipelineConfig=…` with `subprocess`, or MRQ's own
  `MoviePipelineNewProcessExecutor`, which does exactly that), so a crash in a long render does not take the editor
  down, and the editor stays free for the next shot.
- **Mode B/C** for jobs that need no live editor (bulk imports, re-keying after a level rebuild) when the box is
  started just for them.
- **Mode E** only if mode A fails PoC 2 or 3. Nothing in the ops changes between A and E; only `gui.py`/`/screen`
  and the systemd unit differ.

### 3.3 What still needs a display or a sign-in

| Need | Needs a display? | Needs a sign-in? | Removable by code? | Confidence |
|---|---|---|---|---|
| Build the scene, key Sequencer, cine cameras, materials, lights (all ops) | no (mode A) | no | — | likely (PoC 2) |
| Stills through a camera (`look.still`, `seq.still`, `seq.stills`: `take_high_res_screenshot` + `LSE.set_lock_camera_cut_to_viewport`) | needs a **level viewport**, which exists offscreen if Slate runs; otherwise render stills through MRQ (one-frame range) or a `SceneCapture2D` from the camera (agent-04's `docs/linux/engine.md` on `fleet/agent-04/linux-engine`) | no | yes (viewport-free still op as fallback) | unknown → PoC 3 |
| MRQ renders (PIE executor) | no (offscreen) | no | — | likely → PoC 4 |
| MRQ audio (`MoviePipelineWaveOutput`) | no, but needs an audio device: headless there is no PulseAudio; whether UE's SDL audio falls back to a null device, or `-nosound` drops the wav, must be tested | no | if broken: render the wav from the sequence's audio tracks outside UE (the reel already mixes in `films/host-studio/reel/sfx.py`/`score.py`) | unknown → PoC 4 |
| Modal dialogs (overwrite asset, save prompts, restore after crash) | they would block the game thread with no one to click | no | `-unattended` suppresses most; `assets.free` (reel branch) already avoids the overwrite dialog by code; keep "never export over an asset" as a rule | likely |
| Fab: add new Unreal-format assets | the Fab plugin's in-editor browser | **yes** (Epic account) | **unknown**: forum reports of the Fab plugin missing or failing on Linux (5.4–5.6), but a 5.8.2 Linux user got Epic's separate Fab plugin zip (unrealengine.com/linux, unzipped into `Engine/Plugins/Fab`) working after signing in again, and an Epic Launcher Preview for Linux exists since 2026-10-14 (agent-04's `docs/linux/engine.md` on `fleet/agent-04/linux-engine`). Still an interactive sign-in. Content already in the project moves with `Content/` and needs no sign-in | likely |
| MetaHuman cloud: auto-rig (`mh.rig`), texture synthesis (`mh.textures`) | no | **likely yes** (Epic account; the Windows editor got it from the launcher, which does not exist on Linux) | unknown; keep character *creation* on Windows during the hybrid period; *shooting* an already built MetaHuman needs no cloud call | unknown → PoC 6 |
| MetaHuman Creator editing (presets, body, wardrobe, build) on Linux | no | no (local) | — | likely: Creator supported on Linux since 5.7 (https://dev.epicgames.com/documentation/metahuman/metahuman-5-7-release-notes) |
| Audio to face (`speech.to_face`: `MetaHumanPerformance` with AUDIO input) | no | no | — | likely: MetaHuman Animator offline facial on Linux in 5.8 ("Offline and real-time facial MetaHuman Animator functionality available on Linux and macOS"; body animation Windows-only; https://dev.epicgames.com/documentation/metahuman/metahuman-5-8-release-notes-in-unreal-engine). 5.7 had *disabled* Identity and Performance asset creation on Linux, so this is new in 5.8 → PoC 5 |
| `gui.run` uses today: "Fab, some dialogs" (`unreal/README.md:36-37`) | — | — | Fab: no (above). Dialogs: yes (`-unattended`, `assets.free`). No film code on the three branches calls `client.gui` or `film-ue gui` (repo grep) | confirmed (repo) |

## 4. The shoot workflow on Linux, by code

The operator's "shoot" = once the scene is built: place cine cameras, key moves and cuts in Sequencer, check
previews, render. Today's ops already cover it; on Linux it is the same calls through the same tunnel.

```
agent (fleet container or Mac)                    Linux GPU box (no desktop)
film-ue up            ─ start EC2, wait SSM, wait /health (systemd started the editor)
film-ue install       ─ copy fmbridge (only after a change), restart it via the inbox
film-ue exec studio.py / op seq.new, seq.camera_cuts, seq.key_transform, look.camera, look.focus_track, anim.gaze_lock
film-ue op seq.stills (contact sheet frames) ─▶ pull_dir via S3 ─▶ contact sheet built locally (PIL) ─▶ agent looks
film-ue op render.mrq (preview: 960x540, temporal 1)  ─▶ pull_dir ─▶ ffmpeg proxy for review
film-ue op render.mrq (final) or render.process (mode D)  ─▶ pull_dir ─▶ grade/mix/encode locally
film-ue down          ─ stop it (costs by the hour)
```

Generic helpers worth building in claude-film-maker (not film-specific), in priority order:

1. **A Linux backend for `film-ue`** (`tools/filmtools/unreal/workstation.py`): an `os` setting per box, `run()`
   choosing `AWS-RunShellScript`/`AWS-RunPowerShellScript`, `remote_path()`, S3 transfer commands per OS, token read,
   `up` that waits for `/health`, `password` only on Windows. Also lets one `film-ue` drive both boxes in the
   hybrid period (`film-ue --box linux …`). (M)
2. **`unreal/linux/`**: the systemd unit, an `editor.sh` with the flags, a cloud-init/setup script for the AMI
   (NVIDIA driver, Vulkan loader, AWS CLI, SSM agent check, a `ue` user, the engine unpacked from S3, the project
   volume mounted) — so a box is reproducible from a script, not from a hand-set desktop. (M)
3. **`render.process`** op: MRQ in a separate `-game -RenderOffscreen` process from a saved queue asset, with progress
   read from its log/frames, plus `render.still` (one MRQ frame through a camera) as the display-free still. (M)
4. **`seq.contact`** helper on the operator side: frames from `seq.stills` pulled and tiled with labels (frame,
   camera, focal) in one call; today each film script does it itself (`films/host-studio/stills.py`). (S)
5. **`seq.shoot`**: a declarative shot list (camera, lens, focus target, start/end keys, cut frames) applied in one op
   on top of `seq.new`/`look.camera`/`seq.key_transform`/`seq.camera_cuts`, idempotent (re-running replaces the
   shot's keys), returning the cut list read back (`seq.cuts`). The reel's `films/host-studio/reel/shots.py`
   (branch `origin/fleet/agent-06-2/reel`) is the film-specific version to generalise. (M)
6. **`/screen` as an engine capture** (viewport → PNG) and **`/gui` returning 501 on Linux**. (S)
7. **`film-ue sync`** for the hybrid period (section 5.3). (M)

## 5. Moving the project and keeping two boxes in sync

### 5.1 What moves

| Folder of `C:\UEProjects\HostStudio` | Move? | Why |
|---|---|---|
| `HostStudio.uproject` | yes | lists plugins; check it has no `"Modules"` (C++): a C++ module would need a Linux build (unknown: read it) |
| `Content/` | yes | every asset, incl. MetaHumans, grooms, Fab content, `Content/Python` (the bridge, reinstalled anyway) |
| `Config/` | yes | project settings, plugin enablement, cvars. Check for `[/Script/WindowsTargetPlatform…]`-only settings that Linux ignores, and that `DefaultEngine.ini` targets SM6 on Vulkan for Linux (`[/Script/LinuxTargetPlatform.LinuxTargetSettings] TargetedRHIs`) |
| `Plugins/` | if present | project plugins; any with binaries need a Linux build |
| `Saved/` | no (except anything a script needs, e.g. imports already pushed) | logs, autosaves, the bridge token, stills: per box |
| `DerivedDataCache/`, `Intermediate/`, `Binaries/` | no | shaders and cooked data are per platform: Linux compiles its own (Vulkan SM6). **The first open compiles every shader** (MetaHumans, hair strands, Lumen): plan for a long first start, and keep the Linux DDC on the persistent volume so it is paid once |

**Size: unknown** (nothing recorded; the workstation's volume is 300 GB but holds Windows and the engine too). To read
it next time the box is up, over SSM:
`Get-ChildItem C:\UEProjects\HostStudio -Directory | % { "{0} {1:N1} GB" -f $_.Name, ((Get-ChildItem $_.FullName -Recurse -File | Measure Length -Sum).Sum/1GB) }`.

### 5.2 How (without booting Windows)

1. Snapshot the stopped workstation's root volume (it is stopped and preserved by the operator's rule; a snapshot
   does not change it), create a volume from the snapshot in the Linux box's AZ, attach it, mount read-only with the
   kernel `ntfs3` driver (`mount -t ntfs3 -o ro /dev/nvme1n1p? /mnt/win`; if the volume is flagged dirty, `-o ro,force`
   or `ntfs-3g -o ro`), `rsync -a` the folders above to the Linux project volume, detach, delete the copy volume and
   the snapshot. Confidence: likely (standard EBS + ntfs3 since Linux 5.15). Cost: snapshot storage for hours.
2. Or with the Windows box up: `Write-S3Object -Folder … -Recurse` (today's `pull_dir`) to a prefix, then
   `aws s3 sync` down on Linux. Same region, so transfer is fast and free between EC2 and S3 in-region.

Either way, **keep the Linux project on its own EBS volume** (not the root), so the instance type can change and
the volume can be snapshotted as the project's backup.

### 5.3 Hybrid period: two boxes, one project

`.uasset`/`.umap` are binary and cannot be merged, so the rule is **one writer at a time**:

- A **lease** object in the bucket (`s3://BUCKET/film-ue/HostStudio/LEASE.json`: box, since, by whom). `film-ue
  sync push` (from the box holding the lease) does `aws s3 sync Content Config s3://…/HostStudio/ --delete`
  (excluding `Saved`, `DerivedDataCache`, `Intermediate`); `film-ue sync pull` on the other box mirrors it down, then
  takes the lease. The editor must be **closed** (or the level saved and the bridge told to stop writing) during
  a sync; the systemd unit makes that a `systemctl stop`.
- What stays on Windows during the hybrid period: Fab additions, MetaHuman cloud rig/texture steps (if PoC 6 fails),
  anything needing the in-editor UI. What moves to Linux first: shooting and rendering (sections 3–4).
- **Both boxes on the same 5.8.x.** Never open the project in a newer engine first.
- Alternative: Perforce or git-LFS with file locking. More setup than a single operator needs now; the lease is
  enough for one writer and keeps S3 as the single store.

## 6. Looking at the editor (optional, not the workflow)

The workflow does not need eyes on the editor: agents read stills, contact sheets and preview renders. If the
operator wants a look from the Mac anyway:

- **Fallback lane (mode E) + Amazon DCV console session**: DCV on Linux supports a console session with direct GPU
  access, OpenGL without extra software; virtual sessions need `dcv-gl` and are OpenGL-oriented; Vulkan in DCV is
  not stated in the official session docs (confirmed for console/virtual; unknown for Vulkan:
  https://docs.aws.amazon.com/dcv/latest/adminguide/managing-sessions-intro.html). Needs the GRID driver (below). DCV
  on EC2 needs no licence (agent-05, `docs/linux/cost.md` on `fleet/agent-05/linux-cost`).
- **Editor Pixel Streaming** from the offscreen editor (mode A): Epic documents it, experimental; WebRTC to a browser;
  on Linux the default viewer port is 8080 (https://dev.epicgames.com/documentation/unreal-engine/pixel-streaming-in-editor).
  Reach it through the same SSM port-forward (signalling port), no inbound port. Memory growth over hours with
  `-RenderOffscreen` was reported on 5.0/5.4 (https://forums.unrealengine.com/t/renderoffscreen-startup-memory-issue-on-linux/1903757).

## 7. The GPU driver and Linux engine risks (overlap with engine.md)

- **Driver:** AWS documents GRID drivers for G6/Gr6 (L4) on Linux, with the step `NVreg_EnableGpuFirmware=0` for the
  G6 family (likely: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/nvidia-GRID-driver.html). Mode A needs only
  Vulkan on the device (no X). AWS lists Vulkan for the public datacenter (Tesla) driver on G4dn/G5/G6/Gr6/G6e
  (g6f/gr6f are GRID-only) (confirmed via agent-05's `docs/linux/cost.md`), so mode A can use the Tesla driver;
  mode E with Xorg/DCV wants GRID. **Default to the Tesla 580.x driver**: 580 is reported most stable (570 crashes
  with ray tracing, 595 hangs on modal dialogs/resize), and an Epic tech note (Aug 2026) covers a Vulkan-init crash
  with "licensed" drivers (an OpenSSL ABI clash) (agent-04's `docs/linux/engine.md` on `fleet/agent-04/linux-engine`).
  PoC 1 settles it with `vulkaninfo --summary` and the editor log's chosen device.
- **UE 5.8 on Linux has fresh reports**: an NVIDIA `VK_ERROR_DEVICE_LOST` crash at start (thread tagged fixed, fix
  not stated), Wayland/SDL3 explicit-sync crashes worked around with `SDL_VIDEODRIVER=x11`, AMD/Mesa black screens
  (https://forums.unrealengine.com/t/my-experience-unreal-engine-5-8-0-preview-on-linux/2721855,
  https://forums.unrealengine.com/t/ue-5-8-release-instant-vulkan-crash-vk-error-device-lost-on-linux-with-rtx-3090-ti-nvidia-driver/2729632).
  None is on an L4 headless; a server with no compositor avoids the Wayland class entirely. Use **≥ 5.8.2** (device-lost fix UE-385759) and preferably **≥ 5.8.3** (fixes a Linux-only Cinematic Viewport
  crash) (agent-04's `docs/linux/engine.md` on `fleet/agent-04/linux-engine`); the Windows project must then be on the same patch (step 0).
- **Engine binaries:** Epic's prebuilt Linux editor zip (download needs an Epic account login; Ubuntu 22.04, glibc ≥
  2.35: https://dev.epicgames.com/documentation/unreal-engine/linux-development-quickstart-for-unreal-engine) or a
  source build of the exact tag (the build task). Whether the zip carries MetaHuman Creator's core data and the
  MetaHuman plugins is **unknown** (on Windows it is a launcher option): check `Engine/Plugins/MetaHuman*` in the zip.

## 8. Migration plan, each step with the PoC that proves it

| Step | What | PoC that proves it (pass = …) | Box |
|---|---|---|---|
| 0 | Read the facts off the Windows box next time it is up: exact 5.8.x (`film-ue health`), project size by folder, `.uproject` modules/plugins, the scheduled task's command line | (no PoC; a 10-minute read over SSM) | Windows, already running for other work |
| 1 | Linux GPU box with driver + engine | **PoC 1**: `vulkaninfo` lists the L4; `UnrealEditor-Cmd -run=pythonscript -script="import unreal; print(unreal.SystemLibrary.get_engine_version())" -unattended -nullrhi` prints the same 5.8.x | temp EC2 (g6/gr6, Ubuntu 22.04) |
| 2 | Project copied from the snapshot; editor offscreen under systemd; bridge up | **PoC 2**: `systemctl start ue-editor`; `film-ue health` answers through the SSM tunnel; a multi-tick `exec` with 100 `yield`s completes (Slate ticks offscreen); first-open shader compile time recorded | same |
| 3 | Stills with no display | **PoC 3**: `look.still` and `seq.stills` on `/Game/Studio/Studio` produce PNGs identical in framing to the Windows ones (same camera, frame); if not, `render.still` via MRQ does | same |
| 4 | Renders | **PoC 4**: `render.mrq` (PIE) of 48 frames, deferred + Lumen, hair with `r.HairStrands.SkyLighting 0`; then the same via mode D; the wav is written; frame time vs Windows recorded | same |
| 5 | MetaHuman Animator audio solve on Linux | **PoC 5**: `speech.to_face` on a 10 s wav returns an animation with frames > 0 | same |
| 6 | Cloud + sign-in | **PoC 6**: `mh.rig` and `mh.textures` on a copy of a preset: do they run, or fail asking for a login? If login: is there a non-interactive path (an exchange code on the command line, as the launcher passes on Windows)? | same |
| 7 | Soak | **PoC 7**: editor up 2 h running a loop of stills + a render; RSS and VRAM stay flat (the `-RenderOffscreen` memory-growth report) | same |
| 8 | Tooling | Linux backend for `film-ue`, bridge fixes, `unreal/linux/` setup scripts (section 9); `film-ue up/install/health/exec/pull-dir` pass against the PoC box | code, then the PoC box |
| 9 | Hybrid | `film-ue sync` + lease; a change made on Linux (a key in a sequence) appears on Windows after `sync push`/`pull` | both |
| 10 | Cut over | Linux becomes the default box; Windows kept stopped for Fab/cloud until those are proven on Linux or no longer needed | — |

Fallback at step 2/3: switch the systemd unit to mode E (Xorg headless on the GPU) and rerun PoC 2–4.

PoC instance ask (for the orchestrator, when the engine exists): one **g6.4xlarge** (1×L4 as today, so frame
times compare; 16 vCPU, 64 GiB; Linux on-demand $1.589/h in ap-south-1 vs gr6.4xlarge $1.848/h, Windows gr6.4xlarge
$2.584/h, per agent-05 on 2026-11-04), Ubuntu 22.04, **root 100 GB + a 200 GB gp3 project/DDC volume**, **~4 hours**,
self-terminating; purpose PoC 1–7. Take gr6.4xlarge instead only if the editor with two MetaHumans tops 64 GiB
(PoC 2 records peak RSS). A g6.xlarge (16 GiB) is likely too small (unknown). Spot (g6.8xlarge ~$0.49/h) suits mode D
renders later, not the long-running editor.

## 9. Code changes (items 1, 2 (Windows/none split), 4 (process executor), 6–9 and 11 are done in af0f9d6; 3, 5, 10 remain)

Bridge (`unreal/fmbridge`):
1. `__init__.py`: stop importing `gui` at load. (S)
2. `gui.py`: split into `gui_win.py` (today's code) and `gui_x11.py` (xdotool/`import`, mode E only), picked by
   `sys.platform`; with neither available `/gui` answers 501 "no desktop". (S + M for X11)
3. `server.py`: `/screen` → desktop grab where there is one, else an engine viewport capture on the game thread
   (queued like an op); move `log_tail` here; `allow_reuse_address = sys.platform != "win32"`; `/health` adds
   `platform`, `offscreen` and the RHI in use (read from the editor log's RHI line; PoC 1 finds a cleaner source). (M)
4. `ops/render.py`: `render.process` (mode D) and `render.still` (one MRQ frame). (M)
5. `ops/seq.py`: `seq.shoot` declarative shot list (generalised from the reel's `shots.py`). (M)

Operator side (`tools/filmtools/unreal`):
6. `workstation.py`: `os` per box; `run()` (Shell/PowerShell); `remote_path()`; `put_text`, `push_dir`, `pull_dir`
   per OS; `password()` Windows-only; settings for several boxes (`--box`). (M)
7. `client.py`: `token()` through `run()`; nothing else. (S)
8. `cli.py`: `install()` with `remote_path()` and OS-neutral `get()`; `film-ue sync push|pull|lease`; `up` waits for
   `/health`; `--box`. (M)

Box setup (new `unreal/linux/`):
9. `ue-editor.service`, `editor.sh` (flags, env, the level), `setup.sh` (driver, Vulkan loader, AWS CLI, `ue` user,
   engine from S3, volume mount, `fstab`), a README. (M)

Film code:
10. `films/host-studio/{build,stills,shot}.py` and the reel branches' `C:\UEProjects\…` constants → `ws.conf()` +
    `remote_path()`. (S–M, on the reel branch owners' side to avoid conflicts)

Docs:
11. `unreal/README.md`: the Linux box, the flags, the traps found in the PoC, the exact engine version. (S)

## 10. Open questions only the operator can answer

1. During the hybrid period, is Windows kept for Fab additions and MetaHuman cloud rig/texture steps, or must those
   move too (which may be impossible headless if they need an Epic browser login)?
2. Will the Linux engine be Epic's prebuilt zip (someone must download it once with an Epic login and put it in S3)
   or a source build of the exact 5.8.x tag (the build task)?
3. Is an optional "look" path wanted at all (DCV on mode E, or editor Pixel Streaming), or are stills and preview
   renders enough?
4. May the PoC take an EBS snapshot of the stopped workstation's volume to copy the project (it does not change the
   instance or its volume)?
