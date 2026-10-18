#!/usr/bin/env bash
# Timeless v3: subject mattes (BiRefNet) + depth (Video Depth Anything) on the plates, on a RunPod 4090, driven from the VM.
#
#   bash tools/filmtools/amv3/pod_prep3.sh pod <ssh-host> <ssh-port> [prep3 args...]   # on the VM: the full run
#   bash tools/filmtools/amv3/pod_prep3.sh local <DATA> [prep3 args...]                # on any box with the data (CPU: DEVICE=cpu)
#
# `pod`: rsyncs prep3.py, this script and $AMV3_DATA/plates to the pod (/workspace/amv3), runs `local` there over ssh,
# pulls mattes/ and depth/ back into $AMV3_DATA, then verifies counts and writes $AMV3_DATA/prep_sheets/<id>.jpg on the VM.
# `local`: sets up a venv (torch + transformers for BiRefNet, the Video-Depth-Anything repo + weights), then runs
# prep3.py mattes and depth over DATA/plates. Both steps skip shots whose done marker matches: re-run after any failure.
# Env: DEVICE (cuda|cpu, default cuda), VDA_MODEL (large|small, default large), VDA_INPUT (default 518),
#      PX (BiRefNet px, default 1024), DEPTH_FALLBACK=1 (Depth Anything V2 + temporal smoothing instead of VDA),
#      VENV (default /workspace/prep3venv, or ~/.cache/prep3venv when /workspace is missing).
# The pod: get it with `python -m filmtools.runpod up --name amv3-prep` (operator); `python -m filmtools.runpod ssh <id>`
# prints host and port. GPU time: setup ~6-8 min (pip + weights), BiRefNet ~2 min, VDA-Large ~3-4 min for the 35 plates
# (~2000 frames), transfer ~3-5 min each way (~0.9 GB plates up, ~2.5 GB mattes+depth down).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:?usage: pod_prep3.sh pod <host> <port> | local <DATA> [prep3 args]}"; shift

if [ "$MODE" = pod ]; then
  HOST="${1:?ssh host}"; PORT="${2:?ssh port}"; shift 2
  DATA="${AMV3_DATA:-/home/nikhil/code/film-making/work/timeless_v3}"
  SSH="ssh -o StrictHostKeyChecking=accept-new -p $PORT"
  test -d "$DATA/plates" || { echo "no plates in $DATA/plates"; exit 1; }
  $SSH "root@$HOST" 'mkdir -p /workspace/amv3/data /workspace/amv3/bin; command -v rsync >/dev/null || (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rsync >/dev/null)'
  rsync -a -e "$SSH" "$HERE/prep3.py" "$HERE/pod_prep3.sh" "root@$HOST:/workspace/amv3/bin/"
  rsync -a --info=stats1 -e "$SSH" --exclude _sheets "$DATA/plates" "root@$HOST:/workspace/amv3/data/"
  $SSH "root@$HOST" "cd /workspace/amv3 && DEVICE=\${DEVICE:-cuda} VDA_MODEL=${VDA_MODEL:-large} VDA_INPUT=${VDA_INPUT:-518} PX=${PX:-1024} DEPTH_FALLBACK=${DEPTH_FALLBACK:-0} bash bin/pod_prep3.sh local /workspace/amv3/data $*"
  rsync -a --info=stats1 -e "$SSH" "root@$HOST:/workspace/amv3/data/mattes" "root@$HOST:/workspace/amv3/data/depth" "$DATA/"
  python "$HERE/prep3.py" verify --data "$DATA" "$@" || { echo "verify: incomplete shots (re-run this command: finished shots are skipped)"; exit 1; }
  echo "done: $DATA/mattes $DATA/depth, sheets in $DATA/prep_sheets"
  exit 0
fi

[ "$MODE" = local ] || { echo "unknown mode $MODE"; exit 2; }
DATA="${1:?DATA dir}"; shift
DEVICE="${DEVICE:-cuda}"
VENV="${VENV:-$([ -d /workspace ] && echo /workspace/prep3venv || echo "$HOME/.cache/prep3venv")}"
VDA_REPO="${VDA_REPO:-$(dirname "$VENV")/Video-Depth-Anything}"
export HF_HOME="${HF_HOME:-$(dirname "$VENV")/hf}"

if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c "import torch, transformers, timm, einops, kornia, huggingface_hub, cv2" 2>/dev/null; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  if [ "$DEVICE" = cpu ]; then
    "$VENV/bin/pip" install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
  else
    for CU in cu124 cu121; do      # the first wheel set whose CUDA runs on the pod's driver
      "$VENV/bin/pip" install -q torch torchvision --index-url "https://download.pytorch.org/whl/$CU"
      "$VENV/bin/python" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" && break
    done
  fi
  # v2's pinned set (python >= 3.11, as on the pod); unpinned where those wheels do not exist (python 3.10, the VM)
  COMMON="numpy opencv-python-headless pillow scipy huggingface_hub safetensors easydict tqdm matplotlib imageio"
  "$VENV/bin/pip" install -q $COMMON transformers==5.20.1 timm==1.0.30 einops==0.8.2 kornia==0.8.3 \
  || "$VENV/bin/pip" install -q $COMMON transformers timm einops kornia
fi
"$VENV/bin/python" -c "import torch; print('torch', torch.__version__, torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
[ "$DEVICE" = cpu ] || "$VENV/bin/python" -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'"
if [ "${DEPTH_FALLBACK:-0}" != 1 ] && [ ! -d "$VDA_REPO/video_depth_anything" ]; then
  git clone -q --depth 1 https://github.com/DepthAnything/Video-Depth-Anything "$VDA_REPO"
fi
# fetch the weights first so a network problem fails now, not 10 minutes in
"$VENV/bin/python" -c "from transformers import AutoModelForImageSegmentation as M; M.from_pretrained('ZhengPeng7/BiRefNet', trust_remote_code=True); print('birefnet ok')"

T0=$(date +%s)
"$VENV/bin/python" "$HERE/prep3.py" mattes --data "$DATA" --device "$DEVICE" --px "${PX:-1024}" "$@"
T1=$(date +%s)
if [ "${DEPTH_FALLBACK:-0}" = 1 ]; then
  "$VENV/bin/python" "$HERE/prep3.py" depth --data "$DATA" --device "$DEVICE" --fallback --input-size "${VDA_INPUT:-518}" "$@"
else
  "$VENV/bin/python" "$HERE/prep3.py" depth --data "$DATA" --device "$DEVICE" --vda-repo "$VDA_REPO" \
    --model "${VDA_MODEL:-large}" --input-size "${VDA_INPUT:-518}" "$@" \
  || { echo "VDA failed: falling back to Depth Anything V2 + temporal smoothing";
       "$VENV/bin/python" "$HERE/prep3.py" depth --data "$DATA" --device "$DEVICE" --fallback --input-size "${VDA_INPUT:-518}" "$@"; }
fi
T2=$(date +%s)
echo "timing: mattes $((T1 - T0)) s, depth $((T2 - T1)) s"
