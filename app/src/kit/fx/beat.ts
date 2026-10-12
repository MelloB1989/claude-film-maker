// Beat-driven camera effects as pure functions of time: a zoom punch, a shake, a flash, an exposure pump, letterbox bars
// that spring in and out. BeatFx (beatfx.ts) plays them as an overlay; a custom scene can call them directly and return
// their values as its post overrides:
//
//   import { punch, shake } from '@kit/fx';
//   render(f, out) { ...; return { zoom: punch(f, { on: 'beat', grid: this.ctx.audio }), shake: shake(f, { on: 'downbeat', grid: this.ctx.audio }) }; }
//
// Hits come on the film's grid ('beat', 'downbeat' (= 'bar'), 'backbeat': beats 2 and 4) or at given film times, every
// `every`-th one. The motion language is the engine's: a punch is the house spring's kick (5 Hz, damping 0.6) landing on
// the hit, everything else jumps on the hit and decays to 5% over `decay` s (100-250 ms). No randomness but seeded noise.
import { spring } from '../../engine/motion';
import { letterboxAspect, letterboxBar } from '../../engine/looks';
import { noise1 } from '../../engine/util';
import { W, H } from '../../engine/config';
import type { Grid } from '../text/fx';

/** Where hits fall: on the grid, or at film times (s). */
export type On = 'beat' | 'downbeat' | 'bar' | 'backbeat' | number[];

export interface HitOpts {
  /** Default 'beat' (punch, pump), 'downbeat' (shake, flash). */
  on?: On;
  /** Every n-th hit: beats for 'beat' and 'backbeat' (in their own count), bars for 'downbeat' and 'bar' (default 1). */
  every?: number;
  /** The beat grid (a scene's this.ctx.audio); needed by every `on` but a list of times. */
  grid?: Grid;
  /** Hits only in [from, to) (film s; default all). */
  from?: number;
  to?: number;
  /** How strong (each effect's own unit and default). */
  amount?: number;
  /** s to fall to 5% (shake, flash, pump). */
  decay?: number;
}

const EPS = 1e-9;

/** The last hit at or before t (film s), or −Infinity when there is none. */
export function lastHit(t: number, o: HitOpts): number {
  const on = o.on ?? 'beat', every = Math.max(1, Math.round(o.every ?? 1)), lo = o.from ?? -Infinity, hi = o.to ?? Infinity;
  let h = -Infinity;
  if (Array.isArray(on)) {
    let k = -1;
    for (const x of [...on].sort((a, b) => a - b)) if (x <= t + EPS && x >= lo && x < hi) h = (++k % every === 0 ? x : h);
    return h;
  }
  const g = o.grid;
  if (!g) throw new Error(`a hit on '${on}' needs the film's beat grid (grid: this.ctx.audio)`);
  const tt = Math.min(t, hi - EPS);
  if (on === 'beat') {
    const i = Math.floor(g.beatAt(tt) + EPS);
    h = g.timeOfBeat(Math.floor(i / every) * every);
  } else if (on === 'backbeat') {
    // beats 2 and 4 (the odd beats, counting from the bar's first as 0), the n-th of them by `every`
    const i = Math.floor(g.beatAt(tt) + EPS), b = Math.floor((i - 1) / 2);
    h = g.timeOfBeat(2 * (Math.floor(b / every) * every) + 1);
  } else {
    const j = Math.floor(g.barAt(tt) + EPS);
    h = g.timeOfBar(Math.floor(j / every) * every);
  }
  return h >= lo - EPS && h <= t + EPS ? h : -Infinity;
}

/** A hit's envelope dt s after it: 1 at the hit, falling to 5% at `decay` (exponential); 0 before it. */
export function hitEnv(dt: number, decay = 0.2): number {
  return dt < 0 || !Number.isFinite(dt) ? 0 : Math.exp((-3 * dt) / Math.max(1e-3, decay));
}

/** The house spring (5 Hz, damping 0.6). */
const FREQ = 5, DAMP = 0.6;
const WD = 2 * Math.PI * FREQ * Math.sqrt(1 - DAMP * DAMP), A = 2 * Math.PI * FREQ * DAMP;
/** When its kick peaks after launch (s), and its value there. */
export const KICK_PEAK = Math.atan(WD / A) / WD;
const PEAK = Math.exp(-A * KICK_PEAK) * Math.sin(WD * KICK_PEAK);

/**
 * The house spring's kick (its impulse response), x s after launch, scaled to peak at 1 KICK_PEAK (37 ms) in: a
 * punch's shape. It undershoots 9.5% at 160 ms and is at rest by 300 ms. 0 before launch.
 */
export function kick(x: number): number {
  if (!(x > 0)) return 0;
  if (A * x > 40) return 0;
  return (Math.exp(-A * x) * Math.sin(WD * x)) / PEAK;
}

/** A frame, or just its time. */
type At = { t: number };

/**
 * Zoom punch: the frame's zoom (1 = none) on hits, 1 + amount at each hit (default 0.035) along the house spring's
 * kick, launched KICK_PEAK early so it lands on the hit. Never below 1 (the frame never shows its edges).
 */
export function punch(f: At, o: HitOpts = {}): number {
  const h = lastHit(f.t + KICK_PEAK, o);
  return 1 + (o.amount ?? 0.035) * Math.max(0, kick(f.t + KICK_PEAK - h));
}

/**
 * Camera shake on hits: an offset in logical px (post `shake`), `amount` reference px of a 1080 px short side
 * (default 14) at the hit, seeded noise at `freq` Hz (22) decaying over `decay` (0.25 s).
 */
export function shake(f: At, o: HitOpts & { freq?: number; seed?: number } = {}): [number, number] {
  const e = hitEnv(f.t - lastHit(f.t, { on: 'downbeat', ...o }), o.decay ?? 0.25);
  if (e <= 0) return [0, 0];
  const a = (o.amount ?? 14) * (Math.min(W, H) / 1080) * e, x = f.t * (o.freq ?? 22), s = o.seed ?? 1;
  return [a * noise1(x, 101 * s) + 0, a * noise1(x, 101 * s + 37) + 0];
}

/** The zoom that keeps a shake of `px` logical px from showing the frame's edges. */
export const shakeCover = (px: number) => 1 + (2 * px) / Math.min(W, H);

/** Flash on hits: a level 0..amount (default 0.3) at each hit, decaying over `decay` (0.16 s). */
export function flash(f: At, o: HitOpts = {}): number {
  return (o.amount ?? 0.3) * hitEnv(f.t - lastHit(f.t, { on: 'downbeat', ...o }), o.decay ?? 0.16);
}

/** Exposure pump: 1 + amount (default 0.12; negative ducks) at each hit, back to 1 over `decay` (0.25 s). */
export function pump(f: At, o: HitOpts = {}): number {
  return 1 + (o.amount ?? 0.12) * hitEnv(f.t - lastHit(f.t, o), o.decay ?? 0.25);
}

/**
 * Letterbox bars that spring in at `in` and out at `out` (film s), the house spring both ways (9.5% overshoot): the
 * post `letterbox` (an aspect ratio) for a picture of `aspect` (default 2.39). Before `in` and after it springs out:
 * the frame's own aspect (no bars).
 */
export function bars(f: At, o: { aspect?: number; in: number; out?: number }): number {
  const full = letterboxBar(o.aspect ?? 2.39, W, H);
  const k = spring(f.t - o.in) - (o.out !== undefined ? spring(f.t - o.out) : 0);
  return letterboxAspect(Math.max(0, k) * full, W, H);
}
