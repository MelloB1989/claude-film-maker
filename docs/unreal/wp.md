# wp: World Partition in the editor (B37)

A partitioned level (a Fab environment, any big world) holds every actor on disk, and the editor loads only regions
of it. An actor outside the loaded regions does not exist in the editor world, so `level.find` cannot see it and an
editor capture (`view.still` mode capture) does not draw it. The `wp.*` ops show what the partition holds and load
the part a task needs: what a camera sees, a box, a sphere, named actors, or everything.

**Renders do not need this.** A Movie Render Queue render runs in PIE, which streams the partition around the camera
and blocks every frame until the cells are in (`UMoviePipeline::FlushAsyncEngineSystems` ->
`BlockTillLevelStreamingCompleted`, MoviePipelineRendering.cpp:641; MRQ also sets `wp.Runtime.BlockOnSlowStreaming
0`). Load regions before **editor-world** work: captures, QA measurements, layout, look.

Code: `unreal/fmbridge/ops/wp.py`, pure math in `ops/_wp.py`, fake in `tools/tests/fakeunreal/ext_wp.py`, tests in
`tools/tests/test_ue_wp.py`, selftest in `unreal/fmbridge/selftest/wp.py`. Data layers are WP6's `level.layers` /
`level.layer_set`.

## Recipes

**What is in this level?**

```bash
film-ue op wp.describe                   # partitioned?, bounds, actors, loaded now, per grid
film-ue op wp.find contains=Tree loaded=false limit=20
```

**Load what a camera sees before an editor still.**

```bash
film-ue op wp.load camera=Cam_A far_cm=8000        # waits until the actors are in the editor world
film-ue op view.still camera=Cam_A out=/tmp/a.png
```

`far_cm` is how far to load (default 50 m), and `pad_cm` grows the frustum (default 5 m) so shadows and reflections
from just off-screen are there too. The planner keeps only actors whose bounds meet the frustum itself, not just its
bounding box. Running it again changes nothing (`changed: false`).

**Load everything a shot sees.** `film-ue op wp.load sequence=/Game/Reel/SEQ_Reel 'frames=[1080,1160]' every=12`
scrubs the sequence in Sequencer (opened and closed again), samples every 12th frame through the camera cuts, loads
each cut's camera actor if it is not loaded, and loads what any sampled frustum meets. `cameras` lists the cameras
used. Sample more often (`every=4`) for fast camera moves.

**Load a region, a spot or named actors.** Use `box=[[x,y,z],[x,y,z]]` (cm), `around=[x,y,z] radius_cm=3000`,
`labels=[House, Bridge]`, or `all=true` (careful on a big world). Add `pin=true` to keep them loaded when the editor
changes its regions.

**Give the memory back.** `wp.unload all=true`, or pass `labels=`/`box=`. It unloads only what `wp.load` loaded; it
returns the rest in `kept`.

Check: `wp.describe`'s `loaded` count goes up after a load and back down after an unload; `wp.load` returns
`missing: []`.

## Ops (`film-ue ops wp`)

| op | what |
|---|---|
| `wp.describe` | partitioned?, editor/runtime bounds, actors, loaded, spatially/always loaded, per grid, loaded_by_ops |
| `wp.find [contains cls box loaded limit]` | actor descriptors (loaded or not): label, guid, class, bounds, grid, spatial, data layers, loaded |
| `wp.load camera= / sequence= [frames every] / box= / around= radius_cm= / labels= / all=true [far_cm pad_cm pin timeout_s]` | multi-tick: load, wait until they are in the editor world |
| `wp.unload labels= / box= / all=true` | unload what wp.load loaded |

On a level that is not partitioned, every op answers `partitioned: false` with no error, because everything is
already loaded.

## Gotchas

- `load_actors` goes through an actor-list loader adapter owned by the library (one per world). `unload_actors` can
  only remove what that adapter loaded. Actors loaded by the editor's own regions or the "load all" button stay.
- The adapter is dropped when the world partition is uninitialized (the level is closed or reopened), so loads do
  not survive a level change. Load again after `level.open`.
- Descriptors reflect what is **on disk**: a moved but unsaved actor is found at its saved bounds.
- A partitioned level reopens with its spatially loaded actors unloaded, unless the editor restores the user's last
  loaded regions (a per-user setting). Do not assume either: read `wp.describe` first.
- `wp.load all=true` on a city-sized world can take minutes and many GB. Prefer `camera=`.

## API_NOTES (UE 5.8.4 source, verified)

| API (Python) | source | notes |
|---|---|---|
| `WorldPartitionBlueprintLibrary.get_editor_world_bounds / get_runtime_world_bounds` | Engine/Source/Runtime/Engine/Public/WorldPartition/WorldPartitionBlueprintLibrary.h:106,113 | invalid box (`is_valid` false) without a partition |
| `...get_actor_descs() -> [ActorDesc] or None`, `get_intersecting_actor_descs(box)` | WorldPartitionBlueprintLibrary.h:144,151 | editor world (UnrealEditorSubsystem), recursing into containers (.cpp:83-110, 243) |
| `...load_actors(guids) / unload_actors(guids) / pin_actors(guids)` | WorldPartitionBlueprintLibrary.h:119,125,131; .cpp:193-230 | FLoaderAdapterActorList per world |
| `ActorDesc.guid, label, name, native_class, bounds, runtime_grid, is_spatially_loaded, actor_is_editor_only, data_layer_assets` | WorldPartitionBlueprintLibrary.h:20-77 | BlueprintReadOnly |
| `Actor.actor_guid` | Engine/Source/Runtime/Engine/Classes/GameFramework/Actor.h:1097 | BlueprintReadOnly: matches descriptors to loaded actors |
| `CameraComponent.field_of_view, aspect_ratio` | Engine/Source/Runtime/Engine/Classes/Camera/CameraComponent.h:44,108 | horizontal FOV in degrees |
| `Box(min, max, is_valid)` | Engine/Source/Runtime/CoreUObject/Public/UObject/NoExportTypes.h:1560 | |
| `LevelSequenceEditorBlueprintLibrary.open_level_sequence / set_current_time / close_level_sequence` | Engine/Plugins/MovieScene/LevelSequenceEditor/.../LevelSequenceEditorBlueprintLibrary.h:72 (+ the same file) | wp.load sequence= scrubs through them, as seq.scrub does |
| `LevelEditorSubsystem.new_level(path, is_partitioned_world)` (selftest) | Engine/Source/Editor/LevelEditor/Public/LevelEditorSubsystem.h:147 | |
| MRQ streams WP itself | MovieRenderPipelineCore/Private/MoviePipelineRendering.cpp:641, MoviePipelineGameOverrideSetting.cpp:164 | no wp.load needed for renders |
| `UWorldPartitionEditorLoaderAdapter` (regions as in the UI) | Engine/Source/Runtime/Engine/Public/WorldPartition/WorldPartitionEditorLoaderAdapter.h:10 | no UFUNCTIONs: not reachable from Python, hence the actor-list route |

## Selftest

`film-ue selftest wp` takes about 30 s and needs no GPU. It makes a partitioned level with four cubes 200 m apart
and a camera, saves it, and reopens it. It then proves `describe` and `find`; that `wp.load camera=` loads the cube
in view and not the one behind it, and converges; that `around=` loads the cube behind; that `unload` puts it back;
and that a plain level answers `partitioned: false`.

## HANDOFF

Done: the ops, the frustum math, the fake, 9 unit tests, the selftest and this doc. Unproven until the box runs the
selftest: `Guid.to_string` and whether the reopened level comes up unloaded. (The return of `get_actor_descs` is
settled by the Python plugin's rule: a bool return with out params gives None for false, else the out value;
PythonScriptPlugin/Private/PyGenUtil.cpp:1161.) `wp.load sequence=` is unit-tested only (not yet in the selftest).
