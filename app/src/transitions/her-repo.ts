// her → repo (cut 3, spec §4 03–04): a whip, the camera tilting up. The headline, drifting back out of focus, whips
// down out of frame; repo's tilted terminal lands from above. The whip runs a few degrees off the vertical, down and to
// the right, along the terminal's leaning left edge as it lands (repo's opening key: rolled, seen from up and left), so
// the panel's tilt carries the whip's line on. Both sides hold: the streak is the motion.
import type { TransitionSpec } from '../engine/transition';

/** The lean of the terminal's left edge in repo's first frame (rad off the vertical, its foot to the right). */
const LEAN = 0.085;

export default {
  from: 'her', to: 'repo', kind: 'whip', pre: 0.1, post: 0.1,
  // the camera travels up (and a hair left): the picture goes down and right
  dir: [-Math.sin(LEAN), -Math.cos(LEAN)],
} satisfies TransitionSpec;
