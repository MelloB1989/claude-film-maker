// Beat-locked motion helpers for scenes: springs, slams, speed ramps, whips, word onsets and beat pulses.
// Each is a pure function of its inputs (a time, the Frame's beat grid, the voiceover) with no state, so any frame
// renders identically in any order, which adaptive motion blur and seeking depend on. They compose util.ts (TAU, ease,
// prog, pulse) instead of repeating it. The feel is the plan's motion language v2: springs are fast and tight
// (4-6 Hz, damping 0.5-0.7), a whip is 60-120 ms, and nothing bounces like a cartoon.
import type { Frame } from './scene';
import { ease, prog, pulse, TAU } from './util';
import type { VO, Word } from './vo';

/** The house spring: 5 Hz at damping 0.6 overshoots 9.5% and is within 1% by 250 ms. */
const FREQ = 5;
const DAMPING = 0.6;
/** exp(-40) is under half an ulp of 1, so a spring that has decayed this far is exactly 1. */
const SETTLED = 40;

/**
 * Step response of a damped spring: 0 at t <= 0, rising to 1 with a tight overshoot, then at rest. `freq` is the natural
 * frequency in Hz and `damping` the damping ratio, so the overshoot is exp(-pi z / sqrt(1 - z^2)) whatever the frequency:
 * 9.5% at 0.6 (16% at 0.5, 4.6% at 0.7). The defaults settle to within 1% by 250 ms. A damping of 1 or more is critically
 * or over-damped and never passes 1.
 *
 * This is not util.springStep. That one leaves out the sine term of the step response, so it launches at a nonzero speed
 * and overshoots 12.3% at damping 0.6, past the 12% the motion language allows.
 */
export function spring(t: number, freq = FREQ, damping = DAMPING): number {
  if (t <= 0 || freq <= 0) return 0;
  const w = TAU * freq;
  const z = Math.max(0, damping);
  if (z < 1) {
    const a = z * w; // decay rate of the envelope
    if (a * t > SETTLED) return 1;
    const b = w * Math.sqrt(1 - z * z); // damped frequency
    return 1 - Math.exp(-a * t) * (Math.cos(b * t) + (a / b) * Math.sin(b * t));
  }
  const r = w * Math.sqrt(z * z - 1);
  const p1 = z * w - r; // the slow pole
  if (p1 * t > SETTLED) return 1;
  if (r < 1e-9 * w) return 1 - Math.exp(-w * t) * (1 + w * t); // critically damped
  const p2 = z * w + r;
  return 1 - (p2 * Math.exp(-p1 * t) - p1 * Math.exp(-p2 * t)) / (p2 - p1);
}

/** When an under-damped spring first reaches 1: cos(bt) + (a/b) sin(bt) = 0, at bt = pi/2 + asin(z). */
function rise(freq: number, damping: number): number {
  const z = Math.max(0, damping);
  return freq > 0 && z < 1 ? (Math.PI / 2 + Math.asin(z)) / (TAU * freq * Math.sqrt(1 - z * z)) : 0;
}

/**
 * A spring that lands on `hit` (a word's spoken onset, a downbeat): 0 until `hit - lead`, then spring(t - (hit - lead)).
 * `lead` is how early it launches. By default it is the spring's rise time, so the value first reaches 1 exactly at
 * `hit` and the overshoot follows it: the impact lands on the sound. `lead: 0` launches it at the hit instead. A spring
 * that never overshoots has no impact to land, so its default lead is 0.
 */
export function slam(t: number, hit: number, o: { lead?: number; freq?: number; damping?: number } = {}): number {
  const { freq = FREQ, damping = DAMPING } = o;
  return spring(t - (hit - (o.lead ?? rise(freq, damping))), freq, damping);
}

/** The area under ease.inOutCubic (util.keys' default ease) from 0 to u: what a ramp has added once a time falls inside it. */
const rampArea = (u: number) => (u <= 0.5 ? u ** 4 : u - 0.5 + (1 - u) ** 4);

/**
 * Speed-ramp time remap: the time to play at local time `tLocal`, the integral of a speed curve (0 at tLocal = 0).
 * `keys` are [time, speed] and the curve eases between them exactly as util keys() does (inOutCubic, so a ramp into
 * slow motion has no kink), holding the first key's speed before it and the last key's after it. So a run of speed 1
 * maps 1:1 and two keys at 0.25 advance at a quarter. Two keys at the same time change speed instantly (the snap back
 * to real time on a beat) and the mapped time stays continuous. It is monotonic while the speeds are >= 0; a negative
 * speed runs time backwards (a scrub). No keys means real time. Exact (no sampling) and O(keys).
 *
 * util.ts exports a different `remap` (a range remap): import one of the two under an alias.
 */
export function remap(tLocal: number, keys: [t: number, speed: number][]): number {
  if (keys.length === 0) return tLocal;
  const pts = [...keys].sort((a, b) => a[0] - b[0]);
  /** The integral of the speed curve from the first key to x. */
  const area = (x: number): number => {
    const [t0, s0] = pts[0]!;
    if (x <= t0) return s0 * (x - t0);
    let a = 0;
    for (let i = 1; i < pts.length; i++) {
      const [p, sp] = pts[i - 1]!;
      const [k, sk] = pts[i]!;
      if (x >= k) {
        a += ((k - p) * (sp + sk)) / 2; // a whole segment (zero-width for an instant change)
        continue;
      }
      const u = (x - p) / (k - p);
      return a + (k - p) * (sp * u + (sk - sp) * rampArea(u));
    }
    const [tn, sn] = pts[pts.length - 1]!;
    return a + sn * (x - tn);
  };
  return area(tLocal) - area(0);
}

/** The middle of the motion language's 60-120 ms. */
const WHIP_DUR = 0.09;
/** Peak directional blur, in the logical 1920x1080 px scenes lay out in (multiply by SCALE for physical pixels). */
const WHIP_BLUR_PX = 200;

/**
 * A whip around a cut: over `dur` seconds centred on `cut`, `k` eases 0 to 1 (0 before the window, 1 after, 0.5 at the cut
 * where the shots change) and `blurPx` is the directional blur that goes with it, following k's speed as a real whip's
 * smear does: 0 outside the window, 200 logical px at the cut. Drive the pan with k and the blur pass with blurPx. A `dur`
 * of 0 or less is an instant cut with no blur.
 */
export function whip(t: number, cut: number, dur = WHIP_DUR): { k: number; blurPx: number } {
  if (dur <= 0) return { k: t < cut ? 0 : 1, blurPx: 0 };
  const u = prog(t, cut - dur / 2, cut + dur / 2);
  // inOutQuart's speed, scaled to 1 at the cut, is (1 - |2u - 1|)^3
  return { k: ease.inOutQuart(u), blurPx: WHIP_BLUR_PX * (1 - Math.abs(2 * u - 1)) ** 3 };
}

/**
 * The spoken onsets of a scene's words, in order: { w, at: w.start }. Times come from the data, never from hard-coded
 * seconds. A scene with no spoken words gives []; a scene id the voiceover does not have throws, so a typo fails loudly
 * while authoring instead of quietly animating nothing.
 */
export function wordTimes(vo: VO, scene: string): { w: Word; at: number }[] {
  const words = vo.lines.filter((l) => l.scene === scene).flatMap((l) => l.words);
  if (words.length === 0 && !vo.scenes.some((s) => s.id === scene)) {
    throw new Error(`wordTimes: no voiceover scene "${scene}" (have ${vo.scenes.map((s) => s.id).join(', ')})`);
  }
  return words.map((w) => ({ w, at: w.start }));
}

/** The locked score is 4/4 (AudioData.barAt assumes the same when it has no downbeats). */
const BEATS_PER_BAR = 4;

/**
 * A decaying pulse on every beat: 1 on the beat, halving every `halfLife` beats. The unit is beats, not seconds: a Frame
 * carries the grid's beat phase and not the tempo, so the decay follows the tempo (0.2 beats is 120 ms at the score's
 * 100 BPM).
 */
export function onBeat(f: Frame, halfLife = 0.2): number {
  return pulse(f.beatPhase, 0, halfLife);
}

/** The same on every downbeat (the first beat of a bar), with a longer default since it is the accent. `halfLife` is in beats. */
export function onDownbeat(f: Frame, halfLife = 0.5): number {
  return pulse(f.barPhase * BEATS_PER_BAR, 0, halfLife);
}
