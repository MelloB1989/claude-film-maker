#!/bin/bash
# Build the Unreal Engine Linux editor from source on a fresh Ubuntu 22.04 EC2 instance and keep everything in S3.
#
#   sudo UE_TAG=5.8.4-release UE_S3=s3://bucket/ue-linux bash ue-build.sh <stage>...
#
# Stages (run in order, or pick some; each one is timed into $UE_WORK/timings.tsv):
#   prep      apt packages, AWS CLI v2, the build user, BuildConfiguration.xml
#   source    source tree: the prepared cache (src/<tag>/prepared.tar.zst) if S3 has it, else the GitHub tarball
#             from $UE_SRC_URL (a short-lived codeload URL; never a token) or src/<tag>/github.tar.gz, + Setup.sh,
#             then saves prepared.tar.zst so a rebuild never touches GitHub or Epic's CDN
#   generate  GenerateProjectFiles.sh (not needed by the build itself; kept to check the tree is sane)
#   extras    copy extra source plugins from $UE_S3/plugins/<Name>/ into Engine/Plugins/<Name> (e.g. Fab from a
#             launcher install), without Binaries/ or Intermediate/, so the next build compiles them for Linux
#   build     UnrealEditor, ShaderCompileWorker, InterchangeWorker, UnrealPak (+ the plugins a project enables: UE_PROJECT=<.uproject> or
#             UE_PLUGINS="PythonScriptPlugin,MovieRenderPipeline,..." which makes a content-only probe project)
#   package   zstd tarball of the runnable engine + manifest.json -> $UE_S3/engine/<version>/
#   smoke     ue-smoke.sh against the built tree
#
# Env: UE_TAG (required), UE_S3 (required, e.g. s3://rf-render-788655295054-aps1/ue-linux), UE_WORK (/data),
#      UE_SRC_URL, UE_COMMIT (recorded in the manifest), UE_PROJECT, UE_PLUGINS, UE_JOBS (parallel actions; default = all cores, memory-capped by UBT),
#      UE_ZSTD_LEVEL (default 12). Runs as root (SSM); compiles and runs the engine as user $UE_USER (ubuntu): the
#      editor refuses to run as root.
set -euo pipefail
: "${UE_TAG:?UE_TAG=5.8.4-release}" "${UE_S3:?UE_S3=s3://bucket/ue-linux}"
UE_WORK=${UE_WORK:-/data}
UE_USER=${UE_USER:-ubuntu}
UE_ROOT=$UE_WORK/UnrealEngine
UE_ZSTD_LEVEL=${UE_ZSTD_LEVEL:-12}
HERE=$(cd "$(dirname "$0")" && pwd)
LOG=$UE_WORK/build.log
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
mkdir -p "$UE_WORK"
export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-ap-south-1}

say() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG" >&2; }
as_user() { sudo -u "$UE_USER" -H env HOME="/home/$UE_USER" "$@"; }
s3sync_log() { aws s3 cp --quiet "$LOG" "$UE_S3/logs/$UE_TAG/build.log" || true
               aws s3 cp --quiet "$UE_WORK/timings.tsv" "$UE_S3/logs/$UE_TAG/timings.tsv" || true; }
s3_has() { aws s3 ls "$1" >/dev/null 2>&1; }
timed() {  # timed <name> <fn>
  local t0=$(date +%s); say "== $1 start"
  "$2"
  local dt=$(( $(date +%s) - t0 ))
  printf '%s\t%s\t%s\n' "$1" "$dt" "$(date -u +%FT%TZ)" >> "$UE_WORK/timings.tsv"
  say "== $1 done in ${dt}s"; s3sync_log
}

stage_prep() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get -o DPkg::Lock::Timeout=900 update -qq
  apt-get -o DPkg::Lock::Timeout=900 install -y -qq zstd pigz unzip curl jq build-essential xdg-user-dirs >/dev/null
  if ! command -v aws >/dev/null; then
    curl -sSfo /tmp/awscliv2.zip https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip
    (cd /tmp && unzip -qo awscliv2.zip && ./aws/install --update >/dev/null)
  fi
  aws configure set default.s3.max_concurrent_requests 64
  aws configure set default.s3.multipart_chunksize 64MB
  id "$UE_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$UE_USER"
  chown "$UE_USER": "$UE_WORK"
  # UBT: every logical core (default: one action per physical core), 1.5 GiB free per action, the plain parallel
  # executor (UBA on Linux is new and broke ISPC headers in 5.5), no dump_syms pass (slow; symbols are split anyway).
  local cfg=/home/$UE_USER/.config/Unreal\ Engine/UnrealBuildTool
  mkdir -p "$cfg"
  cat > "$cfg/BuildConfiguration.xml" <<XML
<?xml version="1.0" encoding="utf-8" ?>
<Configuration xmlns="https://www.unrealengine.com/BuildConfiguration">
  <BuildConfiguration>
    ${UE_JOBS:+<MaxParallelActions>$UE_JOBS</MaxParallelActions>}
    <bAllCores>true</bAllCores>
    <bAllowUBAExecutor>false</bAllowUBAExecutor>
    <bAllowUBALocalExecutor>false</bAllowUBALocalExecutor>
    <bDisableDumpSyms>true</bDisableDumpSyms>
  </BuildConfiguration>
  <ParallelExecutor>
    <ProcessorCountMultiplier>2</ProcessorCountMultiplier>
    <MemoryPerActionBytes>1610612736</MemoryPerActionBytes>
  </ParallelExecutor>
</Configuration>
XML
  chown -R "$UE_USER": "/home/$UE_USER/.config"
  say "cores: $(nproc), mem: $(free -g | awk '/Mem:/{print $2}') GiB, disk: $(df -h "$UE_WORK" | awk 'NR==2{print $2" "$4" free"}')"
}

stage_source() {
  local src=$UE_S3/src/$UE_TAG
  if [ -e "$UE_ROOT/Engine/Build/OneTimeSetupPerformed" ]; then say "source already prepared"; return; fi
  if s3_has "$src/prepared.tar.zst"; then
    say "restoring prepared source from $src/prepared.tar.zst"
    mkdir -p "$UE_ROOT"
    aws s3 cp --only-show-errors "$src/prepared.tar.zst" - | zstd -dc -T0 | tar -x -C "$UE_ROOT"
    chown -R "$UE_USER": "$UE_ROOT"; return
  fi
  local tgz=$UE_WORK/github.tar.gz
  if [ ! -s "$tgz" ]; then
    if s3_has "$src/github.tar.gz"; then aws s3 cp --only-show-errors "$src/github.tar.gz" "$tgz"
    else
      : "${UE_SRC_URL:?no cached source in $src: set UE_SRC_URL to the codeload URL}"
      local t0=$(date +%s)
      curl -sSfL --retry 3 -o "$tgz" "$UE_SRC_URL"   # never logged: the URL carries a short-lived token
      say "github tarball: $(du -h "$tgz" | cut -f1) in $(( $(date +%s) - t0 ))s"
      aws s3 cp --only-show-errors "$tgz" "$src/github.tar.gz" &
    fi
  fi
  rm -rf "$UE_ROOT"; mkdir -p "$UE_ROOT"
  # GitHub names the top directory <owner>-<repo>-<sha>; for an annotated tag that is the TAG OBJECT's sha, not the
  # commit's: the caller resolves the commit (GET /repos/<repo>/git/tags/<sha>) and passes it as UE_COMMIT
  local top; top=$(set +o pipefail; tar -tzf "$tgz" 2>/dev/null | head -1); top=${top%%/*}
  echo "${top##*-}" > "$UE_WORK/tarball-id.txt"; say "tarball id: $(cat "$UE_WORK/tarball-id.txt")"
  pigz -dc -p 32 "$tgz" | tar -x -C "$UE_ROOT" --strip-components=1
  chown -R "$UE_USER": "$UE_ROOT"
  wait
  local t0=$(date +%s)
  # --force: no prompt; skip other host platforms' binaries
  as_user bash -c "cd '$UE_ROOT' && ./Setup.sh --force --threads=64 --exclude=Mac --exclude=osx64 --exclude=osx32 --exclude=IOS --exclude=TVOS --exclude=Win32" 2>&1 | tail -n 30 | tee -a "$LOG"
  test -e "$UE_ROOT/Engine/Build/OneTimeSetupPerformed"
  printf 'setup.sh\t%s\t%s\n' "$(( $(date +%s) - t0 ))" "$(date -u +%FT%TZ)" >> "$UE_WORK/timings.tsv"
  say "prepared tree: $(du -sh "$UE_ROOT" | cut -f1); saving prepared.tar.zst"
  tar -C "$UE_ROOT" -cf - . | zstd -q -T0 -3 | aws s3 cp --only-show-errors --expected-size 80000000000 - "$src/prepared.tar.zst"
}

stage_generate() { as_user bash -c "cd '$UE_ROOT' && ./GenerateProjectFiles.sh" 2>&1 | tail -n 5 | tee -a "$LOG"; }

stage_extras() {
  local n
  for n in $(aws s3 ls "$UE_S3/plugins/" | awk '/PRE/{print $2}' | tr -d /); do
    say "extra plugin $n"
    rm -rf "$UE_ROOT/Engine/Plugins/$n"
    aws s3 sync --only-show-errors --exclude 'Binaries/*' --exclude 'Intermediate/*' "$UE_S3/plugins/$n/" "$UE_ROOT/Engine/Plugins/$n/"
    find "$UE_ROOT/Engine/Plugins/$n" -depth -type d -empty -delete
  done
  chown -R "$UE_USER": "$UE_ROOT/Engine/Plugins"
}

probe_project() {  # a content-only project that enables $UE_PLUGINS, so their modules get built into the engine
  local d=$UE_WORK/Probe; mkdir -p "$d"
  python3 - "$d/Probe.uproject" "${UE_PLUGINS:-}" <<'PY'
import json, sys
names = [p.strip() for p in sys.argv[2].split(",") if p.strip()]
json.dump({"FileVersion": 3, "EngineAssociation": "", "Category": "", "Description": "plugin probe",
           "Plugins": [{"Name": n, "Enabled": True} for n in names]}, open(sys.argv[1], "w"), indent=1)
PY
  chown -R "$UE_USER": "$d"; echo "$d/Probe.uproject"
}

stage_build() {
  local proj=${UE_PROJECT:-}
  [ -z "$proj" ] && [ -n "${UE_PLUGINS:-}" ] && proj=$(probe_project)
  local p=${proj:+ -Project=$proj}
  # a tag tarball has no prebuilt UnrealBuildTool (GenerateProjectFiles.sh would build it): build it first
  say "building UnrealBuildTool"
  as_user bash -c "cd '$UE_ROOT' && Engine/Build/BatchFiles/BuildUBT.sh" 2>&1 | tail -n 3 | tee -a "$LOG"
  test -e "$UE_ROOT/Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll"
  # one UBT run for every target, so they share one action queue
  say "building UnrealEditor, ShaderCompileWorker, InterchangeWorker, UnrealPak${proj:+ with the plugins of $proj}"
  as_user bash -c "cd '$UE_ROOT' && Engine/Build/BatchFiles/Linux/Build.sh -WaitMutex \
      '-Target=UnrealEditor Linux Development$p' '-Target=ShaderCompileWorker Linux Development' \
      '-Target=InterchangeWorker Linux Development' '-Target=UnrealPak Linux Development'" 2>&1 \
    | tee "$UE_WORK/ubt.log" | grep -E --line-buffered '^\[[0-9]+/[0-9]+\]|error|Total time|Result:|[Pp]arallel|actions|Executor' \
    | awk '!/^\[/ || NR%250==1 {print; fflush()}' | tee -a "$LOG"
  grep -q 'Result: Succeeded' "$UE_WORK/ubt.log"
}

stage_package() {
  local ver; ver=$(jq -r '"\(.MajorVersion).\(.MinorVersion).\(.PatchVersion)"' "$UE_ROOT/Engine/Build/Build.version")
  local dst=$UE_S3/engine/$ver; local out=$UE_WORK/UnrealEngine-$ver-linux.tar.zst
  # the runnable engine: no intermediates, no caches, no split debug symbols (huge, kept separately if wanted)
  tar -C "$UE_ROOT" --exclude='./Engine/Intermediate' --exclude='*/Intermediate/Build' --exclude='./Engine/Saved' \
      --exclude='./Engine/DerivedDataCache' --exclude='*.debug' --exclude='*.sym' --exclude='./.git' \
      -cf - . | zstd -q -T0 -"$UE_ZSTD_LEVEL" -o "$out"
  local sha size usize
  sha=$(sha256sum "$out" | cut -d' ' -f1); size=$(stat -c %s "$out")
  usize=$(du -sb --exclude=Intermediate --exclude=Saved --exclude=DerivedDataCache --exclude='*.debug' --exclude='*.sym' "$UE_ROOT" | cut -f1)
  jq -n --arg tag "$UE_TAG" --arg commit "${UE_COMMIT:-}" --arg tobj "$(cat "$UE_WORK/tarball-id.txt" 2>/dev/null)" --arg ver "$ver" \
     --arg sha "$sha" --argjson size "$size" --argjson usize "$usize" --arg plugins "${UE_PLUGINS:-}" \
     --arg built "$(date -u +%FT%TZ)" --arg host "$(curl -s -m 2 http://169.254.169.254/latest/meta-data/instance-type || true)" \
     --arg file "$(basename "$out")" --arg clang "$(ls "$UE_ROOT"/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/ 2>/dev/null | head -1)" \
     '{tag:$tag, commit:$commit, tag_object:$tobj, version:$ver, target:"UnrealEditor, ShaderCompileWorker, InterchangeWorker, UnrealPak (Linux Development)",
       plugins:($plugins|split(",")|map(select(length>0))), toolchain:$clang, file:$file, sha256:$sha,
       bytes:$size, unpacked_bytes:$usize, built:$built, built_on:$host, excludes:["Intermediate","Saved","DerivedDataCache","*.debug","*.sym"]}' \
     > "$UE_WORK/manifest.json"
  aws s3 cp --only-show-errors "$out" "$dst/$(basename "$out")"
  aws s3 cp --only-show-errors "$UE_WORK/manifest.json" "$dst/manifest.json"
  aws s3 cp --only-show-errors "$HERE/ue-restore.sh" "$dst/ue-restore.sh"
  say "packaged $(numfmt --to=iec "$size") (unpacked $(numfmt --to=iec "$usize")) -> $dst"
}

stage_smoke() { UE_ROOT=$UE_ROOT UE_USER=$UE_USER bash "$HERE/ue-smoke.sh" 2>&1 | tee -a "$LOG"; }

[ $# -gt 0 ] || { sed -n '2,20p' "$0"; exit 2; }
for s in "$@"; do timed "$s" "stage_$s"; done
