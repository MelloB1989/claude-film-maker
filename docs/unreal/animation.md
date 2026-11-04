# animation & performance (WP4)

Make a MetaHuman act by code: a face that reads as alive (organic head motion that follows the gaze, blinks with
human timing, asymmetric expressions with living envelopes, moods that blend line to line, micro-motion in every
hold) over the speech solver's lip-sync; a body that idles without visibly looping, gestures on the stressed word,
walks and turns; plus the animation library (search, describe, curves, additive, retargeting, Control Rig keys).
All the synthesis is `unreal/fmbridge/perfkit/` (pure Python, no engine: unit-tested and usable on the client);
`anim.*` and `perf.*` ops read the editor and write curves and Sequencer tracks.

The operator's note on the last reel was "head movements too robotic, expressions should be more natural". What
makes motion read robotic, and what perfkit does instead:

| robotic | perfkit |
|---|---|
| the head pans at constant speed between keys and stops dead | skewed min-jerk moves (accelerate harder than they brake), 4-9% overshoot and a settle (`curves.move`) |
| the head and eyes turn together, as one camera | the eyes jump first (saccade, 21 ms + 2.2 ms/deg), the head follows 20-60 ms later and takes only part of the shift (~15% under 5 deg, ~85% past 40 deg); the eyes counter-rotate while it catches up (VOR) (`gaze`) |
| a frozen head between moves | 1/f micro-motion (~0.45 deg), breathing pitch (~0.25 Hz), livelier while talking (`head.compose`) |
| sinusoidal yes-nods | a fast drop, a slower return that rebounds past level and settles; repeats shrink (`head.Nod`) |
| a head on a pivot | the chin dips in big turns, roll leans into the turn |
| metronome blinks, symmetric triangles | log-normal intervals (CV ~0.5), fast close / slow open, partial and double blinks, a blink with most gaze shifts > 20 deg, blinks at phrase ends (`blinks`) |
| staring eyes | fixational micro-saccades, face scanning between a listener's eyes and mouth, vergence (`eyes`) |
| expressions as switches, mirrored | attack / sustain-relax / release envelopes, one side leads and is stronger, slow drift while held; a Duchenne smile lifts the cheeks a beat after the mouth (`expressions`) |
| a smile that fights the lip-sync | the mouth region is quieted while the voice is loud (`mouth_mix`) |
| emphasis by hand | stressed syllables and pauses found in the WAV (`audio`): beat nods and brow flashes there |
| a listener frozen while the other talks | small backchannel nods every 2.5-5 s on listen lines (`face.backchannel`) |
| eyes locked on a person for a whole speech | brief thinking glances away (8-15 deg, 0.6-1.2 s) after pauses, never off a lens (`face.aversion`) |

`anim.check` / `perf.check` measure all of this (see Recipes) so Claude can tell without looking.

## Recipes

**Make a speech solve look alive (the one-call fix for "robotic").**
```bash
film-ue op speech.to_face wav=/home/ue/Audio/l1.wav name=l1 face_mesh=/Game/MetaHumans/Ada/Face/Ada_FaceMesh mood=CONFIDENCE
film-ue op perf.face anim=/Game/Speech/Anim/AS_l1 wav=/home/ue/Audio/l1.wav mood=warm 'gaze=[{"t":0,"yaw":0,"scan":"lens"},{"t":2.4,"yaw":28,"pitch":-4,"scan":"face","dist_cm":150}]'
film-ue op seq.anim path=/Game/Shots/S010 label=Ada component=Face 'sections=[{"anim":"/Game/Speech/Anim/AS_l1_perf","start":0}]'
```
Check: `perf.face` returns `report.pass` true (or only `expression_range` failing for a deliberately blank face),
and `plan.shifts` / `plan.blinks` show what it did. `film-ue op perf.check anim=/Game/Speech/Anim/AS_l1` on the
raw solve shows what was wrong before. Angles are in the CHARACTER's frame: yaw + = their left, pitch + = up.

**Look at a performance without rendering** (a PNG of head, eyes, blinks, upper face and mouth on one time axis).
```bash
film-ue op perf.plot anim=/Game/Speech/Anim/AS_l1_perf out=/tmp/l1_perf.png
```
Check (pull the PNG and look): head lines are eased S-curves with a small overshoot, not straight ramps; the eye
strip jumps at each gaze shift and then drifts back as the head catches up; blinks are irregular, some right after a
shift; brows rise on the stressed words. `perf.face ... plot=/tmp/x.png` writes the same for its result.
A sample: [img/perf_plot_sample.png](img/perf_plot_sample.png) (perfkit alone, 10 s, four gaze shifts, a warm mood).

**Long or flaky audio.** `speech.to_face` cuts recordings longer than `max_chunk_s` (40 s) in pauses, solves each
chunk (under `{folder}/Chunks`) and stitches one animation; each solve has a time budget (`timeout_s`, default
60 s + 20 x its length) and is cancelled past it. A failed solve raises `engine`/`timeout` with the reason and a
hint when `fallback=false`; by default that part becomes a loudness-driven lip flap and the result says
`"fallback": true` with `errors` (re-solve later; perf.face still adds head, eyes and blinks over it).
```bash
film-ue op speech.to_face wav=/home/ue/Audio/monologue.wav name=mono face_mesh=/Game/MetaHumans/Ada/Face/Ada_FaceMesh max_chunk_s=30
```
Check: `chunks`, `fallback` false, `errors` empty.

**Calibrate once per face skeleton** (makes the head/eye signs exact; until then perfkit guesses).
```bash
film-ue op perf.calibrate label=Ada            # the face must be Sequencer-driven (mh.drive_face); ~20 s
```
Check: `signs.measured` true, `eye_deg` values 15-45; saved to `Saved/fmbridge/perf/signs_<skeleton>.json` and used
by every later perf.face / perf.apply. It fails with a hint if the head curves do not move the head.

**A whole performance from a spec** (lines with timing, mood, gaze targets, gestures, expressions, nods; walks).
```bash
film-ue plan examples/unreal/performance/presenter_intro.yaml      # perf.solve per line, then perf.compose
film-ue apply examples/unreal/performance/presenter_intro.yaml     # converges; a second apply runs nothing
film-ue op perf.describe sequence=/Game/_Examples/Perf/Seq_PresenterIntro label=Presenter
```
Check: `converged: true`; `report` (in perf.compose's result) passes; `perf.describe` shows the face section on
`AS_<name>_face` with the spec's fingerprint and the body's idle/gesture/walk sections. WAVs must be on the box.

**Preview head motion with no engine.**
```bash
film-ue op perf.head_curves duration_s=6 'gaze=[{"t":1,"yaw":30},{"t":3.5,"yaw":-10,"pitch":-5}]' 'nods=[{"t":4.5,"kind":"nod"}]'
```
Check: `checks` all pass; `shifts` lists when the eyes and the head moved. On the client the same code runs from
`unreal/fmbridge/perfkit` (`sys.path.insert(0, "unreal/fmbridge"); from perfkit import face`).

**Find an animation.**
```bash
film-ue op anim.find query='walk forward loop' path=/MetaHumanCharacter
film-ue op anim.find query='happy face loop' kind=face skeleton=/Game/MetaHumans/Ada/Face/Ada_FaceMesh
film-ue op anim.describe anim=/MetaHumanCharacter/Optional/Animation/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Walk_Loop_F
```
Check: the first result's `kind/category/gait/phase/direction/emotion` match; `length_s` and `skeleton` are from
the asset registry. The MetaHuman template animations (56: idles, expression loops, facial poses, ROMs, UEFN walk
and run start/loop/stop in 4 directions) are listed in `perfkit/library.py` (`KNOWN`). There are no gesture clips
among them: retarget some (below) or author additive ones.

**Idle that does not loop visibly; gestures on the beat; walk; turn.**
```bash
film-ue op perf.idle sequence=/Game/Shots/S010 label=Ada 'clips=["/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"]'
film-ue op perf.gestures sequence=/Game/Shots/S010 label=Ada 'gestures=[{"anim":"/Game/Anim/AS_OpenPalms","at_s":2.1,"stroke_s":0.7}]'
film-ue op perf.walk_to sequence=/Game/Shots/S020 label=Ada 'to=[300,120,0]' walk_anim=/MetaHumanCharacter/Optional/Animation/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Walk_Loop_F clip_speed_cm_s=150 at_frame=24 end_facing=CAM_A
film-ue op perf.turn_to sequence=/Game/Shots/S020 label=Ada target=Guest at_frame=48
```
Check: `perf.walk_to` returns `slide` (the walk loop's play rate and the expected foot slide on the ramps) and
`frames`; walk_to and turn_to each REPLACE the actor's transform track: for several moves use a spec's `actions`.

**Retarget a clip onto a MetaHuman body** (IK Rigs and Retargeter made by code once, reused).
```bash
film-ue op anim.retarget 'anims=["/Game/Mixamo/Wave"]' source_mesh=/Game/Mixamo/Y_Bot target_mesh=/Game/MetaHumans/Ada/Body/m_med_nrw_body out_folder=/Game/Anim/Retargeted
```
`target_mesh` for a built MetaHuman comes from WP3's `mh.body_mesh` (docs/unreal/metahuman.md). Check: `results`
lists the new animations (suffix `_RTG`); `anim.describe` on one shows the target skeleton. Re-runs
overwrite the results of the same name. If the auto chains are wrong, make IK Rigs by hand and pass
`source_rig`/`target_rig`.

**Layer: an additive gesture over the idle.**
```bash
film-ue op anim.additive anim=/Game/Anim/AS_Shrug out=/Game/Anim/AS_Shrug_Add
film-ue op seq.anim path=/Game/Shots/S010 label=Ada component=Body replace=false 'sections=[{"anim":"/Game/Anim/AS_Shrug_Add","start":48}]'
```
Check: `anim.describe` shows `additive.type` local space. Sequencer blends additive sections on top of the full-body
ones (AnimSequencerInstanceProxy.cpp:176) when the body plays in Sequencer's own anim instance.

**Key a Control Rig** (batched: one engine call per control).
```bash
film-ue op anim.rig_controls sequence=/Game/Shots/S010 label=Ada component=Face
film-ue op anim.rig_keys sequence=/Game/Shots/S010 label=Ada component=Face 'keys={"CTRL_L_brow_raiseIn": [[0,0],[12,0.6],[30,0]]}'
```
Check: `keys` counts; a misspelt control is `not_found` with candidates.

**Write or read curves in bulk.**
```bash
film-ue op anim.read_curves anim=/Game/Speech/Anim/AS_l1 contains=Head
film-ue op anim.write_curves anim=/Game/Perf/AS_face mode=add 'curves={"CTRL_expressions_browRaiseInL": [[0,1,2],[0,0.3,0]]}'
film-ue op anim.new path=/Game/Perf/AS_blank skeleton=/Game/MetaHumans/Ada/Face/Ada_FaceMesh length_s=5
```

## Op reference

`film-ue describe anim` and `film-ue describe perf` list them with arguments; each docstring has an Example.

| op | what |
|---|---|
| `anim.find` | rank animations for plain words (+ skeleton, kind, length bounds) |
| `anim.describe` | length, frames, fps, skeleton, curves, bone tracks, additive, root motion, perf metadata |
| `anim.new` | an empty animation on a skeleton (converges) |
| `anim.read_curves` / `anim.write_curves` | float curves in bulk; write modes replace/add/max/mul, one bracket |
| `anim.curves` / `anim.curve` / `anim.set_curve` / `anim.scale_curves` | the older single-curve ops |
| `anim.check` | naturalness checks (pass/metric/threshold/why) |
| `anim.additive` | an additive copy (local or mesh space; base: first frame, ref pose, another anim) |
| `anim.retarget` | IK Rigs + IK Retargeter by code, then the batch retarget |
| `anim.rig_controls` / `anim.rig_keys` | Control Rig controls in a sequence; batched keys (float, rotator, transform) |
| `anim.gaze_lock` | eyes on the lens, solved from the eye bones' measured pose |
| `anim.bake_pose` / `anim.bake_follow` / `anim.head_to_body` | face and body as one skeleton |
| `speech.to_face` / `speech.moods` | MetaHuman Animator's audio solver |
| `perf.face` | make one face animation alive (head, eyes, blinks, brows, moods, expressions) |
| `perf.check` | = anim.check |
| `perf.plot` | the performance as a PNG of strips (head, eyes, blinks, upper face, mouth) |
| `perf.calibrate` | measure the rig's head/eye signs and gains (saved per skeleton) |
| `perf.analyze_audio` | duration, emphasis, pauses, phrase ends, envelope of a WAV |
| `perf.head_curves` | preview head motion (no engine) |
| `perf.vocab` | presets, moods (and solver moods), nod kinds, layers |
| `perf.state` / `perf.plan` / `perf.apply` / `perf.compose` / `perf.solve` / `perf.lock_eyes` / `perf.describe` | the PERFORMANCE spec |
| `perf.idle` / `perf.gestures` / `perf.walk_to` / `perf.turn_to` | body moves without a spec |

Vocabulary (`perf.vocab`): expression presets `smile` (Duchenne), `smile_soft`, `grin`, `smirk`, `brow_raise`,
`brow_flash`, `concern`, `sad`, `angry`, `surprise`, `fear`, `disgust`, `contempt`, `thinking`, `skeptical`,
`squint`, `lip_press`, `wince`, `pout`; moods `neutral calm warm happy joy confident excited sad concerned angry
surprised fearful thoughtful skeptical disgusted bored playful confused` (each also picks the speech solver's mood);
nods `nod beat up shake`; face layers `head eyes blinks expressions brows nods`.

## Spec kind: performance

Schema: `tools/filmtools/unreal/schemas/performance.schema.json`; planner: `perfkit/spec.py` (pure, also run by
`tools/filmtools/unreal/perf_kind.py`); examples: `examples/unreal/performance/`.

```yaml
kind: performance
version: 1
name: presenter_intro
sequence: /Game/_Examples/Perf/Seq_PresenterIntro
actor: Presenter
camera: CAM_A                                  # the target "camera"
targets: {guest: "Guest:Face:FACIAL_L_Eye", desk: [320, 140, 0]}
character: {lead: eyes, head: {gain: 1.1, rest_roll_deg: 1.5}, energy: 1.0}
library:
  idle: [/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle]
  walk: {anim: /MetaHumanCharacter/Optional/Animation/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Walk_Loop_F, speed_cm_s: 145}
  gestures: {open_palms: {anim: /Game/Anim/AS_OpenPalms, stroke_s: 0.7}}
face: {solver_head: soften, blink_mode: replace, mouth_mix: 0.5, camera_lock: false}
lines:
  - id: l1
    audio: /home/ue/Audio/presenter_intro_l1.wav      # solved with the line's mood; emphasis found in it
    mood: warm
    gaze: [{at_s: 0, target: camera}, {at_s: 1.8, target: guest, scan: face}]
    gestures: [{name: open_palms, at_s: 1.1}]         # the stroke lands just before the beat
    expressions: [{preset: smile, at_s: 2.6, duration_s: 1.4, intensity: 0.6, asym: 0.2}]
    nods: [{at_s: 3.0, kind: nod}]
  - {id: listen, duration_s: 2.0, listen: true, gaze: [{at_s: 0, target: guest, scan: face}]}
actions:
  - {at_s: 12.0, walk_to: desk, speed_cm_s: 120, end_facing: camera}
```

Timing on the words: any nod, expression or gesture may say `on_emphasis: 2` (the line's 2nd stressed word),
`strongest`, `first` or `last` instead of `at_s`; the stressed words come from the line's audio (or its `emphasis`
list). An expression put on a word starts 0.15 s before it, so it peaks on it. Listen lines get backchannel nods
(`face.backchannel`), and lines spoken to a person get brief thinking glances away after pauses (`face.aversion`).

How it composes: one continuous face animation (`AS_<name>_face`) on the face track: every line's lip-sync (its
speech solve, or `face_anim`) placed at its time and closed between lines, with perfkit's head, eyes, blinks,
moods and expressions over the whole timeline, so nothing jumps at a line boundary. The body gets idles split around
full-body gestures and walks; the actor's transform gets the walks and turns. Convergence: the face animation
carries the fingerprint of the spec and what it depends on (solve keys, positions); the speech solves carry the key
of their WAV, mood and intensity. Change a mood and only that line re-solves.

## Gotchas

- **YAML reads a bare `yes` / `no` as true / false.** Nod kinds are `nod`, `beat`, `up`, `shake` for that reason
  (`yes`/`no` are still accepted from JSON and Python).
- **Head curve signs are a property of the rig.** Until `perf.calibrate` has run for a face skeleton, perfkit
  assumes HeadYaw + turns to the character's left, HeadPitch + looks up, HeadRoll + tilts the top of the head left,
  eyeLook* at 1.0 = 35/35/25/30 deg (left/right/up/down). Calibrate before judging a still.
- **HeadControlSwitch** must be 1 for the face rig to turn the head from HeadYaw/Pitch/Roll; perf writes it.
  MetaHumanPerformanceExportUtils writes it 0 when head movement is off at export.
- **A face played by Sequencer needs ANIMATION_SINGLE_NODE** and then does not copy the body (unreal/README.md);
  bake face and body together with anim.head_to_body + anim.bake_follow after perf.face if the neck shows.
- **Sequencer averages overlapping full-body sections at equal weight.** A gesture over an idle is made by splitting
  the idle around it (perfkit.body does); only additive sections ride on top. Additive sections need the body in
  Sequencer's own anim instance (the AnimBP slot path does not apply them the same way).
- **perf.walk_to / perf.turn_to replace the transform track.** Use a spec's `actions` for several moves.
- **The walk loop is matched at cruise speed**: the feet slide on the 0.6 s ramp-up and 0.8 s ramp-down unless
  walk start/stop clips are sequenced (the MetaHuman UEFN set has them: `AS_MH_Neutral_Walk_Start_F_Rfoot`, ...).
- **anim.retarget overwrites** results of the same name (bOverwriteExistingFiles) and shows a progress window
  (FScopedSlowTask), not a modal dialog.
- **Curves are keyed linearly** (RCIM_LINEAR) at 30-60 Hz before reduction; perfkit's checks sample at frame rate,
  so dense linear keys are not mistaken for robotic straight lines.
- **Blink rate on short shots** (< 20 s) is judged by count (one per 8 s at least), not rate.
- **Control Rig tracks from Python need a Blueprint-based rig.** 5.8 makes new Control Rigs as independent assets
  (`RigVM.BlueprintIndependentAssets` true), which `load_blueprint_class` cannot turn into a class: `anim.rig_keys`
  with `rig_class` works for legacy ControlRigBlueprint assets (the MetaHuman boards); for others add the track once
  in the editor and key it by code.
- **perf.face copies** the source (`out`, default `<anim>_perf`) and re-makes it on each call; the source is never
  touched.

## Audio2Face-3D (design only, offline)

NVIDIA Audio2Face-3D (A2F-3D; NVIDIA published the SDK and models in 2025 — check the current licence and
packaging before building; inference on an NVIDIA GPU) can replace or complement
MetaHuman Animator's audio solver. Route, offline and unbuilt (nothing here runs it):

1. On the GPU box (an L4 works), run A2F-3D's offline inference (`audio2face-3d` SDK sample or the Maya/UE ACE
   plugin's headless path) on the line's WAV: it outputs per-frame ARKit-style blendshape weights (52) plus tongue
   and jaw, and optionally emotion weights.
2. Map ARKit blendshapes to MetaHuman curves with a table (`perfkit/a2f.py`, to be written): e.g. `jawOpen ->
   CTRL_expressions_jawOpen`, `mouthSmileLeft -> CTRL_expressions_mouthCornerPullL`, `eyeBlinkLeft ->
   CTRL_expressions_eyeBlinkL`, `browInnerUp -> browRaiseInL/R`, `mouthFunnel -> mouthFunnelUL/UR/DL/DR`, ...;
   MetaHuman content has shipped an ARKit-to-MetaHuman mapping pose asset for Live Link (named like
   `mh_arkit_mapping_pose`; not in the engine source, so find it on the box with `assets.list` / `anim.find`): read
   its pose weights once to build the table instead of guessing.
3. Write the curves with `anim.new` + `anim.write_curves` (one batch), then `perf.face` with `blink_mode=replace`,
   `solver_head=replace` (A2F has no head), and `layers` all: the same head/eyes/blinks/brows as for the solver.
4. As a spec option: `lines[].solver: a2f` making perf.plan emit `perf.solve_a2f` instead of `perf.solve`.
Trade-offs: A2F's lips are strong on fast speech and work for any voice with no Epic sign-in; MetaHuman's solver
drives the full rig (tongue, sticky lips) natively and needs no mapping. Keep MetaHuman's as default.

## API_NOTES

Every engine API the WP4 ops call, verified on the UE 5.8.4 source box. Python names are the snake_case of the
reflected names; an out-parameter comes back as the return value.

| Python | C++ | file:line | verified |
|---|---|---|---|
| `AnimationCurveIdentifier().set_curve_identifier(name, RCT_FLOAT)` (ref-self) | `UAnimationCurveIdentifierExtensions::SetCurveIdentifier` (GetCurveIdentifier is deprecated in 5.8) | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/CurveIdentifier.h:150-152 | yes |
| `ControlRig.get_hierarchy().get_controls()` | `URigHierarchy::GetControlKeys` (ScriptName GetControls) | Engine/Plugins/Animation/ControlRig/Source/ControlRig/Public/Rigs/RigHierarchy.h:1181 | yes |
| `MetaHumanPerformance.start_pipeline(True)` -> `StartPipelineErrorType` (NONE, NO_FRAMES, DISABLED) | `StartPipeline`, `EStartPipelineErrorType` | Engine/Plugins/MetaHuman/MetaHumanAnimator/Source/MetaHumanPerformance/Public/MetaHumanPerformance.h:486, :65 | yes |
| `MetaHumanPerformance.is_processing() / cancel_pipeline() / get_number_of_processed_frames()` | `IsProcessing` / `CancelPipeline` / `GetNumberOfProcessedFrames` | MetaHumanPerformance.h:492 / :489 / :563 | yes |
| `unreal.AnimationCurveIdentifierExtensions` (class) | `UAnimationCurveIdentifierExtensions` (UBlueprintFunctionLibrary) | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/CurveIdentifier.h:111 | yes |
| `unreal.RawCurveTrackTypes.RCT_FLOAT` | `ERawCurveTrackTypes::RCT_Float` (UENUM BlueprintType) | Engine/Source/Runtime/Engine/Public/Animation/AnimCurveTypes.h:1044 | yes |
| `unreal.RichCurveKey(time=, value=, interp_mode=)` | `FRichCurveKey` (USTRUCT BlueprintType) | Engine/Source/Runtime/Engine/Classes/Curves/RichCurve.h:79 | yes |
| `unreal.IKRetargeter` | `UIKRetargeter` (UCLASS BlueprintType) | Engine/Plugins/Animation/IKRig/Source/IKRig/Public/Retargeter/IKRetargeter.h:69 | yes |
| `unreal.IKRigDefinitionFactory.create_new_ik_rig_asset(path, name)` | `CreateNewIKRigAsset` (BlueprintCallable; DisplayName does not rename it) | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RigEditor/IKRigDefinitionFactory.h:43 | yes |
| `unreal.RetargetSourceOrTarget.SOURCE / TARGET` | `ERetargetSourceOrTarget` (UENUM) | Engine/Plugins/Animation/IKRig/Source/IKRig/Public/Retargeter/IKRetargetSettings.h:11 | yes |
| `unreal.AutoMapChainType.FUZZY` | `EAutoMapChainType::Fuzzy` (UENUM, exported through AutoMapChains) | Engine/Plugins/Animation/IKRig/Source/IKRig/Public/Retargeter/IKRetargetChainMapping.h:13 | yes |
| `unreal.DataInputType.AUDIO` | `EDataInputType::Audio` (UENUM BlueprintType) | Engine/Plugins/MetaHuman/MetaHumanAnimator/Source/MetaHumanPerformance/Public/MetaHumanPerformance.h:34 | yes |
| `unreal.MetaHumanPerformanceFactoryNew()` | `UMetaHumanPerformanceFactoryNew` (UCLASS, a UFactory) | Engine/Plugins/MetaHuman/MetaHumanAnimator/Source/MetaHumanPerformance/Private/MetaHumanPerformanceFactoryNew.h:13 | yes |
| `unreal.PerformanceExportRange.WHOLE_SEQUENCE` | `EPerformanceExportRange::WholeSequence` (UENUM) | Engine/Plugins/MetaHuman/MetaHumanAnimator/Source/MetaHumanPerformance/Public/MetaHumanPerformanceExportUtils.h:20 | yes |
| `unreal.AnimationLibrary.get_animation_curve_names` | `GetAnimationCurveNames` | Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h:89 | yes |
| `unreal.AnimationLibrary.get_float_keys` | `GetFloatKeys` | Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h:456 | yes |
| `unreal.AnimationLibrary.does_curve_exist` | `DoesCurveExist` | Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h:514 | yes |
| `unreal.AnimationLibrary.get_sequence_length` | `GetSequenceLength` | Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h:598 | yes |
| `unreal.AnimationLibrary.get_num_frames` | `GetNumFrames` | Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h:73 | yes |
| `unreal.AnimationLibrary.get_animation_track_names` | `GetAnimationTrackNames` | Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h:81 | yes |
| `unreal.AnimationLibrary.is_root_motion_enabled` | `IsRootMotionEnabled` | Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h:176 | yes |
| `unreal.AnimationLibrary.set_additive_animation_type` | `SetAdditiveAnimationType` | Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h:152 | yes |
| `unreal.AnimationLibrary.set_additive_base_pose_type` | `SetAdditiveBasePoseType` | Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h:160 | yes |
| `unreal.AnimationLibrary.get_bone_pose_for_frame` | `GetBonePoseForFrame` | Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h:562 | yes |
| `anim.controller.open_bracket` | `OpenBracket` | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataController.h:109 | yes |
| `anim.controller.close_bracket` | `CloseBracket` | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataController.h:117 | yes |
| `anim.controller.set_number_of_frames` | `SetNumberOfFrames` | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataController.h:127 | yes |
| `anim.controller.set_frame_rate` | `SetFrameRate` | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataController.h:176 | yes |
| `anim.controller.add_curve` | `AddCurve` | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataController.h:295 | yes |
| `anim.controller.set_curve_keys` | `SetCurveKeys` | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataController.h:480 | yes |
| `anim.controller.add_bone_curve` | `AddBoneCurve` | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataController.h:188 | yes |
| `anim.controller.set_bone_track_keys` | `SetBoneTrackKeys` | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataController.h:238 | yes |
| `anim.controller.remove_all_curves_of_type` | `RemoveAllCurvesOfType` | Engine/Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataController.h:328 | yes |
| `AnimSequence.additive_anim_type` | `AdditiveAnimType` | Engine/Source/Runtime/Engine/Classes/Animation/AnimSequence.h:285 | yes |
| `AnimSequence.ref_pose_type` | `RefPoseType` | Engine/Source/Runtime/Engine/Classes/Animation/AnimSequence.h:289 | yes |
| `AnimSequence.ref_frame_index` | `RefFrameIndex` | Engine/Source/Runtime/Engine/Classes/Animation/AnimSequence.h:293 | yes |
| `AnimSequence.ref_pose_seq` | `RefPoseSeq` | Engine/Source/Runtime/Engine/Classes/Animation/AnimSequence.h:297 | yes |
| `FACTORY` | `FACTORY` | Engine/Source/Editor/UnrealEd/Classes/Factories/AnimSequenceFactory.h:23 / Private/Factories/AnimSequenceFactory.cpp:69 | yes |
| `EditorAssetLibrary.set_metadata_tag` | `SetMetadataTag` | Engine/Plugins/Editor/EditorScriptingUtilities/Source/EditorScriptingUtilities/Public/EditorAssetLibrary.h:385 | yes |
| `EditorAssetLibrary.get_metadata_tag` | `GetMetadataTag` | Engine/Plugins/Editor/EditorScriptingUtilities/Source/EditorScriptingUtilities/Public/EditorAssetLibrary.h:376 | yes |
| `EditorAssetLibrary.load_blueprint_class` | `LoadBlueprintClass` | Engine/Plugins/Editor/EditorScriptingUtilities/Source/EditorScriptingUtilities/Public/EditorAssetLibrary.h:45 | yes |
| `EditorAssetLibrary.find_asset_data` | `FindAssetData` | Engine/Plugins/Editor/EditorScriptingUtilities/Source/EditorScriptingUtilities/Public/EditorAssetLibrary.h:62 | yes |
| `EditorAssetLibrary.duplicate_asset` | `DuplicateAsset` | Engine/Plugins/Editor/EditorScriptingUtilities/Source/EditorScriptingUtilities/Public/EditorAssetLibrary.h:175 | yes |
| `EditorAssetLibrary.list_assets` | `ListAssets` | Engine/Plugins/Editor/EditorScriptingUtilities/Source/EditorScriptingUtilities/Public/EditorAssetLibrary.h:328 | yes |
| `AssetRegistryHelpers / AssetData.get_tag_value` | `GetTagValue` | Engine/Source/Runtime/AssetRegistry/Public/AssetRegistry/AssetRegistryHelpers.h:124 | yes |
| `AssetRegistryHelpers / AssetData.get_asset_registry` | `GetAssetRegistry` | Engine/Source/Runtime/AssetRegistry/Public/AssetRegistry/AssetRegistryHelpers.h:66 | yes |
| `AssetRegistry.get_assets` | `GetAssets` | Engine/Source/Runtime/AssetRegistry/Public/AssetRegistry/IAssetRegistry.h:363 | yes |
| `ARFilter` | `ARFilter` | Engine/Source/Runtime/CoreUObject/Public/AssetRegistry/ARFilter.h:64 | yes |
| `IKRigDefinitionFactory.CreateNewIKRigAsset` | `CreateNewIKRigAsset` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RigEditor/IKRigDefinitionFactory.h:44 | yes |
| `IKRigController.GetController` | `GetController` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RigEditor/IKRigController.h:57 | yes |
| `IKRigController.SetSkeletalMesh` | `SetSkeletalMesh` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RigEditor/IKRigController.h:62 | yes |
| `IKRigController.ApplyAutoGeneratedRetargetDefinition` | `ApplyAutoGeneratedRetargetDefinition` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RigEditor/IKRigController.h:367 | yes |
| `IKRigController.ApplyAutoFBIK` | `ApplyAutoFBIK` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RigEditor/IKRigController.h:372 | yes |
| `IKRetargeterController.GetController` | `GetController` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargeterController.h:71 | yes |
| `IKRetargeterController.SetIKRig` | `SetIKRig` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargeterController.h:77 | yes |
| `IKRetargeterController.SetPreviewMesh` | `SetPreviewMesh` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargeterController.h:94 | yes |
| `IKRetargeterController.GetNumRetargetOps` | `GetNumRetargetOps` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargeterController.h:183 | yes |
| `IKRetargeterController.AddDefaultOps` | `AddDefaultOps` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargeterController.h:161 | yes |
| `IKRetargeterController.AssignIKRigToAllOps` | `AssignIKRigToAllOps` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargeterController.h:174 | yes |
| `IKRetargeterController.AutoMapChains` | `AutoMapChains` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargeterController.h:286 | yes |
| `IKRetargeterController.AutoAlignAllBones` | `AutoAlignAllBones` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargeterController.h:439 | yes |
| `RunBatchRetarget` | `RunBatchRetarget` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargetBatchOperation.h:194 | yes |
| `IKRetargetBatchOperationInputs` | `IKRetargetBatchOperationInputs` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargetBatchOperation.h:117 | yes |
| `IKRetargetFactory` | `IKRetargetFactory` | Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/RetargetEditor/IKRetargetFactory.h:15 | yes |
| `ERetargetSourceOrTarget` | `ERetargetSourceOrTarget` | Engine/Plugins/Animation/IKRig/Source/IKRig/Public/Retargeter/IKRetargetSettings.h:11 | yes |
| `EAutoMapChainType` | `EAutoMapChainType` | Engine/Plugins/Animation/IKRig/Source/IKRig/Public/Retargeter/IKRetargetChainMapping.h:13 | yes |
| `ControlRigSequencerLibrary.get_control_rigs` | `GetControlRigs` | Engine/Plugins/Animation/ControlRig/Source/ControlRigEditor/Public/ControlRigSequencerEditorLibrary.h:143 | yes |
| `ControlRigSequencerLibrary.find_or_create_control_rig_track` | `FindOrCreateControlRigTrack` | Engine/Plugins/Animation/ControlRig/Source/ControlRigEditor/Public/ControlRigSequencerEditorLibrary.h:154 | yes |
| `ControlRigSequencerLibrary.set_local_control_rig_floats` | `SetLocalControlRigFloats` | Engine/Plugins/Animation/ControlRig/Source/ControlRigEditor/Public/ControlRigSequencerEditorLibrary.h:650 | yes |
| `ControlRigSequencerLibrary.set_local_control_rig_rotators` | `SetLocalControlRigRotators` | Engine/Plugins/Animation/ControlRig/Source/ControlRigEditor/Public/ControlRigSequencerEditorLibrary.h:917 | yes |
| `ControlRigSequencerLibrary.set_local_control_rig_euler_transforms` | `SetLocalControlRigEulerTransforms` | Engine/Plugins/Animation/ControlRig/Source/ControlRigEditor/Public/ControlRigSequencerEditorLibrary.h:1024 | yes |
| `EulerTransform` | `EulerTransform` | Engine/Source/Runtime/AnimationCore/Public/EulerTransform.h:31 | yes |
| `SkelAnimParams` | `SkelAnimParams` | Engine/Source/Runtime/MovieSceneTracks/Public/Sections/MovieSceneSkeletalAnimationSection.h:20 | yes |
| `AdditiveInSequencer` | `AdditiveInSequencer` | Engine/Source/Runtime/AnimGraphRuntime/Private/AnimSequencerInstanceProxy.cpp:176 | yes |
| `GetSkeletalMeshAsset` | `GetSkeletalMeshAsset` | Engine/Source/Runtime/Engine/Classes/Components/SkeletalMeshComponent.h:375 | yes |
| `SkeletalMesh.Skeleton` | `Skeleton` | Engine/Source/Runtime/Engine/Classes/Engine/SkeletalMesh.h:737 | yes |
| `AnimationAsset.Skeleton` | `Skeleton` | Engine/Source/Runtime/Engine/Classes/Animation/AnimationAsset.h:994 | yes || `AssetToolsHelpers.get_asset_tools().create_asset(name, folder, AnimSequence, AnimSequenceFactory())` | `UAnimSequenceFactory::FactoryCreateNew` (TargetSkeleton; no dialog) | Engine/Source/Editor/UnrealEd/Private/Factories/AnimSequenceFactory.cpp:69 | yes |
| MetaHuman face curve names `CTRL_expressions_*` (251) | raw controls list | Engine/Plugins/MetaHuman/MetaHumanCoreTechLib/Source/MetaHumanCoreTech/Private/GuiToRawControlsUtils.cpp:202-447 | yes |
| head curves `HeadYaw/HeadPitch/HeadRoll` (deg), `HeadTranslationX/Y/Z`, `HeadControlSwitch` | export | Engine/Plugins/MetaHuman/MetaHumanAnimator/Source/MetaHumanPerformance/Private/MetaHumanPerformanceExportUtils.cpp:99-109, 2684-2702 | yes |
| `unreal.AudioDrivenAnimationMood.*` (NEUTRAL, HAPPINESS, SADNESS, DISGUST, ANGER, SURPRISE, FEAR, CONFIDENCE, EXCITEMENT, BOREDOM, PLAYFULNESS, CONFUSION, AUTO_DETECT) | `EAudioDrivenAnimationMood` | Engine/Plugins/Animation/AudioDrivenAnimation/StreamingADA/Source/SpeechAnimationSolver/Public/SpeechAnimationSolverTypes.h:13 | yes |
| `unreal.AdditiveAnimationType.AAT_LOCAL_SPACE_BASE / AAT_ROTATION_OFFSET_MESH_SPACE` | `EAdditiveAnimationType` | Engine/Source/Runtime/Engine/Public/Animation/AnimTypes.h:575 | yes |
| `unreal.AdditiveBasePoseType.ABPT_*` | `EAdditiveBasePoseType` | Engine/Source/Runtime/Engine/Classes/Animation/AnimEnums.h:52 | yes |
| `MovieSceneSkeletalAnimationParams.animation / play_rate / weight / slot_name` (seq.anim, WP8) | `FMovieSceneSkeletalAnimationParams` | MovieSceneSkeletalAnimationSection.h:51-97 | yes |

Assumed, to be confirmed by the selftest: `AssetData.get_tag_value("Skeleton")` returns the string (or a tuple whose
last item is it: handled both ways); the MetaHuman face AnimBP turns the head from HeadYaw/Pitch/Roll when
HeadControlSwitch is 1 (perf.calibrate fails loudly if not); the sign conventions (measured by perf.calibrate).

## Selftest

`film-ue selftest anim` (`unreal/fmbridge/selftest/anim.py`, ~1-2 min, needs a GPU for the stills and the MetaHuman
plugin's optional content; no Epic login). It proves: anim.find ranks the templates; anim.describe reads them;
anim.new converges; 30 curves round-trip through write/read exactly and "add" adds; perf.analyze_audio finds the
emphasis of a synthetic voice; perf.face leaves the mouth curves untouched and its result passes anim.check while a
keyed straight-line head fails it; anim.additive; actionable errors; then on a face mesh spawned in the level:
perf.calibrate measures signs and eye gains, perf.apply converges a two-line spec (and a second apply runs nothing),
perf.describe reads it back, the head bone turns > 8 deg toward a 35 deg gaze target (seq.sample), and stills at rest
and turned. The engine-free parts also run on the fake in `tools/tests/test_ue_anim_ops.py`.

Tests: `tools/tests/test_ue_anim_perfkit.py` (49, pure), `test_ue_anim_ops.py` (14, fake engine),
`test_ue_anim_kind.py` (4, the spec kind on the client).

## HANDOFF

State (fleet/agent-01/ue-anim; merged into ue-helpers by the lead as it lands):

- Done, tested on the fake and in pure tests (65 tests): perfkit (gaze/head/eyes/blinks/expressions/audio/metrics/
  body/spec/library), anim.* (find, describe, new, read/write curves, check, additive, retarget, rig controls/keys,
  plus the older curve/gaze/bake ops with flags and examples), perf.* (face, check, calibrate, analyze_audio,
  head_curves, vocab, state/plan/apply/compose/solve/lock_eyes/describe, idle/gestures/walk_to/turn_to), the
  `performance` kind (schema, client planner, 2 examples), selftest/anim.py, this doc.
- Every engine call in ops/anim.py, ops/perf.py and the selftest was re-checked by an independent audit against the
  5.8.4 source (it found `get_controls` vs `get_control_keys` and the deprecated curve-identifier route: fixed).
- speech.to_face (B52): validation first, time budget + cancel, chunking at pauses, lip-flap fallback; on the fake
  with injected failures (`ue.mh_solve = "NO_FRAMES" | "hang"`).
- NOT run on a real editor (no GPU box tonight). First thing on the box: `film-ue selftest anim`. Most likely to
  need a fix, in order:
  1. `perf.calibrate`: whether the face plays the scratch animation (the face component must be Sequencer-driven;
     on a bare SkeletalMeshActor the post-process AnimBP of the MetaHuman face mesh should still run RigLogic) and
     whether HeadYaw/Pitch/Roll turn the head on that path. If it fails with "did not move", run it on a built
     MetaHuman after `mh.drive_face`.
  2. The sign conventions (`HeadSigns`): until calibrated, a gaze to the character's left may turn the head right.
     Look at the `turned` still; calibrate fixes it everywhere.
  3. `anim.find`: `AssetData.get_tag_value` return shape (string vs tuple) and the "Skeleton" tag format
     ("/Script/Engine.Skeleton'/Game/...'" is parsed by splitting on quotes).
  4. `anim.new`: AnimSequenceFactory + `set_number_of_frames` on a fresh model (FactoryCreateNew initialises it with
     one frame: AnimSequenceFactory.cpp:78-79).
  5. `anim.retarget`: the auto-generated chains on a Mixamo skeleton; the progress window under -unattended.
  6. `anim.rig_keys`: `ControlRigSequencerBindingProxy.proxy.get_display_name()` matching the actor/component.
  7. `_curve_id`: `AnimationCurveIdentifier().set_curve_identifier(...)` relies on a ref-self script method writing
     back into the struct; if curves stop being written (selftest `read.round_trip` fails), fall back to the
     deprecated `get_curve_identifier(skeleton, ...)` (it worked on the reel, with a warning per curve).
  8. speech.to_face chunking: whether a chunk's solved head motion jumps at a seam (perf.face softens it).
- Not done / next: procedural additive gestures (author bone-offset additives by code: needs bone axis calibration
  like the head's); `perf.solve_a2f` (Audio2Face route, design above). B31 (pose library) went to agent-11 as
  pose.* calling anim.rig_keys.
