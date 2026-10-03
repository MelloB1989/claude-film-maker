// 04 `repo`: "I'm just a git repo." `cd ~/memory && ls` types in with her and is entered; the listing pops out as four
// chips, a 32nd apart; `git log --oneline` types in the pause and is entered as the camera dives; the commits land as
// glass beads, one a beat, each a thock with its bloom's clink; the file swings in on its hinge.
import { typedCount } from '../../engine/panels';
import { cue, event, onBeat, typing, type Cue, type SceneCues } from '../cue';
import { terminalLines, timesOf } from '../../scenes/repo-time';

const repo: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const lines = terminalLines(T), cd = lines[0]!, cdOut = lines[1]!, log = lines[2]!, logOut = lines[3]!;
  const out: Cue[] = [];
  out.push(...typing('repo:cd', (t) => typedCount(cd, t), T.cd.at, T.cd.end, 'repo.cd'));
  out.push(cue('key_enter', event(c, 'ls', cdOut.at!)));
  T.chips.forEach((t, i) => out.push(cue(`insert_pop_${i + 1}`, event(c, `chip${i}`, t), { gain: -1, pan: -0.24 + 0.16 * i })));
  out.push(...typing('repo:log', (t) => typedCount(log, t), T.log.at, T.log.end, 'repo.log'));
  out.push(cue('key_enter', event(c, 'enter', logOut.at!)));
  // the commits, one a beat: each lands with a thock and blooms with a glassy clink under it
  T.beads.forEach((t) => {
    const b = onBeat(c, t);
    out.push(cue('commit_thock', b));
    out.push(cue('glass_clink', b, { gain: -6 }));
  });
  out.push(cue('card_flip', event(c, 'file', T.fileLand), { gain: -2 }));
  return out;
};
export default repo;
