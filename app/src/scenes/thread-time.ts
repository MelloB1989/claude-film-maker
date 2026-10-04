// The clock of scene 01 `thread`: every moment it keys on, from the data (her measured onsets, the score's beats). Pure:
// thread.ts draws from it and the cue sheet (sfx/scenes/thread.ts) places its sounds from it.
// - The light comes up on the first beat after the opening's half second of black (b01_thread.py Clock.light_on).
// - The plate's speed ramp (b01_thread.py Clock): 1x until "to", 0.25x at "zero", held to the cut.
// - The snap: the thread breaks on "zero" (the word's slam lands on it, through the ramp).
import type { AudioData } from '../engine/audio';
import { wordTimes } from '../engine/motion';
import { norm, type VO, type Word } from '../engine/vo';

/** The words the scene keys on. */
export const WORDS = ['your', 'agent', 'forgets', 'back', 'to', 'zero'] as const;

export function threadTimes(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'thread').map((x) => x.w);
  const find = (s: string) => {
    const w = ws.find((x) => norm(x.w) === norm(s));
    if (!w) throw new Error(`thread: no spoken word "${s}"`);
    return w;
  };
  const words = Object.fromEntries(WORDS.map((k) => [k, find(k)])) as Record<(typeof WORDS)[number], Word>;
  const { to, zero } = words;
  // the plate's speed ramp, in scene-local time
  const lt = (t: number) => t - start;
  const ramp: [number, number][] = [[lt(to.start), 1], [lt(zero.start), 0.25], [lt(end), 0.25], [lt(end), 1]];
  return {
    start, end, words, ramp,
    /** The light comes up on the first beat after the opening's half second of black. */
    lightOn: audio.beats.find((b) => b > start + 0.4) ?? start,
    /** The snap: the thread breaks (film time), on "zero". */
    snap: zero.start,
    /** The last whole frame before the snap: where the break point is read. */
    preSnap: Math.floor(zero.start * 30) / 30,
  };
}
export type ThreadTimes = ReturnType<typeof threadTimes>;
