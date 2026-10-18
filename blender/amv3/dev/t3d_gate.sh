#!/bin/bash
# text_fly gate on the VM: render C10 / C25 with margins (plate + text, half res, 32 spp), preview comps, then
# motion_metrics --gate on the plate pass (what the gate judges) and on the comp (plate + titles).
set -u
OUT=${1:-out/gate}
export RES=${RES:-0.5} SAMPLES=${SAMPLES:-32}
blender/amv3/dev/t3d_job.sh "$OUT" 'AMAZING C09,C10 316-352 c10 316-352' 'SPIDER-MAN C24,C25 638-668 c25 638-668'
for w in c10 c25; do
  for p in plate comp; do
    PYTHONPATH=tools python -m filmtools.amv3.motion_metrics "$OUT/$w/$p" --out "$OUT/$w/mm_$p" --gate 2>&1 | tail -25
  done
done
