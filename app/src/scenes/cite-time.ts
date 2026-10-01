// The clocks of scene 07 `cite` (Plan 2 Task 17): every moment the scene keys on, from her measured onsets and the
// score's grid, and the needle's run along its thread (where its tip is at t). Everything here is a pure function of its
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
  // 4. "I'll show you the line." Out of her pause the thread's tip becomes a needle (form), done as she says "I'll"; it
  //    strikes the file on the downbeat, its tip bursts out of line 14 on the eighth after (exit), and the pull through
  //    lands on "line." (the beat), where the thread snaps taut and the lines it was sewn through light.
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

// ------------------------------------------------------------------------------------------------ the needle's run

/**
 * The needle, in the editor's px: its length from the head to the tip, and the eye's centre from the head (the thread's
 * end sits in it). The rest of its shape is cite-needle.ts's.
 */
export const NEEDLE = { len: 150, eye: 17 } as const;
/** The tip's distance from the eye's centre (px). */
export const EYE_TO_TIP = NEEDLE.len - NEEDLE.eye;

/**
 * The thread's path, as distances along it (px): where the first hole is (A, the entry at line 11), the second (B, the
 * exit under line 14) and its end (where the eye comes to rest).
 */
export interface Run {
  a: number;
  b: number;
  end: number;
}

/** A cubic Hermite segment from (t0, s0) at speed v0 to (t1, s1) at speed v1, at t (clamped to the segment). */
export function hermite(t: number, t0: number, s0: number, v0: number, t1: number, s1: number, v1: number): number {
  const d = t1 - t0, u = clamp((t - t0) / d);
  const u2 = u * u, u3 = u2 * u;
  return (2 * u3 - 3 * u2 + 1) * s0 + (u3 - 2 * u2 + u) * d * v0 + (-2 * u3 + 3 * u2) * s1 + (u3 - u2) * d * v1;
}

/** How far before the entry the tip hangs through the pause (px along the path), and how far it draws back to strike. */
export const POISE = 30;
const WINDUP = 9;

/**
 * Where the thread's tip, then the needle's, is along the path at t (px from its start): drawn out of the citation from
 * the end of the citation's streaming, decelerating into its poise just before the entry; there through the pause and
 * the needle's forming, drawing back a hair; then the strike, into the file on the downbeat at full speed; slowing
 * behind the panel as the needle runs under the lines (the slow motion of the speed ramp), bursting out of the exit on
 * the eighth; and the pull through, braking into its rest on "line." with the eye at the thread's end, where the tug
 * rings out. Monotonic but for the wind-up and the tug's ring.
 */
export function tipAt(t: number, T: Pick<Times, 'draw' | 'form' | 'strike' | 'exit' | 'pull'>, run: Run): number {
  const poise = run.a - POISE;
  if (t <= T.draw.at) return 0;
  if (t < T.draw.end) {
    // drawn out fast, then slowing into the poise (a quartic ease out: the tip searching, then settling)
    const u = (t - T.draw.at) / (T.draw.end - T.draw.at);
    return poise * (1 - (1 - u) ** 4);
  }
  if (t < T.form.at) return poise;
  if (t < T.form.end) return poise - WINDUP * Math.sin((Math.PI / 2) * (t - T.form.at) / (T.form.end - T.form.at)) ** 2;
  const rest = run.end + EYE_TO_TIP;
  // the strike lands at full speed; under the panel it slows to about a fifth of it, and bursts out of the exit
  const vStrike = 1500, vUnder = 260, vExit = 1100;
  if (t < T.strike) return hermite(t, T.form.end, poise - WINDUP, 0, T.strike, run.a, vStrike);
  const mid = (T.strike + T.exit) / 2, sMid = run.a + 0.45 * (run.b - run.a);
  if (t < mid) return hermite(t, T.strike, run.a, vStrike, mid, sMid, vUnder);
  if (t < T.exit) return hermite(t, mid, sMid, vUnder, T.exit, run.b, vExit);
  if (t < T.pull) return hermite(t, T.exit, run.b, vExit, T.pull, rest, 0);
  // the tug: the thread takes the needle's weight and rings out (a few px, in a tenth of a second)
  const k = t - T.pull;
  return rest - 7 * Math.exp(-k / 0.07) * Math.sin(2 * Math.PI * 7 * k);
}

/** The eye's place along the path (px): the needle's tip less the eye-to-tip length once the needle has formed. */
export const eyeAt = (tip: number) => tip - EYE_TO_TIP;

/**
 * The needle's forming, 0..1 over `form`: it crystallises out of the thread's tip back to its eye (the front's place
 * along the needle, from the tip at 0 to the head at 1).
 */
export const formAt = (t: number, T: Pick<Times, 'form'>) => clamp((t - T.form.at) / (T.form.end - T.form.at));

/**
 * Where the drawn thread ends (px along the path): its own tip until the needle forms; while it forms, the front the
 * glass runs back along (the thread's last length turning into the needle); after, the eye.
 */
export function threadEnd(t: number, T: Pick<Times, 'draw' | 'form' | 'strike' | 'exit' | 'pull'>, run: Run): number {
  const tip = tipAt(t, T, run), k = formAt(t, T);
  if (k <= 0) return tip;
  // the front runs from the tip back to the eye's centre (the head is past it: the thread ends in the eye)
  return tip - Math.min(1, k * (NEEDLE.len / EYE_TO_TIP)) * EYE_TO_TIP;
}

/**
 * How taut the thread's run through the air is, 0 (the slack it was drawn out on) to 1 (a straight line from the
 * citation to the entry): it takes up its slack through the pull, faster as the needle draws it, and rings past straight
 * when the tug lands (a twang), settling in a fifth of a second.
 */
export function tautAt(t: number, T: Pick<Times, 'exit' | 'pull'>): number {
  if (t <= T.exit) return 0;
  if (t < T.pull) return ((t - T.exit) / (T.pull - T.exit)) ** 3;
  const k = t - T.pull;
  return 1 + 0.14 * Math.exp(-k / 0.06) * Math.sin(2 * Math.PI * 9 * k);
}

/** The time the tip passes `s` along the path (px) on its run under the lines, by bisection: [strike, exit]. */
export function tipPasses(s: number, T: Pick<Times, 'draw' | 'form' | 'strike' | 'exit' | 'pull'>, run: Run): number {
  let a = T.strike, b = T.exit;
  if (tipAt(a, T, run) >= s) return a;
  if (tipAt(b, T, run) <= s) return b;
  for (let i = 0; i < 48; i++) {
    const m = (a + b) / 2;
    if (tipAt(m, T, run) < s) a = m;
    else b = m;
  }
  return (a + b) / 2;
}
