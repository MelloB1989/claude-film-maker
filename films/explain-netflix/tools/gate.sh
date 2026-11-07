#!/usr/bin/env bash
# gate.sh <out.json> : the caption-band gate (gfx.caption_band_clear) of the v3 graphics: every 3rd frame of every shot
# rendered over black (explain-netflix-black: a matte pass, the graphic alone), checked by bandcheck.py (900 px for full
# shots, 918 for the panels and the lower third). Each render takes the host's render lock (finals.sh's rule).
# Env: PY (python3 with numpy + PIL), LOCK.
set -euo pipefail
OUTJ=$1
REPO=$(cd "$(dirname "$0")/../../.." && pwd); APP=$REPO/app
PY=${PY:-python3} LOCK=${LOCK:-$HOME/fleet-render/.render.lock}
TMP=$REPO/out/explain-netflix/gate; rm -rf "$TMP"; mkdir -p "$TMP"
locked() { until mkdir "$LOCK" 2>/dev/null; do sleep 5; done; trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT; local rc=0; "$@" || rc=$?; rmdir "$LOCK"; trap - EXIT; return $rc; }
# shot first frame count (FRAMES.md)
SHOTS="title 2 67|oca 69 113|prefill 182 162|prefill_panel 344 162|ladder 506 147|abr 653 175|buffer 828 98|buffer_panel 926 98|planes 1024 128|end 1152 48|lowerthird 1200 72"
args=()
cd "$APP"
IFS='|'; for row in $SHOTS; do
  IFS=' ' read -r id f0 n <<<"$row"
  times=$(python3 -c "import sys; f0,n=map(int,sys.argv[1:]); print(','.join(f'{k/24:.6f}' for k in range(f0,f0+n,3)))" "$f0" "$n")
  locked bun scripts/render.ts stills --film explain-netflix-black --fresh --only "$id" --t "$times" --out "$TMP/$id" > "$TMP/$id.log" 2>&1 || { echo "gate: $id render failed"; exit 1; }
  lim=900; [[ $id == *_panel || $id == lowerthird ]] && lim=918
  args+=("$id=$TMP/$id@$lim")
done; IFS=$' \t\n'
"$PY" "$REPO/films/explain-netflix/tools/bandcheck.py" "$OUTJ" "${args[@]}"
