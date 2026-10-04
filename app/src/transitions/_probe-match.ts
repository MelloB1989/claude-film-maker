// Dev probe (not in the film: timeline.ts skips _*.ts): a luma match cut from cite to braid (B through A's highlights).
import type { TransitionSpec } from '../engine/transition';

export default { from: 'cite', to: 'braid', kind: 'match', pre: 0.1, post: 0.15 } satisfies TransitionSpec;
