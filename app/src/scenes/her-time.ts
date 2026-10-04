// The clock of scene 03 `her`: every time it keys on, from the voiceover's onsets and the score's grid, and the pure
// rules of its headline (the strike, the + lines' flat words typing in, the blame gutter). her.ts draws from it and the
// cue sheet (sfx/scenes/her.ts) places its sounds from it.
import type { AudioData } from '../engine/audio';
import { wordTimes } from '../engine/motion';
import { norm, type VO } from '../engine/vo';
import { reformCues } from './her-reform';
import S from './her.strings.json';

/** Every time the scene keys on, from the voiceover's onsets and the score's grid. */
export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'her');
  const find = (w: string, nth = 0) => {
    const h = ws.filter((x) => norm(x.w.w) === w)[nth];
    if (!h) throw new Error(`her: no spoken "${w}" (#${nth})`);
    return h.at;
  };
  const not = find('not'), me = find('me');
  const down = audio.downbeats.find((d) => d > me);
  if (down === undefined) throw new Error('her: no downbeat after "me."');
  const beatAfterDown = audio.beats.find((b) => b > down + 0.05) ?? down + 60 / audio.bpm;
  const a1 = find('a', 0), a2 = find('a', 1);
  // "has" is never spoken: it types in just before her "a", or on a downbeat that falls in the pause before it (the
  // downbeat is an event)
  const hasBefore = (after: number, a: number) => audio.downbeats.find((d) => d > after + 0.2 && d < a - 0.12) ?? a - 0.13;
  const memory = find('memory'), fact = find('fact');
  return {
    start, end, not, me, down, beatAfterDown, hand: reformCues(start, not, me, down).hand,
    every1: find('every', 0), memory, has1: hasBefore(memory, a1), a1, commit: find('commit'),
    every2: find('every', 1), fact, has2: hasBefore(fact, a2), a2, blame: find('blame'),
  };
}
export type Times = ReturnType<typeof timesOf>;

/** The strike through the − line, from the cut's beat (s after it): it runs out-cubic over [at, end]. */
export const STRIKE = { at: 0.03, end: 0.26 } as const;
/** The blame gutter's slide in, from "blame" (s after it): out-expo over [at, end]. */
export const BLAME_GUTTER = { at: 0.02, end: 0.45 } as const;

/** The + lines' words, each line's words in order (their gutter mark aside): the hero words are 1 and 4. */
export const PLUS_WORDS = [S[2]!, S[3]!].map((s) => s.slice(s.indexOf(' ') + 1).split(' '));
export const HEROES: readonly number[] = [1, 4];

/** Each + line's word times, word by word ("has" is never spoken: hasBefore). */
export const plusTimes = (T: Times): number[][] => [
  [T.every1, T.memory, T.has1, T.a1, T.commit],
  [T.every2, T.fact, T.has2, T.a2, T.blame],
];

/** How many of a flat word's n letters show at t: one a frame from `at` (letter k from at + k/30). */
export function flatShown(t: number, at: number, n: number): number {
  let k = 0;
  while (k < n && t >= at + k / 30) k++;
  return k;
}
