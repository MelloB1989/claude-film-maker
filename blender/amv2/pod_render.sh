#!/bin/bash
# One-shot GPU render of every Timeless v2 Blender piece on a RunPod GPU pod (4090), from the VM.
#
#   blender/amv2/pod_render.sh <pod-ip> <ssh-port> [--samples 96] [--device OPTIX|CUDA] [--only a,b] [--no-bootstrap]
#                              [--res-scale 1] [--procs-outro 2] [--key ~/.ssh/id] [--allow-cpu]
#
# Pieces (frames land in $AMV2_DATA/blender/<element>/NNNN.png, NNNN = comp frame, straight-alpha RGBA 1920x1080):
#   timeless3d 802-826, rift 244-262, shockwave 480-489  (blender/amv2/elements.py)
#   outro 819-899                                         (blender/amv2/outro.py, agent-06)
# Steps: bootstrap the pod (Blender 5.2.2 + libs + rsync, tools/filmtools/pod_bootstrap.sh) -> check OPTIX is visible
# (fall back to CUDA) -> ship the repo -> render with a few Blender processes sharing the GPU -> pull the frames ->
# verify every expected frame exists and is a 1920x1080 RGBA PNG -> print per-piece timing. Exits non-zero on any
# failure (a render error, a missing/bad frame, no GPU).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

if [ $# -lt 2 ]; then sed -n 2,14p "$0"; exit 2; fi
IP=$1; PORT=$2; shift 2
SAMPLES=96; DEVICE=OPTIX; ONLY=timeless3d,rift,shockwave,outro; BOOT=1; RES=1; OUTRO_PROCS=2; KEY=""; ALLOW_CPU=0
while [ $# -gt 0 ]; do
  case $1 in
    --samples) SAMPLES=$2; shift 2;;
    --device) DEVICE=$2; shift 2;;
    --only) ONLY=$2; shift 2;;
    --no-bootstrap) BOOT=0; shift;;
    --res-scale) RES=$2; shift 2;;
    --procs-outro) OUTRO_PROCS=$2; shift 2;;
    --key) KEY=$2; shift 2;;
    --allow-cpu) ALLOW_CPU=1; shift;;
    *) echo "pod_render: unknown option $1" >&2; exit 2;;
  esac
done

# where the frames go: $AMV2_DATA (as ecbuild resolves it) or the VM's shared data dir
DATA="${AMV2_DATA:-}"
[ -z "$DATA" ] && [ -d /home/nikhil/code/film-making/work/timeless_v2 ] && DATA=/home/nikhil/code/film-making/work/timeless_v2
[ -z "$DATA" ] && DATA="$REPO/out/data"
mkdir -p "$DATA/blender"

SSHO=(-p "$PORT" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=20 -o BatchMode=yes)
[ -n "$KEY" ] && SSHO+=(-i "$KEY")
pod() { ssh "${SSHO[@]}" "root@$IP" "$@"; }
die() { echo "pod_render: FAIL: $*" >&2; exit 1; }
T_START=$(date +%s)
echo "pod_render: pod root@$IP:$PORT  samples $SAMPLES  device $DEVICE  pieces $ONLY  data $DATA"

pod 'echo connected: $(hostname); nproc; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader' || die "cannot ssh to the pod"

# ---- 1. bootstrap (apt rsync first: pod images lack it; bootstrap installs the GL libs + Blender 5.2.2) -------------
if [ $BOOT = 1 ]; then
  echo "pod_render: bootstrap ..."
  pod 'export DEBIAN_FRONTEND=noninteractive; command -v rsync >/dev/null || { apt-get update -qq >/dev/null && apt-get install -y -qq rsync >/dev/null; }'
  # pod_bootstrap.sh ends in a grep that fails when no GPU is visible; keep its output, judge the devices below
  pod 'bash -s' < "$REPO/tools/filmtools/pod_bootstrap.sh" > /tmp/pod_bootstrap.$$.log 2>&1 || true
  cat /tmp/pod_bootstrap.$$.log; rm -f /tmp/pod_bootstrap.$$.log
fi
pod 'blender --version | head -1' | grep -q "Blender 5.2" || die "Blender 5.2 is not installed on the pod (run without --no-bootstrap)"

# ---- 2. GPU: OPTIX visible? else CUDA --------------------------------------------------------------------------------
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
case $DEVICE in
  OPTIX) if [ "$OPT" -gt 0 ]; then :; elif [ "$CUD" -gt 0 ]; then echo "pod_render: OPTIX not visible, falling back to CUDA"; DEVICE=CUDA; fi;;
  CUDA) [ "$CUD" -gt 0 ] || true;;
esac
if { [ "$DEVICE" = OPTIX ] && [ "$OPT" -eq 0 ]; } || { [ "$DEVICE" = CUDA ] && [ "$CUD" -eq 0 ]; }; then
  if [ $ALLOW_CPU = 1 ]; then echo "pod_render: no GPU device, rendering on CPU (--allow-cpu)"; DEVICE=CPU
  else die "no $DEVICE device visible to Cycles on the pod (use --allow-cpu to render on CPU)"; fi
fi
echo "pod_render: rendering with $DEVICE"

# ---- 3. ship the repo (blender/ + fonts + the outro font that is not in git) -----------------------------------------
# rsync when the VM has it (this one may not): else tar over ssh. out/ and .git are never sent.
echo "pod_render: sync repo ..."
pod 'mkdir -p /root/cfm /root/frames'
FILES=(blender films/timeless/fonts fonts)
EXIST=(); for f in "${FILES[@]}"; do [ -e "$REPO/$f" ] && EXIST+=("$f"); done
if command -v rsync >/dev/null; then
  (cd "$REPO" && rsync -azR --delete -e "ssh ${SSHO[*]}" --exclude __pycache__ --exclude '*.blend' "${EXIST[@]}" "root@$IP:/root/cfm/")
else
  (cd "$REPO" && tar cz --exclude=__pycache__ --exclude='*.blend' "${EXIST[@]}") | pod 'rm -rf /root/cfm/blender && tar xz -C /root/cfm'
fi
OUTRO_FONT=/home/nikhil/code/film-making/handover/amv_handover/fonts/Spider-Man.otf.ttf
if [ -f "$OUTRO_FONT" ]; then
  pod 'mkdir -p /root/cfm/films/timeless/fonts' && cat "$OUTRO_FONT" | pod 'cat > /root/cfm/films/timeless/fonts/Spider-Man.otf.ttf'
fi
pod 'ls /root/cfm/blender/amv2 | tr "\n" " "; ls /root/cfm/films/timeless/fonts | grep -c ttf'

# ---- 4. the job list: one line per Blender process --------------------------------------------------------------------
# label|element|cmd-args   (each process gets nproc/n threads; a 4090 shares fine between the light pieces)
JOBS=""
add() { JOBS+="$1|$2|$3"$'\n'; }
has() { [[ ",$ONLY," == *",$1,"* ]]; }
COMMON="--res-scale $RES --samples $SAMPLES --device $DEVICE"
has timeless3d && add timeless3d timeless3d "elements.py --element timeless3d $COMMON --no-blend --out /root/frames/blender"
has rift       && add rift       rift       "elements.py --element rift $COMMON --no-blend --out /root/frames/blender"
has shockwave  && add shockwave  shockwave  "elements.py --element shockwave $COMMON --no-blend --out /root/frames/blender"
if has outro; then
  # split 819-899 into OUTRO_PROCS contiguous chunks
  n=$OUTRO_PROCS; per=$(( (81 + n - 1) / n ))
  for ((i = 0; i < n; i++)); do
    a=$((819 + i * per)); b=$((a + per - 1)); [ $b -gt 899 ] && b=899; [ $a -gt 899 ] && continue
    add "outro.$i" outro "outro.py --res-scale $RES --samples $SAMPLES --device $DEVICE --frames $a-$b --out /root/frames/blender/outro"
  done
fi
[ -n "$JOBS" ] || die "nothing to render (--only $ONLY)"
NJOBS=$(printf '%s' "$JOBS" | grep -c .)

# ---- 5. render ---------------------------------------------------------------------------------------------------------
# One ssh session runs the lot (xargs -P), so a dropped connection ends the run rather than leaving strays; per-job
# logs + wall times land in /root/frames/log. --python-exit-code 1 makes a script exception a non-zero job.
echo "pod_render: render $NJOBS processes ..."
pod 'rm -rf /root/frames/log /root/frames/blender; mkdir -p /root/frames/log /root/frames/blender'
printf '%s' "$JOBS" | pod 'cat > /root/frames/jobs.txt'
RC=0
pod 'bash -s' <<'REMOTE' 2>&1 | sed -u 's/^/  pod: /' || RC=$?
set -u
cd /root/cfm
export AMV2_FONT=/root/cfm/films/timeless/fonts/Spider-Man.otf.ttf
N=$(grep -c . /root/frames/jobs.txt)
THREADS=$(( $(nproc) / N )); [ $THREADS -lt 2 ] && THREADS=2
run_one() {
  IFS='|' read -r label element args <<<"$1"
  t0=$(date +%s.%N)
  blender -b -t "$2" --factory-startup --python-exit-code 1 -P "blender/amv2/${args%% *}" -- ${args#* } > "/root/frames/log/$label.log" 2>&1
  rc=$?
  t1=$(date +%s.%N)
  echo "$label $element $rc $t0 $t1" > "/root/frames/log/$label.time"
  echo "job $label exit $rc ($(awk -v a=$t0 -v b=$t1 'BEGIN{printf "%.0f", b-a}')s)"
  return $rc
}
export -f run_one
tr '\n' '\0' < /root/frames/jobs.txt | xargs -0 -P "$N" -I{} bash -c 'run_one "$1" '"$THREADS" _ {}
REMOTE
[ $RC = 0 ] || { pod 'tail -n 25 /root/frames/log/*.log' || true; die "a render process failed on the pod (logs in /root/frames/log)"; }

# ---- 6. pull the frames back ------------------------------------------------------------------------------------------
echo "pod_render: pull frames -> $DATA/blender ..."
mkdir -p "$DATA/blender" "$DATA/blender/logs"
if command -v rsync >/dev/null; then
  rsync -a -e "ssh ${SSHO[*]}" "root@$IP:/root/frames/blender/" "$DATA/blender/"
  rsync -a -e "ssh ${SSHO[*]}" "root@$IP:/root/frames/log/" "$DATA/blender/logs/"
else
  pod 'tar c -C /root/frames blender log' | tar x -C "$DATA" --transform 's#^log#blender/logs#'
fi

# ---- 7. verify every expected frame, then report timing -----------------------------------------------------------------
python3 -I - "$DATA/blender" "$ONLY" "$RES" <<'PY' || die "missing or bad frames (see above)"
import struct, sys, zlib
from pathlib import Path
root, only, res = Path(sys.argv[1]), set(sys.argv[2].split(",")), float(sys.argv[3])
want = {"timeless3d": (802, 826), "rift": (244, 262), "shockwave": (480, 489), "outro": (819, 899)}
W, H = round(1920 * res), round(1080 * res)
bad = []
for el, (a, b) in want.items():
    if el not in only:
        continue
    for f in range(a, b + 1):
        p = root / el / f"{f:04d}.png"
        if not p.exists() or p.stat().st_size < 200:
            bad.append(f"{el}/{f:04d}.png missing"); continue
        h = p.read_bytes()[:33]
        if h[:8] != b"\x89PNG\r\n\x1a\n" or h[12:16] != b"IHDR":
            bad.append(f"{el}/{f:04d}.png not a PNG"); continue
        w, ht, depth, ctype = struct.unpack(">IIBB", h[16:26])
        if (w, ht) != (W, H) or ctype != 6:
            bad.append(f"{el}/{f:04d}.png is {w}x{ht} colortype {ctype}, want {W}x{H} RGBA")
    n = len([f for f in range(a, b + 1) if (root / el / f"{f:04d}.png").exists()])
    print(f"verify {el}: {n}/{b - a + 1} frames")
if bad:
    print("\n".join("MISSING/BAD: " + x for x in bad[:40]), file=sys.stderr)
    sys.exit(1)
PY

echo "pod_render: per-piece timing (wall seconds on the pod; pieces ran concurrently, one GPU)"
python3 -I - "$DATA/blender/logs" <<'PY'
import re, sys
from pathlib import Path
logs = Path(sys.argv[1])
rows = {}
for t in sorted(logs.glob("*.time")):
    label, el, rc, t0, t1 = t.read_text().split()
    log = (logs / f"{label}.log").read_text(errors="replace")
    per = [float(x) for x in re.findall(r"(?:frame \d+: |rendered in )([\d.]+)s", log)]
    r = rows.setdefault(el, {"wall": 0.0, "frames": 0, "sum": 0.0})
    r["wall"] = max(r["wall"], float(t1) - float(t0)); r["frames"] += len(per); r["sum"] += sum(per)
print(f"  {'piece':<11}{'frames':>7}{'wall s':>9}{'s/frame':>9}")
for el, r in rows.items():
    print(f"  {el:<11}{r['frames']:>7}{r['wall']:>9.0f}{(r['sum'] / r['frames'] if r['frames'] else 0):>9.1f}")
PY
echo "pod_render: OK in $(( $(date +%s) - T_START ))s. Remember to stop the pod: python -m filmtools.runpod down <pod id>"
