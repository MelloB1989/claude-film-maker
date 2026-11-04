#!/bin/bash
# Restore a prebuilt Unreal Engine Linux editor from S3 onto a fresh Ubuntu 22.04 instance (minutes, not a rebuild).
#
#   sudo UE_S3=s3://bucket/ue-linux bash ue-restore.sh [version, default: newest under engine/] [dest, default /opt/UnrealEngine]
#
# Streams the tarball out of S3 straight into zstd + tar (no second copy on disk), checks its sha256 against
# manifest.json, and gives the tree to $UE_USER (ubuntu): the editor refuses to run as root.
set -euo pipefail
: "${UE_S3:?UE_S3=s3://bucket/ue-linux}"
export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-ap-south-1}
UE_USER=${UE_USER:-ubuntu}
VER=${1:-}; DEST=${2:-/opt/UnrealEngine}
t0=$(date +%s)
command -v zstd >/dev/null && command -v jq >/dev/null || { apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq zstd jq unzip curl >/dev/null; }
if ! command -v aws >/dev/null; then
  curl -sSfo /tmp/awscliv2.zip https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip
  (cd /tmp && unzip -qo awscliv2.zip && ./aws/install --update >/dev/null)
fi
aws configure set default.s3.max_concurrent_requests 64
aws configure set default.s3.multipart_chunksize 64MB
[ -n "$VER" ] || VER=$(aws s3 ls "$UE_S3/engine/" | awk '/PRE/{print $2}' | tr -d / | sort -V | tail -1)
src=$UE_S3/engine/$VER
aws s3 cp --only-show-errors "$src/manifest.json" /tmp/ue-manifest.json
file=$(jq -r .file /tmp/ue-manifest.json); want=$(jq -r .sha256 /tmp/ue-manifest.json)
echo "restoring $(jq -r '.tag+" "+.commit' /tmp/ue-manifest.json) ($(numfmt --to=iec "$(jq .bytes /tmp/ue-manifest.json)")) to $DEST"
mkdir -p "$DEST"
aws s3 cp --only-show-errors "$src/$file" - | tee >(sha256sum | cut -d' ' -f1 > /tmp/ue-restore.sha) | zstd -dc -T0 | tar -x -C "$DEST"
sleep 1; got=$(cat /tmp/ue-restore.sha)
[ "$got" = "$want" ] || { echo "sha256 mismatch: got $got want $want" >&2; exit 1; }
id "$UE_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$UE_USER"
chown -R "$UE_USER": "$DEST"
cp /tmp/ue-manifest.json "$DEST/ue-manifest.json"
echo "restored in $(( $(date +%s) - t0 ))s: $DEST/Engine/Binaries/Linux/UnrealEditor (sha256 ok)"
