# Round 5, T3a: his tee fits his body, reads as cotton, and never clips at the neck (agent-02)

NOT RUN YET. For the orchestrator's one GPU session, after agent-10 merges `fleet/agent-02/r5-garment` into main
and the box's tree has it (`film-ue install` after the pull). T3b (agent-08) adds the cloth simulation on the same
Tee; this plan gives it a tee with real ease, no WPO, and per-vertex colours for its max distance.

Research: `docs/unreal/research/garment-fit.md`. Tools: `docs/unreal/garment.md`. Round 4's state: `r3/DRESS.md`
("Round 4: clipping on him").

## Why (the operator, round 4)

- "his chest still looks like he wore some heavy armor inside": his tee was MetaHuman's default garment pushed out by
  a material WPO (FM_Inflate 0.15 + FM_Neck 0.75 + FM_Patch 1.76 cm, /Game/FM/ClothOp4): an even, smooth, rigid
  shell. A WPO push is not a fit.
- "his shirt looks like it is clipping at the neck a little": his FACE mesh's lower neck (MetaHuman's head mesh runs
  to the clavicles) stands out through the collar; round 4's patch3 left 1-3 px at S15 f1082-1128 (waived; now
  unwaivable).

The fix: refit the tee's GEOMETRY to his uncut body AND his face (regional ease: collar 0.8, shoulder 0.6, chest
1.6, waist 2.4, hem 2.8 cm), weights from his body, no WPO; dress it as its own `Tee` component; measure with
`qa.clip` and `qa.garment_look` (the armor index), which would have failed round 4.

Throughout: `T` = the box's checkout of film/host-studio (with this branch merged), `G=/srv/ue/reel/r5/garment`.
Face rule: everything below writes on the box only; the FBXs and stills hold Host_Op's body/face. Nothing goes to
s3 except `private/`.

## 0. Probes (read-only, ~10 min; batch with the other tracks)

| id | command | expected | if not |
|---|---|---|---|
| G1 | `film-ue op editor.api_names` | `missing` lists none of: GeometryScript_*, AssetExportTask, Exporter, FbxExportOption | a name missing: report it to agent-02; garment.export / body.hide_under / qa.garment_look will fail on it (qa.clip needs none of them) |
| G7 | `film-ue exec $T/films/host-studio/reel/r5/tee_slots.py` | `SkeletalMesh` (the default garment): a slot with "shirt" in its name wearing `/Game/FM/ClothOp4/Host_<MI>_Inflate` (wpo FM_Inflate 0.15, FM_Neck 0.75, FM_Patch 1.76) and `plain` = the original MetaHuman instance path; shorts slots on M_FM_Hidden | write down SHIRT_SLOT (the slot name) and PLAIN_MI (`plain`); `plain` null: use `chain[-2]`'s source: the MI the ClothOp4 copy was made from (r3/DRESS.md) |
| G5 | `film-ue op mh.palette character=<his MH_ asset>` then `film-ue op garment.hidden_face_maps item=<the default garment's WI_>` | head/body maps with `max_shrink_distance` 0.0 (the 5.8.4 default: shrink off) | a head map with shrink > 0: note it (route B, research §3); nothing to change this round |
| G3 | `film-ue op qa.garment_look label=Host ref_body=/Game/Host/Unpacked/Host/Body/SKM_Host_BodyMesh sequence=/Game/Reel/SEQ_Reel 'frames=[1082,1150,1397]' motion_from=1140 motion_frames=12 out_dir=$G/look_r4 > $G/look_r4.json` (the ROUND-4 tee, before anything below) | `verdict` "armor", `terms.wpo.value` 2.66, `index` ≥ 0.5; `terms.motion.value` ~0 | index < 0.5 with wpo 2.66: still FAIL (the wpo rule); send look_r4.json's `terms` (numbers only) to agent-02 to recalibrate detail/motion |
| G3b | the same with `label=Presenter garment=Top ref_body=<her uncut body>` | her fitted top: `detail` above the round-4 tee's | detail lower than his: the detail term cannot tell them apart: drop its weight (`ramps`) and say so |

G3 is the check that would have caught the operator's "armor": its numbers go to agent-09's gate v2 as the round-4
line (`garment.armor_index`, `garment.wpo_cm`).

## 1. Export what the fit needs (~1 min)

```bash
film-ue op garment.export label=Host out_dir=$G/fit ref_body=/Game/Host/Unpacked/Host/Body/SKM_Host_BodyMesh \
    'sequences=["/Game/Reel/SEQ_Reel","/Game/Studio/SEQ_Line1","/Game/Studio/SEQ_Line2"]'
```
Expect: `files` with body, ref_body, face, garment_tee (`SkeletalMesh`'s mesh), garment_Trousers, anim_* (his reel and
line animations), every `[path, true, bytes > 0]`; `manifest.json`. `ref_body` must be his UNCUT body (round 4's
export_alt_body exported the same asset; his_outfit.py used it as uncut). If it reads as cut (the fit's `before` shows
`inside` ~0 but median > 5 cm on the chest), stop: the fit needs the whole body.

## 2. Fit the tee (headless Blender on the box, CPU, ~5-10 min)

```bash
film-ue garment-fit --src $G/fit --garment tee --out $G/fit/out --only-slots shirt --drape-frames 40 --morph-ref \
    --blender /srv/ue/tools/blender-4.2*/blender
```
(GPU session, probe `ref_body_probe.py`: NO uncut body of Host_Op exists in the project. SKM_Host_BodyMesh is uncut
(30455 verts, MetaHuman's full topology; his worn one is cut to 23780) and 0.45 cm median / 1.2 cm p95 from his
shape: `--morph-ref` morphs it onto his worn body.fbx and fills the cut torso smoothly. First report line: matched
~70-80%, the cut region moved median ~0.3-0.8 cm, max < 3; matched < 50% or max > 5 cm: STOP.)
(`--only-slots`: the substring of SHIRT_SLOT from G7, lower case; the shorts stay as they are, hidden.)

Expect `PASS` and, in the lines:
- `ease median ~0.3 -> 1.4-2.0 cm, spread < 0.6 -> >= 0.8, inside the body > 0% -> 0.00%` (before: the face's neck
  is inside the collar: round 4's 1.8 cm);
- per region (after): collar median >= 0.8, shoulder 0.6-1.0, chest 1.4-2.2, waist 2.0-3.0, hem >= 2.4 cm;
- every pose test `0 verts inside`.

If FAIL:
- "the ease is even ... a shell": `--drape-frames 60`;
- "pose test ... inside the body at frame F" near the neck: `--ease '{"collar": 1.1}'`; on the arms: `--ease
  '{"sleeve": 1.8}'`; under the arms (armpit): keep `--weights transfer` and add `--ease '{"shoulder": 0.9}'`;
- "closer than 0.5 cm": `--min-ease 0.6`.
Run again (each run rewrites `$G/fit/out`). Do not import a FAIL.

## 3. Import and dress the Tee (no WPO), ~2 min

```bash
film-ue op mh.import_garment fbx=$G/fit/out/garment_fit_tee.fbx dest=/Game/Host/Fit/SKM_Host_Tee_Fit
film-ue op mh.dress label=Host \
  'garments={"Tee": {"mesh": "/Game/Host/Fit/SKM_Host_Tee_Fit", "materials": {"<SHIRT_SLOT>": "<PLAIN_MI>"}}}' \
  'hide_slots={"SkeletalMesh": ["shirt"], "Tee": ["short"]}'
film-ue op mh.leader_check label=Host
film-ue exec $T/films/host-studio/props/his_outfit_ue/dress_him.py
```
Expect: import `bounds_cm` within 1 cm of the default garment's, `slots` = the default garment's; dress `ok: true`,
`hidden` lists SkeletalMesh's shirt slot(s) and Tee's shorts slots; leader_check every garment `ok`, bone gap < 0.1
cm; dress_him `ok: True` with `Tee` in `seq_sections`. Then `level.save`.
The default garment component stays (its shorts and shirt drawn with nothing): removing a Blueprint's own component
re-creates it on the next construction pass. `host_swap.py` now defaults to INFLATE_CM 0 (this branch); after any
respawn/host_swap/re-place, run step 3's dress + dress_him again.

## 4. Measure (the gate numbers), ~15 min

```bash
film-ue op qa.clip label=Host sequence=/Game/Reel/SEQ_Reel 'shots=["Reel_S13","Reel_S15","Reel_S17","Reel_S18"]' \
    'extra={"Reel_S15":[1082,1104,1128,1150,1220,1290],"Reel_S17":[1390,1397,1404]}' out_dir=$G/clip layer_masks=true
film-ue op qa.garment_look label=Host ref_body=/Game/Host/Unpacked/Host/Body/SKM_Host_BodyMesh \
    sequence=/Game/Reel/SEQ_Reel 'frames=[1082,1150,1397]' motion_from=1140 motion_frames=12 out_dir=$G/look > $G/look.json
film-ue garment-gate --clip $G/clip/clip.json --look $G/look.json --out $G/gate_garment.json --first-pass
```
(`--first-pass`: this accepted fit's first qa.clip pass is the silhouette reference, so silhouette_pct reads 0;
later passes give `ref_dir=$G/clip` to qa.clip and drop the flag.)
Expect (gate v2 lines, agent-09):

| item | line | round 4 | round 5 expected |
|---|---|---|---|
| garment.neck_px | ≤ 0 every frame | 3 px (S15 f1082-1128) | 0 (the face is in the fit's collider; collar ≥ 0.8 cm off it) |
| garment.pair_fraction (Body>Tee, Trousers>Tee, ...) | ≤ 0.001 | 0 after the trousers refit | 0 (the trousers sit 0.14 cm inside the OLD tee: the refit tee is further out) |
| garment.wpo_cm | ≤ 0.2 | 2.66 | 0 |
| garment.armor_index | < 0.5 | G3 (expected ≥ 0.5) | ≤ 0.35 with T3b's sim; without the sim the motion term alone is 1.0 x 1.5 weight: expect ~0.3-0.45 |
| garment.silhouette_pct | ≤ 2.0 vs this pass (later passes) | (r4's ref was the tight tee) | 0 here |
| garment.silhouette_ratio | ≤ 1.12 (guard, agent-09) | G3 | 1.04-1.10 |

`qa.clip` without `ref_dir` gives no silhouette_pct: round 4's reference (Host_after) was the tee's TIGHT shape, and
the refit is legitimately larger (~+4-8% px). The ±2% silhouette line returns in round 6 against this pass
(`ref_dir=$G/clip`). (Told agent-09.)

Look at it too (the operator will): `$G/clip/Reel_S15_1082_final.png` and the S15 hold (f1150), the neck and the
chest; the `_mask.png`s must have no magenta on him. `$G/look/Host_1150_look_normal.png`: folds visible on the chest
and at the hem (not a smooth gradient).

## 5. If the neck still shows (neck_px > 0)

1. The 3D pose tests passed but the render clips: a pose the anims in `$G/fit` do not hold (S15's torso twist is a
   perf.py layer, not an exported anim). Refit with `--ease '{"collar": 1.1}'` (steps 2-4). Do NOT add WPO.
2. Still: route B (research §3), for round 6: a head hidden face map with a grey band under the collar and
   `max_shrink_distance` 1.0 cm on a project copy of his default garment's wardrobe item, then a MetaHuman rebuild.
   Not this session: a rebuild re-creates his components (rounds 3-4) and needs its own re-dress and gate.

## 5b. The neck backstop (route B), only if (A)'s qa.clip still has neck_px > 0 (orchestrator, 06 Nov)

MetaHuman's own head hidden face map, set to SHRINK his face's lower neck under the collar (never cull), so a big
turn (S17 f1397) cannot bring the face mesh through. `reel/r5/neck_backstop.py`; verified on the 5.8.4 source
(research §3). Applied at ASSEMBLY: it costs a rebuild of his MetaHuman and the whole re-dress (~30-40 min).

1. `film-ue exec -c "STAGE='mask'; exec(open('$T/films/host-studio/reel/r5/neck_backstop.py').read())"` (read-only):
   expect `uv_valid` true, `covered` a few hundred to ~2000 face verts, `full_shrink` > 0, `png`
   /srv/ue/reel/r5/garment/neck_hidden.png (a dark band in the head's UV layout; white elsewhere). `covered` 0: the
   Tee is not on him (TEE='Tee').
2. `film-ue exec -c "STAGE='apply'; WI='<the default garment WI_ from G5>'; SHRINK_CM=1.5; exec(open(...).read())"`:
   `read_back` = texture set, max_cull -0.01, min_keep 0.9, max_shrink 1.5.
3. `film-ue op mh.add_item character=<his MH_ asset> item=/Game/Host/Fit/WI_Host_DefaultGarment_Neck slot=Outfits`,
   then `film-ue op mh.build character=<his MH_ asset>` (as round 4's look apply: forced build ~2 min).
4. The re-dress chain (r3/DRESS.md "Next, on the restored box" 1-5, his part): host_swap (HOST='op', INFLATE_CM 0
   is the default now), groom.set again (a respawn drops it), `perf.py drive_faces` + `perf.py place`, step 3's
   `mh.dress` (Tee + hide_slots) + `dress_him.py`, `mh.leader_check`, lod0 probe (no TRASH_), `level.save`.
5. `qa.clip` again (§4): neck_px 0 at S17 f1397. If the shrink shows as a dent at the collar opening (look at
   S13/S15 closeups), lower SHRINK_CM to 1.0 or RAMP to 2 cm (steps 1-4 again).

## 6. Risks

- `ref_body` is not uncut (G7/step 1 check): the fit would fit to the cut body's edges. Stop and report.
- The FBX round trip (UE -> Blender -> UE) of the default garment: its normals/tangents (`mesh_smooth_type` OFF,
  `use_tspace`) and UV seams are kept; if the Tee shades differently from the default garment in the same light
  (a seam line, a darker side), say so: the fix is in garment_fit.py's export, not in the material.
- The fit keeps Epic's tee shape and adds ease; it does not add folds by itself beyond the drape. The cotton READ also
  needs T3b's simulation and the material (roughness 0.8-0.9, a sheen). If `detail` stays low after the sim, the
  next lever is a wrinkle normal map on the Tee's material (round 6).
- `body.hide_under` is NOT used: MetaHuman already removed his body under the default garment, and the refit covers
  the same area. Its faces were never the problem (Body>tee 0 in round 4).

## 7. Outcome (GPU session, 06 Nov, agent-06 ran it)

| run | knobs | qa.clip | why the next |
|---|---|---|---|
| G3 (round-4 tee) | – | armor 0.538 (recalibrated), wpo 2.66 | the line round 4 fails |
| ref_body_probe | – | no uncut Host_Op body; SKM_Host_BodyMesh uncut, 0.45 cm off his | `--morph-ref` written |
| #1 | drape 40 | (pose test counted the hidden shorts) | ease too loose (2.9); test bug |
| #2 | = #1 | no-op (--weights transfer was the default) | – |
| #3 / #4 | drape 0 | rest fit right; #4 crashed in the new pose test, re-read #3's report | imported #3's FBX (Fit, pass 1) |
| pass 1 | transferred weights | neck 1 px; Trousers>tee 6.4% (3 cm, S17/S18) | the hem follows the thighs |
| pass 2 (Fit2) | --weights keep, collar 1.2 | Trousers 0; neck 112 px at S17 f1397 | the collar does not follow the turn |
| pass 3 (Fit3) | --weights blend, collar 1.2 | neck 3 px (S15); Trousers 0.0057 (0.5 cm) | the blend reaches the hem |
| pass 4 (Fit4) | blend collar,shoulder,sleeve; collar 1.5; after the Phase 5 redo | neck 1 px; Trousers 0.0053 | the new torso turn |
| **pass 5 (Fit5)** | **blend collar,shoulder,sleeve; collar 1.8, waist 3.0, hem 3.4** | **neck_px 0, Body>tee 0.00067, Trousers>tee 0, armor 0.109, wpo 0: PASS** | ships, pending the orchestrator's eye |

No cloth on the tee this round (the orchestrator: a closed shell, the failure class of her overshirt); the
`garment.cloth_*` items are NOT ATTEMPTED. The neck backstop (§5b) was not needed.

## 8. After Fit5 (06 Nov evening): what was learnt, where it stopped, the next session

Fit5 passed every number and FAILED by eye: the collar floated like a rolled cowl, the hem flared like a skirt. New
hard guards (core): qa.garment_look collar gap/roll (Fit5: 2.447 cm, 6/6 frames) and hem flare (ratio + the hem's own
outward angle; the ratio's reference-body capture is unreliable, trust the angle).

Root cause found late: with `--morph-ref` the fitted tees (Fit3-Fit6) were exported bound to the REFERENCE person's
skeleton (SKM_Host_BodyMesh's joints), so Unreal posed every part offset by the joint differences (Fit6: Epic's kept
collar 5.5 cm off, the tee 2.8 cm off the trousers). Fixed in core 868ef94e (his skeleton from body.fbx).

The neck backstop (head hidden-face-map shrink) emptied his whole assembly: MetaHuman rejects MaxCullValue < 0
(`TryCombineHiddenFaceMaps`, MetaHumanGeometryRemoval.cpp:45-52) and my "never cull" -0.01 failed the outfit. Fixed
(6646f917: 0.0 + mask floor 1/255) but not re-run; BP_Host_Op was restored from the 14:10 snapshot.

**Fit7** (his skeleton; collar 1.0, waist 2.6, hem 2.0 level, blend collar/shoulder/sleeve, no drape): neck_px 0
WITHOUT the backstop, armor 0.006, wpo 0, hem level. Open: collar gap 1.62 cm / roll (line 0.8), and the trousers.
HOLD at 21:15 IST (the orchestrator).

**Next session, in order (~45 min before previews):**
1. Fit8 = Fit7's command with the collar closer: run BOTH on CPU, pick by qa.garment_look collar + qa.clip neck:
   - A: `--ease '{"collar": 0.4, "waist": 2.6, "hem": 2.0}'` (a hugging crew neck: the gap metric reads ease +
     wall, so 0.4 should land ~0.6-0.8);
   - B: `--keep-regions collar --keep-ramp-cm 3` (Epic's own band, now on his skeleton: it should hug as in round 4;
     its neck poke is what the backstop is for: neck_px > 0 -> A).
   Gate: collar_gap <= 0.8 and roll 0, neck_px 0.
2. Trousers vs Fit8: the round-4 `_Op` vs `R5` qa.clip numbers (agent-06 measured _Op vs Fit7 at the hold: see
   ROUND5.md); keep whichever reads Trousers>tee <= 0.001; else `props/his_outfit_ue/r5_trousers.sh` with TEE = Fit8's FBX
   (~10 min CPU + import; it binds to his skeleton already).
3. If neck_px > 0 with A: the backstop (6646f917) on a COPY of the BP first (never on BP_Host_Op without a snapshot).
4. qa.clip + qa.garment_look + garment-gate --first-pass, then his S13/S15/S17 previews for the orchestrator's eye,
   then the finals.

Round 6 core list (agent-02): qa.garment_look's reference-body capture (silhouette, motion, hem ratio read nonsense on
the box); a real collar fold detector (normals of the rim, not only the radial spread); the single-layer cloth proxy
section with agent-08's FMCloth mapping; a garment-fit flag that refuses to export onto a skeleton other than the
character's.

## 9. Round 5b (06-07 Nov night): his neck HELD for round 6, what was learnt, the plan

**Decision (orchestrator, 01:12 IST):** the neck holds. Epic's default garment (WPO 0, round 4's trousers, charcoal)
passed by eye except the neck. The finals S13/S15/S17+S18 are rendered with **loop 2** (below) and the project is
put back to that state. The tee itself is not the open item: the COLLAR does not match HIS neck.

### The trade the mask cannot win
- Epic's band without WPO hugs (collar_gap 0.15-0.20 cm), but on the S15 turn his neck comes through it:
  neck_px 296, up to 1.79-1.87 cm deep (S15 f1082-1152; S13 ≤ 25 px; S17/S18 0).
- The neck backstop (head hidden-face-map SHRINK) trades that poke for a gap:

| loop | mask (neck_backstop.py) | SHRINK | neck_px (S15) | collar gap | by eye |
|---|---|---|---|---|---|
| 0 | none | - | 296 | 0.15-0.20 | skin through the band |
| 1 | RAMP 1, EDGE_W 0.3 | 3.0 | 9 | - | - |
| 2 | RAMP 1, EDGE_W 0.7, REACH 6 | 3.0 | 3 (≤ 0.5 cm) | 2.2-2.4 | ragged lip + dark crevice + a hole (S13/S15): the FINALS |
| 3 | 2 + DILATE 1.5/0.3 (visible skin) | 3.0 | 19 | - | worse (rim lost) |
| 5, 5b | RAMP 2.5, EDGE_W 0, BOUND 2.0 | 3.0 | = loop 2 | = loop 2 | the build did NOT re-bake (below) |
| 6 | RAMP 1, EDGE_W 0, BOUND 2.0 | 1.2 | 113 | ~1.2 | poke back |

  The gap is the collar's distance to the SKIN, and the shrink moves the skin: 3.0 opens a 2.3 cm crevice, 1.2 leaves
  the poke. Shrink cannot fix a collar that sits up to ~1.9 cm inside the neck on a turn.

### Causes found (measured)
- **The tear (the ragged lip, the hole):** the face mesh's OPEN bottom edge (its stitch to the body at the neck base)
  was inside the shrink: 92/92 open-edge verts near the neck shrunk (`shrunk_on_open_edge`, loop-2 params), moved
  verts down to z 143.9. `BOUND_CM` (b07e8fd1) keeps the edge and 2 cm above it unshrunk: loop 6 lowest moved z 144.6.
- **mh.build re-bakes the head hidden face map only when a WI SETTING changes**, not the texture: loops 5 and 5b
  (new mask; 5b under a new texture name set on the WI) measured loop 2's face to the vertex (1133 moved, max 2.987,
  z 144.1). Loop 6 also changed max_shrink_distance and took (max 1.195). `mask_diff.py` shows loop 5's PNG did
  differ (97 positions, lowest shrunk z +0.8 cm). Round 6: after a mask change, nudge a WI setting (or test it: an
  ALL-WHITE map must measure 0 moved) and prove every build with `shrink_live.py` (by_surface) before any pass.
- **The mask stage's UV seams:** it rasterises with ONE UV per welded vertex, so a triangle across a UV seam is
  drawn on the wrong island: 83 neck positions whose seam copies sample dark on one side and white on the other
  (`mask_seams.py`, grouped by position). The offline redraw (per-corner UVs) brought it to 12, but darkened
  positions outside the coverage (other face sections share UV 0) and the face.fbx export does not match the built
  face (2440 predicted vs 1133 measured). Not used.
- **qa.garment_look collar gap:** the stray-vertex fix (10th-smallest radius, bf43039f) is right, but tonight's 2.2-2.4
  is REAL (the shrunk skin), not that bug. **Roll** (local spread, 07b841bf + d20daa7d): 3.1-3.9 cm on Epic's band,
  worst cells 1-3 cm below the top: probably the depth reaching the shoulder line. Unvalidated on real data.
- **neck_px's rim** needs the face above the collar to be nearer than the tee; a receding (shrunk) neck drops the rim
  in those columns and the hugging band counts (loop 3's 19).

### Round 6 plan (agent-02), in order
1. **Fit the collar to HIS neck**, not the neck to the collar. Either:
   - the Fit path with the round-5b tools: `garment-fit --neck-ring-cm 2 --collar-slack 0` (455c320f/4d1fcfc9: the
     neck opening by shape joins the collar region; Fit9 R1/R2 reached collar ease 0.47/0.37 on CPU, never rendered),
     on Epic's ASSEMBLED tee shape (export the resized garment: `--keep-regions` floated because garment.export
     writes the asset's own shape, 5.3 cm off), with the collar band skinned to neck_01/neck_02 so it follows the S15
     turn; the closed shell moved as ONE wall (Fit7's dark chest ovals: tee_layers.py to confirm);
   - or a neck-ring-matched garment (a crew neck whose opening is cut to his neck girth at the S15 pose).
   Gate: neck_px 0 with NO backstop, collar_gap ≤ 0.8, by eye at S13 f1040 / S15 f1085, f1128 vs round 4.
2. **Backstop only as a ≤ 0.5 cm safety**: SHRINK ≤ 0.5, EDGE_W 0, BOUND_CM 2.0, the mask stage rasterising
   per-triangle UVs of the SKIN section only, `mask_seams` SPLIT 0 before the build, and the re-bake proved
   (`shrink_live` max = SHRINK).
3. Metrics: collar roll depth/band from Epic's band geometry + a real-data must-fail (Fit5 re-dressed); neck_px's rim
   from the tee's own top edge; the all-white build test as a pipeline check.

Assets kept for round 6: T_Host_NeckHidden (loop 2, on the finals), T_Host_NeckHidden5, T_Host_NeckHidden6;
/srv/ue/reel/r5/garment/neck_hidden.loop{2,4,5,6}.png. Her overshirt: round 5's cloth.remove left the clothing data
in the asset (32 → 128 MB); restored from project_r4_snapshot.
