#!/usr/bin/env bash
# gate.sh OUT.json [port=5813]: gfx.caption_band_clear for the WhatsApp v3 graphics, the quick form: every 3rd frame of
# every shot of films/explain-whatsapp-black (the beats full frame, then the panels; over black, params.matte) as
# stills, gathered into a mov in film order, checked by bandcheck.ts --stride 3. Run from app/ on a render host (bun,
# a browser, ffmpeg). Env: RENDER_FLAGS (--allow-software without a GPU).
set -euo pipefail
OUTJ=$1 PORT=${2:-5813}
HERE=$(cd "$(dirname "$0")" && pwd)
TMP=$(mktemp -d)
times=$(python3 - "$HERE/../data/edl.json" <<'PY'
import json, sys
e = json.load(open(sys.argv[1])); T = 12
shots = [s['frames'] + T for s in e['shots']] + [s['frames'] + T for s in e['shots'] if s['kind'] == 'panel']
f, out = 1, []
for n in shots:
    out += [f'{(f + k) / 24:.6f}' for k in range(0, n, 3)]
    f += n
print(','.join(out))
PY
)
bun scripts/render.ts stills --film explain-whatsapp-black --t "$times" --fresh --url "http://localhost:$PORT" ${RENDER_FLAGS:-} --out "$TMP" > "$TMP/render.log" 2>&1 || { tail -5 "$TMP/render.log"; exit 1; }
ls "$TMP"/f_*.png | sort > "$TMP/list"
awk '{print "file \x27" $0 "\x27"}' "$TMP/list" > "$TMP/concat.txt"
ffmpeg -v error -y -f concat -safe 0 -r 24 -i "$TMP/concat.txt" -c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le "$TMP/black3.mov"
bun "$HERE/bandcheck.ts" "$TMP/black3.mov" "$OUTJ" --stride 3
rm -rf "$TMP"
