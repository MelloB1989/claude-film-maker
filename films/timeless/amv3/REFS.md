# Timeless v3: reference study

(Sections "Ref b" and "Motion metrics" by agent-06, task v3-refs-b-metrics. "Refs a and c" is written by another agent
on its own branch; the sections here stand on their own.)

Frame numbers are 0-based video frames at 30 fps (`ffmpeg -start_number 0`), the same numbering as the contact sheets in
`refs_v3/<x>/sheets*/`. "px/f" is pixels per frame in 1080-line units (a 4:5 1350x1080 video and a 16:9 1920x1080 video
compare directly). Zoom rates are `d ln(scale)` per frame, written in % (2 %/f = EDIT.md `ds` 0.02). Roll is in deg/f,
+ = the picture turns clockwise.

---

## Ref b: eitaX, Spider-Man 2 "Newest Tank" (`refs_v3/b/N3TshMrwhGk.mp4`)

1920x1080, 30 fps, 1033 frames. The edit runs **0-859** (fade in from black over 4-12); 860-1032 is the channel's logo
outro (a small spinning coin on black), not part of the edit. thin black bars (~20-30 px) top and bottom on
most shots; a thin red glow line under the top bar on some (290-300, 510-560).

**Structure.** 44 transitions in 860 frames (one every 19.5 f; median shot 17 f, 0.57 s). Two halves: 0-440 introduces
the shots and words; **440-859 re-uses most of the same shots and the same 3D word set with new lyrics** (708 = 422
PARKER, 726 = 440 VENOM, 765 = 480, 782 = 497, 795 = 510, 805-836 = 520-551 YEAH, 838-858 = 551-572). Each section lives in
one colour world: warm orange/fire (0-28, 402-420, 687-705), cold teal (29-58, 81-116, 177-235), black-and-red Miles
(236-306, 497-551), cyan lightning (360-401, 645-686), dusty sepia battle (421-479, 705-765).

### How every transition is built (the pattern)
Measured with `motion_metrics` (below) and checked frame by frame on full-res strips. The pattern is so consistent that
it is a recipe:

1. **A never holds.** Even "still" shots drift at 10-25 px/f, mostly a slow push or pull (median |zoom| 2.1 %/f, p75
   3.5 %/f), with a small roll (median 0.12 deg/f, p75 0.3 deg/f) and translation (median 9.5 px/f).
2. **Acceleration into the cut: 3-5 frames, x1.4-1.9 per frame** (median 1.42/f on picture speed; e.g. cut 59:
   7.9, 12.5, 24, 53, 131 px/f on f54-58; cut 29 zoom 4.4, 6.3, 14.7, 31 %/f on f25-28). The ease is exponential, not
   cubic: speed roughly doubles every 1.5 frames in the last 3 frames.
3. **The smear: 1-3 frames of A abstract** (radial zoom blur centred on the subject, streaks reaching the frame corners,
   chromatic split on the streak ends): 28, 58, 79-80, 289, 322-323, 456-459, 549-550. Peak picture speed at the cut
   (median 224 px/f, i.e. the frame content moves ~1/5 of the frame height per frame).
4. **Often a light frame on the cut itself**: a warm or cyan over-exposed blur of the incoming shot's colours (324-326
   pink/white, 360-361 cyan, 402-404 orange, 438 sand-white, 498 pale, 552 white-blue, 626 white) - luma jumps
   from ~70 to 150-250 for 1-3 frames (the luma spikes on the plot). It is the incoming picture blown out, not a flat white
   card. Pure white only on 366 and 626 (lightning hits).
5. **B lands inside its own blur, still moving the same way**, and decelerates over 8-15 frames (x1.17/f median - a long
   exponential tail, much gentler than the acceleration). B's blur is often **lens defocus (bokeh), not motion blur**:
   29-35 (B is pure bokeh discs, focus racks in over ~10 f), 81-90, 290-295, 327-330. A sharp B appears through the defocus
   while the camera is still moving.
6. **Direction is kept**: 22 of the 24 cuts with a measurable zoom keep the *sign* of the zoom rate (push->push 9,
   pull->pull 13). Only 81 and 575 go push->pull; both hide the reversal behind 2-3 frames of radial smear (575 adds a blow-out
   frame) and a dark, defocused B. Roll also keeps its sign through the cut (e.g. 421 / 438 / 705 / 723 land rolling +0.7-1 deg/f).
7. **Hard cuts are on hits only** (7 of 44 have no smear: 265 TOOK slam, 324, 421, 520/525 eye punch-ins, 609, 705, 744),
   and even those cut *between two moving shots at matching speed*.

### Transition list
`smear` = frames with sharpness < 0.5 x the shot's normal around the cut; `peak` = picture speed px/f at the cut;
`acc` = per-frame speed growth over the last 4 frames of A; `dir` = zoom sign A -> B. Read with the sheets.

| cut | what happens (frames) | peak | acc | smear | dir |
|---|---|---|---|---|---|
| 0-12 | fade in from black while the camera pulls back over Venom/Kraven; CHANCE fades in 12-18 | | | | pull |
| 29 | push into Venom's chest (25-28 radial zoom 4->31 %/f, streaks + CA), cut to Kraven's crew **in full bokeh** still pushing in (+17 %/f -> 1 %/f by 46), focus racks in 29-42 | 174 | 1.59 | 12 | push->push |
| 59 | pull-out of Kraven (54-58: the picture shrinks into a dark centre with radial streaks), Peter lands blurred, zoomed in, pulling out + rolling -1.2 deg/f, NEED already in place | 352 | 1.79 | 5 | pull->pull |
| 81 | push into Peter (78-80 zoom blur, NEED smears), B (Venom's tendrils, teal) arrives defocused and pulls out | 147 | 1.91 | 14 | push->pull |
| 117-153 | push into darkness (115-117), 118-128 near-black corridor, a long dolly toward a lit doorway (128-148) with the night city inside it; the doorway grows until **the city shot inside it becomes the frame** (148-152, frame-in-frame push), the city lands in bokeh (152-156) and racks into focus (158-162) | 174 | 2.13 | 14 | push |
| 177 | the lyric WE'RE GOING TO HEAL flies past the camera (164-176), pull to Kraven's close-up | 187 | 1.3 | 13 | pull->pull |
| 236 | zoom-out through dark (232-235), Miles extreme close-up arrives soft red, pulling out | 207 | 1.46 | 16 | pull->pull |
| 265 | (not a cut) TOOK slams in behind Miles on the beat, slight camera shake | 29 | | 0 | |
| 290 | radial zoom into TOOK/Miles (288-289, one fully abstract frame), Miles in his room arrives dark and defocused, pulling out, rim light | 224 | 1.71 | 5 | pull->pull |
| 307 | whip/zoom into blue-red blur (306-308) to BATTLE (FORCED in the second half) | 298 | 1.42 | 3 | push |
| 324 | BATTLE -> zoom-in with strong RGB split (322-323), **3 frames of warm overexposed abstract** (324-326), Venom/Kraven cell arrives defocused (327-330) | 249 | 1.47 | 0* | |
| 341-345 | whip with a red/white streak to MILES (346-358) | 282 | 1.06 | 3 | |
| 360-401 | lightning: cyan blown-out frames 360-361, 366 full white, ULTIMATE 3D letters wrapped in lightning, whip blur 384-387 (vertical streaks), Electro in lightning 388-400 | 253 | 1.76 | 1-11 | |
| 402 | orange blow-out 402-405 (fire), Venom in flames | 188 | 1.76 | 2 | pull->pull |
| 421 | warm blur (420), PARKER shot (hard cut on the hit), camera pulling + rolling +1 deg/f | 357 | 1.47 | 0 | pull->pull |
| 438 | Peter's swing whips across the lens (432-437, a subject wipe), 438 white-sand blur, Venom/Peter fight | 287 | 1.14 | 17 | push->push |
| 456-459 | VENOM letters + subject blur into a red radial swirl (subject-motion wipe), Miles swinging | | | | |
| 480 | push into fire/tendrils, sand-gold blur, symbiote shot | 385 | 1.97 | 9 | pull->pull |
| 497 | 496-499 pale blow-out, Tobey-suit close-up | 285 | 1.87 | 4 | |
| 510-527 | Miles' mask: eyes light up (510-519); 520 hard punch-in (x1.4) on the beat; 521 roll + push into the left lens, **the next shot (Miles swinging) is already visible as the lens reflection** (521-524); 522-526 push through the lens with radial blur and a warm burst (525-526); B emerges 527-529 still pushing and rolling (the lens portal) | 219-255 | ~1 | 0-1 | push->push |
| 551 | YEAH (540-548) pulls away (549-550 red swirl), 552 white-blue blow-out, rubble battle with WE 3D letters | 362 | 1.61 | 6 | pull->pull |
| 575 | radial zoom on WE/rubble (571-573), 574 white-blue blow-out of A, B (Miles in his room, = 290) lands dark, defocused and pulling out, focus racks in 576-581: the reversal is hidden by the blow-out + the dark defocused B | 248 | 1.93 | 3 | push->pull |
| 592 | blue/red blur 592-594, FORCED letters slam with Miles | 222 | 1.4 | 6 | |
| 609 | FORCED zooms past (606-608), radial red/blue streak into a pink blow-out 610-612, Venom/Kraven cell | 247 | 1.51 | 0 | |
| 626 | 626 full white flash (the drop), 628 red blur, YEAH 2 | 263 | 1.06 | 2 | |
| 645-686 | lightning section 2 (= 360-401) with HE GOT A... words | | | | |
| 687-859 | second pass of 402-572 with new words (HE GOT A HOPE...); 836 white-blue blow-out; 859 into the outro | | | | |

`*` 324's B frames 324-326 are blown-out, so the sharpness test reads them as "bright", not smeared.

### Holds and drift (between transitions)
- Picture speed in holds: median 22.6 px/f, p10 5.4 px/f; **1.2 % of hold frames are below 4 px/f** (v2: 44.6 %).
- Zoom: median |rate| 2.1 %/f (p25 0.85, p75 3.5). Roll: median 0.12 deg/f. Translation: median 9.5 px/f.
- Shape: after each landing the speed decays exponentially (x1.17/f) for 10-15 frames, flattens at 5-15 px/f for a few
  frames, then accelerates (x1.4/f) into the next cut. On the speed plot it is a **sawtooth** with peaks at every cut and
  floors that never touch zero (`refs_metrics/b/plot.png`). v2 is a **square wave**: flat 3-4 px/f plateaus, a jump to 100+ for the
  transition, a drop straight back (`refs_metrics/v2/plot.png`).

### Blur, aberration, light
- Motion blur on A: radial (zoom) blur centred on the subject's face/chest, streaks reaching the corners, 2-3 frames
  (27-28, 57-58, 79-80, 288-289, 322-323). Directional blur only on whips (306-308 diagonal, 384-387 vertical).
- **Chromatic aberration** sits on the smear frames only: visible red/cyan split of the streaks towards the frame edges (322-323,
  456-459, 522-526); none on holds.
- **B lands in defocus** (bokeh discs, focus racking in 6-12 f) rather than in motion blur on many cuts (seen on 29,
  81, 290, 327-330). That is why the measured "frames to re-sharpen" is 5 (median) and up to 13.
- Light: blow-outs of B's own colours on the cut frame (see pattern 4), bloom on every highlight (fire, eyes, lightning),
  white flashes only twice (366, 626). Lightning (360-401, 645-686) is bright cyan bolts with heavy glow over a darkened,
  desaturated teal plate, plus a 2-frame full-frame flash when a bolt hits.

### 3D text in b
Every lyric hook is a **huge extruded 3D word** filling 60-90 % of the frame width, condensed bold with a slight italic,
deep extrusion (about 8-12 % of the letter height), bevelled front edge catching a white highlight, the face in the shot's
key colour (orange-gold CHANCE/NEED, red TOOK/BATTLE/FORCED/VENOM/YEAH/PARKER, teal BEGINS/HUNT, white-blue
ULTIMATE/WE). Small 2D lyric lines ride with it (wide-tracked white caps, e.g. "I GOT A SECOND" on a dark band, "BUT I",
"YOU WITH", "FROM ME").
- **Placement**: in perspective, inside the shot. Behind the subject almost always (NEED: Peter in front of N-E-E-D;
  TOOK: Miles' head covers the middle O's; VENOM, PARKER, YEAH, FORCED behind the characters), on the ground plane or
  a wall plane matching the shot's vanishing point (PARKER 422-430 standing on the street, VENOM 448-456 rising along the
  building wall, YEAH 540-548 on the brick wall).
- **Entrances**: (a) fade/rack in from defocus while the camera drifts (CHANCE 12-18, BEGINS 204-224 - letters appear
  one by one, blurred, sharpen); (b) letters **slam in one per beat** (TOOK 266 T, 268-276 O-O, 278 K; FORCED 596-604)
  with a 1-2 frame motion-blurred approach from depth; (c) **rise / swing in** from below the frame in perspective
  (VENOM 448-454, PARKER 422-428).
- **While it sits**: a **white light sweep** crosses the letters (one letter at a time turns white-hot then cools: CHANCE
  E at 20-22, TOOK T at 272-276, NEED D at 66-78), the camera keeps drifting so the word's perspective changes, the
  extrusion sides catch the shot's light (warm rim from fire, cyan from lightning).
- **Exits**: the word belongs to the plate, so it leaves *with the camera*: it smears in the radial blur of the next
  zoom-through (CHANCE 26-28, NEED 79-80, TOOK 288-289, YEAH 549-550, VENOM 456-459 twisting into a red swirl), or the
  camera flies through it (WE'RE GOING TO HEAL 164-176 rushes past the lens; HE GOT 840-846 letters stream past). No
  word ever fades out on a static frame.
- Timing: a word is on screen 16-28 frames (CHANCE 12-28, NEED 60-80, TOOK 266-289, YEAH 540-550, FORCED 596-608).

### What to take for v3 (b's lessons)
1. Holds are slow pushes/pulls, |ds| 0.01-0.035 per frame, never below ~5 px/f picture speed.
2. Accelerate into the cut over the last 3-5 frames at x1.4-1.9 per frame (expo-in); peak ~200 px/f.
3. 1-3 frames of radial smear + CA on A; then B **keeps the same zoom sign** and decelerates at ~x1.2/f over 10-15 f.
4. Put the blow-out *of B's own colours* on the cut frame instead of a white flash; B may land in defocus that racks in.
5. 3D words behind the subject, in the shot's perspective, slammed or risen in, swept by a white highlight, and they
   leave with the camera move (smeared or flown through), never faded.

---

## Motion metrics: refs vs v2 (the v3 targets)

### The tool
`tools/filmtools/amv3/motion_metrics.py`:

    cd tools && python -m filmtools.amv3.motion_metrics VIDEO_OR_FRAME_DIR --out DIR [--name X] [--start F --end F]
    python -m filmtools.amv3.motion_metrics --reuse --out DIR --end F        # re-derive stats for a frame range
    python -m filmtools.amv3.motion_metrics --compare DIR1 DIR2 ... --out table.md

Needs `opencv-python-headless numpy matplotlib` and an ffmpeg with dav1d for AV1 (the refs are AV1; `imageio-ffmpeg`'s
static binary works and is used when no `ffmpeg` is on PATH). A video of 900 frames takes ~4 min on one core.

Per frame (`metrics.csv`): `gspeed zoom rot tx ty inl` (similarity transform fitted with RANSAC to DIS optical flow on a
480-wide grid: camera speed as the RMS displacement of the fitted model, px/f), `flow_med flow_mean` (picture speed incl.
subject motion), `sharp` (Laplacian variance at 960 wide), `sharp_rel` (vs the shot's 75th percentile), `luma`, `resid`
(error after warping by the flow: high = new picture), `hist_d`, `cut` (hard cut), `event` (1 hard cut, 2 smear-through:
a fast + smeared run with the cut hidden inside the blur), `dup` (a repeated frame), `gfail`. `summary.json` holds the
stats below and a `per_cut` list (speed curves into and out of every transition, sharpness curve, zoom/roll before and
after). `plot.png`: picture/camera speed (log), zoom, roll, sharpness, luma, transitions in red.

**Checked by hand** (full-res strips): ref b cuts 29, 59, 81, 290, 324, 366; c 396-411; a 740-790; v2 plot vs its EDL.
- Cut detection: every hard cut I checked is found on the right frame. Smear-throughs where the cut is hidden inside 5+
  frames of blur are found as `event 2` (c 213-222 -> 222). Lightning and blow-out frames can add a cut on a flash frame
  (b 360/366/372); a 3D word slamming in can register as a hard cut (b 265 TOOK). Expect +-10 % on the count.
- Speeds agree with what you see: b 54-58 (Kraven pull-out) 7.9 -> 131 px/f, zoom -0.9 -> -25 %/f; b 30-46 B's push
  decaying 17 -> 1 %/f; v2 12-46 measured 3-4 px/f (it is visibly near-static).
- **Ref a has a duplicated frame every 30 frames** (30, 60, 90 ... a frame-rate conversion in its upload); the tool flags
  these (`dup`) and skips them, otherwise they fake x30 speed jumps.
- Limits: flow under-reads speed on fully smeared frames (motion is inside the blur) and is noise on near-black frames
  (b 118-145, luma < 15). The similarity fit fails (`gfail`) on 15-25 % of the refs' frames (smear, flashes, lightning);
  stats skip those. `sharp_rel` is conservative: on c 400 the tool says legible at +6 / sharp at +9 frames, by eye B is
  legible at +2 and nearly sharp at +5 (bloom and the shot's own softness lower the Laplacian). Compare v3 to the refs
  **with the tool**, not to by-eye numbers.

### Results (edit ranges only: a 0-800, b 0-859, c 0-636, v2 0-819; outros excluded)
Committed: `films/timeless/amv3/refs_metrics/{a,b,c,v2}/summary.json` + `plot.png`, table `refs_metrics/compare.md`.
Per-frame CSVs (not committed): `/home/nikhil/code/.worktrees/agent-06/mm/{a,b,c,v2}/metrics_0_<end>.csv`.

| metric | ref a | ref b | ref c | **v2** |
|---|---|---|---|---|
| transitions (hard + smear-through) | 34 | 44 | 19 | 44 |
| median shot length (f) | 17 | 17 | 20 | 16 |
| **hold picture speed, median mean flow (px/f)** | 20.5 | 22.6 | 15.0 | **4.5** |
| hold camera speed median / p10 (px/f) | 16.9 / 4.9 | 19.6 / 5.4 | 10.6 / 3.9 | **3.4 / 1.6** |
| hold zoom rate median / p75 (%/f) | 2.5 / 4.4 | 2.1 / 3.5 | 2.1 / 4.0 | **0.39 / 0.93** |
| hold roll median / p75 (deg/f) | 0.09 / 0.21 | 0.12 / 0.29 | 0.05 / 0.12 | **0.02 / 0.06** |
| **% near-static hold frames (< 4 px/f)** | 2.5 | 1.2 | 2.0 | **44.6** |
| still frames (< 0.5 px/f median flow), longest run | 0 %, 0 | 0.4 %, 3 | 0 %, 0 | 0.9 %, 3 |
| picture-speed jump ratio frame to frame, p95 / max (outside +-6 f of cuts) | 2.0 / 7.1 | 1.8 / 5.0 | 1.9 / 4.1 | 2.3 / **13.4** |
| % hold frames with a jump > x1.35 | 21.5 | 25.1 | 19.4 | 15.9 |
| cut peak picture speed, median (px/f) | 190 | 224 | 154 | 151 |
| acceleration into the cut (x per frame, last 4 f) | 1.62 | 1.42 | 1.36 | 1.62 |
| deceleration after the cut (x per frame, 8 f) | 1.24 | 1.17 | 1.25 | 1.31 |
| worst 1-frame speed step into a cut, median | 2.5 | 2.3 | 2.3 | **3.3** |
| **worst 1-frame speed drop out of a cut, median / p90** | 2.2 / 3.8 | 1.8 / 3.0 | 2.0 / 3.1 | **3.3 / 10.1** |
| **zoom sign kept across the cut** (push->push + pull->pull) / reversed | 23 / 2 | 22 / 2 | 9 / 2 | **10 / 12** |
| smear frames per cut, median | 9 | 3 | 10 | 4 |
| % cuts with >= 2 smear frames | 88 | 73 | 95 | 68 |
| **% hard cuts (0 smear frames)** | 12 | 18 | 0 | **32** |
| frames until B is legible / sharp (tool), median | 7.5 / 8 | 0 / 5 | 8 / 11 | 3 / 4 |
| duplicated frames | 3.2 % | 0 | 0 | 0 |

### Where v2 is rough (frames, from `refs_metrics/v2/summary.json`)
1. **Dead holds** (picture speed < 4 px/f for 6+ frames): **12-46, 122-146, 180-186, 192-198, 290-296, 322-329,
   346-360, 377-391, 493-507, 634-652, 693-699, 811-818**. 44.6 % of all hold frames. The refs: 1-2.5 %.
2. **Square-wave transitions**: speed drops by x8-16 in one frame after the cut at **50 (x8.7), 118 (x9.0), 175 (x10.3),
   336 (x8.5), 369 (x9.1), 416 (x11.3), 536 (x14.2), 604 (x15.6), 744 (x16.1)** - the move stops instead of decaying.
   Into the cut: steps of x10-76 in one frame at **9, 50, 83, 201, 336, 436 (x28), 672, 744** (the whip starts from
   rest). The refs' worst single-frame steps are x2-3.
3. **Zoom sign reversed at the cut** (A pushes in, B pulls out from zoomed-in): **83, 201, 300, 369, 400, 554, 587, 620,
   672, 686, 726** (11 of 22 zoom cuts) and pull->push at 771. The zoom rate flips from about +26 %/f to -31 %/f across
   one frame (e.g. 400: +25.4 -> -31.6; 620: +26.2 -> -29.6). The refs do this on 2 of ~24 cuts.
4. **Hard cuts with no smear**: **9, 118, 251, 436, 474, 484, 700, 708, 760, 777, 785, 794, 802** (32 %).
5. Speed into the cut from near zero (`across` x6-80: 118, 519, 570, 656, 686, 700, 785, 794): B starts fast while A
   was nearly still, or the other way round.

### Targets for v3 (the gate)
Run the tool on the v3 render (or straight on the stage's `plate/` PNG folder: the frame number is read from
`f_NNNNN.png`) with `--gate`; it writes `gate.txt` and exits 1 on any FAIL:

    cd tools && python -m filmtools.amv3.motion_metrics ../out/timeless/amv3/Timeless_v3.mp4 --end 820 --out ../out/mm/v3 --gate
    python -m filmtools.amv3.motion_metrics --compare <mm>/a <mm>/b <mm>/c <mm>/v2 ../out/mm/v3 --out ../out/mm/compare.md

Each target sits inside the refs' range (refs b and c pass all 16, ref a fails only on its upload's duplicated frames)
and v2 fails 12 of 16. The targets live in `GATES` in the tool.

| gate | target | refs a / b / c | v2 |
|---|---|---|---|
| near-static hold frames (< 4 px/f) | **<= 5 %** | 2.5 / 1.2 / 2.0 % | 44.6 % FAIL |
| longest near-static run | **<= 4 f** | 2 / 4 / 2 | 28 FAIL |
| hold picture speed, median | **>= 12 px/f** | 20.5 / 22.6 / 15.0 | 4.5 FAIL |
| hold zoom rate, median | **>= 1.5 %/f** (`abs(ds)` >= 0.015) | 2.5 / 2.1 / 2.1 | 0.39 FAIL |
| picture-speed jump outside cuts, max | **<= 7.5** | 7.1 / 5.0 / 4.1 | 13.4 FAIL |
| picture-speed jump outside cuts, p95 | **<= 2.1** | 2.0 / 1.8 / 1.9 | 2.3 FAIL |
| worst 1-frame drop out of a cut, median | **<= 2.3** | 2.2 / 1.8 / 2.0 | 3.3 FAIL |
| worst 1-frame drop out of a cut, p90 | **<= 4.0** | 3.8 / 3.0 / 3.1 | 10.1 FAIL |
| worst 1-frame step into a cut, median | **<= 2.6** | 2.5 / 2.3 / 2.3 | 3.3 FAIL |
| acceleration into the cut (last 4 f) | **x1.35-1.7 per frame** | 1.62 / 1.42 / 1.36 | 1.62 |
| deceleration out of the cut (8 f) | **x1.15-1.27 per frame** | 1.24 / 1.17 / 1.25 | 1.31 FAIL |
| cut peak picture speed, median | **>= 150 px/f** | 190 / 224 / 154 | 151 |
| zoom cuts reversing the zoom sign | **<= 20 %** | 8 / 8 / 18 % | 55 % FAIL |
| hard cuts (0 smear frames) | **<= 20 %**, only on hits | 12 / 18 / 0 % | 32 % FAIL |
| smear frames per cut, median | **>= 3** | 9 / 3 / 10 | 4 |
| duplicated frames | **0** | 3.2 / 0 / 0 % | 0 |

Note the 4 v2 "passes": v2's transitions themselves are fast and smeared enough; what fails is everything around them
(dead holds, square-wave exits, reversed zooms, hard cuts).

### What this says about EDIT.md (please read)
1. **The zoom-through default contradicts the refs.** EDIT.md (`zt`) and all 13 `zt` cuts in edl.json (no `mode`) do
   "A accelerates in to `peak` -> B starts at `land` x zoomed and pulls out": a zoom-sign reversal - exactly v2's rough
   cuts 83/400/587/620/726. The refs keep the sign: **push into A -> B keeps pushing in and decelerates** (b 29, 438, 520,
   723, 805), or **pull out of A -> B is zoomed in and keeps pulling out** (b 59, 177, 236, 290, 402, 421, 551, 687).
   Proposal: make `mode: push` the default for `zt` (B starts at ~1.0-1.3x with a decaying push, ds from ~+0.15/f to
   +0.01/f over 12 f), and add `mode: pull` = A pulls out (ds negative, accelerating) -> B lands at `land` x and keeps
   pulling out. Use the reversal (current behaviour) on at most 1-2 cuts, and only with >= 3 smear frames + a blow-out
   frame to hide it (b 81, 575).
2. **"Landing sharp within 3-4 frames" is stricter than the refs.** By eye the refs' B is legible at +2 and sharp at
   +5-8; by the tool 5-11 frames. v2 already landed sharp in 3-4 and still read as rough. Keep "legible by +3", allow
   "fully sharp by +8", and let B arrive in defocus that racks in (cheap in Blender: animate the camera's DoF f-stop /
   focus distance over the first 6-10 frames of B) - it is half of b's landings.
3. **x1.35 per frame is too tight for the acceleration into a cut** (refs accelerate at x1.4-1.9/f in the last 3 frames;
   single frames step x2-2.5) and about right for the deceleration (x1.17-1.25/f). Suggest: inside windows, allow up to
   x2.5 per frame on the way in and x2.3 on the way out; in holds, keep x1.35.
4. **Holds must move 4-5x faster than v2.** Median drift ~2 %/f zoom (v2 0.4 %/f), i.e. in a 20-frame hold the picture
   scales by ~1.5x, plus 0.1-0.3 deg/f roll. The camera "never stops" rule is right; the magnitude is what v2 lacked.
5. **Flashes**: blow out B's own colours for 1-3 frames on the cut (luma to 150-250) instead of flat white; white only
   on the 1-2 biggest hits.
