// 09 `merkle`: "Fifty things changed? I only look at fifty." The walk goes down the lit paths a level a word, a tick as
// it reaches each; the skipped subtrees fold shut beside it with small clicks (a sound a frame at most), and the first
// seals with its stamp; the crane plunges on "look at"; the 50 slams into its blank on "fifty.".
import { cue, event, slice, word, type Cue, type SceneCues } from '../cue';
import { FOLD_S, PLUNGE, STAMP_AT, nodeTimes, timesOf } from '../../scenes/merkle-time';
import { N, SEED, buildTree, pickChanged } from '../../scenes/merkle-tree';

const TICKS = 8;
/** The walk's words (merkle-time.ts: the root on "I", then a level a word), down to the last directories. */
const WALK = ['I', 'only', 'look', 'at'];

const merkle: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const tree = buildTree(pickChanged(SEED));
  const nt = nodeTimes(tree, T);
  const out: Cue[] = [];
  // the walk's visits tick, a level a word, the root on "I" to the last directories on "at" (the files, on "fifty.", are
  // the 50's slam); the skipped subtrees fold shut between them, each as the walk reaches its parent, the siblings a few
  // frames apart. One sound a frame at most: the visit's tick, else the frame's first fold
  const taken = new Set<number>();
  const ticks = WALK.map((w, k) => {
    const at = word(c, 'L20', w);
    taken.add(Math.round((at.t - s.start) * 30));
    return cue(slice('visited_tick', TICKS, k, 5), at, { gain: -2, pan: [-0.15, -0.05, 0.05, 0.15][k] });
  });
  const folds = new Map<number, number>();
  let first = Infinity;
  for (let id = 0; id < N; id++) {
    const f = nt.fold[id]!;
    if (tree.fold[id] !== id || f >= 1e5) continue;
    const t = s.start + f, fr = Math.round(f * 30);
    first = Math.min(first, t);
    if (taken.has(fr)) continue;
    if (!(folds.get(fr)! <= t)) folds.set(fr, t);
  }
  const fl = [...folds.values()].sort((a, b) => a - b);
  out.push(...ticks);
  fl.forEach((t, i) => out.push(cue('fold_click', event(c, `fold${i}`, t), { gain: -6, pan: (i % 2 === 0 ? 1 : -1) * 0.2 })));
  // the first `= hash · skipped` seals with its stamp
  out.push(cue('stamp', event(c, 'first-stamp', first + FOLD_S * STAMP_AT), { gain: -2 }));
  // the plunge onto the fifty: fastest on its last run, at full speed
  out.push(cue('whoosh_zoom', event(c, 'plunge', T.walk[3]! + (PLUNGE.from + PLUNGE.to) / 2), { gain: -4 }));
  out.push(cue('type_slam', word(c, 'L20', 'fifty', 1)));
  return out;
};
export default merkle;
