// cite → braid (cut 7 of 14): a whip along the thread. The seam cite lays runs down the file's margin beside lines
// 11–14; the camera whips out along that run (cite.ts seamAxis, the seam projected through the camera's last stop), into
// braid's void, where the three arms race in. braid's plate holds its first frame until the cut. `pre` is 0.1 s: the
// settled chain holds for only 0.2 s before it.
import type { TransitionSpec } from '../engine/transition';
import { seamAxis } from '../scenes/cite';

export default { from: 'cite', to: 'braid', kind: 'whip', pre: 0.1, post: 0.15, dir: seamAxis() } satisfies TransitionSpec;
