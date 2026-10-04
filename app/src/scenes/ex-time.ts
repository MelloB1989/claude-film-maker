// The clock of scene 02 `ex`: every time it keys on, from her onsets and the score's grid, and the split-flap rules its
// numerals flip by. Pure: ex.ts draws from it and the cue sheet (sfx/scenes/ex.ts) places its sounds from it.
import type { AudioData } from '../engine/audio';
import { wordTimes } from '../engine/motion';
import { hash } from '../engine/util';
import { norm, type VO, type Word } from '../engine/vo';

/** Every time the scene keys on, from her onsets and the score's grid (song seconds). */
export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'ex').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`ex: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm;
  const beatAfter = (t: number) => audio.beats.find((b) => b > t + 1e-6) ?? t + beat;
  const downAfter = (t: number) => audio.downbeats.find((b) => b > t + 1e-6) ?? t + 4 * beat;
  const store = word('store'), overwrites = word('overwrites'), knew = word('knew'), why = word('why');
  const commitment = word('commitment');
  // the drop is on the beat she says "Commitment" on (or the next one)
  const drop = audio.beats.find((b) => b >= commitment.start - 0.08) ?? commitment.start;
  const berlin = downAfter(store.end);
  const wave1 = beatAfter(overwrites.start + 0.55);
  const stamp0 = downAfter(knew.end);
  const stamps = [stamp0, beatAfter(stamp0), beatAfter(beatAfter(stamp0))];
  if (!(stamps[2]! < drop)) throw new Error('ex: the stamps must land before the drop');
  const resolve = downAfter(drop);
  return {
    start, end,
    its: word('its', 0).start, not: word('not').start, you: word('you', 0).start,
    its2: word('its', 1).start, your: word('your').start, vector: word('vector').start, store: store.start,
    /** The cloud is revealed and a band of light sweeps it, on the first downbeat. */
    reveal: downAfter(start + 0.2),
    /** The type clears as the camera pushes in; the Berlin card flies in and lands on the downbeat ("It"). */
    typeOut: store.end + 0.05, berlin,
    /** Its letters melt, its floats drop into their row, and the cloud takes them over. */
    berlinMorph: berlin + 0.02, berlinSettle: berlin + 0.42,
    /** Lisbon flies in during "overwrites", its letters melt and dive into the row; the flaps land on the beats. */
    lisbonIn: berlin + 0.26, lisbonMorph: wave1 - 0.48, lisbonDive: wave1 - 0.31, wave1, wave2: beatAfter(wave1),
    /** The ghost query, after the overwrite (gone before the first stamp). */
    query: beatAfter(wave1) + 0.06,
    stamps, why: why.start, drop, resolve,
    /** "commits" turns blood a beat after the fatal line. */
    punch: beatAfter(resolve),
  };
}
export type Times = ReturnType<typeof timesOf>;

/** One flap of a split-flap cell (s): the overwrite's flaps fall this far apart, the last landing on its beat. */
export const FLAP = 0.07;
/** The pings through the cloud, after their moments (s): the ghost query's, and why?'s. */
export const PING = { query: 0.12, why: 0.06 } as const;

/**
 * The fatal line's cell s: the flaps its character comes down in on the resolve's downbeat (each cell its own speed, out
 * of phase, all landing together): `steps` flaps, `step` s each.
 */
export function fatalFlap(s: number): { step: number; steps: number } {
  return { step: 0.042 + 0.03 * hash(s, 62), steps: 2 + Math.floor(hash(s, 61) * 3) };
}
