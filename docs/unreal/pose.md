# Poses (B31: `pose.*`)

Named poses on a character's body, by code, checked by numbers: `hands_on_hips`, `arms_crossed`, `hands_clasped`,
`thinking`, `wave`, `point`, `presenting`, `neutral`, `crouch`, `sit`, `lean_forward`, `lean_back` (or your own goal
table). `pose.apply` keys the body's Control Rig at a frame of a sequence and solves it closed-loop: it moves each
effector's control in world space by the bone's remaining error, lets the engine evaluate, measures, and repeats
until every effector is within `tolerance_cm`. `pose.check` measures a pose at a frame. The library and the maths are
`unreal/fmbridge/ops/_pose.py` (pure); the Control Rig track and its keys are WP4's (`anim.rig_keys`,
`anim.rig_controls`), agreed with agent-01.

## Recipes

**Hands on hips at frame 48.**

```bash
film-ue op pose.apply label=Host sequence=/Game/Seq/S010 frame=48 pose=hands_on_hips \
  rig_class=/Game/MetaHumans/Common/Common/MetaHuman_ControlRig
film-ue op pose.check label=Host sequence=/Game/Seq/S010 frame=48 pose=hands_on_hips
```

Check: `pass`, `errors_cm` (every effector, cm from its goal: under the tolerance), `controls` (which rig controls the
pattern match used: read it first when a pose misses), `iterations`. A second apply: `iterations: 0`. Look:
`cam.still` through a camera on the character at that frame (or `seq.still`).

**Sit on a chair.** `pose=sit 'params={"drop_cm": 42}'`: the hips go down 42 cm and back 5, the feet stay planted.
Put the chair under the hips first (layout); check the seat contact with `qa.penetration`.

**A pose of your own.** `pose={"hand_r": {"anchor": "head", "offset": [12, 4, -10]}, "foot_l": "keep", "foot_r":
"keep"}`: effectors hand_l/r, foot_l/r, pelvis, chest, head; anchors pelvis, chest, head, neck, shoulder_l/r,
hand_l/r, foot_l/r, ground; offsets [forward, right, up] cm in the body's frame; "keep" holds an effector where it
is; a world point [x, y, z] works too.

**Hold a pose through a shot.** Apply it at the shot's first and last frames (two calls): the rig's keys
interpolate between them.

**A rig with other control names.** `controls={"hand_l": "LeftHand_IK", ...}` overrides the match;
`film-ue op anim.rig_controls sequence=... label=...` lists the rig's controls.

## Op reference

| op | does |
|---|---|
| `pose.library [pose=]` | the poses, their effectors and goal tables; parameters |
| `pose.apply` | key and solve a pose at a frame (multi-tick; converges) |
| `pose.check` | measure a pose at a frame: `{pass, issues (pose.effector_off), metrics.errors_cm}` (multi-tick) |

## Gotchas

- **Goals are relative to the rest pose**, captured the first time a pose is applied in a sequence (stored on the
  sequence as metadata `fm_pose_rest:<label>`). After moving the character, pass `reset_rest=true`.
- **Control names are matched, not assumed** (hand_l_ik_ctrl, foot_l_ik_ctrl, body_ctrl, spine_05..., head...):
  the MetaHuman body rig's names live in its asset, not in engine source, so they were not verifiable tonight.
- **World-space control writes need the sequence open** in the level editor: the ops open it.
- **Rig assets**: a 5.8 independent Control Rig asset cannot become a Sequencer track from Python
  (`load_blueprint_class` returns None, per agent-01); legacy ControlRigBlueprint assets such as the MetaHuman body
  and face boards work. Pass one of those as `rig_class`.
- **IK controls**: a hand reaches its goal only if its arm can (reach, elbow); a goal out of reach stays in the
  `errors_cm` and fails the check: that is the signal to change the goal, not to iterate more.

## API_NOTES

| API (Python) | source | verified |
|---|---|---|
| `ControlRigSequencerLibrary` (ScriptName of UControlRigSequencerEditorLibrary) | Plugins/Animation/ControlRig/Source/ControlRigEditor/Public/ControlRigSequencerEditorLibrary.h:121 | yes |
| `.get_control_rigs(seq)` | same:143 | yes |
| `.get_control_rig_world_transform(seq, rig, control, frame, time_unit)` | same:557 | yes |
| `.set_control_rig_world_transform(seq, rig, control, frame, transform, time_unit, set_key)` ("sequence must be loaded in the level editor") | same:584 | yes |
| `.find_or_create_control_rig_track` (through anim.rig_keys) | same:154 | yes |
| `MovieSceneTimeUnit.DISPLAY_RATE`, `FrameNumber` | (enum EMovieSceneTimeUnit, used by the signatures above) | yes |
| `RigHierarchy.get_controls()` (ScriptName of GetControlKeys; `get_control_keys` does not exist in Python) | Plugins/Animation/ControlRig/Source/ControlRig/Public/Rigs/RigHierarchy.h:1181 | yes |
| `LevelSequenceEditorBlueprintLibrary.set_global_position(MovieSceneSequencePlaybackParams, MovieSceneTimeUnit)` (replaces set_current_time, deprecated 5.4: :88-90), in ops/_scrub.py | Plugins/MovieScene/LevelSequenceEditor/.../LevelSequenceEditorBlueprintLibrary.h:107-108 | yes |
| `MovieSceneSequencePlaybackParams(frame=FrameTime(FrameNumber(f)), position_type=MovieScenePositionType.FRAME, update_method=UpdatePositionMethod.SCRUB)` | Runtime/MovieScene/Public/MovieSceneSequencePlayer.h:91-120 (EMovieScenePositionType :83, EUpdatePositionMethod :39); FrameTime: Runtime/Core/Public/Misc/FrameTime.h | yes |
| `SkeletalMeshComponent.does_socket_exist`, `get_socket_location` | Runtime/Engine/Classes/Components/SceneComponent.h:809,832 | yes |
| `LevelSequenceEditorBlueprintLibrary.open_level_sequence`, `set_current_time`, `refresh_current_level_sequence`, `get_current_level_sequence` | Plugins/MovieScene/LevelSequenceEditor/.../LevelSequenceEditorBlueprintLibrary.h:36,90,254 | yes |
| `EditorAssetLibrary.set_metadata_tag`, `get_metadata_tag` | EditorAssetLibrary.h:385,376 | yes |
| `ControlRigBlueprint` asset class (selftest search) | Plugins/Animation/ControlRig/Source/ControlRigDeveloper/Public/ControlRigBlueprintLegacy.h:34 | yes |
| `AssetRegistry.get_assets_by_class(TopLevelAssetPath, search_sub_classes)`, `get_assets_by_path` | Runtime/AssetRegistry/Public/AssetRegistry/IAssetRegistry.h:335 | yes |

## Selftest

`film-ue selftest pose` (`unreal/fmbridge/selftest/pose.py`), 1-2 minutes, needs a body Control Rig and body mesh in
the project (a MetaHuman), else skipped with a note. It poses hands_on_hips, arms_crossed, wave and sit, checks every
effector within tolerance and the feet planted, re-applies (nothing changes), notes the rig's controls and the
matches, and takes a still per pose.

## HANDOFF

Done (agent-11, 2026-11-05, branch `fleet/agent-11/ue-pose`): library, ops, fake rig (ext_pose), tests, selftest,
this doc. Not run in an editor. First thing tomorrow: `film-ue selftest pose` on the MetaHuman project; read the
note "pattern match chose" and, if a control was matched wrongly, add its real name to `_pose.CONTROL_PATTERNS`
(first in the list). The offsets of the library poses are first guesses for an adult: tune them on stills.
