# Gesture library on box B (agent-08, R7)

Headless Blender + plain Python beside the editor: never the editor, its project, level or reel paths. Scratch
`/srv/ue/gesture_r7/agent08/`, `nice -n 15`, Blender `-t 4`, one step at a time. No mocap binary ever goes into git:
the FBX, the retargeted clips and the previews live in `s3://…/ue-linux/assets/gesture/` (bucket as for the props).

```bash
# 0. code (this branch) + her skeleton read (fleet/agent-01/r7-body) + the batch's FBX
B=/srv/ue/gesture_r7/agent08
mkdir -p $B/code $B/fbx $B/work
git -C <tree> fetch origin fleet/agent-08/r7-mocap fleet/agent-01/r7-body
git -C <tree> archive origin/fleet/agent-08/r7-mocap films/host-studio/explainers/gesture films/host-studio/explainers/seatkit.py \
  | tar -x -C $B/code --strip-components=3
git -C <tree> show origin/fleet/agent-01/r7-body:films/host-studio/explainers/skeletons/her_body_read.json > $B/her_body_read.json
aws s3 cp --recursive s3://…/ue-linux/assets/gesture/fbx/ $B/fbx/          # the approved Mixamo FBX

# 1. the batch (dump -> retarget -> annotate -> mirror if left-led -> preview), ~10-40 s per clip
BL=$(ls -d /srv/ue/tools/blender-*/blender | sort -V | tail -1)
cd $B/code/gesture && nice -n 15 python3 batch.py catalog.json $B/fbx $B/her_body_read.json $B/work --blender $BL \
  --only mx_talk_seated_a,mx_talk_seated_b,mx_meeting_desk_f,mx_rest_breathe,mx_rest_table,mx_ask_question,mx_ask_one_hand,mx_happy_hand,mx_two_hand_forward,mx_ask_two_hands,mx_count_five,mx_point_bent,mx_point_seated_fwd,mx_shrug,mx_acknowledge,mx_secret_lean \
  > $B/batch1.log 2>&1

# 2. results to S3 (same region: no egress); the library index back to agent-08
aws s3 cp --recursive $B/work/ s3://…/ue-linux/assets/gesture/r7/ --exclude "*/dump.json"
cat $B/batch1.log; cat $B/work/library.json
```

Batch 1 = the TEST's must-haves (agent-10): talking idles + rests (base layer), open palm, size, beat, count, point,
press, release / wave-off, raise-finger, lean-in. Batch 2 = the rest of `catalog.json`.

Checks, per clip in `batch1.log`: `events` > 0 for every non-rest clip; `mirrored` true only for left-led clips;
`clear` = frames where an upper arm was abducted to keep the elbow >= 4 cm outside the shoulder, with the largest
angle (a clip needing > 25° is dropped or re-cut). Previews are a mannequin (no mesh of hers), so they may leave the
box for review.
