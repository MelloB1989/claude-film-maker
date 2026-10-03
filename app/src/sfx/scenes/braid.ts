// 08 `braid`: "Your words. What you meant. How you'd ask… braided into one answer." The query types in at the top
// right as the scene opens; each arm zips in as she names it; on "braided" the rope creaks as the plait is pulled; on
// "one" its head lands on the card's hinge with a thock.
import { cue, event, typing, word, type Cue, type SceneCues } from '../cue';
import { ARMS, QUERY_TYPE, braidTimes, landOf, queryShown } from '../../scenes/braid-time';
import S from '../../scenes/braid.strings.json';

const QUERY = (S as string[])[0]!;

const braid: SceneCues = (c) => {
  const s = c.scene, T = braidTimes(c.vo, c.audio, s.start, s.end);
  const out: Cue[] = [];
  const n = Array.from(QUERY).length, at = s.start + QUERY_TYPE.lead;
  out.push(...typing('braid:query', (t) => queryShown(t, at, n), at, at + n / QUERY_TYPE.cps, 'braid.query'));
  // each arm lands on the first word of its phrase (B08's flight)
  ARMS.forEach((a, i) => out.push(cue('edge_zip', event(c, `arm-${a}`, landOf(T, a)), { pan: [-0.35, 0, 0.35][i]! })));
  // the plait is pulled from just before "braided" (B08's zip)
  out.push(cue('rope_creak', event(c, 'zip', T.zip)));
  // "one": the head lands on the hinge, the card swinging open on it
  out.push(cue('commit_thock', word(c, 'L19', 'one')));
  return out;
};
export default braid;
