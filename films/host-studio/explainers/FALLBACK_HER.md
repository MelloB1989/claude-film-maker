# Her fallback: chest-up talking shots, hands at rest in the WIDE (prepared, NOT applied)

The operator's fallback (orchestrator, 08 Nov), only if her hands still look bad on the r7I preview:
1. The talking shots (MCU, CU, and the MCU_L panel shots) are framed UP TO HER CHEST. The hands go out of frame; the
   gestures still play below the frame edge, so the shoulders move naturally.
2. Every shot that shows her full upper body and hands (only the WIDE) has her hands RESTING idle on the desk: the
   palm-down rest, small natural micro-motion, no gestures. The shoulders, torso and head stay alive.

Source: edl/netflix.json (1427 f at 24 fps, the cut agent-06's r7-boxb renders). The render shots carry ±6 frames of
handles (the farm/render.py layout `shot<NN>_<CAM>/<frame:04d>.png`).

## The EDL shots under the fallback

| Shot | Camera (render dir) | Kind | Frames | Seconds | With handles (s) | Line | Change |
|---|---|---|---|---|---|---|---|
| 01 | CAM_MCU (`shot01_CAM_MCU`) | pres | 0-98 | 0.000-4.083 | -0.250-4.333 | N01 | chest-up framing |
| 02 | CAM_CU (`shot02_CAM_CU`) | pres | 98-141 | 4.083-5.875 | 3.833-6.125 | N02 | chest-up framing |
| 04 | CAM_MCU (`shot04_CAM_MCU`) | pres | 196-305 | 8.167-12.708 | 7.917-12.958 | N04 | chest-up framing |
| 06 | CAM_MCU_L (`shot06_CAM_MCU_L`) | panel | 406-556 | 16.917-23.167 | 16.667-23.417 | N06-N07 | chest-up framing, keep her clear of the right-hand panel card |
| 07 | CAM_CU (`shot07_CAM_CU`) | pres | 556-656 | 23.167-27.333 | 22.917-27.583 | N08 | chest-up framing |
| 10 | CAM_MCU_L (`shot10_CAM_MCU_L`) | panel | 954-1040 | 39.750-43.333 | 39.500-43.583 | N12 | chest-up framing, keep her clear of the panel card |
| 11 | CAM_WIDE (`shot11_CAM_WIDE`) | pres | 1040-1162 | 43.333-48.417 | 43.083-48.667 | N13 | framing unchanged; **rest_only** for the whole shot |
| 13 | CAM_MCU (`shot13_CAM_MCU`) | pres | 1278-1352 | 53.250-56.333 | 53.000-56.583 | N15 | chest-up framing |
| 14 | CAM_CU (`shot14_CAM_CU`) | pres | 1352-1391 | 56.333-57.958 | 56.083-58.208 | N16 | chest-up framing |

Unchanged: the graphics shots 03 (title), 05 (oca), 08 (ladder), 09 (abr), 12 (planes) and 15 (end) have no presenter.

So: **8 shots get the chest-up framing (01, 02, 04, 06, 07, 10, 13, 14) and 1 shot goes rest-only (11, the WIDE).**

## The rest_only range (for agent-01's body mode)

- rest_only: **sequence f1034-1168 (43.083-48.667 s)**, shot 11 with its handles.
- Have the hands ARRIVE at the rest by f1028 (42.83 s), 0.5 s before the handle starts. They travel during the tail
  of shot 10, which is chest-up, so the travel is below the frame edge and never seen. Leave the rest after f1168
  (48.67 s), during graphics shot 12 (no presenter).
- Inside the range: palm-down rest, forearms on the desk TOP (the placed desk geometry, not the seat-space desk;
  the orchestrator's catalogue v3 REST pose), fingers relaxed with small micro-motion. The torso lean, the shoulders,
  breathing, nods and the face follow the sheet as now (acting/her.json N13: face beats, lean, smile on "AWS.").
- The sheet's N13 gestures (the three LIST items, the "that" open palm, the "AWS." beat) are simply not played in
  that range. No sheet change: rest_only by time range overrides them.

## Chest-up framing: what to keep the same

- Keep the camera NAMES (CAM_MCU, CAM_CU, the panel's CAM_MCU_L) and change only their transforms/lens. Then the
  EDL, render.py's shot dirs, the S3 layout and composite.py all stay as they are. A new camera name would mean
  editing edl/netflix.json (`camera`) and the render shot list.
- Frame edge just below the bust line / mid-chest, so a hand that rises in a beat may cross the edge briefly. If any
  hand must never be seen, cap the gesture apex (gesturekit) at the frame edge for these cams.
- The lower third (agent-12's lowerthird.mov, top-left, card to x 680, y ~80-245) plays over shot 01 (f12-84). With a chest-up
  MCU her head sits larger and higher: check the card clears her head and hair in shot 01 (I check it in the
  composite stills at f48).
- The panel shots (06, 10): her frame-left placement and the right-hand card (prefill, buffer) stay as now.

## Gate rows that change (agent-09)

- hands_in_frame for CAM_MCU / CAM_CU / CAM_MCU_L: ~0 by design, so the per-camera minimum (acting.py IN_FRAME:
  MCU 0.6, CU 0.3) no longer applies. Report it as info.
- In the WIDE (shot 11): gesture_onsets_per_s ~0 and the LIST/claw rows have nothing to measure. hands_above_desk_frac
  is not a goal there (the hands ARE on the desk). rest_contact (the hands on the desk top, not the edge) becomes the
  row that matters, plus a micro-motion row (not frozen, not fidgeting).
- The face rows (expr_active, smiles, brow flashes, neutral_hold) are unchanged. The body rows that stay meaningful:
  lean/torso motion, shoulder motion with the off-frame gestures, and breath.

## The composite

No change: composite.py reads the shots by EDL camera name. If the camera names change after all, re-point
edl/netflix.json and the composite follows.
