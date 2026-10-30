# GPU renders on AWS

`gpu-render` renders a film's Blender plates on several EC2 boxes with NVIDIA L40S GPUs. One command starts the
boxes. Each box renders scenes off a shared queue, uploads the plates to S3 and terminates itself when the queue is
empty. Nothing runs between renders.

## Once

```sh
aws login                                  # the AWS CLI, signed in
tools/cloud/gpu-render setup               # S3 bucket, the boxes' role, a no-inbound security group,
                                           # Blender + the VRM add-on (from this Mac's Blender) into S3
tools/cloud/gpu-render image               # the boxes' machine image: Blender, add-ons, uv, the tools' Python
```

Run `image` again only after changing Blender's version or the add-ons. Settings live in
`~/.config/gpu-render.env` (`REGION`, `BUCKET`, `TYPES`, `AZS`, `BLENDER_URL`, `ADDONS`).

## Each render

```sh
tools/cloud/gpu-render render              # the stale scenes on up to 4 L40S boxes; shows the cost, asks first
tools/cloud/gpu-render status              # boxes up, scenes done
tools/cloud/gpu-render pull                # plates (and their stamps) into out/<film>/plates
cd tools && uv run film-anime-render --film rain-ferry    # here, every plate is up to date: it only makes the video
```

Options for `render`:

| Option | What it does |
|---|---|
| `--only a,b` | render these scenes |
| `--all` | render every scene |
| `--gpus N` | number of boxes (default 4, the account's 16-vCPU quota) |
| `--spot` | about 55% cheaper, but AWS may take a box back (its plates so far are kept) |
| `--max-hours H` | each box's hard limit (default 2) |
| `--wait` | wait for the boxes, then pull |
| `--yes` | don't ask |

`stop` terminates a run's boxes at once. `clean` deletes the plates and run files from S3 once you've pulled them.

## What it costs

- **Rendering:** on-demand in Mumbai, per box-hour, `g6e.xlarge` costs $2.24 and `g6e.2xlarge` costs $2.69. The
  whole film on 4 boxes takes about 30–40 minutes.
- **Idle:** you pay only for S3 (the repo, Blender, the last render's plates) and the image's snapshot, a few
  dollars a month at most.
- **Limits:** every box shuts itself down when the queue is empty, and after `--max-hours` whatever happens; its
  shutdown terminates it.
- **No capacity:** if AWS has no capacity for the types in any zone, nothing starts and nothing is charged.

## How it works

- `render` pulls the plates already in S3, asks `film-anime-render --dry-run` which scenes are stale here, syncs the
  repo to `s3://<bucket>/repo/` (only what changed), writes `runs/<run>/queue.txt` (longest scene first), and
  starts the boxes. It tries each type in `TYPES` in every zone until it has `--gpus` boxes.
- Each box runs [boot.sh](boot.sh): it pulls the repo, then two workers take scenes off the queue. A scene is
  claimed by creating `runs/<run>/claims/<scene>` only if it doesn't exist yet, so each scene renders once however
  many boxes there are. Each worker runs `film-anime-render --only <scene> --plates-only`. NVIDIA's EGL is forced,
  so EEVEE draws on the L40S, never on Mesa's software renderer.
- Plates sync to `s3://<bucket>/plates/<film>/` every minute and at the end. Logs go to `runs/<run>/logs/`.
- The boxes take no inbound connections (no SSH). They reach S3 through their instance role, limited to the bucket.
- A plate's stamp holds the fingerprint of the code that made it. The boxes run the same code as this checkout,
  so pulled plates count as up to date here.
