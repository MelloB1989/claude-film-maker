// 15 `weave`: "GitLoom. I don't forget. I commit." The threads swish in from the dark in their long arcs; a riser
// carries the last pass into the lock on the downbeat (B15's lock frame), where the sub hits; at the settle the wordmark
// types itself in, `gitloom 3f9a1c2`, a key a frame.
import { cue, event, typing, type Cue, type SceneCues } from '../cue';
import { arcArrivals, lockFrameTime, timesOf, wordmarkShown } from '../../scenes/weave-time';
import S from '../../scenes/weave.strings.json';

const WORDMARK = (S as string[])[2]!;

const weave: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const out: Cue[] = [];
  arcArrivals(T).forEach((t, i) => out.push(cue('weave_swish', event(c, `arc${i}`, t), { gain: -2 - i, pan: [-0.3, 0.3, -0.15][i] ?? 0 })));
  const lock = event(c, 'lock', lockFrameTime(T));
  out.push(cue('riser', lock));
  out.push(cue('sub_impact', lock));
  const n = Array.from(WORDMARK).length;
  out.push(...typing('weave:wordmark', (t) => wordmarkShown(t, T.settle, n), T.settle, T.settle + 0.1 + n / 30, 'weave.wordmark').map((k) => ({ ...k, gain: (k.gain ?? 0) - 4 })));
  return out;
};
export default weave;
