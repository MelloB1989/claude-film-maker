# assets: import, the content browser, materials and Fab (WP2)

Everything about what is in the project, by code and with no dialog: bring files in (any format, the right settings
for what each is), find things ("a 45 cm chair"), describe and check them by numbers, manage them (rename, move,
remove with their references), build materials from a library of masters or a node graph, and get assets from Fab.
Ops: `assets.*` (assets.py, assets_import.py, assets_catalog.py), `mat.*` (mat.py), `fab.*` (fab.py).

## 1. Recipes

Commands are the generated CLI (`film-ue <area> <verb> --flag`); the same calls from Python are
`ue.assets.import_(files=[...], dest=...)`, `ue.mat.instance(...)`. Paths in `--files`/`--path` are ON THE BOX: push
local files first (`client.push`, or `film-ue push` on your transport).

**Import a prop, ready to use**
```bash
film-ue assets import --files /srv/film/props/chair.fbx --dest /Game/Set/Props --collision convex --detail
film-ue assets mesh --path /Game/Set/Props/chair --nanite true --lods 3
film-ue assets describe --path /Game/Set/Props/chair
```
Check: `describe` gives `size_cm` (is it the size you expect? a chair is ~45 cm to the seat, ~90 cm tall; an FBX in
metres converts to cm by itself), `triangles`, `nanite`, `collision.simple > 0`, `materials` (slot names).
Formats: `.fbx .obj .gltf .glb` (Interchange), `.abc` (`--kind static|geometry_cache|skeletal`, `--groom` for hair
curves, `--abc-preset maya|max|none`), `.usd*` (needs the USDImporter plugin), images, `.wav`.
A skeletal mesh on an existing skeleton: `--kind skeletal --skeleton /Game/Chars/SK_Mannequin`.
Re-running with `--replace false` keeps what an earlier import of the same file made (`changed: false`).

**Import textures with the right settings**
```bash
film-ue assets import_textures --folder /srv/film/tex/rock --dest /Game/Set/Tex
film-ue assets texture --path /Game/Set/Tex/T_Rock_N --role normal
```
Check: each texture's `role` in the answer. Names decide the role (section 5 lists the suffixes); a PNG named
nothing useful that looks like a normal map (mean colour near 0.5, 0.5, 1.0) is imported as one; everything else is
colour (sRGB). `assets.describe` shows `srgb`, `compression`.

**A PBR material from a texture set**
```bash
film-ue mat pbr --path /Game/Set/Mats/MI_Rock --folder /srv/film/tex/rock
film-ue mat check --path /Game/Set/Mats/MI_Rock
```
Check: `master` (opaque_orm when there is a packed ORM map), `maps` (role -> texture), `ignored` (files it could not
place), then `mat check` `pass: true` (it compiles; every texture matches its sampler).

**Prepare a texture set before pushing it** (client side, needs pillow): separate AO/roughness/metallic maps packed
into one ORM (one sampler instead of three), gloss inverted into roughness, an RMA/MRA map reordered, OpenGL normals
flipped with `--flip-green`:
```bash
film-ue texpack ~/downloads/rock_4k --out /tmp/rock_set --flip-green
```
Check: one line per set with the files it wrote and notes ("gloss inverted into roughness", "no metallic map: 0 in
its channel"); files it could not place by name are listed. Then push `/tmp/rock_set` and run `mat pbr --folder`.

**Capture what is there as specs** (the round trip of `film-ue apply`):
```bash
film-ue export-spec material /Game/Set/Mats/MI_Rock /Game/Set/Mats/MI_Oak > mats.yaml
film-ue export-spec asset /Game/Set/Props/SM_Chair > props.yaml
```
Applying an exported spec to the same project plans nothing; edit it and apply it to change or recreate things.

**A material from the library**
```bash
film-ue mat masters                                # what each master is for and its parameters (with units)
film-ue mat instance --path /Game/Set/Mats/MI_RedPaint --master opaque --params '{"Tint": [0.6, 0.05, 0.04], "Roughness": 0.35}'
film-ue mat preset --path /Game/Set/Mats/MI_Window --name glass_clear
film-ue mat preset --path /Game/Set/Mats/MI_Panel --name emissive_panel --nits 400 --color 1,0.9,0.8
film-ue mat describe --path /Game/Set/Mats/MI_RedPaint
```
Check: `updated` lists what was written (empty on a re-run); `mat describe` reads the values back. Emissive is in
nits (cd/m2): 100-300 a screen, ~1500 a lamp shade, 20000 a bare bulb (`mat presets`).

**Any material, by spec (a node graph)**
```bash
film-ue mat graph --path /Game/Set/Mats/M_Rim --spec @rim.json
```
with `rim.json` = `{"nodes": {"c": {"type": "Vector", "name": "Col", "default": [0.1, 0.4, 0.8, 1]}, "f": {"type":
"Fresnel", "exponent": 3}, "rim": {"type": "Lerp", "in": {"A": "c.RGB", "B": [1, 1, 1], "Alpha": "f"}}}, "outputs":
{"BaseColor": "rim", "Roughness": 0.4}}`. Check: `stats.num_samplers` is not -1 (it compiles); a re-run with the
same spec is `changed: false`. A wrong node/pin/output fails before anything is touched, naming the nearest valid
names.

**Put a material on a mesh**: on the mesh asset (every actor that shows it), or on one actor only with WP6's
`level.material`:
```bash
film-ue mat assign --mesh /Game/Set/Props/chair --material /Game/Set/Mats/MI_Oak --slot Seat
```

**Find an asset by what it is and how big**
```bash
film-ue assets find --query "a 45 cm chair" --cls StaticMesh
film-ue assets find --query "table 120x80 cm" --folder /Game/Set
film-ue assets find --query "lamp 1.5 m tall"
film-ue assets find --name "SM_Chair*" --tags '{"category": "furniture"}'
film-ue assets catalog --folder /Game/Set/Props --cls StaticMesh
```
Check: `hits[0]` with `score` (0..1), `size_error` (relative: 0.02 = 2 % off) and `scale` (the uniform factor that
makes it exactly the asked size: put it on the actor with `level.move --scale`). Sizes without a unit are cm;
`tall/high` = Z, `wide` = Y, `long/deep` = X; with no axis word the height or the longest side, whichever is closer.
The catalog comes from the asset registry without loading anything (fast on thousands of assets); `--refresh true`
after imports; `--load true` fills in meshes saved before their counts were known.

**See an asset with no viewport**
```bash
film-ue assets thumbnail --path /Game/Set/Props/chair --out-dir /tmp/thumbs/chair --views 4
```
Check: the PNGs (pull them) and `sheet.png`. It places a temporary copy far below the set with a temporary light,
captures it alone through WP10's `view.turntable`, and removes both.

**Rename, move, clean up**
```bash
film-ue assets rename --src /Game/Imports/chair --dst /Game/Set/Props/SM_Chair
film-ue assets move --paths /Game/Imports/SM_Lamp,/Game/Imports/SM_Rug --folder /Game/Set/Props
film-ue assets refs --path /Game/Set/Mats/MI_Oak                # who uses it, what it uses, level actors
film-ue assets remove --paths /Game/Old/MI_Oak --dry-run         # what would go, what is still used (kept)
film-ue assets remove --folder /Game/Imports
film-ue assets fix_redirectors --folder /Game
film-ue assets audit --folder /Game/Set                          # unused, redirectors, broken materials
```
Check: `assets.remove` refuses (code `conflict`, naming the users) while something uses an asset; removing what is
not there is fine. `assets.audit` `pass: false` means a material does not compile or a texture is the wrong kind.

**Fab and Megascans**
```bash
film-ue fab status                                  # plugin, signed in, saved sign-ins, what to do next
film-ue fab login                                   # uses the saved sign-in (multi-tick)
film-ue fab library --query chair                   # what the account owns
film-ue fab import --path /srv/film/fab/rock_4k.zip # a download on the box: Megascans glTF, FBX, glTF, textures
film-ue fab add --url "<signed url>" --metadata '{"AssetId": "...", "AssetName": "Rock", "IsQuixel": true}'
```
Check: `fab status` `next`; `fab import` `format` and `imported`/`material`. The signed URL for `fab.add` comes from
Fab's own web page: `filmtools.unreal.fab_shim.signed_url(listing_id, token=...)` (headless Chromium; experimental).
First sign-in on a box: `film-ue fab login --portal true`, then a person approves the device code from the editor
log once (WP1's `film-ue epic-login --fab` does the same from the CLI). Never run the console commands `Fab.Logout`
or `Fab.SetEnvironment`: both delete the saved sign-in.

## 2. Op reference

`film-ue describe assets`, `film-ue describe mat`, `film-ue describe fab` list them with every argument.

| op | what |
|---|---|
| `assets.import` | files on the box -> assets, any format, no dialog (old positional args kept; returns object paths, or per file with `detail`) |
| `assets.import_textures` / `assets.texture` | images with settings by role / converge one texture's settings |
| `assets.mesh` | Nanite, generated LODs, simple/convex collision, lightmap UVs, CPU access, LOD group |
| `assets.reimport` | from the source file or a new one (Interchange, keeps settings) |
| `assets.describe` / `assets.catalog` / `assets.find` | one asset's numbers / a folder from registry tags / search by words, size, class, tags |
| `assets.thumbnail` | PNGs of an asset, isolated (multi-tick, GPU) |
| `assets.list` / `assets.props` / `assets.set_props` | listing; raw editor properties (enums by name) |
| `assets.duplicate` / `assets.rename` / `assets.move` / `assets.remove` / `assets.delete` / `assets.folder` | management (`remove` checks references; `delete` does not) |
| `assets.tag` / `assets.refs` / `assets.fix_redirectors` / `assets.audit` | metadata tags; references; redirectors; what needs attention |
| `assets.save` / `assets.save_all` | save given assets or a folder / every dirty package |
| `mat.masters` / `mat.master` | the library's masters (docs, params) / build one |
| `mat.instance` / `mat.preset` / `mat.presets` / `mat.pbr` | instances by params / named looks / from a texture set |
| `mat.graph` | a Material from a node-graph spec |
| `mat.describe` / `mat.check` / `mat.assign` | read back / compiles + textures vs samplers (a check: pass, issues, metrics) / on a mesh slot |
| `fab.status` / `fab.login` / `fab.library` / `fab.import` / `fab.add` | Fab by code |

Shared helpers other areas import from `ops/assets.py`: `EAL`, `load`, `free`, `import_files`, `list_assets`; from
`ops/mat.py`: `master(name) -> path` (WP5's emissive surfaces use `master("emissive")`, `Luminance_nits`).

The material library (`/Game/FM/Lib`, built on first use, with its own 4x4 default textures):

| master | for | parameters |
|---|---|---|
| opaque / opaque_orm | any PBR surface; separate AO/roughness/metallic maps, or one packed ORM | Tint, BaseColorMap, NormalMap, NormalStrength, AOMap/RoughnessMap/MetallicMap or ORMMap, Roughness, Metallic (multiply the maps: with no map they ARE the value), Specular, AOStrength, Tiling |
| masked / masked_orm | cut-outs (leaves, fences, lace), two-sided | + OpacityMap, UseBaseAlpha (switch) |
| foliage | leaves with light through them | masked + TranslucencyMap, Transmission |
| glass | glass, clear plastic, liquids (lit per pixel as a surface) | Tint, Opacity, Roughness, Specular, IOR, Metallic |
| emissive | unlit emitters, in nits | Color, EmissiveMap, Luminance_nits, Tiling |
| screen | a display: emitted picture behind glossy black glass | emissive + ScreenRoughness |
| cloth | velvet, cotton, wool (cloth shading model) | opaque + FuzzColor, Cloth |
| skin | skin-safe subsurface for non-MetaHuman skin, wax, marble | opaque (no metallic) + SubsurfaceColor, SubsurfaceAmount |
| unlit | backdrops, sky cards | Tint, BaseColorMap, Tiling |
| decal | deferred decals | Tint, BaseColorMap, NormalMap, OpacityMap, DecalOpacity, Roughness |

Presets (`mat.presets`): matte_paint, satin_paint, plastic_gloss, plastic_matte, rubber, ceramic, chrome,
brushed_steel, aluminium, gold, copper, brass, glass_clear, glass_frosted, glass_tinted, water, emissive_panel,
lamp_shade, bulb, screen, velvet, cotton, wax, marble, skin_generic, leaf, backdrop.

Graph spec node types (`mat.graph`): Scalar, Vector, Texture, Switch, StaticBool, Const/Const2/Const3/Const4, Add,
Subtract, Multiply, Divide, Lerp, OneMinus, Power (pins Base, Exp), Saturate, Clamp, Min, Max, Abs, Dot, Append,
Mask, Desaturate, TexCoord, VertexColor, Fresnel (ExponentIn, BaseReflectFractionIn, Normal), WorldPosition, Time,
TwoSidedSign, PixelDepth, CameraVector, Function (a MaterialFunctionCall: `function: /Engine/Functions/...`),
Collection, or any engine class by its full name (`MaterialExpressionSine`, pins unchecked). Single-input nodes'
pin is `""`. Outputs of Texture/Vector: RGB, R, G, B, A, RGBA.

## 3. Spec kinds

`material` (order 12) and `asset` (order 10): `tools/filmtools/unreal/assets_kinds.py`, schemas in
`tools/filmtools/unreal/schemas/{material,asset}.schema.json`, examples in `examples/unreal/{material,asset}/`.

```yaml
kind: asset
version: 1
name: chair
file: /srv/film/props/chair.glb        # on the box
dest: /Game/Set/Props
asset: SM_Chair
mesh: {nanite: false, lods: 3, collision: box}
tags: {category: furniture}
---
kind: material
version: 1
name: oak
path: /Game/Set/Mats/MI_Oak
master: opaque_orm                     # or parent:, preset:, graph:
params: {BaseColorMap: /Game/Set/Tex/T_Oak_BaseColor, ORMMap: /Game/Set/Tex/T_Oak_ORM, Roughness: 1, Metallic: 1}
assign: [{mesh: /Game/Set/Props/SM_Chair, slot: 0}]
```
`film-ue plan set.yaml` then `film-ue apply set.yaml`: converged when the second plan is empty. Materials apply
after assets, so a material names the mesh slots it goes on (`assign`); an asset whose source file name changed is
imported again. Texture files land as `T_<stem>` (what `assets.import_textures` names them).

## 4. Gotchas

Engine facts found in the 5.8.4 source tonight (API_NOTES has the lines); the first five are also in
unreal/README.md's traps.

- **A hidden dialog says no.** Under `-unattended` (or an EditorAssetSubsystem call, or an automated import) a
  message box is not shown: it returns its default, No/Cancel. A rename of an asset a class default object refers
  to then silently does nothing. Ops check results instead of trusting a call.
- **Material instance setters always return False** (`MaterialEditingLibrary::SetMaterialInstance*ParameterValue`
  never sets its result) and accept any name, adding an orphan override. `mat.instance` checks names against the
  parent first and reads every value back.
- **`delete_all_material_expressions` skips every other node** (it deletes while iterating the live array): a
  rebuilt material keeps half its old nodes and duplicates its parameters. `mat.*` deletes them one by one and
  checks the count is 0.
- **`recompile_material` returns the compile errors** in 5.8; `get_statistics` waits for the shaders and gives
  `num_samplers == -1` for a material that does not compile. `mat.graph`/`mat.master` fail with the errors.
- **EditorAssetLibrary is in the EditorScriptingUtilities plugin, off by default in a new project.** The
  EditorAssetSubsystem has the same calls and is always there; `ops/assets.py`'s `EAL` falls back to it.
- **Setting a texture on a sampler node resets its sampler type** from the texture: set `sampler_type` after
  `texture` (the graph builder does).
- **Interchange imports FBX, OBJ, glTF and images by default** (5.8). Setting any `factory` on an import task skips
  it. Its options are an InterchangeGenericAssetsPipeline in an InterchangePipelineStackOverride, which REPLACES the
  translator's stack: glTF needs Epic's `/Interchange/Pipelines/DefaultGLTFPipeline` added back (assets.import does).
- **FbxImportUI is half-honoured under Interchange**: `convert_scene`, `convert_scene_unit` and `force_front_x_axis`
  are dropped on a fresh import (the FBX translator's per-user settings win). Units are converted to cm by default.
  `FbxImportUI` and `UsdStageImportOptions` load defaults from per-user config: set every field.
- **`replace_existing` onto an existing asset is a re-import** with Interchange (same asset, new data).
- **Never edit Epic's default pipeline assets in memory** (`/Interchange/Pipelines/Default*`): a later
  `save_dirty_packages` writes the change into the project's defaults. The ops make fresh pipelines.
- **No pipeline sets sRGB or compression**: textures are set after import (`assets.texture`, by role).
- **Alembic defaults to the Maya preset** (scale 1,-1,1; rotation 90,0,0; flip V) and the preset field alone does
  not change scale/rotation when scripting: `--abc-preset` sets them explicitly. A groom (HairStrands plugin) takes
  GroomImportOptions in the task.
- **AssetTools.FixupReferencers is not reachable from Python.** `assets.fix_redirectors` loads each referencer
  (loading follows the redirector), saves it (it now points at the real asset) and deletes the redirector.
- **No Python function renders a thumbnail.** `assets.thumbnail` captures a temporary actor through WP10's
  `view.turntable`. (A saved asset's stored 256 px thumbnail can be read back through `Variant.set_thumbnail_from_object`,
  not used.)
- **Registry tags make a catalog without loading** (ApproxSize "XxYxZ" cm, Triangles, LODs, NaniteEnabled, ...), but
  a mesh saved while it was still compiling has no counts: `assets.catalog --load true`.
- **Skeletal meshes have no triangle-count call**: the `Triangles` registry tag (LOD0) is what there is.
- **Substrate**: new 5.8 projects turn `r.Substrate` on (Blendable GBuffer). The library's legacy-pin graphs still
  work: the engine converts them at compile time. Once `MP_FRONT_MATERIAL` is wired the legacy pins are ignored.
  `thin_translucent` shading forces a coloured-transmittance blend under Substrate.
- **`create_asset` over an existing asset** returns None with an error in the log under `-unattended`
  (interactively: a modal). Everything here edits an existing asset in place or frees the path first.
- **Never change a material while it is drawn** (unreal/README.md): `mat.master`/`mat.graph` refuse to recompile,
  and `mat.instance` to reparent, a material an actor in the open level draws (code `conflict`, naming the actors),
  unless `--force true`. Changing parameter values is safe.
- **Fab**: none of the plugin's API is BlueprintCallable; `call_method` reaches its string-only functions. The
  saved sign-in is tried only when a Fab tab is created (so `-AUTH_TYPE=exchangecode` alone does nothing headless:
  `fab.login` opens a tab). `AddToProject` takes a struct with no Python type: `fab.add` downloads and imports in
  Python, or calls it through the FabScript plugin (section 6). Unreal-engine-format packs need Build Patch
  Services, whose Linux library (`Engine/Plugins/Fab/ThirdParty/libBuildPatchInstallerLib.so`) the source tree does
  not ship (only Epic's binary Fab plugin has it).

## 5. Texture roles by name

The last token of the file name that names a role wins (`T_Wood_Normal_4K` -> normal; resolutions, UDIM numbers and
LOD/version tokens are skipped); one-letter tokens count only at the end (`_N`, `_D`, `_R`).

| role | tokens | sRGB | compression | sampler |
|---|---|---|---|---|
| base_color | basecolor, base_color, albedo, diffuse, diff, color, col, alb, bc, d, c, a | yes | TC_DEFAULT | Color |
| normal | normal, nrm, nor, norm, nml, n (`_gl`/`opengl`: green flipped) | no | TC_NORMALMAP | Normal |
| roughness / gloss | roughness, rough, rgh, r / gloss, glossiness, smoothness, g | no | TC_MASKS | Masks |
| metallic | metallic, metalness, metal, met, mtl, m | no | TC_MASKS | Masks |
| ao | ao, ambientocclusion, occlusion, occ, o | no | TC_MASKS | Masks |
| orm (packed) | orm, arm (R AO, G rough, B metal), rma, mra, rmo, packed, mask(s), mk | no | TC_MASKS | Masks |
| opacity | opacity, alpha, transparency, opac, op | no | TC_MASKS | Masks |
| height | height, displacement, disp, bump, h | no | TC_MASKS | Masks |
| emissive | emissive, emission, emit, glow, e | yes | TC_DEFAULT | Color |
| specular, cavity | specular, spec, s / cavity, cav | no | TC_MASKS | Masks |
| translucency, fuzz | translucency, transmission, sss, subsurface, thickness / fuzz, sheen | yes | TC_DEFAULT | Color |
| hdr | `.exr`, `.hdr` | no | TC_HDR | Color |

## 6. FabScript (optional C++ plugin for `fab.add`)

`unreal/plugins/FabScript` calls Fab's own `UFabBrowserApi::AddToProject` through reflection (FindFunction +
JsonObjectToUStruct + ProcessEvent: no link to Fab's private code), so Epic's exact workflow runs for every format,
packs included. Nothing needs it: without it `fab.add` downloads and imports in Python, and only unreal-engine packs
answer `unsupported` with this hint. To build it into a project on the box:
```bash
cp -r unreal/plugins/FabScript <Project>/Plugins/                      # next to the .uproject
<Engine>/Engine/Build/BatchFiles/Linux/Build.sh <Project>Editor Linux Development -Project=<Project>/<Project>.uproject
# Windows: Engine\Build\BatchFiles\Build.bat <Project>Editor Win64 Development -Project=...
```
Restart the editor; `python: unreal.FabScript.is_fab_loaded()` is True. Not compiled tonight (no engine here): if it
fails, the fixes are header paths in FabScriptLibrary.cpp (JsonObjectConverter.h is in JsonUtilities). For packs on
Linux also copy `libBuildPatchInstallerLib.so` from Epic's binary Fab plugin into `Engine/Plugins/Fab/ThirdParty/`.

## 7. API_NOTES

Verified by reading the UE 5.8.4 source on the source box (`/srv/ue-src/UnrealEngine-5.8.4`), not by running.
Paths are relative to the source root. "rg" = re-checked with ripgrep for this doc; the rest from the WP2 research
notes of the same night (same source, same lines).

| API (Python) | source | used by | notes |
|---|---|---|---|
| `AssetImportTask` fields filename, destination_path, destination_name, replace_existing, automated, save, options, factory, imported_object_paths, get_objects() | Engine/Source/Editor/UnrealEd/Public/AssetImportTask.h:36-93 | assets_import | `result` deprecated 5.1; setting `factory` bypasses Interchange (Developer/AssetTools/Private/AssetTools.cpp:3567) |
| `AssetTools.import_asset_tasks` | Engine/Source/Developer/AssetTools/Public/IAssetTools.h:542 | assets_import, mat | non-modal progress only |
| `InterchangeGenericAssetsPipeline` + `common_meshes_properties`, `common_skeletal_meshes_and_animations_properties`, `mesh_pipeline`, `animation_pipeline`, `material_pipeline` (`.texture_pipeline`), `import_offset_uniform_scale` | Engine/Plugins/Interchange/Runtime/Source/Pipelines/Public/InterchangeGenericAssetsPipeline.h:57-109 | assets_import | sub-pipelines are default subobjects |
| `force_all_mesh_as_type` (`InterchangeForceMeshType.IFMT_*`), `import_lods`, `recompute_normals`, `import_sockets` | .../Pipelines/Public/InterchangeGenericAssetsPipelineSharedSettings.h:71-155 | assets_import | |
| `skeleton` (common skeletal) | same file :203 | assets_import | TSoftObjectPtr |
| mesh pipeline `import_static_meshes`, `combine_static_meshes_behavior`, `collision`, `fallback_collision_type`, `build_nanite`, `generate_lightmap_u_vs`, `import_skeletal_meshes`, `create_physics_asset` | .../Pipelines/Public/InterchangeGenericMeshPipeline.h:73-236 | assets_import | `build_nanite` default True; enum digit spellings resolved fuzzily |
| `import_animations`; `import_materials`, `material_import`; `import_textures`, `flip_normal_map_green_channel` | InterchangeGenericAnimationPipeline.h:69; InterchangeGenericMaterialPipeline.h:85,107; InterchangeGenericTexturePipeline.h:32,48 | assets_import | |
| `InterchangeMaterialImportOption.IMPORT_AS_MATERIAL_INSTANCES` | InterchangeGenericMaterialPipeline.h:38-43 (rg) | assets_import (Megascans) | |
| `InterchangePipelineStackOverride.add_pipeline` | Engine/Source/Runtime/Interchange/Engine/Public/InterchangeManager.h:388-403 | assets_import | replaces the whole stack |
| `InterchangeManager.get_interchange_manager_scripted`, `create_source_data`, `import_asset`, `reimport_asset`; `ImportAssetParameters.is_automated/override_pipelines` | InterchangeManager.h:488, 804, 648, 711; 407-445 | assets_import | bool+out returns None on failure |
| `/Interchange/Pipelines/DefaultGLTFPipeline` | Engine/Config/BaseEngine.ini:3786 | assets_import | glTF stack = assets + this |
| `AbcImportSettings.import_type`, `conversion_settings` (scale, rotation, flip_u, flip_v); `AlembicImportType` | Engine/Plugins/Importers/AlembicImporter/Source/AlembicLibrary/Public/AbcImportSettings.h:310-340, 218-244 | assets_import | presets from Private/AbcImportSettingsCustomization.cpp:217-235 (rg) |
| `GroomImportOptions.conversion_settings` | Engine/Plugins/Runtime/HairStrands/Source/HairStrandsCore/Public/GroomImportOptions.h:22 | assets_import | |
| `UsdStageImportOptions` import_actors/geometry/materials/skeletal_animations/level_sequences | Engine/Plugins/Importers/USDImporter/Source/USDStageImporter/Public/USDStageImportOptions.h:55-74 | assets_import | only with automated=True; ignored if InterchangeOpenUSD is on |
| `Texture` srgb, compression_settings, lod_group, virtual_texture_streaming, max_texture_size, flip_green_channel, mip_gen_settings | Engine/Source/Runtime/Engine/Classes/Engine/Texture.h:1573, 1512, 1544, 1611, 1355, 1391, 1427 | assets_import, mat | enums in Classes/Engine/TextureDefines.h:28, 128, 391 |
| `StaticMeshEditorSubsystem` get/set_nanite_settings, get_lod_count, set_lods, get/set_lod_group, get_simple_collision_count, get_convex_collision_count, remove_collisions, add_simple_collisions, set_convex_decomposition_collisions, set_generate_lightmap_uv, set_allow_cpu_access, get_num_uv_channels | Engine/Source/Editor/StaticMeshEditor/Public/StaticMeshEditorSubsystem.h:217, 226, 152, 51, 98, 108, 259, 276, 338, 247, 310, 478, 490, 501 | assets_import, catalog | EditorStaticMeshLibrary is deprecated |
| `StaticMeshReductionOptions.auto_compute_lod_screen_size/reduction_settings`, `StaticMeshReductionSettings.percent_triangles`; `ScriptCollisionShapeType` | .../StaticMeshEditor/Public/StaticMeshEditorSubsystemHelpers.h:37-57 | assets_import | |
| `StaticMesh.get_num_lods/get_num_triangles/get_num_vertices/get_bounding_box/set_material`, `static_materials` | Engine/Source/Runtime/Engine/Classes/Engine/StaticMesh.h:2177, 2153, 2147, 2204, 2367, 1096 | catalog, mat | |
| `SkeletalMesh.get_bounds`, `skeleton`, `materials`, `physics_asset`; `SkeletalMeshEditorSubsystem.get_lod_count` | Classes/Engine/SkeletalMesh.h:842, 737, 910, 1527; Editor/SkeletalMeshEditor/Public/SkeletalMeshEditorSubsystem.h:252 | catalog, mat | no triangle count call |
| `AssetImportData.extract_filenames`, `scripted_add_filename` | Engine/Source/Runtime/Engine/Classes/EditorFramework/AssetImportData.h:150, 89 | assets_import | |
| `EditorAssetLibrary` / `EditorAssetSubsystem`: does_asset_exist, load_asset, save_asset, save_loaded_asset, save_directory, delete_asset, delete_directory, duplicate_asset, rename_asset, rename_directory, does_directory_exist, make_directory, list_assets, find_asset_data, set/get/remove_metadata_tag, get_metadata_tag_values | Engine/Plugins/Editor/EditorScriptingUtilities/Source/EditorScriptingUtilities/Public/EditorAssetLibrary.h:26-393; Engine/Source/Editor/UnrealEd/Public/Subsystems/EditorAssetSubsystem.h:54-400 | all | delete = force delete without confirmation; rename fails while the registry scans |
| `AssetRegistry.get_assets_by_path`, `scan_paths_synchronous`, `get_dependencies`, `get_referencers`; `AssetRegistryDependencyOptions` | Engine/Source/Runtime/AssetRegistry/Public/AssetRegistry/IAssetRegistry.h:311, 793, 564, 610, 146 | assets, catalog | |
| `AssetData.get_tag_value`, `is_redirector`, `package_name`, `asset_name`, `asset_class_path` | .../AssetRegistry/AssetRegistryHelpers.h:124, 87; CoreUObject/Public/AssetRegistry/AssetData.h:190-203 | catalog, assets | no `tag_values` attribute |
| registry tags ApproxSize, Triangles, Vertices, LODs, NaniteEnabled, Materials, CollisionPrims; SkeletalMesh Bones; Texture2D Dimensions, Format; AssetImportData | Engine/Source/Runtime/Engine/Private/StaticMesh.cpp:6224-6341; SkeletalMesh.cpp:4574-4656; Texture2D.cpp:716-726; Texture.cpp:1478-1498 | catalog | counts missing if saved while compiling |
| `AssetTools.FixupReferencers` | IAssetTools.h:658 | (not callable) | no UFUNCTION: resave route instead |
| `MaterialEditingLibrary` create_material_expression, connect_material_expressions, connect_material_property, get_material_expressions, delete_material_expression, get_num_material_expressions, recompile_material, get_statistics | Engine/Source/Editor/MaterialEditor/Public/MaterialEditingLibrary.h:242, 232, 141, 154, 145, 267, 113-130 | mat | recompile returns errors; delete_all buggy (:150) |
| MI: set_material_instance_parent, set/get_material_instance_scalar/vector/texture/static_switch_parameter_value, update_material_instance, get_*_parameter_names | MaterialEditingLibrary.h:408, 421-465, 490, 502-514 | mat | setters return False always; static switch `update_material_instance=False` |
| `MaterialExpression*` classes, pins and props (TextureSampleParameter2D UVs/RGB..., ScalarParameter, VectorParameter RGB..., StaticSwitchParameter True/False, Multiply A/B, LinearInterpolate A/B/Alpha, Power Base/Exp, Fresnel ExponentIn/BaseReflectFractionIn, ComponentMask "", Constant `r`, Constant2Vector `r`/`g`, Constant3/4Vector `constant`, `desc`) | Engine/Source/Runtime/Engine/Public/Materials/MaterialExpression*.h (Constant.h:17, Constant2Vector.h:18-21, Constant3Vector.h:18, Constant4Vector.h:18, MaterialExpression.h:195: rg) | mat | pin matching in MaterialExpressions.cpp |
| `MaterialProperty.MP_*`, `BlendMode.BLEND_*`, `MaterialShadingModel.MSM_*`, `MaterialDomain.MD_*`, `TranslucencyLightingMode.TLM_*`, `MaterialSamplerType.SAMPLERTYPE_*` | Engine/Source/Runtime/Engine/Classes/Engine/EngineTypes.h; SamplerType enum EngineTypes.h:946 | mat | Python names: PyGenUtil.cpp PythonizeName |
| Material `used_with_*` flags | Engine/Source/Runtime/Engine/Public/Materials/Material.h | mat | grooms: `used_with_hair_strands` |
| `AssetTools.create_asset` + `MaterialFactoryNew` / `MaterialInstanceConstantFactoryNew` | IAssetTools.h:348; AssetTools.cpp:4884-4932 | mat | existing asset + unattended: None, no dialog |
| `Scene.h` auto-exposure "pixel luminance (cd/m2)" | Engine/Source/Runtime/Engine/Classes/Engine/Scene.h:1991 (rg) | mat (nits) | emissive 1.0 = 1 nit |
| Fab `UFabBrowserApi` (GetAuthToken, OpenInNewTab, AddToProject(DownloadUrl, AssetMetadata), Login, Logout) | Engine/Plugins/Fab/Source/Fab/Private/FabBrowserApi.h:86-199 (AddToProject :120, OpenInNewTab :162: rg) | fab, FabScript | plain UFUNCTION(): `call_method` |
| `FFabAssetMetadata` fields | Engine/Plugins/Fab/Source/Fab/Public/Workflows/FabWorkflow.h:16-41 (rg) | FabScript | no BlueprintType |
| Fab console commands Fab.Login/Logout/SetEnvironment | Engine/Plugins/Fab/Source/Fab/Private/FabConsoleCommands.cpp:18-71 | fab | never Logout/SetEnvironment |
| persist login only on tab creation | Engine/Plugins/Fab/Source/Fab/Private/FabBrowser.cpp:337; FabAuthentication.cpp:200-266 | fab.login | |
| library endpoint `<fab>/e/accounts/<id>/ue/library?count=N` | Engine/Plugins/Fab/Source/Fab/Private/Teds/FabMyFolderIntegration.cpp:64-70 | fab.library | account id from the JWT `sub` (an assumption) |
| Megascans import: per-type pipelines | Engine/Plugins/Fab/Source/Fab/Private/Importers/QuixelGLTFImporter.cpp:144-406 | fab.import | |
| `InterchangeMegascansPipeline.megascan_import_type`, `MegascanImportType` (Model3D, Surface, Decal, Imperfection, Plant) | Engine/Plugins/Fab/Source/Fab/Private/Pipelines/InterchangeMegascansPipeline.h:32-39 (rg), :104-116 | fab.import | BlueprintType |
| `FJsonObjectConverter::JsonObjectToUStruct(obj, UStruct*, void*, ...)` | Engine/Source/Runtime/JsonUtilities/Public/JsonObjectConverter.h:239 (rg) | FabScript | |
| `FindFProperty<T>(const UStruct*, FName)` | Engine/Source/Runtime/CoreUObject/Public/UObject/UnrealType.h:7394 (rg) | FabScript | |
| `RenderingLibrary` / `SceneCapture2D` captures | WP10's view.py | assets.thumbnail | via view.turntable |
| `AssetEditorSubsystem.close_all_editors_for_asset(asset)` | Engine/Source/Editor/UnrealEd/Public/Subsystems/AssetEditorSubsystem.h:112 (class), :169-170 (UFUNCTION BlueprintCallable `int32 CloseAllEditorsForAsset(UObject*)`) (rg) | assets.free, assets.remove | returns the number closed |
| `MaterialInterface` (isinstance checks) | Engine/Source/Runtime/Engine/Public/Materials/MaterialInterface.h:351 `class UMaterialInterface : public UObject` (rg) | assets, mat, catalog | base of Material and MaterialInstance |
| `PointLight` (spawn_actor_from_class) | Engine/Source/Runtime/Engine/Classes/Engine/PointLight.h:11 `class APointLight : public ALight` (rg) | assets.thumbnail | its PointLightComponent: attenuation_radius, set_intensity |
| `unreal.new_object(type, outer, name, base_type)`, `unreal.load_class(outer, name)` | Engine/Plugins/Experimental/PythonScriptPlugin/Source/PythonScriptPlugin/Private/PyCore.cpp:2072, :2075 (rg) | fab | module functions of the Python plugin |
| `Object.call_method(name, args=(), kwargs={})` | .../PythonScriptPlugin/Private/PyWrapperObject.cpp:1135 (rg) | fab | calls any UFunction by name: args is a tuple |

## 8. Selftest

`film-ue selftest assets` (unreal/fmbridge/selftest/assets.py): writes its own OBJ, glTF and PNGs on the box,
imports them and checks sizes (an OBJ 50x48x90 box reads as 50x48x90 cm; a 0.3 m glTF cube as 30 cm), the catalog
and `assets.find "chair 90 cm tall"`, mesh settings, a re-import of a changed file, texture roles; builds all 12
masters and checks each compiles, PBR/presets/graph/instances (idempotent, read back), slot assignment, thumbnails
(4 views, not black), rename/move/duplicate/tag/refs/remove refusal/redirector fix/audit/remove; Fab status, a
loose-texture `fab.import`, and `fab.login`/`fab.library` when there is a sign-in. ~3 min (master compiles on a cold
DDC dominate). Needs: GPU. Not run there: `assets.save_all`, `fab.add` (needs a signed URL). On the fake engine it
runs end to end with every check passing (`tests/test_ue_assets_selftest.py`).

## 9. HANDOFF

State (2026-11-05, agent-02): everything above is written, unit-tested against the fake (tests/test_ue_assets_*.py)
and merged into ue-helpers in chunks; nothing has run in a real editor yet (no box tonight). First thing tomorrow:
`film-ue selftest assets` on the GPU box, then fix by its report. Most likely to need a fix, in order:

1. **Enum spellings with digits** (`InterchangeMeshCollision.CONVEX18_DOP`, `MegascanImportType.MODEL3D`,
   `ScriptCollisionShapeType.NDOP18`): `assets_import._enum` matches ignoring underscores and lists candidates in
   its error; check `dir(unreal.X)` once and pin them.
2. **OBJ units** (does Interchange read OBJ as cm?) and the glTF cube's 30 cm: the selftest's two size checks say.
3. **`already_imported`** relies on the AssetImportData registry tag's `RelativeFilename`: confirm its JSON shape.
4. **`assets.fix_redirectors`**: confirm a resaved referencer drops the redirector from the registry at once;
   otherwise add `ar.scan_paths_synchronous` before re-checking.
5. **`assets.thumbnail` lighting**: the temporary point light's intensity (8 r^2/100 cd) is a guess; tune by the
   selftest's thumbnail luma.
6. **`fab.login` on Linux offscreen**: does `OpenInNewTab` create the CEF tab (or its error tab) and trigger the
   persist login? `fab.library`'s account id from the JWT `sub` is an assumption; the endpoint is private.
7. **FabScript** has not been compiled.
8. **EditorScriptingUtilities**: done. `ops/assets.py` `EAL` falls back to the EditorAssetSubsystem when the plugin
   is off, every module of the bridge now imports it (577192b), and a test fails on any new direct
   `unreal.EditorAssetLibrary`. editor.doctor (B11) can treat the plugin as optional.
9. **mat.check's sampler expectations** come from the library's own masters only; for other materials it checks
   compilation only.

Also done after the WP: `film-ue texpack` (cli_texpack.py) and `film-ue export-spec` (cli_exportspec.py), both
unit-tested. Not done: Fab listing id -> signed URL is only the Playwright shim (untested against fab.com, and it
needs Playwright on the client); USD/Alembic/groom imports are untested even on the fake beyond their options.
