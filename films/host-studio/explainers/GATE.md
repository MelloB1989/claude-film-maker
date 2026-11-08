# Explainer gate log (round 6, agent-09)

The spec is `gate_spec.json` and the method is `QA.md`. Every verdict goes here when it is run. The rulings below are
the orchestrator's (cc-64d05f6e), 07 Nov 2026. Each is a scope change or a measure fix, never a waiver.

## Rulings

| ruling | what it changes |
|---|---|
| captions | Every VO line is captioned, over the graphics too, in one band at the bottom 15%. The graphics keep that band clear (`gfx.caption_band_clear`). |
| facts | W06 ("two million") is kept and sourced (WhatsApp's 2012 engineering blog). W17 is softened to "over a hundred billion" (agent-11). |
| INFO for the explainers | `garment.silhouette_pct` and `shot.render_matches_r4`: there is no seated or round-4 reference for these films. |
| cloth NOT ATTEMPTED | His tee is Epic's default garment and her top stays skinned. |
| lips | `lips.render_lag_frames` and `render_conclusive` are INFO: the render measure is invalid. `lips.eye_onsets` is the orchestrator's signed strip. `lead_in_cm` uses the silence-proper window (agent-01, the approved 2.5 f anticipation); the short-gap lines are covered by the silence rows and `eye_onsets`. |
| netflix occlusions | clip_r7 was the overshirt run. V2 (no overshirt) uses `r6b_v2_clip` as its baseline: the forearm and hands sit in front of the top, so they count as occlusions, and later runs are judged against it + 0.01. |
| leaders | `garment.leaders_ok` is a hard pre-render row on every final job (the r6n0 lesson). |
| streaming | `shot.streaming_settled`: warm-up in the render spec and a clean first frame. This came from the CU f1300 tile blocks. |
| grain, close shots | `shot.grain_sigma` ≤ 1.0 (Immerkaer sigma on wall + neck, by projection). f300 (3.10) and MCU_1330 (14.55) fail it; the finals-spec MCU test f29 (0.69) passes. |
| grain, WIDE | `shot.grain_wide_sigma` ≤ 0.8 on flat patches only (wall + a second plaster patch). f300's wall (1.002) fails it; netflix V2 shot 11 (0.55) passes. The WIDE neck and desk patches are INFO (texture at that scale). Evidence: the orchestrator's 1:1 look at shot 11 f1100. |
| his move to box B | `garment.head_state_parity`: agent-06's `him_state` manifest (sha256), and cull_live reading 912 culled verts at z 144.2-153.3, as on box A. |

## Her neckline strip (netflix V2)

The orchestrator ruled on 07 Nov, about 23:10 IST.

- **The defect:** a dark grey strip, about 10 px wide, ran down the inside of her scoop neckline on her left (test30
  MCU f29, x about 1040-1075, y about 600-830 at 1080p). It read as a strap.
- **The cause:** the rim key light's shadow from her own Top onto her skin at the edge (agent-02's diagnosis, key-shadow
  ON/OFF). It was not the texture and not the geometry. Edge1N did not help, so no asset change ships; her original Top
  asset is restored.
- **The fix:** `Top.cast_shadow` OFF, set through setplan + set.py so it is reproducible. Recorded in r5/garment.md:
  rim key-shadow, so turn Top.cast_shadow off for tight tops.
- **The strip measure:** 0.884 with p10 188 after the fix, against 0.717 with p10 77 as rendered.
- **The evidence:** the orchestrator compared it against test30 at 1:1. The band becomes a soft light-grey inner edge
  that reads as real fabric. The rest of the torso is identical: knit, under-bust shading, sleeve hems, chair.
- **WIDE shot 11:** stays as rendered, because the band cannot be seen at WIDE scale. If it is ever re-rendered, check
  her shadow on the chair and desk.

**Gate owner (09 Nov):** agent-09 is rate-limited to Tue 11:30; agent-13 runs the gate on `fleet/agent-13/r7-gate`
(off agent-09's 178a28bf). agent-08's hand rows join it: finger_claw, dip_pip_ratio_bad, fold_at_limit, cascade_broken,
thumb_flat, thumb_stiff (guard), hold_over_collar; hold_chest and claw_score are report rows.

**His arms (the orchestrator, 09 Nov):** body.upperarm_side_clear_cm >= 0.5 and body.upperarm_bust_clear_cm >= 3 GATE
him too (they were never INFO in the spec; this records the ruling): his upper arm 6.6-7.9 cm inside his outfit's flank
is the fault the operator rejected on her. Seated and in gestures, against his outfit's SURFACE (agent-02 confirms it
is not an inner fold). agent-01 opens his rest/relaxed arms (elbows slightly out, forearms on the desk, no chicken
wings). His aba900fe + 7b03480f reads side -7.87 @f84 / bust 1.61 @f54: FAIL.

**His flank split (the orchestrator, 09 Nov):** the ~8 cm is split, not cut into one shell: agent-01 opens his
rest/relaxed abduction to ~20-25 deg (elbows a hand-width off the torso, forearms ON the desk; move.rest_abduction_deg
<= 25 is the guard against wings), and agent-05 slims the flank by the remainder (<= ~4 cm, blended, no dent from
CAM_MCU / WIDE / CU; an inner layer or fold first if LAYERS shows one). His FRONT zone is the same as hers: >= 3 cm at
every frame (gate).

**His blocked build (the orchestrator, 09 Nov):** (1) in his BODY build, body.arm_outfit / arm_torso are WARN (printed
with the numbers) until agent-05's flank refit lands, so the chain writes a body for agent-02/05 to measure and refit
against; the FINAL gate keeps body.upperarm_side_clear_cm >= 0.5 and body.upperarm_bust_clear_cm >= 3 HARD (progress
-7.9 -> -1.2 cm). (2) One owner per part at the rest: agent-08's contact solve owns the resting HAND (palm down, heel ~3
cm over the desk, fingers never below the top) and runs LAST; agent-01's rest arm IK targets that wrist pose (forearm on
the desk, the elbow not hanging); ONE combined sha for him and her. (3) His body.hands_in_frame_mcu_frac 0.447 (line
0.6) is fixed in the FRAMING: CAM_MCU / CAM_MCU_L slightly wider and lower in set_him.json (~6-10 %, the same headroom
ratio); the orchestrator checks the framing by eye on his TEST.

**The place-stage lift (agent-06's find, 09 Nov):** on her 928407cb PLACED dump the face 'place' stage lifted everything
from spine_04 up by ~2.6 cm (-0.55 x) with the pelvis fixed; the arms rode on it and her hands floated 2.6 cm above the
desk in the render. parity --shoulder passed (0.407) because it cancels a torso shift by design. Two rows close the hole:
qa.editor_torso_parity_cm <= 1.0 (spine_05 + clavicles, plain, rendered dump vs track) and
move.rest_contact_rendered_frames == 0 (rest contact on the rendered dump). The fix is agent-01's (agent-04's diagnosis):
perform.py sync's head_to_body bake, H2B_BONES['her'] = [spine_04, spine_05, neck_01, neck_02, head] on r7-body 66785bbe;
hers becomes [neck_01, neck_02, head], rotations only (his was already cut to neck/head, 9c6823c0, for a 3.6 cm lift).

**Cost rule (the orchestrator, 09 Nov):** NO box start for a sha whose OFFLINE `body --perform` build reports ANY issue,
for BOTH presenters (agent-01/08 run it). agent-13's offline naturalness rows on the sha's arm_track (whole take + the
verify windows) are part of the same pre-check: a movement/hand row that fails offline is fixed before a boot, not on
the box. 963942f4 cost a boot cycle on two issues known offline (her pinky_03_l into the desk at landings; his MCU
hands_in_frame 0.574).

**Her r7I verify (09 Nov, agent-06; 963942f4 + agent-08 02505b92, 0 offline build issues):** placed gates: parity
--shoulder 0.309, --torso 0.186 (the lift is gone: placed = seat), claw 0, palm_to_camera 0, rest_contact 0, spread 3.2:
PASS. finger_snap 9.0/min FAIL (rendered by the orchestrator's call). Offline (agent-13): wrist_radial_p95 19.7 in
the windows FAIL as well (the left wrist bends radially for the supination). Both open on agent-08's e1c07794 (snap
9.41 whole / 9.0 windows, radial 18.6 / 19.7).
NOT measured on r7I (cut for time): the rest gate, agent-02's arms (rest/gestures), breath, waist and
rest_contact_rendered as its own row. The finals sha runs chain_H2's full list (agent-06). upperarm_torso 0.4 is INFO
by ruling (A); bust 3.7 / side 0.5 PASS; hands_in_frame MCU 0.61 (netflix 0.5), CU 0.361, WIDE 1.0 PASS.

**Gate owner (09 Nov, later):** agent-13 is rate-limited to Tue 11:30; agent-04 runs the gate on
`fleet/agent-04/r7-gate` (off agent-13's 95374c60), with agent-13's tools as they stand (r7-movement ccc46755).

**Her watch DROPPED (the operator, 09 Nov):** "the left hand with watch looks very bad, watch is clipping through
hand, drop the watch" (r7I WIDE: the band and body cut into her wrist and hand as the wrist bends). agent-05 removes the
watch from her level of record in the set/garment setup code, not with a visibility key, so every future dress keeps it
off. agent-06 applies it at the start of the next T2 session, before her chain. The gate has no watch clearance row
to drop. The evidence is a still in the keys (WIDE f1080, 2x crop of the left wrist), and the orchestrator checks it by
eye. Him: unchanged; the orchestrator checks his wrist on his TEST, and the same rule applies if it clips.

**Her offline GO, 0fa53868 (agent-04, 09 Nov):** agent-08 d1869ce7 + agent-01's palm-off turn as an eased forearm
twist (zero-phase critically damped spring, 24 rad/s, + 55 ms). agent-04 re-ran it on kbuild (naturalness.py at
r7-movement HEAD; whole take / verify windows seq 0-196 + 1040-1162): 0 FAIL. finger_snap 0.0 / 0.0 (was 8.4 / 9.0),
wrist_radial_p95 2.7 / 3.0 (was 18.7 / 19.7), palm_to_camera 0, lag 49.6 / 53.0 ms; n/a by na_ok: humerus_elev_high /
rest, cascade. Build 0 issues (agent-01). The orchestrator: GO for T2. **Fallback (the orchestrator):**
move.lag_hand_ms keeps gating under HANDS_FALLBACK (it reads 24.95 there); agent-01 fixes it only if the fallback is
switched on.

**His NO-GO, 0fa53868 (agent-01's call, agent-04 agrees, 09 Nov):** his proxy body build (his plan on her skeleton) has
3 issues (hands_out_of_frame MCU 38 %, MCU_L 49 %, CU 0 %: the proxy cannot judge framing; on 963942f4 the box read
0.574 where the proxy read 0.255). The proxy rows fail on their own: finger_snap 9.6 (7.5 with the palm guard off: his
gated rest/swivel, not the palm turn), lag_hand 12.7, shape_wrong 4, hold_over_collar 28, palm_to_camera 8,
rest_abduction 25.05, rest_desk 42.6, humerus_elev_high 77.6. T stays stopped. **Tool fix:** r7/arm_track_who.py is
taken from agent-01's head (c62de4a1+). agent-13's copy built his performer without his gated torso, close_alive and
mic_cams, so the box rows would have scored a different motion from the anim the build writes. Hers is unaffected.

**Her r7J verify (09 Nov, T2, 0fa53868 + c62de4a1 tool-only, watch dropped; agent-06's numbers): GATE PASS, 0 FAIL**
(rest_hand_torso_cm 19.55, f198 left). Body build pass; bust 3.7 / side 0.5; agent-02 arms rest
3.72 / 1.28, gestures 3.97 / 1.32; hands_in_frame MCU 0.676, CU 0.392, WIDE 1.0; parity plain 0.364, --shoulder 0.247,
--torso 0.186; movement + hand rows (placed dump and track) 0 FAIL: finger_snap 0.0, claw 0, spread 2.85,
rest_contact 0, palm_to_camera 0; breath 2.22 mm at 15.1/min; waist fit 0.02, poke -0.26; lips lag 0.68 f, track
0.892, onset 77 ms; head gate rc 0. Next: the orchestrator's by-eye review of shots 1/2/11 and the left-wrist still.

**5ea6ab94 offline (agent-04, 09 Nov):** HIM: his proxy (5ea6ab94's arm_track_who.py on her read), whole / TEST spans
0-179 + 422-480: 0 FAIL (snap 0.0, lag 35.1, rest_abduction 18.4, rest_desk 32.6, collar 0, palm 0, shape_wrong 0,
spread 3.98; hold_chest 6 is a report row). The 3 build issues are framing only: the orchestrator's exception (only
the box judges framing; cam_sweep first on T). GO for T. HER: rows pass too (snap 0, radial 2.6, lag 46.3). Her finals
stay on the box-gated 0fa53868 unless the orchestrator moves them (that would need a T2 re-gate).
The orchestrator: her finals A stay on 0fa53868. Only an agent-08 polish candidate B, if it lands clean, may replace
A, and only after a T2 re-gate. START T for him.

**Her candidate B, ff93e054 (agent-08: 0fa53868 + 5ea6ab94 + a softer 'present' and a flatter rest), offline GO
(agent-04, 09 Nov):** whole / windows 0 FAIL: snap 0.0, radial 2.39 / 1.94, spread 2.69 / 2.78, palm 0, near_face 0,
claw 0, rest_contact 0, flexext 22.5 / 20.4, lag 37.7 / 44.1 (line 30). Build 0 issues (agent-08). Plan (the
orchestrator): A composites now; B is built and fully gated on T2, and its finals render to netflix_finals_B only on 0
FAIL; the orchestrator picks A or B by eye.

## Verdicts

### Netflix v2b: REJECTED BY THE OPERATOR (07 Nov, about 23:45 IST). The SIGN below is SUPERSEDED.

The operator's words: "nah, this ain't good at all ... her expression is pale, no emotion at all, viewer will not get
any curiosity ... why is her hands stuck to her body, looks very odd, also her right boob is cover the upper limb of her
right hand ... these presenters must look confident, happy, full of energy, not robotic. also look close to her waist ->
her skirt or whatever she is wearing below is not fit to her."

The technical gate passed, and it still failed. **This gate did not measure acting.** Round 7 adds the PERFORMANCE
rows (`gate_spec.json`):

- face.expr_active_frac, smile_events_per_min, brow_flash_per_min and neutral_hold_max_s;
- body.gesture_onsets_per_s, hands_above_desk_frac and upperarm_torso_clear_cm, with wrist_travel_cm_per_s as INFO;
- garment.waist_fit_cm.

Each row's must_fail is v2b, measured on box B. The numbers support the eye; the operator decides.

**Her R7 TEST (netflix_r7F_TEST), the orchestrator's verdict, 08 Nov:** a big step up. The face is alive, the CU
press-to-lens lands, the WIDE count gestures read and the arms are clear. The arm gate passes on the TEST state (min 5.30
cm; agent-02, `fleet/agent-02/r7-garment` 055b89b0). Two must-fixes before the finals, both judged by the orchestrator's
eye on CAM_MCU f0-100 (box C):

1. **The high rest pose.** Her hands hover at the top of her chest with drooping wrists, which reads as fidgeting. The
   rest becomes hands loosely together at the lower ribcage, 20-30 cm in front of the torso, with neutral wrists.
2. **The lower third covers the gesture zone** in the MCU opening. It moves top-left, or shortens.

**Rulings on agent-01's elbow geometry (the orchestrator, 08 Nov):**

- **(A) Arm clearance is split.** The upper arm must be >= 3 cm from the BUST / front of the Top (the operator's
  complaint). Against the SIDE of the torso it needs no penetration (>= 0.5 cm; light contact reads natural). The old
  whole-torso row becomes INFO.
- **(B) Stroke elevation.** The line is 60 deg ONLY for apexes at or above the upper chest, and 45 deg for the rest. A
  new row, upperarm_abduction_deg <= 35 at strokes, keeps the lift mostly FLEXION (forward), not abduction. High apexes
  are kept for the key beats (agent-11 lowers some if more than ~1/3 are high). The rest-elevation line stays 30 deg.
  agent-13 updates the rows.

**Her verify netflix_r7H (b4325b5b), the orchestrator's verdict, 08 Nov:** a big improvement. The WIDE counting reads
natural and the face is alive. Two gesture fixes come before the finals: the MCU f58-70 'MILLION' spread goes to head
height beside her face, and the CU 'Hit play' is a palm out beside her face. A NEW row (both presenters), hand_near_face
== 0: no hand above the chin or within ~10 cm of the face in the cut camera. agent-01 fixes it in one sha, and only
her 3 verify shots re-render.

**The operator on her verify (08 Nov):** the face is SHIPPABLE. The hands at the WIDE counts (~t44.5, N13) look
'zombie': a claw count hand held up at the shoulder with the forearm vertical, and a flat stiff desk hand. agent-08
leads a hand-perfection task (anatomical shapes, a by-eye shape catalogue, listing instead of counting, new detectors);
its rows join this gate. Her finals and his TEST are on HOLD until the new hand shapes pass.

**Breath in the seat (the orchestrator, 08 Nov):** for both presenters the breath (a vertical chest lift on
spine_05/clavicles, ~2-3.5 mm z at 10-20/min, coupled with speech pauses) moves into the BODY track (gesturekit). The
life layer keeps only a small clavicle + weight shift. The scored track then contains the breath, so the naturalness rows
and parity both see exactly what renders (agent-09's condition: the row run's track sha = the seat that renders). His 4
camera rigs come from box T (set_him.json) for his CU/MCU strokes. One sha carries the face rule + seat breath + his
rigs.

**Parity (the orchestrator, 08 Nov):** agent-13's shoulder-relative parity (r7/parity.py --shoulder) is THE parity
gate. It runs on the RENDERED dump (seat + life), with a 1.0 cm line, and supersedes the seat-only check and the 1.2
sanity row. The naturalness rows are scored on the 30 fps TRACK; the parity proves the editor plays it, and the editor-dump
rows are an INFO cross-check ('track + parity').

**The clock (08 Nov):** the sequence, editor and composite are 24 fps; agent-01's arm_track is 30 fps. Every row maps
frames by TIME (the orchestrator's rule). Matched frame-to-frame, the 'stale life layer' readings (44 / 47 cm) were a
clock artefact and are VOID (agent-13): time-matched, the editor agrees with the track to ~0.35 cm. agent-09's tools:
perf-rest and perf-parity paired frames by number (fixed e500c1d9). perf-face, perf-body, hands_in_frame,
limb/hand_torso, qa_av and the spans all read 24 fps sequence frames only.

**Cost policy (the operator via the orchestrator, 08 Nov):** at most two GPU boxes (T his, T2 hers). The finals
render ON those boxes, not on farm workers, so the farm rows are INFO, and leaders and streaming come from each box's
box.json per job. Every gate passes BEFORE a render: no re-renders, and the verify/test spans are kept to the minimum.

**Round 7 rulings (the orchestrator, 07 Nov):**

| ruling | what it changes |
|---|---|
| face rows | Gated on the face anim CURVES (face.curves_*), with brow line 0.40. v2b's real anim reads 0.22 / 0 / 0 / 3.0 s, so all four fail. The render smile row stays a gate (v2b 0.0/min). The render expr/brow/neutral rows are INFO: MediaPipe reads talking as expression on our face. |
| body rows | Calibrated on v2b's samples. A gesture is the hand going up off the desk (wrist > desk + 10 cm) plus beats while it is up. v2b reads 0.347/s with hands up 0.356; both fail. |
| waist | FROZEN. waist_fit_cm ≤ 0.75 (v2b 1.04 at her left side fails; the orchestrator's eye at 3x puts the defect there). waist_poke_cm ≤ 0.1 is a guard (agent-05's refit R7W +0.49, a visible belly poke, must fail). |
| arm clearance | INFO for the TEST: no validated measure yet. The judge is the orchestrator's eye at 1x/2x, with agent-01's design clearance (3.8 cm) as supporting evidence. It must be a real gate before the full re-render. |
| frown | face.curves_frown_frac is INFO: the full-face solve's angry-brow risk. |


### Netflix v2b: SIGN (07 Nov, about 23:45 IST)

- **Command:** `gate_film.py --film netflix numbers/netflix/*.json --out numbers/netflix/verdict.json`.
- **Result:** 55 PASS, 9 INFO (each by a ruling, reason in the row), 3 NOT ATTEMPTED (cloth), 0 FAIL, 0 WAIVED.
- **Sources:** box B (agent-07, `fleet/agent-07/r6-boxb`), head (agent-04 7266f001), cut v2b (agent-11), graphics band
  (agent-12, film/explain-netflix), the orchestrator's eye strip and eye_onsets.
- **Delivered:** the orchestrator delivered v2b to the operator at 23:29.

| area | result |
|---|---|
| lips | lag 0.77 f, track 0.897, onset 77 ms, silences, cues fresh; eye_onsets 6/6 lines 1.1-1.9 f lead |
| head | blink nod 0.048 / locked 0.103, buzz 0.031, drift 1.03, frozen 0.33 s, nods 8.8/min, blinks 19.3/min, on lens 0.915, saccades 1.41/s, glances 5.3/min |
| body | breath 14.1/min, 2.71 mm; desk, mic and knee contact 0 |
| garment | visible neck poke 0, wpo 0, armor 0.0, hem 0.955, excess over the V2 baseline 0, leaders 1 on every job |
| set | chair/desk 0 px, the mic never on the mouth (0), props overlap 0 (depth-confirmed) |
| shot | cameras 1, streaming 1, grain close 0.742 / WIDE 0.552 |
| exposure | static background patch, all 9 shots: jump 0.007, drift 0.023 |
| hair | lock 1, render cvars 1, cut reach 2.68 %, pop reach 0.0 % |
| cut v2b | -14.0 LUFS / -1.7 dBTP, 1920x1080, 59.46 s, captions 144/144 with onset 84 ms, facts sourced, qc 1, caption band 1 |
| eye | real_person, light, hair_garment and graphics all 1 |

**Scope notes:**

- **Exposure is read on a STATIC background patch (agent-09's change).** The face box measured her shading as she turns
  against the key (fixed box 0.17 / 0.27, tracked worse). Exposure is locked manual in the render spec.
- **The exposure value now covers all 9 shots.** The 3 CUs (02, 07, 14) are read on a static out-of-focus background
  region: 0.005 / 0.023, 0.005 / 0.016 and 0.005 / 0.011. The worst over every shot is jump 0.007, drift 0.023. The
  orchestrator accepted the scope.
- **Spec bug fixed before the run:** an override had dropped `set.props_overlap`'s line. A test now catches any spec
  item without a line.



- *(history)* **Netflix v2** (box B, agent-07): all 9 shots rendered, the guard OK on every job.
  - Cut rows: -14.0 LUFS / -1.7 dBTP, format 1, 59.46 s, captions 144/144 words, onset 84 ms, facts 1, qc 1.
  - The orchestrator's frame-wise watch: picture, lips (~1.7 f lead), hair at the cuts, neckline, grain and mix all
    PASS.
  - ONE fix, composite only (agent-11): the captions over her white top are too faint. The fix is a black backing
    plate at about 45 % alpha behind every caption, dimmed upcoming words at >= 70 % opacity, the same position and
    size, and the 56.08 s audio cut fixed. That makes v2b. The cut rows are re-run on v2b.
  - Still to come from box B: grain per job, clip vs r6b_v2_clip, exposure (tracked boxes), box.json.
- **WhatsApp:** not started. The head-state pull to box B comes first.
