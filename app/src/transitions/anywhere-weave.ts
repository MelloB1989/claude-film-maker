// anywhere → weave (cut 14 of 14, the last cut: into the woven mark). A zoom-through. The namespaces' field has
// receded into the dark, 2,048 boundaries; over anywhere's last 0.2 s the camera stops pulling back and plunges into
// the dark crossing between four tiles (anywhere.ts DIVE, diveCamera), faster and faster, the tiles rushing past, and
// the cut pushes on through that same point: the dark between the boundaries fills the lens, and weave's threads arc
// out of it, B15 emerging from 1.6× about the very point where its mark weaves itself (the track's `mark_c` on its
// first frame). The centre is that point, never a copied number; the dive holds its crossing there every frame. B15
// holds its first frame through the window (a plate scene). The window ends more than a frame before "GitLoom.".
import type { TransitionSpec } from '../engine/transition';
import type { VO } from '../engine/vo';
import { DIVE, diveAim } from '../scenes/anywhere';

export default (vo: VO): TransitionSpec => {
  const cut = vo.scenes.find((s) => s.id === 'anywhere')!.end;
  return {
    from: 'anywhere', to: 'weave', kind: 'zoom', pre: DIVE.lead, post: 0.25,
    center: diveAim(cut), scale: 5, bFrom: 1.6,
  };
};
