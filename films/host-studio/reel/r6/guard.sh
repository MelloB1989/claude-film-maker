#!/bin/bash
# pre-render guard (every render job): strays off the set, leaders + lock, probe_cam 13/13; LUMA=1 also face-luma stills S13 f1040 / S15 f1128 within 0.9-1.1 of round 4
cd /tmp/fleet-agent-06-ue/r5/tree/tools; FU=../../fu; P=/tmp/fleet-agent-06-ue/r6/probes/guard; mkdir -p $P
echo "== guard $(date -u +%H:%M:%S)"
$FU film-ue exec /tmp/fleet-agent-06-ue/r6/strays.py 2>&1 | tr -d '\n ' | tail -c 400; echo
bash /tmp/fleet-agent-06-ue/r6/lead.sh || { echo "GUARD FAIL: leaders"; exit 5; }
$FU python ../films/host-studio/reel/r3/probe_cam.py V01,V02,V03,V04,V05,S11,S12,N01,S13,S15,S16,S17,S18 --check > $P/probe.txt 2>&1 || { echo "GUARD FAIL: probe_cam"; exit 1; }; echo "probe_cam $(grep -c ' OK' $P/probe.txt)/13"
if [ "${LUMA:-0}" = 1 ]; then V=g$(date -u +%H%M)
  for a in "S15 1128" "S13 1040"; do set -- $a; $FU film-ue apply ../films/host-studio/reel/r5/75-still.yaml --set variant=${V}_$1 --set "shots=[\"Reel_$1\"]" --set "frames=[$2,$(($2+1))]" > $P/still_$1.log 2>&1; done
  $FU film-ue sh "cd /srv/ue/r5tree/tools; export FILM_UE_CONF_DIR=/srv/ue/reel/r5/b/conf PATH=\$HOME/.local/bin:\$PATH; for a in 'S15 1128' 'S13 1040'; do set -- \$a; uv run -q --with pillow python ../films/host-studio/reel/r6/face_luma.py --shot \$1 --frames \$2 --img /srv/ue/reel/r5/stills/${V}_\$1 --ref r4=/srv/ue/reel/r3/final_d 2>/dev/null; done" > $P/luma_$V.json; cat $P/luma_$V.json
  python3 -c "
import json,sys
r=[json.loads(l)[0] for l in open('$P/luma_$V.json') if l.startswith('[')]
bad=[(x['shot'],x['ratio_vs_r4']) for x in r if not 0.9<=x['ratio_vs_r4']<=1.1]
print('face_luma', [(x['shot'],x['ratio_vs_r4']) for x in r]); sys.exit(1 if bad or len(r)<2 else 0)" || { echo "GUARD FAIL: face luma"; exit 6; }
fi
echo GUARD-OK
