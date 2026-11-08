#!/bin/bash
# The explainers' composite on a box, CPU only (never the editor or the GPU): graphics synced from s3, composite.py,
# a contact sheet and stills, agent-09's cut QA (qa_av.py all) and the upload to the private review prefix.
#
#   comp_box.sh <film> <tag> [presenter dir] ["stills"]
#   comp_box.sh netflix v3                         # her finals from /srv/ue/explainer/renders/netflix/final
#   comp_box.sh whatsapp v1 "" "48 240 600"
#   PLACEHOLDER=1 comp_box.sh whatsapp p1 none     # graphics-only dry run (missing shots become labelled slugs)
#   PRES_S3=private/renders/r7/farm/explain/netflix/final comp_box.sh netflix v3   # r7: the farm's finals, synced first
#   RENDER_BUCKET=s3://rf-render-788655295054-apne1 PRES_S3=… comp_box.sh netflix v3   # on a Tokyo box (T, T2)
#
# SRC is this checkout's root (default: the tree this script sits in); TOOLS a tools/ with filmtools for qc_ok
# (default: SRC/tools if present, else /srv/ue/r5tree/tools). Outputs: /srv/ue/explain/<film>/out_<tag>/.
set -euo pipefail
FILM=$1; TAG=$2; PRES=${3:-}; STILLS=${4:-"48 240 600"}
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${SRC:-$(cd "$HERE/../../.." && pwd)}
TOOLS=${TOOLS:-$([ -d "$SRC/tools/filmtools" ] && echo "$SRC/tools" || echo /srv/ue/r5tree/tools)}
# r7 cost policy: same-region data only, so a Tokyo box reads the Tokyo bucket (RENDER_BUCKET=s3://rf-render-788655295054-apne1)
B=${RENDER_BUCKET:-s3://rf-render-788655295054-aps1}/ue-linux
case $B in *-apne1/*) export AWS_REGION=${AWS_REGION:-ap-northeast-1} ;; *) export AWS_REGION=${AWS_REGION:-ap-south-1} ;; esac
EX=$SRC/films/host-studio/explainers
GFXP=${GFXP:-gfx/v3/explain-$FILM}  # the v3 graphics (orchestrator); GFXP=gfx/explain-<film> for v2
GFX=/srv/ue/explain/$FILM/gfx_${GFXP//\//_}
OUT=/srv/ue/explain/$FILM/out_$TAG
[ -z "$PRES" ] && PRES=/srv/ue/explainer/renders/$FILM/final
# r7: the finals come from the render farm (agent-07): shot<NN>_<CAM>/<frame>.png under PRES_S3, synced onto this box
if [ -n "${PRES_S3:-}" ]; then
    PRES=/srv/ue/explain/$FILM/pres_${PRES_S3//\//_}
    aws s3 sync --only-show-errors "$B/$PRES_S3/" "$PRES/"
fi
UV="nice -n 10 $HOME/.local/bin/uv run --no-project --with pillow --with imageio-ffmpeg --with numpy"

aws s3 sync --only-show-errors --delete --exclude 'review/*' --exclude '*.tar' --exclude '_*' "$B/$GFXP/" "$GFX/"
rm -rf "$OUT"; mkdir -p "$OUT"
args=(--film "$FILM" --gfx "$GFX" --out "$OUT" --tag "$TAG" --ffmpeg "$(command -v ffmpeg)")
[ "$PRES" != none ] && args+=(--presenter "$PRES")
[ -n "${PLACEHOLDER:-}" ] && args+=(--placeholder --no-prores)
$UV python "$EX/composite.py" "${args[@]}" 2>&1 | tee "$OUT/_composite.log"
[ "${PIPESTATUS[0]}" = 0 ] || exit 1
NAME=${FILM}_r6_$TAG
MP4=$OUT/$NAME.mp4
N=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$MP4")
nice ffmpeg -y -loglevel error -i "$MP4" -vf "select=not(mod(n\,24)),scale=640:-1,tile=4x$(( (N / 24 + 4) / 4 ))" \
    -frames:v 1 "$OUT/${NAME}_contact.jpg"
for f in $STILLS; do nice ffmpeg -y -loglevel error -i "$MP4" -vf "select=eq(n\,$f)" -frames:v 1 "$OUT/${NAME}_f$f.png"; done
(cd "$EX" && PYTHONPATH=$TOOLS $UV python qa_av.py all "$MP4" "$OUT/$NAME.srt" "audio/$FILM/cues.json" \
    --facts "facts_$FILM.json" --out "$OUT/${NAME}_qa_cut.json" > "$OUT/_qa.log" 2>&1) || true
python3 - "$OUT/${NAME}_qa_cut.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
rows = d.get("gate", d.get("rows", d))
for k, v in (rows.items() if isinstance(rows, dict) else []):
    if isinstance(v, dict) and "value" in v:
        print(f"  {k}: {v['value']}" + (f"  ERROR {v['error']}" if v.get("error") else ""))
EOF
aws s3 cp --recursive --sse aws:kms --only-show-errors --exclude 'comp_*' "$OUT/" "$B/private/renders/r6/review/explain/"
ls -la "$OUT" | grep -v comp_
