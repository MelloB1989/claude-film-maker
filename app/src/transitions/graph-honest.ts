// graph → honest (cut 10 of 14): a dip to ink, the film's breath in. The light drains out of the constellation
// before the music goes; honest then cuts in hard on its own ink (post 0: nothing of graph ever shares a frame with it).
import type { TransitionSpec } from '../engine/transition';

export default { from: 'graph', to: 'honest', kind: 'dip', pre: 0.3, post: 0, ease: 'inOutCubic' } satisfies TransitionSpec;
