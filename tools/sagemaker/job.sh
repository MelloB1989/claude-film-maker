#!/bin/bash
# job.sh: what one SageMaker training job runs (tools/sagemaker/sm-render starts it). It renders the Blender plates of
# the scenes in $ONLY for $FILM on the job's NVIDIA GPU and leaves them in /opt/ml/checkpoints/out, which SageMaker
# copies to S3 as they are written (an interrupted spot job keeps what it finished). Channels, downloaded by SageMaker:
#   repo     the repo tree (sm-render syncs it to S3; no out/, no venvs)
#   blender  the Linux Blender tarball          addons  extensions/user_default/*.tar.gz (the VRM add-on)
set -euo pipefail
IN=/opt/ml/input/data
OUT=/opt/ml/checkpoints
W=/opt/ml/work  # on the job's own volume: the image's root disk is small (nothing big or temporary goes there)
mkdir -p $OUT/logs $W/tmp $W/home
chmod 1777 /tmp $W/tmp 2>/dev/null || true
export TMPDIR=$W/tmp HOME=$W/home
# the image's own library and Python paths (Intel-built libraries, its conda Python) must not leak into Blender
unset LD_LIBRARY_PATH LD_PRELOAD PYTHONPATH PYTHONHOME
for d in /usr/local/nvidia/lib64 /usr/local/nvidia/lib; do  # where some hosts mount the driver: keep only that
  [ -d $d ] && export LD_LIBRARY_PATH=${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$d
done
exec > >(tee -a $OUT/logs/job.log) 2>&1
echo "== $(date -u +%FT%TZ) film=$FILM jobs=$JOBS only=$ONLY"
df -h / /opt/ml 2>/dev/null | sed 1d

# the GPU, and its graphics side: EEVEE draws through EGL, and only NVIDIA's (no silent fallback to Mesa's software)
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
export DEBIAN_FRONTEND=noninteractive
apt-get -o APT::Sandbox::User=root update -qq >/dev/null || echo "apt-get update failed: using the image's libraries"
apt-get -o APT::Sandbox::User=root install -y -qq libegl1 libgl1 libxi6 libxkbcommon0 libsm6 libxxf86vm1 libxfixes3 libxrender1 libxext6 \
  libx11-6 >/dev/null || echo "apt-get install failed: using the image's libraries"
if ! ldconfig -p | grep -q libEGL_nvidia; then
  echo "FATAL: no libEGL_nvidia in the container (the job needs NVIDIA_DRIVER_CAPABILITIES=all): not rendering on the CPU"
  exit 3
fi
mkdir -p /usr/share/glvnd/egl_vendor.d
[ -f /usr/share/glvnd/egl_vendor.d/10_nvidia.json ] || \
  echo '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
export __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json

# Blender, its add-ons, the repo (its out/ is the checkpoint dir, so every plate goes to S3 as it lands)
tar -xJf $IN/blender/*.tar.xz -C $W
export BLENDER=$(ls -d $W/blender-*-linux-x64)/blender
missing=$(ldd "$BLENDER" | grep "not found" || true)
[ -n "$missing" ] && { echo "FATAL: Blender's libraries missing in the image:"; echo "$missing"; exit 4; }
"$BLENDER" --version | head -1
EXT=~/.config/blender/$("$BLENDER" --version | head -1 | grep -o '[0-9]\+\.[0-9]\+' | head -1)/extensions/user_default
mkdir -p $EXT && for t in $IN/addons/*.tar.gz; do tar -xzf $t -C $EXT; done
cp -a $IN/repo $W/repo && cd $W/repo
mkdir -p $OUT/out && rm -rf out && ln -s $OUT/out out
export UV_INSTALL_DIR=$W/uv UV_CACHE_DIR=$W/uv-cache UV_PYTHON_INSTALL_DIR=$W/uv-python
curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null
export PATH=$W/uv:$PATH
(cd tools && uv sync -q)

# a GPU-use trace beside the plates (to see what the GPU did), then the render
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv -l 15 > $OUT/logs/gpu.csv &
cd tools && uv run film-anime-render --film "$FILM" --only "$ONLY" --plates-only --jobs "$JOBS" 2>&1 | tee $OUT/logs/render.log
status=${PIPESTATUS[0]}
echo "== $(date -u +%FT%TZ) done, exit $status"
exit $status
