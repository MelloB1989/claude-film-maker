// 12 `proof`: "Forty-four… to ninety-one point four." The room tone (honest's) runs on until the score slams back in;
// from the slam the odometer's four rounds roll, each landing an eighth after its beat, 91.4 landing with a slam as she
// says "four."; the % flips up with a smirk on "bad".
import { cue, event, word, type Cue, type SceneCues } from '../cue';
import { timesOf } from '../../scenes/proof-time';

const proof: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const out: Cue[] = [];
  // each round's roll ends as it clicks home; 91.4, the last, lands with the slam. The roll's take runs about a beat and
  // a half up to its end, so the first round's would begin in the room tone before the score is back: the first round
  // rolls inside the second's take, which begins on the slam
  T.lands.forEach((t, i) => {
    const last = i === T.lands.length - 1;
    if (i > 0) out.push(cue('odometer_roll', event(c, `round${i}`, t), { gain: last ? 0 : -6 + 2 * i, pan: 0.1 }));
    if (last) out.push(cue('type_slam', event(c, 'landing', t)));
  });
  out.push(cue('card_flip', word(c, 'L25', 'bad'), { gain: -8, pan: 0.25 }));
  return out;
};
export default proof;
