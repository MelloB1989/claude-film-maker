#!/bin/bash
# GPU render of the Timeless v3 outro (blender/amv3/outro3.py, comp frames 819-899) on a RunPod 4090, run from the VM.
#
#   blender/amv3/pod_outro3.sh <pod-ip> <ssh-port> [--samples 64] [--device OPTIX|CUDA] [--procs 2] [--res-scale 1]
#                              [--frames 819-899] [--no-bootstrap] [--key ~/.ssh/id]
#
# Frames land in $AMV3_DATA/blender/outro3/NNNN.png (opaque RGBA 1920x1080), the packed .blend in
# $AMV3_DATA/blender/outro3.blend. Same steps as blender/amv2/pod_render.sh: bootstrap (Blender 5.2.2) -> OPTIX check
# (falls back to CUDA) -> ship blender/ + fonts -> render in a few processes sharing the GPU -> pull -> verify every frame.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
if [ $# -lt 2 ]; then sed -n 2,9p "$0"; exit 2; fi
IP=$1; PORT=$2; shift 2
SAMPLES=64; DEVICE=OPTIX; PROCS=2; RES=1; FRAMES=819-899; BOOT=1; KEY=""
while [ $# -gt 0 ]; do
  case $1 in
    --samples) SAMPLES=$2; shift 2;;
    --device) DEVICE=$2; shift 2;;
    --procs) PROCS=$2; shift 2;;
    --res-scale) RES=$2; shift 2;;
    --frames) FRAMES=$2; shift 2;;
    --no-bootstrap) BOOT=0; shift;;
    --key) KEY=$2; shift 2;;
    *) echo "pod_outro3: unknown option $1" >&2; exit 2;;
  esac
done
DATA="${AMV3_DATA:-/home/nikhil/code/film-making/work/timeless_v3}"
mkdir -p "$DATA/blender/outro3"
SSHO=(-p "$PORT" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=20 -o BatchMode=yes)
[ -n "$KEY" ] && SSHO+=(-i "$KEY")
pod() { ssh "${SSHO[@]}" "root@$IP" "$@"; }
die() { echo "pod_outro3: FAIL: $*" >&2; exit 1; }
T_START=$(date +%s)
echo "pod_outro3: root@$IP:$PORT samples $SAMPLES device $DEVICE procs $PROCS frames $FRAMES -> $DATA/blender/outro3"
pod 'echo connected: $(hostname); nvidia-smi --query-gpu=name,memory.total --format=csv,noheader' || die "cannot ssh to the pod"

if [ $BOOT = 1 ]; then
  pod 'export DEBIAN_FRONTEND=noninteractive; command -v rsync >/dev/null || { apt-get update -qq >/dev/null && apt-get install -y -qq rsync >/dev/null; }'
  pod 'bash -s' < "$REPO/tools/filmtools/pod_bootstrap.sh" > /tmp/pod_outro3_boot.$$.log 2>&1 || true
  tail -5 /tmp/pod_outro3_boot.$$.log; rm -f /tmp/pod_outro3_boot.$$.log
fi
pod 'blender --version | head -1' | grep -q "Blender 5.2" || die "Blender 5.2 is not installed on the pod (run without --no-bootstrap)"
if [ "$DEVICE" = OPTIX ]; then
  N=$(pod "blender -b --factory-startup --python-expr 'import bpy
p = bpy.context.preferences.addons[\"cycles\"].preferences
p.compute_device_type = \"OPTIX\"; p.get_devices(); print(\"NOPTIX\", len([d for d in p.devices if d.type == \"OPTIX\"]))' 2>/dev/null | awk '/^NOPTIX/ {print \$2}'" || echo 0)
  [ "${N:-0}" -gt 0 ] || { echo "pod_outro3: OPTIX not visible, using CUDA"; DEVICE=CUDA; }
fi

# ship: outro3 imports blender/amv2/outro.py; the Spider-Man font is outside git
pod 'mkdir -p /root/cfm/films/timeless/fonts /root/frames'
(cd "$REPO" && tar cz --exclude=__pycache__ --exclude='*.blend' blender/amv2 blender/amv3 films/timeless/fonts) | pod 'rm -rf /root/cfm/blender && tar xz -C /root/cfm'
cat /home/nikhil/code/film-making/handover/amv_handover/fonts/Spider-Man.otf.ttf | pod 'cat > /root/cfm/films/timeless/fonts/Spider-Man.otf.ttf'

A=${FRAMES%-*}; B=${FRAMES#*-}
pod "rm -rf /root/frames/outro3 /root/frames/log; mkdir -p /root/frames/outro3 /root/frames/log"
pod "bash -s" <<REMOTE 2>&1 | sed -u 's/^/  pod: /' || die "a render process failed (logs in /root/frames/log on the pod)"
set -e
cd /root/cfm
export AMV2_FONT=/root/cfm/films/timeless/fonts/Spider-Man.otf.ttf
COMMON="--res-scale $RES --samples $SAMPLES --device $DEVICE --out /root/frames/outro3"
# the packed .blend (no render), then $PROCS interleaved frame sets sharing the GPU
blender -b --factory-startup --python-exit-code 1 -P blender/amv3/outro3.py -- \$COMMON --no-render --save /root/frames/outro3_raw.blend > /root/frames/log/save.log 2>&1
blender -b --factory-startup /root/frames/outro3_raw.blend --python-exit-code 1 -P blender/amv2/pack_blend.py -- --out /root/frames/outro3.blend >> /root/frames/log/save.log 2>&1
pids=()
for ((i = 0; i < $PROCS; i++)); do
  fr=\$(python3 -c "print(','.join(str(f) for f in range($A + \$i, $B + 1, $PROCS)))")
  blender -b --factory-startup --python-exit-code 1 -P blender/amv3/outro3.py -- \$COMMON --frames "\$fr" > /root/frames/log/r\$i.log 2>&1 &
  pids+=(\$!)
done
rc=0; for p in "\${pids[@]}"; do wait \$p || rc=1; done
grep -h "rendered in" /root/frames/log/r*.log | awk '{s+=\$(NF); n++} END {printf "frames %d, mean %.1f s/frame per process\n", n, s/n}'
exit \$rc
REMOTE

if command -v rsync >/dev/null; then
  rsync -a -e "ssh ${SSHO[*]}" "root@$IP:/root/frames/outro3/" "$DATA/blender/outro3/"
else
  pod 'tar c -C /root/frames/outro3 .' | tar x -C "$DATA/blender/outro3"
fi
pod 'cat /root/frames/outro3.blend' > "$DATA/blender/outro3.blend"
python3 -I - "$DATA/blender/outro3" "$A" "$B" "$RES" <<'PY' || die "missing or bad frames"
import struct, sys
from pathlib import Path
root, a, b, res = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
W, H = round(1920 * res), round(1080 * res)
bad = []
for f in range(a, b + 1):
    p = root / f"{f:04d}.png"
    if not p.exists():
        bad.append(f"{f:04d} missing"); continue
    h = p.read_bytes()[:26]
    w, ht, _d, ctype = struct.unpack(">IIBB", h[16:26])
    if (w, ht, ctype) != (W, H, 6):
        bad.append(f"{f:04d} is {w}x{ht} colortype {ctype}")
print(f"verify outro3: {b - a + 1 - len(bad)}/{b - a + 1} frames ok")
if bad:
    print("\n".join(bad[:30]), file=sys.stderr); sys.exit(1)
PY
echo "pod_outro3: OK in $(( $(date +%s) - T_START ))s. Stop the pod when done."
