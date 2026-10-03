// braid → merkle (cut 8 of 14): a whip, the camera tilting up. The rope pulls toward camera; the whip tilts up out of it
// into merkle's vault (merkle opens low, looking up at the tree). braid's plate holds its last frame. `pre` is 0.1 s: the
// result card is on screen for only 0.6 s before the cut.
import type { TransitionSpec } from '../engine/transition';

export default { from: 'braid', to: 'merkle', kind: 'whip', pre: 0.1, post: 0.15, dir: [0, -1] } satisfies TransitionSpec;
