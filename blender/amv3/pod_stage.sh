#!/bin/bash
# One-shot GPU render of the Timeless v3 stage (blender/amv3/stage.py: plate / text / light passes) on a RunPod GPU pod
# (4090), run from the VM (where $AMV3_DATA lives).
#
#   blender/amv3/pod_stage.sh <pod-ip> <ssh-port> [--name final1] [--frames 0-834] [--samples 64] [--procs 3]
#                             [--device OPTIX|CUDA] [--passes plate,text,light] [--res 1] [--no-bootstrap]
#                             [--no-data] [--key ~/.ssh/id] [--allow-cpu]
#
# Frames land in $AMV3_DATA/stage/<name>/<pass>/f_NNNNN.png (NNNNN = comp frame, 1920x1080 RGBA, straight alpha), plus
# logs/, gate.csv and keys.json from the first process.
# Steps: bootstrap the pod (Blender 5.2.2 + libs + rsync: tools/filmtools/pod_bootstrap.sh) -> check OPTIX (fall back to
# CUDA) -> ship the repo (blender/amv3, the EDL, fonts) and $AMV3_DATA plates/mattes/depth/tracks -> render the frame
# range split into --procs contiguous chunks, one Blender each, sharing the GPU -> pull the frames -> verify every frame of
# every pass exists, is 1920x1080 RGBA, and that plate alpha is opaque before 819 -> print s/frame.
# Exits non-zero on any failure. The gate runs once (first chunk builds the whole scene and checks 0-818).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

if [ $# -lt 2 ]; then sed -n 2,15p "$0"; exit 2; fi
IP=$1; PORT=$2; shift 2
NAME=final; FRAMES=0-834; SAMPLES=64; PROCS=3; DEVICE=OPTIX; PASSES=plate,text,light; RES=1; BOOT=1; DATA_SYNC=1
KEY=""; ALLOW_CPU=0
while [ $# -gt 0 ]; do
  case $1 in
    --name) NAME=$2; shift 2;;
    --frames) FRAMES=$2; shift 2;;
    --samples) SAMPLES=$2; shift 2;;
    --procs) PROCS=$2; shift 2;;
    --device) DEVICE=$2; shift 2;;
    --passes) PASSES=$2; shift 2;;
    --res) RES=$2; shift 2;;
    --no-bootstrap) BOOT=0; shift;;
    --no-data) DATA_SYNC=0; shift;;
    --key) KEY=$2; shift 2;;
    --allow-cpu) ALLOW_CPU=1; shift;;
    *) echo "pod_stage: unknown option $1" >&2; exit 2;;
  esac
done
F0=${FRAMES%-*}; F1=${FRAMES#*-}

DATA="${AMV3_DATA:-/home/nikhil/code/film-making/work/timeless_v3}"
[ -d "$DATA/plates" ] || { echo "pod_stage: no plates in $DATA" >&2; exit 1; }
OUT="$DATA/stage/$NAME"
mkdir -p "$OUT/logs"

SSHO=(-p "$PORT" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=20 -o BatchMode=yes)
[ -n "$KEY" ] && SSHO+=(-i "$KEY")
pod() { ssh "${SSHO[@]}" "root@$IP" "$@"; }
die() { echo "pod_stage: FAIL: $*" >&2; exit 1; }
T_START=$(date +%s)
echo "pod_stage: pod root@$IP:$PORT  frames $F0-$F1  samples $SAMPLES  procs $PROCS  device $DEVICE  -> $OUT"

pod 'echo connected: $(hostname); nproc; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader' || die "cannot ssh to the pod"

# ---- 1. bootstrap ------------------------------------------------------------------------------------------------------
if [ $BOOT = 1 ]; then
  echo "pod_stage: bootstrap ..."
  pod 'export DEBIAN_FRONTEND=noninteractive; command -v rsync >/dev/null || { apt-get update -qq >/dev/null && apt-get install -y -qq rsync >/dev/null; }'
  pod 'bash -s' < "$REPO/tools/filmtools/pod_bootstrap.sh" > /tmp/pod_bootstrap.$$.log 2>&1 || true
  cat /tmp/pod_bootstrap.$$.log; rm -f /tmp/pod_bootstrap.$$.log
fi
pod 'blender --version | head -1' | grep -q "Blender 5.2" || die "Blender 5.2 is not installed on the pod (run without --no-bootstrap)"

# ---- 2. GPU ------------------------------------------------------------------------------------------------------------
DEVS=$(pod "blender -b --factory-startup --python-expr '
import bpy
p = bpy.context.preferences.addons[\"cycles\"].preferences
for t in (\"OPTIX\", \"CUDA\"):
    try:
        p.compute_device_type = t
        p.get_devices()
        print(\"DEV\", t, len([d for d in p.devices if d.type == t]))
    except TypeError:
        print(\"DEV\", t, 0)
' 2>/dev/null | grep '^DEV'" || true)
echo "$DEVS"
n_of() { echo "$DEVS" | awk -v t="$1" '$2==t {print $3}' | head -1; }
OPT=$(n_of OPTIX); CUD=$(n_of CUDA); OPT=${OPT:-0}; CUD=${CUD:-0}
if [ "$DEVICE" = OPTIX ] && [ "$OPT" -eq 0 ] && [ "$CUD" -gt 0 ]; then echo "pod_stage: OPTIX not visible, using CUDA"; DEVICE=CUDA; fi
if { [ "$DEVICE" = OPTIX ] && [ "$OPT" -eq 0 ]; } || { [ "$DEVICE" = CUDA ] && [ "$CUD" -eq 0 ]; }; then
  if [ $ALLOW_CPU = 1 ]; then echo "pod_stage: no GPU device, rendering on CPU (--allow-cpu)"; DEVICE=CPU
  else die "no $DEVICE device visible to Cycles on the pod (use --allow-cpu to render on CPU)"; fi
fi

# ---- 3. ship the repo + data -------------------------------------------------------------------------------------------
echo "pod_stage: sync repo ..."
pod 'mkdir -p /root/cfm /root/data /root/stage'
FILES=(blender/amv3 films/timeless/amv3/edl.json films/timeless/fonts fonts)
EXIST=(); for f in "${FILES[@]}"; do [ -e "$REPO/$f" ] && EXIST+=("$f"); done
(cd "$REPO" && tar cz --exclude=__pycache__ --exclude='*.blend' --exclude='_harness*' "${EXIST[@]}") | pod 'rm -rf /root/cfm/blender && tar xz -C /root/cfm'
if [ $DATA_SYNC = 1 ]; then
  echo "pod_stage: sync data (plates, mattes, depth, tracks) ..."
  T0=$(date +%s)
  if command -v rsync >/dev/null; then
    (cd "$DATA" && rsync -a --info=stats1 -e "ssh ${SSHO[*]}" --exclude '_*' plates mattes depth tracks "root@$IP:/root/data/")
  else
    (cd "$DATA" && tar c --exclude='_*' plates mattes depth tracks) | pod 'tar x -C /root/data'
  fi
  echo "pod_stage: data synced in $(( $(date +%s) - T0 ))s"
fi
pod 'ls /root/data; du -sh /root/data'

# ---- 4. render ----------------------------------------------------------------------------------------------------------
N=$PROCS; TOTAL=$((F1 - F0 + 1)); PER=$(( (TOTAL + N - 1) / N ))
JOBS=""
for ((i = 0; i < N; i++)); do
  a=$((F0 + i * PER)); b=$((a + PER - 1)); [ $b -gt $F1 ] && b=$F1; [ $a -gt $F1 ] && continue
  extra="--no-gate"; [ $i = 0 ] && extra="--strict-off"
  JOBS+="chunk$i|$a-$b|$extra"$'\n'
done
printf '%s' "$JOBS" | pod 'cat > /root/stage/jobs.txt'
echo "pod_stage: render $(printf '%s' "$JOBS" | grep -c .) processes ..."
RC=0
pod "SAMPLES=$SAMPLES DEVICE=$DEVICE PASSES=$PASSES RES=$RES bash -s" <<'REMOTE' 2>&1 | sed -u 's/^/  pod: /' || RC=$?
set -u
cd /root/cfm
rm -rf /root/stage/out /root/stage/log; mkdir -p /root/stage/out /root/stage/log
N=$(grep -c . /root/stage/jobs.txt)
THREADS=$(( $(nproc) / N )); [ $THREADS -lt 2 ] && THREADS=2
run_one() {
  IFS='|' read -r label frames extra <<<"$1"
  [ "$extra" = "--strict-off" ] && extra=""
  t0=$(date +%s.%N)
  blender -b -t "$2" --factory-startup --python-exit-code 1 -P blender/amv3/stage.py -- \
    --edl films/timeless/amv3/edl.json --data /root/data --frames "$frames" --res "$RES" --samples "$SAMPLES" \
    --device "$DEVICE" --passes "$PASSES" --out "/root/stage/out/$label" $extra > "/root/stage/log/$label.log" 2>&1
  rc=$?
  t1=$(date +%s.%N)
  echo "$label $frames $rc $t0 $t1" > "/root/stage/log/$label.time"
  echo "job $label ($frames) exit $rc ($(awk -v a=$t0 -v b=$t1 'BEGIN{printf "%.0f", b-a}')s)"
  return $rc
}
export -f run_one
export SAMPLES DEVICE PASSES RES
tr '\n' '\0' < /root/stage/jobs.txt | xargs -0 -P "$N" -I{} bash -c 'run_one "$1" '"$THREADS" _ {}
REMOTE
[ $RC = 0 ] || { pod 'tail -n 30 /root/stage/log/*.log' || true; die "a render process failed on the pod (logs in /root/stage/log)"; }

# ---- 5. pull: merge the chunks' pass folders into $OUT ---------------------------------------------------------------------
echo "pod_stage: pull frames -> $OUT ..."
pod 'cd /root/stage && tar c --exclude=_seq --exclude=camdump.json out log' | tar x -C "$OUT" || die "pull failed"
for d in "$OUT"/out/chunk*; do
  for p in ${PASSES//,/ }; do mkdir -p "$OUT/$p"; [ -d "$d/$p" ] && mv "$d/$p"/*.png "$OUT/$p/" 2>/dev/null || true; done
  for f in gate.csv keys.json; do [ -f "$d/$f" ] && [ ! -f "$OUT/$f" ] && mv "$d/$f" "$OUT/$f"; done
  [ -f "$d/stage.log" ] && mv "$d/stage.log" "$OUT/logs/$(basename "$d").stage.log"
  rm -rf "$d"
done
rmdir "$OUT/out" 2>/dev/null || true
[ -d "$OUT/log" ] && mv "$OUT/log"/* "$OUT/logs/" && rmdir "$OUT/log"

# ---- 6. verify ------------------------------------------------------------------------------------------------------------
python3 -I - "$OUT" "$F0" "$F1" "$PASSES" "$RES" <<'PY' || die "missing or bad frames (see above)"
import struct, sys, zlib
from pathlib import Path
out, f0, f1, passes, res = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4].split(","), float(sys.argv[5])
W, H = round(1920 * res), round(1080 * res)
bad = []
def png_alpha_min(p):
    """Minimum alpha of an 8-bit RGBA PNG (pure python, no numpy needed on the VM)."""
    data = p.read_bytes()
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]; typ = data[pos + 4:pos + 8]; body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif typ == b"IDAT":
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride, bpp = w * 4, 4
    prev = bytearray(stride); amin = 255
    for y in range(0, h):
        ft = raw[y * (stride + 1)]; line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0; b = prev[i]; c = prev[i - bpp] if i >= bpp else 0
            if ft == 1: line[i] = (line[i] + a) & 255
            elif ft == 2: line[i] = (line[i] + b) & 255
            elif ft == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif ft == 4:
                pp = a + b - c; pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        amin = min(amin, min(line[3::4])); prev = line
    return amin
for p in passes:
    n = 0
    for f in range(f0, f1 + 1):
        q = out / p / f"f_{f:05d}.png"
        if not q.exists() or q.stat().st_size < 200:
            bad.append(f"{p}/{q.name} missing"); continue
        h = q.read_bytes()[:33]
        w, ht, depth, ctype = struct.unpack(">IIBB", h[16:26])
        if (w, ht) != (W, H) or ctype != 6:
            bad.append(f"{p}/{q.name} is {w}x{ht} colortype {ctype}, want {W}x{H} RGBA"); continue
        n += 1
    print(f"verify {p}: {n}/{f1 - f0 + 1} frames")
# plate alpha: opaque before 819 (spot check every 40th frame; full decode is slow in pure python)
for f in range(max(f0, 0), min(f1, 818) + 1, 40):
    q = out / "plate" / f"f_{f:05d}.png"
    if q.exists():
        a = png_alpha_min(q)
        if a < 250:
            bad.append(f"plate/{q.name}: alpha min {a} before 819 (a hole to black)")
if bad:
    print("\n".join("BAD: " + x for x in bad[:40]), file=sys.stderr)
    sys.exit(1)
PY

echo "pod_stage: timing (pod wall seconds; chunks ran concurrently on one GPU)"
for t in "$OUT"/logs/*.time; do
  read -r label frames rc t0 t1 < "$t"
  a=${frames%-*}; b=${frames#*-}
  awk -v l="$label" -v fr="$frames" -v a="$a" -v b="$b" -v t0="$t0" -v t1="$t1" \
    'BEGIN{n=b-a+1; printf "  %-7s %-9s %5.0fs  %.2f s/frame (all passes)\n", l, fr, t1-t0, (t1-t0)/n}'
done
grep -h "pass \|FAIL\|PASS" "$OUT"/logs/chunk0.stage.log 2>/dev/null | tail -20 || true
echo "pod_stage: OK in $(( $(date +%s) - T_START ))s -> $OUT. Stop the pod: python -m filmtools.runpod down <pod id>"
