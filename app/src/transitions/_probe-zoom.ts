// Dev probe (not in the film: timeline.ts skips _*.ts): a zoom-through from cite into braid, about the frame's centre.
import type { TransitionSpec } from '../engine/transition';

export default { from: 'cite', to: 'braid', kind: 'zoom', pre: 0.1, post: 0.15 } satisfies TransitionSpec;
