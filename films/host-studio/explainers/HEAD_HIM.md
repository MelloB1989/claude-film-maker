# His WhatsApp explainer on box B (spot): the head pass (agent-04)

The orchestrator's plan (07 Nov, third revision, the operator's): box A is saved and terminated after the karma cuts;
his explainer runs on BOX B (spot) after her v2. agent-06 puts his fixed head state under `private/r6/him_state/`
(manifest + sha256); box B's driver (agent-11 until 21:00 IST, then agent-07) pulls it in with the editor stopped,
restarts and runs the guards (QA.md garment.head_state_parity: strays, leaders, face-luma vs r4, cull_live 912 gone /
z 144.2-153.3 as on A, qa.clip neck on a seated still) and `set.py --who him` BEFORE this sheet. agent-01's perform.py
calls `head.face_args` (this branch, `head.py`) for the face's gaze, nods and blinks. Every command runs from the kali
driver tree with box B's film-ue config, passing box B's instance explicitly.

```bash
cd tools
P=../films/host-studio/explainers/perform.py
H=../films/host-studio/explainers/head.py
CUE=../films/host-studio/explainers/cues/him.json     # agent-11's (fleet/agent-11/r6-explainers)
```

## 1. Before his performance (after the pull and the guards)

| step | command | expect | if not |
|---|---|---|---|
| 1a | keep her calibration: copy `<project>/Saved/.../signs_Face_Archetype_Skeleton.json` to `….her_r6`, and `uv run python $P signs --who her --bless` (agent-01, 7891afdb+) | file kept, her sha recorded | — |
| 1b | `film-ue op perf.calibrate label=Host turn_by=auto` (always on box B: its Saved/ calibration is her face's), then copy it to `….him_r6` and `uv run python $P signs --who him --bless` | `turn_on` Face, curves/signs/yaw_table/eye_deg as box A's file in him_state/ (yaw_table identity, eye_deg within 10 %); `turn_strength` (~1.04, box A K2c 1.041) is only in the op response's `raw`: the saved file keeps yaw_gain 1.0 for any strength >= 0.9 | a mismatch, or turn_strength over 10 % from 1.04: stop and tell agent-04 (the pulled face is not box A's) |
| 1c | `uv run python $P rolltest --who him` (agent-01, 2334f626+) | HeadRoll (or whichever curve the signs call roll) turns the head about its FORWARD axis, ~5° lateral elevation, forward elevation ~0 | roll pitches the head: `head.py` keeps ROLL_OK False (no rest tilt, no lean). Send agent-04 the table either way |

The signs file belongs to the face's SKELETON (Face_Archetype_Skeleton), which both presenters share: 1b overwrites
hers on box B (her v2 face is done by then; never re-run her face step after 1b without restoring `.her_r6`; perform.py's
face and sync refuse a signs file whose sha is not the blessed one for `--who`). Never reuse a signs
file after a face rebuild (r5b: its yaw_gain and yaw_table belong to the old face).

## 2. His performance (agent-01's chain)

```bash
uv run python $P all --who him        # push … cams … face … sync … gaze … place … bodycheck
```

What to check in what it keeps under `out/explainers/perf/him/`:
- `cams.json`: his directions from HIS seated eyes (he sits taller than her; not her numbers). Every on-screen
  re-aim over 10° (`face_args.json`: a lens shift at a cut time) goes to agent-07 first: move the camera, not his head.
- `face.json` `report.checks`: blink_nod 0.0, blink_locked < 0.15, blink_speed < 1.5, head_buzz < 0.06.
  `plan.blink_guard` ≤ 10. `report.blinks.per_min` 12-30.
- `face_args.json`: 3 glances at agent-11's think beats (18.5, 26.2, 42.1 s; the panel shots' toward the panel),
  `head.rest_roll_deg` 0 and `lean` 0 while ROLL_OK is False, `avoid_blinks` on every gaze move and the first 6
  frames of each cut.

## 3. The judge (read-only; numbers only)

```bash
uv run python $H sample $CUE --seq /Game/Explainer/SEQ_Explain_Him --label Host --out ../out/explainers/head/him
uv run python $H judge $CUE --head ../out/explainers/head/him/head.json --eyes ../out/explainers/head/him/eyes.json \
    --who him --gate ../films/host-studio/explainers/numbers/whatsapp/head.json
```

`sample` plays the sequence twice (qa.head_stability, then seq.sample of the head and both eyes with each shot's
camera): about 2 × 1359 frames × 2 ticks. Exit 0 = every line in QA.md "Head, eyes, blinks" passes. Send agent-04
the stdout. If a line fails:
- blink_nod / blink_locked: `r6/blink_why.py`'s method (the worst blink vs the plan and the events near it);
  usually a head move the planner cannot see (a tilt, a body move, a re-aim) under a blink: add it to avoid_blinks.
- frozen_s / drift too low: `HEAD_STYLE.micro_deg` up (0.4 → 0.5), not the gain.
- saccades_per_s low: the eyes are locked too hard by gaze (agent-01's gaze lock per span drops perf.face's
  fixational darts): gaze must keep the face's eye offsets on top of the lock.
- on_lens_share low: a camera direction in `cams.json` is wrong, or the lock is off on a span.

## 4. For the orchestrator's eye

agent-07 renders (private, `private/renders/r6/review/explain/him/`): the frames of each glance (away, held, back),
the two re-aims, and three blinks on screen, as one strip; and a 10 s preview across a glance and a cut.
