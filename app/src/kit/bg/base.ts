// The base of every animated background (kit/bg): one fullscreen GLSL pass, a pure function of time, with the params
// every background shares. A background writes `vec4 effect(vec2 p, vec2 uv)`: its light, premultiplied, and how much
// of the base it covers (alpha). The base composites it over the block's `background` (opaque), or leaves it
// transparent (background 'none': premultiplied, alpha = coverage, so it stacks over another block in a Stack or plays
// as an overlay), then dithers it (a static ±1 level triangular dither in display space: no banding in the slow ramps).
//
// Shared params (all optional):
//   color 'accent', color2 'accent2'   palette roles or #hex: the background's two inks
//   background 'theme'                 the base under it: 'theme' (bg), a role, #hex, { from, to, angle? }, or 'none'
//   intensity 1                        how bright the inks are (0.5: quieter, under busy type)
//   speed 1                            how fast it moves (0: frozen)
//   scale 1                            how big its features are (2: twice as large)
//   seed 0                             another arrangement of the same background
//   pulse 'none'                       'beat' | 'downbeat': it swells on the grid and decays (motion.ts onBeat, onDownbeat)
//   pulseAmount 0.35                   how far it swells
//   glow 1.8                           the level its hottest accent cores reach (look.ts glow; 0..GLOW_LEVEL). Only an
//                                      accent ink (or a saturated #hex) is driven past white to bloom: fg never blooms
//   clock 'film'                       'film': it moves on film time, so one background continues across cuts; 'shot'
//   offset 0                           seconds added to its clock
//
// GLSL a background can use: uniforms uTime (its clock times speed, s), uRes (W, H logical px), uIntensity, uScale,
// uSeed, uPulse (0..1, decaying), uColor, uColor2 (linear), uHot1, uHot2 (the inks driven to their glow level: mix
// toward them for a core that blooms); p is the frame centred, in units of its short side (y up); uv is 0..1 (y up).
import * as THREE from 'three';
import { FSPass } from '../../engine/gl';
import { H, W } from '../../engine/config';
import { BLOOM_CHROMA, GLOW_LEVEL, bloomChroma, type RGB } from '../../engine/look';
import { lin } from '../../engine/palette';
import { onBeat, onDownbeat } from '../../engine/motion';
import { Scene, type Frame, type PostOverrides, type SceneCtx } from '../../engine/scene';
import type { Handles } from '../../engine/transition';
import type { Background as BackgroundSpec } from '../common';

export type Pulse = 'beat' | 'downbeat' | 'none';

export interface BgParams {
  color?: string;
  color2?: string;
  background?: BackgroundSpec;
  intensity?: number;
  speed?: number;
  scale?: number;
  seed?: number;
  pulse?: Pulse;
  pulseAmount?: number;
  glow?: number;
  clock?: 'film' | 'shot';
  offset?: number;
}

const ACCENTS = new Set(['accent', 'accentBright', 'accentDim', 'accent2', 'accent2Dim', 'accent2Bright']);

/**
 * The level an ink's hottest core may reach: `level` for an accent role, or a #hex as saturated as an accent (it passes
 * the bloom's chroma gate whole); anything else (fg, the surfaces, a pale #hex) stays at its own colour, so it never
 * blooms. Capped at GLOW_LEVEL + 1.
 */
export function inkLevel(key: string, level: number): number {
  const c = lin(key), m = Math.max(c[0], c[1], c[2], 1e-4);
  const lvl = Math.max(0, Math.min(level, GLOW_LEVEL + 1));
  const glows = ACCENTS.has(key) || (key.startsWith('#') && bloomChroma(c) >= BLOOM_CHROMA[1]);
  return glows ? Math.max(lvl, m) : m;
}

/** An ink driven so its brightest channel reads `level` (look.ts glow, for any role or #hex). */
export function hotInk(key: string, level: number): RGB {
  const c = lin(key), m = Math.max(c[0], c[1], c[2], 1e-4), k = inkLevel(key, level) / m;
  return [c[0] * k, c[1] * k, c[2] * k];
}

/** The pulse at a frame: 0 for 'none', else the house beat (or downbeat) pulse. Throws on an unknown kind. */
export function pulseAt(kind: Pulse, f: Pick<Frame, 'beatPhase' | 'barPhase' | 'beatsPerBar'>): number {
  if (kind === 'none') return 0;
  if (kind === 'beat') return onBeat(f as Frame, 0.3);
  if (kind === 'downbeat') return onDownbeat(f as Frame, 0.6);
  throw new Error(`pulse is 'beat', 'downbeat' or 'none', got '${kind}'`);
}

const BG_GLSL = /* glsl */ `
uniform float uTime, uIntensity, uScale, uSeed, uPulse;
uniform vec2 uRes;
uniform vec3 uColor, uColor2, uHot1, uHot2, uBaseA, uBaseB;
uniform vec2 uBaseDir;
uniform bool uTransparent;
/** An ink's luminance-free mix toward its glow level: k = 0 the ink, 1 its hot core. */
vec3 ink1(float k) { return mix(uColor, uHot1, sat(k)); }
vec3 ink2(float k) { return mix(uColor2, uHot2, sat(k)); }
/** Two linear colours mixed as the eye sees them (display space). */
vec3 mixD(vec3 a, vec3 b, float k) { return toLinear(mix(toSRGB(a), toSRGB(b), k)); }
`;

const MAIN_GLSL = /* glsl */ `
void main() {
  vec2 px = FRAG_PX;
  vec2 uv = px / uRes;
  vec2 p = (px - 0.5 * uRes) / min(uRes.x, uRes.y);
  vec4 e = effect(p, uv);
  vec4 o;
  if (uTransparent) o = e;
  else {
    float k = sat(dot(uv - 0.5, uBaseDir) + 0.5);
    vec3 base = mixD(uBaseA, uBaseB, k * k * (3.0 - 2.0 * k));
    o = vec4(e.rgb + base * (1.0 - sat(e.a)), 1.0);
  }
  // a static triangular dither of ±1 display level: the slow ramps never band
  float d = hash12(floor(gl_FragCoord.xy) + 17.0) + hash12(floor(gl_FragCoord.xy) * 1.37 + 91.0) - 1.0;
  vec3 s = toSRGB(max(o.rgb, 0.0));
  o.rgb = toLinear(max(s + d / 255.0 * step(1e-5, s + o.a), 0.0));
  fragColor = o;
}`;

/**
 * A background block: subclasses give their GLSL (`effect`), their own uniforms and their defaults. Everything is a
 * function of the frame, so it can run before its start and past its end (handles of a second either side).
 */
export abstract class BgScene extends Scene {
  override handles: Handles = { head: 1, tail: 1 };
  protected pass: FSPass | null = null;
  /** The background's own defaults (a film's params override them). */
  protected defaults: Partial<BgParams> & Record<string, unknown> = {};
  private base = {
    uTime: { value: 0 }, uRes: { value: new THREE.Vector2(1, 1) }, uIntensity: { value: 1 }, uScale: { value: 1 },
    uSeed: { value: 0 }, uPulse: { value: 0 }, uColor: { value: new THREE.Vector3() }, uColor2: { value: new THREE.Vector3() },
    uHot1: { value: new THREE.Vector3() }, uHot2: { value: new THREE.Vector3() }, uBaseA: { value: new THREE.Vector3() },
    uBaseB: { value: new THREE.Vector3() }, uBaseDir: { value: new THREE.Vector2(0, -1) }, uTransparent: { value: false },
  };

  constructor(ctx: SceneCtx) {
    super(ctx);
  }

  /** GLSL: the background's own uniforms and helpers, and `vec4 effect(vec2 p, vec2 uv)` (premultiplied light, alpha). */
  protected abstract effect(): string;
  /** The background's own uniforms (set them per frame in update()). */
  protected uniforms(): Record<string, THREE.IUniform> {
    return {};
  }
  /** Per frame: set the background's own uniforms. `time` is its clock (s, times speed). */
  protected update(_f: Frame, _time: number): void {}

  /** A param: the film's, else the background's default, else `fallback`. */
  protected k<T>(key: string, fallback: T): T {
    const v = this.ctx.params[key] ?? this.defaults[key];
    return (v ?? fallback) as T;
  }

  override init() {
    const pulse = this.k<Pulse>('pulse', 'none');
    pulseAt(pulse, { beatPhase: 0, barPhase: 0, beatsPerBar: 4 }); // (throws on an unknown kind, at load)
    for (const key of ['intensity', 'speed', 'scale', 'seed', 'pulseAmount', 'glow', 'offset']) {
      const v = this.ctx.params[key];
      if (v !== undefined && !(typeof v === 'number' && Number.isFinite(v))) throw new Error(`shot ${this.ctx.id}: param '${key}' is a number, got ${JSON.stringify(v)}`);
    }
    this.pass = new FSPass(BG_GLSL + this.effect() + MAIN_GLSL, { ...this.base, ...this.uniforms() });
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    const u = this.base;
    const time = ((this.k<'film' | 'shot'>('clock', 'film') === 'shot' ? f.lt : f.t) + this.k('offset', 0)) * this.k('speed', 1);
    u.uTime.value = time;
    u.uRes.value.set(W, H);
    u.uIntensity.value = this.k('intensity', 1);
    u.uScale.value = Math.max(0.05, this.k('scale', 1));
    u.uSeed.value = this.k('seed', 0);
    u.uPulse.value = pulseAt(this.k<Pulse>('pulse', 'none'), f) * this.k('pulseAmount', 0.35);
    const c1 = this.k('color', 'accent'), c2 = this.k('color2', 'accent2'), glow = this.k('glow', 1.8);
    u.uColor.value.set(...lin(c1));
    u.uColor2.value.set(...lin(c2));
    u.uHot1.value.set(...hotInk(c1, glow));
    u.uHot2.value.set(...hotInk(c2, glow));
    const bg = this.k<BackgroundSpec>('background', 'theme');
    u.uTransparent.value = bg === 'none';
    if (typeof bg === 'object') {
      u.uBaseA.value.set(...lin(bg.from));
      u.uBaseB.value.set(...lin(bg.to));
      const r = ((bg.angle ?? 90) * Math.PI) / 180;
      u.uBaseDir.value.set(Math.cos(r), -Math.sin(r));
    } else if (bg !== 'none') {
      const c = lin(bg === 'theme' ? 'bg' : bg);
      u.uBaseA.value.set(...c);
      u.uBaseB.value.set(...c);
    }
    this.update(f, time);
    this.pass!.render(this.ctx.renderer, out);
  }

  override dispose() {
    this.pass?.mat.dispose();
    this.pass = null;
  }
}
