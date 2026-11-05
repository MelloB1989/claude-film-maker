# fakeunreal: the bridge's engine for unit tests

`sys.modules["unreal"]` in tests, so every op module imports and runs with no editor. Fixtures (from
`tools/tests/conftest.py`): `ue` is a fresh fake per test, and `fmb` is `fmbridge.ops` imported against it.

```python
from fakeunreal import run_op, drive

def test_light_converges(ue):
    run_op("look.light", label="Key", kind="rect", loc=[100, 0, 200])
    run_op("look.light", label="Key", kind="rect", loc=[100, 0, 250])
    assert len([a for a in ue.world.actors() if a.get_actor_label() == "Key"]) == 1
    assert ue.actor("Key").get_actor_location().z == 250
    assert ue.dialogs == []          # nothing would have opened a modal
```

## Faithful (behaves like the engine, enough to assert on)

- **Value types:** `Vector` (arithmetic, length, dot, cross, normal), `Rotator` (positional roll, pitch, yaw;
  forward/right/up vectors with the engine's matrix; `rotate_vector`), `LinearColor`, `Color` (positional B, G, R,
  A), `Transform`, `Quat` (storage only), `FrameNumber`, `FrameRate`, `FrameTime`, `Vector2D`, `IntPoint`,
  `SoftObjectPath`.
- **The level:** `ue.world` holds actors in spawn order. Actors have a label, location, rotation, scale, bounds
  (`get_actor_bounds` gives location plus a 50 cm half extent, set per actor with `ue.spawn(..., extent=)`), tags,
  hidden flags, attach parent, and components created with the actor. Actor classes: `Actor`, `StaticMeshActor`,
  `SkeletalMeshActor`, `CameraActor`, `CineCameraActor`, `PointLight`, `SpotLight`, `RectLight`,
  `DirectionalLight`, `SkyLight`, `ExponentialHeightFog`, `PostProcessVolume`.
- **Subsystems:**
  - `EditorActorSubsystem`: all actors, spawn from class or object, destroy, select, duplicate.
  - `UnrealEditorSubsystem`: the world.
  - `LevelEditorSubsystem`: new, load and save a level, viewport realtime.
  - `EditorLevelLibrary`.
  - `GameplayStatics.get_all_actors_of_class/with_tag`.
- **Content browser:** `ue.assets` maps a package path to an object. `EditorAssetLibrary` handles exist, load, save,
  delete, rename, duplicate, list, directories and metadata. `AssetTools.create_asset` makes the class or the
  factory's class, and refuses to overwrite (it records `("overwrite", path)` in `ue.dialogs`).
  `import_asset_tasks` makes a StaticMesh, SkeletalMesh, SoundWave or Texture2D by extension. `AssetRegistry`
  handles by path, by class and by object path.
- **Engine services:** `Paths` points under a temp project dir. `SystemLibrary.execute_console_command` appends to
  `ue.console`. `log*` appends to `ue.logs`. Slate tick callbacks run on `ue.tick(n)`. `ScopedEditorTransaction`
  appends to `ue.transactions`. `MathLibrary.find_look_at_rotation` is implemented.

## Stubbed (exists, records, returns a Stub)

- Any other `unreal.CamelCase` is a class. Names ending in `Actor`/`Volume` subclass `Actor`, names ending in
  `Component` subclass `SceneComponent`, and everything else subclasses `Object`.
- Any `Class.ALL_CAPS` is an enum value equal to its name.
- Any other `Class.method(...)`, `obj.method(...)` or `unreal.function(...)` is recorded in `ue.calls`. Read them
  with `ue.called("Class.method")` and set returns with `ue.stub("Class.method", value_or_function)`.
- Editor properties: `get_editor_property` and `set_editor_property` store values per object, and attributes read
  them too. Unset properties read as a Stub.

A Stub is truthy, iterates as empty and converts to 0. So code that branches on an engine result may take a branch
the engine would not. Stub what matters.

## Extending for your area

Add `fakeunreal/ext_<area>.py` with `def install(fake):`. It runs for every fresh fake. Add or replace classes
(`fake.LevelSequence = MyFakeSequence`) or default stubs. You own your ext file. Changes to `core.py` go through the
lead (agent-10).

## Auditing what the fake does not model (B58)

Run the suite with `FAKEUNREAL_AUDIT=<file>` to list every engine name the ops touched that no fake models: methods,
editor properties and static functions. Each is a name only the real engine can confirm, so check each one on the
source box (CamelCase, `b` prefix for bools). The 2026-11-05 run listed 50 names, all present in the 5.8.4 headers.
A misspelt property like the old `iris_pattern` would show up here.
