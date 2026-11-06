# Research: garment fit, clipping and the "armor" look (round 5, track T3a)

agent-02, 06 Nov 2026. What professionals and Epic do to put a garment on a MetaHuman so that it neither clips nor
reads as a rigid shell, why ours failed, and how the tools now check it. Cloth SIMULATION is T3b's
([cloth-physics.md](cloth-physics.md)); this page is the garment's shape, the body under it, and the measuring.

Trust: **T1** Epic docs / API reference, **T2** Epic staff, Epic tutorials and release posts, Blender official docs,
**T3** papers, **T4** forums and vendors (labelled where used). Engine: UE 5.8.4 Linux source build + the MetaHuman
plugin (not in the source tree: its APIs are checked against Epic's docs and listed as GPU probes).

## 1. What went wrong on the karma reel (our root causes)

The operator, round 4: *"his chest still looks like he wore some heavy armor inside"* and *"his shirt looks like it is
clipping at the neck a little"*. The tee was MetaHuman's default garment (`MI_WI_DefaultGarment`) with a material
World Position Offset: `FM_Inflate` 0.15 cm everywhere plus a neck patch (`FM_Neck` 0.75, `FM_Patch` 1.76 cm round
the throat), through Material Attributes (round 4's ClothOp4, `films/host-studio/reel/r3/DRESS.md`).

1. **The clip was the FACE mesh, not the body.** A MetaHuman's face (head) mesh runs ~10 cm below `neck_01`, to the
   clavicles; the visible neck skin is the head mesh, driven by the face rig and the body's post-process AnimBP
   correctives (RBF `*_corr` / `*_twist` joints) [22, T4; consistent with 6, 8 T1]. Epic's tee is fitted to the
   body, so the face's lower neck stood ~1.8 cm out through the front of the collar (measured round 4). We pushed the
   cloth out; the professional fixes are to fit the garment round the face as well, or shrink/hide the head skin
   under the collar (section 3).
2. **A WPO push is not a fit.** It moves every vertex along its normal by the same rule, so the garment becomes an
   even offset of the body: the gap that varies on real cloth (tight at the shoulders, loose at the waist and hem)
   is gone, which is the "padded armor" read. It does not change bounds, collision, cloth input or shadows unless
   told: with Virtual Shadow Maps a WPO material invalidates cached pages every frame and shadows clip at the old
   bounds unless *Max World Position Offset Displacement* is set [16, T1]; it writes motion vectors only with
   `r.Velocity.EnableVertexDeformation` [48, T4]. On a closed shell with split normals it can crack at seams.
   Round 4's broad neck term made the silhouette +15% (the orchestrator: "a mock-neck, the chest padded").
3. **No folds and no motion.** The default garment is a smooth skinned shell: no wrinkle normal detail of its own at
   the size it is seen, no cloth simulation, so it moves exactly with the body. Epic's garments get folds from the
   source (Marvelous Designer/CLO export with a baked 2K normal map [21, T1]) and motion from Chaos Cloth.
4. **Our gates measured clipping only.** `neck_px`, pair fractions and a ±2% silhouette passed a tee the operator
   saw at once was wrong: nothing measured ease, folds or motion. qa.garment_look (section 6) is that check.

## 2. The correct pipeline (what Epic does, 5.6+; valid in 5.8)

**Epic's route: Cloth Asset -> Outfit Asset -> Wardrobe Item** [1-6, 19, 20, T1; 9, T2 for 5.8].
- Source bodies: MetaHuman Character -> Export Tool -> Geometry Export -> "Full Body Skeletal Mesh"
  (`<body>_CombinedSkelMesh`) [5].
- Cloth Asset (`CA_`, template "USD Cloth"): `StaticMeshImport` (FBX render mesh, Import Sim Mesh off) or `USDImport`
  (Marvelous/CLO) -> `TransferSkinWeights` (Skeletal Mesh = the `_CombinedSkelMesh`, **Transfer Method = Closest Point
  on Surface**) -> `Remesh` LODs (render 50/30/10%) -> `ClothAssetTerminal` [4, 19, 20]. Epic advises importing the
  garment as a STATIC mesh and letting `TransferSkinWeights` skin it [19].
- Outfit Asset (`OA_`, template "Resizable Outfit"): Sized Outfit Source per size (Size Name, Source Asset, Source
  Body Parts); Num Resizing Interpolation Points 1500 (1000-2500) [3]; RBF warp from the source body to the target.
- Wardrobe Item (`WI_`, Principal Asset = the OA_, Pipeline = MetaHuman Outfit Pipeline), worn in MetaHuman Creator;
  the outfit pipeline carries the **Body Hidden Face Map** (5.6+) and **Head Hidden Face Map** (5.7+) [6, 8].
- Limits: resizing is editor-only [27, T2]; **MetaHuman Creator's assembly strips the sim mesh** (Epic staff, 5.8):
  to keep a simulated outfit, make a second outfit from the "Resizing Graph" template (Target Body = the character,
  Strip Sim Mesh = false) and put it on a Chaos Cloth Component [9, T2]. Morph targets on clothing asserted in 5.7.0
  [27].
- Epic's garments: a thickened render mesh driven by an optional single-sided sim mesh [2]; Marvelous Designer export
  "Thick", unified UVs, 2048 maps, Normal Map on, collar in "Trim_Fusible_Rigid" [21].

**For one film character (ours)** the resizing is not needed: fit the garment to *that* body. Two equivalent routes:
- **A, ours, in core (this round):** `garment.export` -> `film-ue garment-fit` (headless Blender on the box) ->
  `mh.import_garment` -> `mh.dress`, with the face in the collider. Works on the placed actor with leader pose (how
  the reel dresses him), keeps the garment's topology/UVs/materials, and needs no MetaHuman rebuild (round 3-4:
  rebuilds re-create components and dropped hair/garment state).
- **B, Epic's:** the tee as a `CA_`/`OA_`/`WI_` and a Head Hidden Face Map shrink band under the collar. The cleanest
  neck fix (the skin goes in, the cloth keeps its shape), but it needs a MetaHuman re-assembly and the Creator
  pipeline: GPU probe G5 first (section 7).

**The fit itself (route A, `blender/garment_fit.py`):**
1. Collider = the UNCUT reference body + the face mesh (BVH). MetaHuman cuts the body under its own garments; ease
   and weights need the whole one.
2. Optional drape: Blender cloth on the garment in the rest pose, collar and shoulder pinned (`vertex_group_mass`),
   collider `thickness_outer` = min ease; ~40 frames. Cotton-like settings (Blender's Cotton preset is quality 5,
   mass 0.3, tension/compression/shear 15, bending 0.5, air 1 [47, T2]; we use mass 0.15 for jersey).
3. Fit to a REGIONAL ease (cm, garment to skin): collar 0.8, shoulder 0.6, sleeve 1.4, chest 1.6, waist 2.4, hem
   2.8; minimum 0.5 anywhere. A regular tee is +5-10 cm of chest girth, ~0.8-1.6 cm radial on average, near 0 at the
   shoulders, free at the hem [51, T4 + pattern-drafting synthesis]. The move is computed along the body normal and
   SMOOTHED AS A FIELD (Laplacian of the displacement, the Corrective Smooth idea), so seams and folds survive.
   Blender's own equivalent is Shrinkwrap `wrap_mode='OUTSIDE'` + offset (pushes only what is inside; `ABOVE_SURFACE`
   rebuilds the armor shell) then Corrective Smooth [42, 44].
4. Weights from the uncut body: Data Transfer, `data_types_verts={'VGROUP_WEIGHTS'}`,
   `vert_mapping='POLYINTERP_NEAREST'` (nearest face interpolated) [43, T2], smoothed, max 8 influences (import with 8:
   small neck weights are dropped otherwise [22, T4]), normalized. Epic's equivalent: `TransferSkinWeights`, Closest
   Point on Surface.
5. Thickness: jersey is ~0.47 mm (SNUG's measured cotton [13, T3]); a 1.5 mm shell is already 3x real. Solidify
   (offset +1, rim on) only on an OPEN single-layer garment; MetaHuman's default garment is a closed shell: leave it.
6. Export FBX in cm on the body skeleton, `add_leaf_bones=False`, primary Y / secondary X, unscaled root (round 3's
   recipe: an x100 root over bones in metres shrinks the garment to nothing under leader pose).

**The body under it:** MetaHuman removes the body faces under its own garments at assembly (Body Hidden Face Map
[6]). A garment of your own needs the same: `body.hide_under` (Geometry Script, a copy of the body mesh; never the
face: its DNA/morphs do not survive a mesh copy). Fallback: an opacity-masked body material (UV mask): costs the
opaque fast path, shows a hole where a loose collar opens [32, 33, T4]: quick tests only.

## 3. The neck, specifically

In order of preference [7, 8, 10, 22]:
1. The face IN the collider of the fit (route A): the collar stands ≥0.8 cm off the face's lower neck in the rest
   pose, the collar band skinned from the body (8 influences, the full skeleton). No WPO.
2. Head Hidden Face Map shrink (route B, 5.7+): a grey band under the collar on the head UV map moves those vertices
   inward by up to `max_shrink_distance` (`HiddenFaceMapSettings`: `max_cull_value`, `min_keep_value`,
   `max_shrink_distance`) [7]. Only through the Wardrobe Item / Outfit Pipeline. Defaults unpublished (read
   `MetaHumanGeometryRemovalTypes.h` on the box). Known 5.8 bug: an all-black body map is ignored after assembly
   (leave a white speck) [10b, T4].
3. Cloth sim: Max Distance 0 on a 2-4 cm collar band and the shoulder seam (kinematic: then the collar is a fit
   problem, not a sim problem) [10, 37] (T3b).
4. Test at extreme poses in the level/Sequencer with the post-process AnimBP and LOD 0 (clipping often appears only
   there [56, 57, T4]): our qa.clip runs in the shot's camera at the shot's frames, plus the twist frames.

## 4. Knobs and values

| knob | value | where |
|---|---|---|
| ease (cm, to skin) | collar 0.8, shoulder 0.6, sleeve 1.4, chest 1.6, waist 2.4, hem 2.8, min 0.5 | `film-ue garment-fit --ease`, `lib/garmentfit.EASE_CM` |
| ease drawn in beyond | target + 3 cm, 35% of the excess | `--slack 3 --pull 0.35` |
| drape | 40 frames, mass 0.15, tension 15, shear 5, bending 0.5, collision = min ease | `--drape-frames 40` |
| weights | transfer from the uncut body, 8 influences | `--weights transfer` |
| thickness | 0 on a closed shell; 0.05-0.15 cm Solidify on an open jersey | `--thickness` |
| WPO inflate | **0** (FM_Inflate, FM_Neck, FM_Patch) | qa.garment_look fails > 0.2 cm |
| cotton shading | roughness 0.8-0.9, metallic 0, a sheen (Cloth shading model Fuzz Color/Cloth, or Substrate Fuzz Amount/Color/Roughness) [14, 15, 17] | material |
| cotton sim (T3b) | density 0.2 kg/m^2 [11], collision thickness ~1 cm, damping 0.01 [39, 41] | cloth.setup |

## 5. Pitfalls

- A uniform offset of any kind (WPO, `ABOVE_SURFACE` shrinkwrap, a whole-garment Solidify outward) = armor.
- Measuring ease against the CUT body: under the garment there is no skin; every distance is to the arm or the neck
  edge. Always the uncut reference body (`garment.export ref_body`).
- Forgetting the face: the body-only fit clears the body and the face's neck comes through (round 4).
- A garment re-imported over one that is drawn: never; import to a new asset, then `mh.dress` (round 3's assert).
- Leader pose lost after any component change: `mh.dress` sets it last; `mh.leader_check` verifies.
- Clip checks in the asset editor: clipping shows in Sequencer with the post-process AnimBP; measure in the shot.
- Depth precision: fp16 depth steps ~0.3 cm at 3 m (qa.md); tolerance 0.3 cm, min ease 0.5 cm.
- Wardrobe-item hiding masks do not blend across items (last wins) [10b, T4].

## 6. Verify automatically (what would have caught the operator's complaints)

- **Clipping:** `qa.clip` (core now; round 4's rules): per shot and frame, each part depth-captured alone from the
  shot's camera; per (under, over) pair the pixels where the under layer is 0.3-3 cm nearer AND at an intersection
  edge; `neck_px` = Face>tee pixels > 1 cm under the collar rim, not hugging the opening: **gate 0** every frame; pairs
  ≤ 0.001; silhouette vs a reference within ±2%.
- **Armor:** `qa.garment_look`: the armor index from ease spread and median (vs the uncut body, posed), wall
  thickness, WPO parameters, silhouette ratio ((garment ∪ body) / body px), detail (high-frequency energy of the
  garment's world normals) and motion (the garment's motion relative to the body under it). FAIL at index ≥ 0.5 or any
  WPO > 0.2 cm. Papers' measures this follows: garment-in-body area under 1% (DrapeNet 0.9%/0.3% [53], ISP [54]),
  signed-distance histograms per region, SNUG's 2 mm margin [13]; DrapeNet: per-vertex error is not a realism metric.
  The detail and motion thresholds are provisional until probe G3/G4 calibrate them.
- **The fit:** `film-ue garment-fit` exits 1 when verts are inside the body, > 2% are under 0.5 cm, the ease is an
  even shell (spread < 0.6), or a pose test (every animation the sequences play) puts a vertex inside the body.

## 7. Engine questions only the box answers (probes, batched by the orchestrator)

- G1 `film-ue op editor.api_names`: every name in ops/garment.py exposed (GeometryScript names checked on the
  source: `GeometryScript_MeshEdits`, `GeometryScript_Normals`, `GeometryScript_AssetUtils`).
- G2 the fitted tee imports with its vertex colours linear (R = ease/5) and 8 influences.
- G3/G4 calibrate qa.garment_look's detail/motion on her fitted top (cloth) and the round-4 tee (armor).
- G5 does the Host's default garment wardrobe item expose `HeadHiddenFaceMapTexture` (5.7+ API) on this build?
- G6 `body.hide_under apply=false` on her Top: the covered count is sane (her body is MetaHuman-cut under the
  default garment only).

## Sources

1. [T1] Parametric Asset Setup for MetaHuman: https://dev.epicgames.com/documentation/metahuman/parametric-asset-setup-for-metahuman
2. [T1] Getting Started with Parametric Clothing: https://dev.epicgames.com/documentation/metahuman/getting-started-for-creating-parametric-clothing-in-metahuman
3. [T1] Create a MetaHuman Parametric Outfit Asset: https://dev.epicgames.com/documentation/metahuman/create-a-metahuman-parametric-outfit-asset
4. [T1] Building with a Render Mesh: https://dev.epicgames.com/documentation/metahuman/building-a-metahuman-parametric-outfit-with-a-render-mesh
5. [T1] Creating Your MetaHuman Characters: https://dev.epicgames.com/documentation/metahuman/creating-your-metahuman-characters
6. [T1] Testing and Configuring your Parametric Outfit Asset (Body Hidden Face Map): https://dev.epicgames.com/documentation/metahuman/testing-and-configuring-your-parametric-outfit-asset
7. [T1] HiddenFaceMapSettings (5.7 Python API): https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/HiddenFaceMapSettings?application_version=5.7
8. [T1] UMetaHumanOutfitEditorPipeline (5.7: Body/HeadHiddenFaceMapTexture): https://dev.epicgames.com/documentation/unreal-engine/API/Plugins/MetaHumanDefaultEditorPipeline/UMetaHumanOutfitEditorPipeline?application_version=5.7
9. [T2] Epic staff, 5.8: resizing a Chaos Outfit Asset while preserving cloth simulation: https://forums.unrealengine.com/t/intended-workflow-for-resizing-a-chaos-outfit-asset-while-preserving-cloth-simulation/2762838
10. [T1] Dataflow SimulationMaxDistanceConfig: https://dev.epicgames.com/documentation/unreal-engine/node-reference/Dataflow/SimulationMaxDistanceConfig ; 10b [T4] fully hidden body visible after assembly (5.8): https://forums.unrealengine.com/t/fully-hidden-metahuman-body-becomes-visible-after-assembly/2833124
11. [T1] Dataflow SimulationMassConfig (cotton 0.2 kg/m^2): https://dev.epicgames.com/documentation/unreal-engine/node-reference/Dataflow/SimulationMassConfig
13. [T3] SNUG, Santesteban et al., CVPR 2022: https://arxiv.org/abs/2204.02219
14. [T1] Shading models (Cloth): https://dev.epicgames.com/documentation/unreal-engine/shading-models-in-unreal-engine
15. [T1] Substrate Slab (Fuzz): https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/UMaterialExpressionSubstrateSlab-
16. [T1] Virtual Shadow Maps (WPO invalidation, Max WPO Displacement): https://dev.epicgames.com/documentation/unreal-engine/virtual-shadow-maps-in-unreal-engine
17. [T4] cotton roughness reference: https://create.roblox.com/docs/art/modeling/material-reference
19. [T1] Building with an FBX Export: https://dev.epicgames.com/documentation/metahuman/building-a-metahuman-parametric-outfit-with-an-fbx-export
20. [T1] Building with a USD Export: https://dev.epicgames.com/documentation/metahuman/building-a-metahuman-parametric-outfit-with-a-usd-export
21. [T1] Making a Sweater with Marvelous Designer (UEFN): https://dev.epicgames.com/documentation/en-us/fortnite/making-a-sweater-with-marvelous-designer-in-unreal-editor-for-fortnite
22. [T4] MetaHuman neck-area costume clipping (face vs body mesh, correctives): https://forums.unrealengine.com/t/metahuman-the-neck-area-of-character-costumes-has-normal-weight-values-in-maya-but-after-importing-into-ue-and-assembling-there-are-clipping-penetration-issues-may-i-ask-what-caused-this-can-someone-explain-this/2846582
27. [T2] Outfit Asset Resizing Addendum thread: https://forums.unrealengine.com/t/tutorial-chaos-cloth-outfit-asset-resizing-addendum/2647376
32. [T4] poke-through thread: https://forums.unrealengine.com/t/please-little-help-or-advise-when-dealing-with-poke-through-issue/253814
33. [T4] alpha mask add-on: https://superhivemarket.com/products/metahuman-advanced-alpha-mask-creator
35. [T2] Epic news, Tailoring for MetaHumans: CLO and Marvelous Designer to UE (not readable to us: 403): https://www.unrealengine.com/news/tailoring-for-metahumans-clo-and-marvelous-designer-to-unreal-engine-demo
37. [T1] Clothing Tool (Max Distance, Backstop): https://dev.epicgames.com/documentation/en-us/unreal-engine/clothing-tool-in-unreal-engine
39. [T1] SimulationCollisionConfig: https://dev.epicgames.com/documentation/unreal-engine/node-reference/Dataflow/SimulationCollisionConfig
41. [T1] SimulationDampingConfig: https://dev.epicgames.com/documentation/unreal-engine/node-reference/Dataflow/SimulationDampingConfig
42. [T2] Blender ShrinkwrapModifier: https://docs.blender.org/api/current/bpy.types.ShrinkwrapModifier.html
43. [T2] Blender DataTransferModifier: https://docs.blender.org/api/current/bpy.types.DataTransferModifier.html
44. [T2] Blender CorrectiveSmooth / SurfaceDeform / Solidify: https://docs.blender.org/api/current/bpy.types.CorrectiveSmoothModifier.html
45. [T2] Blender export_scene.fbx: https://docs.blender.org/api/current/bpy.ops.export_scene.html
47. [T2] Blender cloth presets: https://projects.blender.org/blender/blender/src/branch/main/scripts/presets/cloth
48. [T4] r.Velocity.EnableVertexDeformation: https://indxzero.github.io/ue544cvarwiki/articles/r.velocity.enablevertexdeformation
51. [T4] ease references: https://knotions.com/learn-understanding-ease/
53. [T3] DrapeNet, CVPR 2023: https://arxiv.org/abs/2211.11277
54. [T3] ISP, NeurIPS 2023: https://arxiv.org/abs/2305.14100
55. [T3] HOOD, CVPR 2023: https://arxiv.org/abs/2212.07242
56. [T4] clipping in scene, not in the MetaHuman editor: https://forums.unrealengine.com/t/new-adaptable-clothing-clipping-issue-in-scene-but-not-in-metahuman-editor-or-blueprint/2549945
57. [T4] skinned clothes clip in Sequencer: https://forums.unrealengine.com/t/5-4-skinned-clothes-clip-through-in-sequencer-but-not-in-skeletal-mesh-editor/2707992

Not verified (pages unreadable to us): the Chaos Cloth 5.6 Updates and Resizing Addendum tutorial bodies, the
"Tailoring for MetaHumans" page, `HiddenFaceMapSettings` defaults, what `MI_WI_DefaultGarment` is internally.
