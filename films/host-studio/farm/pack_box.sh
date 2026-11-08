#!/bin/bash
# Pack an editor box's state (the project, Zen's DDC, explain/ and tools/) as zstd tarballs into its own region's
# PRIVATE bucket prefix (same region: no transfer charge), for film-farm workers made with `up --setup` from
# setup_tokyo.sh. Run as root ON THE BOX by its driver, when it is idle (no render, everything saved):
#
#     sudo bash pack_box.sh T2-20261108-2330          # the state tag: STATE.json id, the tarballs' suffix
#
# The editor is stopped while Zen and the project are read (zenserver holds its files open), and started again at
# the end. Face rule: the tarballs hold the presenter; they go to ue-linux/private/ only, SSE-KMS, the box role.
set -euo pipefail
TAG=${1:?usage: pack_box.sh <state tag>}
case "$TAG" in *[!A-Za-z0-9._-]*) echo "bad tag $TAG"; exit 2;; esac
exec > >(tee -a /var/log/film-pack.log) 2>&1
. /etc/default/ue-editor
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' \
  http://169.254.169.254/latest/api/token)" http://169.254.169.254/latest/meta-data/placement/region)
declare -A BUCKET=([ap-south-1]=rf-render-788655295054-aps1 [ap-northeast-1]=rf-render-788655295054-apne1)
D=s3://${BUCKET[$REGION]:?no bucket for $REGION}/ue-linux/private/xfer
PROJ=$(dirname "$UE_PROJECT")
export AWS_DEFAULT_REGION=$REGION
aws configure set default.s3.max_concurrent_requests 32; aws configure set default.s3.multipart_chunksize 128MB
command -v zstd >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq zstd >/dev/null

echo "{\"id\": \"$TAG\", \"packed\": \"$(date -u +%FT%TZ)\", \"from\": \"$(hostname)\"}" > "$PROJ/STATE.json"
chown ubuntu:ubuntu "$PROJ/STATE.json"
systemctl stop ue-editor
trap 'systemctl start ue-editor' EXIT
pkill -u ubuntu -f '[z]enserver' || true; sleep 3
: > /tmp/pack-manifest.jsonl
pack() { # name parent item [tar excludes...]
  local name=$1 parent=$2 item=$3; shift 3
  local raw t0; raw=$(du -sb "$parent/$item" | cut -f1); t0=$(date +%s)
  tar -C "$parent" "$@" -cf - "$item" | zstd -3 -T0 -q | tee >(sha256sum | cut -d' ' -f1 > /tmp/$name.sha) \
    >(wc -c > /tmp/$name.bytes) | aws s3 cp --only-show-errors --sse aws:kms --expected-size "$raw" - "$D/$name.tar.zst"
  sleep 2
  echo "{\"name\":\"$name.tar.zst\",\"raw\":$raw,\"bytes\":$(cat /tmp/$name.bytes),\"sha256\":\"$(cat /tmp/$name.sha)\",\"s\":$(( $(date +%s)-t0 ))}" \
    | tee -a /tmp/pack-manifest.jsonl
}
pack "project-HostStudio-$TAG" "$(dirname "$PROJ")" "$(basename "$PROJ")" --exclude="$(basename "$PROJ")/Intermediate" \
  --exclude="$(basename "$PROJ")/Saved/Logs" --exclude="$(basename "$PROJ")/Saved/Crashes"
pack "zen-epic-$TAG" /home/ubuntu/.config Epic
pack "explain-$TAG" /srv/ue explain
pack "tools-$TAG" /srv/ue tools
python3 -c 'import json,sys; print(json.dumps([json.loads(l) for l in open(sys.argv[1])], indent=1))' /tmp/pack-manifest.jsonl \
  > "/tmp/xfer-manifest-$TAG.json"
aws s3 cp --only-show-errors --sse aws:kms "/tmp/xfer-manifest-$TAG.json" "$D/xfer-manifest-$TAG.json"
echo "PACK_DONE $TAG -> $D"
