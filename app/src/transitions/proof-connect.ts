// proof → connect (cut 12 of 14): a whip, the camera travelling right. The Act IV lift. On proof's last downbeat a band
// of light starts across 91.4% and accelerates all the way to the cut (proof.ts light): it leads, racing off the % to
// the right, and the camera goes after it, first swinging right in perspective (proof.ts EXIT) and then whipping. connect
// lands still swinging and brakes onto its waiting prompt, its blood light breathing (connect.ts ARRIVE). Both sides
// run their own motion inside their windows (no handles needed). The window ends 0.48 s before "One".
import type { TransitionSpec } from '../engine/transition';
import { EXIT } from '../scenes/proof';

export default { from: 'proof', to: 'connect', kind: 'whip', pre: EXIT.lead, post: 0.12, dir: [1, 0] } satisfies TransitionSpec;
