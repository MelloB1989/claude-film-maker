// thread → ex (cut 1, spec §4 01–02): the freed fibres catch the light and match-cut into float numerals, on the beat.
// A luma match: ex shows through the cold open's brightest points first, its first numerals seeded on the fibres'
// tracked screen points (scenes/ex.ts: the seeds, from B01's fibre_* track), so the same bright points change material.
// The cold open is a plate: it holds its last frame past the cut; ex holds its first until it.
import type { TransitionSpec } from '../engine/transition';

export default {
  from: 'thread', to: 'ex', kind: 'match', pre: 0.1, post: 0.1,
  // a soft key: the fibres' fuzz hands over gradually, not as a hard matte
  soft: 0.16,
} satisfies TransitionSpec;
