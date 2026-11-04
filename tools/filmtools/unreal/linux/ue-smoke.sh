#!/bin/bash
# Smoke-test a Linux Unreal editor headless: start UnrealEditor (Linux has no -Cmd binary) with no RHI on a throwaway project that enables
# the Python plugin, run a Python script, and check what it wrote. Optional: UE_SMOKE_RENDER=1 also tries
# -RenderOffscreen (needs a Vulkan driver: a GPU, or mesa's lavapipe on a CPU box).
#
#   sudo UE_ROOT=/opt/UnrealEngine bash ue-smoke.sh
set -uo pipefail
UE_ROOT=${UE_ROOT:-/opt/UnrealEngine}; UE_USER=${UE_USER:-ubuntu}
P=$(mktemp -d /tmp/ue-smoke.XXXX); chmod 755 "$P"
cat > "$P/Smoke.uproject" <<'J'
{"FileVersion": 3, "EngineAssociation": "", "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": true}]}
J
cat > "$P/smoke.py" <<PY
import unreal
v = unreal.SystemLibrary.get_engine_version()
open("$P/result.txt", "w").write(v + "\n")
unreal.log("SMOKE_OK " + v)
PY
chown -R "$UE_USER": "$P"
run() {  # run <label> <extra args>
  local t0=$(date +%s)
  sudo -u "$UE_USER" -H timeout 900 "$UE_ROOT/Engine/Binaries/Linux/UnrealEditor" "$P/Smoke.uproject" \
    -ExecutePythonScript="$P/smoke.py" -unattended -nosplash -nopause -nosound -stdout -FullStdOutLogOutput $2 \
    > "$P/$1.log" 2>&1
  local rc=$?
  echo "$1: exit $rc in $(( $(date +%s) - t0 ))s; $(grep -m1 -o 'SMOKE_OK.*' "$P/$1.log" || echo 'no SMOKE_OK line')"
  grep -E 'Error:|Fatal' "$P/$1.log" | grep -v -i 'shader\|ddc' | head -5
}
rm -f "$P/result.txt"; run nullrhi "-nullrhi"
ok=0; [ -s "$P/result.txt" ] && { echo "engine version from Python: $(cat "$P/result.txt")"; ok=1; }
if [ "${UE_SMOKE_RENDER:-0}" = 1 ]; then rm -f "$P/result.txt"; run offscreen "-RenderOffscreen"; fi
echo "logs: $P"
[ $ok = 1 ]
