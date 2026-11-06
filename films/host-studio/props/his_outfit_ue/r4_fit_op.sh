#!/bin/sh
# Round 4, his clipping: fit his trousers to the OPERATOR's MetaHuman (Host_Op: his body, his default garment's tee,
# the anims he plays) instead of Trey's, in headless Blender on the GPU box (face rule: his body never leaves it).
# The ones in the project were fitted to Trey's tee: on Host_Op their waistband stood through the tee's hem (cast v3,
# S18: two-tone patches at the hips). CPU only; nothing here touches the editor. Run on the box (as ubuntu) after
#     film-ue exec -c "EXPORT_DIR='his_outfit_op'; exec(open('<tree>/films/host-studio/props/his_outfit_ue/export_body.py').read())"
#     film-ue exec <tree>/films/host-studio/props/his_outfit_ue/export_alt_body.py     (the template body, uncut)
# with Host_Op on the level, then:
#     sh films/host-studio/props/his_outfit_ue/r4_fit_op.sh
# and import it beside Trey's (studio.py's his outfit block picks it for HOST op):
#     film-ue exec -c "IMPORT_DIR='his_outfit_op'; SUFFIX='_Op'; exec(open('<tree>/films/host-studio/props/his_outfit_ue/import_outfit.py').read())"
# Env: PROJ (the UE project), BLENDER, WORK (scratch), PYLIB (scipy for Blender's Python; installed here if missing).
set -eu
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
PROJ=${PROJ:-/srv/ue/projects/HostStudio}
BLENDER=${BLENDER:-$(ls -d /srv/ue/tools/blender-*/blender 2>/dev/null | tail -1)}
WORK=${WORK:-$PROJ/Saved/r4_fit_op}
EXP=$PROJ/Saved/Export
PROPS=$REPO/films/host-studio/props
PYLIB=${PYLIB:-$WORK/pylib}
[ -x "$BLENDER" ] || { echo "no Blender at '$BLENDER' (set BLENDER)" >&2; exit 2; }
[ -f "$EXP/his_outfit_op/body.fbx" ] || { echo "no $EXP/his_outfit_op/body.fbx: run export_body.py with EXPORT_DIR='his_outfit_op'" >&2; exit 2; }
mkdir -p "$WORK/src" "$WORK/out" "$PROJ/Saved/Import/his_outfit_op"
cp "$EXP"/his_outfit_op/*.fbx "$WORK/src/"
[ -f "$EXP/his_outfit_alt/body_alt.fbx" ] && cp "$EXP/his_outfit_alt/body_alt.fbx" "$WORK/src/"
# scipy for Blender's own Python (his_outfit.py: ndimage, cKDTree), matched to its version and numpy
if ! "$BLENDER" -b --factory-startup --python-exit-code 1 --python-expr "import sys; sys.path.append('$PYLIB'); import scipy" >/dev/null 2>&1; then
    pyv=$("$BLENDER" -b --factory-startup --python-expr "import sys; print('PYV', '%d.%d' % sys.version_info[:2])" 2>/dev/null | awk '/^PYV/ {print $2}')
    npv=$("$BLENDER" -b --factory-startup --python-expr "import numpy; print('NPV', numpy.__version__)" 2>/dev/null | awk '/^NPV/ {print $2}')
    echo "installing scipy for Blender's Python $pyv (numpy $npv) into $PYLIB"
    "${UV:-$(command -v uv || echo $HOME/.local/bin/uv)}" pip install --quiet --python-version "$pyv" --only-binary :all: --target "$PYLIB" "scipy<1.14" "numpy==$npv"
    rm -rf "$PYLIB"/numpy "$PYLIB"/numpy-*  # Blender's own numpy comes first; never shadow it
fi
echo "blender: $("$BLENDER" --version | head -1); src: $(ls "$WORK/src" | tr '\n' ' ')"
t0=$(date +%s)
nice "$BLENDER" -b --factory-startup -P "$PROPS/his_outfit.py" -- --src "$WORK/src" --out "$WORK/out" \
    --pylib "$PYLIB" --no-render > "$WORK/blender.log" 2>&1 || { tail -40 "$WORK/blender.log"; exit 1; }
echo "blender: $(( $(date +%s) - t0 )) s, log $WORK/blender.log"
cp "$WORK/out/his_trousers.fbx" "$PROJ/Saved/Import/his_outfit_op/"
grep -E 'tee clearance|tee inside|pull_in_tee|clip|pose |idle|trousers skin|garment: slots|body verts|done' "$WORK/blender.log" | tail -40
[ -f "$WORK/out/his_outfit_tests.json" ] && python3 -c "
import json; t = json.load(open('$WORK/out/his_outfit_tests.json'))
for k, v in t.items(): print(k, json.dumps(v)[:600])"
echo "staged: $PROJ/Saved/Import/his_outfit_op/his_trousers.fbx (next: import_outfit.py with SUFFIX='_Op', host_swap.py HOST='op')"
