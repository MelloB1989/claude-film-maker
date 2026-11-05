# Cloud renders on SageMaker

`sm-render` renders a film's Blender plates on NVIDIA L40S GPUs as SageMaker **training jobs**. A job starts, renders
its scenes, copies the plates to S3 as they land and stops by itself, so nothing runs between renders. Idle, you pay
only for S3: the repo copy and Blender, about 1.5 GB, a few cents a month.

## Once

```sh
aws login                                  # the AWS CLI, signed in
tools/sagemaker/sm-render setup            # S3 bucket, the jobs' role, Blender and the VRM add-on uploaded
```

Settings live in `~/.config/sm-render.env` (`REGION`, `BUCKET`, `ROLE_NAME`, `IMAGE`, `BLENDER_URL`, `ADDONS`).

## Each render

```sh
tools/sagemaker/sm-render render                 # the stale scenes, on 3 L40S; shows the cost and asks first
tools/sagemaker/sm-render status                 # state, minutes and cost so far
tools/sagemaker/sm-render pull                   # plates into out/<film>/plates (stamps included)
cd tools && uv run film-anime-render --film rain-ferry    # here: every plate is up to date, so it only makes the video
tools/sagemaker/sm-render clean                  # delete the run's plates from S3 once pulled
```

Useful options for `render`: `--only a,b` (these scenes), `--all` (every scene), `--gpus N` (1 to 4 jobs),
`--spot` (about 60% cheaper; it may wait for capacity or be interrupted, and plates already written are kept),
`--max-hours H` (each job's hard limit, default 2), `--wait` (wait, then pull), `--yes` (don't ask).

## What it costs

On-demand in Mumbai, per job-hour: ml.g6e.xlarge $3.13, ml.g6e.2xlarge $3.37, ml.g6e.4xlarge $4.51,
ml.g6e.8xlarge $6.80. A whole-film render on 3 GPUs takes roughly 30-45 minutes. `render` prints the per-hour
total and the worst case (every job running to its limit) before it starts anything. Training jobs bill only from
start to stop. `sm-render stop` ends a run early.

Never leave a SageMaker notebook instance, Studio app or endpoint running: they bill every hour until deleted.
This tool uses none of them.

## How it works

- `render` syncs the repo to `s3://<bucket>/repo/` (only changed files; not `out/`, venvs or `.git`), asks
  `film-anime-render --dry-run` which scenes are stale here, splits them across the jobs by length, and starts one
  training job per GPU size (the account's quota allows one job of each size at a time).
- Each job ([job.sh](job.sh)) runs on AWS's PyTorch GPU image, unpacks Blender and the add-ons from S3, forces
  NVIDIA's EGL so EEVEE draws on the L40S, never Mesa's software renderer (it stops if the GPU's graphics libraries
  are missing), then runs `film-anime-render --only <its scenes> --plates-only`.
  Its `out/` is the checkpoint dir, which SageMaker copies to `s3://<bucket>/runs/<run>/<job>/`.
- Plates carry the same fingerprints as local ones (same code, same assets), so after `pull` the local tool treats
  them as up to date.
