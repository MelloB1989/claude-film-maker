// Dev probe (not in the film: timeline.ts skips _*.ts): a crossfade from cite to braid, in linear light.
import type { TransitionSpec } from '../engine/transition';

export default { from: 'cite', to: 'braid', kind: 'xfade', pre: 0.1, post: 0.15 } satisfies TransitionSpec;
