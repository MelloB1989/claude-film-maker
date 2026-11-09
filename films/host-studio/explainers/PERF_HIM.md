# His WhatsApp explainer: the performance (agent-01)

## R7 on box C (the orchestrator, 08 Nov 10:20 IST): agent-06 drives, r7-body 7976d7b6 or later

Box C (`ue-box-c-explainer`, from box B's AMI) runs his whole chain; then his 13 s TEST for the orchestrator.
Same as her R7 TEST chain, which passed its body on box B (0 issues, mesh arms L 5.92 / R 5.30 cm):

```bash
uv run python $P cams --who him                       # FIRST: each camera from his seated eyes (no > 10° direct cut)
uv run python $P signs --who him --bless              # after his perf.calibrate (HEAD_HIM.md 1a-1b)
uv run python $P body --who him --perform             # NEVER --force: the gestures from acting/him.json +
                                                      # acting/timing_him.json (agent-10), set_him.json (his mic)
FACE_SOLVE=full uv run python $P all --who him --from life --bake-chunk 30 --restart-level <his level>
uv run python $P headaxes --who him                   # the head gate: no turn toward the mic (send to agent-04)
```

- body expects: `issues` 0, `upperarm_torso_clear_cm` >= 3 both arms, `hands_in_frame_frac` per camera >= 0.6
  MCU / MCU_L, >= 0.3 CU, ~1.0 WIDE, the mic clear >= 5 cm in each live camera. A fail writes nothing: send me
  `out/explainers/perf/him/body_check.json` (numbers only, never his skeleton).
- Offline his plan reads 49 gestures over 45.6 s of speech = 1.07 onsets/s (the sheet's 0.5-1.2), 10 two-hand.
- `--bake-chunk 30`: 240-frame sampling jobs died on his scene; 30 passes. `--from-bake 2|3` resumes a crash.
- After the perf milestone: ue.sync the project deltas to private S3 for the farm (agent-08).

The sections below are the r6 sheet (box B); the R7 lines above replace its `all` run.

The orchestrator's plan (07 Nov): his explainer runs on box B after her finals, once agent-06's fixed head state is in
box B's project. agent-07 drives. The head side is [HEAD_HIM.md](HEAD_HIM.md) (agent-04): run its step 1 (keep her
signs, `perf.calibrate label=Host`, `rolltest`) first. Every command runs from the kali driver tree with box B's
film-ue config.

```bash
cd tools
P=../films/host-studio/explainers/perform.py
```

## 0. Before it

- agent-07's set, HIM variant: Host on the chair mark, root (20, −20, 0), actor yaw −90 (check it the way hers was
  checked: the eyes split along studio Y). The mic is aimed at his mouth, so commit its numbers as
  `films/host-studio/explainers/set_him.json` (any `seatkit.Set` field, in the actor frame: x forward from the
  mark, y the presenter's right = studio y + 20, z up). Typically `mic` and `boom` (clamp, elbow, tip, capsule);
  `desk_*` too if the desk moved, and `cams` (each presenter camera's position, actor frame) since they are re-aimed
  for his height: the hand-over-mic check reads them. Without the file his body uses her set and cameras.
- His head state pulled from `private/r6/him_state/` into box B's project (box A is terminated after the karma cuts:
  the orchestrator, 07 Nov), with the guards passing: strays, leaders, face luma vs round 4, cull_live parity with box A
  (912 gone, z 144.2-153.3), qa.clip neck on a seated still (agent-09's head_state_parity row). His garments led.
- `set.py --who him` writes `set_him.json` (setplan.set_for_perf): commit it before `body`. Keys that are not
  `seatkit.Set` fields are ignored and named.

## 1. The run

```bash
uv run python $P signs --who her --bless     # FIRST, before his perf.calibrate: the live signs file is still hers
# (HEAD_HIM.md 1a-1b: keep .her_r6, perf.calibrate label=Host)
uv run python $P signs --who him --bless     # right after his calibrate: face/sync refuse a signs file not his
uv run python $P rolltest --who him          # HEAD_HIM.md 1c: send agent-04 the table
uv run python $P all --who him               # body, life, preview, push, solve (17 lines), bias, cams, compose,
                                              # check:solve, workseq, face, check:face, sync, gaze, check:final,
                                              # place, check:placed, bodycheck, numbers
```

`all` stops at the first failure. Restart from that step with `--from <step>`.

| step | what it does | expect | if not |
|---|---|---|---|
| body | his skeleton read and solved IN the editor (it never leaves the box), `AS_exp_him_seat` written | `pass: true`; `tuned` lists any lean or hip change the auto-tune made (lean ≤ 23°, hips ≤ +12.5 cm) | nothing is written on a fail: send agent-01 `out/explainers/perf/him/body_check.json` (numbers) |
| life | breathing additive | 8-22 breaths/min, ≥ 2 mm (read later by bodycheck) | "no body calibration": `$P calibrate_body --who him`, then `--from life` |
| preview | Body = seat + life on SEQ_Explain_Him, garments re-led (`mh.leader` + check) | leaders pass | re-dress (dress_him.py), then preview again |
| solve | 17 mouth-only solves of agent-11's lines (head off, blinks off) | `timing.ok`, no `missing` | a WARNING line: send it |
| cams | each camera's direction from his seated eyes | `pass: true` | a direct cut with a lens move > 10°: agent-07 moves a camera (agent-04's rule), then `--from cams` |
| check:solve / face / final / placed | lipsync.check with the r6 onset window | pass | send the step's JSON |
| bodycheck | what the sequence plays vs desk, seat, mic + the solve | `vs_seatkit` < 1 cm, desk/mic/knee 0 | send it |
| numbers | `numbers/whatsapp/{lips,body}.json` | commit them | lead_in reads an error (not 0) if the editor sees his lips frozen (box A did): send it to agent-09 as is |

Then `qa.clip` in the seated shots (his neck: `garment.neck_px` 0 and `open_edge_shrunk` 0; contacts with the
chair and desk 0), head.py's judge (HEAD_HIM.md §3), stills to the orchestrator, then previews.

## What is his, what is the same as hers

- The same: the seat rules (elbows planted ~2 cm in from the desk edge, forearms lying on the top, hands loose on
  their little-finger edge, shoulders down), the 2.5-frame mouth lead (r5/lipsync.md), the lips gate, the breathing.
- His: his own bone lengths, from his mesh (the solve writes each translation as wanted − (mesh ref − skeleton ref);
  hers was +7.48 cm at the pelvis), `STYLE["him"]` (lean 18°, knees 8 cm out, pronation 72°), mouth gain 1.7 (his rig's
  small jaw travel, round 4), his 15 gestures in `gestures.json` (big ones on his right hand: the mic is on his left).
