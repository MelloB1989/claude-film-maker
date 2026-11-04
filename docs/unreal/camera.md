# Cameras and shooting (WP7: `cam.*`, `shot.*`)

Cinematography by code: cine cameras with real filmbacks and lenses, a **framing solver** that turns "MCU of the
presenter from 3/4 left, eye level, 50 mm" into a camera transform, camera moves baked into Sequencer, rails and
cranes, a scene's coverage on one side of the line, and **shot lists** (a declarative spec) shot into a sequence
with its camera cuts, timed to frames, seconds or dialogue lines. Every result is numeric (where each landmark lands
in the frame, distances, fields of view, depth of field) and checkable (`cam.check`, `shot.check`, stills with
guides, contact sheets).

The maths is `unreal/fmbridge/camkit/` (pure Python, stdlib only, no `unreal`): you can plan and test a whole shot
list without an editor. The ops (`unreal/fmbridge/ops/cam.py`, `ops/shot.py`) read the level into it and write the
answers back; Sequencer data goes only through WP8's ops: one batched `seq.apply` per write when WP8's core is
installed, the per-track `seq.key_*` ops otherwise.

Conventions: cm, degrees, frames at the sequence's rate; `focal_mm`, `sensor_mm` [w, h]; a rotation is
`{"pitch", "yaw", "roll"}`; frame positions **u, v are 0..1 of the picture from its top-left** (outside = out of
frame). A *subject* is an actor label: its skeleton gives the landmarks (UE5 mannequin and MetaHuman bone names),
anything else is framed from its bounds with human proportions.

## Recipes

**Frame a medium close-up.**

```bash
film-ue op cam.frame camera=CAM_A subjects=Presenter size=MCU angle=3/4 side=left height=eye focal_mm=50
```

Check: `solve.error` is ~0 (the anchors landed); `solve.predicted.Presenter.eyes` is `[0.667, 0.27]` (the right
third, room ahead of the face, since from her left she looks frame-left); `solve.warnings` is empty. Then
`film-ue op cam.check camera=CAM_A subjects=Presenter size=MCU` → `pass: true`, and a picture:
`film-ue op cam.still camera=CAM_A out=/tmp/a.png subjects=Presenter` (thirds, safe frames, and green crosses where
the solver put the landmarks: they must sit on the face, the chin, the chest...).

- Sizes: `ECU CU MCU MS COWBOY MWS WS EWS` (aliases: close-up, medium, wide, full, long, choker, american...).
- Angle: `front` 0, `1/4` 22.5, `3/4` 45, `profile` 90, `3/4 back` 135, `back` 180, or degrees, toward the
  subject's own `side` (left: the camera sees its left cheek).
- Height: `eye`, `slight high/low` (±10°), `high/low` (±20°), `overhead` (75°), `worm` (-45°), degrees, a
  landmark the lens sits at (`shoulder`, `chest`, `hip`, `knee`, `ground`), or `{"z": cm}`.
- Lens: `focal_mm` fixed → the distance is solved; `distance_cm` with `focal_mm=null` → the focal length is
  solved (`snap_focal=true` rounds it to a prime and re-solves the distance).
- Composition: `place=auto` (centre when frontal, else the third that leaves lead room), `center`, `left third`,
  `right third`, or a u. `headroom` (v of the head's top), `dutch_deg`.
- Several subjects frame a two-shot / group: the frame spans the highest head and the lowest bottom anchor and
  widens until everyone fits inside the side margins. A group "faces" square to the line between the first two (on
  the side they face, or `side` of the line when they face each other).
- Plan without touching anything: `apply=false`.

**Say it in words.** `film-ue op cam.shoot camera=CAM_A text='medium close-up of Host from 30 deg left, slightly
high, 50mm f/2.8'` (any order; subjects are the level's actor labels found in the text). The result has `parsed`
(the arguments it read), `unparsed` words it ignored (nothing is guessed: check it is empty), and `words`: the camera
described back. `cam.describe subjects=Host` gives every camera's `words` ("MCU of Host from 1/4 left (30 deg),
slightly high, 50 mm f/2.8, right third"); feeding them to `cam.shoot` puts the camera exactly where it is.
Vocabulary: sizes (extreme close-up/ECU/choker, close-up/CU, medium close-up/MCU, medium/mid/waist shot/MS, cowboy,
medium wide/MWS/knee shot, wide/full/long/WS, extreme wide/establishing/EWS, two-shot/group shot), angles (front/
head-on, 1/4, 3/4, profile/side, 3/4 back, behind, `<n> deg`), side (left/right: the subject's own), heights (eye
level, slightly high/low, high/low angle, overhead/bird's eye, worm's eye, ground/hip/chest/shoulder/knee level,
`<n> deg above|below eye level`), `<n>mm`, `<n> m|cm away` (the focal length is then solved), `f/<n>` or `T<n>`,
centered / left third / right third, dutch [n deg].

**Place a camera by hand, then read it.**
`cam.add label=CAM_B 'loc=[400,0,160]' look_at=eyes:Presenter focal_mm=35 aperture=2.8 filmback="16:9 DSLR"`
(look_at: a point, an actor, `Label:Component:bone`, `eyes:Label`). `cam.describe` (all cameras) gives loc, rot,
focal, aperture, filmback, focus, hfov/vfov, rig. `cam.project camera=CAM_B subjects=Presenter` gives every
landmark's u, v, depth and the size the frame is.

**Focus.** `cam.focus label=CAM_A mode=track target=eyes:Presenter` (the engine's tracking focus, offset to the
eyes in the actor's frame at the current pose), `mode=manual distance_cm=320` or `target=...` (its distance now),
`mode=off`. For a subject that moves, bake a follow-focus into the move (`cam.move ... focus_on=eyes:Presenter`).
`cam.check` fails `cam.focus` when the first subject's eyes are outside the depth of field.

**Move the camera.**

```bash
film-ue op cam.move camera=CAM_A sequence=/Game/Seq/S1 start_frame=0 end_frame=120 aim=eyes:Presenter \
  focus_on=eyes:Presenter noise=subtle \
  'moves_=[{"move":"push_in","fraction":0.25,"frames":72,"ease":"in_out"},{"move":"orbit","degrees":30,"frames":48}]'
```

Moves run one after another from the camera's pose; `aim` keeps the aim point where it sat in the frame (a tracked
dolly, a crane that holds its subject). Check: `first`/`last` keys in the result; play it back with `seq.still` or
`shot.sheet`.

| move | args | |
|---|---|---|
| hold | | stays (pans to keep a moving `aim`) |
| follow | | rides along with a moving `aim` (a path `[[frame,[x,y,z]],...]`, e.g. from `seq.sample`) |
| dolly | distance (cm, + forward) | level by default (`free: true` along the lens) |
| push_in / pull_out | distance, or fraction of the way to `aim` (0.25) | toward / away from the subject |
| truck | distance (cm, + right) | |
| pedestal (boom_up/down) | distance (cm, + up) | |
| crane (jib) | rise, reach (cm), swing (deg), arm (cm, 300) | a jib arc around its base |
| orbit / arc | degrees (+ counter-clockwise from above), radius, rise | around `aim` |
| pan / tilt / roll | degrees | |
| whip | degrees | a pan with an `expo` ease, for a hidden cut |
| zoom | focal (mm at the end) | even in log focal |
| dolly_zoom (vertigo) | focal | dollies so `aim` keeps its size |
| rack | to (cm) or to_point | pulls focus |

Eases: `linear in out in_out sine smooth expo`. Noise: `subtle handheld documentary breathing shake`, or
`{"preset", "seed", "scale", "pos" cm, "rot" deg, "hz"}` (seeded: the same seed, the same wobble).

**A rail or a crane.** `cam.rig label=Rail_A kind=rail 'points=[[300,-200,150],[300,200,150]]' camera=CAM_A`, then
`cam.rig_move rig_label=Rail_A sequence=/Game/Seq/S1 'keys=[[0,{"position":0}],[96,{"position":1}]]'`. Crane:
`kind=crane 'loc=[0,0,0]' yaw_deg=0 arm_cm=300 pitch_deg=10`, keys `pitch_deg`, `yaw_deg`, `arm_cm`.

**Cover a scene.** `cam.coverage 'subjects=["Host","Guest"]' side=left` makes `CAM_master` (WS square to the
line), `CAM_two_shot`, each one's `MS/MCU/CU` single from 30° off the other's eyeline, and `CAM_<name>_OTS`
(behind the other's shoulder, focal length solved, the face on the far third). All on one side of the line:
`issues` is empty. One subject: WS/MS/MCU/CU from 3/4 and an MS profile.

**Shoot a shot list.** Write a `shot` spec (below), then `film-ue plan scene.yaml` / `film-ue apply scene.yaml`
(or `film-ue op shot.plan spec=@scene.yaml`, `shot.apply`). Check: `shot.describe sequence=... subjects=[...]`
(the edit: camera, frames, lens, size per cut), `shot.check` (every shot's frame and every cut; a multi-tick job),
`shot.sheet sequence=... out_dir=/tmp/sheet per_shot=3` (a contact sheet with guides and labels).

**Cut on the dialogue.** Give `lines` (or WP12's timing document as `timing`) and either times like
`L2.start-4f`, `L1.end`, `L1.w3.start` (a word), `S2.end+0.5s`, or `auto: {from_lines: true}` (the master, then
each line on its speaker's single, cutting 4 frames early; a speaker's consecutive lines stay on one shot).

**Check a cut.** `cam.check_cut camera_a=CAM_A camera_b=CAM_B 'subjects=["Host","Guest"]'`: `shot.line_180`
(fail: the cameras are on opposite sides of the line), `shot.rule_30` (warn: a jump cut, under 30° and under two
sizes apart).

## Op reference

`film-ue ops cam` and `film-ue ops shot` give signatures and full docstrings.

| op | does |
|---|---|
| `cam.presets` | filmbacks, lenses, sizes, angles, heights, moves, eases, noise presets |
| `cam.add` | make or converge a cine camera (pose, lens, filmback, focus); `changed`, `created` |
| `cam.set` | lens: focal (or `hfov_deg`), aperture, filmback, lens preset, near clip |
| `cam.focus` | manual / track / off |
| `cam.describe` | every camera (or one) as numbers; with `subjects`, its shot in words |
| `cam.shoot` | frame a camera from a sentence of shot grammar (the inverse of the words) |
| `cam.remove` | by labels or prefix (cameras and rigs) |
| `cam.subject` | an actor's landmarks, facing and height as the solver sees them |
| `cam.point` | where a target is (point, actor, bone, eyes:Label) |
| `cam.frame` | the framing solver on a camera (or `apply=false` to plan) |
| `cam.project` | u, v, depth of points / subjects' landmarks in a camera, and the size it is |
| `cam.check` | QA's per-frame framing (WP10) + focus, safe areas, dutch, occlusion |
| `cam.check_cut` | 180° line, 30° rule |
| `cam.coverage` | coverage cameras for a scene |
| `cam.move` | baked moves into a sequence |
| `cam.rig`, `cam.rig_move` | rail / crane, mounted camera, animated |
| `cam.still` | a still with guides and the solver's landmarks (multi-tick) |
| `shot.plan` / `shot.apply` | a shot list resolved / shot into its sequence (converges) |
| `shot.describe` | the edit as it stands |
| `shot.check` | every shot and cut checked (multi-tick) |
| `shot.sheet` | a contact sheet through the cut (multi-tick) |

## Spec kinds

Client side: `tools/filmtools/unreal/cam_kind.py` (`SPEC_KINDS`: `camera` order 50, `shot` order 70); schemas
`tools/filmtools/unreal/schemas/{camera,shot}.schema.json`; examples `examples/unreal/{camera,shot}/*.yaml`.

```yaml
kind: shot
version: 1
name: interview
sequence: /Game/Films/demo/Seq_Interview
fps: 24
lines:
  - {id: L1, speaker: Host, start_s: 1.5, end_s: 4.2}
  - {id: L2, speaker: Guest, start_s: 4.6, end_s: 9.8}
subjects: {Host: {actor: Host}, Guest: {actor: Guest}}
defaults: {focal_mm: 50, aperture: 2.8, camera_prefix: CAM_}
coverage: {side: left}            # the scene's side of the line (Host -> Guest, seen from above)
shots:
  - {id: S1, start: 0, frame: {subjects: [Host, Guest], size: WS, focal_mm: 28}}
  - id: S2
    start: L1.start-4f
    frame: {subjects: [Host], size: MCU, angle: 30}      # no side: the one on the scene's side of the line
    moves: [{move: push_in, fraction: 0.15}]
    noise: subtle
    focus: Host
  - {id: S3, start: L2.start-4f, coverage: Guest_OTS}
```

A shot is `frame` (the solver), `coverage` (a coverage shot by name: `master`, `two_shot`, `<subject>_MS/_MCU/_CU/
_OTS`) or `place` (`loc` + `look_at`/`rot`, `focal_mm`). No `start`: where the previous ends; no `end`: the next
start (the last: `duration`, else the last line's end + `tail_s`). Errors come back all at once with their path and
a fix (`shots[2].frame.size: unknown shot size 'huge'; one of ...`). A `camera` spec is one camera: `frame` or
`loc`+`rot`/`look_at`, lens, `focus`, `rig`; its plan compares `cam.describe` with the solver's target.

## Gotchas

- **The default filmback is the engine's "16:9 Digital Film" (Super 35, 23.76 mm wide)**, not full frame:
  `look.camera` uses 16:9 DSLR (36 mm), where a 50 mm frames like a 33 mm here (`camkit.lens.equivalent_focal`).
- **The engine clamps focal length and aperture to the lens settings** (CineCameraComponent.cpp:528-529): `cam.*`
  widens the limits instead, so `focal_mm=1500` is 1500.
- **A cine camera constrains its aspect ratio to the filmback**: a 4:3 back rendered into 16:9 is pillarboxed.
  u, v are fractions of the *picture* (the filmback), not the image file.
- **Left and right**: a subject's `side` is its own; the scene's side of the line is seen from above along the
  line from the first subject to the second. In Unreal's left-handed frame `checks.side_of_line` is negative on
  the left. Shot lists and coverage pick each single's side for you when you leave it out; `shot.line_180` fails a
  crossing you asked for.
- **Landmarks from bones**: eyes from `FACIAL_L/R_Eye` (MetaHuman face) else 9 cm above `head`; the crown is the
  eyes + 11.5 cm: pass `top_z` (subject spec / `cam.subject`) for big hair or a hat. Facing from the eyes, else the
  clavicles; a prop's facing is its actor forward.
- **Framing uses the pose now.** For an animated subject, scrub the sequence to the shot's frame first, or give the
  move a path (`aim: [[frame, [x,y,z]], ...]`, e.g. from `seq.sample`).
- **Moves replace the camera's transform track** in that sequence; a camera shared by two shots gets both shots'
  keys in one track (between shots it is off screen).
- **`cam.still` / `shot.sheet` draw in pure Python**: keep stills small (480-960 px wide); a 1080p decode costs
  seconds of game thread.
- **QA disagreement**: `cam.check` merges WP10's `framing.*` issues; for a prop or stand-in without a skeleton QA
  judges it from its bounds (`framing.cut` infos on close sizes are expected).

## API_NOTES

Every engine API the camera ops call, verified on the UE 5.8.4 source box (`/srv/ue-src/UnrealEngine-5.8.4`).
Python names are the snake_case of the reflected names.

| API (Python) | source | verified |
|---|---|---|
| `CineCameraComponent.filmback` (FCameraFilmbackSettings `sensor_width`, `sensor_height`) | Runtime/CinematicCamera/Public/CineCameraComponent.h:38; CineCameraSettings.h:21,25 | yes |
| `CineCameraComponent.lens_settings` (`min_focal_length`, `max_focal_length`, `min_f_stop`, `max_f_stop`, `diaphragm_blade_count`) | CineCameraComponent.h:45; CineCameraSettings.h:106,110,114,118,130 | yes |
| `CineCameraComponent.focus_settings` (`focus_method`, `manual_focus_distance`, `tracking_focus_settings` {`actor_to_track`, `relative_offset`}, `smooth_focus_changes`, `focus_smoothing_interp_speed`) | CineCameraComponent.h:52; CineCameraSettings.h:216,220,240,244,248,262,266 | yes |
| `CineCameraComponent.current_focal_length`, `current_aperture` (clamped to the lens: .cpp:528-529) | CineCameraComponent.h:66,70; Private/CineCameraComponent.cpp:528 | yes |
| `get_horizontal_field_of_view`, `get_vertical_field_of_view` (FOV from sensor and focal: .cpp:286-327) | CineCameraComponent.h:108,112 | yes |
| `override_custom_near_clipping_plane`, `set_custom_near_clipping_plane` | CineCameraComponent.h:84,103 | yes |
| constrained aspect ratio = filmback | CineCameraComponent.cpp:45,536 | yes |
| `CineCameraSettings.get_cine_camera_settings().filmback_presets` | CineCameraSettings.h:333,364 | yes |
| filmback and lens presets (the tables in camkit.lens) | Engine/Config/BaseEngine.ini:3609-3639 | yes |
| `CineCameraActor.get_cine_camera_component` | CineCameraActor.h:90 | yes |
| `CameraFocusMethod.MANUAL/TRACKING/DISABLE` | CineCameraSettings.h:191 | yes |
| `CameraRig_Rail.current_position_on_rail`, `lock_orientation_to_rail`, `get_rail_spline_component` | CameraRig_Rail.h:32,36,57 | yes |
| rigs mount on their mount component (GetDefaultAttachComponent) | CameraRig_Rail.cpp:198; CameraRig_Crane.cpp:201 | yes |
| `CameraRig_Crane.crane_pitch`, `crane_yaw`, `crane_arm_length` | CameraRig_Crane.h:32,36,40 | yes |
| `SplineComponent.set_spline_points(points, SplineCoordinateSpace.WORLD, True)` | Runtime/Engine/Classes/Components/SplineComponent.h:556 (enum :39) | yes |
| `Actor.attach_to_actor` (K2_AttachToActor, ScriptName AttachToActor), `AttachmentRule` | GameFramework/Actor.h:2041; Engine/EngineTypes.h:62 | yes |
| `Actor.get_actor_bounds(False)` → (origin, extent) | Actor.h:1611 | yes |
| `Actor.get_actor_forward_vector`, `get_actor_transform`, `set_actor_location`, `set_actor_rotation`, `set_actor_label`, `get_attach_parent_actor` | Actor.h:1593,2496,1636,1663,2742,3548 | yes |
| `Transform.inverse_transform_location` | Engine/Classes/Kismet/KismetMathLibrary.h:3990 (ScriptMethod) | yes |
| `SkeletalMeshComponent.does_socket_exist`, `get_socket_location` (bones are sockets) | Components/SceneComponent.h:809,832; SkinnedMeshComponent.h:1361 | yes |
| `EditorActorSubsystem.spawn_actor_from_class`, `destroy_actor` | Editor/UnrealEd/Public/Subsystems/EditorActorSubsystem.h:228,236 | yes |
| `EditorAssetLibrary.set_metadata_tag`, `get_metadata_tag`, `save_asset`, `does_asset_exist` | Plugins/Editor/EditorScriptingUtilities/.../EditorAssetLibrary.h:385,376,281,70 | yes |
| `LevelSequenceEditorBlueprintLibrary.open_level_sequence`, `set_current_time`, `refresh_current_level_sequence`, `close_level_sequence` | Plugins/MovieScene/LevelSequenceEditor/.../LevelSequenceEditorBlueprintLibrary.h:36,90,254,72 | yes |
| `AutomationLibrary.take_high_res_screenshot` (through `look.still`) | Developer/FunctionalTesting/Public/AutomationBlueprintFunctionLibrary.h:143 | yes |
| rotator axes (FRotationTranslationMatrix), look-at (ToOrientationRotator) mirrored in camkit.geo | Core/Public/Math/RotationTranslationMatrix.h:72-84; Core/Private/Math/UnrealMath.cpp:200 | yes |
| Sequencer writes: `seq.new`, `seq.key_transform`, `seq.key_float`, `seq.camera_cuts`, `seq.cuts`, `seq.still` | WP8's ops (ops/seq.py) | their API |

## Selftest

`film-ue selftest cam` (`unreal/fmbridge/selftest/cam.py`), about 2-3 minutes, needs a GPU (stills), no Epic login,
no assets beyond the engine's basic shapes. In a scratch level lit by one directional light on black it proves:
the fields of view equal the engine's for four filmbacks; markers placed with `lens.unproject` at chosen (u, v)
render there (within 1.5% of the frame) on a 16:9 and a 4:3 back; a 175 cm stand-in framed WS/MCU/CU renders with
its top on the predicted row (within 2.5%); `cam.add`/`cam.frame`/`cam.coverage`/`shot.apply` converge; a push-in's
and a rail's positions played back by Sequencer equal the baked keys; `shot.describe` reads back the spec's cuts;
`shot.check` finds no crossed line; a 9-cell contact sheet. Its metrics include the projection error. The same test
runs on the fake engine in `tools/tests/test_ue_cam_ops.py::test_selftest_runs_on_the_fake` (everything but the
pixel and playback checks).

## HANDOFF

State (2026-11-05, agent-11, branch `fleet/agent-11/ue-cameras`): everything above is written and unit-tested
(`tools/tests/test_ue_cam_kit.py`, `test_ue_cam_ops.py`, `test_ue_cam_spec.py`; all ue tests green), nothing has
run in a real editor yet. Tomorrow on the GPU box:

1. `film-ue selftest cam`. The likely first failures and where to look:
   - *markers off by a constant*: the still's aspect handling (pillarbox/letterbox in `take_high_res_screenshot`
     with a constrained-aspect camera) — the mapping is in the selftest's section 2; camkit.lens assumes the picture
     is the filmback.
   - *the figure's top off*: exposure/threshold in `_bright` (selftest), or bounds: a basic cylinder's bounds are
     its size.
   - *push-in keys not played*: WP8's `seq.key_transform` binding (the camera must be possessable in the sequence)
     or the scrub needing more ticks.
2. `cam.check` on a MetaHuman: compare our landmarks (`cam.subject`) with WP10's from the same bones; the crown
   offset (`CROWN_ABOVE_EYES`) may want tuning per character (hair).
3. Writes: `cam.write_tracks` is the only Sequencer writer. With WP8's `seq.apply` registered it sends one
   sequence spec (`cam.seq_doc`: transform keys, `CameraComponent/...` props, camera cuts, range) in one batched
   call; otherwise the per-track ops. Trial-merged with fleet/agent-06/ue-sequencer@4291b0a: green and converging
   (`test_shot_apply_on_wp8_sequencer` runs once WP8's core is on ue-helpers).

Not done: a `film-ue` CLI shortcut beyond `op`/`plan`/`apply` (WP11's call); shot subsequences on a cinematic shot
track (WP8's `seq.shots`; we cut one sequence with camera cuts); camera shake assets (we bake noise).
