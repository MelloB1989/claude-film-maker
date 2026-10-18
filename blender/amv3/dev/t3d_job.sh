#!/bin/bash
# text3d test render on the VM (render queue): one stage build + render per spec, then preview comps and strips.
# usage: blender/amv3/dev/t3d_job.sh OUT "TITLE ONLY FRAMES NAME [STRIPS...]" ...
#   ONLY = comma cut ids or "all"; STRIPS = A-B ranges for strips.  RES/SAMPLES env override (0.5 / 16).
set -u
OUT=$1; shift
DATA=${DATA:-$AMV3_DATA}
for spec in "$@"; do
  set -- $spec
  title=${1//\?/ } only=$2 frames=$3 name=$4; shift 4
  oa=(--only "$only"); [ "$only" = all ] && oa=()
  T3D_ONLY=$title blender -b -t 14 --factory-startup -P blender/amv3/stage.py -- --edl films/timeless/amv3/edl.json \
    --data "$DATA" --frames "$frames" --res "${RES:-0.5}" --samples "${SAMPLES:-16}" "${oa[@]}" --no-gate \
    --out "$OUT/$name" 2>&1 | grep -E '^\[stage\]|Error|Traceback|line [0-9]' | tail -40
  st=(); for s in "$@"; do st+=(--strip "$s"); done
  python blender/amv3/dev/t3d_preview.py "$OUT/$name" "${st[@]}"
done
