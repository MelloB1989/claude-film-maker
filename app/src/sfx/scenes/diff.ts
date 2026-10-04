// 06 `diff`: "Change your mind? I'll change mine. We'll always have the diff." The blade strikes through `Uses VS Code.`
// on "I'll" and takes the confidence with a lighter second cut; both new rows pop open and neovim types in with her; the
// camera whips down onto the dock on its downbeat; the playhead lands back on 8b21e04 and home on 3f9a1c2, each with a
// glassy clink.
import { typedCount } from '../../engine/panels';
import { cue, event, onBeat, typing, word, type Cue, type SceneCues } from '../cue';
import { DOCK_WHIP, timesOf } from '../../scenes/diff-time';
import { ROW, fileLines } from '../../scenes/diff';

const diff: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const lines = fileLines(T), neo = lines[ROW.neo]!;
  const out: Cue[] = [];
  out.push(cue('pen_strike', word(c, 'L16', "I'll")));
  out.push(cue('pen_strike', event(c, 'confidence', T.conf.at), { gain: -4, pan: -0.15 }));
  // both new rows open together on "mine."
  out.push(cue('insert_pop_2', event(c, 'rows', T.add), { gain: -2, pan: -0.1 }));
  out.push(cue('insert_pop_3', event(c, 'rows', T.add), { gain: -4, pan: 0.1 }));
  // (the file runs on the song's clock until the scrub, so its typing is the song's)
  out.push(...typing('diff:neovim', (t) => typedCount(neo, t), T.add, T.addEnd, 'diff.neovim'));
  // the whip down onto the dock: fastest half way between its keys
  out.push(cue('whoosh_whip', event(c, 'dock-whip', T.dock + (DOCK_WHIP.from + DOCK_WHIP.to) / 2), { gain: -4 }));
  // the playhead lands back on 8b21e04, and home on 3f9a1c2: each on its beat
  out.push(cue('glass_clink', onBeat(c, T.back.end), { pan: -0.2 }));
  out.push(cue('glass_clink', onBeat(c, T.fwd.end), { pan: 0.2 }));
  return out;
};
export default diff;
