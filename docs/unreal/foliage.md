# Foliage and scatter (B39: `foliage.*`)

Grass, rocks, litter and trees scattered by code, the same for the same seed, as **foliage instances**: one
InstancedFoliage actor draws each mesh as a hierarchical instanced static mesh (thousands of instances, no actor
each). A scatter has a name (`prefix`) and owns its instances: re-running it converges (replaces exactly its own
instances, nothing else), a new seed or density replaces them, `foliage.remove` takes them away. PCG graphs run
with a seed and parameters on any actor with a PCG component.

The maths is `unreal/fmbridge/ops/_foliage.py` (pure, seeded, unit-tested; spacing is `_layout.poisson`).

## Recipes

**A lawn with rocks, clear of the table.**

```bash
film-ue op foliage.scatter prefix=Lawn seed=7 \
  'meshes=[{"mesh":"/Game/Env/SM_Grass","weight":4,"scale":[0.8,1.3],"tilt_deg":6},
           {"mesh":"/Game/Env/SM_Pebble","weight":1,"scale":[0.5,1.0],"z_offset_cm":-2}]' \
  'region={"rect":[[-1500,-1500],[1500,1500]]}' density_per_m2=6 exclude_actors='["Table"]' patchiness=0.4
```

Check: `placed == planned`, `dropped` is `{"no_ground": 0, "too_steep": 0}` (instances over nothing or too steep
are dropped and counted), `short_of_target` 0 (else the region is full at that spacing: lower `min_dist_cm`).
`foliage.describe prefix=Lawn` shows the stored count per mesh and `measured` (what the level holds now); they
must agree. A still from above: `cam.add label=Top 'loc=[0,0,4000]' 'rot_={"pitch":-90}' focal_mm=18` then
`look.still`.

**Regions:** `{"rect": [[x0, y0], [x1, y1]]}`, `{"circle": [cx, cy, r]}`, `{"ring": [cx, cy, r0, r1]}` (a path
around a fountain), `{"polygon": [[x, y], ...]}`. **Exclusions:** the same shapes in `exclude`, and actors'
footprints with `exclude_actors` (+ `exclude_margin_cm`, 30).

**How many:** `density_per_m2` (over the region's area) or `count`; spacing `min_dist_cm` (default
0.5 / sqrt(density) m: Poisson-disk, no clumps of overlapping instances); `patchiness` 0..1 with `patch_cm`
(the size of the clumps) thins by a seeded noise field so it reads natural.

**Per mesh:** `weight`, `scale` [lo, hi] (or one number), `height_jitter` [lo, hi] (Z only), `yaw` "random" |
[lo, hi] | degrees, `tilt_deg` (random lean), `z_offset_cm` (sink rocks), `align_to_normal` (lean with the slope).

**Ground:** `surface="trace"` (default) drops each instance onto the first surface below (Visibility channel,
complex collision; other scatters are not ground), between `trace_from_z_cm` and `trace_to_z_cm`;
`max_slope_deg` drops instances on steeper ground. `surface="flat"` puts them at `z_cm`.

**Rendering:** `cull_cm` [start, end] (fade/cull distances), `shadows`.

**Re-run, change, remove.** The same call again: `changed: false`. A new seed, density or mesh list: the scatter's
old instances go and the new ones come (a mesh dropped from the list loses its foliage type).
`force=true` rewrites anyway (after the ground moved). `foliage.remove prefix=Lawn`.

**PCG.** `foliage.pcg label=PCG_Forest graph=/Game/PCG/PG_Forest seed=3 'params={"Density":0.6,"Tree":"/Game/Env/SM_Pine"}'`
sets the graph, the seed and graph parameters (bool, int, float, string, [x, y, z], asset path) on an actor with a
PCG component (a PCG Volume placed in the level, or a Blueprint with a PCGComponent), generates and waits until it
has (`timeout_s`), and counts the instances it made. With `loc` (+ `extent_cm`) it makes a PCG Volume first; if a
script-spawned volume has no bounds the op says so (`unsupported`): place one volume by hand and reuse it.
`foliage.pcg_clear label=... delete=true`.

## Op reference

| op | does |
|---|---|
| `foliage.scatter` | a seeded scatter as foliage instances; converges per prefix (multi-tick: traces yield every 500) |
| `foliage.describe` | every scatter (or one): arguments, seed, foliage types, stored counts, and `measured` per mesh |
| `foliage.remove` | a scatter's instances and foliage types |
| `foliage.pcg` | run a PCG graph with a seed and parameters, wait, count (multi-tick, experimental) |
| `foliage.pcg_clear` | clear (and delete) a PCG actor's output |

## Gotchas

- **One foliage type per mesh per scatter** (`/Game/_Foliage/<prefix>/FT_<prefix>_<i>_<mesh>`): that is how a
  scatter knows its own instances. Two scatters may use the same mesh and never touch each other.
- **Traces need collision.** Ground without collision (a decal, a mesh with collision off) is not found: those
  instances come back in `dropped.no_ground`. Grass meshes usually have no collision, so scatters do not stack.
- **Convergence trusts the stored hash** plus a measured count per mesh. If something moved the ground, pass
  `force=true`.
- **World Partition levels** keep foliage in partition actors; AddInstances handles it; `measured` sums every
  InstancedFoliage actor.
- **PCG generation is asynchronous**: `foliage.pcg` polls the component's `generated` flag between ticks.

## API_NOTES

Verified on the UE 5.8.4 source box.

| API (Python) | source | verified |
|---|---|---|
| `InstancedFoliageActor.add_instances(world, foliage_type, transforms)`, `remove_all_instances(world, foliage_type)` (static, editor) | Runtime/Foliage/Public/InstancedFoliageActor.h:286,289 | yes |
| `FoliageType_InstancedStaticMesh.mesh` | Runtime/Foliage/Public/FoliageType_InstancedStaticMesh.h:18 | yes |
| `FoliageType.cull_distance` (Int32Interval `min`/`max`), `cast_shadow` | Runtime/Foliage/Public/FoliageType.h:296,304; CoreUObject/Public/UObject/NoExportTypes.h:2486,2490 | yes |
| `FoliageType_InstancedStaticMeshFactory` (create_asset) | Editor/FoliageEdit/Private/FoliageTypeFactory.h:24 | yes |
| `InstancedStaticMeshComponent.get_instance_count`, `get_instance_transform`, `static_mesh` | Engine/Classes/Components/InstancedStaticMeshComponent.h:435,338 | yes |
| `SystemLibrary.line_trace_single` (bool + out hit: Python returns the hit or None), `HitResult.to_tuple` (BreakHitResult order) | Engine/Classes/Kismet/KismetSystemLibrary.h:1270 | yes |
| `EditorAssetLibrary.list_assets`, `does_directory_exist`, `delete_directory`, `delete_asset`, `set_metadata_tag`, `get_metadata_tag` | Plugins/Editor/EditorScriptingUtilities/.../EditorAssetLibrary.h:328,301,156,144,385,376 | yes |
| `PCGVolume.pcg_component` | Plugins/PCG/Source/PCG/Public/PCGVolume.h:29 | yes |
| `PCGComponent.set_graph`, `get_graph`, `generate_local(force)`, `cleanup_local(remove_components)`, `seed`, `generated`, `graph_instance` | Plugins/PCG/Source/PCG/Public/PCGComponent.h:194,187,221,232,314,403,626 | yes |
| `PCGGraphParametersHelpers.set_bool/int32/double/string/vector/soft_object_parameter` | Plugins/PCG/Source/PCG/Public/Helpers/PCGGraphParametersHelpers.h:104-146 | yes |
| `PCGGraphFactory` (the selftest's empty graph) | Plugins/PCG/Source/PCGEditor/Private/PCGGraphFactory.h:13 | yes |
| `AssetToolsHelpers.get_asset_tools().create_asset` (foliage types, the selftest's graph) | Developer/AssetTools/Public/IAssetTools.h:898 | yes |
| `PCGGraph` (asset class) | Plugins/PCG/Source/PCG/Public/PCGGraph.h:332 | yes |
| `SoftObjectPath` (asset-path graph parameters) | CoreUObject/Public/UObject/NoExportTypes.h (FSoftObjectPath) | yes |
| `get_editor_subsystem` (UnrealEditorSubsystem world, EditorActorSubsystem) | Editor/UnrealEd/Public/Subsystems/EditorSubsystemBlueprintLibrary.h:20 | yes |
| PCG plugin enabled by default | Plugins/PCG/PCG.uplugin:13 | yes |
| volumes spawned by `spawn_actor_from_class` go through actor factories (TryPlacingActorFromObject) | Editor/UnrealEd/Private/Subsystems/EditorActorSubsystem.cpp:139 | yes (brush not verified) |

## Selftest

`film-ue selftest foliage` (`unreal/fmbridge/selftest/foliage.py`), about 30 s, no GPU needed (one still when
there is one), engine basic shapes only. It proves placement equals the plan, instances sit on the floor (z read
back within 1 cm) and follow a 30° ramp (and lean with it), a slope limit drops them, convergence and replacement,
isolation between scatters, describe = measured, removal, and the PCG plumbing with a graph made by code. A dry run
on the fake engine is `tools/tests/test_ue_foliage.py::test_selftest_runs_on_the_fake`.

## HANDOFF

Done (agent-11, 2026-11-05, branch `fleet/agent-11/ue-foliage`): ops, planner, fake, tests, selftest, this doc.
Not run in a real editor yet. Tomorrow: `film-ue selftest foliage`. Likely issues: `get_instance_transform`'s
Python return shape (the selftest accepts a transform or a tuple); whether a script-spawned PCG Volume gets a brush
(the selftest notes it); trace channel on meshes without Visibility collision.
