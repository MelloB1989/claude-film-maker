#!/bin/sh
# strip.sh <pass dir> <first> <count> <cols> <out.jpg> [tile width]: contact strip of consecutive frames, numbers burnt in.
FF=${FFMPEG:-ffmpeg}
W=${6:-480}
$FF -v error -start_number $2 -i $1/f_%05d.png -frames:v $3 \
  -vf "scale=$W:-2,drawtext=text='%{eif\:n+$2\:d}':x=6:y=6:fontsize=20:fontcolor=yellow:box=1:boxcolor=black@0.6,tile=$4x$(( ($3 + $4 - 1) / $4 )):padding=2" \
  -frames:v 1 -update 1 -q:v 3 -y $5
