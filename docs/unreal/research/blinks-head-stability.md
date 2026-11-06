# Blinks, head stability and natural face/body motion (round 5, T2)

The operator on round 4's cut, about her (the Presenter): **"every time she blinks her head nods a little down like
a jitter, looks very very odd"**. This page covers:

- why it happened;
- what blinks and heads really do;
- how studios keep a head stable under procedural layers;
- what we changed;
- how it is now checked automatically.

Tools are on core branch `fleet/agent-04/r5-blinks`: perfkit `stability.py`/`presets.py`, `perf.face`
`blink_head`/`solver_head`, `qa.head_stability`, `film-qa head`/`head-samples`/`head-gate`.

Sources are tagged by trust:
- **[Epic src]**: the 5.8.4 source tree on the source box, read for this page;
- **[Epic docs]**;
- **[Epic forum]**: forum threads, release notes;
- **[paper]**;
- **[report]**: vendor or user reports.

## 1. Root cause of our failure

Three sources put head pitch inside her blink windows. Each is locked to the blinks by construction, so the head
dipped on *most* blinks, which is what the operator saw:

1. **Gaze blinks rode the chin dip of their own turn.**
   - `blinks.plan` forces a blink onto most gaze shifts over 20° (65–100%), starting with the saccade. That part is
     right: Evinger et al. 1994 found blink activity with 97% of gaze shifts over 33°.
   - `gaze.GazePlan` dips the chin by `0.06 × |Δyaw|` (up to 4°) in the middle of every big horizontal head turn.
   - The blink and the dip land together.
   - Offline, perfkit alone on her round-4 plan, with no solver at all:
     - 3 of her 9 blinks dip **0.8–1.6°**;
     - −1.61° at master f1380 (the S17 glance);
     - −1.23° at f1397;
     - −0.83° at f1145.
2. **The speech solve's own head was kept** (`solver_head='soften'`: low-passed at 2 Hz, 60%).
   - The 5.6+ offline audio solve generates head motion [Epic docs: Audio Driven Animation].
   - In 5.8.4 the face, the blinks and the head come out of **one neural predictor run**.
     `FSpeech2FaceInternal::RunPredictor` binds three outputs: face controls, blink controls (`CTRL_L/R_eye_blink.ty`)
     and head controls (`HeadTranslationY/Z`, `HeadRoll/Pitch/Yaw` → `mha_head_ik_ctrl.{ty,tz,rx,ry,rz}`)
     [Epic src: MetaHumanSpeech2Face/Private/Speech2FaceInternal.cpp:151, Speech2FaceInternal.h:70-76,
     DataDefs.h:22-25,113-124].
   - A head learned together with the blinks moves with *the solve's* blinks, and phrase-final head drops are a
     prosodic norm (Ishi et al. 2007).
   - We replaced the solve's blinks with ours (`blink_mode='replace'`), but 60% of our blinks are drawn to phrase ends,
     the same places. The solve's dips stayed and our blinks sat on them.
   - The solve's `HeadTranslationX/Y/Z` were passed through untouched.
   - `HeadMovementMode` defaults to `TransformTrack` [Epic src: MetaHumanPerformance.h:247], so a solve carries head
     motion unless it is set to Disabled.
3. **Emphasis blinks on beat nods.**
   - 15% of stressed words draw a blink, and every stressed word gets a beat nod (2.2°, a 0.11 s drop).
   - The two coincide by design.

**Not the cause:**
- **The rig.** No blink or expression curve drives the head or neck. The neck RBF reads head rotation, and does not
  move it [Epic docs: neck RBF setup].
- **Physiology.** A real blink pulls the eyeball 1–5° down and nasally (Collewijn, van der Steen & Steinman 1985).
  The head does not move.

**Reproduced offline:** a synthetic solve whose head drops 1.5° on each of its own phrase-end blinks, under her plan
with round 4's settings.
- Round 4's settings fail `blink_nod`, `blink_locked` and `blink_speed`. The blink rate also comes out at **36/min,
  the same number the box gave in round 4**.
- Round 5's defaults pass every check.
- See `tools/tests/test_ue_head_stability.py::test_round4_recipe_nods_with_the_blinks`.

## 2. What natural blinks look like (the numbers perfkit uses)

| quantity | value | source |
|---|---|---|
| rate at rest | ~17/min | Bentivoglio et al. 1997 [paper] |
| rate in conversation | 10.5–32.5/min (95% CI), mean ~26 | Doughty 2001; Bentivoglio 1997 [paper] |
| rate reading / focused | 1.4–14.4/min | Doughty 2001 [paper] |
| intervals | log-normal, CV 0.5–0.8; a CV under 0.25 reads as a metronome | perfkit `blink_regularity` |
| close | 70–100 ms, fast with high acceleration | Evinger 1991; Trutoiu et al. 2011 [paper] |
| open | ~2× the close (150–250 ms), decelerating | Trutoiu et al. 2011 [paper] |
| total | ~250–400 ms | VanderWerf et al. 2003 [paper] |
| partial blinks | up to 50% in the data, but fully closed blinks read as more natural on CG | Trutoiu 2011 [paper] |
| left/right lag | one lid leads by ~5 ms | Kassem & Evinger 2006 [paper] |
| gaze-evoked | blink activity with 97% of gaze shifts over 33° and all head turns over 17°, starting ~39 ms before the head | Evinger et al. 1994 [paper] |
| the eye during a blink | 1–5° down and nasal, no Bell's roll in short blinks | Collewijn et al. 1985 [paper] |
| the head during a blink | **does not move**; no study reports a blink-locked nod | (none found) |

## 3. Keeping a head stable under procedural layers

How production does it:
- The head is **its own channel**. Facial curves never write head rotation. Body and face head motion meet in one
  place, such as Layered Blend Per Bone on `neck_01` [report], or the face rig's HeadControlSwitch.
- A solver's head is either **dropped** or **cleaned** before anything is layered over it:
  1. Spike removal: a Hampel filter, rolling median ± 3·1.4826·MAD.
  2. A zero-phase low-pass. 4th-order Butterworth at 6 Hz is the human-motion default; for a talking head use 2–4 Hz.
     Prosodic nods live at syllable-to-phrase rates.
  3. One Euro when online: Casiez, Roussel & Vogel 2012. Tune by setting β=0, lowering min-cutoff until a hold is
     calm, then raising β until fast moves stop lagging; d-cutoff 1 Hz.
- **Procedural life is additive and small.** Noise micro-motion, not loops: Perlin's Improv; Busso et al. 2007 add
  colored noise before interpolation.
- **UE knobs:**
  - `MetaHumanPerformance.HeadMovementMode` (Disabled / TransformTrack / ControlRig) [Epic src];
  - `bGenerateBlinks`, `bHeadStabilization` [Epic src];
  - export `bEnableControlRigHeadMovement` [Epic src: MetaHumanPerformanceExportUtils.h:254];
  - the face post-process AnimBP's "Enable Head Movement IK", which an Epic reply on the 5.8 thread says can be set
    false [Epic forum].

Our pipeline now does it this way (`perf.face`):

| knob | values | default (r5) | round 4 |
|---|---|---|---|
| `solver_head` | `replace` (the solve's head rotation **and translation** dropped), `clean` (Hampel → each blink window of the solve's and ours bridged → 1.5 Hz zero-phase → 50%), `soften` (2 Hz, 60%), `keep` | **replace** | soften |
| `blink_head` | `still` (no blink moves the head), `free` | **still** | (free) |
| `beat_every` | a beat nod on 1 in n stressed words; 0 = none | 1 (preset-dependent) | 1 |
| `preset` | `presenter_calm`, `presenter_lively`, `listener`, `still_portrait` | none | none |

`blink_head='still'` does three things:
1. It plans blinks *before* the head and drops the chin dip of any turn that carries a blink.
2. It keeps blinks off nod drops: `nod_span`, the blink planner's `avoid`.
3. A last pass (`stability.still_through_blinks`) bridges any pitch or roll departure over 0.15° inside a blink
   window. The bridge is a cubic matching value and slope at both edges, so a turn or drift through the window goes
   on and a dip does not. The plan reports `blink_guard` (windows bridged).

Yaw is never bridged: a gaze turn with its blink is meant to happen.

## 4. Verify automatically

One measurement, three readers: `perfkit/stability.py`.

**Window.** Lid start −0.1 s to lid open +0.12 s. The pitch is detrended by the chord between the window edges, so a
smooth turn scores ~0.

| check | metric | line (FAIL when) | why this line |
|---|---|---|---|
| `blink_nod` | share of blinks whose detrended pitch departs ≥ 0.5° | > 20% | her r4 plan: 3/9 at 0.8–1.6° |
| `blink_locked` | blink-triggered average (−0.2…+0.5 s around onsets) peak | ≥ 0.3° **and** ≥ 2× the control average (onsets away from blinks) | catches a small nod on *every* blink that stays under 0.5° each |
| `blink_speed` | median peak pitch speed in blink windows / outside | ≥ 2.5× and ≥ 6°/s | a jerk without much depth |
| `head_buzz` | residual off a 0.2 s Savitzky–Golay cubic, any axis | RMS > 0.08° or any frame > 0.5° | follows a 32° turn in 0.39 s (perfkit's fastest) at 0; flags snapped keys and solver buzz |
| `head_turn_dip` (warn) | pitch departure in a blink window whose head yaws ≥ 20° | > 2° | the gaze-evoked blink on a big turn is right (Evinger 1994); the pitch along the turn is the turn path, judged on its own (r5 box: his off-screen return turn dipped 2.9°) |

What is judged:
- **Turns:** blinks on a turn of 20° or more are listed under `turns`, not scored as nods.
- **Edges:** blinks whose window runs off either end of the samples are listed under `edge`.
- **Off screen:** the gate judges only the frames where that presenter is on screen in the cut (the shot table's
  cast; `film-qa head-gate --seen` / `perf.py head`). Blinks elsewhere are listed under `unseen`. This is the
  orchestrator's ruling in r5: the check's correct scope, not a waiver.

Readers:
- **Curves:** `perf.face` / `anim.check` reports (`metrics.report`).
- **Bones:** `film-ue op qa.head_stability sequence=… label=… start=… end=… [blinks=@spans.json] out=…`. It plays the
  sequence and reads the head bone in the world plus the Face anim instance's eyeBlink curves. This is what renders,
  so it catches what the curve check cannot see: the body's neck, the face AnimBP's head IK, and anything Sequencer
  layers.
- **Render:** `film-qa head DIR --fps 24 [--box …]`. MediaPipe Face Landmarker (Tasks API, VIDEO mode, CPU) supplies
  the blendshape blinks. The pitch comes from **solvePnP on rigid landmarks only** (nose bridge and tip, canthi, the
  face's sides, forehead) against the shot's first frame.
  - MediaPipe's own transformation matrix is reported alongside. A landmark tracker's pitch is biased by lids and
    cheeks on a blink [report: tracker comparisons; a patent shows blink-locked pitch transients], and a nod that only
    the matrix sees is flagged `head.tracker_artifact`, not failed.
  - Render limits are looser for landmark noise: nod 0.8°, average 0.45°.
  - Use `uv run --with mediapipe==0.10.21`. The model is `face_landmarker.task` float16/1 from
    storage.googleapis.com/mediapipe-models.

**Gate v2** (agent-09). `film-qa head-gate gate_head.json head_her.json head_him.json` writes:
- `head.blink_nod_deg`: the worst blink's departure, line **0.6°**; her round 4 is ≥ 1.61°;
- `head.blink_locked_deg`: the triggered-average peak, line **0.3°**.

## 5. Body secondary motion for a presenter

| channel | natural | robotic | perfkit |
|---|---|---|---|
| breathing | 12–20/min at rest (StatPearls); calm presenter 12–16; breath-to-breath CV ~21% in period, ~33% in volume (Tobin et al. 1988); exhale longer than inhale | a fixed sine | `bodylife.Breaths`: per-cycle period CV 0.2 and depth CV 0.25, inhale 35–45%; round 4 was a fixed-rate wave |
| chest | quiet-breathing chest-wall displacement ~1–8 mm, ~0 at the sternoclavicular level (PMC8184162) | big heaves | spine extension 0.4–0.6° total, clavicles 0.6–1.0° |
| sway | quiet-standing CoP median ~0.33 Hz, 95% of AP power < 1.1 Hz (PMC4393163) | none, or a loop | 2-octave noise at 0.08 Hz |
| weight shift | every few seconds to ~15 s, 1–2 cm | synchronized with other channels | every 6–14 s, 1–1.5 cm, eased, pelvis tilt 0.7°/cm, spine counter-bends |
| head micro-motion | small, < 1 Hz | frozen, or a periodic loop | 1/f noise 0.2–0.5° by preset |
| phase | every channel its own | shared phase | separate seeds |

**Physics-driven secondary motion.** `RigidBody` AnimNode, Physics Control component (Experimental, spring/damper),
or Control Rig Physics in 5.6+, which can be baked [Epic docs, report]. It suits hair cards, loose cloth and
accessories. For a presenter's torso and head, keyed additive life is predictable and reviewable, and physics on the
spine adds risk without adding what reads (none found that a viewer notices).

**Presets** (`perfkit/presets.py`, `perf.face preset=`):

| preset | blinks | head micro | breath | beat nods | use |
|---|---|---|---|---|---|
| `presenter_calm` | talk ~23/min | 0.35° | calm 12/min | 1 in 2 | to the lens |
| `presenter_lively` | talk ~23/min | 0.5° | 15/min | every one | energetic host |
| `listener` | listen ~17/min | 0.3° | 13/min | none | the other face in a two-shot |
| `still_portrait` | calm ~12/min | 0.2° | 12/min | none | a held close-up |

## 6. Pitfalls

- **Replacing blinks and keeping the solver's head separates the two.** The solve's head stays tied to blinks that
  are no longer there. Drop the head (`replace`) or bridge the solve's own blink windows too (`clean` does both
  sets).
- **A landmark tracker sees a nod on every blink.** Judge pitch on rigid landmarks, and confirm in the editor with
  `qa.head_stability`, which reads bones.
- **On the reel's rigs the head curve names lie:** HeadYaw nods. perfkit works in the character's frame through
  `perf.calibrate`'s `HeadSigns`. The solve writes `HeadYaw = mha_head_ik_ctrl.rz` [Epic src], and on these rigs that
  is the nod axis, so the solve's "yaw" is a nod on screen.
- **A curve-level pass is not enough.** The round-4 gates passed curves that did not include the body's neck or the
  face AnimBP. Always run the bone check (`qa.head_stability`) on the master sequence.
- **Never fix a nod by low-passing harder.** A 2 Hz low-pass still passes a 0.45 s dip. Bridge the windows, or drop
  the channel.

## Links

- Audio Driven Animation (head movement, Generate Blinks, Process Mask, Realtime): https://dev.epicgames.com/documentation/en-us/metahuman/audio-driven-animation
- MetaHuman 5.6 release (offline audio "plausible head motion"): https://forums.unrealengine.com/t/metahuman-5-6-release/2539165
- MetaHuman 5.8 release notes: https://dev.epicgames.com/documentation/metahuman/metahuman-5-8-release-notes-in-unreal-engine?lang=en-US ; 5.8 forum thread (Enable Head Movement IK): https://forums.unrealengine.com/t/metahuman-5-8-released/2729288
- EPerformanceHeadMovementMode: https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/MetaHumanPerformance/EPerformanceHeadMovementMode
- MetaHumanPerformance Python (head_movement_mode, head_stabilization, generate_blinks): https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MetaHumanPerformance?application_version=5.7
- Head-IK control after baking [report]: https://forums.unrealengine.com/t/metahuman-head-control-not-working-after-baking-face-performance-to-control-rig/2611299 ; Head Movement IK problems [report]: https://forums.unrealengine.com/t/ue5-6-head-movement-ik-problems/2652719
- eyeBlinkL / eyeFaceScrunchL standards: https://dev.epicgames.com/documentation/metahuman/mh-standards-docs/eyeBlinkL , https://dev.epicgames.com/documentation/metahuman/mh-standards-docs/eyeFaceScrunchL
- Neck RBF drivers: https://dev.epicgames.com/documentation/metahuman/updating-neck-rbf-setup-tool-drivers-for-expression-editor
- Trutoiu et al. 2011, Modeling and animating eye blinks: https://la.disneyresearch.com/wp-content/uploads/Modeling-and-Animating-Eye-Blinks-Paper.pdf
- Bentivoglio et al. 1997: https://pubmed.ncbi.nlm.nih.gov/9399231/ ; Doughty 2001: https://scilit.net/publications/297a9d8bcac35c3019707d09a6d71789
- Kassem & Evinger 2006: https://pmc.ncbi.nlm.nih.gov/articles/PMC3327295
- Evinger et al. 1994, Not looking while leaping: https://researchconnect.stonybrook.edu/en/publications/not-looking-while-leaping-the-linkage-of-blinking-and-saccadic-ga/
- Collewijn et al. 1985: https://scilit.com/publications/9459805b6ac2b76ff8c5d1cb335d5492
- Ishi et al. 2007 (head motion and prosody): https://www.isca-archive.org/interspeech_2007/ishi07_interspeech.pdf
- One Euro filter: https://gery.casiez.net/1euro/
- Munhall et al. 2004: https://www.queensu.ca/psychology/sites/psycwww/files/uploaded_files/Faculty/Kevin%20Munhall/Munhall_Psyc_Sci.pdf ; Busso et al. 2007: https://graphics.cs.uh.edu/wp-content/uploads/papers/2007/T-ASL-Headmotion_0703.pdf
- MediaPipe Face Landmarker (Python): https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python
- Breathing variability (Tobin et al. 1988): https://pubmed.ncbi.nlm.nih.gov/3403474/ ; chest-wall displacement: https://pmc.ncbi.nlm.nih.gov/articles/PMC8184162 ; postural sway spectra: https://pmc.ncbi.nlm.nih.gov/articles/PMC4393163/
- Physics Control component: https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/PhysicsControl/UPhysicsControlComponent
- Perlin, Improv: https://mrl.cs.nyu.edu/projects/improv/
