// Dev probe (not in the film: timeline.ts skips _*.ts): a whip between cite and braid, camera right.
// bun scripts/render.ts stills --transition _probe-whip --frames -3,-2,-1,0,1,2 --samples auto
import type { TransitionSpec } from '../engine/transition';

export default { from: 'cite', to: 'braid', kind: 'whip', pre: 0.1, post: 0.15, dir: [1, 0] } satisfies TransitionSpec;
