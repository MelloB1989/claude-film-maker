// The odometer of `proof` as numbers: where each drum stands (in digit steps) at any time, as a real counter's would.
// Pure functions of t, no three.js, so bun tests them.
//
// The counter is an odometer, not a slot machine. Its fastest drum runs the value; every drum above it turns only as
// the drum below passes from 9 to 0 (the carry), the way a car's mileage counter is geared. So 44 → 72 spins the ones
// drum through 2.8 turns while the tens drum ticks up three times, the last as the ones drum slows; 80 → 83 is three
// slow steps of the ones drum alone (a small gain looks small); 83 → 91.4 brings in the tenths drum, which spins 8.4
// turns while the ones drum steps eight times and the tens ticks once. The motion is the data.
//
// A roll is kicked on its beat at full speed and decelerates (ease-out) into its landing an eighth note later, where
// the fastest drum clicks into its detent: a small spring past the mark and back. While the drums turn they loosen
// apart, and as they land they close up to the figure's own kerning (each round's figure set as one kerned line), so
// every figure at rest is typeset and the mechanism breathes between them.
import { clamp, smoothstep } from '../engine/util';

/** A round of the benchmark: its tag (v1…v7) and its figure as shown ("44", "91.4%"). */
export interface Round { tag: string; figure: string; value: number }

/** The rounds from the copy: [tag, figure, tag, figure, …] (proof.strings.json's first ten strings). */
export function roundsOf(pairs: readonly string[]): Round[] {
  const out: Round[] = [];
  for (let i = 0; i + 1 < pairs.length; i += 2) {
    const figure = pairs[i + 1]!;
    out.push({ tag: pairs[i]!, figure, value: Number(figure.replace('%', '')) });
  }
  return out;
}

/** The roll's ease: full speed on the kick, decelerating into the landing (outQuart: a fifth of the run left at a third
 * of the time, the last tenth taking over half of it). */
export const ROLL_POWER = 4;
export const rollEase = (u: number) => 1 - (1 - clamp(u)) ** ROLL_POWER;

/** The detent's click on the fastest drum (steps, Hz, 1/s): past the mark by `amp` and back, dying within ~0.2 s. */
export const CLICK = { amp: 0.08, freq: 6, decay: 16 };
export function click(dt: number): number {
  // (gone after a second: exp(-16) is under a millionth of a step; and never NaN, before any landing)
  return dt > 0 && dt < 1 ? CLICK.amp * Math.sin(2 * Math.PI * CLICK.freq * dt) * Math.exp(-CLICK.decay * dt) : 0;
}

/** A drum above another turns through the last step of the one below's run from 9 to 0. */
const carry = (x: number, span: number) => Math.floor(x / span) + clamp((x % span) - (span - 1));

export interface Drums {
  /** Positions in digit steps (digit d at rest is position d, mod 10). */
  tens: number;
  ones: number;
  tenths: number;
  /** The round shown, or rolling to, and how far its roll has gone (0 before its kick, 1 from its landing). */
  round: number;
  u: number;
  /** How far the drums stand loosened apart (0 at rest, up to 1 mid-roll). */
  loose: number;
  /** How far the spacing has gone from the last figure's kerning to this one's (0..1). */
  kern: number;
}

/**
 * The drums at t: round 0 until the first kick, then each round from its kick (rolling) to its landing (at rest,
 * clicking). Rounds before the last count in whole units on the ones drum; the last (a figure with a decimal) counts in
 * tenths on the tenths drum.
 */
export function drumsAt(t: number, rounds: readonly Round[], kicks: readonly number[], lands: readonly number[]): Drums {
  let r = 0;
  while (r < kicks.length && t >= kicks[r]!) r++; // rounds kicked so far: rolling to round r
  const from = rounds[Math.max(0, r - 1)]!.value, to = rounds[r]!.value;
  const u = r === 0 ? 1 : clamp((t - kicks[r - 1]!) / (lands[r - 1]! - kicks[r - 1]!));
  const landAt = r === 0 ? -Infinity : lands[r - 1]!;
  const decimal = !Number.isInteger(to);
  const unit = decimal ? 10 : 1;
  const x = (r === 0 ? to * unit : from * unit + (to - from) * unit * rollEase(u)) + click(t - landAt);
  const loose = r === 0 ? 0 : smoothstep(0, 0.12, u) * (1 - smoothstep(0.45, 1, u));
  const kern = r === 0 ? 1 : smoothstep(0.35, 1, u);
  if (decimal) return { tenths: x, ones: carry(x, 10), tens: carry(x, 100), round: r, u, loose, kern };
  return { tenths: 0, ones: x, tens: carry(x, 10), round: r, u, loose, kern };
}

/** The digit a drum at position `p` shows square to the window (the nearest slot). */
export const digitAt = (p: number) => (((Math.round(p) % 10) + 10) % 10);

