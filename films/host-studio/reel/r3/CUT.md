# Round 3: the cut, handoff (agent-06, 2026-11-05 night)

The 65 s and 45 s cuts, 1080p 16:9, are made on the GPU box with `r3/cut.sh`, which wraps `assemble.py` and `cut.py`.
Nothing is pulled to kali. This note covers the cut only. ROUND3.md has the round's state.

## Verified

- **The fixes preview.** `cut.sh preview --scale 0.5 --name karma-r3-preview-960x540` on `preview/night1`, uploaded
  to `shoot/r3/preview/karma-r3-preview-960x540.mp4`. It is 65.000 s, 960x540, with audio and Trey. It passed
  agent-09's gate, except (c): the green tint is open.
- **The tooling, dry-run end to end on the build host** with synthetic frames and the real mixes and cues:
  - `preview --scale 0.5` from 960x540 `.jpeg`: 1560 frames at -14.0 LUFS / -1.7 dBTP; the 45 s is 1080 frames at
    -14.1 LUFS / -1.7 dBTP. The captions land on cue (L2 at f1102).
  - `final --fill-from none --cuts 45s`: every 45 s deliverable, in about 6 min on the build host.
- **The mixes.** `audio/mix/mix.wav` is 65.000 s at -14.0 LUFS, TP -1.7, LRA 7.6. `mix_45.wav` is 45.000 s at
  -14.1 LUFS, TP -1.7. Both are 48 kHz 24-bit.
- **Box quirks, handled in `cut.sh`:**
  - The system ffmpeg is 4.4, so `cut.sh` fetches the static BtbN n8.1 with a sha256 check into `/srv/ue/tools/ffmpeg`.
  - MRQ writes `.jpeg` files.
  - uv is in `~/.local/bin`.

## Not verified

- **The 1080p final cuts were never run on real frames**: no every-shot finals existed before the box was terminated.
  The first real run is tomorrow (ROUND3 tomorrow item 7).
- **The caption word times are estimates** (`vo.py cues` from the built line WAVs). agent-10 is to check them by ear
  on a cast preview. That has not been done.
- **The operator's likeness in cast_op4** (iris brown? hair straight? tee hem fixed?): not verified by me. I have
  seen no frame of Host_Op, and under the face rule none comes to kali. That check belongs to agent-09's gate and
  agent-04.
- **The 65 s timing** (about 10 min) is an estimate from the 45 s dry run.

## Next steps for the finals (tomorrow, on the restored box)

1. **The checkout.** film/host-studio at or after 23db77b1 has everything (`final --cuts` came in with c5fad0e1).
2. **`cues.json`.** It is not in git (it lives under `out/`), and a new box will not have it. Rebuild it on the box:
   `cd tools && uv run python ../films/host-studio/reel/vo.py cues`, which writes
   `out/host-studio/reel/vo/cues.json`, the path `cut.sh` reads. Without it, `cut.sh` prints
   `no ...cues.json: captions timed from LINES` and the captions use the coarse LINES timings. A known-good copy is on
   kali at `.worktrees/agent-06/r3-frames/vo/cues.json` (text only, no face data).
3. **The finals.** Every shot at pick C goes in one fresh dir under `/srv/ue/reel/r3/<dir>`, as
   `<master frame:04d>.png`, either flat or one subdir per shot. Shots can come from more than one dir: list the
   extra dirs in `--fill-from` (comma-separated, under R3_FRAMES), and each shot is taken from the first pass that
   has all of it.
4. **Check.** `R3_FINAL=<dir> films/host-studio/reel/r3/cut.sh check` prints per shot the frames present, the size
   (1920x1080) and the luma. Every shot must have `missing: 0`.
5. **The cuts.** Run them one after the other, 65 s first:

       R3_FINAL=<dir> R3_CUT=/srv/ue/reel/r3/cut/final films/host-studio/reel/r3/cut.sh final --fill-from none --cuts 65s
       R3_FINAL=<dir> R3_CUT=/srv/ue/reel/r3/cut/final films/host-studio/reel/r3/cut.sh final --fill-from none --cuts 45s

   With `--fill-from none`, the run stops if any shot is missing. A rough cut is only for when time runs out: replace
   `none` with a pass that has the missing shot, such as `preview/<build>`, and the console shows `ROUGH CUT: ...`.
6. **QA from numbers only.** No sheets or frames go to kali when Host_Op is in the cut. The console prints frames,
   size, Mb/s and LUFS/dBTP per output. `cut.json` and `cut-45s.json` list where every shot came from, and the run
   fails on a wrong frame count or size. Targets: 1560 / 1080 frames, about -14 LUFS, true peak at or under -1 dBTP.
7. **Upload.** With Host_Op in the cut, everything in `/srv/ue/reel/r3/cut/final` except `overlays/` goes only to
   `ue-linux/private/renders/r3/cut/` with `--sse aws:kms`, followed by a head-object check. That covers:
   - the ProRes 4444 masters, `karma-reel[-45s]-1080p-textless-prores4444.mov`;
   - the H.264s with captions, `-1080p-h264.mp4`;
   - the clean H.264s, `-1080p-clean-h264.mp4`;
   - the captions, `.srt` / `.vtt`;
   - `cut.json`, `cut-45s.json` and `sheets/final.jpg`.

   Only a cut with no faces (Trey) may go to `shoot/r3/final/`.
