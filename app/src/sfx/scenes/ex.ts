// 02 `ex`: the vector store. A cold digital shimmer hangs over the cloud until it collapses; the overwrite split-flaps
// on its beats; the ghost query pings and nothing answers; why? pings back only a score; the three blood tags stamp on
// their beats; the cloud falls into the terminal, its fatal line flapping down onto the downbeat with a dull thunk.
// (`$ git log` is never typed on screen: the terminal comes up with it already there, so it takes no keys.)
import { cue, event, onBeat, onDownbeat, slice, type Cue, type SceneCues } from '../cue';
import { FLAP, PING, fatalFlap, timesOf } from '../../scenes/ex-time';
import S from '../../scenes/ex.strings.json';

const FATAL = (S as string[])[13]!;
/** The overwrite's flaps: a digit turns two to five, so the deepest flip lands this many flaps before its beat. */
const OVERWRITE_FLAPS = 5;
const FLAPS = 6;

const ex: SceneCues = (c) => {
  const s = c.scene, T = timesOf(c.vo, c.audio, s.start, s.end);
  const out: Cue[] = [];
  // the cloud's shimmer: from the cut (the seeds glide into it) to the collapse
  out.push(cue('float_shimmer', event(c, 'start', s.start), { dur: T.drop - s.start }));
  // the overwrite: the region's flaps land on the beats, the row on "knew" (wave1), the rows round it on the next; every
  // cell flips on the same FLAP grid, so a flip lands j flaps before its beat (fewer cells the further back)
  for (const [k, land] of [T.wave1, T.wave2].entries()) {
    const b = onBeat(c, land);
    for (let j = OVERWRITE_FLAPS - 1; j >= 0; j--) {
      out.push(cue(slice('flap', FLAPS, k, j, 3), { t: land - j * FLAP, anchor: `${b.anchor}-${j}flap` }, { gain: -2 * j, pan: -0.2 }));
    }
  }
  // berlin? pings the cloud; nothing comes back
  out.push(cue('cosine_ping', event(c, 'query-ping', T.query + PING.query), { gain: -9, pan: 0.15 }));
  // the three tags stamp on successive beats
  T.stamps.forEach((t, i) => out.push(cue('stamp', onBeat(c, t), { gain: i === 0 ? 0 : -1, pan: -0.3 })));
  // why? pings, and gets a score back
  out.push(cue('cosine_ping', event(c, 'why-ping', T.why + PING.why), { pan: 0.2 }));
  // the fatal line's cells flap down onto the resolve's downbeat (each its own speed, all landing together): one flap a
  // frame at most, from the first to land
  const flips = new Map<number, number>();
  Array.from(FATAL).forEach((_, i) => {
    const { step, steps } = fatalFlap(i);
    for (let j = 1; j < steps; j++) {
      const t = T.resolve - j * step, f = Math.round(t * 30);
      if (!(flips.get(f)! <= t)) flips.set(f, t);
    }
  });
  const down = onDownbeat(c, T.resolve);
  [...flips.entries()].sort((a, b) => a[1] - b[1]).forEach(([f, t], k) => {
    out.push(cue(slice('flap', FLAPS, f - Math.round(T.resolve * 30), 7), { t, anchor: `${down.anchor}-flap${k}` }, { gain: -6 }));
  });
  out.push(cue('fatal_thunk', down));
  return out;
};
export default ex;
