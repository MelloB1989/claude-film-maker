# Changes to the handover plan

`plan.json` here is the handover's `project/scripts/plan.json` with paths remapped, plus these deliberate fixes. Each
was found by watching the previs; the AE reference render only covers f0-599.

| frames | shot | fix | why |
|---|---|---|---|
| 624-657 | M08_shuriken | gold TIMELESS layer pos 980,560 -> 800,500, size 230 -> 210 | The shot opens pushed in 330 % with the layer centre at x 1949, so at 980,560 the title started fully off the right edge and was only whole from about f645: 0.4 s of a 1.1 s title. At 800,500 its centre stays within 200 px of the frame centre from f628 on, and it pulls back into frame with the camera. |
| 624-657 | M08_shuriken | (review of draft 1) gold TIMELESS moved out of the shot into the screen titles (`titles[-1]`, id `screen.4`), pos 960,730, size 240 | As a layer title it rides M08's 330 % push-in, so at any layer position it is clipped by the frame edge for its first ~8 frames (reviewer: 'TIMELES' cut at the right edge f625-631) and later sat across Tom's eyes. In screen space it is whole for its full 34 frames, in the lower third under the eyes and above the watermark. |
| 649, 769 | M08, M15 | black strobes 647 -> 649 and 771 -> 769 | Audio audit (tools/filmtools/amv/audit_audio.py): the nearest music beats are at 648.8 and 769.0; the strobes sat 1.8 and 2.0 frames off them. |
| 59, 84, 795 | T03, M16 | new `polish.hits` (chromatic hits, strength 0.6/0.6/0.8) | Audio audit: big music hits with no picture event. |
| 336-339 | A03_sunset_mask | `rfb_len` 0.7 (default 0.12) | Per-shot fit of the Brightest radial blur against the AE render (luma through the grade, `bake_luma`): the AMAZING wash blows the sky to white in AE, the global ray length left it grey. Luma gap ours - AE over f336-339: -15.4 (-20/-17/-16/-8) -> -0.3 (+2/-1/-4/+2). f340 (no blur, title entering) stays -15. |
| 589-592 | M06_flying_kick | `rfb_len` 0.45 | AE's streaks reach far from the off-centre blur centre (1640, 420). Gap over f589-592: -13.5 (-18/-14/-11/-11) -> +0.2 (-2/+4/+2/-3); f593-595 still -9/-8/-8. |
| 573-576, 587-588 | M05_landing | `rfb_mix` 0.5 (default 1.0: pure max) | Our Brightest streaked brighter than AE here. Mean gap +7.9 (+19/+14/+6/0, +2/+6) -> +1.4 (+12/+6/+1/-2, -4/-5). |
| 100-101 | T03_glove_city | `rfb_len` 0.08, `rfb_mix` 0.5 | The ramp-up at the end of the shot was far too bright (night city). Gap +24.7 (+21/+29) -> +3.5 (+4/+3). 2 frames only: a light fit. |
| 203-206, 571-572 | T07_train, M04_dome_crash | none | The default (0.12, 1.0) is already the best of the grid (gap +2.4 and -1.8): nothing to fix. |
