#!/bin/bash
# Drive ue-build.sh / ue-restore.sh on an EC2 instance over SSM (no inbound port, no ssh). Run where the AWS CLI works.
#
#   ue-ssm.sh push                                  copy this directory's scripts to $UE_S3/tools/
#   ue-ssm.sh start <instance> <unit> '<env + script + args>'
#                                                   run a script from $UE_S3/tools/ as a systemd unit (survives the
#                                                   SSM command; log in /data/<unit>.log), e.g.
#                                                   ue-ssm.sh start i-0abc uebuild 'UE_TAG=5.8.4-release ue-build.sh prep source'
#   ue-ssm.sh sh <instance> '<command>'             run a short shell command and print its output
#   ue-ssm.sh status <instance> <unit>              the unit's state and the tail of its log
#
# Env: UE_S3 (s3://rf-render-788655295054-aps1/ue-linux), AWS_REGION (ap-south-1).
set -euo pipefail
UE_S3=${UE_S3:-s3://rf-render-788655295054-aps1/ue-linux}
export AWS_REGION=${AWS_REGION:-ap-south-1}
HERE=$(cd "$(dirname "$0")" && pwd)

run() {  # run <instance> <script>: send, wait, print stdout/stderr
  local id cmd params
  params=$(python3 -c 'import json,sys; print(json.dumps({"commands": [sys.argv[1]], "executionTimeout": ["3600"]}))' "$2")
  id=$(aws ssm send-command --instance-ids "$1" --document-name AWS-RunShellScript --parameters "$params" \
       --timeout-seconds 600 --query Command.CommandId --output text)
  while :; do
    sleep 3
    local st; st=$(aws ssm get-command-invocation --command-id "$id" --instance-id "$1" --query Status --output text 2>/dev/null || echo Pending)
    case $st in Pending|InProgress|Delayed) continue;; esac
    aws ssm get-command-invocation --command-id "$id" --instance-id "$1" --query '[StandardOutputContent,StandardErrorContent]' --output text
    [ "$st" = Success ]; return
  done
}

bootstrap='set -e; mkdir -p /data /opt/ue-tools
command -v aws >/dev/null || { apt-get update -qq && apt-get install -y -qq unzip curl >/dev/null
  curl -sSfo /tmp/awscliv2.zip https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip && (cd /tmp && unzip -qo awscliv2.zip && ./aws/install --update >/dev/null); }
aws s3 cp --quiet --recursive '"$UE_S3"'/tools/ /opt/ue-tools/ && chmod +x /opt/ue-tools/*.sh'

case ${1:-} in
  push) aws s3 cp --only-show-errors --recursive --exclude '*' --include '*.sh' --include '*.py' "$HERE/" "$UE_S3/tools/"
        aws s3 ls "$UE_S3/tools/" ;;
  start) [ $# -eq 4 ] || exit 2
        run "$2" "$bootstrap
systemctl reset-failed $3 2>/dev/null || true
systemd-run --unit=$3 --property=StandardOutput=append:/data/$3.log --property=StandardError=append:/data/$3.log \
  --setenv=UE_S3=$UE_S3 --setenv=AWS_DEFAULT_REGION=$AWS_REGION --working-directory=/opt/ue-tools /usr/bin/env $4
echo started $3" ;;
  sh) run "$2" "$3" ;;
  status) run "$2" "systemctl show $3 -p ActiveState -p Result -p ExecMainStatus | tr '\n' ' '; echo; tail -n ${4:-25} /data/$3.log; echo; cat /data/timings.tsv 2>/dev/null" ;;
  *) sed -n '2,14p' "$0"; exit 2 ;;
esac
