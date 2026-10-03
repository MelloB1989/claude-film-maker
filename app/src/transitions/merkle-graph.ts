// merkle → graph (cut 9 of 14): a zoom-through, file to file. merkle lands low beside its file, the one lit file in its
// rosette, and after "fifty." the camera drives at it along its line of sight (merkle-camera.ts diveAt), so the file
// holds its place while the vault streams out past the lens; the zoom-through pushes on through that same point, and
// graph's file emerges from it, its link `[[facts/orgs/acme.md]]` opening on the spot where merkle's file was (graph.ts
// pinLink). The centre is the file where merkle's landed camera sees it (landingAim), never a copied number. "fifty."
// ends 32 ms before the cut; the window ends well before "I".
import type { TransitionSpec } from '../engine/transition';
import { landingAim } from '../scenes/merkle-camera';

const { screen } = landingAim();

export default {
  from: 'merkle', to: 'graph', kind: 'zoom', pre: 0.15, post: 0.2,
  center: screen, scale: 4, bFrom: 1.6,
} satisfies TransitionSpec;
