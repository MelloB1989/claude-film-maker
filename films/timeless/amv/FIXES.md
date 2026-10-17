# Changes to the handover plan

`plan.json` here is the handover's `project/scripts/plan.json` with paths remapped, plus these deliberate fixes. Each
was found by watching the previs; the AE reference render only covers f0-599.

| frames | shot | fix | why |
|---|---|---|---|
| 624-657 | M08_shuriken | gold TIMELESS layer pos 980,560 -> 800,500, size 230 -> 210 | The shot opens pushed in 330 % with the layer centre at x 1949, so at 980,560 the title started fully off the right edge and was only whole from about f645: 0.4 s of a 1.1 s title. At 800,500 its centre stays within 200 px of the frame centre from f628 on, and it pulls back into frame with the camera. |
| 624-657 | M08_shuriken | (review of draft 1) gold TIMELESS moved out of the shot into the screen titles (`titles[-1]`, id `screen.4`), pos 960,730, size 240 | As a layer title it rides M08's 330 % push-in, so at any layer position it is clipped by the frame edge for its first ~8 frames (reviewer: 'TIMELES' cut at the right edge f625-631) and later sat across Tom's eyes. In screen space it is whole for its full 34 frames, in the lower third under the eyes and above the watermark. |
| 649, 769 | M08, M15 | black strobes 647 -> 649 and 771 -> 769 | Audio audit (tools/filmtools/amv/audit_audio.py): the nearest music beats are at 648.8 and 769.0; the strobes sat 1.8 and 2.0 frames off them. |
| 59, 84, 795 | T03, M16 | new `polish.hits` (chromatic hits, strength 0.6/0.6/0.8) | Audio audit: big music hits with no picture event. |
| 336-339 | A03_sunset_mask | `rfb_len` 0.2, `rfb_beta` 48 | Brightest radial blur fitted against the AE render (luma through grade v3). AE's sky blows to white at the cut; a longer, harder blur brings it up without the wedge artefacts of a very long ray. Luma gap ours - AE over f336-339: -15.4 (-20/-17/-16/-8) -> -2.2 (-8/-7/-6/+8). |
| 589-592 | M06_flying_kick | `rfb_len` 0.2, `rfb_beta` 48 | AE's bright dust specks streak outward from the off-centre blur; a harder select keeps them bright. f589-592: -13.5 (-18/-14/-11/-11) -> -6.3 (-12/-6/-4/-3). |
| 571-572 | M04_dome_crash | `rfb_len` 0.1, `rfb_beta` 48 | Ramp-up of the radial blur: -1.5 (-1/-2) -> 0.0 (+1/-1). Two frames, light fit. |
| 334-335 | A02_freefall | `rfb_beta` 24 | +6 (+3/+9) -> +2.5 (+1/+4). Two frames, light fit. |
| all rfb | all shots | global radial blur: 'Brightest' now a luma softmax over the ray samples (`layerfx.RFB_SELECT = "soft"`, beta 12) with ray length 0.07 (was 0.12, per-channel max) | The per-channel max mixed a red tap with a blue tap into magenta at every web line, and the hard pick gave cells. 78 shot-start frames with a keyed rfb, f0-599: mean luma gap +5.9 -> +1.8 (before the per-shot rows), sharpness ratio ours/AE 0.85 -> 0.87. M05 f573-574 +19/+14 -> +7/+2, T03 f100-101 +21/+29 -> +7/+6, T07 f203-204 +8/+7 -> 0/+1 with no per-shot field. |
