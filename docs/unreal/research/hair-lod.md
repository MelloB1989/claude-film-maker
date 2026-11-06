# Hair that keeps its length in every shot: groom LOD, Auto LOD, LODSync, MRQ (UE 5.8)

Round 5, track T4 (agent-09). The operator's note on round 4's 65 s cut: "at 01:00 her hair again becomes short!"
01:00 is the S17 -> S18 cut (f1440), S18 being the wide. Round 3 had the same pop at the end of S17's crane out,
and we "fixed" it with a LOD-0 pin. This page covers why the pin was not enough, what Epic's pipeline does, and the
tools that now lock the hair and check it.

Labels: **[SRC]** read in the UE 5.8.4 source (`Engine/Plugins/Runtime/HairStrands`, `Engine/Source/Runtime/...`,
`Engine/Plugins/MetaHuman`), **[DOC]** Epic documentation, **[FORUM]** Epic forum reports, **[INF]** our inference.

## 1. Root cause of OUR failure

There are four layers, and round 4 controlled only the first.

1. **The discrete LOD index.** The MetaHuman's `LODSync` component drives its grooms: Face and Body are `Drive`, and
   Hair, Eyebrows, Eyelashes, Mustache, Beard and Peachfuzz are `Passive`, listed BY NAME in `ComponentsToSync`
   ([SRC] `MetaHumanCharacterEditorActor.cpp:141-150`; [DOC] LODSync component). LODSync resolves the names to
   live components only on register (`LODSyncComponent.cpp InitializeSyncComponents`, called from `OnRegister`;
   there is no `PostEditChange`). A groom whose name is not in that list, or that was re-created under another
   name, never gets the forced LOD. It then picks its LOD from screen size
   (`GroomManager.cpp GetHairInstanceLODIndex`). On a MetaHuman groom, LOD 0-1 are strands, the mid LODs are cards,
   and the lowest are a helmet mesh ([DOC] platform support and LOD specifications). Long-hair cards end higher
   than the strands, and round 3 saw exactly that: "shorter green hair, the cards, from f1217".
   - Round 4's gate item g read `LODSync.forced_lod == 0` and the skeletal meshes, but **never read a groom**.
2. **Auto LOD (the one that bit S18).** `r.HairStrands.LODMode` defaults to **1 = Auto** ([SRC]
   `RenderUtils.cpp:2019`). A groom asset's `LODMode` is `Default` (follow that cvar), `Manual` or `Auto`
   (`GroomAssetInterpolation.h EGroomLODMode`). In Auto, **even at a forced LOD 0** the groom draws
   `RestCurveCount x clamp(screen size + bias, 0, 1)` curves ([SRC] `GroomManager.cpp ComputeActiveCurveCount`,
   which runs whenever the LOD is a strands LOD and `bAutoLOD`). The global bias `r.HairStrands.AutoLOD.Bias`
   defaults to 0.1. Curves are shuffled at build time, so the thinning is uniform. Long hair's ends are already
   sparse, though, and they fade out first, so the hair reads SHORTER and thinner on a wide shot.
   - Screen size comes from the groom's bounds on the view (`ComputeBoundsScreenSize`), so it depends on framing
     and FOV, not on the output resolution [SRC]. S17 (medium) -> S18 (wide) is exactly that drop.
3. **When the mode is read.** `bAutoLOD` is copied once per groom in `UGroomComponent::InitResources`
   ([SRC] `GroomComponent.cpp:3045`), at register time. So `r.HairStrands.LODMode 0` in the MRQ job's console
   variables is too late for grooms that are already registered. Our round-3 fix 951adf24 did exactly that, and
   it never reached film/host-studio anyway (the finals' `r3/30-final.yaml` has no hair cvar). By contrast,
   `r.HairStrands.AutoLOD.Bias` is read every frame (`GetHairStrandsAutoLODBias()` in `ComputeActiveCurveCount`),
   and at 1.0 every curve is kept whatever the mode.
4. **MRQ's "Use LOD Zero"** sets only `r.ForceLOD 0`, `r.SkeletalMeshLODBias -10`, `r.ParticleLODBias -10` and
   foliage ([SRC] `MoviePipelineGameOverrideSetting.cpp:89-95`). It never touches hair ([DOC] MovieGraph
   `disable_lods` is the same).

Not the cause, but worth knowing:
- Hair **simulation reset at a cut**: a reset restarts from the rest pose and the hair settles over several
  frames. The settling shows only in the first frames of a shot, not as a whole-shot change. MRQ needs
  `render_warm_up_frames` for groom sim to settle ([FORUM] groom warm-up issue in MRQ). Our finals have 32
  warm-up frames from the shot start (`preroll: cut`).
- `hair_length_scale` overrides on the component really do shorten strands, and they can be keyed
  ([DOC] `SetHairLengthScale`). `groom.lock_check` lists any override.
- [FORUM] A copied or rebuilt MetaHuman BP loses its LODSync wiring: hair pops between bald and haired, and the
  fix is to recreate the LODSync component. Our version of this is the TRASH_ components left by a Blueprint
  re-instance.

Proven from our own files (numbers, no frames): `r3/30-final.yaml` cvars = `{r.SSS.Quality: 1, r.SSS.HalfRes: 0}`
(no hair cvar), and 951adf24 sits only on `fleet/agent-09/r3-hairlod`. The frames proof is probe P3 in the plan
(`films/host-studio/reel/r5/hair.md`).

## 2. The correct pipeline

1. Every MetaHuman in a shot: one live LODSync (no TRASH_), each visible groom's name in `components_to_sync`,
   `forced_lod = 0`, `use_cards = false`, the skeletal meshes `forced_lod_model = 1` (1-based: 1 = LOD 0).
2. Before the render world registers its grooms (that is, before MRQ starts its PIE world), set
   `r.HairStrands.LODMode 0`, `r.HairStrands.AutoLOD.Bias 1` and `r.HairStrands.UseCardsInsteadOfStrands 0`. Put
   the same three in the render spec's cvars (MRQ's console variables), and for durability in
   `DefaultEngine.ini [SystemSettings]`.
3. Render each shot with warm-up frames (`preroll: cut`, 32) so the hair simulation settles before the first kept
   frame.
4. Check:
   - `groom.lock_check` right before the render (the gate's `hair.lock`);
   - `qa.hair_continuity` in the editor at the cuts (`hair.cut_reach_pct`, `hair.pop_reach_pct`);
   - `film-qa hair` on the rendered frames.

## 3. Knobs and values

| knob | value | where | why |
|---|---|---|---|
| `LODSyncComponent.forced_lod` | 0 | each presenter | the LOD every synced component renders [SRC] |
| `LODSyncComponent.components_to_sync` | contains every visible groom's name (`ComponentSync(name, sync_option=PASSIVE)`) | each presenter | name-matched, resolved on register [SRC] |
| `GroomComponent.use_cards` | false | each groom | `bUseCards` forces cards/meshes [SRC] |
| `SkeletalMeshComponent.forced_lod_model` | 1 | Body/Face/garments | 1-based [DOC] |
| `r.HairStrands.LODMode` | 0 | editor before the render, spec, ini | Manual: discrete LODs, no curve thinning [SRC] |
| `r.HairStrands.AutoLOD.Bias` | 1.0 | spec + editor | read per frame; screen size + 1 clamps to all curves, even for an asset in Auto [SRC] |
| `r.HairStrands.UseCardsInsteadOfStrands` | 0 | spec | the global cards switch [SRC] |
| MRQ game overrides `use_lod_zero` | true | spec | meshes only; keep it, it does not cover hair |

Python names, checked against the 5.8.4 source and the 5.6 Python API: `LODSyncComponent.forced_lod / num_lods /
min_lod / components_to_sync / custom_lod_mapping / get_lod_sync_debug_text()`, `unreal.ComponentSync(name,
sync_option)`, `unreal.SyncOption.DRIVE|PASSIVE|DISABLED`, `GroomComponent.use_cards`, `GroomAsset.lod_mode /
auto_lod_bias / hair_groups_lod[g].lo_ds[l].geometry_type|visible|screen_size|curve_decimation` (`lo_ds` is UE's
snake case of `LODs`; the tool also tries `lods`). `UGroomComponent::SetForcedLOD/GetForcedLOD` are C++ only (not
UFUNCTIONs), so LODSync is the only Python route, and `get_lod_sync_debug_text()` (`"Hair : 0"` per resolved
component) is the only read-back of a groom's rendered LOD.

## 4. Known pitfalls

- A pin that lands on a `TRASH_*` component (a Blueprint re-instance) does nothing; `groom.lock` refuses then.
- A re-dress or respawn that re-creates the groom under a new name drops it out of LODSync. `groom.lock` adds the
  name back. LODSync only resolves names on register, so the editor's debug text shows the groom after a
  level.save + level.open, and the render's PIE world picks it up by itself.
- `r.HairStrands.LODMode` as a render cvar alone is too late (point 1.3). Set it before, or rely on the Bias.
- A groom asset whose own `LODMode` is `Auto` ignores the cvar; the Bias still covers it (`lock_check` notes it).
- `UseCardsInsteadOfStrands 1` hides any LOD that has no cards ([SRC] cvar help: "nothing will be displayed").
- Never toggle `r.HairStrands.Enable` per shot: grooms do not come back without re-creation ([FORUM]).

## 5. How to verify automatically

- `film-ue op groom.lock_check 'labels=["Host","Presenter"]'` returns pass, problems (each with its fix) and
  notes. The gate item `hair.lock` is its pass.
- `film-ue op qa.hair_continuity sequence=/Game/Reel/SEQ_Reel 'labels=["Presenter"]'` measures, at each cut, a
  groom-only depth capture through the cut's camera. Per frame it computes **reach**, how far the hair falls
  below the head in head units ((lowest hair row - head bone row) / (spine_05 row - head bone row)). Reach is
  zoom-free, so a close and a wide shot of the same hair read the same. The check FAILS on a reach change > 12%
  across a cut or > 8% frame to frame (`qa/hair.py THRESHOLDS`).
- `film-qa hair SPEC.json` is the same judge on rendered frames, using a dark-hair matte in a box per shot.
- `film-qa gate` is the review gate v2 (`qa/gate.py`). Each item is a number with a line, and a missing number
  fails. A waiver needs a reason and a name, and is refused on anything the operator complained about.

## Links

- [DOC] Controlling MetaHuman LODs: https://dev.epicgames.com/documentation/en-us/metahuman/controlling-metahuman-levels-of-detail-lods-in-unreal-engine
- [DOC] LODSync component: https://dev.epicgames.com/documentation/en-us/metahuman/lodsync-component-for-unreal-engine
- [DOC] MetaHuman LOD specifications: https://dev.epicgames.com/documentation/en-us/metahuman/platform-support-and-lod-specifications-for-metahumans
- [DOC] Setting up LOD for grooms: https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-level-of-detail-for-grooms-in-unreal-engine
- [DOC] Debugging grooms: https://dev.epicgames.com/documentation/en-us/unreal-engine/debugging-grooms-in-unreal-engine
- [DOC] Python: GroomComponent https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/GroomComponent?application_version=5.6 , LODSyncComponent https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/LODSyncComponent?application_version=5.6 , HairLODSettings https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/HairLODSettings?application_version=5.6 , GroomLODMode https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/GroomLODMode?application_version=5.6 , MoviePipelineGameOverrideSetting https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MoviePipelineGameOverrideSetting?application_version=5.6
- [DOC] UGroomComponent::SetForcedLOD (C++ only): https://dev.epicgames.com/documentation/unreal-engine/API/Plugins/HairStrandsCore/UGroomComponent/SetForcedLOD?application_version=5.3
- [DOC] SetHairLengthScale: https://dev.epicgames.com/documentation/unreal-engine/API/Plugins/HairStrandsCore/UGroomComponent/SetHairLengthScale?application_version=5.4
- [FORUM] Meta hair popping, LODs don't fix it: https://forums.unrealengine.com/t/meta-hair-popping-lods-dont-fix-it/2647244
- [FORUM] Groom AutoLOD in 5.4: https://forums.unrealengine.com/t/groom-autolod-not-working-in-5-4/1903209
- [FORUM] Fixing MetaHuman body LOD (recreate LODSync): https://forums.unrealengine.com/t/tutorial-how-to-fix-metahuman-body-mesh-lod-not-working/2053560
- [FORUM] Hair renders only when the camera is close: https://forums.unrealengine.com/t/metahuman-hairs-render-only-if-the-camera-is-close/481928
- [FORUM] Hair cards missing for some hairstyles: https://forums.unrealengine.com/t/hair-cards-not-available-for-some-hairstyle/243458
- [FORUM] Groom warm-up in MRQ: https://forums.unrealengine.com/t/groom-warm-up-issue-in-movie-render-queue/2659701
- [FORUM] Camera cuts blow hair around: https://forums.unrealengine.com/t/camera-cuts-causing-metahumans-hair-to-blow-all-over/793733
- [VENDOR] cvar wiki, r.HairStrands.LODMode: https://indxzero.github.io/ue544cvarwiki/articles/r.hairstrands.lodmode
- [SRC] UE 5.8.4: `HairStrandsCore/Private/GroomManager.cpp` (ComputeActiveCurveCount, GetHairInstanceLODIndex,
  r.HairStrands.AutoLOD.Bias, r.HairStrands.UseCardsInsteadOfStrands), `GroomComponent.cpp` (InitResources
  bAutoLOD, SetForcedLOD), `RenderCore/Private/RenderUtils.cpp` (r.HairStrands.LODMode = 1),
  `Engine/Private/Components/LODSyncComponent.cpp`, `MovieRenderPipelineCore/Private/MoviePipelineGameOverrideSetting.cpp`,
  `MetaHumanCharacterEditor/Private/MetaHumanCharacterEditorActor.cpp`.
