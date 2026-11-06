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
film-ue garment-fit --src $G/fit --garment tee --out $G/fit/out --only-slots shirt --drape-frames 40 \
    --blender /srv/ue/tools/blender-4.2*/blender
```
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
