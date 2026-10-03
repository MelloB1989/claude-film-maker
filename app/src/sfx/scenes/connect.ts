// 13 `connect`: "One command… and I'm in Claude Code. Or any agent, in any language." The command types in from "One"
// and is entered on the downbeat in her pause; `claude mcp list` types in and is entered as she says "I'm"; the ✔'s pen
// lands on "in" with the Connected chime; then the carousel turns a face a beat, each card flipping in on its beat with
// a soft flap and a breath of air.
import { typedCount } from '../../engine/panels';
import { cue, event, onBeat, onDownbeat, typing, type Cue, type SceneCues } from '../cue';
import { FLIP, timesOf } from '../../scenes/connect-time';
import { ROW, copyOf, terminalLines } from '../../scenes/connect-cards';
import S from '../../scenes/connect.strings.json';

const connect: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const lines = terminalLines(copyOf(S as string[]), T);
  const out: Cue[] = [];
  ROW.cmd.forEach((r) => {
    const l = lines[r]!;
    out.push(...typing(`connect:cmd${r}`, (t) => typedCount(l, t), l.at!, T.type.end, `connect.cmd${r}`));
  });
  out.push(cue('key_enter', onDownbeat(c, T.enter)));
  const list = lines[ROW.list]!;
  out.push(...typing('connect:list', (t) => typedCount(list, t), T.list.at, T.list.end, 'connect.list'));
  out.push(cue('key_enter', event(c, 'list-out', T.out), { gain: -3 }));
  // the ✔: its pen stroke lands on the beat on "in"
  out.push(cue('connected_chime', event(c, 'tick', T.tick)));
  // the carousel: a face a beat, each card landing face up on its beat; the air of its flip is fastest edge-on, half way
  T.cards.forEach((t, i) => {
    const b = onBeat(c, t), pan = i % 2 === 0 ? 0.2 : -0.2;
    out.push(cue('whoosh_whip', event(c, `flip${i}`, t - FLIP.dur / 2), { gain: -8, pan: -pan }));
    out.push(cue('card_flip', b, { gain: -2, pan }));
  });
  return out;
};
export default connect;
