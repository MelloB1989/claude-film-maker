# Round 5, T1: his lips (and hers), on one timebase, proved

Track T1 (agent-01). The research and the reasons for every limit are in core:
[docs/unreal/research/lipsync.md](../../../../docs/unreal/research/lipsync.md).

The tools are on core `fleet/agent-01/r5-lipsync`:

- `perfkit.lipsync`;
- the ops `lipsync.check`, `lipsync.compose` and `lipsync.mouth_boxes`;
- `speech.to_face process_mask=mouth head=false blinks=false` (it now also returns `timing`);
- `film-ue lips cues|curves|render|gate`.

The driver is [`lips.py`](lips.py) in this folder. **Nothing here has run yet.** The orchestrator runs it in the one
GPU session, after core is merged into film/host-studio and the box tree is updated.

## What went wrong (round 4)

- His mouth opened at f1000-1008, but L1's voice starts at f1020. That is ~17 frames (0.7 s) early.
- During his lines the mouth did not follow the words.
- The shipped mix itself is right. Measured here from `audio/mix/mix.wav`, the voice starts at:
  - f1021 for L1 (cue 1020);
  - f1097 for L2 (cue 1095);
  - f1160 for L3a (cue 1158).
- The solver is not early either. In the 5.8.4 plugin source, the audio processing range starts at frame 0 (Relative
  timecode alignment, the default) at 30 fps.
- So the lag entered somewhere between the solve and the placed section. Probe P1 finds which stage.
- The new pipeline does not depend on knowing the stage:
  - one mouth-only solve per line;
  - each placed at its measured WAV start;
  - every stage gated.

## Where it runs

- The kali driver tree (agent-06's), with `FILM_UE_CONF_DIR` and face_data=yes, as in round 4.
- Commands go from `tools/` there: `uv run python ../films/host-studio/reel/r5/lips.py …`.
- The box needs the editor up, the level open, and the presenters calibrated, as in ROUND4 (perf.py push and
  calibrate after any restore).

## Steps, in order, with the numbers to expect

### 0. Merge and update the box tree

- Core `fleet/agent-01/r5-lipsync` goes into main, and then into film/host-studio, together with this film branch.
- Install the bridge: `film-ue install`.
- `film-ue op ops.broken` must return `[]`, and `film-ue describe lipsync.check` must work.

### 1. Measured cues (local, no box, ~1 min)

```
uv pip install stable-ts            # optional: real word timings (CPU); without it words are estimated and flagged
uv run python ../films/host-studio/reel/r5/lips.py cues
```

- It reads `out/host-studio/reel/vo/vo_him.wav` and `vo_her.wav`, the stems the mix was made from.
- It writes `out/host-studio/reel/vo/cues.json` with `measured: true` and the stems' sha256.

Expect:

- `voice_frame` within ±2 frames of the plan: L1 ≈ 1020, L2 ≈ 1095, L3a ≈ 1158, L3b ≈ 1215, L4a ≈ 1350, L4b ≈ 1400
  (the `voice_frame_planned` column).
- No `silent` issue.
- `words_source: whisper` if stable-ts is installed.
- If a `moved` warning appears, the measured frame is the truth.

Then:

- **Captions** (agent-06's cut) read this file. Rebuild them from it, never from round 3's copy.
- `film-ue lips gate` will give `lips.cues_fresh` = 1.

### 2. Push (box)

```
uv run python ../films/host-studio/reel/r5/lips.py push
```

This puts vo_him.wav, vo_her.wav, cues.json and L1…L4b.wav into `<project>/Saved/Import/reel/`.

### 3. P1 — the probe: where round 4's lag entered (read-only, ~3 min per presenter)

```
uv run python ../films/host-studio/reel/r5/lips.py probe --who him > /tmp/p1_him.json
uv run python ../films/host-studio/reel/r5/lips.py probe --who her > /tmp/p1_her.json
```

It runs `lipsync.check` against the same stem on each stage in turn:

- the round-4 line solves (`0_line_*`);
- the base solve (1);
- the composed solve (2);
- the naturalised face (3);
- the follow bake (4);
- the final gaze face (5);
- what SEQ_Reel plays (6).

Expect:

- Stage 0 and stage 1 in sync (|lag| ≤ 1).
- The first stage where L1's `lag_frames` is ≈ -17 is the bug.
- Stage 6 at about -17 on L1, with `silence` issues near f975-1015.
- Send the stage-6 values to agent-09 (lag, `track_r` = min corr, onset lead, silence open/busy). They are round 4's
  column in gate v2.
- If stage 6 is fine but the render was early, the render or the mux moved the audio. Then P3 decides.

### 4. Solve each line alone, mouth only (~1-2 min per line, 6 lines)

```
uv run python ../films/host-studio/reel/r5/lips.py solve
```

- This is `speech.to_face process_mask=mouth head=false blinks=false fallback=false`, in each line's mood (vo.MOODS),
  writing `/Game/Speech/Anim/AS_reel5_<line>`.
- Expect per line: `timing.ok: true` (anim length = WAV length ±2 frames at 30 fps), `options.process_mask:
  MOUTH_ONLY`, `options.head_movement_mode: DISABLED`, and `missing` empty.
- If `missing` lists `audio_driven_animation_output_controls`, the solve was full-face. Compose still takes only the
  speech curves, so go on, but tell the orchestrator.

### 5. P2 — the solver's own lag (read-only, ~1 min)

```
uv run python ../films/host-studio/reel/r5/lips.py bias
```

- Expect each line's `lag_frames` within ±1, `corr` ≥ 0.5, and `mean_lag_s` within ±0.04.
- This is the calibration of the curve gate on this solver and rig:
  - Note the real `corr` values. If good lines read under 0.5, tell agent-09 before the `track_r` line is final.
  - If `mean_lag_s` is outside ±0.04, pass it as `expected_lag_s` to the later checks and say so in the report.

### 6. Compose each face from its lines (~1 min each)

```
uv run python ../films/host-studio/reel/r5/lips.py compose --who him
uv run python ../films/host-studio/reel/r5/lips.py compose --who her
uv run python ../films/host-studio/reel/r5/lips.py check --who him --stage solve      # exit 0
uv run python ../films/host-studio/reel/r5/lips.py check --who her --stage solve      # exit 0
```

`AS_reel_<who>_solve` is rebuilt from round 4's base, with every speech curve replaced:

- each line's mouth at its `file_frame`;
- rest between lines.

This is the asset perf.py's `naturalize` reads.

Expect `pass: true`, `diagnosis: in sync`, and per line |lag| ≤ 1, corr ≥ 0.5, onset lead ≤ 0.25 s, silence
`worst_open` < 0.05.

### 7. The rest of the face, as in round 4, then check each stage

```
uv run python ../films/host-studio/reel/perf.py naturalize --who him     # (and her; T2's blink/head changes land here)
uv run python ../films/host-studio/reel/r5/lips.py check --who him --stage face           # exit 0
uv run python ../films/host-studio/reel/perf.py sync --who him
uv run python ../films/host-studio/reel/perf.py gaze --who him
uv run python ../films/host-studio/reel/r5/lips.py check --who him --stage final          # exit 0
```

Repeat for her.

- **SPEECH_GAIN:** perf.py's `{"him": 1.7}` clamps his jaw. Try 1.3 first (change `SPEECH_GAIN` in perf.py), check
  `corr`, and keep the lowest gain that gives agent-09's lip-gap ≥ 2.0 by eye.
- A `face` stage that fails where `solve` passed means a perfkit layer moved the mouth (T2's area). Send the check
  JSON to agent-04.

### 8. Place and check what the sequence plays

```
uv run python ../films/host-studio/reel/perf.py place --seq /Game/Reel/SEQ_Reel
uv run python ../films/host-studio/reel/r5/lips.py check --who him --stage placed    # exit 0
uv run python ../films/host-studio/reel/r5/lips.py check --who her --stage placed    # exit 0
```

- Expect `sections` to show one Face section at START (960 him, 1080 her), `offset_s` 0, rate 1.0.
- `audio` lists the sequence's audio sections. If the reel's sequence carries the voice, its start must be frame 0
  with offset 0.
- Then `pass: true`. These two JSONs (`out/host-studio/reel/perf/lips_check_<who>_placed.json`) are the gate's
  `--curve` inputs.

### 9. Mouth boxes, then render the presenter shots

```
uv run python ../films/host-studio/reel/r5/lips.py boxes --who him
uv run python ../films/host-studio/reel/r5/lips.py boxes --who her
```

The orchestrator's render batch (S13, S15, S16, S17, S18) follows. No change from round 4 there.

### 10. P3 — the render gate, after the cut is muxed (on the box or kali, CPU)

```
film-ue lips render --video karma-reel-1080p-clean-h264.mp4 --wav out/host-studio/reel/vo/vo_him.wav \
    --cues out/host-studio/reel/vo/cues.json --who him --boxes out/host-studio/reel/perf/mouth_boxes_him.json \
    > render_him.json                               # exit 0; 2 = inconclusive (fix the box), 1 = fail
# the same for her
```

- Expect per line `verdict: pass`, |`lag_frames`| ≤ 1, `sensitive: true` (the 6-frame control moved the lag by 6).
- **Optional SyncNet second opinion:**
  - Setup:
    - `git clone https://github.com/joonson/syncnet_python` on the box;
    - `sh download_model.sh`;
    - `pip install -r requirements.txt` (torch CPU is fine).
  - Then add `--syncnet-dir <it>`.
  - Calibrate it once: a line's `conf` on the in-sync render, and the same with the audio shifted 12 frames. The
    offset must move by about 12.
  - Set `--min-conf` between the two.
- Round 4's cut as a control: `render` on round 4's 65 s clean H.264 must FAIL L1 (about -17 frames). If it does not,
  the render gate cannot be trusted. Report that instead.

### 11. Gate numbers for agent-09

```
film-ue lips gate --curve him=out/host-studio/reel/perf/lips_check_him_placed.json \
    --curve her=out/host-studio/reel/perf/lips_check_her_placed.json \
    --render him=render_him.json --render her=render_her.json \
    --cues out/host-studio/reel/vo/cues.json --stem him=out/host-studio/reel/vo/vo_him.wav \
    --stem her=out/host-studio/reel/vo/vo_her.wav --out lips_gate.json
film-qa gate ... lips_gate.json                        # agent-09's gate v2 merges it
```

| item | line | round 4 (to fill from P1/P3) |
|---|---|---|
| lips.lag_frames | ≤ 1 | ~17 (L1) |
| lips.track_r | ≥ 0.35 | P1 stage 6 |
| lips.onset_lead_ms | ≤ 250 | ~600-800 |
| lips.silence_open | ≤ 0.10 | P1 stage 6 |
| lips.silence_busy | ≤ 0.25 | P1 stage 6 |
| lips.render_lag_frames | ≤ 1 | P3 on the r4 cut |
| lips.render_conclusive | == 1 | — |
| lips.cues_fresh | == 1 | 0 (words_lost) |

## GPU probes (for the orchestrator's batch)

- **P1** (step 3): where the round-4 lag entered. Read-only, ~6 min.
  - Expected: stages 0-1 in sync, a later stage at -17 on L1.
- **P2** (step 5): the solver's own lag and correlation per line.
  - Expected: |lag| ≤ 1, corr ≥ 0.5.
- **P3** (step 10): the render gate on round 4's cut.
  - Expected: FAIL L1 at about -17 with `sensitive: true`. Then the new cut must pass.
- **P4** (in step 4): does 5.8.4's performance accept `audio_driven_animation_output_controls=MOUTH_ONLY` and
  `head_movement_mode=DISABLED` by script?
  - Expected: yes. Both are UPROPERTYs in `MetaHumanPerformance.h` (lines 376 and 247).

## Risks

- **`lipsync.mouth_boxes`** reads the cut's camera at each frame through `cut_camera` and `cam.read`. It is not run
  on the engine yet. If its boxes look wrong, pass `--box x0,y0,x1,y1` per shot instead: the presenter shots are
  near-static.
- **The curve gate's correlation line (0.35)** is set from synthetic tests and the literature. P2 gives the real
  values; agree the line with agent-09 before signing.
- **Per-line solves lose the whole-stem solve's breaths between lines.** `--keep-base 0.2` keeps a fifth of the base's
  mouth there for breaths. It must still pass the silence check.
- **SyncNet on a CG face** is a second opinion only, calibrated per avatar. The crop gate with its control is the
  primary check.
- **T2 (agent-04)** edits perf.face's head and blink layers but has agreed not to touch the speech curves. A `face`
  stage failure after their merge goes to them.
