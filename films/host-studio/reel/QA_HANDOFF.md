# QA handoff (agent-09): the presenter gate, end of night 1 (05 Nov, ~21:50 UTC)

Read with ROUND3.md (state, items 1-17). This file is the presenter gate's own state: what is verified and what is
not, and the exact commands for tomorrow. Numbers only: no Host_Op frame, crop or still has been on kali (face rule).

## Signed

- **night1 fixes preview** (Trey + her), `shoot/r3/preview/karma-r3-preview-960x540.mp4`. Signed with (c) as
  "pop fixed (LOD 0), green tint OPEN".
  - (a) lips: engine ratio her 12.6, him 8.6.
  - (b) watch 3.6 cm.
    - The penetration flags were false positives: the magenta in the stills is her open scoop neckline.
  - (d) blinks 27-29/min, both-eyes-shut 0 frames, head turns her +26/+28 deg, him -53/-21 deg (agent-01).
  - Noted for the finals:
    - S15 pops at f1082-1084 and f1132-1136;
    - a grey under-layer edge on her S16 neckline.

## NOT signed: cast_op3, cast_op4 (Host_Op as him)

cast_op4 numbers are in `agent-07-out/qa_cast_op4/` (`cast_cast_op4.json`, `cast_gate_engine.json`,
`hue_cast_op4.json`).

| check | cast_op4 | gate | state |
|---|---|---|---|
| (a) her S16 frame lips | 3.25 | >= 3 | pass |
| (a) his S13 frame lips (Host_Op) | 1.49 (Trey, same box: 2.15) | >= 3 on frames, rises vs Trey | **FAIL**: his face rig gives less mouth for the same curves |
| (a)/(d) engine: jaw curves, blinks | pass both | | pass, but this reads the curves, not the rig's output |
| (b) watch | 8.2 cm at every frame | <= 8.0, target 3.6 | **FAIL**: seq_dress re-keyed a stale seat. Fix merged (47c8b61b), never run |
| (b) her garments | 0.34-0.37 (S16) | 0.01 | her scoop neckline: a false positive, judged on night1's still |
| (b) his garments (Host_Op) | S13 0.036-0.052, S15 0.117, S17/S18 ~0.03 | 0.01 | **unjudged**: could be the tee-hem patch. Needs the magenta still read on the box |
| (c) hair green_px, ends screen-left | f1236 0.239, f1300 0.217; S16 every 8th frame 0.13-0.27 | <= 0.05 per region | **FAIL**, unchanged since night1 |
| (c) crown | 0.03-0.17 | <= 0.05 | fails in about half the frames |

### Not verified, and how to verify each without frames on kali

- **The iris is brown (cast_op4 u/v 0.92/0.12)?** Run `cast_gate.py hue` on the box over an S13 close frame, with
  `--region iris_l=...` and `--region iris_r=...` boxes from `cam.project` of FACIAL_L/R_Eye (as `mouth` does for
  the lips).
  - Brown reads a* > ~4 and b* > ~8 (hue angle ~45-75 deg).
  - The old 0.08/0.95 light blue/grey reads b* <= 0.
  - The hue gate's L* < 30 cut suits a dark iris. If n comes out ~0, the iris is lighter than L* 30, so it is not dark brown.
  - The likeness itself is the operator's call: cc-64d05f6e reviews on the box.
- **Is the hair straight?** There's no number for it. It needs the operator or cc-64d05f6e to look at a private still.
- **Is the tee-hem patch gone?** Read qa.penetration's magenta still for S15 f1082 on the box (`engine --stills <dir on box>`).
  - Magenta at his waist/hem means the patch is still there: agent-04 slims or lowers the trousers' waistband.
  - Magenta elsewhere is the false-positive pattern.

## Tomorrow, in order (my part, item 15, and the gate)

1. **Hair (c).** It's not the material parameters, the overshirt, the Lumen/scatter cvars, the cards/helmet MIs or coverage (all ruled
   out with numbers; the A/B dirs are in `agent-07-out/hair_ab_f1236*`, `hair_cover`).
   - `cd tools && uv run python ../films/host-studio/reel/hair_teal_ab.py --lights --out <box dir>`: read-only, the lights and
     emissive MIs, greenest first.
   - A/B the top green suspect (off vs on) at `--frame 1236`, then 1300. Score with
     `cast_gate.py hue <stills> --out <dir>`.
   - If no light wins: dump Hair_L_Straight's strand data (the per-strand colour/root UV the groom shader reads) on Linux.
     The strands may carry their own colour that the MI only multiplies.
   - Pass: green_px <= 0.05 in the crown and both ends at f1236 and f1300.
2. **Watch (b).** After dress_her: `seq_dress.py`, then `cast_gate.py engine` must read `b.watch_cm` 3.6 (+-0.5) at
   every frame after a scrub.
   - First dump HerWatch's attach and transform track keys (the report's `watch_actor_rel_was` holds the old offset).
3. **His lips on Host_Op (a), only if the operator picks Host_Op.**
   - Is Host_Op's Face post-process AnimBP the MetaHuman face AnimBP that turns ctrl_expressions_* into joints?
   - Compare FACIAL_C_Jaw travel (level.bone over S13's line windows), Trey vs Host_Op, on the same AS_reel_him_gaze5.
   - If the jaw travels less, it's the rig or the AnimBP, not the curves.
   - Pass: S13 frame lips >= Trey's 2.15 with the same per-frame box (`mouth` then `frames --mouth`).
4. **TRASH_.** No final is signed with TRASH_ in lod0. The order is: dress -> level.save -> level.open -> lod0 -> no TRASH_ -> save.
5. **Cast preview gate** on whichever presenter the operator picks, everything on the box:
   `engine --out` -> `mouth --out mouth.json --shots S13,S16` -> `frames <dir> --engine ... --mouth mouth.json --out ...`.
   - With Host_Op, only numbers come down.
6. **Finals (65 s + 45 s, 1080p, 16:9).**
   - The full 1080p run in a fresh dir at pick C, set shots first. Then QA each presenter shot S13-S18 with the
     same gate on the final frames: lips on S13/S16, hue on S16, the watch/garments from engine.
   - Check S15 f1082-1084 and f1132-1136 for pops (`qa_review.py pops`), and her S16 neckline edge.
   - Then agent-06's `cut.sh final --cuts 65s` and `--cuts 45s`.
   - Host_Op cuts go to `private/` only (KMS). Only Trey/no-face cuts go to `shoot/r3/final/`.

## Tools (on film/host-studio)

- `reel/cast_gate.py`: engine / frames / mouth / hair / hue.
  - hue = Lab on hair-only pixels (L* < 30); green_px = share with a* < -4, gate 0.05.
- `reel/hair_teal_ab.py`: material A/B variants, `--frame`, `--only`, `--lights` (read-only).
- `props/her_outfit_ue/seq_dress.py`: keys HerWatch from dress_her's seat rule (47c8b61b).
