// The type of scene `loom`: her lines (L11–L14) and the tiers' labels, drawn on the scene's 2D layer over the B05
// plate. Pure functions of time.
//
// Her lines are flat Bricolage, one at a time at the top left, each word on its onset (it rises a few px and fades up on
// the house spring). The tier word lights as she says it (bone at 55% to full, the light wiping across it left to
// right), and then behaves as its tier does on the loom:
//   "Facts"       lights and holds: nothing moves it again (long-term).
//   "Incidents…"  lights; on "let go" its letters let go in three waves with the three rows, loosening, drifting up and
//                 softening into the dark (ttl).
//   "Rules"       sets loose (wide tracking) and pulls tight on its onset on the warps' own spring; on "break" it takes
//                 the pluck and holds.
//   "Skills,"     arrives dim on its onset and lights only when the shuttle reaches the skills lane (lazy).
// The labels are JetBrains Mono on hairline leaders rising from their lanes at the fell (tracked): each draws on as she
// names its tier (a dot, the leader, the path typed in), the path bright and the tier's property dim.
import { spring } from '../engine/motion';
import { clamp, ease, hash, prog } from '../engine/util';

/** The wipe that lights a word: 0..1 over 0.28 s from `at`. */
export function lightWipe(t: number, at: number): number {
  return prog(t, at - 0.02, at + 0.26, ease.inOutCubic);
}

/** A word's entrance on its onset: alpha, and how far below its place it still is (px). */
export function reveal(t: number, at: number): { a: number; dy: number } {
  const k = spring(t - at + 0.02);
  return { a: clamp(prog(t, at - 0.02, at + 0.14, ease.outCubic)), dy: (1 - k) * 10 };
}

/** "Rules": extra tracking (em) that snaps out on its onset on the warps' spring (b05_loom.py Story.slack), and the
 * pluck on "break" (px, vertical), ringing out as the warps do. */
export function rulesPull(t: number, onset: number, brk: number): { track: number; jolt: number } {
  const slack = 1 - spring(t - onset + 0.02, 4.2, 0.45);
  const d = t - brk;
  const jolt = d > 0 ? 3.2 * (1 - Math.exp(-d / 0.006)) * Math.exp(-d / 0.32) * Math.sin(2 * Math.PI * 7 * d) : 0;
  return { track: 0.16 * slack, jolt };
}

/** "Incidents…": how far letter i of n has let go at t: it goes with row floor(i * k / n) of the k releases. */
export function letGo(t: number, i: number, n: number, release: number[]) {
  const k = release.length;
  const at = release[Math.min(k - 1, Math.floor((i * k) / n))]! + 0.03 * hash(i, 5);
  const d = ease.outQuad(prog(t, at, at + 0.9));
  const h1 = hash(i, 11) - 0.5, h2 = hash(i, 23);
  return {
    dx: d * 0.25 * h1,
    dy: -d * (0.5 + 0.6 * h2),
    rot: d * h1 * 0.5,
    blur: d * 7,
    a: 1 - ease.inOutCubic(prog(t, at + 0.12, at + 0.85)),
  };
}

/** A label's draw-on from its tier's onset: the dot (0..1+ spring), the leader (0..1) and the characters typed. */
export function labelOn(t: number, at: number, chars: number) {
  return {
    dot: spring(t - at, 6, 0.55),
    leader: prog(t, at, at + 0.16, ease.outExpo),
    typed: clamp(Math.floor((t - at - 0.1) * 60) + 1, 0, chars),
  };
}

/** The gc stamp's landing on `at`: scale (from 1.35, settling on 1 with a hair of overshoot) and alpha. */
export function stamp(t: number, at: number): { s: number; a: number } {
  const k = spring(t - at + 0.03, 5.5, 0.62);
  return { s: 1.35 - 0.35 * k, a: clamp(prog(t, at - 0.03, at + 0.05)) };
}
