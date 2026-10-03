// loom → diff (cut 5 of 14): a whip, the camera travelling right. loom's tour snaps between its tiers like whips, the
// camera always travelling right along the fell (the lanes run out to the left of frame: loom-time.ts lastSnapDir); the
// last snap carries on through the cut into diff's editor, which lands still travelling and brakes onto its first
// framing (diff.ts ARRIVE). loom's plate holds its last frame. `post` is tight: "Change" starts 0.163 s after the cut, so
// the window ends more than a frame before it (group-b.test.ts).
import type { TransitionSpec } from '../engine/transition';

export default { from: 'loom', to: 'diff', kind: 'whip', pre: 0.1, post: 0.1, dir: [1, 0] } satisfies TransitionSpec;
