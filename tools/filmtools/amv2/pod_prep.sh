#!/usr/bin/env bash
# RunPod 4090 pod: RIFE 240 fps copies + BiRefNet mattes for Timeless v2.
#   bash tools/filmtools/amv2/pod_prep.sh [OUT_DIR]        (OUT_DIR default: $REPO/out/timeless/amv2_data)
# The repo must be at the same path as on the other machines (/home/nikhil/code/claude-film-maker, branch amv2 or later),
# with the handover footage at /home/nikhil/code/film-making/handover/amv_handover (override: AMV_HANDOVER=...).
# Results: OUT_DIR/src240/clip_<ID>.mp4 (+ .json), OUT_DIR/mattes/<ID>/NNNNN.png. Copy OUT_DIR to $AMV2_DATA.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT="${1:-$REPO/out/timeless/amv2_data}"
export AMV_HANDOVER="${AMV_HANDOVER:-/home/nikhil/code/film-making/handover/amv_handover}"
export FILMTOOLS_CACHE="${FILMTOOLS_CACHE:-$HOME/.cache/filmtools}"
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
MATTE_CLIPS=A03_sunset_mask,M08_shuriken,T03_glove_city,M14_head_raise,M16_sunset_hero,T01_mask_night

test -d "$AMV_HANDOVER/footage_clips" || { echo "missing $AMV_HANDOVER/footage_clips"; exit 1; }
nvidia-smi -L

# system: ffmpeg >= 5.1 (needs -fps_mode) with libx264. The pod image ships 4.4, so fetch a static build when the test fails.
ffmpeg_ok() {
  command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null &&
  ffmpeg -v error -f lavfi -i color=c=black:s=64x64:d=0.1 -fps_mode passthrough -c:v libx264 -f null - 2>/dev/null
}
if ! ffmpeg_ok; then
  echo "ffmpeg missing or too old ($(ffmpeg -version 2>/dev/null | head -1)); fetching a static build"
  TMP="$(mktemp -d)"
  (command -v curl >/dev/null || { apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl xz-utils; })
  curl -fL --retry 3 -o "$TMP/ff.tar.xz" https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
  tar -xf "$TMP/ff.tar.xz" -C "$TMP"
  install -m 0755 "$TMP"/ffmpeg-*-static/ffmpeg "$TMP"/ffmpeg-*-static/ffprobe /usr/local/bin/
  hash -r
  rm -rf "$TMP"
fi
ffmpeg_ok || { echo "no usable ffmpeg (>= 5.1 with libx264)"; exit 1; }
ffmpeg -version | head -1

# python: an isolated venv so the pod image's torch cannot clash
python3 -m venv /workspace/prepvenv 2>/dev/null || python3 -m venv "$HOME/prepvenv"
VENV="$([ -d /workspace/prepvenv ] && echo /workspace/prepvenv || echo "$HOME/prepvenv")"
"$VENV/bin/pip" install -q --upgrade pip
for CU in cu124 cu121; do      # the first wheel set whose CUDA runs on the pod's driver
  "$VENV/bin/pip" install -q torch torchvision --index-url "https://download.pytorch.org/whl/$CU"
  "$VENV/bin/python" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" && break
done
"$VENV/bin/pip" install -q numpy opencv-python-headless pillow scipy transformers==5.20.1 timm==1.0.30 einops==0.8.2 kornia==0.8.3 huggingface_hub safetensors
"$VENV/bin/python" -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'; print('torch', torch.__version__, torch.cuda.get_device_name(0))"

export PYTHONPATH="$REPO/tools"
export FILM_BIN="$(dirname "$(command -v ffmpeg)")"
mkdir -p "$OUT"

# fetch the RIFE and BiRefNet weights first so a network problem fails now, not 20 minutes in
"$VENV/bin/python" -m filmtools.amv.interp.rife --fetch
"$VENV/bin/python" -c "from transformers import AutoModelForImageSegmentation as M; M.from_pretrained('ZhengPeng7/BiRefNet', trust_remote_code=True); print('birefnet ok')"

# 1. RIFE 240 fps for every handover clip
"$VENV/bin/python" -m filmtools.amv2.prep rife240 --out "$OUT/src240" --device cuda --batch 6
# 2. subject mattes on the 240 fps copies
"$VENV/bin/python" -m filmtools.amv2.prep mattes --clips "$MATTE_CLIPS" --src240 "$OUT/src240" --out "$OUT/mattes" --device cuda --batch 8
echo "done: $OUT"; du -sh "$OUT"/src240 "$OUT"/mattes
