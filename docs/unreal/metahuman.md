# metahuman: MetaHuman creation by code (WP3, `mh.*`)

The whole MetaHuman Character editor (Creator) is driven as ops, with no UI:
- **Create:** from a preset, a copy or blank.
- **Shape:** body measurements and face (preset blend, coefficients, landmarks).
- **Look:** skin, eyes, eyelashes, teeth, makeup, grooms with their colours, outfit.
- **Cloud and build:** Epic's cloud rig and textures, then assemble into a Blueprint.
- **On the placed actor:** garments of your own, kept on leader pose; props riding bones; a numeric clipping check.

A `character` spec converges all of it, and `mh.describe` reads any of it back as JSON.

Code: `unreal/fmbridge/ops/mh/` (character, appearance, wardrobe, cloud, build, actor, spec).
- Spec: `tools/filmtools/unreal/mh_spec.py` + `schemas/character.schema.json` + `examples/unreal/character/`.
- Tests: `tools/tests/test_ue_mh*.py`, the fake `tools/tests/fakeunreal/ext_mh.py`.
- Selftest: `unreal/fmbridge/selftest/mh.py`.

## 1. Recipes

Every op has an SDK twin: `ue.mh.<verb>(...)`. Ops that take longer than a call (`~` in `film-ue describe mh`)
are multi-tick jobs: `--async` plus `film-ue job <id> --wait`.

**A character from a spec (the normal way)**
```bash
film-ue plan examples/unreal/character/presenter.yaml      # what would change, and why
film-ue apply examples/unreal/character/presenter.yaml     # converge; "converged": true when the 2nd plan is empty
film-ue op mh.describe path=/Game/Characters/Trey/MH_Trey  # check: body, skin, wardrobe, rigged, build.bp
```
Or in the editor, in one job: `film-ue op mh.apply spec=@presenter.yaml`. `stop_before=mh.rig` shapes the
character without the cloud.

**Start a character**
```bash
film-ue op mh.presets                                                    # Ada, Jorge, ... (Creator core data)
film-ue op mh.add path=/Game/Characters/Ava/MH_Ava preset=Ada            # or source=<character> | blank=true
film-ue op mh.duplicate source=/Game/Characters/Ava/MH_Ava path=/Game/Characters/Ava/MH_Ava_Old   # a variant
```
Check: `changed` is true the first time and false on a re-run. A wrong preset name gives `not_found` with the near names.

**Body: by measurements**
```bash
film-ue op mh.body_constraints path=/Game/Characters/Ava/MH_Ava         # names, current values, ranges (cm)
film-ue op mh.body character=/Game/Characters/Ava/MH_Ava 'measurements={"Height": 168, "Waist": 61, "Hip": 94, "Fat": -1.8}'
film-ue op mh.body character=/Game/Characters/Ava/MH_Ava from_character=/Game/Host/Presenter_F   # copy a body
```
Check: `body` echoes what the solver holds. `warnings` names any value outside the range for this height. A body
change after a rig makes `mh.describe` `rig_stale`, so re-rig, re-texture and rebuild.

**Face: blend presets, set coefficients, move landmarks**
```bash
film-ue op mh.face path=/Game/Characters/Ava/MH_Ava 'blend={"Ada": 0.7, "Vivian": 0.3}'
film-ue op mh.face_landmarks path=/Game/Characters/Ava/MH_Ava           # indices and positions
film-ue op mh.face path=/Game/Characters/Ava/MH_Ava 'landmarks={"12": [0, 0, 0.4]}'
film-ue op mh.preview path=/Game/Characters/Ava/MH_Ava label=AvaPreview  # live actor, no rig needed; then a still
```
Check: take a still of the preview (`look.camera` + `look.still`, or WP10's `view.still`). The blend is linear in the
face model's coefficients. It is **experimental**: judge the still before spending a cloud rig on it.

**Skin, eyes, eyelashes, teeth, makeup**
```bash
film-ue op mh.skin character=... u=0.55 v=0.45 roughness=1.0 texture_resolution=4k \
  'settings={"freckles": {"density": 0.4, "mask": "Type1"}, "accents": {"cheeks": {"redness": 0.65}}}'
film-ue op mh.eyes path=... 'both={"iris": {"iris_pattern": "Iris003", "primary_color_u": 0.2, "primary_color_v": 0.6}}'
film-ue op mh.eyelashes path=... 'settings={"type": "LongCurl", "melanin": 0.9}'
film-ue op mh.teeth path=... 'settings={"overbite": 0.2, "worn_down": 0.1}'
film-ue op mh.makeup path=... 'settings={"lips": {"type": "Natural", "color": [0.3, 0.06, 0.05]}, "eyes": {"type": "ThinLiner"}}'
film-ue op mh.settings_fields path=... which=makeup                      # every field and its current value
```
Field names are the engine's, in snake_case or CamelCase. Enums go by name (`LongCurl`, `Type1`, `Iris003`).
Colours are `[r, g, b]` linear. A wrong field or enum gives `bad_args` with the valid names.

**Hair, beard, brows: item and colour**
```bash
film-ue op mh.wardrobe kind=Hair                                         # groom items (Beards, Eyebrows, Mustaches, ...)
film-ue op mh.groom character=... slot=Hair item=WI_Hair_L_Straight melanin=1.0 redness=0.05
film-ue op mh.groom character=... slot=Beard item=none
film-ue op mh.item_params character=... slot=Hair                        # Melanin, Redness, Roughness, Whiteness, DyeColor, ombre, highlights
film-ue op mh.item_set character=... slot=Hair 'params={"bUseOmbre": true, "OmbreU": 0.2, "OmbreIntensity": 0.6}'
```
Melanin runs from 0 (blond) to 1 (black); redness from 0 to 1. In the reel, preset hair at melanin 0.8 / redness
0.25 read **green** in warm light, and full melanin fixed it (films/host-studio studio.py). These parameters are
baked by the build. To tune a groom on a placed actor per shot (width, density, the sky-lighting guard), use WP10's
`groom.*` ops.

**Outfit (Creator's clothing)**
```bash
film-ue op mh.wardrobe kind=Clothing
film-ue op mh.add_item character=... item=<WI_...> slot=Outfits 'params={...}'    # mh.item_params lists its colours
film-ue op mh.clear_slot character=... slot=Outfits
```

**The cloud rig, textures and build** (one Epic sign-in per box: `film-ue epic-login`)
```bash
film-ue op mh.auth_status                                  # signed_in true/false (null on Windows: assumed)
film-ue op mh.rig character=... --async ; film-ue job <id> --wait      # ~30 s; changed:false when up to date
film-ue op mh.textures character=... --async ; film-ue job <id> --wait # ~20 s; needs the rig first
film-ue op mh.can_build path=...                           # if not: why, and which op to run
film-ue op mh.build character=... name=Ava                 # ~3 min cinematic on an L4; BP_Ava under <folder>/Unpacked/Ava
film-ue op mh.build character=... name=AvaLow pipeline=optimized quality=medium   # lighter LODs
```
Check: `mh.describe` shows `rigged: true`, `has_high_res_textures: true`, `build.bp`, and `build.stale: false`.
Order matters: **rig, then textures, then build**. A skin change discards the textures, so fetch them again.

**Garments of your own on a placed MetaHuman** (FBX authored in cm on the MetaHuman skeleton)
```bash
film-ue op mh.import_garment fbx=/abs/on/box/her_top.fbx dest=/Game/Outfits/Ava/SKM_Ava_Top
film-ue op level.spawn label=Ava asset=/Game/Characters/Ava/Unpacked/Ava/BP_Ava
film-ue op mh.dress label=Ava 'garments={"Top": {"mesh": "/Game/Outfits/Ava/SKM_Ava_Top", "materials": {"M_Top": "/Game/.../MI_Top"}}}' \
  'hide_slots={"SkeletalMesh": ["short"]}'
film-ue op mh.leader_check label=Ava                       # pass: every garment leads from Body, bone gap < 0.1 cm
film-ue op mh.clip_check label=Ava garment=Top             # pass/metric: body points poking through (experimental)
film-ue op level.save
```
Run `mh.leader label=Ava` after anything else touches the actor's components, after a level load, and before a
render.

**A prop on a bone** (earrings, a watch)
```bash
film-ue op mh.attach label=Ava prop=AvaWatch bone=lowerarm_twist_02_l      # makes it Movable first
```

**A character as a spec (round trip, B27)**
```bash
film-ue op mh.export path=/Game/Host/Host_Trey > trey.json  # then change asset/from and apply it for a twin
```

**Headless Epic sign-in** (docs/linux/engine.md §12c)
- The services take an exchange code: `film-ue op mh.login exchange_code=<code>` sets
  `MetaHuman.Cloud.Config.ExchangeCode`.
- Or they take the saved sign-in from `film-ue epic-login` (device code, persists ~6 months).
- Launch the editor with `-NoMetaHumanAccountPortalLoginFallback` so a missing sign-in fails at once.
- `mh.rig` fails fast anyway (`unsupported`, hint `film-ue epic-login`) when Linux has no saved credential.

## 2. Op reference (`film-ue describe mh`)

| op | what | flags |
|---|---|---|
| `mh.presets` `mh.find` `mh.describe` `mh.export` | read: presets; characters in a folder; full state; state as a spec | read |
| `mh.add` `mh.from_preset` `mh.duplicate` `mh.remove` | create (preset / source / blank), legacy create, variant, delete | idempotent |
| `mh.body_constraints` `mh.body` | body measurement constraints (read / converge) | |
| `mh.face` `mh.face_landmarks` | face: blend, coefficients, landmark deltas (applied once) | experimental |
| `mh.skin` `mh.eyes` `mh.eyelashes` `mh.teeth` `mh.makeup` `mh.settings_fields` | look settings | commit only on change |
| `mh.wardrobe` `mh.palette` `mh.add_item` `mh.clear_slot` `mh.groom` `mh.item_params` `mh.item_set` | wardrobe and item parameters | no duplicate palette entries |
| `mh.auth_status` `mh.login` `mh.rig`~ `mh.textures`~ | Epic sign-in, cloud rig and textures | needs-epic-login, slow |
| `mh.can_build` `mh.build` `mh.preview` | assemble; why it cannot be built; live preview actor | slow (build blocks) |
| `mh.components` `mh.drive_face` `mh.import_garment` `mh.dress` `mh.leader` `mh.leader_check` `mh.attach` `mh.clip_check`~ `mh.cloth_inflate`~ `mh.garment` | the placed actor | |
| `mh.apply`~ | converge to a `character` spec in one job | slow |

## 3. Spec kind `character`

The schema is `tools/filmtools/unreal/schemas/character.schema.json` and the planner is `filmtools.unreal.mh_spec`
(`SPEC_KINDS`, order 30). The fields:
- `asset`, `from`.
- `body` (short form `{Height: 168}`, or `{measurements, from_character, reset}`).
- `face` (`blend` | `coefficients`, plus `landmarks`).
- `skin` (`u`, `v`, `roughness`, `texture_resolution`, and any skin settings).
- `eyes` (`both`/`left`/`right`), `eyelashes`, `teeth`, `makeup`.
- `grooms` (`{Hair: {item, melanin, redness, params}, Beard: none}`), `outfit`.
- `rig` (`full` | `joints` | `none`), `textures`, `build` (`{name, pipeline, quality, build_path, common_path}` or
  `false`).
- `dress` (`{label, garments, hide_slots}`).

```yaml
kind: character
version: 1
name: Maeve
asset: /Game/Characters/Maeve/MH_Maeve
from: {preset: Ada}
face: {blend: {Ada: 0.7, Vivian: 0.3}}
body: {Height: 170, Waist: 64}
skin: {u: 0.2, v: 0.55, freckles: {density: 0.65, mask: Type2}}
grooms: {Hair: {item: WI_Hair_L_Straight, melanin: 0.35, redness: 0.85}}
build: {name: Maeve}
```

**The plan cascades:**
- A body or face change re-rigs.
- A skin change re-fetches the textures.
- Anything the build bakes rebuilds.
- The face is compared by the fingerprint `mh.face` records (`describe.face.applied`), so a blend or landmark move
  is applied once.

**Examples** (one per look): `presenter.yaml` (a fit man, buzz cut with a little grey, stubble),
`blended-face.yaml` (a new face from two presets, freckles, red ombre hair, natural makeup), `older-variant.yaml` (a
variant 25 years on), `shape-only.yaml` (no cloud), `dressed.yaml` (garments of your own on the placed actor).

## 4. Gotchas (the operator's lessons and what the source says)

- **Bodies via constraint copies.** `get_body_constraints` hands out copies. Edit copies, pass the whole list back
  with `set_body_constraints`, then `commit_body_state` (or nothing is kept). `mh.body` does this.
- **The Host_Trey pattern.** A presenter is a preset copied to the project (`/Game/Host/Host_Trey`). Its body is set
  by constraints, it is cloud-rigged and built into `/Game/Host/Unpacked/<name>/BP_<name>`, and the studio script
  places that Blueprint and dresses it. Re-shaping means re-rig, re-texture and rebuild, then the studio script
  re-places and re-dresses (films/host-studio/bodies.py).
- **Garments in cm.** Export FBX garments in cm on the MetaHuman skeleton, with an unscaled root. A root bone that
  carries a scale (bones in metres under a x100 root) shrinks to nothing as soon as the body poses it.
  `mh.import_garment` checks the bounds and `mh.dress` checks the root scale.
- **Leader pose must persist.** Changing any instance component of a Blueprint actor reruns its construction script,
  which re-creates the others, and a re-created garment has lost its leader: it stands in its bind pose while the
  body moves. Set leader pose **last, on every garment, in one pass**. `mh.dress` does it, and `mh.leader` re-does it.
  Run `mh.leader_check` before rendering.
- **Static actors cannot attach to bones.** A spawned prop is Static, and a Static root silently refuses to attach
  to a moving bone. `mh.attach` makes it Movable first.
- **A skin commit discards the cloud textures** (`CommitSkinSettings`, its doc comment, MetaHumanCharacterEditorSubsystem.h:895-901).
  `mh.skin` commits only when a value differs, so a re-run does not throw away 20 s of downloads.
- **Rig before textures.** The texture service signs in through the rig ("User not logged in, please autorig before
  downloading source face textures", MetaHumanCharacterEditorSubsystem.cpp:4218). The build needs both
  (`CanBuildMetaHuman`, .cpp:2238-2272).
- **Rig state is not exposed to Python** (`GetRiggingState`, `HasFaceDNA` are C++ only). `mh` reads it as
  `can_build_meta_human` or `has_face_dna_blendshapes` (a full rig), plus the `FM.MH.Rig` fingerprint tag.
  A joints-only rig without textures reads as `rigged: null`.
- **The cloud outcome is only in the log.** The engine reports success and failure as notifications and
  `LogMetaHumanCharacterEditor` lines ("Auto-Rigging finished in N seconds", "Auto-Rigging of Face failed with code
  'X'"). `mh.rig`/`mh.textures` read the editor log from the moment they ask.
- **The cloud services wait for a browser sign-in** when there is none: the account portal fallback,
  MetaHumanCloudAuthentication.cpp:258-270. Headless that is forever. Hence the fail-fast check and
  `-NoMetaHumanAccountPortalLoginFallback`.
- **The build blocks the editor** for its whole run (~3 min cinematic on an L4; P10 measured 178 s, peak RSS
  15.6 GB). It is one engine call and cannot be split. Do not schedule renders on the same editor meanwhile.
- **A second `try_add_item_from_wardrobe_item` adds a second palette entry** ("Hair_S_BuzzCut_Binding (2)").
  `mh.add_item` reuses the existing key (`get_item_keys_for_wardrobe_item`).
- **Face edits on a rigged character drop the rig**, as Creator's sculpt does. `mh.face` calls `remove_face_rig`
  first (`unrig=true`); then re-rig.
- **The exchange code is echoed to the log** when set with a console command (`ProcessUserConsoleInput` writes to
  GLog). Use a fresh single-use code (~5 min validity).
- **LODs:** assembly quality is the LOD control (`pipeline=optimized quality=low|medium|high`; cinematic is always
  cinematic). `AssemblySettings` on the character and `PipelineOverride` on the build parameters are not editable
  from Python (VisibleAnywhere / no specifiers).
- **Hair strands and the sky light:** indoors, `r.HairStrands.SkyLighting 0` (README trap; WP10's `groom.sky_guard`).
- **A face played by Sequencer** needs `ANIMATION_SINGLE_NODE` (`mh.drive_face`). The chest then pokes through the
  shirt unless face and body are one skeleton (`anim.bake_follow`, `anim.head_to_body`; README).

## 5. API_NOTES (verified on the UE 5.8.4 source box, /srv/ue-src/UnrealEngine-5.8.4)

Paths are relative to `Engine/Plugins/MetaHuman/MetaHumanCharacter/Source/` unless they start with `Engine/`.
In the paths, Sub = `MetaHumanCharacterEditor/Public/MetaHumanCharacterEditorSubsystem.h` and Lib =
`MetaHumanCharacterPalette/Public/MetaHumanCollectionBlueprintLibrary.h`. Python names are the snake_case of the
reflected names. Every row was read in the header/source (✓).

| Python | engine | where | ✓ |
|---|---|---|---|
| `unreal.MetaHumanCharacterEditorSubsystem` (`get_editor_subsystem`) | UMetaHumanCharacterEditorSubsystem | Sub:479 | ✓ |
| `try_add_object_to_edit`, `is_object_added_for_editing`, `remove_object_to_edit` | UFUNCTION BlueprintCallable | Sub:528, 532, 540 | ✓ |
| `spawn_meta_human_actor(c, keep_transient)` | SpawnMetaHumanActor | Sub:684 | ✓ |
| `can_build_meta_human(c, log_error)` | CanBuildMetaHuman (bool overload) | Sub:776; impl .cpp:2238-2290 | ✓ |
| `build_meta_human(c, params)` | BuildMetaHuman | Sub:787 | ✓ |
| `commit_head_model_settings` / `commit_skin_settings` / `commit_eyes_settings` / `commit_makeup_settings` | Commit*Settings | Sub:881, 901, 1062, 1088 | ✓ |
| `request_texture_sources(c, params)` | RequestTextureSources | Sub:916 | ✓ |
| `commit_face_state(c)` | CommitFaceState | Sub:1143 | ✓ |
| `get_face_landmarks(c)` -> list, `translate_face_landmarks(c, idx, deltas)` | Get/TranslateFaceLandmarks | Sub:1276, 1296 | ✓ |
| `get_face_model_coefficients(c)` -> list, `set_face_model_coefficients(c, list)` | Get/SetFaceModelCoefficients | Sub:1307, 1318 | ✓ |
| `request_auto_rigging(c, params)`, `remove_face_rig(c)` | RequestAutoRigging, RemoveFaceRig | Sub:1355, 1364 | ✓ |
| `commit_body_state(c)` | CommitBodyState | Sub:1573 | ✓ |
| `get_body_constraints(c, scale)`, `set_body_constraints(c, list)` | Get/SetBodyConstraints | Sub:1926, 1937 | ✓ |
| `unreal.MetaHumanRigType.JOINTS_ONLY / JOINTS_AND_BLEND_SHAPES` | EMetaHumanRigType | Sub:131 | ✓ |
| `unreal.MetaHumanCharacterAutoRiggingRequestParams` (`rig_type`, `report_progress`, `blocking`) | struct | Sub:152 | ✓ |
| `unreal.MetaHumanCharacterTextureRequestParams` (`report_progress`, `blocking`) | struct | Sub:138 | ✓ |
| `unreal.MetaHumanCharacterEditorBuildParameters` (`pipeline_type`, `pipeline_quality`, `animation_system_name`, `absolute_build_path`, `name_override`, `common_folder_path`, `enable_wardrobe_item_validation`) | struct | MetaHumanCharacterEditor/Public/Subsystem/MetaHumanCharacterBuild.h:25 | ✓ |
| `unreal.MetaHumanDefaultPipelineType` (CINEMATIC, OPTIMIZED, UEFN) | enum | MetaHumanCharacter/Public/MetaHumanCharacterAssemblySettings.h:14 | ✓ |
| `unreal.MetaHumanQualityLevel` (LOW, MEDIUM, HIGH, CINEMATIC) | enum | MetaHuman/MetaHumanSDK/Source/MetaHumanSDKRuntime/Public/MetaHumanTypes.h:53 | ✓ |
| `unreal.MetaHumanCharacter`, `unreal.MetaHumanCharacterFactoryNew` (AssetTools.create_asset) | UCLASS; factory has no dialog | MetaHumanCharacter/Public/MetaHumanCharacter.h:206; MetaHumanCharacterEditor/Public/MetaHumanCharacterFactoryNew.h | ✓ |
| character props `skin_settings`, `eyes_settings`, `makeup_settings`, `head_model_settings`, `has_high_resolution_textures`, `fixed_body_type`, `internal_collection`, `has_face_dna_blendshapes` | UPROPERTY (Visible/EditAnywhere) | MetaHumanCharacter.h:387-402, 515, 528 | ✓ |
| skin settings: `skin` (`u`, `v`, `roughness`, `face_texture_index`, ...), `freckles` (`mask`: NONE/TYPE1-3), `accents` (8 regions), `desired_texture_sources_resolutions` (RES2K/4K/8K) | FMetaHumanCharacterSkinSettings and parts | MetaHumanCharacter/Public/MetaHumanCharacterSkin.h:14, 100, 136, 271, 340 | ✓ |
| eyes `eye_left`/`eye_right` → `iris` (`iris_pattern` IRIS001-009, `primary_color_u/v`, ...), `pupil`, `cornea`, `sclera` | FMetaHumanCharacterEyesSettings | MetaHumanCharacterEyes.h:34, 241 | ✓ |
| head model `eyelashes` (`type` NONE/SHORT_SPARSE/.../LONG_THICK_CURL, `melanin`, ...), `teeth` (`tooth_length`, `overbite`, ...) | FMetaHumanCharacterHeadModelSettings | MetaHumanCharacter.h:162; Eyes.h:271; Teeth.h:28 | ✓ |
| makeup `foundation`, `eyes` (`type`), `blush`, `lips` | FMetaHumanCharacterMakeupSettings | MetaHumanCharacterMakeup.h:196 | ✓ |
| body constraint `name`, `is_active`, `target_measurement`, `min_measurement`, `max_measurement`, `.copy()` | FMetaHumanCharacterBodyConstraint | MetaHuman/MetaHumanCoreTechLib/Source/MetaHumanCoreTechLib/Public/MetaHumanCharacterBodyIdentity.h:89 | ✓ |
| collection `default_instance`, `get_slot_names()`, `get_all_item_keys()`, `get_item_keys_for_wardrobe_item(wi)`, `get_item_slot_name(k)`, `get_item_display_name(k)` | UMetaHumanCollection; palette ScriptMethods | MetaHumanCharacterPalette/Public/MetaHumanCollection.h:303; Lib:269-306 | ✓ |
| `try_add_item_from_wardrobe_item(slot, wi)` -> key or None | TryAddItemFromWardrobeItem | MetaHumanCharacterPalette/Public/MetaHumanCharacterPalette.h:94 | ✓ |
| instance `set_single_slot_selection(slot, key)`, `get_slot_selection_data()` -> `.selection` (`slot_name`, `selected_item`) | UMetaHumanInstance | MetaHumanCharacterPalette/Public/MetaHumanInstance.h:220, 263; MetaHumanPipelineSlotSelection.h:53-56 | ✓ |
| `selection.get_selected_item_path()`, `key.to_asset_name_string()`, `key.is_null()`, `unreal.MetaHumanPaletteItemKey()`, `unreal.MetaHumanPaletteKeyBlueprintLibrary` | ScriptMethods | Lib:45, 51, 235 | ✓ |
| `instance.get_instance_parameters(path)`; param `get_float/set_float/get_bool/set_bool/get_color/set_color/get_name/set_name/get_string/set_string`; `type` | FMetaHumanCharacterInstanceParameter | Lib:146-174, 334 | ✓ |
| groom instance parameters `Melanin`, `Redness`, `Roughness`, `Whiteness`, `Lightness`, `DyeColor`, `bUseOmbre`, `OmbreU`, ... | UMetaHumanDefaultGroomPipelineMaterialParameters (property names = parameter names) | MetaHumanDefaultPipeline/Public/Item/MetaHumanDefaultGroomPipeline.h:26-101; impl AddRuntimeParameter .cpp:53 | ✓ |
| cloud log lines read by `mh.rig`/`mh.textures` | "Auto-Rigging finished in", "Auto-Rigging of Face failed with code", "Download of source face/body textures finished/failed", "User not logged in, please autorig" | MetaHumanCharacterEditor/Private/MetaHumanCharacterEditorSubsystem.cpp:3488, 3509, 3549, 4194, 4214, 4218, 4310, 4330, 4334 | ✓ |
| exchange-code CVar `MetaHuman.Cloud.Config.ExchangeCode`; `-NoMetaHumanAccountPortalLoginFallback` | MetaHumanCloudAuthentication | MetaHuman/MetaHumanSDK/Source/MetaHumanSDKEditor/Private/Cloud/MetaHumanCloudAuthentication.cpp:262, 315-353 | ✓ |
| `unreal.SystemLibrary.execute_console_command`, `get_console_variable_string_value` | KismetSystemLibrary | Engine/Source/Runtime/Engine/Private/KismetSystemLibrary.cpp:571, 593 | ✓ |
| `set_leader_pose_component(body)`, `leader_pose_component`, `get_ref_pose_transform(i)`, `get_bone_index(b)` | USkinnedMeshComponent | Engine/Source/Runtime/Engine/Classes/Components/SkinnedMeshComponent.h:313, 1884, 2053, 1156 | ✓ |
| `set_anim_instance_class`, `set_animation_mode` | USkeletalMeshComponent | Engine/.../Components/SkeletalMeshComponent.h:1096, 1246 | ✓ |
| `unreal.SubobjectDataSubsystem` (`k2_gather_subobject_data_for_instance`, `add_new_subobject`, `rename_subobject`), `unreal.SubobjectDataBlueprintFunctionLibrary`, `unreal.AddNewSubobjectParams` | instance components on a placed Blueprint actor | proven by films/host-studio/unreal/studio.py on the reel | ✓ (in use) |
| `unreal.FbxImportUI`, `unreal.AssetImportTask`, `unreal.FBXImportType.FBXIT_SKELETAL_MESH`, `unreal.FBXNormalImportMethod` | FBX import | proven by props/her_outfit_ue/import_outfit.py, P7 | ✓ (in use) |
| `unreal.MaterialFactoryNew`, `unreal.BlendMode.BLEND_MASKED`, `unreal.MaterialExpressionConstant`, `unreal.MaterialProperty.MP_OPACITY_MASK`, `unreal.MaterialEditingLibrary` | the hidden-slot material | as look.py | ✓ (in use) |
| `unreal.ComponentMobility.MOVABLE`, `unreal.AttachmentRule.KEEP_WORLD` | attach | proven by studio.py | ✓ (in use) |
| `unreal.GeometryScript_SceneUtils.copy_mesh_from_component`, `unreal.GeometryScriptCopyMeshFromComponentOptions` (`requested_lod`), `unreal.GeometryScriptMeshReadLOD` (`lod_type`, `lod_index`), `unreal.GeometryScriptLODType.RENDER_DATA` (posed skinned mesh) | GeometryScripting plugin | Engine/Plugins/Runtime/GeometryScripting/Source/GeometryScriptingCore/Public/GeometryScript/SceneUtilityFunctions.h:32, 80; GeometryScriptTypes.h:47-58, 91-94; ModelingComponents SceneComponentToDynamicMesh.cpp:441-498 | ✓ |
| `unreal.GeometryScript_MeshSpatial.build_bvh_for_mesh`, `find_nearest_point_on_mesh` (`GeometryScriptTrianglePoint`: `valid`, `triangle_id`, `position`), `unreal.GeometryScriptSpatialQueryOptions` | MeshSpatialFunctions | MeshSpatialFunctions.h:59, 76, 113; GeometryScriptTypes.h:212-221 | ✓ |
| `unreal.GeometryScript_MeshQueries.get_all_vertex_positions`, `get_triangle_face_normal`; `unreal.GeometryScript_List.convert_vector_list_to_array`; `unreal.DynamicMesh` | MeshQueryFunctions, ListUtilityFunctions | MeshQueryFunctions.h:152, 220; ListUtilityFunctions.h:188 | ✓ |
| `unreal.MetaHumanPipelineSlotSelectionBlueprintLibrary.get_selected_item_path`, `unreal.MetaHumanCharacterInstanceBlueprintLibrary.get_instance_parameters_for_item` (static forms of the ScriptMethods) | BP libraries | Lib:223-241, 315-334 | ✓ |
| legacy `mh.cloth_inflate`/`mh.drive_face`: `unreal.MaterialEditingLibrary.get_scalar_parameter_names`, `unreal.MaterialExpressionVertexNormalWS`, `unreal.MaterialExpressionAdd`, `unreal.MaterialInstance`, `unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation`, `unreal.AnimationMode`, `unreal.get_engine_subsystem` | carried over unchanged from ops/mh.py | proven on the reel (unreal/README.md trap "never change a material while it is drawn") | ✓ (in use) |
| `unreal.UnrealEditorSubsystem`, `unreal.EditorActorSubsystem`, `unreal.AssetToolsHelpers`, `unreal.Paths`, `unreal.Vector`, `unreal.Rotator`, `unreal.LinearColor`, `unreal.Text`, `unreal.Material`, `unreal.SkeletalMeshComponent` | core editor API | shared with every area | ✓ (in use) |

Not exposed to Python (worked around):
- `GetRiggingState`, `HasFaceDNA`, `IsAutoRiggingFace`, `IsRequestingHighResolutionTextures`, the FText
  `CanBuildMetaHuman`, `CommitFaceEvaluationSettings`.
- `AssemblySettings` (VisibleAnywhere) and `PipelineOverride` (no specifiers).
- Creator's own preset blend tool. Its linear equivalent is `mh.face blend`.

## 6. Selftest (`film-ue selftest mh`)

`unreal/fmbridge/selftest/mh.py`.

**Part 1, no cloud, ~2 min:**
- Presets.
- Add from a preset and blank, with idempotency.
- Body, face blend and landmark-once, skin, eyes, eyelashes, teeth, makeup, groom with colours, item parameters.
- Palette, describe/export, a variant, can_build.
- A preview still.
- `mh.apply` twice: the second run changes nothing.
- Actionable errors for bad names.

**Part 2, only with the Epic sign-in (capability `mh_cloud`), else noted:**
- Rig (records `rig_s`) and its up-to-date skip, textures (`textures_s`), build (`build_s`) and its skip.
- The Blueprint placed, dressed with an extra garment (leader check, bone gap metric), clip check (metric).
- A prop on `hand_l`, and a still.

It takes ~6 min with the cloud. Unit-tested on the fake: `tests/test_ue_mh.py::test_selftest_runs_on_the_fake`.

## 7. HANDOFF (agent-04, 2026-11-05)

**Done:**
- Ops package `ops/mh/` (43 ops, legacy names and signatures kept).
- The fake `ext_mh.py`, 21 unit tests, the spec kind (schema, planner, 5 examples, convergence tests on the fake).
- The selftest and this guide.
- Every engine API is in API_NOTES.

**Untested on an engine (the GPU box decides; first things to look at):**
1. `mh.face blend`: does a linear mix of coefficients look like a face? Judge the still.
2. Python reading of `has_face_dna_blendshapes` (VisibleAnywhere without BlueprintReadOnly: `get_editor_property`
   should work).
3. The palette key names `mh.export` writes, and whether `mh.add_item` resolves them back. The core-name match is in
   wardrobe.py `_item_path`.
4. `mh.clip_check` sign convention: the garment's face normals pointing outward. If every point "pokes", flip the
   sign in `clip_check`.
5. Whether a joints-only rig is detected (`rigged: null`).
6. `mh.textures` waits for `has_high_resolution_textures`. Confirm it turns true only after both downloads.
7. The `instance.get_instance_parameters(path)` ScriptMethod name on UMetaHumanInstance. `_params` falls back to
   `MetaHumanCharacterInstanceBlueprintLibrary.get_instance_parameters_for_item` when it is missing.

**Next:**
- B27 is covered by `mh.export` + apply. Run it on Host_Trey on the box.
- B28 (groom tuning on placed actors) went to agent-09 as `groom.*`, with the parameter mapping.
