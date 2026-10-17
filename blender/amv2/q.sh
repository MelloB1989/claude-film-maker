#!/bin/bash
# usage: q.sh <job-name> "<outro.py args>" [out-dir]   -- run a render through the queue and wait
n=$1; a=$2; o=${3:-out/$1}
cat > /home/nikhil/code/.renderq/$n.json <<J
{"tree": ".worktrees/agent-06/outro", "cmd": "blender -b -t 8 --factory-startup -P blender/amv2/outro.py -- $a --out $o && python blender/amv2/sheet.py $o $o/sheet.jpg 4", "out": "$o", "threads": 8}
J
until [ -f /home/nikhil/code/.renderq/$n.done ]; do sleep 3; done
echo "exit $(cat /home/nikhil/code/.renderq/$n.done)"; grep -E "rendered in|Error|Traceback|outro:" /home/nikhil/code/.renderq/$n.log | tail -${4:-12}
