// The clocks of scene 07 `cite` (Plan 2 Task 17): every moment the scene keys on, from her measured onsets and the
// score's grid, and the thread's run along its route (where its drawn tip is at t). Everything here is a pure function of its
// inputs: nothing is hard-coded in seconds but the small leads and lags round her words.
import type { AudioData } from '../engine/audio';
import { wordTimes } from '../engine/motion';
import { clamp } from '../engine/util';
import { norm, type VO, type Word } from '../engine/vo';

/** A window of song time (s). */
export interface Span {
  at: number;
  end: number;
}

/** Every time the scene keys on (song seconds), from her onsets and the score's beats and downbeats. */
export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'cite').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`cite: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm;
  const ask = word('ask'), why = word('why'), believe = word('believe'), something = word('something');
  const ill = word('ill'), show = word('show'), line = word('line');
  const beatIn = (a: number, b: number) => audio.beats.find((x) => x > a && x < b);
  const downbeatIn = (a: number, b: number) => audio.downbeats.find((x) => x > a && x < b);

  // 1. The question. `what editor do I use?` is typing as the cut lands and is sent a little before the downbeat she
  //    starts "Ask" on, where the answer `neovim.` streams in.
  const answer = downbeatIn(start, why.start) ?? ask.start;
  const question: Span = { at: start - 0.1, end: answer - 0.24 };
  const answerEnd = answer + 0.26;
  // 2. Why. The `why?` chip pops in as the answer completes; the pointer clicks it on "why" and lets go on the beat after,
  //    where the citation's label springs open out of the chip; the citation streams into it, done on "believe".
  const chip = answerEnd + 0.03;
  const click = why.start;
  const release = beatIn(why.start, believe.start) ?? why.end;
  const cite: Span = { at: release + 0.06, end: believe.start + 0.22 };
  // 3. The thread is drawn out of the citation's end as its last characters land, the file jumping to its lines on the
  //    beat in "believe"; its tip arrives over line 11 on the beat in "something…" and hangs there through the pause.
  const scroll = beatIn(believe.start - 0.1, something.start + 0.1) ?? believe.end;
  const draw: Span = { at: cite.end - 0.08, end: beatIn(something.start, ill.start) ?? something.end };
  // 4. "I'll show you the line." Through her pause the tip drifts down onto the file (form: the approach, done as she
  //    says "I'll"); it lands on the file's face on the downbeat (strike) and lies down the margin beside lines 11–14, past
  //    their foot on the eighth after (exit), settling by the next sixteenth; on "line." (the beat, pull) the light lands
  //    and floods up the thread from the lines to the citation.
  const strike = downbeatIn(ill.start - 0.2, show.start) ?? ill.end;
  const form: Span = { at: ill.start - 0.24, end: strike - 0.035 };
  const exit = strike + beat / 2;
  const pull = audio.beats.find((b) => Math.abs(b - line.start) < beat / 4) ?? line.start;
  if (!(question.end < answer && cite.end < draw.end && draw.end < form.at && exit < pull && pull < end - 0.3)) {
    throw new Error('cite: the moments do not fit her line and the window');
  }
  return {
    start, end, beat,
    question, answer, answerEnd, chip, click, release, cite,
    scroll, draw, form, strike, exit, pull,
    /** Her words the light keys on. */
    why: why.start, ill: ill.start, line: line.start,
  };
}
export type Times = ReturnType<typeof timesOf>;

// ------------------------------------------------------------------------------------------------ the thread's run

/** A cubic Hermite segment from (t0, s0) at speed v0 to (t1, s1) at speed v1, at t (clamped to the segment). */
export function hermite(t: number, t0: number, s0: number, v0: number, t1: number, s1: number, v1: number): number {
  const d = t1 - t0, u = clamp((t - t0) / d);
  const u2 = u * u, u3 = u2 * u;
  return (2 * u3 - 3 * u2 + 1) * s0 + (u3 - 2 * u2 + u) * d * v0 + (-2 * u3 + 3 * u2) * s1 + (u3 - u2) * d * v1;
}

/** The route as distances along it (px): where the thread lands on the file's face, and its end (the seam's foot). */
export interface Run {
  land: number;
  end: number;
}

/** When the seam is laid: the eighth after the landing plus a sixteenth, where it comes to rest before the pull. */
export const layEnd = (T: Pick<Times, 'exit' | 'beat'>) => T.exit + T.beat / 4;

/**
 * Where the thread's drawn tip is along its route at t (px from its start), one continuous move with no stop: drawn
 * out of the underline quick, slowing as it falls through the air and her pause, landing on the file's face on the
 * downbeat at the speed it then lays the seam at, and laying it down the margin, easing to rest at its foot.
 * Monotonic, and its speed is continuous through the landing.
 */
export function tipAt(t: number, T: Pick<Times, 'draw' | 'strike' | 'exit' | 'beat'>, run: Run): number {
  if (t <= T.draw.at) return 0;
  const t1 = layEnd(T);
  if (t >= t1) return run.end;
  // the seam is laid at an even ease out: its speed at the landing is 1.5 times its mean
  const vLand = (1.5 * (run.end - run.land)) / (t1 - T.strike);
  if (t < T.strike) {
    // out of the label at twice the fall's mean speed, a long drift, and into the landing at the seam's speed
    const v0 = (2 * run.land) / (T.strike - T.draw.at);
    return hermite(t, T.draw.at, 0, v0, T.strike, run.land, vLand);
  }
  return hermite(t, T.strike, run.land, vLand, t1, run.end, 0);
}

/**
 * How taut the air is, 0 (the slack it is drawn out on) to 1 (drawn in): it draws in as the light lands on "line." and
 * rings a little past (a soft twang), settling in a quarter of a second.
 */
export function tautAt(t: number, T: Pick<Times, 'pull'>): number {
  if (t <= T.pull - 0.08) return 0;
  if (t < T.pull) return ((t - (T.pull - 0.08)) / 0.08) ** 2;
  const k = t - T.pull;
  return 1 + 0.12 * Math.exp(-k / 0.07) * Math.sin(2 * Math.PI * 7 * k);
}

/** The time the tip passes `s` along the route (px) while it lays the seam, by bisection: [strike, layEnd]. */
export function tipPasses(s: number, T: Pick<Times, 'draw' | 'strike' | 'exit' | 'beat'>, run: Run): number {
  let a = T.strike, b = layEnd(T);
  if (tipAt(a, T, run) >= s) return a;
  if (tipAt(b, T, run) <= s) return b;
  for (let i = 0; i < 48; i++) {
    const m = (a + b) / 2;
    if (tipAt(m, T, run) < s) a = m;
    else b = m;
  }
  return (a + b) / 2;
}
