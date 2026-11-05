// Rain: anime rain over a shot, a pure function of time. Thin slanted streaks in depth layers (the far ones dense, thin,
// dim and slow; the near ones sparse, long, bright and fast), splashes ticking on a ground band, lightning, and a clock
// that can slow to a stop, the drops shrinking from streaks to beads as it does (the time-freeze before a duel's cut).
// Transparent by default: stack it over a picture (Stack layer, blend 'normal' or 'screen') or play it as an overlay.
//
// Params (and BgScene's: color '#dde4ec', intensity 1, seed, speed 1, background 'none'):
//   layers 4          depth layers of streaks (1..6)
//   density 1         how many streaks
//   length 1          how long they are
//   angle 8           the slant, degrees (the wind; + falls toward the right)
//   opacity 0.55      how strongly the streaks show
//   ground -1         the splash band's top as a share of the frame from the top (0.7: the lower 30%); -1 no splashes
//   splash 1          how many splashes
//   slow []           [[t, rate], ...] the rain's clock rate over the shot (s from its start), linear between keys
//                     (1 normal, 0 frozen); the streaks shrink to beads as the rate falls
//   lightning []      shot times (s) of lightning: a double flicker of the frame's exposure
//   fade              keys of the rain's strength over the shot ([[t, k], ...], PostKeys' keys): the rain thinning out
import * as THREE from 'three';
import { BgScene } from '../bg/base';
import type { Frame, PostOverrides } from '../../engine/scene';
import { trackAt, type Keys, type Track } from './postkeys';

/** The integral of a piecewise-linear rate through `pts` (sorted [t, rate]) from its first point to x; the rate holds
 * its first value before the first point and its last after the last. */
function rateIntegral(pts: [number, number][], x: number): number {
  const [a, r0] = pts[0]!;
  if (x <= a) return (x - a) * r0;
  let s = 0;
  for (let i = 0; i + 1 < pts.length; i++) {
    const [t0, q0] = pts[i]!, [t1, q1] = pts[i + 1]!;
    if (x <= t1) {
      const qx = q0 + ((q1 - q0) * (x - t0)) / Math.max(1e-9, t1 - t0);
      return s + ((q0 + qx) / 2) * (x - t0);
    }
    s += ((q0 + q1) / 2) * (t1 - t0);
  }
  const [tl, ql] = pts[pts.length - 1]!;
  return s + (x - tl) * ql;
}

function rateAt(pts: [number, number][], x: number): number {
  if (x <= pts[0]![0]) return pts[0]![1];
  for (let i = 0; i + 1 < pts.length; i++) {
    const [t0, q0] = pts[i]!, [t1, q1] = pts[i + 1]!;
    if (x <= t1) return q0 + ((q1 - q0) * (x - t0)) / Math.max(1e-9, t1 - t0);
  }
  return pts[pts.length - 1]![1];
}

/**
 * The rain's own clock at shot time `lt` (s from the shot's start): the integral from 0 of the rate the `slow` keys
 * give ([[t, rate], ...], linear between them; 1 from the shot's start to the first key when that key is later), and
 * the rate itself.
 */
export function rainClock(lt: number, keys: [number, number][] = []): { clock: number; rate: number } {
  if (!keys.length) return { clock: lt, rate: 1 };
  const k = [...keys].sort((x, y) => x[0] - y[0]);
  const pts: [number, number][] = k[0]![0] > 0 ? [[0, 1], ...k] : k;
  return { clock: rateIntegral(pts, lt) - rateIntegral(pts, 0), rate: rateAt(pts, lt) };
}

/** Lightning: the exposure lift at shot time lt for strikes at `times` (a bright flicker, a dip, a second flicker). */
export function lightningAt(lt: number, times: number[] = []): number {
  let v = 0;
  for (const t0 of times) {
    const x = lt - t0;
    if (x < 0 || x > 0.6) continue;
    v = Math.max(v, Math.exp(-x * 30) * 1.2 + (x > 0.12 ? Math.exp(-(x - 0.12) * 14) * 0.8 : 0));
  }
  return v;
}

export class Rain extends BgScene {
  protected override defaults = { background: 'none', color: '#dde4ec', speed: 1 } as Record<string, unknown>;
  private u = {
    uLayers: { value: 4 }, uDensity: { value: 1 }, uLen: { value: 1 }, uAngle: { value: 0.14 }, uOpacity: { value: 0.55 },
    uClock: { value: 0 }, uLenK: { value: 1 }, uGround: { value: -1 }, uSplash: { value: 1 },
  };

  protected override uniforms() {
    return this.u;
  }

  protected effect() {
    return /* glsl */ `
uniform float uLayers, uDensity, uLen, uAngle, uOpacity, uClock, uLenK, uGround, uSplash;

// one depth layer of streaks: p in short-side units, y down, already slanted; i the layer (0 far)
float rainLayer(vec2 p, float t, float i) {
  float depth = uLayers > 1.0 ? i / (uLayers - 1.0) : 1.0;
  float px = 1.0 / min(uRes.x, uRes.y);
  float cols = uDensity * mix(150.0, 34.0, depth);        // columns per short side
  float spd = mix(1.5, 3.6, depth);                        // short sides per second
  float L = uLen * mix(0.03, 0.12, depth) * uLenK;         // streak length
  float wid = mix(0.9, 1.7, depth) * px;                   // half-width
  float a = mix(0.3, 0.95, depth);
  float P = mix(0.32, 0.85, depth);                        // the drops' repeat along a column
  float seed = i * 17.13 + uSeed * 3.7;
  float q = p.x * cols;
  float col = floor(q);
  float hc = hash11(col * 0.731 + seed);
  float x = (fract(q) - 0.5 - (hash11(col * 1.37 + seed) - 0.5) * 0.7) / cols;
  float y = p.y - t * spd * (0.85 + 0.3 * hc) + hc * 13.0;
  float k = floor(y / P);
  float hd = hash12(vec2(col, k) + seed);
  float on = step(0.3, hd);
  float cy = (fract(y / P) - hd * 0.5) * P;
  float along = smoothstep(0.0, L * 0.3 + px, cy) * (1.0 - smoothstep(L * 0.55, L + px, cy));
  float across = exp(-(x * x) / (wid * wid));
  return on * along * across * a * (0.55 + 0.45 * hash11(hd * 91.7));
}

// splashes on the ground band: little flattened rings that open and fade
float splashes(vec2 uvd, float t) {
  if (uGround < 0.0 || uvd.y < uGround) return 0.0;
  float depth = sat((uvd.y - uGround) / max(1e-3, 1.0 - uGround));   // nearer is lower
  float cell = mix(16.0, 42.0, depth);
  vec2 g = uvd * uRes / cell;
  vec2 c = floor(g), f = fract(g) - 0.5;
  float h = hash12(c + uSeed * 7.0);
  float tt = t * (2.2 + 1.5 * h) * uSplash + h * 10.0;
  float k = floor(tt), ph = fract(tt);
  float h2 = hash12(c + k * 1.7 + uSeed);
  if (h2 > 0.45 * uSplash) return 0.0;
  vec2 o = (hash22(c + k) - 0.5) * 0.6;
  float r = ph * 0.42;
  float d = length((f - o) * vec2(1.0, 2.8)) - r;
  float ring = exp(-d * d * 1400.0) * (1.0 - ph) * (1.0 - ph);
  float bead = exp(-dot(f - o - vec2(0.0, 0.18 * ph), f - o - vec2(0.0, 0.18 * ph)) * 900.0) * step(ph, 0.35) * 0.6;
  return (ring + bead) * mix(0.5, 1.0, depth);
}

vec4 effect(vec2 p, vec2 uv) {
  vec2 pd = vec2(p.x, -p.y);
  pd = rot2(uAngle) * pd;
  float r = 0.0;
  for (int i = 0; i < 6; i++) {
    if (float(i) >= uLayers) break;
    r += rainLayer(pd, uClock, float(i));
  }
  r += splashes(vec2(uv.x, 1.0 - uv.y), uClock);
  r = sat(r * uOpacity * uIntensity);
  return vec4(uColor * r, r);
}`;
  }

  protected override update(f: Frame) {
    const u = this.u, P = (k: string, d: number) => this.k(k, d);
    const lt = f.t - this.ctx.start;
    const { clock, rate } = rainClock(lt, this.k<[number, number][]>('slow', []));
    u.uLayers.value = Math.max(1, Math.min(6, Math.round(P('layers', 4))));
    u.uDensity.value = P('density', 1);
    u.uLen.value = P('length', 1);
    u.uAngle.value = (P('angle', 8) * Math.PI) / 180;
    u.uOpacity.value = P('opacity', 0.55);
    u.uClock.value = clock * this.k('speed', 1) + this.k('offset', 0) + this.ctx.start;
    u.uLenK.value = 0.12 + 0.88 * Math.min(1, Math.max(0, rate));
    u.uGround.value = P('ground', -1);
    u.uSplash.value = P('splash', 1);
    const fade = this.k<Keys | Track | null>('fade', null);
    u.uOpacity.value *= fade ? Math.max(0, trackAt(fade, lt)) : 1;
  }

  override render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    super.render(f, out);
    const l = lightningAt(f.t - this.ctx.start, this.k<number[]>('lightning', []));
    if (l > 0.001) return { exposure: 1 + 0.9 * l };
  }
}

export default Rain;
