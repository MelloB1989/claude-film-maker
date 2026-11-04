# Windows workstation inventory (for the Unreal-on-Linux PoC)

Everything below was read live from the workstation (`i-00cf16306340d73c9`, gr6.4xlarge, ap-south-1, Windows Server
2022, NVIDIA L4) on 2026-11-04 over SSM, with PowerShell running as SYSTEM. There was no DCV login and no editor.
The scripts are in this folder (`inventory.ps1`, `inventory-part2.ps1`, `mh-thirdparty.ps1`, `mh-buildcs.ps1`,
`content-list.ps1`, `agent04-checks.ps1`, `copy-to-s3.ps1`). They ran through `runps.py`
(`filmtools.unreal.workstation.ps`). Their raw output is in `inventory-raw/` (1–6, with one Android file-server token
redacted), along with the copy manifest.

Timeline (UTC): `film-ue up` 15:55:14, running 15:55:16 → inventory 15:56–16:03 → S3 copy 15:59:32–~16:01:45
(about 109 s on the instance) → `film-ue down` 16:03:06 → **stopped 16:09:10** (6 min in "stopping"). Uptime was
about 14 min. After that, at the orchestrator's request, I took snapshot **`snap-00f13e5427f61953a`** of the root volume
`vol-0a651e8b82c4a1e42` (300 GB gp3, `/dev/sda1`), tagged `Project=ue-linux-poc`, started 16:09:16.

## 1. Engine

`C:\Program Files\Epic Games\UE_5.8\Engine\Build\Build.version`:

| Field | Value |
|---|---|
| MajorVersion.MinorVersion.PatchVersion | **5.8.4** |
| Changelist | **58902052** |
| CompatibleChangelist | 55116800 |
| BranchName | `++UE5+Release-5.8` |
| IsPromotedBuild / IsLicenseeVersion | 1 / 0 |

**Install type: Epic's installed binary build, not a source build.** The evidence: `Engine/Build/InstalledBuild.txt`
is present, there is an `.egstore/` with three `.manifest` files, `C:\Program Files\Epic Games\Launcher` exists, and
there is no `.git` and no `Setup.bat`. `LauncherInstalled.dat` has an empty `InstallationList`. The `.uproject`'s
`EngineAssociation` is the GUID `{1E2924D9-4D5E-D1CF-3589-2F99FB2B567D}`, not `"5.8"`, and Administrator's
`HKCU\Software\Epic Games\Unreal Engine\Builds` maps that GUID to `C:/Program Files/Epic Games/UE_5.8`. A Linux
engine therefore needs either `EngineAssociation` changed to `"5.8"` or the new engine registered under the same GUID
(`~/.config/Epic/UnrealEngine/Install.ini [Installations]`).

The editor starts from the scheduled task `\OpenHostStudio` (Administrator, Interactive, Highest), which runs
`C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe C:\UEProjects\HostStudio\HostStudio.uproject`
with no extra flags. A second task, `\UEClick`, runs `powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy
Bypass -File C:\ue-setup\click.ps1`; that is the desktop-click helper `film-ue gui` uses.

## 2. Project `C:\UEProjects\HostStudio`

`HostStudio.uproject` (FileVersion 3, "Tech-explainer host studio"):

- **No `Modules`, no `Source/`, no project `Plugins/`, no `Binaries/`: the project is content-only (Blueprint).** Nothing
  needs compiling for Linux on the project side.
- Plugins it enables: `MetaHuman` (with SupportedTargetPlatforms Win64, Linux and Mac), `MetaHumanCharacter`,
  `MetaHumanCoreTech`, `MetaHumanAnimationTools`, `MetaHumanSDK`, `MetaHumanRuntime`, `MovieRenderPipeline`,
  `PythonScriptPlugin`, `EditorScriptingUtilities` and `SequencerScripting`.
- Levels: `/Game/Studio/Studio` (main, 475 KB) and `/Game/Studio/Studio_v1`. `GameDefaultMap` is
  `/Engine/Maps/Templates/OpenWorld`, so scripts should open `/Game/Studio/Studio` explicitly.

Config holds only `DefaultEngine.ini` (1121 B) and `DefaultInput.ini` (9574 B). The settings in `DefaultEngine.ini`
that matter:

```
[/Script/WindowsTargetPlatform.WindowsTargetSettings]
DefaultGraphicsRHI=DefaultGraphicsRHI_DX12
+D3D12TargetedShaderFormats=PCD3D_SM6
[/Script/Engine.RendererSettings]
r.RayTracing=True                    r.Lumen.HardwareRayTracing=True
r.DynamicGlobalIlluminationMethod=1  r.ReflectionMethod=1        (Lumen GI + reflections)
r.Shadow.Virtual.Enable=1            r.GenerateMeshDistanceFields=True
r.SkinCache.CompileShaders=True      r.SkinCache.DefaultBehavior=1
r.GPUSkin.Support16BitBoneIndex=True r.GPUSkin.UnlimitedBoneInfluences=True
r.AntiAliasingMethod=4 (TSR)         r.DefaultFeature.AutoExposure=False   r.AllowStaticLighting=False
```

There is no `[/Script/LinuxTargetPlatform.LinuxTargetSettings]` section, so Linux uses the engine default
(Vulkan, SM6). Hardware ray tracing on Vulkan has to be checked on the Linux box. The file also has an
`AndroidFileServer` section (template default, irrelevant).

Folder sizes:

| Folder | Size | Files |
|---|---:|---:|
| Content | 3,708 MB | 842 |
| — Content/Host (MetaHumans; four 268 MB `*_VT` textures) | 3,176 MB | 255 |
| — Content/Reel / Studio / Speech / FM / Python / Audio | 302 / 175 / 53 / 0.9 / 0.4 / 0.7 MB | |
| Config | 0.01 MB | 2 |
| Plugins, Source, Binaries, Build | absent | |
| Saved | 14,511 MB | 4,875 |
| — MovieRenders / Autosaves / Export / Import / Previs / Stills / A08 / Logs | 8,532 / 4,966 / 302 / 223 / 175 / 94 / 86 / 73 MB | |
| Intermediate | 263 MB | 12 |
| DerivedDataCache | 1,174 MB | 158 |
| **Whole project** | **19,655 MB** | **5,890** |

`C:\UEProjects` contains only `HostStudio`. Pipeline paths inside `Saved` include `Saved/Import` (input meshes and
textures, plus the reel `.wav`s), `Saved/Stills`, `Saved/MovieRenders` and `Saved/Bridge/{in,out}` (fmbridge queue),
with `Saved/fmbridge.token`.

## 3. Plugins outside the stock engine source

- **There are no Marketplace or Fab content plugins.** `Engine/Plugins/Marketplace` does not exist and the project has
  no `Plugins/`.
- The only non-stock engine plugin folder is `Engine/Plugins/Fab` (Epic's Fab browser, v0.0.21, `EnabledByDefault`,
  Editor module, PlatformAllowList Linux/Win64/Mac, **ships `Source/`**, 109 MB). The project doesn't use it. I copied
  it to S3 anyway in case the Linux source build lacks it.
- **Every MetaHuman plugin is engine-bundled**; none comes from Fab. Each ships `Source/`, and all binaries are Win64 only, as
  expected for a Windows install:

| Plugin (path under Engine/Plugins) | Source/ | SupportedTargetPlatforms | Win64-only modules |
|---|---|---|---|
| MetaHuman/MetaHumanAnimator (`MetaHuman`, v5.0.0, 28 modules incl. Speech2Face) | yes | Win64, Linux, Mac | none |
| MetaHuman/MetaHumanCharacter (Creator: Character, CharacterEditor, Palette, DefaultPipeline…) | yes | (unset = all) | none |
| MetaHuman/MetaHumanCoreTechLib (`MetaHumanCoreTech`) | yes | (unset) | none |
| MetaHuman/MetaHumanSDK (SDKEditor, SDKRuntime, InterchangeDNA) | yes | (unset) | none |
| MetaHuman/MetaHumanAnimationTools | yes | (unset) | none |
| MetaHuman/MetaHumanCalibrationProcessing | yes | Win64, Linux, Mac | none |
| MetaHuman/MetaHumanCrowd, MetaHuman/MetaHumanLiveLink | yes | (unset) | none |
| MetaHuman/MetaHumanCoreML | no | Mac, IOS, TVOS, VisionOS | n/a |
| Experimental/MetaHuman/MetaHumanRuntime | no (bare .uplugin, no Binaries) | (unset) | n/a |
| Experimental/MetaHuman/MetaHumanCalibrationDiagnostics | yes | Win64, Linux, Mac | none |
| Experimental/MetaHuman/MetaHumanCharacterUAF | yes | (unset) | MetaHumanCharacterUAFEditor |
| Animation/RigLogic (v13.2.5) | yes | (unset) | RigLogicEditor, RigLogicLibTest |
| Runtime/HairStrands | yes | (unset) | none (Deformer denies Android/IOS) |
| NNE/NNERuntimeORT | yes | PlatformAllowList Win64, Linux, LinuxArm64, Mac | none; `Binaries/ThirdParty/Onnxruntime/Linux` ships in the install |

There are **no prebuilt third-party libraries** in the MetaHuman plugins. The only `.lib`s are UE module import libs under
`Intermediate/`. MetaHumanCoreTechLib's solver code (`carbon`, `nls`, `nrr`, `rigcalibration_core`, `rigmorpher`,
`texture_synthesis`, `bodyshapeeditor`, …) and MeshTracker's `rlibv`/`dlib` ship as source. The Build.cs files have Linux branches
(MetaHumanPlatform has `Private/Linux`; RigLogicLib and RigLogicModule both have Linux cases). The only Windows-only dependency is
MetaHumanCaptureSource, which delay-loads Media Foundation DLLs on Win64; that is used for live capture ingest, which the pipeline
doesn't need. `RigLogicEditor` (Win64-only) is referenced only by `RigLogicDeveloper` (dynamically loaded). No MetaHuman module
or .uplugin depends on it. `MetaHumanSpeech2Face` is Type Editor with no platform list; it depends on NNE and SpeechAnimationSolver.

None of this proves that the plugins build and run on Linux. That is for the Linux build (agent-06) to establish.

## 4. The copy in S3

Bucket `rf-render-788655295054-aps1`:

- `ue-linux/project/HostStudio/` with `HostStudio.uproject` at the top. It holds 1,019 files, **4,121,869,775 bytes**:

  | Kept | Files | Bytes |
  |---|---:|---:|
  | HostStudio.uproject | 1 | 896 |
  | Config/ | 2 | 10,695 |
  | Content/ | 842 | 3,888,348,214 |
  | Saved/Import/ (pipeline inputs: outfits, meshes, reel wavs) | 169 | 233,354,379 |
  | Saved/Config/ (minus CrashReportClient/: Editor.ini, EditorPerProjectUserSettings.ini, GameUserSettings.ini, ConsoleHistory.ini, WorldState) | 5 | 155,591 |

  Skipped: DerivedDataCache, Intermediate, and the rest of Saved (MovieRenders, Autosaves, Export, Previs,
  Stills, Logs, Crashes, Bridge, fmbridge.token and so on are outputs, logs or per-machine state).
- `ue-linux/project/HostStudio.manifest.tsv` lists every copied file as `size<TAB>relative path`. The same file is in
  `inventory-raw/`. To verify a copy, the file count and byte sum must match, or compare the manifest line by line.
  `aws s3 ls --recursive --summarize` on the `ue-linux/project/` prefix showed 1,020 objects (the files plus the
  manifest) and 4,121,930,228 bytes, which is 4,121,869,775 plus the 60,453-byte manifest.
- `ue-linux/plugins/Fab/` holds 194 files, 114,748,489 bytes. That is the whole `Engine/Plugins/Fab` folder, including Win64 binaries.

The copy took 102 s for the project and 109 s in total, with `Write-S3Object -Folder -Recurse` on the instance.

For the voice-to-face PoC: the speech wavs are `Saved/Import/reel/{L1,L2,L3,L3a,L3b,L4a,L4b}.wav` and `stem_her.wav`
(copied), and `Content/Speech/Audio/*` are the imported SoundWaves. The face meshes are
`/Game/Host/Unpacked/Host/Face/SKM_Host_FaceMesh`, `/Game/Host/Unpacked/Presenter/Face/SKM_Presenter_F_FaceMesh`, and the
MetaHuman character assets `/Game/Host/Host` and `/Game/Host/Presenter_F`.

## Not verified

- I did not check whether the Linux engine opens the project, or whether the Vulkan RHI supports hardware ray tracing
  with these settings.
- The snapshot was still `pending` when this was written; see the final report for its state.
- I did not checksum individual files; the check covers file counts and byte sums only.
