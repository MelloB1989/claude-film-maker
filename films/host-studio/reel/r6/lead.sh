#!/bin/bash
# re-lead both after an editor start / level open: dress_him (then mh.dress Trousers + dress_him if still dropped) / dress_her + seq_dress; lock; exit 1 if any leader fails
cd /tmp/fleet-agent-06-ue/r5/tree/tools; FU=../../fu
LC() { $FU film-ue op mh.leader_check label=$1 | python3 -c "import json,sys;d=json.load(sys.stdin);print('$1 leaders',d['pass'],{k:v['leader'] for k,v in d['garments'].items()});sys.exit(0 if d['pass'] else 1)"; }
DH() { $FU film-ue exec ../films/host-studio/props/his_outfit_ue/dress_him.py 2>&1 | tr -d "\n " | cut -c1-200; echo; }
ok=0
LC Host || { DH; LC Host || { $FU film-ue op mh.dress label=Host 'garments={"Trousers": {"mesh": "/Game/Host/Host_Outfit/SKM_Host_Trousers_Op"}}' 2>&1 | tail -c 300; echo; DH; LC Host || ok=1; }; }
LC Presenter || { $FU film-ue exec ../films/host-studio/props/her_outfit_ue/dress_her.py 2>&1 | tr -d "\n " | cut -c1-200; echo
  $FU film-ue exec ../films/host-studio/props/her_outfit_ue/seq_dress.py 2>&1 | tr -d "\n " | cut -c1-200; echo; LC Presenter || ok=1; }
$FU film-ue op groom.lock 'labels=["Host","Presenter"]' persist=true | python3 -c "import json,sys;d=json.load(sys.stdin);print('lock',d['check']['pass'],d['check'].get('problems'));sys.exit(0 if d['check']['pass'] else 1)" || ok=1
date -u +%H:%M:%S; exit $ok
