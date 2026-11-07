#!/usr/bin/env bash
# Render the Netflix explainer graphics in the a12-render image (Chromium + ffmpeg + bun; software WebGL).
#   films/explain-netflix/render.sh sheets [ids...]        contact sheets → out/explain-netflix/sheets/<id>.png
#   films/explain-netflix/render.sh full <id> [from to]    ProRes 422 HQ of the shot → out/explain-netflix/<id>_full.mov
#   alpha deliverables: films/explain-netflix/tools/matte.sh (FRAMES.md)
# Run inside the image (or a host with bun, Chromium and ffmpeg) from the repo root.
set -euo pipefail
cd "$(dirname "$0")/../../app"
FILM=explain-netflix
OUT=../out/$FILM
R=(bun scripts/render.ts)
COMMON=(--film $FILM --allow-software --fresh)
mode=$1; shift
case $mode in
  sheets)
    ids=${*:-title oca prefill prefill_panel ladder abr buffer buffer_panel planes end lowerthird}
    for id in $ids; do "${R[@]}" sheet "${COMMON[@]}" --only "$id" --n 12 --cols 4 --out "$OUT/sheets/$id.png" 2>&1 | grep -v "GL Driver\|BROWSER LOG" || true; done ;;
  full)
    id=$1; "${R[@]}" video "${COMMON[@]}" --only "$id" --prores --noaudio --out "$OUT/${id}_full.mov" ;;
esac
