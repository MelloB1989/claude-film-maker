# Research: cloth and body physics for MetaHuman presenters (UE 5.8, Chaos, MRQ)

Round 5, track T3b (agent-08), 2026-11-06. The operator, on round 4's cut: *"his chest still looks like he wore some
heavy armor inside"*. In round 3, her overshirt changed between a full-shot render and a chunk that started
mid-shot. This doc covers why it happened, what Epic and practitioners do, the knobs, the traps, and how we now
verify it automatically. The tools are in [../cloth.md](../cloth.md).

Trust labels:
- **[src]**: UE 5.8.4 source, read on the source box (`/srv/ue-src/UnrealEngine-5.8.4`, file:line).
- **[epic-docs]**: dev.epicgames.com.
- **[epic-forum]**: Epic staff or release notes.
- **[report]**: vendor or forum report.
- **[ours]**: our inference; a probe tests it.

The raw notes (487 lines, every claim with a URL) are in agent-08's `/work/research/cloth-notes.md`. This doc keeps
what matters to us.

## 1. Root causes of our failure

1. **His tee never simulated.** No check measured whether it did.
   - The tee is a MetaHuman default garment drawn as a skinned mesh. A skinned mesh with no clothing data moves
     rigidly with its bones. That is the "armour".
   - Round 4 then pushed it outward with a World Position Offset "inflate" and a neck patch (ClothOp4/patch3). That
     made the surface smooth and thick, and the WPO is invisible to cloth collision.
   - No gate asked "does the hem move relative to the body?". Our numeric gates (clip pixels, silhouette %) passed a
     garment with zero cloth motion.
   - **Fix:**
     - agent-02 removes the inflate and refits the tee with real ease.
     - `cloth.setup` gives it Chaos cloth.
     - `qa.cloth` fails `cloth.no_clothing` and `cloth.dead`.
     - The gate fails `garment.cloth_alive < 0.30 cm` (round 4 = 0.0).
2. **Default MetaHuman outfits keep their sim mesh only in a full build.**
   - The pipeline sets `bStripSimMesh = !Character->HasFaceDNA()` for the preview path and `false` for the full build
     [src] `Plugins/MetaHuman/MetaHumanCharacter/Source/MetaHumanDefaultEditorPipeline/Private/MetaHumanDefaultEditorPipelineBase.cpp:455,499`.
   - MetaHuman Crowd always strips it [src] `MetaHumanCrowdOutfitEditorPipeline.cpp:417`.
   - A Chaos Outfit simulates on its own `ChaosClothComponent`, not on the skeletal mesh. `cloth.describe` now lists
     both. Whether his default outfit's cloth component exists and is enabled is GPU probe **P-C0**.
3. **Live cloth in MRQ is history-dependent.**
   - At a render start, or after a teleport-and-reset, every particle starts at its skinned position and falls into
     its drape over ~0.5-1.5 s.
   - A chunk that starts mid-shot without play-through warm-up renders that fall. Her round-3 overshirt hung open at
     the shoulder (docs/unreal/render.md, P6).
   - `render.job` fixed mid-shot chunks with the camera-cut warm-up. A shot rendered from its first frame relies only
     on the warm-up hold:
     - The `final` preset holds 32 frames (`warmup_render`).
     - `preview`/`draft` hold 8-16 frames: not enough for an overshirt (54 frames with margin).
     - `cloth.render_check` now says so, with the fix.
4. **The cloth time step is capped at `MaxPhysicsDeltaTime` (default 1/30 s).**
   - `FillDeltaSeconds`: `DeltaSeconds = Min(InDeltaSeconds, InMaxPhysicsDelta)` [src]
     `Source/Runtime/ClothingSystemRuntimeCommon/Private/ClothingSimulation.cpp:166-168`. At 24 fps (0.0417 s) a
     cloth step is clamped to 0.0333 s, so cloth that ticks once per frame runs ~20% slow.
   - It teleports when dt > 1.5 x the cap (`p.Cloth.MaxDeltaTimeTeleportMultiplier`, :17, :173), which is 0.05 s.
     24 fps is under that; 20 fps would teleport every frame.
   - Affected: editor previews, engine warm-up frames and the `qa.cloth` live run.
   - Not affected: MRQ renders with 8 temporal samples, which tick at 1/192 s. So a live check and a render differ
     slightly. Probe **P-C6** measures it; the fix if needed is `MaxPhysicsDeltaTime 0.05`.

## 2. The correct pipeline (what Epic and practitioners do)

**Authoring.**
- 5.8 calls Chaos cloth production-ready. The forward path is the **Cloth Asset** (Dataflow graph), bound either to
  the skeletal mesh as clothing data (5.7+) or to a Chaos Cloth Component. [epic-forum] 5.7/5.8 release notes
- Legacy skeletal-mesh clothing data (Create Clothing Data from Section, then the paint tool) still works. 5.8 adds a
  converter from it to a Cloth Asset graph.
- **Scripting:** Epic staff (Feb 2026, 5.7): "There is no Python integration or scripting available yet" for cloth
  authoring [epic-forum]. On 5.8.4 we confirmed [src]:
  - `UClothingAssetCommon::LodData` is a bare `UPROPERTY()` (`ClothingAsset.h:324-325`), so Python cannot reach the
    weight maps.
  - `UClothingAssetFactory::CreateFromSkeletalMesh` (`ClothingAssetFactory.h:58`) and
    `FSkeletalMeshClothingSystemUtilities::AssignClothingToSection` (`SkeletalMeshClothingSystemUtilities.h:17`) are
    plain C++.
  - `GetCurrentClothingData_GameThread` (`SkeletalMeshComponent.h:1693`) is C++ only.
- 5.8 ships experimental **AI toolsets** that are reachable from Python through
  `unreal.ToolsetRegistry.execute_tool(toolset, tool, json)` (BlueprintCallable, `UToolsetRegistry.h:45-47`):
  - `ChaosClothAssetToolset`: `CreateClothingAsset`, `AssignClothingToSection`, `ConvertClothingAssetCommonToChaosClothAsset`.
  - `DataflowAgent`: `CreateGraph`, `AddNode`, `UpdateNode`, `ConnectNodePins`, ...
  - `UpdateNode` sets any node property from JSON (no edit-flag filter: `DataflowAgentToolset.cpp ApplyJsonToNode`),
    including a `WeightMap` node's `VertexWeights`. But those are per **3D sim vertex** after the importer welds 2D
    patterns (`SkeletalMeshImportNode.cpp:23-35, 99`). The order is internal, so per-vertex maps cannot be written
    reliably from outside.
- **We therefore use the legacy skeletal-mesh path through a 200-line C++ editor plugin (`FMCloth`)** that wraps
  exactly those calls, and keep the rules in Python. Same pattern as FabScript. The Dataflow path via the toolsets
  is the documented alternative, listed in §6.

**Collision.**
- The garment collides with the character's **Physics Asset** (capsules, spheres, tapered capsules) given when the
  clothing data is made (`FSkeletalMeshClothBuildParams.PhysicsAsset`, `SkeletalMesh.h:199-216`) [src].
- MetaHuman body physics assets have gaps at the neck and shoulders [report]. So pin the collar and shoulders
  (max distance 0) rather than trusting capsules there.
- Never let a simulated physics body (RigidBody/Physics Control) share the cloth's collision asset [report].
- A backstop (a sphere behind the skinned surface) is cheaper and more robust than capsules for tight garments
  [epic-docs]. We paint it from the fit's measured ease.

**Painting.**
- Max Distance 0 = kinematic: the particle follows the skinning [epic-docs]. A presenter's tee is anchored at the
  collar and shoulder seams, with a few cm toward the hem and the sleeve ends. Trousers are anchored at the
  waistband.
- `clothkit.paint` paints this by rule (nearest bone segment, a ramp per zone), and pins and caps it with agent-02's
  fit colours (G = pinned, R = ease/5 cm).

**Rendering.**
- Temporal samples sub-step the cloth ("equivalent to multiplying the solver substeps"). Over-constrained cloth then
  twitches. Fix: lower iterations and substeps first, then stiffness [epic-forum, Kriss Gossart, Nov 2025].
- "Caching the simulation is the only way to make TAA work with cloth" [epic-forum, Alex McAdams].
- MRQ's game overrides force `p.ChaosCloth.UseTimeStepSmoothing 0` (docs/unreal/render.md, `MoviePipelineGameOverrideSetting.cpp:150-170`) [src].
- Warm-up [epic-docs, MoviePipelineAntiAliasingSetting]:
  - Without `use_camera_cut_for_warm_up`, MRQ holds the first frame for the warm-up count. The cloth settles but
    arrives without momentum.
  - With it, MRQ plays the camera cut's frames before the range.
- **Teleports:** `TeleportDistanceThreshold`/`TeleportRotationThreshold` (0 = off) plus `bResetAfterTeleport`
  (`SkeletalMeshComponent.h:829-830, 1628-1637`) [src]. A cut that re-places a presenter must teleport-and-reset,
  then settle. A cut where only the camera moves must not.
- **Caching:** Chaos Cache has a skeletal-mesh cloth adapter (`Plugins/ChaosCloth/.../SkeletalMeshComponentCacheAdapter.h`)
  [src], driven by `AChaosCacheManager`. It is BlueprintCallable: `FindOrAddObservedComponent`, `Start`, `Stop`,
  `SetCacheCollection`; modes Record/Play/Static Pose (`CacheManagerActor.h:24-30, 263-417`). The plugin is
  experimental and off by default.
  - Reports up to 5.6.1 say MRQ re-simulated cached cloth. A 5.8.1 report says Take Recorder caching broke Sequencer
    bindings [report].
  - Probe **P-C5** before relying on it.

**Body physics / secondary motion** (practical for presenters).
- Most aliveness comes from the performance plus cloth.
- For danglers (earrings, lanyards, a ponytail guide) use AnimDynamics or one RigidBody node in the post-process
  AnimBP [epic-docs]. Reset its dynamics at hard cuts, as for cloth.
- Physics Control (production-ready in 5.8) is overkill for a talking presenter.
- ML Deformer cloth/soft tissue is quasi-static (wrinkles, no swing) and needs ~5,000 settled poses per garment
  [epic-docs]. Not for us.
- 5.8's Control Rig Dynamics (particles for cosmetic secondary motion) is worth a later look [epic-forum].

## 3. Knobs and values (the presets)

`clothkit/presets.py`, Python names of `UChaosClothConfig`/`UChaosClothSharedSimConfig`, verified in
`Plugins/ChaosCloth/Source/ChaosCloth/Public/ChaosCloth/ChaosClothConfig.h` [src] (engine defaults in brackets):

| knob | cotton_tee | overshirt_light | trousers | why |
|---|---|---|---|---|
| `density` kg/m² [0.35] | 0.15 | 0.20 | 0.28 | fabric weights (jersey ~150 g/m², shirting ~200, chino ~280); Epic's own table gives cotton 0.2 |
| `bending_stiffness_weighted` [1.0] | 0.08 | 0.25 | 0.4 | 1.0 is card: no folds = armour |
| `edge_stiffness_weighted` [1.0] | 1.0 | 1.0 | 1.0 | stretch is held by the tethers |
| `tether_stiffness` / `tether_scale` [1/1] | 1 / 1.03 | 1 / 1.02 | 1 / 1.02 | geodesic tethers stop the hem stretching away |
| `damping_coefficient` [0.01] | 0.06 | 0.06 | 0.08 | calm presenter cloth, no buzz |
| `collision_thickness` cm [1.0] | 0.4 | 0.6 | 0.6 | fitted garments sit close |
| `friction_coefficient` [0.8] | 0.6 | 0.5 | 0.7 | |
| `linear_velocity_scale` / `angular_velocity_scale` [0.75] | 0.75 | 0.75 | 0.75 | Epic default |
| `fictitious_angular_scale` [1.0] | 0.5 | 0.5 | 0.3 | a quick turn flings the hem |
| `enable_linear_velocity_clamping` / `max_linear_velocity` [off / 1000] | on / 500 cm/s | on / 500 | on / 500 | a re-placed presenter cannot fling the cloth |
| `iteration_count` / `max_iteration_count` / `subdivision_count` [1/10/1] | 2 / 6 / 1 | same | same | MRQ temporal samples already sub-step: keep low |
| max distance: collar, shoulder | 0 | 0 | waist 0 | anchors |
| max distance: torso ramp (top to hem) | 0 to 3 cm | 0.3 to 6 cm | thigh 0 to 1, leg 1 to 3 | free at the hem |
| max distance: sleeve (shoulder to end) | 0 to 2 cm | 0 to 3 cm | | free at the sleeve end |
| settle time | 1.0 s | 1.5 s | 1.0 s | pre-roll = ceil(settle x fps x 1.5) |

Component settings (all garments): teleport 50 cm / 45°, reset after teleport, no environment collision,
`wait_for_parallel_cloth_task` on, cloth bound to the leader pose. The research recommends 50-100 cm / 45°.

## 4. Known pitfalls

- **Cloth is LOD 0 only** in our setup. A garment drawn at LOD 1+ is skinned. Renders force LOD 0 (MRQ game
  overrides); `cloth.describe` reports `drawn_lod` (from `forced_lod_model`: 0 = auto, N = LOD N-1).
- **Leader pose:** cloth on a follower component simulates in its own space. `BindClothToLeaderPoseComponent`
  (`SkeletalMeshComponent.h:1425-1426`) [src]. A respawn (host swap, `mh.dress`) re-creates components, which lose
  their settings: run `cloth.settings` after any respawn.
- **WPO inflate and cloth do not mix:** cloth collision sees the mesh, not the material offset. agent-02's refit
  gives real ease instead.
- **Character transform jumps at the render start upset cloth** (spawnables, or a level transform equal to frame 0)
  [report].
- **Self-collision** is expensive and a common jitter source. It is off in every preset.
- **Fit vertex colours:** byte colours come in through FBX. Whether Geometry Script returns them linear or sRGB is
  probe P-C2. `paint` reads R and G only.

## 5. How we verify automatically

- `qa.cloth` runs two passes over the same frames in the live level, reading the simulated particles through
  FMCloth:
  - **reference**: max distance scale 0, so the particles sit on the skinned pose;
  - **sim**: scale 1, reset and pre-rolled.
- D = sim - skinned is the cloth's own motion. `fmbridge/qa/cloth.py judge` checks:

| code | severity | rule (defaults) |
|---|---|---|
| `cloth.no_clothing` | fail | the garment has no clothing data (round 4) |
| `cloth.not_simulating` | fail | max abs D < 0.001 cm over every frame |
| `cloth.nan` | fail | a simulated vertex is NaN/Inf |
| `cloth.explosion` | fail | abs D > min(25 cm, max distance + 5 cm) |
| `cloth.velocity_spike` | fail | dD/dt > 120 cm/s |
| `cloth.dead` | fail | free-zone motion (p75 of the temporal std of D) < 0.15 cm while the body moves >= 2 cm |
| `cloth.stiff` | warn | < 0.30 cm |
| `cloth.cold_start` | fail | the p90 settle speed over the first 4 frames > 3 x the median later, > 0.2 cm/frame |
| `cloth.anchor_slip` | warn | pinned zones' abs D p95 > 0.3 cm (collar sliding into the neck) |
| `cloth.jitter` | warn | second difference of D p95 > 0.12 cm on still frames |
| `cloth.max_distance_exceeded` | warn | > 1% of vertex-frames beyond max distance + 1 cm |

- Penetration under simulation is agent-02's `qa.clip`, run after `cloth.preroll` on the same frames.
- Fold detail in the picture:
  - `qa/cloth.py fold_detail` is the RMS of a difference of Gaussians (σ 1.5 to 4 px) of linear luminance in the
    tee's chest band, over its mean.
  - The gate takes r5/r4 on the same frames.
- Gate v2 (agent-09) items:
  - `garment.cloth_alive >= 0.30 cm` (r4 0.0);
  - `garment.cloth_sound == 1` (r4 0);
  - `garment.cloth_detail_ratio >= 1.25` (r4 1.0).

## 6. Not done here (alternatives, follow-ups)

- **Dataflow Cloth Asset via the 5.8 AI toolsets.** Use it when we author outfits (Panel Cloth, MetaHuman outfit
  resizing). It needs ToolsetRegistry, DataflowAgent and ChaosClothAssetToolset enabled (experimental). Max Distance
  would then come from a WeightMap node with `TransferType` from a painted source, or Epic's vertex-colour import
  patch [epic-forum].
- **Bake to Alembic** (Marvelous/Houdini) for a hero shot: frame-exact by construction.
- **`temporal_sample_count 1` + 8-16 spatial samples** for cloth shots, as Epic staff suggest. Probe P-C7 A/Bs it
  against our `final` preset (8 temporal).

## Links

- UE 5.8 release notes: https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-8-release-notes
- UE 5.7 release notes: https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-7-release-notes?application_version=5.7
- Clothing tool: https://dev.epicgames.com/documentation/en-us/unreal-engine/clothing-tool-in-unreal-engine
- Panel Cloth editor: https://dev.epicgames.com/documentation/en-us/unreal-engine/panel-cloth-editor-overview
- UChaosClothConfig: https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/ChaosCloth/UChaosClothConfig
- Python SkeletalMeshComponent: https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SkeletalMeshComponent
- Python ChaosCacheManager: https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/ChaosCacheManager
- No cloth scripting (Epic staff): https://forums.unrealengine.com/t/how-to-streamline-and-automate-iterative-cloth-workflow-between-maya-and-unreal-proxy-render-mesh-pipeline/2704911
- Temporal samples and cloth (Epic staff): https://forums.unrealengine.com/t/cloth-simulation-renders-incorrect-with-taa/2687943
- Cache is the only TAA-safe way (Epic staff): https://forums.unrealengine.com/t/chas-cloth-mrq-temporal-aa-render-chaos-cloth-kinematic-collider-issues/2644455
- Cloth caching workflow: https://forums.unrealengine.com/t/tutorial-cloth-caching-workflow/1284842
- Cloth workflows for animated characters in Sequencer (community, 5.6): https://forums.unrealengine.com/t/community-tutorial-cloth-simulation-workflows-for-animated-characters-in-sequencer/2680832
- 5.8.1 caching binding report: https://forums.unrealengine.com/t/ue-5-8-1-chaos-caching-breaking-every-bindings-to-actors-in-level-sequence/2740321
- Render start upsets cloth: https://www.versluis.com/2025/06/how-to-stop-chaos-cloth-from-freaking-out-when-rendering/
- MetaHuman physics asset gaps: https://forums.unrealengine.com/t/ue-5-4-panel-cloth-metahumans-collisions-and-physics-assets/1833180
- ML cloth: https://dev.epicgames.com/documentation/en-us/unreal-engine/machine-learning-cloth-simulation-overview
- AnimDynamics: https://dev.epicgames.com/documentation/unreal-engine/animation-blueprint-animdynamics-in-unreal-engine
- RigidBody node: https://dev.epicgames.com/documentation/en-us/unreal-engine/animation-blueprint-rigid-body-in-unreal-engine
- Untangling Cloth (Baraff, Witkin, Kass 2003): https://graphics.pixar.com/library/UntanglingCloth/paper.pdf
