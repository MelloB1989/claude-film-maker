// The clock of scene 15 `weave`: every time it keys on, from the voiceover's onsets and the score's grid, and B15's
// own moments (blender/mark/choreo.py: the lock, the threads' arcs arriving at the mark). Pure: weave.ts draws from it
// and the cue sheet (sfx/scenes/weave.ts) places its sounds from it.
import type { AudioData } from '../engine/audio';
import { wordTimes } from '../engine/motion';
import { FPS } from '../engine/util';
import { norm, type VO } from '../engine/vo';

/** Every time the scene keys on, from the voiceover's onsets and the score's grid. */
export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'weave');
  const at = (w: string, nth = 0) => {
    const h = ws.filter((x) => norm(x.w.w) === w)[nth];
    if (!h) throw new Error(`weave: no spoken "${w}" (#${nth})`);
    return h.at;
  };
  // the cut is on a downbeat (the score's one big hit); the lock is the next one, and the settle the last
  const downs = audio.downbeats.filter((d) => d > start + 0.05 && d < end);
  if (downs.length < 2) throw new Error('weave: needs two downbeats after the cut');
  const lock = downs[0]!, settle = downs[downs.length - 1]!;
  const after = audio.beats.find((b) => b > settle + 0.05) ?? settle + 60 / audio.bpm;
  // the signature: the first beat after the call to action has settled (it lands at after + 0.41)
  const credit = audio.beats.find((b) => b > after + 0.45) ?? after + 60 / audio.bpm;
  return {
    start, end, lock, settle, after, credit,
    gitloom: at('gitloom'),
    forget: [at('i', 0), at('dont'), at('forget')],
    i: at('i', 1), commit: at('commit'),
  };
}
export type Times = ReturnType<typeof timesOf>;

/** The frame B15 locks the mark on (choreo.py Times.lock_frame: the lock's nearest frame), as film time. */
export const lockFrameTime = (T: Pick<Times, 'lock'>) => Math.round(T.lock * FPS) / FPS;

/**
 * The threads that arc in from the dark ahead of the lock (choreo.py FLIGHTS): when each one's head reaches the mark
 * (`enter`, in the plate's animation time, s from the scene's start). The ramp is real time until RAMP_FROM before the
 * lock, so these are film time from the cut. The hook's thread (`xhook`) comes in through the lock itself.
 */
export const ARCS = { stem: 0.3, gbar: 0.46, vloop: 0.92 } as const;
/** choreo.py: the ramp eases to half speed over EASE ending LEAD before the lock; before that, plate time is film time. */
const RAMP_FROM = 0.15 + 0.3;

/** When each arc reaches the mark (film time), in the order they arrive. */
export function arcArrivals(T: Pick<Times, 'start' | 'lock'>): number[] {
  const out = Object.values(ARCS).map((e) => T.start + e).sort((a, b) => a - b);
  for (const t of out) if (!(t < T.lock - RAMP_FROM)) throw new Error('weave: an arc arrives inside the ramp (choreo.py): its film time is not its plate time');
  return out;
}

/** The wordmark's typing: one character a frame from `WORDMARK_LEAD` after the settle. */
export const WORDMARK_LEAD = 0.08;
export const wordmarkShown = (t: number, settle: number, n: number) => Math.min(n, Math.max(0, Math.floor((t - settle - WORDMARK_LEAD) * 30) + 1));
