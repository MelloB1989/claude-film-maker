# QA handoff (agent-09): ROUND 4 (06 Nov), the gate on cast_op5 and the finals' QA

Numbers only. No Host_Op frame, crop or still leaves the box (face rule); the orchestrator looks at Host_Op by eye from
private/. Both this gate and that review must pass before the presenter finals.

## The gate: `cast_gate.py sign` (exit 0 = SIGN, 1 = REFUSE, each failing item with its frames)

On the box, from `tools/` in the box tree, `G=/srv/ue/reel/r4/gate`, `R=../films/host-studio/reel`:

    uv run python $R/cast_gate.py engine --out $G/engine.json            # jaw curves, alive, qa.penetration, watch (scrubs)
    uv run python $R/cast_gate.py mouth  --out $G/mouth.json             # a box per speaker per shot from the lip bones
    uv run python $R/cast_gate.py lod0   --out $G/lod0.json              # read-only
    uv run python $R/r3/probe_cam.py V01,V02,V03,V04,V05,S11,S12,N01,S13,S15,S16,S17,S18 --check > $G/cams.txt
    python3 $R/framing.py > $G/framing.txt
    uv run --with pillow --with numpy python $R/cast_gate.py frames <cast_op5 dir> --engine $G/engine.json \
        --mouth $G/mouth.json --out $G/frames
    uv run --with pillow --with numpy python $R/cast_gate.py hue <cast_op5 dir> --frames 1236,1300 --out $G/hue
    uv run --with pillow --with numpy python $R/cast_gate.py sign --name cast_op5 --engine $G/engine.json \
        --frames $G/frames/cast_gate_frames.json --hue $G/hue/hue.json --turns <tree>/out/host-studio/reel/perf/looks_measured.json \
        --clip <host clip.json> --clip <presenter clip.json> --clip-before /srv/ue/reel/r4/clip/Presenter_before/clip.json --cams $G/cams.txt --framing $G/framing.txt --lod0 $G/lod0.json --out $G/gate.json

| item | measure | pass | why this line |
|---|---|---|---|
| a. lips | every spoken line (L1 S13 him; L2 S15 him; L3a S15 her; L3b S16 her; L4a S17 him; L4b S17 her): mean abs luma change inside the speaker's projected mouth box (per frame, from FACIAL_* lip bones via cam.project) on the line, over the same in the speaker's own silence in that shot (3 frames clear of any line) | ratio >= 2.0 per line; and the engine's jaw on/off >= 3 per person, no silent line | 2.0: preview 1 with no lip sync read 1.55, round 1's good sync 2.37, cast3 S13 2.13. Boxes under 8 px tall (S17's 28 mm two-shot at 960x540: ~5 px) cannot separate a mouth from a pixel of head motion, so those lines are judged on the engine's jaw for that line (jaw_max >= 0.08 and moving), and re-read on the 1080p finals |
| b. watch | HerWatch to hand_l, cm, after seq.scrub, at start+2 / mid / end-3 of S15-S18 | every sample 3.6 +- 0.5 | dress_her's seat is 3.6; cast_op2-4 rendered a stale 8.2, which the old <= 8.0 cap would pass at 7.9 |
| c. hair hue | Lab on the hair's dark pixels (L* < 30) in the crown and both ends regions, f1236 and f1300 | green_px <= 0.05 in every region, ends a* >= -2 | 0.05: the right ends and the clean frames read 0.02-0.03; the defect reads 0.21-0.24 |
| d. head turns | agent-01's `perf.py looks --seq /Game/Reel/SEQ_Reel --measured` (fleet/agent-01/r4-look) -> out/host-studio/reel/perf/looks_measured.json: every look beat x every camera that sees it, at its hold frame | re-applied here, not trusted from `ok`: screen_dir == partner_dir, and gaze err <= 15 deg, or (partner beyond reach, \|true_yaw\| > 100) the head turned their way >= 32.5 deg; AND the head within 15 deg of its planned yaw (head_vs_plan_deg, agent-01 64161ac8); rows from the plan (stage shots.py) or without head_vs_plan_deg refuse | preview2 passed on turn size alone with every turn the wrong way (him S15 -64.6 deg LEFT, err 144); the sign is what failed, so the sign is checked |
| e. clipping | agent-02's `r4/clip_pass.py` clip.json per presenter (`--clip` twice, `--clip-before` her cast_op4 pass): per shot, 6 frames, per under>over pair, `fraction` = px where the under layer pokes 0.3-3 cm through at an intersection edge / the garment's px; him also `neck` (3D: face verts > 0.1 cm outside the tee near the collar) | him: Body>tee, Body>Trousers, Trousers>tee <= 0.001 every frame, and `neck_px` (Face>tee pixels under the collar band) == 0 every frame, missing refuses (the orchestrator, 06 Nov: the after renders still showed the patch while the 3D count read clean, so the 3D `neck` is information only; the band: per column the tee's front-surface top edge, 1.0 cm under it at the rim's depth, nearest rim within 24 px); Face>tee as a whole information only; her: each (shot, pair) worst within +0.01 of before; a missing or errored shot refuses | cast_op4: his clean pairs 0.0000 everywhere, the smallest real clip (S18 hem, 21 px of 4400) 0.0047, so 0.001 (~4 px) sits between; Face>tee cannot tell the collar's clean neck band from a patch in depth (agent-02 tried two rules), so the 3D neck test gates it (before: 227 verts, 2.46 cm); her pairs read 0.03-0.19 on clean frames (scoop neck, open overshirt), so only a change counts |
| f. cameras + framing | probe_cam --check on all 13 Reel_ cameras; framing.py's PROBLEM lines | 13/13 OK, no PROBLEM | the plan's own tolerances (1 cm, 0.1 deg, 0.05 mm) |
| g. lod0 live | the presenters' components (read-only) | no TRASH_ component on Host or Presenter at all; every live LODSync forced_lod 0; every skeletal mesh forced_lod_model 1 | a pin, drive_faces or a dressing on a TRASH_ component does nothing to what renders |

`--waive item=reason` marks a failing item WAIVED (listed, not blocking): only on the orchestrator's word (e.g. the hair
if its time-box ends unfixed).

## Her hair's teal ends (time-boxed, 60 min of box time)

What the numbers say so far: only the screen-LEFT ends are green (f1236: a* 0.0, green_px 0.22) while the screen-right
ends and the crown read a* ~+2. Hiding the overshirt, the two Lumen/scatter cvars, the cards/helmet MIs and coverage
each moved it by < 0.01. One-sided green is directional. The A/B (`hair_teal_ab.py`, R4 variants):
`hair_hidden` (a mask: `cast_gate.py hue --mask hair_hidden.png` measures only the pixels the hair changes, so a dark
green background between thin tips stops counting as green hair), `plants_hidden`, `trt_sat_1` / `trt_off` (the TRT
lobe, the light carried through the strand; its saturation is 1.2), `tips_ombre_root`, `redness_0.15`,
`pp_shadow_desat` (a grade, last resort), and `--lights-ab 8` (each of the 8 lights with the most pull at her head off on
its own). Results below when run.

## The finals' QA: `r3/final_qa.py` (read-only, numbers only)

    uv run --with pillow --with numpy python $R/r3/final_qa.py --final /srv/ue/reel/r3/final_d \
        --cut /srv/ue/reel/r3/cut/final --out /srv/ue/reel/r4/qa/final_qa.json

Plus agent-05's `r3/final_check.py` (FINAL=final_d) and `r3/camcheck.py`. Pass: every shot's frames on disk, 1920x1080,
none black (< 0.01) or white (> 0.97); each cut deliverable 1560 / 1080 frames, audio = picture, -14 +- 1 LUFS, true
peak <= -1 dBTP; every caption line within 2 frames of its first VO word (cues.json through the cut's EDL).

## Round 4 log

- 05:05 hair A/B #1 (base / hair-hidden mask / TerminalGlow off, f1236+f1300): TerminalGlow (green rect, bottom shelf,
  attenuation 2000 cm) is the teal: off -> green_px 0.000 everywhere (ends-L 0.212/0.218, crown 0.114/0.060). The mask
  gives the same numbers: light on the strands, not background. Fix: attenuation 120 cm (studio.py 3b89bbad), applied
  live + saved 05:20:18 (agent-06); verified 05:20:45: green_px 0.000 in all three regions at both frames.
- 05:21 glow_dE (set shots, old vs new radius): mean dE 0.06-0.91, worst block 0.67-4.97; four shots' worst blocks sit at
  the frame's top edge, away from the shelf: a noise-floor A/A (--tags new_a,new_b) decides before any re-render.
- 05:58 cast_op5 PRE-CHECK: REFUSE. Pass b (watch), c (hair), f (13/13 + framing), g (lod0). Fail d: her S15 f1110 head
  -94.6 (err 87.5) and S17 f1392 -120.4 (err 118.9), right way but over-turned (agent-01). Fail e: neck_px S13 81-172,
  S15 609-649 / ~226, S17/S18 smaller. Fail a (frames, aligned): S13 him L1 1.02 (Host_Op's small mouth travel; engine
  jaw 3.8 passes), S16 her L3b 1.99, S15 her L3a 0.80 and S17 him L4a 0.85 (her over-turns in their silences), S15 L2
  and S17 L4b pass. Gate fixes in the run: clip keys Reel_*; the lips box interpolated and each frame pair lined up
  (+-3 px) before differencing, so the head's own move in silence is not read as speech.
- 08:0x (after the box was re-provisioned) final_d set shots, rendered 02:59-04:54 UTC (before the glow fix): frames QA
  PASS (final_check: 3 reports ok; final_qa: all frames present, 1920x1080, no black/white/jump). Glow continuity, worst
  32 px block dE old->new vs the A/A noise floor: V05 4.97/0.32, V04 3.54/0.20, S12 2.50/0.35, V02 2.25/0.38 ->
  RE-RENDER those four; V01 0.71/1.74, V03 0.75/0.94, N01 1.38/0.74, S11 0.67/0.03 stay. Mean dE < 1 everywhere (local,
  upper frame). camcheck on the noise-floor stills: all 8 framing_match (scale 1.000, shift <= 1 px at 480).
- 08:4x lip stills (after agent-01's speech gain, viewport, 24 on / 24 silence per line), frames ratio: S15 L2 6.54,
  S15 L3a 8.01 PASS; S13 L1 1.03, S16 L3b 1.18, S17 L4a 1.16, S17 L4b 1.52. On-line change is alike everywhere (5.9-7.5);
  the failing lines' SILENCES read 4-6 (S15's ~1): S13's head lift, S17's glance, the move after S16's line. A rotating
  head cannot be lined up by a shift, so the frames cannot certify those lines. Added `cast_gate.py lipgap` (engine,
  read-only): the upper-to-lower lip bone gap in cm on the evaluated face, on vs the same silence; `sign --lipgap`
  decides the lines the frames fail (ratio >= 2.0 and opens >= 0.3 cm), and says so per line.
- 08:47 lipgap (engine, lip bone gap; line motion / silence motion, opens on the line): S15 L2 31.4x 2.02 cm, S15 L3a
  40.6x 0.98, S16 L3b 23.3x 1.11, S17 L4a 66.3x 2.98, S17 L4b 28.6x 1.57; S13 L1 opens 3.22 cm but its silence f977-1001
  moves 0.33 cm/frame (others 0.003-0.009): real lip motion before the line, flagged for the orchestrator's eye. Item a
  SIGNED on the orchestrator's rule: S13 L1, S15 L2, S16 L3b by eye; L3a/L4a/L4b on lipgap (S17 also by eye on the
  final re-render). Tee silhouette (orchestrator): Host_fix vs Host_after +6..+15% -> gate e now checks +-2% (S15/S17/S18).
- orchestrator by eye: S13 f977-1017 is the planned smirk/grin (lips part, teeth in a smile), not mouthing; a.lips is
  WAIVED for S13 L1 only (`--waive a.lips=...`), checked on each run that S13 L1 is the item's only failure.
- 09:1x GATE SIGNED on cast_op5 = patch3 (gate_signed.json on the box): b c d f g PASS; a WAIVED (S13 L1, by eye); e
  WAIVED on the orchestrator's eye (no balloon, no hole): residue neck_px 1-3 single px S15 f1082-1128, tee silhouette
  +2.1..+2.2% S15 f1150-1198 (agent-02's tee_silhouette.py agrees, worst +2.23%). Presenter finals released.
- 09:3x FINALS QA final_d (patch3): PASS. 1584 frames, 13 shots complete, 9 render reports ok, 1920x1080, no black/
  white/unreadable, no luma jump (S15's old pops gone); hair at 1080p green_px 0.000 (f1236/f1300).
- 09:4x CUTS QA /srv/ue/reel/r4/final: PASS. 65 s: h264, clean h264, ProRes 4444, 1560 fr, 65.0 s, -14.0 LUFS / -1.7
  dBTP; 45 s: 1080 fr, 45.0 s, -14.1 LUFS / -1.7 dBTP; captions 6/6 lines 0 frames off in both, no filled frames.
  Caveat: cues.json is round 3's known-good copy with ESTIMATED word times (vo.py cues), so the sync check proves the
  captions follow the cues through the EDLs, not that they meet the spoken words to the frame: an ear check remains.
- neck patch (agent-02 neck_px, before4 -> after, worst px per shot): S13 169 -> 172, S15 709 -> 649, S17 91 -> 93,
  S18 39 -> 34: NOT fixed; the gate refuses e until 0.

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
