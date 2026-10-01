// The clock of scene 11 `honest`: every moment it keys on, from the data (her measured onsets, the score's beats and
// downbeats). Nothing here is a hard-coded second.
//
// "And when I don't know... ...I say so." The music is out for the whole beat (the score's `honest` section starts on
// the downbeat after "And"); the picture holds its breath with it.
// - The cut: near-black, and the question types in, whole just before "And".
// - "And when": the evidence floor draws across the dark and the three arms reach up out of it, one after another.
// - "I don't": they search under the floor; on the downbeat where the music drops out they press up to it, and nothing
//   clears it. "know…": they hang there, stilling.
// - The silence: from the beat after "know…" they go slack one by one and fall, in slow motion, out of the frame,
//   which is clear by the beat before "…I".
// - "…I": the response card; "say", on its downbeat: I don't know., quiet and centred; the footnote under the card.
import type { AudioData } from '../engine/audio';
import { wordTimes } from '../engine/motion';
import { norm, type VO, type Word } from '../engine/vo';

/** The arms, in the order she gave them in `braid`; they go slack in the order RELEASE_ORDER gives (an index each). */
export const ARMS = ['lexical', 'body', 'cues'] as const;
export type Arm = (typeof ARMS)[number];
/** Who lets go first (the middle arm, then the left, then the right) and how far apart (s). */
export const RELEASE_ORDER: Record<Arm, number> = { body: 0, lexical: 1, cues: 2 };
export const RELEASE_GAP = 0.11;
/** How long each arm takes to reach up under the floor (s), and how far apart they set out. */
export const RISE_S = 0.36;
export const RISE_GAP = 0.06;

export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'honest').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`honest: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm;
  const and = word('and'), when = word('when'), dont = word('dont'), know = word('know');
  const i2 = word('i', 1), say = word('say'), so = word('so');
  const after = (t: number, grid: number[], what: string) => {
    const b = grid.find((x) => x > t + 1e-6);
    if (b === undefined || b >= end) throw new Error(`honest: no ${what} after ${t} in the window`);
    return b;
  };
  // the question types in from the cut and is whole just before "And"
  const ask = start + 0.07;
  const asked = and.start - 0.06;
  // the music drops out on the downbeat after "And": the arms press up to the floor on it
  const hush = after(and.start, audio.downbeats, 'downbeat');
  if (!(hush < know.start)) throw new Error('honest: the music must drop out before "know"');
  // they set out as the question is sent, a little apart, and are up under the floor by "I"
  const reach = and.start - 0.04;
  // the silence: the first arm lets go on the beat after "know…" ends; the frame is clear by the beat before "…I"
  const release = after(know.end - 0.03, audio.beats, 'beat');
  const clear = [...audio.beats].reverse().find((b) => b < i2.start - 0.15);
  if (clear === undefined || !(clear > release + 0.8)) throw new Error('honest: no room for the fall between "know" and "…I"');
  // "…I": the response card; "say" (on its downbeat if it has one): I don't know.
  const say0 = audio.downbeats.find((d) => Math.abs(d - say.start) < 0.08) ?? say.start;
  return {
    start, end, beat,
    ask, asked,
    /** The floor draws across as she says "And", whole by "when". */
    floor: { at: and.start - 0.1, end: when.start + 0.06 },
    reach,
    /** When arm `a` sets out from its root. */
    rise: (a: Arm) => reach + ARMS.indexOf(a) * RISE_GAP,
    when: when.start,
    dont: dont.start,
    hush,
    know: know.start,
    knowEnd: know.end,
    release,
    /** When arm `a` goes slack. */
    slack: (a: Arm) => release + RELEASE_ORDER[a] * RELEASE_GAP,
    /** The last arm is out of the frame. */
    clear,
    /** The response card comes up with her "…I", and its rows stream in. */
    respond: i2.start - 0.02,
    /** "say": I don't know. */
    say: say0,
    so: so.start,
    soEnd: so.end,
    /** The footnote types in under the card. */
    note: i2.start + 0.22,
  };
}
export type Times = ReturnType<typeof timesOf>;
