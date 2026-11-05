#!/bin/sh
# Round 3, her collar: rebuild the overshirt (props/overshirt.py, the COLLAR knobs) in headless Blender on the GPU box,
# from her body/face/idle as the editor exports them, and stage it for import_overshirt.py. CPU only; nothing here
# touches the editor. Run on the box (as ubuntu) after export_body.py and export_neck_idle.py:
#     sh films/host-studio/props/overshirt_ue/r3_collar.sh
# Env: PROJ (the UE project), BLENDER, WORK (scratch). Prints the clip and collar-gap report at the end.
set -eu
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
PROJ=${PROJ:-/srv/ue/projects/HostStudio}
BLENDER=${BLENDER:-/srv/ue/tools/blender-4.2/blender}
WORK=${WORK:-$PROJ/Saved/r3_collar}
EXP=$PROJ/Saved/Export
PROPS=$REPO/films/host-studio/props
mkdir -p "$WORK/src" "$WORK/out" "$PROJ/Saved/Import/overshirt"
body=$(for f in "$EXP"/overshirt/*.fbx; do basename "$f"; done | grep -i body | grep -v -i -E 'top|tee|shirt|trouser' \
    | head -1)  # the name only: the folder (overshirt) would match 'shirt'
[ -z "$body" ] || body=$EXP/overshirt/$body
[ -n "$body" ] || { echo "no body FBX in $EXP/overshirt: run export_body.py first" >&2; exit 2; }
cp "$body" "$WORK/src/body.fbx"
cp "$EXP/overshirt2/face.fbx" "$EXP/overshirt2/idle.fbx" "$WORK/src/"
cp "$PROPS/out/her_top.fbx" "$WORK/src/"
echo "body: $body; blender: $("$BLENDER" --version | head -1)"
t0=$(date +%s)
nice "$BLENDER" -b --factory-startup -P "$PROPS/overshirt.py" -- --src "$WORK/src" --out "$WORK/out" \
    --stage envelope,sim,detail,skin --body body.fbx --under skin:0.6 --check her_top.fbx > "$WORK/blender.log" 2>&1 \
    || { tail -40 "$WORK/blender.log"; exit 1; }
echo "blender: $(( $(date +%s) - t0 )) s, log $WORK/blender.log"
cp "$WORK/out/overshirt.fbx" "$PROJ/Saved/Import/overshirt/"
cp "$PROPS"/out/overshirt_tex/T_OvershirtTwill_*.png "$PROJ/Saved/Import/overshirt/"
grep -E 'collar:|^pose |idle frame|clip by part|skipped' "$WORK/blender.log" | tail -40
ls "$WORK/out"/*.png 2>/dev/null | head -20
echo "staged: $PROJ/Saved/Import/overshirt/overshirt.fbx (next: film-ue exec import_overshirt.py, restore_leader.py)"
