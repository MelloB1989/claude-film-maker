// diff → cite (cut 6 of 14): a zoom-through. diff's romance dives into the ember of the struck line (diff.ts aimDive),
// and the cut pushes on through that same point, so the camera's drive and the zoom are one move: the old line's light
// fills the lens, and cite's chat emerges from it at 1.6×, settling. The centre is where the dive holds the ember in the
// frame (diff.ts emberAim), never a copied number. The push starts after "diff." (her onset) and the window ends a frame
// before "Ask".
import type { TransitionSpec } from '../engine/transition';
import { emberAim } from '../scenes/diff';

const { screen } = emberAim();

export default {
  from: 'diff', to: 'cite', kind: 'zoom', pre: 0.2, post: 0.15,
  center: screen, scale: 4, bFrom: 1.6,
} satisfies TransitionSpec;
