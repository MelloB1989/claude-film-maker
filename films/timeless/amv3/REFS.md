# REFS: measured study of the v3 reference edits

## Refs a and c (eitaX "We ready?" and sanchezae "We Ready?") — agent-03, task v3-refs-ac

**Status: v2 (refs a and c measured; a and c recipes merged).**

### How the numbers were made (reproducible)
- Frames: `ffmpeg -i <ref>.mp4 -start_number 0 -q:v 2 f_%04d.jpg` (frame 0 = first frame; same numbering as the
  `sheets/` contact sheets).
- `tools/filmtools/amv3/analysis/ref_metrics.py <frames> <out.csv>`: per frame f, the global similarity transform
  f-1 -> f (ORB + RANSAC on 1/4-res frames, refined by ECC affine; reported about the frame centre), Laplacian
  sharpness, radial/tangential gradient share, structure-tensor anisotropy, R-vs-B misregistration (chromatic split at
  the frame edge, full-res px), luma and clipped-white fraction.
- `tools/filmtools/amv3/analysis/transitions.py <csv> cuts/{a,c}.json --holds`: per-window traces, attack/settle, hold drift.
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


### Ref a (eitaX, 852 f): every unique transition
Ref a is an extended cut: **f527-789 replays f264-526** frame for frame (same motion traces, offset 263), and
f792-851 is the eye-logo outro. The unique material is f0-543. **Ref a repeats one frame every 30 f** (f30, 60, 90...:
frame-rate conversion); those frames are excluded from the numbers (they are not designed holds).

| # | frames: last clean A / first smear / cut / last smear / first clean B | type | what moves (measured) | ease | blur | CA | light | extras | strip |
|---|---|---|---|---|---|---|---|---|---|
| a01 | -/0/0/1/3 | open: small oval iris from black, push decelerating | z +31, +16.7, +10.2, +7.6, +6.1, +5.2, +4.4, +3.5, +3.1, +2.7 ... +0.2 (f1-20), then reverses into pull-out -0.1..-2.8 over 8 f | expo-out k 0.55 then 0.85, 10 % in ~9 f | defocus + vignette, sharp by f12 | 8 px f2-3 | luma 6 -> 40 over 12 f | - | (sheet) |
| a03 | 60/-/61/-/70 | **eye portal through 3D text**: FORGET (red emissive, bloom) in front of the face; the camera pushes, the word slides down past the lens (foreground parallax); cut to a macro eye with B (Peter in a crowd) inside the iris; the iris grows until B fills | A: z +0.4, +0.6, +1.7, +2.8, +4.1, +4.5, +5.5, +6.4, +7.2, +8.2, +9.3, +10.4, +11.6, +13.0 (f46-59: a **15-frame near-linear ramp**, +0.9 %/f per frame); eye: +33?, +17.6, +19.3, +19.6, +22.2, +23.2 (f61-66); B: +13.8, +9.0, +4.0, +3.8, +2.4, +1.0, +0.2 (f67-73) then pull-out -0.4..-3.2 (f74-84); ty +9..+56 px/f (the eye is above centre) | ramp 15 f, plateau 6 f, out k ~0.6, 10 % in 6 f | no unreadable frame; sharp falls to 6 % | 2 px | red text glow, skin | PETER PARKER outline text on B | `a_54-73_eye_portal.jpg` |
| a04 | 84/85/86/88/89 | in-shot suit morph (Peter -> suit) with a radial punch | z +1.6, +5.1, +4.5, +1.8, +0.1 (f85-89) | punch 2 f in, 3 f out | radial, sharp 0.1 for 3 f | 3 px | red | - | (sheet) |
| a05 | 114/-/120/-/123 | **red swirl ring portal**: spiral red light arcs grow out of the centre over A, B (hands on head) dissolves in behind them | push z +0.2, +0.5, +0.8, +1.1, +1.3, +1.7, +2.2, +2.9, +3.7, +5.6, +5.0, +6.6, +5.3, +6.4 (f106-119), roll -0.4 -> -1.1 deg/f (f115-119), -2.5 at f121; B: +4.4, +4.6, +4.0, +3.7, +3.3, +2.9, +2.6, +2.2, +1.9, +1.5, +1.0 (f122-132) | ramp 14 f (~1.3x/f), out k 0.88 | none | 1 px | luma 26 -> 100 (red light builds) | spiral rings | `a_108-131_red_swirl_ring.jpg` |
| a06 | 133/134/136/138/139 | pull-out whip, dark warm smear | A: z -1.9, -8.1, -23.1 (f133-135), pan +13, +40, +51 px/f; B keeps pulling out and panning the same way: z -15, -13.3, -10.8, -8.8, -7.9, -6.6, -5.7, -5.1, -4.3, -4.2, -3.8 (f139-149), pan +59, +37, +35, +31, +26, +25, +21, +19, +18, +14, +12 px/f, then roll -1.4..-2.3 deg/f (f152-157) | in expo 3 f; out k 0.87 | 3-4 smear f, sharp 0.1 % | 50-60 px on smear | dark warm (luma 79 -> 31 -> 54) | - | (sheet) |
| a07 | 175/-/178/-/181 | **sling ring portal**: an orange spark ring opens around Strange's hand (15 % of frame at f166), B (Tom) is already inside it at f168, the push grows the ring past the frame edges (f176-177), sparks/embers fly; the whole frame is orange for 4 f, then B clean | push z +1.6, +3.3, +3.2, +3.5, +4.3, +5.6, +6.9, +8.6, +10.1, +11.7, +13.8, +15.8, +21.4, +29.1, +27.7, +23.2, +7.8 (f163-179), pan +10 -> +93 px/f (ring right of centre); B: +13.4, +6.4, +6.2, +4.5, +3.3, +1.9, +1.2, +0.5 (f181-188), then pull-out -0.4..-2.8 | **ramp 14 f (~1.2x/f)**, out k ~0.7, 10 % in 7 f | no unreadable frame; sharp 7 % at the peak | 1-5 px | orange leak: luma 33 -> 110 (f163-176), orange wash f176-180, clean f181 | spark ring, embers | `a_164-187_sling_ring.jpg` |
| a08 | - | 3D text "IS" explodes into gold chunks (camera kick) | roll impulse -3.9 deg/f at f230 decaying -2.6, -2.2, -1.7, -1.1, -0.9, -0.7, -0.5, -0.4 (k 0.78) | impulse + expo decay | chunks motion-blurred | 0 | - | gold extruded slabs fly past the lens up-left for 14 f | `a_224-247_text3d_explode.jpg` |
| a09 | 264/265/268/270/272 | zoom-through out of the 3D title (push -> push) | A: z +6.9, +22, +59 (f264-266); B: +8.6, +7.2, +6.2, +5.6, +4.7, +4.1, +3.6, +3.0 (f272-279), pan -48 -> -8 px/f | in expo 3 f (~3x/f); out k 0.85 | 4 smear f, red/blue directional | 7 px | luma 30 -> 82 | debris in B | `a_244-267_text3d_assemble_zt.jpg`, `a_264-279_zt_push_push.jpg` |
| a10 | 281/282/284/285/286 | **pull-out through flash (pull -> pull)** | A: z -4.9, -19.2, -71 (f281-283); B: -15.2, -15.1, -12, -10.2, -9.1, -8.0, -6.9, -5.9, -4.7, -3.6, -2.5, -1.2 (f286-297), ty -57 -> +12 px/f | in expo 3 f; out k 0.86 | 3 f, sky-blue radial | 40-60 px on smear | white-blue flash luma 152 (8 % clipped) 1 f | - | `a_279-292_pull_flash_pull.jpg` |
| a11 | 298/299/300/302/303 | push through flash, B lands **rolling** | A: z +7.5; B: z +6.1, +4.6, +4.0, +3.7, +3.1, +2.9, +2.8, +2.1, +1.1 (f303-311), **roll +2.9, +2.3, +1.5, +1.0, +0.7, +0.6, +0.5 deg/f** (f303-309), pan (-15, +57) -> (-26, +16) | out k 0.8 | 3 f | 60-90 px on smear | luma 93 1 f | - | (sheet) |
| a12 | 331/332/334/337/338 | zoom-through warm (push -> push) | A: z +8, +21 (f331-332); B: +4.2, +3.4, +2.6, +2.5, +2.3, +2.1, +1.8, +0.5 (f338-345), pan -33 -> -10 px/f | out k 0.9 | 5 f (incl. dup) | 20-80 px | warm | - | (sheet) |
| a13 | 346/348/350/352/353 | pull-out through orange flash | A: z -2.4, -6.4, -17.5 (f346-348); B: -18.6, -13.4, -10.4, -9.2, -7.8, -6.7, -5.6 (f353-359) | in expo 3 f; out k 0.84 | 4 f | 15-150 px on smear | orange flash luma 119 for 3 f | - | (sheet) |
| a14 | 365/366/367/369/370 | pull-out through cyan flash | A: z -3.5, -3.2, -4.9, -12 (f362-365); B: -13.7, -12, -9.4, -8.5, -8.1, -7.5, -7.0, -6.3, -5.7, -4.9, -4.2 (f370-380) | out k 0.9, 12 f | 4 f | 20-70 px | cyan flash luma 134 for 2 f | - | (sheet) |
| a15 | 381/-/388/-/392 | **orange swirl rings, push** (B: arms-out pose inside spiral light arcs) | push z +1.0, +20, +34, +51?, +27, +25, +25, +18, +18 (f381-389), +28?, +13, +11, +8.9, +6.4, +3.3 (f391-396) | ramp 2 f, sustained ~+25 %/f for 6 f, out k 0.8 | bright glow, no unreadable frame | ring colours | **luma 85 -> 171, 17 % clipped** (rings blown out), 6 f | spiral orange-cyan arcs | `a_380-395_swirl_rings_bright.jpg` |
| a16 | 396/397/400/402/403 | zoom-through -> 3D text laid in the scene | B: pull-out z -4.9, -8.6, -7, -5.1, -6.1, -8.2, -4.6, -7.1, -4.4 (f403-411) with pan +49 -> +6 px/f; then push +6.6..+9.5 (f415-418) | - | 5 f | 50-600 (unreliable) | flash luma 145 1 f | I HAVE TO TRY rises from the ground (below) | `a_400-427_text3d_ground.jpg` |
| a17 | 426/427/431/433/434 | blue whip smear -> rotated city (push -> push) | A: z +2.1, +11 (f427-428); B: +10, +7.1, +5.4, +4.3, +3.4, +3.0, +2.3, +1.8, +1.4, +0.9 (f434-443), pan (+15, -20) px/f constant | out k 0.8 | **6 f** (f427-433) | 30-190 px | dark blue | - | (sheet) |
| a18 | 445/446/449/451/452 | pull-out grey smear -> B under the moon | A: z -1.5, -6.0, -17.3 (f444-446); B: -13, -10.5, -9.3, -8.3, -7.1, -6.3, -5.4, -4.8, -4.0 (f452-460), roll +1.45 -> +0.13 deg/f | in expo 3 f; out k 0.88 | 5 f | 50-120 px | luma 83 -> 106 | - | (sheet) |
| a19 | 461/462/465/466/467 | push-through -> iron spider, **constant roll drift in B** | A: z +1.5, +16.5, +50 (f461-463); B: +10.7, +7.2, +5.5, +3.9, +3.1, +2.6, +2.2, +1.7, +1.8, +1.1, +1.0 (f467-477), **roll +1.2..+1.8 deg/f for 11 f**, pan +19 px/f | in expo 3 f (~3x/f); out k 0.8 | 4 f | 90-130 px | luma 101 | - | `a_459-474_zt_roll_drift.jpg` |
| a20 | 477/478/480/481/482 | **roll kick whip** -> pull-out | A: roll +1.8 -> +9.6 deg/f (f477-478); B: z -25, -22, -19, -17, -14.4, -12.7, -11.1, -9.7 (f482-490), roll +0.5..+1.4 deg/f, ty -46 -> -14 | out k 0.88 | 2 f | 300 px on f478 | luma 85 1 f | - | `a_476-491_roll_kick_whip.jpg` |
| a21 | 494/495/497/499/500 | pull-out dark smear -> EITAX scaffold | A: z -3.4, -5.4, -11.4 (f492-494); B: -11.3, -9.7, -8.6, -7.6, -6.9, -6.3, -5.7, -5.1, -4.6, -4.0 (f500-509), pan -34 -> -5 px/f | out k 0.89 | 5 f, dark (luma 32-42) | - | dark dip | 3D EITAX letters on the scaffold | `a_491-506_pull_dark_smear.jpg` |
| a22 | - | in-shot push + roll punch (the kick) | z +2.9, +10.1, +15.2, +18, +15.3, +16.6, +17.2, +16.5, +13.3, +11.6, +9.2, +6.8, +4.3, +3.2 (f512-525), **roll -1.0..-3.0 deg/f for 13 f** | ramp 4 f, plateau 5 f, out 6 f | motion blur only | 3-8 px | - | - | `a_510-529_push_roll_punch.jpg` |
| a23 | 526/527/530/532/533 | pull-out -> white flash -> push (the one sign flip in a) | A: z -2.8, -14.9; B: +11.3, +10.4, +8.6, +7.2, +6.2, +5.6, +4.8 (f533-539), pan -30..-52 px/f | out k 0.87 | 5 f | 20-60 px | **white flash luma 148, 18 % clipped** | - | (sheet) |
| a37 | 791/792/793/793/794 | push into B's eye -> eye-logo outro | outro: pull-out -0.5..-9 %/f accelerating while the logo spins faster: roll +0.5 -> +33 deg/f (f797-846) | - | 2 f | - | to black | glowing outline eye/web logo | `a_786-851_eye_outro.jpg` |

**Ref a holds:** hold drift -0.7..-4.4 %/f zoom (20-130 %/s), pans 2-10 px/f, roll 0.1-0.5 deg/f. Near-still stretches
exist but are rare (a f92-108: |z| < 1 %/f with 2-3 px/f pan + 0.1-0.2 deg/f roll; 3 of 24 frames in f21-44 below
0.3 %/f). Long holds reverse direction once, over 6-10 frames (f21-28, f74-84, f187-190, f312-314).

### Refs a vs c (what differs)
| | ref a (eitaX) | ref c (sanchezae) |
|---|---|---|
| smear frames per cut | 3-6 (median 4) | 1-3 (median 2) |
| zoom sign across the cut | kept: push -> push 8x, pull -> pull 10x, flip 1x | flipped 5x of 9 zts (push -> pull) |
| landing speed | push landings 6-11 %/f; pull-out landings 11-25 %/f | 15-30 %/f |
| settle k | 0.80-0.90 (median 0.86): 10-12 f to 10 % | 0.75-0.85: 7-12 f |
| portals | eye, red swirl, sling ring, orange swirl: long ramps (14-15 f, ~1.2-1.3x/f), **no unreadable frame**, B already inside | eye, red rings, B in matte hole: 6 f expo ramp + 6-9 f plateau at 25-33 %/f |
| flashes | many: 1-3 f at luma 120-150 (blue-white, orange, cyan), 2 big ones at 17-18 % clipped | 2 white flashes (3 f, 30 % clipped), lightning 2 f |
| roll | roll landings (+3 deg/f -> 0 in 6 f) and constant roll drift (1.2-1.8 deg/f, 11 f); punches with 1-3 deg/f roll for 13 f | roll landings (4-8 deg/f -> 0 in 5 f) |
| 3D text | lots (below) | 3 titles |

### 3D text (refs a and c)
- **WE READY? (a f198-226):** chunky condensed italic sans, red face with a dark cracked/grunge texture, red rim glow,
  cap height ~25 % of frame height, the whole word ~95 % of frame width; flies in from the left in depth (f198-206,
  8 f) with horizontal motion blur trailing ~100-200 px; **sits behind the subject** (his head occludes READY); slight
  perspective (closer on the left). "BY EITAX" small (5 %) white serif extruded, top right.
- **IS (a f224-243):** hollow outline letters (thin white stroke, glassy, ~40 % frame height) in front of the subject;
  on the hit (f229) it **explodes into gold extruded slabs** that fly past the camera up-left with heavy motion blur
  for 14 f, and the camera gets a roll kick (-3.9 deg/f decaying, k 0.78).
- **SPIDER-MAN / brand new day (a f244-264):** Spider-Man movie font (pointed serifs), **red face, gold/cream bevelled
  extrusion, depth ~15-20 % of cap height**, visible on the bottom/right sides; cap height ~20 % of frame, word ~82 %
  of width. Letters fly in from the left/near the camera, rotating, overlapping in depth, motion-blurred, and land in
  **~10 f** (f244-254); then the camera pulls out -4..-5 %/f while "brand new day" (gold-cream, 50 % size) fades in
  over 3-4 f; the background is **defocused** while the title holds (rack focus to the text); web strands overlay the
  corners (white, ~30 % opacity). Exit (f262-266): Spider-Man rises through the title and the camera zoom-throughs it.
- **I HAVE TO TRY (a f403-427):** white/silver chrome serif letters, extruded, **standing on the ground** around the
  subject's feet with sparks/debris at their base, in perspective with the floor; they rise into place one by one
  (f403-410, ~1 f stagger, from below/near the lens, motion-blurred) and at the end **tumble and scatter upward
  individually** (f422-427, rotating, blurred), 5 f.
- **FORGET (a f52-66):** red emissive letters with strong bloom, in front of the face; the camera pushes and the word
  slides down and past the lens (foreground parallax) as the eye portal opens.
- **c: CHATTER -> SPIDER-MAN (f15-48)** rebuild in place behind the hosts; **WE READY? BY SANCHEZ (f240-280)** in red
  extruded letters behind Tobey that disintegrate into particles drifting right (18 f); **SPIDER-MAN / BRAND NEW DAY laid
  on the street** with a mirror reflection (f290-320), then the camera zooms through it (c11).
- Common: letters are big (20-40 % of frame height), lit by the scene's colour (red rim / gold bevel), always moving
  (the camera keeps drifting while the text holds), enter in 8-10 f with motion blur, exit by exploding/scattering or by
  the camera flying through them, never by a fade alone.

### Recipes for v3 (refs a and c merged)

**The shape of a flow transition:**
1. **Attack (A):** expo-in. Fast cuts: speed x2-3 per frame over 3 f (z +7, +22, +59 in a09; +1, +4, +9, +25 in c).
   Portals: a long near-linear ramp over 14-15 f (+0.9 %/f per frame, ~1.2-1.3x/f) up to 13-30 %/f.
2. **Smear:** 2 f (c) to 4 f (a) where nothing is readable: sharpness < 6 % of clean, chromatic split 20-60 px (we:
   30-80 px at 1920), luma +40..+120 % from an act-coloured leak/flash (white only on the 2-3 biggest hits:
   17-30 % of pixels clipped for 1-3 f). Portals have no unreadable frame (the hole/ring replaces the smear).
3. **Landing (B):** at the same speed magnitude; expo-out k = 0.80-0.88/frame, 10 % in 7-12 f. First 2-4 frames
   defocused + 5-15 px CA, sharp by frame 4.
4. **Hold:** keeps drifting (zoom 1-3 %/f and/or pan 2-10 px/f and/or roll 0.2-1.8 deg/f); a reversal takes 6-10 f.

| v3 type | pre f | post f | attack | peak (last A frame) | landing (first B frame) | ease out | smear f | CA px @1920 | leak / flash | hold drift after |
|---|---|---|---|---|---|---|---|---|---|---|
| `zt` (push) | 4-5 | 9-12 | expo-in ~2.5x/f | z +22..+60 %/f (scale x1.25-1.8 per frame) | push +6..+11 %/f (a, keep sign) or pull -15..-25 %/f (c, flip) | k 0.85 | 2-4 | 30-80 on smear, 10-20 for 4 f after | act colour leak, luma +50-100 % 1-2 f | 1-3 %/f |
| `zt` mode pull (new) | 3-4 | 10-12 | expo-in ~3x/f | z -17..-70 %/f | pull -13..-19 %/f | k 0.86 | 3-4 | 30-80 | flash luma 120-150 for 1-3 f (orange/cyan/white-blue) | pull-out reversing to push over 6-10 f |
| `whip` | 3-4 | 9-11 | expo-in | pan 50-120 px/f (1350) = 70-170 px/f @1920 + z +-8..-23 | pan continues the same screen direction 60-180 -> 0, k 0.85 | k 0.85 | 3-4 | 40-80 | dark warm or blue | pan 2-5 px/f |
| roll whip (`whip` with roll) | 2 | 8-10 | roll +1.8 -> +9.6 deg/f in 2 f | - | B rolls +0.5..+3 deg/f and pulls out -25 %/f | roll k 0.75 | 2 | 50+ | 1 f flash | roll 0.5-1.5 deg/f |
| `eye_tunnel` / eye portal | 15 (linear ramp) | 6-7 | +0.9 %/f per frame | +13..+33 %/f, 6-8 f plateau | B inside a soft iris hole; hole grows to fill in 6 f | k 0.6-0.84 | 0 | 2-9 | warm skin fill / red text glow | B reverses to -2..-3 %/f pull-out after ~6 f |
| `sling_ring` | 14 (ramp ~1.2x/f) | 7 | from +1.6 to +29 %/f | ring passes the frame edge at the peak | B already inside the ring (visible 10 f before the cut), +13 -> 0 | k 0.7 | 0 (4 f orange wash instead) | 1-5 | orange: luma +230 % at the peak, wash 4 f | push -> pull-out reversal |
| ring/swirl overlay portal | 3-14 | 6-11 | ramp | sustained +6..+25 %/f for 6-12 f | B dissolves in behind the rings | k 0.8-0.88 | 0 | 1-2 | rings blow out: luma up to 171 (17 % clipped) | - |
| `slam` / subject into lens | 3 | 13 | subject fills the lens | - | B push +29 -> 0, pan 136 -> 10 | k 0.80 | 2 | 10 sustained | flash +100 % 1 f | - |
| `text_fly` | 3 | 8 | expo-in ~3x/f through the letters | +59 %/f | B push +8.6 -> 0 | k 0.85 | 4 | 10 | red/blue | - |
| in-shot punch (fx `punch`) | 4 | 6 | z +3, +10, +15, +18 | plateau +15..+17 for 5 f | - | out 6 f | 0 | 3-8 | - | with roll 1-3 deg/f all along |
| hit flash (`flash`) | 0 | 6-12 | - | - | - | decay over 6-12 f | 1-3 | 20-45 | white: 2-3 f, 17-30 % clipped; colour: 1-3 f at luma 120-150 | - |

### The 10 things that make a and c feel smooth, ranked
1. **Speed continuity:** B lands at speed (6-30 %/f) and decays expo-out (k 0.80-0.88, 7-12 f). Never fast -> still.
2. **The camera never stops:** ~97 % of hold frames move > 0.3 %/f (c 207/212, a 127/131 in f0-526, duplicates excluded); typical
   hold drift 1-3.5 %/f zoom, plus pan and roll.
3. **Short, total smears:** 2-4 frames where nothing is readable (sharpness < 6 %), not long half-readable blends.
4. **Expo-in attack** (x2-3 per frame over 3 f) so the cut lands on the fastest frame; portals instead ramp linearly
   over ~15 f and show B early.
5. **Screen direction continues:** pan and roll keep their sign through the cut (a06, a10, c15); a keeps even the zoom
   sign; c flips zoom sign only behind a 2-f total smear.
6. **Light inside the smear:** coloured leak/flash of the scenes' own hue (+40..+120 % luma, 1-3 f); white only on the
   biggest hits.
7. **Chromatic split scales with speed:** 20-60 px at the peak, 5-15 px on the first landing frames, ~0-1 px in holds.
8. **Rack-defocus landing** and defocused backgrounds behind held titles.
9. **Real layering:** subject kept as the foreground layer while the background becomes B (c08, c10); B's subject sweeps
   over A (c05, c19); text in front of a face passes the lens with parallax (a03); text behind the subject (a WE READY?).
10. **Roll as a flavour, not a gimmick:** roll impulses decaying in 5-8 f on hits, slow constant roll drift (1-2 deg/f)
    through some holds.

### Where EDIT.md differs from the refs (suggested changes)
- **Holds:** EDIT.md says "slow push/pull/roll drift". The refs drift 1-3.5 %/f (30-100 %/s), ~10x v2. Make the hold
  solver's minimum speed >= 1 %/f zoom (or >= 3 px/f pan, >= 0.3 deg/f roll) and allow 2-3.5 %/f.
- **Zoom direction:** EDIT.md's zt (push into A, B lands zoomed in and pulls out) is c's recipe. eitaX (a) keeps the
  sign (push -> push, pull -> pull) and feels smoother; add `zt` `mode: pull` (pull out of A through a flash into B
  pulling out) and prefer sign-keeping; when flipping, use >= 2 total-smear frames.
- **Smear length:** EDIT.md says 2-3 smeared frames; a uses 3-6. 2-4 is right; 4 on act changes.
- **Portals (eye_tunnel, sling_ring):** the refs ramp linearly for ~15 f and show B inside the hole/ring from the start
  of the ramp (B moving); there is no smear frame. EDIT.md's eye_tunnel window (16 pre) fits; make the ramp linear,
  not expo, and start B visible.
- **Landing defocus:** not in EDIT.md. Add a 2-4 f defocus on B (Cycles DoF focus pull or a finishing lens blur
  decaying with the camera speed).
- **Flashes:** EDIT.md keeps white for the biggest hit; refs agree (2-3 white flashes per edit), but they use many 1-3 f
  coloured flashes (luma 120-150) on ordinary cuts: put a coloured leak on every zt/whip smear.
- **Text:** EDIT.md's text3d (extruded, bevelled, lit, behind the subject, assemble/shatter) matches a. Add: a
  defocus on the plate while a title holds, letters landing in ~10 f, exits by tumble/scatter (5 f) or fly-through,
  and a gold/cream bevel against a red face (a SPIDER-MAN) as one palette option.

### Measurement caveats
- Motion numbers are a global similarity transform of the whole frame; on frames where the subject dominates (running,
  flying) they mix subject and camera motion. Smeared frames (inlier < 0.15) are not measured.
- The CA estimate (R vs B affine registration) is reliable on clean frames (0-15 px); on smeared or flash frames it
  overshoots (values > 100 px are artefacts): read the smear-frame CA as "large, 20-60 px" from the strips.
- Ref a f527-789 is a replay; the a hold statistics count frames up to f526 only where noted.
