#!/usr/bin/env bash
# finals.sh OUTDIR [samples=8] [port=5313] [shots...]: the v3 deliverables, one render per shot, on a host with bun,
# Chrome and ffmpeg (the render Mac). Run from app/.
#   <id>_full.mov   every beat full frame (ProRes 422 HQ), exactly its EDL frames + 12 tail (render.ts --only <id>)
#   <id>_panel.mov  the panel beats: <id>_k (over black) and <id>_g (over grey) from films/explain-whatsapp-panel,
#                   turned into straight alpha (tools/alpha.ts) as ProRes 4444
# Each file's frame count is checked against the EDL.
set -euo pipefail
OUT=$1 SAMPLES=${2:-8} PORT=${3:-5313}
shift 3 || true
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
want() { python3 -c "import json,sys; e=json.load(open('$HERE/../data/edl.json')); print([s['frames']+12 for s in e['shots'] if s['gfx']==sys.argv[1]][0])" "$1"; }
kind() { python3 -c "import json,sys; e=json.load(open('$HERE/../data/edl.json')); print([s['kind'] for s in e['shots'] if s['gfx']==sys.argv[1]][0])" "$1"; }
count() { ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$1"; }
render() { # film id out
  bun scripts/render.ts video --film "$1" --only "$2" --prores --noaudio --samples "$SAMPLES" --shutter 0.5 --fresh --url "http://localhost:$PORT" --out "$3" 2>&1 | grep -E 'wrote|FAILED' || true
  [ -f "$3" ] || { echo "finals.sh: $3 failed"; exit 1; }
}
SHOTS=("$@")
[ ${#SHOTS[@]} -gt 0 ] || SHOTS=(title connect erlang store ticks group e2e media end)
for s in "${SHOTS[@]}"; do
  n=$(want "$s")
  render explain-whatsapp "$s" "$OUT/${s}_full.mov"
  got=$(count "$OUT/${s}_full.mov"); [ "$got" = "$n" ] || { echo "finals.sh: ${s}_full.mov has $got frames, want $n"; exit 1; }
  echo "${s}_full.mov $got frames"
  if [ "$(kind "$s")" = panel ]; then
    render explain-whatsapp-panel "${s}_k" "$OUT/_${s}_k.mov"
    render explain-whatsapp-panel "${s}_g" "$OUT/_${s}_g.mov"
    bun "$HERE/alpha.ts" "$OUT/_${s}_k.mov" "$OUT/_${s}_g.mov" "$OUT/${s}_panel.mov" --grey 128 --frames "$n"
    rm -f "$OUT/_${s}_k.mov" "$OUT/_${s}_g.mov"
    got=$(count "$OUT/${s}_panel.mov"); [ "$got" = "$n" ] || { echo "finals.sh: ${s}_panel.mov has $got frames, want $n"; exit 1; }
    echo "${s}_panel.mov $got frames"
  fi
done
