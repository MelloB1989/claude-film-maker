# film-farm: Blender and Unreal renders across several GPU boxes

`film-farm` splits a render into chunks, puts them on a queue in S3, and has N GPU boxes on EC2 render them. A box
lost to a spot reclaim costs only its unfinished frames, and every frame is checked at the end. It renders **Blender**
(`blender -b`, Cycles on OptiX/CUDA, or EEVEE) and **Unreal 5.8** (MRQ, through film-ue's `render.job` on each
box's editor). Code: `tools/filmtools/farm/`. Tests: `tools/tests/test_farm.py`.

## 1. A run, start to end

From a `tools/` folder on a machine whose AWS CLI has the account (kali: `AWS_PROFILE=nani`):

```bash
film-farm quota                                                # G vCPU quotas, who uses them, what is free
film-farm submit r7 job.yaml --workers 2                       # validate, plan the chunks, queue (no box yet)
film-farm up r7 -n 2 --ami ami-... --market auto --ttl 3h      # spot first, then on-demand, within the quotas
film-farm status r7 --watch 30                                 # frames done/total, ETA, per-worker fps, $ so far
film-farm logs r7 [i-...]                                      # the workers' logs (chunk ids and timings only)
film-farm verify r7 JOB                                        # every frame once, at its recorded size
film-farm assemble r7 JOB --kinds mp4,prores --wait 30         # on a worker: hash check, continuity, encode
film-farm compare r7 JOB JOB-1box                              # per-frame PSNR against a one-box render
film-farm down r7                                              # cancel spot requests, terminate; prints the cost
```

The bucket comes from `--bucket`, `$FILM_FARM_BUCKET`, or film-ue's settings. Job files may write
`s3://BUCKET/` for it, and `"@path/file.py"` for a file's text (a Blender build script).

Boxes end themselves: after `--idle` (10 min default) with nothing to claim, or at `--ttl` (the worker checks it, and a
systemd timer powers the box off as a backstop). An on-demand box is launched with *shutdown = terminate*, so this
ends it for good. A spot box is a persistent request with *interruption = stop*, so a power-off only stops it:
**`film-farm down` is what terminates it and cancels its request.** The box role cannot do that itself (it has no EC2
rights).

## 2. A job

```yaml
id: reel-v05-s11              # lower case, digits, - _ ; unique per farm (resubmitting the same job is a no-op)
engine: ue                    # ue | blender
frames: [600, 780]            # [start, end), end exclusive, scene/sequence frame numbers
cuts: [720]                   # shot starts: chunks break on them, and pre-roll never crosses one
chunk: 40                     # frames per chunk, or auto (= frames / (3 x workers))
preroll: 24                   # frames rendered before each chunk and thrown away (default ue 24, blender 0)
privacy: private              # public | private
presenter: false              # true forces private (the face rule)
max_attempts: 4               # a chunk failing this often is marked failed (film-farm requeue --retry-failed)
output: {prefix: "s3://BUCKET/ue-linux/private/farm/x/frames/", ext: png, pad: 4, fps: 24}
ue: {...}                     # or blender: {...}
```

**Unreal** (`engines/ue.py`): `spec` is a film-ue RENDER SPEC (docs/unreal/render.md: sequence, level, preset,
spatial/temporal, cvars, warm-ups, aa_method, shutter_timing). The farm sets its frames (pre-roll included), out_dir
and name. `before: [[op, args], ...]` are bridge ops run before every chunk, for a film's own guards (mh.leader,
stray actors, face luma). `guard: {op, args, ok}` is an op whose result must be truthy. `sync: [{s3, local}]` copies
deltas on top of the image once per box, with the editor stopped (the project from
`ue-linux/private/project/<Project>`, the DDC from `ue-linux/private/ddc/5.8.4/...`). `fresh_editor: true` (the
default) restarts the editor before every chunk, the proven path.

**Blender** (`engines/blender.py`): `file` (s3:// or a path on the box) or `build` (bpy code that makes the scene,
the same on every box), `engine`, `device` (OPTIX/CUDA), `samples`, `resolution`, `camera`, `version` (default
5.2.2: installed under /opt from the farm's S3 cache or blender.org). Only the missing frames are rendered. Physics
must be baked into the file, because chunks run out of order.

Examples: `examples/farm/blender-test.yaml` (generic), `films/host-studio/farm/reel-v05-s11.yaml` (a film's UE job).

## 3. How it works

```
kali: film-farm submit ──► s3://B/<root>/job.json, chunks.json          root = farm/<farm>/<job>/ (no frames in it)
box:  worker ─ claim ─► c/<chunk>/lease.json   created If-None-Match: *   (only one box wins)
             ─ every 30 s ─► lease renewed      If-Match: <etag>           (expires 180 s after the last renewal)
             ─ render (pre-roll + chunk) ─► each frame: sha256, upload (SSE-KMS if private), progress/<box>.json
             ─ done ─► c/<chunk>/done.json      If-None-Match: *           {frame: [size, sha256]}
```

- **Leases.** S3's conditional PUT (If-None-Match / If-Match) decides every ownership question, so two boxes can never
  hold a chunk and no SQS or DynamoDB is needed. The box role's `s3:PutObject` is enough.
- **Spot reclaims.** A stopped box stops renewing. After 180 s any box takes the chunk over (attempt + 1), and
  `film-farm requeue` frees it at once if EC2 already says the box is stopped. If the box comes back, its next renewal
  fails, so it stops rendering and uploads nothing more. If nobody took its chunk meanwhile, it resumes that chunk.
- **Idempotent.** A frame counts as there only when a record (`done.json` or a `progress/<box>.json`) vouches for its
  size and hash *and* the object in the output has that size. A re-queued chunk resumes from its first missing frame:
  UE renders one unbroken range from there, pre-rolled again, and does not upload the frames it already has. Blender
  renders just the missing frames. A frame that no record vouches for (cut off mid-upload) is rendered again.
- **Pre-roll** (`model.preroll_from`): a chunk starting at frame `s` renders from `max(job start, its shot's start,
  s - preroll)` and throws those frames away. At the job's start or at a cut, a one-box render starts cold too, so
  the chunk does the same and the two match. Inside the chunk, UE's own warm-ups (`warmup_engine`, `warmup_render`)
  and `preroll: cut` (the shot evaluated from its first frame for cloth and hair) apply as in any film-ue render.
- **Verify** (`verify.verify`): the chunks cover `[start, end)` with no gap or overlap, and every frame is in exactly one
  `done.json` and in the output at the recorded size. Nothing else is in the output prefix. `assemble` also downloads
  every frame and checks its sha256, measures the luma difference into each chunk boundary against the frames around
  it (a jump over 3x the local median is flagged), and encodes H.264 mp4 / ProRes 422 HQ into
  `<prefix>_assembled/`.

## 4. Privacy (the face rule)

- A job with a presenter is `private`. A private job's frames and assembled videos live only under
  `s3://<bucket>/ue-linux/private/`, written with SSE-KMS by the boxes' own role. Validation refuses any other prefix.
  The bucket lets only that role read `private/`.
- The queue (`farm/<farm>/<job>/`: ids, frame numbers, sizes, sha256s, timings) is outside `private/` so the machine
  running `film-farm` can read it. It never holds a frame.
- Nothing private reaches the machine running `film-farm`: `assemble` and `compare` for a private job run **on a
  worker** (a queue task, and SSM respectively) and return numbers only. `--local` is refused for private jobs.
- Worker logs and `workers/<box>.json` hold chunk ids, frame counts and timings, never images or scene content.
- Use the level's own state: if a presenter is anywhere on the level, mark the job private even when no presenter is
  in frame.

## 5. Boxes and money

- `film-farm up` reads the Service Quotas ("All G and VT Spot Instance Requests", "Running On-Demand G and VT
  instances", in vCPUs) and what already uses them, and plans every worker within them. It tries spot first in the
  order g6e.4xlarge, g6e.2xlarge, g6.4xlarge, gr6.4xlarge, g5.4xlarge, each in 1a/1b/1c, then on-demand (`--market`,
  `--types`). Capacity and quota errors move to the next option.
- Tags: `Project=ue-linux-poc`, `FarmJob=<farm>`, `TTLHours`, `film-farm:managed=1`, `Name=farm-<farm>-w<i>`. Stop,
  terminate and the spot-request cancel re-read the boxes and refuse any box without both farm tags, and any box named
  like `kedits-*`, `ue-box-b*`, `gfx-explainers-cpu` or `ue-workstation`, whatever its tags.
- More than 2 workers needs `--big`: ask the operator first.
- Cost (`film-farm cost`): each worker records its sessions (boot to last word), priced at its launch price (the
  on-demand list price from the Pricing API, or the spot price then) plus its disk. It is close (per-second billing)
  but misses the minute between power-on and the worker's first word.
- Measured (farm r7a, 2026-11-07, 2x g6e.2xlarge on-demand at $2.69/h, AMI ue-host-r6-final): boot to first claim
  ~4 min. UE final 4x8 1080p ~0.5 fps per box. A warm editor restart takes 15-30 s (the first after boot ~4 min with
  the shader wait). A 40-frame UE chunk takes ~2 min wall. Blender (Cycles 64 spp 960x540) 0.43 fps per box, plus ~2
  min to install Blender the first time.
- Rough numbers (ap-south-1, Nov 2026): g6e.2xlarge on-demand $2.69/h. At final 4x8, 1080p, an L40S gives about
  0.35-0.4 fps including warm-ups, and a fresh editor plus level open adds ~3-5 min per chunk. So a 60 s explainer
  (1440 frames) is about 1 h of render on one box, or ~20 min on 4 boxes with chunks of ~120.

## 6. Gotchas

- **The image.** Workers are made from an AMI (`--ami`) holding the engine, the project and a warm DDC. Anything newer
  (box B's work) must be pushed to `ue-linux/private/project/<Project>` first and named in the job's `ue.sync`.
- **Chunk size.** Every UE chunk pays an editor restart, the level load and the shader wait. Below ~30 frames, the
  overhead beats the parallelism. Chunks of 60-150 frames are the sweet spot for finals.
- **A hung MRQ** (0 new frames) is cancelled by render.job's own stall watchdog (`stall_s`, 900 s). The worker has a
  second one 10 min later, and the chunk is retried on a fresh editor.
- **Blender frames are identical only on the same GPU and driver**, with the denoiser off or deterministic. Compare
  against a one-box render made on the same type.
- **The box role cannot delete objects.** Failed chunks are cleared by overwriting (`requeue --retry-failed`), and old
  farm prefixes are cleaned with the admin profile.
- **AWS CLI.** The leases need `put-object --if-match` (AWS CLI v2 from late 2024). The worker's fetch script updates an
  older CLI at boot.
- **Stopping a UE box takes minutes** (~6 min in the drill): the editor's unit saves the Epic sign-in on the way
  down. Its lease expires meanwhile and the chunk is taken over. Do not count on a quick stop and start.
- **Cost from the workers' sessions undercounts** the boot (~1-2 min per start) and the time before the worker's first
  word. The bill is per second from `running`.
- **Persistent spot.** A spot box stopped by a reclaim restarts by itself when capacity returns, and its worker service
  starts again (cloud-init does not run twice; the settings stay in /etc/film-farm).
