#!/bin/bash
# On the box: a preview frame dir (S13-S18 JPEGs, master frame numbers) -> MP4 with the reel mix (master frame 0 =
# mix 0 s), then KMS upload to private/renders/r4/review/<name>.mp4 + head-object. Face data: private only.
#   bash encode_preview.sh /srv/ue/reel/r4/preview/cast_op5 cast_op5
set -euo pipefail
D=$1; NAME=$2; T=${TREE:-/srv/ue/r3tree}
mkdir -p "$D/_mp4"; cd "$D"
F0=$(ls [0-9]*.jpeg | sort -n | head -1 | sed 's/\.jpeg//'); N=$(ls [0-9]*.jpeg | wc -l)
A=$T/films/host-studio/reel/audio/mix/mix.wav
OFF=$(python3 -c "print($((10#$F0))/24)")
OUT=$D/_mp4/$NAME.mp4
ffmpeg -y -loglevel error -framerate 24 -start_number $((10#$F0)) -i "$D/%04d.jpeg" -ss "$OFF" -i "$A" \
  -map 0:v -map 1:a -shortest -c:v libx264 -crf 20 -pix_fmt yuv420p -c:a aac -b:a 160k "$OUT"
echo "first=$F0 frames=$N audio_offset_s=$OFF mp4=$OUT bytes=$(stat -c %s "$OUT")"
KEY=ue-linux/private/renders/r4/review/$NAME.mp4
aws s3 cp --only-show-errors "$OUT" "s3://rf-render-788655295054-aps1/$KEY" --sse aws:kms
aws s3api head-object --bucket rf-render-788655295054-aps1 --key "$KEY" --query '[ServerSideEncryption,ContentLength]' --output text
