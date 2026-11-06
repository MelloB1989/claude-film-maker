#!/bin/sh
# Round 5 (agent-02): refit his trousers to the round-5 TEE (garment-fit's Fit6) instead of Epic's default garment,
# so the waistband sits inside the refit tee's hem (Trousers>tee) without a flaring hem. Same fitter as round 4
# (props/his_outfit.py, r4_fit_op.sh), fed from garment.export's out_dir and the Fit6 FBX:
#   body.fbx (his worn body), body_alt.fbx <- ref_body.fbx (uncut), face.fbx, anim_*.fbx, garment.fbx <- the Fit6 tee
#   (it keeps Epic's slots: shirt + shorts, which his_outfit.py tells apart by the slot names).
#     FIT=$G/fit TEE=$G/fit/out11/garment_fit_tee.fbx sh films/host-studio/props/his_outfit_ue/r5_trousers.sh
# then:
#     film-ue exec -c "IMPORT_DIR='his_outfit_r5'; SUFFIX='_R5'; exec(open('<tree>/films/host-studio/props/his_outfit_ue/import_outfit.py').read())"
#     film-ue op mh.dress label=Host 'garments={"Trousers": {"mesh": "/Game/Host/Host_Outfit/SKM_Host_Trousers_R5"}}'
#     film-ue exec <tree>/films/host-studio/props/his_outfit_ue/dress_him.py ; then qa.clip (Trousers>tee).
# CPU only (~10 min); nothing here touches the editor. Env: PROJ, BLENDER, WORK, PYLIB (as r4_fit_op.sh).
set -eu
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
PROJ=${PROJ:-/srv/ue/projects/HostStudio}
BLENDER=${BLENDER:-$(ls -d /srv/ue/tools/blender-*/blender 2>/dev/null | tail -1)}
WORK=${WORK:-$PROJ/Saved/r5_trousers}
PYLIB=${PYLIB:-$PROJ/Saved/r4_fit_op/pylib}
: "${FIT:?FIT= garment.export out_dir}" "${TEE:?TEE= the Fit6 tee FBX}"
[ -x "$BLENDER" ] || { echo "no Blender at '$BLENDER'" >&2; exit 2; }
for f in body.fbx ref_body.fbx face.fbx; do [ -f "$FIT/$f" ] || { echo "no $FIT/$f" >&2; exit 2; }; done
[ -f "$TEE" ] || { echo "no $TEE" >&2; exit 2; }
rm -rf "$WORK/src" "$WORK/out"; mkdir -p "$WORK/src" "$WORK/out" "$PROJ/Saved/Import/his_outfit_r5"
cp "$FIT/body.fbx" "$FIT/face.fbx" "$WORK/src/"
cp "$FIT/ref_body.fbx" "$WORK/src/body_alt.fbx"
cp "$FIT"/anim_*.fbx "$WORK/src/" 2>/dev/null || true
cp "$TEE" "$WORK/src/garment.fbx"
"$BLENDER" -b --factory-startup --python-exit-code 1 --python-expr "import sys; sys.path.append('$PYLIB'); import scipy" \
    >/dev/null 2>&1 || { echo "no scipy for Blender at $PYLIB: run r4_fit_op.sh once (it installs it) or set PYLIB" >&2; exit 2; }
t0=$(date +%s)
nice "$BLENDER" -b --factory-startup -P "$REPO/films/host-studio/props/his_outfit.py" -- --src "$WORK/src" \
    --out "$WORK/out" --pylib "$PYLIB" --no-render > "$WORK/blender.log" 2>&1 || { tail -40 "$WORK/blender.log"; exit 1; }
echo "blender: $(( $(date +%s) - t0 )) s, log $WORK/blender.log"
cp "$WORK/out/his_trousers.fbx" "$PROJ/Saved/Import/his_outfit_r5/"
grep -E 'tee clearance|tee inside|pull_in_tee|clip|pose |idle|trousers skin|garment: slots|body verts|done' "$WORK/blender.log" | tail -40
echo "staged: $PROJ/Saved/Import/his_outfit_r5/his_trousers.fbx (next: import_outfit.py IMPORT_DIR='his_outfit_r5' SUFFIX='_R5')"
