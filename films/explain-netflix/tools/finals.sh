#!/usr/bin/env bash
# finals.sh <out_dir> [shots...] : the v3 graphics deliverables, rendered on a GPU host (the Mac render host).
#   full shots      <id>_full.mov  ProRes 422 HQ, 8-sample motion blur, exactly the frames the shot owns (EDL + 12 tail)
#   alpha overlays  prefill_panel.mov, buffer_panel.mov, lowerthird.mov  ProRes 4444: stills over black and over grey
#                   (the films explain-netflix-black / -grey), straight alpha by alpha.py, encoded with ffmpeg
# Every render.ts call takes the host's render lock (an atomic mkdir: macOS has no flock) and releases it after, so
# other agents' renders interleave; alpha.py and the encodes run outside it.
# Env: PY (a python3 with numpy + PIL, default python3), LOCK (default ~/fleet-render/.render.lock), SAMPLES (8),
#      RENDER_FLAGS (extra render.ts flags, e.g. --allow-software on a host without a GPU).
set -euo pipefail
mkdir -p "$1"; OUT=$(cd "$1" && pwd); shift
REPO=$(cd "$(dirname "$0")/../../.." && pwd); APP=$REPO/app
PY=${PY:-python3} LOCK=${LOCK:-$HOME/fleet-render/.render.lock} SAMPLES=${SAMPLES:-8}
FULL=(title oca prefill ladder abr buffer planes end)
ALPHA=(prefill_panel buffer_panel lowerthird)
want=("$@"); [ ${#want[@]} -gt 0 ] || want=("${FULL[@]}" "${ALPHA[@]}")
locked() { until mkdir "$LOCK" 2>/dev/null; do sleep 5; done; trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT; local rc=0; "$@" || rc=$?; rmdir "$LOCK"; trap - EXIT; return $rc; }
# a shot's first film frame and frame count (FRAMES.md: the EDL frames + 12 tail, after a 1.5 frame lead)
frames_of() { case $1 in prefill_panel) echo 344 162;; buffer_panel) echo 926 98;; lowerthird) echo 1200 72;; *) echo "finals: no frames for $1" >&2; exit 1;; esac; }
cd "$APP"
for id in "${want[@]}"; do
  if [[ " ${FULL[*]} " == *" $id "* ]]; then
    locked bun scripts/render.ts video --film explain-netflix --fresh --only "$id" --prores --noaudio --samples "$SAMPLES" ${RENDER_FLAGS:-} --out "$OUT/${id}_full.mov" 2>&1 | grep -E "^wrote|rror" || true
    [ -s "$OUT/${id}_full.mov" ] || { echo "finals: $id failed"; exit 1; }
  else
    read -r F0 N <<<"$(frames_of "$id")"
    TMP=$REPO/out/explain-netflix/matte/$id; rm -rf "$TMP"; mkdir -p "$TMP"
    times=$(python3 -c "import sys; f0,n=map(int,sys.argv[1:]); print(','.join(f'{k/24:.6f}' for k in range(f0,f0+n)))" "$F0" "$N")
    for m in black grey; do
      locked bun scripts/render.ts stills --film explain-netflix-$m --fresh --only "$id" ${RENDER_FLAGS:-} --t "$times" --out "$TMP/$m" > "$TMP/render_$m.log" 2>&1 || { echo "finals: $id $m failed ($TMP)"; exit 1; }
    done
    "$PY" "$REPO/films/explain-netflix/tools/alpha.py" "$TMP/black" "$TMP/grey" "$TMP/rgba"
    [ "$(ls "$TMP/rgba" | wc -l | tr -d ' ')" -eq "$N" ] || { echo "finals: $id expected $N frames"; exit 1; }
    ffmpeg -y -loglevel error -framerate 24 -i "$TMP/rgba/%05d.png" -c:v prores_ks -profile:v 4 -pix_fmt yuva444p10le -alpha_bits 16 -vendor apl0 "$OUT/$id.mov"
    echo "wrote $OUT/$id.mov ($N frames)"
  fi
done
