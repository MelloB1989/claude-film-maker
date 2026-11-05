# Round 3 cameras: handoff (agent-11, 2026-11-05, end of day)

The reel's cameras are `Reel_<shot>` cine cameras made by `build.py` from `shots.py` (keys) and `motion.py` (easing,
focus). Every shot is 16:9 on a full-frame 36 x 20.25 back.

## Verified

- **His shots follow his body.** S13 and S15 take his eye height through `shots.lifted()` (`EYES_HIM` against the
  174 cm the v2 frames were drawn for). `shots.py` holds agent-04's measurements of Host_Op on his mark: eyes 168.7,
  knee 49.4 (the calf joint). The top of the head, ~180.5, is an estimate (agent-07's measure read 181.7). S13/S15
  sit 5.3 cm below v2. S17/S18 (the two-shot wide) are unchanged.
- **Framing rules, offline.** `framing.py` projects every presenter shot's frames. It checks: cut above the knee (no
  shoes), the head whole for whoever the shot is about, and his head under the sign in S13/S17/S18. All pass for these
  numbers, and also across 165-186 cm. `test_framing.py` + `test_cut.py`: 23 pass.
- **The camera gate.** `r3/probe_cam.py SHOTS --check` reads each live `Reel_` camera on the box (read-only). It
  compares with the plan (1 cm, 0.1 deg, 0.05 mm of focal or filmback, one actor per label). All 13 were OK at
  20:36 UTC, after agent-07's hand fix of the bindings.
- **V05.** The final_c V05 rendered at 18:51 is on plan. final_c_v05_old (18:13) was 1.27x tight from unsaved editor
  state, not the camera. The 19:00 camcheck found V01, V02 and S11 finals off too: ROUND3 item 5 re-renders them.
- **Bindings (core, main a9107015).** seq.rebind / seqcore bind now require exactly their label's actor. A
  possessable is kept by object name, so perf.py's Test cameras could take a deleted Reel_ camera's name and its keys.

## Not verified

- **Not yet run on the engine:** `build.py --cameras` (film/host-studio 3700417f). cameras() now re-makes and checks
  the camera cuts itself (ROUND3 17: dead cut GUIDs after a cameras-only run). The cut code is the same calls that
  build() made.
- **His shots with Host_Op have not been looked at.** I have seen no still of S13/S15/S17/S18 with the new body.
  framing.py is geometry from heights, not a picture.
- **The likeness (cast_op4: iris colour, hair, the tee hem):** not my area and not judged by me. See ROUND3.md item 15
  and agent-04/agent-09's notes.

## Next, on the box, before any presenter final

1. Pull film/host-studio (3700417f or later) into the box tree. It includes main a9107015.
2. `cd tools && uv run python ../films/host-studio/reel/build.py --cameras`. It respawns, rebinds and keys every
   `Reel_` camera, then makes and checks the cut. It ends `cut: 13 shots, -12 to 1572`, or exits with the cut it found.
3. `uv run python ../films/host-studio/reel/r3/probe_cam.py V01,V02,V03,V04,V05,S11,S12,N01,S13,S15,S16,S17,S18 --check`:
   all OK. Any OFF line or second actor means stop; find it before rendering.
4. `film-ue op level.save`, then stills of S13, S15, S17 and S18 at start, middle and end through their Reel_ cameras.
   Send them to agent-11 (or whoever has cameras) for framing: knees out, head whole, his head under the sign, her
   head whole in S15.
5. Then the finals (ROUND3 items 5-6): set shots V01/V02/S11 re-rendered; presenter shots S13-S18 at pick C with
   whichever presenter passes the cast gate. Run probe_cam --check again before each batch.

The camera code doesn't depend on which presenter passes. If the old Host (Trey, eyes 174) is used instead of Host_Op,
set his numbers back with `python3 films/host-studio/reel/framing.py --him eyes=174 top=182 knee=51`, commit, and rerun
steps 2-4.
