// 14 `anywhere`: "On your machine… or in my cloud. One memory for every user you have." The install line types in with
// her and is entered a sixteenth before the chips, which pop out of the machine on sixteenths; the camera pulls back on
// the split's downbeat; on "One" the first namespace tile lands with a clink; then the namespaces double on the
// sixteenths, eleven ticks to 2,048.
import { typedCount } from '../../engine/panels';
import { cue, event, onDownbeat, slice, typing, word, type Cue, type SceneCues } from '../cue';
import { timesOf } from '../../scenes/anywhere-time';
import { terminalSpec } from '../../scenes/anywhere';

const anywhere: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const install = terminalSpec(T).lines[0]!;
  const out: Cue[] = [];
  out.push(...typing('anywhere:install', (t) => typedCount(install, t), T.type.at, T.type.end, 'anywhere.install'));
  out.push(cue('key_enter', event(c, 'enter', T.enter), { gain: -2 }));
  T.chips.forEach((t, i) => out.push(cue(`insert_pop_${i + 1}`, event(c, `chip${i}`, t), { gain: -2, pan: -0.2 + 0.2 * i })));
  out.push(cue('whoosh_whip', onDownbeat(c, T.split), { gain: -4 }));
  out.push(cue('glass_clink', word(c, 'L29', 'one'), { gain: -2 }));
  T.doublings.forEach((t, k) => out.push(cue(slice('visited_tick', 8, k, 11), event(c, `double${k}`, t), { gain: -6 + 0.4 * k, pan: (k % 2 === 0 ? 1 : -1) * 0.1 })));
  return out;
};
export default anywhere;
