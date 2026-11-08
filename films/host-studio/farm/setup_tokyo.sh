#!/bin/bash
# film-farm `up --setup` script for a Tokyo worker made from the plain Deep Learning AMI (NVIDIA driver, no UE): the
# engine and a packed box state (pack_box.sh) restored ONLY from the private Tokyo bucket (same region: no transfer
# charge), then the editor service. Runs once per box as root, before the worker's first claim (~8 min on a
# g6e.2xlarge: box T2's restore took 469 s). Set STATE to the tag pack_box.sh printed before `up`:
#
#     sed 's/^STATE=.*/STATE=T2-20261108-2330/' setup_tokyo.sh > /tmp/setup.sh
#     film-farm --region ap-northeast-1 --bucket rf-render-788655295054-apne1 up her -n 3 --big \
#         --ami ami-0d6aa1676b37d093b --market spot --types g6e.2xlarge --volume-gb 300 --setup /tmp/setup.sh
#
# Idempotent: a marker per finished step, so a rerun repeats nothing that finished.
set -euo pipefail
STATE=unset
ENGINE=engine-5.8.4-20261104
[ "$STATE" != unset ] || { echo "STATE is not set (sed it in before up)"; exit 2; }
TB=rf-render-788655295054-apne1; K=ue-linux/private/xfer; M=/srv/ue/.farm_done_
mkdir -p /srv/ue/projects /home/ubuntu/.config
export AWS_DEFAULT_REGION=ap-northeast-1
aws configure set default.s3.max_concurrent_requests 64; aws configure set default.s3.multipart_chunksize 64MB
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
t0=$(date +%s)
if [ ! -f ${M}deps ]; then
  apt-get -o DPkg::Lock::Timeout=900 update -qq 2>/dev/null
  DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=900 install -y -qq --no-install-recommends zstd jq \
    unzip curl libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgtk-3-0 libnss3 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libasound2 libatk1.0-0 libatk-bridge2.0-0 libxkbcommon0 libxss1 libxtst6 libsecret-1-0 libxcursor1 libxi6 \
    libsdl2-2.0-0 libvulkan1 >/dev/null
  touch ${M}deps; fi
declare -A DEST=([$ENGINE]=/srv/ue/engine [project-HostStudio-$STATE]=/srv/ue/projects
                 [zen-epic-$STATE]=/home/ubuntu/.config [explain-$STATE]=/srv/ue [tools-$STATE]=/srv/ue)
for n in $ENGINE project-HostStudio-$STATE zen-epic-$STATE explain-$STATE tools-$STATE; do
  [ -f ${M}$n ] && { echo "$n: done"; continue; }
  mkdir -p ${DEST[$n]}; a=$(date +%s)
  aws s3 cp --only-show-errors s3://$TB/$K/$n.tar.zst - | zstd -dc -T0 | tar -x -C ${DEST[$n]}   # streamed, no staging
  touch ${M}$n; echo "$n: $(( $(date +%s)-a )) s -> ${DEST[$n]}"
done
aws s3 cp --only-show-errors s3://$TB/$K/$ENGINE.manifest.json /srv/ue/engine/ue-manifest.json
chown -R ubuntu:ubuntu /srv/ue /home/ubuntu/.config
got=$(python3 -c 'import json; print(json.load(open("/srv/ue/projects/HostStudio/STATE.json"))["id"])')
[ "$got" = "$STATE" ] || { echo "STATE.json says $got, wanted $STATE"; exit 3; }
if [ ! -f ${M}service ]; then
  rm -rf /opt/film-src && git clone -q --depth 1 https://github.com/MelloB1989/claude-film-maker.git /opt/film-src
  (cd /opt/film-src/unreal/linux && bash setup.sh service /srv/ue/engine /srv/ue/projects/HostStudio/HostStudio.uproject \
    /Game/Studio/Studio s3://rf-render-788655295054-aps1/ue-linux/secrets/epic/eos_sdk.tgz)
  sed -i 's/^AWS_DEFAULT_REGION=.*/AWS_DEFAULT_REGION=ap-south-1/' /etc/default/ue-editor   # the Epic secret's region
  sudo -u ubuntu -H aws configure set region ap-south-1
  touch ${M}service; fi
systemctl enable --now ue-editor
echo "setup done in $(( $(date +%s)-t0 )) s; state $STATE; editor $(systemctl is-active ue-editor)"
