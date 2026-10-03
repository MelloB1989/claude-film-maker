// 10 `graph`: "I connect the dots… and I learn your language." The link lifts off the page on the downbeat and zips out
// into the dark; maya.md throws its thread short; on the beat after "dots…" the trip's bead drops in with a clink and the
// edge heals with a shimmer; the vocabulary command types in with her and is entered on the downbeat, its answer popping
// in; k8s lifts off the answer as a thread and zips up into the graph.
import { typedCount } from '../../engine/panels';
import { cue, event, onBeat, onDownbeat, typing, type Cue, type SceneCues } from '../cue';
import { timesOf } from '../../scenes/graph-time';
import { vocabLine } from '../../scenes/graph';

const graph: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const cmd = vocabLine(T);
  const out: Cue[] = [];
  out.push(cue('edge_zip', event(c, 'lift', T.lift), { pan: 0.2 }));
  // the dangling link, thrown out from maya.md as the camera opens out
  out.push(cue('edge_zip', event(c, 'dangle', T.thrown.at), { gain: -6, pan: -0.2 }));
  const heal = onBeat(c, T.heal);
  out.push(cue('glass_clink', heal));
  out.push(cue('heal_shimmer', heal, { gain: -2 }));
  out.push(...typing('graph:vocab', (t) => typedCount(cmd, t), T.type.at, T.type.end, 'graph.vocab'));
  const answer = onDownbeat(c, T.answer);
  out.push(cue('key_enter', answer));
  out.push(cue('insert_pop_1', answer, { gain: -3 }));
  out.push(cue('edge_zip', event(c, 'seek', T.seek), { gain: -3 }));
  return out;
};
export default graph;
