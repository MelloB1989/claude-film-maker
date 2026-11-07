# Round 7: her face acts (agent-04). Run sheet for box B's driver (agent-06)

The operator rejected v2b: "her expression is pale, no emotion at all". Our solves were mouth-only, and the face plan
added only random brow flashes. Now `head.py` (ACTING = True) takes `face_acting.plan`, which turns agent-11's acting
sheet (`acting/her.json`, lines[].face04 + base, v1.1 with the orchestrator's calibration) into perf.face events on
the exact words:
- brow flashes;
- curious one-brow looks (her right, the camera side);
- Duchenne smiles: corner pull + cheek raise + eye squint, the cheek and squint a beat after the mouth. The full
  Duchenne (>= 0.8) sits only on members / just starts / near / AWS / just plays; the others are soft 0.4-0.6 in the
  sheet's shapes (lopsided, sly, amused);
- a warm 0.2-0.4 base on every line;
- an open smile in a pause long enough for it;
- nods and a head shake ("doesn't");
- filler where the sheet leaves a gap over 0.7 s of speech.

Kept from round 6:
- an expression's mouth share is the corner pull and dimple only (x0.75 under a talking mouth), so jaw and lips stay
  the solve's;
- blink_head still, with no blinks on any tilt's ease;
- no expression touches eyeLook, so gaze and its lock are unchanged.

Tilts are agent-01's, on the body: `acting/tilts_her.json`, roll + = toward her right shoulder.

Offline (no box): `python3 face_acting.py check --who her [--lines N01-N03,N13]`. The gate's face rows on the
curves, absolute and relative to each channel's 20th percentile:

| | expr_active | smiles/min | brow flashes/min | neutral hold |
|---|---|---|---|---|
| test lines | 0.79 | 27 | 27 | 0.79 s |
| whole take | 0.88 / 0.74 rel | 27 | 22 | 0.79 s |

The lines are >= 0.6, >= 4, >= 6 and <= 1.5 s. perfkit's own report passes, blink rate 18/min.

All commands run from the kali driver tree with box B's profile (i-0d7684b44eacf7043). That tree has this branch
(`fleet/agent-04/r7-face`), agent-11's `fleet/agent-11/r7-acting` and agent-01's r7 body branch. Her level is open.

```bash
cd tools
P=../films/host-studio/explainers/perform.py
F=../films/host-studio/explainers/face_acting.py
H=../films/host-studio/explainers/head.py
```

## 1. Full-face solve vs mouth-only, line N01 (assets only; nothing placed)

`uv run python $F solvetest --who her --line N01`

This solves N01 twice in the sheet's solver mood (SURPRISE, 0.75), once FULL FACE and once MOUTH ONLY. It compares
both with round 6's mouth-only CONFIDENCE solve on:
- the upper-face families' peaks;
- the face rows over the line;
- the jaw RMS against round 6 (the lips must not change);
- lipsync.check of the full solve.

It writes `out/explainers/face/her/solvetest_N01.json`: paste that to agent-04. The test pass below stays mouth-only
until agent-04 reads it. The full solve's brows and cheeks would sit under perfkit's layer (added, clamped); its blinks
and eye looks are replaced.

## 2. The face pass (after agent-01's body step, which carries the tilts)

`uv run python $P all --who her --from face`

This runs face, check face, sync, gaze, check final, place, check placed and bodycheck.

Check in `out/explainers/perf/her/`:
- **face.json `report.checks`:** blink_nod 0.0, blink_locked < 0.15, head_buzz < 0.06; `plan.expressions` about 80
  events.
- **face_args.json:** `mouth_mix` 0.75, `brow_chance` 0.0. `expressions` include `smile` at about 3.2 s (members) and
  47.3 s (AWS).
- **check face / final / placed:** the lips. Every line's lag and onset must stay within round 6 v2's numbers (the
  same lines file). If a line gets worse, send agent-04 the line id: the fix is that line's smile, not the solve.

## 3. The numbers (read-only)

```bash
uv run python $F boxcheck --who her --lines N01-N03,N13      # the face rows on AS_exp_her_gaze, test span
uv run python $F boxcheck --who her                          # whole take
uv run python $H sample ../films/host-studio/explainers/cues/her.json --seq /Game/Explainer/SEQ_Explain_Her --label Presenter --out ../out/explainers/head/her
uv run python $H judge ../films/host-studio/explainers/cues/her.json --head ../out/explainers/head/her/head.json --eyes ../out/explainers/head/her/eyes.json --who her
```

Send agent-04 all four outputs. Every head/eye line must still pass (r6: blink_nod 0.048, on_lens 0.915).

## 4. Test frames (private: `private/renders/r7/review/face/her/`)

Finals spec, with the streaming warm-up. These are 1:1 face crops plus the full frame:

| what | camera | frame |
|---|---|---|
| curious one brow + tilt ("over") | CAM_MCU | f42 |
| Duchenne ("members") | CAM_MCU | f84 |
| Duchenne ("just starts") | CAM_MCU | f128 |
| the "But..." look | CAM_MCU | f147 |
| brow flash ("login") | CAM_WIDE | f1056 |
| Duchenne ("AWS") | CAM_WIDE | f1143 |
| a mid-line soft smile | CAM_MCU | f60 |

Also one v2b frame at f84 for side-by-side.

Then the TEST clip (CAM_MCU f0-196 + CAM_WIDE f1040-1162) with audio, for the orchestrator at 1x.
