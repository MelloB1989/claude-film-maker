# Round 5 plan, T2: her head nods with every blink (agent-04)

The operator on round 4's cut: "every time she blinks her head nods a little down like a jitter, looks very very
odd". The cause, the research and the numbers are in `docs/unreal/research/blinks-head-stability.md`.

**Cause, in short.** Every head dip below is tied to the blinks by construction:
- Gaze blinks rode the chin dip of their own turn. Offline, from perfkit alone on her r4 plan: −1.61° at f1380,
  −1.23° at f1397, −0.83° at f1145.
- The speech solve's head was kept at 60% (`solver_head=soften`). The 5.8.4 solve predicts the head in the same
  network run as its blinks.
- Emphasis blinks landed on beat nods.

**Fix.** `perf.face` now defaults to `solver_head=replace` and `blink_head=still`; this film's `naturalize` says so
explicitly. **Checks:** `qa.head_stability` (the head bone in Sequencer), `film-qa head` (render landmarks), and gate
v2's `head.blink_nod_deg` ≤ 0.6 and `head.blink_locked_deg` ≤ 0.3.

**Code:**
- core: `fleet/agent-04/r5-blinks` (into main through agent-10);
- film: `fleet/agent-04/r5-film-blinks`, which holds this file and `perf.py` (`naturalize` args, the new `head`
  command).

NOT run yet. The orchestrator runs one GPU session for all tracks.

## 0. Before the session

1. agent-10 merges `fleet/agent-04/r5-blinks` into main, main into film/host-studio, and this film branch into
   film/host-studio.
   - The box tree needs both. perf.py's `head` imports `filmtools.unreal.qa_head`, and the bridge needs `perfkit/stability.py`,
     `perfkit/presets.py` and the new `qa.head_stability` op.
2. Offline, on kali or pc2, check the merge:
   ```bash
   cd tools && uv run --with opencv-python-headless==4.10.0.84 pytest -q tests/test_ue_head_stability.py tests/test_ue_anim_perfkit.py
   ```
   Expect 26 + 61 passing (one skip in perfkit).
3. On the box after `film-ue install`: `film-ue op ops.broken` must be empty, and `film-ue describe qa.head_stability`
   must list the op.

## 1. Probes (round 4's state: run BEFORE re-naturalizing; read-only)

Use the restored round-4 project (`private/project/HostStudio`) with SEQ_Reel as placed in round 4. The calibration
lives in Saved/, so run `perf.py calibrate --who him,her` first; agent-01's T1 plan step does it too.

| # | command (from `tools/`) | expect | why |
|---|---|---|---|
| P1 | `film-ue op perf.check anim=/Game/Reel/Perf/AS_reel_her_face` | `report.failed` includes `blink_nod` and/or `blink_locked`; `report.head_stability.blinks`: dips of about −0.8 to −1.6 deg near t=2.7, 12.5 and 13.2 s (her gaze blinks) | r4's face at curve level fails the new checks |
| P2 | `film-ue op perf.check anim=/Game/Reel/Perf/AS_reel_her_solve` | the solve's head around **its own** blinks: `blink_locked` peak ≥ 0.3 deg, or `blink_nod` share > 0.2 | confirms cause 2 on her real solve (the solve's head dips with the solve's blinks). If it passes, cause 2 was minor and causes 1 and 3 explain it; the fix covers all three either way |
| P3 | `uv run python ../films/host-studio/reel/perf.py head --seq /Game/Reel/SEQ_Reel` | exit 1. `her.issues` includes `head.blink_nod` (or `head.blink_locked`). `gate.head.blink_nod_deg.value` ≥ 1.0 (offline ≥ 1.61, at Presenter around f1377-1389). `blink_source` is `curves` with about 10-14 blinks for her. Send agent-09 `head.blink_nod_deg` and `head.blink_locked_deg`: round 4's lines | r4's numbers for gate v2, and proof that the bone check sees what the operator saw |
| P4 | on the box: `uv run --with mediapipe==0.10.21 film-qa head /srv/ue/reel/r3/final_d/<S17 dir> --fps 24 --box 0.45,0,1,1 --out /srv/ue/reel/r5/qa/render_her_r4.json` (her side of the S17 two-shot; adjust the box to her half) | `head.blink_nod` fails, or at least `metrics.blink_locked` ≥ 0.45. If only `matrix_metrics` fails, the result says `head.tracker_artifact` | the render-level check sees it too. The frames stay on the box (face rule) |
| P5 | after P3: is `blink_source` `curves`? | yes. If it says `given`, the Face's anim instance exposed no eyeBlink curve and the planned spans were used | probes whether `AnimInstance.GetCurveValue` sees the Sequencer-played face curves (5.8.4: `UAnimInstance::GetCurveValue`, BlueprintPure, AnimInstance.h:1241) |

## 2. The fix (after T1's solves and calibration, in agent-01's loop order)

T1 (agent-01) owns the solve, calibrate, sync, turn and place steps. This track changes only `naturalize`'s face
arguments, which are already on this branch. Run in this order:

```bash
cd tools
uv run python ../films/host-studio/reel/perf.py naturalize --who her
uv run python ../films/host-studio/reel/perf.py naturalize --who him     # after hers: his blinks avoid hers
uv run python ../films/host-studio/reel/perf.py check --who him,her
```

Expect in each `naturalize` result:
- `report.checks`: `blink_nod` 0.0, `blink_locked` under 0.15, `blink_speed` under 1.5, `head_buzz` under 0.06 (all
  pass). Offline, her plan with a blink-nodding solve gives 0.0 / 0.10 / 0.11 / 0.044.
- `plan.solver_head` "replace", `plan.blink_head` "still", `plan.blink_guard` 0-10. That is how many blink windows
  the last pass smoothed; over 15 means something big is fighting it, so look at `plan.nods`.
- `report.blink_rate` 12-30/min. Round 4's was 36 with the gaze, phrase and emphasis pulls. Blinks now keep off nods,
  so her offline rate is 30.
- `clash_frames` [] (two-shot blinks apart, as in r4).

Then T1's loop continues as in round 4 (turn_head, sync, place). After `place`:

```bash
uv run python ../films/host-studio/reel/perf.py head --seq /Game/Reel/SEQ_Reel
```

Expect exit 0 with:
- `her.pass` and `him.pass` true;
- `gate.head.blink_nod_deg.value` ≤ 0.6 (expected ~0.1-0.35: body breathing and the bone path add a little);
- `gate.head.blink_locked_deg.value` ≤ 0.3 (expected < 0.15);
- `metrics.head_buzz` ≤ 0.08 for each.

The numbers file goes to `out/host-studio/reel/perf/qa/gate_head.json` for agent-09's `film-qa gate`.

If it FAILS:
- `where` names the presenter and frames. Look at `her.worst`.
- **A body nod there.** perf.py's body beats or the partner looks come through the body, not perfkit, so perfkit
  cannot keep blinks off them. Move the blink with `avoid_blinks` (add the span to `naturalize`'s args) or move the
  body beat.
- **head_buzz only.** That is the bone path (turn_head keys, or the body life additive). Run
  `film-ue op qa.head_stability ... out=...` on that range and re-judge offline with `film-qa head-samples`.

## 3. After the finals render (S13-S18)

On the box, for each two-shot and single of hers:

```bash
uv run --with mediapipe==0.10.21 film-qa head /srv/ue/reel/r5/final/<shot> --fps 24 --box <her half>
```

Expect `pass`, with `metrics.blink_nod` ≤ 0.2 and `blink_locked` < 0.45. A `head.tracker_artifact` info is fine.
Do the same for him on S13/S15/S17.

## Expected numbers (for the gate and the orchestrator)

| number | round 4 | round 5 expected | line |
|---|---|---|---|
| head.blink_nod_deg (bones, worst blink) | ≥ 1.61 (offline, perfkit alone; P3 measures the real one) | 0.1-0.35 | ≤ 0.6 |
| head.blink_locked_deg (bones, triggered average) | P3 (offline with a 1.5° solve nod: 0.31) | < 0.15 | ≤ 0.3 |
| perf.face blink_nod share | 0.33-0.42 | 0.0 | ≤ 0.2 |
| her blink rate /min | 36 | 25-30 | 8-35 |
| render blink_nod share (film-qa head) | P4 | ≤ 0.2 | ≤ 0.2 |

## Risks

- **The body's own nods are invisible to perfkit's blink planner** (the hand-off turns, `nod()` beats on the body).
  The gate will name them; the fix is one `avoid_blinks` span each.
- **The anim instance may not expose the Sequencer-played face curves (P5).** perf.py then falls back to the planned
  blinks (`OUT/blinks_<who>.json`), which are the same spans perfkit wrote.
- **The render check needs mediapipe on the box** (pip from PyPI; the model is fetched from storage.googleapis.com
  once). If the box has no internet path to it, skip §3. The bone check is the gate item.
- **Dropping the solve's head removes its speech-driven head motion.** perfkit's speech micro-motion
  (`speech_gain`), beat nods and breathing replace it, and round 4 already layered those. If a line now reads too
  still, the fix is `solver_head=clean` (its head kept at 50% with every blink window bridged), not `soften`.
