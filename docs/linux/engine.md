# Can UE 5.8 on Linux do everything this pipeline does? (engine)

Task 20261104-task-can-ue-58-4639, desk research (2026-11-04). Companion reports: `cost` (agent-05) and `workflow`
(agent-07). PoCs already running: agent-06 builds 5.8 for Linux from source; agent-02 inventories the Windows box
(exact 5.8.x, `.uproject` plugin list) and copies the project to `s3://…/ue-linux/`.

Confidence: **C** confirmed (official doc / release note / Epic staff), **L** likely (user reports, older version,
or inference stated as such), **U** unknown. Sources are numbered at the end ([S1] …). Nothing here was run: every
**L** and **U** row has a PoC test in §9.

The operator's clarification shapes the whole report: Unreal is to be driven **entirely by code** (agents through the
bridge or another code path), never through the editor UI. "Shoot by hand" is out of scope; "shoot" below means
cameras, Sequencer keys and stills made by scripts.

## 1. Verdict

| Stage | Verdict | Why |
|---|---|---|
| **Render-only** (open the finished project, MRQ deferred + Lumen, write PNG/EXR + WAV) | **Feasible, likely.** No hard blocker. | Lumen, VSM, Nanite and MRQ run on Vulkan SM6 (C). `-RenderOffscreen` editors render on Linux GPU nodes with no desktop (L, 5.3 and one 5.8 report). Unproven: a 5.8 headless editor with no display server at all, the MRQ WAV with no sound device, and pixel parity of MetaHuman skin, eyes and groom with DX12. All three need a PoC. Path tracer and Lumen HWRT on Vulkan are **Experimental** (C), and the project renders with Lumen HWRT today (agent-02). Software Lumen is the fallback. |
| **Shoot by script** (Sequencer, cameras, keys, gaze lock, stills) | **Feasible, likely**, after one bridge fix and a new still path. | All the ops are plain editor Python; Python on Linux is documented (C). Today the bridge **cannot start on Linux** because `fmbridge/gui.py` touches `ctypes.windll` at import (repo fact). `look.still` and `seq.show` lean on an editor viewport (`take_high_res_screenshot`, lock-camera-to-viewport), and an offscreen editor may not have a usable one (U). MRQ-based stills are the fallback. |
| **Full** (MetaHuman Character editor, cloud rig + textures, build/assemble, audio-to-face) | **Plausible, not proven.** Two possible blockers. | Creator has run on Linux since 5.7. 5.8 claims "platform parity", assembly runs on Linux (with an OOM known issue), and MetaHuman Animator's offline facial solve is on Linux in 5.8 (C). Unproven: (a) the **Epic account sign-in** the cloud rig and texture services need, done inside a headless Linux editor (U); (b) **audio-to-face** on Linux. The docs don't name it, but the plugin files allow it: Speech2Face has no platform restriction and the ONNX runtime ships for Linux (L, strong; agent-02). The operator rules out a Windows fallback (2026-11-04): if either fails, use the code-only alternatives in §12a. |

**No hard blocker found.** Per the operator's rule, go straight to the PoC (§9).

## 2. What the pipeline touches (from the repo)

Read from `origin/anime/rain-ferry` plus the reel branches `origin/fleet/agent-06-2/reel` and
`origin/fleet/agent-13/reel-v2` (every `unreal.*` name used is listed in the appendix).

| Area | Where | Engine features / plugins |
|---|---|---|
| Bridge | `unreal/fmbridge/server.py`, `inbox.py`, `unreal/init_unreal.py` | PythonScriptPlugin (`init_unreal.py` auto-run, `register_slate_post_tick_callback`), a stdlib HTTP server on 127.0.0.1 |
| GUI | `unreal/fmbridge/gui.py` | **Windows only**: `ctypes.windll.user32/gdi32` SendInput + GDI grab, `C:\Program Files\NICE\DCV\…\dcv.exe get-screenshot` |
| Assets | `ops/assets.py` | AssetTools, EditorAssetLibrary, AssetImportTask, **FBX import** (`FbxImportUI`, skeletal/static), FBX export (`FbxExportOption`), texture import |
| Level | `ops/level.py` | EditorActorSubsystem, spawn, transforms, bone positions |
| Look | `ops/look.py` | MaterialEditingLibrary (materials built and **compiled** from Python), material instances, lights + **lighting channels**, SkyLight, ExponentialHeightFog, post-process, **CineCamera** (tracking focus), `AutomationLibrary.take_high_res_screenshot` (stills) |
| MetaHuman | `ops/mh.py` | **MetaHumanCharacter** plugin: `MetaHumanCharacterEditorSubsystem` (presets from Creator Core Data, `request_auto_rigging` = **cloud rig**, `request_texture_sources` = **cloud texture synthesis**, body constraints, skin, `build_meta_human` = assemble), wardrobe collections (grooms, clothing → Chaos Outfit / Cloth assets), RigLogic, ABP_Face |
| Speech | `ops/speech.py` | **MetaHuman Animator**: `MetaHumanPerformance` with `DataInputType.AUDIO`, `AudioDrivenAnimationMood`, `MetaHumanPerformanceExportUtils` (→ NNE / ONNX runtime), WAV import |
| Animation | `ops/anim.py` | AnimationLibrary (curves, keys, recompression), SkeletalMeshEditorSubsystem |
| Sequencer | `ops/seq.py` + reel scripts | LevelSequence, camera-cut, skeletal-animation, audio, float/double/colour/visibility/material/MPC tracks, `LevelSequenceEditorBlueprintLibrary` (open, set time, lock camera to viewport), TimeWarp |
| Render | `ops/render.py` | **Movie Render Queue**, PIE executor, deferred pass **or path tracer** pass, PNG/EXR/JPG + **WAV** output, AA samples, console variables (Lumen, VSM SMRT, hair MSAA, DOF, motion blur) |
| Hair | `films/host-studio/unreal/studio.py`, README | **Groom / HairStrands** (`GroomComponent`), `r.HairStrands.SkyLighting 0` in the editor and as a render cvar |
| Content | `unreal/README.md`, `films/host-studio/README.md` | **Fab** content (one-time sign-in done through the UI, `gui.py`), Blender-made props imported as FBX |
| Launch | `tools/filmtools/unreal/workstation.py`, `cli.py`, `client.py` | Windows: PowerShell over SSM, a scheduled task that starts the editor **after a DCV login**, `C:\` paths, SSM port-forward to 18765, S3 push/pull |

**The real project, read live by agent-02 (task 20261104-task-inventory-the-windows-f7e8, 2026-11-04 15:56 UTC):**

- Engine **UE 5.8.4**, Epic's binary installed build (`Build.version`: Changelist 58902052, CompatibleChangelist
  55116800, `++UE5+Release-5.8`). `.uproject` `EngineAssociation` is a launcher GUID
  `{1E2924D9-…}`; on Linux set it to `"5.8"` or register the new engine under that GUID.
- `HostStudio.uproject` is **content-only**: no `Source/`, no `Modules`, no project `Plugins/`, no `Binaries/`.
  Enabled plugins: MetaHuman, MetaHumanCharacter, MetaHumanCoreTech, MetaHumanAnimationTools, MetaHumanSDK,
  MetaHumanRuntime, MovieRenderPipeline, PythonScriptPlugin, EditorScriptingUtilities, SequencerScripting.
- **No Fab/Marketplace code plugins** (only Epic's Fab browser plugin v0.0.21 in the engine, which allows Linux and
  which the project does not need). All MetaHuman plugins are engine-bundled with full `Source/`. The `MetaHuman`
  plugin lists `SupportedTargetPlatforms` Win64, Linux, Mac. Build.cs files have Linux branches (`MetaHumanPlatform/
  Private/Linux`, RigLogic). Win64-only modules: `RigLogicEditor`, `RigLogicLibTest`, `MetaHumanCharacterUAFEditor`
  (experimental), and `MetaHumanCaptureSource`'s Media Foundation path (live capture, not used).
- `DefaultEngine.ini`: DX12 SM6, **`r.RayTracing=True`, `r.Lumen.HardwareRayTracing=True`**, Lumen GI + reflections,
  VSM, skin cache, TSR, no static lighting. **No Substrate** setting, so the project uses legacy materials. No Linux
  `TargetedRHIs` section, so Linux defaults to Vulkan SM6.
- Sizes: Content 3.7 GB (Host/ 3.2 GB), DerivedDataCache 1.2 GB (D3D, not reusable for shaders), Saved 14.5 GB
  (renders and autosaves, not needed on Linux).

Consequences: the project opens on Linux without code changes, and nothing in its plugin list is Windows-only. One
thing is **raised in priority**: today's renders use **Lumen hardware ray tracing**, which on Vulkan is Experimental
(P4). If it misbehaves, the fallback is `r.Lumen.HardwareRayTracing=0` (software Lumen), at the cost of a look change
to be checked in P6. `RigLogicEditor` is Win64-only, but **no MetaHuman module depends on it** (C, agent-02, read at 16:03 UTC). Across all
`Engine/Plugins` its only reference is `RigLogicDeveloper.Build.cs:37-38`, which loads it dynamically.

## 3. Feature matrix: Windows (DX12) vs Linux (Vulkan SM6), UE 5.8

"Win" is what the pipeline uses today; on Windows everything in this table works (repo fact).

| Feature | Linux 5.8 | Conf. | Source | PoC |
|---|---|---|---|---|
| Editor on Linux, precompiled | Yes: zips for 5.8.0, 5.8.1, 5.8.2 seen on unrealengine.com/linux (login + EULA; a EULA-loop bug since Sep 2026). 5.8.3/5.8.4 zips not confirmed | C / U | S1–S4 | — |
| Editor from source | Yes: `Setup.sh`, `GenerateProjectFiles.sh`, `make UnrealEditor`; clang 20.1.8, toolchain v26 | C | S7, S9 | P0 (agent-06) |
| Supported distros | Ubuntu 22.04, Rocky/RHEL 8+; glibc ≥ 2.28 (but 5.8.1's `libblake3_dotnet.so` needs 2.30; glibc < 2.35 makes dlopen slow) → use **Ubuntu 22.04** | C | S7, S10, S11 | — |
| RHI | Vulkan only (SM6 needed for Lumen, Nanite, VSM, PT); NVIDIA driver ≥ 570 | C | S10 | P1 |
| Lumen SW GI + reflections | Yes (SM6, RTX 2000+ class; L4/L40S/A10G are Ada/Ampere RTX-class) | C | S10 | P4 |
| Lumen HW RT, Hit Lighting | Yes, **Experimental**; may need engine-config edits (§7). **The project uses it today** (`r.Lumen.HardwareRayTracing=True`) | C | S13, HWRT doc | **P4** |
| Path tracer | Yes, Experimental on Vulkan (since 5.5); hair strands in the PT are experimental on every platform | C | S10, PT doc | P5 |
| PT denoiser | NNE denoiser (OIDN networks, GPU) is the default; platform list not documented | U | PT / NNE doc | P5 |
| Virtual Shadow Maps, Nanite | Yes (SM6 + `VK_KHR_shader_atomic_int64`) | C | S10 | P1 |
| Hair strands (groom) rendering | No Linux SM6 statement; strands worked in 5.0 Linux; MetaHuman hair renders in Linux Creator (5.7+) | L | forum 498241, S7 | P6 |
| MetaHuman skin / eyes / hair materials | No 5.8 DX12-vs-Vulkan comparison exists; one 2020 report of yellow Burley SSS on Vulkan | U | forum 471496 | P6 |
| Substrate | Supported on SM6 Linux ("platform testing incomplete"); default only for *new* 5.7+ projects. **Not used** by HostStudio (agent-02) | C | Substrate doc | — |
| MRQ deferred, PNG/EXR/JPG | Formats have no platform limit; MRQ on Linux used in practice (BEDLAM, 5.3) | L | export-formats doc, S12 | P3 |
| MRQ path-tracer pass | Same as PT above | L | — | P5 |
| MRQ WAV output | Experimental everywhere; on a box with **no sound device** the SDL backend may fail; 5.8 renders silence when no audio | U | forum, 5.8 notes | P3 |
| ProRes / DNx outputs | Probably Win/Mac only (not used by the pipeline) | U | — | — |
| MRQ from the command line | `-game -MoviePipelineConfig=…` and Python executors documented (Windows examples only) | C / L | MRQ CLI doc | P3 |
| Editor with `-RenderOffscreen`, no desktop | Works on Linux GPU nodes (5.3) and one 5.8 report; behaviour with no `DISPLAY` and the 5.8 SDL3 backend undocumented | L | S12, S15 | **P2** |
| Python editor scripting | Yes, Python 3.11.8, Linux paths documented | C | Python doc | P2 |
| `-ExecutePythonScript`, `-run=pythonscript` | Generic, not Linux-specific; `UnrealEditor-Cmd` exists on Linux | C / L | Python doc, forum 735536 | P2 |
| FBX import / export | FBX SDK `.so` ships for Linux; Interchange FBX uses it | L | forum 1334407 | P7 |
| Groom import (Alembic) + binding | No Linux statement; Creator depends on Groom and runs on Linux | L | MH plugin index | P8 |
| MetaHuman Character editor (presets, body, skin, wardrobe) | Yes since 5.7; 5.8 "platform parity" | C | S7, MH 5.7/5.8 notes | P9 |
| MetaHuman build / assemble | Yes (5.8 known issue: repeated assembly can OOM on Linux → add swap) | C | MH 5.8 known issues | P9 |
| Identity / conform-from-identity / depth | Not on Linux in 5.7 (DX12-only tracking); 5.8 unclear. **Not used** by the pipeline | C / U | MH 5.7 known issues | — |
| Cloud auto-rig + texture synthesis | Need an Epic account sign-in in the editor (an EOS overlay) + consent. Works on Linux? **Unknown**; flaky even on Windows (5.8.3 overlay bug, "Server Error") | **U** | forums 2542895, 2844451 | **P10** |
| MetaHuman Animator, offline facial | Yes on Linux in 5.8 (new); body animation Windows-only | C | MH 5.8 notes | P11 |
| Audio-to-face (`speech.to_face`) | Not named for Linux in the docs, but the code allows it. `MetaHuman.uplugin:109` declares `MetaHumanSpeech2Face` (Editor) with **no PlatformAllowList** and a Build.cs with no platform branches. `NNERuntimeORT.uplugin` allows **Win64, Linux, LinuxArm64, Mac** (Beta), and `Binaries/ThirdParty/Onnxruntime/Linux` (`libonnxruntime.so.1.24`) ships even in the Windows install (agent-02) | **L (strong)**: only running it proves it | MH 5.8 notes; agent-02's read of the 5.8.4 install | **P11** |
| RigLogic, assembled MetaHuman runtime | Yes (5.8 FP16 RigLogic on Linux) | C | 5.8 notes | P9 |
| Fab in the editor | Separate Linux plugin zip into `Engine/Plugins/Fab`; sign-in from the Fab window worked on 5.8.2 (one report); "Install from launcher" dead-ends for code plugins; Epic Launcher **Preview for Linux** since 14 Oct 2026 | L | forums, GamingOnLinux | P12 |
| Epic Games Launcher | Linux Preview (Oct 2026), engine install unreliable | L | GamingOnLinux | — |
| Creator Core Data (MH presets) | Launcher option or `Setup.sh` in a source build; a precompiled Linux zip may lack it | L / U | MH getting-started | P0 / P9 |

### 3a. Differences between 5.8.x patches that matter on Linux

| Patch | Date | What changed for Linux | Conf. |
|---|---|---|---|
| 5.8.0 | 2026-06-17 | `VK_ERROR_DEVICE_LOST` crashes on NVIDIA + AMD editors; SDL3 3.4.4; VULKAN_SM6 changes; dynamic rendering + async compute on | C |
| 5.8.1 | 2026-07-28 | 260+ fixes; regression: `libblake3_dotnet.so` needs glibc 2.30 (breaks RHEL 8) | C |
| 5.8.2 | 2026-08-25 | UE-385759 Vulkan device-lost fix | C |
| 5.8.3 | 2026-09-22 | "Linux-only editor crash when opening the Cinematic Viewport" fixed; MetaHuman sign-in overlay bug reported on Windows | C |
| 5.8.4 | 2026-10-20 | Mac/Linux crash on scripted Live Link Face ingest fixed; MRQ WAV crash with no audio fixed; Substrate PT specular fix; Lumen SceneCapture regression fix | C |

**Use 5.8.4 on Linux.** The Windows workstation runs 5.8.4 (agent-02, read live), so build tag `5.8.4-release` and
both platforms stay on the same patch.

## 4. Headless and code-only (the operator's priority 1)

The goal is no desktop, no DCV and no display server: an editor process with the bridge, driven over HTTP, and MRQ
renders started by code.

| Mode | What it gives | Linux status |
|---|---|---|
| **A. Long-running editor, offscreen**: `UnrealEditor Proj.uproject /Game/Studio/Studio -RenderOffscreen -vulkan -unattended -nosplash -stdout -log` (+ `init_unreal.py` starts fmbridge) | Everything the bridge does today, including MRQ with the PIE executor | L: BEDLAM runs the full editor this way with `-ExecCmds="py …"` on GPU nodes (5.3.2, S12); a 5.8 user runs `-RenderOffscreen` sessions with no crashes (S15). U: whether 5.8 (SDL3) starts with **no `DISPLAY` at all**. SDL has an `offscreen` EGL video driver that Epic contributed; `SDL_VIDEODRIVER=offscreen` is the first thing to try, `xvfb-run` the fallback (Xvfb is a few MB, needs no GPU and is not a desktop) |
| **B. One-shot Python**: `UnrealEditor-Cmd Proj.uproject -ExecutePythonScript=job.py -RenderOffscreen …` | A script runs, then the editor quits (or stays alive with `set_keep_python_script_alive`) | C (documented in general), L on Linux |
| **C. Commandlet**: `UnrealEditor-Cmd Proj.uproject -run=pythonscript -script=job.py` | Asset work without a level or rendering (imports, materials, MH assets?) | C in general; no world, no rendering, so no MRQ and no stills |
| **D. Command-line MRQ**: `UnrealEditor-Cmd Proj.uproject /Game/Map -game -LevelSequence=… -MoviePipelineConfig=… -RenderOffscreen -unattended` | A render with no editor UI, one process per job | C (doc), L on Linux; Movie Render Graph configs may need the Python route (5.5 reports) |
| `-nullrhi` | Starts with no GPU | Renders nothing: only for asset-only jobs |

What still needs a display or a person:

- **Epic sign-in** for the MetaHuman cloud services and Fab. Both are interactive overlays or web flows. Whether a
  login made once persists (EOS refresh token under `~/.config/Epic/…`) and is reused by a later offscreen editor is
  **U** (P10). If it isn't, the cloud rig and textures need a one-time interactive session (VNC/DCV on Linux, or do
  that step on Windows).
- **Fab downloads**: avoid the in-editor flow. Add Fab content once, then keep it in the project (it is ordinary
  `.uasset` content in `Content/`) and move it with the project through S3. No sign-in is needed again.
- **Modal dialogs**: an offscreen editor cannot show them, so they hang the game thread. Run with `-unattended`
  (suppresses most), and keep the existing code guards (`assets.free`, "never create over an existing asset" in the
  reel scripts; REEL_PERF.md notes the "Overwrite Existing Object" dialog).
- **Stills** (`look.still` = `take_high_res_screenshot`, `seq.show`/`seq.still` lock the camera to the editor
  viewport): an offscreen editor still has a level-editor viewport client in principle, but this is **U** (P2). The
  robust replacement is a one-frame MRQ render (already code) or a SceneCapture2D to a render target exported as
  PNG, neither of which needs a viewport.

## 5. Today's GUI dependencies and how code removes them (the operator's priority 2)

| Dependency | Where | Remove by code? |
|---|---|---|
| `fmbridge/__init__.py` imports `gui`; `gui.py` runs `ctypes.windll.user32` at import | `unreal/fmbridge/__init__.py:8`, `gui.py:21` | **Yes, required for Linux**: import `gui` lazily (`server.py` already imports it per request) and give `gui.py` a platform guard; on Linux `/screen` returns a render instead of a desktop grab and `/gui` returns "not supported" |
| DCV login, then a scheduled task starts the editor | `tools/filmtools/unreal/workstation.py` (Windows) | **Yes**: on Linux a systemd unit (or `film-ue up` over SSM `AWS-RunShellScript`) starts mode A; no login session |
| DCV/GDI screen grab | `gui.screenshot_png` | **Yes**: replace with a viewport-free still (MRQ one-frame or SceneCapture2D) |
| SendInput clicks for Fab and dialogs | `gui.run` | Fab: replaced by moving content with the project (above). Dialogs: `-unattended` + code guards. Sign-in: **maybe not** (P10) |
| Fab one-time sign-in | README | Not needed on Linux if the content is already in the project (L) |
| MetaHuman cloud sign-in | `mh.rig`, `mh.textures` | **U**: persistence of the EOS login is the open question (P10) |
| Editor log tail | `gui.log_tail` | Already plain file I/O: portable |
| `allow_reuse_address = False` (right on Windows, where reuse lets two servers share a port) | `unreal/fmbridge/server.py:249` | Not a GUI item, but on Linux a quick bridge restart hits `EADDRINUSE` (TIME_WAIT); set it True when `os.name != "nt"` (from agent-07) |

## 6. Getting the engine on Linux

Two routes. Prefer **source** for the long term, because it is scriptable, reproducible to the exact tag, carries
`Setup.sh`'s MetaHuman/Creator Core Data, and is not stuck behind a browser EULA.

- **Precompiled zip** (unrealengine.com/linux): about 39 GB zip, about 70 GB unpacked (5.8.1; S3). The download
  needs an Epic login + EULA in a browser and has a EULA-loop bug (S2, S4), so it can't be fetched by script.
  5.8.3/5.8.4 availability is unconfirmed. Whether MetaHuman plugins and Creator Core Data are inside is U
  (`unzip -l … | grep -E 'MetaHuman|PythonScriptPlugin|Fab'`). The Fab plugin is a separate zip.
- **From source** (agent-06's PoC): see §6a for the fast-build plan.

**Do not cook.** An editor-only build is enough; the pipeline renders inside the editor.

### 6a. Fast build plan (target 15–20 min)

See §10. In short: a 15–20 minute **compile** is plausible on 192 physical cores; the **whole run** (clone,
dependencies, compile, archive) is more like 35–55 minutes. That is an estimate: no public 192-core Linux benchmark
exists, so the first run must time it.

### 6b. Does a Windows project open as-is on Linux?

| Item | Answer | Conf. |
|---|---|---|
| Content (`.uasset`/`.umap`) | Platform-independent; opens as-is | C (general engine design) / L for this project |
| Shaders | **All recompile** for `SF_VULKAN_SM6`; the Windows DDC holds PCD3D shaders. Expect a long first open (MetaHuman + groom + Lumen); keep the Linux DDC (`DerivedDataCache/` or a Zen/shared DDC) on the persistent disk or in S3 | L |
| Texture/mesh DDC | Platform-independent entries could be reused through a shared DDC; simplest is to let Linux build its own once | L |
| `DefaultEngine.ini` | Add `[/Script/LinuxTargetPlatform.LinuxTargetSettings] +TargetedRHIs=SF_VULKAN_SM6`; stale Windows RHI lines have broken startup for some users | L |
| C++ in the project | **None**: HostStudio is content-only (agent-02), so nothing to compile; the bridge is Python | C |
| Plugins with `PlatformAllowList` Win64 only | **None enabled by the project** (agent-02's plugin list, §2); only `RigLogicEditor` among MetaHuman's modules is Win64-only (risk noted in §2) | C / U |
| `EngineAssociation` | A launcher GUID; set `"5.8"` or register the Linux engine under the GUID (`~/.config/Epic/UnrealEngine/Install.ini` `[Installations]`) | C (agent-02) / L (Linux registry file) |
| Path case | Linux is case-sensitive; references in assets are fine, but external file paths in scripts must match case (and drop `C:\`) | L |
| Pixel parity with DX12 | Not guaranteed (Epic confirms Vulkan/DX12 differences, e.g. SingleLayerWater); compare stills (P6) | C |

### 6c. GPU drivers on AWS (Linux)

| Claim | Conf. | Source |
|---|---|---|
| AWS: Tesla (public), GRID and gaming drivers all support Vulkan on G5 (A10G), G6 (L4), G6e (L40S) | C | AWS install-nvidia-driver |
| Tesla driver: no licence, no X needed; NVIDIA: with `DISPLAY` unset the Vulkan loader enumerates GPUs headless | C | AWS, NVIDIA forum 222832 |
| GRID driver: needs no licence server on AWS (AMIs or S3 bucket); Epic tech note (2026-08): **crash at Vulkan init with "licensed" Vulkan drivers** (OpenSSL ABI mismatch), plausibly GRID/vGPU | C (note exists) / U (scope) | forum 2746187 |
| Gaming driver: needs `gridd.conf` + a cert file; meant for one display | C | AWS |
| Driver branch: 580.x reported most stable for UE 5.6–5.8 (570 crashed with RT, 595 hangs on resize / modal dialogs) | L | S14, S15 |
| RT extensions (`VK_KHR_ray_tracing_pipeline`, `ray_query`, `acceleration_structure`) on L4/L40S/A10G headless | L (RT cores; NVIDIA exposes them since 460) | — |

**Default:** Ubuntu 22.04 + NVIDIA **Tesla (public) driver 580.x**, no X server. Try GRID only if Tesla fails.
Datacenter vs GRID matters for licensing and for the OpenSSL tech note, not for features.

## 7. Known 5.8 Linux bugs that could bite

| Bug | Workaround | Conf. |
|---|---|---|
| `VK_ERROR_DEVICE_LOST` editor crashes (5.8.0) | Fixed in 5.8.2 (UE-385759); also `r.Vulkan.EnablePipelineLRUCache=1`, `r.Vulkan.AllowAsyncCompute=0`, `-norhithread` | C |
| Modal dialogs hang / colour-picker crash ("outdated swapchain", driver 595) | Driver 580; rebuild with `VULKAN_USE_IMAGE_ACQUIRE_FENCES 0`; offscreen avoids swapchains | L |
| Wayland + NVIDIA explicit-sync kills the editor | `SDL_VIDEODRIVER=x11` (irrelevant offscreen) | L |
| `-RenderOffscreen` memory growth (5.0–5.4) | Restart the editor between big jobs; watch RSS (P2) | L (old) |
| OpenSSL ABI crash with licensed Vulkan drivers | Use the Tesla driver, or the tech note's fix | C / U |
| Repeated MetaHuman assembly exhausts RAM (OOM kill) | Add swap | C |
| Linux-only Cinematic Viewport crash | Fixed in 5.8.3 | C |
| Packaged Linux 5.7.4 crash on MetaHuman `M_fabric_simpler` cloth material (NVVM compile) | Check in P6 (clothing material) | L |
| EXR WorldDepth/WorldNormal differ from Windows with 32-bit output | Not used by the pipeline (PNG beauty) | L |
| 5.8.1 glibc 2.30 requirement | Ubuntu 22.04 | C |
| Vulkan "gets less development traffic"; Linux memory management lags (Epic staff) | Prefer the larger-VRAM GPU (L40S 48 GB) if L4 (24 GB) runs out | C |

Possible conflict to settle in P4/P5: the 5.5 release notes say Vulkan RT is on by default and at parity with DX12,
but the 5.8 HWRT page says to enable Vulkan ray tracing by editing `Engine/Config/VulkanPC/DataDrivenPlatformInfo.ini`
(`[ShaderPlatform VULKAN_SM6]`: `bSupportsRayTracingShaders`, `bSupportsPathTracing`, `BindlessSupport`) and
`BaseLinuxEngine.ini`. Check those keys in the 5.8.4 tree (source item S-1 below).

## 8. Exact engine-source items to check (once the source is readable)

- S-1 `Engine/Config/VulkanPC/DataDrivenPlatformInfo.ini` `[ShaderPlatform VULKAN_SM6]`: RT, path tracing and bindless defaults.
- S-2 (**settled by agent-02**: no platform restriction on Speech2Face; no MetaHuman dependency on RigLogicEditor) `Engine/Plugins/MetaHuman/**/MetaHuman.uplugin` and `MetaHumanCharacter*.uplugin`: `PlatformAllowList` of the
  Speech2Face / audio-driven modules and the cloud-service (auth) modules.
- S-3 (**settled by agent-02**: Linux allowed, Linux onnxruntime binaries present) `Engine/Plugins/NNE/NNERuntimeORT/NNERuntimeORT.uplugin` and `Binaries/ThirdParty/Onnxruntime/Linux`.
- S-4 `Engine/Plugins/Runtime/HairStrands/HairStrands.uplugin` (Alembic groom importer on Linux).
- S-5 `Engine/Plugins/Media/AppleProResMedia`, `AvidDNxMedia` `.uplugin` (not needed; only for completeness).
- S-6 `git tag --contains 11c1d64a…` (Epic's device-lost commit) for 5.8.x.
- S-7 MetaHuman cloud auth: the EOS login code under `Engine/Plugins/MetaHuman/MetaHumanCharacter/…` (persisted
  refresh token? device-code or exchange-code flow usable without an overlay?).

## 9. Proof-of-concept tests: plan, status and verdicts

GO on 2026-11-04. The box is `i-0573d4267ace3d9cc` (agent-06 brings it up); agent-07 runs the tests, one editor at
a time; agent-04 owns this table and the verdicts. The engine is 5.8.4 from agent-06's source build; the project is
copied from the workstation snapshot (§9a).

**Each result report should include:** the exact command or op call; the engine and driver versions (`nvidia-smi`,
`Build.version`) once; the log lines named in "Evidence"; output paths on the box or in S3; and numbers (times,
sizes, metrics). A test without its evidence stays **pending**.

| # | Test | Pass if | Evidence to report | Status |
|---|---|---|---|---|
| P0 | Source build 5.8.4 (agent-06) | editor, ShaderCompileWorker and plugins built; `Engine/Plugins/MetaHuman/MetaHumanCharacter/Content/Optional/Presets` present (else copy it from the snapshot's engine) | build times, archive path, `ls` of Presets | pending |
| P1 | `DISPLAY= vulkaninfo`, grep RT, `shader_atomic_int64`, `mesh_shader` | all present on the L4 | the grep output, `nvidia-smi` | pending |
| P2 | Editor on the copied project, bridge auto-starts: `film-ue health`, `exec`, `look.still`, `seq.still`; RSS every minute for 2 h | `RHI=Vulkan`, `SM6`; bridge answers; stills are correct images; RSS flat | launch line; log `LogRHI`/`LogVulkanRHI` lines; still PNGs; RSS series; which display mode (rule D1) | pending |
| P3 | `render.mrq` deferred PNG+WAV on a 24-frame chunk of one reel shot, through the bridge; then the same job via command-line MRQ (`UnrealEditor-Cmd … -game -MoviePipelineConfig=… -RenderOffscreen`) | frames written; the command-line job also works (needed for `film-ue render`) | frame dir, s/frame, `LogMovieRenderPipeline` errors, WAV length and peak | pending |
| P4 | Same chunk with the project's Lumen **HWRT** as is; then a 30-min soak | log shows ray tracing enabled; no `VK_ERROR_DEVICE_LOST`; image sane | `LogRayTracing`/`LogVulkanRHI` lines, soak duration, crash count | pending |
| P5 | `render.mrq path_tracer=True`, 8 frames | non-black, denoised | NNE runtime log line, frames | pending |
| P6 | Reel calibration chunks vs the Windows PNGs of the same frames (`s3://rf-render-788655295054-aps1/ue-linux/reference/reel_1080p/<shot>/NNNN.png`: the 1,599 frames the final cut used, plus `reference/cut.json`), with exactly render.py's settings (§9a.5), after the face-mode check (§9a.6) | rule D5 | per-frame SSIM/PSNR, crop colour deltas, contact sheet path | pending |
| P7 | `assets.import` an FBX prop (static + skeletal), then export | imported with materials | asset paths, log | pending |
| P8 | Groom `.abc` import + binding to a MetaHuman | binding builds and renders | asset paths, a still | pending |
| P9 | `mh.from_preset` → `mh.body` → `mh.skin` → `mh.add_item` → `mh.build` (swap on) | BP built, placed, renders | BP path, still, peak RSS | pending |
| P10 | `mh.rig` + `mh.textures`: offscreen first; if a sign-in is needed, the operator signs in once (Xvfb + VNC), restart offscreen, run again | rig and hi-res textures arrive; login survives the restart | log `LogMetaHumanAuth`/`LogEOSAuth`, `has_high_resolution_textures` | pending (needs the operator) |
| P11 | `speech.to_face` on one reel line, mood as REEL_PERF | animation exported, frames > 0, plausible lip-sync (one-frame-per-word check or a short MRQ) | anim path, frames, `LogNNE` runtime line, timing | pending |
| P12 | Fab plugin (source, from the snapshot's engine) built in; the operator signs in; add one free asset | asset lands in `Content/` and renders | asset path, log | pending (needs the operator) |

### 9.1 Decision rules (agreed before the results, so the verdicts are not argued after)

- **D1 Display mode.** Try in this order and keep the first where P2 passes in full: (1) no `DISPLAY` with
  `-RenderOffscreen`; (2) `SDL_VIDEODRIVER=offscreen` with `-RenderOffscreen`; (3) `xvfb-run -s "-screen 0 1920x1080x24"`
  (Xvfb is a few MB, needs no GPU and no desktop, so it still counts as code-only); (4) headless Xorg on the L4.
  Rendering must use the NVIDIA GPU in every mode (check `LogVulkanRHI` names the L4, not llvmpipe).
- **D2 Stills.** If `look.still`/`seq.still` fail or come out black with no viewport, do not block: replace them with
  a one-frame MRQ still op (a helper to build, §11) and go on with P3.
- **D3 Hardware Lumen.** If P4 shows RT disabled, first check the VULKAN_SM6 `DataDrivenPlatformInfo.ini` keys (§7)
  and r.RayTracing in the log. On device lost: `r.Vulkan.EnablePipelineLRUCache=1`, then `r.Vulkan.AllowAsyncCompute=0`,
  then driver 580 ↔ 595. If it is still unstable or wrong, use **software Lumen** (`r.Lumen.HardwareRayTracing 0`)
  for Round 3, provided P6 shows it acceptable (all of Round 3 is on Linux, so consistency within Round 3 is what matters).
- **D4 Audio.** The reel's sound is mixed outside Unreal (`films/host-studio/reel/audio/mix/`), so a silent MRQ WAV
  is **not a blocker**: note it and drop `MoviePipelineWaveOutput` from Linux renders if it misbehaves.
- **D5 Image check (P6).** A sanity check, not a pixel match (Round 3 is Linux-only). Fail if structural: missing or
  white hair, black or wrong eyes, grey or yellow skin SSS, missing shadows, flicker, a neutral face. Otherwise pass
  if full-frame SSIM ≥ 0.90 against the Windows frame of the same number (provisional: calibrate on the first chunk
  by also comparing two adjacent Windows frames) and crop mean colour differs by ≤ 3 ΔE. A larger but uniform
  colour shift passes with a note (it's a grade).
- **D6 Performance.** No pass/fail: record s/frame vs Windows for agent-05. If Linux is more than 2× slower, look at
  shader compilation in the first frames (exclude warm-up) and at HWRT vs SW Lumen before blaming Vulkan.
- **D7 MetaHuman cloud (P10).** If the login does not persist, Round 3 still passes (it needs no cloud call, §12a);
  record that new characters need an interactive session per rig request.

### 9a. The PoC under the operator's decision (no Windows boots; project from an EBS snapshot)

The operator decided there will be no more Windows boots. The project comes from an EBS snapshot of the stopped
workstation's root volume (agent-02), mounted read-only with `ntfs-3g` on the Linux GPU box. Linux renders are
compared with the existing Windows renders of the reel. Steps:

1. **Mount.** Create a volume from the snapshot in the box's AZ, attach it, and run `mount -t ntfs-3g -o ro …`. A
   Windows volume left hibernated or with fast startup on refuses a read-write mount, but read-only is fine.
2. **Read the facts from the disk, not a live Windows.** This settles open items in minutes:
   - `C:\Program Files\Epic Games\UE_5.8\Engine\Build\Build.version`: expect 5.8.4, CL 58902052, so build tag
     `5.8.4-release`.
   - Under `Engine/Plugins/MetaHuman/` and `Engine/Plugins/NNE/`, run `grep -rn RigLogicEditor --include=*.Build.cs
     --include=*.uplugin`. This shows whether MetaHuman Character editing needs the Win64-only module (§2).
   - Read the `.uplugin`/`Build.cs` of the audio-to-face module (`Speech2Face`/`AudioDriven*`) and of
     `NNERuntimeORT` for Linux branches and `PlatformAllowList`. This settles S-2 and S-3 of §8 without the private
     GitHub source.
   - `Engine/Plugins/MetaHuman/MetaHumanCharacter/Content/Optional/` holds the **Creator Core Data** (presets,
     wardrobe, grooms). The content is platform-independent, so if the Linux source build lacks it, copy it from
     here into the Linux engine's same path (L; P9 checks).
3. **Copy the project to ext4, not run from NTFS.** The editor writes `Saved/`, `Intermediate/` and
   `DerivedDataCache/`; ntfs-3g is slow, and the mount is read-only anyway. Run `rsync -a
   /mnt/win/UEProjects/HostStudio/ /data/HostStudio/` excluding `Saved/`, `Intermediate/` and `DerivedDataCache/`
   (Windows D3D shaders, useless on Vulkan). Content is 3.7 GB. Then set `.uproject` `EngineAssociation` to `"5.8"`
   or register the Linux engine under the GUID.
4. **Reference frames:** use `s3://…/ue-linux/reference/reel_1080p/<shot>/NNNN.png` (uploaded from the Mac: all 13 shots, exactly the frames the final cut used, with `cut.json`). The snapshot copy below is only a fallback. Old note: `Saved/MovieRenders/reel_1080p/<shot>/<master frame>.png` is 8.5 GB,
   so no copy from the Mac is needed. Fall back to `out/host-studio/reel/` on the Mac for anything missing. ProRes
   is not a reference: it is a lossy re-encode, so compare against the PNG frames.
5. **Render exactly as Windows did.** `films/host-studio/reel/render.py` (reel branches) drives
   `render.mrq(sequence=/Game/Reel/SEQ_Reel, level=/Game/Studio/Studio, width=1920, height=1080, temporal=8,
   spatial=1, warmup=32, start=shot.start-4 (PREROLL), end=shot.end, cvars={r.HairStrands.SkyLighting: 0})` plus
   `render.QUALITY_CVARS`, deferred pass, PNG. The only change needed is `PROJECT = r"C:\UEProjects\HostStudio"` →
   the Linux project dir (better: `unreal.Paths.project_saved_dir()` on the editor side, which is generic). Start
   with a calibration chunk per shot type (`--frames 24`), not whole shots.
6. **Check the level state before the first render.** REEL_PERF.md notes that a face which "is neutral, or blinks but
   does not speak" means `drive_face` did not persist. Run `mh.components` on each presenter and expect
   `ANIMATION_SINGLE_NODE` on the Face components. If the saved level lacks it, run the reel's drive step first.
   Otherwise a "Linux difference" would really be a scene-state difference.
7. **Compare.** Lumen, TSR and temporal sampling are not bit-deterministic even on the same machine, so do not
   expect identical pixels. Per frame, compute PSNR/SSIM and a mean-colour delta for skin, eyes, hair and clothing
   crops, and make a side-by-side contact sheet. Pass if no structural difference (missing hair, black eyes, wrong
   SSS, missing shadows, flicker) and a small, uniform colour delta. If hardware Lumen fails on Vulkan, re-render
   with `r.Lumen.HardwareRayTracing 0` and report the look delta separately.
8. **Time it.** Record seconds per frame (render.py prints `s_per_frame`) next to the Windows numbers for the same
   shots, for agent-05's cost model.

Order on the box: P1, then P2 (editor offscreen with the bridge on the copied project), then steps 5–8 (= P3, P4,
P6), then P5, then P9–P11 (MetaHuman, which needs the sign-in, so last). P7, P8 and P12 only as needed.

## 10. Build appendix (fast source build)

Desk research for agent-06's build PoC (20261104-task-build-the-ue-08c2). Their measurements replace these estimates.

**Instance** (x86_64 only: there is no Linux ARM64 editor host; L):

| Type (ap-south-1) | Cores / RAM | $/h on-demand | Note | Conf. |
|---|---|---|---|---|
| c8i.96xlarge | 192 cores (384 vCPU) / 768 GiB | 17.99 | fastest; in Mumbai since Jan 2026 | C (region) / L (price) |
| m8a.48xlarge | 192 physical cores (no SMT) / 768 GiB | U in Mumbai (11.69 in us-east-1) | in Mumbai since Jun 2026 | C / U |
| c7i.48xlarge | 96 cores (192 vCPU) / 384 GiB | 8.57 | cheapest big one; probably 1.5–2× slower | L |

The vCPU quota for standard on-demand instances must allow the chosen size (384 for c8i.96xlarge). RAM: UBT budgets
1.5 GiB per action by default (`MemoryPerActionBytes`); 2 GiB/vCPU is enough. **Disk**: one gp3 volume of 500 GiB,
16k+ IOPS, 1,000+ MiB/s (peak tree about 200–300 GB; with 384–768 GiB of RAM most I/O hits the page cache). OS: Ubuntu 22.04.

**Steps** (estimated time each):

1. Packages (`build-essential git curl zstd`, AWS CLI), `ulimit -n 1048576`: 2–3 min.
2. Source: `git clone --depth 1 --single-branch --branch 5.8.4-release` (about 2.5 GB), or the tag tarball from the
   GitHub API piped into `tar`. Setup.sh does not need `.git`. Confirm the tag with `git ls-remote --tags`: 2–4 min.
3. `./Setup.sh --force --threads=64 --exclude=Win64 --exclude=WinArm64 --exclude=Win32 --exclude=Mac --exclude=osx64
   --exclude=IOS --exclude=TVOS --exclude=VisionOS --exclude=HoloLens --exclude=LinuxArm64 --exclude=Android`
   (`--dry-run` first gives the size). It also fetches the v26 clang 20.1.8 toolchain. 4–10 min (U). Check afterwards
   that the MetaHuman Creator Core Data / presets (`/MetaHumanCharacter/Optional/Presets`, used by `mh.presets`) are
   present. If not, find where the source tree gets them (U).
4. `~/.config/Unreal Engine/UnrealBuildTool/BuildConfiguration.xml`: `bAllCores=true` (the default is one action per
   *physical* core), `bAllowUBAExecutor=false` and `bAllowUBALocalExecutor=false` (UBA on Linux is marked
   unsupported and broke ISPC headers in 5.5), `bDisableDumpSyms=true`; optionally `bDisableDebugInfo=true` (faster,
   smaller, no symbols).
5. A single UBT call so all targets share one queue: `Engine/Build/BatchFiles/Linux/Build.sh -Target="UnrealEditor
   Linux Development" -Target="ShaderCompileWorker Linux Development" -Target="InterchangeWorker Linux Development"
   -Target="UnrealPak Linux Development"`: **15–35 min (the main unknown)**. `GenerateProjectFiles.sh` and `make` are
   not needed. Do not use the BuildGraph "Installed Build" route: it also compiles game targets and a DDC.
6. Smoke test: `UnrealEditor-Cmd -nullrhi -unattended -nosplash -ExecCmds=quit`: 1–3 min.
7. Archive: `tar -I 'zstd -T0 -3' --exclude=.git --exclude='*/DerivedDataCache'` streamed to the **private** bucket
   (`ue-linux/`). Keep `Engine/Intermediate` (generated headers, UBT makefiles). Excluding `*.debug` roughly halves the
   size but loses callstacks. Estimated 40–80 GB compressed. Also take an **EBS snapshot** for fast EC2 restores
   (lazy-loading unless a provisioned initialization rate of 100–300 MiB/s or Fast Snapshot Restore is used). An AMI adds little over a snapshot: 5–10 min.

ccache/sccache: UBT 5.8 has no setting for them, and a cache cannot help a one-shot build (L). Rebuilding is avoided
by keeping the result instead.

The archive must never be public: the EULA allows sharing engine code only with other licensees (L).

The first run should record: total action count and the parallelism UBT chose, wall time per step, peak RAM and
disk throughput (`/usr/bin/time -v`, `vmstat`, `iostat`), the single-threaded tail (final links), the Setup.sh
download size, `du` of Binaries/Intermediate/Plugins and of `*.debug`, and the compressed archive size.

Alternative with no build: Epic's precompiled `Linux_Unreal_Engine_5.8.x.zip` (about 39 GB; 5.8.4 not confirmed on
the page; download needs a browser login).

## 11. Generic helpers worth building in claude-film-maker

These are generic, not film-specific, and worth building only once P2 and P3 pass:

1. **A cross-platform `fmbridge`**: lazy `gui` import, a Linux `gui` backend (screen = an offscreen render; input
   = unsupported), path handling without `C:\`. Small, and needed for anything on Linux.
2. **A Linux backend for `film-ue`** (`tools/filmtools/unreal/workstation.py`): SSM `AWS-RunShellScript` instead of
   PowerShell; start and stop the editor as a systemd unit in mode A; `film-ue install` copies into
   `Content/Python` as today; health reads the log over SSM. The client, tunnel and S3 code stay as they are.
3. **`film-ue render` as one process per job** (mode D): command-line MRQ from a saved queue or config, so long
   renders don't depend on the editor session, with frames pushed to S3.
4. **A viewport-free still op**: a one-frame MRQ or SceneCapture2D, replacing `take_high_res_screenshot` for agents.
5. **Engine and DDC caching**: the built engine and the Linux shader DDC as S3 artefacts, restored at boot.
6. **Scripted shot helpers** (camera rigs, dolly/orbit keys, lens/focus pulls, shot lists to Sequencer) on top of
   `seq` and `look`. These are platform-independent and agent-07's workflow report covers them.

## 12. Operator answers (2026-11-04)

1. **Epic login**: yes, the operator's own Epic account. The operator logs in once, interactively, through a temporary
   remote screen when the PoC reaches P10/P12. Everything else stays code-only. For that session only: run the editor
   on a virtual display (`Xvfb :1` + `x11vnc`, or NICE DCV for Linux) instead of `-RenderOffscreen`. Afterwards,
   restart the editor offscreen and test whether the login **persists** (EOS keeps a refresh token in the user's
   config dir; U). If it does not persist, every MetaHuman cloud request needs a new interactive session, which
   makes the code-only alternatives below more important.
2. **Hybrid**: no. Linux only. If something fails on Linux, look for code-only alternatives (§12a).
3. **Fab**: new Fab content must work on Linux, so P12 is in scope.
4. **Round 3** of the reel will be rendered entirely on Linux. There is no mixing, so the DX12-vs-Vulkan comparison
   (P6, §9a) is there to catch errors (missing hair, wrong skin), not to match Windows to the pixel.

### 12a. Code-only alternatives if a MetaHuman service fails on Linux

| Need | If it fails on Linux | Code-only alternative | Conf. |
|---|---|---|---|
| Characters that already exist | — | Round 3 re-renders an existing reel: the built characters, rigs and textures are assets in `Content/` (from the snapshot) and need **no** cloud call again. Cloud rig and textures matter only for **new or reshaped** characters | C (repo: `mh.rig`/`mh.textures` save results into the assets) |
| Cloud auto-rig (`mh.rig`) | Sign-in or service fails | No real substitute for a new face. Epic's **MetaHuman DNA Calibration** (DNACalib: Python/C++, prebuilt for Linux, open) edits an existing DNA rig by code (joints, blend-shape deltas, LODs), but it does not create a rig from a new mesh, and its docs say it is compatible with MetaHumans from UE ≤ 5.5. Mitigation: start new characters from presets that are already rigged and keep edits within what the rig tolerates. A one-off cloud rig through the operator's interactive session is the fallback | L |
| Cloud textures (`mh.textures`) | Same | The Creator synthesizes standard-resolution skin textures locally (agent-02 saw `texture_synthesis` in `MetaHumanCoreTechLib` source), so the character works without the high-res set at lower texture detail. Check `has_high_resolution_textures` and the look in P9 | L |
| Audio-to-face (`speech.to_face`) | Audio solve unavailable on Linux | **NVIDIA Audio2Face-3D**: SDK (C++/CUDA) and UE plugin open-sourced in Sept 2025. Core components are MIT; the model weights are under NVIDIA's open model licence. It runs on Linux. Run it **outside the editor** on the GPU box (wav → ARKit-style blend-shape / MetaHuman curves per frame), then write the curves into an AnimSequence with the existing `anim` ops. That is engine-version-independent, unlike its UE plugin (5.5/5.6). Needs a PoC: quality vs MHA, mapping to the MetaHuman face rig, licence of the weights for the operator's use | L |
| Fab content | In-editor Fab browser fails or needs clicks | The Fab plugin ships **with source** and allows Linux (agent-02), so it compiles into the source-built engine. Login: the operator's one interactive session. Adding assets is UI-driven: either during that session, or by porting `fmbridge/gui.py` to Linux (xdotool + an X screenshot under Xvfb), which brings back the Windows box's `/gui` and `/screen`. Content once added is plain `Content/` and moves with the project | L / U |

## Sources

- S1 5.8 release thread: https://forums.unrealengine.com/t/unreal-engine-5-8-released/2729274
- S2 EULA loop (5.8.2 zip): https://forums.unrealengine.com/t/cant-download-unreal-for-linux-eula-accept-page-is-stuck-in-an-infinite-accept-loop/2763968
- S3 5.8.1 zip size: https://forums.unrealengine.com/t/storage-required-to-install-unreal-engine-5-8-1/2740177
- S4 Linux download loops to EULA: https://forums.unrealengine.com/t/linux-precompiled-download-loops-to-eula-after-successful-acceptance/2764062
- S5 hotfixes: [5.8.1](https://forums.unrealengine.com/t/5-8-1-hotfix-released/2738864), [5.8.2](https://forums.unrealengine.com/t/5-8-2-hotfix-released/2746335), [5.8.3](https://forums.unrealengine.com/t/5-8-3-hotfix-released/2833315), [5.8.4](https://forums.unrealengine.com/t/5-8-4-hotfix-released/2842775)
- S6 Linux quickstart: https://dev.epicgames.com/documentation/en-us/unreal-engine/linux-development-quickstart-for-unreal-engine
- S7 5.8 release notes: https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-8-release-notes
- S8 Linux download page: https://www.unrealengine.com/linux
- S9 Building from source: https://dev.epicgames.com/documentation/en-us/unreal-engine/building-unreal-engine-from-source
- S10 Linux requirements: https://dev.epicgames.com/documentation/en-us/unreal-engine/linux-development-requirements-for-unreal-engine
- S11 RHEL 8 glibc: https://forums.unrealengine.com/t/crash-when-opening-or-packaging-a-project-on-5-8-1-linux-rhel8/2746210
- S12 BEDLAM Linux pipeline (headless editor + MRQ on GPU nodes, 5.3.2): https://github.com/ardithho/Unreal_Linux
- S13 5.5 release notes (Vulkan RT parity): https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-5-release-notes
- S14 Nanite RT crash / driver testing: https://forums.unrealengine.com/t/nanite-raytracing-crash-when-creating-a-new-viewport-after-scene-load/2723779
- S15 forum threads (forums.unrealengine.com/t/…): 2729632 (5.8 device lost, UE-385759, `-RenderOffscreen` report), 2730532 (modal hang), 2721855 (5.8 preview), 2720975 (Vulkan/DX12 parity, Epic staff), 2746187 + tech note https://dev.epicgames.com/community/learning/knowledge-base/RxpX
- S16 AWS NVIDIA drivers: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/install-nvidia-driver.html, …/nvidia-GRID-driver.html, …/nvidia-gaming-driver.html
- Hardware RT: https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-ray-tracing-in-unreal-engine
- Path tracer: https://dev.epicgames.com/documentation/en-us/unreal-engine/path-tracer-in-unreal-engine; NNE denoiser: https://dev.epicgames.com/documentation/en-us/unreal-engine/nne-denoiser-in-unreal-engine
- Substrate: https://dev.epicgames.com/documentation/unreal-engine/overview-of-substrate-materials-in-unreal-engine
- MRQ export formats: https://dev.epicgames.com/documentation/unreal-engine/cinematic-rendering-export-formats-in-unreal-engine; MRQ command line: https://dev.epicgames.com/documentation/en-us/unreal-engine/using-command-line-rendering-with-move-render-queue-in-unreal-engine
- Python scripting: https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python; Linux pip paths: https://dev.epicgames.com/documentation/unreal-engine/python-plugin-dependency-management-for-unreal-engine
- `-RenderOffscreen` on Linux: forums 156716, 1903757 (memory growth), 136834 (segfault); `UnrealEditor-Cmd` on Linux: 735536
- SDL offscreen driver: https://www.phoronix.com/news/SDL-New-Vid-Driver-Offscreen
- NVIDIA headless Vulkan: https://forums.developer.nvidia.com/t/headless-vulkan-with-multiple-gpus/222832
- MetaHuman: 5.6 Windows-only https://forums.unrealengine.com/t/ue-5-6-metahuman-character-creator-linux-support/2541069; 5.7 notes https://dev.epicgames.com/documentation/metahuman/metahuman-5-7-release-notes; 5.7 known issues https://dev.epicgames.com/documentation/metahuman/known-issues-5-7; 5.8 notes https://dev.epicgames.com/documentation/metahuman/metahuman-5-8-release-notes-in-unreal-engine; 5.8 known issues https://dev.epicgames.com/documentation/metahuman/metahuman-known-issues-5-8-in-unreal-engine; hardware https://dev.epicgames.com/documentation/metahuman/metahuman-hardware-requirements-in-unreal-engine; plugin index https://dev.epicgames.com/documentation/en-us/unreal-engine/API/PluginIndex/MetaHumanCharacter and …/PluginIndex/MetaHuman
- MetaHuman cloud sign-in: https://forums.unrealengine.com/t/error-not-logged-in-5-6/2542895; 5.8.3 overlay bug https://forums.unrealengine.com/t/ue-5-8-3-metahuman-create-full-rig-epic-sign-in-overlay-doesnt-respond-to-clicks-login-fails-with-eos-invalidauth/2844451; server errors https://forums.unrealengine.com/t/metahuman-auto-rig-fails-with-server-error/2734187
- NNERuntimeORT: https://dev.epicgames.com/documentation/en-us/unreal-engine/API/PluginIndex/NNERuntimeORT
- Packaged Linux MetaHuman cloth crash: https://forums.unrealengine.com/t/crash-with-5-7-4-and-linux-ubuntu-when-using-metahuman-characters/2714858
- Groom import: https://dev.epicgames.com/documentation/en-us/unreal-engine/importing-grooms-into-unreal-engine
- Fab on Linux: https://forums.unrealengine.com/t/how-to-get-assets-from-fab-into-my-project-on-linux/2692390, https://forums.unrealengine.com/t/solved-fab-on-linux/2149608; Launcher preview: https://www.gamingonlinux.com/2026/10/epic-games-launcher-preview-arrives-native-linux-support-fortnite-for-linux-is-coming-and-upgraded-easy-anti-cheat/
- FBX on Linux: https://forums.unrealengine.com/t/unable-to-build-4-27-2-from-source-on-linux/1334407
- Headless audio: https://forums.unrealengine.com/t/can-t-render-wav-in-runtime/2161606, https://forums.unrealengine.com/t/urgent-audio-cannot-be-heard-in-pixelstreaming-using-linux-container/1219926
- Engine version: `Engine/Build/Build.version` (MajorVersion/MinorVersion/PatchVersion/Changelist), https://dev.epicgames.com/documentation/unreal-engine/versioning-of-assets-and-packages-in-unreal-engine; `unreal.SystemLibrary.get_engine_version()` is what `film-ue health` already reports (`unreal/fmbridge/server.py:257`)

## Appendix: `unreal.*` API used by the pipeline (all three branches)

ARFilter, Actor, ActorComponent, AddNewSubobjectParams, AnimationCurveIdentifierExtensions, AnimationLibrary,
AnimationMode, AssetEditorSubsystem, AssetExportTask, AssetImportTask, AssetRegistryHelpers, AssetToolsHelpers,
AudioDrivenAnimationMood, AutomationLibrary, AutomationUtilsBlueprintLibrary, CameraComponent, CameraFocusMethod,
CollectionScalarParameter, DataInputType, DirectionalLightComponent, EditorActorSubsystem, EditorAssetLibrary,
EditorLoadingAndSavingUtils, EditorPerformanceSettings, ExponentialHeightFogComponent, Exporter, FbxExportOption,
FbxImportUI, GameplayStatics, GroomComponent, KismetMaterialLibrary, LevelEditorSubsystem, LevelSequence,
LevelSequenceEditorBlueprintLibrary, LevelSequenceEditorSubsystem, LightingChannels, MaterialEditingLibrary,
MaterialExpression*, MaterialInstanceConstant, MaterialInstanceDynamic, MaterialParameterCollection,
MetaHumanCharacterAutoRiggingRequestParams, MetaHumanCharacterEditorBuildParameters,
MetaHumanCharacterEditorSubsystem, MetaHumanCharacterTextureRequestParams, MetaHumanDefaultPipelineType,
MetaHumanPaletteItemKey, MetaHumanPerformance, MetaHumanPerformanceExportUtils, MetaHumanPerformanceFactoryNew,
MetaHumanQualityLevel, MetaHumanRigType, MoviePipelineAntiAliasingSetting, MoviePipelineConsoleVariableSetting,
MoviePipelineDeferredPassBase, MoviePipelineDeferredPass_PathTracer, MoviePipelineExecutorJob,
MoviePipelineImageSequenceOutput_{EXR,JPG,PNG}, MoviePipelineOutputSetting, MoviePipelinePIEExecutor,
MoviePipelineQueueSubsystem, MoviePipelineWaveOutput, MovieScene{Audio,CameraCut,Color,ComponentMaterial,Double,Float,
MaterialParameterCollection,SkeletalAnimation,Visibility}Track, MovieSceneTimeWarpVariant, PerformanceExportRange,
SkeletalMeshEditorSubsystem, SkyLightComponent, SubobjectDataBlueprintFunctionLibrary, SubobjectDataSubsystem,
SystemLibrary, UnrealEditorSubsystem, and the core math/struct types.

Sources added for §12a: NVIDIA Audio2Face-3D open-sourcing (https://gigazine.net/gsc_news/en/20250926-nvidia-audio2face-open-sources,
https://huggingface.co/nvidia/Audio2Face-3D-v2.3-Mark/blob/main/README.md, https://build.nvidia.com/nvidia/audio2face-3d/modelcard);
MetaHuman DNA Calibration (https://github.com/EpicGames/MetaHuman-DNA-Calibration,
https://dev.epicgames.com/documentation/metahuman/metahuman-dna-calibration-tools).
