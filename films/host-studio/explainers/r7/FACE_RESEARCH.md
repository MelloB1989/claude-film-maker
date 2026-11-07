# R7 face research: MetaHuman facial PERFORMANCE (for agent-04 / FACE)

Round 7, task 20261108-round-7-research-metahuman-82cb. Research only; no face data.

The problem: v2b's face solves were mouth-only, so the operator saw a "pale, no emotion" face.
The fix:
1. A full-face audio solve with a per-line mood.
2. Word-timed brow, smile and cheek accents on top of it.
3. Baked to one AnimSequence per line.

Every API name is from Epic's **5.7** Python reference unless marked. No 5.8 reference was found, so check each name
on the box with `dir()` / `help()` before relying on it. Our `unreal/fmbridge/ops/speech.py` already uses the
solve names on 5.8.

---

## 1. The tutorial: Shaun Foster, "Emotional Animation, Linked Blending & Baking" (UE 5.5)

[Video](https://www.youtube.com/watch?v=zm3LUB5NLXM). This is a summary from the auto-subtitles, in our own words.

**Part 1 (00:36), audio-driven solve**
- Enable the MetaHuman plugin.
- New MetaHuman Performance asset with:
  - Input Type = Audio, and the SoundWave;
  - Control Rig = the MetaHuman face control rig;
  - Visualization Mesh = the face mesh;
  - accept the prompt to use the audio clock.
- **Process**, then export **both** an Animation Sequence and a Level Sequence.
- In the Level Sequence:
  - add the MetaHuman;
  - on the **Face** track, remove the face Control Rig;
  - add the exported AnimSequence as the face animation.

**Part 2 (04:22), Animation Layers plus pose-library expressions**
- Open the Animation Mode tab (Shift+8), then the **Layers** panel.
- Add the folder `MetaHumans/Common/Common/PoseLibrary` to the Poses view. It holds face poses under
  `Face/Expressions` (Amusement, Joy, Dejection, …) and `Visemes`. Epic ships them, but they are hidden.
- Re-add the face Control Rig, then **select the pose's controls**.
- Create a layer from the selection and name it ("smile"), then **paste the pose**: the keys land on that layer.
- Each extra expression goes on its own layer ("dejection"). Layers are **additive** and can be toggled on and off
  and blended against each other.
- **Tip:** while the mouth is speaking, use a **mostly-closed-mouth expression**. Open-mouth expressions fight the
  lip-sync. A character animator might pause the dialogue to dial in a big open expression; we should not.

**Part 3 (08:20), combine and bake**
- Right-click the Face binding. **Bake Animation Sequence** keys every frame; **Create Linked Animation Sequence**
  makes a clip that stays linked to the Level Sequence and re-bakes when the sequence changes. The tutorial prefers
  the linked clip.
- Then remove the face Control Rig and stack the clips on the Face track: the speech solve plus the
  "smile/expression" clip. Blend the clips by their weights; a third clip is possible.

**Part 4 (10:18), pro tips (animators Heather Harris and Kevin McNulty)**
- **Save before you delete:** deleting the face Control Rig track deletes every layer's keys. Duplicate and rename
  the Level Sequence first; this is your editable source.
- **The voice must match the face:** a smile can be heard in the voice. A smiling face over a neutral read looks
  wrong, so emotion must come from the audio as well as the face.
- **Expression changes the mouth shapes:** they get wider and larger when shouting, and accents change them too.
  A neutral lip-sync with a smile pasted on top is not enough; the solve itself must be emotional.
- Hire or consult a real character animator where possible. Blinks were covered in his previous video.

**What this means for us**
- The tutorial's base solve is **mouth-only**: the same mistake we made.
- Its emotion layer is a hand-placed **pose**, not driven by speech.
- Our plan goes further: the base is a **full-face solve with a mood**, so the mouth shapes carry the emotion
  (tip 3), and the layers are only **accents**.
- Tip 2 is a VO question: our TTS lines must be read happy/confident too. Flag it to the VO owner.

---

## 2. The offline audio solve: settings and Python

Epic doc: [audio-driven animation](https://dev.epicgames.com/documentation/en-us/metahuman/audio-driven-animation)
(UE 5.6+). Python: [MetaHumanPerformance](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MetaHumanPerformance?application_version=5.7).

| UI | Python property | Values / use |
|---|---|---|
| Process Mask | `audio_driven_animation_output_controls` | `AudioDrivenAnimationOutputControls.FULL_FACE` / `MOUTH_ONLY`. **Use FULL_FACE now.** |
| Solve Overrides (mood) | `audio_driven_animation_solve_overrides.mood` | `AudioDrivenAnimationMood` (table below) |
| Solve Overrides (intensity) | `...solve_overrides.mood_intensity` | float, 0-1. **Neutral ignores intensity.** |
| Generate Blinks | `generate_blinks` | bool. True, unless perfkit owns the blinks (see §6). |
| Head Movement | `head_movement_mode` | `PerformanceHeadMovementMode.TRANSFORM_TRACK` / `CONTROL_RIG` / `DISABLED` |
| Head pose reference | `auto_choose_head_movement_reference_frame`, `head_movement_reference_frame` | |
| Downmix / channel | `downmix_channels`, `audio_channel_index` | |
| Frames to process | `start_frame_to_process`, `end_frame_to_process` | |
| Realtime Audio | `realtime_audio` (+ `realtime_audio_mood*`) | **Keep False.** Realtime turns off head motion and the solve options. |
| Model | `audio_driven_animation_models` | Undocumented; leave at the default. |

**Moods** (`AudioDrivenAnimationMood`):

| UI label | Enum |
|---|---|
| Auto Detect | `AUTO_DETECT` |
| Neutral | `NEUTRAL` |
| Happy | `HAPPINESS` |
| Happy: Confident | `CONFIDENCE` |
| Happy: Excited | `EXCITEMENT` |
| Happy: Playful | `PLAYFULNESS` |
| Sad | `SADNESS` |
| Sad: Bored | `BOREDOM` |
| Fear | `FEAR` |
| Fear: Confused | `CONFUSION` |
| Disgust | `DISGUST` |
| Anger | `ANGER` |
| Surprise | `SURPRISE` |

The UI labels differ from the enum names. `film-ue op speech.moods` lists what the box actually has.

**Per-line mood map for the presenter** (a starting point; agent-11's acting sheet wins):

| Line type | Mood | Intensity |
|---|---|---|
| Hook / question ("Network dips?") | `PLAYFULNESS` | 0.6-0.8 |
| Hook, conspiratorial | `EXCITEMENT` | 0.5 |
| Explanation body | `CONFIDENCE` | 0.6-0.8 |
| Payoff ("it just starts", "that's why it just plays") | `HAPPINESS` | 0.8-1.0 |

- Avoid `AUTO_DETECT` on TTS: flat TTS reads as neutral.
- Avoid intensity 1.0 throughout: it compounds with the accent layers and looks mugged. Sweep 0.5/0.75/1.0 on one
  line in the test first.

**Python per line.** This is what `speech._solve` does (`unreal/fmbridge/ops/speech.py:62-132`):

```python
P = unreal.MetaHumanPerformance
perf = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
    f"Perf_{name}", folder, P, unreal.MetaHumanPerformanceFactoryNew())
perf.set_editor_property("input_type", unreal.DataInputType.AUDIO)    # member name: check with dir()
perf.set_editor_property("audio", sound_wave)
perf.set_editor_property("visualization_mesh", face_mesh)
perf.set_editor_property("audio_driven_animation_output_controls",
                         unreal.AudioDrivenAnimationOutputControls.FULL_FACE)
so = perf.get_editor_property("audio_driven_animation_solve_overrides")   # a struct: copy, edit, set back
so.set_editor_property("mood", unreal.AudioDrivenAnimationMood.CONFIDENCE)
so.set_editor_property("mood_intensity", 0.75)
perf.set_editor_property("audio_driven_animation_solve_overrides", so)
perf.set_editor_property("generate_blinks", True)
perf.set_editor_property("head_movement_mode", unreal.PerformanceHeadMovementMode.CONTROL_RIG)
perf.start_pipeline(True)      # scripted; poll perf.is_processing() across ticks (speech.py does)
U = unreal.MetaHumanPerformanceExportUtils
st = U.get_export_animation_sequence_settings(perf)  # CDO, shared: restore show_export_dialog afterwards
st.show_export_dialog = False; st.package_path = f"{folder}/Anim"; st.asset_name = f"AS_{name}"
st.enable_head_movement = True; st.export_range = unreal.PerformanceExportRange.WHOLE_SEQUENCE
anim = U.export_animation_sequence(perf, st)
```

- Our op already does this: `film-ue op speech.to_face wav=… name=L01 face_mesh=… mood=CONFIDENCE intensity=0.75
  process_mask=full head=true blinks=true`.
- Epic's own scripts: `Engine/Plugins/MetaHuman/MetaHumanAnimator/Content/Python/process_audio_performance.py`,
  `export_performance.py` and `ReadMe.txt`.
  ([doc](https://dev.epicgames.com/documentation/en-us/metahuman/python-scripting-for-metahuman-animator))
- **One mood per Performance asset.** For a mood change inside a line, split the WAV at a pause (speech.py's
  chunking), or keep one mood and do the change with accents (§3).

### xADA
"xADA: Expressive Audio Driven Animation for MetaHumans" is Epic's model that makes face, tongue and head
animation from speech. It runs in an automatic mode, or with artist overrides for emotion and blink timing.

Sources:
- [the Unreal Fest Orlando 2025 talk](https://forums.unrealengine.com/t/talks-and-demos-xada-expressive-audio-driven-animation-for-metahumans-unreal-fest-orlando-2025/2674008)
- [the paper](https://researchr.org/publication/TaylorMWSM25)
- [Epic Research](https://www.unrealengine.com/en-US/research) lists an "EpicADA" paper from SIGGRAPH 2025 that looks
  like the same work.

**It ships as the offline audio solve itself** (5.6+, so also 5.7 and 5.8). There is **no separate switch**: Input
Type = Audio with `realtime_audio = False` is xADA, and the mood and blink overrides are its controls. This is
inferred: the features match exactly and forum users call the solver "xADA"
([thread](https://forums.unrealengine.com/t/metahuman-xada-for-custom-audio-streams-guidance-needed/2675424)).
Epic has not said so in a doc.

---

## 3. Word-timed accents: three routes, most robust first

The accents to add: brow flashes, Duchenne smiles, cheek raise and squint, one-brow curiosity.

### A. Curve route (recommended for scripting): write additive accents into the exported AnimSequence's curves

- The face AnimSequence drives the rig through `CTRL_expressions_*` curves (`unreal/fmbridge/perfkit/rig.py`).
- `anim.write_curves` / `anim.set_curve` / `anim.scale_curves` already exist (`unreal/fmbridge/ops/anim.py`).
- Read the solved curve, **add** the accent envelope, clamp to 0-1 and write it back. There is no Sequencer state, no
  selection and no layer API.
- Deterministic, testable with fakeunreal, and agent-09's gate can read the same curves.

Curves:

| Accent | Curves |
|---|---|
| Brow flash | `browRaiseInL/R`, `browRaiseOuterL/R` |
| Smile | `mouthCornerPullL/R` |
| Duchenne | `eyeCheekRaiseL/R` + `eyeSquintInnerL/R` |
| Curious one-brow | `browRaiseOuterL` only, plus a small head tilt |

Check the exact names against the AS's curve list (`perfkit/rig.py` notes the case quirk on 5.8).

### B. Sequencer Animation Layers on the face Control Rig (the tutorial's way; good for hand tweaking)

5.7 Python ([AnimLayer](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimLayer?application_version=5.7),
[ControlRigSequencerLibrary](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/ControlRigSequencerLibrary?application_version=5.7)):

```python
CR = unreal.ControlRigSequencerLibrary
unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(seq)  # the layer calls act on the OPEN Sequencer
# select the face-board controls first (rig.select_control(name) for each), then:
idx = CR.add_anim_layer_from_selection()
layer = CR.get_anim_layers()[idx]          # get_anim_layers(add_if_does_not_exist=True)
layer.set_name("accents_brow"); layer.set_type(unreal.AnimLayerType.ADDITIVE); layer.set_weight(0.8)
# keys: set_local_control_rig_float(s)(seq, rig, control, frame(s), value(s), set_key=True)
# BEST GUESS: aim keys at the layer's section first: track.set_section_to_key(layer_section)
CR.set_local_control_rig_floats(seq, rig, "CTRL_L_brow_raiseOut", frames, values)
```

- Not verified:
  - how a layer maps to its section (`anim_layer_items`);
  - the face-board control names. `CTRL_L_brow_raiseIn` is in our code; `CTRL_L_brow_raiseOut`,
    `CTRL_L_mouth_cornerPull`, `CTRL_L_eye_cheekRaise` and `CTRL_L_eye_squintInner` are likely.
- List the real names with `film-ue op anim.rig_controls`, or
  `[c.name for c in rig.get_hierarchy().get_controls()]`.
- Layers need the OPEN Sequencer and a selection: fragile headless.
- A forum report says Override layers behave additively over layered rigs
  ([thread](https://forums.unrealengine.com/t/using-animation-layers-with-layered-control-rig/2268479)).
- Other calls: `merge_anim_layers_with_settings` and `collapse_control_rig_anim_layers(seq, track, key_reduce,
  tol)` flatten the layers.

### C. A layered (additive) Control Rig track over the AnimSequence

- `CR.find_or_create_control_rig_track(world, seq, rig_class, binding, is_layered_control_rig=True)`. Our
  `anim.rig_keys … layered=true` does this.
- The face rig's keys **add** to the solved animation, with no layer panel involved.
- Fine for the test. Bake it (§4) before the final render.

---

## 4. Baking: Linked Animation Sequences

`unreal.SequencerTools` (5.7, [page](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SequencerTools?application_version=5.7)):

```python
f = unreal.AnimSequenceFactory()
f.set_editor_property("target_skeleton", face_skel)       # set BOTH before create_asset,
f.set_editor_property("preview_skeletal_mesh", face_mesh) # or the link fails / crashes (forum)
anim = unreal.AssetToolsHelpers.get_asset_tools().create_asset(f"AS_{name}_final", folder, unreal.AnimSequence, f)
opt = unreal.AnimSeqExportOption()
opt.export_morph_targets = True; opt.evaluate_all_skeletal_mesh_components = True
unreal.SequencerTools.export_anim_sequence(world, seq, anim, opt, face_binding, True)  # True = create the link
# or: SequencerTools.link_anim_sequence(seq, anim, opt, binding)
# query/clear: get_anim_sequence_link_from_level_sequence, get_level_sequence_link_from_anim_sequence,
#              clear_linked_anim_sequences
```

- Pitfall: [forum, linked anim in Python](https://forums.unrealengine.com/t/creating-linked-animation-sequence-in-python/2094979).
  The forum used `record_in_world_space = True`; for a face, test both values.
- A plain bake is the same call with `create_link=False`.
- **A linked sequence re-bakes when its Level Sequence changes.** That is good while iterating. For finals, freeze
  it: a plain bake, or `clear_linked_anim_sequences`, so a later edit cannot change a rendered take.
- **Keep the source Level Sequence** (tutorial tip 1): duplicate it before removing any face Control Rig track.
- With route A there is nothing to bake: the AS *is* the final.

---

## 5. Rules: what makes a talking face read alive

Numbers are for 30 fps. Each rule names its source.

**Brows**
- Raise on **stressed and key words and questions**, not on every pitch accent: most accents carry none
  ([Ekman, via Edinburgh thesis](https://era.ed.ac.uk/items/c1dfbb39-7eef-4b4d-aec0-8102dcc50453)).
- **Start the rise 2-4 frames before the word and peak on its stressed syllable**; the brow peak also comes before
  the head nod's peak ([Kim/Cvejic/Davis 2014](https://researchers.westernsydney.edu.au/en/publications/tracking-eyebrows-and-head-gestures-associated-with-spoken-prosod/),
  [Cruz & Frota 2023](https://guarant.cz/icphs2023/776.pdf)).
- A flash is about **6 frames** in total (rise ~3), at intensity 0.4-0.7
  ([PMC2238342](https://pmc.ncbi.nlm.nih.gov/articles/PMC2238342)).
- An emphasis raise held across a phrase is 10-20 frames.
- Brows follow the **overall shape** of the intonation, not every pitch wiggle
  ([Frontiers 2022](https://frontiersin.org/articles/10.3389/fcomm.2022.903015/pdf)).
- The R7 targets (≥ 6 flashes/min) fit with this: about one per sentence, on the key word.

**Smiles**
- **Duchenne = corner pull + cheek raise + slight inner squint, together** (AU12 + AU6)
  ([PMC4053432](https://pmc.ncbi.nlm.nih.gov/articles/PMC4053432)).
- A corner pull alone reads polite or fake.
- **Amused/warm smiles have a slow, smooth onset and offset** (8-15 frames). Polite ones are fast-on, abrupt-off and
  read social ([AAMAS 2012](https://ifaamas.csc.liv.ac.uk/Proceedings/aamas2012/papers/2A_5.pdf)).
- Put them at the hook, the payoffs and **line ends**.
- During speech keep the corner pull **moderate (0.3-0.5 over the solve)** with lips mostly closed, so it doesn't
  break visemes (tutorial tip).
- Bigger smiles go in the pauses and at line ends.

**Asymmetry and offsets**
- Never mirror L and R exactly. **The left side leads by about 1 frame**, with 5-15% more amplitude on one side
  ([Mount Sinai](https://scholars.mssm.edu/en/publications/facial-asymmetry-in-posed-and-spontaneous-expressions-of-emotion-2/)).
  The percentage is our choice.
- **Stagger the features: brow, then head, then mouth**, never all starting on the same frame.
- Curiosity is **one brow** (outer raise on one side) plus a 3-6° head tilt.

**Eyes**
- Keep eye contact with the lens (on_lens stays).
- Add **micro-saccades and thinking darts**: a new small target about every 0.3-1 s while talking.
- A dart **moves in 2-3 frames, never eased**. Duration ≈ 25 ms + 2.5 ms/deg
  ([Eyes Alive](https://www.cis.upenn.edu/~badler/papers/EyesAlive.pdf)).
- **Look away briefly at the start of a thought, and back to the lens on the new or key information**
  ([Cassell et al. 1997](https://www.media.mit.edu/gnl/publications/cassell_torres_prevost_97.pdf)). That is the
  "thinking glance".

**Blinks**
- **20-30 per minute** with irregular gaps ([PubMed 9399231](https://pubmed.ncbi.nlm.nih.gov/9399231/)).
- Place them at **phrase boundaries** and **on head turns and gaze shifts**: 97% of large gaze shifts come with a
  blink, starting on the same frame
  ([Evinger 1994](https://researchconnect.stonybrook.edu/en/publications/not-looking-while-leaping-the-linkage-of-blinking-and-saccadic-ga/)).
- Never blink inside a stressed word.

**Head**
- **Nods on stressed words**, timed to the pitch accents and phrase ends; speakers differ in size, not in timing
  ([Graf et al. 2002](https://www.cstr.ed.ac.uk/downloads/publications/2002/paper.vtts.pdf)).
- The solver's `head_movement_mode` gives some of this. Add emphasis nods on the acting sheet's words.

**Holds**
- **No dead holds.** Every held expression keeps a slow drift (a moving hold) of about 5-10% amplitude
  ([Animation Mentor](https://animationmentor.com/blog/why-all-animators-need-to-master-the-moving-hold)).
- Change the expression every 2-4 s. This matches the gate's `neutral_hold_max_s ≤ 1.5`.

**Mouth**
- Lead the sound: open the jaw **1-2 frames before the audio**.
- Hold m/b/p closures 2-3 frames ([AWN](https://www.awn.com/print/vfxworld/inspired-3d-lip-sync-and-facial-animation-part-1)).
- The solve already does most of this. Don't scale it down; mouth-only plus a weak jaw was half of "pale".

**Restraint**
- Osipa: limit the brow range, and "sometimes the best shape is no shape"
  ([Stop Staring ch.9](https://www.oreilly.com/library/view/stop-staring-facial/9780471789208/ch09.html)).
- Vary the accents and keep the intensity variable. The same flash at the same height every sentence reads
  robotic.

---

## 6. Recommended build for the 12-15 s test

1. **Base:** `speech.to_face process_mask=full blinks=true head=true`, with a per-line mood and intensity from the
   §2 table and the acting sheet.
   - Base solve blinks are only an option. If perfkit's blink/eye pass stays (`blink_nod`, on_lens), set
     `generate_blinks=false`, so the blinks don't double. Keep the solver's **brows and cheeks**: FULL_FACE is the
     whole point.
2. **Accents:** route A (curves) from the acting sheet's word times.
   - Brow flash: lead 3 frames, peak 0.5, 6-frame total, L before R by 1 frame.
   - Duchenne at the payoffs: `mouthCornerPull` +0.35, `eyeCheekRaise` +0.4, `eyeSquintInner` +0.2, 10-frame
     onset, moving hold, 12-frame release.
   - One-brow curiosity plus a tilt on the hook.
3. **Eyes:** keep perfkit's on_lens, plus darts every 0.3-1 s and one look-away at each thought start.
4. **Bake:** route A needs none. Routes B/C go through §4 with a link while iterating, then frozen.
5. **Gate:** sweep mood intensity (0.5 / 0.75 / 1.0) on line 1 first. The operator's eye picks the level.

---

## 7. Backup: NVIDIA Audio2Face-3D (open release, Sept 2025)

**Licences** ([GitHub hub](https://github.com/NVIDIA/Audio2Face-3D),
[model card](https://huggingface.co/nvidia/Audio2Face-3D-v3.0),
[NVIDIA Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/)):

| Component | Licence | Commercial use |
|---|---|---|
| SDK | MIT | Yes |
| UE plugin v2.5 | MIT | Yes |
| Training framework | Apache | Yes |
| A2F-3D models (v3.0, v2.3) | NVIDIA Open Model License | Yes, royalty-free |
| Audio2Emotion | Separate gated licence | Only with A2F; no standalone emotion recognition |
| Claire dataset | | Evaluation only |

Open Model License conditions:
- Ship the licence and a Notice file if you redistribute the model.
- The licence ends if you bypass the guardrails or sue over IP.
- NVIDIA claims no rights in the outputs.

**MetaHuman support:**
- The UE plugin outputs ARKit curves into the "Apply ACE Face Animations" node, placed before the MetaHuman ARKit
  mapping pose (`mh_arkit_mapping_pose_A2F`).
- Supports **UE 5.5 and 5.6**; 5.7/5.8 not found ([changelog](https://docs.nvidia.com/ace/ace-unreal-plugin/2.5/ace-unreal-plugin-changelog.html)).
- Emotion: six labels (joy, anger, …) as input, or inferred from the audio by A2E.
- Needs an NVIDIA GPU with CUDA 12.8+.

**Verdict:** only if xADA's moods can't reach the bar.
- ARKit to MetaHuman loses detail compared with xADA's native rig output.
- The plugin lags the engine version we're on.

---

## Unverified, check on box B (5.8)
- `DataInputType.AUDIO` member name.
- The face-board `CTRL_*` names.
- Mapping an AnimLayer to its section for keying.
- The `AnimSeqExportOption` fields for a face-only export.
- That `audio_driven_animation_models` has only one choice.
