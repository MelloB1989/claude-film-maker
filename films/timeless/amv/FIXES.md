# Changes to the handover plan

`plan.json` here is the handover's `project/scripts/plan.json` with paths remapped, plus these deliberate fixes. Each
was found by watching the previs; the AE reference render only covers f0-599.

| frames | shot | fix | why |
|---|---|---|---|
| 624-657 | M08_shuriken | gold TIMELESS layer pos 980,560 -> 800,500, size 230 -> 210 | The shot opens pushed in 330 % with the layer centre at x 1949, so at 980,560 the title started fully off the right edge and was only whole from about f645: 0.4 s of a 1.1 s title. At 800,500 its centre stays within 200 px of the frame centre from f628 on, and it pulls back into frame with the camera. |
