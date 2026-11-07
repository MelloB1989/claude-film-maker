#!/bin/bash
# The explainers' composite on a box, CPU only (never the editor or the GPU): graphics synced from s3, composite.py,
# a contact sheet and stills, agent-09's cut QA (qa_av.py all) and the upload to the private review prefix.
#
#   comp_box.sh <film> <tag> [presenter dir] ["stills"]
#   comp_box.sh netflix v3                         # her finals from /srv/ue/explainer/renders/netflix/final
#   comp_box.sh whatsapp v1 "" "48 240 600"
#   PLACEHOLDER=1 comp_box.sh whatsapp p1 none     # graphics-only dry run (missing shots become labelled slugs)
#
# SRC is this checkout's root (default: the tree this script sits in); TOOLS a tools/ with filmtools for qc_ok
# (default: SRC/tools if present, else /srv/ue/r5tree/tools). Outputs: /srv/ue/explain/<film>/out_<tag>/.
set -euo pipefail
FILM=$1; TAG=$2; PRES=${3:-}; STILLS=${4:-"48 240 600"}
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${SRC:-$(cd "$HERE/../../.." && pwd)}
TOOLS=${TOOLS:-$([ -d "$SRC/tools/filmtools" ] && echo "$SRC/tools" || echo /srv/ue/r5tree/tools)}
B=s3://rf-render-788655295054-aps1/ue-linux
export AWS_REGION=${AWS_REGION:-ap-south-1}
EX=$SRC/films/host-studio/explainers
GFX=/srv/ue/explain/$FILM/gfx
OUT=/srv/ue/explain/$FILM/out_$TAG
[ -z "$PRES" ] && PRES=/srv/ue/explainer/renders/$FILM/final
UV="nice -n 10 $HOME/.local/bin/uv run --no-project --with pillow --with imageio-ffmpeg --with numpy"

aws s3 sync --only-show-errors --delete --exclude 'review/*' --exclude '*.tar' --exclude '_*' "$B/gfx/explain-$FILM/" "$GFX/"
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
rows = d.get("rows", d)
for k, v in (rows.items() if isinstance(rows, dict) else []):
    if isinstance(v, dict) and "value" in v:
        print(f"  {k}: {v['value']}" + (f"  ERROR {v['error']}" if v.get("error") else ""))
EOF
aws s3 cp --recursive --sse aws:kms --only-show-errors --exclude 'comp_*' "$OUT/" "$B/private/renders/r6/review/explain/"
ls -la "$OUT" | grep -v comp_
