# Garments: fit, clipping and the cloth look

A garment on a MetaHuman must (1) never let skin or an under-garment through, as the shot's camera sees it, and (2)
read as cloth, not as a shell. Round 4 of the karma reel passed (1) with a material WPO "inflate" and failed (2): the
operator saw "heavy armor". The research: [research/garment-fit.md](research/garment-fit.md). Simulation (Chaos
Cloth) is [cloth.md](cloth.md) (T3b).

**Never WPO-inflate a garment** (`mh.cloth_inflate` is kept for old levels only). Fit it: real ease in the geometry.

## 1. Recipe: refit a garment, check it

```bash
# 1. export what the fit needs (on the box; the body is face data and stays there)
film-ue op garment.export label=Host out_dir=/srv/ue/fit/host 'sequences=["/Game/Reel/SEQ_Reel"]'
#    -> body.fbx, face.fbx, ref_body.fbx (UNCUT), garment_tee.fbx, anim_*.fbx, manifest.json
# 2. fit in headless Blender (regional ease, face in the collider, weights from the uncut body, pose tests)
film-ue garment-fit --src /srv/ue/fit/host --garment tee --out /srv/ue/fit/host/out --drape-frames 40 --only-slots shirt
#    PASS/FAIL in words, per-region ease, pose tests; exit 1 = do not import
# 3. import as a NEW asset and dress (materials: the plain instances, no FM_Inflate chain)
film-ue op mh.import_garment fbx=/srv/ue/fit/host/out/garment_fit_tee.fbx dest=/Game/Host/Fit/SKM_Host_Tee_Fit
film-ue op mh.dress label=Host 'garments={"SkeletalMesh": {"mesh": "/Game/Host/Fit/SKM_Host_Tee_Fit"}}'
film-ue op mh.leader_check label=Host
# 4. check in the shots
film-ue op qa.clip label=Host sequence=/Game/Reel/SEQ_Reel 'shots=["Reel_S13","Reel_S15","Reel_S17","Reel_S18"]' \
    out_dir=/srv/ue/qa/clip/r5 ref_dir=/srv/ue/reel/r4/clip/Host_after
film-ue op qa.garment_look label=Host ref_body=<uncut body from manifest.json> sequence=/Game/Reel/SEQ_Reel \
    'frames=[1082,1150,1397]' motion_from=1140 motion_frames=12 out_dir=/srv/ue/qa/look/r5
```

A garment of your own that MetaHuman did not cut the body for: `film-ue op body.hide_under label=Ava garment=Top`
(counts), then `apply=true` (a copy of the body mesh without the covered triangles, leader pose re-applied).

**What shipped on the karma reel (round 5, his MetaHuman default-garment tee):**
```bash
film-ue op garment.export label=Host out_dir=$G/fit ref_body=<an UNCUT MetaHuman body: 30455 verts> 'sequences=[...]'
film-ue garment-fit --src $G/fit --garment tee --out $G/fit/out9 --only-slots shirt --morph-ref --drape-frames 0 \
    --weights blend --blend-regions collar,shoulder,sleeve --ease '{"collar": 1.8, "waist": 3.0, "hem": 3.4}'
```
qa.clip: neck_px 0, Body>Tee 0.00067, Trousers>Tee 0; armor 0.109 (round 4's WPO tee: 0.538), wpo 0. It took 9 runs;
the lessons are in §4 (weights, the uncut body, the pose test, the closed shell). **Then rejected by eye**: the collar
floated off his neck like a rolled cowl (collar ease 1.8 cm, and the wrong skeleton, below) and the hem flared (hem
ease 3.4 along the hip normal). qa.garment_look now fails both (collar gap/roll, hem flare). The orchestrator's final
call for round 5: Epic's own default garment, WPO 0, the head hidden-face-map shrink for the neck (reel/r5
neck_backstop.py), round 4's trousers.

## 2. Ops

| op | what | multi-tick |
|---|---|---|
| `garment.export` | body, face, uncut ref body, garments, played anims as FBX + manifest.json for the fit | no |
| `body.hide_under` | body triangles a garment covers (ray out along the skin normal hits it within reach_cm), shrunk by `rings`; `apply` writes a body copy | yes |
| `qa.clip` | per shot/frame depth layers from the shot camera; per (under, over) pair clip px at intersection edges; `neck_px` under the collar band; silhouette vs `ref_dir`; gate | yes |
| `qa.garment_look` | the armor index: ease spread/median vs the uncut body, wall thickness, WPO params, silhouette ratio, normal detail, motion | yes |
| `garment.hidden_face_maps` | a MetaHuman wardrobe item's head/body hidden face maps and settings (cull / shrink) | no |
| `film-ue garment-fit` | CLI: runs `blender/garment_fit.py` on the box, judges `fit_report.json` | (Blender) |

Pure parts, tested without an engine: `unreal/fmbridge/qa/clip.py`, `unreal/fmbridge/qa/garment_look.py`,
`blender/lib/garmentfit.py`, `garment.covered`.

## 3. Gates

| check | pass | from |
|---|---|---|
| qa.clip pair (Body>tee, Body>Trousers, Trousers>tee ...) | fraction ≤ 0.001 every frame (or ≤ its `before` worst + 0.01) | round 4 (agent-09's gate e) |
| qa.clip `neck_px` | 0 every frame | the orchestrator's round-4 ruling |
| qa.clip silhouette vs ref | within ±2% | round 4 |
| qa.garment_look | verdict not `armor`: index < 0.5, WPO ≤ 0.2 cm | round 5 (the operator's "armor") |
| garment-fit | no vert inside the body, ≤ 2% under 0.5 cm, ease spread ≥ 0.6, pose tests 0 inside | round 5 |

The armor index terms (`fmbridge/qa/garment_look.py` RAMPS, score 0 = cloth, 1 = armor):
ease_spread 1.0 → 0.4; ease_median 3 → 5 cm; thickness 0.3 → 0.8 cm; silhouette 1.10 → 1.25; detail 0.035 → 0.012
(provisional); motion 0.12 → 0.03 (provisional); wpo 0 → 0.5 cm.

## 4. Gotchas

- Ease against the CUT body is meaningless (no skin under the garment): give `ref_body` (garment.export finds an
  uncut body mesh beside the body, or refuses and says so).
- The face's lower neck is under the collar: it is in the fit's collider (`--collider ref_body,face`).
- `body.hide_under` never touches the Face (DNA, morph targets); fit round it instead.
- Import a refit as a NEW asset; never re-import over a mesh that is being drawn.
- The fit keeps the garment's topology, UVs and slots: its materials still map. A MetaHuman default garment carries
  the shorts in the same mesh: `--only-slots shirt` fits the tee and leaves the shorts.
- Vertex colours out of the fit: R = ease / 5 cm, G = pinned (collar, shoulder): cloth.setup reads them.
- Detail needs a normal capture (`SCS_Normal`, deferred renderer only).

- **No uncut body of the character?** (MetaHuman assembles only the cut one.) `--morph-ref` with another uncut
  MetaHuman body of the same topology (30455 verts; a cut one has fewer): it is morphed onto the worn body where
  they meet and the cut region filled smoothly (round 5: 74.5% matched, fill median 0.2 cm).
- **Export on THE CHARACTER'S skeleton.** Unreal skins an imported mesh with its own bind pose against the
  character's bones: a garment bound to another body's armature (round 5's `--morph-ref` before 868ef94e kept the
  reference person's) is posed offset by the two skeletons' joint differences (Fit6: Epic's collar band 5.5 cm off
  his neck, the tee riding off trousers fitted to its rest geometry). The fit now always binds to body.fbx's armature.
- **Weights decide clips that ease cannot.** Body-transferred weights let the collar follow a big neck turn, but at
  the hem they follow the thighs, while under-garments fitted to the garment's OWN weights (his trousers copy the
  old tee's) stay with the spine: the waistband came through by 3 cm. `--weights blend --blend-regions
  collar,shoulder,sleeve`: transferred where the neck/arms drive it, the garment's own below (the blend is smoothed
  over ~15 rings, ~15-20 cm: keep the chest out of the transferred set or it reaches the hem).
- **Measure on the final motion.** A later performance pass (calibrate_body) changed his torso turn and brought a
  0.5 cm waistband residue back: 0.6 cm more waist/hem ease cleared it.
- **The fit's pose test is a proxy.** qa.clip in the shot's camera with the real face rig is the judge (round 5: the
  pose test first counted the hidden shorts, then rode the face rigidly on neck_02).
- **A closed-shell garment (a MetaHuman default garment, a solidified overshirt) must not be simulated whole**
  (round 5: her overshirt exploded). Simulate a single-layer proxy section (`--single-layer`, round 6) mapped onto
  the render section.
- **qa.garment_look's silhouette and motion terms are reported with weight 0**: the temporary reference-body actor
  read impossible values on the box (2.30, 966); fix before trusting them.
- **Vertex colours**: the fit writes linear bytes; Unreal reads FBX colours as sRGB FColor: read G (pinned, 0/1),
  not R, unless decoded as raw byte/255.

## 5. API_NOTES (verified on the 5.8.4 source box, /srv/ue-src/UnrealEngine-5.8.4)

GeometryScript paths are under `Engine/Plugins/Runtime/GeometryScripting/Source/GeometryScriptingCore/Public/GeometryScript/`.
Python names are the snake_case of the reflected names. ✓ = read in the header.

| Python | engine | where | ✓ |
|---|---|---|---|
| `unreal.GeometryScript_SceneUtils.copy_mesh_from_component` | CopyMeshFromComponent | SceneUtilityFunctions.h:56 (class), :82 | ✓ |
| `unreal.GeometryScriptCopyMeshFromComponentOptions` | FGeometryScriptCopyMeshFromComponentOptions | SceneUtilityFunctions.h:18 | ✓ |
| `unreal.GeometryScript_MeshSpatial` build_bvh_for_mesh, find_nearest_point_on_mesh, find_nearest_ray_intersection_with_mesh | BuildBVHForMesh, FindNearestPointOnMesh, FindNearestRayIntersectionWithMesh | MeshSpatialFunctions.h:59, :76, :113, :129 | ✓ |
| `unreal.GeometryScript_MeshQueries` get_all_vertex_positions, get_triangle_face_normal, get_triangle_positions, get_triangle_indices, get_all_triangle_i_ds | GetAllVertexPositions, GetTriangleFaceNormal, GetTrianglePositions, GetTriangleIndices, GetAllTriangleIDs | MeshQueryFunctions.h:15, :220, :152, :134, :118, :110 (the ops try `get_all_triangle_ids` too) | ✓ |
| `unreal.GeometryScript_Normals.get_mesh_per_vertex_normals` | GetMeshPerVertexNormals (list as long as MaxVertexID) | MeshNormalsFunctions.h:72, :234 | ✓ |
| `unreal.GeometryScript_List` convert_vector_list_to_array, convert_index_list_to_array, convert_array_to_index_list | ConvertVectorListToArray, ConvertIndexListToArray, ConvertArrayToIndexList | ListUtilityFunctions.h:15, :188, :51, :57 | ✓ |
| `unreal.GeometryScript_AssetUtils` copy_mesh_from_skeletal_mesh, copy_mesh_to_skeletal_mesh | CopyMeshFromSkeletalMesh, CopyMeshToSkeletalMesh (Outcome is ExpandEnumAsExecs: a return) | MeshAssetFunctions.h:230, :410, :423 | ✓ |
| `unreal.GeometryScriptCopyMeshFromAssetOptions`, `unreal.GeometryScriptCopyMeshToAssetOptions` | structs | MeshAssetFunctions.h:56, :111 | ✓ |
| `unreal.GeometryScriptMeshReadLOD`, `unreal.GeometryScriptMeshWriteLOD` | structs | GeometryScriptTypes.h:86, :99 | ✓ |
| `unreal.GeometryScript_MeshEdits.delete_triangles_from_mesh` | DeleteTrianglesFromMesh (ScriptName GeometryScript_MeshEdits, not MeshBasicEdits) | MeshBasicEditFunctions.h:112, :236 | ✓ |
| `unreal.GeometryScript_Materials.get_all_triangle_material_i_ds` | GetAllTriangleMaterialIDs (ScriptName GeometryScript_Materials); a skinned component's copy gives each triangle its section's material SLOT index | MeshMaterialFunctions.h:16, :125; Engine/Plugins/Runtime/MeshModelingToolset/Source/ModelingComponents/Private/ConversionUtils/SkinnedMeshToDynamicMesh.cpp:302-309, :480 | ✓ |
| `unreal.AssetExportTask` | UAssetExportTask | Engine/Source/Runtime/Engine/Public/AssetExportTask.h:14 | ✓ |
| `unreal.Exporter.run_asset_export_task` | UExporter::RunAssetExportTask (BlueprintCallable, static) | Engine/Source/Runtime/Engine/Classes/Exporters/Exporter.h:255 | ✓ |
| `unreal.FbxExportOption` (ascii, vertex_color, level_of_detail, collision, export_morph_targets, map_skeletal_motion_to_root) | UFbxExportOption bASCII, VertexColor, LevelOfDetail, Collision, bExportMorphTargets, MapSkeletalMotionToRoot | Engine/Source/Editor/UnrealEd/Classes/Exporters/FbxExportOption.h:74-111 | ✓ |
| `set_leader_pose_component` | USkinnedMeshComponent::SetLeaderPoseComponent | Engine/Source/Runtime/Engine/Classes/Components/SkinnedMeshComponent.h:1884 | ✓ |
| `set_skeletal_mesh_asset` | USkeletalMeshComponent::SetSkeletalMeshAsset | Engine/Source/Runtime/Engine/Classes/Components/SkeletalMeshComponent.h:369 | ✓ |
| capture source `normal` | ESceneCaptureSource SCS_Normal ("Deferred Renderer only") | Engine/Source/Runtime/Engine/Classes/Engine/EngineTypes.h:542 | ✓ |
| wardrobe item `pipeline` -> `editor_pipeline` | UMetaHumanWardrobeItem::Pipeline (EditAnywhere, Instanced); UMetaHumanSkeletalMeshPipeline / UMetaHumanOutfitPipeline::EditorPipeline | Engine/Plugins/MetaHuman/MetaHumanCharacter/Source/MetaHumanCharacterPalette/Public/MetaHumanWardrobeItem.h:67; MetaHumanDefaultPipeline/Public/Item/MetaHumanSkeletalMeshPipeline.h:97, MetaHumanOutfitPipeline.h:133 | ✓ |
| `head_hidden_face_map_texture`, `body_hidden_face_map_texture` (texture, settings) | UMetaHumanSkeletalMeshEditorPipeline / UMetaHumanOutfitEditorPipeline (EditAnywhere) | MetaHumanDefaultEditorPipeline/Public/Item/MetaHumanSkeletalMeshEditorPipeline.h:41-48, MetaHumanOutfitEditorPipeline.h:83-90 | ✓ |
| settings `max_cull_value` 0.1, `min_keep_value` 0.9, `max_shrink_distance` 0.0 | FHiddenFaceMapSettings (EditAnywhere) | MetaHumanCharacter/Public/MetaHumanGeometryRemovalTypes.h:26, :33, :50 | ✓ |
