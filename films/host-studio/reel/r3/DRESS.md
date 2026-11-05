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
