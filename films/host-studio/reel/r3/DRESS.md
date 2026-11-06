# Round 3: dressing the presenters (her watch, her collar, garments following the body) - handoff

agent-02, end of night 1 (05 Nov). The box is terminated; the project with Host_Op is in `ue-linux/private/` (ROUND3.md,
"Saved"). Everything below is on film/host-studio.

## Verified (on the box, by agent-09's gate on cast3's MRQ frames)

- **Her collar (3b):** the round-3 overshirt (`props/overshirt.py` COLLAR knobs, built in headless Blender on the box by
  `props/overshirt_ue/r3_collar.sh`) rolls on her shoulders with her hair over it. Nothing went into her neck or
  through her hair in S15 f1110-1190 or S16 f1210-1300. The round-2 overshirt is kept as `SKM_Presenter_Overshirt_r2`
  (`props/overshirt_ue/use_overshirt.py`, `WHICH='r2'` to go back).
- **Her watch (3a):** in cast3 it sat flat on the back of her LEFT wrist at 3.6 cm from hand_l, S15-S18.
- **Her garments:** Top, Trousers and Overshirt follow her body in every shot (S17/S18 bind pose fixed).

## Not verified

- **Her watch has regressed:** cast_op2/3 rendered it 8.2 cm from hand_l. The cause was seq_dress keying the actor's
  stale offset. agent-09's fix (47c8b61b) keys the seat from dress_her's rule and drops the old transform tracks. It
  has **not run**. Pass: cast_gate's post-scrub watch check reads 3.6 cm (within 0.5).
- **His outfit (Host_Op or Trey):** `props/his_outfit_ue/dress_him.py` re-sets his garments' leaders and gives each
  garment Host/Body's anim sections in SEQ_Reel. It is merged, but whether it ran before cast_op4 is not recorded (the
  box's exec logs are in `private/logs`). It now refuses to run while TRASH_* components are on Host (ROUND3 item 11),
  which would otherwise be bound into SEQ_Reel. If an earlier run did bind TRASH_* garments, delete those bindings
  under Host in SEQ_Reel (probe_dress.py's "seq" lists them for her; check his the same way).
- **cast_op4, his look:** not mine, and I have not seen it (face rule). The iris (brown?), the hair (straight?) and the
  tee-hem patch (the trousers' waistband: agent-04) wait on cc-64d05f6e's review on the box.
- **Her hair green/teal (agent-09)** and **his weak lips (agent-09/agent-01)** are open; see ROUND3 item 15.

## Next, on the restored box (my part of ROUND3's "Next session" steps 3-5)

After the respawn (ROUND3 step 4: save, open, lod0 with no TRASH_), with whichever presenter the operator picks, and
**with no editor restart between this and the render**:

1. `host_swap.py` (`HOST='op'` or `'trey'`), then `perf.py drive_faces` and `perf.py place` (both presenters).
2. `film-ue exec films/host-studio/props/her_outfit_ue/dress_her.py`. It must return `ok: True`.
3. `film-ue exec films/host-studio/props/her_outfit_ue/seq_dress.py` (47c8b61b or newer). `watch_actor_rel_was` shows
   what it replaced.
4. `film-ue exec films/host-studio/props/his_outfit_ue/dress_him.py`. It must return `ok: True` and list his
   garments (Trousers, plus the default garment with the tee) in `seq_sections`.
5. `film-ue exec films/host-studio/props/her_outfit_ue/probe_dress.py`: every garment's leader is Body, her hair is
   MI_K_HerHair*, and the watch is on lowerarm_twist_01_l.
6. Then `level.save`, `build.py --cameras`, `probe_cam --check` (r3/CAMERAS.md), and the cast preview through
   agent-09's gate. The gate's wrist and collar crops cover 3a/3b; its post-scrub watch check must read 3.6 cm.

If anything re-creates her or his components after step 2 (an overshirt re-import, restore_leader, mh.cloth_inflate,
another host_swap), run 2-5 again.

## The finals (65 s + 45 s, 1080p, 16:9)

As ROUND3 "Next session" steps 6-8:

- 1080p PNG at pick C, one MRQ job per shot from its first frame, into a fresh dir, set shots first (~1560 frames,
  ~70 min).
- Then agent-06's cuts on the box:
  - `R3_FINAL=<dir> R3_CUT=/srv/ue/reel/r3/cut/final films/host-studio/reel/r3/cut.sh final --fill-from none --cuts 65s`
  - the same with `--cuts 45s`.
- Anything with Host_Op goes to `private/` only. Only no-face shots go to `shoot/r3/final/`.
- Before the presenter finals (S16, S13, S15, S17, S18), run steps 2-5 above once more if the editor restarted since
  the cast preview.

## Round 4: clipping on him (Host_Op), agent-02, 06 Nov

Measured, not guessed: `reel/r4/clip_pass.py` (editor-side, multi-tick, read-only) depth-captures each layer alone
(Body, Face, his tee, Trousers; hers Top/Trousers/Overshirt) from the shot's camera at 6 spread frames per shot (plus
agent-01's twist frames in S15/S17) and counts, per (under>over) pair, the pixels where the under layer comes out
through the garment: nearer by 0.3-3 cm (an opening's 10-25 cm drops out), in a cluster that meets an intersection
edge (an arm held in front of the tee does not), and not within 3 px of where the skin leaves the garment (his neck
above the collar edge). `fraction` = clipping px / garment px is agent-09's gate number. Stills and masks stay on the
box (face rule); `reel/r4/clip_sheet.py` makes the crop sheets (`--diag` for the A/B columns: scene, mask, body+face
hidden, garments hidden, each garment's albedo alone).

**Before (cast_op4 state, restored level):** Face>tee 0.004-0.032 in EVERY shot (S15 worst), Trousers>tee
0.005-0.007 in S17/S18, Body>tee 0, Body>Trousers 0; the tee's albedo has no skin colour. The orchestrator confirmed
on the diag sheet: the Face>tee blob is the orange patch left of his neckline, Trousers>tee the hip two-tone.

**Causes and fixes:**
1. The orange patch is his FACE mesh (MetaHuman's face runs ~10 cm below neck_01, to the clavicles): its lower neck
   stands ~1.8 cm out through the tee's front, left of the collar, in every shot. Not a hole: the tee's own depth
   there is continuous with the tee around it (reel/r4 depth layers). The body under the tee is already cut away by
   MetaHuman, and the rig is up to date with his body (agent-04), so the fix is the tee's inflate.
   **But the inflate never reached the render**: MetaHuman's fabric master (M_fabric_simpler) runs on Material
   Attributes, so the plain World Position Offset pin that mh.cloth_inflate (and neck_inflate.py's first build,
   /Game/FM/ClothOp) wired is ignored. Measured (reel/r4/wpo_probe.py, wpo_probe2.py): FM_Inflate 4 cm moved his
   tee 0.0 cm; a bare WPO material on the same tee moved it 4.5 cm. The same holds for any MetaHuman default
   garment studio.py's finish() inflated (Trey's tee too): their inflate was never drawn.
   Fix, take 1 (neck_fix.py, ClothOp3): the offset through Break/Make Material Attributes, with a broad neckline
   term (3 cm over 13 cm): the patch went, but the orchestrator on cast_op5: the collar read as a mock-neck and the
   chest padded (silhouette +15%). REJECTED.
   **Fix, shipped (props/his_outfit_ue/neck_patch.py, /Game/FM/ClothOp4, "patch3"):** the push only where his face
   pierces the tee. At 7 frames (S13-S18) the face verts that pierce the posed tee (geometry, reached from his neck
   axis only through the cloth) are mapped to a reference-pose copy of the tee (the space the material's pre-skinned
   position reads): they lie along the whole front collar arc, mostly 0.1-0.6 cm, and deeper (to 0.96 cm) in one
   place at the throat front. neck_inflate.add_patch: WPO += normal x FM_Patch x a spherical falloff (full inside
   FM_PatchR, none FM_PatchF further) round that deep cluster; the shallow arc gets a weak, narrow neckline term; the
   plain inflate everywhere is 0.15 cm. Values: FM_Inflate 0.15, FM_Neck 0.75 (Z0 144.75, Z1 147.75, front 0.1, bias
   0.5), FM_Patch 1.76 at (-0.71, 5.7, 148.68), R 3.95, F 3.0. host_swap.py applies them (TEE_KNOBS) on a fresh build
   (its NECK_MASTER chain, /Game/FM/ClothOp5, carries the patch term); after a body or garment change re-measure with
   neck_patch.py (FIND_ONLY=True to read). Do NOT run host_swap on the current level (it wears the ClothOp4 chain:
   cloth_inflate would try to reparent drawn instances); there, neck_patch.py re-tunes values in place.
2. The hip two-tone: his trousers were fitted (props/his_outfit.py) to TREY's body and tee, so on Host_Op their
   waistband stood through the tee's hem. Re-fit to his own body and tee on the box: `props/his_outfit_ue/r4_fit_op.sh`
   -> `SKM_Host_Trousers_Op` (imported 04:23 UTC), which studio.py's his outfit block picks for HOST op (Trey keeps
   his). Trousers>tee 0.0067 -> 0.0 in the AFTER pass; the orchestrator: fixed.
3. host_swap never inflated his tee (studio.py's finish() does on a full build only); it now does (see 1).

**The neck gate is in PIXELS** (the orchestrator's ruling): `neck_px` per Host frame = Face>tee clip pixels more than
1 cm (projected at the rim's depth) below the tee's front collar rim. The rim, per image column, is the tee's
front-surface top edge: a tee pixel whose pixel above has no tee, or tee more than 4 cm further (its inside back), with
his face present and nearer than the tee there; a column without one takes the nearest rim column's within 24 px.
Of those, a pixel within 5 px at 960 wide (3 at the 480 captures) of the OPENING (his face with no tee in front, or
the tee's inside more than BAND behind) is his neck at the collar's edge: `at_opening`, not counted (the
orchestrator's ruling on clip_host_fix.jpg: the residual hugging the collar the neckline term moved out is no clip).
Gate (agent-09, item e): neck_px.px == 0 per frame. The 3D vertex check (`neck`) is info only: it modelled an offset
that was never drawn.

**Numbers (worst per shot):**

| | S13 | S15 | S17 | S18 | tee silhouette vs pre-check |
|---|---|---|---|---|---|
| before4 (cast_op4 state) neck_px | 24 | 355 | 10 | 3 | (reference) |
| take 1, ballooned (Host_fix) | 0 | 0 | 0 | 0 | +15% |
| patch2 (plain inflate 0.5) | 0 | 20 | 0 | 0 | +4.5% |
| **patch3, shipped (Host_final 09:05 UTC)** | 0 | 3 | 0 | 0 | +1.2-1.7%, S15 twist hold +2.2% |

Silhouette: reel/r4/tee_silhouette.py (his tee's depth-layer pixels at the same frame and camera vs Host_after, whose
tee is its real shape: the dead inflate; gate 2% in S15/S17/S18). The orchestrator passed patch3 by eye (09:06) and
agent-09 signed the gate on it, waiving item e's last 1-3 px (S15 f1082-1128) and the +2.2%. Face>tee 0.032 ->
0.0071; Trousers>tee 0.0067 -> 0; Body>tee 0; Body>Trousers 0. Her (Presenter_final vs before): Body>Top 0.0001,
Face>Top 0.00077, Top>Overshirt 0.188 (her open overshirt, as before): within +0.01 everywhere.

**Her:** her pass reads high (Body>Top 0.10-0.19, Top>Overshirt 0.03-0.19) from her scoop neckline and the open
overshirt (qa.penetration read 0.34 there): her check is before vs after unchanged, with the watch and collar as
agent-09's gate measures them.

**The order on the box** (box tree /srv/ue/r3tree; T=that), after agent-04's apply:
1. `film-ue exec -c "EXPORT_DIR='his_outfit_op'; exec(open('$T/films/host-studio/props/his_outfit_ue/export_body.py').read())"`
   and `film-ue exec $T/films/host-studio/props/his_outfit_ue/export_alt_body.py`.
2. On the box shell: `sh $T/films/host-studio/props/his_outfit_ue/r4_fit_op.sh` (Blender 4.2 at /srv/ue/tools, CPU).
3. `film-ue exec -c "IMPORT_DIR='his_outfit_op'; SUFFIX='_Op'; exec(open('$T/films/host-studio/props/his_outfit_ue/import_outfit.py').read())"`
4. `film-ue exec -c "HOST='op'; NECK_CM=3.0; INFLATE_CM=0.5; CHECKOUT='$T'; exec(open(CHECKOUT + '/films/host-studio/unreal/host_swap.py').read())"`:
   trousers SKM_Host_Trousers_Op, tee_slots Shirt -> /Game/FM/ClothOp2/*_Inflate, leader_pass True. On a level whose
   tee already wears the dead /Game/FM/ClothOp chain: `props/his_outfit_ue/neck_fix.py` instead.
5. The re-dress (steps 1-5 of "Next, on the restored box" above, from drive_faces on).
6. `clip_pass.py` with TAG='after' for Host and Presenter (DIAG=False), then on the box
   `uv run --with pillow python clip_sheet.py <Host_before4> <Host_after> --out /srv/ue/reel/r4/review/clip_host.jpg`
   -> s3 private/renders/r4/review/ (KMS).

## Round 5 (agent-02): the WPO tee is replaced

The operator read the ClothOp4 tee as "heavy armor". Round 5 refits the tee's geometry (real ease, his face in the
collider, no WPO) and dresses it as its own `Tee` component: `reel/r5/garment.md`. `host_swap.py` now defaults to
INFLATE_CM 0; studio.py's default-garment lookup skips `Tee`.
