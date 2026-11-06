# Round 5, T4 (agent-09): her hair keeps its length at the S17 -> S18 cut, and the review gate v2

NOT RUN YET. The orchestrator runs this in the ONE GPU session, in the order below. Core tools: `fleet/agent-09/r5-hair`
(merged to main through agent-10): `groom.lock`, `groom.lock_check`, `qa.hair_continuity`, `film-qa hair`,
`film-qa gate`. Why: `docs/unreal/research/hair-lod.md`.

## Why her hair was short at 01:00 (f1440, S18 wide)

- `r.HairStrands.LODMode` is 1 (Auto) by default. In Auto, even with LODSync's pin at LOD 0, a groom draws
  `RestCurveCount x clamp(screen size + 0.1)` of its curves (UE 5.8.4 `GroomManager.cpp ComputeActiveCurveCount`).
  - S18 is the widest framing of her, so she has the smallest screen size and the fewest curves.
  - The long, sparse ends vanish first, so the hair reads SHORT.
- Round 4's finals had no hair cvar: `r3/30-final.yaml` cvars were `{r.SSS.Quality, r.SSS.HalfRes}`.
  - My round-3 commit 951adf24 (`r.HairStrands.LODMode 0`) never reached film/host-studio.
  - It would also have been too late as a render cvar: the mode is read when a groom registers.
- Gate g PASSED: LODSync forced_lod 0 and no TRASH_. But it never read a groom, and it never read whether the
  Hair component is in LODSync's list.

## Round-5 probe result: the step at 01:00 is the hair SIMULATION restarting (06 Nov, agent-06's probes)

- P1: LODSync already reached her Hair in round 4 (listed, live_lod 0, STRANDS); only the two Auto-LOD cvars differ.
  Her Hair asset is DEFAULT, so it follows the cvar.
- P3 (the matte) read flat across f1440: reach 2.16 = the box bottom. At night, L*<40 joins her dark clothing to the
  hair, so the matte measured the box. `film-qa hair` now flags `hair.matte_saturated` and voids those numbers.
- The frame differences in her head box show the step (agent-06, round 4's final_d). MAD at 1439->1440 is 2.57,
  against 0.88 / 1.00 beside it and 0.87-1.14 elsewhere. The dark (hair) mass drops 2.4% at f1440 and STAYS.
- S18 is S17's end, locked off: same camera, same screen size, so LOD cannot step there. What changes at f1440 is
  the render JOB. Each shot was its own MRQ job (`chunking: shot`), and a new job means a new PIE world, which
  restarts the groom simulation (UE 5.8.4 `GroomComponent.cpp`: init, hidden->visible or a bone teleport; a camera
  cut alone does not reset it). S18's hair starts from a fresh sim, at an unchanged camera.
- Fix: render **S17 + S18 as ONE job**:
  `--set batch=S17S18 --set 'shots=["Reel_S17","Reel_S18"]' --set chunking=none`. The skeleton is continuous
  1439 -> 1440, so the sim carries over. Keep the hair lock: Auto LOD still thins her hair through S17's crane-out.
- Check: `film-qa hair` on the r5 frames, `gate.hair.cut_pop_ratio` <= 1.8 (round 4: 2.57, so the line fails
  round 4). Core: `fleet/agent-09/r5-hair-cutpop` (qa/hair.py `cut_pop`, gate item `hair.cut_pop_ratio`).

## Fix steps (on the box, after the level is open and the presenters are dressed, before ANY presenter render)

`G=/srv/ue/reel/r5/hair`, from `tools/` in the box tree:

1. `film-ue op groom.lock_check 'labels=["Host","Presenter"]' > $G/check_before.json` (read-only; the before).
   - **Expect:** `pass: false`, with problems including `cvar r.HairStrands.LODMode is 1.0 (want 0)` and
     `r.HairStrands.AutoLOD.Bias is 0.1 (want 1.0)`. Probe P1 reads the rest.
2. `film-ue op groom.lock 'labels=["Host","Presenter"]' persist=true > $G/lock.json`.
   - The same as `uv run python ../films/host-studio/reel/build.py --lod0 on`, which calls it now.
   - **Expect:** `pass: true`, and `render_cvars` = `{r.HairStrands.LODMode: 0, r.HairStrands.AutoLOD.Bias: 1.0,
     r.HairStrands.UseCardsInsteadOfStrands: 0}`.
   - If it refuses on TRASH_: run `level.save` -> `level.open` -> respawn/re-dress (r3/DRESS.md), then lock again.
   - A note `listed but LODSync has not resolved it yet` means groom.lock added Hair to the list. Then:
     `level.save`, `level.open`, `groom.lock_check` -> `live_lod: 0` for Hair.
3. `film-ue op level.save`.
4. `film-ue op qa.hair_continuity sequence=/Game/Reel/SEQ_Reel 'labels=["Presenter"]' 'shots=["Reel_S15","Reel_S16","Reel_S17","Reel_S18"]' out=$G/editor_after.json`
   - **Expect:** `pass: true` and `gate.hair.cut_reach_pct` < 12 (S17->S18 under ~5).
5. Render the presenter shots with `r3/30-final.yaml`. Its cvars now carry the three hair cvars. **S17 and S18
   go in ONE job** (`--set 'shots=["Reel_S17","Reel_S18"]' --set chunking=none`): see the probe result above.
   - Lock first (step 2) EVERY time the editor restarts or the presenters are respawned. `persist=true` writes
     the cvars to DefaultEngine.ini, but the LODSync list and pins are level state.
6. On the finals, read with the shot cameras' bone projections (no frame leaves the box):
   - `uv run python ../films/host-studio/reel/r5/hair_spec.py --who her --frames-dir /srv/ue/reel/r5/final --cuts S15,S16,S17,S18 --out $G/her_spec.json`
   - `uv run python -m filmtools.unreal.qa_local hair $G/her_spec.json --out $G/her_final.json`
   - **Expect:** `pass: true`, and `gate.hair.cut_reach_pct` < 12 at S17->S18 (f1440).
7. The gate (below) with `$G/her_final.json` and `$G/check_after.json` as the hair numbers.

## GPU probes (short; batch them)

| id | what | command | expected |
|---|---|---|---|
| P1 | the live LOD state as round 4 left it | step 1 | `lod_mode` of her Hair asset (DEFAULT expected; AUTO means the asset ignores the cvar, and the Bias covers it), `listed` for Hair (if false, round 4's pin never reached her hair at all), `geometry` at LOD 0 = STRANDS for every group |
| P2 | the Python name of the per-LOD array | step 1's `groups[].geometry` present | present, read via `lo_ds` (the tool also tries `lods`). If `groups` carries an `error`, run `film-ue exec -c "import unreal; print([n for n in dir(unreal.HairGroupsLOD) if 'lod' in n.lower()])"` |
| P3 | **round 4's S17->S18 frames FAIL** (proves the measure) | step 6 with `--frames-dir /srv/ue/reel/r3/final_d --cuts S17,S18`, then `film-qa hair` | `pass: false`, `hair.cut_jump` at f1440, reach drop > 12% (SHORTER). If it reads < 12%, the operator saw a thinning that the matte does not catch: print `cuts[0].area` (an area drop > 25% also fails) and lower `cut_reach` to just under the measured drop. Note it in the report |
| P4 | the editor reads like the render | step 4 with `groom.lock release=true` first (the before), then lock and run again | before: S17->S18 reach drop > 12%; after: < 12% |
| P5 | the cvar timing | after step 2, `film-ue exec -c "import unreal; print(unreal.SystemLibrary.get_console_variable_int_value('r.HairStrands.LODMode'))"` in the render's log (MRQ PIE) | 0. The Bias at 1.0 covers it either way |
| P6 | the cost | the render report's s/frame for S18, vs round 4's | strands at full count on a wide shot: expect a few % slower, not more |

## The review gate v2: run order (the last step before releasing the presenter finals)

Every item is a number. A missing number fails. A waiver needs a reason and a name, and it is refused on lips,
head, garment and hair (the operator complained about all four).

1. The hair numbers: `groom.lock_check` (`hair.lock` = its pass), `qa.hair_continuity` / `film-qa hair`
   (`hair.cut_reach_pct`, `hair.pop_reach_pct`), and the render spec's cvars (`hair.render_cvars`).
   - Write `$G/hair_gate.json`: `{"gate": {"hair.lock": <check.pass>, "hair.render_cvars": 1 if the spec's cvars
     include groom.lock's render_cvars, "hair.cut_reach_pct": ..., "hair.pop_reach_pct": ...}}`.
2. T1 lips (agent-01), T2 head (agent-04), T3a garment fit/clip (agent-02), T3b cloth (agent-08): each track's
   check writes its own `{"gate": {...}}` file (their plans give the commands).
3. `uv run python -m filmtools.unreal.qa_local gate --lines --spec ../films/host-studio/reel/r5/gate_spec.json`
   - **Expect:** `pass: true`. Every line fails its round-4 value.
4. `uv run python -m filmtools.unreal.qa_local gate $G/hair_gate.json <lips> <head> <garment> <cloth> --spec ../films/host-studio/reel/r5/gate_spec.json --out /srv/ue/reel/r5/gate.json`
   - **Expect:** `verdict: SIGN`, exit 0. On REFUSE, each failing item names its command and its round-4 value.

Round 4's numbers through v2: `tools/tests/data/gate_r4_numbers.json`, test `test_round4_numbers_refuse_and_name_each_blocker`.
- **REFUSE.** These fail: lips.lead_in_cm 0.33, lips.onset_lead_ms 600, lips.cues_fresh 0, garment.neck_px 3,
  garment.silhouette_pct 2.23, hair.lock 0, hair.render_cvars 0.
- head.blink_nod_deg, lips.track_r and the cloth item fail as "not measured".
- The three waivers round 4 used are refused.

## Risks

- The lock costs render time: all curves on wide shots (P6).
- `groom.lock` changes level state. A respawn, a re-dress or `groom.set` re-registering components undoes the
  LODSync list or the pins. Lock last, right before the render, and `groom.lock_check` is in the gate.
- The luma matte on rendered frames assumes dark hair over a lighter background inside her head-and-shoulders box.
  Dark set pieces inside that box would add area. P3 calibrates it on round 4's frames. The editor capture
  (groom-only depth) has no such issue.
- The hair simulation settles over the first frames of each shot. `preroll: cut` (32 warm-up frames) is in
  30-final; `qa.hair_continuity`'s pop check samples inside shots (`every=`) if a settle shows.
