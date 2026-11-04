# What would Linux cost, and on which instance?

Task 20261104-task-what-would-linux-4b95 (topic: cost). Desk research only: no AWS resource was started, the stopped
workstation was not touched. **Every price is dated 2026-11-04** and comes from AWS's public, no-account price files
(below), all USD, ap-south-1 (Mumbai) unless a region is named. Confidence tags: **confirmed** (read from an official
source or the repo), **likely** (inferred from official specs or several community reports), **unknown** (a PoC must
settle it; the test is named).

Operator clarification (follow-up, applies here): Unreal is to be driven **entirely by code**, never through the
editor UI. For cost that means: no DCV desktop, no interactive latency budget, no GRID driver requirement (the
datacenter "Tesla" driver is enough for headless Vulkan, see §5), and spot is usable for more than renders.

## 0. Verdict

- **Linux saves the Windows licence: $0.736/h on every 16-vCPU instance (28 % of today's $2.584/h)**, and
  opens spot, which on these GPU types in Mumbai costs 20-30 % of on-demand. *confirmed (prices)*
- **The renders are a small part of the bill.** One 1080p pass of the reel is ~0.6 h of L4 time ($1.65 today on
  Windows); a 4K pass is 1.8-6.8 h. Moving *only* the renders to Linux saves a few dollars per pass; the money is in
  the hours the editor is up for building and shooting. *likely (render speed is the brief's 0.9 s/frame, unverified)*
- **Cheapest instance I am confident works: `gr6.4xlarge` on Linux, $1.848/h on-demand**: the same L4 (22 GiB),
  16 vCPU and 128 GiB as today, so nothing about memory or speed changes; only the OS does. `g6.4xlarge`
  ($1.589/h, same GPU, **64 GiB** RAM) is cheaper if 64 GiB is enough, which nobody has measured. For renders and
  scripted shooting on spot: a pool of `gr6.8xlarge` ($0.528/h, <5 % interruption), `g6.8xlarge` ($0.486/h),
  `gr6.4xlarge` / `g6.4xlarge` (~$0.57/h, >20 % interruption). *confirmed (prices) / likely (works)*
- **The engine does not have to be built**: Epic publishes a precompiled Linux editor zip per 5.8 hotfix
  (`Linux_Unreal_Engine_5.8.x.zip`, ~39 GB, ~70 GB unpacked for 5.8.1 per agent-04's engine note) behind an Epic-account login. If the operator downloads it, the one-off
  build cost is zero. If it is built from source, one `c8i.48xlarge` / `m8a.48xlarge` hour (~$9-12) does it. §6.
- **No cost blocker.** The blockers are in the engine task (MetaHuman Creator / audio-to-face / Fab on Linux).
  Hybrid is ruled out by the operator (2026-11-04): Linux only. Round 3 entirely on Linux: ~$2.5-8 on spot,
  ~$7-24 on-demand (§8).

## 1. Sources (all fetched 2026-11-04)

| What | URL | Notes |
|---|---|---|
| On-demand, per region & OS | `https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/<Region name>/<Linux\|Windows>/index.json` | the data behind aws.amazon.com/ec2/pricing/on-demand; gzip |
| EC2 bulk price list (EBS) | `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/ap-south-1/index.csv` | publication 2026-11-03T23:57Z; EBS rows effective 2026-11-01 |
| S3 bulk price list | `.../offers/v1.0/aws/AmazonS3/current/ap-south-1/index.csv` | effective 2026-10-01 |
| Data transfer | `.../offers/v1.0/aws/AWSDataTransfer/current/ap-south-1/index.csv` | effective 2026-06-01 |
| Spot prices | `https://website.spot.ec2.aws.a2z.com/spot.json` (the feed of aws.amazon.com/ec2/spot/pricing) | Last-Modified 2026-11-04 15:16 UTC; **one number per region, a snapshot** (spot moves per AZ and hour) |
| Spot interruption frequency | `https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json` (Spot Instance Advisor) | Last-Modified **2026-03-20**: 7 months old; no data for ap-south-2 or for g6e/g7e in Mumbai |
| GPU per size | https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html | |
| Drivers per family | https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/install-nvidia-driver.html , .../nvidia-GRID-driver.html | |
| DCV licence on EC2 | https://docs.aws.amazon.com/dcv/latest/adminguide/setting-up-license.html | |
| G7 GPU | https://aws.amazon.com/ec2/instance-types/g7/ | |
| Linux precompiled UE 5.8 | https://forums.unrealengine.com/t/linux-precompiled-download-loops-to-eula-after-successful-acceptance/2764062 (names `Linux_Unreal_Engine_5.8.2.zip`, 2026-09-09); https://forums.unrealengine.com/t/compiler-crashes-on-linux-when-trying-to-compile-lyragame/2837349 (a 5.8.3 prebuilt install, bundled clang 20.1.8); https://aur.archlinux.org/packages/unreal-engine-bin (zip from unrealengine.com/linux, Epic login); https://bytexd.com/how-to-setup-and-run-unreal-engine-5-on-ubuntu/ (~20 GB zip, ~60 GB extracted) | community, not Epic docs |
| UE source/dependency size | https://zompidev.blogspot.com/2026/05/reducing-size-of-unreal-engine-5-source.html (5.7.4: clone 2.48 GB; Setup with all platforms 82.9 GB, without the non-Windows ones 54.7 GB) | community |
| Reel facts | repo: `films/host-studio/reel/PLAN.md` on `origin/fleet/agent-06-2/reel` (1560 frames at 24 fps; 4K estimate 8-15 s/frame with hair in frame); `unreal/fmbridge/ops/render.py` (MRQ settings) | the brief's 0.9 s/frame at 1080p is **not recorded in the repo** |

The scripts that turned these files into the tables are short (filter by instance type, print); rerun them before a
decision: prices change, spot hourly.

## 2. The candidate GPUs (what fits UE 5.8 + MetaHumans)

| Family | GPU | VRAM (usable) | vCPU / RAM of the size that fits | Tesla driver (headless Vulkan) | In Mumbai | Fit |
|---|---|---|---|---|---|---|
| gr6 (today) | L4 | 22 GiB | 4xl: 16 / 128 GiB; 8xl: 32 / 256 | yes | yes | **fits: what runs today** |
| g6 | L4 | 22 GiB | 4xl: 16 / 64; 8xl: 32 / 128 | yes | yes (and ap-south-2) | fits; 4xl RAM unmeasured |
| g5 | A10G | 22 GiB | 4xl: 16 / 64 | yes | yes | fits; A10G has 2x the L4's memory bandwidth (600 vs 300 GB/s), likely as fast or faster for raster; older |
| g6e | L40S | 44 GiB | 2xl: 8 / 64; 4xl: 16 / 128 | yes | yes (and ap-south-2) | fits; ~2.5-3x an L4 on spec (91.6 vs 30.3 FP32 TFLOPS, 864 vs 300 GB/s) *likely* |
| g7e | RTX PRO 6000 Blackwell | 96 GiB | 2xl: 8 / 64 | yes (GRID needs ≥19.1) | yes | fits, overkill; speed vs L4 unknown |
| g7 | RTX PRO 4500 Blackwell | 32 GiB | 4xl: 16 / 64 (no SMT) | yes (GRID needs ≥20.1) | **no** (us-east-1, us-west-2, eu-central-1) | fits, not in India |
| g4dn | T4 | 16 GiB | 4xl: 16 / 64 | yes | yes | **risky**: Turing, ~0.4x an L4, 16 GiB at 4K with strands |
| g6f / gr6f | ½ L4 at most | 11.18 GiB (4xl) | 16 / 64 or 128 | **no: GRID only** | yes | **no**: half the GPU for 0.6-0.7x the price, 11 GiB |

Sources: AWS instance-type and driver docs (§1). *confirmed* for specs; speed ratios *likely* (from specs, no UE
benchmark found).

**VRAM for the reel** *likely, not measured*: 1080p MRQ, deferred + Lumen + virtual shadows + hair strands with
8-sample MSAA visibility: ~8-12 GB; at 3840x2160 the screen-size buffers grow 4x (the hair visibility buffer at 8
samples/pixel alone is several hundred MB), ~12-20 GB. 22 GiB (L4/A10G) should hold it; 16 GiB (T4) may not; 11 GiB
(g6f) will not. **Settle it without Linux** next time the Windows box renders: `nvidia-smi --query-gpu=memory.used
--format=csv -l 5` during a 4K MRQ of S14 (a presenter shot), plus `stat gpu` / `r.ProfileGPU` for the frame time.

## 3. Prices per hour (2026-11-04)

### ap-south-1 (Mumbai), on-demand and spot

| Instance | Windows OD | Linux OD | Win premium | Linux spot | Interruption (advisor, Mar 2026) |
|---|---|---|---|---|---|
| **gr6.4xlarge** (today) | **2.584** | 1.848 | 0.736 | 0.561 | >20 % |
| gr6.8xlarge | 4.410 | 2.938 | 1.472 | **0.528** | **<5 %** |
| g6.2xlarge | 1.542 | 1.174 | 0.368 | 0.405 | >20 % |
| g6.4xlarge | 2.325 | 1.589 | 0.736 | 0.579 | >20 % |
| g6.8xlarge | 3.891 | 2.419 | 1.472 | **0.486** | 10-15 % |
| g5.4xlarge | 2.686 | 1.950 | 0.736 | 0.826 | >20 % |
| g6e.2xlarge | 3.061 | 2.693 | 0.368 | 1.423 | no data |
| g6e.4xlarge | 4.344 | 3.608 | 0.736 | 1.719 | no data |
| g7e.2xlarge | 5.861 | 5.493 | 0.368 | 2.004 | no data |
| g4dn.4xlarge | 2.061 | 1.325 | 0.736 | 0.406 | >20 % |
| gr6f.4xlarge (½ L4) | 2.016 | 1.280 | 0.736 | 1.231 | <5 % |

The Windows premium is exactly **$0.046 per vCPU-hour** on every size (16 vCPU → $0.736/h). The operator was told
~$2.6/h for the workstation: the list price is $2.5843. *confirmed*

### Other regions (Linux on-demand / Linux spot), for the same sizes

| Instance | ap-south-2 Hyderabad | ap-southeast-1 Singapore | us-east-1 | us-west-2 | eu-central-1 |
|---|---|---|---|---|---|
| gr6.4xlarge | not offered | not offered | 1.539 / 0.779 | 1.539 / 0.711 | 1.925 / 0.770 |
| g6.4xlarge | 1.589 / **0.234** | not offered | 1.323 / 0.792 | 1.323 / 0.754 | 1.655 / 0.864 |
| g6.8xlarge | 2.419 / 0.596 | not offered | 2.014 / 0.895 | 2.014 / 0.944 | 2.519 / 0.817 |
| g6e.4xlarge | 3.608 / 1.070 | not offered | 3.004 / 2.126 | 3.004 / 1.757 | 3.757 / 1.078 |
| g7.4xlarge | not offered | not offered | 3.042 / 0.576 | 3.042 / 0.505 | 3.804 / 1.082 |

- **Hyderabad** has Mumbai's on-demand prices and, today, much cheaper spot for g6 (0.234). No advisor data, no gr6,
  and an S3 bucket in Mumbai means inter-region transfer ($0.086/GB out of Mumbai, *confirmed*) unless the bucket
  moves too.
- **US regions** are ~17 % cheaper on-demand but their spot today is *not* cheaper than Mumbai's, and the operator
  sits ~200+ ms away. **Singapore** has no g6/gr6/g6e at all.
- **Latency from India** (*likely*, typical public ping figures; not measured): Mumbai and Hyderabad 15-50 ms,
  Singapore 60-90 ms, Frankfurt 120-160 ms, us-east-1 200-250 ms. With everything driven by code over the bridge,
  latency only stretches each bridge round trip; it matters little. Measure from the operator's Mac with
  `curl -so /dev/null -w '%{time_connect}\n' https://ec2.<region>.amazonaws.com`.

**Spot caveats** *confirmed in principle*: the feed shows one price per region; real prices differ per AZ and change
hourly; Windows spot shows odd pools (cheaper than Linux on some types): don't read Windows spot as a plan. New or
quiet accounts often have a **G/VT spot vCPU quota of 0** ("All G and VT Spot Instance Requests", and "Running
On-Demand G and VT instances" for on-demand): check Service Quotas before counting on spot.

## 4. Storage, transfer, DCV, AMIs (2026-11-04)

| Item | Price (ap-south-1) | Source / confidence |
|---|---|---|
| EBS gp3 | $0.0912 /GB-month; 3000 IOPS + 125 MB/s included; +$0.0057 /IOPS-month, +$0.0456 /MBps-month | EC2 price list, *confirmed* |
| EBS snapshot / AMI | $0.05 /GB-month (archive tier $0.0125, 90-day minimum) | *confirmed* |
| S3 Standard | $0.025 /GB-month; PUT $0.005 /1000; GET $0.0004 /1000 | S3 price list, *confirmed* |
| EC2 ↔ S3 same region | free | *confirmed* (AWS data-transfer rule) |
| Out to the internet (frames to the Mac) | $0.1093 /GB first 10 TB, after AWS's 100 GB/month free tier | DataTransfer price list, *confirmed*; free tier *likely* (AWS policy since 2021) |
| Mumbai → other region | $0.086 /GB | *confirmed* |
| Instance store NVMe | included: g6.4xl 600 GB, g6.8xl 2x450, gr6.4xl 600, g6e.2xl 450 | *confirmed*; wiped on stop: use it for DDC, Intermediate and frames in flight |
| Amazon DCV on EC2 | **no licence, no cost**; the instance role needs `s3:GetObject` on `arn:aws:s3:::dcv-license.ap-south-1/*` | DCV admin guide, *confirmed*. Not needed at all if nothing is ever looked at (the code-only rule) |
| NVIDIA GRID driver | no cost on EC2 (licensed through AWS's EULA for T4/A10G/L4/L40S/RTX PRO); from `s3://ec2-linux-nvidia-drivers/` | AWS GRID doc, *confirmed*. Needed only for a DCV desktop or g6f/gr6f |
| Deep Learning Base AMI (Ubuntu) | no charge beyond EC2 | AWS, *likely* |
| NVIDIA marketplace AMIs (RTX vWS etc.) | some carry a software charge per hour | *likely*; avoid, nothing here needs them |

**Disk sizes (unknown: read them next time the box is up).** Nothing in the repo records the project, DDC or volume
size. Read, through `film-ue` (`workstation.ps`):
`Get-ChildItem C:\UEProjects\HostStudio -Directory | % { $_.Name, ((Get-ChildItem $_.FullName -Recurse -File | Measure Length -Sum).Sum/1GB) }`
(Content, DerivedDataCache, Saved, Intermediate), the shared DDC `"$env:LOCALAPPDATA\UnrealEngine\Common\DerivedDataCache"`,
and `Get-Volume C`. And the **engine patch**: `Get-Content 'C:\Program Files\Epic Games\UE_5.8\Engine\Build\Build.version'`
(MajorVersion/MinorVersion/PatchVersion/Changelist), or in the editor `unreal.SystemLibrary.get_engine_version()`.
Working assumption for the tables: project 60 GB, engine 60 GB, DDC 40 GB. **The Windows DDC is useless on Linux**
(D3D shaders vs Vulkan SPIR-V): the first Linux open compiles every shader again (*likely*; tens of minutes to hours
on 16 vCPU for MetaHumans + groom; unknown). Compile it once and keep the Linux DDC (S3 or a snapshot).

## 5. Driver and AMI

- **Headless Vulkan needs no GRID.** AWS lists OpenGL and Vulkan among the APIs of the Tesla, GRID and gaming drivers
  alike; G4dn/G5/G6/Gr6/G6e/G7/G7e take the Tesla driver, g6f/gr6f only GRID. *confirmed (AWS doc)*
- Recommended base: **AWS Deep Learning Base GPU AMI (Ubuntu 24.04)** (driver preinstalled, free) or plain Ubuntu
  24.04 plus NVIDIA's `.run` / `nvidia-driver-5xx-server` packages. **Unknown:** whether the DL AMI ships the Vulkan
  ICD and `libnvidia-gl` (it is built for CUDA). PoC: `vulkaninfo --summary` shows the L4, and
  `UnrealEditor-Cmd ... -RenderOffscreen` starts with the Vulkan RHI (engine task's test).
- If a desktop is ever wanted: GRID from `s3://ec2-linux-nvidia-drivers/latest/` + DCV, still free.
- Bake one **render AMI**: Ubuntu + driver + the engine on its own volume + the Linux DDC. AMI storage is snapshot
  storage: ~150-200 GB (agent-04's engine sizes) → $7.5-10/month.

## 6. Getting the engine (one-off)

### a. Precompiled (recommended to try first) — ~$0 compute

Epic's `https://www.unrealengine.com/linux` gives `Linux_Unreal_Engine_5.8.x.zip` (5.8.2 and 5.8.3 are seen in
forum posts; whether 5.8.4 is there is unknown). ~20 GB zip, ~60 GB unpacked. *likely (community, consistent)*.
Needs the **operator's Epic login in a browser**; a forum report (2026-09-09) says the page can loop on the EULA:
if it does, the source build below is the fallback. Store: the zip in S3 ($0.50/month). Match the Windows patch (or
newer within 5.8) so assets open unchanged (*likely*: hotfixes keep the asset format).
**Correction from the engine task** (agent-04, `docs/linux/engine.md` on `fleet/agent-04/linux-engine`): the 5.8.1
zip is ~39 GB and unpacks to ~70 GB (an Epic moderator advises planning 150-200 GB); the ~20/60 GB community figure
is from older releases. S3 for the zip: ~$1/month.

### b. Built from source — target 15-20 min compile

| Step | How | Time (*likely*) |
|---|---|---|
| Instance | **`c8i.48xlarge`** (192 vCPU = 96 cores, 384 GiB, $9.00/h OD, Mumbai) or **`m8a.48xlarge`** (192 physical cores, Zen 5, 768 GiB, $12.29/h). Cheaper and slower: `c6a.48xlarge` ($4.49/h, Zen 3). On-demand, not spot (spot $1.3-1.6/h saves a few dollars and risks the hour) | — |
| Disk | 500 GB gp3 (a 5.4 source tree took 340+ GiB while building, ~190 GiB built: agent-04) at 16000 IOPS / 1000 MB/s (an hour of it costs cents), or on m8a build in tmpfs (`/dev/shm`, 768 GiB) | — |
| Clone | `git clone --depth 1 --single-branch --branch 5.8.4-release https://github.com/EpicGames/UnrealEngine.git` with the mellob-ai token as a secret on that instance only | 1-3 min (~2.5 GB) |
| Dependencies | `./Setup.sh` (GitDependencies) with Linux only: `--exclude=Win64 --exclude=Mac --exclude=Android --exclude=IOS --exclude=TVOS --exclude=HoloLens --exclude=LinuxArm64`; `--threads=64` | 3-8 min (~20-30 GB) |
| Project files | `./GenerateProjectFiles.sh` | 1-2 min |
| Compile | `Engine/Build/BatchFiles/Linux/Build.sh UnrealEditor Linux Development -MaxParallelActions=192` then `ShaderCompileWorker`, `UnrealPak`, `CrashReportClient`, `EpicWebHelper` (or `make` for the standard set) | **12-20 min** on 192 threads (~5-6k actions); 25-35 min on c6a |
| Parallelism | UBT caps actions by cores and by RAM per action; set `~/.config/Unreal Engine/UnrealBuildTool/BuildConfiguration.xml` `<ParallelExecutor><MaxProcessorCount>192</MaxProcessorCount><ProcessorCountMultiplier>1</ProcessorCountMultiplier></ParallelExecutor>` and lower its memory-per-action setting if it throttles (2 GiB/action is enough for clang: 384 GiB covers it) | check the field names in `Engine/Source/Programs/UnrealBuildTool/Executors/` for 5.8 |
| ccache / sccache / UBA | **no**: one build, never rebuilt; a cache only helps a second build. UBA's Linux support is not something to depend on | — |
| Keep it | `tar --zstd -T0` of `Engine/` without `Intermediate/`, `.git`, `*.debug` (symbols in a separate tarball) → S3: ~25-40 GB → $0.6-1/month; restore at 0.5-1 GB/s in a few minutes. Also put it on the render AMI (§5). | 5-10 min |
| **Total** | ~45-60 min billed: **$7-12** (c8i/m8a) or ~$5 (c6a, 1-1.2 h) | |

In flight (2026-11-04): agent-06 builds 5.8 from source on a 192-vCPU instance (task 20261104-task-build-the-ue-08c2)
and agent-02 reads the exact engine version and plugin list and copies the project (20261104-task-inventory-the-windows-f7e8);
both store under `ue-linux/` in the render bucket. Their measured numbers replace §4's and §6's estimates.

Plus, either way, **the Linux DDC** for the project: open the project once on the GPU instance (or try
`-run=DerivedDataCache -fill` on a big CPU box with `-nullrhi`; whether that fills the *editor's* Vulkan SM6 shaders
is unknown) and keep the DDC folder in S3 (~$1/month).

## 7. Render cost of the reel (65 s, 24 fps = 1560 frames)

Per pass, on an L4: 1080p = 1560 x 0.9 s = 0.39 h + ~0.25 h start, map load and MRQ warm-ups = **0.64 h**. 4K is 4x
the pixels: **1.8 h** if it scales linearly (3.6 s/frame), **6.8 h** at PLAN.md's upper estimate (15 s/frame with
hair in frame). Other GPUs scaled by the spec ratios in §2 (L40S 2.5x, RTX PRO 6000 4x, T4 0.4x: *likely*/*unknown*).
Spot includes +10 % for re-rendered chunks after interruptions. A cold Linux DDC adds a one-off 0.5-2 h (§4).

| Option | $/h OD | $/h spot | 1080p pass OD | 4K pass OD | 1080p spot | 4K spot |
|---|---|---|---|---|---|---|
| **Windows gr6.4xlarge (today)** | 2.584 | — | **1.65** | **4.68-17.44** | — | — |
| Linux gr6.4xlarge | 1.848 | 0.561 | 1.18 | 3.35-12.48 | 0.40 | 1.12-4.17 |
| Linux gr6.8xlarge | 2.938 | 0.528 | 1.88 | 5.32-19.83 | 0.37 | 1.05-3.92 |
| Linux g6.4xlarge | 1.589 | 0.579 | 1.02 | 2.88-10.73 | 0.41 | 1.15-4.30 |
| Linux g6.8xlarge | 2.419 | 0.486 | 1.55 | 4.38-16.33 | 0.34 | 0.97-3.61 |
| Linux g5.4xlarge | 1.950 | 0.826 | 1.25 | 3.53-13.16 | 0.58 | 1.64-6.13 |
| Linux g6e.2xlarge | 2.693 | 1.423 | 1.09 | 2.35-7.67 | 0.64 | 1.37-4.46 |
| Linux g6e.4xlarge | 3.608 | 1.719 | 1.46 | 3.15-10.28 | 0.77 | 1.65-5.39 |
| Linux g7e.2xlarge | 5.493 | 2.004 | 1.91 | 3.52-10.30 | 0.77 | 1.41-4.13 |
| Linux g4dn.4xlarge | 1.325 | 0.406 | 1.62 | 5.50-21.86 | 0.55 | 1.85-7.37 |
| Linux g6.4xlarge, Hyderabad | 1.589 | 0.234 | 1.02 | 2.88-10.73 | 0.16 | 0.47-1.74 |
| Linux g6.4xlarge, us-east-1 | 1.323 | 0.792 | 0.85 | 2.39-8.93 | 0.56 | 1.58-5.88 |

On-demand, **g6e.2xlarge is the cheapest per 4K pass** if the L40S really is ~2.5x an L4 (unmeasured), but its 8 vCPU
make shader compiles and editor work slow: a render node, not a workstation. Frames back: a 4K PNG is ~15-25 MB →
~30 GB a pass, ~$0-3.40 of egress (free under 100 GB/month).

### Spot interruption handling for MRQ

MRQ writes one file per frame, and `render.mrq` already takes `start`/`end`; `render.progress` counts frames. So:

1. Render the master sequence in **chunks** (a shot, or ~120 frames), each with its warm-up frames (`warmup=32`:
   temporal history and motion blur are rebuilt, so a resumed chunk matches).
2. Frames go to instance-store NVMe and are **synced to S3 continuously** (`aws s3 sync` every ~30 s).
3. A watcher polls IMDS `/latest/meta-data/spot/instance-action` (2-minute notice): stop the queue, final sync.
4. The next instance (same AMI) pulls the chunk list, skips frames already in S3, re-renders the cut chunk.
   Loss per interruption: one chunk's partial frames + warm-up + ~5-10 min of boot and editor start.
5. Ask with **EC2 Fleet / capacity-optimized** over several types and AZs (gr6.8xl, g6.8xl, gr6.4xl, g6.4xl,
   g5.4xl), one-time requests. Don't count on hibernation for GPU types.

## 8. Scenarios (a month with one reel)

Assumptions (change them freely): **40 editor-hours** of scripted building and shooting, **4 x 1080p** passes,
**2 x 4K** passes at the mid estimate (4.3 h L4 each), EBS as in §4 (Windows volume assumed 500 GB gp3: read the real
size). Excludes the operator's own machine and fleet costs.

| Scenario | Compute | Storage /month | **Total /month** | vs today |
|---|---|---|---|---|
| **Today**: Windows gr6.4xlarge OD for everything | 40 h x 2.584 + renders 28.8 = 132.2 | 500 GB gp3 45.6 | **~$178** | — |
| **A. Render-only Linux**: Windows as today for building/shooting; renders on Linux spot (g6.4xl/gr6.8xl pool) | 103.4 + renders ~7.6 | 45.6 + engine/DDC/project snapshot ~150 GB 7.5 | **~$164** | -8 % |
| **B. Full Linux, on-demand**: gr6.4xlarge Linux OD for everything | 40 x 1.848 + renders 20.6 = 94.5 | 200 GB gp3 18.2 + S3 ~2 | **~$115** | -35 % |
| **B'. Full Linux, spot**: gr6.8xlarge spot for building/shooting too (scripts checkpoint by saving the level) | 40 x 0.528 x 1.1 + renders 7.6 = 30.8 | snapshot/AMI 150 GB 7.5 + S3 2 | **~$40** | -77 % |
| **C. Hybrid**: Windows gr6.4xl for MetaHuman character work (10 h), Linux gr6.4xl OD for the rest (30 h) + spot renders | 25.8 + 55.4 + 7.6 = 88.8 | both volumes 45.6 + 18.2 | **~$153** | -14 % |

**Operator decision (2026-11-04): hybrid is out.** Linux only; a step that can't run on Linux gets a code-only
alternative, not a Windows box. Scenario C stays above only for comparison. Fab content must work on Linux too.

**Round 3 of the reel, re-rendered entirely on Linux** (operator decision: no Windows shots mixed in). Assumed: one
Linux DDC fill, one 1080p check pass, one 4K final and one 4K re-render of about half the reel:

| Item | gr6.4xlarge OD | gr6.4xlarge spot | g6e.2xlarge OD (if 22 GiB is too tight) |
|---|---|---|---|
| Linux DDC fill (once, 0.5-2 h) | 0.9-3.7 | 0.3-1.1 | 1.3-5.4 |
| 1080p pass | 1.18 | 0.40 | 1.09 |
| 4K final | 3.35-12.48 | 1.12-4.17 | 2.35-7.67 |
| 4K re-render, half the reel | 1.8-6.3 | 0.6-2.1 | 1.3-3.9 |
| **Round 3 total** | **~$7-24** | **~$2.5-8** | **~$6-18** |
| vs the same on Windows gr6.4xlarge OD (no DDC fill: 1.65 + 4.68-17.44 + 2.3-8.7) | ~$9-28 | | |

Even with the one-off shader-cache fill, round 3 on Linux on-demand costs ~20 % less than on Windows; on spot ~70 %
less; later rounds skip the fill.

**The Epic sign-in costs nothing extra.** The operator's one login (P10/P12) can use a DCV *virtual* session on the
PoC box: it is free on EC2, needs no GRID driver, and takes minutes of instance time already being paid for. For the
precompiled zip only, the operator can also download it on the Mac and `aws s3 cp` it to `ue-linux/`: uploads into
S3 are free; the ~39 GB costs ~$1/month to keep.

One-off for B/B': the engine (§6, $0-12), the first Linux DDC fill (0.5-2 GPU-hours, $1-4), and moving the project
(S3 in-region: free transfer, cents of storage). Hybrid's saving is eaten by keeping two machines' volumes; it is
worth it only while some character step is Windows-only (engine task).

## 9. Risks

1. **Engine features on Linux** (engine task): MetaHuman Creator cloud rig/texture synthesis, audio-to-face,
   Fab, groom, MRQ under `-RenderOffscreen`. A Windows-only step forces scenario C.
2. **Render speed unmeasured**: 0.9 s/frame is the brief's number, not the repo's; 4K is a 4x range. Calibrate with
   PLAN.md's 24 frames of S14 and S11, on Windows first, then the same on Linux (Vulkan vs D3D12 speed: unknown).
3. **RAM and VRAM**: g6.4xlarge has 64 GiB vs today's 128; peak use unknown. Agent-04 found a known MetaHuman
   assembly OOM on Linux in 5.8 (add swap on the NVMe) and Epic's remark that Linux Vulkan memory management lags
   DX12, so the L4's 22 GiB may be tight at 4K with MetaHumans + groom + Lumen; the step up is g6e (L40S, 44 GiB:
   2xl $2.693/h OD, $1.423 spot). This is one more reason to prefer gr6 (128 GiB) for building.
   Read `Get-Process UnrealEditor` WorkingSet64
   peak during a MetaHuman build and a 4K render next time.
4. **Spot**: quota may be 0; advisor data is 7 months old; prices per AZ differ from the feed.
5. **Precompiled download** may loop on Epic's EULA page; the patch you need may not be offered.
6. **Moving the project without booting Windows** (agent-07's workflow note, `docs/linux/workflow.md` on
   `fleet/agent-07/linux-workflow`): snapshot the stopped Windows volume, make a volume from it, mount it read-only
   with `ntfs3` on Linux. Costs a snapshot ($0.05/GB-month while kept) instead of Windows hours.
7. **Cold DDC** on every fresh instance unless the Linux DDC is kept (S3/snapshot); EBS from a snapshot lazy-loads
   (first reads slow) unless the volume is pre-warmed.
8. **Driver/Vulkan on the DL AMI** unverified (§5).

## 10. PoC tests (cost-relevant), in order

1. On the Windows box (no Linux needed): read Build.version, project/DDC/volume sizes, peak RAM and VRAM and s/frame
   for 24 frames of S14 at 1080p and 4K. 0.5 h of the workstation (~$1.30).
2. Check Service Quotas for G/VT on-demand and spot vCPUs in ap-south-1 (and ap-south-2).
3. Engine: the operator tries the precompiled zip download; if not, the source build on c8i.48xlarge (~1 h, ~$9,
   500 GB gp3), tarball to S3, render AMI.
4. One **g6.4xlarge spot** in ap-south-1, 3 h, 200 GB gp3 + its NVMe (~$2 spot / ~$5 OD): `vulkaninfo`, editor
   headless with the bridge, DDC fill timed, the same 24-frame S14/S11 renders at 1080p and 4K, `nvidia-smi` VRAM,
   peak RAM, a simulated interruption (kill mid-chunk, resume) for §7's handling.
5. If 4 passes: one g6e.2xlarge hour (~$1.4 spot) to measure the L40S ratio, which decides the render node.
