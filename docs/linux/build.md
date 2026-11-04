# Building the Unreal Engine 5.8 Linux editor from source

Status, 2026-11-04: **built and stored**. Tag `5.8.4-release` (commit `f45729c0b6f097038e72b52d366a62baeca3275b`)
was compiled on one m8a.48xlarge spot instance in about 6 minutes. The runnable engine is in S3 and restores onto a
fresh GPU instance in about 4 minutes. You never need to rebuild it.

| What | Where (bucket `rf-render-788655295054-aps1`) | Size |
|---|---|---|
| Runnable engine (zstd -12 tarball) | `ue-linux/engine/5.8.4/UnrealEngine-5.8.4-linux.tar.zst` | 26.6 GB (78 GB unpacked) |
| Manifest: tag, commit, plugins, sha256, sizes, timings | `ue-linux/engine/5.8.4/manifest.json` | |
| Restore script (copy of the repo's) | `ue-linux/engine/5.8.4/ue-restore.sh` | |
| GitHub tag tarball | `ue-linux/src/5.8.4-release/github.tar.gz` | 0.6 GB |
| Source tree after `Setup.sh` (all deps + clang toolchain) | `ue-linux/src/5.8.4-release/prepared.tar.zst` | 29.4 GB (77 GB unpacked) |
| Build log and stage timings | `ue-linux/logs/5.8.4-release/` | |

sha256 of the engine tarball: `0fddf192cd882c4df47f9caabb2a3bfbfdd9139fbd5e7b627110c06d1c526f02`.

## Which version, and why

The Windows workstation runs Epic's launcher build **5.8.4** (Build.version: Changelist 58902052,
CompatibleChangelist 55116800; agent-02 read it). `5.8.4-release` is the newest 5.8 tag on GitHub, so the Linux
build is the same patch. A project saved in 5.8.x opens in the same or a later 5.8 patch.

A source build has `Changelist: 0` in Build.version, while the launcher build carries the real CL. Both share
`CompatibleChangelist 55116800`. **Not yet verified:** that every HostStudio asset loads with no version warning.
The PoC's first project open checks this.

The `.uproject`'s `EngineAssociation` is the Windows install's GUID. That doesn't matter on Linux as long as the
editor is started with an explicit `.uproject` path, which is how the scripts start it.

## Scripts (`tools/filmtools/unreal/linux/`)

| Script | Runs on | Does |
|---|---|---|
| `ue-build.sh <stage>...` | the build instance (root) | stages `prep source extras generate build package smoke`, each timed into `/data/timings.tsv` and the log copied to S3 |
| `ue-restore.sh [version] [dest]` | any Ubuntu 22.04 box | streams the tarball S3 → zstd → tar (no second copy on disk), checks sha256 against the manifest, installs the runtime libraries the editor links against, chowns to `ubuntu` |
| `ue-gpu-setup.sh` | an NVIDIA GPU box | 580 server driver from Ubuntu's prebuilt signed modules (no DKMS), headless Vulkan fix, vulkaninfo and ray-tracing extension check |
| `ue-smoke.sh` | a box with the engine | `UnrealEditor` headless (`-nullrhi`, and `-RenderOffscreen` with `UE_SMOKE_RENDER=1`) runs a Python script that writes `unreal.SystemLibrary.get_engine_version()` |
| `ue-ssm.sh push / start / sh / status` | wherever the AWS CLI works | copies the scripts to `ue-linux/tools/` and runs them on an instance over SSM as systemd units, so they survive the SSM command (no inbound port, no ssh) |

Rebuild, or build another tag. Without a cache it needs a short-lived codeload URL, which you take from the
GitHub API's tarball redirect with a token outside the instance. With `src/<tag>/prepared.tar.zst` in S3 it never
touches GitHub or Epic's CDN:

```sh
ue-ssm.sh push
ue-ssm.sh start i-0abc uebuild 'UE_TAG=5.8.4-release UE_COMMIT=<sha> UE_PLUGINS=MetaHuman,...,PythonScriptPlugin bash ue-build.sh prep source build package'
ue-ssm.sh status i-0abc uebuild
```

Restore onto a new box:

```sh
sudo UE_S3=s3://rf-render-788655295054-aps1/ue-linux bash ue-restore.sh 5.8.4 /srv/ue/engine
sudo bash ue-gpu-setup.sh          # on a GPU box
sudo UE_ROOT=/srv/ue/engine bash ue-smoke.sh
```

## Build machine

**m8a.48xlarge, spot**, ap-south-1b. It has 192 physical AMD Zen 5 cores (no SMT) and 741 GiB usable RAM, with a
500 GB gp3 root volume (16,000 IOPS, 1,000 MB/s).

* c7a is **not offered in ap-south-1** (`describe-instance-type-offerings`), so the closest equivalents are below.
* On-demand prices are from the AWS Pricing API; spot prices are from `describe-spot-price-history` on
  2026-11-04, lowest AZ.

  | Type | Cores / RAM | On-demand | Spot |
  |---|---|---|---|
  | m8a.48xlarge (used) | 192 physical / 768 GiB | $12.29/h | $2.05/h |
  | c8i.48xlarge | 96 cores, 192 threads / 384 GiB | $9.00/h | $1.58/h |
  | c7i.48xlarge | 96 cores, 192 threads / 384 GiB | $8.57/h | $1.50/h |
  | c6a.48xlarge | 96 cores, 192 threads / 384 GiB | $4.49/h | $1.31/h |

* **Memory.** UBT keeps 1.5 GiB free per action: `MemoryPerActionBytes`, default `1.5*1024^3` in 5.8.4's
  `UnrealBuildAcceleratorConfig.cs`. With 192 actions that is 288 GiB. The 384 GiB types are enough; the 768 GiB of
  m8a left room to spare. Peak use measured during the compile was 124 GiB in use at the sample taken.
* **Parallelism.** UBT runs one action per *physical* core by default. On SMT machines (c8i, c7i) set
  `bAllCores=true`. `ue-build.sh` writes this into `BuildConfiguration.xml` together with the executor and
  `dump_syms` settings. UBT reported "192 physical cores, 192 logical cores" and ran 192 at once.
* **Spot interruptions.** Every stage checkpoints to S3, and the prepared source tree is cached. An interruption
  costs only the compile (about 6 min) on the next instance.

## Measured timings (2026-11-04, UTC)

| Stage | Time | Notes |
|---|---|---|
| Instance prep (apt, AWS CLI, user, UBT config) | 9 s | |
| GitHub tag tarball (codeload) | 87 s | 579 MB, about 7 MB/s; codeload throttles. Cached in S3 after the first run |
| Unpack + `Setup.sh` (GitDependencies, clang 20.1.8 toolchain `v26`) | 101 s for Setup.sh; 168 s for the stage | the stage includes unpacking and writing `prepared.tar.zst` (zstd -3) to S3 |
| UnrealBuildTool bootstrap (`BuildUBT.sh`) | about 15 s | a tag tarball has no prebuilt UBT |
| **Compile**: UnrealEditor + ShaderCompileWorker + InterchangeWorker + UnrealPak, Linux Development, with the project's plugins | **374 s** (UBT executor: 342 s) | 6,246 actions at 192 in parallel |
| Package (zstd -12 -T0, 78 GB → 26.6 GB) + upload | 107 s | |
| Restore onto g6.4xlarge (download + unpack + sha256) | 258 s | 16 vCPU box; the pipe is bound by zstd and tar there |
| Project copy from S3 (3.9 GB) | 13 s | |

From a fresh instance with no cache, every stage together took about 14 minutes; the instance was up for about 25
minutes, including two failed attempts that I fixed on the box. A rebuild from the S3 cache: about 3 min to restore
`prepared.tar.zst`, plus 6 min to compile, plus 2 min to package.

**Cost.** The spot instance ran about 25 minutes, roughly **$0.9** (on-demand it would have been about $5.2).
S3 holds about 57 GB (engine, prepared source and tarball), roughly $1.4 a month at S3 Standard rates.

### Plugins built

The project's plugins come from the `.uproject` on the workstation (agent-02): MetaHuman, MetaHumanCharacter,
MetaHumanCoreTech, MetaHumanAnimationTools, MetaHumanSDK, MetaHumanRuntime, MovieRenderPipeline, PythonScriptPlugin,
EditorScriptingUtilities and SequencerScripting, plus HairStrands for grooms. `ue-build.sh` builds them into the
engine through a content-only probe project that enables them (`UE_PLUGINS`), or through a real project
(`UE_PROJECT`). Plugin dependencies are pulled in by UBT.

* The MetaHuman Creator presets are in the source tree:
  `Engine/Plugins/MetaHuman/MetaHumanCharacter/Content/Optional/Presets`, 260 MB (Ada, Aera, Aoi, …). The launcher
  install ships them as "Creator Core Data".
* No MetaHuman module references the Win64-only `RigLogicEditor`.
* **Fab** (from the launcher install, copied to `ue-linux/plugins/Fab/`) is **not in this build**. Its source
  allows Linux, so the `extras` stage plus an incremental build would add it. Its asset installer ships only a
  Windows DLL (`ThirdParty/BuildPatchInstallerLib.dll`), so Fab downloads on Linux are unverified.

## GPU box bring-up (g6.4xlarge, NVIDIA L4)

* **Driver:** `linux-modules-nvidia-580-server-$(uname -r)`, plus `nvidia-utils`, `libnvidia-gl` and
  `nvidia-compute-utils` 580-server. These are prebuilt, signed modules for the AWS kernel, so no DKMS build and no
  reboot. `nvidia-smi` reports: NVIDIA L4, 580.178.04, 23034 MiB.
* **Headless Vulkan:** the packaged ICD (`/usr/share/vulkan/icd.d/nvidia_icd.json`) points at `libGLX_nvidia.so.0`.
  Without an X server, `vkCreateInstance` fails with `ERROR_INCOMPATIBLE_DRIVER`. `ue-gpu-setup.sh` diverts the file
  (`dpkg-divert`) and points it at `libEGL_nvidia.so.0`. After that, `vulkaninfo` shows Vulkan 1.4.312 on the NVIDIA
  L4, with `VK_KHR_ray_tracing_pipeline`, `VK_KHR_acceleration_structure`, `VK_KHR_ray_query` and
  `VK_KHR_deferred_host_operations` present.
* **Runtime libraries:** a minimal Ubuntu 22.04 lacks pango and cairo, so `UnrealEditor` exits 127 at once.
  `ue-restore.sh` now installs pango, cairo, gtk3, nss and the X libraries, and warns about any library `ldd`
  cannot find.

## Not verified yet

* **Python smoke test.** On the build box and on the GPU box, the first runs of `ue-smoke.sh` failed before the
  editor started: first the `UnrealEditor-Cmd` path (Linux has only `UnrealEditor`), then the missing pango and
  cairo. Both are fixed in the scripts. The build box was terminated before a rerun, and the GPU box went to the PoC
  runner, so `get_engine_version()` from Python has not run under my scripts yet. The PoC's first open of
  HostStudio, with the Python bridge, covers it.
* **Shader compile time and DDC.** The first open of HostStudio (offscreen, Vulkan SM6) is with the PoC runner.
  `ue-linux/ddc/` is not written yet.
* **Fab plugin**, as above.

## Faster or smaller next time

* **The compile is no longer the bottleneck** (about 6 min on 192 cores). sccache or ccache would not pay off for a
  one-time build of a fixed tag. An Installed Build (BuildGraph) would add game targets and a DDC fill, so it would
  be slower, not faster.
* **Smaller tarball.** `Setup.sh` ran without `--exclude=Win64` or `--exclude=Android`, so Windows and Android
  third-party binaries are in the 78 GB. Excluding them, `Engine/Source` (28 GB, needed only to compile C++, and
  this project has none) and `Engine/Binaries/ThirdParty` for other platforms should roughly halve it. The restore
  time falls with it.
* **Restore in seconds.** An EBS snapshot of a volume with the engine already unpacked (or an AMI) skips the 4
  minutes of zstd and tar. Worth it only if GPU boxes are started often.
* **Debug info.** `bDisableDebugInfo=true` would cut compile and link time and disk use further, but Linux crash
  call stacks would then have no symbols. Kept on, and `*.debug` is left out of the tarball.
