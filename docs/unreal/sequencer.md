# Sequencer core (WP8, `seq.*`)

Level sequences driven entirely by code: describe one as JSON, converge it to a declarative SEQUENCE SPEC in one batched,
idempotent call, write or remove single tracks, evaluate what the engine plays (no ticking, no viewport), and manage
shots (pre-roll for cloth, render chunks), copies and retimes. Frames are display frames at the sequence's rate.

Code: `unreal/fmbridge/ops/seqcore/` (engine-free `_time _curves _model _spec _plan`, the engine side `_engine`, the ops
in `seq_core`); the older single-purpose ops stay in `unreal/fmbridge/ops/seq.py`. Client: `tools/filmtools/unreal/
seq_spec.py` (offline validate/plan, the `sequence` spec kind). Schema: `tools/filmtools/unreal/schemas/
sequence.schema.json`. Examples: `examples/unreal/sequence/`. Tests: `tools/tests/test_ue_seq_*.py`; the fake is
`tools/tests/fakeunreal/ext_seq.py`. Selftest: `unreal/fmbridge/selftest/seq.py`.

## Recipes

**Build a shot from a spec, and re-run it safely.**

    film-ue plan examples/unreal/sequence/two_shot.yaml        # the steps, nothing changed
    film-ue apply examples/unreal/sequence/two_shot.yaml       # create, bind, write what differs; describe again
    film-ue apply examples/unreal/sequence/two_shot.yaml       # changed: false, plan empty

Check: `apply` returns `converged: true` and `remaining: []`; a second apply returns `changed: false`. From Python:
`client.op("seq.apply", spec=yaml.safe_load(open(p)))`. Only tracks that differ are rewritten; tracks the spec does
not mention are kept (`prune: true` removes the unlisted tracks of the bindings it names).

**Read a sequence as JSON (and feed it back).**

    film-ue op seq.describe path=/Game/Film/SEQ_010 keys=false   # key counts only
    film-ue op seq.describe path=/Game/Film/SEQ_010 check=true   # plus seq.check's verdict

The result's `tracks` is the same shape a spec's `tracks:` takes, so `{"sequence", "fps", "range", "bindings",
"tracks"}` of a describe applied back is a no-op. `unsupported` lists tracks of classes the core does not model
(apply never touches them). `film-ue op seq.diff path=A other=B` (or `spec=`) says what differs and where each
track first differs (a param, a section's range, a channel's key index with both keys).

**Key one property fast (a bake).** One call writes every key of a track (batched; Sequencer closed while writing; a
tick yielded every 2000 keys, so 20k keys never freeze the editor):

    film-ue op seq.write path=/Game/S/SEQ_A 'track={"kind":"float","binding":"Key","component":"LightComponent0","name":"Intensity","sections":[{"range":[null,null],"channels":{"value":{"keys":[[0,1000,"linear"],[96,5000]]}}}]}'

Reduce a dense bake first (`seq_spec.core().curves.reduce(samples, tol)`: fewest linear keys within `tol`).

**Check that the keys landed** (numbers, no viewport):

    film-ue op seq.eval path=/Game/S/SEQ_A 'frames=[0,24,48]' 'labels=["Hero"]' \
        'tracks=[{"kind":"float","binding":"Key","component":"LightComponent0","name":"Intensity"}]'

`transforms` are world [x, y, z, pitch, yaw, roll] as Sequencer evaluates them (attachment included); `channels` are
the curves' values. `film-ue op seq.check path=...` finds unbound bindings, camera-cut gaps, cuts to unbound cameras,
rotation flips across ±180, keys outside the range, overlapping shots (issues `seq.*`, CONVENTIONS §8 shape).

**A master sequence of shots, rendered without cold cloth.**

    film-ue apply examples/unreal/sequence/master_shots.yaml
    film-ue op seq.preroll path=/Game/Examples/Seq/SEQ_Master frames=24      # every shot section pre-rolls 24 frames
    film-ue op seq.chunks path=/Game/Examples/Seq/SEQ_Master max_frames=48 preroll=8

Each chunk is `{start, end, eval_from, preroll_frames, shot, first_after_cut, cold}`: render `[eval_from, end)` and
keep `[start, end)`. A chunk never starts a simulation mid-shot (the Linux PoC's open overshirt, docs/linux/engine.md
P6); `max_preroll` caps the cost and flags `cold`. Judge `first_after_cut` frames on their own (TSR history).

**A shot list → an edit (master + one sequence per shot).** `examples/unreal/sequence/shot_list.yaml`: each shot
entry takes `duration` (start defaults to the previous shot's end), `camera: <label>` (a one-camera shot sequence)
or `shot: {...}` (the shot's own tracks, an inline spec), `handles` and `preroll`. Apply converges every shot
sequence (`<master>_<name>`) first, then the master's shot track; a change inside one shot re-applies only that
shot. Frame the cameras with WP7 (`cam.frame`, `shot.apply` into the shot sequence); render with `seq.chunks` on the
master.

**Pull a shot out, move time.**

    film-ue op seq.copy src=/Game/Film/SEQ_All dst=/Game/Film/SEQ_sh020 start=120 end=240   # window -> [0, 120)
    film-ue op seq.retime path=/Game/Film/SEQ_sh020 offset=12 after=48     # ripple: insert 12 frames at 48
    film-ue op seq.retime path=/Game/Film/SEQ_sh020 scale=2 out=/Game/Film/SEQ_sh020_slow  # half speed, a copy

Copy without a window duplicates the asset (everything, even unmodelled tracks). With a window, clips start that
much later into themselves and curves hold their values at the edges. Retime plays animation at rate/scale; audio
is moved, never stretched.

**Change the frame rate (conform).**

    film-ue op seq.conform path=/Game/Film/SEQ_010 fps=25                  # keep TIME: every key stays at its second
    film-ue op seq.conform path=/Game/Film/SEQ_010 fps=48 keep=frames out=/Game/Film/SEQ_010_48   # keep FRAMES

Keeping time only relabels frames (keys, sections and markers live in ticks); `off_frame` counts what now falls
between frames. Keeping frames rewrites every track at the same frame numbers: the sequence plays faster or slower,
animation rates follow, audio sections end where their sound does. A rate that does not land on whole ticks (29.97,
59.94 on 24000) switches the tick resolution to 60000 first, keys migrated.

**Slow down one beat.** `film-ue op seq.retime path=... start=48 end=72 scale=2` plays [48, 72) twice as long and
moves everything after it by 24 frames (animation inside at half rate; audio moved, not stretched).

**Times.** `film-ue op seq.time value=00:01:00:00 fps=23.976` → frame, seconds, timecode (drop-frame `;` at
29.97/59.94), ticks. Specs take `48`, `"48f"`, `"2s"`, `"1m30s"`, `"500ms"` or `"HH:MM:SS:FF"` wherever a frame goes.

## Op reference (`film-ue ops seq`)

| op | what | mutates / idempotent |
|---|---|---|
| `seq.describe(path, spec?, keys, check)` | the sequence as canonical JSON (+ `want` resolved from a spec) | no |
| `seq.validate(spec)` | every problem of a spec at once, offline-equivalent | no |
| `seq.plan(spec, prune?)` | the steps apply would run | no |
| `seq.apply(spec, prune?, dry_run, save)` | converge (multi-tick); re-describes and reports `converged` | yes / yes |
| `seq.add(path, fps, start, end, tick_resolution)` | make or converge rate and range | yes / yes |
| `seq.bind(path, label, spawn?, replace)` | possessable by label, or a spawnable `{class}`/`{template}` | yes / yes |
| `seq.write(path, track)` | one canonical track, batched (multi-tick) | yes / yes |
| `seq.remove_track(path, kind, binding, component, name)`, `seq.remove_binding(path, label)` | remove | yes / yes |
| `seq.markers(path, markers)` | marked frames (display frames) | yes / yes |
| `seq.eval(path, frames, labels, tracks)` | engine evaluation: world transforms, channel values | no |
| `seq.diff(path, other? / spec?)` | what differs, and where each track first differs (a spec: only what it states) | no |
| `seq.check(path)` | numeric QA verdict | no |
| `seq.shots(path)`, `seq.chunks(path, ...)`, `seq.preroll(path, frames)` | shots, render chunks, pre-roll | -, -, yes / yes |
| `seq.copy(src, dst, start?, end?, to, replace)`, `seq.retime(path, offset, scale, pivot, after, start?, end?, out)` | edit time | yes / copy yes, retime no |
| `seq.conform(path, fps, keep=time\|frames, out)` | change the display rate keeping time or frames | yes / yes |
| `seq.time(value, fps, path)` | conversions | no |

Older ops (`ops/seq.py`, kept with their signatures and results, now a thin layer: every write goes through
seqcore's `write_track`, `seq.cuts`/`seq.set_anim` read through `describe`; pinned by `tests/test_ue_seq_legacy.py`): `seq.new`, `seq.shot`,
`seq.key_transform`, `seq.key_float`, `seq.key_color`, `seq.key_visible`, `seq.key_material`, `seq.key_collection`,
`seq.anim`, `seq.audio`, `seq.camera_cuts`, `seq.cuts`, `seq.rebind`, `seq.tracks`, `seq.set_anim`, `seq.scrub`,
`seq.close`, `seq.sample` (bones by ticking, for rigs that settle), `seq.still`, `seq.stills` (stills through the cut).
Each maps to a spec section: key_transform → `transform`, key_float/key_color → `props`, key_visible → `visible`,
key_material → `materials`, key_collection → `collections`, anim → `anim`, audio → `audio`, camera_cuts →
`camera_cuts`.

## The `sequence` spec kind

```yaml
kind: sequence
version: 1
name: two_shot
sequence: /Game/Examples/Seq/SEQ_TwoShot      # made if missing
fps: 24
range: [0, 8s]                                # playback [start, end)
markers: [[48, line_starts]]
bindings:
  Host:                                       # an actor label: a possessable
    transform:
      keys:                                   # [frame, [x,y,z], {pitch,yaw,roll} | look-at point(, interp)]
        - [0, [-300, 0, 0], {yaw: 0}]
        - {frame: 2s, loc: [0, 0, 0], look_at: CamClose, interp: linear}
    anim: {component: Body, sections: [{anim: /Game/Anim/Walk, start: 0, end: 48, blend_out: 6}]}
    visible: [[0, true]]
  Key:
    props:
      LightComponent0/Intensity: [[0, 2], [2s, 8, linear]]
      LightComponent0/LightColor: {type: color, srgb: true, keys: [[0, [1.0, 0.85, 0.7]]]}
  Drone:
    spawn: {class: CineCameraActor}           # the sequence owns it
camera_cuts: [[CamWide, 0], [CamClose, 3s]]
audio: {VO: [{sound: /Game/Audio/L1, start: 12}]}
fade: {color: [0, 0, 0], keys: [[0, 1], [12, 0]]}
shots: [{sequence: /Game/Shots/SEQ_sh010, start: 0, end: 120, preroll: 24},   # or a shot list:
        {name: close, camera: CamClose, duration: 3s, handles: 12}]   # start = previous end; made for you
collections: [{collection: /Game/MPC_Grade, param: Exposure, keys: [[0, 0], [120, 0.3]]}]
tracks: []                                    # raw canonical tracks (seq.describe's shape)
```

Keys: `[frame, value(, interp(, tangents))]` or `{frame, value, interp, tangents: {arrive, leave}}` (slopes per
display frame). Interp leaving a key: `auto` (smooth, clamped), `smart`, `linear`, `constant` (a step), `user`,
`break`. Rotations are always `{pitch, yaw, roll}` and are unwrapped across ±180 (`unwrap: false` to keep them).
Transform channels a spec leaves unkeyed hold the actor's current value. Colours are linear; `srgb: true` converts
(an FColor property such as a light's LightColor). Property owners: `Component/Prop.Path`; without a component, the
actor if it has the property, else its root component. A float property that is a double in C++: `type: double`.
Animation sections default `end` to the clip's length / rate; `loop: false` ends the section with the clip.

Under WP11's engine the kind plans from `seq.describe(path, spec)`: its `want` is the spec resolved in the editor
(look-at targets, clip lengths, property owners), so `film-ue plan` matches what apply will do.

## Gotchas

- **Batched writes.** UE 5.8's scripting channels have no array key API; each `add_key` makes a key object and
  broadcasts OnChannelChanged, which an open Sequencer answers. So the core writes a whole track per op call, closes
  the sequence in Sequencer while writing (and reopens it), yields every 2000 keys, saves once. Never loop
  `seq.key_*` per key over the wire.
- **Two time units.** Scripting channels and section ranges take display frames; section pre/post roll, easing,
  audio and animation start offsets, sub-section offsets and material / collection parameter keys are TICKS
  (24000/s by default). Tangents are stored per tick. The core converts; raw engine code must too.
- **Marked frames:** use `get_marked_frames_from_sequence` / `add_marked_frame_to_sequence` (display rate); the
  shorter names are the deprecated tick-unit ones.
- **Spawnables** are made with the deprecated `add_spawnable_from_class/_instance` (they work headless; the subsystem
  replacements need the sequence open). 5.5+ spawnables are custom bindings: `get_spawnables()` does not list them;
  describe calls a binding spawnable when it has a spawn track. A component track on a spawnable needs the spawned
  object, so the sequence is opened for it.
- **Play rate and shot time scale** are `MovieSceneTimeWarpVariant` (5.5+), set with
  `MovieSceneTimeWarpExtensions.make_time_warp(x)`.
- **No hold-last-frame** in 5.8's skeletal animation params: past the clip the section loops; `loop: false` ends the
  section instead.
- **Material tracks** start with `material_type` EMPTY from Python (nothing plays): the core sets INDEXED_MATERIAL.
  Their sections are `MovieSceneComponentMaterialParameterSection` (parameter info + layer + asset names); a colour
  parameter's channels are named `<Param>R/G/B/A` (no dot).
- **ControlRig's world-transform evaluation** evaluates the OPEN sequence and ignores its sequence argument:
  `seq.eval` with labels opens it.
- **Camera-cut blending** (`bCanBlend`) is not scriptable; `MovieSceneObjectBindingID` exposes only `guid` (build
  ids with `get_binding_id`).
- **Changing `fps`** on an existing sequence keeps keys at their time in seconds (they live in ticks); their frame
  numbers change. `tick_resolution` migrates keys.
- **The `audio` kind (WP12)** also manages audio tracks: let one of the two own a given track name.
- **Event tracks** are read (key counts) but not written: their keys need a director-blueprint endpoint
  (`SequencerTools.create_quick_binding` + `create_event`); seq.write answers `unsupported`.

## API_NOTES (UE 5.8.4 source, verified on the source box)

Paths: `SS/` = Engine/Plugins/MovieScene/SequencerScripting/Source/SequencerScripting/Public/ExtensionLibraries/,
`KC/` = .../SequencerScripting/Private/KeysAndChannels/, `MS/` = Engine/Source/Runtime/MovieScene/Public/, `MST/` =
Engine/Source/Runtime/MovieSceneTracks/Public/, `LSE/` = Engine/Plugins/MovieScene/LevelSequenceEditor/Source/
LevelSequenceEditor/Public/. Python names are the snake_case of the reflected names (PyGenUtil; DisplayName is
ignored, ScriptName wins). All verified by reading the declaration unless marked otherwise.

| Python | engine | source |
|---|---|---|
| `LevelSequence.get/set_display_rate`, `get/set_tick_resolution` (set migrates keys) | MovieSceneSequenceExtensions | SS/MovieSceneSequenceExtensions.h:98, 107, 116, 125 |
| `get/set_playback_start`, `get/set_playback_end` (display frames, end exclusive) | same | :174, 192, 210, 228 |
| `add_possessable(obj)` | same | :411 |
| `add_spawnable_from_class(cls)`, `add_spawnable_from_instance(obj)` (deprecated 5.5, work headless) | same; ULevelSequence::CreateSpawnable | :421, 433; Runtime/LevelSequence/Private/LevelSequence.cpp:948 |
| `get_bindings()`, `get_possessables()` | same | :383, 401 |
| `get_binding_id(proxy)` → MovieSceneObjectBindingID (`guid` only) | same | :457; MS/MovieSceneObjectBindingID.h:201 |
| `add_track(cls)`, `find_tracks_by_exact_type`, `get_tracks`, `remove_track` | same | :79, 69, 49, 89 |
| `get_marked_frames_from_sequence(time_unit)`, `add_marked_frame_to_sequence(mf, time_unit)`, `delete_marked_frames()` | same | :532, 546, 577 |
| `MovieSceneMarkedFrame` `frame_number`, `label` | struct | MS/MovieSceneMarkedFrame.h:37-61 |
| `make_range(start, duration)` (display frames) | same | :145 |
| `locate_bound_objects(binding, world)` | same | :446 |
| `MovieSceneBindingProxy.get_id / get_display_name / set_display_name / get_tracks / find_tracks_by_exact_type / add_track / remove_track / remove / get_parent / set_parent / get_child_possessables / get_possessed_object_class` | MovieSceneBindingExtensions | SS/MovieSceneBindingExtensions.h:44, 53, 62, 107, 127, 154, 136, 144, 190, 199, 163, 181 |
| `track.add_section / get_sections / remove_section / set_display_name / get_display_name` | MovieSceneTrackExtensions | SS/MovieSceneTrackExtensions.h:72, 81, 90, 33, 42 |
| `set_property_name_and_path / get_property_path` | MovieScenePropertyTrackExtensions | SS/MovieScenePropertyTrackExtensions.h:33, 51 |
| `set_num_channels_used` (Float/DoubleVectorTrack) | MovieSceneVectorTrackExtensions | SS/MovieSceneVectorTrackExtensions.h:31 |
| `section.set_range / set_start_frame / set_end_frame / set_start_frame_bounded / set_end_frame_bounded / get_start_frame / get_end_frame / has_start_frame / has_end_frame` | MovieSceneSectionExtensions | SS/MovieSceneSectionExtensions.h:145-209, 36-81 |
| `get_all_channels()` (enabled channels only), `get_channel(name)` | same | :220, 243 |
| `set_row_index / get_row_index` | UMovieSceneSection UFUNCTION | MS/MovieSceneSection.h:541, 545 |
| `set_pre_roll_frames(int ticks) / get_pre_roll_frames / set_post_roll_frames / get_post_roll_frames` | UMovieSceneSection UFUNCTION | MS/MovieSceneSection.h:612-621 |
| `set_ease_in_duration / set_ease_out_duration / get_ease_in_duration / get_ease_out_duration` (ticks) | MovieSceneSectionEasingExtensions | SS/MovieSceneSectionEasingExtensions.h:23-35 |
| channel `add_key(FrameNumber, value, sub_frame, time_unit, interpolation)` (Float/Double/Byte; Bool/Integer/String: no interpolation) | KC/ channels | KC/MovieSceneScriptingDouble.h:245, Float.h:376, Bool.h:79, Integer.h:81, String.h:81 |
| `get_keys / remove_key / set_default / get_default / has_default / evaluate_keys(range, rate) / transform(...)` | same | KC/MovieSceneScriptingDouble.h:285-427, Float.h:446-673 |
| channel `channel_name` | UMovieSceneScriptingChannel BlueprintReadOnly | SequencerScripting/Public/MovieSceneScriptingChannel.h:42 |
| AddKeyInChannel: `Section->Modify()` + `OnChannelChangedWithTime` per key (why writes are batched) | template | SequencerScripting/Public/MovieSceneScriptingChannel.h:67-113 |
| key `get_time(time_unit)`, `get_value`, `get/set_interpolation_mode`, `get/set_tangent_mode`, `get/set_arrive_tangent`, `get/set_leave_tangent`, `set_tangent_weight_mode`, `set_arrive/leave_tangent_weight` | KC/ key classes | KC/MovieSceneScriptingDouble.h:34-223, Float.h:33-154 |
| tangents are slope per tick | FMovieSceneTangentData, curve eval | MS/Channels/MovieSceneCurveChannelCommon.h:47-53; Runtime/MovieScene/Private/Channels/MovieSceneCurveChannelImpl.cpp:74, 825 |
| `MovieSceneKeyInterpolation.AUTO/SMART_AUTO/USER/BREAK/LINEAR/CONSTANT`, `RichCurveInterpMode`, `RichCurveTangentMode` (RCTM_SMART_AUTO), `RichCurveTangentWeightMode.RCTWM_WEIGHTED_BOTH`, `MovieSceneTimeUnit.DISPLAY_RATE` | enums | MS/KeyParams.h:14-29; Engine/Classes/Curves/RichCurve.h, RealCurve.h; MS/MovieSceneTimeUnit.h |
| `MovieScene3DTransformTrack` channels Location.X..Scale.Z as MovieSceneScriptingDoubleChannel (mask not scriptable) | section | MST/Sections/MovieScene3DTransformSection.h:302-319; Private/Sections/MovieScene3DTransformSection.cpp:83-189 |
| `MovieSceneSkeletalAnimationTrack`; section `params` (copy: set back) with `animation`, `start_frame_offset` (ticks), `play_rate` (TimeWarpVariant), `slot_name`, `reverse`; channel "Weight" | section, FMovieSceneSkeletalAnimationParams | MST/Sections/MovieSceneSkeletalAnimationSection.h:50-119 |
| `MovieSceneTimeWarpExtensions.make_time_warp(rate)`, `to_fixed_play_rate` | TimeWarp extensions | SS/MovieSceneTimeWarpExtensions.h:26-52 |
| `MovieSceneVisibilityTrack` (channel = visible; the system drives the bound Actor / SceneComponent itself, so the property name, bHiddenInGame as the reel used, is a label: MovieSceneVisibilitySystem.cpp:40-75), `MovieSceneFloatTrack`, `MovieSceneDoubleTrack`, `MovieSceneBoolTrack`, `MovieSceneByteTrack`, `MovieSceneEnumTrack`, `MovieSceneIntegerTrack`, `MovieSceneStringTrack`, `MovieSceneColorTrack`, `MovieSceneDoubleVectorTrack`, `MovieSceneFloatVectorTrack` | track classes | MST/Tracks/*.h (Visibility: MovieSceneVisibilityTrack.h:15, .cpp:87; Vector: MovieSceneVectorTrack.h:15, 42) |
| `MovieSceneComponentMaterialTrack.get/set_material_info` (`material_slot_index`, `material_slot_name`, `material_type` = `ComponentMaterialType.INDEXED_MATERIAL`) | MovieSceneMaterialTrackExtensions | SS/MovieSceneMaterialTrackExtensions.h:51, 59; MST/Tracks/MovieSceneMaterialTrack.h:17, 237 |
| material section `add_scalar_parameter_key(info, ticks, v, layer, asset, default_interpolation)`, `add_color_parameter_key(...)`, `remove_scalar_parameter`, `remove_color_parameter`; channels `<Param>`, `<Param>R/G/B/A` | MovieSceneComponentMaterialParameterSection | MST/Sections/MovieSceneComponentMaterialParameterSection.h:110-132; Private/...cpp:84-121 |
| `MaterialParameterInfo` (`name`, `association` = `MaterialParameterAssociation.GLOBAL_PARAMETER`, `index`) | struct | Runtime/Engine/Public/MaterialTypes.h |
| `MovieSceneMaterialParameterCollectionTrack` (`mpc`); section MovieSceneParameterSection `add_scalar_parameter_key(name, ticks, v, default_interpolation)`, `add_color_parameter_key`, `remove_scalar_parameter` | track / section | MST/Tracks/MovieSceneMaterialParameterCollectionTrack.h:17-28; MST/Sections/MovieSceneParameterSection.h:337-384 |
| `MovieSceneCameraCutTrack`; section `set/get_camera_binding_id` | section | MST/Sections/MovieSceneCameraCutSection.h:42, 49 |
| `MovieSceneAudioTrack`; section `set_sound / get_sound / set_start_offset / get_start_offset` (ticks); channels Volume, Pitch | section | MST/Sections/MovieSceneAudioSection.h:27; Private/Sections/MovieSceneAudioSection.cpp:85-87 |
| `MovieSceneFadeTrack`; section `fade_color`, `fade_audio` | section | MST/Sections/MovieSceneFadeSection.h:42-47 |
| `MovieSceneLevelVisibilityTrack`; section `set_visibility(LevelVisibility.VISIBLE/HIDDEN) / get_visibility / set_level_names / get_level_names` | section | MST/Sections/MovieSceneLevelVisibilitySection.h:40-49 |
| `MovieSceneSubTrack`, `MovieSceneCinematicShotTrack`; section `set/get_sequence`, `parameters` (`start_frame_offset` ticks of the inner sequence, `time_scale` TimeWarpVariant), `set/get_shot_display_name` | sections | MS/Sections/MovieSceneSubSection.h:110, 161, 262; MST/Sections/MovieSceneCinematicShotSection.h:41-45 |
| `MovieSceneSpawnTrack` (bool section, made by add_spawnable_*) | track | MS/Tracks/MovieSceneSpawnTrack.h:30 |
| `MovieSceneEventTrack` (read only here) | track | MST/Tracks/MovieSceneEventTrack.h; SS/MovieSceneEventTrackExtensions.h:33, 42 |
| `MovieSceneCameraShakeTrack` (not modelled: listed as unsupported) | track | MST/Tracks/MovieSceneCameraShakeTrack.h:30 |
| `LevelSequenceEditorBlueprintLibrary.open_level_sequence / close_level_sequence / get_current_level_sequence / refresh_current_level_sequence / get_bound_objects / set_current_time / set_lock_camera_cut_to_viewport` (set_current_time deprecated 5.4, still works) | LSE library | LSE/LevelSequenceEditorBlueprintLibrary.h:36, 72, 42, 254, 262, 90, 280 |
| `LevelSequenceEditorSubsystem.replace_binding_with_actors(actors, binding)` (needs the sequence open; seq.rebind) | subsystem | LSE/LevelSequenceEditorSubsystem.h:149-308 |
| `ControlRigSequencerEditorLibrary.get_actor_world_transforms(seq, actor, [FrameNumber], time_unit)` (evaluates the OPEN sequence) | ControlRigEditor | Engine/Plugins/Animation/ControlRig/Source/ControlRigEditor/Public/ControlRigSequencerEditorLibrary.h:466; Private/...cpp:202-214 |
| `Transform.translation`, `Transform.rotation` (Quat) `.rotator()` | `Quat_Rotator` ScriptMethod "Rotator" | Runtime/Engine/Classes/Kismet/KismetMathLibrary.h:2908 |
| `AnimSequence.get_play_length()` (the clip length; `sequence_length` is the deprecated fallback) | UAnimationAsset BlueprintPure | Runtime/Engine/Classes/Animation/AnimationAsset.h:1060 |
| `EditorAssetLibrary.duplicate_asset / does_asset_exist / load_asset / save_loaded_asset / list_assets` | EditorScriptingUtilities | Engine/Plugins/Editor/EditorScriptingUtilities/Source/EditorScriptingUtilities/Public/EditorAssetLibrary.h:175 |
| `AssetToolsHelpers.get_asset_tools().create_asset(name, folder, LevelSequence, LevelSequenceFactoryNew())` | AssetTools | Developer/AssetTools/Public/IAssetTools.h (UFUNCTION CreateAsset) |
| `UnrealEditorSubsystem.get_editor_world`, `EditorActorSubsystem` | editor subsystems | Editor/UnrealEd/Public/Subsystems/UnrealEditorSubsystem.h |
| `MathLibrary.find_look_at_rotation` (seq.py's key_transform) | KismetMathLibrary | Runtime/Engine/Classes/Kismet/KismetMathLibrary.h |
| `CameraComponent` (class token), `SceneComponent.get_socket_transform(name, RelativeTransformSpace.RTS_WORLD)` (seq.py's seq.sample) | USceneComponent UFUNCTION | Runtime/Engine/Classes/Components/SceneComponent.h (GetSocketTransform) |
| `unreal.load_class(None, "/Script/Module.Class")`, `unreal.EnumBase` (the Python base of reflected enums; a property's enum value) | Python glue, not UFUNCTIONs | Plugins/Experimental/PythonScriptPlugin/Source/PythonScriptPlugin/Private/PyCore.cpp |
| default tick resolution 24000, display rate 30 (CVars LevelSequence.DefaultTickResolution / DefaultDisplayRate) | ULevelSequence::Initialize | Runtime/LevelSequence/Private/LevelSequence.cpp:78-125 |

## Selftest

`film-ue selftest seq` (`unreal/fmbridge/selftest/seq.py`), ~1-2 min, GPU only for the stills. It builds a scratch
scene, applies a spec with every written track kind, proves idempotency (second apply and plan empty) and the
describe→apply round trip, compares the engine's evaluation with the spec's keys (transforms at key frames, linear
ramps between), rewrites exactly one changed track, prunes, times a 20,000-key bake (`write_keys_per_s` metric), runs
shots / chunks / pre-roll, copy and ripple retime, checks the actionable errors, and takes four stills through the
cut. Its report names everything it could not exercise (no AnimSequence, no audio import).

## HANDOFF

State at the end of the night (agent-06, branch `fleet/agent-06/ue-sequencer`, merged into `ue-helpers` by the lead):

- Done: the pure core (time incl. drop-frame timecode and compatible tick resolutions, keys and curves, canonical
  document, spec compiler, plan, diff, lint, shots, render chunks, copy / retime / stretch transforms), the engine
  adapter for every listed track kind, 20 new `seq.*` ops plus flags/examples on the 20 older ones, the `sequence`
  spec kind for WP11's engine (shot lists: B20), seq.conform (B22), the schema and three examples, the fake
  Sequencer (B41: keys, ranges, playback and markers in ticks), 64 unit tests, the selftest (dry-run on the fake
  through the real harness: every check passes up to the GPU stills). Every UE API verified on the 5.8.4 source
  (table above).
- Not yet run on an engine: tomorrow's first `film-ue selftest seq` is the acceptance test. Most likely to need a
  fix: reading colour / vector / byte channels by order (`_engine._channels`), the material section's colour-channel
  grouping, `get_start_frame` rounding of off-frame sections after a conform (the fake floors).
- Not done: writing event tracks (read only: needs a director-blueprint endpoint), camera-shake / data-layer tracks
  (listed as unsupported); `seq.anim`'s `loop: false` still does nothing in 5.8 (no
  hold-last-frame field), as before.
- Later the same night: `ops/seq.py` became a layer over seqcore (one engine path; B01's helpers from `_util`). Its
  results are pinned against the old implementation (golden `tools/tests/data/seq_legacy_golden.json`); three
  differences are on purpose (anim offset now StartFrameOffset, play rate via make_time_warp, collection keys by
  FName) and listed in that test.
