// Motion curves for v3 explainer graphics (docs/STYLE_V3.md §4): every one a pure function of time, so a frame renders
// the same whenever it is asked for. Times are seconds on the shot's clock.
import * as THREE from 'three';
import { glow, type GlowKey } from '../../engine/look';
import { LIN, type PaletteKey } from '../../engine/palette';
import { clamp, ease, TAU } from '../../engine/util';

/** 0..1 linear progress through [at, at + dur]. */
export const win = (t: number, at: number, dur: number) => clamp((t - at) / Math.max(1e-6, dur));

/**
 * A damped spring from 0 to 1 that starts at `at`: it overshoots by about `over` (0.06-0.12) and settles in about
 * `settleS` seconds. 0 before `at`.
 */
export function spring(t: number, at: number, settleS = 0.55, over = 0.08): number {
  const x = t - at;
  if (x <= 0) return 0;
  // the damping ratio from the overshoot: over = exp(-z pi / sqrt(1 - z^2))
  const l = Math.log(Math.max(1e-4, over));
  const z = -l / Math.sqrt(Math.PI * Math.PI + l * l);
  const wn = 4.6 / (z * settleS);
  const wd = wn * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * wn * x) * (Math.cos(wd * x) + (z / Math.sqrt(1 - z * z)) * Math.sin(wd * x));
}

/**
 * Anticipation, then a spring: a pull back of `amt` over the `antic` seconds before `at`, then the springy move to 1.
 * Use it on a scale or a position: v = from + (to - from) * antic(...).
 */
export function antic(t: number, at: number, o: { antic?: number; amt?: number; settle?: number; over?: number } = {}): number {
  const a = o.antic ?? 0.1, amt = o.amt ?? 0.08;
  if (t < at - a) return 0;
  if (t < at) return -amt * Math.sin((Math.PI / 2) * ((t - (at - a)) / a));
  return -amt + (1 + amt) * spring(t, at, o.settle ?? 0.5, o.over ?? 0.08);
}

/** outExpo through [at, at + dur]: the fast-in, long-settle move (camera arrives, flights). */
export const expo = (t: number, at: number, dur: number) => ease.outExpo(win(t, at, dur));
/** inOutCubic through [at, at + dur]. */
export const smooth = (t: number, at: number, dur: number) => ease.inOutCubic(win(t, at, dur));

/** The start time of item i of a staggered group: `at` + i * `step`. */
export const stagger = (at: number, i: number, step = 2 / 24) => at + i * step;

/** A pulse: 0 before `at`, up to 1 in `rise` s, then decaying with half-life `hl` (an emphasis flash). */
export function pulse(t: number, at: number, rise = 0.04, hl = 0.15): number {
  if (t < at) return 0;
  const x = t - at;
  if (x < rise) return x / rise;
  return Math.pow(0.5, (x - rise) / hl);
}

/** A slow periodic breath, ±1 around 0 (idle secondary motion), phase-shifted by `seed`. */
export const breathe = (t: number, hz = 0.5, seed = 0) => Math.sin(TAU * (hz * t + seed * 0.618));

/** Ease out to `to` from `from`. */
export const mix = (a: number, b: number, k: number) => a + (b - a) * k;

/**
 * A palette colour as linear HDR (for MeshBasicMaterial / emissive): accent roles via glow() (the bloom key reads `k`),
 * others scaled linearly by `k`. Materials that use it should set toneMapped: false only when they mean to bloom.
 */
export function hdr(role: PaletteKey | `#${string}`, k = 1): THREE.Color {
  if (role.startsWith('#')) {
    const c = new THREE.Color(role); // three converts sRGB hex to linear (ColorManagement)
    return c.multiplyScalar(k);
  }
  const glowable: GlowKey[] = ['accent', 'accentBright', 'accentDim', 'accent2', 'accent2Dim'];
  if (glowable.includes(role as GlowKey) && k > 1) {
    const g = glow(role as GlowKey, k);
    return new THREE.Color().setRGB(g[0], g[1], g[2]);
  }
  const c = LIN[role as PaletteKey];
  return new THREE.Color().setRGB(c[0] * k, c[1] * k, c[2] * k);
}

/** World units per px at `dist` from a camera of vertical fov `fovDeg` on a 1080 px tall frame. */
export const unitPerPx = (dist: number, fovDeg: number) => (2 * dist * Math.tan((fovDeg * Math.PI) / 360)) / 1080;

export type V3 = [number, number, number];
export interface CamKey { t: number; pos: V3; target: V3; fov?: number; ease?: (x: number) => number }

/** A camera through keys: each segment eased (inOutCubic by default) from the key before to the key it heads to. */
export function keyed(t: number, ks: CamKey[]): { pos: V3; target: V3; fov?: number } {
  if (t <= ks[0]!.t) return { pos: ks[0]!.pos, target: ks[0]!.target, fov: ks[0]!.fov };
  for (let i = 1; i < ks.length; i++) {
    const a = ks[i - 1]!, b = ks[i]!;
    if (t < b.t) {
      const k = (b.ease ?? ease.inOutCubic)(clamp((t - a.t) / (b.t - a.t)));
      const l = (x: V3, y: V3): V3 => [x[0] + (y[0] - x[0]) * k, x[1] + (y[1] - x[1]) * k, x[2] + (y[2] - x[2]) * k];
      return { pos: l(a.pos, b.pos), target: l(a.target, b.target), fov: (a.fov ?? 30) + ((b.fov ?? a.fov ?? 30) - (a.fov ?? 30)) * k };
    }
  }
  const z = ks[ks.length - 1]!;
  return { pos: z.pos, target: z.target, fov: z.fov };
}

/** World units per em for type of cap height `px` (1080p px) at `dist` from a camera of vertical fov `fov`. */
export const em = (px: number, dist: number, fov = 30) => ((px / 0.7) * 2 * dist * Math.tan((fov * Math.PI) / 360)) / 1080;
