# Changes to the handover plan

`plan.json` here is the handover's `project/scripts/plan.json` with paths remapped, plus these deliberate fixes. Each
was found by watching the previs; the AE reference render only covers f0-599.

| frames | shot | fix | why |
|---|---|---|---|
| 624-657 | M08_shuriken | gold TIMELESS layer pos 980,560 -> 800,500, size 230 -> 210 | The shot opens pushed in 330 % with the layer centre at x 1949, so at 980,560 the title started fully off the right edge and was only whole from about f645: 0.4 s of a 1.1 s title. At 800,500 its centre stays within 200 px of the frame centre from f628 on, and it pulls back into frame with the camera. |
| 624-657 | M08_shuriken | (review of draft 1) gold TIMELESS moved out of the shot into the screen titles (`titles[-1]`, id `screen.4`), pos 960,730, size 240 | As a layer title it rides M08's 330 % push-in, so at any layer position it is clipped by the frame edge for its first ~8 frames (reviewer: 'TIMELES' cut at the right edge f625-631) and later sat across Tom's eyes. In screen space it is whole for its full 34 frames, in the lower third under the eyes and above the watermark. |
| 649, 769 | M08, M15 | black strobes 647 -> 649 and 771 -> 769 | Audio audit (tools/filmtools/amv/audit_audio.py): the nearest music beats are at 648.8 and 769.0; the strobes sat 1.8 and 2.0 frames off them. |
| 59, 84, 795 | T03, M16 | new `polish.hits` (chromatic hits, strength 0.6/0.6/0.8) | Audio audit: big music hits with no picture event. |
