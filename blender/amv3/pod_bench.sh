#!/bin/bash
# GPU timing pass for the stage render optimisations (renderopt.py, task v3-renderopt), run from the VM like
# pod_stage.sh. Assumes the pod was set up by pod_stage.sh (Blender 5.2 + /root/data); pass --data to sync the data.
#
#   blender/amv3/pod_bench.sh <pod-ip> <ssh-port> [--name bench1] [--samples 64] [--device OPTIX] [--data] [--key ~/.ssh/id]
#
# Runs, full res, plate pass, each variant as its own Blender:
#   A. 1 process:  off (the core's render path) vs opt (AMV3_RO default) on a hold (100-111) and a glass window (476-487)
#   B. 3 processes at once (opt): 100-111 | 476-487 | 552-563, nvidia-smi sampled every 0.5 s
# and pulls every log, ro_times.txt / ro_stats.txt and the frames to $AMV3_DATA/stage/<name>/ (for the pixel diffs).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
if [ $# -lt 2 ]; then sed -n 2,13p "$0"; exit 2; fi
IP=$1; PORT=$2; shift 2
NAME=bench1; SAMPLES=64; DEVICE=OPTIX; DATA_SYNC=0; KEY=""
while [ $# -gt 0 ]; do
  case $1 in
    --name) NAME=$2; shift 2;;
    --samples) SAMPLES=$2; shift 2;;
    --device) DEVICE=$2; shift 2;;
    --data) DATA_SYNC=1; shift;;
    --key) KEY=$2; shift 2;;
    *) echo "pod_bench: unknown option $1" >&2; exit 2;;
  esac
done
DATA="${AMV3_DATA:-/home/nikhil/code/film-making/work/timeless_v3}"
OUT="$DATA/stage/$NAME"; mkdir -p "$OUT"
SSHO=(-p "$PORT" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=20 -o BatchMode=yes)
[ -n "$KEY" ] && SSHO+=(-i "$KEY")
pod() { ssh "${SSHO[@]}" "root@$IP" "$@"; }

pod 'nproc; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader; blender --version | head -1'
FILES=(blender/amv3 films/timeless/amv3/edl.json films/timeless/fonts fonts)
EXIST=(); for f in "${FILES[@]}"; do [ -e "$REPO/$f" ] && EXIST+=("$f"); done
(cd "$REPO" && tar cz --exclude=__pycache__ --exclude='*.blend' --exclude='_harness*' "${EXIST[@]}") | pod 'mkdir -p /root/cfm && rm -rf /root/cfm/blender && tar xz -C /root/cfm'
if [ $DATA_SYNC = 1 ]; then
  (cd "$DATA" && rsync -a -e "ssh ${SSHO[*]}" --exclude '_*' plates mattes depth tracks "root@$IP:/root/data/")
fi

pod "SAMPLES=$SAMPLES DEVICE=$DEVICE bash -s" <<'REMOTE' 2>&1 | sed -u 's/^/  pod: /'
set -u
cd /root/cfm
B=/root/bench; rm -rf $B; mkdir -p $B
NP=$(nproc)
run() {  # run <label> <frames> <threads> <AMV3_RO> [env...]
  label=$1; fr=$2; th=$3; ro=$4; shift 4
  t0=$(date +%s.%N)
  env AMV3_RO="$ro" "$@" blender -b -t "$th" --factory-startup -P blender/amv3/stage.py -- \
    --edl films/timeless/amv3/edl.json --data /root/data --frames "$fr" --res 1 --samples "$SAMPLES" --device "$DEVICE" \
    --passes plate --no-gate --out "$B/$label" > "$B/$label.log" 2>&1
  rc=$?
  t1=$(date +%s.%N)
  echo "$label $fr AMV3_RO=$ro exit $rc wall $(awk -v a=$t0 -v b=$t1 'BEGIN{printf "%.0f", b-a}')s :: $(grep -h 'pass plate' "$B/$label.log")"
}
gpu_log() { nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader -lms 500 > "$B/$1.smi" & echo $!; }
util() { awk -F', ' '{gsub(/ %/,"",$2); s+=$2; n++} END {if (n) printf "GPU util mean %.0f %% over %d samples\n", s/n, n}' "$B/$1.smi"; }

for v in off opt; do
  ro=$([ $v = off ] && echo off,stats || echo vis,steps,emis,dngpu,stats)
  for fr in 100-111 476-487; do
    p=$(gpu_log ${v}_$fr); run ${v}_$fr $fr $NP $ro; kill $p; util ${v}_$fr
  done
done
TH=$(( NP / 3 )); [ $TH -lt 2 ] && TH=2
p=$(gpu_log par3)
run par3_a 100-111 $TH vis,steps,emis,dngpu,stats & run par3_b 476-487 $TH vis,steps,emis,dngpu,stats & run par3_c 552-563 $TH vis,steps,emis,dngpu,stats & wait
kill $p; util par3
for f in $B/*/ro_stats.txt; do echo "== $f"; head -4 "$f" | cut -c1-200; done
REMOTE
pod 'cd /root/bench && tar c --exclude=_seq .' | tar x -C "$OUT"
echo "pod_bench: results in $OUT (logs, *.smi, */ro_times.txt, */ro_stats.txt, */plate/)"
