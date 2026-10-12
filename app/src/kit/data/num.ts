// Numbers for the data blocks, as pure functions: formatting, a count that lands on a time, the columns of a figure
// (digits that roll or flip, and the marks between them), odometer drum positions and split-flap runs. No DOM, so bun
// tests them; every value is a function of its inputs and time.
import { flapAt, flapDigit } from '../../engine/glyphs';
import { clamp, ease, prog } from '../../engine/util';

/** Decimal places in a number as written (91.4 → 1, 1200 → 0, 0.125 → 3). */
export function decimalsOf(v: number): number {
  if (!Number.isFinite(v)) return 0;
  const s = String(Math.abs(v));
  if (s.includes('e')) return 0;
  const i = s.indexOf('.');
  return i < 0 ? 0 : s.length - i - 1;
}

/** A number with `decimals` places, thousands grouped by `sep` (none for ''), the point as `point`. */
export function formatNumber(v: number, decimals = 0, sep = ',', point = '.'): string {
  const neg = v < 0;
  const fixed = Math.abs(v).toFixed(Math.max(0, decimals));
  const [int, frac] = fixed.split('.');
  const grouped = sep ? int!.replace(/\B(?=(\d{3})+(?!\d))/g, sep) : int!;
  return (neg ? '−' : '') + grouped + (frac ? point + frac : '');
}

export type CountEase = 'outExpo' | 'outCubic' | 'outQuart' | 'inOutCubic' | 'linear';

/**
 * A count from `from` to `to` that lands at `land` after `dur` seconds of counting (eased): `from` before it starts,
 * `to` from `land` on.
 */
export function countAt(t: number, from: number, to: number, land: number, dur = 1.4, e: CountEase = 'outExpo'): number {
  const u = prog(t, land - dur, land, ease[e]);
  return t >= land ? to : from + (to - from) * u;
}

/** A column of a figure: a digit (it rolls or flips) or a mark between digits (a separator, the point, a sign, a unit). */
export type Column = { kind: 'digit'; d: number; place: number } | { kind: 'mark'; ch: string };

/**
 * The columns of a figure as written ("$1,284.5%"): digits with their place counted from the leftmost digit (0), and
 * everything else as marks.
 */
export function columnsOf(text: string): Column[] {
  let place = 0;
  return Array.from(text).map((ch) => (/[0-9]/.test(ch) ? { kind: 'digit' as const, d: +ch, place: place++ } : { kind: 'mark' as const, ch }));
}

/**
 * The odometer: drum `i` of `n` (0 the leftmost) at time t, as a continuous position in digits (its face shows
 * position mod 10, the fraction rolling the next digit up). Each drum rolls from `from` to its digit `d` with `spins`
 * full turns plus one more for each drum to its left (so the rightmost spins fastest) and lands `stagger` s before the
 * drum to its right; the last lands exactly on `land`. It decelerates hard onto its stop (outQuart over `dur`) and
 * clicks home (a small damped tick after landing).
 */
export function drumAt(t: number, d: number, i: number, n: number, land: number, o: { from?: number; dur?: number; stagger?: number; spins?: number } = {}): number {
  const from = o.from ?? 0, dur = o.dur ?? 1.5, stagger = o.stagger ?? 0.07, spins = o.spins ?? 1;
  const myLand = land - (n - 1 - i) * stagger;
  const travel = 10 * (spins + i) + (((d - from) % 10) + 10) % 10;
  if (t >= myLand) {
    const dt = t - myLand;
    return dt > 0.4 ? from + travel : from + travel + 0.09 * Math.exp(-dt * 22) * Math.sin(dt * 46);
  }
  return from + travel * prog(t, myLand - dur, myLand, ease.outQuart);
}

/** A drum position's face: the digit showing, the next one, and how far (0..1) the drum has rolled toward it. */
export function drumFace(pos: number): { a: number; b: number; f: number } {
  const fl = Math.floor(pos + 1e-6);
  const a = ((fl % 10) + 10) % 10;
  return { a, b: (a + 1) % 10, f: Math.max(0, pos - fl) };
}

/**
 * A split-flap column `i` of `n` landing on digit `to` at `land` (the leftmost lands first, `stagger` s apart, the last
 * on `land`): `steps` flaps of `step` s each, through seeded digits (glyphs.ts flapDigit: never the one it leaves or
 * the one it lands on). Returns the digit showing (A), the one turning over onto it (B) and the flap's progress 0..1,
 * eased as a flap falls (slow off the hinge, hard onto the stop).
 */
export function flapColumn(t: number, from: string, to: string, i: number, n: number, land: number, o: { steps?: number; step?: number; stagger?: number; seed?: number } = {}): { a: string; b: string; p: number } {
  const stagger = o.stagger ?? 0.06, step = o.step ?? 0.075, steps = (o.steps ?? 6) + i, seed = (o.seed ?? 1) * 97 + i;
  const myLand = land - (n - 1 - i) * stagger;
  const { k, p } = flapAt(t, myLand, steps, step);
  if (k < 0) return { a: from, b: from, p: 0 };
  if (k >= steps) return { a: to, b: to, p: 0 };
  const face = (j: number) => (j <= 0 ? from : j >= steps ? to : flapDigit(seed, j, from, to));
  return { a: face(k), b: face(k + 1), p: clamp(p * p) };
}
