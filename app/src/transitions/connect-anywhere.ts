// connect → anywhere (cut 13 of 14): a whip with the carousel's turn. The cards have landed one a beat; on the last
// beat's offbeat the ring starts round once more (connect-time.ts EXIT), accelerating through the cut, and the camera
// whips right with it: the Rust card swings away to the left, and the face that comes round from the right is
// anywhere's terminal on the open book, landing where connect's face stood, centred on it and as wide, still turning in
// and braking onto its page (anywhere.ts arrivalKeys). The turn's way is the whip's: the ring's turn increases, its
// faces travel left, the camera right (group-d.test.ts). connect runs on into its handle through the window; `pre` is
// 0.1 s, so the cards keep their read.
import type { TransitionSpec } from '../engine/transition';
import { EXIT } from '../scenes/connect-time';

export default {
  from: 'connect', to: 'anywhere', kind: 'whip', pre: EXIT.lead, post: EXIT.tail, dir: [1, 0], fromMode: 'run',
} satisfies TransitionSpec;
