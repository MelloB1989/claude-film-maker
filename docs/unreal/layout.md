# Layout, set dressing and scene specs (WP6)

This area finds actors and reads the level as JSON (`level.*`), places things relative to each other and to what
is under them (`layout.*`), and converges a whole set from one declarative spec (`scene.*`, kind `scene`). Every
mutating op is idempotent: re-running it moves the same actors to the same places. Every op answers in numbers
(transforms, bounds), so a change can be checked without looking.

## Recipes

**See what is in the level**

```bash
film-ue op level.describe                                # counts by class, lights, cameras, geometry bounds
film-ue op level.find label='Chair_*'                    # glob or substring; also cls=, tag=, folder=
film-ue op level.find cls=Light 'near=[0,0,150]' radius_cm=500   # nearest first
film-ue op level.get label=Desk                          # + components, meshes, materials
```

Each actor comes back as `{"label", "class", "loc", "rot", "scale", "bounds": {"min", "max", "size"}, "tags",
"folder", "hidden", "mesh"}`. Bounds are world-space and axis-aligned, so a 90° turn swaps X and Y.

**Rest things on what is under them**

```bash
film-ue op layout.drop 'labels=["Desk","Lamp","Mug"]'    # in that order: the desk first, then what sits on it
```

Check: `level.get label=Mug` gives a `bounds.min[2]` equal to the desk's `bounds.max[2]`. Use `mode=trace` to ask
the physics scene instead of the boxes, for a support that is not a box (a sloped floor, a round table).

**Place one thing relative to another**

```bash
film-ue op layout.relative label=Chair of=Desk 'offset_cm=[80,0,0]' face=toward
```

`offset_cm` is [forward, right, up] in the desk's own yaw frame. `face` is one of `toward`, `away`, `same`,
`none`, or `fixed` with `yaw_deg`. The chair is then dropped onto the floor unless you pass `drop=false`.

**Many copies: row, grid, circle, scatter**

```bash
film-ue op layout.array prefix=Stool shape=cylinder pattern=circle count=6 'center=[0,0,0]' radius_cm=120 face=center drop=true
film-ue op layout.array prefix=Lamp asset=/Game/Props/SM_Lamp pattern=row count=4 'start=[0,-300,0]' 'step_cm=[0,200,0]'
film-ue op layout.scatter prefix=Rock asset=/Game/Env/SM_Rock count=30 'region=[[-1000,-1000],[1000,1000]]' \
    min_dist_cm=150 seed=7 'avoid=["Path"]' 'scale_range=[0.5,1.2]'
film-ue op layout.remove prefix=Rock
```

Labels are `<prefix>_00`, `<prefix>_01`, and so on. The pattern owns its actors by the tag `fm.layout:<prefix>`:

- Re-running with a smaller count removes the extras.
- A hand-made `Rock_99` without the tag is never touched.
- Scatter is deterministic for a seed. If it places fewer than `count` (`placed` in the result), the region is
  full at that `min_dist_cm`.

**Tidy: align, distribute, snap**

```bash
film-ue op layout.align 'labels=["Book_00","Book_01","Book_02"]' axis=y to=max
film-ue op layout.distribute 'labels=["A","B","C","D"]' axis=x gap_cm=20
film-ue op layout.snap 'labels=["Desk","Chair"]' grid_cm=5 yaw_step_deg=15
film-ue op qa.overlaps 'ignore=["Floor"]'                # WP10: anything sunk into anything else?
```

**Group: tags and folders**

```bash
film-ue op level.tag 'labels=["Desk","Chair"]' 'add=["set:office"]'
film-ue op level.folder 'labels=["Desk","Chair"]' path=Office/Furniture
film-ue op level.material label=Desk material=/Game/M/MI_Oak
```

**Data layers** (World Partition levels only; elsewhere `unsupported`)

```bash
film-ue op level.layer_add name=Props_Night 'labels=["Lamp","Candle"]'   # makes /Game/DataLayers/Props_Night on first use
film-ue op level.layers
film-ue op level.layer_set name=Props_Night visible=false               # also loaded=, initially_visible=
film-ue op level.layer_remove name=Props_Night 'labels=["Lamp"]'
```

**A whole set from a spec**: write `office.yaml` (the full example is in `examples/unreal/scene/office.yaml`):

```yaml
kind: scene
version: 1
name: office
folder: Office
actors:
  - {label: Desk, shape: cube, size: [160, 80, 75], loc: [0, 0, 0], rot: {yaw: 90}, drop: true}
  - {label: Chair, asset: /Game/Props/SM_Chair, relative: {of: Desk, offset_cm: [80, 0, 0], face: toward}, drop: true}
  - {label: Key, class: RectLight, loc: [150, 120, 230], rot: {pitch: -30, yaw: -140}}
```

```bash
film-ue plan office.yaml          # or: film-ue op scene.plan spec=@office.yaml
film-ue apply office.yaml         # or: film-ue op scene.apply spec=@office.yaml
film-ue op scene.describe name=office > office-now.json    # the set as it is, as a spec (round trip)
film-ue op scene.list ; film-ue op scene.remove name=office
```

After `apply`, `remaining` must be `[]` and a second `plan` must be empty (`converged: true`).

- Moving an actor by hand and re-applying moves it back.
- With `prune: true`, actors tagged with the scene that the spec no longer lists are deleted.
- The planner is pure Python (`unreal/fmbridge/ops/_scene.py`: `validate`, `resolve`, `plan`, `from_state`). It
  takes the state from `scene.state`, so the client can plan offline.

## Op reference

`film-ue ops level.`, `film-ue ops layout.` and `film-ue ops scene.` give each op's signature and full docstring.

| op | what |
|---|---|
| `level.find` / `level.get` / `level.describe` | read actors and the level as JSON |
| `level.tag` / `level.folder` / `level.material` | group and dress (idempotent) |
| `level.new` / `level.open` / `level.save` / `level.actors` / `level.spawn` / `level.move` / `level.set` / `level.delete` / `level.bone` | the original level ops (signatures unchanged) |
| `layout.drop` | rest on what is under (bounds or trace) |
| `layout.relative` | offset in another actor's frame, facing it |
| `layout.array` / `layout.scatter` / `layout.remove` | row/grid/circle and Poisson-disk patterns that own their actors |
| `layout.align` / `layout.distribute` / `layout.snap` | tidy |
| `scene.state` / `scene.plan` / `scene.apply` / `scene.describe` / `scene.list` / `scene.remove` | the scene spec |

## Spec kind: `scene`

- **Schema:** `tools/filmtools/unreal/schemas/scene.schema.json`, generated from `_scene.SCHEMA`. A unit test fails
  when the two differ.
- **Rules beyond the schema** (`_scene.validate` checks these):
  - Labels are unique.
  - Exactly one of `asset`, `shape` or `class`.
  - `loc` or `relative`, not both.
  - `relative.of` names another actor of the scene, with no loops.
  - Rotations are dicts, never lists.
- **Units:**
  - Locations and offsets are in cm.
  - Rotations are in degrees.
  - `size` (shapes only) is in cm, applied as scale = size / 100.
  - `scale` is a factor or `[x, y, z]`.

## Gotchas

- **Bounds are axis-aligned and include every component.** A round table's box is bigger than its top, and a
  lamp with a long cable has a big box. Use `mode=trace` on `layout.drop` for those. For the fine check, use
  `qa.overlaps` / `qa.floating` (WP10).
- **Drop order matters.** `layout.drop` moves actors in the order given, and each rests on the current position of
  what is under it.
- **A support must be below the actor's centre.** A shelf above the actor is never "under" it. To put a cup on a
  high shelf, place the cup above the shelf first.
- **Re-spawning resets an actor.** `scene.apply` re-spawns an actor whose mesh or class changed (with
  `level.spawn replace=true`), which resets properties the spec does not list.
- **`hidden` in a spec is `bHidden`** ("Actor Hidden In Game"): it hides in renders, not in the editor viewport.
- **Pattern ownership is by tag.** Renaming a pattern's actor by hand keeps it owned. Removing its
  `fm.layout:<prefix>` tag releases it.

## API_NOTES (UE 5.8.4 source, verified on the source box)

| Python | engine | source |
|---|---|---|
| `EditorActorSubsystem.get_all_level_actors / spawn_actor_from_object / spawn_actor_from_class / destroy_actor` | UFUNCTION BlueprintCallable | Editor/UnrealEd/Public/Subsystems/EditorActorSubsystem.h:166, 218, 228, 236 |
| `Actor.get_actor_bounds(only_colliding)` → (origin, extent) | `GetActorBounds` UFUNCTION | Runtime/Engine/Classes/GameFramework/Actor.h:1610 |
| `Actor.set_actor_location / get_actor_location` | `K2_SetActorLocation` / `K2_GetActorLocation` | Actor.h:1585, 1568 |
| `Actor.set_actor_rotation / get_actor_rotation` | `K2_SetActorRotation` / `K2_GetActorRotation` | Actor.h:1650, 1589 |
| `Actor.set_actor_scale3d / get_actor_scale3d` | `SetActorScale3D` / `GetActorScale3D` | Actor.h:1706, 1710 |
| `Actor.get_component_by_class / get_components_by_class` | `GetComponentByClass` / `K2_GetComponentsByClass` | Actor.h:3792, 3807 |
| `Actor.get_folder_path / set_folder_path` | UFUNCTION "Editor Scripting \| Actor Editing" (editor builds only) | Actor.h:2757, 2782 |
| `Actor.get_actor_label / set_actor_label` | | Actor.h:2734, 2742 |
| editor property `tags` | `TArray<FName> Tags`, EditAnywhere BlueprintReadWrite | Actor.h:1344 |
| editor property `hidden` | `bHidden`, EditAnywhere | Actor.h:365 |
| `MeshComponent.set_material / get_num_materials`, `PrimitiveComponent.get_material` | | Components/MeshComponent.h:121, 118; Components/PrimitiveComponent.h:1566 |
| editor property `static_mesh` | `UStaticMeshComponent::StaticMesh` | Components/StaticMeshComponent.h:133 |
| `SystemLibrary.line_trace_single(world, start, end, TraceTypeQuery.TRACE_TYPE_QUERY1, complex, ignore, DrawDebugTrace.NONE, ignore_self)` → HitResult or None | `UKismetSystemLibrary::LineTraceSingle` | Runtime/Engine/Classes/Kismet/KismetSystemLibrary.h:1270 |
| `HitResult.to_tuple()`: (blocking_hit, initial_overlap, time, distance, location, impact_point, normal, …) | the `BreakHitResult` native break order | Runtime/Engine/Classes/Kismet/GameplayStatics.h:1078 |
| `MathLibrary.find_look_at_rotation` | `UKismetMathLibrary::FindLookAtRotation` | Runtime/Engine/Classes/Kismet/KismetMathLibrary.h:2300 |
| `DataLayerEditorSubsystem.get_all_data_layers / create_data_layer_instance / get_actors_from_data_layer / add_actors_to_data_layer / remove_actors_from_data_layer / set_data_layer_visibility / set_data_layer_is_loaded_in_editor / set_data_layer_is_initially_visible` | UFUNCTION BlueprintCallable | Editor/DataLayerEditor/Public/DataLayer/DataLayerEditorSubsystem.h:672, 612, 461, 255, 275, 497, 534, 650 |
| `DataLayerCreationParameters.data_layer_asset` | USTRUCT BlueprintType, BlueprintReadWrite | DataLayerEditorSubsystem.h:54, 63 |
| `DataLayerInstance.get_data_layer_short_name / is_visible / is_initially_visible / is_runtime` | UFUNCTION BlueprintCallable (`IsLoadedInEditor` is not exposed: loaded= is always applied) | Runtime/Engine/Public/WorldPartition/DataLayer/DataLayerInstance.h:169, 148, 145, 154 |
| `AssetTools.create_asset(name, dir, DataLayerAsset, DataLayerFactory())` | `UDataLayerFactory` (MinimalAPI, reflected) | Editor/DataLayerEditor/Public/DataLayer/DataLayerFactory.h:19 |
| `LevelEditorSubsystem.editor_play_simulate / editor_request_end_play / is_in_play_in_editor`, `UnrealEditorSubsystem.get_game_world` (layout.settle) | UFUNCTION BlueprintCallable, DevelopmentOnly | LevelEditorSubsystem.h:63, 81, 84; Editor/UnrealEd/Public/Subsystems/UnrealEditorSubsystem.h:52 |
| `PrimitiveComponent.set_simulate_physics`, `SceneComponent.is_simulating_physics / set_mobility` | UFUNCTION BlueprintCallable | Components/PrimitiveComponent.h:1661; Components/SceneComponent.h:690, 1296 |
| `LevelEditorSubsystem.new_level / load_level / save_current_level` | | Editor/LevelEditor/Public/LevelEditorSubsystem.h:147, 167, 174 |

Not yet proven on a running editor:

- **Trace order and channel.** The `to_tuple` order and `TRACE_TYPE_QUERY1` as the Visibility channel. The
  selftest compares the trace result against the bounds result.
- **Folder paths.** `get_folder_path` on a level that uses actor folder objects.

## Selftest

`unreal/fmbridge/selftest/layout.py` (`film-ue selftest layout`), about 1 minute. It needs a GPU for the two
stills; everything else runs without one. It:

- builds a floor, a table, a cup and chairs,
- checks drop by bounds and by trace against each other,
- checks rotated bounds,
- checks relative placement,
- runs each pattern twice to prove idempotency, and shrinks a circle,
- runs scatter with `qa.overlaps`,
- applies a scene spec, plans it again (empty), and describes it back (a no-op plan),
- moves an actor and re-applies to bring it back, then prunes,
- writes stills from above and from a camera.

## HANDOFF

- **Done:**
  - `ops/_util.py` (B01's helpers, used by level/layout/scene).
  - `ops/_layout.py` and `ops/_scene.py` (pure, unit-tested).
  - `level.*` additions, `layout.*`, `scene.*`.
  - The schema, the example and the selftest.
  - 21 unit tests (`tools/tests/test_ue_layout.py`).
- **Not done:**
  - Migrating look/seq/anim to `_util` (B01's second half).
  - World Partition region loading (B37). B44 covers data layers; B38 `layout.settle` is done but unproven:
    Simulate in an offscreen `-unattended` editor is the open question, and the selftest does not run it yet.
  - Foliage/PCG (B39).
  - Registering `scene` with WP11's kind registry once `ue-dx` lands: `_scene.plan(spec, state)` with state from
    `scene.state` is the whole contract.
