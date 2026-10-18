# REFS: measured study of the v3 reference edits

## Refs a and c (eitaX "We ready?" and sanchezae "We Ready?") — agent-03, task v3-refs-ac

**Status: v1 (ref c measured in full, ref a from the sheets; ref a numbers are being added).**

### How the numbers were made (reproducible)
- Frames: `ffmpeg -i <ref>.mp4 -start_number 0 -q:v 2 f_%04d.jpg` (frame 0 = first frame; same numbering as the
  `sheets/` contact sheets).
- `tools/filmtools/amv3/analysis/ref_metrics.py <frames> <out.csv>`: per frame f, the global similarity transform
  f-1 -> f (ORB + RANSAC on 1/4-res frames, refined by ECC affine; reported about the frame centre), Laplacian
  sharpness, radial/tangential gradient share, structure-tensor anisotropy, R-vs-B misregistration (chromatic split at
  the frame edge, full-res px), luma and clipped-white fraction.
- `tools/filmtools/amv3/analysis/transitions.py <csv> cuts/c.json --holds`: per-window traces, attack/settle, hold drift.
- `tools/filmtools/amv3/analysis/strip.py <frames> f0 f1 out.jpg`: the strips below (`films/timeless/amv3/refs_strips/`).
- Units: **z = 100 * ln(scale ratio) per frame** ("% zoom per frame", + = the picture grows = camera pushes in).
  Pan in px/frame of the 1350x1080 frame (multiply by 1.42 for our 1920 width). Roll in deg/frame, + = clockwise.
  Frames marked SMEAR are frames where tracking fails (inlier ratio < 0.15); their motion numbers are not measurements,
  the speed there is bracketed by the frames around them.
- Both refs are 1350x1080 4:5 with the 16:9 footage on a moving card (black bands top/bottom that tilt and shift with the
  camera: the picture is a card moved in 2D, exactly our "card space").

### Ref c (sanchezae, 680 f, 640 f of picture): every transition

| # | frames: last clean A / first smear / cut / last smear / first clean B | type | what moves (measured) | ease | blur | CA | light | extras | strip |
|---|---|---|---|---|---|---|---|---|---|
| c01 | -/0/0/2/4 | open: soft oval iris from black + push | z +21.8, +13.8, +9.1, +6.5, +4.9, +3.8, +2.8, +1.8, +0.9 (f1-9); pan -15 -> -5 px/f | expo-out, k = 0.67/f, 10 % in 7 f | defocus + vignette, sharp by f7 | 0 | luma 26 -> 68 over 7 f | - | `c_0-8_open.jpg` |
| c03 | 58/59/59/60/61 | suit swap in-shot (Tom shirt -> suit) | camera keeps drifting z -1 | - | 2 f soft | 1 px | blue-white electric flash, luma 87 -> 117 for 2 f | lightning arcs on the subject | `c_52-63_suit_swap.jpg` |
| c05 | 101/-/107/-/122 | foreground-layer wipe: B's subject (black suit, back to camera) slides in from the left as a matte layer over A's background | pull-out z -3 -> -5/f sustained 15 f, roll -0.3 -> -0.9 deg/f peak f109 then decays | ease-in 3 f, then constant | B layer defocused near the lens | 2-4 px lateral sustained | - | - | `c_101-122_fg_layer_wipe.jpg` |
| c06 | 132/134/136/141/142 | zoom-out dissolve with horizontal slice glitch (B face fades over A) | z -11 at 136 decays to -1 at 161 (k 0.9) ; pan -5..-9 px/f | expo-out | sharp 1.0 -> 0.1 | 3-4 px | - | RGB slice glitch rows | `c_130-143_glitch_dissolve.jpg` |
| c07 | 163/167/170/177/178 | **eye portal**: push into Tom's eye (A); cut to a macro eye shot with B composited inside the iris (soft circular hole); push through the iris, the hole grows until B fills | A: z +1.7, +7.1, +13.2, +18.0, +22.0, +24.3 (f162-167) then +26.5..+33.3 plateau f167-175; B: +21.5, +14.9, +10.5, +6.0, +1.1 (f176-180) then reverses smoothly to pull-out -2.2/f (f181-200); ty up to +94 px/f (eye off centre); roll <= 2.4 deg/f | in: expo-in over 6 f; plateau 8 f; out: k 0.84, 10 % in 5 f | A sharp 1.0 -> 0.06 (radial, CA) | 7-9 px peak f166-168 | luma 21 -> 49 (skin fills), B arrives bright (102) | - | `c_160-179_eye_portal.jpg` |
| c08 | 211/214/216/221/223 | **zoom-through with B in a matte hole**: camera pushes into Tom's hand; A's background is replaced by B (small, vignetted) behind A's subject; the push carries past A's hand (foreground smears off the lens) and lands in B | A: z +0.7, +4.1, +8.3, +13.3, +20.1 (f210-214); plateau +24..+28 for 9 f (f215-224); B: +16.6, +14.8, +12.5, +9.6, +6.4, +1.7 (f225-230) then reverses into pull-out -3/f; roll +0.8, +2.1, +2.9, +2.4 (f212-215) then -2.3, -6.2, -7.6 deg/f (f222-224) | in: expo-in 4 f (z doubles per frame); plateau; out: 10 % in ~7 f | sharp 0.45 -> 0.06; aniso 0.58 (directional smear along the push) | 4-15 px f215-219 | luma 47 -> 82 (white shirt fills) -> 22 (dark B) | total magnification x41 over 21 f | `c_210-225_zt_hand.jpg` |
| c10 | 283/-/288/-/298 | **background swap + fly past subject**: B's world (snowy street) wipes in from the right behind A's subject (matte), then the camera pushes past the subject, who smears off to the left, leaving B | push ramps z -0.5 -> +4..+8/f (f285-297) with pan -12 -> -28 px/f and roll -0.5..-1.2 deg/f; then constant push +3.5..+4.6/f for 20 f (f297-317) | ease-in ~7 f, then constant | subject motion-blurred as it passes (foreground), B sharp | 1 px | luma 20 -> 132 as the bright street fills | - | `c_278-305_bg_swap.jpg` |
| c11 | 317/319/320/322/323 | **zoom into 3D ground text + white flash** | A: z +3.5 -> +5.8 -> +31 (f317-319); flash; B: +22, +18, +15, +14, +12.5, +8.9, +8.4, +6.9, +6.3, +5.3, +2.3 (f323-333) with pan -48 -> -8 px/f | in 3 f; out k 0.84-0.88, 10 % in 10 f | radial streaks + bloom | 6-12 px on B's first 8 f | **white flash 3 f** (luma 121 -> 185/178/165, 30 % of pixels clipped), decays to base over 12 f; cyan/magenta | B has cyan energy rings + magenta shards | `c_314-333_zt_text_flash.jpg` |
| c12 | 359/360/361/361/362 | **pan-push zoom-through, B rotated** | A: pan accelerates -24, -30, -40, -44, -52, -67, -117 px/f (f352-359) + z +0.8, +3.2, +8.9, +25 (f356-359), roll +0.3 -> +0.8 deg/f; B lands rotated ~-30 deg pulling OUT: z -19, -14, -8, -8, -8, -7, -6, -5, -4, -3.5, -2.7, -2 (f362-373), ty -104 -> -6 | in 6 f (pan first, zoom last 3 f); out 12 f, k 0.80 | blue directional streaks f360-361 | 9-60 px rainbow on smear | blue-white | - | `c_355-366_zt_roll.jpg` |
| c13 | 378/379/380/381/382 | zoom-through (push in A -> pull out B) | A: z +2.1, +5.9, +12.3, +27 (f376-379), roll -0.5..-1.1; B: z -17, -14, -11, -12, -9, -7, -6.5, -5.5, -4.3, -3.1, -1.4, -0.6 (f382-393), ty +20 -> +13 | in expo 4 f; out k 0.80, 11 f | 2 smear f, sharp 0.01 | 40+ px on smear | luma 58 -> 124 -> 77 (light leak) | - | `c_376-385_zt.jpg` |
| c14 | 397/398/400/401/402 | **subject flies into the lens** (A's Spider-Man fills the frame) -> B pushes in | A: subject motion only (camera z ~0); B: z +29, +17, +14, +11, +9, +6.9, +5.3, +4.4, +3.5, +3.0, +2.7, +2.0, +1.6, +0.8 (f401-414) with pan +136 -> +10 px/f | out expo k 0.80, 13 f | subject smear 2 f | 10 px sustained through B | flash luma 137 (f400) | - | `c_395-406_subject_dive.jpg` |
| c15 | 418/419/420/421/423 | **diagonal whip** (pull-out + pan), warm streaks | A: z -0.8, -3.7, -8.4, -16.5, -23.7 (f415-419), pan (-7,-14) -> (-83,-40) px/f; B keeps pulling out: z -19, -10, -4.7, -3.5, -6, -6, -5.5, -5, -4.6 (f422-430), pan -184, -90, -94, -62, -54, -42, -34, -27, -22, -18 px/f | in expo 4 f; out pan k 0.8 | B defocused (rack focus) 4 f, sharp at f425 | 8-20 px | warm orange street lights bloom | - | `c_416-427_whip.jpg` |
| c16 | 435/437/~441/444/446 | **red ring portal** (concentric glowing red arcs grow out of the centre, B inside, push through) | push z +2.6, +11, +19, +15 (f435-438), then sustained +6..+8.5/f for 12 f (f439-450), decays to +1.2 by f455 | in 3 f, sustained 12 f, out 6 f | rings smeared/glow, B soft until 446 | 1-2 px | red-orange rings, glow | rings: 3-4 arcs, thick, additive | `c_434-449_red_ring.jpg` |
| c17 | 458/459/461/462/463 | zoom-through into a radial streak tunnel (B is itself radial streaks) | A: z -1.7, -5.2, -17.5 (pull-out f457-459!); B: -21, -9.3, -3.9, -3.5, -2.1 (f463-467) then push +2..+4.5/f (f469-479) | out k 0.5 | radial | 10-30 px | orange | streaks in B | `c_456-467_zt_streaks.jpg` |
| c18 | 477/478/481/483/484 | zoom-through via orange flare -> dark frame -> B lands **rolling** | A push z +4..+4; flare f479 (orange, luma 109), f480 near black (44); B: roll +6.1, +5.9, +4.8, +2.2, +1.3, +0.9 deg/f (f484-489), pan -208, -128, -102, -54, -34, -28, -20, -15, -10 px/f | roll settles in 5 f | B defocus 2 f | 5-18 px | orange flare + dark dip | - | `c_476-487_zt_flare.jpg` |
| c19 | 493/495/497/499/500 | **B-subject wipe**: B's arm/body (huge, near the lens, orange-lit) sweeps across A as a shaped matte, then B resolves | B: z -24, -21, -36, -23, -20, -19, -15 (f496-501), pan +38 px/f, ty -47 -> -27; settles to z -2/f by f505, then a constant roll drift +0.5..+0.8 deg/f (f505-517) | out 7 f | directional, along the arm | 4 px sustained | warm | - | `c_492-503_subject_wipe.jpg` |
| c20 | 518/519/520/521/522 | **whip down through black** (legs swing up, 1 dark frame, B from above) | A: z +1.3, +5.0, +10.6, +29 (f516-519); B: z -18, -17, -15, -9, -8.5, -6.6, -5.5, -4 (f522-529) with ty +181, +106, +35, +34, +34, +19, +14, +11 px/f (picture slides down = camera tilts up), roll -0.9..-2.6 | in 4 f; out ~8 f | vertical streaks | 10-34 px | 1 dark frame (luma 27) + flash 62 | - | `c_515-526_whip_down.jpg` |
| c21 | 539/540/541/541/542 | lightning flash zoom-through | A: tilt ty -10, -26, -28, -27, -52 px/f, z +7, +9; B: z +5.3, +9, +7.3, +6.3, +5.8, +5.8, +5.6, +4.4, +3.6, +3.1 (f542-551) roll -1.4, -1.9, -2.2, -2.0, -1.5, -1.0 deg/f | B push sustained ~8 f then decays | 2 f | big on flash | **blue-white lightning flash 2 f** (luma 100, 12 % clipped) | lightning arcs in B | `c_536-545_lightning_flash.jpg` |
| c22 | 557/558/559/560/562 | zoom-through warm flash -> long pull-out | A: z -0.2, -1.9, -5.6, -17.5 (pull-out, f556-558); **warm white-orange flash f559-561** (luma 106 -> 143, 18-28 % clipped); B: z -24, -15.6, -11, -10, -8.5, -7.5, -6.7, -6.4, -5.9, -5.1, -4.4 (f561-571) then the shot's own pull-out continues -5..-14/f for 25 f | flash decays over ~8 f | 3 f | 20-45 px on flash frames, 5-15 px for 8 f after | warm white/orange | - | `c_555-566_zt_flash.jpg` |
| c23 | 597/598/601/601/602 | debris bursts toward camera, rainbow smear, B lands upside-down falling | A: pull-out z -14 continuing; smear f598-600 (rainbow CA, luma 152); B: z -60?, -38, -12, -9, -9, -7.5, -6.4, -5.3, -4.5, -4.1, -3.2, -2.6, -2.2, -1.3 (f602-614) with ty +98, +181, +124, +97, +59, +48, +39, +35, +29, +22, +20, +15, +11 px/f | out expo k ~0.8, 12 f | rainbow directional | **up to 86 px rainbow split** on f599 | warm flash | shards/debris in A | `c_590-605_bg_explode.jpg` |
| c24 | 617/618/620/620/621 | subject dives into lens -> B pull-out with roll | A: z +0.8, +4.1, +9.6 (f615-617); B: z -28, -20, -18, -14.5, -10, -6.8, -5.9, -4.5, -3.3, -2.3, -1.6, -1.1, -0.5 (f621-633), pan -152 -> -4 px/f, roll -1.3, -3.9, -4.7, -3.7, -0.6 deg/f | out k 0.71, 10 % in 8 f | 2 f dark warm smear | 16 px on B's first frame | dark warm | fire embers | `c_615-626_subject_dive.jpg` |
| c25 | 636/637/-/-/640 | end: push z +2.4, +6.2, +18.6 into black | expo-in 3 f | - | - | to black | - | - |

Also in c (not cuts): 3D text CHATTER -> SPIDER-MAN rebuilds in place (f15-48, f37-48 letters re-form in depth),
"WE READY? BY SANCHEZ" (f240-262) then the letters disintegrate into drifting particles left->right (f262-280,
`c_256-279_text_disintegrate.jpg`), SPIDER-MAN / BRAND NEW DAY laid on the street with a mirrored reflection (f290-320).

### Ref c: holds (between transition windows)

| hold | frames | zoom %/s mean (min..max) | roll deg/s | pan px/s | still frames (< 0.3 %/f) |
|---|---|---|---|---|---|
| c01->c03 | 13-54 | +5 (-44..+79): pull-out reverses into push over 6 f (f33-40) | +0.2 | 49 | 1/42 |
| c03->c05 | 65-100 | +21 (-19..+44) | -0.7 | 26 | 3/30 |
| c05->c06 | 123-130 | -80 | -5.0 | 99 | 0/8 |
| c06->c07 | 151-160 | -59 | +1.6 | 20 | 0/10 |
| c07->c08 | 186-208 | -47 (-68..-25), decelerating pull-out | +1.0 | 82 | 0/23 |
| c08->c10 | 236-279 | +1 (-89..+126): pull-out, reverses into push (f240-244, 5 f), back to pull-out (f258-262) | +0.6 | 46 | 1/44 |
| c10->c11 | 306-314 | +102 (constant push) | -1.7 | 70 | 0/9 |
| c11->c12 | 337-351 | -161 | +3.0 | 499 | 0/14 |
| c22->c23 | 576-593 | -339 | -1.5 | 389 | 0/18 |

**The camera is never still: 5 of ~230 hold frames are below 0.3 %/frame.** Typical hold drift is 1.5-3.5 %/frame of
zoom (45-100 %/s), i.e. ~10x faster than v2's holds; direction reversals inside a hold take 5-7 frames and pass smoothly
through zero.

### Ref a (eitaX, 852 f): transitions (from the sheets and full-res frames; measured numbers follow in v2 of this section)
Ref a's f580-792 replays f330-530's shots with new transitions (an extended cut); f792-851 is the eye-logo outro.

| # | frames (approx.) | type |
|---|---|---|
| a01 | 0-8 | open: small oval iris from black grows with push-out |
| a02 | 34-58 | 2D/3D outline text ALL/ABOUT -> FORGET (glow red, scales up, camera pushes) |
| a03 | 58-72 | **eye portal**: push past FORGET into the eye, B (Peter in crowd) inside the iris, iris grows to fill |
| a04 | 84-96 | in-shot suit morph (Peter -> Spider-Man) with radial blur and red light |
| a05 | 108-134 | **red swirl ring portal** (spiral red arcs), push through to B (hands-on-head) |
| a06 | 134-140 | zoom-through dark warm smear -> Strange |
| a07 | 164-182 | **sling ring portal**: orange spark ring opens around Strange's hand, B (Tom) inside it, push through, orange leak |
| a08 | 198-262 | 3D text WE READY? flies in (letters from the left in depth), "IS" chunks explode (f226-240), SPIDER-MAN assembles out of 3D chunks flying in (f244-256) |
| a09 | 264-272 | zoom-through text -> red/blue directional smear -> B (falling, debris) |
| a10 | 280-288 | zoom-through: radial smear, sky-blue blur -> B (moon) |
| a11 | 298-304 | zoom-through -> B (Spider-Man on ledge) |
| a12 | 330-338 | zoom-through warm -> B (sling-ring Spider-Man) |
| a13 | 346-354 | zoom-through orange smear |
| a14 | 362-370 | zoom-through cyan |
| a15 | 382-392 | orange swirl rings over B (push) |
| a16 | 396-404 | zoom-through -> B with I HAVE TO TRY 3D text laid in the scene (letters stand up on the ground, f404-426) |
| a17 | 426-434 | whip/smear blue -> B (rotated city) |
| a18 | 444-452 | zoom-through grey -> B (flying under moon) |
| a19 | 462-466 | zoom-through -> B (iron spider) |
| a20 | 476-484 | smear -> B |
| a21 | 494-500 | smear warm -> B (EITAX logo in the scaffold) |
| a22 | 526-534 | zoom-through -> B (debris, moon) |
| a23 | 544-550 | zoom-through radial -> B |
| a24 | 560-566 | zoom-through -> B (ledge, I'M READY 3D text, f578-594) |
| a25-a33 | 594-792 | replays a12-a21 with the same transition types |
| a34 | 790-796 | push into the eye of B -> eye logo outro (glowing outline eye/web on black) |

### Recipes for v3 (from ref c; ref a values will refine them)

**The universal shape (every flow transition in c):**
1. **Attack (A):** the speed roughly doubles every frame for 3-4 frames: z ~ +1, +4, +9, +20..30 %/frame (ease-in-expo,
   ~2x/frame). Pans do the same (-24 -> -117 px/f over 7 f in c12, pan starts before the zoom).
2. **Smear: 1-3 frames** (median 2) where neither shot is readable: sharpness 1-6 % of the clean value, directional or
   radial streaks, chromatic split 10-60 px at the edges (up to 86 px), usually with light: a flash/leak raises mean
   luma by +40..+120 % for 1-3 frames (white only on the biggest hits: c11 3 f, c22 3 f; otherwise orange, blue-white,
   or a near-black dip).
3. **Landing (B): B arrives at the SAME speed magnitude** (z 15-30 %/f, pan 100-200 px/f) and decays expo-out with
   **k = 0.75-0.85 per frame**, reaching 10 % of its landing speed in **7-12 frames**. The first 2-4 B frames are soft
   (motion blur + a rack-defocus that sharpens over 3-4 frames) with 5-15 px of chromatic split that fades over 6-10 f.
4. **Then the hold keeps drifting** at 1.5-3.5 %/f zoom (or 1-5 px/f pan, 0.5-1 deg/f roll) and, where the next
   transition needs the other direction, reverses smoothly over 5-7 frames.

**Direction:** the zoom SIGN does not have to continue (c: push-in A -> pull-out B in c12, c13, c20, c23, c24; push ->
push in c07, c08, c14, c21; pull -> pull in c15, c22). What continues is the **speed magnitude and the screen direction
of the pan/roll**. A push-in into a pull-out works because the smear frames hide the sign change. EDIT.md's zt
(`peak` -> `land` > 1 then pull-out) matches this.

| v3 type | pre f | post f | peak speed | landing | ease | smear f | CA px (1920) | leak / flash | hold drift after |
|---|---|---|---|---|---|---|---|---|---|
| `zt` | 4-6 (expo-in, ~2x/f) | 8-12 | z 25-30 %/f at the last A frame (A scale x2.5-3.5 over the attack) | B at z -15..-25 %/f (pull-out) or +15..+30 (push) | out expo k 0.80 | 2 (1-3) | 15-40 on smear, 8-15 for 6-8 f after | act-coloured leak +50-100 % luma for 2 f; white only on the biggest hits | 1.5-3 %/f, reverse in >= 6 f |
| `whip` | 4 | 8-10 | pan 80-120 px/f (1350) = 110-170 px/f at 1920 + z -15..-25 | B pan 180 -> 0 with k 0.8 | in expo, out expo | 2 | 10-20 | warm streak bloom | pan 1-3 px/f |
| `eye_tunnel` / eye portal | 6 (expo-in) + 6-8 f plateau at z 25-33 %/f | 5 | total magnification x20-40 | B inside a soft circular hole that grows; B already moving | in expo, out k 0.84 | 0 (the hole replaces the smear) | 7-9 | skin warm fill | B reverses to -2 %/f pull-out after 5 f |
| `sling_ring` / ring portal | 3 | 6 | z +11..+19 then sustained +6..+8.5 for 12 f | push continues into B | ease-in 3 f, constant, ease-out 6 f | 0 | 1-2 | rings: red/orange additive glow | push decays to 0 over 6 f |
| `slam` / subject dive | 3 | 13 | A subject fills the lens | B z +29 -> 0 (k 0.80) + pan 136 -> 10 | expo-out | 2 | 10 sustained | flash luma +100 % 1 f | - |
| `flash` (lightning/white) | 2 | 8 | - | - | flash decays over 6-12 f | 2-3 | 20-45 | 2-3 f, 12-30 % pixels clipped | - |
| background swap | 7 | 20 | z 4-8 %/f + pan 12-28 px/f | constant push 3.5-4.5 %/f | ease-in 7 f | 0 | 1 | - | push continues |

### The 10 things that make c (and a) feel smooth, ranked
1. **Speed continuity, not position continuity:** B lands at the speed A left with (both 15-30 %/f), then decays
   expo-out (k ~0.8). There is never a fast-to-still jump.
2. **The camera never stops:** 98 % of hold frames move > 0.3 %/f; typical hold drift 45-100 %/s of zoom.
3. **Short, total smears:** 1-3 frames where nothing is readable (sharpness < 6 %), not long half-readable blends.
4. **Expo-in attack ~2x per frame over 3-4 frames**, so the cut lands on the fastest frame.
5. **Light inside the smear:** a leak/flash of the scenes' own colour (+50-120 % luma) on the smear frames.
6. **Chromatic split scales with speed:** 10-60 px at the peak, 5-15 px on the first landing frames, ~0 in holds.
7. **Rack-defocus landing:** B's first 2-4 frames are out of focus as well as motion blurred and snap sharp.
8. **Layering with mattes:** the subject is kept as a foreground layer while the background becomes B (c08, c10), or
   B's subject sweeps over A (c05, c19); this gives real depth without a 3D package.
9. **Pans lead, zoom follows:** in the fastest cuts the lateral move starts 3-4 f before the zoom (c12, c15, c20).
10. **Roll lands and settles:** roll is added in the last 2-3 A frames (+1..+3 deg/f) and B lands rolling 4-8 deg/f,
    settling in ~5 f (c08, c18, c24).

### Where EDIT.md differs from c
- EDIT.md says "B decelerates (expo-out) 8-14 f": matches (7-12 f to 10 %).
- EDIT.md's hold drift is "slow". The refs' holds are fast (1.5-3.5 %/f zoom); "slow" should mean >= 1 %/f, never < 0.3.
- EDIT.md "direction continues through the cut": the refs keep the speed and the pan/roll screen direction; the zoom
  sign often flips (push in -> pull out) behind the smear.
- The refs use a rack-defocus on landing (not in EDIT.md): add a defocus (DoF or a finishing blur) on B's first 2-4 f.
