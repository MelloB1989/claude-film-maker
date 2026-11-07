#!/usr/bin/env bash
# matte.sh <shot> <first_frame> <nframes> <out.mov> [nshards=8] [port_base=5450]
# An alpha deliverable of one shot: its frames rendered as lossless PNG stills over black and over grey
# (the films explain-netflix-black and -grey), in parallel shards (one Vite server each), turned into straight-alpha PNGs (alpha.py) and encoded as
# ProRes 4444 with alpha. Frames are film frames (24 fps; FRAMES.md). Run from the repo checkout, on a render host with
# bun, Chromium (or Chrome), ffmpeg and python3-numpy/PIL.
set -euo pipefail
SHOT=$1 F0=$2 N=$3 OUT=$4 NS=${5:-8} BASE=${6:-5450}
REPO=$(cd "$(dirname "$0")/../../.." && pwd); APP=$REPO/app
TMP=$REPO/out/explain-netflix/matte/$SHOT; rm -rf "$TMP"; mkdir -p "$TMP"
cd "$APP"
for m in black grey; do
  PIDS=()
  for ((i = 0; i < NS; i++)); do
    times=$(python3 -c "import sys; f0,n,ns,i=map(int,sys.argv[1:]); print(','.join(f'{k/24:.6f}' for k in range(f0+i*n//ns, f0+(i+1)*n//ns)))" "$F0" "$N" "$NS" "$i")
    [ -n "$times" ] || continue
    ( port=$((BASE + i)); FILM_NO_HMR=1 node node_modules/vite/bin/vite.js --host 127.0.0.1 --port $port --strictPort > "$TMP/vite_${m}_$i.log" 2>&1 & vp=$!
      for k in $(seq 300); do curl -sf -o /dev/null http://127.0.0.1:$port/ && break; sleep 0.2; done
      bun scripts/render.ts stills --film explain-netflix-$m --allow-software --url http://127.0.0.1:$port --only "$SHOT" --t "$times" --out "$TMP/$m" > "$TMP/render_${m}_$i.log" 2>&1; rc=$?
      kill $vp 2>/dev/null || true; exit $rc ) &
    PIDS+=($!)
  done
  for p in "${PIDS[@]}"; do wait "$p" || { echo "matte.sh: a $m shard failed (logs in $TMP)"; exit 1; }; done
  echo "$SHOT $m: $(ls "$TMP/$m" | wc -l) frames"
done
python3 "$REPO/films/explain-netflix/tools/alpha.py" "$TMP/black" "$TMP/grey" "$TMP/rgba"
[ "$(ls "$TMP/rgba" | wc -l)" -eq "$N" ] || { echo "matte.sh: expected $N frames"; exit 1; }
ffmpeg -y -loglevel error -framerate 24 -i "$TMP/rgba/%05d.png" -c:v prores_ks -profile:v 4 -pix_fmt yuva444p10le -alpha_bits 16 -vendor apl0 "$OUT"
echo "$OUT"
