# Round 3: hand-off from the night driver (agent-07)

This is the box-side state at the end of round 3, night 1, with the exact steps to the deliverables. ROUND3.md is the
round's summary; this file is how to pick up the box work. Times are UTC.

## Where things are

The GPU box was stopped, then terminated, at the end of the night. Everything below now lives only in S3, under
`s3://rf-render-788655295054-aps1/ue-linux/private/` with SSE-KMS. Only the box role (ue-workstation) can read
private/; kali's profile gets 403 there, as intended. Every count and encryption check below was a head-object run on
the box before it stopped.

| What | Where (under private/) | Check |
|---|---|---|
| Project HostStudio, with Host_Op (character, BP, grooms, identity, capture) | `project/HostStudio` | 1416 objects, aws:kms; synced 21:09:48 after level.save + assets.save_all at 21:09:39 |
| DDC 5.8.4 | `ddc/5.8.4` | 48589 objects, aws:kms; 21:12:59 |
| Operator capture source (re-ingest) | `operator-face/` | 8 objects, 96 MB |
| Set finals at pick C | `renders/r3/final_c` | 986 = 986 |
| Calibration passes | `renders/r3/cal_A`, `cal_B`, `cal_C` | 26 = 26 each |
| Cut dir (previews, reports) | `renders/r3/cut` | 45 = 45 |
| Host_Op cast previews S13-S18, 960x540 | `renders/r3/preview/cast_op`, `cast_op2`, `cast_op3`, `cast_op4` | 614 = 614 each; `_mp4/karma-r3-cast-op{,2,3,4}-960x540.mp4` (2-4 carry the mix) |
| Night logs + the night's handover | `renders/r3/logs` | 15 files |

The Epic sign-in is in the box's `epic_s3` (secrets/epic, aws:kms), saved by ue-epic.sh whenever the editor stops.
The Trey preview (no face data) is outside private/, at `shoot/r3/preview/karma-r3-preview-960x540.mp4`.

**Not kept, gone with the disk:**
- the box-side QA stills and sheets (qa/*, hair_ab/*, hairpop*, hair_cover);
- superseded passes (final/, final_c_v05_old, cut tests);
- the night1 preview frames;
- Saved/ and Intermediate/.

## The saved level (what a restore opens)

- **Host is Host_Op** (BP_Host_Op), respawned fresh at 21:09. Its last look is agent-04's round 4:
  - hair WI_Hair_S_SlickBack, brows WI_Eyebrows_M_Full, mustache WI_Mustache_M_Stubble, no beard;
  - SKIN_UV (0.62, 0.58), IRIS_UV (0.92, 0.12);
  - groom.set melanin 1.0, redness 0.05;
  - the outfit block as in r3-operator-mh 2009a24c.
- **Dressing and face:** dressed (dress_him, seq_dress, restore_leader, drive_faces, dress_her with from_hand 3.6 cm).
  His live components have no TRASH_.
- **Her (Presenter):** placed and dressed. Hair (c) is still open.
- **Cameras:** probe_cam --check gives 13/13 OK.
  - The Reel_V02/S11/S12/N01/S13 bindings had been taken by perf.py's stage cameras (Test_agent-10_*), because
    possessables bind by object name. They were rebound by hand, and perf.py cleanup removed the Test_ actors.
  - The camera cuts were re-made. 955cb129 now makes cameras() re-make and check the cuts itself.
- **Trey (BP_Host) is still in the project as the fallback:** `host_swap.py HOST='trey'`, then a respawn
  (L.spawn replace=True + seq.rebind Host), then the dressing.

## Not verified (decide these first)

1. **Likeness in cast_op4:** nobody has checked it by eye. Look at `cast_op4/_mp4/karma-r3-cast-op4-960x540.mp4`
   against the capture's front/left/right frames, on a box (never off it).
   - **Iris brown?** IRIS_UV 0.92/0.12 is agent-04's guess, chosen because 0.08/0.95 rendered light blue. It has
     not been measured.
   - **Hair straight?** SlickBack replaced SweptUp, which read curly.
   - **Tee hem patches in S17/S18 gone?** tee_slots = {Shirt: MI_WI_DefaultGarment…, Short: MI_K_HisHidden}. agent-04
     says the patches are not slot holes; see 475137ad.
2. **His lips:** S13 ratio 1.49. It fails on the old mouth box, which was set on Trey's framing. Rerun with
   agent-09's projected box: `cast_gate.py mouth --shots S13,S16`, then `cast_gate.py frames … --mouth`.
3. **Her watch:** cast_gate's scrubbed measure reads 8.2 cm (3.6 unscrubbed). Check with watch_scrub.py's numbers
   (agent-07-out/watch_scrub.txt) before a final.
4. **Her hair teal ends (c):** S16 ends-L green_px is about 0.24 at f1236/f1300. No A/B variant has helped yet
   (overshirt hidden, cvars, cards/helmet black, melanin 0.3). agent-09 owns it.
5. **His lod0 pin:** it must hit live components only (no TRASH_) before any presenter final. agent-09 won't sign
   finals otherwise.

## Next steps to the finals (65 s + 45 s, 1080p, 16:9)

On a new box restored from private/ (`film-ue set --project-s3 …/private/project/HostStudio --ddc-s3
…/private/ddc/5.8.4`, then `sync project down`, `sync ddc restore`, editor start):

1. **Tree:** install film/host-studio at its head on kali and in the box tree, including agent-11's exact rebind
   (d88dfa4d) and 955cb129.
2. **Choose the presenter:** watch cast_op4. If Host_Op passes the likeness review, keep him. Otherwise take another
   look round (agent-04) and a cast_op5. If he still fails, swap back to Trey.
3. **Make the level final-ready:** `level.open`, `perf.py drive_faces`, dress_her last. Then level.save → level.open
   → `build.py --lod0 on` (check for no TRASH_) → level.save → `probe_cam.py <13 shots> --check`. Exit 1 means no
   render.
4. **Cast preview and gate:** cast preview S13-S18 into a fresh `preview/<name>`, then agent-09's gate:
   - `cast_gate.py engine`, `frames --mouth`, `hue --frames 1236,1300`;
   - only numbers leave the box;
   - upload with `film-ue sync dir up` to private/ (dry-run first).
5. **Set finals into a FRESH dir** (for example final_d; copy 30-final.yaml with `out_dir: "${out}/final_d"`).
   - V01, V02 and S11 must be re-rendered: final_c holds them on stale cameras.
   - V03, V04, V05, S12 and N01 in final_c match the current cameras. They can be re-rendered, or copied over from
     final_c if you check that the cameras haven't changed since.
   - Afterwards run final_check.py + camcheck.py.
6. **Presenter finals S13, S15, S16, S17, S18:** one batch per shot, each into final_d, only after agent-09 signs the
   gate. The hair fix is part of that sign-off.
7. **Cuts:** `R3_FINAL=final_d films/host-studio/reel/r3/cut.sh final --fill-from none --cuts 65s`, then
   `--cuts 45s`. These are the deliverables (MP4/MOV, srt/vtt, cut.json).
8. **Face rule:**
   - With Host_Op in the cut, the frames and cuts go only to `private/renders/r3/…` via `film-ue sync dir up` with
     KMS.
   - Only no-face set shots and frame-free reports go to shoot/r3/final/.
   - Nothing showing Host_Op reaches kali.

## Box gotchas from the night

- The box is launched with **instanceInitiatedShutdownBehavior = terminate**, and its root volume has
  DeleteOnTermination = true.
  - Any OS shutdown terminates it: a manual `shutdown`, or idle-guard's `shutdown -h now` after 45 idle minutes.
  - Power off with `film-ue down` only.
  - During long quiet syncs, touch `/srv/ue/.guard-keepalive`.
  - The TTLHours tag is enforced off the box.
- **build.py:** run `cameras()` only via build.py (955cb129). Called alone, it used to leave the cut track on dead
  binding GUIDs ("no camera cut on Reel_S13" at apply time).
- **mh.build:**
  - It skips with `changed: false` when its fingerprint misses a groom change. Use `force=true` after a grooms or
    look stage.
  - It refuses while a cloud request runs: retry until mh.textures has finished.
  - A rebuild re-instances the placed BP, which leaves stale TRASH_ components. Respawn the Host
    (`L.spawn(replace=True)` + `seq.rebind`) before saving the map.
- **level.save** crashed or restarted the editor once (20:44). The editor reopens the level from disk, so per-instance
  state that wasn't saved is lost: drive_faces, the dressing, lod0. Re-apply it before rendering.
- **film-ue tools:**
  - `film-ue push` needs the editor's bridge. With the editor stopped, send files through `film-ue sh` (base64).
  - `film-ue sync epic save --dry-run` ignores `--dry-run` and saves.
- **Face rule on kali:** a QA still is face data if its source render ran while Host_Op was on the level. Tonight
  that was 19:00:29 (a crashed swap attempt), 19:27:27-19:28:50, 20:27:18-20:27:57, and from 20:33:50 on. The only
  kali files from those windows were 8 hairpop pair/crop images. They were quarantined by mv (nothing deleted); the
  operator decides in the morning.
