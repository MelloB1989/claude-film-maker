#!/usr/bin/env bash
# Timeless v3: eye / lens region masks (SAM 2.1 video predictor) on the plates, on a RunPod 4090, driven from the VM.
#
#   bash tools/filmtools/amv3/pod_regions.sh pod <ssh-host> <ssh-port> [--only S08,S17]   # on the VM: the full run
#   bash tools/filmtools/amv3/pod_regions.sh local <DATA> [--only ...] [--out DIR]       # any box with the data
#
# `pod`: rsyncs regions.py, this script, the plates of the region shots and tracks/ to the pod (/workspace/amv3), runs
# `local` there over ssh (sam -> post -> sheets), pulls regions/ back into $AMV3_DATA/regions, then verifies frame
# counts on the VM. Re-running is safe (each shot is recomputed; ~10-20 s per shot on the 4090).
# `local`: sets up a venv (torch + SAM 2 from github, weights from Hugging Face), then runs regions.py sam, post and sheets
# (and verify unless FRAMES is set).
# Env: DEVICE (cuda|cpu, default cuda), SAM_MODEL (large|base_plus|small|tiny, default large), FRAMES (a test window:
#      A-B plate frames, or N = N frames around each shot's first prompt frame), VENV (default /workspace/sam2venv, or ~/.cache/sam2venv when /workspace is missing).
# The pod: the operator's (`python -m filmtools.runpod ssh <id>` prints host and port). GPU time: setup ~4-6 min (torch +
# sam2 pip, 0.9 GB weights), SAM ~2-3 min for the 9 shots (~420 unique frames), transfer ~1 min up (~220 MB of plates),
# ~1 min down.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:?usage: pod_regions.sh pod <host> <port> [--only ...] | local <DATA> [--only ...] [--out DIR]}"; shift
SHOTS="S01 S05 S08 S09 S16 S17 S18 S25 S31"

if [ "$MODE" = pod ]; then
  HOST="${1:?ssh host}"; PORT="${2:?ssh port}"; shift 2
  DATA="${AMV3_DATA:-/home/nikhil/code/film-making/work/timeless_v3}"
  SSH="ssh -o StrictHostKeyChecking=accept-new -p $PORT"
  for s in $SHOTS; do test -f "$DATA/plates/$s/plate.json" || { echo "missing plates: $DATA/plates/$s"; exit 1; }; done
  test -d "$DATA/tracks" || { echo "no tracks in $DATA/tracks"; exit 1; }
  $SSH "root@$HOST" 'mkdir -p /workspace/amv3/data/plates /workspace/amv3/bin; command -v rsync >/dev/null || (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rsync >/dev/null)'
  rsync -a -e "$SSH" "$HERE/regions.py" "$HERE/pod_regions.sh" "root@$HOST:/workspace/amv3/bin/"
  rsync -a --info=stats1 -e "$SSH" $(for s in $SHOTS; do echo "$DATA/plates/$s"; done) "root@$HOST:/workspace/amv3/data/plates/"
  rsync -a -e "$SSH" --exclude _sheets --exclude _probe "$DATA/tracks" "root@$HOST:/workspace/amv3/data/"
  $SSH "root@$HOST" "cd /workspace/amv3 && DEVICE=\${DEVICE:-cuda} SAM_MODEL=${SAM_MODEL:-large} FRAMES=${FRAMES:-} bash bin/pod_regions.sh local /workspace/amv3/data $*"
  mkdir -p "$DATA/regions"
  rsync -a --info=stats1 -e "$SSH" "root@$HOST:/workspace/amv3/data/regions/" "$DATA/regions/"
  python "$HERE/regions.py" verify --data "$DATA" "$@" || { echo "verify: incomplete shots (re-run this command)"; exit 1; }
  echo "done: $DATA/regions/<shot>/<kind>/, check sheets in $DATA/regions/_sheets"
  exit 0
fi

[ "$MODE" = local ] || { echo "unknown mode $MODE"; exit 2; }
DATA="${1:?DATA dir}"; shift
DEVICE="${DEVICE:-cuda}"
VENV="${VENV:-$([ -d /workspace ] && echo /workspace/sam2venv || echo "$HOME/.cache/sam2venv")}"
export HF_HOME="${HF_HOME:-$(dirname "$VENV")/hf}"
export SAM2_BUILD_CUDA=0          # skip the optional CUDA extension (only used for hole filling, which post does itself)

if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c "import torch, cv2, hydra, huggingface_hub, sam2.sam2_video_predictor" 2>/dev/null; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip setuptools wheel
  if [ "$DEVICE" = cpu ]; then
    "$VENV/bin/pip" install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
  else
    for CU in cu124 cu121; do      # the first wheel set whose CUDA runs on the pod's driver
      "$VENV/bin/pip" install -q torch torchvision --index-url "https://download.pytorch.org/whl/$CU"
      "$VENV/bin/python" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" && break
    done
  fi
  "$VENV/bin/pip" install -q numpy opencv-python-headless pillow huggingface_hub hydra-core iopath tqdm
  "$VENV/bin/pip" install -q --no-build-isolation "git+https://github.com/facebookresearch/sam2.git" \
  || "$VENV/bin/pip" install -q --no-build-isolation sam2
fi
"$VENV/bin/python" -c "import torch; print('torch', torch.__version__, torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
[ "$DEVICE" = cpu ] || "$VENV/bin/python" -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'"
# fetch the weights first so a network problem fails now
"$VENV/bin/python" -c "from sam2.sam2_video_predictor import SAM2VideoPredictor as P; import sys; sys.path.insert(0, '$HERE'); from regions import MODELS; P.from_pretrained(MODELS['${SAM_MODEL:-large}'], device='cpu'); print('sam2 weights ok')"

T0=$(date +%s)
"$VENV/bin/python" "$HERE/regions.py" sam --data "$DATA" --device "$DEVICE" --model "${SAM_MODEL:-large}" \
  ${FRAMES:+--frames "$FRAMES"} "$@"
T1=$(date +%s)
"$VENV/bin/python" "$HERE/regions.py" post --data "$DATA" "$@"
"$VENV/bin/python" "$HERE/regions.py" sheets --data "$DATA" "$@"
[ -n "${FRAMES:-}" ] || "$VENV/bin/python" "$HERE/regions.py" verify --data "$DATA" "$@" || true
T2=$(date +%s)
echo "timing: sam $((T1 - T0)) s, post+sheets $((T2 - T1)) s"
