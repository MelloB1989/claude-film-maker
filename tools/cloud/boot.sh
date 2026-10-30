#!/bin/bash
# boot.sh: what each GPU box runs at boot (tools/cloud/gpu-render passes it as user data, the lines above this one set
# BUCKET, REGION, FILM, RUN, WORKERS, MAX_MIN). The box's image (gpu-render image) already holds Blender, its add-ons,
# uv and the tools' Python. The box pulls the repo from S3, then each of its WORKERS takes scenes from the run's queue
# (runs/<run>/queue.txt, longest first): a scene is claimed by creating runs/<run>/claims/<scene> only if it doesn't
# exist yet, so every scene is rendered once whatever the number of boxes. Plates go to s3://<bucket>/plates/<film>/
# as they land. When the queue is empty the box shuts down, and its shutdown behaviour terminates it; a timer set at
# boot shuts it down after MAX_MIN minutes whatever happens.
set -uo pipefail
shutdown -h +"$MAX_MIN" "gpu-render: time limit" >/dev/null 2>&1
LOG=/var/log/gpu-render.log
exec > >(tee -a $LOG) 2>&1
tok() { curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300"; }
IID=$(curl -s -H "X-aws-ec2-metadata-token: $(tok)" http://169.254.169.254/latest/meta-data/instance-id)
S3=s3://$BUCKET
export AWS_DEFAULT_REGION=$REGION
echo "== $(date -u +%FT%TZ) $IID run=$RUN film=$FILM workers=$WORKERS limit=${MAX_MIN}min"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
(while sleep 60; do aws s3 cp --quiet $LOG $S3/runs/$RUN/logs/$IID.log; done) &

W=/opt/work
mkdir -p $W && cd $W
aws s3 sync --quiet $S3/repo/ repo/
export BLENDER=/opt/blender/blender HOME=/root UV_CACHE_DIR=/opt/uv-cache UV_PYTHON_INSTALL_DIR=/opt/uv-python
export __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json  # NVIDIA's EGL, never Mesa's software
(cd repo/tools && /opt/uv/uv sync -q) || { echo "uv sync failed"; shutdown -h now; exit 1; }
mkdir -p repo/out/$FILM/plates
(while sleep 60; do aws s3 sync --quiet repo/out/$FILM/plates/ $S3/plates/$FILM/; done) &
aws s3 cp --quiet $S3/runs/$RUN/queue.txt $W/queue.txt

: > $W/empty
claim() {  # create runs/<run>/claims/<scene> only if it doesn't exist: the one worker that manages it renders the scene
  local out
  out=$(aws s3api put-object --bucket $BUCKET --key runs/$RUN/claims/$1 --if-none-match '*' --body $W/empty 2>&1) && return 0
  grep -q PreconditionFailed <<< "$out" || echo "claim $1 failed: $out"
  return 1
}

worker() {
  for scene in $(cat $W/queue.txt); do
    claim $scene || continue  # another worker has it (or the claim failed: logged)
    echo "$(date -u +%T) worker $1: $scene"
    t0=$SECONDS
    (cd repo/tools && /opt/uv/uv run film-anime-render --film "$FILM" --only "$scene" --plates-only --jobs 1) \
      > $W/$scene.log 2>&1
    code=$?
    grep -E "rendered in|FAILED" $W/$scene.log
    echo "$scene exit=$code $((SECONDS - t0))s $IID" | aws s3 cp --quiet - $S3/runs/$RUN/done/$scene
    aws s3 cp --quiet $W/$scene.log $S3/runs/$RUN/logs/$scene.log
  done
}
pids=()
for k in $(seq 1 "$WORKERS"); do worker $k & pids+=($!); done
wait "${pids[@]}"  # the workers only: the log and plate uploaders run until the box goes

aws s3 sync --quiet repo/out/$FILM/plates/ $S3/plates/$FILM/
echo "== $(date -u +%FT%TZ) queue empty: shutting down"
aws s3 cp --quiet $LOG $S3/runs/$RUN/logs/$IID.log
shutdown -h now
