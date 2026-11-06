# Cloth (Chaos) on presenters' garments

Makes a skeletal-mesh garment simulate as Chaos cloth from a fabric preset, with its max distance painted by rule.
Gives MRQ renders the settle frames the cloth needs (pre-roll, or a cache), and measures whether the cloth is
sound and alive, so an "armour" tee fails a check before the operator sees it. The reasons and sources are in
[research/cloth-physics.md](research/cloth-physics.md).

Ops: `film-ue ops cloth`, plus `qa.cloth`.
Pure code (unit-tested, no engine):
- `unreal/fmbridge/clothkit/` (presets, paint, preroll);
- `unreal/fmbridge/qa/cloth.py` (the judge, fold detail, the gate file).

Engine side: the **FMCloth** editor plugin (`unreal/plugins/FMCloth`). In 5.8, clothing data, its weight maps and
the simulated positions are C++ only.

## Recipes

**Build the plugin (once per box, ~1 min).**
```bash
film-ue --box B plugin-build FMCloth      # as FabScript (docs/unreal/assets.md §6): builds against the restored engine
film-ue --box B editor restart
film-ue exec -c "print(hasattr(unreal, 'FMCloth'))"      # True
```
Without it:
- `cloth.setup` answers `unsupported` with this hint;
- `cloth.setup ... dry_run=true` still paints the garment's render vertices and returns the map stats;
- `cloth.describe`, `cloth.settings`, `cloth.render_check` and `cloth.presets` all work.

**Give a garment cloth.**
```bash
film-ue op cloth.describe label=Host                    # which garments simulate; "skinned_only" = armour
film-ue op cloth.setup label=Host component=Tee preset=cotton_tee dry_run=true   # map stats per zone, no writes
film-ue op cloth.setup label=Host component=Tee preset=cotton_tee
film-ue op cloth.describe label=Host component=Tee      # clothing[0].config as the solver has it, settings
```
Check:
- `setup` returns `readback_max_cm` equal to the preset's hem value (3.0 for cotton_tee) and `config.missing: []`.
- `describe` shows `simulating: true` and `solver.dynamic_particles > 0` after a tick.
- Tune with `overrides`, e.g. `'overrides={"zones": {"torso": {"to_cm": 4}}, "config": {"damping_coefficient": 0.08}}'`.
  A misspelt key is an error.

**After any respawn** (`host_swap`, `mh.dress`, a construction-script rerun): component settings live on the placed
actor, so run `film-ue op cloth.settings label=Host`. The clothing data stays on the mesh asset.

**Is it alive? (the check that would have caught round 4.)**
```bash
film-ue op qa.cloth label=Host component=Tee sequence=/Game/Reel/SEQ_Reel start=1000 end=1060
```
Pick frames with a gesture or a turn: "alive" is only judged when the body moves at least 2 cm.
- Pass: no fail issue, and `metrics.zones.hem.motion_cm >= 0.3`.
- Failures:
  - `cloth.no_clothing` / `cloth.dead`: armour.
  - `cloth.cold_start`: give it pre-roll.
  - `cloth.explosion` / `cloth.velocity_spike`: a teleport at a cut, or a collision shape inside the garment.

For penetration under simulation: `film-ue op cloth.preroll sequence=... frame=F 'labels=["Host"]'`, then
agent-02's `qa.clip` on that frame.

**Render with settled cloth.**
```bash
film-ue render plan reel.yaml --json > plan.json        # the chunks
film-ue op cloth.render_check "chunks=$(jq -c .chunks plan.json)" warmup_engine=0 warmup_render=32
```
- `ok: false` returns `warmup_engine` to set in the spec (`warmup_engine: N`), and per-chunk fixes ("render this cut
  from its start").
- The `final` preset holds 32 frames. cotton_tee needs 36 (1.0 s x 24 x 1.5 margin), so set `warmup_engine: 4`.
  An overshirt needs 54, so set `warmup_engine: 22`. The preview/draft presets hold 8-16.
- Engine warm-up frames are cheap: no rendering.

**Deterministic cloth across chunks and re-renders (cache; experimental).**
```bash
film-ue op cloth.cache label=Host mode=record           # then render the shot once (draft is fine): records
film-ue op cloth.cache label=Host mode=play             # every later render of the shot plays the same cloth
film-ue op cloth.cache label=Host mode=off              # back to live simulation
```
Needs the ChaosCaching plugin. Record and play jobs must start on the same frame (one job per shot). Prove it first:
probe P-C5 (render.compare of two `play` renders: identical).

## Op reference (`film-ue describe cloth`)

| op | what |
|---|---|
| `cloth.presets` | presets with config, zones, settle time (offline) |
| `cloth.describe` | per garment: clothing data, config read back, settings, LOD, solver numbers; MetaHuman ChaosClothComponents |
| `cloth.setup` | clothing data on a section, rule-painted MaxDistance/Backstop, preset config, physics asset, component settings |
| `cloth.remove` | take the cloth off a section (an A/B baseline) |
| `cloth.settings` | teleport 50 cm/45° + reset, no env collision, wait for the cloth task, bind to leader |
| `cloth.preroll` ~ | reset the cloth, then hold or play N frames before a frame (live level) |
| `cloth.render_check` | a render plan's chunks vs the settle frames the cloth needs; the warm-up to set |
| `cloth.cache` | a Chaos Cache Manager per character: record / play / off |
| `qa.cloth` ~ | two passes (skinned vs simulated) and the judge: sound + alive |

The pure functions:
- `clothkit.paint.bone_segments / assign / paint / check_maps`;
- `clothkit.preroll.need_frames / check_chunks / live_steps`;
- `qa.cloth.judge / hem_mask / sample / fold_detail / chest_band / gate_numbers`.

## Presets

`cotton_tee`, `overshirt_light` and `trousers`: values and reasons in the research doc §3. Zones are by nearest bone
segment (rest pose). A `ramp` is one of:
- `fixed`;
- `height`: from the zone's top to its lowest vertex;
- `along`: out along the limb from the zone's root bone.

The fit's vertex colours (agent-02's `garment.fit`: R = ease cm / 5, G = pinned) pin vertices (G > 0.5) and cap the
max distance at ease + collision thickness. The backstop keeps the cloth from sinking more than ease - thickness.

## Gotchas

- **LOD 0 only.** Renders force it. A preview at LOD 1+ shows a skinned garment.
- **WPO "inflate" on a cloth garment is invisible to collision and fights the sim.** Remove it (agent-02's refit
  does).
- **Cut that moves a presenter = teleport.** The thresholds handle it, and the reset then needs settle frames. A
  camera-only cut must not reset.
- **Cloth dt is capped at MaxPhysicsDeltaTime (1/30 s).** At 24 fps a once-per-frame tick (editor, `qa.cloth`, engine
  warm-up) runs cloth ~20% slow. MRQ temporal samples do not (1/192 s). Probe P-C6.
- **Temporal samples sub-step cloth.** If renders twitch, lower `iteration_count`/`subdivision_count` before stiffness
  (Epic staff).
- **MetaHuman outfits** simulate on a `ChaosClothComponent` (listed by `cloth.describe` as `cloth_components`). The
  sim mesh is stripped only in preview builds (no face DNA).
- **The weighted config values (bending, edge, area, tethers, anim drive, drag, lift) cannot be written on the asset
  from Python in 5.8.4** (`FChaosClothWeightedValue` has no Python type: round 5). `cloth.setup` and `cloth.settings`
  set them on the running simulation through the Chaos clothing interactor (`config.interactor` in the result). They
  are lost when the component is re-created, so run `cloth.settings` after any respawn. `mass_mode` stays the
  engine's default, Density.
- **`qa.cloth` changes the max distance scale while it runs** and restores it. Do not run it during a render.

## API_NOTES

All checked on the UE 5.8.4 source box (`/srv/ue-src/UnrealEngine-5.8.4`, 2026-11-06), except the Python return
shapes (GPU probes).

| API | where | used by | verified |
|---|---|---|---|
| `SkeletalMeshComponent` UPROPERTYs `bAllowClothActors`, `bDisableClothSimulation`, `bCollideWithEnvironment`, `bResetAfterTeleport`, `bWaitForParallelClothTask`, `ClothBlendWeight`, `TeleportDistanceThreshold`/`TeleportRotationThreshold` (BlueprintGetter/Setter) | Runtime/Engine/Classes/Components/SkeletalMeshComponent.h:761-830, 970-977, 1628-1637 | settings, setup | ✓ |
| `Get/SetClothMaxDistanceScale`, `ForceClothNextUpdateTeleport(AndReset)`, `Suspend/ResumeClothingSimulation`, `IsClothingSimulationSuspended`, `BindClothToLeaderPoseComponent`, `RecreateClothingActors`, `GetClothingSimulationInteractor(Name=None)` (BlueprintCallable) | SkeletalMeshComponent.h:1383-1426, 1686-1687, 2556-2557 | all | ✓ |
| `UClothingSimulationInteractor` `GetNumCloths/DynamicParticles/KinematicParticles/Iterations/Substeps`, `GetSimulationTime` | Runtime/ClothingSystemRuntimeInterface/Public/ClothingSimulationInteractor.h:134-160 | describe | ✓ |
| `USkeletalMesh.MeshClothingAssets` (VisibleAnywhere, BlueprintGetter) | Engine/SkeletalMesh.h:2296 | describe | ✓ |
| `UClothingAssetCommon.PhysicsAsset` (EditAnywhere), `ClothConfigs` (VisibleAnywhere BlueprintReadOnly, Instanced) | ClothingSystemRuntimeCommon/Public/ClothingAsset.h:291-297 | setup | ✓ (Python write to the config objects' own EditAnywhere props: probe P-C1) |
| `UChaosClothConfig` / `UChaosClothSharedSimConfig` property names | Plugins/ChaosCloth/Source/ChaosCloth/Public/ChaosCloth/ChaosClothConfig.h:99-587 | presets | ✓ |
| C++ (FMCloth): `UClothingAssetFactory::CreateFromSkeletalMesh`, `FSkeletalMeshClothBuildParams`, `USkeletalMesh::AddClothingAsset`, `FSkeletalMeshClothingSystemUtilities::Assign/RemoveClothingFromSection`, `FClothLODDataCommon::PointWeightMaps`/`PhysicalMeshData`, `UClothingAssetCommon::ApplyParameterMasks`, `FScopedSkeletalMeshPostEditChange`, `GetCurrentClothingData_GameThread`, `FClothSimulData.ComponentRelativeTransform` | ClothingAssetFactory.h:58; SkeletalMesh.h:199-216, 2356; SkeletalMeshClothingSystemUtilities.h:17-20; ClothLODData.h:24-50; ClothingAsset.h:200, 325; SkeletalMeshTypes.h:259; SkeletalMeshComponent.h:1693; ClothingSystemRuntimeTypes.h:14-40; SkeletalRenderGPUSkin.cpp:1172 | FMCloth | ✓ read; compile = probe P-C1 |
| `ChaosClothComponent` `GetAsset`, `IsSimulationEnabled`, `IsSimulationSuspended`, `TeleportDistanceThreshold` | Plugins/ChaosClothAsset/.../ClothComponent.h:102, 159-171, 507 | describe | ✓ |
| `AChaosCacheManager` `CacheMode` (ECacheMode None/Play/Record), `CacheCollection` (EditInstanceOnly), `StartMode`, `FindOrAddObservedComponent`; `UChaosCacheCollection`; `UCacheCollectionFactory` | Plugins/Experimental/ChaosCaching/.../CacheManagerActor.h:24-30, 192-238, 333-334; CacheCollection.h:11-12 | cache | ✓ read; behaviour = probe P-C5 |
| Skeletal-mesh cloth cache adapter | Plugins/ChaosCloth/Source/ChaosCloth/Private/ChaosCloth/SkeletalMeshComponentCacheAdapter.h:14 | cache | ✓ |
| `SkinnedMeshComponent` `GetNumBones`, `GetBoneName`, `GetParentBone`, `GetRefPoseTransform` | SkinnedMeshComponent.h:1143-1165, 1262-1263, 2052-2053 | bones | ✓ |
| `KismetMathLibrary::ComposeTransforms` | Kismet/KismetMathLibrary.h:3957 | bones | ✓ |
| Geometry Script `CopyMeshFromSkeletalMesh`, `GetMeshPerVertexColors`, `ConvertColorListToArray` | GeometryScripting/.../MeshAssetFunctions.h:408-416; MeshVertexColorFunctions.h:172; ListUtilityFunctions.h:293 | setup (colours, dry run) | ✓ (colour space: probe P-C2) |
| `UChaosClothingInteractor` (per cloth, via `ClothingSimulationInteractor.GetClothingInteractor(name)`): `SetMaterialLinear(edge, bending, area)`, `SetLongRangeAttachmentLinear(tether_stiffness, tether_scale)`, `SetAnimDriveLinear(stiffness)`, `SetAerodynamics(drag, lift, wind)` (BlueprintCallable; floats, no struct) | Plugins/ChaosCloth/Source/ChaosCloth/Public/ChaosCloth/ChaosClothingSimulationInteractor.h:41-84; ClothingSimulationInteractor.h:164 | setup, settings (round 5: the weighted config values cannot be written on the asset from Python: FChaosClothWeightedValue and EClothMassMode have no Python type on the box) | ✓ |
| Python types `ChaosClothWeightedValue` (low, high), `ClothMassMode` (EClothMassMode: UNIFORM_MASS/TOTAL_MASS/DENSITY), `GeometryScriptCopyMeshFromAssetOptions`, `GeometryScript_AssetUtils` (ScriptName of the static mesh functions library), `ChaosCacheManager`, `ChaosCacheCollection` | ChaosClothConfig.h:12; ClothingSystemRuntimeCommon/Public/ClothConfig.h:16; GeometryScripting/.../MeshAssetFunctions.h:56, 230; CacheManagerActor.h:187-188; CacheCollection.h:11-12 | setup, cache | ✓ |
| cloth dt cap `Min(dt, MaxPhysicsDelta)`, teleport above 1.5x (`p.Cloth.MaxDeltaTimeTeleportMultiplier`) | Runtime/ClothingSystemRuntimeCommon/Private/ClothingSimulation.cpp:17, 166-173 | docs | ✓ |
| MetaHuman build keeps the outfit sim mesh (preview strips it) | Plugins/MetaHuman/MetaHumanCharacter/.../MetaHumanDefaultEditorPipelineBase.cpp:455, 499 | docs | ✓ |

## Selftest

None yet: the cloth ops need a garment on a MetaHuman and the FMCloth plugin. The round-5 GPU probes in the film
plan (`films/host-studio/reel/r5/cloth.md`) are the acceptance test. They become `selftest/cloth.py` once they pass.

## HANDOFF

agent-08, 2026-11-06, branch `fleet/agent-08/r5-cloth`.
- **Done:**
  - clothkit, qa.cloth (judge, fold detail, gate file), the ops, the FMCloth plugin source;
  - fakes and tests (`tests/test_ue_cloth*.py`);
  - this doc and the research doc.
- **Unproven until the GPU session (probes P-C0..P-C7 in the film plan):**
  - the plugin compiles;
  - Python can write the config objects;
  - `SimulatedPositions` matches the skinned pose at scale 0;
  - the colour space;
  - caching in MRQ;
  - the 24 fps dt effect.
