// 11 `honest`: "And when I don't know… …I say so." Restraint: the music goes out on the downbeat after "And" (the
// score's `honest` section) and the room is all that is left, the room tone running on under proof's "Forty-four…"
// until the score slams back in. The only other sound is the question, typed in softly as the cut lands.
import { cue, event, typing, type Cue, type SceneCues } from '../cue';
import { questionCps, timesOf, typedShown } from '../../scenes/honest-time';
import { timesOf as proofTimes } from '../../scenes/proof-time';
import S from '../../scenes/honest.strings.json';

const QUESTION = (S as string[])[0]!;

const honest: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const out: Cue[] = [];
  const n = Array.from(QUESTION).length, cps = questionCps(T, n);
  out.push(...typing('honest:ask', (t) => typedShown(t, T.ask, cps, n), T.ask, T.asked, 'honest.ask').map((k) => ({ ...k, gain: (k.gain ?? 0) - 8 })));
  // the room: from the music going out to the score's slam in proof
  const out_ = c.audio.sections.find((x) => x.name === 'honest');
  if (!out_) throw new Error('cue: the score has no `honest` section');
  const p = c.vo.scenes.find((x) => x.id === 'proof');
  if (!p) throw new Error('cue: no scene proof for the room tone to run into');
  const slam = proofTimes(c.vo, c.audio, p.start, p.end).slam;
  out.push(cue('room_tone', { t: out_.start, anchor: `section:${out_.name}` }, { dur: slam - out_.start }));
  return out;
};
export default honest;
